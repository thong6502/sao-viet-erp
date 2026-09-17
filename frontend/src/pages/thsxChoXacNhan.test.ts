// Việc chờ tổ bấm gắn vào công đoạn (§11.5): một nguồn `cho-xac-nhan` → chấm đỏ + tab mở sẵn.
import { describe, expect, it } from "vitest";
import type { SxChoXacNhan } from "../api/client";
import { choNgoaiBan, choTheoViec, coCho, nhanCho, tabCho, tongCho } from "./thsxChoXacNhan";

const d = {
  team_id: 3,
  ban_giao: [
    { id: 1, dich_cong_viec_id: 24, tren_ban: true },
    { id: 2, dich_cong_viec_id: 24, tren_ban: true },
  ],
  ho_tro: [
    { id: 7, cong_viec_id: 24, tren_ban: true },
    { id: 8, cong_viec_id: 99, tren_ban: false },
  ],
  kcs_loi: [
    { loi_id: 4, cong_viec_id: 30, tren_ban: true },
    { loi_id: 5, cong_viec_id: null, tren_ban: false },
  ],
} as unknown as SxChoXacNhan;

describe("thsxChoXacNhan", () => {
  it("gom theo công đoạn, đếm riêng từng loại; lỗi KCS không rõ công đoạn thì không gắn dòng nào", () => {
    const m = choTheoViec(d);
    expect(m.get(24)).toEqual({ nhan: 2, kcs: 0, hoTro: 1 });
    expect(m.get(30)).toEqual({ nhan: 0, kcs: 1, hoTro: 0 });
    expect(m.get(99)).toEqual({ nhan: 0, kcs: 0, hoTro: 1 });
    expect(m.size).toBe(3);
    expect(tongCho(d)).toBe(6);
    expect(choTheoViec(null).size).toBe(0);
    expect(tongCho(null)).toBe(0);
  });

  it("tab mở sẵn đi theo chỗ bấm: Nhận trước, rồi KCS, rồi Bàn giao (hỗ trợ chéo)", () => {
    expect(tabCho({ nhan: 1, kcs: 1, hoTro: 1 })).toBe("nhan");
    expect(tabCho({ nhan: 0, kcs: 2, hoTro: 1 })).toBe("kcs");
    expect(tabCho({ nhan: 0, kcs: 0, hoTro: 1 })).toBe("ban_giao");
    expect(tabCho(undefined)).toBe("van_hanh");
    expect(tabCho({ nhan: 0, kcs: 0, hoTro: 0 })).toBe("van_hanh");
  });

  it("chỉ việc không có dòng trên bàn mới vào danh sách riêng", () => {
    const n = choNgoaiBan(d)!;
    expect(n.ban_giao).toHaveLength(0);
    expect(n.ho_tro.map((h) => h.id)).toEqual([8]);
    expect(n.kcs_loi.map((l) => l.loi_id)).toEqual([5]);
    expect(choNgoaiBan(null)).toBeNull();
  });

  it("câu mô tả chấm nói rõ đang chờ gì", () => {
    expect(nhanCho({ nhan: 2, kcs: 0, hoTro: 1 })).toBe("2 bàn giao chờ nhận · 1 hỗ trợ chéo chờ xác nhận");
    expect(coCho({ nhan: 0, kcs: 0, hoTro: 0 })).toBe(false);
    expect(coCho(undefined)).toBe(false);
  });
});
