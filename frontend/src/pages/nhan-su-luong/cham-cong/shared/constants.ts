// Hằng dùng chung của màn Chấm công (tách từ pages/ChamCongPage.tsx).
import type { HeSoNgay } from "../../../../api/client";

export const FAULT_OPTIONS: { value: string; label: string }[] = [
  { value: "nv_quen", label: "NV quên chấm" },
  { value: "may_hong", label: "Máy hỏng / mất điện" },
  { value: "duyet", label: "Được duyệt (công tác/họp)" },
  { value: "khac", label: "Khác" },
];

export const TIME_HOURS = Array.from({ length: 24 }, (_, index) =>
  String(index).padStart(2, "0"),
);
export const TIME_MINUTES = Array.from({ length: 60 }, (_, index) =>
  String(index).padStart(2, "0"),
);
export const FAULT_LABEL: Record<string, string> = Object.fromEntries(
  FAULT_OPTIONS.map((o) => [o.value, o.label]),
);

/** Hệ số dự phòng khi response chưa có `he_so_ngay` — KHỚP mặc định của `payroll_params`
 *  (`holiday_work_multiplier` 3 ⇒ lễ 1+3 = 4×; `restday_work_multiplier` 2 ⇒ CN 2×).
 *  Chỉ là lưới an toàn: số thật luôn đọc từ máy chủ vì nhà máy khai được ở Cấu hình lương. */
export const HE_SO_NGAY_MAC_DINH: HeSoNgay = { le: 4, nghi_tuan: 2, off1x: 1 };

// --- Mã ca ngắn + màu: SUY DIỄN Ở FE (backend không có cột code/color) -------
// CẤM `signal` (màu lỗi hệ thống) — chỉ 5 họ dưới đây.
export const SHIFT_TONES = ["moss", "amber", "steel", "plum", "rust"] as const;

export const WEEKDAY_NAMES_SHORT = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
