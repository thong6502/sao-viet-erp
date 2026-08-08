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
  type DepartmentPurchaseRequestLineOut,
  type DepartmentPurchaseRequestRow,
  type DepartmentPurchaseRequestStatus,
  type DepartmentPurchaseSourceType,
  type PurchaseRequestStatus,
  type SupplierItemCatalogRow,
} from "../api/client";
import { useCan } from "../auth/permissions";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DetailModal } from "../components/DetailModal";
import { StatusHistoryTimeline } from "../components/StatusHistoryTimeline";
import { RowActionButton } from "../components/RowActionButton";
import { fmtDate } from "../utils/format";
import "./master-data.css";
// Bảng tình trạng từng dòng mượn `.pay-table` của màn Công nợ — cùng loại bảng phụ trong hộp
// thoại, không dựng bộ lớp thứ hai cho y hệt một việc.
import "./payables.css";
import "./purchase.css";

type StatusFilter = "all" | DepartmentPurchaseRequestStatus;

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
  sourceType: DepartmentPurchaseSourceType | null = null,
): DepartmentPurchaseRequestInput {
  return {
    source_type: sourceType,
    related_document_type: null,
    related_document_code: null,
    content: "",
    needed_date: "",
    note: null,
    lines: [emptyLine()],
  };
}

/** Nội dung để HIỆN. Phiếu lập trước 07/08/2026 chưa có ô gộp ⇒ nối lại hai ô cũ. */
function noiDungCu(purpose: string | null, note: string | null): string {
  return [purpose, note].map((x) => (x ?? "").trim()).filter(Boolean).join(" — ");
}

function noiDung(row: DepartmentPurchaseRequestRow): string {
  return row.content?.trim() || noiDungCu(row.purpose, row.note);
}

function todayInputValue(): string {
  const now = new Date();
  const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localNow.toISOString().slice(0, 10);
}

