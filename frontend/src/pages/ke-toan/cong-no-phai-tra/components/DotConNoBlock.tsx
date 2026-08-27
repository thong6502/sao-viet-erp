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
    // Đỏ CHỈ khi đang xem tab "Quá hạn" (lúc đó đúng nghĩa toàn bộ số hiện ra là nợ trễ). Tab
    // "Tất cả" gộp cả nợ chưa tới hạn — tô đỏ cả khối lúc đó là báo động giả cho phần lớn số
    // tiền vốn không có gì bất thường (UI_DESIGN.md §0: màu liều lớn ở chỗ không có việc).
    <section className={`pay-block${tab === "overdue" ? " pay-block--danger" : ""}`}>
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
        Hàng đã về tới đâu thì nợ tới đó, gom theo từng đơn mua, đợt mới nhất lên
        trước. Cột <strong>Đã trả</strong> chỉ đếm tiền trả đích danh đợt đó (khớp
        sao kê nhà cung cấp), <strong>Trừ cọc</strong> là phần cọc của cả đơn chiếu
        xuống — <strong>Còn nợ</strong> đã trừ cả hai. Đợt làm mờ là đợt đã trả
        xong, để dò được tiền cọc đi đâu.
        {chuaDatHan > 0 && (
          <>
            {" "}Có {chuaDatHan} khoản chưa có hạn trả — chúng không bao giờ
            vào cột Quá hạn nên được đẩy lên đầu; khai "Số ngày cho nợ" ở hồ
            sơ nhà cung cấp để hết ca này.
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
        gomTheoDon(khoanNo, detail.coc_chung).map((don) => {
          // Đỏ chỉ khi CHÍNH đơn này có ít nhất một đợt đang trễ — không phải mọi đơn có
          // "còn nợ" đều đỏ. `overdue_days` mỗi dòng đã tính sẵn ở server (aging_bucket cùng
          // nguồn), FE chỉ hỏi lại chứ không tự suy hạn.
          const dangTre = don.items.some((it) => it.overdue_days > 0);
          return (
          <div className="pay-don" key={don.purchase_request_id}>
            <div className="pay-don__head">
              <strong className="pay-don__code">{don.code}</strong>
              {don.coc && don.coc.amount > 0 && (
                // Cọc của CHÍNH đơn này, không phải tổng cọc của mọi đơn. Viết thành MỘT câu
                // theo đúng trạng thái, không chắp "nhãn: số · nhãn: số" — hai số bằng nhau
                // (trừ hết) đứng cạnh nhau từng khiến người đọc tưởng bị lặp/cộng dồn.
                // Trừ hết ⇒ badge moss (đã xong, khỏi làm gì thêm). Còn dư/chưa trừ ⇒ badge
                // amber (tiền đang "trôi nổi", chưa gán đợt nào — đáng để ý).
                <span
                  className={`pay-badge pay-badge--${don.coc.con_du > 0 ? "warn" : "ok"}`}
                >
                  <i className="pay-badge__dot" />
                  Cọc {money(don.coc.amount)}
                  {don.coc.con_du > 0
                    ? don.coc.da_dung > 0
                      ? ` · đã trừ ${money(don.coc.da_dung)} vào đợt giao, còn dư ${money(don.coc.con_du)}`
                      : " · chưa trừ vào đợt giao nào"
                    : " · đã trừ hết vào đợt giao"}
                </span>
              )}
              <span className="pay-don__due">
                còn nợ{" "}
                <b className={dangTre ? "pay-don__due--danger" : undefined}>
                  {money(don.con_no)}
                </b>
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
                  {/* Cột RIÊNG, không gộp vào "Đã trả" (chủ chốt 27/08/2026). Gộp thì bảng cộng
                      trừ khớp nhưng nói dối: đợt hiện "đã trả 100.000" trong khi không ai chuyển
                      cho nó đồng nào, cầm sao kê NCC dò không ra giao dịch đó. */}
                  <th className="pay-num">Trừ cọc</th>
                  <th className="pay-num">Còn nợ</th>
                </tr>
              </thead>
              <tbody>
                {don.items.map((row) => (
                  <tr
                    key={row.delivery_id ?? 0}
                    className={row.da_tat_toan ? "pay-row--done" : undefined}
                  >
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
                      {/* Đợt đã trả xong KHÔNG hiện hạn trả: hạn chỉ có nghĩa khi còn nợ, để lại
                          một ngày quá khứ là trông như đang trễ. */}
                      {row.da_tat_toan ? (
                        <span className="pay-cell--zero">đã trả xong</span>
                      ) : (
                        <HanTra row={row} />
                      )}
                    </td>
                    <td className="pay-num">{money(row.amount)}</td>
                    <td className="pay-num">
                      {row.paid > 0 ? (
                        money(row.paid)
                      ) : (
                        <span className="pay-cell--zero">—</span>
                      )}
                    </td>
                    <td className="pay-num">
                      {row.coc_bu > 0 ? (
                        money(row.coc_bu)
                      ) : (
                        <span className="pay-cell--zero">—</span>
                      )}
                    </td>
                    <td className="pay-num">
                      <strong>{money(row.con_no)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          );
        })
      )}
    </section>
  );
}
