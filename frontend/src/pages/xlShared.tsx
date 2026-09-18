// XẾP LỊCH 3 — helper THUẦN dùng chung ba mảnh của màn (Gantt · hàng chờ · panel).
//
// Ở đây KHÔNG gọi API, KHÔNG giữ state: chỉ số học ngày-giờ + hình học thanh + định dạng. Tách ra
// để lưới và panel không tự tính lệch nhau — cả hai phải quy ra pixel bằng ĐÚNG một công thức, nếu
// không thanh vẽ một đằng còn chữ nói một nẻo.
import type { XlDoan, XlDoanThucTe, XlDong } from "../api/client";

/** Số ngày MỘT màn hình. Bảy vì tuần làm việc là đơn vị người điều độ nghĩ bằng — "lệnh này chạy
 *  hết tuần" là câu họ nói, không phải "hết 5,5 ngày". */
export const SO_NGAY = 7;
/** Bề rộng một ngày (px). Cột nhãn trái + 7 cột này = bề ngang lưới. */
export const NGAY_W = 168;
export const NHAN_W = 260;
/** Đủ cho BỐN dòng nhãn (mã · tên · khách · sản lượng/tờ/con) và, bên lưới, một dải chữ dưới
 *  thanh cho vạch "hạn SX" / "giao khách". */
export const DONG_H = 90;

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
  const nac = nacCuaSo(soNgay);
  const ngayRong = (bay: number, muoiBon: number, baMuoi: number) =>
    nac === 30 ? baMuoi : nac === 14 ? muoiBon : bay;
  if (beNgang <= 480) return { nhanW: 184, ngayW: ngayRong(96, 64, 36), dongH: 90 };
  if (beNgang <= 768) return { nhanW: 184, ngayW: ngayRong(120, 76, 42), dongH: 90 };
  return { nhanW: NHAN_W, ngayW: ngayRong(NGAY_W, 96, 54), dongH: DONG_H };
}

/** Nấc hiển thị của cửa sổ — 7, 14 hay 30 ngày. Ba nút có sẵn rơi đúng nấc của mình; khoảng tự
 *  chọn (20 ngày, 45 ngày…) rơi vào nấc có bề ngang lưới gần nhất. Bề rộng một ngày và kiểu đầu cột
 *  ngày đều đọc nấc này, nên khoảng lẻ dùng lại đúng bộ số đã chỉnh cho ba nấc chứ không đẻ cỡ mới. */
export function nacCuaSo(soNgay: number): 7 | 14 | 30 {
  return soNgay <= 9 ? 7 : soNgay <= 20 ? 14 : 30;
}

/** Trần một lần xem. `/lich` trải MỌI lệnh chạm cửa sổ, cửa sổ càng dài càng nặng — hai tháng là đủ
 *  cho người điều độ nhìn trước, dài hơn thì lùi/tiến bằng mũi tên. */
export const SO_NGAY_TOI_DA = 60;

export const NGAY_NHAP_MIN = "2000-01-01";
export const NGAY_NHAP_MAX = "2099-12-31";

/** Số ngày tính cả hai đầu của khoảng `tu`..`den` (YYYY-MM-DD). Đếm theo UTC để giờ mùa hè không
 *  làm hụt một ngày. */
export function soNgayGiua(tu: string, den: string): number {
  const [y1, m1, d1] = tu.split("-").map(Number);
  const [y2, m2, d2] = den.split("-").map(Number);
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86_400_000) + 1;
}

/** Lời nhắc cho ô chọn khoảng ngày, `null` = dùng được. Ô `date` nhận năm 6 chữ số và năm gõ dở
 *  (0020) nên soi khuôn + khoảng, không tin mỗi `min`/`max` trên thẻ. */
