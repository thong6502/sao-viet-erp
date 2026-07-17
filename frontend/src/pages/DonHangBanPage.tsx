// Đơn hàng bán — redesign-don-hang-ban.md (P1: list + chi tiết + tạo + sửa đặt-hàng).
// Cọc/duyệt/chốt/hủy = P2–P5. Icon dùng bộ Icon nhà (không emoji).
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../components/Icons";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import {
  api,
  type OrderCreateInput,
  type OrderDetail,
  type OrderEnumsOut,
  type OrderLineInput,
  type OrderRow,
  type OrderStatsOut,
  type ProductionOrderRow,
} from "../api/client";
import "./don-hang-ban.css";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

function vnd(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("vi-VN") + "₫";
}
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleDateString("vi-VN");
}

// V5: hình thức thu của Phiếu thu Kế toán (PAYMENT_VOUCHER_TYPES).
const RECEIPT_METHOD_LABELS: Record<string, string> = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
};

const STATUS_META: Record<string, { label: string; bg: string; fg: string }> = {
  draft: { label: "Nháp", bg: "#eef1f6", fg: "#48566a" },
  ordered: { label: "Đã chốt", bg: "#e4f5ec", fg: "#1f8a52" },
  cancelled: { label: "Hủy", bg: "#fdecea", fg: "#b4432b" },
  // dormant (thiết kế đã bỏ) — map để dữ liệu cũ không phun enum thô ra UI
  on_hold: { label: "Tạm giữ", bg: "#fdf2e0", fg: "#a9631a" },
  change_order: { label: "Đổi đơn", bg: "#fdf2e0", fg: "#a9631a" },
};

type TabDef = {
  id: string;
  label: string;
  status?: string;
  approval_state?: string;
  clientFilter?: (o: OrderRow) => boolean;
  countKey?: keyof OrderStatsOut;
};
const TABS: TabDef[] = [
  { id: "all", label: "Tất cả", countKey: "all" },
  { id: "draft", label: "Nháp", status: "draft", countKey: "draft" },
  { id: "pending", label: "Chờ duyệt", approval_state: "pending", countKey: "pending_approval" },
  { id: "awaiting_deposit", label: "Chờ cọc", status: "draft", clientFilter: (o) => !o.deposit_ok },
  { id: "ready", label: "Sẵn sàng chốt", status: "draft", clientFilter: (o) => o.deposit_ok && (!o.needs_approval || o.approval_state === "approved") },
  { id: "ordered", label: "Đã chốt", status: "ordered", countKey: "ordered" },
  { id: "cancelled", label: "Hủy", status: "cancelled", countKey: "cancelled" },
];

function Chip({ icon, label, tone }: { icon: IconName; label: string; tone: "warn" | "muted" | "info" }) {
  return (
    <span className={`dhb__chip tone--${tone}`}>
      <Icon name={icon} size={12} /> {label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status };
  return (
    <span className={`dhb__status-badge status--${status}`}>
      {m.label}
    </span>
  );
}

function RowFlags({ o }: { o: OrderRow }) {
  return (
    <span className="dhb__flags">
      {o.needs_approval && o.approval_state !== "approved" && (
        <Chip icon="clock" label="Chờ duyệt" tone="warn" />
      )}
      {o.order_nature === "gia_cong" && <Chip icon="scissors" label="Gia công" tone="info" />}
      {o.cost_basis === "none" && <Chip icon="help" label="Không giá vốn" tone="muted" />}
    </span>
  );
}

interface Props {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}

export function DonHangBanPage({ navigate }: Props) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("don_hang_ban", "create");
  const canUpdate = can("don_hang_ban", "update");
  const canRecordDeposit = can("don_hang_ban", "record_deposit");
  const canApproveException = can("don_hang_ban", "approve_exception");
  const canManageStatus = can("don_hang_ban", "manage_status");

  const [tab, setTab] = useState("all");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<OrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [enums, setEnums] = useState<OrderEnumsOut | null>(null);

  const [selected, setSelected] = useState<OrderDetail | null>(null);
  const [creating, setCreating] = useState(false);
  const [viewScope, setViewScope] = useState("");
  const [stats, setStats] = useState<OrderStatsOut | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    const t = TABS.find((x) => x.id === tab) ?? TABS[0];
    setLoading(true);
    setErr(null);
    api.orders
      .list(token, {
        q: q || undefined, status: t.status, approval_state: t.approval_state,
        view_scope: viewScope || undefined, sort: "-created_at", page: 1, size: 50,
      })
      .then((r) => {
        const rows = t.clientFilter ? r.items.filter(t.clientFilter) : r.items;
        setRows(rows);
        setTotal(t.clientFilter ? rows.length : r.total);
      })
      .catch((e) => setErr(String(e?.message ?? e)))
      .finally(() => setLoading(false));
    api.orders.stats(token, viewScope || undefined).then(setStats).catch(() => {});
  }, [token, q, tab, viewScope]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (token && !enums) api.orders.enums(token).then(setEnums).catch(() => {});
  }, [token, enums]);

  function openDetail(id: number) {
    if (!token) return;
    api.orders.get(token, id).then(setSelected).catch((e) => setErr(String(e?.message ?? e)));
  }

  return (
    <main className="dhb-container">
      <header className="dhb__header">
        <div className="dhb__title-group">
          <p className="eyebrow">Kinh doanh</p>
          <h1 className="dhb__title">Đơn hàng bán</h1>
        </div>
        {canCreate && (
          <button className="btn btn--primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={16} /> Tạo đơn
          </button>
        )}
      </header>

      {/* Tabs + tìm */}
      <div className="dhb__toolbar">
        <div className="dhb__tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`dhb__tab ${tab === t.id ? "is-active" : ""}`}
            >
              {t.label}
              {t.countKey && stats && stats[t.countKey] !== undefined && (
                <span className="dhb__tab-count">{stats[t.countKey]}</span>
              )}
            </button>
          ))}
        </div>
        <div className="dhb__spacer" />
        <select
          value={viewScope}
          onChange={(e) => setViewScope(e.target.value)}
          title="Phạm vi dữ liệu"
          className="dhb__select"
        >
          <option value="">Phạm vi</option>
          <option value="own">Của tôi</option>
          <option value="department">Cả phòng</option>
          <option value="all">Tất cả</option>
        </select>
        <div className="dhb__search-wrapper">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã / khách / PO…"
            className="dhb__search-input"
          />
          <span className="dhb__search-icon">
            <Icon name="search" size={15} />
          </span>
        </div>
      </div>

      {err && <div className="banner banner--error" role="alert">{err}</div>}

      {/* Bảng */}
      <div className="dhb__tablewrap">
        <table className="dhb__table">
          <thead>
            <tr>
              <th>Mã đơn</th>
              <th>Khách hàng</th>
              <th>Nguồn</th>
              <th className="dhb__text-right">Giá trị</th>
              <th>Cọc</th>
              <th>Ngày giao</th>
              <th>NV</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={8} className="text-center" style={{ padding: 24, color: "var(--ash)" }}>
                  Đang tải…
                </td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center" style={{ padding: 24, color: "var(--ash)" }}>
                  Chưa có đơn hàng.
                </td>
              </tr>
            )}
            {!loading &&
              rows.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => openDetail(o.id)}
                  className="dhb__row"
                >
                  <td>
                    <span className="dhb__order-code">{o.order_no}</span>
                    <div style={{ marginTop: 4 }}>
                      <RowFlags o={o} />
                    </div>
                  </td>
                  <td>{o.customer_name ?? "—"}</td>
                  <td>
                    {o.source_type === "bao_gia" ? (
                      <span className="dhb__order-source-bg">{o.quotation_code ?? "—"}</span>
                    ) : (
                      <span className="dhb__order-source-manual">Nhập tay</span>
                    )}
                  </td>
                  <td className="dhb__mono dhb__text-right">
                    {vnd(o.total_with_vat)}
                  </td>
                  <td>
                    <DepositBar o={o} />
                  </td>
                  <td className="dhb__mono">{fmtDate(o.delivery_committed_date)}</td>
                  <td>{o.sale_name ?? "—"}</td>
                  <td>
                    <StatusBadge status={o.status} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p style={{ color: "var(--ash)", fontSize: 12, marginTop: 8 }}>{total} đơn</p>

      {selected && (
        <OrderDrawer
          order={selected}
          canUpdate={canUpdate}
          canRecordDeposit={canRecordDeposit}
          canApproveException={canApproveException}
          canManageStatus={canManageStatus}
          onClose={() => setSelected(null)}
          onSaved={(d) => {
            setSelected(d);
            load();
          }}
          navigate={navigate}
        />
      )}
      {creating && enums && (
        <CreateModal
          enums={enums}
          onClose={() => setCreating(false)}
          onCreated={(d) => {
            setCreating(false);
            load();
            setSelected(d);
          }}
        />
      )}
    </main>
  );
}

