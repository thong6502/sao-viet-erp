// N28 (gộp vào Task 14) — ruling C109 sau lượt rà vòng 1: mẹo bọc `Blob` vào `File` KHÔNG đóng
// được N28 trên đường `window.open` mà `phieuCongNghePdf` đang dùng (Chromium dựng tên "Lưu" của
// trình xem PDF built-in từ uuid trong chính `blob:` URL, không đọc `File.name`) — xem docstring
// `blobUrlComTen`/`phieuCongNghePdf` ở `client.ts`. KHÔNG CÓ CÁCH nào chứng minh "tên lúc Lưu đúng"
// ở tầng unit test (không quan sát được hộp thoại Lưu thật của trình duyệt), nên bài dưới đây
// KHÔNG khẳng định điều đó.
//
// Cái bài NÀY thật sự canh: hai hàm thuần `tenFileTuHeader` (tách tên khỏi header) và việc
// `blobUrlComTen` có bọc đúng `File` với đúng tên đã tách/lùi hay không — hành vi có thật của CODE
// CỦA TA, kiểm qua tham số THẬT truyền vào `URL.createObjectURL` (không suy luận từ chuỗi blob URL
// trả về — chuỗi đó không mang thông tin tên, và `jsdom` cũng không có `URL.createObjectURL` thật
// để so). Hàm `blobUrlComTen` vẫn có ích cho đường tải nào đó dùng `<a download>` sau này — đó là
// lý do giữ lại thay vì revert.
import { describe, expect, it } from "vitest";

import { tenFileTuHeader } from "./client";
import { api } from "./client";

/** Fetch giả trả một PDF, gắn `Content-Disposition` theo đúng dạng route
 *  `phieu_cong_nghe_pdf` (`backend/app/routers/lenh_san_xuat.py`) phát ra. */
function fetchGia(contentDisposition: string | null) {
  return (async () => {
    const headers = new Headers({ "content-type": "application/pdf" });
    if (contentDisposition) headers.set("Content-Disposition", contentDisposition);
    return {
      ok: true,
      status: 200,
      headers,
      blob: async () => new Blob(["%PDF-1.4 nội dung giả"], { type: "application/pdf" }),
    } as unknown as Response;
  }) as typeof fetch;
}

describe("tenFileTuHeader · tách tên file khỏi Content-Disposition", () => {
  it("dạng backend thật sự phát ra (`inline; filename=\"...\"`) ⇒ tách đúng tên", () => {
    expect(tenFileTuHeader('inline; filename="phieu-cong-nghe-LSX26-0031.pdf"')).toBe(
      "phieu-cong-nghe-LSX26-0031.pdf",
    );
  });

  it("không ngoặc kép cũng tách được (RFC cho phép cả hai dạng)", () => {
    expect(tenFileTuHeader("attachment; filename=bao-cao.pdf")).toBe("bao-cao.pdf");
  });

  it("header rỗng/thiếu ⇒ null, KHÔNG ném lỗi", () => {
    expect(tenFileTuHeader(null)).toBeNull();
    expect(tenFileTuHeader("inline")).toBeNull();
  });
});

describe("api.lenhSanXuat.phieuCongNghePdf · bọc File đúng tên (KHÔNG chứng minh tên lúc Lưu — xem C109)", () => {
  it("⭐ Content-Disposition có tên ⇒ object URL dựng từ FILE mang ĐÚNG tên đó, không phải Blob trần", async () => {
    const cu = globalThis.fetch;
    const goi = { obj: null as unknown };
    // jsdom không có `URL.createObjectURL` thật — gán thẳng một bản giả để BẮT tham số thật sự
    // được truyền vào, đó mới là thứ quyết định tên file lúc "Lưu", không phải chuỗi blob URL trả về.
    const cuCreate = URL.createObjectURL;
    URL.createObjectURL = ((obj: Blob) => {
      goi.obj = obj;
      return "blob:fake-url";
    }) as typeof URL.createObjectURL;
    globalThis.fetch = fetchGia('inline; filename="phieu-cong-nghe-LSX26-0031.pdf"');
    try {
      await api.lenhSanXuat.phieuCongNghePdf("tok", 31);
      expect(goi.obj).toBeInstanceOf(File);
      expect((goi.obj as File).name).toBe("phieu-cong-nghe-LSX26-0031.pdf");
      expect((goi.obj as File).type).toBe("application/pdf");
    } finally {
      globalThis.fetch = cu;
      URL.createObjectURL = cuCreate;
    }
  });

  it("⭐ Content-Disposition thiếu/lạ ⇒ lùi về tên dự phòng `phieu-cong-nghe-<id>.pdf`, vẫn là FILE có tên", async () => {
    const cu = globalThis.fetch;
    const goi = { obj: null as unknown };
    const cuCreate = URL.createObjectURL;
    URL.createObjectURL = ((obj: Blob) => {
      goi.obj = obj;
      return "blob:fake-url";
    }) as typeof URL.createObjectURL;
    globalThis.fetch = fetchGia(null); // header vắng — máy chủ hỏng/proxy nuốt mất
    try {
      await api.lenhSanXuat.phieuCongNghePdf("tok", 31);
      expect(goi.obj).toBeInstanceOf(File);
      expect((goi.obj as File).name).toBe("phieu-cong-nghe-31.pdf");
    } finally {
      globalThis.fetch = cu;
      URL.createObjectURL = cuCreate;
    }
  });
});
