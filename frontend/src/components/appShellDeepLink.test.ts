// `docDeepLinkLsx` là điểm khởi đầu của CẢ BA tình huống brief Task 14 đòi kiểm (Bước 4 / ruling
// C106): sai một khoá ở đây là deep link câm hoặc mở nhầm lệnh mà không ai thấy lỗi ở đâu.
import { describe, expect, it } from "vitest";

import { docDeepLinkLsx } from "./appShellDeepLink";

describe("docDeepLinkLsx · phân tích hash QR phiếu công nghệ", () => {
  it("`#lsx=<id>&pv=<n>` ⇒ tách đúng cả hai", () => {
    expect(docDeepLinkLsx("#lsx=42&pv=3")).toEqual({ lsxId: 42, pv: 3 });
  });

  it("thiếu `pv` (QR in trước khi lệnh có `phien_ban`) ⇒ `pv: null`, KHÔNG rớt cả deep link", () => {
    expect(docDeepLinkLsx("#lsx=42&pv=")).toEqual({ lsxId: 42, pv: null });
    expect(docDeepLinkLsx("#lsx=42")).toEqual({ lsxId: 42, pv: null });
  });

  it("không có khoá `lsx` ⇒ null — kể cả hash QR tem kho `#s=...` (đường KHÁC, đọc ở App.tsx)", () => {
    expect(docDeepLinkLsx("#s=eyJ.abcxyz")).toBeNull();
    expect(docDeepLinkLsx("")).toBeNull();
    expect(docDeepLinkLsx("#")).toBeNull();
  });

  it("id không phải số nguyên dương ⇒ null, không đẩy NaN/0/âm xuống hồ sơ", () => {
    expect(docDeepLinkLsx("#lsx=abc&pv=1")).toBeNull();
    expect(docDeepLinkLsx("#lsx=0&pv=1")).toBeNull();
    expect(docDeepLinkLsx("#lsx=-5&pv=1")).toBeNull();
    expect(docDeepLinkLsx("#lsx=1.5&pv=1")).toBeNull();
  });

  it("`pv` gõ bậy (chữ, số âm) ⇒ coi như không có, KHÔNG kéo cả `lsx` hợp lệ theo", () => {
    expect(docDeepLinkLsx("#lsx=42&pv=abc")).toEqual({ lsxId: 42, pv: null });
    expect(docDeepLinkLsx("#lsx=42&pv=-1")).toEqual({ lsxId: 42, pv: null });
  });
});
