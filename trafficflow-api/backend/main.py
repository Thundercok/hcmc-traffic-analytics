import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import router, start_debug_scheduler, stop_debug_scheduler
from .model_service import ZIPModelService
from .flood_service import FloodModelService
from .prediction_writer import start_writer, stop_writer
from .database import init_db_pool, close_db_pool, init_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("trafficflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_path = os.path.normpath(settings.zip_model_path)
    logger.info(f"[startup] Model path: {model_path}")
    logger.info(f"[startup] Model exists: {os.path.exists(model_path)}")

    if os.path.exists(model_path):
        try:
            svc = ZIPModelService.get_instance()
            svc.load_model(
                model_path=model_path,
                device=settings.zip_model_device,
                input_size=settings.zip_input_size,
            )
            logger.info("[startup] - ZIP Model loaded. Server ready for predictions.")
        except Exception as e:
            logger.error(f"[startup] Failed to load ZIP model: {e}", exc_info=True)
            logger.warning("[startup] Server will start without ZIP model.")
    else:
        logger.warning(
            f"[startup] - ZIP Model file not found at {model_path}. "
            "Predictions will fail until a model is loaded."
        )

    # Initialize Flood Severity Model Service (EfficientNet-B0)
    flood_path = os.path.normpath(settings.flood_model_path)
    try:
        f_svc = FloodModelService.get_instance()
        f_svc.load_model(
            model_path=flood_path,
            device=settings.flood_model_device,
            confidence_gate=settings.flood_confidence_gate,
        )
        logger.info(f"[startup] - Flood Severity Model Service initialized (path: {flood_path}).")
    except Exception as e:
        logger.warning(f"[startup] - Flood model service failed to initialize: {e}")

    # Setup HTTP client
    transport = httpx.AsyncHTTPTransport(retries=5)
    app.state.http_client = httpx.AsyncClient(
        transport=transport,
        timeout=settings.camera_fetch_timeout,
        verify=settings.ssl_verify,
        follow_redirects=True,
    )
    logger.info("[startup] - Shared HTTP client created.")

    # Initialize Database pool and schema on startup
    try:
        await init_db_pool()
        await init_schema()
        logger.info("[startup] - Database pool and schema initialized.")
    except Exception as db_err:
        logger.error(f"[startup] - Database initialization failed: {db_err}", exc_info=True)

    # Start prediction writer - continuous recording every 15 seconds
    # Set WRITER_INTERVAL_SECONDS=0 to disable, or set custom interval
    writer_interval = int(os.getenv("WRITER_INTERVAL_SECONDS", "15"))
    if writer_interval > 0:
        try:
            app.state.writer = await start_writer(interval_seconds=writer_interval)
            logger.info(
                f"[startup] - Prediction writer started (interval: {writer_interval}s)"
            )
        except Exception as e:
            logger.warning(f"[startup] - Prediction writer failed to start: {e}")
            logger.warning("[startup] - Forecasting features will be unavailable.")

    # Start periodic background analytics caching loop
    try:
        start_debug_scheduler(app)
        logger.info("[startup] - Debug analytics scheduler started.")
    except Exception as e:
        logger.warning(f"[startup] - Debug analytics scheduler failed to start: {e}")

    yield

    # Stop debug analytics scheduler
    try:
        stop_debug_scheduler()
        logger.info("[shutdown] - Debug analytics scheduler stopped.")
    except Exception as e:
        logger.warning(f"[shutdown] - Failed to stop debug analytics scheduler: {e}")

    # Cleanup prediction writer
    if hasattr(app.state, "writer"):
        await stop_writer()

    # Cleanup http client
    await app.state.http_client.aclose()
    
    # Close database pool
    try:
        await close_db_pool()
        logger.info("[shutdown] - Database pool closed.")
    except Exception as db_err:
        logger.warning(f"[shutdown] - Failed to close database pool: {db_err}")

    logger.info("[shutdown] Cleaned up resources.")



app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "**TrafficFlow API** — Backend cho ứng dụng dự đoán giao thông TP.HCM.\n\n"
        "Sử dụng model **ZIP (Zero-Inflated Poisson)** để đếm số lượng phương tiện "
        "từ hình ảnh camera giao thông thời gian thực.\n\n"
        "### Endpoints chính:\n"
        "- `POST /api/predict` — Upload ảnh → dự đoán số lượng\n"
        "- `GET /api/predict/camera/{id}` — Lấy ảnh camera live → dự đoán\n"
        "- `GET /api/cameras` — Danh sách camera\n"
        "- `GET /api/health` — Kiểm tra trạng thái hệ thống\n"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "TrafficFlow API",
            "description": "Các endpoint dự đoán giao thông và quản lý camera.",
        }
    ],
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
