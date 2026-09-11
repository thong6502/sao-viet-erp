// Khối chia sản lượng của một mẻ: KHÔNG được có ô tiền nào (11/09/2026 — sản xuất chỉ ghi số lượng).
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PhanBoBlock } from "./ThsxExecPanels";
import type { SxBatch, SxPhanBo } from "../api/client";

const batch = {
  id: 1, bat_dau: "2026-09-11T07:00:00", ket_thuc: "2026-09-11T09:00:00",
  tong: 1000, tot: 980, hong: 20, don_vi: "to",
  mo_ta_loi: null, ghi_chu: null, version: 1, nguoi_tham_gia: [], lot_vao: [],
} as unknown as SxBatch;

const pb = {
  phan_bo_id: 5, batch_id: 1, trang_thai: "draft", version: 1,
  ngay: "2026-09-11", ky_nam: 2026, ky_thang: 9,
  q_tra_luong: 980, don_vi_tra_luong: "to",
  q_ban_dia: 980, don_vi_ban_dia: "to", tong_ty_le_ho_tro: 0,
  can_chot: true, canh_bao: [], thieu_cham_cong: [], loai_tru: [], bu_tru: [],
  dong: [
    { employee_id: 11, ho_ten: "Lê Văn A", department_id: 7, la_ho_tro: false,
      ngay: "2026-09-11", so_luong_tra_luong: 520, so_luong_ban_dia: 520,
      trong_so: 156, phut_thuc_te: 120, he_so_bac: 1.3 },
    { employee_id: 12, ho_ten: "Trần Thị B", department_id: 7, la_ho_tro: false,
      ngay: "2026-09-11", so_luong_tra_luong: 460, so_luong_ban_dia: 460,
      trong_so: 138, phut_thuc_te: 120, he_so_bac: 1.15 },
  ],
} as unknown as SxPhanBo;

const exec = {
  tinhPhanBo: vi.fn(), chotPhanBo: vi.fn(), moLaiPhanBo: vi.fn(),
  loaiTru: vi.fn(), goLoaiTru: vi.fn(),
} as never;

describe("Chia sản lượng", () => {
  it("đổi nhãn khỏi 'Phân bổ lương' và không hiện ô tiền nào", () => {
    render(
      <PhanBoBlock b={batch} pb={pb} canAssign busy={false}
        tenNguoi={new Map()} hoTroUngVien={[]} exec={exec} />,
    );
    expect(screen.getByText("Chia sản lượng")).toBeInTheDocument();
    expect(screen.queryByText(/Phân bổ lương/)).toBeNull();
    expect(screen.queryByText(/đơn giá/i)).toBeNull();
    expect(screen.queryByText(/theo công thức/)).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /Đơn giá/i })).toBeNull();
  });

  it("hiện sản lượng, bậc và PHÚT của từng người", () => {
    render(
      <PhanBoBlock b={batch} pb={pb} canAssign busy={false}
        tenNguoi={new Map()} hoTroUngVien={[]} exec={exec} />,
    );
    expect(screen.getByRole("columnheader", { name: /Phút/i })).toBeInTheDocument();
    expect(screen.getByText("Lê Văn A")).toBeInTheDocument();
    expect(screen.getByText("520")).toBeInTheDocument();
  });
});
