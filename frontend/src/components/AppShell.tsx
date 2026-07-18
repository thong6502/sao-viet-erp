// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, connectQuoteEvents, type PinnedCustomer, type WarehouseOption } from "../api/client";
import { useAuth } from "../auth/useAuth";
import {
  buildCapabilities,
  PermissionsProvider,
  type Capabilities,
} from "../auth/permissions";
import { ActivityLogPage } from "../pages/ActivityLogPage";
import { BaoGiaPage } from "../pages/BaoGiaPage";
import { DonHangBanPage } from "../pages/DonHangBanPage";
import { TinhGiaPage } from "../pages/TinhGiaPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/DepartmentsPage";
import { KhachHangPage } from "../pages/KhachHangPage";
import { ChamCongPage } from "../pages/ChamCongPage";
import { NghiPhepPage } from "../pages/NghiPhepPage";
import { LuongPage } from "../pages/LuongPage";
import { HoSoCuaToiPage } from "../pages/HoSoCuaToiPage";
import { NhanSuPage } from "../pages/NhanSuPage";
import { RebuildCatalogPage } from "../pages/RebuildCatalogPage";
// Danh mục rebuild (config .tsx — render pill JSX)
import { REBUILD_CONFIGS } from "../pages/rebuildCatalogConfigs";
import { DepartmentPurchaseRequestsPage } from "../pages/DepartmentPurchaseRequestsPage";
import { PurchaseRequestsPage } from "../pages/PurchaseRequestsPage";
import { SuppliersPage } from "../pages/SuppliersPage";
import { AccountingPurchaseInboxPage } from "../pages/AccountingPurchaseInboxPage";
import { PaymentVouchersPage } from "../pages/PaymentVouchersPage";
import { PaymentReceiptsPage } from "../pages/PaymentReceiptsPage";
import { AccountingBankAccountsPage } from "../pages/AccountingBankAccountsPage";
import { WarehousesCatalogPage } from "../pages/WarehousesCatalogPage";
import { WarehouseItemsPage } from "../pages/WarehouseItemsPage";
import { KhoConfigPage } from "../pages/KhoConfigPage";
import { KhoBaoCaoPage } from "../pages/KhoBaoCaoPage";
import { KhoKiemKePage } from "../pages/KhoKiemKePage";
import { MODULES_BY_NAV_ID, Sidebar } from "./Sidebar";
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
}

export type NavigateFn = (id: string, params?: NavParams) => void;

/** Nav id kho con: "kho-hang:<warehouseId>" → id kho; parent "kho-hang" → null. */
function warehouseIdOf(navId: string): number | null {
  const [base, wid] = navId.split(":");
  if (base !== "kho-hang" || !wid || !/^\d+$/.test(wid)) return null;
  return Number(wid);
}

export function AppShell() {
  const { token } = useAuth();
  const [activeId, setActiveId] = useState("dashboard");
  const [navParams, setNavParams] = useState<NavParams | null>(null);
  const [readable, setReadable] = useState<Set<string> | null>(null);
  const [caps, setCaps] = useState<Capabilities>(new Map());
  // Các kho admin đã cấu hình → menu con động dưới "Tồn kho" trong sidebar.
  const [warehouses, setWarehouses] = useState<WarehouseOption[]>([]);
  // Badge số theo nav id (vd "nghi-phep": số đơn chờ duyệt) — chỉ người có quyền duyệt.
  const [badges, setBadges] = useState<Record<string, number>>({});
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

  // Nạp/refresh danh sách kho (cho menu con sidebar) khi có quyền `kho`.
  useEffect(() => {
    if (!token || readable === null || !readable.has("kho")) return;
    let cancelled = false;
    api.warehouseItems
      .options(token)
      .then((ws) => !cancelled && setWarehouses(ws))
      .catch(() => !cancelled && setWarehouses([]));
    return () => {
      cancelled = true;
    };
  }, [token, readable, activeId]);

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
  }, [token, readable]);
  useEffect(() => {
    reloadBadges();
    // Refetch khi đổi màn — cả 2 endpoint đều rất nhẹ, giữ badge tươi sau khi thao tác.
  }, [reloadBadges, activeId]);

  // Real-time luồng gửi duyệt (CLAUDE.md "gửi nội bộ = real-time"): mở 1 kênh SSE sau đăng nhập →
  // GĐ thấy 'chờ duyệt' ngay khi Sale trình; Sale thấy 'đã duyệt/từ chối' ngay khi GĐ quyết. Chỉ mở
  // cho người có quyền xem Báo giá (người khác không nhận tín hiệu). Đóng khi logout/đổi phạm vi.
  useEffect(() => {
    if (!token || readable === null || !(readable.has("bao_gia") || readable.has("don_hang_ban") || readable.has("khach_hang"))) return;
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
        pushToast(`🔔 Đơn ${e.code} đã đủ cọc — chốt được rồi`, "info");
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
      } else if (readable.has("khach_hang") && e.type === "care_due") {
        // Tới giờ hẹn → ting người phụ trách: toast + badge "Khách hàng" (số việc đến hạn) tự nhảy.
        pushToast(`🔔 Tới hẹn chăm sóc: ${e.customer}${e.note ? " — " + e.note : ""}`, "info");
        reloadBadges();
      } else if (readable.has("khach_hang") && e.type === "care_assigned") {
        pushToast(`📋 Bạn có hẹn chăm sóc mới: ${e.customer}${e.note ? " — " + e.note : ""}`, "info");
        reloadBadges();
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
  const moduleKeys = MODULES_BY_NAV_ID[baseId];
  const allowed = moduleKeys != null && moduleKeys.some((moduleKey) => readable.has(moduleKey));
  // Menu con động: các kho đã cấu hình gắn dưới mục "Kho hàng".
  const itemChildren = {
    "kho-hang": warehouses.map((w) => ({ id: `kho-hang:${w.id}`, label: w.name })),
  };

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
    // Danh mục rebuild (Máy · Vật liệu Kho · Công đoạn · Loại SP · Giấy) — 1 trang generic theo config.
    if (REBUILD_CONFIGS[baseId]) {
      return <RebuildCatalogPage key={baseId} config={REBUILD_CONFIGS[baseId]} />;
    }
    switch (baseId) {
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
        return <LuongPage focusEmployeeId={navParams?.focusEmployeeId} />;
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
      case "cau-hinh-kho":
        return <WarehousesCatalogPage />;
      case "kho-cauhinh-phieu":
        return <KhoConfigPage />;
      case "kho-bao-cao":
        return <KhoBaoCaoPage />;
      case "kho-kiem-ke":
        return <KhoKiemKePage />;
      case "kho-hang":
        return (
          <WarehouseItemsPage key={activeId} initialWarehouseId={warehouseIdOf(activeId)} />
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
