// MASTER của "Tính giá" — danh sách phiếu tính giá (giá vốn). Bấm dòng → detail. Nút "+ Lập phiếu
// tính giá" tạo nháp rồi mở detail. StatusTabs lọc theo tab; search debounce. Bám pattern list nhà
// (RebuildCatalogPage): row hover, code mono badge, số liệu mono/tabular/vi-VN căn phải.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type PhieuTinhGiaListItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import "./tinh-gia.css";

const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";

function specLine(it: PhieuTinhGiaListItem): string {
  return [`${it.so_thanh_phan} thành phần`, it.kho_thanh_pham]
    .filter((x) => x != null && x !== "")
    .join(" · ");
}

export function PhieuTinhGiaListView({
  onOpen,
  onNew,
}: {
  onOpen: (id: number) => void;
  onNew: (id: number) => void;
}) {
  const { token } = useAuth();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<PhieuTinhGiaListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce ô tìm kiếm.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.phieuTinhGia
      .list(token, { q: debouncedQ })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách phiếu."))
      .finally(() => setLoading(false));
  }, [token, debouncedQ]);
  useEffect(() => {
    load();
  }, [load]);

  const create = useCallback(() => {
    if (!token) return;
    setCreating(true);
    setError(null);
    api.phieuTinhGia
      .create(token, {})
      .then((out) => onNew(out.id))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tạo được phiếu."))
      .finally(() => setCreating(false));
  }, [token, onNew]);

  return (
    <main className="tg-page">
      <header className="tg-head">
        <div className="tg-head__lead">
          <p className="eyebrow">Kinh doanh</p>
          <h1 className="tg-head__title">
            Tính giá thành <span className="tg-head__title-sub">· Phiếu tính giá</span>
          </h1>
          <p className="tg-head__sub">
            Công cụ nội bộ của KTV — tính giá vốn. Số liệu phục vụ lập báo giá cho khách.
            <span className="tg-head__meta">
              {" "}· {fmt(total)} phiếu
            </span>
          </p>
        </div>
        <div className="tg-head__actions">
          <Button variant="accent" onClick={create} loading={creating}>
            + Lập phiếu tính giá
          </Button>
        </div>
      </header>

      <div className="ptg-toolbar">
        <div className="ptg-search">
          <SearchIcon />
          <input
            className="ptg-search__input"
            placeholder="Tìm mã PTG, khách hàng, sản phẩm…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm phiếu tính giá"
          />
        </div>
        <button type="button" className="btn btn--secondary ptg-filter" disabled title="Sắp có">
          Lọc theo tiêu chí
        </button>
      </div>

      {error ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-4)" }}>
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

      <div className="ptg-tablewrap">
        <table className="ptg-table">
          <thead>
            <tr>
              <th>Mã PTG</th>
              <th>Sản phẩm</th>
              <th className="tg-num">SL</th>
              <th className="tg-num">Giá vốn/đơn</th>
              <th className="tg-num">Tổng giá vốn</th>
              <th>Ngày · KTV</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="ptg-msg">
                  Đang tải dữ liệu…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="ptg-empty-td">
                  <div className="ptg-empty">
                    <EmptyIcon />
                    <p className="ptg-empty__title">
                      {debouncedQ ? "Không tìm thấy phiếu phù hợp." : "Chưa có phiếu tính giá nào."}
                    </p>
                    {debouncedQ ? (
                      <Button variant="ghost" onClick={() => setQ("")}>
                        Xóa tìm kiếm
                      </Button>
                    ) : (
                      <Button variant="ghost" onClick={create} loading={creating}>
                        + Lập phiếu đầu tiên
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              items.map((it) => (
                <tr
                  key={it.id}
                  className="ptg-row"
                  role="button"
                  tabIndex={0}
                  onClick={() => onOpen(it.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onOpen(it.id);
                    }
                  }}
                >
                  <td className="tg-mono ptg-nowrap">
                    <span className="ptg-code">{it.ma}</span>
                  </td>
                  <td className="ptg-prod">
                    <span className="ptg-prod__name">{it.ten_san_pham || "—"}</span>
                    <span className="ptg-prod__spec">{specLine(it)}</span>
                  </td>
                  <td className="tg-num">{fmt(it.so_luong)}</td>
                  <td className="tg-num">{fmt(it.gia_von_don)} đ</td>
                  <td className="tg-num ptg-strong">{fmt(it.tong_gia_von)} đ</td>
                  <td className="ptg-when">
                    <span className="ptg-when__date">
                      {it.ngay ? new Date(it.ngay).toLocaleDateString("vi-VN") : "—"}
                    </span>
                    <span className="ptg-when__ktv">{it.ktv ?? "—"}</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && items.length > 0 ? (
        <p className="ptg-foot-note">
          {fmt(total)} phiếu trong bộ lọc hiện tại.
        </p>
      ) : null}
    </main>
  );
}

// ---------- Inline icons ----------
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="ptg-search__icon" aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

const EmptyIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="ptg-empty__icon" aria-hidden="true">
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M8 6h8M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h4" />
  </svg>
);
