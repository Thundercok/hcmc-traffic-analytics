import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  LuGauge,
  LuCamera,
  LuSearch,
  LuRefreshCw,
  LuServer,
  LuActivity,
  LuCheck,
  LuMapPin,
  LuChevronUp,
  LuChevronDown,
} from "react-icons/lu";

export default function AdminPanel({ onNavigateToDashboard }) {
  const apiUrl = import.meta.env.VITE_API_URL || "/api";
  const [cameras, setCameras] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("all"); // "all" | "mapped" | "unmapped" | "auto"
  const [isRunningBatch, setIsRunningBatch] = useState(false);
  const [batchMessage, setBatchMessage] = useState("");
  const [isExpanded, setIsExpanded] = useState(true);

  // Fetch camera list and stats
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [camRes, statsRes] = await Promise.all([
        fetch(`${apiUrl}/cameras`),
        fetch(`${apiUrl}/cameras/stats`),
      ]);

      if (camRes.ok && statsRes.ok) {
        const camData = await camRes.json();
        const statsData = await statsRes.json();
        setCameras(camData.cameras || []);
        setStats(statsData);
      }
    } catch (err) {
      console.error("Failed to fetch admin data", err);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchData();

    // Listen to ROI changes and refresh immediately
    window.addEventListener("cameraRoiChanged", fetchData);
    return () => {
      window.removeEventListener("cameraRoiChanged", fetchData);
    };
  }, [fetchData]);

  // Run batch inference
  const handleBatchInference = async () => {
    if (isRunningBatch || cameras.length === 0) return;
    setIsRunningBatch(true);
    setBatchMessage("Đang chạy dự đoán (31 camera)...");
    try {
      const res = await fetch(`${apiUrl}/predict/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_ids: cameras.map((c) => c.id) }),
      });
      if (res.ok) {
        const data = await res.json();
        setBatchMessage(`Hoàn thành: Thành công ${data.succeeded}, Thất bại ${data.failed}`);
        // Dispatch event to map to reload camera statuses
        window.dispatchEvent(new CustomEvent("camerasRefreshed"));
        setTimeout(() => setBatchMessage(""), 5000);
      } else {
        setBatchMessage("Chạy dự đoán hàng loạt thất bại.");
      }
    } catch (err) {
      console.error("Batch inference failed", err);
      setBatchMessage("Lỗi kết nối API.");
    } finally {
      setIsRunningBatch(false);
    }
  };

  // Filter and Search cameras
  const filteredCameras = useMemo(() => {
    return cameras.filter((cam) => {
      const matchesSearch =
        cam.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        cam.district.toLowerCase().includes(searchQuery.toLowerCase()) ||
        cam.id.includes(searchQuery);

      if (!matchesSearch) return false;

      if (activeFilter === "mapped") return cam.has_roi;
      if (activeFilter === "unmapped") return !cam.has_roi;
      if (activeFilter === "auto") return cam.has_roi && cam.is_auto_roi;

      return true;
    });
  }, [cameras, searchQuery, activeFilter]);

  // Pan to camera and open popup
  const handleCameraSelect = (cam) => {
    window.dispatchEvent(new CustomEvent("openCameraPopup", { detail: cam }));
  };

  return (
    <div className={`control-panel ${isExpanded ? "control-panel--expanded" : ""}`}>
      {/* Panel Header */}
      <div className="control-panel__header" onClick={() => setIsExpanded(!isExpanded)}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div className="control-panel__icon-wrap admin-badge">
            <LuServer size={20} />
          </div>
          <div>
            <h2 className="font-headline-md" style={{ fontSize: "16px", margin: 0 }}>
              Quản trị TrafficFlow
            </h2>
            <div className="font-label-sm" style={{ opacity: 0.7 }}>
              Quận 7 & Nhà Bè · 31 Camera
            </div>
          </div>
        </div>
        <button className="control-panel__toggle" aria-label="Toggle Panel">
          {isExpanded ? <LuChevronDown size={20} /> : <LuChevronUp size={20} />}
        </button>
      </div>

      {isExpanded && (
        <div className="control-panel__content admin-panel__content">
          {/* Progress stats */}
          {stats && (
            <div className="admin-stats-card">
              <div className="admin-stats-card__header">
                <span className="font-label-md">Tiến độ thiết lập ROI</span>
                <span className="font-headline-md" style={{ fontSize: "18px", color: "var(--secondary)" }}>
                  {stats.percentage_mapped}%
                </span>
              </div>
              <div className="admin-progress-bar-wrap">
                <div
                  className="admin-progress-bar-fill"
                  style={{ width: `${stats.percentage_mapped}%` }}
                ></div>
              </div>
              <div className="admin-stats-grid">
                <div>
                  <div className="stat-label">Đã vẽ (ROI)</div>
                  <div className="stat-val">{stats.mapped_cameras}</div>
                </div>
                <div>
                  <div className="stat-label">Chưa vẽ</div>
                  <div className="stat-val">{stats.unmapped_cameras}</div>
                </div>
                <div>
                  <div className="stat-label">Tự động</div>
                  <div className="stat-val">{stats.auto_cameras}</div>
                </div>
              </div>
            </div>
          )}

          {/* Action Row */}
          <div className="admin-action-row">
            <button
              onClick={handleBatchInference}
              disabled={isRunningBatch}
              className={`admin-btn admin-btn--primary ${isRunningBatch ? "admin-btn--loading" : ""}`}
            >
              <LuRefreshCw className={isRunningBatch ? "spin-animation" : ""} size={14} />
              {isRunningBatch ? "Đang chạy..." : "Dự đoán hàng loạt"}
            </button>

            <button
              onClick={() => onNavigateToDashboard?.()}
              className="admin-btn admin-btn--secondary"
            >
              <LuActivity size={14} />
              Dashboard
            </button>
          </div>

          {batchMessage && (
            <div className="admin-message font-label-sm">
              {batchMessage}
            </div>
          )}

          {/* Search bar */}
          <div className="admin-search-wrap">
            <LuSearch className="admin-search-icon" size={16} />
            <input
              type="text"
              placeholder="Tìm kiếm camera hoặc khu vực..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="admin-search-input"
            />
          </div>

          {/* Filters */}
          <div className="admin-filters">
            {[
              { id: "all", label: "Tất cả" },
              { id: "mapped", label: "Đã vẽ" },
              { id: "unmapped", label: "Chưa vẽ" },
              { id: "auto", label: "Tự động" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setActiveFilter(f.id)}
                className={`admin-filter-tab font-label-sm ${activeFilter === f.id ? "active" : ""}`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Camera directory list */}
          {loading && cameras.length === 0 ? (
            <div className="admin-loading-text font-label-md">Đang tải danh sách camera...</div>
          ) : (
            <div className="admin-camera-list">
              {filteredCameras.length === 0 ? (
                <div className="admin-empty-text font-label-md">Không tìm thấy camera phù hợp.</div>
              ) : (
                filteredCameras.map((cam) => (
                  <div
                    key={cam.id}
                    onClick={() => handleCameraSelect(cam)}
                    className="admin-camera-card"
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px", flex: 1 }}>
                      <span className="camera-name font-body-md" style={{ fontWeight: 600 }}>
                        {cam.name}
                      </span>
                      <span className="camera-district font-label-sm" style={{ opacity: 0.6 }}>
                        <LuMapPin size={11} style={{ marginRight: "3px", verticalAlign: "middle" }} />
                        {cam.district}
                      </span>
                    </div>
                    <div>
                      {cam.has_roi ? (
                        cam.is_auto_roi ? (
                          <span className="admin-badge admin-badge--auto font-label-sm">Tự động</span>
                        ) : (
                          <span className="admin-badge admin-badge--mapped font-label-sm">Đã vẽ</span>
                        )
                      ) : (
                        <span className="admin-badge admin-badge--unmapped font-label-sm">Chưa vẽ</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
