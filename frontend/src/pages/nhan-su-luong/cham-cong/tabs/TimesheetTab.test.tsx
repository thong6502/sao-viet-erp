// Phân trang BẢNG CÔNG THÁNG (11/09/2026).
//
// Vì sao có bài này: DB dev chỉ có 12 nhân viên nên bấm tay không bao giờ chạm tới trang thứ hai,
// mà đúng chỗ dễ vỡ lại nằm ở đó — lát cắt, kẹp số trang, và nút Trước/Sau.
//
// Khác `RebuildCatalogPage`: trang ở đây cắt Ở TRÌNH DUYỆT, CỐ Ý. `monthly_timesheet` còn nuôi
// Lương, Chốt công và bản xuất Excel nên không nhét tham số cắt dữ liệu vào nó. Hệ quả phải khoá
// lại: **một lượt gọi `/timesheet` duy nhất cho cả tháng**, đổi trang KHÔNG bắn thêm request, và
// ô KPI vẫn cộng theo TOÀN BỘ tập đang lọc chứ không theo trang đang xem.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TimesheetTab } from "./TimesheetTab";
import type { Timesheet, TimesheetRow } from "../../../../api/client";

const timesheet = vi.fn();
const period = vi.fn();
const meta = vi.fn();

vi.mock("../../../../api/client", () => ({
  api: {
    employees: { meta: (...a: unknown[]) => meta(...a) },
    attendance: {
      timesheet: (...a: unknown[]) => timesheet(...a),
      period: (...a: unknown[]) => period(...a),
    },
  },
}));

const NAM = 2026;
const THANG = 9;
const SO_NGAY = 30;

function hang(i: number): TimesheetRow {
  // Mã đệm 3 chữ số để thứ tự chuỗi trùng thứ tự số — trang 2 phải bắt đầu đúng ở NV051.
  return {
    employee_id: i,
    employee_code: `NV${String(i).padStart(3, "0")}`,
    employee_name: `Nhân viên ${i}`,
    department_id: 1,
    department_name: "Tổ 1",
    shift_id: 1,
    shift_name: "Ca hành chính",
    days: {},
    total_days: 2,
    total_leave: 0,
    paid_leave_days: 0,
    total_hours: 16,
    total_cong: 2,
  };
}

function bang(soNv: number): Timesheet {
  return {
    year: NAM,
    month: THANG,
    days_in_month: SO_NGAY,
    standard_cong: 26,
    holidays: [],
    he_so_ngay: { le: 2, nghi_tuan: 1.5, off1x: 1 },
    rows: Array.from({ length: soNv }, (_, i) => hang(i + 1)),
  };
}

function moMan(soNv: number) {
  timesheet.mockResolvedValue(bang(soNv));
  return render(<TimesheetTab token="t" canAdjust={false} canLock={false} />);
}

/** Mã NV đang hiện trên bảng, theo đúng thứ tự vẽ ra. */
function maDangHien(): string[] {
  return screen
    .getAllByText(/^NV\d{3}$/)
    .map((el) => el.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  meta.mockResolvedValue({ departments: [{ id: 1, name: "Tổ 1" }] });
  period.mockResolvedValue({
    year: NAM,
    month: THANG,
    status: "draft",
    hanging_days: 0,
    ot_thieu_cap_list: [],
  });
});

