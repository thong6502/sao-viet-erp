// Trang danh mục GENERIC (rebuild) — list + drawer form theo SECTION + search + filter tab.
// 1 component cho 6 module (Máy · Vật liệu · Công đoạn · Loại SP) qua `config`. On-brand với
// design system app (tokens rust/ink/paper). Form lean nhưng có nhóm; đủ theo spec là follow-up.
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ApiError } from "../api/client";
import { crud, giayVersions, addGiayVersion, type GiayGiaVersion, type Row } from "../api/rebuildCatalog";
import "./rebuild-catalog.css";

export interface FieldDef {
  key: string;
  label: string;
  type?: "text" | "number" | "date" | "select" | "checkbox" | "json" | "ref" | "ref-multi" | "ref-search" | "bands" | "size_tiers" | "suggest" | "formula";
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
  /** Field gõ TỰ DO (type "suggest"): sinh thêm tab cho giá trị có thật trong dữ liệu mà
   *  `values` chưa liệt kê — khai cứng sẽ bỏ sót nhóm người dùng tự đặt. */
  dynamic?: boolean;
}
export interface CatalogConfig {
  title: string;
  subtitle?: string;
  showCount?: boolean;
  prefix: string;
  columns: ColumnDef[];
  fields: FieldDef[];
  facet?: FacetDef;             // tab lọc phía trên (tùy chọn)
  // Block phụ cuối drawer (preview BHR của Máy · bảng quy đổi của Đơn vị). `existing` = null khi
  // đang TẠO — block nào cần id thì tự nhắc "lưu trước đã".
  renderExtra?: (form: Record<string, unknown>, existing: Row | null) => ReactNode;
  hasVersions?: boolean;        // bật lịch sử giá (Giấy): thêm cột "Phiên bản" bấm mở lịch sử
  softDelete?: boolean;         // "Xóa" = ẩn mềm (active=false), giữ dữ liệu; list chỉ hiện active
  autoCode?: boolean;           // mã sinh NGẦM ở backend → ẩn ô "Mã" lúc tạo, không gửi ma
  /** Tạo xong thì GIỮ drawer mở ở bản ghi vừa tạo. Dùng cho màn có khối con phải gắn vào id (vd
   *  Đơn vị: tạo "tấn" xong khai ngay quy đổi) — đóng phắt là bắt người ta đi tìm lại dòng. */
  moLaiSauKhiTao?: boolean;
  deriveInitial?: (existing: Row | null) => Record<string, unknown>;  // giá trị UI suy ra khi mở form (vd _method)
  transformSubmit?: (body: Record<string, unknown>, form: Record<string, unknown>) => Record<string, unknown>;  // map field UI → body API trước khi gửi
}

