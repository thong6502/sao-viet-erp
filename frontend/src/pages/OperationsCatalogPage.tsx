import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type OperationCatalogRow,
  type OperationCatalogInput,
  type OperationCatalogRateInput,
  type OperationCatalogRateRow,
  type OperationPreviewInput,
  type OperationPreviewResult,
  type PlateDieRateRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./master-data.css";

const PAGE_SIZE = 10;

// Bộ công đoạn thành phẩm theo domain §5 (thêm bồi/ép kim/dập nổi/UV/dán hộp/xén; trước thiếu dan_hop
// dù seed dùng nó cho hộp/túi → hiển thị raw).
const OP_TYPES = [
  { value: "in", label: "In ấn (Printing)" },
  { value: "can_mang", label: "Cán màng (Lamination)" },
  { value: "be", label: "Bế hình / Đột (Die-cutting)" },
  { value: "boi", label: "Bồi (Mounting)" },
  { value: "ep_kim", label: "Ép kim / Nhũ (Foil stamping)" },
  { value: "dap_noi", label: "Dập nổi / chìm (Emboss)" },
  { value: "uv", label: "UV định hình (Spot UV)" },
  { value: "gap", label: "Gấp nếp / Cấn (Folding)" },
  { value: "dong_cuon", label: "Đóng cuốn (Binding)" },
  { value: "dan_hop", label: "Dán hộp (Box gluing)" },
  { value: "xen", label: "Xén (Trimming)" },
  { value: "dong_goi", label: "Đóng gói (Packaging)" },
  { value: "other", label: "Gia công khác" },
];

// §2.2 — cơ sở tính lượng (engine nhân run_rate) & hình thức tính công (mục 14).
const BASIS_QTY = [
  { value: "m2", label: "m² (diện tích)" },
  { value: "to", label: "Tờ in" },
  { value: "luot", label: "Lượt" },
  { value: "cm2", label: "cm² (ép)" },
  { value: "cuon", label: "Cuốn" },
  { value: "cai", label: "Cái" },
  { value: "thung", label: "Thùng" },
  { value: "kg", label: "Kg" },
];

// spec §D — hình thức tính nhân công (labor). "none" = không tách nhân công riêng.
const PRICING_METHOD = [
  { value: "theo_sp", label: "Theo sản phẩm" },
  { value: "theo_gio", label: "Theo giờ" },
  { value: "theo_ca", label: "Theo ca" },
  { value: "khoan", label: "Khoán" },
  { value: "none", label: "Không tính nhân công riêng" },
];

// spec §A — nhóm & loại xử lý
const PROCESS_GROUP = [
  { value: "sau_in", label: "Sau in" },
  { value: "dong_goi", label: "Đóng gói" },
  { value: "dac_biet", label: "Gia công đặc biệt" },
];

const PROCESS_TYPE = [
  { value: "internal", label: "Nội bộ" },
  { value: "outsource", label: "Thuê ngoài" },
  { value: "both", label: "Cả hai" },
];

// spec §C — cách tính chi phí nội bộ
const INTERNAL_METHOD = [
  { value: "per_qty", label: "Theo sản lượng (lượng × đơn giá)" },
  { value: "per_hour", label: "Theo giờ máy ((setup + lượng/tốc độ) × giá giờ)" },
  { value: "combined", label: "Kết hợp (setup + giờ máy + sản lượng)" },
];

// spec §B — công thức lượng tính giá
const QTY_FORMULA = [
  { value: "print_sheet_qty", label: "Theo số tờ in (PRINT_SHEET_QTY)" },
  { value: "finished_qty", label: "Theo thành phẩm (FINISHED_QTY)" },
  { value: "area_m2", label: "Theo diện tích (AREA_M2)" },
  { value: "linear_meter", label: "Theo mét dài (LINEAR_METER)" },
  { value: "book_qty", label: "Theo số cuốn (BOOK_QTY)" },
  { value: "box_qty", label: "Theo số hộp (BOX_QTY)" },
  { value: "pack_qty", label: "Theo số thùng (PACK_QTY)" },
  { value: "manual", label: "Nhập tay (MANUAL)" },
];

// spec §F — loại khuôn
const TOOLING_TYPE = [
  { value: "khuon_be", label: "Khuôn bế" },
  { value: "khuon_ep_kim", label: "Khuôn ép kim" },
  { value: "khuon_dap_noi", label: "Khuôn dập nổi" },
  { value: "other", label: "Khuôn khác" },
];

const OP_TABS = [
  { key: "general", label: "Thông tin chung" },
  { key: "quantity", label: "Lượng tính giá" },
  { key: "internal", label: "Giá nội bộ" },
  { key: "labor", label: "Nhân công" },
  { key: "outsource", label: "Thuê ngoài" },
  { key: "tooling", label: "Khuôn & hao hụt" },
] as const;
type OpTabKey = (typeof OP_TABS)[number]["key"];

