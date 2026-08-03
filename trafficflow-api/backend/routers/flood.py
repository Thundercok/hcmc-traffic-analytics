from datetime import datetime
from io import BytesIO
import logging
from typing import Dict

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from PIL import Image

from ..cameras import CAMERAS_DB
from ..config import settings
from ..flood_service import FloodModelService
from ..schemas import (
    FloodCameraResponse,
    FloodHotspotItem,
    FloodHotspotSummary,
    FloodPredictionResult,
)

logger = logging.getLogger("trafficflow.router.flood")
router = APIRouter()


@router.post(
    "/predict",
    response_model=FloodPredictionResult,
    summary="Dự đoán mức độ ngập từ file ảnh",
    description="Upload ảnh mặt đường/camera → nhận kết quả mức độ ngập (Khô ráo / Ướt / Triều cường ngập sâu) và cảnh báo di chuyển cho xe máy & ô tô.",
)
async def predict_flood_from_image(
    file: UploadFile = File(...),
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là hình ảnh (JPEG/PNG).")

    contents = await file.read()
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Dung lượng file vượt quá giới hạn cho phép.")

    try:
        image = Image.open(BytesIO(contents)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể đọc file ảnh: {e}")

    svc = FloodModelService.get_instance()
    result = svc.predict(image)
    return result


@router.get(
    "/camera/{cam_id}",
    response_model=FloodCameraResponse,
    summary="Dự đoán mức độ ngập từ Camera live",
    description="Lấy khung hình thời gian thực từ camera giao thông theo CamID → phân tích mức độ ngập triều cường và khuyến nghị an toàn.",
)
async def predict_flood_for_camera(
    cam_id: str,
    request: Request,
):
    cam = CAMERAS_DB.get(cam_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy camera với ID '{cam_id}'")

    cam_url = f"{settings.camera_base_url}?id={cam_id}"
    http_client: httpx.AsyncClient = getattr(request.app.state, "http_client", None)

    if not http_client:
        raise HTTPException(status_code=500, detail="HTTP client chưa được khởi tạo.")

    try:
        resp = await http_client.get(cam_url)
        if resp.status_code != 200 or len(resp.content) < 1000:
            raise HTTPException(status_code=502, detail="Camera ngắt kết nối hoặc không gửi được hình ảnh.")
        image = Image.open(BytesIO(resp.content)).convert("RGB")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy ảnh camera {cam_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối camera: {e}")

    svc = FloodModelService.get_instance()
    prediction = svc.predict(image)
    is_hotspot, _ = svc.is_nhabe_hotspot(cam.name, cam.district)

    return FloodCameraResponse(
        camera_id=cam_id,
        camera_name=cam.name,
        district=cam.district,
        is_nhabe_hotspot=is_hotspot,
        flood=prediction,
        timestamp=datetime.now(),
    )


@router.get(
    "/hotspots",
    response_model=FloodHotspotSummary,
    summary="Danh sách & trạng thái ngập các camera Rốn Ngập Nhà Bè",
    description="Truy vấn toàn bộ các camera thuộc khu vực Nhà Bè & Nam Sài Gòn để tổng hợp tình hình triều cường ngập nước thời gian thực.",
)
async def get_nhabe_flood_hotspots(request: Request):
    svc = FloodModelService.get_instance()
    http_client: httpx.AsyncClient = getattr(request.app.state, "http_client", None)

    hotspots = []
    dry_count, wet_count, flooded_count = 0, 0, 0

    for cam_id, cam in CAMERAS_DB.items():
        is_hotspot, kw = svc.is_nhabe_hotspot(cam.name, cam.district)
        if not is_hotspot:
            continue

        pred = None
        if http_client:
            try:
                cam_url = f"{settings.camera_base_url}?id={cam_id}"
                resp = await http_client.get(cam_url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    img = Image.open(BytesIO(resp.content)).convert("RGB")
                    pred = svc.predict(img)
            except Exception:
                pass

        if pred is None:
            # Default fallback for offline hotspot cameras
            advice = svc.predict(Image.new("RGB", (224, 224), (128, 128, 128)))
            pred = advice

        code = pred["severity_code"]
        if code == 0:
            dry_count += 1
        elif code == 1:
            wet_count += 1
        elif code == 2:
            flooded_count += 1

        hotspots.append(
            FloodHotspotItem(
                camera_id=cam_id,
                camera_name=cam.name,
                district=cam.district,
                matched_keyword=kw,
                severity_code=code,
                severity_label=pred["severity_label"],
                severity_display=pred["severity_display"],
                confidence=pred["confidence"],
                motorbike_advice=pred["motorbike_advice"],
                car_advice=pred["car_advice"],
            )
        )

    return FloodHotspotSummary(
        total_hotspots=len(hotspots),
        dry_count=dry_count,
        wet_count=wet_count,
        flooded_count=flooded_count,
        hotspots=hotspots,
        timestamp=datetime.now(),
    )
