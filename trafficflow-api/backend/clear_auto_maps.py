import asyncio
import logging
import argparse
from backend.cameras import CAMERAS
from backend.database import get_pool, init_db_pool, close_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clear_auto_maps")

async def clear_auto_maps():
    parser = argparse.ArgumentParser(description="Clear auto-mapped road segments (ROIs).")
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

    # 2. Perform deletion
    async with pool.acquire() as conn:
        if args.district:
            # Gather camera IDs for the specified district
            district_cam_ids = [c["id"] for c in CAMERAS if c["district"] == args.district]
            if not district_cam_ids:
                logger.warning(f"No cameras found in district '{args.district}'.")
                await close_db_pool()
                return

            logger.info(f"Clearing auto ROIs for district '{args.district}' ({len(district_cam_ids)} potential cameras)...")
            res = await conn.execute(
                """
                DELETE FROM camera_rois 
                WHERE is_auto = TRUE 
                  AND camera_id = ANY($1)
                """,
                district_cam_ids
            )
            # Parse number of deleted rows
            deleted = int(res.split(" ")[1]) if "DELETE" in res else 0
            logger.info(f"Successfully deleted {deleted} auto-mapped camera ROIs in district '{args.district}'.")
        else:
            logger.info("Clearing ALL auto-mapped camera ROIs in database...")
            res = await conn.execute("DELETE FROM camera_rois WHERE is_auto = TRUE")
            deleted = int(res.split(" ")[1]) if "DELETE" in res else 0
            logger.info(f"Successfully deleted {deleted} total auto-mapped camera ROIs.")

        # Print current count
        total = await conn.fetchval("SELECT COUNT(*) FROM camera_rois")
        logger.info(f"Grand total remaining mapped cameras (your manual mappings): {total}")

    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(clear_auto_maps())
