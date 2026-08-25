// Tab Yêu cầu chỉnh công (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type AdjustRequest } from "../../../../api/client";
import { Info } from "lucide-react";
import { statusBadge } from "../components/badges";
import { FAULT_OPTIONS } from "../shared/constants";
import { getInitials } from "../shared/helpers";

// --- Tab: Yêu cầu chỉnh công (HCNS duyệt) -----------------------------------

export function AdjustRequestsTab({
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
