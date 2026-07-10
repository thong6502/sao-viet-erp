// Left navigation rail (ERP shell). Dark `--ink` surface, mono uppercase
// section labels, rust active row — per docs/UI_DESIGN.md (Navigation + Color).
// Sections collapse; items with `children` expand. Active row sets aria-current.
// Each item is gated by a `module` key: only modules the current role can Read
// are shown (feat-010) — sections with no visible items are dropped.
// The user widget lives in the top header (Topbar), not here (feat-018).
import { useEffect, useState } from "react";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { Icon, type IconName } from "./Icons";
import "./sidebar.css";

interface NavChild {
  id: string;
  label: string;
}

interface NavItem {
  id: string;
  label: string;
  icon: IconName;
  module: string;
  children?: NavChild[];
}

interface NavSection {
  id: string;
  label: string;
  items: NavItem[];
}

// Mirrors the reference rail. `module` is the permission key each item is gated
// on; `children` entries are placeholder sub-pages — rename/extend as routes land.
const NAV: NavSection[] = [
  {
    id: "tong-quan",
    label: "Tổng quan",
    items: [
      { id: "dashboard", label: "Dashboard", icon: "grid", module: "dashboard" },
      { id: "ho-so-cua-toi", label: "Hồ sơ của tôi", icon: "users", module: "dashboard" },
    ],
  },
  {
    id: "kinh-doanh",
    label: "Kinh doanh",
    items: [
      { id: "bao-gia", label: "Báo giá in ấn", icon: "fileText", module: "bao_gia" },
      { id: "don-hang-ban", label: "Đơn hàng bán", icon: "cart", module: "don_hang_ban" },
      { id: "khach-hang", label: "Khách hàng", icon: "users", module: "khach_hang" },
    ],
  },
  {
    id: "san-xuat",
    label: "Sản xuất",
    items: [
      { id: "theo-doi-sx", label: "Theo dõi sản xuất", icon: "activity", module: "san_xuat" },
      {
        id: "lenh-sx",
        label: "Lệnh sản xuất",
        icon: "clipboard",
        module: "san_xuat",
        children: [
          { id: "lenh-sx-tao", label: "Tạo lệnh" },
          { id: "lenh-sx-list", label: "Danh sách lệnh" },
        ],
      },
      { id: "ke-hoach-sx", label: "Kế hoạch SX", icon: "calendar", module: "san_xuat" },
    ],
  },
  {
    id: "kho",
    label: "Kho",
    items: [
      { id: "kho-hang", label: "Kho hàng", icon: "warehouse", module: "kho" },
    ],
  },
  {
    id: "thu-mua",
    label: "Thu mua",
    items: [
      { id: "mua-hang", label: "Mua hàng", icon: "bag", module: "thu_mua" },
      { id: "nha-cung-cap", label: "Nhà cung cấp", icon: "truck", module: "thu_mua" },
    ],
  },
  {
    id: "cau-hinh-dm",
    label: "Cấu hình danh mục",
    items: [
      { id: "loai-san-pham", label: "Loại sản phẩm", icon: "clipboard", module: "dm_loai_san_pham" },
      { id: "may-thiet-bi", label: "Thiết bị & Máy in", icon: "warehouse", module: "dm_thiet_bi" },
      { id: "cong-doan", label: "Công đoạn gia công", icon: "activity", module: "dm_cong_doan" },
      { id: "bu-hao", label: "Bù hao", icon: "fileText", module: "dm_cong_doan" },
      { id: "chung-loai-giay", label: "Chủng loại giấy", icon: "fileText", module: "kho" },
      { id: "kho-giay-chuan", label: "Khổ giấy chuẩn", icon: "clipboard", module: "kho" },
      { id: "giay", label: "Giấy", icon: "bag", module: "kho" },
      { id: "vat-tu-in-an", label: "Vật tư in ấn", icon: "bag", module: "kho" },
      { id: "cau-hinh-kho", label: "Cấu hình kho hàng", icon: "warehouse", module: "dm_kho" },
    ],
  },
  {
    id: "nhan-su-luong",
    label: "Nhân sự & Lương",
    items: [
      { id: "nhan-su", label: "Hồ sơ nhân sự", icon: "users", module: "nhan_su" },
      { id: "cham-cong", label: "Chấm công", icon: "activity", module: "nhan_su" },
      { id: "nghi-phep", label: "Nghỉ phép", icon: "calendar", module: "nghi_phep" },
      { id: "luong", label: "Lương", icon: "calculator", module: "luong" },
    ],
  },
  {
    id: "quan-tri",
    label: "Quản lý hệ thống",
    items: [
      { id: "nguoi-dung", label: "Người dùng", icon: "users", module: "nguoi_dung" },
      { id: "phong-ban", label: "Phòng ban", icon: "building", module: "phong_ban" },
      { id: "nhat-ky", label: "Nhật ký", icon: "activity", module: "activity_log" },
    ],
  },
];

