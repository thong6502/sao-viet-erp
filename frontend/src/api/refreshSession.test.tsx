import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { authed, refreshSession } from "./client";
import { AuthProvider } from "../auth/AuthContext";
import { useAuth } from "../auth/useAuth";

// Máy chủ XOAY refresh token mỗi lượt và coi token cũ bị dùng lại là BỊ TRỘM ⇒ thu hồi cả họ token.
// Hai lượt /refresh cùng mang MỘT cookie (StrictMode chạy effect hai lần, lượt khôi phục phiên đè
// lên lượt làm mới do 401, hai tab hết hạn cùng lúc) là lượt về sau bị coi là trộm và người dùng
// văng ra màn đăng nhập. Máy khách phải bảo đảm tại một thời điểm chỉ có MỘT lượt đang bay.

const phien = {
  access_token: "tok-moi",
  token_type: "bearer",
  user: { id: 1, username: "admin", name: "Admin" },
};

function traVe(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** fetch giả: /refresh chậm một nhịp để các lượt gọi kịp chồng lên nhau. */
function fetchGia(xuLy: (url: string) => Response | undefined = () => undefined) {
  const soLanRefresh = { n: 0 };
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/auth/refresh")) {
      soLanRefresh.n += 1;
      await new Promise((r) => setTimeout(r, 20));
      return traVe(200, phien);
    }
    return xuLy(url) ?? traVe(200, {});
  });
  vi.stubGlobal("fetch", fn);
  return soLanRefresh;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("làm mới phiên — một lượt /refresh tại một thời điểm", () => {
  it("gọi chồng nhau thì dùng chung một request", async () => {
    const dem = fetchGia();
    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);
    expect(dem.n).toBe(1);
    expect(a?.access_token).toBe("tok-moi");
    expect(b?.access_token).toBe("tok-moi");
  });

  it("khôi phục phiên lúc mở app KHÔNG bắn thêm lượt khi một request khác đang làm mới vì 401", async () => {
    let lanDau = true;
    const dem = fetchGia((url) => {
      if (url.endsWith("/api/xyz") && lanDau) {
        lanDau = false;
        return traVe(401, { detail: "expired" });
      }
      return undefined;
    });
    await Promise.all([authed("/api/xyz", "tok-cu"), refreshSession()]);
    expect(dem.n).toBe(1);
  });

  it("AuthProvider trong StrictMode chỉ gửi MỘT lượt /refresh", async () => {
    const dem = fetchGia();
    function Ten() {
      const { status, user } = useAuth();
      return <span>{status}:{user?.username ?? "-"}</span>;
    }
    render(
      <StrictMode>
        <AuthProvider><Ten /></AuthProvider>
      </StrictMode>,
    );
    await waitFor(() => expect(screen.getByText("authenticated:admin")).toBeTruthy());
    expect(dem.n).toBe(1);
  });

  it("có Web Locks thì lượt /refresh chạy TRONG khoá dùng chung giữa các tab", async () => {
    fetchGia();
    const tenKhoa: string[] = [];
    vi.stubGlobal("navigator", {
      ...navigator,
      locks: {
        request: (ten: string, cb: () => Promise<unknown>) => {
          tenKhoa.push(ten);
          return cb();
        },
      },
    });
    await refreshSession();
    expect(tenKhoa).toEqual(["svn-auth-refresh"]);
  });
});
