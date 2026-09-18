// Màn Giao hàng — khoá hai thứ mà `tsc` và `vite build` KHÔNG bắt được:
//
//   1. "MỘT Ô = MỘT TAB" có thật ở giao diện chưa. Đây là luật chốt 15/08/2026 và đã cắn một lần
//      rồi: cấp ô rồi mà tab không hiện, hoặc tệ hơn — tab hiện cho người không có ô. Cả hai
//      chiều đều phải test, vì `can()` trả `false` mặc định nên chiều "thiếu ô ⇒ ẩn" luôn xanh
//      kể cả khi dây bị đứt hoàn toàn.
//   2. Khoảng trống nói được BƯỚC TIẾP THEO. Bảng rỗng chỉ nói "hết chuyện"; người mở màn lần đầu
//      không biết yêu cầu giao đẻ ra từ đâu.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

function stubApi({ trips = [], khoi = [], requests = [], drivers = [], taiXe, xe = [], luotMo = [],
                   rieng }: {
  /** Chuyến LẺ (ngoài lượt) và khối LƯỢT XE — hai loại khối của `/bang-giao`. */
  trips?: unknown[]; khoi?: { diem: unknown[] }[];
  requests?: unknown[]; drivers?: unknown[]; taiXe?: unknown[];
  /** Danh mục Xe giao hàng (`/api/xe`) và lượt đang mở của xe (`/luot-xe`) — lượt xe 18/09/2026. */
  xe?: unknown[]; luotMo?: unknown[];
  /** Trả lời RIÊNG cho một URL (vd POST bat-dau-giao kèm cảnh báo). `undefined` = đi nhánh chung. */
  rieng?: (url: string) => unknown;
}) {
  const goi: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const p = String(url);
    goi.push({ url: p, body: init?.body ? JSON.parse(String(init.body)) : null });
    const traRieng = rieng?.(p);
    // Chi tiết MỘT yêu cầu — `/requests/7`, phải bắt TRƯỚC `/requests` chung, và phải đúng
    // hình dạng `{request, trips, lich_su}`. Bản đầu trả `{items: []}` nên dialog `.catch` nuốt
    // mất, test xanh mà không chứng minh gì.
    const body = traRieng !== undefined ? traRieng
      : /\/requests\/\d+/.test(p)
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
      // Danh mục Xe (12/09/2026): hai hộp Lên đơn / Ghi kết quả nạp ô Xe từ `/api/xe`. Thiếu
      // nhánh này thì stub trả `{}` ⇒ `items` undefined ⇒ hộp thoại vỡ ngay lúc vẽ.
      : p.includes("/api/xe") ? { items: xe, total: xe.length }
      : p.includes("/luot-xe?") ? { items: luotMo }
      : p.includes("/con-phai-giao")
      ? { order_id: 3, da_giao_du: false,
          lines: [{ order_line_id: 11, mo_ta: "Hộp giấy", don_vi_tinh: "hộp",
                    qty_dat: 100, da_giao: 0, con_phai_giao: 40 }] }
      : p.includes("/tai-xe-chon")
        ? { items: taiXe ?? [{ id: 5, code: "NVGH01", full_name: "Trần Văn Hùng",
                               department: "Kho", co_tai_khoan: true, co_thao_tac: true }] }
        : p.includes("/bang-giao")
          ? { items: [...khoi.map((l) => ({ luot: l, trip: null })),
                      ...trips.map((t) => ({ luot: null, trip: t }))],
              total: khoi.length + trips.length,
              so_don: khoi.reduce((n, l) => n + l.diem.length, 0) + trips.length }
        : p.includes("/trips") ? { items: trips, total: trips.length }
          : p.includes("/requests") ? { items: requests, total: requests.length }
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
    await waitFor(() => expect(goi.some((g) => g.url.includes("/bang-giao"))).toBe(true));
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
  // Gộp theo yêu cầu (lấy lần MỚI NHẤT + cộng km cả các lần) nay làm ở MÁY CHỦ
  // (`delivery_repo._loc_chuyen`/`tong_km_theo_yeu_cau`, xem `test_09b_...` bên backend) — FE chỉ
  // còn việc HIỂN THỊ đúng những gì `/trips` trả về, nên stub thẳng MỘT dòng đã gộp sẵn, đúng
  // hình dạng API thật (PRD §9: 18km lần hỏng + 22km lần thành công ⇒ `tong_km` 40, ở đây dùng
  // 10 + 200 = 210 để tách bạch với `km` riêng của lần cuối).
  const DA_GOP = { ...CHUYEN, lan_thu: 2, trang_thai: "thanh_cong", km: 200, tong_km: 210 };

  it("⭐ cột Km hiện TỔNG cả các lần máy chủ gộp, không phải km lần cuối", async () => {
    stubApi({ trips: [DA_GOP] });
    ve({});
    await waitFor(() => expect(screen.getByText("210")).toBeInTheDocument());
    expect(screen.queryByText("200")).not.toBeInTheDocument();
  });

  it("dòng hiện trạng thái của lần MỚI NHẤT do máy chủ trả về", async () => {
    stubApi({ trips: [DA_GOP] });
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

describe("Giao hàng · LƯỢT XE — lên đơn vào lượt (PRD khoán km §14)", () => {
  // Chủ chốt 18/09/2026: tài xế ghi số đồng hồ lúc đi, lúc tới từng khách, lúc về kho — máy tự
  // trừ ra km TỪNG CHẶNG rồi tra đơn giá theo chặng. Người lên đơn quyết đơn nào chung một lượt.
  const XE = { id: 3, ma: "51D-853.66", ten: "Xe tải 3.5T", tai_trong: 3.5, active: true };
  const YC = {
    id: 7, code: "YCGH-260819-A1B2", order_id: 3, order_code: "DH-GH-03",
    customer_name: "Dược phẩm Sao Mai", ngay_can_giao: "2026-09-18", dia_chi: "Lô C3",
    trang_thai: "cho_len_ke_hoach", lines: [], so_lan_giao: 0, trang_thai_lsx: [],
    created_at: "2026-09-18T01:00:00Z",
  };

  async function lenDon(luotMo: unknown[]) {
    const goi = stubApi({
      requests: [YC], xe: [XE], luotMo,
      rieng: (u) => (u.endsWith("/plans") ? { trip: CHUYEN, canh_bao: [] } : undefined),
    });
    ve({ can_plan: true, can_read: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Yêu cầu giao/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Lên đơn giao hàng/ }));
    await userEvent.selectOptions(await screen.findByLabelText(/Nhân viên giao/), "5");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: /51D-853\.66/ })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText(/^Xe/), "3");
    fireEvent.change(screen.getByLabelText(/Giờ lấy hàng/), { target: { value: "2026-09-18T08:00" } });
    fireEvent.change(screen.getByLabelText(/Giờ dự kiến giao/), { target: { value: "2026-09-18T10:00" } });
    return goi;
  }

  it("⭐ chọn xe ⇒ hiện ô Lượt xe, mặc định LƯỢT MỚI và gửi `luot_xe_id: \"moi\"`", async () => {
    const goi = await lenDon([]);
    expect(await screen.findByLabelText(/Lượt xe/)).toHaveValue("moi");
    await userEvent.click(screen.getByRole("button", { name: /Lưu kế hoạch/ }));
    await waitFor(() => expect(goi.some((g) => g.url.endsWith("/plans"))).toBe(true));
    const body = goi.find((g) => g.url.endsWith("/plans"))!.body as Record<string, unknown>;
    expect(body.vehicle_id).toBe(3);
    expect(body.luot_xe_id).toBe("moi");
  });

  it("⭐ ghép vào lượt ĐANG MỞ của xe đó ⇒ gửi id lượt", async () => {
    const goi = await lenDon([{ id: 4, code: "LX-260918-AB12", ngay: "2026-09-18", so_diem: 1,
                               tai_xe: "Trần Văn Hùng", da_xuat_phat: false }]);
    const o = await screen.findByLabelText(/Lượt xe/);
    await waitFor(() =>
      expect(within(o).getByRole("option", { name: /LX-260918-AB12/ })).toBeInTheDocument());
    await userEvent.selectOptions(o, "4");
    await userEvent.click(screen.getByRole("button", { name: /Lưu kế hoạch/ }));
    await waitFor(() => expect(goi.some((g) => g.url.endsWith("/plans"))).toBe(true));
    const body = goi.find((g) => g.url.endsWith("/plans"))!.body as Record<string, unknown>;
    expect(body.luot_xe_id).toBe(4);
    // Lượt của xe NÀO thì hỏi đúng xe đó — lượt là vòng chạy của một chiếc xe.
    expect(goi.some((g) => g.url.includes("/luot-xe?vehicle_id=3"))).toBe(true);
  });
});

