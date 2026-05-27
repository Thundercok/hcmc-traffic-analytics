"""Quick test for collect_data module."""

import asyncio, sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "trafficflow-api"))
from backend.cameras import CAMERAS
from collect_data import analyze_image_fast, predict_from_image
import httpx


async def test():
    # Try a known working camera
    cam_id = "63ae76afbfd3d90017e8f106"
    url = f"https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id={cam_id}&t={int(time.time()*1000)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://giaothong.hochiminhcity.gov.vn/",
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
        for attempt in range(3):
            try:
                resp = await http.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.content
                analysis = analyze_image_fast(data)
                pred = predict_from_image(data)
                print(f"Camera ID: {cam_id}")
                print(f"Is error: {analysis['is_error']}")
                print(f"Size: {len(data)} bytes")
                print(f"Brightness: {analysis.get('brightness')}")
                print(f"Red ratio: {analysis.get('red_ratio')}")
                print(
                    f"Prediction: total={pred['total_count']}, car={pred['car_count']}, moto={pred['motorbike_count']}, level={pred['density_level']}"
                )
                break
            except httpx.RemoteProtocolError:
                print(f"Attempt {attempt+1}: Server disconnected, retrying...")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Error: {e}")
                break


asyncio.run(test())
