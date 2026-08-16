// `defineConfig` lấy từ `vitest/config`, không phải `vite`: đó là bản có thêm khoá `test`.
// Với bản của `vite` thì `tsc --noEmit` báo "'test' does not exist in type UserConfigExport",
// mà `npm run build` chạy tsc trước nên cả bản build cũng gãy theo.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev server on 5173 (matches backend CORS_ORIGINS). The frontend talks to the
// backend only through src/api/client.ts using VITE_API_BASE_URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  // Test FE chạy bằng vitest + jsdom. Trước đây "bằng chứng FE" của module bài ghép chỉ là mấy
  // dòng `assert "n.buoc.map" in source` bên pytest — grep chuỗi trên mã nguồn: đổi
  // `n.buoc.map(...)` thành `n.buoc.filter(...).map(...)` là đỏ dù đúng, còn để nguyên chuỗi đó
  // trong comment thì xanh dù đã xoá sạch UI. Nó chứng minh KÝ TỰ tồn tại, không chứng minh render.
  test: {
    environment: "jsdom",
    css: true,
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
