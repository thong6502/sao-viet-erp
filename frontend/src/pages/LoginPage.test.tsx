// `LoginPage` không được đụng `window.location.hash` — Task 14 (deep link QR) đặt cược sống còn
// vào việc SPA không đổi trang lúc đăng nhập nên hash `#lsx=&pv=` tự sống sót qua lượt login,
// AppShell mới có gì để đọc lúc mount (xem `appShellDeepLink.ts`). Dispatch của task này gọi thẳng
// đây là "giả thuyết, không phải sự thật" — bài canh này biến nó thành điều đã kiểm, không phải
// niềm tin suông.
//
// Sửa vòng 1 (P6): bài canh gốc bên dưới CHỈ DỰNG màn rồi soi hash — không hề bấm gì, không hề đi
// qua `onSubmit`/`AuthContext.login` thật. Nó chứng minh được "render không tự ý đụng hash" (thật,
// giữ lại), nhưng KHÔNG chứng minh được điều brief cần: hash phải sống sót qua đúng ĐƯỜNG THẬT một
// người dùng đi — điền form, bấm nút, `login()` chạy xong. Một bug kiểu "xoá hash trong `onSubmit`
// sau khi `login()` resolve" sẽ không bị bài gốc bắt được vì nó không bao giờ gọi `onSubmit`. Bài
// mới ở describe thứ hai đi ĐÚNG đường đó.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthState } from "../auth/AuthContext";
import { LoginPage } from "./LoginPage";

const FAKE_AUTH: AuthState = {
  status: "anonymous",
  user: null,
  token: null,
  login: async () => {},
  logout: async () => {},
  updateUser: () => {},
  notice: null,
  setNotice: () => {},
};

function ve(auth: AuthState = FAKE_AUTH) {
  return render(
    <AuthContext.Provider value={auth}>
      <LoginPage />
    </AuthContext.Provider>,
  );
}

describe("LoginPage · không đụng window.location.hash", () => {
  beforeEach(() => {
    window.location.hash = "#lsx=42&pv=3";
  });
  afterEach(() => {
    window.location.hash = "";
  });

  it("dựng màn đăng nhập xong, hash deep link QR vẫn nguyên vẹn", () => {
    ve();
    expect(screen.getByRole("heading", { name: "Đăng nhập" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#lsx=42&pv=3");
  });
});

// Sửa vòng 2 (mục C, Ruling C110 — giữ mock, sửa TÊN): tên cũ của describe này ("submit THẬT qua
// AuthContext.login") quá lời — `login` dưới đây là `vi.fn()`, bài chỉ chứng minh được lượt SUBMIT
// của `LoginPage` (đọc form, gọi `login(user, pass)`, không đụng `window.location`), KHÔNG chứng
// minh được thân THẬT của `AuthContext.login` hay lượt `App.tsx` hoán màn sau khi đăng nhập cũng
// vô hại với hash. Chuỗi "hash sống sót qua đăng nhập" hiện được hai bài canh gặp nhau ở giữa: bài
// này (đầu vào — submit không đụng hash) và `AppShell.test.tsx` (đầu ra — AppShell đọc đúng hash
// lúc mount). Dựng thêm một `AuthContext` thật + mock tầng API chỉ để nối liền hai đầu đó bị coi là
// đắt hơn phần rủi ro nó mua (ruling C110). CẢNH BÁO còn để ngỏ: nếu sau này ai thêm một thao tác
// đụng `window.location` vào CHÍNH bên trong `AuthContext.login` (không phải `LoginPage.onSubmit`),
// không bài nào ở đây bắt được — `login` luôn là spy, không chạy thân thật.
describe("LoginPage · submit thật của LoginPage không đụng hash (Task 14, sửa vòng 2 mục C)", () => {
  beforeEach(() => {
    window.location.hash = "#lsx=42&pv=3";
  });
  afterEach(() => {
    window.location.hash = "";
  });

  it("⭐ điền tên đăng nhập + mật khẩu, bấm Đăng nhập ⇒ login() nhận ĐÚNG hai giá trị đó, hash không đổi", async () => {
    const login = vi.fn(async () => {});
    ve({ ...FAKE_AUTH, login });

    // `Field` gắn `htmlFor`/`id` đúng chuẩn nên truy vấn được bằng NHÃN — không cần biết cấu trúc
    // DOM bên trong, giống người dùng thật (Tab tới ô rồi gõ).
    await userEvent.type(screen.getByLabelText("TÊN ĐĂNG NHẬP"), "admin");
    await userEvent.type(screen.getByLabelText("MẬT KHẨU"), "admin123");
    await userEvent.click(screen.getByRole("button", { name: /Đăng nhập hệ thống/ }));

    expect(login).toHaveBeenCalledWith("admin", "admin123");
    expect(window.location.hash).toBe("#lsx=42&pv=3");
  });
});
