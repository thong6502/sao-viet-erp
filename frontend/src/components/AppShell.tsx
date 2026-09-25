// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  connectQuoteEvents,
  type CanDoiKhoaDong,
  type DepartmentPurchaseSourceType,
  type HangLoai,
  type ModuleNotificationChannel,
  type PinnedCustomer,
  type SxTeam,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { BAI_GHEP_ENABLED } from "../constants/features";
import { useAuth } from "../auth/useAuth";
import {
  buildCapabilities,
  PermissionsProvider,
  type Capabilities,
} from "../auth/permissions";
import { ActivityLogPage } from "../pages/ActivityLogPage";
import { BaoGiaPage } from "../pages/BaoGiaPage";
import { DonHangBanPage } from "../pages/DonHangBanPage";
import { BaoCaoKinhDoanhPage } from "../pages/bao-cao-kinh-doanh/BaoCaoKinhDoanhPage";
import GiaoHangPage from "../pages/giao-hang/giao-hang";
import { KeHoachSXPage } from "../pages/KeHoachSXPage";
import { LenhSanXuatPage } from "../pages/LenhSanXuatPage";
import { TheoDoiSanXuatPage } from "../pages/TheoDoiSanXuatPage";
import { KeHoachVatTuPage } from "../pages/KeHoachVatTuPage";
import { BaiGhep2Page } from "../pages/BaiGhep2Page";
import { XepLichPage } from "../pages/XepLichPage";
import { ThucHienSxPage } from "../pages/ThucHienSxPage";
import { nhanChang, nhanDonVi } from "../pages/lsxBuoc";
import { KcsTheoLenhPage } from "../pages/kcs/KcsTheoLenhPage";
import { SuaChuaMayPage } from "../pages/SuaChuaMayPage";
import { PhieuBaoTriPage } from "../pages/PhieuBaoTriPage";
import { kyThuatMay } from "../api/kyThuatMay";
import { TinhGiaPage } from "../pages/TinhGiaPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/nhan-su-luong/phong-ban";
import { KhachHangPage } from "../pages/KhachHangPage";
import { QuyTrinhKinhDoanhPage } from "../pages/QuyTrinhKinhDoanhPage";
import { ChamCongPage } from "../pages/nhan-su-luong/cham-cong";
import { NghiPhepPage } from "../pages/nhan-su-luong/nghi-phep";
import { TangCaPage } from "../pages/nhan-su-luong/tang-ca";
import { LuongPage } from "../pages/nhan-su-luong/luong";
import { HoSoCuaToiPage } from "../pages/nhan-su-luong/ho-so-cua-toi";
import { NoiQuyPage } from "../pages/nhan-su-luong/noi-quy";
import { NhanSuPage } from "../pages/nhan-su-luong/nhan-su";
import { KcsKhaiBaoPage } from "../pages/danh-muc/KcsKhaiBaoPage";
import { RebuildCatalogPage } from "../pages/RebuildCatalogPage";
import { KhoTonKhoPage } from "../pages/KhoTonKhoPage";
import { KhoPage } from "../pages/KhoPage";
import { KhoBaoCaoPage } from "../pages/KhoBaoCaoPage";
import type { KhoNhapSeed } from "../pages/KhoDeNghiPage";

// Danh mục rebuild (config .tsx — render pill JSX)
import { REBUILD_CONFIGS } from "../pages/rebuildCatalogConfigs";
import { DepartmentPurchaseRequestsPage } from "../pages/mua-hang/yeu-cau-mua-hang";
import { PurchaseRequestsPage } from "../pages/mua-hang/phieu-mua-hang";
import { SuppliersPage } from "../pages/mua-hang/nha-cung-cap";
import { AccountingPayablesPage } from "../pages/ke-toan/cong-no-phai-tra";
import { AccountingReceivablesPage } from "../pages/ke-toan/cong-no-phai-thu";
import { BaoCaoKeToanPage } from "../pages/ke-toan/bao-cao";
import { AccountingPurchaseInboxPage } from "../pages/ke-toan/don-mua-hang";
import { PaymentVouchersPage } from "../pages/ke-toan/phieu-chi";
import { PaymentReceiptsPage } from "../pages/ke-toan/phieu-thu";
import { AccountingBankAccountsPage } from "../pages/ke-toan/tk-ngan-hang";
import { TaiSanPage } from "../pages/tai-san";
import {
  AUTHENTICATED_NAV_IDS,
  MODULES_BY_NAV_ID,
  Sidebar,
  type NavItem,
} from "./Sidebar";
import { Topbar } from "./Topbar";
import { coQuyenBanTo, khoaBanTo } from "./appShellRealtime";
import { docDeepLinkLsx } from "./appShellDeepLink";

/** A cross-module navigation intent: which screen to open + optional payload so the
 *  target screen can pre-pin a customer or drill straight to a document. */
export interface NavParams {
  /** Pre-pin this customer on the target create flow (CRM → Báo giá / Đơn hàng). */
  customer?: PinnedCustomer;
  /** Open this quotation's detail on the Báo giá screen. */
  openQuoteId?: number;
  /** Open this order's detail on the Đơn hàng bán screen. */
  openOrderId?: number;
  /** Liên thông: mở Chấm công / Nghỉ phép / Lương lọc theo đúng nhân viên này. */
  focusEmployeeId?: number;
  /** Liên thông từ Hồ sơ NV, nút "Đặt ca nền" (bản rà E6, 07/09/2026): mở Chấm công ở tab
   *  Khai ca, lưới Phân ca tháng lọc sẵn + mở form ca nền cho đúng `focusEmployeeId`. Không có
   *  nó thì `focusEmployeeId` mở tab Nhật ký như cũ. */
  chamCongTab?: "khai-ca";
  /** Liên thông: mở màn Yêu cầu mua hàng (YCMH) lọc + tô sáng đúng mã phiếu này. */
  focusRequestCode?: string;
  /** Liên thông từ 3 đèn ở Kế hoạch SX: mở Kế hoạch vật tư / Xếp lịch với ô tìm điền sẵn mã lệnh.
   *  Không có nó thì bấm chấm chỉ tới được MÀN, còn phải tự dò lệnh trong danh sách — vẫn là đổi
   *  màn, chỉ đỡ được nửa việc. */
  focusLsxMa?: string;
  /** Liên thông: mở màn Phiếu chi / UNC với ô tìm kiếm điền sẵn (mã PC/PMH...). */
  focusVoucherQuery?: string;
  /** Liên thông: mở màn Phiếu thu với ô tìm kiếm điền sẵn (mã PC/PT...). */
  focusReceiptQuery?: string;
  /** P3 (redesign-bao-gia §6): mở thẳng 1 Phiếu tính giá (link "↳ PTG" từ Báo giá). */
  focusPhieuId?: number;
  /** Liên thông Kho → YCMH: mở form Yêu cầu mua hàng điền sẵn dòng vật tư (Tên + ĐVT). */
  purchaseSeedLines?: {
    hang_loai?: HangLoai | null;
    hang_id?: number | null;
    item_name: string;
    unit: string;
    quantity: number;
    note?: string | null;
  }[];
  purchaseSeedPurpose?: string;
  /** Liên thông Kế hoạch vật tư → YCMH: điền sẵn cả ĐẦU PHIẾU (nguồn + vết lệnh sản xuất), không
   *  chỉ mấy dòng vật tư. `needed_date` để trống — người lập tự gõ ngày cần hàng (18/09/2026). */
  purchaseSeedHeader?: {
    source_type?: DepartmentPurchaseSourceType | null;
    needed_date?: string | null;
    related_document_type?: string | null;
    related_document_code?: string | null;
  };
  /** Liên thông Kế hoạch vật tư → YCMH: yêu cầu này mua cho lệnh/bài nào (khoá các dòng đã tick).
   *  Gửi kèm lúc Lưu để ngày cần hàng vừa gõ quay về đúng các lệnh đó trên Kế hoạch vật tư. */
  purchaseSeedNguon?: CanDoiKhoaDong[];
  /** Liên thông Đơn hàng → bàn Kế hoạch SX: mở thẳng đơn này ở hàng chờ / danh sách lệnh. */
  openSxOrderId?: number;
  /** Liên thông sơ đồ Bài ghép → Kế hoạch SX: mở thẳng chi tiết một lệnh. */
  openLsxId?: number;
  /** Liên thông Phòng ban → Lương: mở thẳng tab "Cấu hình lương" (bảng lương của tổ). */
  luongTab?: "cauhinh";
  /** Deep-link QR tem kho: mở thẳng drawer lô + vị trí của đúng vật tư này trên màn Tồn kho. */
  /** Deep-link tem QR: khoá mặt hàng gốc dạng `"giay:12"`. */
  openMatHangKey?: string;
  /** Liên thông Đơn mua → Kho: bấm "Nhập kho" ở một đợt giao → mở form Yêu cầu NHẬP điền sẵn. */
  khoNhapSeed?: KhoNhapSeed;
  /** Bấm 1 thông báo kho → mở đúng yêu cầu: `view` chọn tab (Yêu cầu/Hộp), `id` = request_id. */
  khoOpenRequest?: { id: number; view: "denghi" | "yeucau" };
  /** Deep link QR phiếu công nghệ (Task 14): tổ trưởng quét mã dán ở máy → mở thẳng hồ sơ MỘT
   *  lệnh trên màn "Hồ sơ lệnh sản xuất". Nguồn: hash `#lsx=<id>&pv=<phien_ban_in>` đọc lúc
   *  AppShell mount (`appShellDeepLink.ts`), KHÔNG phải một mục Sidebar bấm tay. */
  openHoSoLsxId?: number;
  /** Đi kèm `openHoSoLsxId`: phiên bản phát hành đang IN TRÊN TỜ GIẤY đã quét. Hồ sơ so số này với
   *  `phien_ban` hiện tại của lệnh để báo "phiếu giấy này là bản cũ" khi lệch — xem
   *  `LenhSxHoSoView`. `null` = QR không mang `pv` (không có gì để so, không bày băng). */
  openHoSoPv?: number | null;
  /** Số thứ tự tăng dần MỖI LƯỢT gọi `navigate(...)` (xem `navigate` bên dưới) — bất kể tới màn
   *  nào, bất kể tham số gì. KHÔNG phải "cái gì trong params đã đổi" mà là "đây có phải MỘT LƯỢT
   *  ĐIỀU HƯỚNG MỚI hay không", kể cả khi mọi giá trị nguyên thuỷ khác giống hệt lượt trước (Task
   *  14, lỗi N1 vòng rà lại: quét LẠI đúng tờ giấy vừa đóng thì `openHoSoLsxId`/`openHoSoPv` ra
   *  cùng một cặp số như lần trước, effect của màn đích không có gì để phân biệt hai lượt).
   *  Hạ tầng CHUNG (tăng cho MỌI lượt `navigate`, không riêng gì deep link), nhưng vòng sửa 2 này
   *  CHỈ nối dây cho `LenhSanXuatPage` — 19 nhánh còn lại của `renderContent()` chưa đọc trường
   *  này, hành vi của chúng không đổi. Màn nào sau này cần "điều hướng lại tới cùng chỗ với cùng
   *  tham số vẫn phải coi là một việc mới" thì đưa trường này vào deps effect của chính nó. */
  navSeq?: number;
}

export type NavigateFn = (id: string, params?: NavParams) => void;

const MODULE_NOTIFICATION_NAV: Record<ModuleNotificationChannel, string> = {
  thu_mua: "mua-hang",
  ke_toan: "ke-toan-don-mua-hang",
};

/** Khoá giả cho mục menu "KCS" — người thuộc phòng ban "Tổ KCS" (mg 0306), không phải ô quyền. */
const KCS_NAV_KEY = "kcs_theo_lenh";

