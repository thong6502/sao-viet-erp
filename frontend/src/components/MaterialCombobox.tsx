// Ô CHỌN MẶT HÀNG cho dòng đề nghị kho / bảng giá NCC.
//
// Nguồn là DANH MỤC GỐC (Giấy + Vật tư khác) qua `/api/vat-lieu-kho/mat-hang` — trước đây ô này
// đọc bảng `materials` riêng của kho, nên cùng một tờ giấy tồn tại hai bản ghi không biết nhau.
//
// KHÔNG còn dòng "＋ Tạo …": mọi thứ nhập kho phải có sẵn trong danh mục (chủ chốt 2026-08-08).
// Gõ không ra thì chỉ đường về danh mục, chứ không mời người ta đẻ mã tại chỗ — mã đẻ vội là
// nguồn của tên lệch/mã trùng, đúng thứ làm kho và mua hàng không nối được với nhau.
//
// Dropdown render qua PORTAL (position: fixed) vì bảng dòng + thân drawer đều overflow.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type HangLoai, type MatHangOption } from "../api/client";

export function MaterialCombobox({
  token,
  hangTen,
  onPick,
  placeholder = "Gõ tên vật tư…",
  disabled = false,
  /** Lọc theo tồn: màn đề nghị XUẤT chỉ nên mời mặt hàng đang có hàng. */
  loc,
}: {
  token: string;
  /** Tên mặt hàng đang chọn (hiện trong ô). Null = chưa chọn. */
  hangTen: string | null;
  onPick: (m: MatHangOption) => void;
  placeholder?: string;
  disabled?: boolean;
  loc?: (m: MatHangOption) => boolean;
}) {
  const [text, setText] = useState(hangTen ?? "");
  const [opts, setOpts] = useState<MatHangOption[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setText(hangTen ?? "");
  }, [hangTen]);

  // Tìm (debounce) khi đang mở + gõ.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const t = setTimeout(() => {
      api.matHang
        .tim(token, text.trim() || null, 20)
        .then((r) => {
          if (!cancelled) {
            setOpts(loc ? r.filter(loc) : r);
            setActive(0);
          }
        })
        .catch(() => {});
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [text, open, token, loc]);

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

  function pick(m: MatHangOption) {
    setText(m.ten);
    setOpen(false);
    onPick(m);
  }

  const list = (
    <ul
      className="kho-combo__list"
      role="listbox"
      style={rect ? { top: rect.top, left: rect.left, width: rect.width } : undefined}
    >
      {opts.map((o, i) => (
        <li
          key={`${o.hang_loai}:${o.hang_id}`}
          role="option"
          aria-selected={i === active}
          className={`kho-combo__opt${i === active ? " is-active" : ""}`}
          onMouseEnter={() => setActive(i)}
          onMouseDown={(e) => {
            e.preventDefault();
            pick(o);
          }}
        >
          <span className="kho-combo__name">
            {o.ten}
            {/* Chip nhóm: Giấy và Vật tư khác có thể trùng tên gần giống nhau, không phân biệt
                được thì chọn nhầm mà không ai hay. */}
            <span className="kho-combo__nhom">{o.nhom}</span>
          </span>
          <span className="kho-combo__code">{o.ma}</span>
        </li>
      ))}
      {opts.length === 0 && (
        <li className="kho-combo__empty" role="presentation">
          Không có trong danh mục — khai ở Cấu hình danh mục → Giấy / Vật tư khác.
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
            if (!open) return;
            e.preventDefault();
            if (active < opts.length) pick(opts[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && createPortal(list, document.body)}
    </div>
  );
}

/** Ô CHỌN ĐƠN VỊ theo mặt hàng đang chọn.
 *
 *  Danh sách KHÔNG cố định: nó là "đơn vị gốc + mọi đơn vị đổi được với nó", tính riêng cho từng
 *  mặt hàng (giấy đếm kg thì thấy kg/g/tấn; keo khai quy cách thùng thì thấy thêm thùng). Vì thế
 *  không tái dùng được ô chọn đơn vị dùng-chung nào — phải hỏi server theo mặt hàng.
 *
 *  Mặt hàng chưa khai đơn vị gốc → khoá ô + hiện nguyên văn `ly_do` để người dùng biết đi đâu sửa,
 *  thay vì đưa một ô rỗng không giải thích.
 */
export function DonViChonTheoHang({
  token,
  hangLoai,
  hangId,
  value,
  onChange,
  onQuyDoi,
  disabled = false,
}: {
  token: string;
  hangLoai: HangLoai | null;
  hangId: number | null;
  value: string;
  onChange: (ma: string, heSoVeGoc: number | null) => void;
  /** Hệ số quy đổi của ĐƠN VỊ ĐANG CHỌN về đơn vị gốc — bắn cả khi dòng nạp sẵn từ DB, không chỉ
   *  lúc người dùng bấm đổi (`onChange`). Thiếu nó thì dòng cũ không có gì để quy đổi hiển thị.
   *  `heSoVeGoc` = 1 đơn vị này bằng bao nhiêu đơn vị gốc (dùng CHIA để ra giá/đơn-vị-gốc). */
  onQuyDoi?: (info: { donViGocTen: string; heSoVeGoc: number } | null) => void;
  disabled?: boolean;
}) {
  const [ds, setDs] = useState<{ ma: string; ten: string; he_so_ve_goc: number; la_goc: boolean }[]>([]);
  const [lyDo, setLyDo] = useState<string | null>(null);
  // Callback giữ trong ref: nơi gọi hay truyền arrow inline, đưa thẳng vào deps là vòng lặp render.
  const quyDoiRef = useRef(onQuyDoi);
  quyDoiRef.current = onQuyDoi;

  useEffect(() => {
    if (!hangLoai || !hangId) {
      setDs([]);
      setLyDo(null);
      return;
    }
    let alive = true;
    api.matHang
      .donVi(token, hangLoai, hangId)
      .then((r) => {
        if (!alive) return;
        setDs(r.ds);
        setLyDo(r.ly_do);
        // Chưa chọn đơn vị → mặc định ĐƠN VỊ GỐC, khỏi bắt người ta chọn lại thứ hiển nhiên.
        if (!value && r.don_vi_goc) {
          const goc = r.ds.find((d) => d.la_goc);
          onChange(r.don_vi_goc, goc ? goc.he_so_ve_goc : 1);
        }
      })
      .catch(() => {
        if (alive) {
          setDs([]);
          setLyDo("Không tải được danh sách đơn vị.");
        }
      });
    return () => {
      alive = false;
    };
    // `value`/`onChange` cố tình KHÔNG nằm trong deps: chỉ nạp lại khi ĐỔI MẶT HÀNG, không phải
    // mỗi lần người dùng đổi đơn vị.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, hangLoai, hangId]);

  // Báo hệ số của đơn vị ĐANG chọn mỗi khi danh sách hoặc lựa chọn đổi.
  useEffect(() => {
    if (!quyDoiRef.current) return;
    const goc = ds.find((d) => d.la_goc);
    const dv = ds.find((d) => d.ma === value);
    quyDoiRef.current(
      goc && dv && dv.he_so_ve_goc > 0
        ? { donViGocTen: goc.ten, heSoVeGoc: dv.he_so_ve_goc }
        : null,
    );
  }, [ds, value]);

  if (lyDo) {
    return (
      <span className="kho-dv__loi" title={lyDo}>
        ⚠ {lyDo}
      </span>
    );
  }
  return (
    <select
      className="rc-input"
      style={{ minWidth: 88 }}
      value={value}
      disabled={disabled || ds.length === 0}
      aria-label="Đơn vị tính"
      onChange={(e) => {
        const d = ds.find((x) => x.ma === e.target.value);
        onChange(e.target.value, d ? d.he_so_ve_goc : null);
      }}
    >
      {ds.length === 0 && <option value="">—</option>}
      {ds.map((d) => (
        <option key={d.ma} value={d.ma}>
          {d.ten}
          {d.la_goc ? " (gốc)" : ""}
        </option>
      ))}
    </select>
  );
}
