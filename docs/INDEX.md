# Tài Liệu Kỹ Thuật - TrafficFlow

## Cấu trúc tài liệu

| File                               | Mô tả                     |
| ---------------------------------- | ------------------------- |
| [README.md](README.md)             | Giới thiệu tổng quan      |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Kiến trúc hệ thống        |
| [API.md](API.md)                   | Tài liệu API endpoints    |
| [SPEC.md](SPEC.md)                 | Thông số kỹ thuật         |
| [DATABASE.md](DATABASE.md)         | Database schema & queries |
| [DEPLOYMENT.md](DEPLOYMENT.md)     | Hướng dẫn triển khai      |

---

## Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React)                          │
│  Dashboard • Bản đồ Leaflet • Chỉ đường OSRM                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                              HTTP/REST API
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                           │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐         │
│  │ ZIP Model│  │Congestion│  │ Forecast │  │Prediction    │         │
│  │ Service  │  │Detector  │  │ Service  │  │Writer        │         │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
                    │                    │
                    ▼                    ▼
        ┌──────────────────┐   ┌──────────────────┐
        │  Camera API      │   │  TimescaleDB     │
        │  (External)      │   │  (PostgreSQL)    │
        └──────────────────┘   └──────────────────┘
```

---

## Quick Start

```bash
# Start
docker compose up -d

# Access
http://localhost:5173       # Frontend
http://localhost:8000/docs  # API Docs
```

---

## API Endpoints

| Endpoint                  | Mô tả              |
| ------------------------- | ------------------ |
| `GET /api/health`         | Health check       |
| `GET /api/cameras`        | Danh sách camera   |
| `POST /api/predict`       | Predict từ ảnh     |
| `GET /api/forecast/{id}`  | Dự báo giao thông  |
| `GET /api/congestion/map` | Bản đồ kẹt xe      |
| `POST /api/route`         | Chỉ đường AI-aware |

---

## Thông số kỹ thuật

| Thông số        | Giá trị |
| --------------- | ------- |
| Cameras         | 624     |
| Update interval | 15-30s  |
| Model inference | ~150ms  |
| API response    | ~150ms  |
| Data retention  | 60 phút |

---

## Tech Stack

| Layer      | Technology                            |
| ---------- | ------------------------------------- |
| Frontend   | React 19, Vite, Tailwind CSS, Leaflet |
| Backend    | FastAPI, Python 3.11                  |
| Database   | PostgreSQL 15, TimescaleDB            |
| AI         | PyTorch, ONNX Runtime                 |
| Deployment | Docker, Docker Compose                |
