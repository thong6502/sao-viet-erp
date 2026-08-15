// BARREL — mặt tiền của phân hệ "Cấu hình danh mục".
//
// Ruột đã tách ra `pages/danh-muc/` (15/08/2026): file này trước đó là 2 657 dòng gồm cả trang
// danh sách, drawer, 10 loại ô, tab nhật ký và ô công thức. Giữ lại cái tên ở đây để 8 chỗ đang
// import (kể cả 4 file test) không phải sửa một dòng nào.
//
// Chỗ dùng MỚI thì import thẳng từ `pages/danh-muc/...`, đừng đi vòng qua barrel này.
export { CatalogListPage as RebuildCatalogPage } from "./danh-muc/CatalogListPage";
export { FormulaField } from "./danh-muc/fields/FormulaField";
export { ClockIcon } from "./danh-muc/icons";
export { tongChuanBi } from "./danh-muc/fields/ChuanBiKhoan";
export { isMayIn } from "./danh-muc/types";
export { traBien, useBienCongThuc } from "./danh-muc/bienCongThuc";
export type { BienCongThuc, TraBien } from "./danh-muc/bienCongThuc";
export type {
  CatalogConfig, ChuanBiKhoanRow, ColumnDef, FacetDef, FieldDef, HangMucConRow, LichBaoTriRow,
} from "./danh-muc/types";
