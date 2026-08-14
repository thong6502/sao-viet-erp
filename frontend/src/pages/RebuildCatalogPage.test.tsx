// Phân trang của MÀN DANH MỤC DÙNG CHUNG (10 màn "Cấu hình danh mục" đều là component này).
//
// Điều quan trọng nhất cần khoá: trang được cắt Ở MÁY CHỦ. Bản đầu ngày 14/08/2026 cắt trong JS
// — vẫn kéo cả danh mục về (còn lặp thêm request khi danh mục vượt trần `size=200`), tức là làm
// nặng DB chứ không nhẹ đi. Nên test soi cả REQUEST gửi lên, không chỉ soi cái hiện ra.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RebuildCatalogPage, type CatalogConfig } from "./RebuildCatalogPage";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import type { Row } from "../api/rebuildCatalog";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

const CONFIG: CatalogConfig = {
  title: "Công đoạn",
  prefix: "/api/cong-doan",
  columns: [{ key: "ghi_chu", label: "Ghi chú" }],
  fields: [{ key: "ghi_chu", label: "Ghi chú", type: "text" }],
};

/** Bản có TAB LỌC — số trên tab phải lấy từ `facets` của máy chủ. */
const CONFIG_TAB: CatalogConfig = {
  ...CONFIG,
  facet: { key: "nhom", values: [{ value: "in", label: "In" }, { value: "sau_in", label: "Sau in" }] },
};

/** N dòng danh mục: CD-001 "Công đoạn 1" (lẻ = nhóm in, chẵn = sau in). */
function duLieu(n: number): Row[] {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    ma: `CD-${String(i + 1).padStart(3, "0")}`,
    ten: `Công đoạn ${i + 1}`,
    nhom: i % 2 === 0 ? "in" : "sau_in",
    ghi_chu: "",
  }));
}

