// Cho ô trong bảng / khối chỉ đọc của drawer MỞ SANG MÀN KHÁC (vd mã đơn ở Thành phẩm → Đơn hàng
// bán). Đi context chứ không thêm tham số cho `render` vì config là dữ liệu, còn `render(r, extra)`
// đã dùng tham số thứ hai. `CatalogListPage` cấp `navigate` của AppShell; `CatalogDrawer` bọc lại
// để hỏi "bỏ thay đổi?" trước khi rời màn. Không có (màn dựng trong test) ⇒ `undefined`, ô tự hiện
// chữ thường.
import { createContext, useContext } from "react";
import type { NavigateFn } from "../../components/AppShell";

export const DieuHuongDanhMuc = createContext<NavigateFn | undefined>(undefined);

export function useDieuHuongDanhMuc(): NavigateFn | undefined {
  return useContext(DieuHuongDanhMuc);
}