export function OperationsCatalogPage() {
  const { token } = useAuth();

  const [rows, setRows] = useState<OperationCatalogRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sort] = useState("code");
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit" | "rates">(null);
  const [selected, setSelected] = useState<OperationCatalogRow | null>(null);
  const [deleting, setDeleting] = useState<OperationCatalogRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.operations
      .list(token, {
        q: q.trim() || undefined,
        operation_type: typeFilter || null,
        sort,
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh mục công đoạn.");
      })
      .finally(() => setLoading(false));
  }, [token, q, typeFilter, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    load();
  }

  async function handleDelete() {
    if (!token || !deleting) return;
    try {
      await api.operations.remove(token, deleting.id);
      setDeleting(null);
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được công đoạn.");
      setDeleting(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Công đoạn gia công (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Cấu hình danh mục</p>
        <h1 className="md-page__title">Công đoạn & Đơn giá gia công</h1>
        <p className="md-page__sub">
          Quản lý toàn bộ danh mục công đoạn thành phẩm (cán màng, cấn gấp, bế, đóng cuốn, đóng gói...) và biểu giá.
        </p>
      </header>

      <div className="md-page__toolbar">
        <form className="md-page__search" onSubmit={onSearch}>
          <input
            className="input"
            placeholder="Tìm theo tên / mã công đoạn..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button type="submit" variant="ghost">Tìm</Button>
        </form>

        <select
          className="input md-page__filter"
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
        >
          <option value="">Tất cả loại công đoạn</option>
          {OP_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <div className="md-page__toolbar-spacer" />
        <Button
          variant="primary"
          onClick={() => { setSelected(null); setMode("create"); }}
        >
          + Tạo công đoạn mới
        </Button>
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã công đoạn</th>
              <th>Tên công đoạn</th>
              <th>Loại gia công</th>
              <th>Đơn vị tính</th>
              <th>Cơ sở tính</th>
              <th>Hình thức NC</th>
              <th>Gia công ngoài (Outsource)</th>
              <th>Đơn giá chạy</th>
              <th>Phí tối thiểu (Min charge)</th>
              <th>Trạng thái</th>
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={11} className="md-page__status">Đang tải dữ liệu...</td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={11} className="md-page__empty">Không tìm thấy công đoạn nào.</td>
              </tr>
            ) : (
              rows.map((row) => {
                const activeRate = row.rates.find((r) => r.effective_to === null);
                return (
                  <tr key={row.id} className="md-page__row" onClick={() => { setSelected(row); setMode("edit"); }}>
                    <td className="md-page__mono">{row.code}</td>
                    <td><strong>{row.name}</strong></td>
                    <td>{OP_TYPES.find((t) => t.value === row.operation_type)?.label ?? row.operation_type}</td>
                    <td>{row.unit}</td>
                    <td>
                      <span className="md-page__tag">
                        {BASIS_QTY.find((b) => b.value === row.basis_quantity)?.label ?? row.basis_quantity}
                      </span>
                    </td>
                    <td>
                      <span className="md-page__tag-calc">
                        {PRICING_METHOD.find((p) => p.value === row.pricing_method)?.label ?? row.pricing_method}
                      </span>
                    </td>
                    <td>
                      <span className={`md-page__status-badge ${row.allow_outsource ? "is-active" : "is-inactive"}`}>
                        {row.allow_outsource ? "Cho phép" : "Không"}
                      </span>
                    </td>
                    <td>
                      {activeRate ? (
                        <span className="md-page__price">
                          {activeRate.run_rate.toLocaleString("vi-VN")} đ/{row.unit}
                        </span>
                      ) : (
                        <span className="md-page__danger-text">Chưa cấu hình</span>
                      )}
                    </td>
                    <td>
                      {activeRate ? (
                        <span className="md-page__price">
                          {activeRate.min_charge.toLocaleString("vi-VN")} đ
                        </span>
                      ) : (
                        <span className="md-page__muted">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`md-page__status-badge ${row.is_active ? "is-active" : "is-inactive"}`}>
                        {row.is_active ? "Kích hoạt" : "Đã ẩn"}
                      </span>
                    </td>
                    <td className="md-page__actions-col" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("edit"); }}
                      >
                        Sửa
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => { setSelected(row); setMode("rates"); }}
                      >
                        Biểu giá
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn md-page__rowbtn--danger"
                        onClick={() => setDeleting(row)}
                      >
                        Xóa
                      </button>
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
          <span className="md-page__muted">
            Tổng số: {total} công đoạn · Trang {page}/{totalPages}
          </span>
          <div className="md-page__pager-btns">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Sau ›
            </button>
          </div>
        </div>
      )}

      {/* Create / Edit Dialog */}
      {(mode === "create" || mode === "edit") && (
        <OperationFormDialog
          existing={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Operation Rates Dialog */}
      {mode === "rates" && selected && (
        <OperationRatesDialog
          operation={selected}
          onClose={() => { setMode(null); setSelected(null); }}
          onSaved={() => { setMode(null); setSelected(null); load(); }}
        />
      )}

      {/* Delete Confirmation */}
      {deleting && (
        <div className="md-page__overlay" role="dialog">
          <div className="md-page__dialog md-page__dialog--sm card">
            <div className="md-page__dialog-head">
              <h2>Xác nhận xóa công đoạn</h2>
            </div>
            <div className="md-page__dialog-body">
              <p>Bạn có chắc chắn muốn xóa vĩnh viễn công đoạn <strong>{deleting.name}</strong> ({deleting.code})?</p>
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
}

function OperationFormDialog({
  existing,
  onClose,
  onSaved,
}: {
  existing: OperationCatalogRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const isEdit = existing != null;

  const [tab, setTab] = useState<OpTabKey>("general");

  const [name, setName] = useState(existing?.name ?? "");
  const [opType, setOpType] = useState(existing?.operation_type ?? "can_mang");
  const [unit, setUnit] = useState(existing?.unit ?? "m2");
  const [basisQty, setBasisQty] = useState(existing?.basis_quantity ?? "to");
  const [pricingMethod, setPricingMethod] = useState(existing?.pricing_method ?? "theo_sp");
  const [processGroup, setProcessGroup] = useState(existing?.process_group ?? "sau_in");
  const [processType, setProcessType] = useState(existing?.process_type ?? "internal");
  const [defaultSequence, setDefaultSequence] = useState(String(existing?.default_sequence ?? 0));
  const [quantityFormula, setQuantityFormula] = useState(existing?.quantity_formula_type ?? "print_sheet_qty");
  const [allowManualQty, setAllowManualQty] = useState(existing?.allow_manual_quantity ?? false);
  const [internalMethod, setInternalMethod] = useState(existing?.internal_pricing_method ?? "per_qty");
  const [laborPeople, setLaborPeople] = useState(String(existing?.labor_people_count ?? 1));
  const [hasTooling, setHasTooling] = useState(existing?.has_tooling ?? false);
  const [toolingType, setToolingType] = useState(existing?.tooling_type ?? "khuon_be");
  const [toolingRateId, setToolingRateId] = useState<string>(existing?.tooling_rate_id ? String(existing.tooling_rate_id) : "");
  const [dieRates, setDieRates] = useState<PlateDieRateRow[]>([]);
  const [hasYield, setHasYield] = useState(existing?.has_yield_loss ?? false);
  const [yieldRate, setYieldRate] = useState(existing?.default_yield_rate != null ? String(existing.default_yield_rate) : "98");
  const [yieldRule, setYieldRule] = useState(existing?.default_yield_rule ?? "");
  const [isActive, setIsActive] = useState(existing?.is_active ?? true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bảng giá khuôn hiện hành (DM Đơn giá kẽm & khuôn #5) để công đoạn trỏ tới.
  useEffect(() => {
    if (!token || !hasTooling) return;
    api.plateDieRates.list(token, { current_only: true, is_active: true, size: 200 })
      .then((r) => setDieRates(r.items.filter((x) => x.plate_type !== "ban_kem_offset")))
      .catch(() => setDieRates([]));
  }, [token, hasTooling]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    if (!name.trim()) { setTab("general"); return setError("Tên công đoạn không được trống."); }
    if (!unit.trim()) { setTab("quantity"); return setError("Đơn vị tính không được trống."); }
    if (hasTooling && !toolingType) { setTab("tooling"); return setError("Có phát sinh khuôn thì phải chọn loại khuôn."); }

    const payload: OperationCatalogInput = {
      name: name.trim(),
      operation_type: opType,
      unit: unit.trim(),
      basis_quantity: basisQty,
      pricing_method: pricingMethod,
      process_group: processGroup,
      process_type: processType,
      default_sequence: Number(defaultSequence) || 0,
      quantity_formula_type: quantityFormula,
      allow_manual_quantity: allowManualQty,
      internal_pricing_method: internalMethod,
      labor_people_count: Number(laborPeople) || 1,
      has_tooling: hasTooling,
      tooling_type: hasTooling ? toolingType : null,
      tooling_rate_id: hasTooling && toolingRateId ? Number(toolingRateId) : null,
      has_yield_loss: hasYield,
      default_yield_rate: hasYield ? (Number(yieldRate) || 0) : null,
      default_yield_rule: hasYield ? (yieldRule.trim() || null) : null,
      is_active: isActive,
    };

    setSaving(true);
    try {
      if (isEdit && existing) {
        await api.operations.update(token, existing.id, payload);
      } else {
        await api.operations.create(token, payload);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu công đoạn thất bại.");
      setSaving(false);
    }
  }

  const qtyPreview: Record<string, string> = {
    print_sheet_qty: "Lượng tính = số tờ sản xuất (vd 500 tờ → 500).",
    finished_qty: "Lượng tính = số thành phẩm (vd 1.000 cái → 1.000).",
    area_m2: "Lượng tính = số tờ × diện tích 1 tờ (m²).",
    linear_meter: "Lượng tính = số mét dài (nhập tay).",
    book_qty: "Lượng tính = số cuốn.",
    box_qty: "Lượng tính = số hộp (theo thành phẩm).",
    pack_qty: "Lượng tính = số thùng đóng gói.",
    manual: "Lượng tính = nhập tay tại màn Tính giá.",
  };
  const internalPreview: Record<string, string> = {
    per_qty: "Chi phí = phí setup + lượng × đơn giá sản lượng.",
    per_hour: "Chi phí = (thời gian setup + lượng / tốc độ) × đơn giá giờ máy.",
    combined: "Chi phí = phí setup + giờ máy × đơn giá giờ + lượng × đơn giá sản lượng.",
  };

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>{isEdit ? `Sửa công đoạn: ${existing?.code}` : "Tạo công đoạn gia công mới"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>

        <div className="md-tabs">
          {OP_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`md-tab ${tab === t.key ? "md-tab--active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {tab === "general" && (
            <div className="md-page__form-grid">
              <label className="field md-page__form-wide">
                <span className="field__label">Tên công đoạn gia công *</span>
                <input className="input" placeholder="VD: Cán màng mờ 1 mặt" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Phân loại (kỹ thuật)</span>
                <select className="input" value={opType} onChange={(e) => setOpType(e.target.value)} disabled={isEdit}>
                  {OP_TYPES.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Nhóm công đoạn *</span>
                <select className="input" value={processGroup} onChange={(e) => setProcessGroup(e.target.value)}>
                  {PROCESS_GROUP.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Loại xử lý *</span>
                <select className="input" value={processType} onChange={(e) => setProcessType(e.target.value)}>
                  {PROCESS_TYPE.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Thứ tự mặc định</span>
                <input className="input" type="number" value={defaultSequence} onChange={(e) => setDefaultSequence(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Trạng thái</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="op-active-check" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  <label htmlFor="op-active-check">Kích hoạt hoạt động</label>
                </div>
              </label>
            </div>
          )}

          {tab === "quantity" && (
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Đơn vị đo lường *</span>
                <input className="input" list="op-units" placeholder="VD: m2, to, cai" value={unit} onChange={(e) => setUnit(e.target.value)} />
                <datalist id="op-units">
                  {["m2", "to", "luot", "cuon", "cai", "san_pham", "thung", "kg"].map((u) => <option key={u} value={u} />)}
                </datalist>
              </label>
              <label className="field">
                <span className="field__label">Cơ sở tính lượng (engine) *</span>
                <select className="input" value={basisQty} onChange={(e) => setBasisQty(e.target.value)}>
                  {BASIS_QTY.map((b) => (<option key={b.value} value={b.value}>{b.label}</option>))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Công thức lượng tính *</span>
                <select className="input" value={quantityFormula} onChange={(e) => setQuantityFormula(e.target.value)}>
                  {QTY_FORMULA.map((f) => (<option key={f.value} value={f.value}>{f.label}</option>))}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Nhập tay lượng tính</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="op-manual-qty" checked={allowManualQty} onChange={(e) => setAllowManualQty(e.target.checked)} />
                  <label htmlFor="op-manual-qty">Cho phép nhập tay tại màn Tính giá</label>
                </div>
              </label>
              <div className="md-page__hint md-page__form-wide">{qtyPreview[quantityFormula]}</div>
            </div>
          )}

          {tab === "internal" && (
            <div className="md-page__form-grid">
              <label className="field md-page__form-wide">
                <span className="field__label">Cách tính chi phí nội bộ *</span>
                <select className="input" value={internalMethod} onChange={(e) => setInternalMethod(e.target.value)}>
                  {INTERNAL_METHOD.map((m) => (<option key={m.value} value={m.value}>{m.label}</option>))}
                </select>
              </label>
              <div className="md-page__hint md-page__form-wide">{internalPreview[internalMethod]}</div>
              <div className="md-page__note md-page__form-wide">
                Đơn giá sản lượng, đơn giá giờ máy, tốc độ chuẩn, phí/thời gian setup nhập theo từng
                phiên bản hiệu lực ở nút <strong>“Biểu giá”</strong>.
              </div>
            </div>
          )}

          {tab === "labor" && (
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Kiểu tính nhân công *</span>
                <select className="input" value={pricingMethod} onChange={(e) => setPricingMethod(e.target.value)}>
                  {PRICING_METHOD.map((p) => (<option key={p.value} value={p.value}>{p.label}</option>))}
                </select>
              </label>
              {pricingMethod === "theo_gio" && (
                <label className="field">
                  <span className="field__label">Số người</span>
                  <input className="input" type="number" value={laborPeople} onChange={(e) => setLaborPeople(e.target.value)} />
                </label>
              )}
              <div className="md-page__note md-page__form-wide">
                Đơn giá giờ công / ca / sản phẩm / khoán & min nhân công nhập ở nút <strong>“Biểu giá”</strong>.
                {pricingMethod === "theo_gio" && " Nhân công = số người × giờ máy × đơn giá giờ công."}
                {pricingMethod === "theo_sp" && " Nhân công = lượng × đơn giá sản phẩm."}
                {pricingMethod === "theo_ca" && " Nhân công = số ca × đơn giá ca."}
                {pricingMethod === "khoan" && " Nhân công = tiền khoán cố định."}
                {pricingMethod === "none" && " Không tách chi phí nhân công riêng."}
              </div>
            </div>
          )}

          {tab === "outsource" && (
            <div className="md-page__form-grid">
              <div className="md-page__note md-page__form-wide">
                Loại xử lý hiện tại: <strong>{PROCESS_TYPE.find((t) => t.value === processType)?.label}</strong>.
                {processType === "internal"
                  ? " Đổi Loại xử lý sang “Thuê ngoài” hoặc “Cả hai” (tab Thông tin chung) để dùng bảng giá NCC."
                  : " Nhà cung cấp, đơn giá NCC, phí setup, min charge, vận chuyển, MOQ, lead time nhập theo phiên bản ở nút “Biểu giá”."}
              </div>
              <div className="md-page__hint md-page__form-wide">
                Chi phí thuê ngoài = max(lượng × đơn giá NCC, min charge) + phí setup + phí vận chuyển.
              </div>
            </div>
          )}

          {tab === "tooling" && (
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Phát sinh khuôn</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="op-has-tooling" checked={hasTooling} onChange={(e) => setHasTooling(e.target.checked)} />
                  <label htmlFor="op-has-tooling">Công đoạn có phát sinh khuôn</label>
                </div>
              </label>
              {hasTooling && (
                <label className="field">
                  <span className="field__label">Loại khuôn *</span>
                  <select className="input" value={toolingType} onChange={(e) => setToolingType(e.target.value)}>
                    {TOOLING_TYPE.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
                  </select>
                </label>
              )}
              {hasTooling && (
                <label className="field">
                  <span className="field__label">Bảng giá khuôn (DM Đơn giá kẽm & khuôn)</span>
                  <select className="input" value={toolingRateId} onChange={(e) => setToolingRateId(e.target.value)}>
                    <option value="">— Dùng đơn giá nhập ở “Biểu giá” —</option>
                    {dieRates.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.code} · {d.name} ({d.pricing_method === "area" ? `${d.unit_price_area.toLocaleString("vi-VN")}đ/cm²` : d.pricing_method === "perimeter" ? `${d.unit_price_perimeter.toLocaleString("vi-VN")}đ/m` : `${d.unit_price.toLocaleString("vi-VN")}đ`})
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {hasTooling && (
                <div className="md-page__note md-page__form-wide">
                  Chọn bảng giá khuôn ở trên → engine lấy giá theo cách tính của bảng đó. Bỏ trống → dùng đơn giá khuôn nhập tay ở nút “Biểu giá”.
                </div>
              )}

              <label className="field">
                <span className="field__label">Hao hụt / tỷ lệ đạt</span>
                <div className="md-page__toggle-wrap">
                  <input type="checkbox" id="op-has-yield" checked={hasYield} onChange={(e) => setHasYield(e.target.checked)} />
                  <label htmlFor="op-has-yield">Công đoạn có hao hụt</label>
                </div>
              </label>
              {hasYield && (
                <label className="field">
                  <span className="field__label">Tỷ lệ đạt mặc định (%)</span>
                  <input className="input" type="number" step="0.01" value={yieldRate} onChange={(e) => setYieldRate(e.target.value)} />
                </label>
              )}
              {hasYield && (
                <label className="field">
                  <span className="field__label">Rule bù hao mặc định</span>
                  <input className="input" placeholder="VD: YIELD_DIECUT" value={yieldRule} onChange={(e) => setYieldRule(e.target.value)} />
                </label>
              )}
              {hasYield && (
                <div className="md-page__note md-page__form-wide">
                  Rule chi tiết khai ở danh mục <strong>Định mức &amp; Bù hao</strong>; ở đây chỉ lưu cờ + tỷ lệ đạt mặc định.
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="banner banner--error" role="alert">{error}</div>
          )}

          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu công đoạn</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function OperationRatesDialog({
  operation,
  onClose,
  onSaved,
}: {
  operation: OperationCatalogRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const showOutsource = operation.process_type !== "internal";
  const showTooling = operation.has_tooling;
  const internalMethod = operation.internal_pricing_method || "per_qty";

  const [rates, setRates] = useState<OperationCatalogRateRow[]>([]);
  const [setupFee, setSetupFee] = useState("0");
  const [runRate, setRunRate] = useState("");
  const [hourlyRate, setHourlyRate] = useState("0");
  const [laborRate, setLaborRate] = useState("0");
  const [laborShift, setLaborShift] = useState("0");
  const [laborFixed, setLaborFixed] = useState("0");
  const [laborMin, setLaborMin] = useState("0");
  const [minCharge, setMinCharge] = useState("0");
  const [speed, setSpeed] = useState("0");
  const [setupTimeMins, setSetupTimeMins] = useState("0");
  const [toolingPrice, setToolingPrice] = useState("0");
  const [osSupplier, setOsSupplier] = useState("");
  const [osUnit, setOsUnit] = useState("0");
  const [osSetup, setOsSetup] = useState("0");
  const [osMin, setOsMin] = useState("0");
  const [osTransport, setOsTransport] = useState("0");
  const [osMoq, setOsMoq] = useState("0");
  const [osLead, setOsLead] = useState("0");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().split("T")[0]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Test nhanh (spec §4.7)
  const [tSheet, setTSheet] = useState("500");
  const [tFinished, setTFinished] = useState("1000");
  const [tArea, setTArea] = useState("0.86");
  const [tBook, setTBook] = useState("1000");
  const [tManual, setTManual] = useState("0");
  const [tMode, setTMode] = useState(showOutsource ? "outsourced" : "internal");
  const [preview, setPreview] = useState<OperationPreviewResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  const loadRates = useCallback(() => {
    if (!token) return;
    api.operations
      .get(token, operation.id)
      .then((res) => setRates(res.rates))
      .catch(() => setError("Không tải được biểu giá."));
  }, [token, operation.id]);

  useEffect(() => {
    loadRates();
  }, [loadRates]);

  async function handleAddRate(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);

    const rr = Number(runRate) || 0;
    if (internalMethod !== "per_hour" && (!runRate.trim() || rr < 0)) {
      return setError("Vui lòng nhập đơn giá sản lượng hợp lệ.");
    }
    if ((internalMethod === "per_hour" || internalMethod === "combined")) {
      if ((Number(hourlyRate) || 0) <= 0) return setError("Cách tính theo giờ máy cần đơn giá giờ máy > 0.");
      if ((Number(speed) || 0) <= 0) return setError("Cách tính theo giờ máy cần tốc độ chuẩn > 0.");
    }

    const payload: OperationCatalogRateInput = {
      setup_fee: Number(setupFee) || 0,
      run_rate: rr,
      labor_rate: Number(laborRate) || 0,
      min_charge: Number(minCharge) || 0,
      speed: Number(speed) || 0,
      setup_time_mins: Number(setupTimeMins) || 0,
      hourly_rate: Number(hourlyRate) || 0,
      labor_shift_rate: Number(laborShift) || 0,
      labor_fixed: Number(laborFixed) || 0,
      labor_min: Number(laborMin) || 0,
      tooling_unit_price: Number(toolingPrice) || 0,
      outsource_supplier: osSupplier.trim() || null,
      outsource_unit_price: Number(osUnit) || 0,
      outsource_setup_fee: Number(osSetup) || 0,
      outsource_min_charge: Number(osMin) || 0,
      outsource_transport_fee: Number(osTransport) || 0,
      outsource_moq: Number(osMoq) || 0,
      outsource_lead_time_days: Number(osLead) || 0,
      effective_from: effectiveFrom,
    };

    setSaving(true);
    try {
      await api.operations.addRate(token, operation.id, payload);
      loadRates();
      onSaved();
      setSaving(false);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Lưu đơn giá mới thất bại.");
      setSaving(false);
    }
  }

  async function handlePreview() {
    if (!token || previewing) return;
    setPreviewErr(null);
    setPreviewing(true);
    const input: OperationPreviewInput = {
      sheet_qty: Number(tSheet) || 0,
      finished_qty: Number(tFinished) || 0,
      area_m2: Number(tArea) || 0,
      book_qty: Number(tBook) || 0,
      manual_qty: Number(tManual) || 0,
      execution_mode: tMode,
    };
    try {
      const res = await api.operations.preview(token, operation.id, input);
      setPreview(res);
    } catch (err) {
      if (err instanceof ApiError) setPreviewErr(err.message);
      else setPreviewErr("Không chạy được test công thức.");
    } finally {
      setPreviewing(false);
    }
  }

  const money = (n: number) => `${n.toLocaleString("vi-VN")} đ`;

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card">
        <div className="md-page__dialog-head">
          <h2>Biểu giá & Test công đoạn: {operation.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          <form className="md-page__rates-form" onSubmit={handleAddRate}>
            <h3 className="md-page__section-title">Nội bộ — sản lượng / giờ máy (§C)</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Phí setup cố định (đ)</span>
                <input className="input" type="number" value={setupFee} onChange={(e) => setSetupFee(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Đơn giá sản lượng (đ/{operation.unit}){internalMethod === "per_hour" ? "" : " *"}</span>
                <input className="input" type="number" placeholder="VD: 300" value={runRate} onChange={(e) => setRunRate(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Đơn giá giờ máy (đ/giờ)</span>
                <input className="input" type="number" value={hourlyRate} onChange={(e) => setHourlyRate(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Tốc độ chuẩn (đv/h)</span>
                <input className="input" type="number" value={speed} onChange={(e) => setSpeed(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Thời gian setup (phút)</span>
                <input className="input" type="number" value={setupTimeMins} onChange={(e) => setSetupTimeMins(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Phí tối thiểu / job (đ)</span>
                <input className="input" type="number" value={minCharge} onChange={(e) => setMinCharge(e.target.value)} />
              </label>
            </div>

            <h3 className="md-page__section-title">Nhân công (§D)</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Đơn giá giờ công / sản phẩm (đ)</span>
                <input className="input" type="number" value={laborRate} onChange={(e) => setLaborRate(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Đơn giá ca (đ)</span>
                <input className="input" type="number" value={laborShift} onChange={(e) => setLaborShift(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Tiền khoán (đ)</span>
                <input className="input" type="number" value={laborFixed} onChange={(e) => setLaborFixed(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Min nhân công (đ)</span>
                <input className="input" type="number" value={laborMin} onChange={(e) => setLaborMin(e.target.value)} />
              </label>
            </div>

            {showTooling && (
              <>
                <h3 className="md-page__section-title">Khuôn (§F)</h3>
                <div className="md-page__form-grid">
                  <label className="field">
                    <span className="field__label">Đơn giá khuôn (đ)</span>
                    <input className="input" type="number" value={toolingPrice} onChange={(e) => setToolingPrice(e.target.value)} />
                  </label>
                </div>
              </>
            )}

            {showOutsource && (
              <>
                <h3 className="md-page__section-title">Thuê ngoài — bảng giá NCC (§E)</h3>
                <div className="md-page__form-grid">
                  <label className="field">
                    <span className="field__label">Nhà cung cấp</span>
                    <input className="input" value={osSupplier} onChange={(e) => setOsSupplier(e.target.value)} placeholder="VD: NCC Bế A" />
                  </label>
                  <label className="field">
                    <span className="field__label">Đơn giá NCC (đ/{operation.unit})</span>
                    <input className="input" type="number" value={osUnit} onChange={(e) => setOsUnit(e.target.value)} />
                  </label>
                  <label className="field">
                    <span className="field__label">Phí setup NCC (đ)</span>
                    <input className="input" type="number" value={osSetup} onChange={(e) => setOsSetup(e.target.value)} />
                  </label>
                  <label className="field">
                    <span className="field__label">Min charge (đ)</span>
                    <input className="input" type="number" value={osMin} onChange={(e) => setOsMin(e.target.value)} />
                  </label>
                  <label className="field">
                    <span className="field__label">Phí vận chuyển (đ)</span>
                    <input className="input" type="number" value={osTransport} onChange={(e) => setOsTransport(e.target.value)} />
                  </label>
                  <label className="field">
                    <span className="field__label">MOQ</span>
                    <input className="input" type="number" value={osMoq} onChange={(e) => setOsMoq(e.target.value)} />
                  </label>
                  <label className="field">
                    <span className="field__label">Lead time (ngày)</span>
                    <input className="input" type="number" value={osLead} onChange={(e) => setOsLead(e.target.value)} />
                  </label>
                </div>
              </>
            )}

            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Ngày hiệu lực *</span>
                <input className="input" type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
              </label>
              <div className="md-page__field-btn-align md-page__form-wide">
                <Button type="submit" variant="primary" loading={saving}>Áp dụng đơn giá</Button>
              </div>
            </div>
          </form>

          {error && (
            <div className="banner banner--error" role="alert">{error}</div>
          )}

          {/* Test nhanh công thức — spec §4.7 */}
          <div className="md-page__costs-history">
            <h3 className="md-page__section-title">Test nhanh công thức</h3>
            <div className="md-page__form-grid">
              <label className="field">
                <span className="field__label">Số tờ sản xuất</span>
                <input className="input" type="number" value={tSheet} onChange={(e) => setTSheet(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Số thành phẩm</span>
                <input className="input" type="number" value={tFinished} onChange={(e) => setTFinished(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Diện tích 1 tờ (m²)</span>
                <input className="input" type="number" step="0.0001" value={tArea} onChange={(e) => setTArea(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Số cuốn</span>
                <input className="input" type="number" value={tBook} onChange={(e) => setTBook(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Nhập tay</span>
                <input className="input" type="number" value={tManual} onChange={(e) => setTManual(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Cách làm</span>
                <select className="input" value={tMode} onChange={(e) => setTMode(e.target.value)}>
                  <option value="internal">Nội bộ</option>
                  <option value="outsourced">Thuê ngoài</option>
                </select>
              </label>
              <div className="md-page__field-btn-align md-page__form-wide">
                <Button type="button" variant="ghost" loading={previewing} onClick={handlePreview}>Chạy test công thức</Button>
              </div>
            </div>

            {previewErr && <div className="banner banner--error" role="alert">{previewErr}</div>}

            {preview && (
              <div className="md-page__preview">
                <div className="md-page__preview-head">
                  Lượng tính = <strong>{preview.quantity.toLocaleString("vi-VN")}</strong> {preview.unit} · Cách làm:{" "}
                  <strong>{preview.execution_mode === "outsourced" ? "Thuê ngoài" : "Nội bộ"}</strong>
                </div>
                <table className="md-page__table">
                  <thead>
                    <tr><th>Thành phần</th><th>Công thức</th><th style={{ textAlign: "right" }}>Số tiền</th></tr>
                  </thead>
                  <tbody>
                    {preview.components.map((c, i) => (
                      <tr key={i}>
                        <td>{c.label}</td>
                        <td className="md-page__muted">{c.formula}</td>
                        <td style={{ textAlign: "right" }}>{money(c.amount)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={2}><strong>Tổng {operation.name}</strong></td>
                      <td style={{ textAlign: "right" }}><strong>{money(preview.total)}</strong></td>
                    </tr>
                  </tbody>
                </table>
                {preview.warnings.map((w, i) => (
                  <div key={i} className="banner banner--warn" role="alert">{w}</div>
                ))}
              </div>
            )}
          </div>

          <div className="md-page__costs-history">
            <h3 className="md-page__section-title">Lịch sử biểu giá</h3>
            <div className="md-page__tablewrap">
              <table className="md-page__table">
                <thead>
                  <tr>
                    <th>Setup (đ)</th>
                    <th>Sản lượng (đ/{operation.unit})</th>
                    <th>Giờ máy (đ/h)</th>
                    <th>Nhân công (đ)</th>
                    <th>Min (đ)</th>
                    <th>Khuôn (đ)</th>
                    <th>NCC (đ/{operation.unit})</th>
                    <th>Từ ngày</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="md-page__empty">Chưa có biểu giá lịch sử nào.</td>
                    </tr>
                  ) : (
                    rates.map((r) => {
                      const isActive = r.effective_to === null;
                      return (
                        <tr key={r.id}>
                          <td>{r.setup_fee.toLocaleString("vi-VN")}</td>
                          <td><strong>{r.run_rate.toLocaleString("vi-VN")}</strong></td>
                          <td>{r.hourly_rate ? r.hourly_rate.toLocaleString("vi-VN") : "—"}</td>
                          <td>{r.labor_rate.toLocaleString("vi-VN")}</td>
                          <td>{r.min_charge.toLocaleString("vi-VN")}</td>
                          <td>{r.tooling_unit_price ? r.tooling_unit_price.toLocaleString("vi-VN") : "—"}</td>
                          <td>{r.outsource_unit_price ? r.outsource_unit_price.toLocaleString("vi-VN") : "—"}</td>
                          <td>{r.effective_from}</td>
                          <td>
                            {isActive ? (
                              <span className="md-page__status-badge is-active">Đang áp dụng</span>
                            ) : (
                              <span className="md-page__muted">Hết hạn</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
