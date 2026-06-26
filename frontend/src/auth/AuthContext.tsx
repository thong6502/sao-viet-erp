// Auth state — owns the token + current user and the session lifecycle.
// Cross-cutting concern provided via React context (not reached across layers).
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api, type User } from "../api/client";

const TOKEN_KEY = "gan_app_token";

type Status = "loading" | "authenticated" | "anonymous";

export interface AuthState {
  status: Status;
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // On mount: restore the session from a stored token via /me.
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setStatus("anonymous");
      return;
    }
    let cancelled = false;
    api
      .me(stored)
      .then((restored) => {
        if (cancelled) return;
        setUser(restored);
        setToken(stored);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        // Invalid/expired token (or unreachable) -> treat as logged out.
        localStorage.removeItem(TOKEN_KEY);
        setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    try {
      const res = await api.login(email, password);
      localStorage.setItem(TOKEN_KEY, res.access_token);
      setUser(res.user);
      setToken(res.access_token);
      setStatus("authenticated");
    } catch (err) {
      // Re-throw so the form can render the right message; leave state anonymous.
      throw err instanceof ApiError ? err : new ApiError("Unexpected error.", 0);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setToken(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, user, token, login, logout }),
    [status, user, token, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
