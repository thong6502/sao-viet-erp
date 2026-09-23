import { MonthPicker } from "./MonthPicker";
import "./loc-thang-tao.css";

/** Ô LỌC theo THÁNG TẠO của danh sách đơn (nghỉ phép, tăng ca…) — chủ 23/09/2026: *"lọc theo tháng
 *  là lọc theo ngày tạo nha"*. `value` rỗng = không lọc (xem mọi tháng); có tháng thì hiện nút ✕ để
 *  bỏ lọc, không bắt người dùng đi tìm cách xoá ô tháng. */
export function LocThangTao({
  value,
  onChange,
  disabled,
}: {
  /** `YYYY-MM` hoặc `""` (tất cả). */
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <span className="loc-thang-tao">
      <span className="loc-thang-tao__nhan">Tháng tạo</span>
      <MonthPicker
        value={value}
        onChange={onChange}
        disabled={disabled}
        ariaLabel="Lọc theo tháng tạo"
        nhanTrong="Tất cả các tháng"
      />
      {value && (
        <button
          type="button"
          className="loc-thang-tao__bo"
          onClick={() => onChange("")}
          disabled={disabled}
          aria-label="Bỏ lọc tháng"
          title="Bỏ lọc tháng — xem tất cả"
        >
          ✕
        </button>
      )}
    </span>
  );
}
