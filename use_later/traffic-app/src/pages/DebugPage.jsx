import { useState, useEffect, useCallback } from "react";
import {
  LuActivity, LuDatabase, LuCamera, LuServer, LuClock,
  LuCircleCheck, LuCircleX, LuHardDrive, LuRefreshCw, LuCar,
  LuUsers, LuMapPin, LuTimer, LuTrendingUp, LuTrendingDown,
  LuCpu, LuWifi, LuEye, LuPackage, LuGauge,
  LuListChecks, LuFlame, LuThermometer, LuServerOff
} from "react-icons/lu";

// ─── Utility helpers ────────────────────────────────────────────────────────
function fmtNum(n) {
  if (n == null || n === "") return "—";
  return Number(n).toLocaleString("vi-VN");
}
function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
function fmtRelTime(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Vừa xong";
  if (mins < 60) return `${mins} phút trước`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} giờ trước`;
  return `${Math.floor(hrs / 24)} ngày trước`;
}
function uptimeStr(s) {
  if (!s) return "—";
  return String(s).replace(/days|d/g, "ngày").replace(/day/g, "ngày")
    .replace(/hours|h/g, "giờ").replace(/hour/g, "giờ")
    .replace(/minutes|m/g, "phút").replace(/minute/g, "phút")
    .replace(/seconds|s/g, "giây").replace(/second/g, "giây");
}
function hourLabel(h) {
  if (h == null) return "—";
  return `${String(h).padStart(2, "0")}:00`;
}
function dayLabel(s) {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

// ─── Density config ─────────────────────────────────────────────────────────
const DENSITY = {
  low:      { label: "Thông thoáng", color: "#10b981", bg: "#d1fae5", border: "#6ee7b7", emoji: "🟢" },
  moderate: { label: "Đông vừa",    color: "#f59e0b", bg: "#fef3c7", border: "#fcd34d", emoji: "🟡" },
  heavy:    { label: "Kẹt xe",       color: "#ef4444", bg: "#fee2e2", border: "#fca5a5", emoji: "🔴" },
  severe:   { label: "Kẹt cứng",     color: "#7f1d1d", bg: "#fee2e2", border: "#f87171", emoji: "⛔" },
  unknown:  { label: "Không rõ",     color: "#6b7280", bg: "#f3f4f6", border: "#d1d5db", emoji: "⚪" },
};
function DensityBadge({ level, showEmoji = true }) {
  const d = DENSITY[level] || DENSITY.unknown;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 10px", borderRadius: 99, fontSize: 12, fontWeight: 600,
      background: d.bg, color: d.color, border: `1px solid ${d.border}`,
    }}>
      {showEmoji && <span>{d.emoji}</span>}{d.label}
    </span>
  );
}
// ─── Status Badge ─────────────────────────────────────────────────────────
function StatusBadge({ ok, label }) {
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

// ─── KPI Card ─────────────────────────────────────────────────────────────
function KpiCard({ icon, label, value, sub, trend, color = "#3b82f6", bg = "#eff6ff" }) {
  return (
    <div style={{
      background: "white", borderRadius: 16, padding: "18px 20px",
      border: "1px solid #e5e7eb", boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: -20, right: -10, opacity: 0.06,
        transform: "scale(2.5)",
      }}>
        {icon}
      </div>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12, background: bg,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, color,
        }}>
          {icon}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase", letterSpacing: "0.5px", fontWeight: 600, marginBottom: 3 }}>
            {label}
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "#111827", lineHeight: 1.2, display: "flex", alignItems: "center", gap: 8 }}>
            {value ?? "—"}
            {trend === "up" && <LuTrendingUp size={18} color="#10b981" />}
            {trend === "down" && <LuTrendingDown size={18} color="#ef4444" />}
          </div>
          {sub && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 3 }}>{sub}</div>}
        </div>
      </div>
    </div>
  );
}

// ─── Section Card ─────────────────────────────────────────────────────────
function Section({ title, icon, badge, children, style }) {
  return (
    <div style={{
      background: "white", borderRadius: 16, border: "1px solid #e5e7eb",
      boxShadow: "0 1px 3px rgba(0,0,0,0.04)", overflow: "hidden",
      ...style,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 10, padding: "14px 20px",
        borderBottom: "1px solid #f3f4f6", background: "#fafbfc",
      }}>
        <span style={{ color: icon?.props?.color || "#6b7280" }}>{icon}</span>
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

// ─── Bar Chart ────────────────────────────────────────────────────────────
function BarChart({ data, maxValue, height = 120, color = "#3b82f6", formatValue }) {
  const max = maxValue || Math.max(...(data || []).map(d => d.value), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height }}>
      {(data || []).map((d, i) => {
        const pct = (d.value / max) * 100;
        const isMax = d.value === max && max > 0;
        return (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <div style={{ fontSize: 9, color: "#9ca3af", fontWeight: 600 }}>{formatValue ? formatValue(d.value) : d.value}</div>
            <div style={{
              width: "100%", height: `${Math.max(pct, 2)}%`, background: isMax ? color : `${color}88`,
              borderRadius: "3px 3px 0 0", transition: "all 0.4s ease",
              minHeight: 4,
            }} />
            <div style={{ fontSize: 8, color: "#9ca3af" }}>{d.label}</div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Donut Chart (pure CSS/SVG) ───────────────────────────────────────────
function DonutChart({ data, size = 140 }) {
  if (!data || Object.keys(data).length === 0) {
    return <div style={{ color: "#9ca3af", fontSize: 13 }}>Chưa có dữ liệu</div>;
  }
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  const r = 44;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;

  let cumulative = 0;
  const segments = Object.entries(data).map(([key, val]) => {
    const pct = total > 0 ? val / total : 0;
    const start = cumulative;
    cumulative += pct;
    const d = DENSITY[key] || { color: "#6b7280", label: key, emoji: "⚪" };
    return { ...d, pct, start, end: cumulative, val, key };
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f3f4f6" strokeWidth={18} />
        {segments.map((seg, i) => (
          <circle
            key={seg.key} cx={cx} cy={cy} r={r}
            fill="none" stroke={seg.color} strokeWidth={18}
            strokeDasharray={`${(seg.pct * circumference).toFixed(1)} ${circumference}`}
            strokeDashoffset={((-seg.start) * circumference).toFixed(1)}
            transform={`rotate(-90 ${cx} ${cy})`}
            style={{ transition: "stroke-dasharray 0.8s ease" }}
          />
        ))}
        <circle cx={cx} cy={cy} r={30} fill="white" />
        <text x={cx} y={cy + 5} textAnchor="middle" fontSize={13} fontWeight={800} fill="#111827">
          {total >= 1000 ? `${(total / 1000).toFixed(1)}K` : total}
        </text>
        <text x={cx} y={cy + 18} textAnchor="middle" fontSize={8} fill="#9ca3af">bản ghi</text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 7, minWidth: 100 }}>
        {segments.map((seg) => (
          <div key={seg.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: seg.color, flexShrink: 0 }} />
            <span style={{ color: "#374151", flex: 1 }}>{seg.label}</span>
            <span style={{ color: "#9ca3af", fontFamily: "monospace", fontSize: 11 }}>
              {seg.val.toLocaleString("vi-VN")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Horizontal Progress ───────────────────────────────────────────────────
function HProgress({ label, value, max, color, pct }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
        <span style={{ fontSize: 12, color: "#374151" }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#111827" }}>
          {pct != null ? `${pct.toFixed(1)}%` : (max > 0 ? `${((value / max) * 100).toFixed(1)}%` : "0%")}
        </span>
      </div>
      <div style={{ height: 8, background: "#e5e7eb", borderRadius: 99, overflow: "hidden" }}>
        <div style={{
          width: pct != null ? `${Math.min(pct, 100)}%` : (max > 0 ? `${Math.min((value / max) * 100, 100)}%` : "0%"),
          height: "100%", background: color, borderRadius: 99,
          transition: "width 0.8s ease",
        }} />
      </div>
    </div>
  );
}

// ─── Stat Row ─────────────────────────────────────────────────────────────
function StatRow({ label, value, icon, color = "#374151" }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 0", borderBottom: "1px solid #f3f4f6" }}>
      <span style={{ fontSize: 13, color: "#6b7280", display: "flex", alignItems: "center", gap: 6 }}>
        {icon && <span style={{ color }}>{icon}</span>}
        {label}
      </span>
      <span style={{ fontSize: 13, fontWeight: 600, color }}>{value ?? "—"}</span>
    </div>
  );
}

// ─── Loading ─────────────────────────────────────────────────────────────
function Loading() {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: "80vh", gap: 16, color: "#9ca3af",
    }}>
      <div style={{ animation: "spin 1s linear infinite" }}>
        <LuRefreshCw size={40} color="#3b82f6" />
      </div>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <span style={{ fontSize: 15 }}>Đang tải dashboard...</span>
    </div>
  );
}

// ─── Error ───────────────────────────────────────────────────────────────
function ErrorView({ msg, onRetry }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", minHeight: "80vh", gap: 16,
    }}>
      <div style={{
        width: 80, height: 80, borderRadius: "50%", background: "#fee2e2",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <LuServerOff size={36} color="#dc2626" />
      </div>
      <h2 style={{ margin: 0, color: "#111827", fontSize: 20 }}>Không thể kết nối API</h2>
      <p style={{ color: "#6b7280", margin: 0, fontSize: 14 }}>{msg}</p>
      <button onClick={onRetry} style={{
        marginTop: 8, padding: "10px 24px", background: "#3b82f6", color: "white",
        border: "none", borderRadius: 10, cursor: "pointer", fontSize: 14, fontWeight: 600,
      }}>
        Thử lại ngay
      </button>
    </div>
  );
}

// ─── Camera Grid Item ────────────────────────────────────────────────────
function CameraGridItem({ cam }) {
  return (
    <div style={{
      padding: "10px 12px", borderRadius: 10,
      background: cam.cached ? "#f0fdf4" : "#fef2f2",
      border: `1px solid ${cam.cached ? "#bbf7d0" : "#fecaca"}`,
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: cam.cached ? "#166534" : "#991b1b", marginBottom: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {cam.name || cam.id.slice(-8)}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: cam.last_count != null ? 4 : 0 }}>
        {cam.cached ? <LuCircleCheck size={11} color="#16a34a" /> : <LuCircleX size={11} color="#dc2626" />}
        <span style={{ fontSize: 10, color: cam.cached ? "#16a34a" : "#dc2626" }}>
          {cam.cached ? "Có dữ liệu" : "Chưa có"}
        </span>
      </div>
      {cam.last_count != null && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 16, fontWeight: 800, color: "#111827" }}>{cam.last_count}</span>
          {cam.last_level && <DensityBadge level={cam.last_level} showEmoji={false} />}
        </div>
      )}
      {cam.district && (
        <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 3 }}>
          <LuMapPin size={9} style={{ verticalAlign: "middle" }} /> {cam.district}
        </div>
      )}
      {cam.last_car != null && (
        <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2, display: "flex", gap: 6 }}>
          <span>🚗 {cam.last_car}</span>
          <span>🏍 {cam.last_motorbike}</span>
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────
export default function DebugPage({ onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  const load = useCallback(() => {
    fetch("/api/debug")
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLastUpdated(new Date());
        setLoading(false);
        setError(null);
      })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  if (loading) return <Loading />;
  if (error) return <ErrorView msg={error} onRetry={load} />;

  const { health, database, cameras, writer, analytics } = data;
  const totalRecords = database?.total_records || 0;
  const totalCameras = cameras?.total || 0;
  const cachedCameras = cameras?.cached || 0;
  const byDensity = database?.by_density || {};
  const overall = database?.overall_stats || {};
  const topCameras = database?.top_cameras || [];
  const worstCongestion = database?.worst_congestion || [];
  const hourlyData = (database?.hourly_distribution || []).map(h => ({
    label: hourLabel(h.hour),
    value: h.count,
  }));
  const dailyData = (database?.daily_distribution || []).slice(0, 14).map(d => ({
    label: dayLabel(d.day),
    value: d.count,
  }));

  const peakHour = analytics?.peak_hour;

  return (
    <div style={{
      minHeight: "100vh", background: "#f8fafc",
      fontFamily: "'Segoe UI', 'Inter', -apple-system, sans-serif",
    }}>
      {/* ── Sticky Header ── */}
      <div style={{
        background: "linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 50%, #3b82f6 100%)",
        color: "white", position: "sticky", top: 0, zIndex: 100,
        boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
      }}>
        <div style={{ maxWidth: 1400, margin: "0 auto", padding: "20px 28px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
                <div style={{ background: "rgba(255,255,255,0.15)", borderRadius: 12, padding: "6px 10px" }}>
                  <LuActivity size={24} />
                </div>
                <div>
                  <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, letterSpacing: "-0.3px" }}>
                    TrafficFlow Dashboard
                  </h1>
                  <div style={{ fontSize: 12, opacity: 0.75 }}>
                    Hệ thống giám sát giao thông thông minh · TP. Hồ Chí Minh
                  </div>
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              {lastUpdated && (
                <div style={{ fontSize: 11, opacity: 0.75, textAlign: "right" }}>
                  <div>Cập nhật</div>
                  <div style={{ fontWeight: 600 }}>{lastUpdated.toLocaleTimeString("vi-VN")}</div>
                </div>
              )}
              <button onClick={load} style={{
                width: 36, height: 36, borderRadius: 8, border: "1px solid rgba(255,255,255,0.3)",
                background: "rgba(255,255,255,0.1)", color: "white", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
              }} title="Làm mới">
                <LuRefreshCw size={16} />
              </button>
              <button onClick={() => setAutoRefresh(v => !v)} style={{
                padding: "6px 14px", borderRadius: 8, border: "none", cursor: "pointer",
                fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 5,
                background: autoRefresh ? "#10b981" : "rgba(255,255,255,0.15)",
                color: "white",
              }}>
                <LuTimer size={13} /> {autoRefresh ? "Auto 5s" : "Auto OFF"}
              </button>
              {onBack && (
                <button onClick={onBack} style={{
                  padding: "6px 16px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.4)",
                  background: "transparent", color: "white", cursor: "pointer", fontSize: 13, fontWeight: 600,
                }}>
                  ← Quay lại
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "20px 24px 40px" }}>

        {/* ── Tab Nav ── */}
        <div style={{ display: "flex", gap: 4, marginBottom: 20, flexWrap: "wrap" }}>
          {[
            { id: "overview", label: "Tổng quan", icon: <LuGauge size={14} /> },
            { id: "analytics", label: "Phân tích chi tiết", icon: <LuActivity size={14} /> },
            { id: "cameras", label: "Camera", icon: <LuCamera size={14} /> },
            { id: "system", label: "Hệ thống", icon: <LuServer size={14} /> },
          ].map((tab) => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
              padding: "7px 16px", borderRadius: 8, border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 6,
              background: activeTab === tab.id ? "#1d4ed8" : "white",
              color: activeTab === tab.id ? "white" : "#374151",
              boxShadow: activeTab === tab.id ? "0 2px 8px rgba(29,78,216,0.3)" : "0 1px 3px rgba(0,0,0,0.08)",
              border: activeTab === tab.id ? "none" : "1px solid #e5e7eb",
            }}>
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>

        {/* ══════════════════════════════════════════════════════════ */}
        {/* TAB: TỔNG QUAN                                       */}
        {/* ══════════════════════════════════════════════════════════ */}
        {activeTab === "overview" && (
          <>
            {/* KPI Row */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: 14, marginBottom: 20,
            }}>
              <KpiCard icon={<LuDatabase size={22} />} label="Tổng bản ghi"
                value={fmtNum(totalRecords)}
                sub={`Mới nhất: ${fmtRelTime(database?.latest_prediction)}`}
                color="#3b82f6" bg="#eff6ff" trend={totalRecords > 0 ? "up" : undefined} />
              <KpiCard icon={<LuCamera size={22} />} label="Camera hoạt động"
                value={`${cachedCameras} / ${totalCameras}`}
                sub={`${totalCameras - cachedCameras} camera chưa có dữ liệu`}
                color="#8b5cf6" bg="#ede9fe" />
              <KpiCard icon={<LuCar size={22} />} label="TB xe/ lần dự đoán"
                value={overall.avg_total ? parseFloat(overall.avg_total).toFixed(1) : "—"}
                sub={`Car: ${overall.avg_car?.toFixed(1) || "—"} · Moto: ${overall.avg_motorbike?.toFixed(1) || "—"}`}
                color="#10b981" bg="#d1fae5" />
              <KpiCard icon={<LuHardDrive size={22} />} label="Uptime Database"
                value={uptimeStr(database?.uptime)}
                sub={database?.db_version || "PostgreSQL"}
                color="#f59e0b" bg="#fef3c7" />
            </div>

            {/* Row 2: Donut + Hourly + Quick Stats */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
              gap: 16, marginBottom: 20,
            }}>
              {/* Density Donut */}
              <Section icon={<LuActivity size={16} />} title="Phân bổ mật độ giao thông"
                badge={fmtNum(totalRecords)}>
                <DonutChart data={byDensity} />
              </Section>

              {/* Hourly distribution */}
              <Section icon={<LuClock size={16} />} title="Lưu lượng theo giờ (24h gần nhất)"
                badge={peakHour != null ? `Peak: ${hourLabel(peakHour)}` : null}>
                {hourlyData.length > 0 ? (
                  <BarChart data={hourlyData} color="#3b82f6" height={100} />
                ) : (
                  <div style={{ color: "#9ca3af", fontSize: 13, textAlign: "center", padding: "20px 0" }}>
                    Chưa có dữ liệu theo giờ
                  </div>
                )}
                <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px" }}>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>Giờ cao điểm</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>
                      {peakHour != null ? hourLabel(peakHour) : "—"}
                    </div>
                  </div>
                  <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px" }}>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>Tổng giờ</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>
                      {hourlyData.length}h
                    </div>
                  </div>
                </div>
              </Section>

              {/* Quick stats */}
              <Section icon={<LuGauge size={16} />} title="Thống kê nhanh">
                <HProgress label="🚗 Thông thoáng" value={overall.low_pct || 0} max={100}
                  color="#10b981" pct={overall.low_pct} />
                <HProgress label="🟡 Đông vừa" value={overall.moderate_pct || 0} max={100}
                  color="#f59e0b" pct={overall.moderate_pct} />
                <HProgress label="🔴 Kẹt xe" value={overall.heavy_pct || 0} max={100}
                  color="#ef4444" pct={overall.heavy_pct} />
                <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #f3f4f6" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px" }}>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>Cao nhất</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: "#ef4444" }}>
                        {overall.max_total ?? "—"}
                      </div>
                    </div>
                    <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px" }}>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>Thấp nhất</div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: "#10b981" }}>
                        {overall.min_total ?? "—"}
                      </div>
                    </div>
                  </div>
                </div>
              </Section>
            </div>

            {/* Row 3: Top Cameras + Daily trend */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))",
              gap: 16, marginBottom: 20,
            }}>
              <Section icon={<LuCamera size={16} />} title="Top 10 Camera — Nhiều dữ liệu nhất"
                badge={`${topCameras.length} camera`}>
                {topCameras.slice(0, 10).map((cam, i) => {
                  const info = cameras?.list?.find(c => c.id === cam.camera_id);
                  return (
                    <div key={cam.camera_id} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "8px 0", borderBottom: i < 9 ? "1px solid #f3f4f6" : "none",
                    }}>
                      <div style={{
                        width: 22, height: 22, borderRadius: 6,
                        background: i < 3 ? ["#fef3c7", "#e0e7ff", "#fce7f3"][i] : "#f3f4f6",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 11, fontWeight: 700, color: i < 3 ? "#92400e" : "#6b7280",
                        flexShrink: 0,
                      }}>
                        {i + 1}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {info?.name || cam.camera_id.slice(-8)}
                        </div>
                        <div style={{ fontSize: 11, color: "#9ca3af" }}>
                          {info?.district || "—"} · TB {parseFloat(cam.avg_count).toFixed(1)} xe/lần
                        </div>
                      </div>
                      <div style={{ textAlign: "right", flexShrink: 0 }}>
                        <div style={{ fontSize: 16, fontWeight: 800, color: "#111827" }}>
                          {cam.count.toLocaleString("vi-VN")}
                        </div>
                        <div style={{ fontSize: 10, color: "#9ca3af" }}>lần</div>
                      </div>
                    </div>
                  );
                })}
                {topCameras.length === 0 && (
                  <div style={{ color: "#9ca3af", fontSize: 13, textAlign: "center", padding: "20px 0" }}>
                    Chưa có dữ liệu camera
                  </div>
                )}
              </Section>

              {/* Daily trend */}
              <Section icon={<LuTrendingUp size={16} />} title="Xu hướng theo ngày (14 ngày gần nhất)"
                badge={dailyData.length > 0 ? `${dailyData.reduce((a, b) => a + b.value, 0).toLocaleString("vi-VN")} bản ghi` : null}>
                {dailyData.length > 0 ? (
                  <BarChart data={dailyData} color="#8b5cf6" height={100} />
                ) : (
                  <div style={{ color: "#9ca3af", fontSize: 13, textAlign: "center", padding: "20px 0" }}>
                    Chưa có dữ liệu theo ngày
                  </div>
                )}
                <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                  <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>Ngày nhiều nhất</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#8b5cf6" }}>
                      {dailyData.length > 0 ? Math.max(...dailyData.map(d => d.value)).toLocaleString("vi-VN") : "—"}
                    </div>
                  </div>
                  <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>Trung bình/ngày</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>
                      {dailyData.length > 0 ? Math.round(dailyData.reduce((a, b) => a + b.value, 0) / dailyData.length).toLocaleString("vi-VN") : "—"}
                    </div>
                  </div>
                  <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>Số ngày</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>{dailyData.length}</div>
                  </div>
                </div>
              </Section>
            </div>
          </>
        )}

        {/* ══════════════════════════════════════════════════════════ */}
        {/* TAB: PHÂN TÍCH CHI TIẾT                                  */}
        {/* ══════════════════════════════════════════════════════════ */}
        {activeTab === "analytics" && (
          <>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: 14, marginBottom: 20,
            }}>
              <KpiCard icon={<LuActivity size={22} />} label="Dự đoán/giờ (24h)"
                value={analytics?.predictions_per_hour_24h?.toFixed(1) || "—"}
                sub="trung bình 24 giờ qua"
                color="#6366f1" bg="#ede9fe" />
              <KpiCard icon={<LuFlame size={22} />} label="Quận kẹt nhất"
                value={analytics?.worst_district?.district || "—"}
                sub={analytics?.worst_district ? `TB ${parseFloat(analytics.worst_district.avg_count).toFixed(1)} xe` : "—"}
                color="#ef4444" bg="#fee2e2" />
              <KpiCard icon={<LuThermometer size={22} />} label="Giờ cao điểm"
                value={peakHour != null ? hourLabel(peakHour) : "—"}
                sub={analytics?.peak_hour_count ? `${analytics.peak_hour_count.toLocaleString("vi-VN")} dự đoán` : "—"}
                color="#f59e0b" bg="#fef3c7" />
              <KpiCard icon={<LuPackage size={22} />} label="Dung lượng DB"
                value={database?.db_size || "—"}
                sub={`Bản ghi: ${fmtNum(totalRecords)}`}
                color="#64748b" bg="#f1f5f9" />
            </div>

            {/* Detailed stats */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))",
              gap: 16, marginBottom: 20,
            }}>
              <Section icon={<LuGauge size={16} />} title="Thống kê tổng hợp toàn hệ thống">
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  <StatRow label="Tổng bản ghi" value={fmtNum(totalRecords)} icon={<LuDatabase size={12} />} color="#3b82f6" />
                  <StatRow label="Thời gian hoạt động DB" value={uptimeStr(database?.uptime)} icon={<LuClock size={12} />} />
                  <StatRow label="Phiên bản Database" value={database?.db_version} icon={<LuDatabase size={12} />} />
                  <StatRow label="Dung lượng Database" value={database?.db_size} icon={<LuHardDrive size={12} />} color="#f59e0b" />
                  <StatRow label="Camera theo dõi" value={`${cachedCameras} / ${totalCameras}`} icon={<LuCamera size={12} />} color="#8b5cf6" />
                  <StatRow label="Data mới nhất" value={fmtRelTime(database?.latest_prediction)} icon={<LuClock size={12} />} color="#10b981" />
                  <StatRow label="Data cũ nhất" value={fmtRelTime(database?.oldest_prediction)} icon={<LuClock size={12} />} />
                  <StatRow label="Giờ cao điểm" value={peakHour != null ? hourLabel(peakHour) : "—"} icon={<LuFlame size={12} />} color="#ef4444" />
                  <StatRow label="Quận kẹt nhất" value={analytics?.worst_district?.district || "—"} icon={<LuMapPin size={12} />} color="#dc2626" />
                </div>
              </Section>

              <Section icon={<LuActivity size={16} />} title="Phân bổ chi tiết">
                <HProgress label="🟢 Thông thoáng" color="#10b981" pct={overall.low_pct} />
                <HProgress label="🟡 Đông vừa" color="#f59e0b" pct={overall.moderate_pct} />
                <HProgress label="🔴 Kẹt xe" color="#ef4444" pct={overall.heavy_pct} />
                <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #f3f4f6" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 10 }}>Chi tiết xe</div>
                  <HProgress label="🚗 Ô tô trung bình" value={overall.avg_car} max={overall.avg_total || 1}
                    color="#3b82f6" pct={overall.avg_total > 0 ? (overall.avg_car / overall.avg_total) * 100 : 0} />
                  <HProgress label="🏍 Xe máy trung bình" value={overall.avg_motorbike} max={overall.avg_total || 1}
                    color="#f59e0b" pct={overall.avg_total > 0 ? (overall.avg_motorbike / overall.avg_total) * 100 : 0} />
                </div>
              </Section>
            </div>

            {/* Worst congestion + Top cameras detailed */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))",
              gap: 16, marginBottom: 20,
            }}>
              <Section icon={<LuFlame size={16} />} title="Top 10 — Quận nhiều kẹt xe nhất">
                {worstCongestion.map((cam, i) => {
                  const info = cameras?.list?.find(c => c.id === cam.camera_id);
                  return (
                    <div key={cam.camera_id} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "8px 0", borderBottom: i < 9 ? "1px solid #f3f4f6" : "none",
                    }}>
                      <div style={{ width: 22, height: 22, borderRadius: 6, background: "#fee2e2", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#dc2626", flexShrink: 0 }}>
                        {i + 1}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>
                          {info?.name || cam.camera_id.slice(-8)}
                        </div>
                        <div style={{ fontSize: 11, color: "#9ca3af" }}>{info?.district || "—"}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 16, fontWeight: 800, color: "#ef4444" }}>
                          {parseFloat(cam.avg_count).toFixed(1)}
                        </div>
                        <div style={{ fontSize: 10, color: "#9ca3af" }}>TB xe/lần</div>
                      </div>
                      <div style={{ textAlign: "right", minWidth: 60 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: "#dc2626" }}>
                          {parseFloat(cam.heavy_pct).toFixed(0)}%
                        </div>
                        <div style={{ fontSize: 10, color: "#9ca3af" }}>kẹt xe</div>
                      </div>
                    </div>
                  );
                })}
                {worstCongestion.length === 0 && (
                  <div style={{ color: "#9ca3af", fontSize: 13, textAlign: "center", padding: "20px 0" }}>
                    Chưa có dữ liệu
                  </div>
                )}
              </Section>

              <Section icon={<LuListChecks size={16} />} title="Top 10 Camera — Chi tiết đầy đủ">
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr>
                        {["#", "Camera", "Quận", "Số lần", "TB xe", "TB ô tô", "TB xe máy", "Max", "Std"].map(h => (
                          <th key={h} style={{ padding: "8px 6px", textAlign: "center", background: "#f9fafb", color: "#6b7280", fontWeight: 600, fontSize: 10, textTransform: "uppercase", borderBottom: "1px solid #e5e7eb" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {topCameras.slice(0, 10).map((cam, i) => {
                        const info = cameras?.list?.find(c => c.id === cam.camera_id);
                        return (
                          <tr key={cam.camera_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                            <td style={{ padding: "7px 6px", textAlign: "center", fontWeight: 700, color: i < 3 ? "#3b82f6" : "#6b7280" }}>{i + 1}</td>
                            <td style={{ padding: "7px 6px", color: "#111827", fontWeight: 500 }}>
                              <div style={{ maxWidth: 120, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                {info?.name || cam.camera_id.slice(-8)}
                              </div>
                            </td>
                            <td style={{ padding: "7px 6px", textAlign: "center", color: "#6b7280", fontSize: 11 }}>{info?.district || "—"}</td>
                            <td style={{ padding: "7px 6px", textAlign: "right", fontWeight: 700, color: "#111827" }}>{cam.count.toLocaleString("vi-VN")}</td>
                            <td style={{ padding: "7px 6px", textAlign: "right", fontWeight: 700, color: "#3b82f6" }}>{parseFloat(cam.avg_count).toFixed(1)}</td>
                            <td style={{ padding: "7px 6px", textAlign: "right", color: "#374151" }}>{parseFloat(cam.avg_car || 0).toFixed(1)}</td>
                            <td style={{ padding: "7px 6px", textAlign: "right", color: "#374151" }}>{parseFloat(cam.avg_motorbike || 0).toFixed(1)}</td>
                            <td style={{ padding: "7px 6px", textAlign: "right", color: "#ef4444", fontWeight: 600 }}>{cam.max_count || "—"}</td>
                            <td style={{ padding: "7px 6px", textAlign: "right", color: "#6b7280", fontFamily: "monospace", fontSize: 11 }}>{parseFloat(cam.std_count || 0).toFixed(1)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Section>
            </div>
          </>
        )}

        {/* ══════════════════════════════════════════════════════════ */}
        {/* TAB: CAMERA                                             */}
        {/* ══════════════════════════════════════════════════════════ */}
        {activeTab === "cameras" && (
          <>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: 14, marginBottom: 20,
            }}>
              <KpiCard icon={<LuCamera size={22} />} label="Tổng số Camera"
                value={totalCameras}
                sub={`${cameras?.districts?.length || 0} quận/huyện`}
                color="#3b82f6" bg="#eff6ff" />
              <KpiCard icon={<LuCircleCheck size={22} />} label="Camera có dữ liệu"
                value={cachedCameras}
                sub={`${totalCameras - cachedCameras} camera chưa có`}
                color="#10b981" bg="#d1fae5" />
              <KpiCard icon={<LuEye size={22} />} label="Tỷ lệ hoạt động"
                value={totalCameras > 0 ? `${((cachedCameras / totalCameras) * 100).toFixed(0)}%` : "—"}
                sub={`${cachedCameras} / ${totalCameras}`}
                color="#8b5cf6" bg="#ede9fe" />
              <KpiCard icon={<LuMapPin size={22} />} label="Quận/Huyện"
                value={cameras?.districts?.length || 0}
                sub={cameras?.districts?.join(", ") || "—"}
                color="#f59e0b" bg="#fef3c7" />
            </div>

            {/* Camera grid */}
            <Section icon={<LuEye size={16} />} title={`Danh sách Camera (${cameras?.list?.length || 0})`}
              badge={`${cachedCameras} hoạt động`}>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
                gap: 10,
              }}>
                {(cameras?.list || []).map(cam => (
                  <CameraGridItem key={cam.id} cam={cam} />
                ))}
              </div>
            </Section>
          </>
        )}

        {/* ══════════════════════════════════════════════════════════ */}
        {/* TAB: HỆ THỐNG                                           */}
        {/* ══════════════════════════════════════════════════════════ */}
        {activeTab === "system" && (
          <>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
              gap: 16, marginBottom: 20,
            }}>
              <Section icon={<LuServer size={16} />} title="Tình trạng hệ thống">
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: health?.model_loaded ? "#dcfce7" : "#fef3c7", borderRadius: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: health?.model_loaded ? "#15803d" : "#92400e" }}>Model AI</span>
                    <StatusBadge ok={health?.model_loaded} label={health?.model_loaded ? "Đã tải" : "Chưa tải"} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: database?.status === "connected" ? "#dcfce7" : "#fee2e2", borderRadius: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: database?.status === "connected" ? "#15803d" : "#dc2626" }}>Database</span>
                    <StatusBadge ok={database?.status === "connected"} label={database?.status === "connected" ? "Kết nối" : "Mất kết nối"} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", background: writer?.status === "running" ? "#dcfce7" : "#fef3c7", borderRadius: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: writer?.status === "running" ? "#15803d" : "#92400e" }}>Auto-writer</span>
                    <StatusBadge ok={writer?.status === "running"} label={writer?.status === "running" ? "Đang chạy" : "Dừng"} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f3f4f6" }}>
                    <span style={{ fontSize: 13, color: "#6b7280" }}>Thiết bị</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#111827", background: "#f3f4f6", padding: "2px 10px", borderRadius: 6 }}>{health?.device || "—"}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0" }}>
                    <span style={{ fontSize: 13, color: "#6b7280" }}>Chu kỳ ghi</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{writer?.interval_seconds ? `${writer.interval_seconds} giây` : "—"}</span>
                  </div>
                </div>
              </Section>

              <Section icon={<LuCpu size={16} />} title="Thông tin Model AI">
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  <StatRow label="Tên model" value={health?.model?.model_name || "—"} icon={<LuPackage size={12} />} color="#3b82f6" />
                  <StatRow label="Loại model" value={health?.model?.model_type || "ZIP"} icon={<LuCpu size={12} />} />
                  <StatRow label="Thiết bị" value={health?.device || "—"} icon={<LuServer size={12} />} />
                  <StatRow label="Input size" value={health?.model?.input_size ? `${health.model.input_size}px` : "—"} icon={<LuGauge size={12} />} />
                  <StatRow label="Block size" value={health?.model?.block_size || "—"} icon={<LuGauge size={12} />} />
                  <StatRow label="Zero-inflated" value={health?.model?.zero_inflated != null ? (health.model.zero_inflated ? "Có" : "Không") : "—"} icon={<LuGauge size={12} />} />
                  <StatRow label="Trạng thái" value={health?.model_loaded ? "Đã tải" : "Chưa tải"} icon={health?.model_loaded ? <LuCircleCheck size={12} /> : <LuCircleX size={12} />} color={health?.model_loaded ? "#15803d" : "#dc2626"} />
                </div>
              </Section>

              <Section icon={<LuDatabase size={16} />} title="Database">
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  <StatRow label="Trạng thái" value={database?.status === "connected" ? "Kết nối" : "Mất kết nối"} icon={<LuWifi size={12} />} color={database?.status === "connected" ? "#15803d" : "#dc2626"} />
                  <StatRow label="Phiên bản" value={database?.db_version || "—"} icon={<LuPackage size={12} />} />
                  <StatRow label="Dung lượng" value={database?.db_size || "—"} icon={<LuHardDrive size={12} />} color="#f59e0b" />
                  <StatRow label="Uptime" value={uptimeStr(database?.uptime)} icon={<LuTimer size={12} />} />
                  <StatRow label="Tổng bản ghi" value={fmtNum(totalRecords)} icon={<LuDatabase size={12} />} color="#3b82f6" />
                  <StatRow label="Mới nhất" value={fmtRelTime(database?.latest_prediction)} icon={<LuClock size={12} />} color="#10b981" />
                  <StatRow label="Cũ nhất" value={fmtRelTime(database?.oldest_prediction)} icon={<LuClock size={12} />} />
                </div>
              </Section>
            </div>
          </>
        )}

        {/* ── Footer ── */}
        <div style={{
          textAlign: "center", padding: "24px 0", fontSize: 12, color: "#9ca3af",
          borderTop: "1px solid #e5e7eb", marginTop: 20,
        }}>
          TrafficFlow Dashboard · {new Date().getFullYear()} · Hệ thống giám sát giao thông TP.HCM · {fmtNum(totalRecords)} bản ghi
        </div>
      </div>
    </div>
  );
}
