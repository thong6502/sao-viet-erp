// Badge trạng thái đơn nghỉ phép (tách từ pages/NghiPhepPage.tsx).
import { CheckCircle2, XCircle } from "lucide-react";
import { STATUS_LABEL } from "../shared/constants";

export function StatusBadge({ s }: { s: string }) {
  if (s === "approved") {
    return (
      <span className="cc-status-pill cc-status-pill--approved">
        <CheckCircle2 size={12} />
        <span>Đã duyệt</span>
      </span>
    );
  }
  if (s === "pending") {
    return (
      <span className="cc-status-pill cc-status-pill--pending">
        <span className="cc-status-dot cc-status-dot--pending" />
        <span>Chờ duyệt</span>
      </span>
    );
  }
  if (s === "rejected") {
    return (
      <span className="cc-status-pill cc-status-pill--rejected">
        <XCircle size={12} />
        <span>Từ chối</span>
      </span>
    );
  }
  return (
    <span className="cc-status-pill cc-status-pill--cancelled">
      <span className="cc-status-dot cc-status-dot--cancelled" />
      <span>{STATUS_LABEL[s] ?? s}</span>
    </span>
  );
}
