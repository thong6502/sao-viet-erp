import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type EstimateRow,
  type EstimateDetail,
  type EstimateInput,
  type EstimatePreviewOut,
  type EstimateStats,
  type MaterialRow,
  type MachineRow,
  type OperationCatalogRow,
  type ProductTypeCatalogRow,
  type ImpositionTypeRow,
  type PaperSizeRow,
  type NormRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import { DarkSummaryPanel } from "../components/DarkSummaryPanel";
import { ImpositionDiagram, computeImposition } from "../components/ImpositionDiagram";
import "./tinh-gia.css";

const PAGE_SIZE = 10;

interface OpForm {
  key: string;
  name: string;
  execution_mode: string;
  sequence: number;
}

interface CustomCostForm {
  category: "outsource" | "delivery" | "other";
  description: string;
  total_cost: number;
}

// --- Việt hóa dữ liệu kỹ thuật từ engine (mã đơn vị, key snapshot) ---

const UNIT_LABELS: Record<string, string> = {
  to: "tờ",
  ban: "bản",
  luot: "lượt",
  gio: "giờ",
  trang: "trang",
  click: "lượt click",
  m2: "m²",
  cuon: "cuốn",
  cai: "cái",
  san_pham: "sản phẩm",
  lo: "lô",
  ram: "ram",
  kg: "kg",
  lan: "lần",
  nghin_to: "1.000 tờ",
  nghin_cai: "1.000 cái",
  thung: "thùng",
  "to/gio": "tờ/giờ",
  "trang/phut": "trang/phút",
  "m2/gio": "m²/giờ",
};

function unitLabel(u: string | null | undefined): string {
  if (!u) return "—";
  return UNIT_LABELS[u] ?? u;
}

const SNAPSHOT_LABELS: Record<string, string> = {
  // Cấu hình áp dụng (source_snapshot)
  tooling_rate_code: "Mã bảng giá khuôn (#5)",
  tooling_pricing_method: "Cách tính khuôn",
  tooling_unit_price: "Đơn giá khuôn (nhập tay)",
  tooling_cost: "Tiền khuôn",
  material_id: "Vật liệu (ID)",
  code: "Mã vật liệu",
  name: "Tên vật liệu",
  unit: "Đơn vị bán",
  price_unit: "Đơn vị tính giá",
  unit_price: "Đơn giá",
  min_fee: "Phí tối thiểu",
  rate_id: "Bảng giá (ID)",
  setup_fee: "Phí chuẩn bị",
  min_charge: "Phí tối thiểu",
  hourly_rate: "Đơn giá giờ máy",
  norm_id: "Định mức (ID)",
  ink_cost_per_1000_impressions: "Đơn giá mực / 1.000 lượt-màu",
  run_rate: "Đơn giá gia công",
  labor_rate: "Đơn giá nhân công",
  // Các bước tính toán (calculation_snapshot)
  is_sheet: "Vật tư dạng tờ",
  total_sheets: "Tổng số tờ in (gồm bù hao)",
  sheet_w: "Khổ tờ — rộng (cm)",
  sheet_h: "Khổ tờ — cao (cm)",
  sides: "Số mặt in",
  min_fee_applied: "Đã áp phí tối thiểu",
  run_quantity: "Số lượt chạy",
  page_count: "Số trang",
  colors: "Số màu in",
  forms: "Số khuôn",
  impressions: "Tổng lượt-màu (tờ × màu × mặt)",
  speed: "Tốc độ máy",
  speed_unit: "Đơn vị tốc độ",
  run_qty: "Sản lượng chạy máy",
  run_time_hours: "Thời gian chạy máy",
  setup_hours: "Thời gian chuẩn bị máy",
  machine_hours: "Tổng giờ máy",
  qty_at_op: "Số lượng vào công đoạn",
  pieces_per_sheet: "Số con / tờ",
  run_cost: "Chi phí chạy",
  labor_cost: "Chi phí nhân công",
  // Bình bài (Lát 7) + số tờ 3 lớp (Lát 8)
  imposition: "Kiểu bình bài",
  finished_factor: "Hệ số thành phẩm",
  geometric_pieces_per_sheet: "Số con hình học / tờ",
  plate_set_factor: "Hệ số bộ kẽm",
  impo_pass_count: "Số lượt qua máy",
  ink_pass_factor: "Hệ số lượt in màu",
  theoretical_sheets: "Số tờ lý thuyết",
  sheets_after_yield: "Sau tỷ lệ đạt in",
  makeready_sheets: "Bù hao setup (makeready)",
  running_waste_sheets: "Bù hao chạy máy",
  production_sheets: "Số tờ sản xuất",
  paper_extra_sheets: "Hao giấy riêng",
  purchase_sheets: "Số tờ mua giấy",
  press_per_purchase: "Số tờ in / tờ giấy mua",
};

const MONEY_KEYS = new Set([
  "unit_price", "min_fee", "min_charge", "hourly_rate", "setup_fee",
  "run_rate", "labor_rate", "run_cost", "labor_cost", "ink_cost_per_1000_impressions",
]);
const HOUR_KEYS = new Set(["run_time_hours", "setup_hours", "machine_hours"]);
const ID_KEYS = new Set(["material_id", "rate_id", "norm_id"]);
const UNIT_VALUE_KEYS = new Set(["unit", "price_unit", "speed_unit"]);

// Nguồn đơn giá → tên trang cấu hình tương ứng (trả lời "con số này lấy từ đâu")
const SOURCE_TYPE_LABELS: Record<string, string> = {
  material_costs: "Bảng giá vật tư — trang Vật tư & Đơn giá vật tư",
  machine_rates: "Đơn giá giờ máy — trang Máy móc & Đơn giá giờ máy",
  plate_die_rates: "Trang Đơn giá kẽm & khuôn",
  click_ink_rates: "Trang Bảng giá Click (in kỹ thuật số)",
  operation_rates: "Đơn giá gia công — trang Công đoạn & Đơn giá gia công",
  norms: "Trang Định mức & Bù hao",
  input_spec: "Nhập tay trong phiếu tính giá này",
};

function formatHours(h: number): string {
  const mins = h * 60;
  const minsStr = mins.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
  if (mins < 60) return `${minsStr} phút`;
  return `${h.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} giờ (≈ ${minsStr} phút)`;
}

function snapshotLabel(key: string): string {
  return SNAPSHOT_LABELS[key] ?? key;
}

function snapshotValue(key: string, val: unknown): string {
  if (val === null || val === undefined || val === "") return "—";
  if (typeof val === "boolean") return val ? "Có" : "Không";
  if (typeof val === "number") {
    if (MONEY_KEYS.has(key)) return `${val.toLocaleString("vi-VN")} đ`;
    if (HOUR_KEYS.has(key)) return formatHours(val);
    if (ID_KEYS.has(key)) return `#${val}`;
    return val.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  }
  if (typeof val === "string") {
    if (UNIT_VALUE_KEYS.has(key)) return unitLabel(val);
    return val;
  }
  return JSON.stringify(val);
}

