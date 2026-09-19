// Bước "Giao hàng" trong drawer đơn — luật chốt 19/09/2026: KHÔNG lập yêu cầu giao cho phần chưa
// nhập kho. Ô số lượng điền sẵn và TRẦN theo `giao_duoc` máy chủ tính; sản phẩm chưa có hàng trong
// kho thì không có ô.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BuocGiaoHang, tomTatTienDo } from "./TienDoDon";
import { AuthContext, type AuthState } from "../../../auth/AuthContext";
import { PermissionsProvider, buildCapabilities } from "../../../auth/permissions";
import type { DonTienDo, DonTienDoCum, ModuleCapability, OrderDetail } from "../../../api/client";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

function cum(o: Partial<DonTienDoCum>): DonTienDoCum {
  return {
    khoa: "k", ten: "Hộp", don_vi: "hộp", order_line_ids: [11], dat: 100, co_lenh: true, lenh: [],
    sx_pct: 50, sx_xong: false, kho_de_nghi: 60, kho_da_nhan: 40, cho_kho: 20, ton_that: 40,
    da_giao: 0, dang_giu: 0, con_phai_giao: 100, giao_duoc: 40, ...o,
  };
}

const TD: DonTienDo = {
  order_id: 3, han_cam_ket: null, du_kien_xong: null, chua_du_du_lieu: false, tre_ngay: null,
  ly_do: [],
  cum: [
    cum({ khoa: "hop", ten: "Hộp thuốc", order_line_ids: [11] }),
    cum({ khoa: "to", ten: "Tờ hướng dẫn", order_line_ids: [12], kho_da_nhan: 0, ton_that: 0, giao_duoc: 0 }),
  ],
  yeu_cau: [],
  noi_nhan: {
    khach_id: 7, dia_chi: "Lô C3", nguoi_nhan: "Chị Hạnh", sdt: "0938", luu_y: "Gọi trước 30 phút",
    so_dia_chi: [{ id: 21, nhan: "Kho Bắc Ninh", dia_chi: "KCN Quế Võ", sdt: null, mac_dinh: true }],
    lien_he: [{ id: 31, ten: "Anh Tùng", chuc_vu: "Thủ kho", sdt: "0912", chinh: false }],
  },
};

const ORDER = {
  id: 3, status: "ordered", delivery_address: "Lô C3", delivery_contact_name: "Chị Hạnh",
  delivery_contact_phone: "0938",
} as unknown as OrderDetail;

function ngayMai(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function stubApi() {
  const posts: Record<string, unknown>[] = [];
  vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => {
    if (init?.method === "POST") posts.push(JSON.parse(String(init.body)));
    return Promise.resolve({
      ok: true, status: 201, headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({}), text: async () => "{}",
    } as Response);
  }));
  return posts;
}

