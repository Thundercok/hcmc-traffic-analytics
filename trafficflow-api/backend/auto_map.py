import asyncio
import json
import logging
import argparse
from backend.cameras import CAMERAS
from backend.database import get_pool, init_db_pool, close_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auto_map")

async def auto_map():
    parser = argparse.ArgumentParser(description="Auto-map road segments (ROIs) for cameras.")
    parser.add_argument(
        "--district",
        type=str,
        default=None,
        help="Filter cameras by district (e.g. 'Quận 7' or 'Quận 1')",
    )
    args = parser.parse_args()

    # 1. Initialize database pool
    await init_db_pool()
    pool = await get_pool()

    # Highly calibrated centered default road trapezoid polygon
    default_roi = [
        [0.3, 0.45],
        [0.7, 0.45],
        [0.95, 0.95],
        [0.05, 0.95]
    ]
    roi_json = json.dumps(default_roi)

    # 2. Filter cameras
    if args.district:
        cameras_to_map = [c for c in CAMERAS if c["district"] == args.district]
        logger.info(f"Targeting district '{args.district}': found {len(cameras_to_map)} cameras.")
    else:
        cameras_to_map = CAMERAS
        logger.info(f"Targeting ALL districts: found {len(cameras_to_map)} cameras.")

    if not cameras_to_map:
        logger.warning("No cameras found to map.")
        await close_db_pool()
        return

    # 3. Batch insert ROIs with is_auto = TRUE
    logger.info("Starting auto-mapping...")
    async with pool.acquire() as conn:
        # Check how many ROIs exist
        existing = await conn.fetch("SELECT camera_id, is_auto FROM camera_rois")
        existing_map = {r["camera_id"]: r["is_auto"] for r in existing}
        logger.info(f"Database currently has {len(existing_map)} total camera ROIs.")

        inserted = 0
        skipped_manual = 0
        skipped_exists = 0

        for cam in cameras_to_map:
            cam_id = cam["id"]
            if cam_id in existing_map:
                if not existing_map[cam_id]:
                    skipped_manual += 1
                else:
                    skipped_exists += 1
                continue

            res = await conn.execute(
                """
                INSERT INTO camera_rois (camera_id, roi_polygon, updated_at, is_auto)
                VALUES ($1, $2, NOW(), TRUE)
                ON CONFLICT (camera_id) DO NOTHING
                """,
                cam_id,
                roi_json
            )
            if res == "INSERT 0 1":
                inserted += 1

        logger.info(f"Auto-mapping complete for district filtering: {args.district or 'ALL'}")
        logger.info(f"- Mapped (New): {inserted} cameras")
        logger.info(f"- Skipped (Preserved Manual): {skipped_manual} cameras")
        logger.info(f"- Skipped (Already Auto): {skipped_exists} cameras")
        
        total_mapped = await conn.fetchval("SELECT COUNT(*) FROM camera_rois")
        logger.info(f"Grand total mapped cameras in DB: {total_mapped}")

    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(auto_map())
