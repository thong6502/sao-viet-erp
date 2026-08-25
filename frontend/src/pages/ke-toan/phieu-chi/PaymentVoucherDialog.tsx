// Hộp LẬP PHIẾU CHI / UNC theo đơn mua hàng (tách từ pages/PaymentVoucherDialog.tsx).
// ⚠️ TIỀN THẬT. Giữ ở đây nguyên văn: `maxAmountVnd` (trần đặt cọc vs công nợ theo đợt),
// `amountVnd`, và toàn bộ `submit()` — mọi câu chặn trần/tỷ giá/đợt giao. Sáu khối JSX con chỉ
// là chỗ HIỂN THỊ, nhận state qua props; không khối nào tự tính lại tiền.
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type CompanyBankAccountRow,
  type PaymentVoucherBaseInput,
  type PaymentVoucherInput,
  type PaymentVoucherRow,
  type PaymentVoucherType,
} from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { Button } from "../../../components/Button";
import { VoucherAmountFields } from "./components/VoucherAmountFields";
import { VoucherAttachSection } from "./components/VoucherAttachSection";
import { VoucherRecipientSection } from "./components/VoucherRecipientSection";
import { VoucherRefSection } from "./components/VoucherRefSection";
import { VoucherSegments } from "./components/VoucherSegments";
import { VoucherSummaryStrip } from "./components/VoucherSummaryStrip";
import { cocGoiY, conNoDot, dotGoiY, initialForm, optional } from "./shared/helpers";
import type { LoaiPhieu, PaymentVoucherDialogProps } from "./shared/types";

