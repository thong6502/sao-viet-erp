// Tổ trưởng ăn thưởng / ăn chia theo sản lượng tổ — chỗ khai báo (chủ 19/09/2026).
//
// Khoá bốn điều người khai dựa vào: (1) thấy tổ trưởng là ai + chế độ ĐANG ÁP DỤNG ở góc thẻ, (2) dòng
// ví dụ theo đúng lời chủ (tổ làm 100.000 đ) đổi theo chế độ + tỷ lệ vừa gõ, (3) tỷ lệ sai bị nói ngay
// và khoá nút lưu, (4) lưu gửi đúng payload rồi thẻ cập nhật theo kết quả máy chủ.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ToTruongList } from "../../../../../api/client";
import { ToTruongEditor } from "./ToTruongEditor";

const toTruong = vi.fn();
const khaiToTruong = vi.fn();
const xoaToTruong = vi.fn();

vi.mock("../../../../../api/client", () => ({
  ApiError: class ApiError extends Error {
    status = 400;
  },
  api: {
    luong: {
      toTruong: (...a: unknown[]) => toTruong(...a),
      khaiToTruong: (...a: unknown[]) => khaiToTruong(...a),
      xoaToTruong: (...a: unknown[]) => xoaToTruong(...a),
    },
  },
}));

const MOC_CU = {
  id: 1,
  department_id: 9,
  ap_dung_tu: "2020-01-01",
  che_do: "thuong" as const,
  ty_le: 5,
  ghi_chu: null,
  updated_at: null,
};

function ds(items: ToTruongList["items"], hienHanh: ToTruongList["hien_hanh"]): ToTruongList {
  return { department_id: 9, hien_hanh: hienHanh, items };
}

function ve(props: Partial<Parameters<typeof ToTruongEditor>[0]> = {}) {
  return render(
    <ToTruongEditor
      token="t"
      departmentId={9}
      deptName="Tổ Bồi"
      headName="Nguyễn Văn A"
      headTitle="Tổ trưởng"
      soNguoi={8}
      {...props}
    />,
  );
}

