import { afterEach, describe, expect, it, vi } from "vitest";
import type { BangKeTamUng } from "../api/client";
import { printBangKeTamUng } from "./printBangKeTamUng";

function bangKe(p: Partial<BangKeTamUng> = {}): BangKeTamUng {
  return {
    voucher_id: 80, code: "PC-260925-PG4A", doc_no: "PC00076", voucher_type: "cash",
    voucher_date: "2026-09-25", content: "Tạm ứng lương tháng 09/2026 — 2 người (theo bảng kê)",
    status: "paid", so_nguoi: 2, tong: 40_000,
    rows: [
      { salary_advance_id: 59, ma_phieu: "TU-260925-K4LJ", kind: "tam_ung", employee_id: 1,
        ma_nv: "NV011", ten: "LM Công nhật", department_id: 16, department_name: "Tổ Bồi",
        so_tien: 20_000, so_tai_khoan: null, ngan_hang: null },
      { salary_advance_id: 60, ma_phieu: "TU-260925-LQ4V", kind: "tam_ung", employee_id: 2,
        ma_nv: "NV012", ten: "LM Khoán cao", department_id: 17, department_name: "Tổ In",
        so_tien: 20_000, so_tai_khoan: "0908872122", ngan_hang: "MB" },
    ],
    ...p,
  };
}

function inRa(bk: BangKeTamUng): string {
  let html = "";
  const win = {
    document: { write: (s: string) => (html += s), close: () => {} },
    focus: () => {},
  };
  vi.spyOn(window, "open").mockReturnValue(win as unknown as Window);
  expect(printBangKeTamUng(bk)).toBe(true);
  return html;
}

afterEach(() => vi.restoreAllMocks());

describe("bảng kê đính kèm phiếu chi tạm ứng", () => {
  it("tiền mặt: có cột KÝ NHẬN, không cột tài khoản; đủ dòng + tổng", () => {
    const html = inRa(bangKe());
    expect(html).toContain("BẢNG KÊ CHI TẠM ỨNG LƯƠNG");
    expect(html).toContain("Kèm theo phiếu chi số <b>PC00076</b>");
    expect(html).toContain("Ký nhận");
    expect(html).not.toContain("Số tài khoản");
    expect(html).toContain("LM Công nhật");
    expect(html).toContain("TU-260925-LQ4V");
    expect(html).toContain("40.000");
  });

  it("chuyển khoản: cột số tài khoản + ngân hàng, gọi là ủy nhiệm chi", () => {
    const html = inRa(bangKe({ voucher_type: "bank_transfer", code: "UNC-260925-AAAA" }));
    expect(html).toContain("ủy nhiệm chi");
    expect(html).toContain("Số tài khoản");
    expect(html).toContain("0908872122");
    expect(html).not.toContain("Ký nhận");
  });

  it("trình duyệt chặn pop-up ⇒ trả false để nơi gọi báo", () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    expect(printBangKeTamUng(bangKe())).toBe(false);
  });
});
