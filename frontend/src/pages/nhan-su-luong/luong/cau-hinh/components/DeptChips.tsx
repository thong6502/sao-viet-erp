// Chip chọn bộ phận (tách từ pages/CauHinhLuongTab.tsx).
import type { Department } from "../../../../../api/client";

export function DeptChips({
  depts,
  deptId,
  counts,
  alert,
  disabled,
  onPick,
}: {
  depts: Department[];
  deptId: number | null;
  counts: Record<number, number>;
  /** true = số 0 tô rust. */
  alert: boolean;
  disabled?: boolean;
  onPick: (id: number) => void;
}) {
  if (!depts.length)
    return (
      <p className="cl-hint-inline">
        Chưa có phòng ban nào. Khai ở màn Phòng ban trước.
      </p>
    );
  const nameOf = (id?: number | null) =>
    depts.find((d) => d.id === id)?.name ?? null;
  return (
    <div className="cl-chips">
      {depts.map((d) => {
        const parent = nameOf(d.parent_id);
        const n = counts[d.id] ?? 0;
        return (
          <button
            key={d.id}
            type="button"
            className={`seg${d.id === deptId ? " is-active" : ""}`}
            disabled={disabled}
            title={parent ? `${parent} · ${d.name}` : d.name}
            onClick={() => onPick(d.id)}
          >
            {parent && <span className="cl-chip__parent">{parent} · </span>}
            {d.name}
            <span
              className={`chip-count${alert && n === 0 ? " chip-count--alert" : ""}`}
            >
              {n}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ============================================================================
// TAB 2 — Cơ chế lương theo bộ phận
// ============================================================================
