// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, connectQuoteEvents, type PinnedCustomer } from "../api/client";
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
import { TinhGiaPage } from "../pages/TinhGiaPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/DepartmentsPage";
import { KhachHangPage } from "../pages/KhachHangPage";
import { QuyTrinhKinhDoanhPage } from "../pages/QuyTrinhKinhDoanhPage";
import { ChamCongPage } from "../pages/ChamCongPage";
import { NghiPhepPage } from "../pages/NghiPhepPage";
import { LuongPage } from "../pages/LuongPage";
import { HoSoCuaToiPage } from "../pages/HoSoCuaToiPage";
import { NhanSuPage } from "../pages/NhanSuPage";
import { RebuildCatalogPage } from "../pages/RebuildCatalogPage";
import { KhoHangView } from "../pages/KhoHangView";
// Danh mục rebuild (config .tsx — render pill JSX)
import { REBUILD_CONFIGS } from "../pages/rebuildCatalogConfigs";
import { DepartmentPurchaseRequestsPage } from "../pages/DepartmentPurchaseRequestsPage";
import { PurchaseRequestsPage } from "../pages/PurchaseRequestsPage";
import { SuppliersPage } from "../pages/SuppliersPage";
import { AccountingPurchaseInboxPage } from "../pages/AccountingPurchaseInboxPage";
import { PaymentVouchersPage } from "../pages/PaymentVouchersPage";
import { PaymentReceiptsPage } from "../pages/PaymentReceiptsPage";
import { AccountingBankAccountsPage } from "../pages/AccountingBankAccountsPage";
import { MODULES_BY_NAV_ID, Sidebar, type NavItem } from "./Sidebar";
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
  /** Pre-select this estimate when creating a quotation. */
  estimateId?: number;
  /** Open this estimate's detail on the Tính giá screen. */
  openEstimateId?: number | null;
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
  /** Liên thông Đơn hàng → bàn Kế hoạch SX: mở thẳng đơn này ở hàng chờ / danh sách lệnh. */
  openSxOrderId?: number;
}

export type NavigateFn = (id: string, params?: NavParams) => void;

