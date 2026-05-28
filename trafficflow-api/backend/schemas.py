from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CameraInfo(BaseModel):
    """Schema for a traffic camera."""

    id: str = Field(..., description="Camera ID from HCMC traffic system")
    name: str = Field(..., description="Camera location name")
    district: str = Field(..., description="District name")
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")


class CameraListResponse(BaseModel):
    """Response for GET /api/cameras."""

    cameras: list[CameraInfo]
    total: int


class PredictionResult(BaseModel):
    """Core prediction output from the ZIP model."""

    total_count: int = Field(
        ..., description="Predicted total number of vehicles/people"
    )
    car_count: int = Field(..., description="Predicted number of cars (automobiles)")
    motorbike_count: int = Field(..., description="Predicted number of motorbikes")
    density_level: str = Field(
        ..., description="Traffic density level: low, moderate, heavy, severe"
    )
    global_density_level: Optional[str] = Field(
        None, description="Traffic density level for the full image"
    )
    inference_time_ms: float = Field(
        ..., description="Model inference time in milliseconds"
    )
    heatmap_base64: Optional[str] = Field(
        None, description="Base64 encoded PNG of the density heatmap"
    )

    # Optional ROI specific fields
    roi_count: Optional[int] = Field(
        None, description="Predicted number of vehicles inside the road segment ROI"
    )
    roi_car_count: Optional[int] = Field(
        None, description="Predicted number of cars inside the road segment ROI"
    )
    roi_motorbike_count: Optional[int] = Field(
        None, description="Predicted number of motorbikes inside the road segment ROI"
    )
    roi_congestion_level: Optional[str] = Field(
        None, description="Congestion level within the ROI: low, moderate, heavy, severe"
    )
    roi_area_ratio: Optional[float] = Field(
        None, description="Area ratio of the ROI relative to the full image"
    )
    roi_density_score: Optional[float] = Field(
        None,
        description="ROI congestion score calculated as vehicle count divided by ROI area ratio",
    )
    has_roi: bool = Field(
        False, description="Whether an ROI was used for this prediction"
    )


class PredictionMeta(BaseModel):
    """Metadata about the prediction."""

    model: str = Field(default="ZIP-demo_data", description="Model name")
    device: str = Field(default="cpu", description="Inference device")
    input_size: int = Field(default=448, description="Input image size used")


class PredictResponse(BaseModel):
    """Response for POST /api/predict and GET /api/predict/camera/{id}."""

    camera_id: Optional[str] = Field(
        None, description="Camera ID if from camera endpoint"
    )
    camera_name: Optional[str] = Field(None, description="Camera location name")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Prediction timestamp"
    )
    prediction: PredictionResult
    metadata: PredictionMeta


class ModelStatus(BaseModel):
    """Model status info."""

    status: str
    model_name: Optional[str] = None
    block_size: Optional[int] = None
    zero_inflated: Optional[bool] = None
    input_size: Optional[int] = None
    device: Optional[str] = None


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    app: str
    version: str
    model: ModelStatus
    timestamp: datetime = Field(default_factory=datetime.now)


class BatchPredictRequest(BaseModel):
    """Request body for POST /api/predict/batch."""

    camera_ids: list[str] = Field(
        default=[], description="Specific camera IDs to predict (max 30)"
    )
    district: Optional[str] = Field(
        None, description="Predict all cameras in this district"
    )


class BatchPredictionItem(BaseModel):
    """One camera's prediction result within a batch."""

    camera_id: str
    camera_name: str
    district: str
    lat: float
    lng: float
    prediction: PredictionResult


class BatchPredictResponse(BaseModel):
    """Response for POST /api/predict/batch."""

    predictions: list[BatchPredictionItem]
    total: int = Field(..., description="Total cameras attempted")
    succeeded: int
    failed: int
    total_time_ms: float


class PredictionHistoryEntry(BaseModel):
    """Single history entry for trend charts."""

    timestamp: str
    total_count: int
    car_count: int
    motorbike_count: int
    density_level: str


class PredictionHistoryResponse(BaseModel):
    """Response for GET /api/predict/camera/{id}/history."""

    camera_id: str
    camera_name: Optional[str] = None
    history: list[PredictionHistoryEntry]
    total: int


