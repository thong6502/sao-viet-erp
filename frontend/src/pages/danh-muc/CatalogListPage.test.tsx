// Hai thứ của đợt "một khung cho 10 màn" mà HỎNG TRONG IM LẶNG — không có test thì phải mở đúng
// màn, đúng vai, đúng lúc backend chết mới thấy:
//
//   1. Bảng NÓI DỐI. Trước 15/08/2026 backend chết là ô trống vẫn in "Chưa có giấy nào trong hệ
//      thống." — câu đó vừa sai vừa mời người ta đi tạo lại dữ liệu đang có sẵn.
//   2. Vai chỉ-đọc vẫn thấy đủ nút Thêm / Xóa, bấm xong mới ăn 403.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CatalogListPage } from "./CatalogListPage";
import type { CatalogConfig } from "./types";
import { useDieuHuongDanhMuc } from "./dieuHuong";
import type { NavigateFn } from "../../components/AppShell";
import { AuthContext, type AuthState } from "../../auth/AuthContext";
import { PermissionsProvider, buildCapabilities } from "../../auth/permissions";
import type { ModuleCapability } from "../../api/client";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const CFG: CatalogConfig = {
  title: "Giấy",
  prefix: "/api/giay",
  columns: [{ key: "ghi_chu", label: "Ghi chú" }],
  fields: [{ key: "ghi_chu", label: "Ghi chú", type: "text" }],
};

/** Bảng quyền: chỉ khai đúng những `can_*` mà màn danh mục hỏi tới. */
function quyen(mod: string, cho: Partial<ModuleCapability>): ModuleCapability {
  return {
    module_key: mod, scope: "all",
    can_read: true, can_create: false, can_update: false, can_delete: false,
    ...cho,
  } as ModuleCapability;
}

function moMan(config: CatalogConfig, caps: ModuleCapability[] = [], navigate?: NavigateFn) {
  return render(
    <AuthContext.Provider value={AUTH}>
      <PermissionsProvider caps={buildCapabilities(caps)}>
        <CatalogListPage config={config} navigate={navigate} />
      </PermissionsProvider>
    </AuthContext.Provider>,
  );
}

/** Danh sách trả về `items`; `hong` thì trả 500 để ép nhánh lỗi. */
function stub({ items = [] as unknown[], hong = false } = {}) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(
    hong
      ? new Response(JSON.stringify({ detail: "Mất kết nối cơ sở dữ liệu." }), { status: 500 })
      : new Response(JSON.stringify({ items, total: items.length, page: 1, size: 20 }),
        { status: 200, headers: { "Content-Type": "application/json" } }),
  )));
}

describe("bảng rỗng phải nói ĐÚNG lý do", () => {
  it("tải hỏng thì nói không tải được + mời Tải lại, KHÔNG nói 'chưa có gì'", async () => {
    stub({ hong: true });
    moMan(CFG);

    await screen.findByText("Không tải được danh sách.");
    expect(screen.queryByText(/Chưa có giấy nào/)).toBeNull();
    expect(screen.getByText("Mất kết nối cơ sở dữ liệu.")).toBeTruthy();   // lý do máy chủ trả về
    expect(screen.getByRole("button", { name: "Tải lại" })).toBeTruthy();
    // Một lỗi = MỘT nút Tải lại. Banner trên đầu bảng phải im khi bảng đã rỗng.
    expect(screen.getAllByRole("button", { name: "Tải lại" })).toHaveLength(1);
  });

  it("không hỏng, không lọc, không có dòng nào ⇒ vẫn là câu 'chưa có gì'", async () => {
    stub({ items: [] });
    moMan(CFG);
    await screen.findByText(/Chưa có giấy nào trong hệ thống/);
  });
});

describe("nút GHI gác theo quyền module", () => {
  const CFG_GAC: CatalogConfig = { ...CFG, moduleQuyen: "dm_giay", softDelete: true };
  const DONG = [{ id: 1, ma: "G-001", ten: "Couché 150" }];

  it("vai chỉ-đọc KHÔNG thấy Thêm lẫn Xóa", async () => {
    stub({ items: DONG });
    moMan(CFG_GAC, [quyen("dm_giay", {})]);

    await screen.findByText("G-001");
    expect(screen.queryByRole("button", { name: /Thêm giấy/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Xóa/ })).toBeNull();
  });

  it("đủ quyền thì hai nút hiện lại như cũ", async () => {
    stub({ items: DONG });
    moMan(CFG_GAC, [quyen("dm_giay", { can_create: true, can_delete: true })]);

    await screen.findByText("G-001");
    expect(screen.getByRole("button", { name: /Thêm giấy/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Xóa/ })).toBeTruthy();
  });

  it("config KHÔNG khai `moduleQuyen` ⇒ không gác gì, giữ nguyên hành vi cũ", async () => {
    stub({ items: DONG });
    moMan(CFG);   // không có provider quyền nào cấp `dm_giay`

    await screen.findByText("G-001");
    expect(screen.getByRole("button", { name: /Thêm giấy/ })).toBeTruthy();
  });
});

