// Kho — mảnh dùng chung cho MÀN YÊU CẦU và MÀN HỘP YÊU CẦU (spec-kho-de-nghi §D).
// Hai màn nhìn cùng một chứng từ ở hai đầu luồng nên nhãn/màu trạng thái phải khớp tuyệt
// đối; để mỗi màn tự khai một bảng là kiểu gì cũng lệch sau vài lần sửa.
import { useEffect, useRef, useState, type CSSProperties, type InputHTMLAttributes } from "react";
import type { StockRequestKind, StockRequestStatus, StockVoucherStatus } from "../api/client";
import { Select } from "../components/Select";
import "./kho-request.css";

/** Các mức số dòng/trang cho mọi danh sách kho. Mặc định = 10. */
export const PAGE_SIZES = [10, 15, 20] as const;
export const DEFAULT_PAGE_SIZE = 10;

// Parse chuỗi người dùng gõ (chấp nhận cả dấu "," VN lẫn ".") thành số; "" / "." / "," → null.
function parseDecimal(s: string): number | null {
  const t = s.replace(",", ".").trim();
  if (t === "" || t === ".") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}
// Hiển thị số kiểu VN (dấu phẩy thập phân), KHÔNG chấm ngăn nghìn (chấm nghìn parse lại sẽ vỡ:
// "1.000" → 1). 0/null coi như rỗng để ô fresh trống. Ô đang sửa hiện số thô; bản chỉ-đọc mới fmtQty.
function showDecimal(n: number | null): string {
  return n == null || n === 0 ? "" : String(n).replace(".", ",");
}

/**
 * Ô nhập SỐ THẬP PHÂN cho kho. Sửa lỗi `type="number"` + `value={n || ""}` NUỐT MẤT số 0 và trạng
 * thái đang gõ ("0", "0,", "0,5") — người dùng không gõ được 0,5. Giữ CHUỖI đang gõ làm nguồn hiển
 * thị, chỉ parse ra số khi hợp lệ; nhận cả "," (VN) lẫn "."; đồng bộ lại từ prop khi KHÔNG focus.
 * `allowNull`: ô rỗng trả null (cho đơn giá) thay vì 0 (cho số lượng).
 */
export function DecimalInput({
  value,
  onChange,
  allowNull = false,
  ...rest
}: {
  value: number | null;
  onChange: (n: number | null) => void;
  allowNull?: boolean;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type">) {
  const [text, setText] = useState(() => showDecimal(value));
  const focused = useRef(false);
  // Đồng bộ prop → ô KHI KHÔNG focus (reset form, seed lại) — không giẫm lên lúc người dùng đang gõ.
  useEffect(() => {
    if (!focused.current) setText(showDecimal(value));
  }, [value]);
  return (
    <input
      {...rest}
      type="text"
      inputMode="decimal"
      value={text}
      onFocus={(e) => {
        focused.current = true;
        rest.onFocus?.(e);
      }}
      onBlur={(e) => {
        focused.current = false;
        setText(showDecimal(parseDecimal(text))); // rời ô → chuẩn hóa (bỏ "0" trơ, dấu lẻ…)
        rest.onBlur?.(e);
      }}
      onChange={(e) => {
        const raw = e.target.value;
        // Chỉ nhận: rỗng hoặc chuỗi số với TỐI ĐA một dấu thập phân (, hoặc .). Chặn ký tự khác.
        if (raw !== "" && !/^\d*[.,]?\d*$/.test(raw)) return;
        setText(raw);
        const n = parseDecimal(raw);
        onChange(allowNull ? n : n ?? 0);
      }}
    />
  );
}

/** Bộ chọn số dòng/trang — DROPDOWN mở LÊN TRÊN (drop-up) vì luôn nằm cuối trang/pager, mở xuống
 *  sẽ bị che. Dùng chung ở mọi pager danh sách kho. */
export function PageSizeSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <span className="kho-pgsize">
      <Select
        ariaLabel="Số dòng mỗi trang"
        value={value}
        onChange={(v) => onChange(Number(v))}
        options={PAGE_SIZES.map((n) => ({ value: n, label: `${n} / trang` }))}
        portal
        dropUp
      />
    </span>
  );
}

