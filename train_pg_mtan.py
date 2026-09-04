#!/usr/bin/env python3
"""
Training Script for PG-MTAN (Physics-Guided Multi-Task Attention Network)
Loss: Kendall & Gal Homoscedastic Multi-Task Loss

Usage:
    python train_pg_mtan.py --epochs 50 --batch-size 8
    # For dry-run/testing without real data:
    python train_pg_mtan.py --epochs 2 --batch-size 2 --dummy-data
"""

import os
import time
import argparse
import logging
from tqdm import tqdm
import glob
import json
import numpy as np
from PIL import Image
import torchvision.transforms as T

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
# from torch.utils.tensorboard import SummaryWriter

# Import model and loss from pg_mtan_model.py
from pg_mtan_model import PGMTANNet, KendallGalMultiTaskLoss, DEVICE

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Trainer")

# -------------------------------------------------------------
# 1. Dataset Loader
# -------------------------------------------------------------
class HCMCTrafficFloodDataset(Dataset):
    """
    Dataset loader for HCMC traffic camera data.
    Provides:
    - image: RGB Tensor [3, H, W]
    - density_map: 2D Tensor [1, H/8, W/8] (Traffic Density Ground Truth)
    - traffic_classes: 1D Tensor [4] (Vehicle counts for Moto, Car, Truck, Bus)
    - flood_mask: 2D Tensor [H/8, W/8] (Flood Segmentation: 0=Dry, 1=Wet, 2=Flooded)
    """
    def __init__(self, data_dir, is_train=True, use_dummy=False, img_size=(480, 640)):
        self.data_dir = data_dir
        self.is_train = is_train
        self.use_dummy = use_dummy
        self.img_size = img_size
        self.feat_size = (img_size[0] // 16, img_size[1] // 16) # ResNet18 downsamples by 16 at layer3

        if not use_dummy:
            self.split = 'train' if is_train else 'val'
            self.split_dir = os.path.join(data_dir, self.split)
            
            if os.path.exists(self.split_dir):
                self.image_paths = sorted(glob.glob(os.path.join(self.split_dir, 'images', '*.jpg')))
                with open(os.path.join(self.split_dir, 'labels.json'), 'r') as f:
                    self.labels_dict = json.load(f)
                self.length = len(self.image_paths)
            else:
                logger.warning(f"Data directory {self.split_dir} not found! Falling back to dummy mode.")
                self.use_dummy = True
                self.length = 100 if is_train else 20
                
            self.transform = T.Compose([
                T.Resize((self.img_size[0], self.img_size[1])),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
        else:
            self.length = 100 if is_train else 20

    def __len__(self):
        return self.length

    def __getitem__(self, idx):
        if self.use_dummy:
            # Generate random fake data for testing pipeline
            img = torch.randn(3, self.img_size[0], self.img_size[1])
            # Density map must match the feature map output size (H/16, W/16)
            density_map = torch.rand(1, self.feat_size[0], self.feat_size[1]) * 10
            # Classes: [motorcycle, car, truck, bus]
            traffic_classes = torch.randint(0, 20, (4,), dtype=torch.float32)
            # Flood mask: 0=Dry, 1=Wet, 2=Flooded
            flood_mask = torch.randint(0, 3, (self.feat_size[0], self.feat_size[1]), dtype=torch.long)
            
            return img, density_map, traffic_classes, flood_mask
        
        # Real data implementation
        img_path = self.image_paths[idx]
        img_name = os.path.basename(img_path)
        img_name_no_ext = os.path.splitext(img_name)[0]
        
        # 1. Load Image
        img = Image.open(img_path).convert('RGB')
        img = self.transform(img)
        
        # 2. Load Density Map
        density_path = os.path.join(self.split_dir, 'density_maps', f"{img_name_no_ext}.npy")
        density_np = np.load(density_path)
        density_map = torch.from_numpy(density_np).float()
        
        # 3. Load Flood Mask
        flood_path = os.path.join(self.split_dir, 'flood_masks', f"{img_name_no_ext}.npy")
        flood_np = np.load(flood_path)
        flood_mask = torch.from_numpy(flood_np).long()
        
        # 4. Load Classes
        classes = self.labels_dict.get(img_name, [0, 0, 0, 0])
        traffic_classes = torch.tensor(classes, dtype=torch.float32)
        
        return img, density_map, traffic_classes, flood_mask

# -------------------------------------------------------------
# 2. Training Pipeline
# -------------------------------------------------------------
def train_epoch(model, dataloader, optimizer, loss_fn, writer, epoch, device):
    model.train()
    running_loss = 0.0
    running_loss_traffic = 0.0
    running_loss_flood = 0.0
    
    # Standard Loss Functions for individual tasks
    mse_loss = nn.MSELoss()
    ce_loss = nn.CrossEntropyLoss()

    pbar = tqdm(dataloader, desc=f"Epoch {epoch} [Train]", leave=False)
    for batch_idx, (imgs, true_density, true_cls, true_flood) in enumerate(pbar):
        imgs = imgs.to(device)
        true_density = true_density.to(device)
        true_cls = true_cls.to(device)
        true_flood = true_flood.to(device)

        optimizer.zero_grad()

        # Forward Pass
        outputs = model(imgs)
        pred_density = outputs["density_map"]
        pred_cls = outputs["traffic_cls_logits"]
        pred_flood = outputs["flood_seg_logits"]

        # Calculate Individual Task Losses
        # 1. Traffic Loss (Density MSE + Classification MSE)
        l_density = mse_loss(pred_density, true_density)
        l_cls = mse_loss(pred_cls, true_cls)
        l_traffic = l_density + 0.1 * l_cls

        # 2. Flood Loss (Segmentation CrossEntropy)
        l_flood = ce_loss(pred_flood, true_flood)

        # 3. Apply Kendall & Gal Multi-Task Homoscedastic Loss
        total_loss, s_traffic, s_flood = loss_fn(l_traffic, l_flood)

        # Backward Pass & Optimization
        total_loss.backward()
        
        # Gradient Clipping to prevent explosion (especially for s parameters)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
        
        optimizer.step()

        # Logging
        running_loss += total_loss.item()
        running_loss_traffic += l_traffic.item()
        running_loss_flood += l_flood.item()
        
        pbar.set_postfix({
            'Loss': f"{total_loss.item():.4f}", 
            's_tr': f"{s_traffic:.2f}", 
            's_fl': f"{s_flood:.2f}"
        })

        # TensorBoard Logging per batch
        step = epoch * len(dataloader) + batch_idx
        if step % 10 == 0 and writer is not None:
            writer.add_scalar('Train/Total_Loss', total_loss.item(), step)
            writer.add_scalar('Train/Traffic_Loss', l_traffic.item(), step)
            writer.add_scalar('Train/Flood_Loss', l_flood.item(), step)
            writer.add_scalar('Uncertainty/s_traffic', s_traffic, step)
            writer.add_scalar('Uncertainty/s_flood', s_flood, step)

    return running_loss / len(dataloader)

def validate(model, dataloader, loss_fn, epoch, device):
    model.eval()
    val_loss = 0.0
    mse_loss = nn.MSELoss()
    ce_loss = nn.CrossEntropyLoss()

    with torch.no_grad():
        for imgs, true_density, true_cls, true_flood in tqdm(dataloader, desc=f"Epoch {epoch} [Val]", leave=False):
            imgs = imgs.to(device)
            true_density = true_density.to(device)
            true_cls = true_cls.to(device)
            true_flood = true_flood.to(device)

            outputs = model(imgs)
            
            l_traffic = mse_loss(outputs["density_map"], true_density) + 0.1 * mse_loss(outputs["traffic_cls_logits"], true_cls)
            l_flood = ce_loss(outputs["flood_seg_logits"], true_flood)
            
            total_loss, _, _ = loss_fn(l_traffic, l_flood)
            val_loss += total_loss.item()

    return val_loss / len(dataloader)

def main(args):
    logger.info(f"🚀 Starting PG-MTAN Training Pipeline on {DEVICE.upper()}")
    
    # 1. Initialize Dataset & DataLoaders
    logger.info("Initializing DataLoaders...")
    train_dataset = HCMCTrafficFloodDataset(data_dir="data/HCMC_Traffic", is_train=True, use_dummy=args.dummy_data)
    val_dataset = HCMCTrafficFloodDataset(data_dir="data/HCMC_Traffic", is_train=False, use_dummy=args.dummy_data)
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # 2. Initialize Model & Loss
    logger.info("Initializing PG-MTAN Model...")
    model = PGMTANNet(pretrained=False).to(DEVICE)
    loss_fn = KendallGalMultiTaskLoss(num_tasks=2).to(DEVICE)

    # 3. Optimizer & Scheduler
    # We pass both model parameters and loss_fn parameters (the trainable s1, s2 log_vars)
    optimizer = optim.AdamW(list(model.parameters()) + list(loss_fn.parameters()), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5)

    # 4. TensorBoard Writer
    os.makedirs("runs", exist_ok=True)
    os.makedirs("checkpoints", exist_ok=True)
    run_name = f"PGMTAN_{time.strftime('%Y%m%d_%H%M%S')}"
    # writer = SummaryWriter(log_dir=f"runs/{run_name}")
    writer = None
    logger.info(f"TensorBoard logging to runs/{run_name}")

    # 5. Training Loop
    best_val_loss = float('inf')
    
    for epoch in range(1, args.epochs + 1):
        train_loss = train_epoch(model, train_loader, optimizer, loss_fn, writer, epoch, DEVICE)
        val_loss = validate(model, val_loader, loss_fn, epoch, DEVICE)
        
        scheduler.step(val_loss)

        logger.info(f"Epoch {epoch:03d}/{args.epochs:03d} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
        
        if writer is not None:
            writer.add_scalar('Epoch/Train_Loss', train_loss, epoch)
            writer.add_scalar('Epoch/Val_Loss', val_loss, epoch)
            writer.add_scalar('Epoch/Learning_Rate', optimizer.param_groups[0]['lr'], epoch)

        # Checkpoint Saving
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            ckpt_path = f"checkpoints/best_pg_mtan.pth"
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'loss_vars': loss_fn.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss
            }, ckpt_path)
            logger.info(f"🌟 Saved new best model -> {ckpt_path}")

    if writer is not None:
        writer.close()
    logger.info("🎉 Training Complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PG-MTAN Model")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--dummy-data", action="store_true", help="Use dummy data for testing the pipeline")
    
    args = parser.parse_args()
    main(args)
