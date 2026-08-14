// Bằng chứng cho ĐÚNG cú bấm đã làm trắng màn 14/08/2026: drawer Đơn vị → tab "Quy đổi & số lượng"
// → khối "THÊM QUY ĐỔI MỚI" → nút "Theo quy cách".
//
// Cú bấm đó bật `them.dong` ⇒ khối này render `FormulaField`. `FormulaField` vừa bị đổi sang ô chip
// inline và bản đổi bỏ mất ba hàm JSX vẫn gọi ⇒ ReferenceError NGAY TRONG RENDER ⇒ React gỡ cả cây
// ⇒ trắng bong. Lỗi nổ ở `FormulaField` nhưng người dùng gặp nó Ở ĐÂY, nên khoá lại từ đây.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QuyDoiCuaDonVi } from "./QuyDoiCuaDonVi";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import type { Row } from "../api/rebuildCatalog";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const BIEN = [
  { ma: "dinh_luong", nhan: "Định lượng giấy" },
  { ma: "dai_in", nhan: "Dài tờ in" },
  { ma: "rong_in", nhan: "Rộng tờ in" },
];

/** Đơn vị "bài in" chưa khai quy đổi nào — đúng trạng thái trên ảnh chụp màn hình lỗi. */
const BAI_IN: Row = { id: 7, ma: "bai_in", ten: "bài in", ho: "khac", active: true };

function ketQua(path: string): unknown {
  if (path.startsWith("/api/don-vi/quy-doi")) return { items: [], total: 0, page: 1, size: 200 };
  if (path.startsWith("/api/don-vi/bien")) return { items: BIEN };
  if (path.startsWith("/api/don-vi")) return { items: [BAI_IN], total: 1, page: 1, size: 200 };
  if (path.startsWith("/api/bien-cong-thuc")) {
    return { items: BIEN.map((b) => ({ ...b, mo_ta: b.nhan, don_vi: "", nguon: "", loai: ["quy_doi"] })) };
  }
  return { items: [] };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const path = String(url).replace("http://localhost:8000", "");
    return Promise.resolve(new Response(JSON.stringify(ketQua(path)), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
  }));
});

describe("drawer Đơn vị → Quy đổi & số lượng", () => {
  it("bấm nút “Theo quy cách” KHÔNG làm trắng màn — ô soạn công thức hiện ra", async () => {
    const user = userEvent.setup();
    render(
      <AuthContext.Provider value={AUTH}>
        <QuyDoiCuaDonVi donVi={BAI_IN} />
      </AuthContext.Provider>,
    );

    await screen.findByText("Chưa có quy đổi nào được khai báo cho đơn vị này.");
    await user.click(screen.getByRole("button", { name: "Theo quy cách" }));

    // Khối vẫn còn sống: ô soạn công thức thế chỗ ô số + ô đích (công thức định nghĩa chính đơn vị
    // đang mở nên KHÔNG có "quy đổi về").
    await waitFor(() => expect(document.getElementById("ct-them")).toBeInTheDocument());
    expect(screen.getByText("Danh sách biến khả dụng")).toBeInTheDocument();
    expect(screen.queryByText("— Đơn vị quy đổi về —")).not.toBeInTheDocument();
  });

  it("soạn xong công thức thì nút Thêm quy đổi mở khoá", async () => {
    const user = userEvent.setup();
    render(
      <AuthContext.Provider value={AUTH}>
        <QuyDoiCuaDonVi donVi={BAI_IN} />
      </AuthContext.Provider>,
    );

    await screen.findByText("Chưa có quy đổi nào được khai báo cho đơn vị này.");
    await user.click(screen.getByRole("button", { name: "Theo quy cách" }));

    const nut = screen.getByRole("button", { name: /Thêm quy đổi/ });
    expect(nut).toBeDisabled();
    // Nút khoá thì phải NÓI THIẾU GÌ, không thì người dùng bấm mãi rồi tưởng hỏng.
    expect(screen.getByText(/Nhập hoặc bấm chọn biến/)).toBeInTheDocument();

    await user.type(document.getElementById("ct-them")!, "dai_in");
    await waitFor(() => expect(nut).toBeEnabled());
  });
});
