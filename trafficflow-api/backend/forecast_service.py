"""
Traffic prediction service using historical data.
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np

logger = logging.getLogger("trafficflow.forecast")


class TrafficForecaster:
    """
    Simple traffic prediction using weighted moving average and trend detection.
    """

    def __init__(self):
        self.history_minutes = 30
        self.forecast_horizons = [15, 30, 60]  # minutes ahead
        self._db_available = None
        self._pool = None

    def _compute_weights(self, n: int) -> np.ndarray:
        """Compute exponentially decaying weights for recent observations."""
        if n == 0:
            return np.array([])
        weights = np.exp(-np.linspace(-1, 0, n))
        return weights / weights.sum()

    def _detect_trend(self, counts: list) -> float:
        """Detect trend direction: positive = increasing, negative = decreasing."""
        if len(counts) < 2:
            return 0.0

        # Simple linear regression slope
        x = np.arange(len(counts))
        if len(counts) > 1:
            slope = np.polyfit(x, counts, 1)[0]
            return float(slope)
        return 0.0

    def _get_time_features(self, timestamp: datetime) -> dict:
        """Extract time-based features for better prediction."""
        hour = timestamp.hour
        day_of_week = timestamp.weekday()  # 0=Monday, 6=Sunday

        # Rush hour indicators
        is_morning_rush = 7 <= hour <= 9
        is_evening_rush = 17 <= hour <= 19
        is_weekend = day_of_week >= 5

        return {
            "hour": hour,
            "day_of_week": day_of_week,
            "is_morning_rush": is_morning_rush,
            "is_evening_rush": is_evening_rush,
            "is_weekend": is_weekend,
        }

    async def predict(self, camera_id: str) -> Optional[dict]:
        """
        Predict traffic for next 15, 30, 60 minutes based on 30min history.

        Returns:
            dict with forecasts and confidence scores, or None if not enough data
        """
        from .database import get_camera_history

        history = await get_camera_history(camera_id, minutes=self.history_minutes)

        if len(history) < 3:
            logger.warning(
                f"[predict] Not enough history for {camera_id}: {len(history)} records"
            )
            return None

        # Extract counts
        counts = [h["total_count"] for h in history]
        timestamps = [h["timestamp"] for h in history]

        # Compute weighted moving average
        weights = self._compute_weights(len(counts))
        wma = float(np.average(counts, weights=weights))

        # Detect trend
        trend = self._detect_trend(counts)

        # Time features
        time_features = self._get_time_features(datetime.now())

        # Generate forecasts
        forecasts = []
        for horizon in self.forecast_horizons:
            # Prediction: weighted average + trend adjustment
            # Trend impact decreases as we go further into future
            trend_factor = 0.3 * (horizon / 60)  # 15min=0.075, 30min=0.15, 60min=0.3

            base_prediction = max(0, wma + (trend * trend_factor))

            # Confidence decreases with horizon
            confidence = max(0.3, 0.95 - (horizon / 200))

            # Determine density level
            if base_prediction < 10:
                level = "low"
            elif base_prediction < 30:
                level = "moderate"
            elif base_prediction < 60:
                level = "heavy"
            else:
                level = "severe"

            forecasts.append(
                {
                    "horizon_minutes": horizon,
                    "predicted_count": round(base_prediction),
                    "confidence": round(confidence, 2),
                    "density_level": level,
                    "trend": (
                        "increasing"
                        if trend > 0.5
                        else "decreasing" if trend < -0.5 else "stable"
                    ),
                }
            )

        # Current status
        current_count = counts[0]
        if current_count < 10:
            current_level = "low"
        elif current_count < 30:
            current_level = "moderate"
        elif current_count < 60:
            current_level = "heavy"
        else:
            current_level = "severe"

        result = {
            "camera_id": camera_id,
            "timestamp": datetime.now(),
            "history_points": len(history),
            "current": {
                "count": current_count,
                "density_level": current_level,
            },
            "statistics": {
                "weighted_avg_30min": round(wma, 1),
                "trend_per_sample": round(trend, 2),
                "min_30min": min(counts),
                "max_30min": max(counts),
            },
            "forecasts": forecasts,
            "time_features": time_features,
        }

        logger.info(
            f"[predict] {camera_id}: current={current_count}, "
            f"trend={trend:.2f}, 15min={forecasts[0]['predicted_count']}"
        )

        return result


# Singleton instance
_forecaster: Optional[TrafficForecaster] = None


def get_forecaster() -> TrafficForecaster:
    """Get or create forecaster instance."""
    global _forecaster
    if _forecaster is None:
        _forecaster = TrafficForecaster()
    return _forecaster