// id -> module key, for the shell's route gating.
export const MODULE_BY_NAV_ID: Record<string, string> = Object.fromEntries(
  NAV.flatMap((s) => s.items.map((i) => [i.id, i.module])),
);

interface SidebarProps {
  activeId: string;
  onSelect: (id: string) => void;
  readable: ReadonlySet<string>;
  /** Menu con ĐỘNG theo item id (vd các kho đã cấu hình dưới "Kho hàng"). */
  itemChildren?: Record<string, NavChild[]>;
  /** Badge số (đỏ) theo item id — vd "nghi-phep": số đơn chờ duyệt. Ẩn khi ≤0/absent. */
  badges?: Record<string, number>;
}

export function Sidebar({ activeId, onSelect, readable, itemChildren, badges }: SidebarProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(set: Set<string>, id: string): Set<string> {
    const next = new Set(set);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  }

  // Only show items whose module the role can Read; drop now-empty sections. Inject any
  // dynamic children (e.g. configured warehouses) onto their host item.
  const sections = NAV.map((s) => ({
    ...s,
    items: s.items
      .filter((i) => readable.has(i.module))
      .map((i) => {
        const dyn = itemChildren?.[i.id];
        return dyn && dyn.length ? { ...i, children: dyn } : i;
      }),
  })).filter((s) => s.items.length > 0);

  // Auto-mở item cha khi một menu con của nó đang active (mở lại trang / deep-link).
  useEffect(() => {
    const host = sections
      .flatMap((s) => s.items)
      .find((i) => i.children?.some((c) => c.id === activeId));
    if (host) setExpanded((prev) => (prev.has(host.id) ? prev : new Set(prev).add(host.id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, itemChildren]);

  return (
    <aside className="sidebar">
      <a className="sidebar__brand" href="#" aria-label="Sao Việt Nhật — Hệ thống ERP">
        <span className="sidebar__logo">
          <img src={logoUrl} alt="" width={28} height={28} />
        </span>
        <span className="sidebar__brandtext">
          <strong className="sidebar__name">Sao Việt Nhật</strong>
          <span className="sidebar__tag">Hệ thống ERP</span>
        </span>
      </a>

      <nav className="sidebar__nav" aria-label="Điều hướng chính">
        {sections.map((section) => {
          const isCollapsed = collapsed.has(section.id);
          return (
            <div className="sidebar__section" key={section.id}>
              <button
                type="button"
                className="sidebar__sectionhead"
                aria-expanded={!isCollapsed}
                onClick={() => setCollapsed((s) => toggle(s, section.id))}
              >
                <span>{section.label}</span>
                <Icon
                  name="chevron"
                  size={14}
                  className={`sidebar__caret${isCollapsed ? " is-collapsed" : ""}`}
                />
              </button>

              {!isCollapsed && (
                <ul className="sidebar__items">
                  {section.items.map((item) => (
                    <NavRow
                      key={item.id}
                      item={item}
                      activeId={activeId}
                      isOpen={expanded.has(item.id)}
                      badge={badges?.[item.id] ?? 0}
                      onSelect={onSelect}
                      onToggle={() => setExpanded((s) => toggle(s, item.id))}
                    />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

interface NavRowProps {
  item: NavItem;
  activeId: string;
  isOpen: boolean;
  badge?: number;
  onSelect: (id: string) => void;
  onToggle: () => void;
}

function NavRow({ item, activeId, isOpen, badge, onSelect, onToggle }: NavRowProps) {
  const hasChildren = !!item.children?.length;
  const childActive = item.children?.some((c) => c.id === activeId) ?? false;
  const active = activeId === item.id || (childActive && !isOpen);

  return (
    <li>
      <button
        type="button"
        className={`sidebar__link${active ? " is-active" : ""}`}
        aria-current={activeId === item.id ? "page" : undefined}
        aria-expanded={hasChildren ? isOpen : undefined}
        onClick={() => (hasChildren ? onToggle() : onSelect(item.id))}
      >
        <Icon name={item.icon} className="sidebar__icon" />
        <span className="sidebar__label">{item.label}</span>
        {badge != null && badge > 0 && (
          <span className="sidebar__badge" aria-label={`${badge} chờ xử lý`}>{badge > 99 ? "99+" : badge}</span>
        )}
        {hasChildren && (
          <Icon
            name="chevron"
            size={14}
            className={`sidebar__caret${isOpen ? "" : " is-collapsed"}`}
          />
        )}
      </button>

      {hasChildren && isOpen && (
        <ul className="sidebar__sub">
          {item.children!.map((child) => (
            <li key={child.id}>
              <button
                type="button"
                className={`sidebar__sublink${activeId === child.id ? " is-active" : ""}`}
                aria-current={activeId === child.id ? "page" : undefined}
                onClick={() => onSelect(child.id)}
              >
                {child.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
