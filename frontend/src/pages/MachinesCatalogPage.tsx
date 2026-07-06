import { useCallback, useEffect, useState, type CSSProperties, type FormEvent } from "react";
import {
  ApiError,
  api,
  type MachineRow,
  type MachineInput,
  type MachineRateInput,
  type MachineRateRow,
  type MachineGroup,
  type MachineStatusKind,
  type MachineRoundingPolicy,
  type PaperSizeRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

const MACHINE_TYPES = [
  { value: "offset", label: "Offset" },
  { value: "digital", label: "Kỹ thuật số" },
  { value: "large_format", label: "Khổ lớn" },
  { value: "flexo", label: "Flexo" },
  { value: "other", label: "Khác" },
];
const PROCESS_TYPES = [
  { value: "in", label: "In ấn" },
  { value: "can_mang", label: "Cán màng" },
  { value: "be", label: "Bế / Đột" },
  { value: "gap", label: "Gấp" },
  { value: "dong_cuon", label: "Đóng cuốn" },
  { value: "dong_goi", label: "Đóng gói" },
  { value: "xen", label: "Xén" },
  { value: "other", label: "Khác" },
];
const GROUP_OPTIONS: { value: MachineGroup; label: string }[] = [
  { value: "may_in", label: "Máy in" },
  { value: "may_can", label: "Máy cán" },
  { value: "may_be", label: "Máy bế" },
  { value: "may_xen", label: "Máy xén" },
  { value: "khac", label: "Khác" },
];
const GROUP_LABEL: Record<string, string> = Object.fromEntries(GROUP_OPTIONS.map((o) => [o.value, o.label]));
const STATUS_OPTIONS: { value: MachineStatusKind; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "maintenance", label: "Maintenance" },
];
const ROUNDING_OPTIONS: { value: MachineRoundingPolicy; label: string }[] = [
  { value: "none", label: "Không làm tròn" },
  { value: "0.01", label: "0.01 giờ" },
  { value: "0.25", label: "0.25 giờ" },
  { value: "0.5", label: "0.5 giờ" },
];
const MAT_CHOICES = [
  { value: "paper", label: "Giấy" },
  { value: "decal", label: "Decal" },
  { value: "pp", label: "PP" },
  { value: "canvas", label: "Canvas" },
  { value: "carton", label: "Carton" },
];

type FormMode = { kind: "create"; from?: MachineRow } | { kind: "edit"; row: MachineRow };

