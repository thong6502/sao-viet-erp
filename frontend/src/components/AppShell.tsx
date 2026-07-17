// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PinnedCustomer, type WarehouseOption } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Toaster, toast } from "./Toast";
import { consumePurchaseToastSkip } from "../lib/realtimeFlags";
import {
  buildCapabilities,
  PermissionsProvider,
  type Capabilities,
} from "../auth/permissions";
import { ActivityLogPage } from "../pages/ActivityLogPage";
import { BaoGiaPage } from "../pages/BaoGiaPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DepartmentsPage } from "../pages/DepartmentsPage";
import { DonHangBanPage } from "../pages/DonHangBanPage";
import { KhachHangPage } from "../pages/KhachHangPage";
import { ChamCongPage } from "../pages/ChamCongPage";
import { NghiPhepPage } from "../pages/NghiPhepPage";
import { LuongPage } from "../pages/LuongPage";
import { HoSoCuaToiPage } from "../pages/HoSoCuaToiPage";
import { NhanSuPage } from "../pages/NhanSuPage";
import { UsersPage } from "../pages/UsersPage";
import { NormsCatalogPage } from "../pages/NormsCatalogPage";
import { RebuildCatalogPage } from "../pages/RebuildCatalogPage";
// Danh mục rebuild (config .tsx — render pill JSX)
import { REBUILD_CONFIGS } from "../pages/rebuildCatalogConfigs";
import { DepartmentPurchaseRequestsPage } from "../pages/DepartmentPurchaseRequestsPage";
import { PurchaseRequestsPage } from "../pages/PurchaseRequestsPage";
import { SuppliersPage } from "../pages/SuppliersPage";
import { AccountingPurchaseInboxPage } from "../pages/AccountingPurchaseInboxPage";
import { PaymentVouchersPage } from "../pages/PaymentVouchersPage";
import { AccountingBankAccountsPage } from "../pages/AccountingBankAccountsPage";
import { WarehousesCatalogPage } from "../pages/WarehousesCatalogPage";
import { WarehouseItemsPage } from "../pages/WarehouseItemsPage";
import { KhoConfigPage } from "../pages/KhoConfigPage";
import { KhoBaoCaoPage } from "../pages/KhoBaoCaoPage";
import { ProductionOrdersPage } from "../pages/ProductionOrdersPage";
import { ProfileDialog, type ProfileAction } from "./ProfileDialog";
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
  const [profileAction, setProfileAction] = useState<ProfileAction | null>(null);
  // Các kho admin đã cấu hình → menu con động dưới "Tồn kho" trong sidebar.
  const [warehouses, setWarehouses] = useState<WarehouseOption[]>([]);
  // Badge số theo nav id (vd "nghi-phep": số đơn chờ duyệt) — chỉ người có quyền duyệt.
  const [badges, setBadges] = useState<Record<string, number>>({});
  // Chuông Topbar: số đơn nghỉ CỦA TÔI vừa được quyết mà chưa xem (mọi NV).
  const [leaveUnseen, setLeaveUnseen] = useState(0);

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
  }, [token, readable]);
  useEffect(() => {
    reloadBadges();
    // Refetch khi đổi màn — cả 2 endpoint đều rất nhẹ, giữ badge tươi sau khi thao tác.
  }, [reloadBadges, activeId]);

  // Realtime YCMH: SSE đẩy số yêu cầu mua "chờ xử lý". Badge = số CHƯA XEM (open - seen); vào
  // trang Yêu cầu mua thì đánh dấu đã xem → badge về 0 (lưu localStorage để giữ qua reload).
  const ycmhLast = useRef<number | null>(null);
  const activeIdRef = useRef(activeId);
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);
  const [ycmhOpen, setYcmhOpen] = useState<number | null>(null); // số open thực tế (từ SSE)
  const [ycmhSeen, setYcmhSeen] = useState<number>(() => {
    const v = Number(localStorage.getItem("ycmhSeen"));
    return Number.isFinite(v) && v > 0 ? v : 0;
  });

  useEffect(() => {
    if (!token || readable === null) return;
    const canSee = ["thu_mua", "bao_gia", "don_hang_ban", "kho", "san_xuat", "dm_giay_vat_tu"]
      .some((m) => readable.has(m));
    if (!canSee) return;
    const es = new EventSource(api.departmentPurchaseRequests.eventsUrl(token));
    es.onmessage = (e) => {
      let n: number;
      try { n = JSON.parse(e.data)?.open ?? 0; } catch { return; }
      setYcmhOpen(n);
      const prev = ycmhLast.current;
      // Toast khi có cái MỚI — trừ khi đang ở chính trang đó, hoặc là do mình vừa tạo.
      if (prev !== null && n > prev && activeIdRef.current !== "yeu-cau-mua-hang" && !consumePurchaseToastSkip()) {
        toast(`🛒 Có ${n - prev} yêu cầu mua hàng mới`, "info");
      }
      ycmhLast.current = n;
    };
    return () => es.close();
  }, [token, readable]);

  // Badge = số chưa xem (>=0).
  useEffect(() => {
    const unseen = ycmhOpen == null ? 0 : Math.max(0, ycmhOpen - ycmhSeen);
    setBadges((prev) => (prev["yeu-cau-mua-hang"] === unseen ? prev : { ...prev, "yeu-cau-mua-hang": unseen }));
  }, [ycmhOpen, ycmhSeen]);

  // Vào trang Yêu cầu mua → đánh dấu đã xem (badge về 0).
  useEffect(() => {
    if (activeId === "yeu-cau-mua-hang" && ycmhOpen != null && ycmhOpen !== ycmhSeen) {
      setYcmhSeen(ycmhOpen);
      localStorage.setItem("ycmhSeen", String(ycmhOpen));
    }
  }, [activeId, ycmhOpen, ycmhSeen]);

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
      case "nguoi-dung":
        return <UsersPage />;
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
        return <KhachHangPage navigate={navigate} />;
      case "bao-gia":
        return (
          <BaoGiaPage
            pinnedCustomer={navParams?.customer ?? null}
            openQuoteId={navParams?.openQuoteId ?? null}
            estimateId={navParams?.estimateId ?? null}
            navigate={navigate}
          />
        );
      case "don-hang-ban":
        return (
          <DonHangBanPage
            pinnedCustomer={navParams?.customer ?? null}
            openOrderId={navParams?.openOrderId ?? null}
          />
        );
      case "dinh-muc-bu-hao":
        return <NormsCatalogPage />;
      case "yeu-cau-mua-hang":
        return <DepartmentPurchaseRequestsPage />;
      case "mua-hang":
        return <PurchaseRequestsPage />;
      case "nha-cung-cap":
        return <SuppliersPage />;
      case "ke-toan-yeu-cau-mua":
        return <AccountingPurchaseInboxPage />;
      case "ke-toan-phieu-chi":
        return <PaymentVouchersPage />;
      case "ke-toan-tai-khoan":
        return <AccountingBankAccountsPage />;
      case "cau-hinh-kho":
        return <WarehousesCatalogPage />;
      case "kho-cauhinh-phieu":
        return <KhoConfigPage />;
      case "kho-bao-cao":
        return <KhoBaoCaoPage />;
      case "kho-hang":
        return (
          <WarehouseItemsPage key={activeId} initialWarehouseId={warehouseIdOf(activeId)} />
        );
      case "lenh-san-xuat":
        return <ProductionOrdersPage />;
      case "nhat-ky":
        return <ActivityLogPage />;
      default:
        return <DashboardPage />;
    }
  }

  return (
    <PermissionsProvider caps={caps}>
      <Toaster />
      <div className="shell">
        <Sidebar
          activeId={activeId}
          onSelect={(id) => navigate(id)}
          readable={readable}
          itemChildren={itemChildren}
          badges={badges}
        />
        <div className="shell__main">
          <Topbar onProfileAction={setProfileAction} leaveUnseen={leaveUnseen} onOpenLeave={openLeaveFromBell} />
          <div className="shell__content">{renderContent()}</div>
        </div>
        <ProfileDialog action={profileAction} onClose={() => setProfileAction(null)} />
      </div>
    </PermissionsProvider>
  );
}
