"""
Congestion Detection Service - Rule-based traffic congestion analysis.

Không cần train model - sử dụng motion detection và optical flow
để phân tích tình trạng kẹt xe từ camera images.

Tốc độ: ~50-100ms per frame trên CPU
Độ chính xác: ~70-80% (tương đối)
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("trafficflow.congestion")


@dataclass
class CongestionMetrics:
    """Metrics extracted from frame analysis."""

    motion_ratio: float = 0.0  # % pixels changed (high = moving)
    flow_speed: float = 0.0  # avg optical flow (high = flowing)
    edge_density: float = 0.0  # edge ratio (high = many vehicles)
    vehicle_score: float = 0.0  # horizontal motion ratio
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CongestionResult:
    """Final congestion analysis result."""

    level: int  # 0-3: free, moderate, heavy, severe
    level_name: str  # Vietnamese name
    color: str  # Hex color code
    emoji: str  # Visual indicator
    description: str  # Detailed description
    confidence: float  # 0.0-1.0
    metrics: CongestionMetrics
    is_stable: bool  # True if result is reliable
    is_error: bool = False  # True if analysis failed
    error_message: str = ""


class CongestionDetector:
    """
    Rule-based traffic congestion detector.

    Sử dụng các kỹ thuật:
    1. Motion Detection - phát hiện chuyển động
    2. Optical Flow - đo tốc độ di chuyển
    3. Edge Density - mật độ đường biên (tương quan với số xe)
    """

    # Thresholds cho các mức kẹt xe
    LEVELS = {
        0: {
            "name": "Thông thoáng",
            "color": "#22c55e",
            "emoji": "🟢",
            "description": "Giao thông thông thoáng, xe di chuyển bình thường",
        },
        1: {
            "name": "Đông vừa",
            "color": "#eab308",
            "emoji": "🟡",
            "description": "Xe di chuyển chậm, một số đoạn đông vừa",
        },
        2: {
            "name": "Kẹt xe",
            "color": "#f97316",
            "emoji": "🟠",
            "description": "Nhiều điểm kẹt, thời gian di chuyển tăng đáng kể",
        },
        3: {
            "name": "Kẹt cứng",
            "color": "#ef4444",
            "emoji": "🔴",
            "description": "Kẹt cứng, gần như đứng yên hoặc di chuyển rất chậm",
        },
    }

    def __init__(
        self,
        # Motion thresholds
        motion_threshold: float = 0.02,
        # Scoring weights
        motion_weight: float = 0.40,
        flow_weight: float = 0.30,
        vehicle_weight: float = 0.30,
        # Processing settings
        resize_width: int = 320,
        resize_height: int = 240,
        # Stability settings
        min_frames_for_stable: int = 3,
        max_frame_buffer: int = 20,
    ):
        self.motion_threshold = motion_threshold
        self.motion_weight = motion_weight
        self.flow_weight = flow_weight
        self.vehicle_weight = vehicle_weight

        # Image processing settings
        self.resize_width = resize_width
        self.resize_height = resize_height

        # Buffer cho temporal analysis
        self.min_frames_for_stable = min_frames_for_stable
        self.max_frame_buffer = max_frame_buffer
        self._frame_buffer: deque = deque(maxlen=max_frame_buffer)

        # Previous frame for optical flow
        self._prev_gray: Optional[np.ndarray] = None

        # Stats
        self.total_processed = 0
        self.total_errors = 0

    def analyze_frame(self, frame: np.ndarray) -> CongestionResult:
        """
        Phân tích một frame đơn lẻ.

        Args:
            frame: BGR image from OpenCV (H, W, 3)

        Returns:
            CongestionResult với metrics và level
        """
        try:
            # Resize for faster processing
            frame_resized = cv2.resize(frame, (self.resize_width, self.resize_height))

            # Convert to grayscale
            gray = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)

            metrics = CongestionMetrics()

            # 1. Calculate metrics
            if self._prev_gray is not None:
                # Motion detection
                metrics.motion_ratio = self._calculate_motion_ratio(
                    gray, self._prev_gray
                )

                # Optical flow
                metrics.flow_speed, _ = self._calculate_optical_flow(
                    gray, self._prev_gray
                )

                # Vehicle-like motion
                metrics.vehicle_score = self._analyze_vehicle_motion(
                    gray, self._prev_gray
                )

            # Edge density (không cần previous frame)
            metrics.edge_density = self._calculate_edge_density(gray)

            # Update previous frame
            self._prev_gray = gray.copy()

            # Add to buffer
            self._frame_buffer.append(metrics)

            # 2. Determine congestion level
            level, confidence = self._compute_congestion_level(metrics)

            # 3. Check stability
            is_stable = len(self._frame_buffer) >= self.min_frames_for_stable

            # Override with sequence analysis if we have enough frames
            if is_stable:
                level, confidence = self._analyze_sequence_stable()

            level_info = self.LEVELS[level]

            self.total_processed += 1

            return CongestionResult(
                level=level,
                level_name=level_info["name"],
                color=level_info["color"],
                emoji=level_info["emoji"],
                description=level_info["description"],
                confidence=confidence,
                metrics=metrics,
                is_stable=is_stable,
            )

        except Exception as e:
            self.total_errors += 1
            logger.warning(f"[analyze_frame] Error: {e}")
            return CongestionResult(
                level=1,  # Default to moderate on error
                level_name=self.LEVELS[1]["name"],
                color=self.LEVELS[1]["color"],
                emoji=self.LEVELS[1]["emoji"],
                description="Không thể phân tích hình ảnh",
                confidence=0.0,
                metrics=CongestionMetrics(),
                is_stable=False,
                is_error=True,
                error_message=str(e),
            )

    def _calculate_motion_ratio(
        self, current: np.ndarray, previous: np.ndarray
    ) -> float:
        """Tính tỷ lệ pixels thay đổi."""
        diff = cv2.absdiff(current, previous)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        motion_ratio = np.sum(thresh > 0) / thresh.size
        return float(motion_ratio)

    def _calculate_optical_flow(
        self, current: np.ndarray, previous: np.ndarray
    ) -> tuple:
        """
        Tính optical flow sử dụng Farneback algorithm.
        Returns: (avg_speed, dominant_direction)
        """
        flow = cv2.calcOpticalFlowFarneback(
            previous,
            current,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )

        # Magnitude
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        magnitude[magnitude < 0.5] = 0

        avg_speed = (
            float(np.mean(magnitude[magnitude > 0])) if np.any(magnitude > 0) else 0.0
        )

        return avg_speed, "N/A"

    def _calculate_edge_density(self, gray: np.ndarray) -> float:
        """Tính mật độ edges (đại diện cho số lượng xe)."""
        edges = cv2.Canny(gray, 50, 150)
        density = np.sum(edges > 0) / edges.size
        return float(density)

    def _analyze_vehicle_motion(
        self, current: np.ndarray, previous: np.ndarray
    ) -> float:
        """Phân tích chuyển động horizontal (xe di chuyển ngang)."""
        flow = cv2.calcOpticalFlowFarneback(
            previous,
            current,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )

        h_flow = np.abs(flow[..., 0])
        h_flow[h_flow < 0.5] = 0

        score = np.sum(h_flow > 2) / h_flow.size
        return float(score)

    def _compute_congestion_level(self, metrics: CongestionMetrics) -> tuple:
        """
        Tính mức kẹt xe từ metrics.

        Scoring:
        - Motion cao + Flow cao + Vehicle score cao = Thông thoáng (level 0)
        - Motion thấp + Flow thấp + Vehicle score thấp = Kẹt (level 3)
        """
        # Normalize metrics
        motion_score = min(metrics.motion_ratio / 0.15, 1.0)
        flow_score = min(metrics.flow_speed / 15.0, 1.0)
        vehicle_score = min(metrics.vehicle_score / 0.3, 1.0)

        # Weighted average
        score = (
            self.motion_weight * motion_score
            + self.flow_weight * flow_score
            + self.vehicle_weight * vehicle_score
        )

        # Map score to level
        if score >= 0.70:
            level = 0  # Free
        elif score >= 0.40:
            level = 1  # Moderate
        elif score >= 0.20:
            level = 2  # Heavy
        else:
            level = 3  # Severe

        # Confidence = how "clear" the signal is
        confidence = min(score * 1.5, 1.0) if level < 3 else min((1 - score) * 1.5, 1.0)

        return level, round(confidence, 2)

    def _analyze_sequence_stable(self) -> tuple:
        """
        Phân tích sequence để có kết quả ổn định hơn.
        Sử dụng majority voting và trend analysis.
        """
        if len(self._frame_buffer) < self.min_frames_for_stable:
            return 1, 0.5

        levels = []
        for m in list(self._frame_buffer)[-self.min_frames_for_stable :]:
            level, _ = self._compute_congestion_level(m)
            levels.append(level)

        # Majority voting
        level = max(set(levels), key=levels.count)

        # Check trend
        first_half = np.mean(levels[: len(levels) // 2])
        second_half = np.mean(levels[len(levels) // 2 :])
        trend = second_half - first_half

        # Adjust confidence
        consistency = levels.count(level) / len(levels)
        confidence = consistency

        # If trend is worsening significantly, increase level
        if trend > 0.5:
            level = min(level + 1, 3)
            confidence *= 0.8

        return level, round(confidence, 2)

    def reset(self):
        """Reset buffer và state."""
        self._frame_buffer.clear()
        self._prev_gray = None

    @property
    def stats(self) -> dict:
        """Return processing statistics."""
        return {
            "total_processed": self.total_processed,
            "total_errors": self.total_errors,
            "error_rate": self.total_errors / max(self.total_processed, 1),
            "buffer_size": len(self._frame_buffer),
        }


class CameraCongestionMonitor:
    """
    Monitor congestion cho multiple cameras.

    - Lưu frame buffers riêng cho mỗi camera
    - Xử lý camera errors riêng biệt
    - Tự động reset khi camera offline quá lâu
    """

    def __init__(
        self,
        max_buffer_per_camera: int = 20,
        offline_timeout_seconds: int = 300,  # 5 phút
        stale_frame_seconds: int = 60,  # Frame cũ > 1 phút = stale
    ):
        self.max_buffer_per_camera = max_buffer_per_camera
        self.offline_timeout = offline_timeout_seconds
        self.stale_frame_seconds = stale_frame_seconds

        # Per-camera state
        self._detectors: dict[str, CongestionDetector] = {}
        self._last_frame_time: dict[str, datetime] = {}
        self._error_count: dict[str, int] = {}
        self._max_errors_before_stale = 5

        # Stats
        self.total_cameras_tracked = 0
        self.total_frames_processed = 0

    def get_detector(self, camera_id: str) -> CongestionDetector:
        """Get or create detector cho camera."""
        if camera_id not in self._detectors:
            self._detectors[camera_id] = CongestionDetector(
                max_frame_buffer=self.max_buffer_per_camera
            )
            self._error_count[camera_id] = 0
            self.total_cameras_tracked += 1
            logger.info(f"[get_detector] Created new detector for camera: {camera_id}")
        return self._detectors[camera_id]

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        frame_timestamp: Optional[datetime] = None,
    ) -> CongestionResult:
        """
        Process frame từ camera.

        Args:
            camera_id: Camera identifier
            frame: BGR image
            frame_timestamp: Timestamp của frame (None = now)

        Returns:
            CongestionResult
        """
        timestamp = frame_timestamp or datetime.now()

        detector = self.get_detector(camera_id)

        # Check if camera was offline
        if camera_id in self._last_frame_time:
            time_since_last = (
                timestamp - self._last_frame_time[camera_id]
            ).total_seconds()
            if time_since_last > self.offline_timeout:
                logger.info(
                    f"[process_frame] Camera {camera_id} reconnected after {time_since_last:.0f}s"
                )
                detector.reset()  # Reset buffer vì frames không liên tục

        # Process frame
        result = detector.analyze_frame(frame)

        # Update state
        self._last_frame_time[camera_id] = timestamp
        self.total_frames_processed += 1

        if result.is_error:
            self._error_count[camera_id] = self._error_count.get(camera_id, 0) + 1
        else:
            self._error_count[camera_id] = 0

        return result

    def process_image_bytes(
        self, camera_id: str, image_bytes: bytes
    ) -> CongestionResult:
        """
        Process image từ bytes.

        Args:
            camera_id: Camera identifier
            image_bytes: Raw image bytes

        Returns:
            CongestionResult
        """
        try:
            # Decode image
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                raise ValueError("Failed to decode image")

            return self.process_frame(camera_id, frame)

        except Exception as e:
            logger.warning(f"[process_image_bytes] Error for {camera_id}: {e}")

            # Track error
            self._error_count[camera_id] = self._error_count.get(camera_id, 0) + 1

            # Return error result
            return CongestionResult(
                level=1,
                level_name="Không xác định",
                color="#9ca3af",
                emoji="⚪",
                description="Lỗi xử lý hình ảnh: " + str(e),
                confidence=0.0,
                metrics=CongestionMetrics(),
                is_stable=False,
                is_error=True,
                error_message=str(e),
            )

    def get_all_congestion(self) -> dict[str, dict]:
        """
        Lấy tình trạng kẹt xe hiện tại cho tất cả cameras.

        Returns:
            Dict mapping camera_id -> congestion info
        """
        result = {}

        for camera_id, detector in self._detectors.items():
            if len(detector._frame_buffer) > 0:
                latest = detector._frame_buffer[-1]
                level, _ = detector._compute_congestion_level(latest)
                level_info = CongestionDetector.LEVELS[level]

                result[camera_id] = {
                    "level": level,
                    "level_name": level_info["name"],
                    "color": level_info["color"],
                    "emoji": level_info["emoji"],
                    "last_update": self._last_frame_time.get(camera_id),
                    "is_stale": self._is_camera_stale(camera_id),
                }

        return result

    def _is_camera_stale(self, camera_id: str) -> bool:
        """Kiểm tra camera có stale không (offline hoặc too many errors)."""
        if self._error_count.get(camera_id, 0) >= self._max_errors_before_stale:
            return True

        if camera_id in self._last_frame_time:
            time_since = (
                datetime.now() - self._last_frame_time[camera_id]
            ).total_seconds()
            return time_since > self.stale_frame_seconds

        return True

    def get_camera_status(self, camera_id: str) -> dict:
        """Get detailed status cho một camera."""
        is_stale = self._is_camera_stale(camera_id)
        error_count = self._error_count.get(camera_id, 0)
        last_update = self._last_frame_time.get(camera_id)

        detector = self._detectors.get(camera_id)
        buffer_size = len(detector._frame_buffer) if detector else 0

        return {
            "camera_id": camera_id,
            "is_online": not is_stale,
            "is_stale": is_stale,
            "error_count": error_count,
            "last_update": last_update.isoformat() if last_update else None,
            "buffer_size": buffer_size,
            "has_enough_data": buffer_size >= 3,
        }

    @property
    def stats(self) -> dict:
        """Return overall statistics."""
        return {
            "total_cameras_tracked": self.total_cameras_tracked,
            "total_frames_processed": self.total_frames_processed,
            "total_errors": sum(self._error_count.values()),
            "stale_cameras": sum(
                1 for cam_id in self._detectors.keys() if self._is_camera_stale(cam_id)
            ),
        }


# Global instance
_congestion_monitor: Optional[CameraCongestionMonitor] = None


def get_congestion_monitor() -> CameraCongestionMonitor:
    """Get singleton congestion monitor instance."""
    global _congestion_monitor
    if _congestion_monitor is None:
        _congestion_monitor = CameraCongestionMonitor()
    return _congestion_monitor


def reset_congestion_monitor():
    """Reset global congestion monitor."""
    global _congestion_monitor
    _congestion_monitor = None
