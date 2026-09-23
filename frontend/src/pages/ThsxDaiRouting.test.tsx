// Dải routing: tổ thấy cả chuỗi, bước của tổ khác là CHỈ ĐỌC (không nút, không mở được).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThsxDaiRouting } from "./ThsxDaiRouting";
import type { SxRoutingBuoc } from "../api/client";

function buoc(p: Partial<SxRoutingBuoc>): SxRoutingBuoc {
  return {
    thu_tu: 1, step_key: "s1", ten_cong_doan: "In", to_id: 1, to_ten: "Tổ in",
    la_cua_toi: false, la_kcs_cuoi: false, trang_thai: "completed",
    phan_doan_tong: 1, chay_chung: false, ke_hoach: 5300, thuc_te: 5300,
    don_vi: "tờ", da_giao_sang_toi: null, da_nhan: null, cong_viec_id: null,
    ...p,
  };
}

const dai: SxRoutingBuoc[] = [
  buoc({ thu_tu: 1, step_key: "s1", ten_cong_doan: "In", to_ten: "Nhóm in 5 màu" }),
  buoc({ thu_tu: 2, step_key: "s2", ten_cong_doan: "Cán phủ", to_ten: "Tổ cán phủ",
         da_giao_sang_toi: 5220 }),
  buoc({ thu_tu: 3, step_key: "s3", ten_cong_doan: "Bế", to_ten: "Tổ bế", la_cua_toi: true,
         trang_thai: "running", cong_viec_id: 88, da_nhan: 5220, ke_hoach: 10200, thuc_te: 0 }),
  buoc({ thu_tu: 4, step_key: "s4", ten_cong_doan: "Dán", to_ten: "Tổ dán",
         trang_thai: "released", thuc_te: 0 }),
];

describe("ThsxDaiRouting", () => {
  it("bày đủ chuỗi công đoạn kèm tổ giữ từng bước", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.getByText("In")).toBeInTheDocument();
    expect(screen.getByText("Cán phủ")).toBeInTheDocument();
    expect(screen.getByText("Bế")).toBeInTheDocument();
    expect(screen.getByText("Dán")).toBeInTheDocument();
    expect(screen.getByText("Nhóm in 5 màu")).toBeInTheDocument();
  });

  it("đánh dấu bước của tổ mình", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.getByText("Tổ của bạn")).toBeInTheDocument();
  });

  it("không ô nào bấm được — dải là chỉ đọc", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("ô nguồn nói đã giao sang, ô của mình nói đã nhận", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.getByText(/Đã giao sang/)).toBeInTheDocument();
    expect(screen.getByText(/Đã nhận/)).toBeInTheDocument();
    expect(screen.getAllByText(/5\.220/).length).toBeGreaterThan(0);
  });

  it("lệnh một bước thì không vẽ dải", () => {
    const { container } = render(<ThsxDaiRouting dai={[dai[0]]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("dải dài hơn 5 bước thì gom hai đầu, không cuộn ngang", () => {
    const dai9 = Array.from({ length: 9 }, (_, i) =>
      buoc({ thu_tu: i + 1, step_key: `k${i}`, ten_cong_doan: `CĐ ${i + 1}`,
             la_cua_toi: i === 4 }));
    render(<ThsxDaiRouting dai={dai9} />);
    expect(screen.getByText("CĐ 5")).toBeInTheDocument();
    expect(screen.queryByText("CĐ 1")).not.toBeInTheDocument();
    expect(screen.queryByText("CĐ 9")).not.toBeInTheDocument();
    // Bước của mình ở giữa (thứ 5/9) ⇒ cửa sổ là bước 3-7, gom 2 bước mỗi đầu.
    expect(screen.getAllByText("+2")).toHaveLength(2);
  });
});
