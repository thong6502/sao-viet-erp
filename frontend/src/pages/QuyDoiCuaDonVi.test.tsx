// Khối "Quy đổi & số lượng" của drawer Đơn vị — nay CHỈ còn quy đổi bằng SỐ.
//
// 🔴 Hai test cũ ở đây khoá cú bấm "Theo quy cách" (đã làm trắng màn 14/08/2026 vì `FormulaField`
// ném ReferenceError trong render). Nút đó GỠ 17/08/2026 cùng cột `don_vi_do.cong_thuc` (mg `0215`):
// câu "một lệnh cần bao nhiêu" không thuộc về ĐƠN VỊ mà thuộc về một MÓN / MÁY / ĐẦU VIỆC / BƯỚC,
// và cả bốn nay có ô riêng. Test đổi theo: khoá lại chính việc nút đó KHÔNG được quay lại, vì màn
// này là chỗ nó từng đứng và người sửa sau dễ "khai lại cho tiện".
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

/** Đơn vị "bài in" chưa khai quy đổi nào. */
const BAI_IN: Row = { id: 7, ma: "bai_in", ten: "bài in", ho: "khac", active: true };
const KG: Row = { id: 8, ma: "kg", ten: "kg", ho: "khoi_luong", active: true };

function ketQua(path: string): unknown {
  if (path.startsWith("/api/don-vi/quy-doi")) return { items: [], total: 0, page: 1, size: 200 };
  if (path.startsWith("/api/don-vi")) return { items: [BAI_IN, KG], total: 2, page: 1, size: 200 };
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
  it("KHÔNG còn chế độ “Theo quy cách” — module này chỉ khai đơn vị + quy đổi", async () => {
    render(
      <AuthContext.Provider value={AUTH}>
        <QuyDoiCuaDonVi donVi={BAI_IN} />
      </AuthContext.Provider>,
    );

    await screen.findByText("Chưa có quy đổi nào được khai báo cho đơn vị này.");
    expect(screen.queryByRole("button", { name: "Theo quy cách" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Số cố định" })).not.toBeInTheDocument();
    // Ô soạn công thức cũng không được còn sót lại dưới bất kỳ hình dạng nào.
    expect(document.getElementById("ct-them")).toBeNull();
    expect(screen.queryByText("Danh sách biến khả dụng")).not.toBeInTheDocument();
  });

  it("khai quy đổi bằng SỐ: nút mở khoá khi đủ số + đơn vị đích", async () => {
    const user = userEvent.setup();
    render(
      <AuthContext.Provider value={AUTH}>
        <QuyDoiCuaDonVi donVi={BAI_IN} />
      </AuthContext.Provider>,
    );

    await screen.findByText("Chưa có quy đổi nào được khai báo cho đơn vị này.");
    const nut = screen.getByRole("button", { name: /Thêm quy đổi/ });
    expect(nut).toBeDisabled();
    // Nút khoá thì phải NÓI THIẾU GÌ, không thì người dùng bấm mãi rồi tưởng hỏng.
    expect(screen.getByText("Nhập số quy đổi đã")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Vd: 1.000"), "65");
    // Có số nhưng chưa chọn đích ⇒ vẫn khoá, và câu nhắc đổi theo.
    expect(nut).toBeDisabled();
    expect(screen.getByText("Còn thiếu: chọn đơn vị quy đổi về")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox"), "8");
    await waitFor(() => expect(nut).toBeEnabled());
  });
});
