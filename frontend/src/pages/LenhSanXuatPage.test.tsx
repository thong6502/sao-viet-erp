// Task 14 (deep link QR): `AppShell` đọc hash `#lsx=&pv=` (xem `appShellDeepLink.test.ts`) rồi bơm
// xuống đây qua hai prop `openHoSoId`/`openHoSoPv`. Bài canh này chốt khúc CUỐI của dây chuyền —
// prop tới tay component thì đúng lệnh phải tự mở, KỂ CẢ khi lệnh đó không nằm trong trang bảng
// đang tải (người quét QR ở xưởng không quan tâm trang mấy, tab nào). Khúc đầu dây chuyền (hash
// sống sót qua đăng nhập) nằm ở `LoginPage.test.tsx`; khúc phân tích hash nằm ở
// `appShellDeepLink.test.ts`; khúc băng cảnh báo phiên bản nằm ở `LenhSxHoSoView.test.tsx`.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  LenhSxBoLocOut,
  LenhSxHoSoOut,
  LenhSxListOut,
  LenhSxSummaryOut,
} from "../api/client";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import { PermissionsProvider, buildCapabilities } from "../auth/permissions";
import type { ModuleCapability } from "../api/client";
import { LenhSanXuatPage } from "./LenhSanXuatPage";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const DON_VI = [{ ma: "cai", ten: "cái" }];

const KPI: LenhSxSummaryOut = {
  dang_sx: 1, cong_doan_xong_hom_nay: 0, du_kien_tre: 0, ty_le_kcs_dat_hom_nay: null,
};

const BO_LOC: LenhSxBoLocOut = { may: [] };

/** Bảng phía sau chỉ có lệnh #5 — KHÔNG có lệnh #77. Cố tình: hồ sơ mở qua deep link phải tự đứng
 *  được mà không cần bảng biết gì về nó, đúng thứ ghi chú `LenhSanXuatPage.tsx` nói ("hồ sơ vẽ ĐÈ
 *  lên bảng chứ không thay màn"). */
const LIST: LenhSxListOut = {
  items: [{
    id: 5, ma: "LSX26-0005", ten: "Lệnh khác", khach_hang: null, khach_hang_id: null,
    sale: null, so_luong_dat: 10, don_vi_tinh: "cái", da_giao: 0, is_rush: false,
    buoc_hien_tai: null, nhom_cong_doan: null, may: null, nguoi: [],
    tien_do_pct: 0, tien_do_uoc_tinh: false, gio_may: 0,
    han_hoan_thanh_sx: null, han_giao_khach: null, du_kien_xong: null,
    trang_thai: "dang_sx", canh_bao: [],
  }],
  total: 1, page: 1, page_size: 50, dem_theo_tab: { tat_ca: 1 },
};

/** Hồ sơ TỐI GIẢN — chỉ đủ mọi trường bắt buộc của `LenhSxHoSoOut`, không cần đủ 13 khối như bài
 *  canh của `LenhSxHoSoView.test.tsx` (chỗ đó soi NỘI DUNG hồ sơ; chỗ này chỉ soi ĐÚNG LỆNH nào mở
 *  ra, nên `ma` là trường duy nhất thật sự cần khác biệt). */
