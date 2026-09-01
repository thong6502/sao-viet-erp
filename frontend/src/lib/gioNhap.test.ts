import { describe, expect, it } from "vitest";

import { GIO_NHAP_MAX, GIO_NHAP_MIN, gioNhapHopLe, gioNhapSai } from "./gioNhap";

/**
 * Ô `datetime-local` là nguồn "giá trị rác" thật đã gặp trên bàn Xếp lịch 2: gõ đè vào ô NĂM ra
 * "92026-03-01T20:00" / "202608-09-03T12:00" — trình duyệt coi là hợp lệ (chuẩn HTML cho năm tới
 * 275760), màn chỉ soi "khác rỗng" nên vẫn gửi, và backend trả 422 câm. `min`/`max` chặn được ở
 * Chrome nhưng KHÔNG phải mọi trình duyệt/thiết bị, nên lớp kiểm này là chốt chặn thứ hai.
 */
describe("gioNhapHopLe", () => {
  it("nhận khuôn phút và khuôn có giây", () => {
    expect(gioNhapHopLe("2026-09-01T17:00")).toBe(true);
    expect(gioNhapHopLe("2026-09-01T17:00:30")).toBe(true);
  });

  it("loại năm quá 4 chữ số — đúng hai giá trị rác đã gặp trên UI", () => {
    expect(gioNhapHopLe("92026-03-01T20:00")).toBe(false);
    expect(gioNhapHopLe("202608-09-03T12:00")).toBe(false);
  });

  it("loại giá trị gõ dở hoặc sai khuôn", () => {
    expect(gioNhapHopLe("2026-09-01")).toBe(false);
    expect(gioNhapHopLe("2026-09-01T17")).toBe(false);
    expect(gioNhapHopLe("bậy")).toBe(false);
  });

  it("loại mốc ngoài khoảng dùng được", () => {
    expect(gioNhapHopLe("1999-12-31T23:59")).toBe(false);
    expect(gioNhapHopLe("2100-01-01T00:00")).toBe(false);
    expect(gioNhapHopLe(GIO_NHAP_MIN)).toBe(true);
    expect(gioNhapHopLe(GIO_NHAP_MAX)).toBe(true);
  });

  it("ô TRỐNG không hợp lệ nhưng cũng KHÔNG phải sai", () => {
    // Phân biệt này là cốt lõi: trống = chưa gõ (nhiều màn hiểu là 'gỡ giờ' / 'lấy giờ bấm nút'),
    // còn sai = có gõ mà không dùng được ⇒ mới hiện lời nhắc và khoá nút.
    expect(gioNhapHopLe("")).toBe(false);
    expect(gioNhapSai("")).toBe(false);
    expect(gioNhapSai(null)).toBe(false);
    expect(gioNhapSai("92026-03-01T20:00")).toBe(true);
  });
});