export function RebuildCatalogPage({ config, onMutate }: { config: CatalogConfig; onMutate?: () => void }) {
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

  // Tab lọc: giữ THỨ TỰ khai sẵn, nối thêm giá trị tự do có trong dữ liệu (facet.dynamic).
  const facetValues = useMemo(() => {
    const f = config.facet;
    if (!f) return [];
    if (!f.dynamic) return f.values;
    const known = new Set(f.values.map((v) => v.value));
    const extra = [...new Set(rows.map((r) => String(r[f.key] ?? "").trim()).filter(Boolean))]
      .filter((v) => !known.has(v))
      .sort((a, b) => a.localeCompare(b, "vi"));
    return [...f.values, ...extra.map((v) => ({ value: v, label: v }))];
  }, [config.facet, rows]);

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
      try { await api.update(token, r.id, { ...r, active: false }); load(); onMutate?.(); }
      catch (e) { setError(e instanceof ApiError ? e.message : "Không ẩn được."); }
    } else {
      if (!window.confirm(`Xóa "${r.ten}" (${r.ma})?`)) return;
      try { await api.remove(token, r.id); load(); onMutate?.(); }
      catch (e) { setError(e instanceof ApiError ? e.message : "Không xóa được."); }
    }
  }

  const facetCount = (v: string) =>
    config.facet ? rows.filter((r) => String(r[config.facet!.key] ?? "") === v).length : 0;

  return (
    <main className="rc">
      {config.subtitle ? (
        <>
          <header className="rc__head">
            <div className="rc__headrow">
              <h1 className="rc__title">{config.title}</h1>
              {config.showCount !== false && <span className="rc__count">{rows.length} mục</span>}
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
        </>
      ) : (
        <div className="rc__unified-bar">
          <div className="rc__headrow">
            <h1 className="rc__title">{config.title}</h1>
            {config.showCount !== false && <span className="rc__count">{rows.length} mục</span>}
          </div>
          <div className="rc__unified-right">
            <div className="rc__search-wrapper">
              <SearchIcon />
              <input className="rc__search" placeholder="Tìm mã / tên…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <Button variant="accent" onClick={() => setEditing("new")}>
              <PlusIcon /> Thêm {config.title.toLowerCase()}
            </Button>
          </div>
        </div>
      )}

      {config.facet && (
        <div className="rc__tabs">
          <button className={`rc__tab${facet === "all" ? " is-active" : ""}`} onClick={() => setFacet("all")}>
            Tất cả <span className="rc__tabn">{rows.length}</span>
          </button>
          {facetValues.map((v) => (
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
              <th style={{ width: "10%" }}>Mã</th>
              <th style={{ width: "20%" }}>Tên</th>
              {config.columns.map((c) => {
                const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                const w = c.key === "quy_doi_text" ? "45%" : c.key === "ghi_chu" ? "15%" : undefined;
                return <th key={c.key} style={w ? { width: w } : undefined} className={isCenter ? "text-center" : ""}>{c.label}</th>;
              })}
              <th className="rc__actcol" style={{ width: "10%" }}>Hành động</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Skeleton: 5 hàng ô shimmer thay cho dòng chữ "Đang tải…"
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  <td><span className="rc-skel" style={{ width: "60%" }} /></td>
                  <td><span className="rc-skel" style={{ width: "80%" }} /></td>
                  {config.columns.map((c) => (
                    <td key={c.key}><span className="rc-skel" style={{ width: "50%" }} /></td>
                  ))}
                  <td className="rc__actcol"><span className="rc-skel" style={{ width: "70px" }} /></td>
                </tr>
              ))
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
          onClose={() => { setEditing(null); load(); }}
          onSaved={(moi) => {
            setEditing(config.moLaiSauKhiTao && editing === "new" && moi ? moi : null);
            load();
            onMutate?.();
          }} />
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
  else if (prefix.endsWith("/kho")) codePrefix = "KHO-";
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

  // Giá trị lưu là MÃ (`khoi_luong`), nhãn người đọc nằm ở `options`. Không tra ngược thì dropdown
  // hiện mã trần — chủ mở ô "Nhóm đơn vị" ra thấy "khoi_luong" và không hiểu đang chọn cái gì.
  // Giá trị người dùng tự gõ (không có trong options) thì hiện nguyên văn, đó đã là chữ của họ.
  const nhan = useMemo(() => {
    const m = new Map<string, string>();
    options?.forEach((o) => m.set(o.value, o.label));
    return m;
  }, [options]);

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
            {nhan.get(s) ?? s}
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
  config: CatalogConfig; existing: Row | null; allRows: Row[];
  onClose: () => void; onSaved: (moi?: Row) => void;
}) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const isEdit = existing != null;
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {
      ma: existing?.ma ?? (config.autoCode ? "" : suggestNextCode(config.prefix, allRows)),
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

  const visibleFields = useMemo(
    () => config.fields.filter((f) => !f.showIf || f.showIf(form)),
    [config.fields, form],
  );

  const [formulaTab, setFormulaTab] = useState<"info" | "formula">("info");

  const renderField = (f: FieldDef) => {
    const { cleanLabel, suffix } = parseLabelAndSuffix(f.label);
    const isFullWidth = f.type === "bands" || f.type === "size_tiers" || f.type === "ref-multi" || f.type === "json" || f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta";
    const Tag = f.type === "formula" || f.type === "bands" || f.type === "size_tiers" ? "div" : "label";
    return (
      <Tag className={`rc-field${f.type === "checkbox" ? " rc-field--check" : ""}${isFullWidth ? " rc-field--full" : ""}`} key={f.key}>
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
        ) : f.type === "formula" ? (
          <FormulaField value={String(form[f.key] ?? "")} onChange={(v) => set(f.key, v)} configPrefix={config.prefix} />
        ) : f.type === "checkbox" ? (
          <label className="rc-switch">
            <input type="checkbox" checked={!!form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />
            <span className="rc-switch__slider" />
            <span className="rc-switch__label">{form[f.key] ? "Có" : "Không"}</span>
          </label>
        ) : f.type === "date" ? (
          <div className="rc-input-wrapper">
            <input className="rc-input" type="date"
              value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
          </div>
        ) : f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta" ? (
          <div className="rc-input-wrapper">
            <textarea className="rc-textarea" rows={2} value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} placeholder="Nhập ghi chú hoặc thông tin bổ sung..." />
          </div>
        ) : (
          <div className="rc-input-wrapper">
            <input className={`rc-input${f.type === "number" ? " rc-input--num" : ""}`}
              type={f.type === "number" ? "number" : "text"} step="any" inputMode={f.type === "number" ? "decimal" : undefined}
              value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
            {suffix && <span className="rc-input-suffix">{suffix}</span>}
          </div>
        )}
        {f.hint && <span className="rc-field__hint">{f.hint}</span>}
      </Tag>
    );
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || isMaDuplicate) return;
    setSaving(true); setErr(null);
    const body: Record<string, unknown> = { ten: form.ten };
    if (!config.autoCode || isEdit) body.ma = form.ma;
    for (const f of visibleFields) {
      let v = form[f.key];
      if (f.type === "ref-multi" || f.type === "bands" || f.type === "size_tiers") { body[f.key] = Array.isArray(v) ? v : []; continue; }
      if (v === "" || v === undefined) {
        const kieuChu = !f.type || f.type === "text" || f.type === "date" || f.type === "suggest";
        const voonCoGiaTri = isEdit && existing != null && existing[f.key] != null
          && existing[f.key] !== "";
        if (!f.required && !(kieuChu && voonCoGiaTri)) continue;
      }
      if ((f.type === "number" || f.type === "ref" || f.type === "ref-search") && v !== "" && v != null) v = Number(v);
      if (f.type === "json" && typeof v === "string" && v.trim()) {
        try { v = JSON.parse(v); } catch { setErr(`${f.label}: JSON không hợp lệ.`); setSaving(false); return; }
      }
      if (f.jsonKey) {
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
      const moi = isEdit && existing
        ? await api.update(token, existing.id, finalBody)
        : await api.create(token, finalBody);
      onSaved(moi);
    } catch (e2) { setErr(e2 instanceof ApiError ? e2.message : "Lưu thất bại."); setSaving(false); }
  }

  const typedMa = String(form.ma ?? "").trim().toUpperCase();
  const isMaDuplicate = useMemo(() => {
    if (isEdit || !typedMa) return false;
    return allRows.some((r) => String(r.ma).trim().toUpperCase() === typedMa);
  }, [isEdit, typedMa, allRows]);

  const hasFormulaField = useMemo(
    () => visibleFields.some((f) => f.type === "formula") || config.renderExtra != null,
    [visibleFields, config.renderExtra]
  );

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className={`rc-drawer${hasFormulaField ? " rc-drawer--formula" : ""}`} onClick={(e) => e.stopPropagation()}>
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
          
          {hasFormulaField ? (
            <div>
              <div className="rc-drawer__tabs" style={{ marginBottom: "var(--sp-4)" }}>
                <button
                  type="button"
                  className={`rc-drawer__tab${formulaTab === "info" ? " is-active" : ""}`}
                  onClick={() => setFormulaTab("info")}
                >
                  Khai báo thông tin
                </button>
                <button
                  type="button"
                  className={`rc-drawer__tab${formulaTab === "formula" ? " is-active" : ""}`}
                  onClick={() => setFormulaTab("formula")}
                >
                  {config.renderExtra ? "Công thức quy đổi" : "Công thức tính giá"}
                </button>
              </div>

              {formulaTab === "info" ? (
                <section className="rc-card-section" style={{ padding: "16px 20px" }}>
                  <div className="rc-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: "12px 16px" }}>
                    {!(config.autoCode && !isEdit) && (
                      <label className="rc-field">
                        <span className="rc-field__label">Mã <em>*</em></span>
                        <div className={`rc-input-wrapper${isEdit ? " rc-input-wrapper--ro" : ""}`}>
                          <input className="rc-input rc-mono" value={String(form.ma ?? "")}
                            disabled={isEdit} onChange={(e) => set("ma", e.target.value.toUpperCase())} required placeholder="Mã..." />
                        </div>
                        {!isEdit && typedMa && (
                          <span style={{ fontSize: "11px", fontWeight: "600", marginTop: "1px", color: isMaDuplicate ? "var(--signal, #8a1f1f)" : "var(--moss, #2f5d3a)" }}>
                            {isMaDuplicate ? "Mã đã tồn tại!" : "Mã hợp lệ!"}
                          </span>
                        )}
                      </label>
                    )}
                    <label className="rc-field">
                      <span className="rc-field__label">Tên <em>*</em></span>
                      <div className="rc-input-wrapper">
                        <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
                      </div>
                    </label>

                    {visibleFields
                      .filter((f) => f.type !== "formula")
                      .map(renderField)}
                  </div>
                </section>
              ) : (
                <div>
                  {visibleFields
                    .filter((f) => f.type === "formula")
                    .map(renderField)}
                  {config.renderExtra?.(form, existing)}
                </div>
              )}
            </div>
          ) : (
            <section className="rc-card-section" style={{ padding: "16px 20px" }}>
              <div className="rc-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: "12px 16px" }}>
                {!(config.autoCode && !isEdit) && (
                  <label className="rc-field">
                    <span className="rc-field__label">Mã <em>*</em></span>
                    <div className={`rc-input-wrapper${isEdit ? " rc-input-wrapper--ro" : ""}`}>
                      <input className="rc-input rc-mono" value={String(form.ma ?? "")}
                        disabled={isEdit} onChange={(e) => set("ma", e.target.value.toUpperCase())} required placeholder="Mã..." />
                    </div>
                    {!isEdit && typedMa && (
                      <span style={{ fontSize: "11px", fontWeight: "600", marginTop: "1px", color: isMaDuplicate ? "var(--signal, #8a1f1f)" : "var(--moss, #2f5d3a)" }}>
                        {isMaDuplicate ? "Mã đã tồn tại!" : "Mã hợp lệ!"}
                      </span>
                    )}
                  </label>
                )}
                <label className="rc-field">
                  <span className="rc-field__label">Tên <em>*</em></span>
                  <div className="rc-input-wrapper">
                    <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
                  </div>
                </label>

                {visibleFields
                  .filter((f) => f.type !== "formula")
                  .map(renderField)}
              </div>
            </section>
          )}
        </form>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
          <Button type="button" variant="primary" loading={saving} disabled={isMaDuplicate || (!isEdit && !config.autoCode && !typedMa)} onClick={() => submit(new Event("submit") as unknown as FormEvent)}>
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
          <span><b style={{ fontFamily: "var(--ff-num)" }}>{selected.ma}</b> · {selected.ten}</span>
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
              <b style={{ fontFamily: "var(--ff-num)" }}>{o.ma}</b> · {o.ten}
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

