// GANTT của màn XẾP LỊCH 2 — kế thừa CƠ CHẾ kéo-thả của GanttBoard cũ (Pointer Events + AbortController
// + ghost + a11y phím) nhưng VIẾT LẠI dưới `.xl2-`, và trục THUẦN TUYẾN TÍNH: v2 việc chạy LIÊN TỤC
// (finish = start + chiếm-máy theo đồng-hồ-tường), KHÔNG cắt theo ca ⇒ không dùng buildScale/snapToWork.
//
// Ba CỤM lane: Máy · Tổ · Thuê ngoài, cộng cụm "Chưa đặt giờ" (dòng nháp chưa gán máy/giờ, xếp chip
// tuần tự). Kéo NGANG đổi giờ; kéo DỌC sang lane khác đổi tài nguyên (máy↔tổ). Mỗi cú kéo/nhấn phím chỉ
// ĐỀ XUẤT một patch — controller mới gọi xem-trước rồi ghi (một cửa duy nhất). Component này KHÔNG gọi API.
import {
  Fragment, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties,
} from "react";
import { Icon, type IconName } from "../components/Icons";
import type {
  Xl2Ca, Xl2Dong, Xl2KhoaMay, Xl2Muc, Xl2NgayLe, Xl2TaiMay, Xl2TaiTo,
} from "../api/client";
import { ngayGio, thoiLuong } from "./keHoachSxShared";
import {
  BAR_H, LABEL_W, XL2_MUC_META, buildLinearScale, demViecLanes, dongEntityKey, dongNhanParts,
  dongSerial, nguonIcon, ngayToWall, wallToNaive, type Xl2Zoom,
} from "./xl2Shared";
import { wallMinutes, fromWall, nowWall } from "./gantt-time";

// --------------------------------------------------------------------------
export type Xl2ClusterKey = "may" | "to" | "ncc" | "cho";

export interface Xl2Lane {
  key: string;                 // "may:12" | "to:3" | "ncc:_" | "cho:_"
  cluster: Xl2ClusterKey;
  resId: number | null;        // may_id | department_id | null
  label: string;
  /** Dòng CHƯA đặt giờ (start=null) → xếp chip tuần tự, không đặt theo trục. */
  packed?: boolean;
  dong: Xl2Dong[];
}
export interface Xl2Cluster {
  key: Xl2ClusterKey;
  label: string;
  icon: IconName;
  lanes: Xl2Lane[];
}
export interface Xl2Patch {
  may_id?: number | null;
  department_id?: number | null;
  start_at?: string | null;
}

interface Props {
  clusters: Xl2Cluster[];
  ca: Xl2Ca[];
  ngayLe: Xl2NgayLe[];
  /** Overlay nền (F1): vùng khoá máy · tải máy/ngày · đỉnh quân số tổ/ngày. */
  khoaMay: Xl2KhoaMay[];
  taiMay: Xl2TaiMay[];
  taiTo: Xl2TaiTo[];
  winTu: string;
  winDen: string;
  zoom: Xl2Zoom;
  selectedDongId: number | null;
  selectedEntityKey: string | null;
  /** Mức nặng nhất của MỘT SỐ dòng đã tính vấn đề (dòng đang chọn + chuỗi thực thể). Không có ⇒ trung tính. */
  barMuc: Map<number, Xl2Muc>;
  canUpdate: boolean;
  onSelectDong: (id: number) => void;
  onPropose: (dongId: number, patch: Xl2Patch, dong: Xl2Dong) => void;
}

const SNAP_MIN: Record<Xl2Zoom, number> = { gio: 5, ca: 15, ngay: 30, tuan: 60 };
const TICK_MIN: Record<Xl2Zoom, number> = { gio: 60, ca: 180, ngay: 360, tuan: 1440 };
const DRAG_THRESH = 4;
const PACK_W = 92; // bề rộng chip "chưa đặt giờ"

interface DragState {
  dongId: number;
  dong: Xl2Dong;
  fromX: number;
  fromY: number;
  durMin: number;
  moved: boolean;
  targetLaneKey: string | null;
  startWall: number | null;
  valid: boolean;
}
interface Ghost {
  laneKey: string;
  x: number;
  w: number;
  valid: boolean;
  collide: boolean;
  label: string;
}

