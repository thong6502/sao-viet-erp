// Bảng ĐƠN GIÁ khoán dùng chung ở 2 nơi:
//  - Tab "Lương khoán" tổng (departmentId = null) → mọi tổ, có ô chọn "Tổ".
//  - Panel Cấu hình lương của TỔ (departmentId = <id>) → chỉ tổ đó; tự gắn department_id +
//    group_name = tên tổ, ẩn ô "Tổ" (tổ suy từ ngữ cảnh).
// CRUD lưu ngay qua modal (độc lập với nút "Lưu thay đổi" của cấu hình component).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PieceRate, type PieceRateInput } from "../api/client";
import { money } from "../utils/format";

// Tổ khoán (nhãn) — chỉ dùng cho ô chọn ở tab tổng.
const KHOAN_GROUPS: { key: string; label: string }[] = [
  { key: "to_boi", label: "Tổ Bồi" },
  { key: "to_can_phu", label: "Tổ Cán/Phủ" },
  { key: "to_cat", label: "Tổ Cắt" },
  { key: "may_in_5mau", label: "Máy in 5 màu" },
  { key: "may_in_2mau", label: "Máy in 2 màu" },
  { key: "to_thanh_pham", label: "Tổ Thành phẩm" },
];
const KHOAN_GROUP_LABEL: Record<string, string> = Object.fromEntries(
  KHOAN_GROUPS.map((g) => [g.key, g.label]),
);
// `unit` lưu thẳng CHỮ HIỂN THỊ, CHỌN từ danh mục Đơn vị & quy đổi (chủ 2026-07-31) — trước đó gõ
// tự do, lệch một chữ là lệnh sản xuất vĩnh viễn không quy đổi ra tiền được. Không dựng danh sách
// cứng ở đây: danh mục là nguồn duy nhất, thêm đơn vị mới không phải sửa code.

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

