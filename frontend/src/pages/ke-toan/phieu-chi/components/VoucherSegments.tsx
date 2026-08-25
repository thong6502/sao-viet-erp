// Hai cụm chọn HÌNH THỨC CHI và LOẠI PHIẾU + cảnh báo cọc trùng
// (tách từ pages/PaymentVoucherDialog.tsx).
import type {
  PaymentVoucherBaseInput,
  PaymentVoucherRow,
  PaymentVoucherType,
  PurchaseRequestRow,
} from "../../../../api/client";
import { fmtDate, money } from "../../../../utils/format";
import type { LoaiPhieu } from "../shared/types";

export function VoucherSegments({
  form,
  voucher,
  selectType,
  loai,
  chonLoai,
  coDotGiao,
  purchase,
}: {
  form: PaymentVoucherBaseInput;
  voucher: PaymentVoucherRow | null;
  selectType: (type: PaymentVoucherType) => void;
  loai: LoaiPhieu;
  chonLoai: (next: LoaiPhieu) => void;
  coDotGiao: boolean;
  purchase: PurchaseRequestRow;
}) {
  return (
    <>
    <div className="acct-segment" aria-label="Hình thức chi">
      <button
        type="button"
        className={form.voucher_type === "cash" ? "is-active" : ""}
        onClick={() => selectType("cash")}
        disabled={!!voucher}
      >
        Tiền mặt
      </button>
      <button
        type="button"
        className={
          form.voucher_type === "bank_transfer" ? "is-active" : ""
        }
        onClick={() => selectType("bank_transfer")}
        disabled={!!voucher}
      >
        Chuyển khoản
      </button>
    </div>

    {/* LOẠI PHIẾU đứng TRƯỚC mọi ô khác vì nó quyết định trần, đợt giao và số tiền điền
        sẵn. Người dùng chọn sai ở đây thì mọi ô dưới đều sai theo. */}
    <div className="acct-segment" aria-label="Loại phiếu">
      <button
        type="button"
        className={loai === "dat_coc" ? "is-active" : ""}
        onClick={() => chonLoai("dat_coc")}
        disabled={!!voucher}
      >
        Đặt cọc / ứng trước
      </button>
      <button
        type="button"
        className={loai === "thanh_toan" ? "is-active" : ""}
        onClick={() => chonLoai("thanh_toan")}
        disabled={!!voucher || !coDotGiao}
        title={
          coDotGiao
            ? undefined
            : "Đơn chưa ghi đợt giao nào — hàng chưa về thì mọi khoản chi đều là đặt cọc."
        }
      >
        Thanh toán
      </button>
    </div>
    <p className="acct-loai-hint">
      {loai === "dat_coc"
        ? "Cọc là tiền chi khi hàng CHƯA về nên không gắn đợt giao. Trần tính theo giá trị đơn đặt; cọc trừ vào công nợ của cả đơn."
        : "Trả cho một ĐỢT GIAO cụ thể. Trần đúng bằng công nợ đã phát sinh — chi quá là trả tiền cho hàng chưa về."}
    </p>
    {/* Đơn ĐÃ có phiếu cọc mà lại đang lập phiếu cọc nữa — CẢNH BÁO, không chặn.
        Ứng thêm là ca có thật (cọc 30% rồi NCC đòi ứng thêm 20%), và mỗi lần tiền rời két
        phải là một chứng từ riêng: sửa phiếu cọc cũ lên số to hơn là làm phiếu không khớp
        lần chi thật. Nhưng bấm nhầm cũng là ca có thật, nên phải đập vào mắt. */}
    {!voucher && loai === "dat_coc" && purchase.coc_da_lap.length > 0 && (
      <div className="banner banner--warn" role="status">
        Đơn này <strong>đã có {purchase.coc_da_lap.length} phiếu đặt cọc</strong> —{" "}
        {purchase.coc_da_lap
          .map(
            (c) =>
              `${c.doc_no ?? c.code} ${money(c.amount)} ngày ${fmtDate(c.voucher_date)}`,
          )
          .join(" · ")}
        , tổng <strong>{money(purchase.coc_da_chi)}</strong>. Đây là phiếu cọc
        thứ {purchase.coc_da_lap.length + 1}. Nếu chỉ muốn sửa số cọc cũ thì
        đóng hộp này và sửa đúng phiếu đó.
      </div>
    )}
    </>
  );
}
