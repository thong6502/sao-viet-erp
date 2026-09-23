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

  // Số bàn giao nằm TRÊN đoạn ray ngay trước bước của tổ — đúng MỘT lần. Bản thẻ cũ in nó hai
  // lần ("Đã giao sang 5.220" ở ô nguồn + "Đã nhận 5.220 từ công đoạn trước" ở dòng dưới).
  it("số hàng đã nhận hiện đúng một lần, trên đoạn ray trước bước của tổ", () => {
    render(<ThsxDaiRouting dai={dai} />);
    const nhan = screen.getAllByText("5.220");
    expect(nhan).toHaveLength(1);
    expect(nhan[0]).toHaveAttribute("title", "Đã nhận từ công đoạn trước");
  });

  // "chờ giao" chỉ mọc khi bước của tổ ĐÃ XONG mà hàng chưa sang tổ sau — giục lúc bước còn đang
  // chạy là giục một việc chưa tới lượt.
  it("bước của tổ còn đang chạy thì chưa giục chờ giao", () => {
    render(<ThsxDaiRouting dai={dai} />);
    expect(screen.queryByText("chờ giao")).not.toBeInTheDocument();
  });

  it("bước của tổ xong rồi thì bước kế sau được đánh dấu chờ giao", () => {
    const xong = dai.map((b) => (b.la_cua_toi ? { ...b, trang_thai: "completed" } : b));
    render(<ThsxDaiRouting dai={xong} />);
    expect(screen.getByText("chờ giao").closest("li")).toHaveTextContent("Dán");
  });

  // Tổ thường ôm NHIỀU bước của cùng một lệnh (Tổ cắt: Cắt cuộn · Tề giấy · Cắt thành phẩm).
  // Bản đầu neo mọi thứ vào bước ĐẦU TIÊN của tổ nên dán "chờ giao" lên chính bước của mình.
  describe("tổ giữ nhiều bước của cùng lệnh", () => {
    const nhieu: SxRoutingBuoc[] = [
      buoc({ thu_tu: 1, step_key: "a", ten_cong_doan: "Cắt cuộn", to_ten: "Tổ cắt", la_cua_toi: true }),
      buoc({ thu_tu: 2, step_key: "b", ten_cong_doan: "Tề giấy", to_ten: "Tổ cắt", la_cua_toi: true }),
      buoc({ thu_tu: 3, step_key: "c", ten_cong_doan: "In", to_ten: "Nhóm in máy 4 màu",
             trang_thai: "released", thuc_te: 0 }),
      buoc({ thu_tu: 4, step_key: "d", ten_cong_doan: "Cắt thành phẩm", to_ten: "Tổ cắt",
             la_cua_toi: true, trang_thai: "released", thuc_te: 0, da_nhan: 1120 }),
      buoc({ thu_tu: 5, step_key: "e", ten_cong_doan: "Đóng gói", to_ten: "Tổ thành phẩm / KCS",
             trang_thai: "released", thuc_te: 0 }),
    ];

    it("chỉ đánh dấu chờ giao ở chỗ ĐỔI TỔ, không dán lên bước của chính mình", () => {
      render(<ThsxDaiRouting dai={nhieu} />);
      const cho = screen.getAllByText("chờ giao");
      expect(cho).toHaveLength(1);
      // Hàng rời tổ ở đoạn Tề giấy → In, nên nhãn nằm trên ô In chứ không phải ô Tề giấy.
      expect(cho[0].closest("li")).toHaveTextContent("In");
      expect(cho[0].closest("li")).not.toHaveTextContent("Tề giấy");
    });

    it("số đã nhận gắn vào bước NHẬN hàng từ tổ khác", () => {
      render(<ThsxDaiRouting dai={nhieu} />);
      const nhan = screen.getAllByText("1.120");
      expect(nhan).toHaveLength(1);
      expect(nhan[0].closest("li")).toHaveTextContent("Cắt thành phẩm");
    });

    it("nhấn đúng MỘT bước — bước đang tới tay tổ", () => {
      const { container } = render(<ThsxDaiRouting dai={nhieu} />);
      expect(container.querySelectorAll("[data-toi]")).toHaveLength(3);
      const tam = container.querySelectorAll("[data-tam]");
      expect(tam).toHaveLength(1);
      expect(tam[0]).toHaveTextContent("Cắt thành phẩm");
    });
  });

  it("lệnh một bước thì không vẽ dải", () => {
    const { container } = render(<ThsxDaiRouting dai={[dai[0]]} />);
    expect(container).toBeEmptyDOMElement();
  });

  // Bản trước cắt cửa sổ 5 ô rồi gom hai đầu thành "+N" — chuỗi 6 bước là mất luôn bước cuối,
  // đúng thứ tổ cần thấy nhất. Chuỗi thật có thể dài mười mấy công đoạn: để lưới xuống dòng,
  // KHÔNG giấu bước nào.
  it("dải dài mười mấy bước vẫn hiện đủ, không gom, không cuộn ngang", () => {
    const dai15 = Array.from({ length: 15 }, (_, i) =>
      buoc({ thu_tu: i + 1, step_key: `k${i}`, ten_cong_doan: `CĐ ${i + 1}`,
             la_cua_toi: i === 4 }));
    const { container } = render(<ThsxDaiRouting dai={dai15} />);
    for (let i = 1; i <= 15; i++) expect(screen.getByText(`CĐ ${i}`)).toBeInTheDocument();
    expect(container.querySelectorAll("li")).toHaveLength(15);
    expect(screen.queryByText(/^\+\d/)).not.toBeInTheDocument();
  });

  // Chốt cuối chuyền: ĐÚNG MỘT cái, và nằm ở ô cuối — dài bao nhiêu bước cũng vậy. Ray chạy hết
  // bề ngang ô cuối rồi đụng chốt; thiếu chốt thì đuôi ray thành đường lửng.
  it("chỉ ô cuối mang chốt kết thúc, chuỗi dài hay ngắn đều thế", () => {
    for (const n of [2, 4, 15]) {
      const chuoi = Array.from({ length: n }, (_, i) =>
        buoc({ thu_tu: i + 1, step_key: `c${i}`, ten_cong_doan: `CĐ ${i + 1}` }));
      const { container, unmount } = render(<ThsxDaiRouting dai={chuoi} />);
      const chot = container.querySelectorAll(".thsx-ray__chot");
      expect(chot).toHaveLength(1);
      expect(chot[0].closest("li")).toBe(container.querySelectorAll("li")[n - 1]);
      unmount();
    }
  });

  // Bước nhận đã chạy/đã xong ⇒ hàng rõ ràng đã sang rồi; dán "chờ giao" lên đó là nói ngược với
  // chính dấu ✓ nằm ngay cạnh.
  it("bước nhận đã xong thì thôi giục chờ giao", () => {
    const xong = dai.map((b) =>
      (b.la_cua_toi || b.ten_cong_doan === "Dán" ? { ...b, trang_thai: "completed" } : b));
    render(<ThsxDaiRouting dai={xong} />);
    expect(screen.queryByText("chờ giao")).not.toBeInTheDocument();
  });
});
