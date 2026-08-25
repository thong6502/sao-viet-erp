// Khối "Đợt giao còn nợ" trong drawer Công nợ phải trả
// (tách từ pages/AccountingPayablesPage.tsx).
import type {
  PayableItemRow,
  PayablesDetail,
} from "../../../../api/client";
import type { NavigateFn } from "../../../../components/AppShell";
import { Button } from "../../../../components/Button";
import { fmtDate, money } from "../../../../utils/format";
import { gomTheoDon, tenKhoan } from "../shared/helpers";
import type { Bucket } from "../shared/types";
import { HanTra, HoaDon } from "./payablesCells";

export function DotConNoBlock({
  detail,
  tab,
  khoanNo,
  chuaDatHan,
  canCreateVoucher,
  navigate,
  onClose,
  onChanged,
}: {
  detail: PayablesDetail;
  tab: Bucket;
  khoanNo: PayableItemRow[];
  chuaDatHan: number;
  canCreateVoucher: boolean;
  navigate: NavigateFn;
  onClose: () => void;
  onChanged: () => void;
}) {
  return (
    <section className="pay-block pay-block--danger">
      <header className="pay-block__head">
        <h3>Đợt giao còn nợ</h3>
        <strong>
          {money(
            tab === "overdue"
              ? detail.overdue_amount
              : detail.total_due,
          )}
        </strong>
      </header>
      <p className="pay-block__hint">
        Hàng đã về tới đâu thì nợ tới đó, gom theo từng đơn mua. Cột{" "}
        <strong>Đã trả</strong> chỉ đếm tiền trả{" "}
        <strong>đích danh đợt đó</strong> (khớp sao kê nhà cung cấp).{" "}
        <strong>Còn nợ</strong> đã trừ cả tiền cọc của đơn — nên có đợt
        chưa trả đồng nào mà còn nợ vẫn nhỏ hơn giá trị đợt.
        {chuaDatHan > 0 && (
          <>
            {" "}
            Có <strong>{chuaDatHan} khoản chưa có hạn trả</strong> —
            chúng không bao giờ vào cột Quá hạn nên được đẩy lên đầu;
            khai "Số ngày cho nợ" ở hồ sơ nhà cung cấp để hết ca này.
          </>
        )}
      </p>
      {khoanNo.length === 0 ? (
        <p className="pay-empty">
          {tab === "overdue"
            ? "Không có khoản nào quá hạn."
            : "Không còn khoản nợ nào với nhà cung cấp này."}
        </p>
      ) : (
        gomTheoDon(khoanNo, detail.coc_chung).map((don) => (
          <div className="pay-don" key={don.purchase_request_id}>
            <div className="pay-don__head">
              <strong className="pay-don__code">{don.code}</strong>
              {don.coc && don.coc.amount > 0 && (
                // Cọc của CHÍNH đơn này, không phải tổng cọc của mọi đơn. `da_dung` nói
                // rõ nó đã bù vào đâu — thiếu số đó thì người đọc thấy một khoản trừ mà
                // không biết trừ vào đợt nào.
                <span className="pay-don__coc">
                  cọc {money(don.coc.amount)}
                  {don.coc.da_dung > 0 && ` · đã bù ${money(don.coc.da_dung)}`}
                  {don.coc.con_du > 0 && ` · còn dư ${money(don.coc.con_du)}`}
                </span>
              )}
              <span className="pay-don__due">
                còn nợ <b>{money(don.con_no)}</b>
              </span>
              {canCreateVoucher && (
                // MỘT nút cho cả đơn, không phải mỗi đợt một nút: màn đích là hộp lập
                // phiếu chi của ĐƠN, chọn đợt nào là chọn trong đó.
                <Button
                  variant="ghost"
                  onClick={() => {
                    onChanged();
                    onClose();
                    navigate("ke-toan-don-mua-hang", {
                      focusRequestCode: don.code,
                    });
                  }}
                >
                  Lập phiếu chi
                </Button>
              )}
            </div>
            <table className="pay-table">
              <thead>
                <tr>
                  <th>Đợt</th>
                  <th>Ngày giao</th>
                  <th>Hóa đơn</th>
                  <th>Hạn trả</th>
                  <th className="pay-num">Giá trị</th>
                  <th className="pay-num">Đã trả</th>
                  <th className="pay-num">Còn nợ</th>
                </tr>
              </thead>
              <tbody>
                {don.items.map((row) => (
                  <tr key={row.delivery_id ?? 0}>
                    <td>
                      <strong>{tenKhoan(row)}</strong>
                    </td>
                    <td>{fmtDate(row.delivery_date)}</td>
                    <td>
                      <HoaDon
                        so={row.invoice_number}
                        ngay={row.invoice_date}
                      />
                    </td>
                    <td>
                      <HanTra row={row} />
                    </td>
                    <td className="pay-num">{money(row.amount)}</td>
                    <td className="pay-num">{money(row.paid)}</td>
                    <td className="pay-num">
                      <strong>{money(row.con_no)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}
    </section>
  );
}
