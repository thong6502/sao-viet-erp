// Màn Giao hàng — khoá hai thứ mà `tsc` và `vite build` KHÔNG bắt được:
//
//   1. "MỘT Ô = MỘT TAB" có thật ở giao diện chưa. Đây là luật chốt 15/08/2026 và đã cắn một lần
//      rồi: cấp ô rồi mà tab không hiện, hoặc tệ hơn — tab hiện cho người không có ô. Cả hai
//      chiều đều phải test, vì `can()` trả `false` mặc định nên chiều "thiếu ô ⇒ ẩn" luôn xanh
//      kể cả khi dây bị đứt hoàn toàn.
//   2. Khoảng trống nói được BƯỚC TIẾP THEO. Bảng rỗng chỉ nói "hết chuyện"; người mở màn lần đầu
//      không biết yêu cầu giao đẻ ra từ đâu.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import GiaoHangPage from "./GiaoHangPage";
import { AuthContext, type AuthState } from "../../../auth/AuthContext";
import { PermissionsProvider, buildCapabilities } from "../../../auth/permissions";
import type { ModuleCapability } from "../../../api/client";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

/** Ô quyền của màn Giao hàng — chỉ bật đúng những cờ truyền vào. */
function caps(o: Partial<ModuleCapability>) {
  return buildCapabilities([
    { module_key: "giao_hang", scope: "all", can_read: true, ...o } as ModuleCapability,
  ]);
}

const CHUYEN = {
  id: 1, request_id: 7, request_code: "YCGH-260819-A1B2", order_id: 3, order_code: "DH-GH-01",
  customer_name: "Công ty Bánh kẹo Minh Long", lan_thu: 1, employee_id: 5,
  employee_name: "Trần Văn Hùng",
  gio_lay_hang: "2026-08-20T01:00:00Z", gio_du_kien_giao: "2026-08-20T04:00:00Z",
  ghi_chu_phan_cong: null, trang_thai: "dang_giao", km: null, thoi_gian_ket_thuc: null,
  nguoi_nhan_thuc_te: null, ly_do_that_bai: null, huong_xu_ly: null, ngay_hen_lai: null,
  ghi_chu_ket_qua: null, lines: [], yeu_cau_kho_ma: "DNX0007",
  yeu_cau_kho_trang_thai: "approved",
};

const YEU_CAU = {
  id: 7, code: "YCGH-260819-A1B2", order_id: 3, order_code: "DH-GH-03", customer_id: 1,
  customer_name: "Dược phẩm Sao Mai", department_id: 1, ngay_can_giao: "2026-08-26",
  dia_chi: "Lô C3", nguoi_nhan: "Chị Hạnh", sdt_nguoi_nhan: "0938765432", ghi_chu: null,
  trang_thai: "dang_thuc_hien", ly_do_huy: null, created_by: 1, created_by_name: "Admin",
  created_at: "2026-08-19T10:00:00Z", lines: [], so_lan_giao: 1, trang_thai_lsx: [],
};

function stubApi({ trips = [], requests = [], drivers = [], taiXe }: {
  trips?: unknown[]; requests?: unknown[]; drivers?: unknown[]; taiXe?: unknown[];
}) {
  const goi: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const p = String(url);
    goi.push({ url: p, body: init?.body ? JSON.parse(String(init.body)) : null });
    // Chi tiết MỘT yêu cầu — `/requests/7`, phải bắt TRƯỚC `/requests` chung, và phải đúng
    // hình dạng `{request, trips, lich_su}`. Bản đầu trả `{items: []}` nên dialog `.catch` nuốt
    // mất, test xanh mà không chứng minh gì.
    const body = /\/requests\/\d+/.test(p)
      ? {
          request: {
            ...YEU_CAU,
            lines: [
              { id: 1, order_line_id: 11, qty: 119, mo_ta: "Hộp thuốc 10 vỉ",
                don_vi_tinh: "hộp", da_giao: 0 },
              { id: 2, order_line_id: 12, qty: 119, mo_ta: "Tờ hướng dẫn",
                don_vi_tinh: "tờ", da_giao: 0 },
            ],
          },
          trips: [],
          lich_su: [],
        }
      : p.includes("/con-phai-giao")
      ? { order_id: 3, da_giao_du: false,
          lines: [{ order_line_id: 11, mo_ta: "Hộp giấy", don_vi_tinh: "hộp",
                    qty_dat: 100, da_giao: 0, con_phai_giao: 40 }] }
      : p.includes("/tai-xe-chon")
        ? { items: taiXe ?? [{ id: 5, code: "NVGH01", full_name: "Trần Văn Hùng",
                               department: "Kho", co_tai_khoan: true, co_thao_tac: true }] }
        : p.includes("/trips") ? { items: trips }
          : p.includes("/requests") ? { items: requests }
            : p.includes("/nhan-vien") ? { items: drivers }
              : {};
    return Promise.resolve({
      ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
      json: async () => body, text: async () => JSON.stringify(body),
    } as Response);
  }));
  return goi;
}

