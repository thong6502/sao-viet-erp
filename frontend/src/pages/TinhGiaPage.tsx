import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type EstimateRow,
  type EstimateDetail,
  type EstimateInput,
  type CustomerRow,
  type MaterialRow,
  type MachineRow,
  type OperationCatalogRow,
  type ProductTypeCatalogRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
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

export function TinhGiaPage() {
  const { token } = useAuth();

  // List States
  const [rows, setRows] = useState<EstimateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("code");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [productTypeFilter, setProductTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  // Catalogs
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [productTypes, setProductTypes] = useState<ProductTypeCatalogRow[]>([]);
  const [materials, setMaterials] = useState<MaterialRow[]>([]);
  const [machines, setMachines] = useState<MachineRow[]>([]);
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

  // Form Fields States
  const [customerId, setCustomerId] = useState<number | null>(null);
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

  // Machine
  const [machineId, setMachineId] = useState<number | null>(null);

  // Chosen operations
  const [operations, setOperations] = useState<OpForm[]>([]);
  // Custom charges
  const [customCosts, setCustomCosts] = useState<CustomCostForm[]>([]);

  // Suggest geometric pieces
  const [suggestedPieces, setSuggestedPieces] = useState<number | null>(null);

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

    const status_query = statusFilter === "ready" ? "calculated" : statusFilter;

    api.estimates
      .list(token, {
        q: q.trim() || undefined,
        product_type: productTypeFilter || undefined,
        status: status_query || null,
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
  }, [token, q, statusFilter, productTypeFilter, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

  // Load Catalogs on mount
  useEffect(() => {
    if (!token) return;
    
    api.customers.list(token, { page: 1, size: 200 })
      .then(res => setCustomers(res.items))
      .catch(() => setCustomers([]));

    api.productTypesCatalog.list(token, { page: 1, size: 100 })
      .then(res => setProductTypes(res.items))
      .catch(() => setProductTypes([]));

    api.materials.list(token, { page: 1, size: 200 })
      .then(res => setMaterials(res.items))
      .catch(() => setMaterials([]));

    api.machines.list(token, { page: 1, size: 200 })
      .then(res => setMachines(res.items))
      .catch(() => setMachines([]));

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
    api.costings.suggestPieces(token, {
      sheet_w: mat.width_cm,
      sheet_h: mat.height_cm,
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
  }, [token, materialId, finishedWidth, finishedHeight, boxLength, boxWidth, largeWidth, largeHeight, grainLocked, gripperCm, edgeTrimCm, bleedCm, gutterCm, productType, overridePieces, materials]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  // Open Form for Create
  function openCreate() {
    setEditing(null);
    setCustomerId(null);
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
      setCustomerId(detail.customer_id);
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
      
      // Clear machine/ops since catalog rules change
      setMachineId(null);
      setOperations([]);
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
    const input_spec = {
      product_id: null,
      finished_width: finishedWidth ? Number(finishedWidth) : null,
      finished_height: finishedHeight ? Number(finishedHeight) : null,
      colors: Number(colors),
      sides: Number(sides),
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
      override_pieces: overridePieces,
      pieces_per_sheet: finalPieces,
      sheet_w: mat?.width_cm || 0,
      sheet_h: mat?.height_cm || 0,
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
      customer_id: customerId,
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

  // Calculated KPI details for list page
  const calculatedCount = rows.filter((r) => r.status === "calculated").length;
  const errorCount = rows.filter((r) => r.blocking_error_count > 0).length;

  function renderProductSpecFields() {
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
            <label className="field">
              <span className="field__label">Số mặt in *</span>
              <select className="input" value={sides} onChange={e => setSides(Number(e.target.value))}>
                <option value={1}>In 1 mặt (4/0 hoặc 1/0)</option>
                <option value={2}>In 2 mặt (4/4 hoặc 1/1)</option>
              </select>
            </label>
            <label className="field">
              <span className="field__label">Số màu in *</span>
              <input className="input" type="number" min="1" max="10" value={colors} onChange={e => setColors(Number(e.target.value))} />
            </label>
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
            <label className="field">
              <span className="field__label">Tổng số trang (ruột + bìa) *</span>
              <input className="input" type="number" min="4" step="4" value={pageCount} onChange={e => setPageCount(e.target.value)} />
              <span className="tg__suggest">Phải là số chia hết cho 4 (tay sách).</span>
            </label>
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
            <label className="field">
              <span className="field__label">Số màu in *</span>
              <input className="input" type="number" min="1" max="10" value={colors} onChange={e => setColors(Number(e.target.value))} />
            </label>
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

        {/* KPI Cards section */}
        <div className="tg__kpis">
          <div className="tg__kpi-card tg__kpi-card--total">
            <div className="tg__kpi-info">
              <span className="tg__kpi-label">Tổng phương án</span>
              <span className="tg__kpi-value">{total}</span>
            </div>
            <div className="tg__kpi-icon-wrap">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            </div>
          </div>
          
          <div className="tg__kpi-card tg__kpi-card--ready">
            <div className="tg__kpi-info">
              <span className="tg__kpi-label">Đã tính thành công</span>
              <span className="tg__kpi-value">{calculatedCount}</span>
            </div>
            <div className="tg__kpi-icon-wrap">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            </div>
          </div>
          
          <div className="tg__kpi-card tg__kpi-card--warning">
            <div className="tg__kpi-info">
              <span className="tg__kpi-label">Lỗi chặn định mức</span>
              <span className="tg__kpi-value">{errorCount}</span>
            </div>
            <div className="tg__kpi-icon-wrap">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            </div>
          </div>
        </div>

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
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Lọc trạng thái"
          >
            <option value="">Tất cả trạng thái</option>
            <option value="draft">Nháp</option>
            <option value="ready">Đã tính toán</option>
          </select>

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

        <div className="card tg__tablewrap">
          <table className="tg__table">
            <thead>
              <tr>
                <th>
                  <SortBtn label="Mã TG" col="code" sort={sort} onSort={setSort} />
                </th>
                <th>Khách hàng</th>
                <th>Sản phẩm</th>
                <th>Loại SP</th>
                <th className="tg__num">Số lượng</th>
                <th className="tg__num">Lỗi/Cảnh báo</th>
                <th className="tg__num">Giá vốn tổng</th>
                <th>Trạng thái</th>
                <th className="tg__actions-col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} className="tg__status" role="status">Đang tải…</td>
                </tr>
              ) : listError ? (
                <tr>
                  <td colSpan={9} className="tg__status">
                    <div className="banner banner--error" role="alert">
                      <span>{listError}</span>
                      <button type="button" className="btn btn--ghost" onClick={() => load()}>Thử lại</button>
                    </div>
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="tg__empty">
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

                  const resolvedCust = customers.find(cust => cust.id === (c as any).customer_id);

                  return (
                    <tr key={c.id} className="tg__row" onClick={() => openEdit(c)}>
                      <td className="tg__mono">{c.estimate_number}</td>
                      <td>{resolvedCust?.name ?? <span className="tg__muted">Khách vãng lai</span>}</td>
                      <td><strong>{c.product_name}</strong></td>
                      <td>{productTypes.find(p => p.product_type === c.product_type)?.name ?? c.product_type}</td>
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
                      <td className="tg__num tg__mono"><strong>{minMaxCost}</strong></td>
                      <td>
                        <span className={`tg__badge ${badgeClass}`}>
                          {c.status === "calculated" ? "Đã tính" : c.status === "draft" ? "Nháp" : c.status}
                        </span>
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
        <div style={{ display: "flex", gap: "8px" }}>
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
            Kết quả tính giá & Breakdown {!editing && "(chưa tính)"}
          </button>
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
                  <span className="field__label">Khách hàng</span>
                  <select
                    className="input"
                    value={customerId || ""}
                    onChange={(e) => setCustomerId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Chọn khách hàng (Không bắt buộc)...</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.code})
                      </option>
                    ))}
                  </select>
                </label>

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
                    value="Người phụ trách hiện tại"
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

                <div className="field tg__check tg__form-wide" style={{ marginTop: "8px" }}>
                  <input
                    type="checkbox"
                    checked={overridePieces}
                    onChange={(e) => setOverridePieces(e.target.checked)}
                  />
                  <span>Tự nhập số con trên khổ giấy (Không dùng thuật toán hình học tự động)</span>
                </div>

                {overridePieces ? (
                  <label className="field">
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
                  <div className="field">
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

                <div className="field tg__check">
                  <input
                    type="checkbox"
                    checked={grainLocked}
                    onChange={(e) => setGrainLocked(e.target.checked)}
                  />
                  <span>Ràng buộc thớ giấy (Grain locked - bỏ nhánh quay giấy)</span>
                </div>

                {/* #4 — tham số bình bản (tùy chọn) tinh chỉnh gợi ý số con/khổ */}
                <div className="tg__form-grid" style={{ marginTop: "12px" }}>
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
                        {m.name} ({m.code}) - {m.process_type === "offset" ? "Offset" : m.process_type === "digital" ? "Kỹ thuật số" : "Khổ lớn"}
                      </option>
                    ))}
                  </select>
                </label>

                {machineId !== null && (() => {
                  const m = machines.find(mac => mac.id === machineId);
                  return (
                    <div className="field tg__form-wide" style={{ background: "rgba(20,19,15,0.03)", padding: "10px", borderRadius: "4px" }}>
                      <span className="tg__suggest" style={{ display: "block" }}>
                        Khổ in tối đa: <strong>{m?.max_width_cm} x {m?.max_height_cm} cm</strong>. 
                        Đơn vị tốc độ: <strong>{m?.speed_unit}</strong>.
                      </span>
                      {m?.process_type === "offset" && (
                        <span className="tg__suggest" style={{ display: "block", marginTop: "4px", color: "var(--rust)" }}>
                          💡 <strong>Offset Preview:</strong> Tổng kẽm in dự kiến = {colors} màu x {sides} mặt x {forms} khuôn = <strong>{colors * sides * forms} bản kẽm</strong>.
                        </span>
                      )}
                      {m?.process_type === "digital" && (
                        <span className="tg__suggest" style={{ display: "block", marginTop: "4px", color: "var(--rust)" }}>
                          💡 <strong>Digital Preview:</strong> Click charge sẽ tự động tra cứu click màu/đen trắng dựa trên loại mực in.
                        </span>
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

              {editing && editing.options && editing.options.length > 0 && (
                <div style={{ background: "rgba(20,19,15,0.03)", padding: "10px", borderRadius: "6px", marginBottom: "16px" }}>
                  <span className="tg__summary-label" style={{ fontSize: "12px", display: "block" }}>KHOẢNG GIÁ VỐN ĐỀ XUẤT</span>
                  <strong style={{ fontSize: "18px", color: "var(--rust)", display: "block", marginTop: "4px" }}>
                    {editing.options.length === 1
                      ? `${editing.options[0].total_cost.toLocaleString("vi-VN")} đ`
                      : `${Math.min(...editing.options.map(o => o.total_cost)).toLocaleString("vi-VN")} - ${Math.max(...editing.options.map(o => o.total_cost)).toLocaleString("vi-VN")} đ`
                    }
                  </strong>
                </div>
              )}

              {formError && (
                <div className="banner banner--error" role="alert" style={{ marginBottom: "16px", fontSize: "12px" }}>
                  {formError}
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <Button type="button" variant="primary" loading={saving} onClick={() => handleSave("calculated")} style={{ width: "100%" }}>
                  🚀 Tính giá & Lưu kết quả
                </Button>
                <Button type="button" variant="ghost" loading={saving} onClick={() => handleSave("draft")} style={{ width: "100%" }}>
                  💾 Lưu bản nháp (Draft)
                </Button>
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
                      {opt.warnings_json && opt.warnings_json.length > 0 ? (
                        <span className={`tg__badge ${opt.warnings_json.some(w => w.severity === "blocking_error") ? "tg__badge--error" : "tg__badge--warn"}`}>
                          ⚠️ {opt.warnings_json.length} lỗi/cb
                        </span>
                      ) : (
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
                      <Button type="button" variant="ghost" className="tg__rowbtn" onClick={(e) => { e.stopPropagation(); setActiveQtyTab(idx); }}>
                        Xem Breakdown
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* Breakdown view of selected option */}
          {currentOption && (
            <div style={{ display: "flex", gap: "24px", alignItems: "flex-start" }}>
              
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
                    </div>
                  )}

                  <div className="tg__breakdown-table-wrap">
                    <table className="tg__breakdown-table">
                      <thead>
                        <tr>
                          <th>Hạng mục</th>
                          <th>Mô tả chi tiết công việc</th>
                          <th className="tg__num">Số lượng chạy</th>
                          <th>Đơn vị</th>
                          <th className="tg__num">Đơn giá chạy</th>
                          <th className="tg__num">Setup cố định</th>
                          <th className="tg__num" style={{ width: "220px", textAlign: "right" }}>Thành tiền</th>
                          <th style={{ width: "80px", textAlign: "right" }}>Audit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {currentOption.cost_lines && currentOption.cost_lines.length > 0 ? (
                          currentOption.cost_lines.map((line) => {
                            const percent = currentOption.total_cost > 0
                              ? Math.round((line.total_cost / currentOption.total_cost) * 100)
                              : 0;

                            return (
                              <tr key={line.id} className={getCostCategoryClassName(line.category)}>
                                <td><strong>{getCostCategoryLabel(line.category)}</strong></td>
                                <td>{line.description}</td>
                                <td className="tg__num">{line.quantity.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}</td>
                                <td>{line.unit}</td>
                                <td className="tg__num">{line.unit_cost.toLocaleString("vi-VN")} đ</td>
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
                                    title="Xem công thức chi tiết"
                                  >
                                    Chi tiết
                                  </button>
                                </td>
                              </tr>
                            );
                          })
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
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <span>Trạng thái chuyển Báo giá:</span>
                      {currentOption.can_create_quote ? (
                        <span className="tg__badge tg__badge--ready" style={{ textTransform: "none", letterSpacing: 0 }}>
                          🟢 Sẵn sàng chuyển Báo giá (Phase 2C)
                        </span>
                      ) : (
                        <span className="tg__badge tg__badge--error" style={{ textTransform: "none", letterSpacing: 0 }}>
                          🔴 Bị chặn chuyển Báo giá
                        </span>
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
                <div className="tg__summary-panel" style={{ width: "320px", position: "sticky", top: "24px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--rule-hair)", paddingBottom: "8px", marginBottom: "12px" }}>
                    <h4 style={{ margin: 0, fontSize: "14px", fontWeight: "bold" }}>Audit công thức tính</h4>
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
                    <div className="tg__summary-item">
                      <span className="tg__summary-label">Đơn vị:</span>
                      <span className="tg__summary-value">{auditLine.unit}</span>
                    </div>
                    
                    <div style={{ borderTop: "1px solid var(--rule-hair)", margin: "8px 0", paddingTop: "8px" }} />
                    
                    <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px" }}>SNAPSHOT CẤU HÌNH</span>
                    {auditLine.source_snapshot_json ? (
                      Object.entries(auditLine.source_snapshot_json).map(([key, val]) => (
                        <div className="tg__summary-item" key={key}>
                          <span className="tg__summary-label tg__mono" style={{ fontSize: "11px" }}>{key}</span>
                          <span className="tg__summary-value" style={{ fontSize: "11px" }}>{JSON.stringify(val)}</span>
                        </div>
                      ))
                    ) : (
                      <span className="tg__muted">Không có snapshot.</span>
                    )}

                    <div style={{ borderTop: "1px solid var(--rule-hair)", margin: "8px 0", paddingTop: "8px" }} />
                    
                    <span className="tg__summary-label" style={{ fontWeight: "bold", fontSize: "11px" }}>BƯỚC CHI TIẾT TÍNH TOÁN</span>
                    {auditLine.calculation_snapshot_json ? (
                      Object.entries(auditLine.calculation_snapshot_json).map(([key, val]) => (
                        <div className="tg__summary-item" key={key} style={{ flexDirection: "column", alignItems: "flex-start", gap: "2px" }}>
                          <span className="tg__summary-label tg__mono" style={{ fontSize: "11px", color: "var(--rust)" }}>{key}:</span>
                          <span className="tg__summary-value" style={{ fontSize: "11px", wordBreak: "break-all", whiteSpace: "normal" }}>
                            {typeof val === "object" ? JSON.stringify(val) : String(val)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <span className="tg__muted">Không có snapshot tính toán.</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </main>
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
