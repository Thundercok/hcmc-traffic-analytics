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
            # Check if it already has composite PK with camera_id + timestamp.
            pk_columns = await conn.fetch(
                """
                SELECT a.attname
                FROM pg_constraint c
                JOIN unnest(c.conkey) WITH ORDINALITY AS cols(attnum, ord)
                    ON TRUE
                JOIN pg_attribute a
                    ON a.attrelid = c.conrelid
                   AND a.attnum = cols.attnum
                WHERE c.conrelid = 'prediction_history'::regclass
                  AND c.contype = 'p'
                ORDER BY cols.ord
            """
            )
            has_pk = [r["attname"] for r in pk_columns] == ["camera_id", "timestamp"]

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

            try:
                await conn.execute(
                    "ALTER TABLE prediction_history ADD COLUMN IF NOT EXISTS confidence FLOAT"
                )
                await conn.execute(
                    """
                    ALTER TABLE prediction_history
                    ADD COLUMN IF NOT EXISTS data_source VARCHAR(32) NOT NULL DEFAULT 'live'
                    """
                )
                await conn.execute(
                    "ALTER TABLE prediction_history ADD COLUMN IF NOT EXISTS quality_score FLOAT"
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prediction_timestamp
                        ON prediction_history(timestamp DESC)
                    """
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prediction_camera_time
                        ON prediction_history(camera_id, timestamp DESC)
                    """
                )
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prediction_source_time
                        ON prediction_history(data_source, timestamp DESC)
                    """
                )
                logger.info("[db] prediction_history quality/source columns ready.")
            except Exception as e:
                logger.warning(f"[db] Could not update prediction_history columns: {e}")

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
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    is_auto BOOLEAN DEFAULT FALSE
                )
                """
            )
            await conn.execute("ALTER TABLE camera_rois ADD COLUMN IF NOT EXISTS is_auto BOOLEAN DEFAULT FALSE")
            logger.info("[db] camera_rois table initialized with is_auto column.")
        except Exception as e:
            logger.error(f"[db] Failed to initialize camera_rois table: {e}")

        # Create weather_reports table
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_reports (
                    id BIGSERIAL PRIMARY KEY,
                    lat FLOAT NOT NULL,
                    lng FLOAT NOT NULL,
                    weather_state VARCHAR(20) NOT NULL,
                    rain_intensity VARCHAR(20) DEFAULT 'none',
                    flood_depth_cm INTEGER DEFAULT 0,
                    reporter_name VARCHAR(100) DEFAULT 'Cộng đồng',
                    notes TEXT,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_reports_timestamp ON weather_reports (timestamp DESC)")
            logger.info("[db] weather_reports table initialized.")
        except Exception as e:
            logger.error(f"[db] Failed to initialize weather_reports table: {e}")

        logger.info("[db] Schema initialized successfully.")


async def record_prediction(
    camera_id: str,
    timestamp,
    total_count: int,
    car_count: int,
    motorbike_count: int,
    density_level: str,
    confidence: float | None = None,
    data_source: str = "live",
    quality_score: float | None = None,
):
    """Record a prediction to the database."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO prediction_history 
                (
                    camera_id,
                    timestamp,
                    total_count,
                    car_count,
                    motorbike_count,
                    density_level,
                    confidence,
                    data_source,
                    quality_score
                )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (camera_id, timestamp) DO UPDATE SET
                total_count = EXCLUDED.total_count,
                car_count = EXCLUDED.car_count,
                motorbike_count = EXCLUDED.motorbike_count,
                density_level = EXCLUDED.density_level,
                confidence = EXCLUDED.confidence,
                data_source = EXCLUDED.data_source,
                quality_score = EXCLUDED.quality_score
            """,
            camera_id,
            timestamp,
            total_count,
            car_count,
            motorbike_count,
            density_level,
            confidence,
            data_source[:32],
            quality_score,
        )


async def get_camera_history(
    camera_id: str,
    minutes: int = 30,
    limit: int = 500,
) -> list[dict]:
    """Get prediction history for a camera."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                timestamp,
                total_count,
                car_count,
                motorbike_count,
                density_level,
                confidence,
                data_source,
                quality_score
            FROM prediction_history
            WHERE camera_id = $1
              AND timestamp > NOW() - INTERVAL '1 minute' * $2
            ORDER BY timestamp DESC
            LIMIT $3
            """,
            camera_id,
            minutes,
            limit,
        )

        return [dict(row) for row in rows]


