// Tình trạng người ở ô "Giao người" / "Thợ hỗ trợ": mỗi người LUÔN có một dòng tóm tắt.
import { describe, expect, it } from "vitest";
import type { SxTinhTrangNguoi } from "../api/client";
import { tinhTrangChon } from "./thsxTinhTrangNguoi";

const RANH: SxTinhTrangNguoi = { ly_do_nghi: null, nghi_phep: [], dang_chay: null, viec_cho: [] };
const VIEC = { cong_viec_id: 28, ma: "LSX26-0004", ten_cong_doan: "Bế", to_ten: "Tổ bế" };
const DAN_TAM_DUNG = { cong_viec_id: 29, ma: "LSX26-0004", ten_cong_doan: "Dán", to_ten: "Tổ dán", trang_thai: "paused" as const };
const BE_CHUA_CHAY = { cong_viec_id: 24, ma: "LSX26-0001", ten_cong_doan: "Bế", to_ten: "Tổ bế", trang_thai: "released" as const };
const HOM_NAY = { ngay: "2026-09-17", homNay: "2026-09-17" };

describe("tinhTrangChon", () => {
  it("người rảnh vẫn có dòng 'Rảnh' màu xanh", () => {
    const t = tinhTrangChon(RANH, HOM_NAY);
    expect(t).toMatchObject({ tomTat: "Rảnh", muc: "ranh", chan: null, canhBao: null, ghiChu: null, hang: 0 });
  });

  it("có tên ở việc chưa xong: KHÔNG ghi Rảnh, nói rõ việc nào và trạng thái", () => {
    expect(tinhTrangChon({ ...RANH, viec_cho: [DAN_TAM_DUNG] }, HOM_NAY)).toMatchObject({
      tomTat: "Có tên ở LSX26-0004 · Dán (Tổ dán) — đang tạm dừng", muc: "cho", ghiChu: null, hang: 1,
    });
    expect(tinhTrangChon({ ...RANH, viec_cho: [BE_CHUA_CHAY] }, HOM_NAY).tomTat)
      .toBe("Có tên ở LSX26-0001 · Bế (Tổ bế) — chưa bắt đầu");
    expect(tinhTrangChon({ ...RANH, viec_cho: [DAN_TAM_DUNG, BE_CHUA_CHAY] }, HOM_NAY).tomTat)
      .toBe("Có tên ở LSX26-0004 · Dán (Tổ dán) — đang tạm dừng +1 việc");
  });

  it("đang chạy việc khác mà còn có tên ở việc chưa xong: tóm tắt là việc đang chạy, việc kia xuống ghi chú", () => {
    const t = tinhTrangChon({ ...RANH, dang_chay: VIEC, viec_cho: [BE_CHUA_CHAY] }, HOM_NAY);
    expect(t).toMatchObject({ muc: "canh", ghiChu: "Có tên ở LSX26-0001 · Bế (Tổ bế) — chưa bắt đầu" });
  });

  it("đang chạy việc khác: cảnh báo, chỉ chặn khi việc đích cũng đang chạy", () => {
    const tt = { ...RANH, dang_chay: VIEC };
    expect(tinhTrangChon(tt, HOM_NAY)).toMatchObject({
      tomTat: "Đang chạy LSX26-0004 · Bế (Tổ bế)", muc: "canh", chan: null, hang: 2,
    });
    const chan = tinhTrangChon(tt, { ...HOM_NAY, viecDangChay: true });
    expect(chan.muc).toBe("chan");
    expect(chan.tomTat).toBe(chan.chan);
    expect(chan.hang).toBe(3);
  });

  it("nghỉ phép theo đúng ngày xét: hôm nay bị chặn, ngày khác thì rảnh", () => {
    const tt = { ...RANH, nghi_phep: [{ tu: "2026-09-17", den: "2026-09-17" }] };
    expect(tinhTrangChon(tt, HOM_NAY)).toMatchObject({ tomTat: "Nghỉ phép hôm nay", muc: "chan" });
    expect(tinhTrangChon(tt, { ngay: "2026-09-18", homNay: "2026-09-17" })).toMatchObject({ tomTat: "Rảnh", muc: "ranh" });
  });

  it("nghỉ dài hạn thắng mọi tình trạng khác", () => {
    const t = tinhTrangChon({ ...RANH, ly_do_nghi: "Nghỉ dài hạn", dang_chay: VIEC }, HOM_NAY);
    expect(t).toMatchObject({ tomTat: "Nghỉ dài hạn", muc: "chan", canhBao: null });
  });
});
