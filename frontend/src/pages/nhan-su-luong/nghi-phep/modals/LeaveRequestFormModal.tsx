// Modal tạo đơn xin nghỉ (tách từ pages/NghiPhepPage.tsx).
import type { LeaveType } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { AlertTriangle } from "lucide-react";

export function LeaveRequestFormModal({
  types,
  busy,
  error,
  form,
  setForm,
  onClose,
  onSubmit,
}: {
  types: LeaveType[];
  busy: boolean;
  error: string | null;
  form: { leave_type_id: number | ""; start_date: string; end_date: string; reason: string };
  setForm: React.Dispatch<React.SetStateAction<{ leave_type_id: number | ""; start_date: string; end_date: string; reason: string }>>;
  onClose: () => void;
  onSubmit: () => void;
}) {
  // Ngày ngược (vd 1/8 → 31/7). Backend đã chặn (`leave_service.create_request`), nhưng để nó
  // chặn nghĩa là bắt người dùng đi hết một vòng gửi–chờ–báo đỏ mới biết mình gõ nhầm.
  const ngayNguoc = !!form.start_date && !!form.end_date && form.end_date < form.start_date;
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Tạo đơn xin nghỉ phép</h2>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: "16px" }}>{error}</div>}

          <label className="ns-field">
            <span className="cc-field-label">Loại nghỉ *</span>
            <select value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value === "" ? "" : Number(e.target.value) })}>
              <option value="">— chọn —</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_paid ? " (có lương)" : " (không lương)"}</option>)}
            </select>
          </label>

          <div className="ns-grid" style={{ marginTop: 14 }}>
            <label className="ns-field">
              <span className="cc-field-label">Từ ngày *</span>
              {/* Đẩy "Từ ngày" vượt qua "Đến ngày" đã chọn ⇒ kéo Đến ngày theo. Nghỉ 1 ngày là ca
                  phổ biến nhất nên đây gần như luôn đúng ý, và người dùng THẤY ô đổi trước mắt
                  chứ không bị sửa lén lúc bấm Gửi. */}
              <input
                type="date"
                value={form.start_date}
                onChange={(e) => {
                  const bd = e.target.value;
                  setForm({
                    ...form,
                    start_date: bd,
                    end_date: bd && form.end_date && form.end_date < bd ? bd : form.end_date,
                  });
                }}
              />
            </label>
            <label className="ns-field">
              <span className="cc-field-label">Đến ngày *</span>
              {/* `min` chỉ làm mờ ngày trong lịch chọn — nút Gửi là onClick thường chứ không phải
                  submit của <form> nên validation gốc của trình duyệt KHÔNG BAO GIỜ chạy, gõ tay
                  vẫn lọt. Chốt thật nằm ở `submit()`. */}
              <input
                type="date"
                min={form.start_date || undefined}
                value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
              />
            </label>
          </div>
          {ngayNguoc && (
            <div className="banner banner--error" style={{ marginTop: 10 }}>
              Đến ngày phải sau hoặc bằng từ ngày.
            </div>
          )}

          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Lý do xin nghỉ</span>
            <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="vd: Về quê, khám bệnh…" />
          </label>

          <div className="cc-info-card-note" style={{ marginTop: 16 }}>
            <AlertTriangle size={14} className="cc-note-icon" />
            <span>Ngày nghỉ theo lịch công ty (mặc định Chủ nhật) và ngày lễ không trừ vào phép năm. Đơn xin nghỉ phép năm sẽ bị chặn khi vượt quá số ngày phép còn lại.</span>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          {/* Hành động chính của hộp thoại → cam. Nút "Hủy" bên cạnh là ghost. */}
          <Button variant="accent" onClick={onSubmit} loading={busy}>
            {busy ? "Đang gửi đơn…" : "Gửi đơn xin nghỉ"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
