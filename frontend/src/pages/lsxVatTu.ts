// Bảng kê VẬT TƯ của MỘT lệnh — gom NVL chính · vật tư tiêu hao · dụng cụ theo TỪNG CÔNG ĐOẠN.
//
// Thuần hàm trên `LsxCongDoan[]` + quy cách lệnh, không dính React — cùng lối `lsxBuoc.ts`, để test
// được mà không phải dựng cả màn.
//
// Ba nhóm cố ý KHÔNG gộp làm một, vì ba bản chất khác nhau:
//   · `nvl`     — giấy, tức dòng bước lấy từ DANH MỤC GIẤY (`hang_loai === "giay"`).
//   · `vat_tu`  — mực · kẽm · keo · màng. Khai ở bước, bước nào ăn gì tuỳ đầu việc của nó.
//   · `dung_cu` — khuôn. MƯỢN RỒI TRẢ, không mất đi khỏi kho.
//
// [SỬA 08/09/2026] Panel KHÔNG còn tự đẻ dòng giấy từ `quy_cach_json.giay_id` + `so_to_nguyen` rồi
// treo lên "bước đầu tiên chạm tờ". Hai chỗ đoán, hai chỗ sai: bước tiêu thụ giấy là thứ suy ra
// NGÀY CẦN giấy ở bảng cân đối, mà máy chỉ đoán được nó. Nay người lập lệnh CHỌN TAY giấy trong ô
// "Thêm vật tư" của đúng bước ăn giấy — panel chỉ đọc lại thứ đã khai, không suy gì nữa.
//
// ⚠️ BẪY CỘNG DỒN — vì sao `dung_cu` KHÔNG được cộng ở khối tổng: một con dao dùng ở hai bước vẫn
// là MỘT con dao. Cộng thành "2 khuôn" là đòi xưởng làm thêm một con dao không ai cần. Giấy và vật
// tư thì ngược lại, PHẢI cộng — mỗi bước ăn một phần thật, nhìn riêng từng bước sẽ mua thiếu.
// (Có thật ngay ở lệnh đầu tiên: màng cán bóng khai ở 2 bước, mỗi bước 5.200 m² ⇒ tổng 10.400 m².)
import type { LsxCongDoan } from "../api/client";
import { tenDonVi } from "./tenDonVi";

export type NhomVatTu = "nvl" | "vat_tu" | "dung_cu";

export interface DongKe {
  nhom: NhomVatTu;
  /** Khoá gom ở khối tổng — `giay:3` · `vat_tu:7` · `khuon:5`. Gom theo ID chứ không theo TÊN:
   *  tên là ảnh chụp lúc bung, hai bước bung ở hai thời điểm có thể mang hai tên của cùng một món. */
  khoa: string;
  ma: string | null;
  ten: string;
  /** `null` ở dụng cụ — khuôn không đếm bằng số lượng, chỉ có hoặc không. */
  so_luong: number | null;
  don_vi: string | null;
  /** Câu phụ bên phải: "NVL chính", tình trạng khuôn… */
  chu_thich: string | null;
}

export interface BuocKe {
  id: number;
  thu_tu: number;
  ten: string;
  to: string | null;
  may: string | null;
  dau_viec: string | null;
  /** `false` ⇒ bước đo bằng thước của RIÊNG nó (ghi kẽm đếm bản), không nối vào chuỗi giấy.
   *  Hiện nó như một mắt xích của chuyền là gây hiểu nhầm — panel cho nó nhãn riêng. */
  tren_dong_giay: boolean;
  sl_vao: number;
  dv_vao: string;
  sl_ra: number;
  dv_ra: string;
  dong: DongKe[];
  /** Danh mục bật cờ "cần khuôn" mà lệnh chưa gán con nào ⇒ nói ra, đừng để trống im lặng. */
  thieu_khuon: boolean;
}

export interface TongKe extends DongKe {
  /** Bước nào ăn món này (`thu_tu`). Từ hai bước trở lên là chỗ nhìn riêng sẽ đếm thiếu. */
  buocs: number[];
}

export interface BangKeVatTu {
  buocs: BuocKe[];
  tong: TongKe[];
  /** Bước không khai được món nào — kể cả khuôn. */
  so_buoc_trong: number;
  so_buoc_chua_dau_viec: number;
  /** Số MÓN khác nhau, nuôi ô tóm tắt trên đầu màn. Đếm theo khối tổng nên món khai ở hai bước
   *  vẫn là một món. */
  so_mon: number;
}

