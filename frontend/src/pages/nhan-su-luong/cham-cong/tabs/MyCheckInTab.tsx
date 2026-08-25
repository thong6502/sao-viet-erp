// Tab Chấm công của tôi (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type AttendanceLog,
  type AttendancePreview,
  type AttendanceStatus,
  type CheckResult,
} from "../../../../api/client";
import {
  UserCheck,
  MapPin,
  Clock,
  Clock3,
  ClipboardList,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Coffee,
  Lock,
  Info,
  LogIn,
  LogOut,
} from "lucide-react";
import type { NavigateFn } from "../../../../components/AppShell";
import { GpsRadarMap2D } from "../components/GpsRadarMap2D";
import { MyHistoryModal } from "../modals/MyHistoryModal";
import {
  fmtDateTime,
  fmtElapsed,
  getPosition,
  geoErrText,
} from "../shared/helpers";

// --- Tab: Chấm công của tôi -------------------------------------------------

export function MyCheckIn({
  token,
  canConfig,
  coQuyenGhi,
  navigate,
}: {
  token: string;
  canConfig: boolean;
  /** Ô THAO TÁC của Tự phục vụ — bấm chấm công là GHI dữ liệu (tách 11/08/2026). */
  coQuyenGhi: boolean;
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
    // Chưa được cấp ô Thao tác thì nút khoá luôn — máy chủ cũng chặn, đừng để bấm rồi ăn 403.
    !coQuyenGhi ||
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
      {/* 1. Executive Hero Header Banner */}
      <div className="cc-checkin-hero-header">
        <div className="cc-checkin-user-profile">
          {status.employee_name && (
            <div className={`cc-employee-avatar ${status.next_action === "out" ? "is-working" : "is-off"}`}>
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
                <span className={`cc-status-indicator-dot ${status.next_action === "out" ? "is-working" : "is-off"}`} />
                {status.next_action === "out" ? "Đang trong ca" : "Chưa vào ca"}
              </span>
            </div>
            <div className="cc-employee-sub-chip">
              <Clock size={12} style={{ flexShrink: 0 }} />
              <span>
                {status.last_check
                  ? `Lần gần nhất: Chấm ${status.last_check.check_type === "in" ? "VÀO" : "RA"} lúc ${fmtDateTime(status.last_check.checked_at)}`
                  : "Chưa có lượt chấm công nào hôm nay."}
              </span>
            </div>
          </div>
        </div>

        {/* Live OLED Digital Clock & Shift Status Widget */}
        <div className="cc-checkin-clock-banner">
          <div className="cc-live-clock cc-live-clock-compact">
            <span>{clockH}</span>
            <span className="cc-clock-colon">:</span>
            <span>{clockM}</span>
            <span className="cc-clock-colon">:</span>
            <span className="cc-clock-sec">{clockS}</span>
          </div>

          {status.shift && (
            <div className="cc-shift-tracker-compact">
              <div className="cc-shift-title">
                <Clock3 size={13} style={{ color: "var(--rust)" }} />
                <span>Ca {status.shift.name} ({status.shift.start_time} - {status.shift.end_time})</span>
              </div>
              {showTimer && (
                <div className="cc-shift-elapsed-time">
                  <span>Thời gian làm:</span>
                  <b style={{ fontFamily: "var(--ff-num)" }}>{fmtElapsed(status.last_check?.checked_at, nowTick)}</b>
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
                {preview?.within_range ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <CheckCircle2 size={13} /> Trong vùng
                  </span>
                ) : (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <XCircle size={13} /> Ngoài vùng
                  </span>
                )}
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
                <AlertTriangle size={14} style={{ color: "var(--signal)", flexShrink: 0 }} />
                <span>
                  Hãy di chuyển lại gần xưởng thêm <b>{preview.meters_out > 1000 ? `${(preview.meters_out / 1000).toFixed(1)}km` : `${Math.round(preview.meters_out)}m`}</b> để mở khóa nút chấm công.
                </span>
              </div>
            )}

            {/* Tóm tắt Công & Giờ làm Hôm nay */}
            <div className="cc-today-summary-card">
              <div className="cc-today-summary-header">
                <span className="cc-today-summary-title">Tóm tắt công hôm nay</span>
                {status.shift && (
                  <span className="cc-today-shift-tag">
                    Ca {status.shift.name} ({status.shift.start_time} - {status.shift.end_time})
                  </span>
                )}
              </div>
              <div className="cc-today-metrics-grid">
                <div className="cc-today-metric-item">
                  <span className="cc-today-metric-label">VÀO ĐẦU</span>
                  <span className="cc-today-metric-val">
                    {status.today?.first_in ? (
                      <span style={{ color: "var(--moss)", display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <LogIn size={13} /> {status.today.first_in}
                      </span>
                    ) : (
                      <span style={{ color: "var(--ash-2)" }}>—</span>
                    )}
                  </span>
                </div>
                <div className="cc-today-metric-item">
                  <span className="cc-today-metric-label">RA CUỐI</span>
                  <span className="cc-today-metric-val">
                    {status.today?.last_out ? (
                      <span style={{ color: "var(--rust)", display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <LogOut size={13} /> {status.today.last_out}
                      </span>
                    ) : (
                      <span style={{ color: "var(--ash-2)" }}>—</span>
                    )}
                  </span>
                </div>
                <div className="cc-today-metric-item">
                  <span className="cc-today-metric-label">CÔNG DỰ KIẾN</span>
                  <span className="cc-today-metric-val" style={{ color: "var(--ink)" }}>
                    {status.today?.cong != null ? `${status.today.cong} công` : "—"}
                  </span>
                </div>
              </div>
              {status.today?.reason && (
                <div className="cc-today-reason-note">
                  <Info size={13} style={{ flexShrink: 0, color: "var(--ash)" }} />
                  <span>{status.today.reason}</span>
                </div>
              )}
            </div>

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
                  style={{ marginLeft: 8, display: "inline-flex", alignItems: "center", gap: 4 }}
                  onClick={refreshPreview}
                  disabled={locating}
                >
                  <RefreshCw size={12} className={locating ? "cc-animate-spin" : ""} /> Thử lại
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
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <MapPin size={14} /> Đặt điểm chấm công tại đây
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
