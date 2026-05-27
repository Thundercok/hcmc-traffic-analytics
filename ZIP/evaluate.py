import torch
from torch.amp import autocast
import torch.nn.functional as F
import torch.distributed as dist
from torch import nn, Tensor
from torch.utils.data import DataLoader
from typing import Tuple, Optional
from tqdm import tqdm
import numpy as np

from utils import sliding_window_predict, barrier, calculate_errors


def evaluate(
    model: nn.Module,
    data_loader: DataLoader,
    sliding_window: bool,
    max_input_size: int = 4096,
    window_size: int = 224,
    stride: int = 224,
    max_num_windows: int = 64,
    device: torch.device = torch.device("cuda"),
    amp: bool = False,
    local_rank: int = 0,
    nprocs: int = 1,
    progress_bar: bool = True,
) -> Tuple[Tensor, Tensor]:
    ddp = nprocs > 1
    model = model.to(device)
    model.eval()
    pred_counts, gt_counts = [], []
    data_iter = tqdm(data_loader) if (local_rank == 0 and progress_bar) else data_loader

    # Lists to store (B, C) counts
    pred_counts_list = []
    gt_counts_list = []

    for image, _, gt_densities in data_iter:
        image = image.to(device)
        gt_densities = gt_densities.to(device) # Shape (B, C, H, W)
        
        # Calculate GT counts per class
        # gt_densities shape: (B, C, H, W) -> sum over H, W -> (B, C)
        gt_counts_batch = gt_densities.sum(dim=(-1, -2)) 
        gt_counts_list.append(gt_counts_batch.cpu())

        image_height, image_width = image.shape[-2:]
        
        # Resize image if it's smaller than the window size
        aspect_ratio = image_width / image_height
        if image_height < window_size:
            new_height = window_size
            new_width = int(new_height * aspect_ratio)
            image = F.interpolate(image, size=(new_height, new_width), mode="bicubic", align_corners=False)
            image_height, image_width = new_height, new_width
        if image_width < window_size:
            new_width = window_size
            new_height = int(new_width / aspect_ratio)
            image = F.interpolate(image, size=(new_height, new_width), mode="bicubic", align_corners=False)
            image_height, image_width = new_height, new_width

        with torch.set_grad_enabled(False), autocast(device_type="cuda", enabled=amp):
            if sliding_window or (image_height * image_width) > max_input_size ** 2:
                # Assuming sliding_window_predict handles multi-class output correctly (B, C, H, W)
                pred_den_maps = sliding_window_predict(model, image, window_size, stride, max_num_windows)
            else:
                pred_den_maps = model(image)
            
            # pred_den_maps shape (B, C, H, W) -> sum to (B, C)
            pred_counts_batch = pred_den_maps.sum(dim=(-1, -2))
            pred_counts_list.append(pred_counts_batch.cpu())
    
    barrier(ddp)
    
    # Concatenate all batches: (Total_Samples, C)
    pred_counts = torch.cat(pred_counts_list, dim=0)
    gt_counts = torch.cat(gt_counts_list, dim=0)
    
    assert len(pred_counts) == len(gt_counts), f"Length mismatch: {len(pred_counts)} vs {len(gt_counts)}"

    if ddp:
        pred_counts = pred_counts.to(device)
        gt_counts = gt_counts.to(device)
        
        # Gather all results
        # We need to gather (N, C) tensors.
        local_count = torch.tensor([pred_counts.shape[0]], device=device)
        count_list = [torch.zeros_like(local_count) for _ in range(nprocs)]
        dist.all_gather(count_list, local_count)
        max_len = max([c.item() for c in count_list])
        
        num_classes = pred_counts.shape[1]
        
        # Pad with NaNs
        padded_pred = torch.full((max_len, num_classes), float("nan"), device=device)
        padded_gt = torch.full((max_len, num_classes), float("nan"), device=device)
        
        padded_pred[:pred_counts.shape[0]] = pred_counts
        padded_gt[:gt_counts.shape[0]] = gt_counts
        
        gathered_pred = [torch.zeros_like(padded_pred) for _ in range(nprocs)]
        gathered_gt = [torch.zeros_like(padded_gt) for _ in range(nprocs)]
        
        dist.all_gather(gathered_pred, padded_pred)
        dist.all_gather(gathered_gt, padded_gt)
        
        pred_counts = torch.cat(gathered_pred, dim=0).cpu()
        gt_counts = torch.cat(gathered_gt, dim=0).cpu()
        
        # Remove NaNs (checking one column is enough)
        mask = ~torch.isnan(pred_counts[:, 0])
        pred_counts = pred_counts[mask]
        gt_counts = gt_counts[mask]
        
        pred_counts = pred_counts.numpy()
        gt_counts = gt_counts.numpy()
    else:
        pred_counts = pred_counts.numpy()
        gt_counts = gt_counts.numpy()

    torch.cuda.empty_cache()
    
    # Calculate errors for each class and total
    errors = {}
    num_classes = pred_counts.shape[1]
    
    # Per-class errors
    for c in range(num_classes):
        class_errs = calculate_errors(pred_counts[:, c], gt_counts[:, c])
        for k, v in class_errs.items():
            errors[f"{k}_class_{c}"] = v
            
    # Total count errors (sum of all classes)
    total_pred = pred_counts.sum(axis=1)
    total_gt = gt_counts.sum(axis=1)
    total_errs = calculate_errors(total_pred, total_gt)
    errors.update(total_errs)
    
    return errors