function ve(o: Partial<ModuleCapability>) {
  return render(
    <AuthContext.Provider value={AUTH}>
      <PermissionsProvider caps={caps(o)}>
        <GiaoHangPage />
      </PermissionsProvider>
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("Giao hàng · một ô = một tab", () => {
  it("chỉ có ô Xem ⇒ đúng MỘT tab", async () => {
    stubApi({});
    ve({});
    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(1));
    expect(screen.getByRole("tab", { name: /Đơn giao hàng/ })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Yêu cầu giao/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Nhân viên giao hàng/ })).not.toBeInTheDocument();
  });

  it("tên tab đúng như đã chốt: Đơn giao hàng · Yêu cầu giao · Nhân viên giao hàng", async () => {
    stubApi({});
    ve({ can_plan: true, can_view_drivers: true });
    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(3));
    const ten = screen.getAllByRole("tab").map((t) => t.textContent?.replace(/\d+$/, "").trim());
    expect(ten).toEqual(["Đơn giao hàng", "Yêu cầu giao", "Nhân viên giao hàng"]);
  });

  it("⭐ bật ô Lên kế hoạch ⇒ tab đó HIỆN RA", async () => {
    // Chiều khẳng định mới bắt được dây đứt: `can()` mặc định false nên chiều phủ định
    // luôn xanh, kể cả khi cột không bao giờ tới được frontend.
    stubApi({});
    ve({ can_plan: true });
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Yêu cầu giao/ })).toBeInTheDocument());
    expect(screen.queryByRole("tab", { name: /Nhân viên giao hàng/ })).not.toBeInTheDocument();
  });

  it("⭐ bật ô Nhân viên giao hàng ⇒ tab đó HIỆN RA", async () => {
    stubApi({});
    ve({ can_view_drivers: true });
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Nhân viên giao hàng/ })).toBeInTheDocument());
  });

  it("không có ô Nhân viên giao hàng thì KHÔNG gọi API tab đó", async () => {
    // Gọi rồi nuốt 403 là che mất lỗi cấu hình thật, và tốn một vòng mạng vô ích.
    const goi = stubApi({});
    ve({ can_plan: true });
    await waitFor(() => expect(goi.some((g) => g.url.includes("/trips"))).toBe(true));
    expect(goi.some((g) => g.url.includes("/nhan-vien"))).toBe(false);
  });
});

describe("Giao hàng · khoảng trống nói được bước tiếp theo", () => {
  it("chưa có chuyến nào ⇒ chỉ đường về màn Đơn hàng bán", async () => {
    stubApi({});
    ve({});
    await waitFor(() =>
      expect(screen.getByText("Chưa có đơn giao hàng nào")).toBeInTheDocument());
    expect(screen.getByText(/Đơn hàng bán/)).toBeInTheDocument();
  });
});

