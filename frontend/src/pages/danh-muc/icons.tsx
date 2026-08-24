// MỘT bộ icon cho cả phân hệ danh mục.
//
// Trước 15/08/2026 mỗi chỗ cần icon lại dán nguyên một khối `<svg>` 6 dòng: riêng cái thùng rác
// có HAI bản (`TrashIcon` 11px và `TrashIcon2` 13px) cùng một `path`, khác đúng con số kích thước;
// dấu ✕ có ba bản 12/12/14px. Đổi nét vẽ thì phải nhớ sửa đủ mọi bản — sớm muộn lệch nhau.
//
// Ở đây `SvgIcon` giữ phần khung (viewBox · nét · bo góc), mỗi icon chỉ còn phần `path` của nó.
import type { CSSProperties, ReactNode } from "react";

interface IconProps {
  /** Cạnh vuông, px. Mặc định theo từng icon — chỗ gọi chỉ truyền khi cần lệch chuẩn. */
  size?: number;
  className?: string;
  style?: CSSProperties;
}

function SvgIcon({
  size, sw = 2.5, className, style, children,
}: IconProps & { sw?: number; children: ReactNode }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"
      className={className} style={style}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = ({ size = 15, className = "rc__search-icon", ...r }: IconProps) => (
  <SvgIcon size={size} className={className} {...r}>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </SvgIcon>
);

/** Thùng rác — MỘT bản cho mọi cỡ. Nút xóa trên hàng bảng dùng 13, nút xóa trong ô bảng động
 *  dùng 11 (mặc định). */
export const TrashIcon = ({ size = 11, ...r }: IconProps) => (
  <SvgIcon size={size} {...r}>
    <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6" />
  </SvgIcon>
);

/** Đồng hồ — dùng ở cột "Tốc độ & Chuẩn bị" bên `rebuildCatalogConfigs`, nên phải export ra ngoài
 *  phân hệ. GIỮ NGUYÊN tên: config đang import theo tên này. */
export const ClockIcon = ({ size = 12, ...r }: IconProps) => (
  <SvgIcon size={size} {...r}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3.5 2" />
  </SvgIcon>
);

export const ArrowUpIcon = ({ size = 11, ...r }: IconProps) => (
  <SvgIcon size={size} sw={3} {...r}><path d="m18 15-6-6-6 6" /></SvgIcon>
);

export const ArrowDownIcon = ({ size = 11, ...r }: IconProps) => (
  <SvgIcon size={size} sw={3} {...r}><path d="m6 9 6 6 6-6" /></SvgIcon>
);

export const PlusIcon = ({ size = 13, style, ...r }: IconProps) => (
  <SvgIcon size={size} sw={3} style={{ marginRight: "4px", ...style }} {...r}>
    <path d="M5 12h14M12 5v14" />
  </SvgIcon>
);

/** Dấu ✕ — nút đóng drawer (14) và đóng popover cú pháp (12). */
export const XIcon = ({ size = 14, ...r }: IconProps) => (
  <SvgIcon size={size} {...r}><path d="M18 6 6 18M6 6l12 12" /></SvgIcon>
);

/** Vòng tròn gạch chéo — khối "chưa có gì" (48) và dòng báo lỗi công thức (12). */
export const CircleXIcon = ({ size = 12, sw = 3, ...r }: IconProps & { sw?: number }) => (
  <SvgIcon size={size} sw={sw} {...r}>
    <circle cx="12" cy="12" r="10" />
    <path d="m15 9-6 6M9 9l6 6" />
  </SvgIcon>
);

/** Ổ khoá — nhóm máy HỆ THỐNG không cho xoá (ô "Nhóm máy" ở màn Thiết bị). */
export const LockIcon = ({ size = 12, ...r }: IconProps) => (
  <SvgIcon size={size} {...r}>
    <rect x="5" y="11" width="14" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </SvgIcon>
);
