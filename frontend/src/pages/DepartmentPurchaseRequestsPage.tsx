import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  ApiError,
  api,
  type DepartmentPurchaseRequestInput,
  type DepartmentPurchaseRequestLineInput,
  type DepartmentPurchaseRequestLineOut,
  type DepartmentPurchaseRequestRow,
  type DepartmentPurchaseWorkflowStatus,
  type DepartmentPurchaseSourceType,
  type PurchaseRequestStatus,
} from "../api/client";
import { useCan } from "../auth/permissions";
import { useDebounced } from "../utils/useDebounced";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DonViChonTheoHang, MaterialCombobox } from "../components/MaterialCombobox";
import { EmptyRow } from "../components/EmptyState";
import { StatusHistoryTimeline } from "../components/StatusHistoryTimeline";
import { RowActionButton } from "../components/RowActionButton";
import { Icon } from "../components/Icons";
import { fmtDate } from "../utils/format";
import "./master-data.css";
// Bảng tình trạng từng dòng mượn `.pay-table` của màn Công nợ — cùng loại bảng phụ trong hộp
// thoại, không dựng bộ lớp thứ hai cho y hệt một việc.
import "./payables.css";
import "./purchase.css";

type StatusFilter = "all" | DepartmentPurchaseWorkflowStatus;

/** Số dòng mỗi trang. TRƯỚC 08/08/2026 màn này tải cứng 100 dòng và KHÔNG có phân trang: quá 100
 *  yêu cầu là bảng cắt im lặng trong khi ô "Tổng" vẫn hiện đúng — người dùng không có cách nào
 *  biết mình đang thiếu gì. */
const PAGE_SIZE = 20;

const SOURCE_TYPE_LABELS: Record<DepartmentPurchaseSourceType, string> = {
  kinh_doanh: "Kinh doanh",
  kho: "Kho",
  san_xuat: "Sản xuất",
  cong_nghe: "Công nghệ",
  gia_cong_ngoai: "Gia công ngoài",
  khac: "Khác",
};

const SOURCE_STATUS_META: Record<
  DepartmentPurchaseWorkflowStatus,
  { label: string; tone: string }
