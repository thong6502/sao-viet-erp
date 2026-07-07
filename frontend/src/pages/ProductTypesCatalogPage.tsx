import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ProductTypeCatalogRow,
  type ProductTypeCatalogInput,
  type ProductTypePreviewResult,
  type MaterialRow,
  type ImpositionTypeRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const CALC_STRATEGIES = [
  { value: "sheet_based", label: "Theo khổ tờ (Sheet-based)" },
  { value: "page_based", label: "Theo số trang (Page-based)" },
  { value: "area_based", label: "Theo diện tích m² (Area-based)" },
  { value: "box_based", label: "Theo hộp (Box-based)" },
  { value: "roll_based", label: "Theo cuộn (Roll-based)" },
  { value: "book_based", label: "Theo cuốn sách (Book-based)" },
];

const PRODUCT_GROUPS = [
  { value: "an_pham", label: "Ấn phẩm" },
  { value: "bao_bi", label: "Bao bì" },
  { value: "sach", label: "Sách / nhiều trang" },
  { value: "nhan", label: "Nhãn / tem" },
  { value: "khac", label: "Khác" },
];

const TECH_TYPES = [
  { value: "offset", label: "In Offset" },
  { value: "digital", label: "In Kỹ thuật số" },
  { value: "large_format", label: "In Khổ lớn" },
  { value: "flexo", label: "In Flexo" },
];

const DIM_RULES = [
  { value: "finished", label: "Khổ thành phẩm" },
  { value: "spread", label: "Khổ trải" },
  { value: "multi_page", label: "Khổ trang (nhiều trang)" },
];

const SHEET_MODES = [
  { value: "by_pieces", label: "Theo số con hình học" },
  { value: "by_pages", label: "Theo số trang / tay" },
  { value: "manual", label: "Nhập tay" },
];

const INK_MODES = [
  { value: "per_1000", label: "Theo 1.000 lượt" },
  { value: "coverage", label: "Theo độ phủ" },
];

const TOOLING_TYPES = [
  { value: "khuon_be", label: "Khuôn bế" },
  { value: "khuon_ep_kim", label: "Khuôn ép kim" },
  { value: "khuon_dap_noi", label: "Khuôn dập nổi" },
  { value: "other", label: "Khuôn khác" },
];

// spec §B — vocab field input trên màn Tính giá.
const INPUT_FIELDS = [
  { value: "finished_w", label: "Khổ rộng TP" },
  { value: "finished_h", label: "Khổ cao TP" },
  { value: "finished_d", label: "Khổ sâu / dày TP" },
  { value: "spread_w", label: "Khổ trải rộng" },
  { value: "spread_h", label: "Khổ trải cao" },
  { value: "quantity", label: "Số lượng" },
  { value: "colors", label: "Số màu" },
  { value: "sides", label: "Số mặt" },
  { value: "page_count", label: "Số trang" },
  { value: "signature_count", label: "Số tay" },
  { value: "spine_width", label: "Độ dày gáy" },
  { value: "paper", label: "Giấy" },
  { value: "cover_paper", label: "Giấy bìa" },
  { value: "body_paper", label: "Giấy ruột" },
  { value: "ink", label: "Mực" },
  { value: "machine", label: "Máy in" },
  { value: "sheet_size", label: "Khổ tờ in" },
  { value: "imposition", label: "Kiểu bình bài" },
  { value: "operations", label: "Công đoạn" },
];

const MAT_TYPES = [
  { value: "paper", label: "Giấy in" },
  { value: "decal", label: "Decal" },
  { value: "pp", label: "PP" },
  { value: "canvas", label: "Vải canvas" },
  { value: "carton", label: "Giấy carton" },
  { value: "film", label: "Film" },
  { value: "formex", label: "Formex" },
  { value: "lamination", label: "Màng cán" },
  { value: "glue", label: "Keo dán" },
  { value: "chemical", label: "Hóa chất / mực" },
];

