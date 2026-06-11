import sys
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Setup path so backend is importable
backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Disable background writer and set dummy DB url
os.environ["WRITER_INTERVAL_SECONDS"] = "0"
os.environ["DATABASE_URL"] = "postgresql://dummy:dummy@localhost:5432/dummy"

import httpx
from unittest.mock import MagicMock

# Mock HTTP Client GET to return a valid tiny JPEG image instead of fetching remote URL
mock_http_response = MagicMock(spec=httpx.Response)
mock_http_response.status_code = 200
mock_http_response.content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\x27" "#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
mock_http_response.headers = httpx.Headers({"content-type": "image/jpeg"})

async def mock_http_get(*args, **kwargs):
    return mock_http_response

# Mock database functions so tests can run hermetically
mock_rois = {}

async def mock_save_roi(camera_id, roi_polygon, is_auto=False):
    mock_rois[camera_id] = roi_polygon

async def mock_get_roi(camera_id):
    return mock_rois.get(camera_id)

async def mock_async_none(*args, **kwargs):
    return None

patcher_save = patch('backend.database.save_camera_roi', side_effect=mock_save_roi)
patcher_get = patch('backend.database.get_camera_roi', side_effect=mock_get_roi)
patcher_init_db = patch('backend.database.init_db_pool', side_effect=mock_async_none)
patcher_init_schema = patch('backend.database.init_schema', side_effect=mock_async_none)
patcher_close_db = patch('backend.database.close_db_pool', side_effect=mock_async_none)
patcher_http = patch('httpx.AsyncClient.get', side_effect=mock_http_get)

patcher_save.start()
patcher_get.start()
patcher_init_db.start()
patcher_init_schema.start()
patcher_close_db.start()
patcher_http.start()

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
        svc._is_likely_error_image = lambda image_bytes: False
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
        # Stop patchers
        patcher_save.stop()
        patcher_get.stop()
        patcher_init_db.stop()
        patcher_init_schema.stop()
        patcher_close_db.stop()
        patcher_http.stop()
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
