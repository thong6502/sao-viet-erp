// Dòng MẺ ở bàn tổ (spec 2026-09-18 §7): mẻ ghi theo CÔNG VIỆC KHOÁN, việc phát sinh không cộng
// sản lượng, người tham gia chỉ là danh sách — KHÔNG chia sản lượng, không số phút, không tiền.
// Danh mục đổi sau lúc ghi ⇒ băng cũ → mới + nút lấy số mới (§7.2b).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BatchRow, type ThsxExec } from "./ThsxExecPanels";
import type { SxBatch } from "../api/client";

const batch = {
  id: 1, bat_dau: "2026-09-11T07:00:00", ket_thuc: "2026-09-11T09:00:00",
  tong: 1000, tot: 980, hong: 20, don_vi: "to",
  mo_ta_loi: null, ghi_chu: null, version: 1, lot_vao: [], da_ban_giao: false,
  may_ten: null, ca_ten: null, so_nguoi: 2, su_co: [],
  nguoi_tham_gia: [
    { employee_id: 11, ho_ten: "Lê Văn A" },
    { employee_id: 12, ho_ten: "Trần Thị B" },
  ],
  viec_khoan_id: 7, viec_khoan_ten: "Bình bài & ra kẽm", viec_khoan_don_vi: "ban",
  viec_khoan_don_vi_ten: "bản kẽm", viec_khoan_don_gia: 15000,
  phat_sinh: [{ id: 3, phat_sinh_id: 9, so_luong: 2, ten: "Thay kẽm", don_vi: "ban", don_vi_ten: "bản", don_gia: 40000 }],
  danh_muc_doi: [],
} as unknown as SxBatch;

function execGia() {
  return { capNhatDanhMucMe: vi.fn().mockResolvedValue(true) } as unknown as ThsxExec & {
    capNhatDanhMucMe: ReturnType<typeof vi.fn>;
  };
}

describe("Dòng mẻ ở bàn tổ", () => {
  it("dòng gấp hiện tên việc khoán; mở ra thấy đơn giá · ĐVT, phát sinh và người — không chia, không phút", async () => {
    render(<BatchRow b={batch} canAssign busy={false} exec={execGia()} />);
    expect(screen.getByText("Bình bài & ra kẽm")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText(/15\.000 đ \/ bản kẽm/)).toBeInTheDocument();
    expect(screen.getByText("Thay kẽm")).toBeInTheDocument();
    expect(screen.getByText(/không cộng sản lượng/)).toBeInTheDocument();
    expect(screen.getByText("Lê Văn A, Trần Thị B")).toBeInTheDocument();
    expect(screen.queryByText(/Chia sản lượng|Phút|thành tiền/i)).toBeNull();
  });

  it("mẻ ghi trước bản này nói thẳng 'chưa khai việc khoán', không đoán hộ", () => {
    const b = { ...batch, viec_khoan_id: null, viec_khoan_ten: null, phat_sinh: [] } as SxBatch;
    render(<BatchRow b={b} canAssign busy={false} exec={execGia()} />);
    expect(screen.getByText("chưa khai việc khoán")).toBeInTheDocument();
  });

  it("danh mục đổi ⇒ băng cũ → mới, bấm 'Cập nhật theo danh mục' gọi đúng mẻ", async () => {
    const exec = execGia();
    const b = {
      ...batch,
      danh_muc_doi: [{ truong: "don_gia", nhan: "Đơn giá", cu: "15.000 đ", moi: "18.000 đ", mat: false }],
    } as SxBatch;
    render(<BatchRow b={b} canAssign busy={false} exec={exec} />);
    expect(screen.getByText(/danh mục đổi/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("15.000 đ")).toBeInTheDocument();
    expect(screen.getByText("18.000 đ")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Cập nhật theo danh mục/ }));
    expect(exec.capNhatDanhMucMe).toHaveBeenCalledWith(1);
  });

  it("'Giữ số cũ' chỉ gấp băng, không gọi server; pill vẫn treo và mở lại được", async () => {
    const exec = execGia();
    const b = {
      ...batch,
      danh_muc_doi: [{ truong: "ps:9:don_gia", nhan: "Thay kẽm · đơn giá", cu: "40.000", moi: "45.000", mat: false }],
    } as SxBatch;
    render(<BatchRow b={b} canAssign busy={false} exec={exec} />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getByRole("button", { name: "Giữ số cũ" }));
    expect(exec.capNhatDanhMucMe).not.toHaveBeenCalled();
    expect(screen.queryByText("45.000")).toBeNull();
    expect(screen.getByText(/Mẻ đang giữ số lúc ghi/)).toBeInTheDocument();
    expect(screen.getByText(/danh mục đổi/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
    expect(screen.getByText("45.000")).toBeInTheDocument();
  });

  it("không có quyền ghi thì chỉ thấy băng, không có nút", async () => {
    const b = {
      ...batch,
      danh_muc_doi: [{ truong: "don_gia", nhan: "Đơn giá", cu: "15.000 đ", moi: "18.000 đ", mat: false }],
    } as SxBatch;
    render(<BatchRow b={b} canAssign={false} busy={false} exec={execGia()} />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.queryByRole("button", { name: /Cập nhật theo danh mục/ })).toBeNull();
  });

  it("thân mẻ hiện máy, ca và sự cố", async () => {
    const b = {
      ...batch, may_ten: "Komori 1050", ca_ten: "Ca 1",
      su_co: [{ bat_dau: "2026-09-11T08:00:00", ket_thuc: "2026-09-11T08:20:00", ly_do: "kẹt giấy" }],
    } as SxBatch;
    render(<BatchRow b={b} canAssign busy={false} exec={execGia()} />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    for (const chu of ["Komori 1050", "Ca 1", "kẹt giấy"]) {
      expect(screen.getByText(new RegExp(chu))).toBeInTheDocument();
    }
    expect(screen.getByText(/08:00–08:20: kẹt giấy/)).toBeInTheDocument();
  });

  it("lần dừng qua nửa đêm kèm ngày, dừng chưa chạy lại thì nói rõ", async () => {
    const b = {
      ...batch,
      bat_dau: "2026-09-11T22:00:00", ket_thuc: "2026-09-11T23:50:00",
      su_co: [
        { bat_dau: "2026-09-11T23:40:00", ket_thuc: "2026-09-12T00:21:00", ly_do: "hết giấy" },
        { bat_dau: "2026-09-11T23:45:00", ket_thuc: null, ly_do: "mất điện" },
      ],
    } as SxBatch;
    render(<BatchRow b={b} canAssign busy={false} exec={execGia()} />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText(/23:40–12\/09 00:21: hết giấy/)).toBeInTheDocument();
    expect(screen.getByText(/từ 23:45, chưa chạy lại: mất điện/)).toBeInTheDocument();
  });
});
