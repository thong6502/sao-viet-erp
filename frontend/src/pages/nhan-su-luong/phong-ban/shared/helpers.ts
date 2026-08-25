// Hàm dùng chung của màn Phòng ban (tách từ pages/DepartmentsPage.tsx).
import type { Department, PermissionRow } from "../../../../api/client";
import type { ActionKey } from "../../../../components/PermissionMatrix";
import { READ_IMPLYING_ACTIONS } from "./constants";

export function applyPermissionDependency(
  row: PermissionRow,
  action: ActionKey,
  value: boolean,
): PermissionRow {
  const next = { ...row, [action]: value };
  if (action === "can_read" && !value) {
    for (const key of READ_IMPLYING_ACTIONS) next[key] = false;
    return next;
  }
  if (action === "can_view_salary" && !value) {
    next.can_edit_salary = false;
  }
  if (action === "can_edit_salary" && value) {
    next.can_view_salary = true;
  }
  if (value && READ_IMPLYING_ACTIONS.includes(action)) next.can_read = true;
  return next;
}

/** Group departments by parent and find the roots, so the list can render as a real tree.
 *  Orphans (parent missing/filtered out) are treated as roots so nothing ever disappears. */
export function buildTree(list: Department[]): {
  childrenOf: Map<number, Department[]>;
  roots: Department[];
} {
  const ids = new Set(list.map((d) => d.id));
  const childrenOf = new Map<number, Department[]>();
  const roots: Department[] = [];
  for (const d of list) {
    const parent = d.parent_id ?? null;
    if (parent != null && ids.has(parent)) {
      const bucket = childrenOf.get(parent);
      if (bucket) bucket.push(d);
      else childrenOf.set(parent, [d]);
    } else {
      roots.push(d);
    }
  }
  return { childrenOf, roots };
}

export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}
