// GANTT THEO MÁY — view trực quan lane × thời gian, đọc CÙNG `rows` với bảng (không kế hoạch riêng).
//
// Đợt 1 (tĩnh): lane theo band × trục giờ; tô NỀN ngoài-ca/nghỉ; thanh pieces (gộp nghỉ-trưa/tách-đêm);
// FILL cõng rủi ro; zoom; tải máy %; now-line. Đợt 2: overlay VÙNG KHÓA máy (bảo trì) + tạo/xoá; thanh
// chia 2 đoạn setup/chạy. Đợt 3: cờ CẦN XÁC NHẬN (khổ/số màu/định lượng vượt máy) + cảnh báo thời-lượng-
// snapshot trên bar. Đợt 4: KÉO-THẢ (Pointer Events, curtains chặn vùng cấm) → xem-trước ảnh-hưởng →
// hộp thoại khi có bước-sau/xung-đột/cần-xác-nhận, sạch thì áp thẳng + Hoàn tác; a11y phím mũi tên.
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  api, XEP_LICH_CANH_BAO_TL_LABELS, XEP_LICH_KHOA_LABELS, XEP_LICH_XAC_NHAN_LABELS,
  type XepLichGanBody, type XepLichLichNen, type XepLichPreview, type XepLichPreviewBody,
  type XepLichRow, type XepLichVungKhoaItem,
} from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ngay, ngayGio, thoiLuong } from "./keHoachSxShared";
import type { Band, GroupBy } from "./XepLichPage";
import {
  buildHeaderData, buildScale, barPieces, fromWall, nowWall, snapToWork, wallMinutes, wallOf,
  type TimeScale, type Zoom,
} from "./gantt-time";

const LABEL_W = 220; // bề rộng cột nhãn lane (sticky trái) - nới rộng để không đè chữ
const BAR_H = 26;
const BAR_GAP = 4;
const LANE_PAD = 8;
const DRAG_THRESH = 4; // px vượt ngưỡng mới coi là kéo (dưới ngưỡng = click mở drawer)
const SPAN_DAY: Record<Zoom, number> = { gio: 1, ca: 3, ngay: 14, tuan: 56 };
const SNAP_MIN: Record<Zoom, number> = { gio: 5, ca: 15, ngay: 30, tuan: 60 };
const ZOOMS: { key: Zoom; label: string }[] = [
  { key: "gio", label: "Giờ" },
  { key: "ca", label: "Ca" },
  { key: "ngay", label: "Ngày" },
  { key: "tuan", label: "Tuần" },
];
const KHOA_REASONS = ["bao_tri", "hong_hoc", "nghi", "khac"];

/** Ngày (wall-min đầu ngày) của "hôm nay" giờ nhà máy. */
function todayStartWall(): number {
  const n = new Date();
  return wallOf(n.getFullYear(), n.getMonth() + 1, n.getDate());
}
function isoDay(t: number): string {
  const w = fromWall(t);
  return `${w.y}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
}
function isoLocal(t: number): string {
  const w = fromWall(t);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${w.y}-${p(w.mo)}-${p(w.d)}T${p(w.hh)}:${p(w.mi)}`;
}
/** ISO NAIVE gửi server (giờ nhà máy) từ phút wall. */
const isoSend = (t: number): string => `${isoLocal(t)}:00`;

/** Popover FIXED neo đáy nút, kẹp trong màn (Gantt cuộn cắt absolute). */
function fixedPop(a: DOMRect, width = 240): CSSProperties {
  return {
    position: "fixed",
    top: Math.min(a.bottom + 4, window.innerHeight - 220),
    left: Math.max(12, Math.min(a.left, window.innerWidth - width - 12)),
    width,
  };
}

