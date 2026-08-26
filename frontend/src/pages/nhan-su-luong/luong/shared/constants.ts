// Hằng/mã dùng chung của màn Lương (tách từ pages/LuongPage.tsx).

/** Mã khoản "Hoa hồng kinh doanh" — CÓ CỘT RIÊNG, không nằm trong "Thưởng" (24/08/2026).
 *  Trùng `COMPONENT_CODE_HOA_HONG` ở BE (`models/payroll.py`). */
export const MA_HOA_HONG = "hoa_hong_kd";

/** 2 khoản "mở" seed sẵn cho khoản lặt vặt (thưởng nóng) — đưa LÊN ĐẦU dropdown khoản phát
 *  sinh để không ai phải đẻ một danh mục mới dùng đúng một lần rồi bỏ. */
export const OPEN_COMPONENT_CODES = ["thu_nhap_khac_ct", "thu_nhap_khac_mt"];