describe("Giao hàng · MỘT LƯỢT = MỘT KHỐI trên tab Đơn giao hàng (chủ chốt 18/09/2026)", () => {
  // "Ghép nhiều yêu cầu mà hiện rời từng dòng thì tài xế với người lên đơn khó hiểu quá." Nay mỗi
  // lượt là một khối: đầu (mã · trạng thái · km · nút bước kế tiếp) · tóm tắt (xe · kíp · khách).
  // MẶC ĐỊNH KHÉP ("sổ ra cả vậy xấu quá") — mở ra mới thấy thanh 5 bước và các điểm.
  const LUOT_DIEM = {
    id: 4, code: "LX-260918-AB12", vehicle_id: 3, ngay: "2026-09-18", so_diem: 2,
    so_dong_ho_xuat_phat: null, so_dong_ho_ve_kho: null, ve_kho_luc: null, km_ve_kho: null,
    so_dong_ho: null, so_dong_ho_gan_nhat: null, goi_y_xuat_phat: 12000,
    cho_ve_kho: false, la_diem_cuoi: false,
  };
  const diem = (id: number, rid: number, code: string, khach: string, tt: string,
                luot: Record<string, unknown> = {}) => ({
    ...CHUYEN, id, request_id: rid, request_code: code, customer_name: khach, trang_thai: tt,
    vehicle_id: 3, xe_bien_so: "51D-853.66", employee_name: "Trần Văn Hùng",
    phu_xe_name: "Lê Triều", yeu_cau_kho_ma: null, luot: { ...LUOT_DIEM, ...luot },
  });
  const khoi = (o: Record<string, unknown> = {}, tt = "da_len_ke_hoach",
                luot: Record<string, unknown> = {}) => ({
    id: 4, code: "LX-260918-AB12", ngay: "2026-09-18", vehicle_id: 3, xe_bien_so: "51D-853.66",
    xe_ten: "Xe tải 3.5T", so_dong_ho_xuat_phat: null, so_dong_ho_ve_kho: null, ve_kho_luc: null,
    km_ve_kho: null, goi_y_xuat_phat: 12000, so_dong_ho_gan_nhat: null, cho_ve_kho: false,
    tong_km: 0, so_cho_gui_kho: 0, so_cho_lay_hang: 0, so_cho_bat_dau: 0, so_dang_giao: 0,
    diem: [diem(31, 21, "YCGH-260918-AAAA", "Young Poong", tt, luot),
           diem(32, 22, "YCGH-260918-BBBB", "AOBO", tt, luot)],
    ...o,
  });
  const moKhoi = () => screen.findByRole("article", { name: "Lượt LX-260918-AB12" });
  const nutMo = (k: HTMLElement) => within(k).getByRole("button", { name: /Lượt LX-260918-AB12/ });
  const moRong = async (k: HTMLElement) => {
    await userEvent.click(nutMo(k));
    await waitFor(() => expect(nutMo(k)).toHaveAttribute("aria-expanded", "true"));
  };

  it("⭐ mặc định KHÉP: chỉ thấy tóm tắt; bấm tên lượt mới mở ra, bấm lần nữa khép lại", async () => {
    stubApi({ khoi: [khoi({ so_cho_gui_kho: 2 })] });
    ve({ can_plan: true });
    const k = await moKhoi();
    expect(nutMo(k)).toHaveAttribute("aria-expanded", "false");
    // Khép: có xe, kíp, số điểm + tên khách trên MỘT dòng — không có thanh bước, không có danh sách.
    expect(within(k).getByText("51D-853.66")).toBeInTheDocument();
    expect(within(k).getByText("Trần Văn Hùng")).toBeInTheDocument();
    expect(within(k).getByText(/2 điểm: Young Poong · AOBO/)).toBeInTheDocument();
    expect(within(k).queryByRole("list", { name: "Tiến độ lượt" })).toBeNull();
    // …nhưng nút bước kế tiếp vẫn bấm được ngay trên đầu khối.
    expect(within(k).getByRole("button", { name: "Gửi yêu cầu xuất kho (2)" })).toBeInTheDocument();

    await moRong(k);
    const buoc = within(k).getByRole("list", { name: "Tiến độ lượt" });
    expect(within(buoc).getAllByRole("listitem")).toHaveLength(5);
    expect(within(buoc).getByText("Gửi kho")).toHaveAttribute("aria-current", "step");
    expect(within(k).getByText("Young Poong")).toBeInTheDocument();
    expect(within(k).getByText("AOBO")).toBeInTheDocument();
    expect(within(k).getByText(/Lê Triều/)).toBeInTheDocument();

    await userEvent.click(nutMo(k));
    await waitFor(() => expect(within(k).queryByRole("list", { name: "Tiến độ lượt" })).toBeNull());
    // Tab đếm ĐƠN (2), không đếm khối (1).
    expect(screen.getByRole("tab", { name: /Đơn giao hàng/ })).toHaveTextContent("2");
  });

  it("dòng tóm tắt gộp khách trùng: hai điểm cùng một khách ⇒ \"×2\", không lặp tên", async () => {
    const k2 = khoi({ so_cho_gui_kho: 2 });
    k2.diem = k2.diem.map((d) => ({ ...d, customer_name: "Minh Long" }));
    stubApi({ khoi: [k2] });
    ve({ can_plan: true });
    const k = await moKhoi();
    expect(within(k).getByText(/2 điểm: Minh Long ×2/)).toBeInTheDocument();
  });

  it("⭐ KHÔNG còn nút lẻ gửi kho / lấy hàng / bắt đầu giao ở từng điểm của lượt", async () => {
    // Hai chỗ bấm cho cùng một việc là chỗ rối nhất của bản trước (bấm thử 18/09/2026).
    stubApi({ khoi: [khoi({ so_cho_lay_hang: 1, so_cho_bat_dau: 1 }, "dang_chuan_bi")] });
    ve({ can_plan: true, can_create: true });
    const k = await moKhoi();
    await moRong(k);
    for (const ten of ["Gửi yêu cầu xuất kho", "Đã lấy hàng", "Bắt đầu giao"])
      expect(within(k).queryByRole("button", { name: ten })).toBeNull();
    // …mà chỉ còn nút CẢ LƯỢT; lượt lệch nhịp thì có cả bước kế tiếp.
    expect(within(k).getByRole("button", { name: "Đã lấy hàng cả lượt (1)" })).toBeInTheDocument();
    expect(within(k).getByRole("button", { name: "Bắt đầu giao (1 điểm)" })).toBeInTheDocument();
  });

  it("⭐ chờ gửi kho ⇒ mở ô ghi chú rồi gửi MỘT lệnh cho cả lượt, mỗi điểm một phiếu", async () => {
    const goi = stubApi({
      khoi: [khoi({ so_cho_gui_kho: 2 })],
      rieng: (u) => (u.endsWith("/luot-xe/4/yeu-cau-xuat-kho")
        ? { so_chuyen: 2, phieu: ["DNX0101", "DNX0102"], canh_bao: [] } : undefined),
    });
    ve({ can_plan: true });
    const k = await moKhoi();
    // Bấm ngay trên đầu khối đang khép — ô ghi chú mở ra trong thân khối.
    await userEvent.click(within(k).getByRole("button", { name: "Gửi yêu cầu xuất kho (2)" }));
    expect(nutMo(k)).toHaveAttribute("aria-expanded", "true");
    await userEvent.type(within(k).getByLabelText(/Ghi chú cho kho/), "Soạn trước 7h");
    await userEvent.click(within(k).getByRole("button", { name: "Gửi 2 phiếu" }));
    expect(await within(k).findByText(/Đã gửi 2 phiếu yêu cầu xuất kho: DNX0101, DNX0102/))
      .toBeInTheDocument();
    expect(goi.filter((g) => g.url.includes("/yeu-cau-xuat-kho"))).toHaveLength(1);
    expect(goi.find((g) => g.url.endsWith("/luot-xe/4/yeu-cau-xuat-kho"))!.body)
      .toEqual({ ghi_chu: "Soạn trước 7h" });
  });

  it("không có ô Lên kế hoạch ⇒ khối KHÔNG bày nút gửi kho", async () => {
    stubApi({ khoi: [khoi({ so_cho_gui_kho: 2 })] });
    ve({ can_create: true });
    const k = await moKhoi();
    expect(within(k).queryByRole("button", { name: /Gửi yêu cầu xuất kho/ })).toBeNull();
    await moRong(k);
    expect(within(k).queryByRole("button", { name: /Gửi yêu cầu xuất kho/ })).toBeNull();
  });

  it("Đã lấy hàng cả lượt ⇒ MỘT lệnh, bấm được khi khối đang khép", async () => {
    const goi = stubApi({
      khoi: [khoi({ so_cho_lay_hang: 2 }, "dang_chuan_bi")],
      rieng: (u) => (u.endsWith("/luot-xe/4/da-lay-hang")
        ? { so_chuyen: 2, phieu: [], canh_bao: [] } : undefined),
    });
    ve({ can_create: true });
    const k = await moKhoi();
    await userEvent.click(within(k).getByRole("button", { name: "Đã lấy hàng cả lượt (2)" }));
    expect(await within(k).findByText("Đã lấy hàng 2 điểm.")).toBeInTheDocument();
    expect(goi.filter((g) => g.url.includes("da-lay-hang"))).toHaveLength(1);
  });

  it("⭐ Bắt đầu giao lần đầu hỏi số đồng hồ xuất phát, TỰ ĐIỀN số cuối của xe", async () => {
    const goi = stubApi({
      khoi: [khoi({ so_cho_bat_dau: 2 }, "da_lay_hang")],
      rieng: (u) => (u.endsWith("/luot-xe/4/bat-dau-giao")
        ? { so_chuyen: 2, phieu: [], canh_bao: [] } : undefined),
    });
    ve({ can_create: true });
    const k = await moKhoi();
    await userEvent.click(within(k).getByRole("button", { name: "Bắt đầu giao (2 điểm)" }));
    // Bấm ở khối chỉ MỞ ô số — chưa gửi gì.
    expect(goi.some((g) => g.url.includes("/bat-dau-giao"))).toBe(false);
    const o = within(k).getByLabelText(/Số đồng hồ lúc xuất phát/);
    expect(o).toHaveValue(12000);
    await userEvent.clear(o);
    await userEvent.type(o, "12030");
    await userEvent.click(within(k).getByRole("button", { name: "Bắt đầu giao 2 điểm" }));
    await waitFor(() =>
      expect(goi.some((g) => g.url.endsWith("/luot-xe/4/bat-dau-giao"))).toBe(true));
    expect(goi.filter((g) => g.url.includes("/bat-dau-giao"))).toHaveLength(1);   // MỘT lệnh
    expect(goi.find((g) => g.url.endsWith("/luot-xe/4/bat-dau-giao"))!.body)
      .toEqual({ so_dong_ho_xuat_phat: 12030 });
  });

  it("⭐ xe chạy ngoài sổ ⇒ cảnh báo ở lại cho người bấm đọc, không vụt tắt", async () => {
    const canh = "Xe chạy ngoài sổ 30 km kể từ lượt trước (số cuối đã ghi 12000).";
    stubApi({
      khoi: [khoi({ so_cho_bat_dau: 2 }, "da_lay_hang")],
      rieng: (u) => (u.endsWith("/luot-xe/4/bat-dau-giao")
        ? { so_chuyen: 2, phieu: [], canh_bao: [canh] } : undefined),
    });
    ve({ can_create: true });
    const k = await moKhoi();
    await userEvent.click(within(k).getByRole("button", { name: "Bắt đầu giao (2 điểm)" }));
    await userEvent.click(within(k).getByRole("button", { name: "Bắt đầu giao 2 điểm" }));
    expect(await within(k).findByText(canh)).toBeInTheDocument();
    await userEvent.click(within(k).getByRole("button", { name: "Đã hiểu" }));
    await waitFor(() => expect(within(k).queryByText(canh)).toBeNull());
  });

  it("đã có số xuất phát (xe đi dở, bốc thêm điểm) ⇒ bấm thẳng, không hỏi lại số", async () => {
    const goi = stubApi({
      khoi: [khoi({ so_cho_bat_dau: 1, so_dong_ho_xuat_phat: 12000 }, "da_lay_hang")],
      rieng: (u) => (u.endsWith("/luot-xe/4/bat-dau-giao")
        ? { so_chuyen: 1, phieu: [], canh_bao: [] } : undefined),
    });
    ve({ can_create: true });
    const k = await moKhoi();
    await userEvent.click(within(k).getByRole("button", { name: "Bắt đầu giao (1 điểm)" }));
    await waitFor(() =>
      expect(goi.some((g) => g.url.endsWith("/luot-xe/4/bat-dau-giao"))).toBe(true));
    expect(goi.find((g) => g.url.endsWith("/luot-xe/4/bat-dau-giao"))!.body).toBeNull();
    expect(within(k).queryByLabelText(/Số đồng hồ lúc xuất phát/)).toBeNull();
  });

  const dangGiao = () => khoi(
    { so_dang_giao: 2, so_dong_ho_xuat_phat: 12000, so_dong_ho_gan_nhat: 12000,
      goi_y_xuat_phat: null },
    "dang_giao",
    { so_dong_ho_xuat_phat: 12000, so_dong_ho_gan_nhat: 12000, goi_y_xuat_phat: null },
  );

  it("⭐ đang giao ⇒ đầu khối chỉ đường \"Nhập kết quả\", mở ra thì mỗi điểm một nút; ô SỐ ĐỒNG HỒ thay ô km", async () => {
    const goi = stubApi({ khoi: [dangGiao()] });
    ve({ can_create: true });
    const k = await moKhoi();
    // Khép: nút ở đầu khối MỞ khối ra (việc nhập là của từng điểm, không phải của cả lượt).
    await userEvent.click(within(k).getByRole("button", { name: "Nhập kết quả (2 điểm)" }));
    expect(nutMo(k)).toHaveAttribute("aria-expanded", "true");
    expect(within(k).getByText(/Tới khách nào thì bấm/)).toBeInTheDocument();
    const nut = within(k).getAllByRole("button", { name: "Nhập kết quả" });
    expect(nut).toHaveLength(2);
    await userEvent.click(nut[0]);
    const o = await screen.findByLabelText(/Số đồng hồ lúc tới khách/);
    expect(screen.queryByLabelText(/Số km thực tế/)).toBeNull();
    // Xe là xe CỦA LƯỢT — không bày ô đổi xe riêng một chuyến.
    expect(screen.queryByLabelText(/Xe đã chạy chuyến/)).toBeNull();
    await userEvent.type(o, "12021");
    expect(screen.getByText(/chặng này 21 km/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Người nhận hàng/), "Chị Hạnh");
    await userEvent.click(screen.getByRole("button", { name: /Lưu kết quả/ }));
    await waitFor(() => expect(goi.some((g) => g.url.includes("/trips/31/ket-qua"))).toBe(true));
    const body = goi.find((g) => g.url.includes("/ket-qua"))!.body as Record<string, unknown>;
    expect(body.so_dong_ho).toBe(12021);
    expect("km" in body).toBe(false);
    expect("vehicle_id" in body).toBe(false);
  });

  it("chặng > 500 km ⇒ phải tích xác nhận (lỗi hay gặp là gõ thừa một chữ số)", async () => {
    stubApi({ khoi: [dangGiao()] });
    ve({ can_create: true });
    const k = await moKhoi();
    await moRong(k);
    await userEvent.click(within(k).getAllByRole("button", { name: "Nhập kết quả" })[0]);
    await userEvent.type(await screen.findByLabelText(/Số đồng hồ lúc tới khách/), "12600");
    expect(screen.getByRole("checkbox", { name: /Xác nhận chặng 600 km là đúng/ }))
      .toBeInTheDocument();
  });

  it("gõ dở số đồng hồ KHÔNG báo \"nhỏ hơn số xuất phát\"", async () => {
    // Bấm thử 18/09/2026: gõ "9757" (đang tới 97570) đã hiện cảnh báo đỏ, doạ người gõ đúng.
    stubApi({ khoi: [dangGiao()] });
    ve({ can_create: true });
    const k = await moKhoi();
    await moRong(k);
    await userEvent.click(within(k).getAllByRole("button", { name: "Nhập kết quả" })[0]);
    const o = await screen.findByLabelText(/Số đồng hồ lúc tới khách/);
    await userEvent.type(o, "1200");
    expect(screen.queryByText(/Nhỏ hơn số lúc xuất phát/)).toBeNull();
    await userEvent.type(o, "0");            // 12000 → bằng, vẫn không báo
    expect(screen.queryByText(/Nhỏ hơn số lúc xuất phát/)).toBeNull();
    await userEvent.clear(o);
    await userEvent.type(o, "11990");        // đủ chữ số và nhỏ hơn thật ⇒ báo
    expect(screen.getByText(/Nhỏ hơn số lúc xuất phát/)).toBeInTheDocument();
  });

  it("hộp Nhập kết quả KHÔNG báo \"hết hàng\" trong lúc còn đang tải", async () => {
    // Bấm thử 18/09/2026: hộp vừa mở đã ghi "Không còn hàng nào để giao" rồi mới hiện hàng.
    stubApi({ khoi: [dangGiao()] });
    ve({ can_create: true });
    const k = await moKhoi();
    await moRong(k);
    await userEvent.click(within(k).getAllByRole("button", { name: "Nhập kết quả" })[0]);
    expect(screen.queryByText("Không còn hàng nào để giao.")).toBeNull();
    expect(await screen.findByLabelText(/Số thực nhận — Hộp thuốc/)).toBeInTheDocument();
  });

  it("⭐ mọi điểm xong ⇒ nút Về kho ngay trên đầu khối, gửi số đồng hồ vào ĐÚNG lượt", async () => {
    const goi = stubApi({
      khoi: [khoi({ cho_ve_kho: true, so_dong_ho_xuat_phat: 12000, so_dong_ho_gan_nhat: 12028 },
                  "thanh_cong", { so_dong_ho: 12028 })],
      rieng: (u) => (u.endsWith("/luot-xe/4/ve-kho")
        ? { id: 4, code: "LX-260918-AB12", so_dong_ho_ve_kho: 12045, km_ve_kho: 17,
            ve_kho_luc: "2026-09-18T09:00:00Z", canh_bao: [] }
        : undefined),
    });
    ve({ can_create: true });
    const k = await moKhoi();
    await userEvent.click(within(k).getByRole("button", { name: "Về kho" }));
    await userEvent.type(within(k).getByLabelText(/Số đồng hồ lúc về kho/), "12045");
    expect(within(k).getByText(/chặng về kho 17 km/)).toBeInTheDocument();
    await userEvent.click(within(k).getByRole("button", { name: "Lưu về kho" }));
    await waitFor(() => expect(goi.some((g) => g.url.endsWith("/luot-xe/4/ve-kho"))).toBe(true));
    expect(goi.find((g) => g.url.endsWith("/ve-kho"))!.body)
      .toEqual({ so_dong_ho: 12045, xac_nhan_km_lon: false });
  });

  it("còn điểm đang giao ⇒ KHÔNG có nút Về kho", async () => {
    stubApi({ khoi: [dangGiao()] });
    ve({ can_create: true });
    const k = await moKhoi();
    expect(within(k).queryByRole("button", { name: "Về kho" })).toBeNull();
    await moRong(k);
    expect(within(k).queryByRole("button", { name: "Về kho" })).toBeNull();
  });

  it("đã về kho ⇒ khối ghi Đã về kho, mở ra có dòng Về kho với km chặng về", async () => {
    stubApi({
      khoi: [khoi({ ve_kho_luc: "2026-09-18T09:00:00Z", so_dong_ho_xuat_phat: 12000,
                    so_dong_ho_ve_kho: 12045, km_ve_kho: 17, tong_km: 45 }, "thanh_cong")],
    });
    ve({ can_create: true });
    const k = await moKhoi();
    expect(within(k).getByText("Đã về kho")).toBeInTheDocument();
    expect(within(k).getByText(/Đã chạy/)).toHaveTextContent("Đã chạy 45 km");
    // Không còn việc gì cho cả lượt ⇒ đầu khối không có nút nào ngoài nút khép/mở.
    expect(within(k).getAllByRole("button")).toHaveLength(1);
    await moRong(k);
    expect(within(k).getByText("17 km")).toBeInTheDocument();
    // Mã yêu cầu vẫn bấm mở chi tiết được; chỉ các nút thao tác cả lượt là hết.
    expect(within(k).getAllByRole("button", { name: /YCGH-/ })).toHaveLength(2);
    expect(within(k).queryByRole("button", { name: /Về kho|Bắt đầu|lấy hàng/ })).toBeNull();
  });
});

