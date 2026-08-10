import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icons";
import "./empty-state.css";

/** Ba ca của một danh sách rỗng — KHÁC NHAU, đừng gộp.
 *
 *  `dang-tai` : đã gọi máy chủ, chưa có trả lời.
 *  `rong`     : máy chủ trả lời rồi, đúng là không có gì.
 *  `loi`      : gọi hỏng (mất mạng, máy chủ chết, hết hạn đăng nhập).
 *
 *  Vì sao phải tách: trước 08/08/2026 nhiều màn gộp `loi` vào `rong` nên khi backend chết, bảng in
 *  "Chưa có yêu cầu nào" — hệ NÓI SAI SỰ THẬT, người dùng tưởng sạch việc rồi bỏ đi. Đúng sự cố
 *  ngày 05/08/2026. Gộp `dang-tai` vào `rong` thì nhẹ hơn nhưng vẫn xấu: mỗi lần tải bảng chớp một
 *  nhịp "chưa có gì" rồi mới ra dữ liệu. */
export type TrangThaiRong = "dang-tai" | "rong" | "loi";

export interface EmptyStateProps {
  trangThai?: TrangThaiRong;
  /** Icon minh hoạ cho ca `rong`. Ca `dang-tai` và `loi` dùng icon riêng, không nhận ở đây. */
  icon?: IconName;
  /** Câu chính của ca `rong`. Dùng động từ "Chưa có…", KHÔNG dùng "Không có…" — xem ghi chú dưới. */
  title?: string;
  sub?: string;
  /** Nút gợi ý việc tiếp theo ở ca `rong` (vd "Xoá bộ lọc", "Tạo yêu cầu đầu tiên"). */
  action?: ReactNode;
  /** Câu lỗi thật từ máy chủ. Chỉ dùng cho ca `loi`. */
  loi?: string | null;
  /** Bấm để gọi lại. Thiếu hàm này thì ca `loi` không có nút — người dùng phải tự F5. */
  onThuLai?: () => void;
  /** Bỏ viền + nền, dùng khi đã nằm trong khung có viền sẵn (vd trong ô của bảng). */
  inline?: boolean;
}

/** "Chưa có" chứ không phải "Không có".
 *
 *  "Không có" nghe như một phán quyết (sẽ không bao giờ có); "Chưa có" đúng sự thật hơn — dữ liệu
 *  chưa được nhập, và thường người đang đọc chính là người sẽ nhập. Chốt cho toàn hệ. */
export function EmptyState({
  trangThai = "rong",
  icon = "box",
  title,
  sub,
  action,
  loi,
  onThuLai,
  inline,
}: EmptyStateProps) {
  const cls = `empty-state${inline ? " empty-state--inline" : ""}`;

  if (trangThai === "dang-tai") {
    return (
      <div className={cls} aria-busy="true">
        <Icon name="clock" size={40} />
        <p className="empty-state__title">Đang tải…</p>
      </div>
    );
  }

  if (trangThai === "loi") {
    return (
      <div className={`${cls} empty-state--loi`} role="alert">
        <Icon name="alert" size={40} />
        <p className="empty-state__title">Không đọc được dữ liệu</p>
        {/* Hiện NGUYÊN VĂN câu lỗi của máy chủ. Nuốt đi rồi in câu chung chung thì người dùng
            không phân biệt được "mất mạng" với "hết hạn đăng nhập" — hai việc phải xử khác nhau. */}
        <p className="empty-state__sub">
          {loi || "Máy chủ không trả lời. Kiểm tra đường mạng rồi thử lại."}
        </p>
        {onThuLai && (
          <button type="button" className="btn btn--ghost" onClick={onThuLai}>
            Thử lại
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={cls}>
      <Icon name={icon} size={44} />
      <p className="empty-state__title">{title ?? "Chưa có dữ liệu"}</p>
      {sub && <p className="empty-state__sub">{sub}</p>}
      {action}
    </div>
  );
}

/** Bản dùng TRONG `<tbody>`: tự bọc `<tr><td colSpan>`.
 *
 *  `colSpan` phải khớp số cột ĐANG hiện — có bảng ẩn/hiện cột theo quyền (vd cột Thao tác chỉ hiện
 *  khi có quyền sửa), nên truyền biểu thức chứ đừng gõ số cứng. Lệch là ô rỗng thụt hẳn một cột. */
export function EmptyRow({
  colSpan,
  ...props
}: EmptyStateProps & { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="empty-state__cell">
        <EmptyState {...props} inline />
      </td>
    </tr>
  );
}
