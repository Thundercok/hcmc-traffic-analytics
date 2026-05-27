/*
 * Camera data extracted from CrawlCamera project (District 7, HCMC)
 * Each camera has real coordinates and a real endpoint URL.
 */

const CAMERA_BASE_URL =
  "https://giaothong.hochiminhcity.gov.vn/render/ImageHandler.ashx";

export const cameras = [
  {
    id: "56df8381c062921100c143e2",
    name: "Nguyễn Văn Linh - Nguyễn Hữu Thọ",
    district: "Quận 7",
    lat: 10.7325,
    lng: 106.6989,
  },
  {
    id: "586e6c43d965e61100fcef42",
    name: "Nguyễn Văn Linh - Huỳnh Tấn Phát",
    district: "Quận 7",
    lat: 10.7365,
    lng: 106.7215,
  },
  {
    id: "5a0e9a38d965e60f38fcef46",
    name: "Nguyễn Thị Thập - Lâm Văn Bền",
    district: "Quận 7",
    lat: 10.7395,
    lng: 106.7002,
  },
  {
    id: "5a0e9a6bd965e60f38fcef47",
    name: "Huỳnh Tấn Phát - Trần Xuân Soạn",
    district: "Quận 7",
    lat: 10.745,
    lng: 106.725,
  },
  {
    id: "58e1e039d965e61100fcef44",
    name: "Phú Mỹ Hưng - Tân Phú",
    district: "Quận 7",
    lat: 10.729,
    lng: 106.718,
  },
  {
    id: "5d8e4bc9fe5c1b001195b6c1",
    name: "Nguyễn Lương Bằng - Mai Chí Thọ",
    district: "Quận 7",
    lat: 10.741,
    lng: 106.706,
  },
];

/**
 * Backend API base URL.
 * Khi host backend lên (production), hãy tạo file .env trong thư mục traffic-app
 * chứa biến: VITE_API_URL=https://your-backend-host/api
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

/**
 * Lấy link ảnh camera:
 * - Nếu VITE_API_URL được cấu hình (production / backend), gọi endpoint proxy backend: `${API_BASE_URL}/camera/{id}/image`
 * - Nếu không (dev), fallback sang dev proxy Vite `/hcmc-camera/...`
 */
export function getCameraImageUrl(cameraId) {
  const t = Date.now();
  if (API_BASE_URL) {
    // Backend exposes: GET {API_BASE_URL}/camera/{id}/image
    // Ensure there is no trailing slash duplication
    const base = API_BASE_URL.replace(/\/+$/, "");
    return `${base}/camera/${encodeURIComponent(cameraId)}/image?t=${t}`;
  }
  // Dev fallback (vite proxy)
  return `/hcmc-camera/render/ImageHandler.ashx?id=${encodeURIComponent(cameraId)}&t=${t}`;
}

export default cameras;
