import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  assetUrl,
  type DepartmentPurchaseRequestRow,
  type DepartmentPurchaseRequestStatus,
  type PurchaseAttachmentRow,
  type PurchaseDeliveryRow,
  type PurchaseRequestInput,
  type PurchaseRequestLineInput,
  type PurchaseRequestRow,
  type PurchaseRequestStatus,
  type SupplierRow,
} from "../api/client";
import { useDebounced } from "../utils/useDebounced";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import type { NavigateFn } from "../components/AppShell";
import type { SeedLine } from "./KhoDeNghiPage";
import { CodeLink } from "../components/CodeLink";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DetailModal } from "../components/DetailModal";
import { EmptyRow } from "../components/EmptyState";
import { StatusHistoryTimeline } from "../components/StatusHistoryTimeline";
import { StatusTabs } from "../components/StatusTabs";
import { Icon } from "../components/Icons";
import { RowActionButton } from "../components/RowActionButton";
// `escapeHtml` nhập dưới tên `html` để không phải sửa ~30 chỗ gọi trong mẫu in. Bản chép tay cũ
// trong file này đã xoá — hai bản escape song song là kiểu lỗi chỉ lộ ra ở một ký tự hiếm.
import { escapeHtml as html, fmtDate, money } from "../utils/format";
import "./master-data.css";
// Hộp khai số thực nhận mượn bảng gọn `.pay-table` của màn Công nợ — cùng một loại bảng phụ trong
// hộp thoại, không dựng bộ lớp thứ hai cho y hệt một việc.
import "./payables.css";
import "./purchase.css";

const PAGE_SIZE = 20;
const SOURCE_PAGE_SIZE = 20;

const STATUS_META: Record<
  PurchaseRequestStatus,
  { label: string; tone: string }
> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Từ chối", tone: "rejected" },
  purchased: { label: "Đang mua", tone: "purchased" },
  // Bậc SUY RA từ đợt giao: có ≥1 đợt nhưng tổng thực nhận chưa đủ số đặt. Không ai gõ tay được
  // trạng thái này — nó đổi theo đợt giao, và phần hàng đã về đã đẻ ra công nợ.
  partially_received: { label: "Giao một phần", tone: "partial" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

/** Hai trạng thái GHI ĐƯỢC đợt giao — khớp `_TRANG_THAI_GHI_DOT` bên service. */
const GHI_DOT_DUOC: PurchaseRequestStatus[] = ["purchased", "partially_received"];

type StatusFilter = "all" | PurchaseRequestStatus;
type SourceStatusFilter = "all" | DepartmentPurchaseRequestStatus;
type DepositFilter = "all" | "none" | "unpaid" | "partial" | "enough";

/** Hai tab con của màn Mua hàng (chốt 08/08/2026).
 *
 * Trước đó hai bảng XẾP DỌC trong cùng một màn: đo thật ở 1440×900 (vùng nhìn 843px) thì dòng đầu
 * của bảng phiếu mua bắt đầu ở y≈812 — người dùng chỉ thấy 34% một dòng, và mỗi yêu cầu mới ở
 * bảng trên lại đẩy bảng dưới xuống thêm 68px (5 yêu cầu chờ là bảng phiếu biến mất hẳn).
 * Tách tab để mỗi bảng có nguyên khung nhìn. ĐỪNG gộp lại thành một trang cuộn dọc. */
type PurchaseTab = "yeu-cau" | "phieu";

const SOURCE_STATUS_META: Record<
  DepartmentPurchaseRequestStatus,
  { label: string; tone: string }
> = {
  open: { label: "Chờ Thu mua xử lý", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  in_purchase: { label: "Đang mua", tone: "pending" },
  done: { label: "Hoàn tất", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

/** Dòng hàng trong FORM — mang thêm NCC của riêng nó.
 *
 * Một phiếu mua là thoả thuận với MỘT nhà cung cấp, nhưng một yêu cầu thường chứa hàng của nhiều
 * nơi. Nên NCC gán ở DÒNG, rồi lúc gửi mới nhóm lại thành N phiếu. Ô "Nhà cung cấp" ở đầu phiếu
 * chỉ còn dùng cho chế độ SỬA (phiếu đã tồn tại thì nó vốn đã thuộc về một NCC). */
type FormLine = PurchaseRequestLineInput & {
  supplier_id?: number | null;
  /** Dòng YCMH đẻ ra dòng này — gửi lên để chi tiết yêu cầu hiện được tình trạng từng sản phẩm. */
  department_request_line_id?: number | null;
};

type FormState = Omit<PurchaseRequestInput, "lines"> & { lines: FormLine[] };

function emptyLine(): FormLine {
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

function emptyRequest(): FormState {
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
function noiDung(row: { content?: string | null; purpose?: string | null; note?: string | null }): string {
  const gop = (row.content ?? "").trim();
  if (gop) return gop;
  return [row.purpose, row.note].map((x) => (x ?? "").trim()).filter(Boolean).join(" — ");
}

function todayInputValue(): string {
  const now = new Date();
  const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localNow.toISOString().slice(0, 10);
}

function fromRequest(row: PurchaseRequestRow): FormState {
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
    })),
  };
}

function lineTotal(line: PurchaseRequestLineInput): number {
  const base =
    (Number(line.quantity) || 0) * (Number(line.expected_unit_price) || 0);
  const discount = lineDiscountAmount(line);
  const taxable = Math.max(0, base - discount);
  return Math.round(taxable + lineVatAmount(line));
}

function lineDiscountAmount(line: PurchaseRequestLineInput): number {
  const base =
    (Number(line.quantity) || 0) * (Number(line.expected_unit_price) || 0);
  return Math.round((base * (Number(line.discount_percent) || 0)) / 100);
}

function lineVatAmount(line: PurchaseRequestLineInput): number {
  const base =
    (Number(line.quantity) || 0) * (Number(line.expected_unit_price) || 0);
  const taxable = Math.max(0, base - lineDiscountAmount(line));
  return Math.round((taxable * (Number(line.vat_percent) || 0)) / 100);
}

function normalizeItemName(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function supplierItemForLine(
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

/** Số NCC hiện trong ô chọn của mỗi dòng. Đủ để so giá mà không biến ô chọn thành danh bạ. */
const SO_NCC_GOI_Y = 5;

export type ChaoGia = {
  supplier_id: number;
  supplier_name: string;
  unit_price: number;
  vat_percent: number;
  unit: string;
};

/** Những NCC ĐANG HOẠT ĐỘNG bán mặt hàng này, xếp GIÁ TĂNG DẦN, lấy tối đa `SO_NCC_GOI_Y`.
 *
 * Xếp theo đơn giá CHƯA VAT vì đó là số đi vào dòng hàng. NCC có VAT khác nhau thì giá sau thuế
 * có thể đảo thứ tự — nên ô chọn hiện luôn cả VAT để nhìn là biết, không giấu.
 *
 * Không cần gọi API: danh sách NCC nạp cho màn này đã kèm bảng giá mặt hàng của từng người.
 */
function chaoGiaChoMatHang(
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

/** Ô chọn nhà cung cấp cho MỘT dòng hàng — hiện tối đa 5 nơi bán, rẻ nhất lên trước, kèm giá.
 *
 * Chưa gõ tên vật tư thì chưa biết hỏi ai ⇒ ô khoá lại và nói rõ. Gõ tên mà không ai bán thì cũng
 * nói thẳng, không để ô rỗng im lặng rồi người dùng bấm Lưu mới biết. */
function LineSupplierPicker({
  line,
  suppliers,
  onPick,
}: {
  line: FormLine;
  suppliers: SupplierRow[];
  onPick: (chao: ChaoGia | null) => void;
}) {
  const chaoGia = chaoGiaChoMatHang(line.item_name, suppliers);
  const chuaGoTen = !normalizeItemName(line.item_name);

  if (chuaGoTen || chaoGia.length === 0) {
    return (
      <select className="input" disabled aria-label="Nhà cung cấp của dòng">
        <option>{chuaGoTen ? "Nhập vật tư trước" : "Chưa có NCC nào bán"}</option>
      </select>
    );
  }
  return (
    <select
      className="input"
      required
      aria-label="Nhà cung cấp của dòng"
      value={line.supplier_id ?? ""}
      onChange={(e) =>
        onPick(
          chaoGia.find((c) => c.supplier_id === Number(e.target.value)) ?? null,
        )
      }
    >
      <option value="">Chọn nhà cung cấp</option>
      {/* Nhãn "· rẻ nhất" đang TẮT (dòng comment bên dưới). Bật lại thì thêm `, i` vào tham số
          map — bỏ đi ở đây chỉ vì để lại là TypeScript báo "khai mà không dùng", chứ không phải
          tôi gỡ ý đó. Danh sách vẫn xếp giá tăng dần nên dòng đầu vẫn là rẻ nhất. */}
      {chaoGia.map((c) => (
        <option key={c.supplier_id} value={c.supplier_id}>
          {c.supplier_name} — {money(c.unit_price)}
          {c.vat_percent ? ` (VAT ${c.vat_percent}%)` : ""}
          {/* {i === 0 && chaoGia.length > 1 ? " · rẻ nhất" : ""} */}
        </option>
      ))}
    </select>
  );
}

function applySupplierPrices(
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

function supplierQuotedTotal(
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

function bestSupplierIdForLines(
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

function DepositCell({ row }: { row: PurchaseRequestRow }) {
  if ((row.deposit_expected ?? 0) <= 0) {
    return <span className="md-page__muted">-</span>;
  }
  const paid = row.coc_da_chi ?? 0;
  const expected = row.deposit_expected ?? 0;
  const tone = paid >= expected ? "ok" : paid > 0 ? "warn" : "empty";
  return (
    <div className={`purchase__deposit purchase__deposit--${tone}`}>
      <strong>{money(paid)}</strong>
      <span>/ {money(expected)}</span>
    </div>
  );
}

function printPurchaseRequest(row: PurchaseRequestRow): boolean {
  const win = window.open("", "_blank", "width=980,height=720");
  if (!win) return false;

  const sourceCodes = row.sources.length
    ? row.sources.map((source) => source.code).join(", ")
    : "Chưa gắn";
  const sourceDepartments = row.sources
    .map(
      (source) => source.requesting_department_name || source.requested_by_name,
    )
    .filter(Boolean)
    .join(", ");
  const status = STATUS_META[row.status]?.label ?? row.status;
  const totalDiscount = row.lines.reduce(
    (sum, line) => sum + line.discount_amount,
    0,
  );
  const totalVat = row.lines.reduce((sum, line) => sum + line.vat_amount, 0);
  const printDate = new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());

  const lines = row.lines
    .map(
      (line, index) => `
        <tr>
          <td class="center">${index + 1}</td>
          <td>
            <strong>${html(line.item_name)}</strong>
            ${line.note ? `<div class="muted">${html(line.note)}</div>` : ""}
          </td>
          <td class="center">${html(line.unit)}</td>
          <td class="num">${line.quantity.toLocaleString("vi-VN")}</td>
          <td class="num">${html(money(line.expected_unit_price))}</td>
          <td class="num">${line.discount_percent}%</td>
          <td class="num">${html(money(line.discount_amount))}</td>
          <td class="num">${line.vat_percent}%</td>
          <td class="num">${html(money(line.vat_amount))}</td>
          <td class="num strong">${html(money(line.line_total))}</td>
        </tr>
      `,
    )
    .join("");

  win.document.write(`<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>In đơn mua hàng ${html(row.code)}</title>
  <style>
    @page { size: A4; margin: 14mm; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: #111;
      font-family: Arial, "Helvetica Neue", sans-serif;
      font-size: 12px;
      line-height: 1.35;
    }
    .top {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 2px solid #111;
      padding-bottom: 10px;
      margin-bottom: 16px;
    }
    .company { font-weight: 700; text-transform: uppercase; }
    .muted { color: #666; font-size: 11px; margin-top: 2px; }
    .print-meta { text-align: right; color: #444; }
    h1 {
      margin: 8px 0 4px;
      text-align: center;
      font-size: 22px;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    .code {
      text-align: center;
      font-weight: 700;
      margin-bottom: 14px;
    }
    .status {
      display: inline-block;
      border: 1px solid #111;
      border-radius: 999px;
      padding: 2px 10px;
      font-size: 11px;
      text-transform: uppercase;
    }
    .info {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px 24px;
      margin-bottom: 14px;
    }
    .info div { border-bottom: 1px dotted #bbb; padding-bottom: 4px; }
    .label {
      display: block;
      color: #555;
      font-size: 10px;
      text-transform: uppercase;
      margin-bottom: 2px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }
    th, td {
      border: 1px solid #222;
      padding: 6px 5px;
      vertical-align: top;
    }
    th {
      background: #f1f1f1;
      text-align: center;
      font-size: 10px;
      text-transform: uppercase;
    }
    .center { text-align: center; }
    .num { text-align: right; white-space: nowrap; }
    .strong { font-weight: 700; }
    .summary {
      margin-left: auto;
      margin-top: 10px;
      width: 320px;
    }
    .summary div {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid #ddd;
      padding: 5px 0;
    }
    .summary .grand {
      border-bottom: 2px solid #111;
      font-size: 15px;
      font-weight: 700;
    }
    .note {
      margin-top: 14px;
      border: 1px solid #bbb;
      min-height: 42px;
      padding: 8px;
    }
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
  </style>
</head>
<body>
  <div class="top">
    <div>
      <div class="company">Sao Việt Nhật ERP</div>
      <div class="muted">Phiếu in từ phân hệ Thu mua</div>
    </div>
    <div class="print-meta">
      <div>Ngày in: ${html(printDate)}</div>
      <div class="status">${html(status)}</div>
    </div>
  </div>

  <h1>Đơn mua hàng</h1>
  <div class="code">Mã đơn: ${html(row.code)}</div>

  <section class="info">
    <div><span class="label">Nhà cung cấp</span>${html(row.supplier_name || "Chưa chọn")}</div>
    <div><span class="label">Ngày cần hàng</span>${html(fmtDate(row.needed_date))}</div>
    <div><span class="label">Ngày dự kiến nhận hàng</span>${html(fmtDate(row.expected_receipt_date))}</div>
    <div><span class="label">Phiếu yêu cầu mua hàng</span>${html(sourceCodes)}</div>
    <div><span class="label">Bộ phận/người yêu cầu</span>${html(sourceDepartments || "Nội bộ")}</div>
    <div><span class="label">Người lập</span>${html(row.created_by_name || "—")}</div>
    <div><span class="label">Người duyệt</span>${html(row.approved_by_name || "Chưa duyệt")}</div>
    <div><span class="label">Gửi duyệt</span>${html(fmtDate(row.submitted_at))}</div>
    <div><span class="label">Duyệt lúc</span>${html(fmtDate(row.approved_at))}</div>
    <div style="grid-column: 1 / -1;"><span class="label">Nội dung / mục đích</span>${html(row.content || row.purpose || "—")}</div>
  </section>

  <table>
    <thead>
      <tr>
        <th>STT</th>
        <th>Vật tư / hàng hóa</th>
        <th>ĐVT</th>
        <th>Số lượng</th>
        <th>Đơn giá</th>
        <th>Giảm %</th>
        <th>Tiền giảm</th>
        <th>VAT %</th>
        <th>Tiền VAT</th>
        <th>Thành tiền</th>
      </tr>
    </thead>
    <tbody>${lines}</tbody>
  </table>

  <section class="summary">
    <div><span>Tổng tiền giảm</span><strong>${html(money(totalDiscount))}</strong></div>
    <div><span>Tổng thuế GTGT</span><strong>${html(money(totalVat))}</strong></div>
    <div class="grand"><span>Tổng dự kiến</span><strong>${html(money(row.total_estimate))}</strong></div>
  </section>

  ${row.reject_reason ? `<section class="note"><span class="label">Lý do từ chối / huỷ</span>${html(row.reject_reason)}</section>` : ""}

</body>
</html>`);
  win.document.close();
  win.focus();
  window.setTimeout(() => win.print(), 250);
  return true;
}

export function PurchaseRequestsPage({
  navigate,
  eventTick = 0,
  focusRequestCode = null,
}: {
  navigate: NavigateFn;
  eventTick?: number;
  /** Liên thông từ màn khác (Công nợ / Kế toán thu mua / Phiếu chi): mã tài liệu cần soi.
   *  Mã `PMH-…` = phiếu mua → tab "phieu"; mã `YCMH-…` = yêu cầu → tab "yeu-cau".
   *  Xem effect "BẪY LIÊN THÔNG" bên dưới trước khi đụng vào. */
  focusRequestCode?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("thu_mua", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  // Đợt giao ↔ phiếu nhập kho = CÙNG sự kiện hàng về: bấm "Nhập kho" ở một đợt → nhảy sang màn
  // Yêu cầu kho, mở sẵn form NHẬP điền theo hàng đã nhận. Ghi chú trỏ về mã đơn mua + số đợt.
  //
  // Ô MẶT HÀNG để TRỐNG có chủ ý: từ Đợt 3, kho chỉ nhận hàng CÓ trong danh mục gốc, mà dòng đơn
  // mua chỉ có tên chữ (`item_name`) — ghép theo chuỗi chính là cái sai đang đi chữa ("Couche 150"
  // ≠ "Couché 150 79×109"). Tên hàng đẩy vào ghi chú để người lập đối chiếu rồi tự chọn đúng món.
  const nhapKhoTuDot = (row: PurchaseRequestRow, dot: PurchaseDeliveryRow) => {
    // Đơn giá lấy từ ĐÚNG dòng đơn mua đẻ ra dòng giao này (khớp qua purchase_request_line_id).
    const giaTheoDong = new Map(row.lines.map((pl) => [pl.id, pl.expected_unit_price]));
    const seed: SeedLine[] = dot.lines.map((dl) => ({
      hang_loai: null,
      hang_id: null,
      hang_ma: null,
      hang_ten: null,
      dvt: dl.unit,
      he_so_ve_goc: null,
      sl_de_nghi: dl.quantity,
      don_gia: giaTheoDong.get(dl.purchase_request_line_id) ?? null,
      ghi_chu: [dl.item_name, dl.note].filter(Boolean).join(" — ") || null,
    }));
    navigate("kho-main", {
      khoNhapSeed: {
        seed,
        ngay_can: (dot.delivery_date || "").slice(0, 10),   // ngày nhập = ngày giao của đợt
        ghi_chu: `Nhập từ đơn mua ${row.code} — đợt ${dot.seq_no}`,
        locked: true,   // số liệu từ đơn mua → khoá, không cho sửa dòng
      },
    });
  };
  const canUpdate = can("thu_mua", "update");
  const canApprovePurchase = can("thu_mua", "approve");
  // KHÔNG còn `canApprove` ở màn này: duyệt đơn mua đã chuyển sang Kế toán thu mua (04/08/2026).
  //
  // ⚠️ Hộp "Lý do từ chối" (`reasonModal.kind === "reject"`) vẫn còn trong file nhưng KHÔNG CÒN AI
  // BẤM — chỉ nhánh `cancel` còn chạy. Giữ tạm để chép sang màn Đơn mua hàng; chép xong thì dọn,
  // đừng để nó nằm lại làm người đọc sau tưởng màn này vẫn từ chối được.
  // Tab đang mở. CỐ Ý mở màn ở "yeu-cau" và CỐ Ý không nhớ qua lần vào (không localStorage,
  // không nâng lên URL): hai người mở cùng màn phải thấy giống nhau, và việc của Thu mua luôn
  // bắt đầu từ hộp yêu cầu. Đừng "cải tiến" thành ghi nhớ lựa chọn.
  const [tab, setTab] = useState<PurchaseTab>("yeu-cau");
  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [supplierFilter, setSupplierFilter] = useState<number | "all">("all");
  const [depositFilter, setDepositFilter] = useState<DepositFilter>("all");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [neededFrom, setNeededFrom] = useState("");
  const [neededTo, setNeededTo] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [sourceRows, setSourceRows] = useState<DepartmentPurchaseRequestRow[]>(
    [],
  );
  const [sourceTotal, setSourceTotal] = useState(0);
  // Số đếm trên TAB — CỐ Ý KHÁC số dòng của bảng bên trong, đừng "sửa cho khớp".
  //
  // Bảng yêu cầu mặc định lọc "Tất cả" (chủ chốt 08/08/2026) nên `sourceTotal` gồm cả phiếu đã
  // Hoàn tất / Đã huỷ. Con số trên tab là TÍN HIỆU CÓ VIỆC, nên nó chỉ đếm yêu cầu đang `open`
  // (chờ Thu mua xử lý). `somNhat` = ngày cần hàng sớm nhất trong nhóm đó — dùng cho dải nhắc và
  // cho tone đỏ của tab.
  const [choMua, setChoMua] = useState<{ soLuong: number; somNhat: string | null }>({
    soLuong: 0,
    somNhat: null,
  });
  const [sourceQ, setSourceQ] = useState("");
  const [sourceStatus, setSourceStatus] = useState<SourceStatusFilter>("all");
  const [sourceLoading, setSourceLoading] = useState(true);
  // Ô nhập vẫn bám state gốc (gõ tới đâu hiện tới đó); chỉ lời gọi máy chủ đọc bản đã
  // chậm 300ms — xem `utils/useDebounced`.
  const qDebounced = useDebounced(q);
  const sourceQDebounced = useDebounced(sourceQ);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [sourcePage, setSourcePage] = useState(1);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Lỗi TẢI DANH SÁCH — tách hẳn khỏi `error` (lỗi THAO TÁC).
   *
   *  Vì sao phải hai ô nhớ riêng: `error` bị hàng chục handler thao tác ghi vào (huỷ phiếu, ghi
   *  đợt giao, gán hoá đơn, thậm chí trình duyệt chặn cửa sổ in). Nếu ô rỗng của bảng đọc chung
   *  `error` thì chỉ cần bấm "In phiếu" mà bị chặn pop-up là CẢ BẢNG biến mất, thay bằng "Không
   *  đọc được dữ liệu" — dữ liệu còn nguyên trên máy chủ, chỉ là bảng tự xoá mình vì một lỗi in.
   *  Ô này CHỈ được ghi trong `catch` của hàm tải danh sách. */
  const [listError, setListError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<PurchaseRequestRow | null>(null);
  const [form, setForm] = useState<FormState>(emptyRequest());
  const [formError, setFormError] = useState<string | null>(null);
  // Gom dòng theo NCC để nói trước "sẽ tạo mấy phiếu". Giữ THỨ TỰ NCC xuất hiện lần đầu — khớp
  // đúng cách backend nhóm, để bảng xem trước không nói một đằng, phiếu ra một nẻo.
  const phieuSeTao = useMemo(() => {
    const theoNcc = new Map<number, { ten: string; soDong: number; tien: number }>();
    for (const line of form.lines) {
      if (!line.supplier_id) continue;
      const cu = theoNcc.get(line.supplier_id) ?? {
        ten:
          suppliers.find((s) => s.id === line.supplier_id)?.name ??
          `NCC #${line.supplier_id}`,
        soDong: 0,
        tien: 0,
      };
      cu.soDong += 1;
      cu.tien += lineTotal(line);
      theoNcc.set(line.supplier_id, cu);
    }
    return [...theoNcc.values()];
  }, [form.lines, suppliers]);
  const minPurchaseDate = useMemo(() => todayInputValue(), []);
  // Ngày dự kiến nhận chỉ bị chặn bởi HÔM NAY, KHÔNG bởi ngày cần hàng (chủ 03/08/2026):
  // nhận hàng sớm hơn ngày cần là trường hợp mong muốn, chặn nó là cấm đúng cái tốt.
  const expectedReceiptMinDate = minPurchaseDate;
  const [deleting, setDeleting] = useState<PurchaseRequestRow | null>(null);
  // Dùng CHUNG một hộp "nhập lý do" cho cả huỷ / từ chối / lùi đã nhận — không dựng hộp thứ ba.
  const [reasonModal, setReasonModal] = useState<null | {
    kind: "cancel" | "reject" | "undo_received";
    row: PurchaseRequestRow;
    reason: string;
    error: string | null;
  }>(null);
  // Hộp khai SỐ THỰC NHẬN: mở khi bấm "Đã nhận" (mode `receive`) hoặc khi sửa lại sau (`edit`).
  const [receiveModal, setReceiveModal] = useState<null | {
    row: PurchaseRequestRow;
    mode: "receive" | "edit";
  }>(null);
  // --- Đợt giao: bốn hộp thoại, mỗi hộp một việc ---
  // `delivery: null` = ghi đợt MỚI, khác null = sửa đợt đó.
  const [deliveryModal, setDeliveryModal] = useState<null | {
    row: PurchaseRequestRow;
    delivery: PurchaseDeliveryRow | null;
  }>(null);
  const [invoiceModal, setInvoiceModal] = useState<PurchaseRequestRow | null>(
    null,
  );
  const [deletingDelivery, setDeletingDelivery] = useState<null | {
    row: PurchaseRequestRow;
    delivery: PurchaseDeliveryRow;
  }>(null);
  // "Đóng đơn (không giao nữa)" — cắt phần hàng chưa về ra khỏi công nợ nên BẮT lý do.
  const [closeModal, setCloseModal] = useState<null | {
    row: PurchaseRequestRow;
    reason: string;
    error: string | null;
  }>(null);

  const loadSuppliers = useCallback(() => {
    if (!token) return;
    api.suppliers
      .list(token, { status: "active", sort: "name", page: 1, size: 200 })
      .then((res) => setSuppliers(res.items))
      .catch(() => setSuppliers([]));
  }, [token]);

  /** Đếm yêu cầu ĐANG CHỜ MUA + ngày cần sớm nhất của nhóm đó.
   *
   * Phải hỏi riêng chứ không suy từ `sourceRows`: bảng đang lọc "Tất cả" và chỉ giữ 1 trang, nên
   * đếm tại chỗ sẽ ra số của trang hiện tại. `size: 1` + `sort: needed_date` là đủ: `total` cho số
   * lượng, dòng đầu cho ngày sớm nhất — không kéo cả danh sách về chỉ để lấy hai con số. */
  const loadChoMua = useCallback(() => {
    if (!token) return;
    api.departmentPurchaseRequests
      .list(token, { status: "open", sort: "needed_date", page: 1, size: 1 })
      .then((res) =>
        setChoMua({
          soLuong: res.total,
          somNhat: res.items[0]?.needed_date ?? null,
        }),
      )
      .catch(() => setChoMua({ soLuong: 0, somNhat: null }));
  }, [token]);

  const loadSources = useCallback(() => {
    if (!token) return;
    // Bám theo mọi lần nạp lại danh sách yêu cầu (mọi thao tác chạm YCMH đều gọi `loadSources`)
    // ⇒ số trên tab và dải nhắc không bao giờ đứng hình sau khi lập phiếu / huỷ / đóng đơn.
    loadChoMua();
    setSourceLoading(true);
    setSourceError(null);
    api.departmentPurchaseRequests
      .list(token, {
        q: sourceQDebounced.trim() || undefined,
        status: sourceStatus === "all" ? null : sourceStatus,
        sort: "-created_at",
        page: sourcePage,
        size: SOURCE_PAGE_SIZE,
      })
      .then((res) => {
        setSourceRows(res.items);
        setSourceTotal(res.total);
      })
      .catch(() => {
        setSourceRows([]);
        setSourceTotal(0);
        setSourceError("Không tải được danh sách yêu cầu mua hàng.");
      })
      .finally(() => setSourceLoading(false));
  }, [token, loadChoMua, sourceQDebounced, sourceStatus, sourcePage]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setListError(null);
    api.purchaseRequests
      .list(token, {
        q: qDebounced.trim() || undefined,
        status: status === "all" ? null : status,
        supplier_id: supplierFilter === "all" ? null : supplierFilter,
        deposit_status: depositFilter === "all" ? null : depositFilter,
        created_from: createdFrom || null,
        created_to: createdTo || null,
        needed_from: neededFrom || null,
        needed_to: neededTo || null,
        sort: "-created_at",
        page,
        size: PAGE_SIZE,
      })
      .then((res) => {
        setRows(res.items);
        setTotal(res.total);
        setSelectedId((current) =>
          current != null && res.items.some((row) => row.id === current)
            ? current
            : null,
        );
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setListError("Không tải được danh sách đơn mua hàng.");
      })
      .finally(() => setLoading(false));
  }, [
    token,
    qDebounced,
    status,
    supplierFilter,
    depositFilter,
    createdFrom,
    createdTo,
    neededFrom,
    neededTo,
    page,
  ]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (eventTick <= 0) return;
    loadSuppliers();
    loadSources();
    load();
  }, [eventTick, loadSuppliers, loadSources, load]);

  // ⚠️ ĐƯỜNG PHÒNG THỦ — HIỆN CHƯA CÓ AI GỌI, ĐỪNG GỠ.
  //
  // Tình trạng thật (kiểm 08/08/2026): KHÔNG màn nào đang `navigate("mua-hang", …)` kèm mã. Các
  // màn Kế toán / Công nợ bấm mã thì nhảy sang `ke-toan-don-mua-hang` hoặc `yeu-cau-mua-hang`,
  // không vào đây. Nên đoạn dưới CHƯA chạy lần nào.
  //
  // Vì sao vẫn giữ: từ 08/08/2026 màn này mở mặc định ở tab "Yêu cầu chờ xử lý". Ngày nào có
  // người nối một đường nhảy vào đây kèm mã phiếu mà thiếu đoạn này, người dùng sẽ rơi vào tab
  // yêu cầu và KHÔNG THẤY GÌ — trông y hệt như phiếu đã bị xoá. Mã yêu cầu là `YCMH-…`, mã phiếu
  // mua là `PMH-…` (xem `purchase_service.py`), nên phân nhánh theo tiền tố.
  useEffect(() => {
    const code = (focusRequestCode ?? "").trim();
    if (!code) return;
    if (code.toUpperCase().startsWith("YCMH")) {
      setSourceQ(code);
      setSourceStatus("all");
      setSourcePage(1);
      setTab("yeu-cau");
    } else {
      setQ(code);
      setStatus("all");
      setPage(1);
      setTab("phieu");
    }
  }, [focusRequestCode]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const sourceTotalPages = Math.max(
    1,
    Math.ceil(sourceTotal / SOURCE_PAGE_SIZE),
  );
  // CÓ YÊU CẦU QUÁ HẠN chưa? — điều kiện DUY NHẤT bật tone đỏ ở tab và bật dải nhắc ở tab phiếu.
  // Ngày thường (còn hạn) thì không tô đỏ, không render dải nhắc: không tốn một pixel nào.
  // `minPurchaseDate` chính là HÔM NAY dạng yyyy-mm-dd (memo 1 lần) — dùng lại để khỏi có hai
  // cách tính "hôm nay" trong cùng một file.
  const coYcQuaHan =
    choMua.somNhat !== null && choMua.somNhat < minPurchaseDate;
  // Chỉ thay dòng trong danh sách, KHÔNG đụng selectedId: các nút thao tác nằm ở
  // bảng, chọn dòng ở đây sẽ tự bung popup chi tiết. Popup đang mở thì `selected`
  // tự lấy lại dòng mới từ `rows`.
  function updateRow(next: PurchaseRequestRow) {
    setRows((current) =>
      current.map((row) => (row.id === next.id ? next : row)),
    );
  }

  function openCreatePurchaseRequest(pickedSource: DepartmentPurchaseRequestRow) {
    if (pickedSource.status !== "open") {
      setError("Chỉ lập đơn mua hàng từ yêu cầu đang chờ Thu mua xử lý.");
      return;
    }
    const source = pickedSource;
    const lines = source.lines.map((line) => ({
      item_name: line.item_name,
      unit: line.unit,
      quantity: line.quantity,
      expected_unit_price: line.expected_unit_price,
      discount_percent: 0,
      vat_percent: 0,
      note: line.note ?? `Từ ${source.code}`,
      // Nối DÒNG ↔ DÒNG. Form dựng từ chính các dòng của yêu cầu nên id có sẵn ngay đây; không
      // gửi lên thì chi tiết yêu cầu không hiện được tình trạng từng sản phẩm, mà ghép bù theo
      // tên hàng thì trượt (thu mua sửa được tên cho khớp danh mục NCC).
      department_request_line_id: line.id,
    }));
    // Máy gán sẵn NCC RẺ NHẤT cho TỪNG DÒNG (không phải một NCC cho cả phiếu): phần lớn dòng chỉ
    // có một nơi bán nên tự khớp, người thu mua chỉ phải xử lý mấy chỗ có nhiều lựa chọn.
    // Dòng nào chưa ai bán thì để trống — ô chọn sẽ nói rõ, không im lặng.
    const daGan: FormLine[] = lines.map((line) => {
      const re = chaoGiaChoMatHang(line.item_name, suppliers)[0];
      if (!re) return { ...line, supplier_id: null };
      return {
        ...line,
        supplier_id: re.supplier_id,
        unit: line.unit || re.unit,
        expected_unit_price: re.unit_price,
        vat_percent: re.vat_percent,
      };
    });
    setEditing(null);
    setForm({
      supplier_id: null,
      source_request_ids: [source.id],
      content: source.content ?? source.purpose ?? "",
      needed_date: source.needed_date ?? "",
      expected_receipt_date: "",
      note: null,
      lines: daGan.length ? daGan : [emptyLine()],
    });
    setFormError(null);
    setMode("create");
  }

  function openEdit(row: PurchaseRequestRow) {
    setEditing(row);
    setForm(fromRequest(row));
    setFormError(null);
    setMode("edit");
  }

  function cleanRequest(input: FormState): FormState {
    const trimOptional = (v?: string | null) => {
      const s = (v ?? "").trim();
      return s || null;
    };
    return {
      supplier_id: input.supplier_id ?? null,
      source_request_ids: input.source_request_ids
        .map((id) => Number(id))
        .filter((id) => Number.isFinite(id) && id > 0),
      content: (input.content ?? "").trim(),
      needed_date: (input.needed_date ?? "").trim(),
      expected_receipt_date: trimOptional(input.expected_receipt_date),
      note: null,
      lines: input.lines.map((line) => ({
        item_name: (line.item_name ?? "").trim(),
        unit: (line.unit ?? "").trim(),
        quantity: Number(line.quantity),
        expected_unit_price: Math.round(Number(line.expected_unit_price) || 0),
        discount_percent: Number(line.discount_percent) || 0,
        vat_percent: Number(line.vat_percent) || 0,
        note: trimOptional(line.note),
        supplier_id: line.supplier_id ?? null,
        department_request_line_id: line.department_request_line_id ?? null,
      })),
    };
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    const payload = cleanRequest(form);
    // Chế độ TẠO: NCC gán ở từng DÒNG (kiểm ở dưới), không có ô NCC ở đầu phiếu.
    // Chế độ SỬA: phiếu đã thuộc về một NCC, giữ nguyên ô đầu phiếu.
    const missingHeader = [
      mode === "edit" && !payload.supplier_id ? "Nhà cung cấp" : "",
      !payload.needed_date ? "Ngày cần hàng" : "",
      !payload.content ? "Nội dung / mục đích" : "",
    ].filter(Boolean);
    if (missingHeader.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missingHeader.join(", ")}.`);
      return;
    }
    if (payload.needed_date && payload.needed_date < minPurchaseDate) {
      setFormError("Ngày cần hàng không được nhỏ hơn hôm nay.");
      return;
    }
    if (
      payload.expected_receipt_date &&
      payload.expected_receipt_date < minPurchaseDate
    ) {
      setFormError("Ngày dự kiến nhận hàng không được nhỏ hơn hôm nay.");
      return;
    }
    if (payload.source_request_ids.length !== 1) {
      setFormError("Mỗi đơn mua hàng chỉ được lập từ 1 yêu cầu mua hàng.");
      return;
    }
    if (
      !payload.lines.length ||
      payload.lines.some((line) => !line.item_name || !line.unit)
    ) {
      setFormError(
        "Mỗi phiếu cần ít nhất một dòng hàng; tên vật tư và đơn vị tính không được trống.",
      );
      return;
    }
    if (
      payload.lines.some(
        (line) => line.quantity <= 0 || line.expected_unit_price <= 0,
      )
    ) {
      setFormError("Số lượng và đơn giá dự kiến phải lớn hơn 0.");
      return;
    }
    if (
      payload.lines.some(
        (line) =>
          line.discount_percent < 0 ||
          line.discount_percent > 100 ||
          line.vat_percent < 0 ||
          line.vat_percent > 100,
      )
    ) {
      setFormError(
        "Giảm giá (%) và Thuế GTGT (%) phải trong khoảng 0 đến 100.",
      );
      return;
    }
    // Mỗi dòng phải biết mua của ai — không thì backend không nhóm được thành phiếu.
    if (mode !== "edit") {
      const chuaGan = payload.lines.filter((line) => !line.supplier_id);
      if (chuaGan.length > 0) {
        setFormError(
          `Chưa chọn nhà cung cấp cho: ${chuaGan
            .map((line) => line.item_name || "(dòng trống)")
            .join(", ")}.`,
        );
        return;
      }
    }
    setSaving(true);
    setFormError(null);
    try {
      if (mode === "edit" && editing) {
        const saved = await api.purchaseRequests.update(token, editing.id, {
          ...payload,
          lines: payload.lines.map(({ supplier_id: _bo, ...line }) => line),
        });
        updateRow(saved);
      } else {
        // Tách phiếu theo NCC trong MỘT lời gọi — gọi `create` nhiều lần sẽ bị chặn từ lần thứ
        // hai vì phiếu đầu đã giữ chỗ yêu cầu nguồn.
        const { items } = await api.purchaseRequests.createBatch(token, {
          source_request_ids: payload.source_request_ids,
          content: payload.content,
          needed_date: payload.needed_date,
          expected_receipt_date: payload.expected_receipt_date,
          note: payload.note,
          lines: payload.lines.map((line) => ({
            item_name: line.item_name,
            unit: line.unit,
            quantity: line.quantity,
            expected_unit_price: line.expected_unit_price,
            discount_percent: line.discount_percent,
            vat_percent: line.vat_percent,
            note: line.note,
            supplier_id: line.supplier_id as number,
            department_request_line_id: line.department_request_line_id,
          })),
        });
        setRows((current) => [...items, ...current]);
        setTotal((t) => t + items.length);
        // ⚠️ BẪY THỨ HAI — ĐỪNG GỠ. Nút "Tạo phiếu" nằm ở tab YÊU CẦU; lưu xong mà đứng nguyên
        // tại đó thì người dùng không thấy phiếu vừa lập (nó nằm ở tab kia), tưởng bấm hụt và bấm
        // lại — lần hai bị server chặn vì yêu cầu nguồn đã bị giữ chỗ. Kể cả đường tách nhiều
        // phiếu theo NCC cũng đi qua đây, nên một chỗ này là đủ cho cả hai.
        setTab("phieu");
      }
      setMode(null);
      loadSuppliers();
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError("Không lưu được đơn mua hàng.");
    } finally {
      setSaving(false);
    }
  }

  async function runAction(
    row: PurchaseRequestRow,
    key: string,
    fn: () => Promise<PurchaseRequestRow>,
  ) {
    if (!token) return;
    setActionBusy(`${key}:${row.id}`);
    setError(null);
    try {
      updateRow(await fn());
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không thực hiện được thao tác.");
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmDelete() {
    if (!token || !deleting) return;
    setActionBusy(`delete:${deleting.id}`);
    try {
      await api.purchaseRequests.remove(token, deleting.id);
      setRows((current) => current.filter((row) => row.id !== deleting.id));
      setTotal((t) => Math.max(0, t - 1));
      setSelectedId(null);
      setDeleting(null);
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Không xóa được phiếu.");
      setDeleting(null);
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmReason() {
    if (!token || !reasonModal) return;
    const { row, kind, reason } = reasonModal;
    if (kind === "reject" && !reason.trim()) {
      setReasonModal({ ...reasonModal, error: "Vui lòng nhập lý do từ chối." });
      return;
    }
    // Lùi "Đã nhận hàng" XOÁ một món nợ khỏi màn Kế toán ⇒ bắt buộc ghi lý do, để nhật ký còn truy
    // được. Server cũng chặn lý do rỗng; đây chỉ là chặn sớm cho đỡ một vòng gọi.
    if (kind === "undo_received" && !reason.trim()) {
      setReasonModal({ ...reasonModal, error: "Vui lòng nhập lý do lùi trạng thái." });
      return;
    }
    setActionBusy(`${kind}:${row.id}`);
    setReasonModal({ ...reasonModal, error: null });
    try {
      const next =
        kind === "reject"
          ? await api.purchaseRequests.reject(token, row.id, reason.trim())
          : kind === "undo_received"
            ? await api.purchaseRequests.undoReceived(token, row.id, reason.trim())
            : await api.purchaseRequests.cancel(token, row.id, reason || null);
      updateRow(next);
      setReasonModal(null);
      loadSources();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Không thực hiện được thao tác.";
      setReasonModal((current) =>
        current ? { ...current, error: message } : current,
      );
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmXoaDot() {
    if (!token || !deletingDelivery) return;
    const { row, delivery } = deletingDelivery;
    setActionBusy(`del-dot:${delivery.id}`);
    setError(null);
    try {
      updateRow(
        await api.purchaseRequests.deleteDelivery(token, row.id, delivery.id),
      );
      setDeletingDelivery(null);
      loadSources();
    } catch (err) {
      // Ca hay gặp: đợt đã có phiếu chi gắn vào ⇒ server chặn. Câu báo của server nói rõ phiếu
      // nào, nên đừng nuốt nó bằng câu chung chung.
      setError(err instanceof ApiError ? err.message : "Không xóa được đợt giao.");
      setDeletingDelivery(null);
    } finally {
      setActionBusy(null);
    }
  }

  async function confirmDongDon() {
    if (!token || !closeModal) return;
    const { row, reason } = closeModal;
    if (!reason.trim()) {
      setCloseModal({ ...closeModal, error: "Vui lòng nhập lý do đóng đơn." });
      return;
    }
    setActionBusy(`close:${row.id}`);
    setCloseModal({ ...closeModal, error: null });
    try {
      updateRow(await api.purchaseRequests.close(token, row.id, reason.trim()));
      setCloseModal(null);
      loadSources();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Không đóng được đơn.";
      setCloseModal((current) =>
        current ? { ...current, error: message } : current,
      );
    } finally {
      setActionBusy(null);
    }
  }

  function setLine(index: number, patch: Partial<FormLine>) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, i) =>
        i === index ? { ...line, ...patch } : line,
      ),
    }));
  }

  function openPrint(row: PurchaseRequestRow) {
    if (!printPurchaseRequest(row)) {
      setError(
        "Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.",
      );
    }
  }

  function actionButtons(row: PurchaseRequestRow, dense = false) {
    const busy = (key: string) => actionBusy === `${key}:${row.id}`;
    const canEdit =
      canUpdate && (row.status === "draft" || row.status === "rejected");
    return (
      <div
        className={
          dense
            ? "purchase__actions purchase__actions--dense"
            : "purchase__actions"
        }
      >
        {dense && (
          <RowActionButton
            dense
            label="Xem chi tiết"
            icon="eye"
            onClick={() => setSelectedId(row.id)}
          />
        )}
        {dense && (
          <RowActionButton
            dense
            label="In phiếu"
            icon="printer"
            onClick={() => openPrint(row)}
          />
        )}
        {canEdit && (
          <RowActionButton
            dense={dense}
            label="Sửa"
            icon="pencil"
            onClick={() => openEdit(row)}
          />
        )}
        {canUpdate && (row.status === "draft" || row.status === "rejected") && (
          <RowActionButton
            dense={dense}
            label="Gửi duyệt"
            icon="send"
            loading={busy("submit")}
            onClick={() =>
              runAction(row, "submit", () =>
                api.purchaseRequests.submit(token!, row.id),
              )
            }
          />
        )}
        {/* KHÔNG có nút Duyệt / Từ chối ở màn Mua hàng (chủ 04/08/2026: "phải duyệt ở phần kế
            toán chứ"). Duyệt đơn mua là quyết định CHI TIỀN — nó thuộc về giám đốc / người được
            trao quyền, và nay nằm ở màn Kế toán thu mua → Đơn mua hàng.
            Thu mua ở đây chỉ: Xem · In · Sửa · Gửi duyệt · Huỷ · Xoá. */}
        {canUpdate && row.status === "approved" && (
          <RowActionButton
            dense={dense}
            label="Đang mua"
            icon="bag"
            loading={busy("purchased")}
            onClick={() =>
              runAction(row, "purchased", () =>
                api.purchaseRequests.markPurchased(token!, row.id),
              )
            }
          />
        )}
        {/* GHI ĐỢT GIAO — đường CHÍNH để hàng về vào hệ từ 06/08/2026. Hàng về tới đâu nợ tới đó;
            giao đủ thì phiếu tự lên "Đã nhận", không ai phải bấm. */}
        {canUpdate && GHI_DOT_DUOC.includes(row.status) && (
          <RowActionButton
            dense={dense}
            label="Ghi đợt giao"
            icon="truck"
            onClick={() => setDeliveryModal({ row, delivery: null })}
          />
        )}
        {/* ĐƯỜNG CŨ, chỉ còn cho đơn KHÔNG theo dõi theo đợt (giao một lần, không ai muốn khai
            đợt). Đơn đã có đợt giao thì trạng thái là số SUY RA — server chặn gán tay, nên đừng
            bày nút ra rồi để người dùng bấm vào tường. */}
        {canUpdate &&
          row.status === "purchased" &&
          row.deliveries.length === 0 && (
            <RowActionButton
              dense={dense}
              label="Đã nhận (giao một lần)"
              icon="packageCheck"
              onClick={() => setReceiveModal({ row, mode: "receive" })}
            />
          )}
        {/* Sửa số thực nhận: cũng chỉ cho đơn KHÔNG theo đợt — đơn theo đợt thì sửa ở đúng đợt
            giao đó, sửa ở đây sẽ bị nhánh dẫn xuất ghi đè trong im lặng (server chặn). */}
        {canUpdate &&
          canApprovePurchase &&
          row.status === "received" &&
          row.deliveries.length === 0 && (
            <RowActionButton
              dense={dense}
              label="Sửa số nhận"
              icon="pencil"
              onClick={() => setReceiveModal({ row, mode: "edit" })}
            />
          )}
        {canUpdate && canApprovePurchase && row.status === "received" && (
          <RowActionButton
            dense={dense}
            // Đơn theo đợt: lùi về "Giao một phần" (không phải "Đã mua") — nhãn nói đúng đích để
            // người bấm biết mình sẽ rơi về đâu.
            label={
              row.deliveries.length > 0 ? "Mở lại đơn" : "Lùi đã nhận"
            }
            icon="rotateCcw"
            danger
            onClick={() =>
              setReasonModal({ kind: "undo_received", row, reason: "", error: null })
            }
          />
        )}
        {/* {canCancel &&
          row.status !== "received" &&
          row.status !== "cancelled" && (
            <RowActionButton
              dense={dense}
              label="Hủy"
              icon="ban"
              danger
              onClick={() =>
                setReasonModal({ kind: "cancel", row, reason: "", error: null })
              }
            />
          )} */}
        {/* {canDelete && row.status === "draft" && (
          <RowActionButton
            dense={dense}
            label="Xóa"
            icon="trash"
            danger
            onClick={() => setDeleting(row)}
          />
        )} */}
      </div>
    );
  }

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Mua hàng (403).
        </div>
      </main>
    );
  }

  // Banner lỗi dùng CHUNG cho cả hai tab, vì `error` là MỘT state và cả hai tab đều ghi vào nó:
  // tab yêu cầu ghi khi lập phiếu từ một yêu cầu không còn chờ xử lý, tab phiếu ghi khi thao tác
  // trên phiếu / in phiếu hỏng. Nếu chỉ treo banner ở một tab thì lời báo lỗi của tab kia biến mất
  // trong im lặng — người dùng bấm mà không hiểu vì sao không có gì xảy ra.
  const bannerLoi = error ? (
    <div className="banner banner--error" role="alert">
      {error}
    </div>
  ) : null;

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Thu mua</p>
        <h1 className="md-page__title">Mua hàng</h1>
        <p className="md-page__sub">
          Bộ phận mua hàng lập đơn mua từ YCMH, gửi người có quyền duyệt, sau đó
          theo dõi đang mua và đã nhận hàng.
        </p>
      </header>

      {/* Hai tab con: mỗi bảng một khung nhìn riêng. Số trên tab yêu cầu là số ĐANG CHỜ MUA
          (`open`), KHÁC số dòng bảng bên trong (bảng lọc "Tất cả") — xem chú thích ở `choMua`. */}
      <div className="purchase__tabs">
        <StatusTabs
          active={tab}
          onChange={(key) => setTab(key as PurchaseTab)}
          tabs={[
            {
              key: "yeu-cau",
              label: "Yêu cầu chờ xử lý",
              count: choMua.soLuong,
              tone: coYcQuaHan ? "alert" : "default",
            },
            { key: "phieu", label: "Đơn mua hàng", count: total },
          ]}
        />
      </div>

      {/* Chỉ dựng nội dung của tab ĐANG MỞ (bảng kia không nằm dưới mép màn nữa, nó không tồn tại).
          Nhưng DỮ LIỆU vẫn tải cả hai ngay từ đầu — số đếm trên tab kia phải đúng ngay. */}
      {tab === "yeu-cau" && (
      <section className="card md-page__tablewrap purchase__source-inbox">
        <div className="purchase__source-head">
          <div>
            <p className="eyebrow">Yêu cầu từ phòng ban</p>
            <h2>Danh sách chờ Thu mua xử lý</h2>
          </div>
        </div>

        {bannerLoi}

        <div className="purchase__source-toolbar">
          <form
            className="md-page__search"
            onSubmit={(e) => {
              e.preventDefault();
              setSourcePage(1);
            }}
          >
            <input
              className="input"
              placeholder="Tìm mã yêu cầu, mục đích..."
              value={sourceQ}
              onChange={(e) => {
                setSourceQ(e.target.value);
                setSourcePage(1);
              }}
            />
            {/* <Button type="submit" variant="ghost">
              Tìm
            </Button> */}
          </form>
          <select
            className="input purchase__select"
            value={sourceStatus}
            onChange={(e) => {
              setSourceStatus(e.target.value as SourceStatusFilter);
              setSourcePage(1);
            }}
          >
            <option value="all">Tất cả yêu cầu</option>
            {Object.entries(SOURCE_STATUS_META).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </div>

        <table className="md-page__table">
          <thead>
            {/* Thao tác đứng CUỐI — khớp bảng Phiếu mua ngay dưới. Cùng một màn mà hai bảng để
                cột nút ở hai đầu thì mắt phải nhảy qua lại. */}
            <tr>
              <th>Mã yêu cầu</th>
              <th>Nguồn</th>
              <th>Cần hàng</th>
              <th>Vật tư</th>
              <th>Trạng thái</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {sourceLoading ? (
              <EmptyRow colSpan={6} trangThai="dang-tai" />
            ) : sourceError ? (
              <EmptyRow
                colSpan={6}
                trangThai="loi"
                loi={sourceError}
                onThuLai={loadSources}
              />
            ) : sourceRows.length === 0 ? (
              <EmptyRow
                colSpan={6}
                icon="clipboard"
                title="Chưa có yêu cầu mua từ phòng ban"
                sub="Đơn mua hàng luôn bắt đầu từ một yêu cầu của bộ phận — chờ họ gửi sang."
              />
            ) : (
              sourceRows.map((row) => {
                const disabled = row.status !== "open";
                return (
                  <tr
                    key={row.id}
                    className="md-page__row"
                    onClick={() =>
                      !disabled && canCreate
                        ? openCreatePurchaseRequest(row)
                        : undefined
                    }
                  >
                    <td>
                      <strong className="md-page__mono">{row.code}</strong>
                      <div className="md-page__muted">{noiDung(row)}</div>
                    </td>
                    <td>
                      <div>
                        {row.requesting_department_name ||
                          row.requested_by_name ||
                          "Nội bộ"}
                      </div>
                    </td>
                    <td>{fmtDate(row.needed_date)}</td>
                    <td>
                      <strong>{row.lines.length} dòng</strong>
                      <div className="md-page__muted">
                        {row.lines
                          .slice(0, 2)
                          .map((line) => line.item_name)
                          .join(", ")}
                      </div>
                    </td>
                    <td>
                      <SourceStatusBadge status={row.status} />
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {canCreate && !disabled ? (
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => openCreatePurchaseRequest(row)}
                        >
                          Tạo đơn
                        </Button>
                      ) : (
                        <span className="md-page__muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        <div className="purchase__source-foot">
          <span className="md-page__muted">
            Tổng {sourceTotal} yêu cầu
            {sourceTotalPages > 1 ? ` · Trang ${sourcePage}/${sourceTotalPages}` : ""}
          </span>
          {sourceTotalPages > 1 && (
            <div className="md-page__pager-btns">
              <Button
                variant="ghost"
                disabled={sourcePage <= 1 || sourceLoading}
                onClick={() => setSourcePage((value) => value - 1)}
              >
                Trước
              </Button>
              <Button
                variant="ghost"
                disabled={sourcePage >= sourceTotalPages || sourceLoading}
                onClick={() => setSourcePage((value) => value + 1)}
              >
                Sau
              </Button>
            </div>
          )}
        </div>
      </section>
      )}

      {tab === "phieu" && (
      <>
      {/* Dải nhắc CHỈ hiện khi có yêu cầu đã quá ngày cần hàng — nó là lời cảnh báo, không phải
          thanh trạng thái. Ngày bình thường không render gì cả (xem `coYcQuaHan`). */}
      {coYcQuaHan && (
        <div className="purchase__nhac" role="status">
          <Icon name="alert" size={14} />
          <span>
            <b>{choMua.soLuong}</b> yêu cầu đang chờ, sớm nhất cần{" "}
            {fmtDate(choMua.somNhat)}
          </span>
          <button
            type="button"
            className="purchase__nhac-xem"
            onClick={() => setTab("yeu-cau")}
          >
            Xem
          </button>
        </div>
      )}

      <section className="card md-page__tablewrap purchase__list">
        {/* Thẻ này TRƯỚC 08/08/2026 không có tiêu đề, còn ô tìm + ô lọc thì trôi lơ lửng ngoài thẻ.
            Nay tiêu đề bên trái, bộ lọc bên phải, tất cả nằm TRONG thẻ — cùng khuôn đầu thẻ với
            bảng yêu cầu. Đừng kéo bộ lọc ra ngoài lại. */}
        <div className="purchase__source-head purchase__list-head">
          <div>
            <p className="eyebrow">Thu mua</p>
            <h2>Đơn mua hàng</h2>
          </div>
          <div className="purchase__list-tools">
            <form
              className="md-page__search"
              onSubmit={(e) => {
                // KHÔNG gọi load() ở đây: `load` đóng gói từ khoá ĐÃ CHẬM 300ms, bấm Enter ngay
                // sau khi gõ sẽ bắn lượt với từ khoá CŨ, rồi 300ms sau mới bắn lượt mới — lượt cũ
                // về sau là đè kết quả sai lên bảng. Cứ để bộ chờ tự bắn.
                e.preventDefault();
                setPage(1);
              }}
            >
              <input
                className="input"
                placeholder="Tìm mã phiếu, mục đích, ghi chú..."
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
              />
            </form>
            <select
              className="input purchase__select"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value as StatusFilter);
                setPage(1);
              }}
            >
              <option value="all">Tất cả</option>
              {Object.entries(STATUS_META).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </select>
            <select
              className="input purchase__select"
              value={supplierFilter}
              onChange={(e) => {
                setSupplierFilter(e.target.value === "all" ? "all" : Number(e.target.value));
                setPage(1);
              }}
            >
              <option value="all">Tất cả nhà cung cấp</option>
              {suppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
            <select
              className="input purchase__select"
              value={depositFilter}
              onChange={(e) => {
                setDepositFilter(e.target.value as DepositFilter);
                setPage(1);
              }}
            >
              <option value="all">Tất cả tiền cọc</option>
              <option value="none">Không yêu cầu cọc</option>
              <option value="unpaid">Chưa cọc</option>
              <option value="partial">Cọc thiếu</option>
              <option value="enough">Cọc đủ</option>
            </select>
            <div className="purchase__date-group">
              <span>Ngày tạo</span>
              <input
                className="input purchase__date-filter"
                type="date"
                title="Ngày tạo từ"
                value={createdFrom}
                onChange={(e) => {
                  setCreatedFrom(e.target.value);
                  setPage(1);
                }}
              />
              <input
                className="input purchase__date-filter"
                type="date"
                title="Ngày tạo đến"
                value={createdTo}
                onChange={(e) => {
                  setCreatedTo(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="purchase__date-group">
              <span>Ngày cần hàng</span>
              <input
                className="input purchase__date-filter"
                type="date"
                title="Ngày cần từ"
                value={neededFrom}
                onChange={(e) => {
                  setNeededFrom(e.target.value);
                  setPage(1);
                }}
              />
              <input
                className="input purchase__date-filter"
                type="date"
                title="Ngày cần đến"
                value={neededTo}
                onChange={(e) => {
                  setNeededTo(e.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
        </div>

        {bannerLoi}

        <table className="md-page__table">
          <thead>
            <tr>
              {/* TRẠNG THÁI luôn đứng NGAY TRƯỚC Thao tác — thống nhất ở mọi màn Thu mua /
                  Kế toán. Mỗi màn để một chỗ khác nhau thì người dùng phải đi tìm lại từng lần. */}
              <th>Mã đơn</th>
              <th>Nhà cung cấp</th>
              <th>Ngày tạo</th>
              <th>Cần / Dự kiến nhận</th>
              <th>Tổng dự kiến</th>
              <th>Tiền cọc</th>
              <th>Người tạo / duyệt</th>
              <th>Trạng thái</th>
              {/* `md-page__actions-col` canh tiêu đề THEO NÚT (nút dense nằm sát phải). Thiếu lớp
                  này thì chữ "Thao tác" đứng một nơi, cụm nút đứng một nẻo. */}
              <th className="md-page__actions-col">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <EmptyRow colSpan={9} trangThai="dang-tai" />
            ) : listError ? (
              <EmptyRow colSpan={9} trangThai="loi" loi={listError} onThuLai={load} />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={9}
                icon="cart"
                title="Chưa có đơn mua hàng nào khớp"
                sub={
                  q.trim() ||
                  status !== "all" ||
                  supplierFilter !== "all" ||
                  depositFilter !== "all" ||
                  createdFrom ||
                  createdTo ||
                  neededFrom ||
                  neededTo
                    ? "Thử bỏ bớt bộ lọc hoặc xoá từ khoá tìm kiếm."
                    : "Sang tab Yêu cầu chờ xử lý để chọn một yêu cầu rồi lập đơn mua."
                }
                action={
                  q.trim() ||
                  status !== "all" ||
                  supplierFilter !== "all" ||
                  depositFilter !== "all" ||
                  createdFrom ||
                  createdTo ||
                  neededFrom ||
                  neededTo ? (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => {
                        setQ("");
                        setStatus("all");
                        setSupplierFilter("all");
                        setDepositFilter("all");
                        setCreatedFrom("");
                        setCreatedTo("");
                        setNeededFrom("");
                        setNeededTo("");
                        setPage(1);
                      }}
                    >
                      Xoá bộ lọc
                    </button>
                  ) : undefined
                }
              />
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className={`md-page__row${selected?.id === row.id ? " purchase__row--selected" : ""}`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="purchase__code-cell">
                    <strong className="md-page__mono">{row.code}</strong>
                    <div className="purchase__source-codes">
                      {row.sources.length
                        ? row.sources.map((source, index) => (
                            <span key={source.id}>
                              {index > 0 && ", "}
                              <CodeLink
                                code={source.code}
                                onOpen={openYcmh}
                              />
                            </span>
                          ))
                        : "Chưa gắn yêu cầu"}
                    </div>
                    <div className="md-page__muted purchase__row-purpose">
                      {noiDung(row) || "—"}
                    </div>
                  </td>
                  <td
                    className="purchase__supplier-cell"
                    title={row.supplier_name ?? undefined}
                  >
                    {row.supplier_name || (
                      <span className="md-page__muted">Chưa chọn</span>
                    )}
                  </td>
                  <td className="purchase__date-cell">
                    {fmtDate(row.created_at)}
                  </td>
                  <td className="purchase__date-cell">
                    {fmtDate(row.needed_date)}
                    {row.expected_receipt_date && (
                      <div className="md-page__muted">
                        Nhận: {fmtDate(row.expected_receipt_date)}
                      </div>
                    )}
                  </td>
                  <td className="md-page__price purchase__money-cell">
                    {money(row.total_estimate)}
                  </td>
                  <td className="md-page__price purchase__money-cell">
                    <DepositCell row={row} />
                  </td>
                  <td>
                    <div>
                      {row.created_by_name || (
                        <span className="md-page__muted">—</span>
                      )}
                    </div>
                    <div className="md-page__muted">
                      {row.approved_by_name || "Chưa duyệt"}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={row.status} />
                  </td>
                  <td
                    className="md-page__actions-col"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {actionButtons(row, true)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {/* Chân bảng CÙNG KHUÔN với bảng yêu cầu phía trên: tổng bên trái, nút chuyển trang bên
            phải, và CHỈ hiện nút khi thật sự có nhiều hơn một trang. Trước 08/08/2026 khối này
            nằm ngoài thẻ và luôn in "Trang 1/1" kèm hai nút mờ — nhiễu mà không nói thêm gì. */}
        <div className="purchase__source-foot">
          <span className="md-page__muted">
            Tổng {total} đơn
            {totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ""}
          </span>
          {totalPages > 1 && (
            <div className="md-page__pager-btns">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Sau
              </button>
            </div>
          )}
        </div>
      </section>
      </>
      )}

      {/* Hộp thoại nằm NGOÀI hai tab: mở từ tab nào cũng phải sống tiếp khi tab đổi (lập phiếu
          xong là màn tự nhảy sang tab phiếu — kéo hộp vào trong tab thì nó bị gỡ giữa chừng). */}
      {selected && (
        <DetailModal
          kicker="Chi tiết đơn"
          title={selected.code}
          subtitle={noiDung(selected)}
          badge={<StatusBadge status={selected.status} />}
          footer={actionButtons(selected)}
          onClose={() => setSelectedId(null)}
        >
          <dl className="purchase__facts">
            <div>
              <dt>Nhà cung cấp</dt>
              <dd>{selected.supplier_name || "Chưa chọn"}</dd>
            </div>
            <div>
              <dt>Phiếu yêu cầu mua hàng</dt>
              <dd>
                {selected.sources.length
                  ? selected.sources.map((source, index) => (
                      <span key={source.id}>
                        {index > 0 && ", "}
                        <CodeLink code={source.code} onOpen={openYcmh} />
                      </span>
                    ))
                  : "Chưa gắn"}
              </dd>
            </div>
            <div>
              <dt>Cần hàng</dt>
              <dd>{fmtDate(selected.needed_date)}</dd>
            </div>
            <div>
              <dt>Dự kiến nhận hàng</dt>
              <dd>{fmtDate(selected.expected_receipt_date)}</dd>
            </div>
            <div>
              <dt>Gửi duyệt</dt>
              <dd>{fmtDate(selected.submitted_at)}</dd>
            </div>
            <div>
              <dt>Duyệt bởi</dt>
              <dd>{selected.approved_by_name || "—"}</dd>
            </div>
          </dl>
          {selected.reject_reason && (
            <div className="purchase__note purchase__note--reject">
              <strong>Lý do từ chối / huỷ:</strong> {selected.reject_reason}
            </div>
          )}
          <div className="purchase__lines">
            {selected.lines.map((line) => (
              <div className="purchase__line" key={line.id}>
                <div>
                  <strong>{line.item_name}</strong>
                  <div className="md-page__muted">
                    {line.quantity.toLocaleString("vi-VN")} {line.unit} ×{" "}
                    {money(line.expected_unit_price)}
                  </div>
                  <div className="md-page__muted">
                    Giảm {line.discount_percent}% ={" "}
                    {money(line.discount_amount)} · VAT {line.vat_percent}%
                    = {money(line.vat_amount)}
                  </div>
                  {line.note && (
                    <div className="md-page__muted">{line.note}</div>
                  )}
                </div>
                <strong>{money(line.line_total)}</strong>
              </div>
            ))}
          </div>
          <div className="purchase__detail-total">
            <span>Tổng dự kiến</span>
            <strong>{money(selected.total_estimate)}</strong>
          </div>

          <ContractBlock
            row={selected}
            canUpdate={canUpdate}
            onChanged={updateRow}
            onError={setError}
          />

          <DeliveriesBlock
            row={selected}
            canUpdate={canUpdate}
            canApprove={canApprovePurchase}
            onGhiDot={(delivery) =>
              setDeliveryModal({ row: selected, delivery })
            }
            onGanHoaDon={() => setInvoiceModal(selected)}
            onXoaDot={(delivery) =>
              setDeletingDelivery({ row: selected, delivery })
            }
            onDongDon={() =>
              setCloseModal({ row: selected, reason: "", error: null })
            }
            onNhapKho={(dot) => nhapKhoTuDot(selected, dot)}
          />

          <p className="eyebrow" style={{ marginTop: 16 }}>
            Lịch sử trạng thái
          </p>
          <StatusHistoryTimeline items={selected.status_history} />
        </DetailModal>
      )}

      {mode && (
        <div className="md-page__overlay" role="presentation">
          <div
            className="card md-page__dialog purchase__dialog purchase__dialog--order"
            role="dialog"
            aria-modal="true"
          >
            <div className="md-page__dialog-head">
              <h2>
                {mode === "edit" ? "Sửa đơn mua hàng" : "Tạo đơn mua hàng"}
              </h2>
              <button
                type="button"
                className="md-page__close"
                onClick={() => setMode(null)}
              >
                ×
              </button>
            </div>
            <form className="md-page__dialog-body" onSubmit={save}>
              {formError && (
                <div className="banner banner--error" role="alert">
                  {formError}
                </div>
              )}
              <div className="md-page__form-grid">
                {/* Ô NCC ở ĐẦU PHIẾU chỉ còn cho chế độ SỬA: phiếu đã tồn tại thì nó vốn thuộc về
                    một nhà cung cấp. Lúc TẠO thì NCC gán ở từng DÒNG, vì một yêu cầu thường chứa
                    hàng của nhiều nơi và mỗi NCC phải ra một phiếu riêng. */}
                {mode === "edit" && (
                <LocalField label="Nhà cung cấp" required>
                  <select
                    className="input"
                    required
                    value={form.supplier_id ?? ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        supplier_id: e.target.value ? Number(e.target.value) : null,
                        lines: applySupplierPrices(
                          form.lines,
                          suppliers,
                          e.target.value ? Number(e.target.value) : null,
                        ),
                      })
                    }
                  >
                    <option value="">Chọn nhà cung cấp</option>
                    {suppliers.map((supplier) => {
                      const bestId = bestSupplierIdForLines(form.lines, suppliers);
                      const bestHint =
                        supplier.id === bestId ? " - giá thấp nhất" : "";
                      return (
                        <option key={supplier.id} value={supplier.id}>
                          {`${supplier.name}${bestHint}`}
                        </option>
                      );
                    })}
                  </select>
                </LocalField>
                )}
                <LocalField label="Ngày cần hàng" required>
                  <input
                    className="input"
                    type="date"
                    required
                    min={minPurchaseDate}
                    value={form.needed_date ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, needed_date: e.target.value })
                    }
                  />
                </LocalField>
                <LocalField label="Ngày dự kiến nhận hàng">
                  <input
                    className="input"
                    type="date"
                    min={expectedReceiptMinDate}
                    value={form.expected_receipt_date ?? ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        expected_receipt_date: e.target.value,
                      })
                    }
                  />
                </LocalField>
                {/* MỘT ô thay cho cặp "Mục đích" + "Ghi chú" (chủ chốt 07/08/2026) — xem
                    DepartmentPurchaseRequestsPage cho lý do. */}
                <LocalField label="Nội dung / mục đích" wide required>
                  <textarea
                    className="input purchase__textarea"
                    required
                    value={form.content ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, content: e.target.value })
                    }
                    placeholder="Ví dụ: mua giấy cho đơn hàng ĐH-2026-031, giao trước 20/8"
                  />
                </LocalField>
              </div>

              <div className="purchase__form-section">
                <div className="purchase__form-section-head">
                  <h3>Dòng hàng</h3>
                  {/* KHÔNG có nút thêm dòng: danh sách hàng lấy nguyên từ yêu cầu của bộ phận.
                      Thu mua thêm được một dòng thì thành mua thứ không ai xin. Cần mua thêm thì
                      bộ phận gửi yêu cầu mới, để còn có người duyệt. */}
                  <span className="md-page__muted">
                    Lấy từ yêu cầu — Thu mua chọn nhà cung cấp và giá
                  </span>
                </div>
                <div
                  className={`purchase__line-editor${
                    mode !== "edit" ? " purchase__line-editor--tach-ncc" : ""
                  }`}
                >
                  <div className="purchase__line-labels" aria-hidden="true">
                    <span>
                      Vật tư <span className="purchase__required-star">*</span>
                    </span>
                    {mode !== "edit" && (
                      <span>
                        Nhà cung cấp{" "}
                        <span className="purchase__required-star">*</span>
                      </span>
                    )}
                    <span>
                      ĐVT <span className="purchase__required-star">*</span>
                    </span>
                    <span>
                      Số lượng{" "}
                      <span className="purchase__required-star">*</span>
                    </span>
                    <span>
                      Đơn giá <span className="purchase__required-star">*</span>
                    </span>
                    <span>Giảm (%)</span>
                    <span>Tiền giảm</span>
                    <span>VAT (%)</span>
                    <span>Ghi chú dòng</span>
                    <span>Thành tiền</span>
                    <span></span>
                  </div>
                  {form.lines.map((line, index) => (
                    <div className="purchase__line-edit" key={index}>
                      {/* Vật tư và ĐVT do BỘ PHẬN ĐỀ NGHỊ quyết, thu mua không được đổi — đổi ở
                          đây là mua thứ khác với thứ người ta xin mà không ai hay. Thu mua chỉ
                          chọn MUA CỦA AI và giá. Cùng lý do: không thêm/xoá dòng. */}
                      <input
                        className="input purchase__line-name purchase__readonly-field"
                        required
                        readOnly
                        aria-label="Tên vật tư"
                        title="Vật tư do bộ phận đề nghị khai — Thu mua không sửa được"
                        value={line.item_name}
                      />
                      {mode !== "edit" && (
                        <LineSupplierPicker
                          line={line}
                          suppliers={suppliers}
                          onPick={(chao) =>
                            setLine(index, {
                              supplier_id: chao?.supplier_id ?? null,
                              // Chọn NCC là lấy luôn GIÁ CỦA CHÍNH HỌ — để người dùng gõ lại là
                              // mở đường cho việc đặt một đằng, giá một nẻo.
                              ...(chao
                                ? {
                                    unit: line.unit || chao.unit,
                                    expected_unit_price: chao.unit_price,
                                    vat_percent: chao.vat_percent,
                                  }
                                : {}),
                            })
                          }
                        />
                      )}
                      <input
                        className="input purchase__line-unit purchase__readonly-field"
                        required
                        readOnly
                        aria-label="Đơn vị tính"
                        title="Đơn vị tính do bộ phận đề nghị khai — Thu mua không sửa được"
                        value={line.unit}
                      />
                      <input
                        className="input purchase__number-input purchase__readonly-field"
                        type="number"
                        required
                        readOnly
                        aria-label="Số lượng"
                        title="Số lượng do bộ phận đề nghị khai — Thu mua không sửa được"
                        value={line.quantity > 0 ? line.quantity : ""}
                      />
                      <input
                        className="input purchase__number-input"
                        type="number"
                        min="1"
                        step="1"
                        required
                        aria-label="Đơn giá dự kiến"
                        placeholder="VD: 2200"
                        value={
                          line.expected_unit_price > 0
                            ? line.expected_unit_price
                            : ""
                        }
                        onChange={(e) =>
                          setLine(index, {
                            expected_unit_price: Number(e.target.value || 0),
                          })
                        }
                      />
                      <input
                        className="input purchase__number-input"
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        aria-label="Giảm giá phần trăm"
                        placeholder="VD: 5"
                        value={
                          line.discount_percent > 0 ? line.discount_percent : ""
                        }
                        onChange={(e) =>
                          setLine(index, {
                            discount_percent: Number(e.target.value || 0),
                          })
                        }
                      />
                      <strong className="purchase__line-sum">
                        {lineDiscountAmount(line) > 0 ? (
                          money(lineDiscountAmount(line))
                        ) : (
                          <span className="md-page__muted">0 đ</span>
                        )}
                      </strong>
                      <input
                        className="input purchase__number-input"
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        aria-label="Thuế GTGT phần trăm"
                        placeholder="VD: 8"
                        value={line.vat_percent > 0 ? line.vat_percent : ""}
                        onChange={(e) =>
                          setLine(index, {
                            vat_percent: Number(e.target.value || 0),
                          })
                        }
                      />
                      <input
                        className="input purchase__line-note"
                        aria-label="Ghi chú dòng"
                        placeholder="Nếu có"
                        value={line.note ?? ""}
                        onChange={(e) =>
                          setLine(index, { note: e.target.value })
                        }
                      />
                      <strong className="purchase__line-sum">
                        {line.quantity > 0 && line.expected_unit_price > 0 ? (
                          money(lineTotal(line))
                        ) : (
                          <span className="md-page__muted">Chưa tính</span>
                        )}
                      </strong>
                      {/* Ô trống giữ chỗ cột cuối — bỏ hẳn thì lưới lệch một cột. Không cho xoá
                          dòng vì bỏ bớt là mua thiếu so với thứ bộ phận đã xin, mà phiếu vẫn
                          trông như đã xử lý xong yêu cầu đó. */}
                      <span aria-hidden="true" />
                    </div>
                  ))}
                </div>
                <div className="purchase__form-total">
                  <span>Tổng dự kiến</span>
                  <strong>
                    {money(
                      form.lines.reduce(
                        (sum, line) => sum + lineTotal(line),
                        0,
                      ),
                    )}
                  </strong>
                </div>
                {/* Nói TRƯỚC sẽ đẻ ra mấy phiếu. Bấm Lưu rồi mới thấy danh sách nhảy thêm mấy
                    dòng là bất ngờ không đáng có — và người dùng cần biết để còn đổi NCC. */}
                {mode !== "edit" && phieuSeTao.length > 0 && (
                  <p className="md-page__muted" style={{ marginTop: 4 }}>
                    Sẽ tạo <strong>{phieuSeTao.length} đơn</strong> —{" "}
                    {phieuSeTao
                      .map(
                        (p) =>
                          `${p.ten}: ${p.soDong} dòng / ${money(p.tien)}`,
                      )
                      .join(" · ")}
                  </p>
                )}
              </div>

              <div className="md-page__dialog-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setMode(null)}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving}>
                  Lưu đơn
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Xóa phiếu nháp?"
        message={
          deleting
            ? `Phiếu ${deleting.code} sẽ bị xóa khỏi hệ thống.`
            : undefined
        }
        danger
        confirmLabel="Xóa phiếu"
        busy={deleting ? actionBusy === `delete:${deleting.id}` : false}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />

      <ConfirmDialog
        open={Boolean(reasonModal)}
        title={
          reasonModal?.kind === "reject"
            ? "Từ chối đơn?"
            : reasonModal?.kind === "undo_received"
              ? "Lùi về 'Đang mua'?"
            : "Hủy đơn?"
        }
        message={
          reasonModal
            ? reasonModal.kind === "undo_received"
              ? `Đơn ${reasonModal.row.code} — công nợ của đơn này sẽ mất khỏi màn Kế toán, và yêu cầu của bộ phận quay về "Đang mua".`
              : `Đơn ${reasonModal.row.code}`
            : undefined
        }
        danger
        confirmLabel={
          reasonModal?.kind === "reject"
            ? "Từ chối đơn"
            : reasonModal?.kind === "undo_received"
              ? "Lùi trạng thái"
              : "Hủy đơn"
        }
        busy={
          reasonModal
            ? actionBusy === `${reasonModal.kind}:${reasonModal.row.id}`
            : false
        }
        error={reasonModal?.error ?? null}
        onConfirm={confirmReason}
        onCancel={() => setReasonModal(null)}
      >
        <label className="purchase__field">
          <span>
            {reasonModal?.kind === "reject"
              ? "Lý do từ chối"
              : reasonModal?.kind === "undo_received"
                ? "Lý do lùi (bắt buộc)"
                : "Lý do / ghi chú"}
          </span>
          <textarea
            className="input purchase__textarea"
            value={reasonModal?.reason ?? ""}
            onChange={(e) =>
              setReasonModal((current) =>
                current ? { ...current, reason: e.target.value } : current,
              )
            }
          />
        </label>
      </ConfirmDialog>

      {receiveModal && (
        <ReceiveDialog
          row={receiveModal.row}
          mode={receiveModal.mode}
          onClose={() => setReceiveModal(null)}
          onDone={(next) => {
            updateRow(next);
            setReceiveModal(null);
            loadSources();
          }}
        />
      )}

      {deliveryModal && (
        <DeliveryDialog
          key={deliveryModal.delivery?.id ?? "new"}
          row={deliveryModal.row}
          delivery={deliveryModal.delivery}
          onClose={() => setDeliveryModal(null)}
          onDone={(next) => {
            updateRow(next);
            setDeliveryModal(null);
            loadSources();
          }}
          onChanged={(next) => {
            updateRow(next);
            setDeliveryModal((cur) => (cur ? { ...cur, row: next } : cur));
          }}
        />
      )}

      {invoiceModal && (
        <InvoiceDialog
          row={invoiceModal}
          onClose={() => setInvoiceModal(null)}
          onDone={(next) => {
            updateRow(next);
            setInvoiceModal(null);
          }}
        />
      )}

      <ConfirmDialog
        open={Boolean(deletingDelivery)}
        title="Xóa đợt giao?"
        message={
          deletingDelivery
            ? `Đợt ${deletingDelivery.delivery.seq_no} ngày ${fmtDate(
                deletingDelivery.delivery.delivery_date,
              )} — trị giá ${money(deletingDelivery.delivery.amount)}. Công nợ của đơn sẽ giảm đúng số này.`
            : undefined
        }
        danger
        confirmLabel="Xóa đợt giao"
        busy={
          deletingDelivery
            ? actionBusy === `del-dot:${deletingDelivery.delivery.id}`
            : false
        }
        onConfirm={confirmXoaDot}
        onCancel={() => setDeletingDelivery(null)}
      />

      <ConfirmDialog
        open={Boolean(closeModal)}
        title="Đóng đơn (không giao nữa)?"
        message={
          closeModal
            ? `Phiếu ${closeModal.row.code} — chốt số thực nhận bằng số đã giao (${money(
                closeModal.row.gia_tri_da_giao,
              )}). Phần hàng chưa về sẽ không còn được ghi nợ.`
            : undefined
        }
        danger
        confirmLabel="Đóng đơn"
        busy={closeModal ? actionBusy === `close:${closeModal.row.id}` : false}
        error={closeModal?.error ?? null}
        onConfirm={confirmDongDon}
        onCancel={() => setCloseModal(null)}
      >
        <label className="purchase__field">
          <span>Lý do đóng đơn (bắt buộc)</span>
          <textarea
            className="input purchase__textarea"
            placeholder="Ví dụ: NCC báo hết hàng, không giao nốt phần còn lại."
            value={closeModal?.reason ?? ""}
            onChange={(e) =>
              setCloseModal((current) =>
                current ? { ...current, reason: e.target.value } : current,
              )
            }
          />
        </label>
      </ConfirmDialog>
    </main>
  );
}

/**
 * Khai SỐ THỰC NHẬN lúc bấm "Đã nhận hàng".
 *
 * Ô số điền sẵn bằng số đã đặt ⇒ hàng về đủ thì chỉ bấm Xác nhận, KHÔNG phải gõ gì. Chỉ khi NCC
 * giao thiếu mới phải sửa xuống. Số này là nền của công nợ và là trần lập phiếu chi — ghi nợ đủ
 * cho hàng về thiếu là kế toán chi thừa tiền thật.
 *
 * `mode="edit"` dùng cho ca NCC giao nhiều đợt (đợt 1 về 600, đợt 2 về nốt thì sửa lên 1000);
 * đường này server đòi quyền DUYỆT vì nó đổi số nợ đã ghi.
 */
function ReceiveDialog({
  row,
  mode,
  onClose,
  onDone,
}: {
  row: PurchaseRequestRow;
  mode: "receive" | "edit";
  onClose: () => void;
  onDone: (next: PurchaseRequestRow) => void;
}) {
  const { token } = useAuth();
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      row.lines.map((line) => [
        line.id,
        String(line.received_quantity ?? line.quantity),
      ]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const thieu = row.lines.some(
    (line) => Number(values[line.id] ?? line.quantity) < line.quantity,
  );

  async function submit() {
    if (!token) return;
    const lines = row.lines.map((line) => ({
      line_id: line.id,
      received_quantity: Number(values[line.id] ?? line.quantity),
    }));
    if (lines.some((l) => !Number.isFinite(l.received_quantity!) || l.received_quantity! < 0)) {
      setError("Số thực nhận phải là số không âm.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        mode === "receive"
          ? await api.purchaseRequests.markReceived(token, row.id, lines)
          : await api.purchaseRequests.updateReceivedQuantities(token, row.id, lines),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không lưu được số thực nhận.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      title={mode === "receive" ? "Xác nhận đã nhận hàng" : "Sửa số thực nhận"}
      message={`Phiếu ${row.code} — về đủ thì bấm Xác nhận, về thiếu thì sửa số xuống.`}
      confirmLabel={mode === "receive" ? "Xác nhận đã nhận" : "Lưu số thực nhận"}
      busy={busy}
      error={error}
      onConfirm={submit}
      onCancel={onClose}
    >
      <table className="pay-table">
        <thead>
          <tr>
            <th>Vật tư</th>
            <th className="pay-num">Đặt</th>
            <th className="pay-num">Thực nhận</th>
          </tr>
        </thead>
        <tbody>
          {row.lines.map((line) => (
            <tr key={line.id}>
              <td>{line.item_name}</td>
              <td className="pay-num">
                {line.quantity} {line.unit}
              </td>
              <td className="pay-num">
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={line.quantity}
                  step="any"
                  style={{ width: 110, textAlign: "right" }}
                  value={values[line.id] ?? ""}
                  onChange={(e) =>
                    setValues((current) => ({ ...current, [line.id]: e.target.value }))
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {thieu && (
        <p className="pay-block__hint" style={{ marginTop: 8 }}>
          Có dòng nhận thiếu so với số đặt — công nợ và trần lập phiếu chi sẽ tính theo số thực
          nhận.
        </p>
      )}
    </ConfirmDialog>
  );
}

/** Σ số đã giao của MỘT dòng đặt, cộng qua các đợt — bỏ qua đợt đang sửa (`boQua`) vì số của
 *  chính nó không tính vào "phần các đợt KHÁC đã lấy". Khớp `_clean_dot_lines` bên service. */
function daGiaoKhac(
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
function tienTheoSoLuong(
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

const ATTACHMENT_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
];

/**
 * HỢP ĐỒNG & CHỨNG TỪ — số hợp đồng, cọc dự kiến, ảnh/PDF hợp đồng.
 *
 * Cố ý KHÔNG đẻ danh mục hợp đồng và không đẻ màn mới (Đ3): hợp đồng ở đây là một con số để đối
 * chiếu cộng vài cái ảnh. Tách khỏi form Sửa phiếu vì form đó chỉ mở được với phiếu nháp/bị từ
 * chối, mà hợp đồng thường ký SAU khi phiếu đã duyệt — bắt sửa ở màn nháp là không bao giờ điền
 * được.
 *
 * "Cọc dự kiến" chỉ để NHẮC — nó KHÔNG vào công thức công nợ (tiền cọc THẬT luôn là một phiếu chi
 * loại Đặt cọc; cho số này vào công thức là trừ cọc hai lần). Nhưng nó ĐƯỢC dùng để điền sẵn số
 * tiền khi kế toán lập phiếu Đặt cọc, nên phải khai đúng.
 *
 * CỌC KHOÁ SAU KHI DUYỆT (chủ chốt 06/08/2026): đó là con số người duyệt đã đồng ý; cho sửa sau
 * là đổi số đã ký mà không ai duyệt lại. Số hợp đồng và ảnh thì KHÔNG khoá — hợp đồng ký sau.
 */
function ContractBlock({
  row,
  canUpdate,
  onChanged,
  onError,
}: {
  row: PurchaseRequestRow;
  canUpdate: boolean;
  onChanged: (next: PurchaseRequestRow) => void;
  onError: (message: string | null) => void;
}) {
  const { token } = useAuth();
  const [soHopDong, setSoHopDong] = useState(row.contract_number ?? "");
  const [coc, setCoc] = useState(String(row.deposit_expected || ""));
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Cọc chỉ sửa được khi phiếu còn ở nháp / chờ duyệt / bị từ chối — khớp chốt bên service.
  const cocKhoa = !["draft", "pending_approval", "rejected"].includes(row.status);
  const hopDong = row.attachments.filter((a) => a.kind === "hop_dong");
  const banDau =
    (row.contract_number ?? "") === soHopDong.trim() &&
    (row.deposit_expected || 0) === (Number(coc) || 0);

  async function luu() {
    if (!token || busy) return;
    setBusy(true);
    onError(null);
    try {
      onChanged(
        await api.purchaseRequests.updateContract(token, row.id, {
          contract_number: soHopDong.trim() || null,
          // Cọc đã khoá thì gửi lại ĐÚNG số cũ — server chỉ chặn khi số THAY ĐỔI, nhờ vậy sửa
          // riêng số hợp đồng trên đơn đã duyệt vẫn lưu được.
          deposit_expected: cocKhoa
            ? row.deposit_expected
            : Math.max(0, Math.round(Number(coc) || 0)),
        }),
      );
    } catch (err) {
      onError(
        err instanceof ApiError ? err.message : "Không lưu được thông tin hợp đồng.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function tai(list: FileList | null) {
    if (!token || !list?.length) return;
    setUploading(true);
    onError(null);
    try {
      let moi = row;
      for (const file of Array.from(list)) {
        moi = await api.purchaseRequests.uploadAttachment(
          token,
          row.id,
          file,
          "hop_dong",
        );
      }
      onChanged(moi);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Không tải được file lên.");
    } finally {
      setUploading(false);
    }
  }

  async function xoa(attachment: PurchaseAttachmentRow) {
    if (!token) return;
    setUploading(true);
    onError(null);
    try {
      onChanged(
        await api.purchaseRequests.deleteAttachment(token, row.id, attachment.id),
      );
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Không xóa được file.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="pdot">
      <header className="pdot__head">
        <h3>Hợp đồng &amp; chứng từ</h3>
        {canUpdate && (
          // ⚠️ GIỮ `ghost`, ĐỪNG nâng lên `accent`. Nút này nằm CÙNG hộp thoại Chi tiết phiếu với
          // "Ghi đợt giao" (DeliveriesBlock) — luật là TỐI ĐA MỘT nút cam mỗi hộp thoại, và suất
          // cam đó thuộc về "Ghi đợt giao": đó là việc làm gần như mỗi lần hàng về và là đường
          // DUY NHẤT sinh công nợ, còn hợp đồng khai một lần rồi thôi. Hai nút cam cạnh nhau là
          // mắt không biết nhìn đâu.
          // `disabled={banDau}` giữ nguyên: chưa sửa gì thì không có gì để lưu.
          <Button
            type="button"
            variant="ghost"
            loading={busy}
            disabled={banDau}
            onClick={luu}
          >
            Lưu hợp đồng
          </Button>
        )}
      </header>

      <div className="pdot__contract">
        <label className="purchase__field">
          <span>Số hợp đồng</span>
          <input
            className="input"
            maxLength={64}
            readOnly={!canUpdate}
            value={soHopDong}
            onChange={(e) => setSoHopDong(e.target.value)}
            placeholder="Chưa có hợp đồng"
          />
        </label>
        <label className="purchase__field">
          <span>Cọc dự kiến{cocKhoa && " (đã duyệt — khoá)"}</span>
          <input
            className="input purchase__number-input"
            type="number"
            min={0}
            step={1000}
            readOnly={!canUpdate || cocKhoa}
            value={coc}
            onChange={(e) => setCoc(e.target.value)}
            placeholder="0"
          />
          <small className="pdot__hint">
            {cocKhoa ? (
              <>
                Đơn đã duyệt nên cọc khoá — đây là con số người duyệt đã đồng ý.
                Cần đổi thì lùi phiếu về nháp rồi duyệt lại.
              </>
            ) : (
              <>
                Tiền cọc thật là một <strong>phiếu chi Đặt cọc</strong> bên Kế
                toán — số này <strong>không</strong> vào công nợ, nhưng sẽ được{" "}
                <strong>điền sẵn</strong> khi kế toán lập phiếu cọc.
              </>
            )}
          </small>
        </label>
      </div>

      <div className="pdot__files">
        {hopDong.length === 0 ? (
          <p className="pdot__empty">Chưa đính kèm ảnh/PDF hợp đồng nào.</p>
        ) : (
          <div className="pdot__filegrid">
            {hopDong.map((a) => {
              const href = assetUrl(a.file_url) ?? "#";
              const isImage = ATTACHMENT_IMAGE_TYPES.includes(a.file_type ?? "");
              return (
                <div className="pdot__file" key={a.id}>
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    title={
                      a.uploaded_by_name
                        ? `${a.file_name}\n${a.uploaded_by_name} tải lên ${fmtDate(a.uploaded_at)}`
                        : a.file_name
                    }
                  >
                    {isImage ? (
                      <img
                        className="pdot__thumb"
                        src={href}
                        alt={a.file_name}
                      />
                    ) : (
                      <span className="pdot__filename">{a.file_name}</span>
                    )}
                  </a>
                  {canUpdate && (
                    <button
                      type="button"
                      className="pdot__filex"
                      aria-label={`Xóa ${a.file_name}`}
                      disabled={uploading}
                      onClick={() => xoa(a)}
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {canUpdate && (
          <label className="purchase__field">
            <span>Thêm ảnh / PDF hợp đồng (tối đa 10 MB mỗi file)</span>
            <input
              className="input"
              type="file"
              multiple
              accept="image/*,application/pdf"
              disabled={uploading}
              onChange={(e) => {
                tai(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        )}
      </div>
    </section>
  );
}

/**
 * CÁC ĐỢT GIAO — nơi công nợ thật sự sinh ra.
 *
 * Hàng về tới đâu nợ tới đó: mỗi đợt là một khoản nợ có ngày giao, hạn trả và hoá đơn riêng. Dòng
 * tổng dưới bảng nói đủ ba số để không ai phải tự trừ trong đầu: **Đã giao − Đã chi = Còn nợ**.
 */
function DeliveriesBlock({
  row,
  canUpdate,
  canApprove,
  onGhiDot,
  onGanHoaDon,
  onXoaDot,
  onDongDon,
  onNhapKho,
}: {
  row: PurchaseRequestRow;
  canUpdate: boolean;
  canApprove: boolean;
  onGhiDot: (delivery: PurchaseDeliveryRow | null) => void;
  onGanHoaDon: () => void;
  onXoaDot: (delivery: PurchaseDeliveryRow) => void;
  onDongDon: () => void;
  onNhapKho: (delivery: PurchaseDeliveryRow) => void;
}) {
  const ghiDuoc = canUpdate && GHI_DOT_DUOC.includes(row.status);
  const dots = row.deliveries;

  return (
    <section className="pdot">
      <header className="pdot__head">
        <h3>Các đợt giao</h3>
        <div className="pdot__headbtns">
          {canUpdate && dots.length > 1 && (
            <Button type="button" variant="ghost" onClick={onGanHoaDon}>
              Gán hóa đơn
            </Button>
          )}
          {/* "Đóng đơn" chỉ có nghĩa khi còn hàng chưa về. Server đòi `thu_mua:approve` + lý do;
              nút vẫn hiện cho người thiếu quyền để họ nhận đúng câu báo thay vì không thấy lối. */}
          {canUpdate && canApprove && row.status === "partially_received" && (
            <Button type="button" variant="ghost" onClick={onDongDon}>
              Đóng đơn
            </Button>
          )}
          {ghiDuoc && (
            // Nút CAM DUY NHẤT của hộp thoại Chi tiết phiếu (xem chú thích ở ContractBlock):
            // ghi đợt giao là việc chính của màn và là đường duy nhất sinh công nợ.
            <Button
              type="button"
              variant="accent"
              onClick={() => onGhiDot(null)}
            >
              Ghi đợt giao
            </Button>
          )}
        </div>
      </header>

      {dots.length === 0 ? (
        <p className="pdot__empty">
          <strong>Chưa ghi đợt giao nào.</strong>{" "}
          {ghiDuoc
            ? "Hàng về đợt nào thì ghi đợt đó — công nợ chỉ phát sinh theo số đã ghi ở đây."
            : row.status === "received"
              ? "Đơn này đã chốt nhận hàng theo đường cũ (không theo dõi theo đợt)."
              : "Đơn phải ở trạng thái Đang mua thì mới ghi được đợt giao."}
        </p>
      ) : (
        // Cuộn ngang trong KHUNG RIÊNG của bảng: 8 cột trên drawer 960px là chật, nhưng để cả
        // trang cuộn ngang thì hỏng cả màn (laptop-first).
        <div className="pdot__tablewrap">
        <table className="pay-table pdot__table">
          <thead>
            <tr>
              <th>Đợt</th>
              <th>Ngày giao</th>
              <th>Hàng nhận</th>
              <th className="pay-num">Thành tiền</th>
              <th>Hóa đơn</th>
              <th>Hạn trả</th>
              <th className="pay-num">Đã trả</th>
              {/* Cột nút không có nhãn nhìn thấy được, nhưng `<th>` rỗng thì trình đọc màn hình
                  đọc ra một ô câm — phải có `aria-label`. */}
              {canUpdate && <th aria-label="Thao tác" />}
            </tr>
          </thead>
          <tbody>
            {dots.map((dot) => {
              const khoa = dot.paid_amount > 0;
              return (
                <tr key={dot.id}>
                  <td>
                    {/* Ai khai đợt này nằm ở tooltip chứ không thành cột: đợt giao đẻ ra công nợ
                        nên phải truy được người khai, nhưng nó là câu hỏi hiếm — chiếm một cột
                        thường trực là đẩy cột TIỀN ra khỏi tầm mắt ở 1440px. */}
                    <strong
                      title={
                        dot.created_by_name
                          ? `${dot.created_by_name} ghi ngày ${fmtDate(dot.created_at)}`
                          : undefined
                      }
                    >
                      Đợt {dot.seq_no}
                    </strong>
                  </td>
                  <td>{fmtDate(dot.delivery_date)}</td>
                  <td>
                    {/* Thu gọn: 2 mặt hàng đầu + "…và N nữa". Đổ hết ra là bảng cao gấp ba mà
                        vẫn không ai đọc từng dòng ở đây — chi tiết nằm trong hộp Sửa đợt. */}
                    {dot.lines
                      .slice(0, 2)
                      .map(
                        (l) =>
                          `${l.item_name} ${l.quantity.toLocaleString("vi-VN")} ${l.unit}`,
                      )
                      .join(", ")}
                    {dot.lines.length > 2 && (
                      <small>…và {dot.lines.length - 2} mặt hàng nữa</small>
                    )}
                  </td>
                  <td className="pay-num">
                    <strong>{money(dot.amount)}</strong>
                  </td>
                  <td>
                    {dot.invoice_number ? (
                      <>
                        <strong>{dot.invoice_number}</strong>
                        {dot.invoice_date && (
                          <small>{fmtDate(dot.invoice_date)}</small>
                        )}
                      </>
                    ) : (
                      <small className="pdot__muted">chưa gán</small>
                    )}
                    {/* Có ảnh hoá đơn hay chưa — nhìn được ngay từ bảng, khỏi mở từng đợt ra dò.
                        Chỉ NHẮC, không chặn: hoá đơn về muộn là chuyện thường. */}
                    {(() => {
                      const n = row.attachments.filter(
                        (a) => a.delivery_id === dot.id && a.kind === "hoa_don",
                      ).length;
                      return n > 0 ? (
                        <span className="pdot__clip">📎 {n}</span>
                      ) : null;
                    })()}
                  </td>
                  <td>
                    {dot.chua_dat_han ? (
                      // Đợt không có hạn thì KHÔNG BAO GIỜ vào cột Quá hạn ở màn Công nợ — nói ra
                      // ngay đây để người thu mua đi khai "Số ngày cho nợ" cho NCC.
                      <span className="pay-badge pay-badge--warn">
                        Chưa đặt hạn
                      </span>
                    ) : (
                      fmtDate(dot.due_date)
                    )}
                  </td>
                  <td className="pay-num">
                    {dot.paid_amount > 0 ? (
                      money(dot.paid_amount)
                    ) : (
                      <small className="pdot__muted">—</small>
                    )}
                  </td>
                  {canUpdate && (
                    <td className="pay-num">
                      {/* Đợt ĐÃ CÓ PHIẾU CHI thì server cấm sửa/xoá — tiền đã ra thì không được
                          đổi số hàng dưới chân nó. Hiện KHOÁ ngay ở đây chứ không bày nút rồi để
                          người dùng gõ xong cả form mới ăn lỗi. */}
                      <div className="pdot__rowbtns">
                        {/* 🔌 NỐI SANG PHÂN HỆ KHO (chủ 07/08/2026: *"cho tôi cái nút Nhập kho…
                            để dev bên kho nó tự nối"*). HIỆN Ở MỌI ĐỢT, không riêng đợt đã chi
                            (*"cứ có đợt về là cho nhập kho"*): nhận hàng vào kho là sự kiện VẬT LÝ,
                            không phụ thuộc đã trả tiền. Bấm → nhảy sang màn Yêu cầu kho, mở sẵn form
                            NHẬP điền theo hàng đã nhận của đợt này. (Nối cứng qua `stock_voucher_id`
                            khi lập phiếu là bước sau — xem docs/prd-mua-hang-cong-no.md §11.) */}
                        <RowActionButton
                          dense
                          label="Nhập kho"
                          icon="warehouse"
                          onClick={() => onNhapKho(dot)}
                        />
                        {/* Đợt ĐÃ CÓ PHIẾU CHI thì server cấm sửa/xoá — tiền đã ra thì không được
                            đổi số hàng dưới chân nó. Hiện KHOÁ ngay ở đây chứ không bày nút rồi để
                            người dùng gõ xong cả form mới ăn lỗi. Nhưng NHẬP KHO thì vẫn cho. */}
                        {khoa ? (
                          <span
                            className="pdot__locked"
                            title="Đợt này đã có phiếu chi — huỷ phiếu chi trước rồi mới sửa/xoá được."
                          >
                            Đã chi — khoá
                          </span>
                        ) : (
                          <>
                            <RowActionButton
                              dense
                              label="Sửa đợt giao"
                              icon="pencil"
                              onClick={() => onGhiDot(dot)}
                            />
                            <RowActionButton
                              dense
                              danger
                              label="Xóa đợt giao"
                              icon="trash"
                              onClick={() => onXoaDot(dot)}
                            />
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {/* Dòng tổng: ba số của công thức công nợ, đặt cạnh nhau để không ai phải tự trừ trong đầu. */}
      <div className="pdot__totals">
        <span>
          Đã giao <b>{money(row.gia_tri_da_giao)}</b>
        </span>
        <span>
          Đã chi <b>{money(row.net_paid)}</b>
          {row.receipt_received_amount > 0 && (
            <small> (đã trừ {money(row.receipt_received_amount)} thu về)</small>
          )}
        </span>
        <span className="pdot__totals-due">
          Còn nợ <b>{money(row.outstanding_amount)}</b>
        </span>
      </div>
    </section>
  );
}

/** Một file hoá đơn ĐANG CHỜ tải lên. `url` là `blob:` để xem trước — rỗng với PDF (thẻ `<img>`
 *  không dựng được PDF, ô đó hiện icon thay vì ảnh) nên đừng cấp URL để rồi không dùng. */
type AnhCho = { file: File; url: string };

/**
 * GHI / SỬA MỘT ĐỢT GIAO — khai theo TỪNG DÒNG HÀNG (Đ4).
 *
 * Không có ô nhập tiền: thành tiền hiện ra là số CHỈ-ĐỌC, suy từ đơn giá đã chốt trên phiếu. NCC
 * tính khác đơn giá đặt thì sửa đơn giá trên phiếu rồi duyệt lại, đừng mở ô tiền ở đây.
 *
 * Trần mỗi dòng = số đặt − những gì các đợt KHÁC đã nhận. Khai vống là bơm thẳng vào công nợ một
 * món nợ chưa từng phát sinh; server chặn, đây chặn sớm và nói rõ còn bao nhiêu.
 */
function DeliveryDialog({
  row,
  delivery,
  onClose,
  onDone,
  onChanged,
}: {
  row: PurchaseRequestRow;
  delivery: PurchaseDeliveryRow | null;
  onClose: () => void;
  /** Lưu XONG đợt — cập nhật rồi ĐÓNG hộp. */
  onDone: (next: PurchaseRequestRow) => void;
  /** Đổi thứ gì đó mà hộp phải MỞ TIẾP (xoá một ảnh hoá đơn). Đóng hộp ở đây là người dùng mất
   *  hết những gì đang gõ dở chỉ vì bấm nhầm một cái ×. */
  onChanged: (next: PurchaseRequestRow) => void;
}) {
  const { token } = useAuth();
  const suaDot = delivery != null;

  const conLai = useCallback(
    (lineId: number) =>
      Math.max(
        0,
        row.lines.find((l) => l.id === lineId)!.quantity -
          daGiaoKhac(row, lineId, delivery?.id ?? null),
      ),
    [row, delivery],
  );

  const [ngayGiao, setNgayGiao] = useState(
    delivery?.delivery_date ?? todayInputValue(),
  );
  // Ô "Hạn trả" đang TẮT trên form (khối JSX bên dưới bị comment): hạn trả để hệ suy từ
  // `ngày giao + số ngày cho nợ của NCC`, không ai gõ tay nữa.
  //
  // Vẫn giữ biến này và vẫn GỬI LÊN: sửa một đợt đã có hạn khai tay trước đó mà gửi `null` là âm
  // thầm xoá mất hạn đó, và món nợ tụt khỏi cột Quá hạn không ai hay. Bật lại ô thì đổi dòng này
  // về `useState` là xong.
  const hanTra = delivery?.due_date ?? "";
  const [soHoaDon, setSoHoaDon] = useState(delivery?.invoice_number ?? "");
  const [ngayHoaDon, setNgayHoaDon] = useState(delivery?.invoice_date ?? "");
  const [ghiChu, setGhiChu] = useState(delivery?.note ?? "");
  // Ghi chú là ô HIẾM dùng ⇒ mặc định thu về một nút chữ. Nhưng đợt đang sửa mà ĐÃ có ghi chú thì
  // phải mở sẵn: giấu nó đi là người sửa không thấy câu cũ, và tưởng đợt này chưa ghi gì.
  const [moGhiChu, setMoGhiChu] = useState(() => (delivery?.note ?? "") !== "");
  // Chỉ tự đặt con trỏ khi NGƯỜI DÙNG bấm mở, không giật focus lúc hộp vừa hiện.
  const ghiChuMoSan = useRef(moGhiChu);
  // Ô số của TỪNG dòng đặt. Ghi đợt mới: điền sẵn phần CÒN LẠI ⇒ hàng về đủ thì chỉ bấm Lưu.
  // Không nhận món nào thì xoá trắng ô đó — dòng trống bị loại khỏi đợt.
  const [soNhan, setSoNhan] = useState<Record<number, string>>(() => {
    const out: Record<number, string> = {};
    for (const line of row.lines) {
      const cu = delivery?.lines.find(
        (dl) => dl.purchase_request_line_id === line.id,
      );
      if (suaDot) {
        out[line.id] = cu ? String(cu.quantity) : "";
      } else {
        // Đợt MỚI: không có đợt nào để bỏ qua, nên trừ hết những gì các đợt hiện có đã lấy.
        const con = line.quantity - daGiaoKhac(row, line.id, null);
        out[line.id] = con > 0 ? String(con) : "";
      }
    }
    return out;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Ảnh/PDF hoá đơn chụp ngay lúc ghi đợt. Phải GIỮ TRONG BỘ NHỚ rồi tải sau khi lưu: đợt chưa
  // tồn tại thì chưa có `delivery_id` để gắn file vào. Ghi đợt xong mới quay ra tìm nút đính kèm
  // là kiểu người ta quên — hoá đơn đang cầm trên tay lúc nhận hàng, không phải lúc mở lại phiếu.
  //
  // Mỗi file mang theo một `blob:` URL để hiện ẢNH THẬT ngay khi chọn: người nhận hàng phải soát
  // được con số trên tờ hoá đơn có đọc nổi không TRƯỚC khi lưu, chứ không phải sau khi tải xong.
  const [anhMoi, setAnhMoi] = useState<AnhCho[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [dangKeo, setDangKeo] = useState(false);
  // URL do `createObjectURL` cấp KHÔNG tự mất khi component chết — phải thu hồi tay, nếu không mỗi
  // lần mở/đóng hộp là rò một tấm ảnh. Ref chỉ để bản dọn lúc unmount thấy được danh sách mới nhất.
  const anhMoiRef = useRef<AnhCho[]>([]);
  useEffect(() => {
    anhMoiRef.current = anhMoi;
  }, [anhMoi]);
  useEffect(
    () => () => {
      for (const a of anhMoiRef.current) if (a.url) URL.revokeObjectURL(a.url);
    },
    [],
  );
  const anhDaCo = (delivery?.id ?? null) === null
    ? []
    : row.attachments.filter(
        (a) => a.delivery_id === delivery!.id && a.kind === "hoa_don",
      );

  // THÀNH TIỀN của đợt = Σ số lượng × đơn giá/CK/VAT đã chốt trên phiếu.
  //
  // KHÔNG có ô nhập tiền (chủ chốt 07/08/2026, đảo lại quyết định 06/08): *"không cho sửa nữa,
  // dựa vào số lượng thực tế tính ra tiền luôn"*. Ô gõ tay đẻ ra đúng cái lệch mà chính chủ bắt
  // được — chi tiết PMH hiện một số, ngoài bảng hiện số khác cho cùng một đợt.
  const tienDot = useMemo(
    () =>
      row.lines.reduce((sum, line) => {
        const qty = Number(soNhan[line.id]);
        return sum + (qty > 0 ? tienTheoSoLuong(line, qty) : 0);
      }, 0),
    [row.lines, soNhan],
  );

  /** Nhận file vào hàng chờ. Chặn ngay tại đây thay vì để server từ chối sau khi đợt đã lưu —
   *  lúc đó đợt đã tạo rồi mà người dùng chỉ thấy một câu báo lỗi, dễ ghi lại lần nữa. */
  function themAnh(list: FileList | null) {
    if (!list?.length) return;
    const nhan: AnhCho[] = [];
    for (const file of Array.from(list)) {
      const laAnh = file.type.startsWith("image/");
      if (!(laAnh || file.type === "application/pdf")) {
        setError(`"${file.name}": chỉ nhận ảnh hoặc PDF.`);
        continue;
      }
      if (file.size > 10 * 1024 * 1024) {
        setError(`"${file.name}": vượt quá 10 MB.`);
        continue;
      }
      nhan.push({ file, url: laAnh ? URL.createObjectURL(file) : "" });
    }
    if (nhan.length) setAnhMoi((cur) => [...cur, ...nhan]);
  }

  /** Bỏ một file khỏi hàng chờ — THU HỒI URL ngay tại đây, đừng đợi unmount: bỏ 10 tấm rồi mới
   *  đóng hộp là 10 tấm nằm lại trong bộ nhớ suốt phiên làm việc. */
  function boAnhCho(index: number) {
    setAnhMoi((cur) => {
      const bo = cur[index];
      if (bo?.url) URL.revokeObjectURL(bo.url);
      return cur.filter((_, j) => j !== index);
    });
  }

  async function xoaAnh(attachmentId: number) {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      onChanged(await api.purchaseRequests.deleteAttachment(token, row.id, attachmentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không xóa được ảnh.");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!token || busy) return;
    const lines = row.lines
      .map((line) => ({
        purchase_request_line_id: line.id,
        quantity: Number(soNhan[line.id]),
      }))
      .filter((l) => Number.isFinite(l.quantity) && l.quantity > 0);
    if (lines.length === 0) {
      setError(
        "Đợt giao phải có ít nhất một dòng hàng. Không nhận món nào thì đừng ghi đợt.",
      );
      return;
    }
    const vuot = lines.find((l) => l.quantity > conLai(l.purchase_request_line_id) + 1e-9);
    if (vuot) {
      const line = row.lines.find((x) => x.id === vuot.purchase_request_line_id)!;
      setError(
        `"${line.item_name}": nhận ${vuot.quantity} nhưng chỉ còn ${conLai(line.id)} chưa giao ` +
          `(đặt ${line.quantity}). Nhận dư thì sửa số đặt trên phiếu rồi duyệt lại.`,
      );
      return;
    }
    if (!ngayGiao) {
      setError("Đợt giao phải có ngày giao.");
      return;
    }
    if (hanTra && hanTra < ngayGiao) {
      setError("Hạn trả không được trước ngày giao.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = {
        delivery_date: ngayGiao,
        due_date: hanTra || null,
        invoice_number: soHoaDon.trim() || null,
        invoice_date: ngayHoaDon || null,
        note: ghiChu.trim() || null,
        lines,
      };
      let sau = suaDot
        ? await api.purchaseRequests.updateDelivery(
            token,
            row.id,
            delivery!.id,
            payload,
          )
        : await api.purchaseRequests.createDelivery(token, row.id, payload);

      if (anhMoi.length > 0) {
        // Đợt VỪA tạo là đợt có `seq_no` lớn nhất trong kết quả trả về — server đánh số tăng dần
        // trong phạm vi phiếu. Không dò theo id vì id do DB cấp, giao diện không đoán được.
        const dotId = suaDot
          ? delivery!.id
          : sau.deliveries.reduce(
              (max, d) => (d.seq_no > max.seq_no ? d : max),
              sau.deliveries[0],
            )?.id;
        if (dotId != null) {
          for (const { file } of anhMoi) {
            sau = await api.purchaseRequests.uploadAttachment(
              token,
              row.id,
              file,
              "hoa_don",
              dotId,
            );
          }
        }
      }
      onDone(sau);
    } catch (err) {
      // ĐỢT ĐÃ LƯU rồi mới hỏng ở khâu tải ảnh thì KHÔNG được nói "không lưu được đợt giao" —
      // người dùng sẽ ghi lại lần nữa và đẻ đợt trùng.
      setError(
        err instanceof ApiError ? err.message : "Không lưu được đợt giao.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      wide
      // Mã phiếu vào THẲNG tiêu đề. Đoạn văn dẫn nhập cũ đã bị bỏ: ba câu trong đó lặp lại đúng
      // những gì nhãn vùng, dòng gợi ý và dải "Ghi vào công nợ" bên dưới đã nói.
      title={
        suaDot
          ? `Sửa đợt ${delivery!.seq_no} · ${row.code}`
          : `Ghi đợt giao · ${row.code}`
      }
      confirmLabel={suaDot ? "Lưu đợt giao" : "Ghi đợt giao"}
      busy={busy}
      // Lỗi tự render ở ĐẦU children (ngay dưới đây). ConfirmDialog đặt `error` SAU children, mà
      // hộp này dài hơn một màn ⇒ báo lỗi rơi xuống đáy vùng cuộn, ngoài tầm mắt người vừa bấm Lưu.
      error={null}
      onConfirm={submit}
      onCancel={onClose}
    >
      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      {/* VÙNG 1 — HÀNG NHẬN. Ngày giao nằm ngay trên bảng vì nó là ngày của CHÍNH những dòng
          hàng này, không phải một ô hành chính rời rạc. */}
      <section className="pdot__sec">
        <div className="pdot__sechead">
          <span className="pdot__sectitle">Hàng nhận đợt này</span>
          <label className="pdot__inline">
            <span>
              Ngày giao <span className="purchase__required-star">*</span>
            </span>
            {/* Chặn TƯƠNG LAI: ngày giao là mốc tính hạn trả, gõ nhầm sang tháng sau là món nợ biến
                khỏi cột Quá hạn. Quá khứ vẫn cho — hàng về hôm qua mới ghi hôm nay là chuyện thường. */}
            <input
              className="input"
              type="date"
              max={todayInputValue()}
              value={ngayGiao}
              onChange={(e) => setNgayGiao(e.target.value)}
            />
          </label>
        </div>
        {/* Ô "Hạn trả" TẮT có chủ ý (hạn trả để hệ suy từ ngày giao + số ngày cho nợ của NCC).
            Biến `hanTra` vẫn được gửi lên — xem khai báo state ở đầu component. Giữ nguyên khối
            dưới đây để bật lại được, đừng xoá: */}
        {/* <label className="purchase__field">
          <span>Hạn trả</span>
          <input
            className="input"
            type="date"
            min={ngayGiao || undefined}
            value={hanTra}
            onChange={(e) => setHanTra(e.target.value)}
          />
          <small className="pdot__hint">
            Bỏ trống = lấy ngày giao + số ngày cho nợ của nhà cung cấp. NCC chưa
            khai số ngày thì đợt này <strong>không vào cột Quá hạn</strong>.
          </small>
        </label> */}
        <div className="pdot__tablecard">
          <table className="pdot__linetable">
            <colgroup>
              <col />
              <col className="pdot__c2" />
              <col className="pdot__c3" />
              <col className="pdot__c4" />
            </colgroup>
            <thead>
              <tr>
                <th>Vật tư</th>
                <th className="pdot__num">Đặt</th>
                <th className="pdot__num">Chưa giao</th>
                {/* KHÔNG có cột tiền theo dòng. Tiền của đợt là MỘT số ở ô "Số tiền theo hóa
                    đơn" bên dưới — hoá đơn ghi một số tổng, không tách theo mặt hàng. Cột tiền ở đây
                    chỉ lặp lại con số đã nằm trong dòng gợi ý dưới ô đó, và tệ hơn: nó trông như số
                    chính thức trong khi không phải. */}
                <th className="pdot__num">Thực nhận</th>
              </tr>
            </thead>
            <tbody>
              {row.lines.map((line) => {
                const con = conLai(line.id);
                return (
                  <tr key={line.id}>
                    <td>
                      {line.item_name}
                      <small>{money(line.expected_unit_price)}/{line.unit}</small>
                    </td>
                    <td className="pdot__num">
                      {line.quantity.toLocaleString("vi-VN")} {line.unit}
                    </td>
                    <td className="pdot__num">
                      {con > 0 ? (
                        `${con.toLocaleString("vi-VN")} ${line.unit}`
                      ) : (
                        <small className="pdot__muted">đã giao đủ</small>
                      )}
                    </td>
                    <td className="pdot__num">
                      <span className="pdot__qtywrap">
                        <input
                          className="input pdot__qty"
                          type="number"
                          min={0}
                          max={con}
                          step="any"
                          value={soNhan[line.id] ?? ""}
                          onChange={(e) =>
                            setSoNhan((cur) => ({
                              ...cur,
                              [line.id]: e.target.value,
                            }))
                          }
                        />
                        <span className="pdot__unit">{line.unit}</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* VÙNG 2 — TIỀN. CHỈ ĐỌC: tiền của đợt do máy tính từ số lượng × đơn giá đã chốt trên
          phiếu, không ai gõ tay. Vẫn để nó thành một dải riêng cỡ lớn vì đây là con số ĐI VÀO
          CÔNG NỢ — người khai phải thấy ngay hậu quả của số lượng mình vừa gõ. */}
      <div className="pdot__moneybar pdot__moneybar--auto">
        <span className="pdot__moneynote">
          Tính theo số lượng thực nhận × đơn giá đã chốt trên phiếu mua.
        </span>
        <div className="pdot__result">
          <span className="pdot__resultlabel">Ghi vào công nợ</span>
          <span className="pdot__resultrow">
            <span className="pdot__resultnum">{money(tienDot)}</span>
          </span>
        </div>
      </div>

      {/* VÙNG 3 — HÓA ĐƠN: số, ngày và ẢNH là MỘT nhóm. Ảnh chụp ngay lúc nhận hàng — đó là lúc
          tờ hoá đơn đang cầm trên tay. Bắt quay lại phiếu tìm nút đính kèm là kiểu người ta quên. */}
      <section className="pdot__sec">
        <div className="pdot__sechead">
          <span className="pdot__sectitle">Hóa đơn</span>
          <span className="pdot__secnote">có thể bổ sung sau</span>
        </div>
        <div className="pdot__invgrid">
          <label className="purchase__field">
            <span>Số hóa đơn</span>
            <input
              className="input"
              maxLength={64}
              value={soHoaDon}
              onChange={(e) => setSoHoaDon(e.target.value)}
              placeholder="Chưa có thì để trống"
            />
          </label>
          <label className="purchase__field">
            <span>Ngày hóa đơn</span>
            <input
              className="input"
              type="date"
              max={todayInputValue()}
              value={ngayHoaDon}
              onChange={(e) => setNgayHoaDon(e.target.value)}
            />
          </label>
          {/* Ô chọn file dựng theo mẫu `.nqr-picker` của màn Nội quy: input thật ẩn đi, cái người
              dùng thấy là một nút — và nút đó CŨNG là vùng thả. Kéo thả gọi lại đúng `themAnh` nên
              luật ảnh/PDF + 10 MB chỉ tồn tại ở một chỗ. */}
          <input
            type="file"
            hidden
            multiple
            accept="image/*,application/pdf"
            ref={fileRef}
            onChange={(e) => {
              themAnh(e.target.files);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className={`pdot__pick${dangKeo ? " is-drop" : ""}`}
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDangKeo(true);
            }}
            onDragLeave={(e) => {
              if (e.target === e.currentTarget) setDangKeo(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setDangKeo(false);
              if (!busy) themAnh(e.dataTransfer.files);
            }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              focusable="false"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <path d="M17 8l-5-5-5 5" />
              <path d="M12 3v12" />
            </svg>
            {anhDaCo.length + anhMoi.length > 0
              ? "Thêm ảnh"
              : "Chọn ảnh hóa đơn / kéo vào đây"}
          </button>
        </div>
        <small className="pdot__hint">Ảnh hoặc PDF, tối đa 10 MB mỗi file.</small>
        {(anhDaCo.length > 0 || anhMoi.length > 0) && (
          <div className="pdot__filegrid">
            {anhDaCo.map((a) => (
              <div className="pdot__file" key={a.id}>
                <a
                  href={assetUrl(a.file_url) ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                  title={a.file_name}
                >
                  {ATTACHMENT_IMAGE_TYPES.includes(a.file_type ?? "") ? (
                    <img
                      className="pdot__thumb"
                      src={assetUrl(a.file_url) ?? ""}
                      alt={a.file_name}
                    />
                  ) : (
                    <span className="pdot__thumb pdot__thumb--pdf">
                      <Icon name="fileText" size={22} />
                    </span>
                  )}
                </a>
                <button
                  type="button"
                  className="pdot__filex"
                  aria-label={`Xóa ${a.file_name}`}
                  disabled={busy}
                  onClick={() => xoaAnh(a.id)}
                >
                  ×
                </button>
              </div>
            ))}
            {anhMoi.map((a, i) => (
              <div className="pdot__file" key={`${a.file.name}-${i}`}>
                {/* Xem trước ẢNH THẬT, không phải tên file: người nhận hàng cần soát con số trên
                    tờ hoá đơn có đọc nổi không TRƯỚC khi lưu. Viền đứt + pill để không ai nhầm
                    tấm chờ tải với tấm đã nằm trên máy chủ. */}
                {a.url ? (
                  <img
                    className="pdot__thumb pdot__thumb--cho"
                    src={a.url}
                    alt={a.file.name}
                    title={a.file.name}
                  />
                ) : (
                  <span
                    className="pdot__thumb pdot__thumb--pdf pdot__thumb--cho"
                    title={a.file.name}
                  >
                    <Icon name="fileText" size={22} />
                  </span>
                )}
                <span className="pdot__tilebadge">chờ tải lên</span>
                <button
                  type="button"
                  className="pdot__filex"
                  aria-label={`Bỏ ${a.file.name}`}
                  disabled={busy}
                  onClick={() => boAnhCho(i)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* VÙNG 4 — GHI CHÚ: ô hiếm dùng nên mặc định thu về một nút chữ, đừng chiếm chỗ của thứ
          ngày nào cũng phải gõ. */}
      {moGhiChu ? (
        <label className="pdot__notewrap">
          <span>Ghi chú đợt</span>
          <input
            className="input"
            autoFocus={!ghiChuMoSan.current}
            value={ghiChu}
            onChange={(e) => setGhiChu(e.target.value)}
            placeholder="Ví dụ: giao tại kho 2, thiếu 3 ram bù sau."
          />
        </label>
      ) : (
        <button
          type="button"
          className="pdot__notebtn"
          onClick={() => setMoGhiChu(true)}
        >
          + Ghi chú đợt
        </button>
      )}
    </ConfirmDialog>
  );
}

/**
 * GÁN MỘT HOÁ ĐƠN CHO NHIỀU ĐỢT.
 *
 * Ca thật: NCC giao ba đợt rồi mới xuất một hoá đơn chung. Không có thao tác này thì kế toán phải
 * mở sửa từng đợt và gõ lại cùng một số ba lần — gõ lệch một ký tự là hệ hiểu thành ba hoá đơn.
 */
function InvoiceDialog({
  row,
  onClose,
  onDone,
}: {
  row: PurchaseRequestRow;
  onClose: () => void;
  onDone: (next: PurchaseRequestRow) => void;
}) {
  const { token } = useAuth();
  const [chon, setChon] = useState<number[]>(() =>
    row.deliveries.filter((d) => !d.invoice_number).map((d) => d.id),
  );
  const [so, setSo] = useState("");
  const [ngay, setNgay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!token || busy) return;
    if (chon.length === 0) {
      setError("Chưa chọn đợt giao nào để gán hóa đơn.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        await api.purchaseRequests.assignInvoice(token, row.id, {
          delivery_ids: chon,
          invoice_number: so.trim() || null,
          invoice_date: ngay || null,
        }),
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Không gán được hóa đơn.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      title="Gán hóa đơn cho nhiều đợt"
      message={`Phiếu ${row.code} — các đợt được chọn sẽ mang CÙNG một số hóa đơn. Để trống số hóa đơn là gỡ hóa đơn khỏi các đợt đó.`}
      confirmLabel="Gán hóa đơn"
      busy={busy}
      error={error}
      onConfirm={submit}
      onCancel={onClose}
    >
      <div className="pdot__form">
        <label className="purchase__field">
          <span>Số hóa đơn</span>
          <input
            className="input"
            maxLength={64}
            autoFocus
            value={so}
            onChange={(e) => setSo(e.target.value)}
          />
        </label>
        <label className="purchase__field">
          <span>Ngày hóa đơn</span>
          <input
            className="input"
            type="date"
            max={todayInputValue()}
            value={ngay}
            onChange={(e) => setNgay(e.target.value)}
          />
        </label>
      </div>
      <table className="pay-table">
        <thead>
          <tr>
            {/* Cột ô chọn — `<th>` rỗng là ô câm với trình đọc màn hình, phải có `aria-label`. */}
            <th aria-label="Chọn đợt giao" />
            <th>Đợt</th>
            <th>Ngày giao</th>
            <th>Hóa đơn hiện tại</th>
            <th className="pay-num">Thành tiền</th>
          </tr>
        </thead>
        <tbody>
          {row.deliveries.map((dot) => (
            <tr key={dot.id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={`Chọn đợt ${dot.seq_no}`}
                  checked={chon.includes(dot.id)}
                  onChange={(e) =>
                    setChon((cur) =>
                      e.target.checked
                        ? [...cur, dot.id]
                        : cur.filter((id) => id !== dot.id),
                    )
                  }
                />
              </td>
              <td>
                <strong>Đợt {dot.seq_no}</strong>
              </td>
              <td>{fmtDate(dot.delivery_date)}</td>
              <td>
                {dot.invoice_number ?? (
                  <small className="pdot__muted">chưa gán</small>
                )}
              </td>
              <td className="pay-num">{money(dot.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ConfirmDialog>
  );
}

function StatusBadge({ status }: { status: PurchaseRequestStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>
      {meta.label}
    </span>
  );
}

function SourceStatusBadge({
  status,
}: {
  status: DepartmentPurchaseRequestStatus;
}) {
  const meta = SOURCE_STATUS_META[status];
  return (
    <span className={`purchase__status purchase__status--${meta.tone}`}>
      {meta.label}
    </span>
  );
}

function LocalField({
  label,
  wide = false,
  required = false,
  children,
}: {
  label: string;
  wide?: boolean;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`purchase__field${wide ? " md-page__form-wide" : ""}`}>
      <span>
        {label}
        {required && <span className="purchase__required-star"> *</span>}
      </span>
      {children}
    </label>
  );
}
