import "./ui-blocks.css";

export interface TimelineEntry {
  title: string;
  /** Dòng phụ: "17/05/2026 · Nguyễn Văn A" */
  meta?: string;
  /** Chấm màu nhấn (sự kiện quan trọng: gửi khách, duyệt...) */
  accent?: boolean;
  /** Màu chấm theo loại sự kiện: rust (mốc đầu) / moss (tích cực) / steel / signal (kết thúc). */
  tone?: "rust" | "moss" | "steel" | "signal";
}

export function Timeline({ items, emptyText }: { items: TimelineEntry[]; emptyText?: string }) {
  if (items.length === 0) {
    return <p className="tline__empty">{emptyText ?? "Chưa có hoạt động nào."}</p>;
  }
  return (
    <ul className="tline">
      {items.map((it, idx) => (
        <li
          key={idx}
          className={`tline__item ${it.accent ? "tline__item--accent" : ""}${it.tone ? ` tline__item--tone-${it.tone}` : ""}`}
        >
          <span className="tline__dot" aria-hidden="true" />
          <div className="tline__title">{it.title}</div>
          {it.meta && <div className="tline__meta">{it.meta}</div>}
        </li>
      ))}
    </ul>
  );
}
