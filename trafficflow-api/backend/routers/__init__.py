from datetime import datetime
from fastapi import APIRouter

from ..schemas import HealthResponse, ModelStatus
from ..model_service import ZIPModelService
from ..config import settings

from .cameras import router as cameras_router
from .predict import router as predict_router
from .congestion import router as congestion_router
from .weather import router as weather_router
from .debug import router as debug_router
from .debug import start_debug_scheduler, stop_debug_scheduler

# Core router for TrafficFlow API
router = APIRouter(prefix="/api", tags=["TrafficFlow API"])

# Define app-wide health check endpoint
@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns the application status and model loading state.",
)
async def health_check():
    """[health_check] Returns app health and model status."""
    svc = ZIPModelService.get_instance()
    model_info = svc.model_info

    return HealthResponse(
        app=settings.app_name,
        version=settings.app_version,
        model=ModelStatus(**model_info),
        timestamp=datetime.now(),
    )

# Include all sub-routers
router.include_router(cameras_router)
router.include_router(predict_router)
router.include_router(congestion_router)
router.include_router(weather_router)
router.include_router(debug_router)