// ── FORMULA FIELD EDITOR AND VALIDATOR (Live math preview + click-to-insert variable tags) ──
// PALETTE gợi ý CHỈ 14 biến TỪ PHIẾU (kích thước + sản lượng). Đơn giá/định lượng KHÔNG làm chip —
// chúng kéo từ field của mục (ô "Đơn giá", ô "Định lượng"); nhưng vẫn GÕ được trong công thức và
// validator chấp nhận (xem EXTRA_VALID_VARS) nên công thức mặc định (giấy theo cân) vẫn chạy.
const PHIEU_VARS = [
  "dai_tp", "rong_tp", "dai_nguyen", "rong_nguyen", "dai_in", "rong_in",
  "so_luong", "so_tp", "so_mau", "so_mat", "so_kem", "to_dau_vao", "to_sau_in", "to_nguyen",
];
// Giấy: ngoài 14 biến phiếu, phơi thêm `dinh_luong` (lấy từ ô Định lượng) + `don_gia_kg`
// (lấy từ ô Đơn giá/kg) — công thức theo cân: dinh_luong * dai_nguyen * rong_nguyen * don_gia_kg * to_nguyen.
const GIAY_VARS = [...PHIEU_VARS, "dinh_luong", "don_gia_kg"];
const WHITELIST_VARS = {
  cong_doan: PHIEU_VARS,
  giay: GIAY_VARS,
  // Vật tư: ngoài 14 biến phiếu, chỉ phơi thêm 1 biến `don_gia` (engine bơm từ ô Đơn giá danh mục)
  // — công thức nhân ra thành tiền, vd: so_luong * don_gia. KHÔNG thêm don_gia_kg (nhãn "giấy") /
  // don_gia_m2 (alias trùng don_gia với vật tư) → gây rối.
  vat_tu: [...PHIEU_VARS, "don_gia"],
};

