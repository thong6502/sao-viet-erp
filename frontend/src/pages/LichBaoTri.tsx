// Lịch bảo trì — phiếu THẬT + kỳ DỰ KIẾN (chưa lưu, backend tính lúc đọc) trên cùng một tháng.
//
// Hai hình dạng cho hai loại thiết bị, cùng một dữ liệu:
//   · máy tính → lưới 7 cột, rê chuột ra thẻ thông tin;
//   · điện thoại / màn hình cảm ứng → DANH SÁCH theo ngày, chữ hiện đủ ngay trên dòng.
// Lý do tách: bản cũ ép lưới 7 cột xuống điện thoại rồi phải giấu tên gói đi cho vừa ô, còn thông
// tin phụ thì nằm hết trong tooltip hover — mà màn cảm ứng không có hover. Thợ chụp ảnh tại máy
// bằng điện thoại nên đây là màn họ mở nhiều nhất.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import {
  kyThuatMay, NHAN_DON_VI_CHU_KY, NHAN_TT_BAO_TRI, type BaoTri, type DuKien,
} from "../api/kyThuatMay";
import { BadgeBaoTri, useManHep } from "./KyThuatMayChung";

const THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const THU_DAY_DU = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];
const MAX_CELL_ITEMS = 3;
/** Bộ lọc nhớ giữa các lần mở màn — thợ phụ trách mấy máy cố định, bắt chọn lại mỗi lần là phiền. */
const LOC_KEY = "ktm.lich.loc";

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtNgayFull(isoStr: string): string {
  const [y, m, d] = isoStr.split("-");
  return `Ngày ${d} tháng ${m}, ${y}`;
}

function oCuaThang(nam: number, thang: number): Date[] {
  const dau = new Date(nam, thang, 1);
  const lui = (dau.getDay() + 6) % 7;
  const bat_dau = new Date(nam, thang, 1 - lui);
  const o: Date[] = [];
  for (let i = 0; i < 42; i++) o.push(new Date(bat_dau.getFullYear(), bat_dau.getMonth(), bat_dau.getDate() + i));
  return o[35].getMonth() === thang || o.slice(35).some((d) => d.getMonth() === thang) ? o : o.slice(0, 35);
}

interface BoLoc {
  tt: Record<string, boolean>;
  nhom: string;
  may: string;      // "all" | id máy dạng chuỗi
}

const LOC_MAC_DINH: BoLoc = {
  tt: { cho_thuc_hien: true, hoan_thanh: true, qua_han: true, du_kien: true },
  nhom: "all",
  may: "all",
};

function docLoc(): BoLoc {
  try {
    const raw = localStorage.getItem(LOC_KEY);
    if (!raw) return LOC_MAC_DINH;
    const v = JSON.parse(raw) as Partial<BoLoc>;
    return { ...LOC_MAC_DINH, ...v, tt: { ...LOC_MAC_DINH.tt, ...(v.tt ?? {}) } };
  } catch {
    return LOC_MAC_DINH;   // localStorage hỏng/không có thì chạy như lần đầu, đừng để vỡ màn
  }
}

interface TooltipInfo {
  item: BaoTri | DuKien;
  isDuKien: boolean;
  x: number;
  y: number;
}

