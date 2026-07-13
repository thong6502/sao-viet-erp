import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type PaymentReceiptAttachment,
  type PaymentReceiptRow,
  type PaymentReceiptStatus,
  type PaymentVoucherRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import {
  amountInWords,
  escapeHtml,
  fmtDate,
  fmtDateTime,
  money,
  originalMoney,
} from "../utils/format";
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

/** In Phiếu thu ra cửa sổ mới (A4) — mirror printVoucher của phiếu chi. */
function printReceipt(row: PaymentReceiptRow): boolean {
  const win = window.open("", "_blank", "width=980,height=760");
  if (!win) return false;
  const isBank = row.receipt_method === "bank_transfer";
  const receiveBlock = isBank
    ? `<section class="accounts"><div><h3>Tài khoản nhận tiền</h3><p><b>${escapeHtml(row.company_account_holder)}</b></p><p>${escapeHtml(row.company_account_number)}</p><p>${escapeHtml(row.company_bank_name)} · ${escapeHtml(row.company_bank_branch)}</p></div></section>`
    : `<section class="accounts"><div><h3>Nhập quỹ tiền mặt</h3><p>Người nộp: <b>${escapeHtml(row.payer_name)}</b></p></div></section>`;
  win.document
    .write(`<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>PHIẾU THU ${escapeHtml(row.code)}</title><style>
    @page{size:A4;margin:16mm}*{box-sizing:border-box}body{font:13px Arial,sans-serif;color:#171713;margin:0}header{display:flex;justify-content:space-between;border-bottom:2px solid #171713;padding-bottom:12px}.brand{font-weight:700}.muted{color:#6f6c64}h1{text-align:center;font-size:24px;margin:24px 0 5px}h2{text-align:center;font:700 14px monospace;margin:0 0 22px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 26px}.label{display:block;font-size:10px;text-transform:uppercase;color:#77736a;font-weight:700;margin-bottom:4px}.purpose{margin:18px 0;padding:12px;border:1px solid #cfcac0}.amount{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}.amount div{padding:14px;background:#f3f1eb}.amount strong{display:block;font-size:20px;margin-top:5px}.words{padding:12px;border:1px solid #cfcac0;margin-bottom:16px}.accounts{display:grid;grid-template-columns:1fr;gap:14px;margin-top:16px}.accounts>div{border:1px solid #cfcac0;padding:12px}.accounts h3{font-size:12px;text-transform:uppercase;margin:0 0 10px}.accounts p{margin:5px 0}.refs{margin-top:18px;border-top:1px solid #cfcac0;padding-top:12px}.status{font-weight:700;text-transform:uppercase}@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  </style></head><body>
    <header><div><div class="brand">Sao Việt Nhật ERP</div><div class="muted">Chứng từ từ phân hệ Kế toán</div></div><div><div>Ngày in: ${escapeHtml(fmtDate(new Date().toISOString()))}</div><div class="muted">Lập lúc: ${escapeHtml(fmtDateTime(row.created_at))}</div><div class="status">${escapeHtml(STATUS_META[row.status].label)}</div></div></header>
    <h1>PHIẾU THU</h1><h2>${escapeHtml(row.code)}</h2>
    <section class="grid"><div><span class="label">Ngày thu</span>${escapeHtml(fmtDate(row.receipt_date))}</div><div><span class="label">Người nộp tiền</span>${escapeHtml(row.payer_name)}</div><div><span class="label">Nhà cung cấp</span>${escapeHtml(row.supplier_name)}</div><div><span class="label">Hình thức</span>${escapeHtml(methodText(row))}</div><div><span class="label">Phiếu chi nguồn</span>${escapeHtml(row.payment_voucher_code)}</div><div><span class="label">PMH nguồn</span>${escapeHtml(row.purchase_request_code)}</div></section>
    <section class="purpose"><span class="label">Nội dung thu</span><b>${escapeHtml(row.content)}</b></section>
    <section class="amount"><div><span class="label">Số tiền nguyên tệ</span><strong>${escapeHtml(originalMoney(row.amount, row.currency))}</strong></div><div><span class="label">Quy đổi VND / tỷ giá</span><strong>${escapeHtml(money(row.amount_vnd))} · ${escapeHtml(row.exchange_rate)}</strong></div></section>
    <section class="words"><span class="label">Số tiền quy đổi bằng chữ</span>${escapeHtml(amountInWords(row.amount_vnd))}</section>
    ${receiveBlock}
    <section class="refs"><span class="label">Chứng từ tham chiếu</span>Mã giao dịch: ${escapeHtml(row.bank_reference || "—")}</section>
  </body></html>`);
  win.document.close();
  win.focus();
  window.setTimeout(() => win.print(), 250);
  return true;
}

