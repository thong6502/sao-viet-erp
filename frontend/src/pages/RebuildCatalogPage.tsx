// Trang danh mục GENERIC (rebuild) — list + drawer form theo SECTION + search + filter tab.
// 1 component cho 6 module (Máy · Vật liệu · Công đoạn · Loại SP) qua `config`. On-brand với
// design system app (tokens rust/ink/paper). Form lean nhưng có nhóm; đủ theo spec là follow-up.
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ApiError } from "../api/client";
import { crud, giayVersions, addGiayVersion, type GiayGiaVersion, type Row } from "../api/rebuildCatalog";
import "./rebuild-catalog.css";

export interface FieldDef {
  key: string;
  label: string;
  type?: "text" | "number" | "select" | "checkbox" | "json" | "ref" | "ref-multi" | "ref-search" | "bands" | "size_tiers" | "suggest";
  options?: { value: string; label: string }[];
  refPrefix?: string;           // ref / ref-multi / ref-search: endpoint danh mục nguồn (đổ theo TÊN/MÃ)
  required?: boolean;
  hint?: string;
  group?: string;               // nhóm section trong drawer
  showIf?: (form: Record<string, unknown>) => boolean;  // ẩn/hiện field theo giá trị khác
  default?: unknown;            // prefill khi TẠO MỚI (giá trị thật, không phải placeholder "0")
  jsonKey?: string;             // field lưu LỒNG trong cột JSON này (vd "fields_theo_loai")
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
  renderExtra?: (form: Record<string, unknown>) => ReactNode;  // block phụ cuối drawer (vd preview BHR)
  hasVersions?: boolean;        // bật lịch sử giá (Giấy): thêm cột "Phiên bản" bấm mở lịch sử
  softDelete?: boolean;         // "Xóa" = ẩn mềm (active=false), giữ dữ liệu; list chỉ hiện active
  deriveInitial?: (existing: Row | null) => Record<string, unknown>;  // giá trị UI suy ra khi mở form (vd _method)
  transformSubmit?: (body: Record<string, unknown>, form: Record<string, unknown>) => Record<string, unknown>;  // map field UI → body API trước khi gửi
}

