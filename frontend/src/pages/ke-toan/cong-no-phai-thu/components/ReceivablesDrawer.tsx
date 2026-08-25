// Drawer CHI TIẾT công nợ một khách hàng (tách từ pages/AccountingReceivablesPage.tsx).
import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type ReceivableCustomerRow,
  type ReceivableItemRow,
  type ReceivablesDetail,
} from "../../../../api/client";
import { useCan } from "../../../../auth/permissions";
import type { NavigateFn } from "../../../../components/AppShell";
import { Button } from "../../../../components/Button";
import { CodeLink } from "../../../../components/CodeLink";
import { fmtDate, money } from "../../../../utils/format";
import { methodText } from "../shared/helpers";
import { InvoiceReceiptForm } from "./InvoiceReceiptForm";

export function ReceivablesDrawer({
  row,
  token,
  navigate,
  eventTick,
  onChanged,
  onClose,
}: {
  row: ReceivableCustomerRow;
  token: string | null;
  navigate: NavigateFn;
  eventTick: number;
  onChanged: () => void;
  onClose: () => void;
}) {
  const can = useCan();
  const canCreateReceipt = can("phieu_thu", "create");
  const [detail, setDetail] = useState<ReceivablesDetail | null>(null);
  const [allHistory, setAllHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receiptFor, setReceiptFor] = useState<ReceivableItemRow | null>(null);
  const [accounts, setAccounts] = useState<CompanyBankAccountRow[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);

  const loadDetail = useCallback(() => {
    if (!token || row.customer_id == null) return;
    setError(null);
    api.accounting
      .receivablesDetail(token, row.customer_id, allHistory)
      .then(setDetail)
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : "Không tải được chi tiết công nợ."));
  }, [token, row.customer_id, allHistory]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    if (eventTick <= 0) return;
    loadDetail();
  }, [eventTick, loadDetail]);

  useEffect(() => {
    if (!token || !receiptFor) return;
    setAccountsLoading(true);
    api.accounting
      .companyAccounts(token, true, "receive")
      .then((items) => setAccounts(items.filter((item) => item.currency === "VND")))
      .catch(() => setAccounts([]))
      .finally(() => setAccountsLoading(false));
  }, [token, receiptFor]);

  async function afterReceipt() {
    setReceiptFor(null);
    loadDetail();
    onChanged();
  }

  // ĐÓNG AN TOÀN: đang bung form thu tiền (receiptFor != null) thì Esc/scrim/✕ KHÔNG đóng —
  // tránh mất bản nháp đang gõ. Chỉ đóng khi không có form nào mở.
  const closeIfIdle = () => {
    if (receiptFor == null) onClose();
  };

  // Drawer tự nghe Esc (trước đây do DetailModal lo). Guard receiptFor để không nuốt draft.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && receiptFor == null) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [receiptFor, onClose]);

  return (
    <div className="rc-drawer__scrim" onClick={closeIfIdle}>
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={row.customer_name}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Công nợ phải thu</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{row.customer_name}</h2>
                {detail?.vuot_han_muc ? <span className="acct-voucher-status acct-voucher-status--waiting">Vượt hạn mức</span> : null}
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={closeIfIdle}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>{row.invoice_count} hóa đơn</span>
            {detail && (
              <>
                <span className="purchase__hero-dot">•</span>
                <span>Còn phải thu {money(detail.total_due)}</span>
                {detail.overdue_amount > 0 && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>Quá hạn {money(detail.overdue_amount)}</span>
                  </>
                )}
                {detail.credit_limit > 0 && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>Hạn mức {money(detail.credit_limit)}</span>
                  </>
                )}
              </>
            )}
          </div>
        </div>
        <div className="rc-drawer__body">
      {error && <div className="banner banner--error">{error}</div>}
      {!detail && !error && <p>Đang tải chi tiết...</p>}
      {detail && (
        <>
          {/* Thẻ số thay cho danh sách nhãn–giá trị: số ĐỨNG TRÊN, nhãn nhỏ ở dưới, để mắt bắt
              được con số trước. Số 0 lùi về dấu "—" mờ — ô này thường có 2–3 số 0, để nguyên thì
              số thật chìm nghỉm giữa đống số không. */}
          <div className="ar-stats">
            <div className="ar-stat">
              <b className="ar-stat__n">{money(detail.total_due)}</b>
              <span className="ar-stat__l">Tổng còn phải thu</span>
            </div>
            <div className={`ar-stat${detail.overdue_amount > 0 ? " ar-stat--danger" : ""}`}>
              <b className="ar-stat__n">{detail.overdue_amount > 0 ? money(detail.overdue_amount) : "—"}</b>
              <span className="ar-stat__l">Quá hạn</span>
            </div>
            <div className="ar-stat">
              <b className="ar-stat__n">{detail.received_in_period > 0 ? money(detail.received_in_period) : "—"}</b>
              <span className="ar-stat__l">Đã thu ({detail.period_months} tháng)</span>
            </div>
            <div className="ar-stat">
              <b className="ar-stat__n">{detail.credit_limit > 0 ? money(detail.credit_limit) : "—"}</b>
              <span className="ar-stat__l">Hạn mức</span>
            </div>
          </div>

          <section className="pay-block ar-invoices">
            <div className="pay-block__head"><h3>Hóa đơn còn phải thu</h3><strong>{money(detail.total_due)}</strong></div>
            <p className="pay-block__hint">Tiền cấn cọc và phiếu thu được tách riêng để dễ đối soát.</p>
            <div className="ar-tablewrap">
              <table className="pay-table ar-invoice-table">
                <thead>
                  <tr>
                    {/* "Đơn nguồn" gộp vào ô Hóa đơn (dòng nhỏ bên dưới): 8 cột không vừa bề
                        rộng ô, và cột bị đẩy ra ngoài chính là cột NÚT — người dùng phải kéo
                        ngang mới bấm được "Thu tiền". */}
                    <th>Hóa đơn</th>
                    <th>Ngày / hạn thu</th>
                    <th>Giá trị</th>
                    <th>Cấn cọc</th>
                    <th>Thu trực tiếp</th>
                    <th>Còn nợ</th>
                    <th>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.length === 0 && <tr><td colSpan={7}>Khách hàng này không còn hóa đơn phải thu.</td></tr>}
                  {detail.items.map((item) => (
                    <Fragment key={item.invoice_id}>
                      <tr>
                        <td>
                          <strong>{item.invoice_symbol ? `${item.invoice_symbol} · ` : ""}{item.invoice_number}</strong>
                          <small>
                            {fmtDate(item.invoice_date)} ·{" "}
                            <CodeLink code={item.order_code} onOpen={() => navigate("don-hang-ban", { openOrderId: item.order_id })} />
                          </small>
                        </td>
                        <td>
                          {item.due_date ? fmtDate(item.due_date) : "—"}
                          {item.chua_dat_han && <small>Chưa đặt hạn</small>}
                          {item.overdue_days > 0 && <small className="pay-cell--danger">Quá {item.overdue_days} ngày</small>}
                        </td>
                        <td className="pay-num">{money(item.amount)}</td>
                        <td className="pay-num">{money(item.deposit_offset_amount)}</td>
                        <td className="pay-num">{money(item.direct_received_amount)}</td>
                        <td className="pay-num"><strong>{money(item.remaining_amount)}</strong></td>
                        <td>
                          {canCreateReceipt && item.remaining_amount > 0 && (
                            <Button variant="ghost" onClick={() => setReceiptFor(receiptFor?.invoice_id === item.invoice_id ? null : item)}>
                              Thu tiền
                            </Button>
                          )}
                        </td>
                      </tr>
                      {receiptFor?.invoice_id === item.invoice_id && (
                        <tr className="ar-receipt-form-row">
                          <td colSpan={7}>
                            <InvoiceReceiptForm
                              item={item}
                              customerName={row.customer_name}
                              token={token}
                              accounts={accounts}
                              accountsLoading={accountsLoading}
                              onCancel={() => setReceiptFor(null)}
                              onSaved={afterReceipt}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="pay-block pay-block--ok">
            <div className="pay-block__head"><h3>Lịch sử đã thu / cấn cọc</h3><strong>{money(detail.received_in_period)}</strong></div>
            {/* Rỗng thì nói một câu, ĐỪNG bày 7 tiêu đề cột cho một dòng "chưa có gì" — bảng
                trống trông như đang hỏng chứ không như đang trống. */}
            {detail.paid.length === 0 ? (
              <p className="pay-block__hint">Chưa có khoản thu trong kỳ đang xem.</p>
            ) : (
            <div className="ar-tablewrap">
              <table className="pay-table ar-history-table">
                {/* "Người lập" đứng cạnh chính số phiếu của người đó — soi lịch sử thấy dòng lạ
                    thì câu hỏi đầu tiên luôn là "phiếu này ai ghi". Bên Công nợ phải trả đặt cùng
                    chỗ, để hai màn đọc như nhau. */}
                <thead><tr><th>Phiếu thu</th><th>Người lập</th><th>Áp dụng</th><th>Hóa đơn / đơn</th><th>Ngày thu</th><th>Hình thức</th><th>Số tiền</th></tr></thead>
                <tbody>
                  {detail.paid.map((receipt) => (
                    <tr key={`${receipt.receipt_id}-${receipt.applied_to}-${receipt.sales_invoice_id ?? receipt.order_id}`}>
                      <td>
                        <CodeLink code={receipt.code} onOpen={() => navigate("ke-toan-phieu-thu", { focusReceiptQuery: receipt.code })} />
                        {receipt.doc_no && <small>Số {receipt.doc_no}</small>}
                      </td>
                      <td title={receipt.created_by_name ?? undefined}>{receipt.created_by_name || "—"}</td>
                      <td>{receipt.applied_to === "deposit_offset" ? "Cấn cọc" : "Thu hóa đơn"}</td>
                      <td>
                        {receipt.sales_invoice_number ?? "—"}
                        {receipt.order_code && <small>Đơn {receipt.order_code}</small>}
                      </td>
                      <td>{fmtDate(receipt.receipt_date)}</td>
                      <td>{methodText(receipt.receipt_method)}</td>
                      <td className="pay-num"><strong>{money(receipt.amount)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
            {!detail.all_history && (
              /* Nút đứng ngay sau bảng nên phải TỰ tách khoảng — `pay-block` chỉ giãn cách giữa
                 các khối, không chen vào giữa con của một khối. */
              <div className="ar-more">
                <Button variant="ghost" onClick={() => setAllHistory(true)}>Xem lịch sử thu cũ hơn</Button>
              </div>
            )}
          </section>
        </>
      )}
        </div>
      </aside>
    </div>
  );
}
