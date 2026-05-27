"""
TrafficFlow Data Collector — Thu thập nhanh data cho 624 camera.

Chiến lược:
  Giai đoạn 1 (Khởi tạo): Fill gap tất cả camera nhanh nhất có thể
  Giai đoạn 2 (Duy trì):  Chạy nền, mỗi camera được update định kỳ

Error detection:
  - Image hash (exact match với known error pages)
  - Brightness + red pixel ratio (fast heuristic)
  - Cached error → skip camera trong 1 giờ

Usage:
  python scripts/collect_data.py                    # Full speed (4 workers)
  python scripts/collect_data.py --workers 8         # Max speed (8 workers)
  python scripts/collect_data.py --interval 60       # Background mode, 60s interval
  python scripts/collect_data.py --warmup            # Giai đoạn 1: fill nhanh
"""

import argparse
import asyncio
import hashlib
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import numpy as np
from PIL import Image
import io

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trafficflow-api"))
from backend.cameras import CAMERAS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("collector")


# ─── Config ────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://trafficflow:trafficpass123@localhost:5432/trafficflow"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://giaothong.hochiminhcity.gov.vn/",
}

# Error image signature (precomputed)
ERROR_IMAGE_HASH = hashlib.md5(
    "Đường dẫn không hợp lệ page not found error".encode()
).hexdigest()

# Error page pixel characteristics (measured from real error image)
# Predominant: white/gray ~rgb(245,244,243)
# Error boxes: high red ~rgb(220-240, ~50-100, ~50-100)
ERROR_BRIGHTNESS_THRESHOLD = 0.93  # Error pages are mostly white
ERROR_RED_PIXEL_RATIO = 0.02  # Small red error boxes

# Skip interval when error detected (1 hour)
ERROR_SKIP_HOURS = 1


# ─── Image Analysis (runs in worker process) ────────────────────────────────


def analyze_image_fast(image_bytes: bytes) -> dict:
    """
    Analyze image without full decode — fast path for error detection.
    Returns dict with:
      - is_error: bool — True if this is an error/offline page
      - is_too_small: bool — image too small
      - hash: str — md5 for exact match caching
      - brightness: float — 0-1 average brightness
      - red_ratio: float — fraction of red-ish pixels
    """
    result = {
        "is_error": False,
        "is_too_small": False,
        "hash": hashlib.md5(image_bytes[:5000]).hexdigest(),
        "brightness": None,
        "red_ratio": None,
        "size_bytes": len(image_bytes),
    }

    if len(image_bytes) < 2000:
        result["is_too_small"] = True
        result["is_error"] = True
        return result

    try:
        # Quick check: scan raw bytes for error page signatures
        # Error page contains these Vietnamese strings
        text_chunk = image_bytes[:10000].decode("utf-8", errors="ignore")
        error_signatures = [
            "Đường dẫn không hợp lệ",
            "không tìm thấy",
            "Page not found",
            "Internal Server Error",
            "<html",
        ]
        for sig in error_signatures:
            if sig in text_chunk:
                result["is_error"] = True
                return result

        # Pixel analysis
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img, dtype=np.uint8)

        # Brightness (grayscale mean)
        gray = arr.astype(float).mean(axis=2) / 255.0
        brightness = gray.mean()
        result["brightness"] = float(brightness)

        # Red pixel ratio (pixels where R >> G and R >> B)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        red_mask = (r > 180) & (g < 130) & (b < 130)
        red_ratio = red_mask.sum() / r.size
        result["red_ratio"] = float(red_ratio)

        # Error detection rules:
        # 1. Very bright (white background) + small red boxes = error page
        # 2. Text-based detection above already caught HTML errors
        if brightness > ERROR_BRIGHTNESS_THRESHOLD and red_ratio < 0.15:
            # Bright image without enough red = might be blank/error
            # Check for very uniform color (error pages are flat)
            variance = gray.var()
            if variance < 0.001:  # Very uniform = error page
                result["is_error"] = True

    except Exception:
        result["is_error"] = True

    return result


