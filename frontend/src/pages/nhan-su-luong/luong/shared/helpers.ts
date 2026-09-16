// Hàm thuần (không JSX, không state) của màn Lương (tách từ pages/LuongPage.tsx).
// ⚠️ `money()` ở đây là bản CỤC BỘ của màn Lương (số trần, không hậu tố "đ") — xem ghi chú ở
// `utils/format.ts`. ĐỪNG thay bằng `money` của utils/format: ~96 chỗ trên màn này đang ăn nó.
import type { PayrollLine, SalaryAdvance } from "../../../../api/client";

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

/** TỪNG khoản PHẠT / KHẤU TRỪ của một dòng lương — ĐÚNG những dòng mà phiếu lương in ở cột
 *  "Các khoản TRỪ", để bảng lương và phiếu lương kể cùng một câu chuyện.
 *
 *  ⚠️ Trước 16/09/2026 cột "Vi phạm" trên bảng chỉ đọc `vi_pham`: ai bị "Phạt biên bản" /
 *  "Đi trễ" / "Điện thoại vượt trội" / "Đồng phục · 5S" hay khoản danh mục loại TRỪ thì bảng
 *  hiện dấu gạch trong khi tiền vẫn bị trừ khỏi thực nhận — chủ phát hiện 16/09/2026 (NV
 *  "Test Luồng 0809" bị phạt biên bản 50.000 mà bảng không hiện). Trừ gì phải hiện nấy. */
export function phatRows(l: PayrollLine): [string, number][] {
  const rows: [string, number][] = [
    ["Đi trễ / nghỉ KP", l.di_tre ?? 0],
    ["Điện thoại vượt trội", l.dt_vuot_troi ?? 0],
    ["Phạt biên bản", l.phat_bien_ban ?? 0],
    ["Đồng phục / phạt 5S", l.phat_5s_dong_phuc ?? 0],
    ["Giảm trừ khác", l.vi_pham ?? 0],
    // Khoản danh mục loại TRỪ (mua đồng phục, ứng vật tư…) — trừ thẳng vào thực nhận, KHÔNG
    // thuộc trần 30% Điều 102, nhưng vẫn là tiền bị trừ nên vẫn phải hiện ra bảng.
    ...(l.components ?? [])
      .filter((c) => c.kind === "tru")
      .map(
        (c) =>
          [c.note ? `${c.name} (${c.note})` : c.name, c.amount] as [
            string,
            number,
          ],
      ),
  ];
  return rows.filter(([, v]) => (v ?? 0) !== 0);
}

/** BHXH bắt buộc + đoàn phí công đoàn + thuế TNCN — ba khoản trừ theo luật, gộp MỘT cột cho đỡ
 *  rộng. Trước 16/09/2026 cột đó chỉ hiện `bhxh`, còn đoàn phí và thuế TNCN không cột nào kể. */
export function bhThueRows(l: PayrollLine): [string, number][] {
  return (
    [
      ["BHXH/BHYT/BHTN", l.bhxh ?? 0],
      ["Đoàn phí công đoàn", l.cong_doan ?? 0],
      ["Thuế TNCN", l.pit ?? 0],
    ] as [string, number][]
  ).filter(([, v]) => v !== 0);
}

/** Cột "Phụ cấp" của bảng lương — ĐỦ những khoản phụ cấp engine cộng vào `gross`.
 *
 *  ⚠️ Trước 16/09/2026 cột này chỉ đọc `allowance`, bỏ quên cơm ca · cơm tăng ca · phụ cấp ca
 *  (ba khoản này nằm NGOÀI `allowance`, phiếu lương in riêng từng dòng) ⇒ cộng hết các cột thu
 *  của bảng vẫn thiếu tiền so với thực lĩnh — NV002 kỳ 09/2026 lệch đúng 100.000đ cơm tăng ca. */
export function phuCapRows(l: PayrollLine): [string, number][] {
  const rows: [string, number][] = [
    ["Phụ cấp khác", l.allowance ?? 0],
    ["Cơm ca", l.meal_allowance_pay ?? 0],
    ["Cơm tăng ca", l.com_tang_ca_pay ?? 0],
    ["Phụ cấp ca (theo ca làm)", l.shift_allowance_pay ?? 0],
  ];
  return rows.filter(([, v]) => v !== 0);
}
export function phuCapTotal(l: PayrollLine): number {
  return phuCapRows(l).reduce((s, [, v]) => s + v, 0);
}

/** Tooltip liệt kê từng khoản của một cột GỘP. `dau` = dấu đứng trước số (cột TRỪ để "−"). */
export function chiTiet(rows: [string, number][], dau = "−"): string {
  return rows.map(([k, v]) => `${k}: ${dau}${money(v)}`).join(" · ");
}

/** Từng khoản THƯỞNG của kỳ này (cột "Thưởng" trên bảng + tooltip).
 *
 * ⚠️ KHÔNG lấy khoản `source='employee'`: nó đã nằm trong `allowance` → hiện ở cột "Phụ cấp";
 * gộp cả hai vào đây là bảng đếm đôi tiền của cùng một khoản. Giữ ĐỒNG BỘ với `_bonus_total()`
 * ở BE.
 *
 * ⭐ Hoa hồng KHÔNG ở đây — nó là cột riêng `hoa_hong` trên dòng lương (07/09/2026). Trước đó nó
 * là dòng khoản nguồn `auto`, và có lúc bị gộp vào Thưởng khiến chủ tìm mãi không thấy. Tiền máy
 * tự tính từ phân hệ khác thì phải mang đúng tên nó trên bảng. */
export function bonusRows(l: PayrollLine): [string, number][] {
  return [
    // Điều chỉnh lương (±) — engine CỘNG vào `gross`, phiếu lương in một dòng riêng. Bảng lương
    // không có cột riêng nên gửi nhờ cột "Thưởng" (16/09/2026); không thì cộng hết các cột thu
    // vẫn không ra `gross`, và tiền cộng/trừ tay biến mất khỏi bảng.
    ...((l.dieu_chinh_luong ?? 0) !== 0
      ? ([["Điều chỉnh lương", l.dieu_chinh_luong ?? 0]] as [string, number][])
      : []),
    ...(l.components ?? [])
      .filter((c) => c.kind !== "tru" && c.source === "line")
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

/** Cột "Hoa hồng kinh doanh" — cột riêng `hoa_hong` trên dòng lương (07/09/2026), máy tự tính
 *  theo hoá đơn bán trong kỳ, HCNS không gõ tay. Số 0 nghĩa là chưa khai `commission_pct` ở hồ sơ
 *  lương của người kinh doanh: không khai % thì lúc chốt đơn chụp về rỗng. */
export function hoaHongTotal(l: PayrollLine): number {
  return l.hoa_hong ?? 0;
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
