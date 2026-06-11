import logging
from typing import Optional
import httpx
from fastapi import APIRouter, Request, HTTPException, Query, Response

from ..schemas import (
    CameraInfo,
    CameraListResponse,
    CameraRoiRequest,
    CameraRoiResponse,
)
from ..cameras import (
    CAMERAS,
    get_camera_by_id,
    get_camera_image_url,
    get_cameras_by_district,
    get_all_districts,
)
from ..utils import (
    CAMERA_FETCH_HEADERS,
    NOMINATIM_HEADERS,
    _cache_image,
    _get_cached_image,
)

logger = logging.getLogger("trafficflow.routers.cameras")
router = APIRouter()


@router.get("/geocode/search", summary="Proxy Nominatim search queries to avoid CORS/IP blocking")
async def proxy_geocode_search(q: str = Query(..., min_length=3)):
    """[proxy_geocode_search] Geocode search queries using Nominatim from the backend."""
    url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&addressdetails=1&countrycodes=vn&limit=5"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=NOMINATIM_HEADERS)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Geocode proxy search failed: {e}")
        return []


@router.get("/geocode/reverse", summary="Proxy Nominatim reverse geocoding to avoid CORS/IP blocking")
async def proxy_geocode_reverse(lat: float, lon: float):
    """[proxy_geocode_reverse] Reverse geocode coordinates using Nominatim from the backend."""
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=NOMINATIM_HEADERS)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Geocode proxy reverse failed: {e}")
        return {"display_name": "Vị trí không xác định"}


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
    from ..database import get_all_camera_rois_with_meta
    
    if district:
        filtered = get_cameras_by_district(district)
    else:
        filtered = CAMERAS
        
    try:
        camera_rois = await get_all_camera_rois_with_meta()
    except Exception as e:
        logger.error(f"Failed to fetch camera ROIs for listing: {e}")
        camera_rois = {}
        
    camera_list = []
    for cam in filtered:
        cam_info = dict(cam)
        has_roi = cam["id"] in camera_rois
        is_auto_roi = False
        if has_roi:
            is_auto_roi = camera_rois[cam["id"]]["is_auto"]
        cam_info["has_roi"] = has_roi
        cam_info["is_auto_roi"] = is_auto_roi
        camera_list.append(CameraInfo(**cam_info))
        
    return CameraListResponse(cameras=camera_list, total=len(camera_list))


@router.get(
    "/cameras/stats",
    summary="Get Camera Mapping Progress Stats",
    description="Get statistics on road mapping progress: mapped count vs total.",
)
async def get_camera_mapping_stats():
    """[get_camera_mapping_stats] Returns count of mapped cameras vs total cameras."""
    from ..database import get_all_camera_rois_with_meta
    
    try:
        rois = await get_all_camera_rois_with_meta()
        mapped_count = len(rois)
        manual_count = sum(1 for r in rois.values() if not r["is_auto"])
        auto_count = sum(1 for r in rois.values() if r["is_auto"])
    except Exception as e:
        logger.error(f"Failed to get camera ROIs count from DB: {e}")
        mapped_count = 0
        manual_count = 0
        auto_count = 0
        
    total_count = len(CAMERAS)
    unmapped_count = max(0, total_count - mapped_count)
    percentage = round((mapped_count / total_count * 100), 1) if total_count > 0 else 0.0
    
    return {
        "total_cameras": total_count,
        "mapped_cameras": mapped_count,
        "manual_cameras": manual_count,
        "auto_cameras": auto_count,
        "unmapped_cameras": unmapped_count,
        "percentage_mapped": percentage
    }


@router.get(
    "/cameras/{camera_id}/roi",
    response_model=CameraRoiResponse,
    summary="Get Camera ROI",
    description="Retrieve the saved ROI polygon coordinates for a camera."
)
async def get_camera_roi_endpoint(camera_id: str):
    """[get_camera_roi_endpoint] Retrieve the saved ROI polygon coordinates for a camera."""
    from ..database import get_camera_roi_with_meta
    
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")
        
    roi, is_auto = await get_camera_roi_with_meta(camera_id)
    return CameraRoiResponse(camera_id=camera_id, roi_polygon=roi, is_auto=is_auto)


@router.post(
    "/cameras/{camera_id}/roi",
    summary="Save Camera ROI",
    description="Save the ROI polygon coordinates for a camera."
)
async def save_camera_roi_endpoint(camera_id: str, payload: CameraRoiRequest):
    """[save_camera_roi_endpoint] Save the ROI polygon coordinates for a camera."""
    from ..database import save_camera_roi
    
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
    from ..database import delete_camera_roi
    
    camera = get_camera_by_id(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera ID not found: {camera_id}")
        
    await delete_camera_roi(camera_id)
    return {"status": "success", "message": f"ROI deleted for camera {camera_id}"}


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
