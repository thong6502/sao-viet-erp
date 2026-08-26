/** In Phiếu thu / Phiếu chi theo mẫu Bộ Tài chính — Thông tư 200/2014/TT-BTC.
 *
 *  Mẫu 01-TT = PHIẾU THU, Mẫu 02-TT = PHIẾU CHI. Hai mẫu chỉ khác vài nhãn và thứ tự
 *  ô ký nên dùng chung một builder. Bố cục bám đúng biểu mẫu giấy công ty đang dùng
 *  (khảo sát 2026-07), font Times New Roman, A4. Logo thêm 26/08/2026 vào ô "đơn vị" —
 *  Thông tư 200 quy định CÁC Ô cần có, không cấm logo; mẫu giấy khảo sát ban đầu chưa
 *  có logo chỉ vì bản đó chưa in logo, không phải luật cấm.
 */
import svnLogoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { COMPANY } from "../constants/company";
import { amountInWords, dmyParts, escapeHtml, money, originalMoney } from "./format";

export interface TT200Line {
  label: string;
  value: string;
}

export interface TT200PrintData {
  kind: "chi" | "thu";
  /** Số in ở ô "Số:" (PC00445). Chưa có thì để trống cho viết tay. */
  docNo: string | null;
  /** Ngày chứng từ (ISO yyyy-mm-dd) — in ở dòng dưới tiêu đề. */
  docDate: string | null;
  debitAccount: string | null;
  creditAccount: string | null;
  /** Người nhận tiền (phiếu chi) / người nộp tiền (phiếu thu). */
  personName: string | null;
  personAddress: string | null;
  /** Lý do chi / lý do nộp. */
  reason: string;
  /** Dòng phụ tùy chọn (vd thông tin chuyển khoản của UNC). */
  extraLines?: TT200Line[];
  amount: number;
  amountVnd: number;
  currency: string;
  exchangeRate: number;
  attachmentCount: number;
  /** Phiếu đã hủy → đóng dấu chìm ĐÃ HỦY (vẫn in được, vẫn giữ số trong quyển). */
  cancelled?: boolean;
}

const FORM = {
  chi: {
    formCode: "Mẫu số 02 - TT",
    title: "PHIẾU CHI",
    personLabel: "Họ và tên người nhận tiền",
    reasonLabel: "Lý do chi",
    signers: ["Giám đốc", "Kế toán trưởng", "Thủ quỹ", "Người lập phiếu", "Người nhận tiền"],
  },
  thu: {
    formCode: "Mẫu số 01 - TT",
    title: "PHIẾU THU",
    personLabel: "Họ tên người nộp tiền",
    reasonLabel: "Lý do nộp",
    signers: ["Giám đốc", "Kế toán trưởng", "Người nộp tiền", "Người lập phiếu", "Thủ quỹ"],
  },
} as const;

const DOTS = "................................";

function row(label: string, value: string, dotted = true): string {
  const shown = value || (dotted ? DOTS : "");
  return `<div class="row"><span class="lb">${escapeHtml(label)}:</span> <span class="vl">${escapeHtml(shown)}</span></div>`;
}

/** Mở cửa sổ in; trả false nếu trình duyệt chặn pop-up. */
export function printTT200(data: TT200PrintData): boolean {
  const win = window.open("", "_blank", "width=980,height=760");
  if (!win) return false;
  const form = FORM[data.kind];
  const { d, m, y } = dmyParts(data.docDate);
  const words = amountInWords(data.amountVnd);
  const foreign =
    data.currency !== "VND"
      ? `<div class="row"><span class="lb">+ Tỷ giá ngoại tệ:</span> <span class="vl">${escapeHtml(data.exchangeRate)}</span></div>
         <div class="row"><span class="lb">+ Số tiền nguyên tệ:</span> <span class="vl">${escapeHtml(originalMoney(data.amount, data.currency))}</span></div>`
      : "";
  const extras = (data.extraLines ?? [])
    .map((line) => row(line.label, line.value))
    .join("");
  const signers = form.signers
    .map(
      (name, index) =>
        `<div class="sign"><div class="sign-name">${escapeHtml(name)}</div>
         <div class="sign-sub">(Ký, họ tên${index === 0 ? ", đóng dấu" : ""})</div></div>`,
    )
    .join("");

  win.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>${form.title} ${escapeHtml(data.docNo ?? "")}</title><style>
@page{size:A4;margin:15mm}
*{box-sizing:border-box}
body{font:13px "Times New Roman",serif;color:#000;margin:0;position:relative}
.head{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.unit{max-width:58%;display:flex;gap:8px;align-items:center}
.unit img{height:36px;width:auto;flex-shrink:0}
.unit b{font-size:13.5px}
.form{text-align:center;min-width:38%}
.form b{font-size:13.5px}
.form i{display:block;font-size:11px;margin-top:3px;line-height:1.35}
.title-wrap{display:flex;justify-content:space-between;align-items:flex-start;margin-top:10px}
.title-mid{flex:1;text-align:center}
h1{font-size:20px;margin:6px 0 2px;letter-spacing:.5px}
.doc-date{font-style:italic;font-weight:700;margin-bottom:6px}
.meta{min-width:34%;font-size:12.5px;line-height:1.7}
.meta div{white-space:nowrap}
.body{margin-top:8px;line-height:1.9}
.row{display:flex;gap:6px}
.lb{white-space:nowrap}
.vl{flex:1;font-weight:700}
.sign-date{text-align:right;font-style:italic;margin:14px 0 8px}
.signs{display:flex;justify-content:space-between;gap:8px;text-align:center}
.sign{flex:1}
.sign-name{font-weight:700;font-size:12.5px}
.sign-sub{font-style:italic;font-size:11px}
.tail{margin-top:64px;line-height:1.9}
.stamp{position:fixed;top:42%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);
  font-size:64px;font-weight:700;color:rgba(200,0,0,.18);border:6px solid rgba(200,0,0,.18);
  padding:8px 28px;letter-spacing:6px;pointer-events:none}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body onload="window.print()">
${data.cancelled ? '<div class="stamp">ĐÃ HỦY</div>' : ""}
<div class="head">
  <div class="unit">
    <img src="${svnLogoUrl}" alt="" />
    <b>${escapeHtml(COMPANY.name)}</b>
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
    <div>Quyển số: ...................</div>
    <div>Số: &nbsp;<b>${escapeHtml(data.docNo ?? "...............")}</b></div>
    <div>Nợ: &nbsp;${escapeHtml(data.debitAccount ?? "...............")}</div>
    <div>Có: &nbsp;${escapeHtml(data.creditAccount ?? "...............")}</div>
  </div>
</div>
<div class="body">
  ${row(form.personLabel, data.personName ?? "")}
  ${row("Địa chỉ", data.personAddress ?? "")}
  ${row(form.reasonLabel, data.reason)}
  ${extras}
  ${row("Số tiền", `${money(data.amountVnd)}`, false)}
  ${foreign}
  ${row("Viết bằng chữ", words, false)}
  <div class="row"><span class="lb">Kèm theo:</span> <span class="vl">${escapeHtml(String(data.attachmentCount))} chứng từ gốc</span></div>
</div>
<div class="sign-date">Ngày......tháng.......năm...............</div>
<div class="signs">${signers}</div>
<div class="tail">Đã nhận đủ số tiền (Viết bằng chữ): &nbsp;${escapeHtml(words)}</div>
</body></html>`);
  win.document.close();
  win.focus();
  return true;
}
