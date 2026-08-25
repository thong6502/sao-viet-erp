// Hàm dùng chung của màn Chấm công (tách từ pages/ChamCongPage.tsx).
import type {
  HeSoNgay,
  TimesheetDay,
  TimesheetRow,
  WorkShift,
} from "../../../../api/client";
import { SHIFT_TONES, WEEKDAY_NAMES_SHORT } from "./constants";
import type { PillO, ONgay, DongDacBiet, ShiftMeta } from "./types";

/** Đọc một ô ngày thành thứ hiển thị được: màu ô · giờ · dòng công · pill loại ngày.
 *
 *  ⚠️ MỘT HÀM cho CẢ HAI lịch (tự phục vụ + lịch NV trong màn HCNS). Trước 18/08/2026 hai chỗ
 *  vẽ ô bằng hai đoạn `if` chép tay và ĐÃ trôi khác nhau: bên HCNS hỏi `day.leave` trước nên
 *  ngày lễ hiện thành "Nghỉ phép (P)". Thêm nhãn mới cho từng bên là chép lỗi lần thứ ba.
 *
 *  TRẬT TỰ HỎI — GIỮ NGUYÊN, đừng "dọn":
 *   1. LƯỢT BẤM trước tiên. Ngày lễ / Chủ nhật ĐI LÀM vừa có giờ vào-ra vừa mang cờ ngày;
 *      hỏi cờ trước là nuốt mất giờ công thật (lỗi cũ của cả hai lịch).
 *   2. Trong nhánh có bấm: `plain > holiday > restday` — ĐÚNG thứ tự nhánh tính tiền bên Lương.
 *      Ngày `off1x` rơi vào Chủ nhật mà đọc thành `restday` là hứa 2× trong khi phiếu trả 1×.
 *
 *  Số công quy đổi = `cong × hệ số` chứ không phải hệ số trần: làm nửa ngày lễ thì được 2 công,
 *  đúng như engine tính (`holiday_cong × m_hol`). Viết cứng "4" là nói dối người làm nửa buổi.
 */
export function docONgay(day: TimesheetDay | undefined, heSo: HeSoNgay): ONgay {
  const o: ONgay = {
    variant: "",
    timeRange: "",
    statusLabel: "",
    gain: "",
    gainClass: "cc-month-cell__gain",
    pills: [],
    caLabel: "",
  };
  if (!day) return o;
  // Tên ca hiện DÙ NGÀY CÓ ĐI LÀM HAY KHÔNG: nó là ca ĐƯỢC PHÂN, không phải ca suy từ giờ bấm.
  // Ngày chưa tới / nghỉ vẫn cho thấy "hôm đó xếp ca gì" — đó chính là câu chủ hỏi.
  o.caLabel = day.shift_name ?? "";

  const quyDoi = (hs: number) =>
    day.cong != null ? `→ tính ${Number((day.cong * hs).toFixed(2))} công` : "";

  if (day.first_in || day.last_out) {
    o.variant = " cc-month-cell--work";
    if (day.late || day.early) o.variant += " cc-month-cell--makeup";
    o.timeRange = `${day.first_in ?? "?"} - ${day.last_out ?? "?"}`;
    o.statusLabel =
      day.cong != null
        ? `Công: ${day.cong}`
        : day.hours != null
          ? `${day.hours}h`
          : "Đã chấm";
    if (day.plain) {
      // Ngày công ty cho nghỉ mà vẫn đi làm: trả 1× phẳng, KHÔNG hệ số. Cố ý KHÔNG có dòng
      // "→ tính…" — thêm vào là gợi ý có tiền nhân, mà không hề có.
      o.pills.push({
        text: "NGHỈ",
        tone: "gray",
        title: "Ngày nghỉ của công ty — đi làm tính 1 công, không hệ số",
      });
    } else if (day.holiday) {
      o.pills.push({ text: "LỄ", tone: "red", title: day.leave ?? "Ngày lễ" });
      o.gain = quyDoi(heSo.le);
    } else if (day.restday) {
      o.pills.push({ text: "CN", tone: "purple", title: "Ngày nghỉ tuần — đi làm hưởng thêm" });
      o.gain = quyDoi(heSo.nghi_tuan);
      o.gainClass += " cc-month-cell__gain--restday";
    }
  } else if (day.holiday) {
    // Lễ KHÔNG tiêu ngày phép năm — gọi nó là "Nghỉ Phép (P)" là nói sai bản chất.
    o.variant = " cc-month-cell--holiday";
    o.statusLabel = "Nghỉ lễ — vẫn hưởng lương";
    o.pills.push({ text: "LỄ", tone: "red-soft", title: day.leave ?? "Ngày lễ" });
  } else if (day.leave) {
    o.variant = " cc-month-cell--holiday";
    o.statusLabel = day.leave_paid ? "Nghỉ Phép (P)" : "Nghỉ KL";
  } else if (day.planned_off) {
    // Nghỉ theo lịch xoay ca: dấu KẾ HOẠCH, không ra tiền, không tiêu phép — nên
    // để màu lặng như cuối tuần, đừng mượn màu lễ/phép.
    o.variant = " cc-month-cell--weekend";
    o.statusLabel = "Nghỉ theo lịch";
  }
  if (day.ot_minutes) {
    o.pills.push({ text: "+OT", tone: "orange", title: `Tăng ca: ${day.ot_minutes}′` });
  }
  return o;
}

