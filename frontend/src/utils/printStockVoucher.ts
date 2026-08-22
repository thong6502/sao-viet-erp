/** In Phiếu nhập kho / Phiếu xuất kho theo mẫu Bộ Tài chính — Thông tư 200/2014/TT-BTC.
 *
 *  Mẫu 01-VT = PHIẾU NHẬP KHO, Mẫu 02-VT = PHIẾU XUẤT KHO. Hai mẫu chỉ khác vài nhãn và
 *  thứ tự ô ký nên dùng chung một builder — cùng cách làm với printTT200 (phiếu thu/chi).
 *  Bố cục bám biểu mẫu giấy: không logo, font Times New Roman, A4.
 *
 *  Chỗ lệch có chủ ý so với mẫu chuẩn:
 *   • Dòng "Theo ... số ... ngày ..." điền **số yêu cầu**, vì mọi phiếu đều phải ứng theo
 *     một yêu cầu đã duyệt (spec-kho-de-nghi §5).
 *  (Trước có thêm cột "Mã lô" cho giá xuất đích danh — đã BỎ: lô định danh qua chính phiếu
 *   nhập nguồn nên cột riêng thừa.)
 *
 *  Cột Đơn giá + Thành tiền TỰ ẨN khi người in không có quyền `can_view_cost`: API không
 *  trả số (`don_gia === null`) nên ở đây chỉ cần dò null, không cần truyền thêm cờ quyền.
 */
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { COMPANY } from "../constants/company";
import { amountInWords, dmyParts, escapeHtml, money } from "./format";

export interface StockVoucherPrintLine {
  materialCode: string | null;
  materialName: string | null;
  dvt: string | null;
  /** Số lượng ghi trên chứng từ (yêu cầu đã duyệt). */
  soLuongChungTu: number | null;
  /** Số lượng thực nhập / thực xuất. */
  soLuong: number;
  /** null = người in không có quyền xem giá vốn → bỏ cột. */
  donGia: number | null;
  thanhTien: number | null;
}

export interface StockVoucherPrintData {
  kind: "nhap" | "xuat";
  docNo: string | null;
  /** Ngày chứng từ (ISO yyyy-mm-dd). */
  docDate: string | null;
  debitAccount: string | null;
  creditAccount: string | null;
  /** Bộ phận yêu cầu — ô "Bộ phận" ở góc trên trái. */
  boPhan: string | null;
  /** Họ tên người giao hàng (01-VT) / người nhận hàng (02-VT). */
  nguoiGiaoNhan: string | null;
  /** Số yêu cầu + ngày, điền vào dòng "Theo ... số ... ngày ...". */
  chungTuGoc: string | null;
  chungTuGocNgay: string | null;
  /** Chuỗi trách nhiệm — in rõ AI tạo yêu cầu · AI lập phiếu (kho nhận). Bỏ "người duyệt" vì tạo
   *  yêu cầu kho không còn bước duyệt (1 quyền). */
  nguoiDeNghi: string | null;
  nguoiLapPhieu: string | null;
  /** Tên kho nhập/xuất. */
  khoTen: string | null;
  diaDiem: string | null;
  lyDo: string | null;
  lines: StockVoucherPrintLine[];
  /** Tổng giá vốn; null khi thiếu quyền xem giá. */
  tongTien: number | null;
  /** Phiếu đã hủy → đóng dấu chìm ĐÃ HỦY (vẫn in được, vẫn giữ số trong quyển). */
  cancelled?: boolean;
}

const FORM = {
  nhap: {
    formCode: "Mẫu số 01 - VT",
    title: "PHIẾU NHẬP KHO",
    personLabel: "Họ và tên người giao hàng",
    placeLabel: "Nhập tại kho",
    qtyDocLabel: "Theo chứng từ",
    qtyRealLabel: "Thực nhập",
    reasonLabel: "Lý do nhập kho",
    signers: ["Người lập phiếu", "Người giao hàng", "Thủ kho", "Kế toán trưởng", "Giám đốc"],
  },
  xuat: {
    formCode: "Mẫu số 02 - VT",
    title: "PHIẾU XUẤT KHO",
    personLabel: "Họ và tên người nhận hàng",
    placeLabel: "Xuất tại kho",
    qtyDocLabel: "Yêu cầu",
    qtyRealLabel: "Thực xuất",
    reasonLabel: "Lý do xuất kho",
    signers: ["Người lập phiếu", "Người nhận hàng", "Thủ kho", "Kế toán trưởng", "Giám đốc"],
  },
} as const;