export function KhoanRatesEditor({
  token,
  departmentId = null,
  deptName,
}: {
  token: string;
  departmentId?: number | null;
  deptName?: string;
}) {
  const perDept = departmentId != null;
  const [rates, setRates] = useState<PieceRate[]>([]);
  const [editing, setEditing] = useState<PieceRate | "new" | null>(null);
  // Đơn vị CHỌN ĐƯỢC — lấy thẳng danh mục Đơn vị & quy đổi.
  const [units, setUnits] = useState<string[]>([]);
  const load = useCallback(() => {
    api.luong
      .khoanRates(token, departmentId)
      .then((r) => setRates(r.items))
      .catch(() => setRates([]));
    api.luong
      .khoanUnits(token)
      .then((r) => setUnits(r.items))
      .catch(() => setUnits([]));
  }, [token, departmentId]);
  useEffect(() => {
    load();
  }, [load]);
  async function remove(id: number) {
    await api.luong.deleteKhoanRate(token, id);
    load();
  }

  return (
    <div>
      <div className="cc-toolbar">
        <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
          {perDept ? "Đơn giá khoán của tổ" : "Đơn giá khoán theo tổ"}
        </h4>
        <button className="btn btn--primary" onClick={() => setEditing("new")}>
          + Thêm đơn giá
        </button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr>
              {!perDept && <th>Tổ</th>}
              <th>Mã</th>
              <th>Công việc</th>
              <th>Đơn vị</th>
              <th className="lg-num">Đơn giá</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rates.map((r) => (
              <tr key={r.id}>
                {!perDept && <td>{KHOAN_GROUP_LABEL[r.group_name] ?? r.group_name}</td>}
                <td>{r.code ?? "—"}</td>
                <td>{r.name}</td>
                <td>{r.unit}</td>
                <td className="lg-num">{money(r.unit_price)}</td>
                <td className="cc-rowact">
                  <button className="btn btn--ghost" onClick={() => setEditing(r)}>
                    Sửa
                  </button>
                  <button
                    className="btn btn--ghost ns-danger"
                    onClick={() => remove(r.id)}
                  >
                    Xóa
                  </button>
                </td>
              </tr>
            ))}
            {rates.length === 0 && (
              <tr>
                <td colSpan={perDept ? 5 : 6} className="ns__empty">
                  Chưa có đơn giá khoán nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && (
        <KhoanRateModal
          token={token}
          rate={editing === "new" ? null : editing}
          departmentId={departmentId}
          deptName={deptName}
          units={units}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function KhoanRateModal({
  token,
  rate,
  departmentId = null,
  deptName,
  units,
  onClose,
  onSaved,
}: {
  token: string;
  rate: PieceRate | null;
  departmentId?: number | null;
  deptName?: string;
  /** Gợi ý đơn vị — KHÔNG phải whitelist; gõ ngoài danh sách vẫn lưu được. */
  units: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const perDept = departmentId != null;
  const [group, setGroup] = useState(rate?.group_name ?? KHOAN_GROUPS[0].key);
  const [name, setName] = useState(rate?.name ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "");
  const [price, setPrice] = useState(rate?.unit_price ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    // Trong ngữ cảnh tổ: gắn department_id + group_name = tên tổ (nhãn). Tab tổng: dùng ô "Tổ".
    const input: PieceRateInput = {
      group_name: perDept ? (deptName ?? String(departmentId)).slice(0, 40) : group,
      department_id: departmentId,
      code: rate?.code ?? null,     // mã do máy sinh, người dùng không gõ
      name,
      unit,
      unit_price: price,
      is_active: true,
    };
    try {
      if (rate) await api.luong.updateKhoanRate(token, rate.id, input);
      else await api.luong.createKhoanRate(token, input);
      onSaved();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      {/* Rộng hơn modal chuẩn 490px: form này có thêm bảng tick công đoạn (13+ mục) — để 490 thì
          grid 2 cột bị min-content của bảng tick đẩy tràn, cắt mất ô Đơn giá và dòng hướng dẫn. */}
      <div className="ns-modal__box ns-modal__box--khoan">
        <header className="ns-modal__head">
          <h2>{rate ? "Sửa đơn giá khoán" : "Thêm đơn giá khoán"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {/* Thứ tự trường theo TẦM QUAN TRỌNG: tên công việc (thứ đang đặt tên) → đơn giá +
              đơn vị (cặp đi liền) → mã (không bắt buộc, để cuối). Bản cũ đặt "Mã (nếu có)" lên
              đầu và đẩy "Công việc *" xuống cuối — bắt buộc lại nằm dưới không bắt buộc. */}
          <div className="ns-grid">
            {!perDept && (
              <div className="ns-field ns-wizard__full">
                <span className="ns-field__label">Tổ *</span>
                {/* `group_name` là CHỮ TỰ DO (dòng khai trong Cấu hình lương của tổ lưu thẳng TÊN
                    tổ, vd "Tổ Cán màng"), 6 mã dưới đây chỉ là mồi — gõ tên tổ mới vẫn nhận. Giá
                    trị hiện tại luôn nằm trong danh sách, không thì mở form ra ô rơi về mã đầu và
                    bấm Lưu là đổi tổ của dòng đó mà không ai thấy. */}
                <ComboBox
                  value={group}
                  allowFree
                  placeholder="Gõ để tìm tổ…"
                  options={[
                    ...(group && !KHOAN_GROUPS.some((g) => g.key === group)
                      ? [{ value: group, label: KHOAN_GROUP_LABEL[group] ?? group }] : []),
                    ...KHOAN_GROUPS.map((g) => ({ value: g.key, label: g.label })),
                  ]}
                  onChange={setGroup}
                />
              </div>
            )}
            <label className="ns-field ns-wizard__full">
              <span className="ns-field__label">Công việc *</span>
              <input
                value={name}
                autoFocus
                onChange={(e) => setName(e.target.value)}
                placeholder="vd: Bồi carton 3 lớp E,B"
              />
            </label>
            {/* CHỌN từ danh mục Đơn vị & quy đổi (chủ 2026-07-31), không gõ tự do nữa: đơn vị gõ
                tay mà lệch một chữ là lệnh sản xuất vĩnh viễn không quy đổi ra tiền được. Thiếu
                đơn vị thì thêm ở danh mục — một nguồn, không hai. */}
            <div className="ns-field">
              <span className="ns-field__label">Đơn vị *</span>
              <ComboBox
                value={unit}
                placeholder="Gõ để tìm đơn vị…"
                options={[
                  // Dòng cũ lỡ mang đơn vị ngoài danh mục thì vẫn giữ nguyên, không tự đổi hộ.
                  ...(unit && !units.includes(unit) ? [{ value: unit, label: unit }] : []),
                  ...units.map((u) => ({ value: u, label: u })),
                ]}
                onChange={setUnit}
              />
            </div>
            <label className="ns-field">
              <span className="ns-field__label">Đơn giá *</span>
              {/* Hậu tố ĐỘNG theo ô Đơn vị bên trái — "160.000 đ/m²" đọc thành câu ngay tại
                  chỗ, khỏi phải tự nối hai ô với nhau.
                  KHÔNG dùng `rc-input` của RebuildCatalog: nó khác bo góc / cỡ chữ / màu focus
                  so với `ns-field input`, đặt cạnh 3 ô kia là lạc lõng ngay. */}
              <div className="cl-suffixed">
                <input
                  type="number"
                  min={0}
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                />
                <span>đ/{unit.trim() || "đơn vị"}</span>
              </div>
            </label>
            {/* Ở đây CHỈ KHAI BÁO (chủ 2026-07-31): tổ · công việc · đơn vị · đơn giá. Mọi phép
                nhân ra tiền nằm bên sản xuất. Đã gỡ ô "Tính theo" (nhân ngầm số lượt), khối tick
                "Áp cho công đoạn nào" (luật khớp ngầm) và ô Mã (máy sinh KH-####). */}
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          {/* Thiếu tên công việc thì KHOÁ luôn, đừng để bấm xong mới báo đỏ. */}
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !name.trim()}
            title={!name.trim() ? "Nhập tên công việc trước" : undefined}
          >
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

/** Ô CHỌN kiểu GÕ-ĐỂ-LỌC (Tổ · Đơn vị). `<select>` bắt cuộn tay giữa 18 dòng đơn vị mà không gõ
 *  tắt được; ở đây gõ "cu" là còn "cuốn", bỏ dấu khi so nên gõ "cuon" cũng ra.
 *
 *  `allowFree`: Tổ là chữ TỰ DO (xưởng tự đặt tên tổ) nên gõ tên mới vẫn nhận. Đơn vị thì KHÔNG —
 *  phải là dòng của danh mục Đơn vị & quy đổi, lệch một chữ là lệnh không quy đổi ra tiền được. */
function ComboBox({
  value,
  options,
  placeholder,
  allowFree = false,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  placeholder?: string;
  allowFree?: boolean;
  onChange: (v: string) => void;
}) {
  const [q, setQ] = useState<string | null>(null);   // null = không gõ → hiện giá trị đang chọn
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);

  const norm = (s: string) =>
    s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
  const nhan = options.find((o) => o.value === value)?.label ?? value ?? "";
  const nq = norm((q ?? "").trim());
  const loc = nq ? options.filter((o) => norm(o.label).includes(nq)) : options;

  // Bấm ra ngoài = bỏ dở việc gõ, ô trả về giá trị đang chọn (không tự nhận chữ dở dang).
  useEffect(() => {
    if (!open) return;
    const ngoai = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) { setOpen(false); setQ(null); }
    };
    document.addEventListener("mousedown", ngoai);
    return () => document.removeEventListener("mousedown", ngoai);
  }, [open]);

  const chon = (v: string) => { onChange(v); setQ(null); setOpen(false); };

  return (
    <div className="khoan-cbx" ref={wrap}>
      <input
        value={q ?? nhan}
        placeholder={placeholder}
        onChange={(e) => { setQ(e.target.value); setIdx(0); setOpen(true); }}
        onFocus={() => { setQ(""); setOpen(true); }}
        onBlur={() => { if (allowFree && q !== null && q.trim()) onChange(q.trim()); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault(); setOpen(true); setIdx((i) => Math.min(i + 1, loc.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault(); setIdx((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter" && open && loc[idx]) {
            e.preventDefault(); chon(loc[idx].value);
          } else if (e.key === "Escape") {
            setOpen(false); setQ(null);
          }
        }}
      />
      {open && (
        <div className="khoan-cbx__list" role="listbox">
          {loc.map((o, i) => (
            <button
              key={o.value}
              type="button"
              role="option"
              aria-selected={o.value === value}
              className={`khoan-cbx__item${i === idx ? " is-active" : ""}${o.value === value ? " is-on" : ""}`}
              onMouseEnter={() => setIdx(i)}
              onMouseDown={(e) => e.preventDefault()}   // giữ focus để onBlur không nuốt cú bấm
              onClick={() => chon(o.value)}
            >
              {o.label}
            </button>
          ))}
          {loc.length === 0 && (
            <span className="khoan-cbx__empty">
              {allowFree
                ? "Chưa có tổ nào tên vậy — gõ xong bấm ra ngoài là dùng tên vừa gõ."
                : "Không có đơn vị nào khớp. Thêm ở Cấu hình danh mục → Đơn vị & quy đổi."}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
