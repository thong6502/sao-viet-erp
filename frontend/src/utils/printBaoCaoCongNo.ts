import { COMPANY } from "../constants/company";
import { escapeHtml } from "./format";
import type { BaoCaoCongNo } from "../api/client";

function fmtMoney(v: number): string {
  return v ? Math.round(v).toLocaleString("vi-VN") : "—";
}

function ngayVn(d: string): string {
  if (!d) return "";
  const parts = d.slice(0, 10).split("-");
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return d;
}

export function printBaoCaoCongNo(bc: BaoCaoCongNo): void {
  const win = window.open("", "_blank");
  if (!win) return;

  const tieuDe = escapeHtml(
    bc.tieu_de || (bc.tk === "131" ? "TỔNG HỢP CÔNG NỢ PHẢI THU" : "TỔNG HỢP CÔNG NỢ PHẢI TRẢ"),
  );
  const tuNgay = ngayVn(bc.tu_ngay);
  const denNgay = ngayVn(bc.den_ngay);

  const rowsHtml = bc.items
    .map(
      (d) => `
      <tr>
        <td class="col-code">${escapeHtml(d.ma || "")}</td>
        <td class="col-name">${escapeHtml(d.ten || "")}</td>
        <td class="col-tk">${escapeHtml(d.tk || bc.tk)}</td>
        <td class="col-money">${fmtMoney(d.dau_no)}</td>
        <td class="col-money">${fmtMoney(d.dau_co)}</td>
        <td class="col-money">${fmtMoney(d.ps_no)}</td>
        <td class="col-money">${fmtMoney(d.ps_co)}</td>
        <td class="col-money">${fmtMoney(d.cuoi_no)}</td>
        <td class="col-money">${fmtMoney(d.cuoi_co)}</td>
      </tr>`,
    )
    .join("");

  const today = new Date();
  const d = today.getDate();
  const m = today.getMonth() + 1;
  const y = today.getFullYear();

  win.document.write(`<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>${tieuDe} (${tuNgay} - ${denNgay})</title>
  <style>
    @page {
      size: A4 landscape;
      margin: 10mm 10mm 10mm 10mm;
    }
    * { box-sizing: border-box; }
    body {
      font-family: "Times New Roman", serif;
      font-size: 11pt;
      color: #000;
      margin: 0;
      padding: 0;
    }
    .header {
      margin-bottom: 12px;
    }
    .company-name {
      font-size: 10.5pt;
      font-weight: bold;
      text-transform: uppercase;
    }
    .company-address {
      font-size: 9.5pt;
      color: #333;
    }
    .title-area {
      text-align: center;
      margin-bottom: 16px;
    }
    h1 {
      font-size: 15pt;
      font-weight: bold;
      margin: 4px 0 2px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .subtitle {
      font-size: 11pt;
      font-weight: bold;
      margin-top: 2px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-family: "Microsoft Sans Serif", Arial, sans-serif;
      font-size: 8.5pt;
    }
    th, td {
      border: 0.75pt solid #000;
      padding: 4px 5px;
    }
    th {
      text-align: center;
      font-weight: normal;
      background-color: #f2f2f2;
    }
    .col-code { width: 110px; text-align: left; }
    .col-name { text-align: left; min-width: 180px; }
    .col-tk { width: 55px; text-align: center; }
    .col-money { width: 95px; text-align: right; }
    tfoot tr td {
      font-weight: bold;
      background-color: #f9f9f9;
    }
    .footer-sign {
      margin-top: 24px;
      page-break-inside: avoid;
      font-family: "Times New Roman", serif;
    }
    .sign-date {
      text-align: right;
      font-style: italic;
      font-size: 11pt;
      margin-bottom: 8px;
    }
    .sign-grid {
      display: flex;
      justify-content: space-between;
      text-align: center;
    }
    .sign-box {
      flex: 1;
    }
    .sign-title {
      font-weight: bold;
      font-size: 11pt;
    }
    .sign-hint {
      font-size: 9.5pt;
      font-style: italic;
      margin-top: 2px;
    }
    .sign-space {
      height: 70px;
    }
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      th { background-color: #f2f2f2 !important; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="company-name">${escapeHtml(COMPANY.name)}</div>
    <div class="company-address">${escapeHtml(COMPANY.address)}</div>
  </div>

  <div class="title-area">
    <h1>${tieuDe}</h1>
    <div class="subtitle">
      Tài khoản: ${escapeHtml(bc.tk)}; Loại tiền: Tổng hợp; Từ ngày ${tuNgay} đến ngày ${denNgay}
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th rowspan="2" class="col-code">${escapeHtml(bc.nhan_ma || "Mã đối tượng")}</th>
        <th rowspan="2" class="col-name">${escapeHtml(bc.nhan_ten || "Tên đối tượng")}</th>
        <th rowspan="2" class="col-tk">TK công nợ</th>
        <th colspan="2">Số dư đầu kỳ</th>
        <th colspan="2">Số phát sinh</th>
        <th colspan="2">Số dư cuối kỳ</th>
      </tr>
      <tr>
        <th class="col-money">Nợ</th>
        <th class="col-money">Có</th>
        <th class="col-money">Nợ</th>
        <th class="col-money">Có</th>
        <th class="col-money">Nợ</th>
        <th class="col-money">Có</th>
      </tr>
    </thead>
    <tbody>
      ${rowsHtml}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="3"><b>Số dòng = ${bc.items.length}</b></td>
        <td class="col-money">${fmtMoney(bc.tong.dau_no)}</td>
        <td class="col-money">${fmtMoney(bc.tong.dau_co)}</td>
        <td class="col-money">${fmtMoney(bc.tong.ps_no)}</td>
        <td class="col-money">${fmtMoney(bc.tong.ps_co)}</td>
        <td class="col-money">${fmtMoney(bc.tong.cuoi_no)}</td>
        <td class="col-money">${fmtMoney(bc.tong.cuoi_co)}</td>
      </tr>
    </tfoot>
  </table>

  <div class="footer-sign">
    <div class="sign-date">Ngày ${d} tháng ${m} năm ${y}</div>
    <div class="sign-grid">
      <div class="sign-box">
        <div class="sign-title">Người lập biểu</div>
        <div class="sign-hint">(Ký, họ tên)</div>
        <div class="sign-space"></div>
      </div>
      <div class="sign-box">
        <div class="sign-title">Kế toán trưởng</div>
        <div class="sign-hint">(Ký, họ tên)</div>
        <div class="sign-space"></div>
      </div>
      <div class="sign-box">
        <div class="sign-title">Giám đốc</div>
        <div class="sign-hint">(Ký, họ tên, đóng dấu)</div>
        <div class="sign-space"></div>
      </div>
    </div>
  </div>
  <script>window.onload = function() { window.print(); };</script>
</body>
</html>`);
  win.document.close();
}