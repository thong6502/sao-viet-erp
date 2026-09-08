// Modal "Xác nhận tăng ca theo phiếu" (07/09/2026 — Đợt 1, mục 1.5).
//
// Chủ giữ luật 4 lượt bấm; thợ hay quên cặp bấm tăng ca ⇒ tiền TC = 0 lặng lẽ lúc chốt. Đây là
// đường bù HÀNG LOẠT cho tổ trưởng/HCNS: chọn ngày → máy liệt kê phiếu TC đã duyệt của ngày đó
// (trong phạm vi Chấm bù của người dùng) + tình trạng cặp bấm → tích người thiếu cặp → một nút
// sinh cặp bấm tay có audit. Ai không thiếu (đã có / không đi làm / treo) máy tự bỏ qua, nói rõ vì sao.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type OtConfirmCandidate,
  type OtConfirmResult,
} from "../../../../api/client";
import { AlertTriangle, RefreshCw } from "lucide-react";

const TINH_TRANG: Record<string, { text: string; cls: string }> = {
  thieu_cap: { text: "Thiếu cặp bấm TC", cls: "cc-otc-status--ok" },
  da_co: { text: "Đã có cặp bấm", cls: "" },
  treo: { text: "Thiếu RA ca chính (treo)", cls: "" },
  khong_cham: { text: "Không bấm lượt nào", cls: "" },
  chua_gan_ca: { text: "Chưa gán ca", cls: "" },
};
const KIEU: Record<string, string> = {
  bu_cap: "thêm VÀO + RA tăng ca theo phiếu",
  tach_phien: "tách phiên: RA ca chính lúc hết ca + VÀO tăng ca; lượt RA thật thành RA tăng ca",
};