// Giải thích ngắn từng biến — hiện khi hover chip. Kích thước ở đơn vị MÉT trong công thức.
const VAR_DESC: Record<string, string> = {
  dai_tp: "Dài sản phẩm (vd 0,21)",
  rong_tp: "Rộng sản phẩm",
  dai_nguyen: "Dài tờ giấy nguyên (khổ to, chưa cắt)",
  rong_nguyen: "Rộng tờ giấy nguyên",
  dai_in: "Dài tờ chạy máy in (vd 0,64)",
  rong_in: "Rộng tờ chạy máy in",
  so_luong: "Số cái cần làm (số lượng đặt)",
  so_tp: "Số con/tờ — 1 tờ in ra mấy cái",
  so_mau: "Tổng số màu in (mặt A + mặt B)",
  so_mat: "Số mặt qua máy (1 mặt = 1 · 2 mặt/tự trở = 2)",
  so_kem: "Số bản kẽm (bằng số màu)",
  to_dau_vao: "Số tờ vào máy = tờ cần in + bù hao",
  to_sau_in: "Số tờ tốt sau in (dùng cho gia công)",
  to_nguyen: "Số tờ giấy nguyên tiêu hao (giấy to chưa cắt)",
  dinh_luong: "Định lượng giấy, kg/m² (= gsm ÷ 1.000)",
  dai: "Dài của tờ ĐANG ĐẾM, mét — nơi gọi đưa (mua giấy: khổ nguyên · chạy máy: khổ in)",
  rong: "Rộng của tờ đang đếm, mét",
  so_con: "Số con trên tờ — 1 tờ bế ra mấy con",
  don_gia: "Đơn giá — lấy từ ô Giá / Lịch sử giá của mục",
  don_gia_kg: "Đơn giá theo cân (đ/kg)",
  don_gia_m2: "Đơn giá theo diện tích (đ/m²)",
};
// Biến engine VẪN chấp nhận trong công thức (KHÔNG gợi ý chip, nhưng gõ tay vẫn hợp lệ) — để
// công thức cũ (dùng đơn giá / ép kim theo vị trí・diện tích) không bị validator báo đỏ oan.
const EXTRA_VALID_VARS = [
  "dinh_luong", "don_gia", "don_gia_kg", "don_gia_m2", "don_gia_luot", "don_gia_kem",
  "so_vi_tri", "dien_tich",
];

