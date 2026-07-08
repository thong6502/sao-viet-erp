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
  type?: "text" | "number" | "select" | "checkbox" | "json";
  options?: { value: string; label: string }[];
  required?: boolean;
  hint?: string;
  group?: string;               // nhóm section trong drawer
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
        <input className="rc__search" placeholder="Tìm mã / tên…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="rc__spacer" />
        <Button variant="primary" onClick={() => setEditing("new")}>+ Thêm {config.title.toLowerCase()}</Button>
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
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={() => { setError(null); load(); }}>Tải lại</button>
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th>Mã</th><th>Tên</th>
              {config.columns.map((c) => <th key={c.key}>{c.label}</th>)}
              <th className="rc__actcol"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={config.columns.length + 3} className="rc__msg">Đang tải…</td></tr>
            ) : shown.length === 0 ? (
              <tr><td colSpan={config.columns.length + 3} className="rc__msg">
                {rows.length === 0 ? `Chưa có ${config.title.toLowerCase()} nào — bấm “Thêm” để tạo.` : "Không khớp bộ lọc."}
              </td></tr>
            ) : shown.map((r) => (
              <tr key={r.id} className="rc__row" onClick={() => setEditing(r)}>
                <td className="rc__mono">{String(r.ma)}</td>
                <td className="rc__name">{String(r.ten)}</td>
                {config.columns.map((c) => (
                  <td key={c.key}>{c.render ? c.render(r) : (r[c.key] == null || r[c.key] === "" ? "—" : String(r[c.key]))}</td>
                ))}
                <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                  <button type="button" className="rc__link" onClick={() => setEditing(r)}>Sửa</button>
                  <button type="button" className="rc__link rc__link--danger" onClick={() => remove(r)}>Xóa</button>
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

function CatalogDrawer({ config, existing, onClose, onSaved }: {
  config: CatalogConfig; existing: Row | null; onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const isEdit = existing != null;
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = { ma: existing?.ma ?? "", ten: existing?.ten ?? "" };
    for (const f of config.fields) init[f.key] = existing ? existing[f.key] ?? "" : "";
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));

  // Nhóm field theo `group` (giữ thứ tự xuất hiện).
  const groups = useMemo(() => {
    const order: string[] = [];
    const map = new Map<string, FieldDef[]>();
    for (const f of config.fields) {
      const g = f.group ?? "Thông số";
      if (!map.has(g)) { map.set(g, []); order.push(g); }
      map.get(g)!.push(f);
    }
    return order.map((g) => ({ name: g, fields: map.get(g)! }));
  }, [config.fields]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true); setErr(null);
    const body: Record<string, unknown> = { ma: form.ma, ten: form.ten };
    for (const f of config.fields) {
      let v = form[f.key];
      if (v === "" || v === undefined) { if (!f.required) continue; }
      if (f.type === "number" && v !== "" && v != null) v = Number(v);
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
          {err && <div className="banner banner--error">{err}</div>}
          <section className="rc-sec">
            <div className="rc-sec__title">Định danh</div>
            <div className="rc-grid">
              <label className="rc-field">
                <span className="rc-field__label">Mã <em>*</em></span>
                <input className="rc-input rc-mono" value={String(form.ma ?? "")} disabled={isEdit}
                  onChange={(e) => set("ma", e.target.value)} required placeholder="VD: OFF-74-4C" />
              </label>
              <label className="rc-field">
                <span className="rc-field__label">Tên <em>*</em></span>
                <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
              </label>
            </div>
          </section>

          {groups.map((g) => (
            <section className="rc-sec" key={g.name}>
              <div className="rc-sec__title">{g.name}</div>
              <div className="rc-grid">
                {g.fields.map((f) => (
                  <label className={`rc-field${f.type === "checkbox" ? " rc-field--check" : ""}`} key={f.key}>
                    <span className="rc-field__label">{f.label}{f.required ? " *" : ""}</span>
                    {f.type === "select" ? (
                      <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
                        <option value="">—</option>
                        {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    ) : f.type === "checkbox" ? (
                      <span className="rc-check">
                        <input type="checkbox" checked={!!form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />
                        <span>{form[f.key] ? "Có" : "Không"}</span>
                      </span>
                    ) : f.type === "json" ? (
                      <input className="rc-input rc-mono" placeholder='[1,2] hoặc {"k":1}'
                        value={typeof form[f.key] === "string" ? String(form[f.key]) : JSON.stringify(form[f.key] ?? "")}
                        onChange={(e) => set(f.key, e.target.value)} />
                    ) : (
                      <input className="rc-input" type={f.type === "number" ? "number" : "text"} step="any"
                        value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
                    )}
                    {f.hint && <span className="rc-field__hint">{f.hint}</span>}
                  </label>
                ))}
              </div>
            </section>
          ))}
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
