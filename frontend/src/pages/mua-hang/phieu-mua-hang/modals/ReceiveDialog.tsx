// Hộp khai SỐ THỰC NHẬN (tách từ pages/PurchaseRequestsPage.tsx).
import { useState } from "react";
import { ApiError, api, type PurchaseRequestRow } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";

/**
 * Khai SỐ THỰC NHẬN lúc bấm "Đã nhận hàng".
 *
 * Ô số điền sẵn bằng số đã đặt ⇒ hàng về đủ thì chỉ bấm Xác nhận, KHÔNG phải gõ gì. Chỉ khi NCC
 * giao thiếu mới phải sửa xuống. Số này là nền của công nợ và là trần lập phiếu chi — ghi nợ đủ
 * cho hàng về thiếu là kế toán chi thừa tiền thật.
 *
 * `mode="edit"` dùng cho ca NCC giao nhiều đợt (đợt 1 về 600, đợt 2 về nốt thì sửa lên 1000);
 * đường này server đòi quyền DUYỆT vì nó đổi số nợ đã ghi.
 */
export function ReceiveDialog({
  row,
  mode,
  onClose,
  onDone,
}: {
  row: PurchaseRequestRow;
  mode: "receive" | "edit";
  onClose: () => void;
  onDone: (next: PurchaseRequestRow) => void;
}) {
  const { token } = useAuth();
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      row.lines.map((line) => [
        line.id,
        String(line.received_quantity ?? line.quantity),
      ]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const thieu = row.lines.some(
    (line) => Number(values[line.id] ?? line.quantity) < line.quantity,
  );

  async function submit() {
    if (!token) return;
    const lines = row.lines.map((line) => ({
      line_id: line.id,
      received_quantity: Number(values[line.id] ?? line.quantity),
    }));
    if (lines.some((l) => !Number.isFinite(l.received_quantity!) || l.received_quantity! < 0)) {
      setError("Số thực nhận phải là số không âm.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        mode === "receive"
          ? await api.purchaseRequests.markReceived(token, row.id, lines)
          : await api.purchaseRequests.updateReceivedQuantities(token, row.id, lines),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lưu được số thực nhận.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      title={mode === "receive" ? "Xác nhận đã nhận hàng" : "Sửa số thực nhận"}
      message={`Phiếu ${row.code} — về đủ thì bấm Xác nhận, về thiếu thì sửa số xuống.`}
      confirmLabel={mode === "receive" ? "Xác nhận đã nhận" : "Lưu số thực nhận"}
      busy={busy}
      error={error}
      onConfirm={submit}
      onCancel={onClose}
    >
      <table className="pay-table">
        <thead>
          <tr>
            <th>Vật tư</th>
            <th className="pay-num">Đặt</th>
            <th className="pay-num">Thực nhận</th>
          </tr>
        </thead>
        <tbody>
          {row.lines.map((line) => (
            <tr key={line.id}>
              <td>{line.item_name}</td>
              <td className="pay-num">
                {line.quantity} {line.unit}
              </td>
              <td className="pay-num">
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={line.quantity}
                  step="any"
                  style={{ width: 110, textAlign: "right" }}
                  value={values[line.id] ?? ""}
                  onChange={(e) =>
                    setValues((current) => ({ ...current, [line.id]: e.target.value }))
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {thieu && (
        <p className="pay-block__hint" style={{ marginTop: 8 }}>
          Có dòng nhận thiếu so với số đặt — công nợ và trần lập phiếu chi sẽ tính theo số thực
          nhận.
        </p>
      )}
    </ConfirmDialog>
  );
}
