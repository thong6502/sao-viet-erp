// Hai hộp xác nhận của màn Phiếu thu: XÁC NHẬN ĐÃ THU và HỦY PHIẾU
// (tách từ pages/PaymentReceiptsPage.tsx). Giữ NGUYÊN thứ tự mount như bản gốc.
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là HỘP XÁC NHẬN (không
// có dữ liệu dài để mất) nên scrim và Esc đóng được bình thường; form nhập liệu thì KHÔNG.
import { useEffect } from "react";
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
  // Component này luôn mount (cha render vô điều kiện) nên chỉ nghe Esc khi thật sự có hộp mở,
  // và đóng đúng hộp đang mở.
  const dangMo = marking != null || cancelling != null;
  useEffect(() => {
    if (!dangMo) return;
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (cancelling != null) setCancelling(null);
      else setMarking(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [dangMo, cancelling, setCancelling, setMarking]);

  return (
    <>
    {marking && (
      <div className="rc-drawer__scrim" onClick={() => setMarking(null)}>
        <aside
          className="rc-drawer purchase__drawer-640"
          onClick={(event) => event.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-label={`Xác nhận đã thu ${marking.code}`}
        >
          <div className="purchase__hero-banner">
            <div className="purchase__hero-top">
              <div>
                <span className="purchase__hero-kicker">Xác nhận đã thu</span>
                <div className="purchase__hero-title-row">
                  <h2 className="purchase__hero-code">{marking.code}</h2>
                </div>
              </div>
              <button
                type="button"
                className="purchase__hero-x"
                onClick={() => setMarking(null)}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="rc-drawer__body">
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
          <div className="purchase__drawer-footer">
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
          </div>
        </aside>
      </div>
    )}
    {cancelling && (
      <div className="rc-drawer__scrim" onClick={() => setCancelling(null)}>
        <aside
          className="rc-drawer purchase__drawer-640"
          onClick={(event) => event.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-label={`Hủy ${cancelling.code}`}
        >
          <div className="purchase__hero-banner">
            <div className="purchase__hero-top">
              <div>
                <span className="purchase__hero-kicker">Hủy phiếu thu</span>
                <div className="purchase__hero-title-row">
                  <h2 className="purchase__hero-code">{cancelling.code}</h2>
                </div>
              </div>
              <button
                type="button"
                className="purchase__hero-x"
                onClick={() => setCancelling(null)}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="rc-drawer__body">
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
          <div className="purchase__drawer-footer">
            <Button variant="ghost" onClick={() => setCancelling(null)}>
              Đóng
            </Button>
            <Button variant="danger" loading={busy} onClick={confirmCancel}>
              Hủy phiếu thu
            </Button>
          </div>
        </aside>
      </div>
    )}
    </>
  );
}
