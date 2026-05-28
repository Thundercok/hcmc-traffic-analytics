import { useState, useEffect, useCallback } from "react";
import {
  LuActivity, LuDatabase, LuCamera, LuServer, LuClock,
  LuCircleCheck, LuCircleX, LuHardDrive, LuRefreshCw, LuCar,
  LuBike, LuMapPin, LuTimer, LuTrendingUp, LuTrendingDown,
  LuCpu, LuGauge, LuWifi, LuPackage, LuEye,
  LuArrowLeft, LuFlame, LuX,
  LuInfo, LuMap, LuNavigation,
  LuZap, LuLayers, LuFileQuestion, LuUsers,
} from "react-icons/lu";

// ─── Config ────────────────────────────────────────────────────────────────
const API = "/api";

// ─── Helpers ──────────────────────────────────────────────────────────────
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("vi-VN"));
const safePercent = (numerator, denominator, decimals = 0) => {
  if (!denominator || denominator === 0) return "—";
  return `${((numerator / denominator) * 100).toFixed(decimals)}%`;
};
const relTime = (iso) => {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60) return "Vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  return `${Math.floor(diff / 3600)} giờ trước`;
};

// ─── Density Config ────────────────────────────────────────────────────────
const DENSITY_META = {
  low:      { label: "Thông thoáng", color: "#10b981", bg: "#d1fae5",   border: "#6ee7b7", text: "#065f46", icon: LuCircleCheck },
  moderate: { label: "Đông vừa",   color: "#f59e0b", bg: "#fef3c7",   border: "#fcd34d", text: "#92400e", icon: LuUsers },
  heavy:    { label: "Kẹt xe",     color: "#ef4444", bg: "#fee2e2",   border: "#fca5a5", text: "#991b1b", icon: LuFlame },
  severe:   { label: "Ùn tắc",      color: "#7f1d1d", bg: "#fee2e2",   border: "#f87171", text: "#7f1d1d", icon: LuX },
  unknown:  { label: "Không rõ",    color: "#6b7280", bg: "#f3f4f6",   border: "#d1d5db", text: "#374151", icon: LuFileQuestion },
};

function DensityBadge({ level, size = "sm" }) {
  const d = DENSITY_META[level] || DENSITY_META.unknown;
  const pad = size === "lg" ? "5px 14px" : "3px 10px";
  const fs = size === "lg" ? 13 : 11;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: pad, borderRadius: 99, fontSize: fs, fontWeight: 700,
      background: d.bg, color: d.text, border: `1px solid ${d.border}`,
    }}>
      <d.icon size={size === "lg" ? 13 : 10} />
      {d.label}
    </span>
  );
}

function SystemBadge({ ok, label }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "4px 12px", borderRadius: 99, fontSize: 12, fontWeight: 600,
      background: ok ? "#dcfce7" : "#fee2e2",
      color: ok ? "#15803d" : "#dc2626",
    }}>
      {ok ? <LuCircleCheck size={13} /> : <LuCircleX size={13} />}
      {label}
    </span>
  );
}

// ─── Stat Row ─────────────────────────────────────────────────────────────
function StatRow({ icon: Icon, label, value, color }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 0", borderBottom: "1px solid #f9fafb" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#6b7280" }}>
        {Icon && <Icon size={12} />} {label}
      </span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color || "#111827" }}>{value}</span>
    </div>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────
function KpiCard({ icon: Icon, label, value, sub, accent = "#3b82f6" }) {
  return (
    <div style={{
      background: "white", borderRadius: 16, padding: "20px",
      border: "1px solid #e5e7eb", boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: -18, right: -8, opacity: 0.06,
        transform: "scale(2.8)",
      }}>
        <Icon size={64} color={accent} />
      </div>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 14, background: `${accent}18`,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, color: accent,
        }}>
          <Icon size={22} />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase", letterSpacing: "0.5px", fontWeight: 600, marginBottom: 4 }}>
            {label}
          </div>
          <div style={{ fontSize: 26, fontWeight: 800, color: "#111827", lineHeight: 1.1 }}>
            {value ?? "—"}
          </div>
          {sub && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{sub}</div>}
        </div>
      </div>
    </div>
  );
}

