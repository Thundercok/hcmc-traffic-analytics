import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

import httpx
import numpy as np
from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Query, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .schemas import (
    CameraInfo,
    CameraListResponse,
    PredictResponse,
    PredictionResult,
    PredictionMeta,
    HealthResponse,
    ModelStatus,
    BatchPredictRequest,
    BatchPredictionItem,
    BatchPredictResponse,
    PredictionHistoryEntry,
    PredictionHistoryResponse,
    CongestionResponse,
    CongestionMapResponse,
    CameraCongestionHistoryResponse,
    SystemCongestionStatsResponse,
    CongestionMetricsSchema,
    ForecastResponse,
    CameraRoiRequest,
    CameraRoiResponse,
)
from .forecast_service import get_forecaster
from .cameras import (
    CAMERAS,
    get_camera_by_id,
    get_camera_image_url,
    get_cameras_by_district,
    get_all_districts,
)
from .model_service import ZIPModelService
from .prediction_cache import PredictionCache
from .config import settings

logger = logging.getLogger("trafficflow.router")

_IMAGE_FALLBACK_CACHE = {}
_IMAGE_CACHE_MAX_SIZE = 20  # Maximum number of cached images
_IMAGE_CACHE_TTL_SECONDS = 300  # 5 minutes TTL

# Debug dashboard cache to prevent unbounded DB queries
_DEBUG_CACHE_TTL_SECONDS = 30  # 30 seconds cache for debug endpoint
_debug_cache = {"data": None, "timestamp": 0}


def _cleanup_image_cache() -> None:
    """Remove expired entries from the image cache to prevent unbounded memory growth."""
    current_time = time.time()
    expired_keys = [
        k
        for k, v in _IMAGE_FALLBACK_CACHE.items()
        if current_time - v.get("timestamp", 0) > _IMAGE_CACHE_TTL_SECONDS
    ]
    for k in expired_keys:
        del _IMAGE_FALLBACK_CACHE[k]

    # Also enforce max size by removing oldest entries
    if len(_IMAGE_FALLBACK_CACHE) > _IMAGE_CACHE_MAX_SIZE:
        # Sort by timestamp and keep only the newest entries
        sorted_items = sorted(
            _IMAGE_FALLBACK_CACHE.items(),
            key=lambda x: x[1].get("timestamp", 0),
            reverse=True,
        )
        _IMAGE_FALLBACK_CACHE.clear()
        for k, v in sorted_items[:_IMAGE_CACHE_MAX_SIZE]:
            _IMAGE_FALLBACK_CACHE[k] = v


def _cache_image(camera_id: str, content: bytes, content_type: str) -> None:
    """Cache an image with TTL and size limits."""
    _cleanup_image_cache()
    _IMAGE_FALLBACK_CACHE[camera_id] = {
        "content": content,
        "content_type": content_type,
        "timestamp": time.time(),
    }


def _get_cached_image(camera_id: str) -> dict | None:
    """Get cached image if it exists and is not expired."""
    cached = _IMAGE_FALLBACK_CACHE.get(camera_id)
    if cached:
        if time.time() - cached.get("timestamp", 0) > _IMAGE_CACHE_TTL_SECONDS:
            del _IMAGE_FALLBACK_CACHE[camera_id]
            return None
    return cached


