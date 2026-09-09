// ĐƠN VỊ TỐC ĐỘ của máy — ô chọn bày MỌI đơn vị trong danh mục Đơn vị & quy đổi.
//
// Dùng ở HAI chỗ: ô "Đơn vị tốc độ" của drawer Máy, và cột "Đơn vị" của Năng suất khoán trong
// bảng đầu việc của drawer Công đoạn.
import { useMemo } from "react";

import { Select, type SelectOption } from "../../../components/Select";
import type { Row } from "../types";


// Nhãn đơn vị tốc độ của MỘT máy ("tờ/h"). Server đã tra sẵn tên thật (`don_vi_toc_do_ten`, xem
// `may_thiet_bi_service.gan_ten_don_vi`) nên chỉ việc đọc; mã (`to_gio`) là đường lui cho máy khai
// bằng đơn vị nay đã gỡ khỏi danh mục.
//
// Đặt ở đây chứ không để mỗi màn một bản: bảng danh sách Máy và bảng "Máy chạy được công đoạn này"
// cùng bày đơn vị của cùng một máy — hai bản sao của luật ghép "/h" là hai màn nói lệch nhau ngay
// lần đầu có người sửa một bên.
export function nhanDonViTocDo(r: Row): string {
  const ten = String(r.don_vi_toc_do_ten ?? "").trim();
  if (ten) return `${ten}/h`;
  const ma = String(r.don_vi_toc_do ?? "").trim();
  if (!ma) return "";
  return `${ma.endsWith("_gio") ? ma.slice(0, -4) : ma}/h`;
}


export function DonViTocDoField({
  value, onChange, donViList,
}: {
  value: string;
  onChange: (v: string) => void;
  donViList: Row[];
}) {
  // Mọi đơn vị đang dùng của danh mục — thêm/bớt/đổi tên quản MỘT chỗ ở màn Đơn vị & quy đổi.
  // Giá trị lưu vẫn là `<mã>_gio` để khớp máy đã khai + engine Lệnh SX.
  //
  // Danh sách này dài (~25 đơn vị) nên ô có GÕ TÌM gần đúng: nhãn hiện tên ("hộp/h") còn mã
  // (`hop`) đẩy vào `search` — người khai quen gõ mã vẫn ra, mà cột hẹp không phải cõng thêm chữ.
  const opts = useMemo<SelectOption<string>[]>(() => {
    // Dòng rỗng phải CÒN: bỏ trống là một khai báo thật ("lùi về đơn vị của đơn giá khoán"), không
    // có nó thì chọn nhầm một lần là hết đường quay lại trống.
    const ds: SelectOption<string>[] = [{ value: "", label: "— chọn —" }];
    for (const d of donViList.filter((d) => d.active !== false)) {
      ds.push({ value: `${d.ma}_gio`, label: `${d.ten}/h`, search: `${d.ma} ${d.ma}_gio` });
    }
    // Máy khai từ trước bằng mã nay không còn bày (đơn vị bỏ tick / đơn vị cũ) vẫn phải hiện ra —
    // bỏ qua là mở form thấy trống, bấm Lưu một cái là xoá mất khai báo đang đúng.
    if (value !== "" && !ds.some((d) => d.value === value)) {
      const nhanCu = value.endsWith("_gio") ? `${value.slice(0, -4)}/h` : value;
      ds.push({ value, label: `${nhanCu} — khai cũ`, search: value });
    }
    return ds;
  }, [donViList, value]);

  return (
    <Select
      options={opts}
      value={value}
      onChange={(v) => onChange(v ?? "")}
      placeholder="— chọn —"
      ariaLabel="Đơn vị tốc độ"
      searchable
      searchPlaceholder="Gõ tên hoặc mã đơn vị…"
      portal
      className="rc-input"
    />
  );
}
