// Khối Phân ca tháng + Lịch sử đổi ca (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type EmployeeShiftAssignment,
  type ShiftChange,
  type ShiftPlanMonth,
  type ShiftPlanDay,
  type ShiftPlanRow,
  type ShiftPlanPatchItem,
} from "../../../../api/client";
import {
  AlertTriangle,
  RefreshCw,
  Trash2,
  Lock,
  ChevronLeft,
  ChevronRight,
  Search,
  Save,
  Undo2,
  Eraser,
  Users,
  Repeat,
} from "lucide-react";
import { EmptyState } from "../../../../components/EmptyState";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import {
  DiscardChangesDialog,
} from "../../../../components/DiscardChangesDialog";
import {
  fmtDateTime,
  isoToday,
  fmtYmd,
  fmtDateVN,
  stripTones,
  buildShiftMeta,
  getWeekdayLabel,
  isWeekend,
  getInitials,
  elErr,
} from "../shared/helpers";

// --- Lưới phân ca tháng ------------------------------------------------------
type Brush =
  | { kind: "shift"; shiftId: number }
  | { kind: "off" }
  | { kind: "inherit" };
interface EffCell {
  shiftId: number | null;
  hand: boolean;
  off: boolean;
}
interface DragRect {
  r0: number;
  c0: number;
  r1: number;
  c1: number;
}

const DENSITY_KEY = "cc-sp-density";
const SAVE_CHUNK = 500;
// Dải xem trước trong modal "Áp nhanh" — chỉ để mắt thấy các kíp có lệch nhau thật không.
const QF_STRIP_ROWS = 4;
const QF_STRIP_DAYS = 14;

