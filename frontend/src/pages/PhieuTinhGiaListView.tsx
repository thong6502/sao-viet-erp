// MASTER của "Tính giá" — danh sách phiếu tính giá (giá vốn). Bấm dòng → detail. Nút "+ Lập phiếu
// tính giá" tạo nháp rồi mở detail. StatusTabs lọc theo tab; search debounce. Bám pattern list nhà
// (RebuildCatalogPage): row hover, code mono badge, số liệu mono/tabular/vi-VN căn phải.
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type PhieuTinhGiaListItem,
  type PhieuTinhGiaStatsOut,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { StatusTabs } from "../components/StatusTabs";
import "./tinh-gia.css";

const PAGE_SIZE = 20;

const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";

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
  // Mở form phiếu NHÁP — không tạo bản ghi. Phiếu chỉ vào DB khi có sản phẩm + bấm Tính giá.
  onNew: () => void;
}) {
  const { token } = useAuth();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<PhieuTinhGiaListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<PhieuTinhGiaStatsOut | null>(null);

  const [statusFilter, setStatusFilter] = useState("all");
  const [sort, setSort] = useState("-ngay");

  // Debounce ô tìm kiếm.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQ, statusFilter, sort]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.phieuTinhGia
      .list(token, {
        q: debouncedQ || undefined,
        status: statusFilter === "all" ? undefined : statusFilter,
        sort,
        page,
        size: PAGE_SIZE,
      })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách phiếu."))
      .finally(() => setLoading(false));
    api.phieuTinhGia.stats(token).then(setStats).catch(() => setStats(null));
  }, [token, debouncedQ, statusFilter, sort, page]);
  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const allCount = stats?.all ?? 0;
  const calculatedCount = stats?.calculated ?? 0;
  const draftCount = stats?.draft ?? 0;

  return (
    <main className="rdx-cost tg-page">
      <header className="tg-head">
        <div className="tg-head__lead">
          <div className="eyebrow"><span className="sq" /> Kinh doanh · Giá vốn nội bộ</div>
          <h1 className="tg-head__title">Tính giá thành</h1>
          <p className="tg-head__sub">
            Bóc tách giá vốn theo nguyên vật liệu &amp; công đoạn — cơ sở lập báo giá.
          </p>
        </div>
        <div className="tg-head__actions">
          {/* Chỉ MỞ FORM, không POST: phiếu rỗng không được sinh ra rồi bỏ lại trong DB. */}
          <Button variant="accent" onClick={onNew}>
            <PlusIcon /> Lập phiếu tính giá
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
              {/* SL ở đây là Σ SL CÁC SẢN PHẨM bên trong phiếu (không phải ô SL mặc định đầu
                  phiếu) — có vậy SL × giá vốn/đơn mới ra tổng giá vốn ngay hàng bên cạnh. */}
              <th className="tg-num" title="Tổng số lượng của các sản phẩm trong phiếu">
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
                {/* "Ngày" trần đọc lên không biết là ngày nào — lập, tính giá, hay sửa lần cuối.
                    Cột này sắp xếp theo `created_at` nên gọi đúng tên: ngày LẬP. */}
                <SortBtn label="Ngày lập · Người lập" col="ngay" sort={sort} onSort={setSort} />
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
            ) : items.length === 0 ? (
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
                      <Button variant="ghost" onClick={onNew}>
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
                  <td className="tg-mono ptg-nowrap" style={{ fontWeight: "bold" }}>
                    {it.ma}
                  </td>
                  <td className="ptg-prod">
                    {/* Tên ở ĐẦU PHIẾU (`ten_san_pham`) là chữ ĐÓNG BĂNG: màn phiếu không còn ô
                        nào sửa được nó, nên nó không chạy theo tên hàng bên trong. Vì vậy:
                        · Phiếu 1 MÓN → lấy thẳng tên món đó. Món ấy CHÍNH LÀ phiếu, sửa tên trong
                          phiếu là ngoài này đổi theo ngay; giữ chữ đầu phiếu chỉ tổ trơ tên cũ.
                        · Phiếu NHIỀU MÓN → giữ tên cụm ở đầu phiếu (vd "Bộ ấn phẩm khai trương…")
                          vì không tên món nào gọi được cả cụm; từng món kể ở dòng phụ, và dòng phụ
                          thì chạy theo tên thật. Một phiếu ba món (ruột · bìa · thẻ) mà nhìn ngoài
                          chỉ thấy một dòng là chỗ hay nhầm nhất.
                        · Phiếu CHƯA có món nào → còn gì hiện nấy. */}
                    {(() => {
                      const trong = it.ten_thanh_phans ?? [];
                      const motMon = trong.length === 1;
                      const chinh = motMon ? trong[0] : it.ten_san_pham || trong[0] || "";
                      const con = motMon ? [] : it.ten_san_pham ? trong : trong.slice(1);
                      const ke = con.slice(0, 3).join(" · ") + (con.length > 3 ? " · …" : "");
                      return (
                        <>
                          <span className="ptg-prod__name" title={trong.join(" · ") || undefined}>
                            {chinh || "—"}
                          </span>
                          {con.length > 0 ? (
                            <span className="ptg-prod__spec">+{con.length} sản phẩm: {ke}</span>
                          ) : null}
                        </>
                      );
                    })()}
                  </td>
                  <td className="tg-num">{fmt(it.so_luong)}</td>
                  <td className="tg-num">{fmt(it.gia_von_don)} đ</td>
                  <td className="tg-num ptg-strong" style={{ color: "var(--rust-deep)" }}>
                    {fmt(it.tong_gia_von)} đ
                  </td>
                  <td>
                    {it.so_thanh_phan === 0 ? (
                      <span className="badge neutral"><span className="d" />Nháp</span>
                    ) : it.tong_gia_von > 0 ? (
                      <span className="badge soft"><span className="d" />Đã tính giá</span>
                    ) : (
                      <span className="badge pending"><span className="d" />Đang tính</span>
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

      {!loading && items.length > 0 ? (
        <div className="ptg-pager">
          <span className="ptg-pager__info">
            Tìm thấy {fmt(total)} phiếu · Trang {page}/{totalPages}
          </span>
          <div className="ptg-pager__btns">
            <button
              type="button"
              className="ptg-pager__btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <button
              type="button"
              className="ptg-pager__btn"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Sau ›
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}

// ---------- Inline icons ----------
const PlusIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 5v14M5 12h14" />
  </svg>
);

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
