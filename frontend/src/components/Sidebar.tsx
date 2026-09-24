// Left navigation rail (ERP shell). Dark `--ink` surface, uppercase
// section labels, rust active row — per docs/UI_DESIGN.md (Navigation + Color).
// Sections collapse; items with `children` expand. Active row sets aria-current.
// Each item is gated by a `module` key: only modules the current role can Read
// are shown (feat-010) — sections with no visible items are dropped.
// The user widget lives in the top header (Topbar), not here (feat-018).
import { useEffect, useState } from "react";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { BAI_GHEP_ENABLED, VOUCHER_PAGE_LABEL } from "../constants/features";
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
  /** Mức thụt lề (item ĐỘNG theo cây, vd bàn tổ dưới xưởng) — 0/undefined = thẳng hàng. */
  indent?: number;
  /** Id item CHA trong cây ĐỘNG (vd "Nhóm in máy 5 màu" nằm dưới "Tổ in"). Khai nó thì hàng cha
   *  mọc nút ▾ để GẬP cả nhánh — cây xưởng 11 tổ + nhóm in kéo menu dài quá màn hình. Khác
   *  `children`: con ở đây vẫn là item đầy đủ (icon, badge, bấm vào mở bàn của chính nó). */
  parentId?: string;
}

// Ô `self_service` ĐÃ BỎ 15/08/2026 — phần "của tôi" là quyền đương nhiên, không phải ô cấp.
// Hằng giữ lại tạm cho tới khi dọn xong khoá cũ ở máy chủ; menu KHÔNG còn ăn theo nó.
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
export const NAV: NavSection[] = [
  {
    id: "tong-quan",
    label: "Tổng quan",
    items: [
      { id: "dashboard", label: "Trang chủ", icon: "grid", module: "dashboard" },
      // Hồ sơ CỦA CHÍNH MÌNH ⇒ khoá `self_service` — ô mà `rbac_repo.O_MAC_DINH` cấp sẵn cho
      // MỌI vai mới, và cũng chính là ô máy chủ gác dữ liệu tự phục vụ (`employees.py` ·
      // `attendance.py`). Trước 24/09/2026 mục này ăn ké `dashboard`: tắt Trang chủ của một vai
      // là họ mất luôn đường vào hồ sơ của chính mình. Ô này có DÒNG RIÊNG trong ma trận (nhóm
      // "Tổng quan", ngay dưới Trang chủ) — nó quyết định mục menu này hiện hay không.
      { id: "ho-so-cua-toi", label: "Hồ sơ của tôi", icon: "users", module: "self_service" },
      // "Nội quy công ty" ĐÃ DỜI xuống section "Nhân sự & Lương" (chốt của chủ 09/08/2026):
      // nội quy lao động là tài liệu của HCNS, để ở "Tổng quan" thì không ai đoán ra chỗ tìm.
    ],
  },
  {
    id: "kinh-doanh",
    label: "Kinh doanh",
    items: [
      // Bản đồ luồng khối bán hàng. MỘT MỤC = MỘT Ô QUYỀN từ 24/09/2026 (mg `0329`): trước đó
      // mục này ăn ké bốn khoá KD, nên ma trận phân quyền không có dòng nào mang tên nó và
      // không ai tắt riêng được. Migration đã cấp `quy_trinh_kinh_doanh` cho mọi vai đang đọc
      // được một trong bốn khoá cũ ⇒ không ai mất mục menu.
      {
        id: "quy-trinh-kinh-doanh",
        label: "Quy trình kinh doanh",
        icon: "workflow",
        module: "quy_trinh_kinh_doanh",
      },
      { id: "tinh-gia", label: "Tính giá", icon: "calculator", module: "tinh_gia_thanh" },
      { id: "bao-gia", label: "Báo giá in ấn", icon: "fileText", module: "bao_gia" },
      { id: "don-hang-ban", label: "Đơn hàng bán", icon: "cart", module: "don_hang_ban" },
      // Giao hàng là khúc SAU của đơn hàng bán nên nằm ngay dưới nó, không dựng nhóm mới.
      // Gác bằng MỘT ô `giao_hang` — không có cửa phụ nào khác (bài học ô ma `self_service`).
      { id: "giao-hang", label: "Giao hàng", icon: "truck", module: "giao_hang" },
      { id: "khach-hang", label: "Khách hàng", icon: "users", module: "khach_hang" },
    ],
  },
  {
    // Bàn của bộ phận Kế hoạch sản xuất: nhận đơn Sale đã chuyển xuống → bung lệnh sản xuất.
    id: "san-xuat",
    label: "Sản xuất",
    items: [
      // MỘT MÀN = MỘT Ô QUYỀN (17/08/2026). Trước đó 6 mục dưới đây treo trên đúng hai khoá
      // (`san_xuat` mở 4 màn, `ky_thuat_may` mở 2), nên không có cách nào cho ai đó xem lệnh mà
      // không dời được lịch cả xưởng. Migration 0209 đã sao chép quyền cũ sang 4 khoá mới.
      { id: "ke-hoach-sx", label: "Kế hoạch sản xuất", icon: "workflow", module: "san_xuat" },
      // Bàn TRA (điều độ · QC · sale), khác hẳn Kế hoạch SX là bàn LẬP: chỉ lệnh ĐÃ PHÁT HÀNH, và
      // không một nút ghi nào. Nhãn "Hồ sơ lệnh sản xuất" chứ không "Lệnh sản xuất" — màn Kế hoạch
      // SX đã có sẵn một TAB mang đúng chữ đó. ĐỊNH DANH giữ nguyên: nav id `lenh-san-xuat`,
      // khoá quyền `lenh_san_xuat`, prefix API `/api/lenh-san-xuat`.
      { id: "lenh-san-xuat", label: "Hồ sơ lệnh sản xuất", icon: "clipboard", module: "lenh_san_xuat" },
      // Bàn TRA thứ hai, đứng NGAY SAU "Hồ sơ lệnh sản xuất" vì cùng nhóm người dùng (điều độ · QC ·
      // sale) và cùng module `lenh_sx` — khác câu hỏi: màn kia tra MỘT lệnh theo mã, màn này quét
      // TOÀN XƯỞNG để thấy việc nào tắc / máy nào trống (Task 17, module riêng `theo_doi_san_xuat`,
      // ô quyền đã seed từ Task 1). Icon "eye" — chưa xưởng nào dùng, khớp nghĩa "theo dõi/quan sát".
      { id: "theo-doi-san-xuat", label: "Theo dõi sản xuất", icon: "eye", module: "theo_doi_san_xuat" },
      // Đứng ngay sau Kế hoạch SX vì nó là bước kế tiếp của cùng một người: lệnh chốt xong thì hỏi
      // "còn thiếu vật tư gì, hôm nào phải đặt".
      { id: "ke-hoach-vat-tu", label: "Kế hoạch vật tư", icon: "box", module: "ke_hoach_vat_tu" },
      // Màn bài ghép cũ gỡ 18/08/2026. Id đường dẫn giữ `bai-ghep-2` (đổi id là hỏng dấu trang
      // người dùng đã lưu + bản đồ badge), NHÃN là "Bài ghép" — người dùng chỉ còn một màn.
      // TẠM ẨN 10/09/2026 theo cờ `BAI_GHEP_ENABLED` — spread rỗng chứ KHÔNG xoá dòng, để bật lại
      // là đổi đúng một chữ ở `constants/features.ts`. Ẩn mục menu cũng khoá luôn route: bảng
      // `MODULES_BY_NAV_ID` dựng từ chính `NAV` này, mất mục thì AppShell coi `bai-ghep-2` là màn
      // không có quyền.
      ...(BAI_GHEP_ENABLED
        ? [{ id: "bai-ghep-2", label: "Bài ghép", icon: "layers", module: "bai_ghep_2" } as NavItem]
        : []),
      // Xếp lịch — bàn cấp LỆNH SẢN XUẤT, màn xếp lịch DUY NHẤT của hệ. Bàn theo công đoạn
      // (`xep-lich-cong-doan-2` / `xep_lich_2`, ẩn từ 10/09/2026) xoá hẳn 18/09/2026; khoá quyền
      // bỏ đánh số về `xep_lich`, mg `0314` chép quyền của `xep_lich_3` sang nên không ai mất
      // đường vào. Dấu trang cũ `/xep-lich-3` và `/xep-lich-cong-doan-2` không còn dùng được.
      { id: "xep-lich", label: "Xếp lịch", icon: "calendar", module: "xep_lich" },
    ],
  },
  // KHỐI RIÊNG 24/09/2026 (chủ chốt: *"tách ra làm phân hệ sản xuất riêng đi"*). Mục ở đây KHÔNG
  // khai tĩnh: cây tổ + mục KCS do AppShell tiêm động qua `dynamicItems["to-san-xuat"]` theo đúng
  // những tổ mà người dùng có Xem. Không ai thấy tổ nào ⇒ khối rỗng ⇒ Sidebar tự ẩn cả khối.
  // Ma trận có nhóm cùng tên ("Tổ sản xuất", dựng runtime từ các dòng `to_sx_<id>`), nay hai bên
  // là một khối đúng nghĩa chứ không còn nấp chung trong "Sản xuất".
  {
    id: "to-san-xuat",
    label: "Tổ sản xuất",
    items: [],
  },
  // KHỐI RIÊNG 24/09/2026 (chủ chốt: *"module sửa chữa máy với phiếu bảo trì thì tách ra làm phân
  // hệ sửa chữa & bảo dưỡng"*). Hai màn này là việc của tổ kỹ thuật — hỏng thì sửa, đến hạn thì
  // bảo dưỡng — khác hẳn chuỗi lập lệnh · xếp lịch · chạy hàng của khối Sản xuất.
  {
    id: "sua-chua-bao-duong",
    label: "Sửa chữa & bảo dưỡng",
    items: [
      // MỘT ô quyền cho MỘT mục (24/09/2026, mg `0332`): khung "Yêu cầu báo hỏng" là tab của
      // chính màn này nên `yeu_cau_sua_chua` gỡ hẳn, còn lại ô chi tiết `ky_thuat_may:request`.
      { id: "sua-chua-may", label: "Sửa chữa máy", icon: "settings", module: "ky_thuat_may" },
      { id: "phieu-bao-tri", label: "Phiếu bảo trì", icon: "clock", module: "phieu_bao_tri" },
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
      // BÁO CÁO — MỘT mục, bên trong chia tab Phải trả / Phải thu (chủ chốt 03/09/2026). Bản đầu
      // tách hai mục menu riêng; gộp lại vì hai sổ giống hệt nhau từng cột, tách ra chỉ làm menu
      // kế toán dài thêm mà chẳng ai cần mở riêng lẻ.
      //
      // `module` RIÊNG `bao_cao_cong_no` (chủ chốt 04/09/2026: "báo cáo đó là một module riêng
      // mà") — trước ăn ké quyền Xem của hai khoá công nợ (`modules: [cong_no_phai_tra,
      // cong_no_phai_thu]`, hiện khi có quyền ở BẤT KỲ bên nào), nay là một ô quyền độc lập.
      {
        id: "ke-toan-bao-cao",
        label: "Báo cáo",
        icon: "fileText",
        module: "bao_cao_cong_no",
      },
      {
        id: "ke-toan-tai-khoan-ngan-hang",
        label: "Tài khoản ngân hàng",
        icon: "database",
        module: "tk_ngan_hang",
      },
      // Tài sản & CCDC — module RIÊNG (`tai_san`), không ăn ké quyền `ke_toan`: người quản tài
      // sản có thể không phải người làm phiếu chi, và ngược lại.
      {
        id: "tai-san",
        label: "Tài sản & CCDC",
        icon: "database",
        module: "tai_san",
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
      // Báo cáo kho (kế toán): sổ nhập-xuất + khóa kỳ + export MISA. MODULE RIÊNG từ 24/09/2026
      // (mg `0329`) — trước đó gắn khoá `kho` rồi lọc thêm bằng ô chi tiết `kho:close_book`,
      // nên một MÀN không có dòng nào của riêng nó trong ma trận phân quyền.
      { id: "kho-baocao", label: "Báo cáo kho", icon: "fileText", module: "bao_cao_kho" },
    ],
  },
  {
    id: "cau-hinh-dm",
    label: "Cấu hình danh mục",
    items: [
      { id: "loai-san-pham", label: "Loại sản phẩm", icon: "clipboard", module: "dm_loai_san_pham" },
      { id: "may-thiet-bi", label: "Thiết bị & Máy móc", icon: "warehouse", module: "dm_thiet_bi" },
      { id: "cong-doan", label: "Công đoạn", icon: "activity", module: "dm_cong_doan" },
      // Đơn vị & quy đổi: dùng chung cho khoán · kho · mua hàng, nên nằm ở danh mục chứ không
      // chôn trong màn Lương. MỘT mục cho hai bảng (đơn vị · cặp "1 tấn = 1.000 kg") — tách hai
      // mục thì hai cái tên gần trùng nhau, không ai đoán được vào đâu làm gì.
      { id: "don-vi", label: "Đơn vị & quy đổi", icon: "activity", module: "dm_don_vi" },
      { id: "chung-loai-giay", label: "Chủng loại giấy", icon: "fileText", module: "dm_chung_loai_giay" },
      { id: "giay", label: "Giấy", icon: "bag", module: "dm_giay" },
      { id: "vat-tu-in-an", label: "Vật tư khác", icon: "bag", module: "dm_vat_tu" },
      // Thành phẩm: hàng của đơn hàng bán, hệ tự khai khi chốt đơn. Đứng CẠNH Vật tư khác vì
      // chung một bảng và người dùng hay nhầm hai chỗ (docs/prd-thanh-pham.md).
      { id: "thanh-pham", label: "Thành phẩm", icon: "bag", module: "dm_thanh_pham" },
      // Khuôn: kho dụng cụ của xưởng (bế + ép kim + khung lụa) — khách · loại · số kệ ·
      // tình trạng. Bước cần dụng cụ ở Lệnh sản xuất chọn từ đây. Nhan đề đổi 18/09/2026;
      // `module` GIỮ chuỗi `khuon_be` vì nó nằm trong bảng phân quyền của DB thật.
      { id: "khuon-be", label: "Khuôn", icon: "clipboard", module: "khuon_be" },
      // Khai báo kho: màn CRUD tạo/sửa kho. Kho tạo ở đây tự hiện thành mục dưới SECTION "Kho hàng".
      { id: "khai-bao-kho", label: "Khai báo kho", icon: "warehouse", module: "dm_kho_hang" },
      // Tiêu chí KCS (module KCS kiêm nhiệm, mg 0250): checklist chuẩn hoá + công đoạn nào áp
      // dụng — dùng để chụp (snapshot) checklist khi phát hành lệnh (Task 3).
      { id: "kcs-tieu-chi", label: "Tiêu chí KCS", icon: "fileCheck", module: "dm_kcs_tieu_chi" },
      // Xe giao hàng (12/09/2026): biển số · tải trọng · xe này ăn MỨC khoán km nào. Bảng giá
      // của từng mức khai ở Cấu hình lương — sửa giá là việc kế toán, không phải việc của
      // người khai biển số. Icon `truck` trùng màn Giao hàng là CỐ Ý: hai mục cùng một nghề.
      { id: "xe", label: "Xe giao hàng", icon: "truck", module: "dm_xe" },
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
      // Menu theo ĐÚNG ô của chính nó. Vai Công nhân được cấp `cham_cong` ở phạm vi "Của tôi"
      // ⇒ vẫn vào bấm giờ được; ai không được cấp thì không thấy menu (chủ chốt 15/08/2026).
      { id: "cham-cong", label: "Chấm công", icon: "activity", module: "cham_cong" },
      { id: "nghi-phep", label: "Nghỉ phép", icon: "calendar", module: "nghi_phep" },
      { id: "tang-ca", label: "Tăng ca", icon: "clock", module: "tang_ca" },
      // Lương vào bằng Ô THẬT của chính nó. Trước 15/08/2026 còn mở qua `self_service` —
      // ô cấp sẵn cho mọi vai và ĐÃ GỠ khỏi bảng phân quyền, tức một cái cổng không tay nắm:
      // HCNS tắt ô Lương mà người ta vẫn vào được màn. Migration 0198 + `_luong_self()` bên
      // seed đã rót ô `luong` (Của tôi: Xem + Thao tác) cho mọi vai nên gỡ cổng ma không ai mất màn.
      { id: "luong", label: "Lương", icon: "calculator", module: "luong" },
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
      // ngay trong Hồ sơ nhân sự (tab "Tài khoản & Quyền"). Khoá `nguoi_dung` cũng GỠ HẲN
      // 24/09/2026 (mg `0331`) — bốn thao tác tài khoản thành ô chi tiết của `nhan_su`.
      // "Phòng ban" dời sang Nhân sự & Lương.
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
  /** Đóng ngăn kéo — CHỈ dùng ở màn hẹp (≤1024px), nút ✕ ẩn hoàn toàn ở màn rộng. */
  onClose?: () => void;
}

/** Nhánh cây ĐỘNG đang GẬP — nhớ qua lần vào, nếu không thì mỗi lần F5 lại bung cả 11 tổ và
 *  việc gập thành vô nghĩa. Chế độ riêng tư chặn localStorage ⇒ bọc try, mất nhớ chứ không vỡ màn. */
const GAP_KEY = "sidebar.gapNhanh";

/** Cắt những item bị nhánh GẬP che: leo chuỗi cha, gặp một nút đang gập là ẩn. Cha bị bộ lọc
 *  quyền loại mất thì chuỗi đứt ngay đó (coi như gốc) — không ẩn oan tổ mà người này xem được. */
function locGap(items: NavItem[], gap: ReadonlySet<string>): NavItem[] {
  if (!gap.size) return items;
  const cha = new Map(items.map((i) => [i.id, i.parentId]));
  return items.filter((i) => {
    for (let p = i.parentId; p && cha.has(p); p = cha.get(p)) {
      if (gap.has(p)) return false;
    }
    return true;
  });
}

function docGap(): Set<string> {
  try {
    const raw = localStorage.getItem(GAP_KEY);
    const xs = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(xs) ? xs.filter((x) => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

export function Sidebar({ activeId, onSelect, readable, itemChildren, dynamicItems, badges, hiddenIds, onClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [gap, setGap] = useState<Set<string>>(docGap);

  useEffect(() => {
    try { localStorage.setItem(GAP_KEY, JSON.stringify([...gap])); } catch { /* riêng tư/đầy */ }
  }, [gap]);

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
    const duoc = merged
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
        });
    // Nút cha phải tính TRƯỚC khi cắt nhánh gập — cắt xong thì cha không còn con nào để nhận ra
    // mình là cha, nút ▾ biến mất và nhánh gập rồi không mở lại được.
    const coCon = new Set(duoc.map((i) => i.parentId).filter((x): x is string => !!x));
    return { ...s, coCon, items: locGap(duoc, gap) };
  }).filter((s) => s.items.length > 0);

  // Auto-mở item cha khi một menu con của nó đang active (mở lại trang / deep-link).
  useEffect(() => {
    const host = sections
      .flatMap((s) => s.items)
      .find((i) => i.children?.some((c) => c.id === activeId));
    if (host) setExpanded((prev) => (prev.has(host.id) ? prev : new Set(prev).add(host.id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, itemChildren]);

  // Đi thẳng tới một tổ nằm trong nhánh đang GẬP (bấm toast "có việc mới", mở lại link cũ) → bung
  // chuỗi cha ra cho thấy hàng đang đứng. Chỉ bám `activeId`: tự tay gập trong lúc đang đứng ở một
  // nút con thì nhánh KHÔNG bung lại — đó là ý người dùng.
  useEffect(() => {
    const cha = new Map(
      Object.values(dynamicItems ?? {}).flat().map((i) => [i.id, i.parentId]),
    );
    const chuoi: string[] = [];
    for (let p = cha.get(activeId); p; p = cha.get(p)) chuoi.push(p);
    if (!chuoi.length) return;
    setGap((prev) => {
      if (!chuoi.some((x) => prev.has(x))) return prev;
      const next = new Set(prev);
      for (const x of chuoi) next.delete(x);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, dynamicItems]);

  return (
    <aside className="sidebar">
      {/* ✕ chỉ hiện khi sidebar là NGĂN KÉO (màn hẹp): lúc đó nó phủ lên Topbar nên nút
          hamburger khuất, người dùng cần một đường đóng nhìn thấy được ngoài việc chạm màn che. */}
      <button
        type="button"
        className="sidebar__close"
        onClick={onClose}
        aria-label="Đóng menu điều hướng"
      >
        <Icon name="x" size={18} />
      </button>
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
                      coCon={section.coCon.has(item.id)}
                      dangGap={gap.has(item.id)}
                      onSelect={onSelect}
                      onToggle={() => setExpanded((s) => toggle(s, item.id))}
                      onGap={() => setGap((s) => toggle(s, item.id))}
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
  /** Có item khác nhận mình làm `parentId` → mọc nút ▾ gập nhánh. */
  coCon?: boolean;
  dangGap?: boolean;
  onSelect: (id: string) => void;
  onToggle: () => void;
  onGap?: () => void;
}

function NavRow({ item, activeId, isOpen, badge, coCon, dangGap, onSelect, onToggle, onGap }: NavRowProps) {
  const hasChildren = !!item.children?.length;
  const childActive = item.children?.some((c) => c.id === activeId) ?? false;
  const active = activeId === item.id || (childActive && !isOpen);

  return (
    <li>
      <div className={`sidebar__row${coCon ? " has-twisty" : ""}${active ? " is-active" : ""}`}>
      <button
        type="button"
        className={`sidebar__link${active ? " is-active" : ""}`}
        // Tooltip = nhãn ĐẦY ĐỦ: hàng menu cắt chữ (…) khi rail hẹp, rê chuột vẫn đọc được tên module.
        title={item.label}
        // Thụt tối đa 4 nấc: cây sâu hơn mà thụt tiếp thì rail hẹp không còn chỗ cho tên tổ.
        style={item.indent ? { paddingLeft: `calc(var(--sp-3) + ${Math.min(item.indent, 4) * 14}px)` } : undefined}
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
      {/* Nút gập RIÊNG, không gộp vào hàng: bấm vào tên tổ vẫn phải MỞ BÀN của tổ đó — cha ở cây
          này là một tổ thật có việc, không phải cái nhãn nhóm. */}
      {coCon && (
        <button
          type="button"
          className={`sidebar__twisty${dangGap ? " is-collapsed" : ""}`}
          aria-expanded={!dangGap}
          aria-label={`${dangGap ? "Mở" : "Thu gọn"} các tổ trong ${item.label}`}
          title={dangGap ? "Mở các tổ bên trong" : "Thu gọn các tổ bên trong"}
          onClick={onGap}
        >
          <Icon name="chevron" size={14} />
        </button>
      )}
      </div>

      {hasChildren && isOpen && (
        <ul className="sidebar__sub">
          {item.children!.map((child) => (
            <li key={child.id}>
              <button
                type="button"
                className={`sidebar__sublink${activeId === child.id ? " is-active" : ""}`}
                title={child.label}
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
