# Tài Liệu Database

## Tổng quan

Hệ thống sử dụng **PostgreSQL** với **TimescaleDB** extension để lưu trữ dữ liệu time-series.

### Database Info

- **Engine:** PostgreSQL 15 + TimescaleDB
- **Host:** `localhost:5432`
- **Database:** `trafficflow`
- **User:** `trafficflow`
- **Password:** `trafficpass123`

## Tables

### 1. `prediction_history` (Main Table)

Bảng chính lưu trữ dữ liệu dự đoán giao thông.

```sql
CREATE TABLE prediction_history (
    id BIGSERIAL,
    camera_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_count INTEGER NOT NULL,
    car_count INTEGER NOT NULL,
    motorbike_count INTEGER NOT NULL,
    density_level VARCHAR(20) NOT NULL,
    confidence FLOAT,
    PRIMARY KEY (camera_id, timestamp)
);
```

#### Columns

| Column          | Type        | Mô tả                          |
| --------------- | ----------- | ------------------------------ |
| id              | BIGSERIAL   | Auto-increment ID              |
| camera_id       | TEXT        | Camera identifier              |
| timestamp       | TIMESTAMPTZ | Thời gian dự đoán              |
| total_count     | INTEGER     | Tổng số phương tiện            |
| car_count       | INTEGER     | Số ô tô                        |
| motorbike_count | INTEGER     | Số xe máy                      |
| density_level   | VARCHAR(20) | Mức độ kẹt: low/moderate/heavy |
| confidence      | FLOAT       | Độ tin cậy (0-1)               |

#### Indexes

```sql
-- Primary key composite
PRIMARY KEY (camera_id, timestamp)

-- Index for time-based queries
CREATE INDEX idx_prediction_timestamp ON prediction_history(timestamp DESC);

-- Index for camera + time queries
CREATE INDEX idx_prediction_camera_time ON prediction_history(camera_id, timestamp DESC);
```

#### TimescaleDB Hypertable

```sql
SELECT create_hypertable('prediction_history', 'timestamp',
    if_not_exists => TRUE,
    migrate_data => TRUE);
```

---

### 2. `camera_error_log`

Bảng theo dõi camera offline/errors.

```sql
CREATE TABLE camera_error_log (
    id SERIAL PRIMARY KEY,
    camera_id TEXT NOT NULL,
    error_type TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
```

#### Columns

| Column      | Type        | Mô tả                             |
| ----------- | ----------- | --------------------------------- |
| id          | SERIAL      | Auto-increment ID                 |
| camera_id   | TEXT        | Camera identifier                 |
| error_type  | TEXT        | Loại lỗi (offline, timeout, etc.) |
| detected_at | TIMESTAMPTZ | Thời gian phát hiện               |
| expires_at  | TIMESTAMPTZ | Hết hạn (sau 30 phút)             |

#### Indexes

```sql
CREATE INDEX idx_cam_error_expires ON camera_error_log(camera_id, expires_at);
```

---

## Queries thường dùng

### Lấy dữ liệu 1 giờ gần nhất

```sql
SELECT
    camera_id,
    COUNT(*) as record_count,
    ROUND(AVG(total_count)::numeric, 1) as avg_count,
    ROUND(AVG(car_count)::numeric, 1) as avg_car,
    ROUND(AVG(motorbike_count)::numeric, 1) as avg_motorbike,
    MAX(total_count) as max_count,
    MIN(total_count) as min_count,
    ROUND(STDDEV(total_count)::numeric, 1) as std_count,
    ROUND(AVG(CASE WHEN density_level = 'heavy' THEN 1 ELSE 0 END) * 100, 1) as heavy_pct,
    ROUND(AVG(CASE WHEN density_level = 'moderate' THEN 1 ELSE 0 END) * 100, 1) as moderate_pct,
    ROUND(AVG(CASE WHEN density_level = 'low' THEN 1 ELSE 0 END) * 100, 1) as low_pct,
    MAX(timestamp) as last_record
FROM prediction_history
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY camera_id
ORDER BY record_count DESC;
```

### Đếm records theo camera

```sql
SELECT
    camera_id,
    COUNT(*)
FROM prediction_history
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY camera_id
ORDER BY COUNT(*) DESC;
```

### Lấy tất cả records của 1 camera

```sql
SELECT
    id,
    camera_id,
    total_count,
    car_count,
    motorbike_count,
    density_level,
    timestamp
FROM prediction_history
WHERE camera_id = '662b80051afb9c00172dcaf6'
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

### Thống kê theo mật độ

```sql
SELECT
    density_level,
    COUNT(*) as count
