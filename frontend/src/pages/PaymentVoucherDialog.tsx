import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentStage,
  type PaymentVoucherBaseInput,
  type PaymentVoucherInput,
  type PaymentVoucherRow,
  type PaymentVoucherType,
  type PurchaseRequestRow,
  type SupplierBankAccountRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { UNC_ENABLED } from "../constants/features";

const STAGE_LABELS: Record<PaymentStage, string> = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
};

interface PaymentVoucherDialogProps {
  purchase: PurchaseRequestRow;
  combined?: boolean;
  voucher?: PaymentVoucherRow | null;
  onClose: () => void;
  onSaved: (voucher: PaymentVoucherRow) => void;
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function optional(value?: string | null): string | null {
  const cleaned = (value ?? "").trim();
  return cleaned || null;
}

function initialForm(
  purchase: PurchaseRequestRow,
  voucher?: PaymentVoucherRow | null,
): PaymentVoucherBaseInput {
  if (voucher) {
    return {
      voucher_type: voucher.voucher_type,
      payment_stage: voucher.payment_stage,
      voucher_date: voucher.voucher_date,
      planned_payment_date: voucher.planned_payment_date,
      amount: voucher.amount,
      currency: voucher.currency,
      exchange_rate: voucher.exchange_rate,
      content: voucher.content,
      invoice_number: voucher.invoice_number,
      invoice_date: voucher.invoice_date,
      contract_number: voucher.contract_number,
      company_bank_account_id: voucher.company_bank_account_id,
      supplier_bank_account_id: voucher.supplier_bank_account_id,
      cash_recipient_name: voucher.cash_recipient_name,
      cash_recipient_address: voucher.cash_recipient_address,
      cash_recipient_identity: voucher.cash_recipient_identity,
      bank_fee_bearer: voucher.bank_fee_bearer ?? "payer",
      debit_account: voucher.debit_account,
      credit_account: voucher.credit_account,
      note: voucher.note,
    };
  }
  return {
    voucher_type: "cash",
    // Số tiền mặc định = phần còn được lập, tức tất toán PMH → đợt "final";
    // effect đồng bộ đợt sẽ tự hạ xuống "advance" khi người dùng giảm số tiền.
    payment_stage: "final",
    voucher_date: isoToday(),
    planned_payment_date: null,
    amount: purchase.available_amount,
    currency: "VND",
    exchange_rate: 1,
    content: `Thanh toán ${purchase.code}${purchase.purpose ? ` - ${purchase.purpose}` : ""}`,
    invoice_number: null,
    invoice_date: null,
    contract_number: null,
    company_bank_account_id: null,
    supplier_bank_account_id: null,
    cash_recipient_name: purchase.supplier_name ?? "",
    cash_recipient_address: null,
    cash_recipient_identity: null,
    bank_fee_bearer: "payer",
    debit_account: null,
    credit_account: null,
    note: null,
  };
}

export function PaymentVoucherDialog({
  purchase,
  combined = false,
  voucher = null,
  onClose,
  onSaved,
}: PaymentVoucherDialogProps) {
  const { token } = useAuth();
  const [form, setForm] = useState<PaymentVoucherBaseInput>(() =>
    initialForm(purchase, voucher),
  );
  const [companyAccounts, setCompanyAccounts] = useState<
    CompanyBankAccountRow[]
  >([]);
  const [supplierAccounts, setSupplierAccounts] = useState<
    SupplierBankAccountRow[]
  >([]);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Chứng từ đã mua (hóa đơn/biên nhận) chọn lúc lập — upload sau khi create.
  const [files, setFiles] = useState<File[]>([]);

  const maxAmountVnd = useMemo(
    () =>
      purchase.available_amount +
      (voucher?.status === "waiting_payment" ? voucher.amount_vnd : 0),
    [purchase.available_amount, voucher],
  );
  const amountVnd = useMemo(
    () =>
      Math.round(Number(form.amount || 0) * Number(form.exchange_rate || 0)),
    [form.amount, form.exchange_rate],
  );

  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    Promise.all([
      api.accounting.companyAccounts(token, true),
      purchase.supplier_id
        ? api.accounting.supplierAccounts(token, purchase.supplier_id, true)
        : Promise.resolve([]),
    ])
      .then(([company, supplier]) => {
        setCompanyAccounts(company);
        setSupplierAccounts(supplier);
        setForm((current) => {
          const companyAccountId =
            current.company_bank_account_id ??
            company.find((row) => row.is_default)?.id ??
            company[0]?.id ??
            null;
          const companyAccount = company.find(
            (row) => row.id === companyAccountId,
          );
          const currency =
            current.voucher_type === "bank_transfer"
              ? (companyAccount?.currency ?? current.currency)
              : current.currency;
          return {
            ...current,
            company_bank_account_id: companyAccountId,
            supplier_bank_account_id:
              current.supplier_bank_account_id ??
              supplier.find((row) => row.is_default)?.id ??
              supplier[0]?.id ??
              null,
            currency,
            exchange_rate: currency === "VND" ? 1 : current.exchange_rate,
          };
        });
      })
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token, purchase.supplier_id]);

  // "Thanh toán cuối" = đợt chi tất toán phần còn lại của PMH: so bằng số
  // quy đổi VND với "còn được lập" (không so tổng PMH — sai từ đợt 2 trở đi,
  // và không so nguyên tệ — sai khi thanh toán ngoại tệ).
  useEffect(() => {
    setForm((current) => {
      if (amountVnd === maxAmountVnd && current.payment_stage !== "final") {
        return { ...current, payment_stage: "final" };
      }
      if (amountVnd !== maxAmountVnd && current.payment_stage === "final") {
        return { ...current, payment_stage: "advance" };
      }
      return current;
    });
  }, [amountVnd, maxAmountVnd]);

  function set<K extends keyof PaymentVoucherBaseInput>(
    key: K,
    value: PaymentVoucherBaseInput[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const accepted: File[] = [];
    for (const file of Array.from(list)) {
      if (!(file.type.startsWith("image/") || file.type === "application/pdf")) {
        setError(`"${file.name}": chỉ nhận ảnh hoặc PDF.`);
        continue;
      }
      if (file.size > 10 * 1024 * 1024) {
        setError(`"${file.name}" vượt quá 10 MB.`);
        continue;
      }
      accepted.push(file);
    }
    if (accepted.length) {
      setFiles((current) => [...current, ...accepted]);
    }
  }

  function selectType(type: PaymentVoucherType) {
    if (voucher) return;
    setForm((current) => ({
      ...current,
      voucher_type: type,
      currency:
        type === "bank_transfer"
          ? (companyAccounts.find(
              (row) => row.id === current.company_bank_account_id,
            )?.currency ?? current.currency)
          : current.currency,
      exchange_rate:
        type === "bank_transfer" &&
        companyAccounts.find(
          (row) => row.id === current.company_bank_account_id,
        )?.currency === "VND"
          ? 1
          : current.exchange_rate,
      cash_recipient_name:
        type === "cash"
          ? current.cash_recipient_name || purchase.supplier_name || ""
          : current.cash_recipient_name,
    }));
  }

  function selectCompanyAccount(value: string) {
    const accountId = value ? Number(value) : null;
    const account = companyAccounts.find((row) => row.id === accountId);
    setForm((current) => ({
      ...current,
      company_bank_account_id: accountId,
      currency: account?.currency ?? current.currency,
      exchange_rate:
        account?.currency === "VND"
          ? 1
          : account && account.currency !== current.currency
            ? 1
            : current.exchange_rate,
    }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || saving) return;
    if (!form.voucher_date || !form.content.trim()) {
      setError("Vui lòng nhập ngày chứng từ và nội dung chi.");
      return;
    }
    if (!Number.isFinite(form.amount) || form.amount <= 0) {
      setError("Số tiền thanh toán phải lớn hơn 0.");
      return;
    }
    if (!Number.isFinite(form.exchange_rate) || form.exchange_rate <= 0) {
      setError("Tỷ giá phải lớn hơn 0.");
      return;
    }
    if (
      form.currency.trim().toUpperCase() === "VND" &&
      form.exchange_rate !== 1
    ) {
      setError("Tỷ giá của VND phải bằng 1.");
      return;
    }
    if (amountVnd > maxAmountVnd) {
      setError(
        `Số tiền quy đổi không được vượt quá ${maxAmountVnd.toLocaleString("vi-VN")} đ.`,
      );
      return;
    }
    if (form.voucher_type === "cash" && !form.cash_recipient_name?.trim()) {
      setError("Phiếu chi phải có người nhận tiền.");
      return;
    }
    if (
      form.voucher_type === "bank_transfer" &&
      (!form.company_bank_account_id || !form.supplier_bank_account_id)
    ) {
      setError("UNC phải chọn tài khoản trích nợ và tài khoản thụ hưởng.");
      return;
    }
    if (form.voucher_type === "bank_transfer") {
      const companyCurrency = companyAccounts.find(
        (row) => row.id === form.company_bank_account_id,
      )?.currency;
      const supplierCurrency = supplierAccounts.find(
        (row) => row.id === form.supplier_bank_account_id,
      )?.currency;
      if (
        companyCurrency &&
        supplierCurrency &&
        companyCurrency !== supplierCurrency
      ) {
        setError(
          "Tài khoản trích nợ và tài khoản thụ hưởng phải cùng loại tiền.",
        );
        return;
      }
    }

    const payload: PaymentVoucherBaseInput = {
      ...form,
      amount: Math.round(Number(form.amount)),
      currency: form.currency.trim().toUpperCase(),
      exchange_rate: Number(form.exchange_rate),
      content: form.content.trim(),
      planned_payment_date: optional(form.planned_payment_date),
      invoice_number: optional(form.invoice_number),
      invoice_date: optional(form.invoice_date),
      contract_number: optional(form.contract_number),
      cash_recipient_name: optional(form.cash_recipient_name),
      cash_recipient_address: optional(form.cash_recipient_address),
      cash_recipient_identity: optional(form.cash_recipient_identity),
      debit_account: optional(form.debit_account),
      credit_account: optional(form.credit_account),
      note: optional(form.note),
      company_bank_account_id:
        form.voucher_type === "bank_transfer"
          ? (form.company_bank_account_id ?? null)
          : null,
      supplier_bank_account_id:
        form.voucher_type === "bank_transfer"
          ? (form.supplier_bank_account_id ?? null)
          : null,
      bank_fee_bearer:
        form.voucher_type === "bank_transfer"
          ? (form.bank_fee_bearer ?? "payer")
          : null,
    };
    setSaving(true);
    setError(null);
    try {
      let saved: PaymentVoucherRow;
      if (combined) {
        saved = await api.accounting.approveAndCreateVoucher(
          token,
          purchase.id,
          payload,
        );
      } else if (voucher) {
        const input: PaymentVoucherInput = {
          ...payload,
          purchase_request_id: purchase.id,
        };
        saved = await api.accounting.updateVoucher(token, voucher.id, input);
      } else {
        const input: PaymentVoucherInput = {
          ...payload,
          purchase_request_id: purchase.id,
        };
        saved = await api.accounting.createVoucher(token, input);
      }
      if (!voucher && files.length) {
        try {
          for (const file of files) {
            await api.accounting.uploadVoucherAttachment(token, saved.id, file);
          }
        } catch {
          setError(
            `Chứng từ ${saved.code} đã lập nhưng có file đính kèm tải lên thất bại — mở chứng từ để đính kèm lại.`,
          );
          setSaving(false);
          return;
        }
      }
      onSaved(saved);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không lưu được Phiếu chi/UNC.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="acct-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="payment-voucher-title"
    >
      <form className="acct-modal__box acct-modal__box--wide" onSubmit={submit}>
        <header className="acct-modal__head">
          <div>
            <p className="eyebrow">
              {combined
                ? "Duyệt PMH và lập chứng từ"
                : voucher
                  ? "Sửa chứng từ"
                  : "Lập chứng từ thanh toán"}
            </p>
            <h2 id="payment-voucher-title">
              {purchase.code} · {purchase.supplier_name}
            </h2>
          </div>
          <button
            type="button"
            className="acct-modal__x"
            onClick={onClose}
            aria-label="Đóng"
          >
            ×
          </button>
        </header>

        <div className="acct-modal__body">
          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="acct-summary-strip">
            <div>
              <span>Tổng PMH</span>
              <strong>
                {purchase.total_estimate.toLocaleString("vi-VN")} đ
              </strong>
            </div>
            <div>
              <span>Đã chi</span>
              <strong>{purchase.paid_amount.toLocaleString("vi-VN")} đ</strong>
            </div>
            <div>
              <span>Đang chờ chi</span>
              <strong>
                {purchase.pending_amount.toLocaleString("vi-VN")} đ
              </strong>
            </div>
            <div>
              <span>Còn được lập</span>
              <strong>{maxAmountVnd.toLocaleString("vi-VN")} đ</strong>
            </div>
          </div>

          {/* Tạm ẩn UNC: lập mới thì không cho chọn loại (mặc định tiền mặt). Vẫn
              hiện khi MỞ SỬA một UNC cũ để người dùng biết đây là chứng từ gì —
              lúc đó hai nút vốn đã khóa. */}
          {(UNC_ENABLED || form.voucher_type === "bank_transfer") && (
            <div className="acct-segment" aria-label="Loại chứng từ">
              <button
                type="button"
                className={form.voucher_type === "cash" ? "is-active" : ""}
                onClick={() => selectType("cash")}
                disabled={!!voucher}
              >
                Phiếu chi
              </button>
              <button
                type="button"
                className={
                  form.voucher_type === "bank_transfer" ? "is-active" : ""
                }
                onClick={() => selectType("bank_transfer")}
                disabled={!!voucher}
              >
                Ủy nhiệm chi
              </button>
            </div>
          )}

          <div className="acct-form-grid acct-form-grid--3">
            <label className="acct-field">
              <span>
                Đợt thanh toán <b>*</b>
              </span>
              <select
                className="input"
                value={form.payment_stage}
                onChange={(e) =>
                  set("payment_stage", e.target.value as PaymentStage)
                }
              >
                {Object.entries(STAGE_LABELS).map(([value, label]) => (
                  <option
                    key={value}
                    value={value}
                    disabled={
                      (amountVnd === maxAmountVnd && value !== "final") ||
                      (amountVnd !== maxAmountVnd && value === "final")
                    }
                  >
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="acct-field">
              <span>
                Ngày chứng từ <b>*</b>
              </span>
              <input
                className="input"
                type="date"
                value={form.voucher_date}
                onChange={(e) => set("voucher_date", e.target.value)}
              />
            </label>
            <label className="acct-field">
              <span>Ngày dự kiến chi</span>
              <input
                className="input"
                type="date"
                value={form.planned_payment_date ?? ""}
                onChange={(e) =>
                  set("planned_payment_date", e.target.value || null)
                }
              />
            </label>
            <label className="acct-field">
              <span>
                Số tiền nguyên tệ <b>*</b>
              </span>
              <input
                className="input acct-money-input"
                type="number"
                min="1"
                step="1"
                value={form.amount}
                onChange={(e) => set("amount", Number(e.target.value))}
              />
            </label>
            <label className="acct-field">
              <span>
                Loại tiền <b>*</b>
              </span>
              <input
                className="input"
                maxLength={3}
                readOnly={form.voucher_type === "bank_transfer"}
                value={form.currency}
                onChange={(e) => {
                  const currency = e.target.value.toUpperCase();
                  setForm((current) => ({
                    ...current,
                    currency,
                    exchange_rate:
                      currency === "VND" ? 1 : current.exchange_rate,
                  }));
                }}
              />
            </label>
            <label className="acct-field">
              <span>
                Tỷ giá VND <b>*</b>
              </span>
              <input
                className="input acct-money-input"
                type="number"
                min="0.000001"
                step="0.000001"
                disabled={form.currency === "VND"}
                value={form.exchange_rate}
                onChange={(e) => set("exchange_rate", Number(e.target.value))}
              />
              <small>Quy đổi: {amountVnd.toLocaleString("vi-VN")} đ</small>
            </label>
          </div>

          <label className="acct-field">
            <span>
              Nội dung chi <b>*</b>
            </span>
            <input
              className="input"
              value={form.content}
              onChange={(e) => set("content", e.target.value)}
            />
          </label>

          {form.voucher_type === "cash" ? (
            <section className="acct-form-section">
              <h3>Thông tin người nhận tiền</h3>
              <div className="acct-form-grid acct-form-grid--3">
                <label className="acct-field">
                  <span>
                    Người nhận <b>*</b>
                  </span>
                  <input
                    className="input"
                    value={form.cash_recipient_name ?? ""}
                    onChange={(e) => set("cash_recipient_name", e.target.value)}
                  />
                </label>
                <label className="acct-field">
                  <span>Địa chỉ</span>
                  <input
                    className="input"
                    value={form.cash_recipient_address ?? ""}
                    onChange={(e) =>
                      set("cash_recipient_address", e.target.value)
                    }
                  />
                </label>
                <label className="acct-field">
                  <span>CCCD/Giấy tờ</span>
                  <input
                    className="input"
                    value={form.cash_recipient_identity ?? ""}
                    onChange={(e) =>
                      set("cash_recipient_identity", e.target.value)
                    }
                  />
                </label>
              </div>
            </section>
          ) : (
            <section className="acct-form-section">
              <h3>Thông tin chuyển khoản</h3>
              {!loadingAccounts &&
                (!companyAccounts.length || !supplierAccounts.length) && (
                  <div className="banner banner--warn">
                    Chưa đủ tài khoản ngân hàng. Hãy khai báo trong mục Tài
                    khoản ngân hàng trước khi lập UNC.
                  </div>
                )}
              <div className="acct-form-grid acct-form-grid--3">
                <label className="acct-field">
                  <span>
                    Tài khoản trích nợ <b>*</b>
                  </span>
                  <select
                    className="input"
                    value={form.company_bank_account_id ?? ""}
                    onChange={(e) => selectCompanyAccount(e.target.value)}
                    disabled={loadingAccounts}
                  >
                    <option value="">Chọn tài khoản công ty</option>
                    {companyAccounts.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.bank_name} · {row.account_number} · {row.currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="acct-field">
                  <span>
                    Tài khoản thụ hưởng <b>*</b>
                  </span>
                  <select
                    className="input"
                    value={form.supplier_bank_account_id ?? ""}
                    onChange={(e) =>
                      set(
                        "supplier_bank_account_id",
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                    disabled={loadingAccounts}
                  >
                    <option value="">Chọn tài khoản nhà cung cấp</option>
                    {supplierAccounts.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.bank_name} · {row.account_number} · {row.currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="acct-field">
                  <span>Bên chịu phí</span>
                  <select
                    className="input"
                    value={form.bank_fee_bearer ?? "payer"}
                    onChange={(e) =>
                      set(
                        "bank_fee_bearer",
                        e.target.value as "payer" | "beneficiary" | "shared",
                      )
                    }
                  >
                    <option value="payer">Công ty trả</option>
                    <option value="beneficiary">Người thụ hưởng trả</option>
                    <option value="shared">Chia sẻ phí</option>
                  </select>
                </label>
              </div>
            </section>
          )}

          {!voucher && (
            <section className="acct-form-section">
              <h3>Chứng từ đã mua (hóa đơn, biên nhận, UNC…)</h3>
              <label className="acct-field">
                <span>Ảnh / PDF — tối đa 10 MB mỗi file</span>
                <input
                  className="input"
                  type="file"
                  multiple
                  accept="image/*,application/pdf"
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
              </label>
              {files.length > 0 && (
                <ul className="acct-filelist">
                  {files.map((file, index) => (
                    <li key={`${file.name}-${index}`}>
                      📎 {file.name}
                      <button
                        type="button"
                        className="acct-modal__x acct-filelist__x"
                        aria-label={`Bỏ ${file.name}`}
                        onClick={() =>
                          setFiles((current) =>
                            current.filter((_, i) => i !== index),
                          )
                        }
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <section className="acct-form-section">
            <h3>Định khoản (in trên phiếu)</h3>
            <div className="acct-form-grid acct-form-grid--3">
              <label className="acct-field">
                <span>Nợ</span>
                <input
                  className="input"
                  maxLength={64}
                  placeholder="VD: 242, 1331"
                  value={form.debit_account ?? ""}
                  onChange={(e) => set("debit_account", e.target.value)}
                />
              </label>
              <label className="acct-field">
                <span>Có</span>
                <input
                  className="input"
                  maxLength={64}
                  placeholder={
                    form.voucher_type === "cash" ? "VD: 1111" : "VD: 1121"
                  }
                  value={form.credit_account ?? ""}
                  onChange={(e) => set("credit_account", e.target.value)}
                />
              </label>
            </div>
          </section>

          <section className="acct-form-section">
            <h3>Chứng từ tham chiếu</h3>
            <div className="acct-form-grid acct-form-grid--3">
              <label className="acct-field">
                <span>Số hóa đơn</span>
                <input
                  className="input"
                  value={form.invoice_number ?? ""}
                  onChange={(e) => set("invoice_number", e.target.value)}
                />
              </label>
              <label className="acct-field">
                <span>Ngày hóa đơn</span>
                <input
                  className="input"
                  type="date"
                  value={form.invoice_date ?? ""}
                  onChange={(e) => set("invoice_date", e.target.value || null)}
                />
              </label>
              <label className="acct-field">
                <span>Số hợp đồng</span>
                <input
                  className="input"
                  value={form.contract_number ?? ""}
                  onChange={(e) => set("contract_number", e.target.value)}
                />
              </label>
            </div>
            <label className="acct-field">
              <span>Ghi chú</span>
              <textarea
                className="input acct-textarea"
                value={form.note ?? ""}
                onChange={(e) => set("note", e.target.value)}
              />
            </label>
          </section>
        </div>

        <footer className="acct-modal__foot">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={saving}
          >
            Hủy
          </Button>
          <Button type="submit" variant="accent" loading={saving}>
            {combined
              ? "Duyệt & lập chứng từ"
              : voucher
                ? "Lưu thay đổi"
                : "Lập chứng từ"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
