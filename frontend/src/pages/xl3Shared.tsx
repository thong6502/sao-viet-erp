// XẾP LỊCH 3 — helper THUẦN dùng chung ba mảnh của màn (Gantt · hàng chờ · panel).
//
// Ở đây KHÔNG gọi API, KHÔNG giữ state: chỉ số học ngày-giờ + hình học thanh + định dạng. Tách ra
// để lưới và panel không tự tính lệch nhau — cả hai phải quy ra pixel bằng ĐÚNG một công thức, nếu
// không thanh vẽ một đằng còn chữ nói một nẻo.
import type { Xl3Doan, Xl3DoanThucTe, Xl3Dong } from "../api/client";

/** Số ngày MỘT màn hình. Bảy vì tuần làm việc là đơn vị người điều độ nghĩ bằng — "lệnh này chạy
 *  hết tuần" là câu họ nói, không phải "hết 5,5 ngày". */
export const SO_NGAY = 7;
/** Bề rộng một ngày (px). Cột nhãn trái + 7 cột này = bề ngang lưới. */
export const NGAY_W = 168;
export const NHAN_W = 260;
export const DONG_H = 66;

/** Hình học lưới theo bề ngang cửa sổ. Cột nhãn là cột DÍNH (`position: sticky`) nên trên màn
 *  375px nó ăn 260/375 = 70% chỗ, lưới còn hơn trăm pixel — nhìn thấy đúng một mẩu thanh. Hai nấc
 *  hẹp co nhãn lại và hạ bề rộng một ngày để lưới còn thấy được.
 *
 *  HÀM THUẦN, cố ý: mọi phép quy đổi px↔giờ của lưới (`x`, `pxSangGio`, `khungBao`) đều nhận
 *  `ngayW` truyền vào, nên chỉ cần MỘT nguồn số cho cả vẽ lẫn kéo-thả. Ai gọi tự lo nghe `resize`.
 *  Bề ngang > 768px trả về ĐÚNG số cũ — màn rộng không đổi một pixel.
 *  Ngưỡng 768/480 khớp với @media §78 của `styles/responsive.css`; đổi ở đây phải đổi cả bên đó. */
export function khungLuoi(
  beNgang: number,
  soNgay: number,
): { nhanW: number; ngayW: number; dongH: number } {
  const ngayRong = (bay: number, muoiBon: number, baMuoi: number) =>
    soNgay === 30 ? baMuoi : soNgay === 14 ? muoiBon : bay;
  if (beNgang <= 480) return { nhanW: 184, ngayW: ngayRong(96, 64, 36), dongH: 72 };
  if (beNgang <= 768) return { nhanW: 184, ngayW: ngayRong(120, 76, 42), dongH: 72 };
  return { nhanW: NHAN_W, ngayW: ngayRong(NGAY_W, 96, 54), dongH: DONG_H };
}

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
export function x(iso: string | null | undefined, tu: string, ngayW = NGAY_W): number | null {
  const t = moc(iso);
  return t === null ? null : ((t - mocNgay(tu)) / NGAY_MS) * ngayW;
}

/** Pixel trên lưới → ISO naive, làm tròn về bội số `buoc` phút (mặc định 15).
 *  Làm tròn để kéo-thả ra giờ ĐỌC ĐƯỢC: không ai đặt lệnh chạy lúc 08:07. */
