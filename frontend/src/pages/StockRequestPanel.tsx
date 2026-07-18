// Tab "Đề nghị" trong trang Kho — phiếu ĐỀ NGHỊ nhập/xuất kho (bước TRƯỚC phiếu kho, BRD sơ đồ).
// Vòng đời: Nháp → Chờ duyệt → Đã duyệt → (Lập phiếu) Đã lập phiếu | Từ chối | Đã hủy.
// Quyền: tạo/gửi = kho:read (mọi người xem kho); duyệt = kho:approve; lập phiếu = kho:create.
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  api,
  type KhoItemStatus,
  type KhoMaterialOption,
  type KhoVoucherType,
  type StockRequestInput,
  type StockRequestLineInput,
  type StockRequestRow,
  type VoucherInput,
  type VoucherRow,
  type WarehouseRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { toast } from "../components/Toast";
import { Select, type SelectOption } from "../components/Select";
import { downloadLineTemplate, exportXlsx, matchMaterial, parseLineFile } from "../lib/xlsxImport";
import { VoucherForm, VoucherDetail, specForType, openKhoPrint } from "./StockVoucherPage";

/** Định dạng ngày-giờ VN; rỗng nếu null. */
function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("vi-VN");
}

const R_STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: "Nháp", cls: "md-page__status-badge--draft" },
  pending: { label: "Chờ duyệt", cls: "md-page__status-badge--pending" },
  approved: { label: "Đã duyệt", cls: "md-page__status-badge--approved" },
  rejected: { label: "Từ chối", cls: "md-page__status-badge--rejected" },
  fulfilled: { label: "Đã lập phiếu", cls: "md-page__status-badge--fulfilled" },
  cancelled: { label: "Đã hủy", cls: "md-page__status-badge--cancelled" },
};
const TYPE_LABEL: Record<string, string> = { nhap: "Đề nghị nhập", xuat: "Đề nghị xuất" };

const V_STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: "Nháp", cls: "md-page__status-badge--draft" },
  pending: { label: "Chờ duyệt", cls: "md-page__status-badge--pending" },
  posted: { label: "Đã ghi sổ", cls: "md-page__status-badge--posted" },
  cancelled: { label: "Đã hủy", cls: "md-page__status-badge--cancelled" },
};

