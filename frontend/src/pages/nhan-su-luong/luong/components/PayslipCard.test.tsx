// Phiếu lương của người CHẾ ĐỘ KHOÁN (14/09/2026) — "không có tiền tăng ca luôn".
//
// Engine để tiền GIỜ tăng ca của tổ khoán / tổ Giao hàng = 0đ, nên `ot_pay` của dòng khoán chỉ còn
// phần thêm làm nguyên ngày Chủ nhật / lễ (+ tiền 1× ngày nghỉ off1x). Phiếu phải in dòng "Tăng ca"
// đúng 0đ và tách số kia ra dòng riêng — in chung là người nhận đọc thành "khoán vẫn có tăng ca".
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PayrollLine, PayrollPeriod } from "../../../../api/client";
import { PayslipCard } from "./PayslipCard";

const KY: PayrollPeriod = {
  id: 3, year: 2026, month: 9, status: "draft", standard_cong: 26,
  locked_at: null, paid_at: null, paid_by: null,
};

function dong(o: Partial<PayrollLine>): PayrollLine {
  return {
    id: 1, period_id: 3, employee_id: 9, employee_code: "NV007", employee_name: "Giao Hàng test",
    department_name: "Giao hàng", payroll_group: null, bank_account: null, bank_name: null,
    is_probation: false, actual_cong: 26, standard_cong: 26, monthly_salary: 10_000_000,
    luong_cong: 10_000_000, chuyen_can: 0, allowance: 0, khoan: 0, ot_minutes: 210, ot_pay: 0,
    night_days: 0, night_pay: 0, vi_pham: 0, other_bonus: 0, gross: 10_000_000,
    insurance_base: 10_000_000, bhxh: 0, cong_doan: 0, pit: 0, advance_total: 0,
    net_pay: 10_000_000, note: null,
    ...o,
  } as PayrollLine;
}

function dongThu(nhan: string): HTMLElement {
  const td = screen.getByText(nhan);
  return td.closest("tr") as HTMLElement;
}

describe("Phiếu lương — chế độ khoán không có tiền tăng ca", () => {
  it("⭐ làm nguyên ngày Chủ nhật: dòng Tăng ca 0đ, số tách sang dòng 'Làm ngày Chủ nhật / lễ'", () => {
    render(<PayslipCard period={KY} line={dong({ che_do_khoan: true, ot_pay: 384_615 })} />);

    const tangCa = dongThu("Tăng ca (khoán — không có tiền tăng ca)");
    expect(within(tangCa).getByText("—")).toBeInTheDocument();

    const cn = dongThu("Làm ngày Chủ nhật / lễ");
    expect(within(cn).getByText("384.615")).toBeInTheDocument();

    // Không còn dòng "Tăng ca" trần mang số tiền nào.
    expect(screen.queryByText("Tăng ca")).not.toBeInTheDocument();
  });

  it("khoán có ngày nghỉ off1x thì nhãn nói luôn 'ngày nghỉ 1×'", () => {
    render(<PayslipCard period={KY}
                        line={dong({ che_do_khoan: true, ot_pay: 500_000, off1x_pay: 500_000 })} />);
    expect(dongThu("Làm ngày Chủ nhật / lễ / ngày nghỉ 1×")).toBeInTheDocument();
  });

  it("khoán không làm ngày nghỉ nào: chỉ có dòng Tăng ca 0đ, không mọc dòng CN/lễ rỗng", () => {
    render(<PayslipCard period={KY} line={dong({ che_do_khoan: true, ot_pay: 0 })} />);
    expect(dongThu("Tăng ca (khoán — không có tiền tăng ca)")).toBeInTheDocument();
    expect(screen.queryByText(/Làm ngày Chủ nhật/)).not.toBeInTheDocument();
  });

  it("người KHÔNG ăn khoán: vẫn một dòng 'Tăng ca' mang đủ tiền như cũ", () => {
    render(<PayslipCard period={KY} line={dong({ che_do_khoan: false, ot_pay: 252_404 })} />);
    const tangCa = dongThu("Tăng ca");
    expect(within(tangCa).getByText("252.404")).toBeInTheDocument();
    expect(screen.queryByText(/khoán — không có tiền tăng ca/)).not.toBeInTheDocument();
  });
});
