import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentReceiptInput,
  type PaymentVoucherType,
  type ReceivableCustomerRow,
  type ReceivableItemRow,
  type ReceivablesDetail,
  type ReceivablesSummary,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { fmtDate, money } from "../utils/format";
import "./accounting.css";
import "./payables.css";
import "./purchase.css";

type ListFilter = "all" | "overdue" | "chua_han" | "vuot_han_muc";

const LIST_FILTERS: { id: ListFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "overdue", label: "Quá hạn" },
  { id: "chua_han", label: "Chưa tới hạn" },
  { id: "vuot_han_muc", label: "Vượt hạn mức" },
];

const PAGE_SIZE = 20;

function kpi(value: number | undefined, known: boolean): string {
  return known && value != null ? money(value) : "—";
}

function methodText(value: string): string {
  return value === "bank_transfer" ? "Chuyển khoản" : "Tiền mặt";
}

function localToday(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export function AccountingReceivablesPage({
  navigate,
  eventTick = 0,
}: {
  navigate: NavigateFn;
  eventTick?: number;
}) {
  const { token } = useAuth();
  const [summary, setSummary] = useState<ReceivablesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ListFilter>("all");
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [sentQ, setSentQ] = useState("");
  const [open, setOpen] = useState<ReceivableCustomerRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.accounting
      .receivables(token, { q: sentQ, filter, page, size: PAGE_SIZE })
      .then((data) => {
        setSummary(data);
        if (data.page !== page) setPage(data.page);
      })
      .catch((cause) => {
        setSummary(null);
        setError(cause instanceof ApiError ? cause.message : "Không tải được công nợ phải thu.");
      })
      .finally(() => setLoading(false));
  }, [token, sentQ, filter, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  useEffect(() => {
    const timer = setTimeout(() => setSentQ(q), 350);
    return () => clearTimeout(timer);
  }, [q]);

  const known = !loading && !error && summary != null;
  const rows = summary?.items ?? [];

  const months = summary?.period_months ?? 3;

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">Công nợ phải thu</h1>
        <p className="md-page__sub">
          Theo dõi công nợ phát sinh từ hóa đơn bán đã ghi nhận và phiếu thu.
        </p>
      </header>

      {error && (
        <div className="banner banner--error" role="alert">
          {error} — các con số bên dưới đang để trống, không phải bằng 0.
        </div>
      )}

      <section className="pay-kpibar" aria-label="Tổng quan công nợ phải thu">
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--steel"><Icon name="calculator" size={14} /></span>
          <b className="pay-kpibar__val">{kpi(summary?.total_due, known)}</b>
          <span className="pay-kpibar__label">Tổng phải thu</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--danger"><Icon name="alert" size={14} /></span>
          <b className="pay-kpibar__val pay-kpibar__val--danger">{kpi(summary?.overdue_amount, known)}</b>
          <span className="pay-kpibar__label">Quá hạn</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--ok"><Icon name="fileCheck" size={14} /></span>
          <b className="pay-kpibar__val">{kpi(summary?.received_in_period, known)}</b>
          <span className="pay-kpibar__label">Đã thu ({months} tháng)</span>
        </div>
        <i className="pay-kpibar__sep" aria-hidden="true" />
        <div className="pay-kpibar__item">
          <span className="pay-kpibar__icon pay-kpibar__icon--warn"><Icon name="shield" size={14} /></span>
          <b className="pay-kpibar__val">{known ? summary?.vuot_han_muc_count ?? 0 : "—"}</b>
          <span className="pay-kpibar__label">Khách vượt hạn mức</span>
        </div>
      </section>

      <section className="acct-toolbar">
        <form className="md-page__search" onSubmit={(event) => event.preventDefault()}>
          <input
            className="input"
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="Tìm khách hàng..."
          />
        </form>
        <div className="pay-pills">
          {LIST_FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`pay-pill${filter === item.id ? " pay-pill--on" : ""}`}
              onClick={() => {
                setFilter(item.id);
                setPage(1);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card md-page__tablewrap pay-card ar-summary-table">
        <table className="md-page__table pay-table">
          <thead>
            <tr>
              <th>Khách hàng</th>
              <th>HĐ còn nợ</th>
              <th>Tổng phải thu</th>
              <th>Quá hạn</th>
              <th>Đã thu</th>
              <th>Hạn mức</th>
              <th>Xem</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7}>Đang tải...</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={7}>Chưa có khách hàng còn công nợ phải thu phù hợp.</td></tr>}
            {!loading && rows.map((row) => (
              <tr key={row.customer_id ?? `none-${row.customer_name}`}>
                <td>
                  <strong>{row.customer_name}</strong>
                  <small>Đã ghi hóa đơn {money(row.invoiced_amount)}</small>
                </td>
                <td>{row.invoice_count}</td>
                <td><strong>{money(row.total_due)}</strong></td>
                <td className={row.overdue_amount > 0 ? "pay-cell--danger" : ""}>{money(row.overdue_amount)}</td>
                <td>{money(row.received_amount)}</td>
                <td>
                  {row.credit_limit > 0 ? money(row.credit_limit) : "—"}
                  {row.vuot_han_muc && <small className="pay-cell--danger">Vượt {money(row.vuot_bao_nhieu)}</small>}
                </td>
                <td>
                  <Button variant="ghost" disabled={row.customer_id == null} onClick={() => setOpen(row)} aria-label={`Xem công nợ ${row.customer_name}`}>
                    <Icon name="eye" size={16} />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng {summary?.total ?? 0} khách hàng
            {(summary?.pages ?? 1) > 1 ? ` · Trang ${summary?.page}/${summary?.pages}` : ""}
          </span>
          {(summary?.pages ?? 1) > 1 && (
            <div className="md-page__pager-btns">
              <Button variant="ghost" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                Trước
              </Button>
              <Button
                variant="ghost"
                disabled={page >= (summary?.pages ?? 1) || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Sau
              </Button>
            </div>
          )}
        </div>
      </section>

      {open?.customer_id != null && (
        <ReceivablesDrawer
          row={open}
          token={token}
          navigate={navigate}
          eventTick={eventTick}
          onChanged={load}
          onClose={() => setOpen(null)}
        />
      )}
    </main>
  );
}

function ReceivablesDrawer({
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

  return (
    <DetailModal
      kicker="Công nợ phải thu"
      title={row.customer_name}
      subtitle={detail ? `Còn phải thu ${money(detail.total_due)}` : undefined}
      badge={detail?.vuot_han_muc ? <span className="acct-voucher-status acct-voucher-status--waiting">Vượt hạn mức</span> : undefined}
      onClose={onClose}
    >
      {error && <div className="banner banner--error">{error}</div>}
      {!detail && !error && <p>Đang tải chi tiết...</p>}
      {detail && (
        <>
          <dl className="purchase__facts">
            <div><dt>Tổng còn phải thu</dt><dd>{money(detail.total_due)}</dd></div>
            <div><dt>Quá hạn</dt><dd>{money(detail.overdue_amount)}</dd></div>
            <div><dt>Đã thu ({detail.period_months} tháng)</dt><dd>{money(detail.received_in_period)}</dd></div>
            <div><dt>Hạn mức</dt><dd>{detail.credit_limit > 0 ? money(detail.credit_limit) : "—"}</dd></div>
          </dl>

          <section className="pay-block ar-invoices">
            <div className="pay-block__head"><h3>Hóa đơn còn phải thu</h3><strong>{money(detail.total_due)}</strong></div>
            <p className="pay-block__hint">Tiền cấn cọc và phiếu thu được tách riêng để dễ đối soát.</p>
            <div className="ar-tablewrap">
              <table className="pay-table ar-invoice-table">
                <thead>
                  <tr>
                    <th>Hóa đơn</th>
                    <th>Đơn nguồn</th>
                    <th>Ngày / hạn thu</th>
                    <th>Giá trị</th>
                    <th>Cấn cọc</th>
                    <th>Thu trực tiếp</th>
                    <th>Còn nợ</th>
                    <th>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.length === 0 && <tr><td colSpan={8}>Khách hàng này không còn hóa đơn phải thu.</td></tr>}
                  {detail.items.map((item) => (
                    <Fragment key={item.invoice_id}>
                      <tr>
                        <td><strong>{item.invoice_symbol ? `${item.invoice_symbol} · ` : ""}{item.invoice_number}</strong><small>{fmtDate(item.invoice_date)}</small></td>
                        <td><CodeLink code={item.order_code} onOpen={() => navigate("don-hang-ban", { openOrderId: item.order_id })} /></td>
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
                          <td colSpan={8}>
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
            <div className="ar-tablewrap">
              <table className="pay-table ar-history-table">
                {/* "Người lập" đứng cạnh chính số phiếu của người đó — soi lịch sử thấy dòng lạ
                    thì câu hỏi đầu tiên luôn là "phiếu này ai ghi". Bên Công nợ phải trả đặt cùng
                    chỗ, để hai màn đọc như nhau. */}
                <thead><tr><th>Phiếu thu</th><th>Người lập</th><th>Áp dụng</th><th>Hóa đơn / đơn</th><th>Ngày thu</th><th>Hình thức</th><th>Số tiền</th></tr></thead>
                <tbody>
                  {detail.paid.length === 0 && <tr><td colSpan={7}>Chưa có khoản thu trong kỳ đang xem.</td></tr>}
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
            {!detail.all_history && <Button variant="ghost" onClick={() => setAllHistory(true)}>Xem lịch sử thu cũ hơn</Button>}
          </section>
        </>
      )}
    </DetailModal>
  );
}

function InvoiceReceiptForm({
  item,
  customerName,
  token,
  accounts,
  accountsLoading,
  onCancel,
  onSaved,
}: {
  item: ReceivableItemRow;
  customerName: string;
  token: string | null;
  accounts: CompanyBankAccountRow[];
  accountsLoading: boolean;
  onCancel: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState<PaymentReceiptInput>({
    payer_name: customerName,
    payer_address: null,
    receipt_method: "cash",
    receipt_date: localToday(),
    amount: item.remaining_amount,
    exchange_rate: 1,
    content: `Thu hóa đơn ${item.invoice_number} của đơn ${item.order_code}`,
    company_bank_account_id: null,
    bank_reference: null,
    note: null,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isBank = form.receipt_method === "bank_transfer";

  function set<K extends keyof PaymentReceiptInput>(key: K, value: PaymentReceiptInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!token || saving) return;
    if (!form.payer_name.trim() || !form.receipt_date || !form.content.trim()) {
      setError("Vui lòng nhập người nộp, ngày thu và nội dung thu.");
      return;
    }
    if (!Number.isFinite(form.amount) || form.amount <= 0 || form.amount > item.remaining_amount) {
      setError(`Số tiền thu phải từ 1 đến ${money(item.remaining_amount)}.`);
      return;
    }
    if (isBank && !form.company_bank_account_id) {
      setError("Vui lòng chọn tài khoản công ty nhận tiền.");
      return;
    }
    if (isBank && !form.bank_reference?.trim()) {
      setError("Thu chuyển khoản phải có mã giao dịch hoặc số báo có.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.accounting.createSalesInvoiceReceipt(token, item.invoice_id, {
        ...form,
        payer_name: form.payer_name.trim(),
        amount: Math.round(form.amount),
        content: form.content.trim(),
        company_bank_account_id: isBank ? form.company_bank_account_id : null,
        bank_reference: isBank ? form.bank_reference?.trim() || null : null,
      });
      await onSaved();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không lập được phiếu thu hóa đơn.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="ar-receipt-form" onSubmit={submit}>
      <div className="ar-receipt-form__head">
        <div><strong>Thu hóa đơn {item.invoice_number}</strong><small>Còn phải thu {money(item.remaining_amount)}</small></div>
        <div className="acct-segment" aria-label="Hình thức thu">
          <button type="button" className={!isBank ? "is-active" : ""} onClick={() => set("receipt_method", "cash" as PaymentVoucherType)}>Tiền mặt</button>
          <button type="button" className={isBank ? "is-active" : ""} onClick={() => set("receipt_method", "bank_transfer" as PaymentVoucherType)}>Chuyển khoản</button>
        </div>
      </div>
      {error && <div className="banner banner--error" role="alert">{error}</div>}
      <div className="ar-receipt-form__grid">
        <label className="acct-field"><span>Người nộp <b>*</b></span><input className="input" value={form.payer_name} onChange={(event) => set("payer_name", event.target.value)} /></label>
        <label className="acct-field"><span>Ngày thu <b>*</b></span><input className="input" type="date" min={item.invoice_date} max={localToday()} value={form.receipt_date} onChange={(event) => set("receipt_date", event.target.value)} /></label>
        <label className="acct-field"><span>Số tiền <b>*</b></span><input className="input acct-money-input" type="number" min="1" max={item.remaining_amount} step="1" value={form.amount} onChange={(event) => set("amount", Number(event.target.value))} /></label>
        {isBank && (
          <label className="acct-field"><span>Tài khoản nhận <b>*</b></span>
            <select className="input" value={form.company_bank_account_id ?? ""} disabled={accountsLoading} onChange={(event) => set("company_bank_account_id", event.target.value ? Number(event.target.value) : null)}>
              <option value="">Chọn tài khoản công ty</option>
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.bank_name} · {account.account_number}</option>)}
            </select>
          </label>
        )}
      </div>
      <label className="acct-field"><span>Nội dung thu <b>*</b></span><input className="input" value={form.content} onChange={(event) => set("content", event.target.value)} /></label>
      {isBank && <label className="acct-field"><span>Mã giao dịch <b>*</b></span><input className="input" value={form.bank_reference ?? ""} onChange={(event) => set("bank_reference", event.target.value)} /></label>}
      <div className="ar-receipt-form__actions">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={saving}>Hủy</Button>
        <Button type="submit" variant="primary" loading={saving}>Lập phiếu thu</Button>
      </div>
    </form>
  );
}
