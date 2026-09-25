import { describe, expect, it } from "vitest";
import type { SalaryAdvance } from "../../../../api/client";
import { BO_LOC_TRONG, demTheoTab, dsTo, khopBoLoc, tachLoai, thuocTab } from "./tamUngLoc";

function phieu(p: Partial<SalaryAdvance>): SalaryAdvance {
  return {
    id: 1, code: "TU-260925-AAAA", employee_id: 1, employee_name: "Nguyễn Văn An",
    employee_code: "NV001", department_id: 10, department_name: "Tổ In",
    bank_account: null, bank_name: null, period_year: 2026,
    period_month: 9, advance_date: "2026-09-15", amount: 1_000_000, reason: null,
    kind: "tam_ung", status: "pending", decision_note: null, created_at: "2026-09-15T00:00:00Z",
    ...p,
  } as SalaryAdvance;
}

describe("tab trạng thái", () => {
  it("chờ chi = đã duyệt mà CHƯA có phiếu chi; có phiếu chi thì sang Đã chi", () => {
    const a = phieu({ status: "approved" });
    const b = phieu({ status: "approved", phieu_chi_id: 9, phieu_chi_code: "PC-1" });
    expect(thuocTab(a, "cho_chi")).toBe(true);
    expect(thuocTab(b, "cho_chi")).toBe(false);
    expect(thuocTab(b, "da_chi")).toBe(true);
    expect(thuocTab(phieu({ status: "paid" }), "da_chi")).toBe(true);
    expect(thuocTab(phieu({ status: "cancelled" }), "tu_choi")).toBe(true);
    expect(thuocTab(phieu({ status: "rejected" }), "tat_ca")).toBe(true);
  });
});

describe("bộ lọc", () => {
  it("lọc loại, tổ, và tìm KHÔNG DẤU theo tên / mã NV / mã phiếu", () => {
    const a = phieu({});
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, loai: "luong_dot_1" })).toBe(false);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, loai: "tam_ung" })).toBe(true);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, to: "11" })).toBe(false);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, to: "10" })).toBe(true);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, tim: "nguyen an" })).toBe(true);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, tim: "nv001" })).toBe(true);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, tim: "aaaa" })).toBe(true);
    expect(khopBoLoc(a, { ...BO_LOC_TRONG, tim: "binh" })).toBe(false);
  });

  it("số trên nhãn tab tính SAU bộ lọc loại", () => {
    const ds = [
      phieu({ id: 1, status: "pending" }),
      phieu({ id: 2, status: "pending", kind: "luong_dot_1" }),
      phieu({ id: 3, status: "approved" }),
    ];
    const dem = demTheoTab(ds, { ...BO_LOC_TRONG, loai: "tam_ung" });
    expect(dem).toMatchObject({ tat_ca: 2, cho_duyet: 1, cho_chi: 1, da_chi: 0 });
  });

  it("danh sách tổ không trùng, xếp theo tên", () => {
    const ds = [
      phieu({ id: 1, department_id: 2, department_name: "Tổ Xén" }),
      phieu({ id: 2, department_id: 1, department_name: "Tổ Bế" }),
      phieu({ id: 3, department_id: 2, department_name: "Tổ Xén" }),
    ];
    expect(dsTo(ds).map((t) => t.ten)).toEqual(["Tổ Bế", "Tổ Xén"]);
  });
});

describe("hộp xác nhận tách theo loại", () => {
  it("đếm từng loại và tổng tiền", () => {
    const ds = [
      phieu({ id: 1, amount: 1_000_000 }),
      phieu({ id: 2, amount: 2_500_000, kind: "luong_dot_1" }),
      phieu({ id: 3, amount: 500_000 }),
    ];
    expect(tachLoai(ds)).toBe("2 tạm ứng · 1 lương đợt 1 — tổng 4.000.000đ");
  });
});
