import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  type DepartmentPurchaseRequestInput,
  type DepartmentPurchaseRequestLineInput,
  type DepartmentPurchaseRequestRow,
  type DepartmentPurchaseRequestStatus,
  type DepartmentPurchaseSourceType,
} from "../api/client";
import { useCan } from "../auth/permissions";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { fmtDate } from "../utils/format";
import "./master-data.css";
import "./purchase.css";

type StatusFilter = "all" | DepartmentPurchaseRequestStatus;

const REQUEST_MODULES = [
  "thu_mua",
  "bao_gia",
  "kho",
  "san_xuat",
  "dm_giay_vat_tu",
];

const SOURCE_TYPE_LABELS: Record<DepartmentPurchaseSourceType, string> = {
  kinh_doanh: "Kinh doanh",
  kho: "Kho",
  san_xuat: "Sản xuất",
  cong_nghe: "Công nghệ",
  gia_cong_ngoai: "Gia công ngoài",
  khac: "Khác",
};

const SOURCE_STATUS_META: Record<
  DepartmentPurchaseRequestStatus,
  { label: string; tone: string }
> = {
  open: { label: "Chờ Thu mua xử lý", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  in_purchase: { label: "Đang mua", tone: "pending" },
  done: { label: "Hoàn tất", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

function emptyLine(): DepartmentPurchaseRequestLineInput {
  return {
    item_name: "",
    unit: "",
    quantity: 0,
    note: "",
  };
}

function emptyRequest(
  sourceType: DepartmentPurchaseSourceType,
): DepartmentPurchaseRequestInput {
  return {
    source_type: sourceType,
    related_document_type: null,
    related_document_code: null,
    purpose: "",
    needed_date: "",
    note: "",
    lines: [emptyLine()],
  };
}

export function DepartmentPurchaseRequestsPage({
  focusRequestCode = null,
}: {
  /** Liên thông từ PMH/Phiếu chi: lọc + tô sáng đúng mã YCMH này khi mở trang. */
  focusRequestCode?: string | null;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  const canCreate = REQUEST_MODULES.some((module) => can(module, "create"));
  const canAdminCancel = can("thu_mua", "cancel");

  const defaultSourceType = useMemo<DepartmentPurchaseSourceType>(() => {
    if (can("kho", "create")) return "kho";
    if (can("san_xuat", "create")) return "san_xuat";
    if (can("dm_giay_vat_tu", "create")) return "cong_nghe";
    return "kinh_doanh";
  }, [can]);

  const [rows, setRows] = useState<DepartmentPurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [mode, setMode] = useState(false);
  const [form, setForm] = useState<DepartmentPurchaseRequestInput>(
    emptyRequest(defaultSourceType),
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [canceling, setCanceling] = useState<DepartmentPurchaseRequestRow | null>(
    null,
  );
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.departmentPurchaseRequests
      .list(token, {
        q: q.trim() || undefined,
        status: status === "all" ? null : status,
        sort: "-created_at",
        page: 1,
        size: 100,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh sách yêu cầu mua hàng.");
      })
      .finally(() => setLoading(false));
  }, [token, q, status]);

  useEffect(() => {
    load();
  }, [load]);

  // Liên thông: đổ mã YCMH cần truy vết vào ô tìm kiếm → load() tự chạy lại
  // (q đổi làm useCallback tạo lại), danh sách chỉ còn đúng phiếu đó.
  useEffect(() => {
    if (!focusRequestCode) return;
    setQ(focusRequestCode);
    setStatus("all");
  }, [focusRequestCode]);

  function openCreate() {
    setForm(emptyRequest(defaultSourceType));
    setFormError(null);
    setMode(true);
  }

  function setLine(
    index: number,
    patch: Partial<DepartmentPurchaseRequestLineInput>,
  ) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, i) =>
        i === index ? { ...line, ...patch } : line,
      ),
    }));
  }

  function cleanRequest(
    input: DepartmentPurchaseRequestInput,
  ): DepartmentPurchaseRequestInput {
    const trimOptional = (v?: string | null) => {
      const s = (v ?? "").trim();
      return s || null;
    };
    return {
      source_type: input.source_type,
      related_document_type: null,
      related_document_code: null,
      purpose: (input.purpose ?? "").trim(),
      needed_date: (input.needed_date ?? "").trim(),
      note: trimOptional(input.note),
      lines: input.lines.map((line) => ({
        item_name: (line.item_name ?? "").trim(),
        unit: (line.unit ?? "").trim(),
        quantity: Number(line.quantity),
        note: trimOptional(line.note),
      })),
    };
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    const payload = cleanRequest(form);
    const missingHeader = [
      !payload.source_type ? "Bộ phận phát sinh" : "",
      !payload.needed_date ? "Ngày cần hàng" : "",
      !payload.purpose ? "Mục đích" : "",
    ].filter(Boolean);
    if (missingHeader.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missingHeader.join(", ")}.`);
      return;
    }
    if (
      !payload.lines.length ||
      payload.lines.some((line) => !line.item_name || !line.unit)
    ) {
      setFormError(
        "Yêu cầu cần ít nhất một dòng vật tư; tên vật tư và đơn vị tính không được trống.",
      );
      return;
    }
    if (payload.lines.some((line) => line.quantity <= 0)) {
      setFormError("Số lượng phải lớn hơn 0.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const saved = await api.departmentPurchaseRequests.create(token, payload);
      setRows((current) => [saved, ...current]);
      setTotal((current) => current + 1);
      setMode(false);
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError("Không tạo được yêu cầu mua hàng.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmCancel() {
    if (!token || !canceling) return;
    setActionBusy(`cancel:${canceling.id}`);
    try {
      const saved = await api.departmentPurchaseRequests.cancel(
        token,
        canceling.id,
        "Hủy yêu cầu mua hàng",
      );
      setRows((current) =>
        current.map((row) => (row.id === saved.id ? saved : row)),
      );
      setCanceling(null);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không hủy được yêu cầu mua hàng.");
      setCanceling(null);
    } finally {
      setActionBusy(null);
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Yêu cầu mua hàng (403).
        </div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Phòng ban</p>
        <h1 className="md-page__title">Yêu cầu mua hàng</h1>
        <p className="md-page__sub">
          Các phòng ban tạo yêu cầu vật tư cần mua; Thu mua dùng danh sách này
          để lập phiếu mua hàng gửi kế toán duyệt.
        </p>
      </header>

      <div className="md-page__toolbar">
        <form
          className="md-page__search"
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
        >
          <input
            className="input"
            placeholder="Tìm mã yêu cầu, mục đích, vật tư..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>
        <select
          className="input purchase__select"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusFilter)}
        >
          <option value="all">Tất cả trạng thái</option>
          {Object.entries(SOURCE_STATUS_META).map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.label}
            </option>
          ))}
        </select>
        <div className="md-page__toolbar-spacer" />
        {canCreate && (
          <Button variant="primary" onClick={openCreate}>
            + Tạo yêu cầu mua
          </Button>
        )}
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <section className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã yêu cầu</th>
              <th>Bộ phận</th>
              <th>Cần hàng</th>
              <th>Vật tư</th>
              <th>Trạng thái</th>
              <th>Người tạo</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="md-page__status">
                  Đang tải yêu cầu mua hàng...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="md-page__empty">
                  Chưa có yêu cầu mua hàng phù hợp.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className={`md-page__row${
                    row.code === focusRequestCode
                      ? " purchase__row--selected"
                      : ""
                  }`}
                >
                  <td>
                    <strong className="md-page__mono">{row.code}</strong>
                    <div className="md-page__muted">{row.purpose}</div>
                  </td>
                  <td>
                    {SOURCE_TYPE_LABELS[row.source_type]}
                    <div className="md-page__muted">
                      {row.requesting_department_name || "Nội bộ"}
                    </div>
                  </td>
                  <td>{fmtDate(row.needed_date)}</td>
                  <td>
                    <strong>{row.lines.length} dòng</strong>
                    <div className="md-page__muted">
                      {row.lines
                        .slice(0, 2)
                        .map((line) => line.item_name)
                        .join(", ")}
                    </div>
                  </td>
                  <td>
                    <SourceStatusBadge status={row.status} />
                  </td>
                  <td>
                    {row.requested_by_name || "—"}
                    <div className="md-page__muted">{fmtDate(row.created_at)}</div>
                  </td>
                  <td>
                    {row.status === "open" &&
                    (canAdminCancel || row.requested_by_user_id === user?.id) ? (
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => setCanceling(row)}
                      >
                        Hủy
                      </button>
                    ) : (
                      <span className="md-page__muted">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div className="purchase__source-foot">
          <span className="md-page__muted">Tổng {total} yêu cầu</span>
        </div>
      </section>

      {mode && (
        <div className="md-page__overlay" role="presentation">
          <div
            className="card md-page__dialog purchase__dialog"
            role="dialog"
            aria-modal="true"
          >
            <div className="md-page__dialog-head">
              <h2>Tạo yêu cầu mua hàng</h2>
              <button
                type="button"
                className="md-page__close"
                onClick={() => setMode(false)}
              >
                ×
              </button>
            </div>
            <form className="md-page__dialog-body" onSubmit={save}>
              {formError && (
                <div className="banner banner--error" role="alert">
                  {formError}
                </div>
              )}
              <div className="md-page__form-grid">
                <LocalField label="Bộ phận phát sinh" required>
                  <select
                    className="input"
                    required
                    value={form.source_type}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        source_type: e.target.value as DepartmentPurchaseSourceType,
                      })
                    }
                  >
                    {Object.entries(SOURCE_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </LocalField>
                <LocalField label="Ngày cần hàng" required>
                  <input
                    className="input"
                    type="date"
                    required
                    value={form.needed_date}
                    onChange={(e) =>
                      setForm({ ...form, needed_date: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Mục đích" wide required>
                  <input
                    className="input"
                    required
                    value={form.purpose}
                    onChange={(e) =>
                      setForm({ ...form, purpose: e.target.value })
                    }
                    placeholder="VD: thiếu giấy cho lệnh sản xuất..."
                  />
                </LocalField>
                <LocalField label="Ghi chú" wide>
                  <textarea
                    className="input purchase__textarea"
                    value={form.note ?? ""}
                    onChange={(e) => setForm({ ...form, note: e.target.value })}
                  />
                </LocalField>
              </div>

              <div className="purchase__form-section">
                <div className="purchase__form-section-head">
                  <h3>Vật tư cần mua</h3>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        lines: [...current.lines, emptyLine()],
                      }))
                    }
                  >
                    + Thêm dòng
                  </button>
                </div>
                <div className="purchase__line-editor purchase__line-editor--request">
                  <div className="purchase__line-labels" aria-hidden="true">
                    <span>
                      Vật tư <span className="purchase__required-star">*</span>
                    </span>
                    <span>
                      ĐVT <span className="purchase__required-star">*</span>
                    </span>
                    <span>
                      Số lượng <span className="purchase__required-star">*</span>
                    </span>
                    <span>Ghi chú dòng</span>
                    <span></span>
                  </div>
                  {form.lines.map((line, index) => (
                    <div className="purchase__line-edit" key={index}>
                      <input
                        className="input purchase__line-name"
                        required
                        placeholder="VD: Giấy Duplex 350gsm"
                        value={line.item_name}
                        onChange={(e) =>
                          setLine(index, { item_name: e.target.value })
                        }
                      />
                      <input
                        className="input purchase__line-unit"
                        required
                        placeholder="VD: tờ, kg"
                        value={line.unit}
                        onChange={(e) => setLine(index, { unit: e.target.value })}
                      />
                      <input
                        className="input purchase__number-input"
                        type="number"
                        min="0.01"
                        step="0.01"
                        required
                        placeholder="VD: 1000"
                        value={line.quantity > 0 ? line.quantity : ""}
                        onChange={(e) =>
                          setLine(index, {
                            quantity: Number(e.target.value || 0),
                          })
                        }
                      />
                      <input
                        className="input purchase__line-note"
                        placeholder="Nếu có"
                        value={line.note ?? ""}
                        onChange={(e) => setLine(index, { note: e.target.value })}
                      />
                      <button
                        type="button"
                        className="purchase__line-remove"
                        aria-label="Xóa dòng vật tư"
                        title="Xóa dòng"
                        disabled={form.lines.length <= 1}
                        onClick={() =>
                          setForm((current) => ({
                            ...current,
                            lines: current.lines.filter((_, i) => i !== index),
                          }))
                        }
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="md-page__dialog-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setMode(false)}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving}>
                  Lưu yêu cầu
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(canceling)}
        title="Hủy yêu cầu mua hàng?"
        message={canceling ? `Yêu cầu ${canceling.code} sẽ chuyển sang trạng thái Đã hủy.` : undefined}
        danger
        confirmLabel="Hủy yêu cầu"
        busy={canceling ? actionBusy === `cancel:${canceling.id}` : false}
        onConfirm={confirmCancel}
        onCancel={() => setCanceling(null)}
      />
    </main>
  );
}

function SourceStatusBadge({
  status,
}: {
  status: DepartmentPurchaseRequestStatus;
}) {
  const meta = SOURCE_STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>
      {meta.label}
    </span>
  );
}

function LocalField({
  label,
  wide = false,
  required = false,
  children,
}: {
  label: string;
  wide?: boolean;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`purchase__field${wide ? " md-page__form-wide" : ""}`}>
      <span>
        {label}
        {required && <span className="purchase__required-star"> *</span>}
      </span>
      {children}
    </label>
  );
}
