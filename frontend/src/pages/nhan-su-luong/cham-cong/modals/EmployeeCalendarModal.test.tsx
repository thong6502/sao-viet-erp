import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmployeeCalendarModal } from "./EmployeeCalendarModal";
import type { TimesheetRow, HeSoNgay } from "../../../../api/client";

const mockHeSoNgay: HeSoNgay = {
  le: 2,
  nghi_tuan: 1.5,
  off1x: 1,
};

const mockRow = {
  employee_id: 101,
  employee_code: "NV042",
  employee_name: "Nguyễn Văn An",
  department_id: 2,
  department_name: "Phòng Kỹ Thuật",
  shift_id: 1,
  shift_name: "Ca hành chính",
  days: {
    "1": {
      first_in: "08:00",
      last_out: "17:00",
      hours: 8,
      cong: 1,
      shift_name: "Ca hành chính",
    },
    "2": {
      first_in: "08:15",
      last_out: "18:30",
      hours: 9.5,
      cong: 1,
      late: true,
      ot_minutes: 90,
      shift_name: "Ca hành chính",
    },
    "3": {
      leave: "Nghỉ phép năm",
      leave_paid: true,
    },
    "4": {
      first_in: "08:00",
      last_out: "16:45",
      hours: 7.75,
      cong: 1,
      early: true,
    },
  },
  total_days: 3,
  total_leave: 1,
  paid_leave_days: 1,
  total_hours: 25.25,
  total_cong: 3,
} as unknown as TimesheetRow;

describe("EmployeeCalendarModal", () => {
  it("renders employee header information, avatar initials, and month badge", () => {
    const onClose = vi.fn();
    render(
      <EmployeeCalendarModal
        employeeName="Nguyễn Văn An"
        employeeRow={mockRow}
        year={2026}
        month={9}
        daysInMonth={30}
        heSoNgay={mockHeSoNgay}
        onClose={onClose}
      />,
    );

    expect(screen.getByText("Nguyễn Văn An")).toBeInTheDocument();
    expect(screen.getByText("VA")).toBeInTheDocument(); // Nguyễn Văn An -> VA
    expect(screen.getByText("#NV042")).toBeInTheDocument();
    expect(screen.getByText("Phòng Kỹ Thuật")).toBeInTheDocument();
    expect(screen.getAllByText("Ca hành chính").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Tháng 9\/2026/)).toBeInTheDocument();
  });

  it("renders 4 KPI metrics correctly", () => {
    render(
      <EmployeeCalendarModal
        employeeName="Nguyễn Văn An"
        employeeRow={mockRow}
        year={2026}
        month={9}
        daysInMonth={30}
        heSoNgay={mockHeSoNgay}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Ngày công thực tế")).toBeInTheDocument();
    expect(screen.getByText("3 công")).toBeInTheDocument();
    expect(screen.getByText("/30 ngày trong tháng")).toBeInTheDocument();

    expect(screen.getByText("Tổng giờ làm việc")).toBeInTheDocument();
    expect(screen.getByText("25.25h")).toBeInTheDocument();

    expect(screen.getByText("Giờ tăng ca (OT)")).toBeInTheDocument();
    expect(screen.getByText("1.5h")).toBeInTheDocument(); // 90 min = 1.5h

    expect(screen.getByText("Muộn / Về sớm")).toBeInTheDocument();
    expect(screen.getByText("1 muộn · 1 sớm")).toBeInTheDocument();
  });

  it("renders calendar weekday headers and calls onSelectDay when a day is clicked", async () => {
    const onSelectDay = vi.fn();
    const u = userEvent.setup();

    render(
      <EmployeeCalendarModal
        employeeName="Nguyễn Văn An"
        employeeRow={mockRow}
        year={2026}
        month={9}
        daysInMonth={30}
        heSoNgay={mockHeSoNgay}
        onClose={vi.fn()}
        onSelectDay={onSelectDay}
      />,
    );

    // Weekdays
    expect(screen.getByText("T2")).toBeInTheDocument();
    expect(screen.getByText("CN")).toBeInTheDocument();

    // Day 2 (has late & OT)
    const day2 = screen.getByTitle(/lượt chấm công ngày 02\/09/);
    expect(day2).toBeInTheDocument();
    expect(day2).toHaveTextContent("Muộn");
    expect(day2).toHaveTextContent("+OT");

    await u.click(day2);
    expect(onSelectDay).toHaveBeenCalledWith(2);
  });

  it("closes when close button is clicked or Escape key is pressed", async () => {
    const onClose = vi.fn();
    const u = userEvent.setup();

    render(
      <EmployeeCalendarModal
        employeeName="Nguyễn Văn An"
        employeeRow={mockRow}
        year={2026}
        month={9}
        daysInMonth={30}
        heSoNgay={mockHeSoNgay}
        onClose={onClose}
      />,
    );

    // Click Close (Esc) icon button
    const closeBtn = screen.getByLabelText("Đóng");
    await u.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    // Press Escape key
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
