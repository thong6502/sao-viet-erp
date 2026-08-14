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
import { DetailModal } from "../components/DetailModal";
import { EmptyRow } from "../components/EmptyState";
import { StatusHistoryTimeline } from "../components/StatusHistoryTimeline";
import { RowActionButton } from "../components/RowActionButton";
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const minNeededDate = useMemo(() => todayInputValue(), []);

  // Lấy lại từ `rows` (không lưu cả object) để sau khi Hủy cập nhật `rows` thì
  // popup đang mở tự thấy trạng thái mới.
  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );

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
      related_document_type: null,
      related_document_code: null,
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
        {/* Eyebrow = tên SECTION trên sidebar, chép NGUYÊN VĂN, MỘT cấp. Màn này nằm trong section
            "Thu mua" (Sidebar.tsx: Thu mua → Yêu cầu mua hàng · Mua hàng · Nhà cung cấp), nên
            eyebrow là "Thu mua". Trước 09/08/2026 ghi "Phòng ban" — đó là tên NGƯỜI DÙNG màn, KHÔNG
            phải chỗ màn nằm; ai đọc xong đi tìm mục "Phòng ban" trên sidebar sẽ lạc sang Nhân sự.
            ⚠️ Phải là className="eyebrow": lớp `ns__eyebrow` KHÔNG có CSS ở bất kỳ file nào, dùng
            nó là ra chữ thường 15px. */}
        <p className="eyebrow">Thu mua</p>
        <h1 className="md-page__title">Yêu cầu mua hàng</h1>
        {/* Phụ đề nói rõ VAI của người đang đọc, vì màn mở cho 6 nhóm quyền (Sidebar.tsx: thu_mua ·
            bao_gia · kho · san_xuat · dm_giay_vat_tu · ke_toan). Câu cũ tả cả hai đầu ("các phòng
            ban… Thu mua dùng danh sách này…") nên người mở màn không biết mình là bên nào. */}
        <p className="md-page__sub">
          Phòng ban của bạn gửi yêu cầu vật tư sang Thu mua.
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
        <div className="md-page__toolbar-spacer" />
        {canCreate && (
          // ⚠️ TÊN LỚP ĐẶT NGƯỢC VỚI TÀI LIỆU: `variant="accent"` mới ra màu CAM thương hiệu,
          // `variant="primary"` ra màu NAVY. Ai đọc docs/UI_DESIGN.md rồi gõ "primary" sẽ được
          // một nút navy — đúng lỗi của nút này trước 09/08/2026.
          // Đây là hành động chính DUY NHẤT của màn; luật là TỐI ĐA MỘT nút cam mỗi màn, nên
          // đừng nâng thêm nút nào khác (Xoá bộ lọc, Trước/Sau, nút trên dòng) lên accent.
          <Button variant="accent" onClick={openCreate}>
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
              {/* `md-page__actions-col` canh tiêu đề THEO NÚT (cụm nút dense nằm sát phải). Thiếu
                  lớp này thì chữ "Thao tác" đứng một nơi, cụm nút đứng một nẻo. */}
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <EmptyRow colSpan={7} trangThai="dang-tai" />
            ) : listError ? (
              <EmptyRow
                colSpan={7}
                trangThai="loi"
                loi={listError}
                onThuLai={load}
              />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={7}
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
                    <SourceStatusBadge status={row.workflow_status} />
                  </td>
                  <td
                    className="md-page__actions-col"
                    onClick={(event) => event.stopPropagation()}
                  >
                    {/* Cột Thao tác dùng TOÀN icon dense (`RowActionButton`), không trộn icon với
                        nút chữ: mỗi nút chữ chiếm ~64px nên ba nút là đẩy cột tiền/trạng thái ra
                        khỏi tầm mắt ở 1440px, mà mắt cũng phải đọc hai kiểu ký hiệu trong cùng một
                        ô. Tooltip của `RowActionButton` giữ nguyên phần chữ.
                        GIỮ `danger` ở nút Hủy — mất tín hiệu đỏ là bấm nhầm sang huỷ yêu cầu. */}
                    <div className="purchase__actions purchase__actions--dense">
                      <RowActionButton
                        dense
                        label="Xem chi tiết"
                        icon="eye"
                        onClick={() => setSelectedId(row.id)}
                      />
                      {/* Sửa/Huỷ đòi ĐỦ HAI thứ: là người tạo VÀ có ô Thao tác. Trước 11/08/2026
                          chỉ xét "có phải người tạo không", nên gỡ ô Thao tác rồi hai nút vẫn bày
                          ra — bấm mới ăn 403. Máy chủ vốn chặn đúng; đây là phần giao diện. */}
                      {row.status === "open" &&
                        canUpdate &&
                        row.requested_by_user_id === user?.id && (
                          <RowActionButton
                            dense
                            label="Sửa yêu cầu"
                            icon="pencil"
                            onClick={() => openEdit(row)}
                          />
                        )}
                      {row.status === "open" &&
                        (canAdminCancel ||
                          (canUpdate && row.requested_by_user_id === user?.id)) && (
                          <RowActionButton
                            dense
                            danger
                            label="Hủy yêu cầu"
                            icon="ban"
                            onClick={() => setCanceling(row)}
                          />
                        )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {/* Chân bảng chuẩn: tổng bên trái, điều hướng trang bên phải. Chỉ hiện nút khi thật sự
            có nhiều hơn một trang — bảng 3 dòng mà treo "Trang 1/1" là nhiễu. */}
        <div className="purchase__source-foot">
          <span className="md-page__muted">
            Tổng {total} yêu cầu
            {totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ""}
          </span>
          {totalPages > 1 && (
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
          )}
        </div>
      </section>

      {selected && (
        <DetailModal
          kicker="Chi tiết yêu cầu"
          title={selected.code}
          subtitle={noiDung(selected)}
          badge={<SourceStatusBadge status={selected.workflow_status} />}
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
          {(() => {
            const veDu = selected.lines.filter((l) => {
              const f = l.fulfilment;
              if (!f) return false;
              // Phiếu chưa có tin về số nhận (`null`) mà đã ở bậc "đã nhận" ⇒ luật cũ: coi như đủ.
              const nhan = f.received_quantity ?? f.ordered_quantity;
              return f.purchase_status === "received" && nhan >= f.ordered_quantity;
            }).length;
            if (veDu === 0) return null;
            return (
              <p className="md-page__muted purchase__tien-do">
                {veDu}/{selected.lines.length} mặt hàng đã về đủ
              </p>
            );
          })()}
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
                      {/* Chọn từ DANH MỤC GỐC (Giấy + Vật tư khác) — cùng ô với đề nghị kho và
                          bảng giá NCC. Trước đây đổ từ bảng giá NCC nên món chưa ai báo giá thì
                          không đề nghị mua được, mà tên lưu dạng chuỗi cũng không nối về đâu. */}
                      <div className="purchase__line-name">
                        <MaterialCombobox
                          token={token ?? ""}
                          hangTen={line.item_name || null}
                          onPick={(m) =>
                            setLine(index, {
                              hang_loai: m.hang_loai,
                              hang_id: m.hang_id,
                              item_name: m.ten,
                              unit: "",
                            })
                          }
                        />
                      </div>
                      {/* ĐVT theo CHÍNH mặt hàng vừa chọn (đơn vị gốc + những đơn vị đổi được
                          với nó). Chưa chọn hàng thì khoá — gõ tự do là mở đường cho đơn vị lạ
                          lọt vào, quy đổi tắt lặng lẽ và tồn kho lệch. */}
                      <DonViChonTheoHang
                        token={token ?? ""}
                        hangLoai={line.hang_loai ?? null}
                        hangId={line.hang_id ?? null}
                        value={line.unit}
                        onChange={(ma) => setLine(index, { unit: ma })}
                        disabled={!line.hang_loai || !line.hang_id}
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
  status: DepartmentPurchaseWorkflowStatus;
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
