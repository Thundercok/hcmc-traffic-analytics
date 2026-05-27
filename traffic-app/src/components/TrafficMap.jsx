import React, { useEffect, useRef, useMemo, useCallback, useState, Suspense } from "react";
import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  CircleMarker,
  Tooltip,
  useMap,
  ZoomControl,
} from "react-leaflet";
import L from "leaflet";
import { useDebug } from "../contexts/DebugContext";
import CameraPopup from "./CameraPopup";
import "leaflet/dist/leaflet.css";

// Fix Leaflet default icon issue in bundlers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// ── Static icons (created once at module level) ──
const CAMERA_ICON = L.divIcon({
  className: "",
  html: `<div class="camera-marker"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.934a.5.5 0 0 0-.777-.416L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/></svg></div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
  popupAnchor: [0, -20],
});

const USER_ICON = L.divIcon({
  className: "",
  html: `<div style="width:16px;height:16px;background:#4285F4;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.3)"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

const DEST_ICON = L.divIcon({
  className: "",
  html: `<div style="width:16px;height:16px;background:#EA4335;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.3)"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

const MAP_CENTER = [10.7769, 106.7009];
const MAP_ZOOM = 12;

// Suspense fallback (stable reference)
const POPUP_FALLBACK = (
  <div
    style={{
      width: 220,
      height: 120,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}
  >
    Đang tải...
  </div>
);

// ── Map style / tile layer config ──
const MAP_STYLES = {
  voyager: {
    id: "voyager",
    label: "Bản đồ",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    subdomains: undefined,
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    labelOverlay: null,
    preview: "https://tile.openstreetmap.org/8/199/121.png",
  },
  satellite: {
    id: "satellite",
    label: "Vệ tinh",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    subdomains: undefined,
    maxZoom: 19,
    attribution: '&copy; Esri',
    labelOverlay: null,
    preview: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/8/121/199",
  },
  terrain: {
    id: "terrain",
    label: "Địa hình",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    subdomains: "abc",
    maxZoom: 17,
    attribution: '&copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
    labelOverlay: null,
    preview: "https://a.tile.opentopomap.org/8/199/121.png",
  },
  dark: {
    id: "dark",
    label: "Tối",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    subdomains: "abcd",
    maxZoom: 20,
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    labelOverlay: null,
    preview: "https://a.basemaps.cartocdn.com/dark_all/8/199/121.png",
  },
};
const MAP_STYLE_LIST = Object.values(MAP_STYLES);

// ── Nominatim geocoding cache (debounced to avoid rate limits) ──
const GEOCODE_CACHE_TTL = 60000; // 60 seconds cache
const _geocodeCache = new Map();
const _geocodeDebounce = new Map();

function debouncedGeocode(lat, lon, callback) {
  const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
  
  // Check cache first
  const cached = _geocodeCache.get(key);
  if (cached && Date.now() - cached.timestamp < GEOCODE_CACHE_TTL) {
    callback(cached.address);
    return;
  }
  
  // Check if there's a pending request for this location
  if (_geocodeDebounce.has(key)) {
    clearTimeout(_geocodeDebounce.get(key));
  }
  
  // Debounce: wait 500ms before making request
  const timerId = setTimeout(() => {
    _geocodeDebounce.delete(key);
    fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`)
      .then(r => r.json())
      .then(data => {
        const address = data.display_name?.split(",").slice(0, 3).join(",").trim() || "Vị trí không xác định";
        _geocodeCache.set(key, { address, timestamp: Date.now() });
        callback(address);
      })
      .catch(() => callback("Vị trí không xác định"));
  }, 500);
  
  _geocodeDebounce.set(key, timerId);
}

// ── Travel mode config (calibrated for HCMC urban traffic) ──
// Average speeds account for: red lights, congestion, narrow alleys, u-turns
const MODE_CONFIG = {
  car:       { avgSpeedKmh: 25,  lineColor: "#4285F4" },
  motorbike: { avgSpeedKmh: 30,  lineColor: "#4285F4" },
  bicycle:   { avgSpeedKmh: 15,  lineColor: "#0B8043" },
  walking:   { avgSpeedKmh: 5,   lineColor: "#4285F4" },
};

