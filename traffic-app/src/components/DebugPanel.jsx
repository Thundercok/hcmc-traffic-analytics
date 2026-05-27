import React, { useState, useRef, useEffect } from "react";
import {
  LuBug,
  LuX,
  LuChevronDown,
  LuChevronRight,
  LuCopy,
  LuCheck,
  LuTrash2,
  LuDownload,
  LuClock,
  LuAlertCircle,
  LuInfo,
  LuCheckCircle,
  LuChevronUp,
} from "react-icons/lu";

// ── Debug Logger Hook ──
export const useDebugLogger = () => {
  const [logs, setLogs] = useState([]);

  const addLog = (type, message, data = null, endpoint = "") => {
    const log = {
      id: Date.now() + Math.random(),
      timestamp: new Date().toISOString(),
      type, // 'request' | 'response' | 'error' | 'info'
      message,
      endpoint,
      data,
    };
    setLogs((prev) => [log, ...prev].slice(0, 500)); // Keep last 500 logs
    return log.id;
  };

  const clearLogs = () => setLogs([]);

  const logRequest = (method, endpoint, params = null) =>
    addLog("request", `${method} ${endpoint}`, params, endpoint);

  const logResponse = (endpoint, data, status = 200) =>
    addLog("response", `${status} ${endpoint}`, data, endpoint);

  const logError = (message, error = null) =>
    addLog("error", message, error);

  const logInfo = (message, data = null) =>
    addLog("info", message, data);

  return { logs, addLog, clearLogs, logRequest, logResponse, logError, logInfo };
};

