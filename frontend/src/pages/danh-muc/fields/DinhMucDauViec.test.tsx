import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DinhMucDauViecField } from "./DinhMucDauViec";
import { AuthContext, type AuthState } from "../../../auth/AuthContext";

// Component tự nạp danh mục vật tư khi mount — chặn lại để test không đụng mạng.
vi.mock("../../../api/rebuildCatalog", () => ({
  crud: () => ({ list: async () => ({ items: [] }) }),
}));

// `token: null` ⇒ `useBienCongThuc` trong `FormulaField` không gọi API.
const AUTH: AuthState = {
  status: "anonymous", user: null, token: null,
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const OPT = [{ id: 1, ma: "KH-0002", ten: "In offset", department_id: 5, don_vi_ten: "tờ" }];
const ROW = [{ piece_rate_id: 1, nang_suat_nguoi_gio: 6000, so_nguoi_tieu_chuan: 2, vat_tus: [] }];

function bay(value = ROW) {
  return render(
    <AuthContext.Provider value={AUTH}>
      <DinhMucDauViecField value={value} options={OPT} departmentId={5} donViVao="to"
        onChange={() => {}} />
    </AuthContext.Provider>,
  );
}

describe("DinhMucDauViecField — công thức tiền công", () => {
  it("bấm tên đầu việc thì bung ô công thức tính tiền công", async () => {
    const user = userEvent.setup();
    bay();
    await user.click(screen.getByRole("button", { name: /In offset/ }));
    // `nhanO` render ra `<span>`, không phải `<label for>` ⇒ `getByText`.
    expect(screen.getByText("Công thức tính tiền công")).toBeInTheDocument();
  });
});
