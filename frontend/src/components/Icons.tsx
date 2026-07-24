// Inline stroke-icon set — no icon dependency. Line style (1.75 stroke,
// 24-grid, currentColor) so icons inherit the sidebar text color and the
// rust active state. Add a glyph here, then reference it by name in the nav.
import type { ReactNode, SVGProps } from "react";

const ICONS = {
  // Overview
  grid: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </>
  ),
  // Bài ghép — sheets xếp lớp (nhiều bài chung một tờ in)
  layers: (
    <>
      <path d="M12 3 3 8l9 5 9-5-9-5Z" />
      <path d="M3 12l9 5 9-5" />
      <path d="M3 16l9 5 9-5" />
    </>
  ),
  // Sản phẩm
  box: (
    <>
      <path d="M12 2.6 3.7 7v10L12 21.4 20.3 17V7L12 2.6Z" />
      <path d="M3.9 7.2 12 11.8l8.1-4.6" />
      <path d="M12 11.8v9.4" />
    </>
  ),
  // Tính giá thành
  calculator: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <rect x="8" y="6.5" width="8" height="3" rx="0.8" />
      <path d="M8.5 13h.01M12 13h.01M15.5 13h.01M8.5 16.5h.01M12 16.5h.01M15.5 16.5h.01" />
    </>
  ),
  // Báo giá in ấn
  fileText: (
    <>
      <path d="M14 2.6H7A2 2 0 0 0 5 4.6v14.8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.6Z" />
      <path d="M14 2.6V7.6h5" />
      <path d="M8.5 13h7M8.5 16.5h7" />
    </>
  ),
  // Hợp đồng
  fileCheck: (
    <>
      <path d="M14 2.6H7A2 2 0 0 0 5 4.6v14.8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.6Z" />
      <path d="M14 2.6V7.6h5" />
      <path d="m9 14.6 2 2 4-4.2" />
    </>
  ),
  // Đơn hàng bán
  cart: (
    <>
      <circle cx="9.2" cy="20" r="1.4" />
      <circle cx="17" cy="20" r="1.4" />
      <path d="M2.5 3h2.2l2.3 11.3a1.5 1.5 0 0 0 1.5 1.2h8.2a1.5 1.5 0 0 0 1.5-1.2L20.6 7H6.1" />
    </>
  ),
  // Khách hàng
  users: (
    <>
      <path d="M15.5 20v-1.6a3.8 3.8 0 0 0-3.8-3.8H6.3a3.8 3.8 0 0 0-3.8 3.8V20" />
      <circle cx="9" cy="7.5" r="3.4" />
      <path d="M21.5 20v-1.6a3.8 3.8 0 0 0-2.9-3.7" />
      <path d="M15.5 4.2a3.8 3.8 0 0 1 0 7.3" />
    </>
  ),
  // Theo dõi sản xuất
  activity: <path d="M3 12h3.6l2.6-7.2 5 14.4 2.6-7.2H21" />,
  // Lệnh sản xuất
  clipboard: (
    <>
      <rect x="5" y="4.5" width="14" height="16.5" rx="2" />
      <rect x="8.75" y="2.5" width="6.5" height="3.8" rx="1.2" />
      <path d="M9 11h6M9 14.6h6M9 18.2h3.5" />
    </>
  ),
  // Kế hoạch SX
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="16" rx="2" />
      <path d="M3.5 9.8h17" />
      <path d="M8.5 2.6v4.4M15.5 2.6v4.4" />
    </>
  ),
  // Kho
  warehouse: (
    <>
      <path d="M3 8.6 12 4l9 4.6" />
      <path d="M5 10.4V20h14v-9.6" />
      <rect x="9" y="13.5" width="6" height="6.5" />
    </>
  ),
  // Kho kỹ thuật số
  database: (
    <>
      <ellipse cx="12" cy="5.8" rx="7.5" ry="3.1" />
      <path d="M4.5 5.8v6.2c0 1.7 3.36 3.1 7.5 3.1s7.5-1.4 7.5-3.1V5.8" />
      <path d="M4.5 12v6.2c0 1.7 3.36 3.1 7.5 3.1s7.5-1.4 7.5-3.1V12" />
    </>
  ),
  // Mua hàng
  bag: (
    <>
      <path d="M5.2 8h13.6l-1 12.2a1.2 1.2 0 0 1-1.2 1.1H7.4a1.2 1.2 0 0 1-1.2-1.1Z" />
      <path d="M8.5 8V6.4a3.5 3.5 0 0 1 7 0V8" />
    </>
  ),
  // Nhà cung cấp
  truck: (
    <>
      <rect x="2.5" y="6.5" width="11" height="9.5" rx="1" />
      <path d="M13.5 9.5h3.7l3.3 3.3V16h-7Z" />
      <circle cx="6.6" cy="18.2" r="1.7" />
      <circle cx="17" cy="18.2" r="1.7" />
    </>
  ),
  // Vai trò (roles / permissions)
  shield: (
    <>
      <path d="M12 2.6 5 5.4v5.2c0 4.3 3 7.6 7 8.8 4-1.2 7-4.5 7-8.8V5.4L12 2.6Z" />
      <path d="m9 11.6 2 2 4-4.2" />
    </>
  ),
  // Phòng ban (departments)
  building: (
    <>
      <rect x="3" y="4" width="11" height="17" rx="1" />
      <path d="M14 9h6a1 1 0 0 1 1 1v11h-7" />
      <path d="M6.5 8h4M6.5 12h4M6.5 16h4" />
      <path d="M17 13h1M17 17h1" />
    </>
  ),
  // Thông báo (chuông)
  bell: (
    <>
      <path d="M18 8.5a6 6 0 1 0-12 0c0 6-2.5 7.5-2.5 7.5h17S18 14.5 18 8.5Z" />
      <path d="M10.3 20a2 2 0 0 0 3.4 0" />
    </>
  ),
  // Row actions
  eye: (
    <>
      <path d="M2.8 12s3.35-6.7 9.2-6.7 9.2 6.7 9.2 6.7-3.35 6.7-9.2 6.7-9.2-6.7-9.2-6.7Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  printer: (
    <>
      <path d="M6.5 9V3.5h11V9" />
      <rect x="4" y="9" width="16" height="8" rx="2" />
      <path d="M7 14.5h10v6H7z" />
      <path d="M16.5 12h.01" />
    </>
  ),
  pencil: (
    <>
      <path d="m4 20 4.2-1 10.6-10.6a2 2 0 0 0-2.8-2.8L5.4 16.2Z" />
      <path d="m14.5 7.1 2.8 2.8M4 20l1.4-3.8 2.8 2.8Z" />
    </>
  ),
  send: (
    <>
      <path d="m21 3-7.4 18-3.1-7.5L3 10.4Z" />
      <path d="M10.5 13.5 21 3" />
    </>
  ),
  check: <path d="m4.5 12.5 4.7 4.7L19.8 6.8" />,
  x: <path d="m6 6 12 12M18 6 6 18" />,
  packageCheck: (
    <>
      <path d="M12 2.8 4 7v10l8 4.2 8-4.2V7Z" />
      <path d="M4.2 7.2 12 11.5l7.8-4.3M12 11.5v9.3" />
      <path d="m8.3 5 7.8 4.3" />
      <path d="m14.8 15.6 1.4 1.4 2.8-3" />
    </>
  ),
  ban: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m5.6 5.6 12.8 12.8" />
    </>
  ),
  trash: (
    <>
      <path d="M4.5 7h15M9 7V4h6v3M7 7l.8 13h8.4L17 7" />
      <path d="M10 11v5M14 11v5" />
    </>
  ),
  // Affordance
  chevron: <path d="m6 9 6 6 6-6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.6-3.6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  scissors: (
    <>
      <circle cx="6.5" cy="6.5" r="2.5" />
      <circle cx="6.5" cy="17.5" r="2.5" />
      <path d="M8.7 8.3 20 18M8.7 15.7 20 6" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.3 9.3a2.8 2.8 0 0 1 5.4 1c0 1.9-2.7 2.3-2.7 3.9" />
      <path d="M12 17.2h.01" />
    </>
  ),
  // Quy trình / luồng: hai nút trái gộp vào một nút phải
  workflow: (
    <>
      <rect x="3" y="3.5" width="6.5" height="5.5" rx="1.3" />
      <rect x="3" y="15" width="6.5" height="5.5" rx="1.3" />
      <rect x="14.5" y="9.25" width="6.5" height="5.5" rx="1.3" />
      <path d="M9.5 6.25h2.5a2 2 0 0 1 2 2v3.75" />
      <path d="M9.5 17.75h2.5a2 2 0 0 0 2-2v-1.75" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof ICONS;

export function Icon({
  name,
  size = 18,
  ...rest
}: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {ICONS[name]}
    </svg>
  );
}
