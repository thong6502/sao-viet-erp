// Phiếu bảo trì — sinh ra từ chính LỊCH BẢO TRÌ đã khai trên máy.
//
// Chu kỳ KHÔNG khai ở màn này: nguồn là gói trong `may_thiet_bi.fields_theo_loai.lich_bao_tri`
// (tab "Lịch bảo trì" ở màn Thiết bị & Máy móc). Nút "Sinh phiếu từ lịch" đọc chỗ đó, tính hạn kế
// tiếp rồi đẻ phiếu cho gói đã tới hạn — khai ở danh mục, thực hiện ở đây.
//
// "Quá hạn" / "Đã dời" là cờ DẪN XUẤT backend tính lúc đọc, không phải trạng thái lưu.
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { mayThietBi, type Row } from "../api/rebuildCatalog";
import {
  kyThuatMay, NHAN_DON_VI_CHU_KY, NHAN_TT_BAO_TRI, TT_BAO_TRI,
  type BaoTri, type DuKien,
} from "../api/kyThuatMay";
import { AnhBox, NhatKyPhieu, PhanTrang, fmtNgay, homNay } from "./KyThuatMayChung";
import { LichBaoTri } from "./LichBaoTri";
import "./rebuild-catalog.css";
import "./ky-thuat-may.css";

const SIZE = 20;

/** Ngày cuối của tháng `yyyy-mm` — cận phải khi lọc theo tháng. */
function cuoiThang(thang: string): string {
  const [n, t] = thang.split("-").map(Number);
  return `${thang}-${String(new Date(n, t, 0).getDate()).padStart(2, "0")}`;
}

function chuKyChu(p: BaoTri): string {
  if (!p.chu_ky_so) return p.loai === "dot_xuat" ? "Đột xuất" : "—";
  return `mỗi ${Number(p.chu_ky_so)} ${NHAN_DON_VI_CHU_KY[p.chu_ky_don_vi ?? ""] ?? p.chu_ky_don_vi ?? ""}`;
}

