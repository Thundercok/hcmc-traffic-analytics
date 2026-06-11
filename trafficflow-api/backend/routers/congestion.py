import asyncio
import logging
from datetime import datetime
import httpx
import numpy as np
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool

from ..schemas import (
    CongestionResponse,
    CongestionMapResponse,
    CameraCongestionHistoryResponse,
    SystemCongestionStatsResponse,
    CongestionMetricsSchema,
)
from ..cameras import (
    CAMERAS,
    get_camera_by_id,
    get_camera_image_url,
)
from ..model_service import ZIPModelService
from ..utils import (
    CAMERA_FETCH_HEADERS,
    _cache_image,
    _get_cached_image,
)

logger = logging.getLogger("trafficflow.routers.congestion")
router = APIRouter()


@router.get(
    "/congestion/camera/{camera_id}",
    response_model=CongestionResponse,
    summary="Detect Traffic Congestion",
    description="Run rule-based congestion detection on a live camera feed. "
    "No model training required - uses motion detection and optical flow.",
)
async def detect_congestion(request: Request, camera_id: str):
    """
    [detect_congestion] Phát hiện mức kẹt xe từ camera.

    Sử dụng rule-based analysis:
    - Motion detection (thay đổi pixels)
    - Optical flow (tốc độ di chuyển)
    - Edge density (mật độ xe)

    Kết quả ổn định hơn sau 3-5 frames.
    """
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    svc = ZIPModelService.get_instance()

    # Fetch camera image
    image_url = get_camera_image_url(camera_id)
    try:
        client: httpx.AsyncClient = request.app.state.http_client
        response = await client.get(image_url, headers=CAMERA_FETCH_HEADERS)
        response.raise_for_status()
        image_bytes = response.content

        # Update fallback cache
        _cache_image(
            camera_id, image_bytes, response.headers.get("content-type", "image/jpeg")
        )

    except Exception as e:
        # Try fallback cache
        cached = _get_cached_image(camera_id)
        if cached:
            logger.warning(
                f"[detect_congestion] Fetch failed, using cache for {camera_id}"
            )
            image_bytes = cached["content"]
        else:
            if isinstance(e, httpx.TimeoutException):
                raise HTTPException(
                    status_code=504, detail=f"Timeout fetching camera: {camera_id}"
                )
            elif isinstance(e, httpx.HTTPStatusError):
                raise HTTPException(
                    status_code=502, detail=f"Camera error: {e.response.status_code}"
                )
            else:
                raise HTTPException(
                    status_code=502, detail=f"Failed to fetch camera: {str(e)}"
                )

    # Run congestion detection
    try:
        result = await run_in_threadpool(svc.detect_congestion, camera_id, image_bytes)

        return CongestionResponse(
            camera_id=camera_id,
            camera_name=camera.get("name"),
            timestamp=datetime.now(),
            level=result["level"],
            level_name=result["level_name"],
            color=result["color"],
            emoji=result["emoji"],
            description=result["description"],
            confidence=result["confidence"],
            is_stable=result["is_stable"],
            is_error=result["is_error"],
            error_message=result.get("error_message"),
            metrics=CongestionMetricsSchema(**result["metrics"]),
        )

    except Exception as e:
        logger.error(f"[detect_congestion] Detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Congestion detection error: {str(e)}"
        )


@router.get(
    "/congestion/map",
    response_model=CongestionMapResponse,
    summary="Get Congestion Map",
    description="Get current congestion status for all monitored cameras.",
)
async def get_congestion_map(request: Request):
    """
    [get_congestion_map] Lấy bản đồ kẹt xe tổng hợp.

    - Fetch tất cả cameras
    - Run congestion detection
    - Return summary statistics
    """
    svc = ZIPModelService.get_instance()
    client: httpx.AsyncClient = request.app.state.http_client

    # Lấy tất cả cameras
    cameras = CAMERAS[:15]  # Limit to 15 for performance

    sem = asyncio.Semaphore(5)
    results = []

    async def _process_camera(cam: dict) -> dict | None:
        """Process single camera."""
        try:
            async with sem:
                try:
                    url = get_camera_image_url(cam["id"])
                    resp = await client.get(url, headers=CAMERA_FETCH_HEADERS)
                    resp.raise_for_status()
                    image_bytes = resp.content

                    _cache_image(
                        cam["id"],
                        image_bytes,
                        resp.headers.get("content-type", "image/jpeg"),
                    )

                    result = await run_in_threadpool(
                        svc.detect_congestion, cam["id"], image_bytes
                    )

                    return {
                        "camera_id": cam["id"],
                        "level": result["level"],
                        "level_name": result["level_name"],
                        "color": result["color"],
                        "emoji": result["emoji"],
                        "district": cam.get("district"),
                        "lat": cam.get("lat"),
                        "lng": cam.get("lng"),
                        "is_stable": result["is_stable"],
                    }

                except Exception as e:
                    logger.warning(f"[congestion_map] Failed for {cam['id']}: {e}")
                    # Return stale data if available
                    cached = _get_cached_image(cam["id"])
                    if cached:
                        try:
                            result = await run_in_threadpool(
                                svc.detect_congestion, cam["id"], cached["content"]
                            )
                            return {
                                "camera_id": cam["id"],
                                "level": result["level"],
                                "level_name": result["level_name"] + " (cached)",
                                "color": result["color"],
                                "emoji": "⏸️",
                                "district": cam.get("district"),
                                "lat": cam.get("lat"),
                                "lng": cam.get("lng"),
                                "is_stable": False,
                                "is_cached": True,
                            }
                        except Exception as inner_e:
                            logger.error(f"[congestion_map] Cached detect failed for {cam['id']}: {inner_e}", exc_info=True)
                            return None
                    return None
        except Exception as e:
            logger.error(f"[congestion_map] Critical failure for camera {cam.get('id')}: {e}", exc_info=True)
            return None

    # Process all cameras concurrently
    tasks = [_process_camera(cam) for cam in cameras]
    results = await asyncio.gather(*tasks)

    # Filter successful results
    successful = [r for r in results if r is not None]
    failed = len(results) - len(successful)

    # Build camera dict
    camera_map = {}
    level_counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for r in successful:
        camera_map[r["camera_id"]] = {
            "level": r["level"],
            "level_name": r["level_name"],
            "color": r["color"],
            "emoji": r["emoji"],
            "district": r.get("district"),
            "lat": r.get("lat"),
            "lng": r.get("lng"),
            "is_stable": r.get("is_stable", True),
        }
        level_counts[r["level"]] = level_counts.get(r["level"], 0) + 1

    # Summary
    levels = [r["level"] for r in successful]
    avg_level = np.mean(levels) if levels else 0

    if avg_level < 0.5:
        overall_status = "Thông thoáng trên toàn thành phố"
    elif avg_level < 1.5:
        overall_status = "Một số nơi đông vừa"
    elif avg_level < 2.5:
        overall_status = "Kẹt xe nhiều nơi"
    else:
        overall_status = "Kẹt cứng diện rộng"

    summary = {
        "total": len(successful),
        "free": level_counts.get(0, 0),
        "moderate": level_counts.get(1, 0),
        "heavy": level_counts.get(2, 0),
        "severe": level_counts.get(3, 0),
        "failed": failed,
        "average_level": round(float(avg_level), 2),
        "overall_status": overall_status,
    }

    return CongestionMapResponse(
        updated_at=datetime.now(),
        total_cameras=len(successful),
        stale_cameras=failed,
        cameras=camera_map,
        summary=summary,
    )


