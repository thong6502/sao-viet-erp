// Ô/nhãn nhỏ của màn Đơn mua hàng (Kế toán) — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type { PurchaseRequestRow } from "../../../../api/client";
import { money } from "../../../../utils/format";

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
