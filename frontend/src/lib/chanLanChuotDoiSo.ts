// Chặn "lăn chuột là đổi số" ở MỌI ô `type="number"` của app.
//
// Chrome: con trỏ nằm trên ô số ĐANG focus mà lăn chuột thì số tự tăng/giảm theo từng nấc, không
// báo gì. Người ta gõ số xong rồi cuộn ngăn/trang để xuống ô dưới là số vừa gõ đã khác — đo được
// 17/09/2026 ở ngăn Kiểm công đoạn: Số lỗi 1 tụt về 0 sau một lượt cuộn.
//
// Cách chặn: nhả focus ngay lúc lăn. Trình duyệt chỉ đổi số khi ô còn focus, nên số giữ nguyên còn
// trang vẫn cuộn bình thường. KHÔNG dùng `preventDefault` — cách đó chặn luôn cả cuộn trang.
// Nghe ở `document` pha capture để mọi ô (kể cả trong portal) đều được che mà không màn nào phải nhớ.
export function chanLanChuotDoiSo(doc: Document = document): () => void {
  const khiLan = (e: WheelEvent) => {
    const o = e.target;
    if (o instanceof HTMLInputElement && o.type === "number" && o === doc.activeElement) o.blur();
  };
  doc.addEventListener("wheel", khiLan, { capture: true, passive: true });
  return () => doc.removeEventListener("wheel", khiLan, { capture: true });
}
