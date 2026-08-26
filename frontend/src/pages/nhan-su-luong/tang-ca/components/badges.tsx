// Badge trạng thái phiếu tăng ca (tách từ pages/TangCaPage.tsx).
import { STATUS_LABEL } from "../shared/constants";

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`tc-badge tc-badge--${status}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
