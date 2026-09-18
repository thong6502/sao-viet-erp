import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";
import { NganChiTietLoi } from "../pages/ThucHienSxPage";

// Biến ngoài để "sửa" khối con giữa chừng — giống lỗi chỉ xảy ra một lúc (nạp nóng mã, dữ liệu dở).
let hong = true;
// jsdom in lại lỗi React ném lại qua sự kiện `error` của window — chặn để log test gọn.
const nuotLoi = (e: ErrorEvent) => e.preventDefault();
function KhoiCon() {
  if (hong) throw new Error("kcsCoLoiChoXem is not defined");
  return <p>Nội dung ngăn chi tiết</p>;
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    hong = true;
    // React + ranh giới đều in lỗi ra console — đúng ý, nhưng im đi cho log test gọn.
    vi.spyOn(console, "error").mockImplementation(() => {});
    window.addEventListener("error", nuotLoi);
  });
  afterEach(() => {
    window.removeEventListener("error", nuotLoi);
    vi.restoreAllMocks();
  });

  it("khối con vẽ hỏng → chỉ khối đó thay bằng báo lỗi, phần còn lại của màn đứng nguyên", () => {
    const dong = vi.fn();
    render(
      <div>
        <p>Bảng việc</p>
        <ErrorBoundary fallback={(thuLai) => <NganChiTietLoi onThuLai={thuLai} onClose={dong} />}>
          <KhoiCon />
        </ErrorBoundary>
      </div>,
    );
    expect(screen.getByText("Bảng việc")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Không hiển thị được chi tiết công việc này");
    // Không lộ câu lỗi kỹ thuật ra giao diện.
    expect(screen.queryByText(/is not defined/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
    expect(dong).toHaveBeenCalledTimes(1);
  });

  it("Thử lại → vẽ lại khối con; hết lỗi thì ngăn chi tiết trở lại", () => {
    render(
      <ErrorBoundary fallback={(thuLai) => <NganChiTietLoi onThuLai={thuLai} onClose={() => {}} />}>
        <KhoiCon />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();

    hong = false;
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(screen.getByText("Nội dung ngăn chi tiết")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("đổi key (chọn việc khác) → xoá trạng thái lỗi", () => {
    const ve = (k: string) => (
      <ErrorBoundary key={k} fallback={() => <p>Lỗi</p>}>
        <KhoiCon />
      </ErrorBoundary>
    );
    const { rerender } = render(ve("1:0"));
    expect(screen.getByText("Lỗi")).toBeTruthy();

    hong = false;
    rerender(ve("2:0"));
    expect(screen.getByText("Nội dung ngăn chi tiết")).toBeTruthy();
  });
});