// ── Vietnamese routing instruction translator ──
const MODIFIER_VI = {
  uturn: "Quay đầu",
  "sharp right": "Rẽ gấp phải",
  right: "Rẽ phải",
  "slight right": "Nghiêng phải",
  straight: "Đi thẳng",
  "slight left": "Nghiêng trái",
  left: "Rẽ trái",
  "sharp left": "Rẽ gấp trái",
};

const TYPE_VI = {
  depart: "Xuất phát",
  arrive: "Đến nơi",
  merge: "Nhập làn",
  "on ramp": "Lên dốc",
  "off ramp": "Rời đường",
  fork: "Ngã rẽ",
  "end of road": "Cuối đường",
  roundabout: "Vòng xuyến",
  rotary: "Bùng binh",
  "roundabout turn": "Vòng xuyến",
  notification: "",
  "exit roundabout": "Rời vòng xuyến",
  "exit rotary": "Rời bùng binh",
};

// Convert OSRM bearing (0-360°) to Vietnamese cardinal direction
function bearingToVietnamese(bearing) {
  const dirs = [
    "hướng bắc", "hướng đông bắc", "hướng đông", "hướng đông nam",
    "hướng nam", "hướng tây nam", "hướng tây", "hướng tây bắc",
  ];
  const idx = Math.round(((bearing % 360) + 360) % 360 / 45) % 8;
  return dirs[idx];
}

function translateOsrmStep(step) {
  const type = step.maneuver?.type || "turn";
  const mod = step.maneuver?.modifier || "";
  const street = step.name || "";

  // Get base direction from modifier, fallback to type
  let direction = MODIFIER_VI[mod] || TYPE_VI[type] || "Đi thẳng";

  // Special types override modifier
  if (type === "depart") {
    // Include cardinal direction from bearing
    const bearing = step.maneuver?.bearing_after;
    const cardinal = bearing != null ? bearingToVietnamese(bearing) : "";
    direction = cardinal ? `Xuất phát ${cardinal}` : "Xuất phát";
  } else if (type === "arrive") direction = "Đến nơi";
  else if (type === "roundabout" || type === "rotary") {
    const exit = step.maneuver?.exit;
    direction = exit
      ? `Vào vòng xuyến, ra lối thứ ${exit}`
      : "Vào vòng xuyến";
  } else if (type === "merge") direction = "Nhập làn";
  else if (type === "fork") {
    direction = mod.includes("left") ? "Rẽ trái tại ngã rẽ" : mod.includes("right") ? "Rẽ phải tại ngã rẽ" : "Ngã rẽ";
  } else if (type === "new name" || type === "continue") {
    direction = "Đi tiếp";
  }

  const suffix = street ? ` vào ${street}` : "";
  const instruction = `${direction}${suffix}`;

  const dist = step.distance;
  const distance = dist > 1000
    ? `${(dist / 1000).toFixed(1)}km`
    : `${Math.round(dist)}m`;

  return { instruction, distance };
}

// Translate English LRM instructions to Vietnamese
function translateLrmInstruction(text) {
  if (!text) return "";
  return text
    .replace(/^Head\b/i, "Xuất phát")
    .replace(/^Turn left/i, "Rẽ trái")
    .replace(/^Turn right/i, "Rẽ phải")
    .replace(/^Turn sharp left/i, "Rẽ gấp trái")
    .replace(/^Turn sharp right/i, "Rẽ gấp phải")
    .replace(/^Turn slight left/i, "Nghiêng trái")
    .replace(/^Turn slight right/i, "Nghiêng phải")
    .replace(/^Slight left/i, "Nghiêng trái")
    .replace(/^Slight right/i, "Nghiêng phải")
    .replace(/^Sharp left/i, "Rẽ gấp trái")
    .replace(/^Sharp right/i, "Rẽ gấp phải")
    .replace(/^Continue/i, "Đi tiếp")
    .replace(/^Keep left/i, "Giữ trái")
    .replace(/^Keep right/i, "Giữ phải")
    .replace(/^Go straight/i, "Đi thẳng")
    .replace(/^Make a U-turn/i, "Quay đầu")
    .replace(/^Merge/i, "Nhập làn")
    .replace(/^Fork left/i, "Rẽ trái tại ngã rẽ")
    .replace(/^Fork right/i, "Rẽ phải tại ngã rẽ")
    .replace(/^At the roundabout/i, "Tại vòng xuyến")
    .replace(/^Enter the roundabout/i, "Vào vòng xuyến")
    .replace(/^You have arrived/i, "Đã đến nơi")
    .replace(/\bon(?:to)?\b/gi, "vào")
    .replace(/\band\b/gi, "và")
    .replace(/\bthen\b/gi, "rồi")
    .replace(/\bstraight\b/gi, "thẳng")
    .replace(/\bdestination\b/gi, "đích")
    .replace(/\bthe (\d+)(?:st|nd|rd|th) exit\b/gi, "ra lối thứ $1")
    // Cardinal directions (compound FIRST to avoid partial match)
    .replace(/\bnortheast\b/gi, "hướng đông bắc")
    .replace(/\bnorthwest\b/gi, "hướng tây bắc")
    .replace(/\bsoutheast\b/gi, "hướng đông nam")
    .replace(/\bsouthwest\b/gi, "hướng tây nam")
    .replace(/\bsouth\b/gi, "hướng nam")
    .replace(/\bnorth\b/gi, "hướng bắc")
    .replace(/\beast\b/gi, "hướng đông")
    .replace(/\bwest\b/gi, "hướng tây");
}

