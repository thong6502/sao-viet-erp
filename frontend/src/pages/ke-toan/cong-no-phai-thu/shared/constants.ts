// Hằng dùng chung của màn Công nợ phải thu (tách từ pages/AccountingReceivablesPage.tsx).
import type { ListFilter } from "./types";

export const LIST_FILTERS: { id: ListFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "overdue", label: "Quá hạn" },
  { id: "chua_han", label: "Chưa tới hạn" },
  { id: "vuot_han_muc", label: "Vượt hạn mức" },
];

export const PAGE_SIZE = 20;
