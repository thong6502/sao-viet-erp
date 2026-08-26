// Hàm dùng chung của màn Nghỉ phép (tách từ pages/NghiPhepPage.tsx).
import { ApiError } from "../../../../api/client";

export function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Có lỗi xảy ra.";
}

export function getInitials(name?: string | null) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}
