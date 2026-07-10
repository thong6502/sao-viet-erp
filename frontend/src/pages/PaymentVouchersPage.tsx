import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type PaymentVoucherRow,
  type PaymentVoucherStatus,
  type PurchaseRequestRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { PaymentVoucherDialog } from "./PaymentVoucherDialog";
import "./accounting.css";
import "./purchase.css";


const PAGE_SIZE = 20;

const STATUS_META: Record<PaymentVoucherStatus, { label: string; tone: string }> = {
  waiting_payment: { label: "Chờ chi", tone: "waiting" },
  paid: { label: "Đã chi", tone: "paid" },
  cancelled: { label: "Đã hủy", tone: "cancelled" },
};

const STAGE_LABELS = {
  advance: "Tạm ứng / đặt cọc",
  partial: "Thanh toán một phần",
  final: "Thanh toán cuối",
  other: "Khác",
} as const;


function money(value: number): string {
  return `${Math.round(value).toLocaleString("vi-VN")} đ`;
}


function originalMoney(value: number, currency: string): string {
  return currency === "VND"
    ? money(value)
    : `${Math.round(value).toLocaleString("vi-VN")} ${currency}`;
}


function dateText(value?: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN").format(new Date(value));
}


function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function readTriple(value: number, full: boolean): string {
  const names = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"];
  const hundred = Math.floor(value / 100);
  const ten = Math.floor((value % 100) / 10);
  const unit = value % 10;
  const parts: string[] = [];
  if (hundred > 0 || full) parts.push(`${names[hundred]} trăm`);
  if (ten > 1) {
    parts.push(`${names[ten]} mươi`);
    if (unit === 1) parts.push("mốt");
    else if (unit === 4) parts.push("tư");
    else if (unit === 5) parts.push("lăm");
    else if (unit > 0) parts.push(names[unit]);
  } else if (ten === 1) {
    parts.push("mười");
    if (unit === 5) parts.push("lăm");
    else if (unit > 0) parts.push(names[unit]);
  } else if (unit > 0) {
    if (hundred > 0 || full) parts.push("lẻ");
    parts.push(names[unit]);
  }
  return parts.join(" ");
}


function amountInWords(amount: number): string {
  let value = Math.max(0, Math.round(amount));
  if (value === 0) return "Không đồng";
  const scales = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"];
  const groups: number[] = [];
  while (value > 0) {
    groups.push(value % 1000);
    value = Math.floor(value / 1000);
  }
  const parts: string[] = [];
  for (let i = groups.length - 1; i >= 0; i -= 1) {
    if (groups[i] === 0) continue;
    const words = readTriple(groups[i], i < groups.length - 1 && groups[i] < 100);
    parts.push(`${words}${scales[i] ? ` ${scales[i]}` : ""}`);
  }
  const result = `${parts.join(" ")} đồng`;
  return result.charAt(0).toUpperCase() + result.slice(1);
}


