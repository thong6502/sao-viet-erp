// Màn Tăng ca (module `tang_ca`) — 2 tab:
//   • Phiếu của tôi — NV tự gửi phiếu, theo dõi trạng thái, tự hủy khi chưa được duyệt.
//   • Duyệt phiếu   — tổ trưởng/HCNS duyệt (chọn nhiều → duyệt cả mẻ). Scope `department` nên tổ
//                     trưởng CHỈ thấy người trong tổ mình.
// Nguyên tắc (chốt với chủ 23/07/2026): phiếu = GIẤY PHÉP + MỨC TRẦN. Lượt bấm RA mới quyết tiền,
// nên màn này KHÔNG nhập giờ làm thực — chỉ khai khoảng được phép tăng ca.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type EmployeeRow, type OvertimeRequest } from "../api/client";
import { useCan } from "../auth/permissions";
import { useAuth } from "../auth/useAuth";
import { fmtDateTime } from "../utils/format";
import "./nhan-su.css";
import "./tang-ca.css";

type Tab = "mine" | "approve";

const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  cancelled: "Đã hủy",
};

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

/** Phút-trên-trục-ngày-công → "HH:MM" (kèm "+1" nếu đã sang hôm sau). */
function minToHhmm(m: number): string {
  const day = Math.floor(m / 1440);
  const rem = ((m % 1440) + 1440) % 1440;
  const s = `${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
  return day > 0 ? `${s} (+${day})` : s;
}

/** Phút → "HH:MM" thuần (không kèm "+1") để đổ vào ô nhập; lấy phần trong ngày. */
function plainHhmm(m: number): string {
  const rem = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

function hhmmToMin(v: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(v.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return null;
  return h * 60 + mi;
}

function fmtYmd(v: string): string {
  const [y, m, d] = v.split("-");
  return y && m && d ? `${d}/${m}/${y}` : v;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`tc-badge tc-badge--${status}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

// --- Modal gửi / tạo hộ phiếu ------------------------------------------------

function OvertimeFormModal({
  token,
  forEmployee,
  editing,
  onClose,
  onSaved,
}: {
  token: string;
  /** true = tổ trưởng tạo HỘ (chọn nhân viên, duyệt luôn); false = NV tự gửi. */
  forEmployee: boolean;
  /** Có = SỬA phiếu chờ duyệt (đổ sẵn dữ liệu, lưu bằng PUT). Không = tạo mới. */
  editing?: OvertimeRequest;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [workDate, setWorkDate] = useState(editing?.work_date ?? "");
  const [from, setFrom] = useState(editing ? plainHhmm(editing.from_minute) : "22:00");
  const [to, setTo] = useState(editing ? plainHhmm(editing.to_minute) : "00:00");
  const [nextDay, setNextDay] = useState(editing ? editing.to_minute >= 1440 : true);
  const [reason, setReason] = useState(editing?.reason ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!forEmployee) return;
    api.employees
      .list(token, {})
      .then((r) => setEmps(r.items))
      .catch(() => setEmps([]));
  }, [forEmployee, token]);

  const fromMin = hhmmToMin(from);
  const toMin = hhmmToMin(to);
  const toAbs = toMin == null ? null : toMin + (nextDay ? 1440 : 0);
  const minutes = fromMin != null && toAbs != null ? toAbs - fromMin : null;

  async function save() {
    setErr(null);
    if (!workDate) return setErr("Cần chọn ngày công.");
    if (fromMin == null || toAbs == null) return setErr("Giờ phải dạng HH:MM.");
    if (minutes == null || minutes <= 0)
      return setErr(
        "Giờ kết thúc phải sau giờ bắt đầu (nếu qua nửa đêm nhớ tích “sang hôm sau”).",
      );
    if (forEmployee && employeeId == null) return setErr("Cần chọn nhân viên.");
    setBusy(true);
    try {
      const input = {
        work_date: workDate,
        from_minute: fromMin,
        to_minute: toAbs,
        reason: reason.trim() || null,
      };
      if (editing) {
        await api.overtime.updateMine(token, editing.id, input);
      } else if (forEmployee) {
        await api.overtime.createFor(token, {
          ...input,
          employee_id: employeeId as number,
        });
      } else {
        await api.overtime.createMine(token, input);
      }
      onSaved();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>
            {editing
              ? "Sửa phiếu tăng ca"
              : forEmployee
                ? "Tạo phiếu tăng ca cho thợ"
                : "Gửi phiếu tăng ca"}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="tc-note">
            <span>
              Khai <b>khoảng được phép tăng ca</b>. Tiền trả theo{" "}
              <b>giờ bấm ra thực tế</b>, không vượt quá phiếu — về sớm hơn thì
              trả theo thực tế.
            </span>
          </div>
          <div className="ns-grid">
            {forEmployee && (
              <label className="ns-field">
                <span className="ns-field__label">Nhân viên *</span>
                <select
                  value={employeeId ?? ""}
                  onChange={(e) =>
                    setEmployeeId(
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                >
                  <option value="">— chọn —</option>
                  {emps.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="ns-field">
              <span className="ns-field__label">Ngày công *</span>
              <input
                type="date"
                value={workDate}
                onChange={(e) => setWorkDate(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Từ giờ *</span>
              <input
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                placeholder="22:00"
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đến giờ *</span>
              <input
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="03:00"
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">
              <input
                type="checkbox"
                checked={nextDay}
                onChange={(e) => setNextDay(e.target.checked)}
              />{" "}
              Giờ kết thúc rơi sang <b>hôm sau</b>
            </span>
            {minutes != null && minutes > 0 && (
              <span className="tc-muted">
                Tổng: {Math.floor(minutes / 60)}h
                {minutes % 60 ? ` ${minutes % 60}'` : ""} — ngày công{" "}
                {workDate ? fmtYmd(workDate) : "…"}
              </span>
            )}
          </label>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="vd: chạy đơn gấp cho khách"
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

// --- Modal từ chối (bắt buộc ghi lý do) --------------------------------------

function RejectModal({
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
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Từ chối {count > 1 ? `${count} phiếu` : "phiếu tăng ca"}</h2>
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
              placeholder="vd: hôm nay không cần tăng ca"
            />
          </label>
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

// --- Bảng phiếu dùng chung ---------------------------------------------------

function RequestTable({
  rows,
  showEmployee,
  selectable,
  selected,
  onToggle,
  actions,
}: {
  rows: OvertimeRequest[];
  showEmployee: boolean;
  selectable: boolean;
  selected: Set<number>;
  onToggle: (id: number) => void;
  actions: (r: OvertimeRequest) => React.ReactNode;
}) {
  return (
    <div className="ns__tablewrap">
      <table className="ns__table tc-table">
        <thead>
          <tr>
            {selectable && <th style={{ width: 36 }}></th>}
            {showEmployee && <th>Nhân viên</th>}
            <th>Ngày công</th>
            <th>Khoảng tăng ca</th>
            <th>Số giờ</th>
            <th>Lý do</th>
            <th>Trạng thái</th>
            <th>Người duyệt</th>
            <th>Ghi chú duyệt</th>
            <th className="tc-col-act"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              {selectable && (
                <td>
                  {r.status === "pending" && (
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => onToggle(r.id)}
                    />
                  )}
                </td>
              )}
              {showEmployee && <td>{r.employee_name ?? "—"}</td>}
              <td>{fmtYmd(r.work_date)}</td>
              <td>
                {minToHhmm(r.from_minute)} → {minToHhmm(r.to_minute)}
              </td>
              <td>
                {Math.floor(r.minutes / 60)}h
                {r.minutes % 60 ? ` ${r.minutes % 60}'` : ""}
              </td>
              <td>{r.reason ?? "—"}</td>
              <td>
                <StatusBadge status={r.status} />
              </td>
              <td>
                {r.decided_by_name ? (
                  <>
                    {r.decided_by_name}
                    {r.decided_at && (
                      <div className="tc-muted">{fmtDateTime(r.decided_at)}</div>
                    )}
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>{r.decision_note || "—"}</td>
              <td className="tc-col-act">
                <div className="cc-rowact">{actions(r)}</div>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={10} className="ns__empty">
                Chưa có phiếu tăng ca nào.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// --- Màn chính ---------------------------------------------------------------

export function TangCaPage({
  onChanged,
  eventTick,
}: {
  onChanged?: () => void;
  /** Tăng theo mỗi sự kiện real-time (SSE) → tải lại bảng NGAY khi bên kia duyệt/từ chối/gửi phiếu. */
  eventTick?: number;
}) {
  const { token: authToken } = useAuth();
  const token = authToken ?? ""; // AppShell chỉ render màn này sau khi đăng nhập
  const can = useCan();
  const canApprove = can("tang_ca", "approve");
  const [tab, setTab] = useState<Tab>(canApprove ? "approve" : "mine");
  const [mine, setMine] = useState<OvertimeRequest[]>([]);
  const [hasEmployee, setHasEmployee] = useState(true);
  const [queue, setQueue] = useState<OvertimeRequest[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState<null | "mine" | "for">(null);
  const [editing, setEditing] = useState<OvertimeRequest | null>(null);
  const [rejecting, setRejecting] = useState<null | number[]>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api.overtime
      .mine(token)
      .then((r) => {
        setHasEmployee(r.has_employee);
        setMine(r.items ?? []);
      })
      .catch((e) => setErr(errText(e)));
    if (canApprove) {
      api.overtime
        .list(token)
        .then((r) => setQueue(r.items))
        .catch((e) => setErr(errText(e)));
    }
    api.overtime.markSeen(token).catch(() => undefined);
    onChanged?.(); // badge sidebar + chuông cập nhật ngay sau mỗi thao tác
  }, [token, canApprove, onChanged]);

  // `eventTick` đổi = có sự kiện real-time → tải lại bảng, khỏi bắt người dùng F5.
  useEffect(() => {
    load();
  }, [load, eventTick]);

  const pending = useMemo(
    () => queue.filter((r) => r.status === "pending"),
    [queue],
  );

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      setSelected(new Set());
      load();
    } catch (e) {
      setErr(errText(e));
    }
  }

  return (
    <div className="ns">
      <header className="ns__head">
        <h1 className="ns__title">Tăng ca</h1>
        <p className="ns__desc">
          Muốn tính tiền tăng ca thì phải có phiếu được duyệt. Không có phiếu
          vẫn <b>đủ công ca chính</b> — chỉ phần giờ vượt ca là không ra tiền.
        </p>
      </header>

      {err && <div className="banner banner--error">{err}</div>}

      <div className="tc-tabs">
        <button
          className={`btn ${tab === "mine" ? "btn--primary" : "btn--ghost"}`}
          onClick={() => setTab("mine")}
        >
          Phiếu của tôi
        </button>
        {canApprove && (
          <button
            className={`btn ${tab === "approve" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setTab("approve")}
          >
            Duyệt phiếu{pending.length ? ` (${pending.length})` : ""}
          </button>
        )}
      </div>

      {tab === "mine" && (
        <>
          <div className="cc-toolbar">
            <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
              Phiếu tăng ca của tôi
            </h4>
            {hasEmployee && (
              <button
                className="btn btn--primary"
                onClick={() => setCreating("mine")}
              >
                + Gửi phiếu
              </button>
            )}
          </div>
          {!hasEmployee ? (
            <div className="tc-note">
              <span>
                Tài khoản của bạn chưa gắn hồ sơ nhân viên nên chưa gửi phiếu
                được.
              </span>
            </div>
          ) : (
            <RequestTable
              rows={mine}
              showEmployee={false}
              selectable={false}
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
                      className="btn btn--ghost ns-danger"
                      onClick={() => run(() => api.overtime.cancel(token, r.id))}
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

      {tab === "approve" && canApprove && (
        <>
          <div className="cc-toolbar">
            <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
              Phiếu chờ duyệt trong phạm vi của bạn
            </h4>
            <button
              className="btn btn--primary"
              onClick={() => setCreating("for")}
            >
              + Tạo hộ thợ
            </button>
          </div>
          {selected.size > 0 && (
            <div className="tc-bulkbar">
              <span>Đã chọn {selected.size} phiếu</span>
              <button
                className="btn btn--primary"
                onClick={() =>
                  run(() => api.overtime.bulkApprove(token, [...selected]))
                }
              >
                Duyệt tất cả
              </button>
              <button
                className="btn btn--ghost ns-danger"
                onClick={() => setRejecting([...selected])}
              >
                Từ chối tất cả
              </button>
            </div>
          )}
          <RequestTable
            rows={queue}
            showEmployee
            selectable
            selected={selected}
            onToggle={toggle}
            actions={(r) =>
              r.status === "pending" ? (
                <>
                  <button
                    className="btn btn--ghost"
                    onClick={() => run(() => api.overtime.approve(token, r.id))}
                  >
                    Duyệt
                  </button>
                  <button
                    className="btn btn--ghost ns-danger"
                    onClick={() => setRejecting([r.id])}
                  >
                    Từ chối
                  </button>
                </>
              ) : null
            }
          />
        </>
      )}

      {creating && (
        <OvertimeFormModal
          token={token}
          forEmployee={creating === "for"}
          onClose={() => setCreating(null)}
          onSaved={() => {
            setCreating(null);
            load();
          }}
        />
      )}
      {editing && (
        <OvertimeFormModal
          token={token}
          forEmployee={false}
          editing={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {rejecting && (
        <RejectModal
          count={rejecting.length}
          onClose={() => setRejecting(null)}
          onConfirm={(note) => {
            const ids = rejecting;
            setRejecting(null);
            run(() =>
              ids.length > 1
                ? api.overtime.bulkReject(token, ids, note)
                : api.overtime.reject(token, ids[0], note),
            );
          }}
        />
      )}
    </div>
  );
}