describe("Giao hàng · bảng kế hoạch", () => {
  it("hiện đủ mã yêu cầu, khách, tài xế và trạng thái đọc được", async () => {
    stubApi({ trips: [CHUYEN] });
    ve({});
    await waitFor(() => expect(screen.getByText("YCGH-260819-A1B2")).toBeInTheDocument());
    expect(screen.getByText("Công ty Bánh kẹo Minh Long")).toBeInTheDocument();
    expect(screen.getByText("Trần Văn Hùng")).toBeInTheDocument();
    // Trạng thái phải là TIẾNG VIỆT, không phải khoá kỹ thuật `dang_giao`.
    expect(screen.getByText("Đang giao")).toBeInTheDocument();
    expect(screen.queryByText("dang_giao")).not.toBeInTheDocument();
  });

  it("chuyến đang giao mà KHÔNG có ô Thao tác ⇒ không bày nút Nhập kết quả", async () => {
    // Bày nút rồi bấm ăn 403 trông như hệ thống hỏng, chứ không như "anh không có quyền".
    stubApi({ trips: [CHUYEN] });
    ve({});
    await waitFor(() => expect(screen.getByText("YCGH-260819-A1B2")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Nhập kết quả/ })).not.toBeInTheDocument();
  });

  it("có ô Thao tác ⇒ nút Nhập kết quả hiện ra", async () => {
    stubApi({ trips: [CHUYEN] });
    ve({ can_create: true });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Nhập kết quả/ })).toBeInTheDocument());
  });
});

describe("Giao hàng · không để chuyến nào tắc", () => {
  // Mỗi trạng thái "đang chạy" phải có ĐÚNG một nút đưa nó đi tiếp. Thiếu một nút thì chuyến
  // nằm lại đó vĩnh viễn — API có mà giao diện quên là loại lỗi không ai báo, chỉ thấy "đơn này
  // sao mãi chưa xong".
  const buoc: [string, RegExp][] = [
    ["dang_chuan_bi", /Đã lấy hàng/],
    ["da_lay_hang", /Bắt đầu giao/],
    ["dang_giao", /Nhập kết quả/],
    ["dang_tra_hang", /Kho đã nhận lại/],
  ];
  for (const [tt, nut] of buoc) {
    it(`trạng thái ${tt} có nút đi tiếp`, async () => {
      stubApi({ trips: [{ ...CHUYEN, trang_thai: tt }] });
      ve({ can_create: true });
      expect(await screen.findByRole("button", { name: nut })).toBeInTheDocument();
    });
  }
});

describe("Giao hàng · yêu cầu xuất kho là chứng từ CỦA KHO", () => {
  it("⭐ chưa gửi ⇒ hiện nút Gửi yêu cầu xuất kho", async () => {
    // Hàng ra khỏi kho phải có phiếu kho — giao khách không ngoại lệ. Ba bản trước đều lách
    // (tự sinh · chứng từ song song · bỏ hẳn phiếu), chủ chốt bắt ba lần mới sửa (19/08/2026).
    stubApi({ trips: [{ ...CHUYEN, trang_thai: "da_len_ke_hoach", yeu_cau_kho_ma: null }] });
    ve({ can_plan: true });
    expect(await screen.findByRole("button", { name: /Gửi yêu cầu xuất kho/ }))
      .toBeInTheDocument();
  });

  it("⭐ đã gửi rồi ⇒ KHÔNG bày lại nút", async () => {
    // Gửi hai lần là hai chứng từ kho cho một chuyến — kho soạn hàng hai lượt.
    stubApi({ trips: [{ ...CHUYEN, trang_thai: "da_len_ke_hoach" }] });
    ve({ can_plan: true });
    await waitFor(() => expect(screen.getByText("YCGH-260819-A1B2")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Gửi yêu cầu xuất kho/ })).not.toBeInTheDocument();
  });

  it("mã DNX KHÔNG bày ở cột Thao tác", async () => {
    // Nó không phải thao tác, không có nhãn, đứng cạnh nút thì trông như một nút hỏng
    // (chủ chốt 20/08/2026). Mã vẫn còn ở chi tiết yêu cầu, chỗ có ngữ cảnh để đọc.
    stubApi({ trips: [{ ...CHUYEN, trang_thai: "da_len_ke_hoach" }] });
    ve({ can_plan: true });
    await waitFor(() => expect(screen.getByText("YCGH-260819-A1B2")).toBeInTheDocument());
    expect(screen.queryByText("DNX0007")).toBeNull();
  });

  it("không có ô Lên kế hoạch ⇒ không gửi được", async () => {
    stubApi({ trips: [{ ...CHUYEN, trang_thai: "da_len_ke_hoach", yeu_cau_kho_ma: null }] });
    ve({ can_create: true });
    await waitFor(() => expect(screen.getByText("YCGH-260819-A1B2")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Gửi yêu cầu xuất kho/ })).not.toBeInTheDocument();
  });
});

