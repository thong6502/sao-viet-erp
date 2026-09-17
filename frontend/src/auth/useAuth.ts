import { useContext } from "react";
import type { AuthState } from "./AuthContext";
import { AuthContext } from "./context";

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}
