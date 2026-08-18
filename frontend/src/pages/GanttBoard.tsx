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
  type XepLichKieuKhoang, type XepLichNguoiTangGiua, type XepLichRow,
  type XepLichTaiToKhoang, type XepLichVungKhoaItem,
} from "../api/client";
import type { XepLichVanDe } from "../api/client";
import { kyThuatMay } from "../api/kyThuatMay";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ngay, ngayGio, thoiLuong } from "./keHoachSxShared";
import type { Band, GroupBy } from "./XepLichPage";
import {
  buildHeaderData, buildScale, barPieces, fromWall, nowWall, snapToWork, wallMinutes, wallOf,
  type TimeScale, type Zoom,
} from "./gantt-time";

const LABEL_W = 240; // bề rộng cột nhãn lane (sticky trái) - nới rộng 240px để thông số không đè chữ
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
    `Thiết lập ${thoiLuong(r.setup_phut)} + chạy ${thoiLuong(r.chay_phut)}`,
  ];
  if ((r.chiem_may_phut_max || 0) - (r.chiem_may_phut_min || 0) > 0.5) {
    lines.push(`Nhanh nhất ${thoiLuong(r.chiem_may_phut_min)} – chậm nhất ${thoiLuong(r.chiem_may_phut_max)}`);
  }
  const lag = r.tong_phut - r.chiem_may_phut;
  if (lag > 0) lines.push(`Chờ / di chuyển ${thoiLuong(lag)} (không chiếm máy)`);
  // Tổ tiêu thụ NGƯỜI chứ không chiếm trọn khoảng giờ — số này là thứ quyết định quá tải hay không.
  if (r.department_id != null && (r.so_nhan_cong ?? 0) > 0) lines.push(`Bố trí ${r.so_nhan_cong} người`);
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
  | { kind: "xoa"; item: XepLichVungKhoaItem; rect: DOMRect }
  // Mục I — sửa quân số tổ NGÀY ĐÓ. Mở từ chính khoảng đang đỏ trên lane tổ: người dùng bấm vào
  // đúng chỗ đang báo thiếu người, không phải đi tìm màn khác rồi tự nhớ hôm đó là ngày mấy.
  | { kind: "quan_so"; tai: XepLichTaiToKhoang; rect: DOMRect };

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
  bands, groupBy, token, canUpdate, openRowId, picked, vanDeTheoDong, focusAt, flashKey,
  onOpenRow, onTogglePickBand, onOpenVanDe, onGan, onToast, onChen,
}: {
  bands: Band[];
  groupBy: GroupBy;
  token: string | null;
  canUpdate: boolean;
  /** Dòng đang mở ở panel phải — tô sáng thanh tương ứng để không lạc chỗ đang đứng. */
  openRowId: number | null;
  picked: Set<number>;
  /** Vấn đề dẫn xuất, tra theo id dòng (`impacts.dong_ids`). Chip đỏ ngay trên thanh: xem vấn đề
   *  TẠI cái lịch, không phải mở danh sách thứ hai rồi tự dò ngược. */
  vanDeTheoDong: Map<number, XepLichVanDe[]>;
  /** Mốc giờ cần nhảy tới khi người dùng gõ tìm — thiếu nó thì gõ mã lệnh xếp tháng sau ra lane
   *  trống trơn, phải bấm "Tiến" mấy lần mới thấy. */
  focusAt: string | null;
  flashKey: string | null;
  onOpenRow: (id: number) => void;
  onTogglePickBand: (ids: number[]) => void;
  onOpenVanDe: (issueKey: string) => void;
  onGan: (id: number, body: XepLichGanBody) => Promise<void>;
  onToast: (text: string, undo?: () => void) => void;
  /** Mở bảng "chèn & lùi các việc sau" (`/chen`, không ghi) — dùng lại đúng luồng của panel phải. */
  onChen: (dongId: number, mayId: number | null, dtLocal: string) => void;
}) {
  const [zoom, setZoom] = useState<Zoom>("ngay");
  const [anchor, setAnchor] = useState<number>(() => todayStartWall());
  const [hideOff, setHideOff] = useState<boolean>(true);
  const [lichNen, setLichNen] = useState<XepLichLichNen | null>(null);
  const [khoas, setKhoas] = useState<XepLichVungKhoaItem[]>([]);
  const [khoaTick, setKhoaTick] = useState(0);
  // Mức dùng NGƯỜI của từng tổ theo khoảng giờ (mục I). Lấy từ server chứ không tự cộng ở FE:
  // tô đỏ ở đây phải trùng khít với cái detector chặn phát hành, hai nơi tự tính là có ngày lệch.
  const [taiTo, setTaiTo] = useState<XepLichTaiToKhoang[]>([]);
  // Người khối SX chưa gắn tổ lá — KHÔNG vào quỹ giờ-người của tổ nào, nên phải nhắc ra mặt.
  const [tangGiua, setTangGiua] = useState<XepLichNguoiTangGiua[]>([]);
  const [pop, setPop] = useState<KhoaPop | null>(null);
  const [ghost, setGhost] = useState<Ghost | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [impactBusy, setImpactBusy] = useState(false);
  // Mốc TỚI HẠN BẢO TRÌ của từng máy (mục 2i). `lich_bao_tri` chỉ khai HẠN, không khai thời lượng
  // ⇒ KHÔNG tự sinh vùng chặn (sẽ phải bịa "chặn mấy tiếng"). Cắm mốc để người điều độ tự khoá giờ.
  const [mocBaoTri, setMocBaoTri] = useState<{ may_id: number; ngay: string; goi_ten: string | null }[]>([]);

  useEffect(() => { setHideOff(zoom === "ngay" || zoom === "tuan"); }, [zoom]);

  const winStart = anchor;
  const winEnd = anchor + SPAN_DAY[zoom] * 1440;

  // Gõ tìm ra một dòng nằm ngoài cửa sổ đang xem thì DỜI cửa sổ tới đó. Không có bước này, ô tìm
  // kiếm chỉ lọc lane chứ không đưa mắt tới việc — đúng thứ người dùng vừa gõ lại là thứ không thấy.
  useEffect(() => {
    if (!focusAt) return;
    const t = wallMinutes(focusAt);
    if (!Number.isFinite(t)) return;
    setAnchor((a) => (t >= a && t < a + SPAN_DAY[zoom] * 1440 ? a : Math.floor(t / 1440) * 1440));
  }, [focusAt, zoom]);

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
    api.xepLich.taiTo(token)
      .then((r) => { setTaiTo(r.items); setTangGiua(r.tang_giua ?? []); })
      .catch(() => { setTaiTo([]); setTangGiua([]); });
    // Người xếp lịch không chắc có quyền module Kỹ thuật máy — hỏng thì im lặng bỏ mốc, đừng để
    // cả bàn lịch đỏ lên vì một lớp chú thích.
    kyThuatMay.lich(token, isoDay(winStart), isoDay(winEnd))
      .then((r) => setMocBaoTri(r.du_kien.map((d) => ({ may_id: d.may_id, ngay: d.ngay, goi_ten: d.goi_ten }))))
      .catch(() => setMocBaoTri([]));
  }, [token, winStart, winEnd, bands, khoaTick]);

  const mocByMay = useMemo(() => {
    const m = new Map<number, { ngay: string; goi_ten: string | null }[]>();
    for (const k of mocBaoTri) {
      const a = m.get(k.may_id) ?? [];
      a.push({ ngay: k.ngay, goi_ten: k.goi_ten });
      m.set(k.may_id, a);
    }
    return m;
  }, [mocBaoTri]);

  // Dòng CHƯA CÓ GIỜ, gom theo lane. `_dong_moi` sinh dòng không `start_at` mà Gantt chỉ vẽ dòng
  // có giờ ⇒ 12 lệnh vừa đưa vào kế hoạch trước đây vô hình trên bàn lịch. Dải đỗ là chỗ chúng đỗ.
  const choGio = useMemo(
    () => bands
      .map((b) => ({ band: b, rows: b.rows.filter((r) => !r.start_at) }))
      .filter((g) => g.rows.length > 0),
    [bands],
  );
  const choGioIds = useMemo(() => choGio.flatMap((g) => g.rows.map((r) => r.id)), [choGio]);

  const taiByTo = useMemo(() => {
    const m = new Map<number, XepLichTaiToKhoang[]>();
    for (const k of taiTo) {
      const a = m.get(k.department_id) ?? [];
      a.push(k);
      m.set(k.department_id, a);
    }
    return m;
  }, [taiTo]);

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

  /** MỘT cửa duy nhất trước khi ghi: xem-trước → có gì phải nói thì mở hộp, sạch thì áp thẳng.
   *  Trước đây phím mũi tên ghi THẲNG không qua xem-trước — cùng một việc mà hai đường cho hai kết
   *  quả khác nhau, người dùng bàn phím im lặng đè lên việc khác. */
  const tryGan = useCallback(async (id: number, body: XepLichPreviewBody, row: XepLichRow) => {
    const { token: tk, onToast: t } = env.current;
    if (!tk) return;
    try {
      const pv = await api.xepLich.preview(tk, id, body);
      if (pv.day_doi.length || pv.xung_dot_ids.length || pv.can_xac_nhan || pv.canh_bao.length) {
        setImpact({ dongId: id, row, body, pv });
        return;
      }
      await applyGan(id, body, row);
    } catch {
      // Nuốt lỗi xem-trước rồi ghi im lặng là chỗ tệ nhất: người dùng tưởng đã kiểm, thực ra chưa.
      t("Không xem trước được ảnh hưởng — vẫn xếp, server sẽ chốt lại.");
      await applyGan(id, body, row);
    }
  }, [applyGan]);

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
    void tryGan(d.dongId, { may_id: d.targetMayId, start_at: isoSend(d.startWall) }, d.row);
  }, [tryGan]);

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
  // Đi qua ĐÚNG cửa `tryGan` như kéo-thả (xem mục "một cửa duy nhất" ở trên).
  const onBarKey = useCallback((r: XepLichRow, e: React.KeyboardEvent) => {
    if (!canUpdate || r.is_locked) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const base = wallMinutes(r.start_at ?? "");
      if (!Number.isFinite(base)) return;
      e.preventDefault();
      void tryGan(r.id, { start_at: isoSend(base + (e.key === "ArrowRight" ? SNAP_MIN[zoom] : -SNAP_MIN[zoom])) }, r);
    } else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && groupBy === "may") {
      const lanes = bands.filter((b) => !b.noMay);
      const i = lanes.findIndex((b) => (b.rows[0]?.may_id ?? null) === r.may_id);
      const nb = lanes[i + (e.key === "ArrowDown" ? 1 : -1)];
      if (!nb || !r.start_at) return;
      e.preventDefault();
      void tryGan(r.id, { may_id: nb.rows[0]?.may_id ?? null, start_at: r.start_at }, r);
    }
  }, [canUpdate, groupBy, zoom, bands, tryGan]);

  const registerTrack = useCallback((key: string, el: HTMLDivElement | null) => {
    if (el) trackReg.current.set(key, el);
    else trackReg.current.delete(key);
  }, []);
  const openRowGuarded = useCallback((id: number) => {
    if (draggedRef.current) { draggedRef.current = false; return; }
    onOpenRow(id);
  }, [onOpenRow]);

  async function taoKhoa(
    mayId: number, tu: string, den: string, ly_do: string, kieu: XepLichKieuKhoang,
  ): Promise<void> {
    if (!token) return;
    await api.xepLich.taoVungKhoa(token, mayId, { tu: `${tu}:00`, den: `${den}:00`, ly_do, kieu });
    setPop(null);
    setKhoaTick((t) => t + 1);
  }
  async function xoaKhoa(pid: number): Promise<void> {
    if (!token) return;
    await api.xepLich.xoaVungKhoa(token, pid);
    setPop(null);
    setKhoaTick((t) => t + 1);
  }

  /** "Tìm khe trống" — dùng lại `goi_y` sẵn có rồi xem-trước LẠI tại khe đó, không ghi gì.
   *
   *  Trước đây kéo trúng chỗ đã có việc thì chỉ có Huỷ: người dùng đóng hộp, tự đi dò khe trống
   *  bằng mắt rồi kéo lại. Câu trả lời server đã biết sẵn — chỉ là chưa ai hỏi hộ. */
  const timKhe = useCallback(async () => {
    const im = impact;
    if (!im || !token) return;
    setImpactBusy(true);
    try {
      const gy = await api.xepLich.goiY(token, im.dongId);
      const top = gy.goi_y_may[0];
      const khe = top?.khe_trong ?? gy.khe_trong;
      const mayId = top?.may_id ?? gy.may_id ?? im.body.may_id ?? null;
      if (!khe) { onToast("Chưa tìm được khe trống nào cho công đoạn này."); return; }
      const body: XepLichPreviewBody = { may_id: mayId, start_at: khe };
      const pv = await api.xepLich.preview(token, im.dongId, body);
      setImpact({ dongId: im.dongId, row: im.row, body, pv });
    } catch {
      onToast("Không lấy được gợi ý khe trống.");
    } finally {
      setImpactBusy(false);
    }
  }, [impact, token, onToast]);

  /** "Chèn — lùi các việc sau": chuyển thẳng sang bảng `/chen` (cũng chỉ TÍNH, chưa ghi). Gộp về
   *  đây để một việc không còn hai hộp xem-trước ở hai chỗ khác nhau. */
  const chenTai = useCallback(() => {
    const im = impact;
    if (!im?.body.start_at) return;
    setImpact(null);
    onChen(im.dongId, im.body.may_id ?? im.row.may_id, isoLocal(wallMinutes(im.body.start_at)));
  }, [impact, onChen]);

  /** Gõ đè quân số tổ một ngày (mục I). `soNguoi = null` = bỏ gõ đè, quay về số tự tính. */
  async function luuQuanSo(deptId: number, ngay: string, soNguoi: number | null, lyDo: string) {
    if (!token) return;
    await api.xepLich.datQuanSo(token, deptId, ngay, soNguoi, lyDo);
    setPop(null);
    setKhoaTick((t) => t + 1);   // nạp lại nền lane: sửa quân số là đổi kết luận quá tải
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

      {/* Mục I — người khối SX gắn ở TẦNG GIỮA. Họ KHÔNG được cộng vào tổ nào (cộng là đếm thừa,
          lịch hứa năng lực không có thật), nhưng im lặng bỏ thì quỹ giờ-người hụt mà không ai
          hiểu vì sao. Nói ra để người quản lý đi gắn tổ — máy không tự đoán hộ. */}
      {tangGiua.length > 0 && (
        <p className="xlcd-gnhac">
          <Icon name="help" size={13} />
          {tangGiua.map((t) => `${t.so_nguoi} người thuộc ${t.department_ten}`).join(" · ")}
          {" "}chưa gắn tổ — chưa tính vào quỹ giờ-người của tổ nào.
        </p>
      )}

      {/* DẢI ĐỖ "CHƯA CÓ GIỜ" — đặt NGOÀI vùng cuộn ngang, cố ý. Để chip trong track thì kéo lịch
          sang tháng sau là đám việc chưa xếp trôi khỏi màn, đúng lúc cần nó nhất. Gom theo lane
          nên vẫn đọc được "máy nào đang nợ mấy việc". */}
      {choGio.length > 0 && (
        <div className="xlcd-gpark">
          <div className="xlcd-gpark__head">
            <Icon name="clock" size={13} />
            <b>{choGioIds.length}</b> công đoạn chưa có giờ
            <span className="xlcd-gpark__hint">kéo thẳng vào lane, hoặc chọn rồi bấm “Tự xếp”</span>
            {canUpdate && (
              <button type="button" className="xlcd-gpark__all" onClick={() => onTogglePickBand(choGioIds)}>
                {choGioIds.every((id) => picked.has(id)) ? "Bỏ chọn" : "Chọn tất cả"}
              </button>
            )}
          </div>
          <div className="xlcd-gpark__strip">
            {choGio.map((g) => (
              <div key={g.band.key} className="xlcd-gpark__grp">
                <span className="xlcd-gpark__grpname" title={g.band.label}>
                  <Icon name={g.band.icon} size={11} /> {g.band.label}
                </span>
                {g.rows.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className={`xlcd-gchip${picked.has(r.id) ? " is-picked" : ""}`
                      + `${r.is_rush ? " is-rush" : ""}${openRowId === r.id ? " is-open" : ""}`}
                    title={`${r.lsx_ma ?? ""} · ${r.cong_doan_ten ?? ""}\nChưa có giờ — kéo vào lane hoặc bấm để mở`}
                    onPointerDown={canUpdate && !r.is_locked ? (e) => onBarDown(r, e) : undefined}
                    onClick={() => openRowGuarded(r.id)}
                  >
                    <span className="xlcd-gchip__ma">{r.lsx_ma ?? "—"}</span>
                    <span className="xlcd-gchip__cd">{r.cong_doan_ten ?? "—"}</span>
                    {r.is_rush && <span className="xlcd-gbadge xlcd-gbadge--flag">GẤP</span>}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

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
              mocs={mocByMay.get(b.rows[0]?.may_id ?? -1) ?? []}
              tai={taiByTo.get(b.rows[0]?.department_id ?? -1) ?? []}
              canUpdate={canUpdate}
              ghost={ghost?.key === b.key ? ghost : null}
              dragId={dragRef.current?.dongId ?? null}
              openRowId={openRowId}
              picked={picked}
              vanDeTheoDong={vanDeTheoDong}
              flash={flashKey === b.key}
              onTogglePickBand={onTogglePickBand}
              onOpenVanDe={onOpenVanDe}
              registerTrack={registerTrack}
              onOpenRow={openRowGuarded}
              onBarDown={onBarDown}
              onBarKey={onBarKey}
              onOpenKhoaForm={(mayId, rect) => setPop({ kind: "tao", mayId, rect })}
              onOpenKhoaDel={(item, rect) => setPop({ kind: "xoa", item, rect })}
              onOpenQuanSo={(t, rect) => setPop({ kind: "quan_so", tai: t, rect })}
            />
          ))}
        </div>
      </div>

      {pop?.kind === "tao" && (
        <KhoaForm winStart={winStart} rect={pop.rect} onClose={() => setPop(null)}
          onSave={(tu, den, ly_do, kieu) => taoKhoa(pop.mayId, tu, den, ly_do, kieu)} />
      )}
      {pop?.kind === "quan_so" && (
        <QuanSoForm
          tai={pop.tai}
          rect={pop.rect}
          onClose={() => setPop(null)}
          onSave={(so, lyDo) =>
            luuQuanSo(pop.tai.department_id, isoDay(wallMinutes(pop.tai.start)), so, lyDo)}
        />
      )}
      {pop?.kind === "xoa" && (
        <div className="xlcd-pop xlcd-gkhoa" style={fixedPop(pop.rect)} role="dialog">
          <p className="xlcd-gkhoa__t">
            {pop.item.kieu === "mo_them"
              ? "Máy chạy thêm"
              : (XEP_LICH_KHOA_LABELS[pop.item.ly_do] ?? pop.item.ly_do)} ·{" "}
            {ngayGio(pop.item.start)} → {ngayGio(pop.item.finish)}
          </p>
          <div className="xlcd-gkhoa__row">
            <Button variant="secondary" onClick={() => setPop(null)}>Huỷ</Button>
            <Button variant="danger" onClick={() => xoaKhoa(pop.item.id)}>
              {pop.item.kieu === "mo_them" ? "Bỏ giờ mở thêm" : "Bỏ khóa"}
            </Button>
          </div>
        </div>
      )}

      {impact && (
        <PreviewImpactDialog
          impact={impact}
          busy={impactBusy}
          onCancel={() => setImpact(null)}
          onTimKhe={timKhe}
          onChenTai={chenTai}
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
  band, scale, trackW, offRects, nowX, availMin, isMachine, maint, mocs, tai, canUpdate, ghost,
  dragId, openRowId, picked, vanDeTheoDong, flash, onTogglePickBand, onOpenVanDe,
  registerTrack, onOpenRow, onBarDown, onBarKey, onOpenKhoaForm, onOpenKhoaDel, onOpenQuanSo,
}: {
  band: Band;
  scale: TimeScale;
  trackW: number;
  offRects: { x: number; w: number }[];
  nowX: number | null;
  availMin: number;
  isMachine: boolean;
  maint: XepLichVungKhoaItem[];
  /** Kỳ bảo trì DỰ KIẾN của máy lane này — chỉ là cột mốc nhắc, không chặn xếp việc. */
  mocs: { ngay: string; goi_ten: string | null }[];
  canUpdate: boolean;
  ghost: Ghost | null;
  dragId: number | null;
  openRowId: number | null;
  picked: Set<number>;
  vanDeTheoDong: Map<number, XepLichVanDe[]>;
  flash: boolean;
  onTogglePickBand: (ids: number[]) => void;
  onOpenVanDe: (issueKey: string) => void;
  registerTrack: (key: string, el: HTMLDivElement | null) => void;
  onOpenRow: (id: number) => void;
  onBarDown: (r: XepLichRow, e: React.PointerEvent) => void;
  onBarKey: (r: XepLichRow, e: React.KeyboardEvent) => void;
  onOpenKhoaForm: (mayId: number, rect: DOMRect) => void;
  onOpenKhoaDel: (item: XepLichVungKhoaItem, rect: DOMRect) => void;
  /** Mức dùng người theo khoảng giờ của TỔ ở lane này (mục I). Rỗng với lane máy. */
  tai: XepLichTaiToKhoang[];
  onOpenQuanSo: (tai: XepLichTaiToKhoang, rect: DOMRect) => void;
}) {
  const mayId = band.rows[0]?.may_id ?? null;
  const scheduled = band.rows.filter((r) => r.start_at && r.finish_at);
  const choGio = band.rows.filter((r) => !r.start_at).length;
  const laneIds = band.rows.map((r) => r.id);
  const tickAll = laneIds.length > 0 && laneIds.every((id) => picked.has(id));
  const tickSome = !tickAll && laneIds.some((id) => picked.has(id));

  const packed = useMemo(() => packRows(scheduled.map((r) => ({
    r, x0: scale.xOf(wallMinutes(r.start_at as string)), x1: scale.xOf(wallMinutes(r.finish_at as string)),
  }))), [scheduled, scale]);
  const subRows = packed.length ? Math.max(...packed.map((p) => p.row)) + 1 : 1;
  const laneH = Math.max(68, subRows * BAR_H + (subRows - 1) * BAR_GAP + LANE_PAD * 2);

  const loadPct = useMemo(() => {
    if (!isMachine || availMin <= 0) return null;
    const used = scheduled.reduce((s, r) => {
      const t = wallMinutes(r.start_at as string);
      return t >= scale.winStart && t < scale.winEnd ? s + (r.chiem_may_phut || 0) : s;
    }, 0);
    return Math.round((used / availMin) * 100);
  }, [scheduled, availMin, isMachine, scale]);

  return (
    <div className={`xlcd-glane ${band.noMay ? "xlcd-glane--nomay" : ""}${flash ? " is-flash" : ""}`}
      style={{ height: laneH }}>
      <div className="xlcd-glane__label" style={{ width: LABEL_W }}>
        <div className="xlcd-glane__name">
          {/* Tick CẢ LANE — đường vào `BulkBar` (Tự xếp · Gán máy · Gán tổ · Khoá) sau khi bỏ ô
              tick từng dòng của view Bảng. Nhận cả dòng chưa có giờ: đó đúng là đám cần Tự xếp. */}
          {canUpdate && laneIds.length > 0 && (
            <input
              type="checkbox"
              className="xlcd-glane__tick"
              checked={tickAll}
              ref={(el) => { if (el) el.indeterminate = tickSome; }}
              onChange={() => onTogglePickBand(laneIds)}
              aria-label={`Chọn cả ${band.label}`}
              title="Chọn cả lane để xếp / gán hàng loạt"
            />
          )}
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
        {/* Mục I — NỀN MỨC DÙNG của lane TỔ. Tổ không chiếm trọn khoảng giờ như máy: ràng buộc
            thật nằm ở NGƯỜI. Nền cao dần theo tỉ lệ dùng/quân số, vượt thì đỏ — liếc một cái là
            thấy đoạn nào tổ đang gánh quá sức, không phải bấm sang tab Vấn đề mới biết.
            Số do SERVER quét (cùng nguồn với detector chặn phát hành), FE chỉ vẽ. */}
        {tai.map((k, i) => {
          const x = scale.xOf(wallMinutes(k.start));
          const w = Math.max(2, scale.xOf(wallMinutes(k.finish)) - x);
          const pct = k.quan_so > 0 ? Math.min(1, k.dung / k.quan_so) : 1;
          return (
            <div
              key={`t${i}`}
              className={`xlcd-gtai${k.qua_tai ? " is-over" : ""}${canUpdate ? " is-click" : ""}`}
              style={{ left: x, width: w, height: `${Math.round(pct * 100)}%` }}
              role={canUpdate ? "button" : undefined}
              title={
                `${k.dung}/${k.quan_so} người${k.qua_tai ? " — QUÁ TẢI" : ""}`
                + (canUpdate ? " · bấm để sửa quân số ngày này" : "")
              }
              onClick={canUpdate
                ? (e) => onOpenQuanSo(k, e.currentTarget.getBoundingClientRect())
                : undefined}
            />
          );
        })}
        {/* Hai kiểu khoảng riêng của máy (mục G3) vẽ KHÁC MÀU: `chan` = máy nghỉ (xám gạch),
            `mo_them` = máy chạy thêm ngoài ca (xanh). Cùng một màu thì vùng tăng ca đọc thành
            vùng bảo trì — đúng nghĩa ngược nhau. */}
        {maint.map((k) => {
          const x = scale.xOf(wallMinutes(k.start));
          const w = Math.max(3, scale.xOf(wallMinutes(k.finish)) - x);
          const them = k.kieu === "mo_them";
          return (
            <div key={`k${k.id}`}
              className={`xlcd-gback xlcd-gback--${them ? "mothem" : "maint"} ${canUpdate ? "is-click" : ""}`}
              style={{ left: x, width: w }}
              role={canUpdate ? "button" : undefined}
              title={`${them ? "Máy chạy thêm" : (XEP_LICH_KHOA_LABELS[k.ly_do] ?? k.ly_do)}: ${ngayGio(k.start)} → ${ngayGio(k.finish)}`}
              onClick={canUpdate ? (e) => onOpenKhoaDel(k, e.currentTarget.getBoundingClientRect()) : undefined} />
          );
        })}
        {/* Mốc TỚI HẠN BẢO TRÌ (mục 2i) — vạch nhắc, KHÔNG phải vùng chặn: `lich_bao_tri` chỉ khai
            hạn chứ không khai thời lượng, tự bịa "chặn 4 tiếng" là dựng ràng buộc không có thật. */}
        {mocs.map((m, i) => {
          const x = scale.xOf(wallMinutes(`${m.ngay}T08:00`));
          if (!Number.isFinite(x)) return null;
          return (
            <span key={`bt${i}`} className="xlcd-gmoc" style={{ left: x }}
              title={`Tới hạn bảo trì ${m.goi_ten ?? ""} · ${ngay(m.ngay)}`.replace(/\s+·/, " ·")} />
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
            dragging={dragId === r.id} canUpdate={canUpdate} active={openRowId === r.id}
            vanDe={vanDeTheoDong.get(r.id) ?? []} onOpenVanDe={onOpenVanDe}
            onOpen={onOpenRow} onDown={onBarDown} onKey={onBarKey} />
        ))}
      </div>
    </div>
  );
}

function GanttBar({
  r, scale, top, dragging, canUpdate, active, vanDe, onOpenVanDe, onOpen, onDown, onKey,
}: {
  r: XepLichRow;
  scale: TimeScale;
  top: number;
  dragging: boolean;
  canUpdate: boolean;
  /** Đang mở ở panel phải. */
  active: boolean;
  vanDe: XepLichVanDe[];
  onOpenVanDe: (issueKey: string) => void;
  onOpen: (id: number) => void;
  onDown: (r: XepLichRow, e: React.PointerEvent) => void;
  onKey: (r: XepLichRow, e: React.KeyboardEvent) => void;
}) {
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
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
  // RÂU nhanh–chậm: thanh đặt theo thời lượng TRUNG BÌNH, râu nói "xong sớm nhất / muộn nhất"
  // nếu máy chạy ở tốc độ tối đa / tối thiểu. Máy chưa khai dải ⇒ min = max = TB ⇒ không vẽ.
  let rau: { x: number; w: number } | null = null;
  const dMin = (r.chiem_may_phut_min || 0) - r.chiem_may_phut;
  const dMax = (r.chiem_may_phut_max || 0) - r.chiem_may_phut;
  if (r.finish_at && (dMin < -0.5 || dMax > 0.5)) {
    const fw = wallMinutes(r.finish_at);
    const x0 = scale.xOf(fw + Math.min(dMin, 0));
    const x1 = scale.xOf(fw + Math.max(dMax, 0));
    if (x1 > x0 + 1) rau = { x: x0, w: x1 - x0 };
  }
  const flag = r.nhan_rui_ro === "da_tre" || r.nhan_rui_ro === "nguy_co_tre" ? "TRỄ" : r.is_rush ? "GẤP" : null;
  // Đoạn setup (đầu công đoạn) — chỉ vẽ trên thanh AN TOÀN (thanh rủi ro giữ FILL trạng thái).
  const setupFrac = !isRisky(r) && r.chiem_may_phut > 0 ? Math.min(r.setup_phut / r.chiem_may_phut, 0.85) : 0;
  const draggable = canUpdate && !r.is_locked;
  const last = pieces.length - 1;

  const handleMouseEnter = (e: React.MouseEvent) => {
    setHoverPos({ x: e.clientX, y: e.clientY });
  };
  const handleMouseMove = (e: React.MouseEvent) => {
    setHoverPos({ x: e.clientX, y: e.clientY });
  };
  const handleMouseLeave = () => {
    setHoverPos(null);
  };

  const vdChan = vanDe.some((v) => v.severity === "chan");

  return (
    <>
      {/* Chip VẤN ĐỀ neo đầu thanh — mở thẳng hộp xử lý (tiếp nhận · giao việc · duyệt ngoại lệ).
          Nằm NGOÀI nút thanh: nút lồng trong nút là markup hỏng, mà chip lại phải bấm riêng. */}
      {vanDe.length > 0 && (
        <button
          type="button"
          className={`xlcd-gissue${vdChan ? " is-chan" : ""}`}
          style={{ left: Math.max(0, pieces[0].x - 6), top: top - 6 }}
          title={vanDe.map((v) => v.title).join("\n")}
          aria-label={`${vanDe.length} vấn đề — mở để xử lý`}
          onClick={(e) => { e.stopPropagation(); onOpenVanDe(vanDe[0].issue_key); }}
        >
          {vanDe.length}
        </button>
      )}
      {dry && (
        <span className="xlcd-gdry" style={{ left: dry.x, width: dry.w, top: top + BAR_H / 2 - 1 }} aria-hidden="true" />
      )}
      {rau && (
        <span
          className="xlcd-grau"
          style={{ left: rau.x, width: rau.w, top: top + BAR_H / 2 - 4 }}
          title={`Nhanh nhất ${thoiLuong(r.chiem_may_phut_min)} · chậm nhất ${thoiLuong(r.chiem_may_phut_max)}`}
          aria-hidden="true"
        />
      )}
      {pieces.map((p, i) => (
        <button
          key={i}
          type="button"
          className={`${barClass(r, dragging)} ${draggable ? "is-draggable" : ""}${active ? " is-active" : ""}`}
          style={{ left: p.x, width: p.w, top, height: BAR_H }}
          aria-label={tip.replace(/\n/g, " · ")}
          onPointerDown={i === 0 && draggable ? (e) => onDown(r, e) : undefined}
          onKeyDown={i === 0 && draggable ? (e) => onKey(r, e) : undefined}
          onMouseEnter={handleMouseEnter}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onClick={() => { setHoverPos(null); onOpen(r.id); }}
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
              {/* Mục I — lane TỔ cho thanh CHỒNG NHAU (tổ 8 người chạy 2 việc cùng lúc là bình
                  thường), nên phải ghi SỐ NGƯỜI trên từng thanh: nhìn hai thanh chồng nhau mà
                  không biết mỗi cái ăn mấy người thì không đọc ra tổ có quá tải hay không. */}
              {r.department_id != null && p.w >= 96 && (r.so_nhan_cong ?? 0) > 0 && (
                <span className="xlcd-gbar__nguoi">{r.so_nhan_cong} người</span>
              )}
            </span>
          )}
        </button>
      ))}

      {hoverPos && !dragging && (
        <div
          className="xlcd-gtip-card"
          style={{
            left: Math.min(hoverPos.x + 14, window.innerWidth - 300),
            top: Math.min(hoverPos.y + 14, window.innerHeight - 220),
          }}
        >
          <div className="xlcd-gtip-card__head">
            <span className="xlcd-gtip-card__title">{r.lsx_ma ?? ""} · {r.cong_doan_ten ?? ""}</span>
            {flag && <span className="xlcd-gbadge xlcd-gbadge--flag">{flag}</span>}
          </div>
          <div className="xlcd-gtip-card__res">
            <Icon name="printer" size={12} />
            <span>{r.may_ten ?? r.department_ten ?? r.nha_cung_cap ?? "Chưa gán máy"}</span>
          </div>
          <div className="xlcd-gtip-card__time">
            <Icon name="clock" size={12} />
            <span>{ngayGio(r.start_at)} → {ngayGio(r.finish_at)}</span>
          </div>
          <div className="xlcd-gtip-card__breakdown">
            <span>Thiết lập: {thoiLuong(r.setup_phut)}</span>
            <span>Chạy: {thoiLuong(r.chay_phut)}</span>
            {(r.chiem_may_phut_max || 0) - (r.chiem_may_phut_min || 0) > 0.5 && (
              <span>Nhanh–chậm: {thoiLuong(r.chiem_may_phut_min)} – {thoiLuong(r.chiem_may_phut_max)}</span>
            )}
          </div>
          {(r.canh_bao_thoi_luong || r.ly_do_xac_nhan.length > 0) && (
            <div className="xlcd-gtip-card__warns">
              {r.canh_bao_thoi_luong && (
                <div className="xlcd-gtip-card__warn">
                  <Icon name="alert" size={11} />
                  <span>{XEP_LICH_CANH_BAO_TL_LABELS[r.canh_bao_thoi_luong] ?? r.canh_bao_thoi_luong}</span>
                </div>
              )}
              {r.ly_do_xac_nhan.map((ld, idx) => (
                <div key={idx} className="xlcd-gtip-card__warn">
                  <Icon name="alert" size={11} />
                  <span>{XEP_LICH_XAC_NHAN_LABELS[ld] ?? ld}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function PreviewImpactDialog({
  impact, busy, onCancel, onTimKhe, onChenTai, onConfirm,
}: {
  impact: Impact;
  busy: boolean;
  onCancel: () => void;
  onTimKhe: () => void;
  onChenTai: () => void;
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
          {/* CẢNH BÁO TẠI CHỖ (đợt 2) — đè khoảng khoá máy · ngoài giờ làm · tổ thiếu người · khổ
              vượt máy. Chủ chốt chốt: báo đỏ ngay, KHÔNG chặn. Nút "Vẫn xếp" luôn bấm được. */}
          {pv.canh_bao.length > 0 && (
            <section className="xlcd-gimpact__sec xlcd-gimpact__sec--warn">
              <p className="xlcd-gimpact__t"><Icon name="alert" size={13} /> Xếp được, nhưng nên biết</p>
              <ul>{pv.canh_bao.map((c, i) => <li key={`${c.loai}-${i}`}>{c.chu}</li>)}</ul>
            </section>
          )}
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

        {/* Trước đây chỉ có Huỷ / Vẫn xếp: gặp chỗ kín thì đóng hộp rồi tự đi dò khe trống bằng
            mắt. Hai nút giữa trả lời hộ đúng hai câu tiếp theo — "vậy xếp vào đâu" và "cứ chèn
            vào đây, các việc sau lùi ra". Cả hai vẫn chỉ TÍNH, chưa ghi. */}
        <footer className="xlcd-gimpact__foot">
          <Button variant="secondary" onClick={onCancel}>Huỷ</Button>
          <div className="khsx__spacer" />
          <Button variant="ghost" disabled={busy} onClick={onTimKhe}>
            {busy ? "Đang tìm…" : "Tìm khe trống"}
          </Button>
          {impact.body.start_at && (
            <Button variant="ghost" onClick={onChenTai}>Chèn — lùi các việc sau</Button>
          )}
          <Button variant="primary" onClick={onConfirm}>Vẫn xếp</Button>
        </footer>
      </div>
    </div>
  );
}

/** Form khoảng giờ riêng của MỘT máy — dùng chung cho hai kiểu (mục G3).
 *
 *  Trước đây chỉ khai được "máy nghỉ"; *"tối thứ Tư máy in 2 chạy thêm 3 tiếng"* không có chỗ nào
 *  ghi (lịch xưởng chỉ khai làm bù cho CẢ nhà máy). Cùng một form, đổi ô "Loại khoảng" là đủ —
 *  tách hai màn thì thành hai nơi phải nhớ khi vẽ Gantt và khi cộng giờ.
 *
 *  Ô "Lý do" chỉ có nghĩa với kiểu `chan`: một khoảng CHẠY THÊM mà mang lý do "bảo trì" thì đọc
 *  lại là hiểu ngược, nên ẩn hẳn (server cũng tự ép về `khac`).
 */
function KhoaForm({
  winStart, rect, onClose, onSave,
}: {
  winStart: number;
  rect: DOMRect;
  onClose: () => void;
  onSave: (tu: string, den: string, ly_do: string, kieu: XepLichKieuKhoang) => void;
}) {
  const [tu, setTu] = useState(() => isoLocal(winStart + 8 * 60));      // ~08:00 ngày đầu
  const [den, setDen] = useState(() => isoLocal(winStart + 10 * 60));   // ~10:00
  const [lyDo, setLyDo] = useState("bao_tri");
  const [kieu, setKieu] = useState<XepLichKieuKhoang>("chan");
  const moThem = kieu === "mo_them";
  const ok = tu.length === 16 && den.length === 16 && tu < den;
  return (
    <div className="xlcd-pop xlcd-gkhoa" style={fixedPop(rect)} role="dialog"
      aria-label="Thêm khoảng giờ riêng của máy">
      <label className="xlcd-gkhoa__f">Loại khoảng
        <select value={kieu} onChange={(e) => setKieu(e.target.value as XepLichKieuKhoang)}>
          <option value="chan">Máy nghỉ — không xếp việc vào</option>
          <option value="mo_them">Máy chạy thêm — làm cả ngoài ca</option>
        </select>
      </label>
      {!moThem && (
        <label className="xlcd-gkhoa__f">Lý do
          <select value={lyDo} onChange={(e) => setLyDo(e.target.value)}>
            {KHOA_REASONS.map((k) => <option key={k} value={k}>{XEP_LICH_KHOA_LABELS[k]}</option>)}
          </select>
        </label>
      )}
      <label className="xlcd-gkhoa__f">Từ
        <input type="datetime-local" value={tu} onChange={(e) => setTu(e.target.value)} />
      </label>
      <label className="xlcd-gkhoa__f">Đến
        <input type="datetime-local" value={den} onChange={(e) => setDen(e.target.value)} />
      </label>
      {moThem && (
        <p className="xlcd-gkhoa__hint">
          Máy được xếp việc trong khoảng này kể cả ngoài ca thường của nó.
        </p>
      )}
      <div className="xlcd-gkhoa__row">
        <Button variant="secondary" onClick={onClose}>Huỷ</Button>
        <Button variant="accent" disabled={!ok} onClick={() => onSave(tu, den, lyDo, kieu)}>
          {moThem ? "Mở thêm giờ" : "Khóa máy"}
        </Button>
      </div>
    </div>
  );
}

/** Gõ đè QUÂN SỐ của một tổ trong MỘT NGÀY (mục I).
 *
 *  Mở từ chính khoảng đang đỏ trên lane tổ, nên không phải hỏi "ngày nào, tổ nào" — hai thứ đó đã
 *  nằm trong cái người dùng vừa bấm.
 *
 *  Bắt gõ LÝ DO: con số này ĐÈ lên dữ liệu nhân sự (hồ sơ + đơn phép đã duyệt). Không có lý do thì
 *  tháng sau không ai giải thích nổi vì sao hôm đó lịch tính theo 6 người trong khi hồ sơ nói 3.
 *
 *  Nút "Bỏ gõ đè" trả về số tự tính — cần có, không thì gõ nhầm một lần là con số sai nằm lại mãi.
 */
function QuanSoForm({ tai, rect, onClose, onSave }: {
  tai: XepLichTaiToKhoang;
  rect: DOMRect;
  onClose: () => void;
  onSave: (soNguoi: number | null, lyDo: string) => void;
}) {
  const [so, setSo] = useState(String(tai.quan_so));
  const [lyDo, setLyDo] = useState("");
  const n = Number(so);
  const ok = so !== "" && Number.isFinite(n) && n >= 0 && lyDo.trim().length >= 3;
  return (
    <div className="xlcd-pop xlcd-gkhoa" style={fixedPop(rect)} role="dialog"
      aria-label="Sửa quân số tổ">
      <p className="xlcd-gkhoa__t">
        {tai.department_ten ?? "Tổ"} · {ngay(tai.start)}
        <br />
        <span className={tai.qua_tai ? "xlcd-drawer-rush" : ""}>
          Đang cần {tai.dung} người, có mặt {tai.quan_so}
        </span>
      </p>
      <label className="xlcd-gkhoa__f">Số người có mặt hôm nay
        <input type="number" min="0" value={so} onChange={(e) => setSo(e.target.value)} />
      </label>
      <label className="xlcd-gkhoa__f">Lý do
        <input value={lyDo} onChange={(e) => setLyDo(e.target.value)}
          placeholder="Vd: mượn 3 người tổ Bế" />
      </label>
      <p className="xlcd-gkhoa__hint">
        Số này đè lên hồ sơ nhân sự cho RIÊNG ngày này. Bỏ gõ đè để quay về số tự tính từ hồ sơ.
      </p>
      <div className="xlcd-gkhoa__row">
        <Button variant="secondary" onClick={onClose}>Huỷ</Button>
        <Button variant="ghost" onClick={() => onSave(null, "bỏ gõ đè")}>Bỏ gõ đè</Button>
        <Button variant="accent" disabled={!ok} onClick={() => onSave(n, lyDo.trim())}>Lưu</Button>
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
    // Hai kiểu nền của mục G3 — chú giải phải có, không thì hai mảng màu lạ trên lane không ai đọc ra.
    { type: "maint", label: "Máy nghỉ" },
    { type: "mothem", label: "Chạy thêm ngoài ca" },
    { type: "taito", label: "Tổ quá tải người" },
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