async def get_data_coverage(minutes: int = 24 * 60) -> dict:
    """Return high-level data coverage statistics for the given time window."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        overall = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_records,
                COUNT(DISTINCT camera_id) AS cameras_with_data,
                MIN(timestamp) AS oldest_record,
                MAX(timestamp) AS latest_record
            FROM prediction_history
            WHERE timestamp > NOW() - INTERVAL '1 minute' * $1
            """,
            minutes,
        )
        by_source = await conn.fetch(
            """
            SELECT data_source, COUNT(*) AS count
            FROM prediction_history
            WHERE timestamp > NOW() - INTERVAL '1 minute' * $1
            GROUP BY data_source
            ORDER BY count DESC
            """,
            minutes,
        )
        by_camera = await conn.fetch(
            """
            SELECT
                camera_id,
                COUNT(*) AS record_count,
                MAX(timestamp) AS latest_record
            FROM prediction_history
            WHERE timestamp > NOW() - INTERVAL '1 minute' * $1
            GROUP BY camera_id
            ORDER BY record_count DESC
            """,
            minutes,
        )

    return {
        "total_records": overall["total_records"] or 0,
        "cameras_with_data": overall["cameras_with_data"] or 0,
        "oldest_record": overall["oldest_record"],
        "latest_record": overall["latest_record"],
        "by_source": {r["data_source"] or "unknown": r["count"] for r in by_source},
        "by_camera": [dict(row) for row in by_camera],
    }


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


async def save_camera_roi(camera_id: str, roi_polygon: list[list[float]], is_auto: bool = False) -> None:
    """Save the ROI polygon for a camera."""
    import json
    pool = await get_pool()
    val = json.dumps(roi_polygon)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO camera_rois (camera_id, roi_polygon, updated_at, is_auto)
            VALUES ($1, $2, NOW(), $3)
            ON CONFLICT (camera_id) DO UPDATE SET
                roi_polygon = EXCLUDED.roi_polygon,
                updated_at = NOW(),
                is_auto = EXCLUDED.is_auto
            """,
            camera_id,
            val,
            is_auto
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


async def get_camera_roi_with_meta(camera_id: str) -> tuple[list[list[float]] | None, bool]:
    """Get the saved ROI polygon and its is_auto flag for a camera."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT roi_polygon, is_auto FROM camera_rois WHERE camera_id = $1",
            camera_id
        )
        if row is not None:
            val = row["roi_polygon"]
            is_auto = row["is_auto"] or False
            if isinstance(val, str):
                return json.loads(val), is_auto
            return val, is_auto
        return None, False


async def get_all_camera_rois_with_meta() -> dict[str, dict]:
    """Get ROI polygons and is_auto flags for all cameras."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT camera_id, roi_polygon, is_auto FROM camera_rois")
        res = {}
        for r in rows:
            val = r["roi_polygon"]
            is_auto = r["is_auto"] or False
            if isinstance(val, str):
                poly = json.loads(val)
            else:
                poly = val
            res[r["camera_id"]] = {"roi_polygon": poly, "is_auto": is_auto}
        return res


async def create_weather_report(
    lat: float,
    lng: float,
    weather_state: str,
    rain_intensity: str = "none",
    flood_depth_cm: int = 0,
    reporter_name: str = "Cộng đồng",
    notes: str = None
) -> dict:
    """Create a crowdsourced weather report."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO weather_reports 
                (lat, lng, weather_state, rain_intensity, flood_depth_cm, reporter_name, notes, timestamp)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            RETURNING id, lat, lng, weather_state, rain_intensity, flood_depth_cm, reporter_name, notes, timestamp
            """,
            lat,
            lng,
            weather_state,
            rain_intensity,
            flood_depth_cm,
            reporter_name,
            notes,
        )
        return dict(row)


async def get_active_weather_reports(hours_limit: int = 4) -> list[dict]:
    """Get active weather reports within the last N hours."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, lat, lng, weather_state, rain_intensity, flood_depth_cm, reporter_name, notes, timestamp
            FROM weather_reports
            WHERE timestamp > NOW() - INTERVAL '1 hour' * $1
            ORDER BY timestamp DESC
            """,
            hours_limit
        )
        return [dict(row) for row in rows]

