import torch
import sys
import os

sys.path.append(os.getcwd())

from models import get_model
from losses import QuadLoss
from datasets.utils import generate_density_map

def test_setup():
    print("Testing Multi-class Setup...")
    
    print("\n[1] Initializing Model (EBC with 2 classes)...")
    try:
        # Dummy bins for initialization
        bins = [(0.0, 0.5), (0.5, 1.0)]
        bin_centers = [0.25, 0.75]
        
        model = get_model(
            model_info_path="dummy_info.pth",
            model_name="vgg19",
            block_size=32,
            bins=bins,
            bin_centers=bin_centers,
            zero_inflated=True,
            num_classes=2,
            input_size=128
        )
        print("Model initialized successfully.")
    except Exception as e:
        print(f"FAILED to initialize model: {e}")
        return

    print("\n[2] Testing Forward Pass...")
    try:
        # Batch size 2, 3 channels, 128x128 image
        dummy_input = torch.randn(2, 3, 128, 128)
        
        # Forward
        if model.training:
             outputs = model(dummy_input)
             # Expected outputs for zero_inflated=True:
             # logit_pi (B, C, 2, H, W), logit_maps (B, C, nbins, H, W), lambda (B, C, 1, H, W), den (B, C, H, W)
             print(f"Forward pass successful.")
             print(f"Output shapes:")
             print(f"  Logit PI: {outputs[0].shape}")
             print(f"  Logit Maps: {outputs[1].shape}")
             print(f"  Lambda: {outputs[2].shape}")
             print(f"  Density Map: {outputs[3].shape}")
             
             pred_den_map = outputs[3]
             assert pred_den_map.shape == (2, 2, 4, 4) # 128/32 = 4
        else:
             pred_den_map = model(dummy_input)
             print(f"Inference output shape: {pred_den_map.shape}")

    except Exception as e:
        print(f"FAILED forward pass: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n[3] Testing Loss Function (QuadLoss)...")
    try:
        loss_fn = QuadLoss(
            input_size=128,
            block_size=32,
            bins=bins,
            reg_loss="zipnll",
            aux_loss="none",
            weight_cls=1.0,
            weight_reg=1.0
        )
        
        # Dummy GT
        # GT density map shape: (B, C, H_block, W_block)
        gt_den_map = torch.abs(torch.randn(2, 2, 4, 4)) 
        
        # Dummy Points (List of List of Tensors? No, code expects List[Tensor] for B images)
        # But for multi-class, we discussed QuadLoss limitation.
        # if it runs with simple dummy points (len=B)
        gt_points = [torch.randn(10, 2), torch.randn(5, 2)] 
        
        loss, loss_info = loss_fn(
            pred_logit_map=outputs[1],
            pred_den_map=outputs[3],
            gt_den_map=gt_den_map,
            gt_points=gt_points,
            pred_logit_pi_map=outputs[0],
            pred_lambda_map=outputs[2]
        )
        
        print(f"Loss calculation successful. Total Loss: {loss.item()}")
        print(f"Loss Info keys: {loss_info.keys()}")
        
    except Exception as e:
        print(f"FAILED loss calculation: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n[4] Testing Dataset Utils (generate_density_map)...")
    try:
        # Label with class info: (x, y, class)
        label = torch.tensor([
            [10, 10, 0],
            [20, 20, 1],
            [30, 30, 0]
        ], dtype=torch.float32)
        
        den_map = generate_density_map(label, height=100, width=100, num_classes=2)
        print(f"Density map shape: {den_map.shape}")
        assert den_map.shape == (2, 100, 100)
        assert den_map[0].sum() == 2.0
        assert den_map[1].sum() == 1.0
        print("Density map generation correct.")
        
    except Exception as e:
        print(f"FAILED dataset utils: {e}")
        return

    print("\nALL TESTS PASSED!")

if __name__ == "__main__":
    test_setup()
