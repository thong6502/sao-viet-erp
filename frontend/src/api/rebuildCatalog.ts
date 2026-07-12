// API — 4 danh mục rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP). File riêng dùng chung
// `authed` của client.ts (silent-refresh nhất quán). Wiring Phase E.
import { authed } from "./client";

export interface ListOut<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export type Row = Record<string, unknown> & { id: number; ma: string; ten: string };

function qs(params: Record<string, unknown>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const str = s.toString();
  return str ? `?${str}` : "";
}

/** CRUD generic cho 1 prefix (vd "/api/may-thiet-bi"). */
export function crud(prefix: string) {
  return {
    list(token: string, params: Record<string, unknown> = {}): Promise<ListOut<Row>> {
      return authed<ListOut<Row>>(`${prefix}${qs({ size: 200, ...params })}`, token);
    },
    get(token: string, id: number): Promise<Row> {
      return authed<Row>(`${prefix}/${id}`, token);
    },
    create(token: string, body: Record<string, unknown>): Promise<Row> {
      return authed<Row>(prefix, token, { method: "POST", body: JSON.stringify(body) });
    },
    update(token: string, id: number, body: Record<string, unknown>): Promise<Row> {
      return authed<Row>(`${prefix}/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
    },
    remove(token: string, id: number): Promise<void> {
      return authed<void>(`${prefix}/${id}`, token, { method: "DELETE" });
    },
  };
}

export const mayThietBi = crud("/api/may-thiet-bi");
export const congDoan = crud("/api/cong-doan");
export const loaiSanPham = crud("/api/loai-san-pham");
// Vật liệu Kho: 3 loại con dưới cùng prefix.
export const giay = crud("/api/vat-lieu-kho/giay");
export const muc = crud("/api/vat-lieu-kho/muc");
export const banKem = crud("/api/vat-lieu-kho/ban-kem");

// BHR preview cho Máy.
export function mayBhr(token: string, id: number): Promise<{
  gio_tinh_phi: number | null; breakdown: Record<string, number>; BHR: number; don_gia_ban_gio: number;
}> {
  return authed(`/api/may-thiet-bi/${id}/bhr`, token);
}


