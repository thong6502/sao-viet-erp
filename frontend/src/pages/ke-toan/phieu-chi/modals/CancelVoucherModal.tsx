// Hộp HỦY PHIẾU CHI (bắt lý do) — tách từ pages/PaymentVouchersPage.tsx.
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là HỘP XÁC NHẬN (không
// có dữ liệu dài để mất) nên scrim và Esc đóng được bình thường; form nhập liệu thì KHÔNG.
import { useEffect } from "react";
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
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setCancelling(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setCancelling]);

  return (
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
              <span className="purchase__hero-kicker">Hủy chứng từ</span>
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
            Hủy chứng từ
          </Button>
        </div>
      </aside>
    </div>
  );
}
