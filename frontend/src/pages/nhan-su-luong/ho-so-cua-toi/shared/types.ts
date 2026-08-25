// Kiểu dùng chung của màn "Hồ sơ của tôi" (tách từ pages/HoSoCuaToiPage.tsx).
import type { PayrollLine, PayrollPeriod } from "../../../../api/client";

// --- Trạng thái tải của MỘT nguồn số liệu ------------------------------------
// Bốn ca phải phân biệt được: đang tải · có số · rỗng thật · LỖI. Gộp "lỗi" vào "rỗng" (kiểu
// `.catch(() => setX([]))`) là để máy nói sai sự thật với người dùng — màn in "chưa có gì"
// trong khi máy chủ đang chết.
export type Tai<T> =
  | { tt: "dang-tai" }
  | { tt: "ok"; du: T }
  | { tt: "rong"; vi_sao: string }
  | { tt: "loi" };

export interface SoPhep { con_lai: number; da_dung: number; han_muc: number; ten: string; them: number }
export interface SoCong { cong: number; chuan: number | null; ngay: number; thang: number }
export interface SoLuong { ky: PayrollPeriod; dong: PayrollLine }

export type ChipTone = "ok" | "warn" | "low" | "info" | "money" | "none";
