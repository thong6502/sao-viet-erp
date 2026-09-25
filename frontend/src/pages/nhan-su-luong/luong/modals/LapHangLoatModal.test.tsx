import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { LapHangLoatModal } from "./LapHangLoatModal";
import { api, type UngVienTamUngList } from "../../../../api/client";

vi.mock("../../../../api/client", () => ({
  api: {
    luong: {
      periods: vi.fn(),
      ungVienTamUng: vi.fn(),
      createAdvancesBulk: vi.fn(),
    },
  },
}));

const mockCandidates: UngVienTamUngList = {
  nguong: 10,
  den_ngay: 25,
  items: [
    {
      employee_id: 1,
      code: "NV001",
      name: "Nguyễn Văn A",
      department_id: 1,
      cong: 12,
      du_dieu_kien: true,
      so_tien_goi_y: 2000000,
      so_phieu_da_co: 0,
    },
    {
      employee_id: 2,
      code: "NV002",
      name: "Trần Thị B",
      department_id: 1,
      cong: 8,
      du_dieu_kien: false,
      so_tien_goi_y: 1500000,
      so_phieu_da_co: 0,
    },
    {
      employee_id: 3,
      code: "NV003",
      name: "Lê Văn C",
      department_id: 2,
      cong: 11,
      du_dieu_kien: true,
      so_tien_goi_y: 3000000,
      so_phieu_da_co: 1,
    },
  ],
};

describe("LapHangLoatModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.luong.periods).mockResolvedValue({
      items: [
        {
          id: 1,
          year: 2026,
          month: 9,
          status: "draft",
          standard_cong: 26,
          locked_at: null,
          paid_at: null,
          paid_by: null,
        },
      ],
    });
    vi.mocked(api.luong.ungVienTamUng).mockResolvedValue(mockCandidates);
    vi.mocked(api.luong.createAdvancesBulk).mockResolvedValue({
      items: [{ id: 10, employee_id: 1, amount: 2000000 } as any],
    });
  });

  it("renders header with period badge, KPI ribbon, and candidate table", async () => {
    render(
      <LapHangLoatModal
        token="test-token"
        year={2026}
        month={9}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    );

    // Header title and period badge
    expect(await screen.findByText("Lập phiếu lương đợt 1")).toBeInTheDocument();
    expect(screen.getByText("Kỳ 09/2026")).toBeInTheDocument();

    // KPI ribbon and filter tabs
    expect(screen.getByText("Ngưỡng công")).toBeInTheDocument();
    expect(screen.getAllByText(/Đủ điều kiện/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText((content, element) => element?.tagName.toLowerCase() === "span" && content.includes("/ 3 người"))).toBeInTheDocument();

    // Candidates in table
    expect(screen.getByText("Nguyễn Văn A")).toBeInTheDocument();
    expect(screen.getByText("Trần Thị B")).toBeInTheDocument();
    expect(screen.getByText("Lê Văn C")).toBeInTheDocument();
  });

  it("filters candidates using filter tabs and search input", async () => {
    render(
      <LapHangLoatModal
        token="test-token"
        year={2026}
        month={9}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    );

    await screen.findByText("Nguyễn Văn A");

    // Click "Chưa đủ công" tab
    const chuaDuTab = screen.getByRole("button", { name: /Chưa đủ công/i });
    fireEvent.click(chuaDuTab);

    // Only Trần Thị B should be visible
    expect(screen.queryByText("Nguyễn Văn A")).not.toBeInTheDocument();
    expect(screen.getByText("Trần Thị B")).toBeInTheDocument();

    // Click "Đủ điều kiện" tab
    const duDkTab = screen.getByRole("button", { name: /^Đủ điều kiện/i });
    fireEvent.click(duDkTab);
    expect(screen.getByText("Nguyễn Văn A")).toBeInTheDocument();
    expect(screen.getByText("Lê Văn C")).toBeInTheDocument();
    expect(screen.queryByText("Trần Thị B")).not.toBeInTheDocument();

    // Search by name
    const searchInput = screen.getByPlaceholderText(/Tìm tên, mã nhân viên/i);
    fireEvent.change(searchInput, { target: { value: "NV001" } });
    expect(screen.getByText("Nguyễn Văn A")).toBeInTheDocument();
    expect(screen.queryByText("Lê Văn C")).not.toBeInTheDocument();
  });

  it("allows selecting candidates and submits bulk advances", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(
      <LapHangLoatModal
        token="test-token"
        year={2026}
        month={9}
        onClose={vi.fn()}
        onSaved={onSaved}
      />
    );

    await screen.findByText("Nguyễn Văn A");

    // Click "Chọn đủ ĐK (1)" button to select eligible candidates without prior slips
    const quickSelectBtn = screen.getByRole("button", { name: /Chọn đủ ĐK/i });
    fireEvent.click(quickSelectBtn);

    // Submit button should be enabled and display count
    const submitBtn = screen.getByRole("button", { name: /Lập 1 phiếu/i });
    expect(submitBtn).not.toBeDisabled();

    await user.click(submitBtn);

    expect(api.luong.createAdvancesBulk).toHaveBeenCalledWith(
      "test-token",
      expect.objectContaining({
        period_year: 2026,
        period_month: 9,
        kind: "luong_dot_1",
        items: [{ employee_id: 1, amount: 2000000 }],
      })
    );
    expect(onSaved).toHaveBeenCalledWith(1);
  });

  it("supports mode switching and quick presets in Tạm ứng mode", async () => {
    render(
      <LapHangLoatModal
        token="test-token"
        year={2026}
        month={9}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    );

    await screen.findByText("Nguyễn Văn A");

    // Switch to Tạm ứng mode
    const tamUngTab = screen.getByRole("radio", { name: /Tạm ứng/i });
    fireEvent.click(tamUngTab);

    // Title should update
    expect(screen.getByText("Lập phiếu tạm ứng lương")).toBeInTheDocument();

    // Check presets are rendered
    expect(screen.getByRole("button", { name: "1tr" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2tr" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3tr" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5tr" })).toBeInTheDocument();
  });
});
