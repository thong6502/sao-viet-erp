// Báo cáo kho · tab "Giá gốc thành phẩm" (design nhập kho thành phẩm §5).
//
// Thành phẩm KCS gửi kho nhập với giá gốc 0 — phần mềm không tính được giá thành, kế toán kho gõ tay
// sau. Danh sách theo LÔ GỐC (lô sinh qua điều chuyển không thành dòng riêng); gõ giá một lần là
// máy chủ lan xuống cả họ lô (dòng phiếu nhập + giá lô ⇒ báo cáo Nhập-Xuất-Tồn, giá trị phiếu xuất
// đã ghi sổ). Lọc + trang ở máy chủ; chỉ người có "Xem giá vốn" mới thấy tab này.
//
// Lọc nâng cao (khoảng ngày nhập · kho nhập · khách hàng) cùng khuôn "Lọc nâng cao" của màn danh mục:
// nút cạnh ô tìm, mở ra hàng ô; gập lại mà còn lọc thì hàng nhãn "Kho nhập: … ✕".
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, ApiError, type ThanhPhamChuaGiaGocPage, type ThanhPhamChuaGiaGocRow } from "../api/client";
import type { Row } from "../api/rebuildCatalog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Pager } from "../components/Pager";
import { useDebounced } from "../utils/useDebounced";
import { RefSearchField } from "./danh-muc/fields/RefFields";
import { FilterIcon, XIcon } from "./danh-muc/icons";
import { fmtQty } from "./khoShared";
import "./kho-gia-goc.css";

const CO_TRANG = 50;

const tien = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("vi-VN"));
const ngay = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};
/** Ô giá gõ kiểu "12.000" — chỉ giữ chữ số. Trống ⇒ null (chưa gõ gì). */
function docGia(s: string): number | null {
  const so = s.replace(/\D/g, "");
  return so === "" ? null : Number(so);
}
/** Ô `type="date"` nhận được cả năm 6 chữ số — giá trị rác gửi lên là 422 câm. Chỉ nhận YYYY-MM-DD. */
const ngayHopLe = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s);

type Loc = { tu: string; den: string; khoId: number | null; khachId: number | null };
const LOC_TRONG: Loc = { tu: "", den: "", khoId: null, khachId: null };

/** Ô giá gốc của một lô. Định dạng "1.850" NGAY khi gõ nhưng giữ con trỏ đứng sau đúng chữ số vừa gõ
 *  — định dạng lại cả chuỗi mà không đặt lại con trỏ thì sửa số ở giữa là con trỏ nhảy về cuối. Xoá
 *  trúng dấu chấm thì xoá luôn chữ số cạnh nó, không thì bấm xoá mà chẳng có gì xảy ra. Ô trống lúc
 *  rời đi = thôi sửa (giá cũ hiện lại) — để trống mà hiện "0" mờ thì không ai biết đó là 0 hay rỗng. */
