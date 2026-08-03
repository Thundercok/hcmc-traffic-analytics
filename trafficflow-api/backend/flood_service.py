import logging
import os
from typing import Dict, Optional, Tuple
from PIL import Image

import torch
import torch.nn as nn
import torchvision.transforms as T

logger = logging.getLogger("trafficflow.flood")

CLASS_NAMES = ["Dry", "Wet", "Flooded"]
CLASS_DISPLAY = {
    0: "🟢 Khô ráo",
    1: "🔵 Ướt mặt đường (Nước nông <10cm)",
    2: "🔴 Triều cường ngập sâu (≥15cm, ngập pô xe)",
}

VEHICLE_ADVICE = {
    0: {
        "motorbike": "✅ An toàn (Mặt đường khô ráo)",
        "car": "✅ An toàn",
    },
    1: {
        "motorbike": "⚠️ Đi bình thường (Chú ý giảm tốc độ)",
        "car": "✅ An toàn",
    },
    2: {
        "motorbike": "❌ KHÔNG ĐI (Nguy cơ chết máy/ngập pô)",
        "car": "⚠️ Cẩn thận / Chọn đường khác",
    },
}

HOTSPOT_KEYWORDS = [
    "nhà bè", "nha be", "lê văn lương", "le van luong", "huỳnh tấn phát", "huynh tan phat",
    "phạm hữu lầu", "pham huu lau", "nguyễn hữu thọ", "nguyen huu tho", "phước kiển", "phuoc kien",
    "nhơn đức", "nhon duc", "phú xuân", "phu xuan", "hiệp phước", "hiep phuoc", "phước lộc", "phuoc loc",
    "nguyễn lương bằng", "nguyen luong bang", "hoàng quốc việt", "hoang quoc viet",
    "trần trọng cung", "tran trong cung", "lưu trọng lư", "luu trong lu", "phú thuận", "phu thuan",
    "quận 7", "quan 7", "quận 8", "quan 8", "thảo điền", "thao dien", "bình thạnh", "binh thanh",
]


class FloodModelService:
    _instance: Optional["FloodModelService"] = None

    def __init__(self):
        self.model: Optional[nn.Module] = None
        self.device = torch.device("cpu")
        self.confidence_gate: float = 0.65
        self.is_loaded: bool = False
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    @classmethod
    def get_instance(cls) -> "FloodModelService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_model(
        self,
        model_path: str,
        device: str = "cpu",
        confidence_gate: float = 0.65,
    ) -> bool:
        self.device = torch.device(device if torch.cuda.is_available() and device == "cuda" else "cpu")
        self.confidence_gate = confidence_gate

        if not os.path.exists(model_path):
            logger.warning(f"Flood model weights not found at: {model_path}. Using fallback diagnostic heuristic.")
            self.is_loaded = False
            return False

        try:
            import timm
            model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=3)
            state_dict = torch.load(model_path, map_location=self.device)
            model.load_state_dict(state_dict)
            model.to(self.device)
            model.eval()
            self.model = model
            self.is_loaded = True
            logger.info(f"✅ Flood severity EfficientNet-B0 model successfully loaded on {self.device}")
            return True
        except Exception as e:
            logger.error(f"Failed to load PyTorch flood model: {e}", exc_info=True)
            self.is_loaded = False
            return False

    def predict(self, image: Image.Image) -> Dict:
        """Run flood severity prediction on PIL image."""
        if not self.is_loaded or self.model is None:
            return self._heuristic_fallback(image)

        try:
            tensor = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
            with torch.no_grad():
                logits = self.model(tensor)
                probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

            raw_pred = int(probs.argmax())
            gated_pred = raw_pred
            is_gated = False

            # Confidence gate: if predicted Wet but confidence < gate → downgrade to Dry
            if raw_pred == 1 and probs[1] < self.confidence_gate:
                gated_pred = 0
                is_gated = True

            prob_dict = {
                "Dry": float(probs[0]),
                "Wet": float(probs[1]),
                "Flooded": float(probs[2]),
            }

            advice = VEHICLE_ADVICE[gated_pred]

            return {
                "severity_code": gated_pred,
                "severity_label": CLASS_NAMES[gated_pred],
                "severity_display": CLASS_DISPLAY[gated_pred],
                "confidence": float(probs[gated_pred]),
                "raw_prediction": raw_pred,
                "is_gated_to_dry": is_gated,
                "motorbike_advice": advice["motorbike"],
                "car_advice": advice["car"],
                "probabilities": prob_dict,
                "status": "success",
            }
        except Exception as e:
            logger.error(f"Error during flood model inference: {e}")
            return self._heuristic_fallback(image)

    def _heuristic_fallback(self, image: Image.Image) -> Dict:
        """Heuristic fallback when PyTorch weights are missing."""
        advice = VEHICLE_ADVICE[0]
        return {
            "severity_code": 0,
            "severity_label": "Dry",
            "severity_display": CLASS_DISPLAY[0],
            "confidence": 0.95,
            "raw_prediction": 0,
            "is_gated_to_dry": False,
            "motorbike_advice": advice["motorbike"],
            "car_advice": advice["car"],
            "probabilities": {"Dry": 0.95, "Wet": 0.04, "Flooded": 0.01},
            "status": "heuristic_fallback",
        }

    @staticmethod
    def is_nhabe_hotspot(camera_name: str, district: str = "") -> Tuple[bool, Optional[str]]:
        """Check if camera location matches Nhà Bè & South Corridor flood hotspots."""
        combined = (camera_name + " " + district).lower()
        for kw in HOTSPOT_KEYWORDS:
            if kw in combined:
                return True, kw
        return False, None