describe("Bảng công tháng — phân trang", () => {
  it("mặc định 50 người/trang; cả tháng chỉ gọi /timesheet MỘT lượt", async () => {
    moMan(120);
    await waitFor(() => expect(maDangHien()).toHaveLength(50));

    expect(maDangHien()[0]).toBe("NV001");
    expect(maDangHien()[49]).toBe("NV050");
    // Cắt ở trình duyệt ⇒ đúng một lượt gọi cho cả tháng, không phải mỗi trang một lượt.
    expect(timesheet).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Trang 1\/3/)).toBeInTheDocument();
  });

  it("bấm Sau sang đúng lát kế tiếp và KHÔNG gọi lại máy chủ", async () => {
    const u = userEvent.setup();
    moMan(120);
    await waitFor(() => expect(maDangHien()).toHaveLength(50));

    await u.click(screen.getByRole("button", { name: /Sau/ }));
    await waitFor(() => expect(maDangHien()[0]).toBe("NV051"));
    expect(maDangHien()[49]).toBe("NV100");
    expect(screen.getByText(/Trang 2\/3/)).toBeInTheDocument();
    expect(timesheet).toHaveBeenCalledTimes(1);

    // Trang cuối chỉ còn 20 người — lát cắt không được đệm thêm hàng rỗng.
    await u.click(screen.getByRole("button", { name: /Sau/ }));
    await waitFor(() => expect(maDangHien()).toHaveLength(20));
    expect(maDangHien()[0]).toBe("NV101");
  });

  it("nút Trước/Sau tự mờ ở hai đầu", async () => {
    const u = userEvent.setup();
    moMan(120);
    await waitFor(() => expect(maDangHien()).toHaveLength(50));

    expect(screen.getByRole("button", { name: /Trước/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Sau/ })).toBeEnabled();

    await u.click(screen.getByRole("button", { name: /Sau/ }));
    await u.click(screen.getByRole("button", { name: /Sau/ }));
    await waitFor(() =>
      expect(screen.getByText(/Trang 3\/3/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Sau/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Trước/ })).toBeEnabled();
  });

  it("gõ ô tìm thì về trang 1 — không để bảng trắng vì đứng ở trang cũ", async () => {
    const u = userEvent.setup();
    moMan(120);
    await waitFor(() => expect(maDangHien()).toHaveLength(50));

    await u.click(screen.getByRole("button", { name: /Sau/ }));
    await waitFor(() => expect(maDangHien()[0]).toBe("NV051"));

    // "Nhân viên 7" khớp 7, 70–79 ⇒ 11 người, gọn trong một trang. Đứng ở trang 2 mà không kẹp
    // lại thì bảng trắng trơn trong khi rõ ràng vẫn có người khớp.
    await u.type(
      screen.getByLabelText("Tìm nhân viên trong bảng công"),
      "Nhân viên 7",
    );
    await waitFor(() => expect(maDangHien()).toHaveLength(11));
    expect(maDangHien()[0]).toBe("NV007");
    // Gọn một trang ⇒ cụm Trước/Sau biến mất, và ô đếm nói thẳng tổng số người khớp.
    expect(screen.queryByText(/Trang \d+\/\d+/)).toBeNull();
  });

  it("đổi số/trang giữ nguyên tập đang lọc, và 'Tất cả' vẽ hết", async () => {
    const u = userEvent.setup();
    moMan(120);
    await waitFor(() => expect(maDangHien()).toHaveLength(50));

    await u.selectOptions(screen.getByLabelText(/Mỗi trang/), "100");
    await waitFor(() => expect(maDangHien()).toHaveLength(100));
    expect(screen.getByText(/Trang 1\/2/)).toBeInTheDocument();

    await u.selectOptions(screen.getByLabelText(/Mỗi trang/), "0");
    await waitFor(() => expect(maDangHien()).toHaveLength(120));
    expect(timesheet).toHaveBeenCalledTimes(1);
  });

  it("ô KPI cộng theo TOÀN BỘ tập đang lọc, không theo trang đang xem", async () => {
    moMan(120);
    await waitFor(() => expect(maDangHien()).toHaveLength(50));

    // 120 người × 2 công = 240,0 công, × 16h = 1920,0h. KPI trượt theo trang thì nó nói 50 / 100,0 / 800,0h.
    const so = (nhan: string) =>
      screen.getByText(nhan).parentElement!.querySelector(".cc-ts-kpi-num")!
        .textContent;
    expect(so("Tổng nhân sự")).toBe("120");
    expect(so("Tổng ngày công")).toBe("240.0");
    expect(so("Tổng giờ làm")).toBe("1920.0h");
  });

  it("ít hơn một trang thì chỉ nói tổng số người, không có 'Trang x/y'", async () => {
    moMan(12);
    await waitFor(() => expect(maDangHien()).toHaveLength(12));
    expect(screen.queryByText(/Trang \d+\/\d+/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Sau/ })).toBeNull();
  });
});
