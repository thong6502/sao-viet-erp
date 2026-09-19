import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { api, type SxKcsCongDoan, type SxKcsKiemKetQua, type SxKcsLenhDau } from "../../api/client";
import { KcsKiemForm } from "./KcsKiemForm";

vi.mock("../../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));

const lenh = { id: 4, ma: "LSX26-0004", ten: "Hộp bánh", khach: null, nhom_id: null, nhom_ma: null, nhom_trang_thai: null } as SxKcsLenhDau;
const cd = {
  cong_viec_id: 11, ten: "Bế", phan_doan_so: 1, phan_doan_tong: 1, to_id: 3, to_ten: "Tổ bế",
  trang_thai: "running", tot: 120, hong: 0, don_vi: "con", la_kcs_cuoi: true, checklist: [],
  so_lan_kiem: 2, tong_dat: 50, tong_loi: 3, da_yeu_cau_kho: 0, con_gui_kho: 0, yeu_cau_kho: [], lan_kiem: [],
  so_luong_ra: null, may: null, ghi_chu_ky_thuat: null, quy_cach: null, me: [],
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
    const body = kiem.mock.calls[0][2];
    expect(body.lsx_id).toBe(4);
    expect(body.loi).toHaveLength(1);
    // Lỗi của chính công đoạn đang kiểm ⇒ `cong_viec_id` để trống, máy chủ tự hiểu.
    expect(body.loi![0].cong_viec_id).toBeNull();
    expect(body.loi![0].so_luong).toBe(2);
    expect(body.loi![0].mo_ta).toBe("Xước mép");
    expect(body.loi![0].files.map((f) => f.name)).toEqual(["chup-1.png", "co-san-2.png"]);
  });
});

