// Hằng số dùng chung của tab Cấu hình lương (tách từ pages/CauHinhLuongTab.tsx).
import type {
  PayrollParams,
  SalaryComponentKey,
} from "../../../../../api/client";
import type { CompDraft, SubTab } from "./types";

export const SUB_TABS: { key: SubTab; label: string }[] = [
  { key: "cochE", label: "Cơ chế lương theo bộ phận" },
  { key: "danhmuc", label: "Danh mục khoản thu nhập" },
  { key: "phucap", label: "Bảo hiểm & Thuế" },
];

/** 4 thành phần lương khai theo BỘ PHẬN (PRD v2.1). Các khoản phụ cấp (ca · thâm niên) đã
 *  chuyển sang khai TAY ở từng NV — gửi key cũ lên `PUT /dept-components` giờ ăn 422. */

export const COMPONENT_ROWS: {
  key: SalaryComponentKey;
  name: string;
  desc: string;
  /** "money" = có ô tiền · null = chỉ bật/tắt, không có ô giá trị. */
  kind: "money" | null;
  unit: string;
  /** Bật mà bỏ trống ô tiền ⇒ 0 đ (không có mức cấp công ty để rơi xuống). */
  zeroWhenBlank?: boolean;
}[] = [
  {
    key: "chuyen_can",
    name: "Chuyên cần",
    desc: "Công tắc bật/tắt cho cả tổ — TẮT thì không ai trong tổ được cộng, kể cả đã khai tiền. MỨC TIỀN khai ở hồ sơ từng nhân viên (tab Lương nhân viên). Trừ dần theo ngày nghỉ: nghỉ 0,5 ngày −25% · 1 ngày −50% · từ 2 ngày mất hết.",
    kind: null,
    unit: "—",
  },
  {
    key: "luong_khoan",
    name: "Lương khoán / sản lượng",
    // Vế "hiện mục khai ĐƠN GIÁ khoán của tổ ngay dưới" đã BỎ (04/09/2026): panel đó ẩn khỏi màn
    // này (`tabs/CoCheTab.tsx` — cờ `HIEN_DON_GIA_KHOAN`), để nguyên là chỉ người khai xuống một
    // chỗ không còn tồn tại. Trỏ thẳng sang cửa duy nhất còn khai được.
    desc: "Bật khoán sẽ TỰ TẮT Tăng ca (đã khoán không tính tăng ca theo giờ). Đơn giá khoán của tổ khai ở Cấu hình danh mục → Công việc khoán. Tính tiền khoán theo sản lượng nối khi có Lệnh sản xuất.",
    kind: null,
    unit: "—",
  },
  {
    key: "tang_ca",
    name: "Tăng ca",
    desc: "",
    kind: null,
    unit: "—",
  },
];

// --- Helper -----------------------------------------------------------------

export const READONLY_NOTE =
  "Bạn chỉ có quyền XEM cấu hình lương. Cần sửa thì liên hệ quản trị hệ thống.";

export const SAVED_NOTE =
  "Kỳ lương đang ở trạng thái nháp sẽ áp số mới khi bấm “Tính lại”. Kỳ đã chốt / đã chi giữ nguyên số.";

// ============================================================================

export const PARAMS_A = [
  "standard_hours_per_day",
  "probation_ratio",
  "ot_multiplier",
  "ot_multiplier_restday",
  "ot_multiplier_holiday",
  "restday_work_multiplier",
  "holiday_work_multiplier",
  "night_pct",
  "ot_night_extra_pct",
  "adjust_max_per_month",
  "phu_cap_ca_min_cong",
  "com_tang_ca_nguong_phut",
  "com_tang_ca_muc",
  // Trần giờ làm thêm (Đ107) — thiếu hai tên này thì ô có hiện nhưng thanh "Lưu thay đổi"
  // KHÔNG thấy dirty và `pick()` không gửi xuống ⇒ sửa xong bấm lưu vẫn y như cũ.
  "ot_max_minutes_per_month",
  "ot_max_minutes_per_day",
] as const satisfies readonly (keyof PayrollParams)[];

