// Hộp TỪ CHỐI đơn mua hàng — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { PurchaseRequestRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";

export function RejectModal({
  rejecting,
  setRejecting,
  rejectReason,
  setRejectReason,
  busy,
  reject,
}: {
  rejecting: PurchaseRequestRow;
  setRejecting: Dispatch<SetStateAction<PurchaseRequestRow | null>>;
  rejectReason: string;
  setRejectReason: Dispatch<SetStateAction<string>>;
  busy: string | null;
  reject: () => Promise<void>;
}) {
  return (
    <div className="acct-modal" role="dialog" aria-modal="true">
      <div className="acct-modal__box">
        <header className="acct-modal__head">
          <h2>Từ chối {rejecting.code}</h2>
          <button
            type="button"
            className="acct-modal__x"
            onClick={() => setRejecting(null)}
          >
            ×
          </button>
        </header>
        <div className="acct-modal__body">
          <label className="acct-field">
            <span>
              Lý do từ chối <b>*</b>
            </span>
            <textarea
              autoFocus
              className="input acct-textarea"
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
            />
          </label>
        </div>
        <footer className="acct-modal__foot">
          <Button variant="ghost" onClick={() => setRejecting(null)}>
            Hủy
          </Button>
          <Button
            variant="danger"
            loading={busy === `reject:${rejecting.id}`}
            onClick={reject}
          >
            Từ chối đơn
          </Button>
        </footer>
      </div>
    </div>
  );
}
