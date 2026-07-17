// Trang Lệnh sản xuất (LSX) — Sản xuất P1 + Lớp A (header giàu + Tập tin).
// List → chi tiết 2 panel (Khách hàng | Thông tin phiếu) + tab Tập tin; tạo/sửa LSX.
// Gate module `san_xuat`.
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type ProductionOrderRow,
  type ProductionOrderInput,
  type ProductionAttachment,
  type KhoVoucherType,
  type KhoMaterialOption,
  type KhoItemStatus,
  type WarehouseRow,
  type VoucherRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { VoucherForm, VoucherDetail } from "./StockVoucherPage";
import logoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import "./master-data.css";

// Thông tin công ty in trên phiếu — Sao Việt Nhật. Trường pháp lý để trống ("—")
// chờ khảo sát, chỉ in dòng nào đã có dữ liệu thật.
const SVN_COMPANY = { name: "CÔNG TY SAO VIỆT NHẬT", address: "—", taxCode: "—", phone: "—" };

// 3 loại phiếu kho sinh từ LSX (giống hệ tham khảo): (mã loại, nhãn nút).
const GEN_VOUCHERS: { code: string; label: string }[] = [
  { code: "XK-SX", label: "Tạo phiếu xuất giấy" },
  { code: "NK-XUONG", label: "Tạo phiếu nhập thành phẩm" },
  { code: "XK-KH", label: "Tạo phiếu xuất kho thành phẩm" },
];

