// KỲ BÁO CÁO — docs/prd-bao-cao-cong-no.md §5.1.
//
// Kế toán tự chọn từ ngày đến ngày. Mấy nút nhanh chỉ là điền hộ hai ô ngày, KHÔNG phải một chế
// độ riêng — bấm xong vẫn sửa tay được, và ô ngày vẫn là nguồn sự thật duy nhất.
//
// Mặc định là THÁNG NÀY: đó là kỳ kế toán mở nhiều nhất. Mở màn ra thấy cả năm thì lần nào cũng
// phải thu hẹp lại trước khi đọc được cái gì.

export type Ky = { tu: string; den: string };

function iso(d: Date): string {
  // Tự ghép chứ KHÔNG dùng `toISOString()`: hàm đó đổi sang UTC, nên tối muộn giờ VN nó trả về
  // ngày HÔM TRƯỚC — kỳ "tháng này" sẽ bắt đầu từ ngày cuối tháng trước.
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function khoang(tu: Date, den: Date): Ky {
  return { tu: iso(tu), den: iso(den) };
}

/** Mốc TẠM lúc màn vừa mở, trước khi server trả về danh sách kỳ thật.
 *
 *  Chỉ sống được vài trăm mili-giây: `BaoCaoCongNoPage` nhảy sang KỲ HIỆN TẠI (kỳ chưa chốt,
 *  server dựng từ ngày chốt cuối cùng) ngay khi danh sách kỳ về. Cần một giá trị đầu để hai ô
 *  ngày không rỗng, thế thôi.
 *
 *  Bốn nút "Tháng này/Tháng trước/Quý này/Năm nay" đã BỎ 04/09/2026: kỳ kế toán ở đây là kỳ TỰ
 *  ĐẶT lúc chốt sổ, không phải tháng lịch. Để cả hai lối đặt kỳ trên một màn chính là thứ đẻ ra
 *  mớ "Chốt một phần" không ai hiểu. */
export const kyMacDinh: Ky = (() => {
  const n = new Date();
  return khoang(new Date(n.getFullYear(), n.getMonth(), 1), n);
})();

/** "01/09 – 03/09/2026" — nhãn gọn của kỳ, in ở dòng phụ dưới tiêu đề.
 *
 *  Cùng năm thì chỉ ghi năm MỘT LẦN ở cuối; khác năm thì ghi đủ. Lặp năm hai lần cho một kỳ nằm
 *  gọn trong một năm là bốn ký tự thừa ở chỗ vốn đã chật. */
export function nhanKy(ky: Ky): string {
  const [ny, nt, nd] = ky.tu.split("-");
  const [dy, dt, dd] = ky.den.split("-");
  if (!ny || !dy) return "";
  return ny === dy
    ? `${nd}/${nt} – ${dd}/${dt}/${dy}`
    : `${nd}/${nt}/${ny} – ${dd}/${dt}/${dy}`;
}