const OP_TYPE_LABELS: Record<string, string> = {
  in: "In ấn", can_mang: "Cán màng", be: "Bế hình / Đột", boi: "Bồi", ep_kim: "Ép kim / Nhũ",
  dap_noi: "Dập nổi / chìm", uv: "UV định hình", gap: "Gấp nếp", dong_cuon: "Đóng cuốn",
  dan_hop: "Dán hộp", xen: "Xén", dong_goi: "Đóng gói", other: "Gia công khác",
};

const PT_TABS = [
  { key: "general", label: "Thông tin chung" },
  { key: "inputs", label: "Input cần nhập" },
  { key: "dimension", label: "Quy tắc kích thước" },
  { key: "materials", label: "Vật tư mặc định" },
  { key: "routing", label: "Routing mặc định" },
  { key: "rules", label: "Bình bài & quy tắc" },
  { key: "test", label: "Test nhanh" },
] as const;
type PtTabKey = (typeof PT_TABS)[number]["key"];

export function ProductTypesCatalogPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("dm_loai_san_pham", "create");
  const canUpdate = can("dm_loai_san_pham", "update");
  const canDelete = can("dm_loai_san_pham", "delete");
  const [rows, setRows] = useState<ProductTypeCatalogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<ProductTypeCatalogRow | null>(null);
  const [deleting, setDeleting] = useState<ProductTypeCatalogRow | null>(null);
  const [cloning, setCloning] = useState<ProductTypeCatalogRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.productTypesCatalog
      .list(token, { size: 100 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được cấu hình loại sản phẩm.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => { load(); }, [load]);

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.productTypesCatalog.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được cấu hình.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Loại sản phẩm (403).
        </div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Loại sản phẩm & Quy tắc tính</h1>
        <p className="md-page__sub">
          Template nghiệp vụ cho màn Tính giá: khai loại SP hỏi field nào, gợi ý công đoạn nào,
          bleed/gutter mặc định nào và đi theo nhánh tính nào.
        </p>
      </header>

      <div className="md-page__toolbar">
        <div className="md-page__toolbar-spacer" />
        {canCreate && (
          <Button variant="primary" onClick={() => { setEditing(null); setMode("create"); }}>
            + Tạo loại sản phẩm
          </Button>
        )}
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={() => load()}>Tải lại</button>
        </div>
      )}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã loại SP</th>
              <th>Tên hiển thị</th>
              <th>Nhóm</th>
              <th>Chiến lược tính</th>
              <th>Routing mặc định</th>
              <th>Kích thước</th>
              <th>Bình mặc định</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} className="md-page__status" role="status">Đang tải dữ liệu...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="md-page__empty">Chưa có cấu hình loại sản phẩm nào.</td></tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="md-page__row"
                  onClick={canUpdate ? () => { setEditing(row); setMode("edit"); } : undefined}
                  style={canUpdate ? undefined : { cursor: "default" }}
                >
                  <td className="md-page__mono">{row.product_type}</td>
                  <td><strong>{row.name}</strong></td>
                  <td>{PRODUCT_GROUPS.find((g) => g.value === row.product_group)?.label ?? row.product_group}</td>
                  <td><span className="md-page__tag-calc">{CALC_STRATEGIES.find((s) => s.value === row.calculation_strategy)?.label ?? row.calculation_strategy}</span></td>
                  <td>
                    <div className="md-page__tag-group">
                      {row.default_operations?.length ? row.default_operations.map((op) => (
                        <span key={op} className="md-page__tag">{OP_TYPE_LABELS[op] ?? op}</span>
                      )) : <span className="md-page__muted">—</span>}
                    </div>
                  </td>
                  <td>{DIM_RULES.find((d) => d.value === row.dimension_rule_type)?.label ?? row.dimension_rule_type}</td>
                  <td className="md-page__mono">{row.default_imposition_code ?? "—"}</td>
                  <td>
                    <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                      {row.is_active ? "Đang chạy" : "Tạm ngưng"}
                    </span>
                  </td>
                  <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                    {canUpdate && (
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => { setEditing(row); setMode("edit"); }}>Sửa</button>
                    )}
                    {canCreate && (
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setCloning(row)}>Sao chép</button>
                    )}
                    {canDelete && (
                      <button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => setDeleting(row)}>Xóa</button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {mode && (
        <ProductTypeFormDialog
          existing={editing}
          onClose={() => { setMode(null); setEditing(null); }}
          onSaved={() => { setMode(null); setEditing(null); load(); }}
        />
      )}

      {cloning && (
        <CloneDialog source={cloning} onClose={() => setCloning(null)} onSaved={() => { setCloning(null); load(); }} />
      )}

      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head"><h2>Xác nhận xóa</h2></div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa cấu hình loại sản phẩm <strong>{deleting.name}</strong> ({deleting.product_type})?</p>
              <div className="md-page__dialog-actions">
                <Button variant="ghost" onClick={() => setDeleting(null)}>Hủy</Button>
                <Button variant="danger" onClick={handleDelete}>Xác nhận xóa</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function CloneDialog({ source, onClose, onSaved }: { source: ProductTypeCatalogRow; onClose: () => void; onSaved: () => void; }) {
  const { token } = useAuth();
  const [code, setCode] = useState(`${source.product_type}_v2`);
  const [name, setName] = useState(`${source.name} (bản mới)`);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setSaving(true); setErr(null);
    try {
      await api.productTypesCatalog.clone(token, source.id, { new_product_type: code.trim(), new_name: name.trim() });
      onSaved();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Sao chép thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog md-page__dialog--sm card">
        <div className="md-page__dialog-head"><h2>Sao chép / Tạo version mới</h2><button type="button" className="md-page__close" onClick={onClose}>✕</button></div>
        <form className="md-page__dialog-body" onSubmit={submit}>
          <p className="md-page__note">Nhân bản toàn bộ cấu hình của <strong>{source.name}</strong> sang mã mới.</p>
          <label className="field"><span className="field__label">Mã mới *</span>
            <input className="input" value={code} onChange={(e) => setCode(e.target.value)} /></label>
          <label className="field"><span className="field__label">Tên mới *</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
          {err && <div className="banner banner--error" role="alert">{err}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Tạo bản sao</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ProductTypeFormDialog({ existing, onClose, onSaved }: {
  existing: ProductTypeCatalogRow | null; onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;
  const [tab, setTab] = useState<PtTabKey>("general");

  // §A
  const [productType, setProductType] = useState(existing?.product_type ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [group, setGroup] = useState(existing?.product_group ?? "an_pham");
  const [tech, setTech] = useState(existing?.technology ?? "offset");
  const [strategy, setStrategy] = useState(existing?.calculation_strategy ?? "sheet_based");
  const [displayOrder, setDisplayOrder] = useState(String(existing?.display_order ?? 100));
  const [description, setDescription] = useState(existing?.description ?? "");
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);
  // §B
  const [shown, setShown] = useState<string[]>(existing?.shown_fields ?? existing?.required_fields ?? []);
  const [required, setRequired] = useState<string[]>(existing?.required_fields ?? []);
  // §C
  const [dimRule, setDimRule] = useState(existing?.dimension_rule_type ?? "finished");
  const [bleed, setBleed] = useState(String(existing?.default_bleed_mm ?? 3));
  const [gutter, setGutter] = useState(String(existing?.default_gutter_mm ?? 3));
  const [trim, setTrim] = useState(String(existing?.default_trim_mm ?? 5));
  const [allowRotation, setAllowRotation] = useState(existing?.allow_rotation ?? true);
  const [allowCustom, setAllowCustom] = useState(existing?.allow_custom_size ?? true);
  // §D/§E
  const [hasCoverBody, setHasCoverBody] = useState(existing?.has_cover_body_split ?? false);
  const [hasPageCount, setHasPageCount] = useState(existing?.has_page_count ?? false);
  const [pageMultiple, setPageMultiple] = useState(String(existing?.page_multiple ?? 0));
  const [perSignature, setPerSignature] = useState(String(existing?.pages_per_signature ?? 0));
  const [allowMats, setAllowMats] = useState<string[]>(existing?.allowed_materials ?? []);
  const [defPaper, setDefPaper] = useState<string>(existing?.default_paper_material_id ? String(existing.default_paper_material_id) : "");
  const [defCover, setDefCover] = useState<string>(existing?.default_cover_material_id ? String(existing.default_cover_material_id) : "");
  const [defBody, setDefBody] = useState<string>(existing?.default_body_material_id ? String(existing.default_body_material_id) : "");
  const [defInk, setDefInk] = useState<string>(existing?.default_ink_material_id ? String(existing.default_ink_material_id) : "");
  const [hasPackaging, setHasPackaging] = useState(existing?.has_packaging ?? false);
  const [packQty, setPackQty] = useState(String(existing?.default_pack_qty ?? 0));
  // §F
  const [defOps, setDefOps] = useState<string[]>(existing?.default_operations ?? []);
  const [reqOps, setReqOps] = useState<string[]>(existing?.required_operations ?? []);
  const [allowExtraOps, setAllowExtraOps] = useState(existing?.allow_extra_operations ?? true);
  // §G/§H
  const [allowedImpo, setAllowedImpo] = useState<string[]>(existing?.allowed_imposition_codes ?? []);
  const [defImpo, setDefImpo] = useState<string>(existing?.default_imposition_code ?? "");
  const [allowImpoChange, setAllowImpoChange] = useState(existing?.allow_imposition_change ?? true);
  const [sheetMode, setSheetMode] = useState(existing?.sheet_count_mode ?? "by_pieces");
  const [inkMode, setInkMode] = useState(existing?.ink_cost_mode ?? "per_1000");
  const [hasTooling, setHasTooling] = useState(existing?.has_tooling ?? false);
  const [toolingType, setToolingType] = useState(existing?.default_tooling_type ?? "khuon_be");
  const [allowOverride, setAllowOverride] = useState(existing?.allow_manual_override ?? false);
  const [wastePct, setWastePct] = useState(existing?.waste_pct != null ? String(existing.waste_pct) : "0");
  // compatible_technologies (multi) giữ nguyên từ bản ghi; công nghệ chính khai ở `technology`.
  const [comps] = useState<string[]>(existing?.compatible_technologies ?? []);

  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Danh mục để đổ dropdown/checkbox
  const [opTypes, setOpTypes] = useState<string[]>([]);
  const [materials, setMaterials] = useState<MaterialRow[]>([]);
  const [impoTypes, setImpoTypes] = useState<ImpositionTypeRow[]>([]);
  useEffect(() => {
    if (!token) return;
    api.operations.list(token, { page: 1, size: 200 })
      .then((res) => setOpTypes([...new Set(res.items.map((o) => o.operation_type))]))
      .catch(() => setOpTypes([]));
    api.materials.list(token, { size: 200 }).then((res) => setMaterials(res.items)).catch(() => setMaterials([]));
    api.impositionTypes.list(token, { size: 100 }).then((res) => setImpoTypes(res.items)).catch(() => setImpoTypes([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Test nhanh
  const [preview, setPreview] = useState<ProductTypePreviewResult | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  function toggle(list: string[], setList: (l: string[]) => void, val: string) {
    setList(list.includes(val) ? list.filter((x) => x !== val) : [...list, val]);
  }
  function toggleShown(val: string) {
    if (shown.includes(val)) {
      setShown(shown.filter((x) => x !== val));
      setRequired(required.filter((x) => x !== val)); // ẩn thì bỏ bắt buộc
    } else setShown([...shown, val]);
  }
  function toggleRequired(val: string) {
    if (required.includes(val)) setRequired(required.filter((x) => x !== val));
    else {
      setRequired([...required, val]);
      if (!shown.includes(val)) setShown([...shown, val]); // bắt buộc ⇒ phải hiển thị
    }
  }
  function toggleOp(val: string) {
    if (defOps.includes(val)) {
      setDefOps(defOps.filter((x) => x !== val));
      setReqOps(reqOps.filter((x) => x !== val));
    } else setDefOps([...defOps, val]);
  }

  function buildPayload(): ProductTypeCatalogInput {
    return {
      product_type: productType.trim(),
      name: name.trim(),
      calculation_strategy: strategy,
      product_group: group,
      technology: tech,
      description: description.trim() || null,
      display_order: Number(displayOrder) || 100,
      shown_fields: shown,
      required_fields: required,
      dimension_rule_type: dimRule,
      default_bleed_mm: Number(bleed) || 0,
      default_gutter_mm: Number(gutter) || 0,
      default_trim_mm: Number(trim) || 0,
      allow_rotation: allowRotation,
      allow_custom_size: allowCustom,
      has_page_count: hasPageCount,
      page_multiple: Number(pageMultiple) || 0,
      pages_per_signature: Number(perSignature) || 0,
      has_cover_body_split: hasCoverBody,
      allowed_materials: allowMats,
      default_paper_material_id: defPaper ? Number(defPaper) : null,
      default_cover_material_id: defCover ? Number(defCover) : null,
      default_body_material_id: defBody ? Number(defBody) : null,
      default_ink_material_id: defInk ? Number(defInk) : null,
      has_packaging: hasPackaging,
      default_pack_qty: Number(packQty) || 0,
      default_operations: defOps,
      required_operations: reqOps,
      allow_extra_operations: allowExtraOps,
      allowed_imposition_codes: allowedImpo,
      default_imposition_code: defImpo || null,
      allow_imposition_change: allowImpoChange,
      compatible_technologies: comps,
      sheet_count_mode: sheetMode,
      ink_cost_mode: inkMode,
      has_tooling: hasTooling,
      default_tooling_type: hasTooling ? toolingType : null,
      allow_manual_override: allowOverride,
      waste_pct: Math.max(0, Math.min(100, Number(wastePct) || 0)),
      is_active: isActive,
    };
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setValidationError(null);
    if (!productType.trim()) { setTab("general"); return setValidationError("Mã loại sản phẩm không được trống."); }
    if (!name.trim()) { setTab("general"); return setValidationError("Tên loại sản phẩm không được trống."); }
    if (hasTooling && !toolingType) { setTab("rules"); return setValidationError("Có khuôn thì phải chọn loại khuôn."); }

    setSaving(true);
    try {
      if (isEdit && existing) await api.productTypesCatalog.update(token, existing.id, buildPayload());
      else await api.productTypesCatalog.create(token, buildPayload());
      onSaved();
    } catch (err) {
      setValidationError(err instanceof ApiError ? err.message : "Lưu thất bại. Vui lòng kiểm tra lại.");
      setSaving(false);
    }
  }

  async function runPreview() {
    if (!token || !existing) return;
    setPreviewErr(null);
    try {
      setPreview(await api.productTypesCatalog.preview(token, existing.id));
    } catch (err) {
      setPreviewErr(err instanceof ApiError ? err.message : "Không chạy được test.");
    }
  }

  const paperMats = materials.filter((m) => m.material_type === "paper");
  const inkMats = materials.filter((m) => m.material_type === "chemical" || m.material_type === "paper");

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa loại SP: ${existing?.name}` : "Tạo loại sản phẩm mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>

        <div className="md-tabs">
          {PT_TABS.map((t) => (
            <button key={t.key} type="button" className={`md-tab ${tab === t.key ? "md-tab--active" : ""}`}
              onClick={() => { setTab(t.key); if (t.key === "test") runPreview(); }}>
              {t.label}
            </button>
          ))}
        </div>

        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {tab === "general" && (
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Mã loại sản phẩm *</span>
                <input className="input" placeholder="VD: hop_giay" value={productType} onChange={(e) => setProductType(e.target.value)} disabled={isEdit} /></label>
              <label className="field"><span className="field__label">Tên hiển thị *</span>
                <input className="input" placeholder="VD: Hộp giấy" value={name} onChange={(e) => setName(e.target.value)} /></label>
              <label className="field"><span className="field__label">Nhóm sản phẩm *</span>
                <select className="input" value={group} onChange={(e) => setGroup(e.target.value)}>
                  {PRODUCT_GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Công nghệ áp dụng *</span>
                <select className="input" value={tech} onChange={(e) => setTech(e.target.value)}>
                  {TECH_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Chiến lược tính giá *</span>
                <select className="input" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  {CALC_STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Thứ tự hiển thị</span>
                <input className="input" type="number" value={displayOrder} onChange={(e) => setDisplayOrder(e.target.value)} /></label>
              <label className="field md-page__form-wide"><span className="field__label">Mô tả</span>
                <textarea className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
              <label className="field"><span className="field__label">Trạng thái</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="pt-active" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  <label htmlFor="pt-active">Kích hoạt hoạt động</label></div></label>
            </div>
          )}

          {tab === "inputs" && (
            <>
              <div className="md-page__note">Tick <strong>Hiện</strong> để field xuất hiện trên màn Tính giá; tick <strong>Bắt buộc</strong> để bắt nhập (bắt buộc luôn phải hiện).</div>
              <table className="md-page__table">
                <thead><tr><th>Field</th><th style={{ width: 90 }}>Hiện</th><th style={{ width: 90 }}>Bắt buộc</th></tr></thead>
                <tbody>
                  {INPUT_FIELDS.map((f) => (
                    <tr key={f.value}>
                      <td>{f.label} <span className="md-page__muted md-page__mono">{f.value}</span></td>
                      <td><input type="checkbox" checked={shown.includes(f.value)} onChange={() => toggleShown(f.value)} /></td>
                      <td><input type="checkbox" checked={required.includes(f.value)} onChange={() => toggleRequired(f.value)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {tab === "dimension" && (
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Kiểu kích thước tính số con *</span>
                <select className="input" value={dimRule} onChange={(e) => setDimRule(e.target.value)}>
                  {DIM_RULES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}</select></label>
              <div />
              <label className="field"><span className="field__label">Bleed mặc định (mm)</span>
                <input className="input" type="number" step="0.5" value={bleed} onChange={(e) => setBleed(e.target.value)} /></label>
              <label className="field"><span className="field__label">Gutter mặc định (mm)</span>
                <input className="input" type="number" step="0.5" value={gutter} onChange={(e) => setGutter(e.target.value)} /></label>
              <label className="field"><span className="field__label">Lề xén mặc định (mm)</span>
                <input className="input" type="number" step="0.5" value={trim} onChange={(e) => setTrim(e.target.value)} /></label>
              <label className="field"><span className="field__label">Tùy chọn</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-rot" checked={allowRotation} onChange={(e) => setAllowRotation(e.target.checked)} /><label htmlFor="pt-rot">Cho phép xoay bài</label></div>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-custom" checked={allowCustom} onChange={(e) => setAllowCustom(e.target.checked)} /><label htmlFor="pt-custom">Cho phép nhập khổ custom</label></div></label>
              <div className="md-page__hint md-page__form-wide">
                Số con tính theo <strong>{DIM_RULES.find((d) => d.value === dimRule)?.label}</strong> + bleed + gutter.
                Engine dùng bleed/gutter/lề xén này làm mặc định khi màn Tính giá không nhập tay.
              </div>
            </div>
          )}

          {tab === "materials" && (
            <div className="md-page__form-grid">
              <div className="md-page__choices md-page__form-wide">
                <span className="field__label">Vật liệu được phép (loại)</span>
                <div className="md-page__checkboxes" style={{ maxHeight: 120 }}>
                  {MAT_TYPES.map((m) => (
                    <label key={m.value} className="md-page__checkbox-label">
                      <input type="checkbox" checked={allowMats.includes(m.value)} onChange={() => toggle(allowMats, setAllowMats, m.value)} />
                      <span>{m.label}</span></label>
                  ))}
                </div>
              </div>
              <label className="field"><span className="field__label">Giấy mặc định</span>
                <select className="input" value={defPaper} onChange={(e) => setDefPaper(e.target.value)}>
                  <option value="">— không chọn —</option>
                  {paperMats.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
              <label className="field"><span className="field__label">Mực mặc định</span>
                <select className="input" value={defInk} onChange={(e) => setDefInk(e.target.value)}>
                  <option value="">— không chọn —</option>
                  {inkMats.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
              {hasCoverBody && (
                <>
                  <label className="field"><span className="field__label">Giấy bìa mặc định</span>
                    <select className="input" value={defCover} onChange={(e) => setDefCover(e.target.value)}>
                      <option value="">— không chọn —</option>
                      {paperMats.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
                  <label className="field"><span className="field__label">Giấy ruột mặc định</span>
                    <select className="input" value={defBody} onChange={(e) => setDefBody(e.target.value)}>
                      <option value="">— không chọn —</option>
                      {paperMats.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
                </>
              )}
              <label className="field"><span className="field__label">Bao bì / đóng gói</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-pack" checked={hasPackaging} onChange={(e) => setHasPackaging(e.target.checked)} /><label htmlFor="pt-pack">Có bao bì</label></div></label>
              {hasPackaging && (
                <label className="field"><span className="field__label">Quy cách đóng gói (cái/thùng)</span>
                  <input className="input" type="number" value={packQty} onChange={(e) => setPackQty(e.target.value)} /></label>
              )}
            </div>
          )}

          {tab === "routing" && (
            <div className="md-page__form-grid">
              <div className="md-page__note md-page__form-wide">Tick để thêm công đoạn vào routing (thứ tự = thứ tự tick). Cột <strong>Bắt buộc</strong> đánh dấu công đoạn không được bỏ.</div>
              {opTypes.length === 0 ? (
                <p className="md-page__muted md-page__form-wide">Chưa có công đoạn nào trong danh mục — tạo ở trang "Công đoạn gia công" trước.</p>
              ) : (
                <table className="md-page__table md-page__form-wide">
                  <thead><tr><th style={{ width: 60 }}>Dùng</th><th>Công đoạn</th><th style={{ width: 80 }}>Thứ tự</th><th style={{ width: 90 }}>Bắt buộc</th></tr></thead>
                  <tbody>
                    {opTypes.map((t) => {
                      const idx = defOps.indexOf(t);
                      return (
                        <tr key={t}>
                          <td><input type="checkbox" checked={idx >= 0} onChange={() => toggleOp(t)} /></td>
                          <td>{OP_TYPE_LABELS[t] ?? t}</td>
                          <td>{idx >= 0 ? (idx + 1) * 10 : "—"}</td>
                          <td>{idx >= 0 && <input type="checkbox" checked={reqOps.includes(t)} onChange={() => toggle(reqOps, setReqOps, t)} />}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <label className="field md-page__form-wide">
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-extra" checked={allowExtraOps} onChange={(e) => setAllowExtraOps(e.target.checked)} /><label htmlFor="pt-extra">Cho phép thêm công đoạn ngoài template</label></div></label>
            </div>
          )}

          {tab === "rules" && (
            <div className="md-page__form-grid">
              <div className="md-page__choices md-page__form-wide">
                <span className="field__label">Kiểu bình bài được phép</span>
                <div className="md-page__checkboxes" style={{ maxHeight: 120 }}>
                  {impoTypes.map((it) => (
                    <label key={it.code} className="md-page__checkbox-label">
                      <input type="checkbox" checked={allowedImpo.includes(it.code)} onChange={() => toggle(allowedImpo, setAllowedImpo, it.code)} />
                      <span>{it.name} <span className="md-page__mono md-page__muted">{it.code}</span></span></label>
                  ))}
                </div>
              </div>
              <label className="field"><span className="field__label">Kiểu bình mặc định</span>
                <select className="input" value={defImpo} onChange={(e) => setDefImpo(e.target.value)}>
                  <option value="">— không chọn —</option>
                  {(allowedImpo.length ? allowedImpo : impoTypes.map((i) => i.code)).map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
              <label className="field"><span className="field__label">Cho phép đổi bình bài</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-impo-chg" checked={allowImpoChange} onChange={(e) => setAllowImpoChange(e.target.checked)} /><label htmlFor="pt-impo-chg">Người dùng được đổi</label></div></label>
              <label className="field"><span className="field__label">Cách tính số tờ</span>
                <select className="input" value={sheetMode} onChange={(e) => setSheetMode(e.target.value)}>
                  {SHEET_MODES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
              <label className="field"><span className="field__label">% Bù hao</span>
                <input className="input" type="number" min="0" max="100" step="0.5" value={wastePct}
                  onChange={(e) => setWastePct(e.target.value)} placeholder="VD: 5" />
                <span className="md-page__hint">Cộng thẳng vào SỐ TỜ SẢN XUẤT (đội giấy + mực + giờ máy, KHÔNG đội kẽm). 0 = không hao. Thay cả module Định mức cũ.</span></label>
              <label className="field"><span className="field__label">Cách tính mực</span>
                <select className="input" value={inkMode} onChange={(e) => setInkMode(e.target.value)}>
                  {INK_MODES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Số trang / tay</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-page" checked={hasPageCount} onChange={(e) => setHasPageCount(e.target.checked)} /><label htmlFor="pt-page">Có dùng số trang</label></div>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-cb" checked={hasCoverBody} onChange={(e) => setHasCoverBody(e.target.checked)} /><label htmlFor="pt-cb">Tính bìa / ruột riêng</label></div></label>
              {hasPageCount && (
                <>
                  <label className="field"><span className="field__label">Số trang chia hết cho</span>
                    <input className="input" type="number" value={pageMultiple} onChange={(e) => setPageMultiple(e.target.value)} /></label>
                  <label className="field"><span className="field__label">Số trang mỗi tay</span>
                    <input className="input" type="number" value={perSignature} onChange={(e) => setPerSignature(e.target.value)} /></label>
                </>
              )}
              <label className="field"><span className="field__label">Khuôn</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-tool" checked={hasTooling} onChange={(e) => setHasTooling(e.target.checked)} /><label htmlFor="pt-tool">Có phát sinh khuôn</label></div></label>
              {hasTooling && (
                <label className="field"><span className="field__label">Loại khuôn mặc định *</span>
                  <select className="input" value={toolingType} onChange={(e) => setToolingType(e.target.value)}>
                    {TOOLING_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
              )}
              <label className="field md-page__form-wide">
                <div className="md-page__toggle-wrap"><input type="checkbox" id="pt-override" checked={allowOverride} onChange={(e) => setAllowOverride(e.target.checked)} /><label htmlFor="pt-override">Cho phép override công thức (admin)</label></div></label>
            </div>
          )}

          {tab === "test" && (
            <div>
              {!isEdit ? (
                <div className="md-page__note">Lưu loại sản phẩm trước rồi mở lại để Test nhanh.</div>
              ) : previewErr ? (
                <div className="banner banner--error" role="alert">{previewErr}</div>
              ) : preview ? (
                <div className="md-page__preview">
                  <div className="md-page__preview-head">Khi chọn <strong>{preview.name}</strong> ở màn Tính giá:</div>
                  <div><strong>Field hiển thị:</strong> {preview.shown_fields.map((f) => INPUT_FIELDS.find((x) => x.value === f)?.label ?? f).join(", ") || "—"}</div>
                  <div><strong>Bắt buộc:</strong> {preview.required_fields.map((f) => INPUT_FIELDS.find((x) => x.value === f)?.label ?? f).join(", ") || "—"}</div>
                  <div><strong>Routing:</strong> {preview.routing.map((o) => OP_TYPE_LABELS[o] ?? o).join(" → ") || "—"}</div>
                  <div className="md-page__hint">
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Quy tắc áp dụng:</div>
                    {preview.rules.map((r, i) => <div key={i}>• {r}</div>)}
                  </div>
                  {preview.warnings.map((w, i) => <div key={i} className="banner banner--warn" role="alert">{w}</div>)}
                </div>
              ) : (
                <div className="md-page__note">Đang tải preview... <button type="button" className="btn btn--ghost" onClick={runPreview}>Chạy lại</button></div>
              )}
            </div>
          )}

          {validationError && <div className="banner banner--error" role="alert">{validationError}</div>}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu cấu hình</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