@router.get(
    "/congestion/camera/{camera_id}/history",
    response_model=CameraCongestionHistoryResponse,
    summary="Get Camera Congestion History",
    description="Get congestion history and trend for a specific camera.",
)
async def get_camera_congestion_history(camera_id: str):
    """
    [get_camera_congestion_history] Lấy lịch sử kẹt xe của một camera.
    """
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    svc = ZIPModelService.get_instance()
    monitor = svc.congestion_detector

    # Get detector stats
    status = monitor.get_camera_status(camera_id)
    detector = monitor._detectors.get(camera_id)

    # Get history from buffer
    history = []
    trend = "stable"

    if detector and len(detector._frame_buffer) >= 3:
        levels = []
        for m in detector._frame_buffer:
            level, _ = detector._compute_congestion_level(m)
            levels.append(level)
            history.append(
                {
                    "timestamp": m.timestamp.isoformat(),
                    "level": level,
                    "metrics": {
                        "motion_ratio": m.motion_ratio,
                        "flow_speed": m.flow_speed,
                        "edge_density": m.edge_density,
                    },
                }
            )

        # Calculate trend
        first_half = np.mean(levels[: len(levels) // 2])
        second_half = np.mean(levels[len(levels) // 2 :])
        diff = second_half - first_half

        if diff > 0.3:
            trend = "worsening"
        elif diff < -0.3:
            trend = "improving"
        else:
            trend = "stable"

    current_level = status.get("buffer_size", 0) > 0

    return CameraCongestionHistoryResponse(
        camera_id=camera_id,
        camera_name=camera.get("name"),
        current_level=status.get("buffer_size", 0),
        current_level_name="Có dữ liệu" if current_level else "Chưa có dữ liệu",
        current_color="#22c55e" if current_level else "#9ca3af",
        trend=trend,
        history=history,
        stats=status,
    )


@router.get(
    "/congestion/stats",
    response_model=SystemCongestionStatsResponse,
    summary="Get System Congestion Statistics",
    description="Get overall statistics for the congestion detection system.",
)
async def get_congestion_stats():
    """
    [get_congestion_stats] Lấy thống kê hệ thống.
    """
    svc = ZIPModelService.get_instance()
    monitor = svc.congestion_detector

    stats = monitor.stats

    # Per-detector stats
    detectors = []
    for cam_id, detector in monitor._detectors.items():
        detectors.append(
            {
                "camera_id": cam_id,
                "processed": detector.total_processed,
                "errors": detector.total_errors,
                "buffer_size": len(detector._frame_buffer),
                "is_stale": monitor._is_camera_stale(cam_id),
            }
        )

    return SystemCongestionStatsResponse(
        total_cameras_tracked=stats["total_cameras_tracked"],
        total_frames_processed=stats["total_frames_processed"],
        total_errors=stats["total_errors"],
        stale_cameras=stats["stale_cameras"],
        detectors=detectors,
    )


@router.post(
    "/congestion/reset/{camera_id}",
    summary="Reset Camera Congestion Buffer",
    description="Reset the congestion analysis buffer for a specific camera.",
)
async def reset_camera_congestion(camera_id: str):
    """
    [reset_camera_congestion] Reset buffer cho một camera.

    Dùng khi camera bị offline và reconnect, để bắt đầu phân tích lại từ đầu.
    """
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    svc = ZIPModelService.get_instance()
    monitor = svc.congestion_detector

    detector = monitor._detectors.get(camera_id)
    if detector:
        detector.reset()
        logger.info(f"[reset_congestion] Reset buffer for camera: {camera_id}")
        return {
            "status": "success",
            "message": f"Buffer reset for camera {camera_id}",
            "camera_id": camera_id,
        }
    else:
        return {
            "status": "skipped",
            "message": f"No buffer found for camera {camera_id}",
            "camera_id": camera_id,
        }
