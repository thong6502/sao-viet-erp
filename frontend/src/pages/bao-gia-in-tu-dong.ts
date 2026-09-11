import { useEffect, useRef } from "react";

/** Ảnh phải chờ tải xong mới in: letterhead đầu trang + ảnh minh họa từng dòng. */
const ANH_BAN_IN = ".qpdf .q-mh-img, .qpdf .q-anh img";

/**
 * Có quyền `export` thì bấm "Xem bản in" ra thẳng hộp thoại in, khỏi bắt xem trước rồi bấm
 * thêm nút "In / Lưu PDF". Đợi HẾT ảnh tải xong rồi mới gọi `print()` — lần đầu vào trang ảnh
 * chưa kịp cache, in sớm là bản in thiếu ảnh. In xong (hoặc bấm huỷ) thì `afterprint` đóng
 * khung xem trước.
 *
 * HAI effect TÁCH RỜI, cố ý:
 *
 * - Effect "in": `firedRef` chặn StrictMode (dev) gọi 2 lần ra 2 hộp thoại in liên tiếp.
 * - Effect "đóng": KHÔNG được nằm chung với `firedRef`. Trước đây listener `afterprint` gắn
 *   trong effect "in": StrictMode chạy effect → cleanup gỡ listener → chạy lại thì `firedRef`
 *   đã bật nên trả về sớm, KHÔNG gắn lại listener nào. Hậu quả: in xong khung xem trước không
 *   tự đóng, `showPrint` kẹt `true`, mà khung lại bị `q-print-silent` ẩn ⇒ nút "Xem bản in"
 *   chết câm từ lần bấm thứ hai trở đi cho tới khi F5.
 */
export function useInTuDong(canDownload: boolean, onClose: () => void): void {
  // Giữ callback trong ref để effect "đóng" không phải gắn/gỡ listener theo mỗi lần cha render.
  const dongRef = useRef(onClose);
  dongRef.current = onClose;

  useEffect(() => {
    if (!canDownload) return;
    const dong = () => dongRef.current();
    window.addEventListener("afterprint", dong);
    return () => window.removeEventListener("afterprint", dong);
  }, [canDownload]);

  const firedRef = useRef(false);
  useEffect(() => {
    if (!canDownload || firedRef.current) return;
    firedRef.current = true;
    const imgs = Array.from(document.querySelectorAll<HTMLImageElement>(ANH_BAN_IN));
    const doPrint = () => window.print();
    const pending = imgs.filter((img) => !img.complete);
    if (pending.length === 0) {
      doPrint();
      return;
    }
    let remaining = pending.length;
    const settle = () => {
      remaining -= 1;
      if (remaining <= 0) doPrint();
    };
    pending.forEach((img) => {
      img.addEventListener("load", settle, { once: true });
      img.addEventListener("error", settle, { once: true });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
