/** Format helpers dùng chung toàn app — tiền tệ, ngày tháng, in phiếu.
 *
 * Trước đây mỗi trang tự chép một bản `money`/`fmtDate`/`dateText` riêng;
 * gom về đây để sửa một chỗ là ăn mọi nơi. Trang nào cần định dạng KHÁC
 * (vd LuongPage hiện số trần không "đ") thì giữ helper cục bộ của nó.
 */

/** "1.234.567 đ" — số tiền VND đã quy đổi. */
export function money(value: number): string {
  return `${Math.round(value).toLocaleString("vi-VN")} đ`;
}

/** Số tiền nguyên tệ: VND → "1.234 đ", ngoại tệ → "1.234 USD". */
export function originalMoney(value: number, currency: string): string {
  return currency === "VND"
    ? money(value)
    : `${Math.round(value).toLocaleString("vi-VN")} ${currency}`;
}

/** "20/7/2026" theo vi-VN; rỗng → "—"; chuỗi không parse được → trả nguyên. */
export function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("vi-VN");
}

/** HẠN TRẢ suy từ MỐC CHỐT CÔNG NỢ: mốc + số ngày NCC cho nợ (chủ chốt 28/08/2026).
 *
 *  Chốt 31/8 + 30 ngày ⇒ 30/9. Để ở đây chứ không để mỗi màn tự cộng: cùng một con hạn mà màn
 *  Thu mua và màn Kế toán tính lệch nhau thì hai bên báo quá hạn hai ngày khác nhau.
 *  CHỈ để XEM TRƯỚC — con số thật do server tính (`han_tra_dot`), hai bên phải ra cùng kết quả.
 *  Thiếu vế nào cũng trả "—": mốc là ĐIỂM, số ngày là ĐỘ DÀI, không có đủ thì không ra hạn. */
export function hanTraTuMoc(
  moc?: string | null,
  soNgay?: number | null,
): string {
  if (!moc || soNgay == null) return "—";
  const d = new Date(`${moc}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  d.setDate(d.getDate() + soNgay);
  return d.toLocaleDateString("vi-VN");
}

/** Đếm ngược hạn giao → nhãn + mức khẩn (đổi màu). So 2 dữ kiện có sẵn (hạn vs hôm nay) — máy CHỈ
 *  trình bày theo data, KHÔNG mô hình dự đoán. `over` = quá/đúng hạn, `soon` = ≤3 ngày, `ok` = còn xa.
 *  Rỗng/không parse được → null (không hiện pill). Dùng chung: card tổ · list · detail. */
export function hanGiao(
  value?: string | null,
): { label: string; level: "over" | "soon" | "ok" } | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  const day = 86400000;
  const diff = Math.round(
    (Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) -
      Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / day,
  );
  if (diff < 0) return { label: `Quá hạn ${-diff} ngày`, level: "over" };
  if (diff === 0) return { label: "Hạn hôm nay", level: "over" };
  if (diff <= 3) return { label: `Còn ${diff} ngày`, level: "soon" };
  return { label: `Còn ${diff} ngày`, level: "ok" };
}

/** "20/07/2026" — giữ số 0 đệm, tách thẳng từ chuỗi ISO yyyy-mm-dd (không qua Date). */
export function fmtDateISO(value?: string | null): string {
  if (!value) return "—";
  const [y, m, d] = value.split("-");
  return d && m && y ? `${d}/${m}/${y}` : value;
}

/** Tách ngày/tháng/năm cho mẫu chứng từ "Ngày … tháng … năm …".
 *  Đọc thẳng chuỗi ISO — KHÔNG qua `new Date()` vì "2026-07-13" bị hiểu là UTC
 *  midnight, lệch 1 ngày ở múi giờ âm; trên chứng từ pháp lý là không chấp nhận được.
 *  Rỗng/không parse được → dấu chấm để viết tay. */
export function dmyParts(value?: string | null): { d: string; m: string; y: string } {
  const blank = { d: "......", m: "......", y: "............" };
  if (!value) return blank;
  const [y, m, d] = value.slice(0, 10).split("-");
  if (!y || !m || !d) return blank;
  return { d: String(Number(d)), m: String(Number(m)), y };
}

/** Ngày + giờ (có giây) theo giờ VN; rỗng → "—"; không parse được → trả nguyên.
 *  Backend lưu UTC nhưng SQLite trả ISO KHÔNG có hậu tố Z — nếu để nguyên,
 *  new Date() hiểu là giờ địa phương và hiển thị lệch −7h, nên chuỗi naive
 *  (có "T", không có Z/offset) được coi là UTC. */
export function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
  const d = new Date(!hasTz && value.includes("T") ? `${value}Z` : value);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

/** Escape chuỗi trước khi nhúng vào HTML in phiếu (window.open + document.write). */
export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function readTriple(value: number, full: boolean): string {
  const names = [
    "không",
    "một",
    "hai",
    "ba",
    "bốn",
    "năm",
    "sáu",
    "bảy",
    "tám",
    "chín",
  ];
  const hundred = Math.floor(value / 100);
  const ten = Math.floor((value % 100) / 10);
  const unit = value % 10;
  const parts: string[] = [];
  if (hundred > 0 || full) parts.push(`${names[hundred]} trăm`);
  if (ten > 1) {
    parts.push(`${names[ten]} mươi`);
    if (unit === 1) parts.push("mốt");
    else if (unit === 4) parts.push("tư");
    else if (unit === 5) parts.push("lăm");
    else if (unit > 0) parts.push(names[unit]);
  } else if (ten === 1) {
    parts.push("mười");
    if (unit === 5) parts.push("lăm");
    else if (unit > 0) parts.push(names[unit]);
  } else if (unit > 0) {
    if (hundred > 0 || full) parts.push("lẻ");
    parts.push(names[unit]);
  }
  return parts.join(" ");
}

/** Đọc số tiền thành chữ tiếng Việt: 1250000 → "Một triệu hai trăm năm mươi nghìn đồng". */
export function amountInWords(amount: number): string {
  let value = Math.max(0, Math.round(amount));
  if (value === 0) return "Không đồng";
  const scales = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"];
  const groups: number[] = [];
  while (value > 0) {
    groups.push(value % 1000);
    value = Math.floor(value / 1000);
  }
  const parts: string[] = [];
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    if (groups[i] === 0) continue;
    const words = readTriple(
      groups[i],
      i < groups.length - 1 && groups[i] < 100,
    );
    parts.push(`${words}${scales[i] ? ` ${scales[i]}` : ""}`);
  }
  const result = `${parts.join(" ")} đồng`;
  return result.charAt(0).toUpperCase() + result.slice(1);
}
