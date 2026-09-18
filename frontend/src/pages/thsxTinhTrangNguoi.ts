// Tình trạng người ở ô "Giao người" (ThsxDrawer) và ô "Thợ hỗ trợ" (ThsxExecPanels · HoTroForm).
// Máy chủ trả dữ kiện thô (`SxTinhTrangNguoi`), đây chỉ dịch ra câu cho tổ trưởng đọc + xếp thứ
// tự. Luật chặn THẬT nằm ở máy chủ (`services/san_xuat/tinh_trang_nguoi.py`) — ô chọn tắt đúng
// những người máy chủ sẽ chặn, để khỏi bấm rồi mới nhận lỗi.
import type { SxTinhTrangNguoi } from "../api/client";

type ViecDangChay = NonNullable<SxTinhTrangNguoi["dang_chay"]>;
type ViecCho = SxTinhTrangNguoi["viec_cho"][number];

/** "LSX26-0005 · In offset (Tổ In)" — cùng cách gọi tên việc với câu báo lỗi của máy chủ. */
export function moTaViecDangChay(v: ViecDangChay): string {
  const than = [v.ma, v.ten_cong_doan].filter(Boolean).join(" · ") || "một công việc khác";
  return v.to_ten ? `${than} (${v.to_ten})` : than;
}

/** "Có tên ở LSX26-0004 · Dán (Tổ dán) — đang tạm dừng +1 việc": việc đầu (tạm dừng trước) + số còn lại.
 *  Nói "có tên ở" chứ không nói "rảnh": người đó chưa bận lúc này nhưng việc kia chạy lại là phải về. */
function moTaViecCho(ds: ViecCho[]): string | null {
  if (ds.length === 0) return null;
  const v = ds[0];
  const tt = v.trang_thai === "paused" ? "đang tạm dừng" : "chưa bắt đầu";
  const them = ds.length > 1 ? ` +${ds.length - 1} việc` : "";
  return `Có tên ở ${moTaViecDangChay(v)} — ${tt}${them}`;
}

/** "YYYY-MM-DD" → "dd/mm". */
function ngayNgan(ymd: string): string {
  const [, m, d] = ymd.split("-");
  return `${d}/${m}`;
}

export type MucTinhTrang = "chan" | "canh" | "cho" | "ranh";

export interface TinhTrangChon {
  /** Dòng tình trạng LUÔN có của mỗi người: lý do chặn, việc đang chạy, việc đang có tên, hoặc
   *  "Rảnh". Người rảnh cũng phải có chữ — để trống thì không phân biệt được "rảnh" với "chưa kiểm". */
  tomTat: string;
  /** Mức của `tomTat` — quyết định màu: chặn (đỏ) · đang chạy việc khác (vàng) · có tên ở việc
   *  chưa xong (xám) · rảnh hẳn (xanh). */
  muc: MucTinhTrang;
  /** Lý do KHÔNG chọn được (máy chủ sẽ chặn). `null` = chọn được. */
  chan: string | null;
  /** Chọn được nhưng nên xem lại (đang chạy việc khác). */
  canhBao: string | null;
  /** Việc đang có tên, khi dòng tóm tắt đã dành cho lý do chặn / việc đang chạy. */
  ghiChu: string | null;
  /** Thứ tự xếp trong danh sách: 0 rảnh · 1 có tên ở việc chưa xong · 2 đang chạy việc khác · 3 không chọn được. */
  hang: 0 | 1 | 2 | 3;
}

/**
 * @param ngay       ngày xét nghỉ phép ("YYYY-MM-DD"): hôm nay khi giao việc, ngày làm việc của thỏa thuận khi hỗ trợ.
 * @param homNay     ngày XƯỞNG máy chủ trả về — để nói "hôm nay" thay vì ngày tháng.
 * @param viecDangChay việc đích đang chạy ⇒ giao là mở khoảng tham gia ngay ⇒ người đang chạy việc khác bị chặn.
 * @param chanThem   lý do chặn riêng của ô gọi (vd công nhật ở bước nội bộ), ưu tiên nói trước.
 */
export function tinhTrangChon(
  t: SxTinhTrangNguoi,
  { ngay, homNay, viecDangChay = false, chanThem = null }: {
    ngay: string; homNay: string | null; viecDangChay?: boolean; chanThem?: string | null;
  },
): TinhTrangChon {
  const chay = t.dang_chay ? moTaViecDangChay(t.dang_chay) : null;
  const phep = ngay ? t.nghi_phep.find((k) => k.tu <= ngay && ngay <= k.den) : undefined;
  let chan = chanThem ?? t.ly_do_nghi;
  if (!chan && phep) {
    const khi = ngay === homNay ? "hôm nay" : `ngày ${ngayNgan(ngay)}`;
    chan = phep.tu === phep.den
      ? `Nghỉ phép ${khi}`
      : `Nghỉ phép ${khi} (${ngayNgan(phep.tu)}–${ngayNgan(phep.den)})`;
  }
  if (!chan && chay && viecDangChay) chan = `Đang chạy ${chay} — việc này cũng đang chạy, không giao chồng được`;
  const canhBao = !chan && chay ? `Đang chạy ${chay}` : null;
  const cho = moTaViecCho(t.viec_cho);
  if (chan) return { tomTat: chan, muc: "chan", chan, canhBao, ghiChu: cho, hang: 3 };
  if (canhBao) return { tomTat: canhBao, muc: "canh", chan, canhBao, ghiChu: cho, hang: 2 };
  if (cho) return { tomTat: cho, muc: "cho", chan, canhBao, ghiChu: null, hang: 1 };
  return { tomTat: "Rảnh", muc: "ranh", chan, canhBao, ghiChu: null, hang: 0 };
}
