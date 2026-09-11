/**
 * Tự in bản báo giá khi có quyền `export` — và ĐÓNG được khung xem trước sau khi in.
 *
 * Lỗi thật gặp trên dev 10/09/2026: bấm "Xem bản in" lần đầu thì in ra, nhưng khung xem trước
 * KHÔNG đóng (nó bị `q-print-silent` ẩn nên nhìn như không có gì). `showPrint` vẫn còn `true`
 * ⇒ mọi lần bấm "Xem bản in" sau đó là vô hiệu, nút chết hẳn cho tới khi F5. Người dùng gặp
 * sau khi xóa ảnh rồi thêm ảnh mới vì đó là lúc họ bấm xem bản in lần thứ hai.
 *
 * Gốc rễ: `firedRef` chặn lần chạy thứ hai của effect dưới StrictMode, nhưng cleanup của lần
 * chạy thứ nhất ĐÃ gỡ listener `afterprint` — lần hai trả về sớm nên không gắn lại listener
 * nào. Vì vậy test dưới đây BẮT BUỘC bọc StrictMode.
 */
import { StrictMode } from "react";
import { render } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useInTuDong } from "./bao-gia-in-tu-dong";

function Probe({ canDownload, onClose }: { canDownload: boolean; onClose: () => void }) {
  useInTuDong(canDownload, onClose);
  return null;
}

/** Dựng đúng cấu trúc DOM mà hook đi tìm: `.qpdf` chứa ảnh letterhead + ảnh minh họa. */
function dungBanIn(soAnhMinhHoa: number): HTMLImageElement[] {
  const qpdf = document.createElement("div");
  qpdf.className = "qpdf";
  const anh: HTMLImageElement[] = [];
  for (let i = 0; i < soAnhMinhHoa; i += 1) {
    const td = document.createElement("td");
    td.className = "q-anh";
    const img = document.createElement("img");
    // jsdom không tải ảnh thật; ép `complete=false` cho giống ảnh vừa upload chưa vào cache.
    Object.defineProperty(img, "complete", { value: false, configurable: true });
    td.appendChild(img);
    qpdf.appendChild(td);
    anh.push(img);
  }
  document.body.appendChild(qpdf);
  return anh;
}

let inRa: ReturnType<typeof vi.fn>;

beforeEach(() => {
  inRa = vi.fn();
  Object.defineProperty(window, "print", { value: inRa, configurable: true, writable: true });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("useInTuDong", () => {
  it("in xong (afterprint) thì ĐÓNG khung xem trước — kể cả dưới StrictMode", () => {
    const dong = vi.fn();
    render(<Probe canDownload onClose={dong} />, { wrapper: StrictMode });

    expect(inRa).toHaveBeenCalledTimes(1); // StrictMode gọi effect 2 lần nhưng chỉ in MỘT

    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(dong).toHaveBeenCalledTimes(1);
  });

  it("còn ảnh minh họa chưa tải xong thì CHƯA in, tải xong hết mới in", () => {
    const anh = dungBanIn(2);
    render(<Probe canDownload onClose={vi.fn()} />, { wrapper: StrictMode });

    expect(inRa).not.toHaveBeenCalled();
    act(() => {
      anh[0].dispatchEvent(new Event("load"));
    });
    expect(inRa).not.toHaveBeenCalled();
    act(() => {
      anh[1].dispatchEvent(new Event("load"));
    });
    expect(inRa).toHaveBeenCalledTimes(1);
  });

  it("ảnh hỏng (404) cũng phải cho in, không treo bản in", () => {
    const anh = dungBanIn(1);
    render(<Probe canDownload onClose={vi.fn()} />, { wrapper: StrictMode });

    act(() => {
      anh[0].dispatchEvent(new Event("error"));
    });
    expect(inRa).toHaveBeenCalledTimes(1);
  });

  it("không có quyền export thì chỉ xem trước, KHÔNG tự in", () => {
    const dong = vi.fn();
    render(<Probe canDownload={false} onClose={dong} />, { wrapper: StrictMode });

    expect(inRa).not.toHaveBeenCalled();
    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(dong).not.toHaveBeenCalled();
  });

  it("gỡ khung xem trước rồi thì afterprint muộn KHÔNG gọi lại onClose", () => {
    const dong = vi.fn();
    const { unmount } = render(<Probe canDownload onClose={dong} />, { wrapper: StrictMode });
    unmount();

    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(dong).not.toHaveBeenCalled();
  });
});
