// Màn KCS — KCS theo LỆNH (mg 0306, docs/design-kcs-theo-lenh.md). MỘT mục menu "KCS" cho người
// thuộc phòng ban có cờ "Tổ KCS"; họ kiểm được mọi tổ.
//
// Hai tầng trên cùng một trang:
//   1. Danh sách lệnh (tìm + cắt trang ở MÁY CHỦ) + dashboard báo cáo + bảng "Kết quả đã ghi".
//   2. Bấm một lệnh → chuỗi công đoạn (`KcsChuoiCongDoan`) → bấm "Kiểm" ở công đoạn.
//
// Báo cáo KCS — MỘT lượt gọi `bao-cao` nuôi CẢ dashboard (KPI + 3 biểu đồ) lẫn bảng "Kết quả đã
// ghi" (khoá `lich_su`); lọc chạy ở máy chủ, bảng không lọc lại ở FE.
import { useEffect, useState } from "react";
import {
  ApiError, api,
  type SxKcsBaoCao, type SxKcsCongDoanLoc, type SxKcsLenhList,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useCan, useKcs } from "../../auth/permissions";
import type { NavigateFn } from "../../components/AppShell";
import { Pager } from "../../components/Pager";
import { useDebounced } from "../../utils/useDebounced";
import { num, ngayGio } from "../keHoachSxShared";
import { nhanDonVi } from "../lsxBuoc";
import { KcsChuoiCongDoan } from "./KcsChuoiCongDoan";
import { KcsDashboard, KCS_DASH_FILTERS_RONG, type KcsDashFilters } from "./KcsDashboard";
import { KCS_NHOM_TRANG_THAI, KCS_TRANG_THAI_GUI_KHO_LABEL } from "./kcsNhan";
import "../rebuild-catalog.css";
import "./kcs.css";

