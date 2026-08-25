// Khối "Đã trả" (lịch sử tiền đã rời két) trong drawer Công nợ phải trả
// (tách từ pages/AccountingPayablesPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import type { PayablesDetail } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDate, money } from "../../../../utils/format";
import { PAID_PAGE } from "../shared/constants";
import { HoaDon } from "./payablesCells";

export function DaTraBlock({
  detail,
  paidOpen,
  setPaidOpen,
  paidShown,
  setPaidShown,
  setXemHetLichSu,
}: {
  detail: PayablesDetail;
  paidOpen: boolean;
  setPaidOpen: Dispatch<SetStateAction<boolean>>;
  paidShown: number;
  setPaidShown: Dispatch<SetStateAction<number>>;
  setXemHetLichSu: Dispatch<SetStateAction<boolean>>;
}) {
  return (
    <section className="pay-block pay-block--ok">
      <header className="pay-block__head">
        <button
          type="button"
          className="pay-toggle"
          onClick={() => setPaidOpen((v) => !v)}
        >
          {paidOpen ? "▾" : "▸"}{" "}
          {detail.all_history
            ? "Đã trả — toàn bộ lịch sử"
            : `Đã trả (${detail.period_months} tháng)`}{" "}
          ({detail.paid.length} lần)
        </button>
        <strong>{money(detail.paid_in_period)}</strong>
      </header>
      {paidOpen &&
        (detail.paid.length === 0 ? (
          <>
            <p className="pay-empty">
              {detail.all_history
                ? "Chưa trả lần nào cho nhà cung cấp này."
                : `Chưa trả lần nào trong ${detail.period_months} tháng gần nhất.`}
            </p>
            {!detail.all_history && (
              <Button
                variant="ghost"
                onClick={() => setXemHetLichSu(true)}
              >
                Xem lịch sử cũ hơn
              </Button>
            )}
          </>
        ) : (
          <>
            <p className="pay-block__hint">
              Tiền đã rời két — từng lần một, cộng lại đúng bằng cột "Đã
              trả" ngoài bảng. Đặt cạnh sao kê nhà cung cấp là đối chiếu
              được từng dòng.
            </p>
            <table className="pay-table">
              <thead>
                <tr>
                  <th>Ngày trả</th>
                  <th>Phiếu chi</th>
                  {/* Ai LẬP phiếu — đứng cạnh chính số phiếu của người đó, vì câu hỏi khi
                      soi sao kê luôn là "phiếu này ai cho ra". */}
                  <th>Người lập</th>
                  <th>Hóa đơn</th>
                  <th>Đơn · Đợt</th>
                  <th className="pay-num">Số tiền</th>
                </tr>
              </thead>
              <tbody>
                {detail.paid.slice(0, paidShown).map((row) => (
                  <tr key={row.voucher_id}>
                    <td>{fmtDate(row.paid_date)}</td>
                    <td>
                      {row.doc_no ?? row.code}
                      {!row.has_attachment && (
                        // CẢNH BÁO, không chặn — tiền đã ra rồi, chặn ở đây chẳng cứu được gì.
                        <small className="pay-warn">
                          {" "}
                          chưa có chứng từ
                        </small>
                      )}
                    </td>
                    <td title={row.created_by_name ?? undefined}>
                      {row.created_by_name || "—"}
                    </td>
                    <td>
                      <HoaDon
                        so={row.invoice_number}
                        ngay={row.invoice_date}
                      />
                    </td>
                    <td>
                      {row.purchase_code}
                      {/* Phải nói ĐỢT MẤY, không được ghi "trả theo đợt" chung chung: người
                          cầm sao kê nhà cung cấp đối chiếu từng dòng cần biết dòng nào ứng
                          với đợt nào. */}
                      <small>
                        {" "}
                        {row.payment_stage === "advance"
                          ? "· đặt cọc"
                          : row.delivery_seq_no != null
                            ? `· Đợt ${row.delivery_seq_no}`
                            : "· không theo đợt"}
                      </small>
                    </td>
                    <td className="pay-num">{money(row.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {detail.paid.length > paidShown && (
              <Button
                variant="ghost"
                onClick={() => setPaidShown((n) => n + PAID_PAGE)}
              >
                Xem thêm {detail.paid.length - paidShown} lần trả
              </Button>
            )}
            {!detail.all_history && (
              <Button
                variant="ghost"
                onClick={() => setXemHetLichSu(true)}
              >
                Xem lịch sử cũ hơn {detail.period_months} tháng
              </Button>
            )}
          </>
        ))}
    </section>
  );
}
