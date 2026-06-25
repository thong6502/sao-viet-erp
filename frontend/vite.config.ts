import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server on 5173 (matches backend CORS_ORIGINS). The frontend talks to the
// backend only through src/api/client.ts using VITE_API_BASE_URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
});
