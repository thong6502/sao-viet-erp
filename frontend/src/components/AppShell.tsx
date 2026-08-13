// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  connectQuoteEvents,
  type HangLoai,
  type ModuleNotificationChannel,
  type PinnedCustomer,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import {
  buildCapabilities,
  PermissionsProvider,
  type Capabilities,
} from "../auth/permissions";
import { ActivityLogPage } from "../pages/ActivityLogPage";
import { BaoGiaPage } from "../pages/BaoGiaPage";
import { DonHangBanPage } from "../pages/DonHangBanPage";
import { KeHoachSXPage } from "../pages/KeHoachSXPage";
import { BaiGhepPage } from "../pages/BaiGhepPage";
import { XepLichPage } from "../pages/XepLichPage";
import { TinhGiaPage } from "../pages/TinhGiaPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/DepartmentsPage";
import { KhachHangPage } from "../pages/KhachHangPage";
import { QuyTrinhKinhDoanhPage } from "../pages/QuyTrinhKinhDoanhPage";
import { ChamCongPage } from "../pages/ChamCongPage";
import { NghiPhepPage } from "../pages/NghiPhepPage";
import { TangCaPage } from "../pages/TangCaPage";
import { LuongPage } from "../pages/LuongPage";
import { HoSoCuaToiPage } from "../pages/HoSoCuaToiPage";
import { NoiQuyPage } from "../pages/NoiQuyPage";
import { NhanSuPage } from "../pages/NhanSuPage";
import { RebuildCatalogPage } from "../pages/RebuildCatalogPage";
import { KhoTonKhoPage } from "../pages/KhoTonKhoPage";
import { KhoPage } from "../pages/KhoPage";
import { KhoBaoCaoPage } from "../pages/KhoBaoCaoPage";
import type { KhoNhapSeed } from "../pages/KhoDeNghiPage";

// Danh mục rebuild (config .tsx — render pill JSX)
import { REBUILD_CONFIGS } from "../pages/rebuildCatalogConfigs";
import { DepartmentPurchaseRequestsPage } from "../pages/DepartmentPurchaseRequestsPage";
import { PurchaseRequestsPage } from "../pages/PurchaseRequestsPage";
import { SuppliersPage } from "../pages/SuppliersPage";
import { AccountingPayablesPage } from "../pages/AccountingPayablesPage";
import { AccountingReceivablesPage } from "../pages/AccountingReceivablesPage";
import { AccountingPurchaseInboxPage } from "../pages/AccountingPurchaseInboxPage";
import { PaymentVouchersPage } from "../pages/PaymentVouchersPage";
import { PaymentReceiptsPage } from "../pages/PaymentReceiptsPage";
import { AccountingBankAccountsPage } from "../pages/AccountingBankAccountsPage";
import {
  AUTHENTICATED_NAV_IDS,
  MODULES_BY_NAV_ID,
  Sidebar,
  type NavItem,
} from "./Sidebar";
import { Topbar } from "./Topbar";

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
  /** Liên thông: mở màn Yêu cầu mua hàng (YCMH) lọc + tô sáng đúng mã phiếu này. */
  focusRequestCode?: string;
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
}

export type NavigateFn = (id: string, params?: NavParams) => void;

const MODULE_NOTIFICATION_NAV: Record<ModuleNotificationChannel, string> = {
  thu_mua: "mua-hang",
  ke_toan: "ke-toan-don-mua-hang",
};

