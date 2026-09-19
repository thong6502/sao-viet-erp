import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { SxWorkItemChiTiet } from "../api/client";
import { ThsxDrawer } from "./ThsxDrawer";
import type { ThsxExec } from "./ThsxExecPanels";
import type { SxChoCuaViec } from "./thsxChoXacNhan";
import type { ThsxDrawerTab } from "./ThsxDrawer";

// Thẻ tệp và mục Kết quả KCS tự gọi API lúc mount — ngoài phạm vi các test này.
vi.mock("./ThsxTepLenh", () => ({ ThsxTepLenh: () => null }));
vi.mock("./ThsxKetQuaKcs", () => ({ ThsxKetQuaKcs: () => <div>[kết quả KCS]</div> }));

function chiTiet(runOrder: boolean, daNhan = false, muc?: "all" | "own"): SxWorkItemChiTiet {
  return {
    cong_viec: {
      id: 1, department_id: 7, nguon_ma: "LSX26-0001", nguon_ten: "Hộp bánh", ten_cong_doan: "Bế",
      loai_buoc: "may", nha_cung_cap: null, may_id: null, may: null,
      quy_cach: null, ghi_chu: null, trang_thai: "released",
      khuon: { ma: "KB-0004", ten: "Hộp bánh mang đi 4 ngăn", so_ke: "Kệ B2", tinh_trang: "dang_dat_lam" },
      khuon_da_nhan: daNhan, khuon_da_tra: false,
    },
    trang_thai: "released",
    version: 1,
    quyen: { run_order: runOrder },
    quyen_muc: muc ? { run_order: muc } : {},
    phan_cong: [], phien_chay: [], khoang_tham_gia: [],
  } as unknown as SxWorkItemChiTiet;
}

function mo(runOrder: boolean, daNhan = false, muc?: "all" | "own") {
  const onNhanKhuon = vi.fn();
  render(
    <ThsxDrawer chiTiet={chiTiet(runOrder, daNhan, muc)} loading={false} candidates={[]} hoTroUngVien={[]}
      mayOptions={[]} exec={{} as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
      onBatDau={vi.fn()} onNhanKhuon={onNhanKhuon} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
      onKetThuc={vi.fn()} onClose={vi.fn()} />,
  );
  return { onNhanKhuon };
}

describe("ThsxDrawer · khuôn chưa nhận", () => {
  it("có quyền Thực hiện lệnh: nút Đã nhận khuôn hiện, cảnh báo gọi đúng tên nút và mục", () => {
    const { onNhanKhuon } = mo(true);
    screen.getByRole("button", { name: "Đã nhận khuôn" }).click();
    expect(onNhanKhuon).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).toContain(
      "Chưa nhận khuôn/khung KB-0004 — bấm “Đã nhận khuôn” ở mục Khuôn & khung rồi mới Bắt đầu.",
    );
    expect(document.body.textContent).not.toContain("khối trên");
    expect(document.body.textContent).not.toContain("Cần quyền Thực hiện lệnh");
  });

  it("thiếu quyền: không có nút, cả khối lẫn cảnh báo nói lý do thay vì bảo đi tìm nút", () => {
    mo(false);
    expect(screen.queryByRole("button", { name: "Đã nhận khuôn" })).toBeNull();
    expect(screen.getByText("Cần quyền Thực hiện lệnh ở tổ này mới xác nhận nhận khuôn được.")).toBeTruthy();
    expect(document.body.textContent).toContain(
      "Chưa nhận khuôn/khung KB-0004 — cần quyền Thực hiện lệnh ở tổ này mới xác nhận được.",
    );
  });

  it("quyền Của tôi mà việc chưa giao: nói là chưa giao cho bạn, không bảo đi xin quyền", () => {
    mo(false, false, "own");
    expect(screen.queryByRole("button", { name: "Đã nhận khuôn" })).toBeNull();
    expect(screen.getByText(
      "Việc này chưa giao cho bạn — quyền Thực hiện lệnh của bạn ở tổ này là “Của tôi”, chỉ áp cho việc được giao.",
    )).toBeTruthy();
    expect(document.body.textContent).toContain(
      "Chưa nhận khuôn/khung KB-0004 — việc chưa giao cho bạn, mà quyền của bạn ở tổ này là “Của tôi”.",
    );
    expect(document.body.textContent).not.toContain("Cần quyền");
    expect(document.body.textContent).not.toContain("cần quyền");
  });

  it("đã nhận: không còn cảnh báo, không còn dòng thiếu quyền", () => {
    mo(false, true);
    expect(document.body.textContent).not.toContain("Chưa nhận khuôn/khung");
    expect(document.body.textContent).not.toContain("Cần quyền Thực hiện lệnh");
  });
});