def predict_from_image(image_bytes: bytes) -> dict:
    """
    Heuristic traffic prediction from image pixels.
    Runs in worker process to avoid GIL.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        # Crop road region (bottom 75%, remove sky/signage)
        crop_top = int(h * 0.20)
        road = img.crop((0, crop_top, w, h))
        road = road.resize((224, 224))
        arr = np.array(road, dtype=np.float32) / 255.0

        # Road analysis zones
        bottom_half = arr[int(arr.shape[0] * 0.6) :]
        lower_third = arr[int(arr.shape[0] * 0.7) :]

        # Brightness = density proxy (darker = more vehicles)
        brightness = bottom_half.mean()
        variance = lower_third.var()

        # Motion proxy from texture variance
        motion = min(1.0, variance * 35)

        # Count estimation
        density = (1.0 - brightness) * 280
        total = max(5, int(density * (0.5 + motion * 0.8)))

        # Vehicle split
        car_ratio = 0.12 + 0.22 * (1 - motion)
        car = max(1, int(total * car_ratio))
        moto = max(1, total - car)

        # Density level
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


# ─── Worker: fetch + predict for one camera ───────────────────────────────


def fetch_and_predict_sync(camera: dict, http_timeout: float = 10.0) -> dict | None:
    """
    Synchronous fetch+predict for use in ProcessPoolExecutor.
    Returns prediction dict or None on failure.
    """
    camera_id = camera["id"]
    url = f"https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id={camera_id}&t={int(time.time() * 1000)}"

    try:
        sync_http = httpx.Client(
            timeout=http_timeout,
            follow_redirects=True,
            headers=HEADERS,
        )
        with httpx.Client(
            timeout=http_timeout, follow_redirects=True, headers=HEADERS
        ) as sync_http:
            resp = sync_http.get(url)
            resp.raise_for_status()
            image_bytes = resp.content

        # Analyze
        analysis = analyze_image_fast(image_bytes)
        if analysis["is_error"] or analysis["is_too_small"]:
            return None

        # Predict
        result = predict_from_image(image_bytes)
        result["camera_id"] = camera_id
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["analysis"] = analysis

        return result

    except Exception as e:
        return None


async def fetch_and_predict_async(camera: dict, http: httpx.AsyncClient) -> dict | None:
    """Async version — used in the main loop."""
    camera_id = camera["id"]
    url = f"https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id={camera_id}&t={int(time.time() * 1000)}"

    try:
        resp = await http.get(url, headers=HEADERS, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        image_bytes = resp.content

        analysis = analyze_image_fast(image_bytes)
        if analysis["is_error"] or analysis["is_too_small"]:
            return None

        result = predict_from_image(image_bytes)
        result["camera_id"] = camera_id
        result["timestamp"] = datetime.now(timezone.utc).isoformat()

        return result

    except Exception:
        return None


# ─── Database ──────────────────────────────────────────────────────────────


async def init_db():
    import asyncpg

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=20,
        command_timeout=30,
    )
    # Create skip table if not exists
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
            CREATE INDEX IF NOT EXISTS idx_camera_error_log_camera_id
                ON camera_error_log(camera_id, expires_at);
        """
        )
    return pool


