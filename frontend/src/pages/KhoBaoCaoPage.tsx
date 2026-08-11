// Báo cáo kho (kế toán) — sổ nhập-xuất (phiếu ĐÃ GHI SỔ) + khóa kỳ THEO KHOẢNG (chốt/mở) +
// tab Lịch sử thao tác + export MISA. docs/spec-bao-cao-kho.md. Chỉ quyền `close_book` vào.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type BaoCaoKhoRow,
  type KhoaSoKyRow,
  type KhoKhoaSoRow,
  type StockRequestKind,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { Select } from "../components/Select";
import { fmtQty, todayISO } from "./khoShared";
import "./rebuild-catalog.css";
import "./kho-request.css";

type KhoOpt = { id: number; ma: string; ten: string };
type Tab = "so" | "lichsu" | "ky";

const PAGE_SIZE = 20;

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}
function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  // Backend lưu UTC nhưng serialize KHÔNG kèm offset (naive) → thêm 'Z' để đổi về giờ máy cho đúng.
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const dt = new Date(s);
  if (Number.isNaN(dt.getTime())) return fmtDate(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(dt.getDate())}/${p(dt.getMonth() + 1)}/${dt.getFullYear()} ${p(dt.getHours())}:${p(dt.getMinutes())}`;
}
function fmtMoney(n: number | null): string {
  return n == null ? "" : n.toLocaleString("vi-VN");
}

// Icon khóa/mở theo bộ icon dự án (SVG line, thừa kế currentColor) — thay cho emoji.
function LockIcon({ open = false, size = 13 }: { open?: boolean; size?: number }) {
  return <Icon name={open ? "lockOpen" : "lock"} size={size} style={{ verticalAlign: "-2px" }} />;
}

export function KhoBaoCaoPage({ token }: { token: string }) {
  const [tab, setTab] = useState<Tab>("so");
  const [loai, setLoai] = useState<StockRequestKind>("NHAP");
  const [khoId, setKhoId] = useState<number | null>(null);
  const [tu, setTu] = useState("");
  const [den, setDen] = useState("");

  const [rows, setRows] = useState<BaoCaoKhoRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [khoList, setKhoList] = useState<KhoOpt[]>([]);
  const [exporting, setExporting] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // Khóa/mở kỳ + lịch sử + các kỳ CÒN đang khóa (tab "Kỳ đã khóa")
  const [locks, setLocks] = useState<KhoKhoaSoRow[]>([]);
  const [kyList, setKyList] = useState<KhoaSoKyRow[]>([]);
  const [khoaOpen, setKhoaOpen] = useState(false);
  const [khoaScope, setKhoaScope] = useState<"all" | number>("all");
  const [khoaHanhDong, setKhoaHanhDong] = useState<"khoa" | "mo">("khoa");
  const [khoaTu, setKhoaTu] = useState("");
  const [khoaDen, setKhoaDen] = useState(todayISO());
  const [khoaBusy, setKhoaBusy] = useState(false);
  const [khoaError, setKhoaError] = useState<string | null>(null);

  useEffect(() => {
    crud("/api/kho")
      .list(token, { active: true })
      .then((r) =>
        setKhoList(
          r.items.map((w) => ({ id: Number(w.id), ma: String(w.ma), ten: String(w.ten) })),
        ),
      )
      .catch(() => {});
  }, [token]);

  const loadLocks = useCallback(() => {
    api.kho.baoCao.khoaSo(token).then(setLocks).catch(() => {});
    api.kho.baoCao.ky(token).then(setKyList).catch(() => {});
  }, [token]);
  useEffect(() => {
    loadLocks();
  }, [loadLocks]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.kho.baoCao
      .dong(token, { tu: tu || null, den: den || null, kho_id: khoId, loai })
      .then((p) => setRows(p.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được báo cáo."))
      .finally(() => setLoading(false));
  }, [token, tu, den, khoId, loai]);
  useEffect(() => {
    if (tab === "so") load();
  }, [load, tab]);

  const khoOptions = useMemo(
    () => [
      { value: "", label: "Tất cả kho" },
      ...khoList.map((k) => ({ value: String(k.id), label: `${k.ma} · ${k.ten}` })),
    ],
    [khoList],
  );

  // Bản ghi 'khoa' phủ (kho, NGÀY GHI SỔ) — null nếu không khóa. Mới-nhất-trước (id desc) → bản ghi
  // đầu tiên phủ ngày quyết định (giống backend is_locked). Dùng cả để TÔ MÀU theo kỳ.
  const lockRecordFor = useCallback(
    (khoId: number | null, ngay: string | null): KhoKhoaSoRow | null => {
      const d = ngay?.slice(0, 10);
      if (!d) return null;
      for (const l of locks) {
        if (l.tu_ngay <= d && d <= l.den_ngay && (l.kho_id == null || l.kho_id === khoId)) {
          return l.hanh_dong === "khoa" ? l : null;
        }
      }
      return null;
    },
    [locks],
  );

  // Tìm kiếm (số CT / mã / tên hàng) + phân trang — client-side trên dữ liệu đã tải.
  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        (r.so_ct ?? "").toLowerCase().includes(q) ||
        (r.ma_hang ?? "").toLowerCase().includes(q) ||
        (r.ten_hang ?? "").toLowerCase().includes(q),
    );
  }, [rows, search]);

  const total = useMemo(
    () => filteredRows.reduce((s, r) => s + (r.thanh_tien ?? 0), 0),
    [filteredRows],
  );
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const pagedRows = useMemo(
    () => filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredRows, page],
  );
  useEffect(() => {
    setPage(1);
  }, [search, loai, khoId, tu, den, tab]);

  // Lịch sử thao tác cũng phân trang (dùng chung `page`; reset khi đổi tab ở effect trên).
  const histPageCount = Math.max(1, Math.ceil(locks.length / PAGE_SIZE));
  const pagedLocks = useMemo(
    () => locks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [locks, page],
  );

  // Mỗi kỳ khóa (bản ghi 'khoa' phủ dòng) một MÀU riêng — index theo thứ tự thời gian (tu_ngay).
  const periodIndex = useMemo(() => {
    const ids: number[] = [];
    for (const r of rows) {
      const rec = lockRecordFor(r.kho_id, r.ngay_ghi_so);
      if (rec && !ids.includes(rec.id)) ids.push(rec.id);
    }
    ids.sort((a, b) => {
      const la = locks.find((l) => l.id === a);
      const lb = locks.find((l) => l.id === b);
      return (la?.tu_ngay ?? "").localeCompare(lb?.tu_ngay ?? "");
    });
    const m = new Map<number, number>();
    ids.forEach((id, i) => m.set(id, i));
    return m;
  }, [rows, lockRecordFor, locks]);

  async function doExport() {
    setExporting(true);
    setError(null);
    try {
      const url = await api.kho.baoCao.exportXlsxBlobUrl(token, loai, {
        tu: tu || null,
        den: den || null,
        kho_id: khoId,
        q: search || null,
      });
      const a = document.createElement("a");
      a.href = url;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xuất được Excel.");
    } finally {
      setExporting(false);
    }
  }

  // Bấm "Xem sổ kỳ này" ở tab Kỳ đã khóa → nhảy về tab Sổ, set sẵn khoảng ngày (+kho) của kỳ.
  function viewKy(k: KhoaSoKyRow) {
    setTu(k.tu_ngay);
    setDen(k.den_ngay);
    setKhoId(k.kho_id ?? null);
    setSearch("");
    setTab("so");
  }

  function openKhoa() {
    setKhoaScope(khoId != null ? khoId : "all");
    setKhoaHanhDong("khoa");
    setKhoaTu("");
    setKhoaDen(todayISO());
    setKhoaError(null);
    loadLocks();
    setKhoaOpen(true);
  }
  async function saveKhoa() {
    if (!khoaTu || !khoaDen) {
      setKhoaError("Chọn cả ngày từ và ngày đến.");
      return;
    }
    if (khoaDen < khoaTu) {
      setKhoaError("Ngày đến phải ≥ ngày từ.");
      return;
    }
    setKhoaBusy(true);
    setKhoaError(null);
    try {
      await api.kho.baoCao.setKhoaSo(token, {
        kho_id: khoaScope === "all" ? null : khoaScope,
        tu_ngay: khoaTu,
        den_ngay: khoaDen,
        hanh_dong: khoaHanhDong,
      });
      loadLocks();
      setKhoaOpen(false);
    } catch (e) {
      setKhoaError(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setKhoaBusy(false);
    }
  }

  return (
    <main className="rc kho-list">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Báo cáo kho</h1>
          <span className="rc__count">
            {tab === "so"
              ? `${rows.length} dòng`
              : tab === "lichsu"
                ? `${locks.length} thao tác`
                : `${kyList.length} kỳ`}
          </span>
          <button
            type="button"
            className="btn btn--secondary kho-export-btn"
            onClick={openKhoa}
            title="Khóa / mở sổ kỳ kế toán theo khoảng ngày — toàn kho hoặc từng kho"
          >
            <LockIcon size={15} /> Khóa / mở kỳ
          </button>
          {tab === "so" && (
            <button
              type="button"
              className="btn btn--secondary kho-export-btn"
              disabled={exporting || rows.length === 0}
              onClick={doExport}
              title="Xuất Excel đúng mẫu MISA (theo chiều đang chọn)"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              {exporting ? "Đang xuất…" : "Xuất Excel"}
            </button>
          )}
        </div>
        <p className="rc__sub">
          Sổ nhập–xuất từ phiếu ĐÃ GHI SỔ + khóa/mở kỳ + lịch sử thao tác — cho kế toán kho. Loại
          nhập/xuất MISA do kế toán tự điền trên Excel dựa theo chiều + kho.
        </p>
      </header>

      <div className="kho-shell">
        <div className="kho-shell__fns">
          {(
            [
              ["so", "Sổ nhập-xuất"],
              ["lichsu", "Lịch sử thao tác"],
              ["ky", "Kỳ đã khóa"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`kho-shell__fn${tab === id ? " is-active" : ""}`}
              onClick={() => setTab(id)}
            >
              {label}
              {id === "lichsu" && locks.length > 0 ? ` (${locks.length})` : ""}
              {id === "ky" && kyList.length > 0 ? ` (${kyList.length})` : ""}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rc__empty-state" style={{ color: "var(--rust, #b4531f)" }}>{error}</div>
      )}

      {tab === "so" && (
        <>
          <div className="rc__toolbar">
            <div className="kho-picker">
              <Select
                ariaLabel="Chiều"
                value={loai}
                onChange={(v) => setLoai(v as StockRequestKind)}
                options={[
                  { value: "NHAP", label: "Nhập kho" },
                  { value: "XUAT", label: "Xuất kho" },
                ]}
              />
            </div>
            <div className="kho-picker">
              <Select
                ariaLabel="Kho"
                value={khoId == null ? "" : String(khoId)}
                onChange={(v) => setKhoId(v ? Number(v) : null)}
                options={khoOptions}
              />
            </div>
            <label className="kho-baocao__daterow">
              <span>Ngày ghi sổ từ</span>
              <input type="date" className="rc-input" value={tu} max={den || undefined} onChange={(e) => setTu(e.target.value)} />
            </label>
            <label className="kho-baocao__daterow">
              <span>đến</span>
              <input type="date" className="rc-input" value={den} min={tu || undefined} onChange={(e) => setDen(e.target.value)} />
            </label>
            {(tu || den) && (
              <button type="button" className="rc__link-btn" onClick={() => { setTu(""); setDen(""); }}>
                Xóa lọc ngày
              </button>
            )}
            <input
              className="rc-input"
              style={{ marginLeft: "auto", maxWidth: 260 }}
              placeholder="Tìm số CT / mã / tên hàng…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {locks.some((l) => l.hanh_dong === "khoa") && (
            <p className="rc-field__hint" style={{ margin: "0 0 var(--sp-1)" }}>
              <LockIcon /> = phiếu thuộc kỳ đã khóa sổ (không ghi sổ vào kỳ này); mỗi MÀU vạch trái là một kỳ khóa khác nhau.
            </p>
          )}

          <div className="kho-bc-wrap">
            <table className="rc__table kho-bc">
              <thead>
                <tr>
                  <th title="Ngày hạch toán (MISA) — lúc ghi sổ phiếu">Ngày ghi sổ</th>
                  <th title="Ngày chứng từ — ngày lập phiếu">Ngày CT</th>
                  <th title="Số chứng từ — mã phiếu PNK/PXK">Số CT</th>
                  <th title="Kho của phiếu — kế toán dựa vào chiều + kho để điền mã 0/1/2/3 trên Excel">Kho</th>
                  <th title="Mã vật tư">Mã hàng</th>
                  <th title="Tên vật tư — di chuột xem đầy đủ nếu dài">Tên hàng</th>
                  <th title="Đơn vị tính">ĐVT</th>
                  <th className="kho-bc__num" title="Số lượng nhập/xuất">Số lượng</th>
                  <th className="kho-bc__num" title="Đơn giá (nhập: giá nhập; xuất: giá vốn)">Đơn giá</th>
                  <th className="kho-bc__num" title="Thành tiền = số lượng × đơn giá">Thành tiền</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={10} className="rc__empty-state">Đang tải…</td></tr>
                ) : filteredRows.length === 0 ? (
                  <tr><td colSpan={10} className="rc__empty-state">Không có dòng nào (phiếu đã ghi sổ) trong kỳ / bộ lọc.</td></tr>
                ) : (
                  pagedRows.map((r, i) => {
                    const rec = lockRecordFor(r.kho_id, r.ngay_ghi_so);
                    const pIdx = rec ? (periodIndex.get(rec.id) ?? 0) % 3 : -1;
                    return (
                    <tr key={`${r.voucher_id}-${i}`} className={rec ? `kho-bc__lock kho-bc__lock-${pIdx}` : undefined}>
                      <td>
                        {rec && (
                          <span title={`Kỳ đã khóa: ${fmtDate(rec.tu_ngay)} – ${fmtDate(rec.den_ngay)}`} style={{ marginRight: 3 }}>
                            <LockIcon />
                          </span>
                        )}
                        {fmtDate(r.ngay_ghi_so)}
                      </td>
                      <td>{fmtDate(r.ngay_ct)}</td>
                      <td><span className="rc__code-badge">{r.so_ct}</span></td>
                      <td>{r.kho_ten ?? "—"}</td>
                      <td>{r.ma_hang ?? "—"}</td>
                      <td>
                        <span className="kho-bc__name" title={r.ten_hang ?? ""}>{r.ten_hang ?? "—"}</span>
                      </td>
                      <td>{r.dvt ?? ""}</td>
                      <td className="kho-bc__num">{fmtQty(r.so_luong)}</td>
                      <td className="kho-bc__num">{fmtMoney(r.don_gia)}</td>
                      <td className="kho-bc__num">{fmtMoney(r.thanh_tien)}</td>
                    </tr>
                    );
                  })
                )}
              </tbody>
              {filteredRows.length > 0 && (
                <tfoot>
                  <tr>
                    <td colSpan={9} className="kho-bc__num" style={{ fontWeight: 600 }}>
                      Tổng thành tiền ({filteredRows.length} dòng)
                    </td>
                    <td className="kho-bc__num" style={{ fontWeight: 600 }}>{fmtMoney(total)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {filteredRows.length > 0 && (
            <div className="kho-bc-pager">
              <button
                type="button"
                className="rc__link-btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ‹ Trước
              </button>
              <span>
                Trang {page}/{pageCount} · {filteredRows.length} dòng
              </span>
              <button
                type="button"
                className="rc__link-btn"
                disabled={page >= pageCount}
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              >
                Sau ›
              </button>
            </div>
          )}
        </>
      )}

      {tab === "lichsu" && (
        <>
        <div className="kho-bc-wrap">
          <table className="rc__table kho-bc">
            <thead>
              <tr>
                <th title="Thời điểm thực hiện thao tác (giờ máy)">Thời điểm</th>
                <th title="Khóa kỳ hoặc Mở lại kỳ đã khóa">Hành động</th>
                <th title="Áp dụng cho toàn bộ kho hay một kho cụ thể">Phạm vi</th>
                <th title="Khoảng ngày chứng từ bị khóa/mở (bao gồm 2 đầu)">Khoảng ngày</th>
                <th title="Kế toán thực hiện thao tác">Người thực hiện</th>
              </tr>
            </thead>
            <tbody>
              {locks.length === 0 ? (
                <tr><td colSpan={5} className="rc__empty-state">Chưa có thao tác khóa/mở kỳ nào.</td></tr>
              ) : (
                pagedLocks.map((l) => (
                  <tr key={l.id}>
                    <td>{fmtDateTime(l.khoa_luc)}</td>
                    <td>
                      <span
                        className={`badge-sem badge-sem--${l.hanh_dong === "khoa" ? "rust" : "moss"}`}
                        style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                      >
                        <LockIcon open={l.hanh_dong === "mo"} />
                        {l.hanh_dong === "khoa" ? "Khóa" : "Mở"}
                      </span>
                    </td>
                    <td>{l.kho_id == null ? "Toàn kho" : l.kho_ten ?? `Kho #${l.kho_id}`}</td>
                    <td>{fmtDate(l.tu_ngay)} – {fmtDate(l.den_ngay)}</td>
                    <td>{l.nguoi_khoa_ten ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {locks.length > 0 && (
          <div className="kho-bc-pager">
            <button
              type="button"
              className="rc__link-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹ Trước
            </button>
            <span>
              Trang {page}/{histPageCount} · {locks.length} thao tác
            </span>
            <button
              type="button"
              className="rc__link-btn"
              disabled={page >= histPageCount}
              onClick={() => setPage((p) => Math.min(histPageCount, p + 1))}
            >
              Sau ›
            </button>
          </div>
        )}
        </>
      )}

      {tab === "ky" && (
        <div className="kho-bc-wrap">
          <table className="rc__table kho-bc">
            <thead>
              <tr>
                <th title="Khoảng ngày ghi sổ đang bị khóa (gồm 2 đầu)">Khoảng ngày</th>
                <th title="Toàn kho hay một kho cụ thể">Phạm vi</th>
                <th title="Thời điểm khóa kỳ này">Khóa lúc</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {kyList.length === 0 ? (
                <tr>
                  <td colSpan={4} className="rc__empty-state">
                    Chưa có kỳ nào đang khóa. Bấm “Khóa / mở kỳ” để chốt sổ.
                  </td>
                </tr>
              ) : (
                kyList.map((k, i) => (
                  <tr key={`${k.kho_id ?? "all"}-${k.tu_ngay}-${i}`}>
                    <td>{fmtDate(k.tu_ngay)} – {fmtDate(k.den_ngay)}</td>
                    <td>{k.kho_id == null ? "Toàn kho" : k.kho_ten ?? `Kho #${k.kho_id}`}</td>
                    <td>{fmtDateTime(k.khoa_luc)}</td>
                    <td>
                      <button type="button" className="rc__link-btn" onClick={() => viewKy(k)}>
                        Xem sổ kỳ này
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={khoaOpen}
        title={khoaHanhDong === "khoa" ? "Khóa kỳ kế toán kho" : "Mở lại kỳ kế toán kho"}
        confirmLabel={khoaHanhDong === "khoa" ? "Khóa sổ" : "Mở sổ"}
        cancelLabel="Hủy"
        busy={khoaBusy}
        error={khoaError}
        confirmDisabled={!khoaTu || !khoaDen}
        onConfirm={saveKhoa}
        onCancel={() => setKhoaOpen(false)}
      >
        <div className="kho-khoa">
          <div className="kho-khoa__field">
            <span className="kho-khoa__label">Hành động</span>
            <div className="kho-khoa__seg">
              {(
                [
                  ["khoa", "Khóa kỳ"],
                  ["mo", "Mở kỳ"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`kho-khoa__seg-btn${
                    khoaHanhDong === id ? (id === "khoa" ? " is-khoa" : " is-mo") : ""
                  }`}
                  onClick={() => setKhoaHanhDong(id)}
                >
                  <LockIcon open={id === "mo"} size={15} />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="kho-khoa__field">
            <span className="kho-khoa__label">Phạm vi</span>
            <Select
              portal
              ariaLabel="Phạm vi"
              value={khoaScope === "all" ? "" : String(khoaScope)}
              onChange={(v) => setKhoaScope(v ? Number(v) : "all")}
              options={[
                { value: "", label: "Toàn kho" },
                ...khoList.map((k) => ({ value: String(k.id), label: `${k.ma} · ${k.ten}` })),
              ]}
            />
          </div>

          <div className="kho-khoa__row">
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="khoa-tu">Từ ngày</label>
              <input id="khoa-tu" type="date" className="rc-input" value={khoaTu} max={khoaDen || undefined} onChange={(e) => setKhoaTu(e.target.value)} />
            </div>
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="khoa-den">Đến ngày</label>
              <input id="khoa-den" type="date" className="rc-input" value={khoaDen} min={khoaTu || undefined} onChange={(e) => setKhoaDen(e.target.value)} />
            </div>
          </div>

          <p className={`kho-khoa__note kho-khoa__note--${khoaHanhDong}`}>
            <LockIcon open={khoaHanhDong === "mo"} size={14} />
            <span>
              {khoaHanhDong === "khoa"
                ? "Phiếu có NGÀY GHI SỔ (ngày hạch toán) trong khoảng này thuộc kỳ đã chốt — không ghi sổ vào kỳ này được."
                : "Mở lại kỳ để ghi sổ tiếp. Đặt “Đến ngày” = ngày cuối đang khóa. Thao tác nào cũng lưu vào Lịch sử."}
            </span>
          </p>
        </div>
      </ConfirmDialog>
    </main>
  );
}
