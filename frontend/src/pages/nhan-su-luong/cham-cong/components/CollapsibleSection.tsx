// Khối gập của tab Khai ca (tách từ pages/ChamCongPage.tsx).
import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

/** Khối gập dùng chung. Nội dung mount LAZY lần mở đầu rồi GIỮ (ẩn bằng `hidden`)
 *  — nếu unmount, bản nháp phân ca đang gõ dở sẽ bay mất khi gập khối lại. */
export function CollapsibleSection({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [mounted, setMounted] = useState(defaultOpen);
  useEffect(() => {
    if (open) setMounted(true);
  }, [open]);
  return (
    <section className={`cc-sp-sect ${open ? "is-open" : ""}`}>
      <button
        type="button"
        className="cc-sp-sect__head"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <ChevronDown
          size={16}
          className="cc-sp-sect__chev"
          aria-hidden="true"
        />
        <span className="cc-sp-sect__title">{title}</span>
        {summary != null && <span className="cc-sp-sect__sum">{summary}</span>}
      </button>
      {mounted && (
        <div className="cc-sp-sect__body" hidden={!open}>
          {children}
        </div>
      )}
    </section>
  );
}
