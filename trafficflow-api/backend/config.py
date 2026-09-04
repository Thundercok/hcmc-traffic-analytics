import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "TrafficFlow API"
    app_version: str = "0.2.0-beta"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # ZIP Model (Vehicle Counting)
    zip_model_path: str = os.path.join(
        os.path.dirname(__file__),
        "..",
        "ZIP",
        "checkpoints",
        "demo_data",
        "best_mae_0_quantized.onnx",
    )
    zip_model_device: str = "cpu"  # "cuda" or "cpu"
    zip_input_size: int = 320
    vehicle_split_motorbike_ratio: float = 0.7

    # Flood Severity Prediction Model (EfficientNet-B0)
    flood_model_path: str = os.path.join(
        os.path.dirname(__file__),
        "models",
        "flood_model.pth",
    )
    flood_model_device: str = "cpu"
    flood_input_size: int = 224
    flood_confidence_gate: float = 0.65

    # Congestion Detection (Rule-based, no training)
    congestion_enabled: bool = True
    congestion_min_frames_stable: int = 3
    congestion_max_buffer: int = 20
    congestion_offline_timeout: int = 300  # seconds
    congestion_resize_width: int = 320
    congestion_resize_height: int = 240

    # Security
    api_key: str = ""
    max_upload_bytes: int = 10 * 1024 * 1024
    pil_max_pixels: int = 25_000_000
    ssl_verify: bool = True  # SSL certificate verification for camera fetching

    # Camera source
    camera_base_url: str = (
        "https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx"
    )
    camera_fetch_timeout: int = 10

    # Background writer and historical data
    writer_interval_seconds: int = 15
    writer_batch_size: int = 100
    data_retention_minutes: int = 7 * 24 * 60
    camera_offline_skip_minutes: int = 30

    # Forecasting and data deficiency handling
    forecast_history_minutes: int = 7 * 24 * 60
    forecast_min_history_points: int = 12
    data_coverage_window_hours: int = 24

    # CORS
    cors_origins: list[str] = ["*"]

    model_config = {"env_prefix": "TF_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
