import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Query, Form
from fastapi.concurrency import run_in_threadpool

from ..schemas import (
    PredictResponse,
    BatchPredictRequest,
    BatchPredictResponse,
    BatchPredictionItem,
    PredictionResult,
    PredictionHistoryEntry,
    PredictionHistoryResponse,
)
from ..cameras import (
    get_camera_by_id,
    get_camera_image_url,
    get_cameras_by_district,
)
from ..model_service import ZIPModelService
from ..prediction_cache import PredictionCache
from ..config import settings
from ..utils import (
    CAMERA_FETCH_HEADERS,
    _cache_image,
    _get_cached_image,
    _generate_placeholder_image,
    _validate_image_bytes,
    _parse_roi_polygon,
    _build_predict_response,
)

logger = logging.getLogger("trafficflow.routers.predict")
router = APIRouter()


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
async def predict_from_camera(
    request: Request,
    camera_id: str,
    heatmap: bool = False,
    roi_polygon: Optional[str] = Query(
        None, description="JSON string of normalized ROI polygon coordinates"
    ),
):
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
            # Try to get any other cached camera image as a fallback
            any_cached = None
            if _IMAGE_FALLBACK_CACHE:
                try:
                    for k, v in list(_IMAGE_FALLBACK_CACHE.items()):
                        if v.get("content"):
                            any_cached = v["content"]
                            logger.warning(
                                f"[predict_from_camera] Fetch failed for {camera_id} ({e}). "
                                f"No specific cache found. Falling back to cached image from camera {k}."
                            )
                            break
                except Exception:
                    pass

            if any_cached:
                image_bytes = any_cached
            else:
                logger.warning(
                    f"[predict_from_camera] Fetch failed for {camera_id} ({e}). "
                    "No cache available. Generating dynamic placeholder image."
                )
                try:
                    image_bytes = _generate_placeholder_image(f"CAMERA {camera_id} OFFLINE")
                except Exception as gen_err:
                    logger.error(f"Failed to generate placeholder image: {gen_err}")
                    image_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\x27" "#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'

    # Load ROI polygon from database or request query parameter
    if roi_polygon:
        roi = _parse_roi_polygon(roi_polygon)
    else:
        from ..database import get_camera_roi
        roi = await get_camera_roi(camera_id)

    try:
        result = await run_in_threadpool(
            svc.predict_from_bytes,
            image_bytes,
            return_heatmap=heatmap,
            roi_polygon=roi,
        )
    except Exception as e:
        logger.error(f"[predict_from_camera] Inference failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal prediction error")

    # Record prediction to in-memory cache for instant trend chart update
    try:
        cache = PredictionCache.get_instance()
        cache.record(camera_id, result)
    except Exception as cache_err:
        logger.warning(f"[predict_from_camera] Failed to record to cache: {cache_err}")

    return _build_predict_response(
        result, camera_id=camera_id, camera_name=camera.get("name")
    )


_BATCH_MAX_CAMERAS = 30
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

    # Load all camera ROIs from DB
    try:
        from ..database import get_all_camera_rois
        camera_rois = await get_all_camera_rois()
    except Exception as e:
        logger.error(f"[batch_predict] Failed to fetch camera ROIs: {e}")
        camera_rois = {}

    async def _predict_one(cam: dict) -> dict:
        try:
            roi = camera_rois.get(cam["id"])
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

                result = await run_in_threadpool(
                    svc.predict_from_bytes, image_bytes, roi_polygon=roi
                )
                cache.record(cam["id"], result)
                return {"cam": cam, "result": result, "ok": True}
            except Exception as e:
                cached = _get_cached_image(cam["id"])
                if cached:
                    logger.warning(
                        f"[batch_predict] Fetch failed ({e}), using cached image for {cam['id']}."
                    )
                    image_bytes = cached["content"]
                    try:
                        result = await run_in_threadpool(
                            svc.predict_from_bytes, image_bytes, roi_polygon=roi
                        )
                        cache.record(cam["id"], result)
                        return {"cam": cam, "result": result, "ok": True}
                    except Exception as inner_e:
                        logger.error(f"[batch_predict] Cached predict failed for {cam['id']}: {inner_e}", exc_info=True)
                        return {"cam": cam, "result": None, "ok": False}
                else:
                    logger.warning(f"[batch_predict] Failed for {cam['id']}: {e}")
                    return {"cam": cam, "result": None, "ok": False}
        except Exception as e:
            logger.error(f"[batch_predict] Critical failure for single camera {cam.get('id')}: {e}", exc_info=True)
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

    # Fallback to DB if cache has few entries (cold start)
    if len(history) < 5:
        try:
            from ..database import get_camera_history
            db_history = await get_camera_history(camera_id, minutes=60)
            if db_history:
                formatted_db = []
                for entry in reversed(db_history):
                    ts = entry["timestamp"]
                    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                    formatted_db.append({
                        "timestamp": ts_str,
                        "total_count": entry["total_count"],
                        "car_count": entry["car_count"],
                        "motorbike_count": entry["motorbike_count"],
                        "density_level": entry["density_level"]
                    })
                # Populate in-memory cache
                with cache._lock:
                    cache._data[camera_id].clear()
                    for item in formatted_db:
                        cache._data[camera_id].append({
                            **item,
                            "inference_time_ms": 0
                        })
                history = cache.get_history(camera_id)
        except Exception as e:
            logger.warning(f"[prediction_history] Failed to fetch fallback history from DB: {e}")

    return PredictionHistoryResponse(
        camera_id=camera_id,
        camera_name=camera.get("name"),
        history=[PredictionHistoryEntry(**h) for h in history],
        total=len(history),
    )
