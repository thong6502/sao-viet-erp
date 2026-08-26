// Bảng danh sách phiếu chi (tách từ pages/PaymentVouchersPage.tsx).
import { Fragment, type Dispatch, type SetStateAction } from "react";
import type { PaymentVoucherRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDateTime, money, originalMoney } from "../../../../utils/format";
import {
  SOURCE_LABELS,
  STATUS_META,
  VOUCHER_METHOD_LABELS,
} from "../shared/list-constants";

export function VouchersTable({
  loading,
  rows,
  selected,
  setSelectedId,
  total,
  page,
  setPage,
  totalPages,
}: {
  loading: boolean;
  rows: PaymentVoucherRow[];
  selected: PaymentVoucherRow | null;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  total: number;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  totalPages: number;
}) {
  return (
    <section className="md-page__tablewrap acct-list acct-list--voucher">
      <table className="md-page__table">
        <thead>
          <tr>
            {/* KHÔNG còn cột "Thao tác": bấm vào DÒNG mở drawer chi tiết, mọi thao tác nằm ở
                chân drawer (24/08/2026 — gộp thao tác vào bản ghi). */}
            <th>Mã chứng từ</th>
            <th>Đối tượng</th>
            <th>Người lập</th>
            <th>Lập lúc</th>
            <th className="acct-amount-cell">Số tiền</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk-${i}`} className="purchase__skeleton-row">
                <td><div className="purchase__skeleton-bar" style={{ width: "130px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "150px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
              </tr>
            ))}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={6}>Chưa có chứng từ phù hợp.</td>
            </tr>
          )}
          {!loading &&
            rows.map((row) => (
              <Fragment key={row.id}>
                <tr
                  className={
                    row.id === selected?.id ? "purchase__row--selected" : ""
                  }
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="acct-code-cell">
                    <strong>{row.code}</strong>
                    <small>
                      {VOUCHER_METHOD_LABELS[row.voucher_type] ?? row.voucher_type} ·{" "}
                      {SOURCE_LABELS[row.source_type] ?? row.source_type}
                    </small>
                  </td>
                  <td className="acct-target-cell">
                    <strong>{row.supplier_name}</strong>
                    {row.source_type === "purchase_request" && row.purchase_request_code && (
                      <small>{row.purchase_request_code}</small>
                    )}
                  </td>
                  <td className="acct-user-cell">
                    <div title={row.created_by_name ?? undefined}>
                      {row.created_by_name || "—"}
                    </div>
                  </td>
                  <td className="acct-time-cell">{fmtDateTime(row.created_at)}</td>
                  <td
                    className="acct-amount-cell"
                    title={
                      row.currency !== "VND"
                        ? `${originalMoney(row.amount, row.currency)} · tỷ giá ${row.exchange_rate}`
                        : undefined
                    }
                  >
                    <strong>{money(row.amount_vnd)}</strong>
                  </td>
                  <td className="acct-status-cell">
                    <span
                      className={`acct-pc__state acct-pc__state--${STATUS_META[row.status].tone}`}
                    >
                      <i className="acct-pc__dot" />
                      {STATUS_META[row.status].label}
                    </span>
                    {row.status === "paid" &&
                      row.attachment_count === 0 && (
                        <span className="acct-pc__flag">
                          <i className="acct-pc__dot" />
                          Thiếu chứng từ
                        </span>
                      )}
                  </td>
                </tr>
              </Fragment>
            ))}
        </tbody>
      </table>
      {!loading && (
        <div className="md-page__pager">
          <span>{total} chứng từ</span>
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
