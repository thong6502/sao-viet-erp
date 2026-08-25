// Badge trạng thái yêu cầu (tách từ pages/ChamCongPage.tsx).

const STATUS_MAP: Record<string, [string, string]> = {
  pending: ["cc-badge-status--pending", "Chờ duyệt"],
  approved: ["cc-badge-status--approved", "Đã duyệt"],
  rejected: ["cc-badge-status--rejected", "Từ chối"],
  cancelled: ["cc-badge-status--cancelled", "Đã hủy"],
};

/** Nhãn trạng thái thuần chữ (dùng trong câu văn, không phải badge). */
export function statusText(s: string): string {
  return STATUS_MAP[s]?.[1] ?? s;
}

export function statusBadge(s: string) {
  const [cls, label] = STATUS_MAP[s] ?? ["cc-badge-status--cancelled", s];
  return <span className={`cc-badge-status ${cls}`}>{label}</span>;
}
