#!/usr/bin/env python3
"""
NCKH Baseline Benchmark Audit Script
Performs strict, reproducible cold-start & warm-start benchmarking for:
1. Module A: YOLOv8 Vehicle Detection & PCU Density
2. Module B: HSV Water Reflection Flood Classifier
3. End-to-End Pipeline Latency & Throughput (FPS)
"""

import os
import io
import time
import json
import requests
import numpy as np
from PIL import Image
import cv2
import torch
import torchvision.transforms as T
from ultralytics import YOLO

# Detect Acceleration Device
if torch.cuda.is_available():
    DEVICE = "cuda"
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"

print("=" * 60)
print(f"🚀 NCKH BENCHMARK AUDIT STARTING | ACCELERATOR: {DEVICE.upper()}")
print("=" * 60)

# Sample HCMC Camera IDs
SAMPLE_CAMERAS = {
    "CAM_HUYNH_TAN_PHAT": "5bb74ca1b2383c00192e2124",
    "CAM_TRAN_XUAN_SOAN": "5bb74ca1b2383c00192e2125",
    "CAM_NGUYEN_VAN_LINH": "5bb74ca1b2383c00192e2126"
}
BASE_URL = "https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx"

def fetch_sample_frame():
    """Fetch live camera frame or generate reproducible test image."""
    for cam_name, cam_id in SAMPLE_CAMERAS.items():
        try:
            url = f"{BASE_URL}?id={cam_id}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200 and len(resp.content) > 2000:
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                print(f"📷 Loaded live frame from {cam_name} ({img.size[0]}x{img.size[1]})")
                return img
        except Exception as e:
            continue
    
    # Fallback to generated standard frame (640x480)
    print("⚠️ Live CCTV unavailable, generating standard synthetic benchmark frame (640x480)...")
    np.random.seed(42)
    img_arr = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)
    return Image.fromarray(img_arr)

# -------------------------------------------------------------
# Module Implementations
# -------------------------------------------------------------
class TrafficAnalyzer:
    VEHICLE_CLASSES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    PCU_WEIGHTS = {"bicycle": 0.2, "motorcycle": 0.35, "car": 1.0, "truck": 2.0, "bus": 2.5}

    def __init__(self, model_path="yolov8n.pt"):
        t0 = time.perf_counter()
        self.model = YOLO(model_path)
        self.load_time_ms = (time.perf_counter() - t0) * 1000.0

    def process(self, image: Image.Image, conf=0.25):
        t0 = time.perf_counter()
        results = self.model.predict(image, conf=conf, device=DEVICE, verbose=False)[0]
        t_infer = (time.perf_counter() - t0) * 1000.0

        t0_post = time.perf_counter()
        counts = {"motorcycle": 0, "car": 0, "truck": 0, "bus": 0, "bicycle": 0}
        total_pcu = 0.0
        img_np = np.array(image)
        annotated = img_np.copy()

        for box in results.boxes:
            cls_id = int(box.cls[0].item())
            if cls_id in self.VEHICLE_CLASSES:
                cname = self.VEHICLE_CLASSES[cls_id]
                counts[cname] += 1
                total_pcu += self.PCU_WEIGHTS.get(cname, 1.0)
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                cv2.rectangle(annotated, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), (0, 255, 0), 2)
        
        t_post = (time.perf_counter() - t0_post) * 1000.0
        return t_infer, t_post, sum(counts.values()), total_pcu

class FloodClassifier:
    LABELS = {0: "Dry", 1: "Wet", 2: "Flooded >=15cm"}

    def __init__(self):
        t0 = time.perf_counter()
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        self.init_time_ms = (time.perf_counter() - t0) * 1000.0

    def analyze(self, image: Image.Image):
        t0 = time.perf_counter()
        img_np = np.array(image.convert("RGB"))
        hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV)
        h, w, _ = img_np.shape
        road_roi = hsv[int(h * 0.6):, :]
        val_std = np.std(road_roi[:, :, 2])
        sat_mean = np.mean(road_roi[:, :, 1])
        score = (val_std * 0.4) + (sat_mean * 0.6)
        
        if score > 65.0:
            code = 2
        elif score > 42.0:
            code = 1
        else:
            code = 0
        t_infer = (time.perf_counter() - t0) * 1000.0
        return t_infer, code, score

