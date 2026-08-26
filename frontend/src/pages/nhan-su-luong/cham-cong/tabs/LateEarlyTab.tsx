// Tab Đi muộn / về sớm / nghỉ nửa buổi (tách từ pages/ChamCongPage.tsx).
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  type LateEarlyRequest,
  type LateEarlyRoster,
  type LeaveQuota,
  type LeaveType,
  type MyShift,
} from "../../../../api/client";
import {
  Clock,
  AlertTriangle,
  Coffee,
  Plus,
  Info,
  LogIn,
  LogOut,
} from "lucide-react";
import { statusText, statusBadge } from "../components/badges";
import { fmtDateTime, isoToday, getInitials, elErr } from "../shared/helpers";

// --- Tab: Đi muộn / về sớm / nghỉ nửa buổi (module `di_muon`) ----------------
// Phiếu CHẤM CÔNG ngoại lệ — KHÔNG phải đơn nghỉ phép. 1 phiếu/ngày, khai khoảng VẮNG MẶT,
// tổ trưởng duyệt. NV tự xin; tổ trưởng khai hộ thì duyệt luôn.
// Nghỉ nửa buổi có thể tick "Trừ vào phép năm": tick → tiêu ngày phép (tròn lên 0,5) và phần
// vắng VẪN được trả lương; không tick → quỹ phép nguyên, MẤT CÔNG phần vắng nhưng KHÔNG bị phạt.
//
// Backend KHÔNG lưu "kiểu" (đi muộn / về sớm / nửa buổi) — FE suy ra từ KHUNG CA để hiển thị.
// Không biết ca ⇒ chỉ hiện chip trung tính, ẨN mini-bar: nhãn đoán sai tệ hơn không nhãn.

type ElKind = "late" | "early" | "half" | "mid";
type ElFormKind = "late" | "early" | "half";
/** Một dòng thợ trong roster của module `di_muon` (backend đã lọc scope + bỏ NV đã nghỉ). */
type ElRosterEmp = LateEarlyRoster["employees"][number];

/** Khung ca đã quy về PHÚT trên trục ngày công (ca qua đêm: `endMin` đã cộng 1440). */
interface ElShift {
  name: string;
  startMin: number;
  endMin: number;
  overnight: boolean;
}

const EL_TOLERANCE = 10; // dung sai mép ca (phút) khi suy ra kiểu vắng
const EL_FALLBACK_WINDOW = 480; // ca 8h — mẫu số dự phòng khi chưa gán ca (khớp backend)

const EL_KIND_META: Record<
  ElKind,
  { label: string; Icon: typeof Clock; cls: string }
> = {
  late: { label: "Đi muộn", Icon: LogIn, cls: "el-kind--late" },
  early: { label: "Về sớm", Icon: LogOut, cls: "el-kind--early" },
  half: { label: "Nghỉ nửa buổi", Icon: Coffee, cls: "el-kind--half" },
  mid: { label: "Vắng giữa ca", Icon: Clock, cls: "el-kind--mid" },
};

const EL_FORM_KINDS: {
  value: ElFormKind;
  label: string;
  Icon: typeof Clock;
}[] = [
  { value: "late", label: "Đi muộn", Icon: LogIn },
  { value: "early", label: "Về sớm", Icon: LogOut },
  { value: "half", label: "Nghỉ nửa buổi", Icon: Coffee },
];

const EL_WEEKDAYS = [
  "Chủ nhật",
  "Thứ 2",
  "Thứ 3",
  "Thứ 4",
  "Thứ 5",
  "Thứ 6",
  "Thứ 7",
];



