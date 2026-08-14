import { useEffect, useState } from "react";

/** Trả về `giaTri` nhưng CHẬM lại `ms` — gõ xong mới hỏi máy chủ.
 *
 * Vì sao cần: ô tìm kiếm bắn thẳng `onChange` vào hàm tải là gõ "máy bế" ra 6 request, 5 cái đầu
 * vứt đi, và kết quả hiện ra theo thứ tự request nào về trước chứ không phải theo chữ đang gõ.
 *
 * Trước đây hàm này nằm cục bộ trong `RebuildCatalogPage.tsx` nên màn nào muốn dùng phải chép lại
 * — và mấy màn chép thiếu thì gõ một ký tự vẫn một request.
 */
export function useTre<T>(giaTri: T, ms = 300): T {
  const [tre, setTre] = useState(giaTri);
  useEffect(() => {
    const t = setTimeout(() => setTre(giaTri), ms);
    return () => clearTimeout(t);
  }, [giaTri, ms]);
  return tre;
}
