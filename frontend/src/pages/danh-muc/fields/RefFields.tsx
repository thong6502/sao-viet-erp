// Hai ô TRỎ SANG DANH MỤC KHÁC:
//   `RefMultiField`  — chọn NHIỀU + xếp thứ tự (lưu mảng id), vẽ dạng dòng thời gian.
//   `RefSearchField` — tìm-chọn MỘT (typeahead, bỏ dấu vẫn khớp), lưu id hoặc MÃ.
import { useState } from "react";

import { ArrowDownIcon, ArrowUpIcon, TrashIcon } from "../icons";
import type { Row } from "../types";

export function RefMultiField({ value, options, onChange }: {
  value: number[]; options: Row[]; onChange: (v: number[]) => void;
}) {
  const byId = (id: number) => options.find((o) => o.id === id);
  const move = (i: number, d: number) => {
    const a = [...value]; const j = i + d;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]]; onChange(a);
  };
  const remaining = options.filter((o) => !value.includes(o.id));

  return (
    <div className="rc-rt">
      {value.length === 0 ? (
        <div className="rc-timeline__empty">Chưa chọn công đoạn nào. Hãy thêm ở dưới.</div>
      ) : (
        <div className="rc-timeline">
          {value.map((id, i) => {
            const r = byId(id);
            return (
              <div className="rc-timeline__node" key={id}>
                <div className="rc-timeline__line" />
                <div className="rc-timeline__marker">{i + 1}</div>
                <div className="rc-timeline__content">
                  <span className="rc-timeline__name">{r ? `${r.ma} · ${r.ten}` : `#${id} (đã xóa)`}</span>
                  <div className="rc-timeline__actions">
                    <button type="button" className="rc-timeline__btn" onClick={() => move(i, -1)} disabled={i === 0} title="Di chuyển lên">
                      <ArrowUpIcon />
                    </button>
                    <button type="button" className="rc-timeline__btn" onClick={() => move(i, 1)} disabled={i === value.length - 1} title="Di chuyển xuống">
                      <ArrowDownIcon />
                    </button>
                    <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" onClick={() => onChange(value.filter((_, k) => k !== i))} title="Bỏ chọn">
                      <TrashIcon />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div className="rc-input-wrapper rc-rt__add">
        <select className="rc-input" value=""
          onChange={(e) => { if (e.target.value) onChange([...value, Number(e.target.value)]); }}>
          <option value="">+ Thêm công đoạn tiếp theo…</option>
          {remaining.map((o) => <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>)}
        </select>
      </div>
    </div>
  );
}

// Ô tìm-chọn 1 danh mục theo MÃ (typeahead, bỏ dấu vẫn khớp) — vd chọn bù hao cho công đoạn.
export function RefSearchField({ value, options, placeholder, byMa, onChange }: {
  value: number | string | null; options: Row[]; placeholder?: string;
  /** Lưu MÃ (chuỗi) thay vì id — cho cột trỏ danh mục bằng mã, vd `don_vi_gia`. */
  byMa?: boolean;
  onChange: (v: number | string | null) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const norm = (s: string) =>
    s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
  const rong = value == null || value === "";
  const selected = rong ? null : options.find(
    (o) => (byMa ? String(o.ma ?? "").toLowerCase() === String(value).toLowerCase() : o.id === value)
  ) ?? null;
  const nq = norm(q.trim());
  const matches = (nq
    ? options.filter((o) => norm(`${o.ma} ${o.ten}`).includes(nq))
    : options
  ).slice(0, 20);

  // Có giá trị nhưng KHÔNG khớp danh mục (đơn vị đã ngừng dùng / mã cũ). Hiện nguyên mã + báo đỏ:
  // để ô trắng như chưa chọn thì người dùng tưởng trống, bấm Lưu và giá trị hỏng vẫn nằm nguyên đó.
  if (!rong && !selected) {
    return (
      <div className="rc-input-wrapper" style={{ display: "flex", gap: "6px", alignItems: "stretch" }}>
        <span className="rc-input" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--danger, #b3261e)" }}>
          <span><b style={{ fontFamily: "var(--ff-num)" }}>{String(value)}</b> · không có trong danh mục</span>
          <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" title="Bỏ chọn — tìm lại"
            onClick={() => { onChange(null); setQ(""); setOpen(true); }}>✕</button>
        </span>
      </div>
    );
  }
  if (selected) {
    const displayName = selected.ten ? String(selected.ten) : String(selected.ma ?? value);
    return (
      <div className="rc-input-wrapper" style={{ display: "flex", gap: "6px", alignItems: "stretch" }}>
        <span className="rc-input" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", fontWeight: 500 }}>
          <span>{displayName}</span>
          <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" title="Bỏ chọn — tìm lại"
            onClick={() => { onChange(null); setQ(""); setOpen(true); }}>✕</button>
        </span>
      </div>
    );
  }
  return (
    <div className="rc-input-wrapper" style={{ position: "relative" }}>
      <input className="rc-input" value={q} placeholder={placeholder ?? "Gõ mã / tên để tìm…"}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && matches.length > 0 && (
        <div className="rc-ref-search-panel">
          {matches.map((o) => {
            const showCode = o.ma && o.ma.toLowerCase() !== String(o.ten).toLowerCase();
            return (
              <button
                type="button"
                key={o.id}
                className="rc-ref-search-item"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { onChange(byMa ? String(o.ma) : o.id); setQ(""); setOpen(false); }}
              >
                <span className="rc-ref-search-item__name">{o.ten || o.ma}</span>
                {showCode && <span className="rc-ref-search-item__code">{o.ma}</span>}
              </button>
            );
          })}
        </div>
      )}
      {open && nq && matches.length === 0 && (
        <div className="rc-ref-search-panel" style={{ padding: "10px 12px", color: "var(--ash, #64748b)", fontSize: "12.5px" }}>
          Không thấy mã/tên khớp “{q}”.
        </div>
      )}
    </div>
  );
}
