// Hàm dùng chung của màn Tăng ca (tách từ pages/TangCaPage.tsx).
export function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

/** Phút-trên-trục-ngày-công → "HH:MM" (kèm "+1" nếu đã sang hôm sau). */
export function minToHhmm(m: number): string {
  const day = Math.floor(m / 1440);
  const rem = ((m % 1440) + 1440) % 1440;
  const s = `${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
  return day > 0 ? `${s} (+${day})` : s;
}

/** Phút → "HH:MM" thuần (không kèm "+1") để đổ vào ô nhập; lấy phần trong ngày. */
export function plainHhmm(m: number): string {
  const rem = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

export function hhmmToMin(v: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(v.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return null;
  return h * 60 + mi;
}

/** ĐỘ DÀI tính bằng phút → "40h" / "8h30". Bản sao ĐÚNG của `_gio_phut` ở
 *  `backend/app/services/overtime_service.py` — hai bên phải in ra cùng một chuỗi, nếu không
 *  câu chặn của FE và câu 400 của backend nói hai kiểu cho cùng một lỗi.
 *  ⚠ KHÁC `minToHhmm`: cái kia là MỐC giờ trên trục ngày công, in 2400 phút thành "16:40 (+1)"
 *  là vô nghĩa với người đọc số dư trần tháng. */
export function gioPhut(minute: number): string {
  const m = Math.max(0, Math.round(minute));
  const g = Math.floor(m / 60);
  const ph = m % 60;
  return ph ? `${g}h${String(ph).padStart(2, "0")}` : `${g}h`;
}

/** "YYYY-MM" của hôm nay theo giờ máy — mốc mặc định của dải số dư khi chưa chọn ngày công.
 *  KHÔNG qua `toISOString()`: hàm đó đổi sang UTC nên 07:00 ngày 01 ở VN ra ngày 31 tháng trước. */
export function thangHomNay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
