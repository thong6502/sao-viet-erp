import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { SxWorkItem } from "../api/client";
import { ThsxCards } from "./ThsxCards";

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
    dinh_muc_vat_tu: [],
    la_kcs: false,
    ...p,
  } as SxWorkItem;
}

/** Bọc MỘT bước vào một lệnh — bàn tổ từ 11/09/2026 nhận `lenh`, thẻ/bảng việc nằm bên trong. */
function mockLenh(items: SxWorkItem[]) {
  return [{
    nguon_loai: "lsx", nguon_ma: items[0]?.nguon_ma ?? "LSX26-0003",
    nguon_ten: items[0]?.nguon_ten ?? "", lsx_id: 3, bai_ghep_id: null,
    som_nhat: null, muon_nhat: null, so_viec: items.length,
    digest: { released: items.length, running: 0, paused: 0, completed: 0 },
    cong_viec: items,
  }];
}

describe("ThsxCards — Workstation Studio Task Cards Grid", () => {
  it("hiển thị đúng mã LSX, tên công đoạn, máy và khối lượng mục tiêu", () => {
    const item = mockViec({ id: 101, ten_cong_doan: "In Offset 4 màu" });
    const onPick = vi.fn();

    render(
      <ThsxCards
        lenh={mockLenh([item])}
        selectedId={null}
        onPick={onPick}
      />
    );

    expect(screen.getByText("0003")).toBeInTheDocument();
    expect(screen.getByText("In Offset 4 màu")).toBeInTheDocument();
    expect(screen.getByText("CTP Screen 8600")).toBeInTheDocument();
    expect(screen.getByText("4 kem")).toBeInTheDocument();
  });

  it("kích hoạt 1-click Bắt đầu khi bấm nút trên thẻ", () => {
    const item = mockViec({ id: 102, trang_thai: "released" });
    const onPick = vi.fn();
    const onBatDau = vi.fn();

    render(
      <ThsxCards
        lenh={mockLenh([item])}
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

  it("bấm vào thẻ gọi callback `onPick` để mở chi tiết", () => {
    const item = mockViec({ id: 103 });
    const onPick = vi.fn();

    render(
      <ThsxCards
        lenh={mockLenh([item])}
        selectedId={null}
        onPick={onPick}
      />
    );

    const card = screen.getByRole("region", { name: /Thẻ việc Ghi kẽm CTP/i });
    fireEvent.click(card);

    expect(onPick).toHaveBeenCalledWith(item);
  });
});
