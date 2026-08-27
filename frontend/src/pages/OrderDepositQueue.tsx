// B3 — Cọc đơn hàng trong module Phiếu thu (spec luồng Đơn→Cọc→SX).
// Kế toán (quyền `don_hang_ban:record_deposit`) thấy hàng chờ ghi cọc + LẬP phiếu thu cọc NGAY tại đây.
// Real-time: chốt đơn → SSE `order_deposit_needed` → popup + hàng chờ nhảy; đủ cọc → đơn rời hàng chờ.
// Component tự chứa, MOUNT có điều kiện quyền ở PaymentReceiptsPage → "chỉ ai có quyền mới nghe/thấy".
// 26/08/2026 — vỏ hộp Lập phiếu thu cọc chuyển từ `acct-modal` nền trắng giữa màn sang KHUÔN
// DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner` + `purchase__drawer-footer`), chủ
// chốt: "sao mỗi nơi một màu". Đây là FORM NHẬP SỐ TIỀN CỌC nên đóng AN TOÀN: scrim KHÔNG bắt
// click, KHÔNG Esc-to-close — chỉ ✕ và nút Hủy. Không bọc `<form>` vì `submit()` là handler của
// nút (không nhận FormEvent) — bọc lại là phải sửa chữ ký, mà mọi phép tính/validate tiền cọc
// phải giữ NGUYÊN. Chỉ đổi vỏ.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  connectQuoteEvents,
  type CompanyBankAccountRow,
  type OrderRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { money } from "../utils/format";
import { ToastStack, useToasts } from "./LsxToast";