function elHhmmToMin(v: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(v.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return null;
  return h * 60 + mi;
}

/** Phút trên trục ngày công → "HH:MM" (lấy phần trong ngày; ca đêm vẫn ra giờ đồng hồ đúng). */
function elMinToHhmm(m: number): string {
  const rem = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

/** Ca ở dạng "HH:MM" (nguồn `myStatus().shift` — self-service, ai cũng gọi được). */
function elMakeShift(
  s:
    | {
        name: string;
        start_time: string;
        end_time: string;
        is_overnight: boolean;
      }
    | null
    | undefined,
): ElShift | null {
  if (!s) return null;
  const st = elHhmmToMin(s.start_time);
  const en = elHhmmToMin(s.end_time);
  if (st == null || en == null) return null;
  return elShiftFrom(s.name, st, en, s.is_overnight);
}

/** Ca ở dạng PHÚT (nguồn `lateEarly.roster()` — gác bằng `di_muon:approve`). */
function elShiftFromMinutes(s: {
  name: string;
  start_minute: number;
  end_minute: number;
  is_overnight: boolean;
}): ElShift | null {
  return elShiftFrom(s.name, s.start_minute, s.end_minute, s.is_overnight);
}

function elShiftFrom(
  name: string,
  st: number,
  en: number,
  overnight: boolean,
): ElShift | null {
  const endMin = en + (overnight || en <= st ? 1440 : 0);
  if (endMin <= st) return null;
  return { name, startMin: st, endMin, overnight: endMin > 1440 };
}

/** Ca qua đêm: giờ ĐỒNG HỒ rơi vào phần "sang hôm sau" → đẩy +1440 cho cùng trục với khung ca. */
function elOnAxis(minute: number, sh: ElShift | null): number {
  if (!sh || !sh.overnight) return minute;
  return minute < sh.startMin ? minute + 1440 : minute;
}

/** Suy ra kiểu vắng theo khung ca (dung sai 10'). Không biết ca ⇒ null (chip trung tính). */
function elKindOf(
  fromMinute: number,
  toMinute: number,
  sh: ElShift | null,
): ElKind | null {
  if (!sh) return null;
  const from = elOnAxis(fromMinute, sh);
  const to = elOnAxis(toMinute, sh);
  const span = sh.endMin - sh.startMin;
  const minutes = to - from;
  if (span <= 0 || minutes <= 0) return null;
  const half = span / 2;
  if (from <= sh.startMin + EL_TOLERANCE && minutes < half) return "late";
  if (to >= sh.endMin - EL_TOLERANCE && minutes < half) return "early";
  if (minutes >= half) return "half";
  return "mid";
}

/** "1 giờ 30 phút" — dòng phụ + hint (đọc thành tiếng được). */
function elDurLong(m: number): string {
  const h = Math.floor(m / 60);
  const mi = m % 60;
  if (h && mi) return `${h} giờ ${mi} phút`;
  if (h) return `${h} giờ`;
  return `${mi} phút`;
}

/** "1h30" / "45'" — chip trung tính khi KHÔNG biết ca. */
function elDurShort(m: number): string {
  const h = Math.floor(m / 60);
  const mi = m % 60;
  if (h && mi) return `${h}h${String(mi).padStart(2, "0")}`;
  if (h) return `${h}h`;
  return `${mi}'`;
}

/** 0.5 → "0,5" (dấu phẩy thập phân kiểu Việt). */
function elNum(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/** Quy phút vắng ra ngày phép — LÀM TRÒN LÊN 0,5, trần 1,0 (đúng công thức backend). */
function elLeaveCong(minutes: number, windowMin: number): number {
  if (minutes <= 0 || windowMin <= 0) return 0;
  return Math.min(1, Math.ceil((minutes / windowMin) * 2) / 2);
}

function elWeekday(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  if (!y || !m || !d) return "";
  return EL_WEEKDAYS[new Date(y, m - 1, d).getDay()] ?? "";
}

/** "2026-07-27" → "27/07" (dòng chính ô Ngày công). */
function elDayMonth(ymd: string): string {
  const [, m, d] = ymd.split("-");
  return d && m ? `${d}/${m}` : ymd;
}

/** Mã 1 (icon + CHỮ) + Mã 2 (mini-bar đặt đúng vị trí trong ca). */
function ElKindCell({
  r,
  shift,
}: {
  r: LateEarlyRequest;
  shift: ElShift | null;
}) {
  const kind = elKindOf(r.from_minute, r.to_minute, shift);
  if (kind === null || shift === null) {
    return (
      <div className="el-kindcell">
        <span
          className="el-kind el-kind--mid"
          title="Chưa biết khung ca của nhân viên nên không suy được kiểu vắng."
        >
          <Clock size={12} /> Vắng {elDurShort(r.minutes)}
        </span>
      </div>
    );
  }
  const meta = EL_KIND_META[kind];
  const span = shift.endMin - shift.startMin;
  const from = elOnAxis(r.from_minute, shift);
  const to = elOnAxis(r.to_minute, shift);
  const left = Math.max(
    0,
    Math.min(100, ((from - shift.startMin) / span) * 100),
  );
  const right = Math.max(
    0,
    Math.min(100, ((to - shift.startMin) / span) * 100),
  );
  const width = Math.max(5, Math.min(right - left, 100 - left));
  return (
    <div className="el-kindcell">
      <span className={`el-kind ${meta.cls}`}>
        <meta.Icon size={12} /> {meta.label}
      </span>
      <div
        className="el-bar"
        aria-hidden="true"
        title={`Ca ${elMinToHhmm(shift.startMin)}–${elMinToHhmm(shift.endMin)} · vắng ${elDurLong(r.minutes)}`}
      >
        <span
          className={`el-bar__seg el-bar__seg--${kind}`}
          style={{ left: `${left}%`, width: `${width}%` }}
        />
      </div>
    </div>
  );
}

/** Cột "Phép năm" — nhánh TIỀN tách riêng, không nhét vào màu chip kiểu. */
function ElLeaveCell({ r }: { r: LateEarlyRequest }) {
  if (r.leave_type_id != null) {
    return (
      <span
        className="el-leave"
        title={r.leave_type_name ?? "Trừ vào phép năm"}
      >
        −{elNum(r.leave_cong)} ngày
      </span>
    );
  }
  return (
    <span
      className="el-noleave"
      title="Không đụng quỹ phép — mất công phần vắng, nhưng không bị phạt."
    >
      Không lương
    </span>
  );
}

/** Bảng phiếu dùng chung cho cả 2 tab con. */
function ElTable({
  rows,
  shiftFor,
  showEmployee,
  selectable,
  showDecision,
  selected,
  onToggle,
  actions,
}: {
  rows: LateEarlyRequest[];
  shiftFor: (r: LateEarlyRequest) => ElShift | null;
  showEmployee: boolean;
  selectable: boolean;
  showDecision: boolean;
  selected: Set<number>;
  onToggle: (id: number) => void;
  actions: (r: LateEarlyRequest) => ReactNode;
}) {
  return (
    <div className="cc-timesheet-scroll-container">
      <table className="cc-timesheet-table">
        <thead>
          <tr>
            {selectable && <th style={{ width: "40px" }} aria-label="Chọn" />}
            {showEmployee && <th style={{ textAlign: "left" }}>Nhân viên</th>}
            <th style={{ textAlign: "left" }}>Ngày công</th>
            <th style={{ textAlign: "left" }}>Kiểu</th>
            <th style={{ textAlign: "left" }}>Vắng mặt</th>
            <th style={{ textAlign: "center" }}>Phép năm</th>
            <th style={{ textAlign: "left" }}>Lý do</th>
            <th style={{ textAlign: "center" }}>Trạng thái</th>
            {showDecision && (
              <th style={{ textAlign: "left" }}>Kết quả duyệt</th>
            )}
            <th style={{ textAlign: "right" }} aria-label="Thao tác" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              {selectable && (
                <td style={{ textAlign: "center" }}>
                  {r.status === "pending" && (
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => onToggle(r.id)}
                      aria-label={`Chọn phiếu của ${r.employee_name ?? `NV#${r.employee_id}`}`}
                    />
                  )}
                </td>
              )}
              {showEmployee && (
                <td>
                  <div className="cc-name-cell-wrapper">
                    <span className="cc-name-avatar">
                      {getInitials(r.employee_name)}
                    </span>
                    <span
                      className="cc-name-text-plain"
                      title={r.employee_name ?? `NV#${r.employee_id}`}
                    >
                      {r.employee_name ?? `NV#${r.employee_id}`}
                    </span>
                  </div>
                </td>
              )}
              <td>
                <span className="el-cell-main">{elDayMonth(r.work_date)}</span>
                <span className="el-cell-sub">{elWeekday(r.work_date)}</span>
              </td>
              <td>
                <ElKindCell r={r} shift={shiftFor(r)} />
              </td>
              <td>
                <span className="el-cell-mono">
                  {elMinToHhmm(r.from_minute)} → {elMinToHhmm(r.to_minute)}
                </span>
                <span className="el-cell-sub">{elDurLong(r.minutes)}</span>
              </td>
              <td style={{ textAlign: "center" }}>
                <ElLeaveCell r={r} />
              </td>
              <td>
                <div className="cc-reason-wrapper">
                  <span className="cc-reason-text">{r.reason || "—"}</span>
                </div>
              </td>
              <td style={{ textAlign: "center" }}>{statusBadge(r.status)}</td>
              {showDecision && (
                <td>
                  {r.decided_by_name || r.decided_at || r.decision_note ? (
                    <div className="cc-reason-wrapper">
                      <span className="cc-reason-text">
                        {r.decided_by_name ?? "—"}
                      </span>
                      {r.decided_at && (
                        <span className="el-cell-sub">
                          {fmtDateTime(r.decided_at)}
                        </span>
                      )}
                      {r.decision_note && (
                        <div className="cc-decision-note-sub">
                          💬 {r.decision_note}
                        </div>
                      )}
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
              )}
              <td style={{ textAlign: "right" }}>
                <div className="cc-rowact">{actions(r)}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Từ chối phải ghi lý do — ô bắt buộc trong modal (KHÔNG dùng window.prompt). */
function ElRejectModal({
  count,
  onClose,
  onConfirm,
}: {
  count: number;
  onClose: () => void;
  onConfirm: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <h2>{count > 1 ? `Từ chối ${count} phiếu` : "Từ chối phiếu"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          <label className="ns-field">
            <span className="ns-field__label">Lý do từ chối *</span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="vd: hôm đó xưởng chạy đơn gấp, không bố trí được"
              autoFocus
            />
          </label>
          <p className="np-hint">
            Lý do này hiện ở cột <b>Kết quả duyệt</b> để thợ biết vì sao bị từ
            chối.
          </p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            disabled={!note.trim()}
            onClick={() => onConfirm(note.trim())}
          >
            Từ chối
          </button>
        </footer>
      </div>
    </div>
  );
}

/** Form tạo / sửa phiếu. `forEmployee` = tổ trưởng khai hộ (tạo & duyệt luôn). */
function ElFormModal({
  token,
  forEmployee,
  editing,
  myShift,
  shiftById,
  roster,
  mine,
  onClose,
  onSaved,
  onOpenExisting,
}: {
  token: string;
  forEmployee: boolean;
  editing?: LateEarlyRequest | null;
  /** Ca của CHÍNH TÔI (nguồn `myStatus` — self-service, ai cũng gọi được). */
  myShift: ElShift | null;
  shiftById: Map<number, ElShift>;
  roster: ElRosterEmp[];
  /** Danh sách phiếu của tôi — dò trùng ngày TRƯỚC khi bấm Gửi. */
  mine: LateEarlyRequest[];
  onClose: () => void;
  onSaved: (msg: string) => void;
  onOpenExisting: (r: LateEarlyRequest) => void;
}) {
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [empQuery, setEmpQuery] = useState("");
  const [workDate, setWorkDate] = useState(editing?.work_date ?? isoToday());
  const [from, setFrom] = useState(
    editing ? elMinToHhmm(editing.from_minute) : "",
  );
  const [to, setTo] = useState(editing ? elMinToHhmm(editing.to_minute) : "");
  const [kind, setKind] = useState<ElFormKind | null>(null);
  const [deduct, setDeduct] = useState(
    editing ? editing.leave_type_id != null : false,
  );
  const [leaveTypeId, setLeaveTypeId] = useState<number | null>(
    editing?.leave_type_id ?? null,
  );
  const [reason, setReason] = useState(editing?.reason ?? "");
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [quotas, setQuotas] = useState<LeaveQuota[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Loại nghỉ có hạn mức năm (backend nhận `leave_type_id`, không nhận boolean) + số dư phép
  // của CHÍNH TÔI. Cả 2 endpoint đều là self-service của module `nghi_phep`.
  useEffect(() => {
    api.leaves
      .types(token)
      .then((r) => {
        const list = r.items.filter((t) => t.is_active && t.annual_quota > 0);
        setTypes(list);
        setLeaveTypeId((cur) => cur ?? (list.length ? list[0].id : null));
      })
      .catch(() => setTypes([]));
    if (!forEmployee) {
      api.leaves
        .me(token)
        .then((r) => setQuotas(r.quotas ?? []))
        .catch(() => setQuotas([]));
    }
  }, [token, forEmployee]);

  const pickedEmp =
    employeeId != null
      ? (roster.find((e) => e.id === employeeId) ?? null)
      : null;
  const activeShift = forEmployee
    ? pickedEmp?.default_shift_id != null
      ? (shiftById.get(pickedEmp.default_shift_id) ?? null)
      : null
    : myShift;

  // SỬA phiếu: suy lại kiểu từ khung ca (ca nạp async) để nút segmented sáng đúng ô. Chỉ chạy
  // MỘT LẦN — sau đó người dùng bấm gì là quyền của họ, đừng ghi đè lựa chọn đang gõ dở.
  const kindInferred = useRef(false);
  useEffect(() => {
    if (!editing || kindInferred.current || !activeShift) return;
    const k = elKindOf(editing.from_minute, editing.to_minute, activeShift);
    if (k === null) return;
    kindInferred.current = true;
    if (k !== "mid") setKind(k);
  }, [editing, activeShift]);

  // Checkbox trừ phép CHỈ mở cho nghỉ nửa buổi (đi muộn 20' mà tick trừ sẽ tròn thành 0,5 ngày
  // → lỗ hổng quỹ phép). Ngoại lệ: đang SỬA phiếu vốn có trừ phép mà chưa suy được kiểu ⇒ vẫn
  // phơi ra, nếu không lưu lại sẽ ÂM THẦM mất phần trừ phép cũ.
  const canDeduct =
    kind === "half" || (kind === null && editing?.leave_type_id != null);

  // Chọn kiểu vắng → TỰ ĐIỀN GIỜ theo mép ca: vừa ít thao tác, vừa khoá giờ đúng mép nên
  // chip suy ra kiểu đúng y như người dùng vừa chọn.
  function pickKind(k: ElFormKind) {
    setKind(k);
    if (k !== "half") setDeduct(false);
    const sh = activeShift;
    if (!sh) return;
    const span = sh.endMin - sh.startMin;
    if (k === "late") {
      setFrom(elMinToHhmm(sh.startMin));
      setTo(elMinToHhmm(Math.min(sh.startMin + 60, sh.endMin)));
    } else if (k === "early") {
      setTo(elMinToHhmm(sh.endMin));
      setFrom(elMinToHhmm(Math.max(sh.endMin - 60, sh.startMin)));
    } else {
      setFrom(elMinToHhmm(sh.startMin + Math.round(span / 2)));
      setTo(elMinToHhmm(sh.endMin));
    }
  }

  const fromRaw = elHhmmToMin(from);
  const toRaw = elHhmmToMin(to);
  // Ca qua đêm: đẩy giờ "sang hôm sau" về cùng trục ngày công với khung ca — nhờ vậy KHÔNG cần
  // checkbox "sang hôm sau" mà `from_minute`/`to_minute` gửi lên vẫn đúng trục backend.
  const fromAbs = fromRaw == null ? null : elOnAxis(fromRaw, activeShift);
  const toAbs = toRaw == null ? null : elOnAxis(toRaw, activeShift);
  const minutes = fromAbs != null && toAbs != null ? toAbs - fromAbs : null;
  const timeErr =
    minutes != null && minutes <= 0 ? "Đến lúc phải sau Vắng từ lúc." : null;

  const windowMin = activeShift
    ? activeShift.endMin - activeShift.startMin
    : EL_FALLBACK_WINDOW;
  const leaveCong = elLeaveCong(minutes ?? 0, windowMin);
  const quota =
    quotas.find((q) => q.leave_type_id === leaveTypeId) ??
    quotas.find((q) => q.annual_quota > 0) ??
    null;
  const remaining = quota?.remaining ?? 0;
  const shortOfLeave = !forEmployee && quotas.length > 0 && remaining < 0.5;

  // Băng số dư phép + khối "trừ vào phép năm" của form này ĐANG TẮT (JSX bị comment ở ~7965 và
  // ~8099). Phần tính ở trên giữ nguyên để bật lại chỉ cần bỏ comment khối JSX, không phải dựng
  // lại cả dây chuyền `quotas → quota → remaining`. Ba dòng `void` dưới đây chỉ để TypeScript
  // thôi báo "khai mà không dùng" — không chạy gì, không đổi hành vi.
  void types;
  void leaveCong;
  void shortOfLeave;

  // 1 phiếu/ngày: dò trong danh sách `mine` NGAY khi đổi ngày, đừng để bấm Gửi rồi mới báo.
  const clash = useMemo(() => {
    if (forEmployee || !workDate) return null;
    return (
      mine.find(
        (r) =>
          r.work_date === workDate &&
          (r.status === "pending" || r.status === "approved") &&
          r.id !== editing?.id,
      ) ?? null
    );
  }, [mine, workDate, forEmployee, editing]);

  const empOptions = useMemo(() => {
    const q = empQuery.trim().toLowerCase();
    const list = q
      ? roster.filter(
          (e) =>
            e.full_name.toLowerCase().includes(q) ||
            (e.code ?? "").toLowerCase().includes(q),
        )
      : roster;
    return list.slice(0, 300);
  }, [roster, empQuery]);

  async function save() {
    setErr(null);
    if (forEmployee && employeeId == null) return setErr("Cần chọn nhân viên.");
    if (!workDate) return setErr("Cần chọn ngày công.");
    if (fromAbs == null || toAbs == null)
      return setErr("Cần khai giờ bắt đầu và giờ kết thúc.");
    if (minutes == null || minutes <= 0)
      return setErr("Đến lúc phải sau Vắng từ lúc.");
    const input = {
      work_date: workDate,
      from_minute: fromAbs,
      to_minute: toAbs,
      reason: reason.trim() || null,
      leave_type_id: canDeduct && deduct ? leaveTypeId : null,
    };
    setBusy(true);
    try {
      if (editing) {
        await api.lateEarly.updateMine(token, editing.id, input);
        onSaved("Đã lưu phiếu — chờ tổ trưởng duyệt.");
      } else if (forEmployee) {
        await api.lateEarly.createFor(token, {
          ...input,
          employee_id: employeeId as number,
        });
        onSaved(`Đã tạo & duyệt phiếu cho ${pickedEmp?.full_name ?? "thợ"}.`);
      } else {
        await api.lateEarly.createMine(token, input);
        onSaved("Đã gửi phiếu — chờ tổ trưởng duyệt.");
      }
    } catch (e) {
      setErr(elErr(e)); // NGUYÊN VĂN `detail` của backend — đã tiếng Việt và khớp nhãn UI.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <h2>
            {editing
              ? "Sửa phiếu đi muộn / về sớm"
              : forEmployee
                ? "Khai hộ thợ — đi muộn / về sớm"
                : "Xin đi muộn / về sớm"}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}

          {/* {forEmployee ? (
            <div className="el-balance el-balance--muted">
              <span>Số dư phép của thợ sẽ được hệ thống kiểm khi lưu.</span>
            </div>
          ) : quota ? (
            <div className="el-balance">
              <span>Phép năm · {quota.name}</span>
              <span className="el-balance__val">
                còn {elNum(remaining)} / {elNum(quota.annual_quota)} ngày
              </span>
            </div>
          ) : null} */}

          {forEmployee && (
            <label className="ns-field">
              <span className="ns-field__label">Nhân viên *</span>
              <input
                value={empQuery}
                onChange={(e) => setEmpQuery(e.target.value)}
                placeholder="Gõ tên hoặc mã NV để tìm…"
              />
              <select
                value={employeeId ?? ""}
                onChange={(e) =>
                  setEmployeeId(e.target.value ? Number(e.target.value) : null)
                }
              >
                <option value="">— chọn thợ trong tổ của bạn —</option>
                {empOptions.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                    {e.code ? ` · ${e.code}` : ""}
                    {e.department ? ` · ${e.department}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className={`ns-field ${forEmployee ? "el-field" : ""}`}>
            <span className="ns-field__label">Ngày công *</span>
            <input
              type="date"
              value={workDate}
              onChange={(e) => setWorkDate(e.target.value)}
            />
          </label>

          {clash && (
            <div className="banner banner--warn el-stack">
              <span>
                Ngày {elDayMonth(clash.work_date)} đã có phiếu{" "}
                <b>{statusText(clash.status)}</b>. Mỗi ngày chỉ được một phiếu —
                sửa hoặc hủy phiếu cũ trước.
              </span>
              <button
                className="btn btn--ghost"
                onClick={() => onOpenExisting(clash)}
              >
                Mở phiếu ngày đó
              </button>
            </div>
          )}

          <div className="el-stack">
            <span className="ns-field__label">Kiểu vắng *</span>
            <div className="np-seg el-stack-sm">
              {EL_FORM_KINDS.map((k) => (
                <button
                  key={k.value}
                  type="button"
                  className={`np-seg__btn ${kind === k.value ? "is-active" : ""}`}
                  onClick={() => pickKind(k.value)}
                >
                  <k.Icon size={13} /> {k.label}
                </button>
              ))}
            </div>
          </div>

          {activeShift ? (
            <div className="el-shiftline">
              <Clock size={13} />
              <span>
                Ca của {forEmployee ? "thợ" : "bạn"}: <b>{activeShift.name}</b>{" "}
                ·{" "}
                <span className="el-shiftline__time">
                  {elMinToHhmm(activeShift.startMin)}–
                  {elMinToHhmm(activeShift.endMin)}
                </span>
              </span>
            </div>
          ) : (
            <div className="el-shiftline">
              <AlertTriangle size={13} />
              <span>
                Chưa rõ khung ca{forEmployee ? " của thợ" : ""} — hãy tự khai
                giờ vắng bên dưới.
              </span>
            </div>
          )}

          <div className="el-timegrid">
            <label className="ns-field">
              <span className="ns-field__label">Vắng từ lúc *</span>
              <input
                type="time"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đến lúc *</span>
              <input
                type="time"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
          </div>

          <p className="np-hint">
            Khai đúng khoảng anh/chị <b>KHÔNG có mặt</b> ở xưởng. Ví dụ ca
            07:30–16:30:
            <br />• Đi muộn 1 tiếng → vắng từ <b>07:30</b> đến <b>08:30</b>
            <br />• Về sớm 2 tiếng → vắng từ <b>14:30</b> đến <b>16:30</b>
            <br />• Nghỉ nửa buổi chiều → vắng từ <b>12:30</b> đến <b>16:30</b>
          </p>
          {timeErr ? (
            <p className="np-hint np-hint--warn">{timeErr}</p>
          ) : minutes != null && minutes > 0 ? (
            <p className="np-hint np-hint--ok">Nghỉ {elDurLong(minutes)}</p>
          ) : null}

          {/* {canDeduct && types.length > 0 && (
            <div className="el-stack">
              <label className="ns-check">
                <input
                  type="checkbox"
                  checked={deduct}
                  onChange={(e) => setDeduct(e.target.checked)}
                />
                Trừ vào phép năm — vẫn được trả lương phần vắng
              </label>
              {deduct ? (
                <>
                  <p className="np-hint np-hint--ok">
                    {leaveCong > 0
                      ? `Tiêu ${elNum(leaveCong)} ngày phép năm`
                      : "Khai giờ vắng để biết tiêu bao nhiêu ngày phép"}
                    {forEmployee
                      ? " · số dư của thợ được hệ thống kiểm khi lưu."
                      : leaveCong > 0
                        ? ` · Phép còn lại: ${elNum(remaining)} → ${elNum(Math.max(0, remaining - leaveCong))} ngày`
                        : ""}
                  </p>
                  <label className="ns-field el-field">
                    <span className="ns-field__label">Loại nghỉ</span>
                    <select
                      value={leaveTypeId ?? ""}
                      onChange={(e) =>
                        setLeaveTypeId(
                          e.target.value ? Number(e.target.value) : null,
                        )
                      }
                    >
                      {types.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {shortOfLeave && (
                    <div className="banner banner--warn el-stack">
                      <span>
                        Phép năm chỉ còn {elNum(remaining)} ngày — phiếu này cần{" "}
                        {elNum(leaveCong)} ngày. Bỏ tick để xin không lương (vẫn
                        không bị phạt).
                      </span>
                      <button
                        className="btn btn--ghost"
                        onClick={() => setDeduct(false)}
                      >
                        Bỏ tick, gửi không lương
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <p className="np-hint">
                  Không đụng quỹ phép · mất công phần vắng
                  {minutes != null && minutes > 0
                    ? ` (${elDurLong(minutes)})`
                    : ""}{" "}
                  · không bị phạt đi muộn.
                </p>
              )}
            </div>
          )} */}

          <label className="ns-field el-field">
            <span className="ns-field__label">Lý do</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="vd: con ốm, đưa đi khám"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy
              ? "Đang lưu…"
              : forEmployee
                ? "Tạo & duyệt luôn"
                : "Gửi phiếu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

export function LateEarlyTab({
  token,
  canApprove,
  onChanged,
  eventTick,
}: {
  token: string;
  canApprove: boolean;
  onChanged?: () => void;
  eventTick?: number;
}) {
  const [sub, setSub] = useState<"mine" | "queue">(
    canApprove ? "queue" : "mine",
  );
  // KHỞI TẠO `null` chứ KHÔNG phải `[]`: `[]` làm lúc đang fetch hiện "chưa có phiếu nào" — báo SAI.
  const [mine, setMine] = useState<LateEarlyRequest[] | null>(null);
  const [queue, setQueue] = useState<LateEarlyRequest[] | null>(null);
  const [hasEmployee, setHasEmployee] = useState(true);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [kindFilter, setKindFilter] = useState<Set<ElKind>>(new Set());
  const [pendingCount, setPendingCount] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState<null | "mine" | "for">(null);
  const [editing, setEditing] = useState<LateEarlyRequest | null>(null);
  const [rejecting, setRejecting] = useState<null | number[]>(null);
  // 2 state lỗi RIÊNG — dùng chung một `err` thì lỗi tab này hiện ở tab kia.
  const [errMine, setErrMine] = useState<string | null>(null);
  const [errQueue, setErrQueue] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [myShift, setMyShift] = useState<ElShift | null>(null);
  const [shiftById, setShiftById] = useState<Map<number, ElShift>>(new Map());
  const [roster, setRoster] = useState<ElRosterEmp[]>([]);

  useEffect(() => {
    // Ca của TÔI: `myStatus` là self-service (ai cũng gọi được) → nguồn ca cho tab "của tôi",
    // và là nguồn DUY NHẤT với người KHÔNG có quyền duyệt (họ không gọi được /roster).
    api.attendance
      .myStatus(token)
      .then((s) => setMyShift(elMakeShift(s.shift as MyShift | null)))
      .catch(() => setMyShift(null));
  }, [token]);

  // Roster của chính module `di_muon` (gác bằng `di_muon:approve`, backend đã lọc theo scope,
  // bỏ NV đã nghỉ và sắp theo tên). MỘT lời gọi nuôi cả dropdown "Khai hộ thợ" LẪN khung ca dùng
  // để suy kiểu vắng / vẽ mini-bar / tự điền giờ — khỏi phải mượn quyền `nhan_su:read`.
  useEffect(() => {
    if (!canApprove) return;
    api.lateEarly
      .roster(token)
      .then((r) => {
        setRoster(r.employees);
        const m = new Map<number, ElShift>();
        for (const s of r.shifts) {
          const sh = elShiftFromMinutes(s);
          if (sh) m.set(s.id, sh);
        }
        setShiftById(m);
      })
      .catch(() => {
        setRoster([]);
        setShiftById(new Map());
      });
  }, [token, canApprove]);

  const load = useCallback(() => {
    api.lateEarly
      .mine(token)
      .then((r) => {
        setHasEmployee(r.has_employee);
        setMine(r.items ?? []);
        setErrMine(null);
      })
      .catch((e) => {
        setMine([]);
        setErrMine(elErr(e));
      });
    if (canApprove) {
      api.lateEarly
        .list(token, statusFilter === "all" ? undefined : statusFilter)
        .then((r) => {
          setQueue(r.items);
          setErrQueue(null);
        })
        .catch((e) => {
          setQueue([]);
          setErrQueue(elErr(e));
        });
      api.lateEarly
        .summary(token)
        .then((s) => setPendingCount(s.pending_in_scope ?? 0))
        .catch(() => undefined);
    }
    // Hạ badge sidebar + chuông NGAY sau mỗi lần load (không bắt người dùng đổi màn).
    api.lateEarly.markSeen(token).catch(() => undefined);
    onChanged?.();
  }, [token, canApprove, statusFilter, onChanged]);

  // `eventTick` đổi = có sự kiện real-time (SSE) → tải lại bảng, khỏi bắt người dùng F5.
  useEffect(() => {
    load();
  }, [load, eventTick]);

  const shiftFor = useCallback(
    (r: LateEarlyRequest): ElShift | null => {
      const emp = roster.find((e) => e.id === r.employee_id);
      if (emp?.default_shift_id != null)
        return shiftById.get(emp.default_shift_id) ?? null;
      return null;
    },
    [roster, shiftById],
  );
  const shiftForMine = useCallback(
    (r: LateEarlyRequest): ElShift | null => myShift ?? shiftFor(r),
    [myShift, shiftFor],
  );

  // Chỉ hiện hàng chip lọc kiểu khi THỰC SỰ suy được kiểu — không thì nó lọc trắng bảng.
  const canInferKind = shiftById.size > 0 && roster.length > 0;
  const queueRows = useMemo(() => {
    if (!queue) return null;
    if (!canInferKind || kindFilter.size === 0) return queue;
    return queue.filter((r) => {
      const k = elKindOf(r.from_minute, r.to_minute, shiftFor(r));
      return k !== null && kindFilter.has(k);
    });
  }, [queue, kindFilter, canInferKind, shiftFor]);

  const selectable = useMemo(
    () =>
      new Set(
        (queueRows ?? [])
          .filter((r) => r.status === "pending")
          .map((r) => r.id),
      ),
    [queueRows],
  );
  const picked = useMemo(
    () => [...selected].filter((id) => selectable.has(id)),
    [selected, selectable],
  );

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleKind(k: ElKind) {
    setKindFilter((s) => {
      const next = new Set(s);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  async function run(fn: () => Promise<unknown>, scope: "mine" | "queue") {
    const setErr = scope === "mine" ? setErrMine : setErrQueue;
    setErr(null);
    setOkMsg(null);
    try {
      await fn();
      setSelected(new Set());
      load();
    } catch (e) {
      setErr(elErr(e));
    }
  }

  const showDecision = statusFilter !== "pending";

  return (
    <div>
      <div className="np-seg np-seg--tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={sub === "mine"}
          className={`np-seg__btn ${sub === "mine" ? "is-active" : ""}`}
          onClick={() => setSub("mine")}
        >
          Phiếu của tôi
        </button>
        {canApprove && (
          <button
            type="button"
            role="tab"
            aria-selected={sub === "queue"}
            className={`np-seg__btn ${sub === "queue" ? "is-active" : ""}`}
            onClick={() => setSub("queue")}
          >
            Duyệt phiếu{pendingCount ? ` (${pendingCount})` : ""}
          </button>
        )}
      </div>

      {okMsg && <div className="banner banner--success el-stack">{okMsg}</div>}

      {sub === "mine" && (
        <>
          <div className="cc-ts-toolbar">
            <div
              className="cc-info-card-note el-toolbar-grow"
              style={{ margin: 0, padding: "8px 12px" }}
            >
              <Info size={14} className="cc-note-icon" />
              <span>
                Khai đúng khoảng <b>không có mặt</b> ở xưởng. Phiếu được duyệt ={" "}
                <b>không bị phạt</b> đi muộn / về sớm đúng số phút đã xin.
              </span>
            </div>
            {hasEmployee && (
              <button
                className="btn btn--primary"
                onClick={() => setCreating("mine")}
              >
                <Plus size={14} /> Xin đi muộn / về sớm
              </button>
            )}
          </div>

          {!hasEmployee && (
            <div className="banner banner--warn el-stack">
              Tài khoản của bạn <b>chưa gắn hồ sơ nhân viên</b> nên chưa gửi
              phiếu được. Liên hệ HCNS.
            </div>
          )}
          {errMine && (
            <div className="banner banner--error el-stack">{errMine}</div>
          )}

          {mine === null ? (
            <p className="ns__empty">Đang tải phiếu…</p>
          ) : mine.length === 0 ? (
            <div className="el-empty">
              <p className="el-empty__title">
                Bạn chưa có phiếu đi muộn / về sớm nào.
              </p>
              <p className="el-empty__hint">
                Hôm nào đến muộn hoặc về sớm thì khai ở đây —{" "}
                <b>có phiếu được duyệt mới không bị phạt tiền</b>.
              </p>
              {hasEmployee && (
                <div className="el-empty__cta">
                  <button
                    className="btn btn--primary"
                    onClick={() => setCreating("mine")}
                  >
                    <Plus size={14} /> Xin đi muộn / về sớm
                  </button>
                </div>
              )}
            </div>
          ) : (
            <ElTable
              rows={mine}
              shiftFor={shiftForMine}
              showEmployee={false}
              selectable={false}
              showDecision
              selected={selected}
              onToggle={toggle}
              actions={(r) =>
                r.status === "pending" || r.status === "approved" ? (
                  <>
                    {r.status === "pending" && (
                      <button
                        className="btn btn--ghost"
                        onClick={() => setEditing(r)}
                      >
                        Sửa
                      </button>
                    )}
                    <button
                      className="btn btn--ghost cc-btn-reject"
                      onClick={() =>
                        run(() => api.lateEarly.cancel(token, r.id), "mine")
                      }
                    >
                      Hủy
                    </button>
                  </>
                ) : null
              }
            />
          )}
        </>
      )}

      {sub === "queue" && canApprove && (
        <>
          <div className="cc-ts-toolbar">
            <div className="cc-select-wrapper" style={{ width: "160px" }}>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setSelected(new Set());
                }}
                aria-label="Lọc theo trạng thái"
              >
                <option value="pending">Chờ duyệt</option>
                <option value="approved">Đã duyệt</option>
                <option value="rejected">Từ chối</option>
                <option value="all">Tất cả</option>
              </select>
            </div>
            {canInferKind && (
              <div className="el-filters el-toolbar-grow">
                {(Object.keys(EL_KIND_META) as ElKind[]).map((k) => {
                  const meta = EL_KIND_META[k];
                  return (
                    <button
                      key={k}
                      type="button"
                      className={`el-filter ${kindFilter.has(k) ? "is-on" : ""}`}
                      aria-pressed={kindFilter.has(k)}
                      onClick={() => toggleKind(k)}
                    >
                      <meta.Icon size={12} /> {meta.label}
                    </button>
                  );
                })}
              </div>
            )}
            <button
              className="btn btn--primary"
              onClick={() => setCreating("for")}
            >
              <Plus size={14} /> Khai hộ thợ
            </button>
          </div>

          {errQueue && (
            <div className="banner banner--error el-stack">{errQueue}</div>
          )}

          {picked.length > 0 && (
            <div className="cc-bulk-actions-floating">
              <span className="cc-bulk-label">
                Đã chọn {picked.length} phiếu
              </span>
              <div className="cc-bulk-btn-group">
                <button
                  className="btn btn--primary cc-btn-approve"
                  onClick={() =>
                    run(() => api.lateEarly.bulkApprove(token, picked), "queue")
                  }
                >
                  ✓ Duyệt {picked.length}
                </button>
                <button
                  className="btn btn--ghost cc-btn-reject"
                  onClick={() => setRejecting(picked)}
                >
                  ✕ Từ chối {picked.length}
                </button>
                <button
                  className="btn btn--ghost"
                  onClick={() => setSelected(new Set())}
                >
                  Bỏ chọn
                </button>
              </div>
            </div>
          )}

          {queueRows === null ? (
            <p className="ns__empty">Đang tải phiếu…</p>
          ) : queueRows.length === 0 ? (
            <div className="el-empty">
              <p className="el-empty__title">
                {statusFilter === "pending"
                  ? "Không có phiếu nào chờ bạn duyệt."
                  : "Không có phiếu nào khớp bộ lọc."}
              </p>
              {statusFilter === "pending" ? (
                <p className="el-empty__hint">
                  Đổi bộ lọc sang <b>Tất cả</b> để xem phiếu đã xử lý.
                </p>
              ) : kindFilter.size > 0 ? (
                <p className="el-empty__hint">
                  Bỏ bớt chip lọc kiểu để thấy thêm phiếu.
                </p>
              ) : null}
            </div>
          ) : (
            <ElTable
              rows={queueRows}
              shiftFor={shiftFor}
              showEmployee
              selectable
              showDecision={showDecision}
              selected={selected}
              onToggle={toggle}
              actions={(r) =>
                r.status === "pending" ? (
                  <div className="cc-approve-actions-cell">
                    <button
                      className="btn btn--primary cc-btn-approve"
                      onClick={() =>
                        run(() => api.lateEarly.approve(token, r.id), "queue")
                      }
                    >
                      Duyệt
                    </button>
                    <button
                      className="btn btn--ghost cc-btn-reject"
                      onClick={() => setRejecting([r.id])}
                    >
                      Từ chối
                    </button>
                  </div>
                ) : null
              }
            />
          )}
        </>
      )}

      {(creating || editing) && (
        <ElFormModal
          token={token}
          forEmployee={creating === "for"}
          editing={editing}
          myShift={myShift}
          shiftById={shiftById}
          roster={roster}
          mine={mine ?? []}
          onClose={() => {
            setCreating(null);
            setEditing(null);
          }}
          onSaved={(msg) => {
            setCreating(null);
            setEditing(null);
            setOkMsg(msg);
            load();
          }}
          onOpenExisting={(r) => {
            setCreating(null);
            setEditing(r);
            setSub("mine");
          }}
        />
      )}

      {rejecting && (
        <ElRejectModal
          count={rejecting.length}
          onClose={() => setRejecting(null)}
          onConfirm={(note) => {
            const ids = rejecting;
            setRejecting(null);
            run(
              () =>
                ids.length > 1
                  ? api.lateEarly.bulkReject(token, ids, note)
                  : api.lateEarly.reject(token, ids[0], note),
              "queue",
            );
          }}
        />
      )}
    </div>
  );
}
