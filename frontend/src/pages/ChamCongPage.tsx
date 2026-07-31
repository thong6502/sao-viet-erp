// Chấm công GPS (module `nhan_su`). 3 tab:
//   • Chấm công của tôi — lấy GPS trình duyệt, chấm VÀO/RA nếu trong bán kính điểm gần nhất.
//   • Điểm chấm công (HR) — khai toạ độ + bán kính; "Lấy vị trí hiện tại" để điền nhanh.
//   • Bảng chấm công (HR) — toàn bộ log.
// Server là cổng geofence thật (Haversine); ngoài phạm vi bị chặn cứng.
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  type AttendanceLog,
  type AdjustQuota,
  type AdjustRequest,
  type AttendancePreview,
  type AttendanceStatus,
  type CheckResult,
  type DayDetail,
  type EmployeeShiftAssignment,
  type LateEarlyRequest,
  type LateEarlyRoster,
  type LeaveQuota,
  type LeaveType,
  type MyShift,
  type TodayKpi,
  type Timesheet,
  type TimesheetRow,
  type AttendancePeriod,
  type WorkLocation,
  type WorkLocationInput,
  type ShiftChange,
  type WorkShift,
  type WorkShiftInput,
  type WorkCalendarConfig,
  type WorkCalendarConfigInput,
  type SpecialDay,
  type SpecialDayInput,
  type SpecialDaysOut,
  type CalendarMonth,
  type CalendarDayCell,
  type ShiftPlanMonth,
  type ShiftPlanDay,
  type ShiftPlanRow,
  type ShiftPlanPatchItem,
} from "../api/client";
import type { NavigateFn } from "../components/AppShell";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import {
  UserCheck,
  CalendarDays,
  MapPin,
  Clock,
  Clock3,
  Calendar,
  ClipboardList,
  Table,
  FileEdit,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Trash2,
  Edit3,
  Coffee,
  Moon,
  Sun,
  Lock,
  Unlock,
  Plus,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Info,
  LogIn,
  LogOut,
  Search,
  Save,
  Undo2,
  Eraser,
  Users,
  Repeat,
  Target,
  Navigation,
  ExternalLink,
} from "lucide-react";
import { MixDonut } from "../components/charts";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import "./nhan-su.css";
import "./cham-cong.css";

type Tab =
  | "me"
  | "my-timesheet"
  | "di-muon"
  | "locations"
  | "khai-ca"
  | "lich-le"
  | "logs"
  | "timesheet"
  | "yeu-cau";

const FAULT_OPTIONS: { value: string; label: string }[] = [
  { value: "nv_quen", label: "NV quên chấm" },
  { value: "may_hong", label: "Máy hỏng / mất điện" },
  { value: "duyet", label: "Được duyệt (công tác/họp)" },
  { value: "khac", label: "Khác" },
];

const TIME_HOURS = Array.from({ length: 24 }, (_, index) =>
  String(index).padStart(2, "0"),
);
const TIME_MINUTES = Array.from({ length: 60 }, (_, index) =>
  String(index).padStart(2, "0"),
);
const FAULT_LABEL: Record<string, string> = Object.fromEntries(
  FAULT_OPTIONS.map((o) => [o.value, o.label]),
);

function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  // Server gửi UTC. Nếu chuỗi thiếu nhãn múi giờ (SQLite trả naive) thì coi là UTC,
  // rồi luôn hiển thị theo giờ Việt Nam — không lệ thuộc múi giờ máy người xem.
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s);
  const d = new Date(hasTz ? s : `${s}Z`);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

/** Hôm nay dạng YYYY-MM-DD (giờ máy) — so chuỗi ISO là đủ để biết mốc ở tương lai. */
function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtYmd(value: string | null | undefined): string {
  if (!value) return "Đến nay";
  const [y, m, d] = value.split("-");
  return y && m && d ? `${d}/${m}/${y}` : value;
}

