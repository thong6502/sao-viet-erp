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

// --- trạng thái XẾP LỊCH (bàn Xếp lịch công đoạn) ---------------------------
// Mọi nhãn của bàn xếp lịch nằm ĐÚNG MỘT chỗ (cùng file với pill/chip lệnh) — không đẻ file nhãn riêng.

/** Thời lượng phút → "1 giờ 13 phút". Chữ CÓ DẤU nên KHÔNG dùng mono; canh cột bằng tabular-nums ở CSS. */
export function thoiLuong(phut: number | null | undefined): string {
  if (phut == null || phut <= 0) return "—";
  const t = Math.round(phut);
  const gio = Math.floor(t / 60);
  const p = t % 60;
  if (gio && p) return `${gio} giờ ${p} phút`;
  if (gio) return `${gio} giờ`;
  return `${p} phút`;
}

/** Pill trạng thái xếp lịch (bo TRÒN, bám .khsx-pill). Suy từ trang_thai + is_locked + co_xung_dot;
 *  ưu tiên Xung đột > Khóa > Đã xếp > Chờ. CÓ CHỮ (không chỉ dựa màu — a11y). */
export function LichTrangThaiPill({
  trangThai,
  isLocked = false,
  coXungDot = false,
}: {
  trangThai: string;
  isLocked?: boolean;
  coXungDot?: boolean;
}) {
  let cls = "xlcd-lpill--cho";
  let label = "Chờ xếp lịch";
  let icon: IconName | null = null;
  if (coXungDot) {
    cls = "xlcd-lpill--xungdot";
    label = "Có xung đột";
    icon = "ban";
  } else if (isLocked) {
    cls = "xlcd-lpill--khoa";
    label = "Đã khóa";
    icon = "lock";
  } else if (trangThai === "da_xep") {
    cls = "xlcd-lpill--daxep";
    label = "Đã xếp lịch";
  }
  return (
    <span className={`khsx-pill ${cls}`}>
      {icon ? <Icon name={icon} size={11} /> : <span className="khsx-pill__dot" aria-hidden="true" />}
      {label}
    </span>
  );
}

const RUI_RO_META: Record<string, { label: string; cls: string }> = {
  an_toan: { label: "An toàn", cls: "xlcd-risk--an-toan" },
  sap_toi_han: { label: "Sắp tới hạn", cls: "xlcd-risk--sap" },
  nguy_co_tre: { label: "Nguy cơ trễ", cls: "xlcd-risk--nguy-co" },
  da_tre: { label: "Đã trễ", cls: "xlcd-risk--tre" },
  chua_co_han: { label: "Chưa có hạn", cls: "xlcd-risk--chua" },
};

/** Chip nguy cơ trễ (bo VUÔNG nhẹ) — nhãn rủi ro + độ dư ("−2d"/"+5d"). CÓ CHỮ (a11y color-not-only). */
export function NguyCoTreChip({
  nhan,
  slackNgay = null,
}: {
  nhan: string | null | undefined;
  slackNgay?: number | null;
}) {
  const meta = RUI_RO_META[nhan ?? "chua_co_han"] ?? RUI_RO_META.chua_co_han;
  const slack =
    slackNgay == null
      ? null
      : `${slackNgay > 0 ? "+" : slackNgay < 0 ? "−" : ""}${Math.abs(slackNgay)}d`;
  return (
    <span className={`xlcd-risk ${meta.cls}`}>
      {meta.label}
      {slack && <span className="xlcd-risk__slack">{slack}</span>}
    </span>
  );
}

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
  activeIndex,
}: {
  steps: { ten: string; loai_buoc?: string }[];
  /** Tô đậm bước ĐANG xem (drawer 1 công đoạn) — bỏ trống thì không tô (giữ nguyên hành vi cũ). */
  activeIndex?: number;
}) {
  if (!steps.length) {
    return <span className="khsx-flow khsx-flow--none">chưa có công đoạn</span>;
  }
  return (
    <span className="khsx-flow">
      {steps.map((s, i) => {
        const meta = s.loai_buoc ? LSX_LOAI_BUOC_META[s.loai_buoc as LsxLoaiBuoc] : undefined;
        const ngoaiLe = !!meta && s.loai_buoc !== "may" && s.loai_buoc !== "to";
        const active = i === activeIndex;
        return (
          <span
            key={`${s.ten}-${i}`}
            className={`khsx-flow__step ${ngoaiLe ? `khsx-flow__step--${meta.tone}` : ""} ${active ? "khsx-flow__step--active" : ""}`}
            title={meta?.hint}
            aria-current={active ? "step" : undefined}
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
