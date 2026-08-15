// Ô TÌM của màn danh mục — MỘT cách dựng cho cả 10 màn.
//
// ⚠️ Placeholder phải giữ nguyên chuỗi `"Tìm mã / tên…"`: `RebuildCatalogPage.test.tsx` bắt ô này
// bằng đúng chuỗi đó (`getByPlaceholderText`). Đổi chữ là đỏ hai test phân trang.
import { SearchIcon, XIcon } from "./icons";

export function OTim({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="rc__search-wrapper">
      <SearchIcon />
      <input
        className="rc__search"
        placeholder="Tìm mã / tên…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {/* Xoá nhanh. Chỉ mọc khi CÓ chữ — nút ✕ nằm sẵn trong ô rỗng là một cái nút không làm gì.
          Bôi đen rồi xoá tay thì mất 3 thao tác; đây là 1. */}
      {value !== "" && (
        <button
          type="button"
          className="rc__search-clear"
          aria-label="Xóa ô tìm"
          title="Xóa ô tìm"
          onClick={() => onChange("")}
        >
          <XIcon size={12} />
        </button>
      )}
    </div>
  );
}
