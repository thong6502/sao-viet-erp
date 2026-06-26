// Left navigation rail (ERP shell). Dark `--ink` surface, mono uppercase
// section labels, rust active row — per docs/UI_DESIGN.md (Navigation + Color).
// Sections collapse; items with `children` expand. Active row sets aria-current.
import { useState } from "react";
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
  children?: NavChild[];
}

interface NavSection {
  id: string;
  label: string;
  items: NavItem[];
}

// Mirrors the reference rail. `children` entries are placeholder sub-pages —
// rename/extend them as real routes land.
const NAV: NavSection[] = [
  {
    id: "tong-quan",
    label: "Tổng quan",
    items: [{ id: "dashboard", label: "Dashboard", icon: "grid" }],
  },
  {
    id: "kinh-doanh",
    label: "Kinh doanh",
    items: [
      { id: "san-pham", label: "Sản phẩm", icon: "box" },
      { id: "tinh-gia-thanh", label: "Tính giá thành", icon: "calculator" },
      { id: "bao-gia", label: "Báo giá in ấn", icon: "fileText" },
      { id: "hop-dong", label: "Hợp đồng", icon: "fileCheck" },
      { id: "don-hang-ban", label: "Đơn hàng bán", icon: "cart" },
      { id: "khach-hang", label: "Khách hàng", icon: "users" },
    ],
  },
  {
    id: "san-xuat",
    label: "Sản xuất",
    items: [
      { id: "theo-doi-sx", label: "Theo dõi sản xuất", icon: "activity" },
      {
        id: "lenh-sx",
        label: "Lệnh sản xuất",
        icon: "clipboard",
        children: [
          { id: "lenh-sx-tao", label: "Tạo lệnh" },
          { id: "lenh-sx-list", label: "Danh sách lệnh" },
        ],
      },
      { id: "ke-hoach-sx", label: "Kế hoạch SX", icon: "calendar" },
    ],
  },
  {
    id: "kho",
    label: "Kho",
    items: [
      {
        id: "kho",
        label: "Kho",
        icon: "warehouse",
        children: [
          { id: "kho-ton", label: "Tồn kho" },
          { id: "kho-nhap-xuat", label: "Nhập / Xuất kho" },
        ],
      },
      {
        id: "kho-kts",
        label: "Kho kỹ thuật số",
        icon: "database",
        children: [
          { id: "kts-file", label: "File thiết kế" },
          { id: "kts-tai-nguyen", label: "Tài nguyên" },
        ],
      },
    ],
  },
  {
    id: "thu-mua",
    label: "Thu mua",
    items: [
      { id: "mua-hang", label: "Mua hàng", icon: "bag" },
      { id: "nha-cung-cap", label: "Nhà cung cấp", icon: "truck" },
    ],
  },
  {
    id: "quan-tri",
    label: "Quản trị",
    items: [
      { id: "nguoi-dung", label: "Người dùng", icon: "users" },
      { id: "phong-ban", label: "Phòng ban", icon: "building" },
      { id: "vai-tro", label: "Vai trò", icon: "shield" },
    ],
  },
];

interface SidebarProps {
  activeId: string;
  onSelect: (id: string) => void;
}

export function Sidebar({ activeId, onSelect }: SidebarProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(set: Set<string>, id: string): Set<string> {
    const next = new Set(set);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  }

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
        {NAV.map((section) => {
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
  onSelect: (id: string) => void;
  onToggle: () => void;
}

function NavRow({ item, activeId, isOpen, onSelect, onToggle }: NavRowProps) {
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
