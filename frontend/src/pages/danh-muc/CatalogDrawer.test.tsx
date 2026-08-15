// Lưới test cho DRAWER của màn danh mục dùng chung (phần form ~470 dòng trong
// `RebuildCatalogPage.tsx`, trước 15/08/2026 KHÔNG có test nào).
//
// Vì sao lái qua `RebuildCatalogPage` chứ không import thẳng `CatalogDrawer`: drawer chỉ là một
// nửa của hợp đồng — nửa kia là cái màn truyền vào (`existing` null hay không, `onSaved` nhận gì).
// Lái qua màn thì lưới này sống sót qua đợt tách file: tách xong `RebuildCatalogPage.tsx` còn lại
// một barrel, đường import không đổi một chữ.
//
// Cái được KHOÁ ở đây là HỢP ĐỒNG GỬI LÊN — body POST/PUT đúng khoá, đúng KIỂU, và ô bị ẩn thì
// KHÔNG gửi. Soi cái hiện ra trên màn thôi là không đủ: ô số gửi lên dạng chuỗi vẫn "nhìn đúng".
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RebuildCatalogPage, type CatalogConfig } from "../RebuildCatalogPage";
import { AuthContext, type AuthState } from "../../auth/AuthContext";
import type { Row } from "../../api/rebuildCatalog";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

interface Goi { method: string; path: string; url: URL; body: Record<string, unknown> | null }

/** 3 dòng sẵn có: CD-001…CD-003 ⇒ mã gợi ý cho bản mới là CD-0004. */
function duLieu(): Row[] {
  return [1, 2, 3].map((i) => ({
    id: i,
    ma: `CD-${String(i).padStart(3, "0")}`,
    ten: `Công đoạn ${i}`,
    ghi_chu: "",
  }));
}

/** Giả lập backend danh mục: GET trả phong bì `{items,total,page,size}` có lọc `q`; POST/PUT trả
 *  bản ghi và GHI LẠI body để test soi. */
function stubApi(rows: Row[] = duLieu()) {
  const goi: Goi[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const u = new URL(String(url), "http://localhost:8000");
    const method = (init?.method ?? "GET").toUpperCase();
    let body: Record<string, unknown> | null = null;
    if (typeof init?.body === "string") {
      try { body = JSON.parse(init.body); } catch { body = null; }
    }
    goi.push({ method, path: u.pathname, url: u, body });

    const ok = (data: unknown) => Promise.resolve(new Response(
      JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } },
    ));

    if (method === "POST") return ok({ id: 99, ...(body ?? {}) });
    if (method === "PUT") return ok({ id: 7, ...(body ?? {}) });
    if (method === "DELETE") return ok({});

    // Từ điển biến của ô công thức: trả RỖNG. Đổ danh mục vào đây thì `b.loai.includes(...)` nổ,
    // vì dòng danh mục không có trường `loai` dạng mảng.
    if (u.pathname === "/api/bien-cong-thuc") return ok({ items: [] });

    const q = (u.searchParams.get("q") ?? "").toLowerCase();
    const khop = rows.filter((r) => !q || `${r.ma} ${r.ten}`.toLowerCase().includes(q));
    const size = Math.min(Number(u.searchParams.get("size") ?? 50), 200);
    const page = Number(u.searchParams.get("page") ?? 1);
    return ok({ items: khop.slice((page - 1) * size, page * size), total: khop.length, page, size });
  }));
  return goi;
}

function moMan(config: CatalogConfig, rows?: Row[]) {
  const goi = stubApi(rows);
  render(
    <AuthContext.Provider value={AUTH}>
      <RebuildCatalogPage config={config} />
    </AuthContext.Provider>,
  );
  return goi;
}

/** Chỉ soi TRONG drawer — ngoài kia bảng danh sách cũng có chữ "Mã", "Tên". */
const drawer = () => within(screen.getByRole("dialog"));

/** Body của lời gọi ghi (POST/PUT) gần nhất. */
function bodyGhi(goi: Goi[]): Goi {
  const ds = goi.filter((g) => g.method === "POST" || g.method === "PUT");
  return ds[ds.length - 1];
}
const soLanGhi = (goi: Goi[]) => goi.filter((g) => g.method === "POST" || g.method === "PUT").length;

const CO_BAN: CatalogConfig = {
  title: "Công đoạn",
  prefix: "/api/cong-doan",
  columns: [{ key: "ghi_chu", label: "Ghi chú" }],
  fields: [],
};

/** Mở drawer TẠO MỚI. Chờ mã gợi ý về trước khi trả — không chờ thì lời gợi ý rơi xuống SAU khi
 *  test đã gõ mã của mình, và ô mã nhảy giá trị giữa chừng. */
async function moDrawerTao(user: ReturnType<typeof userEvent.setup>, choMa = true) {
  await user.click(await screen.findByRole("button", { name: /Thêm công đoạn/ }));
  await screen.findByRole("dialog");
  if (choMa) {
    await waitFor(() =>
      expect((drawer().getByPlaceholderText("Mã...") as HTMLInputElement).value).toBe("CD-0004"));
  }
}

