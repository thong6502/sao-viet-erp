import { useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import {
  ApiError,
  api,
  type PaperSizeRow,
  type PaperSizeInput,
  type PaperSizeGroup,
  type MachineRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const SIZE_GROUPS: { value: PaperSizeGroup; label: string }[] = [
  { value: "cong_nghiep", label: "Khổ công nghiệp" },
  { value: "kho_a", label: "Khổ A" },
  { value: "kho_cat", label: "Khổ cắt" },
  { value: "custom", label: "Tùy chỉnh" },
];
// Bộ lọc "Loại khổ" theo mã tóm tắt size_type (derived từ 3 boolean ở backend).
const SIZE_TYPE_FILTERS = [
  { value: "mua", label: "Khổ mua" },
  { value: "in", label: "Khổ tờ in" },
  { value: "ca_hai", label: "Mua + tờ in" },
  { value: "cat", label: "Khổ cắt" },
];

function loaiKhoParts(row: PaperSizeRow): string[] {
  const parts: string[] = [];
  if (row.is_purchase_size) parts.push("Khổ mua");
  if (row.is_print_sheet_size) parts.push("Khổ tờ in");
  if (row.is_cut_size) parts.push("Khổ cắt");
  return parts.length ? parts : ["—"];
}

function num(v: string): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

// Số con hình học — cùng công thức pricing_engine (usable = khổ − nhíp − 2×xén; con = TP + 2×bleed + gutter).
function computePieces(
  sw: number, sh: number, gripper: number, edge: number,
  fw: number, fh: number, bleed: number, gutter: number, allowRotate: boolean,
) {
  const usableW = sw - gripper - 2 * edge;
  const usableH = sh - 2 * edge;
  const pw = fw + 2 * bleed + gutter;
  const ph = fh + 2 * bleed + gutter;
  if (usableW <= 0 || usableH <= 0 || pw <= 0 || ph <= 0) {
    return { usableW, usableH, straight: 0, rotated: 0, best: 0, overSize: sw > 0 && (fw > usableW && fh > usableH) };
  }
  const straight = Math.floor(usableW / pw) * Math.floor(usableH / ph);
  const rotated = Math.floor(usableW / ph) * Math.floor(usableH / pw);
  const best = allowRotate ? Math.max(straight, rotated) : straight;
  return { usableW, usableH, straight, rotated, best, overSize: best === 0 };
}

export function PaperSizesCatalogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<PaperSizeRow[]>([]);
  const [machines, setMachines] = useState<MachineRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // filters
  const [q, setQ] = useState("");
  const [groupF, setGroupF] = useState("");
  const [typeF, setTypeF] = useState("");
  const [machineF, setMachineF] = useState("");
  const [activeF, setActiveF] = useState("");
  const [currentOnly, setCurrentOnly] = useState(true);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<PaperSizeRow | null>(null);
  const [deleting, setDeleting] = useState<PaperSizeRow | null>(null);
  const [historyOf, setHistoryOf] = useState<PaperSizeRow | null>(null);

  const machineName = useCallback(
    (id: number) => machines.find((m) => m.id === id)?.name ?? `#${id}`,
    [machines],
  );

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.paperSizes
      .list(token, {
        q: q || undefined,
        size_group: groupF || undefined,
        size_type: typeF || undefined,
        machine_id: machineF ? Number(machineF) : undefined,
        is_active: activeF === "" ? undefined : activeF === "active",
        current_only: currentOnly,
        size: 200,
      })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục khổ giấy.");
      })
      .finally(() => setLoading(false));
  }, [token, q, groupF, typeF, machineF, activeF, currentOnly]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!token) return;
    api.machines.list(token, { size: 200 }).then((r) => setMachines(r.items)).catch(() => {});
  }, [token]);

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.paperSizes.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không xóa được khổ giấy.");
      setDeleting(null);
    }
  }

  async function handleClone(row: PaperSizeRow) {
    if (!token) return;
    try {
      await api.paperSizes.clone(token, row.id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không sao chép được.");
    }
  }

  async function toggleActive(row: PaperSizeRow) {
    if (!token) return;
    try {
      await api.paperSizes.update(token, row.id, { ...rowToInput(row), is_active: !row.is_active });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đổi được trạng thái.");
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Khổ giấy tiêu chuẩn (403).
        </div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Khổ giấy tiêu chuẩn</h1>
        <p className="md-page__sub">
          Danh mục kích thước tờ giấy — chọn khổ tờ in khi tính giá, tính số con trên tờ, quy đổi tiền giấy.
        </p>
      </header>

      <div className="md-page__toolbar">
        <input
          className="input md-page__filter"
          placeholder="Tìm theo mã / tên khổ…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ width: 220 }}
        />
        <div className="md-page__filter">
          <select className="input select" value={groupF} onChange={(e) => setGroupF(e.target.value)} aria-label="Lọc nhóm khổ">
            <option value="">-- Tất cả nhóm khổ --</option>
            {SIZE_GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </div>
        <div className="md-page__filter">
          <select className="input select" value={typeF} onChange={(e) => setTypeF(e.target.value)} aria-label="Lọc loại khổ">
            <option value="">-- Tất cả loại khổ --</option>
            {SIZE_TYPE_FILTERS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div className="md-page__filter">
          <select className="input select" value={machineF} onChange={(e) => setMachineF(e.target.value)} aria-label="Lọc máy phù hợp">
            <option value="">-- Tất cả máy --</option>
            {machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>
        <div className="md-page__filter">
          <select className="input select" value={activeF} onChange={(e) => setActiveF(e.target.value)} aria-label="Lọc trạng thái">
            <option value="">-- Trạng thái --</option>
            <option value="active">Đang dùng</option>
            <option value="inactive">Tạm ngưng</option>
          </select>
        </div>
        <div className="md-page__toggle-wrap" style={{ padding: "0 8px" }}>
          <input type="checkbox" id="ps-current-only" checked={currentOnly} onChange={(e) => setCurrentOnly(e.target.checked)} />
          <label htmlFor="ps-current-only">Chỉ bản hiện hành</label>
        </div>
        <div className="md-page__toolbar-spacer" />
        <Button variant="primary" onClick={() => { setEditing(null); setMode("create"); }}>
          + Tạo khổ giấy
        </Button>
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={() => { setError(null); load(); }}>Tải lại</button>
        </div>
      )}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Tên khổ</th>
              <th>Rộng (cm)</th>
              <th>Cao (cm)</th>
              <th>Diện tích (m²)</th>
              <th>Loại khổ</th>
              <th>Máy phù hợp</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} className="md-page__status" role="status">Đang tải dữ liệu...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="md-page__empty">Chưa có khổ giấy nào.</td></tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="md-page__row">
                  <td className="md-page__mono">
                    {row.code}
                    {row.version > 1 && <span className="md-page__tag" style={{ marginLeft: 4 }}>v{row.version}</span>}
                  </td>
                  <td><strong>{row.name}</strong></td>
                  <td>{row.width_cm}</td>
                  <td>{row.height_cm}</td>
                  <td>{row.area_m2?.toFixed(4)}</td>
                  <td>
                    <div className="md-page__tag-group">
                      {loaiKhoParts(row).map((p) => <span key={p} className="md-page__tag-calc">{p}</span>)}
                    </div>
                  </td>
                  <td>
                    {!row.compatible_machine_ids || row.compatible_machine_ids.length === 0 ? (
                      <span className="md-page__muted">Mọi máy</span>
                    ) : (
                      <div className="md-page__tag-group">
                        {row.compatible_machine_ids.map((id) => <span key={id} className="md-page__tag-tech">{machineName(id)}</span>)}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                      {row.is_active ? "Đang dùng" : "Tạm ngưng"}
                    </span>
                  </td>
                  <td className="md-page__actions-col">
                    <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => { setEditing(row); setMode("edit"); }}>Sửa</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => handleClone(row)}>Sao chép</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setHistoryOf(row)}>Lịch sử</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => toggleActive(row)}>
                      {row.is_active ? "Ngưng" : "Bật"}
                    </button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => setDeleting(row)}>Xóa</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {mode && (
        <PaperSizeFormDialog
          existing={editing}
          machines={machines}
          allSizes={rows}
          onClose={() => { setMode(null); setEditing(null); }}
          onSaved={() => { setMode(null); setEditing(null); load(); }}
        />
      )}

      {historyOf && (
        <HistoryDialog row={historyOf} onClose={() => setHistoryOf(null)} />
      )}

      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head"><h2>Xác nhận xóa</h2></div>
            <div className="md-page__dialog-body">
              <p>Xóa khổ giấy <strong>{deleting.name}</strong> ({deleting.code})? Khổ đã dùng trong phiếu sẽ không xóa được — hãy Ngưng dùng.</p>
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

