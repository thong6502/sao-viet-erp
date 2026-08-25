// Ô/nhãn nhỏ dùng lại khắp màn Công nợ phải trả (tách từ pages/AccountingPayablesPage.tsx).
import type {
  PayableItemRow,
  PayableSupplierRow,
} from "../../../../api/client";
import { fmtDate, money } from "../../../../utils/format";
import { BUCKET_LABEL } from "../shared/constants";
import type { Bucket } from "../shared/types";

export function PayCell({
  value,
  row,
  bucket,
  onOpen,
  tone,
  raw,
  strong,
}: {
  value: number;
  row: PayableSupplierRow;
  bucket: Bucket;
  onOpen: (next: { row: PayableSupplierRow; bucket: Bucket }) => void;
  tone?: "warn" | "danger" | "ok";
  raw?: boolean;
  strong?: boolean;
}) {
  // Số không đọc được (server cũ chưa trả trường này) ⇒ `—`, KHÔNG để `money()` đẻ ra "NaN đ".
  // "—" nghĩa là chưa biết, đúng tinh thần: im lặng không được giả làm số 0.
  if (!Number.isFinite(value) || value <= 0)
    return <span className="pay-cell pay-cell--zero">—</span>;
  return (
    <button
      type="button"
      className={`pay-cell pay-cell--link${tone ? ` pay-cell--${tone}` : ""}${
        strong ? " pay-cell--strong" : ""
      }`}
      onClick={() => onOpen({ row, bucket })}
      title={`Xem ${BUCKET_LABEL[bucket].toLowerCase()} của ${row.supplier_name}`}
    >
      {raw ? value : money(value)}
    </button>
  );
}

/** Số hoá đơn — nhiều đợt cùng số nghĩa là cùng MỘT hoá đơn. */
export function HoaDon({ so, ngay }: { so: string | null; ngay?: string | null }) {
  if (!so) return <small className="pay-cell--zero">chưa ghi</small>;
  return (
    <>
      <strong>{so}</strong>
      {ngay && <small> {fmtDate(ngay)}</small>}
    </>
  );
}

/** Hạn trả của MỘT đợt giao + mức khẩn. Đợt chưa có hạn không bao giờ vào cột Quá hạn nên phải
 *  đeo badge — nó đã được server đẩy lên đầu danh sách, đây là nửa còn lại của việc chống giấu nợ. */
export function HanTra({ row }: { row: PayableItemRow }) {
  if (row.chua_dat_han) {
    return (
      <span className="pay-badge pay-badge--warn">
        {row.delivery_id == null ? "Đơn không theo đợt" : "Chưa đặt hạn"}
      </span>
    );
  }
  return (
    <>
      {fmtDate(row.due_date)}
      {row.overdue_days > 0 && (
        <span className="pay-badge pay-badge--danger">
          Quá hạn {row.overdue_days} ngày
        </span>
      )}
    </>
  );
}