function printVoucher(row: PaymentVoucherRow): boolean {
  const win = window.open("", "_blank", "width=980,height=760");
  if (!win) return false;
  const isBank = row.voucher_type === "bank_transfer";
  const title = isBank ? "ỦY NHIỆM CHI" : "PHIẾU CHI";
  const accountBlock = isBank
    ? `<section class="accounts">
        <div><h3>Tài khoản trích nợ</h3><p><b>${escapeHtml(row.company_account_holder)}</b></p><p>${escapeHtml(row.company_account_number)}</p><p>${escapeHtml(row.company_bank_name)} · ${escapeHtml(row.company_bank_branch)}</p></div>
        <div><h3>Tài khoản thụ hưởng</h3><p><b>${escapeHtml(row.beneficiary_account_holder)}</b></p><p>${escapeHtml(row.beneficiary_account_number)}</p><p>${escapeHtml(row.beneficiary_bank_name)} · ${escapeHtml(row.beneficiary_bank_branch)}</p></div>
      </section>`
    : `<section class="accounts"><div><h3>Người nhận tiền</h3><p><b>${escapeHtml(row.cash_recipient_name)}</b></p><p>${escapeHtml(row.cash_recipient_address || "—")}</p><p>Giấy tờ: ${escapeHtml(row.cash_recipient_identity || "—")}</p></div></section>`;
  win.document.write(`<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>${title} ${escapeHtml(row.code)}</title><style>
    @page{size:A4;margin:16mm}*{box-sizing:border-box}body{font:13px Arial,sans-serif;color:#171713;margin:0}header{display:flex;justify-content:space-between;border-bottom:2px solid #171713;padding-bottom:12px}.brand{font-weight:700}.muted{color:#6f6c64}h1{text-align:center;font-size:24px;margin:24px 0 5px}h2{text-align:center;font:700 14px monospace;margin:0 0 22px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 26px}.label{display:block;font-size:10px;text-transform:uppercase;color:#77736a;font-weight:700;margin-bottom:4px}.purpose{margin:18px 0;padding:12px;border:1px solid #cfcac0}.amount{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}.amount div{padding:14px;background:#f3f1eb}.amount strong{display:block;font-size:20px;margin-top:5px}.words{padding:12px;border:1px solid #cfcac0;margin-bottom:16px}.accounts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}.accounts>div{border:1px solid #cfcac0;padding:12px}.accounts h3{font-size:12px;text-transform:uppercase;margin:0 0 10px}.accounts p{margin:5px 0}.refs{margin-top:18px;border-top:1px solid #cfcac0;padding-top:12px}.status{font-weight:700;text-transform:uppercase}@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  </style></head><body>
    <header><div><div class="brand">Sao Việt Nhật ERP</div><div class="muted">Chứng từ từ phân hệ Kế toán</div></div><div><div>Ngày in: ${escapeHtml(dateText(new Date().toISOString()))}</div><div class="status">${escapeHtml(STATUS_META[row.status].label)}</div></div></header>
    <h1>${title}</h1><h2>${escapeHtml(row.code)}</h2>
    <section class="grid"><div><span class="label">Ngày chứng từ</span>${escapeHtml(dateText(row.voucher_date))}</div><div><span class="label">Đợt thanh toán</span>${escapeHtml(STAGE_LABELS[row.payment_stage])}</div><div><span class="label">Nhà cung cấp</span>${escapeHtml(row.supplier_name)}</div><div><span class="label">Mã số thuế</span>${escapeHtml(row.supplier_tax_code || "—")}</div><div><span class="label">PMH nguồn</span>${escapeHtml(row.purchase_request_code)}</div><div><span class="label">YCMH nguồn</span>${escapeHtml(row.source_request_codes.join(", ") || "—")}</div></section>
    <section class="purpose"><span class="label">Nội dung chi</span><b>${escapeHtml(row.content)}</b></section>
    <section class="amount"><div><span class="label">Số tiền nguyên tệ</span><strong>${escapeHtml(originalMoney(row.amount, row.currency))}</strong></div><div><span class="label">Quy đổi VND / tỷ giá</span><strong>${escapeHtml(money(row.amount_vnd))} · ${escapeHtml(row.exchange_rate)}</strong></div></section>
    <section class="words"><span class="label">Số tiền quy đổi bằng chữ</span>${escapeHtml(amountInWords(row.amount_vnd))}</section>
    ${accountBlock}
    <section class="refs"><span class="label">Chứng từ tham chiếu</span>Hóa đơn: ${escapeHtml(row.invoice_number || "—")} · Hợp đồng: ${escapeHtml(row.contract_number || "—")} · Mã giao dịch: ${escapeHtml(row.bank_reference || "—")}</section>
  </body></html>`);
  win.document.close();
  win.focus();
  window.setTimeout(() => win.print(), 250);
  return true;
}


