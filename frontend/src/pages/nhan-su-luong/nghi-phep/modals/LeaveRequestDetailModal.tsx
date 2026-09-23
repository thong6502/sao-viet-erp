// Panel chi tiết một đơn nghỉ (tách từ pages/NghiPhepPage.tsx).
import type { LeaveRequest } from "../../../../api/client";
import { Timeline, type TimelineEntry } from "../../../../components/Timeline";
import { fmtDate, fmtDateTime } from "../../../../utils/format";
import { dangXinHuy, homNayYmd } from "../../xin-huy/XinHuy";
import { Calendar, User, FileText, CheckCircle2, AlertCircle } from "lucide-react";

// Timeline trạng thái của 1 đơn (gửi → chờ → kết quả → xin hủy) cho panel chi tiết.
function requestTimeline(r: LeaveRequest): TimelineEntry[] {
  const tl: TimelineEntry[] = [
    { title: "Đã gửi đơn", meta: fmtDate(r.created_at), tone: "moss", accent: true },
  ];
  const yc = r.yeu_cau_huy;
  if (r.status === "pending") tl.push({ title: "Chờ HCNS duyệt…", tone: "rust", accent: true });
  else if (r.status === "rejected") tl.push({ title: "Bị từ chối", meta: r.decision_note ?? undefined, tone: "signal", accent: true });
  else if (r.status === "approved" || (r.status === "cancelled" && r.decided_at)) {
    tl.push({ title: `Đã duyệt${r.is_paid === false ? " (không lương)" : " (tính công P)"}`, meta: [fmtDate(r.decided_at), r.decision_note].filter(Boolean).join(" · ") || undefined, tone: "moss", accent: true });
  }
  // Xin hủy đơn đã duyệt (23/09/2026) — chỉ hiện yêu cầu MỚI NHẤT.
  if (yc && yc.trang_thai !== "rut_lai" && !yc.truc_tiep) {
    tl.push({ title: "Đã xin hủy", meta: [fmtDate(yc.created_at), yc.ly_do].filter(Boolean).join(" · "), tone: "rust" });
    if (yc.trang_thai === "cho") tl.push({ title: "Chờ người duyệt quyết — đơn vẫn hiệu lực", tone: "rust", accent: true });
    else if (yc.trang_thai === "giu_nguyen") tl.push({ title: "Không được hủy — đơn giữ nguyên", meta: [fmtDate(yc.decided_at), yc.decided_by_name, yc.ly_do_quyet].filter(Boolean).join(" · "), tone: "signal", accent: true });
    else if (yc.den_ngay_cu) tl.push({ title: `Đồng ý — rút ngắn còn ${fmtDate(r.start_date)}–${fmtDate(r.end_date)} (gốc tới ${fmtDate(yc.den_ngay_cu)})`, meta: [fmtDate(yc.decided_at), yc.decided_by_name, yc.ly_do_quyet].filter(Boolean).join(" · ") || undefined, tone: "moss", accent: true });
    else tl.push({ title: "Đồng ý hủy — đơn đã hủy", meta: [fmtDate(yc.decided_at), yc.decided_by_name, yc.ly_do_quyet].filter(Boolean).join(" · ") || undefined, tone: "steel", accent: true });
  } else if (r.status === "cancelled") {
    const lyDo = yc?.truc_tiep ? yc.ly_do : undefined;
    tl.push({ title: yc?.truc_tiep ? "Người duyệt đã hủy đơn" : "Đã hủy", meta: [yc?.decided_by_name, lyDo].filter(Boolean).join(" · ") || undefined, tone: "steel" });
  }
  return tl;
}

