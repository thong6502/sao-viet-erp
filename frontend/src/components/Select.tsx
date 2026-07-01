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
}: SelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? null;

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

  // Highlight the current value each time the list opens.
  useEffect(() => {
    if (!open) return;
    const i = options.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function choose(i: number) {
    const opt = options[i];
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
      setActive((a) => Math.min(a + 1, options.length - 1));
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
    <ul
      ref={listRef}
      className={`sel__list${portal ? " sel__list--portal" : ""}`}
      role="listbox"
      aria-activedescendant={`${listId}-${active}`}
      style={
        portal && rect
          ? { position: "fixed", top: rect.top, left: rect.left, width: rect.width, right: "auto" }
          : undefined
      }
    >
      {options.map((opt, i) => (
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
    </ul>
  );

  return (
    <div className={`sel${disabled ? " sel--disabled" : ""}`} ref={rootRef}>
      <button
        type="button"
        id={id}
        ref={triggerRef}
        className={`sel__trigger${open ? " is-open" : ""}`}
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
      {open && (portal ? rect && createPortal(list, document.body) : list)}
    </div>
  );
}
