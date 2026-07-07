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
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ImpositionSchematic } from "../components/ImpositionSchematic";
import { InfoHint } from "../components/InfoHint";
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

// Bước "Điều kiện" đã bỏ: phạm vi áp dụng theo loại SP quản lý MỘT NƠI ở danh mục
// Loại sản phẩm (tab Bình bài & quy tắc); "áp dụng cho số mặt" tự suy từ Nhóm kiểu.
const STEPS = ["Thông tin", "Công thức", "Kiểm thử"];
type ListTab = "all" | "preset" | "custom" | "inactive";

// ---------------------------------------------------------------------------
// Tiện ích thuần
// ---------------------------------------------------------------------------
function fmt(n: number): string {
  return Number.isFinite(n) ? String(n) : "?";
}
function isPreset(row: ImpositionTypeRow): boolean {
  return row.group_kind !== "custom";
}

// --- Bộ chọn "cách in" → suy 4 hệ số (form Công thức hướng dẫn) -----------------
// Người dùng khai CÁCH IN THẬT (mấy mặt · chung/riêng kẽm · perfecting · bồi 2 mảnh),
// hệ thống tự suy 4 hệ số — luôn nhất quán, không tạo được tổ hợp mâu thuẫn.
type PlateMode = "shared" | "separate";
interface ImpoChoice {
  printSides: number;   // 1 | 2
  plateMode: PlateMode; // chung 1 bộ / riêng 2 bộ (chỉ khi 2 mặt)
  perfecting: boolean;  // máy in trở tự động (chỉ khi 2 mặt)
  twoPiece: boolean;    // sản phẩm bồi/dán 2 mảnh → con ÷2
}
interface ImpoCoef { sides: number; finished: number; pass: number; plate: number; ink: number }

function deriveCoef(c: ImpoChoice): ImpoCoef {
  const twoSide = c.printSides === 2;
  return {
    sides: c.printSides,
    ink: c.printSides,                                    // in mấy mặt = lăn mực mấy lần
    pass: !twoSide ? 1 : c.perfecting ? 1 : 2,            // perfecting: 2 mặt 1 lượt máy
    plate: !twoSide ? 1 : c.plateMode === "shared" ? 1 : 2,
    finished: c.twoPiece ? 0.5 : 1.0,                    // bồi 2 mảnh mới chia đôi con
  };
}

