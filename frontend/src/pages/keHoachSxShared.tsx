// Mảnh dùng chung của bàn Kế hoạch sản xuất: pill trạng thái · chip cờ · chip thiếu · skeleton ·
// empty-state · helper định dạng số/ngày. Tách riêng để 4 view (hàng chờ · preview · list · chi
// tiết) không chép lại — và để mọi nhãn trạng thái nằm ĐÚNG MỘT chỗ.
import type { ReactNode } from "react";
import { Icon, type IconName } from "../components/Icons";
import {
  LSX_LOAI_BUOC_META,
  LSX_THIEU_LABELS,
  type LsxLoaiBuoc,
  type LsxTrangThai,
} from "../api/client";

// --- định dạng --------------------------------------------------------------
export function num(v: number | null | undefined): string {
  return v == null ? "—" : Number(v).toLocaleString("vi-VN");
}

export function ngay(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function ngayGio(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleDateString("vi-VN")} ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
}

/** Số ngày còn lại tới hạn (âm = đã quá hạn). null khi không có hạn. */
export function conLai(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

/** Class cảnh báo hạn: quá hạn (đỏ) / ≤3 ngày (hổ phách). */
export function classHan(dateStr: string | null | undefined): string {
  const n = conLai(dateStr);
  if (n == null) return "";
  if (n < 0) return "khsx-date--late";
  if (n <= 3) return "khsx-date--soon";
  return "";
}

// --- trạng thái lệnh --------------------------------------------------------
const PILL: Record<LsxTrangThai, { label: string; cls: string }> = {
  nhap: { label: "Nháp", cls: "khsx-pill--nhap" },
  cho_bo_sung: { label: "Chờ bổ sung", cls: "khsx-pill--thieu" },
  san_sang: { label: "Sẵn sàng", cls: "khsx-pill--sansang" },
};

export function TrangThaiPill({ tt, lg = false }: { tt: LsxTrangThai; lg?: boolean }) {
  const meta = PILL[tt] ?? PILL.nhap;
  return (
    <span className={`khsx-pill ${meta.cls} ${lg ? "khsx-pill--lg" : ""}`}>
      <span className="khsx-pill__dot" aria-hidden="true" />
      {meta.label}
    </span>
  );
}

export const TRANG_THAI_TABS: { key: string; label: string; tone?: "default" | "alert" }[] = [
  { key: "all", label: "Tất cả" },
  { key: "nhap", label: "Nháp" },
  { key: "cho_bo_sung", label: "Chờ bổ sung", tone: "alert" },
  { key: "san_sang", label: "Sẵn sàng" },
];

// --- chip -------------------------------------------------------------------
export function ChipGap() {
  return (
    <span className="khsx-chip khsx-chip--rush">
      <Icon name="bell" size={11} /> GẤP
    </span>
  );
}

export function ChipNgoai({ ncc }: { ncc?: string | null }) {
  return (
    <span className="khsx-chip khsx-chip--ngoai" title={ncc ? `Thuê ngoài: ${ncc}` : "Thuê ngoài"}>
      <Icon name="truck" size={11} /> {ncc || "thuê ngoài"}
    </span>
  );
}

/** Chip THIẾU — bo vuông (khác pill trạng thái bo tròn) để không lẫn. */
export function ChipThieu({ code }: { code: string }) {
  return (
    <span className="khsx-need">
      <Icon name="x" size={10} /> {LSX_THIEU_LABELS[code] ?? code}
    </span>
  );
}

/** Xếp chồng chip thiếu, tối đa `max` rồi gộp phần dư → chiều cao hàng không giật. */
export function ThieuStack({ codes, max = 2 }: { codes: string[]; max?: number }) {
  if (!codes.length) return <span className="khsx-muted">—</span>;
  const hien = codes.slice(0, max);
  const du = codes.slice(max);
  return (
    <span className="khsx-need-stack">
      {hien.map((c) => (
        <ChipThieu key={c} code={c} />
      ))}
      {du.length > 0 && (
        <span
          className="khsx-need khsx-need--more"
          title={du.map((c) => LSX_THIEU_LABELS[c] ?? c).join(" · ")}
        >
          +{du.length}
        </span>
      )}
    </span>
  );
}

/** Cảnh báo MỀM (không nền) — phân cấp: đỏ có nền = chặn, vàng không nền = lưu ý. */
export function CanhBaoMem({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="khsx-warn-inline" title={title}>
      <Icon name="help" size={11} /> {children}
    </span>
  );
}

/** Chuỗi công đoạn "In › Cán › Bế › Dán" — nhìn 1 giây là hiểu cả routing.
 *
 *  Nhận `loai_buoc` (không phải cờ thuê-ngoài) để màn "lệnh dự kiến" và màn lệnh đã tạo dùng
 *  CHUNG một cách gọi tên. Chỉ đánh dấu bước NGOẠI LỆ — bước máy/tổ là phần lớn routing, tô hết
 *  thì màu hết mang tin. */
export function ChuoiCongDoan({
  steps,
}: {
  steps: { ten: string; loai_buoc?: string }[];
}) {
  if (!steps.length) {
    return <span className="khsx-flow khsx-flow--none">chưa có công đoạn</span>;
  }
  return (
    <span className="khsx-flow">
      {steps.map((s, i) => {
        const meta = s.loai_buoc ? LSX_LOAI_BUOC_META[s.loai_buoc as LsxLoaiBuoc] : undefined;
        const ngoaiLe = !!meta && s.loai_buoc !== "may" && s.loai_buoc !== "to";
        return (
          <span
            key={`${s.ten}-${i}`}
            className={`khsx-flow__step ${ngoaiLe ? `khsx-flow__step--${meta.tone}` : ""}`}
            title={meta?.hint}
          >
            {s.loai_buoc === "thue_ngoai" && <Icon name="truck" size={10} />}
            {s.loai_buoc === "cho" && <Icon name="clock" size={10} />}
            {s.ten}
          </span>
        );
      })}
    </span>
  );
}

// --- trạng thái tải / rỗng / lỗi -------------------------------------------
export function Skeleton({ rows = 5, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <tbody className="khsx-skel">
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((__, c) => (
            <td key={c}>
              <span className="khsx-skel__bar" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

export function EmptyState({
  icon,
  title,
  sub,
  action,
}: {
  icon: IconName;
  title: string;
  sub?: string;
  action?: ReactNode;
}) {
  return (
    <div className="khsx-empty">
      <Icon name={icon} size={44} />
      <p className="khsx-empty__title">{title}</p>
      {sub && <p className="khsx-empty__sub">{sub}</p>}
      {action}
    </div>
  );
}

export function BangLoi({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="banner banner--error" role="alert">
      <span>{text}</span>
      {onRetry && (
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          Tải lại
        </button>
      )}
    </div>
  );
}
