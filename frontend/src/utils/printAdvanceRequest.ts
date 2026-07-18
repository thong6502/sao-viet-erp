/** In "GIẤY ĐỀ NGHỊ THANH TOÁN/HOÀN ỨNG" cho 1 phiếu tạm ứng lương.
 *
 *  Bám đúng mẫu giấy công ty đang dùng: font Times New Roman, A4, không logo.
 *  Nhân viên/kế toán bấm "In phiếu" ở màn Tạm ứng → mở cửa sổ in.
 */
import { amountInWords, dmyParts, escapeHtml, money } from "./format";

export interface AdvancePrintData {
  code: string | null;
  employeeName: string | null;
  departmentName: string | null;
  bankAccount: string | null;
  bankName: string | null;
  amount: number;
  advanceDate: string | null;   // ISO yyyy-mm-dd
  periodMonth: number;
  periodYear: number;
  reason: string | null;
}

const DOTS = "..............................";
/** Ô check chưa tích (mẫu vendor có nhiều loại chứng từ — tạm ứng lương để trống hết). */
const BOX = "☐"; // ☐

/** Bỏ dấu tiếng Việt cho "Nội dung chuyển khoản" (ngân hàng hay lỗi font dấu). */
function noAccent(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D");
}

/** Mở cửa sổ in; trả false nếu trình duyệt chặn pop-up. */
export function printAdvanceRequest(d: AdvancePrintData): boolean {
  const win = window.open("", "_blank", "width=980,height=760");
  if (!win) return false;

  const { d: dd, m: mm, y: yy } = dmyParts(d.advanceDate);
  const mmYear = `${String(d.periodMonth).padStart(2, "0")}/${d.periodYear}`;
  const words = amountInWords(d.amount);
  const dienGiai = d.reason?.trim()
    ? `${escapeHtml(d.reason)}`
    : `Tạm ứng lương tháng ${mmYear}`;
  const ndCk = noAccent(`Tam ung luong ${d.employeeName ?? ""} thang ${mmYear}`.trim());

  const docs = [
    "Hợp đồng", "Báo giá", "Đề nghị thanh toán", "Tờ trình", "Hóa đơn",
    "Biên bản nghiệm thu", "Biên bản bàn giao/PNK", "Khác:.............",
  ].map((x) => `${BOX} ${escapeHtml(x)}`).join("&nbsp;&nbsp;&nbsp;");

  win.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>Giấy đề nghị tạm ứng — ${escapeHtml(d.employeeName ?? "")}</title><style>
@page{size:A4;margin:16mm}
*{box-sizing:border-box}
body{font:13px "Times New Roman",serif;color:#000;margin:0}
.date{text-align:right;font-style:italic;margin-bottom:6px}
h1{font-size:19px;text-align:center;margin:2px 0 14px;letter-spacing:.5px}
.row{margin:5px 0;line-height:1.6}
.row .lb{font-weight:400}
.two{display:flex;gap:24px}
.two>div{flex:1}
b.v{font-weight:700}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:12.5px}
th,td{border:1px solid #000;padding:5px 6px;vertical-align:top}
th{text-align:center;font-weight:700}
.num{text-align:right;white-space:nowrap}
.ck{margin:6px 0 2px}
.bank{line-height:1.7}
.tot{margin-top:8px;line-height:1.8}
.tot b{font-weight:700}
.words{font-style:italic}
.signs{display:flex;justify-content:space-between;gap:8px;text-align:center;margin-top:26px}
.sign{flex:1}
.sign-name{font-weight:700}
.sign-sub{font-style:italic;font-size:11px;color:#333}
.sign-space{height:60px}
</style></head><body onload="window.print()">
<div class="date">Số: <b>${escapeHtml(d.code ?? "................")}</b></div>
<div class="date">TP. Hồ Chí Minh, ngày ${escapeHtml(dd)} tháng ${escapeHtml(mm)} năm ${escapeHtml(yy)}</div>
<h1>GIẤY ĐỀ NGHỊ THANH TOÁN/HOÀN ỨNG</h1>

<div class="row two">
  <div><span class="lb">Họ và tên:</span> <b class="v">${escapeHtml(d.employeeName ?? DOTS)}</b></div>
  <div><span class="lb">Đơn vị (phòng):</span> <b class="v">${escapeHtml(d.departmentName ?? DOTS)}</b></div>
</div>
<div class="row"><span class="lb">Lý do:</span> <b class="v">${dienGiai}</b></div>
<div class="row two">
  <div><span class="lb">Mã hợp đồng/vụ việc:</span> ${DOTS}</div>
  <div><span class="lb">Dự kiến ngày chi:</span> ${DOTS}</div>
</div>
<div class="ck"><span class="lb">Chứng từ kèm theo:</span> ${docs}</div>

<table>
  <thead><tr>
    <th style="width:6%">STT</th><th style="width:34%">DIỄN GIẢI</th>
    <th style="width:12%">LOẠI CHỨNG TỪ</th><th style="width:12%">SỐ CHỨNG TỪ</th>
    <th style="width:20%">SỐ TIỀN</th><th style="width:16%">GHI CHÚ</th>
  </tr></thead>
  <tbody>
    <tr>
      <td style="text-align:center">1</td>
      <td>${dienGiai}</td>
      <td></td><td></td>
      <td class="num">${money(d.amount)}đ</td><td></td>
    </tr>
    <tr>
      <td></td>
      <td colspan="5" class="bank">
        <b>Thông tin chuyển khoản:</b><br>
        Tên TK: ${escapeHtml(d.employeeName ?? DOTS)}<br>
        Số tài khoản: ${escapeHtml(d.bankAccount ?? DOTS)}<br>
        Ngân hàng: ${escapeHtml(d.bankName ?? DOTS)}<br>
        Nội dung chuyển khoản: ${escapeHtml(ndCk)}
      </td>
    </tr>
  </tbody>
</table>

<div class="tot">
  <div><b>Tổng cộng: ${money(d.amount)}đ</b></div>
  <div class="words">(Bằng chữ: ${escapeHtml(words)}).</div>
  <div>Số tiền đã tạm ứng &nbsp;: 0</div>
  <div>Số tiền trả lại &nbsp;&nbsp;&nbsp;&nbsp;: 0</div>
  <div>Số tiền lĩnh thêm &nbsp;: <b>${money(d.amount)}đ</b></div>
</div>

<div class="signs">
  ${["Tổng Giám Đốc", "Kế toán trưởng", "Trưởng phòng", "Người đề nghị"]
    .map((n) => `<div class="sign"><div class="sign-name">${escapeHtml(n)}</div><div class="sign-sub">(Ký, họ tên)</div><div class="sign-space"></div></div>`)
    .join("")}
</div>
</body></html>`);
  win.document.close();
  win.focus();
  return true;
}
