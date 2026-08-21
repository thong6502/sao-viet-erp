/** Hai phép tính SỐ của màn Khách hàng — cả hai từng cho ra con số sai mà trông vẫn hợp lý.
 *
 *  Không ai bắt được loại lỗi này bằng mắt: "18%" và "67,5 Mđ" đọc lên đều bình thường. Chỉ khi
 *  đặt cạnh dữ liệu thật (11 báo giá ĐÃ LÊN ĐƠN mà tỉ lệ chốt 18%) mới lộ.
 */
import { describe, expect, it } from "vitest";

import { gopTienTheoSanPham, tinhTiLeChot } from "./khachHangSo";
import type { OrderHistoryRow, QuoteHistoryRow } from "../api/client";

function bg(status: string, total = 1_000_000): QuoteHistoryRow {
  return {
    id: Math.round(total + status.length), code: "BG", version: 1, status,
    total, valid_until: null, created_at: "2026-08-01T00:00:00Z",
  };
}

function don(lines: [string, number][], summary?: string): OrderHistoryRow {
  return {
    id: 1, order_no: "DH", status: "ordered", order_kind: "moi",
    summary: summary ?? lines.map(([d]) => d).join(", "),
    lines: lines.map(([description, line_total]) => ({ description, line_total })),
    total: lines.reduce((s, [, v]) => s + v, 0),
    created_at: "2026-08-01T00:00:00Z",
  };
}

describe("tỉ lệ chốt", () => {
  it("báo giá ĐÃ LÊN ĐƠN là THẮNG — đây là lỗi đã làm màn hình ghi 18% thay vì 88%", () => {
    // Đúng bộ trạng thái của khách An Phát trong ảnh chụp màn hình 16/08/2026.
    const rows = [
      ...Array.from({ length: 11 }, () => bg("converted_to_order", 16_326_000)),
      ...Array.from({ length: 3 }, () => bg("accepted", 24_750_000)),
      bg("draft", 8_650_000),
      bg("sent", 3_960_000),
      bg("rejected", 19_800_000),
    ];
    const r = tinhTiLeChot(rows);
    expect(r.thang).toBe(14);            // 11 đã lên đơn + 3 đã chốt
    expect(r.daChao).toBe(16);           // 17 trừ 1 bản nháp (khách chưa thấy)
    expect(r.pct).toBe(88);              // bản cũ ra 18%
  });

  it("`approved` KHÔNG phải thắng — GĐ duyệt xong nhưng sale chưa gửi, khách chưa thấy", () => {
    const r = tinhTiLeChot([bg("approved"), bg("accepted")]);
    expect(r.thang).toBe(1);
    // `approved` cũng không nằm trong mẫu số: chưa ra khỏi cửa thì chưa chào ai.
    expect(r.daChao).toBe(1);
    expect(r.pct).toBe(100);
  });

  it("bản nháp và báo giá tự huỷ không kéo tỉ lệ xuống", () => {
    const r = tinhTiLeChot([bg("accepted"), bg("draft"), bg("cancelled"), bg("pending_approval")]);
    expect(r.daChao).toBe(1);
    expect(r.pct).toBe(100);
  });

  it("chưa chào báo giá nào thì trả null, KHÔNG phải 0% (0% đọc ra là chào mãi không ai mua)", () => {
    expect(tinhTiLeChot([]).pct).toBeNull();
    expect(tinhTiLeChot([bg("draft")]).pct).toBeNull();
  });

  it("giá trị đã chốt cộng cả báo giá đã lên đơn", () => {
    const r = tinhTiLeChot([bg("converted_to_order", 30_000_000), bg("accepted", 5_000_000),
                            bg("rejected", 99_000_000)]);
    expect(r.giaTriThang).toBe(35_000_000);
  });
});

describe("gộp tiền theo sản phẩm", () => {
  it("dùng TIỀN THẬT của từng dòng, không chia đều tổng đơn", () => {
    // Chia đều sẽ ra 15tr/15tr và xếp hai thứ ngang nhau — số thật là 28tr/2tr.
    const r = gopTienTheoSanPham([don([["Ruột sách 160 trang", 28_000_000],
                                       ["Thẻ nhân viên", 2_000_000]])]);
    expect(r.map((x) => [x.name, x.total])).toEqual([
      ["Ruột sách 160 trang", 28_000_000],
      ["Thẻ nhân viên", 2_000_000],
    ]);
  });

  it("cộng dồn qua nhiều đơn và đếm số ĐƠN có mặt sản phẩm", () => {
    const r = gopTienTheoSanPham([
      don([["Name card", 1_000_000]]),
      don([["Name card", 2_000_000], ["Tờ rơi", 500_000]]),
    ]);
    expect(r[0]).toEqual({ name: "Name card", qty: 2, total: 3_000_000 });
  });

  it("cắt đúng TOP n, xếp theo tiền", () => {
    const r = gopTienTheoSanPham(
      [don([["A", 1], ["B", 5], ["C", 3], ["D", 4], ["E", 2]])], 3);
    expect(r.map((x) => x.name)).toEqual(["B", "D", "C"]);
  });

  it("đơn cũ chưa có `lines` thì vẫn đếm được số đơn, nhưng KHÔNG bịa tiền", () => {
    const cu: OrderHistoryRow = { ...don([], "Catalogue A4, Tờ rơi A5"), lines: [], total: 9_000_000 };
    const r = gopTienTheoSanPham([cu]);
    expect(r.map((x) => [x.name, x.qty, x.total])).toEqual([
      ["Catalogue A4", 1, 0],
      ["Tờ rơi A5", 1, 0],
    ]);
  });
});
