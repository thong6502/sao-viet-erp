// KCS kiêm nhiệm (mg 0250) — trang list-first cho tổ có cờ `la_kcs` (Task 9, đọc
// docs/design-kcs-kiem-nhiem-ui.md mục 1 trước khi sửa cấu trúc).
//
// Nguồn dữ liệu — hai khối KHÔNG cùng một nguồn:
//   - "Chờ KCS" + "Kết quả đã ghi" (routing): `workItems(teamId, "kcs")` trả MỌI bước la_kcs=true
//     của CHÍNH tổ này (kể cả đã kiểm xong — repo không lọc theo trang_thai), rồi gọi `kcsChiTiet`
//     cho từng việc để lấy batch[] — "Còn chờ" = da_ban_giao_xac_nhan (bàn giao CONFIRMED, số BE
//     dùng để chặn ghi vượt) − tổng so_luong_nhan. KHÔNG dùng `so_luong_vao` (kế hoạch tĩnh lúc phát
//     hành LSX) — nó không tự đồng bộ khi bàn giao chạy dần từng đợt, gây "Còn chờ" ảo rồi 400 khi
//     lưu.
//   - "Kết quả đã ghi" (đột xuất): KHÔNG có endpoint liệt kê lịch sử đột xuất theo tổ KCS, vì việc
//     bị kiểm thuộc tổ KHÁC (`kcs_department_id` = tổ này, nhưng `cong_viec_id` không nằm trong
//     `workItems(teamId, "kcs")`). Mỗi lượt lưu đột xuất được ghim vào state PHIÊN NÀY qua
//     `onSaved` — mất khi tải lại trang. Xem `docs/design-kcs-kiem-nhiem-ui.md` mục 7 (việc Task 10)
//     và mục Concerns của report Task 9 — cần endpoint mới nếu muốn lịch sử đột xuất bền vững.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError, api,
  type CongDoanLite, type SxKcsBatchChiTiet, type SxKcsChiTiet, type SxWorkItem,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { num, ngayGio } from "../keHoachSxShared";
import { KcsDashboard, KCS_DASH_FILTERS_RONG, type KcsDashFilters } from "./KcsDashboard";
import { KCS_TRANG_THAI_GUI_KHO_LABEL, KcsResultDrawer, type KcsSavedRow } from "./KcsResultDrawer";
import "../rebuild-catalog.css";
import "./kcs.css";

interface ChoRow {
  item: SxWorkItem;
  daBanGiao: number;
  daKiem: number;
  conCho: number;
}

interface KetQuaRow {
  key: string;
  luc: string;
  soDat: number;
  soLoi: number;
  loai: "routing" | "dot_xuat";
  maNguon: string;
  tenNguon: string;
  tenCongDoan: string;
  /** null = không mở được drawer "xem" (đột xuất phiên này — chưa có API đọc lại chi tiết theo id). */
  view: { item: SxWorkItem; batch: SxKcsBatchChiTiet } | null;
  /** null cho dòng đột xuất-trong-phiên (không có API đọc lại — xem comment đầu file). */
  nguoiGhi: string | null;
  trangThaiGuiKho: string | null;
}

type DrawerState =
  | { mode: "ghi"; item: SxWorkItem; conCho: number }
  | { mode: "dot_xuat" }
  | { mode: "xem"; item: SxWorkItem; batch: SxKcsBatchChiTiet };

/** Ngày theo LỊCH VN (không phải lát cắt chuỗi UTC thô) — khớp `_ngay_vn()` phía backend
 *  (`kcs_bao_cao.py`) dùng để bucket KPI/biểu đồ/Excel theo ngày. `r.luc` LUÔN có offset (cột DB
 *  `bat_dau`/`ket_thuc` khai `DateTime(timezone=True)`; nhánh đột xuất dùng `toISOString()`) nên
 *  không cần nhánh xử lý "naive" như `fmtDateTime()` ở utils/format.ts (nguồn khác, có thể naive).
 *  Việt Nam không có DST nên phép này tương đương toán học với `ZoneInfo("Asia/Bangkok")` phía
 *  Python — không có rủi ro trôi giữa 2 ngôn ngữ. Batch ghi 00:00–07:00 giờ VN rơi vào NGÀY HÔM
 *  TRƯỚC theo UTC — cắt chuỗi thô (bản round 1) lệch 1 ngày với backend đúng vào khung ca đêm. */
