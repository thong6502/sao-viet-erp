/** Bảng lương: hoa hồng phải có CỘT RIÊNG, không lẫn vào cột "Thưởng".
 *
 * Chỗ này đã hỏng HAI lần, mỗi lần một kiểu — nên khoá cả hai chiều:
 *
 *  1. 21/08/2026 — cột "Thưởng" chỉ cộng `source='line'` ⇒ hoa hồng (nguồn `auto`) lọt vào cột
 *     "Tổng" mà KHÔNG cột nào giải thích. Kế toán dò lệch mãi không ra.
 *  2. 24/08/2026 — vá kiểu trên thành giấu chỗ khác: hoa hồng cộng gộp vào "Thưởng", chi tiết chỉ
 *     hiện khi RÊ CHUỘT. Chủ mở bảng lương tìm cột hoa hồng không thấy, tưởng chưa làm.
 *
 * Bài học: tiền do MÁY tự tính từ phân hệ khác thì phải có cột mang ĐÚNG TÊN nó. Bỏ sót và gộp
 * chung đều dẫn tới cùng một hậu quả — người đọc bảng không truy được tiền từ đâu ra.
 *
 * Giữ ĐỒNG BỘ với `_bonus_total()` / `_hoa_hong_total()` ở `routers/payroll.py`.
 */
import { describe, expect, it } from "vitest";

import { bonusRows, hoaHongTotal } from "./LuongPage";

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

/** Dòng lương tối thiểu: 6 cột thưởng cũ đã ngừng ghi nên để 0, chỉ còn `components` nói chuyện. */
const dong = (components: Khoan[]) =>
  ({
    components,
    other_bonus: 0, thuong_5s: 0, thuong_doanh_so: 0,
    thuong_thanh_tich: 0, phep_nam: 0, tra_dong_phuc: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }) as any;

const HOA_HONG = khoan({
  code: "hoa_hong_kd", name: "Hoa hồng kinh doanh", amount: 5_000_000, source: "auto",
});
const THUONG_NONG = khoan({ code: "thuong_nong", name: "Thưởng nóng", amount: 500_000 });

describe("Bảng lương — hoa hồng tách khỏi Thưởng", () => {
  it("⭐ cột Hoa hồng nhận đủ tiền", () => {
    expect(hoaHongTotal(dong([HOA_HONG, THUONG_NONG]))).toBe(5_000_000);
  });

  it("⭐ cột Thưởng KHÔNG còn chứa hoa hồng — cộng hai cột lại không được đếm đôi", () => {
    const rows = bonusRows(dong([HOA_HONG, THUONG_NONG]));
    expect(rows.map(([ten]) => ten)).toEqual(["Thưởng nóng"]);
    expect(rows.reduce((s, [, v]) => s + v, 0)).toBe(500_000);
  });

  it("khoản `auto` KHÁC hoa hồng vẫn ở lại cột Thưởng, không được biến mất", () => {
    // Lọc theo `source==='auto'` thay vì theo MÃ là làm mọi khoản auto tương lai (khoán km…)
    // rơi khỏi bảng — có tiền trong "Tổng" mà không cột nào cộng ra.
    const khac = khoan({ code: "auto_khac", name: "Khoản auto khác", amount: 111, source: "auto" });
    expect(bonusRows(dong([HOA_HONG, khac])).map(([t]) => t)).toEqual(["Khoản auto khác"]);
  });

  it("khoản từ HỒ SƠ (`employee`) không vào cột Thưởng — nó đã nằm ở cột Phụ cấp", () => {
    const hoSo = khoan({ code: "com_ca", name: "Cơm ca", amount: 300_000, source: "employee" });
    expect(bonusRows(dong([hoSo]))).toEqual([]);
  });

  it("khoản TRỪ không được cộng vào cột nào trong hai cột này", () => {
    const tru = khoan({ code: "hoa_hong_kd", name: "Truy thu HH", kind: "tru", amount: 9, source: "auto" });
    expect(hoaHongTotal(dong([tru]))).toBe(0);
    expect(bonusRows(dong([tru]))).toEqual([]);
  });

  it("chưa khai % hoa hồng ⇒ 0, không phải NaN hay undefined", () => {
    expect(hoaHongTotal(dong([]))).toBe(0);
  });
});
