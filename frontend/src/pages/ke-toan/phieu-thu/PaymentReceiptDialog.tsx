// Hộp lập/sửa PHIẾU THU tiền thừa của một phiếu chi (tách từ pages/PaymentReceiptDialog.tsx).
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là FORM TIỀN nên đóng
// AN TOÀN: scrim KHÔNG bắt click, KHÔNG Esc-to-close (tránh mất dữ liệu đang gõ). `remainingVnd`,
// `submit()` và khối `acct-summary-strip` giữ NGUYÊN — chỉ đổi vỏ.
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentReceiptInput,
  type PaymentVoucherType,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { Button } from "../../../components/Button";
import { money } from "../../../utils/format";
import { initialForm, optional } from "./shared/helpers";
import type { PaymentReceiptDialogProps } from "./shared/types";

export function PaymentReceiptDialog({
  voucher,
  receipt = null,
  onClose,
  onSaved,
}: PaymentReceiptDialogProps) {
  const { token } = useAuth();
  // Phần còn được thu: cộng lại chính phiếu này khi đang sửa (nó đang chiếm chỗ).
  const remainingVnd = useMemo(
    () =>
      voucher.amount_vnd -
      voucher.receipt_received_amount -
      voucher.receipt_pending_amount +
      (receipt?.status === "waiting_receipt" ? receipt.amount_vnd : 0),
    [voucher, receipt],
  );
  const [form, setForm] = useState<PaymentReceiptInput>(() =>
    initialForm(voucher, receipt),
  );
  const [companyAccounts, setCompanyAccounts] = useState<
    CompanyBankAccountRow[]
  >([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const amountVnd = useMemo(
    () =>
      Math.round(
        Number(form.amount || 0) *
          Number(form.exchange_rate || voucher.exchange_rate || 1),
      ),
    [form.amount, form.exchange_rate, voucher.exchange_rate],
  );
  const isBank = form.receipt_method === "bank_transfer";

  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    api.accounting
      .companyAccounts(token, true, "receive")
      .then((accounts) => {
        const matching = accounts.filter(
          (row) => row.currency === voucher.currency,
        );
        setCompanyAccounts(matching);
      })
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token, voucher.currency]);

  function set<K extends keyof PaymentReceiptInput>(
    key: K,
    value: PaymentReceiptInput[K],
  ) {
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
    if (amountVnd > remainingVnd) {
      setError(
        `Số tiền thu không được vượt quá ${remainingVnd.toLocaleString("vi-VN")} đ.`,
      );
      return;
    }
    if (isBank && !form.company_bank_account_id) {
      setError("Vui lòng chọn tài khoản công ty nhận tiền.");
      return;
    }

    const payload: PaymentReceiptInput = {
      ...form,
      payer_name: form.payer_name.trim(),
      payer_address: optional(form.payer_address),
      debit_account: optional(form.debit_account),
      credit_account: optional(form.credit_account),
      amount: Math.round(Number(form.amount)),
      exchange_rate: Number(form.exchange_rate || voucher.exchange_rate || 1),
      content: form.content.trim(),
      company_bank_account_id: isBank
        ? (form.company_bank_account_id ?? null)
        : null,
      note: optional(form.note),
    };
    setSaving(true);
    setError(null);
    try {
      const saved = receipt
        ? await api.accounting.updateReceipt(token, receipt.id, payload)
        : await api.accounting.createReceipt(token, voucher.id, payload);
      onSaved(saved);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không lưu được phiếu thu.",
      );
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
        aria-labelledby="payment-receipt-title"
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">
                {receipt ? "Sửa phiếu thu" : "Lập phiếu thu"}
              </span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code" id="payment-receipt-title">
                  {voucher.code} · {voucher.supplier_name}
                </h2>
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
        </div>
        <form className="purchase__drawer-form" onSubmit={submit}>
        <div className="rc-drawer__body">
          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="acct-summary-strip">
            <div>
              <span>Đã chi</span>
              <strong>{money(voucher.amount_vnd)}</strong>
            </div>
            <div>
              <span>Đã thu</span>
              <strong>{money(voucher.receipt_received_amount)}</strong>
            </div>
            <div>
              <span>Chờ thu</span>
              <strong>{money(voucher.receipt_pending_amount)}</strong>
            </div>
            <div>
              <span>Còn được thu</span>
              <strong>{money(remainingVnd)}</strong>
            </div>
          </div>

          <div className="acct-form-grid acct-form-grid--2">
            <label className="acct-field">
              <span>
                Người nộp tiền <b>*</b>
              </span>
              <input
                className="input"
                value={form.payer_name}
                onChange={(e) => set("payer_name", e.target.value)}
                placeholder="NCC hoặc nhân viên phụ trách mua"
              />
            </label>
            <label className="acct-field">
              <span>Địa chỉ người nộp</span>
              <input
                className="input"
                maxLength={500}
                value={form.payer_address ?? ""}
                onChange={(e) => set("payer_address", e.target.value)}
              />
            </label>
          </div>

          {/* Khối "Định khoản" ĐÃ BỎ (chủ chốt 12/08/2026): hai ô Nợ / Có bắt kế toán gõ số
              hiệu tài khoản cho từng phiếu, mà hệ thống không hạch toán gì từ chúng — chỉ in ra.
              Cột `debit_account` và `credit_account` GIỮ NGUYÊN trong DB để phiếu cũ in lại vẫn
              đúng; chỉ gỡ ô nhập. */}
          <div className="acct-segment" aria-label="Hình thức thu">
            <button
              type="button"
              className={form.receipt_method === "cash" ? "is-active" : ""}
              onClick={() => set("receipt_method", "cash" as PaymentVoucherType)}
            >
              Nhập quỹ tiền mặt
            </button>
            <button
              type="button"
              className={
                form.receipt_method === "bank_transfer" ? "is-active" : ""
              }
              onClick={() =>
                set("receipt_method", "bank_transfer" as PaymentVoucherType)
              }
            >
              Về TK ngân hàng
            </button>
          </div>

          {isBank && (
            <label className="acct-field">
              <span>
                Tài khoản công ty nhận tiền <b>*</b>
              </span>
              <select
                className="input"
                value={form.company_bank_account_id ?? ""}
                onChange={(e) =>
                  set(
                    "company_bank_account_id",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                disabled={loadingAccounts}
              >
                <option value="">Chọn tài khoản công ty</option>
                {companyAccounts.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.bank_name} · {row.account_number} · {row.currency}
                  </option>
                ))}
              </select>
              {!loadingAccounts && companyAccounts.length === 0 && (
                <small>
                  Chưa có tài khoản công ty loại tiền {voucher.currency}. Khai
                  báo trong mục Tài khoản ngân hàng trước.
                </small>
              )}
            </label>
          )}

          <div className="acct-form-grid acct-form-grid--3">
            <label className="acct-field">
              <span>
                Ngày thu <b>*</b>
              </span>
              <input
                className="input"
                type="date"
                value={form.receipt_date}
                onChange={(e) => set("receipt_date", e.target.value)}
              />
            </label>
            <label className="acct-field">
              <span>
                Số tiền nguyên tệ ({voucher.currency}) <b>*</b>
              </span>
              <input
                className="input acct-money-input"
                type="number"
                min="1"
                step="1"
                value={form.amount === 0 ? "" : form.amount}
                onChange={(e) => set("amount", Number(e.target.value))}
              />
            </label>
            {voucher.currency !== "VND" ? (
              <label className="acct-field">
                <span>
                  Tỷ giá VND <b>*</b>
                </span>
                <input
                  className="input acct-money-input"
                  type="number"
                  min="0.000001"
                  step="0.000001"
                  value={form.exchange_rate ?? voucher.exchange_rate}
                  onChange={(e) => set("exchange_rate", Number(e.target.value))}
                />
                <small>Quy đổi: {amountVnd.toLocaleString("vi-VN")} đ</small>
              </label>
            ) : (
              <div className="acct-field">
                <span>Quy đổi</span>
                <strong style={{ alignSelf: "flex-start" }}>
                  {money(amountVnd)}
                </strong>
              </div>
            )}
          </div>

          <label className="acct-field">
            <span>
              Nội dung thu <b>*</b>
            </span>
            <input
              className="input"
              value={form.content}
              onChange={(e) => set("content", e.target.value)}
            />
          </label>

          <label className="acct-field">
            <span>Ghi chú</span>
            <textarea
              className="input acct-textarea"
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
            />
          </label>
        </div>

        <div className="purchase__drawer-footer">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={saving}
          >
            Hủy
          </Button>
          <Button type="submit" variant="accent" loading={saving}>
            {receipt ? "Lưu thay đổi" : "Lập phiếu thu"}
          </Button>
        </div>
        </form>
      </aside>
    </div>
  );
}