function ve(td: DonTienDo = TD) {
  const caps = buildCapabilities([
    { module_key: "giao_hang", scope: "all", can_read: true, can_create: true } as ModuleCapability,
  ]);
  return render(
    <AuthContext.Provider value={AUTH}>
      <PermissionsProvider caps={caps}>
        <BuocGiaoHang order={ORDER} td={td} taiLai={() => {}} onIn={() => {}} />
      </PermissionsProvider>
    </AuthContext.Provider>,
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe("Bước Giao hàng · chỉ giao phần kho đã nhận", () => {
  it("điền sẵn phần giao được, sản phẩm chưa có hàng không có ô, gửi đúng dòng đầu cụm", async () => {
    const posts = stubApi();
    ve();
    await userEvent.click(screen.getByRole("button", { name: "Tạo yêu cầu giao hàng" }));
    const o = screen.getByLabelText("Số lượng giao — Hộp thuốc") as HTMLInputElement;
    expect(o.value).toBe("40");
    expect(o.max).toBe("40");
    expect(screen.queryByLabelText("Số lượng giao — Tờ hướng dẫn")).toBeNull();
    expect(screen.getByText(/Chưa có hàng trong kho: Tờ hướng dẫn/)).toBeInTheDocument();

    const ngay = document.querySelector("input[type=date]") as HTMLInputElement;
    await userEvent.type(ngay, ngayMai());
    await userEvent.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].lines).toEqual([{ order_line_id: 11, qty: 40 }]);
    // Không đổi gì ⇒ nơi nhận theo đơn; không có ô gõ tay nào.
    expect(posts[0]).toMatchObject({ dia_chi_id: null, lien_he_id: null });
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("nơi nhận CHỌN trong sổ của khách, lưu ý giao lấy của đơn", async () => {
    const posts = stubApi();
    ve();
    await userEvent.click(screen.getByRole("button", { name: "Tạo yêu cầu giao hàng" }));
    expect(screen.getByText("Gọi trước 30 phút")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Kho Bắc Ninh" }));
    await userEvent.click(screen.getByRole("radio", { name: "Anh Tùng" }));
    const ngay = document.querySelector("input[type=date]") as HTMLInputElement;
    await userEvent.type(ngay, ngayMai());
    await userEvent.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ dia_chi_id: 21, lien_he_id: 31 });
  });

  it("đơn lẫn khách đều chưa có địa chỉ ⇒ báo bổ sung ở hồ sơ khách, khoá Gửi", async () => {
    stubApi();
    ve({ ...TD, noi_nhan: { ...TD.noi_nhan, dia_chi: null, so_dia_chi: [] } });
    await userEvent.click(screen.getByRole("button", { name: "Tạo yêu cầu giao hàng" }));
    expect(screen.getByText(/chưa có địa chỉ giao — thêm ở hồ sơ khách hàng/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gửi yêu cầu" })).toBeDisabled();
  });

  it("gõ vượt phần giao được ⇒ báo ngay và khoá nút Gửi", async () => {
    stubApi();
    ve();
    await userEvent.click(screen.getByRole("button", { name: "Tạo yêu cầu giao hàng" }));
    const o = screen.getByLabelText("Số lượng giao — Hộp thuốc");
    await userEvent.clear(o);
    await userEvent.type(o, "41");
    expect(screen.getByText(/Vượt — giao được tối đa 40/)).toBeInTheDocument();
    expect(screen.getByText("Số lượng vượt phần giao được")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gửi yêu cầu" })).toBeDisabled();
  });

  it("kho chưa nhận gì ⇒ nút tạo yêu cầu khoá kèm lý do", () => {
    stubApi();
    ve({ ...TD, cum: TD.cum.map((c) => ({ ...c, giao_duoc: 0 })) });
    expect(screen.getByRole("button", { name: "Tạo yêu cầu giao hàng" })).toBeDisabled();
    expect(screen.getByText(/chỉ lập yêu cầu cho phần kho đã nhận/)).toBeInTheDocument();
  });

  it("yêu cầu có chuyến đã huỷ ⇒ Kinh doanh huỷ được, không sửa được", () => {
    stubApi();
    ve({
      ...TD,
      yeu_cau: [{
        id: 5, code: "YCGH-0005", ngay_can_giao: ngayMai(), trang_thai: "chuyen_da_huy", ly_do_huy: null,
        dia_chi: "Lô C3", nguoi_nhan: null, sdt_nguoi_nhan: null, ghi_chu: null, created_at: "",
        dong: [{ order_line_id: 11, ten: "Hộp thuốc", qty: 40, da_giao: 0 }],
        chuyen: {
          id: 9, trang_thai: "da_huy", gio_lay_hang: "", gio_du_kien_giao: "", tai_xe: "Anh Tư",
          xe: null, thoi_gian_ket_thuc: null, nguoi_nhan_thuc_te: null, ly_do_that_bai: null,
          tra_hang_ma: null, tra_hang_xong: false, so_anh: 0,
        },
      }],
    });
    expect(screen.getByText("Chuyến đã huỷ")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Huỷ" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sửa" })).toBeNull();
  });
});

describe("Tóm tắt vòng đời · Nhập kho tính mọi sản phẩm, báo món thiếu nguồn", () => {
  // Giống DH002: 1 món có lệnh chưa nhận gì, 1 món giao từ tồn đủ hàng, 2 món không lệnh mà tồn 0.
  const td = {
    ...TD,
    cum: [
      cum({ khoa: "hop", dat: 20000, co_lenh: true, kho_da_nhan: 0, giao_duoc: 0, ton_that: 0 }),
      cum({ khoa: "menu", dat: 1500, co_lenh: false, kho_da_nhan: 0, ton_that: 1500, giao_duoc: 1500 }),
      cum({ khoa: "toroi", dat: 30000, co_lenh: false, kho_da_nhan: 0, ton_that: 0, giao_duoc: 0 }),
      cum({ khoa: "poster", dat: 500, co_lenh: false, kho_da_nhan: 0, ton_that: 0, giao_duoc: 0 }),
    ],
  };

  it("món lấy từ tồn đủ hàng được tính vào Nhập kho, món thiếu nguồn được liệt kê", () => {
    const t = tomTatTienDo(td);
    expect(t.soMonDuHang).toBe(1);
    expect(t.soMon).toBe(4);
    expect(t.khoPct).toBe(25);
    expect(t.khoXong).toBe(false);
    expect(t.thieuNguon.map((c) => c.khoa)).toEqual(["toroi", "poster"]);
  });

  it("món từ tồn đã giao một phần + đang giữ vẫn tính là đã có hàng", () => {
    const t = tomTatTienDo({
      ...TD,
      cum: [cum({ khoa: "menu", dat: 1500, co_lenh: false, da_giao: 500, dang_giu: 400, giao_duoc: 600 })],
    });
    expect(t.khoXong).toBe(true);
    expect(t.thieuNguon).toHaveLength(0);
  });
});
