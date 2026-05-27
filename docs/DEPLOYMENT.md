# Hướng Dẫn Triển Khai

## Mục lục

1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt](#cài-đặt)
3. [Chạy với Docker](#chạy-với-docker)
4. [Cấu hình](#cấu-hình)
5. [Deployment Production](#deployment-production)
6. [Monitoring](#monitoring)
7. [Troubleshooting](#troubleshooting)

---

## Yêu cầu hệ thống

### Phần cứng

| Component | Minimum | Recommended |
| --------- | ------- | ----------- |
| CPU       | 2 cores | 4+ cores    |
| RAM       | 4 GB    | 8+ GB       |
| Disk      | 10 GB   | 20+ GB SSD  |
| Network   | 10 Mbps | 100 Mbps    |

### Software

- **Docker Desktop** 20.10+
- **Docker Compose** 2.0+
- **Git** (để clone repository)

### OS Support

- Windows 10/11 (Docker Desktop)
- macOS 10.15+
- Linux (Ubuntu 20.04+)

---

## Cài đặt

### 1. Cài đặt Docker Desktop

**Windows:**

1. Download Docker Desktop: https://www.docker.com/products/docker-desktop
2. Run installer và làm theo wizard
3. Enable WSL 2 backend nếu được hỏi
4. Restart máy nếu cần

**macOS:**

```bash
brew install --cask docker
```

### 2. Clone Repository

```bash
cd ~/projects
git clone <repository-url> trafficflow
cd trafficflow
```

### 3. Cấu trúc thư mục

```
trafficflow/
├── traffic-app/              # Frontend React
├── trafficflow-api/          # Backend FastAPI
├── CrawlCamera/             # Camera crawler
├── docs/                    # Documentation
├── scripts/                 # Utility scripts
├── ZIP/                     # AI models
├── docker-compose.yml        # Docker orchestration
└── nginx.frontend.conf      # Nginx config
```

---

## Chạy với Docker

### Build và chạy tất cả services

```bash
# Build tất cả images
docker compose build

# Chạy tất cả services (detached mode)
docker compose up -d

# Hoặc build và chạy cùng lúc
docker compose up -d --build
```

### Kiểm tra trạng thái

```bash
# Xem tất cả containers
docker compose ps

# Xem logs của một service
docker compose logs api
docker compose logs frontend
docker compose logs db

# Theo dõi logs real-time
docker compose logs -f
```

### Truy cập ứng dụng

| Service     | URL                         |
| ----------- | --------------------------- |
| Frontend    | http://localhost:5173       |
| Backend API | http://localhost:8000       |
| API Docs    | http://localhost:8000/docs  |
| API ReDoc   | http://localhost:8000/redoc |

### Stop services

```bash
# Stop tất cả
docker compose down

# Stop và xóa volumes (CẨN THẬN: xóa data!)
docker compose down -v
```

---

## Cấu hình

### Environment Variables

Tạo file `.env` nếu cần:

```bash
# Database
DATABASE_URL=postgresql://trafficflow:trafficpass123@db:5432/trafficflow
DB_HOST=db
DB_PORT=5432
DB_USER=trafficflow
DB_PASSWORD=trafficpass123
DB_NAME=trafficflow

# API
TF_HOST=0.0.0.0
TF_PORT=8000
WRITER_INTERVAL_SECONDS=30
```

### Docker Compose Override

Tạo `docker-compose.override.yml` để override cấu hình:

```yaml
version: "3.8"

services:
  api:
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
    ports:
      - "8000:8000"
```

### Nginx Configuration

File `nginx.frontend.conf`:

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Deployment Production

### 1. Chuẩn bị Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Cấu hình Firewall

```bash
# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow SSH
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable
```

### 3. Deploy với Docker

```bash
# Clone repository
git clone <repo-url> /opt/trafficflow
cd /opt/trafficflow

# Pull latest code
git pull origin main

# Build và chạy
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 4. Production docker-compose.prod.yml

```yaml
version: "3.8"

services:
  frontend:
    restart: always
    healthcheck:
      test:
        ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/"]
      interval: 30s
      timeout: 10s
      retries: 3

  api:
    restart: always
    environment:
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    restart: always
    command: postgres -c shared_preload_libraries=timescaledb
```

### 5. SSL/HTTPS với Nginx Proxy

```yaml
# docker-compose.prod.yml
services:
  proxy:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - api
```

### 6. Backup Tự động

Tạo cron job cho backup:

```bash
# /etc/cron.daily/backup-trafficflow
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backups/trafficflow

docker exec nckh-db-1 pg_dump -U trafficflow trafficflow | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

---

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/api/health

# Database status
curl http://localhost:8000/api/debug | jq '.database.status'
```

### Container Stats

```bash
# Resource usage
docker stats

# Chi tiết container
docker inspect nckh-api

# Logs
docker compose logs --tail=100 api
```

### Prometheus Metrics (Future)

```yaml
# docker-compose.metrics.yml
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

---

## Troubleshooting

### Container không chạy

```bash
# Xem logs
docker compose logs <service-name>

# Xem container details
docker compose ps -a
docker compose logs --tail=50
```

### Database connection failed

```bash
# Kiểm tra DB container
docker compose logs db

# Kết nối thủ công
docker exec -it nckh-db-1 psql -U trafficflow -d trafficflow

# Kiểm tra connection
docker exec nckh-db-1 pg_isready -U trafficflow
```

### API trả lỗi 503

```bash
# Kiểm tra model loaded
curl http://localhost:8000/api/health | jq '.model'

# Rebuild API
docker compose up -d --build api
```

### Frontend không load

```bash
# Kiểm tra Nginx logs
docker compose logs frontend

# Rebuild frontend
docker compose up -d --build frontend
```

### Memory issues

```bash
# Xem memory usage
docker stats --no-stream

# Tăng memory Docker Desktop:
# Docker Desktop > Settings > Resources > Memory
```

### Xóa và重建

```bash
# Stop all
docker compose down

# Xóa volumes (CẨN THẬN!)
docker compose down -v

# Xóa images
docker compose down --rmi all

# Rebuild fresh
docker compose up -d --build
```

---

## Quick Reference

```bash
# === START ===
docker compose up -d

# === STOP ===
docker compose down

# === RESTART ===
docker compose restart

# === REBUILD ===
docker compose up -d --build

# === LOGS ===
docker compose logs -f api

# === STATUS ===
docker compose ps

# === CLEAN ===
docker system prune -a
```

---

## Liên hệ hỗ trợ

- Email: nguyenvana@example.com
- Issues: https://github.com/.../issues