> = {
  open: { label: "Chờ Thu mua xử lý", tone: "draft" },
  drafting: { label: "Thu mua đang lập đơn", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  needs_correction: { label: "Cần Thu mua chỉnh sửa", tone: "rejected" },
  in_purchase: { label: "Đang mua", tone: "pending" },
  done: { label: "Hoàn tất", tone: "received" },
  // Tông HỔ PHÁCH, không phải tông "đã hủy" (đỏ/xám): yêu cầu VẪN CÒN SỐNG, chỉ rụng vài món.
  // Dùng chung tông với "Đã hủy" là người đọc lướt tưởng cả phiếu chết, thôi không xử lý nữa.
  partially_cancelled: { label: "Hủy một phần", tone: "partial" },
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

/** Món CÒN SỐNG trong yêu cầu. Món bị bỏ vẫn được máy chủ trả về (kèm ai bỏ · lúc nào · vì sao)
 *  để còn tra lại, nên mọi chỗ đếm/xem-trước phải lọc, không thì con số phồng lên vô nghĩa. */
function dongSong(
  row: DepartmentPurchaseRequestRow,
): DepartmentPurchaseRequestLineOut[] {
  return row.lines.filter((line) => !line.cancelled_at);
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
  seedHeader = null,
}: {
  eventTick?: number;
  /** Liên thông từ PMH/Phiếu chi: lọc + tô sáng đúng mã YCMH này khi mở trang. */
  focusRequestCode?: string | null;
  /** Liên thông từ Kho: mở form tạo, điền sẵn dòng vật tư (Tên + ĐVT) — bỏ trống SL/ghi chú. */
  seedLines?: DepartmentPurchaseRequestLineInput[] | null;
  seedPurpose?: string | null;
  /** Phần ĐẦU PHIẾU điền sẵn — hiện chỉ Kế hoạch vật tư gửi (20/08/2026).
   *
   *  Bên đó đã biết thừa ngày cần (mốc sớm nhất của các lệnh đã tick) và lệnh nào sinh ra yêu cầu
   *  này; bắt người dùng gõ lại là bắt họ đoán lại một con số máy vừa tính xong. Kho gửi seed
   *  không kèm đầu phiếu thì mọi thứ chạy y như cũ. */
  seedHeader?: {
    source_type?: DepartmentPurchaseSourceType | null;
    needed_date?: string | null;
    related_document_type?: string | null;
    related_document_code?: string | null;
  } | null;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  // Huỷ HỘ người khác = quyền quản trị trên chính màn này; người tạo vẫn tự huỷ đơn của mình.
  const canAdminCancel = can("yeu_cau_mua_hang", "cancel");
  // Sửa / huỷ yêu cầu CỦA CHÍNH MÌNH — máy chủ gác `yeu_cau_mua_hang:update`.
  const canUpdate = can("yeu_cau_mua_hang", "update");
  const [canCreate, setCanCreate] = useState(false);
  const [departmentName, setDepartmentName] = useState<string | null>(null);

  const [rows, setRows] = useState<DepartmentPurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  // Ô nhập vẫn bám `q` (gõ tới đâu hiện tới đó); chỉ lời gọi máy chủ đọc bản đã chậm 300ms.
  const qDebounced = useDebounced(q);
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
  /** Đang hỏi bỏ MỘT MÓN khỏi yêu cầu (mg 0233). Lý do bắt buộc — máy chủ trả 422 nếu trống, nên
   *  khoá luôn nút Xác nhận ở đây để người dùng không phải bấm mới biết. */
  const [boMon, setBoMon] = useState<
    { line: DepartmentPurchaseRequestLineOut; reason: string; error: string | null } | null
  >(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [drawerTab, setDrawerTab] = useState<"items" | "history">("items");
  const minNeededDate = useMemo(() => todayInputValue(), []);

  // Lấy lại từ `rows` (không lưu cả object) để sau khi Hủy cập nhật `rows` thì
  // popup đang mở tự thấy trạng thái mới.
  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  /** Có bày cột "Bỏ món" trong bảng chi tiết không. Cùng luật với nút Huỷ yêu cầu: người tạo VÀ
   *  có ô Thao tác, hoặc có quyền huỷ. Từng dòng còn bị máy chủ chặn tiếp qua `can_cancel`. */
  const boMonDuoc = useMemo(() => {
    if (!selected || selected.status === "cancelled") return false;
    return (
      canAdminCancel || (canUpdate && selected.requested_by_user_id === user?.id)
    );
  }, [selected, canAdminCancel, canUpdate, user?.id]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setListError(null);
    api.departmentPurchaseRequests
      .list(token, {
        q: qDebounced.trim() || undefined,
        status: status === "all" ? null : status,
        sort: "-created_at",
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setListError("Không tải được danh sách yêu cầu mua hàng.");
      })
      .finally(() => setLoading(false));
  }, [token, qDebounced, status, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0 || !token) return;
    load();
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

  // Liên thông: đổ mã YCMH cần truy vết vào ô tìm kiếm → load() tự chạy lại
  // (q đổi làm useCallback tạo lại), danh sách chỉ còn đúng phiếu đó.
  useEffect(() => {
    if (!focusRequestCode) return;
    setQ(focusRequestCode);
    setStatus("all");
    setPage(1);
  }, [focusRequestCode]);

  // Liên thông từ Kho / Kế hoạch vật tư: mở form tạo với dòng vật tư điền sẵn. `seedLines` là
  // object MỚI mỗi lần điều hướng nên effect chạy đúng 1 lần / lượt bấm "Tạo yêu cầu mua".
  //
  // KHÔNG tự lưu hộ. Form mở ra đã đủ chữ đủ số, nhưng cái bấm Lưu vẫn là người — số máy tính ra
  // (nhất là số lượng thiếu và ngày cần) là ĐỀ XUẤT, người lo vật tư còn phải làm tròn theo ram /
  // kiện, cộng phòng hao, hoặc bỏ bớt một món đã hỏi mượn được ở xưởng khác.
  useEffect(() => {
    if (!seedLines || seedLines.length === 0) return;
    setEditing(null);
    setForm({
      ...emptyRequest(seedHeader?.source_type ?? "kho"),
      related_document_type: seedHeader?.related_document_type ?? null,
      related_document_code: seedHeader?.related_document_code ?? null,
      needed_date: seedHeader?.needed_date ?? "",
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
      // Món ĐÃ BỎ không vào form sửa: nó là vết đã đóng, sửa lại là mở một cuộc huỷ đã kết thúc.
      // Máy chủ giữ nguyên các dòng đó khi nhận PUT (xem `purchase_repo.update`), nên không gửi
      // lên không có nghĩa là xoá.
      lines: row.lines
        .filter((line) => !line.cancelled_at)
        .map((line) => ({
          hang_loai: line.hang_loai,
          hang_id: line.hang_id,
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


  function cleanRequest(
    input: DepartmentPurchaseRequestInput,
  ): DepartmentPurchaseRequestInput {
    const trimOptional = (v?: string | null) => {
      const s = (v ?? "").trim();
      return s || null;
    };
    return {
      source_type: input.source_type ?? null,
      // GIỮ vết chứng từ nguồn thay vì xoá trắng (20/08/2026). Trước đây hai ô này luôn bị nullhoá
      // vì form gõ tay không có chỗ nhập chúng — nhưng nó cũng xoá luôn vết của phiếu ĐI TỪ màn
      // khác sang (Kế hoạch vật tư gửi mã lệnh), và xoá cả lúc SỬA một phiếu vốn đã có vết. Người
      // mua mở phiếu ra không còn biết mua cho lệnh nào; `openEdit` nạp vào rồi lưu là mất.
      related_document_type: trimOptional(input.related_document_type),
      related_document_code: trimOptional(input.related_document_code),
      content: (input.content ?? "").trim(),
      needed_date: (input.needed_date ?? "").trim(),
      note: null,
      lines: input.lines.map((line) => ({
        // Cặp mặt hàng gốc đi kèm: phiếu mua sinh sau đó nối thẳng về đúng món, không ghép bằng tên.
        hang_loai: line.hang_loai ?? null,
        hang_id: line.hang_id ?? null,
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
    if (
      !payload.lines.length ||
      payload.lines.some((line) => !line.item_name || !line.unit)
    ) {
      setFormError(
        "Yêu cầu cần ít nhất một dòng vật tư; tên vật tư và đơn vị tính không được trống.",
      );
      return;
    }
    // Phải là mặt hàng CÓ THẬT trong danh mục Giấy / Vật tư khác. Dòng cũ (lập trước khi ô chọn
    // này ra đời) mở ra sửa cũng phải chọn lại — tên chuỗi không nối được về đâu cả.
    if (payload.lines.some((line) => !line.hang_loai || !line.hang_id)) {
      setFormError(
        "Mỗi dòng phải chọn vật tư từ danh mục (Giấy / Vật tư khác) — gõ tên để tìm.",
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

  async function confirmBoMon() {
    if (!token || !boMon || !selected) return;
    const ly_do = boMon.reason.trim();
    if (!ly_do) {
      setBoMon({ ...boMon, error: "Nhập lý do bỏ món này khỏi yêu cầu." });
      return;
    }
    setActionBusy(`line-cancel:${boMon.line.id}`);
    try {
      const saved = await api.departmentPurchaseRequests.cancelLine(
        token,
        selected.id,
        boMon.line.id,
        ly_do,
      );
      // Máy chủ trả về CẢ yêu cầu sau khi tính lại (trạng thái phiếu có thể đổi theo, vd món cuối
      // bị bỏ ⇒ phiếu thành Đã hủy) — thay nguyên dòng, đừng vá tay từng ô.
      setRows((current) => current.map((row) => (row.id === saved.id ? saved : row)));
      setBoMon(null);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Không bỏ được món này khỏi yêu cầu.";
      setBoMon((current) => (current ? { ...current, error: message } : current));
    } finally {
      setActionBusy(null);
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
      <div className="purchase__topbar-unified">
        <div className="purchase__topbar-left">
          <h1 className="purchase__topbar-title">Yêu cầu mua hàng</h1>
          <span className="purchase__count-badge">{loading ? "..." : total}</span>
        </div>
        <div className="purchase__topbar-controls">
          <form
            className="purchase__search-wrap"
            onSubmit={(e) => {
              e.preventDefault();
              load();
            }}
          >
            <span className="purchase__search-icon">
              <Icon name="search" size={16} />
            </span>
            <input
              className="input purchase__search-input"
              placeholder="Tìm mã yêu cầu, mục đích, vật tư..."
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </form>
          <select
            className="input purchase__select-modern"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as StatusFilter);
              setPage(1);
            }}
          >
            <option value="all">Tất cả trạng thái</option>
            {Object.entries(SOURCE_STATUS_META).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </div>
        <div className="purchase__topbar-actions">
          {canCreate && (
            <Button variant="accent" onClick={openCreate}>
              + Tạo yêu cầu mua
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <section className="card md-page__tablewrap">
        <table className="md-page__table purchase__table-modern">
          <thead>
            <tr>
              <th style={{ width: "160px" }}>Mã yêu cầu</th>
              <th style={{ width: "210px" }}>Bộ phận / Người tạo</th>
              <th style={{ width: "110px" }}>Vật tư</th>
              <th style={{ width: "130px" }}>Ngày cần hàng</th>
              <th style={{ width: "180px" }}>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "140px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "70px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "130px" }} /></td>
                </tr>
              ))
            ) : listError ? (
              <EmptyRow
                colSpan={5}
                trangThai="loi"
                loi={listError}
                onThuLai={load}
              />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon="clipboard"
                title="Chưa có yêu cầu mua hàng nào khớp"
                sub={
                  q.trim() || status !== "all"
                    ? "Thử bỏ bớt bộ lọc hoặc xoá từ khoá tìm kiếm."
                    : "Bộ phận gửi yêu cầu vật tư sang Thu mua tại đây."
                }
                action={
                  q.trim() || status !== "all" ? (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => {
                        setQ("");
                        setStatus("all");
                        setPage(1);
                      }}
                    >
                      Xoá bộ lọc
                    </button>
                  ) : undefined
                }
              />
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
                    <div className="purchase__code-row">
                      <strong className="purchase__code-badge">{row.code}</strong>
                      {row.related_document_code && (
                        <span
                          className="purchase__source-tag"
                          title={`Chứng từ liên quan: ${row.related_document_type || "Nguồn"} ${row.related_document_code}`}
                        >
                          {row.related_document_code}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="purchase__dept-title">{row.requesting_department_name || "Nội bộ"}</div>
                    <div className="md-page__muted">
                      {row.requested_by_name || SOURCE_TYPE_LABELS[row.source_type]}
                    </div>
                  </td>
                  <td title={row.lines.map((line) => line.item_name).join(", ")}>
                    <span className="purchase__item-chip">{dongSong(row).length} món</span>
                  </td>
                  <td>{fmtDate(row.needed_date)}</td>
                  <td>
                    <div className="purchase__status-col">
                      <SourceStatusBadge status={row.workflow_status} />
                      {row.workflow_status === "partially_cancelled" && (
                        <div className="md-page__muted">
                          {SOURCE_STATUS_META[row.progress_status]?.label ?? row.progress_status} · bỏ {row.cancelled_line_count}/{row.cancelled_line_count + row.active_line_count} món
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {!loading && totalPages > 1 && (
          <div className="purchase__source-foot">
            <span className="md-page__muted">
              Tổng {total} yêu cầu · Trang {page}/{totalPages}
            </span>
            <div className="md-page__pager-btns">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Sau
              </button>
            </div>
          </div>
        )}
      </section>

      {selected && (
        <div className="rc-drawer__scrim" onClick={() => setSelectedId(null)}>
          <aside className="rc-drawer purchase__drawer-780" onClick={(e) => e.stopPropagation()}>
            <div className="purchase__hero-banner">
              <div className="purchase__hero-top">
                <div>
                  <span className="purchase__hero-kicker">Chi tiết yêu cầu mua hàng</span>
                  <div className="purchase__hero-title-row">
                    <h2 className="purchase__hero-code">{selected.code}</h2>
                    <SourceStatusBadge status={selected.workflow_status} />
                  </div>
                </div>
                <button
                  type="button"
                  className="purchase__hero-x"
                  onClick={() => setSelectedId(null)}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>

              <div className="purchase__hero-meta">
                <span>{selected.requesting_department_name || "Nội bộ"}</span>
                {selected.requested_by_name && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>{selected.requested_by_name}</span>
                  </>
                )}
                <span className="purchase__hero-dot">•</span>
                <span className="purchase__hero-date">Cần {fmtDate(selected.needed_date)}</span>
                <span className="purchase__hero-dot">•</span>
                <span>
                  {dongSong(selected).length} mặt hàng
                  {selected.cancelled_line_count > 0 ? ` (đã bỏ ${selected.cancelled_line_count})` : ""}
                </span>
                {selected.related_document_code && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span className="purchase__hero-chip" style={{ margin: 0 }}>
                      {selected.related_document_code}
                    </span>
                  </>
                )}
              </div>
            </div>

            <div className="rc-drawer__tabs" style={{ margin: "16px 24px 0 24px" }}>
              <button
                type="button"
                className={`rc-drawer__tab ${drawerTab === "items" ? "is-active" : ""}`}
                onClick={() => setDrawerTab("items")}
              >
                Nội dung & Vật tư ({dongSong(selected).length})
              </button>
              <button
                type="button"
                className={`rc-drawer__tab ${drawerTab === "history" ? "is-active" : ""}`}
                onClick={() => setDrawerTab("history")}
              >
                Lịch sử trạng thái ({selected.status_history?.length || 0})
              </button>
            </div>

            <div className="rc-drawer__body purchase__drawer-body-wow">
              {drawerTab === "items" ? (
                <>
                  {noiDung(selected) && (
                    <div className="purchase__note" style={{ fontSize: "13px" }}>
                      {noiDung(selected)}
                    </div>
                  )}

                  {selected.reject_reason && (
                    <div className="purchase__note purchase__note--reject">
                      <strong>Lý do từ chối / huỷ:</strong> {selected.reject_reason}
                    </div>
                  )}

                  <div className="purchase__items-section">
                    <table className="pay-table purchase__drawer-table">
                      <thead>
                        <tr>
                          <th>Vật tư</th>
                          <th className="pay-num">Yêu cầu</th>
                          <th>Nhà cung cấp & PMH</th>
                          <th>Trạng thái</th>
                          {boMonDuoc && selected.lines.some((l) => !l.cancelled_at && l.can_cancel) && (
                            <th className="md-page__actions-col">Thao tác</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {selected.lines.map((line) => (
                          <tr
                            key={line.id}
                            className={line.cancelled_at ? "purchase__dong-da-bo" : undefined}
                          >
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                <span style={{ color: "var(--ash)" }}>
                                  <Icon name="box" size={14} />
                                </span>
                                <strong style={{ fontFamily: "var(--ff-sans)" }}>{line.item_name}</strong>
                              </div>
                              {line.note && (
                                <div style={{ fontSize: "11px", color: "var(--ash)", marginTop: "2px" }}>
                                  {line.note}
                                </div>
                              )}
                              {line.cancelled_at && (
                                <div className="md-page__muted" style={{ fontSize: "11px" }}>
                                  Đã bỏ{line.cancelled_by_name ? ` bởi ${line.cancelled_by_name}` : ""} · {fmtDate(line.cancelled_at)}
                                  {line.cancel_reason ? ` — ${line.cancel_reason}` : ""}
                                </div>
                              )}
                            </td>
                            <td className="pay-num">
                              <span className="purchase__qty-badge">
                                {line.quantity.toLocaleString("vi-VN")} {line.unit}
                              </span>
                            </td>
                            <td>
                              {line.fulfilment?.supplier_name ? (
                                <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                                  <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--ink)" }}>
                                    {line.fulfilment.supplier_name}
                                  </span>
                                  {line.fulfilment?.purchase_code && (
                                    <span className="purchase__spec-tag purchase__spec-tag--pmh" style={{ fontSize: "10px", width: "fit-content" }}>
                                      {line.fulfilment.purchase_code}
                                      {line.fulfilment.received_quantity ? ` · nhận ${line.fulfilment.received_quantity.toLocaleString("vi-VN")} ${line.unit}` : ""}
                                    </span>
                                  )}
                                </div>
                              ) : line.fulfilment?.purchase_code ? (
                                <span className="purchase__spec-tag purchase__spec-tag--pmh" style={{ fontSize: "10px" }}>
                                  {line.fulfilment.purchase_code}
                                </span>
                              ) : (
                                <span className="md-page__muted" style={{ fontSize: "12px" }}>—</span>
                              )}
                            </td>
                            <td>
                              {line.cancelled_at ? (
                                <span className="purchase__status purchase__status--cancelled">
                                  Đã bỏ
                                </span>
                              ) : (
                                <LineFulfilmentCell
                                  line={line}
                                  coPhieu={selected.purchase_requests.length > 0}
                                />
                              )}
                            </td>
                            {boMonDuoc && selected.lines.some((l) => !l.cancelled_at && l.can_cancel) && (
                              <td className="md-page__actions-col">
                                {!line.cancelled_at && line.can_cancel && (
                                  <div className="purchase__actions purchase__actions--dense">
                                    <RowActionButton
                                      dense
                                      danger
                                      icon="ban"
                                      label={line.cancel_block_reason ?? "Bỏ món"}
                                      onClick={() => setBoMon({ line, reason: "", error: null })}
                                    />
                                  </div>
                                )}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="purchase__timeline-section">
                  <StatusHistoryTimeline items={selected.status_history} />
                </div>
              )}
            </div>

            {selected.status === "open" &&
              (canAdminCancel || (canUpdate && selected.requested_by_user_id === user?.id)) && (
                <div className="rc-drawer__footer purchase__drawer-footer">
                  {canUpdate && selected.requested_by_user_id === user?.id && (
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() => openEdit(selected)}
                    >
                      <Icon name="edit" size={14} /> Sửa yêu cầu
                    </button>
                  )}
                  {(canAdminCancel ||
                    (canUpdate && selected.requested_by_user_id === user?.id)) && (
                    <button
                      type="button"
                      className="btn btn--danger"
                      onClick={() => setCanceling(selected)}
                    >
                      <Icon name="ban" size={14} /> Hủy yêu cầu
                    </button>
                  )}
                </div>
              )}
          </aside>
        </div>
      )}

      {mode && (
        <div className="md-page__overlay" role="presentation">
          <div
            className="card md-page__dialog purchase__dialog purchase__dialog--request"
            role="dialog"
            aria-modal="true"
            style={{ overflow: "hidden", padding: 0 }}
          >
            <div className="purchase__hero-banner">
              <div className="purchase__hero-top">
                <div>
                  <span className="purchase__hero-kicker">Form nhập liệu vật tư</span>
                  <div className="purchase__hero-title-row">
                    <h2 className="purchase__hero-code" style={{ fontSize: "18px" }}>
                      {editing ? "Sửa yêu cầu mua hàng" : "Tạo yêu cầu mua hàng"}
                    </h2>
                  </div>
                </div>
                <button
                  type="button"
                  className="purchase__hero-x"
                  onClick={closeForm}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>

              <div className="purchase__hero-meta">
                <span>{departmentName || "Nội bộ"}</span>
                {editing && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>{editing.code}</span>
                  </>
                )}
              </div>
            </div>

            <form className="md-page__dialog-body" onSubmit={save} style={{ padding: "20px 24px" }}>
              {formError && (
                <div className="banner banner--error" role="alert" style={{ marginBottom: "16px" }}>
                  {formError}
                </div>
              )}

              <div className="purchase__modal-top-fields">
                <div className="md-page__field" style={{ width: "220px" }}>
                  <label htmlFor="needed_date_input">
                    Ngày cần hàng <span className="md-page__req">*</span>
                  </label>
                  <input
                    id="needed_date_input"
                    className="input purchase__input-flat"
                    type="date"
                    required
                    min={minNeededDate}
                    value={form.needed_date}
                    onChange={(e) =>
                      setForm({ ...form, needed_date: e.target.value })
                    }
                  />
                </div>

                <div className="md-page__field" style={{ width: "100%" }}>
                  <label htmlFor="content_input">
                    Nội dung / mục đích <span className="md-page__req">*</span>
                  </label>
                  <textarea
                    id="content_input"
                    className="input purchase__textarea-flat"
                    required
                    rows={2}
                    value={form.content}
                    onChange={(e) =>
                      setForm({ ...form, content: e.target.value })
                    }
                    placeholder="VD: thiếu giấy cho lệnh sản xuất SX-2026-014, cần trước ngày đóng gói"
                  />
                </div>
              </div>

              <div className="purchase__modal-items-head">
                <h4 className="purchase__section-heading" style={{ margin: 0 }}>
                  Danh sách vật tư cần mua ({form.lines.length})
                </h4>
              </div>

              <div className="purchase__modal-table-wrap">
                <table className="pay-table purchase__modal-table">
                  <thead>
                    <tr>
                      <th style={{ width: "36%" }}>Vật tư *</th>
                      <th style={{ width: "16%" }}>ĐVT</th>
                      <th style={{ width: "18%" }} className="pay-num">Số lượng *</th>
                      <th>Ghi chú dòng</th>
                      <th style={{ width: "40px", textAlign: "center" }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.lines.map((line, index) => (
                      <tr key={index}>
                        <td>
                          <MaterialCombobox
                            token={token ?? ""}
                            hangTen={line.item_name || null}
                            chiCoNhaCungCap
                            onPick={(m) =>
                              setLine(index, {
                                hang_loai: m.hang_loai,
                                hang_id: m.hang_id,
                                item_name: m.ten,
                                unit: "",
                              })
                            }
                          />
                        </td>
                        <td>
                          <DonViChonTheoHang
                            chiDoc
                            token={token ?? ""}
                            hangLoai={line.hang_loai ?? null}
                            hangId={line.hang_id ?? null}
                            value={line.unit}
                            onChange={(ma) => setLine(index, { unit: ma })}
                            disabled={!line.hang_loai || !line.hang_id}
                          />
                        </td>
                        <td className="pay-num">
                          <input
                            className="input purchase__input-flat pay-num"
                            type="number"
                            min="0.01"
                            step="0.01"
                            required
                            placeholder="1000"
                            value={line.quantity > 0 ? line.quantity : ""}
                            onChange={(e) =>
                              setLine(index, {
                                quantity: Number(e.target.value || 0),
                              })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="input purchase__input-flat"
                            placeholder="Nếu có"
                            value={line.note ?? ""}
                            onChange={(e) => setLine(index, { note: e.target.value })}
                          />
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <button
                            type="button"
                            className="purchase__icon-trash-btn"
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
                            <Icon name="trash" size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                    <tr className="purchase__add-line-tr">
                      <td colSpan={5} style={{ padding: 0 }}>
                        <button
                          type="button"
                          className="purchase__add-line-btn"
                          onClick={() =>
                            setForm((current) => ({
                              ...current,
                              lines: [...current.lines, emptyLine()],
                            }))
                          }
                        >
                          <Icon name="plus" size={14} /> Thêm dòng vật tư mới...
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="md-page__dialog-actions" style={{ marginTop: "20px" }}>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={closeForm}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  {editing ? (
                    <>
                      <Icon name="edit" size={14} /> Cập nhật yêu cầu
                    </>
                  ) : (
                    <>
                      <Icon name="plus" size={14} /> Lưu yêu cầu
                    </>
                  )}
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

      {/* Cùng khuôn với hộp "Hủy yêu cầu" ngay trên: hộp XÁC NHẬN, không phải modal biểu mẫu —
          đây là một câu hỏi có/không kèm ô lý do. `confirmDisabled` khoá nút cho tới khi có lý do
          (máy chủ trả 422 nếu trống, đừng bắt người dùng bấm mới biết). */}
      <ConfirmDialog
        open={Boolean(boMon)}
        title="Bỏ món này khỏi yêu cầu?"
        message={
          boMon && selected
            ? // Bỏ món CUỐI CÙNG là huỷ luôn cả yêu cầu — đây là chỗ duy nhất người dùng thấy
              // được điều đó trước khi bấm.
              dongSong(selected).length <= 1
              ? `"${boMon.line.item_name}" là món cuối còn lại — bỏ nó là cả yêu cầu ${selected.code} chuyển sang Đã hủy.`
              : `"${boMon.line.item_name}" sẽ không còn được mua nữa. Các món khác trong yêu cầu vẫn chạy tiếp.`
            : undefined
        }
        danger
        confirmLabel="Bỏ món"
        busy={boMon ? actionBusy === `line-cancel:${boMon.line.id}` : false}
        error={boMon?.error ?? null}
        confirmDisabled={!boMon?.reason.trim()}
        onConfirm={confirmBoMon}
        onCancel={() => setBoMon(null)}
      >
        <label className="purchase__field">
          <span>Lý do bỏ (bắt buộc)</span>
          <textarea
            className="input purchase__textarea"
            value={boMon?.reason ?? ""}
            onChange={(e) =>
              setBoMon((current) =>
                current ? { ...current, reason: e.target.value, error: null } : current,
              )
            }
          />
        </label>
      </ConfirmDialog>
    </main>
  );
}

function SourceStatusBadge({
  status,
}: {
  status: DepartmentPurchaseWorkflowStatus;
}) {
  const meta = SOURCE_STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>
      <span className={`purchase__status-dot purchase__status-dot--${meta.tone}`} />
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
  // "Giao một phần" mà không nói giao BAO NHIÊU thì bộ phận không biết còn thiếu mấy để tính
  // đường xoay — đó là cả lý do của việc này. Hiện số ở cả hai bậc: đang giao dở và đã nhận đủ.
  const dangGiaoDo = f.purchase_status === "partially_received";
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
        {(f.purchase_status === "received" || dangGiaoDo) && (
          <>
            {" "}
            · nhận {nhan.toLocaleString("vi-VN")}
            {dangGiaoDo ? `/${f.ordered_quantity.toLocaleString("vi-VN")}` : ""}{" "}
            {f.ordered_unit}
          </>
        )}
      </small>
      {thieu && <small className="pay-short">Giao thiếu so với số đặt</small>}
      {dangGiaoDo && nhan < f.ordered_quantity && (
        <small className="pay-short">
          Còn {(f.ordered_quantity - nhan).toLocaleString("vi-VN")} {f.ordered_unit} chưa về
        </small>
      )}
      {f.purchase_status === "rejected" && (
        <small className="pay-short">Cần lập phiếu lại cho dòng này</small>
      )}
    </>
  );
}