const FRIENDLY_NAMES: Record<string, string> = {
  dai_tp: "Dài sản phẩm",
  rong_tp: "Rộng sản phẩm",
  dai_nguyen: "Dài tờ nguyên",
  rong_nguyen: "Rộng tờ nguyên",
  dai_in: "Dài tờ in",
  rong_in: "Rộng tờ in",
  so_luong: "Số lượng đặt",
  so_tp: "Số con/tờ in",
  so_mau: "Số màu in",
  so_mat: "Số mặt in",
  so_kem: "Số bản kẽm",
  to_dau_vao: "Tờ vào máy",
  to_sau_in: "Tờ tốt sau in",
  to_nguyen: "Tờ giấy nguyên",
  dinh_luong: "Định lượng giấy",
  don_gia: "Đơn giá",
  don_gia_kg: "Đơn giá giấy (kg)",
  don_gia_m2: "Đơn giá (m²)",
  don_gia_luot: "Đơn giá lượt in",
  don_gia_kem: "Đơn giá kẽm",
  so_vi_tri: "Số vị trí",
  dien_tich: "Diện tích",
  // Biến của công thức QUY ĐỔI đơn vị — tên là VAI TRÒ ("tờ đang đếm"), không neo vào khổ nào.
  dai: "Dài tờ đang đếm",
  rong: "Rộng tờ đang đếm",
  so_con: "Số con/tờ",
};

