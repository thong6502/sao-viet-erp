// Tab Bảng công tháng (tách từ pages/ChamCongPage.tsx).
import { memo, useCallback, useEffect, useMemo, useState } from "react";
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
  FileEdit,
  AlertTriangle,
  RefreshCw,
  Trash2,
  Lock,
  Unlock,
  ClipboardCheck,
  Search,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { MonthPicker } from "../../../../components/MonthPicker";
import { OtConfirmModal } from "../modals/OtConfirmModal";
import { EmployeeCalendarModal } from "../modals/EmployeeCalendarModal";
import {
  FAULT_OPTIONS,
  FAULT_LABEL,
  HE_SO_NGAY_MAC_DINH,
  WEEKDAY_NAMES_SHORT,
} from "../shared/constants";
import {
  soCong,
  congDacBiet,
  congThuong,
  gioTangCa,
  tongCongDacBiet,
  ngayDacBiet,
  getWeekdayIndex,
  getWeekdayLabel,
  isWeekend,
  getInitials,
} from "../shared/helpers";

// --- Tab: Bảng công tháng (HR) ----------------------------------------------

/** Tạo dãy số trang có dấu "..." khi danh sách dài chuẩn ERP */
export function getPageNumbers(
  trangHien: number,
  soTrang: number,
): (number | string)[] {
  if (soTrang <= 7) {
    return Array.from({ length: soTrang }, (_, i) => i + 1);
  }
  if (trangHien <= 4) {
    return [1, 2, 3, 4, 5, "...", soTrang];
  }
  if (trangHien >= soTrang - 3) {
    return [1, "...", soTrang - 4, soTrang - 3, soTrang - 2, soTrang - 1, soTrang];
  }
  return [1, "...", trangHien - 1, trangHien, trangHien + 1, "...", soTrang];
}

/** Bỏ dấu + thường hoá: gõ "quan" vẫn ra "Quân", gõ "nv02" vẫn ra "NV002" — kế toán tìm nhanh
 *  thì không ai gõ dấu. */
