import { useEffect } from "react";
import type { HeSoNgay, TimesheetRow } from "../../../../api/client";
import {
  Calendar,
  Clock,
  UserCheck,
  Zap,
  AlertTriangle,
  X,
} from "lucide-react";
import { docONgay, getInitials, soCong } from "../shared/helpers";

export interface EmployeeCalendarModalProps {
  employeeName: string;
  employeeRow: TimesheetRow;
  year: number;
  month: number;
  daysInMonth: number;
  /** Hệ số quy đổi công lễ / nghỉ tuần từ Cấu hình lương — truyền xuống chứ không đọc lại,
   *  hai lịch phải nói cùng một con số. */
  heSoNgay: HeSoNgay;
  onClose: () => void;
  onSelectDay?: (dayNum: number) => void;
}

const WEEKDAYS = [
  { key: "t2", label: "T2", isWeekend: false },
  { key: "t3", label: "T3", isWeekend: false },
  { key: "t4", label: "T4", isWeekend: false },
  { key: "t5", label: "T5", isWeekend: false },
  { key: "t6", label: "T6", isWeekend: false },
  { key: "t7", label: "T7", isWeekend: true },
  { key: "cn", label: "CN", isWeekend: true },
];

export function EmployeeCalendarModal({
  employeeName,
  employeeRow,
  year,
  month,
  daysInMonth,
  heSoNgay,
  onClose,
  onSelectDay,
}: EmployeeCalendarModalProps) {
  // Lắng nghe phím Escape để đóng modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const startOffset = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Mon=0..Sun=6
  const calendarCells: (number | null)[] = [];
  for (let i = 0; i < startOffset; i++) {
    calendarCells.push(null);
  }
  for (let d = 1; d <= daysInMonth; d++) {
    calendarCells.push(d);
  }

  // Thống kê chỉ số cho nhân viên
  let workedDays = 0;
  let totalOtMinutes = 0;
  let lateDays = 0;
  let earlyDays = 0;
  let leaveDays = 0;

  Object.values(employeeRow.days || {}).forEach((day) => {
    if (day.leave) {
      leaveDays++;
    }
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
  });

  const totalCong = employeeRow.total_cong ?? workedDays;
  const totalHours = employeeRow.total_hours ?? 0;
  const avgHoursPerDay =
    totalCong > 0 ? (totalHours / totalCong).toFixed(1) : "0";
  const otHours = (totalOtMinutes / 60).toFixed(1);

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div
        className="ns-modal__box cc-emp-cal-modal-box"
        style={{ maxWidth: "1020px", width: "95vw" }}
      >
        {/* Header modal */}
        <header className="ns-modal__head cc-emp-cal-header">
          <div className="cc-emp-cal-profile">
            <div className="cc-emp-cal-avatar">
              {getInitials(employeeName)}
            </div>
            <div className="cc-emp-cal-info">
              <div className="cc-emp-cal-name-row">
                <h2 className="cc-emp-cal-name">{employeeName}</h2>
                <div className="cc-emp-cal-month-badge">
                  <Calendar size={14} /> Tháng {month}/{year}
                </div>
              </div>
              <div className="cc-emp-cal-badges">
                {employeeRow.employee_code && (
                  <span className="cc-emp-cal-badge cc-emp-cal-badge--code">
                    #{employeeRow.employee_code}
                  </span>
                )}
                {employeeRow.department_name && (
                  <span className="cc-emp-cal-badge cc-emp-cal-badge--dept">
                    {employeeRow.department_name}
                  </span>
                )}
                {employeeRow.shift_name && (
                  <span className="cc-emp-cal-badge cc-emp-cal-badge--shift">
                    {employeeRow.shift_name}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="ns-modal__x cc-emp-cal-close-btn"
            onClick={onClose}
            title="Đóng (Esc)"
            aria-label="Đóng"
          >
            <X size={18} />
          </button>
        </header>

        {/* Modal body */}
        <div className="ns-modal__body cc-emp-cal-body">
          {/* 4 Thẻ KPI */}
          <div className="cc-emp-cal-kpi-grid">
            <div className="cc-emp-cal-kpi-card">
              <div className="cc-emp-cal-kpi-icon cc-emp-cal-kpi-icon--moss">
                <UserCheck size={18} />
              </div>
              <div className="cc-emp-cal-kpi-content">
                <span className="cc-emp-cal-kpi-label">Ngày công thực tế</span>
                <span className="cc-emp-cal-kpi-val">
                  {employeeRow.total_cong ?? workedDays} công
                </span>
                <span className="cc-emp-cal-kpi-sub">
                  /{daysInMonth} ngày trong tháng
                </span>
              </div>
            </div>

            <div className="cc-emp-cal-kpi-card">
              <div className="cc-emp-cal-kpi-icon cc-emp-cal-kpi-icon--ocean">
                <Clock size={18} />
              </div>
              <div className="cc-emp-cal-kpi-content">
                <span className="cc-emp-cal-kpi-label">Tổng giờ làm việc</span>
                <span className="cc-emp-cal-kpi-val">{totalHours}h</span>
                <span className="cc-emp-cal-kpi-sub">
                  TB {avgHoursPerDay}h / ngày
                </span>
              </div>
            </div>

            <div className="cc-emp-cal-kpi-card">
              <div className="cc-emp-cal-kpi-icon cc-emp-cal-kpi-icon--rust">
                <Zap size={18} />
              </div>
              <div className="cc-emp-cal-kpi-content">
                <span className="cc-emp-cal-kpi-label">Giờ tăng ca (OT)</span>
                <span className="cc-emp-cal-kpi-val">{otHours}h</span>
                <span className="cc-emp-cal-kpi-sub">
                  {totalOtMinutes > 0 ? `${totalOtMinutes} phút tăng ca` : "Không có tăng ca"}
                </span>
              </div>
            </div>

            <div className="cc-emp-cal-kpi-card">
              <div className="cc-emp-cal-kpi-icon cc-emp-cal-kpi-icon--amber">
                <AlertTriangle size={18} />
              </div>
              <div className="cc-emp-cal-kpi-content">
                <span className="cc-emp-cal-kpi-label">Muộn / Về sớm</span>
                <span className={`cc-emp-cal-kpi-val ${lateDays > 0 || earlyDays > 0 ? "text-warn" : ""}`}>
                  {lateDays} muộn · {earlyDays} sớm
                </span>
                <span className="cc-emp-cal-kpi-sub">
                  {lateDays + earlyDays > 0
                    ? `${lateDays + earlyDays} lần vi phạm giờ`
                    : "Đúng giờ hoàn toàn"}
                </span>
              </div>
            </div>
          </div>

          {/* Lưới lịch 7 ngày */}
          <div className="cc-emp-cal-calendar">
            <div className="cc-emp-cal-grid-head">
              {WEEKDAYS.map((w) => (
                <div
                  key={w.key}
                  className={`cc-emp-cal-head-cell ${w.isWeekend ? "cc-emp-cal-head-cell--weekend" : ""}`}
                >
                  {w.label}
                </div>
              ))}
            </div>

            <div className="cc-emp-cal-grid-body">
              {calendarCells.map((dayNum, idx) => {
                if (dayNum === null) {
                  return (
                    <div
                      key={`empty-${idx}`}
                      className="cc-emp-cal-cell cc-emp-cal-cell--empty"
                    />
                  );
                }

                const day = employeeRow.days?.[String(dayNum)];
                const o = docONgay(day, heSoNgay);
                const dayOfWeek = (new Date(year, month - 1, dayNum).getDay() + 6) % 7; // 0=Mon, 5=Sat, 6=Sun
                const isWeekendDay = dayOfWeek === 5 || dayOfWeek === 6;
                const isSunday = dayOfWeek === 6;

                const dd = String(dayNum).padStart(2, "0");
                const mm = String(month).padStart(2, "0");

                let cellClass = "cc-emp-cal-cell" + o.variant;
                if (!day && isWeekendDay) cellClass += " cc-emp-cal-cell--weekend";
                if (isSunday) cellClass += " cc-emp-cal-cell--sunday";
                if (day?.late || day?.early) cellClass += " cc-emp-cal-cell--warning";

                // Badges góc phải: GIỚI HẠN TỐI ĐA 2 BADGE COMPACT, không render trùng lặp
                const badges: React.ReactNode[] = [];

                if (day?.cong != null && day.cong > 0) {
                  badges.push(
                    <span
                      key="cong"
                      className="cc-badge-pill cc-badge-pill--cell cc-badge-pill--work"
                      title={`Công: ${soCong(day.cong)}`}
                    >
                      ✓ {soCong(day.cong)}
                    </span>
                  );
                } else if (day?.holiday) {
                  badges.push(
                    <span
                      key="le"
                      className="cc-badge-pill cc-badge-pill--cell cc-badge-pill--red"
                      title={day.leave ?? "Ngày lễ"}
                    >
                      LỄ
                    </span>
                  );
                } else if (day?.leave) {
                  badges.push(
                    <span
                      key="phep"
                      className="cc-badge-pill cc-badge-pill--cell cc-badge-pill--purple"
                      title={day.leave}
                    >
                      {day.leave_paid ? "P" : "KL"}
                    </span>
                  );
                }

                if (day?.ot_minutes && day.ot_minutes > 0) {
                  const otH = Math.round((day.ot_minutes / 60) * 10) / 10;
                  badges.push(
                    <span
                      key="ot"
                      className="cc-badge-pill cc-badge-pill--cell cc-badge-pill--orange"
                      title={`Tăng ca (OT): ${otH}h (${day.ot_minutes} phút)`}
                    >
                      +{otH}h<span className="sr-only"> (+OT)</span>
                    </span>
                  );
                }

                if (badges.length < 2 && (day?.restday || (day?.cong && isSunday)) && !day?.holiday) {
                  badges.push(
                    <span
                      key="cn"
                      className="cc-badge-pill cc-badge-pill--cell cc-badge-pill--purple"
                      title="Đi làm ngày nghỉ tuần (Chủ nhật)"
                    >
                      CN
                    </span>
                  );
                }

                // Thân giữa: Giờ làm việc hoặc trạng thái ngắn gọn
                let displayTime = "—";
                let isPunchTime = false;
                if (day?.first_in || day?.last_out) {
                  displayTime = `${day.first_in ?? "—"} – ${day.last_out ?? "—"}`;
                  isPunchTime = true;
                } else if (day?.holiday) {
                  displayTime = "Nghỉ lễ";
                } else if (day?.leave) {
                  displayTime = day.leave_paid ? "Nghỉ phép (P)" : "Nghỉ KL";
                } else if (day?.planned_off) {
                  displayTime = "Nghỉ ca";
                } else if (isSunday || isWeekendDay) {
                  displayTime = "Nghỉ tuần";
                }

                // Tooltip title đầy đủ 100% chi tiết
                const tooltipParts: string[] = [];
                tooltipParts.push(`Bấm để xem chi tiết lượt chấm công ngày ${dd}/${mm}`);
                if (o.caLabel) tooltipParts.push(`Ca: ${o.caLabel}`);
                if (isPunchTime) tooltipParts.push(`Giờ làm: ${displayTime}`);
                if (day?.cong != null && day.cong > 0) tooltipParts.push(`Công: ${soCong(day.cong)}`);
                if (day?.ot_minutes && day.ot_minutes > 0) {
                  tooltipParts.push(`Tăng ca: ${day.ot_minutes}′ (+${Math.round((day.ot_minutes / 60) * 10) / 10}h)`);
                }
                if (day?.late) tooltipParts.push("Đi muộn");
                if (day?.early) tooltipParts.push("Về sớm");
                if (day?.holiday) {
                  tooltipParts.push(day.leave ? `Nghỉ lễ (${day.leave})` : "Nghỉ lễ (vẫn hưởng lương)");
                } else if (day?.leave) {
                  tooltipParts.push(day.leave_paid ? `Nghỉ phép (P: ${day.leave})` : `Nghỉ không lương (KL)`);
                } else if (day?.planned_off) {
                  tooltipParts.push("Nghỉ ca theo lịch");
                } else if (isSunday) {
                  tooltipParts.push("Nghỉ Chủ nhật");
                }
                if (o.gain) tooltipParts.push(`Hệ số: ${o.gain}`);

                const cellTitle = tooltipParts.join(" · ");

                return (
                  <div
                    key={dayNum}
                    className={cellClass}
                    onClick={() => onSelectDay?.(dayNum)}
                    title={cellTitle}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectDay?.(dayNum);
                      }
                    }}
                  >
                    <div className="cc-emp-cal-cell-top">
                      <span className={`cc-emp-cal-cell-num ${isSunday ? "cc-emp-cal-cell-num--sun" : ""}`}>
                        {dayNum}
                      </span>
                      <div className="cc-emp-cal-cell-pills">
                        {badges.slice(0, 2)}
                      </div>
                    </div>

                    <div className="cc-emp-cal-cell-body">
                      {o.caLabel && (
                        <div className="cc-emp-cal-cell-ca" title={`Ca làm: ${o.caLabel}`}>
                          {o.caLabel}
                        </div>
                      )}
                      <div
                        className={`cc-emp-cal-cell-time ${!isPunchTime ? "cc-emp-cal-cell-time--status" : ""}`}
                        title={isPunchTime ? `Giờ: ${displayTime}` : displayTime}
                      >
                        {displayTime}
                      </div>
                    </div>

                    <div className="cc-emp-cal-cell-foot">
                      <div className="cc-emp-cal-cell-gain-wrap">
                        {o.gain && (
                          <span className={`cc-emp-cal-cell-gain ${o.gainClass}`} title={o.gain}>
                            {o.gain}
                          </span>
                        )}
                      </div>
                      {(day?.late || day?.early) && (
                        <div className="cc-emp-cal-cell-faults">
                          {day?.late && (
                            <span className="cc-emp-cal-tag cc-emp-cal-tag--late">Muộn</span>
                          )}
                          {day?.early && (
                            <span className="cc-emp-cal-tag cc-emp-cal-tag--early">Sớm</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer modal */}
        <footer className="ns-modal__foot cc-emp-cal-footer">
          <div className="cc-emp-cal-legend">
            <span className="cc-emp-cal-legend-title">Chú giải:</span>
            <span className="cc-emp-cal-legend-item">
              <span className="cc-emp-cal-legend-dot cc-emp-cal-legend-dot--work" />
              Đi làm đủ công
            </span>
            <span className="cc-emp-cal-legend-item">
              <span className="cc-emp-cal-legend-dot cc-emp-cal-legend-dot--ot" />
              Tăng ca (OT)
            </span>
            <span className="cc-emp-cal-legend-item">
              <span className="cc-emp-cal-legend-dot cc-emp-cal-legend-dot--leave" />
              Nghỉ lễ / Nghỉ phép
            </span>
            <span className="cc-emp-cal-legend-item">
              <span className="cc-emp-cal-legend-dot cc-emp-cal-legend-dot--fault" />
              Đi muộn / Về sớm
            </span>
            <span className="cc-emp-cal-legend-item">
              <span className="cc-emp-cal-legend-dot cc-emp-cal-legend-dot--rest" />
              Nghỉ ca / Nghỉ tuần
            </span>
          </div>
          <div className="cc-emp-cal-foot-actions">
            <span className="cc-emp-cal-esc-hint">Nhấn <b>Esc</b> để đóng</span>
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Đóng
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