export function AppShell() {
  const { token } = useAuth();
  const [activeId, setActiveId] = useState("dashboard");
  const [navParams, setNavParams] = useState<NavParams | null>(null);
  const [readable, setReadable] = useState<Set<string> | null>(null);
  const [caps, setCaps] = useState<Capabilities>(new Map());
  // Badge số theo nav id (vd "nghi-phep": số đơn chờ duyệt) — chỉ người có quyền duyệt.
  const [badges, setBadges] = useState<Record<string, number>>({});
  // Kho đã khai báo → đổ menu con ĐỘNG dưới "Kho hàng" (Cấu hình danh mục). Refetch khi
  // khai báo/sửa/xoá kho (onMutate màn khai báo) → navbar cập nhật NGAY, không cần refresh.
  const [khoList, setKhoList] = useState<{ id: number; ma: string; ten: string }[]>([]);
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
  const lastAdvancePending = useRef(0);
  const pushToast = useCallback((text: string, tone: "ok" | "warn" | "info") => {
    const id = ++toastSeq.current;
    setToasts((prev) => [...prev, { id, text, tone }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);

  // Single navigation entrypoint: switches the active screen AND carries an optional
  // payload (pinned customer / document to open). Every param object is fresh so the
  // target screen's effect re-fires even when re-navigating to the same screen.
  const navigate = useCallback<NavigateFn>((id, params) => {
    setActiveId(id);
    setNavParams(params ?? null);
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .myAccess(token)
      .then((acc) => {
        if (cancelled) return;
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

  // Badge Nghỉ phép: số đơn chờ duyệt (endpoint tự trả null nếu người gọi không có quyền
  // duyệt → không hiện badge). NghiPhepPage gọi lại sau mỗi thao tác để badge cập nhật ngay.
  const reloadBadges = useCallback(() => {
    if (!token || readable === null) return;
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
  }, [token, readable]);
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
    if (!token || readable === null || !(readable.has("bao_gia") || readable.has("don_hang_ban") || readable.has("khach_hang") || readable.has("luong") || readable.has("san_xuat"))) return;
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
      } else if (readable.has("don_hang_ban") && e.type === "order_decision") {
        pushToast(
          e.decision === "approved" ? `✓ Đơn ${e.code} đã được duyệt` : `✕ Đơn ${e.code} bị từ chối`,
          e.decision === "approved" ? "ok" : "warn",
        );
        reloadBadges();
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
      } else if (readable.has("san_xuat") && (e.type === "order_ordered" || e.type === "lsx_changed")) {
        // Sale bấm "Chuyển xuống sản xuất" → đơn rơi vào hàng chờ Kế hoạch NGAY (badge nhảy + toast);
        // Kế hoạch tạo/xoá lệnh → hàng chờ tự co lại. Nội dung do màn tự refetch qua `quoteTick`.
        api.lsx
          .hangCho(token)
          .then((r) => {
            setBadges((prev) => ({ ...prev, "ke-hoach-sx": r.total }));
            if (e.type === "order_ordered") {
              pushToast(`🔔 Đơn ${e.code ?? ""} vừa chuyển xuống sản xuất`.trim(), "info");
            }
          })
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
      }
    });
    return close;
  }, [token, readable, reloadBadges, pushToast]);

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
  // "kho-item:<id>" = màn 1 kho (menu con động) — gác cùng quyền `kho` với mục cha "Kho hàng".
  const moduleKeys =
    MODULES_BY_NAV_ID[baseId] ??
    (baseId === "kho-item" ? ["kho"] : undefined);
  const allowed = moduleKeys != null && moduleKeys.some((moduleKey) => readable.has(moduleKey));
  const itemChildren: Record<string, { id: string; label: string }[]> = {};
  // Kho đã khai báo → item ĐỘNG dưới SECTION "Kho hàng" (id section = "kho-hang"). Bấm 1 kho → màn tạm.
  const dynamicItems: Record<string, NavItem[]> = {};
  if (khoList.length) {
    dynamicItems["kho-hang"] = khoList.map((w): NavItem => ({
      id: `kho-item:${w.id}`, label: w.ten, icon: "warehouse", module: "kho",
    }));
  }

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
    // Màn TẠM cho 1 kho đã khai báo (bấm item "kho-item:<id>" dưới section "Kho hàng").
    if (baseId === "kho-item") {
      const id = Number(activeId.split(":")[1]);
      const w = khoList.find((x) => x.id === id);
      return <KhoHangView ten={w?.ten ?? "Kho"} ma={w?.ma} />;
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
      case "cham-cong":
        return <ChamCongPage navigate={navigate} focusEmployeeId={navParams?.focusEmployeeId} />;
      case "nghi-phep":
        return <NghiPhepPage onChanged={reloadBadges} focusEmployeeId={navParams?.focusEmployeeId} />;
      case "luong":
        return <LuongPage focusEmployeeId={navParams?.focusEmployeeId} eventTick={quoteTick} />;
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
            eventTick={quoteTick}
            onBadgeStale={reloadBadges}
          />
        );
      case "bai-ghep":
        return <BaiGhepPage eventTick={quoteTick} onBadgeStale={reloadBadges} />;
      case "yeu-cau-mua-hang":
        return (
          <DepartmentPurchaseRequestsPage
            focusRequestCode={navParams?.focusRequestCode ?? null}
          />
        );
      case "mua-hang":
        return <PurchaseRequestsPage navigate={navigate} />;
      case "nha-cung-cap":
        return <SuppliersPage />;
      case "ke-toan-yeu-cau-mua":
        return <AccountingPurchaseInboxPage navigate={navigate} />;
      case "ke-toan-phieu-chi":
        return (
          <PaymentVouchersPage
            navigate={navigate}
            focusQuery={navParams?.focusVoucherQuery ?? null}
          />
        );
      case "ke-toan-phieu-thu":
        return (
          <PaymentReceiptsPage
            navigate={navigate}
            focusQuery={navParams?.focusReceiptQuery ?? null}
          />
        );
      case "ke-toan-tai-khoan":
        return <AccountingBankAccountsPage />;
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
