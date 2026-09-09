// Bảng kê vật tư của một lệnh (`bangKeVatTu`) — đóng đinh ba luật dễ làm sai số đi mua.
//
// Số liệu lấy từ LSX26-0004 trên DB dev (sách 160 trang · 1.000 cuốn · 5 tay/cuốn · Ford 70 65×86),
// gồm cả ca "màng cán bóng khai ở HAI bước" — chính là ca chứng minh khối tổng không thừa.
//
// [SỬA 08/09/2026] Panel không còn tự suy dòng giấy từ quy cách lệnh. Giấy vào bảng kê y hệt mọi
// món khác: một dòng của BƯỚC, chỉ khác `hang_loai === "giay"`.
import { describe, expect, it } from "vitest";
import type { LsxCongDoan } from "../api/client";
import { bangKeVatTu } from "./lsxVatTu";

type VatTuDong = LsxCongDoan["vat_tus"][number];

let seq = 0;
/** Bước tối thiểu. Mặc định NẰM TRÊN dòng giấy — bước ngoài dòng phải khai rõ, vì đó mới là ca lạ. */
function buoc(p: Partial<LsxCongDoan> = {}): LsxCongDoan {
  seq += 1;
  return {
    id: seq, thu_tu: seq * 10, ten: `Bước ${seq}`,
    department_ten: null, may_ten: null, khoan_ten: null,
    tren_dong_giay: true, requires_tooling: false, khuon_be_id: null,
    so_luong_vao: 0, so_luong_ra: 0, don_vi_vao: "to", don_vi_ra: "to",
    vat_tus: [], ...p,
  } as unknown as LsxCongDoan;
}

function vt(id: number, ten: string, so_luong: number, don_vi = "kg"): VatTuDong {
  return { id: id * 100, hang_loai: "vat_tu", vat_tu_id: id, vat_tu_ma: `VT-${id}`,
           vat_tu_ten: ten, don_vi, so_luong, tu_dong: false } as VatTuDong;
}

/** Dòng lấy từ DANH MỤC GIẤY — cùng bảng, cùng ô "Thêm vật tư", chỉ khác danh mục nguồn. */
function giay(id: number, ten: string, so_luong: number, don_vi = "kg"): VatTuDong {
  return { id: id * 100 + 1, hang_loai: "giay", vat_tu_id: id, vat_tu_ma: `GY-${id}`,
           vat_tu_ten: ten, don_vi, so_luong, tu_dong: false } as VatTuDong;
}

/** Chuỗi 6 bước thật của LSX26-0004. Bước ghi kẽm đứng ĐẦU nhưng ngoài dòng giấy, và người lập
 *  lệnh khai giấy ở bước In — đúng bước ăn giấy thật. */
function chuoiSach() {
  seq = 0;
  return [
    buoc({ ten: "Ghi kẽm CTP", tren_dong_giay: false, department_ten: "Tổ Chế bản",
           so_luong_vao: 1801, don_vi_vao: "m2", so_luong_ra: 7200, don_vi_ra: "bai" }),
    buoc({ ten: "In offset", khoan_ten: "In 2 màu", department_ten: "Tổ In offset",
           may_ten: "Máy 2 màu Mitsubishi 72×102",
           so_luong_vao: 5200, so_luong_ra: 5000,
           vat_tus: [giay(3, "Ford 70 65×86", 436.02),
                     vt(6, "Màng cán bóng", 5200.07, "m2"), vt(2, "Mực pha Pantone", 1_000_000)] }),
    buoc({ ten: "Gấp tay sách", khoan_ten: "Gấp tay sách máy",
           so_luong_vao: 5000, so_luong_ra: 5000, don_vi_ra: "tay" }),
    buoc({ ten: "Bắt tay + vào keo", khoan_ten: "Bắt tay + vào keo gáy vuông",
           so_luong_vao: 5000, don_vi_vao: "tay", so_luong_ra: 1000, don_vi_ra: "cai" }),
    buoc({ ten: "Xén 3 mặt thành phẩm", khoan_ten: "Xén 3 mặt", don_vi_vao: "cai", don_vi_ra: "cai",
           so_luong_vao: 1000, so_luong_ra: 1000, vat_tus: [vt(6, "Màng cán bóng", 5200.07, "m2")] }),
    buoc({ ten: "Đóng gói + nhập kho", khoan_ten: "Đếm, bó, đóng gói", don_vi_vao: "cai",
           don_vi_ra: "cai", so_luong_vao: 1000, so_luong_ra: 1000 }),
  ];
}

