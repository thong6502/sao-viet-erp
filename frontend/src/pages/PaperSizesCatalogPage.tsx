import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type PaperSizeRow,
  type PaperSizeInput,
  type PaperSizeGroup,
  type PaperSizeDuplicateRef,
  type PaperSizeUsageCosting,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";
import "./imposition-rules.css";
import "./paper-sizes.css";

// ---------------------------------------------------------------------------
// Hằng số nhãn
// ---------------------------------------------------------------------------
const SIZE_GROUPS: { value: PaperSizeGroup; label: string }[] = [
  { value: "cong_nghiep", label: "Khổ công nghiệp" },
  { value: "kho_a", label: "Khổ A" },
  { value: "kho_cat", label: "Khổ cắt" },
  { value: "custom", label: "Tùy chỉnh" },
];

type ListTab = "all" | "buy" | "print" | "cut" | "inactive" | "warning";
const COSTING_STATUS_LABEL: Record<string, string> = { draft: "Nháp", ready: "Sẵn sàng" };

// ---------------------------------------------------------------------------
// Tiện ích thuần
// ---------------------------------------------------------------------------
function num(v: string): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function roleParts(row: {
  is_purchase_size: boolean;
  is_print_sheet_size: boolean;
  is_cut_size: boolean;
}): { label: string; cls: string }[] {
  const parts: { label: string; cls: string }[] = [];
  if (row.is_purchase_size) parts.push({ label: "Khổ mua", cls: "ps-role--buy" });
  if (row.is_print_sheet_size) parts.push({ label: "Khổ tờ in", cls: "ps-role--print" });
  if (row.is_cut_size) parts.push({ label: "Khổ cắt", cls: "ps-role--cut" });
  return parts;
}


function ratioBox(w: number, h: number, max = 150): { width: number; height: number } {
  if (!(w > 0 && h > 0)) return { width: 0, height: 0 };
  const scale = max / Math.max(w, h);
  return { width: Math.max(12, Math.round(w * scale)), height: Math.max(12, Math.round(h * scale)) };
}

// Chuẩn hóa "khổ" theo cả 2 chiều để phát hiện trùng khổ trong danh sách.
function dimKey(w: number, h: number): string {
  const a = Math.round(w * 100), b = Math.round(h * 100);
  return a <= b ? `${a}x${b}` : `${b}x${a}`;
}

