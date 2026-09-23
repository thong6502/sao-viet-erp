// Xin hủy đơn nghỉ / phiếu tăng ca ĐÃ DUYỆT (chủ chốt 23/09/2026).
//
// Khoá: (1) nhãn trên dòng nói đúng trạng thái yêu cầu hủy; (2) hộp lý do không cho gửi khi trống;
// (3) hàng đợi người duyệt: "Giữ nguyên" bắt lý do, "Đồng ý hủy" thì không, lỗi máy chủ giữ hộp mở;
// (4) bảng đơn nghỉ: đơn ĐÃ DUYỆT không còn nút "Hủy đơn" cho người lao động — chỉ "Xin hủy", và
// đang có yêu cầu chờ thì thay bằng "Rút lại".
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { LeaveRequest, YeuCauHuy } from "../../../api/client";
import { LeaveTable } from "../nghi-phep/components/LeaveTable";
import { LyDoDialog, XinHuyHangDoi, XinHuyNhan } from "./XinHuy";

const YC: YeuCauHuy = {
  id: 7,
  loai: "nghi_phep",
  request_id: 3,
  ly_do: "Việc nhà xong sớm",
  trang_thai: "cho",
  truc_tiep: false,
  huy_tu_ngay: null,
  den_ngay_cu: null,
  ly_do_quyet: null,
  created_at: "2026-09-23T02:00:00Z",
  decided_at: null,
  decided_by_name: null,
};

const DON: LeaveRequest = {
  id: 3,
  employee_id: 9,
  employee_name: "Nguyễn Văn Thợ",
  leave_type_id: 1,
  leave_type_name: "Việc riêng",
  is_paid: false,
  start_date: "2099-10-05",
  end_date: "2099-10-07",
  days: 3,
  reason: "việc nhà",
  status: "approved",
  decided_by: 2,
  decided_at: "2026-09-20T02:00:00Z",
  decision_note: null,
  created_at: "2026-09-19T02:00:00Z",
  yeu_cau_huy: null,
};

describe("XinHuyNhan", () => {
  it("đang chờ ⇒ 'Đang xin hủy'; giữ nguyên ⇒ kèm lý do; rút ngắn ⇒ ngày gốc; rút lại ⇒ không vẽ", () => {
    const { rerender, container } = render(<XinHuyNhan yc={YC} />);
    expect(screen.getByText("Đang xin hủy")).toBeInTheDocument();
    rerender(<XinHuyNhan yc={{ ...YC, trang_thai: "giu_nguyen", ly_do_quyet: "Tổ thiếu người" }} />);
    expect(screen.getByText("Không được hủy")).toBeInTheDocument();
    expect(screen.getByText("Tổ thiếu người")).toBeInTheDocument();
    rerender(<XinHuyNhan yc={{ ...YC, trang_thai: "dong_y", den_ngay_cu: "2099-10-07" }} />);
    expect(screen.getByText("Rút ngắn")).toBeInTheDocument();
    expect(screen.getByText("gốc tới 7/10/2099")).toBeInTheDocument();
    rerender(<XinHuyNhan yc={{ ...YC, trang_thai: "rut_lai" }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("LyDoDialog", () => {
  it("lý do bắt buộc: trống thì nút gửi khoá; gõ xong gửi đúng chữ đã cắt khoảng trắng", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <LyDoDialog open title="Xin hủy đơn đã duyệt" label="Lý do xin hủy" confirmLabel="Gửi yêu cầu hủy"
        onConfirm={onConfirm} onCancel={() => {}} />,
    );
    const nut = screen.getByRole("button", { name: "Gửi yêu cầu hủy" });
    expect(nut).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "  Con ốm  ");
    expect(nut).toBeEnabled();
    await user.click(nut);
    expect(onConfirm).toHaveBeenCalledWith("Con ốm");
  });

  it("mở lại sau khi gửi ⇒ ô lý do trống, không dính chữ lần trước", async () => {
    const user = userEvent.setup();
    const props = { title: "Xin hủy", label: "Lý do", confirmLabel: "Gửi", onConfirm: vi.fn(), onCancel: () => {} };
    const { rerender } = render(<LyDoDialog open {...props} />);
    await user.type(screen.getByRole("textbox"), "lần một");
    rerender(<LyDoDialog open={false} {...props} />);
    rerender(<LyDoDialog open {...props} />);
    expect(screen.getByRole("textbox")).toHaveValue("");
  });
});

describe("XinHuyHangDoi", () => {
  it("⭐ Giữ nguyên bắt lý do; Đồng ý hủy không bắt; lỗi máy chủ giữ hộp mở và hiện lỗi", async () => {
    const onQuyet = vi.fn().mockRejectedValueOnce(new Error("Yêu cầu hủy này đã được xử lý.")).mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <XinHuyHangDoi donVi="đơn" dong={[{ yc: YC, ten: "Nguyễn Văn Thợ", don: "Việc riêng · 05/10–07/10/2099" }]}
        onQuyet={onQuyet} />,
    );
    expect(screen.getByText("Lý do: Việc nhà xong sớm")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Giữ nguyên" }));
    const giu = screen.getAllByRole("button", { name: "Giữ nguyên" }).at(-1)!;
    expect(giu).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "Tổ đã xếp người thay");
    await user.click(giu);
    await waitFor(() => expect(onQuyet).toHaveBeenCalledWith(YC, false, "Tổ đã xếp người thay"));
    expect(await screen.findByText("Yêu cầu hủy này đã được xử lý.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Quay lại" }));
    await user.click(screen.getByRole("button", { name: "Đồng ý hủy" }));
    const dongY = screen.getAllByRole("button", { name: "Đồng ý hủy" }).at(-1)!;
    expect(dongY).toBeEnabled();
    await user.click(dongY);
    await waitFor(() => expect(onQuyet).toHaveBeenLastCalledWith(YC, true, ""));
  });

  it("không có yêu cầu nào ⇒ không vẽ khối", () => {
    const { container } = render(<XinHuyHangDoi donVi="phiếu" dong={[]} onQuyet={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("LeaveTable — nút theo luật xin hủy", () => {
  const ve = (don: LeaveRequest) =>
    render(<LeaveTable items={[don]} showEmployee={false} onCancel={vi.fn()} onXinHuy={vi.fn()}
      onRutLaiXinHuy={vi.fn()} />);

  it("⭐ đơn ĐÃ DUYỆT: không có 'Hủy đơn', chỉ có 'Xin hủy đơn'", () => {
    ve(DON);
    expect(screen.queryByRole("button", { name: "Hủy đơn" })).toBeNull();
    expect(screen.getByRole("button", { name: "Xin hủy đơn" })).toBeInTheDocument();
  });

  it("đang có yêu cầu chờ ⇒ nhãn 'Đang xin hủy' + nút 'Rút lại', không xin lần hai", () => {
    ve({ ...DON, yeu_cau_huy: YC });
    expect(screen.getByText("Đang xin hủy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rút lại yêu cầu hủy" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xin hủy đơn" })).toBeNull();
  });

  it("đơn đã qua ⇒ không xin hủy được; đơn CHỜ duyệt ⇒ vẫn 'Hủy đơn' thẳng", () => {
    const { unmount } = ve({ ...DON, start_date: "2020-01-06", end_date: "2020-01-06" });
    expect(screen.queryByRole("button", { name: "Xin hủy đơn" })).toBeNull();
    unmount();
    ve({ ...DON, status: "pending", decided_at: null, decided_by: null });
    expect(screen.getByRole("button", { name: "Hủy đơn" })).toBeInTheDocument();
  });
});
