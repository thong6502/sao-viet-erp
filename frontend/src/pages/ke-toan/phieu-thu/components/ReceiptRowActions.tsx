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
  const showMarkReceived = canMarkReceived && row.status === "waiting_receipt";
  const showCancel =
    canCancel &&
    (row.status === "waiting_receipt" ||
      ((row.source_type === "other" || row.source_type === "sales_invoice") &&
        row.status === "received"));
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
