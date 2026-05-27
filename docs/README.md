# TrafficFlow - Hệ Thống Giám Sát Giao Thông TP.HCM

## Giới thiệu

TrafficFlow là hệ thống giám sát luồng giao thông thời gian thực sử dụng AI cho TP.HCM.

### Tính năng

- **624 camera** giám sát thời gian thực
- **ZIP Model** đếm phương tiện (Zero-Inflated Poisson)
- **Phát hiện kẹt xe** (rule-based, OpenCV)
- **Dự báo giao thông** 15/30/60 phút
- **Chỉ đường thông minh** với AI-aware routing

---

## Quick Start

```bash
# Clone & start
git clone <repo>
cd trafficflow
docker compose up -d

# Access
http://localhost:5173   # Frontend
http://localhost:8000/docs  # API Docs
```

---

## Tech Stack

| Layer      | Technology                            |
| ---------- | ------------------------------------- |
| Frontend   | React 19, Vite, Tailwind CSS, Leaflet |
| Backend    | FastAPI, Python 3.11                  |
| Database   | PostgreSQL 15, TimescaleDB            |
| AI         | PyTorch, ONNX Runtime                 |
| Deployment | Docker, Docker Compose                |

---

## Documentation

| Document                        | Mô tả                |
| ------------------------------- | -------------------- |
| [INDEX](INDEX.md)               | Danh mục tài liệu    |
| [ARCHITECTURE](ARCHITECTURE.md) | Kiến trúc hệ thống   |
| [API](API.md)                   | Tài liệu API         |
| [SPEC](SPEC.md)                 | Thông số kỹ thuật    |
| [DATABASE](DATABASE.md)         | Database schema      |
| [DEPLOYMENT](DEPLOYMENT.md)     | Hướng dẫn triển khai |

---

## Architecture

```
Cameras (624) → FastAPI API → ZIP Model (ONNX)
                     ↓
              TimescaleDB
                     ↓
              React Dashboard
```
