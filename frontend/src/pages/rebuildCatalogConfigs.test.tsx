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

describe("cột Quy cách đóng gói", () => {
  it("ghép thành câu đọc được, dùng tên đơn vị", () => {
    render(<>{cot(CFG_VAT_TU, "don_vi_dong_goi")(row({
      don_vi_gia: "kg", don_vi_ten: "kg",
      don_vi_dong_goi: "thung", don_vi_dong_goi_ten: "thùng", he_so_dong_goi: 3,
    }))}</>);
    expect(screen.getByText(/1\s*thùng\s*=\s*3\s*kg/)).toBeInTheDocument();
  });

  it("khai nửa vời (thiếu hệ số) thì không bịa ra câu", () => {
    render(<>{cot(CFG_VAT_TU, "don_vi_dong_goi")(row({
      don_vi_gia: "kg", don_vi_dong_goi: "thung", he_so_dong_goi: null,
    }))}</>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("cảnh báo quy đổi ở màn Đơn vị", () => {
  it("có canh_bao thì HIỆN RA — trước đây server trả mà không màn nào đọc", () => {
    const c = "“1 tờ = 1.000 g” là số cố định, nhưng tờ → g vốn đổi bằng công thức.";
    render(<>{cot(CFG_DON_VI, "canh_bao")(row({ canh_bao: [c] }))}</>);
    expect(screen.getByText(new RegExp("số cố định"))).toBeInTheDocument();
  });

  it("không có cảnh báo thì để gạch, không để ô trống lửng lơ", () => {
    render(<>{cot(CFG_DON_VI, "canh_bao")(row({ canh_bao: [] }))}</>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("hint ĐỘNG của ô hệ số quy cách", () => {
  const hint = (form: Record<string, unknown>) => {
    const h = truong(CFG_VAT_TU, "he_so_dong_goi").hint;
    if (typeof h !== "function") throw new Error("hint phải là hàm để dựng câu theo form");
    return h(form);
  };

  it("đủ ba ô thì ra đúng câu người đọc kiểm được", () => {
    expect(hint({ don_vi_dong_goi: "thùng", don_vi_gia: "kg", he_so_dong_goi: 3 }))
      .toBe("1 thùng = 3 kg");
  });

  it("thiếu ô nào thì chỉ ĐÚNG ô đó, không báo chung chung", () => {
    expect(hint({})).toMatch(/Chọn đơn vị đóng gói/);
    expect(hint({ don_vi_dong_goi: "thùng" })).toMatch(/Chọn ĐVT/);
    expect(hint({ don_vi_dong_goi: "thùng", don_vi_gia: "kg" })).toMatch(/1 thùng = \? kg/);
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
