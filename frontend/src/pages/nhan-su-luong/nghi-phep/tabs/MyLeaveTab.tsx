// Tab "Đơn của tôi" (tách từ pages/NghiPhepPage.tsx).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  type LeaveQuota,
  type LeaveRequest,
  type LeaveType,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { Pager, trangHopLe } from "../../../../components/Pager";
import { Info, Plus } from "lucide-react";
import { LeaveTable } from "../components/LeaveTable";
import { LeaveRequestDetailModal } from "../modals/LeaveRequestDetailModal";
import { LeaveRequestFormModal } from "../modals/LeaveRequestFormModal";
import { PAGE_SIZE } from "../shared/constants";
import { errMsg } from "../shared/helpers";

// --- Tab: Đơn của tôi -------------------------------------------------------

export function MyLeaveTab({ token, onChanged, coQuyenGhi }: {
  token: string;
  onChanged?: () => void;
  /** Ô THAO TÁC của Tự phục vụ — gửi / huỷ đơn của chính mình (tách 11/08/2026). */
  coQuyenGhi: boolean;
}) {
  const [hasEmp, setHasEmp] = useState<boolean | null>(null);
  const [items, setItems] = useState<LeaveRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [quotas, setQuotas] = useState<LeaveQuota[]>([]);
  const [types, setTypes] = useState<LeaveType[]>([]);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<LeaveRequest | null>(null);
  const [form, setForm] = useState({ leave_type_id: "" as number | "", start_date: "", end_date: "", reason: "" });

  const [busy, setBusy] = useState(false);
  /** Lỗi THAO TÁC (gửi đơn) — chỉ hiện trong hộp thoại tạo đơn. */
  const [error, setError] = useState<string | null>(null);
  /** Lỗi TẢI DANH SÁCH — ô nhớ RIÊNG. Gộp chung với `error` thì một lần gửi đơn hỏng cũng
   *  làm cả bảng đơn của mình biến mất. */
  const [listError, setListError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);

  // Đọc id đơn đang mở qua ref để `load` KHÔNG phụ thuộc `selectedRequest`.
  // Nếu để trong deps + setSelectedRequest bên trong load → vòng lặp reopen: đóng modal
  // xong các load() cũ resolve lại set selectedRequest → popup bật lên liên tục.
  const selectedIdRef = useRef<number | null>(null);
  useEffect(() => { selectedIdRef.current = selectedRequest?.id ?? null; }, [selectedRequest]);

  const load = useCallback(() => {
    setLoadingList(true);
    setListError(null);
    api.leaves.me(token, { page, size: PAGE_SIZE }).then((r) => {
      setHasEmp(r.has_employee);
      setItems(r.items);
      setTotal(r.total);
      // `quotas` KHÔNG bị phân trang (backend tính theo cả năm) — vẫn đúng ở mọi trang.
      setQuotas(r.quotas ?? []);
      const trangCanVe = trangHopLe(page, r.total, PAGE_SIZE);
      if (trangCanVe !== null) setPage(trangCanVe);

      // Nếu modal đang mở thì đồng bộ lại trạng thái đơn (chỉ khi id còn khớp).
      // ⚠ Chỉ dò trong TRANG hiện tại. Không tìm thấy thì GIỮ NGUYÊN đơn đang mở chứ đừng đóng
      // modal — hủy một đơn ở trang 2 có thể đẩy nó khỏi trang, đóng phụt là người dùng mất
      // luôn màn xác nhận việc mình vừa làm.
      const openId = selectedIdRef.current;
      if (openId != null) {
        const updated = r.items.find((item) => item.id === openId);
        if (updated) setSelectedRequest(updated);
      }
    })
      // ⚠ TRƯỚC ĐÂY `.catch(() => setHasEmp(false))` — gọi hỏng (mất mạng, 500) cũng in
      // "tài khoản chưa gắn hồ sơ nhân viên": máy NÓI SAI, người dùng đi tìm HCNS trong khi
      // lỗi là ở đường mạng. Giờ lỗi tải nằm ở `listError`, `hasEmp` chỉ đổi khi máy chủ
      // thực sự trả lời.
      .catch((e) => setListError(errMsg(e)))
      .finally(() => setLoadingList(false));
  }, [token, page]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.leaves.types(token).then((r) => setTypes(r.items.filter((t) => t.is_active))).catch(() => {}); }, [token]);

  async function submit() {
    setBusy(true); setError(null);
    try {
      if (form.leave_type_id === "") throw new ApiError("Chọn loại nghỉ.", 400);
      // Chốt THẬT cho ngày ngược (`min` trên ô date không chặn được vì nút Gửi không phải submit
      // của <form>). Dùng ĐÚNG câu chữ của backend `leave_service.create_request` — hai tầng nói
      // hai kiểu thì người dùng tưởng là hai lỗi khác nhau.
      if (form.start_date && form.end_date && form.end_date < form.start_date)
        throw new ApiError("Đến ngày phải sau hoặc bằng từ ngày.", 400);
      const created = await api.leaves.create(token, {
        leave_type_id: form.leave_type_id, start_date: form.start_date, end_date: form.end_date, reason: form.reason || null,
      });
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      setIsCreateOpen(false);
      // Đơn mới xếp đầu (start_date giảm dần) ⇒ về trang 1, không thì gửi đơn xong đang đứng
      // trang 3 sẽ không thấy đơn mình vừa gửi đâu cả.
      if (page !== 1) setPage(1);   // đổi trang ⇒ effect tự gọi lại `load`
      else load();
      onChanged?.();
      setSelectedRequest(created); // Open details modal of newly created request
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }
  
  async function cancel(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn hủy đơn xin nghỉ này không?")) return;
    setBusy(true);
    try {
      await api.leaves.cancel(token, id);
      setSelectedRequest(null);
      load(); 
      onChanged?.();
    } catch (e) {
      alert(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  if (hasEmp === false) {
    return <div className="banner banner--warn" style={{ marginTop: 12 }}>
      Tài khoản của bạn <strong>chưa gắn hồ sơ nhân viên</strong> nên không tạo đơn nghỉ được. Liên hệ HCNS.
    </div>;
  }

  return (
    <div>
      {quotas.length > 0 ? (
        <div className="cc-leave-header-strip">
          <div className="cc-quota-chips">
            {quotas.map((q) => {
              const isLow = q.remaining <= 0;
              const isMedium = q.remaining > 0 && q.remaining <= 2;
              const tone = isLow ? "low" : isMedium ? "medium" : "high";
              return (
                <div key={q.leave_type_id} className={`cc-quota-chip cc-quota-chip--${tone}`}>
                  <span className="cc-quota-chip-label">{q.name}</span>
                  <span className="cc-quota-chip-val">
                    còn <strong>{q.remaining}</strong>/{q.annual_quota} ngày
                  </span>
                  <span className="cc-quota-chip-sub">(đã dùng {q.used} ngày)</span>
                </div>
              );
            })}
          </div>

          <div className="cc-leave-header-right">
            <span className="cc-note-inline">
              <Info size={13} className="cc-note-inline-icon" />
              <span>Click dòng để xem chi tiết</span>
            </span>
            {/* Hành động chính của tab → cam. Lớp cũ `cc-btn-cta-compact` ép navy bằng 6
                dòng `!important`, gỡ nó ra là mất luôn hình dạng nút ⇒ thay bằng
                `ns-btn-cta` (chỉ giữ dáng: đậm chữ + không rớt dòng, KHÔNG khai màu). */}
            {coQuyenGhi && (
              <Button variant="accent" className="ns-btn-cta" onClick={() => { setIsCreateOpen(true); setError(null); }}>
                <Plus size={15} />
                <span>Xin nghỉ phép</span>
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="cc-leave-header-strip cc-leave-header-strip--simple">
          <span className="cc-note-inline">
            <Info size={13} className="cc-note-inline-icon" />
            <span>Click vào dòng bản ghi để xem chi tiết tiến trình đơn</span>
          </span>
          {coQuyenGhi && (
            <Button variant="accent" className="ns-btn-cta" onClick={() => { setIsCreateOpen(true); setError(null); }}>
              <Plus size={15} />
              <span>Xin nghỉ phép</span>
            </Button>
          )}
        </div>
      )}

      <LeaveTable
        items={items}
        showEmployee={false}
        onCancel={cancel}
        onRowClick={(r) => setSelectedRequest(r)}
        loading={loadingList}
        listError={listError}
        onRetry={load}
      />

      {/* Chân bảng CHỈ hiện khi có dòng (chuẩn §2.7) — lúc tải/lỗi/rỗng thì khối trong bảng
          đã nói hết rồi. */}
      {!loadingList && !listError && items.length > 0 && (
        <Pager
          total={total}
          page={page}
          size={PAGE_SIZE}
          loading={loadingList}
          unit="đơn"
          onPage={setPage}
        />
      )}

      {isCreateOpen && (
        <LeaveRequestFormModal 
          types={types}
          busy={busy}
          error={error}
          form={form}
          setForm={setForm}
          onClose={() => setIsCreateOpen(false)}
          onSubmit={submit}
        />
      )}

      {selectedRequest && (
        <LeaveRequestDetailModal 
          request={selectedRequest}
          busy={busy}
          onClose={() => setSelectedRequest(null)}
          onCancel={cancel}
        />
      )}
    </div>
  );
}
