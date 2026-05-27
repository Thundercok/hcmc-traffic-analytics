import React, { useState, useEffect, useCallback } from 'react';
import { getCameraImageUrl } from '../data/cameras';
import {
  LuScanSearch,
  LuClock,
  LuCar,
  LuBike,
  LuActivity,
  LuTally5,
  LuTrendingUp,
} from 'react-icons/lu';

const DENSITY_CONFIG = {
  low: { label: 'Thông thoáng', color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
  moderate: { label: 'Đông vừa', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  heavy: { label: 'Kẹt xe', color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
  severe: { label: 'Kẹt cứng', color: '#991b1b', bg: 'rgba(153,27,27,0.12)' },
};

const API_URL = import.meta.env.VITE_API_URL || '/api';

// ── Mini Sparkline SVG Chart ──
function TrendSparkline({ history }) {
  if (!history || history.length < 2) return null;

  const W = 200, H = 48, PAD = 4;
  const counts = history.map((h) => h.total_count);
  const maxVal = Math.max(...counts, 1);
  const minVal = Math.min(...counts, 0);
  const range = maxVal - minVal || 1;

  const points = counts.map((val, i) => {
    const x = PAD + (i / (counts.length - 1)) * (W - 2 * PAD);
    const y = H - PAD - ((val - minVal) / range) * (H - 2 * PAD);
    return `${x},${y}`;
  });

  const latest = counts[counts.length - 1];
  const prev = counts[counts.length - 2];
  const trendColor = latest > prev ? '#ef4444' : latest < prev ? '#10b981' : '#94a3b8';

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4, fontSize: 11, color: '#64748b' }}>
        <LuTrendingUp size={12} />
        <span>Xu hướng ({history.length} lần đo)</span>
      </div>
      <svg width={W} height={H} style={{ background: '#f8fafc', borderRadius: 6, border: '1px solid #e2e8f0' }}>
        {/* Grid lines */}
        <line x1={PAD} y1={H / 2} x2={W - PAD} y2={H / 2} stroke="#e2e8f0" strokeDasharray="3,3" />
        {/* Trend line */}
        <polyline
          points={points.join(' ')}
          fill="none"
          stroke={trendColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Latest point */}
        {points.length > 0 && (
          <circle
            cx={parseFloat(points[points.length - 1].split(',')[0])}
            cy={parseFloat(points[points.length - 1].split(',')[1])}
            r="3"
            fill={trendColor}
          />
        )}
        {/* Min/Max labels */}
        <text x={W - PAD} y={12} textAnchor="end" fontSize="9" fill="#94a3b8">{maxVal}</text>
        <text x={W - PAD} y={H - 2} textAnchor="end" fontSize="9" fill="#94a3b8">{minVal}</text>
      </svg>
    </div>
  );
}

