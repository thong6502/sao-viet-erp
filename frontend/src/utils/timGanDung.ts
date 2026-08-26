// TÌM GẦN ĐÚNG cho các ô chọn có danh sách dài (công đoạn · giấy · máy · loại sản phẩm · ĐVT).
//
// Người khai giá gõ nhanh, gõ không dấu, và nhớ mỗi mảnh tên: "may in nho", "duplex 250",
// "hop giay". Lọc bằng `includes` thường thì cả ba lần đó đều ra RỖNG dù mục cần tìm nằm ngay
// đó — "MÁY IN NHỎ 46×64" không chứa chuỗi con "may in nho".
//
// Luật ở đây, cố ý dừng ở mức RẺ VÀ ĐOÁN ĐƯỢC (không xếp hạng mờ kiểu fuzzy-score, vì khi máy
// tự ý sắp lại thứ tự thì người dùng mất luôn cảm giác "mục mình cần nằm chỗ nào"):
//   1. bỏ dấu tiếng Việt, đ → d, thường hoá;
//   2. mọi ký tự không phải chữ/số thành khoảng trắng — nên "46x64", "46×64", "46 64" như nhau,
//      và dấu "·" ngăn mã với tên không cản việc gõ liền "cd0003 can mang";
//   3. cắt chuỗi tìm thành từng TỪ, mục nào chứa ĐỦ mọi từ (thứ tự nào cũng được) thì khớp.

export function boDau(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** `tim` rỗng ⇒ true (không lọc gì). Mọi từ trong `tim` phải có mặt trong `chuoi`. */
export function khopGanDung(chuoi: string, tim: string): boolean {
  const q = boDau(tim);
  if (!q) return true;
  const nen = boDau(chuoi);
  return q.split(" ").every((tu) => nen.includes(tu));
}
