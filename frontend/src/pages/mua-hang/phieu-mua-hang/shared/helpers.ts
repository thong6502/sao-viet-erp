// Hàm thuần (không JSX, không state) của màn Mua hàng (tách từ pages/PurchaseRequestsPage.tsx).
// ⚠️ `lineTotal` / `lineDiscountAmount` / `lineVatAmount` là TÂM THUẾ của phân hệ — form nhập,
// bảng xem trước và tiền của từng đợt giao đều ăn ba hàm này. Đừng sửa một ký tự nào của phép
// tính; đổi cách làm tròn ở đây là lệch tiền thật trên phiếu mua và trên công nợ.
import type {
  DepartmentPurchaseRequestRow,
  PurchaseRequestLineInput,
  PurchaseRequestRow,
  SupplierRow,
} from "../../../../api/client";
import { SO_NCC_GOI_Y } from "./constants";
import type { ChaoGia, FormLine, FormState } from "./types";

export function emptyLine(): FormLine {
  return {
    item_name: "",
    unit: "",
    quantity: 0,
    expected_unit_price: 0,
    discount_percent: 0,
    vat_percent: 0,
    note: "",
    supplier_id: null,
  };
}

export function emptyRequest(): FormState {
  return {
    supplier_id: null,
    source_request_ids: [],
    content: "",
    needed_date: "",
    expected_receipt_date: "",
    note: null,
    lines: [emptyLine()],
  };
}

/** Nội dung để HIỆN. Phiếu lập trước 07/08/2026 chưa có ô gộp ⇒ nối lại hai ô cũ. */
export function noiDung(row: { content?: string | null; purpose?: string | null; note?: string | null }): string {
  const gop = (row.content ?? "").trim();
  if (gop) return gop;
  return [row.purpose, row.note].map((x) => (x ?? "").trim()).filter(Boolean).join(" — ");
}

export function todayInputValue(): string {
  const now = new Date();
  const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localNow.toISOString().slice(0, 10);
}

export function fromRequest(row: PurchaseRequestRow): FormState {
  return {
    supplier_id: row.supplier_id,
    source_request_ids: row.sources.map(
      (source) => source.department_request_id,
    ),
    content: noiDung(row),
    needed_date: row.needed_date ?? "",
    expected_receipt_date: row.expected_receipt_date ?? "",
    note: null,
    lines: row.lines.map((line) => ({
      item_name: line.item_name,
      unit: line.unit,
      quantity: line.quantity,
      expected_unit_price: line.expected_unit_price,
      discount_percent: line.discount_percent,
      vat_percent: line.vat_percent,
      note: line.note ?? "",
      // Phiếu đã tồn tại thì mọi dòng đều thuộc NCC của phiếu — không tách nữa.
      supplier_id: row.supplier_id,
      // Đọc lại liên kết YCMH + mặt hàng gốc — thiếu bước này thì lưu (kể cả chỉ để thêm ngày dự
      // kiến nhận hàng) sẽ ghi đè chúng thành rỗng, cắt đứt "hàng đang về" khỏi kế hoạch vật tư.
      department_request_line_id: line.department_request_line_id,
      hang_loai: line.hang_loai,
      hang_id: line.hang_id,
    })),
  };
}

export function lineTotal(line: PurchaseRequestLineInput): number {
  const base =
    (Number(line.quantity) || 0) * (Number(line.expected_unit_price) || 0);
  const discount = lineDiscountAmount(line);
  const taxable = Math.max(0, base - discount);
  return Math.round(taxable + lineVatAmount(line));
}

export function lineDiscountAmount(line: PurchaseRequestLineInput): number {
  const base =
    (Number(line.quantity) || 0) * (Number(line.expected_unit_price) || 0);
  return Math.round((base * (Number(line.discount_percent) || 0)) / 100);
}

export function lineVatAmount(line: PurchaseRequestLineInput): number {
  const base =
    (Number(line.quantity) || 0) * (Number(line.expected_unit_price) || 0);
  const taxable = Math.max(0, base - lineDiscountAmount(line));
  return Math.round((taxable * (Number(line.vat_percent) || 0)) / 100);
}

