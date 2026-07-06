import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type PaperSizeRow,
  type PaperSizeInput,
  type PaperSizeGroup,
  type PaperSizeDuplicateRef,
  type PaperSizeUsageCosting,
  type MachineRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ImpositionDiagram } from "../components/ImpositionDiagram";
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
    return { usableW, usableH, straight: 0, rotated: 0, best: 0, rotatedWins: false };
  }
  const straight = Math.floor(usableW / pw) * Math.floor(usableH / ph);
  const rotated = Math.floor(usableW / ph) * Math.floor(usableH / pw);
  const best = allowRotate ? Math.max(straight, rotated) : straight;
  return { usableW, usableH, straight, rotated, best, rotatedWins: allowRotate && rotated > straight };
}

// ---- Máy phù hợp: tự suy ra từ thông số máy (client-side, cùng logic machines_too_small) ----
type FitStatus = "fit" | "over" | "under" | "unknown";

function isPrintMachine(m: MachineRow): boolean {
  return m.process_type === "in" || m.machine_group === "may_in";
}

function orientationFits(w: number, h: number, m: MachineRow): boolean {
  const maxW = m.max_width_cm as number, maxH = m.max_height_cm as number;
  const minW = m.min_width_cm ?? 0, minH = m.min_height_cm ?? 0;
  return w >= minW && w <= maxW && h >= minH && h <= maxH;
}

function machineFit(w: number, h: number, allowRotate: boolean, m: MachineRow): FitStatus {
  if (m.max_width_cm == null || m.max_height_cm == null) return "unknown"; // máy chưa khai khổ
  if (!(w > 0 && h > 0)) return "unknown";
  if (orientationFits(w, h, m) || (allowRotate && orientationFits(h, w, m))) return "fit";
  const exceedsAsIs = w > m.max_width_cm || h > m.max_height_cm;
  const exceedsRot = h > m.max_width_cm || w > m.max_height_cm;
  const tooBig = allowRotate ? exceedsAsIs && exceedsRot : exceedsAsIs;
  return tooBig ? "over" : "under"; // vượt khổ máy / nhỏ hơn khổ tối thiểu máy kẹp được
}

/** Máy NGƯỜI DÙNG đã chọn mà khổ không lọt (advisory) — chỉ để cảnh báo, không chặn. */
function unfitSelected(
  w: number, h: number, allowRotate: boolean, machines: MachineRow[], ids: number[] | null,
): MachineRow[] {
  if (!ids || ids.length === 0 || !(w > 0 && h > 0)) return [];
  const set = new Set(ids);
  return machines.filter((m) => set.has(m.id)).filter((m) => {
    const s = machineFit(w, h, allowRotate, m);
    return s === "over" || s === "under";
  });
}

