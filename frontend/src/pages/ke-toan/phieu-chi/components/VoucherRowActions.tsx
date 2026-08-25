// Cụm NÚT THAO TÁC của một phiếu chi (In · Lập phiếu thu · Hủy)
// — tách từ pages/PaymentVouchersPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PaymentVoucherRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";

export function VoucherRowActions({
  row,
  canExport,
  startPrint,
  closeDetailThen,
  canCancel,
  setCancelling,
  setCancelReason,
}: {
  row: PaymentVoucherRow;
  canExport: boolean;
  startPrint: (row: PaymentVoucherRow) => void;
  closeDetailThen: (action: () => void) => void;
  canCancel: boolean;
  setCancelling: Dispatch<SetStateAction<PaymentVoucherRow | null>>;
  setCancelReason: Dispatch<SetStateAction<string>>;
}) {
  return (
    <div className="acct-actions">
      {canExport && (
        <Button variant="ghost" onClick={() => startPrint(row)}>
          In phiếu
        </Button>
      )}
      {/* KHÔNG có nút SỬA (chủ chốt 07/08/2026): phiếu chi phát hành ra là TIỀN ĐÃ RỜI KÉT,
          sửa nó là làm tờ giấy đang nằm ở chỗ nhà cung cấp khác với bản trong máy. Sai thì HUỶ
          (giữ số chứng từ, có lý do) rồi lập phiếu mới — dấu vết còn đủ hai bản.
          Thứ duy nhất còn sửa được là ĐÍNH KÈM tài liệu: hoá đơn / UNC thường về sau khi chi. */}
      {/* {canApprove && row.status === "paid" && (
        <Button
          variant="ghost"
          onClick={() => closeDetailThen(() => openTopUp(row))}
          disabled={busy}
        >
          Chi bổ sung
        </Button>
      )}
      {canApprove &&
        row.status === "paid" &&
        row.receipt_received_amount + row.receipt_pending_amount <
          row.amount_vnd && (
          <Button
            variant="ghost"
            onClick={() => closeDetailThen(() => setReceiptFor(row))}
            disabled={busy}
          >
            Lập phiếu thu
          </Button>
        )} */}
      {/* HUỶ nay áp cho phiếu ĐÃ CHI — dùng cho ca ghi nhận nhầm. Bắt lý do; server chặn nếu
          phiếu đã có phiếu thu gắn vào (tiền đã hoàn về thì không xoá dấu vết được nữa), nên
          nút vẫn hiện và người dùng nhận đúng câu báo thay vì im lặng không có lối. */}
      {canCancel &&
        row.status === "paid" &&
        row.receipt_received_amount + row.receipt_pending_amount === 0 && (
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
