import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type PaymentVoucherAttachment,
  type PaymentVoucherRow,
  type PaymentVoucherStatus,
  type PurchaseRequestRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { CodeLink } from "../components/CodeLink";
import { DetailModal } from "../components/DetailModal";
import { Icon } from "../components/Icons";
import { UNC_ENABLED, VOUCHER_PAGE_LABEL } from "../constants/features";
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

const STATUS_META: Record<
  PaymentVoucherStatus,
  { label: string; tone: string }
> = {
  waiting_payment: { label: "Chờ chi", tone: "waiting" },
  paid: { label: "Đã chi", tone: "paid" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

const STAGE_LABELS = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
} as const;

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
  const canApprove = can("ke_toan", "approve");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const openReceipts = (query: string) =>
    navigate("ke-toan-phieu-thu", { focusReceiptQuery: query });
  const canMarkPaid = can("ke_toan", "manage_status");
  const canCancel = can("ke_toan", "cancel");
  const canExport = can("ke_toan", "export");
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
  const [marking, setMarking] = useState<PaymentVoucherRow | null>(null);
  const [bankReference, setBankReference] = useState("");
  const [cancelling, setCancelling] = useState<PaymentVoucherRow | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [receiptFor, setReceiptFor] = useState<PaymentVoucherRow | null>(null);
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

  async function openEdit(row: PaymentVoucherRow) {
    if (!token) return;
    setBusy(true);
    try {
      const purchase = await api.purchaseRequests.get(
        token,
        row.purchase_request_id,
      );
      setEditState({ voucher: row, purchase });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không tải được PMH nguồn.",
      );
    } finally {
      setBusy(false);
    }
  }

  // async function openTopUp(row: PaymentVoucherRow) {
  //   if (!token) return;
  //   setBusy(true);
  //   setError(null);
  //   try {
  //     const purchase = await api.purchaseRequests.get(
  //       token,
  //       row.purchase_request_id,
  //     );
  //     if (!["approved", "purchased", "received"].includes(purchase.status)) {
  //       setError(
  //         `PMH ${purchase.code} không còn ở trạng thái được lập chứng từ.`,
  //       );
  //       return;
  //     }
  //     if (purchase.available_amount <= 0) {
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

  async function confirmPaid() {
    if (!token || !marking) return;
    if (marking.voucher_type === "bank_transfer" && !bankReference.trim()) {
      setError("UNC phải có mã giao dịch hoặc số báo nợ.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.markVoucherPaid(
        token,
        marking.id,
        bankReference.trim() || null,
      );
      setMarking(null);
      setBankReference("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không xác nhận được chứng từ.",
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
        {canApprove && row.status === "waiting_payment" && (
          <Button
            variant="ghost"
            onClick={() => closeDetailThen(() => openEdit(row))}
            disabled={busy}
          >
            Sửa
          </Button>
        )}
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
        {canMarkPaid && row.status === "waiting_payment" && (
          <Button
            variant="accent"
            onClick={() =>
              closeDetailThen(() => {
                setMarking(row);
                setBankReference("");
              })
            }
          >
            Xác nhận đã chi
          </Button>
        )}
        {canCancel && row.status === "waiting_payment" && (
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
          Theo dõi chứng từ chờ chi, đã chi và truy ngược về PMH cùng YCMH
          nguồn.
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
            placeholder={
              UNC_ENABLED ? "Tìm PC, UNC, PMH, YCMH..." : "Tìm PC, PMH, YCMH..."
            }
          />
          {/* <Button type="submit" variant="ghost">
            Tìm
          </Button> */}
        </form>
        <div className="acct-toolbar__filters">
          {/* Tạm ẩn UNC: chỉ còn một loại thì "Tất cả loại" và "Phiếu chi" ra cùng
              kết quả — bỏ luôn bộ lọc thay vì để một ô vô nghĩa. typeFilter giữ
              "all" nên UNC cũ vẫn nằm trong danh sách. */}
          {UNC_ENABLED && (
            <select
              className="input"
              value={typeFilter}
              onChange={(event) => {
                setTypeFilter(event.target.value);
                setPage(1);
              }}
            >
              <option value="all">Tất cả loại</option>
              <option value="cash">Phiếu chi</option>
              <option value="bank_transfer">Ủy nhiệm chi</option>
            </select>
          )}
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
      <section className="card md-page__tablewrap acct-list acct-list--voucher">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã chứng từ</th>
              <th>Loại</th>
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
                <td colSpan={7}>Chưa có chứng từ phù hợp.</td>
              </tr>
            )}
            {!loading &&
              rows.map((row, rowIndex) => (
                <Fragment key={row.id}>
                  {(rowIndex === 0 ||
                    rows[rowIndex - 1].purchase_request_id !==
                      row.purchase_request_id) && (
                    <tr className="acct-group-row">
                      <td colSpan={7}>
                        <div>
                          <strong>{row.purchase_request_code}</strong>
                          <span
                            className="acct-group-row__supplier"
                            title={row.supplier_name}
                          >
                            {row.supplier_name}
                          </span>
                          <span className="acct-group-row__total">
                            {row.purchase_paid_amount != null && (
                              <>
                                Đã chi:{" "}
                                <b>{money(row.purchase_paid_amount)}</b>
                              </>
                            )}
                            {row.purchase_request_total != null && (
                              <>
                                {row.purchase_paid_amount != null && " / "}
                                Tổng PMH: {money(row.purchase_request_total)}
                              </>
                            )}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                  <tr
                    className={
                      row.id === selected?.id ? "purchase__row--selected" : ""
                    }
                    onClick={() => setSelectedId(row.id)}
                  >
                    <td className="acct-code-cell">
                      <strong>{row.code}</strong>
                    </td>
                    <td>
                      {row.voucher_type === "cash" ? "Phiếu chi" : "UNC"}
                    </td>
                    <td className="acct-user-cell">
                      <div title={row.created_by_name ?? undefined}>
                        {row.created_by_name || "—"}
                      </div>
                    </td>
                    <td className="acct-time-cell">
                      {fmtDateTime(row.created_at)}
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
            <div>
              <dt>Ngày chứng từ</dt>
              <dd>{fmtDate(selected.voucher_date)}</dd>
            </div>
            <div>
              <dt>Đợt thanh toán</dt>
              <dd>{STAGE_LABELS[selected.payment_stage]}</dd>
            </div>
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
      {marking && (
        <div className="acct-modal" role="dialog" aria-modal="true">
          <div className="acct-modal__box">
            <header className="acct-modal__head">
              <h2>Xác nhận đã chi {marking.code}</h2>
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
                Số tiền: <strong>{money(marking.amount_vnd)}</strong>
              </p>
              {marking.voucher_type === "bank_transfer" && (
                <label className="acct-field">
                  <span>
                    Mã giao dịch / Số báo nợ <b>*</b>
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
              <Button variant="accent" loading={busy} onClick={confirmPaid}>
                Xác nhận đã chi
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
                Hủy chứng từ
              </Button>
            </footer>
          </div>
        </div>
      )}
    </main>
  );
}
