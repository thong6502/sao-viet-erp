// TRỤC THỜI GIAN GANTT — thuần (không React), test được.
//
// Giờ "nhà máy" wall-clock một múi. Vị trí tính EPOCH-FREE theo UTC-nominal (Date.UTC không có DST) —
// KHÔNG dùng new Date(iso).getTime() (dính múi/DST). Trục TUYẾN TÍNH theo phút làm việc; ngoài-ca/nghỉ
// hiện dạng NỀN (tô loang, thanh liền) ở zoom giờ/ca, hoặc COLLAPSE về seam mảnh ở zoom ngày/tuần.

export type Zoom = "gio" | "ca" | "ngay" | "tuan";
export const PX_PER_MIN: Record<Zoom, number> = { gio: 2.2, ca: 0.75, ngay: 0.28, tuan: 0.06 };
const SEAM_PX = 12; // bề rộng seam khi ẩn giờ ngoài ca (đủ để thấy "có ngắt")
const GOP_KHE_PHUT = 180; // gộp thanh qua khe nghỉ ≤ 3h (nghỉ trưa/giải lao) — KHỚP backend `_doan_chiem`

export interface Khoang { start: string; finish: string } // ISO wall-clock

/** Phút wall-clock DST-free: đọc thành phần từ ISO rồi Date.UTC (UTC không có DST → ổn định). */
export function wallMinutes(iso: string): number {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) return NaN;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) / 60000;
}

/** Phút wall-clock từ thành phần y/m/d/h. */
export function wallOf(y: number, mo: number, d: number, hh = 0, mi = 0): number {
  return Date.UTC(y, mo - 1, d, hh, mi) / 60000;
}

/** Giải mã ngược phút wall → thành phần (dùng getUTC* — UTC-nominal, DST-free). */
export function fromWall(t: number): { y: number; mo: number; d: number; hh: number; mi: number } {
  const dt = new Date(t * 60000);
  return {
    y: dt.getUTCFullYear(), mo: dt.getUTCMonth() + 1, d: dt.getUTCDate(),
    hh: dt.getUTCHours(), mi: dt.getUTCMinutes(),
  };
}

/** "Bây giờ" theo giờ nhà máy (lấy wall-clock máy người dùng, coi là giờ nhà máy). */
export function nowWall(): number {
  const n = new Date();
  return wallOf(n.getFullYear(), n.getMonth() + 1, n.getDate(), n.getHours(), n.getMinutes());
}

const pad2 = (n: number): string => String(n).padStart(2, "0");

interface Seg { t0: number; t1: number; x0: number; x1: number; work: boolean }

export interface TimeScale {
  segs: Seg[];
  width: number;
  winStart: number;
  winEnd: number;
  pxPerMin: number;
  xOf(t: number): number;
  tOf(x: number): number;
  offRects(): { x: number; w: number }[];
}

/**
 * Dựng trục từ khoảng LÀM VIỆC (`khoangLam`, factory-wide) trong cửa sổ [winStart,winEnd] (phút wall).
 * Ngoài ca = phần bù; `hideOff` → collapse mỗi khoảng ngoài-ca về SEAM_PX (zoom ngày/tuần).
 */
export function buildScale(
  khoangLam: Khoang[], winStart: number, winEnd: number, zoom: Zoom, hideOff: boolean,
): TimeScale {
  const ppm = PX_PER_MIN[zoom];
  const work = khoangLam
    .map((k) => [wallMinutes(k.start), wallMinutes(k.finish)] as [number, number])
    .filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b) && b > winStart && a < winEnd)
    .map(([a, b]) => [Math.max(a, winStart), Math.min(b, winEnd)] as [number, number])
    .sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [a, b] of work) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else merged.push([a, b]);
  }

  const segs: Seg[] = [];
  let cursor = winStart;
  let x = 0;
  const push = (t0: number, t1: number, isWork: boolean): void => {
    if (t1 <= t0) return;
    const w = isWork ? (t1 - t0) * ppm : hideOff ? SEAM_PX : (t1 - t0) * ppm;
    segs.push({ t0, t1, x0: x, x1: x + w, work: isWork });
    x += w;
  };
  for (const [a, b] of merged) {
    if (a > cursor) push(cursor, a, false);
    push(a, b, true);
    cursor = b;
  }
  if (cursor < winEnd) push(cursor, winEnd, false);
  const width = x;

  const xOf = (t: number): number => {
    if (t <= winStart) return 0;
    if (t >= winEnd) return width;
    for (const s of segs) {
      if (t >= s.t0 && t <= s.t1) {
        const frac = s.t1 === s.t0 ? 0 : (t - s.t0) / (s.t1 - s.t0);
        return s.x0 + frac * (s.x1 - s.x0);
      }
    }
    return width;
  };
  const tOf = (px: number): number => {
    if (px <= 0) return winStart;
    if (px >= width) return winEnd;
    for (const s of segs) {
      if (px >= s.x0 && px <= s.x1) {
        const frac = s.x1 === s.x0 ? 0 : (px - s.x0) / (s.x1 - s.x0);
        return s.t0 + frac * (s.t1 - s.t0);
      }
    }
    return winEnd;
  };
  const offRects = (): { x: number; w: number }[] =>
    segs.filter((s) => !s.work).map((s) => ({ x: s.x0, w: s.x1 - s.x0 }));

  return { segs, width, winStart, winEnd, pxPerMin: ppm, xOf, tOf, offRects };
}

