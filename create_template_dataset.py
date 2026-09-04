#!/usr/bin/env python3
"""
Script to create a template directory structure for the HCMC Traffic Dataset
and populate it with a few dummy files so you can see exactly how to format your real data.
"""
import os
import json
import numpy as np
from PIL import Image

def create_dataset_template(base_dir="data/HCMC_Traffic"):
    splits = ['train', 'val']
    subdirs = ['images', 'density_maps', 'flood_masks']
    
    img_size = (640, 480) # W, H
    feat_size = (img_size[0] // 16, img_size[1] // 16) # ResNet18 downsampled size (40, 30)

    for split in splits:
        split_dir = os.path.join(base_dir, split)
        
        # Create directories
        for sub in subdirs:
            os.makedirs(os.path.join(split_dir, sub), exist_ok=True)
        
        # Create labels.json
        labels_dict = {}
        
        num_samples = 5 if split == 'train' else 2
        for i in range(num_samples):
            img_name = f"cam_01_{i:04d}"
            
            # 1. Create Dummy Image
            img_arr = np.random.randint(0, 255, (img_size[1], img_size[0], 3), dtype=np.uint8)
            img = Image.fromarray(img_arr)
            img.save(os.path.join(split_dir, 'images', f"{img_name}.jpg"))
            
            # 2. Create Dummy Density Map (.npy)
            density = np.random.rand(1, feat_size[1], feat_size[0]).astype(np.float32) * 5.0
            np.save(os.path.join(split_dir, 'density_maps', f"{img_name}.npy"), density)
            
            # 3. Create Dummy Flood Mask (.npy)
            # 0=Dry, 1=Wet, 2=Flooded
            flood = np.random.randint(0, 3, (feat_size[1], feat_size[0]), dtype=np.int64)
            np.save(os.path.join(split_dir, 'flood_masks', f"{img_name}.npy"), flood)
            
            # 4. Record Class Counts in JSON
            # [motorcycle, car, truck, bus]
            labels_dict[f"{img_name}.jpg"] = [
                np.random.randint(0, 30), # moto
                np.random.randint(0, 10), # car
                np.random.randint(0, 5),  # truck
                np.random.randint(0, 5)   # bus
            ]
            
        with open(os.path.join(split_dir, 'labels.json'), 'w') as f:
            json.dump(labels_dict, f, indent=4)
            
    print(f"✅ Template dataset successfully created at: {os.path.abspath(base_dir)}")
    print("Folder Structure:")
    for root, dirs, files in os.walk(base_dir):
        level = root.replace(base_dir, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if not f.startswith('.'):
                print(f"{subindent}{f}")

if __name__ == "__main__":
    create_dataset_template()