function ymd(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
function cellKey(employeeId: number, date: string): string {
  return `${employeeId}:${date}`;
}

/** Giá trị KẾ THỪA của từng ngày (ca nền) — suy từ chính các ô server trả về `source !== "day"`.
 *  Cần cho lúc người dùng bấm "Mặc định ⌫": biết trước ô sẽ rơi về ca nào mà không phải gọi lại API. */
function inheritOfRow(
  row: ShiftPlanRow,
  cal: ShiftPlanDay[],
): { inherit: (number | null)[]; base: number | null } {
  const n = cal.length;
  const arr: (number | null)[] = new Array(n).fill(null);
  const known: boolean[] = new Array(n).fill(false);
  cal.forEach((c, i) => {
    const cell = row.days[String(c.day)];
    if (cell && cell.source !== "day") {
      arr[i] = cell.shift_id;
      known[i] = true;
    }
  });
  let last: number | null = null;
  let seen = false;
  for (let i = 0; i < n; i++) {
    if (known[i]) {
      last = arr[i];
      seen = true;
    } else if (seen) arr[i] = last;
  }
  const first = known.indexOf(true);
  if (first > 0) for (let i = 0; i < first; i++) arr[i] = arr[first];
  const freq = new Map<number, number>();
  for (const v of arr) if (v != null) freq.set(v, (freq.get(v) ?? 0) + 1);
  let base: number | null = null;
  let bestCount = 0;
  freq.forEach((count, id) => {
    if (count > bestCount) {
      bestCount = count;
      base = id;
    }
  });
  return { inherit: arr, base };
}

// --- Áp nhanh: lặp một mẫu xoay ca cho cả tổ ---------------------------------
/** Mẫu xoay ca = danh sách BƯỚC, mỗi bước là MỘT NGÀY trong chu kỳ.
 *  Xưởng 3 ca chạy 2-2-2 thì mẫu là [C1, C1, C2, C2, K, K].
 *  `phase` = số bước người kế tiếp bắt đầu MUỘN HƠN người liền trước — nhờ đó các
 *  kíp lệch nhau và ngày nào cũng có người đủ ở cả 3 ca. */
interface RotationPlan {
  pattern: Brush[];
  startDay: number; // ngày trong tháng bắt đầu tô (1..số ngày)
  phase: number; // số bước lệch giữa hai người liền nhau
  skipRest: boolean; // bỏ trắng ngày nghỉ tuần / lễ
}

/** Rải mẫu lên từng người theo ĐÚNG THỨ TỰ ĐANG HIỂN THỊ trên lưới.
 *  Hàm thuần: không đụng state, mọi việc ghi đẩy hết qua `paint` (ở màn này là `applyBrush`). */
function runRotation(
  rows: ShiftPlanRow[],
  cal: ShiftPlanDay[],
  plan: RotationPlan,
  paint: (row: ShiftPlanRow, day: ShiftPlanDay, brush: Brush) => void,
): void {
  const len = plan.pattern.length;
  if (len === 0 || rows.length === 0) return;
  const step = ((Math.trunc(plan.phase) % len) + len) % len;
  rows.forEach((row, i) => {
    let pos = (i * step) % len;
    for (const c of cal) {
      if (c.day < plan.startDay) continue;
      // Ngày bỏ qua thì KHÔNG tiêu 1 bước — tăng pos ở đây là lệch cả chu kỳ về sau.
      if (plan.skipRest && !c.is_working) continue;
      const b = plan.pattern[pos % len];
      pos += 1;
      if (b) paint(row, c, b);
    }
  });
}

/** Số ô THỰC SỰ đổi so với nháp đang giữ (thêm mới · bỏ đi · đổi giá trị).
 *  Tô đè đúng giá trị đang có thì không tính — con số khoe trên modal phải là số thật. */
function countPatchDiff(
  before: Map<string, ShiftPlanPatchItem>,
  after: Map<string, ShiftPlanPatchItem>,
): number {
  let n = 0;
  after.forEach((v, k) => {
    const b = before.get(k);
    if (
      !b ||
      b.action !== v.action ||
      (b.shift_id ?? null) !== (v.shift_id ?? null)
    )
      n += 1;
  });
  before.forEach((_, k) => {
    if (!after.has(k)) n += 1;
  });
  return n;
}

/** Ô nhập số: kẹp về khoảng cho phép ngay khi gõ, khỏi lọt giá trị vô nghĩa vào mẫu. */
function clampNum(raw: string, lo: number, hi: number): number {
  const n = Math.trunc(Number(raw));
  if (!Number.isFinite(n)) return lo;
  return Math.min(hi, Math.max(lo, n));
}

// Họp 28/07: tạm ẩn nút "Áp nhanh" (rải ca cả tháng theo chu kỳ). Hàm openQuickFill + modal
// giữ nguyên, bật lại = đổi cờ này thành true. ĐỪNG comment-out khối JSX để ẩn: làm vậy thì
// openQuickFill và icon Repeat thành mồ côi → tsc gãy vì noUnusedLocals (đúng lỗi CI 29/07).
const SHOW_QUICK_FILL: boolean = false;

export function ShiftPlanPanel({ token }: { token: string }) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  });
  const { year, month } = ym;
  const [deptId, setDeptId] = useState<number | "">("");
  const [depts, setDepts] = useState<{ id: number; name: string }[]>([]);
  const [q, setQ] = useState("");
  const [density, setDensity] = useState<"compact" | "roomy">(() =>
    localStorage.getItem(DENSITY_KEY) === "roomy" ? "roomy" : "compact",
  );
  const [data, setData] = useState<ShiftPlanMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [brush, setBrush] = useState<Brush | null>(null);
  const [pending, setPending] = useState<Map<string, ShiftPlanPatchItem>>(
    () => new Map(),
  );
  const [rejects, setRejects] = useState<Map<string, string>>(() => new Map());
  const [drag, setDrag] = useState<DragRect | null>(null);
  // Nhắc khi tô một loạt bỏ qua ngày nghỉ tuần (theo lịch tuần) — người dùng khỏi tưởng hụt ô.
  const [boQuaNghi, setBoQuaNghi] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);
  const [result, setResult] = useState<{
    saved: number;
    cleared: number;
    rejected: number;
  } | null>(null);
  const [guard, setGuard] = useState<{ run: () => void } | null>(null);
  // Lọc nhanh người CHƯA CÓ CA NỀN. Quan trọng vì form hồ sơ không còn gán ca nữa:
  // người mới tạo sẽ không chấm công được cho tới khi được đặt ca nền ở đây.
  const [onlyNoDefault, setOnlyNoDefault] = useState(false);
  // "Đặt ca nền" — ghi vào MỐC hiệu lực (áp dụng mọi tháng sau), khác hẳn tô lưới.
  // `baseTarget` cho phép áp cho MỘT người (bấm ô Ca nền của hàng đó) hoặc TẤT CẢ
  // người đang hiển thị (nút trên thanh công cụ) — cùng một form, cùng một endpoint.
  const [baseTarget, setBaseTarget] = useState<{
    ids: number[];
    label: string;
  } | null>(null);
  // "" = chưa chọn (chặn Áp dụng) · "none" = cố ý bỏ gán ca. Hai thứ này PHẢI khác nhau:
  // để trống mà vẫn cho bấm thì lỡ tay là xoá ca nền cả phòng, và ai mất ca thì không
  // chấm công được.
  const [baseShift, setBaseShift] = useState<number | "" | "none">("");
  const [baseFrom, setBaseFrom] = useState("");
  const [baseBusy, setBaseBusy] = useState(false);
  const [baseMsg, setBaseMsg] = useState<string | null>(null);
  // Lịch sử đổi ca nền của 1 NV (thay cho bảng lịch sử ở khối "Ca mặc định" cũ).
  const [histFor, setHistFor] = useState<{ id: number; name: string } | null>(
    null,
  );
  const [hist, setHist] = useState<EmployeeShiftAssignment[] | null>(null);
  const [histNonce, setHistNonce] = useState(0);
  const [histBusy, setHistBusy] = useState(false);
  const [histErr, setHistErr] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState<EmployeeShiftAssignment | null>(
    null,
  );
  // "Áp nhanh" — rải sẵn một mẫu xoay ca (vd 2-2-2) cho cả tổ, các kíp lệch pha nhau.
  // Chỉ ghi vào NHÁP như tô tay: xem lưới xong người dùng mới bấm Lưu.
  const [qfOpen, setQfOpen] = useState(false);
  const [qfPattern, setQfPattern] = useState<Brush[]>([]);
  const [qfStart, setQfStart] = useState(1);
  const [qfPhase, setQfPhase] = useState(0);
  const [qfSkipRest, setQfSkipRest] = useState(false);

  const locked = data?.locked === true;
  const dirtyCount = pending.size;

  useEffect(() => {
    localStorage.setItem(DENSITY_KEY, density);
  }, [density]);
  useEffect(() => {
    api.employees
      .meta(token)
      .then((m) => setDepts(m.departments))
      .catch(() => setDepts([]));
  }, [token]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.attendance.shiftPlan(
          token,
          year,
          month,
          deptId === "" ? null : deptId,
        ),
      );
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Không tải được lưới phân ca.");
    } finally {
      setLoading(false);
    }
  }, [token, year, month, deptId]);
  useEffect(() => {
    void reload();
  }, [reload]);
  // Đổi tháng/phòng = thay bộ dữ liệu → nháp cũ không còn ý nghĩa (đã hỏi ở guard trước đó).
  useEffect(() => {
    setPending(new Map());
    setRejects(new Map());
    setResult(null);
    setQfStart(1); // tháng khác = số ngày khác → ngày bắt đầu cũ có thể vượt ra ngoài
  }, [year, month, deptId]);

  // --- Lịch tháng + hàng hiển thị -------------------------------------------
  const cal: ShiftPlanDay[] = useMemo(() => {
    if (!data) return [];
    if (data.calendar.length) return data.calendar;
    return Array.from({ length: data.days_in_month }, (_, i) => {
      const day = i + 1;
      return {
        day,
        date: ymd(data.year, data.month, day),
        weekday: (new Date(data.year, data.month - 1, day).getDay() + 6) % 7,
        is_working: !isWeekend(data.year, data.month, day),
        special_kind: null,
        name: null,
      };
    });
  }, [data]);

  const noDefaultCount = useMemo(
    () => (data?.rows ?? []).filter((r) => r.no_default).length,
    [data],
  );

  // Gán xong người cuối cùng ⇒ TỰ TẮT lọc. Không có dòng này thì lọc vẫn bật mà nút bật/tắt đã
  // biến mất (nút chỉ hiện khi còn người thiếu ca) ⇒ lưới rỗng, đổi phòng hay Tải lại cũng vô
  // ích, người dùng kẹt luôn — đúng lỗi chủ báo 29/07/2026.
  // Chờ `data` có rồi mới xét: lúc đang tải `data` là null ⇒ đếm ra 0 ⇒ tắt lọc oan.
  useEffect(() => {
    if (data && onlyNoDefault && noDefaultCount === 0) setOnlyNoDefault(false);
  }, [data, onlyNoDefault, noDefaultCount]);

  const visibleRows = useMemo(() => {
    let rows = data?.rows ?? [];
    if (onlyNoDefault) rows = rows.filter((r) => r.no_default);
    const needle = stripTones(q).trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) =>
      stripTones(`${r.employee_name} ${r.employee_code ?? ""}`)
        .toLowerCase()
        .includes(needle),
    );
  }, [data, q, onlyNoDefault]);

  const shiftMeta = useMemo(() => buildShiftMeta(data?.shifts ?? []), [data]);
  const orderedShifts = useMemo(
    () => [...(data?.shifts ?? [])].sort((a, b) => a.id - b.id),
    [data],
  );
  const paintShifts = useMemo(
    () => orderedShifts.filter((s) => s.is_active),
    [orderedShifts],
  );

  const inheritInfo = useMemo(() => {
    const m = new Map<
      number,
      { inherit: (number | null)[]; base: number | null }
    >();
    for (const r of data?.rows ?? [])
      m.set(r.employee_id, inheritOfRow(r, cal));
    return m;
  }, [data, cal]);

  /** Giá trị HIỂN THỊ của mọi ô = dữ liệu server + nháp đang giữ. */
  const grid: EffCell[][] = useMemo(
    () =>
      visibleRows.map((row) =>
        cal.map((c, ci) => {
          const patch = pending.get(cellKey(row.employee_id, c.date));
          if (patch) {
            if (patch.action === "set")
              return {
                shiftId: patch.shift_id ?? null,
                hand: true,
                off: false,
              };
            if (patch.action === "off")
              return { shiftId: null, hand: true, off: true };
            return {
              shiftId: inheritInfo.get(row.employee_id)?.inherit[ci] ?? null,
              hand: false,
              off: false,
            };
          }
          const cell = row.days[String(c.day)];
          if (!cell) return { shiftId: null, hand: false, off: false };
          return {
            shiftId: cell.shift_id,
            hand: cell.source === "day",
            off: cell.is_off,
          };
        }),
      ),
    [visibleRows, cal, pending, inheritInfo],
  );

  const footCounts = useMemo(
    () =>
      cal.map((_, ci) => {
        const byShift = new Map<number, number>();
        let off = 0;
        let none = 0;
        for (const cells of grid) {
          const eff = cells[ci];
          if (!eff) continue;
          if (eff.off) off += 1;
          else if (eff.shiftId != null)
            byShift.set(eff.shiftId, (byShift.get(eff.shiftId) ?? 0) + 1);
          else none += 1;
        }
        return { byShift, off, none };
      }),
    [grid, cal],
  );

  // --- Bút ca: tô 1 ô hoặc kéo cả hình chữ nhật ------------------------------
  const paintable = !locked && !!brush && !saving;

  const applyBrush = useCallback(
    (
      next: Map<string, ShiftPlanPatchItem>,
      row: ShiftPlanRow,
      c: ShiftPlanDay,
      b: Brush,
    ) => {
      const key = cellKey(row.employee_id, c.date);
      const cell = row.days[String(c.day)];
      const wasHand = cell?.source === "day";
      const wasOff = cell?.is_off === true;
      const wasShift = cell?.shift_id ?? null;
      // Ô quay lại đúng giá trị gốc thì TỰ RƠI khỏi map (không gửi request thừa).
      if (b.kind === "inherit") {
        if (!wasHand) next.delete(key);
        else
          next.set(key, {
            employee_id: row.employee_id,
            work_date: c.date,
            action: "inherit",
          });
      } else if (b.kind === "off") {
        if (wasHand && wasOff) next.delete(key);
        else
          next.set(key, {
            employee_id: row.employee_id,
            work_date: c.date,
            action: "off",
          });
      } else {
        if (wasHand && !wasOff && wasShift === b.shiftId) next.delete(key);
        else
          next.set(key, {
            employee_id: row.employee_id,
            work_date: c.date,
            action: "set",
            shift_id: b.shiftId,
          });
      }
    },
    [],
  );

  // --- Áp nhanh: dựng nháp thử + xem trước -----------------------------------
  const qfPlan: RotationPlan = useMemo(
    () => ({
      pattern: qfPattern,
      startDay: Math.min(Math.max(1, qfStart), Math.max(1, cal.length)),
      phase: qfPhase,
      skipRest: qfSkipRest,
    }),
    [qfPattern, qfStart, qfPhase, qfSkipRest, cal.length],
  );

  /** Nháp SAU KHI áp + số ô đổi. Dùng chung cho dòng tóm tắt và nút "Áp vào nháp",
   *  nên con số người dùng thấy đúng bằng thứ sắp ghi xuống, không phải ước lượng. */
  const qfDraft = useMemo(() => {
    if (!qfOpen || qfPattern.length === 0 || visibleRows.length === 0)
      return null;
    const next = new Map(pending);
    const touched: string[] = [];
    runRotation(visibleRows, cal, qfPlan, (row, day, b) => {
      applyBrush(next, row, day, b);
      touched.push(cellKey(row.employee_id, day.date));
    });
    return { next, touched, changed: countPatchDiff(pending, next) };
  }, [qfOpen, qfPattern.length, visibleRows, cal, qfPlan, pending, applyBrush]);

  /** Dải xem trước: vài người đầu × ít ngày đầu — để mắt kiểm tra các kíp có lệch thật không. */
  const qfStrip = useMemo(() => {
    if (!qfOpen || qfPattern.length === 0) return null;
    const rows = visibleRows.slice(0, QF_STRIP_ROWS);
    if (rows.length === 0) return null;
    const byRow = rows.map(() => new Map<number, Brush>());
    const at = new Map(rows.map((r, i) => [r.employee_id, i]));
    runRotation(rows, cal, qfPlan, (row, day, b) => {
      const i = at.get(row.employee_id);
      if (i != null) byRow[i]?.set(day.day, b);
    });
    return {
      rows,
      byRow,
      days: cal.filter((c) => c.day >= qfPlan.startDay).slice(0, QF_STRIP_DAYS),
    };
  }, [qfOpen, qfPattern.length, visibleRows, cal, qfPlan]);

  const commitRef = useRef<(rect: DragRect) => void>(() => undefined);
  commitRef.current = (rect: DragRect) => {
    if (!brush || locked) return;
    const rA = Math.min(rect.r0, rect.r1),
      rB = Math.max(rect.r0, rect.r1);
    const cA = Math.min(rect.c0, rect.c1),
      cB = Math.max(rect.c0, rect.c1);
    const hits: { row: ShiftPlanRow; day: ShiftPlanDay }[] = [];
    for (let r = rA; r <= rB; r += 1) {
      const row = visibleRows[r];
      if (!row) continue;
      for (let c = cA; c <= cB; c += 1) {
        const day = cal[c];
        if (day) hits.push({ row, day });
      }
    }
    if (!hits.length) return;
    setBoQuaNghi(null);   // xoá nhắc của lần tô trước
    // TÔ MỘT LOẠT (kéo > 1 ô) BỎ QUA (chủ chốt 24/08/2026):
    //   · NGÀY QUÁ KHỨ (< hôm nay) — "lỗi chí mạng": gán 1–30 đè lên ngày đã chấm công / chờ đơn
    //     thì công quá khứ bị tính lại theo ca mới. Quá khứ đã xong, loạt chỉ áp HÔM NAY trở đi.
    //   · NGÀY NGHỈ TUẦN — tuần chuẩn T2–T7, đụng Chủ nhật là sai ý.
    // Cả hai chỉ chặn khi TÔ LOẠT; 1 ô (bút) vẫn cho, để sửa từng ngày khi thật sự cần (máy chủ
    // vẫn chặn riêng việc đổi ca ngày quá khứ ĐÃ CÓ ca).
    const todayIso = (() => {
      const n = new Date();
      return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
    })();
    const effective =
      hits.length > 1
        ? hits.filter((h) => h.day.is_working && h.day.date >= todayIso)
        : hits;
    if (!effective.length) return;
    const boQua = hits.length - effective.length;
    const b = brush;
    setPending((prev) => {
      const next = new Map(prev);
      for (const h of effective) applyBrush(next, h.row, h.day, b);
      return next;
    });
    if (boQua > 0) {
      setBoQuaNghi(
        `Đã bỏ qua ${boQua} ô (ngày đã qua / ngày nghỉ). Tô LOẠT chỉ áp hôm nay trở đi; muốn sửa quá khứ hoặc gán ngày nghỉ thì tô TAY từng ô.`,
      );
    }
    // Ô vừa sửa lại thì gỡ cờ "bị từ chối" của lần lưu trước.
    setRejects((prev) => {
      if (!prev.size) return prev;
      const next = new Map(prev);
      for (const h of hits) next.delete(cellKey(h.row.employee_id, h.day.date));
      return next.size === prev.size ? prev : next;
    });
  };

  const dragRef = useRef<DragRect | null>(null);
  dragRef.current = drag;
  useEffect(() => {
    function onUp() {
      const rect = dragRef.current;
      if (rect) commitRef.current(rect);
      setDrag(null);
    }
    window.addEventListener("mouseup", onUp);
    return () => window.removeEventListener("mouseup", onUp);
  }, []);

  // Phím tắt: 1..9 chọn ca thứ N · 0 = Nghỉ · Backspace/Delete = về mặc định · Esc = bỏ bút.
  useEffect(() => {
    if (locked || qfOpen) return; // đang mở modal Áp nhanh thì phím số là để nhập, không phải đổi bút
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable)
      )
        return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Escape") {
        setBrush(null);
        return;
      }
      if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        setBrush({ kind: "inherit" });
        return;
      }
      if (e.key === "0") {
        setBrush({ kind: "off" });
        return;
      }
      if (/^[1-9]$/.test(e.key)) {
        const s = paintShifts[Number(e.key) - 1];
        if (s) setBrush({ kind: "shift", shiftId: s.id });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [locked, paintShifts, qfOpen]);

  // Chặn mất dữ liệu khi còn nháp.
  useEffect(() => {
    if (!dirtyCount) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirtyCount]);

  useEffect(() => {
    if (histFor == null) {
      setHist(null);
      setHistErr(null);
      return;
    }
    let alive = true;
    api.employees
      .shiftHistory(token, histFor.id)
      .then((r) => {
        if (alive) setHist(r.items);
      })
      .catch(() => {
        if (alive) setHist([]);
      });
    return () => {
      alive = false;
    };
  }, [token, histFor, histNonce]);

  async function removeMilestone(assignmentId: number) {
    if (histFor == null) return;
    setHistBusy(true);
    setHistErr(null);
    try {
      await api.employees.deleteShiftAssignment(
        token,
        histFor.id,
        assignmentId,
      );
      setConfirmDel(null);
      setHistNonce((n) => n + 1); // nạp lại lịch sử
      await reload(); // ca nền đổi ⇒ lưới phải vẽ lại
    } catch (e) {
      setHistErr(e instanceof Error ? e.message : "Không xóa được mốc này.");
    } finally {
      setHistBusy(false);
    }
  }

  // Mở form đặt ca nền: mặc định áp dụng từ NGÀY 1 của tháng đang xem, NHƯNG không lùi trước hôm
  // nay. Ca nền lùi vào quá khứ ⇒ ngày ĐÃ CHẤM CÔNG resolve sang ca mới ⇒ lương kỳ nháp tính lại
  // âm thầm ("lỗi chí mạng" 24/08/2026). Mặc định mùng-1 (như cũ) chính là cái bẫy đó cho tháng
  // hiện tại. Chốt tại đây + `min` ở ô ngày để không MỜI người dùng ghi đè quá khứ. Tháng tương
  // lai vẫn ra mùng 1; tháng hiện tại/cũ ra hôm nay.
  function openBase(ids: number[], label: string, current?: number | null) {
    const dau = `${year}-${String(month).padStart(2, "0")}-01`;
    const homNay = isoToday();
    setBaseFrom(dau > homNay ? dau : homNay);
    setBaseShift(current ?? "");
    setBaseMsg(null);
    setBaseTarget({ ids, label });
  }

  async function applyBase() {
    const ids = baseTarget?.ids ?? [];
    if (ids.length === 0) {
      setBaseMsg("Không có nhân viên nào để áp dụng.");
      return;
    }
    setBaseBusy(true);
    setBaseMsg(null);
    try {
      const res = await api.employees.setShiftBulk(
        token,
        ids,
        typeof baseShift === "number" ? baseShift : null,
        baseFrom,
      );
      // Ca nền đổi ⇒ mọi ô đang "kế thừa" phải vẽ lại theo ca mới.
      await reload();
      if (res.failed.length === 0 && res.adjusted === 0) {
        setBaseTarget(null);
      } else {
        setBaseMsg(
          [
            `Đã đặt ca nền cho ${res.updated} nhân viên.`,
            res.adjusted
              ? `${res.adjusted} người vào làm sau ngày bạn chọn — mốc của họ tự lùi về đúng ngày vào làm.`
              : null,
            res.failed.length
              ? `${res.failed.length} người bị bỏ qua: ${[...new Set(res.failed.map((f) => f.reason))].join(" · ")}`
              : null,
          ]
            .filter(Boolean)
            .join(" "),
        );
      }
    } catch (e) {
      setBaseMsg(e instanceof Error ? e.message : "Không đặt được ca nền.");
    } finally {
      setBaseBusy(false);
    }
  }

  function guarded(run: () => void) {
    if (dirtyCount) setGuard({ run });
    else run();
  }
  function stepMonth(delta: number) {
    guarded(() =>
      setYm((cur) => {
        const m = cur.month + delta;
        if (m < 1) return { year: cur.year - 1, month: 12 };
        if (m > 12) return { year: cur.year + 1, month: 1 };
        return { year: cur.year, month: m };
      }),
    );
  }

  async function save() {
    const items = Array.from(pending.values());
    if (!items.length) return;
    setSaving(true);
    setResult(null);
    setError(null);
    let saved = 0;
    let cleared = 0;
    const rejected: {
      employee_id: number | null;
      date: string;
      reason: string;
    }[] = [];
    try {
      for (let i = 0; i < items.length; i += SAVE_CHUNK) {
        const lot = items.slice(i, i + SAVE_CHUNK);
        setProgress({
          done: Math.min(i + lot.length, items.length),
          total: items.length,
        });
        const out = await api.attendance.saveShiftPlan(token, year, month, lot);
        saved += out.saved;
        cleared += out.cleared;
        rejected.push(...out.rejected);
      }
      const rejMap = new Map(
        rejected.map((r) => [cellKey(r.employee_id ?? -1, r.date), r.reason]),
      );
      setRejects(rejMap);
      // Ô bị từ chối Ở LẠI trạng thái bẩn — tuyệt đối không im lặng bỏ qua.
      setPending((prev) => {
        const next = new Map<string, ShiftPlanPatchItem>();
        prev.forEach((v, k) => {
          if (rejMap.has(k)) next.set(k, v);
        });
        return next;
      });
      setResult({ saved, cleared, rejected: rejected.length });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu phân ca.");
      await reload();
    } finally {
      setSaving(false);
      setProgress(null);
    }
  }

  const rejectReasons = useMemo(
    () => Array.from(new Set(rejects.values())),
    [rejects],
  );

  function brushLabel(b: Brush): string {
    if (b.kind === "off") return "Nghỉ";
    if (b.kind === "inherit") return "Mặc định";
    return shiftMeta.get(b.shiftId)?.code ?? "?";
  }
  function brushCode(b: Brush): string {
    if (b.kind === "off") return "–";
    if (b.kind === "inherit") return "⌫";
    return shiftMeta.get(b.shiftId)?.code ?? "?";
  }
  function brushTone(b: Brush): string {
    return b.kind === "shift"
      ? (shiftMeta.get(b.shiftId)?.tone ?? "steel")
      : "rest";
  }

  // --- Áp nhanh --------------------------------------------------------------
  const qf222 = paintShifts.length >= 3 ? paintShifts.slice(0, 3) : null; // 3 kíp đầu theo thứ tự bút ca
  const qfWeekly = paintShifts.length >= 2 ? paintShifts : null;
  const qfLen = qfPattern.length;
  // Lệch nhiều hơn số bước của chu kỳ thì quay vòng — nói thẳng ra để khỏi tưởng máy ăn gian.
  const qfEffPhase =
    qfLen > 0 ? ((Math.trunc(qfPhase) % qfLen) + qfLen) % qfLen : 0;

  function openQuickFill() {
    // Ca đã ngưng hoạt động thì gỡ khỏi mẫu — tô vào chỉ để server từ chối.
    const live = new Set(paintShifts.map((s) => s.id));
    setQfPattern((p) =>
      p.filter((b) => b.kind !== "shift" || live.has(b.shiftId)),
    );
    setQfStart((d) => Math.min(Math.max(1, d), Math.max(1, cal.length)));
    setQfOpen(true);
  }

  function applyQuickFill() {
    if (locked || !qfDraft) return;
    setPending(qfDraft.next);
    // Ô vừa tô lại thì gỡ cờ "bị từ chối" của lần lưu trước — giống hệt lúc tô tay.
    setRejects((prev) => {
      if (!prev.size) return prev;
      const next = new Map(prev);
      for (const k of qfDraft.touched) next.delete(k);
      return next.size === prev.size ? prev : next;
    });
    setResult(null);
    setQfOpen(false);
  }

  return (
    <div className="cc-sp">
      <div className="cc-ts-header-actions cc-sp-toolbar">
        <div className="cc-ts-filters">
          <div className="cc-sp-month">
            <button
              type="button"
              className="cc-sp-month__nav"
              onClick={() => stepMonth(-1)}
              title="Tháng trước"
              aria-label="Tháng trước"
            >
              <ChevronLeft size={15} />
            </button>
            <span className="cc-sp-month__label">
              Tháng {month}/{year}
            </span>
            <button
              type="button"
              className="cc-sp-month__nav"
              onClick={() => stepMonth(1)}
              title="Tháng sau"
              aria-label="Tháng sau"
            >
              <ChevronRight size={15} />
            </button>
          </div>
          <select
            className="cc-ts-select-dept"
            value={deptId}
            aria-label="Lọc phòng/tổ"
            onChange={(e) => {
              const v = e.target.value === "" ? "" : Number(e.target.value);
              guarded(() => setDeptId(v));
            }}
          >
            <option value="">Tất cả phòng/tổ</option>
            {depts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <div className="cc-sp-search">
            <Search size={14} aria-hidden="true" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm tên / mã NV"
              aria-label="Tìm nhân viên"
            />
          </div>
          {/* Điều kiện có `|| onlyNoDefault`: nút PHẢI còn khi lọc đang bật, kể cả đếm về 0.
              Nút biến mất mà lọc vẫn bật = không còn đường tắt nó đi. */}
          {(noDefaultCount > 0 || onlyNoDefault) && (
            <button
              type="button"
              className={`cc-sp-flag${onlyNoDefault ? " is-on" : ""}`}
              aria-pressed={onlyNoDefault}
              onClick={() => setOnlyNoDefault((v) => !v)}
              title={
                noDefaultCount > 0
                  ? "Những người chưa có ca nền — họ CHƯA CHẤM CÔNG ĐƯỢC cho tới khi được đặt ca"
                  : "Không còn ai thiếu ca — bấm để bỏ lọc, xem lại cả danh sách"
              }
            >
              <AlertTriangle size={13} aria-hidden="true" /> Chưa có ca (
              {noDefaultCount})
            </button>
          )}
        </div>
        <div className="cc-ts-actions">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={locked || visibleRows.length === 0}
            onClick={() =>
              openBase(
                visibleRows.map((r) => r.employee_id),
                `tất cả ${visibleRows.length} nhân viên đang hiển thị`,
              )
            }
            title="Đặt ca nền cho TẤT CẢ nhân viên đang hiển thị (bấm ô 'Ca nền' của một hàng để đặt riêng cho người đó)"
          >
            <Users size={14} /> Đặt ca chính cho tất cả…
          </button>
          {SHOW_QUICK_FILL && (
            <button
              type="button"
              className="btn btn--ghost"
              disabled={locked || visibleRows.length === 0}
              onClick={openQuickFill}
              title="Rải sẵn cả tháng theo một chu kỳ lặp (vd 2-2-2), các kíp tự lệch nhau — khỏi tô tay từng ô"
            >
              <Repeat size={14} /> Áp nhanh…
            </button>
          )}
          <div className="cc-sp-density" role="group" aria-label="Mật độ lưới">
            <button
              type="button"
              className={density === "compact" ? "is-on" : ""}
              aria-pressed={density === "compact"}
              onClick={() => setDensity("compact")}
            >
              Gọn
            </button>
            <button
              type="button"
              className={density === "roomy" ? "is-on" : ""}
              aria-pressed={density === "roomy"}
              onClick={() => setDensity("roomy")}
            >
              Thoáng
            </button>
          </div>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => void reload()}
            disabled={loading || saving}
            title="Tải lại lưới"
          >
            <RefreshCw
              size={14}
              className={loading ? "cc-animate-spin" : undefined}
            />{" "}
            Tải lại
          </button>
        </div>
      </div>

      {locked && (
        <div className="banner banner--warn cc-sp-banner">
          <span>
            <Lock size={13} aria-hidden="true" /> Kỳ công tháng {month}/{year}{" "}
            đã chốt — mở lại kỳ mới sửa được phân ca.
          </span>
        </div>
      )}
      {error && (
        <div className="banner banner--error cc-sp-banner">
          <span>{error}</span>
        </div>
      )}
      {boQuaNghi && (
        <div className="banner banner--warn cc-sp-banner">
          <span>{boQuaNghi}</span>
        </div>
      )}
      {result && (
        <div className="banner banner--success cc-sp-banner">
          <span>
            Đã lưu {result.saved} ô
            {result.cleared ? ` · gỡ ${result.cleared} ô về mặc định` : ""} ·{" "}
            {result.rejected} ô bị từ chối
          </span>
        </div>
      )}
      {rejectReasons.length > 0 && (
        <div className="banner banner--warn cc-sp-banner">
          <span>
            Ô bị từ chối vẫn còn đánh dấu trên lưới (viền cảnh báo) — di chuột
            vào ô để xem lý do. {rejectReasons.join(" · ")}
          </span>
        </div>
      )}

      {!locked && (
        <div className="cc-sp-brush" role="toolbar" aria-label="Bút ca">
          <span className="cc-sp-brush__label">Bút ca</span>
          {paintShifts.map((s, i) => {
            const meta = shiftMeta.get(s.id);
            const on = brush?.kind === "shift" && brush.shiftId === s.id;
            return (
              <button
                key={s.id}
                type="button"
                aria-pressed={on}
                className={`cc-sp-pill cc-sp-pill--${meta?.tone ?? "steel"} ${on ? "is-on" : ""}`}
                title={`${meta?.title ?? s.name}${i < 9 ? ` · phím ${i + 1}` : ""}`}
                onClick={() =>
                  setBrush(on ? null : { kind: "shift", shiftId: s.id })
                }
              >
                <span className="cc-sp-pill__code">{meta?.code ?? "?"}</span>
                <span className="cc-sp-pill__name">{s.name}</span>
              </button>
            );
          })}
          <button
            type="button"
            aria-pressed={brush?.kind === "off"}
            className={`cc-sp-pill cc-sp-pill--rest ${brush?.kind === "off" ? "is-on" : ""}`}
            title="Nghỉ luân phiên — dấu kế hoạch, không chặn chấm công, không sinh hệ số tiền · phím 0"
            onClick={() =>
              setBrush(brush?.kind === "off" ? null : { kind: "off" })
            }
          >
            <span className="cc-sp-pill__code">–</span>
            <span className="cc-sp-pill__name">Nghỉ</span>
          </button>
          <button
            type="button"
            aria-pressed={brush?.kind === "inherit"}
            className={`cc-sp-pill cc-sp-pill--erase ${brush?.kind === "inherit" ? "is-on" : ""}`}
            title="Xoá ô đã khai tay → về ca mặc định · phím Backspace"
            onClick={() =>
              setBrush(brush?.kind === "inherit" ? null : { kind: "inherit" })
            }
          >
            <Eraser size={13} aria-hidden="true" />
            <span className="cc-sp-pill__name">Mặc định ⌫</span>
          </button>
          <span className="cc-sp-brush__hint">
            {brush
              ? `Đang cầm bút "${brushLabel(brush)}" — click 1 ô hoặc kéo để tô cả vùng · Esc bỏ bút`
              : "Chọn 1 bút rồi click/kéo trên lưới · phím 1–9 chọn ca · 0 nghỉ · ⌫ mặc định"}
          </span>
        </div>
      )}

      <div className="cc-sp-legend">
        <span className="cc-sp-lg cc-sp-lg--ghost">Kế thừa ca nền</span>
        <span className="cc-sp-lg cc-sp-lg--hand">Khai tay</span>
        <span className="cc-sp-lg cc-sp-lg--rest">Nghỉ theo lịch</span>
        <span
          className="cc-sp-lg cc-sp-lg--leave"
          title="Đọc thẳng từ phiếu nghỉ đã duyệt — chỉ để XEM, không phải dấu tô tay. Góc xanh = nghỉ có lương, góc đỏ = không lương. Huỷ/từ chối phiếu là dấu tự hết."
        >
          Nghỉ phép (đã duyệt)
        </span>
        <span className="cc-sp-lg cc-sp-lg--hol">Lễ</span>
        <span className="cc-sp-lg cc-sp-lg--make">Làm bù</span>
        <span className="cc-sp-lg cc-sp-lg--x1">Nghỉ 1×</span>
        <span className="cc-sp-lg cc-sp-lg--dirty">Chưa lưu</span>
      </div>

      {loading && <EmptyState trangThai="dang-tai" inline />}
      {!loading && data && (
        <div className="cc-timesheet-scroll-container cc-sp-scroll">
          <table
            className={`cc-timesheet-table cc-sp-table ${density === "roomy" ? "cc-sp-table--roomy" : ""} ${drag ? "is-dragging" : ""}`}
          >
            <thead>
              <tr>
                <th className="cc-sp-col-name">Nhân viên</th>
                <th
                  className="cc-sp-col-base"
                  title="Ca mặc định (nền) đang áp dụng cho nhân viên"
                >
                  Ca nền
                </th>
                {cal.map((c) => {
                  const restDay = !c.is_working;   // theo LỊCH TUẦN thật (works_*), không đóng đinh CN
                  const cls = [
                    "cc-sp-hdr",
                    c.weekday === 0 ? "cc-sp-hdr--wk" : "",
                    restDay ? "cc-sp-hdr--we" : "",
                    c.special_kind === "off" ? "cc-sp-hdr--hol" : "",
                    c.special_kind === "work" ? "cc-sp-hdr--make" : "",
                    c.special_kind === "off1x" ? "cc-sp-hdr--x1" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  const tip = [
                    `${getWeekdayLabel(year, month, c.day)} ${fmtYmd(c.date)}`,
                    c.name,
                    c.special_kind === "off1x"
                      ? "Nghỉ không lương — đi làm hưởng 1× lương chính"
                      : null,
                    c.special_kind === "work" ? "Ngày làm bù" : null,
                  ]
                    .filter(Boolean)
                    .join(" · ");
                  return (
                    <th key={c.day} className={cls} title={tip} scope="col">
                      <div className="cc-sp-hdr__wd">
                        {getWeekdayLabel(year, month, c.day)}
                      </div>
                      <div className="cc-sp-hdr__d">{c.day}</div>
                      {c.special_kind === "off1x" && (
                        <div className="cc-sp-hdr__flag">1×</div>
                      )}
                    </th>
                  );
                })}
                <th
                  className="cc-sp-col-bar"
                  title="Tỷ trọng ca trong tháng của từng nhân viên"
                >
                  Ca/tháng
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, ri) => {
                const base = inheritInfo.get(row.employee_id)?.base ?? null;
                const baseMeta = base != null ? shiftMeta.get(base) : undefined;
                const counts = new Map<number, number>();
                let restDays = 0;
                grid[ri]?.forEach((eff) => {
                  if (eff.off) restDays += 1;
                  else if (eff.shiftId != null)
                    counts.set(eff.shiftId, (counts.get(eff.shiftId) ?? 0) + 1);
                });
                const segs = orderedShifts
                  .filter((s) => (counts.get(s.id) ?? 0) > 0)
                  .map((s) => ({
                    key: `s${s.id}`,
                    tone: shiftMeta.get(s.id)?.tone ?? "steel",
                    n: counts.get(s.id) ?? 0,
                  }));
                const barTitle =
                  [
                    ...orderedShifts
                      .filter((s) => (counts.get(s.id) ?? 0) > 0)
                      .map(
                        (s) =>
                          `${shiftMeta.get(s.id)?.name ?? s.name}: ${counts.get(s.id)}`,
                      ),
                    restDays ? `Nghỉ: ${restDays}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Chưa có ca nào trong tháng";
                const total = Math.max(1, cal.length);
                return (
                  <tr
                    key={row.employee_id}
                    className={row.no_default ? "cc-sp-row--nodef" : ""}
                  >
                    <td className="cc-sp-col-name">
                      <div className="cc-name-cell-wrapper">
                        <span className="cc-name-avatar">
                          {getInitials(row.employee_name)}
                        </span>
                        <span className="cc-sp-who">
                          <button
                            type="button"
                            className="cc-sp-who__name cc-sp-who__link"
                            title={`${row.employee_name} — xem lịch sử đổi ca nền`}
                            onClick={() =>
                              setHistFor({
                                id: row.employee_id,
                                name: row.employee_name,
                              })
                            }
                          >
                            {row.employee_name}
                          </button>
                          <span className="cc-sp-who__sub">
                            <span className="cc-sp-who__code">
                              {row.employee_code ?? "—"}
                            </span>
                            {row.no_default && (
                              <span
                                className="ns-badge ns-badge--warn cc-sp-nodef"
                                title="Nhân viên chưa được gán ca mặc định — khai ca trên lưới hoặc gán ở khối C · Ca mặc định"
                              >
                                Chưa có ca
                              </span>
                            )}
                          </span>
                        </span>
                      </div>
                    </td>
                    <td className="cc-sp-col-base">
                      <button
                        type="button"
                        className="cc-sp-basebtn"
                        disabled={locked}
                        onClick={() =>
                          openBase([row.employee_id], row.employee_name, base)
                        }
                        title={
                          `Đặt ca nền riêng cho ${row.employee_name}` +
                          (baseMeta
                            ? ` — hiện: ${baseMeta.title}`
                            : " — hiện chưa có ca nền")
                        }
                      >
                        {baseMeta ? (
                          <span
                            className={`cc-sp-chip cc-sp-chip--${baseMeta.tone} is-ghost`}
                          >
                            {baseMeta.code}
                          </span>
                        ) : (
                          <span className="cc-sp-chip cc-sp-chip--none is-ghost">
                            ·
                          </span>
                        )}
                      </button>
                    </td>
                    {cal.map((c, ci) => {
                      const key = cellKey(row.employee_id, c.date);
                      // Nghỉ phép đã duyệt: đọc THẲNG từ dữ liệu server, KHÔNG đi qua `eff`.
                      // Bút ca không bao giờ đổi được phép, nên nó phải nằm NGOÀI mọi nhánh
                      // xem-trước bên dưới — tô ca lên ngày nghỉ thì dấu vẫn phải còn.
                      const lv = row.days[String(c.day)];
                      const leaveName = lv?.leave_name ?? null;
                      const inRect =
                        !!drag &&
                        ri >= Math.min(drag.r0, drag.r1) &&
                        ri <= Math.max(drag.r0, drag.r1) &&
                        ci >= Math.min(drag.c0, drag.c1) &&
                        ci <= Math.max(drag.c0, drag.c1);
                      let eff = grid[ri]?.[ci] ?? {
                        shiftId: null,
                        hand: false,
                        off: false,
                      };
                      if (inRect && brush) {
                        if (brush.kind === "off")
                          eff = { shiftId: null, hand: true, off: true };
                        else if (brush.kind === "inherit")
                          eff = {
                            shiftId:
                              inheritInfo.get(row.employee_id)?.inherit[ci] ??
                              null,
                            hand: false,
                            off: false,
                          };
                        else
                          eff = {
                            shiftId: brush.shiftId,
                            hand: true,
                            off: false,
                          };
                      }
                      const meta =
                        eff.shiftId != null
                          ? shiftMeta.get(eff.shiftId)
                          : undefined;
                      const reason = rejects.get(key);
                      const restDay = !c.is_working;   // theo LỊCH TUẦN thật (works_*), không đóng đinh CN
                      const cls = [
                        "cc-day-cell",
                        "cc-sp-cell",
                        c.weekday === 0 ? "cc-sp-cell--wk" : "",
                        restDay ? "cc-sp-cell--we" : "",
                        c.special_kind === "off" || c.special_kind === "off1x"
                          ? "cc-sp-cell--hol"
                          : "",
                        c.special_kind === "work" ? "cc-sp-cell--make" : "",
                        eff.off ? "cc-sp-cell--rest" : "",
                        leaveName ? "cc-sp-cell--leave" : "",
                        leaveName && lv?.leave_paid === false
                          ? "cc-sp-cell--leave-unpaid"
                          : "",
                        pending.has(key) ? "is-dirty" : "",
                        reason ? "is-rejected" : "",
                        inRect ? "is-preview" : "",
                        paintable ? "is-paintable" : "",
                      ]
                        .filter(Boolean)
                        .join(" ");
                      const dayTip = [
                        `${getWeekdayLabel(year, month, c.day)} ${fmtYmd(c.date)}`,
                        c.name,
                        // Vào dayTip (chứ không chỉ chipTip) để hover ĐÂU trong ô cũng đọc được:
                        // chipTip đã nối dayTip vào nên chỉ cần viết một chỗ.
                        leaveName
                          ? `NGHỈ PHÉP ĐÃ DUYỆT: ${leaveName}${lv?.leave_paid === false ? " (không lương)" : ""}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      const chipTip = [
                        eff.off
                          ? "Nghỉ theo lịch (dấu kế hoạch — không chặn chấm công, không sinh hệ số)"
                          : (meta?.title ?? "Chưa có ca"),
                        eff.hand ? "khai tay" : "kế thừa ca nền",
                        dayTip,
                        c.special_kind === "off1x"
                          ? "Nghỉ không lương — đi làm hưởng 1× lương chính"
                          : null,
                        reason ? `TỪ CHỐI: ${reason}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ");
                      return (
                        <td
                          key={c.day}
                          className={cls}
                          title={dayTip}
                          onMouseDown={
                            paintable
                              ? (e) => {
                                  e.preventDefault();
                                  setDrag({ r0: ri, c0: ci, r1: ri, c1: ci });
                                }
                              : undefined
                          }
                          onMouseEnter={
                            paintable
                              ? () =>
                                  setDrag((d) =>
                                    d ? { ...d, r1: ri, c1: ci } : d,
                                  )
                              : undefined
                          }
                        >
                          {/* Ngày NGHỈ TUẦN (theo lịch) mà KHÔNG tô tay ⇒ hiện "nghỉ", KHÔNG hiện
                              ca nền mờ. Trước đây ô Chủ nhật vẫn khoe ca nền (is-ghost) nên Khai ca
                              trông như đã xếp CN, lệch với Công của tôi (để trống). Nay hai màn
                              THÔNG NHAU: CN nghỉ ở cả hai; tô tay (eff.hand) thì mới hiện ca. */}
                          {eff.off || (restDay && !eff.hand) ? (
                            <span className="cc-sp-rest" title={chipTip}>
                              –
                            </span>
                          ) : meta ? (
                            <span
                              className={`cc-sp-chip cc-sp-chip--${meta.tone} ${eff.hand ? "is-hand" : "is-ghost"}`}
                              title={chipTip}
                            >
                              {meta.code}
                            </span>
                          ) : (
                            <span
                              className="cc-sp-chip cc-sp-chip--none is-ghost"
                              title={chipTip}
                            >
                              ·
                            </span>
                          )}
                        </td>
                      );
                    })}
                    <td className="cc-sp-col-bar">
                      <div className="cc-sp-bar" title={barTitle}>
                        {segs.map((s) => (
                          <span
                            key={s.key}
                            className={`cc-sp-bar__seg cc-sp-bar__seg--${s.tone}`}
                            style={{ width: `${(s.n / total) * 100}%` }}
                          />
                        ))}
                        {restDays > 0 && (
                          <span
                            className="cc-sp-bar__seg cc-sp-bar__seg--rest"
                            style={{ width: `${(restDays / total) * 100}%` }}
                          />
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={cal.length + 3} className="ns__empty">
                    {/* Nói RÕ lọc nào đang chặn + cho nút gỡ ngay tại chỗ. "Không có nhân viên
                        phù hợp bộ lọc" trống trơn khiến người dùng tưởng mất dữ liệu. */}
                    {onlyNoDefault ? (
                      <>
                        Đang lọc <b>“Chưa có ca”</b> — không còn ai thiếu ca.{" "}
                        <button
                          type="button"
                          className="cc-sp-who__link"
                          onClick={() => setOnlyNoDefault(false)}
                        >
                          Bỏ lọc, xem cả danh sách
                        </button>
                      </>
                    ) : q.trim() ? (
                      <>
                        Không ai khớp từ khoá <b>“{q.trim()}”</b>.{" "}
                        <button
                          type="button"
                          className="cc-sp-who__link"
                          onClick={() => setQ("")}
                        >
                          Xoá tìm kiếm
                        </button>
                      </>
                    ) : (
                      "Phòng/tổ này chưa có nhân viên nào."
                    )}
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr>
                <td className="cc-sp-col-name cc-sp-foot__label">Người / ca</td>
                <td className="cc-sp-col-base" />
                {cal.map((c, ci) => {
                  const f = footCounts[ci];
                  const parts = orderedShifts.filter(
                    (s) => (f?.byShift.get(s.id) ?? 0) > 0,
                  );
                  const tip =
                    [
                      ...parts.map(
                        (s) =>
                          `${shiftMeta.get(s.id)?.name ?? s.name}: ${f.byShift.get(s.id)}`,
                      ),
                      f?.off ? `Nghỉ: ${f.off}` : null,
                      f?.none ? `Chưa có ca: ${f.none}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Không có ai";
                  return (
                    <td
                      key={c.day}
                      className={`cc-sp-foot ${c.weekday === 0 ? "cc-sp-cell--wk" : ""}`}
                      title={tip}
                    >
                      {parts.map((s, i) => (
                        <span key={s.id}>
                          {i > 0 && <span className="cc-sp-foot__sep">·</span>}
                          <span
                            className={`cc-sp-foot__n cc-sp-foot__n--${shiftMeta.get(s.id)?.tone ?? "steel"}`}
                          >
                            {f.byShift.get(s.id)}
                          </span>
                        </span>
                      ))}
                      {!!f?.off && (
                        <span>
                          {parts.length > 0 && (
                            <span className="cc-sp-foot__sep">·</span>
                          )}
                          <span className="cc-sp-foot__n cc-sp-foot__n--rest">
                            {f.off}
                          </span>
                        </span>
                      )}
                      {!parts.length && !f?.off && (
                        <span className="cc-sp-foot__n cc-sp-foot__n--zero">
                          —
                        </span>
                      )}
                    </td>
                  );
                })}
                <td className="cc-sp-col-bar" />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {!locked && (
        <div className="cc-sp-actionbar">
          <span
            className={`cc-sp-dirty ${dirtyCount ? "is-on" : ""}`}
            aria-live="polite"
          >
            <span className="cc-sp-dirty__dot" aria-hidden="true" />
            {dirtyCount
              ? `${dirtyCount} thay đổi chưa lưu`
              : "Chưa có thay đổi"}
          </span>
          {progress && (
            <span className="cc-sp-progress">
              Đang lưu {progress.done}/{progress.total}…
            </span>
          )}
          <span className="cc-sp-actionbar__gap" />
          <button
            type="button"
            className="btn btn--ghost"
            disabled={!dirtyCount || saving}
            onClick={() => {
              setPending(new Map());
              setRejects(new Map());
              setResult(null);
            }}
          >
            <Undo2 size={14} /> Hoàn tác tất cả
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!dirtyCount || saving}
            onClick={() => void save()}
          >
            <Save size={14} /> {saving ? "Đang lưu…" : "Lưu"}
          </button>
        </div>
      )}

      {baseTarget && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box" style={{ maxWidth: "460px" }}>
            <header className="ns-modal__head">
              <div className="cc-modal-title-group">
                <h2>Đặt ca nền</h2>
                <span className="cc-modal-subtitle">
                  Áp cho: {baseTarget.label}
                </span>
              </div>
              <button
                className="ns-modal__x"
                onClick={() => setBaseTarget(null)}
                disabled={baseBusy}
              >
                ×
              </button>
            </header>
            <div className="ns-modal__body">
              <p className="cc-note">
                Ca nền áp dụng{" "}
                <strong>từ ngày đã chọn trở về sau, cho MỌI tháng</strong> —
                khác với tô ca trên lưới (chỉ đúng ngày đã tô). Ngày nào không
                khai trên lưới thì dùng ca nền này.{" "}
                <strong>Chỉ đặt được từ hôm nay trở đi</strong> — quá khứ đã khoá,
                đổi ca ngày đã chấm công sẽ tính lại lương sai.
              </p>
              <label className="cc-sp-basepop__row">
                <span>Ca</span>
                {/* Bọc `cc-select-wrapper` để ăn style chung (viền, cao 36px, mũi tên vẽ sẵn)
                    thay vì rơi về select mặc định của trình duyệt. */}
                <div className="cc-select-wrapper">
                  <select
                    value={baseShift}
                    onChange={(e) =>
                      setBaseShift(
                        e.target.value === ""
                          ? ""
                          : e.target.value === "none"
                            ? "none"
                            : Number(e.target.value),
                      )
                    }
                  >
                    <option value="">— chọn ca —</option>
                    {paintShifts.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.start_time}–{s.end_time})
                      </option>
                    ))}
                    <option value="none">— bỏ gán ca nền —</option>
                  </select>
                </div>
              </label>
              <label className="cc-sp-basepop__row">
                <span>Áp dụng từ</span>
                <input
                  className="cc-input-text"
                  type="date"
                  min={isoToday()}
                  value={baseFrom}
                  onChange={(e) => setBaseFrom(e.target.value)}
                />
              </label>
              {baseShift === "none" && (
                <p className="cc-sp-basepop__msg">
                  Bỏ ca nền = những ngày không khai trên lưới sẽ{" "}
                  <strong>không có ca</strong>, và người đó
                  <strong> không chấm công được</strong>. Chỉ dùng khi thực sự
                  muốn vậy.
                </p>
              )}
              {baseMsg && <p className="cc-sp-basepop__msg">{baseMsg}</p>}
            </div>
            <footer
              className="ns-modal__foot"
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
              }}
            >
              <button
                className="btn btn--ghost"
                onClick={() => setBaseTarget(null)}
                disabled={baseBusy}
              >
                Hủy
              </button>
              <button
                className="btn btn--primary"
                onClick={() => void applyBase()}
                disabled={baseBusy || baseShift === "" || !baseFrom}
              >
                {baseBusy
                  ? "Đang áp dụng…"
                  : baseShift === "none"
                    ? "Bỏ gán ca nền"
                    : "Áp dụng"}
              </button>
            </footer>
          </div>
        </div>
      )}

      {qfOpen && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box cc-qf-box">
            <header className="ns-modal__head">
              <div className="cc-modal-title-group">
                <h2>Áp nhanh mẫu xoay ca</h2>
                <span className="cc-modal-subtitle">
                  Tháng {month}/{year} · {visibleRows.length} nhân viên đang
                  hiển thị
                </span>
              </div>
              <button className="ns-modal__x" onClick={() => setQfOpen(false)}>
                ×
              </button>
            </header>
            <div className="ns-modal__body cc-qf-body">
              <p className="cc-note">
                Rải sẵn cả tháng theo một chu kỳ lặp đi lặp lại, thay cho việc
                tô tay từng ô. Máy chỉ ghi vào nháp —{" "}
                <strong>áp xong vẫn phải bấm Lưu</strong>.
              </p>

              {(qf222 || qfWeekly) && (
                <div className="cc-qf-block">
                  <div className="cc-qf-head">Mẫu có sẵn</div>
                  <div className="cc-qf-row">
                    {qf222 && (
                      <button
                        type="button"
                        className="cc-qf-preset"
                        title="2 ngày ca đầu → 2 ngày ca giữa → 2 ngày ca khuya, người sau lệch 2 ngày so với người trước"
                        onClick={() => {
                          const [a, b, c] = qf222;
                          if (!a || !b || !c) return;
                          setQfPattern(
                            [a, a, b, b, c, c].map((s) => ({
                              kind: "shift",
                              shiftId: s.id,
                            })),
                          );
                          setQfPhase(2);
                        }}
                      >
                        <span className="cc-qf-preset__name">
                          2-2-2 (3 kíp)
                        </span>
                        <span className="cc-qf-preset__sub">
                          {qf222
                            .map((s) => shiftMeta.get(s.id)?.code ?? "?")
                            .join(" · ")}{" "}
                          · lệch 2 ngày
                        </span>
                      </button>
                    )}
                    {qfWeekly && (
                      <button
                        type="button"
                        className="cc-qf-preset"
                        title="Mỗi ca làm trọn 7 ngày rồi đổi, người sau lệch nguyên 1 tuần"
                        onClick={() => {
                          const p: Brush[] = [];
                          for (const s of qfWeekly)
                            for (let k = 0; k < 7; k += 1)
                              p.push({ kind: "shift", shiftId: s.id });
                          setQfPattern(p);
                          setQfPhase(7);
                        }}
                      >
                        <span className="cc-qf-preset__name">Xoay tuần</span>
                        <span className="cc-qf-preset__sub">
                          mỗi ca 7 ngày · lệch 1 tuần
                        </span>
                      </button>
                    )}
                    <span className="cc-note">
                      Bấm xong vẫn sửa lại được ở dưới.
                    </span>
                  </div>
                </div>
              )}

              <div className="cc-qf-block">
                <div className="cc-qf-head">
                  Chu kỳ lặp — mỗi ô là một ngày
                  {qfLen > 0 && (
                    <span className="cc-qf-head__n">{qfLen} ngày/vòng</span>
                  )}
                </div>
                <div className="cc-qf-chips">
                  {qfLen === 0 && (
                    <span className="cc-qf-chips__empty">
                      Chưa có ngày nào — bấm ca ở dưới để thêm
                    </span>
                  )}
                  {qfPattern.map((b, i) => (
                    <span
                      key={i}
                      className={`cc-qf-chip cc-qf-chip--${brushTone(b)}`}
                      title={`Ngày thứ ${i + 1} của vòng · ${brushLabel(b)}`}
                    >
                      {brushCode(b)}
                    </span>
                  ))}
                </div>
                <div className="cc-qf-row">
                  <span className="cc-qf-row__label">Thêm ngày</span>
                  {paintShifts.map((s) => {
                    const meta = shiftMeta.get(s.id);
                    return (
                      <button
                        key={s.id}
                        type="button"
                        className={`cc-sp-pill cc-sp-pill--${meta?.tone ?? "steel"}`}
                        title={meta?.title ?? s.name}
                        onClick={() =>
                          setQfPattern((p) => [
                            ...p,
                            { kind: "shift", shiftId: s.id },
                          ])
                        }
                      >
                        <span className="cc-sp-pill__code">
                          {meta?.code ?? "?"}
                        </span>
                        <span className="cc-sp-pill__name">{s.name}</span>
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    className="cc-sp-pill"
                    title="Ngày nghỉ luân phiên trong chu kỳ"
                    onClick={() => setQfPattern((p) => [...p, { kind: "off" }])}
                  >
                    <span className="cc-sp-pill__code">–</span>
                    <span className="cc-sp-pill__name">Nghỉ</span>
                  </button>
                  <span className="cc-qf-row__gap" />
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={qfLen === 0}
                    onClick={() => setQfPattern((p) => p.slice(0, -1))}
                  >
                    Xoá ngày cuối
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={qfLen === 0}
                    onClick={() => setQfPattern([])}
                  >
                    Xoá hết
                  </button>
                </div>
              </div>

              <div className="cc-qf-block">
                <div className="cc-qf-opts">
                  <label className="cc-qf-field">
                    <span>Bắt đầu từ ngày</span>
                    <input
                      type="number"
                      min={1}
                      max={Math.max(1, cal.length)}
                      value={qfStart}
                      onChange={(e) =>
                        setQfStart(
                          clampNum(e.target.value, 1, Math.max(1, cal.length)),
                        )
                      }
                    />
                  </label>
                  <label className="cc-qf-field">
                    <span>Lệch pha giữa các nhân viên</span>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      value={qfPhase}
                      onChange={(e) =>
                        setQfPhase(clampNum(e.target.value, 0, 30))
                      }
                    />
                  </label>
                </div>
                <p className="cc-note">
                  Người thứ 2 bắt đầu muộn hơn người thứ nhất bấy nhiêu bước —
                  để các kíp phủ kín mọi ca. Để <strong>0</strong> thì cả tổ
                  chạy y hệt nhau.
                  {qfLen > 0 &&
                    qfEffPhase !== qfPhase &&
                    ` Vòng chỉ có ${qfLen} ngày nên lệch ${qfPhase} thực ra bằng lệch ${qfEffPhase}.`}
                </p>
                <label className="cc-qf-check">
                  <input
                    type="checkbox"
                    checked={qfSkipRest}
                    onChange={(e) => setQfSkipRest(e.target.checked)}
                  />
                  <span>
                    Không tô vào ngày nghỉ tuần &amp; ngày lễ
                    <em>
                      Xưởng 3 ca chạy liên tục thì cứ để TẮT. Bật thì ngày nghỉ
                      bỏ trắng và không tiêu một bước của chu kỳ, nên vòng xoay
                      không bị lệch.
                    </em>
                  </span>
                </label>
              </div>

              {qfStrip && (
                <div className="cc-qf-block">
                  <div className="cc-qf-head">
                    Xem trước {qfStrip.rows.length} người đầu ·{" "}
                    {qfStrip.days.length} ngày đầu
                  </div>
                  <div className="cc-qf-strip">
                    <div className="cc-qf-strip__row cc-qf-strip__row--head">
                      <span className="cc-qf-strip__who" />
                      {qfStrip.days.map((c) => (
                        <span key={c.day} className="cc-qf-strip__d">
                          {c.day}
                        </span>
                      ))}
                    </div>
                    {qfStrip.rows.map((r, i) => (
                      <div key={r.employee_id} className="cc-qf-strip__row">
                        <span
                          className="cc-qf-strip__who"
                          title={r.employee_name}
                        >
                          {r.employee_name}
                        </span>
                        {qfStrip.days.map((c) => {
                          const b = qfStrip.byRow[i]?.get(c.day);
                          if (!b)
                            return (
                              <span
                                key={c.day}
                                className="cc-qf-strip__c cc-qf-strip__c--skip"
                                title="Bỏ trắng"
                              >
                                ·
                              </span>
                            );
                          return (
                            <span
                              key={c.day}
                              className={`cc-qf-strip__c cc-qf-chip--${brushTone(b)}`}
                              title={`Ngày ${c.day} · ${brushLabel(b)}`}
                            >
                              {brushCode(b)}
                            </span>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className="cc-qf-sum">
                Áp cho <strong>{visibleRows.length} nhân viên</strong> đang hiển
                thị · từ ngày <strong>{qfPlan.startDay}</strong> ·{" "}
                <strong>{qfDraft?.changed ?? 0} ô</strong> sẽ đổi
              </p>
              {qfLen > 0 &&
                visibleRows.length > 0 &&
                qfDraft?.changed === 0 && (
                  <p className="cc-sp-basepop__msg">
                    Mẫu này trùng đúng thứ lưới đang có — áp vào cũng không đổi
                    ô nào.
                  </p>
                )}
            </div>
            <footer
              className="ns-modal__foot"
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
              }}
            >
              <button
                className="btn btn--ghost"
                onClick={() => setQfOpen(false)}
              >
                Hủy
              </button>
              <button
                className="btn btn--primary"
                onClick={applyQuickFill}
                disabled={locked || qfLen === 0 || visibleRows.length === 0}
              >
                Áp vào nháp
              </button>
            </footer>
          </div>
        </div>
      )}

      {histFor && (
        <div
          className="cc-sp-drawer"
          role="dialog"
          aria-label={`Lịch sử đổi ca nền — ${histFor.name}`}
        >
          <div
            className="cc-sp-drawer__backdrop"
            onClick={() => setHistFor(null)}
          />
          <div className="cc-sp-drawer__panel">
            <div className="cc-sp-drawer__head">
              <div>
                <div className="cc-sp-drawer__title">Lịch sử ca</div>
                <div className="cc-sp-drawer__sub">{histFor.name}</div>
              </div>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setHistFor(null)}
              >
                Đóng
              </button>
            </div>
            <p className="cc-note">
              Ca nền áp dụng từ ngày hiệu lực trở về sau. Ngày nào khai riêng
              trên lưới thì ô đó thắng ca nền.
            </p>
            {histErr && (
              <div className="banner banner--error">
                <span>{histErr}</span>
              </div>
            )}
            {hist == null && <p className="ns__empty">Đang tải…</p>}
            {hist?.length === 0 && (
              <p className="ns__empty">Chưa có mốc ca nền nào.</p>
            )}
            {hist && hist.length > 0 && (
              <ul className="cc-sp-hist">
                {hist.map((h) => {
                  // 3 trạng thái, KHÔNG phải 2: mốc đặt cho ngày mai không phải "đã qua".
                  const state = h.is_current
                    ? "current"
                    : h.effective_from > isoToday()
                      ? "future"
                      : "past";
                  return (
                    <li key={h.id} className={`cc-sp-hist__item is-${state}`}>
                      <div className="cc-sp-hist__body">
                        <div className="cc-sp-hist__top">
                          <span className="cc-sp-hist__name">
                            {h.shift_id == null
                              ? "Bỏ ca (không có ca)"
                              : (shiftMeta.get(h.shift_id)?.name ??
                                `Ca #${h.shift_id}`)}
                          </span>
                          <span className={`cc-sp-hist__tag is-${state}`}>
                            {state === "current"
                              ? "Đang áp dụng"
                              : state === "future"
                                ? "Sắp áp dụng"
                                : "Đã qua"}
                          </span>
                        </div>
                        <div className="cc-sp-hist__range">
                          {fmtYmd(h.effective_from)} →{" "}
                          {h.effective_to
                            ? fmtYmd(h.effective_to)
                            : "trở về sau"}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="cc-sp-hist__del"
                        disabled={histBusy}
                        onClick={() => setConfirmDel(h)}
                        title="Gỡ mốc này (dùng khi gán nhầm)"
                        aria-label="Gỡ mốc này"
                      >
                        <Trash2 size={14} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="cc-note">
              Gỡ một mốc thì ngày tháng thuộc mốc đó quay về theo{" "}
              <strong>mốc liền trước</strong>.
            </p>

            {/* Phần trên là ca nền ĐANG LÀ GÌ theo giai đoạn; phần này là AI ĐÃ ĐỔI GÌ —
                gồm cả sửa tay từng ngày trên lưới mà danh sách mốc ở trên không hề thể hiện. */}
            <ShiftChangeLogPanel token={token} employeeId={histFor.id} />
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDel}
        danger
        title="Gỡ mốc ca nền"
        message={
          confirmDel
            ? `Gỡ mốc "${
                confirmDel.shift_id == null
                  ? "Bỏ ca"
                  : (shiftMeta.get(confirmDel.shift_id)?.name ??
                    `Ca #${confirmDel.shift_id}`)
              }"` +
              ` áp dụng từ ${fmtYmd(confirmDel.effective_from)}?` +
              " Những ngày thuộc mốc này sẽ quay về theo mốc liền trước."
            : undefined
        }
        confirmLabel="Gỡ mốc"
        busy={histBusy}
        error={histErr}
        onConfirm={() => {
          if (confirmDel) void removeMilestone(confirmDel.id);
        }}
        onCancel={() => {
          setConfirmDel(null);
          setHistErr(null);
        }}
      />

      <DiscardChangesDialog
        open={!!guard}
        message={`Còn ${dirtyCount} ô phân ca chưa lưu. Rời tháng/phòng này mà không lưu?`}
        onDiscard={() => {
          const g = guard;
          setPending(new Map());
          setRejects(new Map());
          setGuard(null);
          g?.run();
        }}
        onKeepEditing={() => setGuard(null)}
      />
    </div>
  );
}

// --- Khối C: Lịch sử thay đổi ca (chủ 28/07/2026) ---------------------------
// Ca của một người đến từ HAI lớp: ô lưới (đè đúng một ngày) và ca nền (áp từ ngày hiệu lực
// TRỞ VỀ SAU). Màn này hiện CẢ HAI — chỉ hiện lưới thì khi ai đó đổi ca nền, người xem thấy
// "không có thay đổi nào" trong khi ca đã đổi thật, tệ hơn là không có màn lịch sử.

const SHIFT_CHANGE_FILTERS = [
  { key: "all", label: "Tất cả" },
  { key: "day", label: "✎ Sửa tay" },
  { key: "base", label: "🗓 Ca nền" },
] as const;

/** Câu mô tả một dòng — dùng chung cho màn HCNS và hộp thư của NV, để hai nơi không kể hai kiểu. */
function shiftChangeText(c: ShiftChange): string {
  const truoc = c.is_off_before ? "Nghỉ theo lịch" : (c.shift_name_before ?? "không có ca");
  const sau = c.is_off_after ? "Nghỉ theo lịch" : (c.shift_name_after ?? "không có ca");
  return `${truoc} → ${sau}`;
}

function ShiftChangeLogPanel({
  token,
  employeeId,
}: {
  token: string;
  employeeId: number;
}) {
  const [filter, setFilter] = useState<(typeof SHIFT_CHANGE_FILTERS)[number]["key"]>("all");
  // null = ĐANG TẢI. Khởi tạo [] sẽ hiện "chưa có thay đổi nào" ngay lúc còn fetch — báo SAI.
  const [rows, setRows] = useState<ShiftChange[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // KHÔNG lọc tháng: drawer mở cho MỘT người nên số dòng vốn ít, mà chặn theo tháng thì thay
  // đổi tháng trước biến mất — đúng lúc người ta mở ra để hỏi "ai đổi ca tôi hôm nọ".
  useEffect(() => {
    let alive = true;
    api.attendance
      .shiftChanges(token, {
        employeeId,
        kind: filter === "all" ? undefined : filter,
      })
      .then((r) => {
        if (!alive) return;
        setRows(r.items);
        setErr(null);
      })
      .catch((e) => alive && setErr(elErr(e)));
    return () => {
      alive = false;
    };
  }, [token, employeeId, filter]);

  return (
    <div className="cc-scl">
      <div className="cc-scl__bar">
        <span className="cc-scl__head">Ai đã đổi ca của người này</span>
        <div className="cc-scl__filters">
          {SHIFT_CHANGE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`cc-scl__filter${filter === f.key ? " is-on" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="banner banner--error">{err}</div>}

      {rows === null ? (
        <p className="cc-hint">Đang tải lịch sử…</p>
      ) : rows.length === 0 ? (
        <p className="cc-hint">
          Chưa có thay đổi nào được ghi lại. Từ nay mọi lần sửa ô trên lưới hoặc đổi ca nền đều
          hiện ở đây kèm người sửa và giờ sửa.
        </p>
      ) : (
        <div className="cc-scl__list">
          {rows.map((c) => (
            <div className="cc-scl__row" key={c.id}>
              <span
                className={`cc-scl__chip cc-scl__chip--${
                  c.origin === "base_remove" ? "rm" : c.kind
                }`}
              >
                {c.origin === "base_remove"
                  ? "⊘ Gỡ mốc"
                  : c.kind === "day"
                    ? "✎ Sửa tay"
                    : "🗓 Ca nền"}
              </span>
              {/* HAI mốc thời gian khác nhau, đừng đọc lẫn: cột này là ngày ca ĐƯỢC ÁP DỤNG,
                  còn giờ ở cột phải mới là LÚC THAO TÁC. */}
              <span className="cc-scl__when">
                {c.kind === "base" ? "Áp dụng từ " : ""}
                {fmtDateVN(c.apply_date)}
                {c.kind === "base" && <em>trở về sau</em>}
              </span>
              <span className="cc-scl__delta">{shiftChangeText(c)}</span>
              <span className="cc-scl__by">
                {c.actor_name ?? "—"}
                <em>{fmtDateTime(c.created_at)}</em>
              </span>
              {!c.notified && (
                <span className="cc-scl__nomail" title="Nhân viên chưa có tài khoản đăng nhập">
                  chưa báo được
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
