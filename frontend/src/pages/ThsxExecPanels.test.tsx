import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SxWorkItemChiTiet } from "../api/client";
import { BatchForm, type ThsxExec } from "./ThsxExecPanels";

const cv = {
  id: 1, department_id: 7, ten_cong_doan: "Cắt thành phẩm", loai_buoc: "to",
  don_vi_ra: "tờ", don_vi_vao: "tờ",
} as SxWorkItemChiTiet["cong_viec"];

function mo(khoan: SxWorkItemChiTiet["khoan"]) {
  render(<BatchForm
    cv={cv}
    khoan={khoan ?? null}
    busy={false}
    batDauMacDinh="2026-09-20T08:00"
    tranGhi={null}
    onXong={vi.fn()}
    exec={{ taoBatch: vi.fn() } as unknown as ThsxExec}
  />);
}

describe("Ghi mẻ lấy Khoán cố định từ Công đoạn", () => {
  it("không còn radio/tìm/đổi Công việc khoán", () => {
    mo({
      id: 9, ten: "Cắt thành phẩm", don_gia: 25, don_vi: "to", don_vi_ten: "tờ",
      phat_sinh: [{ id: 3, ten: "Thay kẽm", don_gia: 100000, don_vi: "kem", don_vi_ten: "bản kẽm" }],
    });
    expect(screen.getByText("Cắt thành phẩm")).toBeInTheDocument();
    expect(screen.getByText("25 đ / tờ")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByText("Đổi việc")).toBeNull();
    expect(screen.getByText("Thay kẽm")).toBeInTheDocument();
  });

  it("chưa cấu hình vẫn mở form ghi mẻ bình thường", () => {
    mo(null);
    expect(screen.getByText("Công đoạn chưa cấu hình Khoán — vẫn có thể ghi mẻ sản lượng.")).toBeInTheDocument();
    expect(screen.getByLabelText("Số lượng làm được")).toBeInTheDocument();
  });
});