router = APIRouter(prefix="/api", tags=["TrafficFlow API"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns the application status and model loading state.",
)
async def health_check():
    """[health_check] Returns app health and model status."""
    svc = ZIPModelService.get_instance()
    model_info = svc.model_info

    return HealthResponse(
        app=settings.app_name,
        version=settings.app_version,
        model=ModelStatus(**model_info),
        timestamp=datetime.now(),
    )


@router.get(
    "/districts",
    summary="List Districts",
    description="Returns all available district names.",
)
async def list_districts():
    """[list_districts] Returns all unique district names."""
    return {"districts": get_all_districts(), "total": len(get_all_districts())}


@router.get(
    "/cameras",
    response_model=CameraListResponse,
    summary="List Traffic Cameras",
    description="Returns all available traffic cameras in HCMC. Optionally filter by district.",
)
async def list_cameras(
    district: Optional[str] = Query(
        None, description="Filter by district name, e.g. 'Quận 7'"
    ),
):
    """[list_cameras] Returns cameras, optionally filtered by district."""
    if district:
        filtered = get_cameras_by_district(district)
    else:
        filtered = CAMERAS
    camera_list = [CameraInfo(**cam) for cam in filtered]
    return CameraListResponse(cameras=camera_list, total=len(camera_list))


@router.get(
    "/cameras/{camera_id}/roi",
    response_model=CameraRoiResponse,
    summary="Get Camera ROI",
    description="Retrieve the saved ROI polygon coordinates for a camera."
)
async def get_camera_roi_endpoint(camera_id: str):
    """[get_camera_roi_endpoint] Retrieve the saved ROI polygon coordinates for a camera."""
    from .database import get_camera_roi
    
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")
        
    roi = await get_camera_roi(camera_id)
    return CameraRoiResponse(camera_id=camera_id, roi_polygon=roi)


@router.post(
    "/cameras/{camera_id}/roi",
    summary="Save Camera ROI",
    description="Save the ROI polygon coordinates for a camera."
)
async def save_camera_roi_endpoint(camera_id: str, payload: CameraRoiRequest):
    """[save_camera_roi_endpoint] Save the ROI polygon coordinates for a camera."""
    from .database import save_camera_roi
    
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")
        
    # Validate polygon
    if len(payload.roi_polygon) < 3:
        raise HTTPException(status_code=400, detail="ROI polygon must contain at least 3 points")
        
    for point in payload.roi_polygon:
        if len(point) != 2:
            raise HTTPException(status_code=400, detail="Each ROI coordinate must be [x, y]")
        x, y = point
        if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
            raise HTTPException(status_code=400, detail="ROI coordinates must be normalized from 0 to 1")
            
    await save_camera_roi(camera_id, payload.roi_polygon)
    return {"status": "success", "message": f"ROI saved for camera {camera_id}"}


@router.delete(
    "/cameras/{camera_id}/roi",
    summary="Delete Camera ROI",
    description="Delete the ROI polygon coordinates for a camera."
)
async def delete_camera_roi_endpoint(camera_id: str):
    """[delete_camera_roi_endpoint] Delete the ROI polygon coordinates for a camera."""
    from .database import delete_camera_roi
    
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")
        
    await delete_camera_roi(camera_id)
    return {"status": "success", "message": f"ROI deleted for camera {camera_id}"}


_MAGIC_JPEG = b"\xff\xd8"
_MAGIC_PNG = b"\x89PNG"


def _validate_image_bytes(data: bytes) -> None:
    """[_validate_image_bytes] Check magic bytes to verify real image content (V-03)."""
    if data[:2] == _MAGIC_JPEG or data[:4] == _MAGIC_PNG:
        return
    raise HTTPException(
        status_code=400, detail="Invalid image format (expected JPEG or PNG)"
    )


def _build_predict_response(
    result: dict, camera_id: str | None = None, camera_name: str | None = None
) -> PredictResponse:
    """[_build_predict_response] Build a standardized prediction response."""
    svc = ZIPModelService.get_instance()
    model_info = svc.model_info
    return PredictResponse(
        camera_id=camera_id,
        camera_name=camera_name,
        timestamp=datetime.now(),
        prediction=PredictionResult(**result),
        metadata=PredictionMeta(
            model=model_info.get("model_name", "ZIP"),
            device=model_info.get("device", "cpu"),
            input_size=model_info.get("input_size", 448),
        ),
    )


def _parse_roi_polygon(raw_polygon: str | None) -> list[list[float]] | None:
    """Parse a normalized ROI polygon: [[x, y], ...] with x/y in 0..1."""
    if not raw_polygon:
        return None

    try:
        polygon = json.loads(raw_polygon)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid roi_polygon JSON") from exc

    if not isinstance(polygon, list) or len(polygon) < 3:
        raise HTTPException(
            status_code=400, detail="roi_polygon must contain at least 3 points"
        )

    parsed = []
    for point in polygon:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise HTTPException(
                status_code=400, detail="Each roi_polygon point must be [x, y]"
            )
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="roi_polygon coordinates must be numbers"
            ) from exc
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            raise HTTPException(
                status_code=400,
                detail="roi_polygon coordinates must be normalized from 0 to 1",
            )
        parsed.append([x, y])

    return parsed


