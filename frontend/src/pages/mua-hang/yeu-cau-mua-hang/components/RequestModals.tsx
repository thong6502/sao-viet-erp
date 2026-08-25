// Cụm HỘP THOẠI xác nhận của màn Yêu cầu mua hàng: huỷ cả phiếu · bỏ một món
// (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import type { DepartmentPurchaseRequestRow } from "../../../../api/client";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import { dongSong } from "../shared/helpers";
import type { BoMonState } from "../shared/types";

export function RequestModals({
  selected,
  canceling,
  setCanceling,
  confirmCancel,
  boMon,
  setBoMon,
  confirmBoMon,
  actionBusy,
}: {
  selected: DepartmentPurchaseRequestRow | null;
  canceling: DepartmentPurchaseRequestRow | null;
  setCanceling: Dispatch<SetStateAction<DepartmentPurchaseRequestRow | null>>;
  confirmCancel: () => Promise<void>;
  boMon: BoMonState | null;
  setBoMon: Dispatch<SetStateAction<BoMonState | null>>;
  confirmBoMon: () => Promise<void>;
  actionBusy: string | null;
}) {
  return (
    <>
      <ConfirmDialog
        open={Boolean(canceling)}
        title="Hủy yêu cầu mua hàng?"
        message={canceling ? `Yêu cầu ${canceling.code} sẽ chuyển sang trạng thái Đã hủy.` : undefined}
        danger
        confirmLabel="Hủy yêu cầu"
        busy={canceling ? actionBusy === `cancel:${canceling.id}` : false}
        onConfirm={confirmCancel}
        onCancel={() => setCanceling(null)}
      />

      {/* Cùng khuôn với hộp "Hủy yêu cầu" ngay trên: hộp XÁC NHẬN, không phải modal biểu mẫu —
          đây là một câu hỏi có/không kèm ô lý do. `confirmDisabled` khoá nút cho tới khi có lý do
          (máy chủ trả 422 nếu trống, đừng bắt người dùng bấm mới biết). */}
      <ConfirmDialog
        open={Boolean(boMon)}
        title="Bỏ món này khỏi yêu cầu?"
        message={
          boMon && selected
            ? // Bỏ món CUỐI CÙNG là huỷ luôn cả yêu cầu — đây là chỗ duy nhất người dùng thấy
              // được điều đó trước khi bấm.
              dongSong(selected).length <= 1
              ? `"${boMon.line.item_name}" là món cuối còn lại — bỏ nó là cả yêu cầu ${selected.code} chuyển sang Đã hủy.`
              : `"${boMon.line.item_name}" sẽ không còn được mua nữa. Các món khác trong yêu cầu vẫn chạy tiếp.`
            : undefined
        }
        danger
        confirmLabel="Bỏ món"
        busy={boMon ? actionBusy === `line-cancel:${boMon.line.id}` : false}
        error={boMon?.error ?? null}
        confirmDisabled={!boMon?.reason.trim()}
        onConfirm={confirmBoMon}
        onCancel={() => setBoMon(null)}
      >
        <label className="purchase__field">
          <span>Lý do bỏ (bắt buộc)</span>
          <textarea
            className="input purchase__textarea"
            value={boMon?.reason ?? ""}
            onChange={(e) =>
              setBoMon((current) =>
                current ? { ...current, reason: e.target.value, error: null } : current,
              )
            }
          />
        </label>
      </ConfirmDialog>
    </>
  );
}
