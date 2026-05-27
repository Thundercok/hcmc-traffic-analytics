# API Documentation

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Endpoints](#2-endpoints)
3. [Request/Response Examples](#3-requestresponse-examples)
4. [Error Handling](#4-error-handling)

---

## 1. Tổng quan

**Base URL**: `http://localhost:8000/api`

### Authentication

Không yêu cầu authentication cho tất cả endpoints.

### Rate Limiting

- Batch predict: max 30 images/request
- Camera image proxy: 5 concurrent requests

---

## 2. Endpoints

### Health

| Method | Endpoint  | Mô tả        |
| ------ | --------- | ------------ |
| GET    | `/health` | Health check |

**Response:**

```json
{
  "status": "ok",
  "model_loaded": true,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

---

### Cameras

#### GET /cameras

Lấy danh sách camera.

| Parameter  | Type   | Default | Mô tả           |
| ---------- | ------ | ------- | --------------- |
| `district` | string | -       | Lọc theo quận   |
| `limit`    | int    | 50      | Số lượng tối đa |

**Response:**

```json
{
  "cameras": [
    {
      "id": "camera_001",
      "name": "Camera 001",
      "district": "Quận 1",
      "lat": 10.7769,
      "lng": 106.7009,
      "url": "http://..."
    }
  ],
  "total": 624
}
```

#### GET /camera/{id}/image

Lấy ảnh từ camera (cached).

**Parameters:**
| Parameter | Type | Mô tả |
|-----------|------|--------|
| `id` | string | Camera ID |
| `width` | int | Resize width (optional) |

---

### Prediction

#### POST /predict

Dự đoán số phương tiện từ ảnh upload.

**Request:** `multipart/form-data`

```
image: <file>
device: cpu (optional)
```

**Response:**

```json
{
  "count": 45,
  "density_level": "medium",
  "processing_time_ms": 150,
  "model": "onnx"
}
```

#### GET /predict/camera/{id}

Dự đoán từ camera hiện tại.

**Response:**

```json
{
  "camera_id": "camera_001",
  "count": 45,
  "density_level": "medium",
  "timestamp": "2024-01-01T12:00:00Z",
  "image_url": "/api/camera/camera_001/image"
}
```

#### POST /predict/batch

Batch predict (max 30 images).

**Request:** `multipart/form-data`

```
images: [<file1>, <file2>, ...]
device: cpu
```

**Response:**

```json
{
  "results": [
    { "index": 0, "count": 45, "density_level": "medium" },
    { "index": 1, "count": 32, "density_level": "low" }
  ],
  "total_processing_time_ms": 450
}
```

---

### Congestion

#### GET /congestion/camera/{id}

Mức độ kẹt xe của một camera.

**Response:**

```json
{
  "camera_id": "camera_001",
  "level": 0,
  "level_text": "Thông thoáng",
  "metrics": {
    "motion_ratio": 0.15,
    "optical_flow": 0.8,
    "edge_density": 0.25,
    "vehicle_motion_score": 0.2
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

**Level meanings:**
| Level | Text | Description |
|-------|------|-------------|
| 0 | Thông thoáng | Smooth traffic |
| 1 | Đông đúc | Heavy traffic |
| 2 | Kẹt xe | Traffic jam |
| 3 | Ùn tắc | Severe congestion |

#### GET /congestion/map

Bản đồ kẹt xe tất cả camera.

**Parameters:**
| Parameter | Type | Default | Mô tả |
|-----------|------|---------|--------|
| `district` | string | - | Lọc theo quận |

**Response:**

```json
{
  "cameras": [
    {
      "camera_id": "camera_001",
      "level": 0,
      "lat": 10.7769,
      "lng": 106.7009
    }
  ],
  "summary": {
    "smooth": 450,
    "heavy": 120,
    "jam": 40,
    "severe": 14
  }
}
```

#### GET /congestion/stats

Thống kê kẹt xe.

**Response:**

```json
{
  "total_cameras": 624,
  "by_level": {
    "0": 450,
    "1": 120,
    "2": 40,
    "3": 14
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

---

### Forecast

#### GET /forecast/{camera_id}

Dự báo giao thông.

**Parameters:**
| Parameter | Type | Default | Mô tả |
|-----------|------|---------|--------|
| `horizon_minutes` | int | 15 | Thời gian dự báo |

**Response:**

```json
{
  "camera_id": "camera_001",
  "current_count": 45,
  "forecast": {
    "15min": {
      "predicted_count": 52,
      "confidence": 0.92,
      "trend": "increasing"
    },
    "30min": {
      "predicted_count": 58,
      "confidence": 0.88,
      "trend": "increasing"
    },
    "60min": {
      "predicted_count": 65,
      "confidence": 0.8,
      "trend": "increasing"
    }
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

---

### Routing

#### POST /route

Tìm đường với AI-aware routing.

**Request:**

```json
{
  "start": { "lat": 10.7769, "lng": 106.7009 },
  "end": { "lat": 10.8231, "lng": 106.6293 },
  "avoid_traffic": true
}
```

**Response:**

```json
{
  "routes": [
    {
      "distance_km": 5.2,
      "duration_min": 12,
      "duration_with_traffic_min": 15,
      "waypoints": [[10.7769, 106.7009], ...],
      "cameras_along_route": [
        {"camera_id": "001", "lat": 10.78, "lng": 106.70, "traffic_level": 1}
      ]
    }
  ]
}
```

---

### Debug

#### GET /debug

System status and statistics.

**Response:**

```json
{
  "api_uptime": 3600,
  "predictions_cache_size": 624,
  "image_cache_size": 20,
  "db_records_count": 15000,
  "last_prediction_time": "2024-01-01T12:00:00Z"
}
```

---

## 3. Request/Response Examples

### Python (httpx)

```python
import httpx

# Health check
resp = httpx.get("http://localhost:8000/api/health")

# Get cameras
resp = httpx.get("http://localhost:8000/api/cameras",
                 params={"district": "Quận 1"})

# Predict from image
with open("traffic.jpg", "rb") as f:
    resp = httpx.post("http://localhost:8000/api/predict",
                      files={"image": f})

# Batch predict
files = [("images", open(f"img_{i}.jpg", "rb")) for i in range(5)]
resp = httpx.post("http://localhost:8000/api/predict/batch", files=files)

# Get congestion map
resp = httpx.get("http://localhost:8000/api/congestion/map")

# Get forecast
resp = httpx.get("http://localhost:8000/api/forecast/camera_001",
                 params={"horizon_minutes": 30})

# Route with traffic
resp = httpx.post("http://localhost:8000/api/route", json={
    "start": {"lat": 10.7769, "lng": 106.7009},
    "end": {"lat": 10.8231, "lng": 106.6293},
    "avoid_traffic": True
})
```

### JavaScript (fetch)

```javascript
// Get cameras
const resp = await fetch("/api/cameras?district=Quận 1");
const { cameras } = await resp.json();

// Predict
const formData = new FormData();
formData.append("image", fileInput.files[0]);
const resp = await fetch("/api/predict", { method: "POST", body: formData });

// Route
const resp = await fetch("/api/route", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    start: { lat: 10.7769, lng: 106.7009 },
    end: { lat: 10.8231, lng: 106.6293 },
  }),
});
```

---

## 4. Error Handling

### Error Response Format

```json
{
  "error": "Error type",
  "message": "Detailed error message",
  "details": {}
}
```

### HTTP Status Codes

| Code | Meaning                                |
| ---- | -------------------------------------- |
| 200  | Success                                |
| 400  | Bad Request - Invalid input            |
| 404  | Not Found - Camera not found           |
| 422  | Validation Error                       |
| 500  | Internal Server Error                  |
| 503  | Service Unavailable - Model not loaded |

### Common Errors

```json
// Camera not found
{"error": "not_found", "message": "Camera camera_999 not found"}

// Invalid image
{"error": "invalid_image", "message": "Could not decode image"}

// Batch too large
{"error": "batch_too_large", "message": "Maximum 30 images per batch"}
```
