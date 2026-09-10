// XẾP LỊCH 3 — helper THUẦN dùng chung ba mảnh của màn (Gantt · hàng chờ · panel).
//
// Ở đây KHÔNG gọi API, KHÔNG giữ state: chỉ số học ngày-giờ + hình học thanh + định dạng. Tách ra
// để lưới và panel không tự tính lệch nhau — cả hai phải quy ra pixel bằng ĐÚNG một công thức, nếu
// không thanh vẽ một đằng còn chữ nói một nẻo.
import type { Xl3Doan, Xl3Dong } from "../api/client";

/** Số ngày MỘT màn hình. Bảy vì tuần làm việc là đơn vị người điều độ nghĩ bằng — "lệnh này chạy
 *  hết tuần" là câu họ nói, không phải "hết 5,5 ngày". */
export const SO_NGAY = 7;
/** Bề rộng một ngày (px). Cột nhãn trái + 7 cột này = bề ngang lưới. */
export const NGAY_W = 168;
export const NHAN_W = 250;
export const DONG_H = 52;

// ---------------------------------------------------------------- ngày tháng
export function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function themNgay(s: string, n: number): string {
  const [y, mo, d] = s.split("-").map(Number);
  return ymd(new Date(y, mo - 1, d + n));
}

/** Thứ Hai của tuần chứa `d`. Cửa sổ luôn bắt đầu từ thứ Hai — nhảy tuần mà mốc trôi theo ngày bấm
 *  thì hai lần mở màn ra hai khung khác nhau, người dùng mất điểm neo. */
export function dauTuan(d: Date): string {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  t.setDate(t.getDate() - ((t.getDay() + 6) % 7));
  return ymd(t);
}

/** ISO naive (giờ nhà máy, KHÔNG đổi múi) → mốc mili-giây để tính hình học. */
export function moc(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]).getTime();
}

export function mocNgay(d: string): number {
  const [y, mo, dd] = d.split("-").map(Number);
  return new Date(y, mo - 1, dd).getTime();
}

const NGAY_MS = 86_400_000;

/** Vị trí trái (px) của một mốc trong cửa sổ bắt đầu từ `tu`. Cho phép ÂM / vượt phải — nơi gọi
 *  tự kẹp, vì thanh tràn mép phải vẫn phải vẽ được nửa nằm trong. */
export function x(iso: string | null | undefined, tu: string): number | null {
  const t = moc(iso);
  return t === null ? null : ((t - mocNgay(tu)) / NGAY_MS) * NGAY_W;
}

/** Pixel trên lưới → ISO naive, làm tròn về bội số `buoc` phút (mặc định 15).
 *  Làm tròn để kéo-thả ra giờ ĐỌC ĐƯỢC: không ai đặt lệnh chạy lúc 08:07. */
export function pxSangGio(px: number, tu: string, buoc = 15): string {
  const ms = mocNgay(tu) + (px / NGAY_W) * NGAY_MS;
  const b = buoc * 60_000;
  const d = new Date(Math.round(ms / b) * b);
  return `${ymd(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

// ---------------------------------------------------------------- hình học thanh
export interface Khoi {
  trai: number;
  rong: number;
  buocIndex: number;
}

/** Khối CHẠY bên trong thanh (lớp đậm). Cắt theo cửa sổ và bỏ khối mảnh hơn 2px — vẽ vạch 0,3px
 *  chỉ tạo nhiễu, người nhìn tưởng lỗi render. */
export function khoiChay(doan: Xl3Doan[], tu: string, rongLuoi: number): Khoi[] {
  const ra: Khoi[] = [];
  for (const d of doan) {
    const a = x(d.tu, tu);
    const b = x(d.den, tu);
    if (a === null || b === null) continue;
    const trai = Math.max(0, a);
    const phai = Math.min(rongLuoi, b);
    if (phai - trai >= 2) ra.push({ trai, rong: phai - trai, buocIndex: d.buoc_index });
  }
  return ra;
}

/** Khung BAO của cả lệnh (lớp nhạt) đã kẹp vào cửa sổ, kèm cờ tràn hai mép để vẽ mũi nhọn. */
export function khungBao(
  dong: Xl3Dong, tu: string, rongLuoi: number,
): { trai: number; rong: number; tranTrai: boolean; tranPhai: boolean } | null {
  const a = x(dong.bat_dau_at, tu);
  const b = x(dong.ket_thuc, tu);
  if (a === null || b === null) return null;
  const trai = Math.max(0, a);
  const phai = Math.min(rongLuoi, b);
  if (phai <= 0 || trai >= rongLuoi) return null;
  return { trai, rong: Math.max(6, phai - trai), tranTrai: a < 0, tranPhai: b > rongLuoi };
}

// ---------------------------------------------------------------- định dạng
export function gio(iso: string | null | undefined): string {
  const m = iso?.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[4]}:${m[5]} ${m[3]}/${m[2]}` : "—";
}

export function ngayNgan(iso: string | null | undefined): string {
  const m = iso?.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}` : "—";
}

/** Phút → "2 ngày 3 giờ" theo NGÀY LÀM VIỆC 8 tiếng. Quy ra ngày lịch (24h) là nói dối: 600 phút
 *  chạy không phải "nửa ngày", nó là gần hai ca. */
export function thoiLuong(phut: number | null | undefined): string {
  const p = Math.round(phut ?? 0);
  if (p <= 0) return "—";
  if (p < 60) return `${p} phút`;
  const gioTong = p / 60;
  if (gioTong < 8) return `${gioTong.toFixed(gioTong < 10 ? 1 : 0)} giờ`;
  const ngayLam = Math.floor(gioTong / 8);
  const du = Math.round(gioTong % 8);
  return du ? `${ngayLam} ngày ${du} giờ` : `${ngayLam} ngày`;
}

/** Trễ hạn SX bao nhiêu ngày (âm = còn sớm, null = chưa đủ dữ kiện). Màn KHÔNG chặn theo số này —
 *  nó chỉ đổi màu để người điều độ tự quyết. */
export function treHan(dong: { ket_thuc: string | null; han_hoan_thanh_sx: string | null }): number | null {
  const kt = moc(dong.ket_thuc);
  if (kt === null || !dong.han_hoan_thanh_sx) return null;
  const han = mocNgay(dong.han_hoan_thanh_sx) + NGAY_MS - 1;   // hết ngày hạn
  return Math.ceil((kt - han) / NGAY_MS);
}

export function classHan(dong: { ket_thuc: string | null; han_hoan_thanh_sx: string | null }): string {
  const t = treHan(dong);
  if (t === null) return "";
  if (t > 0) return "xl3--tre";
  if (t >= -1) return "xl3--sat";
  return "";
}

export function cuoiTuan(d: string): boolean {
  const [y, mo, dd] = d.split("-").map(Number);
  const w = new Date(y, mo - 1, dd).getDay();
  return w === 0 || w === 6;
}

export const THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export function nhanNgay(d: string): { thu: string; so: string; homNay: boolean } {
  const [y, mo, dd] = d.split("-").map(Number);
  const dt = new Date(y, mo - 1, dd);
  return { thu: THU[dt.getDay()], so: `${dd}/${mo}`, homNay: ymd(new Date()) === d };
}