export function RebuildCatalogPage({ config }: { config: CatalogConfig }) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Row | "new" | null>(null);
  const [pricingRow, setPricingRow] = useState<Row | null>(null);  // hasVersions: mở drawer Lịch sử giá
  const [q, setQ] = useState("");
  const [facet, setFacet] = useState("all");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.list(token, config.softDelete ? { active: true } : {})   // xóa mềm: chỉ hiện dòng còn active
      .then((r) => setRows(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
  }, [token, api, config.softDelete]);
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
    if (!token) return;
    if (config.softDelete) {
      if (!window.confirm(`Ẩn "${r.ten}" (${r.ma})? Dữ liệu vẫn giữ (xóa mềm), có thể khôi phục sau.`)) return;
      try { await api.update(token, r.id, { ...r, active: false }); load(); }
      catch (e) { setError(e instanceof ApiError ? e.message : "Không ẩn được."); }
    } else {
      if (!window.confirm(`Xóa "${r.ten}" (${r.ma})?`)) return;
      try { await api.remove(token, r.id); load(); }
      catch (e) { setError(e instanceof ApiError ? e.message : "Không xóa được."); }
    }
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
          <PlusIcon /> Thêm {config.title.toLowerCase()}
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
              {config.columns.map((c) => {
                const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                return <th key={c.key} className={isCenter ? "text-center" : ""}>{c.label}</th>;
              })}
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
                      <Button variant="ghost" onClick={() => setEditing("new")}><PlusIcon /> Tạo {config.title.toLowerCase()}</Button>
                    ) : (
                      <Button variant="ghost" onClick={() => { setQ(""); setFacet("all"); }}>Xóa bộ lọc</Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : shown.map((r) => {
              const noWrapKeys = ["ma", "dai", "bac", "active", "version_no", "gsm", "kho", "don_vi_gia", "don_gia", "kho_max", "so_to_bu_hao"];
              return (
                <tr key={r.id} className="rc__row" onClick={() => setEditing(r)}>
                  <td className="rc__mono rc__nowrap"><span className="rc__code-badge">{String(r.ma)}</span></td>
                  <td className="rc__name">{String(r.ten)}</td>
                  {config.columns.map((c) => {
                    const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                    const classes = [
                      isCenter ? "text-center" : "",
                      noWrapKeys.includes(c.key) ? "rc__nowrap" : ""
                    ].filter(Boolean).join(" ");
                    return (
                      <td key={c.key} className={classes || undefined}>
                        {c.render ? c.render(r) : (r[c.key] == null || r[c.key] === "" ? "—" : String(r[c.key]))}
                      </td>
                    );
                  })}
                  <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                    <button type="button" className="rc__link-btn" onClick={() => setEditing(r)} title="Chỉnh sửa">
                      <EditIcon />
                      <span>Sửa</span>
                    </button>
                    {config.hasVersions && (
                      <button type="button" className="rc__link-btn" onClick={() => setPricingRow(r)} title="Lịch sử giá / nhập đơn giá">
                        <TagIcon />
                        <span>Giá</span>
                      </button>
                    )}
                    <button type="button" className="rc__link-btn rc__link-btn--danger" onClick={() => remove(r)} title="Xóa">
                      <TrashIcon2 />
                      <span>Xóa</span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editing && (
        <CatalogDrawer config={config} existing={editing === "new" ? null : editing} allRows={rows}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}

      {pricingRow && (
        <PriceHistoryDrawer row={pricingRow}
          onClose={() => setPricingRow(null)}
          onSaved={() => { setPricingRow(null); load(); }} />
      )}
    </main>
  );
}

// ── PRICE HISTORY DRAWER (Lịch sử giá Giấy — xem phiên bản + thêm đơn giá mới) ────
function PriceHistoryDrawer({ row, onClose, onSaved }: {
  row: Row; onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const [versions, setVersions] = useState<GiayGiaVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const numOf = (v: unknown) => Number(v) || 0;
  const [form, setForm] = useState({
    don_gia: "",
    don_vi_gia: String(row.don_vi_gia ?? "kg"),
    ngay_hieu_luc: "",
    ghi_chu: "",
  });
  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }));

  const reload = useCallback(() => {
    if (!token) return;
    setLoading(true);
    giayVersions(token, row.id)
      .then((v) => setVersions(v))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được lịch sử giá."))
      .finally(() => setLoading(false));
  }, [token, row.id]);
  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (!token) return;
    const dg = Number(form.don_gia);
    if (!(dg >= 0) || form.don_gia === "") { setErr("Nhập đơn giá hợp lệ."); return; }
    setSaving(true); setErr(null);
    try {
      // Ảnh chụp: giữ nguyên gsm/khổ hiện hành của giấy, chỉ đổi đơn giá + ĐVT + ngày + lý do.
      await addGiayVersion(token, row.id, {
        gsm: numOf(row.gsm),
        kho_dai: numOf(row.kho_dai),
        kho_rong: numOf(row.kho_rong),
        don_vi_gia: form.don_vi_gia,
        don_gia: dg,
        gia_thi_truong: row.gia_thi_truong != null ? numOf(row.gia_thi_truong) : null,
        ngay_hieu_luc: form.ngay_hieu_luc || null,
        ghi_chu: form.ghi_chu.trim() || null,
      });
      setForm((p) => ({ ...p, don_gia: "", ghi_chu: "" }));
      reload();
      onSaved();  // reload danh sách chính để cột Giá (don_gia mirror) cập nhật
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Lưu đơn giá thất bại.");
    } finally { setSaving(false); }
  }

  const DVT: Record<string, string> = { kg: "KG", cai: "CÁI", ram: "Ram", to: "Tờ", tan: "Tấn" };
  const vnd = (v: unknown) => (v == null ? "—" : Number(v).toLocaleString("vi-VN"));

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">Lịch sử giá</div>
            <h2 className="rc-drawer__title">{String(row.ma)} · {String(row.ten)}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="rc-drawer__body">
          {err && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{err}</div>}

          <section className="rc-sec">
            <div className="rc-sec__title">Thêm đơn giá mới</div>
            <div className="rc-grid">
              <label className="rc-field">
                <span className="rc-field__label">Đơn giá *</span>
                <div className="rc-input-wrapper">
                  <input className="rc-input rc-input--num" type="number" step="any" inputMode="decimal"
                    value={form.don_gia} placeholder="0" onChange={(e) => set("don_gia", e.target.value)} />
                </div>
              </label>
              <label className="rc-field">
                <span className="rc-field__label">ĐVT</span>
                <div className="rc-input-wrapper">
                  <select className="rc-input" value={form.don_vi_gia} onChange={(e) => set("don_vi_gia", e.target.value)}>
                    {Object.entries(DVT).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              </label>
              <label className="rc-field">
                <span className="rc-field__label">Ngày hiệu lực</span>
                <div className="rc-input-wrapper">
                  <input className="rc-input" type="date" value={form.ngay_hieu_luc} onChange={(e) => set("ngay_hieu_luc", e.target.value)} />
                </div>
              </label>
              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Lý do đổi giá</span>
                <div className="rc-input-wrapper">
                  <input className="rc-input" type="text" value={form.ghi_chu} placeholder="vd: NCC tăng giá"
                    onChange={(e) => set("ghi_chu", e.target.value)} />
                </div>
              </label>
            </div>
            <div style={{ marginTop: "var(--sp-3)" }}>
              <Button type="button" variant="primary" loading={saving} onClick={submit}>Lưu đơn giá</Button>
            </div>
            <span className="rc-field__hint">Giữ nguyên định lượng {vnd(row.gsm)}g · khổ {vnd(row.kho_rong)}×{vnd(row.kho_dai)} hiện hành; tạo phiên bản mới và cập nhật giá đang dùng.</span>
          </section>

          <section className="rc-sec">
            <div className="rc-sec__title">Các phiên bản giá</div>
            {loading ? (
              <div className="rc__msg">Đang tải…</div>
            ) : versions.length === 0 ? (
              <div className="rc-bands__empty">Chưa có phiên bản giá.</div>
            ) : (
              <div className="rc__tablewrap">
                <table className="rc__table">
                  <thead>
                    <tr>
                      <th>#</th><th className="text-center">Hiện dùng</th>
                      <th className="rc__nowrap">Đơn giá</th><th>ĐVT</th>
                      <th className="rc__nowrap">Hiệu lực</th><th>Lý do</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr key={v.id} className="rc__row">
                        <td className="rc__mono">{v.version_no}</td>
                        <td className="text-center">{v.is_current ? "✓" : ""}</td>
                        <td className="rc__nowrap">{vnd(v.don_gia)}</td>
                        <td>{DVT[v.don_vi_gia] ?? v.don_vi_gia}</td>
                        <td className="rc__nowrap">{v.ngay_hieu_luc ?? "—"}</td>
                        <td>{v.ghi_chu ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onClose}>Đóng</Button>
        </footer>
      </aside>
    </div>
  );
}

const TagIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82Z" />
    <circle cx="7" cy="7" r="1.2" />
  </svg>
);

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

