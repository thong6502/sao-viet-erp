// Drawer CHI TIẾT công nợ một khách hàng (tách từ pages/AccountingReceivablesPage.tsx).
import { useCallback, useEffect, useState } from "react";
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
  const [view, setView] = useState<"open" | "history">("open");
  // Cùng công thức với Công nợ phải trả (PayablesDrawer): còn được nợ = hạn mức trừ đang nợ,
  // không giới hạn dưới 0.
  const conDuocNo = detail ? Math.max(0, detail.credit_limit - detail.total_due) : 0;
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
        <div className="purchase__hero-banner acct-cnu-hero">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Công nợ phải thu</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{row.customer_name}</h2>
                {detail?.vuot_han_muc ? (
                  <span className="pay-badge pay-badge--danger">
                    <i className="pay-badge__dot" />
                    Vượt hạn mức {money(detail.vuot_bao_nhieu)}
                  </span>
                ) : null}
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
          {/* Chính sách "cho nợ" của khách — cùng khuôn `.pay-credit` với Công nợ phải trả, đọc
              từ Customer.credit_limit/payment_term_days (đã có sẵn, sửa ở màn Khách hàng, quyền
              `set_credit_terms`) — không phải trường mới. */}
          <dl className="pay-credit">
            <div>
              <dt>Hạn mức công nợ</dt>
              <dd>
                {detail.credit_limit > 0 ? (
                  money(detail.credit_limit)
                ) : (
                  <span className="pay-cell--zero">Chưa đặt</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Đang nợ</dt>
              <dd className={detail.vuot_han_muc ? "pay-cell--danger" : ""}>
                {money(detail.total_due)}
              </dd>
            </div>
            <div>
              <dt>Còn được nợ</dt>
              <dd>
                {detail.credit_limit > 0 ? (
                  money(conDuocNo)
                ) : (
                  <span className="pay-cell--zero">Không giới hạn</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Số ngày cho nợ</dt>
              <dd>
                {detail.payment_term_days == null ? (
                  <span className="pay-cell--zero">Chưa đặt</span>
                ) : detail.payment_term_days === 0 ? (
                  "Trả ngay"
                ) : (
                  `${detail.payment_term_days} ngày`
                )}
              </dd>
            </div>
          </dl>

          {/* Hai tab tách "còn phải thu" (việc phải làm) khỏi "lịch sử" (tra cứu) — cùng dáng
              `.rc-drawer__tab` với Công nợ phải trả, để hai màn đọc như nhau. */}
          <div className="rc-drawer__tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={view === "open"}
              className={`rc-drawer__tab ${view === "open" ? "is-active" : ""}`}
              onClick={() => setView("open")}
            >
              Hóa đơn còn phải thu
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "history"}
              className={`rc-drawer__tab ${view === "history" ? "is-active" : ""}`}
              onClick={() => setView("history")}
            >
              Lịch sử thanh toán
            </button>
          </div>

          {view === "open" && (
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
                    {/* "Hạn thu" thôi — ngày phát hành hoá đơn đã nằm ở dòng nhỏ dưới mã hoá đơn
                        rồi. Nhãn "Ngày / hạn thu" cũ vừa lặp vừa dài, gãy làm hai dòng kéo cả dải
                        tiêu đề cao gấp đôi. */}
                    <th>Hạn thu</th>
                    {/* `pay-num` cho CẢ th (UI_DESIGN §6): thiếu nó thì tiêu đề canh trái trong khi
                        số canh phải — bốn cột tiền lệch hẳn khỏi nhãn của chính chúng. Bên Công nợ
                        phải trả vốn đã khai đúng, màn này sót. */}
                    <th className="pay-num">Giá trị</th>
                    <th className="pay-num">Cấn cọc</th>
                    <th className="pay-num">Đã thu</th>
                    <th className="pay-num">Còn nợ</th>
                    <th className="ar-invoice-table__act">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.length === 0 && <tr><td colSpan={7}>Khách hàng này không còn hóa đơn phải thu.</td></tr>}
                  {detail.items.map((item) => (
                    <tr
                      key={item.invoice_id}
                      className={receiptFor?.invoice_id === item.invoice_id ? "ar-row--active" : undefined}
                    >
                      <td>
                        <strong>{item.invoice_symbol ? `${item.invoice_symbol} · ` : ""}{item.invoice_number}</strong>
                        <small>
                          {fmtDate(item.invoice_date)} ·{" "}
                          <CodeLink code={item.order_code} onOpen={() => navigate("don-hang-ban", { openOrderId: item.order_id })} />
                        </small>
                      </td>
                      <td>
                        {item.chua_dat_han ? (
                          <span className="pay-cell--zero">Chưa đặt hạn</span>
                        ) : (
                          fmtDate(item.due_date)
                        )}
                        {item.overdue_days > 0 && <small className="pay-cell--danger">Quá {item.overdue_days} ngày</small>}
                      </td>
                      <td className="pay-num">{money(item.amount)}</td>
                      {/* Cấn cọc / Đã thu phần lớn là 0. In "0 đ" cho mỗi dòng là hai cột đầy số
                          không mang tin, át mất cột thật sự phải đọc (Còn nợ). Gạch mờ = "chưa có
                          gì ở đây", mắt lướt qua được. */}
                      <td className="pay-num">
                        {item.deposit_offset_amount > 0 ? (
                          money(item.deposit_offset_amount)
                        ) : (
                          <span className="pay-cell--zero">—</span>
                        )}
                      </td>
                      <td className="pay-num">
                        {item.direct_received_amount > 0 ? (
                          money(item.direct_received_amount)
                        ) : (
                          <span className="pay-cell--zero">—</span>
                        )}
                      </td>
                      <td className="pay-num"><strong>{money(item.remaining_amount)}</strong></td>
                      <td className="ar-invoice-table__act">
                        {canCreateReceipt && item.remaining_amount > 0 && (
                          <Button variant="ghost" onClick={() => setReceiptFor(receiptFor?.invoice_id === item.invoice_id ? null : item)}>
                            {receiptFor?.invoice_id === item.invoice_id ? "Đang thu ▲" : "Thu tiền"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          )}

          {receiptFor && (
            <InvoiceReceiptForm
              item={receiptFor}
              customerName={row.customer_name}
              token={token}
              accounts={accounts}
              accountsLoading={accountsLoading}
              onCancel={() => setReceiptFor(null)}
              onSaved={afterReceipt}
            />
          )}

          {view === "history" && (
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
          )}
        </>
      )}
        </div>
      </aside>
    </div>
  );
}
