import asyncio
import json
import logging
import os
from backend.database import get_pool, init_db_pool, close_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("import_rois")

async def import_rois():
    await init_db_pool()
    pool = await get_pool()
    
    # Check if file is at /app/camera_rois_backup.json (Docker volume) or local relative path
    docker_path = "/app/camera_rois_backup.json"
    local_path = os.path.join(os.path.dirname(__file__), "..", "camera_rois_backup.json")
    
    input_file = docker_path if os.path.exists(docker_path) else local_path
    
    if not os.path.exists(input_file):
        logger.error(f"❌ Không tìm thấy file backup tại: {input_file}")
        await close_db_pool()
        return

    with open(input_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info(f"Đang import {len(records)} dữ liệu mặt đường vào Database...")
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            for r in records:
                # Đảm bảo chuyển polygon về dạng text json
                poly_val = r["roi_polygon"]
                poly_str = json.dumps(poly_val) if isinstance(poly_val, (list, dict)) else poly_val
                
                await conn.execute("""
                    INSERT INTO camera_rois (camera_id, roi_polygon, is_auto, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (camera_id) 
                    DO UPDATE SET roi_polygon = EXCLUDED.roi_polygon, 
                                  is_auto = EXCLUDED.is_auto, 
                                  updated_at = NOW();
                """, r["camera_id"], poly_str, r.get("is_auto", False))
                
    logger.info("🎉 [SUCCESS] Đã đồng bộ cấu trúc mặt đường và dữ liệu thành công!")
    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(import_rois())