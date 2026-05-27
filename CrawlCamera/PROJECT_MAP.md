# PROJECT_MAP: CrawlCamera

## 1. Project Overview
- **Name:** `crawlCamera`
- **Domain:** Data Crawling / IoT Camera Stream (Traffic Cameras HCMC).
- **Tech Stack:** Node.js (v14-alpine), `axios`, `crypto`, `child_process`.
- **Deployment:** Dockerized, hosted on [Fly.io](https://fly.io) (Region: `sin`).
- **Main Goal:** Tự động lấy và lưu trữ hình ảnh từ các camera giao thông (hiện đang lọc "Quận 7") theo chu kỳ để tạo dataset.

## 2. Directory Structure & Key Files
- `index.js` (Entry Point): Script điều phối (Master). Lọc danh sách camera theo quận, quản lý vòng đời các tiến trình con (fork), tự động restart tiến trình con nếu bị crash.
- `crawl.js` (Worker): Tiến trình con thực hiện crawl ảnh cho một Camera ID cụ thể. Fake headers, gọi API định kỳ mỗi 8 giây, check mã băm (MD5) để tránh lưu ảnh trùng lặp.
- `GetDistrict.js`: Script tiện ích (Utility) dùng để map dữ liệu tọa độ (OpenCage) thành quận/huyện tương ứng và xuất ra `ListCamerasWithDistrict.json`.
- `Dockerfile` & `fly.toml`: Cấu hình deploy lên nền tảng Fly.io với Node 14.
- `*.json` / `*.js` (Data files): Chứa metadata của các camera (ID, tọa độ, địa chỉ).

## 3. Execution Flow
1. Khởi chạy `node index.js`.
2. Master script đọc `ListCamerasWithDistrict.json`, lọc ra các camera ở "Quận 7".
3. Với mỗi camera, Master tạo một Child Process chạy `crawl.js <cam_id>` (cách nhau 1 giây).
4. Mỗi Child Process tạo thư mục `./images/<cam_id>`.
5. Trong Child Process, một `setInterval` 8000ms được thiết lập:
   - Tạo random browser headers.
   - Gửi GET request tới `giaothong.hochiminhcity.gov.vn`.
   - Băm buffer ảnh trả về bằng MD5.
   - Nếu hash khác với ảnh trước đó (ảnh có cập nhật) -> Ghi file vào ổ cứng.
6. Nếu Child Process lỗi (timeout, 500, network), nó gọi `process.exit(1)`.
7. Master lắng nghe event `exit`, chờ 2 giây và khởi động lại Child Process đó.
