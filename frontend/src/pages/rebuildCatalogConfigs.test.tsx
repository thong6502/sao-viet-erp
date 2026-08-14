// Bằng chứng THẬT cho phần HIỆN RA của danh mục gốc (Giấy · Vật tư khác · Đơn vị).
//
// Ba thứ dưới đây từng "làm xong" mà người dùng không thấy gì, nên phải khoá lại bằng render chứ
// không bằng niềm tin:
//   · cột ĐVT hiện MÃ (`kem`) thay vì TÊN ("bản kẽm") — mã thì không ai đoán ra;
//   · cảnh báo cặp quy đổi sai: server trả `canh_bao` từ lâu nhưng KHÔNG màn nào render;
//   · câu "1 thùng = 3 kg" dựng từ 3 ô đang gõ — `hint` vốn chỉ nhận chuỗi tĩnh nên câu này im.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CFG_DON_VI, CFG_GIAY, CFG_VAT_TU } from "./rebuildCatalogConfigs";
import type { CatalogConfig, FieldDef } from "./RebuildCatalogPage";
import type { Row } from "../api/rebuildCatalog";

function cot(cfg: CatalogConfig, key: string) {
  const c = cfg.columns.find((x) => x.key === key);
  if (!c?.render) throw new Error(`không có cột "${key}" (hoặc cột không tự render)`);
  return c.render;
}

function truong(cfg: CatalogConfig, key: string): FieldDef {
  const f = cfg.fields.find((x) => x.key === key);
  if (!f) throw new Error(`không có field "${key}"`);
  return f;
}

/** Dòng bảng — chỉ cần 3 khoá bắt buộc của `Row`, phần còn lại tuỳ danh mục. */
const row = (extra: Record<string, unknown>): Row =>
  ({ id: 1, ma: "X", ten: "x", ...extra }) as Row;

describe("cột ĐVT của mặt hàng gốc", () => {
  it("hiện TÊN đơn vị chứ không hiện mã", () => {
    render(<>{cot(CFG_VAT_TU, "don_vi_gia")(row({ don_vi_gia: "kem", don_vi_ten: "bản kẽm" }))}</>);
    expect(screen.getByText("bản kẽm")).toBeInTheDocument();
    expect(screen.queryByText("kem")).not.toBeInTheDocument();
  });

  it("chưa có tên thì lùi về mã, không hiện trống", () => {
    render(<>{cot(CFG_GIAY, "don_vi_gia")(row({ don_vi_gia: "kg" }))}</>);
    expect(screen.getByText("kg")).toBeInTheDocument();
  });

  it("chưa chọn đơn vị thì NÓI RÕ, vì thiếu nó là kho không nhập được mặt hàng", () => {
    render(<>{cot(CFG_GIAY, "don_vi_gia")(row({ don_vi_gia: null }))}</>);
    expect(screen.getByText("Chưa chọn đơn vị")).toBeInTheDocument();
  });
});

describe("cảnh báo quy đổi ở màn Đơn vị", () => {
  it("có canh_bao thì HIỆN RA — trước đây server trả mà không màn nào đọc", () => {
    // Câu dài bị CẮT cho vừa cột nên đừng dò bằng nội dung chữ: bản trước tìm "số cố định" — cụm
    // đó nằm sau ký tự thứ 27 nên không bao giờ có trong DOM, test đỏ mà chẳng nói lên điều gì.
    // Chữ đầy đủ luôn ở `title` (hover ra xem), nên soi ở đó.
    const c = "Chưa khai quy đổi — g chưa đổi qua lại được với đơn vị nào.";
    render(<>{cot(CFG_DON_VI, "canh_bao")(row({ canh_bao: [c] }))}</>);
    expect(screen.getByTitle(c)).toBeInTheDocument();
  });

  it("không có cảnh báo thì để gạch, không để ô trống lửng lơ", () => {
    render(<>{cot(CFG_DON_VI, "canh_bao")(row({ canh_bao: [] }))}</>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("form Vật tư khác KHÔNG còn quy cách đóng gói", () => {
  it("bỏ hẳn hai ô — quy đổi chỉ khai ở danh mục Đơn vị & quy đổi, một nơi duy nhất", () => {
    const keys = CFG_VAT_TU.fields.map((f) => f.key);
    expect(keys).not.toContain("don_vi_dong_goi");
    expect(keys).not.toContain("he_so_dong_goi");
    expect(CFG_VAT_TU.columns.map((c) => c.key)).not.toContain("don_vi_dong_goi");
  });
});

describe("ô ĐVT lấy từ danh mục Đơn vị", () => {
  it("chọn từ /api/don-vi, lưu MÃ, và chỉ mời đơn vị còn dùng", () => {
    for (const cfg of [CFG_GIAY, CFG_VAT_TU]) {
      const f = truong(cfg, "don_vi_gia");
      expect(f.type).toBe("ref-search-ma");          // lưu mã `kg`, không lưu id
      expect(f.refPrefix).toBe("/api/don-vi");       // nguồn duy nhất, không còn list cứng
      expect(f.refParams).toEqual({ active: true }); // không mời đơn vị đã ngừng dùng
    }
  });
});
