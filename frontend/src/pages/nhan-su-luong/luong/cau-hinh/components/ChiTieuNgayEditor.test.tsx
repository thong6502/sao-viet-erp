// Chỉ tiêu ngày của tổ lương khoán / sản lượng — chỗ khai báo (chủ 16/09/2026).
//
// Khoá ba điều người khai dựa vào: (1) thấy ngay số ĐANG ÁP DỤNG ở góc thẻ, (2) gõ trùng ngày của
// mốc cũ thì nút đổi thành "Sửa mốc" (ghi đè, không đẻ mốc mới), (3) lưu gửi đúng ngày + số tiền +
// ghi chú đã cắt khoảng trắng, rồi thẻ cập nhật theo kết quả máy chủ trả về.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChiTieuNgayList } from "../../../../../api/client";
import { ChiTieuNgayEditor } from "./ChiTieuNgayEditor";

const chiTieuNgay = vi.fn();
const khaiChiTieuNgay = vi.fn();
const xoaChiTieuNgay = vi.fn();

vi.mock("../../../../../api/client", () => ({
  ApiError: class ApiError extends Error {
    status = 400;
  },
  api: {
    luong: {
      chiTieuNgay: (...a: unknown[]) => chiTieuNgay(...a),
      khaiChiTieuNgay: (...a: unknown[]) => khaiChiTieuNgay(...a),
      xoaChiTieuNgay: (...a: unknown[]) => xoaChiTieuNgay(...a),
    },
  },
}));

const MOC_CU = {
  id: 1,
  department_id: 9,
  ap_dung_tu: "2020-01-01",
  so_tien: 350_000,
  ghi_chu: null,
  updated_at: null,
};

function ds(items: ChiTieuNgayList["items"], hienHanh: ChiTieuNgayList["hien_hanh"]): ChiTieuNgayList {
  return { department_id: 9, hien_hanh: hienHanh, items };
}

describe("ChiTieuNgayEditor", () => {
  beforeEach(() => {
    chiTieuNgay.mockReset();
    khaiChiTieuNgay.mockReset();
    xoaChiTieuNgay.mockReset();
  });

  it("⭐ số đang áp dụng đứng ở góc thẻ, mốc có nhãn 'đang áp dụng'; nói rõ chưa vào lương", async () => {
    chiTieuNgay.mockResolvedValueOnce(ds([MOC_CU], MOC_CU));
    const { container } = render(<ChiTieuNgayEditor token="t" departmentId={9} deptName="Tổ Bồi" />);
    expect(await screen.findByText("đang áp dụng từ 01/01/2020")).toBeInTheDocument();
    expect(container.querySelector(".cl-chitieu__now-val")).toHaveTextContent("350.000đ/công");
    expect(screen.getByText("đang áp dụng")).toBeInTheDocument();
    expect(screen.getByText(/Chưa áp vào tính lương/)).toBeInTheDocument();
  });

  it("tổ chưa có mốc nào: góc thẻ nói chưa có, không vẽ bảng", async () => {
    chiTieuNgay.mockResolvedValueOnce(ds([], null));
    const { container } = render(<ChiTieuNgayEditor token="t" departmentId={9} deptName="Tổ Bồi" />);
    expect(await screen.findByText("Chưa có chỉ tiêu đang áp dụng")).toBeInTheDocument();
    expect(container.querySelector("table")).toBeNull();
  });

  it("⭐ gõ trùng ngày mốc cũ ⇒ nút thành 'Sửa mốc'; lưu gửi đúng payload rồi cập nhật thẻ", async () => {
    chiTieuNgay.mockResolvedValueOnce(ds([MOC_CU], MOC_CU));
    const moi = { ...MOC_CU, so_tien: 360_000, ghi_chu: "gõ nhầm" };
    khaiChiTieuNgay.mockResolvedValueOnce(ds([moi], moi));
    const user = userEvent.setup();
    const { container } = render(<ChiTieuNgayEditor token="t" departmentId={9} deptName="Tổ Bồi" />);
    await screen.findByText("đang áp dụng từ 01/01/2020");

    const ngay = container.querySelector('input[type="date"]') as HTMLInputElement;
    await user.clear(ngay);
    await user.type(ngay, "2020-01-01");
    expect(screen.getByRole("button", { name: "Sửa mốc" })).toBeInTheDocument();
    // Chưa gõ số thì chưa nhắc ghi đè (bảng mốc ngay dưới đã hiện mốc đó rồi).
    expect(screen.queryByText(/đã có mốc 350.000 đ\/công/)).toBeNull();

    await user.type(screen.getByPlaceholderText("350000"), "360000");
    expect(screen.getByText(/đã có mốc 350.000 đ\/công/)).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Không bắt buộc"), "  gõ nhầm  ");
    await user.click(screen.getByRole("button", { name: "Sửa mốc" }));

    await waitFor(() =>
      expect(khaiChiTieuNgay).toHaveBeenCalledWith("t", 9, {
        ap_dung_tu: "2020-01-01",
        so_tien: 360_000,
        ghi_chu: "gõ nhầm",
      }),
    );
    await waitFor(() =>
      expect(container.querySelector(".cl-chitieu__now-val")).toHaveTextContent("360.000đ/công"),
    );
    expect(screen.getByText("gõ nhầm")).toBeInTheDocument();
  });

  it("sửa số của mốc mà bỏ trống ô Ghi chú ⇒ giữ ghi chú cũ, không xoá mất", async () => {
    const coGhiChu = { ...MOC_CU, ghi_chu: "Theo biên bản họp tổ" };
    chiTieuNgay.mockResolvedValueOnce(ds([coGhiChu], coGhiChu));
    khaiChiTieuNgay.mockResolvedValueOnce(ds([coGhiChu], coGhiChu));
    const user = userEvent.setup();
    const { container } = render(<ChiTieuNgayEditor token="t" departmentId={9} deptName="Tổ Bồi" />);
    await screen.findByText("đang áp dụng từ 01/01/2020");

    const ngay = container.querySelector('input[type="date"]') as HTMLInputElement;
    await user.clear(ngay);
    await user.type(ngay, "2020-01-01");
    await user.type(screen.getByPlaceholderText("350000"), "360000");
    await user.click(screen.getByRole("button", { name: "Sửa mốc" }));

    await waitFor(() =>
      expect(khaiChiTieuNgay).toHaveBeenCalledWith("t", 9, {
        ap_dung_tu: "2020-01-01",
        so_tien: 360_000,
        ghi_chu: "Theo biên bản họp tổ",
      }),
    );
  });

  it("chế độ chỉ xem: không có hàng nhập, không có nút xoá", async () => {
    chiTieuNgay.mockResolvedValueOnce(ds([MOC_CU], MOC_CU));
    const { container } = render(
      <ChiTieuNgayEditor token="t" departmentId={9} deptName="Tổ Bồi" readOnly />,
    );
    await screen.findByText("đang áp dụng từ 01/01/2020");
    expect(container.querySelector(".cl-chitieu__form")).toBeNull();
    expect(container.querySelector("td.act")).toBeNull();
  });
});
