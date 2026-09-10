import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// Giờ chờ của `findBy*` / `waitFor`: 1.000 ms MẶC ĐỊNH là quá chặt cho runner CI hai nhân chạy 40+
// file song song. Không phải màn nào chậm — worker bị BỎ ĐÓI: `userEvent.click` nhường event loop
// sau mỗi cú bấm, và khi cả chục worker tranh hai nhân thì một lượt nhường có thể mất vài trăm ms
// đồng hồ thật, đủ để đồng hồ 1.000 ms cạn trước khi vòng dò kịp chạy lần thứ hai.
//
// Tái hiện được tại chỗ: chạy `LenhSxHoSoView.test.tsx` trong lúc ba tiến trình vitest full-suite
// khác đang chạy ⇒ 4/9 bài đỏ, mỗi bài đứng đúng ở mốc hết giờ. Máy rảnh thì cùng bài xanh kể cả
// khi ép `findByText` xuống `timeout: 1` — tức DOM đã đúng ngay, chỉ là không ai kịp nhìn.
//
// 5.000 ms là ngưỡng chờ, KHÔNG phải chỗ giấu bài hỏng: bài hỏng thật vẫn đỏ, chỉ chậm hơn 4 giây.
configure({ asyncUtilTimeout: 5000 });

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
