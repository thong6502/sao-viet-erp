// Danh mục vật tư kho (MVP). Quản lý bảng `materials` — nguồn cho dropdown vật tư ở
// toàn bộ module Kho (phiếu nhập/xuất, tồn, kiểm kê, báo cáo). Mã (GY###/VT###) tự sinh.
// Gate `dm_giay_vat_tu`. Chỉ dùng field model sẵn có → không migration.
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  ApiError, api, assetUrl,
  type MaterialRow, type MaterialInput, type KhoMaterialOption,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { Select } from "../components/Select";
import { InfoHint } from "../components/InfoHint";
import { exportXlsx } from "../lib/xlsxImport";
import { MATERIAL_TYPES, TYPE_LABEL, MATERIAL_HEADERS, downloadMaterialTemplate, parseMaterialFile } from "../lib/materialsXlsx";
import "./master-data.css";

const MODULE = "dm_giay_vat_tu";

/** Danh mục vật tư. Nhúng trong 1 kho (`warehouseId`) → chỉ hiện vật tư của kho đó,
 *  tạo mới cũng gán vào kho đó. `embedded` = bỏ header trang (đang là tab bên trong). */
export function MaterialsCatalogPage({ warehouseId = null, embedded = false, onChanged }: {
  warehouseId?: number | null;
  embedded?: boolean;
  onChanged?: () => void;
} = {}) {
  const { token } = useAuth();
  const can = useCan();
  // Thủ kho (kho:create) cũng được tạo/sửa vật tư — khớp gate của API materials.
  const canCreate = can(MODULE, "create") || can("kho", "create");
  const canUpdate = can(MODULE, "update") || can("kho", "create");

  const [rows, setRows] = useState<MaterialRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [q, setQ] = useState("");
  const [typeF, setTypeF] = useState("");
  const [activeF, setActiveF] = useState(""); // ""=tất cả, "1"=hoạt động, "0"=đã ẩn
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);

  const [editing, setEditing] = useState<MaterialRow | null | "new">(null); // "new"=tạo mới
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importResult, setImportResult] = useState<{ ok: number; errs: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.materials
      .list(token, {
        q: q.trim() || undefined,
        material_type: typeF || undefined,
        is_active: activeF === "" ? undefined : activeF === "1",
        warehouse_id: warehouseId ?? undefined,
        page,
        size,
      })
      .then((r) => { setRows(r.items); setTotal(r.total); })
      .catch((e) => {
        if (e instanceof ApiError && e.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục vật tư.");
      })
      .finally(() => setLoading(false));
  }, [token, q, typeF, activeF, warehouseId, page, size]);

  useEffect(() => { load(); }, [load]);

  // Tải file mẫu Excel (.xlsx) — đủ cột như form + dòng ví dụ (dùng chung với Import tồn).
  function downloadTemplate() {
    downloadMaterialTemplate("mau-nhap-vat-tu.xlsx");
  }

  // Xuất Excel toàn bộ vật tư (theo bộ lọc hiện tại) — cột trùng mẫu import để có thể sửa & import lại.
  // Backend giới hạn size ≤ 200 → tải lần lượt từng trang 200 rồi gộp.
  async function exportMaterials() {
    if (!token) return;
    setExporting(true); setError(null);
    try {
      const PAGE = 200;
      const all: MaterialRow[] = [];
      for (let page = 1; page <= 200; page++) { // trần 40.000 dòng, phòng vòng lặp vô hạn
        const res = await api.materials.list(token, {
          q: q.trim() || undefined,
          material_type: typeF || undefined,
          is_active: activeF === "" ? undefined : activeF === "1",
          warehouse_id: warehouseId ?? undefined,
          page, size: PAGE,
        });
        all.push(...res.items);
        if (res.items.length < PAGE || all.length >= res.total) break;
      }
      // Ngưỡng tồn (min_levels) theo kho — để điền 2 cột Tồn tối thiểu / Tồn báo sớm.
      const levelMap = new Map<number, { min: number; near: number }>();
      if (warehouseId != null) {
        try {
          const lv = await api.kho.listMinLevels(token, warehouseId);
          for (const x of lv.items) levelMap.set(x.material_id, { min: x.min_qty, near: x.near_min_qty });
        } catch { /* thiếu quyền/không tải được → để trống ngưỡng */ }
      }
      const rows = all.map((m) => {
        const lv = levelMap.get(m.id);
        return [
          m.code, m.name, TYPE_LABEL[m.material_type] ?? m.material_type, m.unit,
          m.group_name ?? "", m.default_supplier ?? "",
          m.purchase_uom ?? "", m.consumption_uom ?? "", m.spec_text ?? "",
          (m.uoms ?? []).map((u) => `${u.uom}=${u.factor}`).join("; "),
          m.paper_family ?? "", m.width_cm ?? "", m.height_cm ?? "", m.gsm ?? "", m.thickness_mm ?? "",
          m.note ?? "", lv && lv.min > 0 ? lv.min : "", lv && lv.near > 0 ? lv.near : "",
          m.is_active ? "Hoạt động" : "Đã ẩn",
        ];
      });
      exportXlsx("danh-muc-vat-tu.xlsx", MATERIAL_HEADERS, rows, "VatTu");
    } catch (e) {
      setError(e instanceof ApiError ? `Xuất Excel thất bại: ${e.message}` : "Xuất Excel thất bại.");
    } finally {
      setExporting(false);
    }
  }

  // Import file Excel (.xlsx / .xls / .csv): đọc đủ cột (dùng chung parseMaterialFile) → tạo từng vật tư → tổng kết.
  async function handleImport(file: File) {
    if (!token) return;
    setImporting(true); setImportResult(null); setError(null);
    try {
      const { rows, errs } = await parseMaterialFile(file, warehouseId ?? null);
      if (rows.length === 0 && errs.length === 0) { setError("File trống hoặc chưa có dòng dữ liệu."); setImporting(false); return; }
      // Có bất kỳ dòng lỗi → KHÔNG import gì cả (sửa hết lỗi rồi import lại).
      if (errs.length > 0) { setImportResult({ ok: 0, errs }); setImporting(false); return; }
      // Mọi dòng hợp lệ → tạo tất cả.
      let ok = 0; const createErrs: string[] = [];
      for (const p of rows) {
        try {
          const saved = await api.materials.create(token, p.payload); ok++;
          // Ngưỡng tồn / tồn báo sớm (nếu có trong file) → ghi vào min_levels của kho vật tư.
          const wh = saved.warehouse_id ?? warehouseId;
          if ((p.minQty != null || p.nearQty != null) && wh != null) {
            await api.kho.upsertMinLevel(token, { material_id: saved.id, warehouse_id: wh, min_qty: p.minQty ?? 0, near_min_qty: p.nearQty ?? 0 });
          }
        } catch (e) { createErrs.push(`Dòng ${p.rowNum} (${p.name}): ${e instanceof ApiError ? e.message : "lỗi"}`); }
      }
      setImportResult({ ok, errs: createErrs });
      if (ok > 0) { load(); onChanged?.(); }
    } catch {
      setError("Không đọc được file. Hãy dùng đúng file mẫu (.xlsx).");
    } finally {
      setImporting(false);
    }
  }

  const pages = Math.max(1, Math.ceil(total / size));

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">Bạn không có quyền truy cập Danh mục vật tư (403).</div>
      </main>
    );
  }

  const Shell = embedded ? "div" : "main";
  return (
    <Shell className={embedded ? "" : "md-page"}>
      {!embedded && (
        <header className="md-page__head">
          <p className="eyebrow">Cấu hình danh mục</p>
          <h1 className="md-page__title">Danh mục vật tư kho</h1>
          <p className="md-page__sub">
            Khai báo vật tư dùng trong Kho (nhập/xuất, tồn). Mã tự sinh: <strong>GY###</strong> cho giấy,
            <strong> VT###</strong> cho vật tư khác. Vật tư <strong>đã ẩn</strong> sẽ không còn xuất hiện ở các phiếu kho.
          </p>
        </header>
      )}

      <div className="md-page__toolbar">
        <input className="input" placeholder="Tìm mã / tên vật tư…" value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }} style={{ minWidth: 240 }} />
        <select className="input" style={{ width: 170 }} value={typeF}
          onChange={(e) => { setTypeF(e.target.value); setPage(1); }}>
          <option value="">— Tất cả loại —</option>
          {MATERIAL_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <select className="input" style={{ width: 150 }} value={activeF}
          onChange={(e) => { setActiveF(e.target.value); setPage(1); }}>
          <option value="">— Tất cả —</option>
          <option value="1">Đang hoạt động</option>
          <option value="0">Đã ẩn</option>
        </select>
        <div className="md-page__toolbar-spacer" />
        <span className="md-page__muted">{total} vật tư</span>
        <Button variant="ghost" loading={exporting} onClick={exportMaterials}>⭱ Xuất Excel</Button>
        {canCreate && (
          <>
            <Button variant="ghost" onClick={downloadTemplate}>⭳ Tải mẫu Excel</Button>
            <Button variant="ghost" loading={importing} onClick={() => fileRef.current?.click()}>⭱ Import Excel</Button>
            <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImport(f); e.target.value = ""; }} />
            <Button variant="primary" onClick={() => setEditing("new")}>+ Thêm vật tư</Button>
          </>
        )}
      </div>

      {importResult && (
        <div className="banner" role="status" style={{ background: importResult.errs.length ? "#fdf6e3" : "#dcecdc", color: importResult.errs.length ? "#8a5a00" : "#244a2e", border: "1px solid rgba(0,0,0,.08)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>✓ Đã nhập <b>{importResult.ok}</b> vật tư{importResult.errs.length ? `, ${importResult.errs.length} dòng lỗi` : ""}.</span>
            <div className="md-page__toolbar-spacer" />
            <button type="button" onClick={() => setImportResult(null)} style={{ background: "none", border: "none", cursor: "pointer" }}>✕</button>
          </div>
          {importResult.errs.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 140, overflowY: "auto", fontSize: 13 }}>
              {importResult.errs.slice(0, 30).map((m, i) => <li key={i}>{m}</li>)}
              {importResult.errs.length > 30 && <li>… và {importResult.errs.length - 30} dòng nữa</li>}
            </ul>
          )}
        </div>
      )}

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap md-page__tablewrap--scroll">
        <table className="md-page__table">
          <thead>
            <tr><th>Mã</th><th>Tên vật tư</th><th>Loại</th><th>Đơn vị</th><th>NCC mặc định</th><th>Trạng thái</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="md-page__status">Đang tải...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6} className="md-page__empty">{q || typeF || activeF ? "Không có vật tư khớp bộ lọc." : "Chưa có vật tư nào."}</td></tr>
            ) : rows.map((m) => (
              <tr key={m.id} className="md-page__row" onClick={() => setEditing(m)}>
                <td className="md-page__mono">{m.code}</td>
                <td>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    {assetUrl(m.image_url) && (
                      <img src={assetUrl(m.image_url)!} alt="" width={28} height={28}
                        style={{ borderRadius: 4, objectFit: "cover", border: "1px solid var(--rule)" }} />
                    )}
                    <strong>{m.name}</strong>
                  </span>
                </td>
                <td>{TYPE_LABEL[m.material_type] ?? m.material_type}</td>
                <td>{m.unit}{m.purchase_uom && m.purchase_uom !== m.unit ? <span className="md-page__muted"> · mua: {m.purchase_uom}</span> : null}</td>
                <td>{m.default_supplier || <span className="md-page__muted">—</span>}</td>
                <td><span className={`md-page__status-badge ${m.is_active ? "is-active" : "is-inactive"}`}>{m.is_active ? "Hoạt động" : "Đã ẩn"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="md-page__pager" style={{ marginTop: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="md-page__muted">Hiển thị</span>
          <select className="input" style={{ width: 72 }} value={size}
            onChange={(e) => { setSize(Number(e.target.value)); setPage(1); }}>
            {[20, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <span className="md-page__muted">dòng · Trang {Math.min(page, pages)}/{pages}</span>
        </div>
        {pages > 1 && (
          <div className="md-page__pager-btns">
            <Button variant="ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>‹ Trước</Button>
            <Button variant="ghost" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages}>Sau ›</Button>
          </div>
        )}
      </div>

      {editing && (
        <MaterialForm
          material={editing === "new" ? null : editing}
          canUpdate={canUpdate}
          defaultWarehouseId={warehouseId}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); onChanged?.(); }}
        />
      )}
    </Shell>
  );
}

type UomRow = { uom: string; factor: string };
type FormTab = "chung" | "thuoctinh";

// Form Thêm / Sửa vật tư — chia 2 tab (Thông tin chung / Thuộc tính) như BRAVO.
// Tab "chung" có ảnh đại diện; tab "thuộc tính" có bảng đơn vị tính quy đổi nhiều dòng.
// Dùng lại làm popup "Tạo mặt hàng" ở phiếu kho (defaultType/defaultName để điền sẵn).
export function MaterialForm({
  material, canUpdate, defaultName = "", defaultType, defaultWarehouseId = null, onClose, onSaved,
  pickList, onPickExisting, onEditExisting, allowCreate = true,
}: {
  material: MaterialRow | null;
  canUpdate: boolean;
  defaultName?: string;
  defaultType?: string;
  /** Kho quản lý gán cho vật tư TẠO MỚI (khi mở từ tab Danh mục của một kho). */
  defaultWarehouseId?: number | null;
  onClose: () => void;
  onSaved: (created?: MaterialRow) => void;
  // Dùng ở phiếu kho: ô "Tìm hàng đã có" đầu form để CHỌN LẠI (tránh tạo trùng).
  pickList?: KhoMaterialOption[];
  onPickExisting?: (m: KhoMaterialOption) => void;
  onEditExisting?: (id: number) => void;
  allowCreate?: boolean; // false (phiếu xuất) → chỉ chọn, ẩn phần tạo mới
}) {
  const { token } = useAuth();
  const isNew = material == null;
  const readOnly = !isNew && !canUpdate;
  const fileRef = useRef<HTMLInputElement | null>(null);
  const inVoucher = !!onPickExisting;
  const pickOnly = inVoucher && !allowCreate;
  const [pickQ, setPickQ] = useState(defaultName);
  const pickKw = pickQ.trim().toLowerCase();
  const pickMatches = (pickList ?? []).filter((m) =>
    !pickKw || m.code.toLowerCase().includes(pickKw) || m.name.toLowerCase().includes(pickKw),
  ).slice(0, pickOnly ? 200 : 12);

  const [tab, setTab] = useState<FormTab>("chung");
  const [code, setCode] = useState(material?.code ?? "");
  const [name, setName] = useState(material?.name ?? defaultName);
  const [type, setType] = useState(material?.material_type ?? defaultType ?? "paper");
  const [unit, setUnit] = useState(material?.unit ?? "");
  const [supplier, setSupplier] = useState(material?.default_supplier ?? "");
  const [supplierOpts, setSupplierOpts] = useState<{ id: number; name: string }[]>([]); // gợi ý NCC từ danh mục
  const [imageUrl, setImageUrl] = useState<string | null>(material?.image_url ?? null);
  const [uploadingImg, setUploadingImg] = useState(false);
  const [paperFamily, setPaperFamily] = useState(material?.paper_family ?? "");
  const [width, setWidth] = useState(material?.width_cm != null ? String(material.width_cm) : "");
  const [height, setHeight] = useState(material?.height_cm != null ? String(material.height_cm) : "");
  const [gsm, setGsm] = useState(material?.gsm != null ? String(material.gsm) : "");
  const [thickness, setThickness] = useState(material?.thickness_mm != null ? String(material.thickness_mm) : "");
  const [uoms, setUoms] = useState<UomRow[]>(
    (material?.uoms ?? []).map((u) => ({ uom: u.uom, factor: String(u.factor) })),
  );
  const [isActive, setIsActive] = useState(material?.is_active ?? true);
  // BRD §3.4
  const [groupName, setGroupName] = useState(material?.group_name ?? "");
  const [purchaseUom, setPurchaseUom] = useState(material?.purchase_uom ?? "");
  const [consumptionUom, setConsumptionUom] = useState(material?.consumption_uom ?? "");
  const [specText, setSpecText] = useState(material?.spec_text ?? "");
  const [note, setNote] = useState(material?.note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Ngưỡng tồn (dùng chung bảng min_levels với tab Báo cáo & cột "Ngưỡng tồn" ở Tồn kho).
  const levelWh = material?.warehouse_id ?? defaultWarehouseId; // kho để đặt ngưỡng
  const showLevel = !inVoucher && levelWh != null; // chỉ ở form Danh mục (không ở quick-create của phiếu)
  const [minStock, setMinStock] = useState("");
  const [nearStock, setNearStock] = useState("");
  const [levelId, setLevelId] = useState<number | null>(null); // id bản ghi ngưỡng hiện có

  const isPaper = type === "paper";
  const num = (v: string): number | null => (v.trim() === "" ? null : Number(v));

  // Nạp ngưỡng tồn hiện có của vật tư (khi sửa) từ min_levels của kho.
  useEffect(() => {
    if (!token || isNew || !material || levelWh == null) return;
    api.kho.listMinLevels(token, levelWh).then((r) => {
      const lv = r.items.find((x) => x.material_id === material.id);
      if (lv) {
        setLevelId(lv.id);
        setMinStock(lv.min_qty ? String(lv.min_qty) : "");
        setNearStock(lv.near_min_qty ? String(lv.near_min_qty) : "");
      }
    }).catch(() => {});
  }, [token, isNew, material, levelWh]);

  // Gợi ý NCC từ danh mục Nhà cung cấp (gated kho:read → thủ kho dùng được). Vẫn cho gõ tên lạ.
  useEffect(() => {
    if (!token) return;
    api.kho.partnerOptions(token, "ncc").then(setSupplierOpts).catch(() => setSupplierOpts([]));
  }, [token]);

  function addUom() { setUoms((r) => [...r, { uom: "", factor: "" }]); }
  function setUomAt(i: number, patch: Partial<UomRow>) {
    setUoms((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function removeUom(i: number) { setUoms((r) => r.filter((_, idx) => idx !== i)); }

  async function onPickImage(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // cho phép chọn lại cùng file
    if (!file || !token) return;
    setError(null);
    setUploadingImg(true);
    try {
      const { image_url } = await api.materials.uploadImage(token, file);
      setImageUrl(image_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Tải ảnh thất bại.");
    } finally {
      setUploadingImg(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    if (!name.trim()) { setTab("chung"); return setError("Nhập tên vật tư."); }
    if (!unit.trim()) { setTab("chung"); return setError("Nhập đơn vị tính."); }
    if (isPaper && !paperFamily.trim()) { setTab("thuoctinh"); return setError("Vật tư là Giấy cần điền Họ giấy."); }
    if (showLevel) {
      const mn = Number(minStock) || 0, nr = Number(nearStock) || 0;
      if (nr > 0 && mn > 0 && nr <= mn) { setTab("chung"); return setError("Tồn báo sớm phải lớn hơn Tồn tối thiểu."); }
    }
    // Đơn vị quy đổi: bỏ dòng trống; dòng có tên thì hệ số phải > 0.
    const cleanUoms = [] as { uom: string; factor: number }[];
    for (const r of uoms) {
      if (!r.uom.trim()) continue;
      const f = Number(r.factor);
      if (!f || Number.isNaN(f) || f <= 0) { setTab("thuoctinh"); return setError(`Hệ số quy đổi của "${r.uom}" phải lớn hơn 0.`); }
      cleanUoms.push({ uom: r.uom.trim(), factor: f });
    }

    const payload: MaterialInput = {
      code: code.trim() || null,
      name: name.trim(),
      material_type: type,
      // Kho quản lý: sửa → giữ kho cũ; tạo mới từ tab Danh mục của 1 kho → gán kho đó.
      warehouse_id: material?.warehouse_id ?? defaultWarehouseId,
      unit: unit.trim(),
      default_supplier: supplier.trim() || null,
      image_url: imageUrl,
      paper_family: isPaper ? paperFamily.trim() || null : null,
      width_cm: isPaper ? num(width) : null,
      height_cm: isPaper ? num(height) : null,
      gsm: isPaper ? num(gsm) : null,
      thickness_mm: num(thickness),
      // Phí tối thiểu đã bỏ khỏi form (thuộc bảng giá, không liên quan kho) — giữ giá trị cũ.
      min_fee: material?.min_fee ?? 0,
      // BRD §3.4
      group_name: groupName.trim() || null,
      purchase_uom: purchaseUom.trim() || null,
      consumption_uom: consumptionUom.trim() || null,
      spec_text: specText.trim() || null,
      note: note.trim() || null,
      // Theo dõi lô/HSD đã bỏ khỏi form — giữ nguyên giá trị cũ trong DB (null nếu tạo mới).
      lot_code: material?.lot_code ?? null,
      track_lot: material?.track_lot ?? false,
      expiry_date: material?.expiry_date ?? null,
      track_expiry: material?.track_expiry ?? false,
      track_qr: material?.track_qr ?? false,
      track_value: material?.track_value ?? true,
      // Ngưỡng tồn đã bỏ khỏi form (không nối cảnh báo nào) — giữ nguyên giá trị cũ trong DB.
      min_stock: material?.min_stock ?? null,
      max_stock: material?.max_stock ?? null,
      // Field đã bỏ khỏi form — giữ nguyên giá trị cũ trong DB.
      default_waste_pct: material?.default_waste_pct ?? 0,
      min_purchase_qty: material?.min_purchase_qty ?? 0,
      uoms: cleanUoms,
      is_active: isActive,
    };

    setSaving(true);
    try {
      const saved = isNew
        ? await api.materials.create(token, payload)
        : await api.materials.update(token, material!.id, payload);
      // Ghi ngưỡng tồn vào min_levels theo kho của vật tư (sau khi lưu vật tư).
      const wh = saved.warehouse_id ?? levelWh;
      if (showLevel && wh != null) {
        const mn = Number(minStock) || 0, nr = Number(nearStock) || 0;
        try {
          if (mn > 0 || nr > 0) await api.kho.upsertMinLevel(token, { material_id: saved.id, warehouse_id: wh, min_qty: mn, near_min_qty: nr });
          else if (levelId != null) await api.kho.deleteMinLevel(token, levelId);
        } catch { /* lỗi ngưỡng không chặn việc lưu vật tư; có thể đặt lại ở tab Báo cáo */ }
      }
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu vật tư thất bại.");
      setSaving(false);
    }
  }

  const TABS: [FormTab, string][] = [["chung", "Thông tin chung"], ["thuoctinh", "Thuộc tính"]];
  const imgSrc = assetUrl(imageUrl);

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 960, width: "96%", maxHeight: "92vh", ...(pickOnly ? { height: "80vh" } : {}), display: "flex", flexDirection: "column" }}>
        <div className="md-page__dialog-head">
          <h2>{!isNew ? `Sửa vật tư · ${material!.code}` : pickOnly ? "Chọn mặt hàng" : "Thêm vật tư"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit} style={{ overflowY: pickOnly ? "hidden" : "auto", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
          {/* Ô tìm hàng đã có (chỉ ở phiếu, khi tạo mới) — chọn để DÙNG LẠI, tránh tạo trùng. */}
          {inVoucher && isNew && (
            <div style={{ marginBottom: pickOnly ? 0 : 14, ...(pickOnly ? { display: "flex", flexDirection: "column", flex: 1, minHeight: 0 } : {}) }}>
              <span className="field__label">Tìm hàng đã có (chọn để dùng lại)</span>
              <div style={{ position: "relative", ...(pickOnly ? { display: "flex", flexDirection: "column", flex: 1, minHeight: 0 } : {}) }}>
              <input className="input" autoFocus value={pickQ} onChange={(e) => setPickQ(e.target.value)}
                placeholder="Gõ mã / tên để tìm mặt hàng đã có…" />
              {(pickKw || pickOnly) && (
                <div className="card" style={pickOnly
                  ? { marginTop: 8, flex: 1, minHeight: 0, overflowY: "auto", padding: 4 }
                  : { position: "absolute", zIndex: 30, top: "calc(100% + 4px)", left: 0, right: 0, maxHeight: 280, overflowY: "auto", padding: 4, boxShadow: "0 8px 24px rgba(0,0,0,.18)" }}>
                  {pickMatches.length === 0 ? (
                    <div className="md-page__muted" style={{ padding: "8px 10px", fontSize: 13 }}>
                      Không thấy hàng khớp.{allowCreate ? " Điền form bên dưới để tạo mới." : " Vật tư mới thêm ở trang Kho → Danh mục vật tư."}
                    </div>
                  ) : pickMatches.map((m) => (
                    <div key={m.id} className="md-page__row" style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", cursor: "pointer" }}
                      onClick={() => onPickExisting!(m)}>
                      <span className="md-page__mono" style={{ width: 80, fontSize: 12 }}>{m.code}</span>
                      <span style={{ flex: 1 }}>{m.name}</span>
                      <span className="md-page__muted" style={{ fontSize: 12 }}>{m.unit}</span>
                      {onEditExisting && (
                        <button type="button" onClick={(e) => { e.stopPropagation(); onEditExisting(m.id); }}
                          style={{ background: "none", border: "none", color: "var(--rust)", cursor: "pointer", fontSize: 12 }}>Sửa</button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              </div>
              {allowCreate && <p className="md-page__muted" style={{ fontSize: 12, margin: "8px 0 0" }}>Không có trong danh sách? Điền form bên dưới để <strong>tạo mới</strong>.</p>}
            </div>
          )}

          {/* Tab bar — ẩn khi chỉ để chọn (phiếu xuất) */}
          {!pickOnly && (<>
          <div style={{ display: "flex", gap: 20, borderBottom: "1px solid var(--rule)", marginBottom: 14 }}>
            {TABS.map(([k, label]) => (
              <button key={k} type="button" onClick={() => setTab(k)}
                style={{ padding: "8px 2px", background: "none", border: "none", cursor: "pointer", fontSize: 14,
                  borderBottom: tab === k ? "2px solid var(--rust)" : "2px solid transparent",
                  fontWeight: tab === k ? 700 : 500, color: tab === k ? "var(--ink)" : "var(--ash)" }}>
                {label}
              </button>
            ))}
          </div>

          {tab === "chung" && (
            <div style={{ display: "flex", gap: 18 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="md-page__form-grid">
                  <div className="field">
                    <span className="field__label">Loại vật tư *</span>
                    <Select portal disabled={readOnly} value={type}
                      options={MATERIAL_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                      onChange={(v) => setType((v as string) ?? "vat_tu")} />
                  </div>
                  <label className="field">
                    <span className="field__label">Đơn vị tính (gốc) *</span>
                    <input className="input" placeholder="tờ / kg / m2 / cái…" value={unit}
                      onChange={(e) => setUnit(e.target.value)} disabled={readOnly} />
                  </label>
                  <label className="field md-page__form-wide">
                    <span className="field__label">Tên vật tư *</span>
                    <input className="input" value={name} onChange={(e) => setName(e.target.value)} disabled={readOnly}
                      placeholder="VD: Couche 150gsm 65x86" />
                  </label>
                  <label className="field">
                    <span className="field__label">Nhóm hàng</span>
                    <input className="input" placeholder="VD: Vật tư in / Bao bì…" value={groupName}
                      onChange={(e) => setGroupName(e.target.value)} disabled={readOnly} />
                  </label>
                  <label className="field">
                    <span className="field__label">Nhà cung cấp mặc định</span>
                    <input className="input" list="mat-supplier-dl" placeholder="Chọn từ danh mục hoặc gõ"
                      value={supplier} onChange={(e) => setSupplier(e.target.value)} disabled={readOnly} />
                    <datalist id="mat-supplier-dl">
                      {supplierOpts.map((s) => <option key={s.id} value={s.name} />)}
                    </datalist>
                  </label>
                  <label className="field md-page__form-wide">
                    <span className="field__label">Ghi chú</span>
                    <input className="input" value={note} onChange={(e) => setNote(e.target.value)} disabled={readOnly} />
                  </label>
                  {showLevel && (
                    <>
                      <label className="field">
                        <span className="field__label">Tồn tối thiểu <InfoHint label="Tồn xuống dưới mức này = Thiếu hàng (đỏ), cần nhập bổ sung. Dùng chung với tab Báo cáo & cột Ngưỡng tồn ở Tồn kho." /></span>
                        <input className="input" type="number" min={0} step="0.001" placeholder="VD: 100"
                          value={minStock} onChange={(e) => setMinStock(e.target.value)} disabled={readOnly} />
                      </label>
                      <label className="field">
                        <span className="field__label">Tồn báo sớm <InfoHint label="Còn trên mức tối thiểu nhưng dưới mức này = Sắp hết (vàng). Để trống nếu không dùng." /></span>
                        <input className="input" type="number" min={0} step="0.001" placeholder="VD: 150 (tùy chọn)"
                          value={nearStock} onChange={(e) => setNearStock(e.target.value)} disabled={readOnly} />
                      </label>
                    </>
                  )}
                  <label className="field">
                    <span className="field__label">Mã vật tư {isNew && <InfoHint label="Bỏ trống mã để hệ thống tự sinh theo loại. Nhập mã riêng thì mã phải chưa tồn tại." />}</span>
                    <input className="input md-page__mono" value={code} onChange={(e) => setCode(e.target.value)} disabled={readOnly}
                      placeholder={isNew ? "Để trống = tự sinh (GY###/VT###)" : ""} />
                  </label>
                  {!isNew && (
                    <label className="field md-page__form-wide" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                      <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} disabled={!canUpdate} />
                      <span className="field__label" style={{ margin: 0 }}>Đang hoạt động (bỏ tick = ẩn khỏi Kho)</span>
                    </label>
                  )}
                </div>
              </div>
              {/* Ảnh đại diện */}
              <div style={{ width: 150, flex: "none" }}>
                <span className="field__label">Ảnh đại diện</span>
                <div style={{ width: 150, height: 150, border: "1px dashed var(--rule)", borderRadius: 8,
                  display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
                  background: "var(--surface-2, #faf8f4)", marginTop: 4 }}>
                  {imgSrc
                    ? <img src={imgSrc} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    : <span className="md-page__muted" style={{ fontSize: 12 }}>Chưa có ảnh</span>}
                </div>
                {!readOnly && (
                  <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                    <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={onPickImage} />
                    <Button type="button" variant="ghost" onClick={() => fileRef.current?.click()} loading={uploadingImg}>
                      {imgSrc ? "Đổi ảnh" : "Tải ảnh"}
                    </Button>
                    {imgSrc && <Button type="button" variant="ghost" onClick={() => setImageUrl(null)}>Xóa</Button>}
                  </div>
                )}
                <p className="md-page__muted" style={{ fontSize: 11, marginTop: 6 }}>JPG/PNG/WebP ≤ 3 MB</p>
              </div>
            </div>
          )}

          {tab === "thuoctinh" && (
            <>
              <div className="md-page__form-grid">
                {isPaper && (
                  <>
                    <label className="field">
                      <span className="field__label">Họ giấy *</span>
                      <input className="input" placeholder="Couche / Ford / Bristol…" value={paperFamily}
                        onChange={(e) => setPaperFamily(e.target.value)} disabled={readOnly} />
                    </label>
                    <label className="field">
                      <span className="field__label">Định lượng (gsm)</span>
                      <input className="input" type="number" step="1" value={gsm}
                        onChange={(e) => setGsm(e.target.value)} disabled={readOnly} />
                    </label>
                    <label className="field">
                      <span className="field__label">Khổ rộng (cm)</span>
                      <input className="input" type="number" step="0.1" value={width}
                        onChange={(e) => setWidth(e.target.value)} disabled={readOnly} />
                    </label>
                    <label className="field">
                      <span className="field__label">Khổ cao/dài (cm)</span>
                      <input className="input" type="number" step="0.1" value={height}
                        onChange={(e) => setHeight(e.target.value)} disabled={readOnly} />
                    </label>
                  </>
                )}
                <label className="field">
                  <span className="field__label">Độ dày (mm)</span>
                  <input className="input" type="number" step="0.01" value={thickness}
                    onChange={(e) => setThickness(e.target.value)} disabled={readOnly} />
                </label>
                <label className="field">
                  <span className="field__label">Đơn vị mua</span>
                  <input className="input" placeholder="ream / thùng / cuộn…" value={purchaseUom}
                    onChange={(e) => setPurchaseUom(e.target.value)} disabled={readOnly} />
                </label>
                <label className="field">
                  <span className="field__label">Đơn vị xuất</span>
                  <input className="input" placeholder="tờ / cái…" value={consumptionUom}
                    onChange={(e) => setConsumptionUom(e.target.value)} disabled={readOnly} />
                </label>
                <label className="field md-page__form-wide">
                  <span className="field__label">Quy cách {isPaper && <InfoHint label="Quy ước khổ giấy: cạnh ngắn viết trước (Rộng ≤ Cao)." />}</span>
                  <input className="input" placeholder="Khổ / định lượng / màu / kích thước…" value={specText}
                    onChange={(e) => setSpecText(e.target.value)} disabled={readOnly} />
                </label>
              </div>

              {/* Đơn vị tính quy đổi — mỗi dòng đọc như 1 câu: 1 [đv] = [hệ số] × [đv gốc] */}
              <div className="field__label" style={{ marginBottom: 6 }}>
                Đơn vị tính quy đổi <InfoHint label={`Khai các đơn vị lớn hơn đơn vị gốc "${unit || "…"}". VD: 1 ream = 500 tờ.`} />
              </div>
              {uoms.length === 0 ? (
                <div className="md-page__uom-empty">
                  Chưa có đơn vị quy đổi. Đơn vị gốc hiện tại: <strong>{unit || "chưa đặt"}</strong>.
                </div>
              ) : (
                <div className="md-page__uom-list">
                  {uoms.map((r, i) => (
                    <div className="md-page__uom-row" key={i}>
                      <span className="md-page__uom-lead">1</span>
                      <input className="input" placeholder="ream / kg / thùng…" value={r.uom}
                        onChange={(e) => setUomAt(i, { uom: e.target.value })} disabled={readOnly} />
                      <span className="md-page__uom-op">=</span>
                      <input className="input md-page__uom-factor" type="number" step="0.0001" placeholder="500" value={r.factor}
                        onChange={(e) => setUomAt(i, { factor: e.target.value })} disabled={readOnly} />
                      <span className="md-page__uom-base">× {unit || "ĐV gốc"}</span>
                      {!readOnly && (
                        <button type="button" className="md-page__uom-del" title="Xóa dòng"
                          onClick={() => removeUom(i)}>✕</button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {!readOnly && (
                <button type="button" className="md-page__uom-add" onClick={addUom}>+ Thêm đơn vị</button>
              )}
            </>
          )}

          </>)}

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>{readOnly || pickOnly ? "Đóng" : "Hủy"}</Button>
            {!readOnly && !pickOnly && (
              <Button type="submit" variant="primary" loading={saving}>{isNew ? "Thêm vật tư" : "Lưu thay đổi"}</Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