const khongDau = (s: string) =>
  (s ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d");

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
  // Tìm theo TÊN / MÃ nhân viên — lọc ngay trên bảng đã tải (cả tháng đã nằm sẵn trong `data`),
  // không bắn thêm request. Bảng 31 cột ngày cuộn ngang, không có ô này thì tìm một người là dò mắt.
  const [tim, setTim] = useState("");
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
  // Hàng đang mở ngăn "Công CN/Lễ" — cột chỉ nói MỘT số tổng, ngăn này mới tách loại + từng ngày.
  const [specialFor, setSpecialFor] = useState<TimesheetRow | null>(null);
  // Modal "Xác nhận TC theo phiếu" (07/09/2026) — bù cặp bấm tăng ca hàng loạt cho người quên bấm.
  const [otConfirmOpen, setOtConfirmOpen] = useState(false);
  const [showOtList, setShowOtList] = useState(false);
  // Băng "phiếu TC thiếu cặp bấm" tách HAI NHÓM (chủ 10/09/2026): nhóm bấm một nút là xong, và
  // nhóm ngày đó thiếu lượt bấm ca chính — nhóm sau vào màn Xác nhận TC thì ô tích mờ, không nói
  // rõ ở đây thì người dùng bấm vào rồi đứng nhìn cái tên không biết làm gì.
  const otList = period?.ot_thieu_cap_list ?? [];
  const otBu1Cham = otList.filter((x) => (x.ma ?? "thieu_cap") === "thieu_cap").length;
  const otPhaiSuaTruoc = otList.length - otBu1Cham;
  const [year, month] = ym.split("-").map(Number);
  // Ngày mặc định của modal: đang xem tháng hiện tại thì lấy HÔM QUA (ngày hay cần bù nhất),
  // tháng cũ thì lấy ngày cuối tháng đó.
  const otDefaultDate = (() => {
    const now = new Date();
    const cungThang =
      now.getFullYear() === year && now.getMonth() + 1 === month;
    const d = cungThang
      ? new Date(
          now.getFullYear(),
          now.getMonth(),
          Math.max(1, now.getDate() - 1),
        )
      : new Date(year, month, 0);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();

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

  async function exportExcel() {
    setDownloading(true);
    try {
      const url = await api.attendance.timesheetExcelBlobUrl(
        token,
        year,
        month,
        deptId === "" ? null : deptId,
        tim.trim() || null,
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `bang-cong-${year}-${String(month).padStart(2, "0")}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  // `useMemo`: mảng này là prop của từng hàng đã bọc `memo`. Dựng lại mỗi lượt render là cấp cho
  // hàng một prop mới toanh ⇒ `memo` không giữ được hàng nào.
  const days = useMemo(
    () =>
      data ? Array.from({ length: data.days_in_month }, (_, i) => i + 1) : [],
    [data],
  );

  const rowsHien = useMemo(() => {
    const q = khongDau(tim.trim());
    const rows = data?.rows ?? [];
    if (!q) return rows;
    return rows.filter(
      (r) =>
        khongDau(r.employee_name).includes(q) ||
        khongDau(r.employee_code).includes(q),
    );
  }, [data, tim]);

  // --- Phân trang TRÊN DỮ LIỆU ĐÃ TẢI (11/09/2026) --------------------------
  //
  // Cả tháng vẫn về một lượt như cũ; chỉ khác là vẽ ra màn theo từng trang. Đây là chỗ nghẽn
  // THẬT ở quy mô lớn: 500 NV × 39 ô = ~19.500 `<td>` trong MỘT bảng.
  //
  // CỐ Ý không phân trang ở máy chủ: `monthly_timesheet` còn nuôi Lương (`metrics_map`), Chốt
  // công (`period_status`/`lock_period`), NV tự xem (`my_timesheet`) và bản xuất Excel — nhét
  // tham số cắt dữ liệu vào đó là đặt một con dao ngay giữa đường Lương đang tin là "đủ người".
  // Giữ dữ liệu đủ ở trình duyệt còn đổi lại hai thứ: ô KPI vẫn cộng theo TOÀN BỘ tập đang lọc
  // (không phải một trang), và ô tìm tên/mã vẫn chạy tức thì không phải gõ-rồi-chờ.
  const [soMoiTrang, setSoMoiTrang] = useState(50);
  const [trang, setTrang] = useState(1);
  const soTrang =
    soMoiTrang === 0 ? 1 : Math.max(1, Math.ceil(rowsHien.length / soMoiTrang));
  // Kẹp lại thay vì tin `trang`: đổi tháng/tổ hay gõ ô tìm đều làm danh sách ngắn lại, đứng ở
  // trang 9 mà còn 2 trang thì bảng trắng trơn trong khi vẫn có người.
  const trangHien = Math.min(trang, soTrang);
  const rowsTrang = useMemo(
    () =>
      soMoiTrang === 0
        ? rowsHien
        : rowsHien.slice((trangHien - 1) * soMoiTrang, trangHien * soMoiTrang),
    [rowsHien, trangHien, soMoiTrang],
  );
  useEffect(() => {
    setTrang(1);
  }, [ym, deptId, tim, soMoiTrang]);

  // Ba callback DÙNG CHUNG cho mọi hàng — `useCallback` để định danh không đổi giữa các lượt
  // render, nếu không `memo` ở `TimesheetRowView` vô hiệu (xem ghi chú ở component đó).
  const laCuoiTuan = useCallback(
    (d: number) => isWeekend(year, month, d),
    [year, month],
  );
  const moODay = useCallback(
    (r: TimesheetRow, dayNum: number) => {
      const date = `${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
      setOpenDay({
        employeeId: r.employee_id,
        employeeName: r.employee_name,
        date,
      });
    },
    [year, month],
  );
  const moChiTietNgay = moODay;
  const moLichNV = useCallback(
    (r: TimesheetRow) => setSelectedEmployeeCal({ row: r, name: r.employee_name }),
    [],
  );
  const moCongDacBiet = useCallback((r: TimesheetRow) => setSpecialFor(r), []);

  // Thứ đang CHẶN chốt công (máy chủ chặn cả đơn chờ duyệt lẫn ngày treo — xem
  // `AttendanceService.lock_period`). Chỉ kể loại nào thật sự còn số.
  const vuongChot = useMemo(() => {
    if (!period || period.status === "locked") return [];
    const ds: { so: number; ten: string }[] = [];
    if ((period.hanging_days ?? 0) > 0)
      ds.push({
        so: period.hanging_days,
        ten: "ngày treo (bấm VÀO, thiếu bấm RA)",
      });
    const cho: [number | undefined, string][] = [
      [period.pending_leaves, "đơn nghỉ phép"],
      [period.pending_late_early, "phiếu đi muộn / về sớm"],
      [period.pending_overtime, "phiếu tăng ca"],
      [period.pending_adjusts, "yêu cầu chỉnh công"],
    ];
    for (const [so, ten] of cho)
      if ((so ?? 0) > 0) ds.push({ so: so ?? 0, ten: `${ten} chờ duyệt` });
    return ds;
  }, [period]);

  // KPI đếm theo HÀNG ĐANG THẤY — lọc còn một người mà ô tổng vẫn nói cả xưởng thì ô tổng nói dối.
  const totalEmployees = rowsHien.length;
  let totalCong = 0;
  let totalHours = 0;
  for (const r of rowsHien) {
    totalCong += r.total_cong ?? r.total_days ?? 0;
    totalHours += r.total_hours ?? 0;
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

      {/* Cụm thông báo trạng thái kỳ công & tăng ca cần xử lý (.cc-ts-alerts-stack) */}
      {((vuongChot.length > 0) || (period && period.status !== "locked" && (period.ot_thieu_cap ?? 0) > 0)) && (
        <div className="cc-ts-alerts-stack">
          {/* Card 1: Vướng mắc chốt công tháng (vuongChot) with Clock icon and styled chips */}
          {vuongChot.length > 0 && (
            <div className="cc-ts-alert-card cc-ts-alert-card--pending">
              <div className="cc-ts-alert-icon">
                <Clock size={16} />
              </div>
              <div className="cc-ts-alert-body">
                <div className="cc-ts-alert-header-row">
                  <div className="cc-ts-alert-title-group">
                    <span className="cc-ts-alert-title">Vướng mắc chốt công tháng</span>
                    <span className="cc-ts-alert-subtext">
                      Chưa chốt được công tháng — còn một số vướng mắc cần phê duyệt hoặc xử lý trước khi khóa bảng công.
                    </span>
                  </div>
                </div>
                <div className="cc-ts-alert-chips">
                  {vuongChot.map((v) => (
                    <span key={v.ten} className="cc-ts-alert-chip">
                      <span className="cc-ts-alert-chip-count">{v.so}</span>
                      <span>{v.ten}</span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Card 2: Phiếu tăng ca đã duyệt chưa có cặp bấm (ot_thieu_cap) */}
          {period && period.status !== "locked" && (period.ot_thieu_cap ?? 0) > 0 && (
            <div className="cc-ts-alert-card cc-ts-alert-card--ot">
              <div className="cc-ts-alert-icon cc-ts-alert-icon--ot">
                <AlertTriangle size={16} />
              </div>
              <div className="cc-ts-alert-body">
                <div className="cc-ts-alert-header-row">
                  <div className="cc-ts-alert-title-group">
                    <span className="cc-ts-alert-title">
                      {period.ot_thieu_cap} phiếu tăng ca đã duyệt chưa có cặp bấm
                    </span>
                    <span className="cc-ts-alert-subtext">
                      Nếu chốt kỳ công lúc này, những phiếu này sẽ tính 0 phút tăng ca do thiếu lượt bấm tương ứng.
                    </span>
                  </div>
                </div>

                <div className="cc-ts-alert-details-row">
                  <div className="cc-ts-alert-breakdown">
                    {otBu1Cham > 0 && (
                      <span className="cc-ts-breakdown-tag cc-ts-breakdown-tag--auto">
                        <b>{otBu1Cham}</b> bù được ngay
                      </span>
                    )}
                    {otPhaiSuaTruoc > 0 && (
                      <span className="cc-ts-breakdown-tag cc-ts-breakdown-tag--manual">
                        <b>{otPhaiSuaTruoc}</b> thiếu giờ ca chính
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="cc-ts-toggle-list-btn"
                    onClick={() => setShowOtList((prev) => !prev)}
                  >
                    <span>{showOtList ? "Ẩn danh sách" : "Xem danh sách"}</span>
                    {showOtList ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                </div>

                {showOtList && (
                  <div className="cc-ts-alert-list-wrap">
                    <ul className="cc-ts-alert-list">
                      {(period.ot_thieu_cap_list ?? []).map((x) => (
                        <li key={`${x.employee_id}-${x.date}`} className="cc-ts-alert-list-item">
                          <span className="cc-ts-alert-emp-name">{x.employee_name}</span>
                          <span className="cc-ts-alert-item-date">{x.date}</span>
                          <span className="cc-ts-alert-item-time">
                            {x.from_time}–{x.to_time}
                          </span>
                          {x.ly_do && <span className="cc-ts-alert-item-reason">{x.ly_do}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* L3 — kỳ ĐÃ CHỐT nhưng vẫn có lượt bấm mới. Băng này là thứ DUY NHẤT cho người dùng biết:
          ảnh chụp không có mấy lượt đó, nên Bảng lương cũng không tính. Không chặn thợ bấm giờ —
          chỉ nhắc HCNS chốt lại kỳ. */}
      {period &&
        period.status === "locked" &&
        (period.phat_sinh_sau_chot ?? 0) > 0 && (
          <div className="banner banner--warn cc-ts-warn-banner">
            <AlertTriangle size={14} />
            <span>
              Kỳ công đã chốt nhưng có{" "}
              <strong>{period.phat_sinh_sau_chot}</strong> lượt bấm ghi vào sau
              đó — <strong>ảnh chụp không có mấy lượt này</strong>, nên Bảng
              lương cũng không tính. Mở lại kỳ công rồi chốt lại để cập nhật.
            </span>
          </div>
        )}

      {period &&
        period.status === "locked" &&
        (period.doi_ca_nen_sau_chot ?? 0) > 0 && (
          <div className="banner banner--warn cc-ts-warn-banner">
            <AlertTriangle size={14} />
            <span>
              Kỳ công đã chốt nhưng có{" "}
              <strong>{period.doi_ca_nen_sau_chot}</strong> lần đổi ca (ca nền /
              ô lưới) hiệu lực trong tháng ghi sau đó —{" "}
              <strong>ảnh chụp đang tính theo ca cũ</strong>, Bảng lương chưa
              chốt được. Mở lại kỳ công, chốt lại rồi bấm Tính lại.
            </span>
          </div>
        )}

      {periodMsg && (
        <div
          className={`banner ${periodMsg.type === "error" ? "banner--error" : "banner--ok"} cc-ts-msg-banner`}
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
          <div className="cc-ts-search">
            <Search size={14} className="cc-ts-search__icon" />
            <input
              className="cc-ts-search__input"
              value={tim}
              onChange={(e) => setTim(e.target.value)}
              placeholder="Tìm tên hoặc mã NV…"
              aria-label="Tìm nhân viên trong bảng công"
            />
            {tim && (
              <button
                type="button"
                className="cc-ts-search__x"
                onClick={() => setTim("")}
                aria-label="Xoá ô tìm"
                title="Xoá ô tìm"
              >
                ×
              </button>
            )}
          </div>
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
              Nghỉ/Phép/Lễ
            </span>
            <span className="cc-ts-legend-item cc-ts-legend-item--ot">
              OT (+)
            </span>
          </div>
        </div>

        <div className="cc-ts-actions">
          {canAdjust && period && period.status !== "locked" && (
            <button
              className="btn btn--ghost"
              onClick={() => setOtConfirmOpen(true)}
              title="Sinh cặp bấm tăng ca cho người có phiếu đã duyệt nhưng quên bấm — cả tổ một lần"
            >
              <ClipboardCheck size={14} />
              <span>
                Xác nhận TC theo phiếu
                {(period.ot_thieu_cap ?? 0) > 0
                  ? ` (${period.ot_thieu_cap})`
                  : ""}
              </span>
            </button>
          )}
          <button
            className="btn btn--ghost cc-ts-btn-export"
            onClick={exportExcel}
            disabled={downloading || !rowsHien.length}
          >
            {downloading ? (
              <RefreshCw className="cc-animate-spin" size={14} />
            ) : (
              <FileEdit size={14} />
            )}
            <span>{downloading ? "Đang xuất…" : "Xuất Excel"}</span>
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

      {otConfirmOpen && (
        <OtConfirmModal
          token={token}
          defaultDate={otDefaultDate}
          depts={depts}
          onClose={() => setOtConfirmOpen(false)}
          onDone={() => {
            reload();
            loadPeriod();
          }}
          onOpenDay={(employeeId, employeeName, d) => {
            setOtConfirmOpen(false);
            setOpenDay({ employeeId, employeeName, date: d });
          }}
        />
      )}

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
                {/* BA cột công phải CỘNG ĐÚNG ra Tổng công (chủ 09/09/2026): trước đó cột này là
                    TỔNG mà lại đứng cạnh CN/Lễ nên bị đọc thành hai rổ rời, không ai biết chỗ nào
                    công thường chỗ nào công lễ. */}
                <th>Công thường</th>
                {/* MỘT cột cho cả ba loại công đặc biệt, và là MỘT SỐ TỔNG (chủ 09/09/2026) —
                    bảng này đã 31 cột ngày, tách ba cột là đẩy cột Giờ ra khỏi màn 1440px.
                    Bấm vào số mới bung ra từng ngày + hệ số quy đổi trong ngăn chi tiết. */}
                <th>CN/Lễ</th>
                <th>Tăng ca</th>
                <th>Tổng công</th>
                <th>Giờ</th>
              </tr>
            </thead>
            <tbody>
              {rowsTrang.map((r) => (
                <TimesheetRowView
                  key={r.employee_id}
                  row={r}
                  days={days}
                  isWeekend={laCuoiTuan}
                  onCellClick={moODay}
                  onNameClick={moLichNV}
                  onSpecialClick={moCongDacBiet}
                />
              ))}
              {rowsHien.length === 0 && (
                <tr>
                  <td colSpan={days.length + 8} className="ns__empty">
                    {tim.trim()
                      ? `Không có nhân viên nào khớp "${tim.trim()}" trong tháng này.`
                      : "Chưa có dữ liệu chấm công tháng này."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && data && rowsHien.length > 0 && (
        <div className="cc-ts-pager">
          <span className="cc-ts-pager__count">
            {soMoiTrang === 0 || soTrang === 1 ? (
              <>
                <b>{rowsHien.length}</b> nhân viên
              </>
            ) : (
              <>
                <b>
                  {(trangHien - 1) * soMoiTrang + 1}–
                  {Math.min(trangHien * soMoiTrang, rowsHien.length)}
                </b>{" "}
                / {rowsHien.length} nhân viên
              </>
            )}
          </span>
          {/* Cột giữa: phân trang chỉ hiện khi soTrang > 1 */}
          {soTrang > 1 && (
            <div className="cc-ts-pager__nav">
              <button
                type="button"
                className="cc-ts-pager__icon-btn"
                disabled={trangHien <= 1}
                onClick={() => setTrang(1)}
                title="Trang đầu"
              >
                <ChevronsLeft size={14} />
              </button>
              <button
                type="button"
                className="btn btn--ghost cc-ts-pager__btn"
                disabled={trangHien <= 1}
                onClick={() => setTrang(trangHien - 1)}
                title="Trang trước"
              >
                <ChevronLeft size={14} />
                <span>‹ Trước</span>
              </button>
              <div className="cc-ts-pager__pages">
                {getPageNumbers(trangHien, soTrang).map((p, idx) =>
                  typeof p === "number" ? (
                    <button
                      key={p}
                      type="button"
                      className={`cc-ts-pager__page-num ${p === trangHien ? "cc-ts-pager__page-num--active" : ""}`}
                      onClick={() => setTrang(p)}
                    >
                      {p}
                    </button>
                  ) : (
                    <span key={`ellipsis-${idx}`} className="cc-ts-pager__ellipsis">
                      …
                    </span>
                  ),
                )}
              </div>
              <span className="cc-ts-pager__pos">
                Trang {trangHien}/{soTrang}
              </span>
              <button
                type="button"
                className="btn btn--ghost cc-ts-pager__btn"
                disabled={trangHien >= soTrang}
                onClick={() => setTrang(trangHien + 1)}
                title="Trang sau"
              >
                <span>Sau ›</span>
                <ChevronRight size={14} />
              </button>
              <button
                type="button"
                className="cc-ts-pager__icon-btn"
                disabled={trangHien >= soTrang}
                onClick={() => setTrang(soTrang)}
                title="Trang cuối"
              >
                <ChevronsRight size={14} />
              </button>
            </div>
          )}
          <div className="cc-ts-pager__size-wrap">
            <label className="cc-ts-pager__size">
              Mỗi trang
              <div className="cc-ts-pager__select-box">
                <select
                  value={soMoiTrang}
                  onChange={(e) => setSoMoiTrang(Number(e.target.value))}
                >
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                  {/* "Tất cả" giữ lại cho ai quen cuộn một mạch — ở vài trăm người thì chậm, nên
                      KHÔNG để làm mặc định. */}
                  <option value={0}>Tất cả</option>
                </select>
                <ChevronDown size={13} className="cc-ts-pager__select-arrow" />
              </div>
            </label>
          </div>
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
          onChanged={() => {
            reload();
            loadPeriod(); // băng "phiếu TC thiếu cặp bấm" + số ngày treo đổi theo lượt chấm bù
          }}
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
          onSelectDay={(dayNum) => moChiTietNgay(selectedEmployeeCal.row, dayNum)}
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

/** Drawer "Công CN/Lễ": từng ngày lễ / nghỉ tuần / ngày nghỉ công ty CÓ ĐI LÀM, kèm số công
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
  // Cột ngoài bảng chỉ nói MỘT số tổng; ngăn này là chỗ "bấm vào mới phân biệt ra" (chủ 09/09/2026):
  // tách theo loại ngày trước, rồi mới tới từng ngày.
  const chips = congDacBiet(row);
  const tongCong = tongCongDacBiet(row);

  return (
    <div
      className="cc-sp-drawer"
      role="dialog"
      aria-label={`Công CN/Lễ — ${row.employee_name}`}
    >
      <div className="cc-sp-drawer__backdrop" onClick={onClose} />
      <div className="cc-sp-drawer__panel">
        <div className="cc-sp-drawer__head">
          <div>
            <div className="cc-sp-drawer__title">Công CN/Lễ</div>
            <div className="cc-sp-drawer__sub">
              {row.employee_name} · tháng {month}/{year}
            </div>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </div>
        {chips.length > 0 && (
          <div className="cc-sp-drawer__tach">
            <span className="cc-sp-drawer__tach-tong">{tongCong} công</span>
            <span className="cc-sp-drawer__tach-dau">=</span>
            {chips.map((c) => (
              <span
                key={c.text}
                className={`cc-badge-pill cc-badge-pill--${c.tone}`}
                title={c.title}
              >
                {c.text}
              </span>
            ))}
          </div>
        )}
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
                        {
                          WEEKDAY_NAMES_SHORT[
                            getWeekdayIndex(year, month, d.ngay)
                          ]
                        }{" "}
                        {String(d.ngay).padStart(2, "0")}/
                        {String(month).padStart(2, "0")} · {d.loai}
                      </span>
                      <span
                        className={`cc-badge-pill cc-badge-pill--${d.tone}`}
                      >
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

/** Một HÀNG của bảng công — bọc `memo` (11/09/2026).
 *
 *  Hàng này nặng: 3 ô đầu + 31 ô ngày + 5 ô tổng ≈ 39 `<td>`. Ô "Tìm tên/mã NV" là state của
 *  component CHA, nên trước khi bọc `memo` thì mỗi ký tự gõ vào ô tìm là React dựng lại TOÀN BỘ
 *  hàng đang hiển thị — 500 NV ⇒ ~19.500 ô mỗi lần nhấn phím. Mở ngăn lịch, bấm chốt kỳ… đều trả
 *  cùng cái giá đó.
 *
 *  ⚠️ `memo` chỉ ăn thua khi MỌI prop giữ nguyên định danh giữa hai lượt vẽ. Vì vậy ba callback
 *  dưới đây nhận `row` làm tham số (cha giữ `useCallback` một bản duy nhất) thay vì đóng gói sẵn
 *  `row` trong arrow function tạo mới mỗi lượt — đổi lại là hàm vô hiệu hoàn toàn. `days` cũng
 *  phải là mảng `useMemo` bên cha, đừng dựng `Array.from(...)` ngay trong thân render. */
const TimesheetRowView = memo(function TimesheetRowView({
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
  onCellClick?: (row: TimesheetRow, dayNum: number) => void;
  onNameClick?: (row: TimesheetRow) => void;
  onSpecialClick?: (row: TimesheetRow) => void;
}) {
  const congCnLe = tongCongDacBiet(row);
  const gioTc = gioTangCa(row);
  const clickable = !!onCellClick;
  const cellProps = (d: number) =>
    clickable
      ? {
          role: "button" as const,
          tabIndex: 0,
          onClick: () => onCellClick!(row, d),
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
            onClick={() => onNameClick?.(row)}
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

        // TRẬT TỰ hỏi như lịch (`docONgay`) và như file Excel: LƯỢT BẤM trước, cờ ngày sau.
        // Hỏi `day.leave` trước thì (1) ngày lễ ĐI LÀM hiện thành "P" — nuốt mất công thật, và
        // (2) ngày lễ nghỉ ở nhà cũng hiện "P" y như nghỉ phép năm, trong khi lễ KHÔNG tiêu phép.
        const coBam = !!(day.first_in || day.last_out);
        if (!coBam && (day.holiday || day.leave)) {
          const nhanNghi = day.holiday ? "L" : day.leave_paid ? "P" : "KL";
          return (
            <td key={d} className={cellClass} {...cellProps(d)}>
              <span
                className="cc-cell-badge cc-cell-badge--leave"
                title={
                  day.holiday
                    ? `Nghỉ lễ: ${day.leave ?? "ngày lễ"} — vẫn hưởng lương, không tiêu phép năm`
                    : `Nghỉ: ${day.leave}`
                }
              >
                {nhanNghi}
              </span>
            </td>
          );
        }

        // Ô ngày CHƯA CÓ LƯỢT CHẤM (ngày mai đã xếp ca, nghỉ luân phiên…) trước đây đeo dấu "•"
        // trên nền XANH của ngày đi làm — nhìn y như đã có công. Cùng loại khó hiểu với chữ "có"
        // của bản .csv cũ (chủ chê 09/09/2026), nên tách hẳn: chưa chấm = dấu lặng, ngày TREO
        // (có bấm mà không ra công/giờ) = dấu "?" màu cảnh báo.
        const treo = coBam && day.cong == null && day.hours == null;
        let badgeClass = "cc-cell-badge";
        if (!coBam) badgeClass += " cc-cell-badge--plan";
        else if (treo) badgeClass += " cc-cell-badge--treo";
        else if (day.late) badgeClass += " cc-cell-badge--late";
        else if (day.early) badgeClass += " cc-cell-badge--early";
        else badgeClass += " cc-cell-badge--work";

        const label =
          day.cong != null
            ? String(day.cong)
            : day.hours != null
              ? `${day.hours}h`
              : treo
                ? "?"
                : "·";
        const tip = !coBam
          ? day.shift_name
            ? `Đã xếp ca ${day.shift_name} — chưa có lượt chấm`
            : "Chưa có lượt chấm"
          : `${day.first_in ?? "?"}–${day.last_out ?? "?"}` +
            (treo ? " · ⚠ thiếu lượt, ngày treo" : "") +
            (day.late ? " · đi muộn" : "") +
            (day.early ? " · về sớm" : "") +
            (day.ot_minutes ? ` · OT ${day.ot_minutes}′` : "") +
            (day.ot_thieu_cap ? " · ⚠ phiếu tăng ca chưa có cặp bấm" : "") +
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
              {day.ot_thieu_cap ? (
                <span
                  className="cc-cell-ot-dot cc-cell-ot-dot--thieu"
                  title="Phiếu tăng ca đã duyệt nhưng chưa có cặp bấm — chốt là 0 phút"
                >
                  !
                </span>
              ) : null}
            </span>
          </td>
        );
      })}
      <td
        style={{ fontWeight: "bold", textAlign: "center" }}
        title="Công ngày thường = tổng công − công CN/lễ − công phép có lương"
      >
        {congThuong(row)}
      </td>
      {/* KHÔNG flex trên <td> (layout bảng vỡ ở Safari/Firefox) — bọc trong <button> rồi flex ở đó. */}
      <td style={{ textAlign: "center" }}>
        {congCnLe <= 0 ? (
          <span style={{ color: "var(--ash-2)" }}>—</span>
        ) : (
          <button
            type="button"
            className="cc-ts-special"
            onClick={() => onSpecialClick?.(row)}
            title="Tổng công ngày nghỉ tuần + ngày lễ + ngày công ty cho nghỉ — bấm để xem từng ngày và hệ số quy đổi"
          >
            <span className="cc-badge-pill cc-badge-pill--purple">
              {congCnLe}
            </span>
          </button>
        )}
      </td>
      <td style={{ fontWeight: "bold", textAlign: "center" }}>
        {gioTc > 0 ? (
          `${gioTc}h`
        ) : (
          <span style={{ color: "var(--ash-2)", fontWeight: "normal" }}>—</span>
        )}
      </td>
      {/* TỔNG CÔNG — con số ra tiền của Bảng lương. Đặt cạnh Tăng ca theo đúng chỗ chủ chỉ. */}
      <td
        className="cc-ts-tongcong"
        style={{ fontWeight: "bold", textAlign: "center" }}
        title="Tổng công = công thường + công CN/lễ + công phép có lương. Đây là số Bảng lương dùng."
      >
        {soCong(row.total_cong ?? row.total_days)}
      </td>
      <td style={{ fontWeight: "bold", textAlign: "center" }}>
        {row.total_hours}h
      </td>
    </tr>
  );
});

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
  const [otOutNext, setOtOutNext] = useState(false); // giờ RA tăng ca rơi sang hôm sau
  const [otBusy, setOtBusy] = useState(false);
  // Chấm bù "sang hôm sau" (07/09/2026): ca đêm quên RA 06:00 sáng, tăng ca vắt nửa đêm. Không có
  // ô này thì lượt 06:00 dính ngày công ⇒ gom về hôm trước, ngày treo vẫn treo.
  const [nextDay, setNextDay] = useState(false);

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
  const sugToNext = !!detail?.ot_suggestion?.to_next_day;
  useEffect(() => {
    if (sugFrom && sugTo) {
      setOtIn(sugFrom);
      setOtOut(sugTo);
      setOtOutNext(sugToNext);
    }
  }, [sugFrom, sugTo, sugToNext]);

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
        next_day: nextDay,
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

  // Xác nhận tăng ca theo phiếu (07/09/2026): máy quyết thêm lượt nào — `bu_cap` (đã ra ca chính
  // trước giờ phiếu ⇒ thêm cặp VÀO/RA TC) hay `tach_phien` (thợ chỉ bấm 2 lượt ⇒ thêm RA ca chính +
  // VÀO TC, lượt RA thật thành RA TC) — cùng một đường với nút hàng loạt trên Bảng công.
  async function confirmOt() {
    const kieu = detail?.ot_suggestion?.kieu ?? "bu_cap";
    if (kieu === "bu_cap" && !otOut) {
      setError("Nhập giờ ra tăng ca thực tế.");
      return;
    }
    setOtBusy(true);
    setError(null);
    try {
      const res = await api.attendance.otConfirm(token, {
        date,
        employee_ids: [employeeId],
        to_time: kieu === "bu_cap" ? otOut : null,
        to_next_day: kieu === "bu_cap" ? otOutNext : false,
      });
      if (res.skipped.length) {
        setError(res.skipped[0].reason);
      }
      load();
      onChanged();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Lỗi khi xác nhận tăng ca theo phiếu.",
      );
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
                    <AlertTriangle size={14} /> Chưa có cặp bấm tăng ca — phiếu{" "}
                    {detail.ot_suggestion.from_time}
                    {detail.ot_suggestion.from_next_day ? " (+1)" : ""}–
                    {detail.ot_suggestion.to_time}
                    {detail.ot_suggestion.to_next_day ? " (+1)" : ""}
                  </h4>
                  {detail.ot_suggestion.kieu === "tach_phien" ? (
                    <>
                      <p className="cc-ot-suggest__hint">
                        NV chỉ bấm 2 lượt, lượt RA đã phủ luôn giờ tăng ca. Máy
                        sẽ thêm <b>RA ca chính lúc hết ca</b> và{" "}
                        <b>VÀO tăng ca {detail.ot_suggestion.from_time}</b>;
                        lượt RA thật cuối ngày thành RA tăng ca (bấm ra là sự
                        thật, phiếu là trần).
                      </p>
                      <div className="cc-adjust-action-row">
                        <button
                          className="btn cc-btn-add-punch"
                          onClick={confirmOt}
                          disabled={otBusy}
                        >
                          {otBusy ? (
                            <RefreshCw className="cc-animate-spin" size={14} />
                          ) : (
                            "Tách phiên theo phiếu"
                          )}
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="cc-ot-suggest__hint">
                        Vào tăng ca lấy theo phiếu ({otIn}
                        {detail.ot_suggestion.from_next_day ? " +1" : ""}); sửa{" "}
                        <b>giờ ra</b> theo thực tế rồi lưu.
                      </p>
                      <div className="cc-ot-suggest__grid">
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
                        <label
                          className="ns-check"
                          style={{ alignSelf: "end" }}
                        >
                          <input
                            type="checkbox"
                            checked={otOutNext}
                            onChange={(e) => setOtOutNext(e.target.checked)}
                          />{" "}
                          Sang ngày hôm sau
                        </label>
                      </div>
                      <div className="cc-adjust-action-row">
                        <button
                          className="btn cc-btn-add-punch"
                          onClick={confirmOt}
                          disabled={otBusy}
                        >
                          {otBusy ? (
                            <RefreshCw className="cc-animate-spin" size={14} />
                          ) : (
                            "Chấm bù cặp tăng ca"
                          )}
                        </button>
                      </div>
                    </>
                  )}
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
                      <span className="cc-field-label">Ngày</span>
                      <label
                        className="ns-check"
                        title="Ca đêm quên bấm RA 06:00 sáng, hoặc tăng ca vắt nửa đêm"
                      >
                        <input
                          type="checkbox"
                          checked={nextDay}
                          onChange={(e) => setNextDay(e.target.checked)}
                        />{" "}
                        Sang hôm sau
                      </label>
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
                        "Thêm chấm bù"
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
