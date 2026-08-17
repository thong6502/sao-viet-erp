import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

describe("API Bài ghép 2", () => {
  afterEach(() => vi.restoreAllMocks());

  it("dùng namespace và endpoint riêng, không gọi nhầm module legacy", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0 }),
    } as Response);

    await api.baiGhep2.list("token");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/bai-ghep-2"),
      expect.any(Object),
    );
    expect(fetchMock.mock.calls[0]?.[0]).not.toContain("/api/bai-ghep/");
  });

  it("đọc vật tư hiệu lực và danh sách người phụ trách từ API Bài ghép 2", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
    } as Response);

    await api.baiGhep2.vatTuHieuLuc("token", 42);
    await api.baiGhep2.nguoiPhuTrachOptions("token");

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      expect.stringContaining("/api/bai-ghep-2/42/vat-tu-hieu-luc"),
      expect.stringContaining("/api/bai-ghep-2/nguoi-phu-trach-options"),
    ]);
  });
});
