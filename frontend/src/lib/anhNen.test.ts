// jsdom KHÔNG có canvas thật (`toBlob` không chạy) nên ở đây chỉ test HAI NHÁNH LÙI — đúng thứ
// quyết định thợ có tải được ảnh hay không. Phần nén thật phải soi trên trình duyệt.
import { describe, expect, it } from "vitest";
import { coChu, nenAnh, NGUONG_BO_QUA } from "./anhNen";

function fakeFile(ten: string, kieu: string, co: number): File {
  const f = new File([new Uint8Array(1)], ten, { type: kieu });
  Object.defineProperty(f, "size", { value: co });
  return f;
}

describe("nenAnh", () => {
  it("không phải ảnh thì trả nguyên file", async () => {
    const f = fakeFile("bao-gia.pdf", "application/pdf", 9 * 1024 * 1024);
    const kq = await nenAnh(f);
    expect(kq.file).toBe(f);
    expect(kq.daNen).toBe(false);
  });

  it("ảnh nhỏ sẵn thì không nén (nén chỉ làm mờ thêm)", async () => {
    const f = fakeFile("nho.jpg", "image/jpeg", NGUONG_BO_QUA - 1);
    expect((await nenAnh(f)).daNen).toBe(false);
  });

  it("GIF giữ nguyên — nén là mất ảnh động", async () => {
    const f = fakeFile("dong.gif", "image/gif", 5 * 1024 * 1024);
    expect((await nenAnh(f)).file).toBe(f);
  });

  it("giải mã lỗi (HEIC, canvas bị chặn) thì trả FILE GỐC chứ không ném lỗi", async () => {
    // Không có `createImageBitmap` trong jsdom ⇒ đi đúng nhánh catch.
    const f = fakeFile("IMG_0421.heic", "image/heic", 6 * 1024 * 1024);
    const kq = await nenAnh(f);
    expect(kq.file).toBe(f);
    expect(kq.daNen).toBe(false);
    expect(kq.sau).toBe(kq.goc);
  });
});

describe("coChu", () => {
  it("đọc được bằng tiếng Việt", () => {
    expect(coChu(6_500_000)).toBe("6,2 MB");
    expect(coChu(380_000)).toBe("371 KB");
  });
});
