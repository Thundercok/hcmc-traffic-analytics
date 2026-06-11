import logging
from fastapi import APIRouter, HTTPException, Query
from ..schemas import WeatherReportCreate, WeatherReportResponse

logger = logging.getLogger("trafficflow.routers.weather")
router = APIRouter()


@router.post(
    "/weather/report",
    response_model=WeatherReportResponse,
    summary="Submit a Crowdsourced Weather Report",
    description="Allows users to submit a real-time weather report (rain, flooding, sun) for their location."
)
async def submit_weather_report(payload: WeatherReportCreate):
    """[submit_weather_report] Create and store a new crowdsourced weather report."""
    from ..database import create_weather_report
    try:
        report = await create_weather_report(
            lat=payload.lat,
            lng=payload.lng,
            weather_state=payload.weather_state,
            rain_intensity=payload.rain_intensity,
            flood_depth_cm=payload.flood_depth_cm,
            reporter_name=payload.reporter_name,
            notes=payload.notes
        )
        return report
    except Exception as e:
        logger.error(f"Failed to save weather report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get(
    "/weather/reports",
    response_model=list[WeatherReportResponse],
    summary="Get Active Weather Reports",
    description="Retrieve all crowdsourced weather reports submitted in the last N hours."
)
async def get_weather_reports(hours: int = Query(4, ge=1, le=24)):
    """[get_weather_reports] Get active weather reports."""
    from ..database import get_active_weather_reports
    try:
        reports = await get_active_weather_reports(hours_limit=hours)
        return reports
    except Exception as e:
        logger.error(f"Failed to fetch weather reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
