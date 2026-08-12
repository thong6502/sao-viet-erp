import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type CompanyBankAccountRow,
  type PaymentVoucherAttachment,
  type PaymentVoucherInput,
  type PaymentVoucherRow,
  type PaymentVoucherSource,
  type PaymentVoucherStatus,
  type PaymentVoucherType,
  type PurchaseRequestRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { VOUCHER_PAGE_LABEL } from "../constants/features";
import {
  amountInWords,
  fmtDate,
  fmtDateTime,
  money,
  originalMoney,
} from "../utils/format";
import { printTT200 } from "../utils/printTT200";
import { PaymentReceiptDialog } from "./PaymentReceiptDialog";
import { PaymentVoucherDialog } from "./PaymentVoucherDialog";
import "./accounting.css";
import "./purchase.css";

const PAGE_SIZE = 20;

/** Chỉ còn HAI trạng thái từ 06/08/2026 (Đ1): lập phiếu chi = tiền đã ra. Bậc "Chờ chi" và nút
 *  "Xác nhận đã chi" đã bỏ hẳn — bên nghiệp vụ nói thẳng *"tạo phiếu chi là đã chi tiền rồi còn
 *  công nợ cái gì"*. Phiếu ghi nhận nhầm thì HUỶ (bắt lý do), không lùi về chờ. */
const STATUS_META: Record<
  PaymentVoucherStatus,
  { label: string; tone: string }
> = {
  paid: { label: "Đã chi", tone: "paid" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

const STAGE_LABELS = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
} as const;

const SOURCE_LABELS: Record<PaymentVoucherSource, string> = {
  purchase_request: "Đơn mua hàng",
  internal_expense: "Khác",
  customer_refund: "Khác",
  other: "Khác",
};

const VOUCHER_METHOD_LABELS: Record<PaymentVoucherType, string> = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
};

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function optional(value?: string | null): string | null {
  const cleaned = (value ?? "").trim();
  return cleaned || null;
}

/** In Phiếu chi theo mẫu 02-TT. UNC cũng dùng mẫu này (chốt nghiệp vụ), chỉ ghi thêm
 *  dòng thông tin chuyển khoản. */
function printVoucher(row: PaymentVoucherRow): boolean {
  const isBank = row.voucher_type === "bank_transfer";
  return printTT200({
    kind: "chi",
    docNo: row.doc_no,
    docDate: row.voucher_date,
    debitAccount: row.debit_account,
    creditAccount: row.credit_account,
    personName: isBank ? row.beneficiary_account_holder || row.supplier_name : row.cash_recipient_name,
    personAddress: isBank ? row.supplier_address : row.cash_recipient_address,
    reason: row.content,
    extraLines: [
      { label: "Nguồn chi", value: SOURCE_LABELS[row.source_type] ?? row.source_type },
      { label: "Đợt thanh toán", value: STAGE_LABELS[row.payment_stage] },
      ...(isBank
        ? [
            {
              label: "Hình thức",
              value: `Chuyển khoản — trích TK ${row.company_account_number ?? "—"} tại ${row.company_bank_name ?? "—"} → TK thụ hưởng ${row.beneficiary_account_number ?? "—"} tại ${row.beneficiary_bank_name ?? "—"}`,
            },
          ]
        : []),
      ...(row.invoice_number ? [{ label: "Hóa đơn", value: row.invoice_number }] : []),
      ...(row.bank_reference ? [{ label: "Mã giao dịch", value: row.bank_reference }] : []),
    ],
    amount: row.amount,
    amountVnd: row.amount_vnd,
    currency: row.currency,
    exchangeRate: row.exchange_rate,
    attachmentCount: row.attachment_count,
    cancelled: row.status === "cancelled",
  });
}

