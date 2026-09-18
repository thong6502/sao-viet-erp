// Bàn tổ có HAI hình dữ liệu; chọn nhầm hình là băng KPI đếm sai.
import { describe, expect, it } from "vitest";
import { chonHinhBan } from "./thsxShared";
import type { SxWorkItemsOut } from "../api/client";

const viec = { id: 3, trang_thai: "released" } as never;

describe("chonHinhBan", () => {
  it('nhom="phang": giữ mảng bước, KHÔNG nhận mảng lệnh rỗng máy chủ vẫn trả kèm', () => {
    // BE khai `lenh: list[...] = []` nên khoá này LUÔN có mặt, kể cả ở chế độ phẳng. Đọc theo
    // "có mảng lệnh hay không" là đếm 0 việc trong khi Gantt đang vẽ đủ việc.
    const r: SxWorkItemsOut = { team_id: 12, nhom: "phang", trang: null, lenh: [], cong_viec: [viec] };
    const h = chonHinhBan(r);
    expect(h.lenh).toBeNull();
    expect(h.cong_viec).toHaveLength(1);
    expect(h.tongLenh).toBe(0);
  });

  it('nhom="lenh": giữ trang lệnh, bỏ mảng bước', () => {
    const r: SxWorkItemsOut = {
      team_id: 12, nhom: "lenh",
      trang: { trang: 2, co_trang: 20, tong: 37 },
      lenh: [{ so_viec: 2, cong_viec: [viec] } as never],
      cong_viec: [],
    };
    const h = chonHinhBan(r);
    expect(h.cong_viec).toBeNull();
    expect(h.lenh).toHaveLength(1);
    expect(h.tongLenh).toBe(37);
  });

  it("lệnh rỗng thật vẫn là chế độ lệnh, không rơi về hình phẳng", () => {
    const h = chonHinhBan({ team_id: 12, nhom: "lenh", trang: { trang: 1, co_trang: 20, tong: 0 }, lenh: [], cong_viec: [] });
    expect(h.lenh).toEqual([]);
    expect(h.cong_viec).toBeNull();
  });
});
