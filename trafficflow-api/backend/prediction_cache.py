import logging
import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger("trafficflow.cache")


class PredictionCache:
    """Singleton in-memory prediction history store."""

    _instance: Optional["PredictionCache"] = None

    def __init__(self, max_per_camera: int = 60):
        self._data: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_per_camera))
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "PredictionCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record(self, camera_id: str, result: dict) -> None:
        """[record] Store a prediction result for a camera."""
        with self._lock:
            self._data[camera_id].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "total_count": result.get("total_count", 0),
                    "car_count": result.get("car_count", 0),
                    "motorbike_count": result.get("motorbike_count", 0),
                    "density_level": result.get("density_level", "low"),
                    "inference_time_ms": result.get("inference_time_ms", 0),
                }
            )

    def get_history(self, camera_id: str) -> list[dict]:
        """[get_history] Return prediction history for a camera (oldest first)."""
        with self._lock:
            return list(self._data.get(camera_id, []))

    def get_latest(self, camera_id: str) -> dict | None:
        """[get_latest] Return the most recent prediction, or None."""
        with self._lock:
            history = self._data.get(camera_id)
            return dict(history[-1]) if history else None
