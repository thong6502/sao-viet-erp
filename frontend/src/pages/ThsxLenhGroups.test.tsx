// Bản ghi của bàn tổ là LỆNH: dòng lệnh hiện mã + tên + số việc, bấm mới bung công đoạn.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThsxLenhGroups } from "./ThsxLenhGroups";
import type { SxLenhNhom } from "../api/client";

const lenh: SxLenhNhom[] = [
  {
    nguon_loai: "lsx", nguon_ma: "LSX26-0012", nguon_ten: "Hộp bánh 500g",
    lsx_id: 12, bai_ghep_id: null,
    som_nhat: "2026-09-11T07:30:00", muon_nhat: "2026-09-11T15:00:00",
    so_viec: 2,
    digest: { released: 1, running: 1, paused: 0, completed: 0 },
    cong_viec: [
      { id: 1, ten_cong_doan: "In 4 màu" } as never,
      { id: 2, ten_cong_doan: "Cán bóng" } as never,
    ],
  },
  {
    nguon_loai: "bai_ghep", nguon_ma: "BG26-0004", nguon_ten: "Ghép 3 lệnh",
    lsx_id: null, bai_ghep_id: 4,
    som_nhat: null, muon_nhat: null,
    so_viec: 1,
    digest: { released: 1, running: 0, paused: 0, completed: 0 },
    cong_viec: [{ id: 9, ten_cong_doan: "Bế" } as never],
  },
];

describe("ThsxLenhGroups", () => {
  it("mỗi lệnh một dòng, kèm mã và số việc", () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={null}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("LSX26-0012")).toBeInTheDocument();
    expect(screen.getByText("Hộp bánh 500g")).toBeInTheDocument();
    expect(screen.getByText("BG26-0004")).toBeInTheDocument();
    expect(screen.getByText("2 việc")).toBeInTheDocument();
  });

  it("lệnh đầu mở sẵn, lệnh sau gấp — bấm mới bung công đoạn", async () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={null}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("In 4 màu")).toBeInTheDocument();
    expect(screen.queryByText("Bế")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /BG26-0004/ }));
    expect(screen.getByText("Bế")).toBeInTheDocument();
  });

  it("lệnh chứa việc đang chọn thì luôn mở", () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={9}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("Bế")).toBeInTheDocument();
  });

  it("lệnh có việc chờ tổ xác nhận: chấm đỏ trên dòng lệnh và mở sẵn dù không phải lệnh đầu", () => {
    const cho = new Map([[9, { nhan: 1, kcs: 0, hoTro: 0 }]]);
    render(<ThsxLenhGroups lenh={lenh} selectedId={null} cho={cho}
      render={(v) => <ul>{v.map((w) => <li key={w.id}>{w.ten_cong_doan}</li>)}</ul>} />);
    expect(screen.getByText("Bế")).toBeInTheDocument();
    expect(screen.getByText("In 4 màu")).toBeInTheDocument();
    const cham = screen.getAllByRole("img", { name: "1 bàn giao chờ nhận" });
    expect(cham).toHaveLength(1);
    expect(screen.getByRole("button", { name: /BG26-0004/ })).toContainElement(cham[0]);
  });

  it("lệnh chưa xếp giờ nói rõ là chưa xếp, không hiện ô giờ trống", () => {
    render(<ThsxLenhGroups lenh={lenh} selectedId={null}
      render={() => null} />);
    expect(screen.getByText("chưa xếp giờ")).toBeInTheDocument();
  });
});
