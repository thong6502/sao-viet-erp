// Khối "Giao hàng" trên màn Đơn hàng bán.
//
// Ca khoá chính: ĐƠN HAI SẢN PHẨM, MỚI XONG CÁI THỨ NHẤT. Yêu cầu giao phải đi được MỘT dòng,
// không kéo cả đơn theo. Bản đầu làm ngầm — để trống ô số là tự loại — đúng việc nhưng nhìn vào
// không biết, nên người lập tưởng cứ gửi là cả đơn đi kèm.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { TaoYeuCauGiaoHang } from "./TaoYeuCauGiaoHang";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import { PermissionsProvider, buildCapabilities } from "../auth/permissions";
import type { ModuleCapability } from "../api/client";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const HOP = { order_line_id: 11, mo_ta: "Hộp thuốc 10 vỉ", don_vi_tinh: "hộp",
              qty_dat: 12000, da_giao: 0, con_phai_giao: 12000 };
const TO = { order_line_id: 12, mo_ta: "Tờ hướng dẫn sử dụng", don_vi_tinh: "tờ",
             qty_dat: 12000, da_giao: 0, con_phai_giao: 12000 };

/** Bắt lại thân request POST để soi ĐÚNG những dòng nào được gửi đi. */
function stubApi() {
  const posts: Record<string, unknown>[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const p = String(url);
    if (init?.method === "POST") posts.push(JSON.parse(String(init.body)));
    const body = p.includes("/con-phai-giao")
      ? { order_id: 3, da_giao_du: false, lines: [HOP, TO] }
      // `/mat-hang` trả THẲNG MẢNG, không bọc `{items}` — bọc nhầm thì combobox không ra gợi ý
      // nào mà cũng không báo lỗi.
      : p.includes("/mat-hang")
        ? [{ hang_loai: "vat_tu", hang_id: 77, nhom: "Vật tư khác",
             ma: "TP-HOP-THUOC", ten: "Hộp thuốc 10 vỉ", don_vi_goc: "hộp" }]
        : p.includes("/requests") ? { items: [] }
          : {};
    return Promise.resolve({
      ok: true, status: 201, headers: new Headers({ "content-type": "application/json" }),
      json: async () => body, text: async () => JSON.stringify(body),
    } as Response);
  }));
  return posts;
}

function ve(o: Partial<ModuleCapability>) {
  const caps = buildCapabilities([
    { module_key: "giao_hang", scope: "all", can_read: true, ...o } as ModuleCapability,
  ]);
  return render(
    <AuthContext.Provider value={AUTH}>
      <PermissionsProvider caps={caps}>
        <TaoYeuCauGiaoHang orderId={3} diaChiMacDinh="Lô C3, KCN Tân Bình"
          nguoiNhanMacDinh="Chị Hạnh" sdtMacDinh="0938765432" />
      </PermissionsProvider>
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("Tạo yêu cầu giao hàng · chọn từng dòng", () => {
  it("⭐ đơn 2 sản phẩm, chỉ tích 1 ⇒ CHỈ dòng đó được gửi", async () => {
    const posts = stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));

    const tich = await screen.findAllByRole("checkbox");
    expect(tich).toHaveLength(2);
    await userEvent.click(tich[0]);                       // chỉ "Hộp thuốc"

    const ngay = screen.getByLabelText(/Ngày cần giao/);
    await userEvent.type(ngay, "2026-09-01");
    await userEvent.click(screen.getByRole("button", { name: /Gửi yêu cầu/ }));

    await waitFor(() => expect(posts).toHaveLength(1));
    const lines = (posts[0] as { lines: Record<string, unknown>[] }).lines;
    expect(lines).toEqual([{ order_line_id: 11, qty: 12000 }]);
  });

  it("⭐ tích rồi BỎ TÍCH ⇒ dòng đó KHÔNG được gửi", async () => {
    // Test "chỉ tích 1" ở trên KHÔNG cắn được ô tích: dòng chưa tích có ô số rỗng nên bộ lọc
    // `qty > 0` đã loại sẵn. Phải đi đường tích-rồi-bỏ mới phân biệt được hai hàng rào —
    // bỏ tích mà không xoá số thì dòng vẫn lọt qua `qty > 0` và đi kèm yêu cầu.
    const posts = stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));

    const tich = await screen.findAllByRole("checkbox");
    await userEvent.click(tich[0]);   // tích Hộp thuốc → điền sẵn 12000
    await userEvent.click(tich[1]);   // tích Tờ hướng dẫn → điền sẵn 12000
    await userEvent.click(tich[1]);   // ĐỔI Ý: bỏ tích Tờ hướng dẫn

    await userEvent.type(screen.getByLabelText(/Ngày cần giao/), "2026-09-01");
    await userEvent.click(screen.getByRole("button", { name: /Gửi yêu cầu/ }));

    await waitFor(() => expect(posts).toHaveLength(1));
    const lines = (posts[0] as { lines: Record<string, unknown>[] }).lines;
    expect(lines).toEqual([{ order_line_id: 11, qty: 12000 }]);
  });

  it("tích vào là điền sẵn TOÀN BỘ phần còn lại", async () => {
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    await userEvent.click((await screen.findAllByRole("checkbox"))[1]);
    expect(screen.getByLabelText(/Số lượng giao — Tờ hướng dẫn/)).toHaveValue(12000);
  });

  it("chưa tích dòng nào ⇒ nút Gửi bị khoá", async () => {
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    await userEvent.type(screen.getByLabelText(/Ngày cần giao/), "2026-09-01");
    expect(screen.getByRole("button", { name: /Gửi yêu cầu/ })).toBeDisabled();
  });

  it("⭐ ô số lượng là input SỐ có trần, không phải ô chữ", async () => {
    // Người dùng gõ được "ưe" vào ô này ở bản đầu — `inputMode="numeric"` chỉ đổi bàn phím
    // điện thoại, bàn phím máy tính vẫn gõ chữ vào được.
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    await userEvent.click((await screen.findAllByRole("checkbox"))[0]);
    const o = screen.getByLabelText(/Số lượng giao — Hộp thuốc/);
    expect(o).toHaveAttribute("type", "number");
    expect(o).toHaveAttribute("max", "12000");   // trần = phần còn phải giao
    expect(o).toHaveAttribute("min", "1");
  });

  it("dòng chưa tích thì ô số bị khoá", async () => {
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    expect(screen.getByLabelText(/Số lượng giao — Hộp thuốc/)).toBeDisabled();
  });
});

