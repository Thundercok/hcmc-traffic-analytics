"""
Background worker to continuously record predictions to database.
Processes ALL 624 cameras in rotation with error detection and offline skipping.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
from PIL import Image
import io

from .database import init_db_pool, init_schema, record_prediction, get_pool
from .cameras import CAMERAS
from .config import settings
from .prediction_cache import PredictionCache

logger = logging.getLogger("trafficflow.writer")

CAMERA_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://giaothong.hochiminhcity.gov.vn/",
}

# Error page detection thresholds
ERROR_BRIGHTNESS_MIN = 0.90
ERROR_SIZE_MIN = 2000
ERROR_VARNCE_MAX = 0.0005

# Skip offline cameras for 30 minutes
OFFLINE_SKIP_HOURS = 0.5

# Data retention — keep only last 60 minutes
DATA_RETENTION_MINUTES = 60
CLEANUP_INTERVAL_BATCHES = 10  # run cleanup every 10 batches


def _is_error_image(image_bytes: bytes) -> tuple[bool, str]:
    """
    Fast error detection without full decode.
    Returns (is_error, reason)
    """
    if len(image_bytes) < ERROR_SIZE_MIN:
        return True, "too_small"

    try:
        text = image_bytes[:8000].decode("utf-8", errors="ignore")
        for sig in (
            "Đường dẫn không hợp lệ",
            "Page not found",
            "không tìm thấy",
            "<html>",
            "Internal Server Error",
        ):
            if sig in text:
                return True, "text_signature"
    except Exception:
        pass

    try:
        img = Image.open(io.BytesIO(image_bytes[:500_000])).convert("RGB")
        arr = np.array(img, dtype=np.float32) / 255.0

        # Bright image + low variance = error/blank page
        brightness = arr.mean()
        variance = arr.var()

        if brightness > ERROR_BRIGHTNESS_MIN and variance < ERROR_VARNCE_MAX:
            return True, "flat_bright_page"

        # Check for red error boxes (very small red regions in mostly white image)
        if brightness > ERROR_BRIGHTNESS_MIN:
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            red_mask = (r > 0.7) & (g < 0.4) & (b < 0.4)
            red_ratio = red_mask.sum() / r.size
            # White page with tiny red boxes = error page
            if variance < 0.01 and red_ratio < 0.05:
                return True, "error_boxes"

    except Exception:
        return True, "decode_failed"

    return False, ""


def _heuristic_predict(image_bytes: bytes) -> dict:
    """
    Fast pixel-based traffic estimation.
    No ML model needed — uses road density analysis.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        # Crop road region (bottom 80%, remove sky/signage)
        crop = img.crop((0, int(h * 0.18), w, h))
        crop = crop.resize((224, 224))
        arr = np.array(crop, dtype=np.float32) / 255.0

        # Split into horizontal lanes (top=far, bottom=near)
        far_lanes = arr[: int(arr.shape[0] * 0.4)]
        near_lanes = arr[int(arr.shape[0] * 0.7) :]

        # Darkness proxy: darker = more vehicles
        brightness_far = 1.0 - far_lanes.mean()
        brightness_near = 1.0 - near_lanes.mean()

        # Texture/motion proxy: more variance = more movement = denser
        texture_far = min(far_lanes.var() * 50, 1.0)
        texture_near = min(near_lanes.var() * 40, 1.0)

        # Weighted combination
        density = (
            brightness_far * 0.35 * (0.5 + texture_far * 0.5)
            + brightness_near * 0.65 * (0.5 + texture_near * 0.5)
        ) * 350

        total = max(5, int(density))

        # Vehicle split
        moto_ratio = 0.70 + 0.15 * texture_near
        moto = max(1, int(total * moto_ratio))
        car = max(1, total - moto)

        if total < 50:
            level = "low"
        elif total < 200:
            level = "moderate"
        elif total < 400:
            level = "heavy"
        else:
            level = "severe"

        return {
            "total_count": total,
            "car_count": car,
            "motorbike_count": moto,
            "density_level": level,
        }

    except Exception:
        return {
            "total_count": 30,
            "car_count": 5,
            "motorbike_count": 25,
            "density_level": "moderate",
        }


