// Mảnh dùng chung của màn Tài sản & CCDC: ô nhập tiền, cách in số, badge, khoảng ngày hợp lệ.
// Để riêng vì cả bốn khung (danh sách · ghi tăng · biến động · kiểm kê) đều đụng tới — chép mỗi
// nơi một bản thì con số 3.300.000.000 hiện ba kiểu khác nhau trên cùng một màn.
import type { ReactNode } from "react";

/** "3.300.000.000" — KHÔNG kèm "đ": bảng có cả cột tiền thì mỗi ô một chữ "đ" là nhiễu, đơn vị
 *  nói một lần ở tiêu đề cột. Chỗ nào đứng lẻ thì tự thêm. */
export function tien(v: number | null | undefined): string {
  return Math.round(Number(v ?? 0)).toLocaleString("vi-VN");
}

/** "3.300.000.000 đ" — dùng khi con số đứng một mình, không nằm trong cột. */
export function tienDon(v: number | null | undefined): string {
  return `${tien(v)} đ`;
}

/** "10/03/2026" — đọc thẳng chuỗi ISO, KHÔNG qua `new Date()` (chuỗi "2026-03-10" bị hiểu là UTC
 *  midnight nên ở múi giờ âm lùi mất một ngày; đây là ngày chứng từ, lệch một ngày là sai kỳ). */
export function ngay(v?: string | null): string {
  if (!v) return "—";
  const [y, m, d] = v.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : v;
}

/** Khoảng ngày chấp nhận được của mọi ô `type="date"` trong module.
 *
 *  Vì sao phải chặn hai đầu: ô ngày của trình duyệt cho gõ tay, và người dùng đã từng gõ ra năm
 *  SÁU chữ số — request bay lên rồi ăn 422 câm, không ô nào đỏ, họ ngồi bấm Lưu lại mãi. Chặn
 *  bằng `min`/`max` thì trình duyệt tự chặn ngay tại ô. Trên 1990 vì tài sản mua trước đó thì
 *  cũng đã khấu hao hết từ lâu; dưới +10 năm để còn ghi ngày dự kiến đưa vào dùng. */
export const NGAY_MIN = "1990-01-01";
export const NGAY_MAX = `${new Date().getFullYear() + 10}-12-31`;
export const HOM_NAY = new Date().toISOString().slice(0, 10);

/** Ô nhập TIỀN: gõ số trần, hiện có dấu chấm nghìn.
 *
 *  Không dùng `type="number"` cho tiền: nguyên giá một máy in là mười chữ số, nhìn "3300000000"
 *  thì không ai đếm nổi có mấy số 0 — mà đếm sai một chữ số ở đây là sai nguyên giá gấp mười.
 *  Con số gửi lên vẫn là số nguyên, mọi ký tự không phải chữ số đều bị loại tại chỗ gõ. */
export function OTien({
  value,
  onChange,
  disabled,
  placeholder,
  className,
  ariaLabel,
}: {
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <input
      className={`rc-input ts-num ${className ?? ""}`}
      type="text"
      inputMode="numeric"
      disabled={disabled}
      placeholder={placeholder}
      aria-label={ariaLabel}
      value={value ? tien(value) : ""}
      onChange={(e) => {
        const so = e.target.value.replace(/\D/g, "");
        onChange(so ? Number(so) : 0);
      }}
    />
  );
}

/** Badge tròn dùng cho loại · trạng thái tài sản · trạng thái kỳ · trạng thái đợt kiểm kê.
 *  `he` là tiền tố lớp CSS (`ts-badge--<he>`), khai màu ở `tai-san.css`. */
export function Badge({ he, children }: { he: string; children: ReactNode }) {
  return <span className={`ts-badge ts-badge--${he}`}>{children}</span>;
}