export function TinhGiaPage({
  navigate,
  openEstimateId = null,
}: {
  navigate?: (id: string, params?: any) => void;
  openEstimateId?: number | null;
}) {
  const { token, user } = useAuth();

  // List States
  const [rows, setRows] = useState<EstimateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [q, setQ] = useState("");
  // "" = tất cả | "draft" | "calculated" | "blocking" (tab lọc)
  const [statusFilter, setStatusFilter] = useState("");
  const [productTypeFilter, setProductTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [stats, setStats] = useState<EstimateStats | null>(null);

  // Catalogs
  const [productTypes, setProductTypes] = useState<ProductTypeCatalogRow[]>([]);
  const [materials, setMaterials] = useState<MaterialRow[]>([]);
  const [machines, setMachines] = useState<MachineRow[]>([]);
  const [impositionTypes, setImpositionTypes] = useState<ImpositionTypeRow[]>([]);
  const [operationsCatalog, setOperationsCatalog] = useState<OperationCatalogRow[]>([]);

  // View Mode: null = List, "create" = Form Create, "edit" = Form Edit
  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const isEdit = mode === "edit";
  const [editing, setEditing] = useState<EstimateDetail | null>(null);
  const [deleting, setDeleting] = useState<EstimateRow | null>(null);
  
  // Form active tab: "spec" = Spec form fields, "result" = Breakdown results
  const [activeFormTab, setActiveFormTab] = useState<"spec" | "result">("spec");
  // Result view active quantity tab index
  const [activeQtyTab, setActiveQtyTab] = useState(0);
  // Audit drawer state: null if closed, contains cost line detail if open
  const [auditLineId, setAuditLineId] = useState<number | null>(null);
  // Anchor để nút "Xem phân rã" cuộn xuống bảng phân rã (phản hồi thấy được kể cả khi chỉ có 1 mức SL)
  const breakdownRef = useRef<HTMLDivElement | null>(null);

  // Form Fields States
  const [productName, setProductName] = useState("");
  const [productType, setProductType] = useState("brochure");
  const [quantityList, setQuantityList] = useState<number[]>([]);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("draft");

  // Specs
  const [finishedWidth, setFinishedWidth] = useState("");
  const [finishedHeight, setFinishedHeight] = useState("");
  const [colors, setColors] = useState(4);
  const [sides, setSides] = useState(2);
  // Kiểu bình bài (mã, vd TU_TRO). Rỗng = engine tự suy theo số mặt (hành vi cũ).
  const [imposition, setImposition] = useState("");
  // §12 — Sửa tay tổng tiền từng dòng, mỗi mục kèm lý do bắt buộc. Đi trong input_spec.overrides.
  const [overrides, setOverrides] = useState<Array<{ target: string; value: number; reason: string }>>([]);
  // §12 nâng cao — override số tờ SX + đơn giá vật tư (đi riêng trong input_spec).
  const [ovProdSheets, setOvProdSheets] = useState<{ value: string; reason: string }>({ value: "", reason: "" });
  const [ovMatPrice, setOvMatPrice] = useState<{ value: string; reason: string }>({ value: "", reason: "" });
  const [pageCount, setPageCount] = useState("");
  const [forms, setForms] = useState(1);
  const [bindingType, setBindingType] = useState("");
  const [boxLength, setBoxLength] = useState("");
  const [boxWidth, setBoxWidth] = useState("");
  const [boxHeight, setBoxHeight] = useState("");
  const [paperThickness, setPaperThickness] = useState("");
  const [shape, setShape] = useState("");
  const [dieCutRequired, setDieCutRequired] = useState(false);
  const [gluingRequired, setGluingRequired] = useState(false);
  const [largeWidth, setLargeWidth] = useState("");
  const [largeHeight, setLargeHeight] = useState("");
  const [edgeFinishing, setEdgeFinishing] = useState("");
  const [eyeletRequired, setEyeletRequired] = useState(false);

  // Material & Layout spec
  const [materialId, setMaterialId] = useState<number | null>(null);
  const [overridePieces, setOverridePieces] = useState(false);
  const [piecesPerSheet, setPiecesPerSheet] = useState("");
  const [grainLocked, setGrainLocked] = useState(false);
  // #4 — tham số bình bản (cm, tùy chọn) tinh chỉnh gợi ý số con/khổ (nhíp/xén/bleed/gutter)
  const [gripperCm, setGripperCm] = useState("");
  const [edgeTrimCm, setEdgeTrimCm] = useState("");
  const [bleedCm, setBleedCm] = useState("");
  const [gutterCm, setGutterCm] = useState("");
  // Khổ tờ in chọn từ DM Khổ giấy tiêu chuẩn (ghi đè khổ tờ từ vật tư khi được chọn).
  const [paperSizes, setPaperSizes] = useState<PaperSizeRow[]>([]);
  const [printSizeId, setPrintSizeId] = useState<number | null>(null);

  // Machine
  const [machineId, setMachineId] = useState<number | null>(null);

  // Chosen operations
  const [operations, setOperations] = useState<OpForm[]>([]);
  // Custom charges
  const [customCosts, setCustomCosts] = useState<CustomCostForm[]>([]);

  // Suggest geometric pieces
  const [suggestedPieces, setSuggestedPieces] = useState<number | null>(null);

  // Live preview giá vốn (không lưu): engine chạy với spec đang gõ, debounce 700ms.
  const [preview, setPreview] = useState<EstimatePreviewOut | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [saving, setSaving] = useState(false);
  const [qtyError, setQtyError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Load List
  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    
    let sort_mapped = sort;
    if (sort === "code") sort_mapped = "estimate_number";
    else if (sort === "-code") sort_mapped = "-estimate_number";

    // Tab "blocking" không phải trạng thái — lọc bằng has_blocking
    const status_query =
      statusFilter === "ready" ? "calculated" : statusFilter === "blocking" ? "" : statusFilter;

    api.estimates
      .list(token, {
        q: q.trim() || undefined,
        product_type: productTypeFilter || undefined,
        status: status_query || null,
        has_blocking: statusFilter === "blocking" || undefined,
        sort: sort_mapped,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        setListError("Không tải được danh sách phương án tính giá hoặc bạn không có quyền truy cập.");
      })
      .finally(() => setLoading(false));

    // Số đếm tab — endpoint mới, backend cũ chưa có: fail thì tab không hiện số
    api.estimates.stats(token).then(setStats).catch(() => setStats(null));
  }, [token, q, statusFilter, productTypeFilter, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

  // Load Catalogs on mount
  useEffect(() => {
    if (!token) return;

    api.productTypesCatalog.list(token, { page: 1, size: 100 })
      .then(res => setProductTypes(res.items))
      .catch(() => setProductTypes([]));

    api.materials.list(token, { page: 1, size: 200 })
      .then(res => setMaterials(res.items))
      .catch(() => setMaterials([]));

    api.machines.list(token, { page: 1, size: 200 })
      .then(res => setMachines(res.items))
      .catch(() => setMachines([]));
    // Khổ tờ in tiêu chuẩn đang hiệu lực (chỉ khổ tờ in) để chọn ở section Vật liệu.
    api.paperSizes.list(token, { current_only: true, is_active: true, size: 200 })
      .then(res => setPaperSizes(res.items.filter(s => s.is_print_sheet_size)))
      .catch(() => setPaperSizes([]));
    // Kiểu bình bài đang hiệu lực (mỗi mã 1 phiên bản hiện hành) để chọn ở section In ấn.
    api.impositionTypes.list(token, { current_only: true, is_active: true, sort: "priority", size: 200 })
      .then(res => setImpositionTypes(res.items))
      .catch(() => setImpositionTypes([]));

    api.operations.list(token, { page: 1, size: 200 })
      .then(res => setOperationsCatalog(res.items))
      .catch(() => setOperationsCatalog([]));
  }, [token]);

  // Fetch geometric suggestions
  useEffect(() => {
    if (!token || materialId === null || overridePieces) {
      setSuggestedPieces(null);
      return;
    }
    const mat = materials.find(m => m.id === materialId);
    if (!mat || !mat.width_cm || !mat.height_cm) {
      setSuggestedPieces(null);
      return;
    }
    
    // Resolve piece dimensions depending on product type
    let pw = 0, ph = 0;
    if (productType === "box" || productType === "packaging") {
      pw = Number(boxLength) || 0;
      ph = Number(boxWidth) || 0;
    } else if (productType === "banner" || productType === "large_format") {
      pw = Number(largeWidth) || 0;
      ph = Number(largeHeight) || 0;
    } else {
      pw = Number(finishedWidth) || 0;
      ph = Number(finishedHeight) || 0;
    }

    if (pw <= 0 || ph <= 0) {
      setSuggestedPieces(null);
      return;
    }

    let cancelled = false;
    const psz = paperSizes.find(s => s.id === printSizeId);
    api.costings.suggestPieces(token, {
      sheet_w: psz?.width_cm ?? mat.width_cm,
      sheet_h: psz?.height_cm ?? mat.height_cm,
      piece_w: pw,
      piece_h: ph,
      grain_locked: grainLocked,
      gripper_cm: Number(gripperCm) || 0,
      edge_trim_cm: Number(edgeTrimCm) || 0,
      bleed_cm: Number(bleedCm) || 0,
      gutter_cm: Number(gutterCm) || 0,
    })
    .then((res) => {
      if (!cancelled) setSuggestedPieces(res.pieces);
    })
    .catch(() => {
      if (!cancelled) setSuggestedPieces(null);
    });

    return () => {
      cancelled = true;
    };
  }, [token, materialId, printSizeId, paperSizes, finishedWidth, finishedHeight, boxLength, boxWidth, largeWidth, largeHeight, grainLocked, gripperCm, edgeTrimCm, bleedCm, gutterCm, productType, overridePieces, materials]);

  // Live preview giá vốn: gọi engine (không lưu) khi đã đủ giấy + máy + số lượng — debounce
  // 700ms để không dội API theo từng phím. Kết quả hiện ở sidebar (mức SL đầu tiên).
  useEffect(() => {
    if (mode === null) return;
    if (!token || materialId === null || machineId === null || quantityList.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    const timer = setTimeout(() => {
      const mat = materials.find((m) => m.id === materialId);
      const psz = paperSizes.find((s) => s.id === printSizeId);
      const input_spec: Record<string, unknown> = {
        product_type: productType,
        finished_width: finishedWidth ? Number(finishedWidth) : null,
        finished_height: finishedHeight ? Number(finishedHeight) : null,
        colors: Number(colors),
        sides: Number(sides),
        imposition: imposition || null,
        overrides,
        override_production_sheets: ovProdSheets.value ? { value: Number(ovProdSheets.value), reason: ovProdSheets.reason } : null,
        override_material_unit_price: ovMatPrice.value ? { value: Number(ovMatPrice.value), reason: ovMatPrice.reason } : null,
        page_count: pageCount ? Number(pageCount) : null,
        forms: Number(forms),
        box_length: boxLength ? Number(boxLength) : null,
        box_width: boxWidth ? Number(boxWidth) : null,
        box_height: boxHeight ? Number(boxHeight) : null,
        width: largeWidth ? Number(largeWidth) : null,
        height: largeHeight ? Number(largeHeight) : null,
        material_id: materialId,
        print_sheet_size_id: printSizeId,
        sheet_w: psz?.width_cm ?? (mat?.width_cm || 0),
        sheet_h: psz?.height_cm ?? (mat?.height_cm || 0),
        grain_locked: grainLocked,
        gripper_cm: Number(gripperCm) || 0,
        edge_trim_cm: Number(edgeTrimCm) || 0,
        bleed_cm: Number(bleedCm) || 0,
        gutter_cm: Number(gutterCm) || 0,
        machine_id: machineId,
        operations: operations.map((o) => ({
          operation_key: o.name.trim(),
          sequence: o.sequence,
          execution_mode: o.execution_mode,
        })),
      };
      if (overridePieces && Number(piecesPerSheet) > 0) {
        input_spec.pieces_per_sheet = Number(piecesPerSheet);
      }
      api.estimates
        .preview(token, { input_spec, quantity: quantityList[0] })
        .then((res) => {
          if (!cancelled) setPreview(res);
        })
        .catch(() => {
          if (!cancelled) setPreview(null);
        })
        .finally(() => {
          if (!cancelled) setPreviewLoading(false);
        });
    }, 700);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, mode, materialId, printSizeId, paperSizes, machineId, quantityList, colors, sides, imposition, overrides, ovProdSheets, ovMatPrice, pageCount, forms, overridePieces, piecesPerSheet, grainLocked, gripperCm, edgeTrimCm, bleedCm, gutterCm, operations, productType, finishedWidth, finishedHeight, boxLength, boxWidth, boxHeight, largeWidth, largeHeight]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  // Open Form for Create
  function openCreate() {
    setEditing(null);
    setProductName("");
    setProductType("brochure");
    setQuantityList([1000]);
    setNote("");
    setStatus("draft");
    
    // Clear specs
    setFinishedWidth("");
    setFinishedHeight("");
    setColors(4);
    setSides(2);
    setImposition("");
    setOverrides([]);
    setOvProdSheets({ value: "", reason: "" });
    setOvMatPrice({ value: "", reason: "" });
    setPageCount("");
    setForms(1);
    setBindingType("");
    setBoxLength("");
    setBoxWidth("");
    setBoxHeight("");
    setPaperThickness("");
    setShape("");
    setDieCutRequired(false);
    setGluingRequired(false);
    setLargeWidth("");
    setLargeHeight("");
    setEdgeFinishing("");
    setEyeletRequired(false);

    setMaterialId(null);
    setOverridePieces(false);
    setPiecesPerSheet("");
    setGrainLocked(false);
    setGripperCm("");
    setEdgeTrimCm("");
    setBleedCm("");
    setGutterCm("");
    setMachineId(null);
    setOperations([]);
    setCustomCosts([]);
    
    setFormError(null);
    setQtyError(null);
    setActiveFormTab("spec");
    setMode("create");
  }

  // Open Form for Edit
  async function openEdit(row: EstimateRow) {
    if (!token) return;
    try {
      setLoading(true);
      const detail = await api.estimates.get(token, row.id);
      setEditing(detail);
      
      const spec = detail.input_spec_json || {};
      setProductName(detail.product_name);
      setProductType(detail.product_type);
      setQuantityList(detail.quantity_list_json);
      setNote(spec.note || "");
      setStatus(detail.status);

      // Map dynamic specs
      setFinishedWidth(spec.finished_width || spec.finished_w || "");
      setFinishedHeight(spec.finished_height || spec.finished_h || "");
      setColors(spec.colors || 4);
      setSides(spec.sides || 2);
      setImposition(spec.imposition || "");
      setOverrides(Array.isArray(spec.overrides) ? spec.overrides : []);
      setOvProdSheets(spec.override_production_sheets ? { value: String(spec.override_production_sheets.value ?? ""), reason: spec.override_production_sheets.reason ?? "" } : { value: "", reason: "" });
      setOvMatPrice(spec.override_material_unit_price ? { value: String(spec.override_material_unit_price.value ?? ""), reason: spec.override_material_unit_price.reason ?? "" } : { value: "", reason: "" });
      setPageCount(spec.page_count || "");
      setForms(spec.forms || 1);
      setBindingType(spec.binding_type || "");
      setBoxLength(spec.box_length || "");
      setBoxWidth(spec.box_width || "");
      setBoxHeight(spec.box_height || "");
      setPaperThickness(spec.paper_thickness || "");
      setShape(spec.shape || "");
      setDieCutRequired(!!spec.die_cut_required);
      setGluingRequired(!!spec.gluing_required);
      setLargeWidth(spec.width || "");
      setLargeHeight(spec.height || "");
      setEdgeFinishing(spec.edge_finishing || "");
      setEyeletRequired(!!spec.eyelet_required);

      setMaterialId(spec.material_id || null);
      setPrintSizeId(spec.print_sheet_size_id || null);
      setOverridePieces(!!spec.override_pieces);
      setPiecesPerSheet(spec.pieces_per_sheet || "");
      setGrainLocked(!!spec.grain_locked);
      setGripperCm(spec.gripper_cm || "");
      setEdgeTrimCm(spec.edge_trim_cm || "");
      setBleedCm(spec.bleed_cm || "");
      setGutterCm(spec.gutter_cm || "");

      setMachineId(spec.machine_id || null);
      
      // Operations mapping
      if (spec.operations) {
        setOperations(spec.operations.map((o: any, idx: number) => ({
          key: `op-${idx}-${Date.now()}`,
          name: o.operation_key || o.name || "",
          execution_mode: o.execution_mode || "internal",
          sequence: o.sequence || (idx + 1) * 10
        })));
      } else {
        setOperations([]);
      }

      // Custom costs mapping
      setCustomCosts(spec.custom_costs || []);

      setFormError(null);
      setQtyError(null);
      
      // If calculated, display result tab by default
      setActiveFormTab(detail.status === "calculated" ? "result" : "spec");
      setActiveQtyTab(0);
      setAuditLineId(null);
      setMode("edit");
    } catch {
      setListError("Không tải được chi tiết phương án.");
    } finally {
      setLoading(false);
    }
  }

  // Mở sẵn 1 phiếu khi điều hướng từ Báo giá ("Xem phiếu tính giá" / ↳ mã phiếu).
  const openedFromNavRef = useRef(false);
  useEffect(() => {
    if (!token || !openEstimateId || openedFromNavRef.current) return;
    openedFromNavRef.current = true;
    openEdit({ id: openEstimateId } as EstimateRow);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, openEstimateId]);

  function handleCloseForm() {
    setMode(null);
    setEditing(null);
    load();
  }

  // Delete Estimate
  async function confirmDelete() {
    if (!token || !deleting) return;
    const target = deleting;
    try {
      await api.estimates.remove(token, target.id);
      setDeleting(null);
      if (rows.length === 1 && page > 1) setPage((p) => p - 1);
      else load();
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden)
        setListError("Bạn không có quyền xoá phương án.");
      else setListError("Xoá không thành công. Vui lòng thử lại.");
      setDeleting(null);
    }
  }

  // Form Field helpers
  const handleProductTypeChange = (newType: string) => {
    if (productType !== newType) {
      if (productName || materialId || operations.length > 0) {
        if (!confirm("Thay đổi loại sản phẩm có thể làm mất một số thông số đã nhập. Bạn có muốn tiếp tục?")) {
          return;
        }
      }
      setProductType(newType);
      
      // Clean type-specific fields
      setFinishedWidth("");
      setFinishedHeight("");
      setPageCount("");
      setForms(1);
      setBindingType("");
      setBoxLength("");
      setBoxWidth("");
      setBoxHeight("");
      setPaperThickness("");
      setShape("");
      setDieCutRequired(false);
      setGluingRequired(false);
      setLargeWidth("");
      setLargeHeight("");
      setEdgeFinishing("");
      setEyeletRequired(false);
      
      // Clear machine since catalog rules change
      setMachineId(null);

      // Áp template loại SP (danh mục #1 — Loại sản phẩm & Quy tắc tính): bleed/gutter/lề xén
      // mặc định (mm→cm), bình bài mặc định, và auto-nạp routing công đoạn từ default_operations.
      const cfg = productTypes.find((p) => p.product_type === newType);
      if (cfg) {
        const mm2cm = (mm?: number | null) => (mm && mm > 0 ? String(Number((mm / 10).toFixed(2))) : "");
        setBleedCm(mm2cm(cfg.default_bleed_mm));
        setGutterCm(mm2cm(cfg.default_gutter_mm));
        setEdgeTrimCm(mm2cm(cfg.default_trim_mm));
        setImposition(cfg.default_imposition_code || "");
        const routed = (cfg.default_operations || [])
          .map((t) => operationsCatalog.find((o) => o.operation_type === t))
          .filter((o): o is OperationCatalogRow => !!o)
          .map((o, idx) => ({
            key: `op-tpl-${o.id}-${idx}`,
            name: o.name,
            execution_mode: (o.allow_outsource ? "outsource" : "internal") as "outsource" | "internal",
            sequence: (idx + 1) * 10,
          }));
        setOperations(routed);
      } else {
        setImposition("");
    setOverrides([]);
    setOvProdSheets({ value: "", reason: "" });
    setOvMatPrice({ value: "", reason: "" });
        setOperations([]);
      }
    }
  };

  // Move Operation up/down in sequence list
  const moveOp = (index: number, direction: "up" | "down") => {
    const nextOps = [...operations];
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    const temp = nextOps[index];
    nextOps[index] = nextOps[targetIndex];
    nextOps[targetIndex] = temp;
    
    // Re-assign sequences in steps of 10
    const updated = nextOps.map((op, idx) => ({
      ...op,
      sequence: (idx + 1) * 10
    }));
    setOperations(updated);
  };

  // Add Operation
  const addOp = (name: string) => {
    if (!name) return;
    const opCat = operationsCatalog.find(o => o.name === name);
    const execution_mode = opCat?.allow_outsource ? "outsource" : "internal";
    const nextSeq = (operations.length + 1) * 10;
    
    setOperations([...operations, {
      key: `op-new-${Date.now()}`,
      name,
      execution_mode,
      sequence: nextSeq
    }]);
  };

  const removeOp = (key: string) => {
    const remaining = operations.filter(o => o.key !== key);
    // Re-sequence
    const updated = remaining.map((op, idx) => ({
      ...op,
      sequence: (idx + 1) * 10
    }));
    setOperations(updated);
  };

  // Phí phát sinh
  const addCustomCost = () => {
    setCustomCosts([...customCosts, { category: "outsource", description: "", total_cost: 0 }]);
  };

  const updateCustomCost = (index: number, patch: Partial<CustomCostForm>) => {
    setCustomCosts(customCosts.map((c, idx) => idx === index ? { ...c, ...patch } : c));
  };

  const removeCustomCost = (index: number) => {
    setCustomCosts(customCosts.filter((_, idx) => idx !== index));
  };

  // Submit / Calculate flow
  function validateForm(): string | null {
    if (!productName.trim()) return "Tên sản phẩm là bắt buộc.";
    if (quantityList.length === 0) return "Cần ít nhất một mức số lượng để tính giá.";
    
    // Verify dimensions based on product type
    if (productType === "box" || productType === "packaging") {
      if (!boxLength || !boxWidth || !boxHeight) return "Các thông số kích thước dài/rộng/cao hộp là bắt buộc.";
    } else if (productType === "banner" || productType === "large_format") {
      if (!largeWidth || !largeHeight) return "Các kích thước rộng/cao banner là bắt buộc.";
    } else {
      if (!finishedWidth || !finishedHeight) return "Các kích thước rộng/cao thành phẩm là bắt buộc.";
    }

    if (materialId === null) return "Vui lòng chọn vật liệu chính.";
    if (machineId === null) return "Vui lòng chọn máy in dự kiến.";
    
    // If pieces_per_sheet is overriden, must be positive int
    if (overridePieces) {
      const pCount = Number(piecesPerSheet);
      if (!Number.isInteger(pCount) || pCount <= 0) {
        return "Số con trên khổ (pieces_per_sheet) nhập tay phải là số nguyên dương.";
      }
    }

    for (let i = 0; i < customCosts.length; i++) {
      if (!customCosts[i].description.trim()) return `Phí phát sinh ${i + 1}: mô tả không được để trống.`;
      if (customCosts[i].total_cost < 0) return `Phí phát sinh ${i + 1}: thành tiền không được nhỏ hơn 0.`;
    }

    return null;
  }

  // §9 — Khóa snapshot phiếu đang xem.
  async function handleLockSnapshot() {
    if (!token || !editing) return;
    try {
      const upd = await api.estimates.lock(token, editing.id);
      setEditing(upd);
      setFormError(null);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Không khóa được phiếu.");
    }
  }
  // §7/§9 — Sao chép phiếu (mở luôn bản mới để chỉnh).
  async function handleDuplicate() {
    if (!token || !editing) return;
    try {
      const dup = await api.estimates.duplicate(token, editing.id);
      await openEdit({ id: dup.id } as EstimateRow);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Không sao chép được phiếu.");
    }
  }
  // §7 — Xuất CSV (mở được bằng Excel). PDF: dùng In trình duyệt.
  function handleExportCsv() {
    if (!editing) return;
    const opt = editing.options?.[0];
    const rows: string[][] = [["Loại", "Diễn giải", "Số lượng", "ĐVT", "Đơn giá", "Thành tiền"]];
    for (const l of opt?.cost_lines ?? []) {
      rows.push([l.category, String(l.description ?? "").replace(/"/g, "'"), String(l.quantity), l.unit, String(l.unit_cost), String(l.total_cost)]);
    }
    rows.push(["", "", "", "", "GIÁ THÀNH TRỰC TIẾP", String(opt?.total_cost ?? 0)]);
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${editing.estimate_number}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleSave(submitStatus: "draft" | "calculated") {
    if (!token || saving) return;
    setFormError(null);
    setQtyError(null);

    const problem = validateForm();
    if (problem) {
      setFormError(problem);
      return;
    }

    // Resolve pieces_per_sheet
    let finalPieces = suggestedPieces;
    if (overridePieces) {
      finalPieces = Number(piecesPerSheet);
    } else if (finalPieces === null) {
      // default fallback
      finalPieces = 1;
    }

    // Build spec
    const mat = materials.find(m => m.id === materialId);
    const chosenPrintSize = paperSizes.find(s => s.id === printSizeId);
    const input_spec = {
      product_id: null,
      finished_width: finishedWidth ? Number(finishedWidth) : null,
      finished_height: finishedHeight ? Number(finishedHeight) : null,
      colors: Number(colors),
      sides: Number(sides),
      imposition: imposition || null,
      overrides,
      override_production_sheets: ovProdSheets.value ? { value: Number(ovProdSheets.value), reason: ovProdSheets.reason } : null,
      override_material_unit_price: ovMatPrice.value ? { value: Number(ovMatPrice.value), reason: ovMatPrice.reason } : null,
      page_count: pageCount ? Number(pageCount) : null,
      forms: Number(forms),
      binding_type: bindingType || null,
      box_length: boxLength ? Number(boxLength) : null,
      box_width: boxWidth ? Number(boxWidth) : null,
      box_height: boxHeight ? Number(boxHeight) : null,
      paper_thickness: paperThickness ? Number(paperThickness) : null,
      shape: shape || null,
      die_cut_required: dieCutRequired,
      gluing_required: gluingRequired,
      width: largeWidth ? Number(largeWidth) : null,
      height: largeHeight ? Number(largeHeight) : null,
      edge_finishing: edgeFinishing || null,
      eyelet_required: eyeletRequired,

      material_id: materialId,
      print_sheet_size_id: printSizeId,
      override_pieces: overridePieces,
      pieces_per_sheet: finalPieces,
      sheet_w: chosenPrintSize?.width_cm ?? (mat?.width_cm || 0),
      sheet_h: chosenPrintSize?.height_cm ?? (mat?.height_cm || 0),
      grain_locked: grainLocked,
      gripper_cm: Number(gripperCm) || 0,
      edge_trim_cm: Number(edgeTrimCm) || 0,
      bleed_cm: Number(bleedCm) || 0,
      gutter_cm: Number(gutterCm) || 0,

      machine_id: machineId,
      operations: operations.map((o) => ({
        operation_key: o.name.trim(),
        sequence: o.sequence,
        execution_mode: o.execution_mode,
      })),
      custom_costs: customCosts.map(c => ({
        category: c.category,
        description: c.description.trim(),
        total_cost: Number(c.total_cost)
      })),
      note: note.trim() || null,
    };

    const input: EstimateInput = {
      product_type: productType,
      product_name: productName.trim(),
      quantity_list: quantityList,
      input_spec,
      customer_id: null, // Tính giá là giá vốn nội bộ — không gắn khách hàng (KH ở Báo giá)
      status: submitStatus,
    };

    setSaving(true);
    try {
      let savedDetail: EstimateDetail;
      if (mode === "edit" && editing) {
        savedDetail = await api.estimates.update(token, editing.id, input);
      } else {
        savedDetail = await api.estimates.create(token, input);
      }
      
      setEditing(savedDetail);
      setMode("edit");
      setStatus(savedDetail.status);
      
      // If we calculate price, automatically switch to result breakdown tab
      if (submitStatus === "calculated") {
        setActiveFormTab("result");
        setActiveQtyTab(0);
      } else {
        alert("Đã lưu nháp phương án thành công!");
      }
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden) {
        setFormError("Bạn không có quyền thực hiện thao tác này.");
      } else if (err instanceof ApiError && err.status === 422) {
        setFormError(err.message);
      } else {
        setFormError("Lưu thất bại. Vui lòng kiểm tra lại cấu hình hoặc dữ liệu master data.");
      }
    } finally {
      setSaving(false);
    }
  }

  // Cost Category utilities
  function getCostCategoryLabel(cat: string): string {
    switch (cat) {
      case "material": return "Vật liệu";
      case "click_ink": return "Click / Mực";
      case "ink": return "Mực in";
      case "plate_die": return "Bản / Khuôn";
      case "machine": return "Chạy máy";
      case "operation": return "Gia công";
      case "packing": return "Đóng gói";
      case "delivery": return "Giao hàng";
      case "outsource": return "Thuê ngoài";
      default: return "Khác";
    }
  }

  function getCostCategoryClassName(cat: string): string {
    return `tg__row-cat-${cat}`;
  }

  function renderProductSpecFields() {
    // Danh mục #1 — shown_fields của loại SP điều khiển field nào hiện trên màn Tính giá.
    // Không khai (rỗng/null) ⇒ hiện đủ như cũ (an toàn ngược).
    const ptCfg = productTypes.find((p) => p.product_type === productType);
    const showField = (key: string) => !ptCfg?.shown_fields?.length || ptCfg.shown_fields.includes(key);
    switch (productType) {
      case "brochure":
      case "namecard":
      case "leaflet":
        return (
          <div className="tg__form-grid">
            <label className="field">
              <span className="field__label">Rộng thành phẩm (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedWidth} onChange={e => setFinishedWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Cao thành phẩm (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedHeight} onChange={e => setFinishedHeight(e.target.value)} />
            </label>
            {showField("sides") && (
            <label className="field">
              <span className="field__label">Số mặt in *</span>
              <select className="input" value={sides} onChange={e => setSides(Number(e.target.value))}>
                <option value={1}>In 1 mặt (4/0 hoặc 1/0)</option>
                <option value={2}>In 2 mặt (4/4 hoặc 1/1)</option>
              </select>
            </label>
            )}
            {showField("colors") && (
            <label className="field">
              <span className="field__label">Số màu in *</span>
              <input className="input" type="number" min="1" max="10" value={colors} onChange={e => setColors(Number(e.target.value))} />
            </label>
            )}
          </div>
        );
      case "catalogue":
      case "book":
      case "magazine":
        return (
          <div className="tg__form-grid">
            <label className="field">
              <span className="field__label">Rộng thành phẩm (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedWidth} onChange={e => setFinishedWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Cao thành phẩm (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedHeight} onChange={e => setFinishedHeight(e.target.value)} />
            </label>
            {showField("page_count") && (
            <label className="field">
              <span className="field__label">Tổng số trang (ruột + bìa) *</span>
              <input className="input" type="number" min="4" step="4" value={pageCount} onChange={e => setPageCount(e.target.value)} />
              <span className="tg__suggest">Phải là số chia hết cho 4 (tay sách).</span>
            </label>
            )}
            <label className="field">
              <span className="field__label">Số form in (bản kẽm ruột+bìa) *</span>
              <input className="input" type="number" min="1" value={forms} onChange={e => setForms(Number(e.target.value))} />
            </label>
            <label className="field">
              <span className="field__label">Kiểu đóng gáy</span>
              <select className="input" value={bindingType} onChange={e => setBindingType(e.target.value)}>
                <option value="">Chọn kiểu gáy...</option>
                <option value="khau_chi">Khâu chỉ + Keo nhiệt</option>
                <option value="keo_nhiet">Phay gáy keo nhiệt</option>
                <option value="dong_kim">Đóng kim giữa</option>
                <option value="lo_xo">Đóng gáy lò xo</option>
              </select>
            </label>
            {showField("colors") && (
            <label className="field">
              <span className="field__label">Số màu in *</span>
              <input className="input" type="number" min="1" max="10" value={colors} onChange={e => setColors(Number(e.target.value))} />
            </label>
            )}
          </div>
        );
      case "sticker":
      case "label":
        return (
          <div className="tg__form-grid">
            <label className="field">
              <span className="field__label">Rộng sticker (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedWidth} onChange={e => setFinishedWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Cao sticker (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedHeight} onChange={e => setFinishedHeight(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Hình dạng bế</span>
              <select className="input" value={shape} onChange={e => setShape(e.target.value)}>
                <option value="">Chọn hình dạng...</option>
                <option value="tron">Hình tròn</option>
                <option value="oval">Hình Oval</option>
                <option value="chu_nhat">Chữ nhật vuông góc</option>
                <option value="bo_goc">Chữ nhật bo góc</option>
                <option value="phuc_tap">Đường bế phức tạp</option>
              </select>
            </label>
            <div className="field tg__check" style={{ marginTop: "24px" }}>
              <input type="checkbox" checked={dieCutRequired} onChange={e => setDieCutRequired(e.target.checked)} />
              <span>Có bế demi / bế đứt tạo hình (Die cut)</span>
            </div>
          </div>
        );
      case "box":
      case "packaging":
        return (
          <div className="tg__form-grid">
            <label className="field">
              <span className="field__label">Chiều dài hộp (cm) *</span>
              <input className="input" type="number" step="0.1" value={boxLength} onChange={e => setBoxLength(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Chiều rộng hộp (cm) *</span>
              <input className="input" type="number" step="0.1" value={boxWidth} onChange={e => setBoxWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Chiều cao hộp (cm) *</span>
              <input className="input" type="number" step="0.1" value={boxHeight} onChange={e => setBoxHeight(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Độ dày hộp (mm)</span>
              <input className="input" type="number" step="0.05" value={paperThickness} onChange={e => setPaperThickness(e.target.value)} />
            </label>
            <div className="field tg__check" style={{ marginTop: "24px" }}>
              <input type="checkbox" checked={dieCutRequired} onChange={e => setDieCutRequired(e.target.checked)} />
              <span>Yêu cầu bế khuôn tạo hình</span>
            </div>
            <div className="field tg__check" style={{ marginTop: "24px" }}>
              <input type="checkbox" checked={gluingRequired} onChange={e => setGluingRequired(e.target.checked)} />
              <span>Yêu cầu dán keo tai cạnh hộp</span>
            </div>
          </div>
        );
      case "banner":
      case "large_format":
        const calculatedArea = Number(largeWidth) > 0 && Number(largeHeight) > 0 ? (Number(largeWidth) * Number(largeHeight) / 10000) : 0;
        return (
          <div className="tg__form-grid">
            <label className="field">
              <span className="field__label">Chiều rộng banner (cm) *</span>
              <input className="input" type="number" step="1" value={largeWidth} onChange={e => setLargeWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Chiều cao banner (cm) *</span>
              <input className="input" type="number" step="1" value={largeHeight} onChange={e => setLargeHeight(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Diện tích tính toán (m²)</span>
              <input className="input" value={calculatedArea.toFixed(2)} readOnly disabled />
            </label>
            <label className="field">
              <span className="field__label">Gia công mép</span>
              <select className="input" value={edgeFinishing} onChange={e => setEdgeFinishing(e.target.value)}>
                <option value="">Chọn gia công mép...</option>
                <option value="gap_mep">Gấp mép dán keo</option>
                <option value="xo_cay">Xỏ cây trên dưới</option>
                <option value="de_nguyen">Để nguyên mép cắt</option>
              </select>
            </label>
            <div className="field tg__check" style={{ marginTop: "24px" }}>
              <input type="checkbox" checked={eyeletRequired} onChange={e => setEyeletRequired(e.target.checked)} />
              <span>Đóng khoen luồn dây (Eyelets)</span>
            </div>
          </div>
        );
      default:
        return (
          <div className="tg__form-grid">
            <label className="field">
              <span className="field__label">Kích thước rộng (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedWidth} onChange={e => setFinishedWidth(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Kích thước cao (cm) *</span>
              <input className="input" type="number" step="0.1" value={finishedHeight} onChange={e => setFinishedHeight(e.target.value)} />
            </label>
          </div>
        );
    }
  }

  // Render main list screen
  if (mode === null) {
    return (
      <main className="tg">
        <header className="tg__head">
          <p className="eyebrow">Kinh doanh</p>
          <h1 className="tg__title">Tính giá</h1>
          <p className="tg__sub">
            Giá thành / giá vốn nội bộ: chọn phương án giấy, nhập số con/khổ, engine tính toán định mức và hao hụt để ra giá vốn.
          </p>
        </header>

        <div className="tg__toolbar">
          <form className="tg__search" onSubmit={onSearch} role="search">
            <input
              className="input"
              placeholder="Tìm theo mã hoặc tên sản phẩm..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Tìm phương án"
            />
            <Button type="submit" variant="ghost">Tìm</Button>
          </form>

          <select
            className="input tg__statusfilter"
            value={productTypeFilter}
            onChange={(e) => {
              setProductTypeFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Lọc loại sản phẩm"
          >
            <option value="">Tất cả loại SP</option>
            {productTypes.map((pt) => (
              <option key={pt.product_type} value={pt.product_type}>
                {pt.name}
              </option>
            ))}
          </select>

          <div className="tg__toolbar-spacer" />

          <Button variant="primary" onClick={openCreate}>
            + Tạo tính giá
          </Button>
        </div>

        {/* Tab trạng thái + đếm số (kiểu hộp thư) */}
        <div style={{ margin: "12px 0 16px" }}>
          <StatusTabs
            tabs={[
              { key: "", label: "Tất cả", count: stats?.total },
              { key: "draft", label: "Nháp", count: stats?.draft },
              { key: "calculated", label: "Đã tính giá", count: stats?.calculated },
              { key: "blocking", label: "Lỗi chặn", count: stats?.blocking, tone: "alert" },
            ]}
            active={statusFilter}
            onChange={(k) => {
              setStatusFilter(k);
              setPage(1);
            }}
          />
        </div>

        <div className="card tg__tablewrap">
          <table className="tg__table">
            <thead>
              <tr>
                <th>
                  <SortBtn label="Mã TG" col="code" sort={sort} onSort={setSort} />
                </th>
                <th>Sản phẩm</th>
                <th className="tg__num">Số lượng</th>
                <th className="tg__num">Lỗi/Cảnh báo</th>
                <th className="tg__num">Giá vốn</th>
                <th>Trạng thái</th>
                <th>Cập nhật</th>
                <th className="tg__actions-col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="tg__status" role="status">Đang tải…</td>
                </tr>
              ) : listError ? (
                <tr>
                  <td colSpan={8} className="tg__status">
                    <div className="banner banner--error" role="alert">
                      <span>{listError}</span>
                      <button type="button" className="btn btn--ghost" onClick={() => load()}>Thử lại</button>
                    </div>
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="tg__empty">
                    <p>Chưa có phương án tính giá nào.</p>
                    <p className="tg__muted">Tạo phương án đầu tiên để bắt đầu tính giá sản phẩm in.</p>
                    <Button variant="primary" onClick={openCreate}>+ Tạo tính giá</Button>
                  </td>
                </tr>
              ) : (
                rows.map((c) => {
                  const isCalculated = c.status === "calculated";
                  const badgeClass = isCalculated
                    ? "tg__badge--ready"
                    : c.status === "cancelled"
                    ? "tg__badge--cancelled"
                    : "";

                  const minMaxCost =
                    c.total_cost_min != null && c.total_cost_max != null
                      ? c.total_cost_min === c.total_cost_max
                        ? `${c.total_cost_min.toLocaleString("vi-VN")} đ`
                        : `${c.total_cost_min.toLocaleString("vi-VN")} - ${c.total_cost_max.toLocaleString("vi-VN")} đ`
                      : "—";

                  const typeLabel = productTypes.find(p => p.product_type === c.product_type)?.name ?? c.product_type;
                  const techLabel = c.machine_type === "offset" ? "Offset" : c.machine_type === "digital" ? "KTS" : null;
                  const specLine = [techLabel, c.spec_summary].filter(Boolean).join(" · ");

                  return (
                    <tr key={c.id} className="tg__row" onClick={() => openEdit(c)}>
                      <td className="tg__mono">{c.estimate_number}</td>
                      <td>
                        <strong>{c.product_name}</strong>
                        <span className="tgroup__subdesc">
                          {typeLabel}
                          {specLine ? ` · ${specLine}` : ""}
                        </span>
                      </td>
                      <td className="tg__num tg__mono">
                        {c.quantity_list_json.map((q) => q.toLocaleString("vi-VN")).join(", ")}
                      </td>
                      <td className="tg__num">
                        {c.blocking_error_count > 0 ? (
                          <span className="tg__badge tg__badge--error" title={`${c.blocking_error_count} lỗi chặn`}>
                            <span className="tg__dot-pulse" /> {c.blocking_error_count} lỗi chặn
                          </span>
                        ) : c.warnings_count > 0 ? (
                          <span className="tg__badge tg__badge--warn" title={`${c.warnings_count} cảnh báo`}>
                            ⚠️ {c.warnings_count} cảnh báo
                          </span>
                        ) : (
                          <span className="tg__muted">Không</span>
                        )}
                      </td>
                      <td className="tg__num tg__mono">
                        <strong>{minMaxCost}</strong>
                        {c.unit_cost_min != null && (
                          <span className="tgroup__subdesc">≈ {Math.round(c.unit_cost_min).toLocaleString("vi-VN")} đ/sp</span>
                        )}
                      </td>
                      <td>
                        <span className={`tg__badge ${badgeClass}`}>
                          {c.status === "calculated" ? "Đã tính" : c.status === "draft" ? "Nháp" : c.status}
                        </span>
                      </td>
                      <td>
                        <span style={{ whiteSpace: "nowrap" }}>
                          {new Date(c.updated_at ?? c.created_at).toLocaleDateString("vi-VN")}
                        </span>
                        {c.created_by_name && <span className="tgroup__subdesc">{c.created_by_name}</span>}
                      </td>
                      <td className="tg__actions-col" onClick={(e) => e.stopPropagation()}>
                        <button type="button" className="btn btn--ghost tg__rowbtn" onClick={() => openEdit(c)}>
                          Xem/Sửa
                        </button>
                        <button type="button" className="btn btn--ghost tg__rowbtn tg__rowbtn--danger" onClick={() => setDeleting(c)}>
                          Xoá
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pager */}
        {total > PAGE_SIZE && (
          <div className="tg__pager">
            <span>Tổng số {total} phương án</span>
            <div className="tg__pager-btns">
              <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Trước</Button>
              <Button disabled={page * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>Sau</Button>
            </div>
          </div>
        )}

        {deleting && (
          <ConfirmDeleteDialog
            costing={deleting}
            onCancel={() => setDeleting(null)}
            onConfirm={confirmDelete}
          />
        )}
      </main>
    );
  }

  // --- Form View (Create / Edit) ---
  const currentOption = editing?.options?.[activeQtyTab];
  const auditLine = currentOption?.cost_lines?.find(l => l.id === auditLineId);

  return (
    <main className="tg">
      <header className="tg__head" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <button type="button" className="btn btn--ghost" onClick={handleCloseForm} style={{ marginBottom: "8px", paddingLeft: 0 }}>
            ← Quay lại danh sách
          </button>
          <h1 className="tg__title">
            {isEdit ? `Sửa phương án · ${editing?.estimate_number}` : "Tạo tính giá mới"}
          </h1>
        </div>

        {/* Form view mode switcher */}
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            type="button"
            className={`btn ${activeFormTab === "spec" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setActiveFormTab("spec")}
          >
            Thông số kỹ thuật
          </button>
          <button
            type="button"
            className={`btn ${activeFormTab === "result" ? "btn--primary" : "btn--ghost"}`}
            disabled={!editing || !editing.options || editing.options.length === 0}
            onClick={() => setActiveFormTab("result")}
          >
            Kết quả & Phân rã chi phí {!editing && "(chưa tính)"}
          </button>
          {editing && editing.status === "calculated" && (
            <Button
              type="button"
              variant="accent"
              onClick={() => {
                if (navigate) {
                  navigate("bao-gia", { estimateId: editing.id });
                }
              }}
              title="Tạo Báo giá thương mại từ phương án này"
              style={{ marginLeft: "12px" }}
            >
              💼 Tạo báo giá
            </Button>
          )}
        </div>
      </header>

      {activeFormTab === "spec" ? (
        <form className="tg__page-layout" onSubmit={(e) => { e.preventDefault(); handleSave("calculated"); }} noValidate>
          {/* Left Columns - Form Inputs */}
          <div className="tg__form-col">
            
            {isEdit && (
              <div className="tg__recalc-notice">
                ⚠️ <strong>Lưu ý:</strong> Thay đổi thông số kỹ thuật hoặc danh sách số lượng sẽ tự động kích hoạt tính toán lại toàn bộ (Recalculate) và thay thế toàn bộ kết quả breakdown cũ.
              </div>
            )}

            {/* Block 1: Thông tin chung */}
            <section className="tg__form-section">
              <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px" }}>
                1. Thông tin chung
              </h3>
              <div className="tg__form-grid" style={{ marginTop: "16px" }}>
                <label className="field">
                  <span className="field__label">Tên sản phẩm in *</span>
                  <input
                    className="input"
                    value={productName}
                    placeholder="Ví dụ: Brochure A4 giới thiệu sản phẩm..."
                    onChange={(e) => setProductName(e.target.value)}
                    required
                  />
                </label>

                <label className="field">
                  <span className="field__label">Người tính giá</span>
                  <input
                    className="input"
                    value={user?.name ?? user?.username ?? "—"}
                    readOnly
                    disabled
                  />
                </label>

                <label className="field">
                  <span className="field__label">Ngày tính giá</span>
                  <input
                    className="input"
                    type="date"
                    value={new Date().toISOString().substring(0, 10)}
                    readOnly
                    disabled
                  />
                </label>

                <label className="field tg__form-wide">
                  <span className="field__label">Ghi chú nội bộ</span>
                  <input
                    className="input"
                    value={note}
                    placeholder="Nhập ghi chú yêu cầu gia công riêng..."
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
              </div>
            </section>

            {/* Block 2: Loại sản phẩm */}
            <section className="tg__form-section">
              <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px" }}>
                2. Loại sản phẩm
              </h3>
              <div className="tg__form-grid" style={{ marginTop: "16px" }}>
                <label className="field tg__form-wide">
                  <span className="field__label">Chọn loại cấu hình sản phẩm</span>
                  <select
                    className="input"
                    value={productType}
                    onChange={(e) => handleProductTypeChange(e.target.value)}
                  >
                    {productTypes.map((pt) => (
                      <option key={pt.product_type} value={pt.product_type}>
                        {pt.name} (Tính {pt.calculation_strategy})
                      </option>
                    ))}
                  </select>
                </label>
                {/* Danh mục #1 — box "Quy tắc áp dụng" theo loại SP đang chọn */}
                {(() => {
                  const cfg = productTypes.find((p) => p.product_type === productType);
                  if (!cfg) return null;
                  const dimLabel: Record<string, string> = { finished: "khổ thành phẩm", spread: "khổ trải", multi_page: "khổ trang (nhiều trang)" };
                  const routing = (cfg.default_operations || []).map((t) => operationsCatalog.find((o) => o.operation_type === t)?.name ?? t);
                  return (
                    <div className="field tg__form-wide" style={{ marginTop: 6, background: "rgba(20,19,15,0.03)", border: "1px solid var(--rule-hair)", borderRadius: 6, padding: "10px 12px", fontSize: 12.5, lineHeight: 1.7 }}>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>Quy tắc áp dụng — {cfg.name}</div>
                      <div>Kích thước tính số con: <strong>{dimLabel[cfg.dimension_rule_type] ?? cfg.dimension_rule_type}</strong>
                        {(cfg.default_bleed_mm || cfg.default_gutter_mm || cfg.default_trim_mm)
                          ? <> · bleed <strong>{cfg.default_bleed_mm}mm</strong> · gutter <strong>{cfg.default_gutter_mm}mm</strong> · lề xén <strong>{cfg.default_trim_mm}mm</strong> (đã tự điền)</>
                          : null}</div>
                      {routing.length ? <div>Routing gợi ý: <strong>{routing.join(" → ")}</strong> (đã tự nạp công đoạn)</div> : null}
                      {cfg.has_tooling ? <div style={{ color: "var(--rust)" }}>Có phát sinh khuôn ({cfg.default_tooling_type ?? "—"}).</div> : null}
                      {cfg.has_cover_body_split ? <div>Tính bìa / ruột riêng.</div> : null}
                      {cfg.allowed_imposition_codes?.length ? <div>Kiểu bình bài cho phép: <strong>{cfg.allowed_imposition_codes.join(", ")}</strong>.</div> : null}
                    </div>
                  );
                })()}
              </div>
            </section>

            {/* Block 3: Số lượng cần tính */}
            <section className="tg__form-section">
              <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px" }}>
                3. Số lượng cần tính
              </h3>
              <div style={{ marginTop: "16px" }}>
                <QuantityChipInput
                  value={quantityList}
                  onChange={setQuantityList}
                  onError={setQtyError}
                />
                {qtyError && (
                  <span className="tg__err" role="alert" style={{ display: "block", marginTop: "8px" }}>
                    {qtyError}
                  </span>
                )}
              </div>
            </section>

            {/* Block 4: Thông số kỹ thuật */}
            <section className="tg__form-section">
              <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px" }}>
                4. Thông số kỹ thuật sản phẩm
              </h3>
              <div style={{ marginTop: "16px" }}>
                {renderProductSpecFields()}
              </div>
            </section>

            {/* Block 5: Vật liệu */}
            <section className="tg__form-section">
              <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px" }}>
                5. Vật liệu in chính
              </h3>
              <div className="tg__form-grid" style={{ marginTop: "16px" }}>
                <label className="field tg__form-wide">
                  <span className="field__label">Chọn chất liệu giấy in *</span>
                  <select
                    className="input"
                    value={materialId || ""}
                    onChange={(e) => setMaterialId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Chọn giấy trong danh mục...</option>
                    {materials.filter(m => m.material_type === "paper").map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.code}) - {m.width_cm}x{m.height_cm}cm
                      </option>
                    ))}
                  </select>
                  {materialId !== null && (() => {
                    const mat = materials.find(m => m.id === materialId);
                    const latestCost = mat?.costs?.[0];
                    return (
                      <span className="tg__suggest" style={{ display: "block", marginTop: "4px" }}>
                        Khổ: <strong>{mat?.width_cm} x {mat?.height_cm} cm</strong>. GSM: <strong>{mat?.gsm}</strong>. 
                        Đơn giá hiện hành: {latestCost ? (
                          <strong>{latestCost.unit_price.toLocaleString("vi-VN")} đ / {latestCost.price_unit}</strong>
                        ) : (
                          <span style={{ color: "var(--signal)", fontWeight: "bold" }}>⚠️ Chưa cấu hình giá hiệu lực!</span>
                        )}
                      </span>
                    );
                  })()}
                </label>

                <label className="field tg__form-wide">
                  <span className="field__label">Khổ tờ in (chuẩn)</span>
                  <select
                    className="input"
                    value={printSizeId || ""}
                    onChange={(e) => setPrintSizeId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">— Dùng khổ của vật tư —</option>
                    {paperSizes
                      .filter(s => machineId === null || !s.compatible_machine_ids || s.compatible_machine_ids.length === 0 || s.compatible_machine_ids.includes(machineId))
                      .map(s => (
                        <option key={s.id} value={s.id}>
                          {s.code} · {s.name} ({s.width_cm}×{s.height_cm} cm)
                        </option>
                      ))}
                  </select>
                  {printSizeId !== null && (() => {
                    const psz = paperSizes.find(s => s.id === printSizeId);
                    const mac = machines.find(m => m.id === machineId);
                    if (!psz) return null;
                    let warn: string | null = null;
                    if (mac && mac.max_width_cm != null && mac.max_height_cm != null) {
                      const w = psz.width_cm, h = psz.height_cm, mw = mac.max_width_cm, mh = mac.max_height_cm;
                      const fits = (w <= mw && h <= mh) || (psz.allow_rotation && h <= mw && w <= mh);
                      if (!fits) warn = `⚠️ Khổ ${w}×${h} vượt khổ in tối đa của ${mac.name} (${mw}×${mh}).`;
                    }
                    return (
                      <span className="tg__suggest" style={{ display: "block", marginTop: "4px" }}>
                        Khổ tờ in: <strong>{psz.width_cm} × {psz.height_cm} cm</strong> — ghi đè khổ từ vật tư.
                        {warn && <span style={{ color: "var(--signal)", fontWeight: "bold", display: "block" }}>{warn}</span>}
                      </span>
                    );
                  })()}
                </label>

                <label className="tg__toggle" style={{ marginTop: "8px" }}>
                  <input
                    type="checkbox"
                    checked={overridePieces}
                    onChange={(e) => setOverridePieces(e.target.checked)}
                  />
                  <span className="tg__toggle-text">
                    Tự nhập số con trên khổ giấy
                    <small>Không dùng thuật toán bình bản tự động — nhập tay số con/khổ.</small>
                  </span>
                </label>

                {overridePieces ? (
                  <label className="field tg__form-wide">
                    <span className="field__label">Số con trên khổ (pieces_per_sheet) *</span>
                    <input
                      className="input"
                      type="number"
                      min="1"
                      value={piecesPerSheet}
                      onChange={(e) => setPiecesPerSheet(e.target.value)}
                    />
                  </label>
                ) : (
                  <div className="field tg__form-wide">
                    <span className="field__label">Bố cục dàn trang (Pieces per sheet)</span>
                    <span className="tg__suggest">
                      Dự kiến từ thuật toán hình học: {suggestedPieces !== null ? (
                        <strong style={{ fontSize: "15px", color: "var(--rust)" }}>{suggestedPieces} con/khổ</strong>
                      ) : (
                        <span className="tg__muted">Vui lòng nhập đầy đủ kích thước khổ in & SP.</span>
                      )}
                    </span>
                  </div>
                )}

                <label className="tg__toggle">
                  <input
                    type="checkbox"
                    checked={grainLocked}
                    onChange={(e) => setGrainLocked(e.target.checked)}
                  />
                  <span className="tg__toggle-text">
                    Ràng buộc thớ giấy (Grain locked)
                    <small>Bỏ nhánh xoay giấy — giữ đúng chiều thớ khi dàn con.</small>
                  </span>
                </label>

                {/* #4 — tham số bình bản CHỈ áp cho thuật toán tự tính số con/khổ; khi
                    "Tự nhập số con" bật, engine dùng số nhập tay nên ẩn để khỏi gây hiểu lầm. */}
                {!overridePieces && (
                  <div className="tg__form-grid tg__form-wide" style={{ marginTop: "12px" }}>
                    <label className="field">
                      <span className="field__label">Kẹp nhíp (cm)</span>
                      <input className="input" type="number" step="0.1" placeholder="VD: 1.0" value={gripperCm} onChange={(e) => setGripperCm(e.target.value)} />
                    </label>
                    <label className="field">
                      <span className="field__label">Xén mép (cm)</span>
                      <input className="input" type="number" step="0.1" placeholder="VD: 0.5" value={edgeTrimCm} onChange={(e) => setEdgeTrimCm(e.target.value)} />
                    </label>
                    <label className="field">
                      <span className="field__label">Bleed tràn lề (cm)</span>
                      <input className="input" type="number" step="0.1" placeholder="VD: 0.3" value={bleedCm} onChange={(e) => setBleedCm(e.target.value)} />
                    </label>
                    <label className="field">
                      <span className="field__label">Chừa giữa con (cm)</span>
                      <input className="input" type="number" step="0.1" placeholder="VD: 0.3" value={gutterCm} onChange={(e) => setGutterCm(e.target.value)} />
                    </label>
                  </div>
                )}

                {/* Sơ đồ bình bản trực quan — cập nhật sống theo khổ giấy + tham số phía trên */}
                {!overridePieces && (() => {
                  const mat = materials.find(m => m.id === materialId);
                  const psz = paperSizes.find(s => s.id === printSizeId);
                  const sw = psz?.width_cm ?? mat?.width_cm;
                  const sh = psz?.height_cm ?? mat?.height_cm;
                  let pw = 0, ph = 0;
                  if (productType === "box" || productType === "packaging") {
                    pw = Number(boxLength) || 0;
                    ph = Number(boxWidth) || 0;
                  } else if (productType === "banner" || productType === "large_format") {
                    pw = Number(largeWidth) || 0;
                    ph = Number(largeHeight) || 0;
                  } else {
                    pw = Number(finishedWidth) || 0;
                    ph = Number(finishedHeight) || 0;
                  }
                  if (!sw || !sh || pw <= 0 || ph <= 0) return null;

                  const inp = {
                    sheetW: sw,
                    sheetH: sh,
                    finishedW: pw,
                    finishedH: ph,
                    gripperCm: Number(gripperCm) || 0,
                    edgeTrimCm: Number(edgeTrimCm) || 0,
                    bleedCm: Number(bleedCm) || 0,
                    gutterCm: Number(gutterCm) || 0,
                    grainLocked,
                  };
                  const lay = computeImposition(inp);
                  if (!lay) return null;

                  return (
                    <div className="tg__form-wide" style={{ display: "flex", gap: "20px", alignItems: "flex-start", flexWrap: "wrap", marginTop: "16px", background: "var(--paper)", border: "1px solid var(--rule-soft)", borderRadius: "8px", padding: "14px" }}>
                      <div style={{ flex: "1 1 260px", maxWidth: "420px" }}>
                        <ImpositionDiagram input={inp} />
                      </div>
                      <div style={{ flex: "1 1 210px", fontSize: "13px" }}>
                        <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px", display: "block", marginBottom: "8px" }}>
                          SƠ ĐỒ BÌNH BẢN — TỰ CẬP NHẬT THEO KHỔ & THAM SỐ
                        </span>
                        <div className="tg__summary-list">
                          <div className="tg__summary-item">
                            <span className="tg__summary-label">Khổ tờ</span>
                            <span className="tg__summary-value tg__mono">{sw}×{sh} cm</span>
                          </div>
                          <div className="tg__summary-item">
                            <span className="tg__summary-label">Bố cục</span>
                            <span className="tg__summary-value tg__mono">
                              {lay.fits ? `${lay.cols}×${lay.rows}${lay.rotated ? " (xoay 90°)" : ""}` : "—"}
                            </span>
                          </div>
                          <div className="tg__summary-item">
                            <span className="tg__summary-label">Số con / tờ</span>
                            <span className="tg__summary-value tg__mono" style={{ color: "var(--rust)", fontWeight: "bold" }}>
                              {suggestedPieces ?? lay.pieces} con
                            </span>
                          </div>
                          <div className="tg__summary-item">
                            <span className="tg__summary-label">Hiệu suất kê</span>
                            <span className="tg__summary-value tg__mono">{lay.fits ? `${Math.round(lay.efficiencyPct)}%` : "0%"}</span>
                          </div>
                        </div>
                        {!lay.fits && (
                          <p style={{ color: "var(--signal)", fontSize: "12.5px", marginTop: "8px", lineHeight: 1.5 }}>
                            ⚠ <strong>Vượt khổ:</strong> thành phẩm {pw}×{ph} cm (kèm bleed/nhíp/xén) lớn hơn vùng in được của tờ
                            {" "}{sw}×{sh} cm — chọn khổ giấy lớn hơn hoặc giảm tham số bình bản.
                          </p>
                        )}
                        {lay.fits && suggestedPieces !== null && suggestedPieces !== lay.pieces && (
                          <p className="tg__suggest" style={{ marginTop: "8px" }}>
                            * Engine chốt {suggestedPieces} con/tờ (sơ đồ ước tính {lay.pieces}).
                          </p>
                        )}
                      </div>

                      {/* Phương án khác — cùng thành phẩm + tham số bình, đổi khổ giấy → so số con/tờ */}
                      {(() => {
                        const curPieces = suggestedPieces ?? lay.pieces;
                        const alts = paperSizes
                          .filter((s) => s.id !== printSizeId && s.width_cm && s.height_cm)
                          .map((s) => {
                            const l = computeImposition({ ...inp, sheetW: s.width_cm, sheetH: s.height_cm });
                            return { s, pieces: l && l.fits ? l.pieces : 0, eff: l && l.fits ? l.efficiencyPct : 0, rotated: !!l?.rotated };
                          })
                          .filter((a) => a.pieces > 0)
                          .sort((a, b) => b.pieces - a.pieces || b.eff - a.eff)
                          .slice(0, 6);
                        if (alts.length === 0) return null;
                        return (
                          <div style={{ flexBasis: "100%", borderTop: "1px dashed var(--rule)", paddingTop: "12px" }}>
                            <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px", display: "block", marginBottom: "8px" }}>
                              PHƯƠNG ÁN KHÁC — cùng thành phẩm, đổi khổ giấy (bấm để chọn)
                            </span>
                            <div className="tg__alt-grid">
                              {alts.map((a) => {
                                const better = a.pieces > curPieces;
                                return (
                                  <button
                                    type="button"
                                    key={a.s.id}
                                    className={`tg__alt${better ? " tg__alt--better" : ""}`}
                                    onClick={() => setPrintSizeId(a.s.id)}
                                    title={`Chọn khổ ${a.s.width_cm}×${a.s.height_cm}`}
                                  >
                                    <span className="tg__alt-name">{a.s.width_cm}×{a.s.height_cm} cm</span>
                                    <span className="tg__alt-pieces">{a.pieces} con/tờ{a.rotated ? " ⟳" : ""}</span>
                                    <span className="tg__alt-eff">{Math.round(a.eff)}% giấy{better ? " · nhiều con hơn" : ""}</span>
                                  </button>
                                );
                              })}
                            </div>
                            <p className="tg__muted" style={{ fontSize: "11.5px", marginTop: "8px" }}>
                              Khổ đang chọn: <strong>{sw}×{sh} cm · {curPieces} con/tờ</strong>. Ô nền xanh = được nhiều con hơn.
                            </p>
                          </div>
                        );
                      })()}
                    </div>
                  );
                })()}
              </div>
            </section>

            {/* Block 6: Công nghệ in / máy */}
            <section className="tg__form-section">
              <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px" }}>
                6. Công nghệ & Máy in
              </h3>
              <div className="tg__form-grid" style={{ marginTop: "16px" }}>
                <label className="field tg__form-wide">
                  <span className="field__label">Chọn máy in dự kiến *</span>
                  <select
                    className="input"
                    value={machineId || ""}
                    onChange={(e) => setMachineId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Chọn máy in...</option>
                    {machines.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.code}) - {m.machine_type === "offset" ? "Offset" : m.machine_type === "digital" ? "Kỹ thuật số" : m.machine_type}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field tg__form-wide">
                  <span className="field__label">Kiểu bình bài</span>
                  <select
                    className="input"
                    value={imposition}
                    onChange={(e) => {
                      const code = e.target.value;
                      setImposition(code);
                      const t = impositionTypes.find((it) => it.code === code);
                      // Kiểu 1 mặt / 2 mặt xác định → đồng bộ số mặt (custom/nhiều trang giữ nguyên).
                      if (t && t.group_kind === "one_side") setSides(1);
                      else if (t && t.group_kind === "two_side") setSides(2);
                    }}
                  >
                    <option value="">— Tự suy theo số mặt —</option>
                    {impositionTypes
                      .filter((it) => !it.applicable_product_types?.length || it.applicable_product_types.includes(productType))
                      .filter((it) => !it.applicable_machine_ids?.length || (machineId !== null && it.applicable_machine_ids.includes(machineId)))
                      .filter((it) => it.applies_to_sides === "any" || it.applies_to_sides === "multi" || it.applies_to_sides === String(sides))
                      // Danh mục #1 — chỉ hiện kiểu bình bài nằm trong allowlist của loại SP (nếu có khai).
                      .filter((it) => {
                        const cfg = productTypes.find((p) => p.product_type === productType);
                        return !cfg?.allowed_imposition_codes?.length || cfg.allowed_imposition_codes.includes(it.code);
                      })
                      .map((it) => (
                        <option key={it.id} value={it.code}>
                          {it.name} ({it.code})
                        </option>
                      ))}
                  </select>
                  {(() => {
                    const t = impositionTypes.find((it) => it.code === imposition);
                    if (!t) return <span className="tg__suggest" style={{ display: "block" }}>Không chọn = engine suy hệ số theo số mặt (1 mặt / trở nhíp 2 kẽm).</span>;
                    return (
                      <div style={{ marginTop: 6, background: "rgba(20,19,15,0.03)", border: "1px solid var(--rule-hair)", borderRadius: 6, padding: "10px 12px", fontSize: 12.5, lineHeight: 1.7 }}>
                        <div style={{ fontWeight: 700, marginBottom: 4 }}>{t.name} — diễn giải</div>
                        <div>Hệ số thành phẩm: <strong>{t.finished_factor}</strong> · Số lượt qua máy: <strong>{t.pass_count}</strong> · Hệ số bộ kẽm: <strong>{t.plate_set_factor}</strong> · Hệ số lượt in màu: <strong>{t.ink_pass_factor}</strong></div>
                        <div style={{ marginTop: 6, color: "var(--rust)" }}>
                          Ảnh hưởng: Số con TP/tờ = con hình học × {t.finished_factor} · Giờ máy = tờ SX × {t.pass_count} / tốc độ · Kẽm = số màu × {t.plate_set_factor} × số form/tay · Mực = tờ SX × số màu × {t.ink_pass_factor}
                        </div>
                      </div>
                    );
                  })()}
                </label>

                {machineId !== null && (() => {
                  const m = machines.find(mac => mac.id === machineId);
                  if (!m) return null;
                  const rate = m.rates.find(r => r.effective_to === null);
                  const mat = materials.find(x => x.id === materialId);
                  const sw = mat?.width_cm ?? null, sh = mat?.height_cm ?? null;
                  const tooBig = sw && sh && m.max_width_cm && m.max_height_cm && (sw > m.max_width_cm || sh > m.max_height_cm);
                  return (
                    <div className="field tg__form-wide" style={{ background: "rgba(20,19,15,0.03)", padding: "10px", borderRadius: "4px", fontSize: 12.5, lineHeight: 1.7 }}>
                      <div><strong>Khả năng máy:</strong> khổ giấy tối đa <strong>{m.max_width_cm ?? "?"}×{m.max_height_cm ?? "?"}cm</strong>
                        {m.max_print_width_cm ? <> · khổ in <strong>{m.max_print_width_cm}×{m.max_print_height_cm}cm</strong></> : null}
                        {m.gripper_cm ? <> · nhíp {m.gripper_cm}cm</> : null}
                        {" · "}tốc độ <strong>{m.speed.toLocaleString("vi-VN")} {m.speed_unit}</strong>
                        {rate ? <> · đơn giá <strong>{rate.hourly_rate.toLocaleString("vi-VN")}đ/giờ</strong></> : <> · <span style={{ color: "var(--rust)" }}>chưa có đơn giá giờ</span></>}
                      </div>
                      {tooBig ? (
                        <div style={{ marginTop: 4, color: "var(--rust)", fontWeight: 600 }}>
                          ⚠️ Khổ giấy {sw}×{sh}cm vượt khổ tối đa của máy — máy có thể không chạy được, hãy đổi máy hoặc khổ.
                        </div>
                      ) : (
                        <div style={{ marginTop: 4, color: "var(--rust)" }}>
                          💡 Giờ máy = setup + tờ tính giờ / tốc độ + vệ sinh + đổi màu + đổi kẽm · Công in = Giờ máy × đơn giá giờ (xem chi tiết ở bảng kết quả).
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </section>

            {/* Block 7: Công đoạn gia công */}
            <section className="tg__form-section">
              <div className="tg__form-section-head">
                <h3 className="tg__section-title">7. Công đoạn gia công sản xuất</h3>
                <div style={{ display: "flex", gap: "8px" }}>
                  <select
                    className="input"
                    defaultValue=""
                    onChange={(e) => {
                      addOp(e.target.value);
                      e.target.value = "";
                    }}
                    style={{ width: "200px", padding: "4px 8px" }}
                  >
                    <option value="">+ Thêm công đoạn...</option>
                    {operationsCatalog.map(o => (
                      <option key={o.id} value={o.name}>{o.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {operations.length === 0 ? (
                <p className="tg__muted" style={{ textAlign: "center", padding: "16px 0" }}>
                  Chưa chọn công đoạn gia công. Engine sẽ tính hao hụt bù hao ngược chuỗi in ấn.
                </p>
              ) : (
                <div className="tg__op-list-vertical">
                  {operations.map((op, idx) => (
                    <div key={op.key} className="tg__op-card-compact">
                      <div className="tg__op-card-info">
                        <span className="tg__op-seq-badge">#{op.sequence}</span>
                        <span className="tg__op-name-main">{op.name}</span>
                        <select
                          className="input"
                          value={op.execution_mode}
                          onChange={(e) => {
                            const updated = operations.map(o => o.key === op.key ? { ...o, execution_mode: e.target.value } : o);
                            setOperations(updated);
                          }}
                          style={{ width: "130px", padding: "2px 6px", fontSize: "12px" }}
                        >
                          <option value="internal">Nội bộ (Internal)</option>
                          <option value="outsource">Gia công ngoài (Outsource)</option>
                        </select>
                        <span className={`tg__op-mode-pill tg__op-mode-pill--${op.execution_mode}`}>
                          {op.execution_mode === "internal" ? "Định mức khoán" : "Giá NCC"}
                        </span>
                      </div>

                      <div className="tg__op-actions-group">
                        <button
                          type="button"
                          className="tg__op-btn-reorder"
                          disabled={idx === 0}
                          onClick={() => moveOp(idx, "up")}
                          title="Di chuyển lên (Tăng sequence sản xuất)"
                        >
                          ▲
                        </button>
                        <button
                          type="button"
                          className="tg__op-btn-reorder"
                          disabled={idx === operations.length - 1}
                          onClick={() => moveOp(idx, "down")}
                          title="Di chuyển xuống (Giảm sequence)"
                        >
                          ▼
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost tg__rowbtn tg__rowbtn--danger"
                          onClick={() => removeOp(op.key)}
                          style={{ marginLeft: "8px" }}
                        >
                          Xoá
                        </button>
                      </div>
                    </div>
                  ))}
                  <span className="tg__suggest" style={{ color: "var(--ash)" }}>
                    * <strong>Chuỗi bù hao ngược:</strong> Bù hao sẽ dồn ngược từ công đoạn cuối cùng (phía dưới) lên in ấn đầu chuỗi (phía trên).
                  </span>
                </div>
              )}
            </section>

            {/* Block 8: Phí phát sinh nhập tay */}
            <section className="tg__form-section">
              <div className="tg__form-section-head">
                <h3 className="tg__section-title">8. Phí phát sinh (nhập tay / outsource ngoài)</h3>
                <Button type="button" variant="ghost" onClick={addCustomCost}>
                  + Thêm phí phát sinh
                </Button>
              </div>

              {customCosts.length === 0 ? (
                <p className="tg__muted" style={{ textAlign: "center", padding: "16px 0" }}>
                  Chưa nhập phí phát sinh tay.
                </p>
              ) : (
                <table className="tg__fees-table">
                  <thead>
                    <tr>
                      <th>Loại chi phí</th>
                      <th>Mô tả chi tiết *</th>
                      <th style={{ width: "200px" }}>Thành tiền (đ) *</th>
                      <th style={{ width: "80px", textAlign: "right" }}>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customCosts.map((cost, idx) => (
                      <tr key={idx}>
                        <td>
                          <select
                            className="input"
                            value={cost.category}
                            onChange={(e) => updateCustomCost(idx, { category: e.target.value as any })}
                          >
                            <option value="outsource">Gia công ngoài (Outsource)</option>
                            <option value="delivery">Vận chuyển (Delivery)</option>
                            <option value="other">Phí khác (Other)</option>
                          </select>
                        </td>
                        <td>
                          <input
                            className="input"
                            value={cost.description}
                            placeholder="Mô tả chi tiết..."
                            onChange={(e) => updateCustomCost(idx, { description: e.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            className="input"
                            type="number"
                            min="0"
                            value={cost.total_cost}
                            onChange={(e) => updateCustomCost(idx, { total_cost: Number(e.target.value) })}
                          />
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <button
                            type="button"
                            className="btn btn--ghost tg__rowbtn tg__rowbtn--danger"
                            onClick={() => removeCustomCost(idx)}
                          >
                            Xoá
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>

          {/* Right Columns - Sticky Sidebar Summary */}
          <div className="tg__sidebar-col">
            <div className="tg__summary-panel">
              <h3 className="tg__summary-title">Tóm tắt cấu hình</h3>
              
              <div className="tg__summary-list">
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Mã phương án</span>
                  <span className="tg__summary-value tg__mono">{editing?.estimate_number ?? "(Tự sinh)"}</span>
                </div>
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Loại sản phẩm</span>
                  <span className="tg__summary-value">{productTypes.find(pt => pt.product_type === productType)?.name || productType}</span>
                </div>
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Số lượng tính</span>
                  <span className="tg__summary-value">{quantityList.length > 0 ? quantityList.join(", ") : "Chưa nhập"}</span>
                </div>
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Vật liệu giấy</span>
                  <span className="tg__summary-value">
                    {materialId ? (materials.find(m => m.id === materialId)?.code || "Đã chọn") : "Chưa chọn"}
                  </span>
                </div>
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Máy in</span>
                  <span className="tg__summary-value">
                    {machineId ? (machines.find(m => m.id === machineId)?.code || "Đã chọn") : "Chưa chọn"}
                  </span>
                </div>
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Số công đoạn</span>
                  <span className="tg__summary-value">{operations.length} công đoạn</span>
                </div>
                <div className="tg__summary-item">
                  <span className="tg__summary-label">Trạng thái lưu</span>
                  <span className="tg__summary-value">
                    <span className={`tg__badge ${status === "calculated" ? "tg__badge--ready" : ""}`}>
                      {status === "calculated" ? "Đã tính" : "Nháp"}
                    </span>
                  </span>
                </div>
              </div>

              {/* Live preview: engine chạy với spec đang gõ (không lưu) — panel tối kiểu phiếu tính giá. */}
              {(() => {
                const savedRange =
                  editing && editing.options && editing.options.length > 0
                    ? editing.options.length === 1
                      ? editing.options[0].total_cost.toLocaleString("vi-VN")
                      : `${Math.min(...editing.options.map(o => o.total_cost)).toLocaleString("vi-VN")} – ${Math.max(...editing.options.map(o => o.total_cost)).toLocaleString("vi-VN")}`
                    : null;
                if (!preview && !previewLoading && !savedRange) return null;

                const GROUPS: Array<[string, string[]]> = [
                  ["Vật tư (giấy + mực)", ["material", "ink"]],
                  ["Khuôn · Bản · Click", ["plate_die", "click_ink"]],
                  ["Chạy máy", ["machine"]],
                  ["Gia công", ["operation", "packing"]],
                  ["Phí khác", ["outsource", "delivery", "other"]],
                ];
                const rows = preview
                  ? GROUPS.map(([label, cats]) => {
                      const sum = preview.cost_lines
                        .filter((l) => cats.includes(l.category))
                        .reduce((acc, l) => acc + l.total_cost, 0);
                      return { label, value: `${Math.round(sum).toLocaleString("vi-VN")} đ`, sum };
                    })
                      .filter((r) => r.sum > 0)
                      .map(({ label, value }) => ({ label, value }))
                  : undefined;

                const qty = quantityList[0];
                const blocking = preview?.warnings.filter((w) => w.severity === "blocking_error").length ?? 0;
                const warns = (preview?.warnings.length ?? 0) - blocking;

                return (
                  <div style={{ marginBottom: "16px" }}>
                    <DarkSummaryPanel
                      label={previewLoading ? "TỔNG GIÁ VỐN (NỘI BỘ) ⋯" : "TỔNG GIÁ VỐN (NỘI BỘ)"}
                      labelExtra={preview && qty ? `SL ${qty.toLocaleString("vi-VN")}` : undefined}
                      amount={preview ? Math.round(preview.total_cost).toLocaleString("vi-VN") : savedRange}
                      sub={
                        preview && qty
                          ? `≈ ${Math.round(preview.total_cost / qty).toLocaleString("vi-VN")} đ/sp giá vốn`
                          : savedRange
                          ? "Kết quả đã lưu — gõ form để xem ước tính mới"
                          : undefined
                      }
                      note="Giá vốn nội bộ, chưa cộng lợi nhuận. Markup & giá bán nằm ở module Báo giá."
                      rows={rows}
                    >
                      {preview && (blocking > 0 || warns > 0 || customCosts.length > 0) && (
                        <div style={{ fontSize: "11.5px", lineHeight: 1.6, color: blocking ? "var(--signal-soft)" : "var(--amber-soft)" }}>
                          {(blocking > 0 || warns > 0) && (
                            <>
                              {blocking > 0 && `⛔ ${blocking} lỗi chặn`}
                              {blocking > 0 && warns > 0 && " · "}
                              {warns > 0 && `⚠️ ${warns} cảnh báo`}
                              {" — chi tiết sau khi Tính giá & Lưu."}
                            </>
                          )}
                          {customCosts.length > 0 && (
                            <div style={{ color: "var(--rule)" }}>* Chưa gồm {customCosts.length} phí phát sinh nhập tay.</div>
                          )}
                        </div>
                      )}
                    </DarkSummaryPanel>
                  </div>
                );
              })()}

              {formError && (
                <div className="banner banner--error" role="alert" style={{ marginBottom: "16px", fontSize: "12px" }}>
                  {formError}
                </div>
              )}

              <div style={{ marginTop: 12, marginBottom: 8, padding: 10, background: "rgba(20,19,15,0.03)", border: "1px solid var(--rule-hair)", borderRadius: 6, fontSize: 12.5 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>✏️ Sửa tay nâng cao (§12) — kèm lý do</div>
                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 8px", alignItems: "center" }}>
                  <span>Số tờ SX</span>
                  <div style={{ display: "flex", gap: 4 }}>
                    <input className="input" type="number" placeholder="số tờ" value={ovProdSheets.value} onChange={(e) => setOvProdSheets({ ...ovProdSheets, value: e.target.value })} style={{ width: 90 }} />
                    <input className="input" placeholder="Lý do" value={ovProdSheets.reason} onChange={(e) => setOvProdSheets({ ...ovProdSheets, reason: e.target.value })} />
                  </div>
                  <span>Đơn giá vật tư</span>
                  <div style={{ display: "flex", gap: 4 }}>
                    <input className="input" type="number" placeholder="đ/đơn vị" value={ovMatPrice.value} onChange={(e) => setOvMatPrice({ ...ovMatPrice, value: e.target.value })} style={{ width: 90 }} />
                    <input className="input" placeholder="Lý do" value={ovMatPrice.reason} onChange={(e) => setOvMatPrice({ ...ovMatPrice, reason: e.target.value })} />
                  </div>
                </div>
                <p className="tg__muted" style={{ marginTop: 6, fontSize: 11 }}>Trống = không sửa. Nhập giá trị thì BẮT BUỘC lý do (thiếu → không tính được). Số tờ SX cascade sang giấy/mực/công in.</p>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {editing?.locked_at ? (
                  <div className="banner banner--info" role="status" style={{ marginBottom: 4 }}>
                    🔒 Phiếu đã <strong>khóa snapshot</strong> (v{editing.version ?? 1}) — không sửa được. Bấm <strong>Sao chép</strong> để tạo phiên bản mới.
                  </div>
                ) : (
                  <>
                    <Button type="button" variant="primary" loading={saving} onClick={() => handleSave("calculated")} style={{ width: "100%" }}>
                      🚀 Tính giá & Lưu kết quả
                    </Button>
                    <Button type="button" variant="ghost" loading={saving} onClick={() => handleSave("draft")} style={{ width: "100%" }}>
                      💾 Lưu bản nháp (Draft)
                    </Button>
                  </>
                )}

                {editing && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {!editing.locked_at && editing.status === "calculated" && (
                      <Button type="button" variant="ghost" onClick={handleLockSnapshot} style={{ flex: "1 1 auto" }}>🔒 Khóa snapshot</Button>
                    )}
                    <Button type="button" variant="ghost" onClick={handleDuplicate} style={{ flex: "1 1 auto" }}>📄 Sao chép</Button>
                    <Button type="button" variant="ghost" onClick={handleExportCsv} style={{ flex: "1 1 auto" }}>⬇️ Xuất CSV</Button>
                  </div>
                )}

                <Button type="button" variant="ghost" onClick={handleCloseForm} style={{ width: "100%" }}>
                  Đóng / Quay lại
                </Button>
              </div>
            </div>
          </div>
        </form>
      ) : (
        // Tab display results calculation breakdown output
        <div style={{ marginTop: "16px" }}>
          
          {/* Summary options table grid */}
          <section className="tg__form-section" style={{ marginBottom: "24px" }}>
            <h3 className="tg__section-title" style={{ borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px", marginBottom: "16px" }}>
              Bảng so sánh tổng hợp các mức số lượng
            </h3>
            
            <table className="tg__table">
              <thead>
                <tr>
                  <th className="tg__num">Mức Số lượng</th>
                  <th className="tg__num">Tổng Giá vốn đề xuất</th>
                  <th className="tg__num">Giá vốn đơn chiếc (SP)</th>
                  <th>Cảnh báo phát sinh</th>
                  <th>Khả năng Báo giá</th>
                  <th>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {editing?.options?.map((opt, idx) => (
                  <tr key={opt.id} className={activeQtyTab === idx ? "tg__row-cat-material" : ""} style={{ cursor: "pointer" }} onClick={() => setActiveQtyTab(idx)}>
                    <td className="tg__num tg__mono"><strong>{opt.quantity.toLocaleString("vi-VN")}</strong></td>
                    <td className="tg__num tg__mono" style={{ color: "var(--rust)" }}><strong>{opt.total_cost.toLocaleString("vi-VN")} đ</strong></td>
                    <td className="tg__num tg__mono">{Math.round(opt.total_cost / opt.quantity).toLocaleString("vi-VN")} đ</td>
                    <td>
                      {opt.warnings_json && opt.warnings_json.length > 0 ? (() => {
                        const blocking = opt.warnings_json.filter(w => w.severity === "blocking_error").length;
                        const others = opt.warnings_json.length - blocking;
                        return (
                          <span className={`tg__badge ${blocking > 0 ? "tg__badge--error" : "tg__badge--warn"}`}>
                            {blocking > 0
                              ? `⛔ ${blocking} lỗi chặn${others > 0 ? ` · ${others} cảnh báo` : ""}`
                              : `⚠️ ${others} cảnh báo`}
                          </span>
                        );
                      })() : (
                        <span className="tg__muted">Không</span>
                      )}
                    </td>
                    <td>
                      {opt.can_create_quote ? (
                        <span style={{ color: "#0e9f6e" }}>🟢 Sẵn sàng</span>
                      ) : (
                        <span style={{ color: "#c81e1e" }}>🔴 Bị chặn (Thiếu cấu hình)</span>
                      )}
                    </td>
                    <td>
                      <Button
                        type="button"
                        variant="ghost"
                        className="tg__rowbtn"
                        title="Xem bảng phân rã chi phí của mức số lượng này"
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveQtyTab(idx);
                          breakdownRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                        }}
                      >
                        {activeQtyTab === idx ? "Đang xem ▾" : "Xem phân rã"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* Breakdown view of selected option */}
          {currentOption && (
            <div ref={breakdownRef} style={{ display: "flex", gap: "24px", alignItems: "flex-start", scrollMarginTop: "16px" }}>
              
              {/* Cost breakdown left panel */}
              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "24px" }}>
                <section className="tg__form-section">
                  <div className="tg__form-section-head">
                    <h3 className="tg__section-title">
                      Phân rã chi phí chi tiết (SL: {currentOption.quantity.toLocaleString("vi-VN")} sản phẩm)
                    </h3>
                  </div>

                  {currentOption.warnings_json && currentOption.warnings_json.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "16px" }}>
                      {currentOption.warnings_json.filter(w => w.severity === "blocking_error").length > 0 && (
                        <div className="tg__warning-alert tg__warning-alert--error" role="alert">
                          <p className="tg__warning-title">⚠️ Lỗi chặn tính toán (Cần xử lý để sẵn sàng báo giá):</p>
                          <ul className="tg__warning-list">
                            {currentOption.warnings_json.filter(w => w.severity === "blocking_error").map((w, idx) => (
                              <li key={idx}>
                                <strong>{w.code}:</strong> {w.message} 
                                {w.source_type && w.source_id && (
                                  <span style={{ marginLeft: "8px", textDecoration: "underline", fontStyle: "italic", fontSize: "11px" }}>
                                    (Master ID: {w.source_type} #{w.source_id})
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {currentOption.warnings_json.filter(w => w.severity === "warning").length > 0 && (
                        <div className="tg__warning-alert tg__warning-alert--warn" role="alert">
                          <p className="tg__warning-title">⚠️ Cảnh báo tính toán:</p>
                          <ul className="tg__warning-list">
                            {currentOption.warnings_json.filter(w => w.severity === "warning").map((w, idx) => (
                              <li key={idx}><strong>{w.code}:</strong> {w.message}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {currentOption.warnings_json.filter(w => w.severity === "info").length > 0 && (
                        <div className="tg__warning-alert" style={{ borderLeft: "3px solid #1c64f2", background: "#eef4ff" }}>
                          <p className="tg__warning-title" style={{ color: "#1a56db" }}>ℹ️ Ghi chú tính toán:</p>
                          <ul className="tg__warning-list">
                            {currentOption.warnings_json.filter(w => w.severity === "info").map((w, idx) => (
                              <li key={idx}>{w.message}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Box thông số sản xuất — trích từ calc snapshot của các dòng chi phí */}
                  {(() => {
                    const lines = currentOption.cost_lines ?? [];
                    const calcOf = (cat: string) => lines.find((l) => l.category === cat)?.calculation_snapshot_json ?? {};
                    const matCalc = calcOf("material");
                    const machCalc = calcOf("machine");
                    const inkCalc = calcOf("ink");
                    const plateCalc = calcOf("plate_die");
                    const opCalc = lines.find((l) => l.calculation_snapshot_json?.pieces_per_sheet)?.calculation_snapshot_json ?? {};

                    const facts: Array<[string, string]> = [];
                    if (plateCalc.imposition) facts.push(["Kiểu bình bài", String(plateCalc.imposition)]);
                    if (opCalc.pieces_per_sheet) facts.push(["Số con / tờ", `${opCalc.pieces_per_sheet} con`]);
                    if (matCalc.sheet_w && matCalc.sheet_h) facts.push(["Khổ giấy", `${matCalc.sheet_w}×${matCalc.sheet_h} cm`]);
                    if (matCalc.theoretical_sheets && matCalc.production_sheets && matCalc.purchase_sheets)
                      facts.push(["Số tờ (lý thuyết→SX→mua)", `${Number(matCalc.theoretical_sheets).toLocaleString("vi-VN")} → ${Number(matCalc.production_sheets).toLocaleString("vi-VN")} → ${Number(matCalc.purchase_sheets).toLocaleString("vi-VN")}`]);
                    else if (matCalc.total_sheets) facts.push(["Tổng tờ in (gồm hao)", `${Number(matCalc.total_sheets).toLocaleString("vi-VN")} tờ`]);
                    if (Number(matCalc.press_per_purchase) > 1) facts.push(["Cắt tờ in / tờ mua", String(matCalc.press_per_purchase)]);
                    if (matCalc.sides) facts.push(["Số mặt in", String(matCalc.sides)]);
                    if (inkCalc.impressions) facts.push(["Tổng lượt-màu", Number(inkCalc.impressions).toLocaleString("vi-VN")]);
                    if (machCalc.run_qty) facts.push(["Sản lượng chạy máy", Number(machCalc.run_qty).toLocaleString("vi-VN")]);
                    if (machCalc.machine_hours) facts.push(["Tổng giờ máy", formatHours(Number(machCalc.machine_hours))]);
                    if (facts.length === 0) return null;

                    return (
                      <div style={{ background: "var(--paper)", border: "1px solid var(--rule-soft)", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px" }}>
                        <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px", display: "block", marginBottom: "8px" }}>
                          ⚙ THÔNG SỐ SẢN XUẤT
                        </span>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "6px 20px" }}>
                          {facts.map(([label, value]) => (
                            <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "12.5px" }}>
                              <span className="tg__summary-label">{label}</span>
                              <span className="tg__mono" style={{ whiteSpace: "nowrap" }}>{value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}

                  <div className="tg__breakdown-table-wrap">
                    <table className="tg__breakdown-table">
                      <thead>
                        <tr>
                          <th>Hạng mục</th>
                          <th>Mô tả chi tiết công việc</th>
                          <th className="tg__num">Số lượng chạy</th>
                          <th>Đơn vị</th>
                          <th className="tg__num">Đơn giá chạy</th>
                          <th className="tg__num" title="Phí chuẩn bị/lên khuôn cố định cho mỗi lần chạy (setup)">Phí chuẩn bị</th>
                          <th className="tg__num" style={{ width: "220px", textAlign: "right" }}>Thành tiền</th>
                          <th style={{ width: "80px", textAlign: "right" }}>Diễn giải</th>
                        </tr>
                      </thead>
                      <tbody>
                        {currentOption.cost_lines && currentOption.cost_lines.length > 0 ? (
                          (() => {
                            // Nhóm dòng chi phí theo khu như phiếu tính giá nhà in
                            const SECTIONS: Array<[string, string[]]> = [
                              ["Nguyên vật liệu & mực", ["material", "ink", "click_ink"]],
                              ["Khuôn · bản kẽm", ["plate_die"]],
                              ["Chạy máy in", ["machine"]],
                              ["Gia công sau in", ["operation", "packing"]],
                              ["Phí phát sinh & thuê ngoài", ["outsource", "delivery", "other"]],
                            ];
                            const lines = currentOption.cost_lines;
                            const grouped = SECTIONS
                              .map(([title, cats]) => [title, lines.filter((l) => cats.includes(l.category))] as const)
                              .filter(([, ls]) => ls.length > 0);
                            const known = new Set(SECTIONS.flatMap(([, cats]) => cats));
                            const leftovers = lines.filter((l) => !known.has(l.category));

                            const renderLine = (line: (typeof lines)[number]) => {
                              const percent = currentOption.total_cost > 0
                                ? Math.round((line.total_cost / currentOption.total_cost) * 100)
                                : 0;
                              return (
                                <tr key={line.id} className={getCostCategoryClassName(line.category)}>
                                  <td>
                                    <strong>{getCostCategoryLabel(line.category)}</strong>
                                    {line.note?.includes("[SỬA TAY]") && (
                                      <span title={line.note} style={{ marginLeft: 6, fontSize: 11, color: "var(--rust)", fontWeight: 700 }}>✏️ sửa tay</span>
                                    )}
                                  </td>
                                  <td>{line.description}</td>
                                  <td className="tg__num">{line.quantity.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}</td>
                                  <td>{unitLabel(line.unit)}</td>
                                  <td className="tg__num" style={{ whiteSpace: "nowrap" }}>
                                    {line.unit_cost.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} đ/{unitLabel(line.unit)}
                                  </td>
                                  <td className="tg__num">{line.setup_cost.toLocaleString("vi-VN")} đ</td>
                                  <td className="tg__num">
                                    <div className="tg__cost-bar-container">
                                      <span className="tg__cost-percent-label">{percent}%</span>
                                      <div className="tg__cost-bar-wrap" title={`Chiếm ${percent}% tổng chi phí`}>
                                        <div className="tg__cost-bar" style={{ width: `${percent}%` }} />
                                      </div>
                                      <strong>{line.total_cost.toLocaleString("vi-VN")} đ</strong>
                                    </div>
                                  </td>
                                  <td style={{ textAlign: "right" }}>
                                    <button
                                      type="button"
                                      className="btn btn--ghost tg__rowbtn"
                                      onClick={() => setAuditLineId(line.id)}
                                      title="Xem cách tính + sửa tay số tiền dòng này"
                                    >
                                      Xem / Sửa tay
                                    </button>
                                  </td>
                                </tr>
                              );
                            };

                            return (
                              <>
                                {grouped.map(([title, ls]) => (
                                  <Fragment key={title}>
                                    <tr className="tgroup__head">
                                      <td colSpan={8}>{title}</td>
                                    </tr>
                                    {ls.map(renderLine)}
                                  </Fragment>
                                ))}
                                {leftovers.map(renderLine)}
                              </>
                            );
                          })()
                        ) : (
                          <tr>
                            <td colSpan={8} className="tg__muted" style={{ textAlign: "center", padding: "16px" }}>
                              Không có dữ liệu chi phí. Hãy kiểm tra lại cấu hình.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="tg__cost-summary" style={{ borderTop: "1px solid var(--rule)", paddingTop: "16px", marginTop: "16px" }}>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                      <span>Trạng thái chuyển Báo giá:</span>
                      {currentOption.can_create_quote ? (
                        <>
                          <span className="tg__badge tg__badge--ready" style={{ textTransform: "none", letterSpacing: 0 }}>
                            🟢 Sẵn sàng chuyển Báo giá
                          </span>
                          <span className="tg__muted" style={{ fontSize: "12px" }}>
                            — sang trang "Báo giá in ấn", tạo báo giá mới và chọn mã tính giá này
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="tg__badge tg__badge--error" style={{ textTransform: "none", letterSpacing: 0 }}>
                            🔴 Bị chặn chuyển Báo giá
                          </span>
                          <span className="tg__muted" style={{ fontSize: "12px" }}>
                            — xử lý các lỗi chặn ở trên rồi tính lại
                          </span>
                        </>
                      )}
                    </div>
                    <div>
                      <span style={{ fontSize: "16px" }}>Tổng giá vốn nội bộ đề xuất: </span>
                      <span className="tg__cost-total-amount" style={{ fontSize: "24px" }}>
                        {currentOption.total_cost.toLocaleString("vi-VN")} đ
                      </span>
                    </div>
                  </div>
                </section>
              </div>

              {/* Cost Audit Panel Right Side */}
              {auditLine && (
                <div className="tg__summary-panel" style={{ width: "320px", flex: "0 0 320px", position: "sticky", top: "24px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px", marginBottom: "12px" }}>
                    <h4 style={{ margin: 0, fontSize: "14px", fontWeight: "bold" }}>Diễn giải cách tính</h4>
                    <button type="button" className="tg__close" onClick={() => setAuditLineId(null)}>✕</button>
                  </div>

                  <div className="tg__summary-list" style={{ fontSize: "12px" }}>
                    <div className="tg__summary-item">
                      <span className="tg__summary-label">Hạng mục:</span>
                      <span className="tg__summary-value">{getCostCategoryLabel(auditLine.category)}</span>
                    </div>
                    <div className="tg__summary-item tg__form-wide">
                      <span className="tg__summary-label">Mô tả:</span>
                      <span className="tg__summary-value" style={{ textAlign: "right" }}>{auditLine.description}</span>
                    </div>

                    {(() => {
                      const computed = auditLine.quantity * auditLine.unit_cost + auditLine.setup_cost;
                      const inkRate = auditLine.category === "ink"
                        ? Number(
                            auditLine.source_snapshot_json?.unit_price ??
                            auditLine.source_snapshot_json?.ink_cost_per_1000_impressions ??
                            0
                          )
                        : 0;
                      return (
                        <div style={{ background: "#f8f4ec", border: "1px solid var(--rule-hair)", borderRadius: "6px", padding: "10px", margin: "10px 0", lineHeight: 1.7 }}>
                          <div style={{ fontWeight: "bold", fontSize: "11px", marginBottom: "4px" }}>THÀNH TIỀN TÍNH THẾ NÀO?</div>
                          {inkRate > 0 ? (
                            <div>
                              {auditLine.quantity.toLocaleString("vi-VN")} lượt-màu, mực tính theo khối 1.000 lượt (làm tròn lên):
                              <br />
                              <span className="tg__mono">
                                {Math.ceil(auditLine.quantity / 1000).toLocaleString("vi-VN")} khối × {inkRate.toLocaleString("vi-VN")} đ
                                {" = "}<strong>{auditLine.total_cost.toLocaleString("vi-VN")} đ</strong>
                              </span>
                            </div>
                          ) : (
                            <div>
                              <span className="tg__mono">
                                {auditLine.quantity.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} {unitLabel(auditLine.unit)}
                                {" × "}{auditLine.unit_cost.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} đ
                                {auditLine.setup_cost > 0 && <> + {auditLine.setup_cost.toLocaleString("vi-VN")} đ chuẩn bị</>}
                              </span>
                              {auditLine.min_charge_applied ? (
                                <div style={{ marginTop: "4px", color: "var(--rust)" }}>
                                  = {Math.round(computed).toLocaleString("vi-VN")} đ — thấp hơn phí tối thiểu đã cấu hình,
                                  nên áp mức sàn: <strong>{auditLine.total_cost.toLocaleString("vi-VN")} đ</strong>
                                </div>
                              ) : (
                                <div style={{ marginTop: "4px" }}>
                                  = <strong>{auditLine.total_cost.toLocaleString("vi-VN")} đ</strong>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {auditLine.source_type && (
                      <div className="tg__summary-item tg__form-wide">
                        <span className="tg__summary-label">Nguồn đơn giá:</span>
                        <span className="tg__summary-value" style={{ textAlign: "right" }}>
                          {SOURCE_TYPE_LABELS[auditLine.source_type] ?? auditLine.source_type}
                        </span>
                      </div>
                    )}

                    <div style={{ borderTop: "1px solid var(--rule-hair)", margin: "8px 0", paddingTop: "8px" }} />

                    <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px" }}>
                      CẤU HÌNH ÁP DỤNG
                      <span style={{ fontWeight: "normal", textTransform: "none" }}> (chốt lúc tính — đổi bảng giá sau không ảnh hưởng)</span>
                    </span>
                    {auditLine.source_snapshot_json ? (
                      Object.entries(auditLine.source_snapshot_json)
                        .filter(([key, val]) => !(val == null && key.startsWith("tooling_")))
                        .map(([key, val]) => (
                        <div className="tg__summary-item" key={key}>
                          <span className="tg__summary-label" style={{ fontSize: "11px" }} title={key}>{snapshotLabel(key)}</span>
                          <span className="tg__summary-value" style={{ fontSize: "11px" }}>{snapshotValue(key, val)}</span>
                        </div>
                      ))
                    ) : (
                      <span className="tg__muted">Không có dữ liệu.</span>
                    )}

                    <div style={{ borderTop: "1px solid var(--rule-hair)", margin: "8px 0", paddingTop: "8px" }} />

                    {/* Định mức & Bù hao áp dụng (mỗi bước nêu rule) — danh mục #7 */}
                    {Array.isArray(auditLine.calculation_snapshot_json?.norms_applied) &&
                      auditLine.calculation_snapshot_json.norms_applied.length > 0 && (
                        <div style={{ background: "#f8f4ec", border: "1px solid var(--rule-hair)", borderRadius: "6px", padding: "10px", margin: "6px 0" }}>
                          <div style={{ fontWeight: "bold", fontSize: "11px", marginBottom: "4px" }}>ĐỊNH MỨC & BÙ HAO ÁP DỤNG</div>
                          {auditLine.calculation_snapshot_json.norms_applied.map((n: { label: string; detail: string; rule: string | null; norm_id?: number | null }, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "11px", padding: "1px 0" }}>
                              <span>{n.label}: <span className="tg__mono">{n.detail}</span></span>
                              <span style={{ display: "flex", gap: "8px", whiteSpace: "nowrap", alignItems: "center" }}>
                                {n.rule && <span className="tg__muted">{n.rule}</span>}
                                {n.norm_id != null && <NormRuleLink normId={n.norm_id} token={token} />}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                    <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px" }}>CÁC BƯỚC TÍNH TOÁN</span>
                    {auditLine.calculation_snapshot_json ? (
                      Object.entries(auditLine.calculation_snapshot_json)
                        .filter(([key]) => key !== "norms_applied")
                        .map(([key, val]) => (
                        <div className="tg__summary-item" key={key}>
                          <span className="tg__summary-label" style={{ fontSize: "11px" }} title={key}>{snapshotLabel(key)}</span>
                          <span className="tg__summary-value" style={{ fontSize: "11px", textAlign: "right" }}>{snapshotValue(key, val)}</span>
                        </div>
                      ))
                    ) : (
                      <span className="tg__muted">Không có dữ liệu.</span>
                    )}
                  </div>
                  <OverrideSection
                    line={auditLine}
                    overrides={overrides}
                    setOverrides={setOverrides}
                    onDone={() => setAuditLineId(null)}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </main>
  );
}

// --- "Xem quy tắc" — popover chi tiết một định mức (danh mục #7), fetch theo id ---
const NORM_GROUP_LABEL: Record<string, string> = {
  YIELD_RATE: "Tỷ lệ đạt",
  SETUP_WASTE: "Bù hao setup",
  RUNNING_WASTE: "Bù hao chạy máy",
  PAPER_EXTRA_WASTE: "Hao giấy riêng",
};

function normFormula(n: NormRow): string {
  const g = n.waste_group;
  if (g === "YIELD_RATE") return `Đạt ${(n.value * 100).toFixed(1)}%`;
  if (g === "RUNNING_WASTE") return `${(n.value * 100).toFixed(2)}% số tờ`;
  if (g === "SETUP_WASTE") {
    if (n.calculation_method === "PER_COLOR_SIDE" || (!n.setup_waste_qty && !n.setup_waste_per_color && !n.setup_waste_per_side))
      return `${n.value} tờ/màu-mặt`;
    const parts: string[] = [];
    if (n.setup_waste_qty) parts.push(`${n.setup_waste_qty}`);
    if (n.setup_waste_per_color) parts.push(`${n.setup_waste_per_color}×màu`);
    if (n.setup_waste_per_side) parts.push(`${n.setup_waste_per_side}×mặt`);
    return parts.length ? `${parts.join(" + ")} tờ` : "0";
  }
  if (g === "PAPER_EXTRA_WASTE") {
    if (n.calculation_method === "FIXED") return `${n.value} tờ`;
    if (n.calculation_method === "PER_REAM") return `${n.value} tờ/ram`;
    return `${(n.value * 100).toFixed(2)}% tờ mua`;
  }
  return String(n.value);
}

function NormDetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px" }}>
      <span className="tg__muted">{label}</span>
      <span style={{ textAlign: "right" }}>{value}</span>
    </div>
  );
}

function NormRuleLink({ normId, token }: { normId: number; token: string | null }) {
  const [open, setOpen] = useState(false);
  const [norm, setNorm] = useState<NormRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function openRule() {
    setOpen(true);
    if (norm || !token) return;
    setLoading(true);
    setErr(null);
    try {
      setNorm(await api.norms.get(token, normId));
    } catch {
      setErr("Không tải được quy tắc định mức.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={openRule}
        style={{ background: "none", border: "none", padding: 0, font: "inherit", color: "var(--rust-deep, #9a3412)", cursor: "pointer", textDecoration: "underline dotted" }}
      >
        Xem quy tắc
      </button>
      {open && (
        <div className="tg__overlay" role="dialog" aria-modal="true" aria-label="Quy tắc định mức" onClick={() => setOpen(false)}>
          <div className="tg__dialog tg__dialog--sm card" onClick={(e) => e.stopPropagation()}>
            <div className="tg__dialog-head">
              <h2>Quy tắc định mức</h2>
              <button type="button" className="tg__close" aria-label="Đóng" onClick={() => setOpen(false)}>✕</button>
            </div>
            <div className="tg__dialog-body">
              {loading ? (
                <p className="tg__muted">Đang tải…</p>
              ) : err ? (
                <p className="tg__muted">{err}</p>
              ) : norm ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "13px" }}>
                  <div><strong>{norm.name || norm.norm_key}</strong>{norm.code && <span className="tg__mono tg__muted"> · {norm.code}</span>}</div>
                  <NormDetailRow label="Nhóm" value={norm.waste_group ? NORM_GROUP_LABEL[norm.waste_group] ?? norm.waste_group : "Đơn giá"} />
                  <NormDetailRow label="Mức hao / Công thức" value={normFormula(norm)} />
                  <NormDetailRow label="Hiệu lực" value={`${norm.effective_from}${norm.effective_to ? ` → ${norm.effective_to}` : " → nay"}${norm.version > 1 ? ` (v${norm.version})` : ""}`} />
                  <NormDetailRow label="Ưu tiên" value={String(norm.priority)} />
                  {norm.note && <NormDetailRow label="Ghi chú" value={norm.note} />}
                  <p className="tg__muted" style={{ fontSize: "11px", marginTop: "4px" }}>
                    Đây là bản định mức đã chốt lúc tính giá. Sửa định mức về sau sẽ tạo phiên bản mới, không đổi phiếu này.
                  </p>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function OverrideSection({ line, overrides, setOverrides, onDone }: {
  line: { category: string; total_cost: number };
  overrides: Array<{ target: string; value: number; reason: string }>;
  setOverrides: (o: Array<{ target: string; value: number; reason: string }>) => void;
  onDone: () => void;
}) {
  const target = `line:${line.category}`;
  const existing = overrides.find((o) => o.target === target);
  const [value, setValue] = useState(existing ? String(existing.value) : String(Math.round(line.total_cost)));
  const [reason, setReason] = useState(existing?.reason ?? "");
  const [err, setErr] = useState<string | null>(null);

  const apply = () => {
    const v = Number(value);
    if (!Number.isFinite(v) || v < 0) return setErr("Số tiền sửa tay phải ≥ 0.");
    if (!reason.trim()) return setErr("Phải nhập lý do sửa tay.");
    setOverrides([...overrides.filter((o) => o.target !== target), { target, value: v, reason: reason.trim() }]);
    onDone();
  };
  const clear = () => {
    setOverrides(overrides.filter((o) => o.target !== target));
    onDone();
  };

  return (
    <div style={{ marginTop: 14, borderTop: "1px solid var(--rule-hair)", paddingTop: 12 }}>
      <div className="tg__summary-label" style={{ fontWeight: "bold", marginBottom: 8 }}>✏️ Sửa tay số tiền dòng này (§12)</div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="field" style={{ flex: "0 0 160px" }}>
          <span className="field__label">Số tiền (đ)</span>
          <input className="input" type="number" min="0" value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <label className="field" style={{ flex: "1 1 240px" }}>
          <span className="field__label">Lý do (bắt buộc)</span>
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="VD: chốt giá NCC thực tế" />
        </label>
      </div>
      {err && <div className="banner banner--error" style={{ marginTop: 8 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button type="button" className="btn btn--primary" onClick={apply}>Áp dụng sửa tay</button>
        {existing && <button type="button" className="btn btn--ghost" onClick={clear}>Bỏ sửa tay</button>}
      </div>
      <p className="tg__muted" style={{ marginTop: 6, fontSize: 12 }}>
        Áp dụng xong bấm <strong>Lưu / Tính lại</strong> để giá vốn cập nhật. Giá gốc + lý do được lưu vào snapshot.
      </p>
    </div>
  );
}

// --- Dynamic components ---

function QuantityChipInput({
  value,
  onChange,
  onError,
}: {
  value: number[];
  onChange: (val: number[]) => void;
  onError: (err: string | null) => void;
}) {
  const [inputVal, setInputVal] = useState("");

  const parseAndAdd = (rawStr: string) => {
    if (!rawStr.trim()) return;
    const parts = rawStr.split(/[\s,]+/);
    const parsed: number[] = [];
    let hasErr = false;
    for (const p of parts) {
      const clean = p.replace(/\./g, "").trim();
      if (!clean) continue;
      const num = Number(clean);
      if (!Number.isInteger(num) || num <= 0) {
        onError(`Số lượng "${p}" không hợp lệ (phải là số nguyên dương).`);
        hasErr = true;
        continue;
      }
      parsed.push(num);
    }
    if (parsed.length > 0 && !hasErr) {
      onError(null);
      const combined = [...value, ...parsed];
      const uniqueSorted = Array.from(new Set(combined)).sort((a, b) => a - b);
      onChange(uniqueSorted);
      setInputVal("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      parseAndAdd(inputVal);
    }
  };

  const handleRemove = (num: number) => {
    onChange(value.filter((n) => n !== num));
  };

  return (
    <div className="tg__chip-input-container">
      <div className="tg__chip-input-field">
        <input
          className="input"
          style={{ flex: 1 }}
          placeholder="Nhập số lượng (vd: 500, 1000) rồi nhấn Enter..."
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => parseAndAdd(inputVal)}
        />
        <Button type="button" variant="ghost" onClick={() => parseAndAdd(inputVal)}>
          Thêm
        </Button>
      </div>
      <div className="tg__qty-chips">
        {value.map((num) => (
          <span key={num} className="tg__qty-chip">
            {num.toLocaleString("vi-VN")}
            <button type="button" className="tg__qty-chip-remove" onClick={() => handleRemove(num)}>
              ✕
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

// --- Sort helper btn ---
function SortBtn({
  label,
  col,
  sort,
  onSort,
}: {
  label: string;
  col: string;
  sort: string;
  onSort: (val: string) => void;
}) {
  const active = sort === col || sort === `-${col}`;
  const isDesc = sort === `-${col}`;

  function onClick() {
    if (sort === col) {
      onSort(`-${col}`);
    } else {
      onSort(col);
    }
  }

  return (
    <button
      type="button"
      className={`tg__sortbtn${active ? " is-active" : ""}`}
      onClick={onClick}
    >
      {label} {active ? (isDesc ? "↓" : "↑") : ""}
    </button>
  );
}

// --- Delete confirm dialog ---
function ConfirmDeleteDialog({
  costing,
  onCancel,
  onConfirm,
}: {
  costing: EstimateRow;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="tg__overlay" role="dialog" aria-modal="true" aria-label="Xoá phương án">
      <div className="tg__dialog tg__dialog--sm card">
        <div className="tg__dialog-head">
          <h2>Xoá phương án tính giá</h2>
          <button type="button" className="tg__close" aria-label="Đóng" onClick={onCancel}>
            ✕
          </button>
        </div>
        <div className="tg__dialog-body">
          <p>
            Xoá phương án <strong>{costing.estimate_number}</strong>? Tất cả kết quả tính toán chi tiết kèm theo sẽ bị xoá vĩnh viễn. Hành động không thể hoàn tác.
          </p>
          <div className="tg__dialog-actions">
            <Button type="button" variant="ghost" onClick={onCancel}>
              Huỷ
            </Button>
            <Button
              type="button"
              variant="primary"
              loading={busy}
              onClick={() => {
                setBusy(true);
                onConfirm();
              }}
            >
              Xoá
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