// ── UTILITY: SUGGEST NEXT SEQUENTIAL CODE ─────────────────────────────────────────
function suggestNextCode(prefix: string, rows: Row[]): string {
  let codePrefix = "MA-";
  if (prefix.includes("loai-san-pham")) codePrefix = "LSP-";
  else if (prefix.includes("may-thiet-bi")) codePrefix = "TB-";
  else if (prefix.includes("cong-doan")) codePrefix = "CD-";
  else if (prefix.includes("giay")) codePrefix = "GL-";
  else if (prefix.includes("muc")) codePrefix = "MUC-";
  else if (prefix.includes("ban-kem")) codePrefix = "KEM-";
  else if (prefix.includes("quy-tac-binh-bai")) codePrefix = "BB-";

  const numRegex = new RegExp(`^${codePrefix}(\\d+)$`);
  let maxNum = 0;
  for (const r of rows) {
    const m = String(r.ma).trim().toUpperCase().match(numRegex);
    if (m) {
      const val = parseInt(m[1], 10);
      if (val > maxNum) maxNum = val;
    }
  }
  return `${codePrefix}${String(maxNum + 1).padStart(4, "0")}`;
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

const PlusIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "4px" }}>
    <path d="M5 12h14M12 5v14"/>
  </svg>
);

// ── CUSTOM SUGGEST COMPONENT (Dropdown + Text input toggle) ──────────────────────────
function SuggestField({
  value,
  options,
  allRows,
  fieldKey,
  placeholder,
  onChange
}: {
  value: string;
  options?: { value: string; label: string }[];
  allRows: Row[];
  fieldKey: string;
  placeholder?: string;
  onChange: (v: string) => void;
}) {
  const suggestions = useMemo(() => {
    const set = new Set<string>();
    options?.forEach((o) => set.add(o.value));
    allRows.forEach((r) => {
      const val = String(r[fieldKey] || "").trim();
      if (val) set.add(val);
    });
    return Array.from(set);
  }, [options, allRows, fieldKey]);

  const isCustomVal = value !== "" && !suggestions.includes(value);
  const [isCustomMode, setIsCustomMode] = useState(isCustomVal);

  useEffect(() => {
    setIsCustomMode(isCustomVal);
  }, [value, isCustomVal]);

  if (isCustomMode) {
    return (
      <div className="rc-suggest-custom" style={{ display: "flex", gap: "var(--sp-2)", width: "100%" }}>
        <input
          className="rc-input"
          style={{ flex: 1 }}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`Nhập ${placeholder || "tên mới"}...`}
          autoFocus
        />
        <button
          type="button"
          className="btn btn--secondary"
          style={{
            padding: "0 var(--sp-3)",
            height: "36px",
            whiteSpace: "nowrap",
            fontSize: "13px",
            borderRadius: "var(--rd-md)",
            border: "1px solid var(--border-neutral)",
            backgroundColor: "var(--bg-card)",
            cursor: "pointer"
          }}
          onClick={() => {
            setIsCustomMode(false);
            onChange("");
          }}
        >
          Chọn từ danh sách
        </button>
      </div>
    );
  }

  return (
    <div className="rc-input-wrapper">
      <select
        className="rc-input"
        value={value}
        onChange={(e) => {
          const val = e.target.value;
          if (val === "_new_") {
            setIsCustomMode(true);
            onChange("");
          } else {
            onChange(val);
          }
        }}
      >
        <option value="">— Chọn {placeholder || "giá trị"} —</option>
        {suggestions.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
        <option value="_new_" style={{ fontWeight: "600", color: "var(--brand, #c2410c)" }}>
          + Thêm mới...
        </option>
      </select>
    </div>
  );
}

