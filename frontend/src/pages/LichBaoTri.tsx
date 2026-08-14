import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import {
  kyThuatMay, NHAN_DON_VI_CHU_KY, NHAN_TT_BAO_TRI, type BaoTri, type DuKien,
} from "../api/kyThuatMay";

const THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const MAX_CELL_ITEMS = 3;

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

// Phân loại nhóm máy từ mã máy (IN-01 -> IN, BE-03 -> BE...)
function nhomCuaMay(ma: string | null): string {
  if (!ma) return "KHAC";
  const prefix = ma.split("-")[0].toUpperCase();
  return prefix || "KHAC";
}

const TEN_NHOM_MAY: Record<string, string> = {
  IN: "Máy in",
  BE: "Máy bế",
  CM: "Máy cán",
  BOI: "Máy bồi",
  DAO: "Máy cắt",
};

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
  const [phieu, setPhieu] = useState<BaoTri[]>([]);
  const [duKien, setDuKien] = useState<DuKien[]>([]);
  const [loading, setLoading] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);

  // Bộ lọc tương tác
  const [trangThaiLoc, setTrangThaiLoc] = useState<Record<string, boolean>>({
    cho_thuc_hien: true,
    hoan_thanh: true,
    qua_han: true,
    du_kien: true,
  });
  const [nhomMayLoc, setNhomMayLoc] = useState<string>("all");

  // State cho Popover xem chi tiết ngày & Tooltip
  const [xemNgay, setXemNgay] = useState<{ key: string; phieu: BaoTri[]; duKien: DuKien[] } | null>(null);
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

  // Tìm danh sách nhóm máy thực tế từ dữ liệu
  const dsNhomMay = useMemo(() => {
    const set = new Set<string>();
    for (const p of phieu) if (p.may_ma) set.add(nhomCuaMay(p.may_ma));
    for (const d of duKien) if (d.may_ma) set.add(nhomCuaMay(d.may_ma));
    return Array.from(set);
  }, [phieu, duKien]);

  // Lọc + gom theo ngày
  const theoNgay = useMemo(() => {
    const m = new Map<string, { phieu: BaoTri[]; du_kien: DuKien[] }>();
    const lay = (k: string) => {
      let v = m.get(k);
      if (!v) { v = { phieu: [], du_kien: [] }; m.set(k, v); }
      return v;
    };

    for (const p of phieu) {
      const isQua = p.qua_han;
      const ttKey = isQua ? "qua_han" : p.trang_thai;
      if (!trangThaiLoc[ttKey]) continue;
      if (nhomMayLoc !== "all" && nhomCuaMay(p.may_ma) !== nhomMayLoc) continue;
      lay(p.ngay_ke_hoach.slice(0, 10)).phieu.push(p);
    }

    if (trangThaiLoc.du_kien) {
      for (const d of duKien) {
        if (nhomMayLoc !== "all" && nhomCuaMay(d.may_ma) !== nhomMayLoc) continue;
        lay(d.ngay.slice(0, 10)).du_kien.push(d);
      }
    }

    return m;
  }, [phieu, duKien, trangThaiLoc, nhomMayLoc]);

  const homNayIso = iso(new Date());
  const nhanThang = thang.toLocaleDateString("vi-VN", { month: "long", year: "numeric" });

  const toggleTrangThai = (k: string) => {
    setTrangThaiLoc((prev) => ({ ...prev, [k]: !prev[k] }));
  };

  const handleMouseEnter = (e: React.MouseEvent, item: BaoTri | DuKien, isDuKien: boolean) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltip({
      item,
      isDuKien,
      x: Math.min(rect.left, window.innerWidth - 320),
      y: rect.bottom + 8,
    });
  };

  const handleMouseLeave = () => {
    setTooltip(null);
  };

  return (
    <section className="ktm-lich">
      {/* Dynamic Filter Toolbar */}
      <div className="ktm-lich__bar">
        <div className="ktm-lich__nhom-may" role="group" aria-label="Lọc theo nhóm máy">
          <button
            type="button"
            className={`ktm-nhom-chip${nhomMayLoc === "all" ? " is-active" : ""}`}
            onClick={() => setNhomMayLoc("all")}
          >
            Tất cả máy
          </button>
          {dsNhomMay.map((nhom) => (
            <button
              key={nhom}
              type="button"
              className={`ktm-nhom-chip${nhomMayLoc === nhom ? " is-active" : ""}`}
              onClick={() => setNhomMayLoc(nhom)}
            >
              {TEN_NHOM_MAY[nhom] ?? `Nhóm ${nhom}`}
            </button>
          ))}
        </div>

        {/* Chú giải tương tác (Click để bật/tắt lọc) */}
        <div className="ktm-lich__chu-giai">
          <button
            type="button"
            className={`ktm-cg-btn${trangThaiLoc.cho_thuc_hien ? " is-active" : " is-off"}`}
            onClick={() => toggleTrangThai("cho_thuc_hien")}
          >
            <i className="ktm-cham ktm-cham--cho" /> Chờ làm
          </button>
          <button
            type="button"
            className={`ktm-cg-btn${trangThaiLoc.hoan_thanh ? " is-active" : " is-off"}`}
            onClick={() => toggleTrangThai("hoan_thanh")}
          >
            <i className="ktm-cham ktm-cham--xong" /> Hoàn thành
          </button>
          <button
            type="button"
            className={`ktm-cg-btn${trangThaiLoc.qua_han ? " is-active" : " is-off"}`}
            onClick={() => toggleTrangThai("qua_han")}
          >
            <i className="ktm-cham ktm-cham--qua" /> Quá hạn
          </button>
          <button
            type="button"
            className={`ktm-cg-btn${trangThaiLoc.du_kien ? " is-active" : " is-off"}`}
            onClick={() => toggleTrangThai("du_kien")}
          >
            <i className="ktm-cham ktm-cham--du-kien" /> Dự kiến
          </button>
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
              <div className="ktm-lich__o-head" onClick={() => tongSo > 0 && setXemNgay({ key, phieu: dsPhieu, duKien: dsDuKien })}>
                <span className="ktm-lich__ngay">{d.getDate()}</span>
                {homNay && <span className="ktm-lich__today-pill">Hôm nay</span>}
              </div>

              <div className="ktm-lich__danh-sach">
                {hienPhieu.map((p) => (
                  <button key={`p-${p.id}`} type="button"
                    className={`ktm-card ktm-card--${p.qua_han ? "qua" : p.trang_thai}`}
                    onMouseEnter={(e) => handleMouseEnter(e, p, false)}
                    onMouseLeave={handleMouseLeave}
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
                    onClick={() => onTaoTuDuKien(dk)}>
                    <span className="ktm-card__badge">{dk.may_ma}</span>
                    <span className="ktm-card__ten">{dk.goi_ten ?? "Bảo trì"}</span>
                  </button>
                ))}

                {soConDuyet > 0 && (
                  <button
                    type="button"
                    className="ktm-card__more"
                    onClick={() => setXemNgay({ key, phieu: dsPhieu, duKien: dsDuKien })}
                  >
                    + {soConDuyet} phiếu khác
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Floating Rich Tooltip */}
      {tooltip && (
        <div
          className="ktm-tooltip"
          style={{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }}
        >
          {tooltip.isDuKien ? (
            <RichDuKienTooltip item={tooltip.item as DuKien} />
          ) : (
            <RichPhieuTooltip item={tooltip.item as BaoTri} />
          )}
        </div>
      )}

      {/* Day Summary Popover Modal */}
      {xemNgay && (
        <div className="ktm-popover-overlay" onClick={() => setXemNgay(null)}>
          <div className="ktm-popover" onClick={(e) => e.stopPropagation()}>
            <div className="ktm-popover__head">
              <div>
                <div className="ktm-popover__date-row">
                  <Icon name="calendar" size={16} />
                  <h3 className="ktm-popover__title">{fmtNgayFull(xemNgay.key)}</h3>
                </div>
                <span className="ktm-popover__sub">{xemNgay.phieu.length + xemNgay.duKien.length} lịch bảo trì trong ngày</span>
              </div>
              <button type="button" className="ktm-popover__close" onClick={() => setXemNgay(null)}>
                <Icon name="x" size={18} />
              </button>
            </div>

            <div className="ktm-popover__body">
              {xemNgay.phieu.length > 0 && (
                <div className="ktm-popover__sec">
                  <div className="ktm-popover__label">Phiếu Bảo Trì ({xemNgay.phieu.length})</div>
                  {xemNgay.phieu.map((p) => {
                    const xong = (p.hang_muc ?? []).filter((h) => h.xong).length;
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
                          <span className={`ktm-badge ktm-badge--tt-${isQua ? "qua_han" : p.trang_thai}`}>
                            {isQua ? (
                              <><Icon name="alert" size={12} /> Quá hạn</>
                            ) : p.trang_thai === "hoan_thanh" ? (
                              <><Icon name="check" size={12} /> Hoàn thành</>
                            ) : (
                              <><Icon name="clock" size={12} /> Chờ thực hiện</>
                            )}
                          </span>
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

              {xemNgay.duKien.length > 0 && (
                <div className="ktm-popover__sec">
                  <div className="ktm-popover__label">Dự Kiến Chu Kỳ ({xemNgay.duKien.length})</div>
                  {xemNgay.duKien.map((dk, i) => (
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
  const hangMucXong = (item.hang_muc ?? []).filter((h) => h.xong).length;
  const hangMucTong = (item.hang_muc ?? []).length;

  return (
    <div className="ktm-tt">
      <div className="ktm-tt__head">
        <span className="ktm-tt__code">{item.ma}</span>
        <span className={`ktm-badge ktm-badge--tt-${isQua ? "qua_han" : item.trang_thai}`}>
          {isQua ? "Quá hạn" : NHAN_TT_BAO_TRI[item.trang_thai]}
        </span>
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
      <div className="ktm-tt__foot">Click để xem & cập nhật phiếu</div>
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