export function loiKhoangNgay(tu: string, den: string): string | null {
  const hopLe = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v) && v >= NGAY_NHAP_MIN && v <= NGAY_NHAP_MAX;
  if (!tu || !den) return "Chọn đủ từ ngày và đến ngày.";
  if (!hopLe(tu) || !hopLe(den)) return "Ngày không hợp lệ.";
  if (den < tu) return "Đến ngày phải từ ngày bắt đầu trở đi.";
  if (soNgayGiua(tu, den) > SO_NGAY_TOI_DA) return `Mỗi lần xem tối đa ${SO_NGAY_TOI_DA} ngày.`;
  return null;
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
export function khoiChay(doan: XlDoan[], tu: string, rongLuoi: number, ngayW = NGAY_W): Khoi[] {
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
export function veTu(dong: XlDong): string | null {
  return dong.thuc_bat_dau_lenh ?? dong.bat_dau_at;
}

export function veDen(dong: XlDong): string | null {
  return dong.ket_thuc_thuc_te ?? dong.ket_thuc;
}

/** Đoạn TỪ LÚC VÀO VIỆC tới mốc phần còn lại. Đây là dải "đã vào việc rồi NẰM CHỜ", KHÔNG phải
 *  "đã chạy": lệnh chạy 13 phút hôm 09/09 rồi chờ tới 06:00 14/09 thì dải này dài 5 ngày. Phần
 *  máy thật sự quay nằm ở `khoiThucTe`, vẽ đè lên trên. `null` khi lệnh chưa chạy, hoặc khi mốc
 *  đã bị kéo về TRƯỚC lúc vào việc (không còn đoạn nào để vẽ). */
export function khungDaVaoViec(
  dong: XlDong, tu: string, rongLuoi: number, ngayW = NGAY_W,
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
  doan: XlDoanThucTe[], tu: string, rongLuoi: number, ngayW = NGAY_W,
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
  dong: XlDong, tu: string, rongLuoi: number, ngayW = NGAY_W,
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

/** "10/09 19:00" — ngày đứng trước giờ, cho nhãn "xong …" cạnh thanh: mắt đang dò theo trục NGÀY
 *  nên ngày phải đọc được trước. */
export function ngayGio(iso: string | null | undefined): string {
  const m = iso?.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : "—";
}

/** Phút → "63h15". Giờ ĐỒNG HỒ, không quy ra "ngày làm 8 tiếng": đây là tổng giờ máy
 *  của nhiều lệnh cộng lại, "7 ngày 7 giờ" đọc thành một lệnh chạy một tuần. */
export function gioPhut(phut: number): string {
  const p = Math.max(0, Math.round(phut));
  return `${Math.floor(p / 60)}h${String(p % 60).padStart(2, "0")}`;
}

/** Tổng phút MÁY CHẠY nằm TRONG cửa sổ `[tu, tu + soNgay)`. Chỉ cộng phần giao với cửa sổ — lệnh vắt
 *  qua mép chỉ được tính phần thật sự nằm trong khoảng đang xem. Cộng cả hai lớp khối chạy của
 *  thanh: `doan` (phần còn lại theo kế hoạch) và `doan_thuc_te` (quãng máy đã quay thật); hai lớp
 *  không chồng nhau vì một bên nằm trước mốc, một bên sau.
 *  Cộng ở FE được vì `/lich` trả TRỌN mọi lệnh chạm cửa sổ, không phân trang. */
export function phutChayTrongCuaSo(dong: XlDong[], tu: string, soNgay: number): number {
  const a = mocNgay(tu);
  const b = a + soNgay * NGAY_MS;
  let tong = 0;
  for (const d of dong) {
    for (const k of [...d.doan, ...(d.doan_thuc_te ?? [])]) {
      const t0 = moc(k.tu);
      const t1 = moc(k.den);
      if (t0 === null || t1 === null) continue;
      tong += Math.max(0, Math.min(t1, b) - Math.max(t0, a));
    }
  }
  return tong / 60_000;
}

/** Phút → "6 giờ 30 phút" / "45 phút" — giờ ĐỒNG HỒ cho mọi thời lượng của màn: giờ chạy của bước,
 *  của lệnh, phần nghỉ. KHÔNG quy ra "ngày làm 8 tiếng": hàm cũ `thoiLuong` (gỡ 14/09/2026) ghi 20 giờ
 *  đóng gói thành "2 ngày 4 giờ", người đọc hiểu 48 giờ; còn chủ nhật 24 giờ nằm chờ thành "3 ngày". */
export function gioChu(phut: number | null | undefined): string {
  const p = Math.max(0, Math.round(phut ?? 0));
  const g = Math.floor(p / 60);
  const m = p % 60;
  if (!g) return `${m} phút`;
  return m ? `${g} giờ ${m} phút` : `${g} giờ`;
}

/** Phút ĐỒNG HỒ giữa hai mốc → "1 ngày 19 giờ" (ngày 24 tiếng) / "3 giờ 4 phút". Cho độ LỆCH giữa
 *  mốc kế hoạch và mốc thực tế: quy theo "ngày làm 8 tiếng" thì 43 giờ thành "5 ngày 3 giờ" — khớp
 *  cả lịch lẫn giờ ca đều không. */
export function quangDongHo(phut: number | null | undefined): string {
  const p = Math.max(0, Math.round(phut ?? 0));
  if (p < 1440) return gioChu(p);
  const gioTong = Math.round(p / 60);
  const ngay = Math.floor(gioTong / 24);
  const g = gioTong % 24;
  return g ? `${ngay} ngày ${g} giờ` : `${ngay} ngày`;
}

/** "2026-09-13" → "CN 13/09". */
export function thuNgay(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${THU[new Date(+m[1], +m[2] - 1, +m[3]).getDay()]} ${m[3]}/${m[2]}`;
}

/** Diễn giải `nghi_ngoai_ca_phut` của panel — bốn loại `*_phut` cộng lại đúng con số gộp. */
export interface XlKhungLap { tu: string; den: string; so_lan: number; phut: number }
export interface XlPhanTachNghi {
  ca_san_xuat: { tu: string; den: string }[];
  /** Từng ca có tên + bữa nghỉ đã khai; rỗng khi xưởng chưa khai ca (khung lùi) — dùng `ca_san_xuat`. */
  cac_ca?: { ten: string; tu: string; den: string; nghi_tu: string | null; nghi_den: string | null }[];
  nghi_giua_ca_phut: number;
  nghi_giua_ca: XlKhungLap[];
  ngoai_ca_phut: number;
  ngoai_ca: XlKhungLap[];
  ngay_nghi_phut: number;
  ngay_nghi: { ngay: string; phut: number; ten: string | null }[];
  gia_cong_ngoai_phut: number;
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
  if (t > 0) return "xl--tre";
  if (t >= -1) return "xl--sat";
  return "";
}


export const THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export function nhanNgay(d: string): { thu: string; so: string; homNay: boolean } {
  const [y, mo, dd] = d.split("-").map(Number);
  const dt = new Date(y, mo - 1, dd);
  return { thu: THU[dt.getDay()], so: `${dd}/${mo}`, homNay: ymd(new Date()) === d };
}
