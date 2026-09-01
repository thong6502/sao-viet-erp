// Ô `datetime-local` của trình duyệt — kiểm giá trị gõ vào, dùng CHUNG mọi phân hệ.
//
// Ô ngày-giờ cho năm tới 6 chữ số (chuẩn HTML tới năm 275760): gõ đè vào ô năm là ra
// "92026-03-01T20:00" — trình duyệt coi là HỢP LỆ nên form nào chỉ soi "khác rỗng" là cho gửi,
// rồi hoặc backend trả 422 câm, hoặc `new Date(...).toISOString()` NÉM lỗi ngay trên màn. Đặt ở
// `lib/` chứ không ở file dùng chung của một phân hệ: Kế hoạch SX, Giao hàng và Lương đều cần.
//
// `min`/`max` trên thẻ input là lớp chặn thứ nhất (Chrome cắt năm còn 4 chữ số), hai hàm dưới đây
// là lớp thứ hai — trình duyệt/thiết bị khác có thể không chặn, và năm 4 chữ số ngoài khoảng
// (0920, 0001…) vẫn lọt qua `min`/`max` khi người dùng gõ dở.
export const GIO_NHAP_MIN = "2000-01-01T00:00";
export const GIO_NHAP_MAX = "2099-12-31T23:59";
const RE_GIO_NHAP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/;

/** Ô ngày-giờ đã gõ xong và nằm trong khoảng dùng được chưa. Rỗng = CHƯA gõ, không phải sai. */
export function gioNhapHopLe(v: string | null | undefined): boolean {
  if (!v) return false;
  if (!RE_GIO_NHAP.test(v)) return false;
  return v >= GIO_NHAP_MIN && v.slice(0, 16) <= GIO_NHAP_MAX;
}

/** Người dùng đã gõ gì đó nhưng KHÔNG dùng được — để hiện lời nhắc, khác hẳn ô còn trống. */
export function gioNhapSai(v: string | null | undefined): boolean {
  return !!v && !gioNhapHopLe(v);
}
