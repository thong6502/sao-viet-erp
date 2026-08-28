// Cụm NÚT THAO TÁC của một phiếu thu (In · Sửa · Xác nhận đã thu · Hủy)
// — tách từ pages/PaymentReceiptsPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PaymentReceiptRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";

export function ReceiptRowActions({
  row,
  canExport,
  startPrint,
  canApprove,
  closeDetailThen,
  openEdit,
  busy,
  canMarkReceived,
  setMarking,
  setBankReference,
  canCancel,
  setCancelling,
  setCancelReason,
}: {
  row: PaymentReceiptRow;
  canExport: boolean;
  startPrint: (row: PaymentReceiptRow) => void;
  canApprove: boolean;
  closeDetailThen: (action: () => void) => void;
  openEdit: (row: PaymentReceiptRow) => Promise<void>;
  busy: boolean;
  canMarkReceived: boolean;
  setMarking: Dispatch<SetStateAction<PaymentReceiptRow | null>>;
  setBankReference: Dispatch<SetStateAction<string>>;
  canCancel: boolean;
  setCancelling: Dispatch<SetStateAction<PaymentReceiptRow | null>>;
  setCancelReason: Dispatch<SetStateAction<string>>;
}) {
  const showExport = canExport;
  const showEdit =
    canApprove &&
    row.status === "waiting_receipt" &&
    row.source_type === "purchase_refund";
  // "Xác nhận đã thu" chỉ còn cho phiếu CŨ lỡ nằm lại ở trạng thái chờ — từ 27/08/2026 phiếu thu
  // lập ra là ĐÃ THU (chủ chốt: *"cứ lập phiếu là ra tiền rồi xác nhận cái gì nữa"*), nên với mọi
  // phiếu mới nút này không bao giờ hiện. Giữ nhánh chứ không xoá hẳn: xoá là phiếu chờ còn sót
  // trong DB thật hết đường chốt, mà chúng đang KHÔNG được trừ vào công nợ.
  const showMarkReceived = canMarkReceived && row.status === "waiting_receipt";
  // Huỷ được ở mọi trạng thái, mọi nguồn — khớp `cancel_receipt` bên service. Phiếu lập ra đã thu
  // ngay thì huỷ (có lý do) là đường sửa sai DUY NHẤT; siết lại là phiếu gõ nhầm kẹt vĩnh viễn.
  const showCancel = canCancel && row.status !== "cancelled";
  if (!showExport && !showEdit && !showMarkReceived && !showCancel) return null;
  return (
    <div className="acct-actions">
      {showExport && (
        <Button variant="ghost" onClick={() => startPrint(row)}>
          In phiếu
        </Button>
      )}
      {showEdit && (
        <Button
          variant="ghost"
          onClick={() => closeDetailThen(() => openEdit(row))}
          disabled={busy}
        >
          Sửa
        </Button>
      )}
      {showMarkReceived && (
        <Button
          variant="accent"
          onClick={() =>
            closeDetailThen(() => {
              setMarking(row);
              setBankReference("");
            })
          }
        >
          Xác nhận đã thu
        </Button>
      )}
      {showCancel && (
        <Button
          variant="danger"
          onClick={() =>
            closeDetailThen(() => {
              setCancelling(row);
              setCancelReason("");
            })
          }
        >
          Hủy
        </Button>
      )}
    </div>
  );
}