# -------------------------------------------------------------
# Run Benchmark
# -------------------------------------------------------------
def run_benchmark(num_warmup=10, num_runs=50):
    sample_img = fetch_sample_frame()

    # Cold Start Measurement
    print("\n❄️ MEASURING COLD-START LATENCY...")
    t_cold_start_t0 = time.perf_counter()
    traffic_analyzer = TrafficAnalyzer("yolov8n.pt")
    flood_classifier = FloodClassifier()
    # First inference cold start
    c_infer, c_post, _, _ = traffic_analyzer.process(sample_img)
    f_infer, _, _ = flood_classifier.analyze(sample_img)
    t_cold_total_ms = (time.perf_counter() - t_cold_start_t0) * 1000.0

    print(f"  • Model Loading Time: {traffic_analyzer.load_time_ms:.2f} ms")
    print(f"  • 1st Frame Cold-Start Pipeline Latency: {t_cold_total_ms:.2f} ms")

    # Warmup
    print(f"\n🔥 WARMING UP DEVICE ({DEVICE.upper()}) FOR {num_warmup} ITERATIONS...")
    for _ in range(num_warmup):
        traffic_analyzer.process(sample_img)
        flood_classifier.analyze(sample_img)

    # Warm Benchmark Runs
    print(f"\n⏱️ RUNNING BENCHMARK ({num_runs} ITERATIONS)...")
    yolo_times = []
    flood_times = []
    post_times = []
    total_times = []

    for i in range(num_runs):
        t0_iter = time.perf_counter()
        
        y_t, p_t, veh_cnt, pcu = traffic_analyzer.process(sample_img)
        f_t, flood_code, score = flood_classifier.analyze(sample_img)
        
        t_total_iter = (time.perf_counter() - t0_iter) * 1000.0

        yolo_times.append(y_t)
        flood_times.append(f_t)
        post_times.append(p_t)
        total_times.append(t_total_iter)

    # Compute Statistics
    stats = {
        "device": DEVICE.upper(),
        "iterations": num_runs,
        "cold_start_total_ms": round(t_cold_total_ms, 2),
        "yolo_load_time_ms": round(traffic_analyzer.load_time_ms, 2),
        "yolo_infer_mean_ms": round(float(np.mean(yolo_times)), 2),
        "yolo_infer_std_ms": round(float(np.std(yolo_times)), 2),
        "flood_infer_mean_ms": round(float(np.mean(flood_times)), 2),
        "flood_infer_std_ms": round(float(np.std(flood_times)), 2),
        "postprocess_mean_ms": round(float(np.mean(post_times)), 2),
        "total_latency_mean_ms": round(float(np.mean(total_times)), 2),
        "total_latency_std_ms": round(float(np.std(total_times)), 2),
        "total_latency_min_ms": round(float(np.min(total_times)), 2),
        "total_latency_max_ms": round(float(np.max(total_times)), 2),
        "total_latency_p50_ms": round(float(np.percentile(total_times, 50)), 2),
        "total_latency_p95_ms": round(float(np.percentile(total_times, 95)), 2),
        "throughput_fps": round(1000.0 / float(np.mean(total_times)), 2)
    }

    # Print Summary Markdown Table
    print("\n" + "=" * 60)
    print("📊 EMPIRICAL BENCHMARK AUDIT RESULTS SUMMARY")
    print("=" * 60)
    print(f"| Hardware Accelerator: | {stats['device']} |")
    print(f"| Benchmark Sample Size: | {stats['iterations']} iterations |")
    print(f"| Cold-Start Init Latency: | {stats['cold_start_total_ms']} ms |")
    print(f"| YOLOv8 Inference Mean: | {stats['yolo_infer_mean_ms']} ± {stats['yolo_infer_std_ms']} ms |")
    print(f"| Flood Classifier Mean: | {stats['flood_infer_mean_ms']} ± {stats['flood_infer_std_ms']} ms |")
    print(f"| Post-Process / BBox: | {stats['postprocess_mean_ms']} ms |")
    print(f"| Total End-to-End Mean: | {stats['total_latency_mean_ms']} ± {stats['total_latency_std_ms']} ms |")
    print(f"| Latency P50 / P95: | {stats['total_latency_p50_ms']} ms / {stats['total_latency_p95_ms']} ms |")
    print(f"| Throughput (FPS): | {stats['throughput_fps']} FPS |")
    print("=" * 60)

    # Save to JSON artifact
    out_path = "benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"✅ Saved full benchmark results to {out_path}")

if __name__ == "__main__":
    run_benchmark(num_warmup=10, num_runs=50)
