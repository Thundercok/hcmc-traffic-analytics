import os
import glob
import time
import csv
import httpx
import asyncio

# Cấu hình
API_URL = "https://htrnguyen-trafficflow-api.hf.space/api/predict"
INPUT_FOLDER = "./test_images"
OUTPUT_CSV = "evaluation_results.csv"
CONCURRENT_REQUESTS = 10


async def predict_image(
    client: httpx.AsyncClient, image_path: str, sem: asyncio.Semaphore
):
    filename = os.path.basename(image_path)
    async with sem:
        try:
            with open(image_path, "rb") as f:
                files = {"file": (filename, f, "image/jpeg")}

                start_time = time.time()
                response = await client.post(API_URL, files=files)
                latency = time.time() - start_time

                if response.status_code == 200:
                    data = response.json()
                    pred = data.get("prediction", {})
                    print(
                        f"[SUCCESS] {filename} -> {pred.get('total_count', 0)} xe ({round(latency, 2)}s)"
                    )
                    return {
                        "filename": filename,
                        "status": "success",
                        "total_count": pred.get("total_count", 0),
                        "car_count": pred.get("car_count", 0),
                        "motorbike_count": pred.get("motorbike_count", 0),
                        "person_count": pred.get("person_count", 0),
                        "density_level": pred.get("density_level", "unknown"),
                        "latency_seconds": round(latency, 2),
                        "error": "",
                    }
                else:
                    print(f"[FAILED] {filename} -> HTTP {response.status_code}")
                    return {
                        "filename": filename,
                        "status": "failed",
                        "total_count": 0,
                        "car_count": 0,
                        "motorbike_count": 0,
                        "person_count": 0,
                        "density_level": "error",
                        "latency_seconds": round(latency, 2),
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }
        except Exception as e:
            print(f"[ERROR] {filename} -> {str(e)}")
            return {
                "filename": filename,
                "status": "error",
                "total_count": 0,
                "car_count": 0,
                "motorbike_count": 0,
                "person_count": 0,
                "density_level": "error",
                "latency_seconds": 0,
                "error": str(e),
            }


async def main():
    if not os.path.exists(INPUT_FOLDER):
        print(f"[ERROR] Không tìm thấy thư mục: {INPUT_FOLDER}")
        print("[INFO] Vui lòng tạo thư mục này và chép ảnh (jpg, png) vào để bắt đầu.")
        os.makedirs(INPUT_FOLDER, exist_ok=True)
        return

    image_extensions = ["*.jpg", "*.jpeg", "*.png"]
    image_paths = []
    for ext in image_extensions:
        image_paths.extend(glob.glob(os.path.join(INPUT_FOLDER, ext)))
        image_paths.extend(glob.glob(os.path.join(INPUT_FOLDER, ext.upper())))

    if not image_paths:
        print(f"[WARNING] Không có ảnh nào trong thư mục {INPUT_FOLDER}.")
        return

    print(f"[INFO] Bắt đầu Stress Test {len(image_paths)} ảnh qua API: {API_URL}")
    print(
        f"[INFO] Đang giả lập {CONCURRENT_REQUESTS} requests đồng thời (Concurrent Processing)..."
    )

    start_total_time = time.time()

    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

    transport = httpx.AsyncHTTPTransport(retries=3)
    async with httpx.AsyncClient(transport=transport, timeout=120.0) as client:
        tasks = [predict_image(client, path, sem) for path in image_paths]
        results = await asyncio.gather(*tasks)

    total_latency = time.time() - start_total_time

    fieldnames = [
        "filename",
        "status",
        "total_count",
        "car_count",
        "motorbike_count",
        "person_count",
        "density_level",
        "latency_seconds",
        "error",
    ]

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[INFO] Hoàn tất quá trình đánh giá. Báo cáo lưu tại: {OUTPUT_CSV}")

    successful_runs = [r for r in results if r["status"] == "success"]
    if successful_runs:
        avg_latency = sum(r["latency_seconds"] for r in successful_runs) / len(
            successful_runs
        )
        print(f"\n[REPORT] THỐNG KÊ HIỆU NĂNG BATCH INFERENCE:")
        print(f"   - Tổng số ảnh đã xử lý: {len(results)}")
        print(
            f"   - Số lượng thành công: {len(successful_runs)}/{len(results)} ({(len(successful_runs)/len(results))*100:.1f}%)"
        )
        print(
            f"   - Tổng thời gian hoàn thành (Wall-clock time): {total_latency:.2f} giây"
        )
        print(
            f"   - Thông lượng (Throughput): {len(results)/total_latency:.2f} ảnh/giây"
        )
        print(
            f"   - Thời gian phản hồi trung bình (Per Image): {avg_latency:.2f} giây/ảnh"
        )


if __name__ == "__main__":
    asyncio.run(main())