export function KcsTheoLenhPage({
  eventTick, onBadgeStale, navigate,
}: {
  eventTick?: number;
  onBadgeStale?: () => void;
  navigate?: NavigateFn;
}) {
  const { token } = useAuth();
  const { kcs } = useKcs();
  const can = useCan();
  // Yêu cầu nhập kho KCS tạo nằm ở màn Kho: người có "Tạo yêu cầu" mở ở tab Yêu cầu, thủ kho mở ở
  // "Phiếu từ yêu cầu". Không có quyền nào ở Kho thì mã chỉ hiện chữ.
  const coTabDeNghi = can("kho", "request");
  const coTabYeuCau = can("kho", "create") || can("kho", "view_stock");
  const moYeuCauKho = navigate && (coTabDeNghi || coTabYeuCau)
    ? (id: number) => navigate("kho-main", { khoOpenRequest: { id, view: coTabDeNghi ? "denghi" : "yeucau" } })
    : undefined;
  const [lsxId, setLsxId] = useState<number | null>(null);

  // ---- Danh sách lệnh --------------------------------------------------------------------
  const [tim, setTim] = useState("");
  const timCham = useDebounced(tim.trim());
  const [daDong, setDaDong] = useState(false);
  const [trang, setTrang] = useState(1);
  const [lenh, setLenh] = useState<SxKcsLenhList | null>(null);
  const [lenhLoading, setLenhLoading] = useState(true);
  const [lenhLoi, setLenhLoi] = useState<string | null>(null);
  const [lenhTick, setLenhTick] = useState(0);

  useEffect(() => { setTrang(1); }, [timCham, daDong]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLenhLoading(true);
    api.sanXuat.kcsLenh(token, { tim: timCham || undefined, trang, daDong })
      .then((r) => { if (alive) { setLenh(r); setLenhLoi(null); } })
      .catch((e) => { if (alive) setLenhLoi(e instanceof ApiError ? e.message : "Không tải được danh sách lệnh."); })
      .finally(() => { if (alive) setLenhLoading(false); });
    return () => { alive = false; };
  }, [token, timCham, trang, daDong, lenhTick, eventTick]);

  // ---- Báo cáo -----------------------------------------------------------------------------
  const [filters, setFilters] = useState<KcsDashFilters>(KCS_DASH_FILTERS_RONG);
  const [congDoanOpts, setCongDoanOpts] = useState<SxKcsCongDoanLoc[]>([]);
  useEffect(() => {
    if (!token) return;
    api.sanXuat.kcsCongDoanLoc(token).then((r) => setCongDoanOpts(r.items)).catch(() => setCongDoanOpts([]));
  }, [token]);

  const [baoCao, setBaoCao] = useState<SxKcsBaoCao | null>(null);
  const [baoCaoLoading, setBaoCaoLoading] = useState(true);
  const [baoCaoError, setBaoCaoError] = useState<string | null>(null);
  const [baoCaoTick, setBaoCaoTick] = useState(0);
  const tuKhoaCham = useDebounced(filters.tuKhoa.trim());
  useEffect(() => {
    if (!token) return;
    let alive = true;
    setBaoCaoLoading(true);
    setBaoCaoError(null);
    api.sanXuat.baoCaoKcs(token, {
      tu: filters.tu || null,
      den: filters.den || null,
      tu_khoa: tuKhoaCham || null,
      cong_doan_id: filters.congDoanId,
    })
      .then((r) => { if (alive) { setBaoCao(r); setBaoCaoLoading(false); } })
      .catch((e) => {
        if (!alive) return;
        setBaoCaoError(e instanceof ApiError ? e.message : "Không tải được báo cáo KCS.");
        setBaoCaoLoading(false);
      });
    return () => { alive = false; };
  }, [token, filters.tu, filters.den, tuKhoaCham, filters.congDoanId, baoCaoTick, eventTick]);

  function daDoi() {
    setLenhTick((k) => k + 1);
    setBaoCaoTick((k) => k + 1);
    onBadgeStale?.();
  }

  // ---- Xuất Excel (người thuộc tổ KCS — máy chủ gác cùng luật) ----------------------------
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  async function xuatExcel() {
    if (!token || exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      const url = await api.sanXuat.exportBaoCaoKcsBlobUrl(token, {
        tu: filters.tu || null,
        den: filters.den || null,
        tu_khoa: filters.tuKhoa.trim() || null,
        cong_doan_id: filters.congDoanId,
      });
      const a = document.createElement("a");
      a.href = url;
      a.download = `Bao-cao-KCS-${filters.tu || "tat-ca"}_${filters.den || "nay"}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) {
      setExportError(e instanceof ApiError ? e.message : "Không xuất được báo cáo.");
    } finally {
      setExporting(false);
    }
  }

  const lichSu = baoCao?.lich_su ?? [];

  return (
    <main className="rc kcs-page">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">KCS</h1>
          <div className="rc__spacer" />
          {kcs && lsxId == null && (
            <button type="button" className="btn btn--accent" onClick={xuatExcel} disabled={exporting}>
              {exporting ? "Đang xuất…" : "Xuất Excel"}
            </button>
          )}
        </div>
      </header>

      {lsxId != null ? (
        <KcsChuoiCongDoan lsxId={lsxId} eventTick={eventTick}
          onBack={() => setLsxId(null)} onChanged={daDoi} onMoYeuCauKho={moYeuCauKho} />
      ) : (
        <>
          {exportError && (
            <div className="banner banner--error" role="alert"><span>{exportError}</span></div>
          )}

          <section className="kcs-section">
            <h2>Lệnh sản xuất <span className="rc__count">{lenh?.tong ?? 0}</span></h2>
            <div className="kcs-lenh__loc">
              <input type="search" placeholder="Tìm mã lệnh, sản phẩm, khách hàng" value={tim}
                aria-label="Tìm lệnh" onChange={(e) => setTim(e.target.value)} />
              <label className="kcs-lenh__dong">
                <input type="checkbox" checked={daDong} onChange={(e) => setDaDong(e.target.checked)} />
                Gồm nhóm đã đóng
              </label>
            </div>
            {lenhLoi ? (
              <div className="rc__empty-state">
                <p className="rc__empty-text">Không tải được danh sách lệnh.</p>
                <p className="rc__empty-sub">{lenhLoi}</p>
                <button type="button" className="btn btn--ghost" onClick={() => setLenhTick((k) => k + 1)}>Tải lại</button>
              </div>
            ) : lenh == null ? (
              <p className="rc__empty-text">Đang tải…</p>
            ) : lenh.items.length === 0 ? (
              <div className="rc__empty-state">
                <p className="rc__empty-text">
                  {timCham ? "Không có lệnh nào khớp." : "Chưa có lệnh nào đang sản xuất."}
                </p>
              </div>
            ) : (
              <>
                <div className="rc__tablewrap">
                  <table className="rc__table kcs-table--lenh">
                    <thead>
                      <tr>
                        <th>Lệnh</th>
                        <th>Khách hàng</th>
                        <th>Nhóm</th>
                        <th className="num">Đã kiểm</th>
                        <th className="num">Lỗi</th>
                        <th className="num">Chờ gửi kho</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lenh.items.map((l) => {
                        const nt = l.nhom_trang_thai ? KCS_NHOM_TRANG_THAI[l.nhom_trang_thai] : null;
                        return (
                          <tr key={l.lsx_id} className="kcs-row--clickable" tabIndex={0}
                            onClick={() => setLsxId(l.lsx_id)}
                            onKeyDown={(e) => { if (e.key === "Enter") setLsxId(l.lsx_id); }}>
                            <td>{l.ma}<div className="rc__sub">{l.ten}</div></td>
                            <td>{l.khach ?? "—"}</td>
                            <td>
                              {l.nhom_ma ?? "—"}
                              {nt && <div className="rc__sub"><span className={`badge-sem ${nt.cls}`}>{nt.nhan}</span></div>}
                            </td>
                            <td className="num">{l.so_da_kiem}/{l.so_cong_doan} công đoạn</td>
                            <td className="num">{l.so_loi > 0 ? num(l.so_loi) : "—"}</td>
                            <td className="num">{l.cuoi && l.cuoi.con_gui_kho > 0 ? num(l.cuoi.con_gui_kho) : "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <Pager total={lenh.tong} page={lenh.trang} size={lenh.co_trang} onPage={setTrang}
                  loading={lenhLoading} unit="lệnh" />
              </>
            )}
          </section>

          <KcsDashboard
            filters={filters} onFiltersChange={setFilters} congDoanOpts={congDoanOpts}
            data={baoCao} loading={baoCaoLoading} error={baoCaoError}
          />

          <section className="kcs-section">
            <h2>Kết quả đã ghi <span className="rc__count">{lichSu.length}</span></h2>
            {baoCaoLoading && baoCao == null ? (
              <p className="rc__empty-text">Đang tải…</p>
            ) : lichSu.length === 0 ? (
              <div className="rc__empty-state">
                <p className="rc__empty-text">Chưa có lần kiểm nào{filters.tu || filters.den || filters.tuKhoa || filters.congDoanId != null ? " khớp bộ lọc" : ""}.</p>
              </div>
            ) : (
              <div className="rc__tablewrap">
                <table className="rc__table kcs-table--ketqua">
                  <thead>
                    <tr>
                      <th>Thời điểm</th>
                      <th>Lệnh · Công đoạn</th>
                      <th className="num">Đạt</th>
                      <th className="num">Lỗi</th>
                      <th>Gửi kho</th>
                      <th>Người kiểm</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lichSu.map((r) => (
                      <tr key={r.kcs_batch_id}>
                        <td>{ngayGio(r.thoi_diem ?? null)}</td>
                        <td>{r.nguon_ma} · {r.ten_cong_doan}<div className="rc__sub">{r.nguon_ten}</div></td>
                        <td className="num">{num(r.so_luong_dat)} {nhanDonVi(r.don_vi)}</td>
                        <td className="num">{num(r.so_luong_khong_dat)}</td>
                        <td>{KCS_TRANG_THAI_GUI_KHO_LABEL[r.trang_thai_gui_kho] ?? r.trang_thai_gui_kho}</td>
                        <td>{r.nguoi_ghi ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
