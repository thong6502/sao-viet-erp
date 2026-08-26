// Hộp TỪ CHỐI đơn mua hàng — tách từ pages/AccountingPurchaseInboxPage.tsx.
// Vỏ dùng KHUÔN DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner`) thay `acct-modal`
// nền trắng giữa màn — chủ chốt 26/08/2026: "sao mỗi nơi một màu". Đây là HỘP XÁC NHẬN (không
// có dữ liệu dài để mất) nên scrim và Esc đóng được bình thường; form nhập liệu thì KHÔNG.
import { useEffect } from "react";
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
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setRejecting(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setRejecting]);

  return (
    <div className="rc-drawer__scrim" onClick={() => setRejecting(null)}>
      <aside
        className="rc-drawer purchase__drawer-640"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Từ chối ${rejecting.code}`}
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Từ chối đơn</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">{rejecting.code}</h2>
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={() => setRejecting(null)}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>{rejecting.supplier_name || "Chưa chọn"}</span>
          </div>
        </div>
        <div className="rc-drawer__body">
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
        <div className="purchase__drawer-footer">
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
        </div>
      </aside>
    </div>
  );
}
