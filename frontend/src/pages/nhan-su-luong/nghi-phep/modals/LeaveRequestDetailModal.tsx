// Panel chi tiết một đơn nghỉ (tách từ pages/NghiPhepPage.tsx).
import type { LeaveRequest } from "../../../../api/client";
import { Timeline, type TimelineEntry } from "../../../../components/Timeline";
import { fmtDate } from "../../../../utils/format";

// Timeline trạng thái của 1 đơn (gửi → chờ → kết quả) cho panel chi tiết.
function requestTimeline(r: LeaveRequest): TimelineEntry[] {
  const tl: TimelineEntry[] = [
    { title: "Đã gửi đơn", meta: fmtDate(r.created_at), tone: "moss", accent: true },
  ];
  if (r.status === "pending") tl.push({ title: "Chờ HCNS duyệt…", tone: "rust", accent: true });
  else if (r.status === "approved") tl.push({ title: `Đã duyệt${r.is_paid === false ? " (không lương)" : " (tính công P)"}`, meta: [fmtDate(r.decided_at), r.decision_note].filter(Boolean).join(" · ") || undefined, tone: "moss", accent: true });
  else if (r.status === "rejected") tl.push({ title: "Bị từ chối", meta: r.decision_note ?? undefined, tone: "signal", accent: true });
  else if (r.status === "cancelled") tl.push({ title: "Đã hủy", tone: "steel" });
  return tl;
}

export function LeaveRequestDetailModal({
  request,
  busy,
  onClose,
  onCancel,
}: {
  request: LeaveRequest;
  busy: boolean;
  onClose: () => void;
  onCancel: (id: number) => void;
}) {
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Chi tiết đơn xin nghỉ</h2>
            <p className="cc-modal-subtitle">
              {request.leave_type_name ?? "—"} · {fmtDate(request.start_date)}–{fmtDate(request.end_date)} ({request.days} ngày)
            </p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          <div className="ns-kv">
            <span className="ns-kv__k">Loại nghỉ</span>
            <span className="ns-kv__v">{request.leave_type_name ?? "—"}{request.is_paid === false ? " (Không lương)" : " (Có lương)"}</span>
          </div>
          <div className="ns-kv">
            <span className="ns-kv__k">Thời gian nghỉ</span>
            <span className="ns-kv__v">{fmtDate(request.start_date)} đến {fmtDate(request.end_date)} ({request.days} ngày)</span>
          </div>
          <div className="ns-kv">
            <span className="ns-kv__k">Lý do xin nghỉ</span>
            <span className="ns-kv__v">{request.reason || "—"}</span>
          </div>
          {request.decision_note && (
            <div className="ns-kv">
              <span className="ns-kv__k">Ghi chú duyệt</span>
              <span className="ns-kv__v">{request.decision_note}</span>
            </div>
          )}
          
          <h4 className="ns-section__title" style={{ marginTop: 20, marginBottom: 10 }}>Tiến trình xử lý đơn</h4>
          <Timeline items={requestTimeline(request)} />
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>Đóng</button>
          {(request.status === "pending" || request.status === "approved") && (
            <button className="btn btn--ghost ns-danger" onClick={() => onCancel(request.id)} disabled={busy}>Hủy đơn</button>
          )}
        </footer>
      </div>
    </div>
  );
}