describe("Giao hàng · một yêu cầu = MỘT dòng", () => {
  const LAN1 = { ...CHUYEN, id: 1, lan_thu: 1, trang_thai: "giao_thieu", km: 10,
                 gio_lay_hang: "2026-08-21T08:38:00Z" };
  const LAN2 = { ...CHUYEN, id: 2, lan_thu: 2, trang_thai: "thanh_cong", km: 200,
                 gio_lay_hang: "2026-08-29T08:39:00Z" };

  it("⭐ dữ liệu CŨ có hai chuyến một yêu cầu ⇒ vẫn CHỈ một dòng", async () => {
    // Từ 22/08/2026 một yêu cầu chỉ có MỘT chuyến (chặn ở service + chỉ số UNIQUE mg 0229), nên
    // cảnh này chỉ còn ở dữ liệu gieo TRƯỚC ngày đó. Bảng vẫn phải gộp về một dòng, không hiện
    // hai dòng trùng mã trùng khách.
    //
    // Nhãn "2 lần giao" đã bỏ cùng lượt: đếm một thứ luôn bằng 1 là bắt người đọc hỏi vì sao.
    stubApi({ trips: [LAN2, LAN1] });
    ve({});
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "YCGH-260819-A1B2" })).toHaveLength(1));
    expect(screen.queryByText("2 lần giao")).not.toBeInTheDocument();
  });

  it("⭐ cột Km là TỔNG cả các lần, không phải km lần cuối", async () => {
    // PRD §9: lần 1 thất bại 18km + lần 2 thành công 22km ⇒ tổng quãng đường 40km.
    stubApi({ trips: [LAN2, LAN1] });
    ve({});
    await waitFor(() => expect(screen.getByText("210")).toBeInTheDocument());
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });

  it("dòng hiện trạng thái của lần MỚI NHẤT", async () => {
    stubApi({ trips: [LAN2, LAN1] });
    ve({});
    await waitFor(() => expect(screen.getByText("Giao thành công")).toBeInTheDocument());
    expect(screen.queryByText("Giao thiếu")).not.toBeInTheDocument();
  });
});

describe("Giao hàng · ô kết quả phải hiện SỐ LƯỢNG", () => {
  async function moKetQua(kq?: string) {
    stubApi({ trips: [CHUYEN] });
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Nhập kết quả/ }));
    if (kq) await userEvent.selectOptions(await screen.findByLabelText(/^Kết quả/), kq);
  }

  it("⭐ Giao thành công vẫn hiện số lượng của TỪNG dòng hàng", async () => {
    // Trước đây chọn "Giao thành công" là máy tự điền, người bấm không thấy mình xác nhận bao
    // nhiêu — mà đó là con số cộng thẳng vào "đã giao" của đơn.
    await moKetQua();
    const o1 = await screen.findByLabelText(/Số thực nhận — Hộp thuốc/);
    const o2 = screen.getByLabelText(/Số thực nhận — Tờ hướng dẫn/);
    expect(o1).toHaveValue(119);
    expect(o2).toHaveValue(119);
    // Thành công = nhận đủ ⇒ khoá ô; muốn sửa số thì đổi kết quả sang Giao thiếu.
    expect(o1).toBeDisabled();
  });

  it("Giao thiếu ⇒ mở khoá ô để sửa", async () => {
    await moKetQua("giao_thieu");
    expect(await screen.findByLabelText(/Số thực nhận — Hộp thuốc/)).toBeEnabled();
  });

  it("⭐ gửi giao thiếu phải kèm ĐỦ HAI dòng hàng, không chỉ dòng đầu", async () => {
    // Bản đầu chỉ gửi `lines[0]` — đơn hai mặt hàng là ghi thiếu hẳn một dòng, không ai báo.
    const goi = stubApi({ trips: [CHUYEN] });
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Nhập kết quả/ }));
    await userEvent.selectOptions(await screen.findByLabelText(/^Kết quả/), "giao_thieu");

    const o1 = await screen.findByLabelText(/Số thực nhận — Hộp thuốc/);
    await userEvent.clear(o1);
    await userEvent.type(o1, "60");
    await userEvent.type(screen.getByLabelText(/Số km thực tế/), "22");
    await userEvent.type(screen.getByLabelText(/Người nhận hàng/), "Chị Hạnh");
    await userEvent.click(screen.getByRole("button", { name: /Lưu kết quả/ }));

    const post = goi.find((g) => g.url.includes("/ket-qua"));
    expect(post).toBeTruthy();
    const body = post!.body as { so_thuc_nhan: { order_line_id: number; qty: number }[] };
    expect(body.so_thuc_nhan).toEqual([
      { order_line_id: 11, qty: 60 },
      { order_line_id: 12, qty: 119 },
    ]);
  });
});

