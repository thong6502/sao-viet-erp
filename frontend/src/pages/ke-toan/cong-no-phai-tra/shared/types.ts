// Kiểu dùng chung của màn Công nợ phải trả (tách từ pages/AccountingPayablesPage.tsx).
/** Rổ đang xem trong drawer. Bấm số nào ngoài bảng thì mở sẵn rổ đó — đỡ một nhịp lọc tay. */
export type Bucket = "all" | "overdue" | "paid";

/** Lọc ở BẢNG NGOÀI (khác `Bucket` — cái kia lọc trong drawer). */
export type ListFilter = "all" | "overdue" | "chua_han" | "vuot_han_muc";
