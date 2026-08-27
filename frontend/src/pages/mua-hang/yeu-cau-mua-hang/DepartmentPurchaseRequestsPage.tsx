// Màn YÊU CẦU MUA HÀNG (bộ phận lập) — shell (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
// Giữ ở đây: state + `load()` + effects liên thông (focus mã · seed từ Kho/Kế hoạch vật tư) +
// handlers (`openCreate` · `openEdit` · `closeForm` · `setLine` · `save` · `confirmBoMon` ·
// `confirmCancel`) + chỗ mount.
// ⚠️ `SOURCE_STATUS_META` của màn này là BẢN RIÊNG, TRÙNG TÊN nhưng khác nội dung với bản ở
// `mua-hang/phieu-mua-hang/` — đừng gộp, đừng import chéo.
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
  type DepartmentPurchaseRequestRow,
} from "../../../api/client";
import { useCan } from "../../../auth/permissions";
import { useDebounced } from "../../../utils/useDebounced";
import { useAuth } from "../../../auth/useAuth";
import { RequestDetailDrawer } from "./components/RequestDetailDrawer";
import { RequestFormDrawer } from "./components/RequestFormDrawer";
import { RequestModals } from "./components/RequestModals";
import { RequestsTable } from "./components/RequestsTable";
import { RequestsToolbar } from "./components/RequestsToolbar";
import { useNapTenDonVi } from "../../tenDonVi";
import { PAGE_SIZE } from "./shared/constants";
import { cleanRequest, emptyRequest, noiDungCu, todayInputValue } from "./shared/helpers";
import type {
  BoMonState,
  DepartmentPurchaseRequestsPageProps,
  StatusFilter,
} from "./shared/types";
import "../../master-data.css";
// Bảng tình trạng từng dòng mượn `.pay-table` của màn Công nợ — cùng loại bảng phụ trong hộp
// thoại, không dựng bộ lớp thứ hai cho y hệt một việc.
import "../../payables.css";
import "../../purchase.css";

export function DepartmentPurchaseRequestsPage({
  eventTick = 0,
  focusRequestCode = null,
  seedLines = null,
  seedPurpose = null,
  seedHeader = null,
}: DepartmentPurchaseRequestsPageProps) {
  const { token, user } = useAuth();
  const can = useCan();
  // Nạp danh mục Đơn vị MỘT lần — bảng dòng hàng trong drawer chi tiết hiện TÊN, không hiện mã.
  useNapTenDonVi();
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
  const [boMon, setBoMon] = useState<BoMonState | null>(null);
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
      <RequestsToolbar
        loading={loading}
        total={total}
        q={q}
        setQ={setQ}
        status={status}
        setStatus={setStatus}
        setPage={setPage}
        load={load}
        canCreate={canCreate}
        openCreate={openCreate}
      />

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <RequestsTable
        loading={loading}
        listError={listError}
        load={load}
        rows={rows}
        q={q}
        setQ={setQ}
        status={status}
        setStatus={setStatus}
        page={page}
        setPage={setPage}
        total={total}
        totalPages={totalPages}
        focusRequestCode={focusRequestCode}
        selectedId={selectedId}
        setSelectedId={setSelectedId}
      />

      {selected && (
        <RequestDetailDrawer
          selected={selected}
          setSelectedId={setSelectedId}
          drawerTab={drawerTab}
          setDrawerTab={setDrawerTab}
          boMonDuoc={boMonDuoc}
          setBoMon={setBoMon}
          canAdminCancel={canAdminCancel}
          canUpdate={canUpdate}
          openEdit={openEdit}
          setCanceling={setCanceling}
        />
      )}

      {mode && (
        <RequestFormDrawer
          editing={editing}
          departmentName={departmentName}
          form={form}
          setForm={setForm}
          setLine={setLine}
          formError={formError}
          minNeededDate={minNeededDate}
          saving={saving}
          save={save}
          closeForm={closeForm}
        />
      )}

      <RequestModals
        selected={selected}
        canceling={canceling}
        setCanceling={setCanceling}
        confirmCancel={confirmCancel}
        boMon={boMon}
        setBoMon={setBoMon}
        confirmBoMon={confirmBoMon}
        actionBusy={actionBusy}
      />
    </main>
  );
}