// Kíp chuẩn GỠ 18/09/2026 (mg `0321`): hệ thôi biết một việc NÊN mấy người, nên không còn câu
// "số thợ khác kíp chuẩn" nào — chỉ giữ luật về NGƯỜI (≥ 1 thợ, có thợ không phải công nhật).
describe("ThsxDrawer · thợ được giao", () => {
  function moKip(soDangGiao: number, trangThai = "released", laKhoan = true) {
    const base = chiTiet(true, true);
    const phanCong = Array.from({ length: soDangGiao }, (_, i) => ({
      id: i + 1, employee_id: 100 + i, ho_ten: `Thợ ${i + 1}`, la_luong_khoan: laKhoan, trang_thai: "active",
    }));
    const ct = {
      ...base,
      cong_viec: { ...base.cong_viec, khuon: null, trang_thai: trangThai },
      trang_thai: trangThai,
      phan_cong: phanCong,
    } as unknown as SxWorkItemChiTiet;
    render(
      <ThsxDrawer chiTiet={ct} loading={false} candidates={[]} hoTroUngVien={[]}
        mayOptions={[]} exec={{} as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
        onBatDau={vi.fn()} onNhanKhuon={vi.fn()} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
        onKetThuc={vi.fn()} onClose={vi.fn()} />,
    );
    return document.body.textContent ?? "";
  }

  it("chưa giao ai: chỉ báo cần giao thợ, không báo lệch kíp (dễ đọc nhầm là lệch giờ)", () => {
    const txt = moKip(0);
    expect(txt).toContain("Chưa giao ai — giao ít nhất 1 thợ để bắt đầu.");
    expect(txt).toContain("Cần giao ít nhất 1 thợ mới bắt đầu được.");
    expect(txt).not.toContain("kíp chuẩn");
    expect(txt).not.toContain("Kíp lệch");
    expect(txt).not.toContain("khoán");
  });

  it("giao 1 thợ: không còn câu kíp chuẩn nào, thẻ thợ không gắn chữ khoán", () => {
    const txt = moKip(1);
    expect(txt).not.toContain("kíp chuẩn");
    expect(txt).not.toContain("chọn lý do");
    expect(txt).not.toContain("khoán");
    expect(txt).not.toContain("Cần giao ít nhất 1 thợ");
    expect(txt).toContain("Đã giao: 1 thợ");
  });

  it("người đang giao toàn công nhật: gắn thẻ công nhật và nói vì sao chưa bắt đầu được", () => {
    const txt = moKip(2, "released", false);
    expect(txt).toContain("công nhật");
    expect(txt).toContain("Người đang giao đều là công nhật — cần thêm ít nhất 1 thợ không phải công nhật mới bắt đầu được.");
    expect(txt).not.toContain("khoán");
  });

  it("tạm dừng với 3 thợ: không hỏi lý do số người", () => {
    const txt = moKip(3, "paused");
    expect(txt).not.toContain("kíp chuẩn");
    expect(txt).not.toContain("chọn lý do");
  });
});

describe("ThsxDrawer · tab KCS", () => {
  function moTab(props: { tabDau?: ThsxDrawerTab; cho?: SxChoCuaViec } = {}) {
    render(
      <ThsxDrawer chiTiet={chiTiet(true, true)} loading={false} candidates={[]} hoTroUngVien={[]}
        mayOptions={[]} exec={{} as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
        onBatDau={vi.fn()} onNhanKhuon={vi.fn()} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
        onKetThuc={vi.fn()} onClose={vi.fn()} {...props} />,
    );
  }

  it("kết quả KCS không nằm lẫn trong tab Vận hành, bấm tab KCS mới hiện", () => {
    moTab();
    expect(screen.queryByText("[kết quả KCS]")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "KCS" }));
    expect(screen.getByText("[kết quả KCS]")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "KCS" }).getAttribute("aria-selected")).toBe("true");
  });

  it("mở từ lỗi KCS: vào thẳng tab KCS, có chấm báo lỗi chờ xem", () => {
    moTab({ tabDau: "kcs", cho: { nhan: 0, kcs: 1, hoTro: 0 } });
    expect(screen.getByText("[kết quả KCS]")).toBeTruthy();
    expect(screen.getByTitle("Có lỗi KCS chờ tổ xem")).toBeTruthy();
  });

  it("không có lỗi chờ xem: không có chấm", () => {
    moTab();
    expect(screen.queryByTitle("Có lỗi KCS chờ tổ xem")).toBeNull();
  });

  it("đổi tab thì khung cuộn về đầu, không giữ vị trí cuộn của tab cũ", () => {
    // jsdom không cuộn thật (scrollTop luôn 0, gán bị bỏ qua) — cắm tạm getter/setter để đọc được giá trị gán.
    const goc = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTop");
    const cuon = new WeakMap<HTMLElement, number>();
    Object.defineProperty(HTMLElement.prototype, "scrollTop", {
      configurable: true,
      get(this: HTMLElement) { return cuon.get(this) ?? 0; },
      set(this: HTMLElement, v: number) { cuon.set(this, v); },
    });
    try {
      moTab();
      const body = document.querySelector<HTMLElement>(".thsx-panel__body")!;
      body.scrollTop = 488;
      fireEvent.click(screen.getByRole("tab", { name: "KCS" }));
      expect(body.scrollTop).toBe(0);
    } finally {
      if (goc) Object.defineProperty(HTMLElement.prototype, "scrollTop", goc);
      else delete (HTMLElement.prototype as { scrollTop?: number }).scrollTop;
    }
  });
});