export function MachinesCatalogPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("dm_thiet_bi", "create");
  const canUpdate = can("dm_thiet_bi", "update");
  const [rows, setRows] = useState<MachineRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [form, setForm] = useState<FormMode | null>(null);
  const [ratesFor, setRatesFor] = useState<MachineRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.machines
      .list(token, { q: q.trim() || undefined, machine_type: typeFilter || null, sort: "code", page, size: PAGE_SIZE })
      .then((res) => { setRows(res.items); setTotal(res.total); })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục máy.");
      })
      .finally(() => setLoading(false));
  }, [token, q, typeFilter, page]);

  useEffect(() => { load(); }, [load]);

  const toggleStatus = useCallback(async (row: MachineRow) => {
    if (!token) return;
    const next: MachineStatusKind = row.status === "active" ? "inactive" : "active";
    try {
      await api.machines.update(token, row.id, { ...machineToInput(row), status: next });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đổi được trạng thái.");
    }
  }, [token, load]);

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">Bạn không có quyền truy cập Máy móc (403).</div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Máy móc & Đơn giá giờ máy</h1>
        <p className="md-page__sub">
          Khai máy in / gia công, khổ chạy được, tốc độ, thời gian setup–vệ sinh–đổi màu–đổi kẽm và đơn giá giờ máy —
          nuôi <strong>Công in = Giờ máy × Đơn giá giờ</strong>. Overhead xưởng đã hấp thụ vào đơn giá giờ.
        </p>
      </header>

      <div className="md-page__toolbar">
        <form className="md-page__search" onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }}>
          <input className="input" placeholder="Tìm theo tên / mã máy..." value={q} onChange={(e) => setQ(e.target.value)} />
          <Button type="submit" variant="ghost">Tìm</Button>
        </form>
        <select className="input md-page__filter" value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}>
          <option value="">Tất cả công nghệ</option>
          {MACHINE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <div className="md-page__toolbar-spacer" />
        {canCreate && <Button variant="primary" onClick={() => setForm({ kind: "create" })}>+ Thêm máy</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã máy</th><th>Tên máy</th><th>Nhóm</th><th>Khổ giấy tối đa</th><th>Khổ in</th>
              <th>Tốc độ</th><th>Đơn giá giờ</th><th>Setup</th><th>Trạng thái</th><th>Dùng</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={11} className="md-page__status">Đang tải dữ liệu...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={11} className="md-page__empty">Chưa có máy nào.</td></tr>
            ) : (
              rows.map((row) => {
                const rate = row.rates.find((r) => r.effective_to === null);
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => setForm({ kind: "edit", row })}>
                    <td className="md-page__mono">{row.code}</td>
                    <td><strong>{row.name}</strong></td>
                    <td>{GROUP_LABEL[row.machine_group] ?? row.machine_group}</td>
                    <td>{row.max_width_cm && row.max_height_cm ? `${row.max_width_cm}×${row.max_height_cm}` : "—"}</td>
                    <td>{row.max_print_width_cm && row.max_print_height_cm ? `${row.max_print_width_cm}×${row.max_print_height_cm}` : "—"}</td>
                    <td>{row.speed.toLocaleString("vi-VN")} {row.speed_unit}</td>
                    <td>{rate ? `${rate.hourly_rate.toLocaleString("vi-VN")}đ` : <span className="md-page__danger-text">Chưa có</span>}</td>
                    <td>{setupBaseHours(row).toFixed(2)}h</td>
                    <td><span className={`md-page__status-badge ${statusClass(row.status)}`}>{row.status}</span></td>
                    <td>{row.used_count}</td>
                    <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                      {canUpdate && <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setForm({ kind: "edit", row })}>Sửa</button>}
                      {canCreate && <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setForm({ kind: "create", from: row })}>Chép</button>}
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => setRatesFor(row)}>Giá giờ</button>
                      {canUpdate && <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => toggleStatus(row)}>{row.status === "active" ? "Ngưng" : "Bật"}</button>}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">Tổng: {total} máy · Trang {page}/{totalPages}</span>
          <div className="md-page__pager-btns">
            <button type="button" className="btn btn--ghost" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>‹ Trước</button>
            <button type="button" className="btn btn--ghost" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Sau ›</button>
          </div>
        </div>
      )}

      {form && (
        <MachineFormDialog mode={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />
      )}
      {ratesFor && (
        <MachineRatesDialog machine={ratesFor} onClose={() => setRatesFor(null)} onSaved={() => { setRatesFor(null); load(); }} />
      )}
    </main>
  );
}

function statusClass(s: string): string {
  return s === "active" ? "is-active" : "is-inactive";
}
function setupBaseHours(m: MachineRow): number {
  const gran = m.setup_time_base_hour + m.cleaning_time_hour + m.color_check_time_hour;
  return gran > 0 ? gran : (m.setup_time_mins + m.changeover_time_mins) / 60;
}

function machineToInput(m: MachineRow): MachineInput {
  const { id, code, used_count, created_by, updated_by, rates, ...fields } = m;
  void id; void code; void used_count; void created_by; void updated_by; void rates;
  return { ...fields };
}

function tabBtnStyle(active: boolean): CSSProperties {
  return {
    padding: "8px 12px", border: "none",
    borderBottom: active ? "2px solid var(--rust, #b45309)" : "2px solid transparent",
    background: "transparent", fontWeight: active ? 700 : 500,
    color: active ? "var(--ink, #111)" : "var(--ink-soft, #667)", cursor: "pointer",
  };
}
const TABS = ["Thông tin chung", "Khổ máy", "Năng suất", "Setup", "Chính sách giá", "Khổ giấy phù hợp", "Test nhanh"];

function num(v: string): number { return Number(v) || 0; }

