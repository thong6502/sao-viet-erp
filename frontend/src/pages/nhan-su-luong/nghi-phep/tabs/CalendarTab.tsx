// Tab "Lịch nghỉ" (HR) (tách từ pages/NghiPhepPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type LeaveCalendar } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { Pager } from "../../../../components/Pager";
import {
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Search,
  Users,
} from "lucide-react";
import { PAGE_SIZE } from "../shared/constants";
import { errMsg, getInitials } from "../shared/helpers";

// --- Tab: Lịch nghỉ (HR) — lưới NV × ngày, tránh duyệt trùng người ----------

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

export function CalendarTab({ token }: { token: string }) {
  const now = new Date();
  const [ym, setYm] = useState<{ year: number; month: number }>({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [data, setData] = useState<LeaveCalendar | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "approved" | "pending" | "paid" | "unpaid">("all");
  /** Trang của LƯỚI (mỗi trang 20 HÀNG nhân viên). Cắt ở client — xem ghi chú ở `PAGE_SIZE`. */
  const [page, setPage] = useState(1);
  const [hoveredCell, setHoveredCell] = useState<{
    employeeName: string;
    day: number;
    leaveTypeName: string;
    isPaid: boolean;
    status: string;
    rect: DOMRect;
  } | null>(null);

  // Ba ca tách rời: `data === null` KHÔNG còn kiêm nghĩa "đang tải" — trước đây gọi hỏng
  // cũng set null nên lưới quay vòng "Đang tải…" vĩnh viễn, không ai biết là mất mạng.
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const load = useCallback(() => {
    setLoading(true);
    setListError(null);
    api.leaves.calendar(token, ym.year, ym.month)
      .then(setData)
      .catch((e) => { setData(null); setListError(errMsg(e)); })
      .finally(() => setLoading(false));
  }, [token, ym]);
  useEffect(() => { load(); }, [load]);

  function shift(delta: number) {
    let m = ym.month + delta, y = ym.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    setYm({ year: y, month: m });
  }

  function goToToday() {
    setYm({ year: now.getFullYear(), month: now.getMonth() + 1 });
  }

  const days = data ? Array.from({ length: data.days_in_month }, (_, i) => i + 1) : [];
  const isWeekend = (d: number) => { const wd = new Date(ym.year, ym.month - 1, d).getDay(); return wd === 0 || wd === 6; };
  const getWeekday = (d: number) => WEEKDAYS[new Date(ym.year, ym.month - 1, d).getDay()];

  // Date highlights
  const isCurrentMonth = now.getFullYear() === ym.year && (now.getMonth() + 1) === ym.month;
  const todayDay = now.getDate();

  // Stats calculation
  const totalEmployeesOff = data
    ? data.employees.filter(e => Object.values(e.days).some(d => d.status === "approved" || d.status === "pending")).length
    : 0;

  const totalPendingRequests = data
    ? data.employees.reduce((acc, e) => acc + Object.values(e.days).filter(d => d.status === "pending").length, 0)
    : 0;

  const totalPaidDays = data
    ? data.employees.reduce((acc, e) => acc + Object.values(e.days).filter(d => d.status === "approved" && d.is_paid).length, 0)
    : 0;

  // Filtering employees
  const filteredEmployees = data
    ? data.employees.filter(e => {
        const matchesName = e.employee_name.toLowerCase().includes(searchQuery.toLowerCase());
        if (!matchesName) return false;

        if (statusFilter === "all") return true;
        const dayList = Object.values(e.days);
        if (statusFilter === "pending") return dayList.some(d => d.status === "pending");
        if (statusFilter === "approved") return dayList.some(d => d.status === "approved");
        if (statusFilter === "paid") return dayList.some(d => d.status === "approved" && d.is_paid);
        if (statusFilter === "unpaid") return dayList.some(d => d.status === "approved" && !d.is_paid);
        return true;
      })
    : [];

  // ĐỔI THÁNG / TỪ KHOÁ / CHIP LỌC ⇒ VỀ TRANG 1. Thiếu bước này là đang ở trang 3, gõ tên một
  // người và lưới rỗng trơn — người dùng tưởng người đó không nghỉ ngày nào.
  //
  // Ở ĐÂY dùng `useEffect` chứ không nhét vào từng handler như hai tab phân trang máy chủ:
  // lưới này cắt trang Ở CLIENT nên reset trang KHÔNG sinh lời gọi mạng nào, không có chuyện
  // hai lượt tải chồng nhau. Mà tháng thì đổi được từ 4 chỗ (nút ‹ ›, ô chọn tháng, nút "Hôm
  // nay") — rải `setPage(1)` ra 4 handler là kiểu gì cũng có ngày thêm chỗ thứ 5 mà quên.
  useEffect(() => { setPage(1); }, [ym, searchQuery, statusFilter]);

  // Cắt trang trên danh sách ĐÃ LỌC. Ba thẻ thống kê phía trên vẫn tính trên `data.employees`
  // đầy đủ — chúng là số của cả tháng, không phải của trang.
  const totalPages = Math.max(1, Math.ceil(filteredEmployees.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const pagedEmployees = filteredEmployees.slice(
    (pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE,
  );

  const ymStr = `${ym.year}-${String(ym.month).padStart(2, "0")}`;

  return (
    <div className="cc-calendar-tab-wrapper">
      {/* 1. Stats & Quick Search Bar */}
      <div className="cc-calendar-dashboard">
        <div className="cc-calendar-search-wrapper">
          <Search size={16} className="cc-calendar-search-icon" />
          <input
            type="text"
            className="cc-calendar-search-input"
            placeholder="Tìm theo tên nhân viên..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="cc-calendar-search-clear" onClick={() => setSearchQuery("")}>×</button>
          )}
        </div>
        
        <div className="cc-calendar-stats-strip">
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--users"><Users size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalEmployeesOff}</span>
              <span className="cc-calendar-stat-label">Nhân sự nghỉ</span>
            </div>
          </div>
          
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--clock"><Clock size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalPendingRequests}</span>
              <span className="cc-calendar-stat-label">Đơn chờ duyệt</span>
            </div>
          </div>

          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--check"><CheckCircle2 size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalPaidDays}</span>
              <span className="cc-calendar-stat-label">Ngày phép P</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Month Navigation & Filter Chips Bar */}
      <div className="cc-calendar-grid-header">
        <div className="cc-calendar-navigator">
          <button className="cc-calendar-month-btn" onClick={() => shift(-1)} title="Tháng trước">
            <ChevronLeft size={16} />
          </button>
          
          <div className="cc-calendar-month-picker-wrapper">
            <input
              type="month"
              className="cc-month-picker-hidden"
              value={ymStr}
              onChange={(e) => {
                if (e.target.value) {
                  const [y, m] = e.target.value.split("-").map(Number);
                  setYm({ year: y, month: m });
                }
              }}
              id="cc-calendar-month-picker"
            />
            <label htmlFor="cc-calendar-month-picker" className="cc-calendar-month-title-pill" title="Bấm để chọn nhanh tháng">
              <Calendar size={14} style={{ marginRight: 6 }} />
              Tháng {ym.month} / {ym.year}
            </label>
          </div>
          
          <button className="cc-calendar-month-btn" onClick={() => shift(1)} title="Tháng sau">
            <ChevronRight size={16} />
          </button>

          {!isCurrentMonth && (
            <button className="cc-calendar-today-btn" onClick={goToToday} title="Trở về tháng hiện tại">
              Hôm nay
            </button>
          )}
        </div>

        <div className="cc-calendar-filter-chips">
          <button
            className={`cc-calendar-chip ${statusFilter === "all" ? "is-active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            Tất cả
          </button>
          <button
            className={`cc-calendar-chip cc-calendar-chip--paid ${statusFilter === "paid" ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === "paid" ? "all" : "paid")}
          >
            <span className="cc-calendar-grid-cell-badge cc-calendar-grid-cell-badge--paid">P</span>
            Có lương
          </button>
          <button
            className={`cc-calendar-chip cc-calendar-chip--unpaid ${statusFilter === "unpaid" ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === "unpaid" ? "all" : "unpaid")}
          >
            <span className="cc-calendar-grid-cell-badge cc-calendar-grid-cell-badge--unpaid">KL</span>
            Không lương
          </button>
          <button
            className={`cc-calendar-chip cc-calendar-chip--pending ${statusFilter === "pending" ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === "pending" ? "all" : "pending")}
          >
            <span className="cc-calendar-grid-cell-dot" />
            Chờ duyệt
          </button>
        </div>
      </div>

      {/* 3. Main Leave Grid Table */}
      {loading ? (
        <EmptyState trangThai="dang-tai" />
      ) : listError ? (
        <EmptyState trangThai="loi" loi={listError} onThuLai={load} />
      ) : !data || data.employees.length === 0 ? (
        <EmptyState
          icon="calendar"
          title="Chưa có ai nghỉ trong tháng này"
          sub="Đơn nghỉ được duyệt sẽ hiện thành ô P / KL trên lưới."
        />
      ) : filteredEmployees.length === 0 ? (
        <EmptyState
          icon="search"
          title="Chưa có nhân viên nào khớp bộ lọc"
          sub="Thử xoá ô tìm tên hoặc bỏ bớt chip lọc phía trên."
        />
      ) : (
        <div className="cc-timesheet-scroll-container cc-calendar-scroll-wrapper">
          <table className="cc-timesheet-table cc-calendar-table">
            <thead>
              <tr className="cc-calendar-dow-row">
                <th className="cc-calendar-sticky-name">NHÂN VIÊN</th>
                {days.map((d) => {
                  const weekend = isWeekend(d);
                  const dow = getWeekday(d);
                  const isToday = isCurrentMonth && d === todayDay;
                  let thCls = "cc-day-dow";
                  if (weekend) thCls += " cc-day-cell--weekend";
                  if (isToday) thCls += " cc-day-hdr-v2--today";
                  return (
                    <th key={d} className={thCls}>
                      {dow}
                    </th>
                  );
                })}
              </tr>
              <tr>
                <th className="cc-calendar-sticky-name cc-calendar-sticky-sub">
                  {/* Đếm theo TOÀN BỘ danh sách đã lọc, không phải số hàng của trang — đây là
                      "có bao nhiêu NV khớp", chân bảng bên dưới mới nói đang xem trang mấy. */}
                  <span className="cc-emp-count-badge">{filteredEmployees.length} NV</span>
                </th>
                {days.map((d) => {
                  const weekend = isWeekend(d);
                  const isToday = isCurrentMonth && d === todayDay;
                  let thCls = weekend ? "cc-day-hdr-v2 cc-day-cell--weekend" : "cc-day-hdr-v2";
                  if (isToday) thCls += " cc-day-hdr-v2--today";
                  
                  return (
                    <th key={d} className={thCls} style={{ textAlign: "center", minWidth: 32, padding: "6px 2px" }}>
                      {d}
                      {isToday && <span className="cc-today-indicator-dot" />}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {pagedEmployees.map((e) => (
                <tr key={e.employee_id} className="cc-calendar-row">
                  <td className="cc-calendar-sticky-name">
                    <div className="cc-name-cell-wrapper">
                      <span className="cc-name-avatar">{getInitials(e.employee_name)}</span>
                      <span className="cc-name-text-plain" title={e.employee_name}>
                        {e.employee_name}
                      </span>
                    </div>
                  </td>
                  {days.map((d) => {
                    const cell = e.days[String(d)];
                    const weekend = isWeekend(d);
                    const isToday = isCurrentMonth && d === todayDay;

                    // Check neighbor cells for continuous span styling
                    const prevCell = e.days[String(d - 1)];
                    const nextCell = e.days[String(d + 1)];
                    const isSpanStart = cell && (!prevCell || prevCell.leave_type_name !== cell.leave_type_name);
                    const isSpanEnd = cell && (!nextCell || nextCell.leave_type_name !== cell.leave_type_name);

                    let cellContent = null;
                    let cellClass = "cc-calendar-cell";
                    if (cell) {
                      cellClass += " cc-calendar-cell--has-leave";
                      if (isSpanStart) cellClass += " cc-calendar-cell--span-start";
                      if (isSpanEnd) cellClass += " cc-calendar-cell--span-end";

                      if (cell.status === "approved") {
                        const badgeClass = cell.is_paid ? "cc-calendar-grid-cell-badge--paid" : "cc-calendar-grid-cell-badge--unpaid";
                        cellContent = <span className={`cc-calendar-grid-cell-badge ${badgeClass}`}>{cell.is_paid ? "P" : "KL"}</span>;
                      } else {
                        cellContent = <span className="cc-calendar-grid-cell-dot" title="Chờ duyệt" />;
                      }
                    }
                    
                    if (weekend) {
                      cellClass += " cc-day-cell--weekend";
                    }
                    if (isToday) {
                      cellClass += " cc-day-cell--today";
                    }
                    
                    return (
                      <td key={d}
                        className={cellClass}
                        style={{ textAlign: "center", padding: "6px 2px", position: "relative" }}
                        onMouseEnter={(event) => {
                          if (cell) {
                            setHoveredCell({
                              employeeName: e.employee_name,
                              day: d,
                              leaveTypeName: cell.leave_type_name,
                              isPaid: cell.is_paid,
                              status: cell.status,
                              rect: event.currentTarget.getBoundingClientRect()
                            });
                          }
                        }}
                        onMouseLeave={() => setHoveredCell(null)}
                      >
                        {cellContent}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Chân bảng chỉ có nghĩa khi lưới đang hiện — ba ca tải/lỗi/rỗng ở trên đã thay chỗ
          của lưới rồi thì đừng in thêm "Tổng 0 nhân viên" bên dưới. */}
      {!loading && !listError && filteredEmployees.length > 0 && (
        <Pager
          total={filteredEmployees.length}
          page={pageSafe}
          size={PAGE_SIZE}
          unit="nhân viên"
          onPage={setPage}
        />
      )}

      {/* 4. Glassmorphic Popover Tooltip */}
      {hoveredCell && (() => {
        const tooltipWidth = 240;
        const leftPos = Math.max(16, Math.min(window.innerWidth - tooltipWidth - 16, hoveredCell.rect.left + (hoveredCell.rect.width / 2) - (tooltipWidth / 2)));
        const showAbove = hoveredCell.rect.bottom + 120 > window.innerHeight;
        const topPos = showAbove ? hoveredCell.rect.top - 120 : hoveredCell.rect.bottom + 8;
        
        return (
          <div className="cc-calendar-tooltip" style={{
            position: "fixed",
            top: topPos,
            left: leftPos,
            zIndex: 1000
          }}>
            <div className="cc-calendar-tooltip-header">
              <span className="cc-calendar-tooltip-avatar">{getInitials(hoveredCell.employeeName)}</span>
              <div>
                <span className="cc-calendar-tooltip-title">{hoveredCell.employeeName}</span>
                <span className="cc-calendar-tooltip-date">Ngày {hoveredCell.day} tháng {ym.month}/{ym.year}</span>
              </div>
            </div>
            <div className="cc-calendar-tooltip-body">
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Loại nghỉ</span>
                <span className="cc-calendar-tooltip-val">{hoveredCell.leaveTypeName}</span>
              </div>
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Chế độ lương</span>
                <span className={`cc-calendar-tooltip-val cc-calendar-tooltip-val--paid-${hoveredCell.isPaid}`}>
                  {hoveredCell.isPaid ? "Có lương (P)" : "Không lương (KL)"}
                </span>
              </div>
              <div className="cc-calendar-tooltip-row">
                <span className="cc-calendar-tooltip-label">Trạng thái</span>
                <span className={`cc-calendar-tooltip-status cc-calendar-tooltip-status--${hoveredCell.status}`}>
                  {hoveredCell.status === "approved" ? "✓ Đã duyệt" : "⏳ Chờ duyệt"}
                </span>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
