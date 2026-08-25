import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type CompanyBankAccountRow,
  type PaymentReceiptAttachment,
  type PaymentReceiptInput,
  type PaymentReceiptRow,
  type PaymentReceiptStatus,
  type PaymentVoucherRow,
  type PaymentVoucherType,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { DetailModal } from "../components/DetailModal";
import { fmtDate, fmtDateTime, money, originalMoney } from "../utils/format";
import { printTT200 } from "../utils/printTT200";
import { PaymentReceiptDialog } from "./PaymentReceiptDialog";
import "./accounting.css";
import "./purchase.css";

const PAGE_SIZE = 20;

const STATUS_META: Record<
  PaymentReceiptStatus,
  { label: string; tone: string }
> = {
  waiting_receipt: { label: "Chờ thu", tone: "waiting" },
  received: { label: "Đã thu", tone: "paid" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

function methodText(row: PaymentReceiptRow): string {
  return row.receipt_method === "bank_transfer"
    ? "Về TK ngân hàng"
    : "Nhập quỹ tiền mặt";
}

/** In Phiếu thu theo mẫu 01-TT. */
function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function optional(value?: string | null): string | null {
  const cleaned = (value ?? "").trim();
  return cleaned || null;
}

function sourceLabel(row: PaymentReceiptRow): string {
  if (row.source_type === "order_deposit") return "Cọc đơn bán";
  if (row.source_type === "sales_invoice") return "Thu hóa đơn";
  if (row.source_type === "other") return "Thu khác";
  return "Thu hoàn phiếu chi";
}

function sourceCode(row: PaymentReceiptRow): string | null {
  if (row.source_type === "order_deposit") return row.order_code;
  if (row.source_type === "sales_invoice") return row.sales_invoice_number;
  if (row.source_type === "purchase_refund") return row.payment_voucher_code;
  return null;
}

function sourceName(row: PaymentReceiptRow): string {
  if (row.source_type === "order_deposit") return row.customer_name || "Khách hàng";
  if (row.source_type === "sales_invoice") return row.customer_name || "Khách hàng";
  if (row.source_type === "purchase_refund") return row.supplier_name || "Nhà cung cấp";
  return row.payer_name;
}

function printReceipt(row: PaymentReceiptRow): boolean {
  const linkedSourceCode = sourceCode(row);
  return printTT200({
    kind: "thu",
    docNo: row.doc_no,
    docDate: row.receipt_date,
    debitAccount: row.debit_account,
    creditAccount: row.credit_account,
    personName: row.payer_name,
    personAddress: row.payer_address,
    reason: row.content,
    extraLines: [
      { label: "Hình thức", value: methodText(row) },
      ...(row.receipt_method === "bank_transfer"
        ? [
            {
              label: "Tài khoản nhận",
              value: `${row.company_account_number ?? "—"} tại ${row.company_bank_name ?? "—"}`,
            },
          ]
        : []),
      { label: "Nguồn thu", value: sourceLabel(row) },
      ...(linkedSourceCode ? [{ label: "Mã nguồn", value: linkedSourceCode }] : []),
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

function OtherReceiptDialog({
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
    <div className="acct-modal" role="dialog" aria-modal="true">
      <form className="acct-modal__box" onSubmit={submit}>
        <header className="acct-modal__head">
          <div>
            <p className="eyebrow">Phiếu thu</p>
            <h2>Tạo phiếu thu</h2>
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
        <footer className="acct-modal__foot">
          <Button variant="ghost" type="button" onClick={onClose}>
            Hủy
          </Button>
          <Button variant="primary" type="submit" loading={saving}>
            Lưu phiếu thu
          </Button>
        </footer>
      </form>
    </div>
  );
}

export function PaymentReceiptsPage({
  navigate,
  eventTick = 0,
  focusQuery = null,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Liên thông từ trang Phiếu chi: lọc theo mã PC/UNC khi mở trang. */
  focusQuery?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Phiếu thu (tách 10/08/2026). `create` = LẬP/SỬA phiếu + gán chứng từ;
  // trước đây gọi là `approve` nên nhìn ma trận tưởng là quyền duyệt.
  const canApprove = can("phieu_thu", "create");
  const canMarkReceived = can("phieu_thu", "manage_status");
  const canCancel = can("phieu_thu", "cancel");
  const canExport = can("phieu_thu", "export");
  const [rows, setRows] = useState<PaymentReceiptRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState(focusQuery ?? "");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editState, setEditState] = useState<null | {
    voucher: PaymentVoucherRow;
    receipt: PaymentReceiptRow;
  }>(null);
  const [creatingOther, setCreatingOther] = useState(false);
  const [marking, setMarking] = useState<PaymentReceiptRow | null>(null);
  const [bankReference, setBankReference] = useState("");
  const [cancelling, setCancelling] = useState<PaymentReceiptRow | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [attachments, setAttachments] = useState<PaymentReceiptAttachment[]>(
    [],
  );
  const [attachmentBusy, setAttachmentBusy] = useState(false);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .receipts(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
        sort: "-created_at",
        page,
        size: PAGE_SIZE,
      })
      .then((response) => {
        setRows(response.items);
        setTotal(response.total);
        setSelectedId((current) =>
          current != null && response.items.some((row) => row.id === current)
            ? current
            : null,
        );
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Không tải được phiếu thu.",
        ),
      )
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    load();
  }, [eventTick, load]);

  useEffect(() => {
    if (!focusQuery) return;
    setQ(focusQuery);
    setStatusFilter("all");
    setPage(1);
  }, [focusQuery]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const openSource = (row: PaymentReceiptRow) => {
    if (row.source_type === "purchase_refund" && row.payment_voucher_code) {
      navigate("ke-toan-phieu-chi", { focusVoucherQuery: row.payment_voucher_code });
      return;
    }
    if (row.source_type === "order_deposit" && row.order_id) {
      navigate("don-hang-ban", { openOrderId: row.order_id });
      return;
    }
    if (row.source_type === "sales_invoice" && row.order_id) {
      navigate("don-hang-ban", { openOrderId: row.order_id });
    }
  };
  const selectedReceiptId = selected?.id ?? null;
  /** Đóng popup rồi mới mở form — không chồng hai lớp cửa sổ. */
  function closeDetailThen(action: () => void) {
    setSelectedId(null);
    action();
  }

  useEffect(() => {
    if (!token || selectedReceiptId == null) {
      setAttachments([]);
      return;
    }
    let cancelled = false;
    api.accounting
      .receiptAttachments(token, selectedReceiptId)
      .then((response) => {
        if (!cancelled) setAttachments(response.items);
      })
      .catch(() => {
        if (!cancelled) setAttachments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token, selectedReceiptId]);

  function startPrint(row: PaymentReceiptRow) {
    if (!printReceipt(row))
      setError(
        "Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.",
      );
  }

  async function uploadAttachments(list: FileList | null) {
    if (!token || selectedReceiptId == null || !list?.length) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      for (const file of Array.from(list)) {
        await api.accounting.uploadReceiptAttachment(
          token,
          selectedReceiptId,
          file,
        );
      }
      const response = await api.accounting.receiptAttachments(
        token,
        selectedReceiptId,
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

  async function removeAttachment(attachment: PaymentReceiptAttachment) {
    if (!token || selectedReceiptId == null) return;
    setAttachmentBusy(true);
    setError(null);
    try {
      await api.accounting.deleteReceiptAttachment(
        token,
        selectedReceiptId,
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

  async function openEdit(row: PaymentReceiptRow) {
    if (!token) return;
    if (!row.payment_voucher_id) {
      setError("Phiếu thu này không có phiếu chi nguồn để sửa ở form thu hoàn.");
      return;
    }
    setBusy(true);
    try {
      const voucher = await api.accounting.voucher(
        token,
        row.payment_voucher_id,
      );
      setEditState({ voucher, receipt: row });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không tải được phiếu chi nguồn.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmReceived() {
    if (!token || !marking) return;
    if (marking.receipt_method === "bank_transfer" && !bankReference.trim()) {
      setError("Thu qua ngân hàng phải có mã giao dịch hoặc số báo có.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.markReceiptReceived(
        token,
        marking.id,
        bankReference.trim() || null,
      );
      setMarking(null);
      setBankReference("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Không xác nhận được phiếu thu.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmCancel() {
    if (!token || !cancelling) return;
    if (!cancelReason.trim()) {
      setError("Vui lòng nhập lý do hủy.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.cancelReceipt(
        token,
        cancelling.id,
        cancelReason.trim(),
      );
      setCancelling(null);
      setCancelReason("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không hủy được phiếu thu.",
      );
    } finally {
      setBusy(false);
    }
  }

  function actions(row: PaymentReceiptRow) {
    return (
      <div className="acct-actions">
        {canExport && (
          <Button variant="ghost" onClick={() => startPrint(row)}>
            In phiếu
          </Button>
        )}
        {canApprove &&
          row.status === "waiting_receipt" &&
          row.source_type === "purchase_refund" && (
          <Button
            variant="ghost"
            onClick={() => closeDetailThen(() => openEdit(row))}
            disabled={busy}
          >
            Sửa
          </Button>
        )}
        {canMarkReceived && row.status === "waiting_receipt" && (
          <Button
            variant="accent"
            onClick={() =>
              closeDetailThen(() => {
                setMarking(row);
                setBankReference("");
              })
            }
          >
            Xác nhận đã thu
          </Button>
        )}
        {canCancel &&
          (row.status === "waiting_receipt" ||
            ((row.source_type === "other" || row.source_type === "sales_invoice") && row.status === "received")) && (
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
        <h1 className="md-page__title">Phiếu thu</h1>
        <p className="md-page__sub">
          Ghi nhận các khoản tiền vào công ty: thu cọc đơn bán, thu hóa đơn,
          thu hoàn từ phiếu chi và các khoản thu khác phát sinh độc lập.
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
            placeholder="Tìm PT, hóa đơn, đơn bán, PC, người nộp..."
          />
          {/* <Button type="submit" variant="ghost">
            Tìm
          </Button> */}
        </form>
        <div className="acct-toolbar__filters">
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
            <Button variant="primary" onClick={() => setCreatingOther(true)}>
              + Tạo phiếu thu
            </Button>
          )}
        </div>
      </section>
      <section className="card md-page__tablewrap acct-list">
        <table className="md-page__table">
          <thead>
            <tr>
              {/* KHÔNG còn cột "Thao tác": bấm vào DÒNG mở drawer chi tiết, mọi thao tác nằm ở
                  chân drawer (24/08/2026 — gộp thao tác vào bản ghi). */}
              <th>Mã phiếu thu</th>
              <th>Người nộp</th>
              <th>Người lập</th>
              <th>Lập lúc</th>
              <th className="acct-amount-cell">Số tiền</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "130px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "140px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                </tr>
              ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={6}>
                  Chưa có phiếu thu phù hợp. Có thể tạo phiếu thu trực tiếp tại đây,
                  hoặc lập từ đơn bán/phiếu chi nguồn khi phát sinh nghiệp vụ.
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((row) => (
                <tr
                  key={row.id}
                  className={
                    row.id === selected?.id ? "purchase__row--selected" : ""
                  }
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="acct-code-cell">
                    <strong>{row.code}</strong>
                    <div className="purchase__source-codes">
                      {sourceCode(row) ? (
                        <>
                          <CodeLink
                            code={sourceCode(row)!}
                            onOpen={() => openSource(row)}
                            title={`Mở ${sourceLabel(row)}`}
                          />
                          <small>
                            {sourceLabel(row)}
                            {row.source_type === "sales_invoice" && row.order_code ? ` · Đơn ${row.order_code}` : ""}
                          </small>
                        </>
                      ) : (
                        <span>{sourceLabel(row)}</span>
                      )}
                    </div>
                  </td>
                  <td
                    className="acct-supplier-cell"
                    title={`${row.payer_name} · ${methodText(row)}`}
                  >
                    {row.payer_name}
                  </td>
                  <td className="acct-user-cell">
                    <div title={row.created_by_name ?? undefined}>
                      {row.created_by_name || "—"}
                    </div>
                  </td>
                  <td className="acct-time-cell">
                    {fmtDateTime(row.created_at)}
                  </td>
                  <td className="acct-amount-cell">
                    <strong>{money(row.amount_vnd)}</strong>
                    {row.currency !== "VND" && (
                      <small>
                        {originalMoney(row.amount, row.currency)}
                      </small>
                    )}
                  </td>
                  <td>
                    <span
                      className={`acct-voucher-status acct-voucher-status--${STATUS_META[row.status].tone}`}
                    >
                      {STATUS_META[row.status].label}
                    </span>
                    {row.status === "received" &&
                      row.attachment_count === 0 && (
                        <span className="acct-missing-doc">
                          Thiếu chứng từ
                        </span>
                      )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {!loading && (
          <div className="md-page__pager">
            <span>{total} phiếu thu</span>
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
        )}
      </section>
      {selected && (
        <DetailModal
          kicker="Phiếu thu"
          title={selected.code}
          subtitle={selected.doc_no ? `Số phiếu: ${selected.doc_no}` : undefined}
          badge={
            <div className="acct-status-stack">
              <span
                className={`acct-voucher-status acct-voucher-status--${STATUS_META[selected.status].tone}`}
              >
                {STATUS_META[selected.status].label}
              </span>
              {selected.status === "received" &&
                selected.attachment_count === 0 && (
                  <span className="acct-missing-doc">Thiếu chứng từ</span>
                )}
            </div>
          }
          footer={actions(selected)}
          onClose={() => setSelectedId(null)}
        >
          <dl className="purchase__facts">
            <div>
              <dt>Nguồn thu</dt>
              <dd>{sourceLabel(selected)}</dd>
            </div>
            {sourceCode(selected) && (
              <div>
                <dt>Mã nguồn</dt>
                <dd>
                  <CodeLink
                    code={sourceCode(selected)!}
                    onOpen={() => openSource(selected)}
                  />
                </dd>
              </div>
            )}
            {selected.purchase_request_code && (
              <div>
                <dt>Đơn mua hàng</dt>
                <dd>{selected.purchase_request_code}</dd>
              </div>
            )}
            {selected.source_type === "sales_invoice" && selected.order_code && (
              <div>
                <dt>Đơn bán nguồn</dt>
                <dd>
                  <CodeLink
                    code={selected.order_code}
                    onOpen={() => openSource(selected)}
                  />
                </dd>
              </div>
            )}
            <div>
              <dt>Đối tượng</dt>
              <dd>{sourceName(selected)}</dd>
            </div>
            <div>
              <dt>Ngày thu</dt>
              <dd>{fmtDate(selected.receipt_date)}</dd>
            </div>
            <div>
              <dt>Người nộp</dt>
              <dd>{selected.payer_name}</dd>
            </div>
            <div>
              <dt>Hình thức</dt>
              <dd>{methodText(selected)}</dd>
            </div>
            <div>
              <dt>Người lập</dt>
              <dd>{selected.created_by_name || "—"}</dd>
            </div>
            <div>
              <dt>Lập lúc</dt>
              <dd>{fmtDateTime(selected.created_at)}</dd>
            </div>
            {selected.received_at && (
              <div>
                <dt>Đã thu lúc</dt>
                <dd>
                  {fmtDateTime(selected.received_at)}
                  {selected.received_by_name
                    ? ` · ${selected.received_by_name}`
                    : ""}
                </dd>
              </div>
            )}
          </dl>
          <div className="acct-purpose">
            <span>Nội dung thu</span>
            <strong>{selected.content}</strong>
          </div>
          <div className="acct-voucher-amount">
            <span>Số tiền quy đổi</span>
            <strong>{money(selected.amount_vnd)}</strong>
            {selected.currency !== "VND" && (
              <small>
                {originalMoney(selected.amount, selected.currency)} · tỷ giá{" "}
                {selected.exchange_rate}
              </small>
            )}
          </div>
          {selected.receipt_method === "bank_transfer" && (
            <div className="acct-account-pair">
              <div>
                <span>Tài khoản nhận</span>
                <strong>{selected.company_account_holder}</strong>
                <small>
                  {selected.company_account_number} ·{" "}
                  {selected.company_bank_name}
                </small>
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
              Chứng từ minh chứng đã thu
            </span>
            {attachments.length === 0 && (
              <small className="acct-attachments__empty">
                Chưa có file đính kèm.
                {selected.status === "received" &&
                  " Phiếu đã thu — cần bổ sung biên nhận/ảnh minh chứng."}
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
                <span>Thêm ảnh biên nhận / PDF (tối đa 10 MB)</span>
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
          {selected.note && (
            <div className="purchase__note">{selected.note}</div>
          )}
          {selected.cancel_reason && (
            <div className="banner banner--error">
              Lý do hủy: {selected.cancel_reason}
            </div>
          )}
        </DetailModal>
      )}

      {editState && (
        <PaymentReceiptDialog
          key={editState.receipt.id}
          voucher={editState.voucher}
          receipt={editState.receipt}
          onClose={() => setEditState(null)}
          onSaved={() => {
            setEditState(null);
            load();
          }}
        />
      )}
      {creatingOther && (
        <OtherReceiptDialog
          onClose={() => setCreatingOther(false)}
          onSaved={() => {
            setCreatingOther(false);
            load();
          }}
        />
      )}
      {marking && (
        <div className="acct-modal" role="dialog" aria-modal="true">
          <div className="acct-modal__box">
            <header className="acct-modal__head">
              <h2>Xác nhận đã thu {marking.code}</h2>
              <button
                type="button"
                className="acct-modal__x"
                onClick={() => setMarking(null)}
              >
                ×
              </button>
            </header>
            <div className="acct-modal__body">
              <p>
                Số tiền: <strong>{money(marking.amount_vnd)}</strong> — người
                nộp: <strong>{marking.payer_name}</strong>
              </p>
              {marking.receipt_method === "bank_transfer" && (
                <label className="acct-field">
                  <span>
                    Mã giao dịch / Số báo có <b>*</b>
                  </span>
                  <input
                    autoFocus
                    className="input"
                    value={bankReference}
                    onChange={(event) => setBankReference(event.target.value)}
                  />
                </label>
              )}
            </div>
            <footer className="acct-modal__foot">
              <Button variant="ghost" onClick={() => setMarking(null)}>
                Hủy
              </Button>
              <Button
                variant="accent"
                loading={busy}
                onClick={confirmReceived}
              >
                Xác nhận đã thu
              </Button>
            </footer>
          </div>
        </div>
      )}
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
                Hủy phiếu thu
              </Button>
            </footer>
          </div>
        </div>
      )}
    </main>
  );
}
