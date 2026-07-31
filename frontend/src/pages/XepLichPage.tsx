// BÀN XẾP LỊCH CÔNG ĐOẠN — biến routing đã "sẵn sàng" thành công việc CÓ MÁY + GIỜ.
//
// Luồng: LSX / bài ghép sẵn sàng nằm ở KHAY "Chờ lập kế hoạch" → "Đưa vào kế hoạch" sinh dòng lịch →
// BẢNG (phải) gom theo Máy / Lệnh / Bài ghép → gán máy·ca·giờ (inline hoặc drawer) → hệ tính giờ kết
// thúc + độ dư + nhãn nguy cơ + cờ xung đột → khóa khi chốt. MÁY CHỈ GHI NHẬN — người kế hoạch quyết.
//
// Kiến trúc: data phẳng (`rows: XepLichRow[]`) tách khỏi render; group/filter/search client-side để lát
// sau cắm Gantt dễ. Điều hướng bằng state qua AppShell (không react-router). Real-time qua `eventTick`.
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  ApiError,
  LSX_LOAI_BUOC_META,
  XEP_LICH_BLOCKED_LABELS,
  XEP_LICH_XAC_NHAN_LABELS,
  api,
  type LsxLoaiBuoc,
  type XepLichGanBody,
  type XepLichGanLoatRow,
  type XepLichGoiY,
  type XepLichHangChoItem,
  type XepLichNguon,
  type XepLichRow,
  type XepLichSanSangOut,
  type XepLichVanDeListOut,
} from "../api/client";
import { crud, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { Icon, type IconName } from "../components/Icons";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DetailModal } from "../components/DetailModal";
import {
  BangLoi,
  ChuoiCongDoan,
  EmptyState,
  LichTrangThaiPill,
  NguyCoTreChip,
  classHan,
  ngay,
  ngayGio,
  num,
  thoiLuong,
} from "./keHoachSxShared";
import { GanttBoard } from "./GanttBoard";
import { VanDeView, type PhuongAnNav } from "./XepLichVanDeView";
import "./ke-hoach-sx.css"; // primitive dùng lại: .khsx-pill · .khsx-seg · .khsx-scrim · .khsx-drawer--buoc · .khsx-nhom …
import "./xep-lich.css";

// ============================ hằng số + helper thuần =========================
export type GroupBy = "may" | "lenh" | "bai-ghep";
interface Filters { thueNgoai: boolean; chiXungDot: boolean }

const GROUP_TABS: { key: GroupBy; label: string; icon: IconName }[] = [
  { key: "may", label: "Máy", icon: "printer" },
  { key: "lenh", label: "Lệnh", icon: "clipboard" },
  { key: "bai-ghep", label: "Bài ghép", icon: "layers" },
];

// Ca cứng — chưa có danh mục ca; `work_shift_id` là FK MỀM nên id 1/2/3 an toàn (để trống được).
const CA_OPTIONS: { id: number; label: string }[] = [
  { id: 1, label: "Sáng" },
  { id: 2, label: "Chiều" },
  { id: 3, label: "Đêm" },
];
const caLabel = (id: number | null | undefined): string | null =>
  id == null ? null : CA_OPTIONS.find((c) => c.id === id)?.label ?? null;

// Nhóm cột ẩn/hiện được (lưu localStorage) — 3 cột phụ dẫn xuất.
const COL_GROUPS: { key: string; label: string }[] = [
  { key: "somNhat", label: "Sớm nhất" },
  { key: "ketThuc", label: "Kết thúc" },
  { key: "thoiLuong", label: "Thời lượng" },
];
const COLS_LS_KEY = "xlcd.cols";
const VIEW_LS_KEY = "xlcd.view";

type ViewMode = "bang" | "gantt" | "van-de";
function loadViewLS(): ViewMode {
  try {
    const v = localStorage.getItem(VIEW_LS_KEY);
    return v === "gantt" || v === "van-de" ? v : "bang";
  } catch { return "bang"; }
}

function loadColsLS(): Set<string> {
  try {
    const raw = localStorage.getItem(COLS_LS_KEY);
    if (raw) return new Set(JSON.parse(raw) as string[]);
  } catch {
    /* ignore */
  }
  return new Set();
}

/** Bỏ dấu để tìm kiếm (bám RefSearchField của RebuildCatalogPage). */
const norm = (s: string): string =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");

type ResKind = "may" | "to" | "ncc" | "none";
/** Bước chiếm gì → ô "Máy/NCC" gán field nào. */
function resKind(lb: LsxLoaiBuoc | null): ResKind {
  if (lb === "thue_ngoai") return "ncc";
  if (lb === "to" || lb === "kcs") return "to";
  if (lb === "cho") return "none";
  return "may"; // may · xa_to · (in chung của bài ghép)
}
function resText(r: XepLichRow): string | null {
  switch (resKind(r.loai_buoc)) {
    case "ncc": return r.nha_cung_cap;
    case "to": return r.department_ten;
    case "none": return null;
    default: return r.may_ten;
  }
}

