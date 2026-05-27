# Technical Specifications

## Mục lục

1. [System Overview](#1-system-overview)
2. [Frontend Specifications](#2-frontend-specifications)
3. [Backend Specifications](#3-backend-specifications)
4. [AI/ML Specifications](#4-aiml-specifications)
5. [Database Specifications](#5-database-specifications)
6. [Performance Metrics](#6-performance-metrics)

---

## 1. System Overview

| Component  | Technology                 |
| ---------- | -------------------------- |
| Frontend   | React 19, Vite, Leaflet    |
| Backend    | FastAPI, Python 3.11       |
| Database   | PostgreSQL 15, TimescaleDB |
| AI Models  | PyTorch, ONNX Runtime      |
| Deployment | Docker, Docker Compose     |

### Project Structure

```
trafficflow/
├── traffic-app/              # Frontend
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   └── DashboardPage.jsx
│   │   └── components/
│   │       ├── TrafficMap.jsx
│   │       ├── ControlPanel.jsx
│   │       └── CameraPopup.jsx
│   └── package.json
│
├── trafficflow-api/          # Backend
│   ├── backend/
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── model_service.py
│   │   ├── congestion_detector.py
│   │   ├── forecast_service.py
│   │   ├── prediction_writer.py
│   │   └── database.py
│   │
│   ├── ZIP/                # AI Models
│   │   ├── models/ebc/
│   │   ├── models/clip_ebc/
│   │   └── losses/
│   │
│   └── checkpoints/
│       └── best_mae_0.onnx
│
└── docker-compose.yml
```

---

## 2. Frontend Specifications

### Dependencies

| Package                 | Version | Purpose           |
| ----------------------- | ------- | ----------------- |
| react                   | ^19.2.5 | UI framework      |
| vite                    | ^8.0.10 | Build tool        |
| react-dom               | ^19.2.5 | DOM renderer      |
| leaflet                 | ^1.9.4  | Maps              |
| react-leaflet           | ^5.0.0  | React-Leaflet     |
| react-leaflet-cluster   | ^2.1.0  | Marker clustering |
| leaflet-routing-machine | ^3.2.12 | Routing           |
| tailwindcss             | ^3.4.17 | Styling           |
| recharts                | ^2.15.1 | Charts            |

### Key Components

| Component     | File              | State Management    |
| ------------- | ----------------- | ------------------- |
| TrafficMap    | TrafficMap.jsx    | useState, useEffect |
| ControlPanel  | ControlPanel.jsx  | useState            |
| CameraPopup   | CameraPopup.jsx   | Props               |
| DashboardPage | DashboardPage.jsx | useState, useEffect |
| KPICard       | KPICard.jsx       | Props               |
| TrafficTable  | TrafficTable.jsx  | Props               |
| DensityChart  | DensityChart.jsx  | Props               |

### Performance Optimizations

| Technique      | Implementation                   |
| -------------- | -------------------------------- |
| Memoization    | React.memo, useMemo, useCallback |
| Lazy Loading   | React.lazy, Suspense             |
| Image Loading  | Intersection Observer            |
| API Debouncing | 300ms debounce on requests       |
| Virtualization | react-window for large lists     |

---

## 3. Backend Specifications

### Dependencies

| Package          | Version   | Purpose          |
| ---------------- | --------- | ---------------- |
| fastapi          | ^0.109.2  | Web framework    |
| uvicorn          | ^0.27.1   | ASGI server      |
| python-multipart | ^0.0.9    | File uploads     |
| httpx            | ^0.27.0   | HTTP client      |
| pydantic         | ^2.6.1    | Data validation  |
| psycopg2-binary  | ^2.9.9    | PostgreSQL       |
| psycopg          | 3.1.18    | Async PostgreSQL |
| sqlalchemy       | ^2.0.25   | ORM              |
| pillow           | ^10.2.0   | Image processing |
| opencv-python    | ^4.9.0.80 | CV operations    |
| torch            | ^2.2.0    | PyTorch          |
| onnxruntime      | ^1.17.0   | ONNX Runtime     |

### Services

| Service            | File                   | Purpose                   |
| ------------------ | ---------------------- | ------------------------- |
| ZIPModelService    | model_service.py       | Model loading & inference |
| CongestionDetector | congestion_detector.py | Traffic analysis          |
| TrafficForecaster  | forecast_service.py    | Time-series prediction    |
| PredictionWriter   | prediction_writer.py   | Batch background writer   |
| CameraManager      | cameras.py             | Camera data management    |

### Caching

| Cache      | TTL    | Max Size | Backend        |
| ---------- | ------ | -------- | -------------- |
| Image      | 5 min  | 20       | In-memory dict |
| Prediction | 1 min  | 624      | In-memory dict |
| Debug      | 30 sec | 1        | In-memory dict |

---

## 4. AI/ML Specifications

### ZIP Model Architecture

```
Input (H x W x 3)
    │
    ▼
Backbone Encoder
├── CSRNet (VGG16 backbone)
├── CANNet (Context-Aware)
├── ViT-B/16 (Transformer)
├── ConvNeXt
├── HRNet
└── MobileCLIP
    │
    ▼
Prediction Heads
├── π head → P(zero) [0, 1]
└── λ head → Density map
    │
    ▼
Output: Vehicle Count
```

### Loss Functions

| Loss           | Formula                                | Weight |
| -------------- | -------------------------------------- | ------ |
| ZIP NLL        | Negative log-likelihood of ZIP         | 1.0    |
| MultiScale MAE | Mean Absolute Error at multiple scales | 1.0    |

### Zero-Inflated Poisson

```
P(X = 0) = π + (1-π) * e^(-λ)
P(X = k) = (1-π) * e^(-λ) * λ^k / k!  (k > 0)

Parameters:
- π ∈ [0, 1]: probability of structural zero
- λ ≥ 0: Poisson mean
```

### ONNX Specifications

| Format       | Precision | Size  | Inference Time |
| ------------ | --------- | ----- | -------------- |
| PyTorch .pth | FP32      | ~50MB | ~200ms         |
| ONNX FP32    | FP32      | ~50MB | ~150ms         |
| ONNX INT8    | INT8      | ~12MB | ~50ms          |

### Congestion Detection Metrics

| Metric        | Formula                         | Weight |
| ------------- | ------------------------------- | ------ |
| Motion Ratio  | `count(absdiff > 25) / total`   | 0.40   |
| Optical Flow  | `mean(magnitude)`               | 0.30   |
| Edge Density  | `count(Canny) / total`          | 0.30   |
| Vehicle Score | `count(horizontal > 2) / total` | -      |

### Traffic Forecasting

| Method                  | Description                   |
| ----------------------- | ----------------------------- |
| Weighted Moving Average | Exponential decay weights     |
| Linear Regression       | Trend detection               |
| Time Features           | Rush hour, weekend indicators |

---

## 5. Database Specifications

### PostgreSQL with TimescaleDB

| Setting        | Value      |
| -------------- | ---------- |
| PostgreSQL     | 15         |
| TimescaleDB    | Latest     |
| Data Retention | 60 minutes |
| Chunk Interval | 1 hour     |

### Schema

```sql
-- Main hypertable
CREATE TABLE prediction_history (
    camera_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    total_count INTEGER,
    car_count INTEGER,
    motorbike_count INTEGER,
    density_level VARCHAR(20),
    PRIMARY KEY (camera_id, timestamp)
);

-- Indexes
CREATE INDEX idx_timestamp ON prediction_history(timestamp DESC);
CREATE INDEX idx_camera_time ON prediction_history(camera_id, timestamp DESC);
```

### Connection Pool

| Parameter       | Value |
| --------------- | ----- |
| Min connections | 5     |
| Max connections | 20    |
| Max overflow    | 10    |
| Pool timeout    | 30s   |

---

## 6. Performance Metrics

### Latency

| Operation       | Target | Max   |
| --------------- | ------ | ----- |
| API response    | 100ms  | 500ms |
| Model inference | 100ms  | 300ms |
| Database query  | 10ms   | 100ms |
| Image load      | 50ms   | 200ms |

### Throughput

| Endpoint            | Target QPS |
| ------------------- | ---------- |
| /api/health         | 1000       |
| /api/cameras        | 100        |
| /api/predict        | 50         |
| /api/congestion/map | 20         |

### Resource Usage

| Resource       | Development | Production |
| -------------- | ----------- | ---------- |
| CPU (API)      | 1 core      | 2 cores    |
| Memory (API)   | 512MB       | 1GB        |
| Memory (Model) | 512MB       | 1GB        |
| Disk (cache)   | 100MB       | 100MB      |

### Uptime Targets

| Service  | Target |
| -------- | ------ |
| API      | 99.9%  |
| Database | 99.9%  |
| Frontend | 99.5%  |

---

## Environment Variables

### Backend

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/db

# Model
ZIP_MODEL_PATH=path/to/model.onnx
ZIP_MODEL_DEVICE=cpu
ZIP_INPUT_SIZE=448

# Writer
WRITER_INTERVAL_SECONDS=15
WRITER_BATCH_SIZE=50
```

### Frontend

```bash
VITE_API_URL=http://localhost:8000/api
VITE_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
```
