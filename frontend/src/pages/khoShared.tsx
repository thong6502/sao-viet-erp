// Kho — mảnh dùng chung cho MÀN ĐỀ NGHỊ và MÀN HỘP YÊU CẦU (spec-kho-de-nghi §D).
// Hai màn nhìn cùng một chứng từ ở hai đầu luồng nên nhãn/màu trạng thái phải khớp tuyệt
// đối; để mỗi màn tự khai một bảng là kiểu gì cũng lệch sau vài lần sửa.
import type { StockRequestStatus, StockVoucherStatus } from "../api/client";
import "./kho-request.css";

interface Tone {
  label: string;
  tone: string;
}

export const REQUEST_STATUS: Record<StockRequestStatus, Tone> = {
  draft: { label: "Nháp", tone: "muted" },
  pending: { label: "Chờ duyệt", tone: "amber" },
  approved: { label: "Đã duyệt", tone: "steel" },
  received: { label: "Kho tiếp nhận", tone: "steel" },
  preparing: { label: "Đang chuẩn bị", tone: "steel" },
  partial: { label: "Đã cấp một phần", tone: "rust" },
  done: { label: "Hoàn tất", tone: "moss" },
  rejected: { label: "Từ chối", tone: "signal" },
  cancelled: { label: "Đã hủy", tone: "muted" },
};

export const VOUCHER_STATUS: Record<StockVoucherStatus, Tone> = {
  // "draft" giữ nguyên GIÁ TRỊ ở BE (chưa ghi sổ) nhưng nhãn đổi thành "Chờ ghi sổ": tạo phiếu là
  // gửi luôn, người lập không sửa được; chỉ người có quyền Ghi sổ mới chốt sổ hoặc hủy.
  draft: { label: "Chờ ghi sổ", tone: "amber" },
  posted: { label: "Đã ghi sổ", tone: "moss" },
  cancelled: { label: "Đã hủy", tone: "muted" },
};

export function RequestStatusBadge({ status }: { status: StockRequestStatus }) {
  const s = REQUEST_STATUS[status] ?? { label: status, tone: "muted" };
  return <span className={`badge-sem badge-sem--${s.tone}`}>{s.label}</span>;
}

export function VoucherStatusBadge({ status }: { status: StockVoucherStatus }) {
  const s = VOUCHER_STATUS[status] ?? { label: status, tone: "muted" };
  return <span className={`badge-sem badge-sem--${s.tone}`}>{s.label}</span>;
}

/** Số lượng: bỏ đuôi .00 (phiếu giấy không ai ghi "10,00 tờ"), tối đa 3 số lẻ. */
export function fmtQty(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "";
  return value.toLocaleString("vi-VN", { maximumFractionDigits: 3 });
}

/** Chuỗi ISO của hôm nay theo giờ máy (dùng để so hạn + mặc định ngày phiếu). */
export function todayISO(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Trạng thái đã đóng sổ — quá hạn thì cũng không còn ý nghĩa cảnh báo. */
const CLOSED: StockRequestStatus[] = ["done", "rejected", "cancelled"];

export function isOverdue(ngayCan: string | null, status: StockRequestStatus): boolean {
  if (!ngayCan || CLOSED.includes(status)) return false;
  return ngayCan < todayISO();
}

/** Kho đang chọn nhớ theo màn (API chỉ trả `muc_ton`/lô khi biết kho). */
export function readStoredKho(key: string): number | null {
  const raw = localStorage.getItem(key);
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function writeStoredKho(key: string, value: number | null): void {
  if (value == null) localStorage.removeItem(key);
  else localStorage.setItem(key, String(value));
}