export function AppShell() {
  const { token, user } = useAuth();
  const [activeId, setActiveId] = useState("dashboard");
  const [navParams, setNavParams] = useState<NavParams | null>(null);
  const [readable, setReadable] = useState<Set<string> | null>(null);
  const [caps, setCaps] = useState<Capabilities>(new Map());
  // Badge số theo nav id (vd "nghi-phep": số đơn chờ duyệt) — chỉ người có quyền duyệt.
  const [badges, setBadges] = useState<Record<string, number>>({});
  // Kho đã khai báo → đổ menu con ĐỘNG dưới "Kho hàng" (Cấu hình danh mục). Refetch khi
  // khai báo/sửa/xoá kho (onMutate màn khai báo) → navbar cập nhật NGAY, không cần refresh.
  const [khoList, setKhoList] = useState<{ id: number; ma: string; ten: string }[]>([]);
  // Số yêu cầu ĐÃ DUYỆT chờ kho lập phiếu, theo chiều — badge cạnh nút Nhập/Xuất trong KhoPage.
  const [khoCounts, setKhoCounts] = useState<{ nhap: number; xuat: number }>({ nhap: 0, xuat: 0 });
  // Chuông Topbar: số đơn nghỉ CỦA TÔI vừa được quyết mà chưa xem (mọi NV).
  const [leaveUnseen, setLeaveUnseen] = useState(0);
  // Real-time luồng gửi duyệt (SSE): toast nổi + mốc 'chờ tôi duyệt' gần nhất để chỉ toast khi TĂNG.
  // `quoteTick` tăng mỗi event → truyền xuống BaoGiaPage cho nó refetch list/stats. Kênh SSE vẫn
  // DUY NHẤT ở đây (trang con mở kênh riêng = tốn kết nối + lệch trạng thái).
  const [quoteTick, setQuoteTick] = useState(0);
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
  const lastElPending = useRef(0);
  const activeIdRef = useRef(activeId);
  const moduleNotificationRevision = useRef<Record<ModuleNotificationChannel, number>>({
    thu_mua: 0,
    ke_toan: 0,
  });
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
  // payload (pinned customer / document to open). Every param object is fresh so the
  // target screen's effect re-fires even when re-navigating to the same screen.
  const navigate = useCallback<NavigateFn>((id, params) => {
    setActiveId(id);
    setNavParams(params ?? null);
  }, []);

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .myAccess(token)
      .then((acc) => {
        if (cancelled) return;
        // Các API "của tôi" tự giới hạn theo hồ sơ đăng nhập, không cần cấp
        // `luong:read` (quyền quản trị). Module ảo này chỉ mở cửa menu tự phục vụ.
        // `self_service` KHÔNG còn được nhét thêm ở đây (10/08/2026): nó là ô quyền thật, do
        // máy chủ trả về như mọi module khác. Nhét tay = giao diện tưởng ai cũng có, bấm vào
        // thì API trả 403 — hai nơi nói hai kiểu.
        setReadable(new Set(acc.modules));
        setCaps(buildCapabilities(acc.permissions));
      })
      .catch(() => {
        if (cancelled) return;
        setReadable(new Set());
        setCaps(new Map());
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

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
          setLeaveUnseen(s.my_decided_unseen ?? 0);
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
    if (readable.has("di_muon")) {
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
    // Badge Kế hoạch SX = số đơn Sale đã chuyển xuống mà CÒN dòng chưa lên lệnh (hàng chờ).
    if (readable.has("san_xuat")) {
      api.lsx
        .hangCho(token)
        .then((r) => setBadges((prev) => ({ ...prev, "ke-hoach-sx": r.total })))
        .catch(() => {});
      // Badge Bài ghép = số LSX sẵn sàng đang chờ ghép (pool).
      api.baiGhep
        .hangCho(token)
        .then((r) => setBadges((prev) => ({ ...prev, "bai-ghep": r.total })))
        .catch(() => {});
      // Badge Xếp lịch = số nguồn (LSX / bài ghép) đang chờ xếp (chưa đưa vào kế hoạch).
      api.xepLich
        .hangCho(token)
        .then((r) => setBadges((prev) => ({ ...prev, "xep-lich-cong-doan": r.total })))
        .catch(() => {});
    }
    // Badge Lương = số đề nghị tạm ứng đang chờ TÔI duyệt (0 với người không có quyền duyệt).
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
          lastKhoPending.current = c.nhap + c.xuat;
          setKhoCounts(c);
          setBadges((prev) => ({ ...prev, "kho-main": c.nhap + c.xuat }));
        })
        .catch(() => {});
    }
  }, [token, readable, reloadModuleNotificationBadges]);
  useEffect(() => {
    reloadBadges();
    // Refetch khi đổi màn — cả 2 endpoint đều rất nhẹ, giữ badge tươi sau khi thao tác.
  }, [reloadBadges, activeId]);

  // Danh sách kho cho menu con động (chỉ người có quyền `kho`). Gọi lại sau mỗi lần khai báo kho.
  const reloadKho = useCallback(() => {
    if (!token || readable === null || !readable.has("kho")) return;
    crud("/api/kho")
      .list(token, { active: true })
      .then((r) => setKhoList(r.items.map((w) => ({ id: Number(w.id), ma: String(w.ma), ten: String(w.ten) }))))
      .catch(() => {});
  }, [token, readable]);
  useEffect(() => { reloadKho(); }, [reloadKho]);

  // Real-time luồng gửi duyệt (CLAUDE.md "gửi nội bộ = real-time"): mở 1 kênh SSE sau đăng nhập →
  // GĐ thấy 'chờ duyệt' ngay khi Sale trình; Sale thấy 'đã duyệt/từ chối' ngay khi GĐ quyết. Chỉ mở
  // cho người có quyền xem Báo giá (người khác không nhận tín hiệu). Đóng khi logout/đổi phạm vi.
  useEffect(() => {
    if (!token || readable === null || !(readable.has("bao_gia") || readable.has("don_hang_ban") || readable.has("khach_hang") || readable.has("luong") || readable.has("san_xuat") || readable.has("kho") || readable.has("tang_ca") || readable.has("di_muon") || readable.has("thu_mua") || readable.has("yeu_cau_mua_hang") || readable.has("ke_toan") ||
      readable.has("phieu_chi") || readable.has("phieu_thu"))) return;

    const close = connectQuoteEvents(token, (e) => {
      // Mọi event luồng duyệt → đẩy tick: màn Báo giá đang mở tự tải lại bảng + số đếm tab.
      setQuoteTick((n) => n + 1);
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
        readable.has("san_xuat") &&
        (e.type === "order_ordered" ||
          e.type === "lsx_changed" ||
          e.type === "bai_ghep_changed" ||
          e.type === "xep_lich_changed")
      ) {
        // Sale "Chuyển xuống sản xuất" → hàng chờ Kế hoạch nhảy (badge + toast); Kế hoạch/ghép bài/
        // xếp lịch đổi → 3 badge khối Sản xuất co giãn NGAY. Nội dung màn tự refetch qua `quoteTick`.
        api.lsx
          .hangCho(token)
          .then((r) => {
            setBadges((prev) => ({ ...prev, "ke-hoach-sx": r.total }));
            if (e.type === "order_ordered") {
              pushToast(`🔔 Đơn ${e.code ?? ""} vừa chuyển xuống sản xuất`.trim(), "info");
            }
          })
          .catch(() => {});
        api.baiGhep
          .hangCho(token)
          .then((r) => setBadges((prev) => ({ ...prev, "bai-ghep": r.total })))
          .catch(() => {});
        api.xepLich
          .hangCho(token)
          .then((r) => setBadges((prev) => ({ ...prev, "xep-lich-cong-doan": r.total })))
          .catch(() => {});
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
            : "✕ Phiếu tăng ca của bạn bị từ chối",
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
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
      } else if (e.type === "el_decision") {
        // NV nộp phiếu đi muộn / về sớm nhận quyết định của tổ trưởng — đẩy riêng tới đúng người.
        pushToast(
          e.decision === "approved"
            ? "✓ Phiếu đi muộn / về sớm của bạn đã được duyệt"
            : "✕ Phiếu đi muộn / về sớm của bạn bị từ chối",
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
      } else if (readable.has("di_muon") && e.type === "el_pending_changed") {
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
            : `Đơn mua hàng${e.code ? " " + e.code : ""} bị từ chối`,
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
      } else if (readable.has("kho") && e.type === "stock_request_pending_changed") {
        // Yêu cầu kho đổi (tạo/duyệt/cấp…) → cập nhật badge Nhập/Xuất; toast thủ kho khi tổng
        // "chờ cấp" TĂNG (có việc mới). quoteTick ở đầu handler đã lo refetch 2 màn kho đang mở.
        api.kho.deNghi
          .counts(token)
          .then((c) => {
            const total = c.nhap + c.xuat;
            setKhoCounts(c);
            setBadges((prev) => ({ ...prev, "kho-main": total }));
            // Toast "có việc mới" CHỈ cho người XỬ LÝ kho (lập phiếu / xem tồn), KHÔNG gửi người TẠO.
            const canProcess = !!(caps.get("kho")?.can_create || caps.get("kho")?.can_view_stock);
            if (total > lastKhoPending.current && canProcess && user?.id !== e.nguoi_tao_id) {
              const dir = e.loai === "XUAT" ? "xuất" : "nhập";
              pushToast(`🔔 Có yêu cầu ${dir} mới chờ cấp`, "info", 9000);
            }
            lastKhoPending.current = total;
          })
          .catch(() => {});
      }
    });
    return close;
  }, [token, readable, reloadBadges, reloadModuleNotificationBadges, pushToast, caps, user]);

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

  // Bấm chuông → mở Nghỉ phép (Đơn của tôi) + đánh dấu đã xem → đóng chuông.
  const openLeaveFromBell = useCallback(() => {
    navigate("nghi-phep");
    if (token) api.leaves.markSeen(token).then(reloadBadges).catch(() => {});
  }, [navigate, token, reloadBadges]);

  if (readable === null) {
    return (
      <div className="shell__center" role="status" aria-live="polite">
        Đang tải…
      </div>
    );
  }

  const baseId = activeId.split(":")[0];
  // "Kho hàng" (kho vật lý: tồn/phiếu/ngưỡng) là VIỆC CỦA KHO, không phải của người đề nghị.
  // Vai chỉ có `kho:read` (để tạo đề nghị) KHÔNG được thấy — chặn bằng `can_view_stock`, để
  // ông sản xuất không nhìn thấy tồn/giá/lô của kho.
  const canViewStock = !!caps.get("kho")?.can_view_stock;
  // Báo cáo kho (kế toán) — chỉ vai có `close_book` (kế toán kho + GĐ) mới vào.
  const canCloseBook = !!caps.get("kho")?.can_close_book;
  // "kho-item:<id>" = màn Tồn kho của 1 kho — gác `kho` + `view_stock`.
  const isKhoView = baseId === "kho-item";
  const moduleKeys = MODULES_BY_NAV_ID[baseId] ?? (isKhoView ? ["kho"] : undefined);
  const allowed =
    AUTHENTICATED_NAV_IDS.has(baseId) ||
    (moduleKeys != null &&
      moduleKeys.some((moduleKey) => readable.has(moduleKey)) &&
      (baseId !== "kho-item" || canViewStock) &&
      (baseId !== "kho-baocao" || canCloseBook));

  const itemChildren: Record<string, { id: string; label: string }[]> = {};
  // Kho đã khai báo → item ĐỘNG dưới SECTION "Kho hàng" (id section = "kho-hang"). Bấm 1 kho → màn tạm.
  // Chỉ đổ khi có `can_view_stock`; thiếu quyền → section "Kho hàng" rỗng nên tự ẩn.
  const dynamicItems: Record<string, NavItem[]> = {};
  if (khoList.length && canViewStock) {
    dynamicItems["kho-hang"] = khoList.map((w): NavItem => ({
      id: `kho-item:${w.id}`, label: w.ten, icon: "warehouse", module: "kho",
    }));
  }
  // Mục "Kho" chỉ cần `kho:read`; tab "Phiếu từ đề nghị" (cần create/view_stock) tự ẩn trong KhoPage.
  const hiddenIds = new Set<string>();
  // "Báo cáo kho" gắn module `kho` (để qua gate readable) nhưng CHỈ kế toán (close_book) thấy.
  if (!canCloseBook) hiddenIds.add("kho-baocao");


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
      return <KhoPage eventTick={quoteTick} nhapSeed={navParams?.khoNhapSeed} counts={khoCounts} />;
    }
    // Báo cáo kho (kế toán): sổ nhập-xuất + khóa kỳ + export MISA. Gác `close_book` ở `allowed`.
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
        />
      );
    }
    // Id cũ "quy-doi" (màn cặp riêng, đã gộp vào drawer đơn vị) → về đúng màn Đơn vị.
    if (baseId === "quy-doi") {
      return <RebuildCatalogPage key="don-vi" config={REBUILD_CONFIGS["don-vi"]} />;
    }
    // Danh mục rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP · Giấy) — 1 trang generic theo config.
    if (REBUILD_CONFIGS[baseId]) {
      return <RebuildCatalogPage key={baseId} config={REBUILD_CONFIGS[baseId]} />;
    }
    switch (baseId) {
      case "quy-trinh-kinh-doanh":
        return <QuyTrinhKinhDoanhPage navigate={navigate} />;
      case "phong-ban":
        return <DepartmentsPage />;
      case "nhan-su":
        return <NhanSuPage navigate={navigate} />;
      case "ho-so-cua-toi":
        return <HoSoCuaToiPage />;
      case "noi-quy":
        return <NoiQuyPage />;
      case "cham-cong":
        // `eventTick` nhảy theo MỌI sự kiện SSE → tab phiếu đi muộn/về sớm đang mở tự tải lại ngay
        // khi tổ trưởng duyệt/từ chối (không chỉ nhảy badge).
        return (
          <ChamCongPage
            navigate={navigate}
            focusEmployeeId={navParams?.focusEmployeeId}
            onChanged={reloadBadges}
            eventTick={quoteTick}
          />
        );
      case "nghi-phep":
        return <NghiPhepPage onChanged={reloadBadges} focusEmployeeId={navParams?.focusEmployeeId} />;
      case "tang-ca":
        // `eventTick` nhảy theo MỌI sự kiện SSE → bảng phiếu đang mở tự tải lại ngay khi bên kia
        // duyệt/từ chối/gửi phiếu (không chỉ nhảy badge).
        return <TangCaPage onChanged={reloadBadges} eventTick={quoteTick} />;
      case "luong":
        return (
          <LuongPage
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
      case "ke-hoach-sx":
        return (
          <KeHoachSXPage
            navigate={navigate}
            openOrderId={navParams?.openSxOrderId ?? null}
            openLsxId={navParams?.openLsxId ?? null}
            eventTick={quoteTick}
            onBadgeStale={reloadBadges}
          />
        );
      case "bai-ghep":
        return <BaiGhepPage navigate={navigate} eventTick={quoteTick} onBadgeStale={reloadBadges} />;
      case "xep-lich-cong-doan":
        return <XepLichPage navigate={navigate} eventTick={quoteTick} onBadgeStale={reloadBadges} />;
      case "yeu-cau-mua-hang":
        return (
          <DepartmentPurchaseRequestsPage
            eventTick={quoteTick}
            focusRequestCode={navParams?.focusRequestCode ?? null}
            seedLines={navParams?.purchaseSeedLines ?? null}
            seedPurpose={navParams?.purchaseSeedPurpose ?? null}
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
      case "ke-toan-tai-khoan-ngan-hang":
        return <AccountingBankAccountsPage />;
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
    <PermissionsProvider caps={caps}>
      <div className="shell">
        <Sidebar
          activeId={activeId}
          onSelect={(id) => navigate(id)}
          readable={readable}
          itemChildren={itemChildren}
          dynamicItems={dynamicItems}
          badges={badges}
          hiddenIds={hiddenIds}
        />
        <div className="shell__main">
          <Topbar onOpenProfile={() => navigate("ho-so-cua-toi")} leaveUnseen={leaveUnseen} onOpenLeave={openLeaveFromBell} />
          <div className="shell__content">{renderContent()}</div>
        </div>
        {/* Toast real-time luồng gửi duyệt — nổi góc trên-phải, tự tắt sau 6s. */}
        {toasts.length > 0 && (
          <div
            aria-live="polite"
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
