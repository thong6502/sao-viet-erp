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
  type DepartmentPurchaseSourceType,
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

const SOURCE_TYPE_LABELS: Record<DepartmentPurchaseSourceType, string> = {
  kinh_doanh: "Kinh doanh",
  kho: "Kho",
  san_xuat: "Sản xuất",
  cong_nghe: "Công nghệ",
  gia_cong_ngoai: "Gia công ngoài",
  khac: "Khác",
};

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

function emptyLine(): PurchaseRequestLineInput {
  return {
    item_name: "",
    unit: "",
    quantity: 0,
    expected_unit_price: 0,
    discount_percent: 0,
    vat_percent: 0,
    note: "",
  };
}

function emptyRequest(): PurchaseRequestInput {
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

function fromRequest(row: PurchaseRequestRow): PurchaseRequestInput {
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
    <div><span class="label">Yêu cầu nguồn</span>${html(sourceCodes)}</div>
    <div><span class="label">Bộ phận/người yêu cầu</span>${html(sourceDepartments || "Nội bộ")}</div>
    <div><span class="label">Người lập</span>${html(row.created_by_name || "—")}</div>
    <div><span class="label">Kế toán duyệt</span>${html(row.approved_by_name || "Chưa duyệt")}</div>
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
  // Lưu CẢ object (không chỉ id) để tick vẫn giữ khi lật sang trang khác — một
  // phiếu mua có thể gom YCMH nằm ở nhiều trang.
  const [checkedSources, setCheckedSources] = useState<
    DepartmentPurchaseRequestRow[]
  >([]);

  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [mode, setMode] = useState<null | "create" | "edit">(null);
  const [editing, setEditing] = useState<PurchaseRequestRow | null>(null);
  const [form, setForm] = useState<PurchaseRequestInput>(emptyRequest());
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<PurchaseRequestRow | null>(null);
  const [reasonModal, setReasonModal] = useState<null | {
    kind: "cancel";
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
        // Giữ tick xuyên trang: một YCMH đang tick chỉ bị bỏ khi trang hiện tại
        // cho thấy nó đã rời trạng thái "open" (đã được gom/hủy); nếu không xuất
        // hiện ở trang này thì nó đang ở trang khác → giữ nguyên.
        setCheckedSources((current) =>
          current.filter((picked) => {
            const fresh = res.items.find((row) => row.id === picked.id);
            return !fresh || fresh.status === "open";
          }),
        );
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
  // Lựa chọn tích lũy across trang — chính là danh sách gom vào phiếu mua.
  const selectedSources = checkedSources;
  // Gộp trang hiện tại với các YCMH đã tick ở trang khác — nếu không, phiếu gom
  // xuyên trang sẽ thiếu ô chọn cho những YCMH nằm ngoài trang đang xem.
  const formSourceRows = useMemo(() => {
    const pool = new Map<number, DepartmentPurchaseRequestRow>();
    for (const row of sourceRows) pool.set(row.id, row);
    for (const row of checkedSources) pool.set(row.id, row);
    return [...pool.values()].filter(
      (row) =>
        row.status === "open" || form.source_request_ids.includes(row.id),
    );
  }, [sourceRows, checkedSources, form.source_request_ids]);

  // Chỉ thay dòng trong danh sách, KHÔNG đụng selectedId: các nút thao tác nằm ở
  // bảng, chọn dòng ở đây sẽ tự bung popup chi tiết. Popup đang mở thì `selected`
  // tự lấy lại dòng mới từ `rows`.
  function updateRow(next: PurchaseRequestRow) {
    setRows((current) =>
      current.map((row) => (row.id === next.id ? next : row)),
    );
  }

  function toggleSource(row: DepartmentPurchaseRequestRow) {
    if (row.status !== "open") return;
    setCheckedSources((current) =>
      current.some((picked) => picked.id === row.id)
        ? current.filter((picked) => picked.id !== row.id)
        : [...current, row],
    );
  }

  function openCreatePurchaseRequest() {
    if (selectedSources.length === 0) {
      setError("Vui lòng chọn ít nhất một yêu cầu mua hàng từ phòng ban.");
      return;
    }
    const dates = selectedSources
      .map((row) => row.needed_date)
      .filter(Boolean)
      .sort();
    const lines = selectedSources.flatMap((source) =>
      source.lines.map((line) => ({
        item_name: line.item_name,
        unit: line.unit,
        quantity: line.quantity,
        expected_unit_price: line.expected_unit_price,
        discount_percent: 0,
        vat_percent: 0,
        note: line.note ?? `Từ ${source.code}`,
      })),
    );
    setEditing(null);
    setForm({
      supplier_id: null,
      source_request_ids: selectedSources.map((source) => source.id),
      purpose:
        selectedSources.length === 1
          ? selectedSources[0].purpose
          : `Mua theo ${selectedSources.map((source) => source.code).join(", ")}`,
      needed_date: dates[0] ?? "",
      expected_receipt_date: "",
      note: "",
      lines: lines.length ? lines : [emptyLine()],
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

  function cleanRequest(input: PurchaseRequestInput): PurchaseRequestInput {
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
      })),
    };
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    const payload = cleanRequest(form);
    const missingHeader = [
      !payload.supplier_id ? "Nhà cung cấp" : "",
      !payload.needed_date ? "Ngày cần hàng" : "",
      !payload.purpose ? "Mục đích" : "",
    ].filter(Boolean);
    if (missingHeader.length > 0) {
      setFormError(`Vui lòng nhập đầy đủ: ${missingHeader.join(", ")}.`);
      return;
    }
    if (payload.source_request_ids.length === 0) {
      setFormError(
        "Vui lòng chọn ít nhất một yêu cầu mua hàng từ phòng ban để lập phiếu.",
      );
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
    setSaving(true);
    setFormError(null);
    try {
      const saved =
        mode === "edit" && editing
          ? await api.purchaseRequests.update(token, editing.id, payload)
          : await api.purchaseRequests.create(token, payload);
      if (mode === "edit") updateRow(saved);
      else {
        setRows((current) => [saved, ...current]);
        setTotal((t) => t + 1);
      }
      setMode(null);
      setCheckedSources([]); // tạo xong: bỏ chọn hết (các YCMH đã gom rời "open")
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
    setActionBusy(`${kind}:${row.id}`);
    setReasonModal({ ...reasonModal, error: null });
    try {
      const next = await api.purchaseRequests.cancel(token, row.id, reason || null);
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

  function setLine(index: number, patch: Partial<PurchaseRequestLineInput>) {
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
          Bộ phận mua hàng lập phiếu yêu cầu, gửi kế toán duyệt, sau đó theo dõi
          đã mua và đã nhận hàng.
        </p>
      </header>

      <section className="card md-page__tablewrap purchase__source-inbox">
        <div className="purchase__source-head">
          <div>
            <p className="eyebrow">Yêu cầu từ phòng ban</p>
            <h2>Danh sách chờ Thu mua xử lý</h2>
          </div>
          <div className="purchase__actions">
            {canCreate && (
              <Button
                variant="primary"
                onClick={openCreatePurchaseRequest}
                disabled={selectedSources.length === 0}
              >
                Tạo phiếu mua từ yêu cầu
              </Button>
            )}
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
            <tr>
              <th>Chọn</th>
              <th>Mã yêu cầu</th>
              <th>Nguồn</th>
              <th>Cần hàng</th>
              <th>Vật tư</th>
              <th>Trạng thái</th>
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
                    className={`md-page__row${checkedSources.some((picked) => picked.id === row.id) ? " purchase__row--selected" : ""}`}
                    onClick={() => toggleSource(row)}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={checkedSources.some(
                          (picked) => picked.id === row.id,
                        )}
                        disabled={disabled}
                        onChange={() => toggleSource(row)}
                        aria-label={`Chọn ${row.code}`}
                      />
                    </td>
                    <td>
                      <strong className="md-page__mono">{row.code}</strong>
                      <div className="md-page__muted">{row.purpose}</div>
                    </td>
                    <td>
                      {/* {SOURCE_TYPE_LABELS[row.source_type]} */}
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
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        <div className="purchase__source-foot">
          <span className="md-page__muted">
            Đã chọn {selectedSources.length} yêu cầu · Tổng {sourceTotal}
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
          onClose={() => setSelectedId(null)}
        >
          <dl className="purchase__facts">
            <div>
              <dt>Nhà cung cấp</dt>
              <dd>{selected.supplier_name || "Chưa chọn"}</dd>
            </div>
            <div>
              <dt>Yêu cầu nguồn</dt>
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
            className="card md-page__dialog purchase__dialog"
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
                <LocalField label="Nhà cung cấp" required>
                  <select
                    className="input"
                    required
                    value={form.supplier_id ?? ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        supplier_id: e.target.value
                          ? Number(e.target.value)
                          : null,
                      })
                    }
                  >
                    <option value="">Chọn nhà cung cấp</option>
                    {suppliers.map((supplier) => (
                      <option key={supplier.id} value={supplier.id}>
                        {supplier.name}
                      </option>
                    ))}
                  </select>
                </LocalField>
                <LocalField label="Yêu cầu nguồn" wide required>
                  <div className="purchase__source-picker">
                    {formSourceRows.length === 0 ? (
                      <span className="md-page__muted">
                        Chưa có yêu cầu đang chờ mua.
                      </span>
                    ) : (
                      formSourceRows.map((source) => (
                        <label
                          key={source.id}
                          className="purchase__source-option"
                        >
                          <input
                            type="checkbox"
                            checked={form.source_request_ids.includes(
                              source.id,
                            )}
                            onChange={(e) =>
                              setForm((current) => ({
                                ...current,
                                source_request_ids: e.target.checked
                                  ? [...current.source_request_ids, source.id]
                                  : current.source_request_ids.filter(
                                      (id) => id !== source.id,
                                    ),
                              }))
                            }
                          />
                          <span>
                            <strong>{source.code}</strong>
                            <small>
                              {SOURCE_TYPE_LABELS[source.source_type]} ·{" "}
                              {fmtDate(source.needed_date)}
                            </small>
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                </LocalField>
                <LocalField label="Ngày cần hàng" required>
                  <input
                    className="input"
                    type="date"
                    required
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
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        lines: [...current.lines, emptyLine()],
                      }))
                    }
                  >
                    + Thêm dòng
                  </button>
                </div>
                <div className="purchase__line-editor">
                  <div className="purchase__line-labels" aria-hidden="true">
                    <span>
                      Vật tư <span className="purchase__required-star">*</span>
                    </span>
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
                      <input
                        className="input purchase__line-name"
                        required
                        aria-label="Tên vật tư"
                        placeholder="VD: Giấy Duplex 350gsm"
                        value={line.item_name}
                        onChange={(e) =>
                          setLine(index, { item_name: e.target.value })
                        }
                      />
                      <input
                        className="input purchase__line-unit"
                        required
                        aria-label="Đơn vị tính"
                        placeholder="VD: tờ, kg, cuộn"
                        value={line.unit}
                        onChange={(e) =>
                          setLine(index, { unit: e.target.value })
                        }
                      />
                      <input
                        className="input purchase__number-input"
                        type="number"
                        min="0.01"
                        step="0.01"
                        required
                        aria-label="Số lượng"
                        placeholder="VD: 1000"
                        value={line.quantity > 0 ? line.quantity : ""}
                        onChange={(e) =>
                          setLine(index, {
                            quantity: Number(e.target.value || 0),
                          })
                        }
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
                      <button
                        type="button"
                        className="purchase__line-remove"
                        aria-label="Xóa dòng vật tư"
                        title="Xóa dòng"
                        disabled={form.lines.length <= 1}
                        onClick={() =>
                          setForm((current) => ({
                            ...current,
                            lines: current.lines.filter((_, i) => i !== index),
                          }))
                        }
                      >
                        ×
                      </button>
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
        title="Hủy phiếu?"
        message={reasonModal ? `Phiếu ${reasonModal.row.code}` : undefined}
        danger
        confirmLabel="Hủy phiếu"
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
          <span>Lý do / ghi chú</span>
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
