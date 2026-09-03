import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChipKhuon, ChipLoaiBuoc } from "./ChipBuoc";

describe("ChipLoaiBuoc", () => {
  it("thuê ngoài CÓ nhà gia công → hiện tên nơi làm", () => {
    render(<ChipLoaiBuoc loai_buoc="thue_ngoai" nha_cung_cap="Cơ sở Minh Phát" />);
    expect(screen.getByText("Ngoài · Cơ sở Minh Phát")).toBeTruthy();
  });

  it("thuê ngoài CHƯA có nhà gia công → vẫn hiện nhãn, đổi sang tone cảnh báo", () => {
    const { container } = render(<ChipLoaiBuoc loai_buoc="thue_ngoai" />);
    expect(screen.getByText("Ngoài · chưa chọn nơi làm")).toBeTruthy();
    expect(container.querySelector(".chip-buoc--canhbao")).toBeTruthy();
  });

  it("máy và tổ vẫn có nhãn riêng", () => {
    render(<ChipLoaiBuoc loai_buoc="may" />);
    expect(screen.getByText("Máy")).toBeTruthy();
  });

  it("không biết loại → không vẽ gì", () => {
    const { container } = render(<ChipLoaiBuoc />);
    expect(container.firstChild).toBeNull();
  });
});

describe("ChipKhuon", () => {
  it("bước cần dụng cụ mà chưa chốt dao → chip đỏ", () => {
    const { container } = render(<ChipKhuon can_khuon />);
    expect(screen.getByText("chưa chốt khuôn")).toBeTruthy();
    expect(container.querySelector(".chip-khuon--thieu")).toBeTruthy();
  });

  it("dao đang dùng → mã + số kệ", () => {
    render(
      <ChipKhuon can_khuon khuon={{ ma: "KB-0123", so_ke: "Kệ A3", tinh_trang: "dang_dung" }} />,
    );
    expect(screen.getByText("KB-0123 · Kệ A3")).toBeTruthy();
  });

  it("dao đang đặt làm → mã + ngày dự kiến, tone vàng", () => {
    const { container } = render(
      <ChipKhuon
        can_khuon
        khuon={{ ma: "KB-0130", tinh_trang: "dang_dat_lam", ngay_ve_du_kien: "2026-09-12" }}
      />,
    );
    expect(screen.getByText("KB-0130 · dự kiến 12/09")).toBeTruthy();
    expect(container.querySelector(".chip-khuon--cho")).toBeTruthy();
  });

  it("tổ đã tích nhận → nói 'đã nhận'", () => {
    render(<ChipKhuon can_khuon khuon={{ ma: "KB-0123", so_ke: "Kệ A3", da_nhan: true }} />);
    expect(screen.getByText("KB-0123 · đã nhận")).toBeTruthy();
  });

  it("bước không cần dụng cụ → không vẽ gì", () => {
    const { container } = render(<ChipKhuon />);
    expect(container.firstChild).toBeNull();
  });
});
