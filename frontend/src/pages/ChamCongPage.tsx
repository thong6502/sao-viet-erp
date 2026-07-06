// Chấm công GPS (module `nhan_su`). 3 tab:
//   • Chấm công của tôi — lấy GPS trình duyệt, chấm VÀO/RA nếu trong bán kính điểm gần nhất.
//   • Điểm chấm công (HR) — khai toạ độ + bán kính; "Lấy vị trí hiện tại" để điền nhanh.
//   • Bảng chấm công (HR) — toàn bộ log.
// Server là cổng geofence thật (Haversine); ngoài phạm vi bị chặn cứng.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AttendanceLog,
  type AttendanceStatus,
  type CheckResult,
  type Timesheet,
  type TimesheetRow,
  type WorkLocation,
  type WorkLocationInput,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import "./nhan-su.css";
import "./cham-cong.css";

type Tab = "me" | "locations" | "logs" | "timesheet";

function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString("vi-VN");
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

export function ChamCongPage() {
  const { token } = useAuth();
  const can = useCan();
  const canConfig = can("nhan_su", "update");
  const [tab, setTab] = useState<Tab>("me");

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
        {canConfig && <button className={tab === "locations" ? "is-active" : ""} onClick={() => setTab("locations")}>Điểm chấm công</button>}
        <button className={tab === "logs" ? "is-active" : ""} onClick={() => setTab("logs")}>Bảng chấm công</button>
        <button className={tab === "timesheet" ? "is-active" : ""} onClick={() => setTab("timesheet")}>Bảng công tháng</button>
      </nav>

      {tab === "me" && <MyCheckIn token={token!} />}
      {tab === "locations" && canConfig && <LocationsTab token={token!} />}
      {tab === "logs" && <LogsTab token={token!} />}
      {tab === "timesheet" && <TimesheetTab token={token!} />}
    </main>
  );
}

// --- Tab: Chấm công của tôi -------------------------------------------------

function MyCheckIn({ token }: { token: string }) {
  const [status, setStatus] = useState<AttendanceStatus | null>(null);
  const [logs, setLogs] = useState<AttendanceLog[]>([]);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [geoErr, setGeoErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api.attendance.myStatus(token).then(setStatus).catch(() => setStatus(null));
    api.attendance.myLogs(token).then((r) => setLogs(r.items)).catch(() => setLogs([]));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function doCheck() {
    setChecking(true);
    setResult(null);
    setGeoErr(null);
    try {
      const pos = await getPosition();
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
  return (
    <div className="cc-grid">
      <div className="cc-card">
        <div className="cc-card__who">{status.employee_name}</div>
        <div className="cc-card__hint">
          {status.last_check
            ? `Lần gần nhất: chấm ${status.last_check.check_type === "in" ? "VÀO" : "RA"} lúc ${fmtDateTime(status.last_check.checked_at)}`
            : "Chưa có lần chấm công nào."}
        </div>

        <button
          className={`cc-bigbtn ${isIn ? "cc-bigbtn--in" : "cc-bigbtn--out"}`}
          onClick={doCheck}
          disabled={checking || !status.locations_configured}
        >
          {checking ? "Đang lấy vị trí…" : isIn ? "📍 Chấm VÀO" : "📍 Chấm RA"}
        </button>

        {!status.locations_configured && (
          <p className="cc-note">Chưa có điểm chấm công nào được khai — liên hệ HCNS.</p>
        )}

        {geoErr && <div className="banner banner--error" style={{ marginTop: 12 }}>{geoErr}</div>}
        {result && (
          <div className={`banner ${result.success ? "banner--ok" : "banner--warn"}`} style={{ marginTop: 12 }}>
            {result.message}
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

function LogsTab({ token }: { token: string }) {
  const [items, setItems] = useState<AttendanceLog[] | null>(null);
  useEffect(() => {
    api.attendance.logs(token).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [token]);
  if (!items) return <p className="ns__empty">Đang tải…</p>;
  return <AttendanceTable logs={items} showEmployee />;
}

// --- Tab: Bảng công tháng (HR) ----------------------------------------------

function TimesheetTab({ token }: { token: string }) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [data, setData] = useState<Timesheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    setLoading(true);
    api.attendance.timesheet(token, year, month)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [token, year, month]);

  async function exportCsv() {
    setDownloading(true);
    try {
      const url = await api.attendance.timesheetCsvBlobUrl(token, year, month);
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
        <button className="btn btn--ghost" onClick={exportCsv} disabled={downloading || !data?.rows.length}>
          {downloading ? "Đang xuất…" : "⬇ Xuất CSV"}
        </button>
        <span className="cc-ts-legend"><span className="cc-day cc-day--on">8h</span> = số giờ · <span className="cc-day cc-day--on">•</span> = có mặt (thiếu giờ ra)</span>
      </div>
      {loading && <p className="ns__empty">Đang tải…</p>}
      {!loading && data && (
        <div className="ns__tablewrap cc-timesheet">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th><th>Họ tên</th>
                {days.map((d) => <th key={d} className="cc-day">{d}</th>)}
                <th className="cc-total">Công</th><th className="cc-total">Giờ</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => <TimesheetRowView key={r.employee_id} row={r} days={days} />)}
              {data.rows.length === 0 && (
                <tr><td colSpan={days.length + 4} className="ns__empty">Chưa có dữ liệu chấm công tháng này.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TimesheetRowView({ row, days }: { row: TimesheetRow; days: number[] }) {
  return (
    <tr>
      <td className="ns__code">{row.employee_code}</td>
      <td>{row.employee_name}</td>
      {days.map((d) => {
        const day = row.days[String(d)];
        return (
          <td key={d} className={`cc-day ${day ? "cc-day--on" : ""}`}
              title={day ? `${day.first_in ?? "?"}–${day.last_out ?? "?"}` : ""}>
            {day ? (day.hours != null ? `${day.hours}h` : "•") : ""}
          </td>
        );
      })}
      <td className="cc-total">{row.total_days}</td>
      <td className="cc-total">{row.total_hours}h</td>
    </tr>
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