const HOSO_77: LenhSxHoSoOut = {
  thong_tin: {
    id: 77, ma: "LSX26-0077", ten: "Lệnh quét QR", loai: null,
    order_id: null, order_no: null, order_line_id: null,
    khach_hang: null, khach_hang_id: null, sale: null,
    so_luong_dat: 100, don_vi_tinh: "cái", is_rush: false,
    han_hoan_thanh_sx: null, han_giao_khach: null,
    ban_giao_at: null, ghi_chu: null, tao_luc: null,
  },
  tien_do: {
    phan_tram: 0, uoc_tinh: false, gio_may: 0,
    du_kien_xong: null, trang_thai: "dang_sx", canh_bao: [],
    buoc_hien_tai: null, buoc_hien_tai_cong_viec_id: null, nhom_cong_doan: null,
    may: null, nguoi: [], da_giao: 0,
  },
  thong_so: {
    giay_ten: null, dinh_luong: null,
    kho_nguyen_dai: null, kho_nguyen_rong: null, kho_in_dai: null, kho_in_rong: null,
    dai_thanh_pham: null, rong_thanh_pham: null, quy_cach_in: null,
    so_mau_a: null, so_mau_b: null, muc_a: [], muc_b: [],
    so_trang: null, trang_moi_tay: null, so_kem: null, so_manh_xa: null,
    loai_san_pham: null, ghi_chu_ky_thuat: null,
    so_con: 0, so_to_ke_hoach: 0, so_to_nguyen: 0, don_vi_tinh: null,
  },
  routing: { nodes: [], canh: [] },
  vat_tu: { hien_tai: { du: true, dong: [] }, canh_bao_sau: [], da_cap: [], bo_qua: [] },
  nhan_luc: { hien_tai: [], lich_su: [] },
  san_luong: { tong: 0, tot: 0, hong: 0, batch: [] },
  su_co: [],
  kcs: { tong_nhan: 0, tong_dat: 0, tong_khong_dat: 0, ty_le_dat: null, batch: [] },
  kho: { so_lenh_trong_nhom: 0, yeu_cau: [], btp: [] },
  giao_hang: {
    nhom_id: null, order_id: null, order_line_ids: [], so_lenh_trong_nhom: 0,
    hang: [], da_nhap_kho: 0, da_giao: 0, co_the_giao: false, don_vi_lech: false,
  },
  timeline: [],
  phien_ban: 3,
};

/** Hồ sơ của LỆNH KHÁC (#5 — chính là dòng có sẵn trong `LIST`), dùng để (a) sửa vòng 1 P4: chứng
 *  minh stub trả ĐÚNG hồ sơ theo id được hỏi chứ không phải luôn `HOSO_77`; (b) sửa vòng 1 P5: là
 *  đích của lượt "mở tay" sau khi đã mở một hồ sơ khác qua QR — `phien_ban: 5` CỐ Ý lớn hơn mọi
 *  `pv` dùng trong file này (1/3), để nếu `moHoSoTay` có bug quên xoá `pv` cũ thì điều kiện băng
 *  cảnh báo (`pv < phien_ban`) vẫn đúng và băng LẠI HIỆN — bài test bắt được đúng ca đó. */
const HOSO_5: LenhSxHoSoOut = {
  ...HOSO_77,
  thong_tin: { ...HOSO_77.thong_tin, id: 5, ma: "LSX26-0005", ten: "Lệnh khác" },
  phien_ban: 5,
};

const HOSO_BY_ID: Record<number, LenhSxHoSoOut> = { 77: HOSO_77, 5: HOSO_5 };

/** Fetch giả PHÂN BIỆT ĐƯỜNG DẪN — bốn nguồn `LenhSanXuatPage` gọi lúc mount (danh sách, KPI, bộ
 *  lọc máy) cộng nguồn `LenhSxHoSoView` gọi khi hồ sơ mở (hồ sơ một lệnh, danh mục đơn vị). Thứ tự
 *  kiểm PHẢI cụ thể trước chung: `/summary` và `/bo-loc` đứng trước lượt kiểm số ở cuối đường dẫn,
 *  nếu không chúng rơi nhầm vào nhánh danh sách trần.
 *
 *  Sửa vòng 1 (P4): nhánh hồ sơ TRƯỚC ĐÂY trả `HOSO_77` bất kể id hỏi là gì — bài test dựa vào stub
 *  đó không canh được việc `LenhSanXuatPage` có truyền ĐÚNG id đã yêu cầu hay không (một bug hardcode
 *  fetch nhầm id vẫn nhận lại `HOSO_77` như thường, bài vẫn xanh). Nay tra theo `HOSO_BY_ID`; id lạ
 *  ⇒ trả 404 thật (không phải "trả bừa `HOSO_77`") để một bug id-sai lộ ra thành lỗi tải hồ sơ, có
 *  thể quan sát được thay vì im lặng trùng khớp. */
