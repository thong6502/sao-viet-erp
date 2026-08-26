// Hộp TẠO PHIẾU THU KHÁC — khoản thu phát sinh độc lập, không gắn phiếu chi/đơn bán
// (tách từ pages/PaymentReceiptsPage.tsx).
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là FORM TIỀN nên đóng
// AN TOÀN: scrim KHÔNG bắt click, KHÔNG Esc-to-close (tránh mất dữ liệu đang gõ). Toàn bộ
// `submit()` / `payload` phía trên giữ NGUYÊN — chỉ đổi vỏ.
import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentReceiptInput,
  type PaymentReceiptRow,
  type PaymentVoucherType,
} from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { isoToday, optional } from "../shared/helpers";

export function OtherReceiptDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (receipt: PaymentReceiptRow) => void;
}) {
  const { token } = useAuth();
  const [form, setForm] = useState<PaymentReceiptInput>({
    payer_name: "",
    payer_address: null,
    receipt_method: "cash",
    receipt_date: isoToday(),
    amount: 0,
    exchange_rate: 1,
    content: "",
    debit_account: null,
    credit_account: null,
    company_bank_account_id: null,
    bank_reference: null,
    note: null,
  });
  const [companyAccounts, setCompanyAccounts] = useState<CompanyBankAccountRow[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isBank = form.receipt_method === "bank_transfer";

  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    api.accounting
      .companyAccounts(token, true, "receive")
      .then((accounts) => setCompanyAccounts(accounts.filter((row) => row.currency === "VND")))
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token]);

  function set<K extends keyof PaymentReceiptInput>(key: K, value: PaymentReceiptInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || saving) return;
    if (!form.payer_name.trim()) {
      setError("Vui lòng nhập người nộp tiền.");
      return;
    }
    if (!form.receipt_date || !form.content.trim()) {
      setError("Vui lòng nhập ngày thu và nội dung thu.");
      return;
    }
    if (!Number.isFinite(form.amount) || form.amount <= 0) {
      setError("Số tiền thu phải lớn hơn 0.");
      return;
    }
    if (isBank && !form.company_bank_account_id) {
      setError("Vui lòng chọn tài khoản công ty nhận tiền.");
      return;
    }
    if (isBank && !optional(form.bank_reference)) {
      setError("Thu qua ngân hàng phải có mã giao dịch hoặc số báo có.");
      return;
    }
    const payload: PaymentReceiptInput = {
      ...form,
      payer_name: form.payer_name.trim(),
      payer_address: optional(form.payer_address),
      receipt_method: form.receipt_method,
      receipt_date: form.receipt_date,
      amount: Math.round(Number(form.amount)),
      exchange_rate: 1,
      content: form.content.trim(),
      debit_account: optional(form.debit_account),
      credit_account: optional(form.credit_account),
      company_bank_account_id: isBank ? form.company_bank_account_id ?? null : null,
      bank_reference: isBank ? optional(form.bank_reference) : null,
      note: optional(form.note),
    };
    setSaving(true);
    setError(null);
    try {
      const saved = await api.accounting.createOtherReceipt(token, payload);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lập được phiếu thu.");
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
        aria-label="Tạo phiếu thu"
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Phiếu thu</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">Tạo phiếu thu</h2>
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
            <span>Khoản thu phát sinh độc lập</span>
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
              <span>Người nộp tiền <b>*</b></span>
              <input
                className="input"
                value={form.payer_name}
                onChange={(event) => set("payer_name", event.target.value)}
                placeholder="Tên khách / nhân viên / đối tượng nộp"
              />
            </label>
            <label className="acct-field">
              <span>Ngày thu <b>*</b></span>
              <input
                className="input"
                type="date"
                value={form.receipt_date}
                onChange={(event) => set("receipt_date", event.target.value)}
              />
            </label>
          </div>
          <label className="acct-field">
            <span>Địa chỉ người nộp</span>
            <input
              className="input"
              value={form.payer_address ?? ""}
              onChange={(event) => set("payer_address", event.target.value)}
            />
          </label>
          <div className="acct-segment" aria-label="Hình thức thu">
            <button
              type="button"
              className={form.receipt_method === "cash" ? "is-active" : ""}
              onClick={() => {
                set("receipt_method", "cash" as PaymentVoucherType);
                set("company_bank_account_id", null);
                set("bank_reference", null);
              }}
            >
              Tiền mặt
            </button>
            <button
              type="button"
              className={isBank ? "is-active" : ""}
              onClick={() => {
                set("receipt_method", "bank_transfer" as PaymentVoucherType);
              }}
            >
              Chuyển khoản
            </button>
          </div>
          {isBank && (
            <div className="acct-form-grid acct-form-grid--2">
              <label className="acct-field">
                <span>Tài khoản nhận <b>*</b></span>
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
                      {account.bank_name} · {account.account_number}
                    </option>
                  ))}
                </select>
              </label>
              <label className="acct-field">
                <span>Mã giao dịch / số báo có <b>*</b></span>
                <input
                  className="input"
                  value={form.bank_reference ?? ""}
                  onChange={(event) => set("bank_reference", event.target.value)}
                />
              </label>
            </div>
          )}
          {/* Hai ô "Định khoản Nợ / Có" ĐÃ BỎ (chủ chốt 15/08/2026) — xem chú thích cùng ngày ở
              `PaymentVouchersPage`. Ô Số tiền vì thế đứng MỘT MÌNH: hạ lưới từ 3 cột xuống 1 để
              nó không bị kéo bằng 1/3 hàng rồi nằm trơ với hai khoảng trống bên cạnh.
              21/08/2026: thôi luôn việc ĐIỀN NGẦM 1111/1121 — chủ: "cái nợ và có ấy thì họ điền
              gì kệ họ". Phiếu in ra để trống dòng chấm cho kế toán tự ghi (`printTT200` đã in
              sẵn dấu chấm khi trống). Hai cột này không nuôi tính toán nào, chỉ để IN. */}
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
          <label className="acct-field">
            <span>Nội dung thu <b>*</b></span>
            <input
              className="input"
              value={form.content}
              onChange={(event) => set("content", event.target.value)}
              placeholder="VD: Thu tiền khách thanh toán, thu bồi hoàn..."
            />
          </label>
          <label className="acct-field">
            <span>Ghi chú</span>
            <textarea
              className="input acct-textarea"
              value={form.note ?? ""}
              onChange={(event) => set("note", event.target.value)}
            />
          </label>
        </div>
        <div className="purchase__drawer-footer">
          <Button variant="ghost" type="button" onClick={onClose}>
            Hủy
          </Button>
          <Button variant="primary" type="submit" loading={saving}>
            Lưu phiếu thu
          </Button>
        </div>
        </form>
      </aside>
    </div>
  );
}
