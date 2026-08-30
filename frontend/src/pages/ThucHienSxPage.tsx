// THỰC HIỆN SẢN XUẤT tại TỔ — "một bàn làm việc" (module `san_xuat`, pha đứng SAU "Xếp lịch 2").
//
// Controller bàn tổ: nhận `teamId`, giữ cửa sổ ngày + zoom + việc + việc-đang-chọn + version lạc
// quan; gọi `api.sanXuat.*`; dựng top → subbar → grid (danh sách trái · timeline giữa · drawer phải)
// → foot. Điều phối drawer + dialog lý do + toast. **KHÔNG kéo–thả** (tổ trưởng chỉ đọc lịch, ghi
// phân công / phiên chạy). Real-time qua `eventTick` (SSE mắc ở AppShell) → refetch tức thì.
//
// Ba chỗ LÝ DO bắt buộc (bám luật BE §8): Tạm dừng luôn cần `ly_do`; Bắt đầu cần `ly_do_tre` khi
// TRỄ; Kết thúc cần `ly_do_tre` khi trễ mà chưa có phiên tạm-dừng nào kèm lý do. Ghi hỏng: 403 →
// "ngoài phạm vi"; 400/khác → toast + refetch chi tiết (không mất chỗ). BE là trọng tài mốc giờ.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, api,
  type SxWorkItem, type SxWorkItemChiTiet, type SxNhanVienChon,
  type SxHoTroUngVien, type SxLyDo,
  type SxKcsChiTiet, type SxKhoChiTiet, type SxDongNhomDieuKien,
  type SxKcsHopThu, type SxKhoHopThu,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { useDebounced } from "../utils/useDebounced";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { BangLoi, EmptyState, ngay, ngayGio } from "./keHoachSxShared";
import { ngayToWall, type Xl2Zoom } from "./xl2Shared";
import { wallMinutes, nowWall } from "./gantt-time";
import { ThsxTimeline } from "./ThsxTimeline";
import { ThsxDanhSach } from "./ThsxDanhSach";
import { ThsxDrawer } from "./ThsxDrawer";
import { type ThsxExec } from "./ThsxExecPanels";
import { ThsxHopThuBar, type Opt } from "./ThsxG5";
import {
  buildThsxClusters, sxCoGio, sxDigest, sxNguonIcon, sxSerial, ThsxTrangThaiPill,
} from "./thsxShared";
import "./thuc-hien-sx.css";

// ============================ helper thuần ==================================
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function addDays(s: string, n: number): string {
  const [y, mo, d] = s.split("-").map(Number);
  return ymd(new Date(y, mo - 1, d + n));
}
/** Thứ Hai của tuần chứa `d` (đầu cửa sổ mặc định). */
function mondayOf(d: Date): string {
  const wd = d.getDay(); // 0=CN … 6=T7
  const shift = wd === 0 ? -6 : 1 - wd;
  return ymd(new Date(d.getFullYear(), d.getMonth(), d.getDate() + shift));
}
function mondayOfIso(iso: string): string {
  const [y, mo, d] = iso.slice(0, 10).split("-").map(Number);
  return mondayOf(new Date(y, mo - 1, d));
}

const ZOOMS: { key: Xl2Zoom; label: string }[] = [
  { key: "gio", label: "Giờ" },
  { key: "ca", label: "Ca" },
  { key: "ngay", label: "Ngày" },
  { key: "tuan", label: "Tuần" },
];
const WIN_SPAN = 14; // 2 tuần hiển thị / bàn
const WIN_STEP = 7;  // ◀▶ dời một tuần
const ZOOM_KEY = "thsx.zoom";

function readZoom(): Xl2Zoom {
  const s = typeof localStorage !== "undefined" ? localStorage.getItem(ZOOM_KEY) : null;
  return s === "gio" || s === "ca" || s === "ngay" || s === "tuan" ? s : "ca";
}

// Kiểu view cột giữa: "lich" (Gantt, mặc định) hay "danh_sach" (bảng — đọc/lọc nhanh nhiều việc).
type ThsxView = "lich" | "danh_sach";
const VIEW_KEY = "thsx.view";

function readView(): ThsxView {
  const s = typeof localStorage !== "undefined" ? localStorage.getItem(VIEW_KEY) : null;
  return s === "danh_sach" ? "danh_sach" : "lich";
}

type ReasonKind = "bat_dau" | "tam_dung" | "ket_thuc";
const REASON_META: Record<ReasonKind, { title: string; confirm: string; ph: string }> = {
  bat_dau: { title: "Bắt đầu trễ — nêu lý do", confirm: "Bắt đầu", ph: "Vì sao bắt đầu trễ so với dự kiến?" },
  tam_dung: { title: "Tạm dừng — nêu lý do", confirm: "Tạm dừng", ph: "Lý do tạm dừng (hết giấy, hỏng máy…)" },
  ket_thuc: { title: "Kết thúc trễ — nêu lý do", confirm: "Kết thúc", ph: "Vì sao kết thúc trễ so với dự kiến?" },
};

// Tiêu đề dialog: bắt đầu có thể vừa trễ vừa lệch số người (§7.1) → ghép động; còn lại lấy META.
function reasonTitle(r: { kind: ReasonKind; tre: boolean; soNguoi?: unknown }): string {
  if (r.kind !== "bat_dau") return REASON_META[r.kind].title;
  const phan: string[] = [];
  if (r.tre) phan.push("bắt đầu trễ");
  if (r.soNguoi) phan.push("số người khác dự kiến");
  return `Bắt đầu — ${phan.join(" · ")} — nêu lý do`;
}