/** Số công gọn: 1 chứ không phải 1.00, nhưng 0,5 công vẫn phải thấy. */
export const soCong = (v?: number | null) => Number((v ?? 0).toFixed(2));

/** Chip tóm tắt cho cột "Công đặc biệt" — rỗng ⇒ caller vẽ "—".
 *  Không bày chip rỗng: tháng không lễ thì ~90% hàng chẳng có gì, chip rỗng chỉ tổ làm bẩn cột. */
export function congDacBiet(row: TimesheetRow): PillO[] {
  const chips: PillO[] = [];
  if (soCong(row.restday_cong) > 0)
    chips.push({
      text: `${soCong(row.restday_cong)} CN`,
      tone: "purple",
      title: "Công làm ngày nghỉ tuần",
    });
  if (soCong(row.holiday_cong) > 0)
    chips.push({
      text: `${soCong(row.holiday_cong)} lễ`,
      tone: "red",
      title: "Công làm ngày lễ",
    });
  if (soCong(row.plain_cong) > 0)
    chips.push({
      text: `${soCong(row.plain_cong)} nghỉ`,
      tone: "gray",
      title: "Công làm ngày công ty cho nghỉ (1×, không hệ số)",
    });
  return chips;
}

/** Bung cột "Công đặc biệt" thành TỪNG NGÀY cho drawer — cột chỉ nói tổng, mà câu hỏi thật của
 *  kế toán là "ngày nào, mấy công, quy đổi ra bao nhiêu". */
export function ngayDacBiet(
  row: TimesheetRow,
  heSo: HeSoNgay,
  tenLe: Map<number, string>,
  year: number,
  month: number,
): DongDacBiet[] {
  const ds: DongDacBiet[] = [];
  for (const [k, day] of Object.entries(row.days)) {
    if (!day.first_in && !day.last_out) continue; // chỉ ngày CÓ ĐI LÀM mới sinh công đặc biệt
    const ngay = Number(k);
    const cong = soCong(day.cong);
    if (cong <= 0) continue;
    if (day.plain) {
      ds.push({ ngay, loai: "Ngày nghỉ công ty", ten: "trả 1× — không hệ số",
                cong, quyDoi: soCong(cong * heSo.off1x), tone: "gray" });
    } else if (day.holiday) {
      ds.push({ ngay, loai: "Ngày lễ", ten: tenLe.get(ngay) ?? "nghỉ lễ hưởng lương",
                cong, quyDoi: soCong(cong * heSo.le), tone: "red" });
    } else if (day.restday) {
      ds.push({ ngay, loai: "Nghỉ tuần", ten: WEEKDAY_NAMES_SHORT[getWeekdayIndex(year, month, ngay)],
                cong, quyDoi: soCong(cong * heSo.nghi_tuan), tone: "purple" });
    }
  }
  return ds.sort((a, b) => a.ngay - b.ngay);
}

export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  // Server gửi UTC. Nếu chuỗi thiếu nhãn múi giờ (SQLite trả naive) thì coi là UTC,
  // rồi luôn hiển thị theo giờ Việt Nam — không lệ thuộc múi giờ máy người xem.
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s);
  const d = new Date(hasTz ? s : `${s}Z`);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
}

/** Hôm nay dạng YYYY-MM-DD (giờ máy) — so chuỗi ISO là đủ để biết mốc ở tương lai. */
export function isoToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function fmtYmd(value: string | null | undefined): string {
  if (!value) return "Đến nay";
  const [y, m, d] = value.split("-");
  return y && m && d ? `${d}/${m}/${y}` : value;
}

