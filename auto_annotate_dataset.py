#!/usr/bin/env python3
"""
Automated Dataset Annotation Engine for PG-MTAN
Uses YOLOv8 for vehicle detection & 2D spatial density map generation +
Physics-informed HSV reflection analysis for 2D flood segmentation masks.
"""

import os
import csv
import json
import glob
import math
import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

# Constants
YOLO_MODEL_PATH = "yolov8n.pt"
DATA_DIR = "data/hand_labeled"
IMAGE_DIR = os.path.join(DATA_DIR, "images")
ANNOTATIONS_CSV = os.path.join(DATA_DIR, "annotations.csv")
OUTPUT_DATASET_DIR = "data/HCMC_Traffic"

IMG_W, IMG_H = 640, 480
FEAT_W, FEAT_H = IMG_W // 16, IMG_H // 16  # (40, 30) matching ResNet18 downsampling

COCO_VEHICLE_MAP = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

def density_level_from_count(total_count):
    if total_count < 15:
        return "low"
    elif total_count < 35:
        return "moderate"
    elif total_count < 60:
        return "heavy"
    else:
        return "severe"

def create_gaussian_density_map(boxes_cls, feat_h=30, feat_w=40, orig_w=640, orig_h=480, sigma=1.5):
    """
    Generate 2D spatial density map [1, feat_h, feat_w] from detected vehicle bounding box centers.
    """
    density_map = np.zeros((1, feat_h, feat_w), dtype=np.float32)
    y_grid, x_grid = np.ogrid[:feat_h, :feat_w]

    for (x1, y1, x2, y2, cls_id) in boxes_cls:
        cx_orig = (x1 + x2) / 2.0
        cy_orig = (y1 + y2) / 2.0

        # Scale center to feature map coordinates
        cx = (cx_orig / orig_w) * feat_w
        cy = (cy_orig / orig_h) * feat_h

        # Weight per vehicle type (TCVN 4054:2005 PCU)
        pcu = 0.35 if cls_id == 3 else (2.5 if cls_id in (5, 7) else 1.0)

        # 2D Gaussian kernel
        dist_sq = (x_grid - cx) ** 2 + (y_grid - cy) ** 2
        gaussian_blob = pcu * np.exp(-dist_sq / (2 * (sigma ** 2)))
        density_map[0] += gaussian_blob

    return density_map

def compute_hsv_flood_mask(rgb_img_np, feat_h=30, feat_w=40):
    """
    Physics-informed HSV reflection & wetness detector.
    Returns 2D flood severity mask [feat_h, feat_w] with values:
    0 = Dry, 1 = Wet, 2 = Flooded (>= 15cm)
    """
    hsv = cv2.cvtColor(rgb_img_np, cv2.COLOR_RGB2HSV)
    h, w, _ = rgb_img_np.shape
    
    # Analyze lower road ROI (bottom 40% of the image)
    road_roi = hsv[int(h * 0.6):, :]
    val_std = float(np.std(road_roi[:, :, 2]))
    sat_mean = float(np.mean(road_roi[:, :, 1]))
    
    # Headlight glare suppression mask (High V, Low S)
    glare_mask = (road_roi[:, :, 2] > 220) & (road_roi[:, :, 1] < 50)
    corrected_sat = sat_mean * (1.0 - float(np.mean(glare_mask)))
    
    score = (val_std * 0.4) + (corrected_sat * 0.6)
    
    if score > 65.0:
        severity = 2  # Flooded >= 15cm
    elif score > 42.0:
        severity = 1  # Wet
    else:
        severity = 0  # Dry

    # Create full 2D mask matching feature map grid
    mask = np.full((feat_h, feat_w), severity, dtype=np.int64)
    return mask, severity, score