// datetime-local ↔ ISO GIỜ NHÀ MÁY (không đổi múi — lấy wall-clock trực tiếp).
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}` : "";
}
function fromLocalInput(local: string): string | null {
  if (!local) return null;
  return local.length === 16 ? `${local}:00` : local; // gửi NAIVE → server coi là giờ nhà máy
}
function pad2(n: number): string {
  return String(n).padStart(2, "0");
}
/** Đầu ca kế = 08:00 ngày làm kế tiếp (xấp xỉ client — server chốt lịch nghỉ khi lưu). */
function nextShiftStart(fromLocal: string): string {
  const base = fromLocal ? new Date(`${fromLocal.length === 16 ? `${fromLocal}:00` : fromLocal}`) : new Date();
  const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + 1, 8, 0, 0);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

// Popover ô inline dùng FIXED (bảng có overflow → absolute bị cắt). Neo tại đáy nút, kẹp trong màn.
function popStyle(a: DOMRect, width = 280): CSSProperties {
  const pad = 16;
  const left = Math.max(pad, Math.min(a.left, window.innerWidth - width - pad));
  const top = Math.min(a.bottom + 6, window.innerHeight - 280);
  return { position: "fixed", top, left, width, zIndex: 9999 };
}

function stepIcon(lb: LsxLoaiBuoc | null, ten?: string | null): IconName {
  if (lb === "thue_ngoai") return "truck";
  if (lb === "kcs") return "shield";
  if (lb === "xa_to" || lb === "bai_ghep") return "layers";
  if (lb === "to") return "building";
  if (lb === "may") {
    const t = (ten ?? "").toLowerCase();
    if (t.includes("ctp") || t.includes("kẽm") || t.includes("in")) return "printer";
    if (t.includes("xén") || t.includes("bế") || t.includes("cắt")) return "scissors";
    if (t.includes("gấp") || t.includes("bắt") || t.includes("dán") || t.includes("vào keo")) return "layers";
    if (t.includes("đóng gói") || t.includes("nhập kho")) return "box";
    return "printer";
  }
  return "clipboard";
}

// ============================ controller =====================================
export function XepLichPage({
  navigate,
  eventTick,
  onBadgeStale,
}: {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  const canCreate = can("san_xuat", "create");
  const canUpdate = can("san_xuat", "update");
  const canApprove = can("san_xuat", "approve"); // quyền PHÁT (can_approve) — nút Phát hành
  const canApproveException = can("san_xuat", "approve_exception"); // duyệt ngoại lệ — nút Xin ngoại lệ (tách khỏi phát hành)

  const [rows, setRows] = useState<XepLichRow[] | null>(null);
  const [queue, setQueue] = useState<XepLichHangChoItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mays, setMays] = useState<Row[]>([]);
  const [phongBans, setPhongBans] = useState<Row[]>([]);
  // View "Vấn đề": xung đột & nguy cơ trễ (dẫn xuất) + danh sách sẵn-sàng-phát-hành. Nạp LUÔN (không
  // chỉ khi mở view) để badge Chặn trên tab + chỉ báo readiness ở header tự nhảy theo SSE.
  const [vanDe, setVanDe] = useState<XepLichVanDeListOut | null>(null);
  const [sanSang, setSanSang] = useState<XepLichSanSangOut | null>(null);
  const [vanDeErr, setVanDeErr] = useState<string | null>(null);

  const [groupBy, setGroupBy] = useState<GroupBy>("may");
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewLS);
  const [filters, setFilters] = useState<Filters>({ thueNgoai: false, chiXungDot: false });
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [openRowId, setOpenRowId] = useState<number | null>(null);
  const [queueOpen, setQueueOpen] = useState(false);
  const [isFocusMode, setIsFocusMode] = useState(false);
  const [colsHidden, setColsHidden] = useState<Set<string>>(loadColsLS);
  const [colsMenuOpen, setColsMenuOpen] = useState(false);
  const [collapsedBands, setCollapsedBands] = useState<Set<string>>(new Set());
  const [flashBandKey, setFlashBandKey] = useState<string | null>(null);
  const [pendingFlash, setPendingFlash] = useState<{ nguon: XepLichNguon; id: number } | null>(null);
  const [toast, setToast] = useState<{ text: string; undo?: () => void } | null>(null);
  const [askGo, setAskGo] = useState<XepLichHangChoItem | null>(null);

  const bandElRefs = useRef<Map<string, HTMLTableRowElement | null>>(new Map());
  const wrapRef = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ l: false, r: false });

  // ---- nạp dữ liệu ----
  const load = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.xepLich.dong(token).then((r) => setRows(r.items)).catch((e: unknown) =>
      setErr(e instanceof ApiError ? e.message : String(e)),
    );
    api.xepLich.hangCho(token).then((r) => setQueue(r.items)).catch(() => {});
  }, [token]);
  useEffect(() => load(), [load, eventTick]);

  // Vấn đề + sẵn-sàng-phát-hành: 1 lần nạp, cả badge Chặn (tab) lẫn view Vấn đề dùng chung state.
  const loadVanDe = useCallback(() => {
    if (!token) return;
    setVanDeErr(null);
    api.xepLich.vanDe(token).then(setVanDe).catch((e: unknown) =>
      setVanDeErr(e instanceof ApiError ? e.message : String(e)),
    );
    api.xepLich.sanSangPhatHanh(token).then(setSanSang).catch(() => {});
  }, [token]);
  useEffect(() => loadVanDe(), [loadVanDe, eventTick]);

  useEffect(() => {
    if (!token) return;
    crud("/api/may-thiet-bi").list(token).then((r) => setMays(r.items)).catch(() => {});
    crud("/api/cong-doan/phong-ban").list(token).then((r) => setPhongBans(r.items)).catch(() => {});
  }, [token]);

  useEffect(() => {
    try { localStorage.setItem(COLS_LS_KEY, JSON.stringify([...colsHidden])); } catch { /* ignore */ }
  }, [colsHidden]);

  useEffect(() => {
    try { localStorage.setItem(VIEW_LS_KEY, viewMode); } catch { /* ignore */ }
  }, [viewMode]);

  useEffect(() => {
    if (!toast?.undo) {
      if (!toast) return;
      const t = setTimeout(() => setToast(null), 4000);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(t);
  }, [toast]);

  // ---- lọc + tìm client-side ----
  const coLoc = filters.thueNgoai || filters.chiXungDot || q.trim() !== "";
  const filtered = useMemo(() => {
    if (!rows) return [];
    const nq = norm(q.trim());
    return rows.filter((r) => {
      if (filters.thueNgoai && r.loai_buoc !== "thue_ngoai") return false;
      if (filters.chiXungDot && !r.co_xung_dot) return false;
      if (nq && !norm(`${r.lsx_ma ?? ""} ${r.cong_doan_ten ?? ""}`).includes(nq)) return false;
      return true;
    });
  }, [rows, filters, q]);

  const summary = useMemo(() => {
    const all = rows ?? [];
    return {
      cho: all.filter((r) => r.trang_thai !== "da_xep").length,
      daXep: all.filter((r) => r.trang_thai === "da_xep").length,
      xungDot: all.filter((r) => r.co_xung_dot).length,
    };
  }, [rows]);

  // ---- gom band ----
  const bands = useMemo<Band[]>(() => {
    const map = new Map<string, Band>();
    for (const r of filtered) {
      const bi = bandInfo(r, groupBy);
      let b = map.get(bi.key);
      if (!b) { b = { ...bi, rows: [] }; map.set(bi.key, b); }
      b.rows.push(r);
    }
    const arr = [...map.values()];
    arr.sort((a, b) =>
      a.noMay ? -1 : b.noMay ? 1 : a.label.localeCompare(b.label, "vi"),
    );
    return arr;
  }, [filtered, groupBy]);

  const flatOrder = useMemo(() => bands.flatMap((b) => b.rows), [bands]);
  const openRow = useMemo(
    () => (openRowId == null ? null : (rows ?? []).find((r) => r.id === openRowId) ?? null),
    [openRowId, rows],
  );

  // ---- cạnh cuộn (shadow 2 mép) ----
  const recomputeEdge = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    setEdge({ l: el.scrollLeft > 0, r: el.scrollLeft < el.scrollWidth - el.clientWidth - 1 });
  }, []);
  useEffect(() => { recomputeEdge(); }, [recomputeEdge, filtered, colsHidden, queueOpen]);

  // ---- cuộn tới band vừa thêm + nháy ----
  useEffect(() => {
    if (!pendingFlash || !rows) return;
    const first = filtered.find((r) =>
      pendingFlash.nguon === "in_ghep"
        ? r.bai_ghep_id === pendingFlash.id
        : r.nguon === "lsx" && r.lsx_id === pendingFlash.id,
    );
    setPendingFlash(null);
    if (!first) return;
    const bk = bandInfo(first, groupBy).key;
    bandElRefs.current.get(bk)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlashBandKey(bk);
    const t = setTimeout(() => setFlashBandKey(null), 1300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, pendingFlash]);

  // ---- áp kết quả server vào bảng ----
  const applyRow = useCallback((row: XepLichRow) => {
    setRows((prev) => (prev ? prev.map((r) => (r.id === row.id ? row : r)) : prev));
  }, []);
  const applyRows = useCallback((list: XepLichRow[]) => {
    setRows((prev) => {
      if (!prev) return prev;
      const m = new Map(list.map((r) => [r.id, r]));
      return prev.map((r) => m.get(r.id) ?? r);
    });
  }, []);

  const mayName = useCallback((id: number | null) =>
    id == null ? null : mays.find((m) => m.id === id)?.ten ?? null, [mays]);
  const deptName = useCallback((id: number | null) =>
    id == null ? null : phongBans.find((d) => d.id === id)?.ten ?? null, [phongBans]);

  // Điều hướng "phương án" từ view Vấn đề — MÁY CHỈ GHI NHẬN: đổi view / nhảy màn, KHÔNG auto-fix.
  // Nhánh bảng: xoá lọc để dòng cần xem chắc chắn hiện, rồi tái dùng pendingFlash để cuộn + nháy band.
  const onPhuongAn = useCallback((p: PhuongAnNav) => {
    if (p.kind === "man-ke-hoach") { navigate?.("ke-hoach-sx"); return; }
    if (p.kind === "gantt-may") { setGroupBy("may"); setViewMode("gantt"); return; }
    setFilters({ thueNgoai: false, chiXungDot: false });
    if (p.kind === "bang-ma") { setQ(p.ma); setGroupBy("lenh"); setViewMode("bang"); return; }
    setQ("");
    if (p.kind === "bang-lenh") { setGroupBy("lenh"); setViewMode("bang"); if (p.flash) setPendingFlash(p.flash); return; }
    if (p.kind === "bang-bai-ghep") { setGroupBy("bai-ghep"); setViewMode("bang"); if (p.flash) setPendingFlash(p.flash); }
  }, [navigate]);

  // ---- gán 1 dòng (optimistic → PUT → cập nhật) ----
  const onGan = useCallback(async (id: number, body: XepLichGanBody) => {
    if (!token) return;
    const before = (rows ?? []).find((r) => r.id === id) ?? null;
    if (before) {
      const opt = { ...before };
      if ("may_id" in body) { opt.may_id = body.may_id ?? null; opt.may_ten = mayName(body.may_id ?? null); }
      if ("department_id" in body) { opt.department_id = body.department_id ?? null; opt.department_ten = deptName(body.department_id ?? null); }
      if ("nha_cung_cap" in body) opt.nha_cung_cap = body.nha_cung_cap ?? null;
      if ("work_shift_id" in body) opt.work_shift_id = body.work_shift_id ?? null;
      if ("start_at" in body) opt.start_at = body.start_at ?? null;
      applyRow(opt);
    }
    try {
      const r = await api.xepLich.gan(token, id, body);
      applyRow(r);
      onBadgeStale?.();
    } catch (e: unknown) {
      if (before) applyRow(before); // revert
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [token, rows, applyRow, mayName, deptName, onBadgeStale]);

  // ---- gợi ý (goi-y) ----
  const fetchGoiY = useCallback(
    (id: number) => (token ? api.xepLich.goiY(token, id) : Promise.reject(new Error("no token"))),
    [token],
  );

  // ---- khay: đưa vào / gỡ ----
  const duaVao = useCallback(async (item: XepLichHangChoItem) => {
    if (!token) return;
    try {
      if (item.nguon === "lsx") await api.xepLich.duaVaoLsx(token, item.id);
      else await api.xepLich.duaVaoBaiGhep(token, item.id);
      setPendingFlash({ nguon: item.nguon, id: item.id });
      setToast({ text: `Đã đưa ${item.ma} vào kế hoạch` });
      load();
      onBadgeStale?.();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [token, load, onBadgeStale]);

  const goKeHoach = useCallback(async (item: XepLichHangChoItem) => {
    if (!token) return;
    try {
      if (item.nguon === "lsx") await api.xepLich.goLsx(token, item.id);
      else await api.xepLich.goBaiGhep(token, item.id);
      setToast({ text: `Đã gỡ ${item.ma} khỏi kế hoạch` });
      load();
      onBadgeStale?.();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setAskGo(null);
    }
  }, [token, load, onBadgeStale]);

  // Lệnh/bài ghép ĐÃ đưa vào (để khay biết cái nào cho "Gỡ"). Suy từ bảng dòng.
  const daVaoKeHoach = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows ?? []) {
      if (r.lsx_id) s.add(`lsx-${r.lsx_id}`);
      if (r.bai_ghep_id) s.add(`in_ghep-${r.bai_ghep_id}`);
    }
    return s;
  }, [rows]);

  // ---- chọn ----
  const togglePick = useCallback((id: number) => {
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);
  const clearPick = useCallback(() => setPicked(new Set()), []);
  const pickableIds = useMemo(
    () => filtered.filter((r) => !r.blocked_reason).map((r) => r.id),
    [filtered],
  );
  const allPicked = pickableIds.length > 0 && pickableIds.every((id) => picked.has(id));
  const togglePickAll = useCallback(() => {
    setPicked((prev) => (pickableIds.every((id) => prev.has(id)) ? new Set() : new Set(pickableIds)));
  }, [pickableIds]);

  // ---- bulk ----
  const bulkGan = useCallback(async (patch: XepLichGanBody, label: string) => {
    if (!token) return;
    const targets = (rows ?? []).filter((r) => picked.has(r.id) && !r.is_locked && !r.blocked_reason);
    if (!targets.length) { setToast({ text: "Không có dòng phù hợp để gán (bỏ qua dòng khóa/chưa đủ điều kiện)" }); return; }
    const before = new Map(targets.map((r) => [r.id, r] as const));
    const payload: XepLichGanLoatRow[] = targets.map((r) => ({ id: r.id, ...patch }));
    try {
      const res = await api.xepLich.ganLoat(token, payload);
      applyRows(res.items);
      onBadgeStale?.();
      setToast({
        text: `${label} cho ${targets.length} dòng`,
        undo: async () => {
          const undo: XepLichGanLoatRow[] = targets.map((r) => ({ id: r.id, ...undoFields(patch, before.get(r.id)!) }));
          try { applyRows((await api.xepLich.ganLoat(token, undo)).items); onBadgeStale?.(); setToast(null); }
          catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
        },
      });
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [token, rows, picked, applyRows, onBadgeStale]);

  const bulkKhoa = useCallback(async (khoa: boolean) => {
    if (!token) return;
    const ids = [...picked];
    if (!ids.length) return;
    try {
      const res = await Promise.all(ids.map((id) => (khoa ? api.xepLich.khoa(token, id, true) : api.xepLich.moKhoa(token, id))));
      applyRows(res);
      onBadgeStale?.();
      setToast({ text: khoa ? `Đã khóa ${ids.length} dòng` : `Đã gỡ khóa ${ids.length} dòng` });
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [token, picked, applyRows, onBadgeStale]);

  const bulkAuto = useCallback(async () => {
    if (!token) return;
    const targets = (rows ?? []).filter((r) => picked.has(r.id) && r.may_id != null && !r.is_locked && !r.blocked_reason);
    if (!targets.length) { setToast({ text: "Chọn dòng đã có máy (chưa khóa) để tự xếp" }); return; }
    const before = new Map(targets.map((r) => [r.id, r.start_at] as const));
    try {
      // Gán TUẦN TỰ (await từng dòng): dòng sau gọi gợi ý SAU khi dòng trước đã chiếm khe → né nhau,
      // không dồn cùng một giờ (gom gợi ý rồi gán một lượt sẽ khiến mọi dòng nhận cùng khe trống).
      const done: XepLichRow[] = [];
      for (const r of targets) {
        const g = await api.xepLich.goiY(token, r.id);
        if (g.khe_trong) done.push(await api.xepLich.gan(token, r.id, { start_at: g.khe_trong }));
      }
      if (!done.length) { setToast({ text: "Chưa tìm được khe trống phù hợp" }); return; }
      applyRows(done);
      onBadgeStale?.();
      setToast({
        text: `Tự xếp ${done.length} dòng vào khe trống sớm nhất`,
        undo: async () => {
          const undo: XepLichGanLoatRow[] = done.map((p) => ({ id: p.id, start_at: before.get(p.id) ?? null }));
          try { applyRows((await api.xepLich.ganLoat(token, undo)).items); onBadgeStale?.(); setToast(null); }
          catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
        },
      });
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }, [token, rows, picked, applyRows, onBadgeStale]);

  // ---- cột hiện ----
  const show = {
    somNhat: !colsHidden.has("somNhat"),
    ketThuc: !colsHidden.has("ketThuc"),
    thoiLuong: !colsHidden.has("thoiLuong"),
  };
  const colCount = 9 + (show.somNhat ? 1 : 0) + (show.ketThuc ? 1 : 0) + (show.thoiLuong ? 1 : 0);

  // ---- dẫn xuất view Vấn đề (badge tab + readiness header) ----
  const vanDeSummary = vanDe?.summary ?? null;
  const chanCount = vanDeSummary?.chan ?? 0;
  const tongVanDe = vanDeSummary?.tong ?? 0;
  const readyCount = (sanSang?.items ?? []).filter((i) => i.blocking === 0).length;
  const currentUserId = user?.id ?? null;

  // ---- điều hướng drawer ----
  const drawerIdx = openRow ? flatOrder.findIndex((r) => r.id === openRow.id) : -1;
  const goPrev = drawerIdx > 0 ? () => setOpenRowId(flatOrder[drawerIdx - 1].id) : undefined;
  const goNext =
    drawerIdx >= 0 && drawerIdx < flatOrder.length - 1 ? () => setOpenRowId(flatOrder[drawerIdx + 1].id) : undefined;

  return (
    <main className={`xlcd ${isFocusMode ? "xlcd--focus" : ""}`}>
      <header className="khsx__head xlcd-head">
        <div className="khsx__headrow">
          <div>
            <p className="eyebrow">Sản xuất</p>
            <h1 className="khsx__title">Xếp lịch công đoạn</h1>
          </div>
          <div className="xlcd-badges">
            <button
              type="button"
              className="xlcd-badge xlcd-badge--cho xlcd-badge--btn"
              onClick={() => setQueueOpen(true)}
              title="Mở khay lệnh / bài ghép chờ đưa vào kế hoạch"
            >
              <span className="xlcd-badge__num">{num(queue?.length ?? 0)}</span> chờ lập kế hoạch
              <span className="xlcd-badge__hint">Mở khay</span>
            </button>
            <span className="xlcd-badge">
              <span className="xlcd-badge__num">{num(summary.cho)}</span> chưa xếp giờ
            </span>
            <span className="xlcd-badge xlcd-badge--daxep">
              <span className="xlcd-badge__num">{num(summary.daXep)}</span> đã xếp
            </span>
            {summary.xungDot > 0 && (
              <span className="xlcd-badge xlcd-badge--alert">
                <span className="xlcd-badge__num">{num(summary.xungDot)}</span> xung đột
              </span>
            )}
            {sanSang && readyCount > 0 && (
              <span className="xlcd-badge xlcd-badge--ready">
                <span className="xlcd-badge__num">{num(readyCount)}</span> sẵn sàng phát hành
              </span>
            )}
          </div>
        </div>
      </header>

      {err && <BangLoi text={err} onRetry={load} />}

      <div className="xlcd__grid">
        {queueOpen && (
          <QueuePopup
            onClose={() => setQueueOpen(false)}
            items={queue}
            canCreate={canCreate}
            canUpdate={canUpdate}
            daVaoKeHoach={daVaoKeHoach}
            onDuaVao={duaVao}
            onAskGo={setAskGo}
          />
        )}

        <section className="xlcd-board" aria-label="Bảng xếp lịch công đoạn">
          <div className="khsx__toolbar">
            <div className="khsx-seg" role="tablist" aria-label="Kiểu xem">
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "bang"}
                className={viewMode === "bang" ? "is-active" : ""}
                onClick={() => setViewMode("bang")}
              >
                <Icon name="columns" size={13} /> Bảng
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "gantt"}
                className={viewMode === "gantt" ? "is-active" : ""}
                onClick={() => setViewMode("gantt")}
              >
                <Icon name="calendar" size={13} /> Gantt
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "van-de"}
                className={viewMode === "van-de" ? "is-active" : ""}
                onClick={() => setViewMode("van-de")}
              >
                <Icon name="shield" size={13} /> Vấn đề
                {chanCount > 0 ? (
                  <span className="xlcd-segbadge xlcd-segbadge--chan">{num(chanCount)}</span>
                ) : tongVanDe > 0 ? (
                  <span className="xlcd-segbadge">{num(tongVanDe)}</span>
                ) : null}
              </button>
            </div>

            {/* Gom-nhóm + 2 chip lọc chỉ có nghĩa với Bảng/Gantt — ẩn ở view Vấn đề. */}
            {viewMode !== "van-de" && (
              <>
                <div className="khsx-seg" role="tablist" aria-label="Gom nhóm theo">
                  {GROUP_TABS.map((g) => (
                    <button
                      key={g.key}
                      type="button"
                      role="tab"
                      aria-selected={groupBy === g.key}
                      className={groupBy === g.key ? "is-active" : ""}
                      onClick={() => setGroupBy(g.key)}
                    >
                      <Icon name={g.icon} size={13} /> {g.label}
                    </button>
                  ))}
                </div>

                <button
                  type="button"
                  className={`xlcd-fchip ${filters.thueNgoai ? "is-on" : ""}`}
                  aria-pressed={filters.thueNgoai}
                  onClick={() => setFilters((f) => ({ ...f, thueNgoai: !f.thueNgoai }))}
                >
                  <Icon name="truck" size={12} /> Thuê ngoài
                </button>
                <button
                  type="button"
                  className={`xlcd-fchip ${filters.chiXungDot ? "is-on" : ""}`}
                  aria-pressed={filters.chiXungDot}
                  onClick={() => setFilters((f) => ({ ...f, chiXungDot: !f.chiXungDot }))}
                >
                  <Icon name="ban" size={12} /> Chỉ xung đột
                </button>
              </>
            )}

            <button
              type="button"
              className={`xlcd-fchip ${isFocusMode ? "is-on" : ""}`}
              onClick={() => setIsFocusMode((v) => !v)}
              title="Mở rộng bàn làm việc"
            >
              <Icon name="maximize" size={12} /> {isFocusMode ? "Thu nhỏ" : "Toàn màn hình"}
            </button>

            <div className="khsx__spacer" />

            <label className="khsx__search">
              <Icon name="search" size={14} />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={viewMode === "van-de" ? "Tìm mã / mô tả vấn đề" : "Tìm mã LSX / bài ghép / công đoạn"}
                aria-label={viewMode === "van-de" ? "Tìm vấn đề" : "Tìm dòng xếp lịch"}
              />
            </label>

            {viewMode !== "van-de" && (
              <div className="xlcd-cols">
                <button
                  type="button"
                  className="xlcd-cols__btn"
                  aria-expanded={colsMenuOpen}
                  onClick={() => setColsMenuOpen((v) => !v)}
                >
                  <Icon name="columns" size={14} /> Cột
                </button>
                {colsMenuOpen && (
                  <ColsMenu
                    hidden={colsHidden}
                    onToggle={(key) =>
                      setColsHidden((prev) => {
                        const next = new Set(prev);
                        next.has(key) ? next.delete(key) : next.add(key);
                        return next;
                      })
                    }
                    onClose={() => setColsMenuOpen(false)}
                  />
                )}
              </div>
            )}
          </div>

          {viewMode === "van-de" ? (
            <VanDeView
              data={vanDe}
              sanSang={sanSang}
              err={vanDeErr}
              onRetry={loadVanDe}
              token={token}
              canApprove={canApprove}
              canApproveException={canApproveException}
              currentUserId={currentUserId}
              q={q}
              mayTen={mayName}
              onRefetch={() => { loadVanDe(); load(); onBadgeStale?.(); }}
              onPhuongAn={onPhuongAn}
              onToast={(text) => setToast({ text })}
              onSetSearch={setQ}
            />
          ) : rows === null ? (
            <BoardSkeleton colCount={colCount} />
          ) : filtered.length === 0 ? (
            coLoc ? (
              <EmptyState
                icon="search"
                title="Không khớp bộ lọc"
                sub="Không có dòng nào khớp nhóm lọc / từ khoá hiện tại."
                action={
                  <Button variant="secondary" onClick={() => { setFilters({ thueNgoai: false, chiXungDot: false }); setQ(""); }}>
                    Xoá lọc
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon="calendar"
                title="Chưa có công đoạn nào cần xếp."
                sub="Đưa một lệnh sản xuất hoặc bài ghép từ khay “Chờ lập kế hoạch” vào kế hoạch để bắt đầu xếp máy và giờ."
              />
            )
          ) : viewMode === "gantt" ? (
            <GanttBoard
              bands={bands}
              groupBy={groupBy}
              token={token}
              canUpdate={canUpdate}
              onOpenRow={setOpenRowId}
              onGan={onGan}
              onToast={(text, undo) => setToast({ text, undo })}
            />
          ) : (
            <div
              ref={wrapRef}
              className={`xlcd-tablewrap ${edge.l ? "is-scroll-l" : ""} ${edge.r ? "is-scroll-r" : ""}`}
              onScroll={recomputeEdge}
            >
              <table className="xlcd-table">
                <caption className="sr-only">Bảng dòng xếp lịch công đoạn gom theo {groupBy}</caption>
                <thead>
                  <tr>
                    <th scope="col" className="xlcd-sticky-l xlcd-sticky-l--1 xlcd-th-chk">
                      <input
                        type="checkbox"
                        aria-label="Chọn tất cả dòng"
                        checked={allPicked}
                        disabled={!canUpdate || pickableIds.length === 0}
                        onChange={togglePickAll}
                      />
                    </th>
                    <th scope="col" className="xlcd-sticky-l xlcd-sticky-l--2" aria-label="Cờ" />
                    <th scope="col" className="xlcd-sticky-l xlcd-sticky-l--3">Mã</th>
                    <th scope="col" className="xlcd-sticky-l xlcd-sticky-l--4 xlcd-shadow-l">Công đoạn</th>
                    <th scope="col" className="khsx-th--num">SL</th>
                    <th scope="col">Thực hiện</th>
                    <th scope="col">Máy / NCC</th>
                    {show.somNhat && <th scope="col" className="khsx-th--num xlcd__col--opt">Sớm nhất</th>}
                    <th scope="col">Bắt đầu</th>
                    {show.ketThuc && <th scope="col" className="khsx-th--num xlcd__col--opt">Kết thúc</th>}
                    {show.thoiLuong && <th scope="col" className="khsx-th--num xlcd__col--opt">Thời lượng</th>}
                    <th scope="col" className="xlcd-sticky-r xlcd-shadow-r">Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {bands.map((b) => {
                    const collapsed = collapsedBands.has(b.key);
                    return (
                      <BandGroup
                        key={b.key}
                        band={b}
                        colCount={colCount}
                        collapsed={collapsed}
                        flash={flashBandKey === b.key}
                        bandRef={(el) => bandElRefs.current.set(b.key, el)}
                        onToggle={() =>
                          setCollapsedBands((prev) => {
                            const next = new Set(prev);
                            next.has(b.key) ? next.delete(b.key) : next.add(b.key);
                            return next;
                          })
                        }
                        onGo={
                          groupBy === "may" || !canUpdate
                            ? undefined
                            : () => {
                                const first = b.rows[0];
                                if (!first) return;
                                const id = first.nguon === "in_ghep" ? first.bai_ghep_id : first.lsx_id;
                                if (id != null)
                                  setAskGo({
                                    nguon: first.nguon, id, ma: b.label, ten: null,
                                    so_cong_doan: b.rows.length, is_rush: false, han_hoan_thanh_sx: null,
                                  });
                              }
                        }
                      >
                        {!collapsed &&
                          b.rows.map((r, stepIdx) => (
                            <BoardRow
                              key={r.id}
                              row={r}
                              stepIdx={stepIdx}
                              groupBy={groupBy}
                              show={show}
                              picked={picked.has(r.id)}
                              canUpdate={canUpdate}
                              mays={mays}
                              phongBans={phongBans}
                              onTogglePick={() => togglePick(r.id)}
                              onOpen={() => setOpenRowId(r.id)}
                              onGan={onGan}
                              fetchGoiY={fetchGoiY}
                            />
                          ))}
                      </BandGroup>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {picked.size > 0 && viewMode !== "van-de" && (
        <BulkBar
          count={picked.size}
          canUpdate={canUpdate}
          mays={mays}
          onGanMay={(id) => bulkGan({ may_id: id }, "Gán máy")}
          onGanCa={(shift) => bulkGan({ work_shift_id: shift }, "Gán ca")}
          onDatGio={(local) => bulkGan({ start_at: fromLocalInput(local) }, "Đặt giờ")}
          onKhoa={() => bulkKhoa(true)}
          onMoKhoa={() => bulkKhoa(false)}
          onAuto={bulkAuto}
          onClear={clearPick}
        />
      )}

      {toast && (
        <div className="xlcd-toast" role="status" aria-live="polite">
          <span>{toast.text}</span>
          {toast.undo && (
            <button type="button" className="xlcd-toast__undo" onClick={toast.undo}>
              Hoàn tác
            </button>
          )}
        </div>
      )}

      {openRow && (
        <DrawerBuoc
          row={openRow}
          siblings={(rows ?? []).filter((r) => r.nguon === "lsx" && r.lsx_id === openRow.lsx_id)}
          mays={mays}
          phongBans={phongBans}
          canUpdate={canUpdate}
          hasPrev={!!goPrev}
          hasNext={!!goNext}
          onPrev={goPrev}
          onNext={goNext}
          onClose={() => setOpenRowId(null)}
          onGan={onGan}
          onKhoa={async (khoa) => {
            if (!token) return;
            try {
              const r = khoa ? await api.xepLich.khoa(token, openRow.id, true) : await api.xepLich.moKhoa(token, openRow.id);
              applyRow(r);
              onBadgeStale?.();
            } catch (e: unknown) {
              setErr(e instanceof ApiError ? e.message : String(e));
            }
          }}
          fetchGoiY={fetchGoiY}
          fetchMembers={async () =>
            token && openRow.bai_ghep_id ? (await api.baiGhep.get(token, openRow.bai_ghep_id)).thanh_vien : []
          }
        />
      )}

      <ConfirmDialog
        open={askGo != null}
        title={askGo ? `Gỡ ${askGo.ma} khỏi kế hoạch?` : ""}
        message="Các dòng lịch của lệnh/bài ghép này sẽ bị xoá và routing mở lại để sửa. Dòng đã khóa phải mở khóa trước."
        confirmLabel="Gỡ kế hoạch"
        danger
        onConfirm={() => askGo && goKeHoach(askGo)}
        onCancel={() => setAskGo(null)}
      />
    </main>
  );
}

// ============================ band ===========================================
export interface Band {
  key: string;
  label: string;
  icon: IconName;
  noMay: boolean;
  rows: XepLichRow[];
}
function bandInfo(r: XepLichRow, gb: GroupBy): Omit<Band, "rows"> {
  if (gb === "may") {
    if (r.may_id == null) return { key: "__nomay", label: "Chưa gán máy", icon: "printer", noMay: true };
    return { key: `may-${r.may_id}`, label: r.may_ten ?? `Máy #${r.may_id}`, icon: "printer", noMay: false };
  }
  if (gb === "bai-ghep") {
    if (r.nguon === "in_ghep") return { key: `bg-${r.bai_ghep_id}`, label: r.lsx_ma ?? "Bài ghép", icon: "layers", noMay: false };
    return { key: `lsx-${r.lsx_id}`, label: r.lsx_ma ?? "—", icon: "clipboard", noMay: false };
  }
  return {
    key: `${r.nguon}-${r.lsx_id ?? r.bai_ghep_id}`,
    label: r.lsx_ma ?? "—",
    icon: r.nguon === "in_ghep" ? "layers" : "clipboard",
    noMay: false,
  };
}
function bandMeta(b: Band): string {
  const tai = b.rows.reduce((s, r) => s + (r.chiem_may_phut || 0), 0);
  const soms = b.rows.map((r) => r.som_nhat).filter((x): x is string => !!x);
  const muons = b.rows.map((r) => r.muon_nhat).filter((x): x is string => !!x);
  const som = soms.length ? ngay(soms.reduce((a, c) => (a < c ? a : c))) : "—";
  const muon = muons.length ? ngay(muons.reduce((a, c) => (a > c ? a : c))) : "—";
  return `${b.rows.length} công đoạn · tải ${thoiLuong(tai)} · ${som}–${muon}`;
}