// ── Heatmap density colors ──
const DENSITY_COLORS = {
  low: { fill: "#10b981", stroke: "#059669" },
  moderate: { fill: "#f59e0b", stroke: "#d97706" },
  heavy: { fill: "#ef4444", stroke: "#dc2626" },
  severe: { fill: "#1f2937", stroke: "#111827" },
};

// ── Traffic route segment colors (Google Maps style) ──
const TRAFFIC_ROUTE_COLORS = {
  low: "#0B8043",
  moderate: "#F9AB00",
  heavy: "#EA4335",
  severe: "#B31412",
  unknown: "#4285F4",
};

// ── Haversine distance (meters) ──
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ── Build traffic-colored route segments ──
function buildTrafficSegments(routeCoords, predictions, fallbackColor) {
  if (!predictions?.length) return null;

  const segments = [];
  let curColor = null;
  let curPositions = [];

  for (const coord of routeCoords) {
    let density = "unknown";
    let minDist = Infinity;
    for (const p of predictions) {
      const d = haversine(coord[0], coord[1], p.lat, p.lng);
      if (d < 500 && d < minDist) {
        minDist = d;
        density = p.prediction.density_level;
      }
    }
    const color = TRAFFIC_ROUTE_COLORS[density] || fallbackColor;
    if (color !== curColor) {
      if (curPositions.length > 1) segments.push({ color: curColor, positions: [...curPositions] });
      curColor = color;
      curPositions = curPositions.length ? [curPositions[curPositions.length - 1], coord] : [coord];
    } else {
      curPositions.push(coord);
    }
  }
  if (curPositions.length > 1) segments.push({ color: curColor, positions: curPositions });
  return segments;
}