export function DepartmentPurchaseRequestsPage({
  eventTick = 0,
  focusRequestCode = null,
  seedLines = null,
  seedPurpose = null,
}: {
  eventTick?: number;
  /** Liên thông từ PMH/Phiếu chi: lọc + tô sáng đúng mã YCMH này khi mở trang. */
  focusRequestCode?: string | null;
  /** Liên thông từ Kho: mở form tạo, điền sẵn dòng vật tư (Tên + ĐVT) — bỏ trống SL/ghi chú. */
  seedLines?: DepartmentPurchaseRequestLineInput[] | null;
  seedPurpose?: string | null;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  const canAdminCancel = can("thu_mua", "cancel");
  const [canCreate, setCanCreate] = useState(false);
  const [departmentName, setDepartmentName] = useState<string | null>(null);
  const [itemCatalog, setItemCatalog] = useState<SupplierItemCatalogRow[]>([]);

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
    emptyRequest(),
  );
  const [editing, setEditing] = useState<DepartmentPurchaseRequestRow | null>(
    null,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [canceling, setCanceling] = useState<DepartmentPurchaseRequestRow | null>(
    null,
  );
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const minNeededDate = useMemo(() => todayInputValue(), []);

  // Lấy lại từ `rows` (không lưu cả object) để sau khi Hủy cập nhật `rows` thì
  // popup đang mở tự thấy trạng thái mới.
  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );

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

  useEffect(() => {
    if (eventTick <= 0 || !token) return;
    load();
    let alive = true;
    api.suppliers
      .itemCatalog(token)
      .then((res) => {
        if (alive) setItemCatalog(res.items);
      })
      .catch(() => {
        if (alive) setItemCatalog([]);
      });
    return () => {
      alive = false;
    };
  }, [eventTick, load, token]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.departmentPurchaseRequests
      .canCreate(token)
      .then((res) => {
        if (alive) setCanCreate(res.can_create);
      })
      .catch(() => {
        if (alive) setCanCreate(false);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api
      .profile(token)
      .then((profile) => {
        if (alive) setDepartmentName(profile.department_name);
      })
      .catch(() => {
        if (alive) setDepartmentName(null);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    api.suppliers
      .itemCatalog(token)
      .then((res) => {
        if (alive) setItemCatalog(res.items);
      })
      .catch(() => {
        if (alive) setItemCatalog([]);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  // Liên thông: đổ mã YCMH cần truy vết vào ô tìm kiếm → load() tự chạy lại
  // (q đổi làm useCallback tạo lại), danh sách chỉ còn đúng phiếu đó.
  useEffect(() => {
    if (!focusRequestCode) return;
    setQ(focusRequestCode);
    setStatus("all");
  }, [focusRequestCode]);

  // Liên thông từ Kho: mở form tạo với dòng vật tư điền sẵn (nguồn = Kho). `seedLines` là object
  // MỚI mỗi lần điều hướng nên effect chạy đúng 1 lần / lượt bấm "Tạo yêu cầu mua".
  useEffect(() => {
    if (!seedLines || seedLines.length === 0) return;
    setForm({
      ...emptyRequest("kho"),
      content: seedPurpose ?? "",
      lines: seedLines,
    });
    setFormError(null);
    setMode(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedLines]);

  function openCreate() {
    setEditing(null);
    setForm(emptyRequest());
    setFormError(null);
    setMode(true);
  }

  function openEdit(row: DepartmentPurchaseRequestRow) {
    setEditing(row);
    setForm({
      source_type: row.source_type,
      related_document_type: row.related_document_type,
      related_document_code: row.related_document_code,
      content: row.content ?? noiDungCu(row.purpose, row.note),
      needed_date: row.needed_date,
      note: null,
      lines: row.lines.map((line) => ({
        item_name: line.item_name,
        unit: line.unit,
        quantity: line.quantity,
        note: line.note,
      })),
    });
    setFormError(null);
    setMode(true);
  }

  function closeForm() {
    setMode(false);
    setEditing(null);
    setFormError(null);
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

  function selectCatalogItem(index: number, itemName: string) {
    const picked = itemCatalog.find((item) => item.item_name === itemName);
    setLine(index, {
      item_name: itemName,
      unit: picked?.unit ?? "",
    });
  }

  function cleanRequest(
    input: DepartmentPurchaseRequestInput,
  ): DepartmentPurchaseRequestInput {
    const trimOptional = (v?: string | null) => {
      const s = (v ?? "").trim();
      return s || null;
    };
    return {
      source_type: input.source_type ?? null,
      related_document_type: null,
      related_document_code: null,
      content: (input.content ?? "").trim(),
      needed_date: (input.needed_date ?? "").trim(),
      note: null,
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
      !payload.needed_date ? "Ngày cần hàng" : "",
      !payload.content ? "Nội dung / mục đích" : "",
    ].filter(Boolean);
    if (missingHeader.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missingHeader.join(", ")}.`);
      return;
    }
    if (payload.needed_date && payload.needed_date < minNeededDate) {
      setFormError("Ngày cần hàng không được nhỏ hơn hôm nay.");
      return;
    }
    if (itemCatalog.length === 0) {
      setFormError("Chua co vat tu nao trong danh muc mat hang nha cung cap.");
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
    if (
      payload.lines.some(
        (line) =>
          !itemCatalog.some((item) => item.item_name === line.item_name),
      )
    ) {
      setFormError("Vat tu yeu cau phai chon tu danh muc mat hang nha cung cap.");
      return;
    }
    if (payload.lines.some((line) => line.quantity <= 0)) {
      setFormError("Số lượng phải lớn hơn 0.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const saved = editing
        ? await api.departmentPurchaseRequests.update(token, editing.id, payload)
        : await api.departmentPurchaseRequests.create(token, payload);
      setRows((current) =>
        editing
          ? current.map((row) => (row.id === saved.id ? saved : row))
          : [saved, ...current],
      );
      if (!editing) setTotal((current) => current + 1);
      closeForm();
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
          {/* <Button type="submit" variant="ghost">
            Tìm
          </Button> */}
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
              {/* TRẠNG THÁI luôn đứng NGAY TRƯỚC Thao tác — thống nhất ở mọi màn Thu mua /
                  Kế toán, để mắt không phải đi tìm lại ở từng màn. */}
              <th>Mã yêu cầu</th>
              <th>Bộ phận</th>
              <th>Cần hàng</th>
              <th>Vật tư</th>
              <th>Người tạo</th>
              <th>Trạng thái</th>
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
                    row.code === focusRequestCode || selectedId === row.id
                      ? " purchase__row--selected"
                      : ""
                  }`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td>
                    <strong className="md-page__mono">{row.code}</strong>
                    <div className="md-page__muted">{noiDung(row)}</div>
                  </td>
                  <td>
                    {row.requesting_department_name || "Nội bộ"}
                    <div className="md-page__muted">
                      {SOURCE_TYPE_LABELS[row.source_type]}
                    </div>
                  </td>
                  <td>{fmtDate(row.needed_date)}</td>
                  <td
                    title={row.lines.map((line) => line.item_name).join(", ")}
                  >
                    <strong>{row.lines.length} dòng</strong>
                    <div className="md-page__muted">
                      {row.lines
                        .slice(0, 2)
                        .map((line) => line.item_name)
                        .join(", ")}
                      {row.lines.length > 2 ? "…" : ""}
                    </div>
                  </td>
                  <td>
                    {row.requested_by_name || "—"}
                    <div className="md-page__muted">{fmtDate(row.created_at)}</div>
                  </td>
                  <td>
                    <SourceStatusBadge status={row.status} />
                  </td>
                  <td
                    className="md-page__actions-col"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <div className="purchase__actions purchase__actions--dense">
                      <RowActionButton
                        dense
                        label="Xem chi tiết"
                        icon="eye"
                        onClick={() => setSelectedId(row.id)}
                      />
                      {row.status === "open" &&
                        row.requested_by_user_id === user?.id && (
                          <button
                            type="button"
                            className="btn btn--ghost md-page__rowbtn"
                            onClick={() => openEdit(row)}
                          >
                            Sửa
                          </button>
                        )}
                      {row.status === "open" &&
                        (canAdminCancel ||
                          row.requested_by_user_id === user?.id) && (
                          <button
                            type="button"
                            className="btn btn--ghost md-page__rowbtn"
                            onClick={() => setCanceling(row)}
                          >
                            Hủy
                          </button>
                        )}
                    </div>
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

      {selected && (
        <DetailModal
          kicker="Chi tiết yêu cầu"
          title={selected.code}
          subtitle={noiDung(selected)}
          badge={<SourceStatusBadge status={selected.status} />}
          onClose={() => setSelectedId(null)}
        >
          <dl className="purchase__facts">
            <div>
              <dt>Nhóm nguồn</dt>
              <dd>{SOURCE_TYPE_LABELS[selected.source_type]}</dd>
            </div>
            <div>
              <dt>Phòng ban</dt>
              <dd>{selected.requesting_department_name || "Nội bộ"}</dd>
            </div>
            <div>
              <dt>Ngày cần hàng</dt>
              <dd>{fmtDate(selected.needed_date)}</dd>
            </div>
            <div>
              <dt>Người tạo</dt>
              <dd>{selected.requested_by_name || "—"}</dd>
            </div>
            <div>
              <dt>Tạo lúc</dt>
              <dd>{fmtDate(selected.created_at)}</dd>
            </div>
          </dl>
          {selected.reject_reason && (
            <div className="purchase__note purchase__note--reject">
              <strong>Lý do từ chối / huỷ:</strong> {selected.reject_reason}
            </div>
          )}
          <p className="eyebrow">
            Vật tư đã yêu cầu ({selected.lines.length} dòng)
          </p>
          {/* Trạng thái ở đầu phiếu là bậc THẤP NHẤT của các dòng — nhìn danh sách biết "có gì đó
              chưa xong". Bảng dưới đây trả lời tiếp: chưa xong ở ĐÂU. Thiếu bảng thì biết kẹt mà
              không biết kẹt chỗ nào; thiếu trạng thái đầu phiếu thì phải mở từng yêu cầu mới biết. */}
          <table className="pay-table">
            <thead>
              <tr>
                <th>Vật tư</th>
                <th className="pay-num">Yêu cầu</th>
                {/* <th>Nhà cung cấp</th> */}
                <th>Tình trạng</th>
              </tr>
            </thead>
            <tbody>
              {selected.lines.map((line) => (
                <tr key={line.id}>
                  <td>
                    <strong>{line.item_name}</strong>
                    {line.note && (
                      <>
                        <br />
                        <small>{line.note}</small>
                      </>
                    )}
                  </td>
                  <td className="pay-num">
                    {line.quantity.toLocaleString("vi-VN")} {line.unit}
                  </td>
                  {/* <td>{line.fulfilment?.supplier_name ?? "—"}</td> */}
                  <td>
                    <LineFulfilmentCell
                      line={line}
                      coPhieu={selected.purchase_requests.length > 0}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {selected.purchase_requests.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 16 }}>
                Phiếu mua đã lập ({selected.purchase_requests.length})
              </p>
              <div className="purchase__lines">
                {selected.purchase_requests.map((p) => (
                  <div className="purchase__line" key={p.id}>
                    <span>
                      <strong>{p.code}</strong>
                      {p.supplier_name && (
                        <>
                          <br />
                          <small>{p.supplier_name}</small>
                        </>
                      )}
                    </span>
                    <StatusBadgePhieu status={p.status} />
                  </div>
                ))}
              </div>
            </>
          )}
          <p className="eyebrow" style={{ marginTop: 16 }}>
            Lịch sử trạng thái
          </p>
          <StatusHistoryTimeline items={selected.status_history} />
        </DetailModal>
      )}

      {mode && (
        <div className="md-page__overlay" role="presentation">
          <div
            className="card md-page__dialog purchase__dialog purchase__dialog--request"
            role="dialog"
            aria-modal="true"
          >
            <div className="md-page__dialog-head">
              <h2>{editing ? "Sửa yêu cầu mua hàng" : "Tạo yêu cầu mua hàng"}</h2>
              <button
                type="button"
                className="md-page__close"
                onClick={closeForm}
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
                <LocalField label="Phòng ban của bạn">
                  <div className="input purchase__readonly-field">
                    {departmentName || "Theo tài khoản đăng nhập"}
                  </div>
                </LocalField>
                <LocalField label="Ngày cần hàng" required>
                  <input
                    className="input"
                    type="date"
                    required
                    min={minNeededDate}
                    value={form.needed_date}
                    onChange={(e) =>
                      setForm({ ...form, needed_date: e.target.value })
                    }
                  />
                </LocalField>
                {/* MỘT ô thay cho cặp "Mục đích" + "Ghi chú" (chủ chốt 07/08/2026). Hai ô cho
                    cùng một ý khiến người khai phân vân chữ nào bỏ vào đâu, rồi mỗi người điền một
                    kiểu. Dữ liệu cũ đã được migration 0171 dồn sang một ô. */}
                <LocalField label="Nội dung / mục đích" wide required>
                  <textarea
                    className="input purchase__textarea"
                    required
                    value={form.content}
                    onChange={(e) =>
                      setForm({ ...form, content: e.target.value })
                    }
                    placeholder="VD: thiếu giấy cho lệnh sản xuất SX-2026-014, cần trước ngày đóng gói"
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
                      <select
                        className="input purchase__line-name"
                        required
                        value={line.item_name}
                        onChange={(e) =>
                          selectCatalogItem(index, e.target.value)
                        }
                      >
                        <option value="">Chọn vật tư</option>
                        {line.item_name &&
                          !itemCatalog.some(
                            (item) => item.item_name === line.item_name,
                          ) && (
                            <option value={line.item_name}>
                              {line.item_name}
                            </option>
                          )}
                        {itemCatalog.map((item) => (
                          <option key={item.item_name} value={item.item_name}>
                            {item.item_name} · {item.unit} · từ{" "}
                            {item.supplier_count > 1
                              ? ` · ${item.supplier_count} NCC`
                              : ""}
                          </option>
                        ))}
                      </select>
                      <input
                        className="input purchase__line-unit"
                        required
                        readOnly
                        placeholder="Tự điền"
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
                  onClick={closeForm}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving}>
                  {editing ? "Cập nhật yêu cầu" : "Lưu yêu cầu"}
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

/** Nhãn trạng thái của một PHIẾU MUA. Dùng chung cho ô tình trạng dòng và danh sách phiếu. */
const PHIEU_STATUS_META: Record<PurchaseRequestStatus, { label: string; tone: string }> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Bị từ chối", tone: "rejected" },
  purchased: { label: "Đã mua", tone: "purchased" },
  partially_received: { label: "Giao một phần", tone: "partial" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

function StatusBadgePhieu({ status }: { status: PurchaseRequestStatus }) {
  const meta = PHIEU_STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>{meta.label}</span>
  );
}

/**
 * Tình trạng của MỘT DÒNG vật tư.
 *
 * Ba ca phải hiện KHÁC nhau, gộp lại là nói dối:
 *   1. Chưa ai lập phiếu cho yêu cầu này ⇒ "Chờ thu mua lập phiếu".
 *   2. Đã có phiếu nhưng dòng này không nối được ⇒ phiếu lập TRƯỚC 05/08/2026, hồi đó chưa có nối
 *      dòng ↔ dòng. Nói thẳng "chưa rõ, xem danh sách phiếu bên dưới" — KHÔNG đoán theo tên hàng,
 *      đoán trượt thì im lặng hiện sai và không ai biết.
 *   3. Nối được ⇒ hiện trạng thái phiếu, kèm cảnh báo nếu NCC giao thiếu hoặc phiếu bị từ chối.
 */
function LineFulfilmentCell({
  line,
  coPhieu,
}: {
  line: DepartmentPurchaseRequestLineOut;
  coPhieu: boolean;
}) {
  if (!line.fulfilment) {
    return coPhieu ? (
      <small>Chưa rõ — phiếu lập trước khi hệ ghi nhận theo dòng</small>
    ) : (
      <small>Chờ thu mua lập phiếu</small>
    );
  }
  const f = line.fulfilment;
  const nhan = f.received_quantity ?? f.ordered_quantity;
  const thieu = f.purchase_status === "received" && nhan < f.ordered_quantity;
  return (
    <>
      <StatusBadgePhieu status={f.purchase_status} />
      <br />
      <small>
        {f.purchase_code}
        {f.ordered_quantity !== line.quantity && (
          // Bộ phận xin 1.000 tờ mà NCC bán theo ram thì thu mua đổi đơn vị — hiện cả hai con số
          // ngay tại dòng, thay vì để hai nơi rời nhau không ai đối chiếu.
          <> · mua {f.ordered_quantity.toLocaleString("vi-VN")} {f.ordered_unit}</>
        )}
        {f.purchase_status === "received" && (
          <> · nhận {nhan.toLocaleString("vi-VN")} {f.ordered_unit}</>
        )}
      </small>
      {thieu && <small className="pay-short">Giao thiếu so với số đặt</small>}
      {f.purchase_status === "rejected" && (
        <small className="pay-short">Cần lập phiếu lại cho dòng này</small>
      )}
    </>
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