export const PARAMS_INS = [
  "bhxh_rate",
  "bhyt_rate",
  "bhtn_rate",
  "bhxh_rate_er",
  "bhyt_rate_er",
  "bhtn_rate_er",
  "bh_base_cap",
  "bhtn_base_cap",
  "cong_doan_rate",
  "tnld_bnn_rate",
  "phat_cap_pct",
  "bhxh_mien_tu_so_ngay",
] as const satisfies readonly (keyof PayrollParams)[];

export const PARAMS_TAX = [
  "deduction_self",
  "deduction_dependent",
  "pit_flat_rate",
  "pit_flat_threshold",
] as const satisfies readonly (keyof PayrollParams)[];

export const OT_FIELDS: {
  key:
    | "ot_multiplier"
    | "ot_multiplier_restday"
    | "ot_multiplier_holiday"
    | "restday_work_multiplier"
    | "holiday_work_multiplier";
  label: string;
  hint: string;
  floor: number;
}[] = [
  {
    key: "ot_multiplier",
    label: "Tăng ca — ngày thường",
    hint: "Trả theo giờ, trên đơn giá giờ của mức nền.",
    floor: 1.5,
  },
  {
    key: "ot_multiplier_restday",
    label: "Tăng ca — ngày nghỉ tuần",
    hint: "Giờ tăng ca rơi vào ngày nghỉ tuần.",
    floor: 2,
  },
  {
    key: "ot_multiplier_holiday",
    label: "Tăng ca — ngày lễ",
    hint: "Giờ tăng ca rơi vào ngày lễ / Tết.",
    floor: 3,
  },
  {
    key: "restday_work_multiplier",
    label: "Làm nguyên công — ngày nghỉ tuần",
    hint: "Đi làm trọn công vào ngày nghỉ tuần: cộng THÊM phần chênh (hệ số − 100%) vì 100% đã nằm trong lương theo công.",
    floor: 2,
  },
  {
    key: "holiday_work_multiplier",
    label: "Làm nguyên công — ngày lễ",
    hint: "Đi làm trọn công ngày lễ: cộng THÊM TRỌN hệ số này (KHÔNG trừ 100%). Nghỉ lễ ở nhà vẫn có lương 100% (Đ112), đi làm được cộng thêm 300% ⇒ tổng 400%. Khác ngày nghỉ tuần: nghỉ CN ở nhà không có lương nên chỉ tổng 200%.",
    floor: 3,
  },
];

// ============================================================================
// TAB 3 — Bảo hiểm & Thuế
// ============================================================================

// --- Thưởng/phạt TỔ TRƯỞNG theo tỷ lệ hàng lỗi (chủ 29/07/2026) -------------
// "Hàng lỗi khoảng 5% thì thưởng 2% trên tổng, lỗi trên 10% thì bị trừ 10% trên tổng.
//  % này là TIỀN đó nha." → % tính trên TỔNG TIỀN KHOÁN của tổ; dương = thưởng, âm = phạt.
//
// ⚠️ Engine CHƯA áp bảng này (tổng khoán hiện luôn = 0 vì chưa có nguồn sản lượng) — banner
// vàng dưới đây nói thẳng điều đó. ĐỪNG GỠ: khai xong mà tưởng đã chạy là mất niềm tin.

export const NEW_COMPONENT: CompDraft = { name: "", kind: "thu", is_taxable: true };

export const INSURANCE_ROWS: {
  label: string;
  er: "bhxh_rate_er" | "bhyt_rate_er" | "bhtn_rate_er";
  ee: "bhxh_rate" | "bhyt_rate" | "bhtn_rate";
}[] = [
  { label: "BHXH", er: "bhxh_rate_er", ee: "bhxh_rate" },
  { label: "BHYT", er: "bhyt_rate_er", ee: "bhyt_rate" },
  { label: "BHTN", er: "bhtn_rate_er", ee: "bhtn_rate" },
];
