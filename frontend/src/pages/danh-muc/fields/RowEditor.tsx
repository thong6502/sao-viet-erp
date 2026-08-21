// KHUNG bảng-động dùng chung: tiêu đề cột · dòng "chưa có gì" · nút xoá cuối hàng · nút "＋ Thêm".
//
// Cố ý CHỈ gom phần KHUNG. Ô trong hàng do người gọi tự vẽ (`veHang`) — tổng quát hoá cả ô nữa là
// đẻ ra một ngôn ngữ khai báo thứ hai (kiểu ô · ràng buộc · nhãn lỗi…), đắt hơn hẳn thứ nó thay,
// mà mỗi bảng lại có một kiểu ô riêng: bậc số lượng có nút gạt Tờ/%, khoản chuẩn bị có dòng tổng.
//
// PHẠM VI: hai bảng thật là `Bands` và `ChuanBiKhoan`. `LichBaoTri` KHÔNG dùng khung này — nó
// không phải bảng mà là danh sách THẺ (mỗi gói một `<section>` có chu kỳ, ngày bắt đầu và một
// `<ol>` việc con lồng bên trong). Ép nó vào khung bảng là đổi cả DOM lẫn CSS của một màn đang
// chạy, để lấy về vài dòng — không đáng.
import type { ReactNode } from "react";

import { TrashIcon } from "../icons";

export function RowEditor<T>({
  rows, cot, trong, themNhan, onThem, onXoa, xoaTitle = "Xoá dòng",
  lopHang, khoa, chan, veHang,
}: {
  rows: T[];
  /** Nhãn các cột DỮ LIỆU. Cột nút xoá tự mọc thêm ở cuối, đừng khai. */
  cot: string[];
  /** Câu hiện khi chưa có dòng nào — nói luôn phải bấm nút gì. */
  trong: string;
  themNhan: string;
  onThem: () => void;
  onXoa: (i: number) => void;
  xoaTitle?: string;
  /** Class thêm cho `<tr>` (vd đánh dấu hàng khai sai khoảng). */
  lopHang?: (r: T, i: number) => string | undefined;
  /** Class thêm cho khung ngoài cùng. */
  khoa?: string;
  /** `<tfoot>` tuỳ chọn — vd dòng "Tổng (tự cộng)". */
  chan?: ReactNode;
  /** Các `<td>` của một hàng, KHÔNG gồm ô nút xoá. */
  veHang: (r: T, i: number) => ReactNode;
}) {
  return (
    <div className={`rc-bands${khoa ? ` ${khoa}` : ""}`}>
      <table className="rc-bands__table">
        <thead>
          <tr>{cot.map((c) => <th key={c}>{c}</th>)}<th /></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={cot.length + 1} className="rc-bands__empty">{trong}</td></tr>
          )}
          {rows.map((r, i) => (
            <tr key={i} className={lopHang?.(r, i) || undefined}>
              {veHang(r, i)}
              <td style={{ textAlign: "center" }}>
                <button type="button" className="rc-bands__del" onClick={() => onXoa(i)} title={xoaTitle}>
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
        {chan}
      </table>
      <button type="button" className="rc-bands__add" onClick={onThem}>{themNhan}</button>
    </div>
  );
}
