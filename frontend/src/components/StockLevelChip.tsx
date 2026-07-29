// Đèn tín hiệu tồn kho — 5 mức, LUÔN kèm CHỮ (không bao giờ chỉ có màu: người mù màu và
// bản in đen trắng đều phải đọc được). Con số tồn KHÔNG bao giờ nằm trong chip; ai có
// `can_view_stock` thì số đi vào `title` (tooltip), còn ô vẫn là đèn.
import type { StockLevel } from "../api/client";
import "../pages/kho-request.css";

export const STOCK_LEVEL_LABEL: Record<StockLevel, string> = {
  du_ton: "Dư",
  du: "Đủ",
  can_mua: "Cần mua",
  het: "Hết",
};

/** Tông `.badge-sem--*` theo mức. `du_ton` dùng steel (xanh xám) — dư thừa là bất thường
 *  về vốn nhưng KHÔNG phải cảnh báo, nên tách hẳn khỏi dải moss/rust/signal. */
const TONE: Record<StockLevel, string> = {
  du_ton: "steel",
  du: "moss",
  can_mua: "rust",
  het: "signal",
};

/** Xấu dần: het > can_mua > du > du_ton. */
const RANK: Record<StockLevel, number> = { het: 4, can_mua: 3, du: 1, du_ton: 0 };

/** Mức XẤU NHẤT trong nhiều dòng — 1 đèn cho cả đề nghị ở màn danh sách. */
export function worstStockLevel(levels: (StockLevel | null | undefined)[]): StockLevel | null {
  let worst: StockLevel | null = null;
  for (const lv of levels) {
    if (!lv) continue;
    if (worst === null || RANK[lv] > RANK[worst]) worst = lv;
  }
  return worst;
}

interface StockLevelChipProps {
  /** null/undefined → KHÔNG render gì (đề nghị NHẬP cố ý không có đèn). */
  level: StockLevel | null | undefined;
  title?: string;
}

export function StockLevelChip({ level, title }: StockLevelChipProps) {
  if (!level) return null;
  return (
    <span className={`badge-sem badge-sem--${TONE[level]}`} title={title}>
      <span className={`kho-dot kho-dot--${level}`} aria-hidden="true" />
      {STOCK_LEVEL_LABEL[level]}
    </span>
  );
}