export function LichBaoTri({ thang, onDoiThang, onMoPhieu, onTaoTuDuKien, nap }: {
  thang: Date;
  onDoiThang: (d: Date) => void;
  onMoPhieu: (p: BaoTri) => void;
  onTaoTuDuKien: (d: DuKien) => void;
  nap: number;
}) {
  const { token } = useAuth();
  const cham = useManHep();
  const [phieu, setPhieu] = useState<BaoTri[]>([]);
  const [duKien, setDuKien] = useState<DuKien[]>([]);
  const [loading, setLoading] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);

  const [loc, setLoc] = useState<BoLoc>(docLoc);
  useEffect(() => {
    try { localStorage.setItem(LOC_KEY, JSON.stringify(loc)); } catch { /* riêng tư/đầy: bỏ qua */ }
  }, [loc]);

  // State cho Popover xem chi tiết ngày & Tooltip
  const [xemNgay, setXemNgay] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  const o = useMemo(() => oCuaThang(thang.getFullYear(), thang.getMonth()), [thang]);
  const tu = iso(o[0]);
  const den = iso(o[o.length - 1]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    kyThuatMay.lich(token, tu, den)
      .then((r) => { setPhieu(r.phieu); setDuKien(r.du_kien); setLoi(null); })
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được lịch."))
      .finally(() => setLoading(false));
  }, [token, tu, den]);

  useEffect(load, [load, nap]);

  // Nhóm máy lấy từ DANH MỤC (`may_loai` backend trả kèm), không đoán từ tiền tố mã: máy đặt mã
  // kiểu khác — "MAY-BE-01" — từng rơi hết vào một rổ "Nhóm KHAC" mà không ai hiểu vì sao.
  const dsNhom = useMemo(() => {
    const set = new Set<string>();
    for (const p of phieu) if (p.may_loai) set.add(p.may_loai);
    for (const d of duKien) if (d.may_loai) set.add(d.may_loai);
    return Array.from(set).sort((a, b) => a.localeCompare(b, "vi"));
  }, [phieu, duKien]);

  // Danh sách máy CÓ việc trong tháng đang xem — chọn giữa 40 máy mà 35 cái không có việc thì ô
  // chọn chỉ tổ dài.
  const dsMay = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of phieu) if (p.may_ma) m.set(p.may_id, p.may_ma);
    for (const d of duKien) if (d.may_ma) m.set(d.may_id, d.may_ma);
    return Array.from(m, ([id, ma]) => ({ id, ma })).sort((a, b) => a.ma.localeCompare(b.ma));
  }, [phieu, duKien]);

  const hopLoc = useCallback((mayId: number, mayLoai: string | null) => {
    if (loc.nhom !== "all" && mayLoai !== loc.nhom) return false;
    if (loc.may !== "all" && String(mayId) !== loc.may) return false;
    return true;
  }, [loc]);

  // Lọc + gom theo ngày
  const theoNgay = useMemo(() => {
    const m = new Map<string, { phieu: BaoTri[]; du_kien: DuKien[] }>();
    const lay = (k: string) => {
      let v = m.get(k);
      if (!v) { v = { phieu: [], du_kien: [] }; m.set(k, v); }
      return v;
    };

    for (const p of phieu) {
      const ttKey = p.qua_han ? "qua_han" : p.trang_thai;
      if (!loc.tt[ttKey]) continue;
      if (!hopLoc(p.may_id, p.may_loai)) continue;
      lay(p.ngay_ke_hoach.slice(0, 10)).phieu.push(p);
    }

    if (loc.tt.du_kien) {
      for (const d of duKien) {
        if (!hopLoc(d.may_id, d.may_loai)) continue;
        lay(d.ngay.slice(0, 10)).du_kien.push(d);
      }
    }

    return m;
  }, [phieu, duKien, loc, hopLoc]);

  const dangLoc = loc.nhom !== "all" || loc.may !== "all"
    || Object.keys(LOC_MAC_DINH.tt).some((k) => !loc.tt[k]);

  const homNayIso = iso(new Date());
  const nhanThang = thang.toLocaleDateString("vi-VN", { month: "long", year: "numeric" });
  const ngayXem = xemNgay ? (theoNgay.get(xemNgay) ?? { phieu: [], du_kien: [] }) : null;

  const toggleTrangThai = (k: string) =>
    setLoc((v) => ({ ...v, tt: { ...v.tt, [k]: !v.tt[k] } }));

  const handleMouseEnter = (e: React.MouseEvent | React.FocusEvent, item: BaoTri | DuKien, isDuKien: boolean) => {
    if (cham) return;                       // màn cảm ứng: chữ đã hiện đủ trên dòng, khỏi tooltip
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltip({
      item,
      isDuKien,
      x: Math.min(rect.left, window.innerWidth - 320),
      y: rect.bottom + 8,
    });
  };

  const handleMouseLeave = () => setTooltip(null);

  // Danh sách theo ngày (bản cảm ứng): chỉ ngày CÓ việc, trong đúng tháng đang xem.
  const dongTheoNgay = useMemo(() => {
    if (!cham) return [];
    return o
      .filter((d) => d.getMonth() === thang.getMonth())
      .map((d) => ({ d, key: iso(d), muc: theoNgay.get(iso(d)) }))
      .filter((r) => (r.muc?.phieu.length ?? 0) + (r.muc?.du_kien.length ?? 0) > 0);
  }, [cham, o, thang, theoNgay]);

  return (
    <section className="ktm-lich">
      {/* Thanh lọc: nhóm máy (danh mục) · máy cụ thể · chú giải bấm được để bật/tắt */}
      <div className="ktm-lich__bar">
        <div className="ktm-lich__nhom-may" role="group" aria-label="Lọc theo nhóm máy">
          <button
            type="button"
            className={`ktm-nhom-chip${loc.nhom === "all" ? " is-active" : ""}`}
            aria-pressed={loc.nhom === "all"}
            onClick={() => setLoc((v) => ({ ...v, nhom: "all" }))}
          >
            Tất cả nhóm
          </button>
          {dsNhom.map((nhom) => (
            <button
              key={nhom}
              type="button"
              className={`ktm-nhom-chip${loc.nhom === nhom ? " is-active" : ""}`}
              aria-pressed={loc.nhom === nhom}
              onClick={() => setLoc((v) => ({ ...v, nhom }))}
            >
              {nhom}
            </button>
          ))}
          {dsMay.length > 1 && (
            <select
              className="rc-input ktm-lich__may-loc"
              value={loc.may}
              aria-label="Lọc theo máy"
              onChange={(e) => setLoc((v) => ({ ...v, may: e.target.value }))}
            >
              <option value="all">Mọi máy có việc ({dsMay.length})</option>
              {dsMay.map((m) => <option key={m.id} value={String(m.id)}>{m.ma}</option>)}
            </select>
          )}
        </div>

        {/* Chú giải tương tác (bấm để bật/tắt lọc) */}
        <div className="ktm-lich__chu-giai">
          {([
            ["cho_thuc_hien", "cho", "Chờ làm"],
            ["hoan_thanh", "xong", "Hoàn thành"],
            ["qua_han", "qua", "Quá hạn"],
            ["du_kien", "du-kien", "Dự kiến"],
          ] as const).map(([key, mau, nhan]) => (
            <button
              key={key}
              type="button"
              className={`ktm-cg-btn${loc.tt[key] ? " is-active" : " is-off"}`}
              aria-pressed={loc.tt[key]}
              onClick={() => toggleTrangThai(key)}
            >
              <i className={`ktm-cham ktm-cham--${mau}`} /> {nhan}
            </button>
          ))}
        </div>
      </div>

      <header className="ktm-lich__head">
        <div className="ktm-lich__dieu-huong">
          <button type="button" className="ktm-lich__nut" aria-label="Tháng trước"
            onClick={() => onDoiThang(new Date(thang.getFullYear(), thang.getMonth() - 1, 1))}>
            <Icon name="chevron" size={16} style={{ transform: "rotate(90deg)" }} />
          </button>
          <strong className="ktm-lich__thang">{nhanThang}</strong>
          <button type="button" className="ktm-lich__nut" aria-label="Tháng sau"
            onClick={() => onDoiThang(new Date(thang.getFullYear(), thang.getMonth() + 1, 1))}>
            <Icon name="chevron" size={16} style={{ transform: "rotate(-90deg)" }} />
          </button>
          <button type="button" className="ktm-lich__homnay"
            onClick={() => onDoiThang(new Date())}>Hôm nay</button>
        </div>
      </header>

      {loi && <div className="banner banner--error" style={{ marginBottom: "var(--sp-3)" }}>{loi}</div>}

      {cham ? (
        <div className={`ktm-agenda${loading ? " is-loading" : ""}`}>
          {dongTheoNgay.length === 0 ? (
            <div className="ktm-agenda__rong">
              <p>{loading ? "Đang tải lịch…" : "Tháng này không có việc bảo trì nào khớp bộ lọc."}</p>
              {/* Tắt hết chú giải là màn trắng trơn — phải có đường ra ngay tại chỗ, đừng bắt người
                  ta tự đoán mình vừa tắt cái gì ở thanh trên. */}
              {!loading && dangLoc && (
                <button type="button" className="btn btn--ghost" onClick={() => setLoc(LOC_MAC_DINH)}>
                  Xoá bộ lọc
                </button>
              )}
            </div>
          ) : dongTheoNgay.map(({ d, key, muc }) => (
            <div key={key} className={`ktm-agenda__ngay${key === homNayIso ? " is-homnay" : ""}`}>
              <div className="ktm-agenda__dau">
                <span className="ktm-agenda__so">{d.getDate()}/{d.getMonth() + 1}</span>
                <span className="ktm-agenda__thu">{THU_DAY_DU[(d.getDay() + 6) % 7]}</span>
                {key === homNayIso && <span className="ktm-lich__today-pill">Hôm nay</span>}
              </div>
              <div className="ktm-agenda__ds">
                {(muc?.phieu ?? []).map((p) => (
                  <button key={`p-${p.id}`} type="button"
                    className={`ktm-agenda__muc ktm-agenda__muc--${p.qua_han ? "qua" : p.trang_thai}`}
                    onClick={() => onMoPhieu(p)}>
                    <span className="ktm-agenda__muc-dau">
                      <span className="ktm-may-badge">{p.may_ma}</span>
                      <span className="ktm-agenda__ma">{p.ma}</span>
                    </span>
                    <strong className="ktm-agenda__ten">{p.goi_ten ?? "Bảo trì"}</strong>
                    <span className="ktm-agenda__meta">
                      {p.qua_han ? "Quá hạn" : NHAN_TT_BAO_TRI[p.trang_thai]}
                      {(p.hang_muc?.length ?? 0) > 0 &&
                        ` · ${(p.hang_muc ?? []).filter((h) => h.xong || h.bo_qua).length}/${p.hang_muc?.length} việc`}
                      {` · ${p.so_anh} ảnh`}
                    </span>
                  </button>
                ))}
                {(muc?.du_kien ?? []).map((dk, i) => (
                  <button key={`d-${dk.may_id}-${dk.goi_id ?? i}`} type="button"
                    className="ktm-agenda__muc ktm-agenda__muc--du-kien"
                    onClick={() => onTaoTuDuKien(dk)}>
                    <span className="ktm-agenda__muc-dau">
                      <span className="ktm-may-badge">{dk.may_ma}</span>
                      <span className="ktm-agenda__ma">Dự kiến</span>
                    </span>
                    <strong className="ktm-agenda__ten">{dk.goi_ten ?? "Bảo trì định kỳ"}</strong>
                    <span className="ktm-agenda__meta">Bấm để lập phiếu</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
      <div className={`ktm-lich__luoi${loading ? " is-loading" : ""}`}>
        {THU.map((t) => <div key={t} className="ktm-lich__thu">{t}</div>)}
        {o.map((d) => {
          const key = iso(d);
          const trongThang = d.getMonth() === thang.getMonth();
          const homNay = key === homNayIso;
          const muc = theoNgay.get(key);
          const dsPhieu = muc?.phieu ?? [];
          const dsDuKien = muc?.du_kien ?? [];
          const tongSo = dsPhieu.length + dsDuKien.length;

          // Gom tối đa MAX_CELL_ITEMS
          const hienPhieu = dsPhieu.slice(0, MAX_CELL_ITEMS);
          const conLaiChot = MAX_CELL_ITEMS - hienPhieu.length;
          const hienDuKien = conLaiChot > 0 ? dsDuKien.slice(0, conLaiChot) : [];
          const soConDuyet = tongSo - (hienPhieu.length + hienDuKien.length);

          return (
            <div key={key}
              className={`ktm-lich__o${trongThang ? "" : " is-ngoai"}${homNay ? " is-homnay" : ""}`}>
              <div className="ktm-lich__o-head" onClick={() => tongSo > 0 && setXemNgay(key)}>
                <span className="ktm-lich__ngay">{d.getDate()}</span>
                {homNay && <span className="ktm-lich__today-pill">Hôm nay</span>}
              </div>

              <div className="ktm-lich__danh-sach">
                {hienPhieu.map((p) => (
                  <button key={`p-${p.id}`} type="button"
                    className={`ktm-card ktm-card--${p.qua_han ? "qua" : p.trang_thai}`}
                    onMouseEnter={(e) => handleMouseEnter(e, p, false)}
                    onMouseLeave={handleMouseLeave}
                    onFocus={(e) => handleMouseEnter(e, p, false)}
                    onBlur={handleMouseLeave}
                    onClick={() => onMoPhieu(p)}>
                    <span className="ktm-card__badge">{p.may_ma}</span>
                    <span className="ktm-card__ten">{p.goi_ten ?? "Bảo trì"}</span>
                  </button>
                ))}

                {hienDuKien.map((dk, i) => (
                  <button key={`d-${dk.may_id}-${dk.goi_id ?? i}`} type="button"
                    className="ktm-card ktm-card--du-kien"
                    onMouseEnter={(e) => handleMouseEnter(e, dk, true)}
                    onMouseLeave={handleMouseLeave}
                    onFocus={(e) => handleMouseEnter(e, dk, true)}
                    onBlur={handleMouseLeave}
                    onClick={() => onTaoTuDuKien(dk)}>
                    <span className="ktm-card__badge">{dk.may_ma}</span>
                    <span className="ktm-card__ten">{dk.goi_ten ?? "Bảo trì"}</span>
                  </button>
                ))}

                {soConDuyet > 0 && (
                  <button
                    type="button"
                    className="ktm-card__more"
                    onClick={() => setXemNgay(key)}
                  >
                    + {soConDuyet} phiếu khác
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      )}

      {/* Thẻ thông tin nổi (chỉ máy tính có chuột) */}
      {tooltip && (
        <div
          className="ktm-tooltip"
          role="tooltip"
          style={{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }}
        >
          {tooltip.isDuKien ? (
            <RichDuKienTooltip item={tooltip.item as DuKien} />
          ) : (
            <RichPhieuTooltip item={tooltip.item as BaoTri} />
          )}
        </div>
      )}

      {/* Popover tóm tắt một ngày. Đọc thẳng từ `theoNgay` nên tạo/sửa phiếu xong là nội dung
          trong này cũng mới theo — chụp lại mảng lúc bấm thì nó đứng im ở bản cũ. */}
      {xemNgay && ngayXem && (
        <div className="ktm-popover-overlay" onClick={() => setXemNgay(null)}>
          <div className="ktm-popover" onClick={(e) => e.stopPropagation()}>
            <div className="ktm-popover__head">
              <div>
                <div className="ktm-popover__date-row">
                  <Icon name="calendar" size={16} />
                  <h3 className="ktm-popover__title">{fmtNgayFull(xemNgay)}</h3>
                </div>
                <span className="ktm-popover__sub">
                  {ngayXem.phieu.length + ngayXem.du_kien.length} lịch bảo trì trong ngày
                </span>
              </div>
              <button type="button" className="ktm-popover__close" onClick={() => setXemNgay(null)}>
                <Icon name="x" size={18} />
              </button>
            </div>

            <div className="ktm-popover__body">
              {ngayXem.phieu.length > 0 && (
                <div className="ktm-popover__sec">
                  <div className="ktm-popover__label">Phiếu bảo trì ({ngayXem.phieu.length})</div>
                  {ngayXem.phieu.map((p) => {
                    const xong = (p.hang_muc ?? []).filter((h) => h.xong || h.bo_qua).length;
                    const tong = (p.hang_muc ?? []).length;
                    const pct = tong > 0 ? Math.round((xong / tong) * 100) : 0;
                    const isQua = p.qua_han;

                    return (
                      <div
                        key={p.id}
                        className={`ktm-popover-item ktm-popover-item--${isQua ? "qua" : p.trang_thai}`}
                        onClick={() => { setXemNgay(null); onMoPhieu(p); }}
                      >
                        <div className="ktm-popover-item__head">
                          <span className="ktm-popover-item__ma">{p.ma}</span>
                          <BadgeBaoTri trangThai={p.trang_thai} quaHan={isQua} />
                        </div>

                        <div className="ktm-popover-item__title">
                          <span className="ktm-may-badge">{p.may_ma ?? "—"}</span>
                          <strong className="ktm-popover-item__goi">{p.goi_ten ?? (p.loai === "dot_xuat" ? "Bảo trì đột xuất" : "Bảo trì")}</strong>
                        </div>

                        <div className="ktm-popover-item__meta">
                          {p.may_ten && <span className="ktm-popover-item__mayten">{p.may_ten}</span>}
                          {tong > 0 && (
                            <span className="ktm-popover-item__check">
                              Checklist: <strong>{xong}/{tong}</strong> ({pct}%)
                            </span>
                          )}
                          <span className={p.so_anh > 0 ? "ktm-anhchip is-du" : "ktm-anhchip is-thieu"}>
                            <Icon name="camera" size={11} /> {p.so_anh} ảnh
                          </span>
                          <Icon name="arrowRight" size={14} className="ktm-popover-item__arrow" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {ngayXem.du_kien.length > 0 && (
                <div className="ktm-popover__sec">
                  <div className="ktm-popover__label">Dự kiến theo chu kỳ ({ngayXem.du_kien.length})</div>
                  {ngayXem.du_kien.map((dk, i) => (
                    <div
                      key={i}
                      className="ktm-popover-item ktm-popover-item--du-kien"
                      onClick={() => { setXemNgay(null); onTaoTuDuKien(dk); }}
                    >
                      <div className="ktm-popover-item__head">
                        <span className="ktm-popover-item__ma">DỰ KIẾN</span>
                        <span className="ktm-badge">
                          <Icon name="plus" size={12} /> Bấm để lập phiếu
                        </span>
                      </div>
                      <div className="ktm-popover-item__title">
                        <span className="ktm-may-badge">{dk.may_ma}</span>
                        <strong className="ktm-popover-item__goi">{dk.goi_ten ?? "Bảo trì định kỳ"}</strong>
                      </div>
                      <div className="ktm-popover-item__meta">
                        <span>Chu kỳ: mỗi {dk.chu_ky_so} {NHAN_DON_VI_CHU_KY[dk.chu_ky_don_vi ?? ""] ?? dk.chu_ky_don_vi}</span>
                        <Icon name="arrowRight" size={14} className="ktm-popover-item__arrow" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function RichPhieuTooltip({ item }: { item: BaoTri }) {
  const isQua = item.qua_han;
  const hangMucXong = (item.hang_muc ?? []).filter((h) => h.xong || h.bo_qua).length;
  const hangMucTong = (item.hang_muc ?? []).length;

  return (
    <div className="ktm-tt">
      <div className="ktm-tt__head">
        <span className="ktm-tt__code">{item.ma}</span>
        {/* `gonNhe`: trong tooltip hẹp thì bỏ icon, giữ nguyên màu + chữ. */}
        <BadgeBaoTri trangThai={item.trang_thai} quaHan={isQua} gonNhe />
      </div>
      <div className="ktm-tt__title">
        <span className="ktm-tt__may">{item.may_ma}</span>
        {item.may_ten && <span className="ktm-tt__mayten"> ({item.may_ten})</span>}
      </div>
      <div className="ktm-tt__goi">{item.goi_ten ?? "Phiếu bảo trì định kỳ"}</div>

      <div className="ktm-tt__grid">
        <div>
          <span className="ktm-tt__lbl">Hạn KH:</span> {item.ngay_ke_hoach.slice(0, 10)}
        </div>
        {item.chu_ky_so && (
          <div>
            <span className="ktm-tt__lbl">Chu kỳ:</span> mỗi {item.chu_ky_so} {NHAN_DON_VI_CHU_KY[item.chu_ky_don_vi ?? ""] ?? item.chu_ky_don_vi}
          </div>
        )}
        <div>
          <span className="ktm-tt__lbl">Checklist:</span> {hangMucTong > 0 ? `${hangMucXong}/${hangMucTong} đã xong` : "Không có"}
        </div>
        <div>
          <span className="ktm-tt__lbl">Ảnh chứng thực:</span> {item.so_anh > 0 ? `${item.so_anh} ảnh` : "Chưa có"}
        </div>
      </div>
      <div className="ktm-tt__foot">Bấm để xem &amp; cập nhật phiếu</div>
    </div>
  );
}

function RichDuKienTooltip({ item }: { item: DuKien }) {
  return (
    <div className="ktm-tt">
      <div className="ktm-tt__head">
        <span className="ktm-tt__code">DỰ KIẾN</span>
        <span className="ktm-badge">Chưa lập phiếu</span>
      </div>
      <div className="ktm-tt__title">
        <span className="ktm-tt__may">{item.may_ma}</span>
        {item.may_ten && <span className="ktm-tt__mayten"> ({item.may_ten})</span>}
      </div>
      <div className="ktm-tt__goi">{item.goi_ten ?? "Bảo trì định kỳ"}</div>
      <div className="ktm-tt__grid">
        <div>
          <span className="ktm-tt__lbl">Ngày dự kiến:</span> {item.ngay.slice(0, 10)}
        </div>
        {item.chu_ky_so && (
          <div>
            <span className="ktm-tt__lbl">Chu kỳ:</span> mỗi {item.chu_ky_so} {NHAN_DON_VI_CHU_KY[item.chu_ky_don_vi ?? ""] ?? item.chu_ky_don_vi}
          </div>
        )}
      </div>
      <div className="ktm-tt__foot ktm-tt__foot--action">Bấm để lập phiếu bảo trì ngay</div>
    </div>
  );
}