describe("KcsKiemForm · quy lỗi về công đoạn trước", () => {
  let dem = 0;
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => `blob:q-${++dem}`);
    URL.revokeObjectURL = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  const inCd = { ...cd, cong_viec_id: 9, ten: "In", to_ten: "Tổ in", don_vi: "to" } as SxKcsCongDoan;
  const sauCd = { ...cd, cong_viec_id: 12, ten: "Dán", to_ten: "Tổ dán" } as SxKcsCongDoan;

  it("chỉ chọn được công đoạn tới công đoạn đang kiểm; chia lỗi hai dòng, mỗi dòng ảnh riêng", async () => {
    const kiem = vi.spyOn(api.sanXuat, "kiemCongDoan").mockResolvedValue({} as SxKcsKiemKetQua);
    render(<KcsKiemForm lenh={lenh} cd={cd} chuoi={[inCd, cd, sauCd]} onClose={vi.fn()} onSaved={vi.fn()} />);
    const sel = screen.getByLabelText("Lỗi do công đoạn") as HTMLSelectElement;
    expect(Array.from(sel.options).map((x) => x.textContent)).toEqual(["In · Tổ in", "Bế · Tổ bế (đang kiểm)"]);
    expect(sel.value).toBe("11");

    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "5" } });
    fireEvent.change(sel, { target: { value: "9" } });
    expect(screen.getByText(/Lỗi tính cho công đoạn/).textContent).toContain("báo về Tổ in");
    fireEvent.change(screen.getByLabelText("Mô tả lỗi"), { target: { value: "Lem mực" } });
    fireEvent.click(screen.getAllByRole("button", { name: /Chọn ảnh có sẵn/ })[0]);
    chon("Chọn ảnh lỗi", anh("lem.png"));
    await screen.findByText("lem.png");

    fireEvent.click(screen.getByRole("button", { name: "+ Thêm dòng lỗi do công đoạn khác" }));
    fireEvent.change(screen.getByLabelText("Số lỗi dòng 2"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Lỗi do công đoạn dòng 2"), { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    expect(screen.getByRole("alert").textContent).toBe("Dòng lỗi 2: có lỗi thì phải mô tả lỗi.");
    fireEvent.change(screen.getByLabelText("Mô tả lỗi dòng 2"), { target: { value: "Bế lệch" } });
    fireEvent.click(screen.getAllByRole("button", { name: /Chọn ảnh có sẵn/ })[1]);
    chon("Chọn ảnh lỗi", anh("lech.png"));
    await screen.findByText("lech.png");
    expect(screen.getByText(/Lần này kiểm/).textContent).toBe("Lần này kiểm 67 con tổ đã làm mà chưa kiểm → đạt 60 con.");

    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    const body = kiem.mock.calls[0][2];
    expect(body.so_loi).toBe(7);
    expect(body.loi!.map((d) => [d.cong_viec_id, d.so_luong, d.mo_ta, d.files.map((f) => f.name)])).toEqual([
      [9, 5, "Lem mực", ["lem.png"]],
      [null, 2, "Bế lệch", ["lech.png"]],
    ]);
  });

  it("công đoạn đầu chuỗi thì không có ô chọn công đoạn", () => {
    render(<KcsKiemForm lenh={lenh} cd={inCd} chuoi={[inCd, cd]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByLabelText("Lỗi do công đoạn")).toBeNull();
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
    expect(screen.getByText("Tổ đã làm").parentElement?.textContent).toContain("120con");
    // 120 tổ làm − (50 đạt + 3 lỗi) đã kiểm = 67 chưa kiểm.
    expect(screen.getByText(/Lần này kiểm/).textContent).toBe("Lần này kiểm 67 con tổ đã làm mà chưa kiểm → đạt 67 con.");
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "70" } });
    fireEvent.change(screen.getByLabelText("Mô tả lỗi"), { target: { value: "Xước" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    expect(screen.getByRole("alert").textContent).toBe("Số lỗi vượt phần tổ đã làm mà chưa kiểm (67 con).");
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "0" } });
    // Sửa ô là thông báo của lần bấm trước hết đúng — không để treo.
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    expect(kiem.mock.calls[0][2]).not.toHaveProperty("so_dat");
    expect(kiem.mock.calls[0][2].so_loi).toBe(0);
  });

  const checklist = [
    { thu_tu: 1, ma: "MAU", ten: "Đúng màu", bat_buoc: true },
    { thu_tu: 2, ma: "MEP", ten: "Mép bế sạch", bat_buoc: false },
  ] as SxKcsCongDoan["checklist"];
  const o = (ten: RegExp) => screen.getByRole("checkbox", { name: ten }) as HTMLInputElement;

  it("tiêu chí là ô tick: tick = đạt, để trống = không đạt; gửi đủ mọi tiêu chí", async () => {
    const kiem = vi.spyOn(api.sanXuat, "kiemCongDoan").mockResolvedValue({} as SxKcsKiemKetQua);
    render(<KcsKiemForm lenh={lenh} cd={{ ...cd, checklist }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Đạt" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    expect(screen.getByRole("alert").textContent).toBe(
      'Tiêu chí bắt buộc "Đúng màu" chưa tick đạt — đạt thì tick, không đạt thì ghi Số lỗi.',
    );
    fireEvent.click(o(/Đúng màu/));
    expect(o(/Đúng màu/).checked).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(o(/Mép bế sạch/));
    fireEvent.click(o(/Mép bế sạch/));
    expect(o(/Mép bế sạch/).checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    expect(kiem.mock.calls[0][2].checklist).toEqual([
      { thu_tu: 1, dat: true, ghi_chu: null },
      { thu_tu: 2, dat: false, ghi_chu: null },
    ]);
  });

  it("Tất cả đạt tick hết rồi đổi thành Bỏ tick hết; bắt buộc để trống mà có Số lỗi thì qua cổng tiêu chí", () => {
    render(<KcsKiemForm lenh={lenh} cd={{ ...cd, checklist }} onClose={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Tất cả đạt" }));
    expect([o(/Đúng màu/).checked, o(/Mép bế sạch/).checked]).toEqual([true, true]);
    fireEvent.click(screen.getByRole("button", { name: "Bỏ tick hết" }));
    expect([o(/Đúng màu/).checked, o(/Mép bế sạch/).checked]).toEqual([false, false]);
    // Không đạt tiêu chí bắt buộc = có hàng lỗi ⇒ ghi Số lỗi là hợp lệ, form đi tiếp tới luật mô tả lỗi.
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu kết quả kiểm" }));
    expect(screen.getByRole("alert").textContent).toBe("Có lỗi thì phải mô tả lỗi.");
  });

  it("tổ chưa ghi thêm gì từ lần kiểm trước ⇒ nói rõ, không cho lưu", () => {
    render(<KcsKiemForm lenh={lenh} cd={{ ...cd, tot: 53 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText(/chưa có gì để kiểm/)).toBeTruthy();
    expect(screen.queryByLabelText("Số lỗi")).toBeNull();
    expect((screen.getByRole("button", { name: "Lưu kết quả kiểm" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("KcsKiemForm · công đoạn giữa chỉ ghi lỗi", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    URL.createObjectURL = vi.fn(() => "blob:giua");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());
  const checklist = [{ thu_tu: 1, ma: "MAU", ten: "Đúng màu", bat_buoc: true }] as SxKcsCongDoan["checklist"];
  const giua = { ...cd, la_kcs_cuoi: false, checklist } as SxKcsCongDoan;

  it("không tiêu chí, không đạt; bắt buộc có lỗi; trần = số tốt − lỗi đã ghi; gửi checklist rỗng", async () => {
    const kiem = vi.spyOn(api.sanXuat, "kiemCongDoan").mockResolvedValue({} as SxKcsKiemKetQua);
    render(<KcsKiemForm lenh={lenh} cd={giua} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText("Ghi lỗi công đoạn")).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Tất cả đạt" })).toBeNull();
    expect(screen.queryByText(/Lần này kiểm/)).toBeNull();
    expect(screen.queryByText("Chờ kiểm", { selector: ".kkf-so__nhan" })).toBeNull();
    expect(screen.getByText("Lỗi đã ghi").parentElement?.textContent).toContain("3con");

    fireEvent.click(screen.getByRole("button", { name: "Lưu lỗi" }));
    expect(screen.getByRole("alert").textContent).toBe("Nhập số lỗi.");
    // 120 tốt − 3 lỗi đã ghi = còn ghi được 117 (đạt 50 của dữ liệu cũ không tính vào trần).
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "118" } });
    fireEvent.change(screen.getByLabelText("Mô tả lỗi"), { target: { value: "Xước" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu lỗi" }));
    expect(screen.getByRole("alert").textContent).toBe("Tổng lỗi vượt số tốt tổ đã ghi (còn ghi được 117 con).");
    fireEvent.change(screen.getByLabelText("Số lỗi"), { target: { value: "4" } });
    chon("Chọn ảnh lỗi", anh("xuoc.png"));
    await screen.findByText("xuoc.png");
    fireEvent.click(screen.getByRole("button", { name: "Lưu lỗi" }));
    await waitFor(() => expect(kiem).toHaveBeenCalledTimes(1));
    expect(kiem.mock.calls[0][2].so_loi).toBe(4);
    expect(kiem.mock.calls[0][2].checklist).toEqual([]);
  });

  it("tổ chưa ghi sản lượng ⇒ không cho ghi lỗi", () => {
    render(<KcsKiemForm lenh={lenh} cd={{ ...giua, tot: 0, tong_loi: 0 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText("Tổ chưa ghi sản lượng nào — chưa có hàng để ghi lỗi.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Lưu lỗi" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("KcsKiemForm · bối cảnh để kiểm", () => {
  const me = (id: number, so_luong: number, gio: string) => ({
    id, so_luong, bat_dau: `2026-09-18T${gio}:00`, ket_thuc: `2026-09-18T${gio}:30`, don_vi: "con",
    viec: "Bế hộp", nguoi_ghi: "Tổ trưởng A", nguoi: ["Thợ B", "Thợ C"],
  });

  it("đầu lệnh, dải số, mẻ chờ kiểm (mới nhất trước), quy cách và dặn dò", () => {
    // Chưa kiểm 67 = mẻ 30 mới nhất + 37 của mẻ 50 kế đó; mẻ 40 cũ nhất đã kiểm.
    const cdDu = {
      ...cd, may: "Máy bế 1", so_luong_ra: 200, ghi_chu_ky_thuat: "Bế nhẹ tay, giữ mép",
      quy_cach: { giay: "C300", so_mau: 4 },
      me: [me(3, 30, "10:00"), me(2, 50, "09:00"), me(1, 40, "08:00")],
    } as SxKcsCongDoan;
    render(<KcsKiemForm lenh={{ ...lenh, khach: "Cty Bánh Kẹo" }} cd={cdDu} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText("LSX26-0004")).toBeTruthy();
    expect(screen.getByText("Cty Bánh Kẹo")).toBeTruthy();
    expect(screen.getByText("Máy bế 1")).toBeTruthy();
    expect(screen.getByText("Kế hoạch").parentElement?.textContent).toContain("200con");
    expect(screen.getByText("Chờ kiểm", { selector: ".kkf-so__nhan" }).parentElement?.textContent).toContain("67con");
    const dong = document.querySelectorAll(".kkf-me__it");
    expect(Array.from(dong).map((d) => d.querySelector(".kkf-me__tt")?.textContent)).toEqual([
      "Chờ kiểm", "Còn 37 chờ kiểm", "Đã kiểm",
    ]);
    expect(dong[0].textContent).toContain("Thợ B, Thợ C");
    expect(dong[0].textContent).toContain("ghi: Tổ trưởng A");
    const qc = screen.getByText("Quy cách chạy máy").closest(".thsx-card") as HTMLElement;
    expect(within(qc).getByText("C300")).toBeTruthy();
    expect(screen.getByText("Bế nhẹ tay, giữ mép")).toBeTruthy();
    expect(screen.getByText("Chưa có lần kiểm nào.")).toBeTruthy();
  });

  it("quá 5 mẻ thì gấp, bấm Xem thêm mới hiện mẻ cũ", () => {
    const nhieu = Array.from({ length: 7 }, (_, i) => me(10 - i, 10, `0${i + 1}:00`));
    render(<KcsKiemForm lenh={lenh} cd={{ ...cd, me: nhieu } as SxKcsCongDoan} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(document.querySelectorAll(".kkf-me__it")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "Xem thêm 2 mẻ cũ hơn" }));
    expect(document.querySelectorAll(".kkf-me__it")).toHaveLength(7);
  });
});
