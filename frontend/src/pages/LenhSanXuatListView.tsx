// MASTER của "Kế hoạch sản xuất" — danh sách LỆNH SẢN XUẤT. Bấm dòng → detail lệnh.
// API record-only (máy chỉ ghi): list trả ID mềm (đơn/ấn phẩm/máy) → resolve tên qua danh mục
// (orders · máy) như PTG resolve giấy/máy. Lọc trạng thái + search client-side (bám PhieuTinhGiaListView).
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, type LenhSXRow, type OrderRow } from "../api/client";
import { mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { StatusTabs } from "../components/StatusTabs";
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

export function LenhSanXuatListView({ onOpen }: { onOpen: (id: number) => void }) {
  const { token } = useAuth();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<LenhSXRow[]>([]);
  const [orders, setOrders] = useState<Map<number, OrderRow>>(new Map());
  const [mays, setMays] = useState<Map<number, Row>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");

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
    ])
      .then(([lenh, ord, may]) => {
        setItems(lenh.items);
        setOrders(new Map(ord.items.map((o) => [o.id, o])));
        setMays(new Map(may.items.map((m) => [m.id, m])));
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được danh sách lệnh sản xuất."),
      )
      .finally(() => setLoading(false));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

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
                      Lệnh sản xuất được đề tự động khi một đơn hàng bán được chốt (mỗi ấn phẩm = 1
                      lệnh).
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
