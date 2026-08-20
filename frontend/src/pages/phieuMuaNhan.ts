// NHÃN "MÓN NÀY ĐANG CÓ AI LO" — dịch `PhieuMuaTom` của server thành câu người đọc được.
//
// Vì sao có file này (câu hỏi 20/08/2026: *"như này là sao biết được cái nào đang yêu cầu mua"*):
// bảng cân đối chỉ cộng hàng khi PMH đã duyệt VÀ có ngày về. Mọi thứ trước mốc đó — đề nghị vừa
// bấm, PMH chờ duyệt, PMH duyệt rồi mà NCC chưa hẹn ngày — đều vẽ ĐỎ giống hệt "chưa ai đụng
// vào", nên người tiếp theo bấm Mua lần nữa. Couché 300 của GB26-0004 có đúng hai YCMH cùng
// 38,08 kg vì lẽ đó.
//
// Thuần hàm, không dính React: dùng chung cho bảng cân đối (`VatTuKeHoachView`) và thẻ lệnh
// (`GiuChoTheoLenhView`), và test được mà không phải dựng cả màn.
import type { PhieuMuaTom } from "../api/client";

/** Trạng thái THÔ của hai chuỗi phiếu → chữ tiếng Việt. Dịch ở FE để đổi chữ khỏi phải đụng
 *  backend; trạng thái lạ thì trả nguyên chuỗi chứ KHÔNG nuốt — nuốt là mất dấu vết. */
const NHAN_PMH: Record<string, string> = {
  pending_approval: "chờ duyệt",
  approved: "đã duyệt",
  purchased: "đã đặt",
  partially_received: "về một phần",
};

const NHAN_YCMH: Record<string, string> = {
  open: "mới đề nghị",
  pending_approval: "chờ duyệt",
  in_purchase: "đang mua",
};

export function nhanTrangThaiPhieu(p: PhieuMuaTom): string {
  const bang = p.loai === "pmh" ? NHAN_PMH : NHAN_YCMH;
  return bang[p.trang_thai] ?? p.trang_thai;
}

/** `1/9` — ngắn có chủ ý. Chip vật tư chỉ còn vài chục pixel; năm đầy đủ nằm ở tooltip. */
function ngayNgan(v: string | null): string | null {
  if (!v) return null;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

/** Một dòng gọn: `PMH-VT-02 · về 1/9` · `YCMH-260820-JI8X · chờ duyệt`.
 *
 *  Có ngày về thì NÓI NGÀY, không nói trạng thái: người lập kế hoạch cần biết "bao giờ có hàng",
 *  còn "đã duyệt hay chưa" chỉ là thủ tục nội bộ của thu mua. Không có ngày mới lùi về trạng thái. */
export function moTaPhieuMua(p: PhieuMuaTom, opts?: { dayDu?: boolean }): string {
  const nd =
    opts?.dayDu && p.ngay_ve
      ? new Date(p.ngay_ve).toLocaleDateString("vi-VN")
      : ngayNgan(p.ngay_ve);
  return `${p.ma} · ${nd ? `về ${nd}` : nhanTrangThaiPhieu(p)}`;
}

/** Phần bày ra trên chip: MỘT phiếu chắc nhất (server đã xếp sẵn) + đuôi `+N`.
 *
 *  Danh sách đầy đủ đi vào `title` — không đổ hết ra chip: ba mã phiếu nằm cạnh nhau thì không ai
 *  đọc cái nào cả, mà việc cần làm chỉ là "đã có người lo, kiểm trước khi bấm Mua". */
export function tomTatPhieuMua(
  ds: PhieuMuaTom[] | null | undefined,
): { chinh: string; them: number; title: string } | null {
  const xs = ds ?? [];
  if (!xs.length) return null;
  const ke = xs.map((p) => `• ${moTaPhieuMua(p, { dayDu: true })}`).join("\n");
  return {
    chinh: moTaPhieuMua(xs[0]),
    them: xs.length - 1,
    title:
      (xs.length > 1
        ? `${xs.length} phiếu đang chạy cho món này:\n`
        : "Đang có phiếu chạy cho món này:\n") +
      ke +
      "\nBấm Mua nữa là đẻ phiếu trùng — kiểm phiếu cũ trước.",
  };
}
