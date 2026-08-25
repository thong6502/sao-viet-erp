// Hai hộp xác nhận của màn Phiếu thu: XÁC NHẬN ĐÃ THU và HỦY PHIẾU
// (tách từ pages/PaymentReceiptsPage.tsx). Giữ NGUYÊN thứ tự mount như bản gốc.
import type { Dispatch, SetStateAction } from "react";
import type { PaymentReceiptRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { money } from "../../../../utils/format";

export function ReceiptConfirmModals({
  marking,
  setMarking,
  bankReference,
  setBankReference,
  busy,
  confirmReceived,
  cancelling,
  setCancelling,
  cancelReason,
  setCancelReason,
  confirmCancel,
}: {
  marking: PaymentReceiptRow | null;
  setMarking: Dispatch<SetStateAction<PaymentReceiptRow | null>>;
  bankReference: string;
  setBankReference: Dispatch<SetStateAction<string>>;
  busy: boolean;
  confirmReceived: () => Promise<void>;
  cancelling: PaymentReceiptRow | null;
  setCancelling: Dispatch<SetStateAction<PaymentReceiptRow | null>>;
  cancelReason: string;
  setCancelReason: Dispatch<SetStateAction<string>>;
  confirmCancel: () => Promise<void>;
}) {
  return (
    <>
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
    </>
  );
}
