"""
Standalone prediction writer - runs on the HOST machine (not inside Docker).
This ensures camera images can be fetched from the public giaothong server.

Usage:
    python scripts/run_writer.py

Requirements (install on host):
    pip install httpx pillow asyncpg python-dotenv torch torchvision timm einops numpy scipy peft open-clip-torch opencv-python-headless PyYAML

Environment variables:
    DATABASE_URL=postgresql://trafficflow:trafficpass123@localhost:5432/trafficflow
    WRITER_INTERVAL_SECONDS=60
    WRITER_BATCH_SIZE=100
    WRITER_CONCURRENCY=12
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trafficflow-api"))

import httpx
import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("writer")

# Import camera list from backend
from backend.cameras import CAMERAS

# ─── Config ────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://trafficflow:trafficpass123@localhost:5432/trafficflow"
)
INTERVAL = int(os.environ.get("WRITER_INTERVAL_SECONDS", "60"))
BATCH_SIZE = int(os.environ.get("WRITER_BATCH_SIZE", "100"))
CONCURRENCY = int(os.environ.get("WRITER_CONCURRENCY", "12"))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://giaothong.hochiminhcity.gov.vn/",
    "Cache-Control": "no-cache",
}


class PredictionWriter:
    """Robust writer with retry, concurrency control, and graceful shutdown."""

    def __init__(self):
        self.running = False
        self._task = None
        self._http: httpx.AsyncClient | None = None
        self._pool: asyncpg.Pool | None = None
        self._cursor = 0
        self._total_records = 0
        self._success_streak = 0

    async def connect(self):
        """Initialize connections."""
        logger.info(f"[setup] Loading ZIP model on host CPU...")
        try:
            from backend.model_service import ZIPModelService
            from pathlib import Path

            zip_path = (
                Path(__file__).resolve().parent.parent
                / "trafficflow-api"
                / "ZIP"
                / "checkpoints"
                / "demo_data"
                / "best_mae_0_quantized.onnx"
            )
            svc = ZIPModelService.get_instance()
            if not svc.is_loaded:
                svc.load_model(str(zip_path), "cpu", 320)
            logger.info(f"[setup] ZIP model loaded: {svc.model_info}")
        except Exception as e:
            logger.warning(f"[setup] ZIP model load failed: {e}, will use heuristic")

        logger.info(f"[setup] Connecting to DB...")
        self._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("[setup] DB pool ready")

        transport = httpx.AsyncHTTPTransport(
            retries=2, limits=httpx.Limits(max_connections=20)
        )
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
        )
        logger.info("[setup] HTTP client ready")

    async def close(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
        if self._pool:
            await self._pool.close()
        logger.info(
            f"[setup] Shutdown complete. Total records written: {self._total_records}"
        )

    async def _fetch_and_predict(self, cam: dict) -> dict | None:
        """Fetch image and predict. Returns dict or None on failure."""
        camera_id = cam["id"]
        url = f"https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id={camera_id}"

        for attempt in range(3):
            try:
                resp = await self._http.get(url, headers=HEADERS)
                resp.raise_for_status()
                image_bytes = resp.content

                if len(image_bytes) < 1000:
                    logger.warning(
                        f"[{camera_id}] Image too small ({len(image_bytes)} bytes), skipping"
                    )
                    return None

                # Predict (CPU-optimized: runs on host, no Docker overhead)
                result = await self._predict(image_bytes)
                return {
                    "camera_id": camera_id,
                    "total_count": result["total_count"],
                    "car_count": result["car_count"],
                    "motorbike_count": result["motorbike_count"],
                    "density_level": result["density_level"],
                    "timestamp": datetime.now(timezone.utc),
                }

            except httpx.TimeoutException:
                logger.warning(f"[{camera_id}] Timeout (attempt {attempt + 1}/3)")
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"[{camera_id}] HTTP {e.response.status_code} (attempt {attempt + 1}/3)"
                )
            except Exception as e:
                logger.warning(f"[{camera_id}] {type(e).__name__}: {e}")

            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))

        return None

    async def _predict(self, image_bytes: bytes) -> dict:
        """
        Run ZIP model prediction on host CPU using the actual backend model.
        Falls back to heuristic if model fails to load.
        """
        try:
            from backend.model_service import ZIPModelService
            from PIL import Image
            import io

            svc = ZIPModelService.get_instance()
            if svc.is_loaded:
                result = svc.predict_from_bytes(image_bytes)
                return {
                    "total_count": result.get("total_count", 50),
                    "car_count": result.get("car_count", 8),
                    "motorbike_count": result.get("motorbike_count", 42),
                    "density_level": result.get("density_level", "moderate"),
                }
        except Exception as e:
            logger.warning(f"[predict] ZIP model error: {e}, using heuristic")

        # Heuristic fallback
        try:
            from PIL import Image
            import io
            import numpy as np

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            w, h = img.size

            # Crop to road region (bottom 70% of frame — sky removed)
            crop_top = int(h * 0.25)
            img = img.crop((0, crop_top, w, h))
            img = img.resize((224, 224))

            arr = np.array(img).astype(np.float32) / 255.0
            # Analyze lower half (road area has more texture/variance)
            lower = arr[int(arr.shape[0] * 0.5) :]
            brightness = lower.mean()
            variance = lower.var()

            # Motion proxy: high variance = more movement = denser traffic
            motion_factor = min(1.0, variance * 40)
            density = (1.0 - brightness) * 300 + motion_factor * 150
            total = max(5, int(density))

            car_ratio = 0.15 + 0.20 * (1 - motion_factor)
            car_count = max(1, int(total * car_ratio))
            motorbike_count = max(1, total - car_count)

            if total < 50:
                level = "low"
            elif total < 200:
                level = "moderate"
            else:
                level = "heavy"

            return {
                "total_count": total,
                "car_count": car_count,
                "motorbike_count": motorbike_count,
                "density_level": level,
            }
        except Exception as e:
            logger.warning(f"[predict] Heuristic also failed: {e}")
            return {
                "total_count": 50,
                "car_count": 8,
                "motorbike_count": 42,
                "density_level": "moderate",
            }

    async def _record_to_db(self, records: list[dict]):
        """Batch insert predictions into DB."""
        if not records:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO prediction_history
                    (camera_id, timestamp, total_count, car_count, motorbike_count, density_level)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        r["camera_id"],
                        r["timestamp"],
                        r["total_count"],
                        r["car_count"],
                        r["motorbike_count"],
                        r["density_level"],
                    )
                    for r in records
                ],
            )

    async def _run_batch(self):
        """Process a batch of cameras."""
        # Select next batch (cycling)
        batch = CAMERAS[self._cursor : self._cursor + BATCH_SIZE]
        if len(batch) < BATCH_SIZE:
            batch = batch + CAMERAS[: BATCH_SIZE - len(batch)]
        self._cursor = (self._cursor + BATCH_SIZE) % len(CAMERAS)

        logger.info(
            f"[batch] Processing {len(batch)} cameras (cursor={self._cursor}/{len(CAMERAS)})"
        )

        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def process(cam: dict) -> dict | None:
            async with semaphore:
                return await self._fetch_and_predict(cam)

        tasks = [process(cam) for cam in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid = [r for r in results if isinstance(r, dict)]
        await self._record_to_db(valid)

        self._total_records += len(valid)
        self._success_streak = len(valid)
        logger.info(
            f"[batch] Done: {len(valid)}/{len(batch)} recorded "
            f"| total: {self._total_records} | cursor: {self._cursor}/{len(CAMERAS)}"
        )

    async def run(self):
        """Main loop."""
        await self.connect()

        # Warmup: run immediately
        logger.info("[warmup] Running initial batch...")
        await self._run_batch()

        self.running = True
        logger.info(
            f"[loop] Starting main loop — interval={INTERVAL}s, batch={BATCH_SIZE}, concurrency={CONCURRENCY}"
        )

        while self.running:
            try:
                await self._run_batch()
            except Exception as e:
                logger.error(f"[loop] Batch error: {e}", exc_info=True)

            await asyncio.sleep(INTERVAL)


async def main():
    writer = PredictionWriter()
    try:
        await writer.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await writer.close()


if __name__ == "__main__":
    asyncio.run(main())
