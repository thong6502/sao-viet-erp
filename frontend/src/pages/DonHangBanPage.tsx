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
} from "../api/client";

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

const DEPOSIT_KIND_LABELS: Record<string, string> = {
  ck: "Chuyển khoản",
  tien_mat: "Tiền mặt",
  vat_tu_ung: "Vật tư khách ứng",
  can_tru_cong_no: "Cấn trừ công nợ",
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
  const c =
    tone === "warn"
      ? { bg: "#fff3e0", fg: "#b4681f" }
      : tone === "info"
      ? { bg: "#e7f0fb", fg: "#2b6cb0" }
      : { bg: "#eef1f6", fg: "#5a6a7d" };
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: 4, padding: "1px 7px",
        borderRadius: 999, background: c.bg, color: c.fg, fontSize: 11, fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      <Icon name={icon} size={12} /> {label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status, bg: "#eef1f6", fg: "#48566a" };
  return (
    <span style={{ padding: "2px 9px", borderRadius: 999, background: m.bg, color: m.fg, fontSize: 12, fontWeight: 600 }}>
      {m.label}
    </span>
  );
}

function RowFlags({ o }: { o: OrderRow }) {
  return (
    <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap" }}>
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
    <main style={{ padding: "28px 32px", maxWidth: 1180 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div>
          <p className="eyebrow">Kinh doanh</p>
          <h1 style={{ margin: "4px 0 0" }}>Đơn hàng bán</h1>
        </div>
        {canCreate && (
          <button className="btn btn--primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={16} /> Tạo đơn
          </button>
        )}
      </div>

      {/* Tabs + tìm */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "18px 0 10px", flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: "6px 13px", borderRadius: 999, border: "1px solid",
              borderColor: tab === t.id ? "#2b3a4d" : "#d7dee7",
              background: tab === t.id ? "#2b3a4d" : "#fff",
              color: tab === t.id ? "#fff" : "#48566a", fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}
          >
            {t.label}{t.countKey && stats ? ` · ${stats[t.countKey]}` : ""}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <select value={viewScope} onChange={(e) => setViewScope(e.target.value)} title="Phạm vi dữ liệu"
          style={{ padding: "7px 10px", borderRadius: 8, border: "1px solid #d7dee7", fontSize: 13, color: "#48566a" }}>
          <option value="">Phạm vi</option>
          <option value="own">Của tôi</option>
          <option value="department">Cả phòng</option>
          <option value="all">Tất cả</option>
        </select>
        <div style={{ position: "relative" }}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã / khách / PO…"
            style={{ padding: "7px 12px 7px 32px", borderRadius: 8, border: "1px solid #d7dee7", fontSize: 13, minWidth: 240 }}
          />
          <span style={{ position: "absolute", left: 10, top: 8, color: "#8a97a8" }}>
            <Icon name="search" size={15} />
          </span>
        </div>
      </div>

      {err && <div className="banner banner--error" role="alert">{err}</div>}

      {/* Bảng */}
      <div style={{ border: "1px solid #e6ebf1", borderRadius: 12, overflow: "hidden", background: "#fff" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f7f9fc", textAlign: "left", color: "#5a6a7d" }}>
              <th style={th}>Mã đơn</th>
              <th style={th}>Khách hàng</th>
              <th style={th}>Nguồn</th>
              <th style={{ ...th, textAlign: "right" }}>Giá trị</th>
              <th style={th}>Cọc</th>
              <th style={th}>Ngày giao</th>
              <th style={th}>NV</th>
              <th style={th}>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} style={{ padding: 24, textAlign: "center", color: "#8a97a8" }}>Đang tải…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={8} style={{ padding: 24, textAlign: "center", color: "#8a97a8" }}>Chưa có đơn hàng.</td></tr>
            )}
            {!loading &&
              rows.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => openDetail(o.id)}
                  style={{ borderTop: "1px solid #eef1f6", cursor: "pointer" }}
                >
                  <td style={td}>
                    <strong>{o.order_no}</strong>
                    <div style={{ marginTop: 3 }}><RowFlags o={o} /></div>
                  </td>
                  <td style={td}>{o.customer_name ?? "—"}</td>
                  <td style={td}>
                    {o.source_type === "bao_gia" ? (
                      <span style={{ color: "#2b6cb0" }}>{o.quotation_code ?? "—"}</span>
                    ) : (
                      "Nhập tay"
                    )}
                  </td>
                  <td style={{ ...td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {vnd(o.total_with_vat)}
                  </td>
                  <td style={td}><DepositBar o={o} /></td>
                  <td style={td}>{fmtDate(o.delivery_committed_date)}</td>
                  <td style={td}>{o.sale_name ?? "—"}</td>
                  <td style={td}><StatusBadge status={o.status} /></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p style={{ color: "#8a97a8", fontSize: 12, marginTop: 8 }}>{total} đơn</p>

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

const th: React.CSSProperties = { padding: "10px 14px", fontWeight: 600, fontSize: 12 };
const td: React.CSSProperties = { padding: "11px 14px", verticalAlign: "top" };

function DepositBar({ o }: { o: OrderRow }) {
  if (!o.deposit_required)
    return <span style={{ color: "#8a97a8", fontSize: 12 }}>—</span>;
  const pct = Math.min(100, Math.round((o.deposit_received / o.deposit_required) * 100));
  return (
    <div style={{ minWidth: 120 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#5a6a7d", marginBottom: 2 }}>
        <span>{vnd(o.deposit_received)}</span>
        {o.deposit_ok ? (
          <span style={{ color: "#1f8a52", display: "inline-flex", gap: 2, alignItems: "center" }}>
            <Icon name="check" size={11} /> đủ
          </span>
        ) : (
          <span>/ {vnd(o.deposit_required)}</span>
        )}
      </div>
      <div style={{ height: 5, borderRadius: 3, background: "#eef1f6", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: o.deposit_ok ? "#1f8a52" : "#e0a92b" }} />
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

  async function removeDeposit(depId: number) {
    if (!token) return;
    const d = await api.orders.deleteDeposit(token, order.id, depId);
    onSaved(d);
  }
  async function upConsent(f: File) { if (token) onSaved(await api.orders.uploadConsent(token, order.id, f)); }
  async function delConsent(aid: number) { if (token) onSaved(await api.orders.deleteConsent(token, order.id, aid)); }
  async function upDepProof(did: number, f: File) { if (token) onSaved(await api.orders.uploadDepositProof(token, order.id, did, f)); }
  async function delDepProof(did: number, aid: number) { if (token) onSaved(await api.orders.deleteDepositProof(token, order.id, did, aid)); }
  const [acts, setActs] = useState<{ at: string; actor_name: string | null; action: string; detail: string }[]>([]);
  const isDraft = order.status === "draft";

  useEffect(() => {
    if (token) api.orders.activity(token, order.id).then((r) => setActs(r.items)).catch(() => {});
  }, [token, order.id]);

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(20,28,38,.32)", zIndex: 50, display: "flex", justifyContent: "flex-end" }}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        style={{ width: 560, maxWidth: "94vw", height: "100%", background: "#fff", overflowY: "auto", boxShadow: "-8px 0 24px rgba(0,0,0,.12)" }}
      >
        <header style={{ display: "flex", alignItems: "center", gap: 10, padding: "18px 22px", borderBottom: "1px solid #eef1f6", position: "sticky", top: 0, background: "#fff", zIndex: 1 }}>
          <h2 style={{ margin: 0, fontSize: 20 }}>{order.order_no}</h2>
          <StatusBadge status={order.status} />
          <RowFlags o={order} />
          <div style={{ flex: 1 }} />
          {isDraft && canUpdate && !editing && (
            <button className="btn" onClick={() => setEditing(true)}><Icon name="pencil" size={14} /> Sửa</button>
          )}
          {canCancel && (
            <button className="btn" onClick={() => setCancelling(true)}><Icon name="ban" size={14} /> Hủy</button>
          )}
          <button className="btn btn--ghost" onClick={onClose} aria-label="Đóng"><Icon name="x" size={16} /></button>
        </header>

        <div style={{ padding: "18px 22px", display: "grid", gap: 22 }}>
          {/* ① Thông tin chung */}
          <Section title="Thông tin chung">
            <KV k="Nguồn" v={order.source_type === "bao_gia" ? "Từ báo giá" : "Nhập giá tay"} />
            <KV k="Loại" v={order.order_kind === "bo_sung" ? "Đơn bổ sung" : "Đơn mới"} />
            <KV k="Bản chất" v={order.order_nature === "gia_cong" ? "Gia công" : "Hàng hóa"} />
            <KV k="NV phụ trách" v={order.sale_name ?? "—"} />
            <KV k="Ngày tạo" v={fmtDate(order.created_at)} />
            {order.ordered_at && <KV k="Ngày chốt" v={fmtDate(order.ordered_at)} />}
          </Section>

          {/* ② Thương mại */}
          <Section title="Thương mại (khóa)">
            <KV k="Khách hàng" v={order.customer_name ?? "—"} />
            {order.source_type === "bao_gia" && (
              <KV
                k="Báo giá"
                v={
                  <button
                    className="link"
                    style={{ color: "#2b6cb0", background: "none", border: 0, cursor: "pointer", padding: 0 }}
                    onClick={() => navigate?.("bao-gia", { openQuoteId: order.quotation_id })}
                  >
                    {order.quotation_code ?? "Báo giá"} · v{order.quotation_version} ↗
                  </button>
                }
              />
            )}
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginTop: 6 }}>
              <thead>
                <tr style={{ color: "#5a6a7d", textAlign: "left" }}>
                  <th style={thS}>Mô tả</th>
                  <th style={{ ...thS, textAlign: "right" }}>SL</th>
                  <th style={{ ...thS, textAlign: "right" }}>Đơn giá</th>
                  <th style={{ ...thS, textAlign: "right" }}>VAT</th>
                  <th style={{ ...thS, textAlign: "right" }}>Thành tiền</th>
                </tr>
              </thead>
              <tbody>
                {order.lines.map((l) => (
                  <tr key={l.id} style={{ borderTop: "1px solid #eef1f6" }}>
                    <td style={tdS}>{l.description}</td>
                    <td style={{ ...tdS, textAlign: "right" }}>{l.qty.toLocaleString("vi-VN")}</td>
                    <td style={{ ...tdS, textAlign: "right" }}>{vnd(l.unit_price_snapshot)}</td>
                    <td style={{ ...tdS, textAlign: "right" }}>{l.vat_pct_estimate}%</td>
                    <td style={{ ...tdS, textAlign: "right" }}>{vnd(l.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 8, display: "grid", gap: 3 }}>
              <KV k="Cộng trước VAT" v={vnd(order.total)} right />
              <KV k="Tổng gồm VAT" v={<strong>{vnd(order.total_with_vat)}</strong>} right />
              {order.margin_pct != null ? (
                <KV k="Biên lợi nhuận" v={`${order.margin_pct}% (giá vốn ${vnd(order.order_cost)})`} right />
              ) : (
                <KV k="Biên lợi nhuận" v={<em style={{ color: "#8a97a8" }}>không xác định (nhập tay)</em>} right />
              )}
            </div>
          </Section>

          {/* ③ Đặt hàng */}
          <Section title="Thông tin đặt hàng">
            {editing ? (
              <EditForm order={order} onCancel={() => setEditing(false)} onSaved={(d) => { setEditing(false); onSaved(d); }} />
            ) : (
              <>
                <KV k="Số PO khách" v={order.customer_po_no ?? "—"} />
                <KV k="Ngày giao cam kết" v={fmtDate(order.delivery_committed_date)} />
                <KV k="Địa chỉ giao" v={order.delivery_address ?? "—"} />
                <KV k="Pháp nhân xuất HĐ" v={order.invoice_entity_name ? `${order.invoice_entity_name}${order.invoice_entity_tax_code ? " · MST " + order.invoice_entity_tax_code : ""}` : "— (mặc định = khách)"} />
                <KV k="% cọc (ghim từ báo giá)" v={order.deposit_pct != null ? `${order.deposit_pct}%` : "—"} />
              </>
            )}
          </Section>

          {/* Chứng cứ khách đồng ý (cổng chốt §8d — bắt buộc với đơn nhập tay) */}
          <Section title="Chứng cứ khách đồng ý">
            {order.consent_attachments.length === 0 && !(isDraft && canUpdate) && (
              <p style={{ color: "#8a97a8", fontSize: 13 }}>Chưa có.</p>
            )}
            <AttachmentList
              items={order.consent_attachments}
              canEdit={isDraft && canUpdate}
              onUpload={upConsent}
              onDelete={delConsent}
              addLabel="Đính kèm chứng cứ (ảnh PO/Zalo…)"
            />
          </Section>

          {/* ④ Cọc */}
          <Section title="Cọc & thu tiền">
            <KV k="Ngưỡng cần thu" v={vnd(order.deposit_required)} right />
            <KV k="Đã thu" v={<strong>{vnd(order.deposit_received)}</strong>} right />
            <div style={{ margin: "6px 0" }}><DepositBar o={order} /></div>
            {order.deposits.length > 0 && (
              <div style={{ display: "grid", gap: 6, marginTop: 4 }}>
                {order.deposits.map((d) => (
                  <div key={d.id} style={{ background: "#f7f9fc", borderRadius: 8, padding: "7px 10px" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                      <strong style={{ fontVariantNumeric: "tabular-nums" }}>{vnd(d.amount_received)}</strong>
                      <span style={{ color: "#7a8698" }}>{DEPOSIT_KIND_LABELS[d.deposit_kind] ?? d.deposit_kind}</span>
                      {d.deposit_kind === "ck" && d.reconciled && (
                        <span style={{ color: "#1f8a52", display: "inline-flex", gap: 2, alignItems: "center" }}><Icon name="check" size={12} /> đối chiếu</span>
                      )}
                      {d.received_at && <span style={{ color: "#8a97a8" }}>{fmtDate(d.received_at)}</span>}
                      <div style={{ flex: 1 }} />
                      {d.recorded_by_name && <span style={{ color: "#8a97a8", fontSize: 12 }}>{d.recorded_by_name}</span>}
                      {canRecordDeposit && isDraft && (
                        <button className="btn btn--ghost" title="Xóa phiếu thu" onClick={() => removeDeposit(d.id)}><Icon name="trash" size={13} /></button>
                      )}
                    </div>
                    {(d.attachments.length > 0 || (canRecordDeposit && isDraft)) && (
                      <div style={{ marginTop: 5 }}>
                        <AttachmentList items={d.attachments} canEdit={canRecordDeposit && isDraft}
                          onUpload={(f) => upDepProof(d.id, f)} onDelete={(aid) => delDepProof(d.id, aid)}
                          addLabel="Đính kèm minh chứng" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {canRecordDeposit && isDraft && <DepositForm order={order} onSaved={onSaved} />}
            {!isDraft && <p style={{ color: "#8a97a8", fontSize: 12, marginTop: 6 }}>Đơn đã chốt — phiếu thu khóa.</p>}
          </Section>

          {/* ⑤ Duyệt (chỉ đơn cần duyệt: nhập tay / bổ sung tự đặt giá) */}
          {order.needs_approval && (
            <Section title="Duyệt đơn đặc thù">
              <ApprovalPanel order={order} canApprove={canApproveException} onSaved={onSaved} />
            </Section>
          )}

          {/* Cổng chốt (khi nháp) / trạng thái sau chốt */}
          {isDraft ? (
            <Section title="Cổng chốt đơn">
              <ConfirmPanel order={order} canManage={canManageStatus} onSaved={onSaved} />
            </Section>
          ) : order.status === "ordered" ? (
            <Section title="Sau chốt">
              <KV k="Đã chốt lúc" v={fmtDate(order.ordered_at)} />
              <p style={{ color: "#8a97a8", fontSize: 12 }}>Duyệt bản in + tiến độ sản xuất là luồng ngoài hệ thống.</p>
            </Section>
          ) : order.status === "cancelled" ? (
            <Section title="Đã hủy">
              <KV k="Lý do" v={order.cancel_reason ?? "—"} />
              {order.cancel_fault && <KV k="Lỗi tại" v={order.cancel_fault === "khach" ? "Khách hàng" : "Xưởng in"} />}
              {order.deposit_received > 0 && (
                <KV k="Cọc" v={`Còn ${vnd(order.deposit_received)} chưa quyết toán — xử lý ngoài hệ thống`} />
              )}
            </Section>
          ) : null}

          {/* ⑥ Nhật ký */}
          <Section title="Nhật ký hoạt động">
            {acts.length === 0 && <p style={{ color: "#8a97a8", fontSize: 13 }}>Chưa có.</p>}
            {acts.map((a, i) => (
              <div key={i} style={{ display: "flex", gap: 8, fontSize: 13, padding: "5px 0", borderTop: i ? "1px solid #f2f5f9" : undefined }}>
                <span style={{ color: "#8a97a8", minWidth: 88 }}>{new Date(a.at).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                <span><strong>{a.actor_name ?? "—"}</strong> · {a.detail || a.action}</span>
              </div>
            ))}
          </Section>
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
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(20,28,38,.32)", zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 440, maxWidth: "92vw", background: "#fff", borderRadius: 14, padding: 22 }}>
        <h3 style={{ margin: "0 0 4px", fontSize: 18 }}>Hủy đơn {order.order_no}</h3>
        <p style={{ color: "#8a97a8", fontSize: 13, marginTop: 0 }}>
          {isOrdered
            ? "Đơn đã chốt — báo giá KHÔNG mở lại; cọc giữ nguyên, hoàn/quyết toán xử lý ngoài hệ thống."
            : "Đơn nháp — hủy xong báo giá vẫn dùng lại được."}
        </p>
        {isOrdered && (
          <Field label="Lỗi tại ai">
            <select value={fault} onChange={(e) => setFault(e.target.value)} style={inp}>
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

const thS: React.CSSProperties = { padding: "6px 8px", fontWeight: 600, fontSize: 11 };
const tdS: React.CSSProperties = { padding: "6px 8px" };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 style={{ margin: "0 0 8px", fontSize: 13, textTransform: "uppercase", letterSpacing: ".04em", color: "#7a8698" }}>{title}</h3>
      <div style={{ display: "grid", gap: 5 }}>{children}</div>
    </section>
  );
}

function KV({ k, v, right }: { k: string; v: React.ReactNode; right?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: right ? "space-between" : undefined, gap: 10, fontSize: 13 }}>
      <span style={{ color: "#7a8698", minWidth: right ? undefined : 150 }}>{k}</span>
      <span style={{ color: "#2b3a4d" }}>{v}</span>
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
      const d = await api.orders.create(token, input);
      onCreated(d);
    } catch (e: unknown) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(20,28,38,.32)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 520, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto", background: "#fff", borderRadius: 14, padding: 24 }}>
        <h2 style={{ margin: "0 0 14px", fontSize: 19 }}>Tạo đơn hàng</h2>

        <Field label="Nguồn đơn">
          <div style={{ display: "flex", gap: 8 }}>
            {enums.source_types.map((s) => (
              <button
                key={s.value}
                onClick={() => setSource(s.value)}
                style={{ flex: 1, padding: "8px", borderRadius: 8, border: "1px solid", borderColor: source === s.value ? "#2b3a4d" : "#d7dee7", background: source === s.value ? "#eef2f8" : "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </Field>

        {source === "bao_gia" ? (
          <Field label="Báo giá đã duyệt (khách đồng ý)">
            <select value={quotationId} onChange={(e) => setQuotationId(e.target.value)} style={inp}>
              <option value="">— Chọn báo giá —</option>
              {quotes.map((qu) => (
                <option key={qu.id} value={qu.id}>{qu.code} · {qu.customer_name ?? ""}</option>
              ))}
            </select>
          </Field>
        ) : (
          <>
            <Field label="Khách hàng">
              <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} style={inp}>
                <option value="">— Chọn khách —</option>
                {custs.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                ))}
              </select>
            </Field>
            <div style={{ margin: "6px 0" }}>
              <span style={{ fontSize: 12, color: "#7a8698" }}>Dòng hàng (nhập tay — không giá vốn, sẽ cần duyệt)</span>
              {lines.map((l, i) => (
                <div key={i} style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <input placeholder="Mô tả" value={l.description} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} style={{ ...inp, flex: 2 }} />
                  <input type="number" placeholder="SL" value={l.qty} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: Number(e.target.value) } : x)))} style={{ ...inp, width: 70 }} />
                  <input type="number" placeholder="Đơn giá" value={l.unit_price ?? 0} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, unit_price: Number(e.target.value) } : x)))} style={{ ...inp, width: 100 }} />
                </div>
              ))}
              <button className="btn btn--ghost" style={{ marginTop: 6 }} onClick={() => setLines((ls) => [...ls, { description: "", qty: 1, unit_price: 0, vat_pct: 8 }])}>
                <Icon name="plus" size={13} /> Thêm dòng
              </button>
            </div>
          </>
        )}

        <Field label="Bản chất">
          <select value={nature} onChange={(e) => setNature(e.target.value)} style={inp}>
            <option value="hang_hoa">Hàng hóa</option>
            <option value="gia_cong">Gia công (khách ứng giấy)</option>
          </select>
        </Field>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13, marginBottom: 8 }}>
          <input type="checkbox" checked={isSupp} onChange={(e) => setIsSupp(e.target.checked)} /> Đơn bổ sung (in thêm — giữ kẽm cũ)
        </label>
        {isSupp && (
          <Field label="Đơn gốc (giữ kẽm)">
            <select value={parentId} onChange={(e) => setParentId(e.target.value)} style={inp}>
              <option value="">— Chọn đơn gốc đã chốt —</option>
              {parents.map((p) => (
                <option key={p.id} value={p.id}>{p.order_no} · {p.customer_name ?? ""}</option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Số PO khách (tùy chọn)"><input value={po} onChange={(e) => setPo(e.target.value)} style={inp} /></Field>

        {err && <div className="banner banner--error">{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
          <button className="btn btn--ghost" onClick={onClose} disabled={saving}>Hủy</button>
          <button className="btn btn--primary" onClick={submit} disabled={saving}>{saving ? "Đang tạo…" : "Tạo đơn"}</button>
        </div>
      </div>
    </div>
  );
}

function ConfirmPanel({ order, canManage, onSaved }: { order: OrderDetail; canManage: boolean; onSaved: (d: OrderDetail) => void }) {
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
  const [kind, setKind] = useState("ck");
  const [received, setReceived] = useState(String(Math.max(0, order.deposit_required - order.deposit_received)));
  const [reconciled, setReconciled] = useState(false);
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const d = await api.orders.addDeposit(token, order.id, {
        deposit_kind: kind,
        amount_received: Number(received) || 0,
        amount_expected: Number(received) || 0,
        reconciled: kind === "ck" ? reconciled : false,
        received_at: date || null,
        note: note || null,
      });
      onSaved(d);
      setOpen(false);
      setReceived("");
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
        <Icon name="plus" size={14} /> Tạo phiếu thu cọc
      </button>
    );
  return (
    <div style={{ marginTop: 8, border: "1px solid #e6ebf1", borderRadius: 10, padding: 12, display: "grid", gap: 8 }}>
      <Field label="Hình thức thu">
        <select value={kind} onChange={(e) => setKind(e.target.value)} style={inp}>
          {Object.entries(DEPOSIT_KIND_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </Field>
      <Field label="Số tiền thực nhận"><input type="number" value={received} onChange={(e) => setReceived(e.target.value)} style={inp} /></Field>
      <Field label="Ngày thu"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={inp} /></Field>
      {kind === "ck" && (
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
          <input type="checkbox" checked={reconciled} onChange={(e) => setReconciled(e.target.checked)} /> Đã đối chiếu sao kê
        </label>
      )}
      <Field label="Ghi chú"><input value={note} onChange={(e) => setNote(e.target.value)} style={inp} /></Field>
      {err && <div className="banner banner--error">{err}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn btn--ghost" onClick={() => setOpen(false)} disabled={saving}>Hủy</button>
        <button className="btn btn--primary" onClick={submit} disabled={saving}>{saving ? "Đang ghi…" : "Ghi phiếu"}</button>
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
    <div style={{ display: "grid", gap: 4 }}>
      {items.map((a) => (
        <div key={a.id} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
          <Icon name="fileText" size={13} />
          <a href={`${API_BASE}${a.url}`} target="_blank" rel="noreferrer" style={{ color: "#2b6cb0", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.file_name ?? "tệp"}</a>
          {canEdit && <button className="btn btn--ghost" title="Xóa" onClick={() => onDelete(a.id)}><Icon name="trash" size={11} /></button>}
        </div>
      ))}
      {canEdit && (
        <>
          <input ref={ref} type="file" accept="image/*,application/pdf" style={{ display: "none" }} onChange={pick} />
          <button className="btn btn--ghost" style={{ justifySelf: "start" }} disabled={busy} onClick={() => ref.current?.click()}>
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
