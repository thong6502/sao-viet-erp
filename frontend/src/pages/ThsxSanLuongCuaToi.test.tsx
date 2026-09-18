// Băng "Các mẻ tôi tham gia" (spec 2026-09-18 §7.5) — sản lượng CẢ MẺ + danh sách người, KHÔNG có
// "phần của tôi", không số phút, không ô tiền.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThsxSanLuongCuaToi } from "./ThsxSanLuongCuaToi";

describe("Các mẻ tôi tham gia", () => {
  it("mở ra thấy mẻ: việc khoán, số của cả mẻ, người kèm nhãn tổ — không tiền, không phút", () => {
    render(<ThsxSanLuongCuaToi data={{
      nam: 2026, thang: 9, employee_id: 11, so_me: 1,
      me: [{
        batch_id: 5, bat_dau: "2026-09-18T08:00:00", ket_thuc: "2026-09-18T09:00:00",
        lsx_ma: "LSX26-0012", ten_cong_doan: "Cán màng mờ", viec_khoan_ten: "Bình bài & ra kẽm",
        tot: 1000, hong: 2, don_vi: "to",
        nguoi_tham_gia: [
          { employee_id: 11, ho_ten: "tôi", to_ten: null },
          { employee_id: 12, ho_ten: "Nguyễn A", to_ten: "Tổ bế" },
        ],
      }],
    }} />);
    expect(screen.getByText(/Các mẻ tôi tham gia · tháng 9\/2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1 mẻ/ }));
    expect(screen.getByText("LSX26-0012")).toBeInTheDocument();
    expect(screen.getByText("Bình bài & ra kẽm")).toBeInTheDocument();
    expect(screen.getByText(/1\.000/)).toBeInTheDocument();
    expect(screen.getByText(/\(Tổ bế\)/)).toBeInTheDocument();
    expect(screen.queryByText(/đồng|tiền|đơn giá|phút|phần của tôi/)).toBeNull();
  });

  it("chưa có mẻ thì nói rõ, không hiện 0 trống trơn", () => {
    render(<ThsxSanLuongCuaToi data={{ nam: 2026, thang: 9, employee_id: 11, so_me: 0, me: [] }} />);
    expect(screen.getByText(/Tháng này bạn chưa có mặt ở mẻ nào/)).toBeInTheDocument();
  });

  it("chưa nạp xong thì không vẽ băng rỗng", () => {
    const { container } = render(<ThsxSanLuongCuaToi data={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