// ── Log Entry Component ──
const LogEntry = ({ log, onCopy }) => {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const typeConfig = {
    request: { icon: LuClock, color: "#3b82f6", bg: "#eff6ff", label: "REQ" },
    response: { icon: LuCheckCircle, color: "#10b981", bg: "#ecfdf5", label: "RES" },
    error: { icon: LuAlertCircle, color: "#ef4444", bg: "#fef2f2", label: "ERR" },
    info: { icon: LuInfo, color: "#8b5cf6", bg: "#f5f3ff", label: "INF" },
  };

  const config = typeConfig[log.type] || typeConfig.info;
  const Icon = config.icon;

  const handleCopy = () => {
    const text = log.data ? JSON.stringify(log.data, null, 2) : log.message;
    navigator.clipboard.writeText(text);
    setCopied(true);
    onCopy();
    setTimeout(() => setCopied(false), 1500);
  };

  const formatTime = (iso) => {
    const d = new Date(iso);
    return d.toLocaleTimeString("vi-VN", { hour12: false });
  };

  const hasData = log.data !== null && log.data !== undefined;

  return (
    <div className="debug-log-entry" style={{ borderLeftColor: config.color }}>
      <div className="debug-log-entry__header" onClick={() => hasData && setExpanded(!expanded)}>
        <div className="debug-log-entry__meta">
          <span className="debug-log-entry__type" style={{ background: config.bg, color: config.color }}>
            <Icon size={10} />
            {config.label}
          </span>
          <span className="debug-log-entry__time">{formatTime(log.timestamp)}</span>
        </div>
        <div className="debug-log-entry__message">
          {log.endpoint && <span className="debug-log-entry__endpoint">{log.endpoint}</span>}
          <span>{log.message}</span>
        </div>
        <div className="debug-log-entry__actions">
          {hasData && (
            expanded ? <LuChevronUp size={14} /> : <LuChevronDown size={14} />
          )}
          <button className="debug-log-entry__copy" onClick={(e) => { e.stopPropagation(); handleCopy(); }}>
            {copied ? <LuCheck size={12} /> : <LuCopy size={12} />}
          </button>
        </div>
      </div>
      {expanded && hasData && (
        <div className="debug-log-entry__body">
          <pre>{JSON.stringify(log.data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

// ── Stats Card ──
const StatsCard = ({ label, value, unit, color }) => (
  <div className="debug-stats-card">
    <div className="debug-stats-card__value" style={{ color: color || "var(--primary)" }}>
      {value}
      {unit && <span className="debug-stats-card__unit">{unit}</span>}
    </div>
    <div className="debug-stats-card__label">{label}</div>
  </div>
);

// ── Main Debug Panel ──
export default function DebugPanel({
  isOpen,
  onToggle,
  logs,
  onClearLogs,
  appState = {},
}) {
  const [activeTab, setActiveTab] = useState("logs"); // 'logs' | 'state' | 'network'
  const logsEndRef = useRef(null);

  const {
    originObj,
    destObj,
    routeData,
    routeTraffic,
    cameraCount = 0,
    analysisTime = 0,
    fetchCount = 0,
  } = appState;

  // Auto-scroll to top when new logs arrive
  useEffect(() => {
    if (logsEndRef.current && activeTab === "logs") {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs.length, activeTab]);

  const handleExportLogs = () => {
    const data = JSON.stringify(logs, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `debug-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      {/* Toggle Button */}
      <button
        className={`debug-toggle-btn ${isOpen ? "debug-toggle-btn--active" : ""}`}
        onClick={onToggle}
        title="Debug Panel"
      >
        <LuBug size={18} />
        <span className="debug-toggle-btn__badge">{logs.length}</span>
      </button>

      {/* Panel */}
      <div className={`debug-panel ${isOpen ? "debug-panel--open" : ""}`}>
        <div className="debug-panel__header">
          <div className="debug-panel__title">
            <LuBug size={16} />
            <span>Debug Console</span>
          </div>
          <div className="debug-panel__actions">
            <button onClick={handleExportLogs} title="Export logs">
              <LuDownload size={14} />
            </button>
            <button onClick={onClearLogs} title="Clear logs">
              <LuTrash2 size={14} />
            </button>
            <button onClick={onToggle} title="Close">
              <LuX size={14} />
            </button>
          </div>
        </div>

        {/* Stats Bar */}
        <div className="debug-panel__stats">
          <StatsCard label="Cameras" value={cameraCount} color="#0058bd" />
          <StatsCard label="Fetch" value={fetchCount} color="#765700" />
          <StatsCard label="Analysis" value={`${analysisTime}ms`} color="#006e2c" />
        </div>

        {/* Tabs */}
        <div className="debug-panel__tabs">
          <button
            className={`debug-panel__tab ${activeTab === "logs" ? "debug-panel__tab--active" : ""}`}
            onClick={() => setActiveTab("logs")}
          >
            Logs ({logs.length})
          </button>
          <button
            className={`debug-panel__tab ${activeTab === "state" ? "debug-panel__tab--active" : ""}`}
            onClick={() => setActiveTab("state")}
          >
            State
          </button>
          <button
            className={`debug-panel__tab ${activeTab === "network" ? "debug-panel__tab--active" : ""}`}
            onClick={() => setActiveTab("network")}
          >
            Network
          </button>
        </div>

        {/* Content */}
        <div className="debug-panel__content">
          {activeTab === "logs" && (
            <div className="debug-logs">
              {logs.length === 0 ? (
                <div className="debug-logs__empty">
                  <LuInfo size={24} />
                  <span>No logs yet. Interact with the app to see debug info.</span>
                </div>
              ) : (
                <>
                  {logs.map((log) => (
                    <LogEntry key={log.id} log={log} onCopy={() => {}} />
                  ))}
                  <div ref={logsEndRef} />
                </>
              )}
            </div>
          )}

          {activeTab === "state" && (
            <div className="debug-state">
              <div className="debug-state__section">
                <h4>Route Info</h4>
                <div className="debug-state__grid">
                  <div className="debug-state__item">
                    <span className="debug-state__label">Origin</span>
                    <span className="debug-state__value">
                      {originObj ? `${originObj.lat.toFixed(5)}, ${originObj.lon.toFixed(5)}` : "Not set"}
                    </span>
                  </div>
                  <div className="debug-state__item">
                    <span className="debug-state__label">Destination</span>
                    <span className="debug-state__value">
                      {destObj ? `${destObj.lat.toFixed(5)}, ${destObj.lon.toFixed(5)}` : "Not set"}
                    </span>
                  </div>
                  <div className="debug-state__item">
                    <span className="debug-state__label">ETA</span>
                    <span className="debug-state__value">{routeData.eta || "—"}</span>
                  </div>
                  <div className="debug-state__item">
                    <span className="debug-state__label">Distance</span>
                    <span className="debug-state__value">{routeData.distance || "—"}</span>
                  </div>
                  <div className="debug-state__item">
                    <span className="debug-state__label">Traffic Level</span>
                    <span className="debug-state__value">{routeData.trafficLevel || "—"}</span>
                  </div>
                  <div className="debug-state__item">
                    <span className="debug-state__label">Segments</span>
                    <span className="debug-state__value">{routeData.segments?.length || 0}</span>
                  </div>
                </div>
              </div>

              {routeTraffic && (
                <div className="debug-state__section">
                  <h4>Traffic Analysis</h4>
                  <div className="debug-state__grid">
                    <div className="debug-state__item">
                      <span className="debug-state__label">Cameras Analyzed</span>
                      <span className="debug-state__value">{routeTraffic.camerasAnalyzed || 0}</span>
                    </div>
                    <div className="debug-state__item">
                      <span className="debug-state__label">Congestion Points</span>
                      <span className="debug-state__value" style={{ color: routeTraffic.congestionPoints > 0 ? "#ef4444" : "#10b981" }}>
                        {routeTraffic.congestionPoints || 0}
                      </span>
                    </div>
                    <div className="debug-state__item">
                      <span className="debug-state__label">Traffic Level</span>
                      <span className="debug-state__value">{routeTraffic.level || "—"}</span>
                    </div>
                    <div className="debug-state__item">
                      <span className="debug-state__label">Confidence</span>
                      <span className="debug-state__value">{(routeTraffic.confidence * 100).toFixed(0) || "—"}%</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="debug-state__section">
                <h4>Environment</h4>
                <div className="debug-state__grid">
                  <div className="debug-state__item">
                    <span className="debug-state__label">API URL</span>
                    <span className="debug-state__value debug-state__value--mono">
                      {import.meta.env.VITE_API_URL || "Not configured"}
                    </span>
                  </div>
                  <div className="debug-state__item">
                    <span className="debug-state__label">Mode</span>
                    <span className="debug-state__value">{import.meta.env.MODE}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "network" && (
            <div className="debug-network">
              <div className="debug-network__endpoints">
                <h4>API Endpoints</h4>
                <div className="debug-network__list">
                  <div className="debug-network__endpoint">
                    <span className="debug-network__method">GET</span>
                    <span className="debug-network__path">/api/cameras</span>
                    <span className="debug-network__desc">Get all camera locations</span>
                  </div>
                  <div className="debug-network__endpoint">
                    <span className="debug-network__method">GET</span>
                    <span className="debug-network__path">/api/cameras/nearby</span>
                    <span className="debug-network__desc">Get cameras near route</span>
                  </div>
                  <div className="debug-network__endpoint">
                    <span className="debug-network__method">POST</span>
                    <span className="debug-network__path">/api/predict</span>
                    <span className="debug-network__desc">Predict traffic flow</span>
                  </div>
                  <div className="debug-network__endpoint">
                    <span className="debug-network__method">GET</span>
                    <span className="debug-network__path">/api/forecast</span>
                    <span className="debug-network__desc">Get traffic forecast</span>
                  </div>
                </div>
              </div>
              <div className="debug-network__info">
                <h4>Request Log</h4>
                <p>Network requests are logged in the Logs tab with full request/response details.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