describe("Giao hàng · KHO LẬP PHIẾU ⇒ \"Kho đã chuẩn bị xong\"", () => {
  // Chủ chốt 20/08/2026. Kho KHÔNG bấm gì trên màn Giao hàng — họ lập phiếu bên màn của họ, và
  // chữ ở đây đổi theo sổ kho (`kho_da_lap_phieu` suy từ `stock_vouchers`, không phải cột lưu).
  const dangChuanBi = { ...CHUYEN, trang_thai: "dang_chuan_bi" };

  it("chưa lập phiếu ⇒ vẫn là \"Kho đang chuẩn bị\"", async () => {
    stubApi({ trips: [{ ...dangChuanBi, kho_da_lap_phieu: false }] });
    ve({ can_read: true });
    expect(await screen.findByText("Kho đang chuẩn bị")).toBeInTheDocument();
    expect(screen.queryByText("Kho đã chuẩn bị xong")).toBeNull();
  });

  it("⭐ lập phiếu rồi ⇒ đổi thành \"Kho đã chuẩn bị xong\"", async () => {
    // Tài xế nhìn dòng này để biết có nên đi lấy hàng chưa — sai chữ là đi không.
    stubApi({ trips: [{ ...dangChuanBi, kho_da_lap_phieu: true }] });
    ve({ can_read: true });
    expect(await screen.findByText("Kho đã chuẩn bị xong")).toBeInTheDocument();
  });

  it("cờ chỉ đổi chữ ở ĐÚNG bước chuẩn bị, không tràn sang bước khác", async () => {
    // `dang_giao` mà cũng đổi chữ thì tài xế đang trên đường lại thấy "Kho đã chuẩn bị xong".
    stubApi({ trips: [{ ...CHUYEN, trang_thai: "dang_giao", kho_da_lap_phieu: true }] });
    ve({ can_read: true });
    expect(await screen.findByText("Đang giao")).toBeInTheDocument();
    expect(screen.queryByText("Kho đã chuẩn bị xong")).toBeNull();
  });
});

