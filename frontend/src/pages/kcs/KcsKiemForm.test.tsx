import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api, type SxKcsCongDoan, type SxKcsKiemKetQua, type SxKcsLenhDau } from "../../api/client";
import { KcsKiemForm } from "./KcsKiemForm";

vi.mock("../../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));

const lenh = { id: 4, ma: "LSX26-0004", ten: "Hộp bánh", khach: null, nhom_id: null, nhom_ma: null, nhom_trang_thai: null } as SxKcsLenhDau;
const cd = {
  cong_viec_id: 11, ten: "Bế", phan_doan_so: 1, phan_doan_tong: 1, to_id: 3, to_ten: "Tổ bế",
  trang_thai: "running", tot: 120, hong: 0, don_vi: "con", la_kcs_cuoi: false, checklist: [],
  so_lan_kiem: 2, tong_dat: 50, tong_loi: 3, da_yeu_cau_kho: 0, con_gui_kho: 0, yeu_cau_kho: [], lan_kiem: [],
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

    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    const gui = kiem.mock.calls[0][2].files ?? [];
    expect(gui.map((f) => f.name)).toEqual(["chup-1.png", "co-san-2.png"]);
  });
});

describe("KcsKiemForm · chỉ gõ số lỗi", () => {
  // jsdom không có scrollIntoView — form cuộn tới thông báo chặn.
  beforeEach(() => { Element.prototype.scrollIntoView = vi.fn(); });
  afterEach(() => vi.restoreAllMocks());

  it("không có ô Số đạt; đạt = phần tổ làm chưa kiểm − lỗi, gửi lên chỉ số lỗi", async () => {
    const kiem = vi.spyOn(api.sanXuat, "kiemCongDoan").mockResolvedValue({} as SxKcsKiemKetQua);
    render(<KcsKiemForm lenh={lenh} cd={cd} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByLabelText("Số đạt")).toBeNull();
    expect(screen.getByText(/Tổ đã làm:/).textContent).toBe("Tổ đã làm: 120 con");
    // 120 tổ làm − (50 đạt + 3 lỗi) đã kiểm = 67 chưa kiểm.
    expect(screen.getByText(/Lần này kiểm/).textContent).toBe("Lần này kiểm 67 con tổ đã làm mà chưa kiểm → đạt 67 con.");
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "70" } });
    fireEvent.change(screen.getByLabelText("Mô tả lỗi"), { target: { value: "Xước" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    expect(screen.getByRole("alert").textContent).toBe("Số lỗi vượt phần tổ đã làm mà chưa kiểm (67 con).");
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    expect(kiem.mock.calls[0][2]).not.toHaveProperty("so_dat");
    expect(kiem.mock.calls[0][2].so_loi).toBe(0);
  });

  it("tổ chưa ghi thêm gì từ lần kiểm trước ⇒ nói rõ, không cho lưu", () => {
    render(<KcsKiemForm lenh={lenh} cd={{ ...cd, tot: 53 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText(/chưa có gì để kiểm/)).toBeTruthy();
    expect(screen.queryByLabelText("Số lỗi")).toBeNull();
    expect((screen.getByRole("button", { name: "Lưu kết quả kiểm" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
