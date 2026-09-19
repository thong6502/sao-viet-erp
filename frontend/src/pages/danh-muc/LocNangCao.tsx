// Bảng "Lọc nâng cao" của màn danh mục — các tiêu chí NGOÀI hàng chip, ghép VÀ với chip và ô tìm.
//
// Hai dạng, cùng một giá trị `value` (`{key: giá trị}`, khoá vắng = không lọc theo tiêu chí đó):
//   · MỞ   — hàng ô chọn, mỗi tiêu chí một ô, kèm "Xoá bộ lọc".
//   · ĐÓNG mà vẫn đang lọc — hàng nhãn "Khách hàng: Minh Long ✕". Gập bảng lại mà không còn gì
//     nói bảng đang bị cắt thì người ta tưởng danh mục chỉ có chừng đó dòng.
// Lọc chạy ở MÁY CHỦ (`CatalogListPage` gửi `value` thành query param) — component này chỉ giữ ô.
import { useEffect, useRef, useState } from "react";

import { crud, type Row } from "../../api/rebuildCatalog";
import { useTre } from "../../lib/useTre";
import { RefSearchField } from "./fields/RefFields";
import { XIcon } from "./icons";
import type { LocNangCaoDef } from "./types";

export type GiaTriLoc = Record<string, string | number>;

/** Danh mục nguồn của ô `ref-search`, đã đổi về `ma`/`ten`. Khách hàng dùng `code`/`name` — không
 *  đổi thì ô tìm-chọn khớp trên `undefined` và bày một danh sách trắng. */
function useNguonLoc(defs: LocNangCaoDef[], token: string | null): Record<string, Row[]> {
  const [nguon, setNguon] = useState<Record<string, Row[]>>({});
  useEffect(() => {
    if (!token) return;
    let alive = true;
    const doVao = (key: string, items: Row[]) => {
      const chuan = items.map((o) => ({
        ...o,
        ma: String(o.ma ?? o.code ?? ""),
        ten: String(o.ten ?? o.name ?? ""),
      }));
      setNguon((d) => ({ ...d, [key]: chuan }));
    };
    for (const d of defs) {
      if (d.type !== "ref-search" || !d.refPrefix) continue;
      const { nho, moi } = crud(d.refPrefix).thamChieu(token, d.refParams ?? {});
      if (nho) doVao(d.key, nho);
      moi.then((items) => { if (alive) doVao(d.key, items); }).catch(() => {});
    }
    return () => { alive = false; };
  }, [defs, token]);
  return nguon;
}

/** Ô gõ tự do. Giữ chữ ở state RIÊNG và chỉ báo lên sau khi ngừng gõ 300ms — cùng nhịp ô tìm
 *  chính; báo từng phím thì mỗi chữ một lần hỏi máy chủ. Giá trị bị xoá từ NGOÀI (✕ trên nhãn,
 *  "Xoá bộ lọc") thì ô phải theo về, không thì còn chữ cũ nằm đó mà bảng đã hết lọc. */