export function PaymentVoucherDialog({
  purchase,
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
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Chứng từ đã mua (hóa đơn/biên nhận) chọn lúc lập — upload sau khi create.
  const [files, setFiles] = useState<File[]>([]);

  const loai: LoaiPhieu =
    form.payment_stage === "advance" ? "dat_coc" : "thanh_toan";
  const coDotGiao = purchase.deliveries.length > 0;

  // TRẦN khác nhau theo loại phiếu (Đ1/§5.4) — đừng gộp làm một:
  //   · ĐẶT CỌC   → `tran_dat_coc` (giá trị ĐƠN ĐẶT − đã chi ròng): cọc là chi khi hàng CHƯA về,
  //                 nên không thể trói vào số hàng đã giao (= 0 lúc đó).
  //   · THANH TOÁN → CÒN NỢ CỦA CHÍNH ĐỢT ĐANG CHỌN.
  //
  // ⚠️ Trần thanh toán KHÔNG được lấy công nợ cả đơn (lỗi 07/08/2026): kế toán chọn "Đợt 2" rồi
  // gõ số của cả đơn thì phần thừa chảy vào rổ cọc chung và lặng lẽ trả hộ Đợt 1 — món nợ của đợt 1
  // biến mất khỏi màn Công nợ mà không ai bấm gì. Trả cho nhiều đợt thì lập nhiều phiếu.
  //
  // Sửa một phiếu đã chi: số cũ của chính nó đang nằm trong `net_paid` nên đã bị trừ khỏi trần —
  // cộng lại, nếu không mở phiếu ra sửa mỗi dòng nội dung cũng bị báo "vượt trần". Chỉ cộng khi
  // phiếu cũ đóng góp vào ĐÚNG cái trần đang tính (server làm y hệt).
  const maxAmountVnd = useMemo(() => {
    const tran =
      loai === "dat_coc"
        ? purchase.tran_dat_coc
        : conNoDot(purchase, form.delivery_id ?? null);
    const cu = voucher?.status === "paid" ? voucher : null;
    const cuLaCoc = cu?.payment_stage === "advance";
    const cungDich =
      cu != null &&
      (loai === "dat_coc"
        ? cuLaCoc
        : !cuLaCoc && (cu.delivery_id ?? null) === (form.delivery_id ?? null));
    return tran + (cungDich ? cu!.amount_vnd : 0);
  }, [loai, purchase, form.delivery_id, voucher]);
  const amountVnd = useMemo(
    () =>
      Math.round(Number(form.amount || 0) * Number(form.exchange_rate || 0)),
    [form.amount, form.exchange_rate],
  );
  const dotDangChon = useMemo(
    () => purchase.deliveries.find((d) => d.id === form.delivery_id) ?? null,
    [purchase.deliveries, form.delivery_id],
  );

  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    api.accounting.companyAccounts(token, true, "pay")
      .then((company) => {
        setCompanyAccounts(company);
        setForm((current) => {
          const companyAccountId = current.company_bank_account_id ?? null;
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
            currency,
            exchange_rate: currency === "VND" ? 1 : current.exchange_rate,
          };
        });
      })
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token]);

  function set<K extends keyof PaymentVoucherBaseInput>(
    key: K,
    value: PaymentVoucherBaseInput[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  /** Đổi LOẠI phiếu là đổi cả ba thứ đi kèm: đợt giao, trần, và số tiền điền sẵn.
   *
   * Giữ nguyên số tiền cũ khi đổi loại là bẫy: người chọn "Đặt cọc" với số bằng công nợ rồi bấm
   * lưu, backend nhận đúng nhưng con số không phải thứ họ định. Điền lại theo trần MỚI. */
  function chonLoai(next: LoaiPhieu) {
    if (voucher) return; // sửa phiếu cũ: loại đã chốt, đổi loại là đổi bản chất chứng từ
    setForm((current) => {
      if (next === "dat_coc") {
        return {
          ...current,
          payment_stage: "advance",
          delivery_id: null,
          amount: cocGoiY(purchase),
        };
      }
      return {
        ...current,
        payment_stage: "final",
        delivery_id: coDotGiao ? dotGoiY(purchase) : null,
        amount: conNoDot(purchase, coDotGiao ? dotGoiY(purchase) : null),
      };
    });
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
    if (maxAmountVnd <= 0) {
      setError(
        loai === "dat_coc"
          ? "Đơn này đã chi đủ giá trị đặt hàng — không còn chỗ để đặt cọc thêm."
          : "Đơn này chưa phát sinh công nợ (hàng chưa về hoặc đã trả hết). Ghi đợt giao trước, hoặc lập phiếu Đặt cọc.",
      );
      return;
    }
    if (amountVnd > maxAmountVnd) {
      setError(
        `Số tiền quy đổi không được vượt quá ${maxAmountVnd.toLocaleString("vi-VN")} đ ` +
          `(${loai === "dat_coc" ? "trần đặt cọc theo giá trị đơn đặt" : "công nợ hiện tại"}).`,
      );
      return;
    }
    // Đơn CÓ đợt giao thì phiếu thanh toán bắt buộc chỉ rõ trả cho đợt nào — không có nó thì công
    // nợ biết TỔNG đã trả nhưng không biết đợt nào đã xong, và cột Quá hạn (tính theo hạn của từng
    // đợt) không quy được về đâu. Server cũng chặn; đây chỉ chặn sớm cho đỡ một vòng gọi.
    if (loai === "thanh_toan" && coDotGiao && !form.delivery_id) {
      setError("Phiếu thanh toán phải chọn đợt giao.");
      return;
    }
    if (form.voucher_type === "cash" && !form.cash_recipient_name?.trim()) {
      setError("Phiếu chi phải có người nhận tiền.");
      return;
    }
    if (
      form.voucher_type === "bank_transfer" &&
      (!form.company_bank_account_id ||
        !form.beneficiary_account_holder?.trim() ||
        !form.beneficiary_account_number?.trim() ||
        !form.beneficiary_bank_name?.trim())
    ) {
      setError("UNC phải có tài khoản công ty, tên chủ tài khoản, số tài khoản và ngân hàng thụ hưởng.");
      return;
    }

    const payload: PaymentVoucherBaseInput = {
      ...form,
      amount: Math.round(Number(form.amount)),
      currency: form.currency.trim().toUpperCase(),
      exchange_rate: Number(form.exchange_rate),
      content: form.content.trim(),
      // Cọc KHÔNG gắn đợt (server từ chối nếu gắn); đơn không có đợt nào cũng phải gửi null.
      delivery_id:
        loai === "dat_coc" || !coDotGiao ? null : (form.delivery_id ?? null),
      // DORMANT — luôn gửi null. Hạn trả nay là `due_date` của đợt giao.
      planned_payment_date: null,
      invoice_number: optional(form.invoice_number),
      invoice_date: optional(form.invoice_date),
      contract_number: optional(form.contract_number),
      cash_recipient_name: optional(form.cash_recipient_name),
      cash_recipient_address: optional(form.cash_recipient_address),
      cash_recipient_identity: optional(form.cash_recipient_identity),
      beneficiary_account_holder: optional(form.beneficiary_account_holder),
      beneficiary_account_number: optional(form.beneficiary_account_number),
      beneficiary_bank_name: optional(form.beneficiary_bank_name),
      beneficiary_bank_branch: optional(form.beneficiary_bank_branch),
      debit_account: optional(form.debit_account),
      credit_account: optional(form.credit_account),
      note: optional(form.note),
      company_bank_account_id:
        form.voucher_type === "bank_transfer"
          ? (form.company_bank_account_id ?? null)
          : null,
      // Tài khoản NCC không còn là danh mục quản lý: UNC lưu ảnh chụp thông tin đã nhập.
      supplier_bank_account_id: null,
      bank_fee_bearer:
        form.voucher_type === "bank_transfer"
          ? (form.bank_fee_bearer ?? "payer")
          : null,
    };
    setSaving(true);
    setError(null);
    try {
      // Đường "duyệt + lập phiếu chi trong một cú bấm" đã BỎ HẲN (chủ 04/08/2026): giám đốc duyệt
      // ở màn Đơn mua hàng trước, kế toán mới lập phiếu chi. Hai chữ ký, hai người — một người
      // vừa duyệt khoản chi vừa viết phiếu chi là phá tách vai.
      //
      // Và KHÔNG có nhánh "sửa" (chủ chốt 07/08/2026): phiếu chi phát hành ra là tiền đã rời két.
      // Sai thì huỷ rồi lập phiếu mới — endpoint PUT bên server cũng đã gỡ.
      const input: PaymentVoucherInput = {
        ...payload,
        purchase_request_id: purchase.id,
      };
      const saved: PaymentVoucherRow = await api.accounting.createVoucher(
        token,
        input,
      );
      if (files.length) {
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
              {voucher ? "Sửa chứng từ" : "Lập chứng từ thanh toán"}
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

          <VoucherSummaryStrip
            purchase={purchase}
            loai={loai}
            maxAmountVnd={maxAmountVnd}
          />

          <VoucherSegments
            form={form}
            voucher={voucher}
            selectType={selectType}
            loai={loai}
            chonLoai={chonLoai}
            coDotGiao={coDotGiao}
            purchase={purchase}
          />

          <VoucherAmountFields
            loai={loai}
            coDotGiao={coDotGiao}
            form={form}
            setForm={setForm}
            set={set}
            voucher={voucher}
            purchase={purchase}
            dotDangChon={dotDangChon}
            maxAmountVnd={maxAmountVnd}
            amountVnd={amountVnd}
          />

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

          <VoucherRecipientSection
            form={form}
            set={set}
            loadingAccounts={loadingAccounts}
            companyAccounts={companyAccounts}
            selectCompanyAccount={selectCompanyAccount}
          />

          <VoucherAttachSection
            voucher={voucher}
            files={files}
            setFiles={setFiles}
            addFiles={addFiles}
          />

          <VoucherRefSection form={form} set={set} />
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
            {voucher ? "Lưu thay đổi" : "Lập chứng từ"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