// ── BANDS EDITOR (bậc số lượng động: Từ SL · Đến SL · Giá trị · Đơn vị) ──────────
interface BacRow { sl_tu?: number | null; sl_den?: number | null; gia_tri?: number; don_vi?: string }
function BandsField({ value, onChange }: { value: BacRow[]; onChange: (v: BacRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<BacRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => {
    const lastRow = rows[rows.length - 1];
    const nextTu = lastRow && lastRow.sl_den != null ? lastRow.sl_den : 0;
    onChange([...rows, { sl_tu: nextTu, sl_den: null, gia_tri: 0, don_vi: lastRow?.don_vi ?? "to" }]);
  };
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const num = (v: unknown) => (v === "" || v == null ? "" : String(v));
  return (
    <div className="rc-bands">
      <table className="rc-bands__table">
        <thead>
          <tr><th>Từ SL</th><th>Đến SL</th><th>Giá trị</th><th>Đơn vị</th><th></th></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={5} className="rc-bands__empty">Chưa có bậc — bấm “＋ Thêm bậc”.</td></tr>
          )}
          {rows.map((r, i) => {
            const isRangeInvalid = r.sl_den !== null && r.sl_den !== undefined && (r.sl_tu ?? 0) >= r.sl_den;
            return (
              <tr key={i} className={isRangeInvalid ? "rc-bands__row--invalid" : ""}>
                <td>
                  <input
                    className={`rc-input rc-input--num${isRangeInvalid ? " rc-input--invalid" : ""}`}
                    type="number"
                    value={num(r.sl_tu)}
                    title={isRangeInvalid ? "Từ SL phải bé hơn Đến SL" : undefined}
                    onChange={(e) => setRow(i, { sl_tu: e.target.value === "" ? 0 : Number(e.target.value) })}
                  />
                </td>
                <td>
                  <input
                    className={`rc-input rc-input--num${isRangeInvalid ? " rc-input--invalid" : ""}`}
                    type="number"
                    placeholder="∞"
                    value={num(r.sl_den)}
                    title={isRangeInvalid ? "Từ SL phải bé hơn Đến SL" : undefined}
                    onChange={(e) => setRow(i, { sl_den: e.target.value === "" ? null : Number(e.target.value) })}
                  />
                </td>
                <td>
                  <input
                    className="rc-input rc-input--num"
                    type="number"
                    step="any"
                    value={num(r.gia_tri)}
                    onChange={(e) => setRow(i, { gia_tri: e.target.value === "" ? 0 : Number(e.target.value) })}
                  />
                </td>
                <td style={{ textAlign: "center" }}>
                  <div className="rc-bands__unit-toggle">
                    <button
                      type="button"
                      className={`rc-bands__unit-btn${(r.don_vi ?? "to") === "to" ? " is-active" : ""}`}
                      onClick={() => setRow(i, { don_vi: "to" })}
                    >
                      Tờ
                    </button>
                    <button
                      type="button"
                      className={`rc-bands__unit-btn${(r.don_vi ?? "to") === "pct" ? " is-active" : ""}`}
                      onClick={() => setRow(i, { don_vi: "pct" })}
                    >
                      %
                    </button>
                  </div>
                </td>
                <td style={{ textAlign: "center" }}>
                  <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xóa bậc">
                    <TrashIcon />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <button type="button" className="rc-bands__add" onClick={add}>＋ Thêm bậc</button>
    </div>
  );
}

// ── SIZE-TIER EDITOR (bậc đơn giá theo kích thước: Đến cỡ cm · Đơn giá đ) ─────────
interface SizeTierRow { den_cm?: number | null; don_gia?: number }
function SizeTiersField({ value, onChange }: { value: SizeTierRow[]; onChange: (v: SizeTierRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<SizeTierRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => {
    const last = rows[rows.length - 1];
    const nextCap = last && last.den_cm != null ? last.den_cm : 0;
    onChange([...rows, { den_cm: nextCap ? nextCap * 2 : 20, don_gia: 0 }]);
  };
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const num = (v: unknown) => (v === "" || v == null ? "" : String(v));
  return (
    <div className="rc-bands">
      <table className="rc-bands__table">
        <thead>
          <tr><th>Đến cỡ (cm)</th><th>Đơn giá (đ)</th><th></th></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={3} className="rc-bands__empty">Chưa có bậc — bấm “＋ Thêm bậc”. Cỡ = cạnh dài thành phẩm.</td></tr>
          )}
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <input className="rc-input rc-input--num" type="number" step="any" placeholder="∞ (trên các mức)"
                  value={num(r.den_cm)}
                  onChange={(e) => setRow(i, { den_cm: e.target.value === "" ? null : Number(e.target.value) })} />
              </td>
              <td>
                <input className="rc-input rc-input--num" type="number" step="any"
                  value={num(r.don_gia)}
                  onChange={(e) => setRow(i, { don_gia: e.target.value === "" ? 0 : Number(e.target.value) })} />
              </td>
              <td style={{ textAlign: "center" }}>
                <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xóa bậc">
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="rc-bands__add" onClick={add}>＋ Thêm bậc</button>
    </div>
  );
}

// ── DRAWER COMPONENT ─────────────────────────────────────────────────────────────
function CatalogDrawer({ config, existing, allRows, onClose, onSaved }: {
  config: CatalogConfig; existing: Row | null; allRows: Row[]; onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const isEdit = existing != null;
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {
      ma: existing?.ma ?? suggestNextCode(config.prefix, allRows),
      ten: existing?.ten ?? ""
    };
    for (const f of config.fields) {
      if (f.type === "ref-multi" || f.type === "bands" || f.type === "size_tiers") {
        const ev = existing?.[f.key];
        init[f.key] = Array.isArray(ev) ? ev : [];
      } else if (f.jsonKey) {
        // field lồng trong cột JSON (vd fields_theo_loai.click_mau)
        const box = existing?.[f.jsonKey] as Record<string, unknown> | undefined;
        init[f.key] = existing ? box?.[f.key] ?? "" : f.default ?? "";
      } else {
        init[f.key] = existing ? existing[f.key] ?? "" : f.default ?? "";
      }
    }
    if (config.deriveInitial) Object.assign(init, config.deriveInitial(existing));  // vd suy _method từ pricing_basis
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
      config.fields.filter((f) => f.type === "ref" || f.type === "ref-multi" || f.type === "ref-search").map((f) => f.refPrefix).filter(Boolean) as string[],
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

  // Quản lý Tab hoạt động trong Form Drawer (chỉ chia tab khi danh mục phức tạp > 12 fields)
  const useTabs = config.fields.length > 12;
  const [activeTab, setActiveTab] = useState<string>("");
  useEffect(() => {
    if (useTabs && groups.length > 0) {
      const names = groups.map((g) => g.name);
      if (!names.includes(activeTab)) {
        setActiveTab(names[0]);
      }
    }
  }, [groups, activeTab, useTabs]);

  // Kiểm tra trùng mã (Live validation)
  const typedMa = String(form.ma ?? "").trim().toUpperCase();
  const isMaDuplicate = useMemo(() => {
    if (isEdit || !typedMa) return false;
    return allRows.some((r) => String(r.ma).trim().toUpperCase() === typedMa);
  }, [isEdit, typedMa, allRows]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || isMaDuplicate) return;
    setSaving(true); setErr(null);
    const body: Record<string, unknown> = { ma: form.ma, ten: form.ten };
    for (const f of visibleFields) {
      let v = form[f.key];
      if (f.type === "ref-multi" || f.type === "bands" || f.type === "size_tiers") { body[f.key] = Array.isArray(v) ? v : []; continue; }
      if (v === "" || v === undefined) { if (!f.required) continue; }
      if ((f.type === "number" || f.type === "ref" || f.type === "ref-search") && v !== "" && v != null) v = Number(v);
      if (f.type === "json" && typeof v === "string" && v.trim()) {
        try { v = JSON.parse(v); } catch { setErr(`${f.label}: JSON không hợp lệ.`); setSaving(false); return; }
      }
      if (f.jsonKey) {
        // gom vào cột JSON, GIỮ key lạ đã có (vd seed đặt thêm) — không ghi đè cả object
        const box = (body[f.jsonKey] as Record<string, unknown>) ??
          { ...((existing?.[f.jsonKey] as Record<string, unknown>) ?? {}) };
        box[f.key] = v;
        body[f.jsonKey] = box;
        continue;
      }
      body[f.key] = v;
    }
    const finalBody = config.transformSubmit ? config.transformSubmit(body, form) : body;
    try {
      if (isEdit && existing) {
        await api.update(token, existing.id, finalBody);
      } else {
        await api.create(token, finalBody);
      }
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
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <form className="rc-drawer__body" onSubmit={submit}>
          {err && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{err}</div>}
          
          <section className="rc-sec rc-sec--ident">
            <div className="rc-grid">
              <label className="rc-field">
                <span className="rc-field__label">Mã <em>*</em></span>
                <div className={`rc-input-wrapper${isEdit ? " rc-input-wrapper--ro" : ""}`}>
                  <input className="rc-input rc-mono" value={String(form.ma ?? "")}
                    disabled={isEdit} onChange={(e) => set("ma", e.target.value.toUpperCase())} required placeholder="Mã..." />
                </div>
                {!isEdit && typedMa && (
                  <span style={{ fontSize: "11px", fontWeight: "600", marginTop: "1px", color: isMaDuplicate ? "var(--signal, #8a1f1f)" : "var(--moss, #2f5d3a)" }}>
                    {isMaDuplicate ? "❌ Mã đã tồn tại!" : "✅ Mã hợp lệ!"}
                  </span>
                )}
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

          {useTabs && groups.length > 1 && (
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
              .filter((g) => !useTabs || groups.length <= 1 || g.name === activeTab)
              .map((g) => (
                <section className="rc-sec" key={g.name}>
                  {(!useTabs || groups.length <= 1) && <div className="rc-sec__title">{g.name}</div>}
                  <div className="rc-grid">
                    {g.fields.map((f) => {
                      const { cleanLabel, suffix } = parseLabelAndSuffix(f.label);
                      const isFullWidth = f.type === "bands" || f.type === "size_tiers" || f.type === "ref-multi" || f.type === "json" || f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta";
                      return (
                        <label className={`rc-field${f.type === "checkbox" ? " rc-field--check" : ""}${isFullWidth ? " rc-field--full" : ""}`} key={f.key}>
                          <span className="rc-field__label">{cleanLabel}{f.required ? " *" : ""}</span>
                          {f.type === "bands" ? (
                            <BandsField value={Array.isArray(form[f.key]) ? (form[f.key] as BacRow[]) : []}
                              onChange={(v) => set(f.key, v)} />
                          ) : f.type === "size_tiers" ? (
                            <SizeTiersField value={Array.isArray(form[f.key]) ? (form[f.key] as SizeTierRow[]) : []}
                              onChange={(v) => set(f.key, v)} />
                          ) : f.type === "select" ? (
                            <div className="rc-input-wrapper">
                              <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
                                <option value="">—</option>
                                {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                              </select>
                            </div>
                          ) : f.type === "suggest" ? (
                            <SuggestField
                              value={String(form[f.key] ?? "")}
                              options={f.options}
                              allRows={allRows}
                              fieldKey={f.key}
                              placeholder={cleanLabel}
                              onChange={(v) => set(f.key, v)}
                            />
                          ) : f.type === "ref" ? (
                            <div className="rc-input-wrapper">
                              <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
                                <option value="">— chọn —</option>
                                {(refData[f.refPrefix ?? ""] ?? []).map((o) => (
                                  <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>
                                ))}
                              </select>
                            </div>
                          ) : f.type === "ref-search" ? (
                            <RefSearchField
                              value={form[f.key] == null || form[f.key] === "" ? null : Number(form[f.key])}
                              options={refData[f.refPrefix ?? ""] ?? []}
                              placeholder={f.hint ?? "Gõ mã / tên để tìm…"}
                              onChange={(v) => set(f.key, v)}
                            />
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
                                placeholder={f.type === "number" ? (f.default != null ? String(f.default) : "0") : (f.hint ?? "")}
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

          {config.renderExtra?.(form)}
        </form>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
          <Button type="button" variant="primary" loading={saving} disabled={isMaDuplicate || (!isEdit && !typedMa)} onClick={() => submit(new Event("submit") as unknown as FormEvent)}>
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

// Ô tìm-chọn 1 danh mục theo MÃ (typeahead, bỏ dấu vẫn khớp) — vd chọn bù hao cho công đoạn.
function RefSearchField({ value, options, placeholder, onChange }: {
  value: number | null; options: Row[]; placeholder?: string; onChange: (v: number | null) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const norm = (s: string) =>
    s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
  const selected = value == null ? null : options.find((o) => o.id === value) ?? null;
  const nq = norm(q.trim());
  const matches = (nq
    ? options.filter((o) => norm(`${o.ma} ${o.ten}`).includes(nq))
    : options
  ).slice(0, 20);

  if (selected) {
    return (
      <div className="rc-input-wrapper" style={{ display: "flex", gap: "6px", alignItems: "stretch" }}>
        <span className="rc-input" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span><b style={{ fontFamily: "var(--ff-mono, monospace)" }}>{selected.ma}</b> · {selected.ten}</span>
          <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" title="Bỏ chọn — tìm lại"
            onClick={() => { onChange(null); setQ(""); setOpen(true); }}>✕</button>
        </span>
      </div>
    );
  }
  const panel: CSSProperties = {
    position: "absolute", top: "100%", left: 0, right: 0, zIndex: 30, marginTop: "2px",
    background: "var(--rc-surface, #fffdf7)", border: "1px solid rgba(0,0,0,0.15)",
    borderRadius: "8px", maxHeight: "240px", overflowY: "auto", boxShadow: "0 8px 24px rgba(0,0,0,0.14)",
  };
  return (
    <div className="rc-input-wrapper" style={{ position: "relative" }}>
      <input className="rc-input" value={q} placeholder={placeholder ?? "Gõ mã / tên để tìm…"}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && matches.length > 0 && (
        <div style={panel}>
          {matches.map((o) => (
            <button type="button" key={o.id}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px",
                background: "transparent", border: "none", cursor: "pointer" }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => { onChange(o.id); setQ(""); setOpen(false); }}>
              <b style={{ fontFamily: "var(--ff-mono, monospace)" }}>{o.ma}</b> · {o.ten}
            </button>
          ))}
        </div>
      )}
      {open && nq && matches.length === 0 && (
        <div style={{ ...panel, padding: "8px 10px", color: "var(--ash, #8a8577)" }}>
          Không thấy mã/tên khớp “{q}”.
        </div>
      )}
    </div>
  );
}
