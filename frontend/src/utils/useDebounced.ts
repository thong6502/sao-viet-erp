import { useEffect, useState } from "react";

/** Trả về `value` nhưng CHẬM lại `delay` mili-giây kể từ lần đổi cuối.
 *
 *  Dùng cho ô tìm kiếm gọi máy chủ: trước 08/08/2026 các màn Thu mua nối thẳng ô nhập vào lời gọi,
 *  nên gõ "giấy duplex" là bắn 11 lượt gọi, lượt trước chưa về lượt sau đã đi — bảng nhấp nháy và
 *  thứ tự trả về không đảm bảo (lượt gọi cũ về SAU có thể đè kết quả mới).
 *
 *  300ms là khoảng nghỉ tự nhiên giữa hai từ khi gõ tiếng Việt có dấu; ngắn hơn thì vẫn bắn thừa,
 *  dài hơn thì người dùng thấy khựng.
 *
 *  LƯU Ý khi dùng: ô nhập vẫn bind vào state GỐC (gõ tới đâu hiện tới đó), chỉ có lời gọi máy chủ
 *  mới đọc giá trị đã chậm. Bind ngược lại là ô nhập giật từng nhịp. */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}