describe("ThsxDrawer · tab Nhận (§11.5)", () => {
  function moNhan(props: { tabDau?: ThsxDrawerTab; cho?: SxChoCuaViec; confirm?: boolean } = {}) {
    const base = chiTiet(true, true);
    const ct = {
      ...base,
      quyen: { ...base.quyen, confirm_output: props.confirm ?? true },
      ban_giao_den: [
        { id: 5, doi_tac_cong_viec_id: 9, doi_tac_ten: "Cán màng mờ", cung_to: false, so_luong: 50,
          don_vi: "to", trang_thai: "adjusted", khong_nhat_quan: false, version: 3, batch_ids: [],
          nguoi_de_xuat: "Lê Cán Màng", de_xuat_luc: "2026-09-17T08:30:00",
          nguoi_xac_nhan: "Trần Tổ Bế", xac_nhan_luc: "2026-09-17T09:10:00",
          dieu_chinh: [{ so_luong_truoc: 55, so_luong_sau: 50, mo_ta: "Đếm lại thiếu 5", khong_nhat_quan: false,
            nguoi: "Trần Tổ Bế", luc: "2026-09-17T10:00:00" }] },
        { id: 6, doi_tac_cong_viec_id: 9, doi_tac_ten: "Cán màng mờ", cung_to: false, so_luong: 30,
          don_vi: "to", trang_thai: "proposed", khong_nhat_quan: false, version: 1, batch_ids: [],
          nguoi_de_xuat: "Lê Cán Màng", de_xuat_luc: "2026-09-17T11:00:00",
          nguoi_xac_nhan: null, xac_nhan_luc: null, dieu_chinh: [] },
      ],
    } as unknown as SxWorkItemChiTiet;
    const xacNhanBanGiao = vi.fn();
    render(
      <ThsxDrawer chiTiet={ct} loading={false} candidates={[]} hoTroUngVien={[]}
        mayOptions={[]} exec={{ xacNhanBanGiao } as unknown as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
        onBatDau={vi.fn()} onNhanKhuon={vi.fn()} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
        onKetThuc={vi.fn()} onClose={vi.fn()} tabDau={props.tabDau} cho={props.cho} />,
    );
    return { xacNhanBanGiao };
  }

  it("mở từ bàn giao chờ nhận: vào thẳng tab Nhận, có chấm, nút Xác nhận ngay đầu danh sách", () => {
    const { xacNhanBanGiao } = moNhan({ tabDau: "nhan", cho: { nhan: 1, kcs: 0, hoTro: 0 } });
    expect(screen.getByRole("tab", { name: /Nhận/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTitle("Có bàn giao chờ tổ nhận")).toBeTruthy();
    const dong = document.querySelectorAll(".thsx-x-bg");
    expect(dong).toHaveLength(2);
    // Lần chờ nhận đứng trước lần đã xác nhận.
    expect(dong[0].textContent).toContain("chờ xác nhận");
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận" }));
    expect(xacNhanBanGiao).toHaveBeenCalledWith(6, 1);
  });

  it("không có việc chờ: mở ở Vận hành, không chấm; bấm tab Nhận vẫn thấy lịch sử bàn giao đến", () => {
    moNhan();
    expect(screen.queryByTitle("Có bàn giao chờ tổ nhận")).toBeNull();
    expect(document.querySelectorAll(".thsx-x-bg")).toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: /Nhận/ }));
    expect(document.querySelectorAll(".thsx-x-bg")).toHaveLength(2);
  });

  it("mỗi dòng ghi ai giao, ai nhận, lúc nào; lịch sử điều chỉnh mở ra đủ ai · trước → sau · mô tả", () => {
    moNhan({ tabDau: "nhan" });
    const [cho, daNhan] = Array.from(document.querySelectorAll<HTMLElement>(".thsx-x-bg"));
    expect(cho.textContent).toContain("Giao: Lê Cán Màng");
    expect(cho.textContent).toContain("Nhận: chưa xác nhận");
    expect(within(cho).queryByRole("button", { name: /Đã điều chỉnh/ })).toBeNull();

    expect(daNhan.textContent).toContain("Giao: Lê Cán Màng");
    expect(daNhan.textContent).toMatch(/Nhận: Trần Tổ Bế · .*09:10/);
    expect(within(daNhan).queryByRole("list", { name: "Lịch sử điều chỉnh" })).toBeNull();
    fireEvent.click(within(daNhan).getByRole("button", { name: "Đã điều chỉnh 1 lần" }));
    const ls = within(daNhan).getByRole("list", { name: "Lịch sử điều chỉnh" });
    expect(ls.textContent).toMatch(/10:00 · Trần Tổ Bế · 55 → 50 \S+ · Đếm lại thiếu 5/);
  });

  it("thiếu quyền Xác nhận sản lượng: không có nút, nói rõ cần quyền gì", () => {
    moNhan({ tabDau: "nhan", confirm: false });
    expect(screen.queryByRole("button", { name: "Xác nhận" })).toBeNull();
    expect(screen.getByText("Xác nhận nhận hàng cần quyền Xác nhận sản lượng của tổ.")).toBeTruthy();
  });
});

