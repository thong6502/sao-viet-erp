// GANTT của màn XẾP LỊCH 2 — kế thừa CƠ CHẾ kéo-thả của GanttBoard cũ (Pointer Events + AbortController
// + ghost + a11y phím) nhưng VIẾT LẠI dưới `.xl2-`, và trục THUẦN TUYẾN TÍNH: v2 việc chạy LIÊN TỤC
// (finish = start + chiếm-máy theo đồng-hồ-tường), KHÔNG cắt theo ca ⇒ không dùng buildScale/snapToWork.
//
// Ba CỤM lane: Máy · Tổ · Thuê ngoài, cộng cụm "Chưa đặt giờ" (dòng nháp chưa gán máy/giờ, xếp chip
// tuần tự). Kéo NGANG đổi giờ; kéo DỌC sang lane khác đổi tài nguyên (máy↔tổ). Mỗi cú kéo/nhấn phím chỉ
// ĐỀ XUẤT một patch — controller mới gọi xem-trước rồi ghi (một cửa duy nhất). Component này KHÔNG gọi API.
import {
  useCallback, useEffect, useMemo, useRef, useState, type CSSProperties,
} from "react";
import type { IconName } from "../components/Icons";
import type {
  Xl2Ca, Xl2CaNhan, Xl2Dong, Xl2KhoaMay, Xl2Muc, Xl2NgayLe, Xl2QRow, Xl2TaiMay, Xl2TaiTo,
} from "../api/client";
import { ngayGio, num, thoiLuong, thoiLuongNgan } from "./keHoachSxShared";
import {
  BAR_H, CLUSTER_HEAD_H, LANE_H, LABEL_W, buildLinearScale, demViecLanes, dongHue, dongEntityKey, dongNhanParts,
  dongSerial, ngayToWall, wallToNaive, type Xl2Zoom,
} from "./xl2Shared";
import { wallMinutes, fromWall, nowWall } from "./gantt-time";

// --------------------------------------------------------------------------
export type Xl2ClusterKey = "may" | "to" | "ncc" | "cho" | "lenh";

/** Cách xếp lane: theo TÀI NGUYÊN (máy · tổ · thuê ngoài — mặt phẳng lịch xưởng) hay theo LỆNH (mỗi
 *  LSX / bài ghép MỘT lane, cả chuỗi công đoạn nằm trên một hàng để nhìn ra đường đi của cả lệnh).
 *  Cùng một bàn, cùng một bộ dữ liệu — chỉ đổi cách gom lane, không gọi thêm API. */
export type Xl2Nhom = "tai_nguyen" | "lenh";

export interface Xl2Lane {
  key: string;                 // "may:12" | "to:3" | "ncc:_" | "cho:_"
  cluster: Xl2ClusterKey;
  resId: number | null;        // may_id | department_id | null
  label: string;
  /** Nhãn PHỤ dưới tên lane (vd tên sản phẩm của lệnh) — chỉ hiện khi có. */
  sub?: string | null;
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
  /** Ca nền KÈM TÊN (§7.1) — để ruy-băng gọi được "Ca 2" thay vì tô một dải xám vô danh. */
  caNhan: Xl2CaNhan[];
  /** Lane đang gom theo tài nguyên hay theo lệnh (đổi cả ý nghĩa của kéo DỌC). */
  nhom: Xl2Nhom;
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
  onDropQueue?: (r: Xl2QRow, lane: Xl2Lane) => void;
}

const SNAP_MIN: Record<Xl2Zoom, number> = { gio: 5, ca: 15, ngay: 30, tuan: 60 };
const TICK_MIN: Record<Xl2Zoom, number> = { gio: 60, ca: 180, ngay: 360, tuan: 1440 };
const DRAG_THRESH = 4;
const PACK_W = 100; // bề rộng chip "chưa đặt giờ"
// Ngưỡng lệch giờ (phút) tính là "trễ đáng kể" khi vẽ lớp thực tế — PHẢI khớp
// NGUONG_LECH_THUC_TE_PHUT bên backend (backend/app/services/xep_lich_van_de_service.py).
const NGUONG_LECH_THUC_TE_PHUT = 60;

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

