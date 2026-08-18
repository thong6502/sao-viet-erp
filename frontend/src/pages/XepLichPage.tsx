// BÀN XẾP LỊCH CÔNG ĐOẠN — biến routing đã "sẵn sàng" thành công việc CÓ MÁY + GIỜ.
//
// Luồng: LSX / bài ghép sẵn sàng nằm ở KHAY "Chờ lập kế hoạch" → "Đưa vào kế hoạch" sinh dòng lịch →
// GANTT gom theo Máy / Lệnh / Bài ghép → kéo thanh (hoặc mở panel phải) để gán máy · giờ → hệ tính giờ
// kết thúc + độ dư + nhãn nguy cơ + cờ xung đột → khóa khi chốt. MÁY CHỈ GHI NHẬN — người kế hoạch quyết.
//
// MỘT BÀN LÀM VIỆC (18/08/2026). Trước đây màn này có 4 view trên CÙNG một tập dữ liệu (Bảng · Gantt ·
// Vấn đề · Tuần) — đổi view là mất chỗ đang đứng, mà mỗi view lại trả lời nửa câu hỏi. Nay:
//   · Gantt là view DUY NHẤT — vấn đề xem ngay trên chính cái lịch, không mở danh sách thứ hai.
//   · Panel phải = chi tiết bước đang chọn (dính, không phải hộp che màn).
//   · Dải chân màn = "N chặn · M lưu ý" (bấm để lọc) + cửa Phát hành — CỬA CHẶN THẬT DUY NHẤT.
//   · Tải 4 tuần tới = khối gập ở đầu Gantt (trả lời "tuần sau còn nhận thêm việc được không").
// Code view Bảng đã gỡ; `VanDeView` giữ nguyên trong `XepLichVanDeView.tsx` (không còn nơi gọi) để
// bật lại được nếu xưởng đòi — khối phát hành đã tách ra dùng chung nên KHÔNG có bản chép đôi.
//
// Kiến trúc: data phẳng (`rows: XepLichRow[]`) tách khỏi render; group/filter/search client-side.
// Điều hướng bằng state qua AppShell (không react-router). Real-time qua `eventTick`.
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  XEP_LICH_BLOCKED_LABELS,
  api,
  type LsxLoaiBuoc,
  type XepLichGanBody,
  type XepLichGanLoatRow,
  type XepLichChen,
  type XepLichGoiY,
  type XepLichKeHoachTuan,
  type XepLichTuanO,
  type XepLichHangChoItem,
  type XepLichNguon,
  type XepLichRow,
  type XepLichSanSangOut,
  type XepLichVanDe,
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
  Skeleton,
  classHan,
  ngay,
  ngayGio,
  num,
  thoiLuong,
} from "./keHoachSxShared";
import { GanttBoard } from "./GanttBoard";
import { DrawerVanDe, PhatHanhDialog, type PhuongAnNav } from "./XepLichVanDeView";
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

// Ô "Ca làm" đã gỡ 18/08/2026. Không phép tính nào đọc `dong.work_shift_id`: `_lich_may` lấy ca từ
// `WorkShift` toàn xưởng, còn máy thì chạy LIÊN TỤC từ 10/08 — ô này chỉ ghi rồi để đó, người dùng
// chọn xong tưởng lịch đổi. Cột DB giữ nguyên (xoá ở lượt sau).

/** Bỏ dấu để tìm kiếm (bám RefSearchField của RebuildCatalogPage). */
const norm = (s: string): string =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");

