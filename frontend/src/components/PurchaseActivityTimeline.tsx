import type { PurchaseActivityRow } from "../api/client";
import { fmtDateTime } from "../utils/format";
import { Timeline, type TimelineEntry } from "./Timeline";

const STATUS_LABELS: Record<string, string> = {
  draft: "Nháp",
  pending_approval: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  purchased: "Đang mua",
  partially_received: "Giao một phần",
  received: "Đã nhận",
  cancelled: "Đã hủy",
};

function statusLabel(value: string | null): string {
  return value ? (STATUS_LABELS[value] ?? value) : "—";
}

function tone(item: PurchaseActivityRow): TimelineEntry["tone"] {
  if (item.event_type === "delivery_deleted" || item.to_status === "rejected" || item.to_status === "cancelled") return "signal";
  if (item.event_type === "delivery_created" || ["approved", "purchased", "received"].includes(item.to_status ?? "")) return "moss";
  return "steel";
}

/** Timeline riêng cho Đơn mua: vẫn đọc đúng đổi trạng thái, đồng thời không bỏ mất đợt giao. */
export function PurchaseActivityTimeline({ items }: { items: PurchaseActivityRow[] }) {
  const entries: TimelineEntry[] = items.map((item) => {
    const isStatus = item.event_type === "status";
    return {
      title: isStatus
        ? item.from_status
          ? `${statusLabel(item.from_status)} → ${statusLabel(item.to_status)}`
          : `Lập đơn · ${statusLabel(item.to_status)}`
        : item.title,
      meta: [
        fmtDateTime(item.created_at),
        item.source === "may" ? "Hệ thống tự cập nhật" : item.actor_name || "—",
        item.detail || "",
        item.reason ? `Lý do: ${item.reason}` : "",
      ].filter(Boolean).join(" · "),
      accent: item.event_type === "delivery_created" || item.to_status === "rejected" || item.to_status === "cancelled",
      tone: tone(item),
    };
  });
  return <Timeline items={entries} emptyText="Chưa ghi nhận hoạt động nào của đơn." />;
}