const DOTS = "................................";

function row(label: string, value: string | null, dotted = true): string {
  const shown = value || (dotted ? DOTS : "");
  return `<div class="row"><span class="lb">${escapeHtml(label)}:</span> <span class="vl">${escapeHtml(shown)}</span></div>`;
}

function qty(n: number | null): string {
  // API trả Numeric(14,2) → JSON số; JS không giữ đuôi .00 nên 10.00 in ra "10", 10.5 in
  // ra "10.5". Đúng thói quen phiếu giấy (không ai ghi "10,00 tờ"), khỏi cần format thêm.
  return n === null || n === undefined ? "" : String(n);
}

/** Mở cửa sổ in; trả false nếu trình duyệt chặn pop-up. */
export function printStockVoucher(data: StockVoucherPrintData): boolean {
  const win = window.open("", "_blank", "width=1024,height=760");
  if (!win) return false;
  const form = FORM[data.kind];
  // Logo: Vite trả data URI (nếu nhỏ, đã inline) hoặc đường dẫn /assets/…; cửa sổ in là about:blank
  // nên path phải kèm origin mới tải được. `onload=print` đợi ảnh tải xong rồi mới in.
  const logoSrc = logoUrl.startsWith("data:") ? logoUrl : window.location.origin + logoUrl;
  const { d, m, y } = dmyParts(data.docDate);
  // Thiếu quyền xem giá vốn → API trả null ở mọi dòng → bỏ hẳn 2 cột tiền.
  const showMoney = data.lines.some((l) => l.donGia !== null && l.donGia !== undefined);
  const words = showMoney && data.tongTien !== null ? amountInWords(data.tongTien) : "";

  const colCount = showMoney ? 8 : 6;
  const body = data.lines
    .map(
      (l, i) => `<tr>
        <td class="c">${i + 1}</td>
        <td>${escapeHtml(l.materialName ?? "")}</td>
        <td class="c">${escapeHtml(l.materialCode ?? "")}</td>
        <td class="c">${escapeHtml(l.dvt ?? "")}</td>
        <td class="r">${qty(l.soLuongChungTu)}</td>
        <td class="r">${qty(l.soLuong)}</td>
        ${showMoney ? `<td class="r">${money(l.donGia ?? 0)}</td><td class="r">${money(l.thanhTien ?? 0)}</td>` : ""}
      </tr>`,
    )
    .join("");

  const totalRow = showMoney
    ? `<tr class="tot"><td colspan="7" class="r"><b>Cộng</b></td><td class="r"><b>${money(data.tongTien ?? 0)}</b></td></tr>`
    : `<tr class="tot"><td colspan="${colCount}" class="r"><b>Cộng</b></td></tr>`;

  const signers = form.signers
    .map(
      (name, index) =>
        `<div class="sign"><div class="sign-name">${escapeHtml(name)}</div>
         <div class="sign-sub">(Ký, họ tên${index === form.signers.length - 1 ? ", đóng dấu" : ""})</div></div>`,
    )
    .join("");

  win.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>${form.title} ${escapeHtml(data.docNo ?? "")}</title><style>
@page{size:A4;margin:12mm}
*{box-sizing:border-box}
body{font:13px "Times New Roman",serif;color:#000;margin:0;position:relative}
.head{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.unit{max-width:60%;display:flex;gap:10px;align-items:flex-start}
.unit-logo{height:48px;width:auto;flex:0 0 auto;object-fit:contain}
.unit b{font-size:13.5px}
.unit div{margin-top:2px}
.form{text-align:center;min-width:38%}
.form b{font-size:13.5px}
.form i{display:block;font-size:11px;margin-top:3px;line-height:1.35}
.title-wrap{display:flex;justify-content:space-between;align-items:flex-start;margin-top:10px}
.title-mid{flex:1;text-align:center}
h1{font-size:20px;margin:6px 0 2px;letter-spacing:.5px}
.doc-date{font-style:italic;font-weight:700;margin-bottom:6px}
.meta{min-width:30%;font-size:12.5px;line-height:1.7}
.meta div{white-space:nowrap}
.body{margin-top:6px;line-height:1.85}
.row{display:flex;gap:6px}
.lb{white-space:nowrap}
.vl{flex:1;font-weight:700}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12.5px}
th,td{border:1px solid #000;padding:4px 5px;vertical-align:top}
th{text-align:center;font-weight:700}
td.c{text-align:center}
td.r{text-align:right}
tr.tot td{font-weight:700}
.words{margin-top:6px;font-style:italic}
.sign-date{text-align:right;font-style:italic;margin:14px 0 8px}
.signs{display:flex;justify-content:space-between;gap:8px;text-align:center}
.sign{flex:1}
.sign-name{font-weight:700;font-size:12.5px}
.sign-sub{font-style:italic;font-size:11px}
.stamp{position:fixed;top:42%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);
  font-size:64px;font-weight:700;color:rgba(200,0,0,.18);border:6px solid rgba(200,0,0,.18);
  padding:8px 28px;letter-spacing:6px;pointer-events:none}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body onload="window.print()">
${data.cancelled ? '<div class="stamp">ĐÃ HỦY</div>' : ""}
<div class="head">
  <div class="unit">
    <img class="unit-logo" src="${escapeHtml(logoSrc)}" alt="">
    <div>
      <b>${escapeHtml(COMPANY.name)}</b>
      <div>${escapeHtml(COMPANY.address)}</div>
      <div>Bộ phận: ${escapeHtml(data.boPhan ?? "...............")}</div>
    </div>
  </div>
  <div class="form"><b>${form.formCode}</b>
    <i>(Ban hành theo Thông tư số 200/2014/TT-BTC<br>Ngày 22/12/2014 của Bộ Tài chính)</i>
  </div>
</div>
<div class="title-wrap">
  <div class="title-mid">
    <h1>${form.title}</h1>
    <div class="doc-date">Ngày ${escapeHtml(d)} tháng ${escapeHtml(m)} năm ${escapeHtml(y)}</div>
  </div>
  <div class="meta">
    <div>Số: &nbsp;<b>${escapeHtml(data.docNo ?? "...............")}</b></div>
    <div>Nợ: &nbsp;${escapeHtml(data.debitAccount ?? "...............")}</div>
    <div>Có: &nbsp;${escapeHtml(data.creditAccount ?? "...............")}</div>
  </div>
</div>
<div class="body">
  ${row(form.personLabel, data.nguoiGiaoNhan)}
  <div class="row"><span class="lb">Theo yêu cầu số:</span> <span class="vl">${escapeHtml(
    data.chungTuGoc ?? DOTS,
  )}${data.chungTuGocNgay ? ` ngày ${escapeHtml(data.chungTuGocNgay)}` : ""}</span></div>
  ${row("Người tạo yêu cầu", data.nguoiDeNghi)}
  ${row("Người lập phiếu (kho)", data.nguoiLapPhieu)}
  ${row(form.reasonLabel, data.lyDo)}
  ${row(form.placeLabel, data.khoTen)}
  ${row("Địa điểm", data.diaDiem)}
</div>
<table>
  <thead>
    <tr>
      <th rowspan="2" style="width:28px">STT</th>
      <th rowspan="2">Tên, nhãn hiệu, quy cách, phẩm chất vật tư</th>
      <th rowspan="2" style="width:76px">Mã số</th>
      <th rowspan="2" style="width:52px">ĐVT</th>
      <th colspan="2" style="width:150px">Số lượng</th>
      ${showMoney ? '<th rowspan="2" style="width:92px">Đơn giá</th><th rowspan="2" style="width:104px">Thành tiền</th>' : ""}
    </tr>
    <tr>
      <th style="width:75px">${form.qtyDocLabel}</th>
      <th style="width:75px">${form.qtyRealLabel}</th>
    </tr>
  </thead>
  <tbody>
    ${body}
    ${totalRow}
  </tbody>
</table>
${showMoney ? `<div class="words">Tổng số tiền (viết bằng chữ): ${escapeHtml(words)}</div>` : ""}
<div class="words">Số chứng từ gốc kèm theo: ................................</div>
<div class="sign-date">Ngày......tháng.......năm...............</div>
<div class="signs">${signers}</div>
</body></html>`);
  win.document.close();
  win.focus();
  return true;
}

// ── Phiếu điều chuyển kho (xuất kho kiêm vận chuyển nội bộ) ───────────────────
//  KHÁC 01-VT/02-VT: điều chuyển là MỘT phiếu Từ kho → Đến kho (nội bộ), không phải nhập/xuất
//  mua-bán. Thêm cột HSD (điều chuyển giữ giá vốn + hạn dùng ĐÍCH DANH theo lô) và ô ký
//  Giao · Vận chuyển · Nhận — làm giấy tờ đi đường.

export interface TransferPrintLine {
  materialCode: string | null;
  materialName: string | null;
  dvt: string | null;
  soLuong: number;
  donGia: number | null;
  thanhTien: number | null;
  /** HSD của lô (ISO yyyy-mm-dd) — null nếu lô không hạn. */
  hsd: string | null;
}

export interface TransferPrintData {
  docNo: string | null;
  docDate: string | null;
  khoNguon: string | null;
  khoDich: string | null;
  nguoiLap: string | null;
  nguoiGiaoNhan: string | null;
  lyDo: string | null;
  lines: TransferPrintLine[];
  tongTien: number | null;
  cancelled?: boolean;
}

/** ISO yyyy-mm-dd → dd/mm/yyyy (ô HSD trên bảng). */
function ddmy(iso: string | null): string {
  return iso ? iso.slice(0, 10).split("-").reverse().join("/") : "";
}

/** In PHIẾU ĐIỀU CHUYỂN KHO; trả false nếu trình duyệt chặn pop-up. */
export function printTransferVoucher(data: TransferPrintData): boolean {
  const win = window.open("", "_blank", "width=1024,height=760");
  if (!win) return false;
  const logoSrc = logoUrl.startsWith("data:") ? logoUrl : window.location.origin + logoUrl;
  const { d, m, y } = dmyParts(data.docDate);
  const showMoney = data.lines.some((l) => l.donGia !== null && l.donGia !== undefined);
  const words = showMoney && data.tongTien !== null ? amountInWords(data.tongTien) : "";

  const body = data.lines
    .map(
      (l, i) => `<tr>
        <td class="c">${i + 1}</td>
        <td>${escapeHtml(l.materialName ?? "")}</td>
        <td class="c">${escapeHtml(l.materialCode ?? "")}</td>
        <td class="c">${escapeHtml(l.dvt ?? "")}</td>
        <td class="r">${qty(l.soLuong)}</td>
        ${showMoney ? `<td class="r">${money(l.donGia ?? 0)}</td><td class="r">${money(l.thanhTien ?? 0)}</td>` : ""}
        <td class="c">${escapeHtml(ddmy(l.hsd))}</td>
      </tr>`,
    )
    .join("");

  const totalRow = showMoney
    ? `<tr class="tot"><td colspan="6" class="r"><b>Cộng</b></td><td class="r"><b>${money(data.tongTien ?? 0)}</b></td><td></td></tr>`
    : `<tr class="tot"><td colspan="6" class="r"><b>Cộng</b></td></tr>`;

  const signerNames = [
    "Người lập phiếu",
    "Người giao hàng (kho nguồn)",
    "Người vận chuyển",
    "Thủ kho nhận (kho đích)",
    "Kế toán trưởng",
  ];
  const signers = signerNames
    .map(
      (name, index) =>
        `<div class="sign"><div class="sign-name">${escapeHtml(name)}</div>
         <div class="sign-sub">(Ký, họ tên${index === signerNames.length - 1 ? ", đóng dấu" : ""})</div></div>`,
    )
    .join("");

  win.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>PHIẾU ĐIỀU CHUYỂN KHO ${escapeHtml(data.docNo ?? "")}</title><style>
@page{size:A4;margin:12mm}
*{box-sizing:border-box}
body{font:13px "Times New Roman",serif;color:#000;margin:0;position:relative}
.head{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.unit{max-width:58%;display:flex;gap:10px;align-items:flex-start}
.unit-logo{height:48px;width:auto;flex:0 0 auto;object-fit:contain}
.unit b{font-size:13.5px}
.unit div{margin-top:2px}
.form{text-align:center;min-width:40%}
.form b{font-size:13px}
.form i{display:block;font-size:11px;margin-top:3px;line-height:1.35}
.title-wrap{display:flex;justify-content:space-between;align-items:flex-start;margin-top:10px}
.title-mid{flex:1;text-align:center}
h1{font-size:19px;margin:6px 0 2px;letter-spacing:.5px}
.doc-date{font-style:italic;font-weight:700;margin-bottom:6px}
.meta{min-width:26%;font-size:12.5px;line-height:1.7}
.meta div{white-space:nowrap}
.body{margin-top:6px;line-height:1.85}
.row{display:flex;gap:6px}
.lb{white-space:nowrap}
.vl{flex:1;font-weight:700}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12.5px}
th,td{border:1px solid #000;padding:4px 5px;vertical-align:top}
th{text-align:center;font-weight:700}
td.c{text-align:center}
td.r{text-align:right}
tr.tot td{font-weight:700}
.words{margin-top:6px;font-style:italic}
.sign-date{text-align:right;font-style:italic;margin:14px 0 8px}
.signs{display:flex;justify-content:space-between;gap:8px;text-align:center}
.sign{flex:1}
.sign-name{font-weight:700;font-size:12px}
.sign-sub{font-style:italic;font-size:11px}
.stamp{position:fixed;top:42%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);
  font-size:64px;font-weight:700;color:rgba(200,0,0,.18);border:6px solid rgba(200,0,0,.18);
  padding:8px 28px;letter-spacing:6px;pointer-events:none}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body onload="window.print()">
${data.cancelled ? '<div class="stamp">ĐÃ HỦY</div>' : ""}
<div class="head">
  <div class="unit">
    <img class="unit-logo" src="${escapeHtml(logoSrc)}" alt="">
    <div>
      <b>${escapeHtml(COMPANY.name)}</b>
      <div>${escapeHtml(COMPANY.address)}</div>
    </div>
  </div>
  <div class="form"><b>Phiếu xuất kho kiêm vận chuyển nội bộ</b>
    <i>(Chứng từ điều chuyển nội bộ — làm giấy tờ đi đường)</i>
  </div>
</div>
<div class="title-wrap">
  <div class="title-mid">
    <h1>PHIẾU ĐIỀU CHUYỂN KHO</h1>
    <div class="doc-date">Ngày ${escapeHtml(d)} tháng ${escapeHtml(m)} năm ${escapeHtml(y)}</div>
  </div>
  <div class="meta">
    <div>Số: &nbsp;<b>${escapeHtml(data.docNo ?? "...............")}</b></div>
  </div>
</div>
<div class="body">
  <div class="row"><span class="lb">Từ kho (nguồn):</span> <span class="vl">${escapeHtml(data.khoNguon ?? DOTS)}</span></div>
  <div class="row"><span class="lb">Đến kho (nhập về):</span> <span class="vl">${escapeHtml(data.khoDich ?? DOTS)}</span></div>
  ${row("Người vận chuyển / giao nhận", data.nguoiGiaoNhan)}
  ${row("Người lập phiếu", data.nguoiLap)}
  ${row("Lý do điều chuyển", data.lyDo)}
</div>
<table>
  <thead>
    <tr>
      <th style="width:28px">STT</th>
      <th>Tên, nhãn hiệu, quy cách vật tư</th>
      <th style="width:76px">Mã số</th>
      <th style="width:52px">ĐVT</th>
      <th style="width:80px">Số lượng</th>
      ${showMoney ? '<th style="width:92px">Đơn giá vốn</th><th style="width:104px">Thành tiền</th>' : ""}
      <th style="width:82px">HSD</th>
    </tr>
  </thead>
  <tbody>
    ${body}
    ${totalRow}
  </tbody>
</table>
${showMoney ? `<div class="words">Tổng giá trị (viết bằng chữ): ${escapeHtml(words)}</div>` : ""}
<div class="sign-date">Ngày......tháng.......năm...............</div>
<div class="signs">${signers}</div>
</body></html>`);
  win.document.close();
  win.focus();
  return true;
}
