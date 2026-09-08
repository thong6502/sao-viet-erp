/** Bảng lương: hoa hồng phải có CỘT RIÊNG, không lẫn vào cột "Thưởng".
 *
 * Chỗ này đã hỏng HAI lần, mỗi lần một kiểu — nên khoá cả hai chiều:
 *
 *  1. 21/08/2026 — cột "Thưởng" chỉ cộng `source='line'` ⇒ hoa hồng (khi đó là dòng `auto`) lọt
 *     vào cột "Tổng" mà KHÔNG cột nào giải thích. Kế toán dò lệch mãi không ra.
 *  2. 24/08/2026 — vá kiểu trên thành giấu chỗ khác: hoa hồng cộng gộp vào "Thưởng", chi tiết chỉ
 *     hiện khi RÊ CHUỘT. Chủ mở bảng lương tìm cột hoa hồng không thấy, tưởng chưa làm.
 *
 * Từ 07/09/2026 hoa hồng là cột `hoa_hong` trên dòng lương (không còn dòng khoản `auto`).
 * Giữ ĐỒNG BỘ với `_bonus_total()` / `_hoa_hong_total()` ở `routers/payroll.py`.
 */
import { describe, expect, it } from "vitest";

import { bonusRows, hoaHongTotal } from "./shared/helpers";

type Khoan = {
  code: string;
  name: string;
  kind: string;
  amount: number;
  source: string;
};

const khoan = (o: Partial<Khoan>): Khoan => ({
  code: "x", name: "X", kind: "thu", amount: 0, source: "line", ...o,
});

/** Dòng lương tối thiểu: 6 cột thưởng cũ đã ngừng ghi nên để 0, chỉ còn `components` + cột hoa hồng. */
const dong = (components: Khoan[], hoa_hong = 0) =>
  ({
    components,
    hoa_hong,
    other_bonus: 0, thuong_5s: 0, thuong_doanh_so: 0,
    thuong_thanh_tich: 0, phep_nam: 0, tra_dong_phuc: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }) as any;

const THUONG_NONG = khoan({ code: "thuong_nong", name: "Thưởng nóng", amount: 500_000 });

describe("Bảng lương — hoa hồng tách khỏi Thưởng", () => {
  it("⭐ cột Hoa hồng đọc thẳng cột `hoa_hong` của dòng lương", () => {
    expect(hoaHongTotal(dong([THUONG_NONG], 5_000_000))).toBe(5_000_000);
  });

  it("⭐ cột Thưởng KHÔNG chứa hoa hồng — cộng hai cột lại không được đếm đôi", () => {
    const rows = bonusRows(dong([THUONG_NONG], 5_000_000));
    expect(rows.map(([ten]) => ten)).toEqual(["Thưởng nóng"]);
    expect(rows.reduce((s, [, v]) => s + v, 0)).toBe(500_000);
  });

  it("dòng `auto` cũ (dữ liệu trước 07/09/2026) không được lẻn vào cột Thưởng", () => {
    const cu = khoan({ code: "hoa_hong_kd", name: "Hoa hồng kinh doanh", amount: 111, source: "auto" });
    expect(bonusRows(dong([cu]))).toEqual([]);
  });

  it("khoản từ HỒ SƠ (`employee`) không vào cột Thưởng — nó đã nằm ở cột Phụ cấp", () => {
    const hoSo = khoan({ code: "com_ca", name: "Cơm ca", amount: 300_000, source: "employee" });
    expect(bonusRows(dong([hoSo]))).toEqual([]);
  });

  it("khoản TRỪ không được cộng vào cột Thưởng", () => {
    const tru = khoan({ code: "truy_thu", name: "Truy thu", kind: "tru", amount: 9 });
    expect(bonusRows(dong([tru]))).toEqual([]);
  });

  it("chưa khai % hoa hồng ⇒ 0, không phải NaN hay undefined", () => {
    expect(hoaHongTotal(dong([]))).toBe(0);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(hoaHongTotal({ components: [] } as any)).toBe(0);
  });
});
