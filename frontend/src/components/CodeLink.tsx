/** Mã chứng từ bấm được (YCMH/PMH/...) — dùng trong ô bảng và panel chi tiết
 *  để nhảy chéo trang tới đúng phiếu. Tự chặn nổi bọt để không kích hoạt
 *  onClick chọn dòng của <tr> chứa nó. Style: `.code-link` (purchase.css). */
export function CodeLink({
  code,
  onOpen,
  title,
}: {
  code: string;
  onOpen: (code: string) => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      className="code-link"
      title={title ?? `Mở ${code}`}
      onClick={(event) => {
        event.stopPropagation();
        onOpen(code);
      }}
    >
      {code}
    </button>
  );
}
