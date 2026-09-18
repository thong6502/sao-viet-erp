import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { gop } from "../test/baiGhepSoDoFixture";
import { BuocChungForm } from "./BaiGhepBuocChungForm";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));
// Danh mục nạp qua `crud(prefix).list` — chỉ ô TỔ cần dữ liệu thật, các prefix khác trả rỗng.
vi.mock("../api/rebuildCatalog", () => ({
  crud: (prefix: string) => ({
    list: vi.fn().mockResolvedValue({
      items: prefix === "/api/cong-doan/phong-ban"
        ? [
            { id: 3, ten: "Tổ in" },
            { id: 5, ten: "Tổ cán phủ" },
            { id: 7, ten: "Tổ bế" },
            { id: 9, ten: "Tổ dán" },
          ]
        : [],
    }),
  }),
}));

describe("form kế hoạch bước chung", () => {
  it("server từ chối thì giữ nguyên draft và form vẫn mở", async () => {
    const user = userEvent.setup();
    const onLuu = vi.fn().mockResolvedValue(false);
    render(<BuocChungForm g={gop({
      step_key: "gang-in",
      ten: "In chung",
      thanh_vien: [
        { lsx_id: 1, lsx_ma: "LSX-1", lsx_step_key: "lsx-1-in", ghi_chu_ky_thuat: null },
        { lsx_id: 2, lsx_ma: "LSX-2", lsx_step_key: "lsx-2-in", ghi_chu_ky_thuat: null },
      ],
    })} canUpdate onLuu={onLuu} onTach={async () => {}} />);

    // Ghi chú của bài nằm ở tab cuối (cùng chỗ với ghi chú kỹ thuật của từng lệnh trên tờ).
    await user.click(screen.getByRole("button", { name: /Các lệnh trên tờ/ }));
    const note = screen.getByLabelText("Ghi chú của bài cho lượt chạy này");
    await user.clear(note);
    await user.type(note, "Giữ nội dung đang khai");
    await user.click(screen.getByRole("button", { name: "Lưu kế hoạch lượt chung" }));

    expect(onLuu).toHaveBeenCalledWith(expect.objectContaining({ ghi_chu: "Giữ nội dung đang khai" }));
    expect(note).toHaveValue("Giữ nội dung đang khai");
    expect(screen.getByRole("button", { name: "Lưu kế hoạch lượt chung" })).toBeInTheDocument();
  });

  // Nhiều tổ phụ trách (18/09/2026): ô TỔ của lượt chung chỉ mời các tổ khai ở danh mục Công đoạn.
  it("ô Tổ phụ trách chỉ mời các tổ phụ trách công đoạn, giữ cả tổ đang gán lệch", async () => {
    render(<BuocChungForm g={gop({
      step_key: "gang-can",
      ten: "Cán màng chung",
      to_chon_duoc: [5, 7],
      department_id: 9,
      to_ten: "Tổ dán",
      thanh_vien: [{ lsx_id: 1, lsx_ma: "LSX-1", lsx_step_key: "lsx-1-can", ghi_chu_ky_thuat: null }],
    })} canUpdate onLuu={async () => true} onTach={async () => {}} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /Phân công & Thiết bị/ }));
    const sel = await screen.findByLabelText(/TỔ PHỤ TRÁCH/);
    expect([...(sel as HTMLSelectElement).options].map((o) => o.text)).toEqual([
      "— chọn tổ —", "Tổ cán phủ", "Tổ bế", "Tổ dán (không còn phụ trách công đoạn)",
    ]);
    expect((sel as HTMLSelectElement).value).toBe("9");
    expect(screen.getByText(/Chỉ các tổ phụ trách khai ở danh mục Công đoạn/)).toBeInTheDocument();
  });

  it("công đoạn chưa khai tổ thì mời mọi tổ, không có câu giới hạn", async () => {
    render(<BuocChungForm g={gop({
      step_key: "gang-in-2",
      ten: "In chung",
      to_chon_duoc: [],
      thanh_vien: [{ lsx_id: 1, lsx_ma: "LSX-1", lsx_step_key: "lsx-1-in", ghi_chu_ky_thuat: null }],
    })} canUpdate onLuu={async () => true} onTach={async () => {}} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /Phân công & Thiết bị/ }));
    const sel = await screen.findByLabelText(/TỔ PHỤ TRÁCH/);
    expect([...(sel as HTMLSelectElement).options].map((o) => o.text)).toEqual([
      "— chọn tổ —", "Tổ in", "Tổ cán phủ", "Tổ bế", "Tổ dán",
    ]);
    expect(screen.queryByText(/Chỉ các tổ phụ trách khai ở danh mục Công đoạn/)).toBeNull();
  });
});