@router.post(
    "/predict",
    response_model=PredictResponse,
    summary="Predict from Uploaded Image",
    description="Upload a traffic camera image and get the predicted vehicle/person count.",
)
async def predict_from_upload(
    file: UploadFile = File(..., description="Traffic camera image (JPEG/PNG)"),
    heatmap: bool = False,
    roi_polygon: Optional[str] = Form(
        None, description="JSON string of normalized ROI polygon coordinates"
    ),
):
    """[predict_from_upload] Run ZIP model inference on an uploaded image."""
    svc = ZIPModelService.get_instance()
    if not svc.is_loaded:
        raise HTTPException(status_code=503, detail="Model is not loaded yet.")

    image_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.max_upload_bytes // 1024 // 1024}MB)",
        )

    _validate_image_bytes(image_bytes)

    roi_coords = _parse_roi_polygon(roi_polygon)

    try:
        result = await run_in_threadpool(
            svc.predict_from_bytes,
            image_bytes,
            return_heatmap=heatmap,
            roi_polygon=roi_coords,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[predict_from_upload] Inference failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal prediction error")

    return _build_predict_response(result)


@router.get(
    "/predict/camera/{camera_id}",
    response_model=PredictResponse,
    summary="Predict from Live Camera",
    description="Fetch the live image from a traffic camera by ID and run prediction.",
)
async def predict_from_camera(request: Request, camera_id: str, heatmap: bool = False):
    """[predict_from_camera] Fetch live camera image → run ZIP inference → return count."""
    svc = ZIPModelService.get_instance()
    if not svc.is_loaded:
        raise HTTPException(status_code=503, detail="Model is not loaded yet.")

    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    image_url = get_camera_image_url(camera_id)
    try:
        client: httpx.AsyncClient = request.app.state.http_client
        response = await client.get(image_url, headers=CAMERA_FETCH_HEADERS)
        response.raise_for_status()
        image_bytes = response.content

        _cache_image(
            camera_id, image_bytes, response.headers.get("content-type", "image/jpeg")
        )
    except Exception as e:
        cached = _get_cached_image(camera_id)
        if cached:
            logger.warning(
                f"[predict_from_camera] Fetch failed ({e}), using cached image for {camera_id}."
            )
            image_bytes = cached["content"]
        else:
            if isinstance(e, httpx.TimeoutException):
                raise HTTPException(
                    status_code=504,
                    detail=f"Timeout fetching camera image: {camera_id}",
                )
            elif isinstance(e, httpx.HTTPStatusError):
                raise HTTPException(
                    status_code=502,
                    detail=f"Camera endpoint error: {e.response.status_code}",
                )
            else:
                logger.error(
                    f"[predict_from_camera] Failed to fetch image: {e}", exc_info=True
                )
                raise HTTPException(
                    status_code=502, detail="Failed to fetch camera image"
                )

    try:
        result = await run_in_threadpool(svc.predict_from_bytes, image_bytes, heatmap)
    except Exception as e:
        logger.error(f"[predict_from_camera] Inference failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal prediction error")

    return _build_predict_response(
        result, camera_id=camera_id, camera_name=camera.get("name")
    )


_BATCH_MAX_CAMERAS = 15
_BATCH_FETCH_SEMAPHORE = 5


@router.post(
    "/predict/batch",
    response_model=BatchPredictResponse,
    summary="Batch Predict Multiple Cameras",
    description="Predict traffic density for multiple cameras at once. "
    "Provide camera_ids or a district name. Max 30 cameras per request.",
)
async def batch_predict(request: Request, body: BatchPredictRequest):
    """[batch_predict] Fetch images and run inference for multiple cameras concurrently."""
    svc = ZIPModelService.get_instance()
    if not svc.is_loaded:
        raise HTTPException(status_code=503, detail="Model is not loaded yet.")

    if body.camera_ids:
        cameras = [get_camera_by_id(cid) for cid in body.camera_ids]
        cameras = [c for c in cameras if c is not None]
    elif body.district:
        cameras = get_cameras_by_district(body.district)
    else:
        raise HTTPException(status_code=400, detail="Provide camera_ids or district")

    if not cameras:
        raise HTTPException(status_code=404, detail="No cameras found")

    cameras = cameras[:_BATCH_MAX_CAMERAS]
    client: httpx.AsyncClient = request.app.state.http_client
    cache = PredictionCache.get_instance()
    sem = asyncio.Semaphore(_BATCH_FETCH_SEMAPHORE)

    async def _predict_one(cam: dict) -> dict:
        """Fetch image + run inference for a single camera."""
        latest = cache.get_latest(cam["id"])
        if latest:
            try:
                last_time = datetime.fromisoformat(latest["timestamp"])
                if (datetime.now() - last_time).total_seconds() < 120:
                    logger.info(
                        f"[batch_predict] CACHE HIT for {cam['id']} ({latest.get('density_level', 'low')})"
                    )
                    return {"cam": cam, "result": latest, "ok": True}
            except Exception:
                pass

        try:
            async with sem:
                url = get_camera_image_url(cam["id"])
                resp = await client.get(url, headers=CAMERA_FETCH_HEADERS)
                resp.raise_for_status()
                image_bytes = resp.content

                _cache_image(
                    cam["id"],
                    image_bytes,
                    resp.headers.get("content-type", "image/jpeg"),
                )

            result = await run_in_threadpool(svc.predict_from_bytes, image_bytes)
            cache.record(cam["id"], result)
            return {"cam": cam, "result": result, "ok": True}
        except Exception as e:
            cached = _get_cached_image(cam["id"])
            if cached:
                logger.warning(
                    f"[batch_predict] Fetch failed ({e}), using cached image for {cam['id']}."
                )
                image_bytes = cached["content"]
                result = await run_in_threadpool(svc.predict_from_bytes, image_bytes)
                cache.record(cam["id"], result)
                return {"cam": cam, "result": result, "ok": True}
            else:
                logger.warning(f"[batch_predict] Failed for {cam['id']}: {e}")
                return {"cam": cam, "result": None, "ok": False}

    start_time = time.time()
    tasks = [_predict_one(cam) for cam in cameras]
    results = await asyncio.gather(*tasks)
    total_time_ms = round((time.time() - start_time) * 1000, 1)

    predictions = []
    failed = 0
    for r in results:
        if r["ok"]:
            cam = r["cam"]
            predictions.append(
                BatchPredictionItem(
                    camera_id=cam["id"],
                    camera_name=cam["name"],
                    district=cam["district"],
                    lat=cam["lat"],
                    lng=cam["lng"],
                    prediction=PredictionResult(**r["result"]),
                )
            )
        else:
            failed += 1

    logger.info(
        f"[batch_predict] Done: {len(predictions)}/{len(cameras)} succeeded in {total_time_ms}ms"
    )
    return BatchPredictResponse(
        predictions=predictions,
        total=len(cameras),
        succeeded=len(predictions),
        failed=failed,
        total_time_ms=total_time_ms,
    )


# ============================================================
# CONGESTION DETECTION ENDPOINTS (Rule-based, no training)
# ============================================================


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
        overall_status = "Một số nơi đông đúc"
    elif avg_level < 2.5:
        overall_status = "Kẹt xe nhiều nơi"
    else:
        overall_status = "Ùn tắc nghiêm trọng"

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


@router.get(
    "/predict/camera/{camera_id}/history",
    response_model=PredictionHistoryResponse,
    summary="Prediction History",
    description="Returns prediction history for a camera (trend chart data).",
)
async def prediction_history(camera_id: str):
    """[prediction_history] Return cached prediction history for trend charts."""
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    cache = PredictionCache.get_instance()
    history = cache.get_history(camera_id)
    return PredictionHistoryResponse(
        camera_id=camera_id,
        camera_name=camera.get("name"),
        history=[PredictionHistoryEntry(**h) for h in history],
        total=len(history),
    )


CAMERA_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://giaothong.hochiminhcity.gov.vn/",
}


