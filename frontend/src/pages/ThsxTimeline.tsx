// TIMELINE của bàn THỰC HIỆN SẢN XUẤT — kế thừa KHUNG trình bày của `Xl2Gantt` nhưng bỏ SẠCH
// kéo–thả (tổ trưởng KHÔNG được dời lịch, §5.2/§10.1) và bỏ overlay xếp-lịch (khoá máy / nhiệt tải /
// đỉnh quân số / "râu" bóc-tách — không thuộc pha thực hiện). Trục THUẦN TUYẾN TÍNH tái dùng
// `buildLinearScale` (đồng-hồ-tường, không nén ngoài-ca).
//
// Thanh = CỬA SỔ KẾ HOẠCH `du_kien_bat_dau → du_kien_ket_thuc`, tô theo `trang_thai` (running nhịp
// đập / paused gạch chéo / completed mờ + tick). LỚP THỰC-TẾ (§5.1): mỗi phiên chạy `w.thuc_te` vẽ
// một ruy-băng moss mảnh ngay dưới thanh — cùng trục giờ nên lệch trái/phải = lệch bắt-đầu/kết-thúc
// so kế hoạch; phiên mở kéo tới "bây giờ". Chi tiết từng phiên vẫn ở DRAWER. Component CHỈ ĐỌC +
// phát `onChonViec(id)` khi bấm thanh.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Icon } from "../components/Icons";
import { ngayGio } from "./keHoachSxShared";
import { LABEL_W, BAR_H, buildLinearScale, ngayToWall, type Xl2Zoom } from "./xl2Shared";
import { wallMinutes, fromWall, nowWall } from "./gantt-time";
import { demViecLanes, sxNguonIcon, sxSerial, ttMeta, type ThsxCluster } from "./thsxShared";

const TICK_MIN: Record<Xl2Zoom, number> = { gio: 60, ca: 180, ngay: 360, tuan: 1440 };
const WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

interface Props {
  clusters: ThsxCluster[];
  winTu: string;
  winDen: string;
  zoom: Xl2Zoom;
  selectedId: number | null;
  onChonViec: (id: number) => void;
}

function hh(t: number): string {
  const w = fromWall(t);
  return `${String(w.hh).padStart(2, "0")}:${String(w.mi).padStart(2, "0")}`;
}