function ngayVN(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date(iso));
}

export function ThucHienKcsPage({
  teamId, tenTo, eventTick, onBadgeStale,
}: {
  teamId: number;
  tenTo?: string;
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Vai Tổ trưởng SX (đối tượng dùng trang này hằng ngày) hiện KHÔNG có `can_export` trên module
  // `san_xuat` (seed.py — vai chỉ được cấp assign_work/record_output/handover, KHÔNG có export) —
  // router `/kcs/bao-cao/export.xlsx` gác quyền `export` nên bấm sẽ luôn 403 nếu không ẩn nút.
  // Ẩn theo RBAC thay vì để lỗi — đúng nguyên tắc "phân quyền lo ai thấy gì". Nếu muốn tổ trưởng
  // xuất được báo cáo KCS của tổ mình thì cần cấp `can_export` cho vai đó (mở rộng RBAC, NGOÀI
  // phạm vi Task 9 — xem report Concerns).
  const canExport = can("san_xuat", "export");

  const [filters, setFilters] = useState<KcsDashFilters>(KCS_DASH_FILTERS_RONG);

  // Danh sách công đoạn cho dropdown filter — fetch một lần ở đây (không fetch trùng lần thứ hai
  // trong KcsDashboard), dùng cho cả prop truyền xuống dashboard lẫn để lọc `ketQuaLoc` theo tên
  // công đoạn snapshot bên dưới.
  const [congDoanOpts, setCongDoanOpts] = useState<CongDoanLite[]>([]);
  useEffect(() => {
    if (!token) return;
    api.congDoan.list(token).then((r) => setCongDoanOpts(r.items)).catch(() => setCongDoanOpts([]));
  }, [token]);

  const [items, setItems] = useState<SxWorkItem[] | null>(null);
  const [chiTietMap, setChiTietMap] = useState<Record<number, SxKcsChiTiet>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Đếm số việc mà kcsChiTiet() lỗi. Trước đây các lỗi này bị nuốt im lặng, khiến "còn chờ" hiện
  // 0 dù thực ra chỉ là không tải được dữ liệu — không phân biệt được với hàng thật sự trống.
  // Nguồn 403 hàng loạt cũ (mặt đọc `/work-items/{id}/kcs` gác bằng cổng GHI `_gate`, đòi phải là
  // tổ trưởng đúng tổ) ĐÃ VÁ: giờ nó gác cùng phạm vi đọc với `/work-items`. Băng dưới vẫn giữ —
  // nó bắt mọi hỏng khác (mạng, 500), và im lặng khi không có việc nào lỗi.
  const [chiTietFailCount, setChiTietFailCount] = useState(0);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    api.sanXuat.workItems(token, teamId, "kcs")
      .then(async (r) => {
        let failCount = 0;
        const entries = await Promise.all(
          r.cong_viec.map((cv): Promise<[number, SxKcsChiTiet]> =>
            api.sanXuat.kcsChiTiet(token, cv.id)
              .then((ct): [number, SxKcsChiTiet] => [cv.id, ct])
              .catch((): [number, SxKcsChiTiet] => {
                failCount += 1;
                return [
                  cv.id,
                  { cong_viec_id: cv.id, la_kcs: cv.la_kcs, checklist: [], da_ban_giao_xac_nhan: 0, batch: [] },
                ];
              }),
          ),
        );
        setItems(r.cong_viec);
        setChiTietMap(Object.fromEntries(entries));
        setChiTietFailCount(failCount);
        setLoading(false);
      })
      .catch((e) => {
        setLoadError(e instanceof ApiError ? e.message : "Không tải được danh sách KCS.");
        setLoading(false);
      });
  }, [token, teamId]);

  useEffect(() => { load(); }, [load, eventTick]);

  // Kết quả đột xuất ghi trong phiên này — xem giải thích ở đầu file.
  const [dotXuatPhien, setDotXuatPhien] = useState<KcsSavedRow[]>([]);

  const choRows: ChoRow[] = useMemo(() => {
    return (items ?? [])
      .map((item) => {
        const batches = chiTietMap[item.id]?.batch ?? [];
        const daBanGiao = chiTietMap[item.id]?.da_ban_giao_xac_nhan ?? 0;
        const daKiem = batches.reduce((s, b) => s + (b.so_luong_nhan || 0), 0);
        return { item, daBanGiao, daKiem, conCho: Math.max(0, daBanGiao - daKiem) };
      })
      .filter((r) => r.conCho > 0);
  }, [items, chiTietMap]);

  const ketQuaRows: KetQuaRow[] = useMemo(() => {
    const fromRouting: KetQuaRow[] = [];
    for (const item of items ?? []) {
      const batches = chiTietMap[item.id]?.batch ?? [];
      for (const b of batches) {
        fromRouting.push({
          key: `routing-${b.id}`,
          luc: b.ket_thuc,
          soDat: b.so_luong_dat,
          soLoi: b.so_luong_khong_dat,
          loai: b.loai,
          maNguon: item.nguon_ma,
          tenNguon: item.nguon_ten,
          tenCongDoan: item.ten_cong_doan,
          view: { item, batch: b },
          nguoiGhi: b.nguoi_ghi ?? null,
          trangThaiGuiKho: b.trang_thai_gui_kho,
        });
      }
    }
    const fromDotXuat: KetQuaRow[] = dotXuatPhien.map((r) => ({
      key: `dotxuat-${r.kcsBatchId}`,
      luc: r.luc,
      soDat: r.soDat,
      soLoi: r.soLoi,
      loai: r.loai,
      maNguon: r.maNguon,
      tenNguon: r.tenNguon,
      tenCongDoan: r.tenCongDoan,
      view: null,
      nguoiGhi: null,
      trangThaiGuiKho: null,
    }));
    return [...fromRouting, ...fromDotXuat].sort((a, b) => (a.luc < b.luc ? 1 : -1));
  }, [items, chiTietMap, dotXuatPhien]);

  // Bộ lọc dashboard (tu/den/loai/congDoanId/tuKhoa) áp luôn cho bảng lịch sử — MỘT bộ filter duy
  // nhất cho KPI/biểu đồ (server-side, qua KcsDashboard) + lịch sử (client-side trên tập đã tải) +
  // Excel (server-side, qua xuatExcel) — đúng yêu cầu mục 1 của Task 10.
  const ketQuaLoc = useMemo(() => {
    const congDoanTen = filters.congDoanId != null
      ? congDoanOpts.find((c) => c.id === filters.congDoanId)?.ten ?? null
      : null;
    return ketQuaRows.filter((r) => {
      if (filters.loai && r.loai !== filters.loai) return false;
      if (filters.tuKhoa.trim()) {
        const q = filters.tuKhoa.trim().toLowerCase();
        if (!`${r.maNguon} ${r.tenNguon}`.toLowerCase().includes(q)) return false;
      }
      // So khớp theo TÊN snapshot công đoạn — cùng cách backend lọc `cong_doan_id` trong
      // kcs_bao_cao.py (`_hang_kcs_theo_scope`, Ruling 3): công đoạn neo LỎNG qua id không ổn
      // định, tên snapshot là cái duy nhất còn đúng qua thời gian.
      if (congDoanTen && r.tenCongDoan !== congDoanTen) return false;
      // r.luc LUÔN có offset (không phải "naive giờ VN" — nhầm lẫn ở round 1, xem `ngayVN()` phía
      // trên) — phải quy đổi tường minh về lịch VN, không được cắt 10 ký tự đầu của chuỗi UTC thô
      // (bản round 1 làm vậy, sai lệch 1 ngày với batch ghi trong khung giờ VN 00:00–07:00).
      const ngay = ngayVN(r.luc);
      if (filters.tu && ngay < filters.tu) return false;
      if (filters.den && ngay > filters.den) return false;
      return true;
    });
  }, [ketQuaRows, filters.loai, filters.tuKhoa, filters.congDoanId, filters.tu, filters.den, congDoanOpts]);
  const dangLocKetQua = !!filters.loai || !!filters.tuKhoa.trim() || !!filters.tu || !!filters.den || filters.congDoanId != null;

  const [drawer, setDrawer] = useState<DrawerState | null>(null);

  // Bump sau mỗi lần lưu để ép `KcsDashboard` gọi lại `bao-cao` — hiệu ứng của nó chỉ phụ thuộc
  // `filters`, không tự biết vừa có kết quả mới (khác `load()` ở trên, chỉ làm mới 2 bảng).
  const [dashRefreshKey, setDashRefreshKey] = useState(0);

  function daLuu(row: KcsSavedRow) {
    if (row.loai === "dot_xuat") setDotXuatPhien((prev) => [row, ...prev]);
    load();
    setDashRefreshKey((k) => k + 1);
    onBadgeStale?.();
  }

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
        kcs_department_id: teamId,
        tu_khoa: filters.tuKhoa || null,
        cong_doan_id: filters.congDoanId,
        loai: filters.loai,
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

  return (
    <main className="rc kcs-page">
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">KCS · {tenTo ?? "Tổ"}</h1>
          <div className="rc__spacer" />
          <button type="button" className="btn btn--ghost" onClick={() => setDrawer({ mode: "dot_xuat" })}>
            Kiểm đột xuất
          </button>
          {canExport && (
            <button type="button" className="btn btn--accent" onClick={xuatExcel} disabled={exporting}>
              {exporting ? "Đang xuất…" : "Xuất Excel"}
            </button>
          )}
        </div>
      </header>

      {exportError && (
        <div className="banner banner--error" role="alert">
          <span>{exportError}</span>
        </div>
      )}

      {chiTietFailCount > 0 && (
        <div className="banner banner--error" role="alert">
          <span>
            Không tải được chi tiết {chiTietFailCount} việc — số "còn chờ" bên dưới có thể THIẾU.{" "}
            <button type="button" className="btn btn--ghost btn--sm" onClick={load}>Tải lại</button>
          </span>
        </div>
      )}

      <KcsDashboard
        teamId={teamId} filters={filters} onFiltersChange={setFilters} refreshKey={dashRefreshKey}
        congDoanOpts={congDoanOpts}
      />

      <section className="kcs-section">
        <h2>Chờ KCS <span className="rc__count">{choRows.length}</span></h2>
        {loading ? (
          <div className="rc__tablewrap">
            <table className="rc__table kcs-table--cho">
              <tbody>
                {Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="rc-skel__row"><td colSpan={7}><span className="rc-skel" style={{ width: "70%" }} /></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : loadError ? (
          <div className="rc__empty-state">
            <p className="rc__empty-text">Không tải được danh sách.</p>
            <p className="rc__empty-sub">{loadError}</p>
            <button type="button" className="btn btn--ghost" onClick={load}>Tải lại</button>
          </div>
        ) : choRows.length === 0 ? (
          <div className="rc__empty-state">
            <p className="rc__empty-text">Không có việc nào đang chờ KCS.</p>
          </div>
        ) : (
          <div className="rc__tablewrap">
            <table className="rc__table kcs-table--cho">
              <thead>
                <tr>
                  <th>Mã đơn/LSX</th>
                  <th>Sản phẩm/Nhóm</th>
                  <th>Công đoạn</th>
                  <th className="num">Đã bàn giao</th>
                  <th className="num">Đã kiểm</th>
                  <th className="num">Còn chờ</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {choRows.map((r) => (
                  <tr key={r.item.id} className="kcs-row--clickable" onClick={() => setDrawer({ mode: "ghi", item: r.item, conCho: r.conCho })}>
                    <td>{r.item.nguon_ma}</td>
                    <td>{r.item.nguon_ten}{r.item.nhom ? ` · ${r.item.nhom}` : ""}</td>
                    <td>{r.item.ten_cong_doan}</td>
                    <td className="num">{num(r.daBanGiao)}</td>
                    <td className="num">{num(r.daKiem)}</td>
                    <td className="num">{num(r.conCho)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="btn btn--accent" onClick={() => setDrawer({ mode: "ghi", item: r.item, conCho: r.conCho })}>
                        Ghi kết quả
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="kcs-section">
        <h2>Kết quả đã ghi <span className="rc__count">{ketQuaLoc.length}</span></h2>
        {loading ? (
          <div className="rc__tablewrap">
            <table className="rc__table kcs-table--ketqua">
              <tbody>
                {Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="rc-skel__row"><td colSpan={7}><span className="rc-skel" style={{ width: "70%" }} /></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : loadError ? (
          <div className="rc__empty-state">
            <p className="rc__empty-text">Không tải được lịch sử.</p>
            <p className="rc__empty-sub">{loadError}</p>
            <button type="button" className="btn btn--ghost" onClick={load}>Tải lại</button>
          </div>
        ) : ketQuaLoc.length === 0 ? (
          <div className="rc__empty-state">
            <p className="rc__empty-text">{dangLocKetQua ? "Không có kết quả khớp bộ lọc." : "Chưa có kết quả KCS nào."}</p>
          </div>
        ) : (
          <div className="rc__tablewrap">
            <table className="rc__table kcs-table--ketqua">
              <thead>
                <tr>
                  <th>Thời điểm</th>
                  <th>Mã đơn/LSX · Công đoạn</th>
                  <th className="num">Đạt</th>
                  <th className="num">Lỗi</th>
                  <th>Loại</th>
                  <th>Trạng thái gửi kho</th>
                  <th>Người ghi</th>
                </tr>
              </thead>
              <tbody>
                {ketQuaLoc.map((r) => (
                  <tr
                    key={r.key}
                    className={r.view ? "kcs-row--clickable" : ""}
                    onClick={r.view ? () => setDrawer({ mode: "xem", item: r.view!.item, batch: r.view!.batch }) : undefined}
                  >
                    <td>{ngayGio(r.luc)}</td>
                    <td>{r.maNguon} · {r.tenCongDoan}</td>
                    <td className="num">{num(r.soDat)}</td>
                    <td className="num">{num(r.soLoi)}</td>
                    <td>
                      <span className={`badge-sem ${r.loai === "routing" ? "badge-sem--steel" : "badge-sem--plum"}`}>
                        {r.loai === "routing" ? "Routing" : "Đột xuất"}
                      </span>
                    </td>
                    <td>{r.trangThaiGuiKho ? (KCS_TRANG_THAI_GUI_KHO_LABEL[r.trangThaiGuiKho] ?? r.trangThaiGuiKho) : "—"}</td>
                    <td>{r.nguoiGhi ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {drawer?.mode === "ghi" && (
        <KcsResultDrawer
          mode="ghi" teamId={teamId} tenTo={tenTo ?? ""} item={drawer.item} conCho={drawer.conCho}
          onClose={() => setDrawer(null)} onSaved={daLuu}
        />
      )}
      {drawer?.mode === "dot_xuat" && (
        <KcsResultDrawer
          mode="dot_xuat" teamId={teamId} tenTo={tenTo ?? ""}
          onClose={() => setDrawer(null)} onSaved={daLuu}
        />
      )}
      {drawer?.mode === "xem" && (
        <KcsResultDrawer
          mode="xem" teamId={teamId} tenTo={tenTo ?? ""} item={drawer.item} batch={drawer.batch}
          onClose={() => setDrawer(null)}
        />
      )}
    </main>
  );
}
