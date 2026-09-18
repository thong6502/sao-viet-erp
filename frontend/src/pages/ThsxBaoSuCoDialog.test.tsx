import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ThsxBaoSuCoDialog } from "./ThsxBaoSuCoDialog";

function mo(p: Partial<Parameters<typeof ThsxBaoSuCoDialog>[0]> = {}) {
  const onGui = vi.fn().mockResolvedValue(true);
  const onClose = vi.fn();
  render(
    <ThsxBaoSuCoDialog mayNhan="M6M · Máy 6 màu Mitsubishi 72×102" dangChay busy={false}
      onGui={onGui} onClose={onClose} {...p} />,
  );
  return { onGui, onClose };
}

describe("ThsxBaoSuCoDialog — cùng khuôn ngăn kéo Báo máy hỏng", () => {
  it("dựng đủ các ô của Yêu cầu mới, máy khoá theo công việc", () => {
    mo();
    const dlg = screen.getByRole("dialog", { name: "Báo máy hỏng — Yêu cầu mới" });
    expect(dlg.textContent).toContain("Báo máy hỏng");
    expect(dlg.textContent).toContain("Yêu cầu mới");
    expect(dlg.textContent).toContain("Thông tin báo sự cố máy");
    const may = screen.getByRole("textbox", { name: /Máy \*/ }) as HTMLInputElement;
    expect(may.disabled).toBe(true);
    expect(may.value).toBe("M6M · Máy 6 màu Mitsubishi 72×102");
    // Mức độ là dãy nút bấm, mặc định Trung bình.
    expect(screen.getByRole("button", { name: "Trung bình" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByPlaceholderText("vd: Trục cán & bạc đạn")).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: /Máy đang dừng, không chạy được/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Gửi yêu cầu" })).toBeTruthy();
  });

  it("thiếu bộ phận hỏng thì không gửi và báo ngay dưới ô", () => {
    const { onGui } = mo();
    fireEvent.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
    expect(onGui).not.toHaveBeenCalled();
    expect(screen.getByText("Chưa ghi bộ phận hỏng.")).toBeTruthy();
  });

  it("tick máy dừng thì triệu chứng thành bắt buộc, đủ thì gửi dung_san_xuat=true rồi đóng", async () => {
    const { onGui, onClose } = mo();
    fireEvent.change(screen.getByPlaceholderText("vd: Trục cán & bạc đạn"), { target: { value: " Motor " } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Máy đang dừng/ }));
    expect(screen.getByText(/Công việc sẽ TẠM DỪNG/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
    expect(onGui).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText(/Kể đúng cái mình thấy/), { target: { value: "Kêu to" } });
    fireEvent.click(screen.getByRole("button", { name: "Nghiêm trọng" }));
    expect(screen.getByRole("button", { name: "Nghiêm trọng" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onGui).toHaveBeenCalledWith({
      bo_phan_hong: "Motor", mo_ta: "Kêu to", muc_do: "nghiem_trong", dung_san_xuat: true,
    });
  });

  it("không tick: gửi được khi chưa ghi triệu chứng; lỗi server thì giữ ngăn kéo", async () => {
    const onGui = vi.fn().mockResolvedValue(false);
    const { onClose } = mo({ onGui, dangChay: false });
    fireEvent.change(screen.getByPlaceholderText("vd: Trục cán & bạc đạn"), { target: { value: "Đầu cắn giấy" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
    await waitFor(() => expect(onGui).toHaveBeenCalledWith({
      bo_phan_hong: "Đầu cắn giấy", mo_ta: null, muc_do: "trung_binh", dung_san_xuat: false,
    }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText(/Công việc đang tạm dừng/)).toBeTruthy();
  });
});
