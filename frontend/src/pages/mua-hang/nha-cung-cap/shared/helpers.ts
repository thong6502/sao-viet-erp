// Hàm dùng chung của màn Nhà cung cấp (tách từ pages/SuppliersPage.tsx).
import type {
  SupplierInput,
  SupplierItemInput,
  SupplierRow,
} from "../../../../api/client";

/** Số ngày kiểu Việt: 8.5 → "8,5", 3 → "3". Dùng cho "trễ TB … ngày" ở cột Đánh giá và hồ sơ NCC.
 *  `null` (chưa trễ đơn nào) → "0" — chỗ gọi phải tự quyết có hiện hay không, đừng in "null". */
export function soNgayVi(v: number | null): string {
  return (v ?? 0).toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

/** Khoá TRÙNG của một mặt hàng = tên + đơn vị, bỏ hoa/thường và khoảng trắng thừa.
 *  Phải khớp `_khoa_vat_tu` bên service — lệch nhau thì máy nói trùng mà màn hình nói không. */
export function khoaVatTu(item: { item_name: string; unit: string }): string {
  return `${item.item_name.trim().replace(/\s+/g, " ").toLowerCase()}|${item.unit
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase()}`;
}

/** Gộp danh sách vừa đọc từ Excel VÀO danh sách đang có trong form.
 *
 *  THÊM VÀO, không thay thế (chủ chốt 07/08/2026): thay cả danh mục là một cú bấm xoá sạch bảng
 *  giá mà không ai lường trước. Trùng tên + đơn vị ⇒ cập nhật dòng đó, không đẻ dòng thứ hai —
 *  hai dòng cùng tên cùng ĐVT khác giá thì form phiếu mua không biết chọn cái nào. */
export function gopVatTu(
  dangCo: SupplierItemInput[],
  doc: SupplierItemInput[],
): { items: SupplierItemInput[]; them: number; capNhat: number } {
  // Bỏ dòng trống mà form vẫn luôn chừa sẵn — giữ lại là danh mục có một dòng rác.
  const ket = dangCo.filter((it) => it.item_name.trim() || it.unit.trim());
  const viTri = new Map(ket.map((it, i) => [khoaVatTu(it), i]));
  let them = 0;
  let capNhat = 0;
  for (const moi of doc) {
    const i = viTri.get(khoaVatTu(moi));
    if (i === undefined) {
      viTri.set(khoaVatTu(moi), ket.length);
      ket.push(moi);
      them += 1;
    } else {
      ket[i] = { ...ket[i], ...moi };
      capNhat += 1;
    }
  }
  return { items: ket.length ? ket : [emptySupplierItem()], them, capNhat };
}

export function emptySupplierItem(): SupplierItemInput {
  return {
    item_name: "",
    unit: "",
    unit_price: 0,
    vat_percent: 0,
    note: "",
  };
}

export function emptySupplier(): SupplierInput {
  return {
    name: "",
    tax_code: "",
    phone: "",
    email: "",
    address: "",
    contact_name: "",
    supplier_group: "",
    payment_terms: "",
    // 0 = chưa đặt hạn mức · null = chưa đặt số ngày cho nợ. Hai mặc định này KHÁC nhau về nghĩa,
    // xem hint trên form.
    credit_limit: 0,
    credit_days: null,
    status: "active",
    note: "",
    items: [emptySupplierItem()],
  };
}

export function fromSupplier(row: SupplierRow): SupplierInput {
  return {
    name: row.name,
    tax_code: row.tax_code ?? "",
    phone: row.phone ?? "",
    email: row.email ?? "",
    address: row.address ?? "",
    contact_name: row.contact_name ?? "",
    supplier_group: row.supplier_group ?? "",
    payment_terms: row.payment_terms ?? "",
    credit_limit: row.credit_limit ?? 0,
    credit_days: row.credit_days ?? null,
    status: row.status,
    note: row.note ?? "",
    items: row.items.length
      ? row.items.map((item) => ({
          // PHẢI mang theo cặp mặt hàng gốc: form ghi kiểu replace-all, bỏ sót là mỗi lần mở NCC
          // ra sửa số điện thoại lại XOÁ SẠCH liên kết mặt hàng của cả bảng giá — im lặng, kéo
          // theo bảng so giá trống.
          hang_loai: item.hang_loai,
          hang_id: item.hang_id,
          item_name: item.item_name,
          unit: item.unit,
          unit_price: item.unit_price,
          vat_percent: item.vat_percent ?? 0,
          note: item.note ?? "",
        }))
      : [emptySupplierItem()],
  };
}

export function cleanSupplierItems(
  items: SupplierItemInput[] = [],
): SupplierItemInput[] {
  return items
    .map((item) => ({
      hang_loai: item.hang_loai ?? null,
      hang_id: item.hang_id ?? null,
      item_name: (item.item_name ?? "").trim(),
      unit: (item.unit ?? "").trim(),
      unit_price: Number(item.unit_price || 0),
      vat_percent: Number(item.vat_percent || 0),
      note: (item.note ?? "").trim() || null,
    }))
    .filter(
      (item) =>
        item.item_name ||
        item.unit ||
        item.unit_price > 0 ||
        item.vat_percent > 0 ||
        item.note,
    );
}

export function cleanSupplier(input: SupplierInput): SupplierInput {
  const trimOptional = (v?: string | null) => {
    const s = (v ?? "").trim();
    return s || null;
  };
  return {
    name: (input.name ?? "").trim(),
    tax_code: (input.tax_code ?? "").trim(),
    phone: (input.phone ?? "").trim(),
    email: (input.email ?? "").trim(),
    address: (input.address ?? "").trim(),
    contact_name: (input.contact_name ?? "").trim(),
    supplier_group: (input.supplier_group ?? "").trim(),
    payment_terms: trimOptional(input.payment_terms),
    credit_limit: Math.max(0, Math.round(Number(input.credit_limit) || 0)),
    // `?? null` chứ KHÔNG `|| null`: `credit_days = 0` là "trả ngay", một giá trị có thật.
    credit_days:
      input.credit_days == null
        ? null
        : Math.max(0, Math.round(Number(input.credit_days) || 0)),
    status: input.status ?? "active",
    note: trimOptional(input.note),
    items: cleanSupplierItems(input.items),
  };
}

export function getPOStatusLabel(status: string): {
  label: string;
  className: string;
} {
  switch (status) {
    case "draft":
      return { label: "Nháp", className: "purchase__status--draft" };
    case "pending":
      return { label: "Chờ duyệt", className: "purchase__status--pending" };
    case "approved":
      return { label: "Đã duyệt", className: "purchase__status--approved" };
    case "purchased":
      return { label: "Đã mua hàng", className: "purchase__status--purchased" };
    case "received":
      return { label: "Đã nhập kho", className: "purchase__status--received" };
    case "rejected":
      return { label: "Từ chối", className: "purchase__status--rejected" };
    case "cancelled":
      return { label: "Đã hủy", className: "purchase__status--cancelled" };
    case "pending_approval":
      return { label: "Chờ phê duyệt", className: "purchase__status--pending" };
    case "partially_received":
      return { label: "Đã nhập kho một phần", className: "purchase__status--received" };
    default:
      return { label: status, className: "purchase__status--draft" };
  }
}