function translateFormula(formula: string): ReactNode[] {
  if (!formula.trim()) return [<span key="empty" style={{ color: "var(--ash, #8a8676)", fontStyle: "italic" }}>Trống (trả về 0đ)</span>];
  let s = formula.replace(/×/g, "*").replace(/÷/g, "/").replace(/−/g, "-");
  const regex = /([a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[\+\-\*\/\(\)\,])/g;
  const matches = s.match(regex) || [];
  
  const elements: ReactNode[] = [];
  let index = 0;
  
  for (const m of matches) {
    const trimmed = m.trim();
    if (!trimmed) continue;
    
    if (FRIENDLY_NAMES[trimmed]) {
      elements.push(
        <span key={index++} className="rc-formula__trans-token rc-formula__trans-token--var">
          {FRIENDLY_NAMES[trimmed]}
        </span>
      );
    } else if (MATH_FUNCS.includes(trimmed)) {
      elements.push(
        <span key={index++} className="rc-formula__trans-token rc-formula__trans-token--func">
          {trimmed.toUpperCase()}
        </span>
      );
    } else if (/^\d+(?:\.\d+)?$/.test(trimmed)) {
      elements.push(
        <span key={index++} className="rc-formula__trans-token rc-formula__trans-token--num">
          {trimmed}
        </span>
      );
    } else if (/^[\+\-\*\/\(\)\,]$/.test(trimmed)) {
      let displayOp = trimmed;
      if (trimmed === "*") displayOp = " × ";
      if (trimmed === "/") displayOp = " ÷ ";
      if (trimmed === "-") displayOp = " − ";
      if (trimmed === "+") displayOp = " + ";
      elements.push(
        <span key={index++} className="rc-formula__trans-token rc-formula__trans-token--op">
          {displayOp}
        </span>
      );
    } else {
      elements.push(
        <span key={index++} className="rc-formula__trans-token rc-formula__trans-token--error">
          {trimmed}
        </span>
      );
    }
  }
  return elements;
}

const MATH_FUNCS = ["ceil", "floor", "round", "max", "min"];

export function FormulaField({
  value,
  onChange,
  configPrefix,
  bienGoiY,
  nhanO = "Công thức tính giá",
  goY = "Nhập công thức tính giá (vd: dai_tp * rong_tp * don_gia)...",
  id = "formula-textarea",
}: {
  value: string;
  onChange: (v: string) => void;
  configPrefix: string;
  /** Bộ biến RIÊNG cho ngữ cảnh khác tính giá (vd quy đổi đơn vị). Có thì thay hẳn whitelist. */
  bienGoiY?: string[];
  nhanO?: string;
  goY?: string;
  /** Nhiều ô công thức trên một màn thì phải khác id — nút chèn biến tìm textarea theo id. */
  id?: string;
}) {
  const isCd = configPrefix.includes("cong-doan");
  const isGiay = configPrefix.endsWith("/giay");   // "/api/vat-lieu-kho/giay"
  const whitelist = bienGoiY ?? (isCd ? WHITELIST_VARS.cong_doan
    : isGiay ? WHITELIST_VARS.giay : WHITELIST_VARS.vat_tu); // chip gợi ý
  // Bộ biến riêng thì KHÔNG nới thêm biến engine tính giá — gõ `don_gia` vào công thức quy đổi
  // phải báo đỏ ngay, không thì để đó tới lúc chạy mới biết.
  const validVars = useMemo(
    () => (bienGoiY ? [...bienGoiY] : [...whitelist, ...EXTRA_VALID_VARS]),
    [whitelist, bienGoiY],
  );
  // Real-time formula validation

  // Popover "Cú pháp"
  const [showSyntax, setShowSyntax] = useState(false);
  const syntaxBtnRef = useRef<HTMLButtonElement>(null);
  const syntaxPopRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!showSyntax) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (syntaxPopRef.current?.contains(t) || syntaxBtnRef.current?.contains(t)) return;
      setShowSyntax(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setShowSyntax(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [showSyntax]);

  const insertVar = (varName: string) => {
    const el = document.getElementById(id) as HTMLTextAreaElement | null;
    if (!el) {
      onChange(value + varName);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const text = el.value;
    const before = text.substring(0, start);
    const after = text.substring(end, text.length);
    const newValue = before + varName + after;
    onChange(newValue);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + varName.length, start + varName.length);
    }, 10);
  };

  // Group variables for clean categorical rendering
  const groups = useMemo(() => {
    const sizeVars = ["dai_tp", "rong_tp", "dai_nguyen", "rong_nguyen", "dai_in", "rong_in",
      "dai", "rong"];
    const qtyVars = ["so_luong", "so_tp", "so_mau", "so_mat", "so_kem", "to_dau_vao", "to_sau_in",
      "to_nguyen", "so_con"];
    const priceVars = ["dinh_luong", "don_gia", "don_gia_m2", "don_gia_luot", "don_gia_kem", "don_gia_kg"];
    const daXep = new Set([...sizeVars, ...qtyVars, ...priceVars]);

    return [
      {
        name: "Kích thước",
        key: "size",
        colorClass: "rc-formula__var-tag--size",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect width="20" height="8" x="2" y="8" rx="1.5"/>
            <path d="M6 16v-4M10 16v-2M14 16v-4M18 16v-2"/>
          </svg>
        ),
        vars: whitelist.filter(v => sizeVars.includes(v))
      },
      {
        name: "Số lượng & Sản lượng",
        key: "qty",
        colorClass: "rc-formula__var-tag--qty",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 22V4c0-.5.2-1 .6-1.4C5 2.2 5.5 2 6 2h12c.5 0 1 .2 1.4.6.4.4.6.9.6 1.4v18l-4-2-4 2-4-2-4 2z"/>
            <path d="M8 6h8M8 10h8M8 14h6"/>
          </svg>
        ),
        vars: whitelist.filter(v => qtyVars.includes(v))
      },
      {
        name: "Giá vốn & Đơn giá",
        key: "price",
        colorClass: "rc-formula__var-tag--price",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" x2="12" y1="2" y2="22"/>
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
        ),
        vars: whitelist.filter(v => priceVars.includes(v))
      },
      {
        name: "Khác",
        key: "khac",
        colorClass: "rc-formula__var-tag--qty",
        icon: null,
        vars: whitelist.filter(v => !daXep.has(v)),
      },
    ].filter(g => g.vars.length > 0);
  }, [whitelist]);

  // Real-time formula validation
  const { valid, error } = useMemo(() => {
    if (!value.trim()) return { valid: true, error: null };
    
    let openParen = 0;
    for (const char of value) {
      if (char === '(') openParen++;
      if (char === ')') openParen--;
      if (openParen < 0) {
        return { valid: false, error: "Đóng mở ngoặc đơn không hợp lệ" };
      }
    }
    if (openParen !== 0) {
      return { valid: false, error: "Thiếu dấu đóng hoặc mở ngoặc đơn" };
    }

    const tokenRegex = /[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[\+\-\*\/\(\)]|\s+/g;
    const tokens = value.match(tokenRegex) || [];
    
    for (const token of tokens) {
      const trimmed = token.trim();
      if (!trimmed) continue;
      
      if (
        !validVars.includes(trimmed) &&
        !MATH_FUNCS.includes(trimmed) &&
        !/^\d+(?:\.\d+)?$/.test(trimmed) &&
        !/^[\+\-\*\/\(\)]$/.test(trimmed)
      ) {
        return {
          valid: false,
          error: `Biến hoặc hàm "${trimmed}" không được hỗ trợ trong hệ thống`
        };
      }
    }

    return { valid: true, error: null };
  }, [value, validVars]);

  return (
    <div className="rc-formula">
      {/* 1. Trình soạn thảo công thức ở trên cùng */}
      <div className="rc-formula__editor-container">
        <div className="rc-formula__editor-header">
          <span className="rc-formula__editor-label">{nhanO}</span>
          <button
            ref={syntaxBtnRef}
            type="button"
            className={`rc-formula__syntax-btn${showSyntax ? " is-open" : ""}`}
            onClick={() => setShowSyntax((s) => !s)}
            aria-expanded={showSyntax}
            title="Phép tính · hàm · biến được hỗ trợ"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M6 8h.01M10 8h.01M14 8h.01M6 12h.01M10 12h.01M14 12h.01M8 16h8" />
            </svg>
            Cú pháp
          </button>
          {showSyntax && (
            <div ref={syntaxPopRef} className="rc-syntax" role="dialog" aria-label="Cú pháp công thức">
              <div className="rc-syntax__head">
                <span>Cú pháp công thức</span>
                <button type="button" className="rc-syntax__x" onClick={() => setShowSyntax(false)} aria-label="Đóng">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
                </button>
              </div>
              <div className="rc-syntax__body">
                <div className="rc-syntax__sec-title">Phép tính</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>+ - * /</code></td><td>cộng · trừ · nhân · chia</td></tr>
                  <tr><td><code>**</code></td><td>lũy thừa</td></tr>
                  <tr><td><code>( )</code></td><td>ngoặc nhóm</td></tr>
                  <tr><td><code>-x</code></td><td>dấu âm đơn</td></tr>
                  <tr><td><code>,</code></td><td>ngăn tham số hàm</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Hàm — đúng 5</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>max(a,b)</code></td><td>lớn nhất — giá sàn</td></tr>
                  <tr><td><code>min(a,b)</code></td><td>nhỏ nhất — giá trần</td></tr>
                  <tr><td><code>round(x)</code></td><td>làm tròn</td></tr>
                  <tr><td><code>ceil(x)</code></td><td>làm tròn lên</td></tr>
                  <tr><td><code>floor(x)</code></td><td>làm tròn xuống</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Biến</div>
                <p className="rc-syntax__note">Bấm chip biến ở dưới để chèn. Kích thước tính bằng <b>mét</b>.</p>
              </div>
            </div>
          )}
        </div>

        {/* Thanh chèn toán tử nhanh */}
        <div className="rc-formula__op-toolbar">
          <span className="rc-formula__op-label">Chèn toán tử:</span>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" + ")} title="Cộng">+</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" - ")} title="Trừ">−</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" * ")} title="Nhân">×</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" / ")} title="Chia">÷</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("(")} title="Mở ngoặc">(</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(")")} title="Đóng ngoặc">)</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("max(")} title="Hàm max">max</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("min(")} title="Hàm min">min</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("round(")} title="Hàm round">round</button>
        </div>

        <textarea
          id={id}
          className="rc-formula__textarea"
          rows={2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={goY}
        />
      </div>

      {/* 2. Dịch nghĩa tiếng Việt ngay dưới ô gõ */}
      <div className="rc-formula__trans-container">
        <div className="rc-formula__trans-title">Dịch nghĩa công thức (tiếng Việt):</div>
        <div className="rc-formula__trans-content">
          {translateFormula(value)}
        </div>
      </div>

      {!valid && (
        <div className="rc-formula__validation">
          <div className="rc-formula__status rc-formula__status--error">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "6px" }}>
              <circle cx="12" cy="12" r="10"/>
              <path d="m15 9-6 6M9 9l6 6"/>
            </svg>
            {error}
          </div>
        </div>
      )}

      {/* 3. Danh sách biến khả dụng (Gom chung 1 nhóm) */}
      <div className="rc-formula__header-bar">
        <span className="rc-formula__header-title">Danh sách biến khả dụng</span>
      </div>

      <div className="rc-formula__all-vars">
        {groups.flatMap((g) => g.vars.map((v) => ({ v, colorClass: g.colorClass }))).map(({ v, colorClass }) => (
          <button
            key={v}
            type="button"
            className={`rc-formula__var-tag ${colorClass}`}
            onClick={() => insertVar(v)}
            title={VAR_DESC[v] || v}
          >
            <span className="rc-formula__var-name">{FRIENDLY_NAMES[v] || v}</span>
            <code className="rc-formula__var-code">{v}</code>
          </button>
        ))}
      </div>
    </div>
  );
}

