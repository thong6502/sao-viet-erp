// Kiểu dùng chung của màn Giao hàng (tách từ pages/GiaoHangPage.tsx).
import type { DeliveryTrip } from "../../../../api/client";

export type TabId = "ke-hoach" | "cho-len-ke-hoach" | "nhan-vien";

/** Một dòng của bảng = MỘT YÊU CẦU, không phải một chuyến. */
export interface DongKeHoach {
  /** Chuyến MỚI NHẤT — nguồn của mọi cột hiện trên dòng và của mọi nút thao tác. */
  moi: DeliveryTrip;
  /** Tổng số lần giao đã thực hiện cho yêu cầu này. */
  /** TỔNG km cả các lần — PRD §9: lần 1 thất bại 18km + lần 2 thành công 22km = 40km. */
  tongKm: number;
}

/** Một dòng hàng còn phải giao TRONG PHẠM VI một yêu cầu. */
export interface DongConLai {
  order_line_id: number;
  mo_ta: string | null;
  don_vi_tinh: string | null;
  con: number;
}