function stubApi() {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    let data: unknown;
    let status = 200;
    const mHoSo = /\/api\/lenh-san-xuat\/(\d+)$/.exec(url);
    if (url.includes("/api/don-vi")) data = { items: DON_VI };
    else if (url.includes("/api/lenh-san-xuat/summary")) data = KPI;
    else if (url.includes("/api/lenh-san-xuat/bo-loc")) data = BO_LOC;
    else if (mHoSo) {
      const id = Number(mHoSo[1]);
      const hs = HOSO_BY_ID[id];
      if (hs) data = hs;
      else {
        status = 404;
        data = { detail: `không có lệnh id=${id} trong stub` };
      }
    } else if (url.includes("/api/lenh-san-xuat")) data = LIST;
    else data = {};
    return Promise.resolve({
      ok: status < 400, status, headers: new Headers({ "content-type": "application/json" }),
      json: async () => data, text: async () => JSON.stringify(data),
    } as Response);
  }));
}

const CAPS = buildCapabilities([
  {
    module_key: "giao_hang", scope: "all",
    can_read: true, can_create: true, can_update: true,
  } as ModuleCapability,
]);

/** Cây UI dùng CHUNG cho lượt `render` đầu và mọi lượt `rerender` sau (sửa vòng 2, mục A) — tách
 *  riêng để bài canh "quét lại cùng lệnh" đổi được `openHoSoSeq` mà không phải chép lại hai lớp
 *  Provider bao quanh. */
function uiLenhSanXuat(
  openHoSoId?: number | null,
  openHoSoPv?: number | null,
  openHoSoSeq?: number | null,
) {
  return (
    <AuthContext.Provider value={AUTH}>
      <PermissionsProvider caps={CAPS}>
        <LenhSanXuatPage
          openHoSoId={openHoSoId}
          openHoSoPv={openHoSoPv}
          openHoSoSeq={openHoSoSeq}
        />
      </PermissionsProvider>
    </AuthContext.Provider>
  );
}

function ve(openHoSoId?: number | null, openHoSoPv?: number | null, openHoSoSeq?: number | null) {
  return render(uiLenhSanXuat(openHoSoId, openHoSoPv, openHoSoSeq));
}

// KHÔNG `vi.unstubAllGlobals()` ở đây (khác `LenhSxHoSoView.test.tsx`): `setup.ts` stub
// `ResizeObserver` MỘT LẦN cho cả file — màn này (khác `LenhSxHoSoView`) có dùng nó để đo tràn
// ngang của bảng, unstub sạch giữa hai bài là xoá luôn cái đó và bài sau ăn `ReferenceError`. Mỗi
// bài tự gọi `stubApi()` để có `fetch` MỚI, nên không cần dọn gì thêm giữa các bài.
describe("LenhSanXuatPage · deep link QR mở đúng hồ sơ (Task 14)", () => {
  it("⭐ có openHoSoId ⇒ hồ sơ lệnh #77 tự mở, dù bảng phía sau chỉ tải lệnh #5", async () => {
    stubApi();
    ve(77, 3);

    // Bảng vẫn tải bình thường ở phía sau — hồ sơ chỉ VẼ ĐÈ lên nó (docstring `LenhSanXuatPage`).
    await screen.findByText("LSX26-0005");
    // Và đúng lệnh #77 được yêu cầu, không phải lệnh nào khác — hồ sơ tự bật không cần bấm dòng.
    await screen.findByText("LSX26-0077");
  });

  it("⭐ không truyền openHoSoId ⇒ không lệnh nào tự mở (hành vi mặc định không đổi)", async () => {
    stubApi();
    ve();

    await screen.findByText("LSX26-0005");
    expect(screen.queryByText("LSX26-0077")).not.toBeInTheDocument();
  });
});

