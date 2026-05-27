# TrafficFlow - Hướng dẫn chạy Docker

## Cấu trúc dịch vụ

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌───────────┐  │
│  │  frontend   │───▶│     api     │───▶│     db    │  │
│  │  (nginx)    │    │  (FastAPI)  │    │(TimescaleDB)│
│  └─────────────┘    └─────────────┘    └───────────┘  │
│         │                                        │
└─────────┼────────────────────────────────────────┘
          │
    ┌─────▼─────┐
    │  port 5173│
    │  (nginx)  │  ← Port public duy nhất
    └───────────┘
```

## Ports

| Port   | Dịch vụ               | Mục đích                            |
| ------ | --------------------- | ----------------------------------- |
| `5173` | Frontend (nginx)      | Giao diện web + API + Docs (public) |
| `5432` | Database (PostgreSQL) | Database (nội bộ, không public)     |

> **Backend port 8000**: Chỉ dùng nội bộ trong Docker network, không public ra ngoài.

## URLs (tất cả qua port 5173)

| URL                                    | Mục đích                       |
| -------------------------------------- | ------------------------------ |
| **http://localhost:5173**              | Giao diện ứng dụng web         |
| **http://localhost:5173/docs**         | Swagger UI (API documentation) |
| **http://localhost:5173/redoc**        | ReDoc (API documentation)      |
| **http://localhost:5173/openapi.json** | OpenAPI JSON spec              |
| **http://localhost:5173/api/health**   | Health check                   |

## Cách chạy

### Khởi động tất cả dịch vụ

```bash
cd c:\Users\nguyen\Desktop\nckh
docker-compose up -d --build
```

### Kiểm tra trạng thái

```bash
docker-compose ps
```

### Xem logs

```bash
docker-compose logs -f
docker-compose logs -f api      # Chỉ logs backend
docker-compose logs -f frontend  # Chỉ logs frontend
```

### Dừng dịch vụ

```bash
docker-compose down
```

### Xóa hoàn toàn (bao gồm database)

```bash
docker-compose down -v
```

## Troubleshooting

### Frontend không load được

- Kiểm tra backend đã chạy chưa: `docker-compose logs api`
- Kiểm tra logs: `docker-compose logs frontend`

### API không hoạt động

- Kiểm tra database: `docker-compose logs db`
- Kiểm tra API: `docker-compose logs api`

### Rebuild từ đầu

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Môi trường

- **Frontend**: Vite + React + Leaflet (nginx)
- **Backend**: FastAPI (Python 3.11)
- **Database**: PostgreSQL + TimescaleDB
- **Model**: ZIP (Zero-Inflated Poisson) cho dự đoán giao thông
