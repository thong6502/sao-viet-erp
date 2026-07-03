import "./ui-blocks.css";

export interface StatusTabItem {
  key: string;
  label: string;
  count?: number;
  /** "alert" tô đỏ số đếm — dùng cho tab kiểu "Cần tôi xử lý" */
  tone?: "default" | "alert";
}

export function StatusTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: StatusTabItem[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="stabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          className={`stabs__tab ${active === t.key ? "stabs__tab--active" : ""}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
          {t.count !== undefined && (
            <span className={`stabs__count ${t.tone === "alert" && t.count > 0 ? "stabs__count--alert" : ""}`}>
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
