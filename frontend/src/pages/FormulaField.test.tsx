// Bằng chứng THẬT cho ô soạn công thức (`FormulaField`) — khoá lại vụ TRẮNG MÀN 14/08/2026.
//
// Ô này vừa đổi từ `textarea` sang "ô chip inline". Bản đổi bỏ ba hàm mà JSX vẫn gọi
// (`handleRemoveToken`, `handleInlineBlur`, `insertVar`) ⇒ ReferenceError NGAY LÚC RENDER ⇒ React
// gỡ cả cây ⇒ bấm "Công thức" ở drawer Đơn vị là trắng bong. Vite dev dùng esbuild, KHÔNG
// type-check, nên lỗi này lọt tới tận trình duyệt.
//
// Vì thế test ở đây phải RENDER và BẤM thật, không grep chuỗi: chỉ cần một identifier trong JSX
// mất chỗ dựa là cả bộ này đỏ.
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FormulaField } from "./RebuildCatalogPage";
import { AuthContext, type AuthState } from "../auth/AuthContext";

// Token null ⇒ `useBienCongThuc` không gọi API (từ điển rỗng, chip hiện MÃ thay nhãn). Whitelist
// đã truyền thẳng qua `bienGoiY` — đúng cách màn Đơn vị & quy đổi đang dùng.
const AUTH: AuthState = {
  status: "anonymous", user: null, token: null,
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const BIEN = ["dinh_luong", "dai_in", "rong_in", "so_mau", "so_mau_pha"];

/** Cha giữ `value` — đúng như drawer thật, để thấy chuỗi công thức thay đổi ra sao. */
function Harness({ dau = "", bien = BIEN }: { dau?: string; bien?: string[] }) {
  const [v, setV] = useState(dau);
  return (
    <AuthContext.Provider value={AUTH}>
      <FormulaField id="ct-test" value={v} onChange={setV} configPrefix="/api/don-vi" bienGoiY={bien} />
      <output data-testid="ct">{v}</output>
    </AuthContext.Provider>
  );
}

const ct = () => screen.getByTestId("ct").textContent;
const o = () => screen.getByRole("textbox") as HTMLInputElement;

describe("ô soạn công thức không được trắng màn", () => {
  it("render được với công thức có sẵn — chip + ô gõ đều có mặt", () => {
    render(<Harness dau="dinh_luong * dai_in" />);
    expect(o()).toBeInTheDocument();
    expect(screen.getByTitle("Xoá biến dinh_luong")).toBeInTheDocument();
  });

  it("render được khi công thức TRỐNG — đây chính là lúc bấm nút “Công thức” ở drawer Đơn vị", () => {
    render(<Harness />);
    expect(o()).toBeInTheDocument();
    expect(ct()).toBe("");
  });
});

describe("thao tác trên ô công thức", () => {
  it("bấm chip biến rồi bấm toán tử → công thức nối thêm (insertVar)", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong" />);
    await user.click(screen.getByTitle("Nhân"));
    expect(ct()).toBe("dinh_luong * ");
  });

  it("bấm × trên chip → đúng token đó biến mất, phần còn lại giữ nguyên (handleRemoveToken)", async () => {
    const user = userEvent.setup();
    render(<Harness dau="dinh_luong * dai_in" />);
    await user.click(screen.getByTitle("Xoá biến dinh_luong"));
    expect(ct()).toBe("* dai_in");
  });

  it("gõ số rồi rời ô → số được chốt vào công thức chứ không bay mất (handleInlineBlur)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "1000");
    expect(ct()).toBe("");        // còn nằm trong ô gõ, chưa vào công thức
    await user.tab();
    expect(ct()).toBe("1000 ");
  });

  it("gõ đúng tên biến → tự hoá chip ngay", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "dai_in");
    expect(ct()).toBe("dai_in ");
    expect(o().value).toBe("");
  });

  it("KHÔNG chốt sớm khi còn mã dài hơn: gõ hết “so_mau_pha” phải ra so_mau_pha", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "so_mau");
    expect(ct()).toBe("");        // `so_mau_pha` còn đó ⇒ chưa được chốt
    await user.type(o(), "_pha");
    expect(ct()).toBe("so_mau_pha ");
  });

  it("chọn gợi ý bằng chuột không sinh chip đôi (blur không cướp mất cú bấm)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(o(), "dinh");
    await user.click(screen.getByRole("listbox").querySelector(".rc-formula__autocomplete-item")!);
    expect(ct()).toBe("dinh_luong ");
  });
});
