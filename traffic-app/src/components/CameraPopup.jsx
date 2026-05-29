import { useState, useEffect, useCallback, useRef } from 'react';
import { getCameraImageUrl } from '../data/cameras';
import {
  LuScanSearch,
  LuClock,
  LuCar,
  LuBike,
  LuActivity,
  LuTally5,
  LuTrendingUp,
  LuTrash2,
  LuSave,
  LuPenTool,
  LuCircleX,
  LuRotateCcw,
  LuX,
} from 'react-icons/lu';

const DENSITY_CONFIG = {
  low: { label: 'Thông thoáng', color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
  moderate: { label: 'Đông vừa', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  heavy: { label: 'Kẹt xe', color: '#ef4444', bg: 'rgba(239,68,68,0.1)' },
  severe: { label: 'Kẹt cứng', color: '#991b1b', bg: 'rgba(153,27,27,0.12)' },
};

const API_URL = import.meta.env.VITE_API_URL || '/api';

function loadStoredRoi(cameraId) {
  try {
    const rois = JSON.parse(localStorage.getItem('camera_rois') || '{}');
    return rois[cameraId] || [];
  } catch (e) {
    console.error("Failed to load ROI from localStorage:", e);
    return [];
  }
}

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

export default function CameraPopup({ camera, onClose }) {
  const [imageUrl, setImageUrl] = useState(getCameraImageUrl(camera.id));
  const [prediction, setPrediction] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showHeatmap, setShowHeatmap] = useState(false);

  // SVG Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [roiState, setRoiState] = useState(() => ({
    cameraId: camera.id,
    points: loadStoredRoi(camera.id),
  }));
  const imgWrapRef = useRef(null);
  const roiPoints = roiState.cameraId === camera.id ? roiState.points : loadStoredRoi(camera.id);

  const setRoiPoints = useCallback((nextPoints) => {
    setRoiState((prev) => ({
      cameraId: camera.id,
      points: typeof nextPoints === 'function' ? nextPoints(prev.cameraId === camera.id ? prev.points : loadStoredRoi(camera.id)) : nextPoints,
    }));
  }, [camera.id]);

  // Auto-refresh image every 5 seconds to simulate real-time feed
  useEffect(() => {
    const interval = setInterval(() => {
      setImageUrl(getCameraImageUrl(camera.id));
    }, 5000);
    return () => clearInterval(interval);
  }, [camera.id]);

  // Sync ROI from backend on camera.id change
  useEffect(() => {
    let active = true;
    const fetchBackendRoi = async () => {
      try {
        const res = await fetch(`${API_URL}/cameras/${camera.id}/roi`);
        if (res.ok && active) {
          const data = await res.json();
          if (data && data.roi_polygon) {
            const rois = JSON.parse(localStorage.getItem('camera_rois') || '{}');
            if (data.roi_polygon.length >= 3) {
              rois[camera.id] = data.roi_polygon;
              localStorage.setItem('camera_rois', JSON.stringify(rois));
              setRoiPoints(data.roi_polygon);
            } else {
              delete rois[camera.id];
              localStorage.setItem('camera_rois', JSON.stringify(rois));
              setRoiPoints([]);
            }
          }
        }
      } catch (err) {
        console.error("Failed to sync ROI from backend:", err);
        const localRoi = loadStoredRoi(camera.id);
        setRoiPoints(localRoi);
      }
    };
    fetchBackendRoi();
    return () => { active = false; };
  }, [camera.id, setRoiPoints]);

  // Fetch prediction history
  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/predict/camera/${camera.id}/history`);
      if (res.ok) {
        const data = await res.json();
        if (data?.history) setHistory(data.history);
      }
    } catch { /* ignore */ }
  }, [camera.id]);

  const handlePredict = async (points = roiPoints) => {
    setLoading(true);
    setError(null);
    try {
      const imageResponse = await fetch(imageUrl);
      if (!imageResponse.ok) throw new Error('Không thể lấy ảnh từ HCMC');
      const imageBlob = await imageResponse.blob();

      const formData = new FormData();
      formData.append('file', imageBlob, 'camera.jpg');

      if (points.length >= 3) {
        formData.append('roi_polygon', JSON.stringify(points));
      }

      const predictResponse = await fetch(`${API_URL}/predict?heatmap=true`, {
        method: 'POST',
        body: formData,
      });

      if (!predictResponse.ok) throw new Error('AI Model phân tích thất bại');
      const data = await predictResponse.json();
      setPrediction(data.prediction);

      await fetchHistory();
    } catch (err) {
      console.error(err);
      setError('Lỗi: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSvgClick = (e) => {
    if (!isDrawing || !imgWrapRef.current) return;
    const rect = imgWrapRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setRoiPoints((prev) => [...prev, [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000]]);
  };

  const handleUndoPoint = () => {
    setRoiPoints((prev) => prev.slice(0, -1));
  };

  const handleClearRoi = async () => {
    setRoiPoints([]);
    setPrediction(null);
    try {
      const rois = JSON.parse(localStorage.getItem('camera_rois') || '{}');
      delete rois[camera.id];
      localStorage.setItem('camera_rois', JSON.stringify(rois));

      await fetch(`${API_URL}/cameras/${camera.id}/roi`, { method: 'DELETE' });
    } catch (err) {
      console.error("Failed to delete ROI on backend:", err);
    }
  };

  const handleSaveRoi = async () => {
    try {
      const rois = JSON.parse(localStorage.getItem('camera_rois') || '{}');
      if (roiPoints.length >= 3) {
        rois[camera.id] = roiPoints;
        localStorage.setItem('camera_rois', JSON.stringify(rois));

        try {
          await fetch(`${API_URL}/cameras/${camera.id}/roi`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roi_polygon: roiPoints }),
          });
        } catch (err) {
          console.error("Failed to save ROI to backend:", err);
        }
      } else {
        delete rois[camera.id];
        localStorage.setItem('camera_rois', JSON.stringify(rois));

        try {
          await fetch(`${API_URL}/cameras/${camera.id}/roi`, { method: 'DELETE' });
        } catch (err) {
          console.error("Failed to delete ROI on backend:", err);
        }
      }

      setPrediction(null);
      setIsDrawing(false);
      if (roiPoints.length >= 3) {
        await handlePredict(roiPoints);
      }
    } catch (e) {
      console.error("Failed to save ROI:", e);
    }
  };

  const hasRoadSegment = roiPoints.length >= 3;
  const globalDensityLevel = prediction?.global_density_level || prediction?.density_level;
  const globalDensity = DENSITY_CONFIG[globalDensityLevel] || DENSITY_CONFIG.low;
  const roiDensity = DENSITY_CONFIG[prediction?.roi_congestion_level] || DENSITY_CONFIG.low;
  const primaryDensity = prediction?.has_roi ? roiDensity : globalDensity;

  const handlePopupEvents = (e) => {
    e.stopPropagation();
    if (e.nativeEvent) {
      e.nativeEvent.stopPropagation();
    }
  };

  return (
    <div
      className="camera-popup"
      onClick={handlePopupEvents}
      onMouseDown={handlePopupEvents}
      onMouseUp={handlePopupEvents}
      onMouseMove={handlePopupEvents}
      onDoubleClick={handlePopupEvents}
      onContextMenu={handlePopupEvents}
      onWheel={handlePopupEvents}
    >
      {/* Image Container Block */}
      <div
        className="camera-popup__img-wrap"
        style={{ position: 'relative', cursor: isDrawing ? 'crosshair' : 'default' }}
        ref={imgWrapRef}
        onClick={handleSvgClick}
      >
        {!showHeatmap && (
          <img
            src={imageUrl}
            alt={`Camera ${camera.name}`}
            loading="eager"
            decoding="async"
            style={{ pointerEvents: 'none' }}
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
            style={{ pointerEvents: 'none' }}
          />
        )}

        {/* SVG Drawing/Viewer Canvas */}
        <svg
          style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            pointerEvents: isDrawing ? 'auto' : 'none', zIndex: 5
          }}
        >
          {roiPoints.length > 0 && (
            <>
              {hasRoadSegment ? (
                <polygon
                  points={roiPoints.map(([x, y]) => `${x * 100}%,${y * 100}%`).join(' ')}
                  fill="rgba(59, 130, 246, 0.25)"
                  stroke="#3b82f6"
                  strokeWidth="2"
                />
              ) : (
                <polyline
                  points={roiPoints.map(([x, y]) => `${x * 100}%,${y * 100}%`).join(' ')}
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth="2"
                />
              )}
              {roiPoints.map(([x, y], idx) => (
                <circle
                  key={idx}
                  cx={`${x * 100}%`}
                  cy={`${y * 100}%`}
                  r="4"
                  fill="#ffffff"
                  stroke="#2563eb"
                  strokeWidth="2"
                />
              ))}
            </>
          )}
        </svg>

        {isDrawing && (
          <div
            style={{
              position: 'absolute', left: 8, bottom: 8, zIndex: 10,
              padding: '4px 8px', borderRadius: 6, background: 'rgba(15, 23, 42, 0.76)',
              color: '#fff', fontSize: 11, fontWeight: 600, backdropFilter: 'blur(4px)'
            }}
          >
            {roiPoints.length < 3 ? `${roiPoints.length}/3 điểm` : 'Đã chọn mặt đường'}
          </div>
        )}

        {prediction?.heatmap_base64 && !isDrawing && (
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

      {/* Main Metadata and Control Panel */}
      <div className="camera-popup__info">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div className="camera-popup__title">{camera.name}</div>
            <div className="camera-popup__subtitle">{camera.district}</div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#64748b', padding: '4px', borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.2s', marginTop: '-4px'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.05)' }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
              title="Đóng"
            >
              <LuX size={18} />
            </button>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
          {!isDrawing ? (
            <>
              <button
                onClick={() => {
                  setIsDrawing(true);
                  setShowHeatmap(false);
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1',
                  background: '#f8fafc', color: '#334155', cursor: 'pointer', fontWeight: 700
                }}
              >
                <LuPenTool size={14} />
                {hasRoadSegment ? 'Sửa mặt đường' : 'Chọn mặt đường'}
              </button>
              {hasRoadSegment && (
                <button
                  onClick={() => handlePredict()}
                  disabled={loading}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                    padding: '6px 10px', borderRadius: 6, border: 'none',
                    background: '#2563eb', color: '#fff', cursor: 'pointer', fontWeight: 700
                  }}
                >
                  <LuScanSearch size={14} />
                  {loading ? 'Đang đo...' : 'Đo ùn tắc'}
                </button>
              )}
            </>
          ) : (
            <>
              <button
                onClick={handleSaveRoi}
                disabled={!hasRoadSegment || loading}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  padding: '6px 10px', borderRadius: 6, border: 'none',
                  background: hasRoadSegment ? '#10b981' : '#cbd5e1',
                  color: 'white', cursor: hasRoadSegment ? 'pointer' : 'not-allowed', fontWeight: 700
                }}
              >
                <LuSave size={14} />
                Lưu & đo
              </button>
              <button
                onClick={handleUndoPoint}
                disabled={roiPoints.length === 0}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1',
                  background: '#f8fafc', color: '#475569', cursor: 'pointer', fontWeight: 600
                }}
              >
                <LuRotateCcw size={14} />
                Lùi
              </button>
              <button
                onClick={handleClearRoi}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  padding: '6px 10px', borderRadius: 6, border: '1px solid #ef4444',
                  background: 'transparent', color: '#ef4444', cursor: 'pointer', fontWeight: 600
                }}
              >
                <LuTrash2 size={14} />
                Xóa
              </button>
              <button
                onClick={() => {
                  setIsDrawing(false);
                  setRoiPoints(loadStoredRoi(camera.id));
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1',
                  background: '#f8fafc', color: '#64748b', cursor: 'pointer', fontWeight: 600
                }}
              >
                <LuCircleX size={14} />
                Hủy
              </button>
            </>
          )}
        </div>

        <div style={{ marginTop: 10 }}>
          {prediction ? (
            <div className="prediction-result" style={{ background: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                  {prediction.has_roi ? 'ÙN TẮC MẶT ĐƯỜNG' : 'KẾT QUẢ TOÀN KHUNG'}
                </span>
                <span className="prediction-result__time" style={{ fontSize: 10, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 3 }}>
                  <LuClock size={10} />
                  {prediction.inference_time_ms}ms
                </span>
              </div>

              <div
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px', borderRadius: 8, background: primaryDensity.bg,
                  border: `1px solid ${primaryDensity.color}33`
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: primaryDensity.color, fontWeight: 800, fontSize: 15 }}>
                  <LuActivity size={16} />
                  {primaryDensity.label}
                </span>
                {prediction.has_roi && prediction.roi_density_score != null && (
                  <strong style={{ color: primaryDensity.color, fontSize: 16 }}>{prediction.roi_density_score}</strong>
                )}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                <div style={{ background: '#f8fafc', borderRadius: 8, padding: 8, textAlign: 'center' }}>
                  <LuCar size={14} color="#3b82f6" />
                  <div style={{ fontWeight: 800, color: '#1e293b' }}>{prediction.has_roi ? prediction.roi_car_count ?? 0 : prediction.car_count}</div>
                  <div style={{ fontSize: 10, color: '#64748b' }}>Ô tô</div>
                </div>
                <div style={{ background: '#f8fafc', borderRadius: 8, padding: 8, textAlign: 'center' }}>
                  <LuBike size={14} color="#8b5cf6" />
                  <div style={{ fontWeight: 800, color: '#1e293b' }}>{prediction.has_roi ? prediction.roi_motorbike_count ?? 0 : prediction.motorbike_count}</div>
                  <div style={{ fontSize: 10, color: '#64748b' }}>Xe máy</div>
                </div>
                <div style={{ background: '#f8fafc', borderRadius: 8, padding: 8, textAlign: 'center' }}>
                  <LuTally5 size={14} color="#0f172a" />
                  <div style={{ fontWeight: 800, color: '#1e293b' }}>{prediction.has_roi ? prediction.roi_count ?? 0 : prediction.total_count}</div>
                  <div style={{ fontSize: 10, color: '#64748b' }}>Tổng</div>
                </div>
              </div>

              {prediction.has_roi ? (
                <div style={{ fontSize: 10, color: '#64748b', textAlign: 'center', background: '#f8fafc', padding: 5, borderRadius: 6 }}>
                  Intersection: density map ∩ mặt đường · {(prediction.roi_area_ratio * 100).toFixed(1)}% khung ảnh
                </div>
              ) : (
                <button
                  onClick={() => {
                    setIsDrawing(true);
                    setShowHeatmap(false);
                  }}
                  className="predict-button"
                  style={{ marginTop: 2, fontSize: 12, padding: '7px 10px' }}
                >
                  <LuPenTool size={14} />
                  Chọn mặt đường để đo đúng đề tài
                </button>
              )}

              <TrendSparkline history={history} />
            </div>
          ) : hasRoadSegment ? (
            <button
              onClick={() => handlePredict()}
              disabled={loading || isDrawing}
              className="predict-button"
            >
              <LuScanSearch size={16} />
              {loading ? 'Đang đo...' : 'Đo ùn tắc mặt đường'}
            </button>
          ) : (
            <button
              onClick={() => {
                setIsDrawing(true);
                setShowHeatmap(false);
              }}
              disabled={loading}
              className="predict-button"
            >
              <LuPenTool size={16} />
              Chọn mặt đường
            </button>
          )}
          {error && <div style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px' }}>{error}</div>}
        </div>
      </div>
    </div>
  );
}