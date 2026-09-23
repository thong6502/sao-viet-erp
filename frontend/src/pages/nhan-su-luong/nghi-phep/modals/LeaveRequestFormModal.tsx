// Modal tạo đơn xin nghỉ phép (tách từ pages/NghiPhepPage.tsx).
import type React from "react";
import type { LeaveType } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { CalendarPlus, Calendar, Clock, Info } from "lucide-react";

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

  // Tính số ngày nghỉ dự kiến khi ngày hợp lệ
  let soNgay: number | null = null;
  if (form.start_date && form.end_date && !ngayNguoc) {
    const start = new Date(form.start_date + "T00:00:00");
    const end = new Date(form.end_date + "T00:00:00");
    const diffDays = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
    if (diffDays > 0) soNgay = diffDays;
  }

  const selectedType = types.find((t) => t.id === form.leave_type_id);

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="leave-form-modal-title">
      <div className="ns-modal__box cc-leave-form-modal">
        {/* Header với icon emblem */}
        <header className="cc-modal-header">
          <div className="cc-modal-header__main">
            <div className="cc-modal-emblem">
              <CalendarPlus size={22} className="cc-modal-emblem__icon" />
            </div>
            <div className="cc-modal-header__text">
              <h2 id="leave-form-modal-title" className="cc-modal-header__title">
                Tạo đơn xin nghỉ phép
              </h2>
              <p className="cc-modal-header__subtitle">
                Gửi đơn đến quản lý trực tiếp &amp; bộ phận nhân sự phê duyệt
              </p>
            </div>
          </div>
          <button
            type="button"
            className="cc-modal-close-btn"
            onClick={onClose}
            aria-label="Đóng"
            disabled={busy}
          >
            ×
          </button>
        </header>

        {/* Body */}
        <div className="cc-modal-body">
          {error && (
            <div className="banner banner--error cc-modal-error-banner" role="alert">
              {error}
            </div>
          )}

          {/* Chọn loại nghỉ với badge Có lương / Không lương */}
          <div className="cc-form-section">
            <div className="cc-form-label-row">
              <label htmlFor="leave-type-select" className="cc-form-label">
                Loại nghỉ <span className="cc-form-required">*</span>
              </label>
              {selectedType && (
                <span
                  className={`cc-type-badge ${
                    selectedType.is_paid ? "cc-type-badge--paid" : "cc-type-badge--unpaid"
                  }`}
                >
                  {selectedType.is_paid ? "Có lương" : "Không lương"}
                </span>
              )}
            </div>
            <select
              id="leave-type-select"
              className="cc-form-select"
              value={form.leave_type_id}
              onChange={(e) =>
                setForm({
                  ...form,
                  leave_type_id: e.target.value === "" ? "" : Number(e.target.value),
                })
              }
            >
              <option value="">— chọn —</option>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} {t.is_paid ? "(Có lương)" : "(Không lương)"}
                  {t.annual_quota > 0 ? ` · Hạn mức ${t.annual_quota} ngày/năm` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Date range selector: Dual cards/inputs với duration live calculation */}
          <div className="cc-form-section">
            <div className="cc-form-label-row">
              <span className="cc-form-label">
                Thời gian nghỉ <span className="cc-form-required">*</span>
              </span>
              {soNgay !== null && (
                <span className="cc-duration-badge">
                  <Clock size={12} className="cc-duration-icon" />
                  {soNgay === 1 ? "1 ngày nghỉ" : `${soNgay} ngày nghỉ`}
                </span>
              )}
            </div>

            <div className="cc-date-dual-grid">
              <div className="cc-date-card">
                <label htmlFor="leave-start-date" className="cc-date-card__header">
                  <Calendar size={14} className="cc-date-card__icon" />
                  <span>Từ ngày *</span>
                </label>
                <input
                  id="leave-start-date"
                  type="date"
                  className="cc-date-card__input"
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
              </div>

              <div className="cc-date-card">
                <label htmlFor="leave-end-date" className="cc-date-card__header">
                  <Calendar size={14} className="cc-date-card__icon" />
                  <span>Đến ngày *</span>
                </label>
                <input
                  id="leave-end-date"
                  type="date"
                  className="cc-date-card__input"
                  min={form.start_date || undefined}
                  value={form.end_date}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                />
              </div>
            </div>

            {ngayNguoc && (
              <div className="banner banner--error cc-date-inline-error" role="alert">
                Đến ngày phải sau hoặc bằng từ ngày.
              </div>
            )}
          </div>

          {/* Textarea lý do xin nghỉ */}
          <div className="cc-form-section">
            <div className="cc-form-label-row">
              <label htmlFor="leave-reason-textarea" className="cc-form-label">
                Lý do xin nghỉ
              </label>
              <span className="cc-form-hint">Tối đa 500 ký tự</span>
            </div>
            <textarea
              id="leave-reason-textarea"
              className="cc-form-textarea"
              rows={3}
              maxLength={500}
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="vd: Về quê, khám bệnh…"
            />
          </div>

          {/* Policy info callout card */}
          <div className="cc-policy-card">
            <div className="cc-policy-card__icon-wrap">
              <Info size={16} className="cc-policy-card__icon" />
            </div>
            <div className="cc-policy-card__body">
              <div className="cc-policy-card__title">Lưu ý chính sách nghỉ phép</div>
              <p className="cc-policy-card__text">
                Ngày nghỉ theo lịch công ty (mặc định Chủ nhật) và ngày lễ không trừ vào phép năm.
                Đơn xin nghỉ phép năm sẽ bị chặn khi vượt quá số ngày phép còn lại.
              </p>
            </div>
          </div>
        </div>

        {/* Polished footer */}
        <footer className="cc-modal-footer">
          <button
            type="button"
            className="btn btn--ghost cc-modal-btn-cancel"
            onClick={onClose}
            disabled={busy}
          >
            Hủy
          </button>
          <Button
            variant="accent"
            onClick={onSubmit}
            loading={busy}
            disabled={busy || ngayNguoc}
            className="cc-modal-btn-submit"
          >
            {busy ? "Đang gửi đơn…" : "Gửi đơn xin nghỉ"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