@router.get(
    "/camera/{camera_id}/image",
    summary="Proxy Camera Image",
    description="Proxies the live camera image from the HCMC traffic server. Use this URL as `<img src>` in the frontend.",
    responses={
        200: {"content": {"image/jpeg": {}}},
        502: {"description": "Camera server unavailable"},
        504: {"description": "Camera server timeout"},
    },
)
async def proxy_camera_image(request: Request, camera_id: str):
    """[proxy_camera_image] Fetch and proxy camera image to bypass CORS."""
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    image_url = get_camera_image_url(camera_id)
    try:
        client: httpx.AsyncClient = request.app.state.http_client
        response = await client.get(
            image_url,
            headers=CAMERA_FETCH_HEADERS,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        response.raise_for_status()

        content = response.content
        content_type = response.headers.get("content-type", "image/jpeg")

        _cache_image(camera_id, content, content_type)
    except Exception as e:
        cached = _get_cached_image(camera_id)
        if cached:
            logger.warning(
                f"[proxy_camera_image] Fetch failed ({e}), using cached image for {camera_id}."
            )
            content = cached["content"]
            content_type = cached["content_type"]
        else:
            if isinstance(e, httpx.TimeoutException):
                raise HTTPException(
                    status_code=504, detail=f"Timeout fetching camera: {camera_id}"
                )
            else:
                logger.error(f"[proxy_camera_image] Failed: {e}", exc_info=True)
                raise HTTPException(status_code=502, detail="Camera fetch error")

    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ============================================================
# FORECAST ENDPOINTS (Prediction from historical data)
# ============================================================


@router.get(
    "/forecast/{camera_id}",
    response_model=ForecastResponse,
    summary="Predict Traffic Future",
    description="Predict traffic density for next 15/30/60 minutes based on 30-minute history.",
)
async def get_traffic_forecast(camera_id: str):
    """
    [get_traffic_forecast] Dự đoán giao thông tương lai dựa trên lịch sử 30 phút.

    Sử dụng:
    - Weighted Moving Average
    - Trend detection (linear regression)
    - Time-based features (rush hour patterns)

    Yêu cầu: Camera phải có ít nhất 3 điểm dữ liệu trong 30 phút qua.
    """
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")

    forecaster = get_forecaster()
    result = await forecaster.predict(camera_id)

    if result is None:
        raise HTTPException(
            status_code=503,
            detail=f"Not enough history data for camera {camera_id}. "
            "Need at least 3 prediction points in the last 30 minutes.",
        )

    return ForecastResponse(
        camera_id=camera_id,
        timestamp=datetime.now(),
        history_points=result["history_points"],
        current=result["current"],
        statistics=result["statistics"],
        forecasts=result["forecasts"],
        time_features=result["time_features"],
    )


# ============================================================
# DEBUG ENDPOINT - System Status Dashboard
# ============================================================


@router.get(
    "/debug",
    summary="Debug Dashboard",
    description="Quick overview of system health, cameras, and database status.",
)
async def debug_dashboard(request: Request):
    """
    Debug endpoint showing:
    - Health status
    - Database stats
    - Camera status
    - Writer status
    - Analytics & reporting data

    Results are cached for 30 seconds to prevent DB overload.
    """
    from .database import get_pool

    # Check cache first
    current_time = time.time()
    if (
        _debug_cache["data"] is not None
        and current_time - _debug_cache["timestamp"] < _DEBUG_CACHE_TTL_SECONDS
    ):
        return _debug_cache["data"]

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

            # Build hourly_per_camera by grouping in Python (same data source)
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

            # Build all_records list - sorted by timestamp desc
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
                    "avg_count": float(r["avg_count"]),
                }
                for r in hourly
            ],
            "daily_distribution": [
                {
                    "day": str(r["day"]),
                    "count": r["count"],
                    "avg_count": float(r["avg_count"]),
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
                "avg_total": float(overall["avg_total"]) if overall["avg_total"] else 0,
                "avg_car": float(overall["avg_car"]) if overall["avg_car"] else 0,
                "avg_motorbike": (
                    float(overall["avg_motorbike"]) if overall["avg_motorbike"] else 0
                ),
                "std_total": float(overall["std_total"]) if overall["std_total"] else 0,
                "max_total": overall["max_total"] or 0,
                "min_total": overall["min_total"] or 0,
                "heavy_pct": float(overall["heavy_pct"]) if overall["heavy_pct"] else 0,
                "moderate_pct": (
                    float(overall["moderate_pct"]) if overall["moderate_pct"] else 0
                ),
                "low_pct": float(overall["low_pct"]) if overall["low_pct"] else 0,
            },
            "recent_records": [
                {
                    "id": str(r["id"]),
                    "camera_id": r["camera_id"],
                    "total_count": r["total_count"] or 0,
                    "car_count": r["car_count"] or 0,
                    "motorbike_count": r["motorbike_count"] or 0,
                    "density_level": r["density_level"] or "unknown",
                    "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                }
                for r in recent_records
            ],
            # hourly_per_camera and all_records are already formatted above using CTE
            "hourly_per_camera": hourly_per_camera,
            "all_records": all_records,
        }
    except Exception as e:
        result["database"] = {"status": "error", "error": str(e)}

    # 3. Camera check — get from DB for accurate real-time status
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Get latest prediction per camera from DB
            latest_per_cam = await conn.fetch(
                """
                SELECT DISTINCT ON (camera_id)
                       camera_id,
                       total_count,
                       car_count,
                       motorbike_count,
                       density_level,
                       timestamp
                FROM prediction_history
                ORDER BY camera_id, timestamp DESC
                """
            )
            latest_map = {r["camera_id"]: dict(r) for r in latest_per_cam}

        cache = PredictionCache.get_instance()
        camera_status = []
        for cam in CAMERAS:
            db_data = latest_map.get(cam["id"])
            cached = cache.get_latest(cam["id"]) if not db_data else None
            camera_status.append(
                {
                    "id": cam["id"],
                    "name": cam["name"],
                    "district": cam["district"],
                    "lat": cam.get("lat"),
                    "lng": cam.get("lng"),
                    "cached": db_data is not None or cached is not None,
                    "last_count": (
                        (db_data or cached or {}).get("total_count")
                        if (db_data or cached)
                        else None
                    ),
                    "last_level": (
                        (db_data or cached or {}).get("density_level")
                        if (db_data or cached)
                        else None
                    ),
                    "last_car": (
                        (db_data or cached or {}).get("car_count")
                        if (db_data or cached)
                        else None
                    ),
                    "last_motorbike": (
                        (db_data or cached or {}).get("motorbike_count")
                        if (db_data or cached)
                        else None
                    ),
                    "last_timestamp": (
                        (db_data or cached or {}).get("timestamp")
                        if (db_data or cached)
                        else None
                    ),
                }
            )
        result["cameras"] = {
            "total": len(CAMERAS),
            "cached": len([c for c in camera_status if c["cached"]]),
            "list": camera_status,
            "districts": list({c["district"] for c in camera_status}),
        }
    except Exception as e:
        logger.warning(f"[debug_dashboard] camera check error: {e}")
        result["cameras"] = {
            "total": len(CAMERAS),
            "cached": 0,
            "list": [],
            "districts": [],
            "error": str(e),
        }

    # 4. Writer status
    try:
        writer = getattr(request.app.state, "writer", None)
        if writer and writer.running:
            result["writer"] = {
                "status": "running",
                "interval_seconds": writer.interval,
                "batch_size": writer.batch_size,
            }
        else:
            result["writer"] = {"status": "stopped"}
    except Exception as e:
        logger.warning(f"[debug_dashboard] writer check error: {e}")
        result["writer"] = {"status": "error", "error": str(e)}

    # 5. Analytics summary
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Predictions per hour (last 24h)
            rate_24h = (
                await conn.fetchval(
                    """
                SELECT COUNT(*) / 24.0
                FROM prediction_history
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                """
                )
                or 0
            )
            # Peak hour (last 30 days)
            peak = await conn.fetchrow(
                """
                SELECT EXTRACT(HOUR FROM timestamp) as hour,
                       COUNT(*) as cnt
                FROM prediction_history
                WHERE timestamp > NOW() - INTERVAL '30 days'
                GROUP BY EXTRACT(HOUR FROM timestamp)
                ORDER BY cnt DESC
                LIMIT 1
                """
            )
            # Safely query using parameterized query with camera IDs
            # Then map results in Python to avoid SQL injection
            camera_ids = [c["id"] for c in CAMERAS]
            district_stats = await conn.fetch(
                """
                SELECT 
                    p.camera_id,
                    COUNT(*) as count,
                    ROUND(AVG(p.total_count)::numeric, 1) as avg_count,
                    ROUND(AVG(CASE WHEN p.density_level = 'heavy' THEN 1 ELSE 0 END) * 100, 1) as heavy_pct
                FROM prediction_history p
                WHERE p.camera_id = ANY($1::text[])
                GROUP BY p.camera_id
                ORDER BY avg_count DESC
                LIMIT 20
                """,
                camera_ids,
            )

            # Build camera_id -> district mapping
            cam_district_map = {c["id"]: c["district"] for c in CAMERAS}

            # Aggregate by district in Python (safe from SQL injection)
            district_agg = {}
            for row in district_stats:
                district = cam_district_map.get(row["camera_id"], "Unknown")
                if district not in district_agg:
                    district_agg[district] = {
                        "count": 0,
                        "avg_count": 0,
                        "heavy_pct": 0,
                        "total_rows": 0,
                    }
                district_agg[district]["count"] += row["count"]
                district_agg[district]["total_rows"] += 1

            # Calculate weighted average
            for district, stats in district_agg.items():
                if stats["total_rows"] > 0:
                    # Get average for this district from individual camera stats
                    district_cams = [
                        r
                        for r in district_stats
                        if cam_district_map.get(r["camera_id"]) == district
                    ]
                    total_count = sum(r["count"] for r in district_cams)
                    if total_count > 0:
                        stats["avg_count"] = (
                            sum(r["avg_count"] * r["count"] for r in district_cams)
                            / total_count
                        )
                        stats["heavy_pct"] = (
                            sum(r["heavy_pct"] * r["count"] for r in district_cams)
                            / total_count
                        )

            # Find worst district
            worst_district_row = max(
                district_agg.items(),
                key=lambda x: x[1]["avg_count"],
                default=(None, None),
            )
            worst_district = (
                {
                    "district": worst_district_row[0],
                    "count": (
                        worst_district_row[1]["count"] if worst_district_row[1] else 0
                    ),
                    "avg_count": (
                        worst_district_row[1]["avg_count"]
                        if worst_district_row[1]
                        else 0
                    ),
                    "heavy_pct": (
                        worst_district_row[1]["heavy_pct"]
                        if worst_district_row[1]
                        else 0
                    ),
                }
                if worst_district_row[0]
                else None
            )
        result["analytics"] = {
            "predictions_per_hour_24h": round(float(rate_24h), 1),
            "peak_hour": int(peak["hour"]) if peak else None,
            "peak_hour_count": peak["cnt"] if peak else None,
            "worst_district": (
                {
                    "district": worst_district["district"],
                    "avg_count": (
                        float(worst_district["avg_count"]) if worst_district else 0
                    ),
                    "heavy_pct": (
                        float(worst_district["heavy_pct"]) if worst_district else 0
                    ),
                    "total_predictions": (
                        worst_district["count"] if worst_district else 0
                    ),
                }
                if worst_district
                else None
            ),
        }
    except Exception as e:
        logger.warning(f"[debug_dashboard] analytics error: {e}")
        result["analytics"] = {}

    # Cache the result before returning
    _debug_cache["data"] = result
    _debug_cache["timestamp"] = time.time()

    return result


@router.get(
    "/debug/camera/{camera_id}/records",
    summary="Get camera records",
    description="Get all records for a specific camera in the last hour.",
)
async def get_camera_records(request: Request, camera_id: str, limit: int = 50):
    """
    Get detailed records for a specific camera.
    Returns all records in the last 1 hour, sorted by timestamp descending.
    """
    from .database import get_pool

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
async def list_camera_ids(request: Request):
    """Get all unique camera IDs from database for debugging."""
    from .database import get_pool

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