// Routing lệnh (19/09/2026, `dau_vao.py`): chưa nhận hàng từ công đoạn trước thì chưa Bắt đầu được;
// tab Nhận bày kế hoạch · thực tế (cộng mẻ) · đã giao sang · đã nhận của từng công đoạn trước.
describe("ThsxDrawer · công đoạn trước", () => {
  function moTruoc(thieu: string[], choXacNhan = 0) {
    const base = chiTiet(true, true);
    const ct = {
      ...base,
      cong_viec: { ...base.cong_viec, khuon: null },
      phan_cong: [{ id: 1, employee_id: 100, ho_ten: "Thợ 1", la_luong_khoan: true, trang_thai: "active" }],
      thieu_dau_vao: thieu,
      cong_doan_truoc: [{
        cong_viec_id: 9, ten_cong_doan: "In offset", phan_doan_so: 1, phan_doan_tong: 2, to_ten: "Tổ In",
        trang_thai: "running", ke_hoach: 1200, don_vi: "to", thuc_te: 1150, da_giao: 1000 + choXacNhan,
        da_xac_nhan: thieu.length ? 0 : 1000, cho_xac_nhan: choXacNhan, don_vi_giao: "to",
      }],
    } as unknown as SxWorkItemChiTiet;
    render(
      <ThsxDrawer chiTiet={ct} loading={false} candidates={[]} hoTroUngVien={[]}
        mayOptions={[]} exec={{} as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
        onBatDau={vi.fn()} onNhanKhuon={vi.fn()} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
        onKetThuc={vi.fn()} onClose={vi.fn()} tabDau="nhan" />,
    );
  }

  it("chưa nhận: nút Bắt đầu khoá, chân ngăn gọi tên công đoạn trước và chỉ tab Nhận", () => {
    moTruoc(["In offset"], 1000);
    expect((screen.getByRole("button", { name: "Bắt đầu" }) as HTMLButtonElement).disabled).toBe(true);
    expect(document.body.textContent).toContain(
      "Chưa nhận hàng từ In offset — tổ trước giao sang và tổ mình xác nhận ở tab “Nhận” rồi mới Bắt đầu được.",
    );
    const [dong] = Array.from(document.querySelectorAll<HTMLElement>(".thsx-x-bg"));
    expect(dong.textContent).toContain("In offset · lần 1/2 · Tổ In");
    expect(dong.textContent).toMatch(/Kế hoạch1\.200/);
    expect(dong.textContent).toMatch(/Thực tế1\.150/);
    expect(dong.textContent).toMatch(/Giao sang2\.000/);
    expect(dong.textContent).toMatch(/Đã nhận0/);
    expect(dong.textContent).toContain("chờ xác nhận");
  });

  it("đã nhận: Bắt đầu mở, không còn câu chưa nhận hàng", () => {
    moTruoc([]);
    expect((screen.getByRole("button", { name: "Bắt đầu" }) as HTMLButtonElement).disabled).toBe(false);
    expect(document.body.textContent).not.toContain("Chưa nhận hàng từ");
    expect(document.body.textContent).not.toContain("chờ xác nhận");
  });
});

describe("ThsxDrawer · chân ngăn theo trạng thái", () => {
  function moTrangThai(trangThai: string) {
    const base = chiTiet(true, true);
    const ct = {
      ...base,
      cong_viec: { ...base.cong_viec, trang_thai: trangThai },
      trang_thai: trangThai,
    } as unknown as SxWorkItemChiTiet;
    render(
      <ThsxDrawer chiTiet={ct} loading={false} candidates={[]} hoTroUngVien={[]}
        mayOptions={[]} exec={{} as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
        onBatDau={vi.fn()} onNhanKhuon={vi.fn()} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
        onKetThuc={vi.fn()} onClose={vi.fn()} />,
    );
  }

  it("việc Hoàn thành: không còn hàng nút chạy máy nào (kể cả nút mờ)", () => {
    moTrangThai("completed");
    for (const ten of ["Bắt đầu", "Tiếp tục", "Tạm dừng", "Kết thúc", "Đổi máy", "Báo sự cố"]) {
      expect(screen.queryByRole("button", { name: ten })).toBeNull();
    }
  });

  it("việc chưa làm vẫn có Bắt đầu; tạm dừng có Tiếp tục + Kết thúc; đang chạy có Tạm dừng + Kết thúc", () => {
    moTrangThai("released");
    expect(screen.getByRole("button", { name: "Bắt đầu" })).toBeTruthy();
    document.body.innerHTML = "";
    moTrangThai("paused");
    expect(screen.getByRole("button", { name: "Tiếp tục" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Kết thúc" })).toBeTruthy();
    document.body.innerHTML = "";
    moTrangThai("running");
    expect(screen.getByRole("button", { name: "Tạm dừng" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Kết thúc" })).toBeTruthy();
  });
});

describe("ThsxDrawer · thẻ Quy cách chạy máy", () => {
  function moQuyCach(quy_cach: Record<string, unknown>) {
    const ct = chiTiet(true, true);
    (ct.cong_viec as unknown as { quy_cach: unknown }).quy_cach = quy_cach;
    render(
      <ThsxDrawer chiTiet={ct} loading={false} candidates={[]} hoTroUngVien={[]}
        mayOptions={[]} exec={{} as ThsxExec} busy={false} onGiao={vi.fn()} onRut={vi.fn()}
        onBatDau={vi.fn()} onNhanKhuon={vi.fn()} onTraKhuon={vi.fn()} onTamDung={vi.fn()}
        onKetThuc={vi.fn()} onClose={vi.fn()} />,
    );
    return screen.getByText("Quy cách chạy máy").closest(".thsx-card") as HTMLElement;
  }

  it("khổ tờ in 0 × 0 (server bỏ khoá): ghi In thẳng khổ giấy nguyên, có khổ nguyên + cách in, mực từng mặt", () => {
    const the = moQuyCach({
      giay: "Giấy C300", kho_nguyen: "860 × 650", kho_tp: "86 × 54", cach_in: "hai_mat",
      so_mat: 2, so_mau: 4, so_kem: 4, muc_a: ["C", "M", "Y"], muc_b: ["K"],
    });
    const chu = the.textContent ?? "";
    expect(chu).toContain("Khổ giấy nguyên:860 × 650 mm");
    expect(chu).toContain("Khổ tờ in:In thẳng khổ giấy nguyên");
    expect(chu).toContain("Cách in:2 mặt (AB)");
    // "2 mặt (AB)" đã nói số mặt — không lặp dòng Số mặt.
    expect(chu).not.toContain("Số mặt:");

    const muc = within(the).getByText("Mực in").closest(".khsx-kv") as HTMLElement;
    const bat = (ten: string) => within(muc).getByRole("button", { name: ten }).getAttribute("aria-pressed");
    expect(bat("Mực C Mặt A")).toBe("true");
    expect(bat("Mực K Mặt A")).toBe("false");
    expect(bat("Mực K Mặt B")).toBe("true");
    expect(bat("Mực C Mặt B")).toBe("false");
    // Chỉ để xem: chip không bấm đổi được.
    expect((within(muc).getByRole("button", { name: "Mực C Mặt A" }) as HTMLButtonElement).disabled).toBe(true);
    expect(muc.textContent).toContain("3 + 1 = 4 kẽm mỗi tay");
  });

  it("có khổ tờ in thì ghi khổ; thẻ cũ không có cách in/mực thì vẫn hiện Số mặt, không có khối mực", () => {
    const the = moQuyCach({ giay: "Giấy C300", kho_in: "790 × 545", so_mat: 1, so_mau: 4 });
    const chu = the.textContent ?? "";
    expect(chu).toContain("Khổ tờ in:790 × 545 mm");
    expect(chu).toContain("Số mặt:1");
    expect(within(the).queryByText("Mực in")).toBeNull();
  });
});