function isRisky(r: XepLichRow): boolean {
  return r.co_xung_dot || r.is_locked
    || r.nhan_rui_ro === "da_tre" || r.nhan_rui_ro === "nguy_co_tre" || r.nhan_rui_ro === "sap_toi_han";
}
function barClass(r: XepLichRow, dragging: boolean): string {
  const c = ["xlcd-gbar"];
  if (r.nguon === "in_ghep") c.push("xlcd-gbar--ghep");
  if (r.nhan_rui_ro === "da_tre" || r.nhan_rui_ro === "nguy_co_tre") c.push("is-late");
  else if (r.co_xung_dot) c.push("is-conflict");
  else if (r.nhan_rui_ro === "sap_toi_han") c.push("is-warn");
  else if (r.is_locked) c.push("is-locked");
  if (r.can_xac_nhan) c.push("has-flag");
  if (dragging) c.push("is-dragging");
  return c.join(" ");
}
/** Tooltip nhiều dòng: nhãn · tài nguyên · giờ · breakdown · cảnh báo (theo-máy/cần-xác-nhận). */
function barTip(r: XepLichRow): string {
  const lines = [
    `${r.lsx_ma ?? ""} · ${r.cong_doan_ten ?? ""}`,
    r.may_ten ?? r.department_ten ?? r.nha_cung_cap ?? "",
    `${ngayGio(r.start_at)} → ${ngayGio(r.finish_at)}`,
    `Thiết lập ${thoiLuong(r.setup_phut)} + chạy ${thoiLuong(r.chay_phut)}${r.ve_sinh_phut > 0 ? ` + vệ sinh ${thoiLuong(r.ve_sinh_phut)}` : ""}`,
  ];
  const lag = r.tong_phut - r.chiem_may_phut;
  if (lag > 0) lines.push(`Chờ / di chuyển ${thoiLuong(lag)} (không chiếm máy)`);
  if (r.theo_may) lines.push("Thời lượng tính theo tốc độ máy");
  else if (r.canh_bao_thoi_luong) lines.push(`⚠ ${XEP_LICH_CANH_BAO_TL_LABELS[r.canh_bao_thoi_luong] ?? r.canh_bao_thoi_luong}`);
  for (const ld of r.ly_do_xac_nhan) lines.push(`⚠ ${XEP_LICH_XAC_NHAN_LABELS[ld] ?? ld}`);
  return lines.filter(Boolean).join("\n");
}

/** Xếp chồng: gán mỗi dòng vào sub-row đầu tiên không đè (greedy theo x bắt đầu). */
function packRows(items: { r: XepLichRow; x0: number; x1: number }[]): { r: XepLichRow; x0: number; x1: number; row: number }[] {
  const sorted = [...items].sort((a, b) => a.x0 - b.x0);
  const rowEnds: number[] = [];
  return sorted.map((it) => {
    let row = rowEnds.findIndex((end) => end <= it.x0 + 0.5);
    if (row === -1) { row = rowEnds.length; rowEnds.push(it.x1); }
    else rowEnds[row] = it.x1;
    return { ...it, row };
  });
}

type KhoaPop =
  | { kind: "tao"; mayId: number; rect: DOMRect }
  | { kind: "xoa"; item: XepLichVungKhoaItem; rect: DOMRect };

// Trạng thái kéo LIVE (ref — không gây re-render mỗi pixel); ghost render qua state riêng.
interface DragLive {
  dongId: number;
  row: XepLichRow;
  fromX: number;
  fromY: number;
  moved: boolean;
  targetKey: string | null;
  targetMayId: number | null;
  startWall: number | null;
  valid: boolean;
}
interface Ghost { key: string; x: number; w: number; valid: boolean; collide: boolean; label: string }
interface Impact { dongId: number; row: XepLichRow; body: XepLichGanBody; pv: XepLichPreview }

