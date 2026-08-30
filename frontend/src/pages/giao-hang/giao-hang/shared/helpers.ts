// Hàm dùng chung của màn Giao hàng (tách từ pages/GiaoHangPage.tsx).
import { NHAN_TRANG_THAI_CHUYEN } from "./constants";

/** Nhãn trạng thái của MỘT chuyến — MỘT hàm cho MỌI chỗ render.
 *
 *  Kho lập phiếu xong ⇒ hàng đã soạn, tài xế tới lấy được, nên chữ đổi thành "Kho đã chuẩn bị
 *  xong" (chủ chốt 20/08/2026). Kho KHÔNG bấm gì trên màn này — cờ `kho_da_lap_phieu` đọc ngược
 *  từ sổ kho.
 *
 *  Viết thành hàm vì bảng chuyến render ở HAI chỗ (tab Đơn giao hàng và tab Yêu cầu giao); chép
 *  hai bản là sớm muộn hai chỗ nói hai kiểu. */
export function nhanChuyen(t: { trang_thai: string; kho_da_lap_phieu?: boolean }): string {
  if (t.trang_thai === "dang_chuan_bi" && t.kho_da_lap_phieu) return "Kho đã chuẩn bị xong";
  return NHAN_TRANG_THAI_CHUYEN[t.trang_thai] ?? t.trang_thai;
}

export function toneChuyen(tt: string): "on" | "off" | "warn" {
  if (tt === "thanh_cong") return "on";
  if (tt === "that_bai" || tt === "da_huy") return "off";
  return "warn";
}
