// Băng "Sản lượng của tôi" — thợ tự trả lời "tháng này tôi làm được bao nhiêu", KHÔNG có ô tiền.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThsxSanLuongCuaToi } from "./ThsxSanLuongCuaToi";

describe("Sản lượng của tôi", () => {
  it("hiện tổng theo từng đơn vị, không có ô tiền", () => {
    render(<ThsxSanLuongCuaToi data={{
      nam: 2026, thang: 9, employee_id: 11, so_me: 7,
      theo_don_vi: [{ don_vi: "to", tong: 12400 }, { don_vi: "cai", tong: 3100 }],
    }} />);
    expect(screen.getByText(/Sản lượng của tôi/)).toBeInTheDocument();
    expect(screen.getByText(/12\.400/)).toBeInTheDocument();
    expect(screen.getByText(/7 mẻ/)).toBeInTheDocument();
    expect(screen.queryByText(/đồng|tiền|đơn giá/)).toBeNull();
  });

  it("chưa có sản lượng thì nói rõ, không hiện 0 trống trơn", () => {
    render(<ThsxSanLuongCuaToi data={{
      nam: 2026, thang: 9, employee_id: 11, so_me: 0, theo_don_vi: [],
    }} />);
    expect(screen.getByText(/Tháng này chưa có mẻ nào được chốt/)).toBeInTheDocument();
  });

  it("chưa nạp xong thì không vẽ băng rỗng", () => {
    const { container } = render(<ThsxSanLuongCuaToi data={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
