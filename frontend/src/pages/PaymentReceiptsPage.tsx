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
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { VOUCHER_PAGE_LABEL } from "../constants/features";
import { fmtDate, fmtDateTime, money, originalMoney } from "../utils/format";
import { printTT200 } from "../utils/printTT200";
import { OrderDepositQueue } from "./OrderDepositQueue";
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
function printReceipt(row: PaymentReceiptRow): boolean {
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
      { label: "Phiếu chi nguồn", value: row.payment_voucher_code },
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
  const canApprove = can("ke_toan", "approve");
  const canMarkReceived = can("ke_toan", "manage_status");
  const canCancel = can("ke_toan", "cancel");
  const canExport = can("ke_toan", "export");
  // B3: quyền "Ghi phiếu thu cọc" (module Đơn hàng bán) — chỉ người này thấy hàng chờ + nghe popup cọc.
  const canRecordDeposit = can("don_hang_ban", "record_deposit");
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
  const openVoucher = (code: string) =>
    navigate("ke-toan-phieu-chi", { focusVoucherQuery: code });
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
        {canCancel && row.status === "waiting_receipt" && (
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
          Ghi nhận tiền quay về công ty — tiền chi ra tiêu không hết do NCC
          hoặc nhân viên phụ trách mua nộp lại.
        </p>
      </header>
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}
      {canRecordDeposit && <OrderDepositQueue />}
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
      <section className="card md-page__tablewrap acct-list">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã phiếu thu</th>
              <th>Người nộp</th>
              <th>Người lập</th>
              <th>Lập lúc</th>
              <th className="acct-amount-cell">Số tiền</th>
              <th>Trạng thái</th>
              <th className="acct-action-cell">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7}>Đang tải...</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={7}>
                  Chưa có phiếu thu phù hợp. Lập phiếu thu từ trang{" "}
                  {VOUCHER_PAGE_LABEL} — nút "Lập phiếu thu" trên phiếu đã chi.
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