/**
 * Thanh việc → các PIECE (rect) của [startISO, finishISO]: chỉ phần LÀM VIỆC, GỘP qua khe nghỉ ≤ 3h
 * (nghỉ trưa → 1 thanh liền, nền loang), TÁCH qua khe dài (đêm/ngày-nghỉ = ngắt thật). Khớp backend.
 */
export function barPieces(
  scale: TimeScale, startISO: string | null, finishISO: string | null,
): { x: number; w: number }[] {
  if (!startISO || !finishISO) return [];
  const s = wallMinutes(startISO);
  const f = wallMinutes(finishISO);
  if (!(Number.isFinite(s) && Number.isFinite(f) && f > s)) return [];
  const occ: [number, number][] = [];
  for (const seg of scale.segs) {
    if (!seg.work) continue;
    const a = Math.max(s, seg.t0);
    const b = Math.min(f, seg.t1);
    if (b > a) occ.push([a, b]);
  }
  if (!occ.length) return [];
  const pieces: [number, number][] = [];
  for (const [a, b] of occ) {
    const last = pieces[pieces.length - 1];
    if (last && a - last[1] <= GOP_KHE_PHUT) last[1] = b;
    else pieces.push([a, b]);
  }
  return pieces.map(([a, b]) => {
    const x = scale.xOf(a);
    return { x, w: Math.max(4, scale.xOf(b) - x) };
  });
}

/**
 * Snap phút wall `t` vào lưới `snapMin` TRONG khoảng làm-việc (kéo-thả). Rơi vào vùng NỀN (ngoài-ca/
 * nghỉ/bảo-trì) = "curtains cấm thả" → nhảy tới mốc làm-việc KẾ (đầu ca sau) và vẫn hợp lệ. Không còn
 * ca nào phía sau → trả mốc cuối + `valid:false` (không cho thả).
 */
export function snapToWork(scale: TimeScale, t: number, snapMin: number): { t: number; valid: boolean } {
  const idx = scale.segs.findIndex((s) => t >= s.t0 && t <= s.t1);
  const seg = idx >= 0 ? scale.segs[idx] : null;
  if (seg && seg.work) {
    const snapped = Math.round(t / snapMin) * snapMin;
    return { t: Math.max(seg.t0, Math.min(snapped, seg.t1)), valid: true };
  }
  if (seg && !seg.work) {
    const next = scale.segs.slice(idx + 1).find((s) => s.work);
    if (next) return { t: next.t0, valid: true };            // snap ra đầu ca kế = curtains
  }
  return { t, valid: false };                                 // sau ca cuối / ngoài trục → cấm thả
}

export interface Tick { x: number; label: string; strong: boolean }

/** Mốc trục theo zoom: giờ (mỗi giờ), ca (mỗi 4h), ngày/tuần (mỗi ngày). Đầu ngày = mốc đậm. */
export function buildTicks(scale: TimeScale, zoom: Zoom): Tick[] {
  const out: Tick[] = [];
  const step = zoom === "gio" ? 60 : zoom === "ca" ? 240 : 1440;
  const first = Math.floor(scale.winStart / 1440) * 1440;
  for (let t = first; t <= scale.winEnd; t += step) {
    if (t < scale.winStart) continue;
    const w = fromWall(t);
    const dayStart = t % 1440 === 0;
    const label = zoom === "ngay" || zoom === "tuan" || dayStart
      ? `${w.d}/${w.mo}`
      : `${pad2(w.hh)}:${pad2(w.mi)}`;
    out.push({ x: scale.xOf(t), label, strong: dayStart });
  }
  return out;
}