export function PhieuBaoTriPage() {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can("ky_thuat_may", "update");
  const taoDuoc = can("ky_thuat_may", "create");

  const [rows, setRows] = useState<BaoTri[]>([]);
  const [dem, setDem] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [thangLoc, setThangLoc] = useState("");   // "" = mọi tháng
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  // Mặc định là VIỆC CẦN LÀM, không phải "tất cả": phiếu tích lại theo tháng, mở ra thấy cả đống
  // phiếu đã xong rồi phải cuộn tìm việc của hôm nay là sai ngay từ màn đầu.
  const [tab, setTab] = useState<string>("can_lam");
  const [mo, setMo] = useState<BaoTri | "new" | null>(null);
  const [may, setMay] = useState<Row[]>([]);
  // Mặc định mở ra là LỊCH: câu hỏi đầu tiên của thợ luôn là "hôm nay/tuần này phải làm gì", không
  // phải "có bao nhiêu phiếu". Bảng giữ lại cho việc tìm kiếm + lọc theo tab.
  const [xem, setXem] = useState<"lich" | "bang">("lich");
  const [thang, setThang] = useState(() => new Date());
  const [lichTick, setLichTick] = useState(0);   // đổi ⇒ lịch nạp lại (sau khi tạo/sửa/xoá phiếu)
  const [duKienMo, setDuKienMo] = useState<DuKien | null>(null);

  // Lọc + tìm kiếm + phân trang đều gửi LÊN SERVER. Lọc trên mảng đã tải chỉ lọc được trang đang
  // xem, mà con số trên tab thì đếm ở DB ⇒ hai chỗ nói hai kiểu.
  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    kyThuatMay.listBaoTri(token, {
      q: q.trim() || undefined,
      trang_thai: tab === "all" ? undefined : tab,
      tu: thangLoc ? `${thangLoc}-01` : undefined,
      den: thangLoc ? cuoiThang(thangLoc) : undefined,
      page,
      size: SIZE,
    })
      .then((r) => { setRows(r.items); setDem(r.dem ?? {}); setTotal(r.total); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
  }, [token, q, tab, thangLoc, page]);

  useEffect(load, [load]);
  useEffect(() => {
    if (!token) return;
    mayThietBi.list(token).then((r) => setMay(r.items)).catch(() => setMay([]));
  }, [token]);

  // `rows` giờ CHÍNH LÀ trang server trả về — không lọc lại lần nữa ở đây.
  const hien = rows;

  // Số trên tab: đếm ở DB trên TOÀN BỘ bảng (`dem`), không phải đếm trang đang xem.
  const soCanLam = dem.cho_thuc_hien ?? 0;
  const tongTatCa = soCanLam + (dem.hoan_thanh ?? 0);
  // "Quá hạn" không suy được từ `dem` (nó phụ thuộc ngày) — lấy `total` khi đang đứng ở chính tab đó,
  // còn lại để backend trả về ở lần bấm sau. Thà không hiện số còn hơn hiện số sai.
  const soQuaHan = tab === "qua_han" ? total : null;

  // Đổi bộ lọc thì về trang 1: đứng ở trang 5 rồi lọc còn 2 trang là bảng trống trơn không rõ vì sao.
  const doiLoc = (fn: () => void) => { fn(); setPage(1); };

  return (
    <div className="rc ktm">
      <div className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Phiếu bảo trì</h1>
          <span className="rc__count">{tongTatCa} phiếu</span>
          {soQuaHan != null && soQuaHan > 0 && (
            <span className="ktm-chip ktm-chip--canh-bao">
              <Icon name="alert" size={13} /> {soQuaHan} quá hạn
            </span>
          )}
        </div>
        <p className="rc__sub">
          Bảo trì định kỳ theo lịch đã khai trên từng máy, và bảo trì đột xuất.
          <strong> Phải có ảnh chứng thực mới xác nhận hoàn thành</strong>; dời lịch thì bắt buộc ghi lý do.
        </p>
      </div>

      <div className="rc__unified-bar">
        {/* Chuyển chế độ xem đứng ĐẦU thanh: nó đổi cả màn hình bên dưới, nấp ở góc phải thì
            người ta không tìm ra. */}
        <div className="ktm-xem" role="group" aria-label="Chế độ xem">
          <button type="button" className={`ktm-xem__nut${xem === "lich" ? " is-active" : ""}`}
            onClick={() => setXem("lich")}>
            <Icon name="calendar" size={14} /> Lịch
          </button>
          <button type="button" className={`ktm-xem__nut${xem === "bang" ? " is-active" : ""}`}
            onClick={() => setXem("bang")}>
            <Icon name="table" size={14} /> Bảng
          </button>
        </div>
        <div className="rc__unified-right" style={{ marginLeft: "auto" }}>
          {xem === "bang" && (
            <>
              <div className="rc__search-wrapper">
                <Icon name="search" size={15} />
                <input className="rc__search" placeholder="Tìm mã phiếu, máy, gói bảo trì…"
                  value={q} onChange={(e) => doiLoc(() => setQ(e.target.value))} />
              </div>
              {/* Lọc theo tháng — với ~400 phiếu/năm thì "xem tất" không còn là câu hỏi có ích. */}
              <div className="ktm-thangloc-wrap">
                <input className="rc-input ktm-thangloc" type="month" value={thangLoc}
                  title="Lọc theo tháng kế hoạch"
                  onChange={(e) => doiLoc(() => setThangLoc(e.target.value))} />
                {thangLoc && (
                  <button type="button" className="ktm-thangloc-x" title="Xoá lọc tháng"
                    onClick={() => doiLoc(() => setThangLoc(""))}>
                    <Icon name="x" size={13} />
                  </button>
                )}
              </div>
            </>
          )}
          {/* Chỉ còn MỘT cách tạo phiếu định kỳ: bấm ô kỳ dự kiến trên màn Lịch. Nút "Sinh phiếu
              từ lịch" (quét mọi máy, đẻ hàng loạt) đã gỡ 12/08/2026 — một cú bấm ra 41 phiếu không
              ai đặt hàng. Nút dưới đây chỉ để lập phiếu ĐỘT XUẤT. */}
          {taoDuoc && (
            <Button variant="accent" onClick={() => setMo("new")}>
              <Icon name="plus" size={15} /> Tạo phiếu đột xuất
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" onClick={load}>Tải lại</button>
        </div>
      )}

      {xem === "lich" ? (
        <LichBaoTri
          thang={thang}
          nap={lichTick}
          onDoiThang={setThang}
          onMoPhieu={(p) => setMo(p)}
          onTaoTuDuKien={(d) => setDuKienMo(d)}
        />
      ) : (
        <>
      <div className="rc__tabs">
        <button className={`rc__tab${tab === "can_lam" ? " is-active" : ""}`}
          onClick={() => doiLoc(() => setTab("can_lam"))}>
          Cần làm <span className="rc__tabn">{soCanLam}</span>
        </button>
        <button className={`rc__tab${tab === "all" ? " is-active" : ""}`}
          onClick={() => doiLoc(() => setTab("all"))}>
          Tất cả <span className="rc__tabn">{tongTatCa}</span>
        </button>
        {TT_BAO_TRI.map((tt) => (
          <button key={tt} className={`rc__tab${tab === tt ? " is-active" : ""}`}
            onClick={() => doiLoc(() => setTab(tt))}>
            {NHAN_TT_BAO_TRI[tt]} <span className="rc__tabn">{dem[tt] ?? 0}</span>
          </button>
        ))}
        {/* Tab dẫn xuất, lọc Ở SERVER. Số chỉ hiện khi đang đứng tại tab này — "quá hạn" phụ thuộc
            ngày nên không suy ra được từ bảng đếm theo trạng thái, mà đoán bừa thì thà đừng hiện. */}
        <button className={`rc__tab${tab === "qua_han" ? " is-active" : ""}${soQuaHan && soQuaHan > 0 ? " is-qua-han" : ""}`}
          onClick={() => doiLoc(() => setTab("qua_han"))}>
          Quá hạn {soQuaHan != null && <span className="rc__tabn">{soQuaHan}</span>}
        </button>
      </div>

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: "13%" }}>Mã phiếu</th>
              <th style={{ width: "18%" }}>Máy</th>
              <th>Gói bảo trì</th>
              <th style={{ width: "14%" }}>Ngày kế hoạch</th>
              <th style={{ width: "15%" }}>Người thực hiện</th>
              <th style={{ width: "14%" }}>Trạng thái</th>
              <th style={{ width: "10%" }} className="text-center">Ảnh</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  {Array.from({ length: 7 }).map((__, j) => (
                    <td key={j}><span className="rc-skel" style={{ width: "70%" }} /></td>
                  ))}
                </tr>
              ))
            ) : hien.length === 0 ? (
              <tr>
                <td colSpan={7} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <p className="rc__empty-text">
                      {tongTatCa === 0
                        ? "Chưa có phiếu nào. Chuyển sang chế độ Lịch: các kỳ bảo trì sắp tới hiện mờ ở đúng ngày của nó, bấm vào là tạo phiếu."
                        : "Không có phiếu nào khớp bộ lọc."}
                    </p>
                    {tongTatCa === 0 ? (
                      <Button variant="ghost" onClick={() => setXem("lich")}>
                        <Icon name="calendar" size={15} /> Mở lịch bảo trì
                      </Button>
                    ) : (
                      <Button variant="ghost" onClick={() => doiLoc(() => { setQ(""); setTab("all"); })}>
                        Xoá bộ lọc
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : hien.map((r) => {
              const xong = (r.hang_muc ?? []).filter((h) => h.xong).length;
              const tong = (r.hang_muc ?? []).length;
              const pct = tong > 0 ? Math.round((xong / tong) * 100) : 0;
              return (
                <tr key={r.id} className="rc__row" onClick={() => setMo(r)}>
                  <td className="rc__mono rc__nowrap">
                    <span className="rc__code-badge">{r.ma}</span>
                    {r.loai === "dot_xuat" ? (
                      <span className="ktm-tag-dotxuat"><Icon name="zap" size={11} /> Đột xuất</span>
                    ) : (
                      <div className="ktm-phu">{chuKyChu(r)}</div>
                    )}
                  </td>
                  <td className="rc__name">
                    <span className="ktm-may-badge">{r.may_ma ?? "—"}</span>
                    <div className="ktm-phu">{r.may_ten ?? ""}</div>
                  </td>
                  <td>
                    <strong className="ktm-goi-title">{r.goi_ten ?? (r.loai === "dot_xuat" ? "Bảo trì đột xuất" : "—")}</strong>
                    {tong > 0 ? (
                      <div className="ktm-progress-wrap" title={`${xong}/${tong} việc checklist đã hoàn thành`}>
                        <div className="ktm-progress-bar">
                          <div
                            className={`ktm-progress-fill${pct === 100 ? " is-full" : ""}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="ktm-progress-text">{xong}/{tong} ({pct}%)</span>
                      </div>
                    ) : (
                      <div className="ktm-phu-sub">Không có checklist</div>
                    )}
                  </td>
                  <td className="rc__nowrap">
                    <div className="ktm-ngay-kh">{fmtNgay(r.ngay_ke_hoach)}</div>
                    {r.da_doi && (
                      <div className="ktm-doi-chip" title={`Ngày kế hoạch ban đầu: ${fmtNgay(r.ngay_ke_hoach_goc)}`}>
                        <Icon name="history" size={12} /> Dời từ {fmtNgay(r.ngay_ke_hoach_goc)}
                      </div>
                    )}
                  </td>
                  <td>
                    {r.nguoi_thuc_hien ? (
                      <span className="ktm-user-pill">
                        <Icon name="users" size={13} /> {r.nguoi_thuc_hien}
                      </span>
                    ) : (
                      <span className="ktm-phu-cho">— Chờ làm</span>
                    )}
                  </td>
                  <td>
                    {r.qua_han ? (
                      <span className="ktm-badge ktm-badge--tt-qua_han">
                        <Icon name="alert" size={12} /> Quá hạn
                      </span>
                    ) : r.trang_thai === "hoan_thanh" ? (
                      <span className="ktm-badge ktm-badge--tt-hoan_thanh">
                        <Icon name="check" size={12} /> Hoàn thành
                      </span>
                    ) : (
                      <span className="ktm-badge ktm-badge--tt-cho_thuc_hien">
                        <Icon name="clock" size={12} /> Chờ thực hiện
                      </span>
                    )}
                  </td>
                  <td className="text-center rc__nowrap">
                    {r.so_anh > 0 ? (
                      <span className="ktm-anhchip is-du" title={`${r.so_anh} ảnh minh chứng đã tải`}>
                        <Icon name="camera" size={12} /> {r.so_anh} ảnh
                      </span>
                    ) : (
                      <span className="ktm-anhchip is-thieu" title="Cần có ít nhất 1 ảnh chứng thực mới xác nhận hoàn thành phiếu">
                        <Icon name="camera" size={12} /> 0 ảnh
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <PhanTrang page={page} size={SIZE} total={total} onDoi={setPage} />
        </>
      )}

      {mo && (
        <BaoTriDrawer
          phieu={mo === "new" ? null : mo}
          may={may}
          suaDuoc={suaDuoc}
          onClose={() => setMo(null)}
          onSaved={(p) => { load(); setLichTick((t) => t + 1); setMo(p); }}
        />
      )}

      {duKienMo && (
        <XacNhanTaoTuDuKien
          duKien={duKienMo}
          onClose={() => setDuKienMo(null)}
          onCreated={(p) => {
            load();
            setLichTick((t) => t + 1);
            setDuKienMo(null);
            setMo(p);          // mở luôn phiếu vừa tạo: bấm ô lịch là để LÀM việc đó, không phải để ngắm
          }}
        />
      )}
    </div>
  );
}

/** Bấm một ô DỰ KIẾN trên lịch → xác nhận rồi tạo phiếu thật cho đúng gói, đúng ngày đó.
 *
 * Hỏi một nhịp chứ không tạo ngay: ô dự kiến nằm sát ô phiếu thật trên cùng một lưới, bấm nhầm là
 * đẻ phiếu mà không ai chủ ý. */
function XacNhanTaoTuDuKien({ duKien, onClose, onCreated }: {
  duKien: DuKien;
  onClose: () => void;
  onCreated: (p: BaoTri) => void;
}) {
  const { token } = useAuth();
  const [dang, setDang] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const tao = async () => {
    if (!token) return;
    setDang(true);
    setLoi(null);
    try {
      const p = await kyThuatMay.createBaoTri(token, {
        may_id: duKien.may_id,
        goi_id: duKien.goi_id,
        loai: "dinh_ky",
        ngay_ke_hoach: duKien.ngay,
      });
      onCreated(p);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không tạo được phiếu.");
      setDang(false);
    }
  };

  return (
    <ConfirmDialog
      open
      title={
        <div className="ktm-dialog-title">
          <Icon name="calendar" size={18} />
          <span>Tạo phiếu bảo trì cho kỳ này?</span>
        </div>
      }
      confirmLabel="Tạo phiếu ngay"
      busy={dang}
      error={loi}
      onConfirm={tao}
      onCancel={onClose}
    >
      <div className="ktm-dukien-card">
        <div className="ktm-dukien-card__head">
          <span className="ktm-may-badge">{duKien.may_ma}</span>
          <strong className="ktm-dukien-card__goi">{duKien.goi_ten ?? "Bảo trì định kỳ"}</strong>
        </div>
        {duKien.may_ten && <p className="ktm-dukien-card__mayten">{duKien.may_ten}</p>}

        <div className="ktm-dukien-card__chips">
          <span className="ktm-meta-chip">
            <Icon name="calendar" size={12} /> Kế hoạch: <strong>{fmtNgay(duKien.ngay)}</strong>
          </span>
          {duKien.chu_ky_so && (
            <span className="ktm-meta-chip">
              <Icon name="refresh" size={12} /> Mỗi {duKien.chu_ky_so} {NHAN_DON_VI_CHU_KY[duKien.chu_ky_don_vi ?? ""] ?? duKien.chu_ky_don_vi}
            </span>
          )}
        </div>

        <p className="ktm-dukien-card__hint">
          ⚡ Tất cả hạng mục công việc trong gói sẽ được chép tự động sang phiếu mới và đưa vào danh sách <strong>Chờ thực hiện</strong>.
        </p>
      </div>
    </ConfirmDialog>
  );
}

function BaoTriDrawer({ phieu, may, suaDuoc, onClose, onSaved }: {
  phieu: BaoTri | null;
  may: Row[];
  suaDuoc: boolean;
  onClose: () => void;
  onSaved: (p: BaoTri) => void;
}) {
  const { token } = useAuth();
  const [hienTai, setHienTai] = useState<BaoTri | null>(phieu);
  const [loi, setLoi] = useState<string | null>(null);
  const [anhTick, setAnhTick] = useState(0);
  const [tab, setTab] = useState<"chi-tiet" | "lich-su">("chi-tiet");

  // form tạo mới / sửa nhẹ
  const [mayId, setMayId] = useState(phieu ? String(phieu.may_id) : "");
  const [goiTen, setGoiTen] = useState(phieu?.goi_ten ?? "");
  const [ngay, setNgay] = useState(phieu?.ngay_ke_hoach ?? homNay());
  const [ghiChu, setGhiChu] = useState(phieu?.ghi_chu ?? "");
  const [luu, setLuu] = useState(false);

  // dời lịch
  const [moDoi, setMoDoi] = useState(false);
  const [ngayMoi, setNgayMoi] = useState("");
  const [lyDo, setLyDo] = useState("");

  // ngày làm THẬT khi xác nhận xong (thợ làm thứ Bảy, thứ Hai mới vào bấm)
  const [ngayXong, setNgayXong] = useState(homNay());

  const xong = hienTai?.trang_thai === "hoan_thanh";
  const khoaSua = !suaDuoc || xong;

  useEffect(() => {
    if (!token || !hienTai || anhTick === 0) return;
    kyThuatMay.listBaoTri(token, { may_id: hienTai.may_id })
      .then((r) => {
        const moi = r.items.find((x) => x.id === hienTai.id);
        if (moi) setHienTai(moi);
      })
      .catch(() => {});
  }, [anhTick, token, hienTai?.id]);

  const luuPhieu = async () => {
    if (!token) return;
    setLoi(null);
    setLuu(true);
    try {
      if (hienTai) {
        const p = await kyThuatMay.updateBaoTri(token, hienTai.id, {
          goi_ten: goiTen.trim() || null,
          ghi_chu: ghiChu.trim() || null,
        });
        setHienTai(p);
        onSaved(p);
      } else {
        if (!mayId) { setLoi("Chưa chọn máy."); setLuu(false); return; }
        const p = await kyThuatMay.createBaoTri(token, {
          may_id: Number(mayId),
          loai: "dot_xuat",
          goi_ten: goiTen.trim() || null,
          ngay_ke_hoach: ngay,
          ghi_chu: ghiChu.trim() || null,
        });
        setHienTai(p);
        onSaved(p);
      }
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Lưu không thành công.");
    } finally {
      setLuu(false);
    }
  };

  const tick = async (hangMucId: string | null | undefined, giaTri: boolean) => {
    if (!token || !hienTai || !hangMucId) return;
    try {
      const p = await kyThuatMay.tickHangMuc(token, hienTai.id, hangMucId, giaTri);
      setHienTai(p);
      onSaved(p);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không lưu được checklist.");
    }
  };

  const doiLich = async () => {
    if (!token || !hienTai) return;
    if (!ngayMoi) { setLoi("Chưa chọn ngày mới."); return; }
    if (!lyDo.trim()) { setLoi("Phải ghi lý do dời lịch."); return; }
    try {
      const p = await kyThuatMay.doiLich(token, hienTai.id, ngayMoi, lyDo.trim());
      setHienTai(p);
      onSaved(p);
      setMoDoi(false);
      setLyDo("");
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không dời được lịch.");
    }
  };

  const doiTrangThai = async (tt: string) => {
    if (!token || !hienTai) return;
    setLoi(null);
    try {
      const p = await kyThuatMay.trangThaiBaoTri(
        token, hienTai.id, tt, tt === "hoan_thanh" ? ngayXong : null,
      );
      setHienTai(p);
      onSaved(p);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không đổi được trạng thái.");
    }
  };

  const hangMuc = hienTai?.hang_muc ?? [];
  const soXong = hangMuc.filter((h) => h.xong).length;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer ktm-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head ktm-drawer-hero">
          <div>
            <div className="ktm-drawer-hero__status">
              {hienTai ? (
                hienTai.qua_han ? (
                  <span className="ktm-badge ktm-badge--tt-qua_han">
                    <Icon name="alert" size={12} /> Quá hạn
                  </span>
                ) : (
                  <span className={`ktm-badge ktm-badge--tt-${hienTai.trang_thai}`}>
                    {hienTai.trang_thai === "hoan_thanh" ? (
                      <Icon name="check" size={12} />
                    ) : (
                      <Icon name="clock" size={12} />
                    )}
                    {NHAN_TT_BAO_TRI[hienTai.trang_thai] ?? hienTai.trang_thai}
                  </span>
                )
              ) : (
                <span className="ktm-badge ktm-tag-dotxuat">
                  <Icon name="zap" size={12} /> Lập phiếu đột xuất
                </span>
              )}
            </div>

            <h2 className="rc-drawer__title ktm-drawer-hero__title">
              {hienTai ? hienTai.ma : "Phiếu bảo trì mới"}
            </h2>

            {hienTai && (
              <div className="ktm-drawer-hero__meta">
                <span className="ktm-may-badge">{hienTai.may_ma}</span>
                {hienTai.may_ten && <span className="ktm-drawer-hero__mayten">{hienTai.may_ten}</span>}
                <span className="ktm-meta-chip">
                  <Icon name="calendar" size={12} /> Kế hoạch: <strong>{fmtNgay(hienTai.ngay_ke_hoach)}</strong>
                </span>
                <span className="ktm-meta-chip">
                  {hienTai.loai === "dot_xuat" ? (
                    <><Icon name="zap" size={11} /> Đột xuất</>
                  ) : (
                    <><Icon name="refresh" size={11} /> {chuKyChu(hienTai)}</>
                  )}
                </span>
              </div>
            )}
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        {/* Tab chỉ hiện khi phiếu ĐÃ TỒN TẠI: phiếu mới chưa có gì để kể lại. */}
        {hienTai && (
          <div className="ktm-tab">
            <button type="button" className={`ktm-tab__nut${tab === "chi-tiet" ? " is-active" : ""}`}
              onClick={() => setTab("chi-tiet")}>Chi tiết</button>
            <button type="button" className={`ktm-tab__nut${tab === "lich-su" ? " is-active" : ""}`}
              onClick={() => setTab("lich-su")}>Lịch sử thao tác</button>
          </div>
        )}

        <div className="rc-drawer__body">
          {hienTai && tab === "lich-su" ? (
            <NhatKyPhieu loai="ky_thuat_bao_tri" phieuId={hienTai.id} />
          ) : (
          <>
          {loi && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{loi}</div>}
          {xong && (
            <div className="ktm-thongbao ktm-thongbao--xong">
              <Icon name="check" size={14} /> Hoàn thành ngày {fmtNgay(hienTai?.ngay_hoan_thanh)} —
              mốc này là gốc để tính kỳ bảo trì kế tiếp.
            </div>
          )}
          {hienTai?.da_doi && (
            <div className="ktm-thongbao">
              <Icon name="history" size={14} /> Đã dời từ {fmtNgay(hienTai.ngay_ke_hoach_goc)} — lý do:{" "}
              {hienTai.ly_do_doi}
            </div>
          )}

          {!hienTai && (
            <div className="ktm-form-banner">
              <Icon name="zap" size={16} />
              <div>
                <strong>Lập phiếu bảo trì đột xuất</strong>
                <p>Khởi tạo khi thiết bị gặp sự cố, kiểm tra đột xuất hoặc thuê đơn vị ngoài bảo dưỡng. Phiếu sẽ tự động vào danh sách chờ thực hiện.</p>
              </div>
            </div>
          )}

          <section className="rc-sec">
            <div className="rc-sec__title">Thông tin phiếu</div>
            <div className="rc-grid">
              {!hienTai && (
                <>
                  <label className="rc-field">
                    <span className="rc-field__label">Máy cần bảo trì *</span>
                    <select className="rc-input" value={mayId} onChange={(e) => setMayId(e.target.value)}>
                      <option value="">— Chọn máy thiết bị —</option>
                      {may.map((m) => (
                        <option key={m.id} value={m.id}>[{String(m.ma)}] · {String(m.ten)}</option>
                      ))}
                    </select>
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Ngày kế hoạch *</span>
                    <input className="rc-input" type="date" value={ngay}
                      onChange={(e) => setNgay(e.target.value)} />
                  </label>
                </>
              )}

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Nội dung / gói bảo trì {!hienTai && "*"}</span>
                <input className="rc-input" value={goiTen} disabled={khoaSua}
                  placeholder="vd: Kiểm tra cảm biến nhiệt · Thay dao bế mòn · Bảo trì đột xuất"
                  onChange={(e) => setGoiTen(e.target.value)} />
                {hienTai?.goi_id && (
                  <span className="ktm-hint">
                    Sinh từ gói trong lịch bảo trì của máy — sửa tên ở đây chỉ đổi trên phiếu này.
                  </span>
                )}
              </label>

              {/* KHÔNG có ô "người nhận việc": không có bước nhận việc nào cả. Ai bấm "Xác nhận đã
                  bảo trì xong" thì chính người đó là người làm, và tên chỉ hiện SAU khi xong. */}
              {xong && hienTai?.nguoi_thuc_hien && (
                <div className="rc-field">
                  <span className="rc-field__label">Người làm</span>
                  <div className="ktm-nguoinhan">
                    <Icon name="users" size={14} /> {hienTai.nguoi_thuc_hien}
                  </div>
                </div>
              )}

              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Ghi chú kỹ thuật</span>
                <input className="rc-input" value={ghiChu} disabled={khoaSua}
                  placeholder="Thuê hãng ngoài thì ghi ở đây — vd: KT hãng Bobst VN sang xử lý lúc 14h"
                  onChange={(e) => setGhiChu(e.target.value)} />
              </label>
            </div>

            {!khoaSua && (
              <div className="ktm-actions">
                <Button variant="accent" onClick={luuPhieu} disabled={luu}>
                  <Icon name={hienTai ? "pencil" : "plus"} size={14} />
                  {luu ? "Đang lưu…" : hienTai ? "Lưu thay đổi" : "Tạo phiếu đột xuất"}
                </Button>
                {!hienTai ? (
                  <button type="button" className="btn btn--ghost" onClick={onClose}>
                    Hủy
                  </button>
                ) : (
                  <button type="button" className="rc__link-btn" onClick={() => { setMoDoi((v) => !v); setNgayMoi(hienTai.ngay_ke_hoach); }}>
                    <Icon name="calendar" size={14} /> Dời lịch
                  </button>
                )}
              </div>
            )}

            {moDoi && !khoaSua && (
              <div className="ktm-doilich">
                <label className="rc-field">
                  <span className="rc-field__label">Ngày mới</span>
                  <input className="rc-input" type="date" value={ngayMoi}
                    onChange={(e) => setNgayMoi(e.target.value)} />
                </label>
                <label className="rc-field">
                  <span className="rc-field__label">Lý do *</span>
                  <input className="rc-input" value={lyDo} placeholder="vd: chờ dao bế về"
                    onChange={(e) => setLyDo(e.target.value)} />
                </label>
                <Button variant="accent" onClick={doiLich}>Xác nhận dời</Button>
              </div>
            )}
          </section>

          {hangMuc.length > 0 && (
            <section className="rc-sec">
              <div className="rc-sec__title ktm-check-head">
                <span>Hạng mục bảo trì</span>
                <div className="ktm-progress-wrap">
                  <div className="ktm-progress-bar" style={{ width: "110px" }}>
                    <div
                      className={`ktm-progress-fill${soXong === hangMuc.length ? " is-full" : ""}`}
                      style={{ width: `${hangMuc.length > 0 ? Math.round((soXong / hangMuc.length) * 100) : 0}%` }}
                    />
                  </div>
                  <span className="ktm-progress-text">{soXong}/{hangMuc.length} ({hangMuc.length > 0 ? Math.round((soXong / hangMuc.length) * 100) : 0}%)</span>
                </div>
              </div>

              <div className="ktm-check-grid">
                {hangMuc.map((h, i) => (
                  <label key={h.id ?? i} className={`ktm-check-card${h.xong ? " is-checked" : ""}`}>
                    <input
                      type="checkbox"
                      checked={h.xong}
                      disabled={khoaSua || !h.id}
                      onChange={(e) => tick(h.id, e.target.checked)}
                    />
                    <span className="ktm-check-card__box">
                      <Icon name="check" size={13} />
                    </span>
                    <span className="ktm-check-card__title">{h.ten}</span>
                    {h.xong && <span className="ktm-check-card__status">✓ Đã làm</span>}
                  </label>
                ))}
              </div>
            </section>
          )}

          {hienTai && (
            <>
              <AnhBox loai="bao_tri" phieuId={hienTai.id} giaiDoan="truoc"
                tieuDe="Ảnh hiện trạng trước bảo trì" khoa={khoaSua}
                onChanged={() => setAnhTick((t) => t + 1)} />

              <AnhBox loai="bao_tri" phieuId={hienTai.id} giaiDoan="sau"
                tieuDe="Ảnh chứng thực sau bảo trì" batBuoc khoa={xong}
                moTa="Bắt buộc để xác nhận hoàn thành."
                onChanged={() => setAnhTick((t) => t + 1)} />

              {/* Phiếu đã xong: một lối lùi DUY NHẤT để sửa phiếu ký nhầm — mở lại về hàng chờ. */}
              {suaDuoc && xong && (
                <div className="ktm-actions">
                  <button type="button" className="rc__link-btn"
                    onClick={() => doiTrangThai("cho_thuc_hien")}>
                    <Icon name="history" size={14} /> Mở lại phiếu (ghi nhầm)
                  </button>
                </div>
              )}

              {suaDuoc && !xong && (
                <section className={`ktm-gatekeeper${hienTai.co_anh_sau ? " is-ready" : ""}`}>
                  <div className="ktm-gatekeeper__head">
                    <Icon name="shield" size={16} />
                    <span className="ktm-gatekeeper__title">Điều kiện xác nhận hoàn thành</span>
                  </div>

                  <div className="ktm-gatekeeper__conds">
                    <div className={`ktm-gate-cond${soXong === hangMuc.length && hangMuc.length > 0 ? " is-pass" : ""}`}>
                      <Icon name={soXong === hangMuc.length && hangMuc.length > 0 ? "check" : "clock"} size={13} />
                      <span>Checklist công việc: {soXong}/{hangMuc.length} hạng mục</span>
                    </div>
                    <div className={`ktm-gate-cond${hienTai.co_anh_sau ? " is-pass" : " is-fail"}`}>
                      <Icon name={hienTai.co_anh_sau ? "check" : "alert"} size={13} />
                      <span>Ảnh chứng thực sau bảo trì: {hienTai.co_anh_sau ? "Đã có ảnh minh chứng" : "Chưa có ảnh (Bắt buộc)"}</span>
                    </div>
                  </div>

                  <div className="ktm-gatekeeper__action">
                    <label className="rc-field ktm-ngayxong">
                      <span className="rc-field__label">Ngày hoàn thành</span>
                      <input className="rc-input" type="date" value={ngayXong} max={homNay()}
                        onChange={(e) => setNgayXong(e.target.value)} />
                    </label>
                    <button type="button" className="ktm-xacnhan__nut"
                      disabled={!hienTai.co_anh_sau}
                      onClick={() => doiTrangThai("hoan_thanh")}>
                      <Icon name="check" size={16} /> Xác nhận đã bảo trì xong
                    </button>
                  </div>
                </section>
              )}
            </>
          )}
          </>
          )}
        </div>
      </aside>
    </div>
  );
}
