import { describe, expect, it } from "vitest";

import {
  BAI_GHEP_2_TABS,
  coTheTaoBai,
  giuLuaChonSauTai,
  quyetDinhRealtime,
  trangThaiUngVien,
} from "./baiGhep2Rules";

describe("quy tắc giao diện Bài ghép 2", () => {
  it("chỉ cho tạo bài khi đã chọn ít nhất hai LSX", () => {
    expect(coTheTaoBai(new Set([11]))).toBe(false);
    expect(coTheTaoBai(new Set([11, 12]))).toBe(true);
  });

  it("có đúng năm tab nghiệp vụ theo thứ tự của LSX", () => {
    expect(BAI_GHEP_2_TABS.map((tab) => tab.label)).toEqual([
      "Thông tin chung",
      "Quy cách",
      "Công đoạn",
      "Vật tư",
      "Nhật ký",
    ]);
  });

  it("chỉ làm sáng bước cùng công đoạn ở LSX khác và được server chấp nhận", () => {
    const selected = { lsxId: 1, congDoanId: 20, stepKey: "a" };
    const verdict = { gop_duoc: true, ly_do: null };

    expect(trangThaiUngVien(selected, { lsxId: 2, congDoanId: 20, stepKey: "b" }, verdict)).toBe("eligible");
    expect(trangThaiUngVien(selected, { lsxId: 2, congDoanId: 30, stepKey: "c" }, verdict)).toBe("blocked");
    expect(trangThaiUngVien(selected, { lsxId: 1, congDoanId: 20, stepKey: "d" }, verdict)).toBe("blocked");
    expect(trangThaiUngVien(selected, { lsxId: 3, congDoanId: 20, stepKey: "e" }, { gop_duoc: false, ly_do: "chu trình" })).toBe("blocked");
  });

  it("tìm kiếm không xóa lựa chọn đang nằm ngoài kết quả lọc", () => {
    expect([...giuLuaChonSauTai(new Set([1, 2]), [2], "LSX-2")]).toEqual([1, 2]);
    expect([...giuLuaChonSauTai(new Set([1, 2]), [2], "")]).toEqual([2]);
  });

  it("SSE chỉ đánh stale khi có draft; còn lại refetch cả tab đang mở", () => {
    expect(quyetDinhRealtime(true, "vattu")).toEqual({ stale: true, refresh: [] });
    expect(quyetDinhRealtime(false, "vattu")).toEqual({ stale: false, refresh: ["detail", "vattu"] });
    expect(quyetDinhRealtime(false, "nhatky")).toEqual({ stale: false, refresh: ["detail", "nhatky"] });
  });
});