export default function CameraPopup({ camera }) {
  const [imageUrl, setImageUrl] = useState(getCameraImageUrl(camera.id));
  const [prediction, setPrediction] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showHeatmap, setShowHeatmap] = useState(false);

  // Auto-refresh image every 5 seconds to simulate real-time feed
  useEffect(() => {
    const interval = setInterval(() => {
      setImageUrl(getCameraImageUrl(camera.id));
    }, 5000);
    return () => clearInterval(interval);
  }, [camera.id]);

  // Fetch prediction history
  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/predict/camera/${camera.id}/history`);
      if (res.ok) {
        const data = await res.json();
        if (data?.history) setHistory(data.history);
      }
    } catch (_) { /* ignore */ }
  }, [camera.id]);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Tải ảnh từ HCMC bằng mạng Việt Nam (qua Vite Proxy để né CORS)
      const imageResponse = await fetch(imageUrl);
      if (!imageResponse.ok) throw new Error('Không thể lấy ảnh từ HCMC');
      const imageBlob = await imageResponse.blob();

      // 2. Upload thẳng ảnh đó lên Hugging Face (tránh việc HF bị chặn IP)
      const formData = new FormData();
      formData.append('file', imageBlob, 'camera.jpg');

      const predictResponse = await fetch(`${API_URL}/predict?heatmap=true`, {
        method: 'POST',
        body: formData,
      });

      if (!predictResponse.ok) throw new Error('AI Model phân tích thất bại');
      const data = await predictResponse.json();
      setPrediction(data.prediction);

      // 3. Fetch updated history (trend chart)
      await fetchHistory();
    } catch (err) {
      console.error(err);
      setError('Lỗi: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const density = prediction ? DENSITY_CONFIG[prediction.density_level] || DENSITY_CONFIG.low : null;

  return (
    <div className="camera-popup">
      <div className="camera-popup__img-wrap" style={{ position: 'relative' }}>
        {!showHeatmap && (
          <img
            src={imageUrl}
            alt={`Camera ${camera.name}`}
            loading="eager"
            decoding="async"
            onError={(e) => {
              e.target.src = `https://placehold.co/400x300/e2e8f0/64748b?text=Camera+Offline`;
            }}
          />
        )}
        {showHeatmap && prediction?.heatmap_base64 && (
          <img
            src={prediction.heatmap_base64}
            alt={`Camera ${camera.name} Heatmap`}
            loading="eager"
            decoding="async"
          />
        )}
        {prediction?.heatmap_base64 && (
          <button 
            onClick={() => setShowHeatmap(!showHeatmap)}
            style={{ 
              position: 'absolute', bottom: 8, right: 8, background: showHeatmap ? '#ef4444' : 'rgba(15, 23, 42, 0.7)', 
              color: 'white', border: 'none', borderRadius: '4px', padding: '4px 8px', fontSize: '11px', 
              fontWeight: 600, cursor: 'pointer', zIndex: 10, backdropFilter: 'blur(4px)', transition: 'all 0.2s'
            }}
          >
            {showHeatmap ? "Hiển thị Ảnh thật" : "Hiển thị Heatmap AI"}
          </button>
        )}
      </div>
      <div className="camera-popup__info">
        <div className="camera-popup__title">{camera.name}</div>
        <div className="camera-popup__subtitle">{camera.district}</div>
        
        <div style={{ marginTop: '10px' }}>
          {prediction ? (
            <div className="prediction-result">
              {/* Vehicle counts row */}
              <div className="prediction-result__counts">
                <div className="prediction-result__count-item">
                  <LuCar size={16} color="#3b82f6" />
                  <span className="prediction-result__count-value">{prediction.car_count}</span>
                  <span className="prediction-result__count-label">Ô tô</span>
                </div>
                <div className="prediction-result__divider" />
                <div className="prediction-result__count-item">
                  <LuBike size={16} color="#8b5cf6" />
                  <span className="prediction-result__count-value">{prediction.motorbike_count}</span>
                  <span className="prediction-result__count-label">Xe máy</span>
                </div>
                <div className="prediction-result__divider" />
                <div className="prediction-result__count-item">
                  <LuTally5 size={16} color="#0f172a" />
                  <span className="prediction-result__count-value">{prediction.total_count}</span>
                  <span className="prediction-result__count-label">Tổng</span>
                </div>
              </div>

              {/* Status row */}
              <div className="prediction-result__status">
                <span
                  className="prediction-result__badge"
                  style={{ color: density.color, background: density.bg }}
                >
                  <LuActivity size={12} />
                  {density.label}
                </span>
                <span className="prediction-result__time">
                  <LuClock size={11} />
                  {prediction.inference_time_ms}ms
                </span>
              </div>

              {/* Trend Chart */}
              <TrendSparkline history={history} />

              {/* Re-predict button */}
              <button
                onClick={handlePredict}
                disabled={loading}
                className="predict-button"
                style={{ marginTop: 8, fontSize: 12, padding: '6px 10px' }}
              >
                <LuScanSearch size={14} />
                {loading ? 'Đang phân tích...' : 'Đếm lại'}
              </button>
            </div>
          ) : (
            <button 
              onClick={handlePredict} 
              disabled={loading}
              className="predict-button"
            >
              <LuScanSearch size={16} />
              {loading ? 'Đang phân tích...' : 'Dự đoán kẹt xe'}
            </button>
          )}
          {error && <div style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px' }}>{error}</div>}
        </div>
      </div>
    </div>
  );
}
