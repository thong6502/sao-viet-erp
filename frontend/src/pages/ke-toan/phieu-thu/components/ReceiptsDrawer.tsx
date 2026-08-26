// Drawer CHI TIẾT một phiếu thu (tách từ pages/PaymentReceiptsPage.tsx).
import type { Dispatch, ReactNode, SetStateAction } from "react";
import {
  assetUrl,
  type PaymentReceiptAttachment,
  type PaymentReceiptRow,
} from "../../../../api/client";
import { CodeLink } from "../../../../components/CodeLink";
import {
  fmtDate,
  fmtDateTime,
  money,
  originalMoney,
} from "../../../../utils/format";
import { STATUS_META } from "../shared/constants";
import {
  methodText,
  sourceCode,
  sourceLabel,
  sourceName,
} from "../shared/helpers";

export function ReceiptsDrawer({
  selected,
  setSelectedId,
  canApprove,
  openSource,
  attachments,
  attachmentBusy,
  uploadAttachments,
  removeAttachment,
  actions,
}: {
  selected: PaymentReceiptRow;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  canApprove: boolean;
  openSource: (row: PaymentReceiptRow) => void;
  attachments: PaymentReceiptAttachment[];
  attachmentBusy: boolean;
  uploadAttachments: (list: FileList | null) => Promise<void>;
  removeAttachment: (attachment: PaymentReceiptAttachment) => Promise<void>;
  actions: (row: PaymentReceiptRow) => ReactNode;
}) {
  const footer = actions(selected);
  return (
    <div className="rc-drawer__scrim" onClick={() => setSelectedId(null)}>
      <aside
        className="rc-drawer purchase__drawer-780 acct-pt-drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={selected.code}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Phiếu thu</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{selected.code}</h2>
                <div className="acct-status-stack">
                  <span
                    className={`acct-pt__state acct-pt__state--${STATUS_META[selected.status].tone}`}
                  >
                    <i className="acct-pt__dot" aria-hidden="true" />
                    {STATUS_META[selected.status].label}
                  </span>
                  {selected.status === "received" &&
                    selected.attachment_count === 0 && (
                      <span className="acct-pt__flag">
                        <i className="acct-pt__dot" aria-hidden="true" />
                        Thiếu chứng từ
                      </span>
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
        </div>
        <div className="rc-drawer__body acct-pt__body">
      <dl className="purchase__facts">
        {selected.doc_no && (
          <div>
            <dt>Số chứng từ</dt>
            <dd>{selected.doc_no}</dd>
          </div>
        )}
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
        </div>
        {footer && <div className="purchase__drawer-footer">{footer}</div>}
      </aside>
    </div>
  );
}
