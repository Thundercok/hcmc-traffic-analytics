import logging
import os
import sys
import time
import cv2
import base64
from io import BytesIO
from typing import Optional

import numpy as np
import torch

torch.set_num_threads(2)

from PIL import Image
from torchvision import transforms
from .config import settings

Image.MAX_IMAGE_PIXELS = settings.pil_max_pixels

logger = logging.getLogger("trafficflow.model")

ZIP_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "ZIP")
)
if ZIP_PROJECT_ROOT not in sys.path:
    sys.path.insert(0, ZIP_PROJECT_ROOT)


class ZIPModelService:
    """
    Service cho ZIP model inference (vehicle counting).

    Features:
    - Singleton pattern
    - ONNX/CPU optimized inference
    - Built-in error handling
    - Congestion detection integration
    """

    _instance: Optional["ZIPModelService"] = None

    def __init__(self):
        self.model = None
        self.device = None
        self.input_size = 448
        self._loaded = False
        self.is_onnx = False

        # Congestion detector - lazy loaded
        self._congestion_detector = None

        # Error tracking
        self.total_inferences = 0
        self.failed_inferences = 0

    @classmethod
    def get_instance(cls) -> "ZIPModelService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_model(self, model_path: str, device: str = "cpu", input_size: int = 448):
        """[load_model] Load ZIP model from checkpoint."""
        if self._loaded:
            logger.info("[load_model] Model already loaded, skipping.")
            return

        self.device = torch.device(device)
        self.input_size = input_size

        logger.info(f"[load_model] Loading ZIP model from: {model_path}")
        logger.info(f"[load_model] Device: {self.device}, Input size: {input_size}")

        try:
            if model_path.endswith(".onnx"):
                import onnxruntime as ort

                logger.info("[load_model] Auto-activating ONNX Runtime")

                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = 2
                sess_options.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )

                self.model = ort.InferenceSession(
                    model_path,
                    sess_options=sess_options,
                    providers=["CPUExecutionProvider"],
                )
                self.is_onnx = True
                self._loaded = True
                logger.info("[load_model] - ONNX model loaded successfully.")
            else:
                from models import get_model

                self.model = get_model(model_info_path=model_path)
                self.model.to(self.device)
                self.model.eval()
                self.is_onnx = False
                self._loaded = True

            if hasattr(self.model, "config"):
                logger.info(
                    f"[load_model] Model config: {self.model.config.get('model_name', 'unknown')}"
                )
                logger.info(
                    f"[load_model] Block size: {self.model.config.get('block_size', '?')}"
                )
                logger.info(
                    f"[load_model] Zero-inflated: {self.model.config.get('zero_inflated', '?')}"
                )

            logger.info("[load_model] - Model loaded successfully.")

        except Exception as e:
            logger.error(f"[load_model] - Failed to load model: {e}", exc_info=True)
            raise

    @property
    def congestion_detector(self):
        """Lazy load congestion detector."""
        if self._congestion_detector is None:
            from .congestion_detector import get_congestion_monitor

            self._congestion_detector = get_congestion_monitor()
            logger.info("[congestion] Congestion detector initialized")
        return self._congestion_detector

    def _preprocess_image(self, image: Image.Image) -> torch.Tensor:
        """[_preprocess_image] Preprocess a PIL Image for inference."""
        transform = transforms.Compose(
            [
                transforms.Resize((self.input_size, self.input_size)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )
        tensor = transform(image).unsqueeze(0)  # (1, 3, H, W)
        return tensor.to(self.device)

    def _generate_heatmap_base64(
        self,
        density_tensor,
        roi_polygon: Optional[list] = None,
        roi_congestion_level: Optional[str] = None,
        original_image: Optional[Image.Image] = None,
    ) -> str:
        # Convert (1, num_classes, H, W) or (1, 1, H, W) or (H, W) to (H, W)
        if density_tensor.ndim == 4:
            if density_tensor.shape[1] > 1:
                den = density_tensor.sum(dim=1).squeeze(0).squeeze(0).numpy()
            else:
                den = density_tensor.squeeze(0).squeeze(0).numpy()
        elif density_tensor.ndim == 3:
            den = density_tensor.squeeze(0).numpy()
        else:
            den = density_tensor.numpy()

        if den.ndim == 3:
            den = den[0]

        # Convert PIL original image to BGR numpy array if provided
        bgr_img = None
        if original_image is not None:
            bgr_img = cv2.cvtColor(np.array(original_image), cv2.COLOR_RGB2BGR)
            h, w = bgr_img.shape[:2]
            den = cv2.resize(den, (w, h), interpolation=cv2.INTER_CUBIC)
        else:
            h, w = den.shape[:2]

        # Normalize density values for colormap projection
        den = np.maximum(den, 0)
        max_den = den.max()
        if max_den > 0:
            norm_den = den / max_den
        else:
            norm_den = den

        norm_map = (norm_den * 255).astype(np.uint8)
        color_map = cv2.applyColorMap(norm_map, cv2.COLORMAP_JET)

        if bgr_img is not None:
            # Create alpha transparency mask from normalized density
            # Scale alpha so even lower density displays clearly, but cap at 0.65 to keep background visible
            alpha = np.minimum(norm_den * 1.5, 0.65)
            alpha = np.expand_dims(alpha, axis=2)
            # Blend: blended = alpha * colormap + (1 - alpha) * original_image
            color_map = (alpha * color_map + (1.0 - alpha) * bgr_img).astype(np.uint8)

        # Draw ROI polygon if provided
        if roi_polygon:
            h, w = color_map.shape[:2]
            pts = np.array(
                [[pt[0] * w, pt[1] * h] for pt in roi_polygon], dtype=np.int32
            )
            # Match colors with density level
            colors = {
                "low": (0, 255, 0),
                "moderate": (0, 180, 255),
                "heavy": (0, 0, 255),
                "severe": (0, 0, 150),
            }
            color = colors.get(roi_congestion_level, (255, 255, 255))

            # Semitransparent fill
            overlay = color_map.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, 0.25, color_map, 0.75, 0, dst=color_map)
            # Solid border
            cv2.polylines(
                color_map,
                [pts],
                isClosed=True,
                color=color,
                thickness=2,
                lineType=cv2.LINE_AA,
            )

        _, buffer = cv2.imencode(".png", color_map)
        return "data:image/png;base64," + base64.b64encode(buffer).decode("utf-8")

    def _normalize_density_tensor(self, model_out) -> torch.Tensor | None:
        """Extract a CPU density tensor with shape (1, C, H, W) when available."""
        if isinstance(model_out, torch.Tensor) and model_out.ndim == 4:
            return model_out.detach().cpu()

        if isinstance(model_out, dict):
            for key in ["pred_den_map", "pred_density", "density_map"]:
                if key not in model_out:
                    continue
                value = model_out[key]
                try:
                    den = value.detach().cpu()
                except AttributeError:
                    den = torch.tensor(value)
                if den.ndim == 2:
                    den = den.unsqueeze(0).unsqueeze(0)
                elif den.ndim == 3:
                    den = den.unsqueeze(0)
                return den if den.ndim == 4 else None

        return None

    def _build_roi_mask(
        self, roi_polygon: Optional[list[list[float]]], height: int, width: int
    ) -> tuple[np.ndarray | None, float]:
        if not roi_polygon or len(roi_polygon) < 3:
            return None, 0.0

        points = []
        for point in roi_polygon:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return None, 0.0
            try:
                x = min(1.0, max(0.0, float(point[0])))
                y = min(1.0, max(0.0, float(point[1])))
            except (TypeError, ValueError):
                return None, 0.0
            points.append([round(x * (width - 1)), round(y * (height - 1))])

        pts = np.array(points, dtype=np.int32)
        mask = np.zeros((height, width), dtype=np.float32)
        cv2.fillPoly(mask, [pts], 1.0)
        area_ratio = float(mask.sum() / mask.size)
        if area_ratio < 0.001:
            return None, 0.0
        return mask, area_ratio

    def _classify_congestion_score(self, score: float) -> str:
        if score < 12.0:
            return "low"
        if score < 35.0:
            return "moderate"
        if score < 60.0:
            return "heavy"
        return "severe"

    def _validate_image(self, image_bytes: bytes) -> tuple[bool, str]:
        """
        Validate image bytes.

        Returns:
            (is_valid, error_message)
        """
        if len(image_bytes) < 100:
            return False, "Image too small"

        # Check magic bytes
        magic_jpeg = b"\xff\xd8"
        magic_png = b"\x89PNG"

        if not (image_bytes[:2] == magic_jpeg or image_bytes[:4] == magic_png):
            return False, "Invalid image format"

        return True, ""

    def _is_likely_error_image(self, image_bytes: bytes) -> bool:
        """
        Kiểm tra xem ảnh có phải là ảnh lỗi (blank, error page, etc.) không.

        Heuristics:
        - Very small file (< 5KB)
        - Uniform color (mostly same pixels)
        - Error text detection (simple check)
        """
        # Size check
        if len(image_bytes) < 5000:
            return True

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if img is None:
                return True

            # Check uniformity (blank image = error)
            mean_val = np.mean(img)
            std_val = np.std(img)

            if std_val < 5:  # Nearly uniform
                return True

            # Check if mostly black or mostly white
            black_ratio = np.sum(img < 10) / img.size
            white_ratio = np.sum(img > 245) / img.size

            if black_ratio > 0.9 or white_ratio > 0.9:
                return True

            return False

        except Exception:
            return True

    def predict_from_image(
        self,
        image: Image.Image,
        return_heatmap: bool = False,
        roi_polygon: Optional[list[list[float]]] = None,
    ) -> dict:
        """
        [predict_from_image] Run inference on a PIL Image with optional ROI.
        """
        if not self._loaded:
            raise RuntimeError("Model is not loaded. Call load_model() first.")

        start_time = time.time()

        image_rgb = image.convert("RGB")
        tensor = self._preprocess_image(image_rgb)

        with torch.no_grad():
            if self.is_onnx:
                ort_inputs = {self.model.get_inputs()[0].name: tensor.cpu().numpy()}
                ort_outs = self.model.run(None, ort_inputs)
                model_out = torch.tensor(ort_outs[0])
            else:
                model_out = self.model(tensor)

        inference_time_ms = round((time.time() - start_time) * 1000, 1)

        den = self._normalize_density_tensor(model_out)
        car_count = 0
        motorbike_count = 0
        total_count = 0

        if den is not None:
            num_classes = den.shape[1]

            if num_classes >= 2:
                class_counts = den.sum(dim=(2, 3)).squeeze(0)
                car_count = max(0, round(float(class_counts[0].item())))
                motorbike_count = max(0, round(float(class_counts[1].item())))
                total_count = car_count + motorbike_count
                logger.debug(
                    f"[predict_from_image] Multi-class output: "
                    f"raw_car={float(class_counts[0]):.2f}, raw_bike={float(class_counts[1]):.2f}"
                )
            else:
                total_count = max(0, round(float(den.sum().item())))

        elif hasattr(model_out, "sum"):
            total_count = max(0, round(float(model_out.sum().item())))

        if total_count > 0 and car_count == 0 and motorbike_count == 0:
            ratio = getattr(settings, "vehicle_split_motorbike_ratio", 0.7)
            motorbike_count = int(round(total_count * ratio))
            car_count = total_count - motorbike_count

        # ROI processing
        roi_count = None
        roi_car_count = None
        roi_motorbike_count = None
        roi_congestion_level = None
        roi_area_ratio = None
        has_roi = False

        roi_density_score = None

        if roi_polygon and den is not None:
            h, w = den.shape[2], den.shape[3]
            mask, roi_area_ratio = self._build_roi_mask(roi_polygon, h, w)

            if mask is not None:
                has_roi = True
                mask_tensor = torch.tensor(mask, dtype=den.dtype)
                num_classes = den.shape[1]
                if num_classes >= 2:
                    roi_car_raw = float((den[0, 0] * mask_tensor).sum().item())
                    roi_bike_raw = float((den[0, 1] * mask_tensor).sum().item())
                    roi_car_count = max(0, round(roi_car_raw))
                    roi_motorbike_count = max(0, round(roi_bike_raw))
                    roi_count = roi_car_count + roi_motorbike_count
                else:
                    roi_count_raw = float((den[0, 0] * mask_tensor).sum().item())
                    roi_count = max(0, round(roi_count_raw))
                    ratio = getattr(settings, "vehicle_split_motorbike_ratio", 0.7)
                    roi_motorbike_count = int(round(roi_count * ratio))
                    roi_car_count = roi_count - roi_motorbike_count

                # Calculate active heatmap intersection with road segment
                total_den = den[0].sum(dim=0)
                active_heatmap = (total_den > 0.2).to(dtype=den.dtype)
                intersection = active_heatmap * mask_tensor
                
                road_pixels = float(mask_tensor.sum().item())
                intersection_pixels = float(intersection.sum().item())
                
                coverage_percentage = (intersection_pixels / road_pixels * 100) if road_pixels > 0 else 0.0
                roi_density_score = round(coverage_percentage, 1)
                
                # Classify based on coverage percentage
                if coverage_percentage < 15.0:
                    roi_congestion_level = "low"
                elif coverage_percentage < 40.0:
                    roi_congestion_level = "moderate"
                elif coverage_percentage < 70.0:
                    roi_congestion_level = "heavy"
                else:
                    roi_congestion_level = "severe"

        # Classify density level (fallback or global)
        if total_count < 10:
            density_level = "low"
        elif total_count < 30:
            density_level = "moderate"
        elif total_count < 60:
            density_level = "heavy"
        else:
            density_level = "severe"

        # If ROI is present, use ROI density level as the main density level
        effective_density_level = (
            roi_congestion_level if has_roi else density_level
        )

        logger.info(
            f"[predict_from_image] Total: {total_count}, ROI: {roi_count} (Car: {roi_car_count}, Bike: {roi_motorbike_count}), Level: {effective_density_level}, Time: {inference_time_ms}ms"
        )

        result = {
            "total_count": total_count,
            "car_count": int(car_count),
            "motorbike_count": int(motorbike_count),
            "density_level": effective_density_level,
            "global_density_level": density_level,
            "inference_time_ms": inference_time_ms,
            "has_roi": has_roi,
            "roi_count": roi_count,
            "roi_car_count": roi_car_count,
            "roi_motorbike_count": roi_motorbike_count,
            "roi_congestion_level": roi_congestion_level,
            "roi_area_ratio": roi_area_ratio,
            "roi_density_score": roi_density_score,
        }

        if return_heatmap and den is not None:
            try:
                result["heatmap_base64"] = self._generate_heatmap_base64(
                    den, roi_polygon, roi_congestion_level, original_image=image_rgb
                )
            except Exception as e:
                logger.warning(f"Failed to generate heatmap: {e}")

        return result

    def predict_from_bytes(
        self,
        image_bytes: bytes,
        return_heatmap: bool = False,
        skip_error_check: bool = False,
        roi_polygon: Optional[list[list[float]]] = None,
    ) -> dict:
        """
        [predict_from_bytes] Run inference from raw image bytes with optional ROI.
        """
        self.total_inferences += 1

        # Validate image
        is_valid, error_msg = self._validate_image(image_bytes)
        if not is_valid:
            self.failed_inferences += 1
            logger.warning(f"[predict_from_bytes] Invalid image: {error_msg}")
            return {
                "total_count": 0,
                "car_count": 0,
                "motorbike_count": 0,
                "density_level": "unknown",
                "inference_time_ms": 0,
                "is_error_image": True,
                "error_message": f"Invalid image: {error_msg}",
            }

        # Check for error/blank images (unless skipped)
        if not skip_error_check and self._is_likely_error_image(image_bytes):
            logger.warning("[predict_from_bytes] Detected likely error/blank image")
            return {
                "total_count": 0,
                "car_count": 0,
                "motorbike_count": 0,
                "density_level": "unknown",
                "inference_time_ms": 0,
                "is_error_image": True,
                "error_message": "Likely error or blank image from camera",
            }

        try:
            image = Image.open(BytesIO(image_bytes))
            return self.predict_from_image(
                image, return_heatmap=return_heatmap, roi_polygon=roi_polygon
            )
        except Exception as e:
            self.failed_inferences += 1
            logger.error(f"[predict_from_bytes] Inference failed: {e}")
            return {
                "total_count": 0,
                "car_count": 0,
                "motorbike_count": 0,
                "density_level": "error",
                "inference_time_ms": 0,
                "is_error_image": True,
                "error_message": str(e),
            }

    def detect_congestion(self, camera_id: str, image_bytes: bytes) -> dict:
        """
        [detect_congestion] Run rule-based congestion detection on camera image.

        Args:
            camera_id: Camera identifier
            image_bytes: Raw image bytes

        Returns:
            dict with congestion analysis results
        """
        monitor = self.congestion_detector
        result = monitor.process_image_bytes(camera_id, image_bytes)

        return {
            "camera_id": camera_id,
            "level": result.level,
            "level_name": result.level_name,
            "color": result.color,
            "emoji": result.emoji,
            "description": result.description,
            "confidence": result.confidence,
            "is_stable": result.is_stable,
            "is_error": result.is_error,
            "error_message": result.error_message if result.is_error else None,
            "metrics": {
                "motion_ratio": result.metrics.motion_ratio,
                "flow_speed": result.metrics.flow_speed,
                "edge_density": result.metrics.edge_density,
                "vehicle_score": result.metrics.vehicle_score,
            },
        }

    def get_all_congestion(self) -> dict:
        """[get_all_congestion] Get congestion status for all monitored cameras."""
        return self.congestion_detector.get_all_congestion()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def model_info(self) -> dict:
        """[model_info] Return model metadata."""
        if not self._loaded:
            return {"status": "not_loaded"}

        config = getattr(self.model, "config", {})

        # Congestion stats
        congestion_stats = {}
        if self._congestion_detector:
            congestion_stats = self._congestion_detector.stats

        return {
            "status": "loaded",
            "model_name": config.get("model_name", "unknown"),
            "block_size": config.get("block_size", None),
            "zero_inflated": config.get("zero_inflated", None),
            "input_size": self.input_size,
            "device": str(self.device),
            "total_inferences": self.total_inferences,
            "failed_inferences": self.failed_inferences,
            "failure_rate": self.failed_inferences / max(self.total_inferences, 1),
            "congestion_stats": congestion_stats,
        }
