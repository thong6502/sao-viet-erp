// Một dòng bảng "Đề nghị cập nhật hồ sơ" (tách từ pages/HoSoCuaToiPage.tsx).
import type { UpdateRequest } from "../../../../api/client";
import { Icon } from "../../../../components/Icons";
import { cfgReq, fmtDate, fmtDateTime, tomTatChanges } from "../shared/helpers";

/** MỘT DÒNG bảng. Cả hàng bấm được bằng chuột, nhưng đường bàn phím là `<button>` THẬT trong ô
 *  "Nội dung" — dán `role="button"` lên `<tr>` là xoá vai "row", trình đọc màn hình mất cấu trúc
 *  bảng. Ô thao tác chặn nổi bọt, không thì một cú bấm "Hủy" mở cả popup lẫn hộp xác nhận. */
export function ReqRow({ req, onXem, onHuy }: { req: UpdateRequest; onXem: () => void; onHuy: () => void }) {
  const cfg = cfgReq(req.status);
  const { ngan, du } = tomTatChanges(req.changes);
  return (
    <tr
      className={`mine__reqrow${req.status === "cancelled" ? " mine__reqrow--mo" : ""}`}
      onClick={onXem}
    >
      <td className="mine__reqcol-date" title={fmtDateTime(req.created_at)}>{fmtDate(req.created_at)}</td>
      <td className="mine__reqcol-st">
        <span className={`badge-sem ${cfg.cls}`}>
          <Icon name={cfg.icon} size={11} />
          <span className="mine__badge-du">{cfg.label}</span>
          <span className="mine__badge-ngan">{cfg.ngan}</span>
        </span>
      </td>
      <td className="mine__reqcell-noidung">
        <button
          type="button" className="mine__reqopen" title={du}
          aria-label={`Mở đề nghị gửi ${fmtDate(req.created_at)} — ${ngan}, ${cfg.label}`}
          onClick={onXem}
        >
          {ngan}
        </button>
        <span className="mine__reqsub">{fmtDate(req.created_at)}</span>
      </td>
      <td className="mine__reqcol-who">
        {req.status === "pending" ? (
          <span className="mine__reqwho--wait">Đang chờ HCNS</span>
        ) : (
          <>
            {/* `decided_at` của đơn tự rút là giờ NGƯỜI GỬI rút — đừng in "Duyệt bởi" ở ca đó. */}
            <span>{req.status === "cancelled" ? "Bạn rút lại" : (req.decided_by_name ?? "HCNS")}</span>
            {req.decided_at && <span className="mine__reqsub mine__reqsub--luon">{fmtDate(req.decided_at)}</span>}
          </>
        )}
      </td>
      <td className="mine__reqcol-act" onClick={(e) => e.stopPropagation()}>
        {req.status === "pending" ? (
          <button type="button" className="mine__reqhuy" onClick={onHuy}>
            <Icon name="x" size={12} /> Hủy
          </button>
        ) : null}
      </td>
    </tr>
  );
}
