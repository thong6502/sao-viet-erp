// Hằng dùng chung của màn Công nợ phải trả (tách từ pages/AccountingPayablesPage.tsx).
import type { Bucket, ListFilter } from "./types";

export const BUCKET_LABEL: Record<Bucket, string> = {
  all: "Tất cả đợt còn nợ",
  overdue: "Quá hạn",
  paid: "Đã trả",
};

export const LIST_FILTERS: { id: ListFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "overdue", label: "Quá hạn" },
  { id: "chua_han", label: "Chưa tới hạn" },
  { id: "vuot_han_muc", label: "Vượt hạn mức" },
];

export const PAID_PAGE = 10;
export const PAGE_SIZE = 20;