function DepositBar({ o }: { o: OrderRow }) {
  if (!o.deposit_required)
    return <span className="dhb__mono" style={{ color: "var(--ash)" }}>—</span>;
  const pct = Math.min(100, Math.round((o.deposit_received / o.deposit_required) * 100));
  return (
    <div className="dhb__deposit-container">
      <div className="dhb__deposit-header">
        <span>{vnd(o.deposit_received)}</span>
        {o.deposit_ok ? (
          <span className="dhb__deposit-ok">
            <Icon name="check" size={11} /> đủ
          </span>
        ) : (
          <span>/ {vnd(o.deposit_required)}</span>
        )}
      </div>
      <div className="dhb__deposit-progress-bg">
        <div
          className="dhb__deposit-progress-bar"
          style={{
            width: `${pct}%`,
            background: o.deposit_ok ? "var(--moss)" : "var(--amber)",
          }}
        />
      </div>
    </div>
  );
}

// --- Drawer chi tiết ----------------------------------------------------------
function OrderDrawer({
  order, canUpdate, canRecordDeposit, canApproveException, canManageStatus, onClose, onSaved, navigate,
}: {
  order: OrderDetail;
  canUpdate: boolean;
  canRecordDeposit: boolean;
  canApproveException: boolean;
  canManageStatus: boolean;
  onClose: () => void;
  onSaved: (d: OrderDetail) => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const [editing, setEditing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const canCancel = (order.status === "draft" && canUpdate) || (order.status === "ordered" && canApproveException);

  async function upConsent(f: File) { if (token) onSaved(await api.orders.uploadConsent(token, order.id, f)); }
  async function delConsent(aid: number) { if (token) onSaved(await api.orders.deleteConsent(token, order.id, aid)); }
  const [acts, setActs] = useState<{ at: string; actor_name: string | null; action: string; detail: string }[]>([]);
  const [prodOrders, setProdOrders] = useState<ProductionOrderRow[]>([]);
  const isDraft = order.status === "draft";
  const [drawerTab, setDrawerTab] = useState<"overview" | "commercial" | "history">("overview");

  const isChotDone = order.status === "ordered" || order.ordered_at != null;
  const isCocDone = order.deposit_ok;
  const isSxDone = prodOrders.length > 0 && prodOrders.every((x) => x.status === "done");
  const isSxActive = prodOrders.length > 0 && !isSxDone && prodOrders.some((x) => x.status === "open");

  const chotDate = order.ordered_at ? fmtDate(order.ordered_at) : (order.created_at ? fmtDate(order.created_at) : "—");
  const cocText = isCocDone ? "đủ" : "chờ cọc";
  const sxText = isSxDone ? "hoàn thành" : (isSxActive ? "đang làm" : "—");

  const [activeStep, setActiveStep] = useState<"chot" | "coc" | "sx" | "giao" | "hoadon">("coc");

  useEffect(() => {
    if (token) api.orders.activity(token, order.id).then((r) => setActs(r.items)).catch(() => {});
  }, [token, order.id]);

  useEffect(() => {
    const defaultStep = !isChotDone ? "chot" : (!isCocDone ? "coc" : (isSxDone ? "giao" : "sx"));
    setActiveStep(defaultStep);
  }, [order.id, isChotDone, isCocDone, isSxDone]);

  useEffect(() => {
    if (token && order.id) {
      api.production.listOrders(token, { size: 100 })
        .then((res) => {
          setProdOrders(res.items.filter((x) => x.order_id === order.id));
        })
        .catch((e) => console.error(e));
    }
  }, [token, order.id]);

  return (
    <div
      onClick={onClose}
      className="dhb__drawer-overlay"
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="dhb__drawer-content"
      >
        <header className="dhb__drawer-header">
          <h2 className="dhb__drawer-title">{order.order_no}</h2>
          <StatusBadge status={order.status} />
          {order.source_type === "bao_gia" && order.quotation_code && (
            <Chip icon="fileText" label={order.quotation_code} tone="muted" />
          )}
          <RowFlags o={order} />
          <div style={{ flex: 1 }} />
          {isDraft && canUpdate && !editing && (
            <button className="btn btn--secondary" style={{ height: 32 }} onClick={() => setEditing(true)}><Icon name="pencil" size={14} /> Sửa</button>
          )}
          {canCancel && (
            <button className="btn btn--secondary" style={{ height: 32 }} onClick={() => setCancelling(true)}><Icon name="ban" size={14} /> Hủy</button>
          )}
          <button className="btn btn--ghost" style={{ height: 32 }} onClick={onClose} aria-label="Đóng"><Icon name="x" size={16} /></button>
        </header>

        <div className="dhb__drawer-tabs">
          <button
            onClick={() => setDrawerTab("overview")}
            className={`dhb__drawer-tab ${drawerTab === "overview" ? "is-active" : ""}`}
          >
            <Icon name="grid" size={13} /> Tổng quan & Vòng đời
          </button>
          <button
            onClick={() => setDrawerTab("commercial")}
            className={`dhb__drawer-tab ${drawerTab === "commercial" ? "is-active" : ""}`}
          >
            <Icon name="cart" size={13} /> Thương mại
          </button>
          <button
            onClick={() => setDrawerTab("history")}
            className={`dhb__drawer-tab ${drawerTab === "history" ? "is-active" : ""}`}
          >
            <Icon name="fileText" size={13} /> Đính kèm & Nhật ký
          </button>
        </div>

        <div className="dhb__drawer-body">
          {drawerTab === "overview" && (
            <>
              {/* ① Thông tin đơn hàng */}
              <Section title="Thông tin đơn hàng">
                <div className="dhb__kv-grid">
                  <KV k="Nguồn" v={order.source_type === "bao_gia" ? "Từ báo giá" : "Nhập giá tay"} />
                  <KV k="Loại" v={order.order_kind === "bo_sung" ? "Đơn bổ sung" : "Đơn mới"} />
                  <KV k="Bản chất" v={order.order_nature === "gia_cong" ? "Gia công" : "Hàng hóa"} />
                  <KV k="NV phụ trách" v={order.sale_name ?? "—"} />
                  <KV k="Ngày tạo" v={<span className="dhb__mono">{fmtDate(order.created_at)}</span>} />
                  {order.ordered_at && <KV k="Ngày chốt" v={<span className="dhb__mono">{fmtDate(order.ordered_at)}</span>} />}
                  {order.customer_po_no && <KV k="Số PO khách" v={<span className="dhb__mono">{order.customer_po_no}</span>} />}
                  {order.delivery_committed_date && <KV k="Ngày giao cam kết" v={<span className="dhb__mono">{fmtDate(order.delivery_committed_date)}</span>} />}
                  {order.delivery_address && <KV k="Địa chỉ giao" v={order.delivery_address} />}
                  {order.invoice_entity_name && (
                    <KV
                      k="Pháp nhân xuất HĐ"
                      v={`${order.invoice_entity_name}${order.invoice_entity_tax_code ? " · MST " + order.invoice_entity_tax_code : ""}`}
                    />
                  )}
                  {order.deposit_pct != null && <KV k="% cọc" v={<span className="dhb__mono">{order.deposit_pct}%</span>} />}
                </div>
                {editing && (
                  <div style={{ marginTop: 12 }}>
                    <EditForm order={order} onCancel={() => setEditing(false)} onSaved={(d) => { setEditing(false); onSaved(d); }} />
                  </div>
                )}
              </Section>
 
              {/* Vòng đời đơn */}
              <Section title="Vòng đời đơn">
                <div className="dhb__lifecycle-header">
                  <span className="dhb__lifecycle-subtitle">read-only · bấm chọn từng bước để xem chi tiết</span>
                </div>
                
                {/* 1. Timeline */}
                <div className="dhb__timeline">
                  <div
                    className={`dhb__timeline-step ${isChotDone ? "is-done" : ""} ${activeStep === "chot" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("chot")}
                  >
                    <div className="dhb__timeline-dot">
                      {isChotDone ? <Icon name="check" size={12} /> : "1"}
                    </div>
                    <span className="dhb__timeline-label">Chốt</span>
                    <span className="dhb__timeline-sub">{chotDate}</span>
                  </div>
                  <div
                    className={`dhb__timeline-step ${isCocDone ? "is-done" : ""} ${activeStep === "coc" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("coc")}
                  >
                    <div className="dhb__timeline-dot">
                      {isCocDone ? <Icon name="check" size={12} /> : "2"}
                    </div>
                    <span className="dhb__timeline-label">Cọc</span>
                    <span className="dhb__timeline-sub">{cocText}</span>
                  </div>
                  <div
                    className={`dhb__timeline-step ${isSxDone ? "is-done" : (isSxActive ? "is-active" : "")} ${activeStep === "sx" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("sx")}
                  >
                    <div className="dhb__timeline-dot">
                      {isSxDone ? <Icon name="check" size={12} /> : (isSxActive ? <Icon name="clock" size={12} /> : "3")}
                    </div>
                    <span className="dhb__timeline-label">Sản xuất</span>
                    <span className="dhb__timeline-sub">{sxText}</span>
                  </div>
                  <div
                    className={`dhb__timeline-step ${activeStep === "giao" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("giao")}
                  >
                    <div className="dhb__timeline-dot">4</div>
                    <span className="dhb__timeline-label">Giao hàng</span>
                    <span className="dhb__timeline-sub">—</span>
                  </div>
                  <div
                    className={`dhb__timeline-step ${activeStep === "hoadon" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("hoadon")}
                  >
                    <div className="dhb__timeline-dot">5</div>
                    <span className="dhb__timeline-label">Hóa đơn</span>
                    <span className="dhb__timeline-sub">—</span>
                  </div>
                </div>
 
                {/* 2. Active Lifecycle Step Card */}
                {activeStep === "chot" && (
                  <div className="dhb__lifecycle-box">
                    <div className="dhb__lifecycle-box-header">
                      <h4 className="dhb__lifecycle-box-title">Chốt đơn hàng</h4>
                      <span className={`dhb__lifecycle-badge ${isChotDone ? "dhb__lifecycle-badge--done" : "dhb__lifecycle-badge--active"}`}>
                        {order.status === "draft" ? "BẢN NHÁP" : (order.status === "ordered" ? "ĐÃ CHỐT" : "ĐÃ HỦY")}
                      </span>
                    </div>
                    <div style={{ marginTop: 4 }}>
                      {isDraft ? (
                        <ConfirmPanel order={order} canManage={canManageStatus} canExtend={canUpdate} onSaved={onSaved} />
                      ) : order.status === "ordered" ? (
                        <>
                          <KV k="Đã chốt lúc" v={<span className="dhb__mono">{fmtDate(order.ordered_at)}</span>} />
                          <p style={{ color: "var(--ash)", fontSize: 12, margin: "6px 0 0" }}>Duyệt bản in + tiến độ sản xuất là luồng ngoài hệ thống.</p>
                        </>
                      ) : order.status === "cancelled" ? (
                        <div style={{ display: "grid", gap: 4 }}>
                          <KV k="Lý do hủy" v={order.cancel_reason ?? "—"} />
                          {order.cancel_fault && <KV k="Lỗi tại" v={order.cancel_fault === "khach" ? "Khách hàng" : "Xưởng in"} />}
                          {order.deposit_received > 0 && (
                            <KV k="Cọc" v={`Còn ${vnd(order.deposit_received)} chưa quyết toán — xử lý ngoài hệ thống`} />
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                )}
 
                {activeStep === "coc" && (
                  <div className="dhb__lifecycle-box">
                    <div className="dhb__lifecycle-box-header">
                      <h4 className="dhb__lifecycle-box-title">Cọc & thu tiền</h4>
                      <span className={`dhb__lifecycle-badge ${isCocDone ? "dhb__lifecycle-badge--done" : "dhb__lifecycle-badge--active"}`}>
                        {isCocDone ? "ĐỦ CỌC" : "CHỜ CỌC"}
                      </span>
                    </div>
                    <div style={{ display: "grid", gap: 4, marginTop: 4 }}>
                      <KV k="Ngưỡng cần thu (30% ghim từ báo giá)" v={<span className="dhb__mono">{vnd(order.deposit_required)}</span>} right />
                      <KV k="Đã thu" v={<strong className="dhb__mono" style={{ color: "var(--ink)" }}>{vnd(order.deposit_received)}</strong>} right />
                    </div>
                    <div style={{ margin: "4px 0" }}><DepositBar o={order} /></div>
                    {order.deposits.length > 0 && (
                      <div style={{ display: "grid", gap: 6, marginTop: 4 }}>
                        {order.deposits.map((d) => (
                          <div key={d.id} style={{ background: "var(--canvas)", border: "1px solid var(--rule-soft)", borderRadius: "var(--r-3)", padding: "8px 12px" }}>
                            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                              <strong className="dhb__mono">{vnd(d.amount)}</strong>
                              <span style={{ color: "var(--ash)" }}>{RECEIPT_METHOD_LABELS[d.receipt_method] ?? d.receipt_method}</span>
                              {d.status === "received" && (
                                <span style={{ color: "var(--moss)", display: "inline-flex", gap: 2, alignItems: "center" }}><Icon name="check" size={12} /> đã thu</span>
                              )}
                              {d.receipt_date && <span style={{ color: "var(--ash-2)" }} className="dhb__mono">{fmtDate(d.receipt_date)}</span>}
                              <div style={{ flex: 1 }} />
                              <button type="button" className="dhb__mono"
                                style={{ color: "var(--rust)", fontSize: 12, background: "none", border: "none", padding: 0, cursor: "pointer", textDecoration: "underline" }}
                                title="Mở phiếu thu này bên Kế toán"
                                onClick={() => navigate?.("ke-toan-phieu-thu", { focusReceiptQuery: d.code })}>
                                {d.doc_no ?? d.code}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {canRecordDeposit && isDraft && <DepositForm order={order} onSaved={onSaved} />}
                    {!isDraft && <p style={{ color: "var(--ash)", fontSize: 12, marginTop: 4, margin: 0 }}>Đơn đã chốt — phiếu thu khóa.</p>}
                  </div>
                )}
 
                {activeStep === "sx" && (
                  <div className="dhb__lifecycle-box">
                    <div className="dhb__lifecycle-box-header">
                      <h4 className="dhb__lifecycle-box-title">Sản xuất</h4>
                      {prodOrders.length > 0 ? (
                        <>
                          <span className={`dhb__lifecycle-badge ${isSxDone ? "dhb__lifecycle-badge--done" : "dhb__lifecycle-badge--active"}`}>
                            {isSxDone ? "HOÀN THÀNH" : "ĐANG SẢN XUẤT"}
                          </span>
                          <button
                            className="link dhb__mono"
                            style={{ color: "var(--rust)", background: "none", border: 0, cursor: "pointer", padding: 0, fontWeight: 700 }}
                            onClick={() => navigate?.("lenh-san-xuat")}
                          >
                            {prodOrders[0].code} ↗
                          </button>
                        </>
                      ) : (
                        <span className="dhb__lifecycle-badge dhb__lifecycle-badge--upcoming">CHƯA BẮT ĐẦU</span>
                      )}
                    </div>
                    {prodOrders.length > 0 ? (
                      <>
                        <p className="dhb__lifecycle-desc" style={{ marginTop: 4 }}>
                          Trạng thái lệnh sản xuất: <strong>{prodOrders[0].status === "done" ? "Hoàn thành" : (prodOrders[0].status === "cancelled" ? "Đã hủy" : "open (đang làm)")}</strong>
                        </p>
                        <p className="dhb__lifecycle-desc" style={{ opacity: 0.7, fontSize: 11, fontStyle: "italic" }}>
                          Kéo từ Lệnh sản xuất qua liên kết đơn. Chỉ mức thô open / done / cancelled mà Sản xuất đang có — tiến độ theo công đoạn là P2, khi có sẽ tự hiện thêm.
                        </p>
                      </>
                    ) : (
                      <p className="dhb__lifecycle-desc">Đơn chưa lập Lệnh sản xuất (LSX).</p>
                    )}
                  </div>
                )}
 
                {activeStep === "giao" && (
                  <div className="dhb__lifecycle-box dhb__lifecycle-box--dotted">
                    <div className="dhb__lifecycle-box-header">
                      <h4 className="dhb__lifecycle-box-title">Giao hàng</h4>
                      <span className="dhb__lifecycle-badge dhb__lifecycle-badge--upcoming">SẮP CÓ - KẾ HOẠCH GIAO HÀNG</span>
                    </div>
                    <div style={{ display: "grid", gap: 4, marginTop: 4 }}>
                      <KV k="Ngày giao cam kết (đã có ở đơn)" v={<span className="dhb__mono">{fmtDate(order.delivery_committed_date)}</span>} />
                    </div>
                    <p className="dhb__lifecycle-desc" style={{ opacity: 0.7, fontSize: 11, fontStyle: "italic", marginTop: 4 }}>
                      Khi có module sẽ hiện thực tế: Lịch giao thực | Đã giao _ / 1.000 | Biên bản giao (POD)
                    </p>
                  </div>
                )}
 
                {activeStep === "hoadon" && (
                  <div className="dhb__lifecycle-box dhb__lifecycle-box--dotted">
                    <div className="dhb__lifecycle-box-header">
                      <h4 className="dhb__lifecycle-box-title">Hóa đơn & công nợ</h4>
                      <span className="dhb__lifecycle-badge dhb__lifecycle-badge--upcoming">SẮP CÓ - HÓA ĐƠN/AR</span>
                    </div>
                    <p className="dhb__lifecycle-desc" style={{ opacity: 0.7, fontSize: 11, fontStyle: "italic" }}>
                      Khi có module sẽ hiện: Số hóa đơn | Còn nợ = tổng – đã thu | Hạn công nợ
                    </p>
                  </div>
                )}
              </Section>
 
              {/* ⑤ Duyệt (chỉ đơn cần duyệt) */}
              {order.needs_approval && (
                <Section title="Duyệt đơn đặc thù">
                  <ApprovalPanel order={order} canApprove={canApproveException} onSaved={onSaved} />
                </Section>
              )}
            </>
          )}

          {drawerTab === "commercial" && (
            <>
              {/* ② Thương mại */}
              <Section title="Thương mại (khóa)">
                <KV k="Khách hàng" v={order.customer_name ?? "—"} />
                {order.source_type === "bao_gia" && order.quotation_code && (
                  <KV
                    k="Báo giá"
                    v={
                      <button
                        className="link dhb__mono"
                        style={{ color: "var(--rust)", background: "none", border: 0, cursor: "pointer", padding: 0 }}
                        onClick={() => navigate?.("bao-gia", { openQuoteId: order.quotation_id })}
                      >
                        {order.quotation_code} · v{order.quotation_version} ↗
                      </button>
                    }
                  />
                )}
                <table className="dhb__comm-table">
                  <thead>
                    <tr>
                      <th>Mô tả</th>
                      <th className="dhb__text-right">SL</th>
                      <th className="dhb__text-right">Đơn giá</th>
                      <th className="dhb__text-right">VAT</th>
                      <th className="dhb__text-right">Thành tiền</th>
                    </tr>
                  </thead>
                  <tbody>
                    {order.lines.map((l) => (
                      <tr key={l.id}>
                        <td>{l.description}</td>
                        <td className="dhb__mono dhb__text-right">{l.qty.toLocaleString("vi-VN")}</td>
                        <td className="dhb__mono dhb__text-right">{vnd(l.unit_price_snapshot)}</td>
                        <td className="dhb__mono dhb__text-right">{l.vat_pct_estimate}%</td>
                        <td className="dhb__mono dhb__text-right">{vnd(l.line_total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="dhb__summary-box">
                  <KV k="Cộng trước VAT" v={<span className="dhb__mono">{vnd(order.total)}</span>} right />
                  <KV k="Tổng gồm VAT" v={<strong className="dhb__mono" style={{ color: "var(--ink)", fontSize: 14 }}>{vnd(order.total_with_vat)}</strong>} right />
                  {order.margin_pct != null ? (
                    <KV k="Biên lợi nhuận" v={<span className="dhb__mono">{order.margin_pct}% (giá vốn {vnd(order.order_cost)})</span>} right />
                  ) : (
                    <KV k="Biên lợi nhuận" v={<em style={{ color: "var(--ash)" }}>không xác định (nhập tay)</em>} right />
                  )}
                </div>
              </Section>
            </>
          )}

          {drawerTab === "history" && (
            <>
              {/* Chứng cứ khách đồng ý */}
              <Section title="Chứng cứ khách đồng ý">
                {order.consent_attachments.length === 0 && !(isDraft && canUpdate) && (
                  <p style={{ color: "var(--ash)", fontSize: 13, margin: 0 }}>Chưa có.</p>
                )}
                <AttachmentList
                  items={order.consent_attachments}
                  canEdit={isDraft && canUpdate}
                  onUpload={upConsent}
                  onDelete={delConsent}
                  addLabel="Đính kèm chứng cứ (ảnh PO/Zalo…)"
                />
              </Section>

              {/* ⑥ Nhật ký */}
              <Section title="Nhật ký hoạt động">
                {acts.length === 0 && <p style={{ color: "var(--ash)", fontSize: 13, margin: 0 }}>Chưa có.</p>}
                {acts.map((a, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, fontSize: 13, padding: "6px 0", borderTop: i ? "1px solid var(--rule-hair)" : undefined }}>
                    <span className="dhb__mono" style={{ color: "var(--ash-2)", minWidth: 92 }}>{new Date(a.at).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                    <span><strong>{a.actor_name ?? "—"}</strong> · {a.detail || a.action}</span>
                  </div>
                ))}
              </Section>
            </>
          )}
        </div>
        {cancelling && (
          <CancelDialog
            order={order}
            onClose={() => setCancelling(false)}
            onSaved={(d) => { setCancelling(false); onSaved(d); }}
          />
        )}
      </aside>
    </div>
  );
}

function CancelDialog({ order, onClose, onSaved }: { order: OrderDetail; onClose: () => void; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const isOrdered = order.status === "ordered";
  const [reason, setReason] = useState("");
  const [fault, setFault] = useState("khach");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      onSaved(await api.orders.cancel(token, order.id, reason, isOrdered ? fault : null));
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div onClick={onClose} className="dhb__modal-overlay" style={{ zIndex: 70 }}>
      <div onClick={(e) => e.stopPropagation()} className="dhb__modal-content" style={{ width: 440 }}>
        <h3 className="dhb__modal-title" style={{ fontSize: 18 }}>Hủy đơn {order.order_no}</h3>
        <p style={{ color: "var(--ash)", fontSize: 13, marginTop: 0, marginBottom: 12 }}>
          {isOrdered
            ? "Đơn đã chốt — báo giá KHÔNG mở lại; cọc giữ nguyên, hoàn/quyết toán xử lý ngoài hệ thống."
            : "Đơn nháp — hủy xong báo giá vẫn dùng lại được."}
        </p>
        {isOrdered && (
          <Field label="Lỗi tại ai">
            <select value={fault} onChange={(e) => setFault(e.target.value)} className="dhb__select" style={{ width: "100%" }}>
              <option value="khach">Khách hàng</option>
              <option value="xuong">Xưởng in</option>
            </select>
          </Field>
        )}
        <Field label="Lý do hủy">
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Nêu lý do; nếu đã chốt, kể luôn tình trạng lúc hủy (vd: đã ra kẽm, khách đổi ý)." style={{ ...inp, minHeight: 60, resize: "vertical" }} />
        </Field>
        {err && <div className="banner banner--error">{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Đóng</button>
          <button className="btn btn--primary" onClick={submit} disabled={busy || !reason.trim()}>{busy ? "Đang hủy…" : "Xác nhận hủy"}</button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="dhb__section">
      <h3 className="dhb__section-title">{title}</h3>
      <div style={{ display: "grid", gap: 6 }}>{children}</div>
    </section>
  );
}

function KV({ k, v, right }: { k: string; v: React.ReactNode; right?: boolean }) {
  return (
    <div className="dhb__kv" style={{ justifyContent: right ? "space-between" : undefined }}>
      <span className="dhb__kv-key" style={{ minWidth: right ? undefined : 150 }}>{k}</span>
      <span className="dhb__kv-val">{v}</span>
    </div>
  );
}

// --- Form sửa đặt-hàng --------------------------------------------------------
function EditForm({ order, onCancel, onSaved }: { order: OrderDetail; onCancel: () => void; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [po, setPo] = useState(order.customer_po_no ?? "");
  const [date, setDate] = useState(order.delivery_committed_date ?? "");
  const [addr, setAddr] = useState(order.delivery_address ?? "");
  const [entity, setEntity] = useState(order.invoice_entity_name ?? "");
  const [taxCode, setTaxCode] = useState(order.invoice_entity_tax_code ?? "");
  const [nature, setNature] = useState(order.order_nature);
  const [depositPct, setDepositPct] = useState(order.deposit_pct != null ? String(order.deposit_pct) : "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const d = await api.orders.update(token, order.id, {
        customer_po_no: po || null,
        delivery_committed_date: date || null,
        delivery_address: addr || null,
        invoice_entity_name: entity || null,
        invoice_entity_tax_code: taxCode || null,
        order_nature: nature,
        deposit_pct: depositPct.trim() === "" ? null : Number(depositPct),
      });
      onSaved(d);
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <Field label="Số PO khách"><input value={po} onChange={(e) => setPo(e.target.value)} style={inp} /></Field>
      <Field label="% cọc"><input type="number" min={0} max={100} value={depositPct} onChange={(e) => setDepositPct(e.target.value)} placeholder="vd 30" style={inp} /></Field>
      <Field label="Ngày giao cam kết"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={inp} /></Field>
      <Field label="Địa chỉ giao"><input value={addr} onChange={(e) => setAddr(e.target.value)} style={inp} /></Field>
      <Field label="Bản chất đơn">
        <select value={nature} onChange={(e) => setNature(e.target.value)} style={inp}>
          <option value="hang_hoa">Hàng hóa</option>
          <option value="gia_cong">Gia công</option>
        </select>
      </Field>
      <Field label="Pháp nhân xuất HĐ"><input value={entity} onChange={(e) => setEntity(e.target.value)} placeholder="Mặc định = khách" style={inp} /></Field>
      <Field label="MST xuất HĐ"><input value={taxCode} onChange={(e) => setTaxCode(e.target.value)} style={inp} /></Field>
      {err && <div className="banner banner--error">{err}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn btn--ghost" onClick={onCancel} disabled={saving}>Hủy</button>
        <button className="btn btn--primary" onClick={save} disabled={saving}>{saving ? "Đang lưu…" : "Lưu"}</button>
      </div>
    </div>
  );
}

// --- Modal tạo đơn ------------------------------------------------------------
function CreateModal({ enums, onClose, onCreated }: { enums: OrderEnumsOut; onClose: () => void; onCreated: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [source, setSource] = useState("bao_gia");
  const [quotationId, setQuotationId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [nature, setNature] = useState("hang_hoa");
  const [lines, setLines] = useState<OrderLineInput[]>([{ description: "", qty: 1, unit_price: 0, vat_pct: 8 }]);
  const [po, setPo] = useState("");
  const [depositPct, setDepositPct] = useState("");
  const [isSupp, setIsSupp] = useState(false);
  const [parentId, setParentId] = useState("");
  const [quotes, setQuotes] = useState<{ id: number; code: string; customer_name: string | null }[]>([]);
  const [custs, setCusts] = useState<{ id: number; name: string; code: string }[]>([]);
  const [parents, setParents] = useState<{ id: number; order_no: string; customer_name: string | null }[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.quotations.list(token, { status: "accepted", size: 100 }).then((r) => setQuotes(r.items)).catch(() => {});
    api.customers.list(token, { size: 200 }).then((r) => setCusts(r.items)).catch(() => {});
    api.orders.list(token, { status: "ordered", size: 100 }).then((r) => setParents(r.items)).catch(() => {});
  }, [token]);

  async function submit() {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const input: OrderCreateInput = {
        source_type: source, order_nature: nature, customer_po_no: po || null,
        order_kind: isSupp ? "bo_sung" : "moi",
        parent_order_id: isSupp && parentId ? Number(parentId) : null,
      };
      if (source === "bao_gia") input.quotation_id = Number(quotationId);
      else {
        input.customer_id = Number(customerId);
        input.lines = lines.filter((l) => l.description);
        input.vat_pct_estimate = lines[0]?.vat_pct ?? 8;
      }
      if (depositPct.trim() !== "") input.deposit_pct = Number(depositPct);
      const d = await api.orders.create(token, input);
      onCreated(d);
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div onClick={onClose} className="dhb__modal-overlay">
      <div onClick={(e) => e.stopPropagation()} className="dhb__modal-content" style={{ maxHeight: "90vh", overflowY: "auto" }}>
        <h2 className="dhb__modal-title">Tạo đơn hàng</h2>

        <Field label="Nguồn đơn">
          <div style={{ display: "flex", gap: 8 }}>
            {enums.source_types.map((s) => (
              <button
                key={s.value}
                onClick={() => setSource(s.value)}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  borderRadius: "var(--r-3)",
                  border: "1px solid",
                  borderColor: source === s.value ? "var(--charcoal)" : "var(--rule-soft)",
                  background: source === s.value ? "var(--charcoal)" : "var(--canvas)",
                  color: source === s.value ? "var(--on-charcoal)" : "var(--ash)",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                  transition: "all var(--duration-fast) var(--easing-standard)",
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </Field>

        {source === "bao_gia" ? (
          <Field label="Báo giá đã duyệt (khách đồng ý)">
            <select value={quotationId} onChange={(e) => setQuotationId(e.target.value)} className="dhb__select" style={{ width: "100%" }}>
              <option value="">— Chọn báo giá —</option>
              {quotes.map((qu) => (
                <option key={qu.id} value={qu.id}>{qu.code} · {qu.customer_name ?? ""}</option>
              ))}
            </select>
          </Field>
        ) : (
          <>
            <Field label="Khách hàng">
              <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} className="dhb__select" style={{ width: "100%" }}>
                <option value="">— Chọn khách —</option>
                {custs.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                ))}
              </select>
            </Field>
            <div style={{ margin: "10px 0" }}>
              <span style={{ fontSize: 12, color: "var(--ash)", display: "block", marginBottom: 6 }}>Dòng hàng (nhập tay — không giá vốn, sẽ cần duyệt)</span>
              {lines.map((l, i) => (
                <div key={i} style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <input placeholder="Mô tả" value={l.description} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} style={{ ...inp, flex: 2 }} />
                  <input type="number" placeholder="SL" value={l.qty} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: Number(e.target.value) } : x)))} style={{ ...inp, width: 70 }} />
                  <input type="number" placeholder="Đơn giá" value={l.unit_price ?? 0} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, unit_price: Number(e.target.value) } : x)))} style={{ ...inp, width: 100 }} />
                </div>
              ))}
              <button className="btn btn--ghost" style={{ marginTop: 8, height: 28, padding: "4px 10px", fontSize: 12 }} onClick={() => setLines((ls) => [...ls, { description: "", qty: 1, unit_price: 0, vat_pct: 8 }])}>
                <Icon name="plus" size={13} /> Thêm dòng
              </button>
            </div>
          </>
        )}

        <Field label="Bản chất">
          <select value={nature} onChange={(e) => setNature(e.target.value)} className="dhb__select" style={{ width: "100%" }}>
            <option value="hang_hoa">Hàng hóa</option>
            <option value="gia_cong">Gia công (khách ứng giấy)</option>
          </select>
        </Field>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13, marginBottom: 12, cursor: "pointer", userSelect: "none" }}>
          <input type="checkbox" checked={isSupp} onChange={(e) => setIsSupp(e.target.checked)} /> Đơn bổ sung (in thêm — giữ kẽm cũ)
        </label>
        {isSupp && (
          <Field label="Đơn gốc (giữ kẽm)">
            <select value={parentId} onChange={(e) => setParentId(e.target.value)} className="dhb__select" style={{ width: "100%" }}>
              <option value="">— Chọn đơn gốc đã chốt —</option>
              {parents.map((p) => (
                <option key={p.id} value={p.id}>{p.order_no} · {p.customer_name ?? ""}</option>
              ))}
            </select>
          </Field>
        )}
        <Field label="% cọc (tùy chọn — báo giá: trống = ghim theo báo giá)"><input type="number" min={0} max={100} value={depositPct} onChange={(e) => setDepositPct(e.target.value)} placeholder="vd 30" style={inp} /></Field>
        <Field label="Số PO khách (tùy chọn)"><input value={po} onChange={(e) => setPo(e.target.value)} style={inp} /></Field>

        {err && <div className="banner banner--error">{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn btn--ghost" onClick={onClose} disabled={saving}>Hủy</button>
          <button className="btn btn--primary" onClick={submit} disabled={saving}>{saving ? "Đang tạo…" : "Tạo đơn"}</button>
        </div>
      </div>
    </div>
  );
}

function ConfirmPanel({ order, canManage, canExtend, onSaved }: { order: OrderDetail; canManage: boolean; canExtend: boolean; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function doConfirm() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      onSaved(await api.orders.confirm(token, order.id));
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  }
  async function doExtend() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      onSaved(await api.orders.extendQuote(token, order.id));
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {order.can_confirm ? (
        <div style={{ color: "#1f8a52", display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
          <Icon name="check" size={15} /> Đủ điều kiện chốt
        </div>
      ) : (
        <div style={{ display: "grid", gap: 4 }}>
          {order.confirm_blockers.map((b, i) => (
            <div key={i} style={{ color: "#b4432b", display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
              <Icon name="x" size={13} /> {b}
            </div>
          ))}
        </div>
      )}
      {order.quote_expired && canExtend && (
        <button className="btn btn--ghost" style={{ justifySelf: "start" }} disabled={busy} onClick={doExtend} title="Đặt lại hạn hiệu lực báo giá nguồn = hôm nay + 30 ngày">
          <Icon name="clock" size={14} /> Gia hạn báo giá (+30 ngày)
        </button>
      )}
      {err && <div className="banner banner--error">{err}</div>}
      {canManage && (
        <button className="btn btn--primary" style={{ justifySelf: "start" }} disabled={busy || !order.can_confirm} onClick={doConfirm}>
          <Icon name="check" size={15} /> Chốt đơn
        </button>
      )}
    </div>
  );
}

const APPROVAL_STATE_META: Record<string, { label: string; bg: string; fg: string }> = {
  none: { label: "Chưa trình", bg: "#eef1f6", fg: "#5a6a7d" },
  pending: { label: "Chờ duyệt", bg: "#fff3e0", fg: "#b4681f" },
  approved: { label: "Đã duyệt", bg: "#e4f5ec", fg: "#1f8a52" },
  rejected: { label: "Bị từ chối", bg: "#fdecea", fg: "#b4432b" },
};

function ApprovalPanel({ order, canApprove, onSaved }: { order: OrderDetail; canApprove: boolean; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const st = order.approval_state;
  const meta = APPROVAL_STATE_META[st] ?? APPROVAL_STATE_META.none;

  async function run(fn: () => Promise<OrderDetail>) {
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      onSaved(await fn());
      setNote("");
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "#7a8698", fontSize: 13 }}>Trạng thái</span>
        <span style={{ padding: "2px 9px", borderRadius: 999, background: meta.bg, color: meta.fg, fontSize: 12, fontWeight: 600 }}>{meta.label}</span>
      </div>
      {order.approvals.map((a) => (
        <div key={a.id} style={{ fontSize: 13, borderLeft: `3px solid ${a.decision === "approved" ? "#1f8a52" : "#b4432b"}`, paddingLeft: 8 }}>
          <strong>{a.decision === "approved" ? "Duyệt" : "Từ chối"}</strong> · {a.decided_by_name ?? "—"} ·{" "}
          {new Date(a.decided_at).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
          {a.note && <div style={{ color: "#5a6a7d" }}>{a.note}</div>}
        </div>
      ))}
      {err && <div className="banner banner--error">{err}</div>}
      {st !== "approved" &&
        (canApprove ? (
          <>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ghi chú / lý do (bắt buộc khi từ chối)" style={{ ...inp, minHeight: 52, resize: "vertical" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn--primary" disabled={busy || !note.trim()} onClick={() => run(() => api.orders.approve(token!, order.id, note))}>
                <Icon name="check" size={14} /> Duyệt
              </button>
              <button className="btn" disabled={busy || !note.trim()} onClick={() => run(() => api.orders.reject(token!, order.id, note))}>
                <Icon name="ban" size={14} /> Từ chối
              </button>
            </div>
          </>
        ) : (
          <button className="btn btn--primary" style={{ justifySelf: "start" }} disabled={busy} onClick={() => run(() => api.orders.submit(token!, order.id))}>
            <Icon name="send" size={14} /> {st === "rejected" ? "Trình duyệt lại" : "Trình duyệt"}
          </button>
        ))}
    </div>
  );
}

function DepositForm({ order, onSaved }: { order: OrderDetail; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState(String(Math.max(0, order.deposit_required - order.deposit_received)));
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const d = await api.orders.addDepositReceipt(token, order.id, {
        receipt_method: method,
        amount: Number(amount) || 0,
        receipt_date: date || null,
        note: note || null,
      });
      onSaved(d);
      setOpen(false);
      setAmount("");
      setNote("");
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  if (!open)
    return (
      <button className="btn" style={{ marginTop: 8 }} onClick={() => setOpen(true)}>
        <Icon name="plus" size={14} /> Lập phiếu thu cọc
      </button>
    );
  return (
    <div style={{ marginTop: 8, border: "1px solid #e6ebf1", borderRadius: 10, padding: 12, display: "grid", gap: 8 }}>
      <p style={{ margin: 0, fontSize: 12, color: "var(--ash)" }}>Lập Phiếu thu THẬT bên Kế toán, gắn đơn này (bấm = đã thu).</p>
      <Field label="Hình thức thu">
        <select value={method} onChange={(e) => setMethod(e.target.value)} style={inp}>
          {Object.entries(RECEIPT_METHOD_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </Field>
      <Field label="Số tiền thực thu"><input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} style={inp} /></Field>
      <Field label="Ngày thu"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={inp} /></Field>
      <Field label="Ghi chú"><input value={note} onChange={(e) => setNote(e.target.value)} style={inp} /></Field>
      {err && <div className="banner banner--error">{err}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn btn--ghost" onClick={() => setOpen(false)} disabled={saving}>Hủy</button>
        <button className="btn btn--primary" onClick={submit} disabled={saving}>{saving ? "Đang lập…" : "Lập phiếu thu"}</button>
      </div>
    </div>
  );
}

function AttachmentList({
  items, canEdit, onUpload, onDelete, addLabel,
}: {
  items: { id: number; url: string; file_name: string | null }[];
  canEdit: boolean;
  onUpload: (f: File) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  addLabel: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  async function pick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true);
    try { await onUpload(f); } finally { setBusy(false); if (ref.current) ref.current.value = ""; }
  }
  return (
    <div className="dhb__attachment-list">
      {items.map((a) => (
        <div key={a.id} className="dhb__attachment-item">
          <Icon name="fileText" size={13} style={{ color: "var(--ash)" }} />
          <a href={`${API_BASE}${a.url}`} target="_blank" rel="noreferrer" className="dhb__attachment-link">{a.file_name ?? "tệp"}</a>
          {canEdit && <button className="btn btn--ghost" style={{ height: 24, padding: "2px 6px" }} title="Xóa" onClick={() => onDelete(a.id)}><Icon name="trash" size={11} /></button>}
        </div>
      ))}
      {canEdit && (
        <>
          <input ref={ref} type="file" accept="image/*,application/pdf" style={{ display: "none" }} onChange={pick} />
          <button className="btn btn--ghost" style={{ justifySelf: "start", height: 28, padding: "4px 10px", fontSize: 12 }} disabled={busy} onClick={() => ref.current?.click()}>
            <Icon name="plus" size={12} /> {busy ? "Đang tải…" : addLabel}
          </button>
        </>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", marginBottom: 8 }}>
      <span style={{ display: "block", fontSize: 12, color: "#7a8698", marginBottom: 3 }}>{label}</span>
      {children}
    </label>
  );
}

const inp: React.CSSProperties = { width: "100%", padding: "8px 11px", borderRadius: 8, border: "1px solid #d7dee7", fontSize: 13, boxSizing: "border-box" };
