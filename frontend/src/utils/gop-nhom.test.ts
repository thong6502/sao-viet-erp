import { describe, it, expect } from "vitest";
import {
  gopTheoNhom,
  gopTrungTen,
  nhomLechSoLuong,
  type DongDaGop,
  type DongGopDuoc,
} from "./gop-nhom";

/** Dòng báo giá rút gọn cho test — chỉ giữ các trường `gopTheoNhom` cần. */
type Dong = DongGopDuoc;
const chon = (d: Dong) => d;

const dong = (x: Partial<Dong> & { ten: string; soLuong: number; thanhTien: number }): Dong => ({
  nhom: null,
  donViTinh: "cuốn",
  tienVat: 0,
  vatPct: 8,
  kichThuoc: null,
  dienGiai: null,
  ...x,
});

describe("gopTheoNhom", () => {
  it("cùng nhãn + cùng SL → gộp 1 dòng, đơn giá = Σ tiền ÷ SL", () => {
    const rows = [
      dong({ nhom: "Sách A5", ten: "Ruột", soLuong: 1200, thanhTien: 12_000_000 }),
      dong({ nhom: "Sách A5", ten: "Bìa", soLuong: 1200, thanhTien: 3_600_000 }),
    ];
    const out = gopTheoNhom(rows, chon);
    expect(out).toHaveLength(1);
    expect(out[0].ten).toBe("Sách A5");
    expect(out[0].soLuong).toBe(1200);
    expect(out[0].thanhTien).toBe(15_600_000);
    expect(out[0].donGia).toBe(13_000);
  });

  it("cùng nhãn nhưng LỆCH SL → tách 2 dòng, mỗi dòng đúng SL + đơn giá của nó", () => {
    // Đúng ca lỗi 9b: gộp 10.000 với 100 rồi chia Σ tiền cho 10.000 ra 2.797 đ/cuốn — số không có thật.
    const rows = [
      dong({ nhom: "sách", ten: "SP1", soLuong: 10_000, thanhTien: 24_426_822 }),
      dong({ nhom: "sách", ten: "SP2", soLuong: 100, thanhTien: 3_545_212 }),
    ];
    const out = gopTheoNhom(rows, chon);
    expect(out).toHaveLength(2);
    expect(out.map((g) => g.soLuong)).toEqual([10_000, 100]);
    expect(out.map((g) => g.thanhTien)).toEqual([24_426_822, 3_545_212]);
    expect(out[0].donGia).toBe(Math.round(24_426_822 / 10_000));
    expect(out[1].donGia).toBe(Math.round(3_545_212 / 100));
    // Nhãn bị tách thì mọi dòng của nó phải ghi tiền tố tên phần để khách phân biệt.
    expect(out[0].dienGiai).toEqual(["SP1"]);
    expect(out[1].dienGiai).toEqual(["SP2"]);
  });

  it("cùng SL nhưng khác ĐVT → VẪN gộp, lấy ĐVT của dòng đầu (chủ chốt 26/08/2026)", () => {
    // ĐVT cố ý KHÔNG nằm trong khoá gộp. Test này khoá quyết định đó lại: ai đó siết thêm ĐVT
    // là đỏ ngay, phải hỏi chủ trước.
    const rows = [
      dong({ nhom: "combo", ten: "Tờ rơi", soLuong: 500, donViTinh: "tờ", thanhTien: 1_000_000 }),
      dong({ nhom: "combo", ten: "Sách", soLuong: 500, donViTinh: "cuốn", thanhTien: 5_000_000 }),
    ];
    const out = gopTheoNhom(rows, chon);
    expect(out).toHaveLength(1);
    expect(out[0].soLuong).toBe(500);
    expect(out[0].donViTinh).toBe("tờ");
    expect(out[0].donGia).toBe(12_000);
  });

  it("cụm đã khai ĐVT nhóm → dòng gộp lấy nhãn đó, dòng con giữ đơn vị của chính nó", () => {
    // Bìa "cái" + ruột "cái", cụm bán theo "cuốn". Trước mg 0264 đơn vị cụm bị ĐÈ lên cả hai dòng
    // con nên đơn hàng tab Thương mại hiện "Bìa sách — 2.000 cuốn".
    const rows = [
      dong({ nhom: "Sách", ten: "Bìa", soLuong: 2000, donViTinh: "cái", dvtNhom: "cuốn", thanhTien: 4_000_000 }),
      dong({ nhom: "Sách", ten: "Ruột", soLuong: 2000, donViTinh: "cái", dvtNhom: "cuốn", thanhTien: 44_000_000 }),
    ];
    const out = gopTheoNhom(rows, chon);
    expect(out).toHaveLength(1);
    expect(out[0].donViTinh).toBe("cuốn");
    expect(rows.map((r) => r.donViTinh)).toEqual(["cái", "cái"]);
  });

  it("cụm chưa khai ĐVT nhóm → dòng gộp rơi về ĐVT dòng đầu (luật cũ)", () => {
    const rows = [
      dong({ nhom: "Sách", ten: "Bìa", soLuong: 2000, donViTinh: "cái", dvtNhom: null, thanhTien: 4_000_000 }),
      dong({ nhom: "Sách", ten: "Ruột", soLuong: 2000, donViTinh: "cái", thanhTien: 44_000_000 }),
    ];
    expect(gopTheoNhom(rows, chon)[0].donViTinh).toBe("cái");
  });

  it("dòng KHÔNG có nhãn nhóm thì `dvtNhom` lạc vào cũng bị bỏ qua", () => {
    const rows = [dong({ ten: "Tờ rơi", soLuong: 500, donViTinh: "tờ", dvtNhom: "cuốn", thanhTien: 1_000_000 })];
    expect(gopTheoNhom(rows, chon)[0].donViTinh).toBe("tờ");
  });

  it("dòng không có nhãn thì đứng riêng như cũ", () => {
    const rows = [
      dong({ ten: "Lẻ 1", soLuong: 10, thanhTien: 100 }),
      dong({ ten: "Lẻ 2", soLuong: 10, thanhTien: 200 }),
    ];
    const out = gopTheoNhom(rows, chon);
    expect(out).toHaveLength(2);
    expect(out.map((g) => g.ten)).toEqual(["Lẻ 1", "Lẻ 2"]);
  });
});

