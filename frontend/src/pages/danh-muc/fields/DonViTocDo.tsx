// ĐƠN VỊ TỐC ĐỘ của máy — ô chọn bày MỌI đơn vị trong danh mục Đơn vị & quy đổi.
//
// 🔴 BỎ LỌC `dung_lam_toc_do` 15/08/2026 (chủ chốt). Cờ đó **không có ô nào trên màn để bật**: nó
// chỉ được migration 0154 bật sẵn cho 8 mã và seed set theo cùng 8 mã ấy. Nghĩa là nó là một danh
// sách cứng nằm dưới DB — đơn vị người dùng tự khai thì cờ = false vĩnh viễn và KHÔNG BAO GIỜ hiện
// ra ở đây. Khai được đơn vị mà không dùng được nó là đúng thứ module Đơn vị & quy đổi sinh ra để bỏ.
//
// Lịch sử: 04/08 khoá cứng danh sách → 11/08 quay lại nguồn động nhưng lọc theo cờ → 15/08 bỏ nốt
// lọc. Đừng dựng lại bộ lọc nào ở đây: muốn ẩn đơn vị thì bỏ `active` ở màn Đơn vị.
//
// Mã lưu giữ khuôn `<mã đơn vị>_gio` — `lsx_service.ma_don_vi_toc_do` cắt hậu tố để biết tốc độ
// đếm bằng gì. Đơn vị của máy khác đơn vị của bước thì Lệnh SX QUY ĐỔI (cầu quy đổi → công thức của
// đơn vị); quy đổi không được thì thời gian chạy = 0 kèm cảnh báo, không im lặng như trước.
import type { Row } from "../types";

// 🔴 `DON_VI_TOC_DO` (9 mã + nhãn viết tay) GỠ 15/08/2026 — bảng nhãn THỨ HAI. Ô chọn lấy tên từ
// danh mục, cột danh sách đọc `don_vi_toc_do_ten` server tra sẵn. Đừng khai lại bảng nào ở đây.

export function DonViTocDoField({
  value, onChange, donViList,
}: {
  value: string;
  onChange: (v: string) => void;
  donViList: Row[];
}) {
  // Mọi đơn vị đang dùng của danh mục — thêm/bớt/đổi tên quản MỘT chỗ ở màn Đơn vị & quy đổi.
  // Giá trị lưu vẫn là `<mã>_gio` để khớp máy đã khai + engine Lệnh SX.
  const opts = donViList
    .filter((d) => d.active !== false)
    .map((d) => ({ ma: `${d.ma}_gio`, nhan: `${d.ten}/h` }));
  // Máy khai từ trước bằng mã nay không còn bày (đơn vị bỏ tick / đơn vị cũ) vẫn phải hiện ra —
  // bỏ qua là mở form thấy trống, bấm Lưu một cái là xoá mất khai báo đang đúng.
  const laKhaiCu = value !== "" && !opts.some((d) => d.ma === value);
  const nhanCu = value.endsWith("_gio") ? `${value.slice(0, -4)}/h` : value;
  return (
    <select className="rc-input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">— chọn —</option>
      {opts.map((d) => (
        <option key={d.ma} value={d.ma}>{d.nhan}</option>
      ))}
      {laKhaiCu && <option value={value}>{nhanCu} — khai cũ</option>}
    </select>
  );
}
