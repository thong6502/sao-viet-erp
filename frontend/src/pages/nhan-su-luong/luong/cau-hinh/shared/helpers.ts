// Hàm dùng chung của tab Cấu hình lương (tách từ pages/CauHinhLuongTab.tsx).
import {
  api,
  type Department,
  type EmployeeRow,
  type LatePenaltyBracket,
  type PayrollParams,
  type PitBracket,
} from "../../../../../api/client";
import type { BracketDraft, PenaltyDraft } from "./types";

export function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}
/** Hệ số nhân (1.5) → % hiển thị (150). Tránh 149.99999 do dấu phẩy động. */

export function toPct(v: number): number {
  return Math.round(v * 1000) / 10;
}
/** PHÚT trong DB → GIỜ trên ô nhập (2400 → 40). Làm tròn 2 số lẻ: nếu DB lỡ có số không chia
 *  hết cho 60 (nhập tay lúc vá dữ liệu) thì ô hiện "40,17" chứ không phải 40.16666666666667. */

export function toGio(phut: number): number {
  return Math.round((phut / 60) * 100) / 100;
}
/** Sắp phòng ban theo CÂY: phòng cha rồi tổ con ngay dưới (dải chip đọc theo mạch tổ chức). */

export function orderByTree(list: Department[]): Department[] {
  const ids = new Set(list.map((d) => d.id));
  const byParent = new Map<number | null, Department[]>();
  for (const d of list) {
    const p = d.parent_id != null && ids.has(d.parent_id) ? d.parent_id : null;
    const bucket = byParent.get(p) ?? [];
    bucket.push(d);
    byParent.set(p, bucket);
  }
  const out: Department[] = [];
  const walk = (parent: number | null) => {
    for (const d of byParent.get(parent) ?? []) {
      out.push(d);
      walk(d.id);
    }
  };
  walk(null);
  return out.length === list.length ? out : list;
}

// --- Ô nhập số dùng chung (primitive .rc-* của màn danh mục) -----------------

export function pick(
  p: PayrollParams,
  keys: readonly (keyof PayrollParams)[],
): Partial<PayrollParams> {
  const out: Partial<PayrollParams> = {};
  for (const k of keys) out[k] = p[k];
  return out;
}

export function restore(
  draft: PayrollParams,
  base: PayrollParams,
  keys: readonly (keyof PayrollParams)[],
): PayrollParams {
  const out = { ...draft };
  for (const k of keys) out[k] = base[k];
  return out;
}

export function as2Draft(items: PitBracket[]): BracketDraft[] {
  return items
    .slice()
    .sort((a, b) => a.seq - b.seq)
    .map((b) => ({ key: `b${b.id}`, id: b.id, up_to: b.up_to, rate: b.rate }));
}
/** Chỉ số dòng đang sai → tô đỏ + chặn nút Lưu. */

export function validateBrackets(list: BracketDraft[]): Set<number> {
  const bad = new Set<number>();
  let prev = -1;
  list.forEach((b, i) => {
    if (b.rate < 0 || b.rate > 1) bad.add(i);
    if (b.up_to == null) {
      if (i !== list.length - 1) bad.add(i); // chỉ bậc CUỐI được để trống (∞)
      return;
    }
    if (b.up_to <= prev) bad.add(i);
    prev = b.up_to;
  });
  return bad;
}

export function as2PenaltyDraft(items: LatePenaltyBracket[]): PenaltyDraft[] {
  return items
    .slice()
    .sort((a, b) => a.seq - b.seq)
    .map((b) => ({
      key: `p${b.id}`,
      id: b.id,
      up_to_minute: b.up_to_minute,
      amount: b.amount,
    }));
}
/** Validate bảng phạt: phút TĂNG DẦN · chỉ bậc CUỐI để trống (∞) · tiền ≥ 0. */

export function validatePenalties(list: PenaltyDraft[]): Set<number> {
  const bad = new Set<number>();
  let prev = -1;
  list.forEach((b, i) => {
    if (b.amount < 0) bad.add(i);
    if (b.up_to_minute == null) {
      if (i !== list.length - 1) bad.add(i); // chỉ bậc CUỐI được để trống (∞)
      return;
    }
    if (b.up_to_minute <= prev) bad.add(i);
    prev = b.up_to_minute;
  });
  return bad;
}

// --- Dải chip phòng ban (dùng chung cho các tab) ----------------------------

export const EMP_PAGE = 200;

export async function fetchAllEmployees(token: string): Promise<EmployeeRow[]> {
  const first = await api.employees.list(token, { page: 1, size: EMP_PAGE });
  const out = [...first.items];
  const pages = Math.ceil(first.total / EMP_PAGE);
  for (let p = 2; p <= pages; p++) {
    const r = await api.employees.list(token, { page: p, size: EMP_PAGE });
    out.push(...r.items);
  }
  return out;
}
