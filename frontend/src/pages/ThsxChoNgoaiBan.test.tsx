import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { SxChoXacNhan } from "../api/client";
import { ThsxChoNgoaiBan } from "./ThsxChoNgoaiBan";

describe("ThsxChoNgoaiBan · lỗi KCS ngoài bàn", () => {
  it("không có nút Đã xem — chỉ Mở để xem, mở vào tab KCS là tổ đã xem (18/09/2026)", () => {
    const onMoKcs = vi.fn();
    const data = {
      team_id: 16, ban_giao: [], ho_tro: [],
      kcs_loi: [{
        loi_id: 6, kcs_batch_id: 9, cong_viec_id: 44, to_id: 16, ten_cong_doan: "Bế", lsx_ma: "LSX26-0004",
        mo_ta: "Xước bề mặt 2 con ở mép bế", so_luong: 2, don_vi: "con", nguoi_kiem: "Nguyễn Thị Hồng Loan",
        luc: "2026-09-17T10:33:00", so_anh: 1, version: 1, tren_ban: false,
      }],
    } as unknown as SxChoXacNhan;
    render(<ThsxChoNgoaiBan data={data} busy={false} onMoBanGiao={vi.fn()} onXacNhanHoTro={vi.fn()}
      onHuyHoTro={vi.fn()} onMoKcs={onMoKcs} />);

    expect(screen.queryByRole("button", { name: /Đã xem/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Mở để xem/ }));
    expect(onMoKcs).toHaveBeenCalledWith(44);
  });
});
