import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  type PurchaseRequestRow,
  type SupplierInput,
  type SupplierItemImportError,
  type SupplierItemInput,
  type SupplierRow,
} from "../api/client";
import { useDebounced } from "../utils/useDebounced";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { DonViChonTheoHang, MaterialCombobox } from "../components/MaterialCombobox";
import { EmptyRow, EmptyState } from "../components/EmptyState";
import { Icon } from "../components/Icons";
import { RowActionButton } from "../components/RowActionButton";
// Định dạng tiền / ngày lấy từ helper CHUNG. Màn này trước 09/08/2026 tự chép lại `formatVND` và
// gọi thẳng `toLocaleDateString("vi-VN")` — sửa cách hiện tiền một lần là phải đi sửa từng màn.
import { fmtDate, money } from "../utils/format";
import "./master-data.css";
import "./purchase.css";

const PAGE_SIZE = 20;

/** Khoá TRÙNG của một mặt hàng = tên + đơn vị, bỏ hoa/thường và khoảng trắng thừa.
 *  Phải khớp `_khoa_vat_tu` bên service — lệch nhau thì máy nói trùng mà màn hình nói không. */
function khoaVatTu(item: { item_name: string; unit: string }): string {
  return `${item.item_name.trim().replace(/\s+/g, " ").toLowerCase()}|${item.unit
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase()}`;
}

/** Gộp danh sách vừa đọc từ Excel VÀO danh sách đang có trong form.
 *
 *  THÊM VÀO, không thay thế (chủ chốt 07/08/2026): thay cả danh mục là một cú bấm xoá sạch bảng
 *  giá mà không ai lường trước. Trùng tên + đơn vị ⇒ cập nhật dòng đó, không đẻ dòng thứ hai —
 *  hai dòng cùng tên cùng ĐVT khác giá thì form phiếu mua không biết chọn cái nào. */
function gopVatTu(
  dangCo: SupplierItemInput[],
  doc: SupplierItemInput[],
): { items: SupplierItemInput[]; them: number; capNhat: number } {
  // Bỏ dòng trống mà form vẫn luôn chừa sẵn — giữ lại là danh mục có một dòng rác.
  const ket = dangCo.filter((it) => it.item_name.trim() || it.unit.trim());
  const viTri = new Map(ket.map((it, i) => [khoaVatTu(it), i]));
  let them = 0;
  let capNhat = 0;
  for (const moi of doc) {
    const i = viTri.get(khoaVatTu(moi));
    if (i === undefined) {
      viTri.set(khoaVatTu(moi), ket.length);
      ket.push(moi);
      them += 1;
    } else {
      ket[i] = { ...ket[i], ...moi };
      capNhat += 1;
    }
  }
  return { items: ket.length ? ket : [emptySupplierItem()], them, capNhat };
}

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
    // 0 = chưa đặt hạn mức · null = chưa đặt số ngày cho nợ. Hai mặc định này KHÁC nhau về nghĩa,
    // xem hint trên form.
    credit_limit: 0,
    credit_days: null,
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
    credit_limit: row.credit_limit ?? 0,
    credit_days: row.credit_days ?? null,
    status: row.status,
    note: row.note ?? "",
    items: row.items.length
      ? row.items.map((item) => ({
          // PHẢI mang theo cặp mặt hàng gốc: form ghi kiểu replace-all, bỏ sót là mỗi lần mở NCC
          // ra sửa số điện thoại lại XOÁ SẠCH liên kết mặt hàng của cả bảng giá — im lặng, kéo
          // theo bảng so giá trống.
          hang_loai: item.hang_loai,
          hang_id: item.hang_id,
          item_name: item.item_name,
          unit: item.unit,
          unit_price: item.unit_price,
          vat_percent: item.vat_percent ?? 0,
          note: item.note ?? "",
        }))
      : [emptySupplierItem()],
  };
}

