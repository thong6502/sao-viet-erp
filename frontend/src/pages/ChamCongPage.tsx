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
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0,
    });
  });
}

function geoErrText(e: unknown): string {
  const code = (e as { code?: number } | null)?.code;
  if (code === 1) return "Bạn đã từ chối quyền vị trí. Hãy cho phép định vị rồi thử lại.";
  if (code === 2) return "Không lấy được vị trí (GPS/định vị không khả dụng).";
  if (code === 3) return "Lấy vị trí quá lâu (timeout). Thử lại.";
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

      <nav className="ns-tabs cc-tabs">
        <button className={tab === "me" ? "is-active" : ""} onClick={() => setTab("me")}>Chấm công của tôi</button>
        <button className={tab === "my-timesheet" ? "is-active" : ""} onClick={() => setTab("my-timesheet")}>Công của tôi</button>
        {canConfig && <button className={tab === "locations" ? "is-active" : ""} onClick={() => setTab("locations")}>Điểm chấm công</button>}
        {canConfig && <button className={tab === "khai-ca" ? "is-active" : ""} onClick={() => setTab("khai-ca")}>Khai ca</button>}
        {canConfig && <button className={tab === "lich-le" ? "is-active" : ""} onClick={() => setTab("lich-le")}>Lịch & Ngày lễ</button>}
        {canView && <button className={tab === "logs" ? "is-active" : ""} onClick={() => setTab("logs")}>Bảng chấm công</button>}
        {canView && <button className={tab === "timesheet" ? "is-active" : ""} onClick={() => setTab("timesheet")}>Bảng công tháng</button>}
        {canView && <button className={tab === "yeu-cau" ? "is-active" : ""} onClick={() => setTab("yeu-cau")}>Yêu cầu chỉnh công</button>}
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
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  const load = useCallback(() => {
    api.attendance.myStatus(token).then(setStatus).catch(() => setStatus(null));
    api.attendance.myLogs(token).then((r) => setLogs(r.items)).catch(() => setLogs([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

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

  async function doCheck() {
    const isOut = status?.next_action === "out";
    // Chống bấm nhầm: xác nhận trước khi chấm RA (kết thúc ca).
    if (isOut && !window.confirm("Bạn sắp chấm RA (kết thúc ca) — đúng không?")) return;
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

  // Lối tắt cho HR/admin: tạo điểm chấm công ngay tại chỗ đang đứng rồi chấm luôn —
  // gỡ kẹt khi mọi điểm đã khai đều ở xa (vd điểm demo ở TP.HCM). Cần quyền cấu hình.
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
  const btnLabel = checking ? "Đang chấm…"
    : locating ? "Đang lấy vị trí…"
    : outside ? `Ngoài vùng — còn ${Math.round(preview!.meters_out ?? 0)} m`
    : isIn ? "📍 Chấm VÀO" : "📍 Chấm RA";
  return (
    <div className="cc-grid">
      <div className="cc-card">
        <div className="cc-card__who">{status.employee_name}</div>
        <div className="cc-card__hint">
          {status.last_check
            ? `Lần gần nhất: chấm ${status.last_check.check_type === "in" ? "VÀO" : "RA"} lúc ${fmtDateTime(status.last_check.checked_at)}`
            : "Chưa có lần chấm công nào."}
        </div>

        {showTimer && (
          <div className="cc-timer">⏱ Đang làm <b>{fmtElapsed(status.last_check?.checked_at, nowTick)}</b></div>
        )}

        <div className="cc-today">
          {status.shift ? (
            <span className="cc-today__shift">🕒 Ca {status.shift.name} · {status.shift.start_time}–{status.shift.end_time}{status.shift.is_overnight ? " (qua đêm)" : ""}</span>
          ) : (
            <span className="cc-today__shift cc-today__shift--none">Chưa gán ca làm việc</span>
          )}
          {status.today ? (
            <span className="cc-today__cong">
              Hôm nay {status.today.first_in ?? "—"}–{status.today.last_out ?? "…"}
              {status.today.cong != null ? <> · công dự kiến <b>{status.today.cong}</b></> : null}
              {status.today.ot_minutes ? <> · OT {status.today.ot_minutes}′</> : null}
            </span>
          ) : (
            <span className="cc-today__cong cc-today__cong--none">Hôm nay chưa có lượt chấm.</span>
          )}
          {status.today?.reason && <span className="cc-chip cc-chip--warn">⚠ {status.today.reason}</span>}
        </div>

        {status.locations_configured && (
          <div className={`cc-geo ${locating ? "cc-geo--wait" : preview?.within_range ? "cc-geo--in" : preview ? "cc-geo--out" : ""}`}>
            <span className="cc-geo__text">
              {locating ? "📡 Đang lấy vị trí…"
                : preview?.within_range ? `✓ Trong phạm vi “${preview.nearest_name}” · cách ${Math.round(preview.distance_m ?? 0)} m`
                : preview ? `⊘ Ngoài phạm vi “${preview.nearest_name}” · còn cách ${Math.round(preview.meters_out ?? 0)} m`
                : "Bấm 🔄 để kiểm tra phạm vi."}
            </span>
            <button className="cc-geo__refresh" onClick={refreshPreview} disabled={locating} title="Cập nhật vị trí">🔄</button>
          </div>
        )}

        <button
          className={`cc-bigbtn ${outside ? "cc-bigbtn--locked" : isIn ? "cc-bigbtn--in" : "cc-bigbtn--out"}`}
          onClick={doCheck}
          disabled={btnDisabled}
        >
          {btnLabel}
        </button>

        {!status.locations_configured && (
          <p className="cc-note">Chưa có điểm chấm công nào được khai — liên hệ HCNS.</p>
        )}

        {navigate && (
          <button className="btn btn--ghost cc-leavebtn" onClick={() => navigate("nghi-phep")}>
            🏖 Xin nghỉ phép
          </button>
        )}

        {geoErr && <div className="banner banner--error" style={{ marginTop: 12 }}>{geoErr}</div>}
        {result && (
          <div className={`banner ${result.success ? "banner--ok" : "banner--warn"}`} style={{ marginTop: 12 }}>
            {result.message}
          </div>
        )}

        {canConfig && (!status.locations_configured || (result != null && !result.within_range)) && (
          <div className="cc-setup">
            <button className="btn btn--ghost cc-setup__btn" onClick={setPointHere} disabled={checking}>
              📍 Đặt điểm chấm công tại vị trí này
            </button>
            <p className="cc-note">
              Tạo điểm mới ngay chỗ bạn đang đứng (bán kính 150 m) rồi chấm luôn.
              Chỉnh tên/tọa độ/bán kính ở tab <b>“Điểm chấm công”</b>.
            </p>
          </div>
        )}

        <p className="cc-note">Cần cho phép trình duyệt truy cập vị trí. Server kiểm khoảng cách tới điểm gần nhất.</p>
      </div>

      <div className="cc-logs">
        <h4 className="ns-section__title">Lịch sử của tôi</h4>
        <AttendanceTable logs={logs} showEmployee={false} />
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

  const days = data ? Array.from({ length: data.days_in_month }, (_, i) => i + 1) : [];
  const row = data?.rows[0] ?? null;
  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar">
        <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} />
        <span className="cc-ts-legend">
          Ô = <b>công theo ca</b> (0,94…) hoặc số giờ nếu chưa gán ca ·
          <span className="cc-day cc-day--on cc-late">muộn</span>
          <span className="cc-day cc-day--on cc-early">sớm</span>
          <span className="cc-day cc-day--on">•<sup className="cc-ot">+</sup></span>OT ·
          <span className="cc-day cc-day--on cc-leave">P</span>nghỉ · <b>bấm ô</b> để xin chỉnh công
        </span>
      </div>
      {loading && <p className="ns__empty">Đang tải…</p>}
      {!loading && !row && <p className="ns__empty">Tháng này bạn chưa có dữ liệu chấm công.</p>}
      {!loading && row && (
        <div className="ns__tablewrap cc-timesheet">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th><th>Họ tên</th><th>Ca</th>
                {days.map((d) => <th key={d} className="cc-day">{d}</th>)}
                <th className="cc-total">Công</th><th className="cc-total">Giờ</th>
              </tr>
            </thead>
            <tbody>
              <TimesheetRowView row={row} days={days} onCellClick={openReq} />
            </tbody>
          </table>
        </div>
      )}

      {reqs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4 className="ns-section__title">Yêu cầu chỉnh công của tôi</h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead><tr><th>Ngày</th><th>Chấm</th><th>Giờ</th><th>Lý do</th><th>Trạng thái</th><th></th></tr></thead>
              <tbody>
                {reqs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.work_date}</td>
                    <td>{r.check_type === "in" ? "VÀO" : "RA"}</td>
                    <td>{r.suggested_time ?? "—"}</td>
                    <td>{r.reason}{r.decision_note ? ` · (${r.decision_note})` : ""}</td>
                    <td>{statusBadge(r.status)}</td>
                    <td>{r.status === "pending" && (
                      <button className="btn btn--ghost" onClick={() => api.attendance.cancelAdjustRequest(token, r.id).then(loadReqs)}>Hủy</button>
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
    await api.attendance.deleteLocation(token, id);
    load();
  }

  return (
    <div>
      <div className="cc-toolbar">
        <button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm điểm</button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr><th>Tên điểm</th><th>Vĩ độ</th><th>Kinh độ</th><th>Bán kính</th><th>Trạng thái</th><th></th></tr>
          </thead>
          <tbody>
            {items?.map((l) => (
              <tr key={l.id}>
                <td>{l.name}</td>
                <td>{Number(l.latitude).toFixed(6)}</td>
                <td>{Number(l.longitude).toFixed(6)}</td>
                <td>{l.radius_m} m</td>
                <td>{l.is_active ? <span className="ns-badge ns-badge--ok">Đang dùng</span> : <span className="ns-badge ns-badge--muted">Tắt</span>}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(l)}>Sửa</button>
                  <button className="btn btn--ghost ns-danger" onClick={() => remove(l.id)}>Xóa</button>
                </td>
              </tr>
            ))}
            {items?.length === 0 && <tr><td colSpan={6} className="ns__empty">Chưa có điểm chấm công nào.</td></tr>}
          </tbody>
        </table>
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
  useEffect(() => setFocus(focusEmployeeId), [focusEmployeeId]);
  useEffect(() => {
    api.attendance.logs(token, focus).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token, focus]);
  const focusName = focus ? items?.find((l) => l.employee_id === focus)?.employee_name : undefined;
  return (
    <div>
      {focus != null && (
        <div className="cc-focus">
          <span>Đang xem chấm công của <b>{focusName ?? `NV #${focus}`}</b></span>
          <button type="button" className="btn btn--ghost" onClick={() => setFocus(undefined)}>✕ Bỏ lọc — xem cả xưởng</button>
        </div>
      )}
      {focus == null && <KpiStrip token={token} />}
      {!items ? <p className="ns__empty">Đang tải…</p> : <AttendanceTable logs={items} showEmployee={focus == null} />}
    </div>
  );
}

// Dải KPI giám sát hôm nay (theo scope): đang có mặt / quên chấm RA / đi muộn / YC chờ duyệt.
function KpiStrip({ token }: { token: string }) {
  const [kpi, setKpi] = useState<TodayKpi | null>(null);
  useEffect(() => {
    api.attendance.kpi(token).then(setKpi).catch(() => setKpi(null));
  }, [token]);
  if (!kpi) return null;
  const cards: { label: string; value: number; tone: string }[] = [
    { label: "Đang có mặt", value: kpi.present_now, tone: "in" },
    { label: "Quên chấm RA", value: kpi.missing_out, tone: "out" },
    { label: "Đi muộn hôm nay", value: kpi.late_today, tone: "late" },
    { label: "YC chờ duyệt", value: kpi.pending_requests, tone: "pending" },
  ];
  return (
    <div className="cc-kpi">
      {cards.map((c) => (
        <div key={c.label} className={`cc-kpi__card cc-kpi--${c.tone}`}>
          <div className="cc-kpi__value">{c.value}</div>
          <div className="cc-kpi__label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}

// --- Tab: Bảng công tháng (HR) ----------------------------------------------

// --- Tab: Khai ca (HR) ------------------------------------------------------

// --- Tab: Lịch làm việc & Ngày lễ (nền dùng chung cho Công / Phép / Lương) --

const WEEKDAY_FIELDS: { key: keyof WorkCalendarConfigInput; label: string }[] = [
  { key: "works_mon", label: "Thứ 2" }, { key: "works_tue", label: "Thứ 3" },
  { key: "works_wed", label: "Thứ 4" }, { key: "works_thu", label: "Thứ 5" },
  { key: "works_fri", label: "Thứ 6" }, { key: "works_sat", label: "Thứ 7" },
  { key: "works_sun", label: "Chủ Nhật" },
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

  const shortfall = special ? special.statutory_paid - special.paid_off_count : 0;

  return (
    <div className="cal">
      <section className="cal-panel">
        <h4 className="ns-section__title">Tuần làm việc chuẩn</h4>
        <p className="cc-note">Bật/tắt từng thứ. Ngày làm việc là mẫu tính công chuẩn tháng + trừ phép năm;
          ngày tắt = nghỉ tuần (không trừ phép). Ngày lễ khai riêng ở dưới.</p>
        <div className="cal-week">
          {WEEKDAY_FIELDS.map((w) => (
            <label key={String(w.key)} className={`cal-week__day ${config?.[w.key] ? "is-on" : ""}`}>
              <input type="checkbox" checked={!!config?.[w.key]} onChange={() => toggleDay(w.key)} />
              <span>{w.label}</span>
            </label>
          ))}
        </div>
        <div className="cc-toolbar">
          <button className="btn btn--primary" onClick={saveConfig} disabled={cfgBusy || !config}>
            {cfgBusy ? "Đang lưu…" : "Lưu tuần làm việc"}
          </button>
          {cfgMsg && <span className="cc-assign__msg">{cfgMsg}</span>}
        </div>
      </section>

      <section className="cal-panel">
        <div className="cal-panel__head">
          <h4 className="ns-section__title">Ngày lễ & làm bù</h4>
          <div className="cal-yearpick">
            <button className="btn btn--ghost" onClick={() => setYear((y) => y - 1)} aria-label="Năm trước">‹</button>
            <span className="cal-year">{year}</span>
            <button className="btn btn--ghost" onClick={() => setYear((y) => y + 1)} aria-label="Năm sau">›</button>
          </div>
        </div>
        {special && shortfall > 0 && (
          <div className="banner banner--warn">
            Năm {year} mới khai {special.paid_off_count}/{special.statutory_paid} ngày nghỉ lễ hưởng lương.
            Bổ sung Tết Nguyên đán, Giỗ Tổ Hùng Vương và ngày kề Quốc khánh theo thông báo Chính phủ.
          </div>
        )}
        <div className="cc-toolbar">
          <button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm ngày</button>
        </div>
        <div className="ns__tablewrap">
          <table className="ns__table">
            <thead>
              <tr><th>Ngày</th><th>Tên</th><th>Loại</th><th>Hưởng lương</th><th></th></tr>
            </thead>
            <tbody>
              {special?.items.map((s) => (
                <tr key={s.id}>
                  <td className="ns__code">{fmtDateVN(s.day)}</td>
                  <td>{s.name}</td>
                  <td>
                    <span className={`ns-badge ${s.kind === "work" ? "ns-badge--info" : "ns-badge--ok"}`}>
                      {KIND_LABEL[s.kind]}
                    </span>
                  </td>
                  <td>{s.kind === "off" ? (s.is_paid ? "Có" : "Không") : "—"}</td>
                  <td className="cc-rowact">
                    <button className="btn btn--ghost" onClick={() => setEditing(s)}>Sửa</button>
                    <button className="btn btn--ghost ns-danger" onClick={() => removeSpecial(s.id)}>Xóa</button>
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

      <section className="cal-panel">
        <div className="cal-panel__head">
          <h4 className="ns-section__title">Xem trước tháng</h4>
          <select className="cal-monthpick" value={previewMonth} onChange={(e) => setPreviewMonth(Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>Tháng {m}</option>)}
          </select>
        </div>
        {!preview && <p className="cal-standard">Đang tải lịch tháng…</p>}
        {preview && (
          <>
            <p className="cal-standard">
              Công chuẩn tháng {preview.month}/{preview.year}: <strong>{preview.working_days}</strong> công
              {preview.holidays.length > 0 && <> · {preview.holidays.length} ngày lễ</>}
            </p>
            <div className="cal-grid">
              {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((d) => (
                <div key={d} className="cal-grid__head">{d}</div>
              ))}
              {buildMonthGrid(preview).map((cell, i) =>
                cell ? (
                  <div key={i} className={`cal-cell cal-cell--${cell.kind}`} title={cell.name ?? ""}>
                    <span className="cal-cell__num">{cell.day}</span>
                    {cell.name && <span className="cal-cell__name">{cell.name}</span>}
                  </div>
                ) : <div key={i} className="cal-cell cal-cell--empty" />
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
    await api.attendance.deleteShift(token, id);
    load();
  }
  return (
    <div>
      <div className="cc-toolbar">
        <button className="btn btn--primary" onClick={() => setEditing("new")}>+ Thêm ca</button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr><th>Tên ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Dung sai</th><th>Loại</th><th>Trạng thái</th><th></th></tr>
          </thead>
          <tbody>
            {items?.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td><td>{s.start_time}</td><td>{s.end_time}</td>
                <td>{s.grace_minutes}′</td>
                <td>{[s.is_overnight ? "Qua đêm" : "", s.night_shift ? "🌙 đêm" : ""].filter(Boolean).join(" · ") || "Thường"}</td>
                <td>{s.is_active
                  ? <span className="ns-badge ns-badge--ok">Đang dùng</span>
                  : <span className="ns-badge ns-badge--muted">Tắt</span>}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(s)}>Sửa</button>
                  <button className="btn btn--ghost ns-danger" onClick={() => remove(s.id)}>Xóa</button>
                </td>
              </tr>
            ))}
            {items?.length === 0 && <tr><td colSpan={7} className="ns__empty">Chưa khai ca nào.</td></tr>}
          </tbody>
        </table>
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
  const [periodMsg, setPeriodMsg] = useState<string | null>(null);
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
      setPeriodMsg("Đã chốt công tháng.");
    } catch (e) {
      setPeriodMsg(e instanceof Error ? e.message : "Lỗi khi chốt công.");
    } finally { setPeriodBusy(false); }
  }
  async function doReopenPeriod() {
    setPeriodBusy(true); setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.reopenPeriod(token, year, month));
      setPeriodMsg("Đã mở lại kỳ công.");
    } catch (e) {
      setPeriodMsg(e instanceof Error ? e.message : "Lỗi khi mở kỳ công.");
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
  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar">
        <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} />
        <select value={deptId} onChange={(e) => setDeptId(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">Tất cả phòng/tổ</option>
          {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="btn btn--ghost" onClick={exportCsv} disabled={downloading || !data?.rows.length}>
          {downloading ? "Đang xuất…" : "⬇ Xuất CSV"}
        </button>
        <span className="cc-ts-legend">
          Ô = <b>công theo ca</b> (0,94…) hoặc số giờ nếu chưa gán ca ·
          <span className="cc-day cc-day--on cc-late">muộn</span>
          <span className="cc-day cc-day--on cc-early">sớm</span>
          <span className="cc-day cc-day--on">•<sup className="cc-ot">+</sup></span>OT
          {canAdjust && <> · <b>bấm vào ô</b> để xem/chấm bù</>}
        </span>
      </div>
      {period && (
        <div className={`cc-period ${period.status === "locked" ? "cc-period--locked" : ""}`}>
          <div className="cc-period__info">
            {period.status === "locked"
              ? <span className="ns-badge ns-badge--ok">Đã chốt công</span>
              : <span className="ns-badge ns-badge--muted">Chưa chốt (nháp)</span>}
            {period.status !== "locked" && (period.hanging_days > 0 || period.pending_leaves + period.pending_adjusts > 0) && (
              <span className="cc-period__warn">
                {period.hanging_days > 0 && ` · ${period.hanging_days} ngày treo (thiếu chấm RA)`}
                {period.pending_leaves + period.pending_adjusts > 0 && ` · ${period.pending_leaves + period.pending_adjusts} đơn chưa duyệt`}
              </span>
            )}
            {period.status === "locked" && <span className="cc-period__warn"> · đóng băng {period.line_count} NV</span>}
          </div>
          {canAdjust && (
            <div className="cc-period__act">
              {period.status === "draft"
                ? <button className="btn btn--primary" onClick={doLockPeriod} disabled={periodBusy}>
                    {periodBusy ? "Đang chốt…" : "Chốt công tháng"}
                  </button>
                : <button className="btn btn--ghost" onClick={doReopenPeriod}
                    disabled={periodBusy || period.payroll_locked}
                    title={period.payroll_locked ? "Kỳ lương đã chốt — không mở lại kỳ công" : ""}>
                    {periodBusy ? "Đang mở…" : "Mở lại kỳ công"}
                  </button>}
              {periodMsg && <span className="cc-period__msg">{periodMsg}</span>}
            </div>
          )}
        </div>
      )}
      {loading && <p className="ns__empty">Đang tải…</p>}
      {!loading && data && (
        <div className="ns__tablewrap cc-timesheet">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th><th>Họ tên</th><th>Ca</th>
                {days.map((d) => <th key={d} className="cc-day">{d}</th>)}
                <th className="cc-total">Công</th><th className="cc-total">Giờ</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <TimesheetRowView key={r.employee_id} row={r} days={days}
                  onCellClick={(dayNum) => openCell(r.employee_id, r.employee_name, dayNum)} />
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
    </div>
  );
}

function TimesheetRowView({ row, days, onCellClick }: {
  row: TimesheetRow; days: number[]; onCellClick?: (dayNum: number) => void;
}) {
  const clickable = !!onCellClick;
  const cellProps = (d: number) => clickable
    ? { role: "button" as const, tabIndex: 0, onClick: () => onCellClick!(d), style: { cursor: "pointer" } }
    : {};
  return (
    <tr>
      <td className="ns__code">{row.employee_code}</td>
      <td>{row.employee_name}</td>
      <td>{row.shift_name ?? "—"}</td>
      {days.map((d) => {
        const day = row.days[String(d)];
        if (!day) return <td key={d} className="cc-day" {...cellProps(d)} />;
        if (day.leave) {
          return (
            <td key={d} className="cc-day cc-day--on cc-leave" title={`Nghỉ: ${day.leave}`} {...cellProps(d)}>
              {day.leave_paid ? "P" : "KL"}
            </td>
          );
        }
        const cls = ["cc-day", "cc-day--on", day.late ? "cc-late" : "", day.early ? "cc-early" : ""]
          .filter(Boolean).join(" ");
        const label = day.cong != null ? String(day.cong) : (day.hours != null ? `${day.hours}h` : "•");
        const tip = `${day.first_in ?? "?"}–${day.last_out ?? "?"}`
          + (day.late ? " · đi muộn" : "") + (day.early ? " · về sớm" : "")
          + (day.ot_minutes ? ` · OT ${day.ot_minutes}′` : "") + (day.night ? " · ca đêm" : "");
        return (
          <td key={d} className={cls} title={tip} {...cellProps(d)}>
            {label}{day.ot_minutes ? <sup className="cc-ot">+</sup> : null}
          </td>
        );
      })}
      <td className="cc-total">{row.total_cong != null ? row.total_cong : row.total_days}</td>
      <td className="cc-total">{row.total_hours}h</td>
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
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Chi tiết chấm công · {employeeName} · {date}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          {!detail ? <p className="ns__empty">Đang tải…</p> : (
            <>
              <p className="cc-note" style={{ marginTop: 0 }}>
                Ca: <b>{detail.shift_name ?? "chưa gán"}</b> · Công:{" "}
                <b>{detail.cong != null ? detail.cong : "—"}</b>
                {detail.reason && <span className="cc-chip cc-chip--warn" style={{ marginLeft: 8 }}>⚠ {detail.reason}</span>}
              </p>
              <div className="ns__tablewrap">
                <table className="ns__table">
                  <thead><tr><th>Giờ</th><th>Chấm</th><th>Nguồn</th><th>Lý do / nguyên nhân</th><th></th></tr></thead>
                  <tbody>
                    {detail.punches.map((p) => (
                      <tr key={p.id}>
                        <td>{p.time}</td>
                        <td>
                          <span className={`ns-badge ${p.check_type === "in" ? "ns-badge--ok" : "ns-badge--info"}`}>
                            {p.check_type === "in" ? "VÀO" : "RA"}
                          </span>
                        </td>
                        <td>{p.is_manual ? <span className="ns-badge ns-badge--muted">Chấm bù</span> : "GPS"}</td>
                        <td>{p.is_manual ? `${p.fault_party ? `[${FAULT_LABEL[p.fault_party] ?? p.fault_party}] ` : ""}${p.adjust_reason ?? ""}` : "—"}</td>
                        <td>{p.is_manual && canAdjust && (
                          <button className="btn btn--ghost ns-danger" onClick={() => removePunch(p.id)} disabled={busy}>Xóa</button>
                        )}</td>
                      </tr>
                    ))}
                    {detail.punches.length === 0 && <tr><td colSpan={5} className="ns__empty">Ngày này chưa có lượt chấm nào.</td></tr>}
                  </tbody>
                </table>
              </div>

              {canAdjust && (
                <div className="cc-adjust">
                  <h4 className="ns-section__title">Chấm bù / sửa</h4>
                  <div className="ns-grid">
                    <label className="ns-field"><span className="ns-field__label">Loại chấm</span>
                      <select value={checkType} onChange={(e) => setCheckType(e.target.value as "in" | "out")}>
                        <option value="in">VÀO</option><option value="out">RA</option>
                      </select></label>
                    <label className="ns-field"><span className="ns-field__label">Giờ</span>
                      <input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
                    <label className="ns-field"><span className="ns-field__label">Nguyên nhân</span>
                      <select value={fault} onChange={(e) => setFault(e.target.value)}>
                        {FAULT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select></label>
                  </div>
                  <label className="ns-field" style={{ marginTop: 12 }}><span className="ns-field__label">Lý do (bắt buộc, ghi vào nhật ký)</span>
                    <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="vd: NV quên chấm ra, đã xác minh…" /></label>
                  <button className="btn btn--primary" style={{ marginTop: 12 }} onClick={addPunch} disabled={busy}>
                    {busy ? "Đang lưu…" : "➕ Thêm punch chấm bù"}
                  </button>
                  <p className="cc-note">Công được TÍNH LẠI từ các punch — không ghi đè con số. Mọi thao tác ghi nhật ký.</p>
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
    pending: ["ns-badge--info", "Chờ duyệt"],
    approved: ["ns-badge--ok", "Đã duyệt"],
    rejected: ["ns-badge--muted", "Từ chối"],
    cancelled: ["ns-badge--muted", "Đã hủy"],
  };
  const [cls, label] = map[s] ?? ["ns-badge--muted", s];
  return <span className={`ns-badge ${cls}`}>{label}</span>;
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
      <div className="cc-toolbar cc-ts-toolbar">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">Chờ duyệt</option>
          <option value="approved">Đã duyệt</option>
          <option value="rejected">Từ chối</option>
          <option value="all">Tất cả</option>
        </select>
        <span className="cc-note">Duyệt = sinh punch chấm bù, công tự tính lại (có nhật ký).</span>
      </div>
      {err && <div className="banner banner--error">{err}</div>}
      {!items ? <p className="ns__empty">Đang tải…</p> : (
        <div className="ns__tablewrap">
          <table className="ns__table">
            <thead>
              <tr><th>Nhân viên</th><th>Ngày</th><th>Chấm</th><th>Giờ</th><th>Lý do</th><th>Trạng thái</th>
                {canAdjust && <th>Xử lý</th>}</tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td>{r.employee_name ?? `NV#${r.employee_id}`}</td>
                  <td>{r.work_date}</td>
                  <td><span className={`ns-badge ${r.check_type === "in" ? "ns-badge--ok" : "ns-badge--info"}`}>{r.check_type === "in" ? "VÀO" : "RA"}</span></td>
                  <td>{r.suggested_time ?? "—"}</td>
                  <td>{r.reason}{r.decision_note ? ` · (${r.decision_note})` : ""}</td>
                  <td>{statusBadge(r.status)}</td>
                  {canAdjust && (
                    <td className="cc-rowact">
                      {r.status === "pending" ? (
                        <>
                          <select value={faults[r.id] ?? r.fault_party ?? "nv_quen"}
                            onChange={(e) => setFaults((f) => ({ ...f, [r.id]: e.target.value }))}>
                            {FAULT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                          </select>
                          <button className="btn btn--primary" onClick={() => approve(r)} disabled={busy}>Duyệt</button>
                          <button className="btn btn--ghost ns-danger" onClick={() => reject(r)} disabled={busy}>Từ chối</button>
                        </>
                      ) : "—"}
                    </td>
                  )}
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={canAdjust ? 7 : 6} className="ns__empty">Không có yêu cầu nào.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- Shared table -----------------------------------------------------------

function AttendanceTable({ logs, showEmployee }: { logs: AttendanceLog[]; showEmployee: boolean }) {
  return (
    <div className="ns__tablewrap">
      <table className="ns__table">
        <thead>
          <tr>
            {showEmployee && <th>Nhân viên</th>}
            <th>Chấm</th><th>Thời gian</th><th>Điểm</th><th>Khoảng cách</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id}>
              {showEmployee && <td>{l.employee_name ?? `NV#${l.employee_id}`}</td>}
              <td>
                <span className={`ns-badge ${l.check_type === "in" ? "ns-badge--ok" : "ns-badge--info"}`}>
                  {l.check_type === "in" ? "VÀO" : "RA"}
                </span>
              </td>
              <td>{fmtDateTime(l.checked_at)}</td>
              <td>{l.location_name ?? "—"}</td>
              <td>{l.distance_m != null ? `${Math.round(l.distance_m)} m` : "—"}</td>
            </tr>
          ))}
          {logs.length === 0 && (
            <tr><td colSpan={showEmployee ? 5 : 4} className="ns__empty">Chưa có bản ghi chấm công.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
