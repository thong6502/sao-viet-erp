// Chấm công GPS (module `nhan_su`). 3 tab:
//   • Chấm công của tôi — lấy GPS trình duyệt, chấm VÀO/RA nếu trong bán kính điểm gần nhất.
//   • Điểm chấm công (HR) — khai toạ độ + bán kính; "Lấy vị trí hiện tại" để điền nhanh.
//   • Bảng chấm công (HR) — toàn bộ log.
// Server là cổng geofence thật (Haversine); ngoài phạm vi bị chặn cứng.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type AttendanceLog,
  type AdjustRequest,
  type AttendancePreview,
  type AttendanceStatus,
  type CheckResult,
  type DayDetail,
  type EmployeeRow,
  type TodayKpi,
  type Timesheet,
  type TimesheetRow,
  type AttendancePeriod,
  type WorkLocation,
  type WorkLocationInput,
  type WorkShift,
  type WorkShiftInput,
  type WorkCalendarConfig,
  type WorkCalendarConfigInput,
  type SpecialDay,
  type SpecialDayInput,
  type SpecialDaysOut,
  type CalendarMonth,
  type CalendarDayCell,
} from "../api/client";
import type { NavigateFn } from "../components/AppShell";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import {
  UserCheck,
  CalendarDays,
  MapPin,
  Clock,
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
  Map as MapIcon,
  ChevronLeft,
  ChevronRight,
  Info,
  LogIn,
  LogOut
} from "lucide-react";
import { MixDonut } from "../components/charts";
import "./nhan-su.css";
import "./cham-cong.css";

type Tab = "me" | "my-timesheet" | "locations" | "khai-ca" | "lich-le" | "logs" | "timesheet" | "yeu-cau";

const FAULT_OPTIONS: { value: string; label: string }[] = [
  { value: "nv_quen", label: "NV quên chấm" },
  { value: "may_hong", label: "Máy hỏng / mất điện" },
  { value: "duyet", label: "Được duyệt (công tác/họp)" },
  { value: "khac", label: "Khác" },
];
const FAULT_LABEL: Record<string, string> = Object.fromEntries(FAULT_OPTIONS.map((o) => [o.value, o.label]));

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

/** "HH:MM:SS" đã trôi kể từ mốc `fromIso` (coi chuỗi thiếu nhãn là UTC như fmtDateTime). */
function fmtElapsed(fromIso: string | null | undefined, now: number): string {
  if (!fromIso) return "00:00:00";
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(fromIso);
  const start = new Date(hasTz ? fromIso : `${fromIso}Z`).getTime();
  let s = Math.max(0, Math.floor((now - start) / 1000));
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
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
    const timeoutErr = Object.assign(new Error("Lấy vị trí quá lâu."), { code: 3 });
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
  if (code === 1) return "Bạn đã từ chối quyền vị trí. Hãy cho phép định vị rồi thử lại.";
  if (code === 2) return "Không lấy được vị trí. Kiểm tra Dịch vụ định vị (Location) của Windows đã bật chưa.";
  if (code === 3) return "Lấy vị trí quá lâu. Kiểm tra mạng và Dịch vụ định vị của Windows rồi thử lại.";
  if (e instanceof Error) return e.message;
  return "Không lấy được vị trí.";
}

export function ChamCongPage({ navigate, focusEmployeeId }: { navigate?: NavigateFn; focusEmployeeId?: number }) {
  const { token } = useAuth();
  const can = useCan();
  const canConfig = can("nhan_su", "update");   // cấu hình điểm/ca
  const canView = can("nhan_su", "read");       // xem toàn xưởng (theo scope)
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
          <p className="ns__sub">Chấm công theo vị trí GPS · phải ở gần điểm làm việc đã khai</p>
        </div>
      </header>

      <nav className="cc-tabs">
        <button className={tab === "me" ? "is-active" : ""} onClick={() => setTab("me")}>
          <UserCheck size={14} /> Chấm công của tôi
        </button>
        <button className={tab === "my-timesheet" ? "is-active" : ""} onClick={() => setTab("my-timesheet")}>
          <CalendarDays size={14} /> Công của tôi
        </button>
        {canConfig && (
          <button className={tab === "locations" ? "is-active" : ""} onClick={() => setTab("locations")}>
            <MapPin size={14} /> Điểm chấm công
          </button>
        )}
        {canConfig && (
          <button className={tab === "khai-ca" ? "is-active" : ""} onClick={() => setTab("khai-ca")}>
            <Clock size={14} /> Khai ca
          </button>
        )}
        {canConfig && (
          <button className={tab === "lich-le" ? "is-active" : ""} onClick={() => setTab("lich-le")}>
            <Calendar size={14} /> Lịch & Ngày lễ
          </button>
        )}
        {canView && (
          <button className={tab === "logs" ? "is-active" : ""} onClick={() => setTab("logs")}>
            <ClipboardList size={14} /> Bảng chấm công
          </button>
        )}
        {canView && (
          <button className={tab === "timesheet" ? "is-active" : ""} onClick={() => setTab("timesheet")}>
            <Table size={14} /> Bảng công tháng
          </button>
        )}
        {canView && (
          <button className={tab === "yeu-cau" ? "is-active" : ""} onClick={() => setTab("yeu-cau")}>
            <FileEdit size={14} /> Yêu cầu chỉnh công
          </button>
        )}
      </nav>

      {tab === "me" && <MyCheckIn token={token!} canConfig={canConfig} navigate={navigate} />}
      {tab === "my-timesheet" && <MyTimesheetTab token={token!} />}
      {tab === "locations" && canConfig && <LocationsTab token={token!} />}
      {tab === "khai-ca" && canConfig && <ShiftsTab token={token!} />}
      {tab === "lich-le" && canConfig && <CalendarTab token={token!} />}
      {tab === "logs" && canView && <LogsTab token={token!} focusEmployeeId={focusEmployeeId} />}
      {tab === "timesheet" && canView && <TimesheetTab token={token!} canAdjust={can("nhan_su", "adjust")} />}
      {tab === "yeu-cau" && canView && <AdjustRequestsTab token={token!} canAdjust={can("nhan_su", "adjust")} />}
    </main>
  );
}

// --- Tab: Chấm công của tôi -------------------------------------------------

