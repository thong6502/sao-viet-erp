// ĐƠN VỊ TỐC ĐỘ của máy — ô chọn bày MỌI đơn vị trong danh mục Đơn vị & quy đổi.
//
import type { Row } from "../types";


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
