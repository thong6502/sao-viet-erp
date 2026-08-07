import type { StatusHistoryRow } from "../api/client";
import { fmtDateTime } from "../utils/format";
import { Timeline, type TimelineEntry } from "./Timeline";

/** Nhãn dùng CHUNG cho hai bộ trạng thái (yêu cầu bộ phận + phiếu mua).
 *
 *  Gộp một bảng được vì hai bộ chỉ trùng nhau ở `pending_approval` và `cancelled`, mà hai chỗ đó
 *  vốn cùng nghĩa. Tách hai bảng thì mỗi lần thêm trạng thái phải nhớ sửa hai nơi. */
const NHAN_TRANG_THAI: Record<string, string> = {
  // Yêu cầu mua hàng của bộ phận
  open: "Chờ Thu mua xử lý",
  in_purchase: "Đang mua",
  done: "Hoàn tất",
  // Phiếu mua hàng
  draft: "Nháp",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  purchased: "Đã mua",
  partially_received: "Giao một phần",
  received: "Đã nhận",
  // Chung
  pending_approval: "Chờ duyệt",
  cancelled: "Đã hủy",
};

/** Trạng thái lạ (dữ liệu cũ, hoặc bậc mới chưa kịp khai nhãn) thì hiện NGUYÊN mã — im lặng bỏ
 *  qua một dòng lịch sử là giấu mất đúng cái người dùng đang đi tìm. */
function nhan(status: string | null | undefined): string {
  if (!status) return "—";
  return NHAN_TRANG_THAI[status] ?? status;
}

function tone(to: string): TimelineEntry["tone"] {
  if (to === "cancelled" || to === "rejected") return "signal";
  if (to === "done" || to === "received" || to === "approved" || to === "purchased") return "moss";
  return "steel";
}

/** Lịch sử đổi trạng thái của MỘT chứng từ — mới nhất trên cùng (đúng thứ tự API trả).
 *
 *  Câu hỏi màn hình này trả lời: "đang ở 'Đã mua' thì TRƯỚC ĐÓ nó ở đâu, ai đẩy, vì sao". Nên mỗi
 *  dòng phải nói đủ ba thứ: từ đâu → tới đâu, lúc nào, ai. `source='may'` là hệ tự suy (vd. giao
 *  đủ hàng ⇒ "Đã nhận") — ghi rõ để không ai đi tìm người đã bấm. */
export function StatusHistoryTimeline({ items }: { items: StatusHistoryRow[] }) {
  const entries: TimelineEntry[] = items.map((it) => ({
    title: it.from_status
      ? `${nhan(it.from_status)} → ${nhan(it.to_status)}`
      : `Lập phiếu · ${nhan(it.to_status)}`,
    meta: [
      fmtDateTime(it.created_at),
      it.source === "may" ? "Hệ thống tự cập nhật" : it.changed_by_name || "—",
      it.reason ? `Lý do: ${it.reason}` : "",
    ]
      .filter(Boolean)
      .join(" · "),
    accent: !it.from_status || it.to_status === "cancelled" || it.to_status === "rejected",
    tone: it.from_status ? tone(it.to_status) : "rust",
  }));
  return (
    <Timeline
      items={entries}
      emptyText="Chưa ghi nhận đổi trạng thái nào — phiếu lập trước 07/08/2026 thì không có lịch sử."
    />
  );
}