// Sửa vòng 1, P5: chưa có bài nào canh đường `pv` BÊN TRONG `LenhSanXuatPage` (khác
// `LenhSxHoSoView.test.tsx` — chỗ đó canh NỘI DUNG băng khi `pv` đã tới tay component, còn đây
// canh việc `LenhSanXuatPage` có TỰ TRUYỀN đúng `pv` xuống hay không, và có XOÁ nó đi lúc mở tay
// hay không). Hai bài dưới đúng kịch bản điều phối viên chốt.
describe("LenhSanXuatPage · đường `pv` (Task 14, sửa vòng 1 P5)", () => {
  it("⭐ openHoSoPv nhỏ hơn phien_ban của hồ sơ #77 ⇒ băng cảnh báo hiện", async () => {
    stubApi();
    ve(77, 1); // HOSO_77.phien_ban = 3 ⇒ 1 < 3.

    await screen.findByRole("heading", { name: "LSX26-0077" });
    expect(
      screen.getByText("Phiếu giấy v1, lệnh hiện tại đã là v3"),
    ).toBeInTheDocument();
  });

  it("⭐ đóng hồ sơ QR rồi mở tay lệnh #5 ⇒ KHÔNG còn băng (mở tay không có tờ giấy nào để so)", async () => {
    stubApi();
    ve(77, 1);

    await screen.findByRole("heading", { name: "LSX26-0077" });
    expect(screen.getByText(/Phiếu giấy v1/)).toBeInTheDocument();

    // Đóng hồ sơ QR — nút DUY NHẤT rõ vai "đóng" của màn (`hslsx-hs__back`, xem LenhSxHoSoView.tsx).
    await userEvent.click(screen.getByRole("button", { name: "Quay lại danh sách" }));
    expect(screen.queryByRole("heading", { name: "LSX26-0077" })).not.toBeInTheDocument();

    // Mở tay lệnh #5 bằng cách bấm dòng trong bảng — không qua QR nên không có `pv`.
    await userEvent.click(screen.getByText("LSX26-0005"));
    await screen.findByRole("heading", { name: "LSX26-0005" });

    // `HOSO_5.phien_ban = 5` CỐ Ý > mọi `pv` dùng trong bài này — nếu còn sót `pv=1` từ lượt QR
    // trước, điều kiện băng (`pv < phien_ban`) vẫn đúng và băng lại hiện lên nhầm lệnh.
    expect(screen.queryByText(/^Phiếu giấy v/)).not.toBeInTheDocument();
  });

  // Bài trên đi qua NÚT ĐÓNG trước khi mở tay — đúng đường một người dùng chuột đi thật. Nhưng
  // `dongHoSo` (nút đóng) VÀ `moHoSoTay` (mở tay) MỖI HÀM đều tự xoá `pv` của mình (xem
  // LenhSanXuatPage.tsx dòng ~176-193): đục MỘT TRONG HAI dòng đó thôi thì bài trên vẫn xanh vì
  // hàm còn lại đỡ thay — không chứng minh riêng lẻ được dòng nào. `LenhSxHoSoView.tsx:352-356` tự
  // ghi nhận một đường tắt CÓ THẬT không qua nút đóng: `lsxId` đổi trong lúc lớp phủ vẫn mounted
  // (Shift+Tab lọt xuống dòng bị che rồi bấm Enter). Bài dưới đi đúng đường đó — mở tay lệnh #5
  // trong khi hồ sơ #77 (mang `pv=1`) CHƯA đóng — để cô lập ĐÚNG MỘT dòng: `setHoSoPv(null)` bên
  // trong `moHoSoTay`.
  // Sửa vòng 2 (mục D): bài trước dùng `userEvent.click(screen.getByText("LSX26-0005"))` — bấm
  // vào CHỮ hiển thị trong dòng. Đường thật của kịch bản này (mở tay lệnh khác trong khi hồ sơ
  // #77 còn che màn) KHÔNG PHẢI chuột: lớp phủ hồ sơ vẽ ĐÈ, chặn hit-test chuột lên dòng bảng phía
  // sau trong một trình duyệt thật — jsdom không hit-test nên chuột "click qua" được, còn đời thật
  // thì không. Đường thật là BÀN PHÍM (Shift+Tab từ "Quay lại danh sách" lọt xuống nút mở của dòng
  // bị che — chính `dongHoSo` cũng dựa vào nút đó để trả tiêu điểm, xem `.hslsx__open[data-lsx]`
  // — rồi Enter). Bấm theo `aria-label` của nút đó (khớp `LenhSanXuatPage.tsx:944-949`) để mô
  // phỏng đúng đường bàn phím thay vì click xuyên lớp phủ mà chuột thật không làm được.
  //
  // Đường này sống được là NHỜ lớp phủ hồ sơ chưa trap tiêu điểm / chưa `inert` nền phía sau (soi
  // ở rà lại vòng 1, N29 — điều phối viên đã park, KHÔNG sửa trong Task 14 vì nó đụng mọi ngăn kéo
  // trong hệ chứ không riêng gì deep link). Nếu sau này khiếm khuyết a11y đó được vá (ngăn kéo trap
  // tiêu điểm / nền `inert`), đường bàn phím này không còn bấm tới nút của dòng bị che được nữa —
  // `setHoSoPv(null)` trong `moHoSoTay` khi đó thành thuần phòng thủ (không còn đường thật nào gọi
  // tới nó qua ngả này) và BÀI NÀY HẾT Ý NGHĨA. Lúc đó XOÁ bài, đừng vá lại cho nó xanh.
  it("⭐ mở tay lệnh #5 trong khi hồ sơ QR khác CHƯA đóng ⇒ `moHoSoTay` tự xoá pv cũ, không băng", async () => {
    stubApi();
    ve(77, 1);

    await screen.findByRole("heading", { name: "LSX26-0077" });
    expect(screen.getByText(/Phiếu giấy v1/)).toBeInTheDocument();

    // KHÔNG bấm nút đóng — mở thẳng lệnh #5 trong khi hồ sơ #77 còn đang mở, như đường
    // Shift+Tab/Enter mà `LenhSxHoSoView.tsx` đã tự ghi nhận là có thật.
    await userEvent.click(screen.getByRole("button", { name: "Mở hồ sơ lệnh LSX26-0005 — Lệnh khác" }));
    await screen.findByRole("heading", { name: "LSX26-0005" });

    expect(screen.queryByText(/^Phiếu giấy v/)).not.toBeInTheDocument();
  });
});

