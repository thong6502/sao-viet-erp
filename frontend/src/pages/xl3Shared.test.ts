import { describe, expect, it } from "vitest";

import { khungLuoi, loiKhoangNgay, nacCuaSo, soNgayGiua } from "./xl3Shared";

describe("khungLuoi với khoảng ngày tự chọn", () => {
  it("ba nút 7/14/30 giữ đúng số cũ trên màn rộng", () => {
    expect(khungLuoi(1600, 7).ngayW).toBe(168);
    expect(khungLuoi(1600, 14).ngayW).toBe(96);
    expect(khungLuoi(1600, 30).ngayW).toBe(54);
  });

  it("khoảng lẻ rơi vào nấc gần nhất thay vì về cỡ 7 ngày", () => {
    expect(nacCuaSo(9)).toBe(7);
    expect(nacCuaSo(10)).toBe(14);
    expect(nacCuaSo(20)).toBe(14);
    expect(nacCuaSo(21)).toBe(30);
    expect(khungLuoi(1600, 20).ngayW).toBe(96);
    expect(khungLuoi(1600, 45).ngayW).toBe(54);
  });
});

describe("soNgayGiua", () => {
  it("đếm cả hai đầu, qua tháng và qua năm", () => {
    expect(soNgayGiua("2026-09-14", "2026-09-14")).toBe(1);
    expect(soNgayGiua("2026-09-14", "2026-10-13")).toBe(30);
    expect(soNgayGiua("2026-12-30", "2027-01-02")).toBe(4);
  });
});

describe("loiKhoangNgay", () => {
  it("khoảng hợp lệ trả null", () => {
    expect(loiKhoangNgay("2026-09-14", "2026-10-03")).toBeNull();
  });

  it("chặn ô trống, năm 6 chữ số, ngày cuối trước ngày đầu, quá trần", () => {
    expect(loiKhoangNgay("", "2026-10-03")).toMatch(/Chọn đủ/);
    expect(loiKhoangNgay("202026-09-14", "2026-10-03")).toMatch(/không hợp lệ/);
    expect(loiKhoangNgay("0020-09-14", "2026-10-03")).toMatch(/không hợp lệ/);
    expect(loiKhoangNgay("2026-10-03", "2026-09-14")).toMatch(/từ ngày bắt đầu/);
    expect(loiKhoangNgay("2026-09-01", "2026-10-30")).toBeNull();
    expect(loiKhoangNgay("2026-09-01", "2026-10-31")).toMatch(/tối đa 60 ngày/);
  });
});
