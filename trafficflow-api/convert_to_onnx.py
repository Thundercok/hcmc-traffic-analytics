import os
import sys
import argparse
import subprocess

# Sửa lỗi Unicode trên Windows Terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Đảm bảo cài đặt các thư viện cần thiết cho quá trình chuyển đổi ONNX
def install_requirements():
    print("[INFO] Đang kiểm tra thư viện ONNX...")
    try:
        import onnx
        import onnxruntime
        import onnxscript
    except ImportError:
        print("[PROCESS] Cài đặt onnx, onnxruntime và onnxscript...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "onnx", "onnxruntime", "onnxscript"]
        )
        import onnx
        import onnxruntime
        import onnxscript

        print("[SUCCESS] Đã cài đặt xong.")


install_requirements()

import torch
from onnxruntime.quantization import quantize_dynamic, QuantType
import logging

# Thiết lập đường dẫn để import models
ZIP_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "ZIP"))
if ZIP_PROJECT_ROOT not in sys.path:
    sys.path.insert(0, ZIP_PROJECT_ROOT)

try:
    from models import get_model
except ImportError as e:
    print(f"[ERROR] Không thể nạp module models: {e}")
    sys.exit(1)


def convert_to_onnx(model_path, output_path, input_size=448):
    print(f"\n[INFO] BẮT ĐẦU QUÁ TRÌNH CHUYỂN ĐỔI ONNX")
    print(f"[INFO] Nguồn PyTorch: {model_path}")

    if not os.path.exists(model_path):
        print(f"[ERROR] Không tìm thấy file model: {model_path}")
        return None

    # 1. Tải mô hình PyTorch
    print("[PROCESS] Đang tải mô hình PyTorch lên RAM...")
    model = get_model(model_info_path=model_path)
    model.eval()
    model.to("cpu")
    print("[SUCCESS] Tải mô hình thành công.")

    # 2. Tạo Dummy Input (Ảnh giả lập)
    print(
        f"[INFO] Kích thước đầu vào (Input Shape): [1, 3, {input_size}, {input_size}]"
    )
    dummy_input = torch.randn(1, 3, input_size, input_size)

    # 3. Xuất sang định dạng ONNX Float32
    print("[PROCESS] Đang Compile và Export sang ONNX (Float32)...")
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=18,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
    )
    print(f"[SUCCESS] Đã xuất file ONNX gốc (Float32): {output_path}")
    print(f"[INFO] Dung lượng: {os.path.getsize(output_path) / (1024*1024):.2f} MB")

    return output_path


def quantize_onnx(onnx_path, quantized_path):
    print("\n[INFO] BẮT ĐẦU LƯỢNG TỬ HOÁ (QUANTIZATION INT8)")
    print("[INFO] Quá trình này giúp mô hình nhẹ hơn x4 lần và tối ưu cho CPU.")

    try:
        quantize_dynamic(
            model_input=onnx_path,
            model_output=quantized_path,
            weight_type=QuantType.QUInt8,
        )
        print(f"[SUCCESS] Đã tạo file ONNX Quantized (INT8): {quantized_path}")
        print(
            f"[INFO] Dung lượng mới: {os.path.getsize(quantized_path) / (1024*1024):.2f} MB"
        )
        print(
            "[INFO] Có thể sử dụng file này để deploy lên Hugging Face hoặc thiết bị biên."
        )
    except Exception as e:
        print(f"[ERROR] Lỗi khi lượng tử hoá: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Chuyển đổi PyTorch Model sang ONNX và Quantize INT8"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="ZIP/checkpoints/demo_data/best_mae_0.pth",
        help="Đường dẫn file .pth gốc",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=448,
        help="Kích thước input_size (ví dụ: 448 hoặc 320)",
    )
    args = parser.parse_args()

    # Tạo tên file ONNX đầu ra
    base_name = os.path.splitext(args.model)[0]
    onnx_fp32_path = f"{base_name}.onnx"
    onnx_int8_path = f"{base_name}_quantized.onnx"

    # Chạy quy trình
    exported_onnx = convert_to_onnx(args.model, onnx_fp32_path, args.size)
    if exported_onnx:
        quantize_onnx(exported_onnx, onnx_int8_path)
