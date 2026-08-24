// Bằng chứng THẬT cho phần HIỆN RA của danh mục gốc (Giấy · Vật tư khác · Đơn vị).
//
// Ba thứ dưới đây từng "làm xong" mà người dùng không thấy gì, nên phải khoá lại bằng render chứ
// không bằng niềm tin:
//   · cột ĐVT hiện MÃ (`kem`) thay vì TÊN ("bản kẽm") — mã thì không ai đoán ra;
//   · cảnh báo cặp quy đổi sai: server trả `canh_bao` từ lâu nhưng KHÔNG màn nào render;
//   · câu "1 thùng = 3 kg" dựng từ 3 ô đang gõ — `hint` vốn chỉ nhận chuỗi tĩnh nên câu này im.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  CFG_CONG_DOAN, CFG_CONG_VIEC_KHOAN, CFG_DON_VI, CFG_GIAY, CFG_MAY, CFG_THANH_PHAM, CFG_VAT_TU,
} from "./rebuildCatalogConfigs";
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

describe("màn Công việc khoán (đơn giá khoán theo tổ)", () => {
  it("cột Đơn vị hiện TÊN khi mã có trong danh mục", () => {
    render(<>{cot(CFG_CONG_VIEC_KHOAN, "unit")(row({ unit: "to", don_vi_ten: "tờ" }))}</>);
    expect(screen.getByText("tờ")).toBeInTheDocument();
  });

  it("mã lạ thì hiện NGUYÊN mã kèm dấu hiệu — không bỏ trắng như thể chưa khai", () => {
    // Dòng đời cũ mang đơn vị ngoài danh mục ("mét tới"): server không tra ra tên nên `don_vi_ten`
    // rỗng. Bỏ trắng ô thì người khai tưởng chưa chọn gì và giá trị hỏng vẫn nằm nguyên đó.
    render(<>{cot(CFG_CONG_VIEC_KHOAN, "unit")(row({ unit: "mét tới", don_vi_ten: null }))}</>);
    const o = screen.getByText("mét tới");
    expect(o).toBeInTheDocument();
    expect(o).toHaveAttribute("title", expect.stringContaining("không có trong danh mục"));
  });

  it("cột Tổ dịch mã tổ đời cũ sang tên đọc được", () => {
    render(<>{cot(CFG_CONG_VIEC_KHOAN, "group_name")(row({ group_name: "to_boi" }))}</>);
    expect(screen.getByText("Tổ Bồi")).toBeInTheDocument();
  });

  it("đi đúng nền danh mục: mã tự sinh · xoá mềm · có tab Nhật ký · gác quyền riêng", () => {
    expect(CFG_CONG_VIEC_KHOAN.autoCode).toBe(true);        // KH-#### do server cấp
    expect(CFG_CONG_VIEC_KHOAN.softDelete).toBe(true);      // còn nơi dùng ⇒ chỉ ngừng dùng
    expect(CFG_CONG_VIEC_KHOAN.nhatKyLoai).toBe("cong_viec_khoan");
    expect(CFG_CONG_VIEC_KHOAN.moduleQuyen).toBe("dm_cong_viec_khoan");
    expect(CFG_CONG_VIEC_KHOAN.prefix).toBe("/api/cong-viec-khoan");
  });

  it("ô Đơn vị dùng CÙNG cách khai với Giấy · Vật tư (lưu mã, chỉ mời đơn vị còn dùng)", () => {
    const f = truong(CFG_CONG_VIEC_KHOAN, "unit");
    expect(f.type).toBe("ref-search-ma");
    expect(f.refPrefix).toBe("/api/don-vi");
    expect(f.refParams).toEqual({ active: true });
  });

  it("KHÔNG có ô `group_name`: nhãn tổ do server suy từ tổ đã chọn", () => {
    const keys = CFG_CONG_VIEC_KHOAN.fields.map((f) => f.key);
    expect(keys).toContain("department_id");
    expect(keys).not.toContain("group_name");
    expect(truong(CFG_CONG_VIEC_KHOAN, "department_id").required).toBe(true);
  });
});

