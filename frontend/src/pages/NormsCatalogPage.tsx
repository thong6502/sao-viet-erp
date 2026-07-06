import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type NormRow,
  type NormInput,
  type NormTestOutput,
  type NormUsageOut,
  type NormConflictsOut,
  type WasteGroup,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 15;

// --- Nhóm định mức + cách tính (§C docs/DINH_MUC_BU_HAO.md) ------------------
type MethodOpt = { value: string; label: string };
const GROUPS: {
  value: WasteGroup;
  label: string;
  badge: string;
  methods: MethodOpt[];
  hint: string;
}[] = [
  {
    value: "YIELD_RATE",
    label: "Tỷ lệ đạt",
    badge: "Tỷ lệ đạt",
    hint: "Cần trước công đoạn = ceil(cần sau / tỷ lệ đạt).",
    methods: [{ value: "PERCENT", label: "Theo % (0–1)" }],
  },
  {
    value: "SETUP_WASTE",
    label: "Bù hao setup / makeready",
    badge: "Setup",
    hint: "Makeready = cố định + theo màu × màu + theo mặt × mặt (clamp min/max).",
    methods: [
      { value: "COMBINED", label: "Cố định + theo màu + theo mặt" },
      { value: "FIXED", label: "Số tờ cố định" },
      { value: "PER_COLOR", label: "Theo số màu" },
      { value: "PER_SIDE", label: "Theo số mặt" },
      { value: "PER_COLOR_SIDE", label: "Theo màu × mặt (cũ)" },
    ],
  },
  {
    value: "RUNNING_WASTE",
    label: "Bù hao chạy máy",
    badge: "Running",
    hint: "Bù hao = clamp(ceil(sản lượng × %), min, max). Có thể chia bậc theo dải số lượng.",
    methods: [{ value: "PERCENT", label: "Theo % sản lượng" }],
  },
  {
    value: "PAPER_EXTRA_WASTE",
    label: "Hao giấy riêng",
    badge: "Giấy",
    hint: "Cộng vào số tờ mua giấy.",
    methods: [
      { value: "PERCENT", label: "% số tờ sản xuất" },
      { value: "FIXED", label: "Số tờ cố định" },
      { value: "PER_REAM", label: "Theo ram (tờ/ram)" },
    ],
  },
];

function groupOf(g: string | null): (typeof GROUPS)[number] | undefined {
  return GROUPS.find((x) => x.value === g);
}

// Nhãn trạng thái phiếu tính giá cho drill-down "Đang dùng trong".
const ESTIMATE_STATUS_LABEL: Record<string, string> = {
  draft: "Nháp",
  calculated: "Đã tính",
  converted_to_quote: "Đã lên báo giá",
  cancelled: "Đã hủy",
};

// Tab nhanh theo loại định mức (lọc nhanh cột "Nhóm").
const QUICK_TABS: { value: string; label: string }[] = [
  { value: "", label: "Tất cả" },
  { value: "SETUP_WASTE", label: "Setup" },
  { value: "RUNNING_WASTE", label: "Hao chạy máy" },
  { value: "PAPER_EXTRA_WASTE", label: "Hao giấy" },
  { value: "YIELD_RATE", label: "Tỷ lệ đạt" },
];

function todayStr(): string {
  return new Date().toISOString().split("T")[0];
}

// Diễn giải "Mức hao / Công thức" của một dòng bằng ngôn ngữ nghiệp vụ.
function valueDisplay(row: NormRow): string {
  const g = row.waste_group;
  if (g === "YIELD_RATE") return `Đạt ${(row.value * 100).toFixed(1)}%`;
  if (g === "RUNNING_WASTE") return `${(row.value * 100).toFixed(2)}% số tờ`;
  if (g === "SETUP_WASTE") {
    const parts: string[] = [];
    if (row.calculation_method === "PER_COLOR_SIDE" || (!row.setup_waste_qty && !row.setup_waste_per_color && !row.setup_waste_per_side))
      return `${row.value} tờ/màu-mặt`;
    if (row.setup_waste_qty) parts.push(`${row.setup_waste_qty}`);
    if (row.setup_waste_per_color) parts.push(`${row.setup_waste_per_color}×màu`);
    if (row.setup_waste_per_side) parts.push(`${row.setup_waste_per_side}×mặt`);
    const body = parts.join(" + ");
    return body ? `${body} tờ` : "0";
  }
  if (g === "PAPER_EXTRA_WASTE") {
    if (row.calculation_method === "FIXED") return `${row.value} tờ`;
    if (row.calculation_method === "PER_REAM") return `${row.value} tờ/ram`;
    return `${(row.value * 100).toFixed(2)}% tờ mua`;
  }
  return String(row.value);
}

// Nhãn "Cách tính" bằng tiếng Việt nghiệp vụ (thay cho enum FIXED/PERCENT/COMBINED).
const METHOD_LABEL: Record<string, string> = {
  FIXED: "Cố định",
  PERCENT: "Theo tỷ lệ %",
  COMBINED: "Công thức kết hợp",
  PER_COLOR: "Theo số màu",
  PER_SIDE: "Theo số mặt",
  PER_COLOR_SIDE: "Theo màu × mặt",
  PER_REAM: "Theo ram",
};
function methodLabel(m: string | null): string {
  return m ? METHOD_LABEL[m] ?? m : "—";
}

// Trạng thái suy từ ngày hiệu lực (không lưu enum): Sắp / Đang / Hết.
function statusOf(row: NormRow, today: string): { label: string; cls: string } {
  if (row.effective_from > today) return { label: "Sắp áp dụng", cls: "is-upcoming" };
  if (row.effective_to === null || row.effective_to > today) return { label: "Đang áp dụng", cls: "is-active" };
  return { label: "Hết hiệu lực", cls: "is-inactive" };
}

// Nhóm nào nhập giá trị dạng % (cho gõ 97 thay vì 0.97).
function isPercentValue(group: WasteGroup, method: string): boolean {
  if (group === "YIELD_RATE" || group === "RUNNING_WASTE") return true;
  if (group === "PAPER_EXTRA_WASTE" && method === "PERCENT") return true;
  return false;
}

