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
  LuZap,
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
  const [floodData, setFloodData] = useState(null);
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
  const dragRectRef = useRef(null);
  const roiPoints = roiState.cameraId === camera.id ? roiState.points : loadStoredRoi(camera.id);

  const validRoiPoints = Array.isArray(roiPoints)
    ? roiPoints.filter(p => Array.isArray(p) && p.length === 2 && typeof p[0] === 'number' && typeof p[1] === 'number')
    : [];
  const hasRoadSegment = validRoiPoints.length >= 3;

  const currentPointsRef = useRef([]);

  // Sync mutable ref with state when state changes
  useEffect(() => {
    currentPointsRef.current = roiPoints;
  }, [roiPoints]);

  const setRoiPoints = useCallback((nextPoints) => {
    setRoiState((prev) => ({
      cameraId: camera.id,
      points: typeof nextPoints === 'function' ? nextPoints(prev.cameraId === camera.id ? prev.points : loadStoredRoi(camera.id)) : nextPoints,
    }));
  }, [camera.id]);

  // Reset state when camera ID changes to prevent showing stale data from the previous camera
  useEffect(() => {
    setImageUrl(getCameraImageUrl(camera.id));
    setPrediction(null);
    setHistory([]);
    setLoading(false);
    setError(null);
    setShowHeatmap(false);
    setIsDrawing(false);
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
              if (!camera.has_roi || camera.is_auto_roi !== data.is_auto) {
                window.dispatchEvent(new CustomEvent('cameraRoiChanged', {
                  detail: { cameraId: camera.id, hasRoi: true, isAutoRoi: data.is_auto }
                }));
              }
            } else {
              delete rois[camera.id];
              localStorage.setItem('camera_rois', JSON.stringify(rois));
              setRoiPoints([]);
              if (camera.has_roi) {
                window.dispatchEvent(new CustomEvent('cameraRoiChanged', {
                  detail: { cameraId: camera.id, hasRoi: false, isAutoRoi: false }
                }));
              }
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
  }, [camera, setRoiPoints]);

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
      let url = `${API_URL}/predict/camera/${camera.id}?heatmap=true`;
      if (points && points.length >= 3) {
        url += `&roi_polygon=${encodeURIComponent(JSON.stringify(points))}`;
      }

      const predictResponse = await fetch(url);
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

  // SVG Point dragging state
  const [draggedPointIndex, setDraggedPointIndex] = useState(null);
  const justDraggedRef = useRef(false);

  // Auto-generate standard perspective road trapezoid
  const handleAutoRoi = () => {
    const defaultTrapezoid = [
      [0.35, 0.4],
      [0.65, 0.4],
      [0.9, 0.95],
      [0.1, 0.95]
    ];
    setRoiPoints(defaultTrapezoid);
    setIsDrawing(true);
    setShowHeatmap(false);
  };

  // Add event listener to window for robust dragging across the window coordinates
  useEffect(() => {
    if (draggedPointIndex === null) return;

    const handleWindowMouseMove = (e) => {
      // Prevent browser default actions (like text selection or image drag-and-drop)
      e.preventDefault();

      if (!imgWrapRef.current) return;
      const rect = imgWrapRef.current.getBoundingClientRect();
      
      const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));

      const rx = Math.round(x * 1000) / 1000;
      const ry = Math.round(y * 1000) / 1000;

      // Update mutable ref coordinates
      const nextPoints = [...currentPointsRef.current];
      nextPoints[draggedPointIndex] = [rx, ry];
      currentPointsRef.current = nextPoints;

      // Buttery smooth dragging: Direct DOM updates to bypass React re-rendering lag
      const circles = imgWrapRef.current.querySelectorAll('.camera-popup__roi-point');
      if (circles && circles[draggedPointIndex]) {
        circles[draggedPointIndex].setAttribute('cx', `${rx * 100}%`);
        circles[draggedPointIndex].setAttribute('cy', `${ry * 100}%`);
      }

      const pointsStr = nextPoints.map(([px, py]) => `${px * 1000},${py * 1000}`).join(' ');
      const polygon = imgWrapRef.current.querySelector('polygon');
      if (polygon) {
        polygon.setAttribute('points', pointsStr);
      }
      const polyline = imgWrapRef.current.querySelector('polyline');
      if (polyline) {
        polyline.setAttribute('points', pointsStr);
      }
    };

    const handleWindowMouseUp = () => {
      if (draggedPointIndex !== null) {
        justDraggedRef.current = true;
        // Sync final coordinates to React state once on release
        setRoiPoints(currentPointsRef.current);
        setTimeout(() => {
          justDraggedRef.current = false;
        }, 50);
      }
      dragRectRef.current = null;
      setDraggedPointIndex(null);
    };

    const handleWindowTouchMove = (e) => {
      if (e.touches.length === 0) return;
      if (!imgWrapRef.current) return;
      
      if (e.cancelable) e.preventDefault();
      const rect = imgWrapRef.current.getBoundingClientRect();
      const touch = e.touches[0];
      const x = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
      const y = Math.max(0, Math.min(1, (touch.clientY - rect.top) / rect.height));

      const rx = Math.round(x * 1000) / 1000;
      const ry = Math.round(y * 1000) / 1000;

      // Update mutable ref coordinates
      const nextPoints = [...currentPointsRef.current];
      nextPoints[draggedPointIndex] = [rx, ry];
      currentPointsRef.current = nextPoints;

      // Buttery smooth dragging: Direct DOM updates
      const circles = imgWrapRef.current.querySelectorAll('.camera-popup__roi-point');
      if (circles && circles[draggedPointIndex]) {
        circles[draggedPointIndex].setAttribute('cx', `${rx * 100}%`);
        circles[draggedPointIndex].setAttribute('cy', `${ry * 100}%`);
      }

      const pointsStr = nextPoints.map(([px, py]) => `${px * 1000},${py * 1000}`).join(' ');
      const polygon = imgWrapRef.current.querySelector('polygon');
      if (polygon) {
        polygon.setAttribute('points', pointsStr);
      }
      const polyline = imgWrapRef.current.querySelector('polyline');
      if (polyline) {
        polyline.setAttribute('points', pointsStr);
      }
    };

    window.addEventListener('mousemove', handleWindowMouseMove, { passive: false });
    window.addEventListener('mouseup', handleWindowMouseUp);
    window.addEventListener('touchmove', handleWindowTouchMove, { passive: false });
    window.addEventListener('touchend', handleWindowMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleWindowMouseMove);
      window.removeEventListener('mouseup', handleWindowMouseUp);
      window.removeEventListener('touchmove', handleWindowTouchMove);
      window.removeEventListener('touchend', handleWindowMouseUp);
    };
  }, [draggedPointIndex, setRoiPoints]);

  const handlePointerDown = (e) => {
    // Only handle left clicks for pointer down (button 0) or touch pointers
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    if (!isDrawing || !imgWrapRef.current || draggedPointIndex !== null) return;
    if (e.target.closest('.camera-popup__roi-point')) return;

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

      window.dispatchEvent(new CustomEvent('cameraRoiChanged', {
        detail: { cameraId: camera.id, hasRoi: false }
      }));

      await fetch(`${API_URL}/cameras/${camera.id}/roi`, { method: 'DELETE' });
    } catch (err) {
      console.error("Failed to delete ROI on backend:", err);
    }
  };

  const handleSaveRoi = async () => {
    try {
      const rois = JSON.parse(localStorage.getItem('camera_rois') || '{}');
      if (validRoiPoints.length >= 3) {
        rois[camera.id] = validRoiPoints;
        localStorage.setItem('camera_rois', JSON.stringify(rois));

        window.dispatchEvent(new CustomEvent('cameraRoiChanged', {
          detail: { cameraId: camera.id, hasRoi: true }
        }));

        try {
          await fetch(`${API_URL}/cameras/${camera.id}/roi`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roi_polygon: validRoiPoints }),
          });
        } catch (err) {
          console.error("Failed to save ROI to backend:", err);
        }
      } else {
        delete rois[camera.id];
        localStorage.setItem('camera_rois', JSON.stringify(rois));

        window.dispatchEvent(new CustomEvent('cameraRoiChanged', {
          detail: { cameraId: camera.id, hasRoi: false }
        }));

        try {
          await fetch(`${API_URL}/cameras/${camera.id}/roi`, { method: 'DELETE' });
        } catch (err) {
          console.error("Failed to delete ROI on backend:", err);
        }
      }

      setPrediction(null);
      setIsDrawing(false);
      if (validRoiPoints.length >= 3) {
        await handlePredict(validRoiPoints);
      }
    } catch (e) {
      console.error("Failed to save ROI:", e);
    }
  };

  // Keyboard Shortcuts for calibration
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Escape to cancel/close
      if (e.key === 'Escape') {
        if (isDrawing) {
          setIsDrawing(false);
          setRoiPoints(loadStoredRoi(camera.id));
        } else {
          onClose?.();
        }
      }
      
      // Active drawing keyboard shortcuts
      if (isDrawing) {
        // Ctrl+Z or Backspace to undo point
        if (((e.ctrlKey || e.metaKey) && e.key === 'z') || e.key === 'Backspace') {
          e.preventDefault();
          handleUndoPoint();
        }
        
        // Ctrl+S or Enter to save (if valid)
        if (((e.ctrlKey || e.metaKey) && e.key === 's') || e.key === 'Enter') {
          if (validRoiPoints.length >= 3 && !loading) {
            e.preventDefault();
            handleSaveRoi();
          }
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isDrawing, validRoiPoints, loading, camera.id, onClose]);

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
        style={{ position: 'relative', cursor: isDrawing ? 'crosshair' : 'default', userSelect: 'none', WebkitUserSelect: 'none' }}
        ref={imgWrapRef}
        onPointerDown={handlePointerDown}
      >
        {!showHeatmap && (
          <img
            src={imageUrl}
            alt={`Camera ${camera.name}`}
            loading="eager"
            decoding="async"
            draggable="false"
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
            draggable="false"
            style={{ pointerEvents: 'none' }}
          />
        )}

        {/* SVG Drawing/Viewer Canvas - Vectors (Polygon/Polyline) Layer */}
        <svg
          viewBox="0 0 1000 1000"
          preserveAspectRatio="none"
          style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            pointerEvents: 'none', zIndex: 4
          }}
        >
          {validRoiPoints.length > 0 && (
            hasRoadSegment ? (
              <polygon
                points={validRoiPoints.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
                fill="rgba(59, 130, 246, 0.25)"
                stroke="#3b82f6"
                strokeWidth="4"
              />
            ) : (
              <polyline
                points={validRoiPoints.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
                fill="none"
                stroke="#3b82f6"
                strokeWidth="4"
              />
            )
          )}
        </svg>

        {/* SVG Drawing/Viewer Canvas - Interactive Circles (Handles) Layer */}
        <svg
          style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            pointerEvents: 'none', zIndex: 5
          }}
        >
          {validRoiPoints.length > 0 && validRoiPoints.map(([x, y], idx) => (
            <circle
              key={idx}
              cx={`${x * 100}%`}
              cy={`${y * 100}%`}
              r={draggedPointIndex === idx ? 8 : 5}
              className={`camera-popup__roi-point ${draggedPointIndex === idx ? 'camera-popup__roi-point--dragging' : ''}`}
              fill="#ffffff"
              stroke="#2563eb"
              strokeWidth="2.5"
              style={{
                cursor: isDrawing ? (draggedPointIndex === idx ? 'grabbing' : 'grab') : 'default',
                pointerEvents: isDrawing ? 'auto' : 'none'
              }}
              onMouseDown={(e) => {
                if (!isDrawing) return;
                e.preventDefault();
                e.stopPropagation();
                if (imgWrapRef.current) {
                  dragRectRef.current = imgWrapRef.current.getBoundingClientRect();
                }
                setDraggedPointIndex(idx);
              }}
              onTouchStart={(e) => {
                if (!isDrawing) return;
                e.preventDefault();
                e.stopPropagation();
                if (imgWrapRef.current) {
                  dragRectRef.current = imgWrapRef.current.getBoundingClientRect();
                }
                setDraggedPointIndex(idx);
              }}
              onClick={(e) => e.stopPropagation()}
            />
          ))}
        </svg>

        {isDrawing && (
          <div
            style={{
              position: 'absolute', left: 8, top: 8, zIndex: 3,
              padding: '4px 8px', borderRadius: 6, background: 'rgba(15, 23, 42, 0.76)',
              color: '#fff', fontSize: 11, fontWeight: 600, backdropFilter: 'blur(4px)',
              pointerEvents: 'none'
            }}
          >
            {validRoiPoints.length < 3 ? `${validRoiPoints.length}/3 điểm` : 'Đã chọn mặt đường'}
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <div className="camera-popup__title" style={{ margin: 0 }}>{camera.name}</div>
              {!camera.has_roi ? (
                <span className="badge badge--warning">Chưa đo</span>
              ) : camera.is_auto_roi ? (
                <span className="badge badge--info" title="Mặt đường được AI dựng mẫu tự động">AI Mẫu</span>
              ) : (
                <span className="badge badge--success" title="Mặt đường đã đo thủ công">Thủ công</span>
              )}
            </div>
            <div className="camera-popup__subtitle" style={{ marginTop: '2px' }}>{camera.district}</div>
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

        
            {/* 🌊 Flood Severity & Vehicle Advice Widget */}
            {floodData?.flood && (
              <div style={{
                background: floodData.flood.severity_code === 2 ? '#fef2f2' : floodData.flood.severity_code === 1 ? '#eff6ff' : '#f0fdf4',
                borderRadius: 8,
                border: `1px solid ${floodData.flood.severity_code === 2 ? '#fca5a5' : floodData.flood.severity_code === 1 ? '#93c5fd' : '#86efac'}`,
                padding: '10px 12px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: floodData.flood.severity_code === 2 ? '#991b1b' : floodData.flood.severity_code === 1 ? '#1e40af' : '#166534', letterSpacing: '0.05em' }}>
                    🌊 TRIỀU CƯỜNG & NGẬP NƯỚC {floodData.is_nhabe_hotspot ? '(RỐN NGẬP NHÀ BÈ)' : ''}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: '#ffffff', color: '#334155' }}>
                    {(floodData.flood.confidence * 100).toFixed(0)}% tin cậy
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 800, color: floodData.flood.severity_code === 2 ? '#dc2626' : floodData.flood.severity_code === 1 ? '#2563eb' : '#16a34a' }}>
                  {floodData.flood.severity_display}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 2, fontSize: 11 }}>
                  <div style={{ background: '#ffffff', padding: '6px 8px', borderRadius: 6, border: '1px solid #e2e8f0' }}>
                    <strong style={{ color: '#0f172a' }}>🏍️ Xe máy:</strong> <span style={{ color: '#334155' }}>{floodData.flood.motorbike_advice}</span>
                  </div>
                  <div style={{ background: '#ffffff', padding: '6px 8px', borderRadius: 6, border: '1px solid #e2e8f0' }}>
                    <strong style={{ color: '#0f172a' }}>🚗 Ô tô:</strong> <span style={{ color: '#334155' }}>{floodData.flood.car_advice}</span>
                  </div>
                </div>
              </div>
            )}

        {/* Banner Alert for Drawing Mode */}
        {isDrawing && (
          <div className="camera-popup__drawing-banner">
            <LuPenTool size={14} />
            <span>Chế độ vẽ: Click để chấm điểm HOẶC ấn <strong>Tự động</strong>, sau đó kéo các điểm để khớp mặt đường.</span>
          </div>
        )}

        {prediction && (
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
              <div style={{ background: '#f8fafc', borderRadius: 8, padding: 8, textAlign: 'center', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
                <LuCar size={14} color="#3b82f6" />
                <div style={{ fontWeight: 800, color: '#1e293b', fontSize: '14px', marginTop: '4px' }}>
                  {prediction.has_roi ? `${prediction.roi_car_count ?? 0}/${prediction.car_count}` : prediction.car_count}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 500 }}>Ô tô</div>
                {prediction.has_roi && (
                  <div style={{ fontSize: 9, color: '#3b82f6', fontWeight: 600, marginTop: 2 }}>
                    {prediction.car_count > 0 ? Math.round(((prediction.roi_car_count ?? 0) / prediction.car_count) * 100) : 0}%
                  </div>
                )}
              </div>
              <div style={{ background: '#f8fafc', borderRadius: 8, padding: 8, textAlign: 'center', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
                <LuBike size={14} color="#8b5cf6" />
                <div style={{ fontWeight: 800, color: '#1e293b', fontSize: '14px', marginTop: '4px' }}>
                  {prediction.has_roi ? `${prediction.roi_motorbike_count ?? 0}/${prediction.motorbike_count}` : prediction.motorbike_count}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 500 }}>Xe máy</div>
                {prediction.has_roi && (
                  <div style={{ fontSize: 9, color: '#8b5cf6', fontWeight: 600, marginTop: 2 }}>
                    {prediction.motorbike_count > 0 ? Math.round(((prediction.roi_motorbike_count ?? 0) / prediction.motorbike_count) * 100) : 0}%
                  </div>
                )}
              </div>
              <div style={{ background: '#f8fafc', borderRadius: 8, padding: 8, textAlign: 'center', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
                <LuTally5 size={14} color="#0f172a" />
                <div style={{ fontWeight: 800, color: '#1e293b', fontSize: '14px', marginTop: '4px' }}>
                  {prediction.has_roi ? `${prediction.roi_count ?? 0}/${prediction.total_count}` : prediction.total_count}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 500 }}>Tổng</div>
                {prediction.has_roi && (
                  <div style={{ fontSize: 9, color: '#475569', fontWeight: 600, marginTop: 2 }}>
                    {prediction.total_count > 0 ? Math.round(((prediction.roi_count ?? 0) / prediction.total_count) * 100) : 0}%
                  </div>
                )}
              </div>
            </div>

            {prediction.has_roi ? (
              <div style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '12px', 
                background: '#f8fafc', 
                padding: '14px', 
                borderRadius: '8px', 
                border: '1px solid #e2e8f0',
                fontSize: '12px',
                color: '#334155'
              }}>
                <div style={{ 
                  fontWeight: 700, 
                  color: '#1e293b', 
                  textTransform: 'uppercase', 
                  fontSize: '10px', 
                  letterSpacing: '0.05em', 
                  borderBottom: '1px solid #e2e8f0', 
                  paddingBottom: '6px', 
                  marginBottom: '2px' 
                }}>
                  Phân tích kỹ thuật phân đoạn (Segment Analytics)
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, color: '#475569' }}>
                      Road Mapping Ratio (mặt đường / khung ảnh)
                    </span>
                    <span style={{ fontWeight: 800, fontFamily: 'monospace', color: '#0f172a', fontSize: '13px' }}>
                      {(prediction.roi_area_ratio * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div style={{ fontSize: '10px', color: '#64748b', fontFamily: 'monospace' }}>
                    Formula: Area(ROI) / Area(Frame)
                  </div>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, color: '#475569' }}>
                      Congestion Index (Chỉ số ùn tắc PCU)
                    </span>
                    <span style={{ fontWeight: 800, fontFamily: 'monospace', color: '#ef4444', fontSize: '13px' }}>
                      {prediction.roi_density_score != null ? `${prediction.roi_density_score.toFixed(1)}%` : '0.0%'}
                    </span>
                  </div>
                  <div style={{ fontSize: '10px', color: '#64748b', fontFamily: 'monospace' }}>
                    Formula: PCU / Capacity = (Cars*2.0 + Bikes*0.4) / (ROI * 45.0)
                  </div>
                </div>
              </div>
            ) : (
              <div className="camera-popup__hint-text">
                💡 Phân tích toàn bộ khung ảnh. Chọn mặt đường bên dưới để phân tích chính xác theo phân đoạn.
              </div>
            )}

            <TrendSparkline history={history} />
          </div>
        )}

        {/* Unified Actions Layout */}
        <div className="camera-popup__actions-group">
          {isDrawing ? (
            <>
              <button
                onClick={handleAutoRoi}
                className="camera-popup__action-btn camera-popup__action-btn--primary"
                style={{ background: 'linear-gradient(135deg, #a855f7 0%, #7e22ce 100%)', boxShadow: '0 4px 12px rgba(168, 85, 247, 0.2)', color: 'white' }}
                title="Tự động tạo mặt đường mẫu"
              >
                <LuZap size={14} />
                Tự động
              </button>
              <button
                onClick={handleSaveRoi}
                disabled={!hasRoadSegment || loading}
                className="camera-popup__action-btn camera-popup__action-btn--success"
              >
                <LuSave size={14} />
                Lưu & đo
              </button>
              <button
                onClick={handleUndoPoint}
                disabled={validRoiPoints.length === 0}
                className="camera-popup__action-btn camera-popup__action-btn--secondary"
                title="Lùi 1 điểm"
              >
                <LuRotateCcw size={14} />
                Lùi
              </button>
              <button
                onClick={handleClearRoi}
                disabled={validRoiPoints.length === 0}
                className="camera-popup__action-btn camera-popup__action-btn--danger"
                title="Xóa tất cả các điểm đã vẽ"
              >
                <LuTrash2 size={14} />
                Xóa
              </button>
              <button
                onClick={() => {
                  setIsDrawing(false);
                  setRoiPoints(loadStoredRoi(camera.id));
                }}
                className="camera-popup__action-btn camera-popup__action-btn--secondary"
              >
                <LuCircleX size={14} />
                Hủy
              </button>
            </>
          ) : (
            <>
              {/* Not Drawing mode */}
              {!hasRoadSegment ? (
                <>
                  {/* Case 2A: No road segment defined */}
                  <button
                    onClick={() => {
                      setIsDrawing(true);
                      setShowHeatmap(false);
                    }}
                    className="camera-popup__action-btn camera-popup__action-btn--primary"
                  >
                    <LuPenTool size={14} />
                    Chọn mặt đường
                  </button>
                  <button
                    onClick={() => handlePredict([])}
                    disabled={loading}
                    className="camera-popup__action-btn camera-popup__action-btn--secondary"
                  >
                    <LuScanSearch size={14} />
                    {loading ? 'Đang đo...' : prediction ? 'Đo lại toàn khung' : 'Đo toàn khung'}
                  </button>
                </>
              ) : (
                <>
                  {/* Case 2B: Road segment exists */}
                  <button
                    onClick={() => handlePredict(validRoiPoints)}
                    disabled={loading}
                    className="camera-popup__action-btn camera-popup__action-btn--primary"
                  >
                    <LuScanSearch size={14} />
                    {loading ? 'Đang đo...' : prediction ? 'Đo lại' : 'Đo mặt đường'}
                  </button>
                  <button
                    onClick={() => {
                      setIsDrawing(true);
                      setShowHeatmap(false);
                    }}
                    className="camera-popup__action-btn camera-popup__action-btn--secondary"
                  >
                    <LuPenTool size={14} />
                    Sửa mặt đường
                  </button>
                  <button
                    onClick={handleClearRoi}
                    className="camera-popup__action-btn camera-popup__action-btn--danger"
                    style={{ flex: '0 0 auto', width: 'auto', minWidth: '40px', padding: '10px' }}
                    title="Xóa mặt đường"
                  >
                    <LuTrash2 size={15} />
                  </button>
                </>
              )}
            </>
          )}
        </div>

        {error && <div style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px', textAlign: 'center' }}>{error}</div>}
      </div>
    </div>
  );
}