function normalizeTime24(value: string): string | null {
  const raw = value.trim();
  let hour: number;
  let minute: number;

  if (/^\d{1,2}$/.test(raw)) {
    hour = Number(raw);
    minute = 0;
  } else if (/^\d{3}$/.test(raw)) {
    hour = Number(raw.slice(0, 1));
    minute = Number(raw.slice(1));
  } else if (/^\d{4}$/.test(raw)) {
    hour = Number(raw.slice(0, 2));
    minute = Number(raw.slice(2));
  } else {
    const match = raw.match(/^(\d{1,2}):(\d{1,2})$/);
    if (!match) return null;
    hour = Number(match[1]);
    minute = Number(match[2]);
  }

  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/** "HH:MM:SS" đã trôi kể từ mốc `fromIso` (coi chuỗi thiếu nhãn là UTC như fmtDateTime). */
function fmtElapsed(fromIso: string | null | undefined, now: number): string {
  if (!fromIso) return "00:00:00";
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(fromIso);
  const start = new Date(hasTz ? fromIso : `${fromIso}Z`).getTime();
  let s = Math.max(0, Math.floor((now - start) / 1000));
  const h = Math.floor(s / 3600);
  s -= h * 3600;
  const m = Math.floor(s / 60);
  s -= m * 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(h)}:${p(m)}:${p(s)}`;
}

/** Promise wrapper quanh navigator.geolocation. */
function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("Trình duyệt không hỗ trợ định vị GPS."));
      return;
    }
    // Backstop: trên máy bàn Windows (không có GPS, Location service tắt) getCurrentPosition
    // có thể TREO mà không bắn timeout riêng của nó → nút "Đang lấy vị trí…" quay vô hạn.
    // Watchdog tự reject để lời gọi LUÔN kết thúc, UI kịp hiện lỗi + nút thử lại.
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(watchdog);
      fn();
    };
    const timeoutErr = Object.assign(new Error("Lấy vị trí quá lâu."), {
      code: 3,
    });
    const watchdog = setTimeout(() => finish(() => reject(timeoutErr)), 14000);
    navigator.geolocation.getCurrentPosition(
      (pos) => finish(() => resolve(pos)),
      (err) => finish(() => reject(err)),
      {
        // Máy bàn không có chip GPS → định vị mạng (WiFi/IP): nhanh, đỡ treo, đủ cho geofence 150 m.
        // Trong xưởng (indoor) GPS còn kém hơn network → cũng hợp use-case công nhân chấm công.
        enableHighAccuracy: false,
        timeout: 12000,
        maximumAge: 30000, // fix ≤30s được tái dùng → preview→chấm không phải dò lại
      },
    );
  });
}

function geoErrText(e: unknown): string {
  const code = (e as { code?: number } | null)?.code;
  if (code === 1)
    return "Bạn đã từ chối quyền vị trí. Hãy cho phép định vị rồi thử lại.";
  if (code === 2)
    return "Không lấy được vị trí. Kiểm tra Dịch vụ định vị (Location) của Windows đã bật chưa.";
  if (code === 3)
    return "Lấy vị trí quá lâu. Kiểm tra mạng và Dịch vụ định vị của Windows rồi thử lại.";
  if (e instanceof Error) return e.message;
  return "Không lấy được vị trí.";
}

export function ChamCongPage({
  navigate,
  focusEmployeeId,
  onChanged,
  eventTick,
}: {
  navigate?: NavigateFn;
  focusEmployeeId?: number;
  /** Gọi sau mỗi lần tải/thao tác → AppShell refetch badge sidebar + chuông ngay. */
  onChanged?: () => void;
  /** Tăng theo mỗi sự kiện real-time (SSE) → tab phiếu đang mở tự tải lại, khỏi bắt F5. */
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canConfig = can("nhan_su", "update"); // cấu hình điểm/ca
  const canView = can("nhan_su", "read"); // xem toàn xưởng (theo scope)
  const canApproveEl = can("di_muon", "approve"); // duyệt phiếu đi muộn / về sớm
  const [tab, setTab] = useState<Tab>("me");

  // Liên thông từ Hồ sơ NV → mở "Bảng chấm công" lọc đúng NV đó.
  useEffect(() => {
    if (focusEmployeeId && canView) setTab("logs");
  }, [focusEmployeeId, canView]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          <h1 className="ns__title">Chấm công</h1>
          <p className="ns__sub">
            Chấm công theo vị trí GPS · phải ở gần điểm làm việc đã khai
          </p>
        </div>
      </header>

      <nav className="cc-tabs">
        <button
          className={tab === "me" ? "is-active" : ""}
          onClick={() => setTab("me")}
        >
          <UserCheck size={14} /> Chấm công của tôi
        </button>
        <button
          className={tab === "my-timesheet" ? "is-active" : ""}
          onClick={() => setTab("my-timesheet")}
        >
          <CalendarDays size={14} /> Công của tôi
        </button>
        {/* LUÔN hiện: ai vào được màn Chấm công cũng phải xin đi muộn/về sớm cho CHÍNH MÌNH được. */}
        <button
          className={tab === "di-muon" ? "is-active" : ""}
          onClick={() => setTab("di-muon")}
        >
          <Clock3 size={14} /> Đi muộn / về sớm / nghỉ nửa buổi
        </button>
        {canConfig && (
          <button
            className={tab === "locations" ? "is-active" : ""}
            onClick={() => setTab("locations")}
          >
            <MapPin size={14} /> Điểm chấm công
          </button>
        )}
        {canConfig && (
          <button
            className={tab === "khai-ca" ? "is-active" : ""}
            onClick={() => setTab("khai-ca")}
          >
            <Clock size={14} /> Khai ca
          </button>
        )}
        {canConfig && (
          <button
            className={tab === "lich-le" ? "is-active" : ""}
            onClick={() => setTab("lich-le")}
          >
            <Calendar size={14} /> Lịch & Ngày lễ
          </button>
        )}
        {canView && (
          <button
            className={tab === "logs" ? "is-active" : ""}
            onClick={() => setTab("logs")}
          >
            <ClipboardList size={14} /> Bảng chấm công
          </button>
        )}
        {canView && (
          <button
            className={tab === "timesheet" ? "is-active" : ""}
            onClick={() => setTab("timesheet")}
          >
            <Table size={14} /> Bảng công tháng
          </button>
        )}
        {canView && (
          <button
            className={tab === "yeu-cau" ? "is-active" : ""}
            onClick={() => setTab("yeu-cau")}
          >
            <FileEdit size={14} /> Yêu cầu chỉnh công
          </button>
        )}
      </nav>

      {tab === "me" && (
        <MyCheckIn token={token!} canConfig={canConfig} navigate={navigate} />
      )}
      {tab === "my-timesheet" && <MyTimesheetTab token={token!} />}
      {tab === "di-muon" && (
        <LateEarlyTab
          token={token!}
          canApprove={canApproveEl}
          onChanged={onChanged}
          eventTick={eventTick}
        />
      )}
      {tab === "locations" && canConfig && <LocationsTab token={token!} />}
      {tab === "khai-ca" && canConfig && <ShiftsTab token={token!} />}
      {tab === "lich-le" && canConfig && <CalendarTab token={token!} />}
      {tab === "logs" && canView && (
        <LogsTab token={token!} focusEmployeeId={focusEmployeeId} />
      )}
      {tab === "timesheet" && canView && (
        <TimesheetTab token={token!} canAdjust={can("nhan_su", "adjust")} />
      )}
      {tab === "yeu-cau" && canView && (
        <AdjustRequestsTab
          token={token!}
          canAdjust={can("nhan_su", "adjust")}
        />
      )}
    </main>
  );
}

// --- Tab: Chấm công của tôi -------------------------------------------------

// --- 2D Visual Radar Map Component for GPS Check-in --------------------------

function GpsRadarMap2D({
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
            <MapPin size={15} style={{ color: "var(--rust)" }} />
            <span>Chấm công GPS hôm nay</span>
          </div>
          <div className="cc-radar-map-sub">
            Định vị GPS trên điện thoại · bán kính <b>{radiusM}m</b> quanh {nearestName ?? "nhà máy"}
          </div>
        </div>
        <button
          type="button"
          className="cc-geo-status-refresh"
          onClick={onRefresh}
          disabled={locating}
          title="Cập nhật vị trí GPS"
        >
          <RefreshCw size={14} className={locating ? "cc-animate-spin" : ""} />
        </button>
      </div>

      {/* 2D Grid Canvas SVG */}
      <div className="cc-radar-grid-container">
        <svg viewBox="0 0 400 180" className="cc-radar-svg">
          <defs>
            <pattern
              id="radar-grid-pattern"
              width="24"
              height="24"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 24 0 L 0 0 0 24"
                fill="none"
                stroke="rgba(215, 205, 190, 0.45)"
                strokeWidth="0.8"
              />
            </pattern>
          </defs>
          <rect width="400" height="180" fill="url(#radar-grid-pattern)" rx="8" />

          {/* Geofence Translucent Circle Area */}
          <circle
            cx={cx}
            cy={cy}
            r={radiusPx}
            fill={withinRange ? "rgba(34, 197, 94, 0.12)" : "rgba(239, 68, 68, 0.08)"}
            stroke={withinRange ? "#16a34a" : "#dc2626"}
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />

          {/* Center Point (Factory / Workplace Center 0m) */}
          <circle cx={cx} cy={cy} r="6" fill="#0f172a" />
          <circle cx={cx} cy={cy} r="2.5" fill="#ffffff" />
          <text
            x={cx}
            y={cy + 18}
            textAnchor="middle"
            fontSize="10"
            fontWeight="bold"
            fill="#334155"
          >
            Tâm ({nearestName ? nearestName.slice(0, 18) : "Nhà máy"})
          </text>

          {/* Connecting Line from Center to User if Outside */}
          {!withinRange && distanceM != null && (
            <line
              x1={cx}
              y1={cy}
              x2={userX}
              y2={userY}
              stroke="#ef4444"
              strokeWidth="1.2"
              strokeDasharray="3 3"
            />
          )}

          {/* User GPS Point Marker */}
          {distanceM != null && (
            <g>
              <circle
                cx={userX}
                cy={userY}
                r="10"
                fill={withinRange ? "rgba(34, 197, 94, 0.25)" : "rgba(239, 68, 68, 0.25)"}
              />
              <circle
                cx={userX}
                cy={userY}
                r="5"
                fill={withinRange ? "#16a34a" : "#dc2626"}
                stroke="#ffffff"
                strokeWidth="1.5"
              />
              <text
                x={userX}
                y={userY - 10}
                textAnchor="middle"
                fontSize="10"
                fontWeight="bold"
                fill={withinRange ? "#15803d" : "#b91c1c"}
              >
                {withinRange
                  ? `Vị trí bạn (${Math.round(distanceM)}m)`
                  : `Bạn (Cách ${metersOut != null ? (metersOut > 1000 ? `${(metersOut / 1000).toFixed(1)}km` : `${Math.round(metersOut)}m`) : `${Math.round(distanceM)}m`})`}
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* Legend Footer */}
      <div className="cc-radar-map-legend">
        <div className="cc-radar-legend-item">
          <span className="cc-radar-dot cc-radar-dot--center" />
          <span>Tâm (0m)</span>
        </div>
        <div className="cc-radar-legend-item">
          <span className="cc-radar-dot cc-radar-dot--fence" />
          <span>Geofence ({radiusM}m)</span>
        </div>
        <div className="cc-radar-legend-item">
          <span
            className={`cc-radar-dot ${withinRange ? "cc-radar-dot--in" : "cc-radar-dot--out"}`}
          />
          <span>
            {withinRange
              ? "Vị trí bạn (Trong vùng)"
              : `Vị trí bạn (Còn cách ${metersOut != null ? (metersOut > 1000 ? `${(metersOut / 1000).toFixed(1)}km` : `${Math.round(metersOut)}m`) : "ngoài vùng"})`}
          </span>
        </div>
      </div>
    </div>
  );
}

function MyCheckIn({
  token,
  canConfig,
  navigate,
}: {
  token: string;
  canConfig: boolean;
  navigate?: NavigateFn;
}) {
  const [status, setStatus] = useState<AttendanceStatus | null>(null);
  const [logs, setLogs] = useState<AttendanceLog[]>([]);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [geoErr, setGeoErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<AttendancePreview | null>(null);
  const [locating, setLocating] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [clockTime, setClockTime] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showConfirmOut, setShowConfirmOut] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(() => {
    api.attendance
      .myStatus(token)
      .then(setStatus)
      .catch(() => setStatus(null));
    api.attendance
      .myLogs(token)
      .then((r) => setLogs(r.items))
      .catch(() => setLogs([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  // Clock live update
  useEffect(() => {
    const updateTime = () => {
      const d = new Date();
      setClockTime(
        d.toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }),
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Vòng geofence "sống": lấy GPS + dry-run tới server (không ghi log) để biết trong/ngoài vùng.
  const refreshPreview = useCallback(async () => {
    setLocating(true);
    setGeoErr(null);
    try {
      const pos = await getPosition();
      const p = await api.attendance.preview(
        token,
        pos.coords.latitude,
        pos.coords.longitude,
      );
      if (mounted.current) setPreview(p);
    } catch (e) {
      if (mounted.current) setGeoErr(geoErrText(e));
    } finally {
      if (mounted.current) setLocating(false);
    }
  }, [token]);
  useEffect(() => {
    if (status?.has_employee && status.can_check && status.locations_configured)
      refreshPreview();
  }, [
    status?.has_employee,
    status?.can_check,
    status?.locations_configured,
    refreshPreview,
  ]);

  // Đồng hồ LIVE khi đang trong ca (lần chấm gần nhất là VÀO → next_action = "out").
  useEffect(() => {
    if (status?.next_action !== "out") return;
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [status?.next_action]);

  async function doCheck(bypassConfirm = false) {
    if (!status?.can_check) {
      setGeoErr(status?.check_block_reason ?? "Hiện chưa thể chấm công.");
      return;
    }
    const isOut = status?.next_action === "out";
    if (isOut && !bypassConfirm) {
      setShowConfirmOut(true);
      return;
    }
    setShowConfirmOut(false);
    setChecking(true);
    setResult(null);
    setGeoErr(null);
    try {
      const pos = await getPosition();
      const res = await api.attendance.check(
        token,
        pos.coords.latitude,
        pos.coords.longitude,
      );
      setResult(res);
      load();
      refreshPreview();
    } catch (e) {
      setGeoErr(geoErrText(e));
    } finally {
      setChecking(false);
    }
  }

  async function setPointHere() {
    setChecking(true);
    setResult(null);
    setGeoErr(null);
    try {
      const pos = await getPosition();
      await api.attendance.createLocation(token, {
        name: "Điểm chấm công của tôi",
        latitude: Number(pos.coords.latitude.toFixed(7)),
        longitude: Number(pos.coords.longitude.toFixed(7)),
        radius_m: 150,
        is_active: true,
      });
      const res = await api.attendance.check(
        token,
        pos.coords.latitude,
        pos.coords.longitude,
      );
      setResult(res);
      load();
    } catch (e) {
      setGeoErr(geoErrText(e));
    } finally {
      setChecking(false);
    }
  }

  if (!status) return <p className="ns__empty">Đang tải…</p>;

  if (!status.has_employee) {
    return (
      <div className="banner banner--warn" style={{ marginTop: 12 }}>
        Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong> nên không
        thể tự chấm công. Liên hệ HCNS để nối tài khoản với hồ sơ.
      </div>
    );
  }

  const isIn = status.next_action !== "out";
  // Lượt kế tiếp thuộc phiên TĂNG CA (đã ra ca chính + có phiếu duyệt) → đổi nhãn nút cho rõ.
  const otMode = !!status.ot_mode;
  const actionLabel = isIn
    ? otMode
      ? "CHẤM VÀO TĂNG CA"
      : "CHẤM VÀO"
    : otMode
      ? "CHẤM RA TĂNG CA"
      : "CHẤM RA";
  const outside = preview != null && !preview.within_range;
  const showTimer =
    status.next_action === "out" && status.last_check?.check_type === "in";
  const btnDisabled =
    checking ||
    locating ||
    !status.can_check ||
    !status.locations_configured ||
    outside;

  function getShiftProgress(start: string, end: string, now: number): number {
    try {
      const todayStr = new Date().toISOString().split("T")[0];
      const startMs = new Date(`${todayStr}T${start}:00`).getTime();
      let endMs = new Date(`${todayStr}T${end}:00`).getTime();
      if (endMs < startMs) {
        endMs += 24 * 60 * 60 * 1000;
      }
      const total = endMs - startMs;
      if (total <= 0) return 0;
      const elapsed = now - startMs;
      return Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
    } catch {
      return 0;
    }
  }

  const clockParts = clockTime.split(":");
  const clockH = clockParts[0] || "00";
  const clockM = clockParts[1] || "00";
  const clockS = clockParts[2] || "00";

  return (
    <div className="cc-checkin-hero-wrapper">
      {/* 1. Hero Header Banner */}
      <div className="cc-checkin-hero-header">
        <div className="cc-checkin-user-profile">
          {status.employee_name && (
            <div className="cc-employee-avatar">
              {status.employee_name
                .split(" ")
                .filter(Boolean)
                .map((n) => n[0])
                .slice(-2)
                .join("")
                .toUpperCase()}
            </div>
          )}
          <div className="cc-checkin-user-info">
            <div className="cc-checkin-user-name">
              <h3>{status.employee_name}</h3>
              <span className={`cc-status-dot-pill ${status.next_action === "out" ? "is-working" : "is-off"}`}>
                {status.next_action === "out" ? "🟢 Đang trong ca" : "⚪ Chưa vào ca"}
              </span>
            </div>
            <div className="cc-employee-sub" style={{ textAlign: "left", marginTop: 2 }}>
              {status.last_check
                ? `Lần gần nhất: chấm ${status.last_check.check_type === "in" ? "VÀO" : "RA"} lúc ${fmtDateTime(status.last_check.checked_at)}`
                : "Chưa có lần chấm công nào."}
            </div>
          </div>
        </div>

        {/* Live Clock & Shift Status Banner */}
        <div className="cc-checkin-clock-banner">
          <div className="cc-live-clock cc-live-clock-compact">
            <span>{clockH}</span>
            <span className="cc-clock-colon">:</span>
            <span>{clockM}</span>
            <span className="cc-clock-colon">:</span>
            <span style={{ opacity: 0.85 }}>{clockS}</span>
          </div>

          {status.shift && (
            <div className="cc-shift-tracker-compact">
              <div className="cc-shift-title">
                <Clock size={13} /> Ca {status.shift.name} ({status.shift.start_time} - {status.shift.end_time})
              </div>
              {showTimer && (
                <div style={{ fontSize: 11, color: "var(--ash)" }}>
                  Thời gian làm: <b>{fmtElapsed(status.last_check?.checked_at, nowTick)}</b>
                </div>
              )}
              {showTimer && (
                <div className="cc-shift-progress-bg">
                  <div
                    className="cc-shift-progress-fill"
                    style={{
                      width: `${getShiftProgress(status.shift.start_time, status.shift.end_time, nowTick)}%`,
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 2. Dual-Column Grid Layout (60% Left / 40% Right) */}
      <div className="cc-checkin-grid-layout">
        {/* Left Column: 2D Radar Map Workspace */}
        <div className="cc-checkin-left-col">
          {status.locations_configured ? (
            <GpsRadarMap2D
              nearestName={preview?.nearest_name ?? null}
              radiusM={preview?.radius_m ?? 150}
              distanceM={preview?.distance_m ?? null}
              metersOut={preview?.meters_out ?? null}
              withinRange={!!preview?.within_range}
              locating={locating}
              onRefresh={refreshPreview}
            />
          ) : (
            <div className="cc-radar-map-2d-card" style={{ padding: 40, textAlign: "center" }}>
              <p className="cc-note">Chưa cấu hình điểm chấm công nào. Hãy liên hệ HCNS.</p>
            </div>
          )}
        </div>

        {/* Right Column: Punch Action Center */}
        <div className="cc-checkin-right-col">
          <div className="cc-punch-card">
            <div className="cc-punch-card-header">
              <span className="cc-punch-card-title">Trung tâm Chấm công</span>
              <span className={`cc-type-badge ${preview?.within_range ? "cc-type-badge--paid" : "cc-type-badge--unpaid"}`}>
                {preview?.within_range ? "✓ Trong vùng" : "⊘ Ngoài vùng"}
              </span>
            </div>

            {status.check_block_reason && (
              <div className="banner banner--warn" style={{ width: "100%", marginTop: 10 }}>
                {status.check_block_reason}
              </div>
            )}

            {/* Glow Pulsing Radar Button */}
            <div className="cc-radar-container" style={{ margin: "24px 0" }}>
              {!btnDisabled && (
                <div className={`cc-radar-wave ${isIn ? "cc-radar-wave--in" : "cc-radar-wave--out"}`} />
              )}
              {!btnDisabled && (
                <div className={`cc-radar-wave ${isIn ? "cc-radar-wave--in" : "cc-radar-wave--out"}`} />
              )}
              <button
                className={`cc-radar-btn ${outside ? "cc-radar-btn--locked" : isIn ? "cc-radar-btn--in" : "cc-radar-btn--out"}`}
                onClick={() => doCheck()}
                disabled={btnDisabled}
              >
                <span className="cc-radar-btn-icon">
                  {locating ? (
                    <RefreshCw className="cc-animate-spin" size={24} />
                  ) : !status.can_check || outside ? (
                    <Lock size={24} />
                  ) : (
                    <UserCheck size={24} />
                  )}
                </span>
                <span style={{ fontSize: "14px", marginTop: "2px", fontWeight: "var(--fw-bold)" }}>
                  {checking
                    ? "Đang chấm…"
                    : locating
                    ? "Đang dò GPS…"
                    : !status.can_check
                    ? "CHƯA ĐẾN GIỜ CHẤM"
                    : actionLabel}
                </span>
              </button>
            </div>

            {outside && preview?.meters_out != null && (
              <div className="cc-outside-hint-box">
                <AlertTriangle size={14} style={{ color: "#dc2626", flexShrink: 0 }} />
                <span>
                  Hãy di chuyển lại gần xưởng thêm <b>{preview.meters_out > 1000 ? `${(preview.meters_out / 1000).toFixed(1)}km` : `${Math.round(preview.meters_out)}m`}</b> để mở khóa nút chấm công.
                </span>
              </div>
            )}

            {/* Quick Action Shortcuts Strip */}
            <div className="cc-shortcuts-strip">
              <button className="cc-shortcut-btn" onClick={() => setShowHistory(true)}>
                <ClipboardList size={14} />
                <span>Lịch sử chấm công</span>
              </button>

              {navigate && (
                <button className="cc-shortcut-btn" onClick={() => navigate("nghi-phep")}>
                  <Coffee size={14} />
                  <span>Đăng ký nghỉ phép</span>
                </button>
              )}
            </div>

            {geoErr && (
              <div
                className="banner banner--error"
                style={{ marginTop: 12, width: "100%" }}
              >
                {geoErr}{" "}
                <button
                  className="btn btn--ghost"
                  style={{ marginLeft: 8 }}
                  onClick={refreshPreview}
                  disabled={locating}
                >
                  🔄 Thử lại
                </button>
              </div>
            )}
            {result && (
              <div
                className={`banner ${result.success ? "banner--ok" : "banner--warn"}`}
                style={{ marginTop: 12, width: "100%" }}
              >
                {result.message}
              </div>
            )}

            {canConfig &&
              (!status.locations_configured ||
                (result != null && !result.within_range)) && (
                <div className="cc-setup" style={{ width: "100%", marginTop: 12 }}>
                  <button
                    className="btn btn--ghost cc-setup__btn"
                    onClick={setPointHere}
                    disabled={checking}
                  >
                    📍 Đặt điểm chấm công tại đây
                  </button>
                  <p className="cc-note">
                    Tạo điểm chấm công mới tại tọa độ hiện tại (bán kính 150m) để
                    chấm ngay.
                  </p>
                </div>
              )}
          </div>
        </div>
      </div>

      {showHistory && (
        <MyHistoryModal logs={logs} onClose={() => setShowHistory(false)} />
      )}

      {showConfirmOut && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div
            className="ns-modal__box cc-confirm-box"
            style={{ maxWidth: "420px" }}
          >
            <header className="ns-modal__head">
              <h2
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  margin: 0,
                }}
              >
                {otMode ? "Xác nhận kết thúc tăng ca" : "Xác nhận kết thúc ca"}
              </h2>
              <button
                className="ns-modal__x"
                onClick={() => setShowConfirmOut(false)}
              >
                ×
              </button>
            </header>
            <div
              className="ns-modal__body"
              style={{ textAlign: "center", padding: "28px 20px" }}
            >
              <div className="cc-confirm-icon-wrap">
                <LogOut size={32} />
              </div>
              <p
                style={{
                  fontSize: "16px",
                  fontWeight: "var(--fw-bold)",
                  color: "var(--ink)",
                  margin: "20px 0 8px 0",
                }}
              >
                {otMode ? "Bạn sắp chấm RA TĂNG CA" : "Bạn sắp chấm RA"}
              </p>
              <p
                style={{
                  fontSize: "13px",
                  color: "var(--ash)",
                  lineHeight: "1.5",
                  margin: 0,
                }}
              >
                {otMode
                  ? "Hành động này sẽ ghi nhận giờ kết thúc phiên tăng ca của bạn. Giờ tăng ca được trả theo thực tế bạn chấm ra (trong khung phiếu đã duyệt)."
                  : "Hành động này sẽ ghi nhận giờ kết thúc ca làm việc của bạn. Bạn chắc chắn muốn kết thúc ca chứ?"}
              </p>
            </div>
            <footer
              className="ns-modal__foot"
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
              }}
            >
              <button
                className="btn btn--ghost"
                style={{ flex: 1 }}
                onClick={() => setShowConfirmOut(false)}
              >
                Hủy
              </button>
              <button
                className="btn btn--primary"
                style={{
                  flex: 1,
                  background: "var(--signal)",
                  borderColor: "var(--signal)",
                  color: "#fff",
                }}
                onClick={() => doCheck(true)}
              >
                {otMode ? "Đồng ý (RA TĂNG CA)" : "Đồng ý (RA)"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function MyHistoryModal({
  logs,
  onClose,
}: {
  logs: AttendanceLog[];
  onClose: () => void;
}) {
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box" style={{ maxWidth: "480px" }}>
        <header className="ns-modal__head">
          <h2
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              margin: 0,
            }}
          >
            <ClipboardList size={18} /> Lịch sử chấm công của tôi
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div
          className="ns-modal__body"
          style={{ maxHeight: "400px", overflowY: "auto" }}
        >
          <div className="cc-timeline" style={{ marginTop: 0 }}>
            {logs.map((l) => (
              <div key={l.id} className="cc-timeline-item">
                <div
                  className={`cc-timeline-badge ${l.check_type === "in" ? "cc-timeline-badge--in" : "cc-timeline-badge--out"}`}
                />
                <div className="cc-timeline-content">
                  <div className="cc-timeline-left">
                    <span className="cc-timeline-action">
                      Chấm {l.check_type === "in" ? "VÀO" : "RA"}
                    </span>
                    <span className="cc-timeline-location">
                      <MapPin size={12} />{" "}
                      {l.location_name || "Vị trí không xác định"}
                    </span>
                  </div>
                  <div className="cc-timeline-right">
                    <span className="cc-timeline-time">
                      {fmtDateTime(l.checked_at)}
                    </span>
                    <div className="cc-timeline-distance">
                      {l.distance_m != null
                        ? `Cự ly: ${Math.round(l.distance_m)}m`
                        : "—"}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {logs.length === 0 && (
              <p
                className="ns__empty"
                style={{
                  background: "var(--paper)",
                  padding: "16px",
                  borderRadius: "8px",
                  border: "1px solid var(--rule-soft)",
                }}
              >
                Chưa có dữ liệu lịch sử chấm công.
              </p>
            )}
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Công của tôi (self-service timesheet) -----------------------------

function MyTimesheetTab({ token }: { token: string }) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [data, setData] = useState<Timesheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [reqs, setReqs] = useState<AdjustRequest[]>([]);
  const [quota, setQuota] = useState<AdjustQuota | null>(null);
  const [reqDate, setReqDate] = useState<string | null>(null); // ngày đang xin chỉnh (mở modal)
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    setLoading(true);
    api.attendance
      .myTimesheet(token, year, month)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [token, year, month]);

  const loadReqs = useCallback(() => {
    api.attendance
      .myAdjustRequests(token)
      .then((r) => {
        setReqs(r.items);
        setQuota(r.quota ?? null);
      })
      .catch(() => {
        setReqs([]);
        setQuota(null);
      });
  }, [token]);
  useEffect(() => {
    loadReqs();
  }, [loadReqs]);

  // Hộp thư "ca của tôi vừa bị đổi" — CHỈ tin CHƯA ĐỌC.
  //
  // Mở màn = đánh dấu đã đọc (badge về 0) nhưng khối vẫn HIỆN hết lượt này, để người ta kịp
  // đọc; lần vào sau mới hết. Lấy cả tin đã đọc thì khối bám đầu màn vĩnh viễn — lỗi đã gặp.
  // Dài thì gập lại: 50 thông báo mà đổ hết ra là đẩy bảng công xuống dưới màn hình.
  const [shiftMsgs, setShiftMsgs] = useState<ShiftChange[]>([]);
  const [msgsOpen, setMsgsOpen] = useState(false);   // mở rộng xem hết
  const [msgsHidden, setMsgsHidden] = useState(false);
  useEffect(() => {
    let alive = true;
    api.attendance
      .myShiftChanges(token, { unseen: true })
      .then((r) => {
        if (!alive) return;
        setShiftMsgs(r.items);
        if (r.items.length > 0) {
          void api.attendance.markShiftChangesSeen(token).catch(() => {});
        }
      })
      .catch(() => alive && setShiftMsgs([]));
    return () => {
      alive = false;
    };
  }, [token]);
  const MSG_PREVIEW = 3;
  const msgsShown = msgsOpen ? shiftMsgs : shiftMsgs.slice(0, MSG_PREVIEW);

  function openReq(dayNum: number) {
    setReqDate(
      `${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`,
    );
  }

  function shiftMonth(offset: number) {
    const [curY, curM] = ym.split("-").map(Number);
    const d = new Date(curY, curM - 1 + offset, 1);
    setYm(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  const row = data?.rows[0] ?? null;

  // Build calendar matrix cells
  const startOffset = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Mon=0..Sun=6
  const calendarCells: (number | null)[] = [];
  for (let i = 0; i < startOffset; i++) {
    calendarCells.push(null);
  }
  if (data) {
    for (let d = 1; d <= data.days_in_month; d++) {
      calendarCells.push(d);
    }
  }

  return (
    <div>
      {/* Ca bị quản lý đổi — người lao động phải biết, không phải tự phát hiện lúc tới xưởng. */}
      {shiftMsgs.length > 0 && !msgsHidden && (
        <div className="cc-myshift">
          <div className="cc-myshift__bar">
            <span className="cc-myshift__head">
              🔔 Ca làm việc của bạn vừa được thay đổi
              {shiftMsgs.length > 1 && ` (${shiftMsgs.length})`}
            </span>
            <button
              type="button"
              className="cc-myshift__x"
              onClick={() => setMsgsHidden(true)}
              aria-label="Ẩn thông báo"
              title="Đã đọc, ẩn đi"
            >
              ×
            </button>
          </div>
          <ul className={`cc-myshift__list${msgsOpen ? " is-open" : ""}`}>
            {msgsShown.map((m) => (
              <li key={m.id}>
                Ca làm việc ngày <b>{fmtDateVN(m.apply_date)}</b>
                {m.kind === "base" && " (và các ngày sau)"} của bạn đã được thay đổi từ{" "}
                <b>{m.is_off_before ? "Nghỉ theo lịch" : (m.shift_name_before ?? "không có ca")}</b>{" "}
                sang{" "}
                <b>{m.is_off_after ? "Nghỉ theo lịch" : (m.shift_name_after ?? "không có ca")}</b>
                {m.actor_name && <> bởi <b>{m.actor_name}</b></>}.
                <em>{fmtDateTime(m.created_at)}</em>
              </li>
            ))}
          </ul>
          {shiftMsgs.length > MSG_PREVIEW && (
            <button
              type="button"
              className="cc-myshift__more"
              onClick={() => setMsgsOpen((o) => !o)}
            >
              {msgsOpen
                ? "Thu gọn"
                : `Xem thêm ${shiftMsgs.length - MSG_PREVIEW} thay đổi nữa`}
            </button>
          )}
        </div>
      )}
      <div className="cc-ts-toolbar-container">
        <div className="cc-month-navigator">
          <button
            className="cc-month-nav-btn"
            onClick={() => shiftMonth(-1)}
            title="Tháng trước"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="cc-month-nav-label">
            Tháng {month} / {year}
          </span>
          <button
            className="cc-month-nav-btn"
            onClick={() => shiftMonth(1)}
            title="Tháng sau"
          >
            <ChevronRight size={16} />
          </button>
          <div className="cc-month-picker-wrapper">
            <input
              type="month"
              className="cc-month-picker-hidden"
              value={ym}
              onChange={(e) => setYm(e.target.value)}
              id="cc-month-picker"
            />
            <label
              htmlFor="cc-month-picker"
              className="cc-month-picker-trigger"
              title="Chọn tháng nhanh"
            >
              <CalendarDays size={14} /> Chọn tháng
            </label>
          </div>
        </div>

        <div className="cc-ts-info-group">
          <div className="cc-ts-legend">
            <span className="cc-ts-legend-title">Chú giải:</span>
            <span className="cc-badge-pill cc-badge-pill--primary">
              ✓ Đi làm
            </span>
            <span className="cc-badge-pill cc-badge-pill--orange">
              +OT Làm thêm
            </span>
            <span className="cc-badge-pill cc-badge-pill--purple">
              Nghỉ lễ/Phép
            </span>
          </div>

          <div className="cc-ts-tip">
            <Info size={13} style={{ color: "var(--rust)" }} />
            <span>Bấm vào ô ngày trên lịch để gửi yêu cầu chỉnh công.</span>
          </div>
        </div>
      </div>
      {loading && <p className="ns__empty">Đang tải biểu công…</p>}
      {!loading && !row && (
        <p className="ns__empty">Tháng này bạn chưa có dữ liệu chấm công.</p>
      )}
      {!loading && row && data && (
        <div
          style={{
            background: "var(--canvas)",
            padding: "20px",
            borderRadius: "10px",
            border: "1px solid var(--rule-soft)",
            boxShadow: "var(--shadow-1)",
          }}
        >
          <h4 className="ns-section__title" style={{ marginTop: 0 }}>
            Lịch công của tôi ({month}/{year})
          </h4>

          <div className="cc-month-grid">
            {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((w) => (
              <div
                key={w}
                style={{
                  textAlign: "center",
                  fontWeight: "bold",
                  fontSize: "12px",
                  paddingBottom: "8px",
                  color: "var(--ash)",
                }}
              >
                {w}
              </div>
            ))}
            {calendarCells.map((dayNum, idx) => {
              if (dayNum === null)
                return (
                  <div
                    key={`empty-${idx}`}
                    className="cc-month-cell cc-month-cell--empty"
                  />
                );
              const day = row.days[String(dayNum)];
              let cellClass = "cc-month-cell";
              let statusLabel = "";
              let timeRange = "";
              let otBadge = false;

              if (day) {
                if (day.leave) {
                  cellClass += " cc-month-cell--holiday";
                  statusLabel = day.leave_paid ? "Nghỉ Phép (P)" : "Nghỉ KL";
                } else {
                  const hasPunch = day.first_in || day.last_out;
                  if (hasPunch) {
                    cellClass += " cc-month-cell--work";
                    if (day.late || day.early)
                      cellClass += " cc-month-cell--makeup";
                    timeRange = `${day.first_in ?? "?"} - ${day.last_out ?? "?"}`;
                    statusLabel =
                      day.cong != null
                        ? `Công: ${day.cong}`
                        : day.hours != null
                          ? `${day.hours}h`
                          : "Đã chấm";
                    if (day.ot_minutes) otBadge = true;
                  }
                }
              }

              const currentDayOfWeek = new Date(
                year,
                month - 1,
                dayNum,
              ).getDay();
              const isWeekend =
                currentDayOfWeek === 0 || currentDayOfWeek === 6;
              if (!day && isWeekend) {
                cellClass += " cc-month-cell--weekend";
              }

              return (
                <div
                  key={dayNum}
                  className={cellClass}
                  style={{ cursor: "pointer" }}
                  onClick={() => openReq(dayNum)}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <span className="cc-month-cell-num">{dayNum}</span>
                    {otBadge && (
                      <span
                        className="cc-badge-pill cc-badge-pill--orange"
                        style={{ padding: "1px 4px", fontSize: "9px" }}
                      >
                        +OT
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: "11px",
                      fontWeight: 600,
                      color: "var(--ink)",
                      marginTop: "4px",
                    }}
                  >
                    {timeRange || "—"}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: "var(--ash)",
                      marginTop: "2px",
                      display: "flex",
                      justifyContent: "space-between",
                      width: "100%",
                    }}
                  >
                    <span>{statusLabel}</span>
                    {day?.late && (
                      <span
                        style={{ color: "var(--signal)", fontWeight: "bold" }}
                      >
                        Muộn
                      </span>
                    )}
                    {day?.early && (
                      <span
                        style={{
                          color: "var(--amber-deep)",
                          fontWeight: "bold",
                        }}
                      >
                        Sớm
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {reqs.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h4 className="ns-section__title">
            Yêu cầu chỉnh công đã gửi
            {quota && quota.limit > 0 && (
              <span
                className="cc-note"
                style={{ marginLeft: 8, fontWeight: 400 }}
              >
                · tháng {quota.month}: {quota.used}/{quota.limit} ngày, còn{" "}
                {quota.remaining} lần
              </span>
            )}
          </h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th>Chấm</th>
                  <th>Giờ đề xuất</th>
                  <th>Lý do</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {reqs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.work_date}</td>
                    <td>{r.check_type === "in" ? "VÀO" : "RA"}</td>
                    <td>{r.suggested_time ?? "—"}</td>
                    <td>
                      {r.reason}
                      {r.decision_note ? ` · (${r.decision_note})` : ""}
                    </td>
                    <td>{statusBadge(r.status)}</td>
                    <td>
                      {r.status === "pending" && (
                        <button
                          className="btn btn--ghost ns-danger"
                          style={{ padding: "2px 8px" }}
                          onClick={() =>
                            api.attendance
                              .cancelAdjustRequest(token, r.id)
                              .then(loadReqs)
                          }
                        >
                          Hủy
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {reqDate && (
        <RequestAdjustModal
          token={token}
          date={reqDate}
          quota={quota}
          onClose={() => setReqDate(null)}
          onSaved={() => {
            setReqDate(null);
            loadReqs();
          }}
        />
      )}
    </div>
  );
}

// NV gửi yêu cầu chỉnh công cho 1 ngày (self-service).
function RequestAdjustModal({
  token,
  date,
  quota,
  onClose,
  onSaved,
}: {
  token: string;
  date: string;
  quota: AdjustQuota | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [checkType, setCheckType] = useState<"in" | "out">("out");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hạn mức đếm theo NGÀY CÔNG: ngày này đã có đơn còn hiệu lực thì gửi thêm (vd bù nốt lượt RA)
  // KHÔNG tốn lượt mới — phải nói ra, không thì người ta sợ không dám gửi.
  // Quota trả về là của THÁNG HIỆN TẠI, còn modal mở được cho ngày thuộc tháng khác (xem bảng
  // công tháng trước rồi bấm vào ô). Lệch tháng thì im lặng để backend quyết — thà không nhắc
  // còn hơn khoá nhầm nút Gửi bằng số của tháng khác.
  const sameMonth =
    !!quota &&
    date.startsWith(`${quota.year}-${String(quota.month).padStart(2, "0")}-`);
  const dayCounted = sameMonth && !!quota && quota.days.includes(date);
  const quotaBlocked =
    sameMonth &&
    !!quota &&
    quota.limit > 0 &&
    !dayCounted &&
    quota.used >= quota.limit;
  const quotaNote =
    !quota || quota.limit === 0 || !sameMonth
      ? null
      : quotaBlocked
        ? `Tháng ${quota.month} đã dùng hết ${quota.used}/${quota.limit} lần chỉnh công. ` +
          `Hủy một yêu cầu đang chờ, hoặc nhờ HCNS chấm bù trực tiếp.`
        : dayCounted
          ? `Ngày này đã tính lượt rồi — gửi thêm không tốn lượt. ` +
            `(Tháng ${quota.month}: đã dùng ${quota.used}/${quota.limit} ngày.)`
          : `Tháng ${quota.month}: đã dùng ${quota.used}/${quota.limit} ngày, còn ${quota.remaining} lần.`;

  async function submit() {
    if (!reason.trim()) {
      setError("Phải nhập lý do.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.attendance.createAdjustRequest(token, {
        date,
        check_type: checkType,
        suggested_time: time || null,
        reason: reason.trim(),
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi gửi yêu cầu.");
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Xin chỉnh công · {date}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          {quotaNote && (
            <div
              className={`banner ${quotaBlocked ? "banner--warn" : ""}`}
              style={{ marginBottom: 12 }}
            >
              {quotaNote}
            </div>
          )}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Chấm còn thiếu</span>
              <select
                value={checkType}
                onChange={(e) => setCheckType(e.target.value as "in" | "out")}
              >
                <option value="in">VÀO</option>
                <option value="out">RA</option>
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">
                Giờ (gợi ý, không bắt buộc)
              </span>
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do (bắt buộc)</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="vd: Quên chấm ra vì máy hết pin…"
            />
          </label>
          <p className="cc-note">
            Yêu cầu sẽ gửi HCNS duyệt. Được duyệt thì công tự cập nhật.
          </p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={submit}
            disabled={busy || quotaBlocked}
          >
            {busy ? "Đang gửi…" : "Gửi yêu cầu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Điểm chấm công (HR) -----------------------------------------------

function LocationsTab({ token }: { token: string }) {
  const [items, setItems] = useState<WorkLocation[] | null>(null);
  const [editing, setEditing] = useState<WorkLocation | "new" | null>(null);

  const load = useCallback(() => {
    api.attendance
      .locations(token)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn xóa điểm chấm công này?"))
      return;
    await api.attendance.deleteLocation(token, id);
    load();
  }

  async function toggleActive(loc: WorkLocation) {
    try {
      await api.attendance.updateLocation(token, loc.id, {
        name: loc.name,
        latitude: loc.latitude,
        longitude: loc.longitude,
        radius_m: loc.radius_m,
        note: loc.note,
        is_active: !loc.is_active,
      });
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Lỗi khi cập nhật.");
    }
  }

  const totalLocations = items?.length ?? 0;
  const activeLocations = items?.filter((l) => l.is_active).length ?? 0;
  const avgRadius =
    items && items.length > 0
      ? Math.round(items.reduce((acc, l) => acc + l.radius_m, 0) / items.length)
      : 0;

  return (
    <div className="cc-locations-wrapper">
      {/* 1. Header Toolbar & Quick Stats */}
      <div className="cc-calendar-dashboard" style={{ marginBottom: 20 }}>
        <div className="cc-calendar-stats-strip">
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--users">
              <MapPin size={16} />
            </span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalLocations}</span>
              <span className="cc-calendar-stat-label">Vị trí geofence</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--check">
              <CheckCircle size={16} />
            </span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{activeLocations}</span>
              <span className="cc-calendar-stat-label">Đang hoạt động</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--clock">
              <Target size={16} />
            </span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{avgRadius} m</span>
              <span className="cc-calendar-stat-label">Bán kính trung bình</span>
            </div>
          </div>
        </div>

        <button
          className="btn btn--primary cc-btn-cta-compact"
          onClick={() => setEditing("new")}
        >
          <Plus size={16} />
          <span>Thêm điểm chấm công</span>
        </button>
      </div>

      {/* 2. Location Cards Grid */}
      {items === null ? (
        <div className="ns__empty cc-calendar-loading">
          <div className="cc-loading-spinner" />
          <span>Đang tải danh sách điểm chấm công...</span>
        </div>
      ) : items.length === 0 ? (
        <div className="ns__empty" style={{ padding: 40 }}>
          Chưa có điểm chấm công nào được cấu hình. Bấm "+ Thêm điểm chấm công" để tạo mới.
        </div>
      ) : (
        <div className="cc-locations-grid">
          {items.map((l) => {
            const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${l.latitude},${l.longitude}`;
            return (
              <div
                key={l.id}
                className={`cc-loc-card-v2 ${!l.is_active ? "is-inactive" : ""}`}
              >
                <div className="cc-loc-card-head">
                  <div className="cc-loc-icon-wrapper">
                    <MapPin size={20} />
                  </div>
                  <div className="cc-loc-title-group">
                    <h3 className="cc-loc-card-title" title={l.name}>
                      {l.name}
                    </h3>
                    <div className="cc-loc-status-row">
                      {l.is_active ? (
                        <span className="cc-type-badge cc-type-badge--paid">
                          <CheckCircle size={11} />
                          <span>Đang dùng</span>
                        </span>
                      ) : (
                        <span className="cc-type-badge cc-type-badge--unpaid">
                          <XCircle size={11} />
                          <span>Đã tắt</span>
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="cc-leave-type-active-switch">
                    <label
                      className="cc-switch"
                      title={
                        l.is_active
                          ? "Đang sử dụng (Click để tắt)"
                          : "Đã tắt (Click để bật)"
                      }
                    >
                      <input
                        type="checkbox"
                        checked={l.is_active}
                        onChange={() => toggleActive(l)}
                      />
                      <span className="cc-slider" />
                    </label>
                  </div>
                </div>

                <div className="cc-loc-card-body">
                  <div className="cc-loc-coord-row">
                    <div className="cc-loc-coord-badge">
                      <Navigation size={12} style={{ opacity: 0.7 }} />
                      <span>
                        {Number(l.latitude).toFixed(6)},{" "}
                        {Number(l.longitude).toFixed(6)}
                      </span>
                    </div>

                    <a
                      href={mapsUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="cc-loc-maps-link"
                      title="Mở tọa độ trên Google Maps"
                    >
                      <span>Bản đồ</span>
                      <ExternalLink size={12} />
                    </a>
                  </div>

                  <div className="cc-geofence-radar-pill">
                    <div className="cc-geofence-pulse-ring" />
                    <Target size={13} style={{ color: "var(--rust)" }} />
                    <span>
                      Bán kính cho phép: <b>{l.radius_m} m</b>
                    </span>
                  </div>

                  {l.note && (
                    <div className="cc-loc-note-box" title={l.note}>
                      <span className="cc-loc-note-label">Ghi chú:</span> {l.note}
                    </div>
                  )}
                </div>

                <div className="cc-loc-card-foot">
                  <button
                    className="cc-leave-type-action-btn"
                    onClick={() => setEditing(l)}
                  >
                    <Edit3 size={13} />
                    <span>Sửa</span>
                  </button>
                  <button
                    className="cc-leave-type-action-btn cc-leave-type-action-btn--danger"
                    onClick={() => remove(l.id)}
                  >
                    <Trash2 size={13} />
                    <span>Xóa</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {editing && (
        <LocationForm
          token={token}
          location={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function LocationForm({
  token,
  location,
  onClose,
  onSaved,
}: {
  token: string;
  location: WorkLocation | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkLocationInput>({
    name: location?.name ?? "",
    latitude: location?.latitude ?? 0,
    longitude: location?.longitude ?? 0,
    radius_m: location?.radius_m ?? 150,
    note: location?.note ?? "",
    is_active: location?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  function set<K extends keyof WorkLocationInput>(
    k: K,
    v: WorkLocationInput[K],
  ) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function useMyLocation() {
    setLocating(true);
    setError(null);
    try {
      const pos = await getPosition();
      setForm((f) => ({
        ...f,
        latitude: Number(pos.coords.latitude.toFixed(7)),
        longitude: Number(pos.coords.longitude.toFixed(7)),
      }));
    } catch (e) {
      setError(geoErrText(e));
    } finally {
      setLocating(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (!form.name.trim()) throw new Error("Vui lòng nhập tên điểm chấm công.");
      if (location)
        await api.attendance.updateLocation(token, location.id, form);
      else await api.attendance.createLocation(token, form);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu.");
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>{location ? "Chỉnh sửa điểm chấm công" : "Tạo điểm chấm công mới"}</h2>
            <p className="cc-modal-subtitle">Cấu hình tọa độ GPS và bán kính geofence cho phép chốt công</p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: 16 }}>{error}</div>}
          
          <label className="ns-field">
            <span className="cc-field-label">Tên điểm chấm công *</span>
            <input
              className="cc-input-text"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="vd: Xưởng in Sao Việt Nhật, Văn phòng đại diện..."
            />
          </label>

          <div style={{ marginTop: 12, marginBottom: 12 }}>
            <button
              type="button"
              className="btn btn--ghost"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                width: "100%",
                justifyContent: "center",
                borderStyle: "dashed",
                borderColor: "var(--rust)",
                color: "var(--rust-deep)",
                background: "var(--rust-soft)",
                padding: "8px 14px",
                borderRadius: "var(--r-3)",
                fontWeight: "var(--fw-bold)",
                fontSize: "12.5px"
              }}
              onClick={useMyLocation}
              disabled={locating}
            >
              <Navigation size={14} />
              <span>{locating ? "Đang lấy tọa độ GPS..." : "Lấy vị trí GPS hiện tại của tôi"}</span>
            </button>
          </div>

          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="cc-field-label">Vĩ độ (latitude)</span>
              <input
                type="number"
                step="0.0000001"
                className="cc-input-text"
                value={form.latitude}
                onChange={(e) => set("latitude", Number(e.target.value))}
              />
            </label>
            <label className="ns-field">
              <span className="cc-field-label">Kinh độ (longitude)</span>
              <input
                type="number"
                step="0.0000001"
                className="cc-input-text"
                value={form.longitude}
                onChange={(e) => set("longitude", Number(e.target.value))}
              />
            </label>
          </div>

          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Bán kính cho phép (mét) *</span>
            <input
              type="number"
              min={10}
              className="cc-input-text"
              value={form.radius_m}
              onChange={(e) => set("radius_m", Number(e.target.value))}
              placeholder="vd: 150"
            />
            <div className="cc-radius-presets-row" style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--ash-2)" }}>Chọn nhanh:</span>
              {[50, 100, 150, 200, 500].map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`cc-calendar-chip ${form.radius_m === r ? "is-active" : ""}`}
                  style={{ padding: "2px 10px", fontSize: 11 }}
                  onClick={() => set("radius_m", r)}
                >
                  {r}m
                </button>
              ))}
            </div>
            <span className="cc-field-subtext" style={{ marginTop: 4 }}>Khoảng cách tối đa (mét) tính từ tâm vị trí cho phép nhân viên ấn nút Chấm công</span>
          </label>

          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Ghi chú</span>
            <input
              className="cc-input-text"
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
              placeholder="Địa chỉ cụ thể, hướng dẫn vị trí..."
            />
          </label>

          <div style={{ marginTop: 16, display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--canvas)", padding: "10px 14px", borderRadius: "var(--r-3)", border: "1px solid var(--rule-soft)" }}>
            <div>
              <span className="cc-field-label" style={{ margin: 0, fontWeight: "var(--fw-bold)" }}>Đang hoạt động</span>
              <span className="cc-field-subtext" style={{ display: "block" }}>Cho phép nhân viên chốt công tại vị trí này.</span>
            </div>
            <label className="cc-switch">
              <input
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) => set("is_active", e.target.checked)}
              />
              <span className="cc-slider" />
            </label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu cấu hình"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Bảng chấm công (HR) -----------------------------------------------

function LogsTab({
  token,
  focusEmployeeId,
}: {
  token: string;
  focusEmployeeId?: number;
}) {
  const [items, setItems] = useState<AttendanceLog[] | null>(null);
  const [focus, setFocus] = useState<number | undefined>(focusEmployeeId);
  const [kpi, setKpi] = useState<TodayKpi | null>(null);

  useEffect(() => setFocus(focusEmployeeId), [focusEmployeeId]);
  useEffect(() => {
    api.attendance
      .logs(token, focus)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, focus]);

  useEffect(() => {
    if (focus == null) {
      api.attendance
        .kpi(token)
        .then(setKpi)
        .catch(() => setKpi(null));
    }
  }, [token, focus]);

  const focusName = focus
    ? items?.find((l) => l.employee_id === focus)?.employee_name
    : undefined;

  // Render chart slices for Recharts MixDonut
  const chartSlices = kpi
    ? [
        { label: "Đang có mặt", value: kpi.present_now },
        { label: "Quên chấm RA", value: kpi.missing_out },
        { label: "Đi muộn hôm nay", value: kpi.late_today },
        { label: "YC chờ duyệt", value: kpi.pending_requests },
      ].filter((s) => s.value > 0)
    : [];

  return (
    <div>
      {focus != null && (
        <div className="cc-focus">
          <span>
            Đang xem chấm công của <b>{focusName ?? `NV #${focus}`}</b>
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setFocus(undefined)}
          >
            ✕ Bỏ lọc — xem cả xưởng
          </button>
        </div>
      )}

      {focus == null && kpi && (
        <div className="cc-analytics-section">
          <div className="cc-analytics-grid">
            {/* KPI Cards Grid */}
            <div className="cc-kpi-grid">
              <div className="cc-kpi-card cc-kpi-card--in">
                <div className="cc-kpi-icon-wrapper">
                  <UserCheck size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.present_now}</span>
                  <span className="cc-kpi-title">Đang có mặt</span>
                </div>
              </div>
              <div className="cc-kpi-card cc-kpi-card--out">
                <div className="cc-kpi-icon-wrapper">
                  <XCircle size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.missing_out}</span>
                  <span className="cc-kpi-title">Quên chấm RA</span>
                </div>
              </div>
              <div className="cc-kpi-card cc-kpi-card--late">
                <div className="cc-kpi-icon-wrapper">
                  <AlertTriangle size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.late_today}</span>
                  <span className="cc-kpi-title">Đi muộn hôm nay</span>
                </div>
              </div>
              <div className="cc-kpi-card cc-kpi-card--pending">
                <div className="cc-kpi-icon-wrapper">
                  <FileEdit size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.pending_requests}</span>
                  <span className="cc-kpi-title">YC chờ duyệt</span>
                </div>
              </div>
            </div>

            {/* Donut chart analysis */}
            <div
              style={{
                background: "var(--paper)",
                padding: "16px",
                borderRadius: "10px",
                border: "1px solid var(--rule-soft)",
              }}
            >
              <div className="cc-chart-title">
                <ClipboardList size={14} /> Tỷ lệ chuyên cần hôm nay
              </div>
              {chartSlices.length > 0 ? (
                <div className="cc-chart-container">
                  <MixDonut
                    slices={chartSlices}
                    centerTop={String(kpi.present_now)}
                    centerBottom="Đang có mặt"
                    formatValue={(v) => `${v} người`}
                    height={160}
                  />
                </div>
              ) : (
                <div
                  className="ns__empty"
                  style={{
                    height: "160px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  Hôm nay chưa có dữ liệu chấm công.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {!items ? (
        <p className="ns__empty">Đang tải lịch sử chấm công…</p>
      ) : (
        <AttendanceTable logs={items} showEmployee={focus == null} />
      )}
    </div>
  );
}

// --- Tab: Bảng công tháng (HR) ----------------------------------------------

// --- Tab: Khai ca (HR) ------------------------------------------------------

// --- Tab: Lịch làm việc & Ngày lễ (nền dùng chung cho Công / Phép / Lương) --

const WEEKDAY_FIELDS: { key: keyof WorkCalendarConfigInput; label: string }[] =
  [
    { key: "works_mon", label: "T2" },
    { key: "works_tue", label: "T3" },
    { key: "works_wed", label: "T4" },
    { key: "works_thu", label: "T5" },
    { key: "works_fri", label: "T6" },
    { key: "works_sat", label: "T7" },
    { key: "works_sun", label: "CN" },
  ];
const KIND_LABEL: Record<string, string> = {
  off: "Nghỉ lễ",
  work: "Làm bù",
  off1x: "Nghỉ — làm 1×",
};

function fmtDateVN(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/** Lưới tháng: chèn ô trống đầu tuần để ngày 1 rơi đúng cột thứ (Mon=0..Sun=6). */
function buildMonthGrid(m: CalendarMonth): (CalendarDayCell | null)[] {
  const lead = m.days.length ? m.days[0].weekday : 0;
  return [...Array<null>(lead).fill(null), ...m.days];
}

function CalendarTab({ token }: { token: string }) {
  const now = new Date();
  const [config, setConfig] = useState<WorkCalendarConfig | null>(null);
  const [cfgBusy, setCfgBusy] = useState(false);
  const [cfgMsg, setCfgMsg] = useState<string | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [special, setSpecial] = useState<SpecialDaysOut | null>(null);
  const [editing, setEditing] = useState<SpecialDay | "new" | null>(null);
  const [previewMonth, setPreviewMonth] = useState(now.getMonth() + 1);
  const [preview, setPreview] = useState<CalendarMonth | null>(null);

  const loadConfig = useCallback(() => {
    api.calendar
      .getConfig(token)
      .then(setConfig)
      .catch(() => setConfig(null));
  }, [token]);
  const loadSpecial = useCallback(() => {
    api.calendar
      .specialDays(token, year)
      .then(setSpecial)
      .catch(() => setSpecial(null));
  }, [token, year]);
  const loadPreview = useCallback(() => {
    api.calendar
      .month(token, year, previewMonth)
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [token, year, previewMonth]);
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);
  useEffect(() => {
    loadSpecial();
  }, [loadSpecial]);
  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  function toggleDay(key: keyof WorkCalendarConfigInput) {
    setConfig((c) => (c ? { ...c, [key]: !c[key] } : c));
    setCfgMsg(null);
  }
  async function saveConfig() {
    if (!config) return;
    setCfgBusy(true);
    setCfgMsg(null);
    try {
      const saved = await api.calendar.updateConfig(token, {
        works_mon: config.works_mon,
        works_tue: config.works_tue,
        works_wed: config.works_wed,
        works_thu: config.works_thu,
        works_fri: config.works_fri,
        works_sat: config.works_sat,
        works_sun: config.works_sun,
      });
      setConfig(saved);
      setCfgMsg("Đã lưu tuần làm việc.");
      loadPreview();
    } catch (e) {
      setCfgMsg(e instanceof Error ? e.message : "Lỗi khi lưu.");
    } finally {
      setCfgBusy(false);
    }
  }
  async function removeSpecial(id: number) {
    await api.calendar.deleteSpecialDay(token, id);
    loadSpecial();
    loadPreview();
  }

  return (
    <div className="cal">
      <div className="cal-grid-top">
        {/* Tuần làm việc chuẩn */}
        <section className="cal-panel">
          <h4 className="ns-section__title">Tuần làm việc chuẩn</h4>
          <p className="cc-note" style={{ marginTop: "4px" }}>
            Bật/tắt từng thứ. Ngày làm việc là mẫu tính công chuẩn tháng + trừ
            phép năm; ngày tắt = nghỉ tuần (không trừ phép). Ngày lễ khai riêng
            ở bên cạnh.
          </p>
          <div className="cal-week">
            {WEEKDAY_FIELDS.map((w) => (
              <label
                key={String(w.key)}
                className={`cal-week__day ${config?.[w.key] ? "is-on" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={!!config?.[w.key]}
                  onChange={() => toggleDay(w.key)}
                />
                <span>{w.label}</span>
              </label>
            ))}
          </div>
          <div
            className="cc-toolbar"
            style={{ marginTop: "auto", marginBottom: 0 }}
          >
            <button
              className="btn btn--primary"
              onClick={saveConfig}
              disabled={cfgBusy || !config}
            >
              {cfgBusy ? "Đang lưu…" : "Lưu tuần làm việc"}
            </button>
            {cfgMsg && (
              <span
                className="cc-assign__msg"
                style={{
                  marginLeft: "12px",
                  color: "var(--moss)",
                  fontSize: "13px",
                }}
              >
                {cfgMsg}
              </span>
            )}
          </div>
        </section>

        {/* Ngày lễ & làm bù */}
        <section
          className="cal-panel"
          style={{ display: "flex", flexDirection: "column" }}
        >
          <div className="cal-panel__head">
            <h4 className="ns-section__title">Ngày lễ & làm bù</h4>
            <div className="cal-yearpick">
              <button
                type="button"
                onClick={() => setYear((y) => y - 1)}
                aria-label="Năm trước"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="cal-year">{year}</span>
              <button
                type="button"
                onClick={() => setYear((y) => y + 1)}
                aria-label="Năm sau"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="cc-toolbar">
            <button
              className="btn btn--primary"
              onClick={() => setEditing("new")}
            >
              <Plus
                size={14}
                style={{
                  marginRight: "4px",
                  display: "inline-block",
                  verticalAlign: "middle",
                }}
              />
              <span>Thêm ngày</span>
            </button>
          </div>

          <div
            className="ns__tablewrap"
            style={{ flexGrow: 1, overflowY: "auto", maxHeight: "250px" }}
          >
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th>Tên</th>
                  <th>Loại</th>
                  <th>Hưởng lương</th>
                  <th style={{ width: "160px", textAlign: "right" }}></th>
                </tr>
              </thead>
              <tbody>
                {special?.items.map((s) => (
                  <tr key={s.id}>
                    <td className="ns__code">{fmtDateVN(s.day)}</td>
                    <td style={{ fontWeight: "var(--fw-medium)" }}>{s.name}</td>
                    <td>
                      <span
                        className={`ns-badge ${s.kind === "work" ? "ns-badge--info" : s.kind === "off1x" ? "ns-badge--warn" : "ns-badge--ok"}`}
                      >
                        {KIND_LABEL[s.kind] ?? s.kind}
                      </span>
                    </td>
                    <td>
                      {s.kind === "off" ? (s.is_paid ? "Có" : "Không") : "—"}
                    </td>
                    <td className="cc-rowact" style={{ textAlign: "right" }}>
                      <button
                        className="btn btn--ghost btn--sm"
                        onClick={() => setEditing(s)}
                        style={{ padding: "4px 8px", marginRight: "4px" }}
                        title="Sửa"
                      >
                        <Edit3
                          size={13}
                          style={{
                            display: "inline-block",
                            verticalAlign: "middle",
                            marginRight: "2px",
                          }}
                        />
                        Sửa
                      </button>
                      <button
                        className="btn btn--ghost btn--sm ns-danger"
                        onClick={() => removeSpecial(s.id)}
                        style={{ padding: "4px 8px" }}
                        title="Xóa"
                      >
                        <Trash2
                          size={13}
                          style={{
                            display: "inline-block",
                            verticalAlign: "middle",
                            marginRight: "2px",
                          }}
                        />
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
                {!special && (
                  <tr>
                    <td colSpan={5} className="ns__empty">
                      Đang tải…
                    </td>
                  </tr>
                )}
                {special?.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="ns__empty">
                      Chưa khai ngày đặc biệt nào cho năm {year}.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Xem trước tháng (Full Width) */}
      <section className="cal-panel">
        <div className="cal-panel__head">
          <h4 className="ns-section__title">Xem trước tháng</h4>
          <div className="cal-monthpick-nav">
            <button
              type="button"
              onClick={() => setPreviewMonth((m) => (m === 1 ? 12 : m - 1))}
              aria-label="Tháng trước"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="cal-month-label">Tháng {previewMonth}</span>
            <button
              type="button"
              onClick={() => setPreviewMonth((m) => (m === 12 ? 1 : m + 1))}
              aria-label="Tháng sau"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        {!preview && <p className="cal-standard">Đang tải lịch tháng…</p>}
        {preview && (
          <>
            <p className="cal-standard">
              <Info size={14} style={{ color: "var(--ash)", flexShrink: 0 }} />
              <span>
                Công chuẩn tháng {preview.month}/{preview.year}:{" "}
                <strong>{preview.working_days}</strong> công
                {preview.holidays.length > 0 && (
                  <> · {preview.holidays.length} ngày lễ</>
                )}
              </span>
            </p>
            <div className="cc-month-grid">
              {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((d) => (
                <div
                  key={d}
                  style={{
                    textAlign: "center",
                    fontWeight: "bold",
                    fontSize: "12px",
                    paddingBottom: "6px",
                    color: "var(--ash)",
                  }}
                >
                  {d}
                </div>
              ))}
              {buildMonthGrid(preview).map((cell, i) =>
                cell ? (
                  <div
                    key={i}
                    className={`cc-month-cell cc-month-cell--${cell.kind}`}
                    title={cell.name ?? ""}
                  >
                    <span className="cc-month-cell-num">{cell.day}</span>
                    {cell.name && (
                      <span className="cc-month-cell-name">{cell.name}</span>
                    )}
                  </div>
                ) : (
                  <div key={i} className="cc-month-cell cc-month-cell--empty" />
                ),
              )}
            </div>
            <div className="cal-legend">
              <span className="cal-lg cal-lg--work">Ngày làm</span>
              <span className="cal-lg cal-lg--weekend">Nghỉ tuần</span>
              <span className="cal-lg cal-lg--holiday">Nghỉ lễ</span>
              <span className="cal-lg cal-lg--makeup">Làm bù</span>
            </div>
          </>
        )}
      </section>

      {editing && (
        <SpecialDayForm
          token={token}
          special={editing === "new" ? null : editing}
          year={year}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            loadSpecial();
            loadPreview();
          }}
        />
      )}
    </div>
  );
}

function SpecialDayForm({
  token,
  special,
  year,
  onClose,
  onSaved,
}: {
  token: string;
  special: SpecialDay | null;
  year: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<SpecialDayInput>({
    day: special?.day ?? `${year}-01-01`,
    kind: special?.kind ?? "off",
    name: special?.name ?? "",
    is_paid: special?.is_paid ?? true,
    note: special?.note ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof SpecialDayInput>(k: K, v: SpecialDayInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (special) await api.calendar.updateSpecialDay(token, special.id, form);
      else await api.calendar.createSpecialDay(token, form);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu.");
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{special ? "Sửa ngày đặc biệt" : "Thêm ngày đặc biệt"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field">
            <span className="ns-field__label">Ngày *</span>
            <input
              type="date"
              value={form.day}
              onChange={(e) => set("day", e.target.value)}
            />
          </label>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Tên *</span>
            <input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="vd Quốc khánh"
            />
          </label>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Loại</span>
            <select
              value={form.kind}
              onChange={(e) =>
                set("kind", e.target.value as "off" | "work" | "off1x")
              }
            >
              <option value="off">Nghỉ lễ (ngày lẽ ra làm nhưng nghỉ)</option>
              <option value="work">Làm bù (đi làm ngày lẽ ra nghỉ)</option>
              <option value="off1x">
                Nghỉ — đi làm chỉ lương chính (1×, không hệ số)
              </option>
            </select>
          </label>
          {form.kind === "off" && (
            <label className="ns-check" style={{ marginTop: 12 }}>
              <input
                type="checkbox"
                checked={!!form.is_paid}
                onChange={(e) => set("is_paid", e.target.checked)}
              />
              Hưởng nguyên lương (cộng 1 công vào bảng công)
            </label>
          )}
          {form.kind === "off1x" && (
            <p className="cc-note" style={{ marginTop: 10 }}>
              Ngày nghỉ <b>không lương</b>. Ai đi làm được{" "}
              <b>cộng thêm 1 công lương chính (1×)</b> — KHÔNG nhân hệ số
              lễ/nghỉ, không bị trần công tháng.
            </p>
          )}
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Ghi chú</span>
            <input
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
              placeholder="vd mùng 1 Tết Âm lịch"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !form.name.trim() || !form.day}
          >
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// ============================================================================
// Khai ca — 3 khối gập: A · Ca làm việc · B · Phân ca tháng · C · Ca mặc định
// ============================================================================

/** Khối gập dùng chung. Nội dung mount LAZY lần mở đầu rồi GIỮ (ẩn bằng `hidden`)
 *  — nếu unmount, bản nháp phân ca đang gõ dở sẽ bay mất khi gập khối lại. */
function CollapsibleSection({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [mounted, setMounted] = useState(defaultOpen);
  useEffect(() => {
    if (open) setMounted(true);
  }, [open]);
  return (
    <section className={`cc-sp-sect ${open ? "is-open" : ""}`}>
      <button
        type="button"
        className="cc-sp-sect__head"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <ChevronDown
          size={16}
          className="cc-sp-sect__chev"
          aria-hidden="true"
        />
        <span className="cc-sp-sect__title">{title}</span>
        {summary != null && <span className="cc-sp-sect__sum">{summary}</span>}
      </button>
      {mounted && (
        <div className="cc-sp-sect__body" hidden={!open}>
          {children}
        </div>
      )}
    </section>
  );
}

// --- Mã ca ngắn + màu: SUY DIỄN Ở FE (backend không có cột code/color) -------
// CẤM `signal` (màu lỗi hệ thống) — chỉ 5 họ dưới đây.
const SHIFT_TONES = ["moss", "amber", "steel", "plum", "rust"] as const;
type ShiftTone = (typeof SHIFT_TONES)[number];

interface ShiftMeta {
  id: number;
  code: string;
  tone: ShiftTone;
  name: string;
  title: string;
}

function stripTones(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");
}

/** Luật deterministic: "ca <n>" → C<n> · "hành chính" → HC · qua đêm → K · còn lại viết tắt ≤3 ký tự. */
function shiftShortCode(s: WorkShift): string {
  const plain = stripTones(s.name).trim();
  const numbered = plain.match(/ca\s*(\d+)/i);
  if (numbered) return `C${numbered[1]}`;
  if (/hanh\s*chinh/i.test(plain)) return "HC";
  if (s.is_overnight) return "K";
  const words = plain.split(/\s+/).filter(Boolean);
  if (words.length >= 2)
    return words
      .slice(0, 3)
      .map((w) => w[0])
      .join("")
      .toUpperCase();
  return (words[0] ?? "?").slice(0, 3).toUpperCase();
}

function buildShiftMeta(shifts: WorkShift[]): Map<number, ShiftMeta> {
  const ordered = [...shifts].sort((a, b) => a.id - b.id); // màu bám thứ tự id tăng dần
  const used = new Map<string, number>();
  const out = new Map<number, ShiftMeta>();
  ordered.forEach((s, i) => {
    const base = shiftShortCode(s);
    const seen = used.get(base) ?? 0;
    used.set(base, seen + 1);
    out.set(s.id, {
      id: s.id,
      code: seen > 0 ? `${base}${seen + 1}` : base, // trùng thì nối chỉ số
      tone: SHIFT_TONES[i % SHIFT_TONES.length],
      name: s.name,
      title: `${s.name} · ${s.start_time}–${s.end_time}${s.is_overnight ? " (qua đêm)" : ""}`,
    });
  });
  return out;
}

// --- Lưới phân ca tháng ------------------------------------------------------
type Brush =
  | { kind: "shift"; shiftId: number }
  | { kind: "off" }
  | { kind: "inherit" };
interface EffCell {
  shiftId: number | null;
  hand: boolean;
  off: boolean;
}
interface DragRect {
  r0: number;
  c0: number;
  r1: number;
  c1: number;
}

const DENSITY_KEY = "cc-sp-density";
const SAVE_CHUNK = 500;
// Dải xem trước trong modal "Áp nhanh" — chỉ để mắt thấy các kíp có lệch nhau thật không.
const QF_STRIP_ROWS = 4;
const QF_STRIP_DAYS = 14;

function ymd(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
function cellKey(employeeId: number, date: string): string {
  return `${employeeId}:${date}`;
}

/** Giá trị KẾ THỪA của từng ngày (ca nền) — suy từ chính các ô server trả về `source !== "day"`.
 *  Cần cho lúc người dùng bấm "Mặc định ⌫": biết trước ô sẽ rơi về ca nào mà không phải gọi lại API. */
function inheritOfRow(
  row: ShiftPlanRow,
  cal: ShiftPlanDay[],
): { inherit: (number | null)[]; base: number | null } {
  const n = cal.length;
  const arr: (number | null)[] = new Array(n).fill(null);
  const known: boolean[] = new Array(n).fill(false);
  cal.forEach((c, i) => {
    const cell = row.days[String(c.day)];
    if (cell && cell.source !== "day") {
      arr[i] = cell.shift_id;
      known[i] = true;
    }
  });
  let last: number | null = null;
  let seen = false;
  for (let i = 0; i < n; i++) {
    if (known[i]) {
      last = arr[i];
      seen = true;
    } else if (seen) arr[i] = last;
  }
  const first = known.indexOf(true);
  if (first > 0) for (let i = 0; i < first; i++) arr[i] = arr[first];
  const freq = new Map<number, number>();
  for (const v of arr) if (v != null) freq.set(v, (freq.get(v) ?? 0) + 1);
  let base: number | null = null;
  let bestCount = 0;
  freq.forEach((count, id) => {
    if (count > bestCount) {
      bestCount = count;
      base = id;
    }
  });
  return { inherit: arr, base };
}

// --- Áp nhanh: lặp một mẫu xoay ca cho cả tổ ---------------------------------
/** Mẫu xoay ca = danh sách BƯỚC, mỗi bước là MỘT NGÀY trong chu kỳ.
 *  Xưởng 3 ca chạy 2-2-2 thì mẫu là [C1, C1, C2, C2, K, K].
 *  `phase` = số bước người kế tiếp bắt đầu MUỘN HƠN người liền trước — nhờ đó các
 *  kíp lệch nhau và ngày nào cũng có người đủ ở cả 3 ca. */
interface RotationPlan {
  pattern: Brush[];
  startDay: number; // ngày trong tháng bắt đầu tô (1..số ngày)
  phase: number; // số bước lệch giữa hai người liền nhau
  skipRest: boolean; // bỏ trắng ngày nghỉ tuần / lễ
}

/** Rải mẫu lên từng người theo ĐÚNG THỨ TỰ ĐANG HIỂN THỊ trên lưới.
 *  Hàm thuần: không đụng state, mọi việc ghi đẩy hết qua `paint` (ở màn này là `applyBrush`). */
function runRotation(
  rows: ShiftPlanRow[],
  cal: ShiftPlanDay[],
  plan: RotationPlan,
  paint: (row: ShiftPlanRow, day: ShiftPlanDay, brush: Brush) => void,
): void {
  const len = plan.pattern.length;
  if (len === 0 || rows.length === 0) return;
  const step = ((Math.trunc(plan.phase) % len) + len) % len;
  rows.forEach((row, i) => {
    let pos = (i * step) % len;
    for (const c of cal) {
      if (c.day < plan.startDay) continue;
      // Ngày bỏ qua thì KHÔNG tiêu 1 bước — tăng pos ở đây là lệch cả chu kỳ về sau.
      if (plan.skipRest && !c.is_working) continue;
      const b = plan.pattern[pos % len];
      pos += 1;
      if (b) paint(row, c, b);
    }
  });
}

/** Số ô THỰC SỰ đổi so với nháp đang giữ (thêm mới · bỏ đi · đổi giá trị).
 *  Tô đè đúng giá trị đang có thì không tính — con số khoe trên modal phải là số thật. */
function countPatchDiff(
  before: Map<string, ShiftPlanPatchItem>,
  after: Map<string, ShiftPlanPatchItem>,
): number {
  let n = 0;
  after.forEach((v, k) => {
    const b = before.get(k);
    if (
      !b ||
      b.action !== v.action ||
      (b.shift_id ?? null) !== (v.shift_id ?? null)
    )
      n += 1;
  });
  before.forEach((_, k) => {
    if (!after.has(k)) n += 1;
  });
  return n;
}

/** Ô nhập số: kẹp về khoảng cho phép ngay khi gõ, khỏi lọt giá trị vô nghĩa vào mẫu. */
function clampNum(raw: string, lo: number, hi: number): number {
  const n = Math.trunc(Number(raw));
  if (!Number.isFinite(n)) return lo;
  return Math.min(hi, Math.max(lo, n));
}

// Họp 28/07: tạm ẩn nút "Áp nhanh" (rải ca cả tháng theo chu kỳ). Hàm openQuickFill + modal
// giữ nguyên, bật lại = đổi cờ này thành true. ĐỪNG comment-out khối JSX để ẩn: làm vậy thì
// openQuickFill và icon Repeat thành mồ côi → tsc gãy vì noUnusedLocals (đúng lỗi CI 29/07).
const SHOW_QUICK_FILL: boolean = false;

function ShiftPlanPanel({ token }: { token: string }) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  });
  const { year, month } = ym;
  const [deptId, setDeptId] = useState<number | "">("");
  const [depts, setDepts] = useState<{ id: number; name: string }[]>([]);
  const [q, setQ] = useState("");
  const [density, setDensity] = useState<"compact" | "roomy">(() =>
    localStorage.getItem(DENSITY_KEY) === "roomy" ? "roomy" : "compact",
  );
  const [data, setData] = useState<ShiftPlanMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [brush, setBrush] = useState<Brush | null>(null);
  const [pending, setPending] = useState<Map<string, ShiftPlanPatchItem>>(
    () => new Map(),
  );
  const [rejects, setRejects] = useState<Map<string, string>>(() => new Map());
  const [drag, setDrag] = useState<DragRect | null>(null);
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);
  const [result, setResult] = useState<{
    saved: number;
    cleared: number;
    rejected: number;
  } | null>(null);
  const [guard, setGuard] = useState<{ run: () => void } | null>(null);
  // Lọc nhanh người CHƯA CÓ CA NỀN. Quan trọng vì form hồ sơ không còn gán ca nữa:
  // người mới tạo sẽ không chấm công được cho tới khi được đặt ca nền ở đây.
  const [onlyNoDefault, setOnlyNoDefault] = useState(false);
  // "Đặt ca nền" — ghi vào MỐC hiệu lực (áp dụng mọi tháng sau), khác hẳn tô lưới.
  // `baseTarget` cho phép áp cho MỘT người (bấm ô Ca nền của hàng đó) hoặc TẤT CẢ
  // người đang hiển thị (nút trên thanh công cụ) — cùng một form, cùng một endpoint.
  const [baseTarget, setBaseTarget] = useState<{
    ids: number[];
    label: string;
  } | null>(null);
  // "" = chưa chọn (chặn Áp dụng) · "none" = cố ý bỏ gán ca. Hai thứ này PHẢI khác nhau:
  // để trống mà vẫn cho bấm thì lỡ tay là xoá ca nền cả phòng, và ai mất ca thì không
  // chấm công được.
  const [baseShift, setBaseShift] = useState<number | "" | "none">("");
  const [baseFrom, setBaseFrom] = useState("");
  const [baseBusy, setBaseBusy] = useState(false);
  const [baseMsg, setBaseMsg] = useState<string | null>(null);
  // Lịch sử đổi ca nền của 1 NV (thay cho bảng lịch sử ở khối "Ca mặc định" cũ).
  const [histFor, setHistFor] = useState<{ id: number; name: string } | null>(
    null,
  );
  const [hist, setHist] = useState<EmployeeShiftAssignment[] | null>(null);
  const [histNonce, setHistNonce] = useState(0);
  const [histBusy, setHistBusy] = useState(false);
  const [histErr, setHistErr] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState<EmployeeShiftAssignment | null>(
    null,
  );
  // "Áp nhanh" — rải sẵn một mẫu xoay ca (vd 2-2-2) cho cả tổ, các kíp lệch pha nhau.
  // Chỉ ghi vào NHÁP như tô tay: xem lưới xong người dùng mới bấm Lưu.
  const [qfOpen, setQfOpen] = useState(false);
  const [qfPattern, setQfPattern] = useState<Brush[]>([]);
  const [qfStart, setQfStart] = useState(1);
  const [qfPhase, setQfPhase] = useState(0);
  const [qfSkipRest, setQfSkipRest] = useState(false);

  const locked = data?.locked === true;
  const dirtyCount = pending.size;

  useEffect(() => {
    localStorage.setItem(DENSITY_KEY, density);
  }, [density]);
  useEffect(() => {
    api.employees
      .meta(token)
      .then((m) => setDepts(m.departments))
      .catch(() => setDepts([]));
  }, [token]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.attendance.shiftPlan(
          token,
          year,
          month,
          deptId === "" ? null : deptId,
        ),
      );
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Không tải được lưới phân ca.");
    } finally {
      setLoading(false);
    }
  }, [token, year, month, deptId]);
  useEffect(() => {
    void reload();
  }, [reload]);
  // Đổi tháng/phòng = thay bộ dữ liệu → nháp cũ không còn ý nghĩa (đã hỏi ở guard trước đó).
  useEffect(() => {
    setPending(new Map());
    setRejects(new Map());
    setResult(null);
    setQfStart(1); // tháng khác = số ngày khác → ngày bắt đầu cũ có thể vượt ra ngoài
  }, [year, month, deptId]);

  // --- Lịch tháng + hàng hiển thị -------------------------------------------
  const cal: ShiftPlanDay[] = useMemo(() => {
    if (!data) return [];
    if (data.calendar.length) return data.calendar;
    return Array.from({ length: data.days_in_month }, (_, i) => {
      const day = i + 1;
      return {
        day,
        date: ymd(data.year, data.month, day),
        weekday: (new Date(data.year, data.month - 1, day).getDay() + 6) % 7,
        is_working: !isWeekend(data.year, data.month, day),
        special_kind: null,
        name: null,
      };
    });
  }, [data]);

  const noDefaultCount = useMemo(
    () => (data?.rows ?? []).filter((r) => r.no_default).length,
    [data],
  );

  const visibleRows = useMemo(() => {
    let rows = data?.rows ?? [];
    if (onlyNoDefault) rows = rows.filter((r) => r.no_default);
    const needle = stripTones(q).trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) =>
      stripTones(`${r.employee_name} ${r.employee_code ?? ""}`)
        .toLowerCase()
        .includes(needle),
    );
  }, [data, q, onlyNoDefault]);

  const shiftMeta = useMemo(() => buildShiftMeta(data?.shifts ?? []), [data]);
  const orderedShifts = useMemo(
    () => [...(data?.shifts ?? [])].sort((a, b) => a.id - b.id),
    [data],
  );
  const paintShifts = useMemo(
    () => orderedShifts.filter((s) => s.is_active),
    [orderedShifts],
  );

  const inheritInfo = useMemo(() => {
    const m = new Map<
      number,
      { inherit: (number | null)[]; base: number | null }
    >();
    for (const r of data?.rows ?? [])
      m.set(r.employee_id, inheritOfRow(r, cal));
    return m;
  }, [data, cal]);

  /** Giá trị HIỂN THỊ của mọi ô = dữ liệu server + nháp đang giữ. */
  const grid: EffCell[][] = useMemo(
    () =>
      visibleRows.map((row) =>
        cal.map((c, ci) => {
          const patch = pending.get(cellKey(row.employee_id, c.date));
          if (patch) {
            if (patch.action === "set")
              return {
                shiftId: patch.shift_id ?? null,
                hand: true,
                off: false,
              };
            if (patch.action === "off")
              return { shiftId: null, hand: true, off: true };
            return {
              shiftId: inheritInfo.get(row.employee_id)?.inherit[ci] ?? null,
              hand: false,
              off: false,
            };
          }
          const cell = row.days[String(c.day)];
          if (!cell) return { shiftId: null, hand: false, off: false };
          return {
            shiftId: cell.shift_id,
            hand: cell.source === "day",
            off: cell.is_off,
          };
        }),
      ),
    [visibleRows, cal, pending, inheritInfo],
  );

  const footCounts = useMemo(
    () =>
      cal.map((_, ci) => {
        const byShift = new Map<number, number>();
        let off = 0;
        let none = 0;
        for (const cells of grid) {
          const eff = cells[ci];
          if (!eff) continue;
          if (eff.off) off += 1;
          else if (eff.shiftId != null)
            byShift.set(eff.shiftId, (byShift.get(eff.shiftId) ?? 0) + 1);
          else none += 1;
        }
        return { byShift, off, none };
      }),
    [grid, cal],
  );

  // --- Bút ca: tô 1 ô hoặc kéo cả hình chữ nhật ------------------------------
  const paintable = !locked && !!brush && !saving;

  const applyBrush = useCallback(
    (
      next: Map<string, ShiftPlanPatchItem>,
      row: ShiftPlanRow,
      c: ShiftPlanDay,
      b: Brush,
    ) => {
      const key = cellKey(row.employee_id, c.date);
      const cell = row.days[String(c.day)];
      const wasHand = cell?.source === "day";
      const wasOff = cell?.is_off === true;
      const wasShift = cell?.shift_id ?? null;
      // Ô quay lại đúng giá trị gốc thì TỰ RƠI khỏi map (không gửi request thừa).
      if (b.kind === "inherit") {
        if (!wasHand) next.delete(key);
        else
          next.set(key, {
            employee_id: row.employee_id,
            work_date: c.date,
            action: "inherit",
          });
      } else if (b.kind === "off") {
        if (wasHand && wasOff) next.delete(key);
        else
          next.set(key, {
            employee_id: row.employee_id,
            work_date: c.date,
            action: "off",
          });
      } else {
        if (wasHand && !wasOff && wasShift === b.shiftId) next.delete(key);
        else
          next.set(key, {
            employee_id: row.employee_id,
            work_date: c.date,
            action: "set",
            shift_id: b.shiftId,
          });
      }
    },
    [],
  );

  // --- Áp nhanh: dựng nháp thử + xem trước -----------------------------------
  const qfPlan: RotationPlan = useMemo(
    () => ({
      pattern: qfPattern,
      startDay: Math.min(Math.max(1, qfStart), Math.max(1, cal.length)),
      phase: qfPhase,
      skipRest: qfSkipRest,
    }),
    [qfPattern, qfStart, qfPhase, qfSkipRest, cal.length],
  );

  /** Nháp SAU KHI áp + số ô đổi. Dùng chung cho dòng tóm tắt và nút "Áp vào nháp",
   *  nên con số người dùng thấy đúng bằng thứ sắp ghi xuống, không phải ước lượng. */
  const qfDraft = useMemo(() => {
    if (!qfOpen || qfPattern.length === 0 || visibleRows.length === 0)
      return null;
    const next = new Map(pending);
    const touched: string[] = [];
    runRotation(visibleRows, cal, qfPlan, (row, day, b) => {
      applyBrush(next, row, day, b);
      touched.push(cellKey(row.employee_id, day.date));
    });
    return { next, touched, changed: countPatchDiff(pending, next) };
  }, [qfOpen, qfPattern.length, visibleRows, cal, qfPlan, pending, applyBrush]);

  /** Dải xem trước: vài người đầu × ít ngày đầu — để mắt kiểm tra các kíp có lệch thật không. */
  const qfStrip = useMemo(() => {
    if (!qfOpen || qfPattern.length === 0) return null;
    const rows = visibleRows.slice(0, QF_STRIP_ROWS);
    if (rows.length === 0) return null;
    const byRow = rows.map(() => new Map<number, Brush>());
    const at = new Map(rows.map((r, i) => [r.employee_id, i]));
    runRotation(rows, cal, qfPlan, (row, day, b) => {
      const i = at.get(row.employee_id);
      if (i != null) byRow[i]?.set(day.day, b);
    });
    return {
      rows,
      byRow,
      days: cal.filter((c) => c.day >= qfPlan.startDay).slice(0, QF_STRIP_DAYS),
    };
  }, [qfOpen, qfPattern.length, visibleRows, cal, qfPlan]);

  const commitRef = useRef<(rect: DragRect) => void>(() => undefined);
  commitRef.current = (rect: DragRect) => {
    if (!brush || locked) return;
    const rA = Math.min(rect.r0, rect.r1),
      rB = Math.max(rect.r0, rect.r1);
    const cA = Math.min(rect.c0, rect.c1),
      cB = Math.max(rect.c0, rect.c1);
    const hits: { row: ShiftPlanRow; day: ShiftPlanDay }[] = [];
    for (let r = rA; r <= rB; r += 1) {
      const row = visibleRows[r];
      if (!row) continue;
      for (let c = cA; c <= cB; c += 1) {
        const day = cal[c];
        if (day) hits.push({ row, day });
      }
    }
    if (!hits.length) return;
    const b = brush;
    setPending((prev) => {
      const next = new Map(prev);
      for (const h of hits) applyBrush(next, h.row, h.day, b);
      return next;
    });
    // Ô vừa sửa lại thì gỡ cờ "bị từ chối" của lần lưu trước.
    setRejects((prev) => {
      if (!prev.size) return prev;
      const next = new Map(prev);
      for (const h of hits) next.delete(cellKey(h.row.employee_id, h.day.date));
      return next.size === prev.size ? prev : next;
    });
  };

  const dragRef = useRef<DragRect | null>(null);
  dragRef.current = drag;
  useEffect(() => {
    function onUp() {
      const rect = dragRef.current;
      if (rect) commitRef.current(rect);
      setDrag(null);
    }
    window.addEventListener("mouseup", onUp);
    return () => window.removeEventListener("mouseup", onUp);
  }, []);

  // Phím tắt: 1..9 chọn ca thứ N · 0 = Nghỉ · Backspace/Delete = về mặc định · Esc = bỏ bút.
  useEffect(() => {
    if (locked || qfOpen) return; // đang mở modal Áp nhanh thì phím số là để nhập, không phải đổi bút
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable)
      )
        return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Escape") {
        setBrush(null);
        return;
      }
      if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        setBrush({ kind: "inherit" });
        return;
      }
      if (e.key === "0") {
        setBrush({ kind: "off" });
        return;
      }
      if (/^[1-9]$/.test(e.key)) {
        const s = paintShifts[Number(e.key) - 1];
        if (s) setBrush({ kind: "shift", shiftId: s.id });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [locked, paintShifts, qfOpen]);

  // Chặn mất dữ liệu khi còn nháp.
  useEffect(() => {
    if (!dirtyCount) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirtyCount]);

  useEffect(() => {
    if (histFor == null) {
      setHist(null);
      setHistErr(null);
      return;
    }
    let alive = true;
    api.employees
      .shiftHistory(token, histFor.id)
      .then((r) => {
        if (alive) setHist(r.items);
      })
      .catch(() => {
        if (alive) setHist([]);
      });
    return () => {
      alive = false;
    };
  }, [token, histFor, histNonce]);

  async function removeMilestone(assignmentId: number) {
    if (histFor == null) return;
    setHistBusy(true);
    setHistErr(null);
    try {
      await api.employees.deleteShiftAssignment(
        token,
        histFor.id,
        assignmentId,
      );
      setConfirmDel(null);
      setHistNonce((n) => n + 1); // nạp lại lịch sử
      await reload(); // ca nền đổi ⇒ lưới phải vẽ lại
    } catch (e) {
      setHistErr(e instanceof Error ? e.message : "Không xóa được mốc này.");
    } finally {
      setHistBusy(false);
    }
  }

  // Mở form đặt ca nền: mặc định áp dụng từ NGÀY 1 của tháng đang xem.
  function openBase(ids: number[], label: string, current?: number | null) {
    setBaseFrom(`${year}-${String(month).padStart(2, "0")}-01`);
    setBaseShift(current ?? "");
    setBaseMsg(null);
    setBaseTarget({ ids, label });
  }

  async function applyBase() {
    const ids = baseTarget?.ids ?? [];
    if (ids.length === 0) {
      setBaseMsg("Không có nhân viên nào để áp dụng.");
      return;
    }
    setBaseBusy(true);
    setBaseMsg(null);
    try {
      const res = await api.employees.setShiftBulk(
        token,
        ids,
        typeof baseShift === "number" ? baseShift : null,
        baseFrom,
      );
      // Ca nền đổi ⇒ mọi ô đang "kế thừa" phải vẽ lại theo ca mới.
      await reload();
      if (res.failed.length === 0 && res.adjusted === 0) {
        setBaseTarget(null);
      } else {
        setBaseMsg(
          [
            `Đã đặt ca nền cho ${res.updated} nhân viên.`,
            res.adjusted
              ? `${res.adjusted} người vào làm sau ngày bạn chọn — mốc của họ tự lùi về đúng ngày vào làm.`
              : null,
            res.failed.length
              ? `${res.failed.length} người bị bỏ qua: ${[...new Set(res.failed.map((f) => f.reason))].join(" · ")}`
              : null,
          ]
            .filter(Boolean)
            .join(" "),
        );
      }
    } catch (e) {
      setBaseMsg(e instanceof Error ? e.message : "Không đặt được ca nền.");
    } finally {
      setBaseBusy(false);
    }
  }

  function guarded(run: () => void) {
    if (dirtyCount) setGuard({ run });
    else run();
  }
  function stepMonth(delta: number) {
    guarded(() =>
      setYm((cur) => {
        const m = cur.month + delta;
        if (m < 1) return { year: cur.year - 1, month: 12 };
        if (m > 12) return { year: cur.year + 1, month: 1 };
        return { year: cur.year, month: m };
      }),
    );
  }

  async function save() {
    const items = Array.from(pending.values());
    if (!items.length) return;
    setSaving(true);
    setResult(null);
    setError(null);
    let saved = 0;
    let cleared = 0;
    const rejected: {
      employee_id: number | null;
      date: string;
      reason: string;
    }[] = [];
    try {
      for (let i = 0; i < items.length; i += SAVE_CHUNK) {
        const lot = items.slice(i, i + SAVE_CHUNK);
        setProgress({
          done: Math.min(i + lot.length, items.length),
          total: items.length,
        });
        const out = await api.attendance.saveShiftPlan(token, year, month, lot);
        saved += out.saved;
        cleared += out.cleared;
        rejected.push(...out.rejected);
      }
      const rejMap = new Map(
        rejected.map((r) => [cellKey(r.employee_id ?? -1, r.date), r.reason]),
      );
      setRejects(rejMap);
      // Ô bị từ chối Ở LẠI trạng thái bẩn — tuyệt đối không im lặng bỏ qua.
      setPending((prev) => {
        const next = new Map<string, ShiftPlanPatchItem>();
        prev.forEach((v, k) => {
          if (rejMap.has(k)) next.set(k, v);
        });
        return next;
      });
      setResult({ saved, cleared, rejected: rejected.length });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu phân ca.");
      await reload();
    } finally {
      setSaving(false);
      setProgress(null);
    }
  }

  const rejectReasons = useMemo(
    () => Array.from(new Set(rejects.values())),
    [rejects],
  );

  function brushLabel(b: Brush): string {
    if (b.kind === "off") return "Nghỉ";
    if (b.kind === "inherit") return "Mặc định";
    return shiftMeta.get(b.shiftId)?.code ?? "?";
  }
  function brushCode(b: Brush): string {
    if (b.kind === "off") return "–";
    if (b.kind === "inherit") return "⌫";
    return shiftMeta.get(b.shiftId)?.code ?? "?";
  }
  function brushTone(b: Brush): string {
    return b.kind === "shift"
      ? (shiftMeta.get(b.shiftId)?.tone ?? "steel")
      : "rest";
  }

  // --- Áp nhanh --------------------------------------------------------------
  const qf222 = paintShifts.length >= 3 ? paintShifts.slice(0, 3) : null; // 3 kíp đầu theo thứ tự bút ca
  const qfWeekly = paintShifts.length >= 2 ? paintShifts : null;
  const qfLen = qfPattern.length;
  // Lệch nhiều hơn số bước của chu kỳ thì quay vòng — nói thẳng ra để khỏi tưởng máy ăn gian.
  const qfEffPhase =
    qfLen > 0 ? ((Math.trunc(qfPhase) % qfLen) + qfLen) % qfLen : 0;

  function openQuickFill() {
    // Ca đã ngưng hoạt động thì gỡ khỏi mẫu — tô vào chỉ để server từ chối.
    const live = new Set(paintShifts.map((s) => s.id));
    setQfPattern((p) =>
      p.filter((b) => b.kind !== "shift" || live.has(b.shiftId)),
    );
    setQfStart((d) => Math.min(Math.max(1, d), Math.max(1, cal.length)));
    setQfOpen(true);
  }

  function applyQuickFill() {
    if (locked || !qfDraft) return;
    setPending(qfDraft.next);
    // Ô vừa tô lại thì gỡ cờ "bị từ chối" của lần lưu trước — giống hệt lúc tô tay.
    setRejects((prev) => {
      if (!prev.size) return prev;
      const next = new Map(prev);
      for (const k of qfDraft.touched) next.delete(k);
      return next.size === prev.size ? prev : next;
    });
    setResult(null);
    setQfOpen(false);
  }

  return (
    <div className="cc-sp">
      <div className="cc-ts-header-actions cc-sp-toolbar">
        <div className="cc-ts-filters">
          <div className="cc-sp-month">
            <button
              type="button"
              className="cc-sp-month__nav"
              onClick={() => stepMonth(-1)}
              title="Tháng trước"
              aria-label="Tháng trước"
            >
              <ChevronLeft size={15} />
            </button>
            <span className="cc-sp-month__label">
              Tháng {month}/{year}
            </span>
            <button
              type="button"
              className="cc-sp-month__nav"
              onClick={() => stepMonth(1)}
              title="Tháng sau"
              aria-label="Tháng sau"
            >
              <ChevronRight size={15} />
            </button>
          </div>
          <select
            className="cc-ts-select-dept"
            value={deptId}
            aria-label="Lọc phòng/tổ"
            onChange={(e) => {
              const v = e.target.value === "" ? "" : Number(e.target.value);
              guarded(() => setDeptId(v));
            }}
          >
            <option value="">Tất cả phòng/tổ</option>
            {depts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <div className="cc-sp-search">
            <Search size={14} aria-hidden="true" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm tên / mã NV"
              aria-label="Tìm nhân viên"
            />
          </div>
          {noDefaultCount > 0 && (
            <button
              type="button"
              className={`cc-sp-flag${onlyNoDefault ? " is-on" : ""}`}
              aria-pressed={onlyNoDefault}
              onClick={() => setOnlyNoDefault((v) => !v)}
              title="Những người chưa có ca nền — họ CHƯA CHẤM CÔNG ĐƯỢC cho tới khi được đặt ca"
            >
              <AlertTriangle size={13} aria-hidden="true" /> Chưa có ca (
              {noDefaultCount})
            </button>
          )}
        </div>
        <div className="cc-ts-actions">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={locked || visibleRows.length === 0}
            onClick={() =>
              openBase(
                visibleRows.map((r) => r.employee_id),
                `tất cả ${visibleRows.length} nhân viên đang hiển thị`,
              )
            }
            title="Đặt ca nền cho TẤT CẢ nhân viên đang hiển thị (bấm ô 'Ca nền' của một hàng để đặt riêng cho người đó)"
          >
            <Users size={14} /> Đặt ca chính cho tất cả…
          </button>
          {SHOW_QUICK_FILL && (
            <button
              type="button"
              className="btn btn--ghost"
              disabled={locked || visibleRows.length === 0}
              onClick={openQuickFill}
              title="Rải sẵn cả tháng theo một chu kỳ lặp (vd 2-2-2), các kíp tự lệch nhau — khỏi tô tay từng ô"
            >
              <Repeat size={14} /> Áp nhanh…
            </button>
          )}
          <div className="cc-sp-density" role="group" aria-label="Mật độ lưới">
            <button
              type="button"
              className={density === "compact" ? "is-on" : ""}
              aria-pressed={density === "compact"}
              onClick={() => setDensity("compact")}
            >
              Gọn
            </button>
            <button
              type="button"
              className={density === "roomy" ? "is-on" : ""}
              aria-pressed={density === "roomy"}
              onClick={() => setDensity("roomy")}
            >
              Thoáng
            </button>
          </div>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => void reload()}
            disabled={loading || saving}
            title="Tải lại lưới"
          >
            <RefreshCw
              size={14}
              className={loading ? "cc-animate-spin" : undefined}
            />{" "}
            Tải lại
          </button>
        </div>
      </div>

      {locked && (
        <div className="banner banner--warn cc-sp-banner">
          <span>
            <Lock size={13} aria-hidden="true" /> Kỳ công tháng {month}/{year}{" "}
            đã chốt — mở lại kỳ mới sửa được phân ca.
          </span>
        </div>
      )}
      {error && (
        <div className="banner banner--error cc-sp-banner">
          <span>{error}</span>
        </div>
      )}
      {result && (
        <div className="banner banner--success cc-sp-banner">
          <span>
            Đã lưu {result.saved} ô
            {result.cleared ? ` · gỡ ${result.cleared} ô về mặc định` : ""} ·{" "}
            {result.rejected} ô bị từ chối
          </span>
        </div>
      )}
      {rejectReasons.length > 0 && (
        <div className="banner banner--warn cc-sp-banner">
          <span>
            Ô bị từ chối vẫn còn đánh dấu trên lưới (viền cảnh báo) — di chuột
            vào ô để xem lý do. {rejectReasons.join(" · ")}
          </span>
        </div>
      )}

      {!locked && (
        <div className="cc-sp-brush" role="toolbar" aria-label="Bút ca">
          <span className="cc-sp-brush__label">Bút ca</span>
          {paintShifts.map((s, i) => {
            const meta = shiftMeta.get(s.id);
            const on = brush?.kind === "shift" && brush.shiftId === s.id;
            return (
              <button
                key={s.id}
                type="button"
                aria-pressed={on}
                className={`cc-sp-pill cc-sp-pill--${meta?.tone ?? "steel"} ${on ? "is-on" : ""}`}
                title={`${meta?.title ?? s.name}${i < 9 ? ` · phím ${i + 1}` : ""}`}
                onClick={() =>
                  setBrush(on ? null : { kind: "shift", shiftId: s.id })
                }
              >
                <span className="cc-sp-pill__code">{meta?.code ?? "?"}</span>
                <span className="cc-sp-pill__name">{s.name}</span>
              </button>
            );
          })}
          <button
            type="button"
            aria-pressed={brush?.kind === "off"}
            className={`cc-sp-pill cc-sp-pill--rest ${brush?.kind === "off" ? "is-on" : ""}`}
            title="Nghỉ luân phiên — dấu kế hoạch, không chặn chấm công, không sinh hệ số tiền · phím 0"
            onClick={() =>
              setBrush(brush?.kind === "off" ? null : { kind: "off" })
            }
          >
            <span className="cc-sp-pill__code">–</span>
            <span className="cc-sp-pill__name">Nghỉ</span>
          </button>
          <button
            type="button"
            aria-pressed={brush?.kind === "inherit"}
            className={`cc-sp-pill cc-sp-pill--erase ${brush?.kind === "inherit" ? "is-on" : ""}`}
            title="Xoá ô đã khai tay → về ca mặc định · phím Backspace"
            onClick={() =>
              setBrush(brush?.kind === "inherit" ? null : { kind: "inherit" })
            }
          >
            <Eraser size={13} aria-hidden="true" />
            <span className="cc-sp-pill__name">Mặc định ⌫</span>
          </button>
          <span className="cc-sp-brush__hint">
            {brush
              ? `Đang cầm bút "${brushLabel(brush)}" — click 1 ô hoặc kéo để tô cả vùng · Esc bỏ bút`
              : "Chọn 1 bút rồi click/kéo trên lưới · phím 1–9 chọn ca · 0 nghỉ · ⌫ mặc định"}
          </span>
        </div>
      )}

      <div className="cc-sp-legend">
        <span className="cc-sp-lg cc-sp-lg--ghost">Kế thừa ca nền</span>
        <span className="cc-sp-lg cc-sp-lg--hand">Khai tay</span>
        <span className="cc-sp-lg cc-sp-lg--rest">Nghỉ theo lịch</span>
        <span className="cc-sp-lg cc-sp-lg--hol">Lễ</span>
        <span className="cc-sp-lg cc-sp-lg--make">Làm bù</span>
        <span className="cc-sp-lg cc-sp-lg--x1">Nghỉ 1×</span>
        <span className="cc-sp-lg cc-sp-lg--dirty">Chưa lưu</span>
      </div>

      {loading && <p className="ns__empty">Đang tải lưới phân ca…</p>}
      {!loading && data && (
        <div className="cc-timesheet-scroll-container cc-sp-scroll">
          <table
            className={`cc-timesheet-table cc-sp-table ${density === "roomy" ? "cc-sp-table--roomy" : ""} ${drag ? "is-dragging" : ""}`}
          >
            <thead>
              <tr>
                <th className="cc-sp-col-name">Nhân viên</th>
                <th
                  className="cc-sp-col-base"
                  title="Ca mặc định (nền) đang áp dụng cho nhân viên"
                >
                  Ca nền
                </th>
                {cal.map((c) => {
                  const restDay = c.weekday === 6 || !c.is_working;
                  const cls = [
                    "cc-sp-hdr",
                    c.weekday === 0 ? "cc-sp-hdr--wk" : "",
                    restDay ? "cc-sp-hdr--we" : "",
                    c.special_kind === "off" ? "cc-sp-hdr--hol" : "",
                    c.special_kind === "work" ? "cc-sp-hdr--make" : "",
                    c.special_kind === "off1x" ? "cc-sp-hdr--x1" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  const tip = [
                    `${getWeekdayLabel(year, month, c.day)} ${fmtYmd(c.date)}`,
                    c.name,
                    c.special_kind === "off1x"
                      ? "Nghỉ không lương — đi làm hưởng 1× lương chính"
                      : null,
                    c.special_kind === "work" ? "Ngày làm bù" : null,
                  ]
                    .filter(Boolean)
                    .join(" · ");
                  return (
                    <th key={c.day} className={cls} title={tip} scope="col">
                      <div className="cc-sp-hdr__wd">
                        {getWeekdayLabel(year, month, c.day)}
                      </div>
                      <div className="cc-sp-hdr__d">{c.day}</div>
                      {c.special_kind === "off1x" && (
                        <div className="cc-sp-hdr__flag">1×</div>
                      )}
                    </th>
                  );
                })}
                <th
                  className="cc-sp-col-bar"
                  title="Tỷ trọng ca trong tháng của từng nhân viên"
                >
                  Ca/tháng
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, ri) => {
                const base = inheritInfo.get(row.employee_id)?.base ?? null;
                const baseMeta = base != null ? shiftMeta.get(base) : undefined;
                const counts = new Map<number, number>();
                let restDays = 0;
                grid[ri]?.forEach((eff) => {
                  if (eff.off) restDays += 1;
                  else if (eff.shiftId != null)
                    counts.set(eff.shiftId, (counts.get(eff.shiftId) ?? 0) + 1);
                });
                const segs = orderedShifts
                  .filter((s) => (counts.get(s.id) ?? 0) > 0)
                  .map((s) => ({
                    key: `s${s.id}`,
                    tone: shiftMeta.get(s.id)?.tone ?? "steel",
                    n: counts.get(s.id) ?? 0,
                  }));
                const barTitle =
                  [
                    ...orderedShifts
                      .filter((s) => (counts.get(s.id) ?? 0) > 0)
                      .map(
                        (s) =>
                          `${shiftMeta.get(s.id)?.name ?? s.name}: ${counts.get(s.id)}`,
                      ),
                    restDays ? `Nghỉ: ${restDays}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Chưa có ca nào trong tháng";
                const total = Math.max(1, cal.length);
                return (
                  <tr
                    key={row.employee_id}
                    className={row.no_default ? "cc-sp-row--nodef" : ""}
                  >
                    <td className="cc-sp-col-name">
                      <div className="cc-name-cell-wrapper">
                        <span className="cc-name-avatar">
                          {getInitials(row.employee_name)}
                        </span>
                        <span className="cc-sp-who">
                          <button
                            type="button"
                            className="cc-sp-who__name cc-sp-who__link"
                            title={`${row.employee_name} — xem lịch sử đổi ca nền`}
                            onClick={() =>
                              setHistFor({
                                id: row.employee_id,
                                name: row.employee_name,
                              })
                            }
                          >
                            {row.employee_name}
                          </button>
                          <span className="cc-sp-who__sub">
                            <span className="cc-sp-who__code">
                              {row.employee_code ?? "—"}
                            </span>
                            {row.no_default && (
                              <span
                                className="ns-badge ns-badge--warn cc-sp-nodef"
                                title="Nhân viên chưa được gán ca mặc định — khai ca trên lưới hoặc gán ở khối C · Ca mặc định"
                              >
                                Chưa có ca
                              </span>
                            )}
                          </span>
                        </span>
                      </div>
                    </td>
                    <td className="cc-sp-col-base">
                      <button
                        type="button"
                        className="cc-sp-basebtn"
                        disabled={locked}
                        onClick={() =>
                          openBase([row.employee_id], row.employee_name, base)
                        }
                        title={
                          `Đặt ca nền riêng cho ${row.employee_name}` +
                          (baseMeta
                            ? ` — hiện: ${baseMeta.title}`
                            : " — hiện chưa có ca nền")
                        }
                      >
                        {baseMeta ? (
                          <span
                            className={`cc-sp-chip cc-sp-chip--${baseMeta.tone} is-ghost`}
                          >
                            {baseMeta.code}
                          </span>
                        ) : (
                          <span className="cc-sp-chip cc-sp-chip--none is-ghost">
                            ·
                          </span>
                        )}
                      </button>
                    </td>
                    {cal.map((c, ci) => {
                      const key = cellKey(row.employee_id, c.date);
                      const inRect =
                        !!drag &&
                        ri >= Math.min(drag.r0, drag.r1) &&
                        ri <= Math.max(drag.r0, drag.r1) &&
                        ci >= Math.min(drag.c0, drag.c1) &&
                        ci <= Math.max(drag.c0, drag.c1);
                      let eff = grid[ri]?.[ci] ?? {
                        shiftId: null,
                        hand: false,
                        off: false,
                      };
                      if (inRect && brush) {
                        if (brush.kind === "off")
                          eff = { shiftId: null, hand: true, off: true };
                        else if (brush.kind === "inherit")
                          eff = {
                            shiftId:
                              inheritInfo.get(row.employee_id)?.inherit[ci] ??
                              null,
                            hand: false,
                            off: false,
                          };
                        else
                          eff = {
                            shiftId: brush.shiftId,
                            hand: true,
                            off: false,
                          };
                      }
                      const meta =
                        eff.shiftId != null
                          ? shiftMeta.get(eff.shiftId)
                          : undefined;
                      const reason = rejects.get(key);
                      const restDay = c.weekday === 6 || !c.is_working;
                      const cls = [
                        "cc-day-cell",
                        "cc-sp-cell",
                        c.weekday === 0 ? "cc-sp-cell--wk" : "",
                        restDay ? "cc-sp-cell--we" : "",
                        c.special_kind === "off" || c.special_kind === "off1x"
                          ? "cc-sp-cell--hol"
                          : "",
                        c.special_kind === "work" ? "cc-sp-cell--make" : "",
                        eff.off ? "cc-sp-cell--rest" : "",
                        pending.has(key) ? "is-dirty" : "",
                        reason ? "is-rejected" : "",
                        inRect ? "is-preview" : "",
                        paintable ? "is-paintable" : "",
                      ]
                        .filter(Boolean)
                        .join(" ");
                      const dayTip = [
                        `${getWeekdayLabel(year, month, c.day)} ${fmtYmd(c.date)}`,
                        c.name,
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      const chipTip = [
                        eff.off
                          ? "Nghỉ theo lịch (dấu kế hoạch — không chặn chấm công, không sinh hệ số)"
                          : (meta?.title ?? "Chưa có ca"),
                        eff.hand ? "khai tay" : "kế thừa ca nền",
                        dayTip,
                        c.special_kind === "off1x"
                          ? "Nghỉ không lương — đi làm hưởng 1× lương chính"
                          : null,
                        reason ? `TỪ CHỐI: ${reason}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      return (
                        <td
                          key={c.day}
                          className={cls}
                          title={dayTip}
                          onMouseDown={
                            paintable
                              ? (e) => {
                                  e.preventDefault();
                                  setDrag({ r0: ri, c0: ci, r1: ri, c1: ci });
                                }
                              : undefined
                          }
                          onMouseEnter={
                            paintable
                              ? () =>
                                  setDrag((d) =>
                                    d ? { ...d, r1: ri, c1: ci } : d,
                                  )
                              : undefined
                          }
                        >
                          {eff.off ? (
                            <span className="cc-sp-rest" title={chipTip}>
                              –
                            </span>
                          ) : meta ? (
                            <span
                              className={`cc-sp-chip cc-sp-chip--${meta.tone} ${eff.hand ? "is-hand" : "is-ghost"}`}
                              title={chipTip}
                            >
                              {meta.code}
                            </span>
                          ) : (
                            <span
                              className="cc-sp-chip cc-sp-chip--none is-ghost"
                              title={chipTip}
                            >
                              ·
                            </span>
                          )}
                        </td>
                      );
                    })}
                    <td className="cc-sp-col-bar">
                      <div className="cc-sp-bar" title={barTitle}>
                        {segs.map((s) => (
                          <span
                            key={s.key}
                            className={`cc-sp-bar__seg cc-sp-bar__seg--${s.tone}`}
                            style={{ width: `${(s.n / total) * 100}%` }}
                          />
                        ))}
                        {restDays > 0 && (
                          <span
                            className="cc-sp-bar__seg cc-sp-bar__seg--rest"
                            style={{ width: `${(restDays / total) * 100}%` }}
                          />
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={cal.length + 3} className="ns__empty">
                    Không có nhân viên phù hợp bộ lọc.
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr>
                <td className="cc-sp-col-name cc-sp-foot__label">Người / ca</td>
                <td className="cc-sp-col-base" />
                {cal.map((c, ci) => {
                  const f = footCounts[ci];
                  const parts = orderedShifts.filter(
                    (s) => (f?.byShift.get(s.id) ?? 0) > 0,
                  );
                  const tip =
                    [
                      ...parts.map(
                        (s) =>
                          `${shiftMeta.get(s.id)?.name ?? s.name}: ${f.byShift.get(s.id)}`,
                      ),
                      f?.off ? `Nghỉ: ${f.off}` : null,
                      f?.none ? `Chưa có ca: ${f.none}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Không có ai";
                  return (
                    <td
                      key={c.day}
                      className={`cc-sp-foot ${c.weekday === 0 ? "cc-sp-cell--wk" : ""}`}
                      title={tip}
                    >
                      {parts.map((s, i) => (
                        <span key={s.id}>
                          {i > 0 && <span className="cc-sp-foot__sep">·</span>}
                          <span
                            className={`cc-sp-foot__n cc-sp-foot__n--${shiftMeta.get(s.id)?.tone ?? "steel"}`}
                          >
                            {f.byShift.get(s.id)}
                          </span>
                        </span>
                      ))}
                      {!!f?.off && (
                        <span>
                          {parts.length > 0 && (
                            <span className="cc-sp-foot__sep">·</span>
                          )}
                          <span className="cc-sp-foot__n cc-sp-foot__n--rest">
                            {f.off}
                          </span>
                        </span>
                      )}
                      {!parts.length && !f?.off && (
                        <span className="cc-sp-foot__n cc-sp-foot__n--zero">
                          —
                        </span>
                      )}
                    </td>
                  );
                })}
                <td className="cc-sp-col-bar" />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {!locked && (
        <div className="cc-sp-actionbar">
          <span
            className={`cc-sp-dirty ${dirtyCount ? "is-on" : ""}`}
            aria-live="polite"
          >
            <span className="cc-sp-dirty__dot" aria-hidden="true" />
            {dirtyCount
              ? `${dirtyCount} thay đổi chưa lưu`
              : "Chưa có thay đổi"}
          </span>
          {progress && (
            <span className="cc-sp-progress">
              Đang lưu {progress.done}/{progress.total}…
            </span>
          )}
          <span className="cc-sp-actionbar__gap" />
          <button
            type="button"
            className="btn btn--ghost"
            disabled={!dirtyCount || saving}
            onClick={() => {
              setPending(new Map());
              setRejects(new Map());
              setResult(null);
            }}
          >
            <Undo2 size={14} /> Hoàn tác tất cả
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!dirtyCount || saving}
            onClick={() => void save()}
          >
            <Save size={14} /> {saving ? "Đang lưu…" : "Lưu"}
          </button>
        </div>
      )}

      {baseTarget && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box" style={{ maxWidth: "460px" }}>
            <header className="ns-modal__head">
              <div className="cc-modal-title-group">
                <h2>Đặt ca nền</h2>
                <span className="cc-modal-subtitle">
                  Áp cho: {baseTarget.label}
                </span>
              </div>
              <button
                className="ns-modal__x"
                onClick={() => setBaseTarget(null)}
                disabled={baseBusy}
              >
                ×
              </button>
            </header>
            <div className="ns-modal__body">
              <p className="cc-note">
                Ca nền áp dụng{" "}
                <strong>từ ngày đã chọn trở về sau, cho MỌI tháng</strong> —
                khác với tô ca trên lưới (chỉ đúng ngày đã tô). Ngày nào không
                khai trên lưới thì dùng ca nền này.
              </p>
              <label className="cc-sp-basepop__row">
                <span>Ca</span>
                <select
                  value={baseShift}
                  onChange={(e) =>
                    setBaseShift(
                      e.target.value === ""
                        ? ""
                        : e.target.value === "none"
                          ? "none"
                          : Number(e.target.value),
                    )
                  }
                >
                  <option value="">— chọn ca —</option>
                  {paintShifts.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.start_time}–{s.end_time})
                    </option>
                  ))}
                  <option value="none">— bỏ gán ca nền —</option>
                </select>
              </label>
              <label className="cc-sp-basepop__row">
                <span>Áp dụng từ</span>
                <input
                  type="date"
                  value={baseFrom}
                  onChange={(e) => setBaseFrom(e.target.value)}
                />
              </label>
              {baseShift === "none" && (
                <p className="cc-sp-basepop__msg">
                  Bỏ ca nền = những ngày không khai trên lưới sẽ{" "}
                  <strong>không có ca</strong>, và người đó
                  <strong> không chấm công được</strong>. Chỉ dùng khi thực sự
                  muốn vậy.
                </p>
              )}
              {baseMsg && <p className="cc-sp-basepop__msg">{baseMsg}</p>}
            </div>
            <footer
              className="ns-modal__foot"
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
              }}
            >
              <button
                className="btn btn--ghost"
                onClick={() => setBaseTarget(null)}
                disabled={baseBusy}
              >
                Hủy
              </button>
              <button
                className="btn btn--primary"
                onClick={() => void applyBase()}
                disabled={baseBusy || baseShift === "" || !baseFrom}
              >
                {baseBusy
                  ? "Đang áp dụng…"
                  : baseShift === "none"
                    ? "Bỏ gán ca nền"
                    : "Áp dụng"}
              </button>
            </footer>
          </div>
        </div>
      )}

      {qfOpen && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box cc-qf-box">
            <header className="ns-modal__head">
              <div className="cc-modal-title-group">
                <h2>Áp nhanh mẫu xoay ca</h2>
                <span className="cc-modal-subtitle">
                  Tháng {month}/{year} · {visibleRows.length} nhân viên đang
                  hiển thị
                </span>
              </div>
              <button className="ns-modal__x" onClick={() => setQfOpen(false)}>
                ×
              </button>
            </header>
            <div className="ns-modal__body cc-qf-body">
              <p className="cc-note">
                Rải sẵn cả tháng theo một chu kỳ lặp đi lặp lại, thay cho việc
                tô tay từng ô. Máy chỉ ghi vào nháp —{" "}
                <strong>áp xong vẫn phải bấm Lưu</strong>.
              </p>

              {(qf222 || qfWeekly) && (
                <div className="cc-qf-block">
                  <div className="cc-qf-head">Mẫu có sẵn</div>
                  <div className="cc-qf-row">
                    {qf222 && (
                      <button
                        type="button"
                        className="cc-qf-preset"
                        title="2 ngày ca đầu → 2 ngày ca giữa → 2 ngày ca khuya, người sau lệch 2 ngày so với người trước"
                        onClick={() => {
                          const [a, b, c] = qf222;
                          if (!a || !b || !c) return;
                          setQfPattern(
                            [a, a, b, b, c, c].map((s) => ({
                              kind: "shift",
                              shiftId: s.id,
                            })),
                          );
                          setQfPhase(2);
                        }}
                      >
                        <span className="cc-qf-preset__name">
                          2-2-2 (3 kíp)
                        </span>
                        <span className="cc-qf-preset__sub">
                          {qf222
                            .map((s) => shiftMeta.get(s.id)?.code ?? "?")
                            .join(" · ")}{" "}
                          · lệch 2 ngày
                        </span>
                      </button>
                    )}
                    {qfWeekly && (
                      <button
                        type="button"
                        className="cc-qf-preset"
                        title="Mỗi ca làm trọn 7 ngày rồi đổi, người sau lệch nguyên 1 tuần"
                        onClick={() => {
                          const p: Brush[] = [];
                          for (const s of qfWeekly)
                            for (let k = 0; k < 7; k += 1)
                              p.push({ kind: "shift", shiftId: s.id });
                          setQfPattern(p);
                          setQfPhase(7);
                        }}
                      >
                        <span className="cc-qf-preset__name">Xoay tuần</span>
                        <span className="cc-qf-preset__sub">
                          mỗi ca 7 ngày · lệch 1 tuần
                        </span>
                      </button>
                    )}
                    <span className="cc-note">
                      Bấm xong vẫn sửa lại được ở dưới.
                    </span>
                  </div>
                </div>
              )}

              <div className="cc-qf-block">
                <div className="cc-qf-head">
                  Chu kỳ lặp — mỗi ô là một ngày
                  {qfLen > 0 && (
                    <span className="cc-qf-head__n">{qfLen} ngày/vòng</span>
                  )}
                </div>
                <div className="cc-qf-chips">
                  {qfLen === 0 && (
                    <span className="cc-qf-chips__empty">
                      Chưa có ngày nào — bấm ca ở dưới để thêm
                    </span>
                  )}
                  {qfPattern.map((b, i) => (
                    <span
                      key={i}
                      className={`cc-qf-chip cc-qf-chip--${brushTone(b)}`}
                      title={`Ngày thứ ${i + 1} của vòng · ${brushLabel(b)}`}
                    >
                      {brushCode(b)}
                    </span>
                  ))}
                </div>
                <div className="cc-qf-row">
                  <span className="cc-qf-row__label">Thêm ngày</span>
                  {paintShifts.map((s) => {
                    const meta = shiftMeta.get(s.id);
                    return (
                      <button
                        key={s.id}
                        type="button"
                        className={`cc-sp-pill cc-sp-pill--${meta?.tone ?? "steel"}`}
                        title={meta?.title ?? s.name}
                        onClick={() =>
                          setQfPattern((p) => [
                            ...p,
                            { kind: "shift", shiftId: s.id },
                          ])
                        }
                      >
                        <span className="cc-sp-pill__code">
                          {meta?.code ?? "?"}
                        </span>
                        <span className="cc-sp-pill__name">{s.name}</span>
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    className="cc-sp-pill"
                    title="Ngày nghỉ luân phiên trong chu kỳ"
                    onClick={() => setQfPattern((p) => [...p, { kind: "off" }])}
                  >
                    <span className="cc-sp-pill__code">–</span>
                    <span className="cc-sp-pill__name">Nghỉ</span>
                  </button>
                  <span className="cc-qf-row__gap" />
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={qfLen === 0}
                    onClick={() => setQfPattern((p) => p.slice(0, -1))}
                  >
                    Xoá ngày cuối
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={qfLen === 0}
                    onClick={() => setQfPattern([])}
                  >
                    Xoá hết
                  </button>
                </div>
              </div>

              <div className="cc-qf-block">
                <div className="cc-qf-opts">
                  <label className="cc-qf-field">
                    <span>Bắt đầu từ ngày</span>
                    <input
                      type="number"
                      min={1}
                      max={Math.max(1, cal.length)}
                      value={qfStart}
                      onChange={(e) =>
                        setQfStart(
                          clampNum(e.target.value, 1, Math.max(1, cal.length)),
                        )
                      }
                    />
                  </label>
                  <label className="cc-qf-field">
                    <span>Lệch pha giữa các nhân viên</span>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      value={qfPhase}
                      onChange={(e) =>
                        setQfPhase(clampNum(e.target.value, 0, 30))
                      }
                    />
                  </label>
                </div>
                <p className="cc-note">
                  Người thứ 2 bắt đầu muộn hơn người thứ nhất bấy nhiêu bước —
                  để các kíp phủ kín mọi ca. Để <strong>0</strong> thì cả tổ
                  chạy y hệt nhau.
                  {qfLen > 0 &&
                    qfEffPhase !== qfPhase &&
                    ` Vòng chỉ có ${qfLen} ngày nên lệch ${qfPhase} thực ra bằng lệch ${qfEffPhase}.`}
                </p>
                <label className="cc-qf-check">
                  <input
                    type="checkbox"
                    checked={qfSkipRest}
                    onChange={(e) => setQfSkipRest(e.target.checked)}
                  />
                  <span>
                    Không tô vào ngày nghỉ tuần &amp; ngày lễ
                    <em>
                      Xưởng 3 ca chạy liên tục thì cứ để TẮT. Bật thì ngày nghỉ
                      bỏ trắng và không tiêu một bước của chu kỳ, nên vòng xoay
                      không bị lệch.
                    </em>
                  </span>
                </label>
              </div>

              {qfStrip && (
                <div className="cc-qf-block">
                  <div className="cc-qf-head">
                    Xem trước {qfStrip.rows.length} người đầu ·{" "}
                    {qfStrip.days.length} ngày đầu
                  </div>
                  <div className="cc-qf-strip">
                    <div className="cc-qf-strip__row cc-qf-strip__row--head">
                      <span className="cc-qf-strip__who" />
                      {qfStrip.days.map((c) => (
                        <span key={c.day} className="cc-qf-strip__d">
                          {c.day}
                        </span>
                      ))}
                    </div>
                    {qfStrip.rows.map((r, i) => (
                      <div key={r.employee_id} className="cc-qf-strip__row">
                        <span
                          className="cc-qf-strip__who"
                          title={r.employee_name}
                        >
                          {r.employee_name}
                        </span>
                        {qfStrip.days.map((c) => {
                          const b = qfStrip.byRow[i]?.get(c.day);
                          if (!b)
                            return (
                              <span
                                key={c.day}
                                className="cc-qf-strip__c cc-qf-strip__c--skip"
                                title="Bỏ trắng"
                              >
                                ·
                              </span>
                            );
                          return (
                            <span
                              key={c.day}
                              className={`cc-qf-strip__c cc-qf-chip--${brushTone(b)}`}
                              title={`Ngày ${c.day} · ${brushLabel(b)}`}
                            >
                              {brushCode(b)}
                            </span>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className="cc-qf-sum">
                Áp cho <strong>{visibleRows.length} nhân viên</strong> đang hiển
                thị · từ ngày <strong>{qfPlan.startDay}</strong> ·{" "}
                <strong>{qfDraft?.changed ?? 0} ô</strong> sẽ đổi
              </p>
              {qfLen > 0 &&
                visibleRows.length > 0 &&
                qfDraft?.changed === 0 && (
                  <p className="cc-sp-basepop__msg">
                    Mẫu này trùng đúng thứ lưới đang có — áp vào cũng không đổi
                    ô nào.
                  </p>
                )}
            </div>
            <footer
              className="ns-modal__foot"
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
              }}
            >
              <button
                className="btn btn--ghost"
                onClick={() => setQfOpen(false)}
              >
                Hủy
              </button>
              <button
                className="btn btn--primary"
                onClick={applyQuickFill}
                disabled={locked || qfLen === 0 || visibleRows.length === 0}
              >
                Áp vào nháp
              </button>
            </footer>
          </div>
        </div>
      )}

      {histFor && (
        <div
          className="cc-sp-drawer"
          role="dialog"
          aria-label={`Lịch sử đổi ca nền — ${histFor.name}`}
        >
          <div
            className="cc-sp-drawer__backdrop"
            onClick={() => setHistFor(null)}
          />
          <div className="cc-sp-drawer__panel">
            <div className="cc-sp-drawer__head">
              <div>
                <div className="cc-sp-drawer__title">Lịch sử ca</div>
                <div className="cc-sp-drawer__sub">{histFor.name}</div>
              </div>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setHistFor(null)}
              >
                Đóng
              </button>
            </div>
            <p className="cc-note">
              Ca nền áp dụng từ ngày hiệu lực trở về sau. Ngày nào khai riêng
              trên lưới thì ô đó thắng ca nền.
            </p>
            {histErr && (
              <div className="banner banner--error">
                <span>{histErr}</span>
              </div>
            )}
            {hist == null && <p className="ns__empty">Đang tải…</p>}
            {hist?.length === 0 && (
              <p className="ns__empty">Chưa có mốc ca nền nào.</p>
            )}
            {hist && hist.length > 0 && (
              <ul className="cc-sp-hist">
                {hist.map((h) => {
                  // 3 trạng thái, KHÔNG phải 2: mốc đặt cho ngày mai không phải "đã qua".
                  const state = h.is_current
                    ? "current"
                    : h.effective_from > isoToday()
                      ? "future"
                      : "past";
                  return (
                    <li key={h.id} className={`cc-sp-hist__item is-${state}`}>
                      <div className="cc-sp-hist__body">
                        <div className="cc-sp-hist__top">
                          <span className="cc-sp-hist__name">
                            {h.shift_id == null
                              ? "Bỏ ca (không có ca)"
                              : (shiftMeta.get(h.shift_id)?.name ??
                                `Ca #${h.shift_id}`)}
                          </span>
                          <span className={`cc-sp-hist__tag is-${state}`}>
                            {state === "current"
                              ? "Đang áp dụng"
                              : state === "future"
                                ? "Sắp áp dụng"
                                : "Đã qua"}
                          </span>
                        </div>
                        <div className="cc-sp-hist__range">
                          {fmtYmd(h.effective_from)} →{" "}
                          {h.effective_to
                            ? fmtYmd(h.effective_to)
                            : "trở về sau"}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="cc-sp-hist__del"
                        disabled={histBusy}
                        onClick={() => setConfirmDel(h)}
                        title="Gỡ mốc này (dùng khi gán nhầm)"
                        aria-label="Gỡ mốc này"
                      >
                        <Trash2 size={14} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="cc-note">
              Gỡ một mốc thì ngày tháng thuộc mốc đó quay về theo{" "}
              <strong>mốc liền trước</strong>.
            </p>

            {/* Phần trên là ca nền ĐANG LÀ GÌ theo giai đoạn; phần này là AI ĐÃ ĐỔI GÌ —
                gồm cả sửa tay từng ngày trên lưới mà danh sách mốc ở trên không hề thể hiện. */}
            <ShiftChangeLogPanel token={token} employeeId={histFor.id} />
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDel}
        danger
        title="Gỡ mốc ca nền"
        message={
          confirmDel
            ? `Gỡ mốc "${
                confirmDel.shift_id == null
                  ? "Bỏ ca"
                  : (shiftMeta.get(confirmDel.shift_id)?.name ??
                    `Ca #${confirmDel.shift_id}`)
              }"` +
              ` áp dụng từ ${fmtYmd(confirmDel.effective_from)}?` +
              " Những ngày thuộc mốc này sẽ quay về theo mốc liền trước."
            : undefined
        }
        confirmLabel="Gỡ mốc"
        busy={histBusy}
        error={histErr}
        onConfirm={() => {
          if (confirmDel) void removeMilestone(confirmDel.id);
        }}
        onCancel={() => {
          setConfirmDel(null);
          setHistErr(null);
        }}
      />

      <DiscardChangesDialog
        open={!!guard}
        message={`Còn ${dirtyCount} ô phân ca chưa lưu. Rời tháng/phòng này mà không lưu?`}
        onDiscard={() => {
          const g = guard;
          setPending(new Map());
          setRejects(new Map());
          setGuard(null);
          g?.run();
        }}
        onKeepEditing={() => setGuard(null)}
      />
    </div>
  );
}

function ShiftsTab({ token }: { token: string }) {
  const [items, setItems] = useState<WorkShift[] | null>(null);
  const [editing, setEditing] = useState<WorkShift | "new" | null>(null);
  const load = useCallback(() => {
    api.attendance
      .shifts(token)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn xóa ca làm việc này?")) return;
    await api.attendance.deleteShift(token, id);
    load();
  }

  const shiftMeta = buildShiftMeta(items ?? []);
  const activeCount = (items ?? []).filter((s) => s.is_active).length;

  return (
    <div className="cc-sp-stack">
      <CollapsibleSection
        title="A · Ca làm việc"
        summary={
          items == null ? (
            "đang tải…"
          ) : (
            <>
              <span className="cc-sp-sum__txt">
                {items.length} ca
                {activeCount !== items.length
                  ? ` · ${activeCount} đang dùng`
                  : ""}
              </span>
              {[...items]
                .sort((a, b) => a.id - b.id)
                .map((s) => {
                  const m = shiftMeta.get(s.id);
                  return (
                    <span
                      key={s.id}
                      className={`cc-sp-chip cc-sp-chip--${m?.tone ?? "steel"} is-hand`}
                      title={m?.title}
                    >
                      {m?.code}
                    </span>
                  );
                })}
            </>
          )
        }
      >
        <div className="cc-toolbar">
          <button
            className="btn btn--primary"
            onClick={() => setEditing("new")}
          >
            <Plus size={14} /> Thêm ca làm việc
          </button>
        </div>

        <div className="cc-card-grid">
          {items?.map((s) => (
            <div
              key={s.id}
              className={`cc-shift-card ${s.is_overnight ? "cc-shift-card--overnight" : ""}`}
            >
              <div className="cc-shift-card-actions">
                <button
                  className="btn btn--ghost"
                  style={{ padding: "4px 6px", minWidth: "auto" }}
                  onClick={() => setEditing(s)}
                  title="Sửa ca"
                >
                  <Edit3 size={13} />
                </button>
                <button
                  className="btn btn--ghost ns-danger"
                  style={{ padding: "4px 6px", minWidth: "auto" }}
                  onClick={() => remove(s.id)}
                  title="Xóa ca"
                >
                  <Trash2 size={13} />
                </button>
              </div>

              <div className="cc-shift-card-header">
                <span className="cc-shift-name">{s.name}</span>
                <span
                  className={`cc-badge-pill ${s.is_active ? "cc-badge-pill--primary" : "cc-badge-pill--gray"}`}
                >
                  {s.is_active ? "Đang hoạt động" : "Đã tắt"}
                </span>
              </div>
              <div className="cc-shift-times">
                <Clock size={13} style={{ color: "var(--ash)" }} />
                <span>
                  {s.start_time} – {s.end_time}
                </span>
              </div>
              <div className="cc-shift-meta">
                <span className="cc-badge-pill cc-badge-pill--gray">
                  Dung sai trễ: {s.grace_minutes}′
                </span>
                {s.is_overnight ? (
                  <span className="cc-badge-pill cc-badge-pill--purple">
                    <Moon
                      size={10}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "2px",
                      }}
                    />{" "}
                    Qua đêm
                  </span>
                ) : (
                  <span className="cc-badge-pill cc-badge-pill--primary">
                    <Sun
                      size={10}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "2px",
                      }}
                    />{" "}
                    Ca ngày
                  </span>
                )}
              </div>
              {s.note && (
                <div
                  style={{
                    fontSize: "12px",
                    color: "var(--ash)",
                    marginTop: "8px",
                  }}
                >
                  Ghi chú: {s.note}
                </div>
              )}
            </div>
          ))}
          {items?.length === 0 && (
            <div className="ns__empty" style={{ gridColumn: "1/-1" }}>
              Chưa có ca làm việc nào được cấu hình.
            </div>
          )}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="B · Phân ca tháng"
        defaultOpen
        summary={
          <span className="cc-sp-sum__txt">
            Lưới ngày × nhân viên · ô trống = kế thừa ca nền
          </span>
        }
      >
        <ShiftPlanPanel token={token} />
      </CollapsibleSection>

      {/* KHÔNG có khối "C · Lịch sử thay đổi ca" riêng (chủ 29/07/2026): lịch sử nằm TRONG
          drawer "Lịch sử ca" của từng người — bấm vào tên nhân viên trên lưới. Hai chỗ cùng
          kể chuyện đổi ca thì người dùng phải tự đoán chỗ nào là chỗ thật. */}
      {editing && (
        <ShiftForm
          token={token}
          shift={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

// --- Khối C: Lịch sử thay đổi ca (chủ 28/07/2026) ---------------------------
// Ca của một người đến từ HAI lớp: ô lưới (đè đúng một ngày) và ca nền (áp từ ngày hiệu lực
// TRỞ VỀ SAU). Màn này hiện CẢ HAI — chỉ hiện lưới thì khi ai đó đổi ca nền, người xem thấy
// "không có thay đổi nào" trong khi ca đã đổi thật, tệ hơn là không có màn lịch sử.

const SHIFT_CHANGE_FILTERS = [
  { key: "all", label: "Tất cả" },
  { key: "day", label: "✎ Sửa tay" },
  { key: "base", label: "🗓 Ca nền" },
] as const;

/** Câu mô tả một dòng — dùng chung cho màn HCNS và hộp thư của NV, để hai nơi không kể hai kiểu. */
function shiftChangeText(c: ShiftChange): string {
  const truoc = c.is_off_before ? "Nghỉ theo lịch" : (c.shift_name_before ?? "không có ca");
  const sau = c.is_off_after ? "Nghỉ theo lịch" : (c.shift_name_after ?? "không có ca");
  return `${truoc} → ${sau}`;
}

function ShiftChangeLogPanel({
  token,
  employeeId,
}: {
  token: string;
  employeeId: number;
}) {
  const [filter, setFilter] = useState<(typeof SHIFT_CHANGE_FILTERS)[number]["key"]>("all");
  // null = ĐANG TẢI. Khởi tạo [] sẽ hiện "chưa có thay đổi nào" ngay lúc còn fetch — báo SAI.
  const [rows, setRows] = useState<ShiftChange[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // KHÔNG lọc tháng: drawer mở cho MỘT người nên số dòng vốn ít, mà chặn theo tháng thì thay
  // đổi tháng trước biến mất — đúng lúc người ta mở ra để hỏi "ai đổi ca tôi hôm nọ".
  useEffect(() => {
    let alive = true;
    api.attendance
      .shiftChanges(token, {
        employeeId,
        kind: filter === "all" ? undefined : filter,
      })
      .then((r) => {
        if (!alive) return;
        setRows(r.items);
        setErr(null);
      })
      .catch((e) => alive && setErr(elErr(e)));
    return () => {
      alive = false;
    };
  }, [token, employeeId, filter]);

  return (
    <div className="cc-scl">
      <div className="cc-scl__bar">
        <span className="cc-scl__head">Ai đã đổi ca của người này</span>
        <div className="cc-scl__filters">
          {SHIFT_CHANGE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`cc-scl__filter${filter === f.key ? " is-on" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="banner banner--error">{err}</div>}

      {rows === null ? (
        <p className="cc-hint">Đang tải lịch sử…</p>
      ) : rows.length === 0 ? (
        <p className="cc-hint">
          Chưa có thay đổi nào được ghi lại. Từ nay mọi lần sửa ô trên lưới hoặc đổi ca nền đều
          hiện ở đây kèm người sửa và giờ sửa.
        </p>
      ) : (
        <div className="cc-scl__list">
          {rows.map((c) => (
            <div className="cc-scl__row" key={c.id}>
              <span
                className={`cc-scl__chip cc-scl__chip--${
                  c.origin === "base_remove" ? "rm" : c.kind
                }`}
              >
                {c.origin === "base_remove"
                  ? "⊘ Gỡ mốc"
                  : c.kind === "day"
                    ? "✎ Sửa tay"
                    : "🗓 Ca nền"}
              </span>
              {/* HAI mốc thời gian khác nhau, đừng đọc lẫn: cột này là ngày ca ĐƯỢC ÁP DỤNG,
                  còn giờ ở cột phải mới là LÚC THAO TÁC. */}
              <span className="cc-scl__when">
                {c.kind === "base" ? "Áp dụng từ " : ""}
                {fmtDateVN(c.apply_date)}
                {c.kind === "base" && <em>trở về sau</em>}
              </span>
              <span className="cc-scl__delta">{shiftChangeText(c)}</span>
              <span className="cc-scl__by">
                {c.actor_name ?? "—"}
                <em>{fmtDateTime(c.created_at)}</em>
              </span>
              {!c.notified && (
                <span className="cc-scl__nomail" title="Nhân viên chưa có tài khoản đăng nhập">
                  chưa báo được
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ShiftForm({
  token,
  shift,
  onClose,
  onSaved,
}: {
  token: string;
  shift: WorkShift | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkShiftInput>({
    name: shift?.name ?? "",
    start_time: shift?.start_time ?? "08:00",
    end_time: shift?.end_time ?? "17:00",
    is_overnight: shift?.is_overnight ?? false,
    night_multiplier: shift?.night_multiplier ?? 1.3,
    grace_minutes: shift?.grace_minutes ?? 5,
    meal_allowance: shift?.meal_allowance ?? 25000,
    shift_allowance: shift?.shift_allowance ?? 50000,
    note: shift?.note ?? "",
    is_active: shift?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof WorkShiftInput>(k: K, v: WorkShiftInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  function timeParts(field: "start_time" | "end_time") {
    return (normalizeTime24(form[field]) ?? "00:00").split(":");
  }
  function setTimePart(
    field: "start_time" | "end_time",
    part: "hour" | "minute",
    value: string,
  ) {
    const [hour, minute] = timeParts(field);
    set(field, part === "hour" ? `${value}:${minute}` : `${hour}:${value}`);
  }
  async function save() {
    setBusy(true);
    setError(null);
    const startTime = normalizeTime24(form.start_time);
    const endTime = normalizeTime24(form.end_time);
    if (!startTime || !endTime) {
      setError("Giờ ca không hợp lệ. Vui lòng chọn lại giờ và phút.");
      setBusy(false);
      return;
    }
    const payload = { ...form, start_time: startTime, end_time: endTime };
    setForm(payload);
    try {
      if (shift) await api.attendance.updateShift(token, shift.id, payload);
      else await api.attendance.createShift(token, payload);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu.");
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{shift ? "Sửa ca làm việc" : "Thêm ca làm việc"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field">
            <span className="ns-field__label">Tên ca *</span>
            <input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="Hành chính / Ca 1…"
            />
          </label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Giờ vào ca (24 giờ)</span>
              <span className="cc-time-selects">
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Giờ</span>
                  <select
                    aria-label="Giờ vào ca"
                    value={timeParts("start_time")[0]}
                    onChange={(e) =>
                      setTimePart("start_time", "hour", e.target.value)
                    }
                  >
                    {TIME_HOURS.map((hour) => (
                      <option key={hour} value={hour}>
                        {hour}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
                <strong className="cc-time-selects__separator">:</strong>
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Phút</span>
                  <select
                    aria-label="Phút vào ca"
                    value={timeParts("start_time")[1]}
                    onChange={(e) =>
                      setTimePart("start_time", "minute", e.target.value)
                    }
                  >
                    {TIME_MINUTES.map((minute) => (
                      <option key={minute} value={minute}>
                        {minute}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Giờ ra ca (24 giờ)</span>
              <span className="cc-time-selects">
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Giờ</span>
                  <select
                    aria-label="Giờ ra ca"
                    value={timeParts("end_time")[0]}
                    onChange={(e) =>
                      setTimePart("end_time", "hour", e.target.value)
                    }
                  >
                    {TIME_HOURS.map((hour) => (
                      <option key={hour} value={hour}>
                        {hour}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
                <strong className="cc-time-selects__separator">:</strong>
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Phút</span>
                  <select
                    aria-label="Phút ra ca"
                    value={timeParts("end_time")[1]}
                    onChange={(e) =>
                      setTimePart("end_time", "minute", e.target.value)
                    }
                  >
                    {TIME_MINUTES.map((minute) => (
                      <option key={minute} value={minute}>
                        {minute}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Dung sai đi muộn (phút)</span>
              <input
                type="number"
                min={0}
                value={form.grace_minutes}
                onChange={(e) => set("grace_minutes", Number(e.target.value))}
              />
            </label>
          </div>
          <p className="cc-note" style={{ marginTop: 8 }}>
            Chọn theo giờ 24 giờ: <strong>00:00 là nửa đêm</strong>, còn{" "}
            <strong>12:00 là buổi trưa</strong>.
          </p>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Phụ cấp cơm (đ)</span>
              <input
                type="number"
                min={0}
                step={5000}
                value={form.meal_allowance ?? 0}
                onChange={(e) => set("meal_allowance", Number(e.target.value))}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Phụ cấp ca (đ)</span>
              <input
                type="number"
                min={0}
                step={5000}
                value={form.shift_allowance ?? 0}
                onChange={(e) => set("shift_allowance", Number(e.target.value))}
              />
            </label>
          </div>
          <p className="cc-note" style={{ marginTop: 8 }}>
            Phụ cấp gắn theo ca: nhân viên được gán ca này sẽ tự cộng khi tính
            lương.
          </p>
          <label className="ns-check" style={{ marginTop: 12 }}>
            <input
              type="checkbox"
              checked={!!form.is_overnight}
              onChange={(e) => set("is_overnight", e.target.checked)}
            />
            Ca qua đêm (ra hôm sau, vd 22:00→06:00)
          </label>
          {form.is_overnight && (
            <label className="ns-field" style={{ marginTop: 10 }}>
              <span className="ns-field__label">
                Hệ số ca đêm (vd 1.3 = +30%)
              </span>
              <input
                type="number"
                min={1}
                step={0.05}
                value={form.night_multiplier ?? 1.3}
                onChange={(e) =>
                  set("night_multiplier", Number(e.target.value))
                }
              />
              <span className="cc-note" style={{ marginTop: 4 }}>
                Cộng thêm cho GIỜ rơi 22h–06h trong ca (theo luật ≥ 1.3 = +30%).
                Tăng ca đêm tính riêng theo Cấu hình lương.
              </span>
            </label>
          )}
          <label className="ns-check">
            <input
              type="checkbox"
              checked={!!form.is_active}
              onChange={(e) => set("is_active", e.target.checked)}
            />{" "}
            Đang dùng
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

const WEEKDAY_NAMES_SHORT = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function getWeekdayIndex(year: number, month: number, day: number): number {
  return new Date(year, month - 1, day).getDay();
}

function getWeekdayLabel(year: number, month: number, day: number): string {
  return WEEKDAY_NAMES_SHORT[getWeekdayIndex(year, month, day)];
}

function isWeekend(year: number, month: number, day: number): boolean {
  const w = getWeekdayIndex(year, month, day);
  return w === 0 || w === 6; // 0 = CN, 6 = T7
}

function EmployeeCalendarModal({
  employeeName,
  employeeRow,
  year,
  month,
  daysInMonth,
  onClose,
}: {
  employeeName: string;
  employeeRow: TimesheetRow;
  year: number;
  month: number;
  daysInMonth: number;
  onClose: () => void;
}) {
  const startOffset = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Mon=0..Sun=6
  const calendarCells: (number | null)[] = [];
  for (let i = 0; i < startOffset; i++) {
    calendarCells.push(null);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    calendarCells.push(d);
  }

  // Calculate statistics for this employee
  let workedDays = 0;
  let totalOtMinutes = 0;
  let lateDays = 0;
  let earlyDays = 0;
  let leaveDays = 0;

  Object.values(employeeRow.days).forEach((day) => {
    if (day.leave) {
      leaveDays++;
    } else {
      if (day.first_in || day.last_out) {
        workedDays += day.cong ?? 1;
      }
      if (day.ot_minutes) {
        totalOtMinutes += day.ot_minutes;
      }
      if (day.late) {
        lateDays++;
      }
      if (day.early) {
        earlyDays++;
      }
    }
  });

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div
        className="ns-modal__box cc-emp-cal-modal-box"
        style={{ maxWidth: "700px" }}
      >
        <header className="ns-modal__head">
          <h2
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              margin: 0,
            }}
          >
            <Calendar size={18} /> Lịch công tháng {month}/{year} ·{" "}
            {employeeName}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {/* Summary metrics of the employee */}
          <div className="cc-emp-cal-summary-grid">
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Số ngày công</span>
              <span className="cc-emp-cal-summary-val">
                {employeeRow.total_cong ?? workedDays} công
              </span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Tổng giờ làm</span>
              <span className="cc-emp-cal-summary-val">
                {employeeRow.total_hours ?? 0}h
              </span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Tăng ca (OT)</span>
              <span className="cc-emp-cal-summary-val">
                {(totalOtMinutes / 60).toFixed(1)}h
              </span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Muộn / Sớm</span>
              <span className="cc-emp-cal-summary-val text-warn">
                {lateDays} / {earlyDays} lần
              </span>
            </div>
          </div>

          {/* Calendar grid */}
          <div className="cc-month-grid" style={{ marginTop: "16px" }}>
            {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((w) => (
              <div
                key={w}
                style={{
                  textAlign: "center",
                  fontWeight: "bold",
                  fontSize: "11px",
                  paddingBottom: "6px",
                  color: "var(--ash)",
                }}
              >
                {w}
              </div>
            ))}
            {calendarCells.map((dayNum, idx) => {
              if (dayNum === null)
                return (
                  <div
                    key={`empty-${idx}`}
                    className="cc-month-cell cc-month-cell--empty"
                  />
                );

              const day = employeeRow.days[String(dayNum)];
              let cellClass = "cc-month-cell cc-emp-cal-cell";
              let timeRange = "";
              let statusLabel = "";
              let otBadge = false;

              if (day) {
                if (day.leave) {
                  cellClass += " cc-month-cell--holiday";
                  statusLabel = day.leave_paid ? "Nghỉ phép (P)" : "Nghỉ KL";
                } else {
                  const hasPunch = day.first_in || day.last_out;
                  if (hasPunch) {
                    cellClass += " cc-month-cell--work";
                    if (day.late || day.early)
                      cellClass += " cc-month-cell--makeup";
                    timeRange = `${day.first_in ?? "?"} - ${day.last_out ?? "?"}`;
                    statusLabel =
                      day.cong != null
                        ? `Công: ${day.cong}`
                        : day.hours != null
                          ? `${day.hours}h`
                          : "Đã chấm";
                    if (day.ot_minutes) otBadge = true;
                  }
                }
              }

              const currentDayOfWeek = new Date(
                year,
                month - 1,
                dayNum,
              ).getDay();
              const isWeekendCell =
                currentDayOfWeek === 0 || currentDayOfWeek === 6;
              if (!day && isWeekendCell) {
                cellClass += " cc-month-cell--weekend";
              }

              return (
                <div key={dayNum} className={cellClass}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <span className="cc-month-cell-num">{dayNum}</span>
                    {otBadge && (
                      <span
                        className="cc-badge-pill cc-badge-pill--orange"
                        style={{ padding: "1px 4px", fontSize: "9px" }}
                      >
                        +OT
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: "11px",
                      fontWeight: 600,
                      color: "var(--ink)",
                      marginTop: "4px",
                    }}
                  >
                    {timeRange || "—"}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: "var(--ash)",
                      marginTop: "2px",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "2px",
                      justifyContent: "space-between",
                      width: "100%",
                    }}
                  >
                    <span>{statusLabel}</span>
                    {day?.late && (
                      <span
                        style={{ color: "var(--signal)", fontWeight: "bold" }}
                      >
                        Muộn
                      </span>
                    )}
                    {day?.early && (
                      <span
                        style={{
                          color: "var(--amber-deep)",
                          fontWeight: "bold",
                        }}
                      >
                        Sớm
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

function TimesheetTab({
  token,
  canAdjust,
}: {
  token: string;
  canAdjust: boolean;
}) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [data, setData] = useState<Timesheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [deptId, setDeptId] = useState<number | "">("");
  const [depts, setDepts] = useState<{ id: number; name: string }[]>([]);
  const [openDay, setOpenDay] = useState<{
    employeeId: number;
    employeeName: string;
    date: string;
  } | null>(null);
  const [period, setPeriod] = useState<AttendancePeriod | null>(null);
  const [periodBusy, setPeriodBusy] = useState(false);
  const [periodMsg, setPeriodMsg] = useState<{
    text: string;
    type: "success" | "error";
  } | null>(null);
  const [selectedEmployeeCal, setSelectedEmployeeCal] = useState<{
    row: TimesheetRow;
    name: string;
  } | null>(null);
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    api.employees
      .meta(token)
      .then((m) => setDepts(m.departments))
      .catch(() => setDepts([]));
  }, [token]);

  const loadPeriod = useCallback(() => {
    api.attendance
      .period(token, year, month)
      .then(setPeriod)
      .catch(() => setPeriod(null));
  }, [token, year, month]);
  useEffect(() => {
    loadPeriod();
    setPeriodMsg(null);
  }, [loadPeriod]);

  const reload = useCallback(() => {
    setLoading(true);
    api.attendance
      .timesheet(token, year, month, deptId === "" ? null : deptId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [token, year, month, deptId]);
  useEffect(() => {
    reload();
  }, [reload]);

  async function doLockPeriod() {
    setPeriodBusy(true);
    setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.lockPeriod(token, year, month));
      setPeriodMsg({ text: "Đã chốt công tháng.", type: "success" });
    } catch (e) {
      setPeriodMsg({
        text: e instanceof Error ? e.message : "Lỗi khi chốt công.",
        type: "error",
      });
    } finally {
      setPeriodBusy(false);
    }
  }
  async function doReopenPeriod() {
    setPeriodBusy(true);
    setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.reopenPeriod(token, year, month));
      setPeriodMsg({ text: "Đã mở lại kỳ công.", type: "success" });
    } catch (e) {
      setPeriodMsg({
        text: e instanceof Error ? e.message : "Lỗi khi mở kỳ công.",
        type: "error",
      });
    } finally {
      setPeriodBusy(false);
    }
  }

  function openCell(employeeId: number, employeeName: string, dayNum: number) {
    const date = `${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
    setOpenDay({ employeeId, employeeName, date });
  }

  async function exportCsv() {
    setDownloading(true);
    try {
      const url = await api.attendance.timesheetCsvBlobUrl(
        token,
        year,
        month,
        deptId === "" ? null : deptId,
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `bang-cong-${year}-${String(month).padStart(2, "0")}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  const days = data
    ? Array.from({ length: data.days_in_month }, (_, i) => i + 1)
    : [];

  // Dynamic KPIs calculations
  const totalEmployees = data?.rows.length ?? 0;
  let totalCong = 0;
  let totalHours = 0;
  if (data?.rows) {
    for (const r of data.rows) {
      totalCong += r.total_cong ?? r.total_days ?? 0;
      totalHours += r.total_hours ?? 0;
    }
  }

  return (
    <div>
      {/* 1. Dynamic Month KPI Dashboard */}
      <div className="cc-ts-kpi-strip">
        <div className="cc-ts-kpi-card cc-ts-kpi-card--total">
          <div className="cc-ts-kpi-icon">
            <UserCheck size={18} />
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">{totalEmployees}</span>
            <span className="cc-ts-kpi-label">Tổng nhân sự</span>
          </div>
        </div>
        <div className="cc-ts-kpi-card cc-ts-kpi-card--cong">
          <div className="cc-ts-kpi-icon">
            <CalendarDays size={18} />
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">{totalCong.toFixed(1)}</span>
            <span className="cc-ts-kpi-label">Tổng ngày công</span>
          </div>
        </div>
        <div className="cc-ts-kpi-card cc-ts-kpi-card--hours">
          <div className="cc-ts-kpi-icon">
            <Clock size={18} />
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">{totalHours.toFixed(1)}h</span>
            <span className="cc-ts-kpi-label">Tổng giờ làm</span>
          </div>
        </div>
        <div
          className={`cc-ts-kpi-card cc-ts-kpi-card--period ${period?.status === "locked" ? "is-locked" : "is-draft"}`}
        >
          <div className="cc-ts-kpi-icon">
            {period?.status === "locked" ? (
              <Lock size={18} />
            ) : (
              <Unlock size={18} />
            )}
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">
              {period?.status === "locked" ? "Đã chốt" : "Bản nháp"}
            </span>
            <span className="cc-ts-kpi-label">
              {period?.status === "locked"
                ? `Khóa băng ${period.line_count} NV`
                : `${(period?.hanging_days ?? 0) > 0 ? `${period?.hanging_days} ngày treo` : "Kỳ công hiện tại"}`}
            </span>
          </div>
        </div>
      </div>

      {/* Warning banner for pending checks */}
      {period &&
        period.status !== "locked" &&
        (period.hanging_days > 0 ||
          period.pending_leaves +
            period.pending_adjusts +
            period.pending_late_early >
            0) && (
          <div
            className="banner banner--warn cc-ts-warn-banner"
            style={{ marginBottom: "16px" }}
          >
            <AlertTriangle size={14} style={{ marginRight: "6px" }} />
            <span>
              Kỳ công có <strong>{period.hanging_days}</strong> ngày treo (thiếu
              chấm RA) và{" "}
              <strong>
                {period.pending_leaves +
                  period.pending_adjusts +
                  period.pending_late_early}
              </strong>{" "}
              đơn chờ duyệt.
            </span>
          </div>
        )}

      {periodMsg && (
        <div
          className={`banner ${periodMsg.type === "error" ? "banner--error" : "banner--ok"} cc-ts-msg-banner`}
          style={{ marginBottom: "16px" }}
        >
          {periodMsg.text}
        </div>
      )}

      {/* 2. Redesigned Filter & Actions Bar */}
      <div className="cc-ts-header-actions">
        <div className="cc-ts-filters">
          <input
            type="month"
            value={ym}
            onChange={(e) => setYm(e.target.value)}
            className="cc-ts-input-month"
          />
          <select
            value={deptId}
            onChange={(e) =>
              setDeptId(e.target.value === "" ? "" : Number(e.target.value))
            }
            className="cc-ts-select-dept"
          >
            <option value="">Tất cả phòng/tổ</option>
            {depts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <div className="cc-ts-legend-strip">
            <span className="cc-ts-legend-item cc-ts-legend-item--work">
              Công
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--late">
              Muộn
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--early">
              Sớm
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--leave">
              Nghỉ/Phép
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--ot">
              OT (+)
            </span>
          </div>
        </div>

        <div className="cc-ts-actions">
          <button
            className="btn btn--ghost cc-ts-btn-export"
            onClick={exportCsv}
            disabled={downloading || !data?.rows.length}
          >
            {downloading ? (
              <RefreshCw className="cc-animate-spin" size={14} />
            ) : (
              <FileEdit size={14} />
            )}
            <span>{downloading ? "Đang xuất…" : "Xuất CSV"}</span>
          </button>

          {canAdjust && period && (
            <div className="cc-ts-action-lock-wrapper">
              {period.status === "draft" ? (
                <button
                  className="btn btn--primary cc-ts-btn-lock"
                  onClick={doLockPeriod}
                  disabled={periodBusy}
                >
                  <Lock size={14} />
                  <span>{periodBusy ? "Đang khóa…" : "Chốt công tháng"}</span>
                </button>
              ) : (
                <button
                  className="btn btn--ghost cc-ts-btn-unlock"
                  onClick={doReopenPeriod}
                  disabled={periodBusy || period.payroll_locked}
                  title={
                    period.payroll_locked
                      ? "Kỳ lương đã chốt — không mở lại kỳ công"
                      : ""
                  }
                >
                  <Unlock size={14} />
                  <span>{periodBusy ? "Đang mở…" : "Mở lại kỳ công"}</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 3. Timesheet Scroll Table */}
      {loading && <p className="ns__empty">Đang tải biểu công…</p>}
      {!loading && data && (
        <div className="cc-timesheet-scroll-container">
          <table className="cc-timesheet-table">
            <thead>
              <tr>
                <th className="cc-sticky-col-code">Mã</th>
                <th className="cc-sticky-col-name">Họ tên</th>
                <th>Ca</th>
                {days.map((d) => {
                  const label = getWeekdayLabel(year, month, d);
                  const weekend = isWeekend(year, month, d);
                  return (
                    <th
                      key={d}
                      className={`cc-day-hdr-v2 ${weekend ? "cc-day-hdr-v2--weekend" : ""}`}
                    >
                      <div className="cc-day-hdr-v2-weekday">{label}</div>
                      <div className="cc-day-hdr-v2-num">{d}</div>
                    </th>
                  );
                })}
                <th>Công</th>
                <th>Giờ</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <TimesheetRowView
                  key={r.employee_id}
                  row={r}
                  days={days}
                  isWeekend={(d) => isWeekend(year, month, d)}
                  onCellClick={(dayNum) =>
                    openCell(r.employee_id, r.employee_name, dayNum)
                  }
                  onNameClick={() =>
                    setSelectedEmployeeCal({ row: r, name: r.employee_name })
                  }
                />
              ))}
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={days.length + 5} className="ns__empty">
                    Chưa có dữ liệu chấm công tháng này.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {openDay && (
        <DayDetailModal
          token={token}
          canAdjust={canAdjust}
          employeeId={openDay.employeeId}
          employeeName={openDay.employeeName}
          date={openDay.date}
          onClose={() => setOpenDay(null)}
          onChanged={reload}
        />
      )}

      {selectedEmployeeCal && (
        <EmployeeCalendarModal
          employeeName={selectedEmployeeCal.name}
          employeeRow={selectedEmployeeCal.row}
          year={year}
          month={month}
          daysInMonth={data?.days_in_month ?? 30}
          onClose={() => setSelectedEmployeeCal(null)}
        />
      )}
    </div>
  );
}

function TimesheetRowView({
  row,
  days,
  isWeekend,
  onCellClick,
  onNameClick,
}: {
  row: TimesheetRow;
  days: number[];
  isWeekend: (dayNum: number) => boolean;
  onCellClick?: (dayNum: number) => void;
  onNameClick?: () => void;
}) {
  const clickable = !!onCellClick;
  const cellProps = (d: number) =>
    clickable
      ? {
          role: "button" as const,
          tabIndex: 0,
          onClick: () => onCellClick!(d),
          style: { cursor: "pointer" },
        }
      : {};
  return (
    <tr>
      <td className="cc-sticky-col-code">{row.employee_code}</td>
      <td className="cc-sticky-col-name">
        <div className="cc-name-cell-wrapper">
          <span className="cc-name-avatar">
            {getInitials(row.employee_name)}
          </span>
          <span
            className="cc-name-link"
            onClick={onNameClick}
            title="Xem lịch công tháng"
          >
            {row.employee_name}
          </span>
        </div>
      </td>
      <td>{row.shift_name ?? "—"}</td>
      {days.map((d) => {
        const isWe = isWeekend(d);
        const day = row.days[String(d)];
        const cellClass = `cc-day-cell ${isWe ? "cc-day-cell--weekend" : ""}`;

        if (!day) return <td key={d} className={cellClass} {...cellProps(d)} />;

        if (day.leave) {
          const leaveLabel = day.leave_paid ? "P" : "KL";
          return (
            <td key={d} className={cellClass} {...cellProps(d)}>
              <span
                className="cc-cell-badge cc-cell-badge--leave"
                title={`Nghỉ: ${day.leave}`}
              >
                {leaveLabel}
              </span>
            </td>
          );
        }

        // Formulate badge classes
        let badgeClass = "cc-cell-badge";
        if (day.late) badgeClass += " cc-cell-badge--late";
        else if (day.early) badgeClass += " cc-cell-badge--early";
        else badgeClass += " cc-cell-badge--work";

        const label =
          day.cong != null
            ? String(day.cong)
            : day.hours != null
              ? `${day.hours}h`
              : "•";
        const tip =
          `${day.first_in ?? "?"}–${day.last_out ?? "?"}` +
          (day.late ? " · đi muộn" : "") +
          (day.early ? " · về sớm" : "") +
          (day.ot_minutes ? ` · OT ${day.ot_minutes}′` : "") +
          (day.night ? " · ca đêm" : "");

        return (
          <td key={d} className={cellClass} {...cellProps(d)}>
            <span className={badgeClass} title={tip}>
              {label}
              {day.ot_minutes ? (
                <span
                  className="cc-cell-ot-dot"
                  title={`Tăng ca: ${day.ot_minutes}′`}
                >
                  +
                </span>
              ) : null}
            </span>
          </td>
        );
      })}
      <td style={{ fontWeight: "bold", textAlign: "center" }}>
        {row.total_cong != null ? row.total_cong : row.total_days}
      </td>
      <td style={{ fontWeight: "bold", textAlign: "center" }}>
        {row.total_hours}h
      </td>
    </tr>
  );
}

// "Ô biết nói": chi tiết punch 1 ngày của 1 NV + chấm bù/sửa (fault_party) có audit.

function DayDetailModal({
  token,
  canAdjust,
  employeeId,
  employeeName,
  date,
  onClose,
  onChanged,
}: {
  token: string;
  canAdjust: boolean;
  employeeId: number;
  employeeName: string;
  date: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<DayDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkType, setCheckType] = useState<"in" | "out">("in");
  const [time, setTime] = useState("08:00");
  const [fault, setFault] = useState("nv_quen");
  const [reason, setReason] = useState("");
  // Chấm bù CẶP tăng ca (1 chạm) khi NV có phiếu TC nhưng thiếu cặp chấm — điền sẵn theo khung phiếu.
  const [otIn, setOtIn] = useState("");
  const [otOut, setOtOut] = useState("");
  const [otBusy, setOtBusy] = useState(false);

  const load = useCallback(() => {
    api.attendance
      .day(token, employeeId, date)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [token, employeeId, date]);
  useEffect(() => {
    load();
  }, [load]);
  // Điền sẵn giờ vào/ra tăng ca theo phiếu khi có gợi ý (HCNS chỉnh lại giờ ra thực tế rồi lưu).
  const sugFrom = detail?.ot_suggestion?.from_time;
  const sugTo = detail?.ot_suggestion?.to_time;
  useEffect(() => {
    if (sugFrom && sugTo) {
      setOtIn(sugFrom);
      setOtOut(sugTo);
    }
  }, [sugFrom, sugTo]);

  async function addPunch() {
    if (!reason.trim()) {
      setError("Phải nhập lý do.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const d = await api.attendance.adjust(token, {
        employee_id: employeeId,
        date,
        check_type: checkType,
        time,
        reason: reason.trim(),
        fault_party: fault,
      });
      setDetail(d);
      setReason("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi chấm bù.");
    } finally {
      setBusy(false);
    }
  }

  async function removePunch(logId: number) {
    setBusy(true);
    setError(null);
    try {
      const d = await api.attendance.deleteManualLog(
        token,
        logId,
        employeeId,
        date,
      );
      setDetail(d);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi xóa.");
    } finally {
      setBusy(false);
    }
  }

  // Chấm bù cặp tăng ca: thêm lượt VÀO rồi RA (2 punch) → engine tự gom thành phiên tăng ca.
  async function addOtPair() {
    if (!otIn || !otOut) {
      setError("Nhập đủ giờ vào và ra tăng ca.");
      return;
    }
    if (otOut <= otIn) {
      setError("Giờ ra tăng ca phải sau giờ vào.");
      return;
    }
    setOtBusy(true);
    setError(null);
    const reasonTxt = "Chấm bù cặp tăng ca (NV quên chấm)";
    try {
      await api.attendance.adjust(token, {
        employee_id: employeeId,
        date,
        check_type: "in",
        time: otIn,
        reason: reasonTxt,
        fault_party: "nv_quen",
      });
      const d = await api.attendance.adjust(token, {
        employee_id: employeeId,
        date,
        check_type: "out",
        time: otOut,
        reason: reasonTxt,
        fault_party: "nv_quen",
      });
      setDetail(d);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi chấm bù cặp tăng ca.");
      load(); // tải lại: có thể lượt VÀO đã thêm nhưng RA lỗi
    } finally {
      setOtBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Chi tiết chấm công</h2>
            <p className="cc-modal-subtitle">
              {employeeName} · Ngày {date}
            </p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error">{error}</div>}
          {!detail ? (
            <p className="ns__empty">Đang tải…</p>
          ) : (
            <>
              {/* Summary Strip */}
              <div className="cc-day-summary-strip">
                <div className="cc-day-summary-item">
                  <span className="cc-day-summary-lbl">Ca làm việc</span>
                  <span className="cc-day-summary-val cc-badge-shift">
                    {detail.shift_name ?? "Chưa gán"}
                  </span>
                </div>
                <div className="cc-day-summary-item">
                  <span className="cc-day-summary-lbl">Ngày công</span>
                  <span className="cc-day-summary-val cc-badge-cong">
                    {detail.cong != null ? detail.cong : "—"}
                  </span>
                </div>
                {detail.reason && (
                  <div className="cc-day-summary-item">
                    <span className="cc-day-summary-lbl">Cảnh báo</span>
                    <span className="cc-day-summary-val cc-badge-warn">
                      ⚠ {detail.reason}
                    </span>
                  </div>
                )}
              </div>

              {/* Punch Timeline */}
              <div className="cc-punch-timeline-container">
                <h4 className="cc-section-title-mini">
                  Lịch sử lượt chấm công
                </h4>
                <div className="cc-timeline-flow">
                  {detail.punches.map((p, idx) => {
                    const isIn = p.check_type === "in";
                    return (
                      <div className="cc-timeline-item" key={p.id}>
                        <div className="cc-timeline-connector">
                          <div
                            className={`cc-timeline-dot ${isIn ? "is-in" : "is-out"}`}
                          />
                          {idx < detail.punches.length - 1 && (
                            <div className="cc-timeline-line" />
                          )}
                        </div>
                        <div className="cc-timeline-content">
                          <div className="cc-timeline-header">
                            <span className="cc-timeline-time">{p.time}</span>
                            <span
                              className={`cc-timeline-badge ${isIn ? "is-in" : "is-out"}`}
                            >
                              {isIn ? "VÀO" : "RA"}
                            </span>
                            <span
                              className={`cc-timeline-source ${p.is_manual ? "is-manual" : "is-gps"}`}
                            >
                              {p.is_manual ? "Chấm bù" : "GPS"}
                            </span>
                          </div>
                          {p.is_manual && (
                            <div className="cc-timeline-details">
                              {p.fault_party && (
                                <span className="cc-fault-party">
                                  {FAULT_LABEL[p.fault_party] ?? p.fault_party}
                                </span>
                              )}
                              {p.adjust_reason && (
                                <span className="cc-adjust-reason">
                                  {" "}
                                  · {p.adjust_reason}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        {p.is_manual && canAdjust && (
                          <button
                            className="cc-btn-timeline-delete"
                            onClick={() => removePunch(p.id)}
                            disabled={busy}
                            title="Xóa lượt chấm này"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                  {detail.punches.length === 0 && (
                    <p
                      className="ns__empty"
                      style={{ padding: "16px 0", textAlign: "center" }}
                    >
                      Ngày này chưa có lượt chấm nào.
                    </p>
                  )}
                </div>
              </div>

              {/* Nhắc + nút 1 chạm: NV có phiếu TC đã duyệt nhưng thiếu cặp chấm tăng ca */}
              {canAdjust && detail.ot_suggestion && (
                <div className="cc-ot-suggest">
                  <h4 className="cc-ot-suggest__title">
                    <AlertTriangle size={14} /> Chưa chấm cặp tăng ca — phiếu{" "}
                    {detail.ot_suggestion.from_time}–
                    {detail.ot_suggestion.to_time}
                  </h4>
                  <p className="cc-ot-suggest__hint">
                    Giờ điền sẵn theo phiếu; sửa <b>giờ ra</b> theo thực tế rồi
                    lưu.
                  </p>
                  <div className="cc-ot-suggest__grid">
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Vào tăng ca</span>
                      <div className="cc-input-time-wrapper">
                        <input
                          type="time"
                          value={otIn}
                          onChange={(e) => setOtIn(e.target.value)}
                        />{" "}
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">
                        Ra tăng ca (thực tế)
                      </span>
                      <div className="cc-input-time-wrapper">
                        <input
                          type="time"
                          value={otOut}
                          onChange={(e) => setOtOut(e.target.value)}
                        />{" "}
                      </div>
                    </div>
                  </div>
                  <div className="cc-adjust-action-row">
                    <button
                      className="btn cc-btn-add-punch"
                      onClick={addOtPair}
                      disabled={otBusy}
                    >
                      {otBusy ? (
                        <RefreshCw className="cc-animate-spin" size={14} />
                      ) : (
                        "Chấm bù cặp tăng ca"
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Form Adjust */}
              {canAdjust && (
                <div className="cc-adjust-section">
                  <h4 className="cc-section-title-mini">Chấm bù / sửa</h4>
                  <div className="cc-adjust-grid">
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Loại chấm</span>
                      <div className="cc-select-wrapper">
                        <select
                          value={checkType}
                          onChange={(e) =>
                            setCheckType(e.target.value as "in" | "out")
                          }
                        >
                          <option value="in">VÀO</option>
                          <option value="out">RA</option>
                        </select>
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Giờ</span>
                      <div className="cc-input-time-wrapper">
                        <input
                          type="time"
                          value={time}
                          onChange={(e) => setTime(e.target.value)}
                        />{" "}
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Nguyên nhân</span>
                      <div className="cc-select-wrapper">
                        <select
                          value={fault}
                          onChange={(e) => setFault(e.target.value)}
                        >
                          {FAULT_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>

                  <div className="cc-adjust-field" style={{ marginTop: 14 }}>
                    <span className="cc-field-label">
                      Lý do (bắt buộc, ghi vào nhật ký)
                    </span>
                    <input
                      className="cc-input-text"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="vd: NV quên chấm ra, đã xác minh…"
                    />
                  </div>

                  <div className="cc-adjust-action-row">
                    <button
                      className="btn btn--primary cc-btn-add-punch"
                      onClick={addPunch}
                      disabled={busy}
                    >
                      {busy ? (
                        <RefreshCw className="cc-animate-spin" size={14} />
                      ) : (
                        "Thêm punch chấm bù"
                      )}
                    </button>
                  </div>

                  <div className="cc-info-card-note">
                    <AlertTriangle size={14} className="cc-note-icon" />
                    <span>
                      Công được <b>tự động tính lại</b> từ các lượt chấm (punch)
                      — không ghi đè trực tiếp con số. Mọi thao tác đều được lưu
                      nhật ký kiểm toán.
                    </span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Yêu cầu chỉnh công (HCNS duyệt) -----------------------------------

const STATUS_MAP: Record<string, [string, string]> = {
  pending: ["cc-badge-status--pending", "Chờ duyệt"],
  approved: ["cc-badge-status--approved", "Đã duyệt"],
  rejected: ["cc-badge-status--rejected", "Từ chối"],
  cancelled: ["cc-badge-status--cancelled", "Đã hủy"],
};

/** Nhãn trạng thái thuần chữ (dùng trong câu văn, không phải badge). */
function statusText(s: string): string {
  return STATUS_MAP[s]?.[1] ?? s;
}

function statusBadge(s: string) {
  const [cls, label] = STATUS_MAP[s] ?? ["cc-badge-status--cancelled", s];
  return <span className={`cc-badge-status ${cls}`}>{label}</span>;
}

function AdjustRequestsTab({
  token,
  canAdjust,
}: {
  token: string;
  canAdjust: boolean;
}) {
  const [items, setItems] = useState<AdjustRequest[] | null>(null);
  const [status, setStatus] = useState("pending");
  const [faults, setFaults] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api.attendance
      .listAdjustRequests(token, status)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, status]);
  useEffect(() => {
    load();
  }, [load]);

  async function approve(r: AdjustRequest) {
    setBusy(true);
    setErr(null);
    try {
      await api.attendance.approveAdjustRequest(token, r.id, {
        fault_party: faults[r.id] ?? r.fault_party ?? "nv_quen",
      });
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lỗi khi duyệt.");
    } finally {
      setBusy(false);
    }
  }
  async function reject(r: AdjustRequest) {
    const note = window.prompt("Lý do từ chối yêu cầu:");
    if (!note) return;
    setBusy(true);
    setErr(null);
    try {
      await api.attendance.rejectAdjustRequest(token, r.id, note);
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Lỗi khi từ chối.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="cc-ts-toolbar">
        <div className="cc-select-wrapper" style={{ width: "160px" }}>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">Chờ duyệt</option>
            <option value="approved">Đã duyệt</option>
            <option value="rejected">Từ chối</option>
            <option value="all">Tất cả</option>
          </select>
        </div>
        <div
          className="cc-info-card-note"
          style={{ margin: 0, padding: "8px 12px" }}
        >
          <Info size={14} className="cc-note-icon" />
          <span>
            Duyệt yêu cầu sẽ tự động tạo lượt chấm công bù (punch) tương ứng và
            tính lại ngày công của ngày đó.
          </span>
        </div>
      </div>

      {err && (
        <div
          className="banner banner--error cc-ts-msg-banner"
          style={{ marginBottom: "16px" }}
        >
          {err}
        </div>
      )}

      {!items ? (
        <p className="ns__empty">Đang tải…</p>
      ) : (
        <div className="cc-timesheet-scroll-container">
          <table className="cc-timesheet-table">
            <thead>
              <tr>
                <th>Nhân viên</th>
                <th>Ngày</th>
                <th style={{ textAlign: "center" }}>Chấm</th>
                <th style={{ textAlign: "center" }}>Giờ</th>
                <th>Lý do</th>
                <th style={{ textAlign: "center" }}>Trạng thái</th>
                {canAdjust && <th style={{ textAlign: "center" }}>Xử lý</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <div className="cc-name-cell-wrapper">
                      <span className="cc-name-avatar">
                        {getInitials(r.employee_name)}
                      </span>
                      <span
                        className="cc-name-text-plain"
                        title={r.employee_name ?? `NV#${r.employee_id}`}
                      >
                        {r.employee_name ?? `NV#${r.employee_id}`}
                      </span>
                    </div>
                  </td>
                  <td>{r.work_date}</td>
                  <td style={{ textAlign: "center" }}>
                    <span
                      className={`cc-cell-badge ${r.check_type === "in" ? "cc-cell-badge--work" : "cc-cell-badge--late"}`}
                    >
                      {r.check_type === "in" ? "VÀO" : "RA"}
                    </span>
                  </td>
                  <td
                    style={{
                      textAlign: "center",
                      fontFamily: "var(--ff-num)",
                      fontWeight: "bold",
                    }}
                  >
                    {r.suggested_time ?? "—"}
                  </td>
                  <td>
                    <div className="cc-reason-wrapper">
                      <span className="cc-reason-text">{r.reason}</span>
                      {r.decision_note && (
                        <div className="cc-decision-note-sub">
                          💬 {r.decision_note}
                        </div>
                      )}
                    </div>
                  </td>
                  <td style={{ textAlign: "center" }}>
                    {statusBadge(r.status)}
                  </td>
                  {canAdjust && (
                    <td style={{ textAlign: "center" }}>
                      {r.status === "pending" ? (
                        <div className="cc-adjust-actions-group">
                          <div className="cc-select-wrapper cc-select-fault-wrapper">
                            <select
                              value={faults[r.id] ?? r.fault_party ?? "nv_quen"}
                              onChange={(e) =>
                                setFaults((f) => ({
                                  ...f,
                                  [r.id]: e.target.value,
                                }))
                              }
                            >
                              {FAULT_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                  {o.label}
                                </option>
                              ))}
                            </select>
                          </div>
                          <button
                            className="btn btn--primary cc-btn-approve"
                            onClick={() => approve(r)}
                            disabled={busy}
                          >
                            Duyệt
                          </button>
                          <button
                            className="btn btn--ghost cc-btn-reject"
                            onClick={() => reject(r)}
                            disabled={busy}
                          >
                            Từ chối
                          </button>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td
                    colSpan={canAdjust ? 7 : 6}
                    className="ns__empty"
                    style={{ padding: "24px", textAlign: "center" }}
                  >
                    Không có yêu cầu chỉnh sửa công nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- Shared table -----------------------------------------------------------

function getInitials(name?: string | null) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (
    parts[parts.length - 2][0] + parts[parts.length - 1][0]
  ).toUpperCase();
}

function parseDateTimeVN(iso: string | null | undefined) {
  if (!iso) return { time: "—", date: "" };
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return { time: iso, date: "" };
  const timeStr = d.toLocaleTimeString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour12: false,
  });
  const dateStr = d.toLocaleDateString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
  });
  return { time: timeStr, date: dateStr };
}

function AttendanceTable({
  logs,
  showEmployee,
}: {
  logs: AttendanceLog[];
  showEmployee: boolean;
}) {
  return (
    <div className="ns__tablewrap">
      <table className="ns__table cc-log-table">
        <thead>
          <tr>
            {showEmployee && <th>Nhân viên</th>}
            <th style={{ width: "120px" }}>Loại</th>
            <th style={{ width: "150px" }}>Thời gian</th>
            <th>Điểm chấm công</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => {
            const { time, date } = parseDateTimeVN(l.checked_at);
            const isInside = l.distance_m == null || l.distance_m <= 150; // Bán kính chuẩn 150m
            return (
              <tr
                key={l.id}
                className={`cc-log-row cc-log-row--${l.check_type}`}
              >
                {showEmployee && (
                  <td>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <span className="cc-avatar-mini">
                        {getInitials(l.employee_name)}
                      </span>
                      <span
                        style={{
                          fontWeight: "var(--fw-medium)",
                          color: "var(--ink)",
                        }}
                      >
                        {l.employee_name ?? `NV#${l.employee_id}`}
                      </span>
                    </div>
                  </td>
                )}
                <td>
                  <span
                    className={`cc-log-badge cc-log-badge--${l.check_type}`}
                  >
                    {l.check_type === "in" ? (
                      <>
                        <LogIn size={12} style={{ marginRight: "4px" }} />
                        <span>VÀO</span>
                      </>
                    ) : (
                      <>
                        <LogOut size={12} style={{ marginRight: "4px" }} />
                        <span>RA</span>
                      </>
                    )}
                  </span>
                </td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    <span className="cc-log-time">{time}</span>
                    <span className="cc-log-date">{date}</span>
                  </div>
                </td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    <span
                      style={{
                        fontWeight: "var(--fw-medium)",
                        color: "var(--ink)",
                      }}
                    >
                      {l.location_name ?? "📍 Vị trí ngoài danh mục"}
                    </span>
                    <span
                      className={`cc-log-distance ${isInside ? "is-inside" : "is-outside"}`}
                    >
                      <MapPin
                        size={11}
                        style={{
                          marginRight: "3px",
                          display: "inline-block",
                          verticalAlign: "middle",
                        }}
                      />
                      {l.distance_m != null
                        ? isInside
                          ? `Trong phạm vi (${Math.round(l.distance_m)}m)`
                          : `Ngoài phạm vi (${Math.round(l.distance_m)}m)`
                        : "Không có GPS"}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
          {logs.length === 0 && (
            <tr>
              <td colSpan={showEmployee ? 4 : 3} className="ns__empty">
                Chưa có bản ghi chấm công.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// --- Tab: Đi muộn / về sớm / nghỉ nửa buổi (module `di_muon`) ----------------
// Phiếu CHẤM CÔNG ngoại lệ — KHÔNG phải đơn nghỉ phép. 1 phiếu/ngày, khai khoảng VẮNG MẶT,
// tổ trưởng duyệt. NV tự xin; tổ trưởng khai hộ thì duyệt luôn.
// Nghỉ nửa buổi có thể tick "Trừ vào phép năm": tick → tiêu ngày phép (tròn lên 0,5) và phần
// vắng VẪN được trả lương; không tick → quỹ phép nguyên, MẤT CÔNG phần vắng nhưng KHÔNG bị phạt.
//
// Backend KHÔNG lưu "kiểu" (đi muộn / về sớm / nửa buổi) — FE suy ra từ KHUNG CA để hiển thị.
// Không biết ca ⇒ chỉ hiện chip trung tính, ẨN mini-bar: nhãn đoán sai tệ hơn không nhãn.

type ElKind = "late" | "early" | "half" | "mid";
type ElFormKind = "late" | "early" | "half";
/** Một dòng thợ trong roster của module `di_muon` (backend đã lọc scope + bỏ NV đã nghỉ). */
type ElRosterEmp = LateEarlyRoster["employees"][number];

/** Khung ca đã quy về PHÚT trên trục ngày công (ca qua đêm: `endMin` đã cộng 1440). */
interface ElShift {
  name: string;
  startMin: number;
  endMin: number;
  overnight: boolean;
}

const EL_TOLERANCE = 10; // dung sai mép ca (phút) khi suy ra kiểu vắng
const EL_FALLBACK_WINDOW = 480; // ca 8h — mẫu số dự phòng khi chưa gán ca (khớp backend)

const EL_KIND_META: Record<
  ElKind,
  { label: string; Icon: typeof Clock; cls: string }
> = {
  late: { label: "Đi muộn", Icon: LogIn, cls: "el-kind--late" },
  early: { label: "Về sớm", Icon: LogOut, cls: "el-kind--early" },
  half: { label: "Nghỉ nửa buổi", Icon: Coffee, cls: "el-kind--half" },
  mid: { label: "Vắng giữa ca", Icon: Clock, cls: "el-kind--mid" },
};

const EL_FORM_KINDS: {
  value: ElFormKind;
  label: string;
  Icon: typeof Clock;
}[] = [
  { value: "late", label: "Đi muộn", Icon: LogIn },
  { value: "early", label: "Về sớm", Icon: LogOut },
  { value: "half", label: "Nghỉ nửa buổi", Icon: Coffee },
];

const EL_WEEKDAYS = [
  "Chủ nhật",
  "Thứ 2",
  "Thứ 3",
  "Thứ 4",
  "Thứ 5",
  "Thứ 6",
  "Thứ 7",
];

function elErr(e: unknown): string {
  // Lỗi 400 của backend đã là tiếng Việt và khớp nhãn UI → hiện NGUYÊN VĂN, đừng viết lại.
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

function elHhmmToMin(v: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(v.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return null;
  return h * 60 + mi;
}

/** Phút trên trục ngày công → "HH:MM" (lấy phần trong ngày; ca đêm vẫn ra giờ đồng hồ đúng). */
function elMinToHhmm(m: number): string {
  const rem = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

/** Ca ở dạng "HH:MM" (nguồn `myStatus().shift` — self-service, ai cũng gọi được). */
function elMakeShift(
  s:
    | {
        name: string;
        start_time: string;
        end_time: string;
        is_overnight: boolean;
      }
    | null
    | undefined,
): ElShift | null {
  if (!s) return null;
  const st = elHhmmToMin(s.start_time);
  const en = elHhmmToMin(s.end_time);
  if (st == null || en == null) return null;
  return elShiftFrom(s.name, st, en, s.is_overnight);
}

/** Ca ở dạng PHÚT (nguồn `lateEarly.roster()` — gác bằng `di_muon:approve`). */
function elShiftFromMinutes(s: {
  name: string;
  start_minute: number;
  end_minute: number;
  is_overnight: boolean;
}): ElShift | null {
  return elShiftFrom(s.name, s.start_minute, s.end_minute, s.is_overnight);
}

function elShiftFrom(
  name: string,
  st: number,
  en: number,
  overnight: boolean,
): ElShift | null {
  const endMin = en + (overnight || en <= st ? 1440 : 0);
  if (endMin <= st) return null;
  return { name, startMin: st, endMin, overnight: endMin > 1440 };
}

/** Ca qua đêm: giờ ĐỒNG HỒ rơi vào phần "sang hôm sau" → đẩy +1440 cho cùng trục với khung ca. */
function elOnAxis(minute: number, sh: ElShift | null): number {
  if (!sh || !sh.overnight) return minute;
  return minute < sh.startMin ? minute + 1440 : minute;
}

/** Suy ra kiểu vắng theo khung ca (dung sai 10'). Không biết ca ⇒ null (chip trung tính). */
function elKindOf(
  fromMinute: number,
  toMinute: number,
  sh: ElShift | null,
): ElKind | null {
  if (!sh) return null;
  const from = elOnAxis(fromMinute, sh);
  const to = elOnAxis(toMinute, sh);
  const span = sh.endMin - sh.startMin;
  const minutes = to - from;
  if (span <= 0 || minutes <= 0) return null;
  const half = span / 2;
  if (from <= sh.startMin + EL_TOLERANCE && minutes < half) return "late";
  if (to >= sh.endMin - EL_TOLERANCE && minutes < half) return "early";
  if (minutes >= half) return "half";
  return "mid";
}

/** "1 giờ 30 phút" — dòng phụ + hint (đọc thành tiếng được). */
function elDurLong(m: number): string {
  const h = Math.floor(m / 60);
  const mi = m % 60;
  if (h && mi) return `${h} giờ ${mi} phút`;
  if (h) return `${h} giờ`;
  return `${mi} phút`;
}

/** "1h30" / "45'" — chip trung tính khi KHÔNG biết ca. */
function elDurShort(m: number): string {
  const h = Math.floor(m / 60);
  const mi = m % 60;
  if (h && mi) return `${h}h${String(mi).padStart(2, "0")}`;
  if (h) return `${h}h`;
  return `${mi}'`;
}

/** 0.5 → "0,5" (dấu phẩy thập phân kiểu Việt). */
function elNum(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/** Quy phút vắng ra ngày phép — LÀM TRÒN LÊN 0,5, trần 1,0 (đúng công thức backend). */
function elLeaveCong(minutes: number, windowMin: number): number {
  if (minutes <= 0 || windowMin <= 0) return 0;
  return Math.min(1, Math.ceil((minutes / windowMin) * 2) / 2);
}

function elWeekday(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  if (!y || !m || !d) return "";
  return EL_WEEKDAYS[new Date(y, m - 1, d).getDay()] ?? "";
}

/** "2026-07-27" → "27/07" (dòng chính ô Ngày công). */
function elDayMonth(ymd: string): string {
  const [, m, d] = ymd.split("-");
  return d && m ? `${d}/${m}` : ymd;
}

/** Mã 1 (icon + CHỮ) + Mã 2 (mini-bar đặt đúng vị trí trong ca). */
function ElKindCell({
  r,
  shift,
}: {
  r: LateEarlyRequest;
  shift: ElShift | null;
}) {
  const kind = elKindOf(r.from_minute, r.to_minute, shift);
  if (kind === null || shift === null) {
    return (
      <div className="el-kindcell">
        <span
          className="el-kind el-kind--mid"
          title="Chưa biết khung ca của nhân viên nên không suy được kiểu vắng."
        >
          <Clock size={12} /> Vắng {elDurShort(r.minutes)}
        </span>
      </div>
    );
  }
  const meta = EL_KIND_META[kind];
  const span = shift.endMin - shift.startMin;
  const from = elOnAxis(r.from_minute, shift);
  const to = elOnAxis(r.to_minute, shift);
  const left = Math.max(
    0,
    Math.min(100, ((from - shift.startMin) / span) * 100),
  );
  const right = Math.max(
    0,
    Math.min(100, ((to - shift.startMin) / span) * 100),
  );
  const width = Math.max(5, Math.min(right - left, 100 - left));
  return (
    <div className="el-kindcell">
      <span className={`el-kind ${meta.cls}`}>
        <meta.Icon size={12} /> {meta.label}
      </span>
      <div
        className="el-bar"
        aria-hidden="true"
        title={`Ca ${elMinToHhmm(shift.startMin)}–${elMinToHhmm(shift.endMin)} · vắng ${elDurLong(r.minutes)}`}
      >
        <span
          className={`el-bar__seg el-bar__seg--${kind}`}
          style={{ left: `${left}%`, width: `${width}%` }}
        />
      </div>
    </div>
  );
}

/** Cột "Phép năm" — nhánh TIỀN tách riêng, không nhét vào màu chip kiểu. */
function ElLeaveCell({ r }: { r: LateEarlyRequest }) {
  if (r.leave_type_id != null) {
    return (
      <span
        className="el-leave"
        title={r.leave_type_name ?? "Trừ vào phép năm"}
      >
        −{elNum(r.leave_cong)} ngày
      </span>
    );
  }
  return (
    <span
      className="el-noleave"
      title="Không đụng quỹ phép — mất công phần vắng, nhưng không bị phạt."
    >
      Không lương
    </span>
  );
}

/** Bảng phiếu dùng chung cho cả 2 tab con. */
function ElTable({
  rows,
  shiftFor,
  showEmployee,
  selectable,
  showDecision,
  selected,
  onToggle,
  actions,
}: {
  rows: LateEarlyRequest[];
  shiftFor: (r: LateEarlyRequest) => ElShift | null;
  showEmployee: boolean;
  selectable: boolean;
  showDecision: boolean;
  selected: Set<number>;
  onToggle: (id: number) => void;
  actions: (r: LateEarlyRequest) => ReactNode;
}) {
  return (
    <div className="cc-timesheet-scroll-container">
      <table className="cc-timesheet-table">
        <thead>
          <tr>
            {selectable && <th style={{ width: "40px" }} aria-label="Chọn" />}
            {showEmployee && <th style={{ textAlign: "left" }}>Nhân viên</th>}
            <th style={{ textAlign: "left" }}>Ngày công</th>
            <th style={{ textAlign: "left" }}>Kiểu</th>
            <th style={{ textAlign: "left" }}>Vắng mặt</th>
            <th style={{ textAlign: "center" }}>Phép năm</th>
            <th style={{ textAlign: "left" }}>Lý do</th>
            <th style={{ textAlign: "center" }}>Trạng thái</th>
            {showDecision && (
              <th style={{ textAlign: "left" }}>Kết quả duyệt</th>
            )}
            <th style={{ textAlign: "right" }} aria-label="Thao tác" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              {selectable && (
                <td style={{ textAlign: "center" }}>
                  {r.status === "pending" && (
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => onToggle(r.id)}
                      aria-label={`Chọn phiếu của ${r.employee_name ?? `NV#${r.employee_id}`}`}
                    />
                  )}
                </td>
              )}
              {showEmployee && (
                <td>
                  <div className="cc-name-cell-wrapper">
                    <span className="cc-name-avatar">
                      {getInitials(r.employee_name)}
                    </span>
                    <span
                      className="cc-name-text-plain"
                      title={r.employee_name ?? `NV#${r.employee_id}`}
                    >
                      {r.employee_name ?? `NV#${r.employee_id}`}
                    </span>
                  </div>
                </td>
              )}
              <td>
                <span className="el-cell-main">{elDayMonth(r.work_date)}</span>
                <span className="el-cell-sub">{elWeekday(r.work_date)}</span>
              </td>
              <td>
                <ElKindCell r={r} shift={shiftFor(r)} />
              </td>
              <td>
                <span className="el-cell-mono">
                  {elMinToHhmm(r.from_minute)} → {elMinToHhmm(r.to_minute)}
                </span>
                <span className="el-cell-sub">{elDurLong(r.minutes)}</span>
              </td>
              <td style={{ textAlign: "center" }}>
                <ElLeaveCell r={r} />
              </td>
              <td>
                <div className="cc-reason-wrapper">
                  <span className="cc-reason-text">{r.reason || "—"}</span>
                </div>
              </td>
              <td style={{ textAlign: "center" }}>{statusBadge(r.status)}</td>
              {showDecision && (
                <td>
                  {r.decided_by_name || r.decided_at || r.decision_note ? (
                    <div className="cc-reason-wrapper">
                      <span className="cc-reason-text">
                        {r.decided_by_name ?? "—"}
                      </span>
                      {r.decided_at && (
                        <span className="el-cell-sub">
                          {fmtDateTime(r.decided_at)}
                        </span>
                      )}
                      {r.decision_note && (
                        <div className="cc-decision-note-sub">
                          💬 {r.decision_note}
                        </div>
                      )}
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
              )}
              <td style={{ textAlign: "right" }}>
                <div className="cc-rowact">{actions(r)}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Từ chối phải ghi lý do — ô bắt buộc trong modal (KHÔNG dùng window.prompt). */
function ElRejectModal({
  count,
  onClose,
  onConfirm,
}: {
  count: number;
  onClose: () => void;
  onConfirm: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <h2>{count > 1 ? `Từ chối ${count} phiếu` : "Từ chối phiếu"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          <label className="ns-field">
            <span className="ns-field__label">Lý do từ chối *</span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="vd: hôm đó xưởng chạy đơn gấp, không bố trí được"
              autoFocus
            />
          </label>
          <p className="np-hint">
            Lý do này hiện ở cột <b>Kết quả duyệt</b> để thợ biết vì sao bị từ
            chối.
          </p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            disabled={!note.trim()}
            onClick={() => onConfirm(note.trim())}
          >
            Từ chối
          </button>
        </footer>
      </div>
    </div>
  );
}

/** Form tạo / sửa phiếu. `forEmployee` = tổ trưởng khai hộ (tạo & duyệt luôn). */
function ElFormModal({
  token,
  forEmployee,
  editing,
  myShift,
  shiftById,
  roster,
  mine,
  onClose,
  onSaved,
  onOpenExisting,
}: {
  token: string;
  forEmployee: boolean;
  editing?: LateEarlyRequest | null;
  /** Ca của CHÍNH TÔI (nguồn `myStatus` — self-service, ai cũng gọi được). */
  myShift: ElShift | null;
  shiftById: Map<number, ElShift>;
  roster: ElRosterEmp[];
  /** Danh sách phiếu của tôi — dò trùng ngày TRƯỚC khi bấm Gửi. */
  mine: LateEarlyRequest[];
  onClose: () => void;
  onSaved: (msg: string) => void;
  onOpenExisting: (r: LateEarlyRequest) => void;
}) {
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [empQuery, setEmpQuery] = useState("");
  const [workDate, setWorkDate] = useState(editing?.work_date ?? isoToday());
  const [from, setFrom] = useState(
    editing ? elMinToHhmm(editing.from_minute) : "",
  );
  const [to, setTo] = useState(editing ? elMinToHhmm(editing.to_minute) : "");
  const [kind, setKind] = useState<ElFormKind | null>(null);
  const [deduct, setDeduct] = useState(
    editing ? editing.leave_type_id != null : false,
  );
  const [leaveTypeId, setLeaveTypeId] = useState<number | null>(
    editing?.leave_type_id ?? null,
  );
  const [reason, setReason] = useState(editing?.reason ?? "");
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [quotas, setQuotas] = useState<LeaveQuota[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Loại nghỉ có hạn mức năm (backend nhận `leave_type_id`, không nhận boolean) + số dư phép
  // của CHÍNH TÔI. Cả 2 endpoint đều là self-service của module `nghi_phep`.
  useEffect(() => {
    api.leaves
      .types(token)
      .then((r) => {
        const list = r.items.filter((t) => t.is_active && t.annual_quota > 0);
        setTypes(list);
        setLeaveTypeId((cur) => cur ?? (list.length ? list[0].id : null));
      })
      .catch(() => setTypes([]));
    if (!forEmployee) {
      api.leaves
        .me(token)
        .then((r) => setQuotas(r.quotas ?? []))
        .catch(() => setQuotas([]));
    }
  }, [token, forEmployee]);

  const pickedEmp =
    employeeId != null
      ? (roster.find((e) => e.id === employeeId) ?? null)
      : null;
  const activeShift = forEmployee
    ? pickedEmp?.default_shift_id != null
      ? (shiftById.get(pickedEmp.default_shift_id) ?? null)
      : null
    : myShift;

  // SỬA phiếu: suy lại kiểu từ khung ca (ca nạp async) để nút segmented sáng đúng ô. Chỉ chạy
  // MỘT LẦN — sau đó người dùng bấm gì là quyền của họ, đừng ghi đè lựa chọn đang gõ dở.
  const kindInferred = useRef(false);
  useEffect(() => {
    if (!editing || kindInferred.current || !activeShift) return;
    const k = elKindOf(editing.from_minute, editing.to_minute, activeShift);
    if (k === null) return;
    kindInferred.current = true;
    if (k !== "mid") setKind(k);
  }, [editing, activeShift]);

  // Checkbox trừ phép CHỈ mở cho nghỉ nửa buổi (đi muộn 20' mà tick trừ sẽ tròn thành 0,5 ngày
  // → lỗ hổng quỹ phép). Ngoại lệ: đang SỬA phiếu vốn có trừ phép mà chưa suy được kiểu ⇒ vẫn
  // phơi ra, nếu không lưu lại sẽ ÂM THẦM mất phần trừ phép cũ.
  const canDeduct =
    kind === "half" || (kind === null && editing?.leave_type_id != null);

  // Chọn kiểu vắng → TỰ ĐIỀN GIỜ theo mép ca: vừa ít thao tác, vừa khoá giờ đúng mép nên
  // chip suy ra kiểu đúng y như người dùng vừa chọn.
  function pickKind(k: ElFormKind) {
    setKind(k);
    if (k !== "half") setDeduct(false);
    const sh = activeShift;
    if (!sh) return;
    const span = sh.endMin - sh.startMin;
    if (k === "late") {
      setFrom(elMinToHhmm(sh.startMin));
      setTo(elMinToHhmm(Math.min(sh.startMin + 60, sh.endMin)));
    } else if (k === "early") {
      setTo(elMinToHhmm(sh.endMin));
      setFrom(elMinToHhmm(Math.max(sh.endMin - 60, sh.startMin)));
    } else {
      setFrom(elMinToHhmm(sh.startMin + Math.round(span / 2)));
      setTo(elMinToHhmm(sh.endMin));
    }
  }

  const fromRaw = elHhmmToMin(from);
  const toRaw = elHhmmToMin(to);
  // Ca qua đêm: đẩy giờ "sang hôm sau" về cùng trục ngày công với khung ca — nhờ vậy KHÔNG cần
  // checkbox "sang hôm sau" mà `from_minute`/`to_minute` gửi lên vẫn đúng trục backend.
  const fromAbs = fromRaw == null ? null : elOnAxis(fromRaw, activeShift);
  const toAbs = toRaw == null ? null : elOnAxis(toRaw, activeShift);
  const minutes = fromAbs != null && toAbs != null ? toAbs - fromAbs : null;
  const timeErr =
    minutes != null && minutes <= 0 ? "Đến lúc phải sau Vắng từ lúc." : null;

  const windowMin = activeShift
    ? activeShift.endMin - activeShift.startMin
    : EL_FALLBACK_WINDOW;
  const leaveCong = elLeaveCong(minutes ?? 0, windowMin);
  const quota =
    quotas.find((q) => q.leave_type_id === leaveTypeId) ??
    quotas.find((q) => q.annual_quota > 0) ??
    null;
  const remaining = quota?.remaining ?? 0;
  const shortOfLeave = !forEmployee && quotas.length > 0 && remaining < 0.5;

  // 1 phiếu/ngày: dò trong danh sách `mine` NGAY khi đổi ngày, đừng để bấm Gửi rồi mới báo.
  const clash = useMemo(() => {
    if (forEmployee || !workDate) return null;
    return (
      mine.find(
        (r) =>
          r.work_date === workDate &&
          (r.status === "pending" || r.status === "approved") &&
          r.id !== editing?.id,
      ) ?? null
    );
  }, [mine, workDate, forEmployee, editing]);

  const empOptions = useMemo(() => {
    const q = empQuery.trim().toLowerCase();
    const list = q
      ? roster.filter(
          (e) =>
            e.full_name.toLowerCase().includes(q) ||
            (e.code ?? "").toLowerCase().includes(q),
        )
      : roster;
    return list.slice(0, 300);
  }, [roster, empQuery]);

  async function save() {
    setErr(null);
    if (forEmployee && employeeId == null) return setErr("Cần chọn nhân viên.");
    if (!workDate) return setErr("Cần chọn ngày công.");
    if (fromAbs == null || toAbs == null)
      return setErr("Cần khai giờ bắt đầu và giờ kết thúc.");
    if (minutes == null || minutes <= 0)
      return setErr("Đến lúc phải sau Vắng từ lúc.");
    const input = {
      work_date: workDate,
      from_minute: fromAbs,
      to_minute: toAbs,
      reason: reason.trim() || null,
      leave_type_id: canDeduct && deduct ? leaveTypeId : null,
    };
    setBusy(true);
    try {
      if (editing) {
        await api.lateEarly.updateMine(token, editing.id, input);
        onSaved("Đã lưu phiếu — chờ tổ trưởng duyệt.");
      } else if (forEmployee) {
        await api.lateEarly.createFor(token, {
          ...input,
          employee_id: employeeId as number,
        });
        onSaved(`Đã tạo & duyệt phiếu cho ${pickedEmp?.full_name ?? "thợ"}.`);
      } else {
        await api.lateEarly.createMine(token, input);
        onSaved("Đã gửi phiếu — chờ tổ trưởng duyệt.");
      }
    } catch (e) {
      setErr(elErr(e)); // NGUYÊN VĂN `detail` của backend — đã tiếng Việt và khớp nhãn UI.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <h2>
            {editing
              ? "Sửa phiếu đi muộn / về sớm"
              : forEmployee
                ? "Khai hộ thợ — đi muộn / về sớm"
                : "Xin đi muộn / về sớm"}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}

          {forEmployee ? (
            <div className="el-balance el-balance--muted">
              <span>Số dư phép của thợ sẽ được hệ thống kiểm khi lưu.</span>
            </div>
          ) : quota ? (
            <div className="el-balance">
              <span>Phép năm · {quota.name}</span>
              <span className="el-balance__val">
                còn {elNum(remaining)} / {elNum(quota.annual_quota)} ngày
              </span>
            </div>
          ) : null}

          {forEmployee && (
            <label className="ns-field">
              <span className="ns-field__label">Nhân viên *</span>
              <input
                value={empQuery}
                onChange={(e) => setEmpQuery(e.target.value)}
                placeholder="Gõ tên hoặc mã NV để tìm…"
              />
              <select
                value={employeeId ?? ""}
                onChange={(e) =>
                  setEmployeeId(e.target.value ? Number(e.target.value) : null)
                }
              >
                <option value="">— chọn thợ trong tổ của bạn —</option>
                {empOptions.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                    {e.code ? ` · ${e.code}` : ""}
                    {e.department ? ` · ${e.department}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className={`ns-field ${forEmployee ? "el-field" : ""}`}>
            <span className="ns-field__label">Ngày công *</span>
            <input
              type="date"
              value={workDate}
              onChange={(e) => setWorkDate(e.target.value)}
            />
          </label>

          {clash && (
            <div className="banner banner--warn el-stack">
              <span>
                Ngày {elDayMonth(clash.work_date)} đã có phiếu{" "}
                <b>{statusText(clash.status)}</b>. Mỗi ngày chỉ được một phiếu —
                sửa hoặc hủy phiếu cũ trước.
              </span>
              <button
                className="btn btn--ghost"
                onClick={() => onOpenExisting(clash)}
              >
                Mở phiếu ngày đó
              </button>
            </div>
          )}

          <div className="el-stack">
            <span className="ns-field__label">Kiểu vắng *</span>
            <div className="np-seg el-stack-sm">
              {EL_FORM_KINDS.map((k) => (
                <button
                  key={k.value}
                  type="button"
                  className={`np-seg__btn ${kind === k.value ? "is-active" : ""}`}
                  onClick={() => pickKind(k.value)}
                >
                  <k.Icon size={13} /> {k.label}
                </button>
              ))}
            </div>
          </div>

          {activeShift ? (
            <div className="el-shiftline">
              <Clock size={13} />
              <span>
                Ca của {forEmployee ? "thợ" : "bạn"}: <b>{activeShift.name}</b>{" "}
                ·{" "}
                <span className="el-shiftline__time">
                  {elMinToHhmm(activeShift.startMin)}–
                  {elMinToHhmm(activeShift.endMin)}
                </span>
              </span>
            </div>
          ) : (
            <div className="el-shiftline">
              <AlertTriangle size={13} />
              <span>
                Chưa rõ khung ca{forEmployee ? " của thợ" : ""} — hãy tự khai
                giờ vắng bên dưới.
              </span>
            </div>
          )}

          <div className="el-timegrid">
            <label className="ns-field">
              <span className="ns-field__label">Vắng từ lúc *</span>
              <input
                type="time"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đến lúc *</span>
              <input
                type="time"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
          </div>

          <p className="np-hint">
            Khai đúng khoảng anh/chị <b>KHÔNG có mặt</b> ở xưởng. Ví dụ ca
            07:30–16:30:
            <br />• Đi muộn 1 tiếng → vắng từ <b>07:30</b> đến <b>08:30</b>
            <br />• Về sớm 2 tiếng → vắng từ <b>14:30</b> đến <b>16:30</b>
            <br />• Nghỉ nửa buổi chiều → vắng từ <b>12:30</b> đến <b>16:30</b>
          </p>
          {timeErr ? (
            <p className="np-hint np-hint--warn">{timeErr}</p>
          ) : minutes != null && minutes > 0 ? (
            <p className="np-hint np-hint--ok">Nghỉ {elDurLong(minutes)}</p>
          ) : null}

          {canDeduct && types.length > 0 && (
            <div className="el-stack">
              <label className="ns-check">
                <input
                  type="checkbox"
                  checked={deduct}
                  onChange={(e) => setDeduct(e.target.checked)}
                />
                Trừ vào phép năm — vẫn được trả lương phần vắng
              </label>
              {deduct ? (
                <>
                  <p className="np-hint np-hint--ok">
                    {leaveCong > 0
                      ? `Tiêu ${elNum(leaveCong)} ngày phép năm`
                      : "Khai giờ vắng để biết tiêu bao nhiêu ngày phép"}
                    {forEmployee
                      ? " · số dư của thợ được hệ thống kiểm khi lưu."
                      : leaveCong > 0
                        ? ` · Phép còn lại: ${elNum(remaining)} → ${elNum(Math.max(0, remaining - leaveCong))} ngày`
                        : ""}
                  </p>
                  <label className="ns-field el-field">
                    <span className="ns-field__label">Loại nghỉ</span>
                    <select
                      value={leaveTypeId ?? ""}
                      onChange={(e) =>
                        setLeaveTypeId(
                          e.target.value ? Number(e.target.value) : null,
                        )
                      }
                    >
                      {types.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {shortOfLeave && (
                    <div className="banner banner--warn el-stack">
                      <span>
                        Phép năm chỉ còn {elNum(remaining)} ngày — phiếu này cần{" "}
                        {elNum(leaveCong)} ngày. Bỏ tick để xin không lương (vẫn
                        không bị phạt).
                      </span>
                      <button
                        className="btn btn--ghost"
                        onClick={() => setDeduct(false)}
                      >
                        Bỏ tick, gửi không lương
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <p className="np-hint">
                  Không đụng quỹ phép · mất công phần vắng
                  {minutes != null && minutes > 0
                    ? ` (${elDurLong(minutes)})`
                    : ""}{" "}
                  · không bị phạt đi muộn.
                </p>
              )}
            </div>
          )}

          <label className="ns-field el-field">
            <span className="ns-field__label">Lý do</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="vd: con ốm, đưa đi khám"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy
              ? "Đang lưu…"
              : forEmployee
                ? "Tạo & duyệt luôn"
                : "Gửi phiếu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function LateEarlyTab({
  token,
  canApprove,
  onChanged,
  eventTick,
}: {
  token: string;
  canApprove: boolean;
  onChanged?: () => void;
  eventTick?: number;
}) {
  const [sub, setSub] = useState<"mine" | "queue">(
    canApprove ? "queue" : "mine",
  );
  // KHỞI TẠO `null` chứ KHÔNG phải `[]`: `[]` làm lúc đang fetch hiện "chưa có phiếu nào" — báo SAI.
  const [mine, setMine] = useState<LateEarlyRequest[] | null>(null);
  const [queue, setQueue] = useState<LateEarlyRequest[] | null>(null);
  const [hasEmployee, setHasEmployee] = useState(true);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [kindFilter, setKindFilter] = useState<Set<ElKind>>(new Set());
  const [pendingCount, setPendingCount] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState<null | "mine" | "for">(null);
  const [editing, setEditing] = useState<LateEarlyRequest | null>(null);
  const [rejecting, setRejecting] = useState<null | number[]>(null);
  // 2 state lỗi RIÊNG — dùng chung một `err` thì lỗi tab này hiện ở tab kia.
  const [errMine, setErrMine] = useState<string | null>(null);
  const [errQueue, setErrQueue] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [myShift, setMyShift] = useState<ElShift | null>(null);
  const [shiftById, setShiftById] = useState<Map<number, ElShift>>(new Map());
  const [roster, setRoster] = useState<ElRosterEmp[]>([]);

  useEffect(() => {
    // Ca của TÔI: `myStatus` là self-service (ai cũng gọi được) → nguồn ca cho tab "của tôi",
    // và là nguồn DUY NHẤT với người KHÔNG có quyền duyệt (họ không gọi được /roster).
    api.attendance
      .myStatus(token)
      .then((s) => setMyShift(elMakeShift(s.shift as MyShift | null)))
      .catch(() => setMyShift(null));
  }, [token]);

  // Roster của chính module `di_muon` (gác bằng `di_muon:approve`, backend đã lọc theo scope,
  // bỏ NV đã nghỉ và sắp theo tên). MỘT lời gọi nuôi cả dropdown "Khai hộ thợ" LẪN khung ca dùng
  // để suy kiểu vắng / vẽ mini-bar / tự điền giờ — khỏi phải mượn quyền `nhan_su:read`.
  useEffect(() => {
    if (!canApprove) return;
    api.lateEarly
      .roster(token)
      .then((r) => {
        setRoster(r.employees);
        const m = new Map<number, ElShift>();
        for (const s of r.shifts) {
          const sh = elShiftFromMinutes(s);
          if (sh) m.set(s.id, sh);
        }
        setShiftById(m);
      })
      .catch(() => {
        setRoster([]);
        setShiftById(new Map());
      });
  }, [token, canApprove]);

  const load = useCallback(() => {
    api.lateEarly
      .mine(token)
      .then((r) => {
        setHasEmployee(r.has_employee);
        setMine(r.items ?? []);
        setErrMine(null);
      })
      .catch((e) => {
        setMine([]);
        setErrMine(elErr(e));
      });
    if (canApprove) {
      api.lateEarly
        .list(token, statusFilter === "all" ? undefined : statusFilter)
        .then((r) => {
          setQueue(r.items);
          setErrQueue(null);
        })
        .catch((e) => {
          setQueue([]);
          setErrQueue(elErr(e));
        });
      api.lateEarly
        .summary(token)
        .then((s) => setPendingCount(s.pending_in_scope ?? 0))
        .catch(() => undefined);
    }
    // Hạ badge sidebar + chuông NGAY sau mỗi lần load (không bắt người dùng đổi màn).
    api.lateEarly.markSeen(token).catch(() => undefined);
    onChanged?.();
  }, [token, canApprove, statusFilter, onChanged]);

  // `eventTick` đổi = có sự kiện real-time (SSE) → tải lại bảng, khỏi bắt người dùng F5.
  useEffect(() => {
    load();
  }, [load, eventTick]);

  const shiftFor = useCallback(
    (r: LateEarlyRequest): ElShift | null => {
      const emp = roster.find((e) => e.id === r.employee_id);
      if (emp?.default_shift_id != null)
        return shiftById.get(emp.default_shift_id) ?? null;
      return null;
    },
    [roster, shiftById],
  );
  const shiftForMine = useCallback(
    (r: LateEarlyRequest): ElShift | null => myShift ?? shiftFor(r),
    [myShift, shiftFor],
  );

  // Chỉ hiện hàng chip lọc kiểu khi THỰC SỰ suy được kiểu — không thì nó lọc trắng bảng.
  const canInferKind = shiftById.size > 0 && roster.length > 0;
  const queueRows = useMemo(() => {
    if (!queue) return null;
    if (!canInferKind || kindFilter.size === 0) return queue;
    return queue.filter((r) => {
      const k = elKindOf(r.from_minute, r.to_minute, shiftFor(r));
      return k !== null && kindFilter.has(k);
    });
  }, [queue, kindFilter, canInferKind, shiftFor]);

  const selectable = useMemo(
    () =>
      new Set(
        (queueRows ?? [])
          .filter((r) => r.status === "pending")
          .map((r) => r.id),
      ),
    [queueRows],
  );
  const picked = useMemo(
    () => [...selected].filter((id) => selectable.has(id)),
    [selected, selectable],
  );

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleKind(k: ElKind) {
    setKindFilter((s) => {
      const next = new Set(s);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  async function run(fn: () => Promise<unknown>, scope: "mine" | "queue") {
    const setErr = scope === "mine" ? setErrMine : setErrQueue;
    setErr(null);
    setOkMsg(null);
    try {
      await fn();
      setSelected(new Set());
      load();
    } catch (e) {
      setErr(elErr(e));
    }
  }

  const showDecision = statusFilter !== "pending";

  return (
    <div>
      <div className="np-seg np-seg--tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={sub === "mine"}
          className={`np-seg__btn ${sub === "mine" ? "is-active" : ""}`}
          onClick={() => setSub("mine")}
        >
          Phiếu của tôi
        </button>
        {canApprove && (
          <button
            type="button"
            role="tab"
            aria-selected={sub === "queue"}
            className={`np-seg__btn ${sub === "queue" ? "is-active" : ""}`}
            onClick={() => setSub("queue")}
          >
            Duyệt phiếu{pendingCount ? ` (${pendingCount})` : ""}
          </button>
        )}
      </div>

      {okMsg && <div className="banner banner--success el-stack">{okMsg}</div>}

      {sub === "mine" && (
        <>
          <div className="cc-ts-toolbar">
            <div
              className="cc-info-card-note el-toolbar-grow"
              style={{ margin: 0, padding: "8px 12px" }}
            >
              <Info size={14} className="cc-note-icon" />
              <span>
                Khai đúng khoảng <b>không có mặt</b> ở xưởng. Phiếu được duyệt ={" "}
                <b>không bị phạt</b> đi muộn / về sớm đúng số phút đã xin.
              </span>
            </div>
            {hasEmployee && (
              <button
                className="btn btn--primary"
                onClick={() => setCreating("mine")}
              >
                <Plus size={14} /> Xin đi muộn / về sớm
              </button>
            )}
          </div>

          {!hasEmployee && (
            <div className="banner banner--warn el-stack">
              Tài khoản của bạn <b>chưa gắn hồ sơ nhân viên</b> nên chưa gửi
              phiếu được. Liên hệ HCNS.
            </div>
          )}
          {errMine && (
            <div className="banner banner--error el-stack">{errMine}</div>
          )}

          {mine === null ? (
            <p className="ns__empty">Đang tải phiếu…</p>
          ) : mine.length === 0 ? (
            <div className="el-empty">
              <p className="el-empty__title">
                Bạn chưa có phiếu đi muộn / về sớm nào.
              </p>
              <p className="el-empty__hint">
                Hôm nào đến muộn hoặc về sớm thì khai ở đây —{" "}
                <b>có phiếu được duyệt mới không bị phạt tiền</b>.
              </p>
              {hasEmployee && (
                <div className="el-empty__cta">
                  <button
                    className="btn btn--primary"
                    onClick={() => setCreating("mine")}
                  >
                    <Plus size={14} /> Xin đi muộn / về sớm
                  </button>
                </div>
              )}
            </div>
          ) : (
            <ElTable
              rows={mine}
              shiftFor={shiftForMine}
              showEmployee={false}
              selectable={false}
              showDecision
              selected={selected}
              onToggle={toggle}
              actions={(r) =>
                r.status === "pending" || r.status === "approved" ? (
                  <>
                    {r.status === "pending" && (
                      <button
                        className="btn btn--ghost"
                        onClick={() => setEditing(r)}
                      >
                        Sửa
                      </button>
                    )}
                    <button
                      className="btn btn--ghost cc-btn-reject"
                      onClick={() =>
                        run(() => api.lateEarly.cancel(token, r.id), "mine")
                      }
                    >
                      Hủy
                    </button>
                  </>
                ) : null
              }
            />
          )}
        </>
      )}

      {sub === "queue" && canApprove && (
        <>
          <div className="cc-ts-toolbar">
            <div className="cc-select-wrapper" style={{ width: "160px" }}>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setSelected(new Set());
                }}
                aria-label="Lọc theo trạng thái"
              >
                <option value="pending">Chờ duyệt</option>
                <option value="approved">Đã duyệt</option>
                <option value="rejected">Từ chối</option>
                <option value="all">Tất cả</option>
              </select>
            </div>
            {canInferKind && (
              <div className="el-filters el-toolbar-grow">
                {(Object.keys(EL_KIND_META) as ElKind[]).map((k) => {
                  const meta = EL_KIND_META[k];
                  return (
                    <button
                      key={k}
                      type="button"
                      className={`el-filter ${kindFilter.has(k) ? "is-on" : ""}`}
                      aria-pressed={kindFilter.has(k)}
                      onClick={() => toggleKind(k)}
                    >
                      <meta.Icon size={12} /> {meta.label}
                    </button>
                  );
                })}
              </div>
            )}
            <button
              className="btn btn--primary"
              onClick={() => setCreating("for")}
            >
              <Plus size={14} /> Khai hộ thợ
            </button>
          </div>

          {errQueue && (
            <div className="banner banner--error el-stack">{errQueue}</div>
          )}

          {picked.length > 0 && (
            <div className="cc-bulk-actions-floating">
              <span className="cc-bulk-label">
                Đã chọn {picked.length} phiếu
              </span>
              <div className="cc-bulk-btn-group">
                <button
                  className="btn btn--primary cc-btn-approve"
                  onClick={() =>
                    run(() => api.lateEarly.bulkApprove(token, picked), "queue")
                  }
                >
                  ✓ Duyệt {picked.length}
                </button>
                <button
                  className="btn btn--ghost cc-btn-reject"
                  onClick={() => setRejecting(picked)}
                >
                  ✕ Từ chối {picked.length}
                </button>
                <button
                  className="btn btn--ghost"
                  onClick={() => setSelected(new Set())}
                >
                  Bỏ chọn
                </button>
              </div>
            </div>
          )}

          {queueRows === null ? (
            <p className="ns__empty">Đang tải phiếu…</p>
          ) : queueRows.length === 0 ? (
            <div className="el-empty">
              <p className="el-empty__title">
                {statusFilter === "pending"
                  ? "Không có phiếu nào chờ bạn duyệt."
                  : "Không có phiếu nào khớp bộ lọc."}
              </p>
              {statusFilter === "pending" ? (
                <p className="el-empty__hint">
                  Đổi bộ lọc sang <b>Tất cả</b> để xem phiếu đã xử lý.
                </p>
              ) : kindFilter.size > 0 ? (
                <p className="el-empty__hint">
                  Bỏ bớt chip lọc kiểu để thấy thêm phiếu.
                </p>
              ) : null}
            </div>
          ) : (
            <ElTable
              rows={queueRows}
              shiftFor={shiftFor}
              showEmployee
              selectable
              showDecision={showDecision}
              selected={selected}
              onToggle={toggle}
              actions={(r) =>
                r.status === "pending" ? (
                  <div className="cc-approve-actions-cell">
                    <button
                      className="btn btn--primary cc-btn-approve"
                      onClick={() =>
                        run(() => api.lateEarly.approve(token, r.id), "queue")
                      }
                    >
                      Duyệt
                    </button>
                    <button
                      className="btn btn--ghost cc-btn-reject"
                      onClick={() => setRejecting([r.id])}
                    >
                      Từ chối
                    </button>
                  </div>
                ) : null
              }
            />
          )}
        </>
      )}

      {(creating || editing) && (
        <ElFormModal
          token={token}
          forEmployee={creating === "for"}
          editing={editing}
          myShift={myShift}
          shiftById={shiftById}
          roster={roster}
          mine={mine ?? []}
          onClose={() => {
            setCreating(null);
            setEditing(null);
          }}
          onSaved={(msg) => {
            setCreating(null);
            setEditing(null);
            setOkMsg(msg);
            load();
          }}
          onOpenExisting={(r) => {
            setCreating(null);
            setEditing(r);
            setSub("mine");
          }}
        />
      )}

      {rejecting && (
        <ElRejectModal
          count={rejecting.length}
          onClose={() => setRejecting(null)}
          onConfirm={(note) => {
            const ids = rejecting;
            setRejecting(null);
            run(
              () =>
                ids.length > 1
                  ? api.lateEarly.bulkReject(token, ids, note)
                  : api.lateEarly.reject(token, ids[0], note),
              "queue",
            );
          }}
        />
      )}
    </div>
  );
}
