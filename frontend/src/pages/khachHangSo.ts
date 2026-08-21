/** Hai phép tính SỐ của màn Khách hàng, tách ra khỏi component để test được.
 *
 *  Cả hai từng cho ra con số SAI mà vẫn trông hợp lý — đúng loại lỗi không ai phát hiện bằng mắt,
 *  nên chúng ở đây kèm test thay vì nằm trong một `useMemo` giữa 4000 dòng JSX.
 */
import type { OrderHistoryRow, QuoteHistoryRow } from "../api/client";

// --- TỈ LỆ CHỐT ---------------------------------------------------------------------------
//
// Phải khớp Y HỆT `CHOT_THANG` / `CHOT_DA_CHAO` ở `backend/app/services/customer_analytics.py`.
// Hai nơi cùng tính một chỉ số là mầm lệch số; giữ được vì frontend BẮT BUỘC tính lại — bộ lọc
// theo năm cắt tập báo giá, mà backend chỉ trả con số lifetime.
//
export const CHOT_THANG = ["accepted", "converted_to_order"];

// Mẫu số CHỈ gồm báo giá khách ĐÃ THẤY. Loại `draft` · `pending_approval` · `approved` (chưa ra
// khỏi cửa) và `cancelled` (mình tự huỷ, không phải khách chê) — để chúng trong mẫu số là tự trừ
// điểm vì những việc khách chưa hề biết. `sent` đang chờ trả lời thì VẪN tính: đã chào mà chưa
// chốt được thì chưa phải thắng.
export const CHOT_DA_CHAO = ["sent", "accepted", "rejected", "expired", "converted_to_order"];

export interface TiLeChot {
  thang: number;
  daChao: number;
  pct: number | null;      // null = chưa chào báo giá nào ⇒ KHÔNG hiện 0% (0% đọc ra là "chào mãi không ai mua")
  giaTriThang: number;
}

export function tinhTiLeChot(rows: QuoteHistoryRow[]): TiLeChot {
  const thangRows = rows.filter((q) => CHOT_THANG.includes(q.status));
  const daChao = rows.filter((q) => CHOT_DA_CHAO.includes(q.status)).length;
  return {
    thang: thangRows.length,
    daChao,
    pct: daChao > 0 ? Math.round((thangRows.length / daChao) * 100) : null,
    giaTriThang: thangRows.reduce((s, q) => s + (q.total ?? 0), 0),
  };
}

// --- TOP SẢN PHẨM -------------------------------------------------------------------------

export interface SanPhamGop {
  name: string;
  qty: number;      // số ĐƠN có mặt sản phẩm này (không phải số lượng in)
  total: number;
}

/** Gộp tiền theo sản phẩm từ TIỀN THẬT của từng dòng đơn (`lines[].line_total`).
 *
 *
 *  Đơn cũ (trước khi backend trả `lines`) vẫn lùi về tách `summary`, nhưng KHÔNG chia tiền nữa —
 *  thà thiếu tiền còn hơn tiền bịa; số đơn vẫn đếm được nên dòng đó không biến mất.
 */
export function gopTienTheoSanPham(rows: OrderHistoryRow[], top = 4): SanPhamGop[] {
  const gop: Record<string, { qty: number; total: number }> = {};
  const cong = (ten: string, tien: number) => {
    const k = ten.trim();
    if (!k) return;
    if (!gop[k]) gop[k] = { qty: 0, total: 0 };
    gop[k].qty += 1;
    gop[k].total += tien;
  };
  for (const o of rows) {
    if (o.lines && o.lines.length > 0) {
      for (const d of o.lines) cong(d.description || "Sản phẩm khác", d.line_total ?? 0);
    } else {
      for (const p of (o.summary || "Sản phẩm khác").split(",")) cong(p, 0);
    }
  }
  return Object.entries(gop)
    .map(([name, stat]) => ({ name, ...stat }))
    .sort((a, b) => b.total - a.total || b.qty - a.qty)
    .slice(0, top);
}