describe("Giao hàng · KM ngày và KM tháng là HAI cột", () => {
  const NV = {
    employee_id: 5, ho_ten: "Trần Văn Hùng", trang_thai: "ranh",
    chuyen_dang_thuc_hien: null, chuyen_ke_tiep: null,
    so_chuyen_xong: 1, tong_km: 12, so_chuyen_thang: 9, tong_km_thang: 340,
  };

  it("⭐ hiện ĐỦ cả hai con số, không gộp làm một", async () => {
    // Hai khung thời gian trả lời hai câu khác nhau: ngày để điều độ ("giờ ai đang rảnh"),
    // tháng để theo dõi định kỳ (chủ chốt 20/08/2026). Gộp một cột là mất một trong hai.
    stubApi({ drivers: [NV] });
    ve({ can_read: true, can_view_drivers: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Nhân viên giao hàng/ }));
    expect(await screen.findByText("340")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("⭐ đổi THÁNG ⇒ gọi lại API kèm tham số tháng", async () => {
    // Thiếu `thang` trong deps của `load` thì đổi tháng mà bảng đứng im — người dùng tưởng
    // tháng sau không có gì (chủ chốt 20/08/2026: "tôi muốn xem tháng sau như nào").
    const goi = stubApi({ drivers: [NV] });
    ve({ can_read: true, can_view_drivers: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Nhân viên giao hàng/ }));

    const o = await screen.findByLabelText(/Tháng/);
    fireEvent.change(o, { target: { value: "2026-09" } });
    await waitFor(() =>
      expect(goi.some((g) => g.url.includes("thang=2026-09"))).toBe(true));
  });

  it("hết người trong tháng đang xem ⇒ VẪN còn ô chọn tháng để quay lại", async () => {
    // Ẩn ô chọn lúc bảng rỗng là nhốt người dùng ở đúng cái tháng trống.
    stubApi({ drivers: [] });
    ve({ can_read: true, can_view_drivers: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Nhân viên giao hàng/ }));
    expect(await screen.findByLabelText(/Tháng/)).toBeInTheDocument();
  });

  it("thiếu số tháng (bản cũ của máy chủ) ⇒ hiện 0, không vỡ", async () => {
    // Máy chủ chưa deploy mà FE đã lên thì `so_chuyen_thang` vắng — hiện "undefined" thì xấu,
    // mà crash thì mất cả bảng.
    const { so_chuyen_thang: _a, tong_km_thang: _b, ...cu } = NV;
    stubApi({ drivers: [cu] });
    ve({ can_read: true, can_view_drivers: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Nhân viên giao hàng/ }));
    expect(await screen.findByText("Trần Văn Hùng")).toBeInTheDocument();
  });
});