def run_auto_annotation():
    print(f"🚀 Initializing YOLOv8 model from {YOLO_MODEL_PATH}...")
    model = YOLO(YOLO_MODEL_PATH)

    image_files = sorted(glob.glob(os.path.join(IMAGE_DIR, "*.jpg")))
    print(f"📷 Found {len(image_files)} image files in {IMAGE_DIR}")

    # Prepare output dataset structure
    train_labels = {}
    val_labels = {}

    for split in ["train", "val"]:
        os.makedirs(os.path.join(OUTPUT_DATASET_DIR, split, "images"), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DATASET_DIR, split, "density_maps"), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DATASET_DIR, split, "flood_masks"), exist_ok=True)

    # Read existing CSV annotations if present
    csv_rows = []
    if os.path.exists(ANNOTATIONS_CSV):
        with open(ANNOTATIONS_CSV, "r", encoding="utf-8-sig") as f:
            csv_rows = list(csv.DictReader(f))

    updated_csv_dict = {r["image_file"]: r for r in csv_rows}

    annotated_count = 0
    for idx, img_path in enumerate(image_files, start=1):
        rel_img_path = os.path.relpath(img_path, DATA_DIR)
        img_name = os.path.basename(img_path)
        img_name_no_ext = os.path.splitext(img_name)[0]

        # Load RGB image
        img_pil = Image.open(img_path).convert("RGB")
        img_resized = img_pil.resize((IMG_W, IMG_H))
        rgb_np = np.array(img_resized)

        # Run YOLOv8 inference with low confidence threshold for small distant vehicles
        results = model(img_resized, conf=0.10, verbose=False)[0]

        counts = {"motorcycle": 0, "car": 0, "bus": 0, "truck": 0}
        detected_boxes = []

        if results.boxes is not None and len(results.boxes) > 0:
            boxes = results.boxes.xyxy.cpu().numpy()
            cls_ids = results.boxes.cls.cpu().numpy().astype(int)

            for box, cls_id in zip(boxes, cls_ids):
                if cls_id in COCO_VEHICLE_MAP:
                    v_type = COCO_VEHICLE_MAP[cls_id]
                    counts[v_type] += 1
                    x1, y1, x2, y2 = box
                    detected_boxes.append((x1, y1, x2, y2, cls_id))

        total_vehicles = counts["motorcycle"] + counts["car"] + counts["bus"] + counts["truck"]
        density_lvl = density_level_from_count(total_vehicles)

        # 1. Generate 2D Density Map
        density_map = create_gaussian_density_map(
            detected_boxes, feat_h=FEAT_H, feat_w=FEAT_W, orig_w=IMG_W, orig_h=IMG_H
        )

        # 2. Compute 2D Flood Mask
        flood_mask, flood_severity, flood_score = compute_hsv_flood_mask(
            rgb_np, feat_h=FEAT_H, feat_w=FEAT_W
        )

        # Determine split (val if index % 5 == 0)
        split = "val" if idx % 5 == 0 else "train"
        target_dir = os.path.join(OUTPUT_DATASET_DIR, split)

        # Save resized image
        img_resized.save(os.path.join(target_dir, "images", f"{img_name_no_ext}.jpg"), format="JPEG")

        # Save density map (.npy)
        np.save(os.path.join(target_dir, "density_maps", f"{img_name_no_ext}.npy"), density_map)

        # Save flood mask (.npy)
        np.save(os.path.join(target_dir, "flood_masks", f"{img_name_no_ext}.npy"), flood_mask)

        # Record in split labels dict: [motorcycle, car, truck, bus]
        class_list = [counts["motorcycle"], counts["car"], counts["truck"], counts["bus"]]
        if split == "train":
            train_labels[f"{img_name_no_ext}.jpg"] = class_list
        else:
            val_labels[f"{img_name_no_ext}.jpg"] = class_list

        # Update CSV dict
        if rel_img_path in updated_csv_dict:
            row = updated_csv_dict[rel_img_path]
            row["total_count"] = str(total_vehicles)
            row["car_count"] = str(counts["car"])
            row["motorbike_count"] = str(counts["motorcycle"])
            row["density_level"] = density_lvl
            row["label_status"] = "auto_annotated_yolo_hsv"
            row["labeler"] = "YOLOv8n + PhysicsHSV"
            row["split"] = split
            row["notes"] = f"Auto-annotated: {counts['motorcycle']} moto, {counts['car']} car, {counts['bus'] + counts['truck']} heavy. Flood score={flood_score:.1f} (level={flood_severity})"

        annotated_count += 1
        print(f"  [{idx:02d}/{len(image_files)}] {img_name} -> Vehicles: {total_vehicles} (M:{counts['motorcycle']}, C:{counts['car']}), Flood Level: {flood_severity} (Score: {flood_score:.1f}) -> Split: {split}")

    # Save JSON labels for both splits
    with open(os.path.join(OUTPUT_DATASET_DIR, "train", "labels.json"), "w", encoding="utf-8") as f:
        json.dump(train_labels, f, indent=4)

    with open(os.path.join(OUTPUT_DATASET_DIR, "val", "labels.json"), "w", encoding="utf-8") as f:
        json.dump(val_labels, f, indent=4)

    # Save updated CSV
    if csv_rows:
        fieldnames = list(csv_rows[0].keys())
        with open(ANNOTATIONS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(list(updated_csv_dict.values()))

    print("=" * 70)
    print(f"🎉 AUTO-ANNOTATION COMPLETE!")
    print(f"  • Total Images Processed: {annotated_count}")
    print(f"  • Train Set Size: {len(train_labels)} samples")
    print(f"  • Val Set Size: {len(val_labels)} samples")
    print(f"  • Output Dataset Location: {os.path.abspath(OUTPUT_DATASET_DIR)}")
    print("=" * 70)

if __name__ == "__main__":
    run_auto_annotation()
