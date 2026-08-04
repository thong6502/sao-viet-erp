import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// jsdom không có ResizeObserver, mà canvas bài ghép dùng nó để căn vừa khi khung đổi kích thước.
// Stub im lặng: test ở đây kiểm HÀNH VI chọn/gộp và nội dung thẻ, không kiểm phép căn vừa.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverStub);

// `scrollTo` cũng chưa có trong jsdom — `canVua()` gọi nó sau khi đo khung.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = function scrollTo() {};
}