export function PaymentReceiptsPage({
  navigate,
  focusQuery = null,
}: {
  navigate: NavigateFn;
  /** Liên thông từ trang Phiếu chi: lọc theo mã PC/UNC khi mở trang. */
  focusQuery?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canApprove = can("ke_toan", "approve");
  const canMarkReceived = can("ke_toan", "manage_status");
  const canCancel = can("ke_toan", "cancel");
  const canExport = can("ke_toan", "export");
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
            : (response.items[0]?.id ?? null),
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
    if (!focusQuery) return;
    setQ(focusQuery);
    setStatusFilter("all");
    setPage(1);
  }, [focusQuery]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? rows[0] ?? null,
    [rows, selectedId],
  );
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const openVoucher = (code: string) =>
    navigate("ke-toan-phieu-chi", { focusVoucherQuery: code });
  const selectedReceiptId = selected?.id ?? null;

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
        {canApprove && row.status === "waiting_receipt" && (
          <Button variant="ghost" onClick={() => openEdit(row)} disabled={busy}>
            Sửa
          </Button>
        )}
        {canMarkReceived && row.status === "waiting_receipt" && (
          <Button
            variant="accent"
            onClick={() => {
              setMarking(row);
              setBankReference("");
            }}
          >
            Xác nhận đã thu
          </Button>
        )}
        {canCancel && row.status === "waiting_receipt" && (
          <Button
            variant="danger"
            onClick={() => {
              setCancelling(row);
              setCancelReason("");
            }}
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
          Ghi nhận tiền quay về công ty — tiền chi ra tiêu không hết do NCC
          hoặc nhân viên phụ trách mua nộp lại.
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
            placeholder="Tìm PT, PC, PMH, NCC, người nộp..."
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
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
        </div>
      </section>
      <div className="acct-master-detail">
        <section className="card md-page__tablewrap acct-list">
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Mã phiếu thu</th>
                <th>Người nộp</th>
                <th>Lập lúc</th>
                <th className="acct-amount-cell">Số tiền</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={5}>Đang tải...</td>
                </tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    Chưa có phiếu thu phù hợp. Lập phiếu thu từ trang Phiếu chi
                    / UNC — nút "Lập phiếu thu" trên phiếu đã chi.
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
                        <CodeLink
                          code={row.payment_voucher_code}
                          onOpen={openVoucher}
                        />
                      </div>
                    </td>
                    <td
                      className="acct-supplier-cell"
                      title={`${row.payer_name} · ${methodText(row)}`}
                    >
                      {row.payer_name}
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
        </section>
        <aside className="purchase__detail">
          {!selected ? (
            <div className="purchase__empty-detail">
              Chọn một phiếu thu để xem chi tiết.
            </div>
          ) : (
            <>
              <div className="purchase__detail-head">
                <div>
                  <p className="eyebrow">Phiếu thu</p>
                  <h2>{selected.code}</h2>
                </div>
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
              </div>
              <dl className="purchase__facts">
                <div>
                  <dt>Phiếu chi nguồn</dt>
                  <dd>
                    <CodeLink
                      code={selected.payment_voucher_code}
                      onOpen={openVoucher}
                    />
                  </dd>
                </div>
                <div>
                  <dt>PMH nguồn</dt>
                  <dd>{selected.purchase_request_code}</dd>
                </div>
                <div>
                  <dt>Nhà cung cấp</dt>
                  <dd>{selected.supplier_name}</dd>
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
              {actions(selected)}
            </>
          )}
        </aside>
      </div>

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
