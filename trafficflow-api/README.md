---
title: TrafficFlow API
emoji: 🚗
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
license: mit
---

# TrafficFlow API Backend

Đây là dịch vụ Backend FastAPI và mô hình AI Zero-shot Image Prior (ZIP) cho dự án TrafficFlow.
Hệ thống cung cấp các API để truy xuất camera giao thông TP.HCM, dự đoán lưu lượng xe cộ và proxy hình ảnh camera.

---

## 🚀 Hướng dẫn Đánh giá Mô hình (Model Evaluation)

Dự án cung cấp sẵn kịch bản kiểm thử tự động `test_batch_inference.py` để sinh viên/nhóm nghiên cứu có thể chạy hàng loạt ảnh và lấy kết quả thống kê.

### 1. Cách chạy kịch bản kiểm thử (Script)

1. Cài đặt thư viện: `pip install httpx`
2. Tạo thư mục `test_images/` nằm cùng cấp với file script và chép các ảnh camera giao thông cần kiểm thử vào (hỗ trợ `.jpg`, `.png`).
3. Chạy lệnh: `python test_batch_inference.py`
4. Code sẽ tự động gửi ảnh lên Hugging Face Endpoint và xuất ra file báo cáo `evaluation_results.csv`.

_(Lưu ý: Mặc định script sẽ tạm dừng 1 giây giữa các ảnh để tránh làm quá tải (spam) Endpoint)._

### 2. Giải thích các Thông số Đầu ra (Output Parameters)

Kết quả trong file `.csv` chứa các tham số quan trọng sau:

- **`total_count`**: Tổng số phương tiện đếm được trong ảnh.
- **`car_count` / `motorbike_count`**: Số lượng dự đoán bóc tách riêng từng loại xe (Dựa trên tỷ lệ ước tính của hệ thống).
- **`density_level`**: Phân loại mức độ kẹt xe AI đánh giá:
  - `low` (Thông thoáng): Mật độ xe thưa thớt, đường trống.
  - `moderate` (Đông vừa): Xe bắt đầu đông nhưng vẫn di chuyển ổn định.
  - `heavy` (Kẹt xe): Lượng xe rất đông, có dấu hiệu ùn ứ.
  - `severe` (Kẹt cứng): Lòng đường đặc kín xe, không thể di chuyển.
- **`latency_seconds`**: Thời gian phản hồi (tính bằng giây). Bao gồm thời gian mạng truyền tải (Network latency) + Thời gian mô hình AI phân tích (Inference time).