describe("danh mục do HỆ SINH — `khongTaoTay` / `khongXoa`", () => {
  // Màn Thành phẩm (mg 0203 · docs/prd-thanh-pham.md L5): dòng ở đó do `OrderService.confirm()`
  // khai từ dòng đơn, mã theo công thức. Cho gõ tay là mở lại đúng cái cửa mà luật 08/08/2026
  // của kho đã đóng.
  const CFG_SINH: CatalogConfig = {
    ...CFG, moduleQuyen: "dm_giay", softDelete: true, khongTaoTay: true, khongXoa: true,
  };
  const DONG = [{ id: 1, ma: "TP-DH-2026-041-11", ten: "Hộp thuốc 10 vỉ" }];

  it("⭐ ĐỦ QUYỀN vẫn KHÔNG thấy Thêm lẫn Xóa", async () => {
    // Đây là chỗ khác hẳn khối trên: khối kia gác theo QUYỀN, khối này là luật CỦA MÀN — có
    // quyền tạo cũng không tạo tay được.
    stub({ items: DONG });
    moMan(CFG_SINH, [quyen("dm_giay", { can_create: true, can_delete: true, can_update: true })]);

    await screen.findByText("TP-DH-2026-041-11");
    expect(screen.queryByRole("button", { name: /Thêm giấy/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Xóa/ })).toBeNull();
  });

  it("vẫn SỬA được — chỉ chặn tạo và xoá", async () => {
    // Chặn quá tay thì không ai sửa nổi ĐVT, mà ĐVT chính là ô kho phải sửa được (PRD L5).
    // Sửa ở màn này là BẤM VÀO DÒNG, không có nút riêng.
    stub({ items: DONG });
    moMan(CFG_SINH, [quyen("dm_giay", { can_create: true, can_delete: true, can_update: true })]);

    await userEvent.click(await screen.findByText("TP-DH-2026-041-11"));
    expect(await screen.findByText(/Chỉnh sửa/)).toBeInTheDocument();
  });

  it("⭐ vẫn NHẬP EXCEL được chỉ với quyền sửa — file chỉ còn sửa dòng đã có", async () => {
    // Thành phẩm 18/09/2026: bỏ nút Thêm nhưng giữ Nhập Excel để sửa hàng loạt. Gác theo `create`
    // như màn thường thì cờ này giấu luôn Nhập Excel, mà `create` ở đây đâu còn nghĩa gì.
    stub({ items: DONG });
    moMan({ ...CFG_SINH, enableImport: true }, [quyen("dm_giay", { can_update: true })]);

    await screen.findByText("TP-DH-2026-041-11");
    expect(screen.queryByRole("button", { name: /Thêm giấy/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Nhập Excel/ })).toBeTruthy();
  });

  it("không khai hai cờ ⇒ giữ nguyên hành vi cũ", async () => {
    stub({ items: DONG });
    moMan({ ...CFG, moduleQuyen: "dm_giay", softDelete: true },
          [quyen("dm_giay", { can_create: true, can_delete: true })]);

    await screen.findByText("TP-DH-2026-041-11");
    expect(screen.getByRole("button", { name: /Thêm giấy/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Xóa/ })).toBeTruthy();
  });
});

describe("mở một dòng bằng BÀN PHÍM", () => {
  it("tên dòng là <button> thật (Enter/Space chạy sẵn), không phải chữ trần trong <tr onClick>", async () => {
    stub({ items: [{ id: 1, ma: "G-001", ten: "Couché 150" }] });
    moMan(CFG);

    await screen.findByText("G-001");
    await waitFor(() => expect(screen.getByRole("button", { name: /^Mở Couché 150/ })).toBeTruthy());
  });
});

