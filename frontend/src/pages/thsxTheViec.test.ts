/** Hai câu chữ mà THẺ VIỆC ở bàn tổ tự dựng từ ảnh chụp lúc phát hành
 *  (`docs/superpowers/specs/2026-09-10-ban-to-du-thong-tin-design.md` §3.4 · §7).
 *
 *  · `slText`       — bước NGOÀI dòng giấy in MỘT số ("4 bản kẽm"), bước trên dòng giữ mũi tên.
 *  · `phutChayText` — "13 phút (11 – 15)"; ba số bằng nhau thì bỏ hẳn phần ngoặc.
 *
 *  Danh mục Đơn vị nạp qua `useNapTenDonVi` nên trong test nó RỖNG — `nhanChang` rơi về mã trần.
 *  Đó chính là hành vi cần cho ở đây: bài này soi CẤU TRÚC câu, không soi nhãn đơn vị.
 */
import { describe, expect, it } from "vitest";

import type { SxWorkItem } from "../api/client";
import { phutChayText, slText } from "./thsxShared";

function viec(p: Partial<SxWorkItem>): SxWorkItem {
  return {
    ngoai_dong: false,
    so_luong_vao: null, so_luong_ra: null, don_vi_vao: null, don_vi_ra: null,
    chay_phut: null, chay_phut_min: null, chay_phut_max: null,
    ...p,
  } as SxWorkItem;
}

describe("slText — khối lượng của một thẻ việc", () => {
  it("bước NGOÀI dòng giấy: một số kèm đơn vị bản địa, KHÔNG mũi tên", () => {
    // Ghi kẽm CTP: vào = ra = 4 vì nó không ăn tờ giấy nào; "4 → 4" chỉ là nhiễu.
    const t = slText(viec({ ngoai_dong: true, so_luong_vao: 4, so_luong_ra: 4, don_vi_vao: "kem", don_vi_ra: "kem" }));
    expect(t).toBe("4 kem");
    expect(t).not.toContain("→");
  });

  it("bước ngoài dòng thiếu `don_vi_ra` vẫn lấy được đơn vị ở vế vào", () => {
    expect(slText(viec({ ngoai_dong: true, so_luong_ra: 4, don_vi_vao: "kem" }))).toBe("4 kem");
  });

  it("bước TRÊN dòng giấy: giữ nguyên mũi tên hai vế (hồi quy)", () => {
    expect(slText(viec({
      so_luong_vao: 2750, so_luong_ra: 2700, don_vi_vao: "to", don_vi_ra: "to",
    }))).toBe("2.750 to → 2.700 to");
  });

  it("chưa có số thì hiện gạch, không hiện 0 — 0 là 'đã chạy mà ra 0'", () => {
    expect(slText(viec({}))).toBe("— → —");
  });
});

describe("phutChayText — dải phút chạy", () => {
  it("máy có khai dải tốc độ: số giữa kèm ngoặc", () => {
    expect(phutChayText(viec({ chay_phut: 13.4, chay_phut_min: 11.2, chay_phut_max: 15.1 })))
      .toBe("13 phút (11 – 15)");
  });

  it("ba số bằng nhau (máy chưa khai min/max): bỏ hẳn ngoặc", () => {
    expect(phutChayText(viec({ chay_phut: 13, chay_phut_min: 13, chay_phut_max: 13 }))).toBe("13 phút");
  });

  it("min/max thiếu thì coi như bằng số giữa, không dựng ngoặc rỗng", () => {
    expect(phutChayText(viec({ chay_phut: 13 }))).toBe("13 phút");
  });

  it("ảnh chụp CŨ chưa có khoá ⇒ null để nơi gọi bỏ hẳn dòng", () => {
    expect(phutChayText(viec({}))).toBeNull();
  });

  it("bước không có máy (0 phút) cũng null — '0 phút' là con số bịa", () => {
    expect(phutChayText(viec({ chay_phut: 0, chay_phut_min: 0, chay_phut_max: 0 }))).toBeNull();
  });
});