function hh(t: number): string {
  const w = fromWall(t);
  return `${String(w.hh).padStart(2, "0")}:${String(w.mi).padStart(2, "0")}`;
}

/** Bậc nhiệt tải máy theo tỉ lệ chiếm ngày: <50% · <75% · <90% · ≥90%. */
function heatBucket(pct: number): 1 | 2 | 3 | 4 {
  if (pct < 0.5) return 1;
  if (pct < 0.75) return 2;
  if (pct < 0.9) return 3;
  return 4;
}

export function Xl2Gantt({
  clusters, ca, ngayLe, khoaMay, taiMay, taiTo, winTu, winDen, zoom,
  selectedDongId, selectedEntityKey, barMuc, canUpdate, onSelectDong, onPropose,
}: Props) {
  const winStart = ngayToWall(winTu);
  const winEnd = ngayToWall(winDen) + 1440; // hết ngày "den"
  const scale = useMemo(() => buildLinearScale(winStart, winEnd, zoom), [winStart, winEnd, zoom]);

  // Tra cứu lane theo key (cho hit-test khi kéo).
  const laneByKey = useMemo(() => {
    const m = new Map<string, Xl2Lane>();
    for (const c of clusters) for (const l of c.lanes) m.set(l.key, l);
    return m;
  }, [clusters]);

  // Nền: lưới ngày + tô ngày lễ + dải ca làm việc (một lần, dùng chung mọi lane).
  const bg = useMemo(() => {
    const dayLines: number[] = [];
    const holidays: { x: number; w: number }[] = [];
    const shifts: { x: number; w: number }[] = [];
    const holiSet = new Map<string, Xl2NgayLe>();
    for (const h of ngayLe) holiSet.set(h.ngay, h);
    for (let d = winStart; d < winEnd; d += 1440) {
      dayLines.push(scale.xOf(d));
      const w = fromWall(d);
      const ymd = `${w.y}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
      if (holiSet.has(ymd)) holidays.push({ x: scale.xOf(d), w: 1440 * scale.ppm });
      for (const [s, e, overnight] of ca) {
        const bStart = d + s;
        const bEnd = overnight ? d + 1440 + e : d + e;
        const x = scale.xOf(bStart);
        const x2 = scale.xOf(bEnd);
        if (x2 > x) shifts.push({ x, w: x2 - x });
      }
    }
    return { dayLines, holidays, shifts };
  }, [ca, ngayLe, winStart, winEnd, scale]);

  // Overlay F1: gom vùng khoá máy + tải máy/ngày + đỉnh quân số tổ/ngày về map theo tài nguyên (O(1) khi vẽ).
  const overlay = useMemo(() => {
    // Tổng phút LÀM VIỆC trong một ngày (mẫu số tính % tải máy); ca rỗng ⇒ trần 24h.
    const caPhut = ca.reduce((n, [s, e, overnight]) => n + Math.max(0, (overnight ? 1440 + e : e) - s), 0);
    const availPerDay = caPhut > 0 ? caPhut : 1440;

    const khoaByMay = new Map<number, { x: number; w: number; title: string }[]>();
    for (const k of khoaMay) {
      const s = wallMinutes(k.start_at);
      const f = wallMinutes(k.finish_at);
      if (!Number.isFinite(s) || !Number.isFinite(f)) continue;
      const arr = khoaByMay.get(k.may_id) ?? khoaByMay.set(k.may_id, []).get(k.may_id)!;
      arr.push({ x: scale.xOf(s), w: Math.max((f - s) * scale.ppm, 2), title: `Khoá máy · ${ngayGio(k.start_at)}–${ngayGio(k.finish_at)}` });
    }

    const taiMayByDay = new Map<number, Map<number, { pct: number; phut: number }>>();
    for (const t of taiMay) {
      const day = ngayToWall(t.ngay);
      if (!Number.isFinite(day)) continue;
      const pct = Math.max(0, Math.min(t.phut_ban / availPerDay, 1));
      const m = taiMayByDay.get(t.may_id) ?? taiMayByDay.set(t.may_id, new Map()).get(t.may_id)!;
      m.set(day, { pct, phut: t.phut_ban });
    }

    const taiToByDept = new Map<number, Map<number, Xl2TaiTo>>();
    for (const t of taiTo) {
      const day = ngayToWall(t.ngay);
      if (!Number.isFinite(day)) continue;
      const m = taiToByDept.get(t.department_id) ?? taiToByDept.set(t.department_id, new Map()).get(t.department_id)!;
      m.set(day, t);
    }
    return { khoaByMay, taiMayByDay, taiToByDept };
  }, [khoaMay, taiMay, taiTo, ca, scale]);

  // Thước: nhãn ngày + tick giờ.
  const ruler = useMemo(() => {
    const days: { x: number; w: number; label: string; holiday: boolean }[] = [];
    const holiSet = new Set(ngayLe.map((h) => h.ngay));
    const WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
    for (let d = winStart; d < winEnd; d += 1440) {
      const w = fromWall(d);
      const ymd = `${w.y}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
      const wd = WD[new Date(Date.UTC(w.y, w.mo - 1, w.d)).getUTCDay()];
      days.push({
        x: scale.xOf(d), w: 1440 * scale.ppm,
        label: `${wd} ${String(w.d).padStart(2, "0")}/${String(w.mo).padStart(2, "0")}`,
        holiday: holiSet.has(ymd),
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
  }, [ngayLe, winStart, winEnd, scale, zoom]);

  const nowX = useMemo(() => {
    const n = nowWall();
    return n >= winStart && n <= winEnd ? scale.xOf(n) : null;
  }, [winStart, winEnd, scale]);

  // --------- kéo-thả (Pointer Events) ---------
  const [ghost, setGhost] = useState<Ghost | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const acRef = useRef<AbortController | null>(null);
  const trackReg = useRef<Map<string, HTMLDivElement>>(new Map());
  const draggedRef = useRef(false);
  const env = useRef({ scale, zoom, laneByKey });
  env.current = { scale, zoom, laneByKey };
  useEffect(() => () => acRef.current?.abort(), []);

  const registerTrack = useCallback((key: string, el: HTMLDivElement | null) => {
    if (el) trackReg.current.set(key, el);
    else trackReg.current.delete(key);
  }, []);

  const onMove = useCallback((e: PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.fromX, e.clientY - d.fromY) <= DRAG_THRESH) return;
    d.moved = true;
    e.preventDefault();
    const { scale: sc, zoom: zm, laneByKey: lanes } = env.current;
    let laneKey: string | null = null;
    let rect: DOMRect | null = null;
    for (const [k, el] of trackReg.current) {
      const rc = el.getBoundingClientRect();
      if (e.clientY >= rc.top && e.clientY <= rc.bottom) { laneKey = k; rect = rc; break; }
    }
    const lane = laneKey ? lanes.get(laneKey) ?? null : null;
    let startWall: number | null = null;
    let valid = false;
    if (rect && lane && !lane.packed) {
      const snap = SNAP_MIN[zm];
      const raw = sc.tOf(e.clientX - rect.left);
      startWall = Math.round(raw / snap) * snap;
      startWall = Math.max(sc.winStart, Math.min(startWall, sc.winEnd - d.durMin));
      valid = true;
    }
    d.targetLaneKey = laneKey; d.startWall = startWall; d.valid = valid;
    // Phản hồi client: đè dòng khác trên lane?
    let collide = false;
    if (startWall != null && lane) {
      const end = startWall + d.durMin;
      for (const rr of lane.dong) {
        if (rr.id === d.dongId || !rr.start_at || !rr.finish_at) continue;
        if (wallMinutes(rr.start_at) < end && startWall < wallMinutes(rr.finish_at)) { collide = true; break; }
      }
    }
    setGhost(laneKey && startWall != null
      ? { laneKey, x: sc.xOf(startWall), w: Math.max(d.durMin * sc.ppm, 14), valid, collide, label: hh(startWall) }
      : null);
  }, []);

  const buildPatch = useCallback((d: DragState): Xl2Patch | null => {
    if (d.startWall == null || !d.targetLaneKey) return null;
    const lane = env.current.laneByKey.get(d.targetLaneKey);
    if (!lane || lane.packed) return null;
    const patch: Xl2Patch = { start_at: wallToNaive(d.startWall) };
    const fromKey = dongLaneKey(d.dong);
    if (lane.key !== fromKey) {
      if (lane.cluster === "may") { patch.may_id = lane.resId; patch.department_id = null; }
      else if (lane.cluster === "to") { patch.department_id = lane.resId; patch.may_id = null; }
      else { patch.may_id = null; patch.department_id = null; }
    }
    return patch;
  }, []);

  const onUp = useCallback(() => {
    acRef.current?.abort();
    const d = dragRef.current;
    dragRef.current = null;
    setGhost(null);
    if (!d) return;
    if (!d.moved) return;
    draggedRef.current = true;
    if (!d.valid) return;
    const patch = buildPatch(d);
    if (patch) onPropose(d.dongId, patch, d.dong);
  }, [buildPatch, onPropose]);

  const onCancel = useCallback(() => {
    acRef.current?.abort();
    dragRef.current = null;
    setGhost(null);
  }, []);

  const onBarDown = useCallback((dong: Xl2Dong, e: React.PointerEvent) => {
    if (!canUpdate || dong.is_locked || !dong.start_at) return;
    const startWall = wallMinutes(dong.start_at);
    const endWall = dong.finish_at ? wallMinutes(dong.finish_at) : startWall + 30;
    draggedRef.current = false;
    dragRef.current = {
      dongId: dong.id, dong, fromX: e.clientX, fromY: e.clientY,
      durMin: Math.max(5, endWall - startWall),
      moved: false, targetLaneKey: dongLaneKey(dong), startWall, valid: false,
    };
    const ac = new AbortController();
    acRef.current = ac;
    window.addEventListener("pointermove", onMove, { signal: ac.signal });
    window.addEventListener("pointerup", onUp, { signal: ac.signal });
    window.addEventListener("pointercancel", onCancel, { signal: ac.signal });
  }, [canUpdate, onMove, onUp, onCancel]);

  const onBarClick = useCallback((dong: Xl2Dong) => {
    if (draggedRef.current) { draggedRef.current = false; return; }
    onSelectDong(dong.id);
  }, [onSelectDong]);

  // A11y: phím thay kéo — ←/→ dời giờ theo bước snap; ↑/↓ đổi lane trong CÙNG cụm.
  const onBarKey = useCallback((dong: Xl2Dong, e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectDong(dong.id); return; }
    if (!canUpdate || dong.is_locked) return;
    if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && dong.start_at) {
      const base = wallMinutes(dong.start_at);
      if (!Number.isFinite(base)) return;
      e.preventDefault();
      const step = SNAP_MIN[zoom] * (e.key === "ArrowRight" ? 1 : -1);
      const nt = Math.max(winStart, Math.min(base + step, winEnd - 5));
      onPropose(dong.id, { start_at: wallToNaive(nt) }, dong);
    } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      const cluster = clusters.find((c) => c.lanes.some((l) => l.key === dongLaneKey(dong)));
      if (!cluster) return;
      const lanes = cluster.lanes.filter((l) => !l.packed);
      const i = lanes.findIndex((l) => l.key === dongLaneKey(dong));
      const nb = lanes[i + (e.key === "ArrowDown" ? 1 : -1)];
      if (!nb || !dong.start_at) return;
      e.preventDefault();
      const patch: Xl2Patch = { start_at: dong.start_at };
      if (nb.cluster === "may") { patch.may_id = nb.resId; patch.department_id = null; }
      else if (nb.cluster === "to") { patch.department_id = nb.resId; patch.may_id = null; }
      else { patch.may_id = null; patch.department_id = null; }
      onPropose(dong.id, patch, dong);
    }
  }, [canUpdate, zoom, winStart, winEnd, clusters, onPropose, onSelectDong]);

  const fullW = LABEL_W + scale.width;
  const laneStyle: CSSProperties = { "--xl2-label-w": `${LABEL_W}px`, "--xl2-bar-h": `${BAR_H}px` } as CSSProperties;

  return (
    <div className="xl2-gantt__scroll">
      <div className="xl2-gantt__inner" style={{ width: fullW, ...laneStyle }}>
        {/* thước */}
        <div className="xl2-ruler" style={{ width: fullW }}>
          <div className="xl2-ruler__spacer" />
          {ruler.days.map((d, i) => (
            <div
              key={`d${i}`}
              className={`xl2-ruler__day${d.holiday ? " xl2-ruler__day--holiday" : ""}`}
              style={{ left: LABEL_W + d.x, width: d.w }}
            >
              {d.label}
            </div>
          ))}
          {ruler.ticks.map((t, i) => (
            <div key={`t${i}`} className="xl2-ruler__tick" style={{ left: LABEL_W + t.x }}>
              {t.label}
            </div>
          ))}
        </div>

        {/* các cụm */}
        {clusters.map((cluster) => (
          <div key={cluster.key} className={`xl2-cluster xl2-cluster--${cluster.key}`}>
            <div className="xl2-cluster__headbg" style={{ width: fullW }} />
            <div className="xl2-cluster__head">
              <Icon name={cluster.icon} size={13} />
              <span>{cluster.label}</span>
              {(() => {
                const viec = demViecLanes(cluster.lanes);
                const unit = cluster.key === "may" ? "máy" : cluster.key === "to" ? "tổ" : "đối tác";
                return cluster.key === "cho"
                  ? <b>· {viec} việc</b>
                  : <b>· {cluster.lanes.length} {unit} · {viec} việc</b>;
              })()}
            </div>
            {cluster.lanes.length === 0 ? (
              <div className="xl2-lane xl2-lane--dim">
                <div className="xl2-lane__label"><span className="xl2-lane__name">— trống —</span></div>
              </div>
            ) : cluster.lanes.map((lane) => (
              <div key={lane.key} className="xl2-lane">
                <div className="xl2-lane__label" title={lane.label}>
                  <Icon name={cluster.icon} size={12} />
                  <span className="xl2-lane__name">{lane.label}</span>
                </div>
                <div
                  className="xl2-lane__track"
                  style={{ width: scale.width }}
                  ref={(el) => registerTrack(lane.key, el)}
                >
                  {/* nền */}
                  {!lane.packed && (
                    <>
                      {bg.shifts.map((s, i) => (
                        <div key={`s${i}`} className="xl2-shift" style={{ left: s.x, width: s.w }} />
                      ))}
                      {bg.holidays.map((h, i) => (
                        <div key={`h${i}`} className="xl2-holiday" style={{ left: h.x, width: h.w }} />
                      ))}
                      {bg.dayLines.map((x, i) => (
                        <div key={`g${i}`} className="xl2-daygrid" style={{ left: x }} />
                      ))}
                      {nowX != null && <div className="xl2-nowline" style={{ left: nowX }} />}
                    </>
                  )}
                  {/* overlay F1 — lane Máy: vùng khoá + dải nhiệt tải máy (sau thanh, z:1) */}
                  {!lane.packed && lane.cluster === "may" && lane.resId != null && (
                    <>
                      {overlay.khoaByMay.get(lane.resId)?.map((k, i) => (
                        <div key={`kh${i}`} className="xl2-khoa" style={{ left: k.x, width: k.w }} title={k.title} />
                      ))}
                      {[...(overlay.taiMayByDay.get(lane.resId)?.entries() ?? [])].map(([dayWall, v]) => (
                        <div
                          key={`ld${dayWall}`}
                          className={`xl2-load xl2-load--h${heatBucket(v.pct)}`}
                          style={{ left: scale.xOf(dayWall), width: 1440 * scale.ppm }}
                          title={`Máy chạy ${thoiLuong(v.phut)} (${Math.round(v.pct * 100)}%)`}
                        >
                          {v.pct >= 0.6 && <span className="xl2-load__n">{Math.round(v.pct * 100)}%</span>}
                        </div>
                      ))}
                    </>
                  )}
                  {/* overlay F1 — lane Tổ: nhiệt đỉnh quân số/ngày */}
                  {!lane.packed && lane.cluster === "to" && lane.resId != null && (
                    <>
                      {[...(overlay.taiToByDept.get(lane.resId)?.entries() ?? [])].map(([dayWall, t]) => {
                        const over = t.dinh > t.so_nguoi && !t.go_de;
                        const cls = over ? "xl2-heat--over" : t.go_de ? "xl2-heat--ok" : "xl2-heat--calm";
                        return (
                          <div
                            key={`ht${dayWall}`}
                            className={`xl2-heat ${cls}`}
                            style={{ left: scale.xOf(dayWall), width: 1440 * scale.ppm }}
                            title={over ? `Quá tải: cần ${t.dinh}, có ${t.so_nguoi}`
                              : t.go_de ? `Đã duyệt vượt: cần ${t.dinh}, có ${t.so_nguoi}`
                                : `Đỉnh ${t.dinh}/${t.so_nguoi}`}
                          >
                            {(over || t.go_de) && (
                              <span className="xl2-heat__n">
                                {over && <Icon name="alert" size={10} />}{t.dinh}/{t.so_nguoi}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </>
                  )}
                  {/* thanh việc */}
                  {lane.dong.map((dong, idx) => {
                    const timed = !lane.packed && !!dong.start_at;
                    const sW = dong.start_at ? wallMinutes(dong.start_at) : NaN;
                    const eW = dong.finish_at ? wallMinutes(dong.finish_at) : sW + 30;
                    const left = timed ? scale.xOf(sW) : idx * (PACK_W + 6);
                    const width = timed ? Math.max((eW - sW) * scale.ppm, 16) : PACK_W;
                    const muc = barMuc.get(dong.id) ?? null;
                    const sel = dong.id === selectedDongId;
                    const chain = !sel && selectedEntityKey != null && dongEntityKey(dong) === selectedEntityKey;
                    const mucCls = muc ? ` xl2-bar--${muc === "chan_dat_lich" ? "dat" : muc === "chan_phat_hanh" ? "ph" : "warn"}` : "";
                    const canDrag = canUpdate && !dong.is_locked && timed;
                    // F2 "râu" bóc-tách: chỉ khi đã có giờ + thanh đủ rộng (<40px thì gộp 1 màu).
                    const bt = dong.boc_tach;
                    const btUncertain = !!bt && bt.chiem_may_phut_max > bt.chiem_may_phut_min;
                    const btTitle = bt
                      ? ` · canh ${thoiLuong(bt.canh_may_phut)} · chạy ${thoiLuong(bt.chay_phut)} · khác ${thoiLuong(bt.khac_phut)}`
                        + (btUncertain
                          ? ` · chiếm ${thoiLuong(bt.chiem_may_phut_min)}–${thoiLuong(bt.chiem_may_phut_max)}`
                          : ` · chiếm ${thoiLuong(bt.chiem_may_phut)}`)
                      : "";
                    // Nhãn dẫn xuất: SERIAL ngắn (bỏ tiền tố năm dùng-chung) + CÔNG ĐOẠN đang xếp.
                    // §10.3 — nhãn ĐỌC ĐƯỢC ở MỌI zoom: rộng thì serial+công-đoạn NẰM TRONG thanh;
                    // hẹp thì tràn ra PHẢI thanh (`.xl2-bar__spill`, track overflow-visible), không cắt.
                    const nhan = dongNhanParts(dong);
                    const serial = dongSerial(dong);
                    const wide = width >= 128;          // đủ chỗ cho serial + công đoạn trong thanh
                    const tiny = width < 44;            // hẹp tới mức serial cũng phải ra ngoài
                    const spillText = tiny
                      ? `${serial}${nhan.congDoan ? ` · ${nhan.congDoan}` : ""}`
                      : (nhan.congDoan ?? "");
                    // Chỉ tràn nhãn cho thanh CÓ GIỜ trên trục; chip nháp "chưa đặt giờ" xếp sát nhau
                    // (PACK_W) nên tràn sẽ đè chip kế — ở đó dựa vào serial-trong-chip + tooltip.
                    const showSpill = timed && !wide && spillText !== "";
                    return (
                      <Fragment key={dong.id}>
                      <button
                        type="button"
                        className={`xl2-bar${mucCls}${sel ? " xl2-bar--sel" : ""}${chain ? " xl2-bar--chain" : ""}${dong.is_locked ? " xl2-bar--locked" : ""}${canDrag ? " xl2-bar--draggable" : ""}${!timed ? " xl2-bar--pack" : ""}`}
                        style={{ left, width }}
                        title={`${nhan.ma}${nhan.congDoan ? ` · ${nhan.congDoan}` : ""}${nhan.sanPham ? ` · ${nhan.sanPham}` : ""}${dong.start_at ? ` · ${ngayGio(dong.start_at)}` : " · chưa đặt giờ"}${dong.is_locked ? " · đã khóa" : ""}${btTitle}`}
                        aria-label={`${nhan.ma}${nhan.congDoan ? `, ${nhan.congDoan}` : ""}${nhan.sanPham ? `, ${nhan.sanPham}` : ""}${dong.start_at ? `, bắt đầu ${ngayGio(dong.start_at)}` : ", chưa đặt giờ"}`}
                        onPointerDown={canDrag ? (e) => onBarDown(dong, e) : undefined}
                        onClick={() => onBarClick(dong)}
                        onKeyDown={(e) => onBarKey(dong, e)}
                      >
                        <Icon name={dong.is_locked ? "lock" : muc ? XL2_MUC_META[muc].icon : nguonIcon(dong.nguon)} size={12} />
                        {!tiny && <span className="xl2-bar__code">{serial}</span>}
                        {wide && nhan.congDoan && <span className="xl2-bar__cd">{nhan.congDoan}</span>}
                        {timed && bt && width >= 40 && (() => {
                          const tot = bt.chiem_may_phut || 1;
                          const pc = (m: number) => `${((m / tot) * 100).toFixed(2)}%`;
                          return (
                            <>
                              <span className="xl2-bar__rau" aria-hidden="true">
                                <span className="xl2-rau-seg xl2-rau-seg--canh" style={{ width: pc(bt.canh_may_phut) }} />
                                <span className="xl2-rau-seg xl2-rau-seg--chay" style={{ width: pc(bt.chay_phut) }} />
                                <span className="xl2-rau-seg xl2-rau-seg--khac" style={{ width: pc(bt.khac_phut) }} />
                              </span>
                              {btUncertain && (
                                <span
                                  className="xl2-whisker"
                                  aria-hidden="true"
                                  style={{
                                    left: `${(bt.chiem_may_phut_min / tot) * 100}%`,
                                    width: `${((bt.chiem_may_phut_max - bt.chiem_may_phut_min) / tot) * 100}%`,
                                  }}
                                />
                              )}
                            </>
                          );
                        })()}
                      </button>
                      {showSpill && (
                        <span
                          className={`xl2-bar__spill${sel ? " is-sel" : ""}`}
                          style={{ left: left + width + 6 }}
                          aria-hidden="true"
                        >{spillText}</span>
                      )}
                      </Fragment>
                    );
                  })}
                  {/* ghost khi kéo trúng lane này */}
                  {ghost && ghost.laneKey === lane.key && (
                    <div
                      className={`xl2-ghost${!ghost.valid ? " xl2-ghost--bad" : ""}${ghost.collide ? " xl2-ghost--collide" : ""}`}
                      style={{ left: ghost.x, width: ghost.w }}
                    >
                      {ghost.label}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Lane-key của một dòng theo tài nguyên hiện gán (khớp cách controller dựng lane). */
function dongLaneKey(d: Xl2Dong): string {
  if (d.may_id != null) return `may:${d.may_id}`;
  if (d.department_id != null) return `to:${d.department_id}`;
  if (d.start_at) return `ncc:${(d.nha_cung_cap ?? "").trim() || "_"}`;
  return "cho:_";
}
