import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BandsField } from "./Bands";
import type { BacRow } from "../types";

// Bậc bù hao nay nằm TRÊN công đoạn và chỉ khai MỐC TRÊN (22/09/2026). Cận dưới suy từ bậc liền
// trước nên không còn ô "Từ SL" — đó là cách duy nhất chặn khoảng hở/khoảng chồng ngay ở ô nhập.
const BA_BAC: BacRow[] = [
  { sl_den: 3000, gia_tri: 150, don_vi: "to" },
  { sl_den: 10000, gia_tri: 3, don_vi: "pct" },
  { sl_den: null, gia_tri: 2, don_vi: "pct" },
];

describe("BandsField", () => {
  it("không còn cột 'Từ SL'", () => {
    render(<BandsField value={BA_BAC} onChange={() => {}} />);
    expect(screen.queryByRole("columnheader", { name: "Từ SL" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Khoảng số lượng" })).toBeInTheDocument();
  });

  it("nhãn khoảng nối từ mốc của bậc liền trước", () => {
    render(<BandsField value={BA_BAC} onChange={() => {}} />);
    expect(screen.getByText("Đến")).toBeInTheDocument();
    expect(screen.getByText("Trên 3.000 đến")).toBeInTheDocument();
    expect(screen.getByText("Trên 10.000")).toBeInTheDocument();
  });

  it("bậc vô hạn không có ô nhập mốc và không xoá được", () => {
    render(<BandsField value={BA_BAC} onChange={() => {}} />);
    // Hai ô mốc = hai bậc hữu hạn; bậc vô hạn chỉ còn chữ.
    expect(screen.getAllByTitle("Mốc trên của bậc")).toHaveLength(2);
    const nutXoa = screen.getAllByTitle("Xóa bậc");
    expect(nutXoa).toHaveLength(2);
  });

  it("'＋ Thêm bậc' chèn TRƯỚC bậc vô hạn", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<BandsField value={BA_BAC} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "＋ Thêm bậc" }));
    const moi = onChange.mock.calls[0][0] as BacRow[];
    expect(moi).toHaveLength(4);
    expect(moi[2].sl_den).toBe(10000);            // bậc mới nằm giữa, chưa khai mốc riêng
    expect(moi[3].sl_den).toBeNull();             // bậc vô hạn vẫn ở cuối
  });

  it("danh sách rỗng thì bậc đầu tiên mở ra là bậc vô hạn", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<BandsField value={[]} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "＋ Thêm bậc" }));
    expect(onChange.mock.calls[0][0]).toEqual([{ sl_den: null, gia_tri: 0, don_vi: "to" }]);
  });

  it("mốc không tăng dần thì đánh dấu hàng sai", () => {
    const { container } = render(
      <BandsField
        value={[{ sl_den: 10000, gia_tri: 1, don_vi: "to" }, { sl_den: 3000, gia_tri: 1, don_vi: "to" },
                { sl_den: null, gia_tri: 1, don_vi: "pct" }]}
        onChange={() => {}}
      />,
    );
    expect(container.querySelectorAll(".rc-bands__row--invalid")).toHaveLength(1);
  });
});
