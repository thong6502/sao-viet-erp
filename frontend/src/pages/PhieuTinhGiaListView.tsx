// MASTER của "Tính giá" — danh sách phiếu tính giá (giá vốn). Bấm dòng → detail. Nút "+ Lập phiếu
// tính giá" tạo nháp rồi mở detail. StatusTabs lọc theo tab; search debounce. Bám pattern list nhà
// (RebuildCatalogPage): row hover, code mono badge, số liệu mono/tabular/vi-VN căn phải.
import { useCallback, useEffect, useState, useMemo } from "react";
import {
  api,
  ApiError,
  type PhieuTinhGiaListItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import "./tinh-gia.css";

const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";

function specLine(it: PhieuTinhGiaListItem): string {
  return [`${it.so_thanh_phan} thành phần`, it.kho_thanh_pham]
    .filter((x) => x != null && x !== "")
    .join(" · ");
}

function SortBtn({
  label,
  col,
  sort,
  onSort,
}: {
  label: string;
  col: string;
  sort: string;
  onSort: (s: string) => void;
}) {
  const active = sort === col || sort === `-${col}`;
  const desc = sort === `-${col}`;
  return (
    <button
      type="button"
      className={`ptg__sortbtn${active ? " is-active" : ""}`}
      onClick={() => onSort(desc ? col : active ? `-${col}` : col)}
    >
      {label}
      {active && <span aria-hidden="true">{desc ? " ↓" : " ↑"}</span>}
    </button>
  );
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
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState("all");
  const [sort, setSort] = useState("-ngay");

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

  // Filter and sort items client-side
  const filteredAndSortedItems = useMemo(() => {
    // 1. Filter by status tab
    let result = items;
    if (statusFilter === "calculated") {
      result = result.filter((it) => it.so_thanh_phan > 0);
    } else if (statusFilter === "draft") {
      result = result.filter((it) => it.so_thanh_phan === 0);
    }

    // 2. Sort client-side
    if (!sort) return result;
    const isDesc = sort.startsWith("-");
    const key = isDesc ? sort.substring(1) : sort;

    return [...result].sort((a, b) => {
      let valA = a[key as keyof PhieuTinhGiaListItem];
      let valB = b[key as keyof PhieuTinhGiaListItem];

      // Handle null/undefined values
      if (valA == null) return isDesc ? 1 : -1;
      if (valB == null) return isDesc ? -1 : 1;

      // Handle string columns
      if (typeof valA === "string" && typeof valB === "string") {
        return isDesc ? valB.localeCompare(valA) : valA.localeCompare(valB);
      }

      // Handle numeric columns
      if (typeof valA === "number" && typeof valB === "number") {
        return isDesc ? valB - valA : valA - valB;
      }

      return 0;
    });
  }, [items, statusFilter, sort]);

  // Tab counts based on currently loaded items
  const allCount = items.length;
  const calculatedCount = items.filter(it => it.so_thanh_phan > 0).length;
  const draftCount = items.filter(it => it.so_thanh_phan === 0).length;

  return (
    <main className="tg-page">
      <header className="tg-head">
        <div className="tg-head__lead">
          <p className="eyebrow">Kinh doanh</p>
          <h1 className="tg-head__title">Tính giá thành</h1>
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

        <div className="ptg-toolbar-spacer" />

        <Button variant="accent" onClick={create} loading={creating}>
          + Lập phiếu tính giá
        </Button>
      </div>

      <div style={{ margin: "4px 0 8px" }}>
        <StatusTabs
          tabs={[
            { key: "all", label: "Tất cả", count: allCount },
            { key: "calculated", label: "Đã tính giá", count: calculatedCount },
            { key: "draft", label: "Phiếu nháp", count: draftCount },
          ]}
          active={statusFilter}
          onChange={setStatusFilter}
        />
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
              <th>
                <SortBtn label="Mã PTG" col="ma" sort={sort} onSort={setSort} />
              </th>
              <th>Sản phẩm</th>
              <th className="tg-num">
                <SortBtn label="SL" col="so_luong" sort={sort} onSort={setSort} />
              </th>
              <th className="tg-num">
                <SortBtn label="Giá vốn/đơn" col="gia_von_don" sort={sort} onSort={setSort} />
              </th>
              <th className="tg-num">
                <SortBtn label="Tổng giá vốn" col="tong_gia_von" sort={sort} onSort={setSort} />
              </th>
              <th>Trạng thái</th>
              <th>
                <SortBtn label="Ngày · KTV" col="ngay" sort={sort} onSort={setSort} />
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="ptg-msg">
                  Đang tải dữ liệu…
                </td>
              </tr>
            ) : filteredAndSortedItems.length === 0 ? (
              <tr>
                <td colSpan={7} className="ptg-empty-td">
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
              filteredAndSortedItems.map((it) => (
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
                  <td className="tg-mono ptg-nowrap" style={{ fontWeight: "bold" }}>
                    {it.ma}
                  </td>
                  <td className="ptg-prod">
                    <span className="ptg-prod__name">{it.ten_san_pham || "—"}</span>
                    <span className="ptg-prod__spec">{specLine(it)}</span>
                  </td>
                  <td className="tg-num">{fmt(it.so_luong)}</td>
                  <td className="tg-num">{fmt(it.gia_von_don)} đ</td>
                  <td className="tg-num ptg-strong" style={{ color: "var(--rust-deep)" }}>
                    {fmt(it.tong_gia_von)} đ
                  </td>
                  <td>
                    {it.so_thanh_phan === 0 ? (
                      <span className="ptg-badge ptg-badge--neutral">Nháp</span>
                    ) : it.tong_gia_von > 0 ? (
                      <span className="ptg-badge ptg-badge--moss">Đã tính giá</span>
                    ) : (
                      <span className="ptg-badge ptg-badge--amber">Đang tính</span>
                    )}
                  </td>
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

      {!loading && filteredAndSortedItems.length > 0 ? (
        <p className="ptg-foot-note">
          Tìm thấy {fmt(filteredAndSortedItems.length)} phiếu trong bộ lọc hiện tại.
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