export function GanttBoard({
  bands, groupBy, token, canUpdate, onOpenRow, onGan, onToast,
}: {
  bands: Band[];
  groupBy: GroupBy;
  token: string | null;
  canUpdate: boolean;
  onOpenRow: (id: number) => void;
  onGan: (id: number, body: XepLichGanBody) => Promise<void>;
  onToast: (text: string, undo?: () => void) => void;
}) {
  const [zoom, setZoom] = useState<Zoom>("ngay");
  const [anchor, setAnchor] = useState<number>(() => todayStartWall());
  const [hideOff, setHideOff] = useState<boolean>(true);
  const [lichNen, setLichNen] = useState<XepLichLichNen | null>(null);
  const [khoas, setKhoas] = useState<XepLichVungKhoaItem[]>([]);
  const [khoaTick, setKhoaTick] = useState(0);
  const [pop, setPop] = useState<KhoaPop | null>(null);
  const [ghost, setGhost] = useState<Ghost | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);

  useEffect(() => { setHideOff(zoom === "ngay" || zoom === "tuan"); }, [zoom]);

  const winStart = anchor;
  const winEnd = anchor + SPAN_DAY[zoom] * 1440;

  // Nạp NỀN lịch (khoảng làm-việc theo ca — factory-wide) + VÙNG KHÓA (mọi máy, overlay theo lane).
  useEffect(() => {
    if (!token) return;
    const mayId = bands.find((b) => b.rows[0]?.may_id != null)?.rows[0]?.may_id ?? 1;
    api.xepLich.lichNen(token, mayId, isoDay(winStart), isoDay(winEnd))
      .then(setLichNen)
      .catch(() => setLichNen({ may_id: mayId, khoang_lam: [], khoang_khoa: [] }));
    api.xepLich.vungKhoaRange(token, isoDay(winStart), isoDay(winEnd))
      .then((r) => setKhoas(r.items))
      .catch(() => setKhoas([]));
  }, [token, winStart, winEnd, bands, khoaTick]);

  const khoaByMay = useMemo(() => {
    const m = new Map<number, XepLichVungKhoaItem[]>();
    for (const k of khoas) { const a = m.get(k.may_id) ?? []; a.push(k); m.set(k.may_id, a); }
    return m;
  }, [khoas]);

  const scale: TimeScale = useMemo(
    () => buildScale(lichNen?.khoang_lam ?? [], winStart, winEnd, zoom, hideOff),
    [lichNen, winStart, winEnd, zoom, hideOff],
  );
  const headerData = useMemo(() => buildHeaderData(scale, zoom), [scale, zoom]);
  const offRects = useMemo(() => scale.offRects(), [scale]);
  const nowX = useMemo(() => {
    const t = nowWall();
    return t >= winStart && t <= winEnd ? scale.xOf(t) : null;
  }, [scale, winStart, winEnd]);
  const availMin = useMemo(
    () => scale.segs.filter((s) => s.work).reduce((sum, s) => sum + (s.t1 - s.t0), 0),
    [scale],
  );

  const trackW = Math.max(scale.width, 320);
  const totalW = LABEL_W + trackW;
  const moveAnchor = (dir: number): void => setAnchor((a) => a + dir * SPAN_DAY[zoom] * 1440);

  // ---- KÉO-THẢ: handler ỔN ĐỊNH đọc env qua ref (tránh re-subscribe listener giữa chừng) ----
  const dragRef = useRef<DragLive | null>(null);
  const draggedRef = useRef(false); // chặn click-mở-drawer ngay sau khi thả
  const acRef = useRef<AbortController | null>(null); // gỡ mọi listener 1 phát khi kết thúc kéo
  const trackReg = useRef<Map<string, HTMLDivElement>>(new Map());
  const env = useRef({ scale, bands, groupBy, zoom, token, onGan, onToast });
  env.current = { scale, bands, groupBy, zoom, token, onGan, onToast };
  useEffect(() => () => acRef.current?.abort(), []); // kéo dở mà rời màn → gỡ listener

  const applyGan = useCallback(async (id: number, body: XepLichGanBody, row: XepLichRow) => {
    const { onGan: g, onToast: t } = env.current;
    const undo = () => g(id, { may_id: row.may_id, start_at: row.start_at, work_shift_id: row.work_shift_id });
    await g(id, body);
    t(`Đã xếp ${row.lsx_ma ?? ""} · ${row.cong_doan_ten ?? ""}`.trim(), undo);
  }, []);

  const onMove = useCallback((e: PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.fromX, e.clientY - d.fromY) <= DRAG_THRESH) return;
    d.moved = true;
    e.preventDefault();
    const { scale: sc, bands: bs, groupBy: gb, zoom: zm } = env.current;
    // Lane dưới con trỏ (hit-test rect track) + rect để đổi px→giờ.
    let key: string | null = null;
    let rect: DOMRect | null = null;
    for (const [k, el] of trackReg.current) {
      const rc = el.getBoundingClientRect();
      if (e.clientY >= rc.top && e.clientY <= rc.bottom) { key = k; rect = rc; break; }
    }
    if (!rect && trackReg.current.size) rect = trackReg.current.values().next().value!.getBoundingClientRect();
    let startWall: number | null = null;
    let valid = false;
    if (rect) {
      const snapped = snapToWork(sc, sc.tOf(e.clientX - rect.left), SNAP_MIN[zm]);
      startWall = snapped.t; valid = snapped.valid;
    }
    const band = key ? bs.find((b) => b.key === key) : null;
    let mayId = d.row.may_id;
    if (gb === "may") {
      mayId = band && !band.noMay ? (band.rows[0]?.may_id ?? null) : null;
      if (!band || band.noMay || mayId == null) valid = false; // curtains dọc: không thả lên "chưa gán máy"
    }
    d.targetKey = key; d.targetMayId = mayId; d.startWall = startWall; d.valid = valid;
    // Phản hồi LIVE (thuần client, không gọi server): nhãn giờ đích + có ĐÈ dòng đã xếp trên lane không.
    const chiem = d.row.chiem_may_phut || 0;
    let collide = false;
    let label = "";
    if (startWall != null) {
      const w = fromWall(startWall);
      label = `${String(w.hh).padStart(2, "0")}:${String(w.mi).padStart(2, "0")}`;
      const end = startWall + chiem;
      for (const rr of band?.rows ?? []) {
        if (rr.id === d.dongId || !rr.start_at || !rr.finish_at) continue;
        if (wallMinutes(rr.start_at) < end && startWall < wallMinutes(rr.finish_at)) { collide = true; break; }
      }
    }
    setGhost(key && startWall != null
      ? { key, x: sc.xOf(startWall), w: Math.max(chiem * sc.pxPerMin, 12), valid, collide, label }
      : null);
  }, []);

  const onCancel = useCallback(() => {
    acRef.current?.abort();
    dragRef.current = null;
    setGhost(null);
  }, []);

  const onUp = useCallback(() => {
    acRef.current?.abort();
    const d = dragRef.current;
    dragRef.current = null;
    setGhost(null);
    if (!d) return;
    if (!d.moved) return;                 // dưới ngưỡng → coi là click (bar onClick mở drawer)
    draggedRef.current = true;            // đã kéo → chặn click kế tiếp
    if (!d.valid || d.startWall == null) return;
    const { token: tk } = env.current;
    if (!tk) return;
    const body: XepLichPreviewBody = { may_id: d.targetMayId, start_at: isoSend(d.startWall) };
    void (async () => {
      try {
        const pv = await api.xepLich.preview(tk, d.dongId, body);
        if (pv.day_doi.length || pv.xung_dot_ids.length || pv.can_xac_nhan) {
          setImpact({ dongId: d.dongId, row: d.row, body, pv });
        } else {
          await applyGan(d.dongId, body, d.row);
        }
      } catch {
        await applyGan(d.dongId, body, d.row); // preview lỗi → vẫn cho gán (server chốt)
      }
    })();
  }, [onMove, applyGan]);

  const onBarDown = useCallback((r: XepLichRow, e: React.PointerEvent) => {
    if (!canUpdate || r.is_locked || !token) return;
    draggedRef.current = false;
    dragRef.current = {
      dongId: r.id, row: r, fromX: e.clientX, fromY: e.clientY,
      moved: false, targetKey: null, targetMayId: r.may_id, startWall: null, valid: false,
    };
    const ac = new AbortController();
    acRef.current = ac;
    window.addEventListener("pointermove", onMove, { signal: ac.signal });
    window.addEventListener("pointerup", onUp, { signal: ac.signal });
    window.addEventListener("pointercancel", onCancel, { signal: ac.signal });
  }, [canUpdate, token, onMove, onUp, onCancel]);

  // A11y: bàn phím thay kéo — ←/→ dời giờ theo bước snap, ↑/↓ đổi lane máy, Enter mở drawer.
  const onBarKey = useCallback((r: XepLichRow, e: React.KeyboardEvent) => {
    if (!canUpdate || r.is_locked) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const base = wallMinutes(r.start_at ?? "");
      if (!Number.isFinite(base)) return;
      e.preventDefault();
      void applyGan(r.id, { start_at: isoSend(base + (e.key === "ArrowRight" ? SNAP_MIN[zoom] : -SNAP_MIN[zoom])) }, r);
    } else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && groupBy === "may") {
      const lanes = bands.filter((b) => !b.noMay);
      const i = lanes.findIndex((b) => (b.rows[0]?.may_id ?? null) === r.may_id);
      const nb = lanes[i + (e.key === "ArrowDown" ? 1 : -1)];
      if (nb) { e.preventDefault(); void applyGan(r.id, { may_id: nb.rows[0]?.may_id ?? null }, r); }
    }
  }, [canUpdate, groupBy, zoom, bands, applyGan]);

  const registerTrack = useCallback((key: string, el: HTMLDivElement | null) => {
    if (el) trackReg.current.set(key, el);
    else trackReg.current.delete(key);
  }, []);
  const openRowGuarded = useCallback((id: number) => {
    if (draggedRef.current) { draggedRef.current = false; return; }
    onOpenRow(id);
  }, [onOpenRow]);

  async function taoKhoa(mayId: number, tu: string, den: string, ly_do: string): Promise<void> {
    if (!token) return;
    await api.xepLich.taoVungKhoa(token, mayId, { tu: `${tu}:00`, den: `${den}:00`, ly_do });
    setPop(null);
    setKhoaTick((t) => t + 1);
  }
  async function xoaKhoa(pid: number): Promise<void> {
    if (!token) return;
    await api.xepLich.xoaVungKhoa(token, pid);
    setPop(null);
    setKhoaTick((t) => t + 1);
  }

  return (
    <div className="xlcd-gantt">
      <div className="xlcd-gantt__controls">
        <div className="khsx-seg" role="tablist" aria-label="Mức phóng đại">
          {ZOOMS.map((z) => (
            <button key={z.key} type="button" role="tab" aria-selected={zoom === z.key}
              className={zoom === z.key ? "is-active" : ""} onClick={() => setZoom(z.key)}>
              {z.label}
            </button>
          ))}
        </div>
        <div className="xlcd-gantt__nav">
          <button type="button" className="xlcd-gnav" onClick={() => moveAnchor(-1)} aria-label="Lùi">
            <Icon name="chevron" size={15} />
          </button>
          <Button variant="secondary" onClick={() => setAnchor(todayStartWall())}>Hôm nay</Button>
          <button type="button" className="xlcd-gnav xlcd-gnav--r" onClick={() => moveAnchor(1)} aria-label="Tiến">
            <Icon name="chevron" size={15} />
          </button>
        </div>
        <label className="xlcd-goff">
          <input type="checkbox" checked={hideOff} onChange={(e) => setHideOff(e.target.checked)} />
          Ẩn giờ ngoài ca
        </label>
        <div className="khsx__spacer" />
        <GanttLegend />
      </div>

      <div className="xlcd-gantt__scroll">
        <div className="xlcd-gantt__inner" style={{ width: totalW }}>
          <div className="xlcd-gantt__head">
            <div className="xlcd-gantt__corner" style={{ width: LABEL_W }}>
              {groupBy === "may" ? "Máy" : groupBy === "bai-ghep" ? "Bài ghép / LSX" : "Lệnh"}
            </div>
            <div className="xlcd-gtimehead xlcd-gtimehead--tiered" style={{ width: trackW }}>
              <div className="xlcd-gtimehead__groups">
                {headerData.groups.map((g, i) => (
                  <div key={i} className="xlcd-gtgroup" style={{ left: g.x, width: g.w }}>
                    <span>{g.label}</span>
                  </div>
                ))}
              </div>
              <div className="xlcd-gtimehead__ticks">
                {headerData.ticks.map((t, i) => (
                  <div
                    key={i}
                    className={`xlcd-gtick ${t.strong ? "is-strong" : ""} ${t.isWeekend ? "is-weekend" : ""}`}
                    style={{ left: t.x }}
                  >
                    <span className="xlcd-gtick__label">{t.label}</span>
                    {t.subLabel && <span className="xlcd-gtick__sub">{t.subLabel}</span>}
                  </div>
                ))}
              </div>
              {nowX != null && (
                <div className="xlcd-gnow xlcd-gnow--head" style={{ left: nowX }} title="Bây giờ">
                  <span className="xlcd-gnow__tag">LIVE</span>
                </div>
              )}
            </div>
          </div>

          {bands.map((b) => (
            <GanttLane
              key={b.key}
              band={b}
              scale={scale}
              trackW={trackW}
              offRects={offRects}
              nowX={nowX}
              availMin={availMin}
              isMachine={groupBy === "may" && !b.noMay}
              maint={khoaByMay.get(b.rows[0]?.may_id ?? -1) ?? []}
              canUpdate={canUpdate}
              ghost={ghost?.key === b.key ? ghost : null}
              dragId={dragRef.current?.dongId ?? null}
              registerTrack={registerTrack}
              onOpenRow={openRowGuarded}
              onBarDown={onBarDown}
              onBarKey={onBarKey}
              onOpenKhoaForm={(mayId, rect) => setPop({ kind: "tao", mayId, rect })}
              onOpenKhoaDel={(item, rect) => setPop({ kind: "xoa", item, rect })}
            />
          ))}
        </div>
      </div>

      {pop?.kind === "tao" && (
        <KhoaForm winStart={winStart} rect={pop.rect} onClose={() => setPop(null)}
          onSave={(tu, den, ly_do) => taoKhoa(pop.mayId, tu, den, ly_do)} />
      )}
      {pop?.kind === "xoa" && (
        <div className="xlcd-pop xlcd-gkhoa" style={fixedPop(pop.rect)} role="dialog">
          <p className="xlcd-gkhoa__t">
            {XEP_LICH_KHOA_LABELS[pop.item.ly_do] ?? pop.item.ly_do} ·{" "}
            {ngayGio(pop.item.start)} → {ngayGio(pop.item.finish)}
          </p>
          <div className="xlcd-gkhoa__row">
            <Button variant="secondary" onClick={() => setPop(null)}>Huỷ</Button>
            <Button variant="danger" onClick={() => xoaKhoa(pop.item.id)}>Bỏ khóa</Button>
          </div>
        </div>
      )}

      {impact && (
        <PreviewImpactDialog
          impact={impact}
          onCancel={() => setImpact(null)}
          onConfirm={async () => {
            const im = impact;
            setImpact(null);
            await applyGan(im.dongId, im.body, im.row);
          }}
        />
      )}
    </div>
  );
}

