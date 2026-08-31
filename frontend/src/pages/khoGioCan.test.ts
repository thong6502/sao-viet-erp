import { describe, expect, it } from "vitest";

import { fmtGioCan, isOverdue } from "./khoShared";

/** `can_luc` naive = giờ NHÀ MÁY (wall-clock), không phải UTC — quy ước của phân hệ sản xuất
 *  (`xep_lich_service._naive`). Ô "Cần lúc" bên kho phải hiện đúng con số tổ trưởng đã gõ, và phải
 *  khớp với badge "Quá hạn" ngồi ngay cạnh nó. */
describe("fmtGioCan — giờ cần của đề nghị sản xuất", () => {
  it("hiện đúng giờ wall-clock, KHÔNG cộng thêm 7 tiếng", () => {
    // Tổ trưởng gõ 31/08/2026 17:56. Coi naive = UTC sẽ ra "1/9/2026 00:56" — lệch ngày.
    expect(fmtGioCan("2026-08-31T17:56:00")).toBe("31/8/2026 17:56");
  });

  it("giữ nguyên ngày với giờ sát nửa đêm", () => {
    expect(fmtGioCan("2026-08-31T23:30:00")).toBe("31/8/2026 23:30");
  });

  it("rỗng → gạch ngang; chuỗi không parse được → trả nguyên", () => {
    expect(fmtGioCan(null)).toBe("—");
    expect(fmtGioCan("")).toBe("—");
    expect(fmtGioCan("hôm nào đó")).toBe("hôm nào đó");
  });

  it("nói CÙNG một giờ với isOverdue — một ô không được nói hai giờ", () => {
    // 17:56 hôm nay đã trôi qua lúc 23:00 ⇒ badge "Quá hạn" bật. Chuỗi hiện ra cũng phải là 17:56
    // của chính ngày đó, chứ không phải 00:56 hôm sau.
    const canLuc = "2026-08-31T17:56:00";
    const luc23h = new Date(2026, 7, 31, 23, 0).getTime();
    const thatSu = new Date(canLuc).getTime();
    expect(thatSu).toBeLessThan(luc23h);
    expect(fmtGioCan(canLuc)).toContain("17:56");
  });
});

describe("isOverdue — mốc trễ theo GIỜ khi có can_luc", () => {
  it("chưa tới giờ cần thì chưa trễ", () => {
    const sau = new Date(Date.now() + 3_600_000);
    const iso = `${sau.getFullYear()}-${String(sau.getMonth() + 1).padStart(2, "0")}-${String(sau.getDate()).padStart(2, "0")}T${String(sau.getHours()).padStart(2, "0")}:${String(sau.getMinutes()).padStart(2, "0")}:00`;
    expect(isOverdue(null, "pending", iso)).toBe(false);
  });

  it("qua giờ cần thì trễ", () => {
    expect(isOverdue(null, "pending", "2020-01-01T08:00:00")).toBe(true);
  });

  it("yêu cầu đã đóng sổ thì không cảnh báo nữa", () => {
    expect(isOverdue(null, "done", "2020-01-01T08:00:00")).toBe(false);
  });
});