const METHODS: Record<string, string> = { cash: "Tiền mặt", bank_transfer: "Chuyển khoản" };

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function OrderDepositQueue() {
  const { token } = useAuth();
  const { toasts, ok: toastOk, dismiss } = useToasts();
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [depOrder, setDepOrder] = useState<OrderRow | null>(null);

  // Hàng chờ ghi cọc = đơn ĐÃ CHỐT có cọc cần thu mà chưa đủ (cọc là bước SAU chốt).
  const load = useCallback(() => {
    if (!token) return;
    api.orders
      .list(token, { status: "ordered", size: 200 })
      .then((r) => setOrders(r.items.filter((o) => o.deposit_required > 0 && !o.deposit_ok)))
      .catch(() => setOrders([]))
      .finally(() => setLoading(false));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  // Real-time: chốt → 'order_deposit_needed' (popup); đủ cọc → 'order_deposit_ok' (rời hàng chờ).
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    if (!token) return;
    return connectQuoteEvents(token, (e) => {
      if (e.type === "order_deposit_needed") {
        loadRef.current();
        toastOk(`🔔 Đơn ${e.code ?? ""} vừa chốt — chờ ghi cọc ${money(e.amount)}`);
      } else if (e.type === "order_deposit_ok") {
        loadRef.current();
      }
    });
  }, [token, toastOk]);

  if (loading && orders.length === 0) return null;

  return (
    <section className="odq">
      <div className="odq__head">
        <div className="odq__title">
          <span className="odq__dot" /> Cọc đơn hàng — chờ ghi
          <span className="odq__count">{orders.length}</span>
        </div>
        <span className="odq__hint">Đơn đã chốt, chưa đủ cọc — thu đủ để Sale chuyển xuống sản xuất.</span>
      </div>
      {orders.length === 0 ? (
        <p className="odq__empty">Không có đơn nào chờ ghi cọc.</p>
      ) : (
        <ul className="odq__list">
          {orders.map((o) => {
            const remaining = Math.max(0, o.deposit_required - o.deposit_received);
            return (
              <li key={o.id} className="odq__row">
                <div className="odq__lead">
                  <span className="odq__code">{o.order_no}</span>
                  {o.is_rush ? <span className="odq__rush">GẤP</span> : null}
                  <span className="odq__cust">{o.customer_name ?? "—"}</span>
                </div>
                <div className="odq__money">
                  <span>
                    Cần <b>{money(o.deposit_required)}</b>
                  </span>
                  <span className="odq__got">đã {money(o.deposit_received)}</span>
                  <span className="odq__lack">thiếu {money(remaining)}</span>
                </div>
                <button type="button" className="btn btn--primary odq__btn" onClick={() => setDepOrder(o)}>
                  Lập phiếu thu cọc
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {depOrder && (
        <OrderDepositDialog
          order={depOrder}
          onClose={() => setDepOrder(null)}
          onSaved={(msg) => {
            setDepOrder(null);
            load();
            toastOk(msg);
          }}
        />
      )}
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </section>
  );
}

function OrderDepositDialog({
  order,
  onClose,
  onSaved,
}: {
  order: OrderRow;
  onClose: () => void;
  onSaved: (msg: string) => void;
}) {
  const { token } = useAuth();
  const remaining = Math.max(0, order.deposit_required - order.deposit_received);
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState(String(remaining));
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // TK công ty NHẬN tiền — chỉ hỏi khi chuyển khoản. Thiếu ô này thì phiếu thu 01-TT in ra không
  // nói được tiền về tài khoản nào, mà đó chính là thứ đối chiếu sao kê cần. Cọc đơn bán chỉ nhận
  // VND (`create_order_receipt` chặn TK ngoại tệ) nên lọc luôn ở đây, đừng đưa lựa chọn sẽ bị từ chối.
  const isBank = method === "bank_transfer";
  const [bankAccountId, setBankAccountId] = useState<number | null>(null);
  const [accounts, setAccounts] = useState<CompanyBankAccountRow[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  useEffect(() => {
    if (!token) return;
    setLoadingAccounts(true);
    api.accounting
      .companyAccounts(token, true, "receive")
      .then((rows) => setAccounts(rows.filter((r) => r.currency === "VND")))
      .catch(() => setAccounts([]))
      .finally(() => setLoadingAccounts(false));
  }, [token]);

  async function submit() {
    if (!token || saving) return;
    if (!(Number(amount) > 0)) {
      setErr("Số tiền thu phải lớn hơn 0.");
      return;
    }
    // Bắt chọn TK khi CÓ tài khoản để chọn. Công ty chưa khai TK nào thì vẫn cho lập (server để
    // trường này tùy chọn) — chặn cứng ở đây là khoá luôn việc ghi cọc của một hồ sơ chưa khai TK.
    if (isBank && accounts.length > 0 && bankAccountId == null) {
      setErr("Chuyển khoản thì phải chọn tài khoản công ty nhận tiền.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const d = await api.orders.addDepositReceipt(token, order.id, {
        receipt_method: method,
        amount: Number(amount),
        receipt_date: date || null,
        note: note || null,
        company_bank_account_id: isBank ? bankAccountId : null,
      });
      onSaved(
        d.deposit_ok
          ? `✓ Đủ cọc đơn ${order.order_no} — đã báo Sale chuyển sản xuất`
          : `Đã ghi cọc đơn ${order.order_no}`,
      );
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String((e as Error)?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rc-drawer__scrim" role="presentation">
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="odq-dialog-title"
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">Lập phiếu thu cọc</span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code" id="odq-dialog-title">
                  {order.order_no}
                </h2>
              </div>
            </div>
            <button type="button" className="purchase__hero-x" onClick={onClose} aria-label="Đóng">
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            <span>{order.customer_name ?? "—"}</span>
            <span className="purchase__hero-dot">•</span>
            <span>Còn thiếu {money(remaining)}</span>
          </div>
        </div>
        <div className="rc-drawer__body">
          {err && (
            <div className="banner banner--error" role="alert">
              {err}
            </div>
          )}
          <div className="acct-summary-strip">
            <div>
              <span>Cần thu{order.deposit_pct != null ? ` (${order.deposit_pct}%)` : ""}</span>
              <strong>{money(order.deposit_required)}</strong>
            </div>
            <div>
              <span>Đã thu</span>
              <strong>{money(order.deposit_received)}</strong>
            </div>
            <div>
              <span>Còn thiếu</span>
              <strong>{money(remaining)}</strong>
            </div>
          </div>
          <label className="acct-field">
            <span>Hình thức thu</span>
            <select className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
              {Object.entries(METHODS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          {isBank && (
            <label className="acct-field">
              <span>
                Tài khoản công ty nhận tiền <b>*</b>
              </span>
              <select
                className="input"
                value={bankAccountId ?? ""}
                onChange={(e) => setBankAccountId(e.target.value ? Number(e.target.value) : null)}
                disabled={loadingAccounts}
              >
                <option value="">Chọn tài khoản công ty</option>
                {accounts.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.bank_name} · {row.account_number} · {row.currency}
                  </option>
                ))}
              </select>
              {!loadingAccounts && accounts.length === 0 && (
                <small>
                  Chưa có tài khoản công ty VND nào bật "dùng để thu". Khai báo trong mục Tài khoản
                  ngân hàng thì phiếu thu mới ghi được tiền về đâu.
                </small>
              )}
            </label>
          )}
          <div className="acct-form-grid acct-form-grid--2">
            <label className="acct-field">
              <span>
                Số tiền thực thu <b>*</b>
              </span>
              <input
                className="input acct-money-input"
                type="number"
                min="1"
                step="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <label className="acct-field">
              <span>Ngày thu</span>
              <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
          </div>
          <label className="acct-field">
            <span>Ghi chú</span>
            <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="tùy chọn" />
          </label>
          <p style={{ margin: 0, fontSize: 12, color: "var(--ash, #8a8578)" }}>
            Bấm = lập Phiếu thu THẬT (01-TT) gắn đơn này (Nợ 111/112 · Có 131). Ngày mặc định hôm nay: {fmtDate(new Date().toISOString())}.
          </p>
        </div>
        <div className="purchase__drawer-footer">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>
            Hủy
          </button>
          <button type="button" className="btn btn--primary" onClick={submit} disabled={saving}>
            {saving ? "Đang lập…" : "Lập phiếu thu cọc"}
          </button>
        </div>
      </aside>
    </div>
  );
}