class PredictionWriter:
    """
    Continuous prediction writer for all cameras.
    - High concurrency (30 parallel fetches)
    - Error detection + offline skipping (30min cache)
    - Heuristic prediction (no ML overhead)
    - Continuous cycling through all cameras every batch_interval
    """

    # Reset skipped cameras every N batches to retry offline cameras
    SKIP_RESET_BATCHES = 10

    def __init__(self, interval_seconds: int = 15, batch_size: int = 100):
        self.interval = max(interval_seconds, 15)  # Minimum 15 seconds
        self.batch_size = min(batch_size, len(CAMERAS))
        self.running = False
        self._task = None
        self._http: httpx.AsyncClient | None = None
        self._cursor = 0
        self._total_records = 0
        self._skipped_this_session = set()
        self._session_start = datetime.now(timezone.utc)
        self._batches_since_cleanup = 0
        self._batches_count = 0

    async def start(self):
        if self.running:
            return

        try:
            await init_db_pool()
            await init_schema()
            await self._ensure_skip_table()
            logger.info("[writer] Database ready")
        except Exception as e:
            logger.error(f"[writer] DB init failed: {e}")
            return

        transport = httpx.AsyncHTTPTransport(
            retries=2,
            limits=httpx.Limits(
                max_connections=40,
                max_keepalive_connections=30,
            ),
        )
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=True,
        )

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"[writer] Started — interval={self.interval}s, batch={self.batch_size}"
        )

    async def _ensure_skip_table(self):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_error_log (
                    id SERIAL PRIMARY KEY,
                    camera_id TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cam_error_expires
                    ON camera_error_log(camera_id, expires_at);
            """
            )

    async def _get_skipped_cameras(self) -> set:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT camera_id FROM camera_error_log WHERE expires_at > NOW()"
            )
            return {r["camera_id"] for r in rows}

    async def _log_error(self, camera_id: str, error_type: str):
        pool = await get_pool()
        expires = datetime.now(timezone.utc) + timedelta(hours=OFFLINE_SKIP_HOURS)
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO camera_error_log(camera_id, error_type, expires_at) VALUES($1, $2, $3)",
                camera_id,
                error_type,
                expires,
            )

    async def _cleanup_old_data(self):
        """Delete records older than DATA_RETENTION_MINUTES."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            deleted = await conn.fetchval(
                """
                DELETE FROM prediction_history
                WHERE timestamp < NOW() - INTERVAL '%d minutes'
                RETURNING COUNT(*)
                """
                % DATA_RETENTION_MINUTES
            )
            if deleted and deleted > 0:
                logger.info(
                    f"[writer] Cleaned up {deleted} old records (>{DATA_RETENTION_MINUTES}min)"
                )

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
        logger.info(f"[writer] Stopped — total records: {self._total_records}")

    async def _run_loop(self):
        # Warmup: immediate first batch
        logger.info("[writer] Warmup batch...")
        await self._process_batch()

        while self.running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"[writer] Batch error: {e}", exc_info=True)
            await asyncio.sleep(self.interval)

    async def _process_batch(self):
        self._batches_count += 1
        self._batches_since_cleanup += 1

        # Reset session skipped set periodically to retry offline cameras
        if self._batches_count % self.SKIP_RESET_BATCHES == 0:
            cleared = len(self._skipped_this_session)
            self._skipped_this_session.clear()
            if cleared > 0:
                logger.info(
                    f"[writer] Reset skipped set ({cleared} cameras will be retried)"
                )

        if self._batches_since_cleanup >= CLEANUP_INTERVAL_BATCHES:
            self._batches_since_cleanup = 0
            # Run cleanup in background (don't block the batch)
            asyncio.create_task(self._cleanup_old_data())

        skipped = await self._get_skipped_cameras()

        # Select next cameras (cycle through all)
        batch = []
        for i in range(len(CAMERAS)):
            idx = (self._cursor + i) % len(CAMERAS)
            c = CAMERAS[idx]
            if c["id"] not in skipped and c["id"] not in self._skipped_this_session:
                batch.append(c)
                if len(batch) >= self.batch_size:
                    break

        if not batch:
            logger.warning("[writer] All cameras in skip window, waiting...")
            return

        self._cursor = (self._cursor + len(batch)) % len(CAMERAS)

        semaphore = asyncio.Semaphore(30)

        async def process(cam: dict) -> dict | None:
            async with semaphore:
                camera_id = cam["id"]
                url = f"https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id={camera_id}"

                try:
                    resp = await self._http.get(url, headers=CAMERA_FETCH_HEADERS)
                    resp.raise_for_status()
                    image_bytes = resp.content

                    is_err, reason = _is_error_image(image_bytes)
                    if is_err:
                        await self._log_error(camera_id, reason)
                        self._skipped_this_session.add(camera_id)
                        return None

                    pred = _heuristic_predict(image_bytes)
                    return {
                        "camera_id": camera_id,
                        "timestamp": datetime.now(timezone.utc),
                        **pred,
                    }

                except httpx.TimeoutException:
                    await self._log_error(camera_id, "timeout")
                    self._skipped_this_session.add(camera_id)
                    return None
                except Exception as e:
                    logger.warning(f"[writer] {camera_id}: {e}")
                    return None

        tasks = [process(cam) for cam in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        cache = PredictionCache.get_instance()
        valid = [r for r in results if isinstance(r, dict)]
        for r in valid:
            try:
                await record_prediction(
                    camera_id=r["camera_id"],
                    timestamp=r["timestamp"],
                    total_count=r["total_count"],
                    car_count=r["car_count"],
                    motorbike_count=r["motorbike_count"],
                    density_level=r["density_level"],
                )
                cache.record(r["camera_id"], r)
                self._total_records += 1
            except Exception:
                pass

        success = len(valid)
        total = len(batch)
        logger.info(
            f"[writer] Batch: {success}/{total} ({success/total*100:.0f}%) | "
            f"cursor={self._cursor}/{len(CAMERAS)} | total_records={self._total_records}"
        )


_writer: PredictionWriter | None = None


async def start_writer(interval_seconds: int = 15):
    global _writer
    if _writer is None:
        _writer = PredictionWriter(interval_seconds=interval_seconds)
        await _writer.start()
    return _writer


async def stop_writer():
    global _writer
    if _writer:
        await _writer.stop()
        _writer = None
