import sys
import os
import unittest
from fastapi.testclient import TestClient

# Setup path so backend is importable
backend_path = "/Users/thundercock2/Documents/Github/nckh-traffic-camera/trafficflow-api"
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from backend.main import app
from backend.model_service import ZIPModelService
from backend.config import settings

class TestRoiLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("Setting up test class...")
        settings.zip_model_path = "/Users/thundercock2/Documents/Github/nckh-traffic-camera/trafficflow-api/ZIP/checkpoints/demo_data/best_mae_0_quantized.onnx"
        
        # Initialize model
        svc = ZIPModelService.get_instance()
        svc.load_model(settings.zip_model_path, device="cpu", input_size=settings.zip_input_size)
        cls.client = TestClient(app)
        print("Test setup complete.")

    def test_predict_camera_with_db_roi(self):
        # Trần Quang Khải - Trần Khắc Chân (We saved an ROI for this in DB earlier)
        camera_id = "662b86c41afb9c00172dd31c"
        print(f"Testing GET /api/predict/camera/{camera_id}...")
        
        with TestClient(app) as client:
            response = client.get(f"/api/predict/camera/{camera_id}?heatmap=true")
            self.assertEqual(response.status_code, 200, f"Failed with status: {response.status_code}")
            
            data = response.json()
            print(f"API Response keys: {data.keys()}")
            self.assertIn("prediction", data)
            
            pred = data["prediction"]
            print(f"Prediction: {pred}")
        
        # Verify that ROI logic was applied
        self.assertTrue(pred["has_roi"], "Should have ROI applied from database")
        self.assertIsNotNone(pred["roi_count"], "roi_count should not be None")
        self.assertIsNotNone(pred["roi_density_score"], "roi_density_score should not be None")
        self.assertIsNotNone(pred["roi_congestion_level"], "roi_congestion_level should not be None")
        
        # Verify roi_density_score represents coverage percentage (0.0 to 100.0)
        score = pred["roi_density_score"]
        self.assertTrue(0.0 <= score <= 100.0, f"roi_density_score {score} is not a valid percentage")
        print(f"Success! Detected ROI coverage percentage: {score}%")
        
        # Verify mapping logic
        level = pred["roi_congestion_level"]
        self.assertIn(level, ["low", "moderate", "heavy", "severe"], f"Invalid level: {level}")
        print(f"Success! Classified ROI congestion level: {level}")

if __name__ == "__main__":
    unittest.main()