describe("bấm link sang MÀN KHÁC từ drawer (vd mã đơn ở Thành phẩm)", () => {
  function NutMoDon() {
    const navigate = useDieuHuongDanhMuc();
    return <button type="button" onClick={() => navigate?.("don-hang-ban", { openOrderId: 5 })}>Mở đơn</button>;
  }
  const CFG_LINK: CatalogConfig = { ...CFG, renderChiDoc: () => <NutMoDon /> };
  const DONG = [{ id: 1, ma: "G-001", ten: "Couché 150", ghi_chu: "" }];

  it("chưa sửa gì ⇒ sang màn kia ngay", async () => {
    const user = userEvent.setup();
    const nav = vi.fn();
    stub({ items: DONG });
    moMan(CFG_LINK, [], nav);

    await user.click(await screen.findByText("G-001"));
    await user.click(await screen.findByRole("button", { name: "Mở đơn" }));
    expect(nav).toHaveBeenCalledWith("don-hang-ban", { openOrderId: 5 });
  });

  it("⭐ đang sửa dở ⇒ hỏi bỏ thay đổi trước, chọn Tiếp tục sửa thì ở lại", async () => {
    // Rời màn là drawer biến mất cùng bản sửa — không qua `roiDi` là mất việc không một lời hỏi.
    const user = userEvent.setup();
    const nav = vi.fn();
    stub({ items: DONG });
    moMan(CFG_LINK, [], nav);

    await user.click(await screen.findByText("G-001"));
    await user.type(await screen.findByDisplayValue("Couché 150"), " mới");
    await user.click(screen.getByRole("button", { name: "Mở đơn" }));
    expect(await screen.findByText("Bỏ thay đổi?")).toBeTruthy();
    expect(nav).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Tiếp tục sửa" }));
    expect(nav).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue("Couché 150 mới")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Mở đơn" }));
    await user.click(await screen.findByRole("button", { name: "Thoát không lưu" }));
    expect(nav).toHaveBeenCalledWith("don-hang-ban", { openOrderId: 5 });
  });
});

describe("Lọc nâng cao (`config.locNangCao`) — lọc ở MÁY CHỦ, ghép với chip", () => {
  const CFG_LOC: CatalogConfig = {
    ...CFG,
    title: "Khuôn",
    prefix: "/api/khuon-be",
    facet: { key: "loai", values: [{ value: "khuon_be", label: "Khuôn bế" }] },
    locNangCao: [{
      key: "tinh_trang", label: "Tình trạng", type: "select",
      options: [{ value: "hong", label: "Hỏng" }],
    }],
  };

  it("màn không khai `locNangCao` ⇒ không mọc nút", async () => {
    stub({ items: [] });
    moMan(CFG);
    await screen.findByText(/Chưa có giấy nào/);
    expect(screen.queryByRole("button", { name: /Lọc nâng cao/ })).toBeNull();
  });

  it("⭐ chọn tiêu chí ⇒ query có tham số đó; gập bảng vẫn lọc và hiện nhãn; ✕ gỡ lọc", async () => {
    stub({ items: [] });
    const u = userEvent.setup();
    moMan(CFG_LOC);
    const fetchMock = vi.mocked(fetch);
    const urls = () => fetchMock.mock.calls.map((c) => String(c[0]));

    await u.click(await screen.findByRole("button", { name: /Lọc nâng cao/ }));
    await u.selectOptions(screen.getByRole("combobox", { name: "Tình trạng" }), "hong");
    await waitFor(() => expect(urls().some((x) => x.includes("tinh_trang=hong"))).toBe(true));
    // Chip loại + lọc nâng cao đi CÙNG một request.
    await u.click(screen.getByRole("button", { name: /Khuôn bế/ }));
    await waitFor(() => expect(urls().some(
      (x) => x.includes("tinh_trang=hong") && x.includes("loai=khuon_be"))).toBe(true));

    // Gập bảng: bộ lọc còn áp, nói thành nhãn.
    await u.click(screen.getByRole("button", { name: /Lọc nâng cao/ }));
    expect(screen.getByText("Hỏng")).toBeTruthy();
    fetchMock.mockClear();
    await u.click(screen.getByRole("button", { name: "Bỏ lọc Tình trạng" }));
    await waitFor(() => expect(urls().some((x) => x.includes("/api/khuon-be?"))).toBe(true));
    expect(urls().some((x) => x.includes("tinh_trang="))).toBe(false);
  });

  it("ô `text` (Số kệ) chờ gõ xong mới hỏi máy chủ, một lần; Xoá bộ lọc thì ô về trống", async () => {
    stub({ items: [] });
    const u = userEvent.setup();
    moMan({ ...CFG_LOC, locNangCao: [{ key: "so_ke", label: "Số kệ", type: "text" }] });
    const fetchMock = vi.mocked(fetch);
    const urls = () => fetchMock.mock.calls.map((c) => String(c[0]));

    await u.click(await screen.findByRole("button", { name: /Lọc nâng cao/ }));
    const o = screen.getByRole("textbox", { name: "Số kệ" });
    await u.type(o, "b3");
    await waitFor(() => expect(urls().some((x) => x.includes("so_ke=b3"))).toBe(true));
    // Gõ từng phím mà không chờ thì "b" lẻ không được đi riêng một lượt.
    expect(urls().some((x) => /so_ke=b(&|$)/.test(x))).toBe(false);

    await u.click(screen.getByRole("button", { name: "Xoá bộ lọc" }));
    await waitFor(() => expect((o as HTMLInputElement).value).toBe(""));
    fetchMock.mockClear();
    await new Promise((r) => setTimeout(r, 400));
    // Ô về trống từ NGOÀI thì không được bắn ngược một lượt `so_ke` nào nữa.
    expect(urls().some((x) => x.includes("so_ke="))).toBe(false);
  });
});
