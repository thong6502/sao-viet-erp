// Hộp THANH TOÁN GỘP nhiều đợt giao của CÙNG một nhà cung cấp trong một lượt (chủ chốt
// 04/09/2026: "Cùng một nhà cung cấp thì có thể chọn nhiều đợt giao và thành toán một lượt
// luôn"). Mỗi đợt được chọn ra MỘT phiếu thanh toán riêng (server tự tính đúng số còn nợ của
// từng đợt), form này chỉ gom các ô CHUNG cho cả lượt: ngày chứng từ, hình thức chi, người/tài
// khoản nhận tiền, nội dung. Không có ô "Số tiền" — số tiền của từng phiếu là còn-nợ của chính
// đợt đó, không sửa tay được ở đây (sửa số bớt/thêm cho một đợt thì lập riêng phiếu đó).
//
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`), giống mọi hộp lập
// phiếu chi khác (chủ chốt 26/08/2026: "sao mỗi nơi một màu"). FORM TIỀN nên đóng AN TOÀN: scrim
// KHÔNG bắt click, KHÔNG Esc-to-close.
import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PayableItemRow,
  type PaymentVoucherType,
  type VoucherBatchInput,
} from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { money } from "../../../../utils/format";
import { tenKhoan } from "../shared/helpers";

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function optional(value: string | null | undefined): string | null {
  const cleaned = (value ?? "").trim();
  return cleaned || null;
}

export function BatchPaymentDialog({
  supplierName,
  items,
  onClose,
  onSaved,
}: {
  supplierName: string;
  /** Các đợt đã chọn — MỌI phần tử đều có `delivery_id` (checkbox chỉ hiện ở đợt đủ điều kiện). */
  items: PayableItemRow[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const [voucherType, setVoucherType] = useState<PaymentVoucherType>("cash");
  const [voucherDate, setVoucherDate] = useState(isoToday());
  const [content, setContent] = useState("");
  const [cashRecipientName, setCashRecipientName] = useState(supplierName);
  const [cashRecipientAddress, setCashRecipientAddress] = useState("");
  const [cashRecipientIdentity, setCashRecipientIdentity] = useState("");
  const [companyBankAccountId, setCompanyBankAccountId] = useState<number | null>(null);
  const [beneficiaryHolder, setBeneficiaryHolder] = useState(supplierName);
  const [beneficiaryNumber, setBeneficiaryNumber] = useState("");
  const [beneficiaryBank, setBeneficiaryBank] = useState("");
  const [beneficiaryBranch, setBeneficiaryBranch] = useState("");
  const [companyAccounts, setCompanyAccounts] = useState<CompanyBankAccountRow[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Chứng từ đính kèm (ảnh/PDF UNC, biên nhận…) — MỘT bộ file gắn vào TỪNG phiếu vừa lập, vì cả
  // lượt thường chỉ có một bằng chứng đã chi (một UNC ngân hàng trả gộp, một biên nhận tiền mặt)
  // nhưng chứng từ lại thuộc về từng phiếu, không có "phiếu gộp" nào để đính kèm chung.
  const [files, setFiles] = useState<File[]>([]);

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

  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    api.accounting
      .companyAccounts(token, true, "pay")
      .then(setCompanyAccounts)
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token]);

  const total = items.reduce((sum, it) => sum + it.con_no, 0);
  const isBank = voucherType === "bank_transfer";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || saving) return;
    if (!voucherDate) {
      setError("Vui lòng nhập ngày chứng từ.");
      return;
    }
    if (!isBank && !cashRecipientName.trim()) {
      setError("Vui lòng nhập người nhận tiền.");
      return;
    }
    if (isBank && !companyBankAccountId) {
      setError("Vui lòng chọn tài khoản trích nợ.");
      return;
    }
    if (
      isBank &&
      (!optional(beneficiaryHolder) || !optional(beneficiaryNumber) || !optional(beneficiaryBank))
    ) {
      setError("Vui lòng nhập đủ tên, số tài khoản và ngân hàng thụ hưởng.");
      return;
    }

    const payload: VoucherBatchInput = {
      items: items.map((it) => ({
        purchase_request_id: it.purchase_request_id,
        delivery_id: it.delivery_id as number,
      })),
      voucher_type: voucherType,
      voucher_date: voucherDate,
      currency: "VND",
      exchange_rate: 1,
      content: optional(content),
      company_bank_account_id: isBank ? companyBankAccountId : null,
      cash_recipient_name: isBank ? null : optional(cashRecipientName),
      cash_recipient_address: isBank ? null : optional(cashRecipientAddress),
      cash_recipient_identity: isBank ? null : optional(cashRecipientIdentity),
      beneficiary_account_holder: isBank ? optional(beneficiaryHolder) : null,
      beneficiary_account_number: isBank ? optional(beneficiaryNumber) : null,
      beneficiary_bank_name: isBank ? optional(beneficiaryBank) : null,
      beneficiary_bank_branch: isBank ? optional(beneficiaryBranch) : null,
      bank_fee_bearer: "payer",
    };
    setSaving(true);
    setError(null);
    try {
      const result = await api.accounting.createVouchersBatch(token, payload);
      if (files.length) {
        // Đính vào TỪNG phiếu vừa lập — vẫn gắn dù có phiếu tải lỗi, không dừng giữa chừng, để
        // không vì một phiếu lỗi mà những phiếu còn lại mất luôn chứng từ.
        const loi: string[] = [];
        for (const voucher of result.vouchers) {
          for (const file of files) {
            try {
              await api.accounting.uploadVoucherAttachment(token, voucher.id, file);
            } catch {
              loi.push(voucher.code);
            }
          }
        }
        if (loi.length) {
          setError(
            `Đã lập ${result.vouchers.length} phiếu nhưng file đính kèm tải lên thất bại ở: ` +
              `${[...new Set(loi)].join(", ")} — mở từng phiếu đó để đính kèm lại.`,
          );
          setSaving(false);
          return;
        }
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lập được phiếu thanh toán.");
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
        aria-label={`Thanh toán gộp — ${supplierName}`}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Thanh toán gộp</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{supplierName}</h2>
              </div>
            </div>
            <button type="button" className="purchase__hero-x" onClick={onClose} aria-label="Đóng">
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>{items.length} đợt giao</span>
            <span className="purchase__hero-dot">•</span>
            <span>Tổng {money(total)}</span>
          </div>
        </div>
        <form className="purchase__drawer-form" onSubmit={submit}>
          <div className="rc-drawer__body">
            {error && (
              <div className="banner banner--error" role="alert">
                {error}
              </div>
            )}
            <p className="pay-block__hint">
              Mỗi đợt ra MỘT phiếu thanh toán riêng, đúng bằng số còn nợ của đợt đó tại thời điểm
              lập — không sửa số tay được ở đây. Muốn trả khác số còn nợ (trả một phần…) thì lập
              riêng phiếu cho đợt đó ở màn Đơn mua hàng.
            </p>
            <table className="pay-table">
              <thead>
                <tr>
                  <th>Đơn hàng</th>
                  <th>Đợt</th>
                  <th className="pay-num">Còn nợ</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.delivery_id}>
                    <td>{it.code}</td>
                    <td>{tenKhoan(it)}</td>
                    <td className="pay-num">{money(it.con_no)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={2}>Tổng cộng</td>
                  <td className="pay-num">
                    <strong>{money(total)}</strong>
                  </td>
                </tr>
              </tfoot>
            </table>

            <div className="acct-form-grid acct-form-grid--2">
              <label className="acct-field">
                <span>
                  Ngày chứng từ <b>*</b>
                </span>
                <input
                  className="input"
                  type="date"
                  max={isoToday()}
                  value={voucherDate}
                  onChange={(event) => setVoucherDate(event.target.value)}
                />
              </label>
            </div>

            <div className="acct-segment" aria-label="Hình thức chi">
              <button
                type="button"
                className={!isBank ? "is-active" : ""}
                onClick={() => setVoucherType("cash")}
              >
                Tiền mặt
              </button>
              <button
                type="button"
                className={isBank ? "is-active" : ""}
                onClick={() => setVoucherType("bank_transfer")}
              >
                Chuyển khoản
              </button>
            </div>

            {isBank ? (
              <section className="acct-form-section">
                <h3>Thông tin chuyển khoản</h3>
                {!loadingAccounts && !companyAccounts.length && (
                  <div className="banner banner--warn">
                    Chưa có tài khoản công ty dùng để chi. Hãy khai báo trong mục Tài khoản ngân
                    hàng trước khi lập UNC.
                  </div>
                )}
                <div className="acct-form-grid acct-form-grid--3">
                  <label className="acct-field">
                    <span>
                      Tài khoản trích nợ <b>*</b>
                    </span>
                    <select
                      className="input"
                      value={companyBankAccountId ?? ""}
                      disabled={loadingAccounts}
                      onChange={(event) =>
                        setCompanyBankAccountId(
                          event.target.value ? Number(event.target.value) : null,
                        )
                      }
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
                      Tên chủ tài khoản <b>*</b>
                    </span>
                    <input
                      className="input"
                      value={beneficiaryHolder}
                      onChange={(event) => setBeneficiaryHolder(event.target.value)}
                    />
                  </label>
                  <label className="acct-field">
                    <span>
                      Số tài khoản thụ hưởng <b>*</b>
                    </span>
                    <input
                      className="input"
                      inputMode="numeric"
                      value={beneficiaryNumber}
                      onChange={(event) => setBeneficiaryNumber(event.target.value)}
                    />
                  </label>
                  <label className="acct-field">
                    <span>
                      Ngân hàng thụ hưởng <b>*</b>
                    </span>
                    <input
                      className="input"
                      value={beneficiaryBank}
                      onChange={(event) => setBeneficiaryBank(event.target.value)}
                    />
                  </label>
                  <label className="acct-field">
                    <span>Chi nhánh</span>
                    <input
                      className="input"
                      value={beneficiaryBranch}
                      onChange={(event) => setBeneficiaryBranch(event.target.value)}
                    />
                  </label>
                </div>
              </section>
            ) : (
              <section className="acct-form-section">
                <h3>Thông tin người nhận tiền</h3>
                <div className="acct-form-grid acct-form-grid--3">
                  <label className="acct-field">
                    <span>
                      Người nhận <b>*</b>
                    </span>
                    <input
                      className="input"
                      value={cashRecipientName}
                      onChange={(event) => setCashRecipientName(event.target.value)}
                    />
                  </label>
                  <label className="acct-field">
                    <span>Địa chỉ</span>
                    <input
                      className="input"
                      value={cashRecipientAddress}
                      onChange={(event) => setCashRecipientAddress(event.target.value)}
                    />
                  </label>
                  <label className="acct-field">
                    <span>CCCD/Giấy tờ</span>
                    <input
                      className="input"
                      value={cashRecipientIdentity}
                      onChange={(event) => setCashRecipientIdentity(event.target.value)}
                    />
                  </label>
                </div>
              </section>
            )}

            <label className="acct-field">
              <span>Nội dung chung (tuỳ chọn)</span>
              <input
                className="input"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="Để trống thì mỗi phiếu tự đặt nội dung theo mã đơn + số đợt"
              />
            </label>

            <section className="acct-form-section">
              <h3>Chứng từ đã chi (UNC, biên nhận…)</h3>
              <p className="pay-block__hint">
                Đính vào TỪNG phiếu trong lượt này — hữu ích khi cả lượt chỉ có một bằng chứng đã
                chi chung (một ảnh UNC ngân hàng trả gộp, một biên nhận tiền mặt).
              </p>
              <label className="acct-field">
                <span>Ảnh / PDF — tối đa 10 MB mỗi file</span>
                <input
                  className="input"
                  type="file"
                  multiple
                  accept="image/*,application/pdf"
                  onChange={(event) => {
                    addFiles(event.target.files);
                    event.target.value = "";
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
                          setFiles((current) => current.filter((_, i) => i !== index))
                        }
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <div className="purchase__drawer-footer">
            <Button type="button" variant="ghost" onClick={onClose}>
              Hủy
            </Button>
            <Button type="submit" variant="primary" loading={saving}>
              Lập {items.length} phiếu
            </Button>
          </div>
        </form>
      </aside>
    </div>
  );
}
