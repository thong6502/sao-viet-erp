// Kho — mảnh dùng chung cho MÀN ĐỀ NGHỊ và MÀN HỘP YÊU CẦU (spec-kho-de-nghi §D).
// Hai màn nhìn cùng một chứng từ ở hai đầu luồng nên nhãn/màu trạng thái phải khớp tuyệt
// đối; để mỗi màn tự khai một bảng là kiểu gì cũng lệch sau vài lần sửa.
import { useEffect, useRef, useState, type CSSProperties } from "react";
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

/** Khoảng ngày [from,to] (yyyy-mm-dd). Rỗng cả hai = không lọc. `val` rỗng = rớt khi ĐANG lọc. */
export function inDateRange(val: string, range: { from: string; to: string }): boolean {
  if (!range.from && !range.to) return true;
  if (!val) return false;
  if (range.from && val < range.from) return false;
  if (range.to && val > range.to) return false;
  return true;
}

/** Tiêu đề cột NGÀY có bộ lọc khoảng: bấm nhãn → bung popup 2 ô Từ/Đến. Lọc RỖNG khi cả hai trống.
 *  Dùng chung cho màn Yêu cầu & Phiếu từ yêu cầu — bấm cột nào lọc đúng cột đó, có chấm báo đang lọc. */
export function DateFilterHead({
  label,
  from,
  to,
  onChange,
  style,
}: {
  label: string;
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  style?: CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLTableCellElement>(null);
  const active = !!(from || to);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  return (
    <th ref={ref} style={style} className="kho-colfil">
      <button
        type="button"
        className={`kho-colfil__btn${active ? " is-active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        title="Bấm để lọc theo khoảng ngày"
      >
        {label}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        {active && <span className="kho-colfil__dot" />}
      </button>
      {open && (
        <div className="kho-colfil__pop" role="dialog">
          <label className="kho-colfil__row">
            <span>Từ</span>
            <input type="date" className="rc-input" value={from} max={to || undefined}
              onChange={(e) => onChange(e.target.value, to)} />
          </label>
          <label className="kho-colfil__row">
            <span>Đến</span>
            <input type="date" className="rc-input" value={to} min={from || undefined}
              onChange={(e) => onChange(from, e.target.value)} />
          </label>
          {active && (
            <button type="button" className="rc__link-btn kho-colfil__clear"
              onClick={() => { onChange("", ""); setOpen(false); }}>
              Xóa lọc
            </button>
          )}
        </div>
      )}
    </th>
  );
}