// ─── Section Card ─────────────────────────────────────────────────────────
function Section({ icon: Icon, title, badge, children, style }) {
  return (
    <div style={{
      background: "white", borderRadius: 16, border: "1px solid #e5e7eb",
      boxShadow: "0 1px 4px rgba(0,0,0,0.05)", overflow: "hidden",
      ...style,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 10, padding: "14px 20px",
        borderBottom: "1px solid #f3f4f6", background: "#fafbfc",
      }}>
        {Icon && <Icon size={16} color="#6b7280" />}
        <span style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>{title}</span>
        {badge != null && (
          <span style={{
            marginLeft: "auto", background: "#eff6ff", color: "#3b82f6",
            fontSize: 11, fontWeight: 700, padding: "2px 10px", borderRadius: 99,
            fontFamily: "monospace",
          }}>
            {badge}
          </span>
        )}
      </div>
      <div style={{ padding: "16px 20px" }}>{children}</div>
    </div>
  );
}

// ─── Donut Chart ───────────────────────────────────────────────────────────
function DonutChart({ data, size = 120 }) {
  if (!data || Object.keys(data).every(k => data[k] === 0)) {
    return <div style={{ color: "#9ca3af", fontSize: 13 }}>Chưa có dữ liệu</div>;
  }
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  const r = size / 2 - 12;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  const segs = Object.entries(data)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => {
      const pct = v / total;
      const dash = pct * circ;
      const gap = circ - dash;
      const d = DENSITY_META[k] || DENSITY_META.unknown;
      const result = { key: k, pct, dash, gap, offset, color: d.color, label: d.label, v };
      offset += dash;
      return result;
    });
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f3f4f6" strokeWidth={16} />
        {segs.map((s, i) => (
          <circle key={s.key} cx={cx} cy={cy} r={r} fill="none"
            stroke={s.color} strokeWidth={16}
            strokeDasharray={`${s.dash} ${s.gap}`}
            strokeDashoffset={-(s.offset)}
            strokeLinecap="butt"
            style={{ transition: "all 0.5s ease" }}
          />
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize={22} fontWeight={800} fill="#111827">{total}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize={10} fill="#9ca3af">camera</text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {segs.map(s => (
          <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: s.color, flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: "#6b7280" }}>{s.label}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#111827", marginLeft: "auto", minWidth: 24, textAlign: "right" }}>{s.v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Bar Chart ────────────────────────────────────────────────────────────
function BarChart({ data, color = "#3b82f6" }) {
  if (!data?.length) return <div style={{ color: "#9ca3af", fontSize: 13 }}>Chưa có dữ liệu</div>;
  const max = Math.max(...data.map(d => d.value), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 80 }}>
      {data.map((d, i) => {
        const pct = (d.value / max) * 100;
        const isMax = d.value === max;
        return (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
            <div style={{ fontSize: 9, color: "#9ca3af", fontWeight: 600 }}>{d.value}</div>
            <div style={{
              width: "100%", height: `${Math.max(pct, 3)}%`,
              background: isMax ? color : `${color}66`,
              borderRadius: "3px 3px 0 0", transition: "all 0.4s ease",
            }} />
            <div style={{ fontSize: 8, color: "#9ca3af", whiteSpace: "nowrap" }}>{d.label}</div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Mini Sparkline ───────────────────────────────────────────────────────
function Sparkline({ history }) {
  if (!history?.length) return null;
  const vals = history.map(h => h.total_count);
  const W = 100, H = 32, P = 3;
  const mx = Math.max(...vals, 1), mn = Math.min(...vals, 0);
  const range = mx - mn || 1;
  const pts = vals.map((v, i) => `${P + (i / (vals.length - 1)) * (W - 2 * P)},${H - P - ((v - mn) / range) * (H - 2 * P)}`).join(" ");
  const last = vals[vals.length - 1];
  const prev = vals[vals.length - 2] ?? last;
  const color = last > prev ? "#ef4444" : last < prev ? "#10b981" : "#6b7280";
  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={P + (W - 2 * P)} cy={H - P - ((last - mn) / range) * (H - 2 * P)} r="2.5" fill={color} />
    </svg>
  );
}

// ─── Camera Card (clickable) ─────────────────────────────────────────────
function CameraCard({ cam, onClick }) {
  const d = DENSITY_META[cam.last_level] || DENSITY_META.unknown;
  return (
    <div
      onClick={() => onClick?.(cam)}
      style={{
        padding: "12px 14px", borderRadius: 12,
        background: cam.cached ? "#f0fdf4" : "#fef2f2",
        border: `1.5px solid ${cam.cached ? "#bbf7d0" : "#fecaca"}`,
        cursor: onClick ? "pointer" : "default",
        transition: "all 0.15s ease",
        position: "relative",
      }}
      onMouseEnter={e => onClick && (e.currentTarget.style.transform = "translateY(-1px)", e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.08)")}
      onMouseLeave={e => onClick && (e.currentTarget.style.transform = "", e.currentTarget.style.boxShadow = "")}
    >
      {/* Status dot */}
      <div style={{
        position: "absolute", top: 10, right: 10,
        width: 8, height: 8, borderRadius: "50%",
        background: cam.cached ? "#22c55e" : "#ef4444",
      }} />

      <div style={{ fontSize: 12, fontWeight: 700, color: cam.cached ? "#166534" : "#991b1b", marginBottom: 2, paddingRight: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {cam.name || cam.id.slice(-8)}
      </div>

      {cam.district && (
        <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 8 }}>
          <LuMapPin size={9} style={{ verticalAlign: "middle" }} /> {cam.district}
        </div>
      )}

      {cam.cached ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: "#111827", lineHeight: 1 }}>
              {cam.last_count ?? "—"}
            </div>
            <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2 }}>
              <LuCar size={9} style={{ verticalAlign: "middle" }} /> {cam.last_car ?? 0}
              <span style={{ margin: "0 4px" }}>·</span>
              <LuBike size={9} style={{ verticalAlign: "middle" }} /> {cam.last_motorbike ?? 0}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
            <DensityBadge level={cam.last_level} />
            <Sparkline history={cam.history} />
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "#9ca3af" }}>
          Chưa có dữ liệu · Click để kiểm tra
        </div>
      )}
    </div>
  );
}

// ─── Traffic Legend ────────────────────────────────────────────────────────
function TrafficLegend() {
  return (
    <Section icon={LuInfo} title="Phương pháp đo lường & Phân loại mật độ" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[
          { level: "low",      desc: "Đường thông thoáng, xe di chuyển bình thường, mật độ tích phân ROI ở mức tối thiểu." },
          { level: "moderate", desc: "Mật độ phương tiện đông vừa phải, tốc độ dòng chảy giao thông giảm nhẹ." },
          { level: "heavy",    desc: "Mật độ tích phân ROI cao, ùn ứ xuất hiện trên các phân đoạn làn đường." },
          { level: "severe",   desc: "Ùn tắc giao thông nghiêm trọng, tích phân mật độ vượt ngưỡng giới hạn, xe di chuyển cực kỳ khó khăn." },
        ].map(({ level, desc }) => {
          const d = DENSITY_META[level];
          return (
            <div key={level} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10, background: d.bg,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0, color: d.text,
              }}>
                <d.icon size={16} />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: d.text, marginBottom: 2 }}>
                  <span style={{
                    display: "inline-block", width: 10, height: 10, borderRadius: 3,
                    background: d.color, marginRight: 6, verticalAlign: "middle",
                  }} />
                  {d.label}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.5 }}>
                  {desc}
                </div>
              </div>
            </div>
          );
        })}
        <div style={{ marginTop: 4, padding: "10px 12px", background: "#f8fafc", borderRadius: 10, fontSize: 12, color: "#64748b", border: "1px dashed #cbd5e1", lineHeight: 1.6 }}>
          <strong style={{ color: "#475569" }}>Nguyên lý đo lường:</strong> Hệ thống sử dụng mạng nơ-ron tích chập để ước lượng bản đồ mật độ (Density Map) từ hình ảnh camera giao thông theo thời gian thực (chu kỳ 30 giây). Mức độ ùn tắc được xác định bằng cách tích phân mật độ phương tiện trên vùng diện tích làn đường được khoanh vùng (ROI - Region of Interest). Các thuật toán dự báo (Forecast) 15/30/60 phút được xây dựng dựa trên chuỗi thời gian phân tích tích lũy 60 phút.
        </div>
      </div>
    </Section>
  );
}