describe("Tạo yêu cầu giao hàng · hệ TỰ KHAI mặt hàng kho", () => {
  it("⭐ KHÔNG bắt người lập chọn mặt hàng kho", async () => {
    // Sản phẩm in là hàng ĐẶT RIÊNG — "Hộp thuốc 10 vỉ — in 2 màu, cán bóng" của khách A không
    // có sẵn trong danh mục để mà chọn. Bắt chọn là bắt chọn một thứ chưa tồn tại (chủ chốt
    // 19/08/2026). Máy chủ tự khai vào Vật tư khác theo đúng mô tả trên đơn.
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    await userEvent.click((await screen.findAllByRole("checkbox"))[0]);
    expect(screen.queryAllByPlaceholderText(/danh mục kho/)).toHaveLength(0);
    await userEvent.type(screen.getByLabelText(/Ngày cần giao/), "2026-09-01");
    // Tích + ngày là đủ để gửi — không có mắt xích nào phải khai thêm.
    expect(screen.getByRole("button", { name: /Gửi yêu cầu/ })).toBeEnabled();
  });

  it("nói rõ máy đã tự khai vào danh mục NÀO", async () => {
    // Phải gọi ĐÚNG TÊN màn "Thành phẩm" — nói chung chung "danh mục" thì kho không biết mở
    // đâu ra mà tìm, và nói nhầm "Vật tư khác" thì họ tìm ở màn không có hàng (mg 0203).
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    expect(await screen.findByText(/tự khai vào danh mục/)).toBeInTheDocument();
    expect(screen.getByText("Thành phẩm")).toBeInTheDocument();
  });
});

describe("Tạo yêu cầu giao hàng · KHÔNG cho ngày quá khứ", () => {
  /** Hôm nay / hôm qua dạng YYYY-MM-DD theo giờ ĐỊA PHƯƠNG — `toISOString()` trả UTC nên có thể
   *  lệch một ngày, mà lệch ở đây là test xanh/đỏ theo múi giờ. */
  function ngay(lech: number): string {
    const d = new Date();
    d.setDate(d.getDate() + lech);
    const p = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  async function mo() {
    stubApi();
    ve({ can_create: true });
    await userEvent.click(await screen.findByRole("button", { name: /Tạo yêu cầu giao hàng/ }));
    await userEvent.click((await screen.findAllByRole("checkbox"))[0]);
  }

  it("⭐ ô ngày có chặn `min` = hôm nay", async () => {
    // Chủ chốt 20/08/2026: "nay ngày 20 lập phiếu thì sao mà chọn được ngày 19".
    await mo();
    expect(screen.getByLabelText(/Ngày cần giao/)).toHaveAttribute("min", ngay(0));
  });

  it("⭐ gõ tay ngày hôm qua ⇒ KHOÁ nút Gửi + báo lỗi", async () => {
    // `min` chỉ chặn ở lịch chọn, gõ tay vẫn lọt — nên phải có hàng rào thứ hai.
    await mo();
    await userEvent.type(screen.getByLabelText(/Ngày cần giao/), ngay(-1));
    expect(await screen.findByRole("alert")).toHaveTextContent(/không được ở quá khứ/i);
    expect(screen.getByRole("button", { name: /Gửi yêu cầu/ })).toBeDisabled();
  });

  it("HÔM NAY thì vẫn gửi được — giao trong ngày là chuyện thường", async () => {
    // Ranh giới lệch một ngày ở đây là chặn mất đúng ca hay dùng nhất.
    await mo();
    await userEvent.type(screen.getByLabelText(/Ngày cần giao/), ngay(0));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /Gửi yêu cầu/ })).toBeEnabled();
  });
});

describe("Tạo yêu cầu giao hàng · cổng quyền", () => {
  it("thiếu ô Thao tác ⇒ không bày nút, nói rõ vì sao", async () => {
    stubApi();
    ve({});
    await waitFor(() => expect(screen.getByText("Hộp thuốc 10 vỉ")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Tạo yêu cầu giao hàng/ })).not.toBeInTheDocument();
    expect(screen.getByText(/chưa được bật ô Thao tác/)).toBeInTheDocument();
  });
});
