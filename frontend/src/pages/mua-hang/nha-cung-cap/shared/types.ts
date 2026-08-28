// Kiểu dùng chung của màn Nhà cung cấp (tách từ pages/SuppliersPage.tsx).
// Hai kiểu dưới đây viết lại ĐÚNG HÌNH của hai ô state trong shell (`nhapKetQua` ·
// `filteredFormItems`) để tab con khai props được — shell vẫn giữ nguyên văn khai báo `useState`
// của nó, TypeScript khớp theo cấu trúc.
import type {
  SupplierItemImportError,
  SupplierItemInput,
} from "../../../../api/client";

/** Khoá sắp xếp của bảng NCC. `rating`/`-rating` là SAO đánh giá (máy tự tính) — NCC "Chưa đánh
 *  giá" luôn nằm CUỐI ở cả hai chiều, backend lo phần đó. `name` là mặc định khi tắt sắp xếp sao. */
export type SortNcc = "name" | "rating" | "-rating";

/** Lọc theo sao: `null` = không lọc, số = chỉ lấy NCC có sao trung bình ≥ số đó. */
export type LocSaoNcc = number | null;

/** Kết quả một lượt nhập Excel bảng giá vật tư (mới nạp vào form, chưa vào DB). */
export interface NhapKetQua {
  them: number;
  capNhat: number;
  errors: SupplierItemImportError[];
}

/** Dòng bảng giá kèm CHỈ SỐ GỐC trong `form.items` — lọc theo ô tìm nội bộ tab 2 vẫn phải sửa
 *  đúng dòng gốc, nên chỉ số đi kèm chứ không tính lại từ danh sách đã lọc. */
export interface FormItemRow {
  item: SupplierItemInput;
  originalIndex: number;
}
