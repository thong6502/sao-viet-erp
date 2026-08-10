import { useId, useRef } from "react";
import "./month-picker.css";

/** Ô chọn kỳ (tháng/năm) có nhãn TIẾNG VIỆT.
 *
 *  Vì sao phải tự vẽ nhãn: ô `type="month"` của trình duyệt tự sinh chữ theo ngôn ngữ của MÁY
 *  TÍNH, không theo ngôn ngữ của phần mềm. Máy cài tiếng Anh thì kỳ lương hiện "August 2026" giữa
 *  màn tiếng Việt — kế toán đọc kỳ lương mỗi ngày, đây là chỗ đọc nhầm tháng chứ không phải chuyện
 *  xấu đẹp. Không có cách nào ép ngôn ngữ cho ô gốc, nên giấu nó đi và tự viết nhãn.
 *
 *  Ô gốc VẪN nằm trong cây (chỉ ẩn khỏi mắt) để giữ nguyên bộ chọn lịch quen thuộc, giữ điều khiển
 *  bằng bàn phím và giữ kiểm tra dữ liệu của form. */
export function MonthPicker({
  value,
  onChange,
  disabled,
  className,
  ariaLabel = "Chọn kỳ",
}: {
  /** Dạng `YYYY-MM`. */
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
}) {
  const id = useId();
  const ref = useRef<HTMLInputElement>(null);

  const [nam, thang] = value.split("-");
  const nhan =
    nam && thang ? `Tháng ${Number(thang)} / ${nam}` : "Chọn kỳ";

  return (
    <span className={`month-picker${className ? ` ${className}` : ""}`}>
      <input
        ref={ref}
        id={id}
        type="month"
        className="month-picker__native"
        value={value}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
      />
      {/* Bấm nhãn phải MỞ lịch, không chỉ đặt con trỏ vào ô đang ẩn. `showPicker` chưa có ở mọi
          trình duyệt nên phải bọc try/catch — hỏng thì lùi về focus, người dùng vẫn gõ được. */}
      <label
        htmlFor={id}
        className="month-picker__label"
        onClick={(e) => {
          if (disabled) return;
          const el = ref.current;
          if (!el) return;
          try {
            (el as HTMLInputElement & { showPicker?: () => void }).showPicker?.();
            e.preventDefault();
          } catch {
            el.focus();
          }
        }}
      >
        {nhan}
      </label>
    </span>
  );
}
