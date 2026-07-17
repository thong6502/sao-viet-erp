// Reusable dropdown that matches the paper + ink + rust system (replaces the native
// <select>, which can't be styled to the design language). Keyboard-accessible listbox:
// open with Enter/Space/↓, move with ↑/↓, choose with Enter, dismiss with Esc; click-away
// closes. Each option can carry a mono `hint` shown after the label.
//
// `portal`: render the popover in a portal at document.body (position: fixed at the trigger)
// so it is NOT clipped by a scrolling parent — use it inside modals. Inline (default) keeps
// the simpler absolute popover and does not close on page scroll.
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./select.css";

export type SelectValue = string | number | null;

// Render dần: hiện 50 mục đầu, cuộn gần đáy mới nạp thêm 50 (danh mục lớn đỡ dựng hết DOM).
const MENU_PAGE = 50;

export interface SelectOption<T extends SelectValue = SelectValue> {
  value: T;
  label: string;
  hint?: string;
}

interface SelectProps<T extends SelectValue> {
  options: SelectOption<T>[];
  value: T;
  onChange: (value: T) => void;
  placeholder?: string;
  disabled?: boolean;
  portal?: boolean;
  id?: string;
  ariaLabel?: string;
  /** Hiện ô tìm kiếm ở đầu danh sách; lọc theo nhãn + hint. Không khớp → "Không có thông tin". */
  searchable?: boolean;
  searchPlaceholder?: string;
  /** Cho phép bỏ chọn (hiện nút × khi đã chọn) — trả về null. */
  clearable?: boolean;
}

export function Select<T extends SelectValue>({
  options,
  value,
  onChange,
  placeholder = "— Chọn —",
  disabled = false,
  portal = false,
  id,
  ariaLabel,
  searchable = false,
  searchPlaceholder = "Tìm kiếm…",
  clearable = false,
}: SelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(MENU_PAGE); // số mục đang render (render dần)
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? null;
  // Danh sách sau lọc (khi bật tìm kiếm). So khớp không dấu-hoa-thường trên nhãn + hint.
  const q = query.trim().toLowerCase();
  const filtered = searchable && q
    ? options.filter((o) => `${o.label} ${o.hint ?? ""}`.toLowerCase().includes(q))
    : options;

  // Portal mode: pin the popover to the trigger's current viewport rect.
  function reposition() {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setRect({ top: r.bottom + 4, left: r.left, width: r.width });
  }

  useLayoutEffect(() => {
    if (open && portal) reposition();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, portal]);

  useEffect(() => {
    if (!open) return;
    function onDocDown(e: MouseEvent) {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || listRef.current?.contains(t)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onDocDown);
    // Keep the fixed popover glued to the trigger on scroll/resize. Scrolling INSIDE the
    // list leaves the trigger's rect unchanged, so it neither moves nor closes.
    if (portal) {
      window.addEventListener("resize", reposition);
      window.addEventListener("scroll", reposition, true);
    }
    return () => {
      document.removeEventListener("mousedown", onDocDown);
      if (portal) {
        window.removeEventListener("resize", reposition);
        window.removeEventListener("scroll", reposition, true);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, portal]);

  // Highlight the current value each time the list opens; reset search + focus the box.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setVisible(MENU_PAGE);
    const i = options.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
    if (searchable) requestAnimationFrame(() => searchRef.current?.focus());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Gõ tìm kiếm → nhảy con trỏ về đầu + render lại từ 50 mục đầu.
  useEffect(() => {
    setActive(0);
    setVisible(MENU_PAGE);
  }, [query]);

  // Điều hướng bàn phím vượt vùng đang render → nạp thêm để mục active tồn tại.
  useEffect(() => {
    if (active >= visible) setVisible(Math.min(active + MENU_PAGE, filtered.length));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  function choose(i: number) {
    const opt = filtered[i];
    if (!opt) return;
    onChange(opt.value);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;
    if (!open) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  }

  const list = (
    <div
      ref={listRef}
      className={`sel__pop${portal ? " sel__pop--portal" : ""}${searchable ? " sel__pop--search" : ""}`}
      style={
        portal && rect
          ? { position: "fixed", top: rect.top, left: rect.left, width: rect.width, right: "auto" }
          : undefined
      }
    >
      {searchable && (
        <div className="sel__search">
          <input
            ref={searchRef}
            className="sel__search-input"
            type="text"
            value={query}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
          />
        </div>
      )}
      <ul
        className="sel__list"
        role="listbox"
        aria-activedescendant={`${listId}-${active}`}
        onScroll={(e) => {
          const el = e.currentTarget;
          if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
            setVisible((v) => Math.min(v + MENU_PAGE, filtered.length));
          }
        }}
      >
        {filtered.length === 0 ? (
          <li className="sel__empty" role="option" aria-selected={false} aria-disabled="true">
            Không có thông tin
          </li>
        ) : filtered.slice(0, visible).map((opt, i) => (
          <li
            key={i}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={opt.value === value}
            className={`sel__opt${i === active ? " is-active" : ""}${
              opt.value === value ? " is-selected" : ""
            }`}
            onMouseEnter={() => setActive(i)}
            onMouseDown={(e) => {
              e.preventDefault();
              choose(i);
            }}
          >
            <span className="sel__opt-label">{opt.label}</span>
            {opt.hint && <span className="sel__opt-hint">{opt.hint}</span>}
            {opt.value === value && (
              <span className="sel__opt-check" aria-hidden="true">✓</span>
            )}
          </li>
        ))}
        {filtered.length > visible && (
          <li className="sel__more" aria-hidden="true">
            Cuộn để xem thêm… (còn {filtered.length - visible})
          </li>
        )}
      </ul>
    </div>
  );

  return (
    <div className={`sel${disabled ? " sel--disabled" : ""}`} ref={rootRef}>
      <button
        type="button"
        id={id}
        ref={triggerRef}
        className={`sel__trigger${open ? " is-open" : ""}${clearable && selected ? " sel__trigger--clearable" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={onKeyDown}
      >
        <span className={`sel__value${selected ? "" : " sel__value--ph"}`}>
          {selected ? selected.label : placeholder}
        </span>
        <span className="sel__caret" aria-hidden="true">▾</span>
      </button>
      {clearable && selected && !disabled && (
        <span
          className="sel__clear"
          role="button"
          aria-label="Bỏ chọn"
          title="Bỏ chọn"
          onMouseDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onChange(null as T);
            setOpen(false);
          }}
        >
          ✕
        </span>
      )}
      {open && (portal ? rect && createPortal(list, document.body) : list)}
    </div>
  );
}