FROM prediction_history
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY density_level;
```

### Camera có kẹt xe nhiều nhất

```sql
SELECT
    camera_id,
    COUNT(*) as count,
    ROUND(AVG(total_count)::numeric, 1) as avg_count,
    ROUND(AVG(CASE WHEN density_level = 'heavy' THEN 1 ELSE 0 END) * 100, 1) as heavy_pct
FROM prediction_history
GROUP BY camera_id
ORDER BY avg_count DESC
LIMIT 10;
```

### Tổng số records

```sql
SELECT COUNT(*) FROM prediction_history;
```

### Xóa records cũ hơn 60 phút

```sql
DELETE FROM prediction_history
WHERE timestamp < NOW() - INTERVAL '60 minutes';
```

---

## Data Retention

- **Retention period:** 60 phút (DATA_RETENTION_MINUTES)
- **Cleanup:** Chạy tự động mỗi 10 batches (~5 phút)
- **Batch size:** 30 giây

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Lifecycle                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Write] ──▶ [Store 60 min] ──▶ [Auto Cleanup]             │
│     │              │                    │                    │
│     ▼              ▼                    ▼                    │
│  Every 30s    TimescaleDB         DELETE records            │
│  (batch)       hypertable         older than 60 min          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Connection Pool

```python
# Connection pool settings
await asyncpg.create_pool(
    dsn,
    min_size=2,      # Minimum connections
    max_size=10,     # Maximum connections
    command_timeout=60,  # Query timeout (seconds)
)
```

### Pool Stats

- Min connections: 2
- Max connections: 10
- Command timeout: 60s

---

## Backup & Recovery

### Backup

```bash
# Full backup
docker exec nckh-db-1 pg_dump -U trafficflow trafficflow > backup.sql

# Backup với timestamp
docker exec nckh-db-1 pg_dump -U trafficflow trafficflow > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore

```bash
# Restore from backup
cat backup.sql | docker exec -i nckh-db-1 psql -U trafficflow trafficflow
```

### Volume Mount

```yaml
db:
  image: timescale/timescaledb:latest-pg15
  volumes:
    - pgdata:/var/lib/postgresql/data
```

---

## Performance Tips

### Query Optimization

1. **Luôn filter theo timestamp trước:**

```sql
-- Tốt
WHERE timestamp > NOW() - INTERVAL '1 hour' AND camera_id = 'xxx'

-- Chậm hơn
WHERE camera_id = 'xxx' AND timestamp > NOW() - INTERVAL '1 hour'
```

2. **Sử dụng LIMIT:**

```sql
-- Có LIMIT
SELECT * FROM prediction_history ORDER BY timestamp DESC LIMIT 100;

-- Không LIMIT (có thể trả về hàng triệu rows)
SELECT * FROM prediction_history ORDER BY timestamp DESC;
```

3. **Tránh SELECT \* trong production:**

```sql
-- Tốt
SELECT camera_id, total_count, timestamp FROM prediction_history...

-- Ít tốt
SELECT * FROM prediction_history...
```

### Indexes

```sql
-- Cho real-time queries
CREATE INDEX idx_recent ON prediction_history(timestamp DESC);

-- Cho camera-specific queries
CREATE INDEX idx_camera ON prediction_history(camera_id);

-- Composite cho frequent queries
CREATE INDEX idx_camera_time ON prediction_history(camera_id, timestamp DESC);
```

---

## Troubleshooting

### Kiểm tra kết nối

```bash
docker exec -it nckh-db-1 psql -U trafficflow -d trafficflow -c "SELECT 1;"
```

### Kiểm tra tables

```bash
docker exec -it nckh-db-1 psql -U trafficflow -d trafficflow -c "\dt"
```

### Kiểm tra indexes

```bash
docker exec -it nckh-db-1 psql -U trafficflow -d trafficflow -c "\di"
```

### Kiểm tra query performance

```sql
-- Enable timing
\timing on

-- Run query
SELECT COUNT(*) FROM prediction_history;

-- Explain analyze
EXPLAIN ANALYZE SELECT * FROM prediction_history WHERE timestamp > NOW() - INTERVAL '1 hour';
```

### Giải phóng space sau xóa

```sql
-- Vacuum để reclaim space
VACUUM FULL prediction_history;

-- Hoặc auto-vacuum
ALTER TABLE prediction_history SET (autovacuum_vacuum_scale_factor = 0.01);
```

---

## Database Stats

```sql
-- Database size
SELECT pg_size_pretty(pg_database_size(current_database()));

-- Table size
SELECT pg_size_pretty(pg_total_relation_size('prediction_history'));

-- Index size
SELECT pg_size_pretty(pg_indexes_size('prediction_history'));

-- Row count
SELECT COUNT(*) FROM prediction_history;

-- Rows per camera
SELECT camera_id, COUNT(*)
FROM prediction_history
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY camera_id
ORDER BY COUNT(*) DESC;
```
