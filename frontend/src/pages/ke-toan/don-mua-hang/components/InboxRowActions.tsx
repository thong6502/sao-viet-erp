// Cụm NÚT THAO TÁC của một đơn (Duyệt · Từ chối · Lập Phiếu chi)
// — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PurchaseRequestRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";

export function InboxRowActions({
  row,
  compact,
  canApprove,
  canCreateVoucher,
  busy,
  closeDetailThen,
  approve,
  setRejecting,
  setRejectReason,
  setVoucherMode,
}: {
  row: PurchaseRequestRow;
  compact: boolean;
  canApprove: boolean;
  canCreateVoucher: boolean;
  busy: string | null;
  closeDetailThen: (action: () => void) => void;
  approve: (row: PurchaseRequestRow) => Promise<void>;
  setRejecting: Dispatch<SetStateAction<PurchaseRequestRow | null>>;
  setRejectReason: Dispatch<SetStateAction<string>>;
  setVoucherMode: Dispatch<
    SetStateAction<null | { purchase: PurchaseRequestRow }>
  >;
}) {
  const showApprove = canApprove && row.status === "pending_approval";
  // Chỉ đơn ĐÃ DUYỆT mới lập được phiếu chi — và người lập là KẾ TOÁN, không cần quyền
  // duyệt. Backend cũng đã chặn (`accounting_service` chỉ nhận PMH từ approved trở lên),
  // đây là lớp hiển thị cho khớp.
  // Trần lập phiếu nay có HAI mức khác nhau (Đ1/§5.4): `tran_dat_coc` cho phiếu đặt cọc
  // (theo giá trị đơn đặt — cọc là chi khi hàng chưa về) và `outstanding_amount` = CÔNG NỢ
  // cho phiếu thanh toán. Còn chỗ ở một trong hai là còn lập được, nên nút hiện khi tổng
  // hai đường còn > 0; hộp thoại mới là chỗ chốt trần theo loại phiếu đã chọn.
  const showVoucher =
    canCreateVoucher &&
    ["approved", "purchased", "partially_received", "received"].includes(
      row.status,
    ) &&
    Math.max(row.tran_dat_coc, row.outstanding_amount) > 0;

  // Nút Từ chối đi kèm CÙNG điều kiện với showApprove — cả ba nút cùng vắng mặt thì
  // đừng trả về container rỗng, để cha (chân drawer) bỏ hẳn khung bao ngoài.
  if (!showApprove && !showVoucher) return null;

  return (
    <div className={`acct-actions${compact ? " acct-actions--compact" : ""}`}>
      {showApprove && (
        <>
          {/* HAI BƯỚC RỜI (chủ 04/08/2026): giám đốc duyệt trước, kế toán lập phiếu chi sau —
              hai chữ ký, hai người. Nút "Duyệt & lập chứng từ" gộp cả hai vào một cú bấm đã bỏ. */}
          <Button
            type="button"
            variant="accent"
            loading={busy === `approve-${row.id}`}
            onClick={() => closeDetailThen(() => approve(row))}
          >
            Duyệt
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              closeDetailThen(() => {
                setRejecting(row);
                setRejectReason("");
              })
            }
          >
            Từ chối
          </Button>
        </>
      )}
      {showVoucher && (
        <Button
          type="button"
          variant="accent"
          onClick={() =>
            closeDetailThen(() =>
              setVoucherMode({ purchase: row }),
            )
          }
        >
          Lập Phiếu chi
        </Button>
      )}
    </div>
  );
}
