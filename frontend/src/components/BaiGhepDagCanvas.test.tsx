// Bằng chứng THẬT cho canvas bài ghép: render nó, bấm vào nó, đọc lại những gì nó hiện.
//
// Trước đây phần FE của module này chỉ được "khoá" bằng mấy dòng `assert "n.buoc.map" in source`
// bên pytest — grep chuỗi trên mã nguồn. Nó chứng minh KÝ TỰ tồn tại, không chứng minh render:
// đổi `n.buoc.map(...)` thành `n.buoc.filter(...).map(...)` là đỏ dù đúng, còn để nguyên chuỗi đó
// trong một comment thì xanh dù đã xoá sạch UI.
import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BaiGhepDagCanvas, sapHang, tinhCot } from "./BaiGhepDagCanvas";
import { buoc, gop, nhanh, soDo } from "../test/baiGhepSoDoFixture";
import type { BaiGhepSoDo } from "../api/client";

/** Thẻ bước mang tên `ten` — bấm vào chính thẻ, không bấm vào nhãn con bên trong. */
function the(ten: string): HTMLElement {
  const el = screen.getByTitle(ten).closest(".dag-node");
  if (!el) throw new Error(`không tìm thấy thẻ "${ten}"`);
  return el as HTMLElement;
}

/** Thanh nổi khi đang chọn bước. Không dùng `getByRole("status")`: ô tỉ lệ zoom ở thanh công cụ
 *  cũng là `status`, và đó là chủ ý — người đọc màn hình cần nghe tỉ lệ khi thu phóng. */
function thanhChon(): HTMLElement | null {
  return document.querySelector(".bgsd-selbar__info");
}

/** Hai lệnh, mỗi lệnh một bước in cùng công đoạn — hình đơn giản nhất còn gộp được. */
function haiLenhChuaGop(): BaiGhepSoDo {
  return soDo({
    nhanh: [
      nhanh({ lsx_id: 1, buoc: [buoc({ step_key: "a-in", ten: "In A" })] }),
      nhanh({ lsx_id: 2, buoc: [buoc({ step_key: "b-in", ten: "In B" })] }),
    ],
  });
}

function hoan<T>() {
  let xong!: (v: T) => void;
  const p = new Promise<T>((res) => { xong = res; });
  return { p, xong };
}

