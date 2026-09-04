// Popup HÀNG CỦA MỘT ĐỢT GIAO — mở từ bảng "Đợt giao còn nợ" (chủ chốt 28/08/2026:
// *"khi tôi bấm vào đợt giao đó thì phải hiện tên các sản phẩm, số lượng, đơn vị tính"*).
//
// Vì sao là POPUP chứ không phải thêm một cột "Hàng đã nhận" như bên Thu mua: bảng này đã có 8
// cột và bốn trong số đó là TIỀN (Giá trị · Đã trả · Trừ cọc · Còn nợ) phải đi liền nhau để đọc
// ra phép trừ. Nhét thêm một cột chữ vào giữa là đẩy cụm tiền ra khỏi tầm mắt ở 1440px — đúng
// bệnh đã vá một lần ở khối này.
//
// CHỈ ĐỌC nên nền mờ bấm được là đóng, khác `InvoiceReceiptForm` (hộp đó chặn vì đang có nháp gõ
// dở, bấm nhầm ra ngoài là mất).
import { useEffect } from "react";
import type { PayableItemRow } from "../../../../api/client";
// Đơn vị lưu bằng MÃ (`cai`), tên hiển thị ("cái") nằm ở danh mục Đơn vị — xem pages/tenDonVi.ts.
import { tenDonVi } from "../../../tenDonVi";
import { fmtDate, money } from "../../../../utils/format";
import { tenKhoan } from "../shared/helpers";

export function HangCuaDotModal({
  item,
  maDon,
  onClose,
}: {
  item: PayableItemRow;
  maDon: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  return (
    <div className="acct-modal" role="presentation" onClick={onClose}>
      <div
        className="acct-modal__box"
        role="dialog"
        aria-modal="true"
        aria-label={`Hàng đã nhận của ${tenKhoan(item)} — ${maDon}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Hàng đã nhận</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">
                  {tenKhoan(item)} · {maDon}
                </h2>
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={onClose}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>Giao {fmtDate(item.delivery_date)}</span>
            <span>Giá trị {money(item.amount)}</span>
          </div>
        </div>
        <div className="acct-modal__body">
          {item.lines.length === 0 ? (
            // Dòng "cả đơn" của phiếu CŨ không quy về đợt nào nên không có hàng. Màn hình đã chặn
            // không cho bấm, nhưng vẫn phải có nhánh này — không thì đổi luật một cái là hộp rỗng.
            <p className="md-page__muted">
              Khoản này ghi ở mức phiếu, không tách theo đợt giao nên không có
              danh sách hàng.
            </p>
          ) : (
            <table className="pay-table">
              <thead>
                <tr>
                  <th>Mặt hàng</th>
                  <th className="pay-num">Số lượng</th>
                  <th className="pay-num">Đơn giá</th>
                  <th className="pay-num">Thành tiền</th>
                </tr>
              </thead>
              <tbody>
                {item.lines.map((line, i) => (
                  <tr key={`${line.item_name}-${i}`}>
                    <td>
                      {line.item_name}
                      {/* DƯ = phần giao VƯỢT số đặt, tính 0đ (chủ chốt 28/08/2026). Phơi ra ngay
                          tại dòng — không thì người đọc thấy số lượng lớn mà thành tiền thấp hơn
                          quantity×đơn giá, tưởng máy tính sai trong khi máy đang tính ĐÚNG. */}
                      {line.du > 0 && (
                        <span
                          className="pay-cell--zero"
                          title="Phần giao vượt số đặt trên phiếu mua — hệ không tính tiền phần này. Kiểm lại với NCC nếu thực tế họ có tính tiền, đừng để sổ thiếu nợ."
                        >
                          {" "}
                          (trong đó {line.du.toLocaleString("vi-VN")}{" "}
                          {tenDonVi(line.unit) ?? line.unit} dư, 0 đ)
                        </span>
                      )}
                    </td>
                    <td className="pay-num">
                      {line.quantity.toLocaleString("vi-VN")}{" "}
                      {tenDonVi(line.unit) ?? line.unit}
                    </td>
                    <td className="pay-num">{money(line.unit_price)}</td>
                    <td className="pay-num">
                      <strong>{money(line.thanh_tien)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>Tổng cộng</td>
                  <td className="pay-num">
                    <strong>
                      {money(item.lines.reduce((s, l) => s + l.thanh_tien, 0))}
                    </strong>
                  </td>
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