export function OtConfirmModal({
  token,
  defaultDate,
  depts,
  onClose,
  onDone,
}: {
  token: string;
  defaultDate: string;
  depts: { id: number; name: string }[];
  onClose: () => void;
  /** Gọi sau khi máy đã sinh cặp bấm — cha tải lại bảng công + kỳ công. */
  onDone: () => void;
}) {
  const [date, setDate] = useState(defaultDate);
  const [deptId, setDeptId] = useState<number | "">("");
  const [items, setItems] = useState<OtConfirmCandidate[] | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OtConfirmResult | null>(null);

  const load = useCallback(() => {
    setItems(null);
    setError(null);
    api.attendance
      .otConfirmCandidates(token, date, deptId === "" ? null : deptId)
      .then((r) => {
        setItems(r.items);
        // Mặc định tích sẵn người THIẾU cặp — đúng việc cần làm; người khác không tích được.
        setChecked(
          new Set(
            r.items
              .filter((x) => x.tinh_trang === "thieu_cap")
              .map((x) => x.employee_id),
          ),
        );
      })
      .catch((e) => {
        setItems([]);
        setError(
          e instanceof Error ? e.message : "Không tải được danh sách phiếu.",
        );
      });
  }, [token, date, deptId]);
  useEffect(() => {
    setResult(null);
    load();
  }, [load]);

  function toggle(id: number, on: boolean) {
    setChecked((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  }

  async function confirm() {
    if (checked.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.attendance.otConfirm(token, {
        date,
        employee_ids: [...checked],
        reason: reason.trim() || null,
      });
      setResult(res);
      onDone();
      // Tải lại để bảng phản ánh tình trạng mới (đã có cặp bấm).
      const r = await api.attendance.otConfirmCandidates(
        token,
        date,
        deptId === "" ? null : deptId,
      );
      setItems(r.items);
      setChecked(new Set());
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Lỗi khi xác nhận tăng ca theo phiếu.",
      );
    } finally {
      setBusy(false);
    }
  }

  const soThieu = (items ?? []).filter((x) => x.tinh_trang === "thieu_cap").length;

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box" style={{ maxWidth: 860 }}>
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Xác nhận tăng ca theo phiếu</h2>
            <p className="cc-modal-subtitle">
              Sinh cặp bấm tăng ca cho những người có phiếu đã duyệt nhưng quên
              bấm — cả tổ một lần.
            </p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <div className="cc-otc-toolbar">
            <label className="ns-field">
              <span className="ns-field__label">Ngày công</span>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Phòng ban / tổ</span>
              <select
                value={deptId}
                onChange={(e) =>
                  setDeptId(e.target.value === "" ? "" : Number(e.target.value))
                }
              >
                <option value="">Tất cả trong phạm vi</option>
                {depts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="ns-field" style={{ flex: 1, minWidth: 220 }}>
              <span className="ns-field__label">Ghi chú (ghi vào nhật ký)</span>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="vd: cả tổ làm tới 20h30 theo lệnh SX"
              />
            </label>
          </div>

          {items === null ? (
            <p className="ns__empty">Đang tải…</p>
          ) : items.length === 0 ? (
            <p className="ns__empty">
              Ngày này không có phiếu tăng ca đã duyệt nào trong phạm vi của bạn.
            </p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="cc-otc-table">
                <thead>
                  <tr>
                    <th style={{ width: 28 }} />
                    <th>Nhân viên</th>
                    <th>Phiếu tăng ca</th>
                    <th>Lượt bấm hôm đó</th>
                    <th>Tình trạng</th>
                    <th>Máy sẽ làm</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((x) => {
                    const tt = TINH_TRANG[x.tinh_trang] ?? {
                      text: x.tinh_trang,
                      cls: "",
                    };
                    const ok = x.tinh_trang === "thieu_cap";
                    return (
                      <tr key={x.ticket_id}>
                        <td>
                          <input
                            type="checkbox"
                            disabled={!ok}
                            checked={ok && checked.has(x.employee_id)}
                            onChange={(e) => toggle(x.employee_id, e.target.checked)}
                            aria-label={`Chọn ${x.employee_name}`}
                          />
                        </td>
                        <td>
                          <b>{x.employee_name}</b>
                          {x.employee_code ? (
                            <span style={{ color: "var(--ash)" }}> · {x.employee_code}</span>
                          ) : null}
                        </td>
                        <td className="cc-otc-punches">
                          {x.from_time}
                          {x.from_next_day ? " (+1)" : ""}–{x.to_time}
                          {x.to_next_day ? " (+1)" : ""}
                        </td>
                        <td className="cc-otc-punches">
                          {x.punches.length === 0
                            ? "—"
                            : x.punches
                                .map(
                                  (p) =>
                                    `${p.check_type === "in" ? "V" : "R"} ${p.time}${p.next_day ? "(+1)" : ""}`,
                                )
                                .join(" · ")}
                        </td>
                        <td>
                          <span className={`cc-otc-status ${tt.cls}`}>{tt.text}</span>
                        </td>
                        <td style={{ fontSize: 12, color: "var(--ash)" }}>
                          {ok && x.kieu ? KIEU[x.kieu] : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {result && (
            <div className="cc-otc-summary banner banner--ok" style={{ display: "block" }}>
              Đã sinh cặp bấm cho <b>{result.done.length}</b> người
              {result.skipped.length > 0 ? (
                <>
                  , bỏ qua <b>{result.skipped.length}</b>:
                  <ul>
                    {result.skipped.map((s) => (
                      <li key={s.employee_id}>
                        {s.employee_name ?? `NV #${s.employee_id}`} — {s.reason}
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                "."
              )}
            </div>
          )}

          <div className="cc-info-card-note">
            <AlertTriangle size={14} className="cc-note-icon" />
            <span>
              Lượt sinh ra là <b>chấm bù</b> có lý do và tên người xác nhận, nguyên nhân
              &quot;được duyệt&quot;; tiền tăng ca vẫn tính theo <b>phiếu ∩ giờ bấm</b>. Xoá
              được ở chi tiết ngày nếu bấm nhầm.
            </span>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Đóng
          </button>
          <button
            className="btn btn--primary"
            onClick={confirm}
            disabled={busy || checked.size === 0}
            title={soThieu === 0 ? "Không có ai thiếu cặp bấm" : undefined}
          >
            {busy ? (
              <RefreshCw className="cc-animate-spin" size={14} />
            ) : (
              `Xác nhận ${checked.size} người`
            )}
          </button>
        </footer>
      </div>
    </div>
  );
}
