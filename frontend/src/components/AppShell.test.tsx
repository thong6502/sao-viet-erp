// Task 14 (deep link QR), sửa vòng 1 P3 — bài canh trước vòng này DỪNG Ở HAI ĐẦU: hàm phân tích
// hash thuần (`appShellDeepLink.test.ts`) và, TỪ PHÍA BÊN KIA, `LenhSanXuatPage.test.tsx` (chỉ
// canh từ chỗ prop đã tới tay component, tự truyền `openHoSoId` bằng tay không qua `AppShell` một
// bước nào). KHÚC NỐI HAI ĐẦU — `AppShell` tự đọc `window.location.hash` lúc mount/khi hash đổi
// (P2) rồi bơm đúng `openHoSoId`/`openHoSoPv` vào nhánh `case "lenh-san-xuat"` của `renderContent()`
// — TRƯỚC ĐÓ KHÔNG CÓ LƯỚI NÀO CANH: xoá cả effect đọc hash, hoặc gõ nhầm khoá
// `navParams?.openHoSoLsxId` thành thứ khác, hai bài canh kia vẫn xanh 100%.
//
// `DashboardPage` (đích tạm lúc mount, trước khi effect kịp điều hướng) và `LenhSanXuatPage` (đích
// cuối) đều bị THAY bằng bản dò (probe): `LenhSanXuatPage` thật kéo theo cả một trang tra cứu with
// nhiều fetch riêng của nó (đã canh riêng ở `LenhSanXuatPage.test.tsx`); mount `AppShell` thật đã
// kéo theo hàng chục side-effect khác không liên quan (badge tổ/kho, kênh SSE...). Mock để cô lập
// ĐÚNG khúc dây chuyền cần canh, không phải bắt nó thoả luôn thân từng trang con.
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../pages/DashboardPage", () => ({
  DashboardPage: () => <div data-testid="probe-dashboard" />,
}));

vi.mock("../pages/LenhSanXuatPage", () => ({
  LenhSanXuatPage: (props: { openHoSoId: number | null; openHoSoPv: number | null }) => (
    <div
      data-testid="probe-lenh-san-xuat"
      data-open-ho-so-id={String(props.openHoSoId)}
      data-open-ho-so-pv={String(props.openHoSoPv)}
    />
  ),
}));

// `connectQuoteEvents` (xem `appShellRealtime.ts` — `lenh_san_xuat` nằm trong `REALTIME_MODULES`)
// là một vòng lặp `fetch` streaming TỰ VIẾT TAY (không phải `EventSource`), có watchdog 50s. Test
// này không cần kênh đó chạy thật, chỉ cần nó không mở một kết nối/hẹn giờ treo lại sau khi bài
// test đã xong — giữ nguyên MỌI export khác qua `importOriginal`, chỉ thay riêng hàm này.
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, connectQuoteEvents: () => () => {} };
});

import { AppShell } from "./AppShell";
import { AuthContext, type AuthState } from "../auth/AuthContext";

const AUTH: AuthState = {
  status: "authenticated", user: null, token: "t",
  login: async () => {}, logout: async () => {},
  updateUser: () => {}, notice: null, setNotice: () => {},
};

/** Fetch giả cho ĐÚNG BỐN nguồn còn lại chạy KHÔNG ĐIỀU KIỆN lúc `AppShell` mount, bất kể
 *  `readable` chứa module gì (đã dò trong `AppShell.tsx`): `myAccess` (dựng `readable`/`caps`),
 *  `moduleNotifications.summary` (trong `reloadBadges`, chỉ gác `!token || readable===null`),
 *  `attendance.notifySummary` và `notifications.list` (cả hai unconditional). Thiếu một trong bốn
 *  thì promise rơi vào nhánh `.catch` — vô hại cho bài này, nhưng để tránh nhiễu log lúc chạy vẫn
 *  khai đủ. */
function stubApi() {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    let data: unknown = {};
    if (url.includes("/api/auth/permissions")) {
      data = { modules: ["dashboard", "lenh_san_xuat"], permissions: [] };
    } else if (url.includes("/api/module-notifications/summary")) {
      data = { thu_mua: 0, ke_toan: 0 };
    } else if (url.includes("/api/attendance/notify-summary")) {
      data = { unseen_shift_changes: 0 };
    } else if (url.includes("/api/notifications")) {
      data = { items: [], unread: 0 };
    }
    return Promise.resolve({
      ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }),
      json: async () => data, text: async () => JSON.stringify(data),
    } as Response);
  }));
}

function ve() {
  return render(
    <AuthContext.Provider value={AUTH}>
      <AppShell />
    </AuthContext.Provider>,
  );
}

describe("AppShell · deep link QR nối hash → props của LenhSanXuatPage (Task 14, sửa vòng 1 P3)", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => {
    window.location.hash = "";
  });

  it("⭐ hash #lsx=77&pv=2 SẴN CÓ lúc mount ⇒ LenhSanXuatPage tự mount với đúng openHoSoId/openHoSoPv", async () => {
    window.location.hash = "#lsx=77&pv=2";
    stubApi();
    ve();

    const probe = await screen.findByTestId("probe-lenh-san-xuat");
    expect(probe.dataset.openHoSoId).toBe("77");
    expect(probe.dataset.openHoSoPv).toBe("2");
  });

  it("không có hash ⇒ ở lại Dashboard, LenhSanXuatPage không mount (hành vi mặc định không đổi)", async () => {
    stubApi();
    ve();

    await screen.findByTestId("probe-dashboard");
    expect(screen.queryByTestId("probe-lenh-san-xuat")).not.toBeInTheDocument();
  });

  // Sửa vòng 1, P2: quét mã THỨ HAI trong lúc tab đã mở sẵn (AppShell đã mount, đang đứng ở
  // Dashboard) chỉ đổi phần fragment của URL — same-document navigation, KHÔNG reload/remount.
  // Bài này giả lập đúng việc trình duyệt tự làm: đổi `location.hash` rồi bắn sự kiện
  // `hashchange`, không unmount/mount lại `<AppShell>`.
  it("⭐ quét mã QR lúc tab đã mở sẵn (hashchange, không remount) ⇒ vẫn nhảy đúng lệnh vừa quét", async () => {
    stubApi();
    ve();
    await screen.findByTestId("probe-dashboard");

    act(() => {
      window.location.hash = "#lsx=88&pv=5";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    const probe = await screen.findByTestId("probe-lenh-san-xuat");
    expect(probe.dataset.openHoSoId).toBe("88");
    expect(probe.dataset.openHoSoPv).toBe("5");
  });
});