export function normalizeItemName(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

export function supplierItemForLine(
  supplier: SupplierRow | undefined,
  line: PurchaseRequestLineInput,
) {
  if (!supplier) return null;
  const name = normalizeItemName(line.item_name);
  return (
    supplier.items.find(
      (item) =>
        normalizeItemName(item.item_name) === name &&
        item.unit.trim().toLowerCase() === line.unit.trim().toLowerCase(),
    ) ??
    supplier.items.find((item) => normalizeItemName(item.item_name) === name) ??
    null
  );
}

/** Những NCC ĐANG HOẠT ĐỘNG bán mặt hàng này, xếp GIÁ TĂNG DẦN, lấy tối đa `SO_NCC_GOI_Y`.
 *
 * Xếp theo đơn giá CHƯA VAT vì đó là số đi vào dòng hàng. NCC có VAT khác nhau thì giá sau thuế
 * có thể đảo thứ tự — nên ô chọn hiện luôn cả VAT để nhìn là biết, không giấu.
 *
 * Không cần gọi API: danh sách NCC nạp cho màn này đã kèm bảng giá mặt hàng của từng người.
 */
export function chaoGiaChoMatHang(
  itemName: string,
  suppliers: SupplierRow[],
): ChaoGia[] {
  const ten = normalizeItemName(itemName);
  if (!ten) return [];
  const out: ChaoGia[] = [];
  for (const ncc of suppliers) {
    if (ncc.status !== "active") continue;
    const item = ncc.items.find(
      (i) => normalizeItemName(i.item_name) === ten && i.is_active !== false,
    );
    if (!item) continue;
    out.push({
      supplier_id: ncc.id,
      supplier_name: ncc.name,
      unit_price: item.unit_price,
      vat_percent: item.vat_percent ?? 0,
      unit: item.unit,
    });
  }
  out.sort((a, b) => a.unit_price - b.unit_price);
  return out.slice(0, SO_NCC_GOI_Y);
}

export function applySupplierPrices(
  lines: PurchaseRequestLineInput[],
  suppliers: SupplierRow[],
  supplierId: number | null,
): PurchaseRequestLineInput[] {
  const supplier = suppliers.find((row) => row.id === supplierId);
  return lines.map((line) => {
    const item = supplierItemForLine(supplier, line);
    if (!item) return line;
    return {
      ...line,
      unit: item.unit || line.unit,
      expected_unit_price: item.unit_price,
      vat_percent: item.vat_percent,
    };
  });
}

export function supplierQuotedTotal(
  supplier: SupplierRow,
  lines: PurchaseRequestLineInput[],
): number | null {
  let total = 0;
  let matched = 0;
  for (const line of lines) {
    const item = supplierItemForLine(supplier, line);
    if (!item) continue;
    matched += 1;
    total += (Number(line.quantity) || 0) * item.unit_price;
  }
  return matched === lines.length && matched > 0 ? total : null;
}

export function bestSupplierIdForLines(
  lines: PurchaseRequestLineInput[],
  suppliers: SupplierRow[],
): number | null {
  let best: { supplierId: number; total: number } | null = null;
  for (const supplier of suppliers) {
    const total = supplierQuotedTotal(supplier, lines);
    if (total == null) continue;
    if (!best || total < best.total) best = { supplierId: supplier.id, total };
  }
  return best?.supplierId ?? null;
}

/** Σ số đã giao của MỘT dòng đặt, cộng qua các đợt — bỏ qua đợt đang sửa (`boQua`) vì số của
 *  chính nó không tính vào "phần các đợt KHÁC đã lấy". Khớp `_clean_dot_lines` bên service. */
export function daGiaoKhac(
  row: PurchaseRequestRow,
  lineId: number,
  boQua?: number | null,
): number {
  let tong = 0;
  for (const dot of row.deliveries) {
    if (boQua != null && dot.id === boQua) continue;
    for (const dl of dot.lines) {
      if (dl.purchase_request_line_id === lineId) tong += dl.quantity;
    }
  }
  return tong;
}

/** Tiền của `qty` theo đơn giá/CK/VAT đã chốt trên phiếu.
 *
 * Đây là bản XEM TRƯỚC ở giao diện; con số thật do server tính (`gia_tri_dot_giao`) — hai bên phải
 * ra cùng một kết quả. Không có ô nhập tiền ở đợt giao (chủ chốt 07/08/2026): tiền suy thẳng từ số
 * lượng thực nhận, nên đợt giao không bao giờ lệch với đơn. */
export function tienTheoSoLuong(
  line: PurchaseRequestRow["lines"][number],
  qty: number,
): number {
  return lineTotal({
    item_name: line.item_name,
    unit: line.unit,
    quantity: qty,
    expected_unit_price: line.expected_unit_price,
    discount_percent: line.discount_percent,
    vat_percent: line.vat_percent,
  });
}

export function purchaseChildSummary(row: DepartmentPurchaseRequestRow): string {
  const dem = new Map<string, number>();
  for (const phieu of row.purchase_requests) {
    const nhom =
      phieu.status === "rejected"
        ? "cần sửa"
        : phieu.status === "draft"
          ? "đang lập"
          : phieu.status === "pending_approval"
            ? "chờ duyệt"
            : phieu.status === "received"
              ? "đã nhận"
              : phieu.status === "cancelled"
                ? "đã hủy"
                : "đang mua";
    dem.set(nhom, (dem.get(nhom) ?? 0) + 1);
  }
  const thuTu = ["cần sửa", "đang lập", "chờ duyệt", "đang mua", "đã nhận", "đã hủy"];
  return thuTu
    .filter((nhom) => dem.has(nhom))
    .map((nhom) => `${dem.get(nhom)} đơn ${nhom}`)
    .join(" · ");
}