/** Nhãn đơn vị đọc từ DANH MỤC, ngã về mã trần khi danh mục chưa nạp xong hoặc mã lạ.
 *  Đừng dựng bảng nhãn cứng ở đây — xem bài học ở `tenDonVi.ts`. */
function nhanDv(ma: string | null | undefined): string {
  const k = (ma ?? "").trim();
  return k ? (tenDonVi(k) ?? k) : "";
}

function soHoac0(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function bangKeVatTu(args: {
  congDoans: LsxCongDoan[];
}): BangKeVatTu {
  const { congDoans } = args;
  const buocSap = [...congDoans].sort((a, b) => a.thu_tu - b.thu_tu);

  const buocs: BuocKe[] = buocSap.map((c) => {
    const dong: DongKe[] = [];

    for (const v of c.vat_tus ?? []) {
      // Món tới từ danh mục Giấy là NVL CHÍNH — khác nhóm, khác khoá gom. Khoá phải mang cả
      // `hang_loai`: Giấy #7 và Vật tư #7 là hai món khác nhau, gom chung một khoá `7` là cộng
      // nhầm kg giấy vào kg keo.
      const giay = v.hang_loai === "giay";
      dong.push({
        nhom: giay ? "nvl" : "vat_tu",
        khoa: `${giay ? "giay" : "vat_tu"}:${v.vat_tu_id}`,
        ma: v.vat_tu_ma ?? null,
        ten: v.vat_tu_ten ?? "",
        so_luong: soHoac0(v.so_luong),
        don_vi: nhanDv(v.don_vi),
        chu_thich: giay ? "NVL chính" : null,
      });
    }

    if (c.khuon_be_id != null) {
      dong.push({
        nhom: "dung_cu",
        khoa: `khuon:${c.khuon_be_id}`,
        ma: c.khuon_be_ma ?? null,
        ten: c.khuon_be_ten ?? `Khuôn #${c.khuon_be_id}`,
        so_luong: null,
        don_vi: null,
        chu_thich: c.khuon_be_tinh_trang ?? null,
      });
    }

    return {
      id: c.id,
      thu_tu: c.thu_tu,
      ten: c.ten,
      to: c.department_ten ?? null,
      may: c.may_ten ?? null,
      dau_viec: c.khoan_ten ?? null,
      tren_dong_giay: c.tren_dong_giay !== false,
      sl_vao: soHoac0(c.so_luong_vao),
      dv_vao: nhanDv(c.don_vi_vao),
      sl_ra: soHoac0(c.so_luong_ra),
      dv_ra: nhanDv(c.don_vi_ra),
      dong,
      thieu_khuon: Boolean(c.requires_tooling) && c.khuon_be_id == null,
    };
  });

  return {
    buocs,
    tong: gomTong(buocs),
    so_buoc_trong: buocs.filter((b) => b.dong.length === 0).length,
    so_buoc_chua_dau_viec: buocs.filter((b) => !b.dau_viec).length,
    so_mon: gomTong(buocs).length,
  };
}

/** Gom các dòng của mọi bước về khối tổng — thứ dùng để đi mua.
 *
 *  Cộng theo cặp (khoá, ĐƠN VỊ): cùng một món mà hai bước khai hai đơn vị thì cộng thẳng là ra số
 *  vô nghĩa (`3 kg + 2 tấn = 5`). Tách thành hai dòng thì người đọc thấy ngay là có chuyện.
 *  Dụng cụ đi đường riêng — gom theo khoá và KHÔNG cộng (xem bẫy ở đầu file).
 */
function gomTong(buocs: BuocKe[]): TongKe[] {
  const bang = new Map<string, TongKe>();
  for (const b of buocs) {
    for (const d of b.dong) {
      const gop = d.nhom === "dung_cu" ? d.khoa : `${d.khoa}|${d.don_vi ?? ""}`;
      const co = bang.get(gop);
      if (co === undefined) {
        bang.set(gop, { ...d, buocs: [b.thu_tu] });
        continue;
      }
      if (!co.buocs.includes(b.thu_tu)) co.buocs.push(b.thu_tu);
      if (d.nhom !== "dung_cu") co.so_luong = (co.so_luong ?? 0) + (d.so_luong ?? 0);
    }
  }
  // NVL trước, vật tư giữa, dụng cụ cuối — đúng thứ tự "tốn tiền nhiều → ít → không tốn".
  const hang: Record<NhomVatTu, number> = { nvl: 0, vat_tu: 1, dung_cu: 2 };
  return [...bang.values()].sort(
    (a, b) => hang[a.nhom] - hang[b.nhom] || a.ten.localeCompare(b.ten, "vi"),
  );
}