describe("Giao hàng · cảnh báo tài xế chưa bấm nút được", () => {
  // Chủ chốt hỏi "là sao chưa hiểu cái này lắm" (20/08/2026) — câu cũ gộp HAI tình huống vào
  // một, nên không chỉ được đi đâu sửa. Giờ tách: chưa có TÀI KHOẢN vs thiếu ô THAO TÁC.
  const YC = {
    id: 7, code: "YCGH-260819-A1B2", order_id: 3, order_code: "DH-GH-03",
    customer_name: "Dược phẩm Sao Mai", ngay_can_giao: "2026-08-26", dia_chi: "Lô C3",
    trang_thai: "cho_len_ke_hoach", lines: [], so_lan_giao: 0, trang_thai_lsx: [],
    created_at: "2026-08-19T10:00:00Z",
  };

  async function moLenKeHoach(taiXe: unknown[]) {
    stubApi({ requests: [YC], taiXe });
    ve({ can_plan: true, can_read: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Yêu cầu giao/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Lên đơn giao hàng/ }));
    await userEvent.selectOptions(await screen.findByLabelText(/Nhân viên giao/), "9");
  }

  it("⭐ chưa có TÀI KHOẢN ⇒ nói đúng thiếu tài khoản", async () => {
    await moLenKeHoach([{ id: 9, code: "NV9", full_name: "Tài Xế A", department: "Giao hàng",
                          co_tai_khoan: false, co_thao_tac: false }]);
    const canh = await screen.findByRole("status");
    expect(canh).toHaveTextContent(/chưa có tài khoản/i);
    expect(canh).toHaveTextContent(/bấm hộ/i);
  });

  it("⭐ có tài khoản nhưng THIẾU Ô THAO TÁC ⇒ nói đúng thiếu quyền", async () => {
    await moLenKeHoach([{ id: 9, code: "NV9", full_name: "Tài Xế B", department: "Giao hàng",
                          co_tai_khoan: true, co_thao_tac: false }]);
    const canh = await screen.findByRole("status");
    expect(canh).toHaveTextContent(/chưa được cấp quyền thao tác/i);
    expect(canh).toHaveTextContent(/bấm hộ/i);
  });

  it("đủ ô Thao tác ⇒ KHÔNG doạ gì cả", async () => {
    await moLenKeHoach([{ id: 9, code: "NV9", full_name: "Tài Xế C", department: "Giao hàng",
                          co_tai_khoan: true, co_thao_tac: true }]);
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("Giao hàng · cột Hàng hoá chỉ ĐẾM", () => {
  // Đổ cả danh sách ra bảng làm dòng cao gấp ba và đẩy cột Thao tác ra rìa — mà tên sản phẩm in
  // vốn đã dài ("Hộp thuốc 10 vỉ — in 2 màu, cán bóng"). Chủ chốt 20/08/2026: chỉ hiện số, muốn
  // xem gì thì bấm mã yêu cầu mở chi tiết.
  const YC2 = {
    id: 7, code: "YCGH-260819-A1B2", order_id: 3, order_code: "DH-GH-03",
    customer_name: "Dược phẩm Sao Mai", ngay_can_giao: "2026-08-26", dia_chi: "Lô C3",
    trang_thai: "cho_len_ke_hoach", so_lan_giao: 0, trang_thai_lsx: [],
    created_at: "2026-08-19T10:00:00Z",
    lines: [
      { id: 1, order_line_id: 11, qty: 1200, mo_ta: "Hộp thuốc 10 vỉ — in 2 màu, cán bóng",
        don_vi_tinh: "hộp", da_giao: 0 },
      { id: 2, order_line_id: 12, qty: 1200, mo_ta: "Tờ hướng dẫn sử dụng — gấp 3",
        don_vi_tinh: "tờ", da_giao: 0 },
    ],
  };

  it("⭐ hiện SỐ mặt hàng, KHÔNG liệt kê tên ra bảng", async () => {
    stubApi({ requests: [YC2] });
    ve({ can_plan: true, can_read: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Yêu cầu giao/ }));
    expect(await screen.findByText("2 mặt hàng")).toBeInTheDocument();
    expect(screen.queryByText(/Hộp thuốc 10 vỉ — in 2 màu, cán bóng ×/)).toBeNull();
  });
});

describe("Giao hàng · khung trang", () => {
  it("⭐ gốc màn phải mang class khung `.rc` — thiếu là nội dung dán sát hai mép", async () => {
    // Bản đầu để gốc là `.kho-list` (mượn của ba màn Kho). Class đó CHỈ chỉnh bảng, không mang
    // layout — ba màn Kho không lộ ra vì `KhoPage` đã bọc `.rc` sẵn, còn màn này do AppShell
    // dựng thẳng nên không có ai bọc hộ. `tsc` và `vite build` đều xanh, mắt mới thấy.
    stubApi({});
    const { container } = ve({});
    await waitFor(() =>
      expect(screen.getByText("Chưa có đơn giao hàng nào")).toBeInTheDocument());
    const goc = container.firstElementChild;
    expect(goc?.tagName).toBe("MAIN");
    expect(goc).toHaveClass("rc");
  });
});

describe("Giao hàng · ô số phải là ô SỐ", () => {
  it("⭐ ô km là input số, không phải ô chữ", async () => {
    // `inputMode="numeric"` CHỈ đổi bàn phím điện thoại — trên máy tính gõ chữ vẫn lọt vào.
    // Bản đầu dùng đúng cái đó và người dùng gõ được "ưe" vào ô số lượng.
    stubApi({ trips: [CHUYEN] });
    ve({ can_create: true });
    const nut = await screen.findByRole("button", { name: /Nhập kết quả/ });
    await userEvent.click(nut);
    const o = await screen.findByLabelText(/Số km thực tế/);
    expect(o).toHaveAttribute("type", "number");
    expect(o).toHaveAttribute("min", "0");   // 0 km là số THẬT, đừng đổi thành 1
  });

  it("⭐ chọn tài xế bằng danh sách, không bắt gõ mã", async () => {
    // Gõ mã nhân viên thì sai một chữ số là phân công nhầm người, không có gì báo.
    stubApi({ requests: [], trips: [] });
    ve({ can_plan: true });
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Yêu cầu giao/ })).toBeInTheDocument());
    expect(screen.queryByLabelText(/Mã nhân viên/)).not.toBeInTheDocument();
  });
});
