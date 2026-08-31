import { describe, expect, it } from "vitest";

import { vtPayloadLines } from "./ThsxExecPanels";

/** Dòng kế hoạch mẫu — Ivory 350, kế hoạch 554 tờ. */
function dong(over: Partial<Parameters<typeof vtPayloadLines>[0][number]> = {}) {
  return {
    key: "vat_tu:7",
    hang_loai: "vat_tu",
    hang_id: 7,
    ten: "Ivory 350 79×109",
    dvt: "to",
    dvtKeHoach: "to",
    sl_ke_hoach: 554,
    sl_yeu_cau: 554,
    slText: "554",
    ly_do_chenh_lech: "",
    tuKeHoach: true,
    ...over,
  };
}

describe("vtPayloadLines — lý do chỉ đi theo khi ô Lý do đang mở", () => {
  it("dòng lệch: giữ nguyên lý do tổ vừa gõ", () => {
    const [ln] = vtPayloadLines([dong({ sl_yeu_cau: 600, slText: "600", ly_do_chenh_lech: "Bù hao chỉnh màu" })], "lan_dau");
    expect(ln.sl_yeu_cau).toBe(600);
    expect(ln.ly_do_chenh_lech).toBe("Bù hao chỉnh màu");
  });

  it("kéo về ĐÚNG kế hoạch: lý do cũ KHÔNG đi theo", () => {
    // Ô Lý do đã đóng (554 = 554) nhưng state vẫn giữ câu gõ lúc còn lệch. Gửi lên thì bảng đối
    // chiếu ghi "không lệch" mà vẫn kèm lý do — mâu thuẫn ngay trên một dòng.
    const [ln] = vtPayloadLines([dong({ ly_do_chenh_lech: "Đổi kế hoạch in, tổ chưa cần cấp giấy" })], "lan_dau");
    expect(ln.sl_yeu_cau).toBe(554);
    expect(ln.ly_do_chenh_lech).toBeNull();
  });

  it("về 0 vẫn là lệch: lý do đi theo", () => {
    const [ln] = vtPayloadLines([dong({ sl_yeu_cau: 0, slText: "0", ly_do_chenh_lech: "Tổ chưa cần" })], "lan_dau");
    expect(ln.sl_yeu_cau).toBe(0);
    expect(ln.ly_do_chenh_lech).toBe("Tổ chưa cần");
  });

  it("lần BỔ SUNG: lý do luôn bắt buộc nên luôn đi theo", () => {
    const ra = vtPayloadLines([dong({ sl_yeu_cau: 30, slText: "30", ly_do_chenh_lech: "Rách khi bế" })], "bo_sung");
    expect(ra).toHaveLength(1);
    expect(ra[0].ly_do_chenh_lech).toBe("Rách khi bế");
  });

  it("lý do toàn khoảng trắng → null, không phải chuỗi rỗng", () => {
    const [ln] = vtPayloadLines([dong({ sl_yeu_cau: 600, slText: "600", ly_do_chenh_lech: "   " })], "lan_dau");
    expect(ln.ly_do_chenh_lech).toBeNull();
  });
});