// ============================ controller =====================================
export function ThucHienSxPage({
  teamId,
  tenTo,
  eventTick,
  onBadgeStale,
}: {
  teamId: number;
  tenTo?: string;
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canAssign = can("san_xuat", "assign_work");
  const canKhoRead = can("kho", "read");     // xem hộp thư kho §14
  const canKhoCreate = can("kho", "create"); // xác nhận nhập/nhận (nhân viên kho)

  const [items, setItems] = useState<SxWorkItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<SxNhanVienChon[]>([]);
  const [hoTroUngVien, setHoTroUngVien] = useState<SxHoTroUngVien[]>([]);
  const lyDoCache = useRef<Record<string, SxLyDo[]>>({});

  // ---- Giai đoạn 5: KCS §13 · Kho §14 · Đóng nhóm §16 (nạp theo việc/nhóm đang chọn) ----
  const [kcsCt, setKcsCt] = useState<SxKcsChiTiet | null>(null);
  const [khoCt, setKhoCt] = useState<SxKhoChiTiet | null>(null);
  const [dieuKien, setDieuKien] = useState<SxDongNhomDieuKien | null>(null);
  const [kcsHopThu, setKcsHopThu] = useState<SxKcsHopThu | null>(null);
  const [khoHopThu, setKhoHopThu] = useState<SxKhoHopThu | null>(null);
  const [g5Tick, setG5Tick] = useState(0); // nhịp refetch riêng cho G5 sau mỗi lệnh ghi

  const [winTu, setWinTu] = useState<string>(() => mondayOf(new Date()));
  const winDen = useMemo(() => addDays(winTu, WIN_SPAN - 1), [winTu]);
  const [zoom, setZoom] = useState<Xl2Zoom>(readZoom);
  useEffect(() => { localStorage.setItem(ZOOM_KEY, zoom); }, [zoom]);
  const [view, setView] = useState<ThsxView>(readView);
  useEffect(() => { localStorage.setItem(VIEW_KEY, view); }, [view]);

  const [q, setQ] = useState("");
  const qd = useDebounced(q, 200);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [chiTiet, setChiTiet] = useState<SxWorkItemChiTiet | null>(null);
  const [ctLoading, setCtLoading] = useState(false);

  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  // reason.tre = ô lý do CHÍNH (trễ / tạm dừng / kết thúc trễ); treBatBuoc = có bắt buộc không.
  // reason.soNguoi = §7.1 số người thực tế lệch dự kiến (chỉ khi bắt đầu) → ô lý do riêng.
  const [reason, setReason] = useState<
    { kind: ReasonKind; tre: boolean; treBatBuoc: boolean; soNguoi?: { thucTe: number; duKien: number } } | null
  >(null);
  const [reasonText, setReasonText] = useState("");
  const [reasonSoNguoiText, setReasonSoNguoiText] = useState("");

  // ---- nạp dữ liệu ----
  const loadItems = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.sanXuat.workItems(token, teamId)
      .then((r) => { setItems(r.cong_viec); setErr(null); })
      .catch((e: unknown) => setErr(e instanceof ApiError
        ? (e.isForbidden ? "Tổ này ngoài phạm vi của bạn." : e.message)
        : String(e)));
  }, [token, teamId]);

  useEffect(() => { loadItems(); }, [loadItems, eventTick]);

  // Ứng viên "Giao người" — endpoint riêng module (KHÔNG dùng api.employees vì gác quyền nhan_su).
  useEffect(() => {
    if (!token) return;
    api.sanXuat.nhanVienChon(token, teamId)
      .then((r) => setCandidates(r.nhan_vien))
      .catch(() => setCandidates([]));
  }, [token, teamId]);

  // Ứng viên HỖ TRỢ CHÉO (§9) — thợ tổ SX khác đang làm; đổi tổ → dọn cache lý do (danh mục chung, giữ được).
  useEffect(() => {
    if (!token) return;
    api.sanXuat.hoTroUngVien(token, teamId)
      .then((r) => setHoTroUngVien(r.nhan_vien))
      .catch(() => setHoTroUngVien([]));
  }, [token, teamId]);

  // Danh mục lý do/lỗi (§15) nạp-lười theo nhóm, cache trong phiên (KHÔNG hardcode danh sách ở FE).
  const loadLyDo = useCallback(async (nhom: string): Promise<SxLyDo[]> => {
    if (!token) return [];
    const c = lyDoCache.current[nhom];
    if (c) return c;
    try {
      const r = await api.sanXuat.lyDo(token, nhom);
      lyDoCache.current[nhom] = r.items;
      return r.items;
    } catch { return []; }
  }, [token]);

  // Đổi tổ → dọn lựa chọn.
  useEffect(() => { setSelectedId(null); setChiTiet(null); }, [teamId]);

  // ---- chi tiết việc đang chọn (drawer) ----
  const loadChiTiet = useCallback((id: number | null) => {
    if (!token || id == null) { setChiTiet(null); return Promise.resolve(); }
    setCtLoading(true);
    return api.sanXuat.chiTiet(token, id)
      .then((r) => { setChiTiet(r); })
      .catch(() => { setChiTiet(null); })
      .finally(() => setCtLoading(false));
  }, [token]);

  useEffect(() => { void loadChiTiet(selectedId); }, [loadChiTiet, selectedId, eventTick]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // ---- Giai đoạn 5: cờ dẫn xuất từ việc đang chọn (chỉ tin khi chi tiết khớp id) ----
  const selCv = chiTiet && chiTiet.cong_viec.id === selectedId ? chiTiet.cong_viec : null;
  const isKcs = !!selCv?.la_kcs;
  const isKcsCuoi = !!selCv?.la_kcs_cuoi;
  const selNhom = selCv?.nhom_id ?? null;

  // Tổ có thể chỉ định "chịu trách nhiệm lỗi" — gom từ ứng viên hỗ trợ chéo (không đụng quyền nhân sự).
  const toChiuOpts = useMemo<Opt[]>(() => {
    const seen = new Map<number, string>();
    for (const c of hoTroUngVien) {
      if (c.to_id != null && c.to_id !== teamId && !seen.has(c.to_id)) {
        seen.set(c.to_id, c.to_ten ?? `Tổ #${c.to_id}`);
      }
    }
    return [...seen.entries()].map(([id, ten]) => ({ id, ten }));
  }, [hoTroUngVien, teamId]);

  // Công đoạn thượng nguồn có thể gán "liên đới lỗi" — từ các bàn giao ĐẾN việc này.
  const congDoanRefOpts = useMemo<Opt[]>(() => {
    const seen = new Map<number, string>();
    for (const b of chiTiet?.ban_giao_den ?? []) {
      if (b.doi_tac_cong_viec_id != null && !seen.has(b.doi_tac_cong_viec_id)) {
        seen.set(b.doi_tac_cong_viec_id, b.doi_tac_ten);
      }
    }
    return [...seen.entries()].map(([id, ten]) => ({ id, ten }));
  }, [chiTiet]);

  // KCS §13 — mẻ kiểm tra + lỗi của việc đang chọn (chỉ bước `la_kcs`).
  useEffect(() => {
    if (!token || selectedId == null || !isKcs) { setKcsCt(null); return; }
    let alive = true;
    api.sanXuat.kcsChiTiet(token, selectedId)
      .then((r) => { if (alive) setKcsCt(r); })
      .catch(() => { if (alive) setKcsCt(null); });
    return () => { alive = false; };
  }, [token, selectedId, isKcs, eventTick, g5Tick]);

  // Kho §14 — yêu cầu nhập + BTP dư của NHÓM (bước KCS thuộc một nhóm thành phẩm).
  useEffect(() => {
    if (!token || selNhom == null || !isKcs) { setKhoCt(null); return; }
    let alive = true;
    api.sanXuat.khoChiTietNhom(token, selNhom)
      .then((r) => { if (alive) setKhoCt(r); })
      .catch(() => { if (alive) setKhoCt(null); });
    return () => { alive = false; };
  }, [token, selNhom, isKcs, eventTick, g5Tick]);

  // §16/§13.3 — checklist cổng đóng nhóm (chỉ ở KCS CUỐI của nhóm).
  useEffect(() => {
    if (!token || selNhom == null || !isKcsCuoi) { setDieuKien(null); return; }
    let alive = true;
    api.sanXuat.dieuKienDongNhom(token, selNhom)
      .then((r) => { if (alive) setDieuKien(r); })
      .catch(() => { if (alive) setDieuKien(null); });
    return () => { alive = false; };
  }, [token, selNhom, isKcsCuoi, eventTick, g5Tick]);

  // Hộp thư LỖI KCS — việc tổ mình bị yêu cầu nhận/từ chối (server lọc theo tổ trưởng đang đăng nhập).
  useEffect(() => {
    if (!token) { setKcsHopThu(null); return; }
    let alive = true;
    api.sanXuat.kcsHopThu(token)
      .then((r) => { if (alive) setKcsHopThu(r); })
      .catch(() => { if (alive) setKcsHopThu(null); });
    return () => { alive = false; };
  }, [token, teamId, eventTick, g5Tick]);

  // Hộp thư KHO — yêu cầu nhập/nhận chờ xác nhận (chỉ khi có quyền đọc kho).
  useEffect(() => {
    if (!token || !canKhoRead) { setKhoHopThu(null); return; }
    let alive = true;
    api.sanXuat.khoHopThu(token)
      .then((r) => { if (alive) setKhoHopThu(r); })
      .catch(() => { if (alive) setKhoHopThu(null); });
    return () => { alive = false; };
  }, [token, canKhoRead, eventTick, g5Tick]);

  // ---- lọc + gom nhóm cột trái / cluster timeline ----
  const winStartW = useMemo(() => ngayToWall(winTu), [winTu]);
  const winEndW = useMemo(() => ngayToWall(winDen) + 1440, [winDen]);

  const overlaps = useCallback((w: SxWorkItem): boolean => {
    if (!sxCoGio(w)) return false;
    const s = wallMinutes(w.du_kien_bat_dau as string);
    const e = wallMinutes(w.du_kien_ket_thuc as string);
    if (!Number.isFinite(s) || !Number.isFinite(e)) return false;
    return s < winEndW && e > winStartW;
  }, [winStartW, winEndW]);

  const match = useCallback((w: SxWorkItem): boolean => {
    const kw = qd.trim().toLowerCase();
    if (!kw) return true;
    return [w.nguon_ma, w.ten_cong_doan, w.may, w.nguon_ten]
      .some((s) => (s || "").toLowerCase().includes(kw));
  }, [qd]);

  const startW = (w: SxWorkItem) => wallMinutes(w.du_kien_bat_dau as string);
  const groups = useMemo(() => {
    const filtered = (items ?? []).filter(match);
    const timed = filtered.filter(overlaps).sort((a, b) => startW(a) - startW(b));
    const outWin = filtered.filter((w) => sxCoGio(w) && !overlaps(w)).sort((a, b) => startW(a) - startW(b));
    const untimed = filtered.filter((w) => !sxCoGio(w));
    return { tong: filtered.length, timed, outWin, untimed };
  }, [items, match, overlaps]);

  const clusters = useMemo(() => buildThsxClusters(groups.timed), [groups.timed]);
  const digest = useMemo(() => sxDigest(items ?? []), [items]);

  // ---- chọn việc: mở drawer + (nếu ngoài cửa sổ) dời cửa sổ tới tuần của việc ----
  const pickViec = useCallback((w: SxWorkItem) => {
    if (sxCoGio(w) && !overlaps(w)) setWinTu(mondayOfIso(w.du_kien_bat_dau as string));
    setSelectedId(w.id);
  }, [overlaps]);
  const closePanel = useCallback(() => setSelectedId(null), []);

  // ---- ghi (khoá lạc quan) ----
  const handleErr = useCallback((e: unknown) => {
    if (e instanceof ApiError) {
      if (e.isForbidden) { setToast("Ngoài phạm vi — bạn không thao tác được việc này."); return; }
      setToast(e.message || "Không lưu được — đã tải lại bản mới.");
      void loadChiTiet(selectedId);
      return;
    }
    setToast("Lỗi mạng — thử lại.");
  }, [loadChiTiet, selectedId]);

  const mutate = useCallback(async <T,>(run: () => Promise<T>, ok: string): Promise<T | null> => {
    if (!token || selectedId == null) return null;
    setBusy(true);
    try {
      const r = await run();
      setReason(null);
      setReasonText("");
      await loadChiTiet(selectedId);
      loadItems();
      onBadgeStale?.();
      setToast(ok);
      return r;
    } catch (e) {
      handleErr(e);
      return null;
    } finally { setBusy(false); }
  }, [token, selectedId, loadChiTiet, loadItems, onBadgeStale, handleErr]);

  // Ghi G5 trong DRAWER (cần việc đang chọn): refetch chi tiết + việc + nhịp G5; badge tổ nháy.
  const mutateG5 = useCallback(async (run: () => Promise<unknown>, ok: string): Promise<boolean> => {
    if (!token || selectedId == null) return false;
    setBusy(true);
    try {
      await run();
      await loadChiTiet(selectedId);
      loadItems();
      onBadgeStale?.();
      setToast(ok);
      return true;
    } catch (e) {
      handleErr(e);
      return false;
    } finally {
      setBusy(false);
      setG5Tick((t) => t + 1);
    }
  }, [token, selectedId, loadChiTiet, loadItems, onBadgeStale, handleErr]);

  // Ghi từ HỘP THƯ mức trang (không cần drawer): phản hồi lỗi · kho xác nhận nhập/nhận.
  const mutateInbox = useCallback(async (run: () => Promise<unknown>, ok: string): Promise<boolean> => {
    if (!token) return false;
    setBusy(true);
    try {
      await run();
      if (selectedId != null) await loadChiTiet(selectedId);
      loadItems();
      onBadgeStale?.();
      setToast(ok);
      return true;
    } catch (e) {
      handleErr(e);
      return false;
    } finally {
      setBusy(false);
      setG5Tick((t) => t + 1);
    }
  }, [token, selectedId, loadChiTiet, loadItems, onBadgeStale, handleErr]);

  const onPhanHoiLoi = useCallback((loiId: number, chapNhan: boolean, lyDo: string | null, version: number) => {
    void mutateInbox(() => api.sanXuat.phanHoiLoiKcs(token!, loiId, {
      chap_nhan: chapNhan, ly_do_tu_choi: lyDo, expected_version: version,
    }), chapNhan ? "Đã nhận trách nhiệm lỗi." : "Đã từ chối lỗi.");
  }, [mutateInbox, token]);

  const onKhoXacNhanNhap = useCallback((ycId: number, soLuong: number, version: number) => {
    void mutateInbox(() => api.sanXuat.khoXacNhanNhap(token!, ycId, {
      so_luong: soLuong, expected_version: version,
    }), "Kho đã xác nhận nhập.");
  }, [mutateInbox, token]);

  const onKhoXacNhanBtp = useCallback((lotId: number) => {
    void mutateInbox(() => api.sanXuat.khoXacNhanBtp(token!, lotId), "Kho đã nhận BTP.");
  }, [mutateInbox, token]);

  const ver = () => chiTiet?.version;

  const onGiao = useCallback((employeeId: number) => {
    if (selectedId == null) return;
    void mutate(() => api.sanXuat.phanCong(token!, selectedId, { employee_id: employeeId, expected_version: ver() }),
      "Đã giao người vào việc.");
  }, [mutate, token, selectedId, chiTiet]);

  const onRut = useCallback((phanCongId: number) => {
    if (selectedId == null) return;
    void mutate(() => api.sanXuat.rut(token!, phanCongId, { expected_version: ver() }),
      "Đã rút người khỏi việc.");
  }, [mutate, token, selectedId, chiTiet]);

  // Bắt đầu: TRỄ (§7.2) và/hoặc số người thực tế ≠ dự kiến (§7.1) → hỏi lý do; khớp giờ+người → thẳng.
  const onBatDau = useCallback(() => {
    const cv = chiTiet?.cong_viec;
    const late = !!cv?.du_kien_bat_dau && nowWall() > wallMinutes(cv.du_kien_bat_dau);
    // Roster active phải đếm y hệt backend (SanXuatPhanCong trạng thái "active").
    const rosterActive = (chiTiet?.phan_cong ?? []).filter((p) => p.trang_thai === "active").length;
    const duKien = cv?.du_kien_so_nguoi ?? null;
    const lech = duKien != null && rosterActive !== duKien;
    if (late || lech) {
      setReasonText("");
      setReasonSoNguoiText("");
      setReason({
        kind: "bat_dau",
        tre: late,
        treBatBuoc: late,
        soNguoi: lech ? { thucTe: rosterActive, duKien: duKien! } : undefined,
      });
      return;
    }
    if (selectedId != null) void mutate(() => api.sanXuat.batDau(token!, selectedId, { expected_version: ver() }), "Đã bắt đầu.");
  }, [chiTiet, mutate, token, selectedId]);

  // Tạm dừng: lý do BẮT BUỘC luôn.
  const onTamDung = useCallback(() => {
    setReasonText("");
    setReason({ kind: "tam_dung", tre: true, treBatBuoc: true });
  }, []);

  // Kết thúc: TRỄ → hỏi lý do (bắt buộc nếu chưa có phiên tạm-dừng nào kèm lý do); đúng giờ → thẳng.
  const onKetThuc = useCallback(() => {
    const cv = chiTiet?.cong_viec;
    const late = !!cv?.du_kien_ket_thuc && nowWall() > wallMinutes(cv.du_kien_ket_thuc);
    const daCoLyDoDung = (chiTiet?.phien_chay ?? []).some((p) => p.loai_dong === "tam_dung" && !!p.ly_do);
    if (late) { setReasonText(""); setReason({ kind: "ket_thuc", tre: true, treBatBuoc: !daCoLyDoDung }); return; }
    if (selectedId != null) void mutate(() => api.sanXuat.ketThuc(token!, selectedId, { expected_version: ver() }), "Đã kết thúc.");
  }, [chiTiet, mutate, token, selectedId]);

  const confirmReason = useCallback(() => {
    if (!reason || selectedId == null) return;
    const txt = reasonText.trim();
    const soNguoiTxt = reasonSoNguoiText.trim();
    if (reason.kind === "tam_dung") {
      void mutate(() => api.sanXuat.tamDung(token!, selectedId, { ly_do: txt, expected_version: ver() }), "Đã tạm dừng.");
    } else if (reason.kind === "bat_dau") {
      void mutate(() => api.sanXuat.batDau(token!, selectedId, {
        ly_do_tre: reason.tre ? (txt || null) : null,
        ly_do_so_nguoi: reason.soNguoi ? (soNguoiTxt || null) : null,
        expected_version: ver(),
      }), "Đã bắt đầu.");
    } else {
      void mutate(() => api.sanXuat.ketThuc(token!, selectedId, { ly_do_tre: txt || null, expected_version: ver() }), "Đã kết thúc.");
    }
  }, [reason, reasonText, reasonSoNguoiText, mutate, token, selectedId, chiTiet]);

  // ---- Giai đoạn 3+4: hợp đồng các mặt GHI cho drawer (mọi mặt qua `mutate` → refetch + toast) ----
  const exec = useMemo<ThsxExec>(() => {
    const ok = (p: Promise<unknown | null>) => p.then((r) => r != null);
    return {
      taoBatch: (b) => mutate(() => api.sanXuat.taoBatch(token!, selectedId!, b), "Đã ghi mẻ sản lượng.")
        .then((r) => (r ? r.ket_qua_lsx ?? [] : null)),
      deXuatBanGiao: (b) => ok(mutate(() => api.sanXuat.deXuatBanGiao(token!, selectedId!, b), "Đã đề xuất bàn giao.")),
      suaBanGiao: (id, b) => ok(mutate(() => api.sanXuat.suaBanGiao(token!, id, b), "Đã sửa số lượng bàn giao.")),
      xacNhanBanGiao: (id, v) => ok(mutate(() => api.sanXuat.xacNhanBanGiao(token!, id, { expected_version: v }), "Đã xác nhận bàn giao.")),
      dieuChinhBanGiao: (id, b) => ok(mutate(() => api.sanXuat.dieuChinhBanGiao(token!, id, b), "Đã điều chỉnh bàn giao.")),
      xacNhanVatTu: (voucherId) => ok(mutate(() => api.sanXuat.xacNhanVatTu(token!, { voucher_id: voucherId, department_id: teamId }), "Đã xác nhận nhận vật tư.")),
      deXuatHoTro: (b) => ok(mutate(() => api.sanXuat.deXuatHoTro(token!, selectedId!, b), "Đã đề xuất hỗ trợ.")),
      xacNhanHoTro: (id, v) => ok(mutate(() => api.sanXuat.xacNhanHoTro(token!, id, { expected_version: v }), "Đã xác nhận hỗ trợ.")),
      huyHoTro: (id, lyDo, v) => ok(mutate(() => api.sanXuat.huyHoTro(token!, id, { ly_do: lyDo || null, expected_version: v }), "Đã huỷ hỗ trợ.")),
      tinhPhanBo: (batchId) => ok(mutate(() => api.sanXuat.tinhPhanBo(token!, batchId), "Đã tính phân bổ lương.")),
      chotPhanBo: (phanBoId, v) => ok(mutate(() => api.sanXuat.chotPhanBo(token!, phanBoId, { expected_version: v }), "Đã chốt phân bổ.")),
      moLaiPhanBo: (phanBoId, lyDoId, v) => ok(mutate(() => api.sanXuat.moLaiPhanBo(token!, phanBoId, { ly_do_id: lyDoId, expected_version: v }), "Đã mở lại phân bổ.")),
      buTru: (batchId, b) => ok(mutate(() => api.sanXuat.buTru(token!, batchId, b), "Đã ghi bù trừ.")),
      loaiTru: (batchId, b) => ok(mutate(() => api.sanXuat.loaiTru(token!, batchId, b), "Đã loại khỏi lương batch.")),
      goLoaiTru: (batchId, b) => ok(mutate(() => api.sanXuat.goLoaiTru(token!, batchId, b), "Đã gỡ loại trừ.")),
      // Giai đoạn 5 — KCS §13 · Kho §14 · Đóng nhóm §16/§13.3 (đi qua `mutateG5`).
      taoBatchKcs: (cvId, b) => mutateG5(() => api.sanXuat.taoBatchKcs(token!, cvId, b), "Đã ghi mẻ kiểm tra KCS."),
      ghiLoiKcs: (batchId, b) => mutateG5(() => api.sanXuat.ghiLoiKcs(token!, batchId, b), "Đã ghi lỗi KCS."),
      themAnhLoiKcs: (loiId, files) => mutateG5(() => api.sanXuat.themAnhLoiKcs(token!, loiId, files), "Đã thêm ảnh lỗi."),
      xoaAnhKcs: (anhId) => mutateG5(() => api.sanXuat.xoaAnhKcs(token!, anhId), "Đã xoá ảnh."),
      taoYeuCauNhap: (b) => mutateG5(() => api.sanXuat.taoYeuCauNhap(token!, b), "Đã gửi yêu cầu nhập kho."),
      huyPhanChuaNhan: (ycId, b) => mutateG5(() => api.sanXuat.huyPhanChuaNhan(token!, ycId, b), "Đã huỷ phần chưa nhận."),
      phanLoaiBtp: (b) => mutateG5(() => api.sanXuat.phanLoaiBtp(token!, b), "Đã ghi phân loại BTP."),
      dongThieu: (nhomId, b) => mutateG5(() => api.sanXuat.dongThieu(token!, nhomId, b), "Đã đóng thiếu nhóm."),
    };
  }, [mutate, mutateG5, token, selectedId, teamId]);

  const panelOpen = selectedId != null;

  // ============================ render =======================================
  return (
    <div className="thsx">
      {/* Thanh trên */}
      <div className="thsx-top">
        <div className="thsx-top__title">
          <Icon name="users" size={20} />
          <span>Bàn tổ · {tenTo ?? `#${teamId}`}</span>
        </div>
        <div className="thsx-top__spacer" />
        <div className="thsx-top__grp">
          <button type="button" className="thsx-iconbtn" title="Tuần trước" aria-label="Tuần trước"
            onClick={() => setWinTu((s) => addDays(s, -WIN_STEP))}>
            <Icon name="chevron" size={16} className="thsx-rot180" />
          </button>
          <span className="thsx-top__win">
            <b>{ngay(winTu)}</b> — <b>{ngay(winDen)}</b>
          </span>
          <button type="button" className="thsx-iconbtn" title="Tuần sau" aria-label="Tuần sau"
            onClick={() => setWinTu((s) => addDays(s, WIN_STEP))}>
            <Icon name="chevron" size={16} />
          </button>
          <button type="button" className="thsx-iconbtn" title="Về tuần này" aria-label="Về tuần này"
            onClick={() => setWinTu(mondayOf(new Date()))}>
            <Icon name="refresh" size={15} />
          </button>
        </div>
        <div className="thsx-seg" role="group" aria-label="Kiểu xem">
          <button type="button" className="thsx-seg__btn" title="Xem theo lịch (Gantt)"
            aria-pressed={view === "lich"} onClick={() => setView("lich")}>
            <Icon name="layout" size={13} /> Lịch
          </button>
          <button type="button" className="thsx-seg__btn" title="Xem danh sách bản ghi"
            aria-pressed={view === "danh_sach"} onClick={() => setView("danh_sach")}>
            <Icon name="table" size={13} /> Danh sách
          </button>
        </div>
        {view === "lich" && (
          <div className="thsx-seg" role="group" aria-label="Mật độ trục thời gian">
            {ZOOMS.map((z) => (
              <button key={z.key} type="button" className="thsx-seg__btn"
                aria-pressed={zoom === z.key} onClick={() => setZoom(z.key)}>
                {z.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Thanh phụ: tìm + digest */}
      <div className="thsx-subbar">
        <div className="thsx-search">
          <Icon name="search" size={15} className="thsx-search__ic" />
          <input type="search" className="thsx-search__in" value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã / công đoạn / máy…" aria-label="Tìm trong việc của tổ" />
          {q && (
            <button type="button" className="thsx-search__clear" aria-label="Xoá tìm" onClick={() => setQ("")}>
              <Icon name="x" size={13} />
            </button>
          )}
        </div>
        <div className="thsx-subbar__spacer" />
        <div className="thsx-digest" aria-label="Tổng quan việc của tổ">
          <span className="thsx-digest__chip"><Icon name="clipboard" size={12} /> <b className="thsx-num">{digest.tong}</b> việc</span>
          <span className="thsx-digest__chip thsx-digest__chip--run"><Icon name="play" size={12} /> <b className="thsx-num">{digest.running}</b> đang chạy</span>
          <span className="thsx-digest__chip thsx-digest__chip--pause"><Icon name="pause" size={12} /> <b className="thsx-num">{digest.paused}</b> tạm dừng</span>
          <span className="thsx-digest__chip"><Icon name="clock" size={12} /> <b className="thsx-num">{digest.released}</b> chờ làm</span>
          <span className="thsx-digest__chip thsx-digest__chip--done"><Icon name="check" size={12} /> <b className="thsx-num">{digest.completed}</b> xong</span>
        </div>
      </div>

      {/* Hộp thư mức trang (§13/§14) — chỉ hiện khi CÓ việc chờ; real-time qua eventTick/g5Tick */}
      <ThsxHopThuBar
        kcsItems={kcsHopThu?.loi ?? []}
        khoHopThu={khoHopThu}
        canKhoRead={canKhoRead}
        canKhoCreate={canKhoCreate}
        busy={busy}
        onPhanHoiLoi={onPhanHoiLoi}
        onKhoXacNhanNhap={onKhoXacNhanNhap}
        onKhoXacNhanBtp={onKhoXacNhanBtp}
      />

      {/* Lưới 3 cột */}
      <div className={`thsx-grid${panelOpen ? " is-panel" : ""}`}>
        {/* CỘT TRÁI — danh sách việc của tổ */}
        <aside className="thsx-list">
          <div className="thsx-list__head">
            <Icon name="clipboard" size={16} />
            <h2>Việc của tổ</h2>
            <span className="thsx-list__count thsx-num">{groups.tong}</span>
          </div>
          <div className="thsx-list__body">
            {err ? (
              <div className="thsx-list__pad"><BangLoi text={err} onRetry={loadItems} /></div>
            ) : items == null ? (
              <ListSkeleton />
            ) : groups.tong === 0 ? (
              <EmptyState icon={q ? "search" : "check"}
                title={q ? "Không khớp tìm kiếm" : "Chưa có việc phát hành"}
                sub={q ? "Thử đổi từ khoá." : "Khi một gói được phát hành, việc của tổ sẽ hiện ở đây."} />
            ) : (
              <>
                <ListSection label="Trong cửa sổ" icon="calendar" viec={groups.timed}
                  selectedId={selectedId} onPick={pickViec} />
                <ListSection label="Ngoài cửa sổ" icon="history" viec={groups.outWin}
                  selectedId={selectedId} onPick={pickViec} />
                <ListSection label="Chưa định giờ" icon="clock" viec={groups.untimed}
                  selectedId={selectedId} onPick={pickViec} />
              </>
            )}
          </div>
        </aside>

        {/* CỘT GIỮA — timeline (Gantt) hoặc bảng (Danh sách) */}
        <section className="thsx-center thsx-col--center">
          {err ? (
            <div className="thsx-centerempty"><BangLoi text={err} onRetry={loadItems} /></div>
          ) : items == null ? (
            view === "danh_sach" ? <ListSkeleton /> : <TimelineSkeleton />
          ) : view === "danh_sach" ? (
            groups.tong === 0 ? (
              <div className="thsx-centerempty">
                <EmptyState icon={q ? "search" : "check"}
                  title={q ? "Không khớp tìm kiếm" : "Chưa có việc phát hành"}
                  sub={q ? "Thử đổi từ khoá." : "Khi một gói được phát hành, việc của tổ sẽ hiện ở đây."} />
              </div>
            ) : (
              <ThsxDanhSach
                timed={groups.timed}
                outWin={groups.outWin}
                untimed={groups.untimed}
                selectedId={selectedId}
                onPick={pickViec}
              />
            )
          ) : clusters.length === 0 ? (
            <div className="thsx-centerempty">
              <EmptyState icon="calendar" title="Không có việc định giờ trong cửa sổ này"
                sub="Dời cửa sổ ngày, hoặc chọn một việc 'chưa định giờ' ở cột trái để xem chi tiết." />
            </div>
          ) : (
            <ThsxTimeline
              clusters={clusters}
              winTu={winTu}
              winDen={winDen}
              zoom={zoom}
              selectedId={selectedId}
              onChonViec={setSelectedId}
            />
          )}
        </section>

        {/* CỘT PHẢI — drawer chi tiết */}
        <aside className={`thsx-panel${panelOpen ? " thsx-panel--open" : ""}`}
          aria-label="Chi tiết công việc đang chọn">
          {panelOpen && (
            <ThsxDrawer
              chiTiet={chiTiet}
              loading={ctLoading}
              canAssign={canAssign}
              candidates={candidates}
              hoTroUngVien={hoTroUngVien}
              loadLyDo={loadLyDo}
              exec={exec}
              busy={busy}
              kcsCt={kcsCt}
              khoCt={khoCt}
              dieuKien={dieuKien}
              toChiuOpts={toChiuOpts}
              congDoanRefOpts={congDoanRefOpts}
              onGiao={onGiao}
              onRut={onRut}
              onBatDau={onBatDau}
              onTamDung={onTamDung}
              onKetThuc={onKetThuc}
              onClose={closePanel}
            />
          )}
        </aside>
      </div>

      {/* Nền mờ đóng drawer (chỉ hiện trên màn hẹp qua CSS) */}
      {panelOpen && <div className="thsx-scrim" onClick={closePanel} aria-hidden="true" />}

      {/* Dải chân — chú giải trạng thái + cửa sổ */}
      <div className="thsx-foot">
        <div className="thsx-foot__legend" aria-hidden="true">
          <span className="thsx-lg thsx-lg--released"><i /> Chờ làm</span>
          <span className="thsx-lg thsx-lg--running"><i /> Đang chạy</span>
          <span className="thsx-lg thsx-lg--paused"><i /> Tạm dừng</span>
          <span className="thsx-lg thsx-lg--completed"><i /> Hoàn thành</span>
          <span className="thsx-lg thsx-lg--actual"><i /> Thực tế</span>
        </div>
        <div className="thsx-foot__spacer" />
        <div className="thsx-foot__hint">
          <Icon name="calendar" size={14} />
          <span className="thsx-num">{ngay(winTu)} — {ngay(winDen)}</span>
          <span className="thsx-foot__dot">·</span>
          {ZOOMS.find((z) => z.key === zoom)?.label}
        </div>
      </div>

      {/* Dialog lý do (§8): ô CHÍNH (trễ/tạm dừng) + ô §7.1 lệch số người khi bắt đầu */}
      <ConfirmDialog
        open={!!reason}
        title={reason ? <span><Icon name="alert" size={16} /> {reasonTitle(reason)}</span> : ""}
        confirmLabel={reason ? REASON_META[reason.kind].confirm : "Xác nhận"}
        confirmDisabled={
          !!reason && (
            (reason.tre && reason.treBatBuoc && reasonText.trim() === "") ||
            (!!reason.soNguoi && reasonSoNguoiText.trim() === "")
          )
        }
        busy={busy}
        onConfirm={confirmReason}
        onCancel={() => { setReason(null); setReasonText(""); setReasonSoNguoiText(""); }}
      >
        {reason && (
          <div className="thsx-dlg-fields">
            {reason.soNguoi && (
              <label className="thsx-dlg-field">
                <span className="thsx-dlg-field__lb">
                  Số người thực tế <b className="thsx-num">{reason.soNguoi.thucTe}</b> ≠ dự kiến{" "}
                  <b className="thsx-num">{reason.soNguoi.duKien}</b> — nêu lý do
                </span>
                <textarea className="thsx-dlg-reason" autoFocus
                  placeholder="Vì sao khác số người dự kiến? (thợ nghỉ, ghép thêm hỗ trợ…)"
                  value={reasonSoNguoiText} onChange={(e) => setReasonSoNguoiText(e.target.value)} />
              </label>
            )}
            {reason.tre && (
              <label className="thsx-dlg-field">
                {reason.soNguoi && <span className="thsx-dlg-field__lb">{REASON_META[reason.kind].title}</span>}
                <textarea className="thsx-dlg-reason" autoFocus={!reason.soNguoi}
                  placeholder={REASON_META[reason.kind].ph}
                  value={reasonText} onChange={(e) => setReasonText(e.target.value)} />
              </label>
            )}
          </div>
        )}
      </ConfirmDialog>

      {toast && <div className="thsx-toast" role="status">{toast}</div>}
    </div>
  );
}

// ============================ danh sách trái — 1 nhóm ======================
function ListSection({
  label, icon, viec, selectedId, onPick,
}: {
  label: string;
  icon: Parameters<typeof Icon>[0]["name"];
  viec: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
}) {
  if (viec.length === 0) return null;
  return (
    <div className="thsx-lsec">
      <div className="thsx-lsec__label">
        <Icon name={icon} size={12} /> {label}
        <span className="thsx-lsec__n thsx-num">{viec.length}</span>
      </div>
      {viec.map((w) => (
        <ListRow key={w.id} w={w} selected={w.id === selectedId} onPick={() => onPick(w)} />
      ))}
    </div>
  );
}

function ListRow({ w, selected, onPick }: { w: SxWorkItem; selected: boolean; onPick: () => void }) {
  return (
    <button type="button" className={`thsx-lrow${selected ? " thsx-lrow--sel" : ""}`}
      aria-pressed={selected} onClick={onPick}>
      <div className="thsx-lrow__top">
        <Icon name={sxNguonIcon(w.nguon_loai)} size={13} className="thsx-lrow__nic" />
        <span className="thsx-lrow__serial thsx-num">{sxSerial(w.nguon_ma)}</span>
        <span className="thsx-lrow__spacer" />
        <ThsxTrangThaiPill tt={w.trang_thai} size="xs" />
      </div>
      <div className="thsx-lrow__cd">{w.ten_cong_doan || "—"}</div>
      <div className="thsx-lrow__meta">
        {w.may && <span className="thsx-lrow__may"><Icon name="printer" size={11} /> {w.may}</span>}
        {w.du_kien_bat_dau && (
          <span className="thsx-lrow__gio thsx-num"><Icon name="clock" size={11} /> {ngayGio(w.du_kien_bat_dau)}</span>
        )}
        {w.la_kcs && <span className="thsx-lrow__kcs">KCS</span>}
      </div>
    </button>
  );
}

// ============================ skeleton lúc tải ==============================
function TimelineSkeleton() {
  const rows: [number, number][] = [
    [8, 42], [26, 30], [4, 54], [36, 28], [12, 46], [30, 34], [6, 50], [20, 38],
  ];
  return (
    <div className="thsx-skel" role="status" aria-label="Đang tải bàn làm việc">
      {rows.map(([off, w], i) => (
        <div className="thsx-skel__row" key={i}>
          <div className="thsx-skel__lbl" />
          <div className="thsx-skel__bar" style={{ marginLeft: `${off}%`, width: `${w}%` }} />
        </div>
      ))}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="thsx-skel-q" role="status" aria-label="Đang tải danh sách việc">
      {[0, 1, 2, 3].map((i) => <div className="thsx-skel__q" key={i} />)}
    </div>
  );
}
