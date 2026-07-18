// MASTER của "Kế hoạch sản xuất" — danh sách LỆNH SẢN XUẤT. Bấm dòng → detail lệnh.
// API record-only (máy chỉ ghi): list trả ID mềm (đơn/ấn phẩm/máy) → resolve tên qua danh mục
// (orders · máy) như PTG resolve giấy/máy. Lọc trạng thái + search client-side (bám PhieuTinhGiaListView).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  connectQuoteEvents,
  type HangChoDon,
  type LenhSXRow,
  type OrderRow,
} from "../api/client";
import { mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { StatusTabs } from "../components/StatusTabs";
import { ToastStack, useToasts } from "./LsxToast";
import "./lenh-san-xuat.css";

// Trạng thái lệnh (suy ra ở BE, record-only) → nhãn + biến thể badge (màu app).
const LENH_META: Record<string, { label: string; variant: string }> = {
  nhap: { label: "Nháp", variant: "neutral" },
  dang_chay: { label: "Đang chạy", variant: "run" },
  xong: { label: "Xong", variant: "done" },
  huy: { label: "Hủy", variant: "danger" },
};
function lenhMeta(tt: string): { label: string; variant: string } {
  return LENH_META[tt] ?? { label: tt || "—", variant: "neutral" };
}

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

// Đếm ngược hạn giao → nhãn + mức khẩn (đổi màu). Máy CHỈ trình bày theo data, không phán.
function hanGiao(v: string | null | undefined): { label: string; level: "over" | "soon" | "ok" } | null {
  if (!v) return null;
  const d = new Date(v);
  if (isNaN(d.getTime())) return null;
  const today = new Date();
  const day = 86400000;
  const diff = Math.round(
    (Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) -
      Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / day,
  );
  if (diff < 0) return { label: `Quá hạn ${-diff} ngày`, level: "over" };
  if (diff === 0) return { label: "Hạn hôm nay", level: "over" };
  if (diff <= 3) return { label: `Còn ${diff} ngày`, level: "soon" };
  return { label: `Còn ${diff} ngày`, level: "ok" };
}

const anPhamLabel = (id: number | null): string =>
  id ? `Ấn phẩm #${id}` : "— chưa gắn ấn phẩm";

export function LenhSanXuatListView({
  onOpen,
  onGhep,
}: {
  onOpen: (id: number) => void;
  onGhep: () => void;
}) {
  const { token } = useAuth();
  const { toasts, ok: toastOk, err: toastErr, dismiss: toastDismiss } = useToasts();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<LenhSXRow[]>([]);
  const [orders, setOrders] = useState<Map<number, OrderRow>>(new Map());
  const [mays, setMays] = useState<Map<number, Row>>(new Map());
  const [hangCho, setHangCho] = useState<HangChoDon[]>([]);
  const [bungBusy, setBungBusy] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("cho_kh");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim().toLowerCase()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.lenhSanXuat.list(token, {}),
      api.orders.list(token, { size: 200 }).catch(() => ({ items: [] as OrderRow[] })),
      mayThietBi.list(token).catch(() => ({ items: [] as Row[] })),
      api.lenhSanXuat.hangCho(token).catch(() => [] as HangChoDon[]),
    ])
      .then(([lenh, ord, may, hc]) => {
        setItems(lenh.items);
        setOrders(new Map(ord.items.map((o) => [o.id, o])));
        setMays(new Map(may.items.map((m) => [m.id, m])));
        setHangCho(hc);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được danh sách lệnh sản xuất."),
      )
      .finally(() => setLoading(false));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  // Real-time handoff: đơn chốt 'bắn xuống' hàng chờ; Sale đổi gấp/lưu ý sau chốt → badge nhảy + toast.
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    if (!token) return;
    return connectQuoteEvents(token, (e) => {
      if (e.type === "order_ordered") {
        loadRef.current();
        toastOk("🔔 Đơn mới chờ lên kế hoạch");
      } else if (e.type === "order_sx_hint_changed") {
        loadRef.current();
        toastOk(e.is_rush ? "⚡ Một đơn vừa chuyển GẤP" : "Cập nhật lưu ý sản xuất");
      }
    });
  }, [token, toastOk]);

  // Kế hoạch NHẬN đơn: bung (idempotent) → lệnh nháp; rời hàng chờ, nhảy sang tab Nháp.
  const doBung = useCallback(
    async (orderId: number, orderNo: string) => {
      if (!token || bungBusy != null) return;
      setBungBusy(orderId);
      try {
        const lenhs = await api.lenhSanXuat.bung(token, orderId);
        setHangCho((hc) => hc.filter((x) => x.order_id !== orderId));
        toastOk(`Đã lên kế hoạch ${orderNo} — ${lenhs.length} lệnh nháp`);
        setStatusFilter("nhap");
        load();
      } catch (e) {
        toastErr(e instanceof ApiError ? e.message : "Không lên kế hoạch được đơn này.");
      } finally {
        setBungBusy(null);
      }
    },
    [token, bungBusy, load, toastOk, toastErr],
  );

  const mayName = useCallback(
    (id: number | null): string | null => {
      if (id == null) return null;
      const m = mays.get(id);
      return m ? String(m.ten ?? m.ma ?? `#${id}`) : `Máy #${id}`;
    },
    [mays],
  );

  const filtered = useMemo(() => {
    let rows = items;
    if (statusFilter !== "all") rows = rows.filter((r) => r.trang_thai === statusFilter);
    if (debouncedQ) {
      rows = rows.filter((r) => {
        const o = orders.get(r.order_id);
        const hay = [
          maLenh(r.id),
          o?.order_no ?? "",
          o?.customer_name ?? "",
          mayName(r.may_id) ?? "",
          r.phieu_thanh_phan_id ? `ấn phẩm ${r.phieu_thanh_phan_id}` : "",
        ]
          .join(" ")
          .toLowerCase();
        return hay.includes(debouncedQ);
      });
    }
    // Đang chạy trước (việc cần theo), rồi nháp, xong, hủy; trong nhóm mới cập nhật lên đầu.
    const order: Record<string, number> = { dang_chay: 0, nhap: 1, xong: 2, huy: 3 };
    return [...rows].sort((a, b) => {
      const d = (order[a.trang_thai] ?? 9) - (order[b.trang_thai] ?? 9);
      if (d !== 0) return d;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }, [items, statusFilter, debouncedQ, orders, mayName]);

  const count = (tt: string) => items.filter((r) => r.trang_thai === tt).length;

  const hcFiltered = useMemo(() => {
    if (!debouncedQ) return hangCho;
    return hangCho.filter((h) =>
      [h.order_no, h.khach ?? "", h.an_pham.map((a) => a.description).join(" ")]
        .join(" ")
        .toLowerCase()
        .includes(debouncedQ),
    );
  }, [hangCho, debouncedQ]);

  return (
    <main className="lsx">
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <div className="lsx-eyebrow">
            <span className="sq" /> Sản xuất · Kế hoạch
          </div>
          <h1 className="lsx-head__title">Kế hoạch sản xuất</h1>
          <p className="lsx-head__sub">
            Lệnh sản xuất suy từ đơn đã chốt — theo dõi duyệt mẫu, ghép tờ in, sản lượng &amp; giao
            nhận giữa các tổ.
          </p>
        </div>
        <div className="lsx-head__actions">
          <button type="button" className="btn btn--primary" onClick={onGhep}>
            <PlusLayersIcon /> Ghép bài
          </button>
        </div>
      </header>

      <div className="lsx-toolbar">
        <div className="lsx-search">
          <SearchIcon />
          <input
            className="lsx-search__input"
            placeholder="Tìm mã lệnh, đơn hàng, khách, máy…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm lệnh sản xuất"
          />
        </div>
      </div>

      <div className="lsx-tabrow">
        <StatusTabs
          tabs={[
            { key: "cho_kh", label: "Chờ lên kế hoạch", count: hangCho.length },
            { key: "all", label: "Tất cả", count: items.length },
            { key: "dang_chay", label: "Đang chạy", count: count("dang_chay") },
            { key: "nhap", label: "Nháp", count: count("nhap") },
            { key: "xong", label: "Xong", count: count("xong") },
            { key: "huy", label: "Hủy", count: count("huy") },
          ]}
          active={statusFilter}
          onChange={setStatusFilter}
        />
      </div>

      {error ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-2)" }}>
          <span>{error}</span>
          <button
            type="button"
            className="btn btn--ghost"
            style={{ padding: "4px 12px", fontSize: "12px" }}
            onClick={load}
          >
            Tải lại
          </button>
        </div>
      ) : null}

      {statusFilter === "cho_kh" ? (
        loading ? (
          <div className="lsx-msg" style={{ padding: "var(--sp-6)" }}>Đang tải dữ liệu…</div>
        ) : hcFiltered.length === 0 ? (
          <div className="lsx-empty">
            <InboxIcon />
            <p className="lsx-empty__title">
              {debouncedQ ? "Không có đơn chờ phù hợp." : "Chưa có đơn nào chờ lên kế hoạch."}
            </p>
            <p className="lsx-empty__sub">
              Đơn bán vừa được chốt sẽ hiện ở đây (real-time) để kế hoạch bấm “Lên kế hoạch”.
            </p>
          </div>
        ) : (
          <ul className="lsx-hc">
            {hcFiltered.map((hc) => {
              const due = hanGiao(hc.delivery_committed_date);
              return (
                <li key={hc.order_id} className={`lsx-hc__card${hc.is_rush ? " is-rush" : ""}`}>
                  <div className="lsx-hc__top">
                    <div className="lsx-hc__idline">
                      <span className="lsx-code">{hc.order_no}</span>
                      {hc.is_rush ? (
                        <span className="lsx-badge lsx-badge--danger">
                          <span className="lsx-badge__d" /> GẤP
                        </span>
                      ) : null}
                    </div>
                    {due ? (
                      <span className={`lsx-due lsx-due--${due.level}`}>
                        <ClockIcon /> {due.label}
                      </span>
                    ) : null}
                  </div>
                  <div className="lsx-hc__cust">{hc.khach ?? "— khách chưa gán"}</div>
                  {hc.production_note ? (
                    <div className="lsx-hc__note">
                      <NoteIcon />
                      <span>{hc.production_note}</span>
                    </div>
                  ) : null}
                  <ul className="lsx-hc__aps">
                    {hc.an_pham.map((a, i) => (
                      <li key={i} className="lsx-hc__ap">
                        <span className="lsx-hc__apname">
                          {a.description || anPhamLabel(a.phieu_thanh_phan_id)}
                        </span>
                        <span className="lsx-hc__apqty mono">
                          {a.qty.toLocaleString("vi-VN")} {a.don_vi_tinh}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="lsx-hc__foot">
                    <span className="lsx-hc__apcount">
                      {hc.an_pham.length} ấn phẩm → {hc.an_pham.length} lệnh
                    </span>
                    <button
                      type="button"
                      className="btn btn--primary lsx-hc__btn"
                      disabled={bungBusy != null}
                      onClick={() => doBung(hc.order_id, hc.order_no)}
                    >
                      {bungBusy === hc.order_id ? (
                        "Đang lên kế hoạch…"
                      ) : (
                        <>
                          <ArrowDownIcon /> Lên kế hoạch
                        </>
                      )}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )
      ) : (
      <>
      <div className="lsx-tablewrap">
        <table className="lsx-table">
          <thead>
            <tr>
              <th>Lệnh · Ấn phẩm</th>
              <th>Đơn hàng · Khách</th>
              <th>Máy</th>
              <th>Duyệt mẫu</th>
              <th>Trạng thái</th>
              <th>Hạn giao</th>
              <th>Cập nhật</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="lsx-msg">
                  Đang tải dữ liệu…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 0 }}>
                  <div className="lsx-empty">
                    <EmptyIcon />
                    <p className="lsx-empty__title">
                      {debouncedQ || statusFilter !== "all"
                        ? "Không có lệnh phù hợp bộ lọc."
                        : "Chưa có lệnh sản xuất nào."}
                    </p>
                    <p className="lsx-empty__sub">
                      Đơn đã chốt hiện ở tab “Chờ lên kế hoạch” — bấm “Lên kế hoạch” để đề lệnh (mỗi
                      ấn phẩm = 1 lệnh).
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((r) => {
                const o = orders.get(r.order_id);
                const meta = lenhMeta(r.trang_thai);
                const my = mayName(r.may_id);
                return (
                  <tr
                    key={r.id}
                    className="lsx-row"
                    role="button"
                    tabIndex={0}
                    onClick={() => onOpen(r.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onOpen(r.id);
                      }
                    }}
                  >
                    <td>
                      <div className="lsx-cellstack">
                        <span className="lsx-code">{maLenh(r.id)}</span>
                        <span className="lsx-cellstack__sub mono">
                          {r.phieu_thanh_phan_id ? `Ấn phẩm #${r.phieu_thanh_phan_id}` : "— chưa gắn ấn phẩm"}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="lsx-cellstack">
                        <span className="lsx-cellstack__main">{o?.customer_name ?? "—"}</span>
                        <span className="lsx-cellstack__sub mono">{o?.order_no ?? `Đơn #${r.order_id}`}</span>
                      </div>
                    </td>
                    <td>
                      {my ? (
                        <span className="mono" style={{ fontSize: 12.5 }}>{my}</span>
                      ) : (
                        <span className="muted">— chưa gán</span>
                      )}
                    </td>
                    <td>
                      {r.mau_approved_at ? (
                        <span className="lsx-stampchip lsx-stampchip--on">
                          <SealIcon /> Đã duyệt
                        </span>
                      ) : (
                        <span className="lsx-stampchip lsx-stampchip--off">
                          <ClockIcon /> Chờ duyệt
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={`lsx-badge lsx-badge--${meta.variant}`}>
                        <span className="lsx-badge__d" />
                        {meta.label}
                      </span>
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: 12.5 }}>
                        {fmtDate(o?.delivery_committed_date)}
                      </span>
                      {o?.is_rush ? (
                        <span className="lsx-rush">
                          <ZapIcon /> Gấp
                        </span>
                      ) : null}
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: 12, color: "var(--ash)" }}>
                        {fmtDate(r.updated_at)}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && filtered.length > 0 ? (
        <p className="lsx-foot-note">
          {filtered.length} lệnh trong bộ lọc hiện tại · tổng {items.length} lệnh.
        </p>
      ) : null}
      </>
      )}

      <ToastStack toasts={toasts} onDismiss={toastDismiss} />
    </main>
  );
}

// ---------- Inline icons (Lucide-style, 1.75 stroke, currentColor) ----------
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-search__icon" aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);
const SealIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.6 5 5.4v5.2c0 4.3 3 7.6 7 8.8 4-1.2 7-4.5 7-8.8V5.4L12 2.6Z" />
    <path d="m9 11.6 2 2 4-4.2" />
  </svg>
);
const ClockIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </svg>
);
const ZapIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true">
    <path d="M13 2 4.5 13.2h6.2L10 22l8.5-11.2h-6.2Z" />
  </svg>
);
const EmptyIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-empty__icon" aria-hidden="true">
    <rect x="5" y="4.5" width="14" height="16.5" rx="2" />
    <rect x="8.75" y="2.5" width="6.5" height="3.8" rx="1.2" />
    <path d="M9 11h6M9 14.6h6M9 18.2h3.5" />
  </svg>
);
const PlusLayersIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 5-2.8" />
    <path d="M18 14v6M15 17h6" />
  </svg>
);
const NoteIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15.5 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L15.5 3Z" />
    <path d="M15 3v5h5M8.5 12.5h7M8.5 16h5" />
  </svg>
);
const ArrowDownIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 4.5v13M6.5 12 12 17.5 17.5 12" />
  </svg>
);
const InboxIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-empty__icon" aria-hidden="true">
    <path d="M4 13.5 6.5 6h11L20 13.5" />
    <path d="M4 13.5V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5.5" />
    <path d="M4 13.5h4l1.5 2.2h5L16 13.5h4" />
  </svg>
);