export function StockRequestPanel({
  warehouse,
  warehouses,
  materials,
  voucherTypes,
  statuses,
  canApprove,
  canCreate,
  onFulfilled,
  view = "requests",
}: {
  warehouse: WarehouseRow;
  warehouses: WarehouseRow[];
  materials: KhoMaterialOption[];
  voucherTypes: KhoVoucherType[];
  statuses: KhoItemStatus[];
  canApprove: boolean;
  canCreate: boolean;
  /** Sau khi lập phiếu từ đề nghị — để trang cha nạp lại danh sách phiếu kho. */
  onFulfilled: () => void;
  /** "requests" = danh sách đề nghị; "vouchers" = phiếu lập từ đề nghị (2 tab riêng). */
  view?: "requests" | "vouchers";
}) {
  const { token } = useAuth();
  const [rows, setRows] = useState<StockRequestRow[]>([]);
  const [reqVouchers, setReqVouchers] = useState<VoucherRow[]>([]); // phiếu kho lập từ đề nghị
  const [loading, setLoading] = useState(false);
  const [typeF, setTypeF] = useState("");
  const [statusF, setStatusF] = useState("");
  const [q, setQ] = useState(""); // tìm mã / người đề nghị / mã phiếu kho
  const [formOpen, setFormOpen] = useState(false);
  // Import Excel trực tiếp (không qua form): chọn file → kiểm tra → tạo → báo kết quả.
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState<{ ok: number; errs: string[] } | null>(null);
  const importFileRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<StockRequestRow | null>(null);
  const [detail, setDetail] = useState<StockRequestRow | null>(null);
  // Sửa / Hủy(popup lý do) / Xóa phiếu kho ở bảng dưới.
  const [editVoucher, setEditVoucher] = useState<VoucherRow | null>(null);
  const [detailVoucher, setDetailVoucher] = useState<VoucherRow | null>(null); // xem chi tiết phiếu
  const [voucherAction, setVoucherAction] = useState<{ v: VoucherRow; kind: "cancel" | "delete" } | null>(null);
  const [vaBusy, setVaBusy] = useState(false);
  const [vaError, setVaError] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  // Lọc + phân trang bảng "phiếu lập từ đề nghị".
  const [vGroupF, setVGroupF] = useState(""); // nhap/xuat
  const [vStatusF, setVStatusF] = useState("");
  const [vq, setVq] = useState("");
  const [vPage, setVPage] = useState(1);
  const [vPageSize, setVPageSize] = useState(8);
  // Phân trang bảng đề nghị.
  const [reqPage, setReqPage] = useState(1);
  const [reqPageSize, setReqPageSize] = useState(10);


  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    const p = view === "vouchers"
      ? api.kho.listVouchers(token, { warehouse_id: warehouse.id, size: 200 })
          // Phiếu lập từ đề nghị (ref stock_request) + phiếu tạo bằng import Excel (ref import).
          .then((vs) => setReqVouchers(vs.items.filter((v) => v.ref_type === "stock_request" || v.ref_type === "import")))
      : api.kho.listRequests(token, { warehouse_id: warehouse.id, size: 200 })
          .then((rs) => setRows(rs.items));
    p.catch(() => {}).finally(() => setLoading(false));
  }, [token, warehouse.id, view]);

  // Import Excel thẳng: đọc file → gộp theo "Nhóm phiếu" → kiểm tra tất cả → tạo nhiều đề nghị/phiếu.
  async function runImport(file: File) {
    if (!token) return;
    const kind: "request" | "voucher" = view === "vouchers" ? "voucher" : "request";
    const docLabel = kind === "request" ? "đề nghị" : "phiếu";
    setImportBusy(true); setImportResult(null);
    try {
      const lines = await parseLineFile(file);
      if (lines.length === 0) { setImportResult({ ok: 0, errs: ["File trống hoặc chưa có dòng dữ liệu."] }); setImportBusy(false); return; }
      const types = voucherTypes.filter((t) => t.is_active !== false && (t.voucher_group === "nhap" || t.voucher_group === "xuat"));
      const defType = types.find((t) => t.voucher_group === "nhap") ?? types[0] ?? null;
      const parsed = lines.map((line) => ({ line, mat: matchMaterial(materials, line.code, line.name) }));
      // Gộp theo "Nhóm phiếu" (trống → chung 1 nhóm).
      const map = new Map<string, typeof parsed>();
      for (const r of parsed) { const key = r.line.group.trim() || "1"; if (!map.has(key)) map.set(key, []); map.get(key)!.push(r); }
      const groups = [...map.entries()].map(([key, grows]) => {
        const typeText = grows.map((g) => g.line.typeText).find((t) => t.trim())?.trim() ?? "";
        const s = typeText.toLowerCase();
        const type = s ? (types.find((t) => t.code.toLowerCase() === s || t.name.toLowerCase() === s) ?? null) : defType;
        const partner = grows.map((g) => g.line.partner).find((p) => p.trim())?.trim() || "";
        return { key, rows: grows, type, typeText, partner };
      });
      // Kiểm tra toàn bộ — 1 lỗi là chặn hết.
      const errs: string[] = [];
      parsed.forEach((r, i) => {
        if (!r.mat) errs.push(`Dòng ${i + 2}: không khớp vật tư "${r.line.code || r.line.name}"`);
        else if (!(r.line.qty > 0)) errs.push(`Dòng ${i + 2} (${r.mat.code}): SL ≤ 0`);
      });
      groups.forEach((g) => { if (!g.type) errs.push(`Nhóm "${g.key}": không rõ Loại phiếu${g.typeText ? ` ("${g.typeText}")` : ""}`); });
      if (errs.length) { setImportResult({ ok: 0, errs }); setImportBusy(false); return; }
      // Tạo từng nhóm.
      const codes: string[] = [];
      for (const g of groups) {
        const type = g.type!;
        const isNhap = type.voucher_group !== "xuat";
        if (kind === "request") {
          const rlines = g.rows.map((r) => ({ material_id: r.mat!.id, quantity: r.line.qty, uom: r.line.unit || r.mat!.unit || null, note: r.line.note || null }));
          const rr = await api.kho.createRequest(token, { request_type: isNhap ? "nhap" : "xuat", voucher_type_id: type.id, warehouse_id: warehouse.id, partner_ref: g.partner || null, reason: null, lines: rlines });
          codes.push(rr.code);
        } else {
          const hasCost = specForType(type).showCost;
          const vlines = g.rows.map((r) => ({ material_id: r.mat!.id, quantity: r.line.qty, uom: r.line.unit || r.mat!.unit || null, unit_cost: hasCost ? (r.line.unitCost ?? null) : null, note: r.line.note || null }));
          const header: VoucherInput = { voucher_type_id: type.id, doc_date: new Date().toISOString().slice(0, 10), partner_ref: g.partner || null, ref_type: "import", reason: null, lines: vlines };
          if (isNhap) header.dst_warehouse_id = warehouse.id; else header.src_warehouse_id = warehouse.id;
          const vv = await api.kho.createVoucher(token, header);
          codes.push(vv.code);
        }
      }
      setImportResult({ ok: codes.length, errs: [] });
      load(); if (kind === "voucher") onFulfilled();
      toast(codes.length === 1 ? `✓ Đã tạo ${codes[0]} từ Excel` : `✓ Đã tạo ${codes.length} ${docLabel} từ Excel`, "success");
    } catch (e) {
      setImportResult({ ok: 0, errs: [e instanceof ApiError ? e.message : "Import thất bại."] });
    } finally {
      setImportBusy(false);
    }
  }


  async function runVoucherAction() {
    if (!token || !voucherAction || vaBusy) return;
    setVaBusy(true); setVaError(null);
    try {
      if (voucherAction.kind === "delete") await api.kho.deleteVoucher(token, voucherAction.v.id);
      else await api.kho.cancelVoucher(token, voucherAction.v.id, cancelReason.trim() || undefined);
      setVoucherAction(null); setVaBusy(false); setCancelReason(""); load(); onFulfilled();
    } catch (err) {
      setVaError(err instanceof ApiError ? err.message : "Thao tác thất bại.");
      setVaBusy(false);
    }
  }

  useEffect(() => { load(); }, [load]);

  // Cập nhật TỨC THỜI qua SSE: CHỈ tải lại khi chữ ký dữ liệu ĐỔI (có thay đổi thật), bỏ qua
  // sự kiện baseline lúc kết nối / kết nối lại → không còn refresh liên tục.
  const esRef = useRef<EventSource | null>(null);
  useEffect(() => {
    if (!token) return;
    const es = new EventSource(api.kho.eventsUrl(token, warehouse.id));
    esRef.current = es;
    let lastSig: string | null = null;
    es.onmessage = (e) => {
      let sig: string | null = null;
      try { sig = JSON.parse(e.data)?.sig ?? null; } catch { sig = e.data; }
      if (lastSig !== null && sig !== lastSig && document.visibilityState === "visible") load();
      lastSig = sig;
    };
    return () => { es.close(); esRef.current = null; };
  }, [token, warehouse.id, load]);

  // Dự phòng: CHỈ khi SSE không mở được (proxy chặn) mới poll thưa; SSE chạy thì đứng yên.
  useEffect(() => {
    const id = window.setInterval(() => {
      const es = esRef.current;
      if ((!es || es.readyState !== 1) && document.visibilityState === "visible") load();
    }, 60000);
    return () => window.clearInterval(id);
  }, [load]);

  const kw = q.trim().toLowerCase();
  const filtered = rows.filter(
    (r) => (!typeF || r.request_type === typeF)
      && (!statusF || r.status === statusF)
      && (!kw || r.code.toLowerCase().includes(kw)
        || (r.requested_by_name ?? "").toLowerCase().includes(kw)
        || (r.voucher_code ?? "").toLowerCase().includes(kw)),
  );
  const reqPages = Math.max(1, Math.ceil(filtered.length / reqPageSize));
  const reqCur = Math.min(reqPage, reqPages);
  const reqPageRows = filtered.slice((reqCur - 1) * reqPageSize, reqCur * reqPageSize);

  // Danh sách loại phiếu (nhập/xuất, đang bật) → kèm sheet tra cứu "LoaiPhieu" trong file mẫu.
  const docTypeOpts = useMemo(
    () => voucherTypes
      .filter((t) => t.is_active !== false && (t.voucher_group === "nhap" || t.voucher_group === "xuat"))
      .map((t) => ({ code: t.code, name: t.name, group: t.voucher_group })),
    [voucherTypes],
  );

  // Lọc + phân trang bảng phiếu lập từ đề nghị.
  const vTypeById = useMemo(() => new Map(voucherTypes.map((t) => [t.id, t])), [voucherTypes]);
  const vKw = vq.trim().toLowerCase();
  const vFiltered = reqVouchers.filter((v) => {
    const t = vTypeById.get(v.voucher_type_id);
    return (!vGroupF || t?.voucher_group === vGroupF)
      && (!vStatusF || v.status === vStatusF)
      && (!vKw || v.code.toLowerCase().includes(vKw)
        || (v.partner_ref ?? "").toLowerCase().includes(vKw)
        || (t?.name ?? "").toLowerCase().includes(vKw));
  });
  const vPages = Math.max(1, Math.ceil(vFiltered.length / vPageSize));
  const vCurPage = Math.min(vPage, vPages);
  const vPageRows = vFiltered.slice((vCurPage - 1) * vPageSize, vCurPage * vPageSize);

  const docLabel = view === "vouchers" ? "phiếu" : "đề nghị";
  // Input file ẩn + banner kết quả (dùng chung cho cả 2 tab).
  const importUI = (
    <>
      <input ref={importFileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) runImport(f); e.target.value = ""; }} />
      {importResult && (
        <div className="banner" role="status" style={{ marginBottom: 10, background: importResult.errs.length ? "#fdf6e3" : "#dcecdc", color: importResult.errs.length ? "#8a5a00" : "#244a2e", border: "1px solid rgba(0,0,0,.08)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>{importResult.errs.length
              ? `Không import — có ${importResult.errs.length} lỗi (sửa hết trong file rồi import lại).`
              : `✓ Đã tạo ${importResult.ok} ${docLabel} từ Excel.`}</span>
            <div className="md-page__toolbar-spacer" />
            <button type="button" onClick={() => setImportResult(null)} style={{ background: "none", border: "none", cursor: "pointer" }}>✕</button>
          </div>
          {importResult.errs.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 140, overflowY: "auto", fontSize: 13 }}>
              {importResult.errs.slice(0, 30).map((m, i) => <li key={i}>{m}</li>)}
              {importResult.errs.length > 30 && <li>… và {importResult.errs.length - 30} lỗi nữa</li>}
            </ul>
          )}
        </div>
      )}
    </>
  );

  return (
    <>
      {view === "requests" && (<>
      {importUI}
      <div className="md-page__toolbar" style={{ marginBottom: 10 }}>
        <input className="input" placeholder="Tìm mã / người đề nghị / mã phiếu…" value={q}
          onChange={(e) => { setQ(e.target.value); setReqPage(1); }} style={{ minWidth: 240 }} />
        <select className="input" style={{ width: 170 }} value={typeF} onChange={(e) => { setTypeF(e.target.value); setReqPage(1); }}>
          <option value="">— Nhập & Xuất —</option>
          <option value="nhap">Đề nghị nhập</option>
          <option value="xuat">Đề nghị xuất</option>
        </select>
        <select className="input" style={{ width: 170 }} value={statusF} onChange={(e) => { setStatusF(e.target.value); setReqPage(1); }}>
          <option value="">— Tất cả trạng thái —</option>
          {Object.entries(R_STATUS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        <div className="md-page__toolbar-spacer" />
        <span className="md-page__muted" style={{ marginRight: 10 }}>{filtered.length} đề nghị</span>
        <Button variant="ghost" onClick={() => exportXlsx(
          `de-nghi-${warehouse.code}.xlsx`,
          ["Loại phiếu", "Nhóm phiếu", "Mã vật tư", "Tên vật tư", "Số lượng", "Đơn vị", "Đối tượng", "Ghi chú", "Trạng thái", "Người đề nghị", "Phiếu kho"],
          // Chi tiết: mỗi sản phẩm 1 dòng; "Nhóm phiếu" = mã đề nghị (gộp các dòng cùng 1 đề nghị) → import lại được.
          filtered.flatMap((r) => {
            const typeCode = r.voucher_type_id != null ? (vTypeById.get(r.voucher_type_id)?.code ?? "") : "";
            const st = R_STATUS[r.status]?.label ?? r.status;
            const tail = [r.partner_ref ?? "", st, r.requested_by_name ?? "", r.voucher_code ?? ""];
            return r.lines.length
              ? r.lines.map((ln) => [typeCode, r.code, ln.material_code ?? "", ln.material_name ?? "", ln.quantity, ln.uom ?? "", tail[0], ln.note ?? "", tail[1], tail[2], tail[3]])
              : [[typeCode, r.code, "", "", "", "", tail[0], "", tail[1], tail[2], tail[3]]];
          }),
          "DeNghi",
        )}>⭱ Xuất Excel</Button>
        <Button variant="ghost" onClick={() => downloadLineTemplate("mau-de-nghi.xlsx", { withGroups: true, types: docTypeOpts })}>⭳ Tải mẫu Excel</Button>
        <Button variant="ghost" loading={importBusy} onClick={() => importFileRef.current?.click()}>⭱ Import Excel</Button>
        <Button variant="primary" onClick={() => { setEditing(null); setFormOpen(true); }}>+ Tạo đề nghị</Button>
      </div>

      <div className="card md-page__tablewrap md-page__tablewrap--scroll">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã</th><th>Loại</th><th>Số dòng</th><th>Người đề nghị</th><th>Phiếu kho</th><th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="md-page__status">Đang tải...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={6} className="md-page__empty">Chưa có đề nghị nào cho kho này.</td></tr>
            ) : reqPageRows.map((r) => {
              const st = R_STATUS[r.status] ?? { label: r.status, cls: "is-inactive" };
              return (
                <tr key={r.id} className="md-page__row" onClick={() => setDetail(r)} title="Bấm để xem / thao tác">
                  <td className="md-page__mono">{r.code}</td>
                  <td>{TYPE_LABEL[r.request_type] ?? r.request_type}</td>
                  <td>{r.lines.length}</td>
                  <td>{r.requested_by_name || <span className="md-page__muted">—</span>}</td>
                  <td className="md-page__mono">{r.voucher_code || <span className="md-page__muted">—</span>}</td>
                  <td><span className={`md-page__status-badge ${st.cls}`}>{st.label}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {filtered.length > 0 && (
        <div className="md-page__pager" style={{ marginTop: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="md-page__muted">Hiển thị</span>
            <select className="input" style={{ width: 72 }} value={reqPageSize}
              onChange={(e) => { setReqPageSize(Number(e.target.value)); setReqPage(1); }}>
              {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <span className="md-page__muted">dòng · Trang {reqCur}/{reqPages}</span>
          </div>
          {reqPages > 1 && (
            <div className="md-page__pager-btns">
              <Button variant="ghost" onClick={() => setReqPage((p) => Math.max(1, p - 1))} disabled={reqCur <= 1}>‹ Trước</Button>
              <Button variant="ghost" onClick={() => setReqPage((p) => Math.min(reqPages, p + 1))} disabled={reqCur >= reqPages}>Sau ›</Button>
            </div>
          )}
        </div>
      )}
      </>)}

      {/* ===== TAB RIÊNG: PHIẾU KHO lập từ đề nghị đã duyệt ===== */}
      {view === "vouchers" && (<>
      {importUI}
      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 8px" }}>
        <span className="md-page__muted">{vFiltered.length} phiếu (từ đề nghị / import)</span>
        <div className="md-page__toolbar-spacer" />
        <Button variant="ghost" onClick={() => exportXlsx(
          `phieu-tu-de-nghi-${warehouse.code}.xlsx`,
          ["Mã phiếu", "Loại", "Đối tượng", "Số dòng", "Trạng thái"],
          vFiltered.map((v) => [v.code, vTypeById.get(v.voucher_type_id)?.name ?? `#${v.voucher_type_id}`,
            v.partner_ref ?? "", v.lines.length, V_STATUS[v.status]?.label ?? v.status]),
          "Phieu",
        )}>⭱ Xuất Excel</Button>
        {canCreate && (
          <>
            <Button variant="ghost" onClick={() => downloadLineTemplate("mau-phieu-kho.xlsx", { withPrice: true, withGroups: true, types: docTypeOpts })}>⭳ Tải mẫu Excel</Button>
            <Button variant="ghost" loading={importBusy} onClick={() => importFileRef.current?.click()}>⭱ Import Excel</Button>
          </>
        )}
      </div>
      <div className="md-page__toolbar" style={{ marginBottom: 10 }}>
        <input className="input" placeholder="Tìm mã phiếu / đối tượng / loại…" value={vq}
          onChange={(e) => { setVq(e.target.value); setVPage(1); }} style={{ minWidth: 240 }} />
        <select className="input" style={{ width: 150 }} value={vGroupF}
          onChange={(e) => { setVGroupF(e.target.value); setVPage(1); }}>
          <option value="">— Nhập & Xuất —</option>
          <option value="nhap">Phiếu nhập</option>
          <option value="xuat">Phiếu xuất</option>
        </select>
        <select className="input" style={{ width: 160 }} value={vStatusF}
          onChange={(e) => { setVStatusF(e.target.value); setVPage(1); }}>
          <option value="">— Tất cả trạng thái —</option>
          <option value="draft">Nháp</option>
          <option value="pending">Chờ duyệt</option>
          <option value="posted">Đã ghi sổ</option>
          <option value="cancelled">Đã hủy</option>
        </select>
      </div>
      <div className="card md-page__tablewrap md-page__tablewrap--scroll">
        <table className="md-page__table">
          <thead>
            <tr>
              <th>Mã phiếu</th><th>Loại</th><th>Đối tượng</th><th>Số dòng</th><th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {vPageRows.length === 0 ? (
              <tr><td colSpan={5} className="md-page__empty">{reqVouchers.length === 0 ? "Chưa có phiếu nào. Duyệt 1 đề nghị ở trên rồi bấm “Lập phiếu kho”." : "Không có phiếu khớp bộ lọc."}</td></tr>
            ) : vPageRows.map((v) => {
              const t = vTypeById.get(v.voucher_type_id);
              const st = V_STATUS[v.status] ?? { label: v.status, cls: "is-inactive" };
              return (
                <tr key={v.id} className="md-page__row" onClick={() => setDetailVoucher(v)} title="Bấm để xem / thao tác">
                  <td className="md-page__mono">{v.code}</td>
                  <td>{t ? t.name : `#${v.voucher_type_id}`}</td>
                  <td>{v.partner_ref || <span className="md-page__muted">—</span>}</td>
                  <td>{v.lines.length}</td>
                  <td><span className={`md-page__status-badge ${st.cls}`}>{st.label}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="md-page__pager" style={{ marginTop: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="md-page__muted">Hiển thị</span>
          <select className="input" style={{ width: 72 }} value={vPageSize}
            onChange={(e) => { setVPageSize(Number(e.target.value)); setVPage(1); }}>
            {[8, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <span className="md-page__muted">dòng · Trang {vCurPage}/{vPages}</span>
        </div>
        {vPages > 1 && (
          <div className="md-page__pager-btns">
            <Button variant="ghost" onClick={() => setVPage((p) => Math.max(1, p - 1))} disabled={vCurPage <= 1}>‹ Trước</Button>
            <Button variant="ghost" onClick={() => setVPage((p) => Math.min(vPages, p + 1))} disabled={vCurPage >= vPages}>Sau ›</Button>
          </div>
        )}
      </div>
      </>)}

      {formOpen && (
        <RequestForm
          warehouse={warehouse}
          materials={materials}
          voucherTypes={voucherTypes}
          editing={editing}
          onClose={() => { setFormOpen(false); setEditing(null); }}
          onSaved={() => { setFormOpen(false); setEditing(null); load(); }}
        />
      )}
      {detail && (
        <RequestDetail
          request={detail}
          voucherTypes={voucherTypes}
          canApprove={canApprove}
          canCreate={canCreate}
          onClose={() => setDetail(null)}
          onEdit={() => { setEditing(detail); setDetail(null); setFormOpen(true); }}
          onChanged={(fulfilled) => { setDetail(null); load(); if (fulfilled) onFulfilled(); }}
        />
      )}
      {/* Xem chi tiết phiếu kho (bấm dòng hoặc icon 👁). */}
      {detailVoucher && (
        <VoucherDetail
          voucher={detailVoucher}
          types={voucherTypes}
          warehouses={warehouses}
          materials={materials}
          statuses={statuses}
          canApprove={canApprove}
          canCreate={canCreate}
          onClose={() => setDetailVoucher(null)}
          onChanged={() => { setDetailVoucher(null); load(); onFulfilled(); }}
          onOpenRequest={async (rid) => {
            if (!token) return;
            try { const req = await api.kho.getRequest(token, rid); setDetailVoucher(null); setDetail(req); }
            catch { /* không mở được đề nghị → bỏ qua */ }
          }}
          onEdit={() => { const v = detailVoucher; setDetailVoucher(null); setEditVoucher(v); }}
          onDelete={() => { const v = detailVoucher; setDetailVoucher(null); setVaError(null); setVoucherAction({ v, kind: "delete" }); }}
        />
      )}
      {/* Sửa phiếu kho (nháp) từ icon ✏️ ở bảng dưới. */}
      {editVoucher && (
        <VoucherForm
          types={voucherTypes}
          warehouses={warehouses}
          materials={materials}
          statuses={statuses}
          lockedWarehouse={warehouse}
          editing={editVoucher}
          onClose={() => setEditVoucher(null)}
          onSaved={() => { setEditVoucher(null); load(); onFulfilled(); }}
        />
      )}

      {/* Hủy (có lý do) / Xóa phiếu kho — popup tham khảo trang Mua hàng. */}
      <ConfirmDialog
        open={!!voucherAction}
        danger
        title={voucherAction?.kind === "delete" ? "Xóa phiếu?" : "Hủy phiếu?"}
        message={voucherAction?.kind === "delete"
          ? `Xóa hẳn phiếu ${voucherAction?.v.code} (nháp). Không khôi phục được.`
          : undefined}
        confirmLabel={voucherAction?.kind === "delete" ? "Xóa" : "Hủy phiếu"}
        cancelLabel="Đóng"
        busy={vaBusy}
        error={vaError}
        onConfirm={runVoucherAction}
        onCancel={() => { if (!vaBusy) { setVoucherAction(null); setVaError(null); } }}
      >
        {voucherAction?.kind === "cancel" && (
          <>
            <div style={{ marginBottom: 8 }}>Phiếu <b className="md-page__mono">{voucherAction.v.code}</b></div>
            <label className="field" style={{ width: "100%" }}>
              <span className="field__label">Lý do / ghi chú</span>
              <textarea className="input" rows={3} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
            </label>
          </>
        )}
      </ConfirmDialog>
    </>
  );
}

// --- Form tạo/sửa đề nghị (chỉ SL đề nghị; SL thực nhận điền lúc lập phiếu) ---
function RequestForm({
  warehouse,
  materials,
  voucherTypes,
  editing,
  onClose,
  onSaved,
}: {
  warehouse: WarehouseRow;
  materials: KhoMaterialOption[];
  voucherTypes: KhoVoucherType[];
  editing: StockRequestRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  // Đủ CASE nhập/xuất như phiếu kho (NK-GK, NK-NVL, XK-KH, XK-SX…). Bỏ chuyển kho (làm ở Phiếu kho).
  const shownTypes = useMemo(
    () => voucherTypes.filter((t) => t.is_active !== false && (t.voucher_group === "nhap" || t.voucher_group === "xuat")),
    [voucherTypes],
  );
  const [voucherTypeId, setVoucherTypeId] = useState<number | null>(
    editing?.voucher_type_id ?? shownTypes.find((t) => t.voucher_group === "nhap")?.id ?? shownTypes[0]?.id ?? null,
  );
  const selType = shownTypes.find((t) => t.id === voucherTypeId);
  const requestType: "nhap" | "xuat" = selType?.voucher_group === "xuat" ? "xuat" : "nhap";
  const spec = specForType(selType);
  const [partnerRef, setPartnerRef] = useState(editing?.partner_ref ?? "");
  // Chỉ NCC map danh mục (module Nhà cung cấp). Khách hàng nhập tay — chưa có module lưu KH.
  const partnerCatalog: "ncc" | null = spec.partnerKind === "ncc" ? "ncc" : null;
  const [partnerOpts, setPartnerOpts] = useState<{ id: number; name: string }[]>([]);
  useEffect(() => {
    if (!token || !partnerCatalog) { setPartnerOpts([]); return; }
    api.kho.partnerOptions(token, partnerCatalog).then(setPartnerOpts).catch(() => setPartnerOpts([]));
  }, [token, partnerCatalog]);
  const partnerSelectOptions = useMemo<SelectOption<string>[]>(
    () => partnerOpts.map((p) => ({ value: p.name, label: p.name })),
    [partnerOpts],
  );
  const [reason, setReason] = useState(editing?.reason ?? "");
  const [lines, setLines] = useState<StockRequestLineInput[]>(
    editing?.lines.map((l) => ({ material_id: l.material_id, quantity: Number(l.quantity), uom: l.uom, note: l.note })) ?? [],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matById = useMemo(() => new Map(materials.map((m) => [m.id, m])), [materials]);
  // Options cho ô chọn vật tư có tìm kiếm (nhãn = tên, hint = mã; lọc theo cả 2).
  const materialOptions = useMemo<SelectOption<number>[]>(
    () => materials.map((m) => ({ value: m.id, label: m.name, hint: m.code })),
    [materials],
  );
  // Tồn hiện tại theo vật tư (tham chiếu trên dòng hàng).
  const [stockMap, setStockMap] = useState<Map<number, number>>(new Map());
  useEffect(() => {
    if (!token) return;
    api.kho.stock(token, { warehouse_id: warehouse.id }).then((r) => {
      const m = new Map<number, number>();
      for (const b of r.items) m.set(b.material_id, (m.get(b.material_id) ?? 0) + b.on_hand);
      setStockMap(m);
    }).catch(() => {});
  }, [token, warehouse.id]);

  function addLine() {
    // Dòng mới để TRỐNG vật tư — người dùng tự chọn trong danh sách.
    setLines((ls) => [...ls, { material_id: 0, quantity: 1, uom: "", note: "" }]);
  }
  function setLine(i: number, patch: Partial<StockRequestLineInput>) {
    setLines((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  }
  function pickMaterial(i: number, materialId: number) {
    const m = matById.get(materialId);
    setLine(i, { material_id: materialId, uom: m?.unit ?? "", note: m?.note?.trim() || "" });
  }

  // submitAfter = lưu xong gửi duyệt luôn (draft → chờ duyệt) trong 1 thao tác.
  async function save(submitAfter: boolean) {
    if (!token || saving) return;
    setError(null);
    if (lines.length === 0) return setError("Thêm ít nhất 1 dòng vật tư.");
    if (lines.some((l) => !l.material_id)) return setError("Có dòng chưa chọn vật tư.");
    if (lines.some((l) => !(Number(l.quantity) > 0))) return setError("Số lượng đề nghị phải > 0.");
    if (!voucherTypeId) return setError("Chọn loại phiếu.");
    const input: StockRequestInput = {
      request_type: requestType,
      voucher_type_id: voucherTypeId,
      warehouse_id: warehouse.id,
      partner_ref: partnerRef.trim() || null,
      reason: reason.trim() || null,
      lines: lines.map((l) => ({ ...l, quantity: Number(l.quantity) })),
    };
    setSaving(true);
    try {
      const saved = editing
        ? await api.kho.updateRequest(token, editing.id, input)
        : await api.kho.createRequest(token, input);
      if (submitAfter && saved.status === "draft") await api.kho.submitRequest(token, saved.id);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu đề nghị thất bại.");
      setSaving(false);
    }
  }
  const onSubmit = (e: FormEvent) => { e.preventDefault(); save(false); };

  return (
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 760, width: "94%" }}>
        <div className="md-page__dialog-head">
          <h2>{editing ? `Sửa đề nghị · ${editing.code}` : "Tạo đề nghị kho"} · {warehouse.code} {warehouse.name}</h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <form className="md-page__dialog-body" onSubmit={onSubmit}>
          <div className="md-page__form-grid">
            <label className="field">
              <span className="field__label">Loại phiếu *</span>
              <select className="input" value={voucherTypeId ?? ""} disabled={!!editing}
                onChange={(e) => setVoucherTypeId(e.target.value ? Number(e.target.value) : null)}>
                <optgroup label="Nhập kho">
                  {shownTypes.filter((t) => t.voucher_group === "nhap").map((t) => (
                    <option key={t.id} value={t.id}>{t.code} · {t.name}</option>
                  ))}
                </optgroup>
                <optgroup label="Xuất kho">
                  {shownTypes.filter((t) => t.voucher_group === "xuat").map((t) => (
                    <option key={t.id} value={t.id}>{t.code} · {t.name}</option>
                  ))}
                </optgroup>
              </select>
            </label>
            <label className="field">
              <span className="field__label">{spec.partnerKind ? spec.partnerLabel : "Đối tượng"}</span>
              {partnerCatalog ? (
                <Select
                  portal
                  searchable
                  clearable
                  placeholder="— Chọn nhà cung cấp —"
                  searchPlaceholder="Tìm nhà cung cấp…"
                  ariaLabel={spec.partnerLabel}
                  value={partnerRef || null}
                  options={partnerSelectOptions}
                  onChange={(v) => setPartnerRef(v ? String(v) : "")}
                />
              ) : (
                <input className="input" placeholder={spec.partnerPlaceholder || "VD: Cty ABC / Tổ in"}
                  value={partnerRef} onChange={(e) => setPartnerRef(e.target.value)} />
              )}
            </label>
            <label className="field md-page__form-wide">
              <span className="field__label">Lý do / Diễn giải</span>
              <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "6px 0" }}>
            <strong>Dòng hàng đề nghị</strong>
            <Button type="button" variant="ghost" onClick={addLine}>+ Thêm mặt hàng</Button>
          </div>
          <div className="md-page__tablewrap">
            <table className="md-page__table">
              <thead>
                <tr>
                  <th style={{ width: 90 }}>Mã</th>
                  <th>Vật tư</th>
                  <th style={{ width: 90, textAlign: "right" }}>Tồn hiện tại</th>
                  <th style={{ width: 100 }}>SL đề nghị</th>
                  <th style={{ width: 70 }}>Đơn vị</th>
                  <th style={{ width: 150 }}>NCC</th>
                  <th>Ghi chú</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {lines.length === 0 ? (
                  <tr><td colSpan={8} className="md-page__empty">Chưa có dòng nào. Bấm “+ Thêm mặt hàng”.</td></tr>
                ) : lines.map((l, i) => {
                  const m = l.material_id ? matById.get(l.material_id) : null;
                  const onHand = l.material_id ? stockMap.get(l.material_id) : undefined;
                  return (
                  <tr key={i}>
                    <td className="md-page__mono">{m ? m.code : <span className="md-page__muted">—</span>}</td>
                    <td>
                      <Select
                        portal
                        searchable
                        searchPlaceholder="Tìm mã / tên vật tư…"
                        placeholder="— Chọn vật tư —"
                        ariaLabel="Chọn vật tư"
                        value={l.material_id || null}
                        options={materialOptions}
                        onChange={(v) => pickMaterial(i, Number(v))}
                      />
                    </td>
                    <td style={{ textAlign: "right" }}>{onHand != null ? onHand.toLocaleString("vi-VN") : <span className="md-page__muted">—</span>}</td>
                    <td><input className="input" type="number" step="0.001" min="0" value={l.quantity} onChange={(e) => setLine(i, { quantity: Number(e.target.value) })} /></td>
                    <td><input className="input" value={l.uom ?? ""} onChange={(e) => setLine(i, { uom: e.target.value })} /></td>
                    <td>{m?.default_supplier || <span className="md-page__muted">—</span>}</td>
                    <td><input className="input" placeholder="Ghi chú" value={l.note ?? ""} onChange={(e) => setLine(i, { note: e.target.value })} /></td>
                    <td style={{ textAlign: "center" }}>
                      <button type="button" className="btn btn--ghost" style={{ padding: "2px 8px", color: "var(--rust)" }}
                        onClick={() => setLines((ls) => ls.filter((_, k) => k !== i))}>✕</button>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {materials.length === 0 && (
            <div className="banner banner--warn" role="status">Kho này chưa có vật tư nào. Vào tab <strong>Danh mục</strong> tạo vật tư trước.</div>
          )}
          {error && <div className="banner banner--error" role="alert">{error}</div>}
          <div className="md-page__dialog-actions">
            <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
            <div style={{ flex: 1 }} />
            <Button type="button" variant="ghost" loading={saving} onClick={() => save(false)}>Lưu nháp</Button>
            <Button type="button" variant="primary" loading={saving} onClick={() => save(true)}>Lưu &amp; gửi duyệt</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Chi tiết đề nghị + hành động theo trạng thái ---
function RequestDetail({
  request,
  voucherTypes,
  canApprove,
  canCreate,
  onClose,
  onEdit,
  onChanged,
}: {
  request: StockRequestRow;
  voucherTypes: KhoVoucherType[];
  canApprove: boolean;
  canCreate: boolean;
  onClose: () => void;
  onEdit: () => void;
  onChanged: (fulfilled: boolean) => void;
}) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false); // cảnh báo trước khi Hủy đề nghị
  // Loại phiếu khớp chiều đề nghị để lập phiếu.
  const vtypeOpts = voucherTypes.filter((t) => t.voucher_group === request.request_type && t.is_active);
  const typeName = request.voucher_type_name ?? vtypeOpts.find((t) => t.id === request.voucher_type_id)?.name ?? null;
  // Ưu tiên đúng loại phiếu đã chọn khi tạo đề nghị.
  const [vtypeId, setVtypeId] = useState<number | null>(request.voucher_type_id ?? vtypeOpts[0]?.id ?? null);

  const st = R_STATUS[request.status] ?? { label: request.status, cls: "is-inactive" };

  async function act(fn: () => Promise<unknown>, fulfilled = false) {
    if (!token || busy) return;
    setBusy(true); setError(null);
    try { await fn(); onChanged(fulfilled); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Thao tác thất bại."); setBusy(false); }
  }

  function printRequest() {
    // Ngày lập: "Ngày dd tháng mm năm yyyy" theo created_at.
    const d = request.created_at ? new Date(request.created_at) : null;
    const dateLine = d && !Number.isNaN(d.getTime())
      ? `Ngày ${String(d.getDate()).padStart(2, "0")} tháng ${String(d.getMonth() + 1).padStart(2, "0")} năm ${d.getFullYear()}`
      : undefined;
    const total = request.lines.reduce((s, l) => s + Number(l.quantity), 0);
    openKhoPrint({
      title: request.request_type === "nhap" ? "PHIẾU ĐỀ NGHỊ NHẬP KHO" : "PHIẾU ĐỀ NGHỊ XUẤT KHO",
      code: request.code,
      dateLine,
      metaRows: [
        ["Loại phiếu", request.voucher_type_name ?? (request.request_type === "nhap" ? "Nhập kho" : "Xuất kho")],
        ["Kho", `${request.warehouse_code ?? ""} ${request.warehouse_name ?? ""}`.trim() || "………"],
        [request.request_type === "nhap" ? "Nhà cung cấp / Nguồn" : "Bộ phận / Tổ nhận", request.partner_ref ?? "………"],
        ["Người đề nghị", request.requested_by_name ?? "………"],
        ...(request.approved_by_name
          ? [["Người duyệt", `${request.approved_by_name}${request.approved_at ? " · " + fmtDateTime(request.approved_at) : ""}`] as [string, string]]
          : []),
        ["Lý do", request.reason ?? "………"],
      ],
      columns: [
        { label: "STT", align: "c", width: "34px" },
        { label: "Mã hàng", width: "110px" },
        { label: "Tên hàng" },
        { label: "ĐVT", align: "c", width: "56px" },
        { label: "SL đề nghị", align: "r", width: "90px" },
        { label: "Ghi chú", width: "150px" },
      ],
      rows: request.lines.map((l, i) => [
        i + 1, l.material_code ?? "—", l.material_name ?? `#${l.material_id}`,
        l.uom ?? "—", Number(l.quantity).toLocaleString("vi-VN"), l.note ?? "",
      ]),
      footRow: ["", "", "", "Cộng", total.toLocaleString("vi-VN"), ""],
      note: `Trạng thái: ${R_STATUS[request.status]?.label ?? request.status}`,
      signRoles: ["NGƯỜI ĐỀ NGHỊ", "NGƯỜI DUYỆT", "THỦ KHO"],
    });
  }

  return (
    <>
    <div className="md-page__overlay" role="dialog">
      <div className="md-page__dialog card" style={{ maxWidth: 720, width: "94%", maxHeight: "88vh", display: "flex", flexDirection: "column" }}>
        <div className="md-page__dialog-head">
          <h2>{TYPE_LABEL[request.request_type]} · {request.code}
            <span className={`md-page__status-badge ${st.cls}`} style={{ marginLeft: 10 }}>{st.label}</span>
          </h2>
          <button type="button" className="md-page__close" onClick={onClose}>✕</button>
        </div>
        <div className="md-page__dialog-body" style={{ overflowY: "auto" }}>
          <div className="md-page__form-grid" style={{ marginBottom: 10 }}>
            <div className="field">
              <span className="field__label">Loại phiếu {request.voucher_code ? "(đã lập)" : "(sẽ lập)"}</span>
              <div><strong>{typeName ?? (request.request_type === "nhap" ? "Nhập kho" : "Xuất kho")}</strong></div>
            </div>
            <div className="field"><span className="field__label">Kho</span><div>{request.warehouse_code} · {request.warehouse_name}</div></div>
            <div className="field"><span className="field__label">{request.request_type === "nhap" ? "NCC / Nguồn" : "Bộ phận / Tổ nhận"}</span><div>{request.partner_ref || "—"}</div></div>
            <div className="field"><span className="field__label">Người đề nghị</span><div>{request.requested_by_name || "—"}</div></div>
            <div className="field">
              <span className="field__label">{request.status === "rejected" ? "Người từ chối" : "Người duyệt"}</span>
              <div>
                {request.approved_by_name || "—"}
                {request.approved_at && (
                  <span className="md-page__muted"> · {fmtDateTime(request.approved_at)}</span>
                )}
              </div>
            </div>
            <div className="field md-page__form-wide"><span className="field__label">Lý do</span><div>{request.reason || "—"}</div></div>
            {request.status === "rejected" && request.rejected_reason && (
              <div className="field md-page__form-wide"><span className="field__label">Lý do từ chối</span><div style={{ color: "var(--rust)" }}>{request.rejected_reason}</div></div>
            )}
            {request.voucher_code && (
              <div className="field md-page__form-wide"><span className="field__label">Phiếu kho đã lập</span><div className="md-page__mono">{request.voucher_code}</div></div>
            )}
          </div>

          <div className="md-page__tablewrap">
            <table className="md-page__table">
              <thead><tr><th>Vật tư</th><th style={{ textAlign: "right" }}>SL đề nghị</th><th>Đơn vị</th><th>Ghi chú</th></tr></thead>
              <tbody>
                {request.lines.map((l) => (
                  <tr key={l.id}>
                    <td><strong>{l.material_code}</strong> <span className="md-page__muted">· {l.material_name}</span></td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{Number(l.quantity).toLocaleString("vi-VN")}</td>
                    <td>{l.uom || "—"}</td>
                    <td>{l.note || <span className="md-page__muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {request.status === "approved" && canCreate && (
            <div className="banner" style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span>Lập phiếu {request.request_type === "nhap" ? "nhập" : "xuất"} từ đề nghị này <span className="md-page__muted">(ghi sổ luôn)</span>:</span>
              {request.voucher_type_id ? (
                // Đã chốt loại phiếu lúc tạo đề nghị → KHÓA, không cho đổi.
                <span className="md-page__wh-badge" style={{ margin: 0 }}>
                  <strong>{request.voucher_type_name ?? vtypeOpts.find((t) => t.id === request.voucher_type_id)?.name ?? `#${request.voucher_type_id}`}</strong>
                </span>
              ) : (
                <select className="input" style={{ width: 240 }} value={vtypeId ?? ""} onChange={(e) => setVtypeId(e.target.value ? Number(e.target.value) : null)}>
                  {vtypeOpts.length === 0 ? <option value="">(Chưa có loại phiếu phù hợp)</option>
                    : vtypeOpts.map((t) => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}
                </select>
              )}
              <Button variant="primary" loading={busy} disabled={!vtypeId}
                onClick={() => vtypeId && act(() => api.kho.fulfillRequest(token!, request.id, vtypeId), true)}>
                Lập &amp; ghi sổ phiếu
              </Button>
            </div>
          )}

          {rejecting && (
            <div className="banner banner--warn" style={{ marginTop: 12 }}>
              <label className="field" style={{ width: "100%" }}>
                <span className="field__label">Lý do từ chối</span>
                <input className="input" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} autoFocus />
              </label>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <Button variant="ghost" onClick={() => setRejecting(false)}>Bỏ</Button>
                <Button variant="primary" loading={busy} onClick={() => act(() => api.kho.rejectRequest(token!, request.id, rejectReason))}>Xác nhận từ chối</Button>
              </div>
            </div>
          )}

          {error && <div className="banner banner--error" role="alert" style={{ marginTop: 10 }}>{error}</div>}
        </div>

        <div className="md-page__dialog-actions" style={{ flexWrap: "wrap" }}>
          <Button variant="ghost" onClick={printRequest}>In phiếu</Button>
          <div className="md-page__toolbar-spacer" />
          {request.status === "draft" && (
            <>
              <Button variant="ghost" onClick={onEdit}>Sửa</Button>
              <Button variant="ghost" loading={busy} onClick={() => setConfirmCancel(true)}>Hủy</Button>
              <Button variant="primary" loading={busy} onClick={() => act(() => api.kho.submitRequest(token!, request.id))}>Gửi duyệt</Button>
            </>
          )}
          {request.status === "pending" && (
            <>
              <Button variant="ghost" loading={busy} onClick={() => setConfirmCancel(true)}>Hủy</Button>
              {canApprove && !rejecting && (
                <>
                  <Button variant="ghost" onClick={() => setRejecting(true)}>Từ chối</Button>
                  <Button variant="primary" loading={busy} onClick={() => act(() => api.kho.approveRequest(token!, request.id))}>Duyệt</Button>
                </>
              )}
            </>
          )}
          {request.status === "approved" && (
            <Button variant="ghost" loading={busy} onClick={() => setConfirmCancel(true)}>Hủy đề nghị</Button>
          )}
        </div>
      </div>
    </div>
    <ConfirmDialog
      open={confirmCancel}
      danger
      title="Hủy đề nghị?"
      message={`Hủy đề nghị ${request.code}? Đề nghị sẽ chuyển sang "Đã hủy" và không dùng để lập phiếu được nữa.`}
      confirmLabel="Xác nhận hủy"
      cancelLabel="Không"
      busy={busy}
      error={error}
      onConfirm={() => act(() => api.kho.cancelRequest(token!, request.id))}
      onCancel={() => { if (!busy) { setConfirmCancel(false); setError(null); } }}
    />
    </>
  );
}
