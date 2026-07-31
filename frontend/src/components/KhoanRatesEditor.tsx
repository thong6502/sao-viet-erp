// Bảng ĐƠN GIÁ khoán dùng chung ở 2 nơi:
//  - Tab "Lương khoán" tổng (departmentId = null) → mọi tổ, có ô chọn "Tổ".
//  - Panel Cấu hình lương của TỔ (departmentId = <id>) → chỉ tổ đó; tự gắn department_id +
//    group_name = tên tổ, ẩn ô "Tổ" (tổ suy từ ngữ cảnh).
// CRUD lưu ngay qua modal (độc lập với nút "Lưu thay đổi" của cấu hình component).
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Info,
  Save,
  X,
} from "lucide-react";
import { api, type PieceRate, type PieceRateInput } from "../api/client";
import { money } from "../utils/format";

const LEGACY_GROUP_LABEL: Record<string, string> = {
  to_boi: "Tổ Bồi",
  to_can_phu: "Tổ Cán/Phủ",
  to_cat: "Tổ Cắt",
  may_in_5mau: "Máy in 5 màu",
  may_in_2mau: "Máy in 2 màu",
  to_thanh_pham: "Tổ Thành phẩm",
};

const groupLabel = (g: string): string => LEGACY_GROUP_LABEL[g] ?? g;

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
  const [units, setUnits] = useState<string[]>([]);
  const [sxDepts, setSxDepts] = useState<{ id: number; name: string }[]>([]);

  const load = useCallback(() => {
    api.luong
      .khoanRates(token, departmentId)
      .then((r) => setRates(r.items))
      .catch(() => setRates([]));
    api.luong
      .khoanUnits(token)
      .then((r) => setUnits(r.items))
      .catch(() => setUnits([]));
    if (departmentId == null) {
      api.employees
        .meta(token)
        .then((m) =>
          setSxDepts(m.departments.filter((d) => d.la_san_xuat).map((d) => ({ id: d.id, name: d.name }))),
        )
        .catch(() => setSxDepts([]));
    }
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
                {!perDept && <td>{groupLabel(r.group_name)}</td>}
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
          sxDepts={sxDepts}
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
  sxDepts,
  onClose,
  onSaved,
}: {
  token: string;
  rate: PieceRate | null;
  departmentId?: number | null;
  deptName?: string;
  units: string[];
  sxDepts: { id: number; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const perDept = departmentId != null;
  const legacyKey = rate && rate.department_id == null ? `legacy:${rate.group_name}` : null;
  const [dept, setDept] = useState(
    legacyKey ?? (rate?.department_id != null ? String(rate.department_id) : ""),
  );
  const [name, setName] = useState(rate?.name ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "");
  const [price, setPrice] = useState(rate?.unit_price ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const isLegacy = dept.startsWith("legacy:");
  const chonDept = isLegacy ? null : sxDepts.find((d) => String(d.id) === dept) ?? null;

  async function save() {
    setBusy(true);
    setErr(null);
    const input: PieceRateInput = {
      group_name: perDept
        ? (deptName ?? String(departmentId)).slice(0, 40)
        : isLegacy
          ? dept.slice(7)
          : (chonDept?.name ?? "").slice(0, 40),
      department_id: perDept ? departmentId : (chonDept ? chonDept.id : null),
      code: rate?.code ?? null,
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
      <div className="ns-modal__box ns-modal__box--khoan">
        <header className="ns-modal__head">
          <div>
            <h2>{rate ? "Sửa đơn giá khoán" : "Thêm đơn giá khoán"}</h2>
            <div className="ns-modal__subtitle">Cấu hình thông tin công việc, đơn vị và định mức đơn giá</div>
          </div>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng modal">
            <X size={18} />
          </button>
        </header>
        <div className="ns-modal__body">
          {err && (
            <div className="banner banner--error" style={{ marginBottom: 16 }}>
              <AlertCircle size={16} />
              <span>{err}</span>
            </div>
          )}
          <div className="ns-grid">
            {!perDept && (
              <div className="ns-field ns-wizard__full">
                <span className="ns-field__label">Tổ *</span>
                <ComboBox
                  value={dept}
                  placeholder="Gõ để tìm tổ…"
                  options={[
                    ...(legacyKey
                      ? [{ value: legacyKey, label: `${groupLabel(legacyKey.slice(7))} (chưa gắn tổ)` }]
                      : []),
                    ...sxDepts.map((d) => ({ value: String(d.id), label: d.name })),
                  ]}
                  emptyText="Không có tổ nào khớp. Tổ mới thì thêm ở Phòng ban và bật Khối Sản xuất."
                  onChange={setDept}
                />
                {sxDepts.length === 0 && (
                  <div className="khoan-hint-box">
                    <Info size={16} style={{ flexShrink: 0 }} />
                    <span>
                      Chưa có phòng ban nào bật <b>Khối Sản xuất</b> — bật ở Phòng ban → Chỉnh sửa
                      thông tin, rồi quay lại.
                    </span>
                  </div>
                )}
                {isLegacy && (
                  <div className="khoan-hint-box">
                    <Info size={16} style={{ flexShrink: 0 }} />
                    <span>
                      Dòng cũ chưa gắn tổ thật nên bước lệnh sản xuất không thấy. Chọn lại một tổ
                      trong danh sách để nối vào.
                    </span>
                  </div>
                )}
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
            <div className="ns-field">
              <span className="ns-field__label">Đơn vị *</span>
              <ComboBox
                value={unit}
                placeholder="Gõ để tìm đơn vị…"
                options={[
                  ...(unit && !units.includes(unit) ? [{ value: unit, label: unit }] : []),
                  ...units.map((u) => ({ value: u, label: u })),
                ]}
                emptyText="Không có đơn vị nào khớp. Thêm ở Cấu hình danh mục → Đơn vị & quy đổi."
                onChange={setUnit}
              />
            </div>
            <label className="ns-field">
              <span className="ns-field__label">Đơn giá *</span>
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
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !name.trim() || (!perDept && !dept)}
            title={
              !name.trim() ? "Nhập tên công việc trước"
                : !perDept && !dept ? "Chọn tổ trước"
                  : undefined
            }
          >
            <Save size={15} style={{ marginRight: 6 }} />
            {busy ? "Đang lưu…" : "Lưu đơn giá"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ComboBox({
  value,
  options,
  placeholder,
  emptyText = "Không có dòng nào khớp.",
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  placeholder?: string;
  emptyText?: string;
  onChange: (v: string) => void;
}) {
  const [q, setQ] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const norm = (s: string) =>
    s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
  const nhan = options.find((o) => o.value === value)?.label ?? value ?? "";
  const nq = norm((q ?? "").trim());
  const loc = nq ? options.filter((o) => norm(o.label).includes(nq)) : options;

  const reposition = useCallback(() => {
    if (!inputRef.current) return;
    const r = inputRef.current.getBoundingClientRect();
    const listHeight = listRef.current?.offsetHeight || 210;
    const spaceBelow = window.innerHeight - r.bottom;
    const showAbove = spaceBelow < listHeight && r.top > listHeight;

    setRect({
      top: showAbove ? Math.max(10, r.top - listHeight - 6) : r.bottom + 4,
      left: r.left,
      width: r.width,
    });
  }, []);

  useLayoutEffect(() => {
    if (open) {
      reposition();
    }
  }, [open, reposition, loc.length]);

  useEffect(() => {
    if (!open) return;
    const handleDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        wrapRef.current?.contains(target) ||
        listRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
      setQ(null);
    };

    document.addEventListener("mousedown", handleDown);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("mousedown", handleDown);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open, reposition]);

  const chon = (v: string) => {
    onChange(v);
    setQ(null);
    setOpen(false);
  };

  const portalContent = open && (
    <div
      ref={listRef}
      className="khoan-cbx__list"
      role="listbox"
      style={
        rect
          ? {
              position: "fixed",
              top: rect.top,
              left: rect.left,
              width: rect.width,
              zIndex: 9999,
            }
          : { display: "none" }
      }
    >
      {loc.map((o, i) => {
        const selected = o.value === value;
        const active = i === idx;
        return (
          <button
            key={o.value}
            type="button"
            role="option"
            aria-selected={selected}
            className={`khoan-cbx__item${active ? " is-active" : ""}${selected ? " is-on" : ""}`}
            onMouseEnter={() => setIdx(i)}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => chon(o.value)}
          >
            <span className="khoan-cbx__item-text">{o.label}</span>
            {selected && <Check className="khoan-cbx__item-check" size={15} />}
          </button>
        );
      })}
      {loc.length === 0 && (
        <div className="khoan-cbx__empty">
          <Info size={16} className="khoan-cbx__empty-icon" />
          <span>{emptyText}</span>
        </div>
      )}
    </div>
  );

  return (
    <div className={`khoan-cbx${open ? " is-open" : ""}`} ref={wrapRef}>
      <div className="khoan-cbx__input-wrap">
        <input
          ref={inputRef}
          className="khoan-cbx__input"
          value={q ?? nhan}
          placeholder={placeholder}
          onChange={(e) => {
            setQ(e.target.value);
            setIdx(0);
            setOpen(true);
          }}
          onFocus={() => {
            setQ("");
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setIdx((i) => Math.min(i + 1, loc.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIdx((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter" && open && loc[idx]) {
              e.preventDefault();
              chon(loc[idx].value);
            } else if (e.key === "Escape") {
              setOpen(false);
              setQ(null);
            }
          }}
        />
        <ChevronDown className="khoan-cbx__arrow" size={16} />
      </div>
      {createPortal(portalContent, document.body)}
    </div>
  );
}

