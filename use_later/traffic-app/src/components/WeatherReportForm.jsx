import React, { useState } from "react";
import { LuX, LuCloudRain, LuWaves, LuSun, LuCloud, LuUser, LuFileText } from "react-icons/lu";

export default function WeatherReportForm({ position, address, onClose, onReportSubmitted }) {
  const [weatherState, setWeatherState] = useState("rainy");
  const [rainIntensity, setRainIntensity] = useState("light");
  const [floodDepth, setFloodDepth] = useState(10);
  const [reporterName, setReporterName] = useState("");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const payload = {
      lat: position[0],
      lng: position[1],
      weather_state: weatherState,
      rain_intensity: weatherState === "rainy" || weatherState === "flooded" ? rainIntensity : "none",
      flood_depth_cm: weatherState === "flooded" ? Number(floodDepth) : 0,
      reporter_name: reporterName.trim() || "Cộng đồng",
      notes: notes.trim() || null,
    };

    try {
      const apiUrl = import.meta.env.VITE_API_URL || "/api";
      const response = await fetch(`${apiUrl}/weather/report`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error("Không thể gửi báo cáo. Vui lòng thử lại.");
      }

      onReportSubmitted?.();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="weather-form-overlay">
      <div className="weather-form-container glass-card">
        <div className="weather-form-header">
          <h3>Báo Cáo Thời Tiết</h3>
          <button className="close-btn" onClick={onClose}>
            <LuX size={20} />
          </button>
        </div>

        <div className="weather-form-address">
          <span>📍 Vị trí:</span> {address || `${position[0].toFixed(5)}, ${position[1].toFixed(5)}`}
        </div>

        <form onSubmit={handleSubmit}>
          {error && <div className="weather-form-error">{error}</div>}

          {/* Chọn trạng thái thời tiết */}
          <div className="form-group">
            <label>Tình trạng thời tiết:</label>
            <div className="weather-state-options">
              <button
                type="button"
                className={`state-btn ${weatherState === "sunny" ? "active sunny" : ""}`}
                onClick={() => setWeatherState("sunny")}
              >
                <LuSun size={20} />
                <span>Nắng</span>
              </button>
              <button
                type="button"
                className={`state-btn ${weatherState === "cloudy" ? "active cloudy" : ""}`}
                onClick={() => setWeatherState("cloudy")}
              >
                <LuCloud size={20} />
                <span>Nhiều mây</span>
              </button>
              <button
                type="button"
                className={`state-btn ${weatherState === "rainy" ? "active rainy" : ""}`}
                onClick={() => setWeatherState("rainy")}
              >
                <LuCloudRain size={20} />
                <span>Mưa</span>
              </button>
              <button
                type="button"
                className={`state-btn ${weatherState === "flooded" ? "active flooded" : ""}`}
                onClick={() => setWeatherState("flooded")}
              >
                <LuWaves size={20} />
                <span>Ngập lụt</span>
              </button>
            </div>
          </div>

          {/* Cường độ mưa (nếu chọn Mưa hoặc Ngập lụt) */}
          {(weatherState === "rainy" || weatherState === "flooded") && (
            <div className="form-group fade-in">
              <label>Cường độ mưa:</label>
              <div className="intensity-options">
                <button
                  type="button"
                  className={`intensity-btn ${rainIntensity === "light" ? "active" : ""}`}
                  onClick={() => setRainIntensity("light")}
                >
                  Mưa nhỏ
                </button>
                <button
                  type="button"
                  className={`intensity-btn ${rainIntensity === "heavy" ? "active" : ""}`}
                  onClick={() => setRainIntensity("heavy")}
                >
                  Mưa lớn / Giông
                </button>
              </div>
            </div>
          )}

          {/* Độ sâu ngập lụt (nếu chọn Ngập lụt) */}
          {weatherState === "flooded" && (
            <div className="form-group fade-in">
              <label>Độ sâu ngập ước tính (cm): {floodDepth} cm</label>
              <input
                type="range"
                min="5"
                max="100"
                step="5"
                value={floodDepth}
                onChange={(e) => setFloodDepth(Number(e.target.value))}
                className="depth-slider"
              />
              <div className="depth-indicators">
                <span>Mắt cá chân (5cm)</span>
                <span>Ngập nửa bánh xe (30cm)</span>
                <span>Ngập sâu (&gt;60cm)</span>
              </div>
            </div>
          )}

          {/* Thông tin người báo cáo */}
          <div className="form-group">
            <label htmlFor="reporter_name">
              <LuUser size={16} /> Người báo cáo:
            </label>
            <input
              type="text"
              id="reporter_name"
              placeholder="Nhập tên của bạn (Tùy chọn)"
              value={reporterName}
              onChange={(e) => setReporterName(e.target.value)}
              maxLength={50}
            />
          </div>

          {/* Ghi chú thêm */}
          <div className="form-group">
            <label htmlFor="notes">
              <LuFileText size={16} /> Ghi chú thêm:
            </label>
            <textarea
              id="notes"
              placeholder="VD: Đoạn đường Nguyễn Hữu Cảnh xe máy đang chết máy hàng loạt..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              maxLength={200}
            />
          </div>

          <button
            type="submit"
            className="submit-btn"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Đang gửi báo cáo..." : "Gửi báo cáo thực tế"}
          </button>
        </form>
      </div>
    </div>
  );
}