const STATUS_LABEL: Record<string, string> = {
  open: "Đang mở", done: "Hoàn thành", cancelled: "Đã hủy",
};
// Nhãn trạng thái phiếu kho (khác vòng đời LSX) — cho bảng "Phiếu kho của lệnh này".
const V_STATUS_LABEL: Record<string, string> = {
  draft: "Nháp", pending: "Chờ duyệt", posted: "Đã ghi sổ", cancelled: "Đã hủy",
};

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  return d && m && y ? `${d}/${m}/${y}` : s;
}
function fmtDateTime(s: string | null): string {
  if (!s) return "—";
  const dt = new Date(s);
  return isNaN(dt.getTime()) ? s : dt.toLocaleString("vi-VN");
}
function esc(v: unknown): string {
  return String(v ?? "—").replace(/[&<>]/g, (c) => (c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;"));
}

// In "Phiếu sản xuất" — mở cửa sổ in, dựng HTML sạch rồi window.print(). 7 mẫu còn lại cần
// dữ liệu Lớp B/C (phương án in, kẽm, giấy) nên chưa in được.
function printProductionOrder(o: ProductionOrderRow): void {
  const w = window.open("", "_blank", "width=920,height=1040");
  if (!w) return;
  const logoAbs = new URL(logoUrl, window.location.href).href;

  // "Ngày … tháng … năm …" theo ngày lập phiếu SX (fallback ngày đặt).
  const dSrc = o.doc_date || o.order_date || "";
  const [yy, mm, dd] = dSrc ? dSrc.split("-") : ["", "", ""];
  const dateLine = dd && mm && yy ? `Ngày ${dd} tháng ${mm} năm ${yy}` : "";

  // Dòng pháp lý công ty — chỉ hiện khi có dữ liệu thật (không in "—").
  const legal = [
    SVN_COMPANY.address !== "—" ? `Địa chỉ: ${esc(SVN_COMPANY.address)}` : "",
    SVN_COMPANY.taxCode !== "—" ? `MST: ${esc(SVN_COMPANY.taxCode)}` : "",
    SVN_COMPANY.phone !== "—" ? `Điện thoại: ${esc(SVN_COMPANY.phone)}` : "",
  ].filter(Boolean).map((x) => `<div>${x}</div>`).join("");

  const rows: [string, string][] = [
    ["Khách hàng", esc(o.customer_name)],
    ["Theo hợp đồng số", esc(o.contract_no)],
    ["Ấn phẩm", esc(o.product_name)],
    ["Số lượng", o.quantity != null ? esc(o.quantity) : "—"],
    ["Ngày đặt", fmtDate(o.order_date)],
    ["Yêu cầu nhận hàng", fmtDate(o.delivery_request_date)],
    ["Ngày lập phiếu SX", fmtDate(o.doc_date)],
    ["Ngày hoàn thành", fmtDate(o.due_date)],
    ["Trạng thái", esc(STATUS_LABEL[o.status] ?? o.status)],
    ["Duyệt lệnh", o.approved_at ? `Đã duyệt · ${esc(o.approved_by_name)} · ${fmtDateTime(o.approved_at)}` : "Chưa duyệt"],
    ["Người lập", esc(o.created_by_name)],
  ];
  const notes: [string, string | null][] = [
    ["Lưu ý kỹ thuật khi in", o.tech_note_print],
    ["Lưu ý kỹ thuật đóng xén", o.tech_note_finishing],
    ["Ghi chú", o.note],
  ];
  // Ô ký theo chuỗi lệnh sản xuất: người lập → người duyệt → xưởng thực hiện.
  const SIGN = ["Người lập phiếu", "Duyệt sản xuất", "Quản đốc xưởng"];

  w.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>Phiếu sản xuất ${esc(o.code)}</title>
<style>
  * { font-family: 'Times New Roman', 'Segoe UI', serif; box-sizing: border-box; }
  body { margin: 0; color: #111; font-size: 13.5px; line-height: 1.4; }
  .sheet { padding: 16mm 14mm; }
  .head { display: flex; align-items: flex-start; gap: 14px; padding-bottom: 8px; margin-bottom: 4px; }
  .head img { height: 60px; }
  .company__name { font-size: 16px; font-weight: 700; text-transform: uppercase; }
  .company__legal { font-size: 12.5px; color: #222; margin-top: 2px; }
  .company__legal div { margin: 1px 0; }
  h1 { font-size: 22px; text-align: center; margin: 14px 0 4px; text-transform: uppercase; font-weight: 700; letter-spacing: .5px; }
  .datebar { text-align: center; font-size: 13px; margin-bottom: 2px; }
  .docno { text-align: center; font-size: 13px; margin-bottom: 14px; }
  .info { display: grid; grid-template-columns: 1fr 1fr; gap: 0 28px; margin-bottom: 14px; }
  .info__row { display: flex; gap: 8px; padding: 4px 2px; border-bottom: 1px dotted #cfcac0; }
  .info__k { color: #333; min-width: 122px; }
  .info__v { font-weight: 700; flex: 1; }
  .note { border: 1px solid #333; border-radius: 4px; padding: 8px 10px; margin-bottom: 10px; white-space: pre-wrap; font-size: 13px; }
  .note .lbl { color: #333; font-weight: 700; display: block; margin-bottom: 3px; text-transform: uppercase; font-size: 12px; letter-spacing: .3px; }
  .sign { display: flex; justify-content: space-around; gap: 12px; margin-top: 40px; text-align: center; font-size: 13px; }
  .sign > div { flex: 1 1 0; max-width: 33%; }
  .sign__role { font-weight: 700; }
  .sign__hint { font-style: italic; font-size: 12px; color: #444; }
  .sign__space { height: 80px; }
  @media print { .sheet { padding: 12mm; } body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head>
<body onload="window.print()" onafterprint="window.close()">
  <div class="sheet">
    <div class="head">
      <img src="${logoAbs}" alt="logo">
      <div>
        <div class="company__name">${esc(SVN_COMPANY.name)}</div>
        ${legal ? `<div class="company__legal">${legal}</div>` : ""}
      </div>
    </div>

    <h1>Phiếu sản xuất</h1>
    ${dateLine ? `<div class="datebar">${dateLine}</div>` : ""}
    <div class="docno">Số: <strong>${esc(o.code)}</strong></div>

    <div class="info">
      ${rows.map(([k, v]) => `<div class="info__row"><span class="info__k">${k}:</span><span class="info__v">${v}</span></div>`).join("")}
    </div>

    ${notes.filter(([, v]) => v && v.trim()).map(([k, v]) => `<div class="note"><span class="lbl">${k}</span>${esc(v)}</div>`).join("")}

    <div class="sign">
      ${SIGN.map((role) => `<div><div class="sign__role">${esc(role)}</div><div class="sign__hint">(Ký, họ tên)</div><div class="sign__space"></div></div>`).join("")}
    </div>
  </div>
</body></html>`);
  w.document.close();
}

export function ProductionOrdersPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("san_xuat", "create");

  const [rows, setRows] = useState<ProductionOrderRow[]>([]);
  const [statusF, setStatusF] = useState("");
  const [q, setQ] = useState("");
  const [kindF, setKindF] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<ProductionOrderRow | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.production.listOrders(token, { status: statusF || undefined, order_kind: kindF || undefined, q: q.trim() || undefined, size: 100 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được danh sách lệnh sản xuất.");
      })
      .finally(() => setLoading(false));
  }, [token, statusF, kindF, q]);

  useEffect(() => { load(); }, [load]);

  if (forbidden) {
    return (
      <main className="md-page">
        <div className="banner banner--error" role="alert">Bạn không có quyền truy cập Sản xuất (403).</div>
      </main>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head">
        <p className="eyebrow">Sản xuất · Chứng từ</p>
        <h1 className="md-page__title">Lệnh sản xuất</h1>
        <p className="md-page__sub">
          Mỗi lệnh sản xuất (LSX) là một chứng từ độc lập. Kho tham chiếu LSX khi nhập thành phẩm / xuất NVL.
        </p>
      </header>

      <div className="md-page__toolbar">
        <select className="input" value={kindF} onChange={(e) => setKindF(e.target.value)}>
          <option value="">— Tất cả loại lệnh —</option>
          <option value="thuong">Lệnh thường</option>
          <option value="bu">Lệnh bù</option>
        </select>
        <select className="input" value={statusF} onChange={(e) => setStatusF(e.target.value)}>
          <option value="">— Tất cả trạng thái —</option>
          <option value="open">Đang mở</option>
          <option value="done">Hoàn thành</option>
          <option value="cancelled">Đã hủy</option>
        </select>
        <input className="input" placeholder="Tìm mã LSX / sản phẩm…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="md-page__toolbar-spacer" />
        {canCreate && <Button variant="primary" onClick={() => setCreating(true)}>+ Tạo lệnh</Button>}
      </div>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <div className="card md-page__tablewrap">
        <table className="md-page__table">
          <thead>
            <tr><th>Mã LSX</th><th>Khách hàng</th><th>Sản phẩm</th><th>Số lượng</th><th>Ngày lập</th><th>Hoàn thành</th><th>Duyệt</th><th>Trạng thái</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="md-page__status">Đang tải...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={8} className="md-page__empty">Chưa có lệnh sản xuất. Bấm “Tạo lệnh”.</td></tr>
            ) : (
              rows.map((o) => (
                <tr key={o.id} className="md-page__row" onClick={() => setDetail(o)}>
                  <td className="md-page__mono">
                    {o.code}
                    {o.order_kind === "bu" && <span className="md-page__status-badge" style={{ marginLeft: 6, background: "#f0d9c0", color: "#8a4b1a" }}>Bù</span>}
                  </td>
                  <td>{o.customer_name || <span className="md-page__muted">—</span>}</td>
                  <td>{o.product_name || <span className="md-page__muted">—</span>}</td>
                  <td>{o.quantity ?? <span className="md-page__muted">—</span>}</td>
                  <td>{fmtDate(o.doc_date)}</td>
                  <td>{fmtDate(o.due_date)}</td>
                  <td>
                    <span className="md-page__status-badge" style={{ background: o.approved_at ? "#dbe7dd" : "#efe4c4", color: o.approved_at ? "#244a2e" : "#7a5c0f" }}>
                      {o.approved_at ? "✓ Đã duyệt" : "Chưa duyệt"}
                    </span>
                  </td>
                  <td>
                    <span className={`md-page__status-badge ${o.status === "open" ? "is-active" : "is-inactive"}`}>
                      {STATUS_LABEL[o.status] ?? o.status}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {creating && (
        <ProductionOrderForm onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }} />
      )}
      {detail && (
        <ProductionOrderDetail
          order={detail}
          canCreate={canCreate}
          onClose={() => setDetail(null)}
          onChanged={() => { setDetail(null); load(); }}
        />
      )}
    </main>
  );
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "150px 1fr", gap: 12, padding: "5px 0", fontSize: 14, alignItems: "baseline" }}>
      <span className="md-page__muted" style={{ textAlign: "right" }}>{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function ProductionOrderDetail({
  order, canCreate, onClose, onChanged,
}: {
  order: ProductionOrderRow; canCreate: boolean; onClose: () => void; onChanged: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canApproveLsx = can("san_xuat", "approve");
  // Sinh phiếu kho từ LSX cần quyền LẬP PHIẾU KHO (kho:create) — không phải quyền sản xuất.
  const canKhoCreate = can("kho", "create");
  const [cur, setCur] = useState<ProductionOrderRow>(order);
  const [tab, setTab] = useState<"info" | "files" | "vouchers">("info");
  const [editing, setEditing] = useState(false);
  const [atts, setAtts] = useState<ProductionAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Sinh phiếu kho từ LSX: dữ liệu kho + loại phiếu đang mở.
  const [khoData, setKhoData] = useState<{
    types: KhoVoucherType[]; materials: KhoMaterialOption[]; statuses: KhoItemStatus[]; warehouses: WarehouseRow[];
  } | null>(null);
  const [genCode, setGenCode] = useState<string | null>(null);
  const [genMenuOpen, setGenMenuOpen] = useState(false); // menu "Sinh phiếu kho"
  const [buForm, setBuForm] = useState(false); // mở form tạo lệnh bù cho lệnh này
  const [confirmCancel, setConfirmCancel] = useState(false); // popup xác nhận Hủy lệnh
  const [parentDetail, setParentDetail] = useState<ProductionOrderRow | null>(null); // LSX gốc đang mở
  // Truy vết Mức A — mọi phiếu kho trỏ về LSX này (ref_type='lsx', ref_id=order.id).
  const [linked, setLinked] = useState<VoucherRow[]>([]);
  const [vtypes, setVtypes] = useState<KhoVoucherType[]>([]);
  const [openVoucher, setOpenVoucher] = useState<VoucherRow | null>(null);
  // Lọc + phân trang bảng "Phiếu kho của lệnh này" (client-side; linked nạp tối đa 200).
  const [vTypeF, setVTypeF] = useState("");
  const [vStatusF, setVStatusF] = useState("");
  const [vPage, setVPage] = useState(1);
  const V_PAGE_SIZE = 8;

  function openParent() {
    if (!token || !cur.parent_order_id) return;
    api.production.getOrder(token, cur.parent_order_id).then(setParentDetail).catch(() => {});
  }

  const loadAtts = useCallback(() => {
    if (!token) return;
    api.production.orderAttachments(token, order.id).then((r) => setAtts(r.items)).catch(() => {});
  }, [token, order.id]);
  useEffect(() => { loadAtts(); }, [loadAtts]);

  // Phiếu kho của lệnh này — cần quyền kho:read (không có thì im lặng để trống).
  const loadLinked = useCallback(() => {
    if (!token) return;
    api.kho.listVouchers(token, { ref_type: "lsx", ref_id: order.id, size: 200 })
      .then((r) => setLinked(r.items)).catch(() => setLinked([]));
  }, [token, order.id]);
  useEffect(() => { loadLinked(); }, [loadLinked]);
  useEffect(() => {
    if (!token) return;
    api.kho.voucherTypes(token).then((r) => setVtypes(r.items)).catch(() => {});
  }, [token]);

  // Nạp dữ liệu kho (loại phiếu, vật tư, trạng thái, kho) — để sinh phiếu VÀ để mở
  // chi tiết phiếu kho từ bảng truy vết. Cần quyền đọc kho; thiếu quyền thì im lặng.
  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.kho.voucherTypes(token),
      api.kho.materialOptions(token),
      api.kho.itemStatuses(token),
      api.warehouses.list(token, { size: 200, sort: "code" }),
    ]).then(([t, m, s, w]) =>
      setKhoData({ types: t.items, materials: m, statuses: s.items, warehouses: w.items }),
    ).catch(() => {});
  }, [token]);

  async function setStatus(to: "done" | "cancelled" | "open") {
    if (!token) return;
    setBusy(true); setError(null);
    try { const r = await api.production.closeOrder(token, order.id, to); setCur(r); onChanged(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Cập nhật trạng thái thất bại."); setBusy(false); }
  }
  async function setApprove(approve: boolean) {
    if (!token) return;
    setBusy(true); setError(null);
    try { const r = await api.production.approveOrder(token, order.id, approve); setCur(r); onChanged(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Duyệt lệnh thất bại."); }
    finally { setBusy(false); }
  }
  async function onUploadFiles(list: FileList | null) {
    if (!token || !list || !list.length) return;
    setBusy(true); setError(null);
    try { for (const f of Array.from(list)) await api.production.uploadOrderAttachment(token, order.id, f); loadAtts(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Tải file thất bại."); }
    finally { setBusy(false); }
  }
  async function onDeleteAtt(aid: number) {
    if (!token) return;
    setBusy(true); setError(null);
    try { await api.production.deleteOrderAttachment(token, order.id, aid); loadAtts(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Xóa file thất bại."); }
    finally { setBusy(false); }
  }

  if (editing) {
    return (
      <ProductionOrderForm
        initial={cur}
        onClose={() => setEditing(false)}
        onSaved={(updated) => { setCur(updated); setEditing(false); onChanged(); }}
      />
    );
  }

  // Dữ liệu bảng "Phiếu kho" — options lọc (chỉ loại/trạng thái thực sự xuất hiện), lọc + phân trang.
  const vTypeOptions = vtypes.filter((t) => linked.some((v) => v.voucher_type_id === t.id));
  const vStatusOptions = Array.from(new Set(linked.map((v) => v.status)));
  const vFiltered = linked.filter((v) =>
    (!vTypeF || String(v.voucher_type_id) === vTypeF) && (!vStatusF || v.status === vStatusF),
  );
  const vPages = Math.max(1, Math.ceil(vFiltered.length / V_PAGE_SIZE));
  const vPageRows = vFiltered.slice((Math.min(vPage, vPages) - 1) * V_PAGE_SIZE, Math.min(vPage, vPages) * V_PAGE_SIZE);

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 940, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2>Chi tiết phiếu sản xuất: {cur.code}</h2>
          {cur.order_kind === "bu" && (
            <span className="md-page__status-badge" style={{ marginLeft: 10, background: "#f0d9c0", color: "#8a4b1a" }}>Lệnh bù</span>
          )}
          <span className={`md-page__status-badge ${cur.status === "open" ? "is-active" : "is-inactive"}`} style={{ marginLeft: 10 }}>
            {STATUS_LABEL[cur.status] ?? cur.status}
          </span>
          <span className="md-page__status-badge" style={{ marginLeft: 10, background: cur.approved_at ? "#dbe7dd" : "#efe4c4", color: cur.approved_at ? "#244a2e" : "#7a5c0f" }}>
            {cur.approved_at ? "✓ Đã duyệt" : "Chưa duyệt"}
          </span>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body">
          {/* Tabs */}
          <div className="md-page__tabs" style={{ display: "flex", gap: 16, borderBottom: "1px solid var(--border, #e2ddd3)", marginBottom: 14 }}>
            <button type="button" className="md-page__tab" onClick={() => setTab("info")}
              style={{ padding: "6px 2px", background: "none", border: "none", cursor: "pointer", borderBottom: tab === "info" ? "2px solid var(--accent, #b5531f)" : "2px solid transparent", fontWeight: tab === "info" ? 600 : 400 }}>
              Thông tin
            </button>
            <button type="button" className="md-page__tab" onClick={() => setTab("files")}
              style={{ padding: "6px 2px", background: "none", border: "none", cursor: "pointer", borderBottom: tab === "files" ? "2px solid var(--accent, #b5531f)" : "2px solid transparent", fontWeight: tab === "files" ? 600 : 400 }}>
              Tập tin{atts.length ? ` (${atts.length})` : ""}
            </button>
            <button type="button" className="md-page__tab" onClick={() => setTab("vouchers")}
              style={{ padding: "6px 2px", background: "none", border: "none", cursor: "pointer", borderBottom: tab === "vouchers" ? "2px solid var(--accent, #b5531f)" : "2px solid transparent", fontWeight: tab === "vouchers" ? 600 : 400 }}>
              Phiếu kho{linked.length ? ` (${linked.length})` : ""}
            </button>
          </div>

          {(() => {
            const genList = khoData ? GEN_VOUCHERS.filter((g) => khoData.types.some((t) => t.code === g.code)) : [];
            return (
              <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
                {/* Nhóm 1 — thao tác trên lệnh */}
                <Button variant="ghost" onClick={() => printProductionOrder(cur)}>🖨 In phiếu</Button>
                {canCreate && <Button variant="ghost" onClick={() => setEditing(true)}>Cập nhật</Button>}
                {canCreate && canApproveLsx && (cur.approved_at
                  ? <Button variant="ghost" onClick={() => setApprove(false)} loading={busy}>Bỏ duyệt</Button>
                  : <Button variant="primary" onClick={() => setApprove(true)} loading={busy}>Duyệt lệnh</Button>
                )}
                {canCreate && (cur.status === "open" ? (
                  <>
                    <Button variant="ghost" onClick={() => setStatus("done")} loading={busy}>Hoàn thành</Button>
                    <Button variant="danger" onClick={() => setConfirmCancel(true)} disabled={busy}>Hủy</Button>
                  </>
                ) : (
                  <Button variant="ghost" onClick={() => setStatus("open")} loading={busy}>Mở lại</Button>
                ))}
                {canCreate && cur.order_kind !== "bu" && (
                  <Button variant="ghost" onClick={() => setBuForm(true)}>Tạo lệnh bù</Button>
                )}

                {/* Nhóm 2 — sinh phiếu kho gộp vào 1 menu thả xuống (BRD §2.5: cần lệnh đã duyệt). */}
                {canKhoCreate && genList.length > 0 && (
                  <div style={{ position: "relative", marginLeft: "auto" }}>
                    <Button variant="primary" disabled={!cur.approved_at}
                      title={cur.approved_at ? undefined : "Cần duyệt lệnh trước khi sinh phiếu kho"}
                      onClick={() => setGenMenuOpen((o) => !o)}>+ Sinh phiếu kho ▾</Button>
                    {genMenuOpen && cur.approved_at && (
                      <>
                        <div style={{ position: "fixed", inset: 0, zIndex: 20 }} onClick={() => setGenMenuOpen(false)} />
                        <div className="card" style={{ position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 21, minWidth: 240, padding: 4, boxShadow: "0 8px 24px rgba(0,0,0,.18)" }}>
                          {genList.map((g) => (
                            <button key={g.code} type="button" className="md-page__row"
                              style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px", background: "none", border: "none", cursor: "pointer", borderRadius: 6 }}
                              onClick={() => { setGenMenuOpen(false); setGenCode(g.code); }}>{g.label}</button>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
                {canKhoCreate && genList.length > 0 && !cur.approved_at && (
                  <span className="md-page__muted" style={{ fontSize: 12 }}>Duyệt lệnh để sinh phiếu kho</span>
                )}
              </div>
            );
          })()}

          {tab === "info" && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28, alignItems: "start" }}>
                <section>
                  <h3 className="md-page__section-title">Khách hàng</h3>
                  {cur.customer_name ? (
                    <div style={{ fontSize: 17, fontWeight: 600, margin: "6px 0" }}>{cur.customer_name}</div>
                  ) : (
                    <p className="md-page__muted" style={{ margin: "6px 0" }}>— Chưa có khách hàng —</p>
                  )}
                  {cur.contract_no && <DetailRow label="Theo hợp đồng số" value={cur.contract_no} />}
                </section>
                <section>
                  <h3 className="md-page__section-title">Thông tin phiếu #{cur.id}</h3>
                  <DetailRow label="Mã số" value={<span className="md-page__mono">{cur.code}</span>} />
                  <DetailRow label="Loại lệnh" value={cur.order_kind === "bu" ? "Lệnh bù" : "Lệnh thường"} />
                  {cur.order_kind === "bu" && (
                    <DetailRow label="LSX gốc (nguồn)" value={
                      cur.parent_order_id ? (
                        <button type="button" onClick={openParent}
                          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--accent, #b5531f)", fontWeight: 600, textDecoration: "underline" }}>
                          {cur.parent_code || `#${cur.parent_order_id}`} ↗
                        </button>
                      ) : "— (không gắn LSX gốc) —"
                    } />
                  )}
                  {cur.order_kind === "bu" && <DetailRow label="Lý do bù" value={cur.bu_reason || "—"} />}
                  <DetailRow label="Sản phẩm" value={cur.product_name || "—"} />
                  <DetailRow label="Số lượng" value={cur.quantity ?? "—"} />
                  <DetailRow label="Ngày đặt" value={fmtDate(cur.order_date)} />
                  <DetailRow label="Yêu cầu nhận hàng" value={fmtDate(cur.delivery_request_date)} />
                  <DetailRow label="Ngày lập phiếu SX" value={fmtDate(cur.doc_date)} />
                  <DetailRow label="Ngày hoàn thành" value={fmtDate(cur.due_date)} />
                  <DetailRow label="Duyệt lệnh" value={cur.approved_at
                    ? <span style={{ color: "#244a2e", fontWeight: 600 }}>Đã duyệt · {cur.approved_by_name || "—"} · {fmtDateTime(cur.approved_at)}</span>
                    : <span style={{ color: "#7a5c0f" }}>Chưa duyệt</span>} />
                  <DetailRow label="Người nhập" value={cur.created_by_name || "—"} />
                  <DetailRow label="Ngày tạo" value={fmtDateTime(cur.created_at)} />
                  <DetailRow label="Người cập nhật" value={cur.updated_by_name || "—"} />
                  <DetailRow label="Ngày cập nhật" value={fmtDateTime(cur.updated_at)} />
                </section>
              </div>
              {(cur.tech_note_print || cur.tech_note_finishing || cur.note) && (
                <div style={{ marginTop: 16 }}>
                  {cur.tech_note_print && <DetailRow label="Lưu ý kỹ thuật khi in" value={<span style={{ whiteSpace: "pre-wrap" }}>{cur.tech_note_print}</span>} />}
                  {cur.tech_note_finishing && <DetailRow label="Lưu ý đóng xén" value={<span style={{ whiteSpace: "pre-wrap" }}>{cur.tech_note_finishing}</span>} />}
                  {cur.note && <DetailRow label="Ghi chú" value={<span style={{ whiteSpace: "pre-wrap" }}>{cur.note}</span>} />}
                </div>
              )}
            </>
          )}

          {/* Truy vết Mức A — mọi phiếu kho (xuất NVL / nhập TP / xuất giao khách) của lệnh này. */}
          {tab === "vouchers" && (
            <>
              {linked.length === 0 ? (
                <p className="md-page__muted" style={{ margin: "6px 0" }}>Chưa có phiếu kho nào gắn với lệnh này.</p>
              ) : (
                <>
                  {/* Lọc theo loại phiếu + trạng thái */}
                  <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                    <select className="input" style={{ width: "auto", minWidth: 180 }} value={vTypeF}
                      onChange={(e) => { setVTypeF(e.target.value); setVPage(1); }}>
                      <option value="">Tất cả loại phiếu</option>
                      {vTypeOptions.map((o) => <option key={o.id} value={String(o.id)}>{o.name}</option>)}
                    </select>
                    <select className="input" style={{ width: "auto", minWidth: 150 }} value={vStatusF}
                      onChange={(e) => { setVStatusF(e.target.value); setVPage(1); }}>
                      <option value="">Tất cả trạng thái</option>
                      {vStatusOptions.map((s) => <option key={s} value={s}>{V_STATUS_LABEL[s] ?? s}</option>)}
                    </select>
                    {(vTypeF || vStatusF) && (
                      <button type="button" className="md-page__tab" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent, #b5531f)" }}
                        onClick={() => { setVTypeF(""); setVStatusF(""); setVPage(1); }}>Xóa lọc</button>
                    )}
                  </div>

                  {/* Bảng cuộn — giới hạn chiều cao, dài quá thì cuộn dọc */}
                  <div className="card md-page__tablewrap" style={{ maxHeight: 360, overflowY: "auto" }}>
                    <table className="md-page__table">
                      <thead>
                        <tr>
                          <th>Mã phiếu</th><th>Loại phiếu</th><th>Ngày</th>
                          <th style={{ textAlign: "right" }}>Số dòng</th><th>Trạng thái</th>
                        </tr>
                      </thead>
                      <tbody>
                        {vPageRows.length === 0 ? (
                          <tr><td colSpan={5} className="md-page__muted" style={{ padding: "10px" }}>Không có phiếu khớp bộ lọc.</td></tr>
                        ) : vPageRows.map((v) => {
                          const vt = vtypes.find((t) => t.id === v.voucher_type_id);
                          return (
                            <tr key={v.id} style={{ cursor: "pointer" }} onClick={() => setOpenVoucher(v)}>
                              <td className="md-page__mono" style={{ color: "var(--accent, #b5531f)", fontWeight: 600 }}>{v.code}</td>
                              <td>{vt?.name ?? `#${v.voucher_type_id}`}</td>
                              <td>{fmtDate(v.doc_date)}</td>
                              <td style={{ textAlign: "right" }}>{v.lines?.length ?? 0}</td>
                              <td>{V_STATUS_LABEL[v.status] ?? v.status}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Phân trang */}
                  {vFiltered.length > V_PAGE_SIZE && (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, marginTop: 10 }}>
                      <span className="md-page__muted" style={{ fontSize: 13 }}>
                        {vFiltered.length} phiếu · Trang {Math.min(vPage, vPages)}/{vPages}
                      </span>
                      <Button variant="ghost" disabled={vPage <= 1} onClick={() => setVPage((p) => Math.max(1, p - 1))}>‹ Trước</Button>
                      <Button variant="ghost" disabled={vPage >= vPages} onClick={() => setVPage((p) => Math.min(vPages, p + 1))}>Sau ›</Button>
                    </div>
                  )}
                </>
              )}
            </>
          )}

          {tab === "files" && (
            <>
              {atts.length === 0 ? (
                <p className="md-page__muted" style={{ margin: "4px 0" }}>Chưa có tập tin đính kèm.</p>
              ) : (
                <ul className="md-page__filelist">
                  {atts.map((a) => (
                    <li key={a.id}>
                      <a className="md-page__file-name" href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">📎 {a.file_name}</a>
                      {canCreate && <button type="button" className="md-page__file-x" disabled={busy} onClick={() => onDeleteAtt(a.id)}>✕</button>}
                    </li>
                  ))}
                </ul>
              )}
              {canCreate && (
                <input className="input" type="file" multiple disabled={busy} style={{ marginTop: 8 }}
                  onChange={(e) => { onUploadFiles(e.target.files); e.target.value = ""; }} />
              )}
            </>
          )}

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button variant="ghost" onClick={onClose}>Đóng</Button>
          </div>
        </div>
      </div>
      {genCode && khoData && (() => {
        const vt = khoData.types.find((t) => t.code === genCode);
        if (!vt) return null;
        return (
          <VoucherForm
            types={khoData.types}
            warehouses={khoData.warehouses}
            materials={khoData.materials}
            statuses={khoData.statuses}
            lockedTypeId={vt.id}
            prefillLsx={{
              id: cur.id, code: cur.code,
              customerName: cur.customer_name, productName: cur.product_name, quantity: cur.quantity,
            }}
            onClose={() => setGenCode(null)}
            onSaved={() => { setGenCode(null); loadLinked(); }}
          />
        );
      })()}
      {/* Mở chi tiết một phiếu kho từ bảng truy vết (cần dữ liệu kho đã nạp). */}
      {openVoucher && khoData && (
        <VoucherDetail
          voucher={openVoucher}
          types={khoData.types}
          warehouses={khoData.warehouses}
          materials={khoData.materials}
          statuses={khoData.statuses}
          canApprove={can("kho", "approve")}
          canCreate={can("kho", "create")}
          onClose={() => setOpenVoucher(null)}
          onChanged={() => { loadLinked(); }}
        />
      )}
      {/* Tạo lệnh bù CHO lệnh này — gắn sẵn gốc + điền sẵn khách/sản phẩm. */}
      {buForm && (
        <ProductionOrderForm
          buParent={cur}
          onClose={() => setBuForm(false)}
          onSaved={() => { setBuForm(false); onChanged(); }}
        />
      )}
      {/* LSX gốc (nguồn) mở chồng lên — truy nguồn lệnh bù. */}
      {parentDetail && (
        <ProductionOrderDetail
          order={parentDetail}
          canCreate={canCreate}
          onClose={() => setParentDetail(null)}
          onChanged={() => setParentDetail(null)}
        />
      )}
      <ConfirmDialog
        open={confirmCancel}
        danger
        title="Hủy lệnh sản xuất?"
        message={`Hủy lệnh ${cur.code}? Lệnh sẽ chuyển sang "Đã hủy".`}
        confirmLabel="Xác nhận hủy"
        cancelLabel="Không"
        busy={busy}
        error={error}
        onConfirm={() => setStatus("cancelled")}
        onCancel={() => { if (!busy) { setConfirmCancel(false); setError(null); } }}
      />
    </div>
  );
}

// Form tạo/sửa LSX. Lệnh bù KHÔNG chọn ở đây — tạo từ nút "Tạo lệnh bù" trong chi tiết 1 LSX
// (truyền `buParent`). Cũng dùng cho "Tạo LSX nhanh" trong phiếu kho (không truyền gì).
export function ProductionOrderForm({
  initial, buParent, onClose, onSaved,
}: {
  /** Có → chế độ sửa; không → tạo mới. */
  initial?: ProductionOrderRow;
  /** Có → tạo LỆNH BÙ cho LSX này (gắn sẵn gốc + điền sẵn khách/sản phẩm). */
  buParent?: ProductionOrderRow | null;
  onClose: () => void;
  /** Trả về LSX vừa tạo/sửa để nơi gọi dùng tiếp (quick-create trong kho). */
  onSaved: (saved: ProductionOrderRow) => void;
}) {
  const { token } = useAuth();
  // Lệnh bù xác định theo NGỮ CẢNH: đang tạo bù (buParent) hoặc đang sửa 1 lệnh bù sẵn.
  const isBu = !!buParent || initial?.order_kind === "bu";
  const parentId = buParent?.id ?? initial?.parent_order_id ?? null;
  const parentCode = buParent?.code ?? initial?.parent_code ?? null;
  // Tạo bù → điền sẵn khách/sản phẩm/hợp đồng từ lệnh gốc.
  const [productName, setProductName] = useState(initial?.product_name ?? buParent?.product_name ?? "");
  const [contractNo, setContractNo] = useState(initial?.contract_no ?? buParent?.contract_no ?? "");
  const [customerName, setCustomerName] = useState(initial?.customer_name ?? buParent?.customer_name ?? "");
  const [quantity, setQuantity] = useState(initial?.quantity != null ? String(initial.quantity) : "");
  const [orderDate, setOrderDate] = useState(initial?.order_date ?? "");
  const [deliveryDate, setDeliveryDate] = useState(initial?.delivery_request_date ?? "");
  const [docDate, setDocDate] = useState(initial?.doc_date ?? todayISO());
  const [dueDate, setDueDate] = useState(initial?.due_date ?? "");
  const [techPrint, setTechPrint] = useState(initial?.tech_note_print ?? "");
  const [techFinishing, setTechFinishing] = useState(initial?.tech_note_finishing ?? "");
  const [note, setNote] = useState(initial?.note ?? "");
  const [buReason, setBuReason] = useState(initial?.bu_reason ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || saving) return;
    setError(null);
    if (!productName.trim()) return setError("Cần nhập tên sản phẩm.");
    if (isBu && !buReason.trim()) return setError("Cần nhập lý do bù.");
    const payload: ProductionOrderInput = {
      product_name: productName.trim(),
      contract_no: contractNo.trim() || null,
      customer_name: customerName.trim() || null,
      quantity: quantity.trim() ? Number(quantity) : null,
      order_date: orderDate || null,
      delivery_request_date: deliveryDate || null,
      doc_date: docDate || null,
      due_date: dueDate || null,
      order_kind: isBu ? "bu" : "thuong",
      parent_order_id: isBu ? parentId : null,
      bu_reason: isBu ? (buReason.trim() || null) : null,
      tech_note_print: techPrint.trim() || null,
      tech_note_finishing: techFinishing.trim() || null,
      note: note.trim() || null,
    };
    setSaving(true);
    try {
      const saved = initial
        ? await api.production.updateOrder(token, initial.id, payload)
        : await api.production.createOrder(token, payload);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu lệnh sản xuất thất bại.");
      setSaving(false);
    }
  }

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 760, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2>{initial ? `Sửa lệnh sản xuất: ${initial.code}` : isBu ? "Tạo lệnh bù" : "Tạo lệnh sản xuất"}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          {isBu && (
            <div className="md-page__wh-badge" style={{ display: "block", margin: "0 0 14px", padding: "10px 12px", background: "#f0d9c0" }}>
              <div className="md-page__muted" style={{ marginBottom: 4 }}>Lệnh bù cho LSX gốc</div>
              <strong className="md-page__mono">{parentCode ?? `#${parentId}`}</strong>
            </div>
          )}
          <div className="md-page__form-grid">
            {isBu && (
              <label className="field md-page__form-wide">
                <span className="field__label">Lý do bù *</span>
                <input className="input" placeholder="VD: Hàng khách trả lỗi in / hao hụt vượt định mức" value={buReason} onChange={(e) => setBuReason(e.target.value)} />
              </label>
            )}
            <label className="field md-page__form-wide">
              <span className="field__label">Sản phẩm *</span>
              <input className="input" placeholder="VD: Hộp giấy Couche 150gsm" value={productName} onChange={(e) => setProductName(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Theo hợp đồng số</span>
              <input className="input" placeholder="VD: SO-157/07" value={contractNo} onChange={(e) => setContractNo(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Khách hàng</span>
              <input className="input" placeholder="VD: Cty TNHH In Ấn ABC" value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Số lượng</span>
              <input className="input" type="number" step="0.001" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Ngày đặt</span>
              <input className="input" type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Yêu cầu nhận hàng</span>
              <input className="input" type="date" value={deliveryDate} onChange={(e) => setDeliveryDate(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Ngày lập phiếu SX</span>
              <input className="input" type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} />
            </label>
            <label className="field">
              <span className="field__label">Ngày hoàn thành</span>
              <input className="input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </label>
            <label className="field md-page__form-wide">
              <span className="field__label">Lưu ý kỹ thuật khi in</span>
              <textarea className="input" rows={2} value={techPrint} onChange={(e) => setTechPrint(e.target.value)} />
            </label>
            <label className="field md-page__form-wide">
              <span className="field__label">Lưu ý kỹ thuật đóng xén</span>
              <textarea className="input" rows={2} value={techFinishing} onChange={(e) => setTechFinishing(e.target.value)} />
            </label>
            <label className="field md-page__form-wide">
              <span className="field__label">Ghi chú</span>
              <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
          </div>
          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>{initial ? "Lưu thay đổi" : "Tạo lệnh"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