function cleanSupplierItems(
  items: SupplierItemInput[] = [],
): SupplierItemInput[] {
  return items
    .map((item) => ({
      hang_loai: item.hang_loai ?? null,
      hang_id: item.hang_id ?? null,
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
    credit_limit: Math.max(0, Math.round(Number(input.credit_limit) || 0)),
    // `?? null` chứ KHÔNG `|| null`: `credit_days = 0` là "trả ngay", một giá trị có thật.
    credit_days:
      input.credit_days == null
        ? null
        : Math.max(0, Math.round(Number(input.credit_days) || 0)),
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

function getPOStatusLabel(status: string): {
  label: string;
  className: string;
} {
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
    case "pending_approval":
      return { label: "Chờ phê duyệt", className: "purchase__status--pending" };
    case "partially_received":
      return { label: "Đã nhập kho một phần", className: "purchase__status--received" };
    default:
      return { label: status, className: "purchase__status--draft" };
  }
}

export function SuppliersPage({
  eventTick = 0,
}: {
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Nhà cung cấp (tách 10/08/2026) — không mượn quyền màn Mua hàng nữa.
  const canCreate = can("nha_cung_cap", "create");
  const canUpdate = can("nha_cung_cap", "update");

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
  /** Lỗi TẢI DANH SÁCH — tách hẳn khỏi `error` (lỗi THAO TÁC).
   *
   *  Vì sao phải hai ô nhớ riêng: `error` bị hàng chục handler thao tác ghi vào (huỷ phiếu, ghi
   *  đợt giao, gán hoá đơn, thậm chí trình duyệt chặn cửa sổ in). Nếu ô rỗng của bảng đọc chung
   *  `error` thì chỉ cần bấm "In phiếu" mà bị chặn pop-up là CẢ BẢNG biến mất, thay bằng "Không
   *  đọc được dữ liệu" — dữ liệu còn nguyên trên máy chủ, chỉ là bảng tự xoá mình vì một lỗi in.
   *  Ô này CHỈ được ghi trong `catch` của hàm tải danh sách. */
  const [listError, setListError] = useState<string | null>(null);
  // Ô nhập vẫn bám state gốc (gõ tới đâu hiện tới đó); chỉ lời gọi máy chủ đọc bản đã
  // chậm 300ms — xem `utils/useDebounced`.
  const qDebounced = useDebounced(q);
  const [forbidden, setForbidden] = useState(false);

  // Side Drawer State
  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [selected, setSelected] = useState<SupplierRow | null>(null);
  const [form, setForm] = useState<SupplierInput>(emptySupplier());
  const [formError, setFormError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"info" | "items" | "history">(
    "info",
  );

  // Tab 2 internal item search filter
  const [itemSearchQ, setItemSearchQ] = useState("");

  // Gợi ý tên vật tư gộp-mọi-NCC (`api.suppliers.itemCatalog`) ĐÃ BỎ: ô Tên vật tư giờ chọn từ
  // DANH MỤC GỐC qua `MaterialCombobox`, nên tên không còn cơ hội trượt ("Couche 150" vs
  // "Couché 150") — thứ mà gợi ý kia sinh ra để chữa.
  // Nhập / xuất Excel bảng giá vật tư.
  //
  // File ĐỌC XONG chỉ nạp vào form, CHƯA vào DB — bảng giá được lưu bằng chính cú "Lưu nhà cung
  // cấp". Nhập thẳng DB thì cú lưu form đó (đang giữ danh sách cũ) sẽ xoá mất phần vừa nhập.
  const fileVatTuRef = useRef<HTMLInputElement | null>(null);
  const [nhapDang, setNhapDang] = useState(false);
  const [nhapKetQua, setNhapKetQua] = useState<
    { them: number; capNhat: number; errors: SupplierItemImportError[] } | null
  >(null);

  async function taiFile(lay: () => Promise<string>, ten: string) {
    if (!token) return;
    try {
      const url = await lay();
      const a = document.createElement("a");
      a.href = url;
      a.download = ten;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Không tải được file Excel.",
      );
    }
  }

  async function nhapExcel(file: File) {
    if (!token) return;
    setNhapDang(true);
    setFormError(null);
    try {
      const res = await api.suppliers.itemsImport(token, file);
      const gop = gopVatTu(
        form.items ?? [],
        res.items.map((r) => ({
          item_name: r.item_name,
          unit: r.unit,
          unit_price: r.unit_price,
          vat_percent: r.vat_percent,
          note: r.note,
        })),
      );
      setForm((current) => ({ ...current, items: gop.items }));
      setNhapKetQua({
        them: gop.them,
        capNhat: gop.capNhat,
        errors: res.errors,
      });
    } catch (err) {
      setNhapKetQua(null);
      setFormError(
        err instanceof ApiError ? err.message : "Không đọc được file Excel.",
      );
    } finally {
      setNhapDang(false);
    }
  }

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
      api.suppliers.list(token, {
        size: 500,
        sort: "name",
        status: "inactive",
      }),
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
    setListError(null);
    api.suppliers
      .list(token, {
        q: qDebounced.trim() || undefined,
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
        else setListError("Không tải được danh sách nhà cung cấp.");
      })
      .finally(() => setLoading(false));
  }, [token, qDebounced, status, selectedGroup, page]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0 || !token) return;
    loadAll();
    load();
  }, [eventTick, token, loadAll, load]);

  // Dynamic Supplier Group Pills — chỉ lấy từ data thực, KHÔNG hardcode
  const groupPills = useMemo(() => {
    const src = allSuppliers.length > 0 ? allSuppliers : rows;
    const fromData = Array.from(
      new Set(src.map((s) => s.supplier_group).filter(Boolean)),
    ) as string[];
    fromData.sort((a, b) => a.localeCompare(b, "vi"));

    return fromData.map((grp) => {
      const count =
        allSuppliers.filter((s) => s.supplier_group === grp).length ||
        rows.filter((s) => s.supplier_group === grp).length;
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
        inactiveCount: allSuppliers.filter((s) => s.status === "inactive")
          .length,
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
          else
            setPoError("Không tải được lịch sử mua hàng của nhà cung cấp này.");
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
    setNhapKetQua(null);
    setPoList([]);
    setMode("create");
  }

  function openEdit(row: SupplierRow) {
    setSelected(row);
    setForm(fromSupplier(row));
    setFormError(null);
    setActiveTab("info");
    setItemSearchQ("");
    setNhapKetQua(null);
    setPoList([]);
    setMode("edit");
  }

  function closeDrawer() {
    setMode(null);
    setSelected(null);
    setNhapKetQua(null);
  }

  function setSupplierItem(index: number, patch: Partial<SupplierItemInput>) {
    setForm((current) => ({
      ...current,
      items: (current.items ?? [emptySupplierItem()]).map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    }));
  }

  // Hệ số quy đổi về đơn vị gốc của TỪNG DÒNG bảng giá (server trả theo mặt hàng + đơn vị đã chọn).
  // Chỉ để HIỂN THỊ cột "Giá quy về gốc" — không lưu, không gửi lên: hệ số là dữ liệu sống, đóng
  // băng nó vào bảng giá NCC là mời sai số vào giữa việc so giá.
  const [quyDoiDong, setQuyDoiDong] = useState<
    Record<number, { donViGocTen: string; heSoVeGoc: number } | null>
  >({});

  function ghiQuyDoiDong(
    index: number,
    info: { donViGocTen: string; heSoVeGoc: number } | null,
  ) {
    setQuyDoiDong((cur) =>
      cur[index]?.donViGocTen === info?.donViGocTen &&
      cur[index]?.heSoVeGoc === info?.heSoVeGoc
        ? cur
        : { ...cur, [index]: info },
    );
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

      {/* DẢI CHỈ SỐ một hàng — bản mẫu `.rdx-compact-kpi` ở DepartmentsPage (và `.pay-kpibar` ở
          màn Công nợ). Trước 09/08/2026 đây là 3 THẺ cao ~78px với emoji tự chế 🏢 ✓ – :
            · emoji đổi hình theo font từng máy và không mang nghĩa cố định — "–" chẳng ai đọc ra
              "tạm ngừng"; icon nay lấy từ bộ `<Icon>` dùng chung nên cùng nét với mọi màn khác.
            · ba thẻ ăn gần một phần tư màn laptop cho thứ đọc mất một giây, đẩy BẢNG NCC (nội dung
              thật của màn) xuống dưới nếp gấp.
          Số ở đây đếm TOÀN BỘ nhà cung cấp (`allSuppliers`, tải riêng), không phải trang đang xem. */}
      <div className="supplier__kpi" aria-label="Tóm tắt nhà cung cấp">
        <div className="supplier__kpi-item">
          <span className="supplier__kpi-icon supplier__kpi-icon--steel">
            <Icon name="truck" size={15} />
          </span>
          <span className="supplier__kpi-body">
            <b className="supplier__kpi-val">{stats.totalCount}</b>
            <span className="supplier__kpi-lbl">Nhà cung cấp</span>
          </span>
        </div>

        <span className="supplier__kpi-sep" aria-hidden="true" />

        <div className="supplier__kpi-item">
          <span className="supplier__kpi-icon supplier__kpi-icon--ok">
            <Icon name="check" size={15} />
          </span>
          <span className="supplier__kpi-body">
            <b className="supplier__kpi-val">{stats.activeCount}</b>
            <span className="supplier__kpi-lbl">Đang hợp tác</span>
          </span>
        </div>

        <span className="supplier__kpi-sep" aria-hidden="true" />

        <div className="supplier__kpi-item">
          <span className="supplier__kpi-icon supplier__kpi-icon--warn">
            <Icon name="ban" size={15} />
          </span>
          <span className="supplier__kpi-body">
            <b className="supplier__kpi-val">{stats.inactiveCount}</b>
            <span className="supplier__kpi-lbl">Tạm ngừng</span>
          </span>
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
          {/* <Button type="submit" variant="ghost">
            Tìm
          </Button> */}
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
          // ⚠️ TÊN LỚP ĐẶT NGƯỢC VỚI TÀI LIỆU: `variant="accent"` mới ra màu CAM thương hiệu,
          // `variant="primary"` ra màu NAVY. Đây là hành động chính DUY NHẤT của màn nền; nút cam
          // thứ hai của màn nằm trong DRAWER ("Lưu nhà cung cấp") — khác hộp nên không phạm luật
          // "tối đa MỘT nút cam mỗi màn / mỗi hộp thoại". Đừng nâng thêm nút nào lên accent.
          <Button variant="accent" onClick={openCreate}>
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
              <EmptyRow colSpan={canUpdate ? 5 : 4} trangThai="dang-tai" />
            ) : listError ? (
              <EmptyRow
                colSpan={canUpdate ? 5 : 4}
                trangThai="loi"
                loi={listError}
                onThuLai={load}
              />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={canUpdate ? 5 : 4}
                icon="truck"
                title="Chưa có nhà cung cấp nào khớp"
                sub="Khai nhà cung cấp trước, rồi mới khai bảng giá vật tư của họ."
              />
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
                    <div
                      style={{
                        display: "flex",
                        gap: "6px",
                        alignItems: "center",
                        flexWrap: "wrap",
                        marginTop: "4px",
                      }}
                    >
                      {/* {row.supplier_group && (
                        <span className="supplier-group-badge">{row.supplier_group}</span>
                      )} */}
                      {row.tax_code && (
                        <span
                          className="md-page__mono md-page__muted"
                          style={{ fontSize: "12px" }}
                        >
                          MST: {row.tax_code}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Column 2: Contact Person + Phone link / Email */}
                  <td className="supplier__contact-cell">
                    <div>
                      <strong>
                        {row.contact_name || (
                          <span className="md-page__muted">—</span>
                        )}
                      </strong>
                    </div>
                    <div
                      className="supplier__secondary"
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "2px",
                        fontSize: "12px",
                      }}
                    >
                      {row.phone && (
                        <a
                          // href={`tel:${row.phone}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            color: "var(--moss-deep)",
                            textDecoration: "none",
                            fontWeight: 500,
                          }}
                        >
                          {row.phone}
                        </a>
                      )}
                      {row.email && (
                        <a
                          // href={`mailto:${row.email}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            color: "var(--ash)",
                            textDecoration: "none",
                          }}
                        >
                          {row.email}
                        </a>
                      )}
                      {!row.phone && !row.email && (
                        <span className="md-page__muted">—</span>
                      )}
                    </div>
                  </td>

                  {/* Column 3: Mặt hàng — chỉ hiện số đếm */}
                  <td className="supplier__items-cell">
                    {row.items.length > 0 ? (
                      <span
                        className="ir-tab__count"
                        style={{ fontSize: "12px" }}
                      >
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

                  {/* Column 6: Actions — TOÀN icon dense (`RowActionButton`), thống nhất với hai
                      màn Thu mua còn lại. Hai nút chữ cũ ngốn ~150px nên cột phải giữ 17% bề
                      ngang chỉ để chứa chữ, cắt mất chỗ của tên NCC và người liên hệ.
                      GIỮ `danger` cho nút Ngừng: nó cắt NCC khỏi mọi ô chọn ở phiếu mua — mất tín
                      hiệu đỏ là bấm nhầm. Chiều ngược lại (Mở lại hợp tác) KHÔNG nguy hiểm nên
                      không tô đỏ; nhãn/icon cũng đổi theo trạng thái, đừng gộp thành một. */}
                  {canUpdate && (
                    <td
                      className="md-page__actions-col supplier__actions-cell"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="purchase__actions purchase__actions--dense">
                        <RowActionButton
                          dense
                          label="Xem / sửa nhà cung cấp"
                          icon="pencil"
                          onClick={() => openEdit(row)}
                        />
                        {row.status === "active" ? (
                          <RowActionButton
                            dense
                            danger
                            label="Ngừng hợp tác"
                            icon="ban"
                            onClick={() => toggle(row)}
                          />
                        ) : (
                          <RowActionButton
                            dense
                            label="Mở lại hợp tác"
                            icon="check"
                            onClick={() => toggle(row)}
                          />
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Chân bảng chuẩn: tổng bên TRÁI, nút chuyển trang bên PHẢI, và CHỈ hiện nút khi thật sự
          có nhiều hơn một trang (mẫu: `.purchase__source-foot` ở PurchaseRequestsPage). Danh mục
          NCC thường gọn trong một trang — treo "Trang 1/1" kèm hai nút mờ là nhiễu mà không nói
          thêm điều gì. */}
      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng {total} NCC
            {totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ""}
          </span>
          {totalPages > 1 && (
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
          )}
        </div>
      )}

      {/* Full Height Side Drawer (Replaces centered modal dialog) */}
      {mode && (
        <div
          className="supplier-drawer-overlay"
          role="presentation"
          onClick={closeDrawer}
        >
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
                  <span className="supplier-tab-count">
                    {itemsInForm.length}
                  </span>
                )}
              </button>

              {mode === "edit" && (
                <button
                  type="button"
                  className={`supplier-drawer__tab ${
                    activeTab === "history"
                      ? "supplier-drawer__tab--active"
                      : ""
                  }`}
                  onClick={() => setActiveTab("history")}
                >
                  Lịch sử mua hàng
                </button>
              )}
            </div>

            {/* Drawer Form Content */}
            <form
              style={{
                display: "flex",
                flexDirection: "column",
                height: "calc(100% - 120px)",
              }}
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
                        onChange={(e) =>
                          setForm({ ...form, name: e.target.value })
                        }
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

                    {/* HẠN MỨC + SỐ NGÀY CHO NỢ — nền của cảnh báo "Vượt hạn mức" và cột "Quá
                        hạn" ở màn Công nợ. Cả hai là CẢNH BÁO MỀM: hệ nói cho người biết, người
                        quyết — không chặn lập/duyệt phiếu ở đâu cả. */}
                    <LocalField label="Hạn mức công nợ (VNĐ)">
                      <input
                        className="input"
                        type="number"
                        min={0}
                        step={1000}
                        value={form.credit_limit ? form.credit_limit : ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            credit_limit: Math.max(
                              0,
                              Math.round(Number(e.target.value) || 0),
                            ),
                          })
                        }
                        placeholder="Để trống = không đặt hạn mức"
                      />
                      <small className="supplier__hint">
                        Để trống hoặc 0 = không đặt hạn mức, sẽ không bao giờ
                        báo vượt.
                      </small>
                    </LocalField>

                    <LocalField label="Số ngày cho nợ">
                      {/* Hai ca KHÁC HẲN NHAU, đừng ép null thành 0: để trống = chưa đặt hạn (đợt
                          giao không vào cột Quá hạn) · 0 = trả ngay (quá hạn ngay hôm sau). */}
                      <input
                        className="input"
                        type="number"
                        min={0}
                        step={1}
                        value={form.credit_days ?? ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            credit_days:
                              e.target.value === ""
                                ? null
                                : Math.max(
                                    0,
                                    Math.round(Number(e.target.value) || 0),
                                  ),
                          })
                        }
                        placeholder="Để trống = chưa đặt hạn"
                      />
                      <small className="supplier__hint">
                        Để trống = <strong>chưa đặt hạn</strong>, đợt giao không
                        vào cột Quá hạn. Nhập <strong>0</strong> = trả ngay.
                      </small>
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
                        onChange={(e) =>
                          setForm({ ...form, note: e.target.value })
                        }
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
                          Khai báo đơn giá &amp; VAT hiện tại để gợi ý tự động
                          khi lập Phiếu Mua Hàng.
                        </p>
                      </div>
                      <div className="supplier__items-actions">
                        {/* Tải mẫu đứng TRƯỚC Nhập: thứ tự nút là thứ tự việc phải làm. */}
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() =>
                            taiFile(
                              () => api.suppliers.itemsTemplateBlobUrl(token!),
                              "mau-vat-tu-nha-cung-cap.xlsx",
                            )
                          }
                        >
                          Tải mẫu
                        </button>
                        {/* Xuất chỉ có nghĩa với NCC ĐÃ LƯU — NCC đang tạo mới chưa có id. */}
                        {mode === "edit" && selected && (
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() =>
                              taiFile(
                                () =>
                                  api.suppliers.itemsExportBlobUrl(
                                    token!,
                                    selected.id,
                                  ),
                                `vat-tu-${selected.id}.xlsx`,
                              )
                            }
                          >
                            Xuất Excel
                          </button>
                        )}
                        <input
                          ref={fileVatTuRef}
                          type="file"
                          accept=".xlsx"
                          style={{ display: "none" }}
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            // Xoá value ngay: chọn LẠI đúng file vừa chọn vẫn phải bắn onChange.
                            e.target.value = "";
                            if (file) void nhapExcel(file);
                          }}
                        />
                        <button
                          type="button"
                          className="btn btn--ghost"
                          disabled={nhapDang}
                          onClick={() => fileVatTuRef.current?.click()}
                        >
                          {nhapDang ? "Đang đọc..." : "Nhập Excel"}
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() =>
                            setForm((current) => ({
                              ...current,
                              items: [
                                ...(current.items ?? []),
                                emptySupplierItem(),
                              ],
                            }))
                          }
                        >
                          + Thêm mặt hàng
                        </button>
                      </div>
                    </div>

                    {nhapKetQua && (
                      <div className="supplier__import-result">
                        <div className="supplier__import-head">
                          <strong>
                            Đã nạp {nhapKetQua.them} mặt hàng mới
                            {nhapKetQua.capNhat > 0
                              ? `, cập nhật ${nhapKetQua.capNhat} mặt hàng`
                              : ""}
                            .
                          </strong>
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() => setNhapKetQua(null)}
                          >
                            Đóng
                          </button>
                        </div>
                        {/* Nói rõ CHƯA vào sổ: người dùng đóng drawer là mất sạch phần vừa nhập. */}
                        <p className="md-page__muted">
                          Chưa lưu — kiểm lại bảng dưới rồi bấm{" "}
                          <strong>Lưu nhà cung cấp</strong>. Tối đa 500 dòng /
                          file, mỗi file cho một nhà cung cấp.
                        </p>
                        {nhapKetQua.errors.length > 0 && (
                          <ul className="supplier__import-errors">
                            {nhapKetQua.errors.map((e) => (
                              <li key={`${e.row}-${e.message}`}>
                                <strong>Dòng {e.row}:</strong> {e.message}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* Toolbar tìm kiếm vật tư trong drawer */}
                    <div
                      style={{
                        display: "flex",
                        gap: "10px",
                        alignItems: "center",
                      }}
                    >
                      <input
                        className="input"
                        placeholder="Tìm vật tư trong bảng giá..."
                        value={itemSearchQ}
                        onChange={(e) => setItemSearchQ(e.target.value)}
                        style={{ maxWidth: "280px" }}
                      />
                      <span
                        className="md-page__muted"
                        style={{ fontSize: "13px" }}
                      >
                        Hiển thị {filteredFormItems.length} /{" "}
                        {itemsInForm.length} vật tư
                      </span>
                    </div>

                    {/* Table Editor */}
                    <div className="supplier__item-editor">
                      <div
                        className="supplier__item-labels"
                        aria-hidden="true"
                        style={{
                          gridTemplateColumns:
                            "minmax(170px, 1.3fr) minmax(70px, 0.5fr) minmax(105px, 0.75fr) minmax(120px, 0.85fr) minmax(60px, 0.45fr) minmax(110px, 0.75fr) minmax(78px, 0.5fr) minmax(110px, 0.85fr) 36px",
                        }}
                      >
                        <span>Tên vật tư *</span>
                        <span>ĐVT *</span>
                        <span>Đơn giá (chưa VAT) *</span>
                        <span title="Quy giá về đơn vị gốc của mặt hàng để so ngang giữa các NCC (ông báo đ/ram, ông báo đ/kg).">
                          Giá quy về gốc
                        </span>
                        <span>VAT %</span>
                        <span>Giá sau VAT</span>
                        {/* BỎ 10/08/2026 cột "Giao (ngày)" (mg 0176): lúc khai danh mục NCC thì
                            chưa ai biết ông ấy giao mấy ngày — số gõ vào là số đoán, mà kế hoạch
                            lại dựa vào đó để báo trễ. Cần lại thì SUY từ lịch sử mua (ngày đặt →
                            ngày nhận thật), đừng bắt khai tay. */}
                        <span>Ghi chú</span>
                        <span></span>
                      </div>

                      {filteredFormItems.map(({ item, originalIndex }) => {
                        const priceAfterVAT =
                          (item.unit_price || 0) *
                          (1 + (item.vat_percent || 0) / 100);
                        // Cùng công thức server dùng ở `/api/supplier-items/so-gia`: 1 đơn vị NCC
                        // bán bằng `heSoVeGoc` đơn vị gốc ⇒ giá/đơn-vị-gốc = giá ÷ hệ số. Hệ số
                        // lấy TỪ SERVER (không tự suy ở FE) nên hai nơi không thể lệch.
                        const quyDoi = quyDoiDong[originalIndex];
                        const giaVeGoc =
                          quyDoi && item.unit_price > 0
                            ? Math.round(item.unit_price / quyDoi.heSoVeGoc)
                            : null;

                        return (
                          <div
                            className="supplier__item-row"
                            key={originalIndex}
                            style={{
                              gridTemplateColumns:
                                "minmax(170px, 1.3fr) minmax(70px, 0.5fr) minmax(105px, 0.75fr) minmax(120px, 0.85fr) minmax(60px, 0.45fr) minmax(110px, 0.75fr) minmax(78px, 0.5fr) minmax(110px, 0.85fr) 36px",
                            }}
                          >
                            {/* CHỌN từ danh mục gốc, không gõ tự do nữa: ghép NCC với kho bằng
                                chuỗi tên là trượt thầm lặng ("Couche 150" ≠ "Couché 150 79×109"),
                                mà trượt thì mãi không so được giá. Đổi mặt hàng → xoá đơn vị cũ,
                                vì đơn vị dùng được phụ thuộc chính mặt hàng. */}
                            <MaterialCombobox
                              token={token ?? ""}
                              hangTen={item.item_name || null}
                              onPick={(m) =>
                                setSupplierItem(originalIndex, {
                                  hang_loai: m.hang_loai,
                                  hang_id: m.hang_id,
                                  item_name: m.ten,
                                  unit: "",
                                })
                              }
                              placeholder="Gõ tên vật tư…"
                            />
                            {item.hang_loai && item.hang_id ? (
                              <DonViChonTheoHang
                                token={token ?? ""}
                                hangLoai={item.hang_loai}
                                hangId={item.hang_id}
                                value={item.unit}
                                onChange={(ma) =>
                                  setSupplierItem(originalIndex, { unit: ma })
                                }
                                onQuyDoi={(info) => ghiQuyDoiDong(originalIndex, info)}
                              />
                            ) : (
                              // Chưa chọn mặt hàng → KHOÁ ô đơn vị. Trước đây cho gõ tự do; gõ tự
                              // do là mở đường cho đơn vị lạ ("thùg") lọt vào, quy đổi tắt lặng lẽ
                              // và giá không quy về gốc được để so giữa các NCC.
                              <input
                                className="input"
                                placeholder="Chọn vật tư trước"
                                value={item.unit}
                                readOnly
                                disabled
                              />
                            )}
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
                            <div
                              className="supplier-item-vat-calculated"
                              title={
                                giaVeGoc
                                  ? `${money(item.unit_price)} / ${item.unit} ÷ ${quyDoi!.heSoVeGoc} = ${money(giaVeGoc)} / ${quyDoi!.donViGocTen}`
                                  : "Gắn mặt hàng gốc + chọn đơn vị đổi được thì mới quy đổi được."
                              }
                            >
                              {giaVeGoc
                                ? `${money(giaVeGoc)}/${quyDoi!.donViGocTen}`
                                : "—"}
                            </div>
                            <input
                              className="input purchase__number-input"
                              type="number"
                              min="0"
                              max="100"
                              step="0.01"
                              placeholder="10"
                              value={
                                (item.vat_percent ?? 0) >= 0
                                  ? item.vat_percent
                                  : ""
                              }
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  vat_percent: Number(e.target.value || 0),
                                })
                              }
                            />
                            <div className="supplier-item-vat-calculated">
                              {item.unit_price > 0 ? money(priceAfterVAT) : "—"}
                            </div>
                            <input
                              className="input"
                              placeholder="Nếu có"
                              value={item.note ?? ""}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  note: e.target.value,
                                })
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
                    <h3
                      style={{
                        fontSize: "16px",
                        fontWeight: "bold",
                        marginBottom: "4px",
                      }}
                    >
                      Lịch sử Phiếu Mua Hàng (PMH)
                    </h3>
                    <p
                      className="md-page__muted"
                      style={{ marginBottom: "16px" }}
                    >
                      Danh sách các đơn mua hàng đã được giao cho NCC này xử lý.
                    </p>

                    {/* Ba ca đang tải / rỗng / lỗi dùng CHUNG khối `EmptyState` như mọi danh sách
                        khác (chuẩn đợt 2 §f) — trước đây chỗ này tự dựng ba kiểu riêng.
                        Ca "chưa lưu NCC" KHÔNG phải một trong ba ca đó: nó là điều kiện chưa đủ để
                        hỏi máy chủ, nên vẫn là banner hướng dẫn.
                        `poError` là ô nhớ RIÊNG của bảng này (chỉ ghi trong catch của lượt tải
                        lịch sử), không dùng chung với `error` thao tác — giữ nguyên như vậy. */}
                    {mode === "create" || !selected ? (
                      <div className="banner banner--info">
                        Vui lòng lưu thông tin nhà cung cấp trước khi xem lịch
                        sử mua hàng.
                      </div>
                    ) : poLoading ? (
                      <EmptyState trangThai="dang-tai" />
                    ) : poError ? (
                      <EmptyState trangThai="loi" loi={poError} />
                    ) : poList.length === 0 ? (
                      <EmptyState
                        icon="cart"
                        title="Chưa có phiếu mua hàng nào với nhà cung cấp này"
                        sub="Phiếu mua lập từ màn Mua hàng sẽ tự hiện ở đây."
                      />
                    ) : (
                      <div className="card md-page__tablewrap">
                        <table className="md-page__table">
                          <thead>
                            <tr>
                              <th>Mã PMH</th>
                              <th>Ngày tạo</th>
                              <th>Mục đích / Người tạo</th>
                              <th style={{ textAlign: "right" }}>
                                Tổng giá trị
                              </th>
                              <th>Trạng thái PMH</th>
                            </tr>
                          </thead>
                          <tbody>
                            {poList.map((po) => {
                              const statusMeta = getPOStatusLabel(po.status);
                              return (
                                <tr key={po.id}>
                                  <td
                                    className="md-page__mono"
                                    style={{ fontWeight: "bold" }}
                                  >
                                    {po.code}
                                  </td>
                                  <td className="md-page__mono">
                                    {fmtDate(po.created_at)}
                                  </td>
                                  <td>
                                    <div>{po.purpose || "Mua vật tư in"}</div>
                                    <div
                                      className="md-page__muted"
                                      style={{ fontSize: "12px" }}
                                    >
                                      Bởi: {po.created_by_name || "Hệ thống"}
                                    </div>
                                  </td>
                                  <td style={{ textAlign: "right" }}>
                                    <strong className="md-page__price">
                                      {money(po.total_estimate ?? 0)}
                                    </strong>
                                  </td>
                                  <td>
                                    <span
                                      className={`purchase__status ${statusMeta.className}`}
                                    >
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
