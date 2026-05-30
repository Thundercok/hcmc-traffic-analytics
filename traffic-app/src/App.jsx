import React, { useState, useCallback, useMemo, useEffect } from "react";
import {
  LuLocateFixed,
  LuX,
  LuCornerUpLeft,
  LuCornerUpRight,
  LuUndo2,
  LuMoveUp,
  LuRuler,
} from "react-icons/lu";
import ControlPanel from "./components/ControlPanel";
import TrafficMap from "./components/TrafficMap";
import DebugPage from "./pages/DebugPage";
import DashboardPage from "./pages/DashboardPage";
import "./index.css";

// Navigation UI Overlay (Mô phỏng Giao diện Lái xe)
const NavigationOverlay = React.memo(function NavigationOverlay({
  steps,
  eta,
  distance,
  routeTraffic,
  onExit,
}) {
  const currentStep =
    steps && steps.length > 0
      ? steps[0]
      : { instruction: "Đi thẳng đến đích", distance: distance };

  const getIcon = (text) => {
    const t = text.toLowerCase();
    if (t.includes("trái") || t.includes("left")) return <LuCornerUpLeft size={48} />;
    if (t.includes("phải") || t.includes("right")) return <LuCornerUpRight size={48} />;
    if (t.includes("quay đầu") || t.includes("u-turn")) return <LuUndo2 size={48} />;
    return <LuMoveUp size={48} />;
  };

  return (
    <div className="navigation-overlay">
      <div className="nav-header">
        <span className="nav-icon">{getIcon(currentStep.instruction)}</span>
        <div>
          <div className="nav-main">{currentStep.instruction}</div>
          <div className="nav-sub">
            <LuRuler size={16} />
            {currentStep.distance}
          </div>
        </div>
      </div>

      <div className="nav-footer">
        <div>
          <div className="eta">{eta}</div>
          <div className="meta" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {distance}
            {routeTraffic && routeTraffic.camerasAnalyzed > 0 && (
              <span style={{ 
                color: routeTraffic.congestionPoints > 0 ? '#ef4444' : '#10b981', 
                fontWeight: 600,
                fontSize: 13
              }}>
                • {routeTraffic.congestionPoints > 0 ? `${routeTraffic.congestionPoints} điểm kẹt xe` : 'Đường thông thoáng'}
              </span>
            )}
          </div>
        </div>
        <button className="nav-exit-btn" onClick={onExit}>
          <LuX size={18} />
          Thoát
        </button>
      </div>
    </div>
  );
});