function OGiaGoc({ row, dang, dv, onDoi, onBo, onLuu }: {
  row: ThanhPhamChuaGiaGocRow;
  dang: string | undefined;
  dv: string;
  onDoi: (s: string) => void;
  onBo: () => void;
  onLuu: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const conTro = useRef<number | null>(null);
  const gia = dang == null ? null : docGia(dang);
  const doi = gia != null && gia !== row.don_gia;

  useLayoutEffect(() => {
    const el = ref.current;
    const n = conTro.current;
    if (n == null || !el) return;
    conTro.current = null;
    let pos = 0;
    for (let dem = 0; pos < el.value.length && dem < n; pos++) if (/\d/.test(el.value[pos])) dem++;
    el.setSelectionRange(pos, pos);
  });

  return (
    <div className="kgg-gia">
      <input
        ref={ref}
        className={`rc-input kgg-gia__o${doi ? " is-doi" : ""}`}
        inputMode="numeric"
        aria-label={`Giá gốc lô ${row.ma_lo}`}
        placeholder={row.don_gia > 0 ? "Gõ giá mới" : "Chưa có giá"}
        value={dang ?? (row.don_gia > 0 ? tien(row.don_gia) : "")}
        onChange={(e) => {
          const el = e.target;
          let so = el.value.replace(/\D/g, "");
          let truoc = el.value.slice(0, el.selectionStart ?? el.value.length).replace(/\D/g, "").length;
          const cu = (dang ?? (row.don_gia > 0 ? tien(row.don_gia) : "")).replace(/\D/g, "");
          const kieu = (e.nativeEvent as InputEvent).inputType;
          if (so === cu && kieu === "deleteContentBackward" && truoc > 0) {
            so = so.slice(0, truoc - 1) + so.slice(truoc);
            truoc -= 1;
          } else if (so === cu && kieu === "deleteContentForward" && truoc < so.length) {
            so = so.slice(0, truoc) + so.slice(truoc + 1);
          }
          const g = docGia(so);
          conTro.current = truoc;
          onDoi(g == null ? "" : tien(g));
        }}
        onBlur={() => {
          if (dang != null && (gia == null || gia === row.don_gia)) onBo();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && doi) onLuu();
          if (e.key === "Escape" && dang != null) { e.preventDefault(); onBo(); }
        }}
      />
      <span className="kgg-gia__dv">đ/{dv || "đv"}</span>
      {/* Luôn giữ chỗ cho nút — nút mọc ra/biến mất mà chiếm chỗ thì cả bảng nở ra co vào theo
          từng phím gõ, và ở màn hẹp nút bị đẩy ra ngoài khung, phải kéo ngang mới thấy. */}
      <span className="kgg-gia__nut" style={{ visibility: doi ? "visible" : "hidden" }} aria-hidden={!doi}>
        <button type="button" className="btn btn--accent btn--sm" tabIndex={doi ? 0 : -1}
          onMouseDown={(e) => e.preventDefault()} onClick={onLuu}>
          Lưu
        </button>
        <button type="button" className="kgg-gia__bo" tabIndex={doi ? 0 : -1}
          title="Bỏ, giữ giá cũ (Esc)" aria-label={`Bỏ giá đang gõ của lô ${row.ma_lo}`}
          onMouseDown={(e) => e.preventDefault()} onClick={onBo}>
          <XIcon size={13} />
        </button>
      </span>
    </div>
  );
}

