// Tab Bảng công tháng (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type DayDetail,
  type HeSoNgay,
  type HolidayMark,
  type Timesheet,
  type TimesheetRow,
  type AttendancePeriod,
} from "../../../../api/client";
import {
  UserCheck,
  CalendarDays,
  Clock,
  Calendar,
  FileEdit,
  AlertTriangle,
  RefreshCw,
  Trash2,
  Lock,
  Unlock,
} from "lucide-react";
import { MonthPicker } from "../../../../components/MonthPicker";
import {
  FAULT_OPTIONS,
  FAULT_LABEL,
  HE_SO_NGAY_MAC_DINH,
  WEEKDAY_NAMES_SHORT,
} from "../shared/constants";
import {
  docONgay,
  soCong,
  congDacBiet,
  ngayDacBiet,
  getWeekdayIndex,
  getWeekdayLabel,
  isWeekend,
  getInitials,
} from "../shared/helpers";

// --- Tab: Bảng công tháng (HR) ----------------------------------------------

function EmployeeCalendarModal({
  employeeName,
  employeeRow,
  year,
  month,
  daysInMonth,
  heSoNgay,
  onClose,
}: {
  employeeName: string;
  employeeRow: TimesheetRow;
  year: number;
  month: number;
  daysInMonth: number;
  /** Hệ số quy đổi công lễ / nghỉ tuần từ Cấu hình lương — truyền xuống chứ không đọc lại,
   *  hai lịch phải nói cùng một con số. */
  heSoNgay: HeSoNgay;
  onClose: () => void;
}) {
  const startOffset = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Mon=0..Sun=6
  const calendarCells: (number | null)[] = [];
  for (let i = 0; i < startOffset; i++) {
    calendarCells.push(null);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    calendarCells.push(d);
  }

  // Calculate statistics for this employee
  let workedDays = 0;
  let totalOtMinutes = 0;
  let lateDays = 0;
  let earlyDays = 0;
  let leaveDays = 0;

  Object.values(employeeRow.days).forEach((day) => {
    if (day.leave) {
      leaveDays++;
    } else {
      if (day.first_in || day.last_out) {
        workedDays += day.cong ?? 1;
      }
      if (day.ot_minutes) {
        totalOtMinutes += day.ot_minutes;
      }
      if (day.late) {
        lateDays++;
      }
      if (day.early) {
        earlyDays++;
      }
    }
  });

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div
        className="ns-modal__box cc-emp-cal-modal-box"
        style={{ maxWidth: "700px" }}
      >
        <header className="ns-modal__head">
          <h2
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              margin: 0,
            }}
          >
            <Calendar size={18} /> Lịch công tháng {month}/{year} ·{" "}
            {employeeName}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {/* Summary metrics of the employee */}
          <div className="cc-emp-cal-summary-grid">
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Số ngày công</span>
              <span className="cc-emp-cal-summary-val">
                {employeeRow.total_cong ?? workedDays} công
              </span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Tổng giờ làm</span>
              <span className="cc-emp-cal-summary-val">
                {employeeRow.total_hours ?? 0}h
              </span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Tăng ca (OT)</span>
              <span className="cc-emp-cal-summary-val">
                {(totalOtMinutes / 60).toFixed(1)}h
              </span>
            </div>
            <div className="cc-emp-cal-summary-card">
              <span className="cc-emp-cal-summary-lbl">Muộn / Sớm</span>
              <span className="cc-emp-cal-summary-val text-warn">
                {lateDays} / {earlyDays} lần
              </span>
            </div>
          </div>

          {/* Calendar grid */}
          <div className="cc-month-grid" style={{ marginTop: "16px" }}>
            {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((w) => (
              <div
                key={w}
                style={{
                  textAlign: "center",
                  fontWeight: "bold",
                  fontSize: "11px",
                  paddingBottom: "6px",
                  color: "var(--ash)",
                }}
              >
                {w}
              </div>
            ))}
            {calendarCells.map((dayNum, idx) => {
              if (dayNum === null)
                return (
                  <div
                    key={`empty-${idx}`}
                    className="cc-month-cell cc-month-cell--empty"
                  />
                );

              const day = employeeRow.days[String(dayNum)];
              // CHUNG hàm với lịch tự phục vụ. Đoạn `if` cũ ở đây hỏi `day.leave` TRƯỚC nên ngày
              // lễ hiện thành "Nghỉ phép (P)" — HCNS và người lao động nhìn cùng một ngày mà đọc
              // ra hai chuyện khác nhau.
              const o = docONgay(day, heSoNgay);
              let cellClass = "cc-month-cell cc-emp-cal-cell" + o.variant;

              const currentDayOfWeek = new Date(
                year,
                month - 1,
                dayNum,
              ).getDay();
              const isWeekendCell =
                currentDayOfWeek === 0 || currentDayOfWeek === 6;
              if (!day && isWeekendCell) {
                cellClass += " cc-month-cell--weekend";
              }

              return (
                <div key={dayNum} className={cellClass}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <span className="cc-month-cell-num">{dayNum}</span>
                    <span className="cc-month-cell__pills">
                      {o.pills.map((p) => (
                        <span
                          key={p.text}
                          className={`cc-badge-pill cc-badge-pill--cell cc-badge-pill--${p.tone}`}
                          title={p.title}
                        >
                          {p.text}
                        </span>
                      ))}
                    </span>
                  </div>
                  {/* Tên CA của ngày (Phân ca tháng) — hiện DÙ có bấm hay không. Chủ hỏi
                      "điền ca từng ngày vào ô công". Bấm ô để đổi ca ở tab Khai ca. */}
                  {o.caLabel && (
                    <div className="cc-month-cell__ca" title={`Ca làm: ${o.caLabel}`}>
                      {o.caLabel}
                    </div>
                  )}
                  <div
                    style={{
                      fontSize: "11px",
                      fontWeight: 600,
                      color: "var(--ink)",
                      marginTop: "4px",
                    }}
                  >
                    {o.timeRange || "—"}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: "var(--ash)",
                      marginTop: "2px",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "2px",
                      justifyContent: "space-between",
                      width: "100%",
                    }}
                  >
                    <span>
                      {o.statusLabel}
                      {o.gain && <span className={o.gainClass}> {o.gain}</span>}
                    </span>
                    {day?.late && (
                      <span
                        style={{ color: "var(--signal)", fontWeight: "bold" }}
                      >
                        Muộn
                      </span>
                    )}
                    {day?.early && (
                      <span
                        style={{
                          color: "var(--amber-deep)",
                          fontWeight: "bold",
                        }}
                      >
                        Sớm
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

export function TimesheetTab({
  token,
  canAdjust,
  canLock,
}: {
  token: string;
  canAdjust: boolean;
  /** Ô "Chốt kỳ công / Mở lại kỳ" — TÁCH khỏi ô Chấm bù từ đợt 4 (10/08/2026).
   *
   *  ⚠️ Trước 11/08/2026 hai nút này gác bằng `canAdjust` (ô Chấm bù) trong khi máy chủ đòi
   *  `cham_cong:lock` ⇒ sai CẢ HAI CHIỀU: có Chấm bù mà không có Chốt kỳ thì vẫn thấy nút rồi bấm
   *  ăn 403; có Chốt kỳ mà không có Chấm bù thì không thấy nút dù máy chủ cho phép. */
  canLock: boolean;
}) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [data, setData] = useState<Timesheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [deptId, setDeptId] = useState<number | "">("");
  const [depts, setDepts] = useState<{ id: number; name: string }[]>([]);
  const [openDay, setOpenDay] = useState<{
    employeeId: number;
    employeeName: string;
    date: string;
  } | null>(null);
  const [period, setPeriod] = useState<AttendancePeriod | null>(null);
  const [periodBusy, setPeriodBusy] = useState(false);
  const [periodMsg, setPeriodMsg] = useState<{
    text: string;
    type: "success" | "error";
  } | null>(null);
  const [selectedEmployeeCal, setSelectedEmployeeCal] = useState<{
    row: TimesheetRow;
    name: string;
  } | null>(null);
  // Hàng đang mở drawer "Công đặc biệt" — cột chỉ nói tổng, drawer nói từng ngày.
  const [specialFor, setSpecialFor] = useState<TimesheetRow | null>(null);
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    api.employees
      .meta(token)
      .then((m) => setDepts(m.departments))
      .catch(() => setDepts([]));
  }, [token]);

  const loadPeriod = useCallback(() => {
    api.attendance
      .period(token, year, month)
      .then(setPeriod)
      .catch(() => setPeriod(null));
  }, [token, year, month]);
  useEffect(() => {
    loadPeriod();
    setPeriodMsg(null);
  }, [loadPeriod]);

  const reload = useCallback(() => {
    setLoading(true);
    api.attendance
      .timesheet(token, year, month, deptId === "" ? null : deptId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [token, year, month, deptId]);
  useEffect(() => {
    reload();
  }, [reload]);

  async function doLockPeriod() {
    setPeriodBusy(true);
    setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.lockPeriod(token, year, month));
      setPeriodMsg({ text: "Đã chốt công tháng.", type: "success" });
    } catch (e) {
      setPeriodMsg({
        text: e instanceof Error ? e.message : "Lỗi khi chốt công.",
        type: "error",
      });
    } finally {
      setPeriodBusy(false);
    }
  }
  async function doReopenPeriod() {
    setPeriodBusy(true);
    setPeriodMsg(null);
    try {
      setPeriod(await api.attendance.reopenPeriod(token, year, month));
      setPeriodMsg({ text: "Đã mở lại kỳ công.", type: "success" });
    } catch (e) {
      setPeriodMsg({
        text: e instanceof Error ? e.message : "Lỗi khi mở kỳ công.",
        type: "error",
      });
    } finally {
      setPeriodBusy(false);
    }
  }

  function openCell(employeeId: number, employeeName: string, dayNum: number) {
    const date = `${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
    setOpenDay({ employeeId, employeeName, date });
  }

  async function exportCsv() {
    setDownloading(true);
    try {
      const url = await api.attendance.timesheetCsvBlobUrl(
        token,
        year,
        month,
        deptId === "" ? null : deptId,
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `bang-cong-${year}-${String(month).padStart(2, "0")}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  const days = data
    ? Array.from({ length: data.days_in_month }, (_, i) => i + 1)
    : [];

  // Dynamic KPIs calculations
  const totalEmployees = data?.rows.length ?? 0;
  let totalCong = 0;
  let totalHours = 0;
  if (data?.rows) {
    for (const r of data.rows) {
      totalCong += r.total_cong ?? r.total_days ?? 0;
      totalHours += r.total_hours ?? 0;
    }
  }

  return (
    <div>
      {/* 1. Dynamic Month KPI Dashboard */}
      <div className="cc-ts-kpi-strip">
        <div className="cc-ts-kpi-card cc-ts-kpi-card--total">
          <div className="cc-ts-kpi-icon">
            <UserCheck size={18} />
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">{totalEmployees}</span>
            <span className="cc-ts-kpi-label">Tổng nhân sự</span>
          </div>
        </div>
        <div className="cc-ts-kpi-card cc-ts-kpi-card--cong">
          <div className="cc-ts-kpi-icon">
            <CalendarDays size={18} />
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">{totalCong.toFixed(1)}</span>
            <span className="cc-ts-kpi-label">Tổng ngày công</span>
          </div>
        </div>
        <div className="cc-ts-kpi-card cc-ts-kpi-card--hours">
          <div className="cc-ts-kpi-icon">
            <Clock size={18} />
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">{totalHours.toFixed(1)}h</span>
            <span className="cc-ts-kpi-label">Tổng giờ làm</span>
          </div>
        </div>
        <div
          className={`cc-ts-kpi-card cc-ts-kpi-card--period ${period?.status === "locked" ? "is-locked" : "is-draft"}`}
        >
          <div className="cc-ts-kpi-icon">
            {period?.status === "locked" ? (
              <Lock size={18} />
            ) : (
              <Unlock size={18} />
            )}
          </div>
          <div className="cc-ts-kpi-info">
            <span className="cc-ts-kpi-num">
              {period?.status === "locked" ? "Đã chốt" : "Bản nháp"}
            </span>
            <span className="cc-ts-kpi-label">
              {period?.status === "locked"
                ? `Khóa băng ${period.line_count} NV`
                : `${(period?.hanging_days ?? 0) > 0 ? `${period?.hanging_days} ngày treo` : "Kỳ công hiện tại"}`}
            </span>
          </div>
        </div>
      </div>

      {/* Warning banner for pending checks */}
      {period &&
        period.status !== "locked" &&
        (period.hanging_days > 0 ||
          period.pending_leaves +
            period.pending_adjusts +
            period.pending_late_early +
            (period.pending_overtime ?? 0) >
            0) && (
          <div
            className="banner banner--warn cc-ts-warn-banner"
            style={{ marginBottom: "16px" }}
          >
            <AlertTriangle size={14} style={{ marginRight: "6px" }} />
            <span>
              Kỳ công có <strong>{period.hanging_days}</strong> ngày treo (thiếu
              chấm RA) và{" "}
              <strong>
                {period.pending_leaves +
                  period.pending_adjusts +
                  period.pending_late_early +
                  (period.pending_overtime ?? 0)}
              </strong>{" "}
              đơn chờ duyệt (nghỉ phép · đi muộn–về sớm · tăng ca · chỉnh công).
            </span>
          </div>
        )}

      {/* L3 — kỳ ĐÃ CHỐT nhưng vẫn có lượt bấm mới. Băng này là thứ DUY NHẤT cho người dùng biết:
          ảnh chụp không có mấy lượt đó, nên Bảng lương cũng không tính. Không chặn thợ bấm giờ —
          chỉ nhắc HCNS chốt lại kỳ. */}
      {period && period.status === "locked" && (period.phat_sinh_sau_chot ?? 0) > 0 && (
        <div
          className="banner banner--warn cc-ts-warn-banner"
          style={{ marginBottom: "16px" }}
        >
          <AlertTriangle size={14} style={{ marginRight: "6px" }} />
          <span>
            Kỳ công đã chốt nhưng có <strong>{period.phat_sinh_sau_chot}</strong> lượt bấm ghi
            vào sau đó — <strong>ảnh chụp không có mấy lượt này</strong>, nên Bảng lương cũng
            không tính. Mở lại kỳ công rồi chốt lại để cập nhật.
          </span>
        </div>
      )}

      {periodMsg && (
        <div
          className={`banner ${periodMsg.type === "error" ? "banner--error" : "banner--ok"} cc-ts-msg-banner`}
          style={{ marginBottom: "16px" }}
        >
          {periodMsg.text}
        </div>
      )}

      {/* 2. Redesigned Filter & Actions Bar */}
      <div className="cc-ts-header-actions">
        <div className="cc-ts-filters">
          <MonthPicker
            value={ym}
            onChange={setYm}
            className="cc-ts-input-month"
            ariaLabel="Kỳ chấm công"
          />
          <select
            value={deptId}
            onChange={(e) =>
              setDeptId(e.target.value === "" ? "" : Number(e.target.value))
            }
            className="cc-ts-select-dept"
          >
            <option value="">Tất cả phòng/tổ</option>
            {depts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <div className="cc-ts-legend-strip">
            <span className="cc-ts-legend-item cc-ts-legend-item--work">
              Công
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--late">
              Muộn
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--early">
              Sớm
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--leave">
              Nghỉ/Phép
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--ot">
              OT (+)
            </span>
          </div>
        </div>

        <div className="cc-ts-actions">
          <button
            className="btn btn--ghost cc-ts-btn-export"
            onClick={exportCsv}
            disabled={downloading || !data?.rows.length}
          >
            {downloading ? (
              <RefreshCw className="cc-animate-spin" size={14} />
            ) : (
              <FileEdit size={14} />
            )}
            <span>{downloading ? "Đang xuất…" : "Xuất CSV"}</span>
          </button>

          {canLock && period && (
            <div className="cc-ts-action-lock-wrapper">
              {period.status === "draft" ? (
                <button
                  className="btn btn--primary cc-ts-btn-lock"
                  onClick={doLockPeriod}
                  disabled={periodBusy}
                >
                  <Lock size={14} />
                  <span>{periodBusy ? "Đang khóa…" : "Chốt công tháng"}</span>
                </button>
              ) : (
                <button
                  className="btn btn--ghost cc-ts-btn-unlock"
                  onClick={doReopenPeriod}
                  disabled={periodBusy || period.payroll_locked}
                  title={
                    period.payroll_locked
                      ? "Kỳ lương đã chốt — không mở lại kỳ công"
                      : ""
                  }
                >
                  <Unlock size={14} />
                  <span>{periodBusy ? "Đang mở…" : "Mở lại kỳ công"}</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 3. Timesheet Scroll Table */}
      {loading && <p className="ns__empty">Đang tải biểu công…</p>}
      {!loading && data && (
        <div className="cc-timesheet-scroll-container">
          <table className="cc-timesheet-table">
            <thead>
              <tr>
                <th className="cc-sticky-col-code">Mã</th>
                <th className="cc-sticky-col-name">Họ tên</th>
                <th>Ca</th>
                {days.map((d) => {
                  const label = getWeekdayLabel(year, month, d);
                  const weekend = isWeekend(year, month, d);
                  return (
                    <th
                      key={d}
                      className={`cc-day-hdr-v2 ${weekend ? "cc-day-hdr-v2--weekend" : ""}`}
                    >
                      <div className="cc-day-hdr-v2-weekday">{label}</div>
                      <div className="cc-day-hdr-v2-num">{d}</div>
                    </th>
                  );
                })}
                <th>Công</th>
                {/* MỘT cột cho cả ba loại công đặc biệt — bảng này đã 31 cột ngày, thêm ba cột
                    riêng là đẩy cột Giờ ra khỏi màn 1440px. Chi tiết từng ngày nằm trong drawer. */}
                <th>Công đặc biệt</th>
                <th>Giờ</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <TimesheetRowView
                  key={r.employee_id}
                  row={r}
                  days={days}
                  isWeekend={(d) => isWeekend(year, month, d)}
                  onCellClick={(dayNum) =>
                    openCell(r.employee_id, r.employee_name, dayNum)
                  }
                  onNameClick={() =>
                    setSelectedEmployeeCal({ row: r, name: r.employee_name })
                  }
                  onSpecialClick={() => setSpecialFor(r)}
                />
              ))}
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={days.length + 6} className="ns__empty">
                    Chưa có dữ liệu chấm công tháng này.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {openDay && (
        <DayDetailModal
          token={token}
          canAdjust={canAdjust}
          employeeId={openDay.employeeId}
          employeeName={openDay.employeeName}
          date={openDay.date}
          onClose={() => setOpenDay(null)}
          onChanged={reload}
        />
      )}

      {selectedEmployeeCal && (
        <EmployeeCalendarModal
          employeeName={selectedEmployeeCal.name}
          employeeRow={selectedEmployeeCal.row}
          year={year}
          month={month}
          daysInMonth={data?.days_in_month ?? 30}
          heSoNgay={data?.he_so_ngay ?? HE_SO_NGAY_MAC_DINH}
          onClose={() => setSelectedEmployeeCal(null)}
        />
      )}

      {specialFor && (
        <CongDacBietDrawer
          row={specialFor}
          year={year}
          month={month}
          heSoNgay={data?.he_so_ngay ?? HE_SO_NGAY_MAC_DINH}
          holidays={data?.holidays ?? []}
          onClose={() => setSpecialFor(null)}
        />
      )}
    </div>
  );
}

/** Drawer "Công đặc biệt": từng ngày lễ / nghỉ tuần / ngày nghỉ công ty CÓ ĐI LÀM, kèm số công
 *  quy đổi. Đây là chỗ trả lời câu hỏi tiền — nên nói luôn VÌ SAO lễ và Chủ nhật khác hệ số,
 *  đừng bắt kế toán đi tra Sổ tay mới hiểu con số trên màn. */
function CongDacBietDrawer({
  row,
  year,
  month,
  heSoNgay,
  holidays,
  onClose,
}: {
  row: TimesheetRow;
  year: number;
  month: number;
  heSoNgay: HeSoNgay;
  holidays: HolidayMark[];
  onClose: () => void;
}) {
  const tenLe = useMemo(
    () => new Map(holidays.map((h) => [h.day, h.name])),
    [holidays],
  );
  const dong = useMemo(
    () => ngayDacBiet(row, heSoNgay, tenLe, year, month),
    [row, heSoNgay, tenLe, year, month],
  );
  const tongQuyDoi = soCong(dong.reduce((s, d) => s + d.quyDoi, 0));

  return (
    <div
      className="cc-sp-drawer"
      role="dialog"
      aria-label={`Công đặc biệt — ${row.employee_name}`}
    >
      <div className="cc-sp-drawer__backdrop" onClick={onClose} />
      <div className="cc-sp-drawer__panel">
        <div className="cc-sp-drawer__head">
          <div>
            <div className="cc-sp-drawer__title">Công đặc biệt</div>
            <div className="cc-sp-drawer__sub">
              {row.employee_name} · tháng {month}/{year}
            </div>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </div>
        <p className="cc-note">
          Ngày lễ đi làm tính {soCong(heSoNgay.le)} công (1 công tiền lễ + phần
          làm thêm ngày lễ). Ngày nghỉ tuần đi làm tính{" "}
          {soCong(heSoNgay.nghi_tuan)} công. Ngày công ty cho nghỉ mà vẫn đi làm
          tính 1 công, không hệ số.
        </p>
        {dong.length === 0 ? (
          <p className="ns__empty">
            Tháng này không có ngày lễ / nghỉ tuần nào đi làm.
          </p>
        ) : (
          <>
            <ul className="cc-sp-hist">
              {dong.map((d) => (
                <li key={d.ngay} className="cc-sp-hist__item">
                  <div className="cc-sp-hist__body">
                    <div className="cc-sp-hist__top">
                      <span className="cc-sp-hist__name">
                        {WEEKDAY_NAMES_SHORT[getWeekdayIndex(year, month, d.ngay)]}{" "}
                        {String(d.ngay).padStart(2, "0")}/
                        {String(month).padStart(2, "0")} · {d.loai}
                      </span>
                      <span className={`cc-badge-pill cc-badge-pill--${d.tone}`}>
                        {d.cong} → {d.quyDoi} công
                      </span>
                    </div>
                    <div className="cc-sp-hist__range">{d.ten}</div>
                  </div>
                </li>
              ))}
            </ul>
            <div className="cc-ts-special__total">
              <span>Tổng quy đổi</span>
              <b>{tongQuyDoi} công</b>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TimesheetRowView({
  row,
  days,
  isWeekend,
  onCellClick,
  onNameClick,
  onSpecialClick,
}: {
  row: TimesheetRow;
  days: number[];
  isWeekend: (dayNum: number) => boolean;
  onCellClick?: (dayNum: number) => void;
  onNameClick?: () => void;
  onSpecialClick?: () => void;
}) {
  const chipsDacBiet = congDacBiet(row);
  const clickable = !!onCellClick;
  const cellProps = (d: number) =>
    clickable
      ? {
          role: "button" as const,
          tabIndex: 0,
          onClick: () => onCellClick!(d),
          style: { cursor: "pointer" },
        }
      : {};
  return (
    <tr>
      <td className="cc-sticky-col-code">{row.employee_code}</td>
      <td className="cc-sticky-col-name">
        <div className="cc-name-cell-wrapper">
          <span className="cc-name-avatar">
            {getInitials(row.employee_name)}
          </span>
          <span
            className="cc-name-link"
            onClick={onNameClick}
            title="Xem lịch công tháng"
          >
            {row.employee_name}
          </span>
        </div>
      </td>
      <td>{row.shift_name ?? "—"}</td>
      {days.map((d) => {
        const isWe = isWeekend(d);
        const day = row.days[String(d)];
        const cellClass = `cc-day-cell ${isWe ? "cc-day-cell--weekend" : ""}`;

        if (!day) return <td key={d} className={cellClass} {...cellProps(d)} />;

        if (day.leave) {
          const leaveLabel = day.leave_paid ? "P" : "KL";
          return (
            <td key={d} className={cellClass} {...cellProps(d)}>
              <span
                className="cc-cell-badge cc-cell-badge--leave"
                title={`Nghỉ: ${day.leave}`}
              >
                {leaveLabel}
              </span>
            </td>
          );
        }

        // Formulate badge classes
        let badgeClass = "cc-cell-badge";
        if (day.late) badgeClass += " cc-cell-badge--late";
        else if (day.early) badgeClass += " cc-cell-badge--early";
        else badgeClass += " cc-cell-badge--work";

        const label =
          day.cong != null
            ? String(day.cong)
            : day.hours != null
              ? `${day.hours}h`
              : "•";
        const tip =
          `${day.first_in ?? "?"}–${day.last_out ?? "?"}` +
          (day.late ? " · đi muộn" : "") +
          (day.early ? " · về sớm" : "") +
          (day.ot_minutes ? ` · OT ${day.ot_minutes}′` : "") +
          (day.night ? " · ca đêm" : "");

        return (
          <td key={d} className={cellClass} {...cellProps(d)}>
            <span className={badgeClass} title={tip}>
              {label}
              {day.ot_minutes ? (
                <span
                  className="cc-cell-ot-dot"
                  title={`Tăng ca: ${day.ot_minutes}′`}
                >
                  +
                </span>
              ) : null}
            </span>
          </td>
        );
      })}
      <td style={{ fontWeight: "bold", textAlign: "center" }}>
        {row.total_cong != null ? row.total_cong : row.total_days}
      </td>
      {/* KHÔNG flex trên <td> (layout bảng vỡ ở Safari/Firefox) — bọc trong <button> rồi flex ở đó. */}
      <td style={{ textAlign: "center" }}>
        {chipsDacBiet.length === 0 ? (
          <span style={{ color: "var(--ash-2)" }}>—</span>
        ) : (
          <button
            type="button"
            className="cc-ts-special"
            onClick={onSpecialClick}
            title="Xem từng ngày và số công quy đổi"
          >
            {chipsDacBiet.map((c) => (
              <span
                key={c.text}
                className={`cc-badge-pill cc-badge-pill--${c.tone}`}
              >
                {c.text}
              </span>
            ))}
          </button>
        )}
      </td>
      <td style={{ fontWeight: "bold", textAlign: "center" }}>
        {row.total_hours}h
      </td>
    </tr>
  );
}

// "Ô biết nói": chi tiết punch 1 ngày của 1 NV + chấm bù/sửa (fault_party) có audit.

function DayDetailModal({
  token,
  canAdjust,
  employeeId,
  employeeName,
  date,
  onClose,
  onChanged,
}: {
  token: string;
  canAdjust: boolean;
  employeeId: number;
  employeeName: string;
  date: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<DayDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkType, setCheckType] = useState<"in" | "out">("in");
  const [time, setTime] = useState("08:00");
  const [fault, setFault] = useState("nv_quen");
  const [reason, setReason] = useState("");
  // Chấm bù CẶP tăng ca (1 chạm) khi NV có phiếu TC nhưng thiếu cặp chấm — điền sẵn theo khung phiếu.
  const [otIn, setOtIn] = useState("");
  const [otOut, setOtOut] = useState("");
  const [otBusy, setOtBusy] = useState(false);

  const load = useCallback(() => {
    api.attendance
      .day(token, employeeId, date)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [token, employeeId, date]);
  useEffect(() => {
    load();
  }, [load]);
  // Điền sẵn giờ vào/ra tăng ca theo phiếu khi có gợi ý (HCNS chỉnh lại giờ ra thực tế rồi lưu).
  const sugFrom = detail?.ot_suggestion?.from_time;
  const sugTo = detail?.ot_suggestion?.to_time;
  useEffect(() => {
    if (sugFrom && sugTo) {
      setOtIn(sugFrom);
      setOtOut(sugTo);
    }
  }, [sugFrom, sugTo]);

  async function addPunch() {
    if (!reason.trim()) {
      setError("Phải nhập lý do.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const d = await api.attendance.adjust(token, {
        employee_id: employeeId,
        date,
        check_type: checkType,
        time,
        reason: reason.trim(),
        fault_party: fault,
      });
      setDetail(d);
      setReason("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi chấm bù.");
    } finally {
      setBusy(false);
    }
  }

  async function removePunch(logId: number) {
    setBusy(true);
    setError(null);
    try {
      const d = await api.attendance.deleteManualLog(
        token,
        logId,
        employeeId,
        date,
      );
      setDetail(d);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi xóa.");
    } finally {
      setBusy(false);
    }
  }

  // Chấm bù cặp tăng ca: thêm lượt VÀO rồi RA (2 punch) → engine tự gom thành phiên tăng ca.
  async function addOtPair() {
    if (!otIn || !otOut) {
      setError("Nhập đủ giờ vào và ra tăng ca.");
      return;
    }
    if (otOut <= otIn) {
      setError("Giờ ra tăng ca phải sau giờ vào.");
      return;
    }
    setOtBusy(true);
    setError(null);
    const reasonTxt = "Chấm bù cặp tăng ca (NV quên chấm)";
    try {
      await api.attendance.adjust(token, {
        employee_id: employeeId,
        date,
        check_type: "in",
        time: otIn,
        reason: reasonTxt,
        fault_party: "nv_quen",
      });
      const d = await api.attendance.adjust(token, {
        employee_id: employeeId,
        date,
        check_type: "out",
        time: otOut,
        reason: reasonTxt,
        fault_party: "nv_quen",
      });
      setDetail(d);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi chấm bù cặp tăng ca.");
      load(); // tải lại: có thể lượt VÀO đã thêm nhưng RA lỗi
    } finally {
      setOtBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>Chi tiết chấm công</h2>
            <p className="cc-modal-subtitle">
              {employeeName} · Ngày {date}
            </p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error">{error}</div>}
          {!detail ? (
            <p className="ns__empty">Đang tải…</p>
          ) : (
            <>
              {/* Summary Strip */}
              <div className="cc-day-summary-strip">
                <div className="cc-day-summary-item">
                  <span className="cc-day-summary-lbl">Ca làm việc</span>
                  <span className="cc-day-summary-val cc-badge-shift">
                    {detail.shift_name ?? "Chưa gán"}
                  </span>
                </div>
                <div className="cc-day-summary-item">
                  <span className="cc-day-summary-lbl">Ngày công</span>
                  <span className="cc-day-summary-val cc-badge-cong">
                    {detail.cong != null ? detail.cong : "—"}
                  </span>
                </div>
                {detail.reason && (
                  <div className="cc-day-summary-item">
                    <span className="cc-day-summary-lbl">Cảnh báo</span>
                    <span className="cc-day-summary-val cc-badge-warn">
                      ⚠ {detail.reason}
                    </span>
                  </div>
                )}
              </div>

              {/* Punch Timeline */}
              <div className="cc-punch-timeline-container">
                <h4 className="cc-section-title-mini">
                  Lịch sử lượt chấm công
                </h4>
                <div className="cc-timeline-flow">
                  {detail.punches.map((p, idx) => {
                    const isIn = p.check_type === "in";
                    return (
                      <div className="cc-timeline-item" key={p.id}>
                        <div className="cc-timeline-connector">
                          <div
                            className={`cc-timeline-dot ${isIn ? "is-in" : "is-out"}`}
                          />
                          {idx < detail.punches.length - 1 && (
                            <div className="cc-timeline-line" />
                          )}
                        </div>
                        <div className="cc-timeline-content">
                          <div className="cc-timeline-header">
                            <span className="cc-timeline-time">{p.time}</span>
                            <span
                              className={`cc-timeline-badge ${isIn ? "is-in" : "is-out"}`}
                            >
                              {isIn ? "VÀO" : "RA"}
                            </span>
                            <span
                              className={`cc-timeline-source ${p.is_manual ? "is-manual" : "is-gps"}`}
                            >
                              {p.is_manual ? "Chấm bù" : "GPS"}
                            </span>
                          </div>
                          {p.is_manual && (
                            <div className="cc-timeline-details">
                              {p.fault_party && (
                                <span className="cc-fault-party">
                                  {FAULT_LABEL[p.fault_party] ?? p.fault_party}
                                </span>
                              )}
                              {p.adjust_reason && (
                                <span className="cc-adjust-reason">
                                  {" "}
                                  · {p.adjust_reason}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        {p.is_manual && canAdjust && (
                          <button
                            className="cc-btn-timeline-delete"
                            onClick={() => removePunch(p.id)}
                            disabled={busy}
                            title="Xóa lượt chấm này"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                  {detail.punches.length === 0 && (
                    <p
                      className="ns__empty"
                      style={{ padding: "16px 0", textAlign: "center" }}
                    >
                      Ngày này chưa có lượt chấm nào.
                    </p>
                  )}
                </div>
              </div>

              {/* Nhắc + nút 1 chạm: NV có phiếu TC đã duyệt nhưng thiếu cặp chấm tăng ca */}
              {canAdjust && detail.ot_suggestion && (
                <div className="cc-ot-suggest">
                  <h4 className="cc-ot-suggest__title">
                    <AlertTriangle size={14} /> Chưa chấm cặp tăng ca — phiếu{" "}
                    {detail.ot_suggestion.from_time}–
                    {detail.ot_suggestion.to_time}
                  </h4>
                  <p className="cc-ot-suggest__hint">
                    Giờ điền sẵn theo phiếu; sửa <b>giờ ra</b> theo thực tế rồi
                    lưu.
                  </p>
                  <div className="cc-ot-suggest__grid">
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Vào tăng ca</span>
                      <div className="cc-input-time-wrapper">
                        <input
                          type="time"
                          value={otIn}
                          onChange={(e) => setOtIn(e.target.value)}
                        />{" "}
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">
                        Ra tăng ca (thực tế)
                      </span>
                      <div className="cc-input-time-wrapper">
                        <input
                          type="time"
                          value={otOut}
                          onChange={(e) => setOtOut(e.target.value)}
                        />{" "}
                      </div>
                    </div>
                  </div>
                  <div className="cc-adjust-action-row">
                    <button
                      className="btn cc-btn-add-punch"
                      onClick={addOtPair}
                      disabled={otBusy}
                    >
                      {otBusy ? (
                        <RefreshCw className="cc-animate-spin" size={14} />
                      ) : (
                        "Chấm bù cặp tăng ca"
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Form Adjust */}
              {canAdjust && (
                <div className="cc-adjust-section">
                  <h4 className="cc-section-title-mini">Chấm bù / sửa</h4>
                  <div className="cc-adjust-grid">
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Loại chấm</span>
                      <div className="cc-select-wrapper">
                        <select
                          value={checkType}
                          onChange={(e) =>
                            setCheckType(e.target.value as "in" | "out")
                          }
                        >
                          <option value="in">VÀO</option>
                          <option value="out">RA</option>
                        </select>
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Giờ</span>
                      <div className="cc-input-time-wrapper">
                        <input
                          type="time"
                          value={time}
                          onChange={(e) => setTime(e.target.value)}
                        />{" "}
                      </div>
                    </div>
                    <div className="cc-adjust-field">
                      <span className="cc-field-label">Nguyên nhân</span>
                      <div className="cc-select-wrapper">
                        <select
                          value={fault}
                          onChange={(e) => setFault(e.target.value)}
                        >
                          {FAULT_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>

                  <div className="cc-adjust-field" style={{ marginTop: 14 }}>
                    <span className="cc-field-label">
                      Lý do (bắt buộc, ghi vào nhật ký)
                    </span>
                    <input
                      className="cc-input-text"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="vd: NV quên chấm ra, đã xác minh…"
                    />
                  </div>

                  <div className="cc-adjust-action-row">
                    <button
                      className="btn btn--primary cc-btn-add-punch"
                      onClick={addPunch}
                      disabled={busy}
                    >
                      {busy ? (
                        <RefreshCw className="cc-animate-spin" size={14} />
                      ) : (
                        "Thêm punch chấm bù"
                      )}
                    </button>
                  </div>

                  <div className="cc-info-card-note">
                    <AlertTriangle size={14} className="cc-note-icon" />
                    <span>
                      Công được <b>tự động tính lại</b> từ các lượt chấm (punch)
                      — không ghi đè trực tiếp con số. Mọi thao tác đều được lưu
                      nhật ký kiểm toán.
                    </span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}