function OChuLoc({ value, onChange, label, placeholder }: {
  value: string; onChange: (v: string | null) => void; label: string; placeholder?: string;
}) {
  const [chu, setChu] = useState(value);
  const tre = useTre(chu);
  // Giá trị ô này báo lên lần cuối. `value` đổi mà KHÁC nó ⇒ đổi từ ngoài, kéo ô theo; bằng nó ⇒ là
  // tiếng vọng của chính mình, bỏ qua — so với `chu` thì đang gõ dở "B3" bị kéo ngược về "B".
  const daBao = useRef(value);
  useEffect(() => {
    const v = tre.trim();
    if (v === daBao.current) return;
    daBao.current = v;
    onChange(v || null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ báo khi CHỮ đã lắng
  }, [tre]);
  useEffect(() => {
    if (value === daBao.current) return;
    daBao.current = value;
    setChu(value);
  }, [value]);
  return (
    <input className="rc-input" aria-label={label} placeholder={placeholder}
      value={chu} onChange={(e) => setChu(e.target.value)} />
  );
}

export function LocNangCao({ defs, value, onChange, mo, token }: {
  defs: LocNangCaoDef[];
  value: GiaTriLoc;
  onChange: (v: GiaTriLoc) => void;
  /** Bảng đang mở (hàng ô chọn) hay gập (chỉ còn nhãn của tiêu chí đang áp). */
  mo: boolean;
  token: string | null;
}) {
  const nguon = useNguonLoc(defs, token);

  const dat = (key: string, v: string | number | null) => {
    const moi = { ...value };
    if (v == null || v === "") delete moi[key];
    else moi[key] = v;
    onChange(moi);
  };

  /** Chữ hiện cho giá trị đang lọc — nhãn của lựa chọn, hoặc tên dòng của danh mục nguồn. Chưa nạp
   *  kịp nguồn thì hiện tạm giá trị thô, KHÔNG để trống: nhãn rỗng trông như bộ lọc hỏng. */
  const nhanGiaTri = (d: LocNangCaoDef): string => {
    const v = value[d.key];
    if (d.type === "select") return d.options?.find((o) => o.value === String(v))?.label ?? String(v);
    if (d.type === "text") return `"${v}"`;
    const dong = (nguon[d.key] ?? []).find((o) => o.id === Number(v));
    return dong ? String(dong.ten || dong.ma) : `#${v}`;
  };

  const dangAp = defs.filter((d) => value[d.key] != null && value[d.key] !== "");

  if (!mo) {
    if (dangAp.length === 0) return null;
    return (
      <div className="rc__locnc-tags" aria-label="Bộ lọc đang áp">
        {dangAp.map((d) => (
          <span key={d.key} className="rc__locnc-tag">
            <span className="rc__locnc-tag-k">{d.label}:</span> {nhanGiaTri(d)}
            <button type="button" className="rc__locnc-tag-x" aria-label={`Bỏ lọc ${d.label}`}
              title={`Bỏ lọc ${d.label}`} onClick={() => dat(d.key, null)}>
              <XIcon size={11} />
            </button>
          </span>
        ))}
        {dangAp.length > 1 && (
          <button type="button" className="rc__locnc-clear" onClick={() => onChange({})}>Xoá hết</button>
        )}
      </div>
    );
  }

  return (
    <div className="rc__locnc" role="group" aria-label="Lọc nâng cao">
      {/* `div` chứ KHÔNG `label`: ô tìm-chọn đã chọn có nút ✕ bên trong, mà bấm vào chữ của một
          `label` là bấm hộ phần tử điều khiển ĐẦU TIÊN trong nó — tức bấm nhầm ✕, xoá mất bộ lọc. */}
      {defs.map((d) => (
        <div key={d.key} className={d.type === "ref-search" ? "rc__locnc-field rc__locnc-field--rong" : "rc__locnc-field"}>
          <span className="rc__locnc-label">{d.label}</span>
          {d.type === "text" ? (
            <OChuLoc value={value[d.key] != null ? String(value[d.key]) : ""} label={d.label}
              placeholder={d.placeholder} onChange={(v) => dat(d.key, v)} />
          ) : d.type === "select" ? (
            <select className="rc-input" aria-label={d.label}
              value={value[d.key] != null ? String(value[d.key]) : ""}
              onChange={(e) => dat(d.key, e.target.value)}>
              <option value="">Tất cả</option>
              {(d.options ?? []).map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          ) : (
            <RefSearchField
              value={value[d.key] != null ? Number(value[d.key]) : null}
              options={nguon[d.key] ?? []}
              placeholder={`Gõ tên ${d.label.toLowerCase()} để tìm…`}
              onChange={(v) => dat(d.key, v)}
            />
          )}
        </div>
      ))}
      {dangAp.length > 0 && (
        <button type="button" className="rc__locnc-clear" onClick={() => onChange({})}>Xoá bộ lọc</button>
      )}
    </div>
  );
}
