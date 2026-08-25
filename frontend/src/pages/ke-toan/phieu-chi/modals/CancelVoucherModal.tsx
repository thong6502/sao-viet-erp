// Hộp HỦY PHIẾU CHI (bắt lý do) — tách từ pages/PaymentVouchersPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PaymentVoucherRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";

export function CancelVoucherModal({
  cancelling,
  setCancelling,
  cancelReason,
  setCancelReason,
  busy,
  confirmCancel,
}: {
  cancelling: PaymentVoucherRow;
  setCancelling: Dispatch<SetStateAction<PaymentVoucherRow | null>>;
  cancelReason: string;
  setCancelReason: Dispatch<SetStateAction<string>>;
  busy: boolean;
  confirmCancel: () => Promise<void>;
}) {
  return (
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
  );
}
