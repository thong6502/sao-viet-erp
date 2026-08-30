// Ô TÌM Sản phẩm tái bản — gõ tên, chọn một kết quả để nạp NGUYÊN cấu hình kỹ thuật đã từng
// chốt đơn (docs/spec-san-pham-tai-ban.md). Ô này là một Ô RIÊNG (khác ô "Tên sản phẩm" bên
// cạnh): gõ xong CHỌN là kích hoạt hành động nạp (không tự giữ giá trị) — nên input tự trở về
// rỗng sau khi chọn, sẵn sàng cho lượt tìm tiếp theo.
//
// Tái dùng nguyên bộ CSS `.kho-combo*` sẵn có trong repo (global, xem `cssKhongCuop.test.ts`) —
// cùng một ngôn ngữ thị giác cho "gõ tên, chọn gợi ý".
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api, ApiError, type SanPhamTaiBanGoiY as GoiY } from "../api/client";

function fmtNgay(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function SanPhamTaiBanGoiY({
  token,
  onChon,
  placeholder = "Gõ tên sản phẩm đã từng chốt đơn…",
  ariaLabel = "Tìm sản phẩm tái bản",
}: {
  token: string;
  onChon: (id: number) => void;
  placeholder?: string;
  ariaLabel?: string;
}) {
  const [value, setValue] = useState("");
  const [opts, setOpts] = useState<GoiY[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    let huy = false;
    const t = setTimeout(() => {
      api.phieuTinhGia
        .timSanPhamTaiBan(token, value.trim(), 20)
        .then((items) => {
          if (huy) return;
          setOpts(items);
          setActive(0);
        })
        .catch(() => {});
    }, 200);
    return () => {
      huy = true;
      clearTimeout(t);
    };
  }, [value, open, token]);

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

  function chon(o: GoiY) {
    onChon(o.id);
    setValue("");
    setOpen(false);
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
            chon(o);
          }}
        >
          <span className="kho-combo__name">{o.ten}</span>
          <span className="kho-combo__code">Cập nhật {fmtNgay(o.updated_at)}</span>
        </li>
      ))}
      {opts.length === 0 && (
        <li className="kho-combo__empty" role="presentation">
          Chưa có sản phẩm nào từng chốt đơn tên như vậy.
        </li>
      )}
    </ul>
  );

  return (
    <div className="kho-combo" ref={rootRef}>
      <input
        ref={inputRef}
        className="tg-input"
        type="text"
        value={value}
        placeholder={placeholder}
        aria-label={ariaLabel}
        autoComplete="off"
        onChange={(e) => {
          setValue(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, Math.max(0, opts.length - 1)));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            if (!open || active >= opts.length) return;
            e.preventDefault();
            chon(opts[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && createPortal(list, document.body)}
    </div>
  );
}

// Re-export type để tránh import trùng `ApiError` không dùng gây lỗi lint ở nơi khác — giữ tối
// giản, module này chỉ cần `api`.
export type { ApiError };
