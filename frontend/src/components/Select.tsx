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
import { khopGanDung } from "../utils/timGanDung";
import "./select.css";

export type SelectValue = string | number | null;

export interface SelectOption<T extends SelectValue = SelectValue> {
  value: T;
  label: string;
  hint?: string;
  /** Dòng phụ DƯỚI nhãn (vd "NV Sales · Kinh doanh" dưới tên người). Khác `hint` vốn nằm CÙNG
   *  dòng: dùng khi dòng phụ là thuộc tính của lựa chọn chứ không phải chú thích ngắn. Không
   *  truyền thì DOM giữ nguyên như cũ. */
  sub?: string;
  /** Chấm số ĐỎ (báo "mới/chưa xem") ở cuối lựa chọn — vd số phản hồi kho chưa xem. Ẩn khi ≤0. */
  badge?: number;
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
  /** Hiện ô tìm ngay trong popover — dùng khi danh sách dài (vd chọn vật tư trong kho). */
  searchable?: boolean;
  /** Chỉ có nghĩa với `searchable`: đẩy chuỗi tìm ra ngoài để gọi API. Có handler này thì
   *  KHÔNG lọc cục bộ nữa (server đã lọc, lọc thêm sẽ giấu mất kết quả vừa tải về). */
  onSearch?: (query: string) => void;
  searchPlaceholder?: string;
  /** Căn lề popover ("left" mặc định, "right" cho các ô ở góc phải thanh công cụ). */
  align?: "left" | "right";
  /** Mở LÊN TRÊN thay vì xuống dưới — cho ô nằm cuối trang/pager (mở xuống sẽ bị che). Cần `portal`. */
  dropUp?: boolean;
  /** Class THÊM cho nút bấm (trigger) — để ô này đội lốt input/chip của màn đang dùng thay vì
   *  luôn mang bộ mặt `sel__trigger`. Không truyền thì không đổi gì. */
  className?: string;
  /** Class THÊM cho popover. Cần vì bản `portal` treo ở `document.body`, ra NGOÀI mọi selector
   *  bọc theo màn — không có class riêng thì màn không cách nào chỉnh được cái danh sách. */
  listClassName?: string;
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
  onSearch,
  searchPlaceholder = "Tìm…",
  align = "left",
  dropUp = false,
  className,
  listClassName,
}: SelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [query, setQuery] = useState("");
  const [rect, setRect] = useState<{ top: number; bottom: number; left: number; right: number; width: number; up: boolean } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? null;
  // Lọc cục bộ CHỈ khi không có `onSearch` (nguồn tĩnh). Có `onSearch` = server lọc rồi.
  const shown =
    searchable && !onSearch && query.trim()
      ? // Khớp GẦN ĐÚNG: bỏ dấu + tách từ (xem `utils/timGanDung`). Gõ "may in nho" phải ra
        // "MÁY IN NHỎ 46×64" — lọc `includes` thường trả rỗng ở đúng những lần gõ như vậy.
        // Soi cả `sub` vì dòng phụ hay chứa đúng thứ người ta nhớ (khổ máy, gsm giấy).
        options.filter((o) => khopGanDung(`${o.label} ${o.hint ?? ""} ${o.sub ?? ""}`, query))
      : options;

  // Portal mode: pin the popover to the trigger's current viewport rect.
  function reposition() {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // Tự LẬT LÊN khi dưới trigger không đủ chỗ (280px là max-height của popover trong select.css).
    // Không lật thì ô nằm cuối modal mở ra một danh sách bị cắt đáy màn, phần dưới không bấm được.
    const choDuoi = window.innerHeight - r.bottom;
    setRect({
      up: dropUp || (choDuoi < 240 && r.top > choDuoi),
      top: r.bottom + 4,
      bottom: window.innerHeight - r.top + 4, // neo mép DƯỚI popover ngay trên trigger (mở lên)
      left: r.left,
      right: r.right,
      width: r.width,
    });
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

  // Highlight the current value each time the list opens. Ô tìm (nếu có) reset + nhận focus.
  useEffect(() => {
    if (!open) return;
    const i = shown.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
    if (searchable) {
      setQuery("");
      // Focus sau khi popover đã gắn vào DOM (portal render ở tick sau).
      const t = setTimeout(() => searchRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function choose(i: number) {
    const opt = shown[i];
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
      // Chỉ đóng DANH SÁCH. Không chặn thì phím Esc bay tiếp lên modal/drawer cha và đóng
      // luôn cả cửa sổ — thẻ <select> gốc trước đây tự nuốt phím này.
      e.stopPropagation();
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, shown.length - 1));
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
      className={`sel__list${portal ? " sel__list--portal" : ""}${align === "right" ? " sel__list--right" : ""}${
        listClassName ? ` ${listClassName}` : ""
      }`}
      role="listbox"
      aria-activedescendant={`${listId}-${active}`}
      style={
        portal && rect
          ? {
              position: "fixed",
              // dropUp: neo mép DƯỚI, top:"auto" để XOÁ `top: calc(100%+4px)` của .sel__list
              // (không xoá thì phần tử bị đẩy xuống dưới viewport → menu nằm ngoài màn, không bấm được).
              ...(rect.up ? { top: "auto", bottom: rect.bottom } : { top: rect.top }),
              // Bề ngang danh sách: RỘNG BẰNG NÚT LÀ SÀN, không phải trần (03/09/2026). Trước đó
              // nút rộng ≥60px thì `width` bị đóng đinh bằng bề ngang nút, tên dài hơn nút bị
              // `text-overflow: ellipsis` cắt cụt — nút "+ Thêm công đoạn…" hẹp nên cả danh sách
              // công đoạn hiện thành "In AB- Máy in-11 x 1…", không đọc được tên nào. Nay thả cho
              // nở theo nội dung, chỉ chặn ở mép màn hình để không tràn ra ngoài.
              ...(align === "right"
                ? { right: window.innerWidth - rect.right, left: "auto", minWidth: rect.width,
                    maxWidth: Math.max(rect.width, rect.right - 8) }
                : { left: rect.left, right: "auto",
                    // Nút TÍ HON (vd mũi tên 22px chèn công đoạn): sàn 220px, không thì danh sách
                    // chỉ còn một sợi và chữ vỡ từng ký tự.
                    minWidth: rect.width < 60 ? 220 : rect.width,
                    maxWidth: Math.max(rect.width, window.innerWidth - rect.left - 8) }),
            }
          : undefined
      }
    >
      {searchable && (
        <li className="sel__search" role="presentation">
          <input
            ref={searchRef}
            className="sel__searchinput"
            type="text"
            value={query}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
              onSearch?.(e.target.value);
            }}
            // Space phải gõ được thành ký tự → chỉ chuyển tiếp phím ĐIỀU HƯỚNG cho listbox.
            onKeyDown={(e) => {
              if (["Escape", "ArrowDown", "ArrowUp", "Enter", "Tab"].includes(e.key)) onKeyDown(e);
            }}
            onMouseDown={(e) => e.stopPropagation()}
          />
        </li>
      )}
      {searchable && shown.length === 0 && (
        <li className="sel__empty" role="presentation">
          Không tìm thấy.
        </li>
      )}
      {shown.map((opt, i) => (
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
          {opt.sub ? (
            <span className="sel__opt-stack">
              <span className="sel__opt-label">{opt.label}</span>
              <span className="sel__opt-sub">{opt.sub}</span>
            </span>
          ) : (
            <span className="sel__opt-label">{opt.label}</span>
          )}
          {opt.hint && <span className="sel__opt-hint">{opt.hint}</span>}
          {opt.badge != null && opt.badge > 0 && (
            <span className="sel__opt-badge" aria-label={`${opt.badge} chưa xem`}>
              {opt.badge > 99 ? "99+" : opt.badge}
            </span>
          )}
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
        className={`sel__trigger${open ? " is-open" : ""}${className ? ` ${className}` : ""}`}
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