/** Phút-trong-ngày → "HH:MM" (ca khai bằng phút từ 00:00; qua đêm thì cộng dồn quá 1440 rồi mới gói). */
function hhm(m: number): string {
  const t = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

export function Xl2Gantt({
  clusters, ca, caNhan, nhom, ngayLe, khoaMay, taiMay, taiTo, winTu, winDen, zoom,
  selectedDongId, selectedEntityKey, barMuc, canUpdate, onSelectDong, onPropose, onDropQueue,
}: Props) {
  const winStart = ngayToWall(winTu);
  const winEnd = ngayToWall(winDen) + 1440; // hết ngày "den"
  const scale = useMemo(() => buildLinearScale(winStart, winEnd, zoom), [winStart, winEnd, zoom]);

  // Hover state cho toàn bộ chuỗi thực thể (Chain Glow effect)
  const [hoverEntityKey, setHoverEntityKey] = useState<string | null>(null);

  // Tra cứu lane theo key (cho hit-test khi kéo).
  const laneByKey = useMemo(() => {
    const m = new Map<string, Xl2Lane>();
    for (const c of clusters) for (const l of c.lanes) m.set(l.key, l);
    return m;
  }, [clusters]);

  // BỐ CỤC CA — tính MỘT LẦN rồi dùng cho cả ruy-băng trên thước lẫn vạch mốc trong lane.
  //
  // Trước đây mỗi ca vẽ thành một dải phủ kín chiều cao lane bằng đúng màu đường kẻ, mà ca xưởng lại
  // GỐI NHAU (hành chính 8–17 nằm đè Ca 1 6–14, Ca 2 14–22…) nên bốn ca chồng lên nhau thành một
  // mảng xám phủ trọn 24h — nhìn không ra ca nào với ca nào. Nay: ca nào ra ca nấy, TÁCH HÀNG khi
  // gối nhau, có TÊN; trong lane chỉ còn vạch MỐC BẮT ĐẦU — đúng với luật v2 (§7.1 chỉ soi giờ bắt
  // đầu, việc đã chạy thì chạy liên tục xuyên ca).
  const caLayout = useMemo(() => {
    const src = caNhan.length
      ? caNhan.map((c) => ({ ten: c.ten, s: c.bat_dau_phut, e: c.ket_thuc_phut, qd: c.qua_dem }))
      : ca.map(([s, e, od], i) => ({ ten: `Ca ${i + 1}`, s, e, qd: od }));
    // Đoạn chiếm trong MỘT ngày; ca qua đêm cắt làm hai ([s,1440) và [0,e)) để xếp hàng không bị đè
    // bởi chính phần tràn sang hôm sau.
    const segsOf = (c: { s: number; e: number; qd: boolean }): [number, number][] =>
      c.qd || c.e <= c.s ? [[c.s, 1440], [0, c.e]] : [[c.s, c.e]];
    const rows: [number, number][][] = [];
    const items = src.map((c, i) => {
      const segs = segsOf(c).filter(([a, b]) => b > a);
      let r = rows.findIndex((occ) => segs.every(([a, b]) => occ.every(([x, y]) => b <= x || a >= y)));
      if (r < 0) { r = rows.length; rows.push([]); }
      rows[r].push(...segs);
      return { ten: c.ten, s: c.s, idx: i, row: r, dai: (c.qd || c.e <= c.s ? 1440 + c.e : c.e) - c.s };
    });
    // Giờ KHÔNG ca nào phủ = xưởng không ai trực. Phần bù của hợp các đoạn — xưởng phủ kín 24h thì
    // mảng này rỗng, và đó là câu trả lời thật chứ không phải lỗi vẽ.
    const phu = items
      .flatMap((c) => (c.dai >= 1440 ? [[0, 1440] as [number, number]]
        : c.s + c.dai > 1440 ? [[c.s, 1440] as [number, number], [0, c.s + c.dai - 1440] as [number, number]]
          : [[c.s, c.s + c.dai] as [number, number]]))
      .sort((a, b) => a[0] - b[0]);
    const trong: [number, number][] = [];
    let cur = 0;
    for (const [a, b] of phu) {
      if (a > cur) trong.push([cur, a]);
      cur = Math.max(cur, b);
    }
    if (cur < 1440) trong.push([cur, 1440]);
    return { items, rows: Math.max(rows.length, 1), trong };
  }, [ca, caNhan]);

  // Nền: lưới ngày + tô ngày lễ + vạch mốc bắt đầu ca + khoảng ngoài mọi ca.
  const bg = useMemo(() => {
    const dayLines: number[] = [];
    const holidays: { x: number; w: number }[] = [];
    const caStarts: { x: number; idx: number; title: string }[] = [];
    const nonwork: { x: number; w: number }[] = [];
    const holiSet = new Map<string, Xl2NgayLe>();
    for (const h of ngayLe) holiSet.set(h.ngay, h);
    for (let d = winStart; d < winEnd; d += 1440) {
      dayLines.push(scale.xOf(d));
      const w = fromWall(d);
      const ymd = `${w.y}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
      if (holiSet.has(ymd)) holidays.push({ x: scale.xOf(d), w: 1440 * scale.ppm });
      for (const c of caLayout.items) {
        caStarts.push({ x: scale.xOf(d + c.s), idx: c.idx, title: `${c.ten} bắt đầu ${hhm(c.s)}` });
      }
      for (const [a, b] of caLayout.trong) {
        const x = scale.xOf(d + a);
        nonwork.push({ x, w: Math.max(scale.xOf(d + b) - x, 1) });
      }
    }
    return { dayLines, holidays, caStarts, nonwork };
  }, [caLayout, ngayLe, winStart, winEnd, scale]);

  // Ruy-băng ca dưới thước: mỗi ngày lặp lại đúng bộ ca, mỗi ca một thanh CÓ TÊN ở hàng của nó.
  const ribbon = useMemo(() => {
    const out: { x: number; w: number; row: number; idx: number; ten: string; gio: string }[] = [];
    // Lùi MỘT NGÀY trước mép trái: ca qua đêm (Ca 3 22:00–06:00) khởi hành từ HÔM TRƯỚC, mà vòng lặp
    // cũ bắt đầu đúng `winStart` nên khúc 00:00–06:00 của ngày đầu cửa sổ không ai vẽ. Người xem thấy
    // dải trống rồi kết luận "máy xếp việc ngoài ca" — trong khi engine xếp ĐÚNG luật, chỉ là cái ca
    // hợp lệ đó không được tô. `scale.xOf` tự kẹp về 0 nên phần thò ra trái không đè cột nhãn.
    for (let d = winStart - 1440; d < winEnd; d += 1440) {
      for (const c of caLayout.items) {
        const x = scale.xOf(d + c.s);
        const x2 = scale.xOf(d + c.s + c.dai);
        if (x2 <= x) continue;
        out.push({ x, w: x2 - x, row: c.row, idx: c.idx, ten: c.ten, gio: `${hhm(c.s)}–${hhm(c.s + c.dai)}` });
      }
    }
    return out;
  }, [caLayout, winStart, winEnd, scale]);

  // Overlay F1: gom vùng khoá máy + tải máy/ngày + đỉnh quân số tổ/ngày về map theo tài nguyên (O(1) khi vẽ).
  const overlay = useMemo(() => {
    // MẪU SỐ của % tải = số phút trong ngày xưởng THỰC SỰ có ca phủ. Lấy từ phần bù của
    // `caLayout.trong` (khoảng không ca nào phủ) — tức chính cái đang được VẼ trên ruy-băng ca, nên
    // con số luôn khớp với hình. CỘNG THẲNG độ dài từng ca là SAI: ca xưởng gối nhau (Hành chính
    // 08:00–17:00 nằm gọn trong Ca 1 + Ca 2) nên tổng ra 1980' cho một ngày chỉ có 1440' ⇒ mọi %
    // tải thấp giả ~27% (sửa 22/08/2026, khớp `constraint.phut_ca_moi_ngay` bên máy chủ).
    // Từ mg 0227 máy chủ chỉ gửi ca có cờ `ca_san_xuat` (ca văn phòng ở lại màn Ca kíp), nên ruy-băng
    // ca và mẫu số này cùng nói về MỘT thứ: giờ xưởng có người đứng máy.
    const caPhut = 1440 - caLayout.trong.reduce((n, [a, b]) => n + Math.max(0, b - a), 0);
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
  }, [khoaMay, taiMay, taiTo, caLayout, scale]);

  // Thước: nhãn ngày + tick giờ 2 tầng hiện đại.
  const todayYmd = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, []);

  const ruler = useMemo(() => {
    const days: { x: number; w: number; label: string; wd: string; dayNum: string; isToday: boolean; isWeekend: boolean; holiday: boolean }[] = [];
    const holiSet = new Set(ngayLe.map((h) => h.ngay));
    const WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
    for (let d = winStart; d < winEnd; d += 1440) {
      const w = fromWall(d);
      const ymd = `${w.y}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
      const dayIdx = new Date(Date.UTC(w.y, w.mo - 1, w.d)).getUTCDay();
      const wd = WD[dayIdx];
      const isWeekend = dayIdx === 0 || dayIdx === 6;
      const isToday = ymd === todayYmd;
      days.push({
        x: scale.xOf(d),
        w: 1440 * scale.ppm,
        label: `${wd} ${String(w.d).padStart(2, "0")}/${String(w.mo).padStart(2, "0")}`,
        wd,
        dayNum: `${String(w.d).padStart(2, "0")}/${String(w.mo).padStart(2, "0")}`,
        isToday,
        isWeekend,
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
  }, [ngayLe, winStart, winEnd, scale, zoom, todayYmd]);

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
    // Gom theo LỆNH: lane = một LSX, không phải một tài nguyên ⇒ kéo chỉ đổi GIỜ. Thả sang lane
    // lệnh khác thì bỏ qua hẳn (không ai "chuyển bước sang lệnh khác" bằng cách kéo thanh).
    if (lane.cluster === "lenh") {
      return lane.key === dongLaneKey(d.dong, "lenh") ? patch : null;
    }
    const fromKey = dongLaneKey(d.dong, "tai_nguyen");
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
      moved: false, targetLaneKey: dongLaneKey(dong, nhom), startWall, valid: false,
    };
    const ac = new AbortController();
    acRef.current = ac;
    window.addEventListener("pointermove", onMove, { signal: ac.signal });
    window.addEventListener("pointerup", onUp, { signal: ac.signal });
    window.addEventListener("pointercancel", onCancel, { signal: ac.signal });
  }, [canUpdate, nhom, onMove, onUp, onCancel]);

  const onBarClick = useCallback((dong: Xl2Dong) => {
    if (draggedRef.current) { draggedRef.current = false; return; }
    onSelectDong(dong.id);
  }, [onSelectDong]);

  // A11y: phím thay kéo
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
      if (nhom === "lenh") return;   // lane = lệnh, đổi lane không có nghĩa gì
      const cluster = clusters.find((c) => c.lanes.some((l) => l.key === dongLaneKey(dong, nhom)));
      if (!cluster) return;
      const lanes = cluster.lanes.filter((l) => !l.packed);
      const i = lanes.findIndex((l) => l.key === dongLaneKey(dong, nhom));
      const nb = lanes[i + (e.key === "ArrowDown" ? 1 : -1)];
      if (!nb || !dong.start_at) return;
      e.preventDefault();
      const patch: Xl2Patch = { start_at: dong.start_at };
      if (nb.cluster === "may") { patch.may_id = nb.resId; patch.department_id = null; }
      else if (nb.cluster === "to") { patch.department_id = nb.resId; patch.may_id = null; }
      else { patch.may_id = null; patch.department_id = null; }
      onPropose(dong.id, patch, dong);
    }
  }, [canUpdate, nhom, zoom, winStart, winEnd, clusters, onPropose, onSelectDong]);

  // Tính toán tọa độ Y chính xác của từng lane để vẽ đường nối SVG
  const laneYMap = useMemo(() => {
    const map = new Map<string, number>();
    let currentY = 44; // Ruler height
    for (const cluster of clusters) {
      currentY += CLUSTER_HEAD_H;
      if (cluster.lanes.length === 0) {
        currentY += LANE_H;
      } else {
        for (const lane of cluster.lanes) {
          map.set(lane.key, currentY + 8 + BAR_H / 2);
          currentY += LANE_H;
        }
      }
    }
    return { map, totalHeight: currentY };
  }, [clusters]);

  // Vẽ đường cong liên kết thứ tự quy trình (Dependency Flow Curves)
  const dependencyCurves = useMemo(() => {
    const activeKey = hoverEntityKey || selectedEntityKey;
    if (!activeKey) return [];
    const items: { dong: Xl2Dong; laneKey: string; x1: number; x2: number; y: number }[] = [];
    for (const cluster of clusters) {
      for (const lane of cluster.lanes) {
        if (lane.packed) continue;
        const y = laneYMap.map.get(lane.key);
        if (y == null) continue;
        for (const d of lane.dong) {
          if (dongEntityKey(d) === activeKey && d.start_at) {
            const sW = wallMinutes(d.start_at);
            const eW = d.finish_at ? wallMinutes(d.finish_at) : sW + 30;
            items.push({
              dong: d,
              laneKey: lane.key,
              x1: LABEL_W + scale.xOf(sW),
              x2: LABEL_W + scale.xOf(eW),
              y,
            });
          }
        }
      }
    }
    items.sort((a, b) => (a.dong.buoc_thu_tu ?? 0) - (b.dong.buoc_thu_tu ?? 0));
    const curves: { id: string; d: string; hasConflict: boolean; xMid: number; yMid: number }[] = [];
    for (let i = 0; i < items.length - 1; i++) {
      const from = items[i];
      const to = items[i + 1];
      const xFrom = from.x2;
      const yFrom = from.y;
      const xTo = to.x1;
      const yTo = to.y;
      const hasConflict = xTo < xFrom;
      const dx = Math.abs(xTo - xFrom);
      const cpOffset = Math.max(dx * 0.4, 28);
      const cp1x = xFrom + cpOffset;
      const cp1y = yFrom;
      const cp2x = xTo - cpOffset;
      const cp2y = yTo;
      const path = `M ${xFrom} ${yFrom} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${xTo} ${yTo}`;
      curves.push({
        id: `${from.dong.id}->${to.dong.id}`,
        d: path,
        hasConflict,
        xMid: (xFrom + xTo) / 2,
        yMid: (yFrom + yTo) / 2,
      });
    }
    return curves;
  }, [hoverEntityKey, selectedEntityKey, clusters, laneYMap, scale]);

  const scrollRef = useRef<HTMLDivElement | null>(null);

  const fullW = LABEL_W + scale.width;
  const laneStyle: CSSProperties = { "--xl2-label-w": `${LABEL_W}px`, "--xl2-bar-h": `${BAR_H}px` } as CSSProperties;

  return (
    <div className="xl2-gantt-wrap">
      <div className="xl2-gantt__scroll" ref={scrollRef}>
        <div className="xl2-gantt__inner" style={{ width: fullW, ...laneStyle }}>
          {/* Thước 2 tầng tích hợp Ca xưởng */}
          <div className="xl2-ruler" style={{ width: fullW }}>
            <div className="xl2-ruler__spacer" />
            {ruler.days.map((d, i) => (
              <div
                key={`d${i}`}
                className={`xl2-ruler__day${d.holiday ? " xl2-ruler__day--holiday" : ""}${d.isToday ? " xl2-ruler__day--today" : ""}${d.isWeekend ? " xl2-ruler__day--weekend" : ""}`}
                style={{ left: LABEL_W + d.x, width: d.w }}
              >
                <span className="xl2-ruler__wd">{d.wd}</span>
                <span className="xl2-ruler__dnum">{d.dayNum}</span>
                {d.isToday && <span className="xl2-ruler__today-dot" title="Hôm nay" />}
              </div>
            ))}
            {ruler.ticks.map((t, i) => (
              <div key={`t${i}`} className="xl2-ruler__tick" style={{ left: LABEL_W + t.x }}>
                {t.label}
              </div>
            ))}
          </div>

          {/* Ruy-băng Ca làm việc tích hợp */}
          <div className="xl2-carib" style={{ width: fullW, height: caLayout.rows * 16 + 6 }}>
            <div className="xl2-carib__spacer">
              <span>Ca làm việc</span>
            </div>
            {ribbon.map((b, i) => (
              <div
                key={`cb${i}`}
                className={`xl2-carib__ca xl2-carib__ca--c${b.idx % 5}`}
                style={{ left: LABEL_W + b.x, width: Math.max(b.w, 2), top: 3 + b.row * 16 }}
                title={`${b.ten} · ${b.gio}`}
              >
                {b.w >= 40 && <span className="xl2-carib__ten">{b.ten}</span>}
                {b.w >= 100 && <span className="xl2-carib__gio">{b.gio}</span>}
              </div>
            ))}
          </div>

          {/* SVG Dependency Flow Lines */}
          {dependencyCurves.length > 0 && (
            <svg
              className="xl2-svg-deps"
              style={{ width: fullW, height: laneYMap.totalHeight }}
              aria-hidden="true"
            >
              <defs>
                <marker id="xl2-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="var(--rust)" />
                </marker>
                <marker id="xl2-arrow-bad" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="var(--signal)" />
                </marker>
              </defs>
              {dependencyCurves.map((c) => (
                <g key={c.id}>
                  <path d={c.d} className="xl2-dep-path-glow" />
                  <path
                    d={c.d}
                    className={`xl2-dep-path${c.hasConflict ? " xl2-dep-path--bad" : ""}`}
                    markerEnd={c.hasConflict ? "url(#xl2-arrow-bad)" : "url(#xl2-arrow)"}
                  />
                  {!c.hasConflict && (
                    <circle r="3" fill="var(--rust)" className="xl2-dep-particle">
                      <animateMotion path={c.d} dur="1.8s" repeatCount="indefinite" />
                    </circle>
                  )}
                  {c.hasConflict && (
                    <circle cx={c.xMid} cy={c.yMid} r="4.5" className="xl2-dep-conflict-dot" />
                  )}
                </g>
              ))}
            </svg>
          )}

          {/* Vạch gióng từ tính khi đang kéo */}
          {ghost && (
            <div
              className={`xl2-magnetic-guide${!ghost.valid ? " xl2-magnetic-guide--bad" : ""}${ghost.collide ? " xl2-magnetic-guide--collide" : ""}`}
              style={{ left: LABEL_W + ghost.x }}
            >
              <div className="xl2-magnetic-badge">{ghost.label}</div>
            </div>
          )}

          {/* Các cụm tài nguyên */}
          {clusters.map((cluster) => (
            <div key={cluster.key} className={`xl2-cluster xl2-cluster--${cluster.key}`}>
              <div className="xl2-cluster__headbg" style={{ width: fullW }} />
              <div className="xl2-cluster__head">
                <span className="xl2-cluster__title">{cluster.label}</span>
                {(() => {
                  const viec = demViecLanes(cluster.lanes);
                  const unit = cluster.key === "may" ? "máy" : cluster.key === "to" ? "tổ"
                    : cluster.key === "lenh" ? "lệnh" : "đối tác";
                  return cluster.key === "cho"
                    ? <span className="xl2-cluster__count">· <b>{viec}</b> việc nháp</span>
                    : <span className="xl2-cluster__count">· {cluster.lanes.length} {unit} · <b>{viec}</b> việc</span>;
                })()}
              </div>
              {cluster.lanes.length === 0 ? (
                <div className="xl2-lane xl2-lane--dim">
                  <div className="xl2-lane__label"><span className="xl2-lane__name">— trống —</span></div>
                </div>
              ) : cluster.lanes.map((lane) => {
                // % tải = trung bình trên NHỮNG NGÀY CÓ VIỆC, không phải trên cả cửa sổ: máy rảnh 13
                // ngày đợi một bài thì câu trả lời hữu ích là "hôm chạy nó ken bao nhiêu", chứ không
                // phải một số gần 0 do chia đều. Kèm SỐ NGÀY vào tooltip để không bị đọc nhầm thành
                // tải của cả khung ngày đang xem.
                const tai = lane.cluster === "may" && lane.resId != null ? (() => {
                  const m = overlay.taiMayByDay.get(lane.resId);
                  if (!m || m.size === 0) return { pct: 0, ngay: 0 };
                  let sum = 0;
                  for (const v of m.values()) sum += v.pct;
                  return { pct: Math.round((sum / m.size) * 100), ngay: m.size };
                })() : null;
                const avgLoad = tai?.pct ?? null;

                return (
                  <div key={lane.key} className="xl2-lane">
                    <div className="xl2-lane__label" title={lane.label}>
                      <div className="xl2-lane__info">
                        <div className="xl2-lane__name-row">
                          <span className="xl2-lane__name">{lane.label}</span>
                        </div>
                        <div className="xl2-lane__sub-row">
                          {lane.cluster === "may" && (
                            <>
                              <span className="xl2-lane__spec">
                                {avgLoad != null && avgLoad > 0 ? `${avgLoad}% tải` : "Rảnh"}
                              </span>
                              {avgLoad != null && (
                                <span
                                  className="xl2-cap-bar"
                                  title={tai && tai.ngay > 0
                                    ? `Tải trung bình ${avgLoad}% — tính trên ${tai.ngay} ngày có việc trong khung đang xem`
                                    : "Chưa có việc nào trong khung đang xem"}
                                >
                                  <span
                                    className={`xl2-cap-bar__fill${avgLoad > 85 ? " is-high" : avgLoad > 65 ? " is-med" : ""}`}
                                    style={{ width: `${Math.min(avgLoad, 100)}%` }}
                                  />
                                </span>
                              )}
                            </>
                          )}
                          {lane.cluster === "to" && (
                            <span className="xl2-lane__spec">Tổ trực ca</span>
                          )}
                          {lane.cluster === "ncc" && (
                            <span className="xl2-lane__spec">Đối tác thuê ngoài</span>
                          )}
                          {lane.cluster === "lenh" && lane.sub && (
                            <span className="xl2-lane__spec" title={lane.sub}>{lane.sub}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div
                      className="xl2-lane__track"
                      style={{ width: scale.width }}
                      ref={(el) => registerTrack(lane.key, el)}
                      onDragOver={canUpdate ? (e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "copy";
                      } : undefined}
                      onDrop={canUpdate ? (e) => {
                        e.preventDefault();
                        const raw = e.dataTransfer.getData("application/json");
                        if (!raw) return;
                        try {
                          const data = JSON.parse(raw);
                          if (data && data.r) {
                            onDropQueue?.(data.r, lane);
                          }
                        } catch {}
                      } : undefined}
                    >
                    {/* Nền lưới thời gian & ngày nghỉ */}
                    {!lane.packed && (
                      <>
                        {bg.nonwork.map((w, i) => (
                          <div key={`nw${i}`} className="xl2-nonwork" style={{ left: w.x, width: w.w }}
                            title="Ngoài mọi ca — không ca nào phủ giờ này" />
                        ))}
                        {bg.holidays.map((h, i) => (
                          <div key={`h${i}`} className="xl2-holiday" style={{ left: h.x, width: h.w }} />
                        ))}
                        {bg.dayLines.map((x, i) => (
                          <div key={`g${i}`} className="xl2-daygrid" style={{ left: x }} />
                        ))}
                        {ruler.ticks.map((t, i) => (
                          <div key={`tg${i}`} className="xl2-tickgrid" style={{ left: t.x }} />
                        ))}
                        {bg.caStarts.map((c, i) => (
                          <div key={`cs${i}`} className={`xl2-castart xl2-castart--c${c.idx % 5}`}
                            style={{ left: c.x }} title={c.title} />
                        ))}
                        {nowX != null && <div className="xl2-nowline" style={{ left: nowX }} />}
                      </>
                    )}
                    {/* Khoá máy / Bảo trì (chỉ vẽ vùng khoá bảo trì, KHÔNG vẽ dải cam ngang) */}
                    {!lane.packed && lane.cluster === "may" && lane.resId != null && (
                      <>
                        {overlay.khoaByMay.get(lane.resId)?.map((k, i) => (
                          <div key={`kh${i}`} className="xl2-khoa" style={{ left: k.x, width: k.w }} title={k.title} />
                        ))}
                      </>
                    )}
                    {/* Thanh công việc Modern Task Capsule */}
                    {lane.dong.map((dong, idx) => {
                      const timed = !lane.packed && !!dong.start_at;
                      const sW = dong.start_at ? wallMinutes(dong.start_at) : NaN;
                      const eW = dong.finish_at ? wallMinutes(dong.finish_at) : sW + 30;
                      const left = timed ? scale.xOf(sW) : idx * (PACK_W + 8);
                      const width = timed ? Math.max((eW - sW) * scale.ppm, 24) : PACK_W;
                      const muc = barMuc.get(dong.id) ?? null;
                      const sel = dong.id === selectedDongId;
                      const thisEntityKey = dongEntityKey(dong);
                      const chain = !sel && selectedEntityKey != null && thisEntityKey === selectedEntityKey;
                      const isHoveredChain = hoverEntityKey != null && thisEntityKey === hoverEntityKey;
                      const activeEntityKey = hoverEntityKey || selectedEntityKey;
                      const isDimmed = activeEntityKey != null && thisEntityKey !== activeEntityKey;
                      const mucCls = muc ? ` xl2-bar--${muc === "chan_dat_lich" ? "dat" : muc === "chan_phat_hanh" ? "ph" : "warn"}` : "";
                      const canDrag = canUpdate && !dong.is_locked && timed;
                      
                      const bt = dong.boc_tach;
                      const btUncertain = !!bt && bt.chiem_may_phut_max > bt.chiem_may_phut_min;
                      const btTitle = bt
                        ? ` · chuẩn bị máy ${thoiLuong(bt.canh_may_phut)} · chạy ${thoiLuong(bt.chay_phut)} · khác ${thoiLuong(bt.khac_phut)}`
                          + (btUncertain
                            ? ` · chiếm ${thoiLuong(bt.chiem_may_phut)} (xong sớm nhất sau ${thoiLuong(bt.chiem_may_phut_min)}, muộn nhất ${thoiLuong(bt.chiem_may_phut_max)})`
                            : ` · chiếm ${thoiLuong(bt.chiem_may_phut)}`)
                        : "";
                      
                      const nhan = dongNhanParts(dong);
                      const serial = dongSerial(dong);
                      const hue = dongHue(dong);
                      const isNcc = lane.cluster === "ncc";
                      const isWide = width >= 96;
                      const isMedium = width >= 44 && !isWide;
                      // HAI VÙNG dưới đây vẽ NẰM TRONG chip (chốt 25/08/2026). Trước kia dải sai số là
                      // "râu" gạch đứt treo DƯỚI thanh — trùng đúng ngôn ngữ hình của đường phụ thuộc
                      // Gantt nên ai cũng đọc nhầm thành "việc này nối sang việc kia".
                      const inner = Math.max(width - 4, 0); // trừ dải accent mép trái
                      const chiem = bt?.chiem_may_phut || 0;
                      //  ĐẦU chip = chuẩn bị máy, vẽ ĐÚNG TỈ LỆ (bản cũ ép 4–30% nên bước canh 45ph/chạy
                      //  15ph vẫn hiện ra mẩu bé tí, nhìn ngược hẳn sự thật). Nhỏ quá thì thôi không vẽ.
                      const setupPx = timed && bt && bt.canh_may_phut > 0 && chiem > 0
                        ? Math.min((bt.canh_may_phut / chiem) * inner, inner)
                        : 0;
                      //  ĐUÔI chip = quãng "có thể đã xong rồi": từ mốc sớm nhất tới mép phải thanh.
                      const slackPx = timed && bt && btUncertain && chiem > 0
                        ? Math.min(Math.max(((chiem - bt.chiem_may_phut_min) / chiem) * inner, 6), inner * 0.5)
                        : 0;
                      // ── LỚP THỰC TẾ (spec-thuc-te-vs-ke-hoach §2.1) ────────────────────────
                      // Vẽ NẰM TRONG thanh, cùng ngôn ngữ hình với `__setup` / `__slack` — không
                      // treo râu dưới thanh (râu dưới trên màn này chỉ có một nghĩa: phụ thuộc).
                      const tt = dong.thuc_te;
                      const tienDoPx = timed && tt && tt.phan_tram != null
                        ? Math.min(Math.max(tt.phan_tram, 0), 100) / 100 * inner
                        : 0;
                      // Đuôi sọc: ĐANG CHẠY mà đã quá mốc kết thúc dự kiến (spec §2.2, vế 2).
                      // Ba điều kiện, thiếu cái nào cũng nói dối: đã VÀO việc (lệnh mới phát hành
                      // mà chưa ai đụng thì chưa "quá giờ" — đó là rủi ro kế hoạch, việc của bộ dò
                      // `nguy_co_tre`), CHƯA đóng (việc xong muộn thì cái trễ đã nằm ở thanh sau,
                      // vẽ nữa là đếm hai lần), và quá ngưỡng. Cùng bộ điều kiện với
                      // `_lech_thuc_te` bên backend — hai bên lệch nhau thì bàn Gantt và hàng đèn
                      // đỏ hai chỗ khác nhau.
                      const quaGio = !!tt && tt.bat_dau_thuc != null && tt.ket_thuc_thuc == null
                        && (tt.tre_ket_thuc_phut ?? 0) >= NGUONG_LECH_THUC_TE_PHUT;
                      // Tooltip ở bàn XẾP LỊCH chỉ nói chuyện GIỜ. Con số sản lượng (đã làm / còn
                      // thiếu) là việc của bàn tổ bên Thực hiện SX — người xếp lịch cần biết mốc
                      // trôi để xếp lại, không phải để theo dõi sản lượng hộ tổ.
                      const ttTitle = tt
                          // Việc ĐÃ ĐÓNG thì thôi nhắc "vào muộn" — backend `_lech_thuc_te` cũng im ở
                          // đúng chỗ này (cái muộn đã nằm trong mốc bắt đầu của bước sau). Không đồng bộ
                          // thì hàng đèn im mà tooltip vẫn kể, hai mặt của cùng một dữ liệu nói hai kiểu.
                        ? (tt.ket_thuc_thuc == null && (tt.tre_bat_dau_phut ?? 0) >= NGUONG_LECH_THUC_TE_PHUT ? ` · vào muộn ${thoiLuongNgan(tt.tre_bat_dau_phut!)}` : "")
                          + (quaGio ? ` · quá giờ ${thoiLuongNgan(tt.tre_ket_thuc_phut!)}` : "")
                        : "";
                      const durLabel = chiem ? thoiLuongNgan(chiem) : null;
                      //  Máy có khai nhanh–chậm ⇒ in thẳng DẢI GIỜ ("1g05–1g40") thay vì con số giữa:
                      //  đọc ra ngay là còn xê dịch, khỏi phải đoán bằng hình.
                      const durRange = bt && btUncertain
                        ? `${thoiLuongNgan(bt.chiem_may_phut_min)}–${thoiLuongNgan(bt.chiem_may_phut_max)}`
                        : null;
                      // MÃ LỆNH + BƯỚC là thứ luôn phải đọc được trên MỌI thanh (vd "LSX-0029·B3").
                      // Thanh hẹp thì rụng thời lượng trước — bề rộng thanh vốn đã nói lên thời lượng,
                      // còn không thấy mã lệnh thì cả bàn Gantt thành một dãy ô vô danh.
                      const buocLabel = dong.buoc_thu_tu != null ? `B${dong.buoc_thu_tu + 1}` : "";
                      // Thanh của công đoạn ĐÃ TÁCH phải tự nói ra nó là lần chạy thứ mấy — không
                      // thì hai thanh cùng mã cùng bước nằm hai chỗ trông y hệt lỗi trùng lịch.
                      const phanDoanLabel = dong.phan_doan_tong > 1
                        ? `${dong.phan_doan_so}/${dong.phan_doan_tong}`
                        : "";
                      const phanDoanSuffix = phanDoanLabel ? `·${phanDoanLabel}` : "";
                      const serialNgan = serial.replace(/^(?:LSX|GB)-/, "");
                      const maBuoc = `${serial}${buocLabel ? `·${buocLabel}` : ""}${phanDoanSuffix}`;
                      const maBuocNgan = `${serialNgan}${buocLabel ? `·${buocLabel}` : ""}${phanDoanSuffix}`;
                      // Phần việc của CHÍNH thanh này — chỉ có nghĩa khi bước đã chia, dòng trọn
                      // bước để NULL nên không có gì để nói.
                      const slTitle = dong.so_luong != null
                        ? ` · lần chạy ${phanDoanLabel}, ${dong.so_luong.toLocaleString("vi-VN")}`
                        : "";
                      const slAria = dong.so_luong != null
                        ? `, lần chạy ${dong.phan_doan_so} trên ${dong.phan_doan_tong}, ${dong.so_luong.toLocaleString("vi-VN")}`
                        : "";

                      return (
                        <button
                          key={dong.id}
                          type="button"
                          className={`xl2-bar${isNcc ? " xl2-bar--ncc" : ""}${mucCls}${sel ? " xl2-bar--sel" : ""}${chain ? " xl2-bar--chain" : ""}${isHoveredChain ? " xl2-bar--chain-hover" : ""}${isDimmed ? " xl2-bar--dimmed" : ""}${dong.is_locked ? " xl2-bar--locked" : ""}${canDrag ? " xl2-bar--draggable" : ""}${!timed ? " xl2-bar--pack" : ""}${quaGio ? " xl2-bar--qua-gio" : ""}`}
                          style={{ left, width, "--lsx-h": hue } as CSSProperties}
                          title={`${nhan.ma}${nhan.congDoan ? ` · ${nhan.congDoan}` : ""}${nhan.sanPham ? ` · ${nhan.sanPham}` : ""}${slTitle}${dong.start_at ? ` · ${ngayGio(dong.start_at)}` : " · chưa đặt giờ"}${dong.is_locked ? " · đã khóa" : ""}${btTitle}${ttTitle}`}
                          aria-label={`${nhan.ma}${nhan.congDoan ? `, ${nhan.congDoan}` : ""}${nhan.sanPham ? `, ${nhan.sanPham}` : ""}${slAria}${dong.start_at ? `, bắt đầu ${ngayGio(dong.start_at)}` : ", chưa đặt giờ"}`}
                          onPointerDown={canDrag ? (e) => onBarDown(dong, e) : undefined}
                          onClick={() => onBarClick(dong)}
                          onKeyDown={(e) => onBarKey(dong, e)}
                          onPointerEnter={() => setHoverEntityKey(thisEntityKey)}
                          onPointerLeave={() => setHoverEntityKey(null)}
                        >
                          {/* Accent chỉ báo trạng thái mép trái */}
                          <span className="xl2-bar__accent" />

                          {/* Vệt tiến độ thật: nền mờ chạy từ mép trái, KHÔNG đè chữ. */}
                          {tienDoPx > 0 && tt && (
                            <span
                              className="xl2-bar__thuc-te"
                              style={{ width: tienDoPx }}
                              title={`Đã chạy ${num(tt.phan_tram)}%`}
                              aria-hidden="true"
                            />
                          )}
                          {/* Đuôi sọc "còn đang chạy quá giờ" — mọc ra ngoài mép phải. */}
                          {quaGio && (
                            <span className="xl2-bar__qua-gio" aria-hidden="true" />
                          )}

                          {/* Đầu chip: quãng CHUẨN BỊ MÁY — mảng đậm + vạch ngăn, KHÔNG dùng sọc chéo
                              (sọc chéo trên màn này chỉ có một nghĩa: ngoài ca / máy bị khoá). */}
                          {setupPx >= 5 && bt && (
                            <span
                              className="xl2-bar__setup"
                              style={{ width: setupPx }}
                              title={`Chuẩn bị máy: ${thoiLuong(bt.canh_may_phut)}`}
                              aria-hidden="true"
                            />
                          )}

                          {/* Đuôi chip: quãng XÊ DỊCH giờ xong — nhạt dần, ngăn bằng vạch đứt dọc. */}
                          {slackPx >= 6 && bt && (
                            <span
                              className="xl2-bar__slack"
                              style={{ width: slackPx }}
                              title={`Xong sớm nhất sau ${thoiLuong(bt.chiem_may_phut_min)}, muộn nhất ${thoiLuong(bt.chiem_may_phut_max)}`}
                              aria-hidden="true"
                            />
                          )}

                          <div className="xl2-bar__body">
                            {isWide ? (
                              <>
                                <div className="xl2-bar__row1">
                                  <span className="xl2-bar__code" title={maBuoc}>{serial}</span>
                                  {buocLabel && (
                                    <span className="xl2-bar__step-pill">{buocLabel}</span>
                                  )}
                                  {phanDoanLabel && (
                                    <span className="xl2-bar__run-pill"
                                      title={`Lần chạy ${phanDoanLabel}${dong.so_luong != null ? ` · ${dong.so_luong.toLocaleString("vi-VN")}` : ""}`}>
                                      {phanDoanLabel}
                                    </span>
                                  )}
                                  {durRange && width >= 150 ? (
                                    <span className="xl2-bar__dur xl2-bar__dur--range">{durRange}</span>
                                  ) : durLabel && width >= 112 ? (
                                    <span className="xl2-bar__dur">{durLabel}</span>
                                  ) : null}
                                </div>
                                {nhan.congDoan && (
                                  <div className="xl2-bar__row2">
                                    <span className="xl2-bar__cd">{nhan.congDoan}</span>
                                    {nhan.sanPham && <span className="xl2-bar__sp">· {nhan.sanPham}</span>}
                                  </div>
                                )}
                              </>
                            ) : isMedium ? (
                              <div className="xl2-bar__row1">
                                <span className="xl2-bar__code" title={maBuoc}>{maBuocNgan}</span>
                              </div>
                            ) : (
                              <div className="xl2-bar__row1 xl2-bar__row1--tiny">
                                <span className="xl2-bar__code" title={maBuoc}>{maBuocNgan}</span>
                              </div>
                            )}
                          </div>
                        </button>
                      );
                    })}
                    {/* ghost khi kéo trúng lane này */}
                    {ghost && ghost.laneKey === lane.key && (
                      <div
                        className={`xl2-ghost${!ghost.valid ? " xl2-ghost--bad" : ""}${ghost.collide ? " xl2-ghost--collide" : ""}`}
                        style={{ left: ghost.x, width: ghost.w }}
                      >
                        <span className="xl2-ghost__pill">{ghost.label}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Lane-key của một dòng — theo TÀI NGUYÊN đang gán, hoặc theo LỆNH khi bàn đang gom theo lệnh. */
function dongLaneKey(d: Xl2Dong, nhom: Xl2Nhom): string {
  if (nhom === "lenh") return `lenh:${dongEntityKey(d)}`;
  if (d.may_id != null) return `may:${d.may_id}`;
  if (d.department_id != null) return `to:${d.department_id}`;
  if (d.start_at) return `ncc:${(d.nha_cung_cap ?? "").trim() || "_"}`;
  return "cho:_";
}