export function LeaveRequestDetailModal({
  request,
  busy,
  onClose,
  onCancel,
  onXinHuy,
  onRutLaiXinHuy,
}: {
  request: LeaveRequest;
  busy: boolean;
  onClose: () => void;
  /** Hủy thẳng — chỉ đơn đang chờ. */
  onCancel: (id: number) => void;
  onXinHuy?: (r: LeaveRequest) => void;
  onRutLaiXinHuy?: (r: LeaveRequest) => void;
}) {
  const dangXin = dangXinHuy(request.yeu_cau_huy);
  const xinDuoc = request.status === "approved" && !dangXin && request.end_date >= homNayYmd();

  const renderStatusBadge = () => {
    if (dangXin) {
      return (
        <span className="cc-status-pill cc-status-pill--pending">
          <span className="cc-status-dot cc-status-dot--pending" />
          Đang xin hủy
        </span>
      );
    }
    switch (request.status) {
      case "approved":
        return (
          <span className="cc-status-pill cc-status-pill--approved">
            Đã duyệt
          </span>
        );
      case "rejected":
        return (
          <span className="cc-status-pill cc-status-pill--rejected">
            Bị từ chối
          </span>
        );
      case "cancelled":
        return (
          <span className="cc-status-pill cc-status-pill--cancelled">
            <span className="cc-status-dot cc-status-dot--cancelled" />
            Đã hủy
          </span>
        );
      case "pending":
      default:
        return (
          <span className="cc-status-pill cc-status-pill--pending">
            <span className="cc-status-dot cc-status-dot--pending" />
            Chờ HCNS duyệt
          </span>
        );
    }
  };

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="leave-detail-modal-title">
      <div className="ns-modal__box cc-leave-detail-modal">
        {/* Header with status badge right by the title */}
        <header className="cc-detail-header">
          <div className="cc-detail-header__title-group">
            <h2 id="leave-detail-modal-title" className="cc-detail-header__title">
              Chi tiết đơn xin nghỉ
            </h2>
            {renderStatusBadge()}
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

        <div className="cc-modal-body">
          {/* Hero summary banner: leave type (with color badge), dates range, and duration pill */}
          <div className="cc-detail-hero">
            <div className="cc-detail-hero__main">
              <div className="cc-detail-hero__type-row">
                <span className="cc-detail-hero__type">
                  {request.leave_type_name ?? "Đơn xin nghỉ"}
                </span>
                <span
                  className={`cc-type-badge ${
                    request.is_paid === false ? "cc-type-badge--unpaid" : "cc-type-badge--paid"
                  }`}
                >
                  {request.is_paid === false ? "Không lương" : "Có lương"}
                </span>
              </div>
              <div className="cc-detail-hero__dates">
                <Calendar size={13} className="cc-detail-hero__calendar-icon" />
                <span>
                  {fmtDate(request.start_date)} đến {fmtDate(request.end_date)}
                </span>
              </div>
            </div>
            <div className="cc-detail-hero__duration">
              <span className="cc-detail-hero__pill">{request.days} ngày</span>
            </div>
          </div>

          {/* Clean details cards */}
          <div className="cc-detail-cards">
            {/* Người gửi đơn */}
            <div className="cc-detail-card">
              <div className="cc-detail-card__label">
                <User size={13} className="cc-detail-card__icon" />
                <span>Người gửi đơn</span>
              </div>
              <div className="cc-detail-card__val">
                <span className="cc-detail-card__strong">{request.employee_name || "—"}</span>
                {request.created_at && (
                  <span className="cc-detail-card__meta">
                    {" "}· Gửi lúc {fmtDateTime(request.created_at)}
                  </span>
                )}
              </div>
            </div>

            {/* Lý do xin nghỉ */}
            <div className="cc-detail-card">
              <div className="cc-detail-card__label">
                <FileText size={13} className="cc-detail-card__icon" />
                <span>Lý do xin nghỉ</span>
              </div>
              <div className="cc-detail-card__val cc-detail-card__val--reason">
                {request.reason || <span className="cc-detail-card__empty">Không ghi lý do</span>}
              </div>
            </div>

            {/* Người duyệt & ghi chú duyệt nếu có */}
            {(request.decided_at || request.decision_note) && (
              <div className="cc-detail-card">
                <div className="cc-detail-card__label">
                  <CheckCircle2 size={13} className="cc-detail-card__icon" />
                  <span>Duyệt đơn</span>
                </div>
                <div className="cc-detail-card__val">
                  {request.decision_note ? (
                    <div className="cc-detail-decision-note">"{request.decision_note}"</div>
                  ) : (
                    <span className="cc-detail-card__meta">Không có ghi chú</span>
                  )}
                  {request.decided_at && (
                    <div className="cc-detail-card__meta">
                      Thời gian: {fmtDateTime(request.decided_at)}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Thông tin xin hủy nếu có */}
            {request.yeu_cau_huy && request.yeu_cau_huy.trang_thai !== "rut_lai" && (
              <div className="cc-detail-card cc-detail-card--xin-huy">
                <div className="cc-detail-card__label">
                  <AlertCircle size={13} className="cc-detail-card__icon" />
                  <span>Yêu cầu hủy</span>
                </div>
                <div className="cc-detail-card__val">
                  <div className="cc-detail-xh-status">
                    {request.yeu_cau_huy.trang_thai === "cho" && (
                      <span className="ns-badge ns-badge--warn">Đang chờ duyệt hủy</span>
                    )}
                    {request.yeu_cau_huy.trang_thai === "dong_y" && (
                      <span className="ns-badge ns-badge--info">
                        {request.yeu_cau_huy.den_ngay_cu ? "Đồng ý rút ngắn" : "Đã đồng ý hủy"}
                      </span>
                    )}
                    {request.yeu_cau_huy.trang_thai === "giu_nguyen" && (
                      <span className="ns-badge ns-badge--muted">Không được hủy (giữ nguyên)</span>
                    )}
                  </div>
                  <div className="cc-detail-xh-reason">
                    Lý do xin hủy: <strong>{request.yeu_cau_huy.ly_do}</strong>
                  </div>
                  {request.yeu_cau_huy.huy_tu_ngay && (
                    <div className="cc-detail-card__meta">
                      Nghỉ dở dang: Hủy từ {fmtDate(request.yeu_cau_huy.huy_tu_ngay)}, giữ các ngày trước.
                    </div>
                  )}
                  {request.yeu_cau_huy.ly_do_quyet && (
                    <div className="cc-detail-card__meta">
                      Ý kiến người duyệt: {request.yeu_cau_huy.ly_do_quyet}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Polished timeline section */}
          <div className="cc-detail-timeline-section">
            <h4 className="cc-detail-timeline-title">Tiến trình xử lý đơn</h4>
            <div className="cc-detail-timeline-wrap">
              <Timeline items={requestTimeline(request)} />
            </div>
          </div>
        </div>

        {/* Clean action buttons in footer */}
        <footer className="cc-modal-footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
          {request.status === "pending" && (
            <button
              type="button"
              className="btn btn--ghost ns-danger"
              onClick={() => onCancel(request.id)}
              disabled={busy}
            >
              Hủy đơn
            </button>
          )}
          {/* Đơn ĐÃ DUYỆT chỉ được XIN hủy (23/09/2026) — người duyệt quyết, đơn vẫn hiệu lực tới lúc đó. */}
          {xinDuoc && onXinHuy && (
            <button
              type="button"
              className="btn btn--ghost ns-danger"
              onClick={() => onXinHuy(request)}
              disabled={busy}
            >
              Xin hủy đơn
            </button>
          )}
          {dangXin && onRutLaiXinHuy && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => onRutLaiXinHuy(request)}
              disabled={busy}
            >
              Rút lại yêu cầu hủy
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
