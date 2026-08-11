// Đơn hàng bán — redesign-don-hang-ban.md (P1: list + chi tiết + sửa thông tin đặt-hàng).
// Cọc/chốt/hủy = P2–P5. Icon dùng bộ Icon nhà (không emoji).
// Màn này KHÔNG tạo đơn: đơn sinh từ màn Báo giá khi khách chốt. Luồng duyệt đơn đặc thù đã gỡ.
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../components/Icons";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import {
  api,
  ApiError,
  type CustomerAddress,
  type CustomerContact,
  type LsxListItem,
  type OrderDetail,
  type OrderRow,
  type OrderStatsOut,
} from "../api/client";
import { DeliveryNotePrint } from "./DeliveryNotePrint";
import { gopTheoNhom } from "../utils/gop-nhom";
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
// VND rút gọn cho KPI (tránh số dài): ≥1 tỷ → "₫x,xx tỷ", ≥1 triệu → "₫x,x tr", còn lại đầy đủ.
function vndShort(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1_000_000_000) return "₫" + (v / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 }) + " tỷ";
  if (v >= 1_000_000) return "₫" + (v / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 }) + " tr";
  return vnd(v);
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
  clientFilter?: (o: OrderRow) => boolean;
  countKey?: keyof OrderStatsOut;
};
// Tab "Chờ duyệt" đã bỏ cùng luồng duyệt đơn đặc thù — nó chỉ đếm đơn nhập tay, mà đường tạo
// đơn tay đã gỡ nên tab đó vĩnh viễn rỗng.
const TABS: TabDef[] = [
  { id: "all", label: "Tất cả", countKey: "all" },
  { id: "draft", label: "Nháp", status: "draft", countKey: "draft" },
  { id: "awaiting_deposit", label: "Chờ cọc", status: "draft", clientFilter: (o) => !o.deposit_ok },
  { id: "ready", label: "Sẵn sàng chốt", status: "draft", clientFilter: (o) => o.deposit_ok },
  { id: "ordered", label: "Đã chốt", status: "ordered", countKey: "ordered" },
  { id: "cancelled", label: "Hủy", status: "cancelled", countKey: "cancelled" },
];

function Chip({ icon, label, tone }: { icon: IconName; label: string; tone: "warn" | "muted" | "info" | "rush" }) {
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
      {o.is_rush && <Chip icon="bell" label="GẤP" tone="rush" />}
      {/* "Chờ duyệt" + "Gia công" đã bỏ cùng luồng duyệt và trường Bản chất đơn.
          "Không giá vốn" GIỮ: đơn nhập tay CŨ (cost_basis='none') vẫn còn trong DB. */}
      {o.cost_basis === "none" && <Chip icon="help" label="Không giá vốn" tone="muted" />}
    </span>
  );
}

interface Props {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  openOrderId?: number | null;   // deep-link từ Báo giá ("Xem đơn") → mở drawer đơn vừa tạo
}

export function DonHangBanPage({ navigate, openOrderId }: Props) {
  const { token } = useAuth();
  const can = useCan();
  // `create` KHÔNG còn được dùng ở màn này (đơn sinh từ Báo giá) — quyền vẫn tồn tại, gác ở đó.
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
  // `/enums` không còn được nạp ở đây: nó chỉ phục vụ hộp thoại tạo đơn (đã xoá). Nhãn trạng thái
  // dùng bảng STATUS_META tĩnh phía trên.

  const [selected, setSelected] = useState<OrderDetail | null>(null);
  const [stats, setStats] = useState<OrderStatsOut | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    const t = TABS.find((x) => x.id === tab) ?? TABS[0];
    setLoading(true);
    setErr(null);
    api.orders
      .list(token, {
        q: q || undefined, status: t.status,
        sort: "-created_at", page: 1, size: 50,
      })
      .then((r) => {
        const rows = t.clientFilter ? r.items.filter(t.clientFilter) : r.items;
        setRows(rows);
        setTotal(t.clientFilter ? rows.length : r.total);
      })
      .catch((e) => setErr(String(e?.message ?? e)))
      .finally(() => setLoading(false));
    api.orders.stats(token).then(setStats).catch(() => {});
  }, [token, q, tab]);

  useEffect(() => {
    load();
  }, [load]);

  function openDetail(id: number) {
    if (!token) return;
    api.orders.get(token, id).then(setSelected).catch((e) => setErr(String(e?.message ?? e)));
  }

  // Deep-link từ Báo giá (nút "Xem đơn" sau khi tạo đơn) → mở drawer đơn ngay khi vào màn.
  useEffect(() => {
    if (token && openOrderId) openDetail(openOrderId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, openOrderId]);

  return (
    <main className="dhb-container">
      <header className="dhb__header">
        <div className="dhb__title-group">
          <p className="eyebrow">Kinh doanh</p>
          <h1 className="dhb__title">Đơn hàng bán</h1>
        </div>
        {/* Nút "+ Tạo đơn" đã gỡ: đơn CHỈ sinh từ màn Báo giá khi khách chốt (BaoGiaPage →
            api.orders.create). Giữ nút ở đây là cửa thứ hai làm cùng một việc. */}
      </header>

      {stats && <KpiStrip stats={stats} />}

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
                  <td className="dhb__val">{vnd(o.total_with_vat)}</td>
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
    </main>
  );
}

