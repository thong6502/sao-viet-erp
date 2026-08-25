// Gán MỘT hoá đơn cho NHIỀU đợt giao (tách từ pages/PurchaseRequestsPage.tsx).
import { useState } from "react";
import { ApiError, api, type PurchaseRequestRow } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import { fmtDate, money } from "../../../../utils/format";
import { todayInputValue } from "../shared/helpers";

/**
 * GÁN MỘT HOÁ ĐƠN CHO NHIỀU ĐỢT.
 *
 * Ca thật: NCC giao ba đợt rồi mới xuất một hoá đơn chung. Không có thao tác này thì kế toán phải
 * mở sửa từng đợt và gõ lại cùng một số ba lần — gõ lệch một ký tự là hệ hiểu thành ba hoá đơn.
 */
export function InvoiceDialog({
  row,
  onClose,
  onDone,
}: {
  row: PurchaseRequestRow;
  onClose: () => void;
  onDone: (next: PurchaseRequestRow) => void;
}) {
  const { token } = useAuth();
  const [chon, setChon] = useState<number[]>(() =>
    row.deliveries.filter((d) => !d.invoice_number).map((d) => d.id),
  );
  const [so, setSo] = useState("");
  const [ngay, setNgay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!token || busy) return;
    if (chon.length === 0) {
      setError("Chưa chọn đợt giao nào để gán hóa đơn.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        await api.purchaseRequests.assignInvoice(token, row.id, {
          delivery_ids: chon,
          invoice_number: so.trim() || null,
          invoice_date: ngay || null,
        }),
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không gán được hóa đơn.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      title="Gán hóa đơn cho nhiều đợt"
      message={`Phiếu ${row.code} — các đợt được chọn sẽ mang CÙNG một số hóa đơn. Để trống số hóa đơn là gỡ hóa đơn khỏi các đợt đó.`}
      confirmLabel="Gán hóa đơn"
      busy={busy}
      error={error}
      onConfirm={submit}
      onCancel={onClose}
    >
      <div className="pdot__form">
        <label className="purchase__field">
          <span>Số hóa đơn</span>
          <input
            className="input"
            maxLength={64}
            autoFocus
            value={so}
            onChange={(e) => setSo(e.target.value)}
          />
        </label>
        <label className="purchase__field">
          <span>Ngày hóa đơn</span>
          <input
            className="input"
            type="date"
            max={todayInputValue()}
            value={ngay}
            onChange={(e) => setNgay(e.target.value)}
          />
        </label>
      </div>
      <table className="pay-table">
        <thead>
          <tr>
            {/* Cột ô chọn — `<th>` rỗng là ô câm với trình đọc màn hình, phải có `aria-label`. */}
            <th aria-label="Chọn đợt giao" />
            <th>Đợt</th>
            <th>Ngày giao</th>
            <th>Hóa đơn hiện tại</th>
            <th className="pay-num">Thành tiền</th>
          </tr>
        </thead>
        <tbody>
          {row.deliveries.map((dot) => (
            <tr key={dot.id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={`Chọn đợt ${dot.seq_no}`}
                  checked={chon.includes(dot.id)}
                  onChange={(e) =>
                    setChon((cur) =>
                      e.target.checked
                        ? [...cur, dot.id]
                        : cur.filter((id) => id !== dot.id),
                    )
                  }
                />
              </td>
              <td>
                <strong>Đợt {dot.seq_no}</strong>
              </td>
              <td>{fmtDate(dot.delivery_date)}</td>
              <td>
                {dot.invoice_number ?? (
                  <small className="pdot__muted">chưa gán</small>
                )}
              </td>
              <td className="pay-num">{money(dot.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ConfirmDialog>
  );
}