function GanttLane({
  band, scale, trackW, offRects, nowX, availMin, isMachine, maint, canUpdate, ghost, dragId,
  registerTrack, onOpenRow, onBarDown, onBarKey, onOpenKhoaForm, onOpenKhoaDel,
}: {
  band: Band;
  scale: TimeScale;
  trackW: number;
  offRects: { x: number; w: number }[];
  nowX: number | null;
  availMin: number;
  isMachine: boolean;
  maint: XepLichVungKhoaItem[];
  canUpdate: boolean;
  ghost: Ghost | null;
  dragId: number | null;
  registerTrack: (key: string, el: HTMLDivElement | null) => void;
  onOpenRow: (id: number) => void;
  onBarDown: (r: XepLichRow, e: React.PointerEvent) => void;
  onBarKey: (r: XepLichRow, e: React.KeyboardEvent) => void;
  onOpenKhoaForm: (mayId: number, rect: DOMRect) => void;
  onOpenKhoaDel: (item: XepLichVungKhoaItem, rect: DOMRect) => void;
}) {
  const mayId = band.rows[0]?.may_id ?? null;
  const scheduled = band.rows.filter((r) => r.start_at && r.finish_at);
  const choGio = band.rows.filter((r) => !r.start_at && (r.may_id != null || r.department_id != null)).length;

  const packed = useMemo(() => packRows(scheduled.map((r) => ({
    r, x0: scale.xOf(wallMinutes(r.start_at as string)), x1: scale.xOf(wallMinutes(r.finish_at as string)),
  }))), [scheduled, scale]);
  const subRows = packed.length ? Math.max(...packed.map((p) => p.row)) + 1 : 1;
  const laneH = Math.max(58, subRows * BAR_H + (subRows - 1) * BAR_GAP + LANE_PAD * 2);

  const loadPct = useMemo(() => {
    if (!isMachine || availMin <= 0) return null;
    const used = scheduled.reduce((s, r) => {
      const t = wallMinutes(r.start_at as string);
      return t >= scale.winStart && t < scale.winEnd ? s + (r.chiem_may_phut || 0) : s;
    }, 0);
    return Math.round((used / availMin) * 100);
  }, [scheduled, availMin, isMachine, scale]);

  return (
    <div className={`xlcd-glane ${band.noMay ? "xlcd-glane--nomay" : ""}`} style={{ height: laneH }}>
      <div className="xlcd-glane__label" style={{ width: LABEL_W }}>
        <div className="xlcd-glane__name">
          <span className="xlcd-glane__status-dot" title="Máy hoạt động bình thường" />
          <Icon name={band.icon} size={13} />
          <span title={band.label}>{band.label}</span>
          {isMachine && canUpdate && mayId != null && (
            <button type="button" className="xlcd-glane__khoa" title="Thêm khoảng bảo trì / khóa máy"
              onClick={(e) => onOpenKhoaForm(mayId, e.currentTarget.getBoundingClientRect())}>
              <Icon name="ban" size={12} />
            </button>
          )}
        </div>
        <div className="xlcd-glane__meta">
          {loadPct != null && <LoadMeter pct={loadPct} />}
          <span className="xlcd-glane__sub">
            {band.rows.length} công đoạn{choGio > 0 && ` · ${choGio} chờ giờ`}
          </span>
        </div>
      </div>
      <div className="xlcd-glane__track" style={{ width: trackW }}
        ref={(el) => registerTrack(band.key, el)}>
        {offRects.map((o, i) => (
          <div key={`o${i}`} className="xlcd-gback xlcd-gback--off" style={{ left: o.x, width: o.w }} />
        ))}
        {maint.map((k) => {
          const x = scale.xOf(wallMinutes(k.start));
          const w = Math.max(3, scale.xOf(wallMinutes(k.finish)) - x);
          return (
            <div key={`k${k.id}`} className={`xlcd-gback xlcd-gback--maint ${canUpdate ? "is-click" : ""}`}
              style={{ left: x, width: w }}
              role={canUpdate ? "button" : undefined}
              title={`${XEP_LICH_KHOA_LABELS[k.ly_do] ?? k.ly_do}: ${ngayGio(k.start)} → ${ngayGio(k.finish)}`}
              onClick={canUpdate ? (e) => onOpenKhoaDel(k, e.currentTarget.getBoundingClientRect()) : undefined} />
          );
        })}
        {nowX != null && <div className="xlcd-gnow" style={{ left: nowX }} />}
        {ghost && (
          <div className={`xlcd-gghost ${!ghost.valid ? "is-invalid" : ghost.collide ? "is-collide" : ""}`}
            style={{ left: ghost.x, width: ghost.w, top: LANE_PAD, height: BAR_H }} aria-hidden="true">
            <span className="xlcd-gghost__t">{ghost.label}{ghost.collide && " · đè"}</span>
          </div>
        )}
        {packed.map(({ r, row }) => (
          <GanttBar key={r.id} r={r} scale={scale} top={LANE_PAD + row * (BAR_H + BAR_GAP)}
            dragging={dragId === r.id} canUpdate={canUpdate}
            onOpen={onOpenRow} onDown={onBarDown} onKey={onBarKey} />
        ))}
      </div>
    </div>
  );
}

