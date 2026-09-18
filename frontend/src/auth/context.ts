import { createContext } from "react";
import type { AuthState } from "./AuthContext";

// Đối tượng context ở module riêng, không nằm trong AuthContext.tsx: sửa file đó thì Vite HMR chạy
// lại nó, `createContext` đẻ context MỚI trong khi <AuthProvider> đang gắn vẫn giữ cái cũ ⇒ mọi
// `useAuth` ném "must be used within <AuthProvider>", trang trắng tới khi tải lại.
export const AuthContext = createContext<AuthState | null>(null);
