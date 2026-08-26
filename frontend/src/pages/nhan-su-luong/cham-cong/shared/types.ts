// Kiểu dùng chung của màn Chấm công (tách từ pages/ChamCongPage.tsx).
import { SHIFT_TONES } from "./constants";

export type Tab =
  | "me"
  | "my-timesheet"
  | "di-muon"
  | "locations"
  | "khai-ca"
  | "lich-le"
  | "logs"
  | "timesheet"
  | "yeu-cau";

export type PillO = { text: string; tone: string; title: string };
export type ONgay = {
  /** class phụ nối sau `cc-month-cell` (màu nền ô) */
  variant: string;
  timeRange: string;
  statusLabel: string;
  /** "→ tính 4 công" — rỗng nếu ngày này không có hệ số */
  gain: string;
  gainClass: string;
  pills: PillO[];
  /** Tên CA của ngày (vd "HC", "Ca 1") — máy chủ đã phân sẵn (`day.shift_name`), gán ở Khai ca →
   *  Phân ca tháng. Rỗng ⇒ ngày không có ca (nghỉ theo lịch / ngoài lịch phân). */
  caLabel: string;
};

export type DongDacBiet = {
  ngay: number;
  loai: string;
  ten: string;
  cong: number;
  quyDoi: number;
  tone: string;
};

export type ShiftTone = (typeof SHIFT_TONES)[number];

export interface ShiftMeta {
  id: number;
  code: string;
  tone: ShiftTone;
  name: string;
  title: string;
}
