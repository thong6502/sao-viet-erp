// Left navigation rail (ERP shell). Dark `--ink` surface, mono uppercase
// section labels, rust active row — per docs/UI_DESIGN.md (Navigation + Color).
// Sections collapse; items with `children` expand. Active row sets aria-current.
// Each item is gated by a `module` key: only modules the current role can Read
// are shown (feat-010) — sections with no visible items are dropped.
// The user widget lives in the top header (Topbar), not here (feat-018).
import { useEffect, useState } from "react";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { VOUCHER_PAGE_LABEL } from "../constants/features";
import { Icon, type IconName } from "./Icons";
import "./sidebar.css";

interface NavChild {
  id: string;
  label: string;
}

export interface NavItem {
  id: string;
  label: string;
  icon: IconName;
  module: string;
  modules?: string[];
  children?: NavChild[];
}

export const SELF_SERVICE_MODULE = "self_service";

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
      // Bản đồ luồng khối bán hàng — hiện cho ai vào được BẤT KỲ màn KD nào (không đẻ quyền mới).
      {
        id: "quy-trinh-kinh-doanh",
        label: "Quy trình kinh doanh",
        icon: "workflow",
        module: "tinh_gia_thanh",
        modules: ["tinh_gia_thanh", "bao_gia", "don_hang_ban", "khach_hang"],
      },
      { id: "tinh-gia", label: "Tính giá", icon: "calculator", module: "tinh_gia_thanh" },
      { id: "bao-gia", label: "Báo giá in ấn", icon: "fileText", module: "bao_gia" },
      { id: "don-hang-ban", label: "Đơn hàng bán", icon: "cart", module: "don_hang_ban" },
      { id: "khach-hang", label: "Khách hàng", icon: "users", module: "khach_hang" },
    ],
  },
  {
    // Bàn của bộ phận Kế hoạch sản xuất: nhận đơn Sale đã chuyển xuống → bung lệnh sản xuất.
    id: "san-xuat",
    label: "Sản xuất",
    items: [
      { id: "ke-hoach-sx", label: "Kế hoạch sản xuất", icon: "workflow", module: "san_xuat" },
      { id: "bai-ghep", label: "Bài ghép", icon: "layers", module: "san_xuat" },
      { id: "xep-lich-cong-doan", label: "Xếp lịch công đoạn", icon: "calendar", module: "san_xuat" },
    ],
  },
  {
    id: "thu-mua",
    label: "Thu mua",
    items: [
      {
        id: "yeu-cau-mua-hang",
        label: "Yêu cầu mua hàng",
        icon: "clipboard",
        module: "thu_mua",
        // ke_toan: kế toán bấm mã YCMH từ PMH/Phiếu chi để truy vết ngược.
        modules: [
          "thu_mua",
          "bao_gia",
          "kho",
          "san_xuat",
          "dm_giay_vat_tu",
          "ke_toan",
        ],
      },
      { id: "mua-hang", label: "Mua hàng", icon: "bag", module: "thu_mua" },
      { id: "nha-cung-cap", label: "Nhà cung cấp", icon: "truck", module: "thu_mua" },
    ],
  },
  {
    id: "ke-toan",
    label: "Kế toán",
    items: [
      { id: "ke-toan-yeu-cau-mua", label: "Yêu cầu mua hàng", icon: "fileCheck", module: "ke_toan" },
      { id: "ke-toan-phieu-chi", label: VOUCHER_PAGE_LABEL, icon: "calculator", module: "ke_toan" },
      { id: "ke-toan-phieu-thu", label: "Phiếu thu", icon: "fileText", module: "ke_toan" },
      { id: "ke-toan-tai-khoan", label: "Tài khoản ngân hàng", icon: "building", module: "ke_toan" },
    ],
  },
  {
    // SECTION "Nhập xuất kho" — nghiệp vụ chứng từ kho (đề nghị + phiếu nhập/xuất). TÁCH khỏi
    // "Kho hàng" vì section đó chỉ để LIỆT KÊ các kho vật lý đã khai báo, không chứa màn nghiệp vụ.
    id: "nhap-xuat-kho",
    label: "Nhập xuất kho",
    items: [
      // MỘT mục — bên trong chia tab VIỆC (Đề nghị · Hộp yêu cầu) × CHIỀU (Nhập · Xuất).
      // Tab "Hộp yêu cầu" tự ẩn nếu vai không có create/view_stock (gate trong KhoPage).
      // Tên "Đề nghị & Cấp phát": đúng việc của module (xin vật tư → kho cấp), phân biệt với
      // section "Kho hàng" (kho vật lý: tồn/phiếu/ngưỡng).
      { id: "kho-main", label: "Đề nghị nhập xuất", icon: "warehouse", module: "kho" },
    ],
  },
  {
    // SECTION "Kho hàng" — CHỈ chứa các kho ĐÃ KHAI BÁO (inject ĐỘNG từ AppShell qua
    // dynamicItems, key theo section id). Không có kho nào → section tự ẩn.
    id: "kho-hang",
    label: "Kho hàng",
    items: [],
  },
  {
    id: "cau-hinh-dm",
    label: "Cấu hình danh mục",
    items: [
      { id: "loai-san-pham", label: "Loại sản phẩm", icon: "clipboard", module: "dm_loai_san_pham" },
      { id: "may-thiet-bi", label: "Thiết bị & Máy in", icon: "warehouse", module: "dm_thiet_bi" },
      { id: "cong-doan", label: "Công đoạn", icon: "activity", module: "dm_cong_doan" },
      { id: "bu-hao", label: "Bù hao", icon: "fileText", module: "dm_cong_doan" },
      // Đơn vị & quy đổi: dùng chung cho khoán · kho · mua hàng, nên nằm ở danh mục chứ không
      // chôn trong màn Lương. MỘT mục cho hai bảng (đơn vị · cặp "1 tấn = 1.000 kg") — tách hai
      // mục thì hai cái tên gần trùng nhau, không ai đoán được vào đâu làm gì.
      { id: "don-vi", label: "Đơn vị & quy đổi", icon: "activity", module: "dm_cong_doan" },
      { id: "chung-loai-giay", label: "Chủng loại giấy", icon: "fileText", module: "kho" },
      { id: "giay", label: "Giấy", icon: "bag", module: "kho" },
      { id: "vat-tu-in-an", label: "Vật tư in ấn", icon: "bag", module: "kho" },
      // Khuôn bế: khai báo nơi lưu trữ khuôn (số kệ · ngày làm · tình trạng). Quyền RIÊNG `khuon_be`.
      { id: "khuon-be", label: "Khuôn bế", icon: "clipboard", module: "khuon_be" },
      // Khai báo kho: màn CRUD tạo/sửa kho. Kho tạo ở đây tự hiện thành mục dưới SECTION "Kho hàng".
      { id: "khai-bao-kho", label: "Khai báo kho", icon: "warehouse", module: "kho" },
    ],
  },
  {
    id: "nhan-su-luong",
    label: "Nhân sự & Lương",
    items: [
      // Phòng ban = cây tổ chức: liệt kê theo HỒ SƠ, đếm theo hồ sơ, điều chuyển ghi Quá
      // trình công tác → việc của HCNS, không phải quản trị hệ thống. Đứng trước Hồ sơ nhân
      // sự vì nó là cái khung chứa.
      { id: "phong-ban", label: "Phòng ban", icon: "building", module: "phong_ban" },
      { id: "nhan-su", label: "Hồ sơ nhân sự", icon: "users", module: "nhan_su" },
      { id: "cham-cong", label: "Chấm công", icon: "activity", module: "nhan_su", modules: ["nhan_su", SELF_SERVICE_MODULE] },
      { id: "nghi-phep", label: "Nghỉ phép", icon: "calendar", module: "nghi_phep" },
      { id: "tang-ca", label: "Tăng ca", icon: "clock", module: "tang_ca" },
      {
        id: "luong",
        label: "Lương",
        icon: "calculator",
        module: "luong",
        modules: ["luong", SELF_SERVICE_MODULE],
      },
    ],
  },
  {
    id: "quan-tri",
    label: "Quản lý hệ thống",
    items: [
      // Màn "Người dùng" ĐÃ BỎ: mọi tài khoản thuộc một hồ sơ nhân viên → quản tài khoản
      // ngay trong Hồ sơ nhân sự (tab "Tài khoản & Quyền"). Quyền `nguoi_dung` vẫn gác các
      // thao tác đó, chỉ là không còn màn riêng. "Phòng ban" dời sang Nhân sự & Lương.
      { id: "nhat-ky", label: "Nhật ký", icon: "activity", module: "activity_log" },
    ],
  },
];