function MyCheckIn({ token, canConfig, navigate }: { token: string; canConfig: boolean; navigate?: NavigateFn }) {
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
    return () => { mounted.current = false; };
  }, []);

  const load = useCallback(() => {
    api.attendance.myStatus(token).then(setStatus).catch(() => setStatus(null));
    api.attendance.myLogs(token).then((r) => setLogs(r.items)).catch(() => setLogs([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  // Clock live update
  useEffect(() => {
    const updateTime = () => {
      const d = new Date();
      setClockTime(d.toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Vòng geofence "sống": lấy GPS + dry-run tới server (không ghi log) để biết trong/ngoài vùng.
  const refreshPreview = useCallback(async () => {
    setLocating(true); setGeoErr(null);
    try {
      const pos = await getPosition();
      const p = await api.attendance.preview(token, pos.coords.latitude, pos.coords.longitude);
      if (mounted.current) setPreview(p);
    } catch (e) {
      if (mounted.current) setGeoErr(geoErrText(e));
    } finally {
      if (mounted.current) setLocating(false);
    }
  }, [token]);
  useEffect(() => {
    if (status?.has_employee && status.locations_configured) refreshPreview();
  }, [status?.has_employee, status?.locations_configured, refreshPreview]);

  // Đồng hồ LIVE khi đang trong ca (lần chấm gần nhất là VÀO → next_action = "out").
  useEffect(() => {
    if (status?.next_action !== "out") return;
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [status?.next_action]);

  async function doCheck(bypassConfirm = false) {
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
      const res = await api.attendance.check(token, pos.coords.latitude, pos.coords.longitude);
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
      const res = await api.attendance.check(token, pos.coords.latitude, pos.coords.longitude);
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
        Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong> nên không thể tự chấm công.
        Liên hệ HCNS để nối tài khoản với hồ sơ.
      </div>
    );
  }

  const isIn = status.next_action === "in";
  const outside = preview != null && !preview.within_range;
  const showTimer = status.next_action === "out" && status.last_check?.check_type === "in";
  const btnDisabled = checking || locating || !status.locations_configured || outside;

  const geoCls = locating ? "cc-geo-status--wait" : preview?.within_range ? "cc-geo-status--in" : preview ? "cc-geo-status--out" : "";

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
    <div className="cc-grid">
      <div className="cc-main-card">
        {status.employee_name && (
          <div className="cc-employee-avatar">
            {status.employee_name.split(" ").filter(Boolean).map(n => n[0]).slice(-2).join("").toUpperCase()}
          </div>
        )}
        <div className="cc-employee-name">{status.employee_name}</div>
        <div className="cc-employee-sub">
          {status.last_check
            ? `Lần gần nhất: chấm ${status.last_check.check_type === "in" ? "VÀO" : "RA"} lúc ${fmtDateTime(status.last_check.checked_at)}`
            : "Chưa có lần chấm công nào."}
        </div>

        {/* Live Clock Component */}
        <div className="cc-live-clock">
          <span>{clockH}</span>
          <span className="cc-clock-colon">:</span>
          <span>{clockM}</span>
          <span className="cc-clock-colon">:</span>
          <span style={{ opacity: 0.85 }}>{clockS}</span>
        </div>

        {/* Shift Details Tracker progress */}
        {status.shift && (
          <div className="cc-shift-tracker">
            <div className="cc-shift-title">
              <Clock size={14} /> Ca {status.shift.name} ({status.shift.start_time} - {status.shift.end_time})
            </div>
            <div className="cc-shift-time">
              {showTimer ? (
                <span>Thời gian đã làm: <b>{fmtElapsed(status.last_check?.checked_at, nowTick)}</b></span>
              ) : (
                <span>Chưa bắt đầu ca làm việc.</span>
              )}
            </div>
            {showTimer && (
              <div className="cc-shift-progress-bg">
                <div className="cc-shift-progress-fill" style={{ width: `${getShiftProgress(status.shift.start_time, status.shift.end_time, nowTick)}%` }} />
              </div>
            )}
          </div>
        )}

        {/* GPS Range Status Bar */}
        {status.locations_configured && (
          <div className={`cc-geo-status ${geoCls}`}>
            {locating ? <RefreshCw className="cc-animate-spin" size={14} /> : preview?.within_range ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
            <span style={{ flex: 1, textAlign: "left" }}>
              {locating ? "📡 Đang định vị GPS của bạn..."
                : preview?.within_range ? `✓ Trong phạm vi "${preview.nearest_name}" · cách ${Math.round(preview.distance_m ?? 0)} m`
                : preview ? `⊘ Ngoài phạm vi "${preview.nearest_name}" · còn cách ${Math.round(preview.meters_out ?? 0)} m`
                : "Bấm nút bên phải để tải lại phạm vi."}
            </span>
            <button className="cc-geo-status-refresh" onClick={refreshPreview} disabled={locating} title="Cập nhật vị trí">
              <RefreshCw size={12} className={locating ? "cc-animate-spin" : ""} />
            </button>
          </div>
        )}

        {/* Glow Pulsing Radar Button */}
        <div className="cc-radar-container">
          {!btnDisabled && <div className={`cc-radar-wave ${isIn ? "cc-radar-wave--in" : "cc-radar-wave--out"}`} />}
          {!btnDisabled && <div className={`cc-radar-wave ${isIn ? "cc-radar-wave--in" : "cc-radar-wave--out"}`} />}
          <button
            className={`cc-radar-btn ${outside ? "cc-radar-btn--locked" : isIn ? "cc-radar-btn--in" : "cc-radar-btn--out"}`}
            onClick={() => doCheck()}
            disabled={btnDisabled}
          >
            <span className="cc-radar-btn-icon">
              {locating ? <RefreshCw className="cc-animate-spin" size={24} /> : outside ? <Lock size={24} /> : <UserCheck size={24} />}
            </span>
            <span style={{ fontSize: "14px", marginTop: "2px" }}>
              {checking ? "Đang chấm…" : locating ? "Đang dò GPS…" : isIn ? "CHẤM VÀO" : "CHẤM RA"}
            </span>
          </button>
        </div>

        {!status.locations_configured && (
          <p className="cc-note">Chưa cấu hình điểm chấm công nào. Hãy liên hệ HCNS.</p>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", width: "100%", marginTop: "16px" }}>
          <button className="btn btn--ghost" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", padding: "10px var(--sp-2)", fontSize: "13px" }} onClick={() => setShowHistory(true)}>
            <ClipboardList size={14} /> Lịch sử
          </button>
          {navigate && (
            <button className="btn btn--ghost" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", padding: "10px var(--sp-2)", fontSize: "13px" }} onClick={() => navigate("nghi-phep")}>
              <Coffee size={14} /> Nghỉ phép
            </button>
          )}
        </div>

        {geoErr && (
          <div className="banner banner--error" style={{ marginTop: 12, width: "100%" }}>
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
          <div className={`banner ${result.success ? "banner--ok" : "banner--warn"}`} style={{ marginTop: 12, width: "100%" }}>
            {result.message}
          </div>
        )}

        {canConfig && (!status.locations_configured || (result != null && !result.within_range)) && (
          <div className="cc-setup" style={{ width: "100%" }}>
            <button className="btn btn--ghost cc-setup__btn" onClick={setPointHere} disabled={checking}>
              📍 Đặt điểm chấm công tại đây
            </button>
            <p className="cc-note">
              Tạo điểm chấm công mới tại tọa độ hiện tại (bán kính 150m) để chấm ngay.
            </p>
          </div>
        )}
      </div>

      {showHistory && (
        <MyHistoryModal logs={logs} onClose={() => setShowHistory(false)} />
      )}

      {showConfirmOut && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box cc-confirm-box" style={{ maxWidth: "420px" }}>
            <header className="ns-modal__head">
              <h2 style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0 }}>
                Xác nhận kết thúc ca
              </h2>
              <button className="ns-modal__x" onClick={() => setShowConfirmOut(false)}>×</button>
            </header>
            <div className="ns-modal__body" style={{ textAlign: "center", padding: "28px 20px" }}>
              <div className="cc-confirm-icon-wrap">
                <LogOut size={32} />
              </div>
              <p style={{ fontSize: "16px", fontWeight: "var(--fw-bold)", color: "var(--ink)", margin: "20px 0 8px 0" }}>
                Bạn sắp chấm RA
              </p>
              <p style={{ fontSize: "13px", color: "var(--ash)", lineHeight: "1.5", margin: 0 }}>
                Hành động này sẽ ghi nhận giờ kết thúc ca làm việc của bạn. Bạn chắc chắn muốn kết thúc ca chứ?
              </p>
            </div>
            <footer className="ns-modal__foot" style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
              <button className="btn btn--ghost" style={{ flex: 1 }} onClick={() => setShowConfirmOut(false)}>Hủy</button>
              <button className="btn btn--primary" style={{ flex: 1, background: "var(--signal)", borderColor: "var(--signal)", color: "#fff" }} onClick={() => doCheck(true)}>
                Đồng ý (RA)
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function MyHistoryModal({ logs, onClose }: { logs: AttendanceLog[]; onClose: () => void }) {
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box" style={{ maxWidth: "480px" }}>
        <header className="ns-modal__head">
          <h2 style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0 }}>
            <ClipboardList size={18} /> Lịch sử chấm công của tôi
          </h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body" style={{ maxHeight: "400px", overflowY: "auto" }}>
          <div className="cc-timeline" style={{ marginTop: 0 }}>
            {logs.map((l) => (
              <div key={l.id} className="cc-timeline-item">
                <div className={`cc-timeline-badge ${l.check_type === "in" ? "cc-timeline-badge--in" : "cc-timeline-badge--out"}`} />
                <div className="cc-timeline-content">
                  <div className="cc-timeline-left">
                    <span className="cc-timeline-action">
                      Chấm {l.check_type === "in" ? "VÀO" : "RA"}
                    </span>
                    <span className="cc-timeline-location">
                      <MapPin size={12} /> {l.location_name || "Vị trí không xác định"}
                    </span>
                  </div>
                  <div className="cc-timeline-right">
                    <span className="cc-timeline-time">{fmtDateTime(l.checked_at)}</span>
                    <div className="cc-timeline-distance">
                      {l.distance_m != null ? `Cự ly: ${Math.round(l.distance_m)}m` : "—"}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {logs.length === 0 && (
              <p className="ns__empty" style={{ background: "var(--paper)", padding: "16px", borderRadius: "8px", border: "1px solid var(--rule-soft)" }}>
                Chưa có dữ liệu lịch sử chấm công.
              </p>
            )}
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>Đóng</button>
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
  const [reqDate, setReqDate] = useState<string | null>(null);   // ngày đang xin chỉnh (mở modal)
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    setLoading(true);
    api.attendance.myTimesheet(token, year, month)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [token, year, month]);

  const loadReqs = useCallback(() => {
    api.attendance.myAdjustRequests(token).then((r) => setReqs(r.items)).catch(() => setReqs([]));
  }, [token]);
  useEffect(() => { loadReqs(); }, [loadReqs]);

  function openReq(dayNum: number) {
    setReqDate(`${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`);
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
      <div className="cc-ts-toolbar-container">
        <div className="cc-month-navigator">
          <button className="cc-month-nav-btn" onClick={() => shiftMonth(-1)} title="Tháng trước">
            <ChevronLeft size={16} />
          </button>
          <span className="cc-month-nav-label">
            Tháng {month} / {year}
          </span>
          <button className="cc-month-nav-btn" onClick={() => shiftMonth(1)} title="Tháng sau">
            <ChevronRight size={16} />
          </button>
          <div className="cc-month-picker-wrapper">
            <input type="month" className="cc-month-picker-hidden" value={ym} onChange={(e) => setYm(e.target.value)} id="cc-month-picker" />
            <label htmlFor="cc-month-picker" className="cc-month-picker-trigger" title="Chọn tháng nhanh">
              <CalendarDays size={14} /> Chọn tháng
            </label>
          </div>
        </div>

        <div className="cc-ts-info-group">
          <div className="cc-ts-legend">
            <span className="cc-ts-legend-title">Chú giải:</span>
            <span className="cc-badge-pill cc-badge-pill--primary">✓ Đi làm</span>
            <span className="cc-badge-pill cc-badge-pill--orange">+OT Làm thêm</span>
            <span className="cc-badge-pill cc-badge-pill--purple">Nghỉ lễ/Phép</span>
          </div>

          <div className="cc-ts-tip">
            <Info size={13} style={{ color: "var(--rust)" }} />
            <span>Bấm vào ô ngày trên lịch để gửi yêu cầu chỉnh công.</span>
          </div>
        </div>
      </div>
      {loading && <p className="ns__empty">Đang tải biểu công…</p>}
      {!loading && !row && <p className="ns__empty">Tháng này bạn chưa có dữ liệu chấm công.</p>}
      {!loading && row && data && (
        <div style={{ background: "var(--canvas)", padding: "20px", borderRadius: "10px", border: "1px solid var(--rule-soft)", boxShadow: "var(--shadow-1)" }}>
          <h4 className="ns-section__title" style={{ marginTop: 0 }}>Lịch công của tôi ({month}/{year})</h4>
          
          <div className="cc-month-grid">
            {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((w) => (
              <div key={w} style={{ textAlign: "center", fontWeight: "bold", fontSize: "12px", paddingBottom: "8px", color: "var(--ash)" }}>{w}</div>
            ))}
            {calendarCells.map((dayNum, idx) => {
              if (dayNum === null) return <div key={`empty-${idx}`} className="cc-month-cell cc-month-cell--empty" />;
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
                    if (day.late || day.early) cellClass += " cc-month-cell--makeup";
                    timeRange = `${day.first_in ?? "?"} - ${day.last_out ?? "?"}`;
                    statusLabel = day.cong != null ? `Công: ${day.cong}` : (day.hours != null ? `${day.hours}h` : "Đã chấm");
                    if (day.ot_minutes) otBadge = true;
                  }
                }
              }
              
              const currentDayOfWeek = new Date(year, month - 1, dayNum).getDay();
              const isWeekend = currentDayOfWeek === 0 || currentDayOfWeek === 6;
              if (!day && isWeekend) {
                cellClass += " cc-month-cell--weekend";
              }

              return (
                <div key={dayNum} className={cellClass} style={{ cursor: "pointer" }} onClick={() => openReq(dayNum)}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span className="cc-month-cell-num">{dayNum}</span>
                    {otBadge && <span className="cc-badge-pill cc-badge-pill--orange" style={{ padding: "1px 4px", fontSize: "9px" }}>+OT</span>}
                  </div>
                  <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--ink)", marginTop: "4px" }}>
                    {timeRange || "—"}
                  </div>
                  <div style={{ fontSize: "10px", color: "var(--ash)", marginTop: "2px", display: "flex", justifyContent: "space-between", width: "100%" }}>
                    <span>{statusLabel}</span>
                    {day?.late && <span style={{ color: "var(--signal)", fontWeight: "bold" }}>Muộn</span>}
                    {day?.early && <span style={{ color: "var(--amber-deep)", fontWeight: "bold" }}>Sớm</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {reqs.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h4 className="ns-section__title">Yêu cầu chỉnh công đã gửi</h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead><tr><th>Ngày</th><th>Chấm</th><th>Giờ đề xuất</th><th>Lý do</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
              <tbody>
                {reqs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.work_date}</td>
                    <td>{r.check_type === "in" ? "VÀO" : "RA"}</td>
                    <td>{r.suggested_time ?? "—"}</td>
                    <td>{r.reason}{r.decision_note ? ` · (${r.decision_note})` : ""}</td>
                    <td>{statusBadge(r.status)}</td>
                    <td>{r.status === "pending" && (
                      <button className="btn btn--ghost ns-danger" style={{ padding: "2px 8px" }} onClick={() => api.attendance.cancelAdjustRequest(token, r.id).then(loadReqs)}>Hủy</button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {reqDate && (
        <RequestAdjustModal token={token} date={reqDate}
          onClose={() => setReqDate(null)} onSaved={() => { setReqDate(null); loadReqs(); }} />
      )}
    </div>
  );
}

// NV gửi yêu cầu chỉnh công cho 1 ngày (self-service).
function RequestAdjustModal({ token, date, onClose, onSaved }: {
  token: string; date: string; onClose: () => void; onSaved: () => void;
}) {
  const [checkType, setCheckType] = useState<"in" | "out">("out");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!reason.trim()) { setError("Phải nhập lý do."); return; }
    setBusy(true); setError(null);
    try {
      await api.attendance.createAdjustRequest(token, {
        date, check_type: checkType, suggested_time: time || null, reason: reason.trim(),
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
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <div className="ns-grid">
            <label className="ns-field"><span className="ns-field__label">Chấm còn thiếu</span>
              <select value={checkType} onChange={(e) => setCheckType(e.target.value as "in" | "out")}>
                <option value="in">VÀO</option><option value="out">RA</option>
              </select></label>
            <label className="ns-field"><span className="ns-field__label">Giờ (gợi ý, không bắt buộc)</span>
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Lý do (bắt buộc)</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="vd: Quên chấm ra vì máy hết pin…" /></label>
          <p className="cc-note">Yêu cầu sẽ gửi HCNS duyệt. Được duyệt thì công tự cập nhật.</p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={submit} disabled={busy}>{busy ? "Đang gửi…" : "Gửi yêu cầu"}</button>
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
    api.attendance.locations(token).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function remove(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn xóa điểm chấm công này?")) return;
    await api.attendance.deleteLocation(token, id);
    load();
  }

  return (
    <div>
      <div className="cc-toolbar">
        <button className="btn btn--primary" onClick={() => setEditing("new")}>
          <Plus size={14} /> Thêm điểm chấm công
        </button>
      </div>

      <div className="cc-card-grid">
        {items?.map((l) => (
          <div key={l.id} className="cc-loc-card">
            <div>
              <div className="cc-loc-header">
                <span className="cc-loc-title">{l.name}</span>
                <span className={`cc-badge-pill ${l.is_active ? "cc-badge-pill--primary" : "cc-badge-pill--gray"}`}>
                  {l.is_active ? "Đang dùng" : "Đã tắt"}
                </span>
              </div>
              <div className="cc-loc-details">
                <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                  <MapIcon size={14} />
                  <span className="cc-loc-coord">{Number(l.latitude).toFixed(6)}, {Number(l.longitude).toFixed(6)}</span>
                </div>
                <div className="cc-loc-radius">
                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", border: "2px solid var(--rust)", background: "var(--rust-soft)" }} />
                  Bán kính geofence: <b>{l.radius_m} m</b>
                </div>
                {l.note && <div style={{ fontSize: "12px", color: "var(--ash)", marginTop: "4px" }}>Ghi chú: {l.note}</div>}
              </div>
            </div>
            <div className="cc-loc-actions">
              <button className="btn btn--ghost" style={{ padding: "4px 10px" }} onClick={() => setEditing(l)}>
                <Edit3 size={12} /> Sửa
              </button>
              <button className="btn btn--ghost ns-danger" style={{ padding: "4px 10px" }} onClick={() => remove(l.id)}>
                <Trash2 size={12} /> Xóa
              </button>
            </div>
          </div>
        ))}
        {items?.length === 0 && <div className="ns__empty" style={{ gridColumn: "1/-1" }}>Chưa có điểm chấm công nào được cấu hình.</div>}
      </div>

      {editing && (
        <LocationForm
          token={token}
          location={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

function LocationForm({ token, location, onClose, onSaved }: {
  token: string; location: WorkLocation | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkLocationInput>({
    name: location?.name ?? "",
    latitude: location?.latitude ?? 0,
    longitude: location?.longitude ?? 0,
    radius_m: location?.radius_m ?? 100,
    note: location?.note ?? "",
    is_active: location?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  function set<K extends keyof WorkLocationInput>(k: K, v: WorkLocationInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function useMyLocation() {
    setLocating(true);
    setError(null);
    try {
      const pos = await getPosition();
      setForm((f) => ({ ...f, latitude: Number(pos.coords.latitude.toFixed(7)), longitude: Number(pos.coords.longitude.toFixed(7)) }));
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
      if (location) await api.attendance.updateLocation(token, location.id, form);
      else await api.attendance.createLocation(token, form);
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
          <h2>{location ? "Sửa điểm chấm công" : "Thêm điểm chấm công"}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field"><span className="ns-field__label">Tên điểm *</span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field"><span className="ns-field__label">Vĩ độ (latitude)</span>
              <input type="number" step="0.0000001" value={form.latitude} onChange={(e) => set("latitude", Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Kinh độ (longitude)</span>
              <input type="number" step="0.0000001" value={form.longitude} onChange={(e) => set("longitude", Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Bán kính (mét)</span>
              <input type="number" min={1} value={form.radius_m} onChange={(e) => set("radius_m", Number(e.target.value))} /></label>
            <label className="ns-field"><span className="ns-field__label">Trạng thái</span>
              <label className="ns-check"><input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Đang dùng</label>
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Ghi chú (địa chỉ…)</span>
            <input value={form.note ?? ""} onChange={(e) => set("note", e.target.value)} /></label>
          <button className="btn btn--ghost" style={{ marginTop: 12 }} onClick={useMyLocation} disabled={locating}>
            {locating ? "Đang lấy…" : "📍 Lấy vị trí hiện tại của tôi"}
          </button>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Bảng chấm công (HR) -----------------------------------------------

function LogsTab({ token, focusEmployeeId }: { token: string; focusEmployeeId?: number }) {
  const [items, setItems] = useState<AttendanceLog[] | null>(null);
  const [focus, setFocus] = useState<number | undefined>(focusEmployeeId);
  const [kpi, setKpi] = useState<TodayKpi | null>(null);

  useEffect(() => setFocus(focusEmployeeId), [focusEmployeeId]);
  useEffect(() => {
    api.attendance.logs(token, focus).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, focus]);

  useEffect(() => {
    if (focus == null) {
      api.attendance.kpi(token).then(setKpi).catch(() => setKpi(null));
    }
  }, [token, focus]);

  const focusName = focus ? items?.find((l) => l.employee_id === focus)?.employee_name : undefined;

  // Render chart slices for Recharts MixDonut
  const chartSlices = kpi ? [
    { label: "Đang có mặt", value: kpi.present_now },
    { label: "Quên chấm RA", value: kpi.missing_out },
    { label: "Đi muộn hôm nay", value: kpi.late_today },
    { label: "YC chờ duyệt", value: kpi.pending_requests },
  ].filter(s => s.value > 0) : [];

  return (
    <div>
      {focus != null && (
        <div className="cc-focus">
          <span>Đang xem chấm công của <b>{focusName ?? `NV #${focus}`}</b></span>
          <button type="button" className="btn btn--ghost" onClick={() => setFocus(undefined)}>✕ Bỏ lọc — xem cả xưởng</button>
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
            <div style={{ background: "var(--paper)", padding: "16px", borderRadius: "10px", border: "1px solid var(--rule-soft)" }}>
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
                <div className="ns__empty" style={{ height: "160px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  Hôm nay chưa có dữ liệu chấm công.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {!items ? <p className="ns__empty">Đang tải lịch sử chấm công…</p> : <AttendanceTable logs={items} showEmployee={focus == null} />}
    </div>
  );
}

// --- Tab: Bảng công tháng (HR) ----------------------------------------------

// --- Tab: Khai ca (HR) ------------------------------------------------------

// --- Tab: Lịch làm việc & Ngày lễ (nền dùng chung cho Công / Phép / Lương) --

const WEEKDAY_FIELDS: { key: keyof WorkCalendarConfigInput; label: string }[] = [
  { key: "works_mon", label: "T2" }, { key: "works_tue", label: "T3" },
  { key: "works_wed", label: "T4" }, { key: "works_thu", label: "T5" },
  { key: "works_fri", label: "T6" }, { key: "works_sat", label: "T7" },
  { key: "works_sun", label: "CN" },
];
const KIND_LABEL: Record<string, string> = { off: "Nghỉ lễ", work: "Làm bù" };

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
    api.calendar.getConfig(token).then(setConfig).catch(() => setConfig(null));
  }, [token]);
  const loadSpecial = useCallback(() => {
    api.calendar.specialDays(token, year).then(setSpecial).catch(() => setSpecial(null));
  }, [token, year]);
  const loadPreview = useCallback(() => {
    api.calendar.month(token, year, previewMonth).then(setPreview).catch(() => setPreview(null));
  }, [token, year, previewMonth]);
  useEffect(() => { loadConfig(); }, [loadConfig]);
  useEffect(() => { loadSpecial(); }, [loadSpecial]);
  useEffect(() => { loadPreview(); }, [loadPreview]);

  function toggleDay(key: keyof WorkCalendarConfigInput) {
    setConfig((c) => (c ? { ...c, [key]: !c[key] } : c));
    setCfgMsg(null);
  }
  async function saveConfig() {
    if (!config) return;
    setCfgBusy(true); setCfgMsg(null);
    try {
      const saved = await api.calendar.updateConfig(token, {
        works_mon: config.works_mon, works_tue: config.works_tue, works_wed: config.works_wed,
        works_thu: config.works_thu, works_fri: config.works_fri, works_sat: config.works_sat,
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
    loadSpecial(); loadPreview();
  }

  return (
    <div className="cal">
      <div className="cal-grid-top">
        {/* Tuần làm việc chuẩn */}
        <section className="cal-panel">
          <h4 className="ns-section__title">Tuần làm việc chuẩn</h4>
          <p className="cc-note" style={{ marginTop: "4px" }}>
            Bật/tắt từng thứ. Ngày làm việc là mẫu tính công chuẩn tháng + trừ phép năm;
            ngày tắt = nghỉ tuần (không trừ phép). Ngày lễ khai riêng ở bên cạnh.
          </p>
          <div className="cal-week">
            {WEEKDAY_FIELDS.map((w) => (
              <label key={String(w.key)} className={`cal-week__day ${config?.[w.key] ? "is-on" : ""}`}>
                <input type="checkbox" checked={!!config?.[w.key]} onChange={() => toggleDay(w.key)} />
                <span>{w.label}</span>
              </label>
            ))}
          </div>
          <div className="cc-toolbar" style={{ marginTop: "auto", marginBottom: 0 }}>
            <button className="btn btn--primary" onClick={saveConfig} disabled={cfgBusy || !config}>
              {cfgBusy ? "Đang lưu…" : "Lưu tuần làm việc"}
            </button>
            {cfgMsg && <span className="cc-assign__msg" style={{ marginLeft: "12px", color: "var(--moss)", fontSize: "13px" }}>{cfgMsg}</span>}
          </div>
        </section>

        {/* Ngày lễ & làm bù */}
        <section className="cal-panel" style={{ display: "flex", flexDirection: "column" }}>
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
            <button className="btn btn--primary" onClick={() => setEditing("new")}>
              <Plus size={14} style={{ marginRight: "4px", display: "inline-block", verticalAlign: "middle" }} />
              <span>Thêm ngày</span>
            </button>
          </div>

          <div className="ns__tablewrap" style={{ flexGrow: 1, overflowY: "auto", maxHeight: "250px" }}>
            <table className="ns__table">
              <thead>
                <tr><th>Ngày</th><th>Tên</th><th>Loại</th><th>Hưởng lương</th><th style={{ width: "160px", textAlign: "right" }}></th></tr>
              </thead>
              <tbody>
                {special?.items.map((s) => (
                  <tr key={s.id}>
                    <td className="ns__code">{fmtDateVN(s.day)}</td>
                    <td style={{ fontWeight: "var(--fw-medium)" }}>{s.name}</td>
                    <td>
                      <span className={`ns-badge ${s.kind === "work" ? "ns-badge--info" : "ns-badge--ok"}`}>
                        {KIND_LABEL[s.kind]}
                      </span>
                    </td>
                    <td>{s.kind === "off" ? (s.is_paid ? "Có" : "Không") : "—"}</td>
                    <td className="cc-rowact" style={{ textAlign: "right" }}>
                      <button
                        className="btn btn--ghost btn--sm"
                        onClick={() => setEditing(s)}
                        style={{ padding: "4px 8px", marginRight: "4px" }}
                        title="Sửa"
                      >
                        <Edit3 size={13} style={{ display: "inline-block", verticalAlign: "middle", marginRight: "2px" }} />
                        Sửa
                      </button>
                      <button
                        className="btn btn--ghost btn--sm ns-danger"
                        onClick={() => removeSpecial(s.id)}
                        style={{ padding: "4px 8px" }}
                        title="Xóa"
                      >
                        <Trash2 size={13} style={{ display: "inline-block", verticalAlign: "middle", marginRight: "2px" }} />
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
                {!special && (
                  <tr><td colSpan={5} className="ns__empty">Đang tải…</td></tr>
                )}
                {special?.items.length === 0 && (
                  <tr><td colSpan={5} className="ns__empty">Chưa khai ngày đặc biệt nào cho năm {year}.</td></tr>
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
                Công chuẩn tháng {preview.month}/{preview.year}: <strong>{preview.working_days}</strong> công
                {preview.holidays.length > 0 && <> · {preview.holidays.length} ngày lễ</>}
              </span>
            </p>
            <div className="cc-month-grid">
              {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((d) => (
                <div key={d} style={{ textAlign: "center", fontWeight: "bold", fontSize: "12px", paddingBottom: "6px", color: "var(--ash)" }}>{d}</div>
              ))}
              {buildMonthGrid(preview).map((cell, i) =>
                cell ? (
                  <div key={i} className={`cc-month-cell cc-month-cell--${cell.kind}`} title={cell.name ?? ""}>
                    <span className="cc-month-cell-num">{cell.day}</span>
                    {cell.name && <span className="cc-month-cell-name">{cell.name}</span>}
                  </div>
                ) : <div key={i} className="cc-month-cell cc-month-cell--empty" />
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
        <SpecialDayForm token={token} special={editing === "new" ? null : editing} year={year}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); loadSpecial(); loadPreview(); }} />
      )}
    </div>
  );
}

function SpecialDayForm({ token, special, year, onClose, onSaved }: {
  token: string; special: SpecialDay | null; year: number; onClose: () => void; onSaved: () => void;
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
  function set<K extends keyof SpecialDayInput>(k: K, v: SpecialDayInput[K]) { setForm((f) => ({ ...f, [k]: v })); }
  async function save() {
    setBusy(true); setError(null);
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
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field"><span className="ns-field__label">Ngày *</span>
            <input type="date" value={form.day} onChange={(e) => set("day", e.target.value)} /></label>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Tên *</span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="vd Quốc khánh" /></label>
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Loại</span>
            <select value={form.kind} onChange={(e) => set("kind", e.target.value as "off" | "work")}>
              <option value="off">Nghỉ lễ (ngày lẽ ra làm nhưng nghỉ)</option>
              <option value="work">Làm bù (đi làm ngày lẽ ra nghỉ)</option>
            </select></label>
          {form.kind === "off" && (
            <label className="ns-check" style={{ marginTop: 12 }}>
              <input type="checkbox" checked={!!form.is_paid} onChange={(e) => set("is_paid", e.target.checked)} />
              Hưởng nguyên lương (cộng 1 công vào bảng công)
            </label>
          )}
          <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Ghi chú</span>
            <input value={form.note ?? ""} onChange={(e) => set("note", e.target.value)} placeholder="vd mùng 1 Tết Âm lịch" /></label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy || !form.name.trim() || !form.day}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ShiftsTab({ token }: { token: string }) {
  const [items, setItems] = useState<WorkShift[] | null>(null);
  const [editing, setEditing] = useState<WorkShift | "new" | null>(null);
  const load = useCallback(() => {
    api.attendance.shifts(token).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function remove(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn xóa ca làm việc này?")) return;
    await api.attendance.deleteShift(token, id);
    load();
  }
  return (
    <div>
      <div className="cc-toolbar">
        <button className="btn btn--primary" onClick={() => setEditing("new")}>
          <Plus size={14} /> Thêm ca làm việc
        </button>
      </div>

      <div className="cc-card-grid">
        {items?.map((s) => (
          <div key={s.id} className={`cc-shift-card ${s.is_overnight ? "cc-shift-card--overnight" : s.night_shift ? "cc-shift-card--night" : ""}`}>
            <div className="cc-shift-card-actions">
              <button className="btn btn--ghost" style={{ padding: "4px 6px", minWidth: "auto" }} onClick={() => setEditing(s)} title="Sửa ca">
                <Edit3 size={13} />
              </button>
              <button className="btn btn--ghost ns-danger" style={{ padding: "4px 6px", minWidth: "auto" }} onClick={() => remove(s.id)} title="Xóa ca">
                <Trash2 size={13} />
              </button>
            </div>
            
            <div className="cc-shift-card-header">
              <span className="cc-shift-name">{s.name}</span>
              <span className={`cc-badge-pill ${s.is_active ? "cc-badge-pill--primary" : "cc-badge-pill--gray"}`}>
                {s.is_active ? "Đang hoạt động" : "Đã tắt"}
              </span>
            </div>
            <div className="cc-shift-times">
              <Clock size={13} style={{ color: "var(--ash)" }} />
              <span>{s.start_time} – {s.end_time}</span>
            </div>
            <div className="cc-shift-meta">
              <span className="cc-badge-pill cc-badge-pill--gray">Dung sai trễ: {s.grace_minutes}′</span>
              {s.is_overnight && <span className="cc-badge-pill cc-badge-pill--purple"><Moon size={10} style={{ display: "inline", verticalAlign: "middle", marginRight: "2px" }} /> Qua đêm</span>}
              {s.night_shift && <span className="cc-badge-pill cc-badge-pill--orange"><Coffee size={10} style={{ display: "inline", verticalAlign: "middle", marginRight: "2px" }} /> Ca đêm</span>}
              {!s.is_overnight && !s.night_shift && <span className="cc-badge-pill cc-badge-pill--primary"><Sun size={10} style={{ display: "inline", verticalAlign: "middle", marginRight: "2px" }} /> Ca ngày</span>}
            </div>
            {s.note && <div style={{ fontSize: "12px", color: "var(--ash)", marginTop: "8px" }}>Ghi chú: {s.note}</div>}
          </div>
        ))}
        {items?.length === 0 && <div className="ns__empty" style={{ gridColumn: "1/-1" }}>Chưa có ca làm việc nào được cấu hình.</div>}
      </div>

      <AssignShiftPanel token={token} shifts={items ?? []} />

      {editing && (
        <ShiftForm token={token} shift={editing === "new" ? null : editing}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

// Gán ca mặc định cho nhân viên (đơn lẻ auto-save + gán hàng loạt theo bộ lọc).
function AssignShiftPanel({ token, shifts }: { token: string; shifts: WorkShift[] }) {
  const [emps, setEmps] = useState<EmployeeRow[] | null>(null);
  const [deptFilter, setDeptFilter] = useState<number | "">("");
  const [bulkShift, setBulkShift] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    api.employees.list(token, { size: 200, sort: "code" })
      .then((r) => setEmps(r.items)).catch(() => setEmps([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const depts = Array.from(
    new Map((emps ?? []).filter((e) => e.department_id != null)
      .map((e) => [e.department_id!, e.department_name ?? `Phòng #${e.department_id}`])).entries()
  );
  const shown = (emps ?? []).filter((e) => deptFilter === "" || e.department_id === deptFilter);

  async function assignOne(id: number, shiftId: number | null) {
    setMsg(null);
    await api.employees.setShift(token, id, shiftId);
    setEmps((list) => (list ?? []).map((e) => (e.id === id ? { ...e, default_shift_id: shiftId } : e)));
  }

  async function applyBulk() {
    if (bulkShift === "" || !shown.length) return;
    setBusy(true); setMsg(null);
    try {
      for (const e of shown) await assignOne(e.id, bulkShift);
      setMsg(`Đã gán ca cho ${shown.length} nhân viên.`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Lỗi khi gán ca.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cc-assign">
      <h4 className="ns-section__title">Gán ca mặc định</h4>
      <p className="cc-note">Ca mặc định dùng để tính công ở Bảng công tháng. Chọn ca ở từng dòng để lưu ngay,
        hoặc lọc theo phòng/tổ rồi “Gán hàng loạt”.</p>
      <div className="cc-toolbar cc-assign__bar">
        <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">Tất cả phòng/tổ</option>
          {depts.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <select value={bulkShift} onChange={(e) => setBulkShift(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">— chọn ca để gán hàng loạt —</option>
          {shifts.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.start_time}–{s.end_time})</option>)}
        </select>
        <button className="btn btn--ghost" onClick={applyBulk} disabled={busy || bulkShift === "" || !shown.length}>
          {busy ? "Đang gán…" : `Gán hàng loạt (${shown.length})`}
        </button>
        {msg && <span className="cc-assign__msg">{msg}</span>}
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr><th>Mã</th><th>Họ tên</th><th>Phòng/Tổ</th><th>Ca mặc định</th></tr>
          </thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.id}>
                <td className="ns__code">{e.code}</td>
                <td>{e.full_name}</td>
                <td>{e.department_name ?? "—"}</td>
                <td>
                  <select
                    value={e.default_shift_id ?? ""}
                    onChange={(ev) => assignOne(e.id, ev.target.value === "" ? null : Number(ev.target.value))}
                  >
                    <option value="">— chưa gán —</option>
                    {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </td>
              </tr>
            ))}
            {emps && shown.length === 0 && <tr><td colSpan={4} className="ns__empty">Không có nhân viên phù hợp bộ lọc.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ShiftForm({ token, shift, onClose, onSaved }: {
  token: string; shift: WorkShift | null; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkShiftInput>({
    name: shift?.name ?? "", start_time: shift?.start_time ?? "08:00", end_time: shift?.end_time ?? "17:00",
    is_overnight: shift?.is_overnight ?? false, night_shift: shift?.night_shift ?? false,
    grace_minutes: shift?.grace_minutes ?? 5, note: shift?.note ?? "", is_active: shift?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof WorkShiftInput>(k: K, v: WorkShiftInput[K]) { setForm((f) => ({ ...f, [k]: v })); }
  async function save() {
    setBusy(true); setError(null);
    try {
      if (shift) await api.attendance.updateShift(token, shift.id, form);
      else await api.attendance.createShift(token, form);
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
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field"><span className="ns-field__label">Tên ca *</span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Hành chính / Ca 1…" /></label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field"><span className="ns-field__label">Giờ vào ca</span>
              <input type="time" value={form.start_time} onChange={(e) => set("start_time", e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Giờ ra ca</span>
              <input type="time" value={form.end_time} onChange={(e) => set("end_time", e.target.value)} /></label>
            <label className="ns-field"><span className="ns-field__label">Dung sai đi muộn (phút)</span>
              <input type="number" min={0} value={form.grace_minutes} onChange={(e) => set("grace_minutes", Number(e.target.value))} /></label>
          </div>
          <label className="ns-check" style={{ marginTop: 12 }}>
            <input type="checkbox" checked={!!form.is_overnight} onChange={(e) => set("is_overnight", e.target.checked)} />
            Ca qua đêm (ra hôm sau, vd 22:00→06:00)
          </label>
          <label className="ns-check">
            <input type="checkbox" checked={!!form.night_shift} onChange={(e) => set("night_shift", e.target.checked)} />
            Ca đêm (có phụ cấp)
          </label>
          <label className="ns-check">
            <input type="checkbox" checked={!!form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Đang dùng
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu"}</button>
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
  onClose
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
      <div className="ns-modal__box cc-emp-cal-modal-box" style={{ maxWidth: "700px" }}>
        <header className="ns-modal__head">
          <h2 style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0 }}>
            <Calendar size={18} /> Lịch công tháng {month}/{year} · {employeeName}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {/* Summary metrics of the employee */}
          <div className="cc-emp-cal-summary-grid">
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Số ngày công</span>
              <span className="cc-emp-cal-summary-val">{employeeRow.total_cong ?? workedDays} công</span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Tổng giờ làm</span>
              <span className="cc-emp-cal-summary-val">{employeeRow.total_hours ?? 0}h</span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Tăng ca (OT)</span>
              <span className="cc-emp-cal-summary-val">{(totalOtMinutes / 60).toFixed(1)}h</span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Muộn / Sớm</span>
              <span className="cc-emp-cal-summary-val text-warn">{lateDays} / {earlyDays} lần</span>
            </div>
          </div>

          {/* Calendar grid */}
          <div className="cc-month-grid" style={{ marginTop: "16px" }}>
            {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((w) => (
              <div key={w} style={{ textAlign: "center", fontWeight: "bold", fontSize: "11px", paddingBottom: "6px", color: "var(--ash)" }}>{w}</div>
            ))}
            {calendarCells.map((dayNum, idx) => {
              if (dayNum === null) return <div key={`empty-${idx}`} className="cc-month-cell cc-month-cell--empty" />;
              
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
                    if (day.late || day.early) cellClass += " cc-month-cell--makeup";
                    timeRange = `${day.first_in ?? "?"} - ${day.last_out ?? "?"}`;
                    statusLabel = day.cong != null ? `Công: ${day.cong}` : (day.hours != null ? `${day.hours}h` : "Đã chấm");
                    if (day.ot_minutes) otBadge = true;
                  }
                }
              }

              const currentDayOfWeek = new Date(year, month - 1, dayNum).getDay();
              const isWeekendCell = currentDayOfWeek === 0 || currentDayOfWeek === 6;
              if (!day && isWeekendCell) {
                cellClass += " cc-month-cell--weekend";
              }

              return (
                <div key={dayNum} className={cellClass}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span className="cc-month-cell-num">{dayNum}</span>
                    {otBadge && <span className="cc-badge-pill cc-badge-pill--orange" style={{ padding: "1px 4px", fontSize: "9px" }}>+OT</span>}
                  </div>
                  <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--ink)", marginTop: "4px" }}>
                    {timeRange || "—"}
                  </div>
                  <div style={{ fontSize: "10px", color: "var(--ash)", marginTop: "2px", display: "flex", flexWrap: "wrap", gap: "2px", justifyContent: "space-between", width: "100%" }}>
                    <span>{statusLabel}</span>
                    {day?.late && <span style={{ color: "var(--signal)", fontWeight: "bold" }}>Muộn</span>}
                    {day?.early && <span style={{ color: "var(--amber-deep)", fontWeight: "bold" }}>Sớm</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>Đóng</button>
        </footer>
      </div>
    </div>
  );
}

function TimesheetTab({ token, canAdjust }: { token: string; canAdjust: boolean }) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [data, setData] = useState<Timesheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [deptId, setDeptId] = useState<number | "">("");
  const [depts, setDepts] = useState<{ id: number; name: string }[]>([]);
  const [openDay, setOpenDay] = useState<{ employeeId: number; employeeName: string; date: string } | null>(null);
  const [period, setPeriod] = useState<AttendancePeriod | null>(null);
  const [periodBusy, setPeriodBusy] = useState(false);
  const [periodMsg, setPeriodMsg] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [selectedEmployeeCal, setSelectedEmployeeCal] = useState<{ row: TimesheetRow; name: string } | null>(null);
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    api.employees.meta(token).then((m) => setDepts(m.departments)).catch(() => setDepts([]));
  }, [token]);

  const loadPeriod = useCallback(() => {
    api.attendance.period(token, year, month).then(setPeriod).catch(() => setPeriod(null));
  }, [token, year, month]);
  useEffect(() => { loadPeriod(); setPeriodMsg(null); }, [loadPeriod]);

  const reload = useCallback(() => {
    setLoading(true);
    api.attendance.timesheet(token, year, month, deptId === "" ? null : deptId)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [token, year, month, deptId]);
  useEffect(() => { reload(); }, [reload]);

  async function doLockPeriod() {
    setPeriodBusy(true); setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.lockPeriod(token, year, month));
      setPeriodMsg({ text: "Đã chốt công tháng.", type: "success" });
    } catch (e) {
      setPeriodMsg({ text: e instanceof Error ? e.message : "Lỗi khi chốt công.", type: "error" });
    } finally { setPeriodBusy(false); }
  }
  async function doReopenPeriod() {
    setPeriodBusy(true); setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.reopenPeriod(token, year, month));
      setPeriodMsg({ text: "Đã mở lại kỳ công.", type: "success" });
    } catch (e) {
      setPeriodMsg({ text: e instanceof Error ? e.message : "Lỗi khi mở kỳ công.", type: "error" });
    } finally { setPeriodBusy(false); }
  }

  function openCell(employeeId: number, employeeName: string, dayNum: number) {
    const date = `${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
    setOpenDay({ employeeId, employeeName, date });
  }

  async function exportCsv() {
    setDownloading(true);
    try {
      const url = await api.attendance.timesheetCsvBlobUrl(token, year, month, deptId === "" ? null : deptId);
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

  const days = data ? Array.from({ length: data.days_in_month }, (_, i) => i + 1) : [];

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
        <div className={`cc-ts-kpi-card cc-ts-kpi-card--period ${period?.status === "locked" ? "is-locked" : "is-draft"}`}>
          <div className="cc-ts-kpi-icon">
            {period?.status === "locked" ? <Lock size={18} /> : <Unlock size={18} />}
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
      {period && period.status !== "locked" && (period.hanging_days > 0 || period.pending_leaves + period.pending_adjusts > 0) && (
        <div className="banner banner--warn cc-ts-warn-banner" style={{ marginBottom: "16px" }}>
          <AlertTriangle size={14} style={{ marginRight: "6px" }} />
          <span>
            Kỳ công có <strong>{period.hanging_days}</strong> ngày treo (thiếu chấm RA) và <strong>{period.pending_leaves + period.pending_adjusts}</strong> đơn chờ duyệt.
          </span>
        </div>
      )}

      {periodMsg && (
        <div className={`banner ${periodMsg.type === "error" ? "banner--error" : "banner--ok"} cc-ts-msg-banner`} style={{ marginBottom: "16px" }}>
          {periodMsg.text}
        </div>
      )}

      {/* 2. Redesigned Filter & Actions Bar */}
      <div className="cc-ts-header-actions">
        <div className="cc-ts-filters">
          <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} className="cc-ts-input-month" />
          <select value={deptId} onChange={(e) => setDeptId(e.target.value === "" ? "" : Number(e.target.value))} className="cc-ts-select-dept">
            <option value="">Tất cả phòng/tổ</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <div className="cc-ts-legend-strip">
            <span className="cc-ts-legend-item cc-ts-legend-item--work">Công</span>
            <span className="cc-ts-legend-item cc-ts-legend-item--late">Muộn</span>
            <span className="cc-ts-legend-item cc-ts-legend-item--early">Sớm</span>
            <span className="cc-ts-legend-item cc-ts-legend-item--leave">Nghỉ/Phép</span>
            <span className="cc-ts-legend-item cc-ts-legend-item--ot">OT (+)</span>
          </div>
        </div>

        <div className="cc-ts-actions">
          <button className="btn btn--ghost cc-ts-btn-export" onClick={exportCsv} disabled={downloading || !data?.rows.length}>
            {downloading ? <RefreshCw className="cc-animate-spin" size={14} /> : <FileEdit size={14} />}
            <span>{downloading ? "Đang xuất…" : "Xuất CSV"}</span>
          </button>

          {canAdjust && period && (
            <div className="cc-ts-action-lock-wrapper">
              {period.status === "draft" ? (
                <button className="btn btn--primary cc-ts-btn-lock" onClick={doLockPeriod} disabled={periodBusy}>
                  <Lock size={14} />
                  <span>{periodBusy ? "Đang khóa…" : "Chốt công tháng"}</span>
                </button>
              ) : (
                <button className="btn btn--ghost cc-ts-btn-unlock" onClick={doReopenPeriod} disabled={periodBusy || period.payroll_locked} title={period.payroll_locked ? "Kỳ lương đã chốt — không mở lại kỳ công" : ""}>
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
                    <th key={d} className={`cc-day-hdr-v2 ${weekend ? "cc-day-hdr-v2--weekend" : ""}`}>
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
                  onCellClick={(dayNum) => openCell(r.employee_id, r.employee_name, dayNum)}
                  onNameClick={() => setSelectedEmployeeCal({ row: r, name: r.employee_name })}
                />
              ))}
              {data.rows.length === 0 && (
                <tr><td colSpan={days.length + 5} className="ns__empty">Chưa có dữ liệu chấm công tháng này.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {openDay && (
        <DayDetailModal
          token={token} canAdjust={canAdjust}
          employeeId={openDay.employeeId} employeeName={openDay.employeeName} date={openDay.date}
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
  onNameClick
}: {
  row: TimesheetRow;
  days: number[];
  isWeekend: (dayNum: number) => boolean;
  onCellClick?: (dayNum: number) => void;
  onNameClick?: () => void;
}) {
  const clickable = !!onCellClick;
  const cellProps = (d: number) => clickable
    ? { role: "button" as const, tabIndex: 0, onClick: () => onCellClick!(d), style: { cursor: "pointer" } }
    : {};
  return (
    <tr>
      <td className="cc-sticky-col-code">{row.employee_code}</td>
      <td className="cc-sticky-col-name">
        <div className="cc-name-cell-wrapper">
          <span className="cc-name-avatar">{getInitials(row.employee_name)}</span>
          <span className="cc-name-link" onClick={onNameClick} title="Xem lịch công tháng">
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
              <span className="cc-cell-badge cc-cell-badge--leave" title={`Nghỉ: ${day.leave}`}>
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
        
        const label = day.cong != null ? String(day.cong) : (day.hours != null ? `${day.hours}h` : "•");
        const tip = `${day.first_in ?? "?"}–${day.last_out ?? "?"}`
          + (day.late ? " · đi muộn" : "") + (day.early ? " · về sớm" : "")
          + (day.ot_minutes ? ` · OT ${day.ot_minutes}′` : "") + (day.night ? " · ca đêm" : "");
          
        return (
          <td key={d} className={cellClass} {...cellProps(d)}>
            <span className={badgeClass} title={tip}>
              {label}
              {day.ot_minutes ? <span className="cc-cell-ot-dot" title={`Tăng ca: ${day.ot_minutes}′`}>+</span> : null}
            </span>
          </td>
        );
      })}
      <td style={{ fontWeight: "bold", textAlign: "center" }}>{row.total_cong != null ? row.total_cong : row.total_days}</td>
      <td style={{ fontWeight: "bold", textAlign: "center" }}>{row.total_hours}h</td>
    </tr>
  );
}

// "Ô biết nói": chi tiết punch 1 ngày của 1 NV + chấm bù/sửa (fault_party) có audit.

function DayDetailModal({ token, canAdjust, employeeId, employeeName, date, onClose, onChanged }: {
  token: string; canAdjust: boolean; employeeId: number; employeeName: string; date: string;
  onClose: () => void; onChanged: () => void;
}) {
  const [detail, setDetail] = useState<DayDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkType, setCheckType] = useState<"in" | "out">("in");
  const [time, setTime] = useState("08:00");
  const [fault, setFault] = useState("nv_quen");
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    api.attendance.day(token, employeeId, date).then(setDetail).catch(() => setDetail(null));
  }, [token, employeeId, date]);
  useEffect(() => { load(); }, [load]);

  async function addPunch() {
    if (!reason.trim()) { setError("Phải nhập lý do."); return; }
    setBusy(true); setError(null);
    try {
      const d = await api.attendance.adjust(token, {
        employee_id: employeeId, date, check_type: checkType, time, reason: reason.trim(), fault_party: fault,
      });
      setDetail(d); setReason(""); onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi chấm bù.");
    } finally { setBusy(false); }
  }

  async function removePunch(logId: number) {
    setBusy(true); setError(null);
    try {
      const d = await api.attendance.deleteManualLog(token, logId, employeeId, date);
      setDetail(d); onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi xóa.");
    } finally { setBusy(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Chi tiết chấm công</h2>
            <p className="cc-modal-subtitle">{employeeName} · Ngày {date}</p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error">{error}</div>}
          {!detail ? <p className="ns__empty">Đang tải…</p> : (
            <>
              {/* Summary Strip */}
              <div className="cc-day-summary-strip">
                <div className="cc-day-summary-item">
                  <span className="cc-day-summary-lbl">Ca làm việc</span>
                  <span className="cc-day-summary-val cc-badge-shift">{detail.shift_name ?? "Chưa gán"}</span>
                </div>
                <div className="cc-day-summary-item">
                  <span className="cc-day-summary-lbl">Ngày công</span>
                  <span className="cc-day-summary-val cc-badge-cong">{detail.cong != null ? detail.cong : "—"}</span>
                </div>
                {detail.reason && (
                  <div className="cc-day-summary-item">
                    <span className="cc-day-summary-lbl">Cảnh báo</span>
                    <span className="cc-day-summary-val cc-badge-warn">⚠ {detail.reason}</span>
                  </div>
                )}
              </div>

              {/* Punch Timeline */}
              <div className="cc-punch-timeline-container">
                <h4 className="cc-section-title-mini">Lịch sử lượt chấm công</h4>
                <div className="cc-timeline-flow">
                  {detail.punches.map((p, idx) => {
                    const isIn = p.check_type === "in";
                    return (
                      <div className="cc-timeline-item" key={p.id}>
                        <div className="cc-timeline-connector">
                          <div className={`cc-timeline-dot ${isIn ? "is-in" : "is-out"}`} />
                          {idx < detail.punches.length - 1 && <div className="cc-timeline-line" />}
                        </div>
                        <div className="cc-timeline-content">
                          <div className="cc-timeline-header">
                            <span className="cc-timeline-time">{p.time}</span>
                            <span className={`cc-timeline-badge ${isIn ? "is-in" : "is-out"}`}>
                              {isIn ? "VÀO" : "RA"}
                            </span>
                            <span className={`cc-timeline-source ${p.is_manual ? "is-manual" : "is-gps"}`}>
                              {p.is_manual ? "Chấm bù" : "GPS"}
                            </span>
                          </div>
                          {p.is_manual && (
                            <div className="cc-timeline-details">
                              {p.fault_party && <span className="cc-fault-party">{FAULT_LABEL[p.fault_party] ?? p.fault_party}</span>}
                              {p.adjust_reason && <span className="cc-adjust-reason"> · {p.adjust_reason}</span>}
                            </div>
                          )}
                        </div>
                        {p.is_manual && canAdjust && (
                          <button className="cc-btn-timeline-delete" onClick={() => removePunch(p.id)} disabled={busy} title="Xóa lượt chấm này">
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                  {detail.punches.length === 0 && (
                    <p className="ns__empty" style={{ padding: "16px 0", textAlign: "center" }}>Ngày này chưa có lượt chấm nào.</p>
                  )}
                </div>
              </div>

              {/* Form Adjust */}
              {canAdjust && (
                <div className="cc-adjust-section">
                  <h4 className="cc-section-title-mini">Chấm bù / sửa</h4>
                  <div className="cc-adjust-grid">
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Loại chấm</span>
                      <div className="cc-select-wrapper">
                        <select value={checkType} onChange={(e) => setCheckType(e.target.value as "in" | "out")}>
                          <option value="in">VÀO</option>
                          <option value="out">RA</option>
                        </select>
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Giờ</span>
                      <div className="cc-input-time-wrapper">
                        <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
                        <Clock size={14} className="cc-time-icon-inside" />
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Nguyên nhân</span>
                      <div className="cc-select-wrapper">
                        <select value={fault} onChange={(e) => setFault(e.target.value)}>
                          {FAULT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      </div>
                    </div>
                  </div>
                  
                  <div className="cc-adjust-field" style={{ marginTop: 14 }}>
                    <span className="cc-field-label">Lý do (bắt buộc, ghi vào nhật ký)</span>
                    <input className="cc-input-text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="vd: NV quên chấm ra, đã xác minh…" />
                  </div>
                  
                  <div className="cc-adjust-action-row">
                    <button className="btn btn--primary cc-btn-add-punch" onClick={addPunch} disabled={busy}>
                      {busy ? <RefreshCw className="cc-animate-spin" size={14} /> : "Thêm punch chấm bù"}
                    </button>
                  </div>
                  
                  <div className="cc-info-card-note">
                    <AlertTriangle size={14} className="cc-note-icon" />
                    <span>Công được <b>tự động tính lại</b> từ các lượt chấm (punch) — không ghi đè trực tiếp con số. Mọi thao tác đều được lưu nhật ký kiểm toán.</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>Đóng</button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Yêu cầu chỉnh công (HCNS duyệt) -----------------------------------

function statusBadge(s: string) {
  const map: Record<string, [string, string]> = {
    pending: ["cc-badge-status--pending", "Chờ duyệt"],
    approved: ["cc-badge-status--approved", "Đã duyệt"],
    rejected: ["cc-badge-status--rejected", "Từ chối"],
    cancelled: ["cc-badge-status--cancelled", "Đã hủy"],
  };
  const [cls, label] = map[s] ?? ["cc-badge-status--cancelled", s];
  return <span className={`cc-badge-status ${cls}`}>{label}</span>;
}

function AdjustRequestsTab({ token, canAdjust }: { token: string; canAdjust: boolean }) {
  const [items, setItems] = useState<AdjustRequest[] | null>(null);
  const [status, setStatus] = useState("pending");
  const [faults, setFaults] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api.attendance.listAdjustRequests(token, status).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, status]);
  useEffect(() => { load(); }, [load]);

  async function approve(r: AdjustRequest) {
    setBusy(true); setErr(null);
    try {
      await api.attendance.approveAdjustRequest(token, r.id, { fault_party: faults[r.id] ?? r.fault_party ?? "nv_quen" });
      load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi duyệt."); }
    finally { setBusy(false); }
  }
  async function reject(r: AdjustRequest) {
    const note = window.prompt("Lý do từ chối yêu cầu:");
    if (!note) return;
    setBusy(true); setErr(null);
    try { await api.attendance.rejectAdjustRequest(token, r.id, note); load(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi từ chối."); }
    finally { setBusy(false); }
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
        <div className="cc-info-card-note" style={{ margin: 0, padding: "8px 12px" }}>
          <Info size={14} className="cc-note-icon" />
          <span>Duyệt yêu cầu sẽ tự động tạo lượt chấm công bù (punch) tương ứng và tính lại ngày công của ngày đó.</span>
        </div>
      </div>
      
      {err && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{err}</div>}
      
      {!items ? <p className="ns__empty">Đang tải…</p> : (
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
                      <span className="cc-name-avatar">{getInitials(r.employee_name)}</span>
                      <span className="cc-name-text-plain" title={r.employee_name ?? `NV#${r.employee_id}`}>
                        {r.employee_name ?? `NV#${r.employee_id}`}
                      </span>
                    </div>
                  </td>
                  <td>{r.work_date}</td>
                  <td style={{ textAlign: "center" }}>
                    <span className={`cc-cell-badge ${r.check_type === "in" ? "cc-cell-badge--work" : "cc-cell-badge--late"}`}>
                      {r.check_type === "in" ? "VÀO" : "RA"}
                    </span>
                  </td>
                  <td style={{ textAlign: "center", fontFamily: "var(--ff-mono)", fontWeight: "bold" }}>
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
                  <td style={{ textAlign: "center" }}>{statusBadge(r.status)}</td>
                  {canAdjust && (
                    <td style={{ textAlign: "center" }}>
                      {r.status === "pending" ? (
                        <div className="cc-adjust-actions-group">
                          <div className="cc-select-wrapper cc-select-fault-wrapper">
                            <select value={faults[r.id] ?? r.fault_party ?? "nv_quen"}
                              onChange={(e) => setFaults((f) => ({ ...f, [r.id]: e.target.value }))}>
                              {FAULT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                          </div>
                          <button className="btn btn--primary cc-btn-approve" onClick={() => approve(r)} disabled={busy}>Duyệt</button>
                          <button className="btn btn--ghost cc-btn-reject" onClick={() => reject(r)} disabled={busy}>Từ chối</button>
                        </div>
                      ) : "—"}
                    </td>
                  )}
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={canAdjust ? 7 : 6} className="ns__empty" style={{ padding: "24px", textAlign: "center" }}>
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
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}

function parseDateTimeVN(iso: string | null | undefined) {
  if (!iso) return { time: "—", date: "" };
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return { time: iso, date: "" };
  const timeStr = d.toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false });
  const dateStr = d.toLocaleDateString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
  return { time: timeStr, date: dateStr };
}

function AttendanceTable({ logs, showEmployee }: { logs: AttendanceLog[]; showEmployee: boolean }) {
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
              <tr key={l.id} className={`cc-log-row cc-log-row--${l.check_type}`}>
                {showEmployee && (
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <span className="cc-avatar-mini">{getInitials(l.employee_name)}</span>
                      <span style={{ fontWeight: "var(--fw-medium)", color: "var(--ink)" }}>{l.employee_name ?? `NV#${l.employee_id}`}</span>
                    </div>
                  </td>
                )}
                <td>
                  <span className={`cc-log-badge cc-log-badge--${l.check_type}`}>
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
                    <span style={{ fontWeight: "var(--fw-medium)", color: "var(--ink)" }}>{l.location_name ?? "📍 Vị trí ngoài danh mục"}</span>
                    <span className={`cc-log-distance ${isInside ? "is-inside" : "is-outside"}`}>
                      <MapPin size={11} style={{ marginRight: "3px", display: "inline-block", verticalAlign: "middle" }} />
                      {l.distance_m != null ? (
                        isInside ? `Trong phạm vi (${Math.round(l.distance_m)}m)` : `Ngoài phạm vi (${Math.round(l.distance_m)}m)`
                      ) : "Không có GPS"}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
          {logs.length === 0 && (
            <tr>
              <td colSpan={showEmployee ? 4 : 3} className="ns__empty">Chưa có bản ghi chấm công.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
