// Báo cáo kho · tab "Giá gốc thành phẩm" (design nhập kho thành phẩm §5).
//
// Thành phẩm KCS gửi kho nhập với giá gốc 0 — phần mềm không tính được giá thành, kế toán kho gõ tay
// sau. Danh sách theo LÔ GỐC (lô sinh qua điều chuyển không thành dòng riêng); gõ giá một lần là
// máy chủ lan xuống cả họ lô (dòng phiếu nhập + giá lô ⇒ báo cáo Nhập-Xuất-Tồn, giá trị phiếu xuất
// đã ghi sổ). Lọc + trang ở máy chủ; chỉ người có "Xem giá vốn" mới thấy tab này.
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api, ApiError, type ThanhPhamChuaGiaGocPage, type ThanhPhamChuaGiaGocRow } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Pager } from "../components/Pager";
import { useDebounced } from "../utils/useDebounced";
import { fmtQty } from "./khoShared";

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

export function KhoGiaGocThanhPham({ token, onCount }: { token: string; onCount?: (n: number) => void }) {
  const [tim, setTim] = useState("");
  const timCham = useDebounced(tim.trim());
  const [chiChuaGia, setChiChuaGia] = useState(true);
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

  useEffect(() => { setTrang(1); }, [timCham, chiChuaGia]);
  useEffect(() => {
    let alive = true;
    setDangTai(true);
    api.kho.baoCao.thanhPhamChuaGiaGoc(token, { q: timCham || undefined, chiChuaGia, page: trang, size: CO_TRANG })
      .then((r) => { if (alive) { setData(r); setLoi(null); onCount?.(r.total); } })
      .catch((e) => { if (alive) setLoi(e instanceof ApiError ? e.message : "Không tải được danh sách thành phẩm."); })
      .finally(() => { if (alive) setDangTai(false); });
    return () => { alive = false; };
  }, [token, timCham, chiChuaGia, trang, tick, onCount]);

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
      setNhap((cu) => {
        const moi = { ...cu };
        delete moi[xacNhan.row.lot_id];
        return moi;
      });
      setXacNhan(null);
      setTick((t) => t + 1);
    } catch (e) {
      setLuuLoi(e instanceof ApiError ? e.message : "Không lưu được giá gốc.");
    } finally {
      setLuuBusy(false);
    }
  }

  const rows = data?.items ?? [];

  return (
    <>
      <div className="banner banner--info" style={{ marginBottom: 8 }}>
        <span>
          Thành phẩm KCS gửi kho nhập với <b>giá gốc 0</b>. Gõ giá gốc cho <b>lô gốc</b> — lô đã điều chuyển sang
          kho khác và phiếu xuất đã ghi sổ của các lô đó cập nhật theo. Kỳ đã khoá sổ thì không sửa được.
        </span>
      </div>
      {thongBao && (
        <div className="banner banner--success" role="status" style={{ marginBottom: 8 }}>
          <span>{thongBao}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setThongBao(null)}>Đóng</button>
        </div>
      )}
      <div className="rc__toolbar">
        <div className="rc__search-wrapper" style={{ width: 280 }}>
          <Search className="rc__search-icon" style={{ width: 15, height: 15 }} />
          <input
            className="rc__search"
            placeholder="Tìm mã lô / hàng / lệnh / đơn / khách…"
            value={tim}
            onChange={(e) => setTim(e.target.value)}
          />
        </div>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
          <input type="checkbox" checked={chiChuaGia} onChange={(e) => setChiChuaGia(e.target.checked)} />
          Chỉ lô chưa có giá gốc
        </label>
      </div>
      {loi && <div className="rc__empty-state" style={{ color: "var(--rust, #b4531f)" }}>{loi}</div>}
      <div className="kho-bc-wrap">
        <table className="rc__table kho-bc">
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
              <th className="kho-bc__num">Giá gốc</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {dangTai && data == null ? (
              <tr><td colSpan={10} className="rc__empty-state">Đang tải…</td></tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={10} className="rc__empty-state">
                  {chiChuaGia ? "Không còn lô thành phẩm nào chưa có giá gốc." : "Chưa có lô thành phẩm nào nhập từ KCS."}
                </td>
              </tr>
            ) : rows.map((r) => {
              const dang = nhap[r.lot_id];
              const gia = dang == null ? null : docGia(dang);
              const doi = gia != null && gia !== r.don_gia;
              const dv = r.dvt_ten ?? r.dvt ?? "";
              return (
                <tr key={r.lot_id}>
                  <td>
                    <strong>{r.ma_lo}</strong>
                    {r.so_lo > 1 && <div className="rc__muted">+{r.so_lo - 1} lô điều chuyển</div>}
                  </td>
                  <td>{ngay(r.ngay_nhap)}</td>
                  <td>{r.kho_ten ?? "—"}</td>
                  <td>
                    <div>{r.ten_hang ?? "—"}</div>
                    {r.ma_hang && <div className="rc__muted">{r.ma_hang}</div>}
                  </td>
                  <td>
                    <div>{[r.lsx_ma, r.order_ma].filter(Boolean).join(" · ") || "—"}</div>
                    {r.khach_hang && <div className="rc__muted">{r.khach_hang}</div>}
                  </td>
                  <td className="kho-bc__num">{fmtQty(r.so_luong_nhap)} {dv}</td>
                  <td className="kho-bc__num">{fmtQty(r.sl_con_lai)} {dv}</td>
                  <td className="kho-bc__num">{tien(r.don_gia_ban)}</td>
                  <td className="kho-bc__num">
                    <input
                      className="rc-input"
                      style={{ width: 120, textAlign: "right" }}
                      inputMode="numeric"
                      aria-label={`Giá gốc lô ${r.ma_lo}`}
                      placeholder="0"
                      value={dang ?? (r.don_gia > 0 ? tien(r.don_gia) : "")}
                      onChange={(e) => {
                        const g = docGia(e.target.value);
                        setNhap((cu) => ({ ...cu, [r.lot_id]: g == null ? "" : tien(g) }));
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && doi && gia != null) { setLuuLoi(null); setXacNhan({ row: r, gia }); }
                      }}
                    />
                  </td>
                  <td>
                    {doi && gia != null && (
                      <button type="button" className="btn btn--accent btn--sm"
                        onClick={() => { setLuuLoi(null); setXacNhan({ row: r, gia }); }}>
                        Lưu
                      </button>
                    )}
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
