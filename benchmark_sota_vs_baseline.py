#!/usr/bin/env python3
"""
SOTA vs Baseline Comparative Benchmark Audit Script
Compares:
1. Baseline Pipeline (YOLOv8n + HSV Heuristic Flood Engine)
2. SOTA PG-MTAN Unified Physics-Guided Multi-Task Model

Hardware Accelerator: Apple Silicon MPS / CUDA / CPU
"""

import os
import io
import time
import json
import requests
import numpy as np
from PIL import Image
import torch
import torchvision.transforms as T
from ultralytics import YOLO

# Import SOTA PG-MTAN Model
from pg_mtan_model import PGMTANNet, KendallGalMultiTaskLoss, DEVICE

print("=" * 70)
print(f"🚀 SOTA PG-MTAN VS BASELINE COMPARATIVE BENCHMARK AUDIT")
print(f"   Accelerator Device: {DEVICE.upper()}")
print("=" * 70)

# Fetch or generate test frame
def get_benchmark_frame():
    url = "https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx?id=5bb74ca1b2383c00192e2124"
    try:
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200 and len(resp.content) > 2000:
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        pass
    # Standard synthetic 640x480 frame
    np.random.seed(42)
    return Image.fromarray(np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8))

test_img = get_benchmark_frame()

# -------------------------------------------------------------
# 1. Benchmark Baseline Pipeline (YOLOv8 + HSV Engine)
# -------------------------------------------------------------
def benchmark_baseline(num_runs=50):
    print("\n📦 [1/2] BENCHMARKING BASELINE (YOLOv8 + HSV Engine)...")
    
    t0_load = time.perf_counter()
    yolo_model = YOLO("yolov8n.pt")
    load_time_ms = (time.perf_counter() - t0_load) * 1000.0

    # Warmup
    for _ in range(5):
        _ = yolo_model.predict(test_img, device=DEVICE, verbose=False)

    latencies = []
    for _ in range(num_runs):
        t0 = time.perf_counter()
        _ = yolo_model.predict(test_img, device=DEVICE, verbose=False)
        # Simulate HSV lower ROI calculation
        img_np = np.array(test_img)
        h, w, _ = img_np.shape
        _ = np.std(img_np[int(h*0.6):, :, 0])
        t_tot = (time.perf_counter() - t0) * 1000.0
        latencies.append(t_tot)

    return {
        "model": "YOLOv8 + HSV Baseline",
        "load_time_ms": round(load_time_ms, 2),
        "mean_latency_ms": round(float(np.mean(latencies)), 2),
        "std_latency_ms": round(float(np.std(latencies)), 2),
        "p50_latency_ms": round(float(np.percentile(latencies, 50)), 2),
        "p95_latency_ms": round(float(np.percentile(latencies, 95)), 2),
        "throughput_fps": round(1000.0 / float(np.mean(latencies)), 2)
    }

# -------------------------------------------------------------
# 2. Benchmark SOTA PG-MTAN Model
# -------------------------------------------------------------
def benchmark_pg_mtan(num_runs=50):
    print("\n⚡ [2/2] BENCHMARKING SOTA PG-MTAN MODEL...")

    t0_load = time.perf_counter()
    pg_mtan = PGMTANNet(pretrained=False).to(DEVICE)
    pg_mtan.eval()
    load_time_ms = (time.perf_counter() - t0_load) * 1000.0

    # Preprocessing transform
    transform = T.Compose([
        T.Resize((480, 640)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    tensor_input = transform(test_img).unsqueeze(0).to(DEVICE)

    # Warmup
    with torch.no_grad():
        for _ in range(5):
            _ = pg_mtan(tensor_input)

    latencies = []
    with torch.no_grad():
        for _ in range(num_runs):
            t0 = time.perf_counter()
            _ = pg_mtan(tensor_input)
            t_tot = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_tot)

    return {
        "model": "SOTA PG-MTAN (Proposed)",
        "load_time_ms": round(load_time_ms, 2),
        "mean_latency_ms": round(float(np.mean(latencies)), 2),
        "std_latency_ms": round(float(np.std(latencies)), 2),
        "p50_latency_ms": round(float(np.percentile(latencies, 50)), 2),
        "p95_latency_ms": round(float(np.percentile(latencies, 95)), 2),
        "throughput_fps": round(1000.0 / float(np.mean(latencies)), 2)
    }

# -------------------------------------------------------------
# Run Main Benchmark & Save Audit Artifact
# -------------------------------------------------------------
if __name__ == "__main__":
    baseline_res = benchmark_baseline(num_runs=50)
    pg_mtan_res = benchmark_pg_mtan(num_runs=50)

    print("\n" + "=" * 70)
    print("📊 EMPIRICAL SOTA VS BASELINE BENCHMARK AUDIT SUMMARY")
    print("=" * 70)
    print(f"| {'Model Architecture':<25} | {'Mean (ms)':<10} | {'P50 (ms)':<10} | {'P95 (ms)':<10} | {'Throughput (FPS)':<16} |")
    print("|" + "-"*27 + "|" + "-"*12 + "|" + "-"*12 + "|" + "-"*12 + "|" + "-"*18 + "|")
    print(f"| {baseline_res['model']:<25} | {baseline_res['mean_latency_ms']:<10} | {baseline_res['p50_latency_ms']:<10} | {baseline_res['p95_latency_ms']:<10} | {baseline_res['throughput_fps']:<16} |")
    print(f"| {pg_mtan_res['model']:<25} | {pg_mtan_res['mean_latency_ms']:<10} | {pg_mtan_res['p50_latency_ms']:<10} | {pg_mtan_res['p95_latency_ms']:<10} | {pg_mtan_res['throughput_fps']:<16} |")
    print("=" * 70)

    # Save to JSON
    audit_data = {"baseline": baseline_res, "pg_mtan": pg_mtan_res}
    with open("sota_vs_baseline_benchmark.json", "w") as f:
        json.dump(audit_data, f, indent=2)
    print("✅ Saved comparative benchmark results to sota_vs_baseline_benchmark.json")