export function AppShell() {
  const { token, user } = useAuth();
  const [activeId, setActiveId] = useState("dashboard");
  const [navParams, setNavParams] = useState<NavParams | null>(null);
  // Ngăn kéo điều hướng ở màn hẹp (≤1024px). Màn rộng: sidebar cố định, cờ này vô hại.
  const [navOpen, setNavOpen] = useState(false);
  const [readable, setReadable] = useState<Set<string> | null>(null);
  const [caps, setCaps] = useState<Capabilities>(new Map());
  // KCS theo lệnh (mg 0306): tư cách thành viên / trưởng phòng ban "Tổ KCS" — KHÔNG phải ô quyền
  // của vai. Máy chủ trả kèm bộ quyền; mở mục menu "KCS" và nút "Đóng thiếu nhóm".
  const [kcsTuCach, setKcsTuCach] = useState<{ kcs: boolean; truongKcs: boolean }>({ kcs: false, truongKcs: false });
  // Badge số theo nav id (vd "nghi-phep": số đơn chờ duyệt) — chỉ người có quyền duyệt.
  const [badges, setBadges] = useState<Record<string, number>>({});
  // Đã toast "bảo trì tới hạn" trong phiên này chưa — badge refetch nhiều lần, không có cờ này thì
  // mỗi lần refetch lại đẩy thêm một toast y hệt.
  const daToastBaoTri = useRef(false);
  // Đang có một lượt `can-doi` chạy dở hay chưa. Endpoint này duyệt MỌI lệnh + bài ghép rồi chạy
  // engine quy đổi cho từng dòng (đo 18/08/2026 ở 100k lệnh: 23,8 s · 3,75 MB). Uvicorn chạy MỘT
  // tiến trình nên hai lượt chồng nhau không chạy nhanh gấp đôi — chúng giành GIL và làm cả API
  // đứng hình (RSS phồng 3,1 GB). Có lượt đang chạy thì bỏ qua lượt mới: con số vẫn tới nơi.
  const dangNapVatTu = useRef(false);
  // Kho đã khai báo → đổ menu con ĐỘNG dưới "Kho hàng" (Cấu hình danh mục). Refetch khi
  // khai báo/sửa/xoá kho (onMutate màn khai báo) → navbar cập nhật NGAY, không cần refresh.
  const [khoList, setKhoList] = useState<{ id: number; ma: string; ten: string }[]>([]);
  // Số yêu cầu ĐÃ DUYỆT chờ kho lập phiếu (badge Nhập/Xuất) + phản hồi kho chưa xem của NGƯỜI TẠO
  // (done_unseen=Hoàn tất, fail_unseen=Không thành) — nuôi badge tab Yêu cầu + số đỏ bộ lọc.
  const [khoCounts, setKhoCounts] = useState<{
    nhap: number;
    xuat: number;
    dieu_chuyen: number;
    done_unseen: number;
    fail_unseen: number;
  }>({ nhap: 0, xuat: 0, dieu_chuyen: 0, done_unseen: 0, fail_unseen: 0 });
  // Bàn "Thực hiện sản xuất": tổ đã khai báo → node lá ĐỘNG dưới section "Sản xuất" + badge =
  // số việc chờ. `teams` MỘT cú gọi ra cả list lẫn badge (`so_viec_cho`) — đừng thêm API badge
  // riêng. Refetch khi có sự kiện `san_xuat_cong_viec_changed` (badge nhảy + bàn đang mở tự tươi).
  const [teamList, setTeamList] = useState<SxTeam[]>([]);
  // Real-time luồng gửi duyệt (SSE): toast nổi + mốc 'chờ tôi duyệt' gần nhất để chỉ toast khi TĂNG.
  // `quoteTick` tăng mỗi event → truyền xuống BaoGiaPage cho nó refetch list/stats. Kênh SSE vẫn
  // DUY NHẤT ở đây (trang con mở kênh riêng = tốn kết nối + lệch trạng thái).
  const [quoteTick, setQuoteTick] = useState(0);
  // Tín hiệu ĐÍCH DANH cho bàn tổ: SỐ LẦN đề nghị cấp vật tư đổi, ĐẾM THEO TỪNG công việc. Tách
  // khỏi `quoteTick` có chủ đích — sự kiện này broadcast toàn hệ, đẩy vào tick chung là bắt mọi
  // màn đang mở của cả nhà máy gọi lại API mỗi lần một tổ bấm gửi (xem nhánh SSE bên dưới).
  // Đếm theo công việc chứ không phải một `{n, congViecId}` chung: hai sự kiện rơi cùng một nhịp
  // React thì cái sau ghi đè `congViecId` của cái trước, và nếu cái bị đè đúng là việc đang mở thì
  // drawer im luôn. Dạng bản đồ cũng khỏi cần cửa sổ "mấy sự kiện chưa xem" ở phía nhận.
  const [vatTuDeNghiDem, setVatTuDeNghiDem] = useState<Record<number, number>>({});
  // Cùng khuôn đếm-theo-id cho tệp đính kèm của lệnh: chỉ màn chi tiết ĐÚNG lệnh đó nạp lại danh
  // sách tệp, các màn khác (và chính danh sách lệnh) không bị kéo gọi API theo.
  const [lsxDinhKemDem, setLsxDinhKemDem] = useState<Record<number, number>>({});
  const [toasts, setToasts] = useState<{ id: number; text: string; tone: "ok" | "warn" | "info" }[]>([]);
  const toastSeq = useRef(0);
  const lastPending = useRef(0);
  const lastOrderAction = useRef(0);
  // Số lần ca của TÔI bị đổi mà chưa đọc — chỉ toast khi số TĂNG (có việc mới), không toast
  // lại mỗi lần refetch.
  const lastShiftChange = useRef(0);
  const lastAdvancePending = useRef(0);
  const lastKhoPending = useRef(0);
  const lastOtPending = useRef(0);
  // Số việc chờ duyệt nghỉ phép lần trước (đơn mới + xin hủy) — toast CHỈ khi số TĂNG (23/09/2026).
  const lastLeavePending = useRef(0);
  const lastElPending = useRef(0);
  // Một cú bấm Bật/Nhả giữ chỗ đẻ HAI event (`bat()` báo công tắc đổi, `nhat_them()` báo vừa
  // nhặt được dòng mới) — cả hai đều cần cho máy khác đang mở màn, nhưng người bấm thì thấy
  // hai toast giống hệt nhau. Gộp trong 2 giây.
  const lastKhvtToast = useRef(0);
  // CÙNG khuôn throttle với `lastKhvtToast` (mốc thời gian + cửa 2 giây), nhưng mốc RIÊNG: dùng
  // chung một mốc cho hai loại toast khác nhau là chúng nuốt lẫn của nhau.
  const lastVatTuToast = useRef(0);
  // Công việc mà bàn "Thực hiện sản xuất" đang mở drawer. Không bắn toast cho chính việc đó:
  // drawer đã tự nạp lại (đếm bên dưới), còn người vừa bấm thì đã ăn toast của `mutate` rồi.
  const cvDangMo = useRef<number | null>(null);
  const datCvDangMo = useCallback((id: number | null) => { cvDangMo.current = id; }, []);
  const activeIdRef = useRef(activeId);
  const moduleNotificationRevision = useRef<Record<ModuleNotificationChannel, number>>({
    thu_mua: 0,
    ke_toan: 0,
  });
  // Tăng mỗi lượt `navigate(...)` — xem `navSeq` trong `NavParams` và `navigate` bên dưới.
  const navSeqRef = useRef(0);
  // Giữ tham số `ms` (thông báo kho hiện lâu 9s) — luồng thông báo-theo-phòng dùng.
  const pushToast = useCallback(
    (text: string, tone: "ok" | "warn" | "info", ms = 6000) => {
      const id = ++toastSeq.current;
      setToasts((prev) => [...prev, { id, text, tone }]);
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), ms);
    },
    [],
  );

  // Single navigation entrypoint: switches the active screen AND carries an optional
  // payload (pinned customer / document to open). A fresh params OBJECT each call does
  // NOT by itself make the target screen's effect re-fire — every current consumer
  // destructures primitive fields out of it (`navParams?.xxx`), and React's dependency
  // check compares those primitives by value, not the wrapping object by identity. Two
  // calls carrying the same primitive values (e.g. re-navigating to the same doc) look
  // identical to such an effect. `navSeq` below exists to break that tie when a screen
  // needs "navigated again" to count as a change even with unchanged params (Task 14,
  // lỗi N1: quét lại đúng QR vừa đóng thì không mở lại gì).
  const navigate = useCallback<NavigateFn>((id, params) => {
    setActiveId(id);
    setNavParams({ ...(params ?? {}), navSeq: ++navSeqRef.current });
    // Chọn xong một mục thì đóng ngăn kéo — không thì ở điện thoại nó che hết màn vừa mở.
    setNavOpen(false);
  }, []);

  // Deep link QR phiếu công nghệ (Task 14, ruling C105/C108): đọc `#lsx=&pv=` lúc AppShell mount
  // rồi tự nhảy thẳng vào đúng hồ sơ — tổ trưởng quét mã xong không phải tự dò lệnh trong bảng.
  // Chỗ đọc CHỈ ở đây vì AppShell chỉ mount khi ĐÃ có phiên (App.tsx); hash SỐNG SÓT qua lượt đăng
  // nhập vì `LoginPage` không đụng `window.location` (bài canh: `LoginPage.test.tsx`).
  // KHÔNG tự kiểm quyền lần hai ở đây — lệnh ngoài phạm vi thì `ho_so.ho_so()` phía backend đã
  // chặn (404/403), `LenhSxHoSoView` chỉ việc hiện lỗi đó tử tế (ruling C108).
  //
  // Sửa vòng 1 (P2): KHÔNG được chỉ đọc MỘT LẦN lúc mount. Tổ trưởng đã mở sẵn hệ thống trong tab
  // đó (AppShell đã mount, hash lần trước đã bị `replaceState` xoá) rồi quét mã THỨ HAI — trình
  // duyệt chỉ đổi phần fragment của URL, đó là same-document navigation nên KHÔNG reload, KHÔNG
  // remount, effect mount-một-lần không chạy lại ⇒ im lặng không làm gì. Sự đổi hash đó tự nó vẫn
  // bắn sự kiện `hashchange` dù không load lại trang, nên nghe thêm sự kiện đó, DÙNG CHUNG một hàm
  // xử lý với lượt mount (không chép hai bản logic).
  useEffect(() => {
    const doDeepLink = () => {
      const dl = docDeepLinkLsx(window.location.hash);
      if (!dl) return;
      navigate("lenh-san-xuat", { openHoSoLsxId: dl.lsxId, openHoSoPv: dl.pv });
      // Xoá hash NGAY sau khi dùng: nó chỉ có nghĩa lúc VÀO CỬA. Để nguyên thì F5 giữa lúc điều độ
      // đang xem một lệnh KHÁC lại kéo họ về đúng lệnh cũ trên QR — URL không còn đại diện cho màn
      // đang mở (`AppShell` không đồng bộ URL với `activeId`/`navParams`, xem đầu file).
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    };
    doDeepLink();
    window.addEventListener("hashchange", doDeepLink);
    return () => window.removeEventListener("hashchange", doDeepLink);
  }, [navigate]);

  // Esc đóng ngăn kéo (bàn phím + máy đọc màn hình đều cần đường thoát ngoài nút hamburger).
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  // Số thứ tự lượt hỏi quyền: lượt cũ về muộn (hoặc về sau khi đổi phiên) thì bỏ, đừng đè lượt mới.
  const luotHoiQuyen = useRef(0);
  // Bộ quyền đang áp (dạng chuỗi) để nhận ra lượt hỏi lại trả về y hệt.
  const quyenDangAp = useRef<string | null>(null);
  const reloadAccess = useCallback((baoNeuDoi = false) => {
    const luot = ++luotHoiQuyen.current;
    if (!token) return;
    api
      .myAccess(token)
      .then((acc) => {
        if (luot !== luotHoiQuyen.current) return;
        // Y hệt bộ đang áp ⇒ giữ nguyên `readable`/`caps`: đổi tham chiếu là kênh SSE (phụ thuộc
        // hai giá trị này) đóng rồi nối lại vô cớ, sự kiện bắn trúng khe đó bị rơi.
        const dauVet = JSON.stringify(acc);
        if (dauVet === quyenDangAp.current) return;
        const lanDau = quyenDangAp.current === null;
        quyenDangAp.current = dauVet;
        // Các API "của tôi" tự giới hạn theo hồ sơ đăng nhập, không cần cấp
        // `luong:read` (quyền quản trị). Module ảo này chỉ mở cửa menu tự phục vụ.
        // `self_service` KHÔNG còn được nhét thêm ở đây (10/08/2026): nó là ô quyền thật, do
        // máy chủ trả về như mọi module khác. Nhét tay = giao diện tưởng ai cũng có, bấm vào
        // thì API trả 403 — hai nơi nói hai kiểu.
        setReadable(new Set(acc.modules));
        setCaps(buildCapabilities(acc.permissions));
        setKcsTuCach({ kcs: !!acc.kcs, truongKcs: !!acc.truong_kcs });
        if (baoNeuDoi && !lanDau) pushToast("Quyền của bạn vừa được cập nhật.", "info");
      })
      .catch(() => {
        if (luot !== luotHoiQuyen.current) return;
        // Lượt ĐẦU hỏng ⇒ chưa có gì để giữ, coi như không quyền. Lượt tải lại (sau khi lưu vai
        // trò) hỏng ⇒ giữ bộ quyền đang có; xoá sạch thì menu biến mất chỉ vì một cú mạng chập.
        setReadable((cur) => cur ?? new Set());
      });
  }, [token, pushToast]);
  useEffect(() => {
    reloadAccess();
    return () => {
      luotHoiQuyen.current++;
      quyenDangAp.current = null;
    };
  }, [reloadAccess]);
  // Màn tự gọi tải lại (vừa lưu vai trò của chính mình) đã có toast "Đã lưu" riêng — không báo thêm.
  const taiLaiQuyenTuMan = useCallback(() => reloadAccess(false), [reloadAccess]);

  const reloadModuleNotificationBadges = useCallback(() => {
    if (!token || readable === null) return;
    const revision = { ...moduleNotificationRevision.current };
    api.moduleNotifications
      .summary(token)
      .then((summary) => {
        const activeNav = activeIdRef.current.split(":")[0];
        setBadges((prev) => {
          const next = { ...prev };
          if (revision.thu_mua === moduleNotificationRevision.current.thu_mua) {
            next[MODULE_NOTIFICATION_NAV.thu_mua] =
              readable.has("thu_mua") && activeNav !== MODULE_NOTIFICATION_NAV.thu_mua
                ? summary.thu_mua
                : 0;
          }
          if (revision.ke_toan === moduleNotificationRevision.current.ke_toan) {
            next[MODULE_NOTIFICATION_NAV.ke_toan] =
              readable.has("ke_toan") && activeNav !== MODULE_NOTIFICATION_NAV.ke_toan
                ? summary.ke_toan
                : 0;
          }
          return next;
        });
      })
      .catch(() => {});
  }, [token, readable]);

  const markModuleNotificationsRead = useCallback(
    (channel: ModuleNotificationChannel) => {
      if (!token) return;
      const navId = MODULE_NOTIFICATION_NAV[channel];
      const revision = ++moduleNotificationRevision.current[channel];
      setBadges((prev) => ({ ...prev, [navId]: 0 }));
      api.moduleNotifications.markRead(token, channel).catch(() => {
        api.moduleNotifications
          .summary(token)
          .then((summary) => {
            if (moduleNotificationRevision.current[channel] !== revision) return;
            setBadges((prev) => ({ ...prev, [navId]: summary[channel] }));
          })
          .catch(() => {});
      });
    },
    [token],
  );
  const markThuMuaNotificationsRead = useCallback(
    () => markModuleNotificationsRead("thu_mua"),
    [markModuleNotificationsRead],
  );
  const markKeToanNotificationsRead = useCallback(
    () => markModuleNotificationsRead("ke_toan"),
    [markModuleNotificationsRead],
  );

  // Badge Nghỉ phép: số đơn chờ duyệt (endpoint tự trả null nếu người gọi không có quyền
  // duyệt → không hiện badge). NghiPhepPage gọi lại sau mỗi thao tác để badge cập nhật ngay.
  const reloadBadges = useCallback(() => {
    if (!token || readable === null) return;
    reloadModuleNotificationBadges();
    if (readable.has("nghi_phep")) {
      api.leaves
        .summary(token)
        .then((s) => {
          setBadges((prev) => ({
            ...prev,
            "nghi-phep": s.pending_in_scope && s.pending_in_scope > 0 ? s.pending_in_scope : 0,
          }));
          lastLeavePending.current = s.pending_in_scope ?? 0;
        })
        .catch(() => {});
    }
    // Badge Tăng ca: số phiếu chờ duyệt trong scope (endpoint trả null nếu không có quyền duyệt).
    if (readable.has("tang_ca")) {
      api.overtime
        .summary(token)
        .then((s) => {
          setBadges((prev) => ({
            ...prev,
            "tang-ca": s.pending_in_scope && s.pending_in_scope > 0 ? s.pending_in_scope : 0,
          }));
          lastOtPending.current = s.pending_in_scope ?? 0;
        })
        .catch(() => {});
    }
    // Badge Chấm công: số phiếu ĐI MUỘN / VỀ SỚM chờ duyệt trong scope (null nếu không duyệt được).
    // Treo ở nav `cham-cong` vì tab phiếu nằm trong màn Chấm công, KHÔNG phải màn Tăng ca.
    // Gác bằng chính màn chứa badge (`cham_cong`), KHÔNG phải khoá cũ `di_muon` — khoá đó đã gộp
    // về `cham_cong.approve_late_early` (mg 0212) và đang bị gỡ khỏi ma trận quyền. Ai được xem
    // Chấm công thì hỏi; MÁY CHỦ mới là nơi quyết định có số hay không (trả null nếu không duyệt
    // được), nên mở rộng cửa ở đây không lộ gì.
    if (readable.has("cham_cong")) {
      api.lateEarly
        .summary(token)
        .then((s) => {
          const n = s.pending_in_scope && s.pending_in_scope > 0 ? s.pending_in_scope : 0;
          setBadges((prev) => ({ ...prev, "cham-cong": n }));
          lastElPending.current = s.pending_in_scope ?? 0;
        })
        .catch(() => {});
    }
    // Badge Khách hàng: số việc chăm sóc ĐẾN HẠN trong scope (khảo sát #28) — kéo sale
    // quay lại panel "Cần chăm sóc" mà không cần notification center.
    if (readable.has("khach_hang")) {
      api.customers
        .careFollowups(token)
        .then((r) => {
          setBadges((prev) => ({ ...prev, "khach-hang": r.items.length }));
        })
        .catch(() => {});
    }
    // Badge Chấm công = số lần ca CỦA TÔI bị đổi mà tôi chưa đọc. KHÔNG gác sau `readable`:
    // công nhân xưởng không có quyền đọc module nhân sự vẫn phải biết ca mình bị đổi.
    api.attendance
      .notifySummary(token)
      .then((s) => {
        lastShiftChange.current = s.unseen_shift_changes;
        setBadges((prev) => ({ ...prev, "cham-cong": s.unseen_shift_changes }));
      })
      .catch(() => {});
    // Badge Báo giá in ấn = 'chờ TÔI duyệt' (người duyệt) + 'quyết định chưa xem' (người soạn).
    // Số real-time: SSE đẩy sự kiện → hàm này refetch; ở đây cũng là snapshot lúc đổi màn/mở app.
    if (readable.has("bao_gia")) {
      api.quotations
        .notifySummary(token)
        .then((s) => {
          lastPending.current = s.pending_approval_count;
          setBadges((prev) => ({
            ...prev,
            "bao-gia": s.pending_approval_count + s.my_decided_unseen,
          }));
        })
        .catch(() => {});
    }
    // Badge Đơn hàng bán = 'việc chờ TÔI' theo vai (TP: chờ duyệt; Kế toán: chờ ghi cọc; Sale:
    // sẵn sàng chốt). Số real-time: SSE đẩy sự kiện → refetch; đây là snapshot lúc đổi màn/mở app.
    if (readable.has("don_hang_ban")) {
      api.orders
        .notifySummary(token)
        .then((s) => {
          lastOrderAction.current = s.action_count;
          setBadges((prev) => ({ ...prev, "don-hang-ban": s.action_count }));
        })
        .catch(() => {});
    }
    // Bốn badge khối Sản xuất — mỗi cái gác bằng KHOÁ CỦA MÀN NÓ (tách 17/08/2026). Trước đây cả
    // bốn nằm chung trong `if (readable.has("san_xuat"))`; để nguyên thì ai chỉ được cấp Bài ghép
    // sẽ không thấy badge của chính màn mình, còn ai chỉ có Kế hoạch SX lại gọi 3 API bị 403
    // (im lặng vì `.catch`, nhưng vẫn là 3 lượt gọi thừa mỗi lần mở app).
    // Badge Kế hoạch SX = số đơn Sale đã chuyển xuống mà CÒN dòng chưa lên lệnh (hàng chờ).
    if (readable.has("san_xuat")) {
      api.lsx
        .hangCho(token)
        .then((r) => setBadges((prev) => ({ ...prev, "ke-hoach-sx": r.total })))
        .catch(() => {});
    }
    // Badge Bài ghép = số LSX sẵn sàng đang chờ ghép (pool). Màn ĐANG ẨN (`BAI_GHEP_ENABLED`) ⇒
    // không gọi API: badge treo ở một mục menu không còn hiện, gọi cũng chỉ tốn một lượt mạng.
    if (BAI_GHEP_ENABLED && readable.has("bai_ghep_2")) {
      api.baiGhep2
        .hangCho(token)
        .then((r) => setBadges((prev) => ({ ...prev, "bai-ghep-2": r.total })))
        .catch(() => {});
    }
    // Badge Xếp lịch = số thẻ CHỜ XẾP (`tong` là sau lọc ở máy chủ, không phải số dòng trả về).
    if (readable.has("xep_lich")) {
      api.xepLich
        .hangCho(token, { moi_trang: 1 })
        .then((r) => setBadges((prev) => ({ ...prev, "xep-lich": r.tong })))
        .catch(() => {});
    }
    // (Badge Kế hoạch vật tư KHÔNG nạp ở đây nữa — xem `reloadBadgeVatTu` ngay dưới.)
    // Badge Sửa chữa máy = số YÊU CẦU báo hỏng chưa ai tiếp nhận (không phải số phiếu đang sửa):
    // phiếu đang sửa là việc tổ đã cầm, còn lời báo chưa tiếp nhận mới là thứ đang nằm chờ người.
    // Gác theo `ky_thuat_may` vì đây là hàng chờ CỦA TỔ SỬA CHỮA — người báo hỏng không cần số này
    // (và endpoint cũng đòi đúng quyền đó).
    if (readable.has("ky_thuat_may")) {
      kyThuatMay
        .choXuLy(token)
        .then((r) => setBadges((prev) => ({ ...prev, "sua-chua-may": r.total })))
        .catch(() => {});
    }
    // Badge Phiếu bảo trì = số phiếu TỚI HẠN/quá hạn còn dở. Ticker nền đẩy `bao_tri_due` khi tới
    // ngày ⇒ số này tự nhảy, thợ không phải mở màn mới biết máy tới kỳ.
    if (readable.has("phieu_bao_tri")) {
      kyThuatMay
        .denHan(token)
        .then((r) => {
          setBadges((prev) => ({ ...prev, "phieu-bao-tri": r.total }));
          // Toast NGAY khi mở app nếu đang có việc tới hạn — không chỉ dựa vào sự kiện SSE.
          // Sự kiện là "bắn rồi thôi": ticker ting lúc 7h sáng mà thợ 8h mới đăng nhập thì cú ting
          // đó rơi vào hư không, và sổ "đã ting" của ticker chặn nhắc lại cho tới hôm sau. Badge
          // thì bền (đọc theo trạng thái), nhưng một con số nhỏ trên thanh bên rất dễ lướt qua.
          if (r.total > 0 && !daToastBaoTri.current) {
            daToastBaoTri.current = true;   // đúng MỘT lần mỗi phiên, không lặp mỗi lần refetch
            pushToast(
              r.qua_han > 0
                ? `⚠️ ${r.qua_han} phiếu bảo trì quá hạn (tổng ${r.total} phiếu tới hạn)`
                : `🔧 ${r.total} phiếu bảo trì tới hạn hôm nay`,
              r.qua_han > 0 ? "warn" : "info",
            );
          }
        })
        .catch(() => {});
    }
    if (readable.has("luong")) {
      api.luong
        .advanceNotifySummary(token)
        .then((s) => {
          lastAdvancePending.current = s.pending_approval_count;
          setBadges((prev) => ({ ...prev, luong: s.pending_approval_count }));
        })
        .catch(() => {});
    }
    // Badge Kho = số yêu cầu ĐÃ DUYỆT chờ kho lập phiếu (Nhập + Xuất). Snapshot; toast do SSE lo.
    if (readable.has("kho")) {
      api.kho.deNghi
        .counts(token)
        .then((c) => {
          // Workload (chờ cấp) nuôi toast "việc mới"; badge = workload + phản-hồi-kho-chưa-xem của tôi.
          lastKhoPending.current = c.nhap + c.xuat + c.dieu_chuyen;
          setKhoCounts(c);
          setBadges((prev) => ({
            ...prev,
            "kho-main": c.nhap + c.xuat + c.dieu_chuyen + c.done_unseen + c.fail_unseen,
          }));
        })
        .catch(() => {});
    }
  }, [token, readable, reloadModuleNotificationBadges]);
  // Nạp MỘT lần sau khi đăng nhập (và khi phạm vi quyền đổi). CỐ Ý bỏ `activeId` khỏi danh sách
  // phụ thuộc (18/08/2026): ghi chú cũ "cả 2 endpoint đều rất nhẹ" đã sai từ lâu — chùm này nay
  // gọi ~10 endpoint, trong đó `bai-ghep-2/hang-cho`, `xep-lich/hang-cho`,
  // `kho/de-nghi/counts` đều là hàm nặng CPU thuần Python. Bắt chúng chạy lại mỗi lần ĐỔI MÀN là
  // trả giá lớn cho những con số hiếm khi đổi, và trên một tiến trình uvicorn thì nó làm cả API
  // đứng hình chứ không riêng cái đang gọi.
  //
  // Badge KHÔNG vì thế mà cũ: thay đổi THẬT đều có đường đẩy tới — nhánh SSE bên dưới nạp lại ba
  // badge khối Sản xuất + badge kho ngay khi có sự kiện, còn các màn gọi `onBadgeStale` sau mỗi
  // thao tác của chính người dùng (Kế hoạch SX · Bài ghép · Xếp lịch · Nghỉ phép · Tăng ca…).
  useEffect(() => {
    reloadBadges();
  }, [reloadBadges]);

  // Badge Kế hoạch vật tư = Σ BA loại việc phải lo: thiếu · chưa đánh giá được · hàng về muộn.
  // Gộp cả ba vì cả ba đều làm lệnh đứng máy — thứ máy không tính nổi còn phải lo NHIỀU HƠN thứ đã
  // biết thiếu, còn hàng về muộn thì đã mua rồi nhưng vẫn chưa chạy được.
  //
  // ⚠️ TÁCH khỏi `reloadBadges` (18/09/2026): `can-doi` duyệt mọi lệnh + bài ghép + lô kho + phiếu
  // mua rồi chạy engine quy đổi cho từng dòng. Nằm trong `reloadBadges` thì nó chạy lại sau MỖI
  // sự kiện và mỗi thao tác gọi `onBadgeStale`/`onChanged` — nghỉ phép, tăng ca, báo giá, chăm sóc
  // khách… chẳng cái nào đổi được con số này. Nay chỉ nạp lúc mở app / đổi quyền; khi màn Kế hoạch
  // vật tư đang mở thì chính màn báo số lên (`baoSoViecVatTu`), không tốn thêm lượt gọi nào.
  const reloadBadgeVatTu = useCallback(() => {
    if (!token || readable === null || !readable.has("ke_hoach_vat_tu")) return;
    if (dangNapVatTu.current) return;
    dangNapVatTu.current = true;
    api.keHoachVatTu
      .canDoi(token, { chi_thieu: true })
      .then((r) =>
        setBadges((prev) => ({
          ...prev,
          // Cộng CẢ HAI loại phải lo: thiếu · chưa đánh giá được.
          "ke-hoach-vat-tu": (r.items ?? []).reduce(
            (s, g) => s + (g.so_dong_do ?? 0) + (g.so_dong_khong_ro ?? 0),
            0,
          ),
        })),
      )
      .catch(() => {})
      .finally(() => {
        dangNapVatTu.current = false;
      });
  }, [token, readable]);
  useEffect(() => {
    reloadBadgeVatTu();
  }, [reloadBadgeVatTu]);
  const baoSoViecVatTu = useCallback((n: number) => {
    setBadges((prev) => (prev["ke-hoach-vat-tu"] === n ? prev : { ...prev, "ke-hoach-vat-tu": n }));
  }, []);

  // Danh sách kho cho menu con động (chỉ người có quyền `kho`). Gọi lại sau mỗi lần khai báo kho.
  const reloadKho = useCallback(() => {
    if (!token || readable === null || !readable.has("kho")) return;
    crud("/api/kho")
      .list(token, { active: true })
      .then((r) => setKhoList(r.items.map((w) => ({ id: Number(w.id), ma: String(w.ma), ten: String(w.ten) }))))
      .catch(() => {});
  }, [token, readable]);
  useEffect(() => { reloadKho(); }, [reloadKho]);

  // Danh sách bàn tổ (chỉ người có Xem ở ít nhất một dòng quyền theo tổ). MỘT cú gọi ra cả list
  // (đổ node lá, đã theo thứ tự cây) lẫn badge (`so_viec_cho`). Gọi lại sau mỗi sự kiện bàn tổ đổi (SSE).
  const reloadTeams = useCallback(() => {
    if (!token || readable === null) return;
    // Vừa bị rút hết quyền bàn tổ (tải lại quyền sau khi lưu vai trò) ⇒ bỏ danh sách cũ luôn.
    if (!coQuyenBanTo(readable)) {
      setTeamList([]);
      return;
    }
    api.sanXuat
      .teams(token)
      .then((r) => setTeamList(r.teams))
      .catch(() => {});
  }, [token, readable]);
  useEffect(() => { reloadTeams(); }, [reloadTeams]);
  // Badge node lá tổ = `so_viec_cho` (đã kèm trong `teams`, KHÔNG gọi API badge riêng). Đồng bộ
  // mỗi khi teamList đổi (nạp đầu + sau mỗi sự kiện bàn tổ).
  useEffect(() => {
    if (!teamList.length) return;
    setBadges((prev) => {
      const next = { ...prev };
      for (const t of teamList) {
        // Việc chờ làm + việc giữa hai tổ đang chờ tổ này đứng tên (bàn giao đến, hỗ trợ chéo).
        next[`thuc-hien-sx:${t.id}`] = t.so_viec_cho + (t.so_cho_xac_nhan ?? 0);
      }
      return next;
    });
  }, [teamList]);

  // Real-time luồng gửi duyệt (CLAUDE.md "gửi nội bộ = real-time"): mở 1 kênh SSE sau đăng nhập →
  // GĐ thấy 'chờ duyệt' ngay khi Sale trình; Sale thấy 'đã duyệt/từ chối' ngay khi GĐ quyết. Đóng
  // khi logout/đổi bộ quyền.
  //
  // MỌI tài khoản đăng nhập đều mở (17/09/2026). Trước đó chỉ mở khi có Xem ở một danh sách module
  // "có thời gian thực" — nên tài khoản chưa có vai hoặc vai chỉ có màn tĩnh không bao giờ nghe
  // được `quyen_doi`: được gán vai xong vẫn đứng nhìn menu trống tới khi F5. Danh sách đó còn chép
  // hai lần lệch nhau (bản thứ hai thiếu Bài ghép, Xếp lịch, Hồ sơ lệnh SX) và chặn luôn các tin
  // gửi đích danh cho chính người đó (đổi ca, chuông) — thứ vốn không cần quyền module nào.
  useEffect(() => {
    if (!token || readable === null) return;

    const close = connectQuoteEvents(token, (e) => {
      // Quyền của CHÍNH người này vừa đổi (vai của họ được lưu lại ma trận, được gán/gỡ vai, đổi
      // phòng). Máy chủ đã gác theo quyền mới từ request kế tiếp; menu + nút thì phải hỏi lại.
      if (e.type === "quyen_doi") {
        reloadAccess(true);
        return;
      }
      // Chuyến giao của CHÍNH tài xế này — máy chủ đẩy đích danh nên không lọc quyền lần nữa.
      // Tài xế đang ở kho hoặc trên đường, không ngồi canh màn hình (CLAUDE.md: nội bộ = tức thì).
      if (e.type === "giao_hang_chuyen") {
        setQuoteTick((n) => n + 1);
        pushToast(
          String(e.message ?? "Chuyến giao của bạn vừa cập nhật."),
          e.viec === "kho_xong" ? "ok" : "info",
        );
        return;
      }
      // Đề nghị cấp vật tư của MỘT công đoạn vừa đổi. `hub.broadcast` gửi cho MỌI kết nối chứ
      // không theo phạm vi, nên cả hai cổng lọc nằm ở đây:
      //   1) toast gác quyền Xem bàn tổ — không thì kế toán, lái xe cũng ăn toast của tổ in;
      //   2) KHÔNG bump `quoteTick` (tick chung của mọi màn) — chỉ đẩy đích danh `cong_viec_id`
      //      xuống bàn tổ để đúng drawer đang mở việc đó nạp lại. Bump tick chung ở đây là biến
      //      một lần tổ gửi đề nghị thành một lượt gọi API cho MỌI màn đang mở của cả nhà máy.
      if (e.type === "san_xuat_vat_tu_de_nghi_changed") {
        if (coQuyenBanTo(readable)) {
          const cv = e.cong_viec_id;
          setVatTuDeNghiDem((m) => ({ ...m, [cv]: (m[cv] ?? 0) + 1 }));
          // Cổng thứ 3: KHÔNG toast cho việc người này đang mở (drawer vừa tươi, và nếu chính họ
          // bấm thì `mutate` đã toast rồi) và gộp trong 2 giây — không thì mỗi lần bất kỳ tổ nào
          // trong nhà máy bấm gửi là mọi người xem được bàn tổ ăn một toast.
          const gio = Date.now();
          if (cv !== cvDangMo.current && gio - lastVatTuToast.current > 2000) {
            lastVatTuToast.current = gio;
            pushToast("📦 Đề nghị cấp vật tư của công đoạn vừa cập nhật", "info");
          }
        }
        return;
      }
      // Tệp đính kèm của lệnh: không toast (không phải việc gửi tới ai), không bump tick chung.
      // Hai nơi đọc: tab Tệp của Kế hoạch SX và thẻ "Tệp của lệnh" trong drawer Bàn tổ (tổ không
      // có module `san_xuat`, vào bằng quyền theo tổ).
      if (e.type === "lsx_dinh_kem_changed") {
        if (readable.has("san_xuat") || coQuyenBanTo(readable)) {
          const id = e.lsx_id;
          setLsxDinhKemDem((m) => ({ ...m, [id]: (m[id] ?? 0) + 1 }));
        }
        return;
      }
      // Mọi event luồng duyệt → đẩy tick: màn Báo giá đang mở tự tải lại bảng + số đếm tab.
      setQuoteTick((n) => n + 1);
      // Giữ chỗ vật tư vừa đổi (bật/tắt/nhặt thêm/hàng về/đối soát PMH) — tick ở trên đã bump nên
      // màn Kế hoạch vật tư tự tải lại; chỉ cần báo cho người đang mở màn khác biết số đã đổi.
      if (e.type === "ke_hoach_vat_tu_thay_doi") {
        const gio = Date.now();
        if (gio - lastKhvtToast.current > 2000) {
          lastKhvtToast.current = gio;
          pushToast("Kế hoạch vật tư vừa cập nhật.", "info");
        }
        return;
      }
      if (e.type === "quote_decision") {
        pushToast(
          e.decision === "approved"
            ? `✓ Báo giá ${e.code} đã được duyệt`
            : `✕ Báo giá ${e.code} bị từ chối`,
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (readable.has("bao_gia") && e.type === "quote_pending_changed") {
        // Danh sách 'chờ duyệt' đổi → refetch số; chỉ toast khi số 'chờ TÔI duyệt' TĂNG (có việc mới).
        api.quotations
          .notifySummary(token)
          .then((s) => {
            setBadges((prev) => ({
              ...prev,
              "bao-gia": s.pending_approval_count + s.my_decided_unseen,
            }));
            if (s.pending_approval_count > lastPending.current) {
              pushToast(`🔔 Có báo giá${e.code ? " " + e.code : ""} chờ bạn duyệt`, "info");
            }
            lastPending.current = s.pending_approval_count;
          })
          .catch(() => {});
      // Nhánh `order_decision` (duyệt/từ chối đơn đặc thù) đã gỡ cùng luồng duyệt — backend
      // không còn publish event này nữa.
      } else if (readable.has("don_hang_ban") && e.type === "order_deposit_ok") {
        pushToast(`🔔 Đơn ${e.code} đã đủ cọc — chuyển xuống sản xuất được rồi`, "info");
        reloadBadges();
      } else if (readable.has("don_hang_ban") && e.type === "order_pending_changed") {
        // Danh sách 'chờ (duyệt/ghi cọc/chốt)' đổi → refetch số theo vai; toast khi số 'chờ TÔI' TĂNG.
        api.orders
          .notifySummary(token)
          .then((s) => {
            setBadges((prev) => ({ ...prev, "don-hang-ban": s.action_count }));
            if (s.action_count > lastOrderAction.current) {
              pushToast("🔔 Có đơn hàng chờ bạn xử lý", "info");
            }
            lastOrderAction.current = s.action_count;
          })
          .catch(() => {});
      } else if (e.type === "shift_changed") {
        // Quản lý vừa đổi ca của TÔI. Không gác sau `readable`: đây là việc của chính mình,
        // công nhân xưởng không có quyền đọc module nhân sự vẫn phải nhận được.
        api.attendance
          .notifySummary(token)
          .then((s) => {
            setBadges((prev) => ({ ...prev, "cham-cong": s.unseen_shift_changes }));
            if (s.unseen_shift_changes > lastShiftChange.current) {
              pushToast("🔔 Ca làm việc của bạn vừa được thay đổi", "info");
            }
            lastShiftChange.current = s.unseen_shift_changes;
          })
          .catch(() => {});
      } else if (
        e.type === "order_ordered" ||
        e.type === "lsx_changed" ||
        e.type === "bai_ghep_changed" ||
        e.type === "xep_lich_changed"
      ) {
        // Sale "Chuyển xuống sản xuất" → hàng chờ Kế hoạch nhảy (badge + toast); Kế hoạch/ghép bài/
        // xếp lịch đổi → 3 badge khối Sản xuất co giãn NGAY. Nội dung màn tự refetch qua `quoteTick`.
        //
        // Ba lượt nạp gác RIÊNG từng khoá (tách 17/08/2026): một sự kiện `lsx_changed` vẫn làm
        // hàng chờ của cả ba màn đổi, nhưng người chỉ có Bài ghép thì chỉ nên nạp lại badge Bài ghép.
        if (readable.has("san_xuat")) {
          api.lsx
            .hangCho(token)
            .then((r) => {
              setBadges((prev) => ({ ...prev, "ke-hoach-sx": r.total }));
              if (e.type === "order_ordered") {
                pushToast(`🔔 Đơn ${e.code ?? ""} vừa chuyển xuống sản xuất`.trim(), "info");
              }
            })
            .catch(() => {});
        }
        if (BAI_GHEP_ENABLED && readable.has("bai_ghep_2")) {
          api.baiGhep2
            .hangCho(token)
            .then((r) => setBadges((prev) => ({ ...prev, "bai-ghep-2": r.total })))
            .catch(() => {});
        }
        if (readable.has("xep_lich")) {
          api.xepLich
            .hangCho(token, { moi_trang: 1 })
            .then((r) => setBadges((prev) => ({ ...prev, "xep-lich": r.tong })))
            .catch(() => {});
        }
      } else if (coQuyenBanTo(readable) && e.type === "san_xuat_cong_viec_changed") {
        // Bàn tổ đổi (giao người / bắt đầu / tạm dừng / kết thúc / phát hành) → badge tổ nhảy
        // NGAY; `quoteTick` đã bump ở đầu handler nên bàn đang mở tự refetch (không refresh).
        // `teams` mang cả `so_viec_cho` nên reloadTeams lo luôn badge — không gọi API badge riêng.
        reloadTeams();
      } else if (coQuyenBanTo(readable) && e.type === "san_xuat_kcs_changed") {
        // KCS ghi/điều chỉnh một lần kiểm, hoặc tổ mở tab KCS (đã xem lỗi) → badge "chờ xác nhận" của tổ
        // bị báo lỗi đổi NGAY; `quoteTick` đã bump ở đầu handler nên màn KCS, hộp "KCS báo lỗi" và
        // mục "Kết quả KCS" đang mở tự nạp lại (không refresh).
        reloadTeams();
      } else if (
        coQuyenBanTo(readable) &&
        (e.type === "san_xuat_ban_giao_changed" || e.type === "san_xuat_ho_tro_changed")
      ) {
        // Việc giữa hai tổ đổi (bàn giao · hỗ trợ chéo) → badge "chờ xác nhận" của tổ nhảy NGAY;
        // `quoteTick` đã bump nên hộp "Chờ tổ bạn xác nhận" của bàn đang mở tự nạp lại.
        reloadTeams();
      } else if (e.type === "san_xuat_ban_giao") {
        // Đẩy ĐÍCH DANH (máy chủ đã lọc người giữ Xác nhận sản lượng trọn tổ bên kia, trừ người bấm).
        const sl = e.so_luong != null ? `${e.so_luong.toLocaleString("vi-VN")} ${nhanDonVi(e.don_vi)}`.trim() : "";
        const tuyen = `${e.nguon_ten || "?"} → ${e.dich_ten || "?"}`;
        if (e.su_kien === "xac_nhan") {
          pushToast(`✓ Tổ nhận đã xác nhận bàn giao ${tuyen}${sl ? " · " + sl : ""}`, "ok");
        } else if (e.su_kien === "dieu_chinh") {
          pushToast(`✏️ Bàn giao ${tuyen} vừa được điều chỉnh${sl ? " thành " + sl : ""}`, "warn");
        } else if (e.su_kien === "sua") {
          pushToast(`✏️ Bàn giao ${tuyen} vừa sửa${sl ? " còn " + sl : ""} — chờ tổ bạn xác nhận`, "info");
        } else {
          pushToast(`🔔 Bàn giao mới ${tuyen}${sl ? " · " + sl : ""} — chờ tổ bạn xác nhận`, "info");
        }
      } else if (e.type === "san_xuat_ho_tro") {
        const ai = `${e.ho_ten || "?"} (${e.to_goc_ten || "?"}) → ${e.ten_cong_doan || "?"} · ${e.to_thuc_hien_ten || "?"}`;
        if (e.trang_thai === "confirmed") {
          pushToast(`✓ Hỗ trợ chéo đã đủ hai tổ xác nhận: ${ai}`, "ok");
        } else if (e.trang_thai === "cancelled") {
          pushToast(`✕ Thỏa thuận hỗ trợ chéo đã huỷ: ${ai}`, "warn");
        } else {
          pushToast(`🔔 Lời mời hỗ trợ chéo: ${ai} — chờ tổ bạn xác nhận`, "info");
        }
      } else if (e.type === "san_xuat_duoc_giao_viec") {
        // Đẩy đích danh tới người vừa được giao việc (chỉ người có tài khoản nhận) — toast cá nhân.
        pushToast("🔔 Bạn được giao việc sản xuất mới", "info");
      } else if (e.type === "san_xuat_kcs_ket_qua") {
        // KCS vừa kiểm một công đoạn của tổ — đẩy ĐÍCH DANH tới người giữ Xác nhận sản lượng của tổ
        // đó (§ thông báo tổ). Một chiều: tổ mở tab KCS là đã xem, không Nhận/Từ chối.
        const ai = e.nguoi_kiem ? `KCS ${e.nguoi_kiem}` : "KCS";
        const soDat = e.so_dat ?? 0;
        const soLoi = e.so_loi ?? 0;
        const lenh = e.lsx_ma ? ` (${e.lsx_ma})` : "";
        if (e.phat_hien_o) {
          // Lỗi của công đoạn này bị bắt ở bước SAU — KCS quy trách nhiệm về tổ.
          pushToast(
            `⚠️ ${ai} bắt lỗi ${e.ten_cong_doan || "công đoạn"}${lenh} ở bước ${e.phat_hien_o}: ${soLoi.toLocaleString("vi-VN")} ${nhanChang(e.don_vi)}`.trim(),
            "warn",
          );
        } else {
          const so = `đạt ${soDat.toLocaleString("vi-VN")} · lỗi ${soLoi.toLocaleString("vi-VN")}`;
          pushToast(
            `${soLoi > 0 ? "⚠️" : "✓"} ${ai} đã kiểm ${e.ten_cong_doan || "công đoạn"}${lenh}: ${so}`,
            soLoi > 0 ? "warn" : "ok",
          );
        }
      } else if (e.type === "san_xuat_kho") {
        // Nhập kho thành phẩm là tương tác GIỮA KCS và kho — kho ghi sổ phiếu nhập thì đẩy ĐÍCH DANH
        // tới người tạo yêu cầu (kho đã nhận tới đâu). `trang_thai` = trạng thái yêu cầu kho.
        const ma = e.ma ? ` ${e.ma}` : "";
        pushToast(
          e.trang_thai === "partial"
            ? `📦 Kho đã nhận MỘT PHẦN yêu cầu nhập kho${ma} — phần còn lại vẫn chờ nhập`
            : `📦 Kho đã nhận đủ yêu cầu nhập kho${ma}`,
          "ok",
        );
      } else if (
        (readable.has("san_xuat") || readable.has("don_hang_ban")) &&
        e.type === "san_xuat_nhom_dong"
      ) {
        // Nhóm thành phẩm đã đóng (§16 đủ = KCS đạt đủ mục tiêu / §13.3 thiếu = trưởng KCS chốt khi
        // hụt) → báo Sale + Kế hoạch SX NGAY. Broadcast nên gác theo vai (san_xuat = Kế hoạch,
        // don_hang_ban = Sale).
        pushToast(
          e.trang_thai === "closed_short"
            ? "⚠️ Nhóm thành phẩm đã ĐÓNG THIẾU"
            : "✅ Nhóm thành phẩm đã hoàn tất — đơn có thể giao",
          e.trang_thai === "closed_short" ? "warn" : "ok",
        );
      } else if (readable.has("ky_thuat_may") && e.type === "ky_thuat_yeu_cau_moi") {
        // Bộ phận khác vừa báo máy hỏng → ting tổ sửa chữa NGAY. Máy đang dừng thì đổi giọng: đó
        // là khác biệt giữa "lát nữa ghé xem" và "bỏ việc đang làm chạy sang".
        pushToast(
          e.may_dung
            ? `⚠️ ${e.may} ĐANG DỪNG · ${e.bo_phan_hong} — ${e.nguoi_bao ?? "?"} báo`
            : `🔔 Báo máy hỏng: ${e.may} · ${e.bo_phan_hong}${e.nguoi_bao ? " — " + e.nguoi_bao : ""}`,
          e.may_dung ? "warn" : "info",
        );
        reloadBadges();
      } else if (e.type === "ky_thuat_yeu_cau_ket_qua") {
        // Kết quả đẩy riêng về ĐÚNG người đã báo (không broadcast) ⇒ KHÔNG gác quyền: nhận được
        // sự kiện này nghĩa là mình chính là người gửi lời báo đó.
        pushToast(
          e.ket_qua === "da_tao_phieu"
            ? `✅ ${e.ma} đã được tiếp nhận — phiếu ${e.phieu_ma ?? ""}${e.boi ? " · " + e.boi : ""}`
            : `✕ ${e.ma} không lập phiếu: ${e.ly_do ?? ""}`,
          e.ket_qua === "da_tao_phieu" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (readable.has("phieu_bao_tri") && e.type === "bao_tri_due") {
        // Tới ngày bảo trì → ting tổ sửa chữa: toast + badge "Phiếu bảo trì" tự nhảy.
        pushToast(
          `${e.qua_han ? "⚠️ Quá hạn bảo trì" : "🔧 Tới hạn bảo trì"}: ${e.may} · ${e.goi}`.trim(),
          e.qua_han ? "warn" : "info",
        );
        reloadBadges();
      } else if (readable.has("khach_hang") && e.type === "care_due") {
        // Tới giờ hẹn → ting người phụ trách: toast + badge "Khách hàng" (số việc đến hạn) tự nhảy.
        pushToast(`🔔 Tới hẹn chăm sóc: ${e.customer}${e.note ? " — " + e.note : ""}`, "info");
        reloadBadges();
      } else if (readable.has("khach_hang") && e.type === "care_assigned") {
        pushToast(`📋 Bạn có hẹn chăm sóc mới: ${e.customer}${e.note ? " — " + e.note : ""}`, "info");
        reloadBadges();
      } else if (e.type === "advance_decision") {
        // Nhân viên đề nghị nhận quyết định của kế toán — đẩy riêng tới đúng người.
        pushToast(
          e.decision === "approved"
            ? "✓ Đề nghị tạm ứng của bạn đã được duyệt"
            : "✕ Đề nghị tạm ứng của bạn bị từ chối",
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (e.type === "ot_decision") {
        // NV nộp phiếu tăng ca nhận quyết định của tổ trưởng — đẩy riêng tới đúng người.
        pushToast(
          e.decision === "approved"
            ? "✓ Phiếu tăng ca của bạn đã được duyệt"
            : e.decision === "cancelled"
              ? "✕ Phiếu tăng ca đã duyệt của bạn vừa bị HUỶ — tối nay không còn giấy phép tăng ca"
              : e.decision === "huy_dong_y"
                ? "✓ Yêu cầu hủy phiếu tăng ca của bạn đã được đồng ý — phiếu đã hủy"
                : e.decision === "huy_giu_nguyen"
                  ? "✕ Yêu cầu hủy phiếu tăng ca không được đồng ý — phiếu vẫn giữ, xem lý do ở Tăng ca"
                  : "✕ Phiếu tăng ca của bạn bị từ chối",
          e.decision === "approved" || e.decision === "huy_dong_y" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (e.type === "leave_decision") {
        // Nghỉ phép (23/09/2026): quyết định về đơn đẩy riêng tới người đứng tên đơn.
        const msg: Record<string, string> = {
          approved: "✓ Đơn nghỉ phép của bạn đã được duyệt",
          rejected: "✕ Đơn nghỉ phép của bạn bị từ chối — xem lý do ở Nghỉ phép",
          cancelled: "✕ Đơn nghỉ đã duyệt của bạn vừa bị HỦY — xem lý do ở Nghỉ phép",
          huy_dong_y: "✓ Yêu cầu hủy đơn nghỉ đã được đồng ý — đơn đã hủy",
          huy_rut_ngan: "✓ Yêu cầu hủy đơn nghỉ đã được đồng ý — đơn được rút ngắn, giữ các ngày đã nghỉ",
          huy_giu_nguyen: "✕ Yêu cầu hủy đơn nghỉ không được đồng ý — đơn vẫn giữ, xem lý do ở Nghỉ phép",
        };
        pushToast(msg[e.decision] ?? "Đơn nghỉ phép của bạn vừa được cập nhật",
          e.decision === "approved" || e.decision === "huy_dong_y" || e.decision === "huy_rut_ngan" ? "ok" : "warn");
        reloadBadges();
      } else if (readable.has("nghi_phep") && e.type === "leave_pending_changed") {
        // Có đơn mới / yêu cầu hủy / vừa xử lý → refetch số chờ duyệt; toast khi TĂNG (người duyệt).
        api.leaves
          .summary(token)
          .then((s) => {
            const n = s.pending_in_scope ?? 0;
            setBadges((prev) => ({ ...prev, "nghi-phep": n }));
            if (n > lastLeavePending.current) {
              pushToast("🔔 Có đơn nghỉ phép / yêu cầu hủy chờ bạn duyệt", "info");
            }
            lastLeavePending.current = n;
          })
          .catch(() => {});
      } else if (readable.has("tang_ca") && e.type === "ot_pending_changed") {
        // Có phiếu tăng ca mới/hủy → refetch số 'chờ duyệt'; toast khi TĂNG (người duyệt).
        api.overtime
          .summary(token)
          .then((s) => {
            const n = s.pending_in_scope ?? 0;
            setBadges((prev) => ({ ...prev, "tang-ca": n }));
            if (n > lastOtPending.current) {
              pushToast("🔔 Có phiếu tăng ca chờ bạn duyệt", "info");
            }
            lastOtPending.current = n;
          })
          .catch(() => {});
      } else if (e.type === "adjust_decision") {
        // NV gửi yêu cầu chỉnh công nhận quyết định (E7, 08/09/2026) — không phải F5 mới biết bị từ chối.
        pushToast(
          e.decision === "approved"
            ? `✓ Yêu cầu chỉnh công ngày ${e.code ?? ""} đã được duyệt`
            : `✕ Yêu cầu chỉnh công ngày ${e.code ?? ""} bị từ chối — xem lý do ở Chấm công`,
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (readable.has("cham_cong") && e.type === "adjust_pending_changed") {
        // Có yêu cầu chỉnh công mới/huỷ → người duyệt refetch (tab đang mở tự tải lại theo eventTick).
        reloadBadges();
      } else if (e.type === "el_decision") {
        // NV nộp phiếu đi muộn / về sớm nhận quyết định của tổ trưởng — đẩy riêng tới đúng người.
        pushToast(
          e.decision === "approved"
            ? "✓ Phiếu đi muộn / về sớm của bạn đã được duyệt"
            : "✕ Phiếu đi muộn / về sớm của bạn bị từ chối",
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (readable.has("cham_cong") && e.type === "el_pending_changed") {
        // Có phiếu đi muộn mới/hủy → refetch số 'chờ duyệt'; toast khi TĂNG (người duyệt).
        // Badge treo ở nav "cham-cong" (tab phiếu nằm trong màn Chấm công).
        api.lateEarly
          .summary(token)
          .then((s) => {
            const n = s.pending_in_scope ?? 0;
            setBadges((prev) => ({ ...prev, "cham-cong": n }));
            if (n > lastElPending.current) {
              pushToast("🔔 Có phiếu đi muộn / về sớm chờ bạn duyệt", "info");
            }
            lastElPending.current = n;
          })
          .catch(() => {});
      } else if (
        readable.has("thu_mua") &&
        e.type === "department_purchase_request_created" &&
        e.actor_user_id !== user?.id
      ) {
        pushToast(`Có yêu cầu mua hàng${e.code ? " " + e.code : ""} mới từ phòng ban`, "info");
        reloadBadges();
      } else if (
        readable.has("ke_toan") &&
        e.type === "purchase_pending_approval" &&
        e.actor_user_id !== user?.id
      ) {
        pushToast(`Có đơn mua hàng${e.code ? " " + e.code : ""} chờ xử lý`, "info");
        reloadBadges();
      } else if (
        readable.has("thu_mua") &&
        e.type === "purchase_decision" &&
        e.actor_user_id !== user?.id &&
        (e.recipient_user_id == null || e.recipient_user_id === user?.id)
      ) {
        pushToast(
          e.decision === "approved"
            ? `Đơn mua hàng${e.code ? " " + e.code : ""} đã được duyệt`
            : `Đơn mua hàng${e.code ? " " + e.code : ""} bị từ chối, cần sửa và gửi lại`,
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (
        (readable.has("ke_toan") || readable.has("phieu_chi")) &&
        (e.type === "purchase_delivery_created" ||
          e.type === "purchase_delivery_updated" ||
          e.type === "purchase_delivery_deleted" ||
          e.type === "purchase_invoice_updated") &&
        e.actor_user_id !== user?.id
      ) {
        const code = e.code ? ` ${e.code}` : "";
        if (e.type === "purchase_delivery_created") {
          pushToast(
            `Đơn mua hàng${code} có đợt giao mới${e.seq_no ? ` số ${e.seq_no}` : ""}`,
            "info",
          );
        } else if (e.type === "purchase_delivery_updated") {
          pushToast(`Đợt giao của đơn mua hàng${code} đã được cập nhật`, "info");
        } else if (e.type === "purchase_delivery_deleted") {
          pushToast(`Đợt giao của đơn mua hàng${code} đã được xóa`, "warn");
        } else {
          pushToast(`Hóa đơn của đơn mua hàng${code} đã được cập nhật`, "info");
        }
        reloadBadges();
      } else if (
        readable.has("thu_mua") &&
        e.type === "payment_voucher_created" &&
        e.actor_user_id !== user?.id &&
        (e.recipient_user_id == null || e.recipient_user_id === user?.id)
      ) {
        pushToast(
          `Kế toán đã lập chứng từ${e.voucher_code ? " " + e.voucher_code : ""}${
            e.code ? ` cho đơn ${e.code}` : ""
          }`,
          "ok",
        );
        reloadBadges();
      } else if (
        readable.has("thu_mua") &&
        e.type === "payment_voucher_cancelled" &&
        e.actor_user_id !== user?.id &&
        (e.recipient_user_id == null || e.recipient_user_id === user?.id)
      ) {
        pushToast(
          `Kế toán đã hủy chứng từ${e.voucher_code ? " " + e.voucher_code : ""}${
            e.code ? ` của đơn ${e.code}` : ""
          }`,
          "warn",
        );
        reloadBadges();
      } else if (
        (readable.has("thu_mua") || readable.has("ke_toan")) &&
        (e.type === "purchase_changed" || e.type === "accounting_changed")
      ) {
        reloadModuleNotificationBadges();
      } else if (readable.has("luong") && e.type === "advance_pending_changed") {
        // Có đề nghị tạm ứng mới/đổi → refetch số 'chờ duyệt'; toast khi TĂNG (người duyệt).
        api.luong
          .advanceNotifySummary(token)
          .then((s) => {
            setBadges((prev) => ({ ...prev, luong: s.pending_approval_count }));
            if (s.pending_approval_count > lastAdvancePending.current) {
              pushToast("🔔 Có đề nghị tạm ứng chờ bạn duyệt", "info");
            }
            lastAdvancePending.current = s.pending_approval_count;
          })
          .catch(() => {});
      } else if (readable.has("kho") && e.type === "stock_request") {
        // Tin ĐÍCH DANH của luồng kho (duyệt/từ chối/hủy/cấp…). Câu chữ backend soạn; chèn CHIỀU
        // (nhập/xuất) vào đầu cho cụ thể, hiện lâu hơn (9s).
        const dir = e.loai === "XUAT" ? "xuất" : "nhập";
        const msg = e.message.startsWith("Yêu cầu")
          ? e.message.replace(/^Yêu cầu/, `Yêu cầu ${dir}`)
          : e.message;
        pushToast(msg, "info", 9000);
        // Phản hồi kho (hoàn tất/không thành) cho yêu cầu CỦA TÔI → badge nhập-xuất nhảy NGAY (không
        // đợi refresh). Chỉ người TẠO/DUYỆT nhận tin đích danh này nên refetch là đúng đối tượng.
        api.kho.deNghi
          .counts(token)
          .then((c) => {
            lastKhoPending.current = c.nhap + c.xuat + c.dieu_chuyen;
            setKhoCounts(c);
            setBadges((prev) => ({
              ...prev,
              "kho-main": c.nhap + c.xuat + c.dieu_chuyen + c.done_unseen + c.fail_unseen,
            }));
          })
          .catch(() => {});
      } else if (readable.has("kho") && e.type === "stock_request_pending_changed") {
        // Yêu cầu kho đổi (tạo/duyệt/cấp…) → cập nhật badge Nhập/Xuất; toast thủ kho khi tổng
        // "chờ cấp" TĂNG (có việc mới). quoteTick ở đầu handler đã lo refetch 2 màn kho đang mở.
        api.kho.deNghi
          .counts(token)
          .then((c) => {
            const workload = c.nhap + c.xuat + c.dieu_chuyen; // chỉ "chờ cấp" — nuôi toast việc-mới
            setKhoCounts(c);
            setBadges((prev) => ({
              ...prev,
              "kho-main": workload + c.done_unseen + c.fail_unseen,
            }));
            // Toast "có việc mới" CHỈ cho người XỬ LÝ kho (lập phiếu / xem tồn), KHÔNG gửi người TẠO.
            const canProcess = !!(caps.get("kho")?.can_create || caps.get("kho")?.can_view_stock);
            if (workload > lastKhoPending.current && canProcess && user?.id !== e.nguoi_tao_id) {
              const dir = e.loai === "XUAT" ? "xuất" : "nhập";
              // Nói rõ đến từ AI · PHÒNG nào để thủ kho biết nguồn ngay.
              const who = [e.nguoi_tao_ten, e.bo_phan_ten].filter(Boolean).join(" · ");
              pushToast(
                `🔔 Có yêu cầu ${dir} mới chờ cấp${who ? ` — ${who}` : ""}`,
                "info",
                9000,
              );
            }
            lastKhoPending.current = workload;
          })
          .catch(() => {});
      }
    });
    return close;
  }, [token, readable, reloadBadges, reloadModuleNotificationBadges, reloadTeams, pushToast, caps, user, reloadAccess]);

  useEffect(() => {
    if (readable === null) return;
    const baseId = activeId.split(":")[0];
    if (baseId === MODULE_NOTIFICATION_NAV.thu_mua && readable.has("thu_mua")) {
      markThuMuaNotificationsRead();
    } else if (baseId === MODULE_NOTIFICATION_NAV.ke_toan && readable.has("ke_toan")) {
      markKeToanNotificationsRead();
    }
  }, [
    activeId,
    readable,
    markThuMuaNotificationsRead,
    markKeToanNotificationsRead,
  ]);

  // Mở màn Báo giá = người soạn đã xem các quyết định → đánh dấu seen + hạ badge (giống chuông Nghỉ phép).
  useEffect(() => {
    if (!token || readable === null) return;
    if (activeId.split(":")[0] === "bao-gia" && readable.has("bao_gia")) {
      api.quotations.markDecisionsSeen(token).then(reloadBadges).catch(() => {});
    }
  }, [activeId, token, readable, reloadBadges]);


  if (readable === null) {
    return (
      <div className="shell__center" role="status" aria-live="polite">
        Đang tải…
      </div>
    );
  }

  const baseId = activeId.split(":")[0];
  // Màn TỒN KHO của từng kho là VIỆC CỦA KHO, không phải của người đề nghị: ông sản xuất chỉ có
  // `kho:read` để đi xin vật tư thì KHÔNG được nhìn tồn/lô. Từ 24/09/2026 (mg `0334`) đây là
  // module RIÊNG `ton_kho` có dòng của mình trong ma trận, thay cho ô chi tiết `kho:view_stock`
  // — trước đó cả nhóm mục menu này nấp sau một công tắc trong panel của màn Yêu cầu nhập xuất.
  const canViewStock = !!caps.get("ton_kho")?.can_read;
  // "kho-item:<id>" = màn Tồn kho của 1 kho — gác `ton_kho:read`.
  const isKhoView = baseId === "kho-item";
  const moduleKeys =
    MODULES_BY_NAV_ID[baseId] ??
    // "thuc-hien-sx" là node lá ĐỘNG — không nằm trong NAV tĩnh của Sidebar nên MODULES_BY_NAV_ID
    // không có, phải khai tay ở đây.
    (baseId === "thuc-hien-sx"
      ? khoaBanTo(readable)
      : isKhoView ? ["ton_kho"] : undefined);
  const allowed =
    AUTHENTICATED_NAV_IDS.has(baseId) ||
    // Màn KCS: người thuộc phòng ban "Tổ KCS", không đi qua ô quyền của vai.
    (baseId === "kcs" && kcsTuCach.kcs) ||
    // KHÔNG mục nào còn phải lọc thêm sau `readable` nữa: "Báo cáo kho" (mg `0329`) và màn Tồn
    // kho của từng kho (mg `0334`) đều đã có khoá riêng. Trước đây cả hai gắn khoá `kho` rồi chặn
    // thêm bằng ô chi tiết `close_book` / `view_stock` — đúng chỗ làm ra những MÀN không có dòng
    // nào của riêng mình trong ma trận phân quyền.
    (moduleKeys != null && moduleKeys.some((moduleKey) => readable.has(moduleKey)));

  const itemChildren: Record<string, { id: string; label: string }[]> = {};
  // Kho đã khai báo → item ĐỘNG dưới SECTION "Kho hàng" (id section = "kho-hang"). Bấm 1 kho → màn tạm.
  // Chỉ đổ khi có `ton_kho:read`; thiếu quyền → khối chỉ còn 2 mục nghiệp vụ (hoặc rỗng, tự ẩn).
  const dynamicItems: Record<string, NavItem[]> = {};
  if (khoList.length && canViewStock) {
    dynamicItems["kho-hang"] = khoList.map((w): NavItem => ({
      id: `kho-item:${w.id}`, label: w.ten, icon: "warehouse", module: "ton_kho",
    }));
  }
  // Mục "KCS" (KCS theo lệnh, mg 0306) — MỘT mục cho người thuộc phòng ban "Tổ KCS", kiểm mọi tổ.
  // Khoá giả `KCS_NAV_KEY` chỉ để Sidebar (lọc theo `readable`) cho mục này qua; nó không phải ô
  // quyền nào trong ma trận.
  const sanXuatDong: NavItem[] = [];
  if (kcsTuCach.kcs) {
    sanXuatDong.push({ id: "kcs", label: "KCS", icon: "shield", module: KCS_NAV_KEY });
  }
  // Tổ đã khai báo → node lá ĐỘNG dưới SECTION "Tổ sản xuất" (id section = "to-san-xuat", khối
  // tách riêng 24/09/2026 — trước đó đổ chung vào khối "Sản xuất"). Bấm 1 tổ → mở
  // bàn "Thực hiện sản xuất" lọc theo tổ. teamList chỉ có dữ liệu khi có Xem ở một dòng quyền theo
  // tổ, nên thiếu quyền thì không đổ node nào. Máy chủ trả theo thứ tự cây kèm `cap` — thụt lề tính
  // từ nút NÔNG nhất người này thấy, để ai chỉ thấy vài tổ lá thì menu vẫn thẳng hàng.
  if (teamList.length) {
    const cacKhoaTo = khoaBanTo(readable);
    const capGoc = Math.min(...teamList.map((t) => t.cap ?? 0));
    // Danh sách về PHẲNG nhưng theo thứ tự cây: nút cha của một hàng là hàng NÔNG hơn gần nhất
    // phía trên. Giữ một chồng để suy ra `parentId` → Sidebar gập được cả nhánh (11 tổ + 5 nhóm in
    // đẩy menu dài quá màn hình).
    const nganh: { cap: number; id: string }[] = [];
    for (const t of teamList) {
      const cap = (t.cap ?? 0) - capGoc;
      while (nganh.length && nganh[nganh.length - 1].cap >= cap) nganh.pop();
      const id = `thuc-hien-sx:${t.id}`;
      sanXuatDong.push({
        id, label: t.ten, icon: "users", module: "to_sx",
        modules: cacKhoaTo, indent: cap,
        parentId: nganh.length ? nganh[nganh.length - 1].id : undefined,
      });
      nganh.push({ cap, id });
    }
  }
  if (sanXuatDong.length) dynamicItems["to-san-xuat"] = sanXuatDong;
  const readableNav = kcsTuCach.kcs ? new Set([...readable, KCS_NAV_KEY]) : readable;
  // Mục "Kho" chỉ cần `kho:read`; tab "Phiếu từ đề nghị" (cần create/view_stock) tự ẩn trong KhoPage.
  const hiddenIds = new Set<string>();


  function renderContent() {
    if (!allowed) {
      return (
        <main className="shell__forbidden">
          <div className="banner banner--error" role="alert">
            <span>Bạn không có quyền truy cập mục này (403).</span>
            <button
              type="button"
              className="btn btn--ghost"
              style={{ padding: "2px 10px" }}
              onClick={() => setActiveId("dashboard")}
            >
              Về Dashboard
            </button>
          </div>
        </main>
      );
    }
    // Khai báo kho: màn CRUD generic + onMutate → refetch item động ngay sau khi tạo/sửa/xoá.
    if (baseId === "khai-bao-kho") {
      return <RebuildCatalogPage key="khai-bao-kho" config={REBUILD_CONFIGS["khai-bao-kho"]} onMutate={reloadKho} />;
    }
    // Kho — MỘT module, chia tab (Đề nghị · Hộp yêu cầu) × (Nhập · Xuất). `quoteTick` là tick
    // CHUNG của kênh SSE: mọi sự kiện kho đều đẩy tick nên bảng tự tươi, không mở EventSource riêng.
    if (baseId === "kho-main") {
      return (
        <KhoPage
          eventTick={quoteTick}
          nhapSeed={navParams?.khoNhapSeed}
          counts={khoCounts}
          onSeen={reloadBadges}
          openRequest={navParams?.khoOpenRequest}
        />
      );
    }
    // Báo cáo kho (kế toán): sổ nhập-xuất + khóa kỳ + export MISA. Gác bằng khoá riêng
    // `bao_cao_kho` ở `allowed`; khoá kỳ bên trong còn hỏi thêm ô chi tiết `close_book` ở máy chủ.
    if (baseId === "kho-baocao") {
      return <KhoBaoCaoPage token={token ?? ""} />;
    }
    // Màn TỒN KHO của 1 kho đã khai báo (bấm item "kho-item:<id>" dưới section "Kho hàng").
    if (baseId === "kho-item") {
      const id = Number(activeId.split(":")[1]);
      const w = khoList.find((x) => x.id === id);
      return (
        <KhoTonKhoPage
          key={`kho-ton-${id}`}
          khoId={id}
          ten={w?.ten ?? "Kho"}
          ma={w?.ma}
          token={token ?? ""}
          navigate={navigate}
          openMatHangKey={navParams?.openMatHangKey ?? null}
          khoOptions={khoList}
        />
      );
    }
    // Bàn "Thực hiện sản xuất" của 1 tổ (bấm node lá "thuc-hien-sx:<teamId>" dưới section Sản xuất).
    // `eventTick` = quoteTick (bump theo MỌI sự kiện SSE) → bàn đang mở tự refetch khi bàn tổ đổi.
    if (baseId === "thuc-hien-sx") {
      const teamId = Number(activeId.split(":")[1]);
      const t = teamList.find((x) => x.id === teamId);
      return (
        <ThucHienSxPage
          key={`thsx-${teamId}`}
          teamId={teamId}
          tenTo={t?.ten}
          laTho={t?.la_tho ?? false}
          eventTick={quoteTick}
          vatTuDeNghiDem={vatTuDeNghiDem}
          dinhKemDem={lsxDinhKemDem}
          onXemCongViec={datCvDangMo}
          onBadgeStale={reloadTeams}
        />
      );
    }
    // Màn KCS theo lệnh — một màn cho mọi người KCS, không theo tổ.
    if (baseId === "kcs") {
      return <KcsTheoLenhPage key="kcs" eventTick={quoteTick} onBadgeStale={reloadTeams} navigate={navigate} />;
    }
    // Id cũ "quy-doi" (màn cặp riêng, đã gộp vào drawer đơn vị) → về đúng màn Đơn vị.
    if (baseId === "quy-doi") {
      return <RebuildCatalogPage key="don-vi" config={REBUILD_CONFIGS["don-vi"]} />;
    }
    // Tiêu chí KCS KHÔNG dùng nền danh mục phẳng: khai theo cây Giai đoạn → Công đoạn → hạng
    // mục kiểm (08/09/2026, `docs/design-kcs-theo-cong-doan.md` mục 5).
    if (baseId === "kcs-tieu-chi") {
      return <KcsKhaiBaoPage key="kcs-tieu-chi" />;
    }
    // Danh mục rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP · Giấy) — 1 trang generic theo config.
    if (REBUILD_CONFIGS[baseId]) {
      return <RebuildCatalogPage key={baseId} config={REBUILD_CONFIGS[baseId]} navigate={navigate} />;
    }
    switch (baseId) {
      case "quy-trinh-kinh-doanh":
        return <QuyTrinhKinhDoanhPage navigate={navigate} />;
      case "phong-ban":
        return <DepartmentsPage />;
      case "nhan-su":
        return <NhanSuPage navigate={navigate} />;
      case "ho-so-cua-toi":
        return <HoSoCuaToiPage navigate={navigate} />;
      case "noi-quy":
        return <NoiQuyPage />;
      case "cham-cong":
        // `eventTick` nhảy theo MỌI sự kiện SSE → tab phiếu đi muộn/về sớm đang mở tự tải lại ngay
        // khi tổ trưởng duyệt/từ chối (không chỉ nhảy badge).
        return (
          <ChamCongPage
            navigate={navigate}
            focusEmployeeId={navParams?.focusEmployeeId}
            openTab={navParams?.chamCongTab}
            onChanged={reloadBadges}
            eventTick={quoteTick}
          />
        );
      case "nghi-phep":
        return <NghiPhepPage onChanged={reloadBadges} focusEmployeeId={navParams?.focusEmployeeId} eventTick={quoteTick} />;
      case "tang-ca":
        // `eventTick` nhảy theo MỌI sự kiện SSE → bảng phiếu đang mở tự tải lại ngay khi bên kia
        // duyệt/từ chối/gửi phiếu (không chỉ nhảy badge).
        return <TangCaPage onChanged={reloadBadges} eventTick={quoteTick} />;
      case "luong":
        return (
          <LuongPage
            navigate={navigate}
            focusEmployeeId={navParams?.focusEmployeeId}
            eventTick={quoteTick}
            openTab={navParams?.luongTab}
          />
        );
      case "khach-hang":
        return <KhachHangPage navigate={navigate} onBadgeStale={reloadBadges} />;
      case "tinh-gia":
        return <TinhGiaPage navigate={navigate} openPhieuId={navParams?.focusPhieuId} />;
      case "bao-gia":
        return (
          <BaoGiaPage
            openQuoteId={navParams?.openQuoteId ?? null}
            navigate={navigate}
            eventTick={quoteTick}
          />
        );
      case "don-hang-ban":
        return <DonHangBanPage navigate={navigate} openOrderId={navParams?.openOrderId ?? null} />;
      case "bao-cao-kinh-doanh":
        return <BaoCaoKinhDoanhPage />;
      case "giao-hang":
        // `eventTick` tăng mỗi sự kiện SSE ⇒ bảng chuyến tự tươi, không phải F5.
        return <GiaoHangPage eventTick={quoteTick} />;
      case "ke-hoach-sx":
        return (
          <KeHoachSXPage
            navigate={navigate}
            openOrderId={navParams?.openSxOrderId ?? null}
            openLsxId={navParams?.openLsxId ?? null}
            eventTick={quoteTick}
            dinhKemDem={lsxDinhKemDem}
            onBadgeStale={reloadBadges}
          />
        );
      case "lenh-san-xuat":
        // Bàn TRA CỨU, chỉ đọc. `eventTick` nhích theo MỌI sự kiện SSE ⇒ bảng tự tươi khi tổ bấm
        // Bắt đầu/Kết thúc — màn tự GỘP 2 giây rồi mới gọi lại, và KHÔNG toast (bảng tra cứu
        // không phải chỗ báo tin). Hồ sơ một lệnh là LỚP PHỦ do chính màn này mở, không phải một
        // trang riêng — `navigate` chỉ để hồ sơ đi tiếp sang màn Đơn hàng bán khi cần lập yêu cầu
        // giao hàng.
        return (
          <LenhSanXuatPage
            eventTick={quoteTick}
            navigate={navigate}
            openHoSoId={navParams?.openHoSoLsxId ?? null}
            openHoSoPv={navParams?.openHoSoPv ?? null}
            openHoSoSeq={navParams?.navSeq ?? null}
          />
        );
      case "theo-doi-san-xuat":
        // Bàn quét TOÀN XƯỞNG (Kanban · Theo máy — 17b; Theo ca · Gantt để chỗ cho 18b), chỉ đọc.
        // Hồ sơ một lệnh là LỚP PHỦ do chính màn này mở (tái dùng `LenhSxHoSoView`, cùng khuôn
        // `lenh-san-xuat`) — không cần `navParams` nào ở đây, màn không có deep-link riêng.
        return <TheoDoiSanXuatPage eventTick={quoteTick} navigate={navigate} />;
      case "ke-hoach-vat-tu":
        return (
          <KeHoachVatTuPage
            navigate={navigate}
            eventTick={quoteTick}
            focusLsxMa={navParams?.focusLsxMa ?? null}
            onSoViec={baoSoViecVatTu}
          />
        );
      // GIỮ NGUYÊN dù màn đang ẩn (`BAI_GHEP_ENABLED = false`): route này hiện không tới được —
      // mục menu bị ẩn nên `MODULES_BY_NAV_ID` không có id `bai-ghep-2` và cổng `allowed` chặn
      // trước khi tới đây. Bỏ `case` đi thì bật cờ lại phải sửa hai chỗ thay vì một.
      case "bai-ghep-2":
        return <BaiGhep2Page navigate={navigate} eventTick={quoteTick} onBadgeStale={reloadBadges} />;
      case "xep-lich":
        return <XepLichPage eventTick={quoteTick} onBadgeStale={reloadBadges} />;
      case "sua-chua-may":
        // `eventTick` nhích theo MỌI sự kiện SSE ⇒ danh sách yêu cầu tự nạp lại khi có lời báo mới
        // hoặc khi người khác vừa tiếp nhận — không để hai người cùng lập phiếu cho một cái máy.
        return <SuaChuaMayPage eventTick={quoteTick} onBadgeStale={reloadBadges} />;
      case "phieu-bao-tri":
        return <PhieuBaoTriPage />;
      case "yeu-cau-mua-hang":
        return (
          <DepartmentPurchaseRequestsPage
            eventTick={quoteTick}
            focusRequestCode={navParams?.focusRequestCode ?? null}
            seedLines={navParams?.purchaseSeedLines ?? null}
            seedPurpose={navParams?.purchaseSeedPurpose ?? null}
            seedHeader={navParams?.purchaseSeedHeader ?? null}
            seedNguon={navParams?.purchaseSeedNguon ?? null}
          />
        );
      case "mua-hang":
        // `focusRequestCode` nối sang cả màn Mua hàng: từ 08/08/2026 màn này có hai tab con và
        // mở mặc định ở tab "Yêu cầu chờ xử lý". Màn nào bấm mã nhảy sang đây (mã `PMH-…` hay
        // `YCMH-…`) thì trang tự chọn đúng tab + đổ mã vào ô tìm — không có dòng này thì người
        // dùng rơi vào tab yêu cầu, không thấy phiếu, tưởng phiếu đã bị xoá.
        return (
          <PurchaseRequestsPage
            navigate={navigate}
            eventTick={quoteTick}
            focusRequestCode={navParams?.focusRequestCode ?? null}
            onDataRefreshed={markThuMuaNotificationsRead}
          />
        );
      case "nha-cung-cap":
        return <SuppliersPage eventTick={quoteTick} />;
      // Nhóm con "Kế toán thu mua" đã BỎ ngày 12/08/2026 — ba màn của nó nay đứng ngang hàng với
      // Phiếu thu / Công nợ phải thu. Không còn id cha nên cũng không cần nhánh rơi-vào-con-đầu.
      case "ke-toan-don-mua-hang":
        return (
          <AccountingPurchaseInboxPage
            navigate={navigate}
            eventTick={quoteTick}
            focusRequestCode={navParams?.focusRequestCode ?? null}
            onDataRefreshed={markKeToanNotificationsRead}
          />
        );
      case "ke-toan-phieu-chi":
        return (
          <PaymentVouchersPage
            navigate={navigate}
            eventTick={quoteTick}
            focusQuery={navParams?.focusVoucherQuery ?? null}
          />
        );
      case "ke-toan-cong-no":
        return <AccountingPayablesPage navigate={navigate} eventTick={quoteTick} />;
      case "ke-toan-cong-no-phai-thu":
        return <AccountingReceivablesPage navigate={navigate} eventTick={quoteTick} />;
      case "ke-toan-bao-cao":
        return <BaoCaoKeToanPage navigate={navigate} />;
      case "ke-toan-tai-khoan-ngan-hang":
        return <AccountingBankAccountsPage />;
      case "tai-san":
        return <TaiSanPage />;
      case "ke-toan-phieu-thu":
        return (
          <PaymentReceiptsPage
            navigate={navigate}
            eventTick={quoteTick}
            focusQuery={navParams?.focusReceiptQuery ?? null}
          />
        );
      case "nhat-ky":
        return <ActivityLogPage />;
      default:
        return <DashboardPage />;
    }
  }

  return (
    <PermissionsProvider caps={caps} onReload={taiLaiQuyenTuMan} kcs={kcsTuCach.kcs} truongKcs={kcsTuCach.truongKcs}>
      <div className={`shell${navOpen ? " is-nav-open" : ""}`}>
        {/* Màn che sau ngăn kéo — chỉ tồn tại khi ngăn kéo mở (màn hẹp). */}
        {navOpen && (
          <button
            type="button"
            className="shell__scrim"
            aria-label="Đóng menu điều hướng"
            onClick={() => setNavOpen(false)}
          />
        )}
        <Sidebar
          activeId={activeId}
          onSelect={(id) => navigate(id)}
          readable={readableNav}
          itemChildren={itemChildren}
          dynamicItems={dynamicItems}
          badges={badges}
          hiddenIds={hiddenIds}
          onClose={() => setNavOpen(false)}
        />
        <div className="shell__main">
          <Topbar
            onOpenProfile={() => navigate("ho-so-cua-toi")}
            onToggleNav={() => setNavOpen((v) => !v)}
            navOpen={navOpen}
          />
          <div className="shell__content">{renderContent()}</div>
        </div>
        {/* Toast real-time luồng gửi duyệt — nổi góc trên-phải, tự tắt sau 6s. */}
        {toasts.length > 0 && (
          <div
            aria-live="polite"
            className="apx-toastwrap"
            style={{
              position: "fixed", top: 16, right: 16, zIndex: 9999,
              display: "flex", flexDirection: "column", gap: 8, maxWidth: 340,
            }}
          >
            {toasts.map((t) => (
              <div
                key={t.id}
                role="status"
                onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
                style={{
                  padding: "10px 14px", borderRadius: 10, cursor: "pointer",
                  color: "#fff", fontSize: 13, fontWeight: 600, lineHeight: 1.35,
                  boxShadow: "0 10px 28px rgba(0,0,0,.28)",
                  background:
                    t.tone === "ok" ? "#1f8a52" : t.tone === "warn" ? "#b4432b" : "#2b6cb0",
                }}
              >
                {t.text}
              </div>
            ))}
          </div>
        )}
      </div>
    </PermissionsProvider>
  );
}