export function pxSangGio(px: number, tu: string, buoc = 15, ngayW = NGAY_W): string {
  const ms = mocNgay(tu) + (px / ngayW) * NGAY_MS;
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
export function khoiChay(doan: Xl3Doan[], tu: string, rongLuoi: number, ngayW = NGAY_W): Khoi[] {
  const ra: Khoi[] = [];
  for (const d of doan) {
    const a = x(d.tu, tu, ngayW);
    const b = x(d.den, tu, ngayW);
    if (a === null || b === null) continue;
    const trai = Math.max(0, a);
    const phai = Math.min(rongLuoi, b);
    if (phai - trai >= 2) ra.push({ trai, rong: phai - trai, buocIndex: d.buoc_index });
  }
  return ra;
}

/** Hai mép của cả lệnh trên bàn. Lệnh ĐÃ CHẠY DỞ bắt đầu ở lúc nó thật sự vào việc, KHÔNG ở mốc:
 *  mốc lúc đó là "bắt đầu phần còn lại" và nằm ở tương lai, vẽ từ đó thì bàn nói lệnh chưa bắt
 *  đầu trong khi tổ đã làm xong mấy bước. Mép phải cũng vậy — theo thực tế, không theo kế hoạch. */
export function veTu(dong: Xl3Dong): string | null {
  return dong.thuc_bat_dau_lenh ?? dong.bat_dau_at;
}

export function veDen(dong: Xl3Dong): string | null {
  return dong.ket_thuc_thuc_te ?? dong.ket_thuc;
}

/** Đoạn TỪ LÚC VÀO VIỆC tới mốc phần còn lại. Đây là dải "đã vào việc rồi NẰM CHỜ", KHÔNG phải
 *  "đã chạy": lệnh chạy 13 phút hôm 09/09 rồi chờ tới 06:00 14/09 thì dải này dài 5 ngày. Phần
 *  máy thật sự quay nằm ở `khoiThucTe`, vẽ đè lên trên. `null` khi lệnh chưa chạy, hoặc khi mốc
 *  đã bị kéo về TRƯỚC lúc vào việc (không còn đoạn nào để vẽ). */
export function khungDaVaoViec(
  dong: Xl3Dong, tu: string, rongLuoi: number, ngayW = NGAY_W,
): { trai: number; rong: number } | null {
  if (!dong.thuc_bat_dau_lenh) return null;
  const a = x(dong.thuc_bat_dau_lenh, tu, ngayW);
  const b = x(dong.bat_dau_at, tu, ngayW);
  if (a === null || b === null || b <= a) return null;
  const trai = Math.max(0, a);
  const phai = Math.min(rongLuoi, b);
  if (phai - trai < 2) return null;
  return { trai, rong: phai - trai };
}

/** Các quãng CHẠY THẬT bên trong dải chờ, đã kẹp vào cửa sổ. Toạ độ TUYỆT ĐỐI trên lưới —
 *  người gọi tự trừ đi mép trái của dải nếu vẽ chúng làm con của dải. */
export function khoiThucTe(
  doan: Xl3DoanThucTe[], tu: string, rongLuoi: number, ngayW = NGAY_W,
): { trai: number; rong: number; tu: string; den: string }[] {
  const ra: { trai: number; rong: number; tu: string; den: string }[] = [];
  for (const d of doan ?? []) {
    const a = x(d.tu, tu, ngayW);
    const b = x(d.den, tu, ngayW);
    if (a === null || b === null) continue;
    const trai = Math.max(0, a);
    const phai = Math.min(rongLuoi, b);
    // Ở lát 7 ngày, 13 phút chạy ra 1,5px. Vẫn phải THẤY được — đó là bằng chứng lệnh có chạy —
    // nên kéo lên 3px thay vì bỏ như `khoiChay` làm với vạch nhiễu bên trong thanh.
    if (phai > trai) ra.push({ trai, rong: Math.max(3, phai - trai), tu: d.tu, den: d.den });
  }
  return ra;
}

/** Khung BAO của PHẦN CÒN LẠI (thanh kéo được) đã kẹp vào cửa sổ, kèm cờ tràn hai mép. */
export function khungBao(
  dong: Xl3Dong, tu: string, rongLuoi: number, ngayW = NGAY_W,
): { trai: number; rong: number; tranTrai: boolean; tranPhai: boolean } | null {
  const a = x(dong.bat_dau_at, tu, ngayW);
  const b = x(veDen(dong), tu, ngayW);
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


export const THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export function nhanNgay(d: string): { thu: string; so: string; homNay: boolean } {
  const [y, mo, dd] = d.split("-").map(Number);
  const dt = new Date(y, mo - 1, dd);
  return { thu: THU[dt.getDay()], so: `${dd}/${mo}`, homNay: ymd(new Date()) === d };
}