// Sửa vòng 2 (mục A, lỗi MỚI mức Quan trọng ở lượt rà lại): quét LẠI ĐÚNG lệnh vừa đóng ngăn kéo
// thì trước vòng sửa này KHÔNG mở lại gì. `openHoSoId`/`openHoSoPv` ra CÙNG cặp giá trị như lần
// trước ⇒ hai giá trị nguyên thuỷ đó "không đổi" dưới mắt effect khai deps `[openHoSoId,
// openHoSoPv]` — dù `AppShell` có tạo object `navParams` MỚI mỗi lượt `navigate`, hiệu đó vô nghĩa
// vì `LenhSanXuatPage` chỉ đọc giá trị nguyên thuỷ bóc ra, không đọc chính object. Gốc rễ và cách
// sửa: xem chú thích `navigate` + `navSeq` trong `AppShell.tsx`, và effect deep link trong
// `LenhSanXuatPage.tsx` (nay có thêm `openHoSoSeq` trong deps).
describe("LenhSanXuatPage · quét LẠI đúng lệnh vừa đóng vẫn phải mở lại (Task 14, sửa vòng 2 mục A)", () => {
  it("⭐ quét lại #lsx=77&pv=1 (cùng id/pv, chỉ openHoSoSeq tăng) sau khi đã đóng ⇒ hồ sơ 77 mở lại", async () => {
    stubApi();
    const { rerender } = ve(77, 1, 1);

    await screen.findByRole("heading", { name: "LSX26-0077" });

    // Lỡ tay đóng ngăn kéo — như tổ trưởng thật sự làm giữa hai lượt quét.
    await userEvent.click(screen.getByRole("button", { name: "Quay lại danh sách" }));
    expect(screen.queryByRole("heading", { name: "LSX26-0077" })).not.toBeInTheDocument();

    // Quét LẠI CHÍNH mã đó: `openHoSoId`/`openHoSoPv` giống hệt lượt trước (`77`, `1`) — đúng cặp
    // giá trị nguyên thuỷ `AppShell` thật sự truyền khi tổ trưởng quét lại cùng một tờ giấy. Chỉ
    // `openHoSoSeq` tăng (2), đúng như `navigate()` thật của `AppShell` tự làm ở MỌI lượt gọi.
    rerender(uiLenhSanXuat(77, 1, 2));

    // Trước vòng sửa 2: effect không chạy lại (deps không đổi) ⇒ dòng dưới đây timeout, bài đỏ.
    await screen.findByRole("heading", { name: "LSX26-0077" });
  });
});
