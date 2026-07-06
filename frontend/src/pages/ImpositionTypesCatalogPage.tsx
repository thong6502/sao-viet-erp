import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type ImpositionTypeRow,
  type ImpositionTypeInput,
  type ImpositionGroupKind,
  type ImpositionAppliesToSides,
  type ImpositionPreviewOut,
  type ImpositionUsageEstimate,
  type ProductTypeCatalogRow,
  type MachineRow,
  type PaperSizeRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ImpositionSchematic } from "../components/ImpositionSchematic";
import "./master-data.css";
import "./imposition-rules.css";

// ---------------------------------------------------------------------------
// Hằng số nhãn
// ---------------------------------------------------------------------------
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

const APPLIES_SIDES_OPTIONS: { value: ImpositionAppliesToSides; label: string }[] = [
  { value: "any", label: "Mọi số mặt" },
  { value: "1", label: "Chỉ 1 mặt" },
  { value: "2", label: "Chỉ 2 mặt" },
  { value: "multi", label: "Nhiều mặt / nhiều trang" },
];
const APPLIES_SIDES_LABEL: Record<string, string> = Object.fromEntries(
  APPLIES_SIDES_OPTIONS.map((o) => [o.value, o.label]),
);

const STEPS = ["Thông tin", "Công thức", "Điều kiện", "Kiểm thử"];
type ListTab = "all" | "preset" | "custom" | "inactive" | "conflict";

// ---------------------------------------------------------------------------
// Tiện ích thuần
// ---------------------------------------------------------------------------
function fmt(n: number): string {
  return Number.isFinite(n) ? String(n) : "?";
}
function isPreset(row: ImpositionTypeRow): boolean {
  return row.group_kind !== "custom";
}
function prioBucket(priority: number): { cls: string; label: string } {
  if (priority <= 20) return { cls: "ir-prio--hi", label: "Ưu tiên cao" };
  if (priority <= 60) return { cls: "ir-prio--mid", label: "Trung bình" };
  return { cls: "ir-prio--lo", label: "Thấp" };
}

/** Chip tóm tắt "cách tính giá" — suy từ hệ số, ×1 làm mờ cho đỡ rối. */
function calcChips(row: ImpositionTypeRow): { label: string; muted: boolean }[] {
  const mk = (prefix: string, v: number) => ({ label: `${prefix} ×${fmt(v)}`, muted: v === 1 });
  return [
    mk("TP/tờ", row.finished_factor),
    mk("Máy", row.pass_count),
    mk("Kẽm", row.plate_set_factor),
    mk("Mực", row.ink_pass_factor),
  ];
}

function appliesLabel(row: ImpositionTypeRow, ptName: Record<string, string>): string {
  const pts = row.applicable_product_types;
  if (!pts || pts.length === 0) return "mọi loại SP";
  if (pts.length <= 2) return pts.map((c) => ptName[c] ?? c).join(", ");
  return `${pts.length} loại SP`;
}

// ---- Phát hiện xung đột rule (thuần client trên tập phiên bản đang hiệu lực) ----
function overlapNums(a: number[] | null, b: number[] | null): boolean {
  const aAll = !a || a.length === 0;
  const bAll = !b || b.length === 0;
  if (aAll || bAll) return true;
  return a!.some((x) => b!.includes(x));
}
function overlapStrs(a: string[] | null, b: string[] | null): boolean {
  const aAll = !a || a.length === 0;
  const bAll = !b || b.length === 0;
  if (aAll || bAll) return true;
  return a!.some((x) => b!.includes(x));
}
function sidesOverlap(a: ImpositionAppliesToSides, b: ImpositionAppliesToSides): boolean {
  if (a === "any" || b === "any") return true;
  return a === b;
}
function rulesConflict(a: ImpositionTypeRow, b: ImpositionTypeRow): boolean {
  if (!a.is_active || !b.is_active) return false;
  if (a.code === b.code) return false; // cùng mã = version-chain, không phải xung đột
  // Xung đột THỰC SỰ = trùng ưu tiên + trùng phạm vi ⇒ engine không có winner rõ ràng.
  // Khác ưu tiên thì thang ưu tiên đã tự phân xử (số nhỏ thắng) nên không coi là cảnh báo.
  if (a.priority !== b.priority) return false;
  if ((a.technology || "") !== (b.technology || "")) return false;
  if (!sidesOverlap(a.applies_to_sides, b.applies_to_sides)) return false;
  if (!overlapStrs(a.applicable_product_types, b.applicable_product_types)) return false;
  if (!overlapNums(a.applicable_machine_ids, b.applicable_machine_ids)) return false;
  if (!overlapNums(a.applicable_paper_size_ids, b.applicable_paper_size_ids)) return false;
  return true;
}
type ConflictPair = { a: ImpositionTypeRow; b: ImpositionTypeRow; samePriority: boolean };
function computeConflicts(rows: ImpositionTypeRow[]): {
  pairs: ConflictPair[];
  ids: Set<number>;
} {
  const pairs: ConflictPair[] = [];
  const ids = new Set<number>();
  for (let i = 0; i < rows.length; i++) {
    for (let j = i + 1; j < rows.length; j++) {
      if (rulesConflict(rows[i], rows[j])) {
        pairs.push({ a: rows[i], b: rows[j], samePriority: rows[i].priority === rows[j].priority });
        ids.add(rows[i].id);
        ids.add(rows[j].id);
      }
    }
  }
  return { pairs, ids };
}

