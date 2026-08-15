import { describe, expect, it } from "vitest";

import { ApiError, authed } from "./client";

/** Bọc một Response giả cho `fetch` — chỉ cần `ok`/`status`/`json`. */
function gia(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

async function batLoi(status: number, body: unknown): Promise<ApiError> {
  const cu = globalThis.fetch;
  globalThis.fetch = (async () => gia(status, body)) as typeof fetch;
  try {
    await authed("/api/thu", "tok");
    throw new Error("đáng lẽ phải ném ApiError");
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    return e;
  } finally {
    globalThis.fetch = cu;
  }
}

describe("thông báo lỗi 422", () => {
  it("nêu TÊN TRƯỜNG sai, không nói trống không", async () => {
    // 422 của FastAPI: `detail` là MẢNG. Trước 15/08/2026 chỉ nhánh chuỗi được xử ⇒ mọi lỗi kiểm
    // dữ liệu của cả app hiện đúng câu "Request failed (422)." — người dùng không biết sửa ô nào.
    const e = await batLoi(422, {
      detail: [
        { type: "greater_than", loc: ["body", "he_so_ngoai_dong"], msg: "Input should be greater than 0" },
      ],
    });
    expect(e.status).toBe(422);
    expect(e.message).toContain("he_so_ngoai_dong");
    expect(e.message).not.toContain("Request failed");
  });

  it("gộp nhiều lỗi nhưng CẮT ở 3 — form sai chục ô thì banner dài hơn cả form", async () => {
    const e = await batLoi(422, {
      detail: Array.from({ length: 5 }, (_, i) => ({
        loc: ["body", "dau_viec_dinh_muc", i, "nang_suat_nguoi_gio"],
        msg: "Field required",
      })),
    });
    expect(e.message.split(" · ")).toHaveLength(3);
    expect(e.message).toContain("+2 lỗi nữa");
    // Đường dẫn giữ cả chỉ số dòng — sai ở đầu việc thứ mấy là thứ phải nói ra.
    expect(e.message).toContain("dau_viec_dinh_muc › 0 › nang_suat_nguoi_gio");
  });

  it("`detail` là CHUỖI (lỗi nghiệp vụ 400/409) thì giữ nguyên câu tiếng Việt", async () => {
    const e = await batLoi(409, { detail: "Mã đã tồn tại." });
    expect(e.message).toBe("Mã đã tồn tại.");
  });

  it("thân không phải JSON thì mới rơi về câu chung", async () => {
    const cu = globalThis.fetch;
    globalThis.fetch = (async () => ({
      ok: false, status: 500,
      json: async () => { throw new Error("not json"); },
    }) as unknown as Response) as typeof fetch;
    try {
      await authed("/api/thu", "tok");
      throw new Error("đáng lẽ phải ném");
    } catch (e) {
      expect((e as ApiError).message).toContain("500");
    } finally {
      globalThis.fetch = cu;
    }
  });
});