function GanttBar({
  r, scale, top, dragging, canUpdate, onOpen, onDown, onKey,
}: {
  r: XepLichRow;
  scale: TimeScale;
  top: number;
  dragging: boolean;
  canUpdate: boolean;
  onOpen: (id: number) => void;
  onDown: (r: XepLichRow, e: React.PointerEvent) => void;
  onKey: (r: XepLichRow, e: React.KeyboardEvent) => void;
}) {
  const pieces = barPieces(scale, r.start_at, r.finish_at);
  if (!pieces.length) return null;
  const tip = barTip(r);
  // Vệt CHỜ (khô mực/keo/di chuyển) = lag finish→bước sau, KHÔNG chiếm máy → vệt chấm mờ nối tiếp.
  const lag = r.tong_phut - r.chiem_may_phut;
  let dry: { x: number; w: number } | null = null;
  if (lag > 0 && r.finish_at) {
    const fw = wallMinutes(r.finish_at);
    const x0 = scale.xOf(fw);
    const x1 = scale.xOf(fw + lag);
    if (x1 > x0 + 1) dry = { x: x0, w: x1 - x0 };
  }
  const flag = r.nhan_rui_ro === "da_tre" || r.nhan_rui_ro === "nguy_co_tre" ? "TRỄ" : r.is_rush ? "GẤP" : null;
  // Đoạn setup (đầu công đoạn) — chỉ vẽ trên thanh AN TOÀN (thanh rủi ro giữ FILL trạng thái).
  const setupFrac = !isRisky(r) && r.chiem_may_phut > 0 ? Math.min(r.setup_phut / r.chiem_may_phut, 0.85) : 0;
  const draggable = canUpdate && !r.is_locked;
  const last = pieces.length - 1;
  return (
    <>
      {dry && (
        <span className="xlcd-gdry" style={{ left: dry.x, width: dry.w, top: top + BAR_H / 2 - 1 }} aria-hidden="true" />
      )}
      {pieces.map((p, i) => (
        <button
          key={i}
          type="button"
          className={`${barClass(r, dragging)} ${draggable ? "is-draggable" : ""}`}
          style={{ left: p.x, width: p.w, top, height: BAR_H }}
          title={tip}
          aria-label={tip.replace(/\n/g, " · ")}
          onPointerDown={i === 0 && draggable ? (e) => onDown(r, e) : undefined}
          onKeyDown={i === 0 && draggable ? (e) => onKey(r, e) : undefined}
          onClick={() => onOpen(r.id)}
        >
          {i === 0 && setupFrac > 0 && (
            <span className="xlcd-gbar__setup" style={{ width: `${setupFrac * 100}%` }} aria-hidden="true" />
          )}
          {i === last && (flag || r.is_locked || r.can_xac_nhan || p.w >= 40) && (
            <span className="xlcd-gbar__txt">
              {flag && <span className="xlcd-gbadge xlcd-gbadge--flag">{flag}</span>}
              {r.can_xac_nhan && !flag && <span className="xlcd-gbadge xlcd-gbadge--warn" title="Cần xác nhận máy">!</span>}
              {r.nguon === "in_ghep" && p.w >= 40 && <span className="xlcd-gbadge xlcd-gbadge--bg">BG</span>}
              {r.is_locked && <Icon name="lock" size={10} />}
              {p.w >= 64 && <span className="xlcd-gbar__ma">{r.lsx_ma}</span>}
            </span>
          )}
        </button>
      ))}
    </>
  );
}

