// Authenticated app shell: persistent left Sidebar + the active screen.
// On entry it loads the current user's readable modules (feat-010) to gate both
// the sidebar (handled in Sidebar) and the content (a forbidden module → 403).
import { useCallback, useEffect, useState } from "react";
import { api, type PinnedCustomer } from "../api/client";
import { useAuth } from "../auth/useAuth";
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
import { RolesPage } from "../pages/RolesPage";
import { TinhGiaPage } from "../pages/TinhGiaPage";
import { UsersPage } from "../pages/UsersPage";
import { ProductTypesCatalogPage } from "../pages/ProductTypesCatalogPage";
import { MaterialsCatalogPage } from "../pages/MaterialsCatalogPage";
import { MachinesCatalogPage } from "../pages/MachinesCatalogPage";
import { OperationsCatalogPage } from "../pages/OperationsCatalogPage";
import { ClickInkRatesPage } from "../pages/ClickInkRatesPage";
import { PlateDieRatesPage } from "../pages/PlateDieRatesPage";
import { NormsCatalogPage } from "../pages/NormsCatalogPage";
import { ProfileDialog, type ProfileAction } from "./ProfileDialog";
import { MODULE_BY_NAV_ID, Sidebar } from "./Sidebar";
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
}

export type NavigateFn = (id: string, params?: NavParams) => void;

export function AppShell() {
  const { token } = useAuth();
  const [activeId, setActiveId] = useState("dashboard");
  const [navParams, setNavParams] = useState<NavParams | null>(null);
  const [readable, setReadable] = useState<Set<string> | null>(null);
  const [caps, setCaps] = useState<Capabilities>(new Map());
  const [profileAction, setProfileAction] = useState<ProfileAction | null>(null);

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

  if (readable === null) {
    return (
      <div className="shell__center" role="status" aria-live="polite">
        Đang tải…
      </div>
    );
  }

  const moduleKey = MODULE_BY_NAV_ID[activeId];
  const allowed = moduleKey != null && readable.has(moduleKey);

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
    switch (activeId) {
      case "vai-tro":
        return <RolesPage />;
      case "phong-ban":
        return <DepartmentsPage />;
      case "nguoi-dung":
        return <UsersPage />;
      case "khach-hang":
        return <KhachHangPage navigate={navigate} />;
      case "tinh-gia-thanh":
        return <TinhGiaPage navigate={navigate} openEstimateId={navParams?.openEstimateId ?? null} />;
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
      case "loai-san-pham":
        return <ProductTypesCatalogPage />;
      case "vat-lieu":
        return <MaterialsCatalogPage />;
      case "thiet-bi-may":
        return <MachinesCatalogPage />;
      case "cong-doan-gc":
        return <OperationsCatalogPage />;
      case "gia-click":
        return <ClickInkRatesPage />;
      case "gia-khuon-ban":
        return <PlateDieRatesPage />;
      case "dinh-muc-bu-hao":
        return <NormsCatalogPage />;
      case "nhat-ky":
        return <ActivityLogPage />;
      default:
        return <DashboardPage />;
    }
  }

  return (
    <PermissionsProvider caps={caps}>
      <div className="shell">
        <Sidebar activeId={activeId} onSelect={(id) => navigate(id)} readable={readable} />
        <div className="shell__main">
          <Topbar onProfileAction={setProfileAction} />
          <div className="shell__content">{renderContent()}</div>
        </div>
        <ProfileDialog action={profileAction} onClose={() => setProfileAction(null)} />
      </div>
    </PermissionsProvider>
  );
}
