// Ba thứ của đợt "một khung cho 10 màn" mà HỎNG TRONG IM LẶNG — không có test thì phải mở đúng
// màn, đúng vai, đúng lúc backend chết mới thấy:
//
//   1. Bảng NÓI DỐI. Trước 15/08/2026 backend chết là ô trống vẫn in "Chưa có giấy nào trong hệ
//      thống." — câu đó vừa sai vừa mời người ta đi tạo lại dữ liệu đang có sẵn.
//   2. Vai chỉ-đọc vẫn thấy đủ nút Thêm / Xóa, bấm xong mới ăn 403.
//   3. Header rẽ hai nhánh theo `subtitle` (một trường NỘI DUNG quyết định BỐ CỤC) nên hai màn bỏ
//      trống nó trông như sản phẩm của app khác.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CatalogListPage } from "./CatalogListPage";
import type { CatalogConfig } from "./types";
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

function moMan(config: CatalogConfig, caps: ModuleCapability[] = []) {
  return render(
    <AuthContext.Provider value={AUTH}>
      <PermissionsProvider caps={buildCapabilities(caps)}>
        <CatalogListPage config={config} />
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

  it("không khai hai cờ ⇒ giữ nguyên hành vi cũ", async () => {
    stub({ items: DONG });
    moMan({ ...CFG, moduleQuyen: "dm_giay", softDelete: true },
          [quyen("dm_giay", { can_create: true, can_delete: true })]);

    await screen.findByText("TP-DH-2026-041-11");
    expect(screen.getByRole("button", { name: /Thêm giấy/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Xóa/ })).toBeTruthy();
  });
});

describe("header MỘT dạng — `subtitle` chỉ là nội dung, không phải bố cục", () => {
  it("không có subtitle thì KHÔNG đẻ thẻ <p> rỗng, số đếm vẫn hiện", async () => {
    stub({ items: [{ id: 1, ma: "G-001", ten: "Couché 150" }] });
    const { container } = moMan(CFG);

    await screen.findByText("G-001");
    expect(screen.getByText("1 mục")).toBeTruthy();
    expect(container.querySelector(".rc__sub")).toBeNull();
  });

  it("có subtitle thì thêm ĐÚNG một dòng, phần còn lại của header y hệt", async () => {
    stub({ items: [{ id: 1, ma: "G-001", ten: "Couché 150" }] });
    const { container } = moMan({ ...CFG, subtitle: "Từng loại giấy cụ thể." });

    await screen.findByText("G-001");
    expect(screen.getByText("1 mục")).toBeTruthy();
    expect(container.querySelectorAll(".rc__sub")).toHaveLength(1);
    // Thanh gộp cũ (`rc__unified-bar`) đã bỏ — chỉ còn MỘT khung header cho cả 10 màn.
    expect(container.querySelector(".rc__unified-bar")).toBeNull();
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
