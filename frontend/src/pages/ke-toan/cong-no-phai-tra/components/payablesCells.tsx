// Ô/nhãn nhỏ dùng lại khắp màn Công nợ phải trả (tách từ pages/AccountingPayablesPage.tsx).
import {
  assetUrl,
  type PayableItemRow,
  type PayableSupplierRow,
} from "../../../../api/client";
import { Icon } from "../../../../components/Icons";
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

/** Số hoá đơn — nhiều đợt cùng số nghĩa là cùng MỘT hoá đơn.
 *
 *  `files` = ảnh/PDF hoá đơn đã đính kèm lúc GHI ĐỢT GIAO bên Thu mua (04/09/2026: *"Hóa đơn có
 *  file hóa đơn thì hiện ra đây luôn"*). CHỈ ĐỌC ở đây — mở tab mới xem, không upload/xoá được từ
 *  màn Công nợ. Số hoá đơn và file là HAI thứ độc lập: có số mà chưa có ảnh vẫn hoàn toàn bình
 *  thường (ghi tay trước, chụp ảnh sau), nên hai phần không chờ nhau. */
export function HoaDon({
  so,
  ngay,
  files,
}: {
  so: string | null;
  ngay?: string | null;
  files?: { id: number; file_name: string; file_url: string; file_type: string | null }[];
}) {
  return (
    <>
      {so ? <strong>{so}</strong> : <small className="pay-cell--zero">chưa ghi</small>}
      {ngay && <small> {fmtDate(ngay)}</small>}
      {files && files.length > 0 && (
        <a
          className="pay-hoadon-file"
          href={assetUrl(files[0].file_url) ?? "#"}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          title={
            files.length > 1
              ? `Xem ${files[0].file_name} (+${files.length - 1} file khác)`
              : `Xem ${files[0].file_name}`
          }
        >
          <Icon name="fileText" size={13} />
          {files.length > 1 && <span>×{files.length}</span>}
        </a>
      )}
    </>
  );
}

/** Rổ tuổi 31–60 ngày trở lên mới lên mức "danger" — dưới đó (1–7 / 8–15 / 16–30) chỉ "warn".
 *  Mốc lấy đúng biên `d31_60`/`d60_plus` của `AGING_BUCKETS` (accounting_service.py) — mới trễ
 *  vài ngày mà tô đỏ y hệt trễ hai tháng thì kế toán hết cách biết cái nào phải xử trước. */
const AGING_DANGER: ReadonlySet<string> = new Set(["d31_60", "d60_plus"]);

/** Hạn trả của MỘT đợt giao + mức khẩn. Đợt chưa có hạn không bao giờ vào cột Quá hạn nên phải
 *  đeo badge — nó đã được server đẩy lên đầu danh sách, đây là nửa còn lại của việc chống giấu nợ.
 *  Số ngày trễ GIỮ NGUYÊN chính xác (không quy tròn về khoảng) — chỉ đổi MÀU theo rổ tuổi. */
export function HanTra({ row }: { row: PayableItemRow }) {
  if (row.chua_dat_han) {
    return (
      <span className="pay-badge pay-badge--warn">
        <i className="pay-badge__dot" />
        {row.delivery_id == null ? "Đơn không theo đợt" : "Chưa đặt hạn"}
      </span>
    );
  }
  return (
    <>
      {fmtDate(row.due_date)}
      {row.overdue_days > 0 && (
        <span
          className={`pay-badge pay-badge--${
            row.aging_bucket && AGING_DANGER.has(row.aging_bucket) ? "danger" : "warn"
          }`}
        >
          <i className="pay-badge__dot" />
          Quá hạn {row.overdue_days} ngày
        </span>
      )}
    </>
  );
}
