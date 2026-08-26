// Hộp LẬP PHIẾU CHI ĐỘC LẬP — khoản chi không gắn đơn mua hàng
// (tách từ pages/PaymentVouchersPage.tsx).
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là FORM TIỀN nên đóng
// AN TOÀN: scrim KHÔNG bắt click, KHÔNG Esc-to-close (tránh mất dữ liệu đang gõ). Toàn bộ
// `submit()` / `payload` phía trên giữ NGUYÊN — chỉ đổi vỏ.
import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentVoucherInput,
  type PaymentVoucherRow,
  type PaymentVoucherType,
} from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { isoToday, optional } from "../shared/helpers";

export function StandaloneVoucherDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (voucher: PaymentVoucherRow) => void;
}) {
  const { token } = useAuth();
  const [form, setForm] = useState<PaymentVoucherInput>({
    source_type: "other",
    voucher_type: "cash",
    payment_stage: "other",
    voucher_date: isoToday(),
    amount: 0,
    currency: "VND",
    exchange_rate: 1,
    content: "",
    cash_recipient_name: "",
    cash_recipient_address: null,
    cash_recipient_identity: null,
    company_bank_account_id: null,
    beneficiary_account_holder: null,
    beneficiary_account_number: null,
    beneficiary_bank_name: null,
    beneficiary_bank_branch: null,
    bank_fee_bearer: "payer",
    debit_account: null,
    credit_account: null,
    note: null,
  });
  const [companyAccounts, setCompanyAccounts] = useState<CompanyBankAccountRow[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isBank = form.voucher_type === "bank_transfer";

  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    api.accounting
      .companyAccounts(token, true, "pay")
      .then((accounts) => setCompanyAccounts(accounts))
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token]);

  function set<K extends keyof PaymentVoucherInput>(key: K, value: PaymentVoucherInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || saving) return;
    if (!form.voucher_date || !form.content.trim()) {
      setError("Vui lòng nhập ngày chứng từ và nội dung chi.");
      return;
    }
    if (!form.cash_recipient_name?.trim()) {
      setError("Vui lòng nhập người nhận / đối tượng nhận tiền.");
      return;
    }
    if (!Number.isFinite(form.amount) || form.amount <= 0) {
      setError("Số tiền chi phải lớn hơn 0.");
      return;
    }
    if (isBank && !form.company_bank_account_id) {
      setError("UNC phải chọn tài khoản trích nợ.");
      return;
    }
    if (
      isBank &&
      (!optional(form.beneficiary_account_holder) ||
        !optional(form.beneficiary_account_number) ||
        !optional(form.beneficiary_bank_name))
    ) {
      setError("UNC phải có tên, số tài khoản và ngân hàng thụ hưởng.");
      return;
    }

    const payload: PaymentVoucherInput = {
      ...form,
      purchase_request_id: null,
      source_type: "other",
      voucher_type: form.voucher_type,
      payment_stage: "other",
      delivery_id: null,
      planned_payment_date: null,
      amount: Math.round(Number(form.amount)),
      currency: form.currency.trim().toUpperCase(),
      exchange_rate: Number(form.exchange_rate || 1),
      content: form.content.trim(),
      cash_recipient_name: form.cash_recipient_name.trim(),
      cash_recipient_address: optional(form.cash_recipient_address),
      cash_recipient_identity: optional(form.cash_recipient_identity),
      company_bank_account_id: isBank ? form.company_bank_account_id ?? null : null,
      supplier_bank_account_id: null,
      beneficiary_account_holder: isBank ? optional(form.beneficiary_account_holder) : null,
      beneficiary_account_number: isBank ? optional(form.beneficiary_account_number) : null,
      beneficiary_bank_name: isBank ? optional(form.beneficiary_bank_name) : null,
      beneficiary_bank_branch: isBank ? optional(form.beneficiary_bank_branch) : null,
      bank_fee_bearer: isBank ? form.bank_fee_bearer ?? "payer" : null,
      debit_account: optional(form.debit_account),
      credit_account: optional(form.credit_account),
      invoice_number: optional(form.invoice_number),
      invoice_date: optional(form.invoice_date),
      contract_number: optional(form.contract_number),
      note: optional(form.note),
    };
    setSaving(true);
    setError(null);
    try {
      const saved = await api.accounting.createVoucher(token, payload);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lập được phiếu chi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rc-drawer__scrim" role="presentation">
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Tạo phiếu chi"
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Phiếu chi</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">Tạo phiếu chi</h2>
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
            <span>Khoản chi không gắn đơn mua hàng</span>
            <span className="purchase__hero-dot">•</span>
            <span>{isBank ? "Chuyển khoản" : "Tiền mặt"}</span>
          </div>
        </div>
        <form className="purchase__drawer-form" onSubmit={submit}>
        <div className="rc-drawer__body">
          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}
          <div className="acct-form-grid acct-form-grid--2">
            <label className="acct-field">
              <span>Ngày chứng từ <b>*</b></span>
              <input
                className="input"
                type="date"
                max={isoToday()}
                value={form.voucher_date}
                onChange={(event) => set("voucher_date", event.target.value)}
              />
            </label>
          </div>
          <div className="acct-segment" aria-label="Hình thức chi">
            <button
              type="button"
              className={form.voucher_type === "cash" ? "is-active" : ""}
              onClick={() => {
                set("voucher_type", "cash" as PaymentVoucherType);
                set("company_bank_account_id", null);
              }}
            >
              Tiền mặt
            </button>
            <button
              type="button"
              className={isBank ? "is-active" : ""}
              onClick={() => {
                set("voucher_type", "bank_transfer" as PaymentVoucherType);
              }}
            >
              Chuyển khoản
            </button>
          </div>
          <div className="acct-form-grid acct-form-grid--2">
            <label className="acct-field">
              <span>Người nhận / đối tượng <b>*</b></span>
              <input
                className="input"
                value={form.cash_recipient_name ?? ""}
                onChange={(event) => set("cash_recipient_name", event.target.value)}
                placeholder="Tên người, khách hàng hoặc đơn vị nhận tiền"
              />
            </label>
            <label className="acct-field">
              <span>Số tiền (VND) <b>*</b></span>
              <input
                className="input acct-money-input"
                type="number"
                min="1"
                step="1"
                value={form.amount === 0 ? "" : form.amount}
                onChange={(event) => set("amount", Number(event.target.value))}
              />
            </label>
          </div>
          <label className="acct-field">
            <span>Địa chỉ / thông tin liên hệ</span>
            <input
              className="input"
              value={form.cash_recipient_address ?? ""}
              onChange={(event) => set("cash_recipient_address", event.target.value)}
            />
          </label>
          {isBank && (
            <section className="acct-form-section">
              <h3>Thông tin chuyển khoản</h3>
              <div className="acct-form-grid acct-form-grid--2">
                <label className="acct-field">
                  <span>Tài khoản trích nợ <b>*</b></span>
                  <select
                    className="input"
                    value={form.company_bank_account_id ?? ""}
                    disabled={loadingAccounts}
                    onChange={(event) =>
                      set(
                        "company_bank_account_id",
                        event.target.value ? Number(event.target.value) : null,
                      )
                    }
                  >
                    <option value="">Chọn tài khoản công ty</option>
                    {companyAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.bank_name} · {account.account_number} · {account.currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="acct-field">
                  <span>Tên thụ hưởng <b>*</b></span>
                  <input
                    className="input"
                    value={form.beneficiary_account_holder ?? ""}
                    onChange={(event) => set("beneficiary_account_holder", event.target.value)}
                  />
                </label>
                <label className="acct-field">
                  <span>Số tài khoản <b>*</b></span>
                  <input
                    className="input"
                    value={form.beneficiary_account_number ?? ""}
                    onChange={(event) => set("beneficiary_account_number", event.target.value)}
                  />
                </label>
                <label className="acct-field">
                  <span>Ngân hàng <b>*</b></span>
                  <input
                    className="input"
                    value={form.beneficiary_bank_name ?? ""}
                    onChange={(event) => set("beneficiary_bank_name", event.target.value)}
                  />
                </label>
              </div>
            </section>
          )}
          <label className="acct-field">
            <span>Nội dung chi <b>*</b></span>
            <input
              className="input"
              value={form.content}
              onChange={(event) => set("content", event.target.value)}
              placeholder="VD: Thanh toán tiền điện tháng 8"
            />
          </label>
          {/* Hai ô "Định khoản Nợ / Có" ĐÃ BỎ (chủ chốt 15/08/2026) — cùng lý do đã bỏ ở hộp
              thoại phiếu chi theo đơn hôm 12/08: chúng bắt kế toán gõ số hiệu tài khoản cho từng
              phiếu mà hệ thống KHÔNG hạch toán gì từ đó, chỉ in ra.
              Đợt 12/08 tôi chỉ dọn hộp thoại lập-theo-đơn và bỏ sót đúng hai form LẬP RỜI này.
              21/08/2026: thôi luôn việc ĐIỀN NGẦM 1111/1121 — chủ: "cái nợ và có ấy thì họ điền
              gì kệ họ". Phiếu in ra để trống dòng chấm cho kế toán tự ghi (`printTT200` in sẵn
              dấu chấm khi trống), đúng ý ban đầu của hai cột: "định khoản nhập tay". */}
          <section className="acct-form-section">
            <h3>Chứng từ tham chiếu</h3>
            <div className="acct-form-grid acct-form-grid--2">
              <label className="acct-field">
                <span>Số hóa đơn</span>
                <input
                  className="input"
                  value={form.invoice_number ?? ""}
                  onChange={(event) => set("invoice_number", event.target.value)}
                />
              </label>
              <label className="acct-field">
                <span>Ngày hóa đơn</span>
                <input
                  className="input"
                  type="date"
                  max={isoToday()}
                  value={form.invoice_date ?? ""}
                  onChange={(event) => set("invoice_date", event.target.value || null)}
                />
              </label>
            </div>
          </section>
        </div>
        <div className="purchase__drawer-footer">
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            Lưu phiếu
          </Button>
        </div>
        </form>
      </aside>
    </div>
  );
}
