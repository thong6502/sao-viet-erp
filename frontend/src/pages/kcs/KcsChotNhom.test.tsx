import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { SxDongNhomDieuKien, SxDongNhomDieuKienItem } from "../../api/client";
import { KcsChotNhom, tomTatChotNhom } from "./KcsChotNhom";

vi.mock("../../auth/useAuth", () => ({ useAuth: () => ({ token: "token-test" }) }));
const dieuKienDongNhom = vi.fn();
const dongThieu = vi.fn();
vi.mock("../../api/client", async (goc) => ({
  ...(await goc<typeof import("../../api/client")>()),
  api: {
    sanXuat: {
      dieuKienDongNhom: (...a: unknown[]) => dieuKienDongNhom(...a),
      dongThieu: (...a: unknown[]) => dongThieu(...a),
    },
  },
}));

function dk(over: Partial<SxDongNhomDieuKien>, sai: Record<string, string> = {}): SxDongNhomDieuKien {
  const ma = ["moi_viec_xong", "khong_lech_ban_giao", "kcs_cuoi_kiem_het", "dat_muc_tieu"];
  const dieu_kien: SxDongNhomDieuKienItem[] = ma.map((m) => ({
    ma: m, ten: m, dat: !(m in sai), chi_tiet: sai[m] ?? "",
  }));
  const duThieu = !("khong_lech_ban_giao" in sai) && !("kcs_cuoi_kiem_het" in sai);
  return {
    nhom_id: 4, trang_thai: "in_production", version: 1,
    du_dong_du: Object.keys(sai).length === 0, du_dong_thieu: duThieu,
    dieu_kien, muc_tieu: 10000, da_dat: 288, con_thieu: 9712,
    ...over,
  };
}

describe("tomTatChotNhom — một câu nói nhóm đang ở đâu", () => {
  it("NTP26-0004: thiếu hàng + còn việc dở, đóng thiếu được ⇒ không có lý do chặn", () => {
    const t = tomTatChotNhom(dk({}, { moi_viec_xong: "còn 5 việc chưa xong", dat_muc_tieu: "mới đạt 288/10.000" }));
    expect(t.tone).toBe("cho");
    expect(t.cau).toBe("Chưa đủ hàng, còn 5 việc chưa xong.");
    expect(t.goiY).toBe('Nếu không làm tiếp nữa, trưởng tổ KCS bấm "Đóng thiếu" để chốt giao 288 / 10.000.');
    expect(t.lyDoChan).toEqual([]);
  });

  it("đủ hàng nhưng còn việc ⇒ nói rõ xong hết thì tự đóng đủ", () => {
    const t = tomTatChotNhom(dk({ da_dat: 10000, con_thieu: 0 }, { moi_viec_xong: "còn 2 việc chưa xong" }));
    expect(t.cau).toBe("Đủ hàng rồi, nhưng còn 2 việc chưa xong — xong hết thì nhóm tự đóng đủ.");
  });

  it("KCS chưa kiểm hết hàng tổ đã làm ⇒ chặn đóng thiếu, nói bằng lời thường", () => {
    const t = tomTatChotNhom(dk({}, { dat_muc_tieu: "mới đạt 288/10.000", kcs_cuoi_kiem_het: "mới kiểm 250/300" }));
    expect(t.goiY).toBeNull();
    expect(t.lyDoChan).toEqual(["KCS chưa kiểm hết hàng tổ đã làm ở công đoạn cuối (mới kiểm 250/300)."]);
  });

  it("bàn giao lệch ⇒ chặn đóng thiếu", () => {
    const t = tomTatChotNhom(dk({}, { khong_lech_ban_giao: "1 công đoạn bàn giao chưa nhất quán" }));
    expect(t.lyDoChan).toEqual(["Có công đoạn bàn giao chưa khớp số — tổ phải xử lý ở bàn tổ trước."]);
  });

  it("đã đóng ⇒ câu chốt, không gợi ý, không lý do", () => {
    expect(tomTatChotNhom(dk({ trang_thai: "closed_full" })).cau).toBe("Đã đóng đủ — đủ hàng để giao.");
    const t = tomTatChotNhom(dk({ trang_thai: "closed_short" }, { dat_muc_tieu: "x" }));
    expect(t).toEqual({ tone: "dong", cau: "Đã đóng thiếu — chốt giao 288 / 10.000.", goiY: null, lyDoChan: [] });
  });

  it("màn: số đạt/mục tiêu + câu tình trạng; trưởng KCS bấm Đóng thiếu → xác nhận → gọi máy chủ", async () => {
    const mo = dk({}, { moi_viec_xong: "còn 5 việc chưa xong", dat_muc_tieu: "mới đạt 288/10.000" });
    dieuKienDongNhom.mockResolvedValueOnce(mo)
      .mockResolvedValueOnce({ ...mo, trang_thai: "closed_short", version: 2 });
    dongThieu.mockResolvedValue({});
    const onDone = vi.fn();
    render(<KcsChotNhom nhomId={4} nhan="NTP26-0004" canDong onDone={onDone} />);

    expect(await screen.findByText("Chưa đủ hàng, còn 5 việc chưa xong.")).toBeTruthy();
    expect(screen.getByText("9.712")).toBeTruthy();
    expect(screen.queryByText(/toàn vẹn|Mọi công việc đã hoàn thành/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Đóng thiếu/ }));
    fireEvent.click(screen.getByRole("button", { name: /Xác nhận đóng thiếu/ }));
    await waitFor(() => expect(dongThieu).toHaveBeenCalledWith("token-test", 4, { expected_version: 1 }));
    expect(await screen.findByText("Đã đóng thiếu — chốt giao 288 / 10.000.")).toBeTruthy();
    expect(onDone).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Đóng thiếu/ })).toBeNull();
  });

  it("màn: người không phải trưởng KCS thấy câu hướng dẫn nhưng không có nút", async () => {
    dieuKienDongNhom.mockResolvedValueOnce(dk({}, { dat_muc_tieu: "mới đạt 288/10.000" }));
    render(<KcsChotNhom nhomId={4} nhan="NTP26-0004" canDong={false} onDone={() => {}} />);
    expect(await screen.findByText(/trưởng tổ KCS bấm "Đóng thiếu"/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Đóng thiếu/ })).toBeNull();
  });

  it("công đoạn cuối chưa có số mục tiêu", () => {
    const t = tomTatChotNhom(dk({ muc_tieu: null, con_thieu: null }, { dat_muc_tieu: "công đoạn cuối chưa có số mục tiêu" }));
    expect(t.cau).toBe("Công đoạn cuối chưa có số mục tiêu nên nhóm không tự đóng được.");
    expect(t.goiY).toBe('Nếu không làm tiếp nữa, trưởng tổ KCS bấm "Đóng thiếu" để chốt giao 288.');
  });
});
