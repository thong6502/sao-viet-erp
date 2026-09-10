import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { SxWorkItem } from "../api/client";
import { ThsxDanhSach } from "./ThsxDanhSach";

function mockViec(p: Partial<SxWorkItem>): SxWorkItem {
  return {
    id: 1,
    nguon_loai: "lsx",
    nguon_ma: "LSX26-0003",
    nguon_ten: "Hộp bánh mang đi 4 ngăn",
    ten_cong_doan: "Ghi kẽm CTP",
    loai_buoc: "may",
    may: "CTP Screen 8600",
    trang_thai: "released",
    so_luong_vao: 4,
    so_luong_ra: 4,
    don_vi_vao: "kem",
    don_vi_ra: "kem",
    ngoai_dong: true,
    chay_phut: 13,
    dinh_muc_vat_tu: [{ vat_tu_id: 1, ma: "KM01", ten: "Bản kẽm CTP 1030x790", don_vi: "cai", so_luong: 4 }],
    la_kcs: false,
    quy_cach: { giay: "Couche", dinh_luong: 300, kho_in: "640 x 450", so_mau: 4, so_kem: 4 },
    ...p,
  } as SxWorkItem;
}

describe("ThsxDanhSach — Workstation Studio Modern Table View", () => {
  it("hiển thị đúng thông tin mã nguồn, công đoạn, máy, quy cách và vật tư", () => {
    const item = mockViec({ id: 201, ten_cong_doan: "Ghi kẽm CTP" });
    const onPick = vi.fn();

    render(
      <ThsxDanhSach
        timed={[item]}
        outWin={[]}
        untimed={[]}
        selectedId={null}
        onPick={onPick}
      />
    );

    expect(screen.getByText("0003")).toBeInTheDocument();
    expect(screen.getByText("Ghi kẽm CTP")).toBeInTheDocument();
    expect(screen.getByText("CTP Screen 8600")).toBeInTheDocument();
    expect(screen.getByText("Bản kẽm CTP 1030x790")).toBeInTheDocument();
    expect(screen.getByText(/Couche 300gsm/i)).toBeInTheDocument();
  });

  it("kích hoạt 1-click Bắt đầu khi bấm nút trực tiếp trong bảng", () => {
    const item = mockViec({ id: 202, trang_thai: "released" });
    const onPick = vi.fn();
    const onBatDau = vi.fn();

    render(
      <ThsxDanhSach
        timed={[item]}
        outWin={[]}
        untimed={[]}
        selectedId={null}
        onPick={onPick}
        onBatDau={onBatDau}
      />
    );

    const btnStart = screen.getByText("Bắt đầu");
    expect(btnStart).toBeInTheDocument();
    fireEvent.click(btnStart);

    expect(onBatDau).toHaveBeenCalledWith(item);
  });

  it("cho phép mở rộng accordion xem dặn dò kỹ thuật khi bấm nút chevron toggle", () => {
    const item = mockViec({ id: 203, ghi_chu: "Kiểm tra kỹ bù hao 5%" });
    const onPick = vi.fn();

    render(
      <ThsxDanhSach
        timed={[item]}
        outWin={[]}
        untimed={[]}
        selectedId={null}
        onPick={onPick}
      />
    );

    const toggleBtn = screen.getByLabelText("Toggle chi tiết dòng");
    fireEvent.click(toggleBtn);

    expect(screen.getByText("Kiểm tra kỹ bù hao 5%")).toBeInTheDocument();
  });
});
