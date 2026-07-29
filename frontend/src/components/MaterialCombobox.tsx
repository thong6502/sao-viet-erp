// Ô NHẬP vật tư kiểu gõ-thẳng (combobox) cho dòng đề nghị kho.
//
// Khác `Select` (bấm mở rồi mới tìm): đây là input để GÕ NGAY. Gõ tới đâu, hàng cũ khớp
// tên/mã hiện tới đó để chọn; không có hàng khớp thì hiện "＋ Tạo …" để thêm mới tại chỗ.
// Dropdown render qua PORTAL (position: fixed) vì bảng dòng + thân drawer đều overflow, để
// trong sẽ bị cắt.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type StockMaterialOption } from "../api/client";

export function MaterialCombobox({
  token,
  materialName,
  onPick,
  onCreate,
  onText,
  createLabel = "Tạo",
  hideCreate = false,
  placeholder = "Gõ tên vật tư…",
  disabled = false,
}: {
  token: string;
  materialName: string | null;
  onPick: (m: StockMaterialOption) => void;
  onCreate: (name: string) => void;
  /** Báo text đang gõ ra ngoài — để dùng chính ô này làm tên hàng MỚI (không cần ô riêng). */
  onText?: (text: string) => void;
  /** Nhãn dòng thêm mới. Đề nghị KHÔNG tạo mã → "Hàng mới"; phiếu tạo mã → "Tạo mã". */
  createLabel?: string;
  /** Ẩn dòng "＋ Tạo …": khi text gõ vào ĐÃ là tên hàng mới (qua onText) thì không cần dòng này. */
  hideCreate?: boolean;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [text, setText] = useState(materialName ?? "");
  const [opts, setOpts] = useState<StockMaterialOption[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Đồng bộ khi tên hàng đổi từ ngoài (vừa chọn / vừa tạo).
  useEffect(() => {
    setText(materialName ?? "");
  }, [materialName]);

  // Tìm (debounce) khi đang mở + gõ.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const t = setTimeout(() => {
      api.kho.deNghi
        .vatTu(token, text.trim() || null, 20)
        .then((r) => {
          if (!cancelled) {
            setOpts(r);
            setActive(0);
          }
        })
        .catch(() => {});
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [text, open, token]);

  function reposition() {
    const el = inputRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setRect({ top: r.bottom + 4, left: r.left, width: r.width });
  }

  useLayoutEffect(() => {
    if (open) reposition();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open]);

  const trimmed = text.trim();
  const hasExact = opts.some((o) => (o.name ?? "").toLowerCase() === trimmed.toLowerCase());
  const showCreate = trimmed.length > 0 && !hasExact && !hideCreate;
  const rowCount = opts.length + (showCreate ? 1 : 0);

  function pick(m: StockMaterialOption) {
    setText(m.name ?? "");
    setOpen(false);
    onPick(m);
  }
  function create() {
    setOpen(false);
    onCreate(trimmed);
  }

  const list = (
    <ul
      className="kho-combo__list"
      role="listbox"
      style={rect ? { top: rect.top, left: rect.left, width: rect.width } : undefined}
    >
      {opts.map((o, i) => (
        <li
          key={o.id}
          role="option"
          aria-selected={i === active}
          className={`kho-combo__opt${i === active ? " is-active" : ""}`}
          onMouseEnter={() => setActive(i)}
          onMouseDown={(e) => {
            e.preventDefault();
            pick(o);
          }}
        >
          <span className="kho-combo__name">{o.name}</span>
          <span className="kho-combo__code">{o.code}</span>
        </li>
      ))}
      {showCreate && (
        <li
          role="option"
          aria-selected={active === opts.length}
          className={`kho-combo__opt kho-combo__create${active === opts.length ? " is-active" : ""}`}
          onMouseEnter={() => setActive(opts.length)}
          onMouseDown={(e) => {
            e.preventDefault();
            create();
          }}
        >
          ＋ {createLabel} “{trimmed}”
        </li>
      )}
      {rowCount === 0 && (
        <li className="kho-combo__empty" role="presentation">
          {hideCreate
            ? "Không có hàng trùng — tên vừa gõ sẽ là hàng mới."
            : "Gõ tên vật tư để tìm hoặc tạo mới."}
        </li>
      )}
    </ul>
  );

  return (
    <div className="kho-combo" ref={rootRef}>
      <input
        ref={inputRef}
        className="rc-input kho-combo__input"
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Vật tư"
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          onText?.(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, Math.max(0, rowCount - 1)));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            if (!open) return;
            e.preventDefault();
            if (active < opts.length) pick(opts[active]);
            else if (showCreate) create();
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && createPortal(list, document.body)}
    </div>
  );
}