// ─── Mini Map Preview ─────────────────────────────────────────────────────
function MiniMapPreview({ cameras, onCameraClick }) {
  const active = cameras?.list?.filter(c => c.cached) || [];
  const byLevel = { low: 0, moderate: 0, heavy: 0, severe: 0 };
  active.forEach(c => { byLevel[c.last_level] = (byLevel[c.last_level] || 0) + 1; });
  return (
    <div style={{
      background: "#1e293b", borderRadius: 16, padding: "16px 20px",
      display: "grid", gridTemplateColumns: "1fr auto", gap: 16, alignItems: "center",
    }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, color: "white", marginBottom: 4 }}>Bản đồ giao thông</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>
          {active.length} camera đang hoạt động · {cameras?.districts?.length || 0} quận/huyện
        </div>
        <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
          {Object.entries(byLevel).filter(([, v]) => v > 0).map(([k, v]) => {
            const d = DENSITY_META[k];
            return (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{ width: 8, height: 8, borderRadius: 2, background: d.color }} />
                <span style={{ fontSize: 12, color: "#94a3b8" }}>{v}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{
        width: 64, height: 64, borderRadius: 14, background: "#334155",
        display: "flex", alignItems: "center", justifyContent: "center",
        cursor: "pointer",
      }} onClick={() => onCameraClick?.()}>
        <LuMap size={28} color="#60a5fa" />
      </div>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────
export default function Dashboard({ onBack, onCameraClick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [tab, setTab] = useState("overview");
  const [expandedCam, setExpandedCam] = useState(null);

  const load = useCallback(() => {
    fetch(`${API}/debug`)
      .then(r => r.json())
      .then(d => { setData(d); setLastUpdated(new Date()); setLoading(false); setError(null); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh mỗi 30 giây
  useEffect(() => {
    const interval = setInterval(() => {
      fetch(`${API}/debug`)
        .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
        .then(d => { setData(d); setLastUpdated(new Date()); setError(null); })
        .catch(() => {}); // Silently ignore errors during background refresh
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Toggle expand camera row
  const toggleCamExpand = useCallback((cameraId) => {
    setExpandedCam(prev => prev === cameraId ? null : cameraId);
  }, []);

  const { health, database, writer, cameras, traffic } = data || {};
  const totalRecs = traffic?.total_records || 0;
  const allRecords = database?.all_records || [];
  const activeCams = cameras?.list?.filter(c => c.cached).length || 0;

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", flexDirection: "column", gap: 12 }}>
        <LuActivity size={40} color="#3b82f6" style={{ animation: "spin 1s linear infinite" }} />
        <div style={{ color: "#6b7280", fontSize: 14 }}>Đang tải dashboard...</div>
        <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24, textAlign: "center" }}>
        <LuX size={40} color="#ef4444" />
        <div style={{ color: "#ef4444", marginTop: 12 }}>Lỗi: {error}</div>
        <button onClick={load} style={{ marginTop: 12, padding: "8px 20px", background: "#3b82f6", color: "white", border: "none", borderRadius: 8, cursor: "pointer" }}>
          Thử lại
        </button>
      </div>
    );
  }

  const activeCamsByLevel = {};
  (cameras?.list || []).filter(c => c.cached).forEach(c => {
    const l = c.last_level || "unknown";
    activeCamsByLevel[l] = (activeCamsByLevel[l] || 0) + 1;
  });

  return (
    <div style={{
      minHeight: "100vh",
      height: "100vh",
      overflow: "hidden",
      background: "#f8fafc",
      fontFamily: "system-ui, -apple-system, sans-serif",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* ── Header ── */}
      <div style={{
        background: "white", borderBottom: "1px solid #e5e7eb",
        padding: "0 24px", position: "sticky", top: 0, zIndex: 100,
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, height: 56 }}>
          <button
            onClick={onBack}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "6px 14px", borderRadius: 8, border: "1px solid #e5e7eb",
              background: "white", cursor: "pointer", fontSize: 13, fontWeight: 600,
              color: "#374151", transition: "all 0.15s",
            }}
          >
            <LuArrowLeft size={14} /> Quay lại Map
          </button>
          <div style={{ width: 1, height: 24, background: "#e5e7eb" }} />
          <LuActivity size={20} color="#3b82f6" />
          <span style={{ fontSize: 17, fontWeight: 800, color: "#111827" }}>TrafficFlow Dashboard</span>
          <span style={{
            marginLeft: 4, background: "#eff6ff", color: "#3b82f6",
            fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
          }}>BETA</span>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 12, color: "#9ca3af" }}>
              <LuClock size={11} style={{ verticalAlign: "middle" }} /> {relTime(lastUpdated)}
            </span>
            <button
              onClick={load}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "6px 12px", borderRadius: 8, border: "none",
                background: "#f1f5f9", cursor: "pointer", fontSize: 12, fontWeight: 600,
                color: "#475569",
              }}
            >
              <LuRefreshCw size={13} /> Làm mới
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {[
            { id: "overview", label: "Tổng quan", icon: LuLayers },
            { id: "cameras", label: "Camera", icon: LuCamera },
            { id: "system", label: "Hệ thống", icon: LuServer },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "8px 16px", border: "none", borderBottom: `2px solid ${tab === t.id ? "#3b82f6" : "transparent"}`,
                background: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
                color: tab === t.id ? "#3b82f6" : "#6b7280",
                transition: "all 0.15s",
              }}
            >
              <t.icon size={14} /> {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Content ── */}
      <div style={{
        flex: 1,
        overflow: "auto",
        padding: "20px 24px 40px",
      }}>
        <div style={{ maxWidth: 1400, margin: "0 auto" }}>

        {/* ── OVERVIEW TAB ── */}
        {tab === "overview" && (
          <>
            <TrafficLegend />

            {/* Mini map preview */}
            <MiniMapPreview cameras={cameras} onCameraClick={onBack} />

            {/* KPIs */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, margin: "16px 0" }}>
              <KpiCard icon={LuDatabase} label="Tổng bản ghi" value={fmt(totalRecs)} sub="Trong 60 phút gần đây" accent="#3b82f6" />
              <KpiCard icon={LuCamera} label="Camera hoạt động" value={`${activeCams} / ${cameras?.list?.length || 0}`} sub="Đang ghi nhận dữ liệu" accent="#10b981" />
              <KpiCard icon={LuActivity} label="Writer" value={writer?.status === "running" ? "Đang chạy" : "Dừng"} sub={`Chu kỳ ${writer?.interval_seconds || 30}s`} accent="#f59e0b" />
              <KpiCard icon={LuGauge} label="Model AI" value={health?.model_loaded ? "Đã tải" : "Chưa tải"} sub={health?.device || "CPU"} accent="#8b5cf6" />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {/* Traffic distribution donut */}
              <Section icon={LuFlame} title="Phân bố mức độ kẹt xe" badge={`${activeCams} camera`}>
                <DonutChart data={activeCamsByLevel} size={140} />
              </Section>

              {/* Hourly bar chart */}
              <Section icon={LuClock} title="Mật độ theo giờ (hôm nay)">
                <BarChart
                  data={traffic?.hourly?.map(h => ({ label: `${String(h.hour).padStart(2, "0")}:00`, value: h.avg_count || 0 })) || []}
                  color="#3b82f6"
                />
              </Section>
            </div>

            {/* System status */}
            <Section icon={LuZap} title="Trạng thái hệ thống" style={{ marginTop: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: health?.model_loaded ? "#dcfce7" : "#fef3c7", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Model AI</span>
                  <SystemBadge ok={health?.model_loaded} label={health?.model_loaded ? "Đã tải" : "Chưa tải"} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: database?.status === "connected" ? "#dcfce7" : "#fee2e2", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Database</span>
                  <SystemBadge ok={database?.status === "connected"} label={database?.status === "connected" ? "Kết nối" : "Mất kết nối"} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: writer?.status === "running" ? "#dcfce7" : "#fef3c7", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Auto-writer</span>
                  <SystemBadge ok={writer?.status === "running"} label={writer?.status === "running" ? "Đang ghi" : "Dừng"} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "#f0fdf4", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Dung lượng DB</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>{database?.db_size || "—"}</span>
                </div>
              </div>
            </Section>
          </>
        )}

        {/* ── CAMERAS TAB ── */}
        {tab === "cameras" && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, marginBottom: 16 }}>
              <KpiCard icon={LuCamera} label="Tổng số Camera" value={cameras?.list?.length || 0} sub={`${cameras?.districts?.length || 0} quận/huyện`} accent="#3b82f6" />
              <KpiCard icon={LuCircleCheck} label="Camera hoạt động" value={activeCams} sub={`${safePercent(activeCams, cameras?.list?.length)} đang ghi dữ liệu`} accent="#10b981" />
              <KpiCard icon={LuEye} label="Tổng bản ghi" value={fmt(totalRecs)} sub="60 phút gần đây" accent="#8b5cf6" />
            </div>

            {/* Camera grid */}
            <Section icon={LuCamera} title="Danh sách Camera" badge={`${activeCams} đang hoạt động`}>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                gap: 10,
              }}>
                {(cameras?.list || []).map(cam => (
                  <CameraCard key={cam.id} cam={cam} onClick={onCameraClick} />
                ))}
              </div>
            </Section>
          </>
        )}

        {/* ── SYSTEM TAB ── */}
        {tab === "system" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Section icon={LuServer} title="Trạng thái hệ thống">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: health?.model_loaded ? "#dcfce7" : "#fef3c7", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Model AI</span>
                  <SystemBadge ok={health?.model_loaded} label={health?.model_loaded ? "Đã tải" : "Chưa tải"} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: database?.status === "connected" ? "#dcfce7" : "#fee2e2", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Database</span>
                  <SystemBadge ok={database?.status === "connected"} label={database?.status === "connected" ? "Kết nối" : "Mất kết nối"} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: writer?.status === "running" ? "#dcfce7" : "#fef3c7", borderRadius: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Auto-writer</span>
                  <SystemBadge ok={writer?.status === "running"} label={writer?.status === "running" ? "Đang ghi" : "Dừng"} />
                </div>
                <StatRow icon={LuCpu} label="Thiết bị" value={health?.device || "—"} />
                <StatRow icon={LuTimer} label="Chu kỳ ghi" value={writer?.interval_seconds ? `${writer.interval_seconds} giây` : "—"} />
                <StatRow icon={LuDatabase} label="Tổng bản ghi" value={fmt(totalRecs)} color="#3b82f6" />
                <StatRow icon={LuClock} label="Bản ghi mới nhất" value={relTime(database?.latest_prediction)} color="#10b981" />
              </div>
            </Section>

            <Section icon={LuCpu} title="Thông tin Model AI">
              <div style={{ display: "flex", flexDirection: "column" }}>
                <StatRow icon={LuPackage} label="Tên model" value={health?.model?.model_name || "—"} />
                <StatRow icon={LuCpu} label="Loại model" value={health?.model?.model_type || "ZIP"} />
                <StatRow icon={LuServer} label="Thiết bị" value={health?.device || "—"} />
                <StatRow icon={LuGauge} label="Input size" value={health?.model?.input_size ? `${health.model.input_size}px` : "—"} />
                <StatRow icon={LuGauge} label="Block size" value={health?.model?.block_size || "—"} />
                <StatRow icon={LuGauge} label="Zero-inflated" value={health?.model?.zero_inflated != null ? (health.model.zero_inflated ? "Có" : "Không") : "—"} />
                <StatRow icon={health?.model_loaded ? LuCircleCheck : LuCircleX} label="Trạng thái" value={health?.model_loaded ? "Đã tải" : "Chưa tải"} color={health?.model_loaded ? "#15803d" : "#dc2626"} />
              </div>
            </Section>

            {/* Recent Records Table - Full width */}
            <div style={{ gridColumn: "1 / -1" }}>
            <Section icon={LuDatabase} title="Chi tiết Camera - 1 giờ gần nhất" style={{ marginTop: 16 }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 900 }}>
                  <thead>
                    <tr style={{ background: "#f8fafc" }}>
                      <th style={{ width: 30, padding: "10px 0 10px 12px", borderBottom: "2px solid #e5e7eb" }}></th>
                      <th style={{ padding: "10px 12px", textAlign: "left", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb", whiteSpace: "nowrap" }}>Camera</th>
                      <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>Bản ghi</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>TB Tổng</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>TB Ô tô</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>TB Xe máy</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>Max</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>Min</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>Độ lệch</th>
                      <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>% Kẹt</th>
                      <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>% Đông</th>
                      <th style={{ padding: "10px 12px", textAlign: "center", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>% Thông</th>
                      <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#6b7280", borderBottom: "2px solid #e5e7eb" }}>Mới nhất</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(database?.hourly_per_camera || []).map((cam, idx) => {
                      const camName = cameras?.list?.find(c => c.id === cam.camera_id)?.name || cam.camera_id?.slice(-8) || "—";
                      const lastTime = cam.last_record ? relTime(cam.last_record) : "—";
                      const isExpanded = expandedCam === cam.camera_id;
                      return (
                        <>
                        <tr
                          key={cam.camera_id}
                          onClick={() => toggleCamExpand(cam.camera_id)}
                          style={{ borderBottom: "1px solid #f3f4f6", background: idx % 2 === 0 ? "white" : "#fafbfc", cursor: "pointer" }}
                        >
                          <td style={{ padding: "10px 0 10px 12px", textAlign: "center", color: "#9ca3af" }}>
                            <span style={{ display: "inline-block", transition: "transform 0.2s", transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}>
                              ▶
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1e40af", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={camName}>{camName}</td>
                          <td style={{ padding: "10px 12px", textAlign: "center", fontFamily: "monospace", fontWeight: 700, color: "#059669" }}>{cam.record_count}</td>
                          <td style={{ padding: "10px 12px", textAlign: "right", fontWeight: 700, color: "#111827" }}>{cam.avg_count}</td>
                          <td style={{ padding: "10px 12px", textAlign: "right", color: "#6b7280" }}>{cam.avg_car}</td>
                          <td style={{ padding: "10px 12px", textAlign: "right", color: "#6b7280" }}>{cam.avg_motorbike}</td>
                          <td style={{ padding: "10px 12px", textAlign: "right", color: "#dc2626", fontWeight: 600 }}>{cam.max_count}</td>
                          <td style={{ padding: "10px 12px", textAlign: "right", color: "#059669" }}>{cam.min_count}</td>
                          <td style={{ padding: "10px 12px", textAlign: "right", color: "#6b7280" }}>{cam.std_count}</td>
                          <td style={{ padding: "10px 12px", textAlign: "center" }}>
                            <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: "#fee2e2", color: "#991b1b" }}>
                              {cam.heavy_pct}%
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", textAlign: "center" }}>
                            <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: "#fef3c7", color: "#92400e" }}>
                              {cam.moderate_pct}%
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", textAlign: "center" }}>
                            <span style={{ padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: "#d1fae5", color: "#065f46" }}>
                              {cam.low_pct}%
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", textAlign: "right", color: "#6b7280", fontSize: 11 }}>{lastTime}</td>
                        </tr>
                        {isExpanded && (
                          <tr key={`${cam.camera_id}-expanded`}>
                            <td colSpan={13} style={{ padding: 0, background: "#f8fafc" }}>
                              <div style={{ padding: "12px 16px 16px 42px" }}>
                                {(() => {
                                  const camRecs = allRecords.filter(r => r.camera_id === cam.camera_id);
                                  return (
                                    <>
                                      <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", marginBottom: 8, textTransform: "uppercase" }}>
                                        Chi tiết bản ghi ({camRecs.length} bản ghi)
                                      </div>
                                      {camRecs.length > 0 ? (
                                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                                          <thead>
                                            <tr style={{ background: "#f1f5f9" }}>
                                              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>#</th>
                                              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>Tổng</th>
                                              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>Ô tô</th>
                                              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>Xe máy</th>
                                              <th style={{ padding: "6px 10px", textAlign: "center", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>Mức</th>
                                              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>Độ tin cậy</th>
                                              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#64748b", borderBottom: "1px solid #e2e8f0" }}>Thời gian</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {camRecs.map((rec, i) => {
                                              const d = DENSITY_META[rec.density_level] || DENSITY_META.unknown;
                                              return (
                                                <tr key={rec.id || i} style={{ background: i % 2 === 0 ? "white" : "#fafbfc", borderBottom: "1px solid #f1f5f9" }}>
                                                  <td style={{ padding: "6px 10px", textAlign: "right", color: "#94a3b8", fontFamily: "monospace" }}>{String(i + 1).padStart(3, "0")}</td>
                                                  <td style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: "#1e293b" }}>{rec.total_count}</td>
                                                  <td style={{ padding: "6px 10px", textAlign: "right", color: "#64748b" }}>{rec.car_count}</td>
                                                  <td style={{ padding: "6px 10px", textAlign: "right", color: "#64748b" }}>{rec.motorbike_count}</td>
                                                  <td style={{ padding: "6px 10px", textAlign: "center" }}>
                                                    <span style={{ padding: "1px 6px", borderRadius: 99, fontSize: 10, fontWeight: 700, background: d.bg, color: d.text }}>
                                                      {d.label}
                                                    </span>
                                                  </td>
                                                  <td style={{ padding: "6px 10px", textAlign: "right", color: rec.confidence && rec.confidence > 0.8 ? "#059669" : "#64748b" }}>
                                                    {rec.confidence ? `${(rec.confidence * 100).toFixed(0)}%` : "—"}
                                                  </td>
                                                  <td style={{ padding: "6px 10px", textAlign: "right", color: "#64748b" }}>{rec.timestamp ? new Date(rec.timestamp).toLocaleTimeString("vi-VN") : "—"}</td>
                                                </tr>
                                              );
                                            })}
                                          </tbody>
                                        </table>
                                      ) : (
                                        <div style={{ padding: "16px", textAlign: "center", color: "#9ca3af" }}>Không có bản ghi</div>
                                      )}
                                    </>
                                  );
                                })()}
                              </div>
                            </td>
                          </tr>
                        )}
                        </>
                      );
                    })}
                    {(!database?.hourly_per_camera || database.hourly_per_camera.length === 0) && (
                      <tr>
                        <td colSpan={13} style={{ padding: "24px", textAlign: "center", color: "#9ca3af" }}>
                          Chưa có dữ liệu trong 1 giờ qua
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Section>
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
