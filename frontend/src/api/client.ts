// API client — the ONLY module that knows backend URLs, request/response shapes,
// and error mapping (docs/ARCHITECTURE.md). Components/hooks call these functions,
// never fetch() directly.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export interface User {
  id: number;
  username: string;
  name: string;
  avatar_url?: string | null;
}

/** Enriched profile for the account panel (spec-04): user + resolved dept/role + created. */
export interface Profile extends User {
  department_name: string | null;
  role_name: string | null;
  created_at: string;
}

/** Resolve a server-relative asset path (e.g. an avatar `/static/...`) to a full URL the
 *  browser can load from the API origin. Returns null for an empty/missing path. */
export function assetUrl(path?: string | null): string | null {
  if (!path) return null;
  return /^https?:\/\//i.test(path) ? path : `${BASE_URL}${path}`;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

/** Normalized API error so the UI can branch on kind without parsing strings. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number, // 0 = network/unreachable
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }

  get isAuth(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let resp: Response;
  try {
    // Let the browser set the multipart boundary itself for FormData (avatar upload);
    // force JSON otherwise.
    const isForm = init.body instanceof FormData;
    resp = await fetch(`${BASE_URL}${path}`, {
      ...init,
      // Send/receive the httpOnly refresh cookie (spec-03). Requires the backend to
      // allow credentials with a specific origin (never "*").
      credentials: "include",
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
  }

  if (!resp.ok) {
    const detail = await safeDetail(resp);
    throw new ApiError(detail ?? `Request failed (${resp.status}).`, resp.status);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

async function safeDetail(resp: Response): Promise<string | null> {
  try {
    const body = await resp.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    /* non-JSON error body */
  }
  return null;
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function authed<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  try {
    return await request<T>(path, {
      ...init,
      headers: { ...authHeader(token), ...(init.headers ?? {}) },
    });
  } catch (err) {
    // Access token expired? Refresh once (silently) and retry the original request.
    if (err instanceof ApiError && err.isAuth) {
      const fresh = await refreshAccessToken();
      if (fresh) {
        return await request<T>(path, {
          ...init,
          headers: { ...authHeader(fresh), ...(init.headers ?? {}) },
        });
      }
    }
    throw err;
  }
}

// --- Silent refresh ---------------------------------------------------------
// A single shared in-flight refresh so a burst of concurrent 401s triggers at most
// ONE /refresh call (no refresh storm). Callbacks let AuthContext stay in sync.

let refreshInFlight: Promise<string | null> | null = null;
let onAccessToken: (token: string | null) => void = () => {};
let onSessionEnded: () => void = () => {};