// KPI đầu list — tóm tắt tiền/đếm rule-based từ `stats` (aggregate backend, chính xác toàn hệ).
function KpiStrip({ stats }: { stats: OrderStatsOut }) {
  return (
    <div className="dhb__kpis">
      <div className="dhb__kpi">
        <div className="dhb__kpi-l"><Icon name="fileText" size={13} /> Tổng đơn</div>
        <div className="dhb__kpi-n">{stats.all}</div>
        <div className="dhb__kpi-s">{stats.ordered} đã chốt</div>
      </div>
      <div className="dhb__kpi">
        <div className="dhb__kpi-l"><Icon name="clock" size={13} /> Chờ cọc</div>
        <div className="dhb__kpi-n">{stats.awaiting_deposit}<span className="dhb__kpi-u"> đơn</span></div>
        <div className="dhb__kpi-s" style={{ color: stats.deposit_shortfall > 0 ? "var(--amber-deep)" : undefined }}>
          cần thu {vndShort(stats.deposit_shortfall)}
        </div>
      </div>
      <div className="dhb__kpi">
        <div className="dhb__kpi-l"><Icon name="check" size={13} /> Giá trị đã chốt</div>
        <div className="dhb__kpi-n" style={{ fontFamily: "var(--ff-num)", fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{vndShort(stats.ordered_value)}</div>
        <div className="dhb__kpi-s">{stats.ordered} đơn</div>
      </div>
      {/* Thẻ "Chờ duyệt · đơn đặc thù" đã bỏ cùng luồng duyệt — nó chỉ đếm đơn nhập tay. */}
    </div>
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
  const [showPrint, setShowPrint] = useState(false);
  const canCancel = (order.status === "draft" && canUpdate) || (order.status === "ordered" && canApproveException);

  async function upConsent(f: File) { if (token) onSaved(await api.orders.uploadConsent(token, order.id, f)); }
  async function delConsent(aid: number) { if (token) onSaved(await api.orders.deleteConsent(token, order.id, aid)); }
  const [acts, setActs] = useState<{ at: string; actor_name: string | null; action: string; detail: string }[]>([]);
  const isDraft = order.status === "draft";
  const [drawerTab, setDrawerTab] = useState<"overview" | "commercial" | "history">("overview");

  const isChotDone = order.status === "ordered" || order.ordered_at != null;
  // Vòng đời: CHỐT (thông tin) → CỌC (kế toán thu, SAU chốt) → SẢN XUẤT. Cọc 'xong' = đã chốt VÀ
  // (không cần cọc HOẶC thu đủ). Trước chốt → cọc chưa tới lượt.
  const noDeposit = order.deposit_required <= 0;
  const isCocDone = isChotDone && order.deposit_ok;
  const remaining = Math.max(0, order.deposit_required - order.deposit_received);

  // Bước Sản xuất — đọc LỆNH THẬT của bàn Kế hoạch SX (`/api/lsx`). Chưa chuyển → chờ kế hoạch lên
  // lệnh → đang chạy. "Xong" thuộc pha THỰC THI (nhập kho thành phẩm) — chưa dựng nên luôn false,
  // đừng suy ra từ trạng thái lệnh ở lát này.
  const [lenhs, setLenhs] = useState<LsxListItem[]>([]);
  useEffect(() => {
    if (!token || order.status !== "ordered" || !order.san_xuat_released_at) {
      setLenhs([]);
      return;
    }
    api.lsx.list(token, { order_id: order.id }).then((r) => setLenhs(r.items)).catch(() => setLenhs([]));
  }, [token, order.id, order.status, order.san_xuat_released_at]);
  const sxReleased = !!order.san_xuat_released_at;
  const sxDone = false;
  const sxState: "chua" | "cho_kh" | "chay" =
    !sxReleased ? "chua" : lenhs.length === 0 ? "cho_kh" : "chay";
  const sxText = { chua: "chưa chuyển", cho_kh: "chờ kế hoạch", chay: "đang chạy" }[sxState];

  const doneSeg = (isChotDone ? 1 : 0) + (isCocDone ? 1 : 0) + (sxDone ? 1 : 0);

  const chotDate = order.ordered_at ? fmtDate(order.ordered_at) : (order.created_at ? fmtDate(order.created_at) : "—");
  const cocText = !isChotDone ? "chưa tới" : noDeposit ? "không cần cọc" : order.deposit_ok ? "đủ" : "chờ cọc";

  const [activeStep, setActiveStep] = useState<"coc" | "chot" | "sanxuat" | "giao" | "hoadon">("coc");

  useEffect(() => {
    if (token) api.orders.activity(token, order.id).then((r) => setActs(r.items)).catch(() => {});
  }, [token, order.id]);

  useEffect(() => {
    const defaultStep = !isChotDone ? "chot" : !isCocDone ? "coc" : !sxDone ? "sanxuat" : "giao";
    setActiveStep(defaultStep);
  }, [order.id, isChotDone, isCocDone, sxDone]);

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
          <div className="dhb__drawer-headmain">
            <div className="dhb__drawer-headtop">
              <h2 className="dhb__drawer-title">{order.order_no}</h2>
              <StatusBadge status={order.status} />
              {order.source_type === "bao_gia" && order.quotation_code && (
                <Chip icon="fileText" label={order.quotation_code} tone="muted" />
              )}
              <RowFlags o={order} />
            </div>
            <div className="dhb__drawer-cust"><Icon name="users" size={13} /> {order.customer_name ?? "—"}</div>
          </div>
          <button className="btn btn--secondary" style={{ height: 32 }} onClick={() => setShowPrint(true)}><Icon name="printer" size={14} /> Xem bản in</button>
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
                  <KV k="NV phụ trách" v={order.sale_name ?? "—"} />
                  <KV k="Ngày tạo" v={<span className="dhb__mono">{fmtDate(order.created_at)}</span>} />
                  {order.ordered_at && <KV k="Ngày chốt" v={<span className="dhb__mono">{fmtDate(order.ordered_at)}</span>} />}
                  {/* Luôn hiện thông tin đặt hàng/giao (trống = "—") để đơn đã chốt vẫn xem được đủ. */}
                  <KV k="Số PO khách" v={order.customer_po_no ? <span className="dhb__mono">{order.customer_po_no}</span> : "—"} />
                  <KV k="Ngày giao cam kết" v={<span className="dhb__mono">{fmtDate(order.delivery_committed_date)}</span>} />
                  <KV k="Địa chỉ giao" v={order.delivery_address || "—"} />
                  <KV
                    k="Người nhận"
                    v={[order.delivery_contact_name, order.delivery_contact_phone].filter(Boolean).join(" · ") || "—"}
                  />
                  <KV k="Lưu ý giao" v={order.delivery_note || "—"} />
                  {!(order.status === "ordered" && canUpdate) && (
                    <KV k="Lưu ý SX" v={order.production_note || "—"} />
                  )}
                  <KV k="% cọc" v={<span className="dhb__mono">{order.deposit_pct != null ? `${order.deposit_pct}%` : "—"}</span>} />
                </div>
                {editing && (
                  <div style={{ marginTop: 12 }}>
                    <EditForm order={order} onCancel={() => setEditing(false)} onSaved={(d) => { setEditing(false); onSaved(d); }} />
                  </div>
                )}
              </Section>

              {/* Lưu ý sản xuất — sửa được cả khi đã chốt (đường hẹp D3 → realtime bàn Kế hoạch) */}
              {order.status === "ordered" && canUpdate && (
                <ProductionHintEditor order={order} onSaved={onSaved} />
              )}

              {/* Vòng đời đơn */}
              <Section title="Vòng đời đơn">
                <div className="dhb__lifecycle-header">
                  <span className="dhb__lifecycle-subtitle">read-only · bấm chọn từng bước để xem chi tiết</span>
                </div>
                
                {/* 1. Timeline — Chốt (thông tin) → Cọc (kế toán thu) → Sản xuất → Giao → Hóa đơn */}
                <div className="dhb__timeline">
                  <div className="dhb__timeline-track" />
                  <div className="dhb__timeline-fill" style={{ width: `${(doneSeg / 4) * 100}%` }} />
                  <div
                    className={`dhb__timeline-step ${isChotDone ? "is-done" : ""} ${activeStep === "chot" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("chot")}
                  >
                    <div className="dhb__timeline-dot">{isChotDone ? <Icon name="check" size={12} /> : "1"}</div>
                    <span className="dhb__timeline-label">Chốt</span>
                    <span className="dhb__timeline-sub">{isChotDone ? chotDate : "chưa chốt"}</span>
                  </div>
                  <div
                    className={`dhb__timeline-step ${isCocDone ? "is-done" : ""} ${activeStep === "coc" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("coc")}
                  >
                    <div className="dhb__timeline-dot">{isCocDone ? <Icon name="check" size={12} /> : "2"}</div>
                    <span className="dhb__timeline-label">Cọc</span>
                    <span className="dhb__timeline-sub">{cocText}</span>
                  </div>
                  <div
                    className={`dhb__timeline-step ${sxDone ? "is-done" : ""} ${activeStep === "sanxuat" ? "is-selected" : ""}`}
                    onClick={() => setActiveStep("sanxuat")}
                  >
                    <div className="dhb__timeline-dot">{sxDone ? <Icon name="check" size={12} /> : "3"}</div>
                    <span className="dhb__timeline-label">Sản xuất</span>
                    <span className="dhb__timeline-sub">{isChotDone ? sxText : "—"}</span>
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
                          <p style={{ color: "var(--ash)", fontSize: 12, margin: "6px 0 0" }}>Bước tiếp: bấm “Sản xuất” để chuyển đơn xuống kế hoạch.</p>
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
                      <h4 className="dhb__lifecycle-box-title">Cọc &amp; thu tiền</h4>
                      <span className={`dhb__lifecycle-badge ${isCocDone ? "dhb__lifecycle-badge--done" : !isChotDone ? "dhb__lifecycle-badge--upcoming" : "dhb__lifecycle-badge--active"}`}>
                        {!isChotDone ? "CHƯA TỚI" : isCocDone ? "ĐỦ CỌC" : "CHỜ CỌC"}
                      </span>
                    </div>
                    <div className="dhb__stat-trio">
                      <div className="dhb__stat"><div className="dhb__stat-l">Cần thu{order.deposit_pct != null ? ` (${order.deposit_pct}%)` : ""}</div><div className="dhb__stat-n">{vnd(order.deposit_required)}</div></div>
                      <div className="dhb__stat"><div className="dhb__stat-l">Đã thu</div><div className="dhb__stat-n" style={{ color: isCocDone ? "var(--moss-deep)" : undefined }}>{vnd(order.deposit_received)}</div></div>
                      <div className="dhb__stat"><div className="dhb__stat-l">Còn thiếu</div><div className="dhb__stat-n" style={{ color: remaining > 0 ? "var(--amber-deep)" : undefined }}>{vnd(remaining)}</div></div>
                    </div>
                    <div style={{ margin: "4px 0" }}><DepositBar o={order} /></div>
                    {order.deposits.length > 0 && (
                      <div style={{ display: "grid", gap: 6, marginTop: 4 }}>
                        {order.deposits.map((d) => (
                          <div key={d.id} className="dhb__receipt-row">
                            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                              <strong className="dhb__mono" style={{ fontSize: 14, color: "var(--ink)" }}>{vnd(d.amount)}</strong>
                              <span style={{ color: "var(--ash-2)" }}>{RECEIPT_METHOD_LABELS[d.receipt_method] ?? d.receipt_method}</span>
                              {d.status === "received" && (
                                <span style={{ color: "var(--moss)", display: "inline-flex", gap: 2, alignItems: "center" }}><Icon name="check" size={12} /> đã thu</span>
                              )}
                              {d.receipt_date && <span style={{ color: "var(--ash-2)" }} className="dhb__mono">{fmtDate(d.receipt_date)}</span>}
                              <div style={{ flex: 1 }} />
                              <button type="button" className="link dhb__mono"
                                style={{ color: "var(--rust)", background: "none", border: 0, padding: 0, cursor: "pointer", fontWeight: 600 }}
                                title="Mở phiếu thu này bên Kế toán"
                                onClick={() => navigate?.("ke-toan-phieu-thu", { focusReceiptQuery: d.code })}>
                                {d.doc_no ?? d.code} ↗
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {order.deposits.length === 0 && (
                      <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--ash-2)" }}>Chưa có phiếu thu cọc nào.</p>
                    )}
                    {!isChotDone ? (
                      <p style={{ color: "var(--ash)", fontSize: 12, margin: "4px 0 0" }}>
                        Đơn phải CHỐT (đủ thông tin) trước — sau chốt kế toán thu cọc ở bước này.
                      </p>
                    ) : isCocDone ? (
                      <p style={{ color: "var(--moss-deep)", fontSize: 12, margin: "4px 0 0" }}>
                        Đã đủ cọc — Sale chuyển đơn xuống sản xuất ở bước “Sản xuất”.
                      </p>
                    ) : canRecordDeposit ? (
                      <DepositForm order={order} onSaved={onSaved} />
                    ) : (
                      <p style={{ color: "var(--ash)", fontSize: 12, margin: "4px 0 0" }}>Chờ kế toán thu cọc.</p>
                    )}
                  </div>
                )}
 
 
                {activeStep === "sanxuat" && (
                  <div className="dhb__lifecycle-box">
                    <div className="dhb__lifecycle-box-header">
                      <h4 className="dhb__lifecycle-box-title">Sản xuất</h4>
                      <span className={`dhb__lifecycle-badge ${sxDone ? "dhb__lifecycle-badge--done" : sxReleased ? "dhb__lifecycle-badge--active" : "dhb__lifecycle-badge--upcoming"}`}>
                        {sxText.toUpperCase()}
                      </span>
                    </div>
                    <div style={{ marginTop: 4 }}>
                      {order.status !== "ordered" ? (
                        <p style={{ color: "var(--ash)", fontSize: 12, margin: 0 }}>Đơn phải chốt trước mới chuyển xuống sản xuất được.</p>
                      ) : !sxReleased ? (
                        order.deposit_ok ? (
                          <ReleaseSXButton order={order} canUpdate={canUpdate} onSaved={onSaved} />
                        ) : (
                          <p style={{ color: "var(--amber-deep)", fontSize: 12, margin: 0 }}>
                            Chờ kế toán thu đủ cọc (bước “Cọc”) — đủ cọc rồi mới bật nút “Chuyển xuống sản xuất”.
                          </p>
                        )
                      ) : (
                        <div style={{ display: "grid", gap: 4 }}>
                          <KV k="Trạng thái" v={sxText} />
                          <KV k="Chuyển lúc" v={<span className="dhb__mono">{fmtDate(order.san_xuat_released_at)}</span>} />
                          {lenhs.length > 0 && (
                            <KV
                              k="Lệnh SX"
                              v={`${lenhs.length} lệnh · ${lenhs.filter((l) => l.trang_thai === "san_sang").length} sẵn sàng`}
                            />
                          )}
                          <p style={{ color: "var(--ash)", fontSize: 12, margin: "2px 0 0" }}>
                            {sxState === "cho_kh"
                              ? "Đang chờ Kế hoạch lên lệnh sản xuất."
                              : "Kế hoạch đã lên lệnh — bước này XONG khi nhập kho thành phẩm."}
                          </p>
                          <button
                            type="button"
                            className="link dhb__mono"
                            style={{ color: "var(--rust)", background: "none", border: 0, padding: 0, cursor: "pointer", fontWeight: 600, justifySelf: "start" }}
                            onClick={() => navigate?.("ke-hoach-sx", { openSxOrderId: order.id })}
                          >
                            Mở bàn Kế hoạch sản xuất ↗
                          </button>
                        </div>
                      )}
                    </div>
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
              {/* Khối ⑤ "Duyệt đơn đặc thù" đã gỡ cùng luồng duyệt. */}
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
                    {/* Khối THƯƠNG MẠI = mặt đối ngoại của đơn → gộp theo nhãn nhóm y như báo giá
                        khách đã nhận (ruột + bìa = 1 quyển). Dòng thật vẫn nguyên ở dưới DB để
                        sản xuất sinh lệnh riêng cho từng phần. */}
                    {gopTheoNhom(order.lines, (l) => ({
                      nhom: l.nhom,
                      ten: l.description,
                      soLuong: l.qty,
                      donViTinh: l.don_vi_tinh || "",
                      thanhTien: l.line_total ?? 0,
                      tienVat: 0,
                      vatPct: l.vat_pct_estimate,
                    })).flatMap((g) => {
                      const dongLe = g.goc.length === 1;
                      return [
                        <tr key={g.key} className={dongLe ? undefined : "dhb__comm-nhom"}>
                          <td>
                            {g.ten}
                            {!dongLe && (
                              <span className="dhb__comm-nhomSub">{g.goc.length} phần</span>
                            )}
                          </td>
                          <td className="dhb__mono dhb__text-right">{g.soLuong.toLocaleString("vi-VN")}{g.donViTinh ? ` ${g.donViTinh}` : ""}</td>
                          <td className="dhb__mono dhb__text-right">{vnd(g.donGia)}</td>
                          <td className="dhb__mono dhb__text-right">{g.vatPct === null ? "—" : `${g.vatPct}%`}</td>
                          <td className="dhb__mono dhb__text-right">{vnd(g.thanhTien)}</td>
                        </tr>,
                        // Nhóm thì SỔ ra từng phần (ruột, bìa) — người trong nhà cần thấy đủ,
                        // khách chỉ thấy dòng gộp trên bản in.
                        ...(dongLe
                          ? []
                          : g.goc.map((l, k) => (
                              <tr
                                key={`${g.key}-${l.id}`}
                                className={`dhb__comm-con${k === g.goc.length - 1 ? " dhb__comm-conCuoi" : ""}`}
                              >
                                <td>{l.description}</td>
                                <td className="dhb__mono dhb__text-right">{l.qty.toLocaleString("vi-VN")}{l.don_vi_tinh ? ` ${l.don_vi_tinh}` : ""}</td>
                                <td className="dhb__mono dhb__text-right">{vnd(l.unit_price_snapshot)}</td>
                                <td className="dhb__mono dhb__text-right">{l.vat_pct_estimate}%</td>
                                <td className="dhb__mono dhb__text-right">{vnd(l.line_total)}</td>
                              </tr>
                            ))),
                      ];
                    })}
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
        {showPrint && <DeliveryNotePrint d={order} onClose={() => setShowPrint(false)} />}
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
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Nêu lý do; nếu đã chốt, kể luôn tình trạng lúc hủy (vd: đã ra kẽm, khách đổi ý)." className="dhb__input" style={{ minHeight: 60, resize: "vertical" }} />
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

// D3: Sale đổi GẤP / lưu ý SX SAU khi đơn đã CHỐT (đơn khóa sửa) → đường hẹp production-hint →
// backend broadcast → bàn Kế hoạch "ting" (badge nhảy). Chỉ 2 field, không đụng phần còn lại của đơn.
function ProductionHintEditor({ order, onSaved }: { order: OrderDetail; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [isRush, setIsRush] = useState(order.is_rush);
  const [note, setNote] = useState(order.production_note ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const dirty = isRush !== order.is_rush || note.trim() !== (order.production_note ?? "");

  async function save() {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const d = await api.orders.updateProductionHint(token, order.id, {
        is_rush: isRush,
        production_note: note.trim(),
      });
      onSaved(d);
      setSaved(true);
      setOpen(false);
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Section title="Lưu ý sản xuất (gửi xưởng)">
      {!open ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            {order.is_rush ? <Chip icon="bell" label="GẤP" tone="rush" /> : null}
            <span style={{ fontSize: 13, color: order.production_note ? "var(--ink)" : "var(--ash)" }}>
              {order.production_note || "Chưa có lưu ý gửi xưởng"}
            </span>
          </div>
          <button
            type="button"
            className="btn btn--ghost"
            style={{ padding: "4px 12px", fontSize: 12, flex: "none" }}
            onClick={() => { setIsRush(order.is_rush); setNote(order.production_note ?? ""); setSaved(false); setOpen(true); }}
          >
            Sửa
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
            <input type="checkbox" checked={isRush} onChange={(e) => setIsRush(e.target.checked)} />
            <span>Đánh dấu <strong>GẤP</strong> — ưu tiên ở xưởng</span>
          </label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Lưu ý cho xưởng in (vd: in test màu trước, giấy khách ứng…)"
            className="dhb__input"
            style={{ minHeight: 60, resize: "vertical" }}
          />
          {err && <div className="banner banner--error">{err}</div>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="btn btn--ghost" onClick={() => setOpen(false)} disabled={saving}>Đóng</button>
            <button className="btn btn--primary" onClick={save} disabled={saving || !dirty}>
              {saving ? "Đang lưu…" : "Lưu & báo xưởng"}
            </button>
          </div>
        </div>
      )}
      {saved && !open ? (
        <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--moss, #2f5d3a)" }}>
          Đã cập nhật — bàn kế hoạch nhận ngay.
        </p>
      ) : null}
    </Section>
  );
}

// Handoff: Sale "Chuyển xuống sản xuất" — đơn đã chốt (đủ cọc) → vào hàng chờ Kế hoạch (người quyết).
function ReleaseSXButton({ order, canUpdate, onSaved }: { order: OrderDetail; canUpdate: boolean; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function go() {
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      onSaved(await api.orders.releaseProduction(token, order.id));
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <p style={{ color: "var(--ash)", fontSize: 12, margin: 0 }}>Đơn đã chốt &amp; đủ cọc — đẩy vào hàng chờ Kế hoạch sản xuất.</p>
      {err && <div className="banner banner--error">{err}</div>}
      <button className="btn btn--primary" onClick={go} disabled={busy || !canUpdate} style={{ justifySelf: "start" }}>
        {busy ? "Đang chuyển…" : "Chuyển xuống sản xuất →"}
      </button>
    </div>
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
  const [contactName, setContactName] = useState(order.delivery_contact_name ?? "");
  const [contactPhone, setContactPhone] = useState(order.delivery_contact_phone ?? "");
  const [pickedContactId, setPickedContactId] = useState("");
  const [contacts, setContacts] = useState<CustomerContact[]>([]);
  const [pickedAddrId, setPickedAddrId] = useState("");
  const [addresses, setAddresses] = useState<CustomerAddress[]>([]);
  const [deliveryNote, setDeliveryNote] = useState(order.delivery_note ?? "");
  const [productionNote, setProductionNote] = useState(order.production_note ?? "");
  const [isRush, setIsRush] = useState(order.is_rush);
  const [depositPct, setDepositPct] = useState(order.deposit_pct != null ? String(order.deposit_pct) : "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Xổ danh bạ + điểm giao của khách → AUTO-FILL người liên hệ CHÍNH + địa chỉ MẶC ĐỊNH khi ô đang
  // trống (đơn chưa có sẵn). Vẫn cho Sale đổi/sửa tay. Không đè giá trị đã lưu trên đơn.
  useEffect(() => {
    if (!token || order.customer_id == null) return;
    api.customers.contacts(token, order.customer_id).then((r) => {
      setContacts(r.items);
      const primary = r.items.find((c) => c.is_primary) ?? r.items[0];
      if (primary && !order.delivery_contact_name && !order.delivery_contact_phone) {
        setContactName((v) => v || primary.name);
        setContactPhone((v) => v || (primary.phone ?? ""));
        setPickedContactId(String(primary.id));
      }
    }).catch(() => {});
    api.customers.addresses(token, order.customer_id).then((r) => {
      setAddresses(r.items);
      const def = r.items.find((a) => a.is_default) ?? r.items[0];
      if (def && !order.delivery_address) {
        setAddr((v) => v || def.address);
        setPickedAddrId(String(def.id));
      }
    }).catch(() => {});
  }, [token, order.customer_id, order.delivery_contact_name, order.delivery_contact_phone, order.delivery_address]);

  // Chọn 1 liên hệ trong danh bạ → điền tên + SĐT (vẫn cho sửa tay 2 ô bên dưới).
  function pickContact(id: string) {
    setPickedContactId(id);
    const c = contacts.find((x) => String(x.id) === id);
    if (c) {
      setContactName(c.name);
      setContactPhone(c.phone ?? "");
    }
  }

  // Chọn 1 điểm giao đã lưu → điền địa chỉ (vẫn sửa tay được).
  function pickAddress(id: string) {
    setPickedAddrId(id);
    const a = addresses.find((x) => String(x.id) === id);
    if (a) setAddr(a.address);
  }

  async function save() {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const d = await api.orders.update(token, order.id, {
        customer_po_no: po || null,
        delivery_committed_date: date || null,
        delivery_address: addr || null,
        delivery_contact_name: contactName.trim() || null,
        delivery_contact_phone: contactPhone.trim() || null,
        delivery_note: deliveryNote.trim() || null,
        production_note: productionNote.trim() || null,
        is_rush: isRush,
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
      <Field label="Số PO khách"><input value={po} onChange={(e) => setPo(e.target.value)} className="dhb__input" /></Field>
      <Field label="% cọc"><input type="number" min={0} max={100} value={depositPct} onChange={(e) => setDepositPct(e.target.value)} placeholder="vd 30" className="dhb__input" /></Field>
      <Field label="Ngày giao cam kết"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="dhb__input" /></Field>
      {/* Địa chỉ giao + người nhận LUÔN hiện, và LẤY TỪ HỒ SƠ KHÁCH — không gõ tay ở đơn (gõ tay
          là đẻ dữ liệu khách nằm rải rác ngoài hồ sơ). Khách chưa khai thì dropdown vẫn hiện,
          sổ xuống rỗng kèm lời nhắc sang màn Khách hàng khai trước. */}
      <Field label="Địa chỉ giao">
        <select
          value={pickedAddrId}
          onChange={(e) => pickAddress(e.target.value)}
          className="dhb__select"
          style={{ width: "100%" }}
        >
          <option value="">
            {addresses.length > 0 ? "— Chọn điểm giao —" : "— Khách chưa khai điểm giao —"}
          </option>
          {addresses.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}{a.address ? ` · ${a.address}` : ""}{a.is_default ? " (mặc định)" : ""}
            </option>
          ))}
        </select>
        {addr && <div className="dhb__pick-echo">{addr}</div>}
      </Field>
      <Field label="Người nhận">
        <select
          value={pickedContactId}
          onChange={(e) => pickContact(e.target.value)}
          className="dhb__select"
          style={{ width: "100%" }}
        >
          <option value="">
            {contacts.length > 0 ? "— Chọn liên hệ —" : "— Khách chưa có danh bạ liên hệ —"}
          </option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}{c.phone ? ` · ${c.phone}` : ""}{c.is_primary ? " (liên hệ chính)" : ""}
            </option>
          ))}
        </select>
        {(contactName || contactPhone) && (
          <div className="dhb__pick-echo">
            {[contactName, contactPhone].filter(Boolean).join(" · ")}
          </div>
        )}
      </Field>
      <Field label="Lưu ý giao hàng"><textarea value={deliveryNote} onChange={(e) => setDeliveryNote(e.target.value)} placeholder="Dặn tài xế / khâu giao (giờ giao, tầng, gọi trước…)" className="dhb__input" style={{ minHeight: 56, resize: "vertical" }} /></Field>
      <Field label="Lưu ý sản xuất"><textarea value={productionNote} onChange={(e) => setProductionNote(e.target.value)} placeholder="Dặn tổ in / xưởng (canh màu, cấn bế, gia công…)" className="dhb__input" style={{ minHeight: 56, resize: "vertical" }} /></Field>
      <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13, cursor: "pointer", userSelect: "none" }}>
        <input type="checkbox" checked={isRush} onChange={(e) => setIsRush(e.target.checked)} /> Hàng gấp (ưu tiên sản xuất)
      </label>
      {/* 3 ô "Bản chất đơn" · "Pháp nhân xuất HĐ" · "MST xuất HĐ" đã gỡ (2026-08-04). */}
      {err && <div className="banner banner--error">{err}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn btn--ghost" onClick={onCancel} disabled={saving}>Hủy</button>
        <button className="btn btn--primary" onClick={save} disabled={saving}>{saving ? "Đang lưu…" : "Lưu"}</button>
      </div>
    </div>
  );
}

// Modal "Tạo đơn hàng" đã XOÁ: đơn chỉ sinh từ màn Báo giá khi khách chốt.

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

// `ApprovalPanel` + `APPROVAL_STATE_META` đã XOÁ cùng luồng duyệt đơn đặc thù.

function DepositForm({ order, onSaved }: { order: OrderDetail; onSaved: (d: OrderDetail) => void }) {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const remaining = Math.max(0, order.deposit_required - order.deposit_received);
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState(String(remaining));
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
    <div style={{ marginTop: 8, border: "1px solid var(--rule-soft)", borderRadius: "var(--r-3)", padding: 12, display: "grid", gap: 8 }}>
      <p style={{ margin: 0, fontSize: 12, color: "var(--ash)" }}>
        Lập Phiếu thu THẬT bên Kế toán, gắn đơn này (bấm = đã thu).
        {remaining > 0 && <> Còn thiếu <strong className="dhb__mono" style={{ color: "var(--ink)" }}>{vnd(remaining)}</strong>.</>}
      </p>
      <Field label="Hình thức thu">
        <select value={method} onChange={(e) => setMethod(e.target.value)} className="dhb__select" style={{ width: "100%" }}>
          {Object.entries(RECEIPT_METHOD_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </Field>
      <Field label="Số tiền thực thu">
        <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="dhb__input" />
        {Number(amount) > 0 && <div className="dhb__mono" style={{ fontSize: 12, color: "var(--ash-2)", marginTop: 2 }}>= {vnd(Number(amount))}</div>}
      </Field>
      <Field label="Ngày thu"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="dhb__input" /></Field>
      <Field label="Ghi chú"><input value={note} onChange={(e) => setNote(e.target.value)} className="dhb__input" /></Field>
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
      <span style={{ display: "block", fontSize: 12, color: "var(--ash)", marginBottom: 3 }}>{label}</span>
      {children}
    </label>
  );
}