function PreviewImpactDialog({
  impact, onCancel, onConfirm,
}: {
  impact: Impact;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { row, pv } = impact;
  return (
    <div className="xlcd-scrim" onClick={onCancel}>
      <div className="xlcd-gimpact" role="dialog" aria-modal="true" aria-label="Ảnh hưởng khi xếp" onClick={(e) => e.stopPropagation()}>
        <header className="xlcd-gimpact__head">
          <Icon name="calendar" size={16} />
          <div>
            <h3>Xếp {row.lsx_ma ?? ""} · {row.cong_doan_ten ?? ""}</h3>
            <p className="xlcd-gimpact__when">
              {ngayGio(impact.body.start_at ?? null)} → {ngayGio(pv.finish_at)} · chiếm máy {thoiLuong(pv.chiem_may_phut)}
              {pv.theo_may && <span className="xlcd-gimpact__tag">theo máy</span>}
            </p>
          </div>
        </header>

        <div className="xlcd-gimpact__body">
          {pv.can_xac_nhan && (
            <section className="xlcd-gimpact__sec xlcd-gimpact__sec--warn">
              <p className="xlcd-gimpact__t"><Icon name="ban" size={13} /> Máy có thể không kham nổi</p>
              <ul>{pv.ly_do_xac_nhan.map((ld) => <li key={ld}>{XEP_LICH_XAC_NHAN_LABELS[ld] ?? ld}</li>)}</ul>
            </section>
          )}
          {pv.xung_dot_ids.length > 0 && (
            <section className="xlcd-gimpact__sec xlcd-gimpact__sec--bad">
              <p className="xlcd-gimpact__t"><Icon name="ban" size={13} /> Chồng giờ {pv.xung_dot_ids.length} công đoạn khác trên máy này</p>
            </section>
          )}
          {pv.day_doi.length > 0 && (
            <section className="xlcd-gimpact__sec">
              <p className="xlcd-gimpact__t"><Icon name="chevron" size={13} /> Đẩy {pv.day_doi.length} bước sau</p>
              <ul>
                {pv.day_doi.slice(0, 5).map((d) => (
                  <li key={d.id}>{d.cong_doan_ten ?? `#${d.id}`} → sớm nhất {ngayGio(d.som_nhat)}</li>
                ))}
                {pv.day_doi.length > 5 && <li>… và {pv.day_doi.length - 5} bước nữa</li>}
              </ul>
            </section>
          )}
          {pv.han_hoan_thanh_moi && (
            <p className="xlcd-gimpact__han">
              Hoàn thành chuỗi dự kiến: <b>{ngay(pv.han_hoan_thanh_moi)}</b>
              {(pv.nhan_rui_ro === "da_tre" || pv.nhan_rui_ro === "nguy_co_tre") && (
                <span className="xlcd-gimpact__late"> · nguy cơ trễ hạn</span>
              )}
            </p>
          )}
        </div>

        <footer className="xlcd-gimpact__foot">
          <Button variant="secondary" onClick={onCancel}>Huỷ</Button>
          <Button variant="primary" onClick={onConfirm}>Vẫn xếp</Button>
        </footer>
      </div>
    </div>
  );
}

function KhoaForm({
  winStart, rect, onClose, onSave,
}: {
  winStart: number;
  rect: DOMRect;
  onClose: () => void;
  onSave: (tu: string, den: string, ly_do: string) => void;
}) {
  const [tu, setTu] = useState(() => isoLocal(winStart + 8 * 60));      // ~08:00 ngày đầu
  const [den, setDen] = useState(() => isoLocal(winStart + 10 * 60));   // ~10:00
  const [lyDo, setLyDo] = useState("bao_tri");
  const ok = tu.length === 16 && den.length === 16 && tu < den;
  return (
    <div className="xlcd-pop xlcd-gkhoa" style={fixedPop(rect)} role="dialog" aria-label="Thêm khoảng khóa máy">
      <label className="xlcd-gkhoa__f">Lý do
        <select value={lyDo} onChange={(e) => setLyDo(e.target.value)}>
          {KHOA_REASONS.map((k) => <option key={k} value={k}>{XEP_LICH_KHOA_LABELS[k]}</option>)}
        </select>
      </label>
      <label className="xlcd-gkhoa__f">Từ
        <input type="datetime-local" value={tu} onChange={(e) => setTu(e.target.value)} />
      </label>
      <label className="xlcd-gkhoa__f">Đến
        <input type="datetime-local" value={den} onChange={(e) => setDen(e.target.value)} />
      </label>
      <div className="xlcd-gkhoa__row">
        <Button variant="secondary" onClick={onClose}>Huỷ</Button>
        <Button variant="accent" disabled={!ok} onClick={() => onSave(tu, den, lyDo)}>Khóa máy</Button>
      </div>
    </div>
  );
}

function LoadMeter({ pct }: { pct: number }) {
  const level = pct > 100 ? "over" : pct >= 85 ? "warn" : "good";
  return (
    <span className={`xlcd-gload xlcd-gload--${level}`} title={`Tải máy ${pct}%`}>
      <span className="xlcd-gload__bar">
        <span className="xlcd-gload__fill" style={{ width: `${Math.min(pct, 100)}%` }} />
      </span>
      <span className="xlcd-gload__pct">{pct}%</span>
    </span>
  );
}

function GanttLegend() {
  const items: { type: string; label: string }[] = [
    { type: "daxep", label: "Đã xếp" },
    { type: "ghep", label: "Bài ghép" },
    { type: "warn", label: "Sắp tới hạn" },
    { type: "late", label: "Nguy cơ / trễ" },
    { type: "conflict", label: "Xung đột" },
    { type: "locked", label: "Đã khóa" },
  ];
  return (
    <div className="xlcd-glegend" aria-hidden="true">
      {items.map((it) => (
        <span key={it.label} className={`xlcd-glegend__it xlcd-glegend__it--${it.type}`}>
          <span className="xlcd-glegend__dot" />
          {it.label}
        </span>
      ))}
    </div>
  );
}
