// Hàm thuần (không JSX, không state) của màn Lương (tách từ pages/LuongPage.tsx).
// ⚠️ `money()` ở đây là bản CỤC BỘ của màn Lương (số trần, không hậu tố "đ") — xem ghi chú ở
// `utils/format.ts`. ĐỪNG thay bằng `money` của utils/format: ~96 chỗ trên màn này đang ăn nó.
import type { PayrollLine, SalaryAdvance } from "../../../../api/client";
import { MA_HOA_HONG } from "./constants";

export function money(n: number | null | undefined): string {
  if (n == null) return "0";
  return Math.round(n).toLocaleString("vi-VN");
}
export function fmtYmd(value: string | null | undefined): string {
  if (!value) return "Đến nay";
  const [y, m, d] = value.split("-");
  return y && m && d ? `${d}/${m}/${y}` : value;
}
export function curYm(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
/** Kỳ lệch `delta` tháng so với tháng này, dạng `YYYY-MM`. Luôn dựng từ ngày 1 để tháng 31 ngày
 *  không trượt sang tháng sau (31/01 + 1 tháng ra 03/03 nếu cộng thẳng vào ngày hiện tại). */
function ymOffset(delta: number): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
/** Khoảng kỳ lương HỢP LÝ cho một phiếu tạm ứng / lương đợt 1.
 *
 *  Ô "Kỳ lương" quyết định BẢNG LƯƠNG THÁNG NÀO trừ lại khoản ứng — gõ nhầm năm là tiền ra hôm
 *  nay mà sang năm sau mới thu lại, và không màn nào kêu lên vì kỳ đó chưa tồn tại (backend chỉ
 *  chặn kỳ ĐÃ CHỐT / ĐÃ CHI). Nên chặn ngay ở ô:
 *    · `max` = tháng SAU tháng này — ứng trước cho kỳ tới là việc thật, xa hơn là gõ nhầm;
 *    · `min` = 12 tháng trước — xa hơn nữa thì kỳ đó chắc chắn đã chốt/đã chi rồi. */
export function khoangKyUng(): { min: string; max: string } {
  return { min: ymOffset(-12), max: ymOffset(1) };
}
/** `YYYY-MM` → `MM/YYYY` để đọc trong câu tiếng Việt. */
export function ymLabel(ym: string): string {
  const [y, m] = ym.split("-");
  return y && m ? `${m}/${y}` : ym;
}

/** Câu + sắc thái cho trạng thái kỳ lương, hiện NGAY dưới ô Kỳ lương ở modal tạm ứng.
 *
 *  Trả `null` = CHƯA BIẾT (đang tải, hoặc không có quyền `luong:read` để đọc danh sách kỳ) ⇒ im
 *  lặng, đừng đoán. Đoán sai ở đây tệ hơn không nói gì: backend vẫn là chốt chặn thật. */
export function trangThaiKyUng(
  status: string | null,
): { text: string; tone: "muted" | "ok" | "bad" } | null {
  if (status === null) return null;
  if (status === "chua_tao")
    return {
      text: "Kỳ này chưa tạo — phiếu vẫn lập được, sẽ trừ khi kỳ được tính lương.",
      tone: "muted",
    };
  if (status === "draft")
    return {
      text: "Kỳ đang mở — khoản ứng sẽ trừ vào bảng lương tháng này.",
      tone: "ok",
    };
  if (status === "locked")
    return { text: "Kỳ đã chốt — không lập được phiếu cho kỳ này.", tone: "bad" };
  if (status === "paid")
    return { text: "Kỳ đã chi — không lập được phiếu cho kỳ này.", tone: "bad" };
  // Máy chủ thêm trạng thái mới mà màn chưa biết: nói chung chung còn hơn nói SAI, và KHÔNG tự
  // khoá nút — khoá nhầm là chặn việc thật (cùng cách xử của `lyDoChuaCoPhieu`).
  return {
    text: "Chưa rõ trạng thái kỳ này — cứ gửi, máy chủ sẽ báo nếu kỳ đã khoá.",
    tone: "muted",
  };
}

// Hôm nay dạng YYYY-MM-DD, dựng từ giờ ĐỊA PHƯƠNG (không dùng toISOString để tránh
// lệch 1 ngày khi ở múi giờ VN lúc rạng sáng).
export function todayYmd(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

/** 6 cột thưởng NGỪNG GHI từ 28/07/2026 — giữ lại vì kỳ đã chốt vẫn có số. */
export function legacyBonusRows(l: PayrollLine): [string, number][] {
  return (
    [
      ["Phép năm", l.phep_nam],
      ["Thưởng 5S", l.thuong_5s],
      ["Thưởng doanh số", l.thuong_doanh_so],
      ["Thưởng thành tích", l.thuong_thanh_tich],
      ["Trả đồng phục", l.tra_dong_phuc],
      ["Thưởng khác", l.other_bonus],
    ] as [string, number][]
  ).filter(([, v]) => (v ?? 0) !== 0);
}

/** Từng khoản THƯỞNG của kỳ này (cột "Thưởng" trên bảng + tooltip).
 *
 * ⚠️ KHÔNG lấy khoản `source='employee'`: nó đã nằm trong `allowance` → hiện ở cột "Phụ cấp";
 * gộp cả hai vào đây là bảng đếm đôi tiền của cùng một khoản. Còn `auto` thì PHẢI có: nó nằm
 * ngoài `allowance`, cộng thẳng vào `gross`. Giữ ĐỒNG BỘ với `_bonus_total()` ở BE.
 *
 * ⭐ TRỪ hoa hồng — nay có cột riêng. Gộp nó vào đây là cách cũ, và cách cũ khiến chủ mở bảng
 * lương tìm mãi không thấy hoa hồng đâu: nó lẫn với thưởng nóng trong một con số, chi tiết chỉ
 * hiện khi rê chuột. Tiền máy tự tính từ phân hệ khác thì phải mang đúng tên nó trên bảng. */
export function bonusRows(l: PayrollLine): [string, number][] {
  return [
    ...(l.components ?? [])
      .filter(
        (c) =>
          c.kind !== "tru" &&
          (c.source === "line" || c.source === "auto") &&
          c.code !== MA_HOA_HONG,
      )
      .map(
        (c) =>
          [c.note ? `${c.name} (${c.note})` : c.name, c.amount] as [
            string,
            number,
          ],
      ),
    ...legacyBonusRows(l),
  ];
}
export function bonusTotal(l: PayrollLine): number {
  return bonusRows(l).reduce((s, [, v]) => s + v, 0);
}
export function bonusTitle(l: PayrollLine): string {
  const rows = bonusRows(l);
  return rows.length
    ? rows.map(([k, v]) => `${k}: ${money(v)}`).join(" · ")
    : "";
}

/** Cột "Hoa hồng kinh doanh" — máy tự tính theo hoá đơn bán trong kỳ, HCNS không gõ tay.
 *  Số 0 nghĩa là chưa khai `commission_pct` ở hồ sơ lương của người kinh doanh: không khai % thì
 *  lúc chốt đơn chụp về rỗng, và mọi bước sau đều bằng 0. */
export function hoaHongTotal(l: PayrollLine): number {
  return (l.components ?? [])
    .filter((c) => c.kind !== "tru" && c.code === MA_HOA_HONG)
    .reduce((s, c) => s + c.amount, 0);
}

/** Map 1 bản ghi tạm ứng → dữ liệu phiếu in "Giấy đề nghị tạm ứng". */
export function advPrintData(a: SalaryAdvance) {
  return {
    code: a.code,
    employeeName: a.employee_name,
    departmentName: a.department_name,
    bankAccount: a.bank_account,
    bankName: a.bank_name,
    amount: a.amount,
    advanceDate: a.advance_date,
    periodMonth: a.period_month,
    periodYear: a.period_year,
    reason: a.reason,
    kind: a.kind,
  };
}