const FIT_BADGE: Record<FitStatus, { cls: string; label: string }> = {
  fit: { cls: "ps-fit-badge--fit", label: "Phù hợp" },
  over: { cls: "ps-fit-badge--over", label: "Vượt khổ máy" },
  under: { cls: "ps-fit-badge--under", label: "Nhỏ hơn khổ tối thiểu" },
  unknown: { cls: "ps-fit-badge--unknown", label: "Máy chưa khai khổ" },
};

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
  const [machines, setMachines] = useState<MachineRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [q, setQ] = useState("");
  const [machineF, setMachineF] = useState("");
  const [tab, setTab] = useState<ListTab>("all");

  const [drawer, setDrawer] = useState<null | { existing: PaperSizeRow | null }>(null);
  const [usageFor, setUsageFor] = useState<PaperSizeRow | null>(null);
  const [historyFor, setHistoryFor] = useState<PaperSizeRow | null>(null);
  const [fitFor, setFitFor] = useState<PaperSizeRow | null>(null);
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

  useEffect(() => {
    if (!token) return;
    api.machines.list(token, { size: 200 }).then((r) => setMachines(r.items)).catch(() => {});
  }, [token]);

  // Phát hiện trùng khổ (cùng kích thước, khác mã) trong danh sách hiện hành → cảnh báo.
  const dupIds = useMemo(() => {
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

  // Máy NGƯỜI DÙNG chọn nhưng khổ không lọt (advisory) — cho cột + tab cảnh báo. Không tự suy máy.
  const badPickedById = useMemo(() => {
    const map = new Map<number, MachineRow[]>();
    for (const r of rows)
      map.set(r.id, unfitSelected(r.width_cm, r.height_cm, r.allow_rotation, machines, r.compatible_machine_ids));
    return map;
  }, [rows, machines]);

  const warnIds = useMemo(() => {
    const ids = new Set<number>(dupIds);
    for (const r of rows) {
      if (r.is_active && (badPickedById.get(r.id)?.length ?? 0) > 0) ids.add(r.id);
    }
    return ids;
  }, [rows, badPickedById, dupIds]);

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
    const machineId = machineF ? Number(machineF) : null;
    const machine = machineId ? machines.find((m) => m.id === machineId) : null;
    return rows.filter((r) => {
      if (tab === "buy" && !r.is_purchase_size) return false;
      if (tab === "print" && !r.is_print_sheet_size) return false;
      if (tab === "cut" && !r.is_cut_size) return false;
      if (tab === "inactive" && r.is_active) return false;
      if (tab === "warning" && !warnIds.has(r.id)) return false;
      if (machine) {
        const picked = r.compatible_machine_ids;
        const applies = !picked || picked.length === 0 || picked.includes(machine.id);
        if (!applies) return false; // "Áp dụng cho máy X" = mọi-máy hoặc có tick X
      }
      if (needle) {
        const hay = `${r.code} ${r.name} ${r.width_cm}×${r.height_cm}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [rows, tab, q, machineF, machines, warnIds]);

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
        <select
          className="input md-page__filter"
          value={machineF}
          onChange={(e) => setMachineF(e.target.value)}
          aria-label="Lọc theo máy phù hợp"
        >
          <option value="">Mọi máy áp dụng</option>
          {machines.filter(isPrintMachine).map((m) => (
            <option key={m.id} value={m.id}>Áp dụng cho {m.name}</option>
          ))}
        </select>
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
              <th>Máy phù hợp</th>
              <th>Đang dùng trong</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="md-page__status" role="status">Đang tải dữ liệu…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={7} className="md-page__empty">Không có khổ giấy nào khớp bộ lọc.</td></tr>
            ) : (
              filtered.map((row) => {
                const used = isUsed(row);
                const picked = row.compatible_machine_ids ?? [];
                const badPicked = badPickedById.get(row.id) ?? [];
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
                      {picked.length === 0 ? (
                        <span className="md-page__muted">Mọi máy</span>
                      ) : (
                        <button
                          type="button"
                          className={`ps-fit-link${badPicked.length ? " ps-fit-zero" : ""}`}
                          title={badPicked.length ? `Khổ không lọt: ${badPicked.map((m) => m.name).join(", ")}` : undefined}
                          onClick={() => setFitFor(row)}
                        >
                          {badPicked.length > 0 ? "⚠ " : ""}{picked.length} máy
                        </button>
                      )}
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
          machines={machines}
          allSizes={rows}
          onClose={() => setDrawer(null)}
          onSaved={() => { setDrawer(null); load(); }}
        />
      )}
      {fitFor && <MachineFitDialog row={fitFor} machines={machines} onClose={() => setFitFor(null)} />}
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
  const used = !!existing && (existing.used_in_costings > 0 || existing.used_count > 0);

  const [code] = useState(existing?.code ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const nameTouched = useRef(isEdit);
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

  // Mô phỏng số con
  const [tGripper, setTGripper] = useState("1");
  const [tEdge, setTEdge] = useState("0.5");
  const [tFinW, setTFinW] = useState("21");
  const [tFinH, setTFinH] = useState("29.7");
  const [tBleed, setTBleed] = useState("0.3");
  const [tGutter, setTGutter] = useState("0");

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

  const unfit = useMemo(
    () => unfitSelected(w, h, allowRotation, machines, machineIds.length ? machineIds : null),
    [w, h, allowRotation, machines, machineIds],
  );
  const pieces = useMemo(
    () => computePieces(w, h, num(tGripper), num(tEdge), num(tFinW), num(tFinH), num(tBleed), num(tGutter), allowRotation),
    [w, h, tGripper, tEdge, tFinW, tFinH, tBleed, tGutter, allowRotation],
  );
  const box = ratioBox(w, h);
  const parentOptions = allSizes.filter((s) => s.id !== existing?.id);
  const printMachines = machines.filter(isPrintMachine);

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
              <div className="field md-page__form-wide">
                <span className="field__label">Vai trò khổ</span>
                <div className="md-page__toggle-wrap" style={{ gap: 18, flexWrap: "wrap" }}>
                  <label title="Khổ dùng để mua giấy (quy đổi tiền giấy theo ram/kg)." style={{ display: "flex", gap: 5, alignItems: "center" }}>
                    <input type="checkbox" checked={isPurchase} onChange={(e) => setIsPurchase(e.target.checked)} /> Khổ mua
                  </label>
                  <label title="Khổ tờ in để bình bài, tính số con trên tờ." style={{ display: "flex", gap: 5, alignItems: "center" }}>
                    <input type="checkbox" checked={isPrint} onChange={(e) => setIsPrint(e.target.checked)} /> Khổ tờ in
                  </label>
                  <label title="Khổ cắt ra từ khổ lớn hơn (có khổ cha)." style={{ display: "flex", gap: 5, alignItems: "center" }}>
                    <input type="checkbox" checked={isCut} onChange={(e) => setIsCut(e.target.checked)} /> Khổ cắt
                  </label>
                </div>
              </div>
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
                <label className="field">
                  <span className="field__label">Xoay chiều</span>
                  <div className="md-page__toggle-wrap">
                    <input type="checkbox" id="ps-rot" checked={allowRotation} onChange={(e) => setAllowRotation(e.target.checked)} />
                    <label htmlFor="ps-rot">Cho phép xoay khi tính số con</label>
                  </div>
                  {w > 0 && h > 0 && (pieces.straight > 0 || pieces.rotated > 0) && (
                    <span className="field__hint">
                      Với TP {num(tFinW)}×{num(tFinH)}: tắt <strong>{pieces.straight}</strong> con · bật{" "}
                      <strong>{Math.max(pieces.straight, pieces.rotated)}</strong> con/tờ
                      {pieces.rotated > pieces.straight ? ` (+${pieces.rotated - pieces.straight})` : " (không đổi)"}
                    </span>
                  )}
                </label>
              </div>
              <div className="ir-split__aside">
                <div className="ps-ratio">
                  <span className="ps-ratio__cap">Tỷ lệ khổ giấy</span>
                  <div className="ps-ratio__frame">
                    {box.width > 0 ? (
                      <div className="ps-ratio__box" style={{ width: box.width, height: box.height }}>
                        {allowRotation && <span className="ps-ratio__rot" title="Đang thử cả 2 chiều khi tính số con">↻</span>}
                      </div>
                    ) : (
                      <span className="md-page__muted" style={{ fontSize: 12 }}>Nhập rộng/cao để xem</span>
                    )}
                  </div>
                  {box.width > 0 && <span className="ps-ratio__cap">{w} × {h} cm</span>}
                </div>
              </div>
            </div>
            <p className="field__hint" style={{ marginTop: 6 }}>
              Khi bật “Cho phép xoay”, engine thử cả {w || "79"}×{h || "109"} và {h || "109"}×{w || "79"} để ra nhiều con hơn trên tờ.
            </p>
            {dupMatch && (
              <div className="ir-warn" role="status" style={{ marginTop: 8 }}>
                Đã tồn tại khổ <strong>{dupMatch.name}</strong> ({dupMatch.code} · {dupMatch.width_cm}×{dupMatch.height_cm}) trùng kích thước
                {" "}(kể cả xoay). Cân nhắc dùng khổ hiện có thay vì tạo trùng.
              </div>
            )}
          </div>

          {/* 3 — Khổ cắt (chỉ khi là khổ cắt) */}
          {isCut && (
            <div>
              <div className="ps-sec">3 · Quan hệ khổ cắt</div>
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
            </div>
          )}

          {/* 4 — Máy áp dụng: NGƯỜI DÙNG tự chọn; hệ thống chỉ cảnh báo nếu khổ không lọt */}
          <div>
            <div className="ps-sec">4 · Máy áp dụng</div>
            <p className="field__hint" style={{ marginTop: 0 }}>
              Tự chọn máy khổ này chạy được. <strong>Bỏ trống = áp dụng mọi máy.</strong> Hệ thống chỉ{" "}
              <strong>cảnh báo</strong> nếu khổ không lọt máy bạn chọn — không tự quyết, không chặn.
            </p>
            <div className="md-page__toggle-wrap" style={{ gap: 16, flexWrap: "wrap" }}>
              {printMachines.length === 0 && <span className="md-page__muted">Chưa có máy in nào trong danh mục.</span>}
              {printMachines.map((m) => {
                const st: FitStatus = w > 0 && h > 0 ? machineFit(w, h, allowRotation, m) : "unknown";
                const on = machineIds.includes(m.id);
                return (
                  <label key={m.id} style={{ display: "flex", gap: 5, alignItems: "center" }}>
                    <input type="checkbox" checked={on} onChange={() => toggleMachine(m.id)} />
                    {m.name}
                    {m.max_width_cm != null && (
                      <span className="md-page__muted" style={{ fontSize: 11 }}> ({m.max_width_cm}×{m.max_height_cm})</span>
                    )}
                    {on && (st === "over" || st === "under") && (
                      <span className={`ps-fit-badge ${FIT_BADGE[st].cls}`} style={{ marginLeft: 2 }}>{FIT_BADGE[st].label}</span>
                    )}
                  </label>
                );
              })}
            </div>
            {unfit.length > 0 && (
              <div className="ir-warn" role="status" style={{ marginTop: 8 }}>
                ⚠ Khổ {w}×{h} có thể không lọt máy bạn chọn: <strong>{unfit.map((m) => m.name).join(", ")}</strong>. Vẫn lưu được nếu bạn chắc chắn.
              </div>
            )}
            {machineIds.length > 0 && (
              <label className="field" style={{ maxWidth: 320, marginTop: 10 }}>
                <span className="field__label">Khổ mặc định cho máy (gợi ý ở Tính giá)</span>
                <select className="input select" value={defaultMachine} onChange={(e) => setDefaultMachine(e.target.value)}>
                  <option value="">-- Không --</option>
                  {printMachines.filter((m) => machineIds.includes(m.id)).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </label>
            )}
          </div>

          {/* 5 — Hiệu lực */}
          <div>
            <div className="ps-sec">5 · Hiệu lực</div>
            <label className="field" style={{ maxWidth: 240 }}>
              <span className="field__label">Áp dụng từ ngày</span>
              <input className="input" type="date" value={effectiveFrom ?? ""} onChange={(e) => setEffectiveFrom(e.target.value)} />
            </label>
          </div>

          {/* 6 — Mô phỏng số con */}
          <div>
            <div className="ps-sec">6 · Mô phỏng số con</div>
            <div className="ir-split">
              <div className="ir-split__form md-page__form-grid">
                <label className="field"><span className="field__label">Khổ TP rộng (cm)</span>
                  <input className="input" type="number" step="0.1" value={tFinW} onChange={(e) => setTFinW(e.target.value)} /></label>
                <label className="field"><span className="field__label">Khổ TP cao (cm)</span>
                  <input className="input" type="number" step="0.1" value={tFinH} onChange={(e) => setTFinH(e.target.value)} /></label>
                <label className="field"><span className="field__label">Bleed (cm)</span>
                  <input className="input" type="number" step="0.1" value={tBleed} onChange={(e) => setTBleed(e.target.value)} /></label>
                <label className="field"><span className="field__label">Chừa giữa con (cm)</span>
                  <input className="input" type="number" step="0.1" value={tGutter} onChange={(e) => setTGutter(e.target.value)} /></label>
                <label className="field"><span className="field__label">Nhíp máy (cm)</span>
                  <input className="input" type="number" step="0.1" value={tGripper} onChange={(e) => setTGripper(e.target.value)} /></label>
                <label className="field"><span className="field__label">Xén mép (cm)</span>
                  <input className="input" type="number" step="0.1" value={tEdge} onChange={(e) => setTEdge(e.target.value)} /></label>
              </div>
              <div className="ir-split__aside">
                <div className="ir-panel">
                  <span className="ir-panel__title">Kết quả mô phỏng</span>
                  {w > 0 && h > 0 ? (
                    <>
                      <div className="ir-panel__row">Khổ giấy: <strong>{w}×{h}</strong> · TP: <strong>{num(tFinW)}×{num(tFinH)}</strong></div>
                      <div className="ir-panel__row">Khổ in khả dụng: <strong>{pieces.usableW.toFixed(1)}×{pieces.usableH.toFixed(1)} cm</strong></div>
                      <div className="ir-panel__row" style={{ marginTop: 6 }}>
                        <span className="ps-sim-hero">{pieces.best} <small>con/tờ</small></span>
                      </div>
                      <div className="ir-panel__row md-page__muted">
                        Không xoay {pieces.straight} · Xoay {pieces.rotated}
                        {pieces.rotatedWins && <> — phương án tốt nhất: <strong>xoay ngang</strong></>}
                        {!allowRotation && <> — (đang tắt xoay)</>}
                      </div>
                      {pieces.best === 0 && (
                        <div className="md-page__danger-text" style={{ marginTop: 4 }}>⚠ Thành phẩm không lọt khổ in — kiểm tra lại kích thước.</div>
                      )}
                      <div className="ps-sim-diagram">
                        <ImpositionDiagram
                          input={{
                            sheetW: w, sheetH: h,
                            finishedW: num(tFinW), finishedH: num(tFinH),
                            gripperCm: num(tGripper), edgeTrimCm: num(tEdge),
                            bleedCm: num(tBleed), gutterCm: num(tGutter),
                            grainLocked: !allowRotation,
                          }}
                        />
                        <span className="ps-ratio__cap">
                          {allowRotation ? "Đang cho xoay — engine chọn chiều nhiều con hơn" : "Đang tắt xoay — giữ đúng chiều thớ"}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="md-page__muted" style={{ fontSize: 13 }}>Nhập rộng/cao ở mục 2 để xem số con.</div>
                  )}
                </div>
              </div>
            </div>
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
// Dialog: máy phù hợp (chi tiết fit)
// ---------------------------------------------------------------------------
function MachineFitDialog({ row, machines, onClose }: { row: PaperSizeRow; machines: MachineRow[]; onClose: () => void }) {
  const pickedIds = row.compatible_machine_ids ?? [];
  const picked = machines.filter((m) => pickedIds.includes(m.id));
  return (
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 620 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head">
          <h2>Máy áp dụng: {row.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <p className="md-page__note">
            Khổ <span className="md-page__mono">{row.width_cm}×{row.height_cm} cm</span>{row.allow_rotation ? " (cho xoay)" : " (không xoay)"} — do người dùng chọn.
            Cột “Kết quả” chỉ là <strong>kiểm tra tham khảo</strong> khổ có lọt máy hay không.
          </p>
          {picked.length === 0 ? (
            <p className="md-page__empty">Áp dụng mọi máy — không giới hạn.</p>
          ) : (
            <table className="md-page__table">
              <thead>
                <tr><th>Máy</th><th>Khổ máy (min → max)</th><th>Kết quả</th></tr>
              </thead>
              <tbody>
                {picked.map((m) => {
                  const status = machineFit(row.width_cm, row.height_cm, row.allow_rotation, m);
                  return (
                    <tr key={m.id}>
                      <td>{m.name}</td>
                      <td className="md-page__muted" style={{ fontSize: 12 }}>
                        {m.max_width_cm == null ? "—" : `${m.min_width_cm ?? 0}×${m.min_height_cm ?? 0} → ${m.max_width_cm}×${m.max_height_cm}`}
                      </td>
                      <td><span className={`ps-fit-badge ${FIT_BADGE[status].cls}`}>{FIT_BADGE[status].label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
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