describe("ToTruongEditor", () => {
  beforeEach(() => {
    toTruong.mockReset();
    khaiToTruong.mockReset();
    xoaToTruong.mockReset();
  });

  it("⭐ nêu tên tổ trưởng; chế độ đang áp dụng đứng ở góc thẻ; nói rõ chưa vào lương", async () => {
    toTruong.mockResolvedValueOnce(ds([MOC_CU], MOC_CU));
    const { container } = ve();
    expect(await screen.findByText("đang áp dụng từ 01/01/2020")).toBeInTheDocument();
    expect(container.querySelector(".cl-chitieu__now-val")).toHaveTextContent("Ăn thưởng 5%");
    expect(container.querySelector(".cl-totruong__nguoi")).toHaveTextContent("Tổ trưởng: Nguyễn Văn A");
    expect(screen.getByText(/Chưa áp vào tính lương/)).toBeInTheDocument();
  });

  it("tổ chưa có mốc + chưa có người đứng đầu: nói rõ cả hai, không vẽ bảng", async () => {
    toTruong.mockResolvedValueOnce(ds([], null));
    const { container } = ve({ headName: null });
    expect(await screen.findByText("Chưa khai — không áp dụng")).toBeInTheDocument();
    expect(container.querySelector(".cl-totruong__nguoi")).toHaveTextContent(
      "Tổ chưa có người đứng đầu",
    );
    expect(container.querySelector("table")).toBeNull();
  });

  it("⭐ dòng ví dụ theo lời chủ: ăn thưởng 5% = +5.000 đ; ăn chia 5% = 5.000 đ + 95.000 đ chia đều", async () => {
    toTruong.mockResolvedValueOnce(ds([], null));
    const user = userEvent.setup();
    const { container } = ve();
    await screen.findByText("Chưa khai — không áp dụng");
    const vd = () => container.querySelector(".cl-totruong__vd");

    await user.type(screen.getByPlaceholderText("5"), "5");
    expect(vd()).toHaveTextContent(
      "Ví dụ tổ làm ra 100.000 đ → công ty thưởng thêm tổ trưởng 5.000 đ; thợ vẫn ăn sản lượng của mình.",
    );

    await user.click(screen.getByRole("radio", { name: "Ăn chia" }));
    expect(vd()).toHaveTextContent(
      "tổ trưởng lấy 5.000 đ, 95.000 đ còn lại chia đều cho cả tổ (8 người ≈ 11.875 đ/người).",
    );

    await user.click(screen.getByRole("radio", { name: "Không áp dụng" }));
    expect(vd()).toHaveTextContent("không thưởng hay chia gì thêm");
    expect(screen.getByPlaceholderText("—")).toBeDisabled();
  });

  it("ăn chia 100% bị nói ngay dưới ô và khoá nút lưu", async () => {
    toTruong.mockResolvedValueOnce(ds([], null));
    const user = userEvent.setup();
    ve();
    await screen.findByText("Chưa khai — không áp dụng");
    await user.click(screen.getByRole("radio", { name: "Ăn chia" }));
    await user.type(screen.getByPlaceholderText("5"), "100");
    expect(screen.getByText(/Ăn chia phải nhỏ hơn 100%/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thêm mốc" })).toBeDisabled();
  });

  it("⭐ gõ trùng ngày mốc cũ ⇒ 'Sửa mốc'; lưu gửi đúng payload rồi cập nhật góc thẻ", async () => {
    toTruong.mockResolvedValueOnce(ds([MOC_CU], MOC_CU));
    const moi = { ...MOC_CU, che_do: "chia" as const, ty_le: 7.5, ghi_chu: "họp tổ" };
    khaiToTruong.mockResolvedValueOnce(ds([moi], moi));
    const user = userEvent.setup();
    const { container } = ve();
    await screen.findByText("đang áp dụng từ 01/01/2020");

    const ngay = container.querySelector('input[type="date"]') as HTMLInputElement;
    await user.clear(ngay);
    await user.type(ngay, "2020-01-01");
    expect(screen.getByRole("button", { name: "Sửa mốc" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Ăn chia" }));
    await user.type(screen.getByPlaceholderText("5"), "7.5");
    expect(screen.getByText(/đã có mốc Ăn thưởng 5%/)).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Không bắt buộc"), "  họp tổ  ");
    await user.click(screen.getByRole("button", { name: "Sửa mốc" }));

    await waitFor(() =>
      expect(khaiToTruong).toHaveBeenCalledWith("t", 9, {
        ap_dung_tu: "2020-01-01",
        che_do: "chia",
        ty_le: 7.5,
        ghi_chu: "họp tổ",
      }),
    );
    await waitFor(() =>
      expect(container.querySelector(".cl-chitieu__now-val")).toHaveTextContent("Ăn chia 7,5%"),
    );
  });

  it("'Không áp dụng' gửi tỷ lệ 0 dù ô % đã gõ số trước đó", async () => {
    toTruong.mockResolvedValueOnce(ds([], null));
    khaiToTruong.mockResolvedValueOnce(ds([], null));
    const user = userEvent.setup();
    const { container } = ve();
    await screen.findByText("Chưa khai — không áp dụng");
    const ngay = container.querySelector('input[type="date"]') as HTMLInputElement;
    await user.clear(ngay);
    await user.type(ngay, "2021-01-01");
    await user.type(screen.getByPlaceholderText("5"), "5");
    await user.click(screen.getByRole("radio", { name: "Không áp dụng" }));
    await user.click(screen.getByRole("button", { name: "Thêm mốc" }));
    await waitFor(() =>
      expect(khaiToTruong).toHaveBeenCalledWith("t", 9, {
        ap_dung_tu: "2021-01-01",
        che_do: "khong",
        ty_le: 0,
        ghi_chu: null,
      }),
    );
  });

  it("chế độ chỉ xem: không có hàng nhập, không có nút xoá", async () => {
    toTruong.mockResolvedValueOnce(ds([MOC_CU], MOC_CU));
    const { container } = ve({ readOnly: true });
    await screen.findByText("đang áp dụng từ 01/01/2020");
    expect(container.querySelector(".cl-totruong__form")).toBeNull();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(container.querySelector("td.act")).toBeNull();
  });
});