/** Suy ngược lựa chọn từ 4 hệ số đã lưu (mở kiểu cũ). */
function choiceFromCoef(sides: number, finished: number, pass: number, plate: number): ImpoChoice {
  return {
    printSides: sides === 2 ? 2 : 1,
    plateMode: plate >= 2 ? "separate" : "shared",
    perfecting: sides === 2 && pass === 1,
    twoPiece: finished < 1,
  };
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
    }),
    [rows],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (tab === "preset" && !isPreset(r)) return false;
      if (tab === "custom" && isPreset(r)) return false;
      if (tab === "inactive" && r.is_active) return false;
      if (techFilter && r.technology !== techFilter) return false;
      if (groupFilter && r.group_kind !== groupFilter) return false;
      if (needle && !(`${r.code} ${r.name}`.toLowerCase().includes(needle))) return false;
      return true;
    });
  }, [rows, tab, techFilter, groupFilter, q]);

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
          ["all", "Tất cả", counts.all],
          ["preset", "Preset hệ thống", counts.preset],
          ["custom", "Tùy chỉnh", counts.custom],
          ["inactive", "Đang ngừng", counts.inactive],
        ] as [ListTab, string, number][]).map(([key, label, n]) => (
          <button
            key={key}
            type="button"
            className={`ir-tab${tab === key ? " ir-tab--active" : ""}`}
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
              <th>Phiên bản</th>
              <th>Đang dùng</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="md-page__status" role="status">Đang tải dữ liệu…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={7} className="md-page__empty">Không có quy tắc nào khớp bộ lọc.</td></tr>
            ) : (
              filtered.map((row) => {
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
                    <td className="md-page__mono">v{row.version}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {row.estimate_count > 0 ? (
                        <button type="button" className="ir-usage-link" onClick={() => setUsageFor(row)}>
                          {row.estimate_count} tính giá
                        </button>
                      ) : (
                        <span className="ir-usage-zero">0 tính giá</span>
                      )}
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
  // 2 cờ này đã bỏ khỏi UI (không tác động giá — engine chỉ đọc 4 hệ số số). Giữ giá trị
  // cũ từ bản ghi để không mất dữ liệu; sơ đồ minh họa suy "dùng chung kẽm" từ số bộ kẽm.
  const [allowRotate] = useState(source?.allow_rotate ?? true);
  const sharedPlateSet = Number(plateSetFactor) <= 1;

  // --- Form Công thức hướng dẫn: chọn cách in → tự suy 4 hệ số ---------------
  // Suy ngược lựa chọn từ bản ghi (kiểu mới mặc định 1 mặt).
  const initChoice = choiceFromCoef(
    source ? source.sides : 1,
    source ? Number(source.finished_factor) : 1,
    source ? Number(source.pass_count) : 1,
    source ? Number(source.plate_set_factor) : 1,
  );
  const [printSides, setPrintSides] = useState(initChoice.printSides);
  const [plateMode, setPlateMode] = useState<PlateMode>(initChoice.plateMode);
  const [perfecting, setPerfecting] = useState(initChoice.perfecting);
  const [twoPiece, setTwoPiece] = useState(initChoice.twoPiece);
  // Chế độ nhập tay 4 hệ số (nâng cao). Bật sẵn nếu hệ số cũ KHÔNG khớp bộ suy —
  // để không âm thầm đổi số của kiểu lạ (VD CUSTOM ink=1).
  const [advancedCoef, setAdvancedCoef] = useState(() => {
    if (!source) return false;
    const d = deriveCoef(initChoice);
    return !(
      d.sides === source.sides &&
      d.finished === Number(source.finished_factor) &&
      d.pass === Number(source.pass_count) &&
      d.plate === Number(source.plate_set_factor) &&
      d.ink === Number(source.ink_pass_factor)
    );
  });

  // Ở chế độ hướng dẫn: đổi lựa chọn → ghi 4 hệ số + số mặt.
  useEffect(() => {
    if (advancedCoef) return;
    const d = deriveCoef({ printSides, plateMode, perfecting, twoPiece });
    setSides(d.sides);
    setFinishedFactor(String(d.finished));
    setPassCount(String(d.pass));
    setPlateSetFactor(String(d.plate));
    setInkPassFactor(String(d.ink));
  }, [advancedCoef, printSides, plateMode, perfecting, twoPiece]);

  // Bước "Điều kiện" đã bỏ — technology/allow_multi_signature/applicable_* gửi lại như cũ.
  const [technology] = useState(source?.technology ?? "offset");
  const [allowMultiSignature] = useState(source?.allow_multi_signature ?? true);
  // Priority đã bỏ khỏi UI (không cần — chọn kiểu ở Loại SP). Giữ giá trị cũ để sắp dropdown.
  const [priority] = useState(source ? String(source.priority) : "100");

  const [effectiveFrom, setEffectiveFrom] = useState(isVersion ? "" : source?.effective_from ?? "");
  const [effectiveTo, setEffectiveTo] = useState(isVersion ? "" : source?.effective_to ?? "");

  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [testedOk, setTestedOk] = useState(false);

  const ff = Number(finishedFactor);
  const pc = Number(passCount);
  const psf = Number(plateSetFactor);
  const ipf = Number(inkPassFactor);

  const softWarnings: string[] = [];
  const softInfos: string[] = [];
  if (sides === 1 && Number.isFinite(ipf) && ipf > 1) softWarnings.push("Số mặt = 1 nhưng số lần lăn mực > 1 — thường không hợp lý.");
  if (sides === 2 && Number.isFinite(pc) && pc === 1) softWarnings.push("Số mặt = 2 mà số lần chạy máy = 1 — có phải máy perfecting (in trở tự động)?");
  // Tổ hợp mâu thuẫn vật lý: kẽm RIÊNG (≥2) thì mỗi ô tự đủ 2 mặt → con phải NGUYÊN (1.0);
  // kẽm CHUNG (1) cho 2 mặt thì con phải ÷2. Trộn ngược = vừa tốn kẽm vừa tốn giấy.
  if (Number.isFinite(psf) && psf >= 2 && Number.isFinite(ff) && ff < 1) {
    softWarnings.push("Kẽm riêng (≥2 bộ) thì mỗi ô tự đủ 2 mặt — tỉ lệ con thường = 1. Tổ hợp '2 kẽm + tỉ lệ < 1' vừa tốn kẽm vừa tốn giấy, gần như chắc chắn nhập nhầm.");
  }
  if (sides === 2 && Number.isFinite(psf) && psf <= 1 && Number.isFinite(ff) && ff >= 1) {
    softWarnings.push("2 mặt dùng CHUNG 1 bộ kẽm thì thường phải chia đôi số con (tỉ lệ 0.5) — kiểm tra lại tỉ lệ con nếu đây là kiểu tự trở/trở nhíp 1 kẽm.");
  }
  if (Number.isFinite(ff) && ff === 0.5) softInfos.push("Tỉ lệ con 0.5 = 2 ô ghép 1 sản phẩm → cần gấp đôi số tờ in (giấy vẫn in kín, không bỏ trắng nửa nào).");
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
    if (!Number.isFinite(prio) || prio < 0) return fail("Thứ tự ưu tiên không được âm.", 0);
    if (effectiveFrom && effectiveTo && effectiveTo <= effectiveFrom) return fail("Ngày hết hiệu lực phải sau ngày bắt đầu.", 0);
    // Gate kiểm thử: lưu Active phải chạy thử ít nhất 1 lần với bộ hệ số hiện tại.
    if (isActive && !testedOk) return fail("Hãy chạy Kiểm thử ít nhất 1 lần trước khi lưu quy tắc ở trạng thái Active.", 2);

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
      // "Áp dụng cho số mặt" suy thẳng từ Nhóm kiểu — hết cảnh 2 field lệch nhau
      // (VD kiểu "1 mặt" mà điều kiện lại ghi "chỉ 2 mặt").
      applies_to_sides:
        groupKind === "one_side" ? "1"
        : groupKind === "two_side" ? "2"
        : groupKind === "multi_page" ? "multi"
        : "any",
      // Phạm vi loại SP / máy / khổ giấy quản lý MỘT NƠI ở danh mục Loại sản phẩm
      // (tab Bình bài & quy tắc) — lưu từ form này luôn về "áp dụng tất cả".
      applicable_product_types: null,
      applicable_machine_ids: null,
      applicable_paper_size_ids: null,
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

          {/* BƯỚC 2 — Công thức: chọn CÁCH IN → tự suy 4 hệ số */}
          {step === 1 && (
            <div className="ir-split">
              <div className="ir-split__form">
                {!advancedCoef ? (
                  <div className="ir-choice">
                    {/* 1 — số mặt */}
                    <div className="ir-choice__q">
                      <span className="ir-choice__label">Sản phẩm in mấy mặt?</span>
                      <div className="ir-choice__opts">
                        <button type="button" disabled={disabled}
                          className={`ir-opt${printSides === 1 ? " is-on" : ""}`}
                          onClick={() => { setPrintSides(1); setTwoPiece(false); }}>1 mặt</button>
                        <button type="button" disabled={disabled}
                          className={`ir-opt${printSides === 2 ? " is-on" : ""}`}
                          onClick={() => setPrintSides(2)}>2 mặt</button>
                      </div>
                    </div>

                    {/* 2 — chung/riêng kẽm (chỉ khi 2 mặt) */}
                    {printSides === 2 && (
                      <div className="ir-choice__q">
                        <span className="ir-choice__label">
                          Làm khuôn kẽm kiểu nào?
                          <InfoHint label="Chung 1 bộ (tự trở): rẻ kẽm, lật giấy in mặt kia — con vẫn nguyên. Riêng 2 bộ (trở nhíp/A-B): tốn gấp đôi kẽm, hợp sản phẩm lớn/đơn to." />
                        </span>
                        <div className="ir-choice__opts ir-choice__opts--col">
                          <button type="button" disabled={disabled}
                            className={`ir-opt${plateMode === "shared" ? " is-on" : ""}`}
                            onClick={() => setPlateMode("shared")}>Chung 1 bộ kẽm (tự trở) — rẻ kẽm</button>
                          <button type="button" disabled={disabled}
                            className={`ir-opt${plateMode === "separate" ? " is-on" : ""}`}
                            onClick={() => setPlateMode("separate")}>Riêng 2 bộ kẽm (trở nhíp / A-B)</button>
                        </div>
                      </div>
                    )}

                    {/* 3 — perfecting (chỉ khi 2 mặt) */}
                    {printSides === 2 && (
                      <label className="ir-choice__toggle">
                        <input type="checkbox" checked={perfecting} disabled={disabled}
                          onChange={(e) => setPerfecting(e.target.checked)} />
                        <span>Máy in trở tự động (perfecting) — in 2 mặt trong 1 lượt qua máy
                          <InfoHint label="Máy có bộ lật tự động: in cả 2 mặt trong 1 lần tờ chạy qua → giờ máy KHÔNG nhân 2. Máy thường thì bỏ trống." />
                        </span>
                      </label>
                    )}

                    {/* 4 — bồi 2 mảnh (chỉ có nghĩa khi 2 mặt: 1 mảnh trước + 1 mảnh sau) */}
                    {printSides === 2 && (
                      <label className="ir-choice__toggle">
                        <input type="checkbox" checked={twoPiece} disabled={disabled}
                          onChange={(e) => setTwoPiece(e.target.checked)} />
                        <span>Sản phẩm ghép từ 2 mảnh giấy in riêng (thẻ bồi / bìa cứng)
                          <InfoHint label="Loại có lõi cứng ở giữa, không lật in được: 1 mảnh in mặt trước, 1 mảnh in mặt sau, dán lại → 2 ô = 1 SP → con ÷2. Card/tờ rơi thường (in 2 mặt lật giấy) thì BỎ TRỐNG." />
                        </span>
                      </label>
                    )}

                    {/* Hệ số suy ra (chỉ đọc, minh bạch) */}
                    <div className="ir-derived">
                      <span className="ir-derived__title">Hệ số suy ra (tự động)</span>
                      <div className="ir-derived__grid">
                        <span>Tỉ lệ con: <strong>{fmt(ff)}</strong></span>
                        <span>Số bộ kẽm: <strong>{fmt(psf)}</strong></span>
                        <span>Lượt máy: <strong>{fmt(pc)}</strong></span>
                        <span>Lượt mực: <strong>{fmt(ipf)}</strong></span>
                      </div>
                    </div>

                    <button type="button" className="ir-adv-toggle" disabled={disabled}
                      onClick={() => setAdvancedCoef(true)}>
                      Nhập tay hệ số (nâng cao) →
                    </button>
                  </div>
                ) : (
                  <div className="ir-adv">
                    <div className="ir-adv__head">
                      <span className="ir-test-badge ir-test-badge--todo">✎ Nhập tay hệ số</span>
                      <button type="button" className="ir-adv-toggle" disabled={disabled}
                        onClick={() => setAdvancedCoef(false)}>← Quay lại chọn cách in</button>
                    </div>
                    <p className="ir-adv__note">
                      Chế độ nâng cao — bạn tự điền 4 hệ số và tự chịu trách nhiệm tính nhất quán
                      (engine không kiểm tra chéo). Dùng khi cách in không khớp các lựa chọn sẵn.
                    </p>
                    <div className="ir-adv__grid">
                      <label className="field">
                        <span className="field__label">Số mặt in</span>
                        <select className="input" value={sides} disabled={disabled}
                          onChange={(e) => setSides(Number(e.target.value))}>
                          {SIDES_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                        </select>
                        <span className="ir-adv__feeds">dữ liệu gốc</span>
                      </label>
                      <NumField label="Tỉ lệ con lấy được/tờ *" value={finishedFactor} set={setFinishedFactor} disabled={disabled}
                        hint="1 = mỗi ô 1 SP · 0.5 = 2 ô ghép 1 SP (bồi 2 mảnh)." feeds="TIỀN GIẤY" />
                      <NumField label="Số lần chạy máy (mỗi tờ) *" value={passCount} set={setPassCount} disabled={disabled} integer
                        hint="Tờ qua máy mấy lượt → GIỜ MÁY. 2 mặt = 2 · perfecting = 1." feeds="GIỜ MÁY" />
                      <NumField label="Số bộ kẽm *" value={plateSetFactor} set={setPlateSetFactor} disabled={disabled} integer
                        hint="Chung kẽm = 1 · kẽm riêng = 2 · 1 mặt = 1." feeds="TIỀN KẼM" />
                      <NumField label="Số lần lăn mực (mỗi tờ) *" value={inkPassFactor} set={setInkPassFactor} disabled={disabled} integer
                        hint="= số mặt (1 hoặc 2)." feeds="TIỀN MỰC" />
                    </div>
                  </div>
                )}
              </div>
              <div className="ir-split__aside">
                <div className="ir-panel">
                  <span className="ir-panel__title">Xem trực quan kiểu bình</span>
                  <ImpositionSchematic
                    sides={sides}
                    finishedFactor={ff}
                    plateSetFactor={psf}
                    passCount={pc}
                    inkPassFactor={ipf}
                    sharedPlateSet={sharedPlateSet}
                    allowRotate={allowRotate}
                  />
                </div>
                <div className="ir-panel" style={{ marginTop: 8 }}>
                  <span className="ir-panel__title">Ảnh hưởng đến giá</span>
                  <div className="ir-panel__row" style={{ fontWeight: 600 }}>
                    Đọc nhanh: {ff === 0.5 ? "2 ô ghép 1 sản phẩm (con ÷2)" : ff === 1 ? "mỗi ô ra 1 sản phẩm" : `mỗi ô ra ${fmt(ff)} sản phẩm`}
                    {" · "}{psf <= 1 ? "chung 1 bộ kẽm" : `${fmt(psf)} bộ kẽm riêng`}
                    {" · "}tờ qua máy {fmt(pc)} lượt · mực {fmt(ipf)} lần/tờ
                  </div>
                  <div className="ir-panel__row">Số con thành phẩm mỗi tờ = số con xếp được trên tờ × <strong>{fmt(ff)}</strong> → quyết định TIỀN GIẤY</div>
                  <div className="ir-panel__row">Số tờ sản xuất = số lượng thành phẩm ÷ số con thành phẩm/tờ</div>
                  <div className="ir-panel__row">Số lần in = số tờ in thực tế × <strong>{fmt(pc)}</strong> → TIỀN GIỜ MÁY</div>
                  <div className="ir-panel__row">Số bản kẽm = số màu × <strong>{fmt(psf)}</strong> × số tay sách → TIỀN KẼM (làm 1 lần cho cả đơn)</div>
                  <div className="ir-panel__row">Số lần lăn mực = số tờ in thực tế × số màu × <strong>{fmt(ipf)}</strong> → TIỀN MỰC</div>
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
          {/* BƯỚC 3 — Kiểm thử (gọi engine thật) */}
          {step === 2 && (
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
function NumField({ label, value, set, disabled, hint, integer, feeds }: { label: string; value: string; set: (s: string) => void; disabled?: boolean; hint?: string; integer?: boolean; feeds?: string }) {
  // Chú thích dài để trong tooltip hover (ⓘ) — form gọn, cần mới đọc.
  // `feeds` = khoản tiền hệ số này nuôi (hiện dạng tag nhỏ dưới ô).
  return (
    <label className="field">
      <span className="field__label">
        {label}
        {hint ? <InfoHint label={hint} /> : null}
      </span>
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
      {feeds ? <span className="ir-adv__feeds">→ nuôi {feeds}</span> : null}
    </label>
  );
}

// ---------------------------------------------------------------------------
// Bước 3 — Kiểm thử: gọi engine thật (POST /preview)
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
