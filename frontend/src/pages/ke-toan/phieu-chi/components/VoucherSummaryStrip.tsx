// Dải TỔNG QUAN TIỀN của hộp lập phiếu chi (tách từ pages/PaymentVoucherDialog.tsx).
// ⚠️ TIỀN THẬT — bốn con số này move nguyên văn, không sửa một ký tự nào.
import type { PurchaseRequestRow } from "../../../../api/client";
import type { LoaiPhieu } from "../shared/types";

export function VoucherSummaryStrip({
  purchase,
  loai,
  maxAmountVnd,
}: {
  purchase: PurchaseRequestRow;
  loai: LoaiPhieu;
  maxAmountVnd: number;
}) {
  return (
    <>
    {/* Bốn số theo đúng công thức mới: nợ = HÀNG ĐÃ VỀ − đã chi ròng. Ô cuối đổi nghĩa theo
        LOẠI phiếu đang chọn, nên nhãn của nó cũng phải đổi — để nguyên "Còn được lập" là
        người dùng không biết con số đang đo cái gì. */}
    <div className="acct-summary-strip">
      <div>
        <span>Tổng PMH</span>
        <strong>
          {purchase.total_estimate.toLocaleString("vi-VN")} đ
        </strong>
      </div>
      <div>
        <span>Hàng đã giao</span>
        <strong>
          {purchase.gia_tri_da_giao.toLocaleString("vi-VN")} đ
        </strong>
      </div>
      <div>
        <span>Đã chi ròng</span>
        <strong>{purchase.net_paid.toLocaleString("vi-VN")} đ</strong>
      </div>
      <div>
        <span>
          {loai === "dat_coc" ? "Trần đặt cọc" : "Công nợ (trần chi)"}
        </span>
        <strong>{maxAmountVnd.toLocaleString("vi-VN")} đ</strong>
      </div>
    </div>
    </>
  );
}
