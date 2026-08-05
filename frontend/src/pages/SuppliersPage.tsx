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
  type PurchaseRequestRow,
  type SupplierInput,
  type SupplierItemCatalogRow,
  type SupplierItemInput,
  type SupplierRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import "./master-data.css";
import "./purchase.css";

const PAGE_SIZE = 12;

function emptySupplierItem(): SupplierItemInput {
  return {
    item_name: "",
    unit: "",
    unit_price: 0,
    vat_percent: 0,
    note: "",
  };
}

function emptySupplier(): SupplierInput {
  return {
    name: "",
    tax_code: "",
    phone: "",
    email: "",
    address: "",
    contact_name: "",
    supplier_group: "",
    payment_terms: "",
    status: "active",
    note: "",
    items: [emptySupplierItem()],
  };
}

function fromSupplier(row: SupplierRow): SupplierInput {
  return {
    name: row.name,
    tax_code: row.tax_code ?? "",
    phone: row.phone ?? "",
    email: row.email ?? "",
    address: row.address ?? "",
    contact_name: row.contact_name ?? "",
    supplier_group: row.supplier_group ?? "",
    payment_terms: row.payment_terms ?? "",
    status: row.status,
    note: row.note ?? "",
    items: row.items.length
      ? row.items.map((item) => ({
          item_name: item.item_name,
          unit: item.unit,
          unit_price: item.unit_price,
          vat_percent: item.vat_percent ?? 0,
          note: item.note ?? "",
        }))
      : [emptySupplierItem()],
  };
}

function cleanSupplierItems(items: SupplierItemInput[] = []): SupplierItemInput[] {
  return items
    .map((item) => ({
      item_name: (item.item_name ?? "").trim(),
      unit: (item.unit ?? "").trim(),
      unit_price: Number(item.unit_price || 0),
      vat_percent: Number(item.vat_percent || 0),
      note: (item.note ?? "").trim() || null,
    }))
    .filter(
      (item) =>
        item.item_name ||
        item.unit ||
        item.unit_price > 0 ||
        item.vat_percent > 0 ||
        item.note,
    );
}

function cleanSupplier(input: SupplierInput): SupplierInput {
  const trimOptional = (v?: string | null) => {
    const s = (v ?? "").trim();
    return s || null;
  };
  return {
    name: (input.name ?? "").trim(),
    tax_code: (input.tax_code ?? "").trim(),
    phone: (input.phone ?? "").trim(),
    email: (input.email ?? "").trim(),
    address: (input.address ?? "").trim(),
    contact_name: (input.contact_name ?? "").trim(),
    supplier_group: (input.supplier_group ?? "").trim(),
    payment_terms: trimOptional(input.payment_terms),
    status: input.status ?? "active",
    note: trimOptional(input.note),
    items: cleanSupplierItems(input.items),
  };
}

const REQUIRED_SUPPLIER_FIELDS: Array<[keyof SupplierInput, string]> = [
  ["name", "Tên nhà cung cấp"],
  ["supplier_group", "Nhóm"],
  ["tax_code", "Mã số thuế"],
  ["contact_name", "Người liên hệ"],
  ["phone", "Số điện thoại"],
  ["email", "Email"],
  ["address", "Địa chỉ"],
];

function formatVND(amount: number): string {
  return new Intl.NumberFormat("vi-VN").format(Math.round(amount)) + " đ";
}

function getPOStatusLabel(status: string): { label: string; className: string } {
  switch (status) {
    case "draft":
      return { label: "Nháp", className: "purchase__status--draft" };
    case "pending":
      return { label: "Chờ duyệt", className: "purchase__status--pending" };
    case "approved":
      return { label: "Đã duyệt", className: "purchase__status--approved" };
    case "purchased":
      return { label: "Đã mua hàng", className: "purchase__status--purchased" };
    case "received":
      return { label: "Đã nhập kho", className: "purchase__status--received" };
    case "rejected":
      return { label: "Từ chối", className: "purchase__status--rejected" };
    case "cancelled":
      return { label: "Đã hủy", className: "purchase__status--cancelled" };
    default:
      return { label: status, className: "purchase__status--draft" };
  }
}

