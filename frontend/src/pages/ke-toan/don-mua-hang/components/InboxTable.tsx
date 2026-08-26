// Bảng danh sách đơn mua hàng (Kế toán) — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PurchaseRequestRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { CodeLink } from "../../../../components/CodeLink";
import { fmtDate, money } from "../../../../utils/format";
import { PAYMENT_META, STATUS_META } from "../shared/constants";
import { DepositCell } from "./inboxCells";

export function InboxTable({
  loading,
  rows,
  selected,
  setSelectedId,
  openYcmh,
  total,
  page,
  setPage,
  totalPages,
}: {
  loading: boolean;
  rows: PurchaseRequestRow[];
  selected: PurchaseRequestRow | null;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  openYcmh: (code: string) => void;
  total: number;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  totalPages: number;
}) {
  return (
    <section className="md-page__tablewrap acct-list acct-dmh__frame">
      <table className="md-page__table">
        <thead>
          <tr>
            {/* HAI cột trạng thái (đơn + thanh toán) đứng cạnh nhau ở cuối. KHÔNG còn cột
                "Thao tác": bấm vào DÒNG mở drawer chi tiết, mọi thao tác nằm ở chân drawer
                (24/08/2026 — gộp thao tác vào bản ghi). */}
            <th>Mã đơn</th>
            <th>Nhà cung cấp</th>
            <th>Ngày tạo</th>
            <th className="acct-amount-cell">Tổng đơn</th>
            <th className="acct-amount-cell">Tiền cọc</th>
            <th>Ngày cần</th>
            <th>Trạng thái</th>
            <th>Thanh toán</th>
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk-${i}`} className="purchase__skeleton-row">
                <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "150px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
              </tr>
            ))}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={8}>Không có đơn mua hàng phù hợp.</td>
            </tr>
          )}
          {!loading &&
            rows.map((row) => {
              const status = STATUS_META[row.status];
              const payment = PAYMENT_META[row.payment_status];
              return (
                <tr
                  key={row.id}
                  className={
                    row.id === selected?.id ? "purchase__row--selected" : ""
                  }
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="acct-code-cell">
                    <strong>{row.code}</strong>
                    <div className="purchase__source-codes">
                      {row.sources.map((source, index) => (
                        <span key={source.id}>
                          {index > 0 && ", "}
                          <CodeLink code={source.code} onOpen={openYcmh} />
                        </span>
                      ))}
                    </div>
                  </td>
                  <td
                    className="acct-supplier-cell"
                    title={row.supplier_name ?? undefined}
                  >
                    {row.supplier_name || "—"}
                  </td>
                  <td className="acct-dmh__date">{fmtDate(row.created_at)}</td>
                  <td className="acct-amount-cell">
                    <strong>{money(row.total_estimate)}</strong>
                  </td>
                  <td className="acct-amount-cell">
                    <DepositCell row={row} />
                  </td>
                  <td className="acct-dmh__date">
                    {fmtDate(row.needed_date)}
                  </td>
                  <td>
                    <span
                      className={`acct-dmh__state acct-dmh__state--${status.tone}`}
                    >
                      <i className="acct-dmh__dot" />
                      {status.label}
                    </span>
                  </td>
                  <td>
                    <strong className="acct-dmh__due">
                      {money(row.outstanding_amount)}
                    </strong>
                    <small>{payment.label}</small>
                  </td>
                </tr>
              );
            })}
        </tbody>
      </table>
      {!loading && (
        <div className="md-page__pager">
          <span>{total} đơn</span>
          <div>
            <Button
              variant="ghost"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Trước
            </Button>
            <span>
              {page}/{totalPages}
            </span>
            <Button
              variant="ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((value) => value + 1)}
            >
              Sau
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
