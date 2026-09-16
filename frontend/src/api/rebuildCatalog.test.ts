import { afterEach, describe, expect, it, vi } from "vitest";

import { crud } from "./rebuildCatalog";

// Token giả mang `sub` — khoá nhớ theo NGƯỜI chứ không theo chuỗi token.
const tok = (sub: number, doi = "") => `h.${btoa(JSON.stringify({ sub: String(sub), doi }))}.s`;

/** Giả backend: mỗi GET trả `{items}` đánh số theo lượt gọi, để phân biệt bản nhớ với bản mới. */
function giaBackend() {
  let luot = 0;
  const fetchGia = vi.fn(async () => {
    luot += 1;
    return new Response(JSON.stringify({ items: [{ id: luot, ma: `M${luot}`, ten: `lượt ${luot}` }] }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchGia);
  return fetchGia;
}

afterEach(() => vi.unstubAllGlobals());

// Mỗi bài một prefix riêng: bộ nhớ nằm ở cấp module, dùng chung prefix là bài sau đọc nhớ của bài trước.
describe("crud().thamChieu — danh sách cho ô chọn trong drawer", () => {
  it("mở lần hai có bản nhớ NGAY, vẫn hỏi lại nền rồi trả bản mới", async () => {
    const f = giaBackend();
    const api = crud("/api/tc-mo-lai");
    const lan1 = api.thamChieu(tok(1));
    expect(lan1.nho).toBeUndefined();
    expect(api.daNho(tok(1))).toBeUndefined();
    expect((await lan1.moi)[0].ten).toBe("lượt 1");
    // `daNho` chỉ đọc nhớ — không bắn thêm request nào.
    expect(api.daNho(tok(1))?.[0].ten).toBe("lượt 1");
    expect(f).toHaveBeenCalledTimes(1);

    const lan2 = api.thamChieu(tok(1, "da-xoay"));
    expect(lan2.nho?.[0].ten).toBe("lượt 1");
    expect((await lan2.moi)[0].ten).toBe("lượt 2");
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("hai chỗ hỏi cùng lúc (StrictMode chạy effect hai lần) dùng chung MỘT request", async () => {
    const f = giaBackend();
    const api = crud("/api/tc-trung");
    const a = api.thamChieu(tok(1), { active: true });
    const b = api.thamChieu(tok(1), { active: true });
    expect(await a.moi).toEqual(await b.moi);
    expect(f).toHaveBeenCalledTimes(1);
    // `batMoi` thì KHÔNG đi nhờ request đang bay.
    const c = api.thamChieu(tok(1), { active: true });
    api.thamChieu(tok(1), { active: true }, true);
    await c.moi;
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("người khác đăng nhập thì không thấy bản nhớ của người trước", async () => {
    giaBackend();
    const api = crud("/api/tc-nguoi");
    await api.thamChieu(tok(1)).moi;
    expect(api.thamChieu(tok(2)).nho).toBeUndefined();
  });

  it("ghi vào danh mục thì bỏ nhớ của đúng danh mục đó", async () => {
    giaBackend();
    const may = crud("/api/tc-may");
    const to = crud("/api/tc-may-to");            // prefix trùng ĐẦU chuỗi — không được xoá lây
    await may.thamChieu(tok(1), { size: 200 }).moi;
    await to.thamChieu(tok(1)).moi;
    await may.datActive(tok(1), 1, false);
    expect(may.thamChieu(tok(1), { size: 200 }).nho).toBeUndefined();
    expect(to.thamChieu(tok(1)).nho).toBeDefined();
  });
});