export function ThsxTimeline({ clusters, winTu, winDen, zoom, selectedId, onChonViec }: Props) {
  const winStart = ngayToWall(winTu);
  const winEnd = ngayToWall(winDen) + 1440; // hết ngày "den"
  const scale = useMemo(() => buildLinearScale(winStart, winEnd, zoom), [winStart, winEnd, zoom]);

  // Nền: chỉ lưới ngày + đường "bây giờ". KHÔNG băng ca / ngày lễ — `/work-items` không trả ca/lịch.
  const dayLines = useMemo(() => {
    const xs: number[] = [];
    for (let d = winStart; d < winEnd; d += 1440) xs.push(scale.xOf(d));
    return xs;
  }, [winStart, winEnd, scale]);

  // Thước: nhãn ngày + tick giờ.
  const ruler = useMemo(() => {
    const days: { x: number; w: number; label: string }[] = [];
    for (let d = winStart; d < winEnd; d += 1440) {
      const w = fromWall(d);
      const wd = WD[new Date(Date.UTC(w.y, w.mo - 1, w.d)).getUTCDay()];
      days.push({
        x: scale.xOf(d), w: 1440 * scale.ppm,
        label: `${wd} ${String(w.d).padStart(2, "0")}/${String(w.mo).padStart(2, "0")}`,
      });
    }
    const ticks: { x: number; label: string }[] = [];
    const step = TICK_MIN[zoom];
    if (step < 1440) {
      const first = Math.ceil(winStart / step) * step;
      for (let t = first; t < winEnd; t += step) {
        if ((t - winStart) % 1440 === 0) continue; // 00:00 đã có nhãn ngày
        ticks.push({ x: scale.xOf(t), label: hh(t) });
      }
    }
    return { days, ticks };
  }, [winStart, winEnd, scale, zoom]);

  const nowX = useMemo(() => {
    const n = nowWall();
    return n >= winStart && n <= winEnd ? scale.xOf(n) : null;
  }, [winStart, winEnd, scale]);

  // Cột nhãn 270px vừa vặn trên máy bàn, nhưng ở 375px nó ăn gần hết bề ngang: phần vẽ thanh
  // chỉ còn khoảng 105px trên một trục dài hơn 11.000px — mở ra là một dải trống. Màn hẹp rút
  // cột nhãn còn 140px; tên máy/công đoạn dài thì cắt bằng "…" (đã có `title` đầy đủ khi chạm
  // giữ). Cùng ngưỡng 820px với chỗ CSS xếp chồng hai cột.
  const [labelW, setLabelW] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(max-width: 820px)").matches ? 140 : LABEL_W);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 820px)");
    const apDung = () => setLabelW(mq.matches ? 140 : LABEL_W);
    apDung();
    mq.addEventListener("change", apDung);
    return () => mq.removeEventListener("change", apDung);
  }, []);

  // Cuộn ngang tới thanh đang chọn (bấm dòng trái → thấy thanh; §3 "scroll-to").
  const scrollRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (selectedId == null) return;
    const el = scrollRef.current;
    if (!el) return;
    let start: string | null = null;
    for (const c of clusters) for (const l of c.lanes) {
      const w = l.viec.find((x) => x.id === selectedId);
      if (w) { start = w.du_kien_bat_dau; break; }
    }
    if (!start) return;
    const sW = wallMinutes(start);
    if (!Number.isFinite(sW)) return;
    const barLeft = scale.xOf(sW);
    const target = labelW + barLeft - el.clientWidth / 2;
    el.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
  }, [selectedId, clusters, scale, labelW]);

  const fullW = labelW + scale.width;
  const laneStyle: CSSProperties = {
    "--thsx-label-w": `${labelW}px`, "--thsx-bar-h": `${BAR_H}px`,
  } as CSSProperties;

  return (
    <div className="thsx-gantt__scroll" ref={scrollRef}>
      <div className="thsx-gantt__inner" style={{ width: fullW, ...laneStyle }}>
        {/* thước */}
        <div className="thsx-ruler" style={{ width: fullW }}>
          <div className="thsx-ruler__spacer" />
          {ruler.days.map((d, i) => (
            <div key={`d${i}`} className="thsx-ruler__day" style={{ left: labelW + d.x, width: d.w }}>
              {d.label}
            </div>
          ))}
          {ruler.ticks.map((t, i) => (
            <div key={`t${i}`} className="thsx-ruler__tick" style={{ left: labelW + t.x }}>
              {t.label}
            </div>
          ))}
        </div>

        {/* các cụm */}
        {clusters.map((cluster) => (
          <div key={cluster.key} className={`thsx-cluster thsx-cluster--${cluster.key}`}>
            <div className="thsx-cluster__headbg" style={{ width: fullW }} />
            <div className="thsx-cluster__head">
              <Icon name={cluster.icon} size={13} />
              <span>{cluster.label}</span>
              <b>· {cluster.lanes.length} {cluster.unit} · {demViecLanes(cluster.lanes)} việc</b>
            </div>
            {cluster.lanes.map((lane) => (
              <div key={lane.key} className="thsx-lane">
                <div className="thsx-lane__label" title={lane.label}>
                  <Icon name={cluster.icon} size={12} />
                  <span className="thsx-lane__name">{lane.label}</span>
                </div>
                <div className="thsx-lane__track" style={{ width: scale.width }}>
                  {/* nền */}
                  {dayLines.map((x, i) => (
                    <div key={`g${i}`} className="thsx-daygrid" style={{ left: x }} />
                  ))}
                  {nowX != null && <div className="thsx-nowline" style={{ left: nowX }} />}
                  {/* thanh việc */}
                  {lane.viec.map((w) => {
                    const sW = w.du_kien_bat_dau ? wallMinutes(w.du_kien_bat_dau) : NaN;
                    const eW = w.du_kien_ket_thuc ? wallMinutes(w.du_kien_ket_thuc) : sW + 30;
                    if (!Number.isFinite(sW)) return null;
                    const left = scale.xOf(sW);
                    const right = scale.xOf(eW);
                    const width = Math.max(right - left, 16);
                    const sel = w.id === selectedId;
                    const meta = ttMeta(w.trang_thai);
                    const serial = sxSerial(w.nguon_ma);
                    const wide = width >= 128;
                    const tiny = width < 44;
                    const cd = w.ten_cong_doan || "";
                    const spillText = tiny ? `${serial}${cd ? ` · ${cd}` : ""}` : cd;
                    const showSpill = !wide && spillText !== "";
                    const barIcon = w.trang_thai === "released" ? sxNguonIcon(w.nguon_loai) : meta.icon;
                    // Lớp thực-tế (§5.1): mỗi phiên chạy = một ruy-băng mảnh ngay dưới thanh kế
                    // hoạch. Phiên mở (ket_thuc=null) kéo tới "bây giờ" và nhấp nháy như đang chạy.
                    const acts = (w.thuc_te ?? []).flatMap((iv) => {
                      const aS = wallMinutes(iv.bat_dau);
                      if (!Number.isFinite(aS)) return [];
                      const eRaw = iv.ket_thuc ? wallMinutes(iv.ket_thuc) : nowWall();
                      const aE = Number.isFinite(eRaw) ? Math.max(eRaw, aS) : aS;
                      const aLeft = scale.xOf(aS);
                      return [{
                        left: aLeft, width: Math.max(scale.xOf(aE) - aLeft, 3),
                        open: iv.ket_thuc == null, tu: iv.bat_dau, den: iv.ket_thuc,
                      }];
                    });
                    return (
                      <div className="thsx-barwrap" key={w.id}>
                        {acts.map((a, i) => (
                          <span
                            key={`a${i}`}
                            className={`thsx-actbar${a.open ? " thsx-actbar--open" : ""}`}
                            style={{ left: a.left, width: a.width }}
                            title={`Thực tế: ${ngayGio(a.tu)}${a.den ? ` → ${ngayGio(a.den)}` : " → đang chạy"}`}
                            aria-hidden="true"
                          />
                        ))}
                        <button
                          type="button"
                          className={`thsx-bar thsx-bar--${w.trang_thai}${sel ? " thsx-bar--sel" : ""}${w.la_kcs ? " thsx-bar--kcs" : ""}`}
                          style={{ left, width }}
                          title={`${w.nguon_ma || serial}${cd ? ` · ${cd}` : ""}${w.nguon_ten ? ` · ${w.nguon_ten}` : ""} · ${meta.label} · ${w.du_kien_bat_dau ? ngayGio(w.du_kien_bat_dau) : "chưa định giờ"}${w.la_kcs ? " · KCS" : ""}`}
                          aria-label={`${w.nguon_ma || serial}${cd ? `, ${cd}` : ""}, ${meta.label}${w.la_kcs ? ", KCS" : ""}`}
                          aria-pressed={sel}
                          onClick={() => onChonViec(w.id)}
                        >
                          <Icon name={barIcon} size={12} />
                          {!tiny && <span className="thsx-bar__code">{serial}</span>}
                          {wide && cd && <span className="thsx-bar__cd">{cd}</span>}
                          {w.la_kcs && width >= 40 && <span className="thsx-bar__kcs" aria-hidden="true">KCS</span>}
                          {w.trang_thai === "completed" && width >= 34 && (
                            <Icon name="check" size={12} />
                          )}
                        </button>
                        {showSpill && (
                          <span
                            className={`thsx-bar__spill${sel ? " is-sel" : ""}`}
                            style={{ left: left + width + 6 }}
                            aria-hidden="true"
                          >{spillText}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
