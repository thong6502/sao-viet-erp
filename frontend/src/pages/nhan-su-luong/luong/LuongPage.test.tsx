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

import {
  bhThueRows,
  bonusRows,
  hoaHongTotal,
  phatRows,
  phuCapRows,
  phuCapTotal,
} from "./shared/helpers";

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

/** Bảng lương phải hiện ĐỦ khoản TRỪ — trừ gì hiện nấy.
 *
 * 16/09/2026 — chủ mở bảng lương của NV "Test Luồng 0809": người này bị **Phạt biên bản
 * 50.000** (khai ở "Sửa dòng lương" → khối "Các khoản giảm trừ (phạt)"), tiền đã trừ thật vào
 * thực nhận và phiếu lương in đúng, nhưng cột "Vi phạm" trên bảng hiện dấu gạch vì cột đó chỉ
 * đọc mỗi `vi_pham`. Bốn ô phạt chi tiết + khoản danh mục loại TRỪ + đoàn phí + thuế TNCN đều
 * không cột nào kể ⇒ cộng các cột lại không ra thực nhận, kế toán dò mãi không thấy tiền đi đâu.
 */
describe("Bảng lương — cột giảm trừ kể đủ khoản trừ", () => {
  /** Dòng lương tối thiểu cho hai hàm cột TRỪ. */
  const dongTru = (o: Record<string, unknown> = {}) =>
    ({
      di_tre: 0, dt_vuot_troi: 0, phat_bien_ban: 0, phat_5s_dong_phuc: 0,
      vi_pham: 0, bhxh: 0, cong_doan: 0, pit: 0, components: [],
      ...o,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    }) as any;

  it("⭐ Phạt biên bản khai ở 'Sửa dòng lương' PHẢI ra cột phạt của bảng", () => {
    const rows = phatRows(dongTru({ phat_bien_ban: 50_000 }));
    expect(rows).toEqual([["Phạt biên bản", 50_000]]);
  });

  it("⭐ đủ 4 ô phạt chi tiết + 'Giảm trừ khác' + khoản danh mục loại TRỪ", () => {
    const rows = phatRows(
      dongTru({
        di_tre: 1, dt_vuot_troi: 2, phat_bien_ban: 3, phat_5s_dong_phuc: 4, vi_pham: 5,
        components: [
          { code: "mua_dp", name: "Mua đồng phục", kind: "tru", amount: 6, source: "line" },
          { code: "com_ca", name: "Cơm ca", kind: "thu", amount: 99, source: "line" },
        ],
      }),
    );
    expect(rows.map(([ten]) => ten)).toEqual([
      "Đi trễ / nghỉ KP", "Điện thoại vượt trội", "Phạt biên bản",
      "Đồng phục / phạt 5S", "Giảm trừ khác", "Mua đồng phục",
    ]);
    expect(rows.reduce((s2, [, v]) => s2 + v, 0)).toBe(21);
  });

  it("không phạt gì thì không đẻ dòng rỗng (bảng hiện dấu gạch)", () => {
    expect(phatRows(dongTru())).toEqual([]);
  });

  it("⭐ đoàn phí công đoàn và thuế TNCN cũng phải hiện, không chỉ mỗi BHXH", () => {
    const rows = bhThueRows(dongTru({ bhxh: 1_092_000, cong_doan: 52_000, pit: 200_000 }));
    expect(rows).toEqual([
      ["BHXH/BHYT/BHTN", 1_092_000],
      ["Đoàn phí công đoàn", 52_000],
      ["Thuế TNCN", 200_000],
    ]);
  });

  it("khoản THU không được lẻn vào cột trừ", () => {
    const rows = phatRows(
      dongTru({
        components: [
          { code: "thuong_nong", name: "Thưởng nóng", kind: "thu", amount: 500_000, source: "line" },
        ],
      }),
    );
    expect(rows).toEqual([]);
  });
});

/** Cột "Phụ cấp" phải kể đủ — cơm ca, cơm tăng ca, phụ cấp ca nằm NGOÀI `allowance`.
 *
 * 16/09/2026 — soát lại bảng lương kỳ 09/2026 sau khi vá cột phạt: cộng hết các cột THU của
 * NV002 vẫn thiếu đúng 100.000đ so với thực lĩnh, vì cơm tăng ca có trong `gross` của engine mà
 * không cột nào trên bảng kể. Ba khoản này phiếu lương in từng dòng riêng, bảng gộp vào cột
 * "Phụ cấp" (rê chuột ra chi tiết) — nhưng KHÔNG được bỏ quên.
 */
describe("Bảng lương — cột Phụ cấp gồm cả cơm ca và phụ cấp ca", () => {
  const dongPc = (o: Record<string, unknown> = {}) =>
    ({
      allowance: 0, meal_allowance_pay: 0, com_tang_ca_pay: 0, shift_allowance_pay: 0,
      ...o,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    }) as any;

  it("⭐ cơm tăng ca không được rơi khỏi bảng (NV002 kỳ 09/2026 lệch 100.000đ)", () => {
    expect(phuCapTotal(dongPc({ allowance: 170_308, com_tang_ca_pay: 100_000 }))).toBe(270_308);
  });

  it("⭐ đủ 4 khoản, đúng tên như phiếu lương", () => {
    const rows = phuCapRows(
      dongPc({
        allowance: 1, meal_allowance_pay: 2, com_tang_ca_pay: 3, shift_allowance_pay: 4,
      }),
    );
    expect(rows).toEqual([
      ["Phụ cấp khác", 1],
      ["Cơm ca", 2],
      ["Cơm tăng ca", 3],
      ["Phụ cấp ca (theo ca làm)", 4],
    ]);
  });

  it("khoản nào 0 thì không đẻ dòng trong tooltip", () => {
    expect(phuCapRows(dongPc({ allowance: 500_000 }))).toEqual([["Phụ cấp khác", 500_000]]);
    expect(phuCapRows(dongPc())).toEqual([]);
  });

  it("dòng lương cũ thiếu hẳn 3 ô (kỳ trước khi có cơm ca) vẫn ra số, không NaN", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(phuCapTotal({ allowance: 300_000 } as any)).toBe(300_000);
  });
});