type ResKind = "may" | "to" | "ncc" | "none";
/** Bước chiếm gì → ô "Máy/NCC" gán field nào. */
function resKind(lb: LsxLoaiBuoc | null): ResKind {
  if (lb === "thue_ngoai") return "ncc";
  if (lb === "to") return "to";
  return "may"; // bước Máy và dòng in chung của bài ghép
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
// ============================ controller =====================================
export function XepLichPage({
  navigate,
  eventTick,
  onBadgeStale,
  focusLsxMa,
}: {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  eventTick?: number;
  onBadgeStale?: () => void;
  /** Đèn "Máy & giờ" / "Người" ở Kế hoạch SX bấm sang đây: điền sẵn ô tìm bằng mã lệnh, không bắt
   *  người dùng dò lại trong cả bàn xếp lịch. */
  focusLsxMa?: string | null;
}) {
  const { token, user } = useAuth();
  const can = useCan();
  const canCreate = can("xep_lich", "create");
  const canUpdate = can("xep_lich", "update");
  const canApprove = can("xep_lich", "approve"); // quyền PHÁT (can_approve) — nút Phát hành
  const canApproveException = can("xep_lich", "approve_exception"); // duyệt ngoại lệ — nút Xin ngoại lệ (tách khỏi phát hành)

  const [rows, setRows] = useState<XepLichRow[] | null>(null);
  const [queue, setQueue] = useState<XepLichHangChoItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mays, setMays] = useState<Row[]>([]);
  const [phongBans, setPhongBans] = useState<Row[]>([]);
  // View "Vấn đề": xung đột & nguy cơ trễ (dẫn xuất) + danh sách sẵn-sàng-phát-hành. Nạp LUÔN (không
  // chỉ khi mở view) để badge Chặn trên tab + chỉ báo readiness ở header tự nhảy theo SSE.
  const [vanDe, setVanDe] = useState<XepLichVanDeListOut | null>(null);
  const [sanSang, setSanSang] = useState<XepLichSanSangOut | null>(null);

  const [groupBy, setGroupBy] = useState<GroupBy>("may");
  const [filters, setFilters] = useState<Filters>({ thueNgoai: false, chiXungDot: false });
  const [q, setQ] = useState(focusLsxMa ?? "");
  // Bấm chấm lần thứ hai với mã khác (màn đã mount) phải đổi ô tìm theo.
  useEffect(() => {
    if (focusLsxMa) setQ(focusLsxMa);
  }, [focusLsxMa]);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [openRowId, setOpenRowId] = useState<number | null>(null);
  const [queueOpen, setQueueOpen] = useState(false);
  const [isFocusMode, setIsFocusMode] = useState(false);
  const [toast, setToast] = useState<{ text: string; undo?: () => void } | null>(null);
  const [askGo, setAskGo] = useState<XepLichHangChoItem | null>(null);
  // Khối gập "Tải 4 tuần tới": CHỈ mount khi mở — `TuanView` tự gọi API lúc mount, gập mà vẫn mount
  // là mỗi lần vào màn lại nện thêm một lượt tính tải 4 tuần cho toàn xưởng.
  const [tuanMo, setTuanMo] = useState(false);
  const [phatHanhMo, setPhatHanhMo] = useState(false);
  const [vanDeKey, setVanDeKey] = useState<string | null>(null);
  // Nhảy trục thời gian + nháy thanh trên Gantt (thay cuộn-tới-band của view Bảng đã gỡ).
  const [flashKey, setFlashKey] = useState<string | null>(null);
  const [pendingFlash, setPendingFlash] = useState<{ nguon: XepLichNguon; id: number } | null>(null);

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

  // Vấn đề + sẵn-sàng-phát-hành: 1 lần nạp, dải chân màn và chip trên thanh Gantt dùng chung
  // state. Lỗi nạp báo qua `setErr` chung — trước có ô lỗi riêng, nhưng nó nằm ở view Vấn đề đã
  // gỡ nên chỉ còn là biến không ai đọc.
  const loadVanDe = useCallback(() => {
    if (!token) return;
    api.xepLich.vanDe(token).then(setVanDe).catch((e: unknown) =>
      setErr(e instanceof ApiError ? e.message : String(e)),
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
  // Lọc theo NHÓM MÁY — đích của cú bấm ô đỏ ở bảng Tuần (mục J: "bấm ô đỏ → nhảy Gantt đã lọc
  // nhóm máy đó"). Ô tìm kiếm `q` không làm được việc này: nó chỉ dò mã lệnh và tên công đoạn.
  const [nhomMay, setNhomMay] = useState<string | null>(null);
  const mayTheoNhom = useMemo(() => {
    const m = new Map<number, string>();
    for (const x of mays) m.set(x.id, String(x.loai_may ?? "").trim() || String(x.ten));
    return m;
  }, [mays]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const nq = norm(q.trim());
    return rows.filter((r) => {
      if (filters.thueNgoai && r.loai_buoc !== "thue_ngoai") return false;
      if (filters.chiXungDot && !r.co_xung_dot) return false;
      if (nhomMay && (r.may_id == null || mayTheoNhom.get(r.may_id) !== nhomMay)) return false;
      if (nq && !norm(`${r.lsx_ma ?? ""} ${r.cong_doan_ten ?? ""}`).includes(nq)) return false;
      return true;
    });
  }, [rows, filters, q, nhomMay, mayTheoNhom]);

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

  // ---- nháy lane vừa thêm (Gantt tự cuộn tới) ----
  useEffect(() => {
    if (!pendingFlash || !rows) return;
    const first = filtered.find((r) =>
      pendingFlash.nguon === "in_ghep"
        ? r.bai_ghep_id === pendingFlash.id
        : r.nguon === "lsx" && r.lsx_id === pendingFlash.id,
    );
    setPendingFlash(null);
    if (!first) return;
    setFlashKey(bandInfo(first, groupBy).key);
    const t = setTimeout(() => setFlashKey(null), 1600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, pendingFlash]);

  // ---- mốc thời gian Gantt phải nhảy tới ----
  // Gõ mã một lệnh xếp tháng 11 mà trục vẫn đứng ở hôm nay thì lane trống trơn, phải bấm "Tiến" 6
  // lần mới thấy — đúng lúc người ta tin là "không có gì". Chỉ nhảy khi CÓ tìm kiếm: không thì mỗi
  // lần nạp lại màn là trục tự nhảy đi đâu đó.
  const focusAt = useMemo(() => {
    if (!q.trim()) return null;
    const mocs = filtered.map((r) => r.start_at).filter((x): x is string => !!x).sort();
    return mocs[0] ?? null;
  }, [q, filtered]);

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

  // Điều hướng "phương án" từ danh sách vấn đề — MÁY CHỈ GHI NHẬN: đổi cách gom / nhảy màn, KHÔNG
  // auto-fix. Không còn view nào để đổi, nên "phương án" giờ = đổi TRỤC GOM + xoá lọc + nháy lane.
  const onPhuongAn = useCallback((p: PhuongAnNav) => {
    if (p.kind === "man-ke-hoach") { navigate?.("ke-hoach-sx"); return; }
    setVanDeKey(null);
    if (p.kind === "gantt-may") { setGroupBy("may"); return; }
    setFilters({ thueNgoai: false, chiXungDot: false });
    if (p.kind === "gantt-ma") { setQ(p.ma); setGroupBy("lenh"); return; }
    setQ("");
    if (p.kind === "gantt-lenh") { setGroupBy("lenh"); if (p.flash) setPendingFlash(p.flash); return; }
    if (p.kind === "gantt-bai-ghep") { setGroupBy("bai-ghep"); if (p.flash) setPendingFlash(p.flash); }
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
  const clearPick = useCallback(() => setPicked(new Set()), []);
  // Tick CẢ LANE trên Gantt — đường vào duy nhất còn lại cho `BulkBar` sau khi bỏ ô tick từng dòng
  // của bảng. Nhận cả dòng CHƯA CÓ GIỜ (chip ở dải đỗ) vì đó đúng là đám cần "Tự xếp" nhất.
  const togglePickBand = useCallback((ids: number[]) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (ids.every((id) => prev.has(id))) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }, []);

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
    const targets = (rows ?? [])
      .filter((r) => picked.has(r.id) && r.may_id != null && !r.is_locked && !r.blocked_reason)
      // (E) GOM VIỆC CÙNG LOẠI: trong cùng mức ưu tiên (hạn giao), xếp liền các việc cùng giấy ·
      // cùng khổ · cùng bộ mực (`gom_key` do server cấp). Vì `bulkAuto` gán TUẦN TỰ — dòng sau lấy
      // khe ngay sau dòng trước — nên chỉ cần đổi THỨ TỰ là chúng nằm cạnh nhau trên máy, thợ khỏi
      // rửa mực / thay giấy giữa chừng.
      //
      // Chỉ đổi thứ tự ĐỀ XUẤT: không đụng công thức thời gian, không khai thêm gì. Hạn giao vẫn
      // là trục ưu tiên NGOÀI — gom mà đẩy một lệnh gấp xuống sau là tối ưu nhầm thứ.
      .sort((a, b) => {
        const ha = a.muon_nhat ?? "9999";
        const hb = b.muon_nhat ?? "9999";
        if (ha !== hb) return ha < hb ? -1 : 1;
        const ga = a.gom_key ?? "~";        // "~" > mọi khoá thật ⇒ dòng chưa đủ quy cách xuống cuối
        const gb = b.gom_key ?? "~";
        if (ga !== gb) return ga < gb ? -1 : 1;
        return a.id - b.id;
      });
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

  // ---- G1: chèn lệnh gấp & đẩy -------------------------------------------
  // Hai pha TÁCH HẲN: `moChen` chỉ TÍNH (server không ghi gì, thoát ra là mất), `apChen` mới ghi
  // bằng đúng `ganLoat` mà kéo-thả đang dùng — nên có sẵn Hoàn tác, không phải đẻ đường ghi thứ hai.
  const [chen, setChen] = useState<XepLichChen | null>(null);
  const [chenBusy, setChenBusy] = useState(false);

  const moChen = useCallback(async (dongId: number, mayId: number | null, dtStr: string) => {
    const tai = fromLocalInput(dtStr);
    if (!token || !tai) return;
    setChenBusy(true);
    try {
      setChen(await api.xepLich.chen(token, dongId, { may_id: mayId, tai }));
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setChenBusy(false);
    }
  }, [token]);

  const apChen = useCallback(async () => {
    if (!token || !chen) return;
    const truoc = new Map((rows ?? []).map((r) => [r.id, r.start_at] as const));
    const payload: XepLichGanLoatRow[] = chen.rows
      .filter((r) => r.moi)
      .map((r) => ({
        id: r.id,
        start_at: r.moi,
        // Chỉ dòng ĐANG CHÈN mới đổi máy; các dòng bị đẩy giữ nguyên máy của chúng.
        ...(r.la_viec_chen ? { may_id: chen.may_id } : {}),
      }));
    if (!payload.length) { setChen(null); return; }
    setChenBusy(true);
    try {
      const res = await api.xepLich.ganLoat(token, payload);
      applyRows(res.items);
      onBadgeStale?.();
      setChen(null);
      setToast({
        text: `Đã chèn và dời ${payload.length - 1} việc phía sau`,
        undo: async () => {
          const undo: XepLichGanLoatRow[] = payload.map((p) => ({
            id: p.id, start_at: truoc.get(p.id) ?? null,
          }));
          try { applyRows((await api.xepLich.ganLoat(token, undo)).items); onBadgeStale?.(); setToast(null); }
          catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
        },
      });
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setChenBusy(false);
    }
  }, [token, chen, rows, applyRows, onBadgeStale]);

  // ---- dẫn xuất vấn đề: dải chân màn + chip trên thanh Gantt ----
  const vanDeSummary = vanDe?.summary ?? null;
  const chanCount = vanDeSummary?.chan ?? 0;
  const tongVanDe = vanDeSummary?.tong ?? 0;
  const readyCount = (sanSang?.items ?? []).filter((i) => i.blocking === 0).length;
  const luuYCount = Math.max(0, tongVanDe - chanCount);
  const currentUserId = user?.id ?? null;

  // Vấn đề gắn vào từng DÒNG lịch (`impacts.dong_ids`) → chip trên đúng thanh Gantt gây ra nó.
  // Không có bước này thì "3 chặn" ở dải chân chỉ là con số, người dùng vẫn phải tự dò xem thanh nào.
  const vanDeTheoDong = useMemo(() => {
    const m = new Map<number, XepLichVanDe[]>();
    for (const it of vanDe?.items ?? []) {
      for (const id of it.impacts.dong_ids) {
        const cur = m.get(id);
        if (cur) cur.push(it); else m.set(id, [it]);
      }
    }
    return m;
  }, [vanDe]);
  const openVanDe = vanDeKey ? (vanDe?.items ?? []).find((x) => x.issue_key === vanDeKey) ?? null : null;
  useEffect(() => {
    if (vanDeKey && vanDe && !vanDe.items.some((x) => x.issue_key === vanDeKey)) setVanDeKey(null);
  }, [vanDe, vanDeKey]);

  // ---- điều hướng drawer ----
  const drawerIdx = openRow ? flatOrder.findIndex((r) => r.id === openRow.id) : -1;
  const goPrev = drawerIdx > 0 ? () => setOpenRowId(flatOrder[drawerIdx - 1].id) : undefined;
  const goNext =
    drawerIdx >= 0 && drawerIdx < flatOrder.length - 1 ? () => setOpenRowId(flatOrder[drawerIdx + 1].id) : undefined;

  // Alt+↑/↓ — duyệt hết 60 bước bằng bàn phím thay vì rê chuột dò từng thanh trên Gantt. Phải là
  // Alt: mũi tên TRẦN đang là "dời giờ / đổi lane" của thanh đang focus, cướp nó là hỏng cả hai.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
      if (drawerIdx < 0) return;
      const next = drawerIdx + (e.key === "ArrowDown" ? 1 : -1);
      if (next < 0 || next >= flatOrder.length) return;
      e.preventDefault();
      setOpenRowId(flatOrder[next].id);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerIdx, flatOrder]);

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

      <div className={`xlcd__grid ${openRow ? "is-panel" : ""}`}>
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
            {/* Đang lọc theo nhóm máy (bấm từ bảng Tuần sang) — PHẢI có chip gỡ, không thì người
                dùng ngồi nhìn một bàn thiếu lane mà không biết vì sao. */}
            {nhomMay && (
              <button
                type="button"
                className="khsx-pill xlcd-pill-loc"
                onClick={() => setNhomMay(null)}
                title="Bỏ lọc nhóm máy"
              >
                Nhóm: {nhomMay} ✕
              </button>
            )}
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
                placeholder="Tìm mã LSX / bài ghép / công đoạn"
                aria-label="Tìm dòng xếp lịch"
              />
            </label>
          </div>

          {/* Mục J — TẢI 4 TUẦN TỚI, khối GẬP. Không phải view riêng nữa: câu nó trả lời ("tuần sau
              còn nhận thêm việc được không") là câu hỏi thỉnh thoảng, còn Gantt là bàn làm việc
              hằng ngày. Đổi cả màn để hỏi một câu thỉnh thoảng là bắt người ta trả giá mỗi ngày.
              Chỉ mount khi mở — `TuanView` gọi API ngay lúc mount. */}
          <details
            className="xlcd-tuanfold"
            open={tuanMo}
            onToggle={(e) => setTuanMo((e.currentTarget as HTMLDetailsElement).open)}
          >
            <summary className="xlcd-tuanfold__sum">
              <Icon name="calendar" size={13} /> Tải 4 tuần tới
              <span className="xlcd-tuanfold__hint">còn nhận thêm việc được không</span>
            </summary>
            {tuanMo && (
              <TuanView
                token={token}
                eventTick={eventTick}
                onMoGantt={(nhom) => { setNhomMay(nhom); setGroupBy("may"); setTuanMo(false); }}
              />
            )}
          </details>

          {rows === null ? (
            <BoardSkeleton />
          ) : filtered.length === 0 ? (
            coLoc ? (
              <EmptyState
                icon="search"
                title="Không khớp bộ lọc"
                sub="Không có dòng nào khớp nhóm lọc / từ khoá hiện tại."
                action={
                  <Button variant="secondary" onClick={() => { setFilters({ thueNgoai: false, chiXungDot: false }); setQ(""); setNhomMay(null); }}>
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
          ) : (
            <GanttBoard
              bands={bands}
              groupBy={groupBy}
              token={token}
              canUpdate={canUpdate}
              openRowId={openRowId}
              picked={picked}
              vanDeTheoDong={vanDeTheoDong}
              focusAt={focusAt}
              flashKey={flashKey}
              onOpenRow={setOpenRowId}
              onTogglePickBand={togglePickBand}
              onOpenVanDe={setVanDeKey}
              onGan={onGan}
              onChen={moChen}
              onToast={(text, undo) => setToast({ text, undo })}
            />
          )}
        </section>

        {/* PANEL PHẢI DÍNH — không phải hộp che màn. Sửa một bước mà vẫn nhìn thấy cả bàn lịch là
            khác biệt lớn nhất của đợt này: trước đây mở drawer là mất chỗ đang đứng, đóng lại phải
            dò từ đầu. MỘT tab duy nhất (chi tiết bước) — nhét danh sách vấn đề vào đây chỉ là view
            thứ hai trá hình. */}
        {openRow && (
          <DrawerBuoc
            inline
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
              token && openRow.bai_ghep_id ? (await api.baiGhep2.get(token, openRow.bai_ghep_id)).thanh_vien : []
            }
            onChen={moChen}
            chenBusy={chenBusy}
          />
        )}
      </div>

      {picked.size > 0 ? (
        <BulkBar
          count={picked.size}
          canUpdate={canUpdate}
          mays={mays}
          phongBans={phongBans}
          onGanMay={(id) => bulkGan({ may_id: id }, "Gán máy")}
          onGanTo={(id) => bulkGan({ department_id: id }, "Gán tổ")}
          onDatGio={(local) => bulkGan({ start_at: fromLocalInput(local) }, "Đặt giờ")}
          onKhoa={() => bulkKhoa(true)}
          onMoKhoa={() => bulkKhoa(false)}
          onAuto={bulkAuto}
          onClear={clearPick}
        />
      ) : (
        /* DẢI CHÂN MÀN — hai con số + cửa Phát hành. Đây là chỗ view "Vấn đề" và cửa phát hành đi
           về sau khi cắt: vấn đề xem NGAY TRÊN LỊCH (bấm số → lọc còn thanh có vấn đề), phát hành
           mở hộp thoại. Cửa chặn không rơi mất, chỉ đổi khung. */
        (chanCount > 0 || luuYCount > 0 || readyCount > 0) && (
          <div className="xlcd-bulk xlcd-footbar" role="region" aria-label="Vấn đề & phát hành">
            <button
              type="button"
              className={`xlcd-footbar__stat ${chanCount > 0 ? "is-chan" : ""} ${filters.chiXungDot ? "is-on" : ""}`}
              aria-pressed={filters.chiXungDot}
              onClick={() => setFilters((f) => ({ ...f, chiXungDot: !f.chiXungDot }))}
              title="Lọc bàn lịch còn lại các thanh đang vướng"
            >
              <Icon name="ban" size={13} />
              <b>{num(chanCount)}</b> chưa phát hành được
              {luuYCount > 0 && <span className="xlcd-footbar__phu">· {num(luuYCount)} nên xem</span>}
            </button>
            {filters.chiXungDot && (
              <button type="button" className="xlcd-footbar__go" onClick={() => setFilters((f) => ({ ...f, chiXungDot: false }))}>
                Xem lại tất cả
              </button>
            )}
            <div className="khsx__spacer" />
            <button
              type="button"
              className="xlcd-bulk__btn xlcd-bulk__btn--accent"
              onClick={() => setPhatHanhMo(true)}
            >
              <Icon name="send" size={13} /> Phát hành{readyCount > 0 ? ` (${num(readyCount)})` : ""}
            </button>
          </div>
        )
      )}

      {phatHanhMo && (
        <PhatHanhDialog
          sanSang={sanSang}
          chan={chanCount}
          token={token}
          canApprove={canApprove}
          onRefetch={() => { loadVanDe(); load(); onBadgeStale?.(); }}
          onToast={(text) => setToast({ text })}
          onShowIssues={(ma) => { setQ(ma); setGroupBy("lenh"); }}
          onClose={() => setPhatHanhMo(false)}
        />
      )}

      {openVanDe && (
        <DrawerVanDe
          it={openVanDe}
          groupSize={openVanDe.group_key ? (vanDe?.items ?? []).filter((x) => x.group_key === openVanDe.group_key).length : 0}
          token={token}
          canApproveException={canApproveException}
          currentUserId={currentUserId}
          mayTen={mayName}
          hasPrev={false}
          hasNext={false}
          onClose={() => setVanDeKey(null)}
          onDone={() => { loadVanDe(); load(); onBadgeStale?.(); }}
          onToast={(text) => setToast({ text })}
          onPhuongAn={onPhuongAn}
          onShowGroup={() => { setVanDeKey(null); setFilters((f) => ({ ...f, chiXungDot: true })); }}
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

      {chen && (
        <ChenPreviewDialog
          data={chen}
          busy={chenBusy}
          onHuy={() => setChen(null)}
          onLuu={apChen}
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
                  <Icon name="columns" size={13} /> Bảng nén
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
                        <td title={it.ten ?? undefined}>
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
  count, canUpdate, mays, phongBans, onGanMay, onGanTo, onDatGio, onKhoa, onMoKhoa, onAuto, onClear,
}: {
  count: number;
  canUpdate: boolean;
  mays: Row[];
  phongBans: Row[];
  onGanMay: (id: number) => void;
  /** Thợ nghỉ ốm phải chuyển 12 bước sang tổ khác — việc thật, mà ô tick từng dòng đã gỡ cùng
   *  view Bảng nên đây là đường DUY NHẤT còn lại. `gan()` đã nhận `department_id` từ trước. */
  onGanTo: (id: number) => void;
  onDatGio: (local: string) => void;
  onKhoa: () => void;
  onMoKhoa: () => void;
  onAuto: () => void;
  onClear: () => void;
}) {
  const [pop, setPop] = useState<"may" | "to" | "gio" | null>(null);
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
            <button type="button" className="xlcd-bulk__btn" onClick={() => setPop(pop === "to" ? null : "to")}>
              <Icon name="building" size={13} /> Gán tổ <Icon name="chevron" size={12} />
            </button>
            {pop === "to" && (
              <div className="xlcd-pop xlcd-pop--up" onClick={(e) => e.stopPropagation()}>
                <RefPick options={phongBans} placeholder="Chọn tổ cho các dòng…" onPick={(id) => { onGanTo(id); setPop(null); }} />
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
  onChen, chenBusy, inline,
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
  /** G1 — mở bảng xem trước chèn (không ghi). `dt` là giá trị ô giờ đang gõ trên drawer. */
  onChen: (dongId: number, mayId: number | null, dt: string) => void;
  chenBusy: boolean;
  /** PANEL DÍNH bên phải Gantt (mặc định của màn) thay vì hộp che cả bàn lịch. */
  inline?: boolean;
}) {
  const kind = resKind(row.loai_buoc);
  const [mayId, setMayId] = useState<number | null>(row.may_id);
  const [deptId, setDeptId] = useState<number | null>(row.department_id);
  const [ncc, setNcc] = useState(row.nha_cung_cap ?? "");
  const [dt, setDt] = useState(toLocalInput(row.start_at));
  const [goiY, setGoiY] = useState<XepLichGoiY | null>(null);
  const [members, setMembers] = useState<{ lsx_id: number; lsx_ma: string | null; lsx_ten: string | null }[] | null>(null);

  useEffect(() => {
    setMayId(row.may_id); setDeptId(row.department_id); setNcc(row.nha_cung_cap ?? "");
    setDt(toLocalInput(row.start_at)); setGoiY(null);
  }, [row.id, row.may_id, row.department_id, row.nha_cung_cap, row.start_at]);

  useEffect(() => { fetchGoiY(row.id).then(setGoiY).catch(() => setGoiY(null)); }, [row.id, fetchGoiY]);
  useEffect(() => {
    if (row.nguon === "in_ghep") fetchMembers().then(setMembers).catch(() => setMembers([]));
    else setMembers(null);
  }, [row.id, row.nguon, fetchMembers]);

  // Esc đóng panel — nhưng chỉ khi con trỏ KHÔNG nằm trong ô nhập (Esc trong `datetime-local` là
  // "bỏ giá trị đang gõ", đóng luôn panel là cướp thao tác).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
      onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const steps = [...siblings].sort((a, b) => (a.som_nhat ?? "").localeCompare(b.som_nhat ?? ""));
  const activeIndex = steps.findIndex((s) => s.id === row.id);
  const blocked = !!row.blocked_reason;
  const readOnly = !canUpdate || row.is_locked;

  const luu = () => {
    const body: XepLichGanBody = { start_at: fromLocalInput(dt) };
    if (kind === "may") body.may_id = mayId;
    else if (kind === "to") body.department_id = deptId;
    else if (kind === "ncc") body.nha_cung_cap = ncc.trim() || null;
    onGan(row.id, body);
    onClose();
  };

  const mayTen = mays.find((m) => m.id === mayId)?.ten ?? row.may_ten;
  const deptTen = phongBans.find((d) => d.id === deptId)?.ten ?? row.department_ten;

  const than = (
      <div
        className={inline ? "xlcd-side__box" : "khsx-drawer khsx-drawer--buoc"}
        role={inline ? "region" : "dialog"}
        aria-modal={inline ? undefined : true}
        aria-label="Xếp lịch công đoạn"
        onClick={(e) => e.stopPropagation()}
      >
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
            <h3 className="khsx-nhom__title">Gán máy · giờ</h3>

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
                    {/* Bước đang trỏ một phòng KHÔNG còn trong danh sách Tổ (mục H siết định nghĩa
                        Tổ = nút lá trong nhánh Sản xuất). Không thêm dòng này thì `<select>` hiện
                        TRỐNG dù bước vẫn đang gán tổ đó, và bấm Lưu là xoá mất tổ của lệnh đang
                        chạy. Giữ nguyên giá trị, chỉ dán nhãn để người xếp biết mà sửa dần. */}
                    {kind === "to" && row.department_id != null
                      && !phongBans.some((o) => o.id === row.department_id) && (
                      <option value={row.department_id}>
                        {row.department_ten ?? `#${row.department_id}`} (không còn là tổ)
                      </option>
                    )}
                  </select>
                )}
              </label>
            )}

            <label className="khsx-field" style={{ marginTop: "var(--sp-3)" }}>
              <span className="khsx-field__label">Bắt đầu</span>
              <input type="datetime-local" value={dt} disabled={readOnly} onChange={(e) => setDt(e.target.value)} />
            </label>

            {/* G1 — CHÈN LỆNH GẤP. Đặt ngay dưới ô giờ vì nó dùng đúng giờ đang gõ ở trên: "chèn
                vào đây" = chèn vào mốc này trên máy này. Bấm chỉ MỞ BẢNG XEM TRƯỚC, chưa ghi gì —
                người xếp nhìn trọn dây bị đẩy rồi mới quyết, thay vì kéo tay từng việc và mỗi lần
                một lần ăn báo đỏ trùng máy. */}
            {kind === "may" && !readOnly && (
              <div className="khsx-goiy" style={{ marginTop: "var(--sp-3)" }}>
                <p className="khsx-goiy__text">
                  Ngày đã kín? <b>Chèn vào đây</b> sẽ lùi các việc phía sau trên máy này vừa đủ hết
                  chồng lấn — và cho xem trước toàn bộ trước khi ghi.
                </p>
                <div className="khsx-goiy__acts">
                  <Button
                    variant="accent"
                    disabled={!mayId || !dt || chenBusy}
                    onClick={() => onChen(row.id, mayId, dt)}
                  >
                    {chenBusy ? "Đang tính…" : "Chèn vào đây"}
                  </Button>
                </div>
              </div>
            )}

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

          {/* Mục D — TOP 3 MÁY, sắp theo GIỜ XONG.
              Vì sao không sắp theo "máy trống sớm nhất": tốc độ khai theo từng máy, nên máy chậm
              rảnh lúc 8h vẫn có thể xong SAU máy nhanh rảnh lúc 10h. Sắp theo giờ trống là đưa ra
              lời khuyên sai đúng lúc người ta tin nó nhất.
              Bảng này chạy CẢ KHI dòng chưa gán máy — đúng lúc cần gợi ý nhất. */}
          {kind === "may" && goiY && goiY.goi_y_may.length > 0 && !readOnly && (
            <div className="khsx-goiy khsx-goiy--may">
              <p className="khsx-goiy__text">
                Máy làm được công đoạn này, xếp theo <b>giờ xong</b> — bấm một dòng là gán luôn máy
                và giờ bắt đầu.
              </p>
              <table className="xlcd-topmay">
                <thead>
                  <tr>
                    <th>Máy</th>
                    <th>Bắt đầu được</th>
                    <th>Xong lúc</th>
                    <th>Chiếm máy</th>
                  </tr>
                </thead>
                <tbody>
                  {goiY.goi_y_may.map((g) => (
                    <tr
                      key={g.may_id}
                      className={`xlcd-topmay__row${g.may_id === mayId ? " is-current" : ""}`}
                    >
                      <td>
                        <button
                          type="button"
                          className="xlcd-topmay__pick"
                          onClick={() => {
                            setMayId(g.may_id);
                            if (g.khe_trong) setDt(toLocalInput(g.khe_trong));
                          }}
                        >
                          {g.may_ten ?? `Máy #${g.may_id}`}
                        </button>
                        {g.khong_hop_kho && (
                          <span className="xlcd-topmay__canh" title="Khổ giấy vượt khổ máy — vẫn gán được, cần xác nhận">
                            khổ vượt máy
                          </span>
                        )}
                        {/* Mục E — nói ra vì sao máy này đáng chọn khi hoà giờ: việc liền trước
                            cùng giấy/khổ/mực nên đổi việc gần như khỏi canh lại máy. */}
                        {g.cung_gom && (
                          <span className="xlcd-topmay__gom" title="Việc liền trước cùng giấy · khổ · bộ mực — đỡ canh máy">
                            nối việc cùng loại
                          </span>
                        )}
                      </td>
                      <td>{ngayGio(g.khe_trong)}</td>
                      <td className="xlcd-topmay__finish">{ngayGio(g.finish)}</td>
                      <td>{thoiLuong(g.chiem_may_phut)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
  );

  if (inline) return <aside className="xlcd-side" aria-label="Chi tiết bước">{than}</aside>;
  return <div className="khsx-scrim" onClick={onClose}>{than}</div>;
}

// ============================ skeleton ======================================
function BoardSkeleton() {
  return (
    <div className="xlcd-gskel" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, i) => (
        <span key={i} className="khsx-skel__bar xlcd-gskel__bar" />
      ))}
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

// ============================ J — tầng kế hoạch tuần ========================
/** Bảng tải theo TUẦN của từng máy / tổ. Tính lúc đọc ở server, **không lưu gì**.
 *
 *  Câu hỏi màn này trả lời: *"tuần sau còn nhận thêm việc được không"* — nên nó cố tình không có
 *  lịch giờ. Điểm dễ hiểu sai nhất: **Cần** gồm CẢ việc chưa xếp (việc chưa có giờ tính vào tuần
 *  chứa hạn của nó). Chỉ đếm việc đã xếp thì bảng báo "còn rỗng" trong khi hàng chờ đang đầy, và
 *  người ta nhận thêm đơn rồi vỡ trận.
 */
function TuanView({ token, eventTick, onMoGantt }: {
  token: string | null;
  eventTick?: number;
  /** Bấm ô MÁY → mở Gantt đã lọc đúng NHÓM máy đó (mục J). */
  onMoGantt: (nhom: string) => void;
}) {
  const [data, setData] = useState<XepLichKeHoachTuan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [soTuan, setSoTuan] = useState(4);

  const load = useCallback(() => {
    if (!token) return;
    const hom_nay = new Date();
    const tu = `${hom_nay.getFullYear()}-${String(hom_nay.getMonth() + 1).padStart(2, "0")}-${String(hom_nay.getDate()).padStart(2, "0")}`;
    api.xepLich.keHoachTuan(token, tu, soTuan)
      .then((r) => { setData(r); setErr(null); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, soTuan]);

  useEffect(() => load(), [load, eventTick]);

  if (err) return <BangLoi text={err} onRetry={load} />;
  if (!data) return <Skeleton rows={6} cols={5} />;
  if (data.items.length === 0) {
    return (
      <EmptyState
        icon="calendar"
        title="Chưa có việc nào trong các tuần này"
        sub="Đưa lệnh vào kế hoạch ở tab Hàng chờ, hoặc mở rộng số tuần."
      />
    );
  }

  const tuans = [...new Set(data.items.map((i) => i.tuan))];
  // Khoá dòng: máy gom theo NHÓM (`res_id` null) nên phải lấy `nhom`; tổ lấy id. Dùng `res_id`
  // cho cả hai thì mọi nhóm máy dồn chung một khoá "may:null" và bảng còn đúng một dòng máy.
  const khoaRes = (i: XepLichTuanO) => `${i.loai}:${i.res_id ?? i.nhom ?? i.ten}`;
  const res = [...new Map(data.items.map((i) => [khoaRes(i), i])).values()];

  return (
    <div className="xlcd-tuan">
      <div className="khsx__toolbar">
        <span className="xlcd-tuan__hint">
          <b>Cần</b> tính cả việc <b>chưa xếp</b> (dồn vào tuần chứa hạn của nó) — không thì bảng
          báo còn rỗng trong khi hàng chờ đang đầy. Tổ tính theo <b>giờ-người</b>.
        </span>
        <div className="khsx-seg khsx-seg--sm" role="tablist" aria-label="Số tuần">
          {[2, 4, 8].map((n) => (
            <button key={n} type="button" className={soTuan === n ? "is-active" : ""}
              onClick={() => setSoTuan(n)}>
              {n} tuần
            </button>
          ))}
        </div>
      </div>
      <div className="xlcd-tuan__scroll">
        <table className="xlcd-tuan__tbl">
          <thead>
            <tr>
              <th>Tài nguyên</th>
              {tuans.map((t) => {
                const o = data.items.find((i) => i.tuan === t);
                return <th key={t} className="xlcd-tuan__th">Tuần {o?.iso_tuan ?? ""}<span>{ngay(t)}</span></th>;
              })}
            </tr>
          </thead>
          <tbody>
            {res.map((r) => (
              <tr key={khoaRes(r)}>
                <td className="xlcd-tuan__res">
                  <span className={`xlcd-tuan__kind xlcd-tuan__kind--${r.loai}`}>
                    {r.loai === "may" ? "Máy" : "Tổ"}
                  </span>
                  {r.ten}
                </td>
                {tuans.map((t) => {
                  const o = data.items.find((i) => i.tuan === t && khoaRes(i) === khoaRes(r));
                  if (!o) return <td key={t} className="xlcd-tuan__o">—</td>;
                  const donVi = r.loai === "to" ? "giờ-người" : "giờ";
                  return (
                    <td key={t} className={`xlcd-tuan__o xlcd-tuan__o--${o.mau}`}>
                      {/* Bấm ô MÁY → nhảy Gantt đã lọc đúng NHÓM máy đó. Ô tổ chưa có lane riêng
                          nên không gắn hành động — thà không bấm được còn hơn bấm ra màn lạc đề. */}
                      <button
                        type="button"
                        className="xlcd-tuan__btn"
                        disabled={o.loai !== "may"}
                        onClick={() => o.loai === "may" && o.nhom && onMoGantt(o.nhom)}
                        title={o.loai === "may" ? "Mở Gantt của máy này" : undefined}
                      >
                        <b>{o.pct >= 999 ? "—" : `${o.pct}%`}</b>
                        <span>{num(o.can_gio)}/{num(o.kha_dung_gio)} {donVi}</span>
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================ G1 — bảng xem trước CHÈN ======================
/** Bảng *giờ cũ → giờ mới* của một lần chèn. **Chưa ghi gì** cho tới khi bấm Lưu.
 *
 *  Vì sao phải có bảng chứ không chèn thẳng: chèn một việc gấp vào ngày kín kéo theo cả dây việc
 *  phía sau, và hai hậu quả thật sự đau chỉ lộ ra khi nhìn TỔNG THỂ — lệnh nào vì thế mà trễ hạn,
 *  và việc nào lùi tới thì đè lên máy của lệnh khác. Chèn xong mới thấy là đã muộn.
 */
function ChenPreviewDialog({ data, busy, onHuy, onLuu }: {
  data: XepLichChen;
  busy: boolean;
  onHuy: () => void;
  onLuu: () => void;
}) {
  const biDay = data.rows.filter((r) => !r.la_viec_chen).length;
  const soTre = new Set(data.rows.filter((r) => r.tre_han).map((r) => r.lsx_ma)).size;
  const soDungDo = data.rows.filter((r) => r.dung_do.length > 0).length;
  return (
    <ConfirmDialog
      open
      title="Chèn vào đây?"
      message={
        biDay === 0
          ? "Lọt vừa khe trống — không việc nào phải lùi."
          : `${biDay} việc phía sau sẽ lùi vừa đủ để hết chồng lấn. Chưa ghi gì cho tới khi bấm Lưu.`
      }
      confirmLabel="Lưu"
      busy={busy}
      onConfirm={onLuu}
      onCancel={onHuy}
    >
      <div className="xlcd-chen">
        {data.chan === "gap_khoa" && (
          <p className="xlcd-chen__chan">
            Gặp việc đã khóa — dừng đẩy tại đó. Các việc sau nó giữ nguyên giờ; mở khóa nếu muốn dời tiếp.
          </p>
        )}
        {(soTre > 0 || soDungDo > 0) && (
          <p className="xlcd-chen__canh">
            {soTre > 0 && <>{soTre} lệnh sẽ <b>trễ hạn</b>. </>}
            {soDungDo > 0 && (
              <>{soDungDo} việc lùi tới sẽ <b>đè việc của lệnh khác</b> — hệ KHÔNG đẩy tiếp, bạn tự xử.</>
            )}
          </p>
        )}
        <div className="xlcd-chen__scroll">
          <table className="xlcd-chen__tbl">
            <thead>
              <tr>
                <th>Lệnh · công đoạn</th>
                <th>Máy</th>
                <th>Giờ cũ</th>
                <th>Giờ mới</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr
                  key={r.id}
                  className={`${r.la_viec_chen ? "is-chen" : ""} ${r.tre_han ? "is-tre" : ""}`.trim()}
                >
                  <td>
                    <span className="xlcd-chen__ma">{r.lsx_ma ?? "—"}</span>{" "}
                    <span className="xlcd-chen__ten">{r.cong_doan_ten ?? ""}</span>
                    {r.la_viec_chen && <span className="xlcd-chen__tag">việc chèn</span>}
                    {r.tre_han && <span className="xlcd-chen__tag xlcd-chen__tag--tre">trễ hạn</span>}
                    {r.dung_do.length > 0 && (
                      <span className="xlcd-chen__tag xlcd-chen__tag--do"
                        title={`Đè lên: ${r.dung_do.join(", ")}`}>
                        đụng {r.dung_do.join(", ")}
                      </span>
                    )}
                  </td>
                  <td>{r.may_ten ?? "—"}</td>
                  <td className="xlcd-chen__cu">{ngayGio(r.cu)}</td>
                  <td className="xlcd-chen__moi">{ngayGio(r.moi)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </ConfirmDialog>
  );
}