function StandaloneVoucherDialog({
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
    credit_account: "1111",
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
      credit_account: optional(form.credit_account) ?? (isBank ? "1121" : "1111"),
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
    <div className="acct-modal" role="dialog" aria-modal="true">
      <form className="acct-modal__box" onSubmit={submit}>
        <header className="acct-modal__head">
          <div>
            <p className="eyebrow">Phiếu chi</p>
            <h2>Tạo phiếu chi</h2>
          </div>
          <button type="button" className="acct-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="acct-modal__body">
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
                set("credit_account", "1111");
              }}
            >
              Tiền mặt
            </button>
            <button
              type="button"
              className={isBank ? "is-active" : ""}
              onClick={() => {
                set("voucher_type", "bank_transfer" as PaymentVoucherType);
                set("credit_account", "1121");
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
          <section className="acct-form-section">
            <h3>Định khoản và tham chiếu</h3>
            <div className="acct-form-grid acct-form-grid--2">
              <label className="acct-field">
                <span>Nợ</span>
                <input
                  className="input"
                  value={form.debit_account ?? ""}
                  onChange={(event) => set("debit_account", event.target.value)}
                  placeholder="VD: 642, 1331"
                />
              </label>
              <label className="acct-field">
                <span>Có</span>
                <input
                  className="input"
                  value={form.credit_account ?? ""}
                  onChange={(event) => set("credit_account", event.target.value)}
                  placeholder={isBank ? "1121" : "1111"}
                />
              </label>
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
        <footer className="acct-modal__foot">
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            Lưu phiếu
          </Button>
        </footer>
      </form>
    </div>
  );
}