export function NormsCatalogPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("dm_dinh_muc", "create");
  const canUpdate = can("dm_dinh_muc", "update");
  const canDelete = can("dm_dinh_muc", "delete");

  const [rows, setRows] = useState<NormRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [wasteGroupFilter, setWasteGroupFilter] = useState("");
  const [productTypeFilter, setProductTypeFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [operationFilter, setOperationFilter] = useState("");
  const [onlyCurrent, setOnlyCurrent] = useState(true);
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");

  const [productTypes, setProductTypes] = useState<{ product_type: string; name: string }[]>([]);
  const [machines, setMachines] = useState<{ id: number; name: string }[]>([]);
  const [operations, setOperations] = useState<{ id: number; name: string; code: string; operation_type?: string }[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "form" | "close" | "history">(null);
  const [basedOn, setBasedOn] = useState<NormRow | null>(null); // null = tạo mới; có = mở/tạo phiên bản từ dòng có sẵn
  const [selected, setSelected] = useState<NormRow | null>(null);
  const [deleting, setDeleting] = useState<NormRow | null>(null);
  const [history, setHistory] = useState<NormRow[]>([]);
  const [dlgTab, setDlgTab] = useState<"setup" | "test">("setup");
  const [menuFor, setMenuFor] = useState<number | null>(null); // dòng đang mở menu ⋯
  const [usageFor, setUsageFor] = useState<NormRow | null>(null); // "Đang dùng trong" drill-down
  const [usageData, setUsageData] = useState<NormUsageOut | null>(null);
  const [conflicts, setConflicts] = useState<NormConflictsOut>({ conflicts: {}, labels: {} });
  const conflictIds = useMemo(() => new Set(Object.keys(conflicts.conflicts).map(Number)), [conflicts]);

  const warnOnly = wasteGroupFilter === "__warn__";

  // --- Form state ---
  const [wasteGroup, setWasteGroup] = useState<WasteGroup>("YIELD_RATE");
  const [method, setMethod] = useState("PERCENT");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [valuePct, setValuePct] = useState(""); // giá trị dạng % (97 = 0.97) cho nhóm tỷ lệ
  const [operationKey, setOperationKey] = useState("");
  const [operationId, setOperationId] = useState("");
  const [applyProducts, setApplyProducts] = useState<string[]>([]);
  const [applyMachines, setApplyMachines] = useState<number[]>([]);
  const [qtyMin, setQtyMin] = useState("");
  const [qtyMax, setQtyMax] = useState("");
  const [ctxColors, setCtxColors] = useState("");
  const [ctxSides, setCtxSides] = useState("");
  const [setupQty, setSetupQty] = useState("");
  const [setupPerColor, setSetupPerColor] = useState("");
  const [setupPerSide, setSetupPerSide] = useState("");
  const [minWaste, setMinWaste] = useState("");
  const [maxWaste, setMaxWaste] = useState("");
  const [paperToPurchase, setPaperToPurchase] = useState(true);
  const [priority, setPriority] = useState("100");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [note, setNote] = useState("");

  // Close dialog
  const [effectiveTo, setEffectiveTo] = useState("");

  // Preview inputs (khối 3)
  const [pvColors, setPvColors] = useState("4");
  const [pvSides, setPvSides] = useState("2");
  const [pvBase, setPvBase] = useState("1000");

  // Test tab
  const [testQty, setTestQty] = useState("1000");
  const [testPPS, setTestPPS] = useState("4");
  const [testColors, setTestColors] = useState("4");
  const [testSides, setTestSides] = useState("2");
  const [testForms, setTestForms] = useState("1");
  const [testProduct, setTestProduct] = useState("");
  const [testMachine, setTestMachine] = useState("");
  const [testOps, setTestOps] = useState("");
  const [testResult, setTestResult] = useState<NormTestOutput | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const loadReferences = useCallback(() => {
    if (!token) return;
    api.productTypesCatalog.list(token, { page: 1, size: 200 }).then((res) => setProductTypes(res.items)).catch(() => {});
    api.machines.list(token, { page: 1, size: 200 }).then((res) => setMachines(res.items)).catch(() => {});
    api.operations.list(token, { page: 1, size: 200 }).then((res) => setOperations(res.items)).catch(() => {});
  }, [token]);

  const loadConflicts = useCallback(() => {
    if (!token) return;
    api.norms.conflicts(token).then(setConflicts).catch(() => {});
  }, [token]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    // Tab "Có cảnh báo": lấy toàn bộ bản hiện hành rồi lọc client theo conflictIds.
    const isWarn = wasteGroupFilter === "__warn__";
    api.norms
      .list(token, {
        q: q || null,
        waste_group: isWarn ? null : wasteGroupFilter || null,
        product_type: productTypeFilter || null,
        machine_id: machineFilter ? Number(machineFilter) : null,
        operation_id: operationFilter ? Number(operationFilter) : null,
        only_current: isWarn ? true : onlyCurrent,
        page: isWarn ? 1 : page,
        size: isWarn ? 200 : PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục Định mức & Bù hao.");
      })
      .finally(() => setLoading(false));
  }, [token, q, wasteGroupFilter, productTypeFilter, machineFilter, operationFilter, onlyCurrent, page]);

  useEffect(() => {
    load();
    loadReferences();
  }, [load, loadReferences]);

  useEffect(() => {
    loadConflicts();
  }, [loadConflicts]);

  function resetForm() {
    setWasteGroup("YIELD_RATE");
    setMethod("PERCENT");
    setCode("");
    setName("");
    setValue("");
    setValuePct("");
    setOperationKey("");
    setOperationId("");
    setApplyProducts([]);
    setApplyMachines([]);
    setQtyMin("");
    setQtyMax("");
    setCtxColors("");
    setCtxSides("");
    setSetupQty("");
    setSetupPerColor("");
    setSetupPerSide("");
    setMinWaste("");
    setMaxWaste("");
    setPaperToPurchase(true);
    setPriority("100");
    setNote("");
    setEffectiveFrom(todayStr());
    setTestResult(null);
    setTestError(null);
    setDlgTab("setup");
  }

  function handleCreateClick() {
    setBasedOn(null);
    resetForm();
    setMode("form");
  }

  function fillFromRow(row: NormRow) {
    const g = (row.waste_group ?? "YIELD_RATE") as WasteGroup;
    const m = row.calculation_method ?? "PERCENT";
    setWasteGroup(g);
    setMethod(m);
    setCode(row.code ?? "");
    setName(row.name ?? "");
    setValue(String(row.value ?? ""));
    setValuePct(isPercentValue(g, m) && row.value != null ? String(+(row.value * 100).toFixed(4)) : "");
    setOperationKey(row.operation_key ?? "");
    setOperationId(row.operation_id ? String(row.operation_id) : "");
    setApplyProducts(row.applicable_product_types ?? []);
    setApplyMachines(row.applicable_machine_ids ?? []);
    setQtyMin(row.qty_min != null ? String(row.qty_min) : "");
    setQtyMax(row.qty_max != null ? String(row.qty_max) : "");
    setCtxColors(row.context?.colors != null ? String(row.context.colors) : "");
    setCtxSides(row.context?.sides != null ? String(row.context.sides) : "");
    setSetupQty(row.setup_waste_qty != null ? String(row.setup_waste_qty) : "");
    setSetupPerColor(row.setup_waste_per_color != null ? String(row.setup_waste_per_color) : "");
    setSetupPerSide(row.setup_waste_per_side != null ? String(row.setup_waste_per_side) : "");
    setMinWaste(row.min_waste_qty != null ? String(row.min_waste_qty) : "");
    setMaxWaste(row.max_waste_qty != null ? String(row.max_waste_qty) : "");
    setPaperToPurchase(row.paper_add_to_purchase);
    setPriority(String(row.priority ?? 100));
    setNote(row.note ?? "");
    setTestResult(null);
    setTestError(null);
    setDlgTab("setup");
  }

  function handleOpenClick(row: NormRow) {
    // Mở: xem cấu hình đầy đủ; lưu = tạo phiên bản mới của chính cấu hình này.
    setMenuFor(null);
    setBasedOn(row);
    fillFromRow(row);
    setEffectiveFrom(todayStr());
    setMode("form");
  }

  function handleDuplicateFillClick(row: NormRow) {
    // Sao chép: mở form thêm mới thành quy tắc KHÁC (đổi mã), ngày hiệu lực = hôm nay.
    setMenuFor(null);
    setBasedOn(null);
    fillFromRow(row);
    setCode(row.code ? `${row.code}_COPY` : "");
    setEffectiveFrom(todayStr());
    setMode("form");
  }

  function onGroupChange(g: WasteGroup) {
    setWasteGroup(g);
    const grp = groupOf(g);
    const nextMethod = grp?.methods[0]?.value ?? "PERCENT";
    setMethod(nextMethod);
    // Đổi nhóm → giá trị cũ không còn ý nghĩa, xóa cả hai ô nhập.
    setValue("");
    setValuePct("");
  }

  // Giá trị dạng phân số gửi lên engine: nhóm % thì lấy từ ô % (97 → 0.97).
  function effectiveValue(): number {
    if (isPercentValue(wasteGroup, method)) return valuePct ? Number(valuePct) / 100 : 0;
    return value ? Number(value) : 0;
  }

  function buildPayload(): NormInput {
    const context: Record<string, number> = {};
    if (ctxColors) context.colors = Number(ctxColors);
    if (ctxSides) context.sides = Number(ctxSides);
    return {
      waste_group: wasteGroup,
      calculation_method: method,
      value: effectiveValue(),
      code: code || null,
      name: name || null,
      operation_id: operationId ? Number(operationId) : null,
      operation_key: operationKey || null,
      applicable_product_types: applyProducts.length ? applyProducts : null,
      applicable_machine_ids: applyMachines.length ? applyMachines : null,
      qty_min: qtyMin ? Number(qtyMin) : null,
      qty_max: qtyMax ? Number(qtyMax) : null,
      context: Object.keys(context).length ? context : null,
      setup_waste_qty: setupQty ? Number(setupQty) : null,
      setup_waste_per_color: setupPerColor ? Number(setupPerColor) : null,
      setup_waste_per_side: setupPerSide ? Number(setupPerSide) : null,
      min_waste_qty: minWaste ? Number(minWaste) : null,
      max_waste_qty: maxWaste ? Number(maxWaste) : null,
      paper_add_to_purchase: paperToPurchase,
      priority: priority ? Number(priority) : 100,
      effective_from: effectiveFrom,
      note: note || null,
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    // Validation client (soft).
    if (!code.trim()) {
      setError("Vui lòng nhập mã quy tắc — mã là danh tính của quy tắc (1 quy tắc = 1 mã).");
      return;
    }
    if (wasteGroup === "YIELD_RATE") {
      const v = effectiveValue();
      if (!(v > 0 && v <= 1)) {
        setError("Tỷ lệ đạt phải trong khoảng 0–100%.");
        return;
      }
    }
    if (minWaste && maxWaste && Number(maxWaste) < Number(minWaste)) {
      setError("Bù hao tối đa không được nhỏ hơn tối thiểu.");
      return;
    }
    if (operationId && operationKey) {
      setError("Chỉ chọn một trong hai: Công đoạn hệ thống hoặc từ khóa công đoạn.");
      return;
    }
    try {
      await api.norms.create(token, buildPayload());
      setMode(null);
      setPage(1);
      load();
      loadConflicts();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi lưu định mức.");
    }
  }

  async function runTest() {
    if (!token) return;
    setTestError(null);
    try {
      const res = await api.norms.test(token, {
        quantity: Number(testQty) || 0,
        pieces_per_sheet: Number(testPPS) || 1,
        colors: Number(testColors) || 1,
        sides: Number(testSides) || 1,
        forms: Number(testForms) || 1,
        product_type: testProduct || null,
        machine_id: testMachine ? Number(testMachine) : null,
        operation_keys: testOps.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setTestResult(res);
    } catch (err) {
      if (err instanceof ApiError) setTestError(err.message);
      else setTestError("Lỗi khi chạy test định mức.");
    }
  }

  async function openHistory(row: NormRow) {
    if (!token) return;
    setSelected(row);
    setMode("history");
    try {
      const res = await api.norms.history(token, row.id);
      setHistory(res.items);
    } catch {
      setHistory([]);
    }
  }

  async function openUsage(row: NormRow) {
    if (!token) return;
    setMenuFor(null);
    setUsageFor(row);
    setUsageData(null);
    try {
      setUsageData(await api.norms.usage(token, row.id));
    } catch {
      setUsageData(null);
    }
  }

  function handleCloseClick(row: NormRow) {
    setSelected(row);
    setEffectiveTo(todayStr());
    setMode("close");
  }

  async function handleCloseSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || !selected) return;
    setError(null);
    try {
      await api.norms.close(token, selected.id, effectiveTo);
      setMode(null);
      setSelected(null);
      load();
      loadConflicts();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi đóng định mức.");
    }
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    setError(null);
    try {
      await api.norms.remove(token, deleting.id);
      setDeleting(null);
      load();
      loadConflicts();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lỗi khi xóa định mức.");
      setDeleting(null);
    }
  }

  // --- Inline preview (khối 3) ---
  const preview = useMemo(() => {
    const colors = Number(pvColors) || 0;
    const sides = Number(pvSides) || 0;
    const base = Number(pvBase) || 0;
    const valFrac = isPercentValue(wasteGroup, method) ? (Number(valuePct) || 0) / 100 : (Number(value) || 0);
    const clamp = (v: number) => {
      let r = v;
      if (minWaste) r = Math.max(r, Number(minWaste));
      if (maxWaste) r = Math.min(r, Number(maxWaste));
      return r;
    };
    if (wasteGroup === "YIELD_RATE") {
      const y = valFrac || 1;
      return y > 0 ? `Cần trước = ceil(${base} / ${y}) = ${Math.ceil(base / y)} tờ` : "Nhập tỷ lệ đạt > 0";
    }
    if (wasteGroup === "SETUP_WASTE") {
      let mk: number;
      if (method === "PER_COLOR_SIDE") mk = valFrac * colors * sides;
      else mk = (Number(setupQty) || 0) + (Number(setupPerColor) || 0) * colors + (Number(setupPerSide) || 0) * sides;
      return `Makeready = ${Math.round(clamp(mk))} tờ (với ${colors} màu, ${sides} mặt)`;
    }
    if (wasteGroup === "RUNNING_WASTE") {
      const w = Math.ceil(base * valFrac);
      return `Running = clamp(ceil(${base} × ${(valFrac * 100).toFixed(2)}%)) = ${Math.round(clamp(w))} tờ`;
    }
    if (wasteGroup === "PAPER_EXTRA_WASTE") {
      let p: number;
      if (method === "FIXED") p = valFrac;
      else if (method === "PER_REAM") p = valFrac * (base / 500);
      else p = Math.ceil(base * valFrac);
      return `Hao giấy = ${Math.round(clamp(p))} tờ → cộng vào tờ mua`;
    }
    return "";
  }, [wasteGroup, method, value, valuePct, setupQty, setupPerColor, setupPerSide, minWaste, maxWaste, pvColors, pvSides, pvBase]);

  if (forbidden) {
    return (
      <div className="md-page">
        <div className="banner banner--error">Bạn không có quyền xem danh mục Định mức & Bù hao (403).</div>
      </div>
    );
  }

  const grp = groupOf(wasteGroup);
  const isYield = wasteGroup === "YIELD_RATE";
  const isSetup = wasteGroup === "SETUP_WASTE";
  const isRunning = wasteGroup === "RUNNING_WASTE";
  const isPaper = wasteGroup === "PAPER_EXTRA_WASTE";
  const today = todayStr();
  const displayRows = warnOnly ? rows.filter((r) => conflictIds.has(r.id)) : rows;

  return (
    <div className="md-page">
      <div className="md-page__head">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 className="md-page__title">Định mức & Bù hao</h1>
            <p className="md-page__sub">Khai báo quy tắc setup, hao chạy máy, hao giấy & tỷ lệ đạt → engine tính số tờ sản xuất, số tờ mua giấy và chi phí công đoạn.</p>
          </div>
          {canCreate && <Button variant="primary" onClick={handleCreateClick}>+ Tạo quy tắc</Button>}
        </div>
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {/* Tab nhanh theo loại định mức */}
      <div className="md-page__tabs">
        {QUICK_TABS.map((t) => (
          <button
            key={t.value || "all"}
            type="button"
            className={`md-page__tab ${wasteGroupFilter === t.value ? "md-page__tab--active" : ""}`}
            onClick={() => { setWasteGroupFilter(t.value); setPage(1); }}
          >
            {t.label}
          </button>
        ))}
        <button
          type="button"
          className={`md-page__tab md-page__tab--warn ${warnOnly ? "md-page__tab--active" : ""}`}
          onClick={() => { setWasteGroupFilter("__warn__"); setPage(1); }}
          title="Các quy tắc cùng độ cụ thể + phạm vi giao nhau — engine không phân xử rõ được."
        >
          ⚠ Có cảnh báo
          {conflictIds.size > 0 && <span className="md-page__tab__count">{conflictIds.size}</span>}
        </button>
      </div>

      {/* Filters */}
      <div className="md-page__toolbar">
        <form
          className="md-page__search"
          onSubmit={(e) => { e.preventDefault(); setQ(qInput.trim()); setPage(1); }}
        >
          <input
            className="input"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="Tìm theo mã / tên quy tắc…"
            aria-label="Tìm quy tắc định mức"
          />
          <Button variant="secondary" type="submit">Tìm</Button>
          {q && (
            <Button variant="ghost" type="button" onClick={() => { setQ(""); setQInput(""); setPage(1); }}>Xóa lọc</Button>
          )}
        </form>
        <div className="md-page__filter">
          <select className="input select" value={productTypeFilter} onChange={(e) => { setProductTypeFilter(e.target.value); setPage(1); }} aria-label="Lọc loại sản phẩm">
            <option value="">-- Tất cả loại SP --</option>
            {productTypes.map((p) => <option key={p.product_type} value={p.product_type}>{p.name}</option>)}
          </select>
        </div>
        <div className="md-page__filter">
          <select className="input select" value={machineFilter} onChange={(e) => { setMachineFilter(e.target.value); setPage(1); }} aria-label="Lọc máy">
            <option value="">-- Tất cả máy --</option>
            {machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>
        <div className="md-page__filter">
          <select className="input select" value={operationFilter} onChange={(e) => { setOperationFilter(e.target.value); setPage(1); }} aria-label="Lọc công đoạn">
            <option value="">-- Tất cả công đoạn --</option>
            {operations.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.code})</option>)}
          </select>
        </div>
        <div className="md-page__filter">
          <select className="input select" value={onlyCurrent ? "current" : "all"} onChange={(e) => { setOnlyCurrent(e.target.value === "current"); setPage(1); }} aria-label="Lọc phiên bản">
            <option value="current">Bản hiện hành</option>
            <option value="all">Tất cả phiên bản</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="card md-page__tablewrap">
        {loading ? (
          <div style={{ padding: "40px", textAlign: "center" }}>Đang tải định mức...</div>
        ) : displayRows.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center" }} className="md-page__muted">
            {warnOnly ? "Không có quy tắc nào đang cảnh báo xung đột." : "Không tìm thấy định mức nào."}
          </div>
        ) : (
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Quy tắc</th>
                <th>Nhóm</th>
                <th>Công đoạn</th>
                <th>Mức hao / Công thức</th>
                <th>Áp dụng cho</th>
                <th title="Engine ưu tiên quy tắc CỤ THỂ hơn (khớp nhiều điều kiện). Số ưu tiên chỉ dùng để phá hòa khi độ cụ thể bằng nhau — số LỚN hơn = ưu tiên cao hơn.">Ưu tiên&nbsp;ⓘ</th>
                <th>Đang dùng trong</th>
                <th>Hiệu lực</th>
                <th>Trạng thái</th>
                <th className="md-page__actions-col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row) => {
                const g = groupOf(row.waste_group);
                const op = operations.find((o) => o.id === row.operation_id);
                const st = statusOf(row, today);
                const rowConflicts = conflicts.conflicts[String(row.id)] || [];
                const active = row.effective_to === null || row.effective_to > today;
                const applyLabel = row.applicable_product_types?.length
                  ? `${row.applicable_product_types.length} loại SP`
                  : row.product_type
                  ? productTypes.find((p) => p.product_type === row.product_type)?.name ?? row.product_type
                  : row.applicable_machine_ids?.length
                  ? `${row.applicable_machine_ids.length} máy`
                  : row.machine_id
                  ? machines.find((m) => m.id === row.machine_id)?.name ?? `Máy ${row.machine_id}`
                  : "Tất cả";
                return (
                  <tr key={row.id}>
                    <td className="md-page__mono">{row.code || <span className="md-page__muted">—</span>}</td>
                    <td>{row.name || <span className="md-page__muted">{row.norm_key}</span>}</td>
                    <td>{g ? <span className="md-page__tag">{g.badge}</span> : <span className="md-page__muted">Đơn giá</span>}</td>
                    <td>{op ? op.name : row.operation_key ? <span className="md-page__mono">{row.operation_key}</span> : <span className="md-page__muted">Khâu in/chung</span>}</td>
                    <td>
                      <div className="md-page__price" style={{ fontSize: "14px" }}>{valueDisplay(row)}</div>
                      <div className="md-page__formula-sub">{methodLabel(row.calculation_method)}</div>
                    </td>
                    <td>{applyLabel === "Tất cả" ? <span className="md-page__muted">Tất cả</span> : <span className="md-page__tag-tech">{applyLabel}</span>}</td>
                    <td style={{ textAlign: "right" }} title="Số lớn hơn = ưu tiên cao hơn (chỉ phá hòa khi độ cụ thể bằng nhau)">{row.priority}</td>
                    <td>
                      {row.estimate_count > 0 ? (
                        <button type="button" className="md-page__usage-link" onClick={() => openUsage(row)}>
                          {row.estimate_count} phiếu tính giá
                        </button>
                      ) : (
                        <span className="md-page__usage-zero">0 phiếu</span>
                      )}
                    </td>
                    <td style={{ fontSize: "12px" }}>{row.effective_from}{row.effective_to ? ` → ${row.effective_to}` : ""} {row.version > 1 && <span className="md-page__tag">v{row.version}</span>}</td>
                    <td>
                      <span className={`md-page__status-badge ${st.cls}`}>{st.label}</span>
                      {rowConflicts.length > 0 && (
                        <span
                          className="md-page__conflict-flag"
                          title={`Có thể xung đột với: ${rowConflicts.map((id) => conflicts.labels[String(id)] || `#${id}`).join(", ")}`}
                        >
                          ⚠
                        </span>
                      )}
                    </td>
                    <td className="md-page__actions-col">
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => handleOpenClick(row)}>Mở</button>
                      <span className="md-page__menu-wrap">
                        <button
                          type="button"
                          className="md-page__iconbtn"
                          title="Thao tác khác"
                          aria-haspopup="menu"
                          onClick={() => setMenuFor(menuFor === row.id ? null : row.id)}
                        >
                          ⋯
                        </button>
                        {menuFor === row.id && (
                          <>
                            <div style={{ position: "fixed", inset: 0, zIndex: 29 }} onClick={() => setMenuFor(null)} />
                            <div className="md-page__menu" role="menu">
                              {canUpdate && <button type="button" onClick={() => handleOpenClick(row)}>Tạo phiên bản mới</button>}
                              {canCreate && <button type="button" onClick={() => handleDuplicateFillClick(row)}>Sao chép thành quy tắc mới</button>}
                              {active && canUpdate && <button type="button" onClick={() => { setMenuFor(null); handleCloseClick(row); }}>Ngừng áp dụng</button>}
                              {row.estimate_count > 0 && <button type="button" onClick={() => openUsage(row)}>Xem phiếu tính giá đang dùng</button>}
                              <button type="button" onClick={() => { setMenuFor(null); openHistory(row); }}>Xem lịch sử</button>
                              {canDelete && row.effective_from > today && (
                                <>
                                  <div className="md-page__menu__sep" />
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
              })}
            </tbody>
          </table>
        )}
      </div>

      {!warnOnly && total > PAGE_SIZE && (
        <div className="md-page__pager">
          <span>Tổng số: <strong>{total}</strong> quy tắc</span>
          <div className="md-page__pager-btns">
            <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Trước</Button>
            <span style={{ alignSelf: "center", padding: "0 10px" }}>Trang {page} / {Math.ceil(total / PAGE_SIZE)}</span>
            <Button variant="secondary" disabled={page * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>Sau</Button>
          </div>
        </div>
      )}

      {/* Create/Edit dialog with tabs */}
      {mode === "form" && (
        <div className="md-page__overlay">
          <div className="card md-page__dialog">
            <div className="md-page__dialog-head">
              <h2>{basedOn ? `Quy tắc: ${basedOn.code || basedOn.name || basedOn.norm_key}` : "Tạo quy tắc Định mức / Bù hao"}</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: "8px", padding: "0 var(--sp-4)", borderBottom: "1px solid var(--rule-soft)" }}>
              <button type="button" className={`btn ${dlgTab === "setup" ? "btn--primary" : "btn--ghost"}`} onClick={() => setDlgTab("setup")}>Thiết lập</button>
              <button type="button" className={`btn ${dlgTab === "test" ? "btn--primary" : "btn--ghost"}`} onClick={() => setDlgTab("test")}>Test nhanh</button>
            </div>

            {dlgTab === "setup" ? (
              <form className="md-page__dialog-body" onSubmit={handleSubmit}>
                {basedOn && (
                  <div className="md-page__hint" style={{ background: "var(--rust-soft)" }}>
                    {basedOn.estimate_count > 0 && (
                      <>Quy tắc này đang dùng trong <strong>{basedOn.estimate_count} phiếu tính giá</strong>. </>
                    )}
                    Định mức không sửa trực tiếp. <strong>Lưu</strong> sẽ tạo <strong>phiên bản mới</strong> (đóng bản đang chạy từ ngày hiệu lực này) — báo giá cũ vẫn giữ nguyên bản cũ.
                  </div>
                )}
                {basedOn && (conflicts.conflicts[String(basedOn.id)]?.length ?? 0) > 0 && (
                  <div className="md-page__hint" style={{ background: "var(--signal-soft, #fdecec)" }}>
                    ⚠ Quy tắc có thể xung đột với: <strong>{(conflicts.conflicts[String(basedOn.id)] || []).map((id) => conflicts.labels[String(id)] || `#${id}`).join(", ")}</strong>. Các quy tắc cùng độ cụ thể + phạm vi giao nhau — engine chỉ còn phân xử bằng ưu tiên / ngày hiệu lực. Cân nhắc thu hẹp phạm vi hoặc chỉnh ưu tiên.
                  </div>
                )}
                {/* Khối 1 — Thông tin chung */}
                <h3 className="md-page__section-title">① Thông tin chung</h3>
                <div className="md-page__form-grid">
                  <div>
                    <label className="label">Nhóm định mức</label>
                    <select className="input select" value={wasteGroup} onChange={(e) => onGroupChange(e.target.value as WasteGroup)}>
                      {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label">Cách tính</label>
                    <select className="input select" value={method} onChange={(e) => setMethod(e.target.value)}>
                      {grp?.methods.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label">Mã định mức *</label>
                    <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="VD: MR_PRINT_4C" required />
                    <p className="md-page__note" style={{ fontSize: "11px", marginTop: "2px" }}>Mã là danh tính quy tắc — 2 mã khác nhau luôn chạy song song, không âm thầm đè nhau.</p>
                  </div>
                  <div>
                    <label className="label">Tên định mức</label>
                    <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="VD: Makeready in 4 màu" />
                  </div>
                </div>
                <p className="md-page__muted" style={{ fontSize: "12px", margin: "4px 0" }}>{grp?.hint}</p>

                {/* Khối 2 — Phạm vi áp dụng */}
                <h3 className="md-page__section-title">② Phạm vi áp dụng</h3>
                <div className="md-page__form-grid">
                  <div>
                    <label className="label">Loại sản phẩm (bỏ trống = tất cả)</label>
                    <div className="md-page__checkboxes">
                      {productTypes.map((p) => (
                        <label key={p.product_type} className="md-page__checkbox-label">
                          <input type="checkbox" checked={applyProducts.includes(p.product_type)} onChange={(e) => setApplyProducts((prev) => e.target.checked ? [...prev, p.product_type] : prev.filter((x) => x !== p.product_type))} />
                          {p.name}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="label">Máy áp dụng (bỏ trống = tất cả)</label>
                    <div className="md-page__checkboxes">
                      {machines.map((m) => (
                        <label key={m.id} className="md-page__checkbox-label">
                          <input type="checkbox" checked={applyMachines.includes(m.id)} onChange={(e) => setApplyMachines((prev) => e.target.checked ? [...prev, m.id] : prev.filter((x) => x !== m.id))} />
                          {m.name}
                        </label>
                      ))}
                    </div>
                  </div>
                  {(isYield || isSetup || isRunning) && (
                    <>
                      <div>
                        <label className="label">Công đoạn hệ thống (tỷ lệ đạt/setup theo CĐ)</label>
                        <select className="input select" value={operationId} onChange={(e) => { setOperationId(e.target.value); if (e.target.value) setOperationKey(""); }}>
                          <option value="">-- Khâu in / chung --</option>
                          {operations.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.code})</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="label">Hoặc từ khóa công đoạn</label>
                        <input className="input" value={operationKey} onChange={(e) => { setOperationKey(e.target.value); if (e.target.value) setOperationId(""); }} placeholder="VD: be, can_mang, dan_hop" />
                      </div>
                    </>
                  )}
                  {isRunning && (
                    <>
                      <div>
                        <label className="label">Dải sản lượng từ</label>
                        <input type="number" className="input" value={qtyMin} onChange={(e) => setQtyMin(e.target.value)} placeholder="VD: 1" min="0" />
                      </div>
                      <div>
                        <label className="label">Dải sản lượng đến</label>
                        <input type="number" className="input" value={qtyMax} onChange={(e) => setQtyMax(e.target.value)} placeholder="VD: 500 (trống = ∞)" min="0" />
                      </div>
                    </>
                  )}
                  <div>
                    <label className="label">Thứ tự ưu tiên</label>
                    <input type="number" className="input" value={priority} onChange={(e) => setPriority(e.target.value)} />
                    <p className="md-page__muted" style={{ fontSize: "11px", margin: "2px 0 0" }}>
                      Engine chọn quy tắc <strong>cụ thể hơn</strong> (khớp nhiều điều kiện) trước. Số này chỉ phá hòa khi độ cụ thể bằng nhau — <strong>số lớn hơn = ưu tiên cao hơn</strong>.
                    </p>
                  </div>
                </div>

                {/* Khối 3 — Cách tính (đổi theo nhóm) */}
                <h3 className="md-page__section-title">③ Cách tính</h3>
                <div className="md-page__form-grid">
                  {isPercentValue(wasteGroup, method) && (
                    <div>
                      <label className="label">
                        {isYield ? "Tỷ lệ đạt (%)" : isRunning ? "Tỷ lệ hao (%)" : "Tỷ lệ hao giấy (%)"}
                      </label>
                      <input type="number" step="0.01" className="input" value={valuePct} onChange={(e) => setValuePct(e.target.value)} placeholder={isYield ? "97" : "1.5"} />
                      <p className="md-page__muted" style={{ fontSize: "11px", margin: "2px 0 0" }}>
                        Gõ theo % (VD {isYield ? "97" : "1.5"}). Hệ thống tự lưu {isYield ? "0.97" : "0.015"} cho engine.
                      </p>
                    </div>
                  )}
                  {isPaper && (method === "FIXED" || method === "PER_REAM") && (
                    <div>
                      <label className="label">{method === "FIXED" ? "Số tờ cố định" : "Số tờ / ram"}</label>
                      <input type="number" step="0.001" className="input" value={value} onChange={(e) => setValue(e.target.value)} placeholder={method === "PER_REAM" ? "5" : "20"} />
                    </div>
                  )}
                  {isSetup && method === "PER_COLOR_SIDE" && (
                    <div>
                      <label className="label">Số tờ / màu-mặt (cũ)</label>
                      <input type="number" className="input" value={value} onChange={(e) => setValue(e.target.value)} placeholder="15" />
                    </div>
                  )}
                  {isSetup && (method === "FIXED" || method === "COMBINED") && (
                    <div>
                      <label className="label">Số tờ cố định</label>
                      <input type="number" className="input" value={setupQty} onChange={(e) => setSetupQty(e.target.value)} placeholder="100" />
                    </div>
                  )}
                  {isSetup && (method === "PER_COLOR" || method === "COMBINED") && (
                    <div>
                      <label className="label">Số tờ / màu</label>
                      <input type="number" className="input" value={setupPerColor} onChange={(e) => setSetupPerColor(e.target.value)} placeholder="30" />
                    </div>
                  )}
                  {isSetup && (method === "PER_SIDE" || method === "COMBINED") && (
                    <div>
                      <label className="label">Số tờ / mặt</label>
                      <input type="number" className="input" value={setupPerSide} onChange={(e) => setSetupPerSide(e.target.value)} placeholder="50" />
                    </div>
                  )}
                  {(isSetup || isRunning || isPaper) && (
                    <>
                      <div>
                        <label className="label">Min (tờ)</label>
                        <input type="number" className="input" value={minWaste} onChange={(e) => setMinWaste(e.target.value)} placeholder="—" />
                      </div>
                      <div>
                        <label className="label">Max (tờ)</label>
                        <input type="number" className="input" value={maxWaste} onChange={(e) => setMaxWaste(e.target.value)} placeholder="—" />
                      </div>
                    </>
                  )}
                  {isPaper && (
                    <div className="md-page__toggle-wrap">
                      <input type="checkbox" id="paper2p" checked={paperToPurchase} onChange={(e) => setPaperToPurchase(e.target.checked)} />
                      <label htmlFor="paper2p">Cộng vào số tờ mua giấy</label>
                    </div>
                  )}
                  {(isSetup || isYield) && (
                    <>
                      <div>
                        <label className="label">Số màu (context, tùy chọn)</label>
                        <input type="number" className="input" value={ctxColors} onChange={(e) => setCtxColors(e.target.value)} placeholder="VD: 4" min="1" />
                      </div>
                      <div>
                        <label className="label">Số mặt (context, tùy chọn)</label>
                        <input type="number" className="input" value={ctxSides} onChange={(e) => setCtxSides(e.target.value)} placeholder="VD: 2" min="1" />
                      </div>
                    </>
                  )}
                </div>

                {/* Preview */}
                <div className="md-page__preview">
                  <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "6px" }}>
                    <span className="md-page__muted" style={{ fontSize: "12px" }}>Xem thử với:</span>
                    <input className="input" style={{ width: "70px" }} type="number" value={pvColors} onChange={(e) => setPvColors(e.target.value)} title="màu" /> màu
                    <input className="input" style={{ width: "70px" }} type="number" value={pvSides} onChange={(e) => setPvSides(e.target.value)} title="mặt" /> mặt
                    <input className="input" style={{ width: "90px" }} type="number" value={pvBase} onChange={(e) => setPvBase(e.target.value)} title="số tờ nền" /> tờ nền
                  </div>
                  <div className="md-page__mono" style={{ fontSize: "13px" }}>{preview}</div>
                  {isYield && valuePct !== "" && Number(valuePct) > 0 && Number(valuePct) < 80 && (
                    <div style={{ color: "var(--rust, #b45309)", fontSize: "12px", marginTop: "4px" }}>
                      ⚠ Tỷ lệ đạt {Number(valuePct).toFixed(0)}% khá thấp (&lt; 80%) — kiểm tra lại kẻo nhập nhầm.
                    </div>
                  )}
                </div>

                {/* Khối 4 — Hiệu lực */}
                <h3 className="md-page__section-title">④ Hiệu lực</h3>
                <div className="md-page__form-grid">
                  <div>
                    <label className="label">Ngày hiệu lực từ</label>
                    <input type="date" className="input" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} required />
                  </div>
                  <div>
                    <label className="label">Ghi chú</label>
                    <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Diễn giải" />
                  </div>
                </div>

                <div className="md-page__dialog-actions">
                  <Button variant="secondary" type="button" onClick={() => setMode(null)}>Hủy</Button>
                  <Button variant="primary" type="submit">Lưu thiết lập</Button>
                </div>
              </form>
            ) : (
              <div className="md-page__dialog-body">
                <h3 className="md-page__section-title">⑤ Test nhanh — chạy thử số tờ với định mức hiện hành</h3>
                <div className="md-page__form-grid">
                  <div><label className="label">Số lượng đặt</label><input type="number" className="input" value={testQty} onChange={(e) => setTestQty(e.target.value)} /></div>
                  <div><label className="label">Số con / tờ</label><input type="number" className="input" value={testPPS} onChange={(e) => setTestPPS(e.target.value)} /></div>
                  <div><label className="label">Số màu</label><input type="number" className="input" value={testColors} onChange={(e) => setTestColors(e.target.value)} /></div>
                  <div><label className="label">Số mặt</label><input type="number" className="input" value={testSides} onChange={(e) => setTestSides(e.target.value)} /></div>
                  <div><label className="label">Số khuôn (forms)</label><input type="number" className="input" value={testForms} onChange={(e) => setTestForms(e.target.value)} /></div>
                  <div>
                    <label className="label">Loại sản phẩm</label>
                    <select className="input select" value={testProduct} onChange={(e) => setTestProduct(e.target.value)}>
                      <option value="">-- Không --</option>
                      {productTypes.map((p) => <option key={p.product_type} value={p.product_type}>{p.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label">Máy</label>
                    <select className="input select" value={testMachine} onChange={(e) => setTestMachine(e.target.value)}>
                      <option value="">-- Không --</option>
                      {machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                    </select>
                  </div>
                  <div className="md-page__form-wide">
                    <label className="label">Chuỗi công đoạn sau in (mã, cách nhau dấu phẩy — thứ tự sản xuất)</label>
                    <input className="input" value={testOps} onChange={(e) => setTestOps(e.target.value)} placeholder="VD: can_mang, be, dan_hop" />
                    <p className="md-page__muted" style={{ fontSize: "11px" }}>Mã có sẵn: {operations.map((o) => o.operation_type || o.code).filter(Boolean).join(", ")}</p>
                  </div>
                </div>
                <div style={{ margin: "10px 0" }}>
                  <Button variant="primary" type="button" onClick={runTest}>Test công thức</Button>
                </div>
                {testError && <div className="banner banner--error">{testError}</div>}
                {testResult && (
                  <div className="md-page__preview">
                    <table className="md-page__table" style={{ fontSize: "13px" }}>
                      <tbody>
                        <tr><td>Số tờ lý thuyết</td><td style={{ textAlign: "right" }}><strong>{testResult.theoretical_sheets.toLocaleString("vi-VN")}</strong></td></tr>
                        <tr><td>Cần trước in</td><td style={{ textAlign: "right" }}>{testResult.required_before_print.toLocaleString("vi-VN")}</td></tr>
                        <tr><td>Sau tỷ lệ đạt in</td><td style={{ textAlign: "right" }}>{testResult.sheets_after_yield.toLocaleString("vi-VN")}</td></tr>
                        <tr><td>Makeready</td><td style={{ textAlign: "right" }}>{testResult.makeready_sheets.toLocaleString("vi-VN")}</td></tr>
                        <tr><td>Số tờ sản xuất</td><td style={{ textAlign: "right" }}><strong>{testResult.production_sheets.toLocaleString("vi-VN")}</strong></td></tr>
                        <tr><td>Hao giấy riêng</td><td style={{ textAlign: "right" }}>{testResult.paper_extra_sheets.toLocaleString("vi-VN")}</td></tr>
                        <tr><td>Số tờ mua giấy</td><td style={{ textAlign: "right" }}><strong className="md-page__price">{testResult.purchase_sheets.toLocaleString("vi-VN")}</strong></td></tr>
                      </tbody>
                    </table>
                    <div style={{ marginTop: "8px" }}>
                      <div className="md-page__muted" style={{ fontSize: "11px", fontWeight: "bold" }}>DIỄN GIẢI TỪNG BƯỚC</div>
                      {testResult.steps.map((s, i) => (
                        <div key={i} className="md-page__mono" style={{ fontSize: "12px", padding: "2px 0" }}>
                          {s.label}: {s.detail} {s.rule_code && <span className="md-page__tag">{s.rule_code}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Close dialog */}
      {mode === "close" && selected && (
        <div className="md-page__overlay">
          <form className="card md-page__dialog md-page__dialog--sm" onSubmit={handleCloseSubmit}>
            <div className="md-page__dialog-head">
              <h2>Ngừng áp dụng quy tắc</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Ngừng áp dụng quy tắc <strong>{selected.code || selected.name || selected.norm_key}</strong> kể từ ngày dưới đây. Báo giá đã dùng bản này vẫn giữ nguyên.</p>
              <div>
                <label className="label">Ngày kết thúc (không gồm ngày này)</label>
                <input type="date" className="input" value={effectiveTo} onChange={(e) => setEffectiveTo(e.target.value)} required />
              </div>
              <div className="md-page__dialog-actions">
                <Button variant="secondary" type="button" onClick={() => setMode(null)}>Hủy</Button>
                <Button variant="danger" type="submit">Xác nhận ngừng</Button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* History dialog */}
      {mode === "history" && selected && (
        <div className="md-page__overlay">
          <div className="card md-page__dialog">
            <div className="md-page__dialog-head">
              <h2>Lịch sử version — {selected.code || selected.norm_key}</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <table className="md-page__table">
                <thead><tr><th>Version</th><th>Mức hao / Công thức</th><th>Áp dụng từ</th><th>Đến</th><th>Đang dùng</th></tr></thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td>v{h.version}</td>
                      <td className="md-page__price">{valueDisplay(h)}</td>
                      <td>{h.effective_from}</td>
                      <td>{h.effective_to || <span className="md-page__muted">Vô hạn</span>}</td>
                      <td style={{ textAlign: "right" }}>{h.estimate_count > 0 ? `${h.estimate_count} phiếu` : <span className="md-page__muted">—</span>}</td>
                    </tr>
                  ))}
                  {history.length === 0 && <tr><td colSpan={5} className="md-page__muted" style={{ textAlign: "center" }}>Không có dữ liệu.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Usage drill-down — "Đang dùng trong" */}
      {usageFor && (
        <div className="md-page__overlay">
          <div className="card md-page__dialog">
            <div className="md-page__dialog-head">
              <h2>Phiếu tính giá đang dùng — {usageFor.code || usageFor.name || usageFor.norm_key}</h2>
              <button type="button" className="md-page__close" onClick={() => { setUsageFor(null); setUsageData(null); }}>×</button>
            </div>
            <div className="md-page__dialog-body">
              {usageData === null ? (
                <p className="md-page__muted">Đang tải…</p>
              ) : usageData.estimate_count === 0 ? (
                <p className="md-page__muted">Chưa có phiếu tính giá nào dùng quy tắc này.</p>
              ) : (
                <>
                  <p className="md-page__muted" style={{ fontSize: "12px" }}>
                    <strong>{usageData.estimate_count}</strong> phiếu tính giá đang tham chiếu quy tắc này
                    {usageData.estimates.length < usageData.estimate_count ? ` (hiện ${usageData.estimates.length} phiếu gần nhất)` : ""}. Sửa quy tắc đã dùng → hãy tạo phiên bản mới để không lệch báo giá cũ.
                  </p>
                  <table className="md-page__table">
                    <thead><tr><th>Số phiếu</th><th>Sản phẩm</th><th>Trạng thái</th><th>Ngày tạo</th></tr></thead>
                    <tbody>
                      {usageData.estimates.map((e) => (
                        <tr key={e.id}>
                          <td className="md-page__mono">{e.estimate_number}</td>
                          <td>{e.product_name}</td>
                          <td>{ESTIMATE_STATUS_LABEL[e.status] ?? e.status}</td>
                          <td style={{ fontSize: "12px" }}>{new Date(e.created_at).toLocaleDateString("vi-VN")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleting && (
        <div className="md-page__overlay">
          <div className="card md-page__dialog md-page__dialog--sm">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa</h2>
              <button type="button" className="md-page__close" onClick={() => setDeleting(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Xóa vĩnh viễn quy tắc định mức tương lai này?</p>
              <div className="md-page__dialog-actions">
                <Button variant="secondary" onClick={() => setDeleting(null)}>Hủy</Button>
                <Button variant="danger" onClick={handleDelete}>Xác nhận xóa</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
