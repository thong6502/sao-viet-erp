import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { LOC_TRONG, ThsxLocNangCao, soTieuChi, thamSoLoc, type ThsxLoc } from "./ThsxLocNangCao";

function Khung({ dau = LOC_TRONG, mo = true, nhan }: { dau?: ThsxLoc; mo?: boolean; nhan?: (l: ThsxLoc) => void }) {
  const [loc, setLoc] = useState(dau);
  return <ThsxLocNangCao mo={mo} value={loc} onChange={(l) => { setLoc(l); nhan?.(l); }} />;
}

describe("thamSoLoc", () => {
  it("mặc định không gửi gì — máy chủ tự sắp lệnh nhận sau lên trên", () => {
    expect(thamSoLoc(LOC_TRONG)).toEqual({});
    expect(soTieuChi(LOC_TRONG)).toBe(0);
  });

  it("khoảng ngày ngược thì KHÔNG gửi ngày, ngày năm 6 chữ số cũng không", () => {
    expect(thamSoLoc({ ...LOC_TRONG, nhanTu: "2026-09-20", nhanDen: "2026-09-10" }))
      .toEqual({});
    expect(thamSoLoc({ ...LOC_TRONG, nhanTu: "202609-01-01" })).toEqual({});
    expect(thamSoLoc({ ...LOC_TRONG, trangThai: ["running"], nhanTu: "2026-09-01", sapXep: "du_kien" }))
      .toEqual({ trangThai: ["running"], nhanTu: "2026-09-01", sapXep: "du_kien" });
  });
});

describe("ThsxLocNangCao", () => {
  it("bấm trạng thái bật/tắt, chọn cách sắp", async () => {
    const ghi: ThsxLoc[] = [];
    render(<Khung nhan={(l) => ghi.push(l)} />);
    await userEvent.click(screen.getByRole("button", { name: "Đang chạy" }));
    await userEvent.click(screen.getByRole("button", { name: "Tạm dừng" }));
    expect(ghi[ghi.length - 1].trangThai).toEqual(["running", "paused"]);
    await userEvent.click(screen.getByRole("button", { name: "Đang chạy" }));
    expect(ghi[ghi.length - 1].trangThai).toEqual(["paused"]);
    await userEvent.click(screen.getByRole("radio", { name: "Theo giờ dự kiến" }));
    expect(ghi[ghi.length - 1].sapXep).toBe("du_kien");
    await userEvent.click(screen.getByRole("button", { name: "Xoá bộ lọc" }));
    expect(ghi[ghi.length - 1]).toEqual(LOC_TRONG);
  });

  it("ngày nhận: ô ngày chỉ mở khi chọn Khoảng ngày; nút nhanh điền sẵn cả hai đầu", async () => {
    const ghi: ThsxLoc[] = [];
    render(<Khung nhan={(l) => ghi.push(l)} />);
    expect(screen.getByRole("radio", { name: "Tất cả" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByLabelText("Nhận từ ngày")).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: "7 ngày" }));
    const l = ghi[ghi.length - 1];
    expect(l.nhanTu).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(l.nhanTu < l.nhanDen).toBe(true);
    expect(screen.getByRole("radio", { name: "7 ngày" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: /Khoảng ngày/ }));
    expect(screen.getByLabelText("Nhận từ ngày")).toHaveValue(l.nhanTu);
  });

  it("khoảng ngày ngược thì báo ngay trên ô", () => {
    render(<Khung dau={{ ...LOC_TRONG, nhanTu: "2026-09-20", nhanDen: "2026-09-10" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("chưa lọc theo ngày");
  });

  it("gập mà vẫn lọc thì còn nhãn bộ lọc, bấm ✕ là bỏ đúng tiêu chí đó", async () => {
    render(<Khung mo={false} dau={{ ...LOC_TRONG, trangThai: ["completed"], nhanTu: "2026-09-16", nhanDen: "2026-09-16" }} />);
    expect(screen.getByText(/Hoàn thành/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bỏ lọc Trạng thái" }));
    expect(screen.queryByText(/Hoàn thành/)).toBeNull();
    expect(screen.getByText(/16\/9\/2026/)).toBeInTheDocument();
  });

  it("không lọc gì mà gập thì không bày gì", () => {
    const { container } = render(<Khung mo={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
