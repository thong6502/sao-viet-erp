import "./pager.css";

/** Chân bảng phân trang DÙNG CHUNG — khuôn chốt ở `docs/prd-dong-bo-ui-thu-mua-nhan-su.md` §2:
 *  TỔNG bên trái, nút Trước/Sau bên phải, và CHỈ hiện nút khi thật sự có hơn một trang.
 *
 *  Vì sao ẩn nút ở bảng 1 trang: một cặp nút mờ tịt dưới bảng 3 dòng chỉ làm người dùng đi tìm
 *  trang thứ hai không tồn tại — nhiễu mà không nói thêm được gì.
 *
 *  ⚠ `total` phải là TỔNG TRÊN MÁY CHỦ, không phải `rows.length`. Truyền `rows.length` vào thì
 *  màn nào cũng in "Tổng 20" và nút chuyển trang không bao giờ hiện. */
export function Pager({
  total,
  page,
  size,
  onPage,
  loading,
  unit = "bản ghi",
  note,
}: {
  total: number;
  page: number;
  size: number;
  onPage: (page: number) => void;
  /** Khoá nút trong lúc đang gọi máy chủ — chống bấm dồn ra hai lượt gọi chồng nhau. */
  loading?: boolean;
  /** Danh từ đếm được, viết thường: "tài liệu", "đơn", "phiếu"… */
  unit?: string;
  /** Câu lưu ý thêm bên trái (vd: "chọn tất cả" chỉ trong phạm vi trang đang xem). */
  note?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, size)));
  return (
    <div className="pager">
      <span className="pager__total">
        Tổng {total} {unit}
        {totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ""}
        {note ? <span className="pager__note"> · {note}</span> : null}
      </span>
      {totalPages > 1 && (
        <div className="pager__btns">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={page <= 1 || !!loading}
            onClick={() => onPage(page - 1)}
          >
            Trước
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={page >= totalPages || !!loading}
            onClick={() => onPage(page + 1)}
          >
            Sau
          </button>
        </div>
      )}
    </div>
  );
}

/** Kẹp `page` về khoảng hợp lệ sau khi máy chủ trả `total`.
 *
 *  Ca thật: đang đứng trang 3, xoá nốt dòng cuối của trang đó ⇒ `total` co lại còn 2 trang,
 *  trang 3 rỗng trơn và người dùng tưởng mất sạch dữ liệu. Gọi hàm này trong `.then()` của mỗi
 *  lần tải: nó trả về số trang cần nhảy về, hoặc `null` nếu trang hiện tại vẫn hợp lệ. */
export function trangHopLe(page: number, total: number, size: number): number | null {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, size)));
  return page > totalPages ? totalPages : null;
}
