# Tài Liệu Kỹ Thuật - Hệ Thống Giám Sát Giao Thông TP.HCM

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Kiến trúc hệ thống](#2-kiến-trúc-hệ-thống)
3. [Frontend](#3-frontend)
4. [Backend](#4-backend)
5. [AI Model - ZIP](#5-ai-model---zip)
6. [Thuật toán](#6-thuật-toán)
7. [Database](#7-database)
8. [Deployment](#8-deployment)

---

## 1. Tổng quan

**TrafficFlow** là hệ thống giám sát luồng giao thông thời gian thực cho TP.HCM, sử dụng AI để phân tích ảnh từ 624 camera.

### Thông số kỹ thuật

| Thông số        | Giá trị    |
| --------------- | ---------- |
| Số camera       | 624        |
| Cập nhật        | 15-30 giây |
| Data retention  | 60 phút    |
| Model inference | ~150ms/ảnh |
| API response    | ~150ms     |

### Tính năng chính

- Giám sát thời gian thực 624 camera
- Phát hiện kẹt xe (rule-based)
- Dự báo giao thông 15/30/60 phút
- Chỉ đường thông minh (AI-aware)
- Dashboard analytics

---

## 2. Kiến trúc hệ thống

### 2.1 Sơ đồ kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React)                           │
│  Dashboard • Bản đồ Leaflet • Chỉ đường OSRM                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                              HTTP/REST API
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                           │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐       │
│  │ ZIP Model│  │Congestion│  │ Forecast │  │Prediction   │       │
│  │ Service  │  │Detector  │  │ Service │  │Writer      │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
                    │                    │
                    ▼                    ▼
        ┌──────────────────┐   ┌──────────────────┐
        │  Camera API      │   │  TimescaleDB     │
        │ (External)      │   │  (PostgreSQL)    │
        └──────────────────┘   └──────────────────┘
```

### 2.2 Cấu trúc thư mục

```
trafficflow/
├── traffic-app/                 # Frontend React
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/DashboardPage.jsx
│   │   └── components/
│   │       ├── TrafficMap.jsx      # Map + Routing
│   │       ├── ControlPanel.jsx    # Route input
│   │       └── CameraPopup.jsx     # Camera info
│   └── package.json
│
├── trafficflow-api/            # Backend FastAPI
│   ├── backend/
│   │   ├── main.py            # FastAPI entry
│   │   ├── router.py         # API endpoints
│   │   ├── model_service.py   # ZIP model
│   │   ├── congestion_detector.py
│   │   ├── forecast_service.py
│   │   ├── prediction_writer.py
│   │   └── database.py
│   │
│   ├── ZIP/                  # AI Models
│   │   ├── models/ebc/       # EBC architecture
│   │   ├── models/clip_ebc/  # CLIP-EBC
│   │   └── losses/           # Loss functions
│   │
│   └── checkpoints/demo_data/
│       └── best_mae_0.onnx   # ONNX model
│
└── docker-compose.yml
```

### 2.3 Data Flow

```
Camera → Backend → ZIP Model → Database → Frontend
   │                        │
   │                        ▼
   │                   Congestion
   │                   Detection
   ▼
Heuristic (fallback)
```

---

## 3. Frontend

### 3.1 Công nghệ

| Technology              | Version | Purpose                |
| ----------------------- | ------- | ---------------------- |
| React                   | 19.2.5  | UI framework           |
| Vite                    | 8.0.10  | Build tool             |
| Leaflet                 | 1.9.4   | Maps                   |
| leaflet-routing-machine | 3.2.12  | Routing                |
| react-leaflet           | 5.0.0   | React-Leaflet bindings |

### 3.2 Components chính

| Component     | File              | Mô tả                      |
| ------------- | ----------------- | -------------------------- |
| TrafficMap    | TrafficMap.jsx    | Bản đồ + markers + routing |
| ControlPanel  | ControlPanel.jsx  | Input điểm đi/đến          |
| DashboardPage | DashboardPage.jsx | Analytics dashboard        |
| CameraPopup   | CameraPopup.jsx   | Popup thông tin camera     |

### 3.3 API Integration

```javascript
// Endpoints chính
GET / api / health; // Health check
GET / api / cameras; // Danh sách camera
POST / api / predict; // Predict từ ảnh
GET / api / forecast / { id }; // Dự báo
GET / api / congestion / map; // Bản đồ kẹt xe
GET / api / debug; // System status
```

---

## 4. Backend

### 4.1 FastAPI Structure

| File                   | Mô tả                         |
| ---------------------- | ----------------------------- |
| main.py                | App entry, lifespan           |
| router.py              | Tất cả endpoints (~1500 dòng) |
| model_service.py       | ZIP model loading & inference |
| congestion_detector.py | Phát hiện kẹt xe              |
| forecast_service.py    | Dự báo giao thông             |
| prediction_writer.py   | Background batch writer       |

### 4.2 API Endpoints chính

```
Health:
  GET /api/health

Cameras:
  GET /api/cameras?district=Quận 1
  GET /api/camera/{id}/image

Prediction:
  POST /api/predict                    # Upload ảnh
  GET  /api/predict/camera/{id}       # Từ camera
  POST /api/predict/batch             # Batch (max 30)

Congestion:
  GET /api/congestion/camera/{id}
  GET /api/congestion/map
  GET /api/congestion/stats

Forecast:
  GET /api/forecast/{camera_id}
```

### 4.3 Caching System

```python
# Image cache
_IMAGE_FALLBACK_CACHE = {}  # Max 20 images, 5 min TTL

# Prediction cache
class PredictionCache:
    # Lưu prediction gần nhất cho mỗi camera

# Debug cache
_DEBUG_CACHE_TTL = 30  # seconds
```

---

## 5. AI Model - ZIP

### 5.1 Zero-Inflated Poisson

ZIP model giải quyết bài toán đếm phương tiện với nhiều zeros.

**Công thức**:

```
P(X = 0) = π + (1-π) * e^(-λ)
P(X = k) = (1-π) * e^(-λ) * λ^k / k!  (k > 0)
```

**Biến số**:

- π = xác suất "structural zero"
- λ = số xe trung bình (Poisson parameter)

### 5.2 Model Architecture

```
Input Image
    │
    ▼
Backbone Encoder (CSRNet/CANNet/ViT/VGG/HRNet)
    │
    ▼
Prediction Heads
├── π head → P(zero)
└── λ head → Density map
    │
    ▼
Sum → Vehicle Count
```

### 5.3 Supported Backbones

| Backbone | Type        | Parameters |
| -------- | ----------- | ---------- |
| CSRNet   | CNN         | ~16M       |
| CANNet   | CNN         | ~12M       |
| VGG16    | CNN         | ~20M       |
| ViT-B/16 | Transformer | ~86M       |
| ConvNeXt | CNN         | ~50M       |
| HRNet    | CNN         | ~9M        |

### 5.4 ONNX Deployment

| Format       | Size  | Speed  | Use case   |
| ------------ | ----- | ------ | ---------- |
| PyTorch .pth | ~50MB | ~200ms | Training   |
| ONNX FP32    | ~50MB | ~150ms | Production |
| ONNX INT8    | ~12MB | ~50ms  | Edge/CPU   |

---

## 6. Thuật toán

### 6.1 Phát hiện kẹt xe (Congestion Detection)

**Rule-based, không cần ML training**

| Metric        | Công thức                            |
| ------------- | ------------------------------------ |
| Motion Ratio  | `count(absdiff > 25) / total_pixels` |
| Optical Flow  | `mean(magnitude[Farneback])`         |
| Edge Density  | `count(Canny) / total_pixels`        |
| Vehicle Score | `count(horizontal_flow > 2) / total` |

**Scoring**:

```
score = 0.40 * motion + 0.30 * flow + 0.30 * vehicle

Level:
  ≥ 0.70 → 0 (Thông thoáng)
  0.40-0.70 → 1 (Đông đúc)
  0.20-0.40 → 2 (Kẹt xe)
  < 0.20 → 3 (Ùn tắc)
```

### 6.2 Dự báo giao thông (Forecasting)

**Time-series với Weighted Moving Average**

```python
# Exponential decay weights
weights = exp(-linspace(-1, 0, n))

# Trend detection (linear regression)
slope = polyfit(x, counts, 1)[0]

# Forecast
predicted = wma + slope * trend_factor
confidence = 0.95 - (horizon / 200)
```

### 6.3 AI-Aware Routing

```
1. Get routes từ OSRM (≤ 3 alternatives)
2. Find cameras within 500m of route
3. Batch predict traffic
4. Calculate penalties:
   - Heavy: +5 min
   - Severe: +10 min
5. Select route with lowest adjusted ETA
```

---

## 7. Database

### 7.1 Schema

```sql
-- Main table (TimescaleDB hypertable)
CREATE TABLE prediction_history (
    camera_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    total_count INTEGER,
    car_count INTEGER,
    motorbike_count INTEGER,
    density_level VARCHAR(20),
    PRIMARY KEY (camera_id, timestamp)
);

-- Convert to hypertable
SELECT create_hypertable('prediction_history', 'timestamp');
```

### 7.2 Indexes

```sql
PRIMARY KEY (camera_id, timestamp);
INDEX idx_timestamp ON prediction_history(timestamp DESC);
INDEX idx_camera_time ON prediction_history(camera_id, timestamp DESC);
```

### 7.3 Common Queries

```sql
-- Records count
SELECT COUNT(*) FROM prediction_history;

-- Recent records
SELECT camera_id, AVG(total_count)
FROM prediction_history
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY camera_id;

-- Density distribution
SELECT density_level, COUNT(*)
FROM prediction_history
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY density_level;
```

### 7.4 Data Retention

- **Retention**: 60 phút
- **Cleanup**: Mỗi 10 batches (~5 phút)

---

## 8. Deployment

### 8.1 Docker Compose

```yaml
services:
  frontend:
    build: ./traffic-app
    ports: ["5173:80"]

  api:
    build: ./trafficflow-api
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql://...
      - WRITER_INTERVAL_SECONDS=15
    depends_on:
      - db

  db:
    image: timescale/timescaledb:latest-pg15
```

### 8.2 Environment Variables

```bash
# Database
DATABASE_URL=postgresql://trafficflow:trafficpass123@db:5432/trafficflow

# Model
ZIP_MODEL_PATH=ZIP/checkpoints/demo_data/best_mae_0.onnx
ZIP_MODEL_DEVICE=cpu
ZIP_INPUT_SIZE=448

# Writer
WRITER_INTERVAL_SECONDS=15
```

### 8.3 Ports

| Service  | Port | URL                        |
| -------- | ---- | -------------------------- |
| Frontend | 5173 | http://localhost:5173      |
| Backend  | 8000 | http://localhost:8000      |
| API Docs | 8000 | http://localhost:8000/docs |