describe("nhomLechSoLuong", () => {
  it("nêu số dòng sẽ in cho nhãn bị lệch số lượng", () => {
    const rows = [
      dong({ nhom: "sách", ten: "SP1", soLuong: 10_000, thanhTien: 1 }),
      dong({ nhom: "sách", ten: "SP2", soLuong: 100, thanhTien: 1 }),
      dong({ nhom: "khớp", ten: "Ruột", soLuong: 300, thanhTien: 1 }),
      dong({ nhom: "khớp", ten: "Bìa", soLuong: 300, thanhTien: 1 }),
    ];
    const lech = nhomLechSoLuong(rows, chon);
    expect(lech).toHaveLength(1);
    expect(lech[0].ten).toBe("sách");
    expect(lech[0].soDongSeIn).toBe(2);
    expect(lech[0].phan.map((p) => p.soLuong)).toEqual([10_000, 100]);
  });
});

describe("gopTrungTen", () => {
  const g = (
    ten: string,
    soLuong: number,
    thanhTien: number,
    x: Partial<DongDaGop<Dong>> = {},
  ): DongDaGop<Dong> => ({
    key: `${ten}-${soLuong}`,
    ten,
    soLuong,
    donViTinh: "cái",
    thanhTien,
    tienVat: 0,
    vatPct: 10,
    kichThuoc: null,
    dienGiai: [],
    donGia: soLuong > 0 ? Math.round(thanhTien / soLuong) : thanhTien,
    goc: [],
    ...x,
  });

  it("trùng TÊN sản phẩm → 1 dòng, mỗi SL là một mức", () => {
    const out = gopTrungTen([
      g("Hộp bánh 200g", 10_000, 32_000_000),
      g("Hộp bánh 200g", 20_000, 61_524_494),
      g("Hộp bánh 200g", 50_000, 144_678_957),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].ten).toBe("Hộp bánh 200g");
    expect(out[0].muc.map((m) => m.soLuong)).toEqual([10_000, 20_000, 50_000]);
    expect(out[0].muc.map((m) => m.thanhTien)).toEqual([32_000_000, 61_524_494, 144_678_957]);
    // Chân bảng giữ nguyên: Σ thành tiền của dòng gộp = Σ các mức.
    expect(out[0].thanhTien).toBe(32_000_000 + 61_524_494 + 144_678_957);
  });

  it("khác tên thì đứng riêng, thứ tự theo lần xuất hiện đầu", () => {
    const out = gopTrungTen([
      g("Hộp bánh 200g", 10_000, 32_000_000),
      g("Thẻ nhân viên", 500, 1_000_000),
      g("Hộp bánh 200g", 20_000, 61_524_494),
    ]);
    expect(out.map((x) => x.ten)).toEqual(["Hộp bánh 200g", "Thẻ nhân viên"]);
    expect(out[0].muc).toHaveLength(2);
    expect(out[1].muc).toHaveLength(1);
  });

  it("gõ lệch hoa/thường và khoảng trắng vẫn coi là cùng tên", () => {
    const out = gopTrungTen([
      g("Hộp bánh 200g", 10_000, 32_000_000),
      g("  hộp BÁNH 200g ", 20_000, 61_524_494),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].ten).toBe("Hộp bánh 200g"); // giữ nguyên chữ của mức ĐẦU
  });

  it("các mức trùng diễn giải → chỉ in một lần; lệch thì giữ đủ, không trùng lặp", () => {
    const a = ["KT: 420×300mm", "Giấy C300 300g"];
    const trung = gopTrungTen([
      g("Hộp bánh", 10_000, 1, { dienGiai: [...a] }),
      g("Hộp bánh", 20_000, 1, { dienGiai: [...a] }),
    ]);
    expect(trung[0].dienGiai).toEqual(a);

    const lech = gopTrungTen([
      g("Hộp bánh", 10_000, 1, { dienGiai: [...a] }),
      g("Hộp bánh", 20_000, 1, { dienGiai: [...a, "Cán màng mờ"] }),
    ]);
    expect(lech[0].dienGiai).toEqual([...a, "Cán màng mờ"]);
  });

  it("mức lệch VAT% → cột % để trống, tiền vẫn cộng đủ", () => {
    const out = gopTrungTen([
      g("Hộp bánh", 10_000, 1_000_000, { tienVat: 100_000, vatPct: 10 }),
      g("Hộp bánh", 20_000, 2_000_000, { tienVat: 160_000, vatPct: 8 }),
    ]);
    expect(out[0].vatPct).toBeNull();
    expect(out[0].tienVat).toBe(260_000);
  });

  it("kích thước chỉ giữ khi mọi mức giống nhau", () => {
    const cung = gopTrungTen([
      g("Hộp bánh", 10_000, 1, { kichThuoc: "420×300" }),
      g("Hộp bánh", 20_000, 1, { kichThuoc: "420×300" }),
    ]);
    expect(cung[0].kichThuoc).toBe("420×300");
    const lech = gopTrungTen([
      g("Hộp bánh", 10_000, 1, { kichThuoc: "420×300" }),
      g("Hộp bánh", 20_000, 1, { kichThuoc: "500×300" }),
    ]);
    expect(lech[0].kichThuoc).toBeNull();
  });

  it("giữ được dòng gốc của MỌI mức (chỗ gọi cần `note` khi dòng chỉ có 1 mức)", () => {
    const r1 = dong({ ten: "A", soLuong: 10, thanhTien: 1 });
    const r2 = dong({ ten: "A", soLuong: 20, thanhTien: 2 });
    const out = gopTrungTen([
      g("Hộp bánh", 10, 1, { goc: [r1] }),
      g("Hộp bánh", 20, 2, { goc: [r2] }),
    ]);
    expect(out[0].goc).toEqual([r1, r2]);
  });
});