describe("chọn bước để gộp", () => {
  it("thẻ công đoạn chọn được bằng bàn phím và báo trạng thái đã chọn", async () => {
    const hoi = vi.fn().mockResolvedValue({});
    render(
      <BaiGhepDagCanvas sd={haiLenhChuaGop()} chon={null} onChon={() => {}}
                        onGop={async () => {}} onHoiUngVien={hoi} />,
    );

    const node = the("In A");
    node.focus();
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(hoi).toHaveBeenCalledWith(["a-in"]));
    expect(node).toHaveAttribute("aria-pressed", "true");
  });

  it("không làm sáng bước cùng LSX hoặc khác công đoạn dù phản hồi ứng viên bị rộng", async () => {
    const data = soDo({
      nhanh: [
        nhanh({ lsx_id: 1, buoc: [
          buoc({ step_key: "a-in", ten: "In A", cong_doan_id: 20 }),
          buoc({ step_key: "a-in-2", ten: "In A lần 2", cong_doan_id: 20 }),
        ] }),
        nhanh({ lsx_id: 2, buoc: [
          buoc({ step_key: "b-can", ten: "Cán B", cong_doan_id: 30 }),
          buoc({ step_key: "b-in", ten: "In B", cong_doan_id: 20 }),
        ] }),
      ],
    });
    const hoi = vi.fn().mockResolvedValue({
      "a-in-2": { gop_duoc: true, ly_do: null },
      "b-can": { gop_duoc: true, ly_do: null },
      "b-in": { gop_duoc: true, ly_do: null },
    });
    render(<BaiGhepDagCanvas sd={data} chon={null} onChon={() => {}} onGop={async () => {}} onHoiUngVien={hoi} />);

    await userEvent.click(the("In A"));
    await waitFor(() => expect(the("In B")).toHaveClass("is-ung-vien"));

    expect(the("In A lần 2")).not.toHaveClass("is-ung-vien");
    expect(the("Cán B")).not.toHaveClass("is-ung-vien");
  });

  it("một cú bấm = MỘT lượt hỏi server, kể cả dưới StrictMode", async () => {
    // StrictMode gọi updater của `setState` HAI lần để soi hàm thuần. Đặt lời gọi mạng bên trong
    // updater là mỗi cú bấm bắn hai request — và hai request ấy còn đua nhau ghi kết quả.
    const hoi = vi.fn().mockResolvedValue({});
    render(
      <StrictMode>
        <BaiGhepDagCanvas sd={haiLenhChuaGop()} chon={null} onChon={() => {}}
                          onGop={async () => {}} onHoiUngVien={hoi} />
      </StrictMode>,
    );

    await userEvent.click(the("In A"));
    await waitFor(() => expect(hoi).toHaveBeenCalledTimes(1));
    expect(hoi).toHaveBeenCalledWith(["a-in"]);
  });

  it("câu trả lời của tập chọn CŨ về muộn thì bị bỏ, không sáng nhầm thẻ", async () => {
    // Bấm nhanh hai thẻ: lượt hỏi thứ nhất về SAU lượt thứ hai. Không có seq token thì kết quả cũ
    // ghi đè lên tập chọn mới → thẻ sáng sai → bấm Gộp ăn 409, đúng cái mà "kiểm TRƯỚC" định tránh.
    const cham = hoan<Record<string, { gop_duoc: boolean; ly_do: string | null }>>();
    const nhanh_ = hoan<Record<string, { gop_duoc: boolean; ly_do: string | null }>>();
    const hoi = vi.fn()
      .mockReturnValueOnce(cham.p)
      .mockReturnValueOnce(nhanh_.p);

    const { container } = render(
      <BaiGhepDagCanvas sd={haiLenhChuaGop()} chon={null} onChon={() => {}}
                        onGop={async () => {}} onHoiUngVien={hoi} />,
    );

    await userEvent.click(the("In A"));
    await userEvent.click(the("In B"));          // ungVien còn rỗng → chọn lại từ đầu
    await waitFor(() => expect(hoi).toHaveBeenCalledTimes(2));

    nhanh_.xong({});                              // lượt MỚI về trước, trả rỗng
    cham.xong({ "a-in": { gop_duoc: true, ly_do: null } });   // lượt CŨ về sau
    await waitFor(() => expect(thanhChon()).toHaveTextContent(/Đã chọn/));

    expect(container.querySelectorAll(".is-ung-vien")).toHaveLength(0);
  });

  it("bấm thẻ mờ vì sinh vòng thì NÓI lý do, không im lặng nuốt cú bấm", async () => {
    const hoi = vi.fn().mockResolvedValue({
      "b-in": { gop_duoc: false, ly_do: "Gộp sẽ sinh vòng: In B đang chờ Cán A" },
    });
    render(
      <BaiGhepDagCanvas sd={haiLenhChuaGop()} chon={null} onChon={() => {}}
                        onGop={async () => {}} onHoiUngVien={hoi} />,
    );

    await userEvent.click(the("In A"));
    await waitFor(() => expect(the("In B")).toHaveClass("is-mo"));

    await userEvent.click(the("In B"));
    expect(await screen.findByRole("alert")).toHaveTextContent("In B đang chờ Cán A");
    // Và tập chọn KHÔNG đổi — thẻ mờ vì vòng thì vẫn không được chọn.
    expect(thanhChon()).toHaveTextContent(/Đã chọn\s*1\s*bước/);
  });
});

