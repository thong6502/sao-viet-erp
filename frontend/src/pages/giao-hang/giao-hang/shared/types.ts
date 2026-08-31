// Kiểu dùng chung của màn Giao hàng (tách từ pages/GiaoHangPage.tsx).
export type TabId = "ke-hoach" | "cho-len-ke-hoach" | "nhan-vien";

/** Một dòng hàng còn phải giao TRONG PHẠM VI một yêu cầu. */
export interface DongConLai {
  order_line_id: number;
  mo_ta: string | null;
  don_vi_tinh: string | null;
  con: number;
}
