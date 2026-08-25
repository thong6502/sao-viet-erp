// Drawer CHI TIẾT một phiếu chi (tách từ pages/PaymentVouchersPage.tsx).
import type { Dispatch, ReactNode, SetStateAction } from "react";
import {
  assetUrl,
  type PaymentVoucherAttachment,
  type PaymentVoucherRow,
} from "../../../../api/client";
import { CodeLink } from "../../../../components/CodeLink";
import {
  amountInWords,
  fmtDate,
  fmtDateTime,
  money,
  originalMoney,
} from "../../../../utils/format";
import {
  SOURCE_LABELS,
  STAGE_LABELS,
  STATUS_META,
} from "../shared/list-constants";

export function VouchersDrawer({
  selected,
  setSelectedId,
  canApprove,
  openYcmh,
  openReceipts,
  attachments,
  attachmentBusy,
  uploadAttachments,
  removeAttachment,
  actions,
}: {
  selected: PaymentVoucherRow;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  canApprove: boolean;
  openYcmh: (code: string) => void;
  openReceipts: (query: string) => void;
  attachments: PaymentVoucherAttachment[];
  attachmentBusy: boolean;
  uploadAttachments: (list: FileList | null) => Promise<void>;
  removeAttachment: (attachment: PaymentVoucherAttachment) => Promise<void>;
  actions: (row: PaymentVoucherRow) => ReactNode;
}) {
  return (
    <div className="rc-drawer__scrim" onClick={() => setSelectedId(null)}>
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={selected.code}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">
                {selected.voucher_type === "cash" ? "Phiếu chi" : "Ủy nhiệm chi"}
              </span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{selected.code}</h2>
                <div className="acct-status-stack">
                  <span
                    className={`acct-voucher-status acct-voucher-status--${STATUS_META[selected.status].tone}`}
                  >
                    {STATUS_META[selected.status].label}
                  </span>
                  {selected.status === "paid" &&
                    selected.attachment_count === 0 && (
                      <span className="acct-missing-doc">Thiếu chứng từ</span>
                    )}
                </div>
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={() => setSelectedId(null)}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>{selected.supplier_name}</span>
            <span className="purchase__hero-dot">•</span>
            <span>Ngày {fmtDate(selected.voucher_date)}</span>
            <span className="purchase__hero-dot">•</span>
            <span>{money(selected.amount_vnd)}</span>
            <span className="purchase__hero-dot">•</span>
            <span>Người lập {selected.created_by_name || "—"}</span>
            {selected.doc_no && (
              <>
                <span className="purchase__hero-dot">•</span>
                <span>Số CT {selected.doc_no}</span>
              </>
            )}
          </div>
        </div>
        <div className="rc-drawer__body">
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
        </div>
        <div className="purchase__drawer-footer">{actions(selected)}</div>
      </aside>
    </div>
  );
}