describe("CatalogDrawer — form của màn danh mục dùng chung", () => {
  it("bày ĐỦ ô đã khai, gom theo đúng nhóm", async () => {
    const user = userEvent.setup();
    moMan({
      ...CO_BAN,
      fields: [
        { key: "nhom", label: "Nhóm", type: "text", group: "Phân loại" },
        { key: "so_mau", label: "Số màu", type: "number", group: "Phân loại" },
        { key: "ghi_chu", label: "Ghi chú", type: "text", group: "Khác" },
      ],
    });
    await moDrawerTao(user);

    // Mã + Tên luôn có, không phải khai trong `fields`.
    for (const nhan of [/^Mã/, /^Tên/, /^Nhóm/, /^Số màu/, /^Ghi chú/]) {
      expect(drawer().getByLabelText(nhan)).toBeTruthy();
    }
    // Tiêu đề nhóm — khai `group` thì phải mọc section, không đổ một mạch.
    expect(drawer().getByText("Phân loại")).toBeTruthy();
    expect(drawer().getByText("Khác")).toBeTruthy();
  });

  it("`autoCode` thì KHÔNG bày ô Mã, và body POST KHÔNG mang `ma`", async () => {
    const user = userEvent.setup();
    const goi = moMan({
      ...CO_BAN,
      autoCode: true,
      fields: [{ key: "ghi_chu", label: "Ghi chú", type: "text" }],
    });
    await moDrawerTao(user, false);

    expect(drawer().queryByPlaceholderText("Mã...")).toBeNull();
    expect(drawer().queryByLabelText(/^Mã/)).toBeNull();

    await user.type(drawer().getByLabelText(/^Tên/), "Bế tay");
    await user.click(drawer().getByRole("button", { name: "Tạo mới" }));

    await waitFor(() => expect(soLanGhi(goi)).toBe(1));
    const ghi = bodyGhi(goi);
    expect(ghi.method).toBe("POST");
    expect(ghi.path).toBe("/api/cong-doan");
    expect(ghi.body).not.toHaveProperty("ma");
    expect(ghi.body?.ten).toBe("Bế tay");
  });

  it("body POST đúng KIỂU: ô số ra số, ô công tắc ra boolean, mã viết HOA", async () => {
    const user = userEvent.setup();
    const goi = moMan({
      ...CO_BAN,
      fields: [
        { key: "so_mau", label: "Số màu", type: "number" },
        { key: "cho_phep", label: "Cho phép", type: "checkbox", default: false },
      ],
    });
    await moDrawerTao(user);

    const oMa = drawer().getByPlaceholderText("Mã...") as HTMLInputElement;
    await user.clear(oMa);
    await user.type(oMa, "cd-900");        // gõ thường → ô tự viết hoa
    expect(oMa.value).toBe("CD-900");

    await user.type(drawer().getByLabelText(/^Tên/), "Cán màng");
    await user.type(drawer().getByLabelText(/^Số màu/), "4");
    await user.click(drawer().getByLabelText(/^Cho phép/));

    await user.click(drawer().getByRole("button", { name: "Tạo mới" }));
    await waitFor(() => expect(soLanGhi(goi)).toBe(1));

    const b = bodyGhi(goi).body!;
    expect(b.ma).toBe("CD-900");
    expect(b.ten).toBe("Cán màng");
    // Đây là chỗ dễ vỡ nhất: ô number bind vào chuỗi, quên `Number()` là gửi lên "4".
    expect(b.so_mau).toBe(4);
    expect(typeof b.so_mau).toBe("number");
    expect(b.cho_phep).toBe(true);
  });

  it("sửa bản ghi cũ: PUT đúng id, ô Mã KHÓA", async () => {
    const user = userEvent.setup();
    const rows: Row[] = [{ id: 7, ma: "CD-007", ten: "Bế", ghi_chu: "cũ" }];
    const goi = moMan({ ...CO_BAN, fields: [{ key: "ghi_chu", label: "Ghi chú", type: "text" }] }, rows);

    await user.click(await screen.findByText("Bế"));
    await screen.findByRole("dialog");

    const oMa = drawer().getByPlaceholderText("Mã...") as HTMLInputElement;
    expect(oMa.value).toBe("CD-007");
    expect(oMa).toBeDisabled();

    const oTen = drawer().getByLabelText(/^Tên/);
    await user.clear(oTen);
    await user.type(oTen, "Bế nổi");
    await user.click(drawer().getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(soLanGhi(goi)).toBe(1));
    const ghi = bodyGhi(goi);
    expect(ghi.method).toBe("PUT");
    expect(ghi.path).toBe("/api/cong-doan/7");     // đúng id bản ghi, không phải id nào khác
    expect(ghi.body?.ten).toBe("Bế nổi");
    expect(ghi.body?.ma).toBe("CD-007");            // ô khoá nhưng VẪN gửi lên
  });

  it("`tabsKhai`: tab không còn ô nào để hiện thì BỎ HẲN, không bày ra rồi mở ra trắng", async () => {
    const user = userEvent.setup();
    moMan({
      ...CO_BAN,
      tabsKhai: [
        { id: "chung", label: "Thông tin chung", groups: ["Phân loại"] },
        { id: "kho", label: "Khổ & Vùng in", groups: ["Khổ"] },
        { id: "rong", label: "Tab rỗng", groups: ["Nhóm không ai khai"] },
      ],
      fields: [
        { key: "nhom", label: "Nhóm", type: "text", group: "Phân loại" },
        { key: "kho_rong", label: "Khổ rộng", type: "number", group: "Khổ" },
      ],
    });
    await moDrawerTao(user);

    expect(drawer().getByRole("button", { name: "Thông tin chung" })).toBeTruthy();
    expect(drawer().getByRole("button", { name: "Khổ & Vùng in" })).toBeTruthy();
    expect(drawer().queryByRole("button", { name: "Tab rỗng" })).toBeNull();

    // Tab đầu đang mở → chỉ thấy ô của nhóm đó; bấm sang tab hai mới thấy ô bên kia.
    expect(drawer().getByLabelText(/^Nhóm/)).toBeTruthy();
    expect(drawer().queryByLabelText(/^Khổ rộng/)).toBeNull();
    await user.click(drawer().getByRole("button", { name: "Khổ & Vùng in" }));
    expect(drawer().getByLabelText(/^Khổ rộng/)).toBeTruthy();
  });

  // Esc là phím của lớp TRÊN CÙNG. Drawer gần như luôn là lớp DƯỚI, nên nó phải biết nhường.
  // Bản đầu của vỏ drawer dùng chung (15/08/2026) nghe Esc vô điều kiện: mở popover "Cú pháp"
  // trong ô công thức rồi bấm Esc là đóng luôn cả drawer — mất sạch thứ đang khai, mà người dùng
  // chỉ định đóng một cái popover. Cả hai cùng nghe trên `document` nên `stopPropagation` không
  // cứu được (nó không chặn listener cùng một node).
  it("Esc: popover “Cú pháp” đang mở thì chỉ đóng popover, drawer VẪN mở", async () => {
    const user = userEvent.setup();
    moMan({ ...CO_BAN, fields: [{ key: "cong_thuc", label: "Công thức", type: "formula" }] });
    await moDrawerTao(user);

    await user.click(screen.getByRole("button", { name: "Công thức tính giá" }));
    await user.click(screen.getByRole("button", { name: /Cú pháp/ }));
    expect(screen.getByRole("dialog", { name: "Cú pháp công thức" })).toBeTruthy();

    await user.keyboard("{Escape}");
    // Popover biến mất…
    expect(screen.queryByRole("dialog", { name: "Cú pháp công thức" })).toBeNull();
    // …còn drawer thì KHÔNG. Đây là cả nội dung của bài test.
    expect(screen.getByRole("button", { name: "Tạo mới" })).toBeTruthy();
  });

  it("ô bị `showIf` ẩn thì KHÔNG lọt vào body, dù trong form vẫn còn giá trị mặc định", async () => {
    const user = userEvent.setup();
    const goi = moMan({
      ...CO_BAN,
      fields: [
        { key: "loai", label: "Loại", type: "select",
          options: [{ value: "in", label: "In" }, { value: "sau_in", label: "Sau in" }] },
        // Chỉ hỏi khi Loại = "in". Có `default` nên form LUÔN cầm giá trị — nếu submit đọc
        // `config.fields` thay vì `visibleFields` thì số này lọt lên server, im lặng.
        { key: "so_mau", label: "Số màu", type: "number", default: 4,
          showIf: (f) => f.loai === "in" },
      ],
    });
    await moDrawerTao(user);

    expect(drawer().queryByLabelText(/^Số màu/)).toBeNull();
    await user.type(drawer().getByLabelText(/^Tên/), "Gấp tay");
    await user.click(drawer().getByRole("button", { name: "Tạo mới" }));

    await waitFor(() => expect(soLanGhi(goi)).toBe(1));
    expect(bodyGhi(goi).body).not.toHaveProperty("so_mau");

    // Lưu xong drawer đóng — mở lại, lần này chọn "In" để ô hiện ra. Chứng minh ca trên không
    // phải do field chết mà đúng là do `showIf`.
    await user.click(await screen.findByRole("button", { name: /Thêm công đoạn/ }));
    await screen.findByRole("dialog");
    await user.selectOptions(drawer().getByLabelText(/^Loại/), "in");
    expect(drawer().getByLabelText(/^Số màu/)).toBeTruthy();
    await user.type(drawer().getByLabelText(/^Tên/), "In offset");
    await user.click(drawer().getByRole("button", { name: "Tạo mới" }));

    await waitFor(() => expect(soLanGhi(goi)).toBe(2));
    expect(bodyGhi(goi).body?.so_mau).toBe(4);
  });
});
