import { useCallback, useEffect, useState, type CSSProperties, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ImpositionTypeRow,
  type ImpositionTypeInput,
  type ImpositionGroupKind,
  type ImpositionAppliesToSides,
  type ProductTypeCatalogRow,
  type MachineRow,
  type PaperSizeRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const SIDES_OPTIONS = [
  { value: 1, label: "1 mặt" },
  { value: 2, label: "2 mặt" },
];

const GROUP_OPTIONS: { value: ImpositionGroupKind; label: string }[] = [
  { value: "one_side", label: "1 mặt" },
  { value: "two_side", label: "2 mặt" },
  { value: "multi_page", label: "Nhiều trang" },
  { value: "custom", label: "Tùy chỉnh" },
];
const GROUP_LABEL: Record<string, string> = Object.fromEntries(GROUP_OPTIONS.map((o) => [o.value, o.label]));

const APPLIES_SIDES_OPTIONS: { value: ImpositionAppliesToSides; label: string }[] = [
  { value: "any", label: "Không giới hạn" },
  { value: "1", label: "Chỉ 1 mặt" },
  { value: "2", label: "Chỉ 2 mặt" },
  { value: "multi", label: "Nhiều mặt / nhiều trang" },
];

type FormMode =
  | { kind: "create"; from?: ImpositionTypeRow } // create (optionally cloned from a row)
  | { kind: "edit"; row: ImpositionTypeRow }
  | { kind: "version"; row: ImpositionTypeRow }; // force a new version

export function ImpositionTypesCatalogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<ImpositionTypeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [form, setForm] = useState<FormMode | null>(null);
  const [history, setHistory] = useState<ImpositionTypeRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.impositionTypes
      .list(token, { current_only: true, sort: "priority", size: 200 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục kiểu bình bài.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleActive = useCallback(
    async (row: ImpositionTypeRow) => {
      if (!token) return;
      try {
        await api.impositionTypes.update(token, row.id, { ...rowToInput(row), is_active: !row.is_active });
        load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không đổi được trạng thái.");
      }
    },
    [token, load],
  );

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Kiểu bình bài (403).
        </div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Kiểu bình bài</h1>
        <p className="md-page__sub">
          Khai báo các kiểu bình (1 mặt / A-B / tự trở / trở nhíp / perfecting / tùy chỉnh) và bộ hệ
          số engine dùng để tính <strong>số con thành phẩm</strong>, <strong>số bộ kẽm</strong>,{" "}
          <strong>số lượt qua máy</strong> và <strong>lượt in màu</strong>. Kiểu đã dùng trong báo giá
          không sửa trực tiếp — dùng <em>Tạo phiên bản mới</em>; không xóa vật lý, chỉ <em>Ngưng áp dụng</em>.
        </p>
      </header>

      <div className="md-page__toolbar">
        <div className="md-page__toolbar-spacer" />
        <Button variant="primary" onClick={() => setForm({ kind: "create" })}>
          + Thêm mới
        </Button>
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
              <th>Mã</th>
              <th>Tên kiểu</th>
              <th>Nhóm</th>
              <th>HS TP</th>
              <th>Lượt máy</th>
              <th>Bộ kẽm</th>
              <th>Lượt mực</th>
              <th>Áp dụng</th>
              <th>Ver</th>
              <th>Dùng</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={12} className="md-page__status" role="status">Đang tải dữ liệu...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={12} className="md-page__empty">Chưa có kiểu bình bài nào.</td></tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="md-page__row" onClick={() => setForm({ kind: "edit", row })}>
                  <td className="md-page__mono">{row.code}</td>
                  <td><strong>{row.name}</strong></td>
                  <td>{GROUP_LABEL[row.group_kind] ?? row.group_kind}</td>
                  <td>{row.finished_factor}</td>
                  <td>{row.pass_count}</td>
                  <td>{row.plate_set_factor}</td>
                  <td>{row.ink_pass_factor}</td>
                  <td>{appliesLabel(row)}</td>
                  <td className="md-page__mono">v{row.version}</td>
                  <td>{row.used_count}</td>
                  <td>
                    <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                      {row.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" title="Sửa" onClick={() => setForm({ kind: "edit", row })}>Sửa</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" title="Tạo phiên bản mới" onClick={() => setForm({ kind: "version", row })}>Version</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" title="Sao chép sang mã mới" onClick={() => setForm({ kind: "create", from: row })}>Chép</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" title={row.is_active ? "Ngưng áp dụng" : "Kích hoạt"} onClick={() => toggleActive(row)}>{row.is_active ? "Ngưng" : "Bật"}</button>
                    <button type="button" className="btn btn--ghost md-page__rowbtn" title="Xem lịch sử phiên bản" onClick={() => setHistory(row)}>LS</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {form && (
        <ImpositionTypeFormDialog
          mode={form}
          onClose={() => setForm(null)}
          onSaved={() => { setForm(null); load(); }}
        />
      )}

      {history && (
        <VersionHistoryDialog row={history} onClose={() => setHistory(null)} />
      )}
    </main>
  );
}

function appliesLabel(row: ImpositionTypeRow): string {
  const pts = row.applicable_product_types;
  if (!pts || pts.length === 0) return "Tất cả";
  if (pts.length <= 2) return pts.join(", ");
  return `${pts.length} loại SP`;
}

function rowToInput(row: ImpositionTypeRow): ImpositionTypeInput {
  return {
    name: row.name,
    group_kind: row.group_kind,
    sides: row.sides,
    finished_factor: row.finished_factor,
    pass_count: row.pass_count,
    plate_set_factor: row.plate_set_factor,
    ink_pass_factor: row.ink_pass_factor,
    allow_rotate: row.allow_rotate,
    shared_plate_set: row.shared_plate_set,
    note: row.note,
    technology: row.technology,
    applies_to_sides: row.applies_to_sides,
    applicable_product_types: row.applicable_product_types,
    applicable_machine_ids: row.applicable_machine_ids,
    applicable_paper_size_ids: row.applicable_paper_size_ids,
    allow_multi_signature: row.allow_multi_signature,
    priority: row.priority,
    effective_from: row.effective_from,
    effective_to: row.effective_to,
    is_active: row.is_active,
  };
}

function tabBtnStyle(active: boolean): CSSProperties {
  return {
    padding: "8px 14px",
    border: "none",
    borderBottom: active ? "2px solid var(--rust, #b45309)" : "2px solid transparent",
    background: "transparent",
    fontWeight: active ? 700 : 500,
    color: active ? "var(--ink, #111)" : "var(--ink-soft, #667)",
    cursor: "pointer",
  };
}

const TABS = ["Thông tin chung", "Hệ số tính", "Điều kiện áp dụng", "Kiểm thử nhanh"];

function ImpositionTypeFormDialog({
  mode,
  onClose,
  onSaved,
}: {
  mode: FormMode;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const source = mode.kind === "create" ? mode.from ?? null : mode.row;
  const isEdit = mode.kind === "edit";
  const isVersion = mode.kind === "version";
  const isClone = mode.kind === "create" && !!mode.from;
  const willVersion = isVersion || (isEdit && (source?.used_count ?? 0) > 0);

  const [tab, setTab] = useState(0);

  const [code, setCode] = useState(mode.kind === "create" ? "" : source?.code ?? "");
  const [name, setName] = useState(isClone ? `${source?.name} (bản sao)` : source?.name ?? "");
  const [groupKind, setGroupKind] = useState<ImpositionGroupKind>(source?.group_kind ?? "custom");
  const [note, setNote] = useState(source?.note ?? "");
  const [isActive, setIsActive] = useState(source?.is_active ?? true);

  const [sides, setSides] = useState(source ? source.sides : 1);
  const [finishedFactor, setFinishedFactor] = useState(source ? String(source.finished_factor) : "1");
  const [passCount, setPassCount] = useState(source ? String(source.pass_count) : "1");
  const [plateSetFactor, setPlateSetFactor] = useState(source ? String(source.plate_set_factor) : "1");
  const [inkPassFactor, setInkPassFactor] = useState(source ? String(source.ink_pass_factor) : "1");
  const [allowRotate, setAllowRotate] = useState(source?.allow_rotate ?? true);
  const [sharedPlateSet, setSharedPlateSet] = useState(source?.shared_plate_set ?? false);

  const [technology, setTechnology] = useState(source?.technology ?? "offset");
  const [appliesToSides, setAppliesToSides] = useState<ImpositionAppliesToSides>(source?.applies_to_sides ?? "any");
  const [productTypes, setProductTypes] = useState<string[]>(source?.applicable_product_types ?? []);
  const [machineIds, setMachineIds] = useState<number[]>(source?.applicable_machine_ids ?? []);
  const [paperSizeIds, setPaperSizeIds] = useState<number[]>(source?.applicable_paper_size_ids ?? []);
  const [allowMultiSignature, setAllowMultiSignature] = useState(source?.allow_multi_signature ?? true);
  const [priority, setPriority] = useState(source ? String(source.priority) : "100");

  const [effectiveFrom, setEffectiveFrom] = useState(isVersion ? "" : source?.effective_from ?? "");
  const [effectiveTo, setEffectiveTo] = useState(isVersion ? "" : source?.effective_to ?? "");

  const [ptOptions, setPtOptions] = useState<ProductTypeCatalogRow[]>([]);
  const [machineOptions, setMachineOptions] = useState<MachineRow[]>([]);
  const [paperOptions, setPaperOptions] = useState<PaperSizeRow[]>([]);

  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.productTypesCatalog.list(token, { size: 200 }).then((r) => setPtOptions(r.items)).catch(() => {});
    api.machines.list(token, { machine_type: "offset", size: 200 }).then((r) => setMachineOptions(r.items)).catch(() => {});
    api.paperSizes.list(token, { size: 200 }).then((r) => setPaperOptions(r.items)).catch(() => {});
  }, [token]);

  const ff = Number(finishedFactor);
  const pc = Number(passCount);
  const psf = Number(plateSetFactor);
  const ipf = Number(inkPassFactor);

  // Cảnh báo mềm (không chặn lưu)
  const softWarnings: string[] = [];
  const softInfos: string[] = [];
  if (sides === 1 && Number.isFinite(ipf) && ipf > 1) softWarnings.push("Số mặt = 1 nhưng hệ số lượt in màu > 1 — thường không hợp lý.");
  if (sides === 2 && Number.isFinite(pc) && pc === 1) softWarnings.push("Số mặt = 2 mà số lượt qua máy = 1 — có phải máy perfecting (in trở tự động)?");
  if (Number.isFinite(ff) && ff === 0.5) softInfos.push("Hệ số thành phẩm 0.5 sẽ giảm một nửa số con/tờ (cần gấp đôi số tờ in).");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setValidationError(null);

    if (mode.kind === "create" && !code.trim()) return fail("Mã kiểu bình bài không được trống.");
    if (!name.trim()) return fail("Tên kiểu bình bài không được trống.");
    if (sides !== 1 && sides !== 2) return fail("Số mặt in phải là 1 hoặc 2.");
    if (!Number.isFinite(ff) || ff <= 0) return fail("Hệ số thành phẩm phải lớn hơn 0.");
    if (!Number.isFinite(pc) || pc <= 0) return fail("Số lượt qua máy phải lớn hơn 0.");
    if (!Number.isFinite(psf) || psf < 0) return fail("Hệ số bộ kẽm không được âm.");
    if (!Number.isFinite(ipf) || ipf < 0) return fail("Hệ số lượt in màu không được âm.");
    const prio = Number(priority);
    if (!Number.isFinite(prio) || prio < 0) return fail("Thứ tự ưu tiên không được âm.");
    if (effectiveFrom && effectiveTo && effectiveTo <= effectiveFrom) return fail("Ngày hết hiệu lực phải sau ngày bắt đầu.");

    const payload: ImpositionTypeInput = {
      name: name.trim(),
      group_kind: groupKind,
      sides,
      finished_factor: ff,
      pass_count: pc,
      plate_set_factor: psf,
      ink_pass_factor: ipf,
      allow_rotate: allowRotate,
      shared_plate_set: sharedPlateSet,
      note: note.trim() ? note.trim() : null,
      technology: technology.trim() || "offset",
      applies_to_sides: appliesToSides,
      applicable_product_types: productTypes.length ? productTypes : null,
      applicable_machine_ids: machineIds.length ? machineIds : null,
      applicable_paper_size_ids: paperSizeIds.length ? paperSizeIds : null,
      allow_multi_signature: allowMultiSignature,
      priority: prio,
      effective_from: effectiveFrom || null,
      effective_to: effectiveTo || null,
      is_active: isActive,
    };
    if (mode.kind === "create") payload.code = code.trim().toUpperCase();
    if (isVersion) payload.force_version = true;

    setSaving(true);
    try {
      if (mode.kind === "create") {
        await api.impositionTypes.create(token, payload);
      } else {
        await api.impositionTypes.update(token, source!.id, payload);
      }
      onSaved();
    } catch (err) {
      setValidationError(err instanceof ApiError ? err.message : "Lưu thất bại. Vui lòng kiểm tra lại.");
      setSaving(false);
    }
    function fail(msg: string) {
      setValidationError(msg);
    }
  }

  const title = mode.kind === "create"
    ? (isClone ? `Sao chép từ: ${source?.name}` : "Tạo kiểu bình bài mới")
    : isVersion
      ? `Tạo phiên bản mới: ${source?.name} (v${(source?.version ?? 1) + 1})`
      : `Chỉnh sửa: ${source?.name}`;

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 780 }}>
        <div className="md-page__dialog-head">
          <h2>{title}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--rule-soft, #e5e7eb)", padding: "0 16px" }}>
          {TABS.map((t, i) => (
            <button key={t} type="button" style={tabBtnStyle(tab === i)} onClick={() => setTab(i)}>{t}</button>
          ))}
        </div>

        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {willVersion && (
            <div className="banner banner--info" role="status">
              {isVersion
                ? "Sẽ tạo một phiên bản mới của mã này (bản cũ giữ nguyên, đóng hiệu lực hôm nay)."
                : <>Kiểu này đã dùng trong <strong>{source?.used_count}</strong> báo giá. Sửa hệ số sẽ tạo <strong>phiên bản mới</strong>; báo giá cũ giữ số đã chốt.</>}
            </div>
          )}

          {/* TAB 1 — Thông tin chung */}
          {tab === 0 && (
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Mã kiểu *</span>
                <input className="input md-page__mono" placeholder="VD: TU_TRO" value={code} disabled={mode.kind !== "create"} onChange={(e) => setCode(e.target.value.toUpperCase())} />
                {mode.kind !== "create" && <span className="field__hint">Mã không đổi sau khi tạo.</span>}
              </label>
              <label className="field">
                <span className="field__label">Tên kiểu *</span>
                <input className="input" placeholder="VD: Tự trở" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Nhóm kiểu *</span>
                <select className="input" value={groupKind} onChange={(e) => setGroupKind(e.target.value as ImpositionGroupKind)}>
                  {GROUP_OPTIONS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Trạng thái</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="it-active" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  <label htmlFor="it-active">Active</label>
                </div>
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span className="field__label">Mô tả</span>
                <textarea className="input" rows={2} placeholder="Diễn giải nghiệp vụ (tùy chọn)" value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Hiệu lực từ</span>
                <input className="input" type="date" value={effectiveFrom ?? ""} onChange={(e) => setEffectiveFrom(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Hiệu lực đến</span>
                <input className="input" type="date" value={effectiveTo ?? ""} onChange={(e) => setEffectiveTo(e.target.value)} />
              </label>
            </div>
          )}

          {/* TAB 2 — Hệ số tính + box công thức */}
          {tab === 1 && (
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
              <div className="md-page__form-grid" style={{ flex: "1 1 340px" }}>
                <label className="field">
                  <span className="field__label">Số mặt in</span>
                  <select className="input" value={sides} onChange={(e) => setSides(Number(e.target.value))}>
                    {SIDES_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="field__label">Hệ số thành phẩm *</span>
                  <input className="input" type="number" min="0" step="0.001" value={finishedFactor} onChange={(e) => setFinishedFactor(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Số lượt qua máy *</span>
                  <input className="input" type="number" min="0" step="0.001" value={passCount} onChange={(e) => setPassCount(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Hệ số bộ kẽm *</span>
                  <input className="input" type="number" min="0" step="0.001" value={plateSetFactor} onChange={(e) => setPlateSetFactor(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Hệ số lượt in màu *</span>
                  <input className="input" type="number" min="0" step="0.001" value={inkPassFactor} onChange={(e) => setInkPassFactor(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Cho phép xoay</span>
                  <div className="md-page__toggle-wrap">
                    <input type="checkbox" id="it-rotate" checked={allowRotate} onChange={(e) => setAllowRotate(e.target.checked)} />
                    <label htmlFor="it-rotate">Cho phép xoay bài</label>
                  </div>
                </label>
                <label className="field">
                  <span className="field__label">Dùng chung bộ kẽm</span>
                  <div className="md-page__toggle-wrap">
                    <input type="checkbox" id="it-shared" checked={sharedPlateSet} onChange={(e) => setSharedPlateSet(e.target.checked)} />
                    <label htmlFor="it-shared">2 mặt chung 1 bộ kẽm</label>
                  </div>
                </label>
              </div>
              <div style={{ flex: "1 1 260px", background: "var(--paper, rgba(20,19,15,0.03))", border: "1px solid var(--rule-soft, #e5e7eb)", borderRadius: 8, padding: 14, fontSize: 13, lineHeight: 1.7 }}>
                <strong style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>Ảnh hưởng công thức</strong>
                <div style={{ marginTop: 8 }}>Số con TP/tờ = số con hình học × <strong>{fmt(ff)}</strong></div>
                <div>Giờ máy = số tờ SX × <strong>{fmt(pc)}</strong> / tốc độ máy</div>
                <div>Kẽm = số màu × <strong>{fmt(psf)}</strong> × số form/tay</div>
                <div>Mực = số tờ SX × số màu × <strong>{fmt(ipf)}</strong></div>
              </div>
            </div>
          )}

          {/* TAB 3 — Điều kiện áp dụng */}
          {tab === 2 && (
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Công nghệ</span>
                <input className="input" value={technology} onChange={(e) => setTechnology(e.target.value)} placeholder="offset" />
              </label>
              <label className="field">
                <span className="field__label">Áp dụng cho số mặt</span>
                <select className="input" value={appliesToSides} onChange={(e) => setAppliesToSides(e.target.value as ImpositionAppliesToSides)}>
                  {APPLIES_SIDES_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Thứ tự ưu tiên</span>
                <input className="input" type="number" min="0" step="1" value={priority} onChange={(e) => setPriority(e.target.value)} />
                <span className="field__hint">Nhỏ = ưu tiên gợi ý cao</span>
              </label>
              <label className="field">
                <span className="field__label">Nhiều tay sách</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="it-multisig" checked={allowMultiSignature} onChange={(e) => setAllowMultiSignature(e.target.checked)} />
                  <label htmlFor="it-multisig">Cho phép khi nhiều tay sách</label>
                </div>
              </label>
              <div className="field" style={{ gridColumn: "1 / -1" }}>
                <span className="field__label">Áp dụng loại sản phẩm (trống = tất cả)</span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 4 }}>
                  {ptOptions.map((p) => (
                    <label key={p.product_type} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={productTypes.includes(p.product_type)}
                        onChange={(e) => setProductTypes((prev) => e.target.checked ? [...prev, p.product_type] : prev.filter((x) => x !== p.product_type))}
                      />
                      {p.name}
                    </label>
                  ))}
                </div>
              </div>
              <label className="field">
                <span className="field__label">Áp dụng cho máy (offset)</span>
                <select className="input" multiple size={4} value={machineIds.map(String)} onChange={(e) => setMachineIds(Array.from(e.target.selectedOptions, (o) => Number(o.value)))}>
                  {machineOptions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Áp dụng cho khổ giấy</span>
                <select className="input" multiple size={4} value={paperSizeIds.map(String)} onChange={(e) => setPaperSizeIds(Array.from(e.target.selectedOptions, (o) => Number(o.value)))}>
                  {paperOptions.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.width_cm}×{p.height_cm})</option>)}
                </select>
              </label>
            </div>
          )}

          {/* TAB 4 — Kiểm thử nhanh */}
          {tab === 3 && <QuickTest ff={ff} pc={pc} psf={psf} ipf={ipf} />}

          {(softWarnings.length > 0 || softInfos.length > 0) && (
            <div style={{ marginTop: 12 }}>
              {softWarnings.map((w, i) => (
                <div key={`w${i}`} className="banner banner--error" role="alert" style={{ marginBottom: 6 }}>⚠️ {w}</div>
              ))}
              {softInfos.map((w, i) => (
                <div key={`i${i}`} className="banner banner--info" role="status" style={{ marginBottom: 6 }}>ℹ️ {w}</div>
              ))}
            </div>
          )}

          {validationError && <div className="banner banner--error" role="alert">{validationError}</div>}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>
              {mode.kind === "create" ? "Tạo mới" : isVersion ? "Tạo phiên bản mới" : willVersion ? "Lưu (tạo bản mới nếu đổi hệ số)" : "Lưu"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function QuickTest({ ff, pc, psf, ipf }: { ff: number; pc: number; psf: number; ipf: number }) {
  const [geo, setGeo] = useState("8");
  const [qty, setQty] = useState("1000");
  const [prodSheets, setProdSheets] = useState("300");
  const [colors, setColors] = useState("4");
  const [forms, setForms] = useState("1");
  const [speed, setSpeed] = useState("6000");

  const g = Number(geo), q = Number(qty), ps = Number(prodSheets), c = Number(colors), f = Number(forms), sp = Number(speed);
  const finishedPieces = Number.isFinite(g) && Number.isFinite(ff) ? Math.max(1, Math.floor(g * ff)) : 0;
  const theoSheets = q > 0 && finishedPieces > 0 ? Math.ceil(q / finishedPieces) : 0;
  const machineSheets = Number.isFinite(ps) && Number.isFinite(pc) ? ps * pc : 0;
  const runHours = sp > 0 ? machineSheets / sp : 0;
  const plates = [c, psf, f].every(Number.isFinite) ? Math.round(c * psf * f) : 0;
  const inkImpr = [ps, c, ipf].every(Number.isFinite) ? ps * c * ipf : 0;

  const num = (v: string, set: (s: string) => void, label: string) => (
    <label className="field">
      <span className="field__label">{label}</span>
      <input className="input" type="number" value={v} onChange={(e) => set(e.target.value)} />
    </label>
  );

  return (
    <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
      <div className="md-page__form-grid" style={{ flex: "1 1 300px" }}>
        {num(geo, setGeo, "Số con hình học")}
        {num(qty, setQty, "SL thành phẩm")}
        {num(prodSheets, setProdSheets, "Số tờ sản xuất")}
        {num(colors, setColors, "Số màu")}
        {num(forms, setForms, "Số form/tay")}
        {num(speed, setSpeed, "Tốc độ máy (tờ/giờ)")}
      </div>
      <div style={{ flex: "1 1 280px", background: "var(--paper, rgba(20,19,15,0.03))", border: "1px solid var(--rule-soft, #e5e7eb)", borderRadius: 8, padding: 14, fontSize: 13, lineHeight: 1.8 }}>
        <strong style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>Preview engine</strong>
        <div style={{ marginTop: 8 }}>Số con TP/tờ = {geo} × {fmt(ff)} = <strong>{finishedPieces}</strong> con</div>
        <div>Số tờ lý thuyết = ⌈{qty} / {finishedPieces}⌉ = <strong>{theoSheets.toLocaleString("vi-VN")}</strong> tờ</div>
        <div style={{ marginTop: 6 }}>Số tờ tính giờ máy = {prodSheets} × {fmt(pc)} = <strong>{machineSheets.toLocaleString("vi-VN")}</strong> lượt tờ</div>
        <div>Giờ chạy = {machineSheets} / {speed} = <strong>{runHours.toFixed(3)}</strong> giờ</div>
        <div style={{ marginTop: 6 }}>Số bản kẽm = {colors} × {fmt(psf)} × {forms} = <strong>{plates}</strong> bản</div>
        <div>Lượt in màu = {prodSheets} × {colors} × {fmt(ipf)} = <strong>{inkImpr.toLocaleString("vi-VN")}</strong> lượt màu</div>
      </div>
    </div>
  );
}

function VersionHistoryDialog({ row, onClose }: { row: ImpositionTypeRow; onClose: () => void }) {
  const { token } = useAuth();
  const [versions, setVersions] = useState<ImpositionTypeRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.impositionTypes
      .list(token, { code: row.code, sort: "code", size: 200 })
      .then((r) => setVersions([...r.items].sort((a, b) => b.version - a.version)))
      .catch(() => setVersions([]))
      .finally(() => setLoading(false));
  }, [token, row.code]);

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 720 }}>
        <div className="md-page__dialog-head">
          <h2>Lịch sử phiên bản: {row.code}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          {loading ? (
            <p className="md-page__status">Đang tải...</p>
          ) : (
            <table className="md-page__table">
              <thead>
                <tr>
                  <th>Ver</th><th>Tên</th><th>HS TP</th><th>Lượt máy</th><th>Bộ kẽm</th><th>Lượt mực</th>
                  <th>Hiệu lực</th><th>Dùng</th><th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.id}>
                    <td className="md-page__mono">v{v.version}</td>
                    <td>{v.name}</td>
                    <td>{v.finished_factor}</td>
                    <td>{v.pass_count}</td>
                    <td>{v.plate_set_factor}</td>
                    <td>{v.ink_pass_factor}</td>
                    <td style={{ fontSize: 12 }}>{v.effective_from ?? "—"} → {v.effective_to ?? "nay"}</td>
                    <td>{v.used_count}</td>
                    <td>
                      <span className={`md-page__status-badge ${v.is_active ? "is-active" : "is-inactive"}`}>
                        {v.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function fmt(n: number): string {
  return Number.isFinite(n) ? String(n) : "?";
}