describe("chip dư tờ", () => {
  /** Bước gộp là bước CUỐI routing — rất hay gặp ngay sau khi vừa gộp bước in. */
  function gopLaBuocCuoi(): BaiGhepSoDo {
    const chung = gop({
      step_key: "gang-in",
      thanh_vien: [
        { lsx_id: 1, lsx_ma: "LSX-1", lsx_step_key: "a-in", ghi_chu_ky_thuat: null },
        { lsx_id: 2, lsx_ma: "LSX-2", lsx_step_key: "b-in", ghi_chu_ky_thuat: null },
      ],
    });
    return soDo({
      nhanh: [
        nhanh({
          lsx_id: 1, toa_step_key: "a-in", nhu_cau_to: 4000, du_to: 1075,
          buoc: [buoc({ step_key: "a-in", ten: "In A", gop_step_key: "gang-in" })],
        }),
        nhanh({
          lsx_id: 2, toa_step_key: "b-in", nhu_cau_to: 5075, du_to: 0,
          buoc: [buoc({ step_key: "b-in", ten: "In B", gop_step_key: "gang-in" })],
        }),
      ],
      gop: [chung],
    });
  }

  it("vẫn hiện khi bước gộp là bước cuối, dù không còn thẻ riêng nào để neo", () => {
    // Điều kiện cũ là "bước NGAY SAU điểm toả" — không có bước nào sau thì chip bốc hơi, dù
    // `du_to` khác 0. Số có mà màn hình câm.
    render(
      <BaiGhepDagCanvas sd={gopLaBuocCuoi()} chon={null} onChon={() => {}} />,
    );
    expect(screen.getByText(/\+\s*1[.,]075\s*tờ/)).toBeInTheDocument();
    expect(screen.getByText(/đủ tờ/)).toBeInTheDocument();   // lệnh quyết định số tờ của bài
  });
});

describe("xếp hàng & xếp cột", () => {
  it("sapHang kéo thành viên của một lượt chung nằm liền nhau", () => {
    // Bài 3 lệnh mà chỉ hàng 0 và hàng 2 gộp → thẻ chung trải qua hàng 1 và phủ mất thẻ của nó.
    const sd = soDo({
      nhanh: [1, 2, 3].map((id) =>
        nhanh({ lsx_id: id, buoc: [buoc({ step_key: `${id}-in` })] })),
      gop: [gop({
        step_key: "gang",
        thanh_vien: [
          { lsx_id: 1, lsx_ma: "LSX-1", lsx_step_key: "1-in", ghi_chu_ky_thuat: null },
          { lsx_id: 3, lsx_ma: "LSX-3", lsx_step_key: "3-in", ghi_chu_ky_thuat: null },
        ],
      })],
    });
    const thuTu = sapHang(sd);
    expect(new Set(thuTu)).toEqual(new Set([0, 1, 2]));       // không mất nhánh nào
    expect(Math.abs(thuTu.indexOf(0) - thuTu.indexOf(2))).toBe(1);
  });

  it("tinhCot đẩy cột theo cạnh CHÉO LỆNH, không chỉ theo thứ tự mảng", () => {
    // Bìa chờ ruột: thẻ bìa phải nằm bên PHẢI thẻ ruột, không thì dây nối chạy ngược.
    const sd = soDo({
      nhanh: [
        nhanh({ lsx_id: 1, buoc: [buoc({ step_key: "ruot-in" }), buoc({ step_key: "ruot-xen" })] }),
        nhanh({
          lsx_id: 2,
          buoc: [buoc({ step_key: "bia-vao", phu_thuoc_step_keys: ["ruot-xen"] })],
        }),
      ],
    });
    const { cot, hoiTu } = tinhCot(sd);
    expect(hoiTu).toBe(true);
    expect(cot["bia-vao"]).toBeGreaterThan(cot["ruot-xen"]);
  });

  it("tinhCot báo chưa hội tụ khi ràng buộc là vòng, thay vì lặng lẽ trả layout sai", () => {
    const sd = soDo({
      nhanh: [
        nhanh({ lsx_id: 1, buoc: [buoc({ step_key: "x", phu_thuoc_step_keys: ["y"] })] }),
        nhanh({ lsx_id: 2, buoc: [buoc({ step_key: "y", phu_thuoc_step_keys: ["x"] })] }),
      ],
    });
    expect(tinhCot(sd).hoiTu).toBe(false);
  });
});
