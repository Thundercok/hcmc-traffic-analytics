"""
Database configuration and connection management.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

logger = logging.getLogger("trafficflow.db")

_pool: Optional[asyncpg.Pool] = None


async def init_db_pool(dsn: str = None) -> asyncpg.Pool:
    """Initialize database connection pool."""
    global _pool

    if _pool is not None:
        return _pool

    if dsn is None:
        dsn = os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('DB_USER', 'trafficflow')}:"
            f"{os.getenv('DB_PASSWORD', 'trafficpass123')}@"
            f"{os.getenv('DB_HOST', 'localhost')}:"
            f"{os.getenv('DB_PORT', '5432')}/"
            f"{os.getenv('DB_NAME', 'trafficflow')}",
        )

    logger.info(f"[db] Connecting to database...")
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )
    logger.info("[db] Database pool created successfully.")

    return _pool


async def close_db_pool():
    """Close database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("[db] Database pool closed.")


async def get_pool() -> asyncpg.Pool:
    """Get existing pool or create new one."""
    global _pool
    if _pool is None:
        await init_db_pool()
    return _pool


@asynccontextmanager
async def get_connection():
    """Context manager for database connection."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def init_schema():
    """Initialize database schema."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Check if table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_tables 
                WHERE schemaname = 'public' 
                AND tablename = 'prediction_history'
            )
        """
        )

        if not table_exists:
            try:
                await conn.execute(
                    """
                    CREATE TABLE prediction_history (
                        id BIGSERIAL,
                        camera_id TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        total_count INTEGER NOT NULL,
                        car_count INTEGER NOT NULL,
                        motorbike_count INTEGER NOT NULL,
                        density_level VARCHAR(20) NOT NULL,
                        confidence FLOAT,
                        PRIMARY KEY (camera_id, timestamp)
                    )
                    """
                )
                logger.info("[db] Created prediction_history table.")
                table_exists = True
            except Exception as e:
                logger.error(f"[db] Failed to create prediction_history table: {e}")
                raise

        if table_exists:
            # Check if it already has composite PK with timestamp
            has_pk = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conrelid = 'prediction_history'::regclass
                    AND contype = 'p'
                    AND conkey = '{2}'  -- timestamp is column 2
                )
            """
            )

            if not has_pk:
                # Drop existing primary key and recreate with composite
                try:
                    await conn.execute(
                        """
                        ALTER TABLE prediction_history 
                        DROP CONSTRAINT IF EXISTS prediction_history_pkey,
                        ADD PRIMARY KEY (camera_id, timestamp)
                    """
                    )
                    logger.info(
                        "[db] Recreated primary key as composite (camera_id, timestamp)"
                    )
                except Exception as e:
                    logger.warning(f"[db] Could not modify PK: {e}")

        # Try to convert to hypertable (TimescaleDB)
        try:
            result = await conn.fetchval(
                """
                SELECT create_hypertable('prediction_history', 'timestamp', 
                    if_not_exists => TRUE, 
                    migrate_data => TRUE,
                    force_partitioning => TRUE)
            """
            )
            if result:
                logger.info("[db] TimescaleDB hypertable created.")
            else:
                logger.info("[db] TimescaleDB hypertable already exists.")
        except Exception as e:
            logger.warning(f"[db] TimescaleDB not available: {e}")
            logger.info("[db] Using regular PostgreSQL table.")

        # Create camera_rois table
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_rois (
                    camera_id TEXT PRIMARY KEY,
                    roi_polygon JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            logger.info("[db] camera_rois table initialized.")
        except Exception as e:
            logger.error(f"[db] Failed to initialize camera_rois table: {e}")

        logger.info("[db] Schema initialized successfully.")


async def record_prediction(
    camera_id: str,
    timestamp,
    total_count: int,
    car_count: int,
    motorbike_count: int,
    density_level: str,
):
    """Record a prediction to the database."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO prediction_history 
                (camera_id, timestamp, total_count, car_count, motorbike_count, density_level)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (camera_id, timestamp) DO UPDATE SET
                total_count = EXCLUDED.total_count,
                car_count = EXCLUDED.car_count,
                motorbike_count = EXCLUDED.motorbike_count,
                density_level = EXCLUDED.density_level
            """,
            camera_id,
            timestamp,
            total_count,
            car_count,
            motorbike_count,
            density_level,
        )


async def get_camera_history(
    camera_id: str,
    minutes: int = 30,
) -> list[dict]:
    """Get prediction history for a camera."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT timestamp, total_count, car_count, motorbike_count, density_level
            FROM prediction_history
            WHERE camera_id = $1
              AND timestamp > NOW() - INTERVAL '1 minute' * $2
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            camera_id,
            minutes,
        )

        return [dict(row) for row in rows]


async def get_camera_roi(camera_id: str) -> list[list[float]] | None:
    """Get the saved ROI polygon for a camera."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT roi_polygon FROM camera_rois WHERE camera_id = $1",
            camera_id
        )
        if val is not None:
            if isinstance(val, str):
                return json.loads(val)
            return val
        return None


async def save_camera_roi(camera_id: str, roi_polygon: list[list[float]]) -> None:
    """Save the ROI polygon for a camera."""
    import json
    pool = await get_pool()
    val = json.dumps(roi_polygon)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO camera_rois (camera_id, roi_polygon, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (camera_id) DO UPDATE SET
                roi_polygon = EXCLUDED.roi_polygon,
                updated_at = NOW()
            """,
            camera_id,
            val
        )


async def delete_camera_roi(camera_id: str) -> None:
    """Delete the ROI polygon for a camera."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM camera_rois WHERE camera_id = $1",
            camera_id
        )


async def get_all_camera_rois() -> dict[str, list[list[float]]]:
    """Get ROI polygons for all cameras."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT camera_id, roi_polygon FROM camera_rois")
        res = {}
        for r in rows:
            val = r["roi_polygon"]
            if isinstance(val, str):
                res[r["camera_id"]] = json.loads(val)
            else:
                res[r["camera_id"]] = val
        return res
