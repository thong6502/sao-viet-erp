import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { SxKcsCongViec } from "../api/client";
import { ThsxKetQuaKcs } from "./ThsxKetQuaKcs";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));
const kcsCongViec = vi.fn();
vi.mock("../api/client", async (goc) => ({
  ...(await goc<typeof import("../api/client")>()),
  api: { sanXuat: { kcsCongViec: (...a: unknown[]) => kcsCongViec(...a) } },
}));

function loi(id: number, daXem: boolean) {
  return {
    id, mo_ta: `Lỗi ${id}`, so_luong: 2, don_vi: "con", to_chiu_id: 3, anh: [],
    da_xem_luc: daXem ? "2026-09-18T09:00:00" : null, nguoi_xem: daXem ? "Tổ Trưởng" : null,
  };
}

function kq(congViecId: number): SxKcsCongViec {
  return {
    cong_viec_id: congViecId, la_kcs_cuoi: false, checklist: [],
    lan_kiem: [{
      id: 5, nguoi_kiem: "Nguyễn Thị Hồng Loan", luc: "2026-09-17T10:33:00", so_dat: 40, so_loi: 4,
      don_vi: "con", ket_luan: "dat_mot_phan", checklist: [], ghi_chu: null, version: 1,
      loi: [loi(9, false), loi(10, false), loi(11, true)],
    }],
  } as unknown as SxKcsCongViec;
}

describe("ThsxKetQuaKcs · mở tab là tổ đã xem (18/09/2026)", () => {
  beforeEach(() => kcsCongViec.mockReset());

  it("gửi đã xem MỘT lượt cho lỗi chưa xem nằm trong danh sách chờ của người mở, không có nút", async () => {
    kcsCongViec.mockResolvedValue(kq(1));
    const onXem = vi.fn();
    // Lỗi 10 không thuộc danh sách chờ của người này (không có quyền Xác nhận tổ chịu) ⇒ không ghi.
    render(<ThsxKetQuaKcs congViecId={1} loiChoXem={new Set([9, 11])} onXem={onXem} />);

    await waitFor(() => expect(onXem).toHaveBeenCalledTimes(1));
    expect(onXem).toHaveBeenCalledWith([9]);
    expect(screen.queryByRole("button", { name: /Đã xem/ })).toBeNull();
    expect(screen.getAllByText("Tổ chưa xem")).toHaveLength(2);
  });

  it("thợ không nằm trong danh sách chờ mở tab: không ghi gì", async () => {
    kcsCongViec.mockResolvedValue(kq(1));
    const onXem = vi.fn();
    render(<ThsxKetQuaKcs congViecId={1} loiChoXem={new Set()} onXem={onXem} />);

    await screen.findByText("Lỗi 9");
    expect(onXem).not.toHaveBeenCalled();
  });

  it("dữ liệu nạp lại khi danh sách chờ chưa kịp cập nhật: không gửi lặp", async () => {
    kcsCongViec.mockResolvedValue(kq(1));
    const onXem = vi.fn();
    const cho = new Set([9]);
    const { rerender } = render(<ThsxKetQuaKcs congViecId={1} kcsTick={0} loiChoXem={cho} onXem={onXem} />);
    await waitFor(() => expect(onXem).toHaveBeenCalledTimes(1));

    rerender(<ThsxKetQuaKcs congViecId={1} kcsTick={1} loiChoXem={new Set([9])} onXem={onXem} />);
    await waitFor(() => expect(kcsCongViec).toHaveBeenCalledTimes(2));
    expect(onXem).toHaveBeenCalledTimes(1);
  });
});