interface Tone {
  label: string;
  tone: string;
}

export const REQUEST_STATUS: Record<StockRequestStatus, Tone> = {
  draft: { label: "Nháp", tone: "muted" },
  pending: { label: "Chờ duyệt", tone: "amber" },
  // Đã BỎ bước duyệt yêu cầu kho → tạo là "approved" ngay. Nhãn "Chờ xử lý" (chờ kho tiếp nhận/cấp),
  // KHÔNG dùng "Đã duyệt" nữa vì không còn ai duyệt.
  approved: { label: "Chờ xử lý", tone: "steel" },
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
  return (
    <span className={`badge-sem badge-sem--${s.tone}`}>
      <span className={`status-dot status-dot--${s.tone}`} />
      {s.label}
    </span>
  );
}

export function VoucherStatusBadge({ status }: { status: StockVoucherStatus }) {
  const s = VOUCHER_STATUS[status] ?? { label: status, tone: "muted" };
  return (
    <span className={`badge-sem badge-sem--${s.tone}`}>
      <span className={`status-dot status-dot--${s.tone}`} />
      {s.label}
    </span>
  );
}

/** Trạng thái PHIẾU ĐIỀU CHUYỂN (mặt tiền là vế NHẬP đích): chờ kho đích ghi sổ · đã ghi sổ (hoàn
 *  tất cả tuyến) · đã hủy. Nhãn RIÊNG so với phiếu thường ("Hoàn tất" thay "Đã ghi sổ"). */
export type TransferStatus = "cho-ghi-so" | "hoan-tat" | "da-huy";

const TRANSFER_STATUS: Record<TransferStatus, Tone> = {
  "cho-ghi-so": { label: "Chờ ghi sổ", tone: "amber" },
  "hoan-tat": { label: "Hoàn tất", tone: "moss" },
  "da-huy": { label: "Đã hủy", tone: "muted" },
};

export function TransferStatusBadge({ status }: { status: TransferStatus }) {
  const s = TRANSFER_STATUS[status];
  return (
    <span className={`badge-sem badge-sem--${s.tone}`}>
      <span className={`status-dot status-dot--${s.tone}`} />
      {s.label}
    </span>
  );
}

/** Nhãn ĐIỀU CHUYỂN — dán lên yêu cầu điều chuyển (NHẬP ở đích) để phân biệt với nhập/xuất thường.
 *  Kèm tên kho nguồn khi có ("Điều chuyển từ «kho»"). Dùng chung ở Hộp yêu cầu · Yêu cầu · drawer. */
export function DieuChuyenPill({ khoNguonTen }: { khoNguonTen?: string | null }) {
  return (
    <span
      className="badge-sem badge-sem--plum"
      title={khoNguonTen ? `Điều chuyển từ ${khoNguonTen}` : "Điều chuyển nội bộ"}
    >
      <span aria-hidden style={{ fontSize: 12, lineHeight: 1 }}>⇄</span> Điều chuyển{khoNguonTen ? ` · từ ${khoNguonTen}` : ""}
    </span>
  );
}

/** Chip LOẠI yêu cầu — cột "Loại" ở danh sách Yêu cầu / Phiếu từ yêu cầu: Nhập · Xuất · Điều chuyển.
 *  `dieuChuyen` ưu tiên (yêu cầu điều chuyển vốn là NHẬP ở đích, nhưng hiển thị là "Điều chuyển"). */
export function LoaiYeuCauChip({ loai, dieuChuyen }: { loai: StockRequestKind; dieuChuyen?: boolean }) {
  if (dieuChuyen) {
    return (
      <span className="badge-sem badge-sem--plum">
        <span aria-hidden style={{ fontSize: 12, lineHeight: 1 }}>⇄</span> Điều chuyển
      </span>
    );
  }
  return loai === "NHAP" ? (
    <span className="badge-sem badge-sem--steel">
      <span aria-hidden style={{ fontSize: 12, lineHeight: 1 }}>↓</span> Nhập
    </span>
  ) : (
    <span className="badge-sem badge-sem--rust">
      <span aria-hidden style={{ fontSize: 12, lineHeight: 1 }}>↑</span> Xuất
    </span>
  );
}