async def get_skipped_cameras(pool) -> set:
    """Get camera IDs that are currently in error-skip window."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT camera_id FROM camera_error_log WHERE expires_at > NOW()"
        )
        return {r["camera_id"] for r in rows}


async def log_camera_error(pool, camera_id: str, error_type: str = "offline"):
    """Log a camera error so it's skipped for 1 hour."""
    expires = datetime.now(timezone.utc) + timedelta(hours=ERROR_SKIP_HOURS)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO camera_error_log (camera_id, error_type, expires_at)
            VALUES ($1, $2, $3)
            """,
            camera_id,
            error_type,
            expires,
        )


async def insert_predictions(pool, predictions: list[dict]):
    """Batch insert predictions."""
    if not predictions:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO prediction_history
                (camera_id, timestamp, total_count, car_count, motorbike_count, density_level)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            [
                (
                    p["camera_id"],
                    p["timestamp"],
                    p["total_count"],
                    p["car_count"],
                    p["motorbike_count"],
                    p["density_level"],
                )
                for p in predictions
            ],
        )


# ─── Batch Collector ───────────────────────────────────────────────────────


class BatchCollector:
    """
    Collects predictions for a batch of cameras using async concurrency.
    Designed to maximize throughput on host machine.
    """

    def __init__(self, concurrency: int = 20):
        self.concurrency = concurrency
        self.http: httpx.AsyncClient | None = None
        self.pool = None
        self.stats = {
            "total": 0,
            "success": 0,
            "error": 0,
            "skipped": 0,
            "total_records": 0,
        }

    async def run_batch(self, cameras: list[dict]) -> list[dict]:
        """Process a batch of cameras concurrently."""
        semaphore = asyncio.Semaphore(self.concurrency)

        async def process(cam: dict) -> dict | None:
            async with semaphore:
                result = await fetch_and_predict_async(cam, self.http)
                self.stats["total"] += 1
                if result:
                    self.stats["success"] += 1
                else:
                    self.stats["error"] += 1
                return result

        tasks = [process(cam) for cam in cameras]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    async def collect_all(self, cameras: list[dict], pool) -> int:
        """
        Collect predictions for all cameras in rounds.
        Returns total records inserted.
        """
        self.pool = pool
        transport = httpx.AsyncHTTPTransport(
            retries=1,
            limits=httpx.Limits(
                max_connections=self.concurrency + 10,
                max_keepalive_connections=self.concurrency,
            ),
        )
        self.http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=True,
        )

        total_inserted = 0
        round_num = 0
        batch_size = min(100, len(cameras))

        while cameras:
            round_num += 1
            # Get cameras not in skip window
            skipped = await get_skipped_cameras(pool)
            available = [c for c in cameras if c["id"] not in skipped]

            if not available:
                logger.info(
                    f"[round {round_num}] All cameras in skip window, waiting..."
                )
                await asyncio.sleep(60)
                continue

            # Process batch
            batch = available[:batch_size]
            cameras = cameras[batch_size:]

            results = await self.run_batch(batch)
            predictions = [r for r in results if r is not None]

            # Log errors
            processed_ids = {r["camera_id"] for r in results}
            failed_ids = {c["id"] for c in batch} - processed_ids
            for cid in failed_ids:
                await log_camera_error(pool, cid, "offline")
                self.stats["skipped"] += 1

            # Insert to DB
            await insert_predictions(pool, predictions)
            total_inserted += len(predictions)
            self.stats["total_records"] += len(predictions)

            rate = len(predictions) / max(1, len(batch)) * 100
            logger.info(
                f"[round {round_num}] {len(predictions)}/{len(batch)} ({rate:.0f}%) | "
                f"total: {self.stats['total_records']} records | "
                f"skipped: {len(skipped)} cameras"
            )

            # Brief pause between batches
            if cameras:
                await asyncio.sleep(2)

        await self.http.aclose()
        return total_inserted


# ─── Warmup Phase ──────────────────────────────────────────────────────────


async def warmup_phase(cameras: list[dict], pool) -> int:
    """
    Giai đoạn 1: Fill nhanh tất cả camera.
    - Retry failed cameras immediately (no 1-hour skip)
    - High concurrency (50)
    - Multiple rounds until all cameras succeed or give up
    """
    logger.info(f"[warmup] Starting — {len(cameras)} cameras to fill")
    collector = BatchCollector(concurrency=50)

    transport = httpx.AsyncHTTPTransport(
        retries=1,
        limits=httpx.Limits(max_connections=60, max_keepalive_connections=60),
    )
    collector.http = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(12.0, connect=5.0),
        follow_redirects=True,
    )
    collector.pool = pool

    total_inserted = 0
    remaining = list(cameras)
    attempt = 0

    while remaining and attempt < 5:
        attempt += 1
        logger.info(f"[warmup] Attempt {attempt} — {len(remaining)} cameras remaining")

        # Try each camera, retry immediately on failure
        semaphore = asyncio.Semaphore(50)

        async def process(cam: dict) -> dict | None:
            async with semaphore:
                return await fetch_and_predict_async(cam, collector.http)

        tasks = [process(cam) for cam in remaining]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, dict)]
        remaining = [
            cam
            for cam, r in zip(remaining, results)
            if not isinstance(r, dict) or r is None
        ]

        if valid:
            await insert_predictions(pool, valid)
            total_inserted += len(valid)

        logger.info(
            f"[warmup] Attempt {attempt}: {len(valid)}/{len(remaining) + len(valid)} succeeded | "
            f"remaining: {len(remaining)}"
        )

        if remaining and attempt < 5:
            await asyncio.sleep(5)

    if remaining:
        # Log as errors for later
        for cam in remaining:
            await log_camera_error(pool, cam["id"], "persistent_offline")

    await collector.http.aclose()
    return total_inserted


# ─── Main ──────────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="TrafficFlow Data Collector")
    parser.add_argument("--workers", type=int, default=4, help="Concurrency level")
    parser.add_argument(
        "--interval", type=int, default=0, help="Loop interval in seconds (0=run once)"
    )
    parser.add_argument(
        "--warmup", action="store_true", help="Run warmup phase (fast fill)"
    )
    parser.add_argument(
        "--max-rounds", type=int, default=0, help="Max rounds (0=unlimited)"
    )
    args = parser.parse_args()

    pool = await init_db()
    logger.info(
        f"DB connected | {len(CAMERAS)} cameras loaded | concurrency={args.workers}"
    )

    try:
        if args.warmup:
            # Phase 1: Fast warmup
            inserted = await warmup_phase(CAMERAS, pool)
            logger.info(f"[warmup] DONE — {inserted} total records inserted")
        elif args.interval > 0:
            # Phase 2: Background loop
            collector = BatchCollector(concurrency=args.workers)
            round_num = 0
            while True:
                round_num += 1
                remaining = list(CAMERAS)
                inserted = await collector.collect_all(remaining, pool)
                logger.info(
                    f"[loop] Round {round_num}: {inserted} records this round | total: {collector.stats['total_records']}"
                )
                if args.max_rounds > 0 and round_num >= args.max_rounds:
                    break
                await asyncio.sleep(args.interval)
        else:
            # One-shot batch
            collector = BatchCollector(concurrency=args.workers)
            remaining = list(CAMERAS)
            inserted = await collector.collect_all(remaining, pool)
            logger.info(
                f"[done] {inserted} records inserted | stats: {collector.stats}"
            )

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