describe("Giao hàng · GOM NHIỀU YÊU CẦU chạy MỘT lượt (chủ chốt 18/09/2026)", () => {
  // "Gom nhiều phiếu lại chạy 1 lượt" — MỖI yêu cầu vẫn một đơn giao hàng + một phiếu xuất kho;
  // lượt chỉ gom đường đi.
  const XE = { id: 3, ma: "51D-853.66", ten: "Xe tải 3.5T", tai_trong: 3.5, active: true };
  const yc = (id: number, code: string, khach: string) => ({
    id, code, order_id: id, order_code: `DH-${id}`, customer_name: khach,
    ngay_can_giao: "2026-09-19", dia_chi: "Lô C3", trang_thai: "cho_len_ke_hoach", lines: [],
    so_lan_giao: 0, trang_thai_lsx: [], created_at: "2026-09-18T01:00:00Z",
  });
  const A = yc(21, "YCGH-260918-AAAA", "Young Poong");
  const B = yc(22, "YCGH-260918-BBBB", "AOBO");
  const KHOI_MOI = {
    id: 4, code: "LX-260918-AB12", ngay: "2026-09-19", vehicle_id: 3, xe_bien_so: "51D-853.66",
    xe_ten: "Xe tải 3.5T", so_dong_ho_xuat_phat: null, so_dong_ho_ve_kho: null, ve_kho_luc: null,
    km_ve_kho: null, goi_y_xuat_phat: null, so_dong_ho_gan_nhat: null, cho_ve_kho: false,
    tong_km: 0, so_cho_gui_kho: 2, so_cho_lay_hang: 0, so_cho_bat_dau: 0, so_dang_giao: 0,
    diem: [
      { ...CHUYEN, id: 31, request_id: 21, request_code: A.code, customer_name: "Young Poong",
        trang_thai: "da_len_ke_hoach", yeu_cau_kho_ma: null },
      { ...CHUYEN, id: 32, request_id: 22, request_code: B.code, customer_name: "AOBO",
        trang_thai: "da_len_ke_hoach", yeu_cau_kho_ma: null },
    ],
  };

  it("⭐ tick hai yêu cầu ⇒ \"Lên lượt xe (2)\" ⇒ MỘT lần gửi cả hai, rồi khối lượt nổi lên", async () => {
    const goi = stubApi({
      requests: [A, B], xe: [XE], khoi: [KHOI_MOI],
      rieng: (u) => (u.endsWith("/giao-hang/luot-xe")
        ? { luot_id: 4, code: "LX-260918-AB12", trips: [], canh_bao: [] } : undefined),
    });
    ve({ can_plan: true, can_read: true, can_create: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Yêu cầu giao/ }));
    const nut = await screen.findByRole("button", { name: /Lên lượt xe/ });
    expect(nut).toBeDisabled();                      // chưa tick gì thì chưa bấm được
    await userEvent.click(screen.getByRole("checkbox", { name: `Chọn ${A.code}` }));
    // Câu trên thanh chọn KHÔNG đổi theo số chọn — đổi là bảng nhảy, cú bấm sau trượt.
    expect(screen.getByText("Tick nhiều yêu cầu để chở chung một lượt xe.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: `Chọn ${B.code}` }));
    await userEvent.click(screen.getByRole("button", { name: "Lên lượt xe (2)" }));

    const hop = await screen.findByRole("dialog");
    expect(within(hop).getByText("Lên lượt xe · 2 yêu cầu")).toBeInTheDocument();
    await userEvent.selectOptions(within(hop).getByLabelText(/Nhân viên giao/), "5");
    await waitFor(() =>
      expect(within(hop).getByRole("option", { name: /51D-853\.66/ })).toBeInTheDocument());
    await userEvent.selectOptions(within(hop).getByLabelText(/^Xe/), "3");
    fireEvent.change(within(hop).getByLabelText(/Giờ lấy hàng/), { target: { value: "2026-09-19T08:00" } });
    fireEvent.change(within(hop).getByLabelText(/Giờ dự kiến giao/), { target: { value: "2026-09-19T11:00" } });
    await userEvent.click(within(hop).getByRole("button", { name: /Lưu lượt xe \(2 đơn\)/ }));

    await waitFor(() => expect(goi.some((g) => g.url.endsWith("/giao-hang/luot-xe"))).toBe(true));
    const body = goi.find((g) => g.url.endsWith("/giao-hang/luot-xe"))!.body as Record<string, unknown>;
    expect(body.request_ids).toEqual([21, 22]);
    expect(body).toMatchObject({ employee_id: 5, vehicle_id: 3, luot_xe_id: "moi" });
    // Không gọi `/plans` lẻ từng yêu cầu.
    expect(goi.some((g) => g.url.endsWith("/plans"))).toBe(false);
    // Về tab Đơn giao hàng, khối lượt vừa lập NỔI lên — bước kế tiếp nằm ngay trên khối.
    const k = await screen.findByRole("article", { name: "Lượt LX-260918-AB12" });
    expect(k).toHaveClass("is-moi");
    expect(within(k).getByRole("button", { name: "Gửi yêu cầu xuất kho (2)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Đơn giao hàng/ })).toHaveAttribute("aria-selected", "true");
  });

  it("lên lượt mà chưa chọn xe ⇒ nút lưu mờ (lượt là vòng chạy của MỘT chiếc xe)", async () => {
    stubApi({ requests: [A, B], xe: [] });
    ve({ can_plan: true, can_read: true });
    await userEvent.click(await screen.findByRole("tab", { name: /Yêu cầu giao/ }));
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "Chọn tất cả yêu cầu trên trang" }));
    await userEvent.click(screen.getByRole("button", { name: "Lên lượt xe (2)" }));
    const hop = await screen.findByRole("dialog");
    await userEvent.selectOptions(within(hop).getByLabelText(/Nhân viên giao/), "5");
    fireEvent.change(within(hop).getByLabelText(/Giờ lấy hàng/), { target: { value: "2026-09-19T08:00" } });
    fireEvent.change(within(hop).getByLabelText(/Giờ dự kiến giao/), { target: { value: "2026-09-19T11:00" } });
    expect(within(hop).getByRole("button", { name: /Lưu lượt xe/ })).toBeDisabled();
    expect(within(hop).getByText(/lượt là vòng chạy của một chiếc xe/)).toBeInTheDocument();
  });
});
