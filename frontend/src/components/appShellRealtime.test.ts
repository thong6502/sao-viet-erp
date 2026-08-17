import { describe, expect, it } from "vitest";
import { coTheMoKenhSse } from "./appShellRealtime";

describe("SSE AppShell", () => {
  it("mở kênh cho người chỉ có quyền đọc Bài ghép 2", () => {
    expect(coTheMoKenhSse(new Set(["bai_ghep_2"]))).toBe(true);
  });
});
