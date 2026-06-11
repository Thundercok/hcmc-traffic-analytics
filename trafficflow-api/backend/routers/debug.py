import asyncio
import logging
import time
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException

from ..cameras import get_camera_by_id, CAMERAS
from ..model_service import ZIPModelService

logger = logging.getLogger("trafficflow.routers.debug")
router = APIRouter()

# Global variables for caching debug statistics
_debug_cached_data = None
_background_task = None
_running = False


async def compute_debug_dashboard_data() -> dict:
    """Run all 14+ database queries to build the complete debug stats payload."""
    from ..database import get_pool

    result = {
        "timestamp": datetime.now().isoformat(),
        "health": {},
        "database": {},
        "cameras": {},
        "writer": {},
        "analytics": {},
    }

    # 1. Health check
    try:
        svc = ZIPModelService.get_instance()
        loaded = svc.is_loaded
        info = svc.model_info
        result["health"] = {
            "status": "healthy" if loaded else "loading",
            "model_loaded": loaded,
            "device": str(svc.device) if loaded else None,
            "model": info,
        }
    except Exception as e:
        result["health"] = {"status": "unhealthy", "error": str(e)}

    # 2. Database check
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            total_records = await conn.fetchval(
                "SELECT COUNT(*) FROM prediction_history"
            )
            latest = await conn.fetchval(
                "SELECT MAX(timestamp) FROM prediction_history"
            )
            oldest = await conn.fetchval(
                "SELECT MIN(timestamp) FROM prediction_history"
            )
            by_level = await conn.fetch(
                "SELECT density_level, COUNT(*) FROM prediction_history GROUP BY density_level"
            )
            by_camera = await conn.fetch(
                """
                SELECT camera_id, COUNT(*) as count,
                       ROUND(AVG(total_count)::numeric, 1) as avg_count,
                       ROUND(AVG(car_count)::numeric, 1) as avg_car,
                       ROUND(AVG(motorbike_count)::numeric, 1) as avg_motorbike,
                       MAX(total_count) as max_count,
                       MIN(total_count) as min_count,
                       ROUND(STDDEV(total_count)::numeric, 1) as std_count
                FROM prediction_history
                GROUP BY camera_id
                ORDER BY count DESC
                LIMIT 20
                """
            )
            # Hourly distribution
            hourly = await conn.fetch(
                """
                SELECT EXTRACT(HOUR FROM timestamp) as hour,
                       COUNT(*) as count,
                       ROUND(AVG(total_count)::numeric, 1) as avg_count
                FROM prediction_history
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY EXTRACT(HOUR FROM timestamp)
                ORDER BY hour
                """
            )
            # Daily distribution
            daily = await conn.fetch(
                """
                SELECT DATE(timestamp) as day,
                       COUNT(*) as count,
                       ROUND(AVG(total_count)::numeric, 1) as avg_count
                FROM prediction_history
                WHERE timestamp > NOW() - INTERVAL '30 days'
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
                LIMIT 30
                """
            )
            # Top 10 worst congestion (highest avg count)
            worst = await conn.fetch(
                """
                SELECT camera_id, COUNT(*) as count,
                       ROUND(AVG(total_count)::numeric, 1) as avg_count,
                       ROUND(AVG(CASE WHEN density_level = 'heavy' THEN 1 ELSE 0 END) * 100, 1) as heavy_pct
                FROM prediction_history
                GROUP BY camera_id
                ORDER BY avg_count DESC
                LIMIT 10
                """
            )
            # Overall stats
            overall = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total,
                    ROUND(AVG(total_count)::numeric, 1) as avg_total,
                    ROUND(AVG(car_count)::numeric, 1) as avg_car,
                    ROUND(AVG(motorbike_count)::numeric, 1) as avg_motorbike,
                    ROUND(STDDEV(total_count)::numeric, 1) as std_total,
                    MAX(total_count) as max_total,
                    MIN(total_count) as min_total,
                    ROUND(AVG(CASE WHEN density_level = 'heavy' THEN 1 ELSE 0 END) * 100, 1) as heavy_pct,
                    ROUND(AVG(CASE WHEN density_level = 'moderate' THEN 1 ELSE 0 END) * 100, 1) as moderate_pct,
                    ROUND(AVG(CASE WHEN density_level = 'low' THEN 1 ELSE 0 END) * 100, 1) as low_pct
                FROM prediction_history
                """
            )
            db_uptime = await conn.fetchval("SELECT NOW() - pg_postmaster_start_time()")
            db_size = await conn.fetchval(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            )
            db_version = await conn.fetchval("SHOW server_version")

            # Get 10 most recent individual records
            recent_records = await conn.fetch(
                """
                SELECT
                    id,
                    camera_id,
                    total_count,
                    car_count,
                    motorbike_count,
                    density_level,
                    timestamp
                FROM prediction_history
                ORDER BY timestamp DESC
                LIMIT 10
                """
            )

            # Query ALL records once for the last hour
            all_hourly_records = await conn.fetch(
                """
                SELECT
                    CAST(id AS TEXT) as id,
                    CAST(camera_id AS TEXT) as camera_id,
                    total_count,
                    car_count,
                    motorbike_count,
                    density_level,
                    timestamp
                FROM prediction_history
                WHERE timestamp > NOW() - INTERVAL '1 hour'
                ORDER BY camera_id, timestamp DESC
                """
            )

            # Build hourly_per_camera by grouping in Python
            from collections import defaultdict
            camera_groups = defaultdict(list)
            for r in all_hourly_records:
                camera_groups[r["camera_id"]].append(r)

            hourly_per_camera = []
            for cam_id, records in camera_groups.items():
                counts = [r["total_count"] for r in records]
                cars = [r["car_count"] for r in records]
                motorbikes = [r["motorbike_count"] for r in records]
                levels = [r["density_level"] for r in records]

                import statistics
                avg_count = round(statistics.mean(counts), 1) if counts else 0
                avg_car = round(statistics.mean(cars), 1) if cars else 0
                avg_motorbike = (
                    round(statistics.mean(motorbikes), 1) if motorbikes else 0
                )
                std_count = round(statistics.stdev(counts), 1) if len(counts) > 1 else 0

                heavy_count = sum(1 for l in levels if l == "heavy")
                moderate_count = sum(1 for l in levels if l == "moderate")
                low_count = sum(1 for l in levels if l == "low")
                total = len(levels) or 1

                hourly_per_camera.append(
                    {
                        "camera_id": cam_id,
                        "record_count": len(records),
                        "avg_count": avg_count,
                        "avg_car": avg_car,
                        "avg_motorbike": avg_motorbike,
                        "max_count": max(counts) if counts else 0,
                        "min_count": min(counts) if counts else 0,
                        "std_count": std_count,
                        "heavy_pct": round(heavy_count / total * 100, 1),
                        "moderate_pct": round(moderate_count / total * 100, 1),
                        "low_pct": round(low_count / total * 100, 1),
                        "last_record": (
                            records[0]["timestamp"].isoformat() if records else None
                        ),
                    }
                )

            # Sort by record_count desc
            hourly_per_camera.sort(key=lambda x: x["record_count"], reverse=True)

            all_records = [
                {
                    "id": str(r["id"]),
                    "camera_id": r["camera_id"],
                    "total_count": r["total_count"] or 0,
                    "car_count": r["car_count"] or 0,
                    "motorbike_count": r["motorbike_count"] or 0,
                    "density_level": r["density_level"] or "unknown",
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                }
                for r in all_hourly_records
            ]

        result["database"] = {
            "status": "connected",
            "total_records": total_records,
            "latest_prediction": latest.isoformat() if latest else None,
            "oldest_prediction": oldest.isoformat() if oldest else None,
            "uptime": str(db_uptime),
            "db_version": db_version,
            "db_size": db_size,
            "by_density": {r["density_level"]: r["count"] for r in by_level},
            "top_cameras": [
                {
                    "camera_id": r["camera_id"],
                    "count": r["count"],
                    "avg_count": float(r["avg_count"]) if r["avg_count"] else 0,
                    "avg_car": float(r["avg_car"]) if r["avg_car"] else 0,
                    "avg_motorbike": (
                        float(r["avg_motorbike"]) if r["avg_motorbike"] else 0
                    ),
                    "max_count": r["max_count"],
                    "min_count": r["min_count"],
                    "std_count": float(r["std_count"]) if r["std_count"] else 0,
                }
                for r in by_camera
            ],
            "hourly_distribution": [
                {
                    "hour": int(r["hour"]),
                    "count": r["count"],
                    "avg_count": float(r["avg_count"]) if r["avg_count"] else 0,
                }
                for r in hourly
            ],
            "daily_distribution": [
                {
                    "day": str(r["day"]),
                    "count": r["count"],
                    "avg_count": float(r["avg_count"]) if r["avg_count"] else 0,
                }
                for r in daily
            ],
            "worst_congestion": [
                {
                    "camera_id": r["camera_id"],
                    "count": r["count"],
                    "avg_count": float(r["avg_count"]) if r["avg_count"] else 0,
                    "heavy_pct": float(r["heavy_pct"]) if r["heavy_pct"] else 0,
                }
                for r in worst
            ],
            "overall_stats": {
                "total_records": overall["total"],
                "avg_total": float(overall["avg_total"]) if overall["avg_total"] else 0,
                "avg_car": float(overall["avg_car"]) if overall["avg_car"] else 0,
                "avg_motorbike": float(overall["avg_motorbike"]) if overall["avg_motorbike"] else 0,
                "std_total": float(overall["std_total"]) if overall["std_total"] else 0,
                "max_total": overall["max_total"],
                "min_total": overall["min_total"],
                "heavy_pct": float(overall["heavy_pct"]) if overall["heavy_pct"] else 0,
                "moderate_pct": float(overall["moderate_pct"]) if overall["moderate_pct"] else 0,
                "low_pct": float(overall["low_pct"]) if overall["low_pct"] else 0,
            },
            "recent_records": [
                {
                    "id": str(r["id"]),
                    "camera_id": r["camera_id"],
                    "total_count": r["total_count"],
                    "car_count": r["car_count"],
                    "motorbike_count": r["motorbike_count"],
                    "density_level": r["density_level"],
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                }
                for r in recent_records
            ],
            "hourly_per_camera": hourly_per_camera,
            "all_records": all_records,
        }
    except Exception as e:
        logger.error(f"[compute_debug_dashboard_data] DB analytics failed: {e}", exc_info=True)
        result["database"] = {"status": "error", "error": str(e)}

    # 3. Camera stats
    try:
        from ..database import get_all_camera_rois
        rois = await get_all_camera_rois()
        result["cameras"] = {
            "total_cameras": len(CAMERAS),
            "mapped_cameras": len(rois),
            "unmapped_cameras": len(CAMERAS) - len(rois),
            "mapping_ratio": len(rois) / max(len(CAMERAS), 1),
        }
    except Exception as e:
        logger.warning(f"[compute_debug_dashboard_data] camera check error: {e}")
        result["cameras"] = {"error": str(e)}

    # 4. Writer check
    try:
        result["writer"] = {"status": "not_active"}
    except Exception as e:
        logger.warning(f"[compute_debug_dashboard_data] writer check error: {e}")
        result["writer"] = {"error": str(e)}

    return result


async def update_debug_analytics_loop():
    """Background task loop to refresh the debug stats cache once every 2 minutes."""
    global _debug_cached_data, _running
    _running = True
    # Initial sleep to allow database to fully initialize on startup
    await asyncio.sleep(5)
    while _running:
        try:
            logger.info("[debug-scheduler] Running periodic background analytics update...")
            data = await compute_debug_dashboard_data()
            _debug_cached_data = data
            logger.info("[debug-scheduler] Background analytics updated successfully.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[debug-scheduler] Failed to update background analytics: {e}", exc_info=True)
        await asyncio.sleep(120)  # Update every 2 minutes


def start_debug_scheduler(app):
    """Start the background scheduler task."""
    global _background_task
    _background_task = asyncio.create_task(update_debug_analytics_loop())
    logger.info("[debug-scheduler] Background statistics task started.")


def stop_debug_scheduler():
    """Stop the background scheduler task."""
    global _running, _background_task
    _running = False
    if _background_task:
        _background_task.cancel()
        logger.info("[debug-scheduler] Background statistics task stopped.")


@router.get(
    "/debug",
    summary="Debug Dashboard",
    description="Quick overview of system health, cameras, and database status. Results are cached and updated asynchronously.",
)
async def debug_dashboard(request: Request):
    """[debug_dashboard] Returns cached debug dashboard statistics instantly."""
    global _debug_cached_data

    # Fallback to direct calculation if the cache hasn't been populated yet
    if _debug_cached_data is None:
        logger.info("[debug_dashboard] Cache is empty, generating inline...")
        _debug_cached_data = await compute_debug_dashboard_data()

    # Dynamic status update for prediction writer
    if hasattr(request.app.state, "writer"):
        from ..prediction_writer import _writer
        if _writer and _writer.running:
            _debug_cached_data["writer"] = {
                "status": "running",
                "interval_seconds": _writer.interval,
                "total_records": _writer._total_records,
                "batches_processed": _writer._batches_count,
            }
        else:
            _debug_cached_data["writer"] = {"status": "inactive"}
    else:
        _debug_cached_data["writer"] = {"status": "not_initialized"}

    # Dynamic status update for http client
    if hasattr(request.app.state, "http_client"):
        client = request.app.state.http_client
        _debug_cached_data["health"]["http_client"] = {
            "is_closed": client.is_closed
        }

    # Add active/stale camera counts dynamically from congestion monitor
    try:
        svc = ZIPModelService.get_instance()
        if svc._congestion_detector:
            stats = svc.congestion_detector.stats
            _debug_cached_data["analytics"]["congestion_monitor"] = stats
    except Exception as e:
        logger.warning(f"[debug_dashboard] Failed to read congestion monitor stats: {e}")

    _debug_cached_data["timestamp"] = datetime.now().isoformat()
    return _debug_cached_data


@router.get(
    "/debug/camera/{camera_id}/records",
    summary="Get camera records",
    description="Get all records for a specific camera in the last hour.",
)
async def get_camera_debug_records(camera_id: str, limit: int = 50):
    """Get detailed records for a specific camera in the last hour."""
    from ..database import get_pool

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            records = await conn.fetch(
                """
                SELECT
                    id,
                    camera_id,
                    total_count,
                    car_count,
                    motorbike_count,
                    density_level,
                    confidence,
                    timestamp
                FROM prediction_history
                WHERE camera_id = $1
                  AND timestamp > NOW() - INTERVAL '1 hour'
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                camera_id,
                limit,
            )

        return {
            "camera_id": camera_id,
            "record_count": len(records),
            "records": [
                {
                    "id": str(r["id"]),
                    "total_count": r["total_count"] or 0,
                    "car_count": r["car_count"] or 0,
                    "motorbike_count": r["motorbike_count"] or 0,
                    "density_level": r["density_level"] or "unknown",
                    "confidence": float(r["confidence"]) if r["confidence"] else None,
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                }
                for r in records
            ],
        }
    except Exception as e:
        logger.warning(f"[get_camera_records] error: {e}")
        return {
            "camera_id": camera_id,
            "record_count": 0,
            "records": [],
            "error": str(e),
        }


@router.get(
    "/debug/cameras/list",
    summary="List all camera IDs",
    description="Get all camera IDs from prediction_history table for debugging.",
)
async def list_camera_ids():
    """Get all unique camera IDs from database for debugging."""
    from ..database import get_pool

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            ids = await conn.fetch(
                """
                SELECT DISTINCT camera_id, COUNT(*) as count
                FROM prediction_history
                WHERE timestamp > NOW() - INTERVAL '1 hour'
                GROUP BY camera_id
                ORDER BY count DESC
                LIMIT 20
                """
            )

        return {
            "cameras": [
                {"camera_id": r["camera_id"], "count": r["count"]} for r in ids
            ],
        }
    except Exception as e:
        logger.warning(f"[list_camera_ids] error: {e}")
        return {"cameras": [], "error": str(e)}
