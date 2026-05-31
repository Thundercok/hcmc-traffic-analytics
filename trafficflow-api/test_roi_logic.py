import sys
import os
import unittest
from fastapi.testclient import TestClient

# Setup path so backend is importable
backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from backend.main import app
from backend.model_service import ZIPModelService
from backend.config import settings

class TestRoiLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("Setting up test class...")
        settings.zip_model_path = os.path.join(backend_path, "ZIP", "checkpoints", "demo_data", "best_mae_0_quantized.onnx")
        
        # Initialize model
        svc = ZIPModelService.get_instance()
        svc.load_model(settings.zip_model_path, device="cpu", input_size=settings.zip_input_size)
        cls.client_ctx = TestClient(app)
        cls.client = cls.client_ctx.__enter__()
        print("Test setup complete.")

    @classmethod
    def tearDownClass(cls):
        print("Tearing down test class...")
        cls.client_ctx.__exit__(None, None, None)
        svc = ZIPModelService.get_instance()
        svc.model = None
        svc._loaded = False
        import gc
        gc.collect()
        print("Test teardown complete.")
        # Force clean exit to prevent ONNX/C++ runtime crash on teardown
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    def test_predict_camera_with_db_roi(self):
        # Trần Quang Khải - Trần Khắc Chân
        camera_id = "662b86c41afb9c00172dd31c"
        print(f"Testing GET /api/predict/camera/{camera_id}...")
        
        roi_polygon = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        
        # Hermetic setup: save ROI to database first
        save_response = self.client.post(
            f"/api/cameras/{camera_id}/roi",
            json={"roi_polygon": roi_polygon}
        )
        self.assertEqual(save_response.status_code, 200, f"Failed to save ROI: {save_response.text}")
        
        response = self.client.get(f"/api/predict/camera/{camera_id}?heatmap=true")
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
