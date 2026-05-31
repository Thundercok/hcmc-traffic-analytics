import asyncio
import json
import logging
import os
import sys

# Khắc phục lỗi tìm module bằng cách add thư mục /app vào Python Path
sys.path.append("/app")

from backend.database import get_pool, init_db_pool, close_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("export_rois")

async def export_rois():
    await init_db_pool()
    pool = get_pool()
    
    # Ghi thẳng file backup ra thư mục gốc /app của container
    output_file = "/app/camera_rois_backup.json"
    logger.info("🎬 Đang trích xuất dữ liệu vùng mặt đường (ROI) từ DB...")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT camera_id, roi_polygon, is_auto FROM camera_rois ORDER BY camera_id"
        )
        
        records = []
        for r in rows:
            val = r["roi_polygon"]
            try:
                poly = json.loads(val) if isinstance(val, str) else val
            except Exception:
                poly = val
                
            records.append({
                "camera_id": r["camera_id"],
                "roi_polygon": poly,
                "is_auto": r["is_auto"] or False
            })
            
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
            
        logger.info(f"💾 Xuất thành công {len(records)} vùng ROI ra file '{output_file}'")
    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(export_rois())