export function KhoGiaGocThanhPham({ token, onCount }: { token: string; onCount?: (n: number) => void }) {
  const [tim, setTim] = useState("");
  const timCham = useDebounced(tim.trim());
  const [chiChuaGia, setChiChuaGia] = useState(true);
  const [moLoc, setMoLoc] = useState(false);
  const [loc, setLoc] = useState<Loc>(LOC_TRONG);
  const [trang, setTrang] = useState(1);
  const [data, setData] = useState<ThanhPhamChuaGiaGocPage | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // Giá đang gõ dở theo lô (chưa lưu) — chuỗi hiển thị.
  const [nhap, setNhap] = useState<Record<number, string>>({});
  const [xacNhan, setXacNhan] = useState<{ row: ThanhPhamChuaGiaGocRow; gia: number } | null>(null);
  const [luuBusy, setLuuBusy] = useState(false);
  const [luuLoi, setLuuLoi] = useState<string | null>(null);
  const [thongBao, setThongBao] = useState<string | null>(null);

  const tu = ngayHopLe(loc.tu) ? loc.tu : "";
  const den = ngayHopLe(loc.den) ? loc.den : "";
  const nguocNgay = tu !== "" && den !== "" && den < tu;
  const soLoc = (tu || den ? 1 : 0) + (loc.khoId != null ? 1 : 0) + (loc.khachId != null ? 1 : 0);

  useEffect(() => { setTrang(1); }, [timCham, chiChuaGia, tu, den, loc.khoId, loc.khachId]);
  useEffect(() => {
    if (nguocNgay) return;
    let alive = true;
    setDangTai(true);
    api.kho.baoCao.thanhPhamChuaGiaGoc(token, {
      q: timCham || undefined, chiChuaGia, page: trang, size: CO_TRANG,
      tu: tu || undefined, den: den || undefined,
      khoId: loc.khoId ?? undefined, khachHangId: loc.khachId ?? undefined,
    })
      .then((r) => { if (alive) { setData(r); setLoi(null); onCount?.(r.total); } })
      .catch((e) => { if (alive) setLoi(e instanceof ApiError ? e.message : "Không tải được danh sách thành phẩm."); })
      .finally(() => { if (alive) setDangTai(false); });
    return () => { alive = false; };
  }, [token, timCham, chiChuaGia, trang, tick, onCount, tu, den, nguocNgay, loc.khoId, loc.khachId]);

  async function luu() {
    if (!xacNhan || luuBusy) return;
    setLuuBusy(true);
    setLuuLoi(null);
    try {
      const r = await api.kho.phieu.suaGiaGoc(token, xacNhan.row.lot_id, xacNhan.gia);
      setThongBao(
        `Đã đổi giá gốc lô ${r.ma_lo}: ${tien(r.don_gia_cu)} → ${tien(r.don_gia)} đ`
        + (r.so_lo > 1 ? ` (áp cho ${r.so_lo} lô, gồm lô đã điều chuyển).` : "."),
      );
      boNhap(xacNhan.row.lot_id);
      setXacNhan(null);
      setTick((t) => t + 1);
    } catch (e) {
      setLuuLoi(e instanceof ApiError ? e.message : "Không lưu được giá gốc.");
    } finally {
      setLuuBusy(false);
    }
  }
  function boNhap(lotId: number) {
    setNhap((cu) => {
      if (!(lotId in cu)) return cu;
      const moi = { ...cu };
      delete moi[lotId];
      return moi;
    });
  }

  const rows = data?.items ?? [];
  const cacKho = data?.cac_kho ?? [];
  const cacKhach: Row[] = (data?.cac_khach ?? []).map((k) => ({ id: k.id, ma: "", ten: k.ten ?? `#${k.id}` }));
  const tenKho = (id: number) => cacKho.find((k) => k.id === id)?.ten ?? `#${id}`;
  const tenKhach = (id: number) => cacKhach.find((k) => k.id === id)?.ten ?? `#${id}`;
  const nhanNgay = tu && den ? `${ngay(tu)} – ${ngay(den)}` : tu ? `từ ${ngay(tu)}` : den ? `đến ${ngay(den)}` : "";
  const coLoc = soLoc > 0 || timCham !== "";

  return (
    <>
      {thongBao ? (
        <div className="banner banner--success" role="status" style={{ marginBottom: 8 }}>
          <span>{thongBao}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setThongBao(null)}>Đóng</button>
        </div>
      ) : (
        <div className="banner banner--info" style={{ marginBottom: 8 }}>
          <span>
            Thành phẩm KCS gửi kho nhập với <b>giá gốc 0</b>. Gõ giá gốc cho <b>lô gốc</b> — lô đã điều chuyển sang
            kho khác và phiếu xuất đã ghi sổ của các lô đó cập nhật theo. Kỳ đã khoá sổ thì không sửa được.
          </span>
        </div>
      )}
      <div className="rc__toolbar kgg-toolbar">
        <div className="rc__search-wrapper" style={{ width: 280 }}>
          <Search className="rc__search-icon" style={{ width: 15, height: 15 }} />
          <input
            className="rc__search"
            placeholder="Tìm mã lô / hàng / lệnh / đơn / khách…"
            value={tim}
            onChange={(e) => setTim(e.target.value)}
          />
        </div>
        <button type="button"
          className={`rc__locnc-btn${moLoc ? " is-open" : ""}${soLoc > 0 ? " is-active" : ""}`}
          aria-expanded={moLoc}
          onClick={() => setMoLoc((v) => !v)}>
          <FilterIcon /> Lọc nâng cao
          {soLoc > 0 && <span className="chip-count">{soLoc}</span>}
        </button>
        <label className="kgg-chi-chua">
          <input type="checkbox" checked={chiChuaGia} onChange={(e) => setChiChuaGia(e.target.checked)} />
          Chỉ lô chưa có giá gốc
        </label>
      </div>

      {moLoc ? (
        <div className="rc__locnc kgg-loc" role="group" aria-label="Lọc nâng cao">
          <div className="rc__locnc-field rc__locnc-field--rong">
            <span className="rc__locnc-label">Ngày nhập</span>
            <div className="kgg-loc__ngay">
              <input type="date" className="rc-input" aria-label="Ngày nhập từ" value={loc.tu}
                min="2000-01-01" max={den || "2099-12-31"}
                onChange={(e) => setLoc((l) => ({ ...l, tu: e.target.value }))} />
              <span className="kgg-loc__den">đến</span>
              <input type="date" className="rc-input" aria-label="Ngày nhập đến" value={loc.den}
                min={tu || "2000-01-01"} max="2099-12-31"
                onChange={(e) => setLoc((l) => ({ ...l, den: e.target.value }))} />
            </div>
            {nguocNgay && <span className="rc-field__hint rc-field__hint--loi">Ngày "đến" phải từ ngày "từ" trở đi.</span>}
          </div>
          <div className="rc__locnc-field">
            <span className="rc__locnc-label">Kho nhập</span>
            <select className="rc-input" aria-label="Kho nhập"
              value={loc.khoId == null ? "" : String(loc.khoId)}
              onChange={(e) => setLoc((l) => ({ ...l, khoId: e.target.value ? Number(e.target.value) : null }))}>
              <option value="">Tất cả</option>
              {cacKho.map((k) => <option key={k.id} value={k.id}>{k.ten ?? `#${k.id}`}</option>)}
            </select>
          </div>
          <div className="rc__locnc-field rc__locnc-field--rong">
            <span className="rc__locnc-label">Khách hàng</span>
            <RefSearchField
              value={loc.khachId}
              options={cacKhach}
              placeholder="Gõ tên khách hàng để tìm…"
              onChange={(v) => setLoc((l) => ({ ...l, khachId: v == null || v === "" ? null : Number(v) }))}
            />
          </div>
          {soLoc > 0 && (
            <button type="button" className="rc__locnc-clear" onClick={() => setLoc(LOC_TRONG)}>Xoá bộ lọc</button>
          )}
        </div>
      ) : soLoc > 0 && (
        <div className="rc__locnc-tags" aria-label="Bộ lọc đang áp">
          {nhanNgay && (
            <span className="rc__locnc-tag">
              <span className="rc__locnc-tag-k">Ngày nhập:</span> {nhanNgay}
              <button type="button" className="rc__locnc-tag-x" aria-label="Bỏ lọc Ngày nhập" title="Bỏ lọc Ngày nhập"
                onClick={() => setLoc((l) => ({ ...l, tu: "", den: "" }))}>
                <XIcon size={11} />
              </button>
            </span>
          )}
          {loc.khoId != null && (
            <span className="rc__locnc-tag">
              <span className="rc__locnc-tag-k">Kho nhập:</span> {tenKho(loc.khoId)}
              <button type="button" className="rc__locnc-tag-x" aria-label="Bỏ lọc Kho nhập" title="Bỏ lọc Kho nhập"
                onClick={() => setLoc((l) => ({ ...l, khoId: null }))}>
                <XIcon size={11} />
              </button>
            </span>
          )}
          {loc.khachId != null && (
            <span className="rc__locnc-tag">
              <span className="rc__locnc-tag-k">Khách hàng:</span> {tenKhach(loc.khachId)}
              <button type="button" className="rc__locnc-tag-x" aria-label="Bỏ lọc Khách hàng" title="Bỏ lọc Khách hàng"
                onClick={() => setLoc((l) => ({ ...l, khachId: null }))}>
                <XIcon size={11} />
              </button>
            </span>
          )}
          {soLoc > 1 && (
            <button type="button" className="rc__locnc-clear" onClick={() => setLoc(LOC_TRONG)}>Xoá hết</button>
          )}
        </div>
      )}

      {loi && <div className="rc__empty-state" style={{ color: "var(--rust, #b4531f)" }}>{loi}</div>}
      <div className="kho-bc-wrap kgg-wrap">
        <table className="rc__table kho-bc kgg-bang">
          <thead>
            <tr>
              <th>Mã lô</th>
              <th>Ngày nhập</th>
              <th>Kho nhập</th>
              <th>Mặt hàng</th>
              <th>Lệnh · Đơn · Khách</th>
              <th className="kho-bc__num">SL nhập</th>
              <th className="kho-bc__num">Còn tồn</th>
              <th className="kho-bc__num">Giá bán (đơn)</th>
              <th>Giá gốc</th>
            </tr>
          </thead>
          <tbody>
            {dangTai && data == null ? (
              <tr><td colSpan={9} className="rc__empty-state">Đang tải…</td></tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="rc__empty-state">
                  {coLoc
                    ? "Không có lô nào khớp bộ lọc."
                    : chiChuaGia ? "Không còn lô thành phẩm nào chưa có giá gốc." : "Chưa có lô thành phẩm nào nhập từ KCS."}
                </td>
              </tr>
            ) : rows.map((r) => {
              const dang = nhap[r.lot_id];
              const dv = r.dvt_ten ?? r.dvt ?? "";
              return (
                <tr key={r.lot_id}>
                  <td>
                    <strong>{r.ma_lo}</strong>
                    {r.so_lo > 1 && <div className="rc__muted">+{r.so_lo - 1} lô điều chuyển</div>}
                  </td>
                  <td>{ngay(r.ngay_nhap)}</td>
                  <td className="kgg-chu">{r.kho_ten ?? "—"}</td>
                  <td className="kgg-chu">
                    <div>{r.ten_hang ?? "—"}</div>
                    {r.ma_hang && <div className="rc__muted">{r.ma_hang}</div>}
                  </td>
                  <td className="kgg-chu">
                    <div>{[r.lsx_ma, r.order_ma].filter(Boolean).join(" · ") || "—"}</div>
                    {r.khach_hang && <div className="rc__muted">{r.khach_hang}</div>}
                  </td>
                  <td className="kho-bc__num">{fmtQty(r.so_luong_nhap)} {dv}</td>
                  <td className="kho-bc__num">{fmtQty(r.sl_con_lai)} {dv}</td>
                  <td className="kho-bc__num">{tien(r.don_gia_ban)}</td>
                  <td>
                    <OGiaGoc
                      row={r}
                      dang={dang}
                      dv={dv}
                      onDoi={(s) => setNhap((cu) => ({ ...cu, [r.lot_id]: s }))}
                      onBo={() => boNhap(r.lot_id)}
                      onLuu={() => {
                        const gia = dang == null ? null : docGia(dang);
                        if (gia == null || gia === r.don_gia) return;
                        setLuuLoi(null);
                        setXacNhan({ row: r, gia });
                      }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {data && (
        <Pager total={data.total} page={data.page} size={data.size} onPage={setTrang} loading={dangTai} unit="lô gốc" />
      )}

      <ConfirmDialog
        open={xacNhan != null}
        title="Đổi giá gốc thành phẩm"
        message={xacNhan
          ? `Lô ${xacNhan.row.ma_lo} (${xacNhan.row.ten_hang ?? "thành phẩm"}): giá gốc ${tien(xacNhan.row.don_gia)} → ${tien(xacNhan.gia)} đ/${xacNhan.row.dvt_ten ?? xacNhan.row.dvt ?? "đơn vị"}.`
            + (xacNhan.row.so_lo > 1 ? ` Áp luôn cho ${xacNhan.row.so_lo - 1} lô đã điều chuyển sang kho khác.` : "")
            + " Báo cáo Nhập-Xuất-Tồn và giá trị phiếu xuất đã ghi sổ của các lô này đổi theo."
          : undefined}
        confirmLabel="Lưu giá gốc"
        busy={luuBusy}
        error={luuLoi}
        onConfirm={luu}
        onCancel={() => { if (!luuBusy) setXacNhan(null); }}
      />
    </>
  );
}