// ── Simulate Future Traffic (Heuristic based on HCMC rush hours) ──
// Uses deterministic hash based on camera_id for consistent results
function hashCode(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

function simulateFutureTraffic(predictions, sliderValue) {
  if (!sliderValue || sliderValue === 0 || !predictions) return predictions;
  
  // sliderValue index: 0 (Hiện tại), 1 (+1h), 2 (+2h), 3 (+4h)
  const offsetMap = { 0: 0, 1: 1, 2: 2, 3: 4 };
  const offsetHours = offsetMap[sliderValue] || 0;
  if (offsetHours === 0) return predictions;

  const targetHour = (new Date().getHours() + offsetHours) % 24;
  // HCMC Rush hours: 7AM-9AM and 5PM-7PM
  const isRushHour = (targetHour >= 7 && targetHour <= 9) || (targetHour >= 17 && targetHour <= 19);
  // Night time: 10PM to 5AM
  const isNight = (targetHour >= 22 || targetHour <= 5);

  const levels = ["low", "moderate", "heavy", "severe"];
  
  return predictions.map(p => {
    // Deep copy to avoid mutating cache
    const newP = { ...p, prediction: { ...p.prediction } };
    let levelIdx = levels.indexOf(newP.prediction.density_level);
    if (levelIdx === -1) levelIdx = 0;

    if (isNight) {
      // Traffic drops significantly at night
      levelIdx = Math.max(0, levelIdx - 2); 
    } else if (isRushHour) {
      // Traffic increases during rush hour
      levelIdx = Math.min(3, levelIdx + 1);
      // Deterministically make some heavy traffic severe based on camera_id hash
      if (levelIdx === 2) {
        const hash = hashCode(p.camera_id || String(p.camera_id) || '');
        if (hash % 2 === 0) levelIdx = 3; // 50% become severe based on hash
      }
    } else {
      // Normal hours: traffic tends to moderate/low
      if (levelIdx > 1) levelIdx -= 1; 
    }
    
    newP.prediction.density_level = levels[levelIdx];
    return newP;
  });
}

// ── Helper: format duration for display ──
function formatEta(durationMin) {
  if (!durationMin) return "";
  if (durationMin >= 60) {
    const hours = Math.floor(durationMin / 60);
    const mins = durationMin % 60;
    return mins > 0 ? `${hours} giờ ${mins} phút` : `${hours} giờ`;
  }
  return `${durationMin} phút`;
}

// ── Helper: process raw route data into app-consumable shape ──
function processRouteResult(r, modeConf) {
  if (!r) return null;

  const coords = (r.coordinates || r.positions || [])
    .map((c) => {
      if (Array.isArray(c)) return [c[0], c[1]];
      if (c.lat !== undefined && c.lng !== undefined) return [c.lat, c.lng];
      return null;
    })
    .filter(Boolean);

  const distanceKm =
    r.summary && r.summary.totalDistance
      ? (r.summary.totalDistance / 1000).toFixed(1)
      : r.distance || "";

  // Calculate ETA using calibrated HCMC average speed (not OSRM's optimistic highway estimate)
  let durationMin;
  if (r.summary && r.summary.totalDistance) {
    const distKm = r.summary.totalDistance / 1000;
    durationMin = Math.round((distKm / modeConf.avgSpeedKmh) * 60);
  } else if (typeof r.distance === "string" && r.distance.includes("km")) {
    const distKm = parseFloat(r.distance);
    if (!isNaN(distKm)) durationMin = Math.round((distKm / modeConf.avgSpeedKmh) * 60);
  } else {
    durationMin = r.duration || "";
  }

  const steps = (r.steps || r.instructions || []).map((ins) => {
    if (!ins) return { instruction: "", distance: "" };
    // LRM instructions come as { text, distance } — translate text to Vietnamese
    if (ins.text)
      return {
        instruction: translateLrmInstruction(ins.text),
        distance: ins.distance
          ? ins.distance > 1000
            ? `${(ins.distance / 1000).toFixed(1)}km`
            : `${Math.round(ins.distance)}m`
          : "",
      };
    return {
      instruction: ins.instruction || ins.name || "",
      distance: typeof ins.distance === "string" 
        ? ins.distance 
        : ins.distance
          ? ins.distance > 1000
            ? `${(ins.distance / 1000).toFixed(1)}km`
            : `${Math.round(ins.distance)}m`
          : "",
    };
  });

  return {
    segments: [{ color: modeConf.lineColor, positions: coords }],
    positions: coords,
    eta: formatEta(durationMin) || r.eta || "",
    distance: distanceKm ? `${distanceKm} km` : r.distance || "",
    steps,
  };
}

// ── MapController: fly to user location ──
function MapController({ userLocation }) {
  const map = useMap();
  useEffect(() => {
    if (userLocation) {
      map.flyTo(userLocation, 15, { animate: true, duration: 1.5 });
    }
  }, [userLocation, map]);
  return null;
}

// ── Dropped Pin icon (Google Maps style) ──
const DROPPED_PIN_ICON = L.divIcon({
  className: "",
  html: `<div style="width:14px;height:14px;background:#E53935;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.4)"></div>`,
  iconSize: [18, 18],
  iconAnchor: [9, 18],
  popupAnchor: [0, -20],
});

// ── LongPressHandler: detects 600ms hold on map ──
function LongPressHandler({ onLongPress }) {
  const map = useMap();
  const timerRef = useRef(null);
  const startPosRef = useRef(null);

  useEffect(() => {
    const handleDown = (e) => {
      startPosRef.current = e.containerPoint;
      timerRef.current = setTimeout(() => {
        onLongPress?.(e.latlng);
      }, 600);
    };

    const handleUp = () => clearTimeout(timerRef.current);
    const handleMove = (e) => {
      // Cancel if finger/mouse moved more than 10px (dragging)
      if (
        startPosRef.current &&
        e.containerPoint.distanceTo(startPosRef.current) > 10
      ) {
        clearTimeout(timerRef.current);
      }
    };

    // Disable browser context menu on the map container
    const container = map.getContainer();
    const preventContext = (e) => e.preventDefault();
    container.addEventListener("contextmenu", preventContext);

    map.on("mousedown", handleDown);
    map.on("mouseup", handleUp);
    map.on("mousemove", handleMove);

    return () => {
      clearTimeout(timerRef.current);
      map.off("mousedown", handleDown);
      map.off("mouseup", handleUp);
      map.off("mousemove", handleMove);
      container.removeEventListener("contextmenu", preventContext);
    };
  }, [map, onLongPress]);

  return null;
}

// ── MapStyleSwitcher: floating panel to change map tiles ──
function MapStyleSwitcher({ mapStyle, onChange }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="map-style-switcher" data-open={isOpen}>
      {/* Collapsed: show current style thumbnail */}
      <button
        className="map-style-switcher__toggle"
        onClick={() => setIsOpen(!isOpen)}
        title="Kiểu bản đồ"
      >
        <img
          src={mapStyle.preview}
          alt={mapStyle.label}
          className="map-style-switcher__preview"
        />
        <span className="map-style-switcher__current-label">
          {mapStyle.label}
        </span>
      </button>

      {/* Expanded: show all style options */}
      {isOpen && (
        <div className="map-style-switcher__panel">
          {MAP_STYLE_LIST.map((style) => (
            <button
              key={style.id}
              className={`map-style-switcher__option ${
                mapStyle.id === style.id
                  ? "map-style-switcher__option--active"
                  : ""
              }`}
              onClick={() => {
                onChange(style);
                setIsOpen(false);
              }}
            >
              <img
                src={style.preview}
                alt={style.label}
                className="map-style-switcher__thumb"
              />
              <span className="map-style-switcher__label">{style.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── DroppedPin: shows popup with address + origin/destination buttons ──
function DroppedPin({ position, onSetOrigin, onSetDestination, onClose }) {
  const [address, setAddress] = useState("Đang tải địa chỉ...");

  useEffect(() => {
    let cancelled = false;
    let timeoutId = null;
    
    debouncedGeocode(position[0], position[1], (result) => {
      if (!cancelled) {
        setAddress(result);
      }
    });
    
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [position]);

  const btnStyle = {
    padding: "6px 12px",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    display: "flex",
    alignItems: "center",
    gap: 4,
    flex: 1,
    justifyContent: "center",
  };

  return (
    <Marker position={position} icon={DROPPED_PIN_ICON}>
      <Popup
        autoPan={true}
        closeButton={true}
        eventHandlers={{ remove: onClose }}
      >
        <div style={{ minWidth: 180 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              marginBottom: 8,
              color: "#1e293b",
              lineHeight: 1.4,
            }}
          >
            📍 {address}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              style={{ ...btnStyle, background: "#3b82f6", color: "white" }}
              onClick={() => onSetOrigin(position, address)}
            >
              Đi từ đây
            </button>
            <button
              style={{ ...btnStyle, background: "#ef4444", color: "white" }}
              onClick={() => onSetDestination(position, address)}
            >
              Đến đây
            </button>
          </div>
        </div>
      </Popup>
    </Marker>
  );
}

// ── AI-Aware Dynamic Penalized Routing ──
function AIAwareRouting({ from, to, liveCameras, sliderValue, travelMode, onRouteFound, onRouteTraffic }) {
  const map = useMap();
  const { logRequest, logResponse, logError, logInfo, startAnalysis, endAnalysis } = useDebug();

  useEffect(() => {
    if (!from || !to) return;
    let cancelled = false;

    (async () => {
      try {
        const modeConf = MODE_CONFIG[travelMode] || MODE_CONFIG.car;
        // OSRM profile
        const profile = travelMode === 'walking' ? 'foot' : travelMode === 'bicycle' ? 'bike' : 'driving';
        
        startAnalysis();
        logInfo("Starting route calculation", { from, to, travelMode });
        
        // 1. Request top 3 alternatives from OSRM
        const url = `https://router.project-osrm.org/route/v1/${profile}/${from[1]},${from[0]};${to[1]},${to[0]}?overview=full&geometries=geojson&steps=true&alternatives=3`;
        logRequest("GET", "/route/v1/*", { profile, camerasCount: uniqueCamIds.size });
        const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
        const data = await res.json();
        logResponse("/route/v1/*", data, res.status);
        
        if (cancelled || !data?.routes?.length) return;
        
        // 2. Gather ALL unique cameras for ALL routes
        const allCoords = [];
        const routeCamMap = new Map(); // route_index -> camera[]

        data.routes.forEach((route, idx) => {
          const coords = route.geometry?.coordinates?.map(c => [c[1], c[0]]) || [];
          allCoords.push(coords);
          
          const sampled = coords.filter((_, i) => i % 10 === 0 || i === coords.length - 1);
          const nearbyCameras = liveCameras.filter(cam =>
            sampled.some(coord => haversine(cam.lat, cam.lng, coord[0], coord[1]) <= 500)
          );
          routeCamMap.set(idx, nearbyCameras);
        });

        // 3. Batch Predict ALL unique cameras ONCE
        const uniqueCamIds = new Set();
        routeCamMap.forEach(cams => cams.forEach(c => uniqueCamIds.add(c.id)));
        
        const predictionDict = {};
        if (uniqueCamIds.size > 0) {
            const apiUrl = import.meta.env.VITE_API_URL || "/api";
            logRequest("POST", "/predict/batch", { camera_ids: Array.from(uniqueCamIds) });
            const camRes = await fetch(`${apiUrl}/predict/batch`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ camera_ids: Array.from(uniqueCamIds) }),
            });
            if (camRes.ok && !cancelled) {
               const camData = await camRes.json();
               logResponse("/predict/batch", camData, camRes.status);
               if (camData?.predictions?.length > 0) {
                 const simulated = simulateFutureTraffic(camData.predictions, sliderValue);
                 simulated.forEach(p => {
                    predictionDict[p.camera_id] = p;
                 });
                 logInfo(`Loaded ${camData.predictions.length} predictions`);
               }
            } else {
              logError("Predict batch failed", await camRes.text());
            }
        }
        
        if (cancelled) return;

        // 4. Score each route
        let bestRouteResult = null;
        let bestTrafficAnalysis = null;
        let bestScore = Infinity;
        const alternativeSegments = []; // for drawing gray lines

        data.routes.forEach((route, idx) => {
          const coords = allCoords[idx];
          const processedResult = processRouteResult({
             coordinates: coords.map(c => ({lat: c[0], lng: c[1]})),
             summary: { totalDistance: route.distance, totalTime: route.duration },
             instructions: [],
             steps: route.legs?.[0]?.steps?.map(translateOsrmStep) || []
          }, modeConf);

          const nearbyCameras = routeCamMap.get(idx) || [];
          const routePredictions = nearbyCameras.map(c => predictionDict[c.id]).filter(Boolean);

          let routeTrafficAnalysis = { camerasAnalyzed: 0, congestionPoints: 0, level: "low", segments: null, predictions: [] };
          let penaltyMins = 0;

          if (routePredictions.length > 0) {
             let heavyCount = 0;
             let severeCount = 0;
             routePredictions.forEach(p => {
                if (p.prediction.density_level === "heavy") heavyCount++;
                if (p.prediction.density_level === "severe") severeCount++;
             });
             
             penaltyMins = (heavyCount * 5) + (severeCount * 10);
             const congestionPoints = heavyCount + severeCount;
             routeTrafficAnalysis = {
               camerasAnalyzed: routePredictions.length,
               congestionPoints,
               level: congestionPoints >= 2 ? "heavy" : congestionPoints === 1 ? "moderate" : "low",
               segments: buildTrafficSegments(coords, routePredictions, modeConf.lineColor),
               predictions: routePredictions
             };
          }

          const distKm = route.distance / 1000;
          const baseDurationMin = Math.round((distKm / modeConf.avgSpeedKmh) * 60);
          const adjustedEta = baseDurationMin + penaltyMins;

          if (adjustedEta < bestScore) {
             // If there was a previous best, demote it to alternative (gray line)
             if (bestRouteResult && bestRouteResult.positions) {
                alternativeSegments.push({ 
                  color: "#94a3b8", 
                  positions: bestRouteResult.positions,
                  weight: 5,
                  opacity: 0.5 
                });
             }

             bestScore = adjustedEta;
             bestRouteResult = {
               ...processedResult,
               eta: formatEta(adjustedEta),
               segments: routeTrafficAnalysis.segments || [{ color: modeConf.lineColor, positions: coords }]
             };
             bestTrafficAnalysis = routeTrafficAnalysis;
          } else {
             // Not the best, add to alternatives
             alternativeSegments.push({ 
               color: "#94a3b8", 
               positions: coords,
               weight: 5,
               opacity: 0.5 
             });
          }
        });

        if (cancelled) return;

        // 5. Emit the BEST route and prepend alternative paths to be drawn beneath
        if (bestRouteResult) {
          bestRouteResult.segments = [...alternativeSegments, ...(bestRouteResult.segments || [])];
          
          logInfo("Route calculation complete", {
            bestEta: bestRouteResult.eta,
            camerasAnalyzed: bestTrafficAnalysis.camerasAnalyzed,
            congestionPoints: bestTrafficAnalysis.congestionPoints
          });
          
          onRouteFound?.(bestRouteResult);
          onRouteTraffic?.(bestTrafficAnalysis);
          
          if (bestRouteResult.positions?.length > 0 && map) {
            const bounds = L.latLngBounds(bestRouteResult.positions);
            map.fitBounds(bounds, { padding: [50, 50], animate: true });
          }
        }
        
        endAnalysis();
      } catch (err) {
        logError("AI Aware Routing failed", err.message);
        endAnalysis();
      }
    })();

    return () => { cancelled = true; };
  }, [from, to, travelMode, sliderValue, liveCameras, map, onRouteFound, onRouteTraffic]);

  return null;
}

// ── TrafficHeatmap: density circles around cameras ──
function TrafficHeatmap({ sliderValue }) {
  const [heatData, setHeatData] = useState([]);

  const fetchHeatmap = useCallback(async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "/api";
      const res = await fetch(`${apiUrl}/predict/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ district: "Quận 7" }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data?.predictions) setHeatData(data.predictions);
    } catch (err) {
      console.error("Heatmap fetch failed", err);
    }
  }, []);

  useEffect(() => {
    fetchHeatmap();
    const interval = setInterval(fetchHeatmap, 120_000); // refresh every 2 min
    return () => clearInterval(interval);
  }, [fetchHeatmap]);

  const simulatedData = useMemo(() => simulateFutureTraffic(heatData, sliderValue), [heatData, sliderValue]);

  return simulatedData.map((item) => {
    const colors = DENSITY_COLORS[item.prediction.density_level] || DENSITY_COLORS.low;
    return (
      <CircleMarker
        key={`heat-${item.camera_id}`}
        center={[item.lat, item.lng]}
        radius={18}
        pathOptions={{
          fillColor: colors.fill,
          fillOpacity: 0.35,
          color: colors.stroke,
          weight: 2,
          opacity: 0.7,
        }}
      >
        <Tooltip direction="top" offset={[0, -10]} opacity={0.9}>
          <div style={{ fontSize: 12, lineHeight: 1.4 }}>
            <strong>{item.camera_name}</strong>
            <br />
            {item.prediction.total_count} xe (
            {item.prediction.car_count} ô tô,{" "}
            {item.prediction.motorbike_count} xe máy)
          </div>
        </Tooltip>
      </CircleMarker>
    );
  });
}

// ── Main TrafficMap component ──
const TrafficMap = React.memo(function TrafficMap({
  routeSegments,
  userLocation,
  destLocation,
  onSetOrigin,
  onSetDestination,
  onRouteFound,
  onRouteTraffic,
  travelMode,
  sliderValue,
}) {
  const [liveCameras, setLiveCameras] = React.useState([]);
  const [droppedPin, setDroppedPin] = React.useState(null);
  const [mapStyle, setMapStyle] = React.useState(MAP_STYLES.voyager);
  const { logRequest, logResponse, logError, logInfo, startAnalysis, endAnalysis } = useDebug();
  const mapRef = React.useRef(null);
  const cameraRefs = React.useRef({});

  // Listen for openCameraPopup events from Dashboard
  React.useEffect(() => {
    const handleOpenPopup = (e) => {
      const cam = e.detail;
      if (!cam || !mapRef.current) return;
      const map = mapRef.current;
      if (cam.lat && cam.lng) {
        map.setView([cam.lat, cam.lng], 17, { animate: true });
      }
      const marker = cameraRefs.current[cam.id];
      if (marker) {
        setTimeout(() => marker.openPopup(), 300);
      }
    };
    window.addEventListener("openCameraPopup", handleOpenPopup);
    return () => window.removeEventListener("openCameraPopup", handleOpenPopup);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    const fetchCameras = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || "/api";
        logRequest("GET", "/cameras");
        const res = await fetch(`${apiUrl}/cameras`);
        const data = await res.json();
        if (!cancelled) {
          logResponse("/cameras", data, res.status);
          if (data?.cameras) {
            setLiveCameras(data.cameras);
            logInfo(`Loaded ${data.cameras.length} cameras`);
          }
        }
      } catch (err) {
        logError("Failed to load cameras", err.message);
      }
    };
    fetchCameras();
    return () => {
      cancelled = true;
    };
  }, []);



  // Handle long press → drop pin
  const handleLongPress = useCallback(
    (latlng) => {
      setDroppedPin([latlng.lat, latlng.lng]);
    },
    [],
  );

  // Pin action handlers
  const handlePinOrigin = useCallback(
    (position, address) => {
      setDroppedPin(null);
      onSetOrigin?.(position, address);
    },
    [onSetOrigin],
  );

  const handlePinDestination = useCallback(
    (position, address) => {
      setDroppedPin(null);
      onSetDestination?.(position, address);
    },
    [onSetDestination],
  );

  const renderedMarkers = useMemo(
    () =>
      liveCameras.map((cam) => (
        <Marker
          key={cam.id}
          position={[cam.lat, cam.lng]}
          icon={CAMERA_ICON}
          eventHandlers={{
            click: (e) => {
              e.target.openPopup();
            },
          }}
          ref={(leafletMarker) => {
            if (leafletMarker) cameraRefs.current[cam.id] = leafletMarker;
          }}
        >
          <Popup maxWidth={280} minWidth={200} closeButton={true}>
              <CameraPopup camera={cam} />
          </Popup>
        </Marker>
      )),
    [liveCameras],
  );

  // Memoize polylines to avoid re-creating on every render
  const routePolylines = useMemo(
    () =>
      routeSegments?.map((segment, idx) => (
        <Polyline
          key={`${idx}-${segment.color}`}
          positions={segment.positions}
          pathOptions={{
            color: segment.color,
            weight: segment.weight || 6,
            opacity: segment.opacity || 0.85,
            lineCap: "round",
            lineJoin: "round",
          }}
        />
      )),
    [routeSegments],
  );

  return (
    <MapContainer
      ref={mapRef}
      center={MAP_CENTER}
      zoom={MAP_ZOOM}
      zoomControl={false}
      style={{ width: "100%", height: "100%" }}
      id="traffic-map"
    >
      <ZoomControl position="bottomright" />
      <MapController userLocation={userLocation} />
      <LongPressHandler onLongPress={handleLongPress} />
      <MapStyleSwitcher mapStyle={mapStyle} onChange={setMapStyle} />

      <TileLayer
        key={`base-${mapStyle.id}`}
        url={mapStyle.url}
        maxZoom={mapStyle.maxZoom}
        attribution={mapStyle.attribution}
        subdomains={mapStyle.subdomains || "abc"}
      />
      {mapStyle.labelOverlay && (
        <TileLayer
          key={`labels-${mapStyle.id}`}
          url={mapStyle.labelOverlay}
          subdomains="abcd"
          maxZoom={20}
          pane="overlayPane"
        />
      )}

      {/* Traffic Heatmap Layer */}
      {/* <TrafficHeatmap sliderValue={sliderValue} /> */}

      {/* Dropped Pin from long-press */}
      {droppedPin && (
        <DroppedPin
          position={droppedPin}
          onSetOrigin={handlePinOrigin}
          onSetDestination={handlePinDestination}
          onClose={() => setDroppedPin(null)}
        />
      )}

      {userLocation && (
        <Marker position={userLocation} icon={USER_ICON} zIndexOffset={1000} />
      )}

      {destLocation && (
        <Marker
          position={destLocation}
          icon={DEST_ICON}
          zIndexOffset={1000}
        />
      )}

      {routePolylines}

      {userLocation && destLocation && (
        <AIAwareRouting
          from={userLocation}
          to={destLocation}
          liveCameras={liveCameras}
          sliderValue={sliderValue}
          travelMode={travelMode}
          onRouteFound={onRouteFound}
          onRouteTraffic={onRouteTraffic}
        />
      )}
      
      {/* Direct markers without clustering */}
      {renderedMarkers}
    </MapContainer>
  );
});

export default TrafficMap;
