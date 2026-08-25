// Nhãn trạng thái + ô tình trạng dòng của màn Yêu cầu mua hàng
// (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type {
  DepartmentPurchaseRequestLineOut,
  DepartmentPurchaseWorkflowStatus,
  PurchaseRequestStatus,
} from "../../../../api/client";
import { PHIEU_STATUS_META, SOURCE_STATUS_META } from "../shared/constants";

export function SourceStatusBadge({
  status,
}: {
  status: DepartmentPurchaseWorkflowStatus;
}) {
  const meta = SOURCE_STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>
      <span className={`purchase__status-dot purchase__status-dot--${meta.tone}`} />
      {meta.label}
    </span>
  );
}

export function StatusBadgePhieu({ status }: { status: PurchaseRequestStatus }) {
  const meta = PHIEU_STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>{meta.label}</span>
  );
}

/**
 * Tình trạng của MỘT DÒNG vật tư.
 *
 * Ba ca phải hiện KHÁC nhau, gộp lại là nói dối:
 *   1. Chưa ai lập phiếu cho yêu cầu này ⇒ "Chờ thu mua lập phiếu".
 *   2. Đã có phiếu nhưng dòng này không nối được ⇒ phiếu lập TRƯỚC 05/08/2026, hồi đó chưa có nối
 *      dòng ↔ dòng. Nói thẳng "chưa rõ, xem danh sách phiếu bên dưới" — KHÔNG đoán theo tên hàng,
 *      đoán trượt thì im lặng hiện sai và không ai biết.
 *   3. Nối được ⇒ hiện trạng thái phiếu, kèm cảnh báo nếu NCC giao thiếu hoặc phiếu bị từ chối.
 */
export function LineFulfilmentCell({
  line,
  coPhieu,
}: {
  line: DepartmentPurchaseRequestLineOut;
  coPhieu: boolean;
}) {
  if (!line.fulfilment) {
    return coPhieu ? (
      <small>Chưa rõ — phiếu lập trước khi hệ ghi nhận theo dòng</small>
    ) : (
      <small>Chờ thu mua lập phiếu</small>
    );
  }
  const f = line.fulfilment;
  const nhan = f.received_quantity ?? f.ordered_quantity;
  const thieu = f.purchase_status === "received" && nhan < f.ordered_quantity;
  // "Giao một phần" mà không nói giao BAO NHIÊU thì bộ phận không biết còn thiếu mấy để tính
  // đường xoay — đó là cả lý do của việc này. Hiện số ở cả hai bậc: đang giao dở và đã nhận đủ.
  const dangGiaoDo = f.purchase_status === "partially_received";
  return (
    <>
      <StatusBadgePhieu status={f.purchase_status} />
      <br />
      <small>
        {f.purchase_code}
        {f.ordered_quantity !== line.quantity && (
          // Bộ phận xin 1.000 tờ mà NCC bán theo ram thì thu mua đổi đơn vị — hiện cả hai con số
          // ngay tại dòng, thay vì để hai nơi rời nhau không ai đối chiếu.
          <> · mua {f.ordered_quantity.toLocaleString("vi-VN")} {f.ordered_unit}</>
        )}
        {(f.purchase_status === "received" || dangGiaoDo) && (
          <>
            {" "}
            · nhận {nhan.toLocaleString("vi-VN")}
            {dangGiaoDo ? `/${f.ordered_quantity.toLocaleString("vi-VN")}` : ""}{" "}
            {f.ordered_unit}
          </>
        )}
      </small>
      {thieu && <small className="pay-short">Giao thiếu so với số đặt</small>}
      {dangGiaoDo && nhan < f.ordered_quantity && (
        <small className="pay-short">
          Còn {(f.ordered_quantity - nhan).toLocaleString("vi-VN")} {f.ordered_unit} chưa về
        </small>
      )}
      {f.purchase_status === "rejected" && (
        <small className="pay-short">Cần lập phiếu lại cho dòng này</small>
      )}
    </>
  );
}