export function PaymentVouchersPage() {
  const { token } = useAuth();
  const can = useCan();
  const canApprove = can("ke_toan", "approve");
  const canMarkPaid = can("ke_toan", "manage_status");
  const canCancel = can("ke_toan", "cancel");
  const canExport = can("ke_toan", "export");
  const [rows, setRows] = useState<PaymentVoucherRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editState, setEditState] = useState<null | { voucher: PaymentVoucherRow; purchase: PurchaseRequestRow }>(null);
  const [marking, setMarking] = useState<PaymentVoucherRow | null>(null);
  const [bankReference, setBankReference] = useState("");
  const [cancelling, setCancelling] = useState<PaymentVoucherRow | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.accounting
      .vouchers(token, {
        q: q.trim() || undefined,
        status: statusFilter === "all" ? null : statusFilter,
        voucher_type: typeFilter === "all" ? null : typeFilter,
        sort: "-created_at",
        page,
        size: PAGE_SIZE,
      })
      .then((response) => {
        setRows(response.items);
        setTotal(response.total);
        setSelectedId((current) =>
          current != null && response.items.some((row) => row.id === current)
            ? current
            : response.items[0]?.id ?? null,
        );
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được Phiếu chi/UNC."))
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, typeFilter, page]);

  useEffect(() => { load(); }, [load]);

  const selected = useMemo(() => rows.find((row) => row.id === selectedId) ?? rows[0] ?? null, [rows, selectedId]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function openEdit(row: PaymentVoucherRow) {
    if (!token) return;
    setBusy(true);
    try {
      const purchase = await api.purchaseRequests.get(token, row.purchase_request_id);
      setEditState({ voucher: row, purchase });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được PMH nguồn.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPaid() {
    if (!token || !marking) return;
    if (marking.voucher_type === "bank_transfer" && !bankReference.trim()) {
      setError("UNC phải có mã giao dịch hoặc số báo nợ.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.markVoucherPaid(token, marking.id, bankReference.trim() || null);
      setMarking(null);
      setBankReference("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không xác nhận được chứng từ.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmCancel() {
    if (!token || !cancelling) return;
    if (!cancelReason.trim()) {
      setError("Vui lòng nhập lý do hủy.");
      return;
    }
    setBusy(true);
    try {
      await api.accounting.cancelVoucher(token, cancelling.id, cancelReason.trim());
      setCancelling(null);
      setCancelReason("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không hủy được chứng từ.");
    } finally {
      setBusy(false);
    }
  }

  function startPrint(row: PaymentVoucherRow) {
    if (!printVoucher(row)) setError("Trình duyệt đang chặn cửa sổ in. Vui lòng cho phép pop-up rồi thử lại.");
  }

  function actions(row: PaymentVoucherRow) {
    return (
      <div className="acct-actions">
        {canExport && <Button variant="ghost" onClick={() => startPrint(row)}>In phiếu</Button>}
        {canApprove && row.status === "waiting_payment" && <Button variant="ghost" onClick={() => openEdit(row)} disabled={busy}>Sửa</Button>}
        {canMarkPaid && row.status === "waiting_payment" && <Button variant="accent" onClick={() => { setMarking(row); setBankReference(""); }}>Xác nhận đã chi</Button>}
        {canCancel && row.status === "waiting_payment" && <Button variant="danger" onClick={() => { setCancelling(row); setCancelReason(""); }}>Hủy</Button>}
      </div>
    );
  }

  return (
    <main className="md-page">
      <header className="md-page__head"><p className="eyebrow">Kế toán</p><h1 className="md-page__title">Phiếu chi / UNC</h1><p className="md-page__sub">Theo dõi chứng từ chờ chi, đã chi và truy ngược về PMH cùng YCMH nguồn.</p></header>
      {error && <div className="banner banner--error" role="alert">{error}</div>}
      <section className="acct-toolbar">
        <form className="md-page__search" onSubmit={(event) => { event.preventDefault(); setPage(1); load(); }}><input className="input" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Tìm PC, UNC, PMH, YCMH..." /><Button type="submit" variant="ghost">Tìm</Button></form>
        <div className="acct-toolbar__filters">
          <select className="input" value={typeFilter} onChange={(event) => { setTypeFilter(event.target.value); setPage(1); }}><option value="all">Tất cả loại</option><option value="cash">Phiếu chi</option><option value="bank_transfer">Ủy nhiệm chi</option></select>
          <select className="input" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}><option value="all">Tất cả trạng thái</option>{Object.entries(STATUS_META).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}</select>
        </div>
      </section>
      <div className="acct-master-detail">
        <section className="card md-page__tablewrap acct-list">
          <table className="md-page__table"><thead><tr><th>Mã chứng từ</th><th>Loại</th><th>PMH nguồn</th><th>Nhà cung cấp</th><th>Số tiền</th><th>Trạng thái</th></tr></thead><tbody>
            {loading && <tr><td colSpan={6}>Đang tải...</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={6}>Chưa có chứng từ phù hợp.</td></tr>}
            {!loading && rows.map((row) => <tr key={row.id} className={row.id === selected?.id ? "purchase__row--selected" : ""} onClick={() => setSelectedId(row.id)}><td><strong>{row.code}</strong><div className="purchase__source-codes">{row.source_request_codes.join(", ")}</div></td><td>{row.voucher_type === "cash" ? "Phiếu chi" : "UNC"}</td><td>{row.purchase_request_code}</td><td>{row.supplier_name}</td><td><strong>{money(row.amount_vnd)}</strong>{row.currency !== "VND" && <div className="purchase__source-codes">{originalMoney(row.amount, row.currency)}</div>}</td><td><span className={`acct-voucher-status acct-voucher-status--${STATUS_META[row.status].tone}`}>{STATUS_META[row.status].label}</span></td></tr>)}
          </tbody></table>
          <div className="md-page__pager"><span>{total} chứng từ</span><div><Button variant="ghost" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Trước</Button><span>{page}/{totalPages}</span><Button variant="ghost" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Sau</Button></div></div>
        </section>
        <aside className="purchase__detail">
          {!selected ? <div className="purchase__empty-detail">Chọn một chứng từ để xem chi tiết.</div> : <>
            <div className="purchase__detail-head"><div><p className="eyebrow">{selected.voucher_type === "cash" ? "Phiếu chi" : "Ủy nhiệm chi"}</p><h2>{selected.code}</h2></div><span className={`acct-voucher-status acct-voucher-status--${STATUS_META[selected.status].tone}`}>{STATUS_META[selected.status].label}</span></div>
            <dl className="purchase__facts"><div><dt>PMH nguồn</dt><dd>{selected.purchase_request_code}</dd></div><div><dt>YCMH nguồn</dt><dd>{selected.source_request_codes.join(", ") || "—"}</dd></div><div><dt>Nhà cung cấp</dt><dd>{selected.supplier_name}</dd></div><div><dt>Ngày chứng từ</dt><dd>{dateText(selected.voucher_date)}</dd></div><div><dt>Đợt thanh toán</dt><dd>{STAGE_LABELS[selected.payment_stage]}</dd></div><div><dt>Người lập</dt><dd>{selected.created_by_name || "—"}</dd></div></dl>
            <div className="acct-purpose"><span>Nội dung chi</span><strong>{selected.content}</strong></div>
            <div className="acct-voucher-amount"><span>Số tiền quy đổi</span><strong>{money(selected.amount_vnd)}</strong><small>{selected.currency !== "VND" ? `${originalMoney(selected.amount, selected.currency)} · tỷ giá ${selected.exchange_rate}` : amountInWords(selected.amount_vnd)}</small></div>
            {selected.voucher_type === "bank_transfer" ? <div className="acct-account-pair"><div><span>Trích nợ</span><strong>{selected.company_account_holder}</strong><small>{selected.company_account_number} · {selected.company_bank_name}</small></div><div><span>Thụ hưởng</span><strong>{selected.beneficiary_account_holder}</strong><small>{selected.beneficiary_account_number} · {selected.beneficiary_bank_name}</small></div></div> : <div className="acct-account-pair"><div><span>Người nhận</span><strong>{selected.cash_recipient_name}</strong><small>{selected.cash_recipient_address || "—"}</small></div></div>}
            {selected.bank_reference && <div className="purchase__note">Mã giao dịch: <strong>{selected.bank_reference}</strong></div>}
            {selected.cancel_reason && <div className="banner banner--error">Lý do hủy: {selected.cancel_reason}</div>}
            {actions(selected)}
          </>}
        </aside>
      </div>

      {editState && <PaymentVoucherDialog purchase={editState.purchase} voucher={editState.voucher} onClose={() => setEditState(null)} onSaved={() => { setEditState(null); load(); }} />}
      {marking && <div className="acct-modal" role="dialog" aria-modal="true"><div className="acct-modal__box"><header className="acct-modal__head"><h2>Xác nhận đã chi {marking.code}</h2><button type="button" className="acct-modal__x" onClick={() => setMarking(null)}>×</button></header><div className="acct-modal__body"><p>Số tiền: <strong>{money(marking.amount_vnd)}</strong></p>{marking.voucher_type === "bank_transfer" && <label className="acct-field"><span>Mã giao dịch / Số báo nợ <b>*</b></span><input autoFocus className="input" value={bankReference} onChange={(event) => setBankReference(event.target.value)} /></label>}</div><footer className="acct-modal__foot"><Button variant="ghost" onClick={() => setMarking(null)}>Hủy</Button><Button variant="accent" loading={busy} onClick={confirmPaid}>Xác nhận đã chi</Button></footer></div></div>}
      {cancelling && <div className="acct-modal" role="dialog" aria-modal="true"><div className="acct-modal__box"><header className="acct-modal__head"><h2>Hủy {cancelling.code}</h2><button type="button" className="acct-modal__x" onClick={() => setCancelling(null)}>×</button></header><div className="acct-modal__body"><label className="acct-field"><span>Lý do hủy <b>*</b></span><textarea autoFocus className="input acct-textarea" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} /></label></div><footer className="acct-modal__foot"><Button variant="ghost" onClick={() => setCancelling(null)}>Đóng</Button><Button variant="danger" loading={busy} onClick={confirmCancel}>Hủy chứng từ</Button></footer></div></div>}
    </main>
  );
}
