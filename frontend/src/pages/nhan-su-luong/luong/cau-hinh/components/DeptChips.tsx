// Bộ chọn phòng ban / tổ cho Cấu hình lương (chỉ dùng Select tìm kiếm, không liệt kê chip).
import { useMemo } from "react";
import { Building2, Users } from "lucide-react";
import type { Department } from "../../../../../api/client";
import { Select, type SelectOption } from "../../../../../components/Select";

export interface DeptChipsProps {
  depts: Department[];
  deptId: number | null;
  counts: Record<number, number>;
  /** true = số 0 tô rust. */
  alert?: boolean;
  disabled?: boolean;
  onPick: (id: number) => void;
}

export function DeptChips({
  depts,
  deptId,
  counts,
  disabled,
  onPick,
}: DeptChipsProps) {
  if (!depts.length) {
    return (
      <p className="cl-hint-inline">
        Chưa có phòng ban nào. Khai ở màn Phòng ban trước.
      </p>
    );
  }

  // Map tra cứu nhanh O(1)
  const deptMap = useMemo(() => {
    const map = new Map<number, Department>();
    for (const d of depts) map.set(d.id, d);
    return map;
  }, [depts]);

  // Phòng ban đang chọn hiện tại
  const currentDept = useMemo(() => {
    if (deptId != null) {
      const d = deptMap.get(deptId);
      if (d) return d;
    }
    return depts.length > 0 ? depts[0] : null;
  }, [deptId, deptMap, depts]);

  const parentName = useMemo(() => {
    if (!currentDept?.parent_id) return null;
    return deptMap.get(currentDept.parent_id)?.name ?? null;
  }, [currentDept, deptMap]);

  // Danh sách options gom nhóm theo khối cha, sắp xếp nhóm liền nhau để Select render optgroup
  const selectOptions: SelectOption<number>[] = useMemo(() => {
    const list = depts.map((d) => {
      const pName = d.parent_id != null ? (deptMap.get(d.parent_id)?.name ?? "") : "";
      const n = counts[d.id] ?? d.employee_count ?? 0;
      const groupName = pName
        ? pName.toLowerCase().startsWith("khối")
          ? pName
          : `Khối ${pName}`
        : "Phòng ban chính / Khối chung";
      return {
        value: d.id,
        label: d.name,
        hint: `${n} NV`,
        group: groupName,
        sub: pName ? `Thuộc: ${pName}` : undefined,
        search: `${d.code || ""} ${d.name} ${pName}`,
      };
    });

    // Sắp xếp theo group để các lựa chọn cùng group đứng liền nhau
    list.sort((a, b) => {
      const gCmp = a.group.localeCompare(b.group, "vi");
      if (gCmp !== 0) return gCmp;
      return a.label.localeCompare(b.label, "vi");
    });

    return list;
  }, [depts, deptMap, counts]);

  const currentCount = currentDept ? (counts[currentDept.id] ?? currentDept.employee_count ?? 0) : 0;

  const selectedId = currentDept ? currentDept.id : depts[0].id;

  return (
    <div className="cl-dept-bar" role="region" aria-label="Bộ chọn phòng ban cấu hình lương">
      <div className="cl-dept-bar__info">
        <span className="cl-dept-bar__label">
          <Building2 size={16} aria-hidden />
          <span>Bộ phận đang cấu hình:</span>
        </span>
        <span className="cl-dept-bar__current-name">
          {parentName && <span className="cl-dept-bar__parent">{parentName} ❯ </span>}
          <strong>{currentDept?.name ?? "—"}</strong>
        </span>
        <span className="cl-dept-bar__count">
          <Users size={12} aria-hidden />
          {currentCount} nhân sự
        </span>
        {currentDept?.la_san_xuat && (
          <span className="rc-pill rc-pill--amber">Sản xuất</span>
        )}
        {currentDept?.la_giao_hang && (
          <span className="rc-pill rc-pill--blue">Giao hàng</span>
        )}
      </div>

      <div className="cl-dept-bar__picker">
        <label className="cl-dept-bar__picker-label" htmlFor="cl-dept-select">
          Đổi bộ phận:
        </label>
        <div className="cl-dept-bar__select-wrap">
          <Select<number>
            id="cl-dept-select"
            value={selectedId}
            onChange={(val) => {
              if (val != null) onPick(val);
            }}
            options={selectOptions}
            searchable
            searchPlaceholder="Gõ để tìm nhanh bộ phận / tổ…"
            placeholder="— Chọn phòng ban / tổ —"
            disabled={disabled}
            ariaLabel="Chọn phòng ban cần cấu hình lương"
          />
        </div>
      </div>
    </div>
  );
}
