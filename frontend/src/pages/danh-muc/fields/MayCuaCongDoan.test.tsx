import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MayCuaCongDoanField } from "./MayCuaCongDoan";
import type { MayCongDoanRow } from "../types";
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
  it("chỉ bày máy thuộc nhóm đã tick", async () => {
    const user = userEvent.setup();
    bay({ value: [], options: MAY, nhomChoPhep: ["Máy in"], nhomCongDoan: "print",
          onChange: () => {} });
    // Máy nay nằm trong ô chọn GÕ-TÌM (`5340acff`), không bày sẵn thành danh sách nữa ⇒ phải mở
    // ô ra mới thấy tên. Danh sách lọc theo nhóm vẫn là thứ đang kiểm.
    await user.click(screen.getByRole("button", { name: "Chọn máy cho công đoạn" }));
    expect(screen.getByText(/Komori 5 màu/)).toBeInTheDocument();
    expect(screen.queryByText(/Yawa 1050/)).not.toBeInTheDocument();
  });

  it("bấm tên máy mở Ô GIỜ, không kéo theo ô giá", async () => {
    const user = userEvent.setup();
    bay({ value: [{ may_id: 1 }], options: MAY, nhomChoPhep: ["Máy in"], nhomCongDoan: "print",
          onChange: () => {} });
    await user.click(screen.getByRole("button", { name: /Komori 5 màu/ }));
    // `nhanO` render ra `<span className="rc-formula__editor-label">`, KHÔNG phải `<label for>`
    // ⇒ dùng `getByText`, `getByLabelText` sẽ không thấy.
    expect(screen.getByText("Công thức giờ chạy")).toBeInTheDocument();
    expect(screen.queryByText("Công thức giá")).not.toBeInTheDocument();
  });

  it("bấm ô giá của DÒNG NÀO thì mở đúng ô giá của dòng ấy", async () => {
    // Bẫy đã gặp trên màn thật: panel khoá theo DÒNG nên bấm ô "Cách tính giá" của dòng 2
    // không có gì xảy ra, panel của dòng 1 vẫn nằm đó — trông hệt như hệ bay ra công thức nhầm dòng.
    const user = userEvent.setup();
    bay({
      value: [{ may_id: 1, cong_thuc_gia: "sl_vao * 420" }, { may_id: 2, cong_thuc_gia: null }],
      options: MAY, nhomChoPhep: [], nhomCongDoan: "print", onChange: () => {},
    });

    await user.click(screen.getAllByTitle("Sửa cách tính giá của máy này")[1]);

    // Soi trên `document`, KHÔNG phải `container`: panel nay là popup nổi treo ở `document.body`
    // qua portal (07/09/2026 — `FormulaPopover`), không còn là hàng phụ trong chính bảng.
    expect(document.querySelector("#ct-gia-2")).not.toBeNull();
    expect(document.querySelector("#ct-gia-1")).toBeNull();
    expect(document.querySelector("#ct-gio-2")).toBeNull();
  });

  it("panel là POPUP nổi ngoài bảng, bấm ra ngoài thì đóng", async () => {
    // Lối cũ chèn hàng phụ vào chính bảng nên bấm ô ở cuối bảng là panel mọc ngoài tầm nhìn —
    // người khai bấm xong không thấy gì đổi. Hai điều kiện của bản popup: nằm NGOÀI cây của bảng,
    // và tự đóng khi bấm chỗ khác.
    const user = userEvent.setup();
    const { container } = bay({
      value: [{ may_id: 1, cong_thuc_gia: "sl_vao * 420" }],
      options: MAY, nhomChoPhep: [], nhomCongDoan: "print", onChange: () => {},
    });

    await user.click(screen.getByTitle("Sửa cách tính giá của máy này"));
    const pop = screen.getByRole("dialog", { name: "Công thức giá" });
    expect(container.contains(pop)).toBe(false);

    await user.click(document.body);
    expect(screen.queryByRole("dialog", { name: "Công thức giá" })).toBeNull();
  });

  it("✕ trả ô về công thức lúc mở, Xong thì giữ nguyên bản vừa sửa", async () => {
    // Ô công thức ghi thẳng vào form theo từng nhịp gõ, nên popup phải tự nhớ bản gốc — không thì
    // lỡ tay sửa một ô đã khai đúng là chỉ còn đường đóng cả drawer, mất luôn mọi thứ khai dở.
    const user = userEvent.setup();
    function Bang() {
      const [v, setV] = useState<MayCongDoanRow[]>([{ may_id: 1, cong_thuc_gia: "sl_vao * 420" }]);
      return <MayCuaCongDoanField value={v} options={MAY} nhomChoPhep={[]}
        nhomCongDoan="print" onChange={setV} />;
    }
    render(<AuthContext.Provider value={AUTH}><Bang /></AuthContext.Provider>);

    const o = () => screen.getByTitle("Sửa cách tính giá của máy này");
    await user.click(o());
    await user.click(screen.getByRole("button", { name: "×" }));
    expect(o().textContent).toBe("sl_vao * 420 *");

    await user.click(screen.getByRole("button", { name: "Bỏ sửa" }));
    expect(o().textContent).toBe("sl_vao * 420");

    await user.click(o());
    await user.click(screen.getByRole("button", { name: "×" }));
    await user.click(screen.getByRole("button", { name: "Xong" }));
    expect(screen.queryByRole("dialog", { name: "Công thức giá" })).toBeNull();
    expect(o().textContent).toBe("sl_vao * 420 *");
  });

  it("công đoạn KHÔNG thuộc nhóm In thì không có ô công thức giá", async () => {
    const user = userEvent.setup();
    bay({ value: [{ may_id: 2 }], options: MAY, nhomChoPhep: ["Bế"], nhomCongDoan: "finishing",
          onChange: () => {} });
    await user.click(screen.getByRole("button", { name: /Yawa 1050/ }));
    expect(screen.getByText("Công thức giờ chạy")).toBeInTheDocument();
    expect(screen.queryByText("Công thức giá")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Sửa cách tính giá của máy này")).not.toBeInTheDocument();
  });
});