export function SuppliersPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("thu_mua", "create");
  const canUpdate = can("thu_mua", "update");

  const [allSuppliers, setAllSuppliers] = useState<SupplierRow[]>([]);
  const [rows, setRows] = useState<SupplierRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"all" | "active" | "inactive">("all");
  const [selectedGroup, setSelectedGroup] = useState<string>("all");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // Side Drawer State
  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [selected, setSelected] = useState<SupplierRow | null>(null);
  const [form, setForm] = useState<SupplierInput>(emptySupplier());
  const [formError, setFormError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"info" | "items" | "history">("info");

  // Tab 2 internal item search filter
  const [itemSearchQ, setItemSearchQ] = useState("");

  // Danh mục vật tư GỘP của mọi NCC — dùng để gợi ý tên khi khai mặt hàng.
  //
  // Vì sao cần: hệ nhận diện "cùng một vật tư" bằng CHÍNH CHUỖI TÊN (viết thường, cắt khoảng
  // trắng). NCC A khai "Giấy Duplex 350gsm", NCC B khai "Giay Duplex 350" là hai vật tư khác nhau
  // ⇒ không so được giá giữa hai bên, và lúc gom mua hàng máy không bao giờ gợi ý B thay cho A.
  // Gợi ý ở đây để tên tự hội tụ, thay vì dựng một bảng vật tư trung tâm.
  const [itemCatalog, setItemCatalog] = useState<SupplierItemCatalogRow[]>([]);
  useEffect(() => {
    if (!token) return;
    api.suppliers
      .itemCatalog(token)
      .then((res) => setItemCatalog(res.items))
      .catch(() => setItemCatalog([]));   // không chặn: mất gợi ý thì vẫn gõ tay được
  }, [token]);

  // Tab 3 Purchase Orders History State
  const [poList, setPoList] = useState<PurchaseRequestRow[]>([]);
  const [poLoading, setPoLoading] = useState(false);
  const [poError, setPoError] = useState<string | null>(null);

  // Load all suppliers (active + inactive) để tính stats — gọi 2 lần riêng biệt rồi merge
  // tránh phụ thuộc vào backend có hỗ trợ status=null hay không
  const loadAll = useCallback(() => {
    if (!token) return;
    Promise.all([
      api.suppliers.list(token, { size: 500, sort: "name", status: "active" }),
      api.suppliers.list(token, { size: 500, sort: "name", status: "inactive" }),
    ])
      .then(([activeRes, inactiveRes]) => {
        setAllSuppliers([...activeRes.items, ...inactiveRes.items]);
      })
      .catch(() => {
        // non-blocking; stats sẽ fallback về rows
      });
  }, [token]);

  // Load paginated list with search and filters
  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.suppliers
      .list(token, {
        q: q.trim() || undefined,
        status: status === "all" ? null : status,
        supplier_group: selectedGroup === "all" ? null : selectedGroup,
        sort: "name",
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh sách nhà cung cấp.");
      })
      .finally(() => setLoading(false));
  }, [token, q, status, selectedGroup, page]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    load();
  }, [load]);

  // Dynamic Supplier Group Pills — chỉ lấy từ data thực, KHÔNG hardcode
  const groupPills = useMemo(() => {
    const src = allSuppliers.length > 0 ? allSuppliers : rows;
    const fromData = Array.from(
      new Set(src.map((s) => s.supplier_group).filter(Boolean)),
    ) as string[];
    fromData.sort((a, b) => a.localeCompare(b, "vi"));

    return fromData.map((grp) => {
      const count = allSuppliers.filter((s) => s.supplier_group === grp).length
        || rows.filter((s) => s.supplier_group === grp).length;
      return { group: grp, count };
    });
  }, [allSuppliers, rows]);

  // Dải pill lọc theo nhóm ĐANG TẮT (JSX bị comment ở ~500). Giữ nguyên phần tính ở trên để bật
  // lại chỉ cần bỏ comment khối JSX. `selectedGroup` vẫn chạy thật — nó đi thẳng vào tham số
  // `supplier_group` của API, chỉ là hiện chưa có nút nào đổi nó. Hai dòng `void` dưới đây chỉ để
  // TypeScript thôi báo "khai mà không dùng" — không chạy gì, không đổi hành vi.
  void groupPills;
  void setSelectedGroup;

  // Metric stats — fallback về rows khi allSuppliers chưa load xong
  const stats = useMemo(() => {
    if (allSuppliers.length > 0) {
      return {
        totalCount: allSuppliers.length,
        activeCount: allSuppliers.filter((s) => s.status === "active").length,
        inactiveCount: allSuppliers.filter((s) => s.status === "inactive").length,
      };
    }
    // Fallback: dùng total từ API + rows để có thông tin cơ bản
    return {
      totalCount: total,
      activeCount: rows.filter((s) => s.status === "active").length,
      inactiveCount: rows.filter((s) => s.status === "inactive").length,
    };
  }, [allSuppliers, rows, total]);

  // Load Purchase Orders when Tab 3 is active and editing existing supplier
  useEffect(() => {
    if (activeTab === "history" && selected && token) {
      setPoLoading(true);
      setPoError(null);
      // api.purchaseRequests.list filters by supplier_id
      api.purchaseRequests
        .list(token, { supplier_id: selected.id, size: 50 })
        .then((res) => {
          setPoList(res.items);
        })
        .catch((err) => {
          if (err instanceof ApiError) setPoError(err.message);
          else setPoError("Không tải được lịch sử mua hàng của nhà cung cấp này.");
        })
        .finally(() => setPoLoading(false));
    }
  }, [activeTab, selected, token]);

  function openCreate() {
    setSelected(null);
    setForm(emptySupplier());
    setFormError(null);
    setActiveTab("info");
    setItemSearchQ("");
    setPoList([]);
    setMode("create");
  }

  function openEdit(row: SupplierRow) {
    setSelected(row);
    setForm(fromSupplier(row));
    setFormError(null);
    setActiveTab("info");
    setItemSearchQ("");
    setPoList([]);
    setMode("edit");
  }

  function closeDrawer() {
    setMode(null);
    setSelected(null);
  }

  function setSupplierItem(index: number, patch: Partial<SupplierItemInput>) {
    setForm((current) => ({
      ...current,
      items: (current.items ?? [emptySupplierItem()]).map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    }));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    const payload = cleanSupplier(form);
    const missing = REQUIRED_SUPPLIER_FIELDS.filter(
      ([key]) => !String(payload[key] ?? "").trim(),
    ).map(([, label]) => label);
    if (missing.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missing.join(", ")}.`);
      setActiveTab("info");
      return;
    }
    if (
      (payload.items ?? []).some(
        (item) => !item.item_name || !item.unit || item.unit_price <= 0,
      )
    ) {
      setFormError(
        "Mỗi mặt hàng nhà cung cấp cần nhập đủ tên, ĐVT và đơn giá lớn hơn 0.",
      );
      setActiveTab("items");
      return;
    }
    if (
      (payload.items ?? []).some(
        (item) => (item.vat_percent ?? 0) < 0 || (item.vat_percent ?? 0) > 100,
      )
    ) {
      setFormError("VAT mặt hàng nhà cung cấp phải từ 0 đến 100.");
      setActiveTab("items");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (mode === "edit" && selected) {
        await api.suppliers.update(token, selected.id, payload);
      } else {
        await api.suppliers.create(token, payload);
      }
      closeDrawer();
      loadAll();
      load();
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError("Không lưu được nhà cung cấp.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(row: SupplierRow) {
    if (!token || !canUpdate) return;
    try {
      await api.suppliers.toggleActive(token, row.id);
      loadAll();
      load();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không đổi được trạng thái nhà cung cấp.");
    }
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Nhà cung cấp (403).
        </div>
      </main>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Items displayed in Tab 2 with internal search filter
  const itemsInForm = form.items ?? [emptySupplierItem()];
  const filteredFormItems = itemsInForm
    .map((item, originalIndex) => ({ item, originalIndex }))
    .filter(({ item }) => {
      if (!itemSearchQ.trim()) return true;
      const qLower = itemSearchQ.trim().toLowerCase();
      return (
        item.item_name.toLowerCase().includes(qLower) ||
        item.unit.toLowerCase().includes(qLower) ||
        (item.note ?? "").toLowerCase().includes(qLower)
      );
    });

  return (
    <main className="md-page">
      {/* Header Section */}
      <header className="md-page__head">
        <p className="eyebrow">Thu mua</p>
        <h1 className="md-page__title">Nhà cung cấp</h1>
        <p className="md-page__sub">
          Danh mục đối tác do bộ phận mua hàng quản lý, dùng để chọn vào phiếu
          yêu cầu và phiếu mua hàng.
        </p>
      </header>

      {/* 3 Metric Stats Cards at top */}
      <div className="supplier-stats">
        <div className="supplier-stat-card">
          <div className="supplier-stat-icon">🏢</div>
          <div className="supplier-stat-info">
            <span className="supplier-stat-val">{stats.totalCount}</span>
            <span className="supplier-stat-label">Tổng Nhà cung cấp</span>
          </div>
        </div>

        <div className="supplier-stat-card">
          <div className="supplier-stat-icon supplier-stat-icon--green">✓</div>
          <div className="supplier-stat-info">
            <span className="supplier-stat-val supplier-stat-val--green">
              {stats.activeCount}
            </span>
            <span className="supplier-stat-label">Đang hợp tác</span>
          </div>
        </div>

        <div className="supplier-stat-card">
          <div className="supplier-stat-icon supplier-stat-icon--amber">–</div>
          <div className="supplier-stat-info">
            <span className="supplier-stat-val supplier-stat-val--amber">
              {stats.inactiveCount}
            </span>
            <span className="supplier-stat-label">Tạm ngừng</span>
          </div>
        </div>
      </div>



      {/* Search Toolbar */}
      <div className="md-page__toolbar">
        <form
          className="md-page__search"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            load();
          }}
        >
          <input
            className="input"
            placeholder="Tìm Tên NCC, MST, SĐT, liên hệ, tên mặt hàng..."
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
        </form>

        <select
          className="input purchase__select"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as "all" | "active" | "inactive");
            setPage(1);
          }}
        >
          <option value="active">Đang hợp tác</option>
          <option value="inactive">Tạm ngừng hợp tác</option>
          <option value="all">Tất cả trạng thái</option>
        </select>

        <div className="md-page__toolbar-spacer" />

        {canCreate && (
          <Button variant="primary" onClick={openCreate}>
            + Thêm NCC
          </Button>
        )}
      </div>

      {/* Lọc nhanh theo nhóm NCC. Nhóm lấy từ dữ liệu thật (`groupPills`), chưa nhóm nào được đặt
          thì cả dải tự ẩn — không bày ô lọc rỗng. Lọc chạy ở SERVER qua `supplier_group`, nên
          đếm ở pill là đếm toàn bộ NCC chứ không phải mỗi trang đang xem. */}
      {/* {groupPills.length > 0 && (
        <div className="supplier-pills-bar">
          <button
            type="button"
            className={`supplier-pill${selectedGroup === "all" ? " supplier-pill--active" : ""}`}
            onClick={() => {
              setSelectedGroup("all");
              setPage(1);
            }}
          >
            Tất cả
            <span className="supplier-pill__count">
              {allSuppliers.length || rows.length}
            </span>
          </button>
          {groupPills.map((p) => (
            <button
              key={p.group}
              type="button"
              className={`supplier-pill${selectedGroup === p.group ? " supplier-pill--active" : ""}`}
              onClick={() => {
                setSelectedGroup(p.group);
                setPage(1);
              }}
            >
              {p.group}
              <span className="supplier-pill__count">{p.count}</span>
            </button>
          ))}
        </div>
      )} */}

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      {/* Modern Table List */}
      <div className="card md-page__tablewrap supplier__tablewrap">
        <table className="md-page__table supplier__table">
          <colgroup>
            <col className="supplier__col-name" />
            <col className="supplier__col-contact" />
            <col className="supplier__col-items" />
            <col className="supplier__col-status" />
            {canUpdate && <col className="supplier__col-actions" />}
          </colgroup>
          <thead>
            <tr>
              <th>Nhà cung cấp</th>
              <th>Người liên hệ</th>
              <th>Mặt hàng</th>
              <th>Trạng thái</th>
              {canUpdate && <th className="md-page__actions-col">Thao tác</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={canUpdate ? 5 : 4} className="md-page__status">
                  Đang tải dữ liệu...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={canUpdate ? 5 : 4} className="md-page__empty">
                  Chưa có nhà cung cấp phù hợp.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="md-page__row"
                  onClick={canUpdate ? () => openEdit(row) : undefined}
                >
                  {/* Column 1: Supplier Name + Group Badge + Tax Code */}
                  <td className="supplier__name-cell">
                    <strong className="supplier__primary">{row.name}</strong>
                    <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap", marginTop: "4px" }}>
                      {/* {row.supplier_group && (
                        <span className="supplier-group-badge">{row.supplier_group}</span>
                      )} */}
                      {row.tax_code && (
                        <span className="md-page__mono md-page__muted" style={{ fontSize: "12px" }}>
                          MST: {row.tax_code}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Column 2: Contact Person + Phone link / Email */}
                  <td className="supplier__contact-cell">
                    <div>
                      <strong>{row.contact_name || <span className="md-page__muted">—</span>}</strong>
                    </div>
                    <div className="supplier__secondary" style={{ display: "flex", flexDirection: "column", gap: "2px", fontSize: "12px" }}>
                      {row.phone && (
                        <a
                          href={`tel:${row.phone}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{ color: "var(--moss-deep)", textDecoration: "none", fontWeight: 500 }}
                        >
                         {row.phone}
                        </a>
                      )}
                      {row.email && (
                        <a
                          href={`mailto:${row.email}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{ color: "var(--ash)", textDecoration: "none" }}
                        >
                         {row.email}
                        </a>
                      )}
                      {!row.phone && !row.email && <span className="md-page__muted">—</span>}
                    </div>
                  </td>

                  {/* Column 3: Mặt hàng — chỉ hiện số đếm */}
                  <td className="supplier__items-cell">
                    {row.items.length > 0 ? (
                      <span className="ir-tab__count" style={{ fontSize: "12px" }}>
                        {row.items.length} mặt hàng
                      </span>
                    ) : (
                      <span className="md-page__muted">Chưa có báo giá</span>
                    )}
                  </td>

                  {/* Column 5: Status Pill */}
                  <td>
                    <span
                      className={`md-purchase__status-badge ${
                        row.status === "active" ? "is-active" : "is-inactive"
                      }`}
                    >
                      {row.status === "active" ? "Hoạt động" : "Tạm ngừng"}
                    </span>
                  </td>

                  {/* Column 6: Actions */}
                  {canUpdate && (
                    <td
                      className="md-page__actions-col supplier__actions-cell"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => openEdit(row)}
                      >
                        Xem/Sửa
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost md-page__rowbtn"
                        onClick={() => toggle(row)}
                      >
                        {row.status === "active" ? "Ngừng" : "Mở"}
                      </button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng số: {total} NCC · Trang {page}/{totalPages}
          </span>
          <div className="md-page__pager-btns">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Trước
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Sau
            </button>
          </div>
        </div>
      )}

      {/* Full Height Side Drawer (Replaces centered modal dialog) */}
      {mode && (
        <div className="supplier-drawer-overlay" role="presentation" onClick={closeDrawer}>
          <div
            className="supplier-drawer"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drawer Header */}
            <div className="supplier-drawer__head">
              <div className="supplier-drawer__head-info">
                <h2>
                  {mode === "edit"
                    ? `Chi tiết NCC: ${selected?.name}`
                    : "Thêm nhà cung cấp mới"}
                </h2>
                {selected && (
                  <span
                    className={`md-purchase__status-badge ${
                      selected.status === "active" ? "is-active" : "is-inactive"
                    }`}
                  >
                    {selected.status === "active" ? "Hoạt động" : "Tạm ngừng"}
                  </span>
                )}
              </div>
              <button
                type="button"
                className="md-page__close"
                onClick={closeDrawer}
                title="Đóng cửa sổ"
              >
                ×
              </button>
            </div>

            {/* Drawer 3-Tab Stepper */}
            <div className="supplier-drawer__tabs">
              <button
                type="button"
                className={`supplier-drawer__tab ${
                  activeTab === "info" ? "supplier-drawer__tab--active" : ""
                }`}
                onClick={() => setActiveTab("info")}
              >
                Thông tin chung
              </button>

              <button
                type="button"
                className={`supplier-drawer__tab ${
                  activeTab === "items" ? "supplier-drawer__tab--active" : ""
                }`}
                onClick={() => setActiveTab("items")}
              >
                Bảng giá vật tư
                {itemsInForm.length > 0 && (
                  <span className="supplier-tab-count">{itemsInForm.length}</span>
                )}
              </button>

              {mode === "edit" && (
                <button
                  type="button"
                  className={`supplier-drawer__tab ${
                    activeTab === "history" ? "supplier-drawer__tab--active" : ""
                  }`}
                  onClick={() => setActiveTab("history")}
                >
                  Lịch sử mua hàng
                </button>
              )}
            </div>

            {/* Drawer Form Content */}
            <form
              style={{ display: "flex", flexDirection: "column", height: "calc(100% - 120px)" }}
              onSubmit={save}
            >
              <div className="supplier-drawer__body">
                {formError && (
                  <div className="banner banner--error" role="alert">
                    {formError}
                  </div>
                )}

                {/* TAB 1: Thông tin chung & Pháp lý */}
                {activeTab === "info" && (
                  <div className="md-page__form-grid">
                    <LocalField label="Tên nhà cung cấp" required>
                      <input
                        className="input"
                        required
                        value={form.name}
                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                        placeholder="VD: Công ty TNHH Giấy Việt Triều"
                      />
                    </LocalField>

                    <LocalField label="Nhóm" required>
                      <input
                        className="input"
                        required
                        value={form.supplier_group ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, supplier_group: e.target.value })
                        }
                        placeholder="Giấy in, Mực & Hóa chất, Gia công ngoài..."
                      />
                    </LocalField>

                    <LocalField label="Mã số thuế" required>
                      <input
                        className="input md-page__mono"
                        required
                        value={form.tax_code ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, tax_code: e.target.value })
                        }
                        placeholder="0101234567"
                      />
                    </LocalField>

                    <LocalField label="Người liên hệ" required>
                      <input
                        className="input"
                        required
                        value={form.contact_name ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, contact_name: e.target.value })
                        }
                        placeholder="VD: Anh Nam (Kinh doanh)"
                      />
                    </LocalField>

                    <LocalField label="Số điện thoại" required>
                      <input
                        className="input"
                        required
                        value={form.phone ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, phone: e.target.value })
                        }
                        placeholder="0988123456"
                      />
                    </LocalField>

                    <LocalField label="Email" required>
                      <input
                        className="input"
                        required
                        type="email"
                        value={form.email ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, email: e.target.value })
                        }
                        placeholder="kinhdoanh@viettrieu.vn"
                      />
                    </LocalField>

                    <LocalField label="Điều khoản thanh toán">
                      <input
                        className="input"
                        value={form.payment_terms ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, payment_terms: e.target.value })
                        }
                        placeholder="Công nợ 30 ngày, Thanh toán ngay..."
                      />
                    </LocalField>

                    <LocalField label="Trạng thái">
                      <select
                        className="input"
                        value={form.status ?? "active"}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            status: e.target.value as "active" | "inactive",
                          })
                        }
                      >
                        <option value="active">Hoạt động (Active)</option>
                        <option value="inactive">Tạm ngừng (Inactive)</option>
                      </select>
                    </LocalField>

                    <LocalField label="Địa chỉ" wide required>
                      <input
                        className="input"
                        required
                        value={form.address ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, address: e.target.value })
                        }
                        placeholder="Số 15, Đường Cầu Diễn, Bắc Từ Liêm, Hà Nội"
                      />
                    </LocalField>

                    <LocalField label="Ghi chú" wide>
                      <textarea
                        className="input purchase__textarea"
                        value={form.note ?? ""}
                        onChange={(e) => setForm({ ...form, note: e.target.value })}
                        placeholder="Ghi chú thêm về năng lực, ưu đãi chiết khấu..."
                      />
                    </LocalField>
                  </div>
                )}

                {/* TAB 2: Bảng giá mặt hàng vật tư */}
                {activeTab === "items" && (
                  <section className="supplier__items-section">
                    <div className="supplier__items-head">
                      <div>
                        <h3 style={{ fontSize: "16px", fontWeight: "bold" }}>
                          Danh mục &amp; Báo giá Vật tư
                        </h3>
                        <p className="md-page__muted">
                          Khai báo đơn giá &amp; VAT hiện tại để gợi ý tự động khi lập Phiếu Mua Hàng.
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() =>
                          setForm((current) => ({
                            ...current,
                            items: [...(current.items ?? []), emptySupplierItem()],
                          }))
                        }
                      >
                        + Thêm mặt hàng
                      </button>
                    </div>

                    {/* Toolbar tìm kiếm vật tư trong drawer */}
                    <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                      <input
                        className="input"
                        placeholder="Tìm vật tư trong bảng giá..."
                        value={itemSearchQ}
                        onChange={(e) => setItemSearchQ(e.target.value)}
                        style={{ maxWidth: "280px" }}
                      />
                      <span className="md-page__muted" style={{ fontSize: "13px" }}>
                        Hiển thị {filteredFormItems.length} / {itemsInForm.length} vật tư
                      </span>
                    </div>

                    {/* Nguồn gợi ý dùng chung cho MỌI dòng — khai một lần, đừng lặp trong map. */}
                    <datalist id="supplier-item-name-suggestions">
                      {itemCatalog.map((c) => (
                        <option key={c.item_name} value={c.item_name}>
                          {c.unit}
                          {c.supplier_count > 1 ? ` · ${c.supplier_count} NCC đang bán` : ""}
                        </option>
                      ))}
                    </datalist>

                    {/* Table Editor */}
                    <div className="supplier__item-editor">
                      <div className="supplier__item-labels" aria-hidden="true" style={{ gridTemplateColumns: "minmax(180px, 1.4fr) minmax(70px, 0.5fr) minmax(110px, 0.8fr) minmax(65px, 0.5fr) minmax(120px, 0.8fr) minmax(130px, 1fr) 36px" }}>
                        <span>Tên vật tư *</span>
                        <span>ĐVT *</span>
                        <span>Đơn giá (chưa VAT) *</span>
                        <span>VAT %</span>
                        <span>Giá sau VAT</span>
                        <span>Ghi chú</span>
                        <span></span>
                      </div>

                      {filteredFormItems.map(({ item, originalIndex }) => {
                        const priceAfterVAT =
                          (item.unit_price || 0) * (1 + (item.vat_percent || 0) / 100);

                        return (
                          <div
                            className="supplier__item-row"
                            key={originalIndex}
                            style={{ gridTemplateColumns: "minmax(180px, 1.4fr) minmax(70px, 0.5fr) minmax(110px, 0.8fr) minmax(65px, 0.5fr) minmax(120px, 0.8fr) minmax(130px, 1fr) 36px" }}
                          >
                            {/* `datalist` chứ không phải `select`: tên MỚI phải gõ được, vì đây
                                chính là chỗ vật tư mới vào danh mục. Gợi ý chỉ để tên hội tụ. */}
                            <input
                              className="input"
                              list="supplier-item-name-suggestions"
                              placeholder="VD: Giấy Duplex 350gsm"
                              value={item.item_name}
                              onChange={(e) => {
                                const ten = e.target.value;
                                // Gõ/chọn trúng tên đã có mà chưa khai ĐVT thì điền hộ — đơn vị
                                // lệch nhau cũng làm hai bên không so được với nhau.
                                const trung = itemCatalog.find(
                                  (c) =>
                                    c.item_name.trim().toLowerCase() ===
                                    ten.trim().toLowerCase(),
                                );
                                setSupplierItem(originalIndex, {
                                  item_name: ten,
                                  ...(trung && !item.unit ? { unit: trung.unit } : {}),
                                });
                              }}
                            />
                            <input
                              className="input"
                              placeholder="tờ, kg..."
                              value={item.unit}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, { unit: e.target.value })
                              }
                            />
                            <input
                              className="input purchase__number-input"
                              type="number"
                              min="0"
                              step="1"
                              placeholder="2200"
                              value={item.unit_price > 0 ? item.unit_price : ""}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  unit_price: Number(e.target.value || 0),
                                })
                              }
                            />
                            <input
                              className="input purchase__number-input"
                              type="number"
                              min="0"
                              max="100"
                              step="0.01"
                              placeholder="10"
                              value={(item.vat_percent ?? 0) >= 0 ? item.vat_percent : ""}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  vat_percent: Number(e.target.value || 0),
                                })
                              }
                            />
                            <div className="supplier-item-vat-calculated">
                              {item.unit_price > 0 ? formatVND(priceAfterVAT) : "—"}
                            </div>
                            <input
                              className="input"
                              placeholder="Nếu có"
                              value={item.note ?? ""}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, { note: e.target.value })
                              }
                            />
                            <button
                              type="button"
                              className="supplier__item-remove"
                              disabled={itemsInForm.length <= 1}
                              title="Xóa dòng"
                              aria-label="Xóa mặt hàng"
                              onClick={() =>
                                setForm((current) => ({
                                  ...current,
                                  items: (current.items ?? []).filter(
                                    (_, i) => i !== originalIndex,
                                  ),
                                }))
                              }
                            >
                              ×
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}

                {/* TAB 3: Lịch sử Mua hàng (PMH) */}
                {activeTab === "history" && (
                  <div>
                    <h3 style={{ fontSize: "16px", fontWeight: "bold", marginBottom: "4px" }}>
                      Lịch sử Phiếu Mua Hàng (PMH)
                    </h3>
                    <p className="md-page__muted" style={{ marginBottom: "16px" }}>
                      Danh sách các đơn mua hàng đã được giao cho NCC này xử lý.
                    </p>

                    {mode === "create" || !selected ? (
                      <div className="banner banner--info">
                        Vui lòng lưu thông tin nhà cung cấp trước khi xem lịch sử mua hàng.
                      </div>
                    ) : poLoading ? (
                      <div className="md-page__status">Đang tải lịch sử mua hàng...</div>
                    ) : poError ? (
                      <div className="banner banner--error">{poError}</div>
                    ) : poList.length === 0 ? (
                      <div className="md-page__empty">
                        Chưa có Phiếu Mua Hàng nào phát sinh với nhà cung cấp này.
                      </div>
                    ) : (
                      <div className="card md-page__tablewrap">
                        <table className="md-page__table">
                          <thead>
                            <tr>
                              <th>Mã PMH</th>
                              <th>Ngày tạo</th>
                              <th>Mục đích / Người tạo</th>
                              <th style={{ textAlign: "right" }}>Tổng giá trị</th>
                              <th>Trạng thái PMH</th>
                            </tr>
                          </thead>
                          <tbody>
                            {poList.map((po) => {
                              const statusMeta = getPOStatusLabel(po.status);
                              return (
                                <tr key={po.id}>
                                  <td className="md-page__mono" style={{ fontWeight: "bold" }}>
                                    {po.code}
                                  </td>
                                  <td className="md-page__mono">
                                    {new Date(po.created_at).toLocaleDateString("vi-VN")}
                                  </td>
                                  <td>
                                    <div>{po.purpose || "Mua vật tư in"}</div>
                                    <div className="md-page__muted" style={{ fontSize: "12px" }}>
                                      Bởi: {po.created_by_name || "Hệ thống"}
                                    </div>
                                  </td>
                                  <td style={{ textAlign: "right" }}>
                                    <strong className="md-page__price">
                                      {formatVND(po.total_estimate ?? 0)}
                                    </strong>
                                  </td>
                                  <td>
                                    <span className={`purchase__status ${statusMeta.className}`}>
                                      {statusMeta.label}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Drawer Footer Actions */}
              <div className="supplier-drawer__foot">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={closeDrawer}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving}>
                  Lưu nhà cung cấp
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
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
