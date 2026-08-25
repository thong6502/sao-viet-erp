// Kiểu dùng chung của màn Nhà cung cấp (tách từ pages/SuppliersPage.tsx).
// Ba kiểu dưới đây viết lại ĐÚNG HÌNH của ba ô state trong shell (`quyDoiDong` · `nhapKetQua` ·
// `filteredFormItems`) để tab con khai props được — shell vẫn giữ nguyên văn khai báo `useState`
// của nó, TypeScript khớp theo cấu trúc.
import type {
  SupplierItemImportError,
  SupplierItemInput,
} from "../../../../api/client";

/** Hệ số quy đổi về đơn vị gốc của MỘT dòng bảng giá — chỉ để hiển thị, không lưu. */
export interface QuyDoiDongInfo {
  donViGocTen: string;
  heSoVeGoc: number;
}

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