function ke(congDoans: LsxCongDoan[]) {
  return bangKeVatTu({ congDoans });
}

describe("bangKeVatTu", () => {
  it("giấy nằm ở ĐÚNG bước người ta khai, không bị máy treo sang bước khác", () => {
    const b = ke(chuoiSach()).buocs;
    expect(b[0].dong).toHaveLength(0);      // ghi kẽm không khai gì thì trống, đừng nhét giấy vào
    const nvl = b[1].dong.filter((d) => d.nhom === "nvl");
    expect(nvl).toHaveLength(1);
    expect(nvl[0].ten).toBe("Ford 70 65×86");
    expect(nvl[0].so_luong).toBe(436.02);
    expect(nvl[0].chu_thich).toBe("NVL chính");
  });

  it("không bước nào khai giấy ⇒ bảng kê KHÔNG tự đẻ dòng NVL", () => {
    seq = 0;
    const r = ke([buoc({ vat_tus: [vt(2, "Mực", 5)] }), buoc()]);
    expect(r.tong.filter((t) => t.nhom === "nvl")).toHaveLength(0);
  });

  it("Giấy #7 và Vật tư #7 là HAI món — khoá gom phải mang cả danh mục", () => {
    // Trùng id giữa hai danh mục là chuyện thường. Gom bằng id trần thì kg giấy cộng thẳng vào
    // kg keo, ra một dòng vô nghĩa mà nhìn vẫn "có vẻ đúng".
    seq = 0;
    const r = ke([buoc({ vat_tus: [giay(7, "Ivory 350", 40), vt(7, "Keo dán", 3)] })]);
    expect(r.tong).toHaveLength(2);
    expect(r.tong.map((t) => t.khoa).sort()).toEqual(["giay:7", "vat_tu:7"]);
    expect(r.tong.find((t) => t.nhom === "nvl")?.so_luong).toBe(40);
  });

  it("vật tư khai ở HAI bước thì khối tổng phải CỘNG lại", () => {
    // Ca thật của LSX26-0004. Nhìn theo từng công đoạn chỉ thấy hai lần "5.200", tưởng là một —
    // mua theo đó là thiếu đúng một nửa.
    const t = ke(chuoiSach()).tong.find((x) => x.ten === "Màng cán bóng");
    expect(t?.so_luong).toBeCloseTo(10_400.14, 2);
    expect(t?.buocs).toEqual([20, 50]);
  });

  it("khuôn dùng ở hai bước vẫn là MỘT con dao — không cộng thành 2", () => {
    seq = 0;
    const dao = { khuon_be_id: 5, khuon_be_ma: "KB-0005", khuon_be_ten: "Dao bế hộp",
                  khuon_be_tinh_trang: "dang_dung", requires_tooling: true };
    const r = ke([buoc(dao), buoc(dao)]);
    const dc = r.tong.filter((x) => x.nhom === "dung_cu");
    expect(dc).toHaveLength(1);
    expect(dc[0].so_luong).toBeNull();     // dụng cụ không có số lượng để mà cộng
    expect(dc[0].buocs).toEqual([10, 20]);
  });

  it("cùng một món khai hai ĐƠN VỊ khác nhau ⇒ tách dòng, không cộng bừa", () => {
    // `3 kg + 2 tấn = 5` là số vô nghĩa. Tách ra thì người đọc thấy ngay là có chuyện.
    seq = 0;
    const r = ke([buoc({ vat_tus: [vt(9, "Keo", 3, "kg")] }),
                  buoc({ vat_tus: [vt(9, "Keo", 2, "tan")] })]);
    expect(r.tong.filter((x) => x.ten === "Keo")).toHaveLength(2);
  });

  it("đếm bước trống, bước chưa đầu việc và số món cho ô tóm tắt", () => {
    const r = ke(chuoiSach());
    expect(r.so_buoc_trong).toBe(4);          // #10 #30 #40 #60
    expect(r.so_buoc_chua_dau_viec).toBe(1);  // #10 ghi kẽm
    expect(r.so_mon).toBe(3);                 // giấy + màng + mực
  });

  it("bước bật cờ cần khuôn mà chưa gán thì nói ra", () => {
    seq = 0;
    const r = ke([buoc({ requires_tooling: true }), buoc({ requires_tooling: false })]);
    expect(r.buocs.map((b) => b.thieu_khuon)).toEqual([true, false]);
  });
});
