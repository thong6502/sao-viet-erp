import { describe, expect, it } from "vitest";

import type { PhieuMuaTom } from "../api/client";
import { moTaPhieuMua, nhanTrangThaiPhieu, tomTatPhieuMua } from "./phieuMuaNhan";

function p(x: Partial<PhieuMuaTom>): PhieuMuaTom {
  return { ma: "PMH-1", loai: "pmh", trang_thai: "purchased", ngay_ve: null, ...x };
}

describe("nhãn phiếu đang chạy", () => {
  it("có ngày về thì NÓI NGÀY, không nói thủ tục", () => {
    // Người lập kế hoạch cần biết "bao giờ có hàng"; "đã duyệt hay chưa" là việc nội bộ của thu mua.
    expect(moTaPhieuMua(p({ ma: "PMH-VT-02", ngay_ve: "2026-09-01" }))).toBe("PMH-VT-02 · về 1/9");
  });

  it("chưa hẹn ngày thì lùi về trạng thái, KHÔNG bỏ trống", () => {
    // Bỏ trống là quay lại đúng chỗ hỏng: nhìn y hệt "chưa ai mua".
    expect(moTaPhieuMua(p({ ma: "PMH-9", trang_thai: "purchased" }))).toBe("PMH-9 · đã đặt");
    expect(moTaPhieuMua(p({ ma: "YC-1", loai: "ycmh", trang_thai: "open" }))).toBe(
      "YC-1 · mới đề nghị",
    );
  });

  it("trạng thái lạ thì trả nguyên chuỗi — nuốt là mất dấu vết", () => {
    expect(nhanTrangThaiPhieu(p({ trang_thai: "trang_thai_moi" }))).toBe("trang_thai_moi");
  });

  it("chip lấy phiếu ĐẦU (server đã xếp chắc → lỏng) và đếm phần còn lại", () => {
    const kq = tomTatPhieuMua([
      p({ ma: "PMH-3", ngay_ve: "2026-09-01" }),
      p({ ma: "PMH-1", trang_thai: "pending_approval" }),
      p({ ma: "YC-2", loai: "ycmh", trang_thai: "open" }),
    ]);
    expect(kq?.chinh).toBe("PMH-3 · về 1/9");
    expect(kq?.them).toBe(2);
    // Tooltip phải kê ĐỦ: hai phiếu cùng món nằm cạnh nhau chính là dấu hiệu đã đề nghị trùng.
    expect(kq?.title).toContain("PMH-1 · chờ duyệt");
    expect(kq?.title).toContain("YC-2 · mới đề nghị");
  });

  it("không có phiếu nào thì trả null — không đẻ khối rỗng lên màn", () => {
    expect(tomTatPhieuMua([])).toBeNull();
    expect(tomTatPhieuMua(undefined)).toBeNull();
  });
});
