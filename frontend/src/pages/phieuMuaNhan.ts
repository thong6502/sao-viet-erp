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
  // HAI TRẠNG THÁI CỦA RIÊNG MÓN, không phải của yêu cầu (24/08/2026 — *"đọc thì phải hiển thị
  // lên ui chứ"*). Server dò đơn mua cũ của chính món đó rồi mới gửi lên; trước hôm ấy mọi món
  // chưa có đơn sống đều bị dán chung chữ "mới đề nghị", kể cả món đã bị trả phiếu và đang đứng.
  dang_lap_don: "thu mua đang lập đơn",
  don_bi_tu_choi: "đơn bị từ chối, chờ lập lại",
};

/** Món này ĐANG KẸT: đã đi qua thu mua, phiếu bị trả, chưa ai lập lại.
 *
 *  Khác hẳn "chưa ai lo" — chưa ai lo thì cứ chờ tới lượt, còn kẹt thì chờ mãi cũng không nhúc
 *  nhích. Giao diện dùng cờ này để tô khác, đừng để nó nằm lẫn giữa những chip bình thường. */
export function vetDangKep(p: PhieuMuaTom): boolean {
  return p.loai === "ycmh" && p.trang_thai === "don_bi_tu_choi";
}

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
): { chinh: string; them: number; kep: boolean; title: string } | null {
  const xs = ds ?? [];
  if (!xs.length) return null;
  const ke = xs.map((p) => `• ${moTaPhieuMua(p, { dayDu: true })}`).join("\n");
  // Món kẹt thì lời khuyên ĐỔI HẲN: "kiểm phiếu cũ trước" là câu chống đặt trùng, vô nghĩa với
  // một món mà phiếu cũ đã chết — ở đó việc cần làm là hối thu mua lập lại, không phải chờ.
  const kep = xs.filter(vetDangKep);
  return {
    chinh: moTaPhieuMua(xs[0]),
    them: xs.length - 1,
    kep: kep.length > 0,
    title:
      (xs.length > 1
        ? `${xs.length} phiếu đang chạy cho món này:\n`
        : "Đang có phiếu chạy cho món này:\n") +
      ke +
      (kep.length > 0
        ? `\n⚠ ${kep.map((p) => p.ma).join(", ")}: phiếu mua đã bị từ chối, món này đứng lại` +
          " — thu mua phải lập lại đơn, chờ thêm cũng không có hàng."
        : "\nBấm Mua nữa là đẻ phiếu trùng — kiểm phiếu cũ trước."),
  };
}
