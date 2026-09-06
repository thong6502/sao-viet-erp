import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MayCuaCongDoanField } from "./MayCuaCongDoan";
import { AuthContext, type AuthState } from "../../../auth/AuthContext";

// `token: null` ⇒ `useBienCongThuc` bên trong `FormulaField` KHÔNG gọi API (từ điển rỗng, chip
// hiện mã thay nhãn). Đúng mẫu `frontend/src/pages/FormulaField.test.tsx:20-26`.
const AUTH: AuthState = {
  status: "anonymous", user: null, token: null,
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const MAY = [
  { id: 1, ma: "MAY-01", ten: "Komori 5 màu", loai_may: "Máy in" },
  { id: 2, ma: "MAY-02", ten: "Yawa 1050", loai_may: "Bế" },
];

function bay(props: Parameters<typeof MayCuaCongDoanField>[0]) {
  return render(
    <AuthContext.Provider value={AUTH}><MayCuaCongDoanField {...props} /></AuthContext.Provider>,
  );
}

describe("MayCuaCongDoanField", () => {
  it("chỉ bày máy thuộc nhóm đã tick", () => {
    bay({ value: [], options: MAY, nhomChoPhep: ["Máy in"], nhomCongDoan: "print",
          onChange: () => {} });
    expect(screen.getByText(/Komori 5 màu/)).toBeInTheDocument();
    expect(screen.queryByText(/Yawa 1050/)).not.toBeInTheDocument();
  });

  it("bấm dòng máy thì bung panel hai ô công thức", async () => {
    const user = userEvent.setup();
    bay({ value: [{ may_id: 1 }], options: MAY, nhomChoPhep: ["Máy in"], nhomCongDoan: "print",
          onChange: () => {} });
    await user.click(screen.getByRole("button", { name: /Komori 5 màu/ }));
    // `nhanO` render ra `<span className="rc-formula__editor-label">`, KHÔNG phải `<label for>`
    // ⇒ dùng `getByText`, `getByLabelText` sẽ không thấy.
    expect(screen.getByText("Công thức giờ chạy")).toBeInTheDocument();
    expect(screen.getByText("Công thức giá")).toBeInTheDocument();
  });

  it("công đoạn KHÔNG thuộc nhóm In thì không có ô công thức giá", async () => {
    const user = userEvent.setup();
    bay({ value: [{ may_id: 2 }], options: MAY, nhomChoPhep: ["Bế"], nhomCongDoan: "finishing",
          onChange: () => {} });
    await user.click(screen.getByRole("button", { name: /Yawa 1050/ }));
    expect(screen.getByText("Công thức giờ chạy")).toBeInTheDocument();
    expect(screen.queryByText("Công thức giá")).not.toBeInTheDocument();
  });
});
