import React, { useState, useEffect, useRef } from "react";
import {
  LuRoute,
  LuChevronUp,
  LuChevronDown,
  LuLocateFixed,
  LuMapPin,
  LuClock,
  LuCar,
  LuBike,
  LuNavigation,
  LuCornerUpLeft,
  LuCornerUpRight,
  LuUndo2,
  LuMoveUp,
  LuVideo,
  LuArrowUpDown,
  LuX,
  LuCheck,
  LuActivity,
} from "react-icons/lu";
import { MdTwoWheeler, MdDirectionsWalk } from "react-icons/md";

const TRAVEL_MODES = [
  { id: "car", label: "Ô tô", icon: LuCar },
  { id: "motorbike", label: "Xe máy", icon: MdTwoWheeler },
  { id: "bicycle", label: "Xe đạp", icon: LuBike },
  { id: "walking", label: "Đi bộ", icon: MdDirectionsWalk },
];

const SLIDER_LABELS = ["Hiện tại", "+1 giờ", "+2 giờ", "+4 giờ"];
const SLIDER_THRESHOLDS = [0, 5, 35, 65, 100]; // Derived from slider min=0, max=100

export default function ControlPanel({
  originText,
  setOriginText,
  destText,
  onOriginSelect,
  onDestinationSelect,
  onSwapLocations,
  sliderValue,
  onSliderChange,
  eta,
  distance,
  trafficLevel,
  navigationSteps,
  onStartNavigation,
  travelMode,
  onTravelModeChange,
  routeTraffic,
}) {
  const [localDestText, setLocalDestText] = useState("");
  const [originSuggestions, setOriginSuggestions] = useState([]);
  const [destSuggestions, setDestSuggestions] = useState([]);
  const [activeDropdown, setActiveDropdown] = useState(null); // "origin" | "dest"
  const [isExpanded, setIsExpanded] = useState(false);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || "/api";
        const res = await fetch(`${apiUrl}/cameras/stats`);
        if (res.ok) {
          const data = await res.json();
          setStats(data);
        }
      } catch (err) {
        console.error("Failed to fetch camera mapping stats", err);
      }
    };
    fetchStats();
    // Refresh stats every 10 seconds
    const interval = setInterval(fetchStats, 10000);
    
    // Listen to ROI changes and refresh stats immediately
    window.addEventListener("cameraRoiChanged", fetchStats);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener("cameraRoiChanged", fetchStats);
    };
  }, []);

  // Sync prop destText to local state when map is clicked
  useEffect(() => {
    if (destText !== undefined && destText !== null) {
      setLocalDestText(destText);
    }
  }, [destText]);

  const fetchSuggestions = async (query, setSuggestions) => {
    if (!query || query.length < 3) {
      setSuggestions([]);
      return;
    }
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&addressdetails=1&countrycodes=vn&limit=5`,
      );
      const data = await res.json();
      setSuggestions(data);
    } catch (err) {
      console.error("Lỗi khi tìm kiếm địa điểm", err);
    }
  };

  useEffect(() => {
    const timer = setTimeout(
      () => fetchSuggestions(originText, setOriginSuggestions),
      600,
    );
    return () => clearTimeout(timer);
  }, [originText]);

  useEffect(() => {
    const timer = setTimeout(
      () => fetchSuggestions(localDestText, setDestSuggestions),
      600,
    );
    return () => clearTimeout(timer);
  }, [localDestText]);

  const handleOriginChange = (e) => {
    setOriginText(e.target.value);
    setActiveDropdown("origin");
  };

  const handleDestChange = (e) => {
    setLocalDestText(e.target.value);
    setActiveDropdown("dest");
  };

  const selectSuggestion = (item, type) => {
    const point = {
      text: item.display_name,
      lat: parseFloat(item.lat),
      lon: parseFloat(item.lon),
    };
    if (type === "origin") {
      setOriginText(item.display_name);
      onOriginSelect?.(point);
      setActiveDropdown(null);
    } else {
      setLocalDestText(item.display_name);
      onDestinationSelect?.(point);
      setActiveDropdown(null);
    }
  };

  const clearInput = (type) => {
    if (type === "origin") {
      setOriginText("");
      onOriginSelect?.(null);
      setOriginSuggestions([]);
    } else {
      setLocalDestText("");
      onDestinationSelect?.(null);
      setDestSuggestions([]);
    }
  };

  const getTrafficVietnamese = (level) => {
    if (!level) return "Đang tính...";
    if (level === "low") return "Thông thoáng";
    if (level === "moderate") return "Đông vừa";
    if (level === "heavy") return "Kẹt xe";
    if (level === "severe") return "Kẹt cứng";
    return level;
  };

  const isHeavy =
    trafficLevel === "Kẹt nặng" ||
    trafficLevel === "Kẹt cứng" ||
    trafficLevel === "heavy" ||
    trafficLevel === "severe";
  const trafficColor = isHeavy
    ? "var(--error)"
    : trafficLevel === "moderate"
      ? "var(--warning)"
      : "var(--secondary)";
  const trafficText = getTrafficVietnamese(trafficLevel);

  const getLabelFromValue = (val) => {
    for (let i = SLIDER_THRESHOLDS.length - 1; i >= 0; i--) {
      if (val >= SLIDER_THRESHOLDS[i]) {
        return SLIDER_LABELS[i];
      }
    }
    return SLIDER_LABELS[0];
  };

  const getStepIcon = (instruction) => {
    if (instruction.includes("trái")) return <LuCornerUpLeft size={18} />;
    if (instruction.includes("phải")) return <LuCornerUpRight size={18} />;
    if (instruction.includes("quay đầu")) return <LuUndo2 size={18} />;
    return <LuMoveUp size={18} />;
  };

  return (
    <div
      className="control-panel"
      id="control-panel"
      style={{
        height: isExpanded ? "auto" : "60px",
        overflow: "hidden",
        cursor: isExpanded ? "default" : "pointer",
      }}
    >
      {/* Header Panel */}
      <div
        style={{
          padding: "16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "white",
        }}
        onClick={() => !isExpanded && setIsExpanded(true)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <LuRoute size={20} color="var(--primary)" />
          <span className="font-headline-md" style={{ fontSize: "16px" }}>
            Tra cứu lộ trình
          </span>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsExpanded(!isExpanded);
          }}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--on-surface-variant)",
            display: "flex",
            alignItems: "center",
          }}
        >
          {isExpanded ? <LuChevronUp size={22} /> : <LuChevronDown size={22} />}
        </button>
        <a
          href="/dashboard"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            window.history.pushState({}, "", "/dashboard");
            window.dispatchEvent(new PopStateEvent("popstate"));
          }}
          style={{
            display: "flex", alignItems: "center", gap: 4,
            padding: "4px 10px", borderRadius: 8,
            background: "#f1f5f9", border: "1px solid #e2e8f0",
            color: "#475569", fontSize: 12, fontWeight: 600,
            textDecoration: "none", marginLeft: 4,
          }}
          title="Dashboard"
        >
          <LuActivity size={13} />
          Dashboard
        </a>
      </div>

      <div
        className="control-panel__body"
        style={{ display: isExpanded ? "flex" : "none", paddingTop: 0 }}
      >
        {/* Camera Mapping Progress Stats */}
        {stats && (
          <div style={{
            background: "linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)",
            border: "1px solid #bbf7d0",
            borderRadius: "12px",
            padding: "10px 14px",
            marginTop: "10px",
            marginBottom: "12px",
            display: "flex",
            flexDirection: "column",
            gap: "5px",
            boxShadow: "0 2px 8px rgba(16, 185, 129, 0.04)"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "12px", fontWeight: "700", color: "#166534", display: "flex", alignItems: "center", gap: "6px" }}>
                <LuVideo size={14} />
                Số hóa mặt đường
              </span>
              <span style={{ fontSize: "12px", fontWeight: "800", color: "#15803d" }}>
                {stats.mapped_cameras} / {stats.total_cameras} (cam)
              </span>
            </div>
            
            {/* Progress bar container */}
            <div style={{
              width: "100%",
              height: "6px",
              background: "rgba(21, 128, 61, 0.1)",
              borderRadius: "10px",
              overflow: "hidden"
            }}>
              <div style={{
                width: `${stats.percentage_mapped}%`,
                height: "100%",
                background: "linear-gradient(90deg, #10b981 0%, #059669 100%)",
                borderRadius: "10px",
                transition: "width 0.4s cubic-bezier(0.4, 0, 0.2, 1)"
              }} />
            </div>
            
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#166534", opacity: 0.8 }}>
              <span>Hoàn thành: {stats.percentage_mapped}%</span>
              <span>Còn lại: {stats.unmapped_cameras} camera</span>
            </div>

            {/* Detailed breakdown counts */}
            <div style={{ 
              display: "flex", 
              flexDirection: "column", 
              gap: "3px", 
              borderTop: "1px dashed rgba(22, 101, 52, 0.2)", 
              paddingTop: "6px", 
              marginTop: "4px", 
              fontSize: "10.5px", 
              color: "#166534" 
            }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>✍️ Thủ công (do bạn vẽ):</span>
                <span style={{ fontWeight: "700" }}>{stats.manual_cameras || 0} cam</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>🤖 Tự động (AI dựng):</span>
                <span style={{ fontWeight: "700" }}>{stats.auto_cameras || 0} cam</span>
              </div>
            </div>
          </div>
        )}

        {/* Route Inputs */}
        <div className="route-inputs" style={{ position: "relative" }}>
          <div className="route-inputs__line" />
          
          <div className="route-input" style={{ position: "relative" }}>
            <LuLocateFixed size={18} className="icon-origin" />
            <input
              type="text"
              placeholder="Điểm đi (Ví dụ: Chợ Bến Thành)"
              value={originText}
              onChange={handleOriginChange}
              onFocus={() => setActiveDropdown("origin")}
              onBlur={() => setTimeout(() => setActiveDropdown(null), 200)}
            />
            {originText && (
              <button className="clear-input-btn" onClick={() => clearInput("origin")}>
                <LuX size={16} />
              </button>
            )}
            {activeDropdown === "origin" && originSuggestions.length > 0 && (
              <ul className="autocomplete-dropdown">
                {originSuggestions.map((s, idx) => (
                  <li key={idx} onMouseDown={() => selectSuggestion(s, "origin")}>
                    <LuMapPin size={14} style={{ minWidth: 14 }} />
                    <span className="truncate">{s.display_name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="route-input" style={{ position: "relative" }}>
            <LuMapPin size={18} className="icon-dest" />
            <input
              type="text"
              placeholder="Điểm đến (Ví dụ: Đại học Tôn Đức Thắng)"
              value={localDestText}
              onChange={handleDestChange}
              onFocus={() => setActiveDropdown("dest")}
              onBlur={() => setTimeout(() => setActiveDropdown(null), 200)}
            />
            {localDestText && (
              <button className="clear-input-btn" onClick={() => clearInput("dest")}>
                <LuX size={16} />
              </button>
            )}
            {activeDropdown === "dest" && destSuggestions.length > 0 && (
              <ul className="autocomplete-dropdown">
                {destSuggestions.map((s, idx) => (
                  <li key={idx} onMouseDown={() => selectSuggestion(s, "dest")}>
                    <LuMapPin size={14} style={{ minWidth: 14 }} />
                    <span className="truncate">{s.display_name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <button className="swap-locations-btn" onClick={onSwapLocations} title="Đảo ngược vị trí">
            <LuArrowUpDown size={18} />
          </button>
        </div>

        <div className="divider" />

        {/* Transport Mode Selector */}
        <div className="mode-selector">
          {TRAVEL_MODES.map((mode) => {
            const Icon = mode.icon;
            const isActive = travelMode === mode.id;
            return (
              <button
                key={mode.id}
                className={`mode-selector__btn ${isActive ? "mode-selector__btn--active" : ""}`}
                onClick={() => onTravelModeChange?.(mode.id)}
                title={mode.label}
              >
                <Icon size={20} />
                <span>{mode.label}</span>
              </button>
            );
          })}
        </div>

        <div className="divider" />

        {/* Predict Traffic Slider */}
        <div className="predict-slider">
          <div className="predict-slider__header">
            <label className="predict-slider__label font-label-md">
              <LuClock size={14} />
              Dự đoán giao thông
            </label>
            <span className="predict-slider__value font-label-md">
              {getLabelFromValue(sliderValue)}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={sliderValue}
            onChange={(e) => onSliderChange?.(Number(e.target.value))}
          />
          <div className="predict-slider__marks font-label-sm">
            {SLIDER_LABELS.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
        </div>

        {/* Summary Panel */}
        {distance && (
          <>
            <div
              className="summary-panel"
              style={{
                marginBottom: navigationSteps?.length > 0 ? "12px" : "0",
              }}
            >
              <div className="summary-left">
                <div className="summary-icon">
                  {(() => {
                    const SummaryIcon = TRAVEL_MODES.find(m => m.id === travelMode)?.icon || LuCar;
                    return <SummaryIcon size={20} />;
                  })()}
                </div>
                <div>
                  <div
                    className="summary-eta font-headline-md"
                    style={{ fontSize: 18 }}
                  >
                    {eta}
                  </div>
                  <div className="summary-label font-label-sm">
                    Tuyến đường nhanh nhất
                  </div>
                </div>
              </div>
              <div className="summary-right">
                <span className="summary-distance font-body-md">
                  {distance}
                </span>
                <span
                  className="summary-traffic font-label-sm"
                  style={{ color: trafficColor }}
                >
                  <span
                    className="summary-traffic__dot"
                    style={{ background: trafficColor }}
                  />
                  {trafficText}
                </span>
              </div>
            </div>

            {/* AI Traffic Analysis */}
            {routeTraffic && routeTraffic.camerasAnalyzed > 0 && (
              <div style={{
                background: '#f0f9ff',
                border: '1px solid #bae6fd',
                borderRadius: 8,
                padding: '10px 12px',
                fontSize: 12,
                display: "flex",
                flexDirection: "column",
                gap: "8px"
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: '#0369a1' }}>
                    <LuRoute size={14} />
                    Phân tích AI ({routeTraffic.camerasAnalyzed} camera dọc tuyến)
                  </div>
                  {routeTraffic.congestionPoints === 0 && (
                    <span style={{ color: '#16a34a', fontWeight: 600, fontSize: 11, display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <LuCheck size={14} /> Thông thoáng
                    </span>
                  )}
                </div>

                <div style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                  maxHeight: "150px",
                  overflowY: "auto",
                  paddingRight: "4px"
                }} className="custom-scrollbar">
                  {routeTraffic.predictions.map((p, idx) => {
                    const density = p.prediction.density_level;
                    const colors = {
                      low: { bg: "#dcfce7", text: "#16a34a", dot: "#22c55e", label: "Thông thoáng" },
                      moderate: { bg: "#fef9c3", text: "#ca8a04", dot: "#eab308", label: "Đông vừa" },
                      heavy: { bg: "#fee2e2", text: "#dc2626", dot: "#ef4444", label: "Kẹt xe" },
                      severe: { bg: "#7f1d1d", text: "#fca5a5", dot: "#ef4444", label: "Kẹt cứng" },
                      unknown: { bg: "#f1f5f9", text: "#64748b", dot: "#94a3b8", label: "Không rõ" }
                    };
                    const c = colors[density] || colors.unknown;
                    
                    return (
                      <div key={idx} style={{ 
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        background: "#fff", padding: "6px 8px", borderRadius: "6px", border: "1px solid #e0f2fe"
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px", overflow: "hidden" }}>
                          <LuVideo size={14} color="#0ea5e9" style={{flexShrink: 0}} />
                          <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: 500 }}>
                            {p.camera_name}
                          </span>
                        </div>
                        <div style={{ 
                          display: "flex", alignItems: "center", gap: "4px",
                          background: c.bg, color: c.text, padding: "2px 6px", borderRadius: "4px",
                          fontWeight: 600, fontSize: 10, flexShrink: 0
                        }}>
                          <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot }} />
                          {c.label} ({p.prediction.total_count} xe)
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Navigation Steps */}
            {navigationSteps && navigationSteps.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px",
                }}
              >
                <div
                  style={{
                    maxHeight: "160px",
                    overflowY: "auto",
                    background: "#F8FAFC",
                    borderRadius: "12px",
                    padding: "12px",
                    border: "1px solid #E2E8F0",
                  }}
                >
                  <div
                    className="font-label-md"
                    style={{
                      marginBottom: "8px",
                      color: "var(--on-surface-variant)",
                    }}
                  >
                    Chỉ đường chi tiết:
                  </div>
                  {navigationSteps.map((step, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "8px",
                        marginBottom: "8px",
                        borderBottom:
                          idx !== navigationSteps.length - 1
                            ? "1px solid #E2E8F0"
                            : "none",
                        paddingBottom: "8px",
                      }}
                    >
                      <span style={{ color: "var(--primary)", flexShrink: 0, marginTop: 2 }}>
                        {getStepIcon(step.instruction)}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div
                          className="font-body-md"
                          style={{ fontSize: "13px" }}
                        >
                          {step.instruction}
                        </div>
                        <div
                          className="font-label-sm"
                          style={{ color: "var(--on-surface-variant)" }}
                        >
                          {step.distance}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Nút Bắt đầu Điều Hướng */}
                <button onClick={onStartNavigation} className="start-button">
                  <LuNavigation size={18} />
                  Bắt đầu
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