# ============================================================
# CONGESTION DETECTION SCHEMAS (Rule-based, no training)
# ============================================================


class CongestionMetricsSchema(BaseModel):
    """Metrics from congestion analysis."""

    motion_ratio: float = Field(..., description="Motion pixel ratio (0-1)")
    flow_speed: float = Field(..., description="Average optical flow speed")
    edge_density: float = Field(..., description="Edge pixel ratio")
    vehicle_score: float = Field(..., description="Horizontal vehicle-like motion")


class CongestionResponse(BaseModel):
    """Response for congestion detection endpoint."""

    camera_id: str
    camera_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    # Congestion info
    level: int = Field(
        ..., description="Congestion level: 0=free, 1=moderate, 2=heavy, 3=severe"
    )
    level_name: str = Field(..., description="Vietnamese level name")
    color: str = Field(..., description="Hex color code")
    emoji: str = Field(..., description="Visual emoji indicator")
    description: str = Field(..., description="Detailed description")

    # Confidence & reliability
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Prediction confidence (0-1)"
    )
    is_stable: bool = Field(
        ..., description="True if result is based on multiple frames"
    )
    is_error: bool = Field(default=False, description="True if analysis had errors")
    error_message: Optional[str] = Field(
        None, description="Error message if analysis failed"
    )

    # Raw metrics
    metrics: CongestionMetricsSchema


class CongestionMapResponse(BaseModel):
    """Response for GET /api/congestion/map."""

    updated_at: datetime = Field(default_factory=datetime.now)
    total_cameras: int = Field(..., description="Total cameras being monitored")
    stale_cameras: int = Field(
        ..., description="Cameras that are offline or have errors"
    )

    cameras: dict[str, dict] = Field(
        ..., description="Camera ID -> congestion info mapping"
    )

    summary: dict = Field(..., description="Summary statistics")
    # summary keys: total, free, moderate, heavy, severe, average_level, overall_status


class CameraCongestionHistoryResponse(BaseModel):
    """Response for GET /api/congestion/camera/{id}/history."""

    camera_id: str
    camera_name: Optional[str] = None
    current_level: int
    current_level_name: str
    current_color: str
    trend: str = Field(..., description="Traffic trend: improving, stable, worsening")

    history: list[dict] = Field(..., description="Recent congestion history")
    stats: dict = Field(..., description="Camera-specific statistics")


class SystemCongestionStatsResponse(BaseModel):
    """Response for GET /api/congestion/stats."""

    total_cameras_tracked: int
    total_frames_processed: int
    total_errors: int
    stale_cameras: int

    detectors: list[dict] = Field(
        default_factory=list, description="Per-detector statistics"
    )


# ============================================================
# FORECAST SCHEMAS (Prediction using historical data)
# ============================================================


class ForecastItem(BaseModel):
    """Single forecast point."""

    horizon_minutes: int = Field(..., description="Minutes ahead")
    predicted_count: int = Field(..., description="Predicted vehicle count")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")
    density_level: str = Field(..., description="Predicted density level")
    trend: str = Field(..., description="Traffic trend: increasing, stable, decreasing")


class CurrentStatus(BaseModel):
    """Current traffic status."""

    count: int
    density_level: str


class Statistics(BaseModel):
    """30-minute statistics."""

    weighted_avg_30min: float
    trend_per_sample: float
    min_30min: int
    max_30min: int


class TimeFeatures(BaseModel):
    """Time-based features."""

    hour: int
    day_of_week: int
    is_morning_rush: bool
    is_evening_rush: bool
    is_weekend: bool


class ForecastResponse(BaseModel):
    """Response for GET /api/forecast/{camera_id}."""

    camera_id: str
    timestamp: datetime
    history_points: int = Field(..., description="Number of history points used")
    current: CurrentStatus
    statistics: Statistics
    forecasts: list[ForecastItem]
    time_features: TimeFeatures


class CameraRoiRequest(BaseModel):
    """Request schema for setting a camera's ROI."""

    roi_polygon: list[list[float]] = Field(..., description="List of normalized [x, y] coordinates")


class CameraRoiResponse(BaseModel):
    """Response schema for getting a camera's ROI."""

    camera_id: str
    roi_polygon: Optional[list[list[float]]] = Field(None, description="List of normalized [x, y] coordinates")