/** AuthContext registers how to receive a rotated access token / a dead session. */
export function registerAuthCallbacks(cb: {
  onAccessToken: (token: string | null) => void;
  onSessionEnded: () => void;
}): void {
  onAccessToken = cb.onAccessToken;
  onSessionEnded = cb.onSessionEnded;
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = api
      .refresh()
      .then((res) => {
        onAccessToken(res.access_token);
        return res.access_token;
      })
      .catch(() => {
        onSessionEnded();
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// --- RBAC admin shapes ------------------------------------------------------

export type Scope = "own" | "department" | "all";

export interface ModuleDef {
  key: string;
  label: string;
}

export interface Department {
  id: number;
  name: string;
  code: string;
  description?: string | null;
  parent_id?: number | null;
  head_user_id?: number | null;
  head_name?: string | null;
  /** This department's own role/user counts. */
  role_count?: number;
  user_count?: number;
  /** Branch-rolled-up counts (department + every descendant) — PBI-4001. */
  total_role_count?: number;
  total_user_count?: number;
}

/** A staff member of a department (PBI-4001 detail panel). */
export interface DepartmentMember {
  id: number;
  name: string;
  username: string;
  role_name?: string | null;
  is_active: boolean;
  is_head: boolean;
}

/** A node in a department's delete-preview subtree (spec-05). */
export interface DepartmentSubtreeRow {
  id: number;
  name: string;
  code: string;
}

export interface UserBrief {
  id: number;
  name: string;
  username: string;
}

export interface UserRow {
  id: number;
  name: string;
  username: string;
  department_id: number | null;
  department_name: string | null;
  role_id: number | null;
  role_name: string | null;
  is_active: boolean;
}

export interface AuditRow {
  id: number;
  actor_user_id: number | null;
  actor_name: string | null;
  action: string;
  target: string;
  detail: string;
  created_at: string;
}

export interface Role {
  id: number;
  name: string;
  department_id: number;
}

export interface PermissionRow {
  module_key: string;
  can_read: boolean;
  can_create: boolean;
  can_update: boolean;
  can_delete: boolean;
  scope: Scope;
}

export const api = {
  login(username: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  me(token: string): Promise<User> {
    return request<User>("/api/auth/me", { headers: authHeader(token) });
  },

  /** Exchange the httpOnly refresh cookie for a new access token (rotates the cookie). */
  refresh(): Promise<LoginResponse> {
    return request<LoginResponse>("/api/auth/refresh", { method: "POST" });
  },

  /** Revoke the refresh token server-side and clear the cookie. */
  logout(): Promise<void> {
    return request<void>("/api/auth/logout", { method: "POST" });
  },

  /** Module keys the current user can Read (for menu/route gating). */
  myPermissions(token: string): Promise<string[]> {
    return authed<{ modules: string[] }>("/api/auth/permissions", token).then(
      (r) => r.modules,
    );
  },

  // --- Self-service profile (spec-04) ---------------------------------------

  /** Enriched current-user profile (department/role names + created_at). */
  profile(token: string): Promise<Profile> {
    return authed<Profile>("/api/auth/me", token);
  },

  /** Change the display name; returns the updated user. */
  updateName(token: string, name: string): Promise<User> {
    return authed<User>("/api/users/me", token, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
  },

  /** Upload a new avatar (JPG/PNG ≤ 2 MB); returns its server path. */
  uploadAvatar(token: string, file: File): Promise<{ avatar_url: string }> {
    const form = new FormData();
    form.append("file", file);
    return authed<{ avatar_url: string }>("/api/users/me/avatar", token, {
      method: "POST",
      body: form,
    });
  },

  /** Remove the avatar → initials fallback. */
  removeAvatar(token: string): Promise<void> {
    return authed<void>("/api/users/me/avatar", token, { method: "DELETE" });
  },

  /** Change the current user's password; ends all sessions (caller returns to Login). */
  changePassword(token: string, currentPassword: string, newPassword: string): Promise<void> {
    return authed<void>("/api/auth/change-password", token, {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },

  rbac: {
    modules(token: string): Promise<ModuleDef[]> {
      return authed<ModuleDef[]>("/api/rbac/modules", token);
    },
    departments(token: string): Promise<Department[]> {
      return authed<Department[]>("/api/departments", token);
    },
    departmentUsers(token: string, departmentId: number): Promise<DepartmentMember[]> {
      return authed<DepartmentMember[]>(`/api/departments/${departmentId}/users`, token);
    },
    createDepartment(
      token: string,
      name: string,
      description: string | null,
      parentId: number | null,
    ): Promise<Department> {
      return authed<Department>("/api/departments", token, {
        method: "POST",
        body: JSON.stringify({ name, description, parent_id: parentId }),
      });
    },
    updateDepartment(
      token: string,
      id: number,
      name: string,
      headUserId: number | null,
      description: string | null,
    ): Promise<Department> {
      return authed<Department>(`/api/departments/${id}`, token, {
        method: "PUT",
        body: JSON.stringify({ name, head_user_id: headUserId, description }),
      });
    },
    /** Departments that would be deleted with this one's branch (spec-05 confirm). */
    departmentSubtree(token: string, id: number): Promise<DepartmentSubtreeRow[]> {
      return authed<DepartmentSubtreeRow[]>(`/api/departments/${id}/subtree`, token);
    },
    deleteDepartment(token: string, id: number): Promise<void> {
      return authed<void>(`/api/departments/${id}`, token, { method: "DELETE" });
    },
    users(token: string): Promise<UserRow[]> {
      return authed<UserRow[]>("/api/users", token);
    },
    createUser(token: string, name: string, username: string, departmentId: number): Promise<UserRow> {
      return authed<UserRow>("/api/users", token, {
        method: "POST",
        body: JSON.stringify({ name, username, department_id: departmentId }),
      });
    },
    assignUserRole(token: string, userId: number, roleId: number | null): Promise<UserRow> {
      return authed<UserRow>(`/api/users/${userId}/role`, token, {
        method: "PUT",
        body: JSON.stringify({ role_id: roleId }),
      });
    },
    setUserActive(token: string, userId: number, isActive: boolean): Promise<UserRow> {
      return authed<UserRow>(`/api/users/${userId}/active`, token, {
        method: "PUT",
        body: JSON.stringify({ is_active: isActive }),
      });
    },
    activityLog(token: string): Promise<AuditRow[]> {
      return authed<AuditRow[]>("/api/audit", token);
    },
    roles(token: string, departmentId: number): Promise<Role[]> {
      return authed<Role[]>(`/api/roles?department_id=${departmentId}`, token);
    },
    createRole(token: string, name: string, departmentId: number): Promise<Role> {
      return authed<Role>("/api/roles", token, {
        method: "POST",
        body: JSON.stringify({ name, department_id: departmentId }),
      });
    },
    renameRole(token: string, roleId: number, name: string): Promise<Role> {
      return authed<Role>(`/api/roles/${roleId}`, token, {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
    },
    deleteRole(token: string, roleId: number): Promise<void> {
      return authed<void>(`/api/roles/${roleId}`, token, { method: "DELETE" });
    },
    permissions(token: string, roleId: number): Promise<PermissionRow[]> {
      return authed<PermissionRow[]>(`/api/roles/${roleId}/permissions`, token);
    },
    savePermissions(
      token: string,
      roleId: number,
      rows: PermissionRow[],
    ): Promise<PermissionRow[]> {
      return authed<PermissionRow[]>(`/api/roles/${roleId}/permissions`, token, {
        method: "PUT",
        body: JSON.stringify({ permissions: rows }),
      });
    },
  },
};
