import { describe, it, expect } from "vitest";
import { gopTheoNhom, nhomLechSoLuong, type DongGopDuoc } from "./gop-nhom";

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
