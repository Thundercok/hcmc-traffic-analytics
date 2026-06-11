import time
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import HTTPException

from .schemas import PredictResponse, PredictionResult, PredictionMeta
from .model_service import ZIPModelService
from .config import settings

logger = logging.getLogger("trafficflow.utils")

_IMAGE_FALLBACK_CACHE = {}
_IMAGE_CACHE_MAX_SIZE = 20  # Maximum number of cached images
_IMAGE_CACHE_TTL_SECONDS = 300  # 5 minutes TTL

CAMERA_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://giaothong.hochiminhcity.gov.vn/",
}

NOMINATIM_HEADERS = {
    "User-Agent": "TrafficFlowApp/1.0 (contact@trafficflow.vn)",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

_MAGIC_JPEG = b"\xff\xd8"
_MAGIC_PNG = b"\x89PNG"


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


def _generate_placeholder_image(text: str = "CAMERA OFFLINE") -> bytes:
    """Generate a programmatic placeholder JPEG image with offline text overlay using Pillow."""
    import io
    from PIL import Image, ImageDraw
    try:
        # Create a simple gray image
        img = Image.new("RGB", (640, 480), color=(128, 128, 128))
        d = ImageDraw.Draw(img)
        d.text((320, 240), text, fill=(255, 255, 255), anchor="mm")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Error drawing placeholder image: {e}")
        # Raw tiny black JPEG 1x1 fallback to prevent crashes
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\x27" "#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'


def _validate_image_bytes(data: bytes) -> None:
    """[_validate_image_bytes] Check magic bytes to verify real image content (V-03)."""
    if data[:2] == _MAGIC_JPEG or data[:4] == _MAGIC_PNG:
        return
    raise HTTPException(
        status_code=400, detail="Invalid image format (expected JPEG or PNG)"
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
