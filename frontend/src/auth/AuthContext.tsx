// Auth state — owns the (in-memory) access token + current user and the session
// lifecycle. The long-lived refresh token lives ONLY in an httpOnly cookie (spec-03),
// so the access token is never persisted to localStorage (XSS can't read it).
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api, registerAuthCallbacks, type User } from "../api/client";

type Status = "loading" | "authenticated" | "anonymous";

export interface AuthState {
  status: Status;
  user: User | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** feat-018: patch local user state after a profile update (name, avatar_url) */
  updateUser: (patch: Partial<User>) => void;
  /** A one-shot message to surface on the Login screen (e.g. after a password change
   *  forces re-login, feat-022). Cleared by the Login screen once shown. */
  notice: string | null;
  setNotice: (msg: string | null) => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Let the API client push a rotated access token (silent refresh) and signal a dead
  // session back into React state.
  useEffect(() => {
    registerAuthCallbacks({
      onAccessToken: (t) => setToken(t),
      onSessionEnded: () => {
        setUser(null);
        setToken(null);
        setStatus("anonymous");
      },
    });
  }, []);

  // On mount: restore the session from the httpOnly refresh cookie via /refresh.
  // No stored bearer token to read — the cookie rides along automatically.
  useEffect(() => {
    let cancelled = false;
    api
      .refresh()
      .then((res) => {
        if (cancelled) return;
        setUser(res.user);
        setToken(res.access_token);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        // No/expired/revoked refresh cookie -> treat as logged out.
        setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    try {
      const res = await api.login(username, password);
      // The server set the refresh cookie; keep the access token in memory only.
      setUser(res.user);
      setToken(res.access_token);
      setStatus("authenticated");
    } catch (err) {
      // Re-throw so the form can render the right message; leave state anonymous.
      throw err instanceof ApiError ? err : new ApiError("Unexpected error.", 0);
    }
  }, []);

  const logout = useCallback(async () => {
    // Best-effort server-side revoke; clear local state regardless of the result.
    try {
      await api.logout();
    } catch {
      /* even if the call fails, end the session locally */
    }
    setUser(null);
    setToken(null);
    setStatus("anonymous");
  }, []);

  const updateUser = useCallback((patch: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, user, token, login, logout, updateUser, notice, setNotice }),
    [status, user, token, login, logout, updateUser, notice],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
