// Cụm HỘP THOẠI của màn Mua hàng (tách từ pages/PurchaseRequestsPage.tsx).
// Giữ NGUYÊN THỨ TỰ mount như bản gốc — đây là 7 lớp phủ anh em, đảo chỗ là đảo thứ tự xếp lớp.
// ⚠️ Mọi `onDone`/`onChanged` ở đây đều phải gọi ĐỦ cặp xương sống `updateRow(next)` +
// `loadSources()` — cả hai nhận qua props từ shell, đừng "gọn hoá" bớt một cái.
import type { Dispatch, SetStateAction } from "react";
import type { PurchaseRequestRow } from "../../../../api/client";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import { fmtDate, money } from "../../../../utils/format";
import { DeliveryDialog } from "../modals/DeliveryDialog";
import { InvoiceDialog } from "../modals/InvoiceDialog";
import { ReceiveDialog } from "../modals/ReceiveDialog";
import type {
  CloseModalState,
  DeletingDeliveryState,
  DeliveryModalState,
  ReasonModalState,
  ReceiveModalState,
} from "../shared/types";

export function PurchaseModals({
  actionBusy,
  updateRow,
  loadSources,
  deleting,
  setDeleting,
  confirmDelete,
  reasonModal,
  setReasonModal,
  confirmReason,
  receiveModal,
  setReceiveModal,
  deliveryModal,
  setDeliveryModal,
  invoiceModal,
  setInvoiceModal,
  deletingDelivery,
  setDeletingDelivery,
  confirmXoaDot,
  closeModal,
  setCloseModal,
  confirmDongDon,
}: {
  actionBusy: string | null;
  updateRow: (next: PurchaseRequestRow) => void;
  loadSources: () => void;
  deleting: PurchaseRequestRow | null;
  setDeleting: Dispatch<SetStateAction<PurchaseRequestRow | null>>;
  confirmDelete: () => Promise<void>;
  reasonModal: ReasonModalState | null;
  setReasonModal: Dispatch<SetStateAction<ReasonModalState | null>>;
  confirmReason: () => Promise<void>;
  receiveModal: ReceiveModalState | null;
  setReceiveModal: Dispatch<SetStateAction<ReceiveModalState | null>>;
  deliveryModal: DeliveryModalState | null;
  setDeliveryModal: Dispatch<SetStateAction<DeliveryModalState | null>>;
  invoiceModal: PurchaseRequestRow | null;
  setInvoiceModal: Dispatch<SetStateAction<PurchaseRequestRow | null>>;
  deletingDelivery: DeletingDeliveryState | null;
  setDeletingDelivery: Dispatch<SetStateAction<DeletingDeliveryState | null>>;
  confirmXoaDot: () => Promise<void>;
  closeModal: CloseModalState | null;
  setCloseModal: Dispatch<SetStateAction<CloseModalState | null>>;
  confirmDongDon: () => Promise<void>;
}) {
  return (
    <>
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Xóa phiếu nháp?"
        message={
          deleting
            ? `Phiếu ${deleting.code} sẽ bị xóa khỏi hệ thống.`
            : undefined
        }
        danger
        confirmLabel="Xóa phiếu"
        busy={deleting ? actionBusy === `delete:${deleting.id}` : false}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />

      <ConfirmDialog
        open={Boolean(reasonModal)}
        // Hộp thoại này nay CHỈ dùng cho một việc: HUỶ PHIẾU.
        title="Huỷ phiếu mua hàng?"
        message={
          reasonModal
            ? `Phiếu ${reasonModal.row.code} sẽ dừng hẳn, và yêu cầu của bộ phận quay lại hàng chờ để lập phiếu khác. Không hoàn tác được.`
            : undefined
        }
        danger
        confirmLabel="Huỷ phiếu"
        busy={
          reasonModal
            ? actionBusy === `${reasonModal.kind}:${reasonModal.row.id}`
            : false
        }
        error={reasonModal?.error ?? null}
        onConfirm={confirmReason}
        onCancel={() => setReasonModal(null)}
      >
        <label className="purchase__field">
          <span>
            Lý do huỷ (bắt buộc)
          </span>
          <textarea
            className="input purchase__textarea"
            value={reasonModal?.reason ?? ""}
            onChange={(e) =>
              setReasonModal((current) =>
                current ? { ...current, reason: e.target.value } : current,
              )
            }
          />
        </label>
      </ConfirmDialog>

      {receiveModal && (
        <ReceiveDialog
          row={receiveModal.row}
          mode={receiveModal.mode}
          onClose={() => setReceiveModal(null)}
          onDone={(next) => {
            updateRow(next);
            setReceiveModal(null);
            loadSources();
          }}
        />
      )}

      {deliveryModal && (
        <DeliveryDialog
          key={deliveryModal.delivery?.id ?? "new"}
          row={deliveryModal.row}
          delivery={deliveryModal.delivery}
          onClose={() => setDeliveryModal(null)}
          onDone={(next) => {
            updateRow(next);
            setDeliveryModal(null);
            loadSources();
          }}
          onChanged={(next) => {
            updateRow(next);
            setDeliveryModal((cur) => (cur ? { ...cur, row: next } : cur));
          }}
        />
      )}

      {invoiceModal && (
        <InvoiceDialog
          row={invoiceModal}
          onClose={() => setInvoiceModal(null)}
          onDone={(next) => {
            updateRow(next);
            setInvoiceModal(null);
          }}
        />
      )}

      <ConfirmDialog
        open={Boolean(deletingDelivery)}
        title="Xóa đợt giao?"
        message={
          deletingDelivery
            ? `Đợt ${deletingDelivery.delivery.seq_no} ngày ${fmtDate(
                deletingDelivery.delivery.delivery_date,
              )} — trị giá ${money(deletingDelivery.delivery.amount)}. Công nợ của đơn sẽ giảm đúng số này.`
            : undefined
        }
        danger
        confirmLabel="Xóa đợt giao"
        busy={
          deletingDelivery
            ? actionBusy === `del-dot:${deletingDelivery.delivery.id}`
            : false
        }
        onConfirm={confirmXoaDot}
        onCancel={() => setDeletingDelivery(null)}
      />

      <ConfirmDialog
        open={Boolean(closeModal)}
        title="Đóng đơn (không giao nữa)?"
        message={
          closeModal
            ? `Phiếu ${closeModal.row.code} — chốt số thực nhận bằng số đã giao (${money(
                closeModal.row.gia_tri_da_giao,
              )}). Phần hàng chưa về sẽ không còn được ghi nợ.`
            : undefined
        }
        danger
        confirmLabel="Đóng đơn"
        busy={closeModal ? actionBusy === `close:${closeModal.row.id}` : false}
        error={closeModal?.error ?? null}
        onConfirm={confirmDongDon}
        onCancel={() => setCloseModal(null)}
      >
        <label className="purchase__field">
          <span>Lý do đóng đơn (bắt buộc)</span>
          <textarea
            className="input purchase__textarea"
            placeholder="Ví dụ: NCC báo hết hàng, không giao nốt phần còn lại."
            value={closeModal?.reason ?? ""}
            onChange={(e) =>
              setCloseModal((current) =>
                current ? { ...current, reason: e.target.value } : current,
              )
            }
          />
        </label>
      </ConfirmDialog>
    </>
  );
}
