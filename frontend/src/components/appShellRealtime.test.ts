import { describe, expect, it } from "vitest";
import { coQuyenBanTo } from "./appShellRealtime";

describe("Cổng Bàn tổ", () => {
  it("chỉ mở khi có Xem ở ít nhất một dòng tổ — Kế hoạch SX (`san_xuat`) không tính", () => {
    expect(coQuyenBanTo(new Set(["to_sx_5"]))).toBe(true);
    expect(coQuyenBanTo(new Set(["san_xuat", "lenh_san_xuat"]))).toBe(false);
  });
});
