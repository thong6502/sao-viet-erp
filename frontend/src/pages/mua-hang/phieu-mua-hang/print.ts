// Mẫu in phiếu mua hàng khổ A4 (tách từ pages/PurchaseRequestsPage.tsx).
import type { PurchaseRequestRow } from "../../../api/client";
// `escapeHtml` nhập dưới tên `html` để không phải sửa ~30 chỗ gọi trong mẫu in. Bản chép tay cũ
// trong file này đã xoá — hai bản escape song song là kiểu lỗi chỉ lộ ra ở một ký tự hiếm.
import { escapeHtml as html, fmtDate, money } from "../../../utils/format";
import { STATUS_META } from "./shared/constants";

export function printPurchaseRequest(row: PurchaseRequestRow): boolean {
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
    .sign {
      display: flex;
      justify-content: space-around;
      gap: 24px;
      margin-top: 30px;
      text-align: center;
      page-break-inside: avoid;
    }
    .sign-col { flex: 1; }
    .sign-role { font-weight: 700; text-transform: uppercase; font-size: 12px; }
    .sign-hint { color: #666; font-size: 10px; font-style: italic; margin-top: 2px; }
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

  <section class="sign">
    <div class="sign-col">
      <div class="sign-role">Người mua hàng</div>
      <div class="sign-hint">(Ký, ghi rõ họ tên)</div>
    </div>
    <div class="sign-col">
      <div class="sign-role">Kế toán trưởng</div>
      <div class="sign-hint">(Ký, ghi rõ họ tên)</div>
    </div>
  </section>

</body>
</html>`);
  win.document.close();
  win.focus();
  window.setTimeout(() => win.print(), 250);
  return true;
}