export function normalizeTime24(value: string): string | null {
  const raw = value.trim();
  let hour: number;
  let minute: number;

  if (/^\d{1,2}$/.test(raw)) {
    hour = Number(raw);
    minute = 0;
  } else if (/^\d{3}$/.test(raw)) {
    hour = Number(raw.slice(0, 1));
    minute = Number(raw.slice(1));
  } else if (/^\d{4}$/.test(raw)) {
    hour = Number(raw.slice(0, 2));
    minute = Number(raw.slice(2));
  } else {
    const match = raw.match(/^(\d{1,2}):(\d{1,2})$/);
    if (!match) return null;
    hour = Number(match[1]);
    minute = Number(match[2]);
  }

  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/** "HH:MM:SS" đã trôi kể từ mốc `fromIso` (coi chuỗi thiếu nhãn là UTC như fmtDateTime). */
export function fmtElapsed(fromIso: string | null | undefined, now: number): string {
  if (!fromIso) return "00:00:00";
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(fromIso);
  const start = new Date(hasTz ? fromIso : `${fromIso}Z`).getTime();
  let s = Math.max(0, Math.floor((now - start) / 1000));
  const h = Math.floor(s / 3600);
  s -= h * 3600;
  const m = Math.floor(s / 60);
  s -= m * 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(h)}:${p(m)}:${p(s)}`;
}

/** Promise wrapper quanh navigator.geolocation. */
export function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("Trình duyệt không hỗ trợ định vị GPS."));
      return;
    }
    // Backstop: trên máy bàn Windows (không có GPS, Location service tắt) getCurrentPosition
    // có thể TREO mà không bắn timeout riêng của nó → nút "Đang lấy vị trí…" quay vô hạn.
    // Watchdog tự reject để lời gọi LUÔN kết thúc, UI kịp hiện lỗi + nút thử lại.
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(watchdog);
      fn();
    };
    const timeoutErr = Object.assign(new Error("Lấy vị trí quá lâu."), {
      code: 3,
    });
    const watchdog = setTimeout(() => finish(() => reject(timeoutErr)), 14000);
    navigator.geolocation.getCurrentPosition(
      (pos) => finish(() => resolve(pos)),
      (err) => finish(() => reject(err)),
      {
        // Máy bàn không có chip GPS → định vị mạng (WiFi/IP): nhanh, đỡ treo, đủ cho geofence 150 m.
        // Trong xưởng (indoor) GPS còn kém hơn network → cũng hợp use-case công nhân chấm công.
        enableHighAccuracy: false,
        timeout: 12000,
        maximumAge: 30000, // fix ≤30s được tái dùng → preview→chấm không phải dò lại
      },
    );
  });
}

export function geoErrText(e: unknown): string {
  const code = (e as { code?: number } | null)?.code;
  if (code === 1)
    return "Bạn đã từ chối quyền vị trí. Hãy cho phép định vị rồi thử lại.";
  if (code === 2)
    return "Không lấy được vị trí. Kiểm tra Dịch vụ định vị (Location) của Windows đã bật chưa.";
  if (code === 3)
    return "Lấy vị trí quá lâu. Kiểm tra mạng và Dịch vụ định vị của Windows rồi thử lại.";
  if (e instanceof Error) return e.message;
  return "Không lấy được vị trí.";
}

export function fmtDateVN(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function stripTones(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");
}

/** Luật deterministic: "ca <n>" → C<n> · "hành chính" → HC · qua đêm → K · còn lại viết tắt ≤3 ký tự. */
export function shiftShortCode(s: WorkShift): string {
  const plain = stripTones(s.name).trim();
  const numbered = plain.match(/ca\s*(\d+)/i);
  if (numbered) return `C${numbered[1]}`;
  if (/hanh\s*chinh/i.test(plain)) return "HC";
  if (s.is_overnight) return "K";
  const words = plain.split(/\s+/).filter(Boolean);
  if (words.length >= 2)
    return words
      .slice(0, 3)
      .map((w) => w[0])
      .join("")
      .toUpperCase();
  return (words[0] ?? "?").slice(0, 3).toUpperCase();
}

export function buildShiftMeta(shifts: WorkShift[]): Map<number, ShiftMeta> {
  const ordered = [...shifts].sort((a, b) => a.id - b.id); // màu bám thứ tự id tăng dần
  const used = new Map<string, number>();
  const out = new Map<number, ShiftMeta>();
  ordered.forEach((s, i) => {
    const base = shiftShortCode(s);
    const seen = used.get(base) ?? 0;
    used.set(base, seen + 1);
    out.set(s.id, {
      id: s.id,
      code: seen > 0 ? `${base}${seen + 1}` : base, // trùng thì nối chỉ số
      tone: SHIFT_TONES[i % SHIFT_TONES.length],
      name: s.name,
      title: `${s.name} · ${s.start_time}–${s.end_time}${s.is_overnight ? " (qua đêm)" : ""}`,
    });
  });
  return out;
}

export function getWeekdayIndex(year: number, month: number, day: number): number {
  return new Date(year, month - 1, day).getDay();
}

export function getWeekdayLabel(year: number, month: number, day: number): string {
  return WEEKDAY_NAMES_SHORT[getWeekdayIndex(year, month, day)];
}

export function isWeekend(year: number, month: number, day: number): boolean {
  const w = getWeekdayIndex(year, month, day);
  return w === 0 || w === 6; // 0 = CN, 6 = T7
}

export function getInitials(name?: string | null) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (
    parts[parts.length - 2][0] + parts[parts.length - 1][0]
  ).toUpperCase();
}

export function elErr(e: unknown): string {
  // Lỗi 400 của backend đã là tiếng Việt và khớp nhãn UI → hiện NGUYÊN VĂN, đừng viết lại.
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}