describe("ô Cách đo lượng ở màn Máy và Công việc khoán (mg 0213)", () => {
  it("cả hai dùng bộ chip `quy_doi` — ô ra LƯỢNG không được mời chip đơn giá", () => {
    for (const cfg of [CFG_MAY, CFG_CONG_VIEC_KHOAN]) {
      const f = truong(cfg, "cong_thuc_luong");
      expect(f.type).toBe("formula");
      expect(f.loaiO).toBe("quy_doi");
    }
  });

  it("nhãn tab công thức KHÔNG phải \"Công thức tính giá\" — hai ô này không nhắc tới tiền", () => {
    expect(CFG_MAY.nhanTabCongThuc).toBe("Cách đo lượng");
    expect(CFG_CONG_VIEC_KHOAN.nhanTabCongThuc).toBe("Cách đo lượng");
  });

  it("Giấy: hai ô công thức TÁCH hai tab riêng (Tính giá · Tính lượng)", () => {
    // Cả hai ô vẫn còn — chỉ tách tab qua `nhanTab`. `cong_thuc_gia` ra TIỀN cho phiếu tính giá,
    // `cong_thuc_luong` ra kg cho bảng cân đối vật tư; không được nhét chung một tab.
    expect(truong(CFG_GIAY, "cong_thuc_gia").nhanTab).toBe("Công thức tính giá");
    expect(truong(CFG_GIAY, "cong_thuc_luong").nhanTab).toBe("Công thức tính lượng");
    // Mỗi ô tự khai tab của nó nên KHÔNG dùng nhãn config-level.
    expect(CFG_GIAY.nhanTabCongThuc).toBeUndefined();
  });

  it("Công đoạn: hai ô công thức TÁCH hai tab riêng (Tính giá · Sản lượng ra)", () => {
    // Y như Giấy: `cong_thuc_gia` ra TIỀN cho phiếu tính giá, `cong_thuc_san_luong` ra LƯỢNG cho
    // bước ngoài dòng giấy — mỗi ô tự khai `nhanTab`, không nhét chung một tab "Công thức".
    expect(truong(CFG_CONG_DOAN, "cong_thuc_gia").nhanTab).toBe("Công thức tính giá");
    expect(truong(CFG_CONG_DOAN, "cong_thuc_san_luong").nhanTab).toBe("Công thức sản lượng ra");
    // Ô sản lượng ra dùng bộ chip `quy_doi` (ra lượng, không mời chip đơn giá).
    expect(truong(CFG_CONG_DOAN, "cong_thuc_san_luong").loaiO).toBe("quy_doi");
    // Mỗi ô tự khai tab nên KHÔNG dùng nhãn config-level.
    expect(CFG_CONG_DOAN.nhanTabCongThuc).toBeUndefined();
  });

  it("Vật tư khác: CHỈ tab tính lượng — ẩn ô công thức GIÁ khỏi drawer", () => {
    // Ô giá bị ẩn khỏi màn (cột DB + đường engine vẫn còn); nhãn tab đổi cho khớp để đừng mời
    // người khai gõ công thức tiền vào ô ra lượng.
    expect(CFG_VAT_TU.fields.some((f) => f.key === "cong_thuc_gia")).toBe(false);
    expect(CFG_VAT_TU.nhanTabCongThuc).toBe("Công thức tính lượng");
    // Ô lượng vẫn còn, dùng bộ chip `quy_doi` (không mời chip đơn giá).
    expect(truong(CFG_VAT_TU, "cong_thuc_luong").loaiO).toBe("quy_doi");
  });
});

describe("Thành phẩm — hàng đặt riêng của MỘT khách (docs/prd-thanh-pham.md)", () => {
  it("bảng KHÔNG còn cột Khách hàng", () => {
    // Đảo luật 21/08/2026 ("không dùng tới với lại cũng không cần thiết"). Trước đó cột này để
    // phân biệt hai thành phẩm cùng tên khác khách; đếm lúc gỡ: 7 thành phẩm, 0 tên trùng.
    // Mã dòng (`TP-<mã khách>-nnn`) vẫn chỉ ra chủ nếu về sau có trùng thật.
    expect(CFG_THANH_PHAM.columns.some((c) => c.key === "customer_ten")).toBe(false);
  });

  it("⭐ KHÔNG còn ô Khách hàng ở đâu cả", () => {
    // Đảo luật 21/08/2026: "khách hàng mình lưu làm gì, mình không dùng tới — thành phẩm này là
    // một cái tên hàng mới, nêu chưa khai để tái sử dụng, tránh phình lên".
    //
    // Trước đó ô này BẮT BUỘC vì `customer_id` là công tắc chia hai màn — để trống là dòng vừa
    // khai rơi sang màn Vật tư khác rồi mất tích. Công tắc nay là cột `la_thanh_pham` (mg 0228)
    // do repo tự đóng dấu, nên bỏ ô này an toàn.
    //
    // Test này ĐỎ ngay khi ai đó đưa lại khách vào thành phẩm — dù ở cột hay ở ô.
    expect(CFG_THANH_PHAM.fields.some((f) => f.key === "customer_id")).toBe(false);
    expect(CFG_THANH_PHAM.columns.some((c) => c.key === "customer_ten")).toBe(false);
  });

  it("KHÔNG cho xoá, NHƯNG cho khai tay", () => {
    // Xoá là làm mồ côi lô tồn (L7). Khai tay thì cho (L5 nới 19/08/2026) — luật siết 08/08/2026
    // của kho bỏ ô tên tự do TRÊN PHIẾU XUẤT, nó không cấm khai danh mục.
    expect(CFG_THANH_PHAM.khongXoa).toBe(true);
    expect(CFG_THANH_PHAM.khongTaoTay).toBeUndefined();
  });

  it("KHÔNG bày ô Mã thành ô sửa", () => {
    // Mã đã nằm trong lô tồn và phiếu đã ghi sổ. Máy chủ gạt đi, nhưng lúc đó họ đã gõ xong rồi.
    expect(CFG_THANH_PHAM.fields.some((f) => f.key === "ma")).toBe(false);
  });

  it("ô quyền RIÊNG, không dùng chung với Vật tư khác", () => {
    expect(CFG_THANH_PHAM.moduleQuyen).toBe("dm_thanh_pham");
    expect(CFG_VAT_TU.moduleQuyen).toBe("dm_vat_tu");
  });
});
