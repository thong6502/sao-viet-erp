import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { gop } from "../test/baiGhepSoDoFixture";
import { BuocChungForm } from "./BaiGhepBuocChungForm";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));
vi.mock("../api/rebuildCatalog", () => ({
  crud: () => ({ list: vi.fn().mockResolvedValue({ items: [] }) }),
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
});