// ---------------------------------------------------------------------------
// Trang danh sách
// ---------------------------------------------------------------------------
export function PaperSizesCatalogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<PaperSizeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [q, setQ] = useState("");
  const [tab, setTab] = useState<ListTab>("all");

  const [drawer, setDrawer] = useState<null | { existing: PaperSizeRow | null }>(null);
  const [usageFor, setUsageFor] = useState<PaperSizeRow | null>(null);
  const [historyFor, setHistoryFor] = useState<PaperSizeRow | null>(null);
  const [deleting, setDeleting] = useState<PaperSizeRow | null>(null);
  const [menuFor, setMenuFor] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.paperSizes
      .list(token, { current_only: true, size: 200 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục khổ giấy.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => { load(); }, [load]);

  // Phát hiện trùng khổ (cùng kích thước, khác mã) → cảnh báo.
  const warnIds = useMemo(() => {
    const byDim = new Map<string, PaperSizeRow[]>();
    for (const r of rows) {
      const k = dimKey(r.width_cm, r.height_cm);
      (byDim.get(k) ?? byDim.set(k, []).get(k)!).push(r);
    }
    const ids = new Set<number>();
    for (const group of byDim.values()) {
      const codes = new Set(group.map((r) => r.code));
      if (codes.size > 1) group.forEach((r) => ids.add(r.id));
    }
    return ids;
  }, [rows]);

  const counts = useMemo(
    () => ({
      all: rows.length,
      buy: rows.filter((r) => r.is_purchase_size).length,
      print: rows.filter((r) => r.is_print_sheet_size).length,
      cut: rows.filter((r) => r.is_cut_size).length,
      inactive: rows.filter((r) => !r.is_active).length,
      warning: warnIds.size,
    }),
    [rows, warnIds],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (tab === "buy" && !r.is_purchase_size) return false;
      if (tab === "print" && !r.is_print_sheet_size) return false;
      if (tab === "cut" && !r.is_cut_size) return false;
      if (tab === "inactive" && r.is_active) return false;
      if (tab === "warning" && !warnIds.has(r.id)) return false;
      if (needle) {
        const hay = `${r.code} ${r.name} ${r.width_cm}×${r.height_cm}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [rows, tab, q, warnIds]);

  const isUsed = (r: PaperSizeRow) => r.used_in_costings > 0 || r.used_count > 0;

  const toggleActive = useCallback(
    async (row: PaperSizeRow) => {
      if (!token) return;
      setMenuFor(null);
      try {
        await api.paperSizes.update(token, row.id, { ...rowToInput(row), is_active: !row.is_active });
        load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không đổi được trạng thái.");
      }
    },
    [token, load],
  );

  const handleClone = useCallback(
    async (row: PaperSizeRow) => {
      if (!token) return;
      setMenuFor(null);
      try {
        await api.paperSizes.clone(token, row.id);
        load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không sao chép được.");
      }
    },
    [token, load],
  );

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
          Danh mục kích thước giấy dùng cho phiếu tính giá. Engine dùng khổ này để tính{" "}
          <strong>số con trên tờ</strong>, <strong>số tờ sản xuất</strong>, <strong>hao hụt</strong> và{" "}
          <strong>quy đổi tiền giấy</strong>. Khổ đã dùng trong phiếu không sửa/xóa trực tiếp — tạo phiên bản mới.
        </p>
      </header>

      <div className="md-page__toolbar">
        <div className="md-page__search">
          <input
            className="input"
            placeholder="Tìm theo mã / tên / kích thước…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="md-page__toolbar-spacer" />
        <Button variant="primary" onClick={() => { setMenuFor(null); setDrawer({ existing: null }); }}>
          + Tạo khổ giấy
        </Button>
      </div>

      <div className="ir-tabs">
        {([
          ["all", "Tất cả", counts.all, false],
          ["buy", "Khổ mua", counts.buy, false],
          ["print", "Khổ tờ in", counts.print, false],
          ["cut", "Khổ cắt", counts.cut, false],
          ["inactive", "Tạm ngừng", counts.inactive, false],
          ["warning", "⚠ Có cảnh báo", counts.warning, true],
        ] as [ListTab, string, number, boolean][]).map(([key, label, n, warn]) => (
          <button
            key={key}
            type="button"
            className={`ir-tab${tab === key ? " ir-tab--active" : ""}${warn ? " ir-tab--warn" : ""}`}
            onClick={() => setTab(key)}
          >
            {label}
            <span className="ir-tab__count">{n}</span>
          </button>
        ))}
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
              <th>Khổ giấy</th>
              <th>Kích thước</th>
              <th>Vai trò</th>
              <th>Đang dùng trong</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="md-page__status" role="status">Đang tải dữ liệu…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={6} className="md-page__empty">Không có khổ giấy nào khớp bộ lọc.</td></tr>
            ) : (
              filtered.map((row) => {
                const used = isUsed(row);
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => openRow(row)}>
                    <td>
                      <div><strong>{row.name}</strong></div>
                      <div className="md-page__mono md-page__muted">
                        {row.code}{row.version > 1 && <span className="md-page__tag" style={{ marginLeft: 4 }}>v{row.version}</span>}
                      </div>
                    </td>
                    <td>
                      <div>{row.width_cm} × {row.height_cm} cm</div>
                      <div className="md-page__muted" style={{ fontSize: 12 }}>{row.area_m2?.toFixed(4)} m²</div>
                    </td>
                    <td>
                      <div className="md-page__tag-group">
                        {roleParts(row).map((p) => <span key={p.label} className={`ps-role ${p.cls}`}>{p.label}</span>)}
                        {roleParts(row).length === 0 && <span className="md-page__muted">—</span>}
                      </div>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {row.used_in_costings > 0 ? (
                        <button type="button" className="ir-usage-link" onClick={() => setUsageFor(row)}>
                          {row.used_in_costings} phiếu tính giá
                        </button>
                      ) : (
                        <span className="ir-usage-zero">0 phiếu</span>
                      )}
                    </td>
                    <td>
                      <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                        {row.is_active ? "Đang dùng" : "Tạm ngừng"}
                      </span>
                    </td>
                    <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => openRow(row)}>Mở</button>
                      <span className="ir-menu-wrap">
                        <button
                          type="button"
                          className="ir-iconbtn"
                          title="Thao tác khác"
                          aria-haspopup="menu"
                          onClick={() => setMenuFor(menuFor === row.id ? null : row.id)}
                        >
                          ⋯
                        </button>
                        {menuFor === row.id && (
                          <>
                            <div style={{ position: "fixed", inset: 0, zIndex: 29 }} onClick={() => setMenuFor(null)} />
                            <div className="ir-menu" role="menu">
                              <button type="button" onClick={() => openRow(row)}>
                                {used ? "Xem chi tiết" : "Chỉnh sửa"}
                              </button>
                              <button type="button" onClick={() => handleClone(row)}>Tạo bản sao</button>
                              <button type="button" onClick={() => toggleActive(row)}>
                                {row.is_active ? "Tạm ngừng sử dụng" : "Kích hoạt lại"}
                              </button>
                              {row.used_in_costings > 0 && (
                                <button type="button" onClick={() => { setMenuFor(null); setUsageFor(row); }}>
                                  Xem nơi đang dùng
                                </button>
                              )}
                              <button type="button" onClick={() => { setMenuFor(null); setHistoryFor(row); }}>
                                Lịch sử thay đổi
                              </button>
                              {!used && (
                                <>
                                  <div className="ir-menu__sep" />
                                  <button type="button" className="danger" onClick={() => { setMenuFor(null); setDeleting(row); }}>Xóa</button>
                                </>
                              )}
                            </div>
                          </>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {drawer && (
        <PaperSizeDrawer
          existing={drawer.existing}
          onClose={() => setDrawer(null)}
          onSaved={() => { setDrawer(null); load(); }}
        />
      )}
      {usageFor && <UsageDialog row={usageFor} onClose={() => setUsageFor(null)} />}
      {historyFor && <HistoryDialog row={historyFor} onClose={() => setHistoryFor(null)} />}
      {deleting && (
        <div className="md-page__overlay" role="dialog" onClick={() => setDeleting(null)}>
          <div className="md-page__dialog md-page__dialog--sm card" onClick={(e) => e.stopPropagation()}>
            <div className="md-page__dialog-head"><h2>Xác nhận xóa</h2></div>
            <div className="md-page__dialog-body">
              <p>Xóa khổ giấy <strong>{deleting.name}</strong> ({deleting.code})? Chỉ nên xóa khổ chưa dùng ở phiếu nào.</p>
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

  function openRow(row: PaperSizeRow) {
    setMenuFor(null);
    setDrawer({ existing: row });
  }
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

// ---------------------------------------------------------------------------
// Drawer tạo / sửa
// ---------------------------------------------------------------------------
function PaperSizeDrawer({
  existing, onClose, onSaved,
}: {
  existing: PaperSizeRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;
  const used = !!existing && (existing.used_in_costings > 0 || existing.used_count > 0);

  const [code] = useState(existing?.code ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const nameTouched = useRef(isEdit);
  const [group, setGroup] = useState<PaperSizeGroup>((existing?.size_group as PaperSizeGroup) ?? "cong_nghiep");
  const [note, setNote] = useState(existing?.note ?? "");
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [width, setWidth] = useState(existing ? String(existing.width_cm) : "");
  const [height, setHeight] = useState(existing ? String(existing.height_cm) : "");
  // Máy áp dụng / Xoay chiều / Hiệu lực / Mô phỏng đã bỏ khỏi form — chọn máy ở Tính giá.

  const [dupMatch, setDupMatch] = useState<PaperSizeDuplicateRef | null>(null);
  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const w = num(width), h = num(height);
  const area = w > 0 && h > 0 ? (w * h) / 10000 : 0;

  // Tên tự gợi ý từ kích thước cho tới khi người dùng tự sửa.
  useEffect(() => {
    if (!nameTouched.current && w > 0 && h > 0) setName(`Khổ ${w}×${h}`);
  }, [w, h]);

  // Cảnh báo trùng khổ (§13) — debounce gọi backend.
  useEffect(() => {
    if (!token || !(w > 0 && h > 0)) { setDupMatch(null); return; }
    const t = setTimeout(() => {
      api.paperSizes
        .checkDuplicate(token, { width: w, height: h, excludeId: existing?.id ?? null })
        .then((r) => setDupMatch(r.matched))
        .catch(() => setDupMatch(null));
    }, 350);
    return () => clearTimeout(t);
  }, [token, w, h, existing?.id]);

  const box = ratioBox(w, h);

  function buildPayload(): PaperSizeInput | null {
    if (!name.trim()) { setValidationError("Tên khổ giấy không được trống."); return null; }
    if (!(w > 0)) { setValidationError("Chiều rộng (cm) phải lớn hơn 0."); return null; }
    if (!(h > 0)) { setValidationError("Chiều cao (cm) phải lớn hơn 0."); return null; }
    // Gọn: mọi khổ chuẩn = khổ tờ in. Khái niệm khổ-mua / khổ-cắt / khổ mặc định theo máy
    // đã bỏ khỏi form (chưa nối vào tính giá) → luôn gửi mặc định.
    return {
      code: isEdit ? undefined : (code.trim() || undefined),
      name: name.trim(),
      size_group: group,
      is_purchase_size: false,
      is_print_sheet_size: true,
      is_cut_size: false,
      note: note.trim() ? note.trim() : null,
      is_active: isActive,
      width_cm: w,
      height_cm: h,
      allow_rotation: true,
      compatible_machine_ids: null,
      default_machine_id: null,
      parent_size_id: null,
      cut_count: null,
      cut_waste_rate: null,
      effective_from: null,
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

  return (
    <div className="ir-drawer-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="ir-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="ir-drawer__head">
          <div>
            <h2>{isEdit ? `Chỉnh sửa: ${existing?.name}` : "Tạo khổ giấy mới"}</h2>
            <div className="ir-drawer__head-sub">
              {existing
                ? <span className="md-page__mono">{existing.code} · v{existing.version}{used ? ` · đã dùng ${existing.used_in_costings} phiếu` : ""}</span>
                : "Khổ giấy dùng làm dữ liệu nền cho engine tính giá"}
            </div>
          </div>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>

        {used && (
          <div className="banner banner--info" role="status" style={{ margin: "12px 24px 0" }}>
            Khổ này đã dùng trong <strong>{existing?.used_in_costings}</strong> phiếu tính giá. Đổi <strong>kích thước</strong> sẽ{" "}
            <strong>tạo phiên bản mới</strong> (bản cũ đóng băng để báo giá cũ giữ số); sửa nhóm/vai trò/máy thì cập nhật tại chỗ.
          </div>
        )}

        <form className="ir-drawer__body" onSubmit={onSubmit}>
          {/* 1 — Thông tin khổ */}
          <div>
            <div className="ps-sec">1 · Thông tin khổ</div>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Tên khổ *</span>
                <input className="input" placeholder="VD: Khổ 79×109" value={name}
                  onChange={(e) => { nameTouched.current = true; setName(e.target.value); }} />
                {!nameTouched.current && <span className="field__hint">Tự gợi ý theo kích thước.</span>}
              </label>
              <label className="field">
                <span className="field__label">Mã khổ</span>
                <input className="input md-page__mono" placeholder={isEdit ? "" : "Tự sinh KG### nếu bỏ trống"}
                  value={code} disabled readOnly />
                <span className="field__hint">{isEdit ? "Mã không đổi sau khi tạo." : "Để hệ thống tự sinh."}</span>
              </label>
              <label className="field">
                <span className="field__label">Nhóm khổ</span>
                <select className="input select" value={group} onChange={(e) => setGroup(e.target.value as PaperSizeGroup)}>
                  {SIZE_GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Trạng thái</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="ps-active" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  <label htmlFor="ps-active">Đang dùng</label>
                </div>
              </label>
              <label className="field md-page__form-wide">
                <span className="field__label">Ghi chú</span>
                <input className="input" placeholder="Ghi chú (tùy chọn)" value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
          </div>

          {/* 2 — Kích thước + preview + cảnh báo trùng */}
          <div>
            <div className="ps-sec">2 · Kích thước</div>
            <div className="ir-split">
              <div className="ir-split__form md-page__form-grid">
                <label className="field">
                  <span className="field__label">Rộng (cm) *</span>
                  <input className="input" type="number" min="0" step="0.01" placeholder="VD: 79" value={width}
                    onChange={(e) => setWidth(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Cao (cm) *</span>
                  <input className="input" type="number" min="0" step="0.01" placeholder="VD: 109" value={height}
                    onChange={(e) => setHeight(e.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Diện tích (m²)</span>
                  <input className="input" value={area ? area.toFixed(4) : ""} disabled readOnly />
                </label>
              </div>
              <div className="ir-split__aside">
                <div className="ps-ratio">
                  <span className="ps-ratio__cap">Tỷ lệ khổ giấy</span>
                  <div className="ps-ratio__frame">
                    {box.width > 0 ? (
                      <div className="ps-ratio__box" style={{ width: box.width, height: box.height }} />
                    ) : (
                      <span className="md-page__muted" style={{ fontSize: 12 }}>Nhập rộng/cao để xem</span>
                    )}
                  </div>
                  {box.width > 0 && <span className="ps-ratio__cap">{w} × {h} cm</span>}
                </div>
              </div>
            </div>
            {dupMatch && (
              <div className="ir-warn" role="status" style={{ marginTop: 8 }}>
                Đã tồn tại khổ <strong>{dupMatch.name}</strong> ({dupMatch.code} · {dupMatch.width_cm}×{dupMatch.height_cm}) trùng kích thước
                {" "}(kể cả xoay). Cân nhắc dùng khổ hiện có thay vì tạo trùng.
              </div>
            )}
          </div>

          {validationError && <div className="banner banner--error" role="alert">{validationError}</div>}
        </form>

        <div className="ir-drawer__foot">
          <div />
          <div className="ir-drawer__foot-right">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            {isEdit && (
              <Button type="button" variant="secondary" loading={saving} onClick={() => submit(true)}>
                Lưu thành phiên bản mới
              </Button>
            )}
            <Button type="button" variant="primary" loading={saving} onClick={() => submit(false)}>
              {isEdit ? "Lưu" : "Lưu và kích hoạt"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dialog: nơi đang dùng (drill-down phiếu tính giá)
// ---------------------------------------------------------------------------
function UsageDialog({ row, onClose }: { row: PaperSizeRow; onClose: () => void }) {
  const { token } = useAuth();
  const [items, setItems] = useState<PaperSizeUsageCosting[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.paperSizes
      .usage(token, row.id)
      .then((r) => setItems(r.costings))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được danh sách phiếu."))
      .finally(() => setLoading(false));
  }, [token, row.id]);

  return (
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head">
          <h2>Nơi đang dùng: {row.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <p className="md-page__note">
            <span className="md-page__mono">{row.code}</span> — {row.used_in_costings} phiếu tính giá đang tham chiếu khổ này. Vì vậy khổ không xóa được (để giữ dữ liệu báo giá cũ).
          </p>
          {loading ? (
            <p className="md-page__status">Đang tải…</p>
          ) : err ? (
            <div className="banner banner--error">{err}</div>
          ) : items.length === 0 ? (
            <p className="md-page__empty">Chưa có phiếu tính giá nào.</p>
          ) : (
            <table className="md-page__table">
              <thead>
                <tr><th>Số phiếu</th><th>Sản phẩm</th><th>SL</th><th>Trạng thái</th><th>Ngày tạo</th></tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id}>
                    <td className="md-page__mono">{c.code}</td>
                    <td>{c.product_name ?? <span className="md-page__muted">—</span>}</td>
                    <td>{c.qty_final.toLocaleString("vi-VN")}</td>
                    <td>{COSTING_STATUS_LABEL[c.status] ?? c.status}</td>
                    <td style={{ fontSize: 12 }}>{new Date(c.created_at).toLocaleDateString("vi-VN")}</td>
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

// ---------------------------------------------------------------------------
// Dialog: lịch sử phiên bản
// ---------------------------------------------------------------------------
function HistoryDialog({ row, onClose }: { row: PaperSizeRow; onClose: () => void }) {
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
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 680 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head">
          <h2>Lịch sử phiên bản: {row.code}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          {err && <div className="banner banner--error">{err}</div>}
          {!items ? <p className="md-page__muted">Đang tải…</p> : (
            <table className="md-page__table">
              <thead>
                <tr><th>Phiên bản</th><th>Kích thước</th><th>Áp dụng từ</th><th>Đến</th><th>Đã dùng</th><th>Trạng thái</th></tr>
              </thead>
              <tbody>
                {items.map((v) => (
                  <tr key={v.id}>
                    <td className="md-page__mono">v{v.version}</td>
                    <td>{v.width_cm}×{v.height_cm} cm</td>
                    <td>{v.effective_from ?? <span className="md-page__muted">—</span>}</td>
                    <td>{v.effective_to ?? <span className="md-page__muted">Vô hạn</span>}</td>
                    <td>{v.used_in_costings}</td>
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
