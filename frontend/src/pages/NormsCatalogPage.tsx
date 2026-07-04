import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type NormRow,
  type NormInput,
  type NormTestOutput,
  type WasteGroup,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
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

function todayStr(): string {
  return new Date().toISOString().split("T")[0];
}

// Diễn giải giá trị của một dòng trên bảng danh sách.
function valueDisplay(row: NormRow): string {
  const g = row.waste_group;
  if (g === "YIELD_RATE") return `${(row.value * 100).toFixed(1)}%`;
  if (g === "RUNNING_WASTE") return `${(row.value * 100).toFixed(2)}%`;
  if (g === "SETUP_WASTE") {
    const parts: string[] = [];
    if (row.calculation_method === "PER_COLOR_SIDE" || (!row.setup_waste_qty && !row.setup_waste_per_color && !row.setup_waste_per_side))
      return `${row.value} tờ/màu-mặt`;
    if (row.setup_waste_qty) parts.push(`${row.setup_waste_qty} cố định`);
    if (row.setup_waste_per_color) parts.push(`${row.setup_waste_per_color}/màu`);
    if (row.setup_waste_per_side) parts.push(`${row.setup_waste_per_side}/mặt`);
    return parts.join(" + ") || "0";
  }
  if (g === "PAPER_EXTRA_WASTE") {
    if (row.calculation_method === "FIXED") return `${row.value} tờ`;
    if (row.calculation_method === "PER_REAM") return `${row.value} tờ/ram`;
    return `${(row.value * 100).toFixed(2)}%`;
  }
  return String(row.value);
}

