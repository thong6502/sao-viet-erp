// Radar GPS 2D của tab Chấm công của tôi (tách từ pages/ChamCongPage.tsx).
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
  Target,
} from "lucide-react";

// --- 2D Visual Radar Map Component for GPS Check-in --------------------------

export function GpsRadarMap2D({
  nearestName,
  radiusM,
  distanceM,
  metersOut,
  withinRange,
  locating,
  onRefresh,
}: {
  nearestName: string | null;
  radiusM: number;
  distanceM: number | null;
  metersOut: number | null;
  withinRange: boolean;
  locating: boolean;
  onRefresh: () => void;
}) {
  const cx = 200;
  const cy = 90;
  const radiusPx = 55; // Visual circle radius for 150m geofence

  let userX = cx;
  let userY = cy;

  if (distanceM != null && radiusM > 0) {
    const distRatio = distanceM / radiusM;
    let pxDist = 0;
    if (withinRange) {
      pxDist = Math.min(radiusPx - 10, distRatio * (radiusPx - 12));
      if (pxDist < 12 && distanceM > 2) pxDist = 18;
    } else {
      pxDist = Math.min(135, radiusPx + 22 + Math.min(45, (distRatio - 1) * 20));
    }

    const angleRad = (-35 * Math.PI) / 180;
    userX = cx + pxDist * Math.cos(angleRad);
    userY = cy + pxDist * Math.sin(angleRad);
  }

  return (
    <div className="cc-radar-map-2d-card">
      <div className="cc-radar-map-header">
        <div className="cc-radar-map-title-group">
          <div className="cc-radar-map-title">
            <Target size={16} style={{ color: "var(--rust)" }} />
            <span>Bản đồ Radar GPS định vị</span>
          </div>
          <div className="cc-radar-map-sub">
            Phạm vi chấm công <b>{radiusM}m</b> quanh {nearestName ?? "nhà máy"}
          </div>
        </div>
        <button
          type="button"
          className="cc-geo-status-refresh"
          onClick={onRefresh}
          disabled={locating}
          title="Cập nhật tọa độ GPS"
        >
          <RefreshCw size={14} className={locating ? "cc-animate-spin" : ""} />
        </button>
      </div>

      {/* 2D Tactical HUD Radar Grid Canvas SVG */}
      <div className="cc-radar-grid-container">
        <svg viewBox="0 0 400 180" className="cc-radar-svg">
          <defs>
            <pattern
              id="radar-grid-pattern"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 20 0 L 0 0 0 20"
                fill="none"
                stroke="rgba(71, 85, 105, 0.25)"
                strokeWidth="0.8"
              />
            </pattern>
            <radialGradient id="geofence-bg-gradient">
              <stop offset="0%" stopColor={withinRange ? "rgba(47, 93, 58, 0.28)" : "rgba(138, 31, 31, 0.22)"} />
              <stop offset="100%" stopColor={withinRange ? "rgba(47, 93, 58, 0.02)" : "rgba(138, 31, 31, 0.02)"} />
            </radialGradient>
          </defs>

          {/* Dark Tactical Grid Background */}
          <rect width="400" height="180" fill="#0b1329" />
          <rect width="400" height="180" fill="url(#radar-grid-pattern)" />

          {/* HUD Corner Tactical Brackets */}
          <path d="M 8 16 L 8 8 L 16 8" fill="none" stroke="rgba(148, 163, 184, 0.4)" strokeWidth="1.5" />
          <path d="M 392 16 L 392 8 L 384 8" fill="none" stroke="rgba(148, 163, 184, 0.4)" strokeWidth="1.5" />
          <path d="M 8 164 L 8 172 L 16 172" fill="none" stroke="rgba(148, 163, 184, 0.4)" strokeWidth="1.5" />
          <path d="M 392 164 L 392 172 L 384 172" fill="none" stroke="rgba(148, 163, 184, 0.4)" strokeWidth="1.5" />

          {/* HUD Top Live Status Bar */}
          <text x="14" y="18" fontSize="8" fontWeight="bold" fill="rgba(148, 163, 184, 0.65)" letterSpacing="0.08em" style={{ fontFamily: "var(--ff-num)" }}>
            RADAR GPS // THEO DÕI TRỰC TIẾP
          </text>
          <text x="386" y="18" textAnchor="end" fontSize="8" fontWeight="bold" fill={withinRange ? "#4ade80" : "#f87171"} letterSpacing="0.08em" style={{ fontFamily: "var(--ff-num)" }}>
            ● VÙNG CHẤM CÔNG: {withinRange ? "ĐẠT" : "NGOÀI VÙNG"}
          </text>

          {/* Expanding Radial Wave Ripples from Center */}
          <g>
            <circle cx={cx} cy={cy} r="0" fill="none" stroke={withinRange ? "#4ade80" : "#f87171"} strokeWidth="1.8">
              <animate attributeName="r" from="0" to={radiusPx * 1.35} dur="3s" repeatCount="indefinite" begin="0s" />
              <animate attributeName="opacity" values="0.9;0.4;0" dur="3s" repeatCount="indefinite" begin="0s" />
            </circle>
            <circle cx={cx} cy={cy} r="0" fill="none" stroke={withinRange ? "#4ade80" : "#f87171"} strokeWidth="1.8">
              <animate attributeName="r" from="0" to={radiusPx * 1.35} dur="3s" repeatCount="indefinite" begin="1s" />
              <animate attributeName="opacity" values="0.9;0.4;0" dur="3s" repeatCount="indefinite" begin="1s" />
            </circle>
            <circle cx={cx} cy={cy} r="0" fill="none" stroke={withinRange ? "#4ade80" : "#f87171"} strokeWidth="1.8">
              <animate attributeName="r" from="0" to={radiusPx * 1.35} dur="3s" repeatCount="indefinite" begin="2s" />
              <animate attributeName="opacity" values="0.9;0.4;0" dur="3s" repeatCount="indefinite" begin="2s" />
            </circle>
          </g>

          {/* Tactical 360 Rotating Sweep Line & Sector Fade */}
          <g>
            <path
              d={`M ${cx} ${cy} L ${cx} ${cy - radiusPx * 1.35} A ${radiusPx * 1.35} ${radiusPx * 1.35} 0 0 1 ${cx + radiusPx * 0.95} ${cy - radiusPx * 0.95} Z`}
              fill={withinRange ? "rgba(74, 222, 128, 0.18)" : "rgba(248, 113, 113, 0.18)"}
            />
            <line
              x1={cx}
              y1={cy}
              x2={cx}
              y2={cy - radiusPx * 1.35}
              stroke={withinRange ? "#4ade80" : "#f87171"}
              strokeWidth="2.2"
              strokeLinecap="round"
            />
            <animateTransform
              attributeName="transform"
              type="rotate"
              from={`0 ${cx} ${cy}`}
              to={`360 ${cx} ${cy}`}
              dur="3.5s"
              repeatCount="indefinite"
            />
          </g>

          {/* Concentric HUD Inner Range Rings */}
          <circle cx={cx} cy={cy} r={radiusPx * 0.33} fill="none" stroke="rgba(100, 116, 139, 0.3)" strokeWidth="0.8" strokeDasharray="2 2" />
          <circle cx={cx} cy={cy} r={radiusPx * 0.66} fill="none" stroke="rgba(100, 116, 139, 0.3)" strokeWidth="0.8" strokeDasharray="2 2" />

          {/* Geofence Translucent Circle Area */}
          <circle
            cx={cx}
            cy={cy}
            r={radiusPx}
            fill="url(#geofence-bg-gradient)"
            stroke={withinRange ? "var(--moss)" : "var(--signal)"}
            strokeWidth="1.8"
            strokeDasharray="5 3"
          />

          {/* Compass Cardinal Points (N, S, E, W) */}
          <text x={cx} y={cy - radiusPx - 4} textAnchor="middle" fontSize="8" fontWeight="bold" fill="rgba(148, 163, 184, 0.7)" style={{ fontFamily: "var(--ff-num)" }}>N</text>
          <text x={cx} y={cy + radiusPx + 11} textAnchor="middle" fontSize="8" fontWeight="bold" fill="rgba(148, 163, 184, 0.7)" style={{ fontFamily: "var(--ff-num)" }}>S</text>
          <text x={cx - radiusPx - 8} y={cy + 3} textAnchor="middle" fontSize="8" fontWeight="bold" fill="rgba(148, 163, 184, 0.7)" style={{ fontFamily: "var(--ff-num)" }}>W</text>
          <text x={cx + radiusPx + 8} y={cy + 3} textAnchor="middle" fontSize="8" fontWeight="bold" fill="rgba(148, 163, 184, 0.7)" style={{ fontFamily: "var(--ff-num)" }}>E</text>

          {/* Crosshair Axes Lines */}
          <line x1={cx - radiusPx - 15} y1={cy} x2={cx + radiusPx + 15} y2={cy} stroke="rgba(148, 163, 184, 0.2)" strokeWidth="1" />
          <line x1={cx} y1={cy - radiusPx - 15} x2={cx} y2={cy + radiusPx + 15} stroke="rgba(148, 163, 184, 0.2)" strokeWidth="1" />

          {/* Center Point (Factory / Workplace Center 0m) */}
          <circle cx={cx} cy={cy} r="6" fill="#ffffff" />
          <circle cx={cx} cy={cy} r="3.5" fill="#0f172a" />
          <circle cx={cx} cy={cy} r="1.5" fill="var(--rust)" />

          <g transform={`translate(${cx}, ${cy + 28})`}>
            <rect
              x="-54"
              y="-7.5"
              width="108"
              height="14"
              rx="3.5"
              fill="rgba(11, 19, 41, 0.85)"
              stroke="rgba(148, 163, 184, 0.35)"
              strokeWidth="0.6"
            />
            <text
              x="0"
              y="2.5"
              textAnchor="middle"
              fontSize="8.5"
              fontWeight="600"
              fill="#e2e8f0"
              letterSpacing="0.03em"
            >
              Tâm ({nearestName ? (nearestName.length > 13 ? nearestName.slice(0, 13) + "…" : nearestName) : "Nhà máy"})
            </text>
          </g>

          {/* Connecting Line from Center to User */}
          {distanceM != null && (
            <line
              x1={cx}
              y1={cy}
              x2={userX}
              y2={userY}
              stroke={withinRange ? "var(--moss)" : "var(--signal)"}
              strokeWidth="1.4"
              strokeDasharray={withinRange ? "none" : "3 3"}
            />
          )}

          {/* User GPS Point Marker */}
          {distanceM != null && (
            <g>
              <circle
                cx={userX}
                cy={userY}
                r="14"
                fill={withinRange ? "rgba(47, 93, 58, 0.2)" : "rgba(138, 31, 31, 0.2)"}
                className="cc-radar-user-ping"
              />
              <circle
                cx={userX}
                cy={userY}
                r="5"
                fill={withinRange ? "var(--moss)" : "var(--signal)"}
                stroke="#ffffff"
                strokeWidth="1.8"
              />

              <g transform={`translate(${userX}, ${userY - 16})`}>
                <rect
                  x="-50"
                  y="-7.5"
                  width="100"
                  height="14"
                  rx="3.5"
                  fill={withinRange ? "rgba(22, 60, 32, 0.88)" : "rgba(80, 20, 20, 0.88)"}
                  stroke={withinRange ? "rgba(74, 222, 128, 0.65)" : "rgba(248, 113, 113, 0.65)"}
                  strokeWidth="0.6"
                />
                <text
                  x="0"
                  y="2.5"
                  textAnchor="middle"
                  fontSize="8.5"
                  fontWeight="600"
                  fill="#ffffff"
                  style={{ fontFamily: "var(--ff-num)" }}
                  letterSpacing="0.03em"
                >
                  {withinRange
                    ? `Vị trí bạn (${Math.round(distanceM)}m)`
                    : `Cách ${metersOut != null ? (metersOut > 1000 ? `${(metersOut / 1000).toFixed(1)}km` : `${Math.round(metersOut)}m`) : `${Math.round(distanceM)}m`}`}
                </text>
              </g>
            </g>
          )}
        </svg>
      </div>

      {/* Location Metrics Strip Below 2D Canvas */}
      <div className="cc-radar-map-metrics-strip">
        <div className="cc-radar-metric-chip">
          <span className="cc-radar-metric-label">Bán kính hợp lệ</span>
          <span className="cc-radar-metric-val">{radiusM} m</span>
        </div>
        <div className="cc-radar-metric-chip">
          <span className="cc-radar-metric-label">Khoảng cách hiện tại</span>
          <span className="cc-radar-metric-val">
            {distanceM != null
              ? distanceM > 1000
                ? `${(distanceM / 1000).toFixed(1)} km`
                : `${Math.round(distanceM)} m`
              : "—"}
          </span>
        </div>
        <div className="cc-radar-metric-chip">
          <span className="cc-radar-metric-label">Trạng thái vị trí</span>
          <span className={`cc-radar-metric-val ${withinRange ? "is-safe" : "is-warn"}`}>
            {withinRange ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <CheckCircle2 size={13} /> Trong phạm vi
              </span>
            ) : metersOut != null ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <AlertCircle size={13} /> Cách {metersOut > 1000 ? `${(metersOut / 1000).toFixed(1)}km` : `${Math.round(metersOut)}m`}
              </span>
            ) : (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <XCircle size={13} /> Ngoài vùng
              </span>
            )}
          </span>
        </div>
      </div>

      {/* Legend Footer */}
      <div className="cc-radar-map-legend">
        <div className="cc-radar-legend-item">
          <span className="cc-radar-dot cc-radar-dot--center" />
          <span>Tâm nhà máy (0m)</span>
        </div>
        <div className="cc-radar-legend-item">
          <span className="cc-radar-dot cc-radar-dot--fence" />
          <span>Vùng Geofence ({radiusM}m)</span>
        </div>
        <div className="cc-radar-legend-item">
          <span
            className={`cc-radar-dot ${withinRange ? "cc-radar-dot--in" : "cc-radar-dot--out"}`}
          />
          <span>
            {withinRange
              ? "Vị trí bạn (Hợp lệ)"
              : `Vị trí bạn (Cách ${metersOut != null ? (metersOut > 1000 ? `${(metersOut / 1000).toFixed(1)}km` : `${Math.round(metersOut)}m`) : "ngoài vùng"})`}
          </span>
        </div>
      </div>
    </div>
  );
}
