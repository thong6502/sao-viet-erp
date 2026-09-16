/** Hình học + chữ của LỊCH NGÀY bàn tổ: thanh dính theo NGUYÊN NGÀY, giờ viết trong thanh. */
import { describe, expect, it } from "vitest";

import type { SxWorkItem } from "../api/client";
import { coThanh, dayThucTe, dongHaiThanh, oNgay } from "./ThsxLichNgay";

function viec(p: Partial<SxWorkItem>): SxWorkItem {
  return { trang_thai: "released", thuc_te: [], ...p } as SxWorkItem;
}

const TU = "2026-09-14"; // thứ Hai

describe("oNgay — ô ngày mà quãng kế hoạch chạm", () => {
  it("việc 4 phút trong một ngày vẫn chiếm trọn ô ngày đó", () => {
    expect(oNgay("2026-09-15T08:17:00", "2026-09-15T08:21:00", TU, 7))
      .toEqual({ dau: 1, cuoi: 1, tranTrai: false, tranPhai: false });
  });

  it("mốc kết thúc đúng 00:00 KHÔNG chạm sang ngày sau", () => {
    expect(oNgay("2026-09-15T20:00", "2026-09-16T00:00", TU, 7)).toMatchObject({ dau: 1, cuoi: 1 });
    // Việc 0 phút lúc nửa đêm: không được ra ô cuối nằm trước ô đầu.
    expect(oNgay("2026-09-16T00:00", "2026-09-16T00:00", TU, 7)).toMatchObject({ dau: 2, cuoi: 2 });
  });

  it("vắt qua mép cửa sổ thì kẹp lại và báo tràn", () => {
    expect(oNgay("2026-09-12T08:00", "2026-09-15T10:00", TU, 7))
      .toEqual({ dau: 0, cuoi: 1, tranTrai: true, tranPhai: false });
    expect(oNgay("2026-09-19T08:00", "2026-09-23T10:00", TU, 7))
      .toEqual({ dau: 5, cuoi: 6, tranTrai: false, tranPhai: true });
  });

  it("nằm hẳn ngoài cửa sổ hoặc thiếu mốc ⇒ null", () => {
    expect(oNgay("2026-09-21T08:00", "2026-09-21T09:00", TU, 7)).toBeNull();
    expect(oNgay("2026-09-10T08:00", "2026-09-13T23:59", TU, 7)).toBeNull();
    expect(oNgay(null, "2026-09-15T09:00", TU, 7)).toBeNull();
  });
});

describe("dayThucTe — ngày có chạy thật, gộp liền nhau", () => {
  it("hai phiên cùng ngày gộp một dải; phiên mở kéo tới hôm nay và đánh dấu mở", () => {
    expect(dayThucTe([
      { bat_dau: "2026-09-15T11:37", ket_thuc: "2026-09-15T11:37" },
      { bat_dau: "2026-09-15T11:38", ket_thuc: "2026-09-15T11:40" },
    ], TU, 7, "2026-09-15T12:00")).toEqual([{ dau: 1, cuoi: 1, mo: false }]);

    expect(dayThucTe([
      { bat_dau: "2026-09-14T22:00", ket_thuc: "2026-09-15T02:00" },
      { bat_dau: "2026-09-17T07:00", ket_thuc: null },
    ], TU, 7, "2026-09-18T09:00")).toEqual([
      { dau: 0, cuoi: 1, mo: false },
      { dau: 3, cuoi: 4, mo: true },
    ]);
  });
});

describe("dongHaiThanh — dòng 2 trong thanh", () => {
  it("chờ làm: giờ kế hoạch trong ngày, khác ngày thì ra ngày", () => {
    const w = viec({ du_kien_bat_dau: "2026-09-15T08:17:00", du_kien_ket_thuc: "2026-09-15T08:21:00" });
    expect(dongHaiThanh(w, "du")).toBe("KH 08:17–08:21");
    expect(dongHaiThanh(w, "gon")).toBe("08:17–08:21");
    expect(dongHaiThanh(w, "mini")).toBe("08:17");
    const nhieuNgay = viec({ du_kien_bat_dau: "2026-09-15T20:00", du_kien_ket_thuc: "2026-09-17T10:00" });
    expect(dongHaiThanh(nhieuNgay, "du")).toBe("KH 15/9 → 17/9");
    expect(dongHaiThanh(nhieuNgay, "mini")).toBe("→ 17/9");
    expect(dongHaiThanh(viec({ du_kien_bat_dau: "2026-09-15T08:21", du_kien_ket_thuc: "2026-09-15T08:21" }), "du"))
      .toBe("KH 08:21");
  });

  it("hoàn thành: giờ xong THẬT, lệch ngày kế hoạch thì kèm ngày", () => {
    const thuc_te = [
      { bat_dau: "2026-09-15T11:37", ket_thuc: "2026-09-15T11:37" },
      { bat_dau: "2026-09-15T11:38", ket_thuc: "2026-09-15T11:40" },
    ];
    const kh = { du_kien_bat_dau: "2026-09-15T08:21", du_kien_ket_thuc: "2026-09-15T08:21" };
    expect(dongHaiThanh(viec({ trang_thai: "completed", thuc_te, ...kh }), "du")).toBe("Xong 11:40");
    expect(dongHaiThanh(viec({ trang_thai: "completed", thuc_te, ...kh }), "mini")).toBe("11:40");
    const tre = viec({ trang_thai: "completed", ...kh, thuc_te: [{ bat_dau: "2026-09-16T07:00", ket_thuc: "2026-09-16T09:05" }] });
    expect(dongHaiThanh(tre, "du")).toBe("Xong 16/9 09:05");
    expect(dongHaiThanh(tre, "mini")).toBe("16/9");
  });

  it("đang chạy: giờ bắt đầu của phiên đang mở", () => {
    const w = viec({
      trang_thai: "running", du_kien_bat_dau: "2026-09-15T07:00",
      thuc_te: [{ bat_dau: "2026-09-15T07:05", ket_thuc: null }],
    });
    expect(dongHaiThanh(w, "du")).toBe("Chạy từ 07:05");
    expect(dongHaiThanh(w, "gon")).toBe("Từ 07:05");
    expect(dongHaiThanh(w, "mini")).toBe("07:05");
  });

  it("ngưỡng cỡ chữ theo bề rộng thanh", () => {
    expect([coThanh(160), coThanh(120), coThanh(119), coThanh(88), coThanh(83), coThanh(56)])
      .toEqual(["du", "du", "gon", "gon", "mini", "mini"]);
  });
});
