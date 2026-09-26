/** In "BẢNG KÊ" đính kèm phiếu chi tạm ứng / lương đợt 1 (25/09/2026).
 *
 *  Chủ chốt: chi một lượt cho 1 hay 1000 người thì chỉ MỘT phiếu chi, người nhận ghi "Theo bảng kê
 *  đính kèm (N người)" — bảng kê này là phần "đính kèm" đó. Tiền mặt: có cột KÝ NHẬN cho từng người
 *  (ký khi lĩnh tại quỹ). Chuyển khoản: cột số tài khoản + ngân hàng.
 *  Bám nếp giấy tờ công ty như `printAdvanceRequest`: Times New Roman, A4, không logo.
 */
import { api, type BangKeTamUng } from "../api/client";
import { amountInWords, dmyParts, escapeHtml, money } from "./format";

/** Mở cửa sổ in; trả false nếu trình duyệt chặn pop-up. */
export function printBangKeTamUng(bk: BangKeTamUng): boolean {
  const win = window.open("", "_blank", "width=1100,height=780");
  if (!win) return false;
  const { d, m, y } = dmyParts(bk.voucher_date);
  const tienMat = bk.voucher_type !== "bank_transfer";
  const loai = (k: string) => (k === "luong_dot_1" ? "Lương đợt 1" : "Tạm ứng");
  const dong = bk.rows
    .map(
      (r, i) => `<tr>
  <td class="c">${i + 1}</td>
  <td>${escapeHtml(r.ma_nv ?? "")}</td>
  <td>${escapeHtml(r.ten ?? "")}</td>
  <td>${escapeHtml(r.department_name ?? "")}</td>
  <td>${escapeHtml(loai(r.kind))}</td>
  <td>${escapeHtml(r.ma_phieu ?? "")}</td>
  <td class="num">${money(r.so_tien)}</td>
  ${
    tienMat
      ? `<td class="ky"></td>`
      : `<td>${escapeHtml(r.so_tai_khoan ?? "")}</td><td>${escapeHtml(r.ngan_hang ?? "")}</td>`
  }
</tr>`,
    )
    .join("");
  const cotCuoi = tienMat
    ? `<th style="width:16%">Ký nhận</th>`
    : `<th style="width:14%">Số tài khoản</th><th style="width:16%">Ngân hàng</th>`;

  win.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>Bảng kê ${escapeHtml(bk.code)}</title><style>
@page{size:A4 ${tienMat ? "portrait" : "landscape"};margin:12mm}
*{box-sizing:border-box}
body{font:12.5px "Times New Roman",serif;color:#000;margin:0}
h1{font-size:18px;text-align:center;margin:0 0 4px;letter-spacing:.5px}
.sub{text-align:center;font-style:italic;margin-bottom:10px}
.row{margin:3px 0}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{border:1px solid #000;padding:4px 5px;vertical-align:middle}
th{text-align:center;font-weight:700}
thead{display:table-header-group}
tr{page-break-inside:avoid}
.c{text-align:center}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.ky{height:30px}
.tong td{font-weight:700}
.words{font-style:italic;margin-top:6px}
.signs{display:flex;justify-content:space-between;gap:8px;text-align:center;margin-top:22px}
.sign{flex:1}
.sign-name{font-weight:700}
.sign-sub{font-style:italic;font-size:11px}
.sign-space{height:56px}
</style></head><body onload="window.print()">
<h1>BẢNG KÊ CHI ${bk.rows.every((r) => r.kind === "luong_dot_1") ? "LƯƠNG ĐỢT 1" : bk.rows.every((r) => r.kind !== "luong_dot_1") ? "TẠM ỨNG LƯƠNG" : "TẠM ỨNG / LƯƠNG ĐỢT 1"}</h1>
<div class="sub">Kèm theo ${tienMat ? "phiếu chi" : "ủy nhiệm chi"} số <b>${escapeHtml(bk.doc_no ?? bk.code)}</b> (${escapeHtml(bk.code)}) ngày ${escapeHtml(d)}/${escapeHtml(m)}/${escapeHtml(y)}</div>
<div class="row">Nội dung: <b>${escapeHtml(bk.content ?? "")}</b></div>
<div class="row">Số người: <b>${bk.so_nguoi}</b> · Số phiếu: <b>${bk.rows.length}</b> · Hình thức: <b>${tienMat ? "Tiền mặt" : "Chuyển khoản"}</b></div>
<table>
  <thead><tr>
    <th style="width:5%">STT</th><th style="width:9%">Mã NV</th><th>Họ và tên</th>
    <th style="width:14%">Phòng / tổ</th><th style="width:9%">Loại</th><th style="width:13%">Mã phiếu</th>
    <th style="width:11%">Số tiền</th>${cotCuoi}
  </tr></thead>
  <tbody>${dong}
    <tr class="tong"><td colspan="6" class="c">Tổng cộng</td><td class="num">${money(bk.tong)}</td>${tienMat ? "<td></td>" : "<td></td><td></td>"}</tr>
  </tbody>
</table>
<div class="words">(Bằng chữ: ${escapeHtml(amountInWords(bk.tong))}).</div>
<div class="signs">
  ${["Người lập biểu", "Kế toán trưởng", tienMat ? "Thủ quỹ" : "Giám đốc"]
    .map((n) => `<div class="sign"><div class="sign-name">${escapeHtml(n)}</div><div class="sign-sub">(Ký, họ tên)</div><div class="sign-space"></div></div>`)
    .join("")}
</div>
</body></html>`);
  win.document.close();
  win.focus();
  return true;
}

/** Tải bảng kê của phiếu chi rồi mở cửa sổ in — dùng chung cho màn Tạm ứng và sổ phiếu chi. Ném
 *  lỗi có câu tiếng Việt để nơi gọi hiện lên. */
export async function taiVaInBangKe(token: string, voucherId: number): Promise<void> {
  const bk = await api.accounting.bangKeTamUng(token, voucherId);
  if (!printBangKeTamUng(bk)) {
    throw new Error("Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.");
  }
}
