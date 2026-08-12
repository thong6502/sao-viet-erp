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
import { fmtDate, money } from "../utils/format";

/** Hôm nay dạng `yyyy-mm-dd` — trần cho ngày chứng từ và ngày hoá đơn (không cho chọn tương lai). */
const HOM_NAY = new Date().toISOString().slice(0, 10);

const STAGE_LABELS: Record<PaymentStage, string> = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
};

/** Hai LOẠI phiếu, khác nhau ở ba chỗ: có gắn đợt giao không, trần là số nào, và tiền chi ra khi
 *  hàng đã về hay chưa. Bắt chọn ngay từ đầu thay vì suy từ số tiền — cách cũ (số tiền = trần thì
 *  tự thành "thanh toán cuối") đoán mò, và đoán sai thì backend từ chối sau khi người dùng đã gõ
 *  xong cả form. */
type LoaiPhieu = "dat_coc" | "thanh_toan";

interface PaymentVoucherDialogProps {
  purchase: PurchaseRequestRow;
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

/** Đợt giao CÒN NỢ đầu tiên — gợi ý mặc định khi lập phiếu thanh toán.
 *
 *  Dùng `con_no` (đã trừ cả tiền trả đích danh lẫn cọc bù) chứ không tự trừ tay: đợt được cọc phủ
 *  hết thì không còn gì để trả, chọn sẵn nó là mời người dùng gõ một số rồi ăn lỗi. */
function dotGoiY(purchase: PurchaseRequestRow): number | null {
  const con_no = purchase.deliveries.filter((d) => d.con_no > 0);
  const nguon = con_no.length ? con_no : purchase.deliveries;
  return nguon[0]?.id ?? null;
}

/** Còn nợ của một đợt — cũng chính là TRẦN lập phiếu chi thanh toán cho đợt đó. */
function conNoDot(purchase: PurchaseRequestRow, deliveryId: number | null): number {
  if (deliveryId == null) return purchase.outstanding_amount;
  return purchase.deliveries.find((d) => d.id === deliveryId)?.con_no ?? 0;
}

/** Số tiền điền sẵn cho phiếu ĐẶT CỌC.
 *
 * Ưu tiên **cọc dự kiến** thu mua đã khai trên phiếu mua — đó là con số đã thoả thuận với NCC và
 * đã qua duyệt, kế toán không phải đi hỏi lại.
 *
 * Chưa khai (bằng 0) thì lấy **nửa giá trị đơn** (chủ chốt 06/08/2026) — mức cọc thông thường, để
 * kế toán có sẵn một số hợp lý mà sửa, thay vì đối diện ô trống hoặc bị điền nguyên giá trị đơn
 * (điền nguyên đơn là mời người ta bấm Lưu và ứng trước 100%).
 *
 * Luôn kẹp trong trần đặt cọc — gợi ý mà vượt trần thì bấm Lưu là ăn lỗi ngay. */
/** Nội dung đơn để nhét vào nội dung phiếu chi. Phiếu CŨ chưa có ô gộp ⇒ lấy `purpose`. */
function moTaDon(purchase: PurchaseRequestRow): string {
  return (purchase.content ?? purchase.purpose ?? "").trim();
}

function cocGoiY(purchase: PurchaseRequestRow): number {
  const mong_muon =
    purchase.deposit_expected > 0
      ? purchase.deposit_expected
      : Math.round(purchase.total_estimate / 2);
  return Math.min(mong_muon, purchase.tran_dat_coc);
}

function initialForm(
  purchase: PurchaseRequestRow,
  voucher?: PaymentVoucherRow | null,
): PaymentVoucherBaseInput {
  if (voucher) {
    return {
      voucher_type: voucher.voucher_type,
      payment_stage: voucher.payment_stage,
      delivery_id: voucher.delivery_id,
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
  // Chưa có đợt giao nào ⇒ hàng chưa về ⇒ đây chỉ có thể là tiền ĐẶT CỌC. Có đợt rồi thì mặc định
  // là THANH TOÁN, gắn sẵn đợt còn nợ và điền sẵn số công nợ.
  const chuaCoDot = purchase.deliveries.length === 0;
  return {
    voucher_type: "cash",
    payment_stage: chuaCoDot ? "advance" : "final",
    delivery_id: chuaCoDot ? null : dotGoiY(purchase),
    voucher_date: isoToday(),
    // DORMANT: hạn trả đã chuyển lên đợt giao, phiếu chi không còn hạn.
    planned_payment_date: null,
    amount: chuaCoDot
      ? cocGoiY(purchase)
      : conNoDot(purchase, dotGoiY(purchase)),
    currency: "VND",
    exchange_rate: 1,
    content: `Thanh toán ${purchase.code}${
      moTaDon(purchase) ? ` - ${moTaDon(purchase)}` : ""
    }`.slice(0, 500),
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
    Promise.all([
      api.accounting.companyAccounts(token, true, "pay"),
      purchase.supplier_id
        ? api.accounting.supplierAccounts(token, purchase.supplier_id, true)
        : Promise.resolve([]),
    ])
      .then(([company, supplier]) => {
        setCompanyAccounts(company);
        setSupplierAccounts(supplier);
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
            supplier_bank_account_id: current.supplier_bank_account_id ?? null,
            currency,
            exchange_rate: currency === "VND" ? 1 : current.exchange_rate,
          };
        });
      })
      .catch(() => setError("Không tải được danh sách tài khoản ngân hàng."))
      .finally(() => setLoadingAccounts(false));
  }, [token, purchase.supplier_id]);

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

          {/* Bốn số theo đúng công thức mới: nợ = HÀNG ĐÃ VỀ − đã chi ròng. Ô cuối đổi nghĩa theo
              LOẠI phiếu đang chọn, nên nhãn của nó cũng phải đổi — để nguyên "Còn được lập" là
              người dùng không biết con số đang đo cái gì. */}
          <div className="acct-summary-strip">
            <div>
              <span>Tổng PMH</span>
              <strong>
                {purchase.total_estimate.toLocaleString("vi-VN")} đ
              </strong>
            </div>
            <div>
              <span>Hàng đã giao</span>
              <strong>
                {purchase.gia_tri_da_giao.toLocaleString("vi-VN")} đ
              </strong>
            </div>
            <div>
              <span>Đã chi ròng</span>
              <strong>{purchase.net_paid.toLocaleString("vi-VN")} đ</strong>
            </div>
            <div>
              <span>
                {loai === "dat_coc" ? "Trần đặt cọc" : "Công nợ (trần chi)"}
              </span>
              <strong>{maxAmountVnd.toLocaleString("vi-VN")} đ</strong>
            </div>
          </div>

          <div className="acct-segment" aria-label="Hình thức chi">
            <button
              type="button"
              className={form.voucher_type === "cash" ? "is-active" : ""}
              onClick={() => selectType("cash")}
              disabled={!!voucher}
            >
              Tiền mặt
            </button>
            <button
              type="button"
              className={
                form.voucher_type === "bank_transfer" ? "is-active" : ""
              }
              onClick={() => selectType("bank_transfer")}
              disabled={!!voucher}
            >
              Chuyển khoản
            </button>
          </div>

          {/* LOẠI PHIẾU đứng TRƯỚC mọi ô khác vì nó quyết định trần, đợt giao và số tiền điền
              sẵn. Người dùng chọn sai ở đây thì mọi ô dưới đều sai theo. */}
          <div className="acct-segment" aria-label="Loại phiếu">
            <button
              type="button"
              className={loai === "dat_coc" ? "is-active" : ""}
              onClick={() => chonLoai("dat_coc")}
              disabled={!!voucher}
            >
              Đặt cọc / ứng trước
            </button>
            <button
              type="button"
              className={loai === "thanh_toan" ? "is-active" : ""}
              onClick={() => chonLoai("thanh_toan")}
              disabled={!!voucher || !coDotGiao}
              title={
                coDotGiao
                  ? undefined
                  : "Đơn chưa ghi đợt giao nào — hàng chưa về thì mọi khoản chi đều là đặt cọc."
              }
            >
              Thanh toán
            </button>
          </div>
          <p className="acct-loai-hint">
            {loai === "dat_coc"
              ? "Cọc là tiền chi khi hàng CHƯA về nên không gắn đợt giao. Trần tính theo giá trị đơn đặt; cọc trừ vào công nợ của cả đơn."
              : "Trả cho một ĐỢT GIAO cụ thể. Trần đúng bằng công nợ đã phát sinh — chi quá là trả tiền cho hàng chưa về."}
          </p>
          {/* Đơn ĐÃ có phiếu cọc mà lại đang lập phiếu cọc nữa — CẢNH BÁO, không chặn.
              Ứng thêm là ca có thật (cọc 30% rồi NCC đòi ứng thêm 20%), và mỗi lần tiền rời két
              phải là một chứng từ riêng: sửa phiếu cọc cũ lên số to hơn là làm phiếu không khớp
              lần chi thật. Nhưng bấm nhầm cũng là ca có thật, nên phải đập vào mắt. */}
          {!voucher && loai === "dat_coc" && purchase.coc_da_lap.length > 0 && (
            <div className="banner banner--warn" role="status">
              Đơn này <strong>đã có {purchase.coc_da_lap.length} phiếu đặt cọc</strong> —{" "}
              {purchase.coc_da_lap
                .map(
                  (c) =>
                    `${c.doc_no ?? c.code} ${money(c.amount)} ngày ${fmtDate(c.voucher_date)}`,
                )
                .join(" · ")}
              , tổng <strong>{money(purchase.coc_da_chi)}</strong>. Đây là phiếu cọc
              thứ {purchase.coc_da_lap.length + 1}. Nếu chỉ muốn sửa số cọc cũ thì
              đóng hộp này và sửa đúng phiếu đó.
            </div>
          )}

          <div className="acct-form-grid acct-form-grid--3">
            {loai === "thanh_toan" && coDotGiao ? (
              <label className="acct-field">
                <span>
                  Đợt giao <b>*</b>
                </span>
                <select
                  className="input"
                  value={form.delivery_id ?? ""}
                  disabled={!!voucher}
                  onChange={(e) => {
                    // Đổi đợt là đổi TRẦN ⇒ điền lại số tiền theo đợt mới. Giữ số cũ là người dùng
                    // bấm Lưu với con số của đợt trước rồi ăn lỗi mà không hiểu vì sao.
                    const id = e.target.value ? Number(e.target.value) : null;
                    setForm((current) => ({
                      ...current,
                      delivery_id: id,
                      amount: conNoDot(purchase, id),
                    }));
                  }}
                >
                  <option value="">Chọn đợt giao</option>
                  {purchase.deliveries.map((d) => (
                    <option key={d.id} value={d.id}>
                      Đợt {d.seq_no} · {fmtDate(d.delivery_date)} ·{" "}
                      {d.con_no > 0 ? `còn nợ ${money(d.con_no)}` : "đã trả xong"}
                    </option>
                  ))}
                </select>
                {dotDangChon && (
                  <small>
                    Giá trị đợt {money(dotDangChon.amount)} · đã trả{" "}
                    {money(dotDangChon.paid_amount)}

                    {` · còn nợ ${money(dotDangChon.con_no)}`}
                    {dotDangChon.invoice_number
                      ? ` · HĐ ${dotDangChon.invoice_number}`
                      : " · chưa gán hóa đơn"}
                  </small>
                )}
              </label>
            ) : (
              <label className="acct-field">
                <span>Đợt thanh toán</span>
                <select
                  className="input"
                  value={form.payment_stage}
                  disabled={loai === "dat_coc"}
                  onChange={(e) =>
                    set("payment_stage", e.target.value as PaymentStage)
                  }
                >
                  {Object.entries(STAGE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="acct-field">
              <span>
                Ngày chứng từ <b>*</b>
              </span>
              {/* Chặn TƯƠNG LAI, KHÔNG chặn quá khứ: hoá đơn về muộn là chuyện thường, phiếu phải
                  mang ngày chi tiêu thật mới vào đúng kỳ kế toán. */}
              <input
                className="input"
                type="date"
                max={HOM_NAY}
                value={form.voucher_date}
                onChange={(e) => set("voucher_date", e.target.value)}
              />
            </label>
            {/* Ô "Hạn trả tiền" ĐÃ BỎ (06/08/2026). Phiếu chi là tiền đã ra thì nó không có hạn
                trả; hạn nay thuộc về ĐỢT GIAO (`due_date`, suy từ số ngày cho nợ của NCC), khai ở
                màn Mua hàng. Để lại ô này là đẻ hai nơi khai cùng một thứ. */}
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
              <small>
                Tối đa {maxAmountVnd.toLocaleString("vi-VN")} đ
              </small>
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
                  max={HOM_NAY}
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
            {voucher ? "Lưu thay đổi" : "Lập chứng từ"}
          </Button>
        </footer>
      </form>
    </div>
  );
}
