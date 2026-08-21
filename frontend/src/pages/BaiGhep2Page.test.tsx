import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConInput } from "./BaiGhep2Page";

describe("quy cách thành viên Bài ghép 2", () => {
  it("cho lưu 0 con/tờ để biểu diễn chưa cấu hình", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    render(<ConInput value={2} disabled={false} onSave={save} />);

    const input = screen.getByRole("spinbutton");
    expect(input).toHaveAttribute("min", "0");
    await userEvent.clear(input);
    await userEvent.type(input, "0");
    await userEvent.tab();

    expect(save).toHaveBeenCalledWith(0);
  });
});
