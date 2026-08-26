// Hàm dùng chung của màn Công nợ phải trả (tách từ pages/AccountingPayablesPage.tsx).
import type { PayableItemRow, PayablesDetail } from "../../../../api/client";
import { money } from "../../../../utils/format";

/** `—` khi CHƯA BIẾT (đang tải / lỗi), số khi đã tính ra. Đừng bao giờ lẫn hai thứ. */
export function kpi(value: number | undefined, biet: boolean): string {
  return biet && value != null ? money(value) : "—";
}

/** Nhãn một khoản nợ trong phạm vi MỘT đơn: "Đợt 2", hoặc "Cả đơn" với đơn cũ không theo đợt. */
export function tenKhoan(row: PayableItemRow): string {
  return row.seq_no != null ? `Đợt ${row.seq_no}` : "Cả đơn";
}

/** Gom các khoản nợ theo ĐƠN MUA, giữ nguyên thứ tự server đã sắp (hạn trả, chưa-có-hạn lên đầu).
 *
 *  Vì sao phải gom (chủ 07/08/2026): đổ phẳng mọi đợt của mọi PMH vào một bảng thì có 3 đơn là ba
 *  nhóm đợt trộn lẫn, và dòng "Đặt cọc cho cả đơn" ở dưới gộp cọc của cả ba — ghi "cả đơn" mà liệt
 *  kê ba mã, không ai biết cọc nào của đơn nào. Gom lại thì mỗi đơn tự mang cọc của chính nó. */
export function gomTheoDon(items: PayableItemRow[], cocs: PayablesDetail["coc_chung"]) {
  const cocTheoDon = new Map(cocs.map((c) => [c.purchase_request_id, c]));
  const nhom = new Map<
    number,
    { code: string; items: PayableItemRow[]; coc: PayablesDetail["coc_chung"][number] | null }
  >();
  for (const row of items) {
    let g = nhom.get(row.purchase_request_id);
    if (!g) {
      g = {
        code: row.code,
        items: [],
        coc: cocTheoDon.get(row.purchase_request_id) ?? null,
      };
      nhom.set(row.purchase_request_id, g);
    }
    g.items.push(row);
  }
  return [...nhom.entries()].map(([id, g]) => ({
    purchase_request_id: id,
    ...g,
    con_no: g.items.reduce((sum, r) => sum + r.con_no, 0),
  }));
}
