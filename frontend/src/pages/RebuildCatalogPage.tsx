// Trang danh mục GENERIC (rebuild) — list + drawer form theo SECTION + search + filter tab.
// 1 component cho 6 module (Máy · Vật liệu · Công đoạn · Loại SP) qua `config`. On-brand với
// design system app (tokens rust/ink/paper). Form lean nhưng có nhóm; đủ theo spec là follow-up.
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ApiError } from "../api/client";
import { crud, type Row } from "../api/rebuildCatalog";
import "./rebuild-catalog.css";

export interface FieldDef {
  key: string;
  label: string;
  type?: "text" | "number" | "select" | "checkbox" | "json" | "ref" | "ref-multi";
  options?: { value: string; label: string }[];
  refPrefix?: string;           // ref / ref-multi: endpoint danh mục nguồn (đổ dropdown theo TÊN)
  required?: boolean;
  hint?: string;
  group?: string;               // nhóm section trong drawer
  showIf?: (form: Record<string, unknown>) => boolean;  // ẩn/hiện field theo giá trị khác
}
export interface ColumnDef {
  key: string;
  label: string;
  render?: (r: Row) => ReactNode;
}
export interface FacetDef {
  key: string;                  // field lọc (vd "nhom")
  values: { value: string; label: string }[];
}
export interface CatalogConfig {
  title: string;
  subtitle: string;
  prefix: string;
  columns: ColumnDef[];
  fields: FieldDef[];
  facet?: FacetDef;             // tab lọc phía trên (tùy chọn)
}

export function RebuildCatalogPage({ config }: { config: CatalogConfig }) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Row | "new" | null>(null);
  const [q, setQ] = useState("");
  const [facet, setFacet] = useState("all");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.list(token)
      .then((r) => setRows(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
  }, [token, api]);
  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (facet !== "all" && config.facet && String(r[config.facet.key] ?? "") !== facet) return false;
      if (needle && !`${r.ma} ${r.ten}`.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [rows, q, facet, config.facet]);

  async function remove(r: Row) {
    if (!token || !window.confirm(`Xóa "${r.ten}" (${r.ma})?`)) return;
    try { await api.remove(token, r.id); load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Không xóa được."); }
  }

  const facetCount = (v: string) =>
    config.facet ? rows.filter((r) => String(r[config.facet!.key] ?? "") === v).length : 0;

  return (
    <main className="rc">
      <header className="rc__head">
        <p className="rc__eyebrow">Cấu hình danh mục · pipeline mới</p>
        <div className="rc__headrow">
          <h1 className="rc__title">{config.title}</h1>
          <span className="rc__count">{rows.length}</span>
        </div>
        <p className="rc__sub">{config.subtitle}</p>
      </header>

      <div className="rc__toolbar">
        <div className="rc__search-wrapper">
          <SearchIcon />
          <input className="rc__search" placeholder="Tìm mã / tên…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="rc__spacer" />
        <Button variant="accent" onClick={() => setEditing("new")}>
          <span style={{ fontSize: "16px", marginRight: "4px", fontWeight: "bold" }}>+</span> Thêm {config.title.toLowerCase()}
        </Button>
      </div>

      {config.facet && (
        <div className="rc__tabs">
          <button className={`rc__tab${facet === "all" ? " is-active" : ""}`} onClick={() => setFacet("all")}>
            Tất cả <span className="rc__tabn">{rows.length}</span>
          </button>
          {config.facet.values.map((v) => (
            <button key={v.value} className={`rc__tab${facet === v.value ? " is-active" : ""}`}
              onClick={() => setFacet(v.value)}>
              {v.label} <span className="rc__tabn">{facetCount(v.value)}</span>
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: "12px" }} onClick={() => { setError(null); load(); }}>Tải lại</button>
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: "15%" }}>Mã</th>
              <th style={{ width: "35%" }}>Tên</th>
              {config.columns.map((c) => <th key={c.key}>{c.label}</th>)}
              <th className="rc__actcol" style={{ width: "180px" }}>Hành động</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={config.columns.length + 3} className="rc__msg">Đang tải dữ liệu…</td></tr>
            ) : shown.length === 0 ? (
              <tr>
                <td colSpan={config.columns.length + 3} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="rc__empty-icon">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="m15 9-6 6M9 9l6 6"/>
                    </svg>
                    <p className="rc__empty-text">
                      {rows.length === 0 ? `Chưa có ${config.title.toLowerCase()} nào trong hệ thống.` : "Không tìm thấy kết quả phù hợp với bộ lọc."}
                    </p>
                    {rows.length === 0 ? (
                      <Button variant="ghost" onClick={() => setEditing("new")}>+ Tạo {config.title.toLowerCase()}</Button>
                    ) : (
                      <Button variant="ghost" onClick={() => { setQ(""); setFacet("all"); }}>Xóa bộ lọc</Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : shown.map((r) => (
              <tr key={r.id} className="rc__row" onClick={() => setEditing(r)}>
                <td className="rc__mono"><span className="rc__code-badge">{String(r.ma)}</span></td>
                <td className="rc__name">{String(r.ten)}</td>
                {config.columns.map((c) => (
                  <td key={c.key}>{c.render ? c.render(r) : (r[c.key] == null || r[c.key] === "" ? "—" : String(r[c.key]))}</td>
                ))}
                <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                  <button type="button" className="rc__link-btn" onClick={() => setEditing(r)} title="Chỉnh sửa">
                    <EditIcon />
                    <span>Sửa</span>
                  </button>
                  <button type="button" className="rc__link-btn rc__link-btn--danger" onClick={() => remove(r)} title="Xóa">
                    <TrashIcon2 />
                    <span>Xóa</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <CatalogDrawer config={config} existing={editing === "new" ? null : editing}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </main>
  );
}

// ── UTILITY: PARSE UNIT SUFFIX FROM LABEL ─────────────────────────────────────────
function parseLabelAndSuffix(label: string): { cleanLabel: string; suffix: string | null } {
  const parenMatch = label.match(/\s*\(([^)]+)\)\s*$/);
  if (parenMatch) {
    return { cleanLabel: label.replace(parenMatch[0], "").trim(), suffix: parenMatch[1] };
  }
  const percentMatch = label.match(/\s*%\s*$/);
  if (percentMatch) {
    return { cleanLabel: label.replace(percentMatch[0], "").trim(), suffix: "%" };
  }
  return { cleanLabel: label, suffix: null };
}

// ── INLINE SVG ICONS ─────────────────────────────────────────────────────────────
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="rc__search-icon">
    <circle cx="11" cy="11" r="8"/>
    <path d="m21 21-4.3-4.3"/>
  </svg>
);

const EditIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
  </svg>
);

const TrashIcon2 = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
  </svg>
);

const ArrowUpIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="m18 15-6-6-6 6"/>
  </svg>
);

const ArrowDownIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="m6 9 6 6 6-6"/>
  </svg>
);

const TrashIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
  </svg>
);

// ── DRAWER COMPONENT ─────────────────────────────────────────────────────────────
function CatalogDrawer({ config, existing, onClose, onSaved }: {
  config: CatalogConfig; existing: Row | null; onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const isEdit = existing != null;
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = { ma: existing?.ma ?? "", ten: existing?.ten ?? "" };
    for (const f of config.fields) {
      if (f.type === "ref-multi") {
        const ev = existing?.[f.key];
        init[f.key] = Array.isArray(ev) ? ev : [];
      } else {
        init[f.key] = existing ? existing[f.key] ?? "" : "";
      }
    }
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));

  // Đổ dropdown "chọn theo tên" cho field ref/ref-multi từ danh mục nguồn.
  const [refData, setRefData] = useState<Record<string, Row[]>>({});
  useEffect(() => {
    if (!token) return;
    const prefixes = [...new Set(
      config.fields.filter((f) => f.type === "ref" || f.type === "ref-multi").map((f) => f.refPrefix).filter(Boolean) as string[],
    )];
    if (prefixes.length === 0) return;
    let alive = true;
    Promise.all(prefixes.map((p) => crud(p).list(token).then((r) => [p, r.items] as const).catch(() => [p, [] as Row[]] as const)))
      .then((entries) => { if (alive) setRefData(Object.fromEntries(entries)); });
    return () => { alive = false; };
  }, [token, config.fields]);

  // Field hiển thị theo điều kiện
  const visibleFields = useMemo(
    () => config.fields.filter((f) => !f.showIf || f.showIf(form)),
    [config.fields, form],
  );

  // Nhóm field theo `group`
  const groups = useMemo(() => {
    const order: string[] = [];
    const map = new Map<string, FieldDef[]>();
    for (const f of visibleFields) {
      const g = f.group ?? "Thông số";
      if (!map.has(g)) { map.set(g, []); order.push(g); }
      map.get(g)!.push(f);
    }
    return order.map((g) => ({ name: g, fields: map.get(g)! }));
  }, [visibleFields]);

  // Quản lý Tab hoạt động trong Form Drawer
  const [activeTab, setActiveTab] = useState<string>("");
  useEffect(() => {
    if (groups.length > 0) {
      const names = groups.map((g) => g.name);
      if (!names.includes(activeTab)) {
        setActiveTab(names[0]);
      }
    }
  }, [groups, activeTab]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true); setErr(null);
    const body: Record<string, unknown> = { ma: form.ma, ten: form.ten };
    for (const f of visibleFields) {
      let v = form[f.key];
      if (f.type === "ref-multi") { body[f.key] = Array.isArray(v) ? v : []; continue; }
      if (v === "" || v === undefined) { if (!f.required) continue; }
      if ((f.type === "number" || f.type === "ref") && v !== "" && v != null) v = Number(v);
      if (f.type === "json" && typeof v === "string" && v.trim()) {
        try { v = JSON.parse(v); } catch { setErr(`${f.label}: JSON không hợp lệ.`); setSaving(false); return; }
      }
      body[f.key] = v;
    }
    try {
      if (isEdit && existing) await api.update(token, existing.id, body);
      else await api.create(token, body);
      onSaved();
    } catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "Lưu thất bại."); setSaving(false); }
  }

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">{isEdit ? "Chỉnh sửa" : "Thêm mới"}</div>
            <h2 className="rc-drawer__title">{isEdit ? String(existing?.ten) : config.title}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">✕</button>
        </header>

        <form className="rc-drawer__body" onSubmit={submit}>
          {err && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{err}</div>}
          
          <section className="rc-sec rc-sec--ident">
            <div className="rc-grid">
              <label className="rc-field">
                <span className="rc-field__label">Mã <em>*</em></span>
                <div className={`rc-input-wrapper${isEdit ? " rc-input-wrapper--ro" : ""}`}>
                  <input className="rc-input rc-mono" value={String(form.ma ?? "")}
                    disabled={isEdit} onChange={(e) => set("ma", e.target.value)} required placeholder="VD: OFF-74-4C" />
                </div>
                {isEdit && <span className="rc-field__hint">Mã không đổi sau khi tạo.</span>}
              </label>
              <label className="rc-field">
                <span className="rc-field__label">Tên <em>*</em></span>
                <div className="rc-input-wrapper">
                  <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
                </div>
              </label>
            </div>
          </section>

          {groups.length > 1 && (
            <div className="rc-drawer__tabs">
              {groups.map((g) => (
                <button
                  key={g.name}
                  type="button"
                  className={`rc-drawer__tab${activeTab === g.name ? " is-active" : ""}`}
                  onClick={() => setActiveTab(g.name)}
                >
                  {g.name}
                </button>
              ))}
            </div>
          )}

          <div className="rc-drawer__fields-container">
            {groups
              .filter((g) => groups.length <= 1 || g.name === activeTab)
              .map((g) => (
                <section className="rc-sec" key={g.name}>
                  {groups.length <= 1 && <div className="rc-sec__title">{g.name}</div>}
                  <div className="rc-grid">
                    {g.fields.map((f) => {
                      const { cleanLabel, suffix } = parseLabelAndSuffix(f.label);
                      return (
                        <label className={`rc-field${f.type === "checkbox" ? " rc-field--check" : ""}`} key={f.key}>
                          <span className="rc-field__label">{cleanLabel}{f.required ? " *" : ""}</span>
                          {f.type === "select" ? (
                            <div className="rc-input-wrapper">
                              <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
                                <option value="">—</option>
                                {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                              </select>
                            </div>
                          ) : f.type === "ref" ? (
                            <div className="rc-input-wrapper">
                              <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
                                <option value="">— chọn —</option>
                                {(refData[f.refPrefix ?? ""] ?? []).map((o) => (
                                  <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>
                                ))}
                              </select>
                            </div>
                          ) : f.type === "ref-multi" ? (
                            <RefMultiField
                              value={Array.isArray(form[f.key]) ? (form[f.key] as number[]) : []}
                              options={refData[f.refPrefix ?? ""] ?? []}
                              onChange={(v) => set(f.key, v)}
                            />
                          ) : f.type === "checkbox" ? (
                            <label className="rc-switch">
                              <input type="checkbox" checked={!!form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />
                              <span className="rc-switch__slider" />
                              <span className="rc-switch__label">{form[f.key] ? "Có" : "Không"}</span>
                            </label>
                          ) : f.type === "json" ? (
                            <div className="rc-input-wrapper">
                              <input className="rc-input rc-mono" placeholder='[1,2] hoặc {"k":1}'
                                value={typeof form[f.key] === "string" ? String(form[f.key]) : JSON.stringify(form[f.key] ?? "")}
                                onChange={(e) => set(f.key, e.target.value)} />
                            </div>
                          ) : (
                            <div className="rc-input-wrapper">
                              <input className={`rc-input${f.type === "number" ? " rc-input--num" : ""}`}
                                type={f.type === "number" ? "number" : "text"} step="any" inputMode={f.type === "number" ? "decimal" : undefined}
                                placeholder={f.type === "number" ? "0" : (f.hint ?? "")}
                                value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
                              {suffix && <span className="rc-input-suffix">{suffix}</span>}
                            </div>
                          )}
                          {f.hint && <span className="rc-field__hint">{f.hint}</span>}
                        </label>
                      );
                    })}
                  </div>
                </section>
              ))}
          </div>
        </form>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
          <Button type="button" variant="primary" loading={saving} onClick={() => submit(new Event("submit") as unknown as FormEvent)}>
            {isEdit ? "Lưu thay đổi" : "Tạo mới"}
          </Button>
        </footer>
      </aside>
    </div>
  );
}

// ── TIMELINE MULTI-PICKER ────────────────────────────────────────────────────────
function RefMultiField({ value, options, onChange }: {
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