/** Giả lập endpoint danh mục: lọc `q`/`nhom` rồi cắt `page`/`size` — y như backend. */
function stubApi(tong: number) {
  const tatCa = duLieu(tong);
  const goi: URL[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const u = new URL(String(url), "http://localhost:8000");
    goi.push(u);
    const q = (u.searchParams.get("q") ?? "").toLowerCase();
    const nhom = u.searchParams.get("nhom");
    const khop = tatCa.filter((r) =>
      (!q || `${r.ma} ${r.ten}`.toLowerCase().includes(q)) && (!nhom || r.nhom === nhom));
    const size = Math.min(Number(u.searchParams.get("size") ?? 50), 200);
    const page = Number(u.searchParams.get("page") ?? 1);
    // `facets` KHÔNG lọc theo tab (giống router thật), nhưng CÓ lọc theo `q`.
    const theoQ = tatCa.filter((r) => !q || `${r.ma} ${r.ten}`.toLowerCase().includes(q));
    const facets: Record<string, number> = {};
    for (const r of theoQ) facets[String(r.nhom)] = (facets[String(r.nhom)] ?? 0) + 1;
    return Promise.resolve(new Response(
      JSON.stringify({
        items: khop.slice((page - 1) * size, page * size),
        total: khop.length, page, size, facets,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  }));
  return goi;
}

function moMan(config: CatalogConfig = CONFIG) {
  return render(
    <AuthContext.Provider value={AUTH}>
      <RebuildCatalogPage config={config} />
    </AuthContext.Provider>,
  );
}

/** Mã của các dòng đang hiện trên bảng (cột đầu). */
function maDangHien(): string[] {
  return screen.getAllByTitle(/^CD-\d{3}$/).map((el) => el.textContent ?? "");
}

/** Request danh sách (bỏ qua các lời gọi khác, vd dữ liệu phụ theo dòng). */
function reqDanhSach(goi: URL[]): URL[] {
  return goi.filter((u) => u.pathname === "/api/cong-doan");
}

/** Request danh sách GẦN NHẤT. */
function reqCuoi(goi: URL[]): URL {
  const ds = reqDanhSach(goi);
  return ds[ds.length - 1];
}

describe("RebuildCatalogPage — phân trang 20 dòng/trang Ở MÁY CHỦ", () => {
  it("chỉ xin 20 dòng mỗi trang, không kéo cả danh mục về", async () => {
    const goi = stubApi(45);
    moMan();

    await screen.findByText("CD-001");
    const req = reqDanhSach(goi);
    expect(req).toHaveLength(1);                                   // đúng MỘT lượt gọi
    expect(req[0].searchParams.get("size")).toBe("20");
    expect(req[0].searchParams.get("page")).toBe("1");
    expect(maDangHien()).toHaveLength(20);
  });

  it("bấm Sau là XIN TRANG 2 từ máy chủ, không cắt lại trong JS", async () => {
    const goi = stubApi(45);
    const user = userEvent.setup();
    moMan();

    await screen.findByText("CD-001");
    expect(screen.getByText(/Tổng 45 bản ghi/).textContent).toContain("Trang 1/3");

    await user.click(screen.getByRole("button", { name: "Sau" }));
    await waitFor(() => expect(maDangHien()[0]).toBe("CD-021"));
    expect(reqCuoi(goi).searchParams.get("page")).toBe("2");
    expect(maDangHien()[19]).toBe("CD-040");

    await user.click(screen.getByRole("button", { name: "Sau" }));
    await waitFor(() => expect(maDangHien()).toHaveLength(5));     // trang cuối còn 5 dòng
    expect(screen.getByRole("button", { name: "Sau" })).toBeDisabled();
  });

  it("gõ tìm thì GỬI `q` lên máy chủ và kéo về trang 1", async () => {
    const goi = stubApi(45);
    const user = userEvent.setup();
    moMan();

    await screen.findByText("CD-001");
    await user.click(screen.getByRole("button", { name: "Sau" }));   // đang đứng trang 2
    await waitFor(() => expect(maDangHien()[0]).toBe("CD-021"));

    // "Công đoạn 44" nằm ở trang 3 — gõ tìm phải ra, không được "không tìm thấy" vì ngoài trang.
    await user.type(screen.getByPlaceholderText("Tìm mã / tên…"), "đoạn 44");
    await waitFor(() => expect(maDangHien()).toEqual(["CD-044"]));

    const cuoi = reqCuoi(goi);
    expect(cuoi.searchParams.get("q")).toBe("đoạn 44");
    expect(cuoi.searchParams.get("page")).toBe("1");
    expect(screen.getByText(/Tổng 1 bản ghi/)).toBeTruthy();
  });

  it("gõ liên tục chỉ tốn MỘT request (chờ gõ xong mới hỏi)", async () => {
    const goi = stubApi(45);
    const user = userEvent.setup();
    moMan();

    await screen.findByText("CD-001");
    const truoc = reqDanhSach(goi).length;
    await user.type(screen.getByPlaceholderText("Tìm mã / tên…"), "đoạn 12");
    await waitFor(() => expect(maDangHien()).toEqual(["CD-012"]));
    expect(reqDanhSach(goi).length - truoc).toBe(1);   // 7 phím = 1 request, không phải 7
  });

  it("tab lọc: số trên tab lấy từ `facets` của máy chủ, bấm tab thì gửi bộ lọc lên", async () => {
    const goi = stubApi(45);
    const user = userEvent.setup();
    moMan(CONFIG_TAB);

    await screen.findByText("CD-001");
    const tabs = screen.getByRole("button", { name: /^Tất cả/ });
    expect(tabs.textContent).toContain("45");                        // tổng, không phải 20 dòng đang xem
    expect(screen.getByRole("button", { name: /^In/ }).textContent).toContain("23");
    expect(screen.getByRole("button", { name: /^Sau in/ }).textContent).toContain("22");

    await user.click(screen.getByRole("button", { name: /^Sau in/ }));
    await waitFor(() => expect(reqCuoi(goi).searchParams.get("nhom")).toBe("sau_in"));
    await waitFor(() => expect(screen.getByText(/Tổng 22 bản ghi/)).toBeTruthy());
    // Đang đứng ở tab con nhưng số cạnh tiêu đề vẫn là tổng cả danh mục.
    expect(within(screen.getByRole("main")).getByText("45 mục")).toBeTruthy();
  });

  it("bảng rỗng thì KHÔNG hiện chân phân trang (khối “chưa có…” nói thay rồi)", async () => {
    stubApi(0);
    moMan();

    await screen.findByText(/Chưa có công đoạn nào/);
    expect(screen.queryByText(/Tổng .* bản ghi/)).toBeNull();
  });
});