/** Gắn `title` (tooltip trình duyệt) cho MỌI `<th>` của bảng = chính chữ tiêu đề cột → hover ra tên
 *  cột đầy đủ dù cột bị cắt (vd "Mặt hàng / Tổng"). Trả ref gắn vào `<table>`. Không đè title có sẵn
 *  (vd cột phễu ngày/số đã có mô tả riêng). Chạy sau mỗi render vì số cột có thể đổi (ẩn/hiện theo quyền). */
export function useHeaderTitles<T extends HTMLElement = HTMLTableElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    // Gắn cho MỌI `<th>` trong phạm vi ref (đặt ref ở `<table>` hoặc bọc cả `<main>` để phủ nhiều bảng).
    ref.current?.querySelectorAll<HTMLTableCellElement>("thead th").forEach((th) => {
      const t = (th.textContent || "").trim();
      if (t && !th.hasAttribute("title")) th.setAttribute("title", t);
    });
  });
  return ref;
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

/** `canLuc` (giờ cần thật, từ đề nghị sản xuất) ưu tiên khi có — so THEO GIỜ, không theo ngày:
 *  cột hiển thị đã đổi nhãn "Cần lúc" và hiện giờ (task-8-ruling-man-kho), nên tín hiệu trễ phải
 *  khớp — ca sáng cần 06:00 mà tới chiều vẫn chưa "Quá hạn" thì đá ngay với chính cột vừa hiện giờ
 *  cạnh nó (task-8-review.md Important 4). Không có `canLuc` (yêu cầu kho thường) → giữ NGUYÊN
 *  hành vi cũ, so theo ngày trơn. */
export function isOverdue(
  ngayCan: string | null,
  status: StockRequestStatus,
  canLuc?: string | null,
): boolean {
  if (CLOSED.includes(status)) return false;
  if (canLuc) return new Date(canLuc).getTime() < Date.now();
  if (!ngayCan) return false;
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
  className,
  style,
}: {
  label: string;
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  className?: string;
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
    <th ref={ref} style={style} className={`kho-colfil${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className={`kho-colfil__btn${active ? " is-active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        title="Bấm để lọc theo khoảng ngày"
      >
        {label}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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

/** Khoảng SỐ [from,to]. `from`/`to` là chuỗi từ ô number (rỗng = không chặn phía đó). `val` null/NaN
 *  → rớt khi ĐANG lọc. */
export function inNumRange(val: number | null | undefined, range: { from: string; to: string }): boolean {
  const lo = range.from.trim() === "" ? null : Number(range.from);
  const hi = range.to.trim() === "" ? null : Number(range.to);
  if (lo === null && hi === null) return true;
  if (val == null || !Number.isFinite(val)) return false;
  if (lo !== null && Number.isFinite(lo) && val < lo) return false;
  if (hi !== null && Number.isFinite(hi) && val > hi) return false;
  return true;
}

/** Tiêu đề cột SỐ có bộ lọc khoảng: bấm nhãn → bung popup 2 ô Từ/Đến (number). Chấm báo đang lọc.
 *  `className` (vd "kho-bc__num") giữ canh phải như cột số thường. */
export function NumFilterHead({
  label,
  from,
  to,
  onChange,
  className,
  style,
}: {
  label: string;
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  className?: string;
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
    <th ref={ref} style={style} className={`kho-colfil kho-colfil--num${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className={`kho-colfil__btn${active ? " is-active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        title="Bấm để lọc theo khoảng số"
      >
        {label}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
        {active && <span className="kho-colfil__dot" />}
      </button>
      {open && (
        <div className="kho-colfil__pop" role="dialog">
          <label className="kho-colfil__row">
            <span>Từ</span>
            <input type="number" className="rc-input" value={from}
              onChange={(e) => onChange(e.target.value, to)} />
          </label>
          <label className="kho-colfil__row">
            <span>Đến</span>
            <input type="number" className="rc-input" value={to}
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