function MachineFormDialog({ mode, onClose, onSaved }: { mode: FormMode; onClose: () => void; onSaved: () => void }) {
  const { token } = useAuth();
  const src = mode.kind === "edit" ? mode.row : mode.from ?? null;
  const isEdit = mode.kind === "edit";
  const [tab, setTab] = useState(0);

  const s = (n: number | null | undefined) => (n === null || n === undefined ? "" : String(n));
  const [code, setCode] = useState(mode.kind === "create" ? "" : src?.code ?? "");
  const [name, setName] = useState(isEdit ? src!.name : src ? `${src.name} (bản sao)` : "");
  const [mType, setMType] = useState(src?.machine_type ?? "offset");
  const [pType, setPType] = useState(src?.process_type ?? "in");
  const [group, setGroup] = useState<MachineGroup>(src?.machine_group ?? "may_in");
  const [status, setStatus] = useState<MachineStatusKind>(src?.status ?? "active");
  const [note, setNote] = useState(src?.note ?? "");
  const [numInk, setNumInk] = useState(s(src?.num_ink_units));
  const [perfecting, setPerfecting] = useState(src?.supports_perfecting ?? false);

  const [maxW, setMaxW] = useState(s(src?.max_width_cm));
  const [maxH, setMaxH] = useState(s(src?.max_height_cm));
  const [minW, setMinW] = useState(s(src?.min_width_cm));
  const [minH, setMinH] = useState(s(src?.min_height_cm));
  const [pMaxW, setPMaxW] = useState(s(src?.max_print_width_cm));
  const [pMaxH, setPMaxH] = useState(s(src?.max_print_height_cm));
  const [gripper, setGripper] = useState(s(src?.gripper_cm) || "0");
  const [sideMargin, setSideMargin] = useState(s(src?.side_margin_cm) || "0");
  const [tbMargin, setTbMargin] = useState(s(src?.top_bottom_margin_cm) || "0");

  const [speed, setSpeed] = useState(s(src?.speed));
  const [speedUnit, setSpeedUnit] = useState(src?.speed_unit ?? "to/gio");
  const [minSpeed, setMinSpeed] = useState(s(src?.min_speed));
  const [maxSpeed, setMaxSpeed] = useState(s(src?.max_speed));
  const [rounding, setRounding] = useState<MachineRoundingPolicy>(src?.rounding_hour_policy ?? "0.01");

  const [setupBase, setSetupBase] = useState(s(src?.setup_time_base_hour) || "0");
  const [setupPerColor, setSetupPerColor] = useState(s(src?.setup_time_per_color_hour) || "0");
  const [setupPerSide, setSetupPerSide] = useState(s(src?.setup_time_per_side_hour) || "0");
  const [cleaning, setCleaning] = useState(s(src?.cleaning_time_hour) || "0");
  const [colorChange, setColorChange] = useState(s(src?.color_change_time_hour) || "0");
  const [plateChange, setPlateChange] = useState(s(src?.plate_change_time_per_plate_hour) || "0");
  const [colorCheck, setColorCheck] = useState(s(src?.color_check_time_hour) || "0");
  const [minSetup, setMinSetup] = useState(s(src?.min_setup_time_hour) || "0");
  const [maxSetup, setMaxSetup] = useState(s(src?.max_setup_time_hour));
  const [setupMins, setSetupMins] = useState(s(src?.setup_time_mins) || "0");
  const [changeover, setChangeover] = useState(s(src?.changeover_time_mins) || "0");
  const [setupWaste, setSetupWaste] = useState(s(src?.setup_waste_sheets) || "0");

  const [overheadIncl, setOverheadIncl] = useState(src?.overhead_included ?? true);
  const [operatorIncl, setOperatorIncl] = useState(src?.operator_included ?? true);
  const [materials, setMaterials] = useState<string[]>(src?.supported_materials ?? ["paper"]);
  const [paperIds, setPaperIds] = useState<number[]>(src?.compatible_paper_size_ids ?? []);
  const [paperOptions, setPaperOptions] = useState<PaperSizeRow[]>([]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.paperSizes.list(token, { size: 200 }).then((r) => setPaperOptions(r.items)).catch(() => {});
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    if (mode.kind === "create" && !code.trim()) return setError("Mã máy không được trống.");
    if (!name.trim()) return setError("Tên máy không được trống.");
    const sp = Number(speed);
    if (!sp || sp <= 0) return setError("Tốc độ chuẩn phải lớn hơn 0.");
    if (maxW && pMaxW && Number(pMaxW) > Number(maxW)) return setError("Khổ in tối đa không được lớn hơn khổ giấy tối đa (rộng).");
    if (maxH && pMaxH && Number(pMaxH) > Number(maxH)) return setError("Khổ in tối đa không được lớn hơn khổ giấy tối đa (cao).");

    const payload: MachineInput = {
      name: name.trim(), machine_type: mType, process_type: pType, machine_group: group, status,
      note: note.trim() ? note.trim() : null,
      speed: sp, speed_unit: speedUnit.trim(),
      min_speed: minSpeed ? Number(minSpeed) : null, max_speed: maxSpeed ? Number(maxSpeed) : null,
      max_width_cm: maxW ? Number(maxW) : null, max_height_cm: maxH ? Number(maxH) : null,
      min_width_cm: minW ? Number(minW) : null, min_height_cm: minH ? Number(minH) : null,
      max_print_width_cm: pMaxW ? Number(pMaxW) : null, max_print_height_cm: pMaxH ? Number(pMaxH) : null,
      gripper_cm: num(gripper), side_margin_cm: num(sideMargin), top_bottom_margin_cm: num(tbMargin),
      compatible_paper_size_ids: paperIds.length ? paperIds : null,
      setup_time_mins: num(setupMins), changeover_time_mins: num(changeover), setup_waste_sheets: num(setupWaste),
      setup_time_base_hour: num(setupBase), setup_time_per_color_hour: num(setupPerColor),
      setup_time_per_side_hour: num(setupPerSide), cleaning_time_hour: num(cleaning),
      color_change_time_hour: num(colorChange), plate_change_time_per_plate_hour: num(plateChange),
      color_check_time_hour: num(colorCheck), min_setup_time_hour: num(minSetup),
      max_setup_time_hour: maxSetup ? Number(maxSetup) : null,
      rounding_hour_policy: rounding, overhead_included: overheadIncl, operator_included: operatorIncl,
      num_ink_units: numInk ? Number(numInk) : null, supports_perfecting: perfecting,
      supported_materials: materials, is_active: status === "active",
    };
    if (mode.kind === "create") payload.code = code.trim().toUpperCase();

    setSaving(true);
    try {
      if (isEdit) await api.machines.update(token, src!.id, payload);
      else await api.machines.create(token, payload);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu máy thất bại.");
      setSaving(false);
    }
  }

  const usableW = Math.max(0, (Number(pMaxW) || Number(maxW) || 0) - num(gripper) - 2 * num(sideMargin));
  const usableH = Math.max(0, (Number(pMaxH) || Number(maxH) || 0) - 2 * num(tbMargin));

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 820 }}>
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa máy: ${src?.name}` : mode.from ? `Sao chép từ: ${mode.from.name}` : "Tạo máy mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div style={{ display: "flex", gap: 2, flexWrap: "wrap", borderBottom: "1px solid var(--rule-soft,#e5e7eb)", padding: "0 12px" }}>
          {TABS.map((t, i) => <button key={t} type="button" style={tabBtnStyle(tab === i)} onClick={() => setTab(i)}>{t}</button>)}
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {isEdit && (src?.used_count ?? 0) > 0 && (
            <div className="banner banner--info" role="status">
              Máy đã dùng trong <strong>{src?.used_count}</strong> báo giá — không sửa được tốc độ / khổ / thời gian setup (đổi giá qua "Giá giờ").
            </div>
          )}

          {tab === 0 && (
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Mã máy *</span>
                <input className="input md-page__mono" placeholder="OFFSET_102_01" value={code} disabled={isEdit} onChange={(e) => setCode(e.target.value.toUpperCase())} /></label>
              <label className="field"><span className="field__label">Tên máy *</span>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
              <label className="field"><span className="field__label">Nhóm máy</span>
                <select className="input" value={group} onChange={(e) => setGroup(e.target.value as MachineGroup)}>{GROUP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Công nghệ</span>
                <select className="input" value={mType} onChange={(e) => setMType(e.target.value)}>{MACHINE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Công đoạn</span>
                <select className="input" value={pType} onChange={(e) => setPType(e.target.value)}>{PROCESS_TYPES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></label>
              <label className="field"><span className="field__label">Số đơn vị màu</span>
                <input className="input" type="number" min="1" placeholder="VD: 4" value={numInk} onChange={(e) => setNumInk(e.target.value)} /></label>
              <label className="field"><span className="field__label">Trạng thái</span>
                <select className="input" value={status} onChange={(e) => setStatus(e.target.value as MachineStatusKind)}>{STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
              <label className="field"><span className="field__label">In 2 mặt 1 lượt</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="mc-perf" checked={perfecting} onChange={(e) => setPerfecting(e.target.checked)} /><label htmlFor="mc-perf">Perfecting</label></div></label>
              <label className="field" style={{ gridColumn: "1 / -1" }}><span className="field__label">Ghi chú</span>
                <textarea className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
            </div>
          )}

          {tab === 1 && (
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
              <div className="md-page__form-grid" style={{ flex: "1 1 360px" }}>
                <label className="field"><span className="field__label">Khổ giấy tối thiểu — Rộng (cm)</span><input className="input" type="number" value={minW} onChange={(e) => setMinW(e.target.value)} /></label>
                <label className="field"><span className="field__label">Khổ giấy tối thiểu — Cao (cm)</span><input className="input" type="number" value={minH} onChange={(e) => setMinH(e.target.value)} /></label>
                <label className="field"><span className="field__label">Khổ giấy tối đa — Rộng (cm)</span><input className="input" type="number" value={maxW} onChange={(e) => setMaxW(e.target.value)} /></label>
                <label className="field"><span className="field__label">Khổ giấy tối đa — Cao (cm)</span><input className="input" type="number" value={maxH} onChange={(e) => setMaxH(e.target.value)} /></label>
                <label className="field"><span className="field__label">Khổ IN tối đa — Rộng (cm)</span><input className="input" type="number" value={pMaxW} onChange={(e) => setPMaxW(e.target.value)} /></label>
                <label className="field"><span className="field__label">Khổ IN tối đa — Cao (cm)</span><input className="input" type="number" value={pMaxH} onChange={(e) => setPMaxH(e.target.value)} /></label>
                <label className="field"><span className="field__label">Nhíp máy (cm)</span><input className="input" type="number" step="0.1" value={gripper} onChange={(e) => setGripper(e.target.value)} /></label>
                <label className="field"><span className="field__label">Lề an toàn ngang (cm)</span><input className="input" type="number" step="0.1" value={sideMargin} onChange={(e) => setSideMargin(e.target.value)} /></label>
                <label className="field"><span className="field__label">Lề an toàn dọc (cm)</span><input className="input" type="number" step="0.1" value={tbMargin} onChange={(e) => setTbMargin(e.target.value)} /></label>
              </div>
              <div style={{ flex: "1 1 220px", background: "var(--paper,rgba(20,19,15,.03))", border: "1px solid var(--rule-soft,#e5e7eb)", borderRadius: 8, padding: 14, fontSize: 13, lineHeight: 1.7 }}>
                <strong style={{ fontSize: 11, textTransform: "uppercase" }}>Vùng in khả dụng (ước)</strong>
                <div style={{ marginTop: 8 }}>= min(khổ in, khổ giấy) − nhíp − lề</div>
                <div>≈ <strong>{usableW.toFixed(1)} × {usableH.toFixed(1)} cm</strong></div>
              </div>
            </div>
          )}

          {tab === 2 && (
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Tốc độ chuẩn *</span><input className="input" type="number" value={speed} onChange={(e) => setSpeed(e.target.value)} /></label>
              <label className="field"><span className="field__label">Đơn vị tốc độ *</span>
                <input className="input" list="mc-speed-units" value={speedUnit} onChange={(e) => setSpeedUnit(e.target.value)} />
                <datalist id="mc-speed-units"><option value="to/gio" /><option value="trang/phut" /><option value="m2/gio" /></datalist></label>
              <label className="field"><span className="field__label">Tốc độ tối thiểu</span><input className="input" type="number" value={minSpeed} onChange={(e) => setMinSpeed(e.target.value)} /></label>
              <label className="field"><span className="field__label">Tốc độ tối đa</span><input className="input" type="number" value={maxSpeed} onChange={(e) => setMaxSpeed(e.target.value)} /></label>
              <label className="field"><span className="field__label">Làm tròn giờ chạy</span>
                <select className="input" value={rounding} onChange={(e) => setRounding(e.target.value as MachineRoundingPolicy)}>{ROUNDING_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
            </div>
          )}

          {tab === 3 && (
            <>
              <div className="md-page__form-grid">
                <label className="field"><span className="field__label">Setup cố định (giờ)</span><input className="input" type="number" step="0.01" value={setupBase} onChange={(e) => setSetupBase(e.target.value)} /></label>
                <label className="field"><span className="field__label">Setup theo màu (giờ/màu)</span><input className="input" type="number" step="0.01" value={setupPerColor} onChange={(e) => setSetupPerColor(e.target.value)} /></label>
                <label className="field"><span className="field__label">Setup theo mặt (giờ/mặt)</span><input className="input" type="number" step="0.01" value={setupPerSide} onChange={(e) => setSetupPerSide(e.target.value)} /></label>
                <label className="field"><span className="field__label">Vệ sinh máy (giờ)</span><input className="input" type="number" step="0.01" value={cleaning} onChange={(e) => setCleaning(e.target.value)} /></label>
                <label className="field"><span className="field__label">Đổi màu (giờ/màu)</span><input className="input" type="number" step="0.01" value={colorChange} onChange={(e) => setColorChange(e.target.value)} /></label>
                <label className="field"><span className="field__label">Đổi kẽm (giờ/bản)</span><input className="input" type="number" step="0.01" value={plateChange} onChange={(e) => setPlateChange(e.target.value)} /></label>
                <label className="field"><span className="field__label">Kiểm/canh màu (giờ)</span><input className="input" type="number" step="0.01" value={colorCheck} onChange={(e) => setColorCheck(e.target.value)} /></label>
                <label className="field"><span className="field__label">Min setup (giờ)</span><input className="input" type="number" step="0.01" value={minSetup} onChange={(e) => setMinSetup(e.target.value)} /></label>
                <label className="field"><span className="field__label">Max setup (giờ)</span><input className="input" type="number" step="0.01" value={maxSetup} onChange={(e) => setMaxSetup(e.target.value)} /></label>
                <label className="field"><span className="field__label">Hao giấy setup (tờ)</span><input className="input" type="number" value={setupWaste} onChange={(e) => setSetupWaste(e.target.value)} /></label>
                <label className="field"><span className="field__label">(Fallback) setup (phút)</span><input className="input" type="number" value={setupMins} onChange={(e) => setSetupMins(e.target.value)} /></label>
                <label className="field"><span className="field__label">(Fallback) đổi bài (phút)</span><input className="input" type="number" value={changeover} onChange={(e) => setChangeover(e.target.value)} /></label>
              </div>
              <p className="field__hint" style={{ marginTop: 8 }}>Đây là <strong>thời gian</strong> để tính giờ máy. Hao giấy setup/makeready nằm ở trang Định mức & Bù hao. Nếu để trống các ô giờ → engine dùng fallback (phút).</p>
            </>
          )}

          {tab === 4 && (
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Overhead đã bao gồm</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="mc-oh" checked={overheadIncl} onChange={(e) => setOverheadIncl(e.target.checked)} /><label htmlFor="mc-oh">Overhead xưởng nằm trong đơn giá giờ</label></div></label>
              <label className="field"><span className="field__label">Nhân công vận hành bao gồm</span>
                <div className="md-page__toggle-wrap"><input type="checkbox" id="mc-op" checked={operatorIncl} onChange={(e) => setOperatorIncl(e.target.checked)} /><label htmlFor="mc-op">Đơn giá giờ đã gồm nhân công chính</label></div></label>
              <div className="field" style={{ gridColumn: "1 / -1" }}><span className="field__hint">Đơn giá giờ máy (đ/giờ) + cấu thành tham khảo được nhập ở nút <strong>"Giá giờ"</strong> (versioned theo ngày hiệu lực).</span></div>
            </div>
          )}

          {tab === 5 && (
            <div className="md-page__form-grid">
              <div className="field" style={{ gridColumn: "1 / -1" }}><span className="field__label">Khổ giấy phù hợp (trống = tất cả)</span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 4 }}>
                  {paperOptions.map((p) => (
                    <label key={p.id} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                      <input type="checkbox" checked={paperIds.includes(p.id)}
                        onChange={(e) => setPaperIds((prev) => e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id))} />
                      {p.name} ({p.width_cm}×{p.height_cm})
                    </label>
                  ))}
                </div>
              </div>
              <div className="field" style={{ gridColumn: "1 / -1" }}><span className="field__label">Chất liệu hỗ trợ</span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 4 }}>
                  {MAT_CHOICES.map((c) => (
                    <label key={c.value} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                      <input type="checkbox" checked={materials.includes(c.value)}
                        onChange={() => setMaterials((prev) => prev.includes(c.value) ? prev.filter((x) => x !== c.value) : [...prev, c.value])} />
                      {c.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === 6 && (
            <MachineQuickTest
              speed={Number(speed) || 0}
              setup={{
                base: num(setupBase), perColor: num(setupPerColor), perSide: num(setupPerSide),
                cleaning: num(cleaning), colorChange: num(colorChange), plateChange: num(plateChange),
                colorCheck: num(colorCheck), minSetup: num(minSetup), maxSetup: maxSetup ? Number(maxSetup) : null,
                fallbackMins: num(setupMins) + num(changeover),
              }}
              rounding={rounding}
              defaultRate={src?.rates.find((r) => r.effective_to === null)?.hourly_rate ?? 500000}
            />
          )}

          {error && <div className="banner banner--error" role="alert">{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>{isEdit ? "Lưu" : "Tạo máy"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

type SetupCfg = {
  base: number; perColor: number; perSide: number; cleaning: number; colorChange: number;
  plateChange: number; colorCheck: number; minSetup: number; maxSetup: number | null; fallbackMins: number;
};

function computeSetup(cfg: SetupCfg, colors: number, sides: number, plates: number): number {
  const gran = cfg.base + cfg.perColor * colors + cfg.perSide * sides + cfg.cleaning
    + cfg.colorChange * colors + cfg.plateChange * plates + cfg.colorCheck;
  if (gran > 0) {
    let s = gran;
    if (cfg.minSetup && s < cfg.minSetup) s = cfg.minSetup;
    if (cfg.maxSetup != null && s > cfg.maxSetup) s = cfg.maxSetup;
    return s;
  }
  return cfg.fallbackMins / 60;
}
function roundHours(h: number, policy: MachineRoundingPolicy): number {
  if (policy === "none") return h;
  const step = Number(policy);
  return Math.ceil(h / step) * step;
}

function MachineQuickTest({ speed, setup, rounding, defaultRate }: {
  speed: number; setup: SetupCfg; rounding: MachineRoundingPolicy; defaultRate: number;
}) {
  const [sheets, setSheets] = useState("3000");
  const [pass, setPass] = useState("1");
  const [colors, setColors] = useState("4");
  const [plates, setPlates] = useState("4");
  const [sides, setSides] = useState("1");
  const [testSpeed, setTestSpeed] = useState(String(speed || 6000));
  const [rate, setRate] = useState(String(defaultRate));

  const sp = Number(testSpeed) || 1;
  const machineSheets = (Number(sheets) || 0) * (Number(pass) || 1);
  const run = machineSheets / sp;
  const setupH = computeSetup(setup, Number(colors) || 0, Number(sides) || 0, Number(plates) || 0);
  const totalH = roundHours(run + setupH, rounding);
  const cost = totalH * (Number(rate) || 0);

  const field = (v: string, set: (s: string) => void, label: string) => (
    <label className="field"><span className="field__label">{label}</span><input className="input" type="number" value={v} onChange={(e) => set(e.target.value)} /></label>
  );

  return (
    <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
      <div className="md-page__form-grid" style={{ flex: "1 1 300px" }}>
        {field(sheets, setSheets, "Số tờ sản xuất")}
        {field(pass, setPass, "Số lượt qua máy")}
        {field(colors, setColors, "Số màu")}
        {field(plates, setPlates, "Số bản kẽm")}
        {field(sides, setSides, "Số mặt")}
        {field(testSpeed, setTestSpeed, "Tốc độ (tờ/giờ)")}
        {field(rate, setRate, "Đơn giá giờ (đ)")}
      </div>
      <div style={{ flex: "1 1 300px", background: "var(--paper,rgba(20,19,15,.03))", border: "1px solid var(--rule-soft,#e5e7eb)", borderRadius: 8, padding: 14, fontSize: 13, lineHeight: 1.8 }}>
        <strong style={{ fontSize: 11, textTransform: "uppercase" }}>Preview công in</strong>
        <div style={{ marginTop: 8 }}>Số tờ tính giờ máy = {sheets} × {pass} = <strong>{machineSheets.toLocaleString("vi-VN")}</strong> tờ</div>
        <div>Giờ chạy = {machineSheets} / {testSpeed} = <strong>{run.toFixed(2)}</strong> giờ</div>
        <div>Giờ setup = <strong>{setupH.toFixed(2)}</strong> giờ</div>
        <div style={{ marginTop: 6 }}>Tổng giờ máy = <strong>{totalH.toFixed(2)}</strong> giờ</div>
        <div style={{ marginTop: 6, color: "var(--rust)" }}>Công in = {totalH.toFixed(2)} × {Number(rate).toLocaleString("vi-VN")} = <strong>{Math.round(cost).toLocaleString("vi-VN")}đ</strong></div>
      </div>
    </div>
  );
}

function MachineRatesDialog({ machine, onClose, onSaved }: { machine: MachineRow; onClose: () => void; onSaved: () => void }) {
  const { token } = useAuth();
  const [rates, setRates] = useState<MachineRateRow[]>([]);
  const [hourlyRate, setHourlyRate] = useState("");
  const [minCharge, setMinCharge] = useState("0");
  const [minRunTime, setMinRunTime] = useState("0");
  const [dep, setDep] = useState("0");
  const [energy, setEnergy] = useState("0");
  const [maint, setMaint] = useState("0");
  const [labor, setLabor] = useState("0");
  const [overhead, setOverhead] = useState("0");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRates = useCallback(() => {
    if (!token) return;
    api.machines.get(token, machine.id).then((res) => setRates(res.rates)).catch(() => setError("Không tải được biểu giá."));
  }, [token, machine.id]);
  useEffect(() => { loadRates(); }, [loadRates]);

  const bd = num(dep) + num(energy) + num(maint) + num(labor) + num(overhead);

  async function handleAddRate(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    const hr = Number(hourlyRate);
    if (!hourlyRate.trim() || hr < 0) return setError("Đơn giá giờ máy phải ≥ 0.");
    const payload: MachineRateInput = {
      hourly_rate: hr, min_charge: num(minCharge), min_run_time_mins: num(minRunTime),
      rate_depreciation: num(dep), rate_energy: num(energy), rate_maintenance: num(maint),
      rate_labor: num(labor), rate_overhead: num(overhead), effective_from: effectiveFrom,
    };
    setSaving(true);
    try {
      await api.machines.addRate(token, machine.id, payload);
      setHourlyRate("");
      loadRates();
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu đơn giá thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>Đơn giá giờ máy: {machine.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <form className="md-page__rates-form" onSubmit={handleAddRate}>
            <h3 className="md-page__section-title">Đơn giá giờ mới (versioned theo ngày)</h3>
            <div className="md-page__form-grid">
              <label className="field"><span className="field__label">Đơn giá giờ (đ) *</span><input className="input" type="number" value={hourlyRate} onChange={(e) => setHourlyRate(e.target.value)} /></label>
              <label className="field"><span className="field__label">Min charge (đ)</span><input className="input" type="number" value={minCharge} onChange={(e) => setMinCharge(e.target.value)} /></label>
              <label className="field"><span className="field__label">Giờ chạy tối thiểu (phút)</span><input className="input" type="number" value={minRunTime} onChange={(e) => setMinRunTime(e.target.value)} /></label>
              <label className="field"><span className="field__label">Ngày hiệu lực *</span><input className="input" type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} /></label>
              <label className="field"><span className="field__label">Khấu hao (đ/giờ)</span><input className="input" type="number" value={dep} onChange={(e) => setDep(e.target.value)} /></label>
              <label className="field"><span className="field__label">Điện/vật tư phụ (đ/giờ)</span><input className="input" type="number" value={energy} onChange={(e) => setEnergy(e.target.value)} /></label>
              <label className="field"><span className="field__label">Bảo trì (đ/giờ)</span><input className="input" type="number" value={maint} onChange={(e) => setMaint(e.target.value)} /></label>
              <label className="field"><span className="field__label">Nhân công (đ/giờ)</span><input className="input" type="number" value={labor} onChange={(e) => setLabor(e.target.value)} /></label>
              <label className="field"><span className="field__label">Overhead xưởng (đ/giờ)</span><input className="input" type="number" value={overhead} onChange={(e) => setOverhead(e.target.value)} /></label>
              <div className="field"><span className="field__hint">Tổng cấu thành: <strong>{bd.toLocaleString("vi-VN")}đ</strong> {hourlyRate && bd > 0 && bd !== Number(hourlyRate) ? "(≠ đơn giá — chỉ tham khảo)" : ""}</span></div>
              <div className="md-page__field-btn-align md-page__form-wide"><Button type="submit" variant="primary" loading={saving}>Áp dụng đơn giá</Button></div>
            </div>
          </form>
          {error && <div className="banner banner--error" role="alert">{error}</div>}
          <div className="md-page__costs-history">
            <h3 className="md-page__section-title">Lịch sử biểu giá</h3>
            <div className="md-page__tablewrap">
              <table className="md-page__table">
                <thead><tr><th>Giá giờ</th><th>Min charge</th><th>Từ</th><th>Đến</th><th>Trạng thái</th></tr></thead>
                <tbody>
                  {rates.length === 0 ? (
                    <tr><td colSpan={5} className="md-page__empty">Chưa có biểu giá.</td></tr>
                  ) : rates.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.hourly_rate.toLocaleString("vi-VN")}đ</strong></td>
                      <td>{r.min_charge.toLocaleString("vi-VN")}đ</td>
                      <td>{r.effective_from}</td>
                      <td>{r.effective_to ?? "—"}</td>
                      <td>{r.effective_to === null ? <span className="md-page__status-badge is-active">Hiện hành</span> : <span className="md-page__muted">Hết hạn</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="md-page__dialog-actions"><Button variant="ghost" onClick={onClose}>Đóng</Button></div>
        </div>
      </div>
    </div>
  );
}
