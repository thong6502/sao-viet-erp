import { useAuth } from "./auth/useAuth";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { PublicScanPage, readScanToken } from "./pages/PublicScanPage";

// Route by auth state (no router lib needed for the auth gate this spec):
//   scan QR  -> trang tra kho CÔNG KHAI (không cần đăng nhập) — bắt TRƯỚC mọi thứ
//   loading  -> restoring session via /me
//   authed   -> protected Dashboard
//   anonymous-> Login
export function App() {
  const { status } = useAuth();

  // Tem QR dán kệ mở "#s=<token>": ai quét cũng xem được, KHÔNG qua cổng đăng nhập.
  const scanToken = readScanToken();
  if (scanToken) return <PublicScanPage scanToken={scanToken} />;

  if (status === "loading") {
    return (
      <div className="screen-center" role="status" aria-live="polite">
        Restoring session…
      </div>
    );
  }

  return status === "authenticated" ? <AppShell /> : <LoginPage />;
}
