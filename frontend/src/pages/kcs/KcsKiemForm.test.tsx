import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api, type SxKcsCongDoan, type SxKcsKiemKetQua, type SxKcsLenhDau } from "../../api/client";
import { KcsKiemForm } from "./KcsKiemForm";

vi.mock("../../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));

const lenh = { id: 4, ma: "LSX26-0004", ten: "Hộp bánh", khach: null, nhom_id: null, nhom_ma: null, nhom_trang_thai: null } as SxKcsLenhDau;
const cd = {
  cong_viec_id: 11, ten: "Bế", phan_doan_so: 1, phan_doan_tong: 1, to_id: 3, to_ten: "Tổ bế",
  trang_thai: "running", tot: 0, hong: 0, don_vi: "con", la_kcs_cuoi: false, checklist: [],
  so_lan_kiem: 0, tong_dat: 0, tong_loi: 0, da_yeu_cau_kho: 0, con_gui_kho: 0, yeu_cau_kho: [], lan_kiem: [],
} as SxKcsCongDoan;

const anh = (ten: string) => new File(["x"], ten, { type: "image/png" });

function chon(nhan: string, ...files: File[]) {
  const o = screen.getByLabelText(nhan) as HTMLInputElement;
  Object.defineProperty(o, "files", { value: files, configurable: true });
  fireEvent.change(o);
}

describe("KcsKiemForm · danh sách ảnh lỗi", () => {
  let dem = 0;
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => `blob:anh-${++dem}`);
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  it("chụp và chọn nhiều lần thì cộng dồn, bỏ được từng ảnh, Lưu gửi đúng các ảnh còn lại", async () => {
    const kiem = vi.spyOn(api.sanXuat, "kiemCongDoan").mockResolvedValue({} as SxKcsKiemKetQua);
    render(<KcsKiemForm lenh={lenh} cd={cd} onClose={vi.fn()} onSaved={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Mô tả lỗi"), { target: { value: "Xước mép" } });
    expect(screen.getByText("Chưa có ảnh")).toBeTruthy();
    expect((screen.getByLabelText("Chụp ảnh lỗi") as HTMLInputElement).getAttribute("capture")).toBe("environment");

    chon("Chụp ảnh lỗi", anh("chup-1.png"));
    await screen.findByText("chup-1.png");
    chon("Chọn ảnh lỗi", anh("co-san-1.png"), anh("co-san-2.png"));
    await screen.findByText("co-san-2.png");
    // Lần chọn sau KHÔNG đè ảnh chụp trước.
    expect(screen.getByText("chup-1.png")).toBeTruthy();
    expect(screen.getByText("3 ảnh")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Bỏ co-san-1.png" }));
    expect(screen.queryByText("co-san-1.png")).toBeNull();
    expect(screen.getByText("2 ảnh")).toBeTruthy();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Xem trước chup-1.png" }));
    expect(screen.getByRole("dialog", { name: "chup-1.png" })).toBeTruthy();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "chup-1.png" })).toBeNull();

    fireEvent.change(screen.getByLabelText("Số đạt"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    const gui = kiem.mock.calls[0][2].files ?? [];
    expect(gui.map((f) => f.name)).toEqual(["chup-1.png", "co-san-2.png"]);
  });
});