function BandGroup({
  band, colCount, collapsed, flash, bandRef, onToggle, onGo, children,
}: {
  band: Band;
  colCount: number;
  collapsed: boolean;
  flash: boolean;
  bandRef: (el: HTMLTableRowElement | null) => void;
  onToggle: () => void;
  onGo?: () => void;
  children: ReactNode;
}) {
  const totalSteps = band.rows.length;
  const scheduledSteps = band.rows.filter((r) => r.start_at != null || r.trang_thai === "da_xep").length;
  const pct = totalSteps > 0 ? Math.round((scheduledSteps / totalSteps) * 100) : 0;

  return (
    <>
      <tr
        ref={bandRef}
        className={`xlcd-band ${band.noMay ? "xlcd-band--nomay" : ""} ${flash ? "is-flash" : ""}`}
      >
        <td colSpan={colCount}>
          <div className="xlcd-band__inner">
            <button
              type="button"
              className="xlcd-band__toggle"
              aria-expanded={!collapsed}
              onClick={onToggle}
            >
              <Icon name="chevron" size={15} className={collapsed ? "xlcd-band__caret is-collapsed" : "xlcd-band__caret"} />
              <Icon name={band.icon} size={15} />
              <span className="xlcd-band__title">{band.label}</span>
            </button>
            <span className="xlcd-band__meta">{bandMeta(band)}</span>

            <div className="xlcd-band__progress-wrap" title={`${scheduledSteps}/${totalSteps} công đoạn đã xếp (${pct}%)`}>
              <div className="xlcd-band__progress">
                <div
                  className={`xlcd-band__progress-bar ${pct === 100 ? "xlcd-band__progress-bar--complete" : ""}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="xlcd-band__progress-num">{scheduledSteps}/{totalSteps} đã xếp</span>
            </div>

            {onGo && (
              <button type="button" className="xlcd-band__go" onClick={onGo}>
                <Icon name="lockOpen" size={12} /> Gỡ kế hoạch
              </button>
            )}
          </div>
        </td>
      </tr>
      {children}
    </>
  );
}

// ============================ 1 dòng bảng ====================================
interface ShowCols { somNhat: boolean; ketThuc: boolean; thoiLuong: boolean }

function BoardRow({
  row, stepIdx, groupBy, show, picked, canUpdate, mays, phongBans, onTogglePick, onOpen, onGan, fetchGoiY,
}: {
  row: XepLichRow;
  stepIdx?: number;
  groupBy?: GroupBy;
  show: ShowCols;
  picked: boolean;
  canUpdate: boolean;
  mays: Row[];
  phongBans: Row[];
  onTogglePick: () => void;
  onOpen: () => void;
  onGan: (id: number, body: XepLichGanBody) => void;
  fetchGoiY: (id: number) => Promise<XepLichGoiY>;
}) {
  const blocked = !!row.blocked_reason;
  const editable = canUpdate && !row.is_locked && !blocked;
  const meta = row.loai_buoc ? LSX_LOAI_BUOC_META[row.loai_buoc] : undefined;
  const soomTre = !!row.start_at && !!row.som_nhat && row.start_at < row.som_nhat;
  const isGhep = row.nguon === "in_ghep";
  const isGroupedByOrder = groupBy === "lenh" || groupBy === "bai-ghep";

  return (
    <tr
      className={`xlcd-row ${row.is_rush ? "xlcd-row--rush" : ""} ${picked ? "is-checked" : ""} ${blocked ? "xlcd-row--blocked" : ""} ${isGhep ? "xlcd-row--ghep" : ""}`}
      tabIndex={0}
      aria-label={`Mở công đoạn ${row.cong_doan_ten ?? ""} của ${row.lsx_ma ?? ""}`}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter") { e.preventDefault(); onOpen(); }
      }}
    >
      {/* 1 · chọn */}
      <td className="xlcd-sticky-l xlcd-sticky-l--1 xlcd-td-chk" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          aria-label={`Chọn ${row.lsx_ma ?? ""} · ${row.cong_doan_ten ?? ""}`}
          checked={picked}
          disabled={blocked || !canUpdate}
          onChange={onTogglePick}
        />
      </td>
      {/* 2 · cờ */}
      <td className="xlcd-sticky-l xlcd-sticky-l--2 xlcd-td-flag">
        {row.is_rush && <Icon name="bell" size={13} className="xlcd-flag-rush" />}
        {row.is_locked && <Icon name="lock" size={12} className="xlcd-flag-lock" />}
      </td>
      {/* 3 · mã */}
      <td className="xlcd-sticky-l xlcd-sticky-l--3">
        {isGroupedByOrder && stepIdx != null ? (
          <span className="xlcd-step-badge" title={`Bước ${stepIdx + 1} của ${row.lsx_ma ?? ""}`}>
            CĐ {String(stepIdx + 1).padStart(2, "0")}
          </span>
        ) : (
          <span className="xlcd-ma">
            {isGhep && <Icon name="layers" size={12} />}
            {row.lsx_ma ?? "—"}
          </span>
        )}
        {isGhep && !isGroupedByOrder && <span className="khsx__sub">bài in ghép</span>}
      </td>
      {/* 4 · công đoạn */}
      <td className="xlcd-sticky-l xlcd-sticky-l--4 xlcd-shadow-l">
        <div className="xlcd-cd-cell">
          <Icon name={stepIcon(row.loai_buoc, row.cong_doan_ten)} size={13} className="xlcd-cd-icon" />
          <span className="xlcd-cd">{row.cong_doan_ten ?? "—"}</span>
        </div>
      </td>
      {/* 5 · SL */}
      <td className="khsx-num">
        {row.so_luong_vao == null ? "—" : (
          <>{num(row.so_luong_vao)} <span className="khsx-unit">{row.don_vi_vao}</span></>
        )}
      </td>
      {/* 6 · thực hiện */}
      <td>
        <div className="xlcd-dept-tag" title={row.department_ten ?? meta?.label}>
          {meta && <span className={`khsx-lb khsx-lb--${meta.tone}`}>{meta.label}</span>}
          {row.department_ten && <span>{row.department_ten}</span>}
        </div>
      </td>
      {/* 7 · máy / NCC (inline) */}
      <td onClick={(e) => e.stopPropagation()}>
        <ResCell row={row} editable={editable} mays={mays} phongBans={phongBans} onGan={onGan} fetchGoiY={fetchGoiY} />
      </td>
      {/* 8 · sớm nhất */}
      {show.somNhat && (
        <td className={`khsx-num xlcd__col--opt ${soomTre ? "xlcd-early" : ""}`} title={soomTre ? "Bắt đầu sớm hơn mốc sớm-nhất" : undefined}>
          {ngayGio(row.som_nhat)}
        </td>
      )}
      {/* 9 · bắt đầu (inline) */}
      <td onClick={(e) => e.stopPropagation()}>
        <StartCell row={row} editable={editable} onGan={onGan} fetchGoiY={fetchGoiY} />
      </td>
      {/* 10 · kết thúc */}
      {show.ketThuc && <td className="khsx-num xlcd__col--opt">{ngayGio(row.finish_at)}</td>}
      {/* 11 · thời lượng */}
      {show.thoiLuong && (
        <td className="khsx-num xlcd__col--opt khsx-dur">
          {thoiLuong(row.chiem_may_phut)}
          {row.tong_phut > row.chiem_may_phut && (
            <div className="khsx__sub">dẫn {thoiLuong(row.tong_phut)}</div>
          )}
        </td>
      )}
      {/* 12 · trạng thái */}
      <td className="xlcd-sticky-r xlcd-shadow-r">
        <div className="xlcd-tt">
          <LichTrangThaiPill trangThai={row.trang_thai} isLocked={row.is_locked} coXungDot={row.co_xung_dot} />
          <NguyCoTreChip nhan={row.nhan_rui_ro} slackNgay={row.slack_ngay} />
          {row.can_xac_nhan && (
            <span
              className="xlcd-xnchip"
              title={row.ly_do_xac_nhan.map((l) => XEP_LICH_XAC_NHAN_LABELS[l] ?? l).join("\n")}
            >
              <Icon name="ban" size={11} /> Cần xác nhận
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

// ============================ ô inline: máy / NCC ============================
function ResCell({
  row, editable, mays, phongBans, onGan, fetchGoiY,
}: {
  row: XepLichRow;
  editable: boolean;
  mays: Row[];
  phongBans: Row[];
  onGan: (id: number, body: XepLichGanBody) => void;
  fetchGoiY: (id: number) => Promise<XepLichGoiY>;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const kind = resKind(row.loai_buoc);
  const txt = resText(row);
  useDismiss(open, () => setOpen(false));

  if (kind === "none") return <span className="khsx-muted">—</span>;

  const placeholder = kind === "ncc" ? "Chọn nhà gia công…" : kind === "to" ? "Chọn tổ…" : "Chọn máy…";

  return (
    <div className="xlcd-cellwrap" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={`xlcd-cell ${txt ? "" : "xlcd-cell--empty"}`}
        disabled={!editable}
        onClick={(e) => { setAnchor(e.currentTarget.getBoundingClientRect()); setOpen((v) => !v); }}
      >
        {txt ?? placeholder}
      </button>
      {open && anchor && (
        <div className="xlcd-pop" style={popStyle(anchor)} onClick={(e) => e.stopPropagation()}>
          {kind === "ncc" ? (
            <NccInput
              value={row.nha_cung_cap ?? ""}
              onSave={(v) => { onGan(row.id, { nha_cung_cap: v || null }); setOpen(false); }}
            />
          ) : (
            <RefPick
              options={kind === "to" ? phongBans : mays}
              placeholder={placeholder}
              header={
                kind === "may" && row.may_id != null ? (
                  <button
                    type="button"
                    className="xlcd-pick__suggest"
                    onClick={async () => {
                      const g = await fetchGoiY(row.id);
                      if (g.khe_trong) onGan(row.id, { start_at: g.khe_trong });
                      setOpen(false);
                    }}
                  >
                    <Icon name="clock" size={12} /> Máy trống sớm nhất
                  </button>
                ) : null
              }
              onPick={(id) => {
                onGan(row.id, kind === "to" ? { department_id: id } : { may_id: id });
                setOpen(false);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ============================ ô inline: ca + bắt đầu ========================
function StartCell({
  row, editable, onGan, fetchGoiY,
}: {
  row: XepLichRow;
  editable: boolean;
  onGan: (id: number, body: XepLichGanBody) => void;
  fetchGoiY: (id: number) => Promise<XepLichGoiY>;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [dt, setDt] = useState(toLocalInput(row.start_at));
  const [ca, setCa] = useState<number | null>(row.work_shift_id ?? null);
  useDismiss(open, () => setOpen(false));

  useEffect(() => {
    if (open) { setDt(toLocalInput(row.start_at)); setCa(row.work_shift_id ?? null); }
  }, [open, row.start_at, row.work_shift_id]);

  const caTxt = caLabel(row.work_shift_id);

  return (
    <div className="xlcd-cellwrap" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={`xlcd-cell ${row.start_at ? "" : "xlcd-cell--empty"}`}
        disabled={!editable}
        onClick={(e) => { setAnchor(e.currentTarget.getBoundingClientRect()); setOpen((v) => !v); }}
      >
        {row.start_at ? ngayGio(row.start_at) : "Đặt giờ…"}
        {caTxt && <span className="xlcd-cell__sub">{caTxt}</span>}
      </button>
      {open && anchor && (
        <div className="xlcd-pop xlcd-pop--time" style={popStyle(anchor, 300)} onClick={(e) => e.stopPropagation()}>
          <p className="xlcd-pop__label">Ca làm</p>
          <div className="khsx-seg khsx-seg--sm">
            {CA_OPTIONS.map((c) => (
              <button
                key={c.id}
                type="button"
                className={ca === c.id ? "is-active" : ""}
                onClick={() => setCa(ca === c.id ? null : c.id)}
              >
                {c.label}
              </button>
            ))}
          </div>

          <p className="xlcd-pop__label">Bắt đầu</p>
          <input
            type="datetime-local"
            className="xlcd-pop__dt"
            value={dt}
            onChange={(e) => setDt(e.target.value)}
          />
          <div className="xlcd-pop__quick">
            {row.som_nhat && (
              <button type="button" onClick={() => setDt(toLocalInput(row.som_nhat))}>Sớm nhất</button>
            )}
            <button type="button" onClick={() => setDt(nextShiftStart(dt))}>Đầu ca kế</button>
            {row.may_id != null && (
              <button
                type="button"
                onClick={async () => { const g = await fetchGoiY(row.id); if (g.khe_trong) setDt(toLocalInput(g.khe_trong)); }}
              >
                Máy trống sớm nhất
              </button>
            )}
          </div>

          <p className="xlcd-pop__derive">
            Kết thúc {ngayGio(row.finish_at)} · chiếm máy {thoiLuong(row.chiem_may_phut)}
            <span className="xlcd-pop__derive-note"> (cập nhật sau khi lưu)</span>
          </p>

          <div className="xlcd-pop__foot">
            <button type="button" className="xlcd-pop__cancel" onClick={() => setOpen(false)}>Hủy</button>
            <Button
              variant="primary"
              onClick={() => { onGan(row.id, { start_at: fromLocalInput(dt), work_shift_id: ca }); setOpen(false); }}
            >
              Lưu
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================ typeahead danh mục ============================
function RefPick({
  options, placeholder, header, onPick,
}: {
  options: Row[];
  placeholder: string;
  header?: ReactNode;
  onPick: (id: number) => void;
}) {
  const [q, setQ] = useState("");
  const nq = norm(q.trim());
  const matches = (nq ? options.filter((o) => norm(`${o.ma} ${o.ten}`).includes(nq)) : options).slice(0, 30);
  return (
    <div className="xlcd-pick">
      <input
        className="xlcd-pick__input"
        autoFocus
        value={q}
        placeholder={placeholder}
        onChange={(e) => setQ(e.target.value)}
      />
      {header}
      <div className="xlcd-pick__list">
        {matches.map((o) => (
          <button
            key={o.id}
            type="button"
            className="xlcd-pick__opt"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onPick(o.id)}
          >
            <b>{o.ma}</b> · {o.ten}
          </button>
        ))}
        {nq && matches.length === 0 && <p className="xlcd-pick__empty">Không thấy “{q}”.</p>}
      </div>
    </div>
  );
}

function NccInput({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [v, setV] = useState(value);
  return (
    <div className="xlcd-ncc">
      <input
        className="xlcd-pick__input"
        autoFocus
        value={v}
        placeholder="Tên nhà gia công"
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") onSave(v.trim()); }}
      />
      <Button variant="primary" onClick={() => onSave(v.trim())}>Lưu</Button>
    </div>
  );
}

// ============================ menu cột ======================================
function ColsMenu({
  hidden, onToggle, onClose,
}: {
  hidden: Set<string>;
  onToggle: (key: string) => void;
  onClose: () => void;
}) {
  useDismiss(true, onClose);
  return (
    <div className="xlcd-colsmenu" onClick={(e) => e.stopPropagation()} role="menu">
      <p className="xlcd-colsmenu__head">Hiện cột phụ</p>
      {COL_GROUPS.map((c) => (
        <label key={c.key} className="xlcd-colsmenu__row">
          <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => onToggle(c.key)} />
          <span>{c.label}</span>
        </label>
      ))}
    </div>
  );
}

// ============================ popup "Chờ lập kế hoạch" =======================
// Dùng primitive DetailModal (overlay + Esc + bấm ra ngoài + nút ×) thay vì tự dựng lớp phủ:
// khay trượt-từ-trái cũ khi đóng vẫn nằm đè mép trái board nên để lộ vệt trắng dọc cạnh sidebar,
// và lớp phủ riêng của nó không phủ hết padding trang.
function QueuePopup({
  onClose, items, canCreate, canUpdate, daVaoKeHoach, onDuaVao, onAskGo,
}: {
  onClose: () => void;
  items: XepLichHangChoItem[] | null;
  canCreate: boolean;
  canUpdate: boolean;
  daVaoKeHoach: Set<string>;
  onDuaVao: (item: XepLichHangChoItem) => void;
  onAskGo: (item: XepLichHangChoItem) => void;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMode, setFilterMode] = useState<"all" | "rush" | "ghep" | "lsx">("all");
  const [viewMode, setViewMode] = useState<"table" | "card">("table");
  const [sortBy, setSortBy] = useState<"rush" | "deadline" | "ma" | "steps">("rush");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  const total = items?.length ?? 0;
  const rushCount = useMemo(() => items?.filter((i) => i.is_rush).length ?? 0, [items]);

  const filteredItems = useMemo(() => {
    if (!items) return null;
    let result = items.filter((it) => {
      if (filterMode === "rush" && !it.is_rush) return false;
      if (filterMode === "ghep" && it.nguon !== "in_ghep") return false;
      if (filterMode === "lsx" && it.nguon !== "lsx") return false;

      if (searchQuery.trim() !== "") {
        const q = searchQuery.toLowerCase().trim();
        const matchMa = it.ma.toLowerCase().includes(q);
        const matchTen = (it.ten || "").toLowerCase().includes(q);
        if (!matchMa && !matchTen) return false;
      }

      return true;
    });

    // Sắp xếp
    result = [...result].sort((a, b) => {
      if (sortBy === "rush") {
        if (a.is_rush !== b.is_rush) return a.is_rush ? -1 : 1;
      } else if (sortBy === "deadline") {
        if (a.han_hoan_thanh_sx && b.han_hoan_thanh_sx) {
          return a.han_hoan_thanh_sx.localeCompare(b.han_hoan_thanh_sx);
        }
        if (a.han_hoan_thanh_sx) return -1;
        if (b.han_hoan_thanh_sx) return 1;
      } else if (sortBy === "ma") {
        return a.ma.localeCompare(b.ma);
      } else if (sortBy === "steps") {
        return (b.so_cong_doan || 0) - (a.so_cong_doan || 0);
      }
      return 0;
    });

    return result;
  }, [items, filterMode, searchQuery, sortBy]);

  // Các lệnh khả dụng để chọn (chưa đưa vào kế hoạch)
  const selectableItems = useMemo(() => {
    if (!filteredItems) return [];
    return filteredItems.filter((it) => !daVaoKeHoach.has(`${it.nguon}-${it.id}`));
  }, [filteredItems, daVaoKeHoach]);

  const isAllSelected = useMemo(() => {
    if (selectableItems.length === 0) return false;
    return selectableItems.every((it) => selectedKeys.has(`${it.nguon}-${it.id}`));
  }, [selectableItems, selectedKeys]);

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedKeys(new Set());
    } else {
      const next = new Set<string>();
      selectableItems.forEach((it) => next.add(`${it.nguon}-${it.id}`));
      setSelectedKeys(next);
    }
  };

  const toggleSelectItem = (itemKey: string) => {
    const next = new Set(selectedKeys);
    if (next.has(itemKey)) next.delete(itemKey);
    else next.add(itemKey);
    setSelectedKeys(next);
  };

  const handleBatchSchedule = () => {
    if (!filteredItems) return;
    filteredItems.forEach((it) => {
      const key = `${it.nguon}-${it.id}`;
      if (selectedKeys.has(key) && !daVaoKeHoach.has(key)) {
        onDuaVao(it);
      }
    });
    setSelectedKeys(new Set());
  };

  return (
    <DetailModal
      kicker="XẾP LỊCH"
      title="Chờ lập kế hoạch"
      subtitle={
        items === null
          ? "Đang tải danh sách hàng chờ…"
          : total === 0
            ? "Không còn lệnh / bài ghép nào chờ."
            : `${num(total)} lệnh / bài ghép sẵn sàng ${rushCount > 0 ? `(${rushCount} lệnh GẤP)` : ""}`
      }
      onClose={onClose}
    >
      <div className="xlcd-queue__container">
        {/* HEADER CONTROLS: STATS + VIEW TOGGLE & SORTING */}
        {items && items.length > 0 && (
          <div className="xlcd-queue__insights">
            <div className="xlcd-queue__stat-chip">
              <Icon name="layers" size={12} />
              <span>Sẵn sàng: <strong>{total}</strong></span>
            </div>
            {rushCount > 0 && (
              <div className="xlcd-queue__stat-chip xlcd-queue__stat-chip--rush">
                <span>GẤP: <strong>{rushCount}</strong></span>
              </div>
            )}

            <div className="xlcd-queue__controls-right">
              {/* SORT DROPDOWN */}
              <select
                className="xlcd-queue__sort-select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                title="Sắp xếp danh sách"
              >
                <option value="rush">Ưu tiên GẤP</option>
                <option value="deadline">Hạn SX gần nhất</option>
                <option value="ma">Mã (A-Z)</option>
                <option value="steps">Số công đoạn</option>
              </select>

              {/* VIEW SWITCHER */}
              <div className="xlcd-queue__mode-switch">
                <button
                  type="button"
                  className={`xlcd-queue__mode-btn ${viewMode === "table" ? "is-active" : ""}`}
                  onClick={() => setViewMode("table")}
                  title="Dạng Bảng nén (Phù hợp 20+ lệnh)"
                >
                  <Icon name="table" size={13} /> Bảng nén
                </button>
                <button
                  type="button"
                  className={`xlcd-queue__mode-btn ${viewMode === "card" ? "is-active" : ""}`}
                  onClick={() => setViewMode("card")}
                  title="Dạng Thẻ Visual"
                >
                  <Icon name="grid" size={13} /> Thẻ
                </button>
              </div>
            </div>
          </div>
        )}

        {/* IN-MODAL SEARCH & FILTER TOOLBAR */}
        {items && items.length > 0 && (
          <div className="xlcd-queue__toolbar">
            <div className="xlcd-queue__search-box">
              <Icon name="search" size={14} className="xlcd-queue__search-icon" />
              <input
                type="text"
                className="xlcd-queue__search-input"
                placeholder="Tìm theo mã LSX, bài ghép, tên đơn hàng..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="xlcd-queue__search-clear"
                  onClick={() => setSearchQuery("")}
                >
                  ×
                </button>
              )}
            </div>

            <div className="xlcd-queue__filter-pills">
              <button
                type="button"
                className={`xlcd-queue__pill ${filterMode === "all" ? "is-active" : ""}`}
                onClick={() => setFilterMode("all")}
              >
                Tất cả ({total})
              </button>
              {rushCount > 0 && (
                <button
                  type="button"
                  className={`xlcd-queue__pill xlcd-queue__pill--rush ${filterMode === "rush" ? "is-active" : ""}`}
                  onClick={() => setFilterMode("rush")}
                >
                  Chỉ GẤP ({rushCount})
                </button>
              )}
              <button
                type="button"
                className={`xlcd-queue__pill ${filterMode === "lsx" ? "is-active" : ""}`}
                onClick={() => setFilterMode("lsx")}
              >
                Lệnh sản xuất
              </button>
              <button
                type="button"
                className={`xlcd-queue__pill ${filterMode === "ghep" ? "is-active" : ""}`}
                onClick={() => setFilterMode("ghep")}
              >
                Bài ghép
              </button>
            </div>
          </div>
        )}

        {/* DẠNG BẢNG NÉN (COMPACT TABLE VIEW - TỐI ƯU CHO 20+ LSX) */}
        {viewMode === "table" ? (
          <div className="xlcd-queue__table-wrap">
            {items === null ? (
              <QueueSkeleton />
            ) : filteredItems && filteredItems.length === 0 ? (
              <div className="xlcd-queue__empty-box">
                <Icon name="search" size={24} />
                <p className="xlcd-queue__empty">Không tìm thấy lệnh / bài ghép phù hợp.</p>
              </div>
            ) : (
              <table className="xlcd-queue__table">
                <thead>
                  <tr>
                    {canCreate && (
                      <th style={{ width: 36, textAlign: "center" }}>
                        <input
                          type="checkbox"
                          className="xlcd-queue__chk"
                          checked={isAllSelected}
                          onChange={toggleSelectAll}
                          title="Chọn tất cả các lệnh chưa xếp"
                        />
                      </th>
                    )}
                    <th style={{ width: 90 }}>Loại</th>
                    <th style={{ width: 130 }}>Mã Lệnh</th>
                    <th>Tên sản phẩm / Đơn hàng</th>
                    <th style={{ width: 100 }}>Công đoạn</th>
                    <th style={{ width: 110 }}>Hạn SX</th>
                    <th style={{ width: 130, textAlign: "right" }}>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems?.map((it) => {
                    const itemKey = `${it.nguon}-${it.id}`;
                    const inPlan = daVaoKeHoach.has(itemKey);
                    const isGhep = it.nguon === "in_ghep";
                    const isSelected = selectedKeys.has(itemKey);

                    return (
                      <tr
                        key={itemKey}
                        className={`${isSelected ? "is-selected" : ""} ${inPlan ? "is-inplan" : ""}`}
                      >
                        {canCreate && (
                          <td style={{ textAlign: "center" }}>
                            {!inPlan && (
                              <input
                                type="checkbox"
                                className="xlcd-queue__chk"
                                checked={isSelected}
                                onChange={() => toggleSelectItem(itemKey)}
                              />
                            )}
                          </td>
                        )}
                        <td>
                          <span className={`xlcd-queue__source-tag ${isGhep ? "xlcd-queue__source-tag--ghep" : ""}`}>
                            {isGhep ? "Bài ghép" : "Lệnh SX"}
                          </span>
                        </td>
                        <td>
                          <span className="xlcd-queue__ma">{it.ma}</span>
                          {it.is_rush && (
                            <span className="xlcd-queue__rush-badge" style={{ marginLeft: 4 }}>GẤP</span>
                          )}
                        </td>
                        <td title={it.ten}>
                          <strong style={{ fontWeight: 600, color: "#1e293b" }}>{it.ten || "—"}</strong>
                        </td>
                        <td>
                          <span className="xlcd-queue__stage-chip">
                            {it.so_cong_doan} {isGhep ? "lệnh" : "bước"}
                          </span>
                        </td>
                        <td>
                          {it.han_hoan_thanh_sx ? (
                            <span className={`xlcd-queue__han ${classHan(it.han_hoan_thanh_sx)}`}>
                              {ngay(it.han_hoan_thanh_sx)}
                            </span>
                          ) : "—"}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          {inPlan ? (
                            <span className="xlcd-queue__inplan-tag" style={{ fontSize: 11 }}>
                              <Icon name="check" size={11} /> Đã vào KH
                              {canUpdate && (
                                <button
                                  type="button"
                                  className="xlcd-queue__go"
                                  style={{ marginLeft: 6 }}
                                  onClick={() => onAskGo(it)}
                                >
                                  Gỡ
                                </button>
                              )}
                            </span>
                          ) : (
                            canCreate && (
                              <button
                                type="button"
                                className="xlcd-queue__tbl-btn"
                                onClick={() => onDuaVao(it)}
                              >
                                + Đưa vào
                              </button>
                            )
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        ) : (
          /* DẠNG THẺ (CARD VIEW) */
          <div className="xlcd-queue__list">
            {items === null ? (
              <QueueSkeleton />
            ) : filteredItems && filteredItems.length === 0 ? (
              <div className="xlcd-queue__empty-box">
                <Icon name="search" size={24} />
                <p className="xlcd-queue__empty">Không tìm thấy lệnh / bài ghép phù hợp.</p>
              </div>
            ) : (
              filteredItems?.map((it) => {
                const itemKey = `${it.nguon}-${it.id}`;
                const inPlan = daVaoKeHoach.has(itemKey);
                const isGhep = it.nguon === "in_ghep";
                const isSelected = selectedKeys.has(itemKey);
                return (
                  <div
                    key={itemKey}
                    className={`xlcd-queue__item ${it.is_rush ? "xlcd-queue__item--rush" : ""} ${inPlan ? "xlcd-queue__item--inplan" : ""}`}
                    role={canCreate && !inPlan ? "button" : undefined}
                    tabIndex={canCreate && !inPlan ? 0 : undefined}
                    aria-label={`Đưa ${it.ma} vào kế hoạch`}
                    onClick={canCreate && !inPlan ? () => onDuaVao(it) : undefined}
                    onKeyDown={(e) => {
                      if (canCreate && !inPlan && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onDuaVao(it); }
                    }}
                  >
                    {/* CARD HEADER */}
                    <div className="xlcd-queue__itemhead">
                      {canCreate && !inPlan && (
                        <input
                          type="checkbox"
                          className="xlcd-queue__chk"
                          checked={isSelected}
                          onClick={(e) => e.stopPropagation()}
                          onChange={() => toggleSelectItem(itemKey)}
                        />
                      )}
                      <span className={`xlcd-queue__source-tag ${isGhep ? "xlcd-queue__source-tag--ghep" : ""}`}>
                        {isGhep ? "Bài ghép" : "Lệnh SX"}
                      </span>

                      <span className="xlcd-queue__ma">
                        {it.ma}
                      </span>

                      {it.is_rush && (
                        <span className="xlcd-queue__rush-badge" title="Đơn hàng gấp cần ưu tiên">
                          GẤP
                        </span>
                      )}
                    </div>

                    {/* ORDER TITLE */}
                    {it.ten && <p className="xlcd-queue__name" title={it.ten}>{it.ten}</p>}

                    {/* METADATA CHIPS */}
                    <div className="xlcd-queue__meta">
                      <span className="xlcd-queue__stage-chip">
                        <Icon name="layers" size={11} />
                        {it.so_cong_doan} {isGhep ? "lệnh" : "công đoạn"}
                      </span>

                      {it.han_hoan_thanh_sx && (
                        <span className={`xlcd-queue__han ${classHan(it.han_hoan_thanh_sx)}`}>
                          <Icon name="clock" size={11} />
                          Hạn {ngay(it.han_hoan_thanh_sx)}
                        </span>
                      )}
                    </div>

                    {/* CTA ACTION BUTTON / IN-PLAN STATE */}
                    {inPlan ? (
                      <div className="xlcd-queue__inplan">
                        <span className="xlcd-queue__inplan-tag">
                          <Icon name="check" size={12} /> Đã đưa vào kế hoạch
                        </span>
                        {canUpdate && (
                          <button
                            type="button"
                            className="xlcd-queue__go"
                            onClick={(e) => { e.stopPropagation(); onAskGo(it); }}
                            title="Gỡ khỏi kế hoạch"
                          >
                            Gỡ
                          </button>
                        )}
                      </div>
                    ) : (
                      canCreate && (
                        <div className="xlcd-queue__action-row">
                          <button type="button" className="xlcd-queue__btn-cta">
                            <span>+ Đưa vào kế hoạch</span>
                            <Icon name="chevron" size={12} />
                          </button>
                        </div>
                      )
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* FLOATING BATCH ACTION BAR WHEN ITEMS ARE CHECKED */}
        {selectedKeys.size > 0 && canCreate && (
          <div className="xlcd-queue__batch-bar">
            <div className="xlcd-queue__batch-count">
              Đã chọn <strong>{selectedKeys.size}</strong> lệnh sản xuất / bài ghép
            </div>
            <button
              type="button"
              className="xlcd-queue__btn-add-batch"
              onClick={handleBatchSchedule}
            >
              + Đưa {selectedKeys.size} lệnh vào kế hoạch
            </button>
          </div>
        )}
      </div>
    </DetailModal>
  );
}

// ============================ bulk-bar ======================================
function BulkBar({
  count, canUpdate, mays, onGanMay, onGanCa, onDatGio, onKhoa, onMoKhoa, onAuto, onClear,
}: {
  count: number;
  canUpdate: boolean;
  mays: Row[];
  onGanMay: (id: number) => void;
  onGanCa: (shift: number) => void;
  onDatGio: (local: string) => void;
  onKhoa: () => void;
  onMoKhoa: () => void;
  onAuto: () => void;
  onClear: () => void;
}) {
  const [pop, setPop] = useState<"may" | "ca" | "gio" | null>(null);
  const [dt, setDt] = useState("");
  useDismiss(pop != null, () => setPop(null));

  return (
    <div className="xlcd-bulk" role="region" aria-label={`${count} dòng đang chọn`}>
      <span className="xlcd-bulk__count">{count} đã chọn</span>

      {canUpdate && (
        <>
          <div className="xlcd-bulk__wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="xlcd-bulk__btn" onClick={() => setPop(pop === "may" ? null : "may")}>
              <Icon name="printer" size={13} /> Gán máy <Icon name="chevron" size={12} />
            </button>
            {pop === "may" && (
              <div className="xlcd-pop xlcd-pop--up" onClick={(e) => e.stopPropagation()}>
                <RefPick options={mays} placeholder="Chọn máy cho các dòng…" onPick={(id) => { onGanMay(id); setPop(null); }} />
              </div>
            )}
          </div>

          <div className="xlcd-bulk__wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="xlcd-bulk__btn" onClick={() => setPop(pop === "ca" ? null : "ca")}>
              Gán ca <Icon name="chevron" size={12} />
            </button>
            {pop === "ca" && (
              <div className="xlcd-pop xlcd-pop--up" onClick={(e) => e.stopPropagation()}>
                <div className="khsx-seg khsx-seg--sm">
                  {CA_OPTIONS.map((c) => (
                    <button key={c.id} type="button" onClick={() => { onGanCa(c.id); setPop(null); }}>{c.label}</button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="xlcd-bulk__wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="xlcd-bulk__btn" onClick={() => setPop(pop === "gio" ? null : "gio")}>
              <Icon name="clock" size={13} /> Đặt giờ <Icon name="chevron" size={12} />
            </button>
            {pop === "gio" && (
              <div className="xlcd-pop xlcd-pop--up" onClick={(e) => e.stopPropagation()}>
                <input type="datetime-local" className="xlcd-pop__dt" value={dt} onChange={(e) => setDt(e.target.value)} />
                <div className="xlcd-pop__foot">
                  <button type="button" className="xlcd-pop__cancel" onClick={() => setPop(null)}>Hủy</button>
                  <Button variant="primary" disabled={!dt} onClick={() => { onDatGio(dt); setPop(null); }}>Đặt</Button>
                </div>
              </div>
            )}
          </div>

          <button type="button" className="xlcd-bulk__btn" onClick={onKhoa}><Icon name="lock" size={13} /> Khóa</button>
          <button type="button" className="xlcd-bulk__btn" onClick={onMoKhoa}><Icon name="lockOpen" size={13} /> Gỡ khóa</button>
          <span className="xlcd-bulk__sep" />
          <button type="button" className="xlcd-bulk__btn xlcd-bulk__btn--accent" onClick={onAuto}>
            <Icon name="clock" size={13} /> Tự xếp: máy trống sớm nhất
          </button>
        </>
      )}

      <button type="button" className="xlcd-bulk__clear" onClick={onClear}>Bỏ chọn</button>
    </div>
  );
}

// ============================ drawer 1 công đoạn ============================
function DrawerBuoc({
  row, siblings, mays, phongBans, canUpdate, hasPrev, hasNext, onPrev, onNext, onClose, onGan, onKhoa, fetchGoiY, fetchMembers,
}: {
  row: XepLichRow;
  siblings: XepLichRow[];
  mays: Row[];
  phongBans: Row[];
  canUpdate: boolean;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev?: () => void;
  onNext?: () => void;
  onClose: () => void;
  onGan: (id: number, body: XepLichGanBody) => void;
  onKhoa: (khoa: boolean) => void;
  fetchGoiY: (id: number) => Promise<XepLichGoiY>;
  fetchMembers: () => Promise<{ lsx_id: number; lsx_ma: string | null; lsx_ten: string | null }[]>;
}) {
  const kind = resKind(row.loai_buoc);
  const [mayId, setMayId] = useState<number | null>(row.may_id);
  const [deptId, setDeptId] = useState<number | null>(row.department_id);
  const [ncc, setNcc] = useState(row.nha_cung_cap ?? "");
  const [ca, setCa] = useState<number | null>(row.work_shift_id ?? null);
  const [dt, setDt] = useState(toLocalInput(row.start_at));
  const [goiY, setGoiY] = useState<XepLichGoiY | null>(null);
  const [members, setMembers] = useState<{ lsx_id: number; lsx_ma: string | null; lsx_ten: string | null }[] | null>(null);

  useEffect(() => {
    setMayId(row.may_id); setDeptId(row.department_id); setNcc(row.nha_cung_cap ?? "");
    setCa(row.work_shift_id ?? null); setDt(toLocalInput(row.start_at)); setGoiY(null);
  }, [row.id, row.may_id, row.department_id, row.nha_cung_cap, row.work_shift_id, row.start_at]);

  useEffect(() => { fetchGoiY(row.id).then(setGoiY).catch(() => setGoiY(null)); }, [row.id, fetchGoiY]);
  useEffect(() => {
    if (row.nguon === "in_ghep") fetchMembers().then(setMembers).catch(() => setMembers([]));
    else setMembers(null);
  }, [row.id, row.nguon, fetchMembers]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const steps = [...siblings].sort((a, b) => (a.som_nhat ?? "").localeCompare(b.som_nhat ?? ""));
  const activeIndex = steps.findIndex((s) => s.id === row.id);
  const blocked = !!row.blocked_reason;
  const readOnly = !canUpdate || row.is_locked;

  const luu = () => {
    const body: XepLichGanBody = { work_shift_id: ca, start_at: fromLocalInput(dt) };
    if (kind === "may") body.may_id = mayId;
    else if (kind === "to") body.department_id = deptId;
    else if (kind === "ncc") body.nha_cung_cap = ncc.trim() || null;
    onGan(row.id, body);
    onClose();
  };

  const mayTen = mays.find((m) => m.id === mayId)?.ten ?? row.may_ten;
  const deptTen = phongBans.find((d) => d.id === deptId)?.ten ?? row.department_ten;

  return (
    <div className="khsx-scrim" onClick={onClose}>
      <div className="khsx-drawer khsx-drawer--buoc" role="dialog" aria-modal="true" aria-label="Xếp lịch công đoạn" onClick={(e) => e.stopPropagation()}>
        <div className="khsx-drawer__head">
          <div className="khsx-drawer__headmain">
            <p className="khsx-drawer__kicker">Xếp lịch công đoạn</p>
            <h2 className="khsx-drawer__title">{row.cong_doan_ten ?? "Công đoạn"}</h2>
            <p className="khsx-drawer__meta">
              {row.lsx_ma ?? "—"}
              {row.is_rush && <> · <span className="xlcd-drawer-rush">GẤP</span></>}
            </p>
          </div>
          <div className="khsx-buoc__nav">
            <button type="button" disabled={!hasPrev} onClick={onPrev} aria-label="Công đoạn trước"><Icon name="chevron" size={16} /></button>
            <button type="button" disabled={!hasNext} onClick={onNext} aria-label="Công đoạn sau"><Icon name="chevron" size={16} /></button>
          </div>
          <button type="button" className="khsx-drawer__x" onClick={onClose} aria-label="Đóng"><Icon name="x" size={18} /></button>
        </div>

        <div className="khsx-drawer__body">
          {steps.length > 1 && (
            <div className="xlcd-drawer-flow">
              <ChuoiCongDoan steps={steps.map((s) => ({ ten: s.cong_doan_ten ?? "—", loai_buoc: s.loai_buoc ?? undefined }))} activeIndex={activeIndex} />
            </div>
          )}

          {blocked ? (
            <div className="khsx-ready khsx-ready--blocked">
              <p className="khsx-ready__title">Chưa xếp được — còn thiếu</p>
              <ul className="khsx-ready__list">
                <li className="khsx-ready__item">
                  <Icon name="x" size={12} />
                  <span>{XEP_LICH_BLOCKED_LABELS[row.blocked_reason!] ?? row.blocked_reason}</span>
                </li>
              </ul>
            </div>
          ) : (
            <div className="khsx-ready khsx-ready--ok">
              <p className="khsx-ready__title"><Icon name="check" size={15} /> Đủ điều kiện xếp lịch.</p>
            </div>
          )}

          <div className="khsx-nhom">
            <h3 className="khsx-nhom__title">Gán máy · ca · giờ</h3>

            {kind === "none" ? (
              <p className="khsx-nhom__sub">Bước chờ kỹ thuật — không chiếm máy, chỉ cần đặt giờ bắt đầu.</p>
            ) : kind === "ncc" ? (
              <label className="khsx-field">
                <span className="khsx-field__label">Nhà gia công</span>
                <input value={ncc} disabled={readOnly} onChange={(e) => setNcc(e.target.value)} placeholder="Tên nhà gia công" />
              </label>
            ) : (
              <label className="khsx-field">
                <span className="khsx-field__label">{kind === "to" ? "Tổ thực hiện" : "Máy"}</span>
                {readOnly ? (
                  <span className="khsx-kv__val">{(kind === "to" ? deptTen : mayTen) ?? "—"}</span>
                ) : (
                  <select
                    value={kind === "to" ? (deptId ?? "") : (mayId ?? "")}
                    onChange={(e) => {
                      const v = e.target.value ? Number(e.target.value) : null;
                      if (kind === "to") setDeptId(v); else setMayId(v);
                    }}
                  >
                    <option value="">— chưa gán —</option>
                    {(kind === "to" ? phongBans : mays).map((o) => (
                      <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>
                    ))}
                  </select>
                )}
              </label>
            )}

            <div className="khsx-field" style={{ marginTop: "var(--sp-3)" }}>
              <span className="khsx-field__label">Ca làm</span>
              <div className="khsx-seg khsx-seg--sm">
                {CA_OPTIONS.map((c) => (
                  <button key={c.id} type="button" disabled={readOnly} className={ca === c.id ? "is-active" : ""} onClick={() => setCa(ca === c.id ? null : c.id)}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="khsx-field" style={{ marginTop: "var(--sp-3)" }}>
              <span className="khsx-field__label">Bắt đầu</span>
              <input type="datetime-local" value={dt} disabled={readOnly} onChange={(e) => setDt(e.target.value)} />
            </label>

            <div className="khsx-tinh">
              <div className="khsx-tinh__row">
                <span className="khsx-tinh__label">Chiếm máy</span>
                <span className="khsx-tinh__val">{thoiLuong(row.chiem_may_phut)}</span>
              </div>
              <div className="khsx-tinh__row">
                <span className="khsx-tinh__label">Tổng dẫn</span>
                <span className="khsx-tinh__val">{thoiLuong(row.tong_phut)}</span>
              </div>
              <div className="khsx-tinh__row khsx-tinh__row--total">
                <span className="khsx-tinh__label">Kết thúc</span>
                <span className="khsx-tinh__val">{ngayGio(row.finish_at)}</span>
              </div>
            </div>
          </div>

          {goiY && (goiY.khe_trong || goiY.han_lui) && !readOnly && (
            <div className="khsx-goiy">
              <p className="khsx-goiy__text">
                Máy đề xuất, người quyết. Chọn nhanh mốc bắt đầu theo gợi ý dưới đây.
              </p>
              <div className="khsx-goiy__acts">
                {goiY.khe_trong && (
                  <Button variant="secondary" onClick={() => setDt(toLocalInput(goiY.khe_trong))}>
                    Máy trống sớm nhất ({ngayGio(goiY.khe_trong)})
                  </Button>
                )}
                {goiY.han_lui && (
                  <Button variant="ghost" onClick={() => setDt(toLocalInput(goiY.han_lui))}>
                    Hạn lùi ({ngayGio(goiY.han_lui)})
                  </Button>
                )}
              </div>
            </div>
          )}

          {row.nguon === "in_ghep" && (
            <div className="khsx-nhom">
              <h3 className="khsx-nhom__title">Thành viên bài ghép</h3>
              {members === null ? (
                <p className="khsx-nhom__sub">Đang tải…</p>
              ) : members.length === 0 ? (
                <p className="khsx-nhom__sub">Không có thành viên.</p>
              ) : (
                <ul className="xlcd-members">
                  {members.map((m) => (
                    <li key={m.lsx_id}>
                      <span className="xlcd-members__ma">{m.lsx_ma ?? "—"}</span>
                      <span className="xlcd-members__ten">{m.lsx_ten ?? ""}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="khsx-drawer__foot">
          {canUpdate && (
            row.is_locked ? (
              <Button variant="ghost" onClick={() => onKhoa(false)}><Icon name="lockOpen" size={14} /> Gỡ khóa</Button>
            ) : (
              <Button variant="ghost" onClick={() => onKhoa(true)}><Icon name="lock" size={14} /> Khóa</Button>
            )
          )}
          <div className="khsx-drawer__footbtns">
            <Button variant="secondary" onClick={onClose}>Hủy</Button>
            <Button variant="primary" disabled={readOnly} onClick={luu}>Lưu</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================ skeleton ======================================
function BoardSkeleton({ colCount }: { colCount: number }) {
  return (
    <div className="xlcd-tablewrap">
      <table className="xlcd-table">
        <tbody className="khsx-skel">
          {Array.from({ length: 6 }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: colCount }).map((__, c) => (
                <td key={c}><span className="khsx-skel__bar" /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function QueueSkeleton() {
  return (
    <div className="xlcd-queue__skel">
      {Array.from({ length: 4 }).map((_, i) => (
        <span key={i} className="khsx-skel__bar xlcd-queue__skelbar" />
      ))}
    </div>
  );
}

// ============================ hook: đóng khi click ngoài / Esc =============
function useDismiss(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onDocClick = () => onClose();
    const id = window.setTimeout(() => document.addEventListener("click", onDocClick), 0);
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);
}

// ============================ helper undo ===================================
function undoFields(patch: XepLichGanBody, prev: XepLichRow): XepLichGanBody {
  const out: XepLichGanBody = {};
  if ("may_id" in patch) out.may_id = prev.may_id;
  if ("department_id" in patch) out.department_id = prev.department_id;
  if ("nha_cung_cap" in patch) out.nha_cung_cap = prev.nha_cung_cap;
  if ("work_shift_id" in patch) out.work_shift_id = prev.work_shift_id;
  if ("start_at" in patch) out.start_at = prev.start_at;
  return out;
}
