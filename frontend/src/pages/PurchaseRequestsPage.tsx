import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  type DepartmentPurchaseRequestRow,
  type DepartmentPurchaseRequestStatus,
  type PurchaseRequestInput,
  type PurchaseRequestLineInput,
  type PurchaseRequestRow,
  type PurchaseRequestStatus,
  type SupplierRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import type { NavigateFn } from "../components/AppShell";
import { CodeLink } from "../components/CodeLink";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DetailModal } from "../components/DetailModal";
import { RowActionButton } from "../components/RowActionButton";
import { fmtDate, money } from "../utils/format";
import "./master-data.css";
import "./purchase.css";

const PAGE_SIZE = 10;
const SOURCE_PAGE_SIZE = 20;

const STATUS_META: Record<
  PurchaseRequestStatus,
  { label: string; tone: string }
> = {
  draft: { label: "Nháp", tone: "draft" },
  pending_approval: { label: "Chờ duyệt", tone: "pending" },
  approved: { label: "Đã duyệt", tone: "approved" },
  rejected: { label: "Từ chối", tone: "rejected" },
  purchased: { label: "Đã mua", tone: "purchased" },
  received: { label: "Đã nhận", tone: "received" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

type StatusFilter = "all" | PurchaseRequestStatus;
type SourceStatusFilter = "all" | DepartmentPurchaseRequestStatus;

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
type FormLine = PurchaseRequestLineInput & { supplier_id?: number | null };

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
    purpose: "",
    needed_date: "",
    expected_receipt_date: "",
    note: "",
    lines: [emptyLine()],
  };
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
    purpose: row.purpose ?? "",
    needed_date: row.needed_date ?? "",
    expected_receipt_date: row.expected_receipt_date ?? "",
    note: row.note ?? "",
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

function html(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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
  <title>In phiếu mua hàng ${html(row.code)}</title>
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

  <h1>Phiếu mua hàng</h1>
  <div class="code">Mã phiếu: ${html(row.code)}</div>

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
    <div style="grid-column: 1 / -1;"><span class="label">Mục đích</span>${html(row.purpose || "—")}</div>
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

  ${row.note ? `<section class="note"><span class="label">Ghi chú</span>${html(row.note)}</section>` : ""}

</body>
</html>`);
  win.document.close();
  win.focus();
  window.setTimeout(() => win.print(), 250);
  return true;
}

export function PurchaseRequestsPage({ navigate }: { navigate: NavigateFn }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("thu_mua", "create");
  const openYcmh = (code: string) =>
    navigate("yeu-cau-mua-hang", { focusRequestCode: code });
  const canUpdate = can("thu_mua", "update");
  // KHÔNG còn `canApprove` ở màn này: duyệt đơn mua đã chuyển sang Kế toán thu mua (04/08/2026).
  //
  // ⚠️ Hộp "Lý do từ chối" (`reasonModal.kind === "reject"`) vẫn còn trong file nhưng KHÔNG CÒN AI
  // BẤM — chỉ nhánh `cancel` còn chạy. Giữ tạm để chép sang màn Đơn mua hàng; chép xong thì dọn,
  // đừng để nó nằm lại làm người đọc sau tưởng màn này vẫn từ chối được.
  const canDelete = can("thu_mua", "delete");
  const canCancel = can("thu_mua", "cancel");

  const [rows, setRows] = useState<PurchaseRequestRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [sourceRows, setSourceRows] = useState<DepartmentPurchaseRequestRow[]>(
    [],
  );
  const [sourceTotal, setSourceTotal] = useState(0);
  const [sourceQ, setSourceQ] = useState("");
  const [sourceStatus, setSourceStatus] = useState<SourceStatusFilter>("all");
  const [sourceLoading, setSourceLoading] = useState(true);
  const [sourcePage, setSourcePage] = useState(1);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
  const [reasonModal, setReasonModal] = useState<null | {
    kind: "cancel" | "reject";
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

  const loadSources = useCallback(() => {
    if (!token) return;
    setSourceLoading(true);
    api.departmentPurchaseRequests
      .list(token, {
        q: sourceQ.trim() || undefined,
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
      })
      .finally(() => setSourceLoading(false));
  }, [token, sourceQ, sourceStatus, sourcePage]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.purchaseRequests
      .list(token, {
        q: q.trim() || undefined,
        status: status === "all" ? null : status,
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
        else setError("Không tải được danh sách phiếu mua hàng.");
      })
      .finally(() => setLoading(false));
  }, [token, q, status, page]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    load();
  }, [load]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const sourceTotalPages = Math.max(
    1,
    Math.ceil(sourceTotal / SOURCE_PAGE_SIZE),
  );
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
      setError("Chỉ lập phiếu mua hàng từ yêu cầu đang chờ Thu mua xử lý.");
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
      purpose: source.purpose,
      needed_date: source.needed_date ?? "",
      expected_receipt_date: "",
      note: "",
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
      purpose: (input.purpose ?? "").trim(),
      needed_date: (input.needed_date ?? "").trim(),
      expected_receipt_date: trimOptional(input.expected_receipt_date),
      note: trimOptional(input.note),
      lines: input.lines.map((line) => ({
        item_name: (line.item_name ?? "").trim(),
        unit: (line.unit ?? "").trim(),
        quantity: Number(line.quantity),
        expected_unit_price: Math.round(Number(line.expected_unit_price) || 0),
        discount_percent: Number(line.discount_percent) || 0,
        vat_percent: Number(line.vat_percent) || 0,
        note: trimOptional(line.note),
        supplier_id: line.supplier_id ?? null,
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
      !payload.purpose ? "Mục đích" : "",
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
      setFormError("Mỗi phiếu mua hàng chỉ được lập từ 1 yêu cầu mua hàng.");
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
          purpose: payload.purpose,
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
          })),
        });
        setRows((current) => [...items, ...current]);
        setTotal((t) => t + items.length);
      }
      setMode(null);
      loadSuppliers();
      loadSources();
    } catch (err) {
      if (err instanceof ApiError) setFormError(err.message);
      else setFormError("Không lưu được phiếu mua hàng.");
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
    setActionBusy(`${kind}:${row.id}`);
    setReasonModal({ ...reasonModal, error: null });
    try {
      const next =
        kind === "reject"
          ? await api.purchaseRequests.reject(token, row.id, reason.trim())
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
            label="Đã mua"
            icon="bag"
            loading={busy("purchased")}
            onClick={() =>
              runAction(row, "purchased", () =>
                api.purchaseRequests.markPurchased(token!, row.id),
              )
            }
          />
        )}
        {canUpdate && row.status === "purchased" && (
          <RowActionButton
            dense={dense}
            label="Đã nhận"
            icon="packageCheck"
            loading={busy("received")}
            onClick={() =>
              runAction(row, "received", () =>
                api.purchaseRequests.markReceived(token!, row.id),
              )
            }
          />
        )}
        {canCancel &&
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
          )}
        {canDelete && row.status === "draft" && (
          <RowActionButton
            dense={dense}
            label="Xóa"
            icon="trash"
            danger
            onClick={() => setDeleting(row)}
          />
        )}
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

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Thu mua</p>
        <h1 className="md-page__title">Mua hàng</h1>
        <p className="md-page__sub">
          Bộ phận mua hàng lập PMH từ YCMH, gửi người có quyền duyệt, sau đó
          theo dõi đã mua và đã nhận hàng.
        </p>
      </header>

      <section className="card md-page__tablewrap purchase__source-inbox">
        <div className="purchase__source-head">
          <div>
            <p className="eyebrow">Yêu cầu từ phòng ban</p>
            <h2>Danh sách chờ Thu mua xử lý</h2>
          </div>
        </div>

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
            <Button type="submit" variant="ghost">
              Tìm
            </Button>
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
              <tr>
                <td colSpan={6} className="md-page__status">
                  Đang tải yêu cầu...
                </td>
              </tr>
            ) : sourceRows.length === 0 ? (
              <tr>
                <td colSpan={6} className="md-page__empty">
                  Chưa có yêu cầu mua từ phòng ban.
                </td>
              </tr>
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
                      <div className="md-page__muted">{row.purpose}</div>
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
                          Tạo phiếu
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
          </span>
          {sourceTotalPages > 1 && (
            <div className="md-page__pager-btns">
              <Button
                variant="ghost"
                disabled={sourcePage <= 1}
                onClick={() => setSourcePage((value) => value - 1)}
              >
                Trước
              </Button>
              <span className="md-page__muted">
                Trang {sourcePage}/{sourceTotalPages}
              </span>
              <Button
                variant="ghost"
                disabled={sourcePage >= sourceTotalPages}
                onClick={() => setSourcePage((value) => value + 1)}
              >
                Sau
              </Button>
            </div>
          )}
        </div>
      </section>

      <div className="md-page__toolbar">
        <form
          className="md-page__search"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            load();
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
          <Button type="submit" variant="ghost">
            Tìm
          </Button>
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
        <div className="md-page__toolbar-spacer" />
      </div>

      {error && (
        <div className="banner banner--error" role="alert">
          {error}
        </div>
      )}

      <section className="card md-page__tablewrap purchase__list">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã phiếu</th>
              <th>Trạng thái</th>
              <th>Nhà cung cấp</th>
              <th>Cần / Dự kiến nhận</th>
              <th>Tổng dự kiến</th>
              <th>Người tạo / duyệt</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="md-page__status">
                  Đang tải dữ liệu...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="md-page__empty">
                  Chưa có phiếu mua hàng phù hợp.
                </td>
              </tr>
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
                      {row.purpose || "—"}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={row.status} />
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
      </section>

      {selected && (
        <DetailModal
          kicker="Chi tiết phiếu"
          title={selected.code}
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
          {selected.note && (
            <div className="purchase__note">{selected.note}</div>
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
        </DetailModal>
      )}

      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng số: {total} phiếu · Trang {page}/{totalPages}
          </span>
          <div className="md-page__pager-btns">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Trước
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Sau
            </button>
          </div>
        </div>
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
                {mode === "edit" ? "Sửa phiếu mua hàng" : "Tạo phiếu mua hàng"}
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
                <LocalField label="Mục đích" wide required>
                  <input
                    className="input"
                    required
                    value={form.purpose ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, purpose: e.target.value })
                    }
                    placeholder="Ví dụ: mua giấy cho đơn hàng..."
                  />
                </LocalField>
                <LocalField label="Ghi chú" wide>
                  <textarea
                    className="input purchase__textarea"
                    value={form.note ?? ""}
                    onChange={(e) => setForm({ ...form, note: e.target.value })}
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
                    Sẽ tạo <strong>{phieuSeTao.length} phiếu</strong> —{" "}
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
                  Lưu phiếu
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
        title={reasonModal?.kind === "reject" ? "Từ chối phiếu?" : "Hủy phiếu?"}
        message={reasonModal ? `Phiếu ${reasonModal.row.code}` : undefined}
        danger
        confirmLabel={reasonModal?.kind === "reject" ? "Từ chối phiếu" : "Hủy phiếu"}
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
            {reasonModal?.kind === "reject" ? "Lý do từ chối" : "Lý do / ghi chú"}
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
    </main>
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