// Reconstruct a full input payload from a row (for quick toggle / prefill).
function rowToInput(row: PaperSizeRow): PaperSizeInput {
  return {
    name: row.name,
    size_group: row.size_group as PaperSizeGroup,
    is_purchase_size: row.is_purchase_size,
    is_print_sheet_size: row.is_print_sheet_size,
    is_cut_size: row.is_cut_size,
    note: row.note,
    is_active: row.is_active,
    width_cm: row.width_cm,
    height_cm: row.height_cm,
    allow_rotation: row.allow_rotation,
    compatible_machine_ids: row.compatible_machine_ids,
    default_machine_id: row.default_machine_id,
    parent_size_id: row.parent_size_id,
    cut_count: row.cut_count,
    cut_waste_rate: row.cut_waste_rate,
  };
}

const sectionHead: CSSProperties = {
  margin: "18px 0 8px", fontSize: 13, fontWeight: 700, textTransform: "uppercase",
  letterSpacing: ".04em", color: "var(--text-muted, #64748b)",
};

function PaperSizeFormDialog({
  existing, machines, allSizes, onClose, onSaved,
}: {
  existing: PaperSizeRow | null;
  machines: MachineRow[];
  allSizes: PaperSizeRow[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [code, setCode] = useState(existing?.code ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [group, setGroup] = useState<PaperSizeGroup>((existing?.size_group as PaperSizeGroup) ?? "cong_nghiep");
  const [isPurchase, setIsPurchase] = useState(existing?.is_purchase_size ?? false);
  const [isPrint, setIsPrint] = useState(existing?.is_print_sheet_size ?? true);
  const [isCut, setIsCut] = useState(existing?.is_cut_size ?? false);
  const [note, setNote] = useState(existing?.note ?? "");
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [width, setWidth] = useState(existing ? String(existing.width_cm) : "");
  const [height, setHeight] = useState(existing ? String(existing.height_cm) : "");
  const [allowRotation, setAllowRotation] = useState(existing?.allow_rotation ?? true);

  const [machineIds, setMachineIds] = useState<number[]>(existing?.compatible_machine_ids ?? []);
  const [defaultMachine, setDefaultMachine] = useState<string>(existing?.default_machine_id ? String(existing.default_machine_id) : "");

  const [parentId, setParentId] = useState<string>(existing?.parent_size_id ? String(existing.parent_size_id) : "");
  const [cutCount, setCutCount] = useState(existing?.cut_count ? String(existing.cut_count) : "");
  const [cutWaste, setCutWaste] = useState(existing?.cut_waste_rate != null ? String(existing.cut_waste_rate) : "");
  const [effectiveFrom, setEffectiveFrom] = useState(existing?.effective_from ?? "");

  // Test số con inputs
  const [tGripper, setTGripper] = useState("1");
  const [tEdge, setTEdge] = useState("0.5");
  const [tFinW, setTFinW] = useState("21");
  const [tFinH, setTFinH] = useState("29.7");
  const [tBleed, setTBleed] = useState("0.3");
  const [tGutter, setTGutter] = useState("0");

  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const w = num(width), h = num(height);
  const area = w > 0 && h > 0 ? (w * h) / 10000 : 0;

  const pieces = useMemo(
    () => computePieces(w, h, num(tGripper), num(tEdge), num(tFinW), num(tFinH), num(tBleed), num(tGutter), allowRotation),
    [w, h, tGripper, tEdge, tFinW, tFinH, tBleed, tGutter, allowRotation],
  );

  // Máy vượt khổ (cảnh báo tại chỗ)
  const overSizeMachines = useMemo(() => {
    if (!(w > 0 && h > 0)) return [];
    return machines
      .filter((m) => machineIds.includes(m.id) && m.max_width_cm != null && m.max_height_cm != null)
      .filter((m) => {
        const mw = m.max_width_cm!, mh = m.max_height_cm!;
        const fits = (w <= mw && h <= mh) || (allowRotation && h <= mw && w <= mh);
        return !fits;
      })
      .map((m) => m.name);
  }, [machines, machineIds, w, h, allowRotation]);

  function toggleMachine(id: number) {
    setMachineIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function buildPayload(): PaperSizeInput | null {
    if (!name.trim()) { setValidationError("Tên khổ giấy không được trống."); return null; }
    if (!(w > 0)) { setValidationError("Chiều rộng (cm) phải lớn hơn 0."); return null; }
    if (!(h > 0)) { setValidationError("Chiều cao (cm) phải lớn hơn 0."); return null; }
    if (isCut && !parentId) { setValidationError("Khổ cắt phải chọn khổ cha."); return null; }
    return {
      code: isEdit ? undefined : (code.trim() || undefined),
      name: name.trim(),
      size_group: group,
      is_purchase_size: isPurchase,
      is_print_sheet_size: isPrint,
      is_cut_size: isCut,
      note: note.trim() ? note.trim() : null,
      is_active: isActive,
      width_cm: w,
      height_cm: h,
      allow_rotation: allowRotation,
      compatible_machine_ids: machineIds.length ? machineIds : null,
      default_machine_id: defaultMachine ? Number(defaultMachine) : null,
      parent_size_id: isCut && parentId ? Number(parentId) : null,
      cut_count: isCut && cutCount ? Number(cutCount) : null,
      cut_waste_rate: isCut && cutWaste ? Number(cutWaste) : null,
      effective_from: effectiveFrom || null,
    };
  }

  async function submit(asNewVersion: boolean) {
    if (!token || saving) return;
    setValidationError(null);
    const payload = buildPayload();
    if (!payload) return;
    setSaving(true);
    try {
      if (isEdit && existing) {
        if (asNewVersion) await api.paperSizes.createVersion(token, existing.id, payload);
        else await api.paperSizes.update(token, existing.id, payload);
      } else {
        await api.paperSizes.create(token, payload);
      }
      onSaved();
    } catch (err) {
      setValidationError(err instanceof ApiError ? err.message : "Lưu thất bại. Vui lòng kiểm tra lại.");
      setSaving(false);
    }
  }

  function onSubmit(e: FormEvent) { e.preventDefault(); submit(false); }

  const parentOptions = allSizes.filter((s) => s.id !== existing?.id);

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 760 }}>
        <div className="md-page__dialog-head">
          <h2>
            {isEdit ? `Chỉnh sửa khổ giấy: ${existing?.name}` : "Tạo khổ giấy mới"}
            {isEdit && existing && (
              <span className="md-page__muted" style={{ fontSize: 13, marginLeft: 8 }}>
                (v{existing.version}{existing.used_count > 0 ? ` · đã dùng ${existing.used_count} phiếu` : ""})
              </span>
            )}
          </h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {/* KHỐI 1 — Thông tin chung */}
          <div style={sectionHead}>1 · Thông tin chung</div>
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Mã khổ giấy</span>
              <input className="input" placeholder={isEdit ? "" : "Tự sinh KG### nếu bỏ trống"} value={code}
                     disabled={isEdit} onChange={(e) => setCode(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Tên khổ *</span>
              <input className="input" placeholder="VD: Khổ 79×109" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Nhóm khổ</span>
              <select className="input select" value={group} onChange={(e) => setGroup(e.target.value as PaperSizeGroup)}>
                {SIZE_GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
              </select>
            </label>
            <div className="field">
              <span className="field__label">Loại khổ</span>
              <div className="md-page__toggle-wrap" style={{ gap: 14, flexWrap: "wrap" }}>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input type="checkbox" checked={isPurchase} onChange={(e) => setIsPurchase(e.target.checked)} /> Khổ mua
                </label>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input type="checkbox" checked={isPrint} onChange={(e) => setIsPrint(e.target.checked)} /> Khổ tờ in
                </label>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input type="checkbox" checked={isCut} onChange={(e) => setIsCut(e.target.checked)} /> Khổ cắt
                </label>
              </div>
            </div>
            <label className="field">
              <span className="field__label">Trạng thái</span>
              <div className="md-page__toggle-wrap">
                <input type="checkbox" id="ps-active-check" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                <label htmlFor="ps-active-check">Kích hoạt hoạt động</label>
              </div>
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span className="field__label">Ghi chú</span>
              <input className="input" placeholder="Ghi chú (tùy chọn)" value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
          </div>

          {/* KHỐI 2 — Kích thước */}
          <div style={sectionHead}>2 · Kích thước</div>
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Rộng (cm) *</span>
              <input className="input" type="number" min="0" step="0.01" placeholder="VD: 79" value={width} onChange={(e) => setWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Cao (cm) *</span>
              <input className="input" type="number" min="0" step="0.01" placeholder="VD: 109" value={height} onChange={(e) => setHeight(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Diện tích (m²)</span>
              <input className="input" value={area ? area.toFixed(4) : ""} disabled readOnly />
            </label>
            <label className="field">
              <span className="field__label">Xoay chiều</span>
              <div className="md-page__toggle-wrap">
                <input type="checkbox" id="ps-rot" checked={allowRotation} onChange={(e) => setAllowRotation(e.target.checked)} />
                <label htmlFor="ps-rot">Cho phép xoay khi tính số con</label>
              </div>
            </label>
          </div>

          {/* KHỐI 3 — Áp dụng cho máy */}
          <div style={sectionHead}>3 · Áp dụng cho máy</div>
          <div className="field">
            <span className="field__label">Máy phù hợp (bỏ trống = mọi máy)</span>
            <div className="md-page__toggle-wrap" style={{ gap: 16, flexWrap: "wrap" }}>
              {machines.length === 0 && <span className="md-page__muted">Chưa có máy nào.</span>}
              {machines.map((m) => (
                <label key={m.id} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input type="checkbox" checked={machineIds.includes(m.id)} onChange={() => toggleMachine(m.id)} />
                  {m.name}
                  {m.max_width_cm != null && m.max_height_cm != null && (
                    <span className="md-page__muted" style={{ fontSize: 11 }}> ({m.max_width_cm}×{m.max_height_cm})</span>
                  )}
                </label>
              ))}
            </div>
          </div>
          {machineIds.length > 0 && (
            <label className="field" style={{ maxWidth: 300 }}>
              <span className="field__label">Là khổ mặc định cho máy</span>
              <select className="input select" value={defaultMachine} onChange={(e) => setDefaultMachine(e.target.value)}>
                <option value="">-- Không --</option>
                {machines.filter((m) => machineIds.includes(m.id)).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
          )}
          {overSizeMachines.length > 0 && (
            <div className="banner banner--error" role="alert" style={{ marginTop: 8 }}>
              ⚠ Khổ {w}×{h} vượt khổ in tối đa của máy: {overSizeMachines.join(", ")}.
            </div>
          )}

          {/* KHỐI 4 — Quan hệ khổ cắt */}
          {isCut && (
            <>
              <div style={sectionHead}>4 · Quan hệ khổ cắt</div>
              <div className="md-page__form-grid">
                <label className="field">
                  <span className="field__label">Khổ cha *</span>
                  <select className="input select" value={parentId} onChange={(e) => setParentId(e.target.value)}>
                    <option value="">-- Chọn khổ cha --</option>
                    {parentOptions.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.name} ({s.width_cm}×{s.height_cm})</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="field__label">Số tờ con tạo ra</span>
                  <input className="input" type="number" min="1" step="1" placeholder="VD: 2" value={cutCount} onChange={(e) => setCutCount(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Hao hụt cắt (%)</span>
                  <input className="input" type="number" min="0" step="0.01" placeholder="0" value={cutWaste} onChange={(e) => setCutWaste(e.target.value)} />
                </label>
              </div>
            </>
          )}

          {/* Ngày hiệu lực (versioning) */}
          <div style={sectionHead}>Hiệu lực</div>
          <label className="field" style={{ maxWidth: 240 }}>
            <span className="field__label">Áp dụng từ ngày</span>
            <input className="input" type="date" value={effectiveFrom ?? ""} onChange={(e) => setEffectiveFrom(e.target.value)} />
          </label>

          {/* KHỐI 5 — Test số con */}
          <div style={sectionHead}>Test số con hình học</div>
          <div className="card" style={{ padding: 14, background: "var(--surface-2, #f8fafc)" }}>
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Nhíp máy (cm)</span>
                <input className="input" type="number" step="0.1" value={tGripper} onChange={(e) => setTGripper(e.target.value)} /></label>
              <label className="field"><span className="field__label">Xén mép (cm)</span>
                <input className="input" type="number" step="0.1" value={tEdge} onChange={(e) => setTEdge(e.target.value)} /></label>
              <label className="field"><span className="field__label">Khổ TP rộng (cm)</span>
                <input className="input" type="number" step="0.1" value={tFinW} onChange={(e) => setTFinW(e.target.value)} /></label>
              <label className="field"><span className="field__label">Khổ TP cao (cm)</span>
                <input className="input" type="number" step="0.1" value={tFinH} onChange={(e) => setTFinH(e.target.value)} /></label>
              <label className="field"><span className="field__label">Bleed (cm)</span>
                <input className="input" type="number" step="0.1" value={tBleed} onChange={(e) => setTBleed(e.target.value)} /></label>
              <label className="field"><span className="field__label">Chừa giữa con (cm)</span>
                <input className="input" type="number" step="0.1" value={tGutter} onChange={(e) => setTGutter(e.target.value)} /></label>
            </div>
            {w > 0 && h > 0 ? (
              <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.7 }}>
                <div>Khổ in khả dụng: <strong>{pieces.usableW.toFixed(1)} × {pieces.usableH.toFixed(1)} cm</strong></div>
                <div>Số con không xoay: <strong>{pieces.straight}</strong> · Số con có xoay: <strong>{pieces.rotated}</strong></div>
                <div>→ Số con hình học chọn: <strong style={{ fontSize: 15 }}>{pieces.best} con/tờ</strong>
                  {!allowRotation && <span className="md-page__muted"> (đang tắt xoay)</span>}</div>
                {pieces.best === 0 && <div className="md-page__muted" style={{ color: "#b91c1c" }}>⚠ Khổ thành phẩm không lọt khổ in — kiểm tra lại kích thước.</div>}
              </div>
            ) : (
              <div className="md-page__muted" style={{ marginTop: 8 }}>Nhập Rộng/Cao ở khối 2 để xem số con.</div>
            )}
          </div>

          {validationError && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{validationError}</div>}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            {isEdit && (
              <Button type="button" variant="secondary" loading={saving} onClick={() => submit(true)}>
                Lưu thành version mới
              </Button>
            )}
            <Button type="submit" variant="primary" loading={saving}>Lưu khổ giấy</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function HistoryDialog({
  row, onClose,
}: {
  row: PaperSizeRow;
  onClose: () => void;
}) {
  const { token } = useAuth();
  const [items, setItems] = useState<PaperSizeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.paperSizes.history(token, row.id)
      .then((r) => setItems(r.items))
      .catch(() => setErr("Không tải được lịch sử."));
  }, [token, row.id]);

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 640 }}>
        <div className="md-page__dialog-head">
          <h2>Lịch sử phiên bản: {row.code}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          {err && <div className="banner banner--error">{err}</div>}
          {!items ? <p className="md-page__muted">Đang tải…</p> : (
            <table className="md-page__table">
              <thead>
                <tr><th>Version</th><th>Kích thước</th><th>Áp dụng từ</th><th>Đến</th><th>Đã dùng</th><th>Trạng thái</th></tr>
              </thead>
              <tbody>
                {items.map((v) => (
                  <tr key={v.id}>
                    <td className="md-page__mono">v{v.version}</td>
                    <td>{v.width_cm}×{v.height_cm} cm</td>
                    <td>{v.effective_from ?? <span className="md-page__muted">—</span>}</td>
                    <td>{v.effective_to ?? <span className="md-page__muted">Vô hạn</span>}</td>
                    <td>{v.used_count}</td>
                    <td>
                      <span className={`md-page__status-badge ${v.is_active ? "is-active" : "is-inactive"}`}>
                        {v.is_active ? "Đang dùng" : "Đã đóng"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
