/** Gác ô tìm GẦN ĐÚNG của các ô chọn danh mục (ĐVT · loại SP · giấy · máy · công đoạn).
 *
 *  Lý do có file này: lọc `includes` thuần đã im lặng trả RỖNG ở đúng những lần gõ thật — người
 *  dùng gõ không dấu, gõ mảnh, gõ sai thứ tự. Rỗng trông y hệt "danh mục không có món đó", nên
 *  họ đi khai lại một dòng trùng thay vì chọn dòng đang có.
 */
import { describe, expect, it } from "vitest";
import { boDau, khopGanDung } from "./timGanDung";

describe("boDau", () => {
  it("bỏ dấu, hạ chữ thường, đổi đ→d", () => {
    expect(boDau("MÁY IN NHỎ 46×64")).toBe("may in nho 46 64");
    expect(boDau("Đóng gói")).toBe("dong goi");
  });
  it("gom mọi thứ không phải chữ/số thành MỘT khoảng trắng", () => {
    expect(boDau("SVN-DL250 · Duplex 250gsm")).toBe("svn dl250 duplex 250gsm");
  });
});

describe("khopGanDung", () => {
  const MAY = "TB-0010 · MÁY IN NHỎ 46×64 (couché/hộp bồi)";

  it("gõ không dấu vẫn ra", () => {
    expect(khopGanDung(MAY, "may in nho")).toBe(true);
  });
  it("gõ SAI THỨ TỰ vẫn ra — mỗi từ chỉ cần có mặt", () => {
    expect(khopGanDung(MAY, "nho may")).toBe(true);
  });
  it("gõ mã cụt vẫn ra", () => {
    expect(khopGanDung(MAY, "tb 0010")).toBe(true);
    expect(khopGanDung(MAY, "tb-0010")).toBe(true);
  });
  it("gõ có dấu đầy đủ vẫn ra", () => {
    expect(khopGanDung(MAY, "máy in nhỏ")).toBe(true);
  });
  it("thiếu MỘT từ là trượt — không nới thành tìm mờ", () => {
    expect(khopGanDung(MAY, "may in lon")).toBe(false);
  });
  it("chuỗi tìm rỗng thì mọi dòng đều đạt (chưa gõ = chưa lọc)", () => {
    expect(khopGanDung(MAY, "")).toBe(true);
    expect(khopGanDung(MAY, "   ")).toBe(true);
  });
  it("số dính chữ tách được: 'duplex 250' khớp 'Duplex 250gsm'", () => {
    expect(khopGanDung("SVN-DL250 · Duplex 250gsm", "duplex 250")).toBe(true);
  });
});