// ---------------------------------------------------------------------------
// Trang danh sách
// ---------------------------------------------------------------------------
export function ImpositionTypesCatalogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<ImpositionTypeRow[]>([]);
  const [ptName, setPtName] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [q, setQ] = useState("");
  const [techFilter, setTechFilter] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [tab, setTab] = useState<ListTab>("all");

  const [drawer, setDrawer] = useState<DrawerMode | null>(null);
  const [usageFor, setUsageFor] = useState<ImpositionTypeRow | null>(null);
  const [historyFor, setHistoryFor] = useState<ImpositionTypeRow | null>(null);
  const [menuFor, setMenuFor] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.impositionTypes
      .list(token, { current_only: true, sort: "priority", size: 200 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục quy tắc bình bài.");
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!token) return;
    api.productTypesCatalog
      .list(token, { size: 200 })
      .then((r) => setPtName(Object.fromEntries(r.items.map((p) => [p.product_type, p.name]))))
      .catch(() => {});
  }, [token]);

  const { pairs: conflictPairs, ids: conflictIds } = useMemo(() => computeConflicts(rows), [rows]);

  const techOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.technology).filter(Boolean))).sort(),
    [rows],
  );

  const counts = useMemo(
    () => ({
      all: rows.length,
      preset: rows.filter(isPreset).length,
      custom: rows.filter((r) => !isPreset(r)).length,
      inactive: rows.filter((r) => !r.is_active).length,
      conflict: conflictIds.size,
    }),
    [rows, conflictIds],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (tab === "preset" && !isPreset(r)) return false;
      if (tab === "custom" && isPreset(r)) return false;
      if (tab === "inactive" && r.is_active) return false;
      if (tab === "conflict" && !conflictIds.has(r.id)) return false;
      if (techFilter && r.technology !== techFilter) return false;
      if (groupFilter && r.group_kind !== groupFilter) return false;
      if (needle && !(`${r.code} ${r.name}`.toLowerCase().includes(needle))) return false;
      return true;
    });
  }, [rows, tab, techFilter, groupFilter, q, conflictIds]);

  const toggleActive = useCallback(
    async (row: ImpositionTypeRow) => {
      if (!token) return;
      setMenuFor(null);
      try {
        await api.impositionTypes.update(token, row.id, { ...rowToInput(row), is_active: !row.is_active });
        load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không đổi được trạng thái.");
      }
    },
    [token, load],
  );

  const onDelete = useCallback(
    async (row: ImpositionTypeRow) => {
      if (!token) return;
      setMenuFor(null);
      if (!window.confirm(`Xóa quy tắc "${row.name}" (${row.code})? Chỉ nên xóa quy tắc chưa dùng ở đâu.`)) return;
      try {
        await api.impositionTypes.remove(token, row.id);
        load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không xóa được quy tắc.");
      }
    },
    [token, load],
  );

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Quy tắc bình bài (403).
        </div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Quy tắc bình bài</h1>
        <p className="md-page__sub">
          Mỗi quy tắc xác định cách tính <strong>số con thành phẩm</strong>, <strong>số tờ sản xuất</strong>,{" "}
          <strong>lượt qua máy</strong>, <strong>bộ kẽm</strong> và <strong>lượt in màu</strong> cho tính giá.
          Quy tắc đã chốt trong báo giá không sửa trực tiếp — hãy <em>Tạo phiên bản mới</em>.
        </p>
      </header>

      <div className="md-page__toolbar">
        <div className="md-page__search">
          <input
            className="input"
            placeholder="Tìm theo mã / tên quy tắc…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select className="input md-page__filter" value={techFilter} onChange={(e) => setTechFilter(e.target.value)}>
          <option value="">Mọi công nghệ</option>
          {techOptions.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select className="input md-page__filter" value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}>
          <option value="">Mọi nhóm kiểu</option>
          {GROUP_OPTIONS.map((g) => (
            <option key={g.value} value={g.value}>{g.label}</option>
          ))}
        </select>
        <div className="md-page__toolbar-spacer" />
        <Button variant="primary" onClick={() => setDrawer({ kind: "create" })}>
          + Tạo quy tắc
        </Button>
      </div>

      <div className="ir-tabs">
        {([
          ["all", "Tất cả", counts.all, false],
          ["preset", "Preset hệ thống", counts.preset, false],
          ["custom", "Tùy chỉnh", counts.custom, false],
          ["inactive", "Đang ngừng", counts.inactive, false],
          ["conflict", "⚠ Có cảnh báo", counts.conflict, true],
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

      {conflictPairs.length > 0 && (tab === "all" || tab === "conflict") && (
        <div className="ir-warn" role="status">
          {conflictPairs.slice(0, 4).map((p, i) => (
            <div key={i}>
              <strong>"{p.a.name}"</strong> và <strong>"{p.b.name}"</strong> cùng áp dụng (
              {p.a.technology} · {APPLIES_SIDES_LABEL[p.a.applies_to_sides] ?? p.a.applies_to_sides}){" "}
              và <strong>cùng ưu tiên {p.a.priority}</strong> — engine không có thứ tự rõ ràng, nên chỉnh ưu tiên để tránh nhập nhằng.
            </div>
          ))}
          {conflictPairs.length > 4 && <div>… và {conflictPairs.length - 4} cặp khác.</div>}
        </div>
      )}

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
              <th>Quy tắc</th>
              <th>Áp dụng cho</th>
              <th>Cách tính giá</th>
              <th>Ưu tiên</th>
              <th>Phiên bản</th>
              <th>Đang dùng</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="md-page__status" role="status">Đang tải dữ liệu…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={8} className="md-page__empty">Không có quy tắc nào khớp bộ lọc.</td></tr>
            ) : (
              filtered.map((row) => {
                const prio = prioBucket(row.priority);
                const used = row.used_count > 0;
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => openRow(row)}>
                    <td>
                      <div><strong>{row.name}</strong></div>
                      <div className="md-page__mono md-page__muted">{row.code}</div>
                    </td>
                    <td>
                      <div>{APPLIES_SIDES_LABEL[row.applies_to_sides] ?? row.applies_to_sides}</div>
                      <div className="md-page__muted" style={{ fontSize: 12 }}>
                        <span className="md-page__tag-tech">{row.technology}</span> · {appliesLabel(row, ptName)}
                      </div>
                    </td>
                    <td>
                      <div className="ir-chips">
                        {calcChips(row).map((c, i) => (
                          <span key={i} className={`ir-chip${c.muted ? " ir-chip--muted" : ""}`}>{c.label}</span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span className={`ir-prio ${prio.cls}`} title={`priority = ${row.priority} (nhỏ = ưu tiên cao)`}>
                        {prio.label}
                      </span>
                    </td>
                    <td className="md-page__mono">v{row.version}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {row.estimate_count > 0 ? (
                        <button type="button" className="ir-usage-link" onClick={() => setUsageFor(row)}>
                          {row.estimate_count} tính giá
                        </button>
                      ) : (
                        <span className="ir-usage-zero">0 tính giá</span>
                      )}
                      {conflictIds.has(row.id) && <span className="ir-conflict-flag" title="Có cảnh báo xung đột">⚠</span>}
                    </td>
                    <td>
                      <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                        {row.is_active ? "Active" : "Inactive"}
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
                            <div
                              style={{ position: "fixed", inset: 0, zIndex: 29 }}
                              onClick={() => setMenuFor(null)}
                            />
                            <div className="ir-menu" role="menu">
                              <button type="button" onClick={() => openRow(row)}>
                                {used ? "Xem chi tiết" : "Chỉnh sửa"}
                              </button>
                              {used && (
                                <button type="button" onClick={() => { setMenuFor(null); setDrawer({ kind: "version", row }); }}>
                                  Tạo phiên bản mới
                                </button>
                              )}
                              <button type="button" onClick={() => { setMenuFor(null); setDrawer({ kind: "create", from: row }); }}>
                                Nhân bản
                              </button>
                              <button type="button" onClick={() => toggleActive(row)}>
                                {row.is_active ? "Tạm ngừng áp dụng" : "Kích hoạt lại"}
                              </button>
                              {row.estimate_count > 0 && (
                                <button type="button" onClick={() => { setMenuFor(null); setUsageFor(row); }}>
                                  Xem tính giá đã dùng
                                </button>
                              )}
                              <button type="button" onClick={() => { setMenuFor(null); setHistoryFor(row); }}>
                                Lịch sử thay đổi
                              </button>
                              {!used && row.estimate_count === 0 && (
                                <>
                                  <div className="ir-menu__sep" />
                                  <button type="button" className="danger" onClick={() => onDelete(row)}>Xóa</button>
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
        <RuleDrawer
          mode={drawer}
          onClose={() => setDrawer(null)}
          onSaved={() => { setDrawer(null); load(); }}
          onRequestVersion={(row) => setDrawer({ kind: "version", row })}
          onOpenHistory={(row) => setHistoryFor(row)}
          onOpenUsage={(row) => setUsageFor(row)}
        />
      )}
      {usageFor && <UsageDialog row={usageFor} onClose={() => setUsageFor(null)} />}
      {historyFor && <VersionHistoryDialog row={historyFor} onClose={() => setHistoryFor(null)} />}
    </main>
  );

  function openRow(row: ImpositionTypeRow) {
    setMenuFor(null);
    setDrawer(row.used_count > 0 ? { kind: "view", row } : { kind: "edit", row });
  }
}

// ---------------------------------------------------------------------------
// Drawer + stepper
// ---------------------------------------------------------------------------
type DrawerMode =
  | { kind: "create"; from?: ImpositionTypeRow }
  | { kind: "edit"; row: ImpositionTypeRow }
  | { kind: "version"; row: ImpositionTypeRow }
  | { kind: "view"; row: ImpositionTypeRow };

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

function RuleDrawer({
  mode,
  onClose,
  onSaved,
  onRequestVersion,
  onOpenHistory,
  onOpenUsage,
}: {
  mode: DrawerMode;
  onClose: () => void;
  onSaved: () => void;
  onRequestVersion: (row: ImpositionTypeRow) => void;
  onOpenHistory: (row: ImpositionTypeRow) => void;
  onOpenUsage: (row: ImpositionTypeRow) => void;
}) {
  const { token } = useAuth();
  const source = mode.kind === "create" ? mode.from ?? null : mode.row;
  const isCreate = mode.kind === "create";
  const isClone = isCreate && !!mode.from;
  const isVersion = mode.kind === "version";
  const readOnly = mode.kind === "view";

  const [step, setStep] = useState(0);

  const [code, setCode] = useState(isCreate ? "" : source?.code ?? "");
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
  const [testedOk, setTestedOk] = useState(false);

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

  const softWarnings: string[] = [];
  const softInfos: string[] = [];
  if (sides === 1 && Number.isFinite(ipf) && ipf > 1) softWarnings.push("Số mặt = 1 nhưng số lần lăn mực > 1 — thường không hợp lý.");
  if (sides === 2 && Number.isFinite(pc) && pc === 1) softWarnings.push("Số mặt = 2 mà số lần chạy máy = 1 — có phải máy perfecting (in trở tự động)?");
  if (Number.isFinite(ff) && ff === 0.5) softInfos.push("Tỉ lệ con lấy được/tờ 0.5 sẽ giảm một nửa số con mỗi tờ (cần gấp đôi số tờ in).");
  if (source && source.estimate_count > 0 && (mode.kind === "edit")) {
    softInfos.push(`Quy tắc đang dùng trong ${source.estimate_count} tính giá — sửa tại chỗ sẽ ảnh hưởng lần tính lại sau.`);
  }

  // Đổi hệ số ⇒ phải chạy lại kiểm thử trước khi lưu Active.
  const factorKey = `${finishedFactor}|${passCount}|${plateSetFactor}|${inkPassFactor}`;
  useEffect(() => { setTestedOk(false); }, [factorKey]);

  function fail(msg: string, gotoStep?: number) {
    setValidationError(msg);
    if (gotoStep !== undefined) setStep(gotoStep);
  }

  async function onSubmit(e?: FormEvent) {
    e?.preventDefault();
    if (!token || saving || readOnly) return;
    setValidationError(null);

    if (isCreate && !code.trim()) return fail("Mã quy tắc không được trống.", 0);
    if (!name.trim()) return fail("Tên quy tắc không được trống.", 0);
    if (sides !== 1 && sides !== 2) return fail("Số mặt in phải là 1 hoặc 2.", 1);
    if (!Number.isFinite(ff) || ff <= 0) return fail("Tỉ lệ con lấy được/tờ phải lớn hơn 0.", 1);
    if (!Number.isFinite(pc) || pc <= 0) return fail("Số lần chạy máy phải lớn hơn 0.", 1);
    if (!Number.isFinite(psf) || psf < 0) return fail("Số bộ kẽm không được âm.", 1);
    if (!Number.isFinite(ipf) || ipf < 0) return fail("Số lần lăn mực không được âm.", 1);
    const prio = Number(priority);
    if (!Number.isFinite(prio) || prio < 0) return fail("Thứ tự ưu tiên không được âm.", 2);
    if (effectiveFrom && effectiveTo && effectiveTo <= effectiveFrom) return fail("Ngày hết hiệu lực phải sau ngày bắt đầu.", 0);
    // Gate kiểm thử: lưu Active phải chạy thử ít nhất 1 lần với bộ hệ số hiện tại.
    if (isActive && !testedOk) return fail("Hãy chạy Kiểm thử ít nhất 1 lần trước khi lưu quy tắc ở trạng thái Active.", 3);

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
    if (isCreate) payload.code = code.trim().toUpperCase();
    if (isVersion) payload.force_version = true;

    setSaving(true);
    try {
      if (isCreate) await api.impositionTypes.create(token, payload);
      else await api.impositionTypes.update(token, source!.id, payload);
      onSaved();
    } catch (err) {
      setValidationError(err instanceof ApiError ? err.message : "Lưu thất bại. Vui lòng kiểm tra lại.");
      setSaving(false);
    }
  }

  const title = isCreate
    ? (isClone ? `Nhân bản từ: ${source?.name}` : "Tạo quy tắc bình bài mới")
    : isVersion
      ? `Tạo phiên bản mới: ${source?.name} (v${(source?.version ?? 1) + 1})`
      : readOnly
        ? `Chi tiết: ${source?.name}`
        : `Chỉnh sửa: ${source?.name}`;

  const disabled = readOnly;
  const isLast = step === STEPS.length - 1;

  return (
    <div className="ir-drawer-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="ir-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="ir-drawer__head">
          <div>
            <h2>{title}</h2>
            <div className="ir-drawer__head-sub">
              {source ? <span className="md-page__mono">{source.code} · v{source.version}</span> : "Quy tắc dùng cho engine tính giá"}
            </div>
          </div>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>

        {readOnly && (
          <div className="banner banner--info" role="status" style={{ margin: "12px 24px 0" }}>
            Quy tắc này đã dùng trong <strong>{source?.used_count}</strong> báo giá nên khóa sửa trực tiếp.
            Hãy <strong>Tạo phiên bản mới</strong> để chỉnh sửa — báo giá cũ giữ số đã chốt.
          </div>
        )}
        {isVersion && (
          <div className="banner banner--info" role="status" style={{ margin: "12px 24px 0" }}>
            Sẽ tạo <strong>phiên bản mới</strong> của mã {source?.code}; bản cũ đóng hiệu lực hôm nay, báo giá cũ giữ nguyên.
          </div>
        )}

        <div className="ir-stepper">
          {STEPS.map((s, i) => (
            <button
              key={s}
              type="button"
              className={`ir-step${step === i ? " ir-step--active" : ""}${step > i ? " ir-step--done" : ""}`}
              onClick={() => setStep(i)}
            >
              <span className="ir-step__num">{step > i ? "✓" : i + 1}</span>
              {s}
            </button>
          ))}
        </div>

        <div className="ir-drawer__body">
          {/* BƯỚC 1 — Thông tin */}
          {step === 0 && (
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Mã quy tắc *</span>
                <input className="input md-page__mono" placeholder="VD: TU_TRO" value={code} disabled={!isCreate}
                  onChange={(e) => setCode(e.target.value.toUpperCase())} />
                {!isCreate && <span className="field__hint">Mã không đổi sau khi tạo.</span>}
              </label>
              <label className="field">
                <span className="field__label">Tên quy tắc *</span>
                <input className="input" placeholder="VD: Tự trở" value={name} disabled={disabled}
                  onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Nhóm kiểu *</span>
                <select className="input" value={groupKind} disabled={disabled}
                  onChange={(e) => setGroupKind(e.target.value as ImpositionGroupKind)}>
                  {GROUP_OPTIONS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Trạng thái</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="ir-active" checked={isActive} disabled={disabled}
                    onChange={(e) => setIsActive(e.target.checked)} />
                  <label htmlFor="ir-active">Active</label>
                </div>
              </label>
              <label className="field md-page__form-wide">
                <span className="field__label">Mô tả nghiệp vụ</span>
                <textarea className="input" rows={2} placeholder="Diễn giải khi nào dùng quy tắc này (tùy chọn)"
                  value={note} disabled={disabled} onChange={(e) => setNote(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Hiệu lực từ</span>
                <input className="input" type="date" value={effectiveFrom ?? ""} disabled={disabled}
                  onChange={(e) => setEffectiveFrom(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Hiệu lực đến</span>
                <input className="input" type="date" value={effectiveTo ?? ""} disabled={disabled}
                  onChange={(e) => setEffectiveTo(e.target.value)} />
              </label>
            </div>
          )}

          {/* BƯỚC 2 — Công thức + panel Ảnh hưởng đến giá */}
          {step === 1 && (
            <div className="ir-split">
              <div className="ir-split__form md-page__form-grid">
                <label className="field">
                  <span className="field__label">Số mặt in</span>
                  <select className="input" value={sides} disabled={disabled}
                    onChange={(e) => setSides(Number(e.target.value))}>
                    {SIDES_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </label>
                <NumField label="Tỉ lệ con lấy được/tờ *" value={finishedFactor} set={setFinishedFactor} disabled={disabled}
                  hint="1 = đủ số con như in 1 mặt · 0.5 = còn một nửa (tự trở)" />
                <NumField label="Số lần chạy máy (mỗi tờ) *" value={passCount} set={setPassCount} disabled={disabled} integer
                  hint="Mỗi tờ qua máy mấy lần — in 2 mặt thường 2" />
                <NumField label="Số bộ kẽm *" value={plateSetFactor} set={setPlateSetFactor} disabled={disabled} integer
                  hint="1 = chung 1 bộ · 2 = mặt trước/sau làm kẽm riêng" />
                <NumField label="Số lần lăn mực (mỗi tờ) *" value={inkPassFactor} set={setInkPassFactor} disabled={disabled} integer
                  hint="Mỗi tờ lăn mực mấy lần — in 2 mặt thường 2" />
                <label className="field">
                  <span className="field__label">Cho xoay bài khi bình</span>
                  <div className="md-page__toggle-wrap">
                    <input type="checkbox" id="ir-rotate" checked={allowRotate} disabled={disabled}
                      onChange={(e) => setAllowRotate(e.target.checked)} />
                    <label htmlFor="ir-rotate">Cho phép xoay</label>
                  </div>
                  <span className="field__hint">Xoay bài 90° để kê được nhiều con hơn</span>
                </label>
                <label className="field">
                  <span className="field__label">Dùng chung bộ kẽm</span>
                  <div className="md-page__toggle-wrap">
                    <input type="checkbox" id="ir-shared" checked={sharedPlateSet} disabled={disabled}
                      onChange={(e) => setSharedPlateSet(e.target.checked)} />
                    <label htmlFor="ir-shared">2 mặt xài chung 1 bộ kẽm</label>
                  </div>
                  <span className="field__hint">Cả 2 mặt in bằng 1 bộ kẽm (kiểu tự trở)</span>
                </label>
              </div>
              <div className="ir-split__aside">
                <div className="ir-panel">
                  <span className="ir-panel__title">Xem trực quan kiểu bình</span>
                  <ImpositionSchematic
                    sides={sides}
                    finishedFactor={ff}
                    plateSetFactor={psf}
                    passCount={pc}
                    sharedPlateSet={sharedPlateSet}
                    allowRotate={allowRotate}
                  />
                </div>
                <div className="ir-panel" style={{ marginTop: 8 }}>
                  <span className="ir-panel__title">Ảnh hưởng đến giá</span>
                  <div className="ir-panel__row">Số con thành phẩm mỗi tờ = số con xếp được trên tờ × <strong>{fmt(ff)}</strong></div>
                  <div className="ir-panel__row">Số tờ sản xuất = số lượng thành phẩm ÷ số con thành phẩm/tờ</div>
                  <div className="ir-panel__row">Số lần in = số tờ in thực tế × <strong>{fmt(pc)}</strong></div>
                  <div className="ir-panel__row">Số bản kẽm = số màu × <strong>{fmt(psf)}</strong> × số tay sách</div>
                  <div className="ir-panel__row">Số lần lăn mực = số tờ in thực tế × số màu × <strong>{fmt(ipf)}</strong></div>
                </div>
                {softWarnings.map((w, i) => (
                  <div key={`w${i}`} className="banner banner--error" role="alert" style={{ marginTop: 8 }}>⚠️ {w}</div>
                ))}
                {softInfos.map((w, i) => (
                  <div key={`i${i}`} className="banner banner--info" role="status" style={{ marginTop: 8 }}>ℹ️ {w}</div>
                ))}
              </div>
            </div>
          )}

          {/* BƯỚC 3 — Điều kiện áp dụng (rule builder) */}
          {step === 2 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
              <div className="md-page__form-grid">
                <label className="field">
                  <span className="field__label">Công nghệ</span>
                  <input className="input" value={technology} disabled={disabled}
                    onChange={(e) => setTechnology(e.target.value)} placeholder="offset" />
                </label>
                <label className="field">
                  <span className="field__label">Áp dụng cho số mặt</span>
                  <select className="input" value={appliesToSides} disabled={disabled}
                    onChange={(e) => setAppliesToSides(e.target.value as ImpositionAppliesToSides)}>
                    {APPLIES_SIDES_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="field__label">Thứ tự ưu tiên</span>
                  <input className="input" type="number" min="0" step="1" value={priority} disabled={disabled}
                    onChange={(e) => setPriority(e.target.value)} />
                  <span className="field__hint">Nhỏ = ưu tiên cao. {(() => { const p = prioBucket(Number(priority) || 0); return p.label; })()}</span>
                </label>
                <label className="field">
                  <span className="field__label">Nhiều tay sách</span>
                  <div className="md-page__toggle-wrap">
                    <input type="checkbox" id="ir-multisig" checked={allowMultiSignature} disabled={disabled}
                      onChange={(e) => setAllowMultiSignature(e.target.checked)} />
                    <label htmlFor="ir-multisig">Cho phép khi nhiều tay sách</label>
                  </div>
                </label>
              </div>

              <div className="field">
                <span className="field__label">Áp dụng loại sản phẩm (trống = tất cả)</span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 4 }}>
                  {ptOptions.map((p) => (
                    <label key={p.product_type} className="md-page__checkbox-label">
                      <input type="checkbox" checked={productTypes.includes(p.product_type)} disabled={disabled}
                        onChange={(e) => setProductTypes((prev) => e.target.checked ? [...prev, p.product_type] : prev.filter((x) => x !== p.product_type))} />
                      {p.name}
                    </label>
                  ))}
                </div>
              </div>

              <div className="ir-split">
                <div className="ir-split__form">
                  <span className="field__label">Áp dụng cho máy (offset)</span>
                  <MultiSelectSearch
                    options={machineOptions.map((m) => ({ key: m.id, label: m.name }))}
                    selected={machineIds}
                    onChange={(keys) => setMachineIds(keys as number[])}
                    placeholder="Tìm máy…"
                    disabled={disabled}
                  />
                </div>
                <div className="ir-split__form">
                  <span className="field__label">Áp dụng cho khổ giấy</span>
                  <MultiSelectSearch
                    options={paperOptions.map((p) => ({ key: p.id, label: `${p.name} (${p.width_cm}×${p.height_cm})` }))}
                    selected={paperSizeIds}
                    onChange={(keys) => setPaperSizeIds(keys as number[])}
                    placeholder="Tìm khổ giấy…"
                    disabled={disabled}
                  />
                </div>
              </div>
            </div>
          )}

          {/* BƯỚC 4 — Kiểm thử (gọi engine thật) */}
          {step === 3 && (
            <QuickTest
              token={token}
              ff={ff} pc={pc} psf={psf} ipf={ipf}
              code={source?.code ?? code}
              onTested={() => setTestedOk(true)}
            />
          )}

          {validationError && <div className="banner banner--error" role="alert">{validationError}</div>}
        </div>

        <div className="ir-drawer__foot">
          <div>
            {step > 0 && (
              <Button type="button" variant="ghost" onClick={() => setStep(step - 1)}>← Quay lại</Button>
            )}
          </div>
          <div className="ir-drawer__foot-right">
            {readOnly ? (
              <>
                {source && source.used_count > 0 && (
                  <Button type="button" variant="ghost" onClick={() => onOpenHistory(source)}>Lịch sử</Button>
                )}
                {source && source.estimate_count > 0 && (
                  <Button type="button" variant="ghost" onClick={() => onOpenUsage(source)}>Xem tính giá</Button>
                )}
                {source && (
                  <Button type="button" variant="primary" onClick={() => onRequestVersion(source)}>Tạo phiên bản mới</Button>
                )}
              </>
            ) : (
              <>
                <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
                {isLast ? (
                  <Button type="button" variant="primary" loading={saving} onClick={() => onSubmit()}>
                    {isCreate ? "Tạo quy tắc" : isVersion ? "Tạo phiên bản mới" : "Lưu"}
                  </Button>
                ) : (
                  <Button type="button" variant="primary" onClick={() => setStep(step + 1)}>Tiếp →</Button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Ô đếm (số nguyên): cắt phần thập phân + đổi dấu phẩy → không còn nhập nhầm "1,001".
function sanitizeInt(raw: string): string {
  if (raw.trim() === "") return "";
  const n = Math.trunc(Number(raw.replace(",", ".")));
  return Number.isFinite(n) ? String(n) : "";
}
function NumField({ label, value, set, disabled, hint, integer }: { label: string; value: string; set: (s: string) => void; disabled?: boolean; hint?: string; integer?: boolean }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <input
        className="input"
        type="number"
        min="0"
        step={integer ? "1" : "0.5"}
        inputMode={integer ? "numeric" : "decimal"}
        value={value}
        disabled={disabled}
        onChange={(e) => set(e.target.value)}
        onBlur={integer ? () => set(sanitizeInt(value)) : undefined}
      />
      {hint ? <span className="field__hint">{hint}</span> : null}
    </label>
  );
}

// ---------------------------------------------------------------------------
// Multi-select có tìm kiếm + chọn tất cả + đếm
// ---------------------------------------------------------------------------
function MultiSelectSearch({
  options,
  selected,
  onChange,
  placeholder,
  disabled,
}: {
  options: { key: string | number; label: string }[];
  selected: (string | number)[];
  onChange: (keys: (string | number)[]) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [needle, setNeedle] = useState("");
  const selectedSet = new Set(selected);
  const shown = options.filter((o) => o.label.toLowerCase().includes(needle.trim().toLowerCase()));
  const allShownSelected = shown.length > 0 && shown.every((o) => selectedSet.has(o.key));

  function toggle(key: string | number) {
    if (disabled) return;
    onChange(selectedSet.has(key) ? selected.filter((k) => k !== key) : [...selected, key]);
  }
  function toggleAllShown() {
    if (disabled) return;
    if (allShownSelected) {
      const shownKeys = new Set(shown.map((o) => o.key));
      onChange(selected.filter((k) => !shownKeys.has(k)));
    } else {
      const merged = new Set(selected);
      shown.forEach((o) => merged.add(o.key));
      onChange(Array.from(merged));
    }
  }

  return (
    <>
      <div className="ir-ms">
        <div className="ir-ms__bar">
          <span aria-hidden>🔍</span>
          <input className="ir-ms__search" placeholder={placeholder ?? "Tìm…"} value={needle}
            disabled={disabled} onChange={(e) => setNeedle(e.target.value)} />
          {shown.length > 0 && !disabled && (
            <button type="button" className="ir-ms__act" onClick={toggleAllShown}>
              {allShownSelected ? "Bỏ chọn" : "Chọn tất cả"}
            </button>
          )}
        </div>
        <div className="ir-ms__list">
          {shown.length === 0 ? (
            <div className="ir-ms__empty">Không có mục nào.</div>
          ) : (
            shown.map((o) => (
              <label key={o.key} className="ir-ms__opt">
                <input type="checkbox" checked={selectedSet.has(o.key)} disabled={disabled} onChange={() => toggle(o.key)} />
                {o.label}
              </label>
            ))
          )}
        </div>
      </div>
      <div className="ir-ms__count">
        {selected.length > 0 ? `Đã chọn ${selected.length}/${options.length}` : `Trống = áp dụng tất cả (${options.length})`}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Bước 4 — Kiểm thử: gọi engine thật (POST /preview)
// ---------------------------------------------------------------------------
function QuickTest({
  token,
  ff, pc, psf, ipf,
  code,
  onTested,
}: {
  token: string | null;
  ff: number; pc: number; psf: number; ipf: number;
  code: string;
  onTested: () => void;
}) {
  const sampleKey = `impo-test:${code || "new"}`;
  const [geo, setGeo] = useState("8");
  const [qty, setQty] = useState("1000");
  const [prodSheets, setProdSheets] = useState("300");
  const [colors, setColors] = useState("4");
  const [forms, setForms] = useState("1");
  const [speed, setSpeed] = useState("6000");
  const [result, setResult] = useState<ImpositionPreviewOut | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const loadedSample = useRef(false);

  // Nạp test case mẫu đã lưu (localStorage) 1 lần.
  useEffect(() => {
    if (loadedSample.current) return;
    loadedSample.current = true;
    try {
      const raw = localStorage.getItem(sampleKey);
      if (raw) {
        const s = JSON.parse(raw);
        if (s.geo) setGeo(String(s.geo));
        if (s.qty) setQty(String(s.qty));
        if (s.prodSheets) setProdSheets(String(s.prodSheets));
        if (s.colors) setColors(String(s.colors));
        if (s.forms) setForms(String(s.forms));
        if (s.speed) setSpeed(String(s.speed));
      }
    } catch { /* ignore */ }
  }, [sampleKey]);

  async function run() {
    if (!token || running) return;
    setErr(null);
    setRunning(true);
    try {
      const out = await api.impositionTypes.preview(token, {
        finished_factor: ff,
        pass_count: pc,
        plate_set_factor: psf,
        ink_pass_factor: ipf,
        geometric_pieces: Number(geo) || 0,
        quantity: Number(qty) || 0,
        production_sheets: Number(prodSheets) || 0,
        colors: Number(colors) || 0,
        forms: Number(forms) || 1,
        machine_speed: Number(speed) || 0,
      });
      setResult(out);
      onTested();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không chạy được kiểm thử.");
    } finally {
      setRunning(false);
    }
  }

  function saveSample() {
    try {
      localStorage.setItem(sampleKey, JSON.stringify({ geo, qty, prodSheets, colors, forms, speed }));
    } catch { /* ignore */ }
  }

  const num = (v: string, set: (s: string) => void, label: string) => (
    <label className="field">
      <span className="field__label">{label}</span>
      <input className="input" type="number" value={v} onChange={(e) => set(e.target.value)} />
    </label>
  );

  return (
    <div className="ir-split">
      <div className="ir-split__form md-page__form-grid">
        {num(geo, setGeo, "Số con hình học")}
        {num(qty, setQty, "SL thành phẩm")}
        {num(prodSheets, setProdSheets, "Số tờ sản xuất")}
        {num(colors, setColors, "Số màu")}
        {num(forms, setForms, "Số form/tay")}
        {num(speed, setSpeed, "Tốc độ máy (tờ/giờ)")}
        <div className="md-page__form-wide" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Button type="button" variant="primary" loading={running} onClick={run}>Chạy thử (engine)</Button>
          <Button type="button" variant="ghost" onClick={saveSample}>Lưu làm test case mẫu</Button>
        </div>
      </div>
      <div className="ir-split__aside">
        <div className="ir-panel">
          <span className="ir-panel__title">Kết quả engine</span>
          {!result ? (
            <div className="md-page__muted" style={{ fontSize: 13 }}>
              <span className="ir-test-badge ir-test-badge--todo">Chưa chạy thử</span>
              <div style={{ marginTop: 8 }}>Bấm <strong>Chạy thử</strong> để engine tính đúng các biến dùng cho tính giá.</div>
            </div>
          ) : (
            <>
              <span className="ir-test-badge ir-test-badge--ok">✓ Đã kiểm thử — số từ engine</span>
              <div className="ir-test-grid">
                <TestCell label="Số con TP/tờ" value={result.finished_pieces_per_sheet} />
                <TestCell label="Số tờ lý thuyết" value={result.theoretical_sheets} />
                <TestCell label="Lượt qua máy" value={result.machine_sheets} />
                <TestCell label="Giờ chạy" value={result.run_hours} decimals={3} />
                <TestCell label="Số bộ kẽm" value={result.plates} />
                <TestCell label="Lượt in màu" value={result.ink_impressions} />
              </div>
            </>
          )}
          {err && <div className="banner banner--error" role="alert" style={{ marginTop: 8 }}>{err}</div>}
        </div>
      </div>
    </div>
  );
}

function TestCell({ label, value, decimals }: { label: string; value: number; decimals?: number }) {
  const shown = decimals != null ? value.toFixed(decimals) : value.toLocaleString("vi-VN");
  return (
    <div className="ir-test-cell">
      <span>{label}</span>
      <strong>{shown}</strong>
    </div>
  );
}

// ---------------------------------------------------------------------------
// "Xem tính giá đã dùng" — drill-down
// ---------------------------------------------------------------------------
const EST_STATUS_LABEL: Record<string, string> = {
  draft: "Nháp",
  calculated: "Đã tính",
  cancelled: "Đã hủy",
  converted_to_quote: "Đã lên báo giá",
};

function UsageDialog({ row, onClose }: { row: ImpositionTypeRow; onClose: () => void }) {
  const { token } = useAuth();
  const [items, setItems] = useState<ImpositionUsageEstimate[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.impositionTypes
      .usage(token, row.id)
      .then((r) => setItems(r.estimates))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được danh sách tính giá."))
      .finally(() => setLoading(false));
  }, [token, row.id]);

  return (
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head">
          <h2>Tính giá đang dùng: {row.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <p className="md-page__note">
            <span className="md-page__mono">{row.code}</span> — {row.estimate_count} phiếu tính giá đang tham chiếu quy tắc này.
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
                <tr><th>Số phiếu</th><th>Sản phẩm</th><th>Trạng thái</th><th>Ngày tạo</th></tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id}>
                    <td className="md-page__mono">{e.estimate_number}</td>
                    <td>{e.product_name}</td>
                    <td>{EST_STATUS_LABEL[e.status] ?? e.status}</td>
                    <td style={{ fontSize: 12 }}>{new Date(e.created_at).toLocaleDateString("vi-VN")}</td>
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
// Lịch sử phiên bản
// ---------------------------------------------------------------------------
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
    <div className="md-page__overlay" role="dialog" onClick={onClose}>
      <div className="md-page__dialog card" style={{ maxWidth: 720 }} onClick={(e) => e.stopPropagation()}>
        <div className="md-page__dialog-head">
          <h2>Lịch sử phiên bản: {row.code}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          {loading ? (
            <p className="md-page__status">Đang tải…</p>
          ) : (
            <table className="md-page__table">
              <thead>
                <tr>
                  <th>Ver</th><th>Tên</th><th>TP/tờ</th><th>Máy</th><th>Kẽm</th><th>Mực</th>
                  <th>Hiệu lực</th><th>Dùng (BG)</th><th>Trạng thái</th>
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
