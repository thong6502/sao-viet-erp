// Form THU TIỀN theo hóa đơn, hiện ngay trong drawer (tách từ pages/AccountingReceivablesPage.tsx).
// Khối này gắn logic thu tiền — giữ nguyên nguyên khối, không tách nhỏ.
import { useState } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentReceiptInput,
  type PaymentVoucherType,
  type ReceivableItemRow,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { money } from "../../../../utils/format";
import { localToday } from "../shared/helpers";

export function InvoiceReceiptForm({
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
