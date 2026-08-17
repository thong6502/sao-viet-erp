// NHÃN TỔ đọc được cho một dòng "Công việc khoán".
//
// `piece_rates.group_name` là nhãn tổ lưu ngay trên dòng. Dòng khai từ 17/08/2026 mang đúng TÊN TỔ
// (service suy từ `department_id` mỗi lần ghi, mg `0210` đã đồng bộ dòng cũ có tổ), nhưng dòng đời
// đầu chưa gắn tổ nào thì còn giữ MÃ tổ cũ dạng `to_boi` — không dịch thì bảng hiện "to_boi" giữa
// một cột toàn tên tiếng Việt.
//
// Ở file riêng vì hai chỗ cùng cần: màn danh mục (`rebuildCatalogConfigs`) và panel "Đơn giá khoán
// của tổ" trong Cấu hình lương (`components/KhoanRatesEditor`). Chép hai bản là sớm muộn một bên
// thêm nhãn mà bên kia không có.

/** Mã tổ đời đầu → tên đọc được. ĐÓNG: chỉ những mã đã nằm trong dữ liệu, không đoán thêm. */
const TO_DOI_CU: Record<string, string> = {
  to_boi: "Tổ Bồi",
  to_can_phu: "Tổ Cán/Phủ",
  to_cat: "Tổ Cắt",
  may_in_5mau: "Máy in 5 màu",
  may_in_2mau: "Máy in 2 màu",
  to_thanh_pham: "Tổ Thành phẩm",
};

/** `"to_boi"` → `"Tổ Bồi"`; tên tổ thật thì trả nguyên. Rỗng → `"—"` (dòng chưa gắn tổ). */
export function nhanTo(groupName: unknown): string {
  const g = String(groupName ?? "").trim();
  if (!g) return "—";
  return TO_DOI_CU[g] ?? g;
}
