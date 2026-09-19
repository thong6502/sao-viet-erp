// Compact Inline KPI Strip component per docs/UI_DESIGN.md §4.
// Single container with hairline dividers separating KPI cells, height ~40px.
import { Icon, type IconName } from "./Icons";
import "../styles/compactKpiStrip.css";

export interface KpiStripItem {
  id: string;
  label: string;
  value: string | number;
  icon?: IconName;
  alert?: boolean;
  hint?: string;
  colorClass?: string;
}

export function CompactKpiStrip({
  items,
  loading = false,
  className = "",
}: {
  items: KpiStripItem[];
  loading?: boolean;
  className?: string;
}) {
  return (
    <div className={`rdx-compact-kpi ${className}`}>
      {items.map((item) => (
        <div key={item.id} className={`rdx-compact-kpi__cell ${item.alert ? "is-alert" : ""}`}>
          {item.icon && (
            <span className={`rdx-compact-kpi__icon ${item.colorClass ?? ""}`}>
              <Icon name={item.icon} size={15} />
            </span>
          )}
          <span className="rdx-compact-kpi__val">
            {loading ? "…" : item.value}
          </span>
          <span className="rdx-compact-kpi__label">{item.label}</span>
          {item.hint && <span className="rdx-compact-kpi__hint">{item.hint}</span>}
        </div>
      ))}
    </div>
  );
}