// id -> module key, for the shell's route gating.
export const MODULE_BY_NAV_ID: Record<string, string> = Object.fromEntries(
  NAV.flatMap((s) => s.items.map((i) => [i.id, i.module])),
);

export const MODULES_BY_NAV_ID: Record<string, string[]> = Object.fromEntries(
  NAV.flatMap((s) => s.items.map((i) => [i.id, i.modules ?? [i.module]])),
);

interface SidebarProps {
  activeId: string;
  onSelect: (id: string) => void;
  readable: ReadonlySet<string>;
  /** Menu con ĐỘNG theo item id (vd các kho đã cấu hình dưới "Kho hàng"). */
  itemChildren?: Record<string, NavChild[]>;
  /** Item ĐỘNG chèn vào 1 SECTION (theo section id) — vd các kho đã khai báo dưới section "Kho hàng". */
  dynamicItems?: Record<string, NavItem[]>;
  /** Badge số (đỏ) theo item id — vd "nghi-phep": số đơn chờ duyệt. Ẩn khi ≤0/absent. */
  badges?: Record<string, number>;
  /** Item ẩn hẳn dù có quyền Read module — cho mục cần quyền CHI TIẾT (vd "Hộp yêu cầu kho"
   *  cần `can_create`/`can_view_stock`). Sidebar không biết ma trận quyền nên AppShell tính sẵn. */
  hiddenIds?: ReadonlySet<string>;
}

export function Sidebar({ activeId, onSelect, readable, itemChildren, dynamicItems, badges, hiddenIds }: SidebarProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(set: Set<string>, id: string): Set<string> {
    const next = new Set(set);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  }

  // Only show items whose module the role can Read; drop now-empty sections. Inject any
  // dynamic children (e.g. configured warehouses) onto their host item.
  const sections = NAV.map((s) => {
    // Gộp item tĩnh + item ĐỘNG của section (vd kho đã khai báo dưới "Kho hàng"), rồi lọc theo quyền.
    const merged = [...s.items, ...(dynamicItems?.[s.id] ?? [])];
    return {
      ...s,
      items: merged
        .filter((i) => !hiddenIds?.has(i.id))
        .filter((i) => (i.modules ?? [i.module]).some((module) => readable.has(module)))
        .map((i) => {
          const dyn = itemChildren?.[i.id];
          return dyn && dyn.length ? { ...i, children: dyn } : i;
        }),
    };
  }).filter((s) => s.items.length > 0);

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