export default function App() {
  // Client-side routing
  const [page, setPage] = useState(window.location.pathname === "/dashboard" ? "dashboard" : "main");

  useEffect(() => {
    const handlePopState = () => {
      setPage(window.location.pathname === "/dashboard" ? "dashboard" : "main");
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigateTo = (path) => {
    window.history.pushState({}, "", path);
    setPage(path === "/dashboard" ? "dashboard" : "main");
  };

  // Render Dashboard Page
  if (page === "dashboard") {
    return (
      <DashboardPage
        onBack={() => navigateTo("/")}
        onCameraClick={(cam) => {
          // Navigate to map and trigger camera popup
          navigateTo("/");
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent("openCameraPopup", { detail: cam }));
          }, 100);
        }}
      />
    );
  }

  // Main App
  const [sliderValue, setSliderValue] = useState(0);
  const [originObj, setOriginObj] = useState(null);
  const [destObj, setDestObj] = useState(null);
  const [originText, setOriginText] = useState("");
  const [isNavigating, setIsNavigating] = useState(false);
  const [travelMode, setTravelMode] = useState("car");

  const [routeData, setRouteData] = useState({
    segments: [],
    eta: "",
    distance: "",
    trafficLevel: "",
    steps: [],
  });

  const [routeTraffic, setRouteTraffic] = useState(null);

  const handleRouteFound = useCallback((route) => {
    if (!route) return;
    setRouteData({
      segments:
        route.segments ||
        (route.positions
          ? [{ color: "var(--secondary)", positions: route.positions }]
          : []),
      eta: route.eta || "",
      distance: route.distance || "",
      trafficLevel: route.trafficLevel || "low",
      steps: route.steps || [],
    });
    setRouteTraffic(null);
  }, []);

  const handleRouteTraffic = useCallback((traffic) => {
    setRouteTraffic(traffic);
    if (traffic?.segments) {
      setRouteData((prev) => ({
        ...prev,
        segments: traffic.segments,
        trafficLevel: traffic.level || prev.trafficLevel,
      }));
    }
  }, []);

  const handleFloatingGPSClick = useCallback(() => {
    if (!navigator.geolocation) {
      alert("Trình duyệt không hỗ trợ định vị GPS.");
      return;
    }
    setOriginText("Đang lấy vị trí...");
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        try {
          const apiUrl = import.meta.env.VITE_API_URL || "/api";
          const res = await fetch(
            `${apiUrl}/geocode/reverse?lat=${latitude}&lon=${longitude}`,
          );
          const data = await res.json();
          const address = data.display_name.split(",").slice(0, 3).join(",");
          setOriginText(address);
          setOriginObj({ text: address, lat: latitude, lon: longitude });
        } catch (err) {
          console.error("Lỗi lấy vị trí", err);
          setOriginText(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
          setOriginObj({
            text: "Vị trí hiện tại",
            lat: latitude,
            lon: longitude,
          });
        }
      },
      () => {
        alert("Vui lòng cấp quyền truy cập vị trí trong trình duyệt.");
        setOriginText("");
      },
    );
  }, []);

  const handleSetOrigin = useCallback(
    (position, address) => {
      if (isNavigating) return;
      setOriginText(address);
      setOriginObj({ text: address, lat: position[0], lon: position[1] });
    },
    [isNavigating],
  );

  const handleSetDestination = useCallback(
    (position, address) => {
      if (isNavigating) return;
      setDestObj({ text: address, lat: position[0], lon: position[1] });
    },
    [isNavigating],
  );

  const handleStartNavigation = useCallback(
    () => setIsNavigating(true),
    [],
  );
  const handleExitNavigation = useCallback(
    () => setIsNavigating(false),
    [],
  );

  const userLocation = useMemo(
    () => (originObj ? [originObj.lat, originObj.lon] : null),
    [originObj],
  );
  const destLocation = useMemo(
    () => (destObj ? [destObj.lat, destObj.lon] : null),
    [destObj],
  );
  const destText = destObj ? destObj.text : "";

  const handleSwapLocations = useCallback(() => {
    const tempOrigin = originObj;
    const tempDest = destObj;
    setOriginObj(tempDest);
    setDestObj(tempOrigin);
    setOriginText(tempDest ? tempDest.text : "");
  }, [originObj, destObj]);

  return (
    <div className="app-root">
      <TrafficMap
        routeSegments={routeData.segments}
        userLocation={userLocation}
        destLocation={destLocation}
        onSetOrigin={handleSetOrigin}
        onSetDestination={handleSetDestination}
        onRouteFound={handleRouteFound}
        onRouteTraffic={handleRouteTraffic}
        travelMode={travelMode}
        sliderValue={sliderValue}
      />

      {!isNavigating && (
        <>
          <ControlPanel
            originText={originText}
            setOriginText={setOriginText}
            destText={destText}
            onOriginSelect={setOriginObj}
            onDestinationSelect={setDestObj}
            onSwapLocations={handleSwapLocations}
            sliderValue={sliderValue}
            onSliderChange={setSliderValue}
            eta={routeData.eta}
            distance={routeData.distance}
            trafficLevel={routeData.trafficLevel}
            navigationSteps={routeData.steps}
            onStartNavigation={handleStartNavigation}
            travelMode={travelMode}
            onTravelModeChange={setTravelMode}
            routeTraffic={routeTraffic}
          />

          <button
            onClick={handleFloatingGPSClick}
            className="floating-gps-button"
            title="Đến vị trí hiện tại"
          >
            <LuLocateFixed size={20} />
          </button>

        </>
      )}

      {isNavigating && (
        <NavigationOverlay
          steps={routeData.steps}
          eta={routeData.eta}
          distance={routeData.distance}
          routeTraffic={routeTraffic}
          onExit={handleExitNavigation}
        />
      )}
    </div>
  );
}
