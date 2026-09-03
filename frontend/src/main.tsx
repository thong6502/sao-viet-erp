import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./styles/global.css";
// Nạp CUỐI: `import { App }` ở trên chạy trước nên CSS của từng màn đã được chèn xong, rồi
// mới tới global.css và file này — nhờ vậy luật ở đây thắng khi cùng độ đặc hiệu. Mọi luật
// trong đó đều nằm trong @media hẹp nên màn rộng không đổi một pixel; xem đầu file.
import "./styles/responsive.css";
// Sàn chữ 12px cho điện thoại — SINH TỰ ĐỘNG từ chính CSS của dự án (xem đầu file).
import "./styles/responsive-chu.css";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element #root not found");

createRoot(rootEl).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