export function PaymentVouchersPage({
  navigate,
  eventTick = 0,
  focusQuery = null,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Liên thông từ trang Phiếu thu: điền sẵn ô tìm kiếm (mã PC/UNC). */
  focusQuery?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Phiếu chi (tách 10/08/2026). `create` = LẬP phiếu + gán chứng từ.
  const canApprove = can("phieu_chi", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const openReceipts = (query: string) =>
    navigate("ke-toan-phieu-thu", { focusReceiptQuery: query });
  // KHÔNG còn `canMarkPaid`: bước "Xác nhận đã chi" đã bỏ cùng với trạng thái Chờ chi (Đ1).
  const canCancel = can("phieu_chi", "cancel");
  const canExport = can("phieu_chi", "export");
  const [rows, setRows] = useState<PaymentVoucherRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editState, setEditState] = useState<null | {
    voucher: PaymentVoucherRow | null;
    purchase: PurchaseRequestRow;
  }>(null);
  const [cancelling, setCancelling] = useState<PaymentVoucherRow | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [receiptFor, setReceiptFor] = useState<PaymentVoucherRow | null>(null);
  const [standaloneOpen, setStandaloneOpen] = useState(false);
  const [attachments, setAttachments] = useState<PaymentVoucherAttachment[]>(
    [],
  );
  const [attachmentBusy, setAttachmentBusy] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .vouchers(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
        voucher_type: typeFilter === "all" ? null : typeFilter,
        // "group": phiếu cùng PMH đứng cạnh nhau, nhóm có phiếu mới nhất lên đầu.
        sort: "-group",
        page,
        size: PAGE_SIZE,
      })
      .then((response) => {
        setRows(response.items);
        setTotal(response.total);
        // Chỉ giữ popup đang mở nếu phiếu đó còn trong kết quả; KHÔNG tự chọn
        // dòng đầu (sẽ làm popup tự bung khi vào trang).
        setSelectedId((current) =>
          current != null && response.items.some((row) => row.id === current)
            ? current
            : null,
        );
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Không tải được Phiếu chi.",
        ),
      )
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, typeFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  // Liên thông từ trang Phiếu thu: điền mã vào ô tìm → load() tự chạy lại.
  useEffect(() => {
    if (!focusQuery) return;
    setQ(focusQuery);
    setStatusFilter("all");
    setTypeFilter("all");
    setPage(1);
  }, [focusQuery]);

  // Phiếu đang mở popup (null = không mở).
  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  const selectedVoucherId = selected?.id ?? null;
  /** Đóng popup rồi mới mở form — không chồng hai lớp cửa sổ. */
  function closeDetailThen(action: () => void) {
    setSelectedId(null);
    action();
  }

  useEffect(() => {
    if (!token || selectedVoucherId == null) {
      setAttachments([]);
      return;
    }
    let cancelled = false;
    api.accounting
      .voucherAttachments(token, selectedVoucherId)
      .then((response) => {
        if (!cancelled) setAttachments(response.items);
      })
      .catch(() => {
        if (!cancelled) setAttachments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token, selectedVoucherId]);

  async function uploadAttachments(list: FileList | null) {
    if (!token || selectedVoucherId == null || !list?.length) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      for (const file of Array.from(list)) {
        await api.accounting.uploadVoucherAttachment(
          token,
          selectedVoucherId,
          file,
        );
      }
      const response = await api.accounting.voucherAttachments(
        token,
        selectedVoucherId,
      );
      setAttachments(response.items);
      load(); // cập nhật attachment_count → badge "Thiếu chứng từ" ở bảng
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không tải được file lên.",
      );
    } finally {
      setAttachmentBusy(false);
    }
  }

  async function removeAttachment(attachment: PaymentVoucherAttachment) {
    if (!token || selectedVoucherId == null) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      await api.accounting.deleteVoucherAttachment(
        token,
        selectedVoucherId,
        attachment.id,
      );
      setAttachments((current) =>
        current.filter((row) => row.id !== attachment.id),
      );
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không xóa được file đính kèm.",
      );
    } finally {
      setAttachmentBusy(false);
    }
  }
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // ĐÃ GỠ 07/08/2026 — `openEdit`. Không còn đường sửa phiếu chi đã lập.

  // async function openTopUp(row: PaymentVoucherRow) {
  //   if (!token) return;
  //   setBusy(true);
  //   setError(null);
  //   try {
  //     const purchase = await api.purchaseRequests.get(
  //       token,
  //       row.purchase_request_id,
  //     );
  //     if (!["approved", "purchased", "partially_received", "received"]
  //           .includes(purchase.status)) {
  //       setError(
  //         `PMH ${purchase.code} không còn ở trạng thái được lập chứng từ.`,
  //       );
  //       return;
  //     }
  //     // `available_amount` ĐÃ BỎ (06/08/2026). Trần nay có HAI mức theo loại phiếu:
  //     // `tran_dat_coc` (đặt cọc) và `outstanding_amount` = công nợ (thanh toán).
  //     if (Math.max(purchase.tran_dat_coc, purchase.outstanding_amount) <= 0) {
  //       setError(`PMH ${purchase.code} đã được lập đủ chứng từ thanh toán.`);
  //       return;
  //     }
  //     setEditState({ voucher: null, purchase });
  //   } catch (err) {
  //     setError(
  //       err instanceof ApiError ? err.message : "Không tải được PMH nguồn.",
  //     );
  //   } finally {
  //     setBusy(false);
  //   }
  // }

  async function confirmCancel() {
    if (!token || !cancelling) return;
    if (!cancelReason.trim()) {
      setError("Vui lòng nhập lý do hủy.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.cancelVoucher(
        token,
        cancelling.id,
        cancelReason.trim(),
      );
      setCancelling(null);
      setCancelReason("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không hủy được chứng từ.",
      );
    } finally {
      setBusy(false);
    }
  }

  function startPrint(row: PaymentVoucherRow) {
    if (!printVoucher(row))
      setError(
        "Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.",
      );
  }

  function actions(row: PaymentVoucherRow) {
    return (
      <div className="acct-actions">
        {canExport && (
          <Button variant="ghost" onClick={() => startPrint(row)}>
            In phiếu
          </Button>
        )}
        {/* KHÔNG có nút SỬA (chủ chốt 07/08/2026): phiếu chi phát hành ra là TIỀN ĐÃ RỜI KÉT,
            sửa nó là làm tờ giấy đang nằm ở chỗ nhà cung cấp khác với bản trong máy. Sai thì HUỶ
            (giữ số chứng từ, có lý do) rồi lập phiếu mới — dấu vết còn đủ hai bản.
            Thứ duy nhất còn sửa được là ĐÍNH KÈM tài liệu: hoá đơn / UNC thường về sau khi chi. */}
        {/* {canApprove && row.status === "paid" && (
          <Button
            variant="ghost"
            onClick={() => closeDetailThen(() => openTopUp(row))}
            disabled={busy}
          >
            Chi bổ sung
          </Button>
        )}
        {canApprove &&
          row.status === "paid" &&
          row.receipt_received_amount + row.receipt_pending_amount <
            row.amount_vnd && (
            <Button
              variant="ghost"
              onClick={() => closeDetailThen(() => setReceiptFor(row))}
              disabled={busy}
            >
              Lập phiếu thu
            </Button>
          )} */}
        {/* HUỶ nay áp cho phiếu ĐÃ CHI — dùng cho ca ghi nhận nhầm. Bắt lý do; server chặn nếu
            phiếu đã có phiếu thu gắn vào (tiền đã hoàn về thì không xoá dấu vết được nữa), nên
            nút vẫn hiện và người dùng nhận đúng câu báo thay vì im lặng không có lối. */}
        {canCancel &&
          row.status === "paid" &&
          row.receipt_received_amount + row.receipt_pending_amount === 0 && (
            <Button
              variant="danger"
              onClick={() =>
                closeDetailThen(() => {
                  setCancelling(row);
                  setCancelReason("");
                })
              }
            >
              Hủy
            </Button>
          )}
      </div>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Kế toán</p>
        <h1 className="md-page__title">{VOUCHER_PAGE_LABEL}</h1>
        <p className="md-page__sub">
          Lập phiếu chi là tiền đã ra khỏi két — phiếu sinh ra đã là "Đã chi".
          Ghi nhận nhầm thì hủy phiếu (bắt lý do), nguồn chi có thể là Đơn mua hàng,
          chi phí nội bộ, hoàn tiền khách hàng hoặc khoản chi khác.
        </p>
      </header>
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      <section className="acct-toolbar">
        <form
          className="md-page__search"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            load();
          }}
        >
          <input
            className="input"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Tìm PC, UNC, PMH, YCMH..."
          />
          {/* <Button type="submit" variant="ghost">
            Tìm
          </Button> */}
        </form>
        <div className="acct-toolbar__filters">
          <select
            className="input"
            value={typeFilter}
            onChange={(event) => {
              setTypeFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">Tất cả hình thức</option>
            <option value="cash">Tiền mặt</option>
            <option value="bank_transfer">Chuyển khoản</option>
          </select>
          <select
            className="input"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">Tất cả trạng thái</option>
            {Object.entries(STATUS_META).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
          {canApprove && (
            <Button variant="primary" onClick={() => setStandaloneOpen(true)}>
              + Tạo phiếu chi
            </Button>
          )}
        </div>
      </section>
      <section className="card md-page__tablewrap acct-list acct-list--voucher">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã chứng từ</th>
              <th>Đối tượng</th>
              <th>Người lập</th>
              <th className="acct-amount-cell">Số tiền</th>
              <th>Trạng thái</th>
              <th className="acct-action-cell">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6}>Đang tải...</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={6}>Chưa có chứng từ phù hợp.</td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => (
                <Fragment key={row.id}>
                  <tr
                    className={
                      row.id === selected?.id ? "purchase__row--selected" : ""
                    }
                    onClick={() => setSelectedId(row.id)}
                  >
                    <td className="acct-code-cell">
                      <strong>{row.code}</strong>
                      <small>
                        {VOUCHER_METHOD_LABELS[row.voucher_type] ?? row.voucher_type} ·{" "}
                        {SOURCE_LABELS[row.source_type] ?? row.source_type}
                      </small>
                    </td>
                    <td className="acct-target-cell">
                      <strong>{row.supplier_name}</strong>
                      {row.source_type === "purchase_request" && row.purchase_request_code && (
                        <small>{row.purchase_request_code}</small>
                      )}
                    </td>
                    <td className="acct-user-cell">
                      <div title={row.created_by_name ?? undefined}>
                        {row.created_by_name || "—"}
                      </div>
                      <small>{fmtDateTime(row.created_at)}</small>
                    </td>
                    <td
                      className="acct-amount-cell"
                      title={
                        row.currency !== "VND"
                          ? `${originalMoney(row.amount, row.currency)} · tỷ giá ${row.exchange_rate}`
                          : undefined
                      }
                    >
                      <strong>{money(row.amount_vnd)}</strong>
                    </td>
                    <td className="acct-status-cell">
                      <span
                        className={`acct-voucher-status acct-voucher-status--${STATUS_META[row.status].tone}`}
                      >
                        {STATUS_META[row.status].label}
                      </span>
                      {row.status === "paid" &&
                        row.attachment_count === 0 && (
                          <span className="acct-missing-doc">
                            Thiếu chứng từ
                          </span>
                        )}
                    </td>
                    <td className="acct-action-cell">
                      <button
                        type="button"
                        className="acct-eye"
                        aria-label={`Xem chi tiết ${row.code}`}
                        title="Xem chi tiết"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedId(row.id);
                        }}
                      >
                        <Icon name="eye" size={17} />
                      </button>
                    </td>
                  </tr>
                </Fragment>
              ))}
          </tbody>
        </table>
        <div className="md-page__pager">
          <span>{total} chứng từ</span>
          <div>
            <Button
              variant="ghost"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Trước
            </Button>
            <span>
              {page}/{totalPages}
            </span>
            <Button
              variant="ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((value) => value + 1)}
            >
              Sau
            </Button>
          </div>
        </div>
      </section>
      {selected && (
        <DetailModal
          kicker={selected.voucher_type === "cash" ? "Phiếu chi" : "Ủy nhiệm chi"}
          title={selected.code}
          subtitle={selected.doc_no ? `Số phiếu: ${selected.doc_no}` : undefined}
          badge={
            <div className="acct-status-stack">
              <span
                className={`acct-voucher-status acct-voucher-status--${STATUS_META[selected.status].tone}`}
              >
                {STATUS_META[selected.status].label}
              </span>
              {selected.status === "paid" && selected.attachment_count === 0 && (
                <span className="acct-missing-doc">Thiếu chứng từ</span>
              )}
            </div>
          }
          footer={actions(selected)}
          onClose={() => setSelectedId(null)}
        >
          <dl className="purchase__facts">
            {selected.source_type === "purchase_request" ? (
              <>
                <div>
                  <dt>PMH nguồn</dt>
                  <dd>{selected.purchase_request_code}</dd>
                </div>
                <div>
                  <dt>YCMH nguồn</dt>
                  <dd>
                    {selected.source_request_codes.length
                      ? selected.source_request_codes.map((code, index) => (
                          <span key={code}>
                            {index > 0 && ", "}
                            <CodeLink code={code} onOpen={openYcmh} />
                          </span>
                        ))
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Nhà cung cấp</dt>
                  <dd>{selected.supplier_name}</dd>
                </div>
              </>
            ) : (
              <>
                <div>
                  <dt>Nguồn chi</dt>
                  <dd>{SOURCE_LABELS[selected.source_type] ?? selected.source_type}</dd>
                </div>
                <div>
                  <dt>Đối tượng nhận</dt>
                  <dd>{selected.supplier_name}</dd>
                </div>
              </>
            )}
            <div>
              <dt>Ngày chứng từ</dt>
              <dd>{fmtDate(selected.voucher_date)}</dd>
            </div>
            <div>
              <dt>Đợt thanh toán</dt>
              <dd>
                {selected.source_type === "purchase_request"
                  ? STAGE_LABELS[selected.payment_stage]
                  : SOURCE_LABELS[selected.source_type]}
              </dd>
            </div>
            {selected.source_type === "purchase_request" && (
              <div>
                <dt>Trả cho đợt giao</dt>
                <dd>
                  {selected.delivery_seq_no != null
                    ? `Đợt ${selected.delivery_seq_no}`
                    : selected.payment_stage === "advance"
                      ? "Không gắn đợt (đặt cọc)"
                      : "Đơn không theo dõi theo đợt"}
                </dd>
              </div>
            )}
            <div>
              <dt>Người lập</dt>
              <dd>{selected.created_by_name || "—"}</dd>
            </div>
            <div>
              <dt>Lập lúc</dt>
              <dd>{fmtDateTime(selected.created_at)}</dd>
            </div>
          </dl>
          <div className="acct-purpose">
            <span>Nội dung chi</span>
            <strong>{selected.content}</strong>
          </div>
          <div className="acct-voucher-amount">
            <span>Số tiền quy đổi</span>
            <strong>{money(selected.amount_vnd)}</strong>
            <small>
              {selected.currency !== "VND"
                ? `${originalMoney(selected.amount, selected.currency)} · tỷ giá ${selected.exchange_rate}`
                : amountInWords(selected.amount_vnd)}
            </small>
            {(selected.receipt_received_amount > 0 ||
              selected.receipt_pending_amount > 0) && (
              <small>
                <button
                  type="button"
                  className="code-link"
                  onClick={() => openReceipts(selected.code)}
                >
                  Đã thu {money(selected.receipt_received_amount)}
                  {selected.receipt_pending_amount > 0
                    ? ` · chờ thu ${money(selected.receipt_pending_amount)}`
                    : ""}
                </button>
              </small>
            )}
          </div>
          {selected.voucher_type === "bank_transfer" ? (
            <div className="acct-account-pair">
              <div>
                <span>Trích nợ</span>
                <strong>{selected.company_account_holder}</strong>
                <small>
                  {selected.company_account_number} ·{" "}
                  {selected.company_bank_name}
                </small>
              </div>
              <div>
                <span>Thụ hưởng</span>
                <strong>{selected.beneficiary_account_holder}</strong>
                <small>
                  {selected.beneficiary_account_number} ·{" "}
                  {selected.beneficiary_bank_name}
                </small>
              </div>
            </div>
          ) : (
            <div className="acct-account-pair">
              <div>
                <span>Người nhận</span>
                <strong>{selected.cash_recipient_name}</strong>
                <small>{selected.cash_recipient_address || "—"}</small>
              </div>
            </div>
          )}
          {selected.bank_reference && (
            <div className="purchase__note">
              Mã giao dịch: <strong>{selected.bank_reference}</strong>
            </div>
          )}
          <div className="acct-attachments">
            <span className="acct-attachments__label">
              Chứng từ đính kèm
            </span>
            {attachments.length === 0 && (
              <small className="acct-attachments__empty">
                Chưa có file đính kèm.
                {selected.status === "paid" &&
                  " Phiếu đã chi — cần bổ sung hóa đơn/biên nhận."}
              </small>
            )}
            {attachments.length > 0 && (
              <div className="acct-att-grid">
                {attachments.map((attachment) => {
                  const isImage = [
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                    "image/gif",
                  ].includes(attachment.file_type ?? "");
                  const href = assetUrl(attachment.file_url) ?? "#";
                  return (
                    <div className="acct-att-item" key={attachment.id}>
                      {isImage ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          title={attachment.file_name}
                        >
                          <img
                            className="acct-att-thumb"
                            src={href}
                            alt={attachment.file_name}
                          />
                        </a>
                      ) : (
                        <a
                          className="acct-att-file"
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          title={attachment.file_name}
                        >
                          📎 {attachment.file_name}
                        </a>
                      )}
                      {canApprove && (
                        <button
                          type="button"
                          className="acct-att-x"
                          aria-label={`Xóa ${attachment.file_name}`}
                          disabled={attachmentBusy}
                          onClick={() => removeAttachment(attachment)}
                        >
                          ×
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {canApprove && selected.status !== "cancelled" && (
              <label className="acct-field">
                <span>Thêm ảnh hóa đơn / PDF (tối đa 10 MB)</span>
                <input
                  className="input"
                  type="file"
                  multiple
                  accept="image/*,application/pdf"
                  disabled={attachmentBusy}
                  onChange={(event) => {
                    uploadAttachments(event.target.files);
                    event.target.value = "";
                  }}
                />
              </label>
            )}
          </div>
          {selected.cancel_reason && (
            <div className="banner banner--error">
              Lý do hủy: {selected.cancel_reason}
            </div>
          )}
        </DetailModal>
      )}

      {editState && (
        <PaymentVoucherDialog
          key={editState.voucher?.id ?? "new"}
          purchase={editState.purchase}
          voucher={editState.voucher}
          onClose={() => setEditState(null)}
          onSaved={() => {
            setEditState(null);
            load();
          }}
        />
      )}
      {standaloneOpen && (
        <StandaloneVoucherDialog
          onClose={() => setStandaloneOpen(false)}
          onSaved={(saved) => {
            setStandaloneOpen(false);
            setSelectedId(saved.id);
            load();
          }}
        />
      )}
      {receiptFor && (
        <PaymentReceiptDialog
          key={`receipt-${receiptFor.id}`}
          voucher={receiptFor}
          onClose={() => setReceiptFor(null)}
          onSaved={() => {
            setReceiptFor(null);
            load();
          }}
        />
      )}
      {/* ĐÃ GỠ 06/08/2026 — hộp "Xác nhận đã chi". Phiếu lập ra đã là tiền ra khỏi két, không còn
          bước xác nhận nào ở giữa (Đ1). Endpoint `mark-paid` cũng đã gỡ khỏi backend. */}
      {cancelling && (
        <div className="acct-modal" role="dialog" aria-modal="true">
          <div className="acct-modal__box">
            <header className="acct-modal__head">
              <h2>Hủy {cancelling.code}</h2>
              <button
                type="button"
                className="acct-modal__x"
                onClick={() => setCancelling(null)}
              >
                ×
              </button>
            </header>
            <div className="acct-modal__body">
              <label className="acct-field">
                <span>
                  Lý do hủy <b>*</b>
                </span>
                <textarea
                  autoFocus
                  className="input acct-textarea"
                  value={cancelReason}
                  onChange={(event) => setCancelReason(event.target.value)}
                />
              </label>
            </div>
            <footer className="acct-modal__foot">
              <Button variant="ghost" onClick={() => setCancelling(null)}>
                Đóng
              </Button>
              <Button variant="danger" loading={busy} onClick={confirmCancel}>
                Hủy chứng từ
              </Button>
            </footer>
          </div>
        </div>
      )}
    </main>
  );
}
