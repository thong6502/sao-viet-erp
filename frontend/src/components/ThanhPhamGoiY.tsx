// Ô TÊN SẢN PHẨM có GỢI Ý từ danh mục Thành phẩm — dùng ở phiếu tính giá.
//
// KHÁC `MaterialCombobox` ở một điểm quyết định: ô kia **ép phải chọn** (mọi thứ nhập kho phải có
// sẵn trong danh mục, luật 08/08/2026). Ô này thì **gõ tự do là chính, gợi ý là phụ** — sản phẩm
// mới thì cứ gõ tên mới, không ai chặn.
//
// Vì sao gợi ý ở ĐÂY (chủ chốt 19/08/2026): tên gõ ở ô này đi thẳng tới đích không biến dạng —
//
//     phiếu tính giá `.ten` → quote_items.product_name → order_lines.description
//                                              (order_service.py:428)
//
// …và `order_lines.description` chính là nửa sau của khoá gộp trùng `(khách, tên đã chuẩn hoá)`.
// Nên chỉ cần người tính giá CHỌN LẠI đúng tên cũ là lúc chốt đơn hệ dùng lại đúng dòng danh mục
// cũ, không đẻ dòng mới. Không cần cột nối nào giữa dòng đơn và danh mục.
//
// Gợi ý KHÔNG lọc theo khách: phiếu tính giá chưa biết khách (khách chỉ gắn ở bước báo giá), và
// theo chủ dự án thì "nó chỉ là tên thành phẩm thôi" — có sẵn thì dùng lại tên đó.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { crud } from "../api/rebuildCatalog";

type GoiY = { id: number; ma: string; ten: string; customer_ten?: string | null };

export function ThanhPhamGoiY({
  token,
  value,
  onChange,
  placeholder,
  ariaLabel = "Tên sản phẩm",
}: {
  token: string;
  value: string;
  onChange: (ten: string) => void;
  placeholder?: string;
  ariaLabel?: string;
}) {
  const [opts, setOpts] = useState<GoiY[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Tìm (debounce) khi đang mở + gõ. Chỉ mời dòng ĐANG DÙNG — mời dòng đã ngừng là dẫn người ta
  // gõ lại một cái tên vừa bị khai tử.
  useEffect(() => {
    if (!open) return;
    let huy = false;
    const t = setTimeout(() => {
      crud("/api/vat-lieu-kho/thanh-pham")
        .list(token, { q: value.trim() || undefined, active: true, size: 20 })
        .then((r) => {
          if (huy) return;
          setOpts((r.items ?? []) as unknown as GoiY[]);
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

  // Dropdown render qua PORTAL (position: fixed) vì thân modal phiếu tính giá có overflow —
  // render tại chỗ là danh sách bị cắt cụt ngay dòng đầu.
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
    // Chép NGUYÊN VĂN tên trong danh mục — lệch một dấu là lúc chốt đơn không khớp khoá gộp nữa.
    onChange(o.ten);
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
          {/* CỐ Ý KHÔNG hiện tên khách (chủ 21/08/2026: "cái đó chỉ là có sản phẩm thôi, mình
              chỉ sử dụng lại tên đó thôi mà nên bỏ"). Ở đây người ta đang CHỌN LẠI MỘT CÁI TÊN,
              giống như bán cùng một cái quạt cho nhiều khách — tên khách không giúp gì cho việc
              chọn, mà lại dính liền tên sản phẩm thành "Sản phẩm BCông ty Bánh…". */}
          <span className="kho-combo__name">{o.ten}</span>
          <span className="kho-combo__code">{o.ma}</span>
        </li>
      ))}
      {opts.length === 0 && (
        <li className="kho-combo__empty" role="presentation">
          Chưa có thành phẩm nào tên như vậy — cứ gõ tên mới, hệ tự khai khi chốt đơn.
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
          onChange(e.target.value);
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
            // Enter khi ĐANG mở gợi ý mới là chọn. Đóng rồi thì để Enter đi tiếp như ô thường —
            // nuốt phím Enter của một ô text là thứ người dùng không đoán được.
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