export function NormsCatalogPage() {
  const { token } = useAuth();

  const [rows, setRows] = useState<NormRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [wasteGroupFilter, setWasteGroupFilter] = useState("");
  const [productTypeFilter, setProductTypeFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [operationFilter, setOperationFilter] = useState("");
  const [onlyCurrent, setOnlyCurrent] = useState(true);

  const [productTypes, setProductTypes] = useState<{ product_type: string; name: string }[]>([]);
  const [machines, setMachines] = useState<{ id: number; name: string }[]>([]);
  const [operations, setOperations] = useState<{ id: number; name: string; code: string; operation_type?: string }[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "form" | "close" | "history">(null);
  const [editing, setEditing] = useState<NormRow | null>(null); // null = create
  const [selected, setSelected] = useState<NormRow | null>(null);
  const [deleting, setDeleting] = useState<NormRow | null>(null);
  const [history, setHistory] = useState<NormRow[]>([]);
  const [dlgTab, setDlgTab] = useState<"setup" | "test">("setup");

  // --- Form state ---
  const [wasteGroup, setWasteGroup] = useState<WasteGroup>("YIELD_RATE");
  const [method, setMethod] = useState("PERCENT");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
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

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.norms
      .list(token, {
        waste_group: wasteGroupFilter || null,
        product_type: productTypeFilter || null,
        machine_id: machineFilter ? Number(machineFilter) : null,
        operation_id: operationFilter ? Number(operationFilter) : null,
        only_current: onlyCurrent,
        page,
        size: PAGE_SIZE,
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
  }, [token, wasteGroupFilter, productTypeFilter, machineFilter, operationFilter, onlyCurrent, page]);

  useEffect(() => {
    load();
    loadReferences();
  }, [load, loadReferences]);

  function resetForm() {
    setWasteGroup("YIELD_RATE");
    setMethod("PERCENT");
    setCode("");
    setName("");
    setValue("");
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
    setEditing(null);
    resetForm();
    setMode("form");
  }

  function fillFromRow(row: NormRow) {
    setWasteGroup((row.waste_group ?? "YIELD_RATE") as WasteGroup);
    setMethod(row.calculation_method ?? "PERCENT");
    setCode(row.code ?? "");
    setName(row.name ?? "");
    setValue(String(row.value ?? ""));
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

  function handleDuplicateFillClick(row: NormRow) {
    // Sao chép: mở form thêm mới với giá trị copy, ngày hiệu lực = hôm nay.
    setEditing(null);
    fillFromRow(row);
    setCode(row.code ? `${row.code}_COPY` : "");
    setEffectiveFrom(todayStr());
    setMode("form");
  }

  function onGroupChange(g: WasteGroup) {
    setWasteGroup(g);
    const grp = groupOf(g);
    setMethod(grp?.methods[0]?.value ?? "PERCENT");
  }

  function buildPayload(): NormInput {
    const context: Record<string, number> = {};
    if (ctxColors) context.colors = Number(ctxColors);
    if (ctxSides) context.sides = Number(ctxSides);
    return {
      waste_group: wasteGroup,
      calculation_method: method,
      value: value ? Number(value) : 0,
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
    if (wasteGroup === "YIELD_RATE") {
      const v = Number(value);
      if (!(v > 0 && v <= 1)) {
        setError("Tỷ lệ đạt phải trong khoảng (0, 1].");
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
    const clamp = (v: number) => {
      let r = v;
      if (minWaste) r = Math.max(r, Number(minWaste));
      if (maxWaste) r = Math.min(r, Number(maxWaste));
      return r;
    };
    if (wasteGroup === "YIELD_RATE") {
      const y = Number(value) || 1;
      return y > 0 ? `Cần trước = ceil(${base} / ${y}) = ${Math.ceil(base / y)} tờ` : "Nhập tỷ lệ đạt > 0";
    }
    if (wasteGroup === "SETUP_WASTE") {
      let mk: number;
      if (method === "PER_COLOR_SIDE") mk = (Number(value) || 0) * colors * sides;
      else mk = (Number(setupQty) || 0) + (Number(setupPerColor) || 0) * colors + (Number(setupPerSide) || 0) * sides;
      return `Makeready = ${Math.round(clamp(mk))} tờ (với ${colors} màu, ${sides} mặt)`;
    }
    if (wasteGroup === "RUNNING_WASTE") {
      const w = Math.ceil(base * (Number(value) || 0));
      return `Running = clamp(ceil(${base} × ${((Number(value) || 0) * 100).toFixed(2)}%)) = ${Math.round(clamp(w))} tờ`;
    }
    if (wasteGroup === "PAPER_EXTRA_WASTE") {
      let p: number;
      if (method === "FIXED") p = Number(value) || 0;
      else if (method === "PER_REAM") p = (Number(value) || 0) * (base / 500);
      else p = Math.ceil(base * (Number(value) || 0));
      return `Hao giấy = ${Math.round(clamp(p))} tờ → cộng vào tờ mua`;
    }
    return "";
  }, [wasteGroup, method, value, setupQty, setupPerColor, setupPerSide, minWaste, maxWaste, pvColors, pvSides, pvBase]);

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

  return (
    <div className="md-page">
      <div className="md-page__head">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 className="md-page__title">Định mức & Bù hao</h1>
            <p className="md-page__sub">Khai tỷ lệ đạt, bù hao setup, chạy máy & hao giấy → engine tính số tờ sản xuất và mua giấy</p>
          </div>
          <Button variant="primary" onClick={handleCreateClick}>+ Thêm quy tắc định mức</Button>
        </div>
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      {/* Filters */}
      <div className="md-page__toolbar">
        <div className="md-page__filter" style={{ width: "220px" }}>
          <select className="input select" value={wasteGroupFilter} onChange={(e) => { setWasteGroupFilter(e.target.value); setPage(1); }} aria-label="Lọc nhóm định mức">
            <option value="">-- Tất cả nhóm --</option>
            {GROUPS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </div>
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
        <div className="md-page__toggle-wrap" style={{ padding: "0 var(--sp-2)" }}>
          <input type="checkbox" id="onlyCurrent" checked={onlyCurrent} onChange={(e) => { setOnlyCurrent(e.target.checked); setPage(1); }} />
          <label htmlFor="onlyCurrent">Chỉ xem bản hiện hành</label>
        </div>
      </div>

      {/* Table */}
      <div className="card md-page__tablewrap">
        {loading ? (
          <div style={{ padding: "40px", textAlign: "center" }}>Đang tải định mức...</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center" }} className="md-page__muted">Không tìm thấy định mức nào.</div>
        ) : (
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Tên</th>
                <th>Nhóm</th>
                <th>Công đoạn</th>
                <th>Cách tính</th>
                <th>Giá trị</th>
                <th>Áp dụng</th>
                <th>Ưu tiên</th>
                <th>Hiệu lực</th>
                <th>Trạng thái</th>
                <th style={{ width: "120px" }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const g = groupOf(row.waste_group);
                const op = operations.find((o) => o.id === row.operation_id);
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
                    <td className="md-page__muted" style={{ fontSize: "12px" }}>{row.calculation_method || "—"}</td>
                    <td className="md-page__price" style={{ fontSize: "15px" }}>{valueDisplay(row)}</td>
                    <td>{applyLabel === "Tất cả" ? <span className="md-page__muted">Tất cả</span> : <span className="md-page__tag-tech">{applyLabel}</span>}</td>
                    <td style={{ textAlign: "right" }}>{row.priority}</td>
                    <td style={{ fontSize: "12px" }}>{row.effective_from}{row.effective_to ? ` → ${row.effective_to}` : ""} {row.version > 1 && <span className="md-page__tag">v{row.version}</span>}</td>
                    <td>
                      <span className={`md-page__status-badge ${active ? "is-active" : "is-inactive"}`}>{active ? "Hữu hiệu" : "Hết hạn"}</span>
                    </td>
                    <td className="md-page__actions-col">
                      <button type="button" className="btn btn--secondary md-page__rowbtn" onClick={() => handleDuplicateFillClick(row)}>Sao chép</button>
                      <button type="button" className="btn btn--ghost md-page__rowbtn" onClick={() => openHistory(row)}>Lịch sử</button>
                      {active && <button type="button" className="btn btn--secondary md-page__rowbtn" onClick={() => handleCloseClick(row)}>Đóng</button>}
                      {row.effective_from > today && <button type="button" className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger" onClick={() => setDeleting(row)}>Xóa</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {total > PAGE_SIZE && (
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
              <h2>{editing ? "Sửa" : "Tạo"} quy tắc Định mức / Bù hao</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: "8px", padding: "0 var(--sp-4)", borderBottom: "1px solid var(--rule-soft)" }}>
              <button type="button" className={`btn ${dlgTab === "setup" ? "btn--primary" : "btn--ghost"}`} onClick={() => setDlgTab("setup")}>Thiết lập</button>
              <button type="button" className={`btn ${dlgTab === "test" ? "btn--primary" : "btn--ghost"}`} onClick={() => setDlgTab("test")}>Test nhanh</button>
            </div>

            {dlgTab === "setup" ? (
              <form className="md-page__dialog-body" onSubmit={handleSubmit}>
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
                    <label className="label">Mã định mức</label>
                    <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="VD: MR_PRINT_4C" />
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
                  </div>
                </div>

                {/* Khối 3 — Cách tính (đổi theo nhóm) */}
                <h3 className="md-page__section-title">③ Cách tính</h3>
                <div className="md-page__form-grid">
                  {(isYield || isRunning || isPaper) && (method !== "PER_COLOR_SIDE") && (
                    <div>
                      <label className="label">
                        {isYield ? "Tỷ lệ đạt (0–1, VD 0.97)" : isRunning ? "Tỷ lệ hao (0–1, VD 0.03)" : method === "FIXED" ? "Số tờ cố định" : method === "PER_REAM" ? "Số tờ / ram" : "Tỷ lệ hao giấy (0–1)"}
                      </label>
                      <input type="number" step="0.001" className="input" value={value} onChange={(e) => setValue(e.target.value)} placeholder={isYield ? "0.97" : "0.03"} />
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
                  {isYield && value !== "" && Number(value) > 0 && Number(value) < 0.8 && (
                    <div style={{ color: "var(--rust, #b45309)", fontSize: "12px", marginTop: "4px" }}>
                      ⚠ Tỷ lệ đạt {(Number(value) * 100).toFixed(0)}% khá thấp (&lt; 80%) — kiểm tra lại kẻo nhập nhầm.
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
              <h2>Đóng hiệu lực định mức</h2>
              <button type="button" className="md-page__close" onClick={() => setMode(null)}>×</button>
            </div>
            <div className="md-page__dialog-body">
              <p>Dừng hiệu lực quy tắc <strong>{selected.code || selected.name || selected.norm_key}</strong>.</p>
              <div>
                <label className="label">Ngày kết thúc (không gồm ngày này)</label>
                <input type="date" className="input" value={effectiveTo} onChange={(e) => setEffectiveTo(e.target.value)} required />
              </div>
              <div className="md-page__dialog-actions">
                <Button variant="secondary" type="button" onClick={() => setMode(null)}>Hủy</Button>
                <Button variant="danger" type="submit">Xác nhận đóng</Button>
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
                <thead><tr><th>Version</th><th>Giá trị</th><th>Áp dụng từ</th><th>Đến</th><th>Đã dùng</th></tr></thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td>v{h.version}</td>
                      <td className="md-page__price">{valueDisplay(h)}</td>
                      <td>{h.effective_from}</td>
                      <td>{h.effective_to || <span className="md-page__muted">Vô hạn</span>}</td>
                      <td style={{ textAlign: "right" }}>{h.used_count}</td>
                    </tr>
                  ))}
                  {history.length === 0 && <tr><td colSpan={5} className="md-page__muted" style={{ textAlign: "center" }}>Không có dữ liệu.</td></tr>}
                </tbody>
              </table>
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
