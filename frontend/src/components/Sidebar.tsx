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
  /** Khoá quyền RIÊNG của menu con. Bỏ trống thì con dùng chung khoá của cha (mặc định cũ).
   *  Có từ 10/08/2026 khi phân hệ Kế toán tách mỗi màn một khoá — ba màn con của "Kế toán thu
   *  mua" nay là ba ô quyền khác nhau, không còn cùng bật/tắt theo cha. */
  module?: string;
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
// Menu hiện cho MỌI tài khoản đăng nhập KHÔNG CẦN cấp ô nào — tức luật ngầm, đi ngược Luật 1
// của đợt phân quyền ("không có ô nào bật thì không vào được").
//
// ⚠️ NAY RỖNG, và cố ý để rỗng. Hai mục từng nằm đây đều đã có ô thật:
//   • "yeu-cau-mua-hang" → khoá `yeu_cau_mua_hang` (10/08/2026)
//   • "noi-quy"          → khoá `noi_quy`, được seed + migration cấp cho MỌI vai nên thực tế ai
//                          cũng vẫn đọc được, khác ở chỗ giờ quản trị GỠ ĐƯỢC.
// Thêm id mới vào đây = tạo lại đúng cái luật ngầm vừa dọn. Muốn "ai cũng vào được" thì cấp ô đó
// cho mọi vai (xem `RoleRepository.O_MAC_DINH`), đừng bỏ qua cổng quyền.
export const AUTHENTICATED_NAV_IDS: ReadonlySet<string> = new Set([]);

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
      // "Nội quy công ty" ĐÃ DỜI xuống section "Nhân sự & Lương" (chốt của chủ 09/08/2026):
      // nội quy lao động là tài liệu của HCNS, để ở "Tổng quan" thì không ai đoán ra chỗ tìm.
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
      // Kỹ thuật máy: MỘT module quyền cho cả hai màn — cùng một người (thợ sửa chữa) làm cả hai
      // việc, tách hai dòng quyền chỉ tổ bắt người cấp quyền tick hai lần.
      { id: "sua-chua-may", label: "Sửa chữa máy", icon: "settings", module: "ky_thuat_may" },
      { id: "phieu-bao-tri", label: "Phiếu bảo trì", icon: "clock", module: "ky_thuat_may" },
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
        module: "yeu_cau_mua_hang",
        // ke_toan: kế toán bấm mã YCMH từ PMH/Phiếu chi để truy vết ngược.
        // Danh sách dự phòng GIỮ NGUYÊN các phân hệ đề nghị vật tư — nó là TẬP CON của
        // DEPARTMENT_REQUEST_READER_MODULES ở backend. Rộng hơn backend là menu hiện mà API trả
        // 403; hẹp hơn thì chỉ ẩn menu, quyền đọc dữ liệu không suy suyển.
        //
        // ⚠️ CỐ Ý THIẾU "thu_mua" (chủ chốt 15/08/2026: "tôi chỉ cấp quyền cho mình nhìn thấy
        // menu thu mua thôi"). Người mua hàng VẪN đọc được YCMH ở máy chủ — bắt buộc, vì màn Mua
        // hàng gọi thẳng API đó để nạp ô chọn nguồn (`loadSources`). Chỉ là không tự động hiện
        // thêm một mục menu khi quản trị mới cấp mỗi ô Mua hàng; muốn có menu thì cấp ô
        // "Yêu cầu mua hàng". Gỡ dòng ngoại lệ trong `test_giao_dien_khop_may_chu.py` nếu đảo lại.
        modules: [
          "yeu_cau_mua_hang",
          "bao_gia",
          "kho",
          "san_xuat",
          "dm_giay",
          "ke_toan",
        ],
      },
      { id: "mua-hang", label: "Mua hàng", icon: "bag", module: "thu_mua" },
      { id: "nha-cung-cap", label: "Nhà cung cấp", icon: "truck", module: "nha_cung_cap" },
    ],
  },
  {
    id: "ke-toan",
    label: "Kế toán",
    items: [
      // BỎ NHÓM CON "Kế toán thu mua" (chủ chốt 12/08/2026): ba màn dưới nay đứng NGANG HÀNG với
      // Phiếu thu · Công nợ phải thu · Tài khoản ngân hàng. Lý do gộp cũ (số liệu công nợ phải trả
      // đến từ PMH + phiếu chi) đúng về dữ liệu nhưng sai về thao tác: bên THU đã phẳng, để bên CHI
      // thụt thêm một cấp thì hai vế đối xứng của cùng một việc lại nằm hai độ sâu khác nhau.
      //
      // Icon đi theo CẶP cho dễ đọc: hai phiếu dùng `fileText`, hai công nợ dùng `calculator`.
      //
      // "Đơn mua hàng" TRƯỚC ĐÂY mang nhãn "Yêu cầu mua hàng" — nhãn SAI: màn này hiển thị PHIẾU
      // MUA HÀNG (`/api/accounting/inbox` trả `PurchaseRequestListOut`), không phải YCMH. Nhìn
      // menu cũ tưởng có hai chỗ xem YCMH, thật ra một chỗ là PMH.
      //
      // Đây cũng là nơi DUYỆT đơn mua hàng (chủ 04/08/2026: "phải duyệt ở phần kế toán chứ") —
      // màn Mua hàng bên Thu mua không còn nút duyệt nữa.
      {
        id: "ke-toan-don-mua-hang",
        label: "Đơn mua hàng",
        icon: "clipboard",
        module: "ke_toan",
      },
      {
        id: "ke-toan-phieu-chi",
        label: VOUCHER_PAGE_LABEL,
        icon: "fileText",
        module: "phieu_chi",
      },
      {
        id: "ke-toan-cong-no",
        label: "Công nợ phải trả",
        icon: "calculator",
        module: "cong_no_phai_tra",
      },
      {
        id: "ke-toan-phieu-thu",
        label: "Phiếu thu",
        icon: "fileText",
        module: "phieu_thu",
      },
      {
        id: "ke-toan-cong-no-phai-thu",
        label: "Công nợ phải thu",
        icon: "calculator",
        module: "cong_no_phai_thu",
      },
      {
        id: "ke-toan-tai-khoan-ngan-hang",
        label: "Tài khoản ngân hàng",
        icon: "database",
        module: "tk_ngan_hang",
      },
    ],
  },
  {
    // SECTION "Kho hàng" — GỘP màn nghiệp vụ kho (Yêu cầu nhập xuất · Báo cáo kho) + các kho ĐÃ
    // KHAI BÁO (inject ĐỘNG từ AppShell qua dynamicItems, key theo section id → xếp SAU 2 mục
    // nghiệp vụ, vì merge = [...items, ...dynamicItems]). `id`/`module` giữ nguyên nên routing +
    // quyền không đổi khi dời khỏi section "Nhập xuất kho" cũ (đã bỏ).
    id: "kho-hang",
    label: "Kho hàng",
    items: [
      // MỘT mục — bên trong chia tab VIỆC (Yêu cầu · Hộp yêu cầu) × CHIỀU (Nhập · Xuất).
      // Tab "Hộp yêu cầu" tự ẩn nếu vai không có create/view_stock (gate trong KhoPage).
      { id: "kho-main", label: "Yêu cầu nhập xuất", icon: "warehouse", module: "kho" },
      // Báo cáo kho (kế toán): sổ nhập-xuất + khóa kỳ + export MISA. AppShell ẩn nếu thiếu close_book.
      { id: "kho-baocao", label: "Báo cáo kho", icon: "fileText", module: "kho" },
    ],
  },
  {
    id: "cau-hinh-dm",
    label: "Cấu hình danh mục",
    items: [
      { id: "loai-san-pham", label: "Loại sản phẩm", icon: "clipboard", module: "dm_loai_san_pham" },
      { id: "may-thiet-bi", label: "Thiết bị & Máy móc", icon: "warehouse", module: "dm_thiet_bi" },
      { id: "cong-doan", label: "Công đoạn", icon: "activity", module: "dm_cong_doan" },
      { id: "bu-hao", label: "Bù hao", icon: "fileText", module: "dm_bu_hao" },
      // Đơn vị & quy đổi: dùng chung cho khoán · kho · mua hàng, nên nằm ở danh mục chứ không
      // chôn trong màn Lương. MỘT mục cho hai bảng (đơn vị · cặp "1 tấn = 1.000 kg") — tách hai
      // mục thì hai cái tên gần trùng nhau, không ai đoán được vào đâu làm gì.
      { id: "don-vi", label: "Đơn vị & quy đổi", icon: "activity", module: "dm_don_vi" },
      { id: "chung-loai-giay", label: "Chủng loại giấy", icon: "fileText", module: "dm_chung_loai_giay" },
      { id: "giay", label: "Giấy", icon: "bag", module: "dm_giay" },
      { id: "vat-tu-in-an", label: "Vật tư khác", icon: "bag", module: "dm_vat_tu" },
      // Khuôn bế: khai báo nơi lưu trữ khuôn (số kệ · ngày làm · tình trạng). Quyền RIÊNG `khuon_be`.
      { id: "khuon-be", label: "Khuôn bế", icon: "clipboard", module: "khuon_be" },
      // Khai báo kho: màn CRUD tạo/sửa kho. Kho tạo ở đây tự hiện thành mục dưới SECTION "Kho hàng".
      { id: "khai-bao-kho", label: "Khai báo kho", icon: "warehouse", module: "dm_kho_hang" },
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
      // Khoá RIÊNG `cham_cong` (10/08/2026) — trước đây dùng chung `nhan_su` nên cấp quyền xem
      // hồ sơ là mở luôn bảng công cả công ty. Vẫn nhận SELF_SERVICE: thợ chỉ có ô Tự phục vụ
      // cũng phải vào được màn này để bấm chấm công và xem công của mình.
      { id: "cham-cong", label: "Chấm công", icon: "activity", module: "cham_cong", modules: ["cham_cong", SELF_SERVICE_MODULE] },
      { id: "nghi-phep", label: "Nghỉ phép", icon: "calendar", module: "nghi_phep" },
      { id: "tang-ca", label: "Tăng ca", icon: "clock", module: "tang_ca" },
      {
        id: "luong",
        label: "Lương",
        icon: "calculator",
        module: "luong",
        modules: ["luong", SELF_SERVICE_MODULE],
      },
      // Nội quy lao động: ai cũng phải đọc, nhưng từ 10/08/2026 đi qua Ô QUYỀN `noi_quy` thật
      // (seed + migration cấp cho MỌI vai) chứ không còn nằm trong AUTHENTICATED_NAV_IDS.
      // ⚠ ĐỪNG dời lại lên "Tổng quan" và ĐỪNG đổi `id`/`module`: id là khoá route + khoá
      // MODULE_BY_NAV_ID, đổi là gãy cả điều hướng lẫn cổng quyền.
      {
        id: "noi-quy",
        label: "Nội quy công ty",
        icon: "book",
        module: "noi_quy",
        modules: ["noi_quy"],
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

/** nav id → những module cần có quyền đọc để vào được mục đó.
 *
 * ⚠️ PHẢI gom cả MENU CON. `NavChild` không khai `module` riêng nên nó **thừa hưởng** của item
 * cha; thiếu vế này thì mọi mục con tra ra `undefined` và `AppShell` chặn 403 — kể cả giám đốc
 * toàn quyền. Đúng lỗi đã xảy ra 04/08/2026 khi gom "Đơn mua hàng" + "Phiếu chi" thành con của
 * "Kế toán thu mua": hai mục đang chạy tốt bỗng báo "không có quyền truy cập".
 */
export const MODULES_BY_NAV_ID: Record<string, string[]> = Object.fromEntries(
  NAV.flatMap((s) =>
    s.items.flatMap((i) => {
      const mods = i.modules ?? [i.module];
      return [
        [i.id, mods] as [string, string[]],
        // Menu con có khoá riêng thì dùng khoá đó — nếu vẫn kế thừa của cha thì hàng rào ở
        // AppShell sẽ cho vào cả ba màn con chỉ vì có quyền một màn.
        ...(i.children ?? []).map(
          (c) => [c.id, c.module ? [c.module] : mods] as [string, string[]],
        ),
      ];
    }),
  ),
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
        .filter((i) =>
          AUTHENTICATED_NAV_IDS.has(i.id) ||
          (i.modules ?? [i.module]).some((module) => readable.has(module)),
        )
        .map((i) => {
          const dyn = itemChildren?.[i.id];
          if (dyn && dyn.length) return { ...i, children: dyn };
          // Menu con có khoá riêng → ẩn con nào chưa được cấp. Con không khai khoá thì theo cha
          // (giữ nguyên nếp cũ của mọi nhóm khác).
          if (!i.children?.some((c) => c.module)) return i;
          return {
            ...i,
            children: i.children.filter((c) => !c.module || readable.has(c.module)),
          };
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
          <span
            className="sidebar__badge"
            aria-label={`${badge} thông báo chưa đọc`}
            title={`${badge} thông báo chưa đọc`}
          >
            {badge > 99 ? "99+" : badge}
          </span>
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
