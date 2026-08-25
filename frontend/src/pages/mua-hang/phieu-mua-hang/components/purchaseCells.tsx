// Ô/nhãn nhỏ dùng lại khắp màn Mua hàng (tách từ pages/PurchaseRequestsPage.tsx).
import type { ReactNode } from "react";
import type {
  DepartmentPurchaseWorkflowStatus,
  PurchaseRequestRow,
  PurchaseRequestStatus,
} from "../../../../api/client";
import { money } from "../../../../utils/format";
import { SOURCE_STATUS_META, STATUS_META } from "../shared/constants";

export function DepositCell({ row }: { row: PurchaseRequestRow }) {
  if ((row.deposit_expected ?? 0) <= 0) {
    return <span className="md-page__muted">-</span>;
  }
  const paid = row.coc_da_chi ?? 0;
  const expected = row.deposit_expected ?? 0;
  const tone = paid >= expected ? "ok" : paid > 0 ? "warn" : "empty";
  return (
    <div className={`purchase__deposit purchase__deposit--${tone}`}>
      <strong>{money(paid)}</strong>
      <span>/ {money(expected)}</span>
    </div>
  );
}

export function StatusBadge({ status }: { status: PurchaseRequestStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>
      {meta.label}
    </span>
  );
}

export function SourceStatusBadge({
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

export function LocalField({
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
