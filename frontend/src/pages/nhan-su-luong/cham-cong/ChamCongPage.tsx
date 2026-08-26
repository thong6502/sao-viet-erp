// Chấm công GPS (module `nhan_su`). 3 tab:
//   • Chấm công của tôi — lấy GPS trình duyệt, chấm VÀO/RA nếu trong bán kính điểm gần nhất.
//   • Điểm chấm công (HR) — khai toạ độ + bán kính; "Lấy vị trí hiện tại" để điền nhanh.
//   • Nhật ký chấm công (HR) — 100 lượt bấm gần nhất, tìm được theo tên/mã NV.
// Server là cổng geofence thật (Haversine); ngoài phạm vi bị chặn cứng.
import { useEffect, useState } from "react";
import {
  UserCheck,
  CalendarDays,
  MapPin,
  Clock,
  Clock3,
  Calendar,
  ClipboardList,
  Table,
  FileEdit,
} from "lucide-react";
import { useAuth } from "../../../auth/useAuth";
import { useCan, useSelfService } from "../../../auth/permissions";
import type { NavigateFn } from "../../../components/AppShell";
import type { Tab } from "./shared/types";
import { AdjustRequestsTab } from "./tabs/AdjustRequestsTab";
import { CalendarTab } from "./tabs/CalendarTab";
import { LateEarlyTab } from "./tabs/LateEarlyTab";
import { LocationsTab } from "./tabs/LocationsTab";
import { LogsTab } from "./tabs/LogsTab";
import { MyCheckIn } from "./tabs/MyCheckInTab";
import { MyTimesheetTab } from "./tabs/MyTimesheetTab";
import { ShiftsTab } from "./tabs/ShiftsTab";
import { TimesheetTab } from "./tabs/TimesheetTab";
import "../../nhan-su.css";
import "../../cham-cong.css";

export function ChamCongPage({
  navigate,
  focusEmployeeId,
  onChanged,
  eventTick,
}: {
  navigate?: NavigateFn;
  focusEmployeeId?: number;
  /** Gọi sau mỗi lần tải/thao tác → AppShell refetch badge sidebar + chuông ngay. */
  onChanged?: () => void;
  /** Tăng theo mỗi sự kiện real-time (SSE) → tab phiếu đang mở tự tải lại, khỏi bắt F5. */
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá RIÊNG của màn Chấm công (10/08/2026) — không mượn quyền màn Hồ sơ nhân sự nữa.
  // `update` = ô "Cấu hình chấm công": gác cả ĐỌC lẫn GHI ba tab Điểm chấm công / Khai ca /
  // Lịch & Ngày lễ (trước đây đường đọc chỉ đòi `read` nên ẩn tab mà API vẫn trả dữ liệu).
  // MỘT Ô = MỘT TAB (chủ chốt 15/08/2026, mg 0194). Trước đó `canConfig` một mình mở BA tab
  // cấu hình — bật một ô ra ba màn, người cấp quyền không biết mình vừa mở cái gì.
  const canDiemChamCong = can("cham_cong", "manage_locations");
  const canKhaiCa = can("cham_cong", "manage_shifts");
  const canLichLe = can("cham_cong", "manage_calendar");
  // Ghi vào ba tab cấu hình: vẫn là ô Thao tác chung của màn (luật "bật Thao tác là thao tác cả").
  const canConfig = can("cham_cong", "update");
  // Bảng công tháng = lưới cả xưởng + nút Chốt kỳ ⇒ Ô RIÊNG, không đi theo `read` nữa.
  // `read` nay = mở màn + ba tab CỦA TÔI (bấm giờ · lịch công của mình · tự xin đi muộn).
  const canView = can("cham_cong", "view_timesheet");
  // Ô RIÊNG (11/08/2026): Bảng công tháng là số công đã tổng hợp; NHẬT KÝ là từng lượt bấm
  // kèm giờ + toạ độ của cả xưởng — ai đi sớm về muộn hôm nào, đọc là biết. Hai mức nhạy cảm
  // khác nhau nên hai ô khác nhau.
  const canViewLog = can("cham_cong", "view_log");
  // Tab "Yêu cầu chỉnh công" có KHOÁ RIÊNG từ 11/08/2026 — không còn ăn theo `cham_cong`.
  // Xem danh sách = ô Xem của màn đó; duyệt / từ chối = ô Duyệt riêng.
  // Tab Yêu cầu chỉnh công hiện theo chính ô DUYỆT — bỏ ô "xem" riêng (mg 0194).
  const canViewYcch = can("cham_cong", "approve");
  const canApproveYcch = can("cham_cong", "approve");
  // Ô TỰ PHỤC VỤ (đợt 3) — quản trị TẮT ĐƯỢC. Không hỏi thì tắt xong nút vẫn bày ra, bấm
  // mới ăn 403: trông như hệ thống hỏng chứ không như "anh không có quyền".
  const tuPhucVu = useSelfService();
  // Ô THAO TÁC của Tự phục vụ — TÁCH khỏi ô Xem ngày 11/08/2026. Tab/danh sách đi theo ô
  // Xem; còn nút GỬI · SỬA · HUỶ thì đi theo ô này.
  // GHI LÀ GHI — gửi / sửa / huỷ đơn của CHÍNH MÌNH vẫn đòi ô Thao tác của màn Chấm công
  // (chủ chốt 15/08/2026: *"tôi chưa bật thao tác vẫn bấm gửi đơn được nè"*). Chỉ phần ĐỌC dữ
  // liệu của mình mới là quyền đương nhiên.
  const tuPhucVuGhi = can("cham_cong", "create");
  const canApproveEl = can("cham_cong", "approve_late_early"); // gộp từ khoá `di_muon`
  // Mặc định vào tab của mình; ai bị gỡ ô Tự phục vụ thì mở thẳng tab xem được — không thì
  // vào màn là thấy một tab trống trơn không hiểu vì sao.
  const [tab, setTab] = useState<Tab>("me");

  // Liên thông từ Hồ sơ NV → mở "Nhật ký chấm công" lọc đúng NV đó.
  useEffect(() => {
    if (focusEmployeeId && canViewLog) setTab("logs");
  }, [focusEmployeeId, canViewLog]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          <h1 className="ns__title">Chấm công</h1>
          <p className="ns__sub">
            Chấm công theo vị trí GPS · phải ở gần điểm làm việc đã khai
          </p>
        </div>
      </header>

      <nav className="cc-tabs">
        {tuPhucVu && (
          <button
            className={tab === "me" ? "is-active" : ""}
            onClick={() => setTab("me")}
          >
            <UserCheck size={14} /> Chấm công của tôi
          </button>
        )}
        {tuPhucVu && (
          <button
            className={tab === "my-timesheet" ? "is-active" : ""}
            onClick={() => setTab("my-timesheet")}
          >
            <CalendarDays size={14} /> Công của tôi
          </button>
        )}
        {/* Hiện với người CÓ ô Tự phục vụ (ai cũng phải xin đi muộn/về sớm cho CHÍNH MÌNH được) —
            hoặc với người DUYỆT phiếu của tổ. Trước đây "LUÔN hiện", nhưng từ khi Tự phục vụ thành
            ô tắt được thì luôn-hiện nghĩa là bày nút cho người không bấm được. */}
        {(tuPhucVu || canApproveEl) && (
          <button
            className={tab === "di-muon" ? "is-active" : ""}
            onClick={() => setTab("di-muon")}
          >
            <Clock3 size={14} /> Đi muộn / về sớm / nghỉ nửa buổi
          </button>
        )}
        {canDiemChamCong && (
          <button
            className={tab === "locations" ? "is-active" : ""}
            onClick={() => setTab("locations")}
          >
            <MapPin size={14} /> Điểm chấm công
          </button>
        )}
        {canKhaiCa && (
          <button
            className={tab === "khai-ca" ? "is-active" : ""}
            onClick={() => setTab("khai-ca")}
          >
            <Clock size={14} /> Khai ca
          </button>
        )}
        {canLichLe && (
          <button
            className={tab === "lich-le" ? "is-active" : ""}
            onClick={() => setTab("lich-le")}
          >
            <Calendar size={14} /> Lịch & Ngày lễ
          </button>
        )}
        {canViewLog && (
          <button
            className={tab === "logs" ? "is-active" : ""}
            onClick={() => setTab("logs")}
          >
            <ClipboardList size={14} /> Nhật ký chấm công
          </button>
        )}
        {canView && (
          <button
            className={tab === "timesheet" ? "is-active" : ""}
            onClick={() => setTab("timesheet")}
          >
            <Table size={14} /> Bảng công tháng
          </button>
        )}
        {canViewYcch && (
          <button
            className={tab === "yeu-cau" ? "is-active" : ""}
            onClick={() => setTab("yeu-cau")}
          >
            <FileEdit size={14} /> Yêu cầu chỉnh công
          </button>
        )}
      </nav>

      {tab === "me" && (
        <MyCheckIn
          token={token!}
          canConfig={canConfig}
          coQuyenGhi={tuPhucVuGhi}
          navigate={navigate}
        />
      )}
      {tab === "my-timesheet" && tuPhucVu && <MyTimesheetTab token={token!} />}
      {tab === "di-muon" && (
        <LateEarlyTab
          token={token!}
          canApprove={canApproveEl}
          onChanged={onChanged}
          eventTick={eventTick}
        />
      )}
      {tab === "locations" && canConfig && <LocationsTab token={token!} />}
      {tab === "khai-ca" && canConfig && <ShiftsTab token={token!} />}
      {tab === "lich-le" && canConfig && <CalendarTab token={token!} />}
      {tab === "logs" && canViewLog && (
        <LogsTab token={token!} focusEmployeeId={focusEmployeeId} />
      )}
      {tab === "timesheet" && canView && (
        <TimesheetTab
          token={token!}
          canAdjust={can("cham_cong", "adjust")}
          canLock={can("cham_cong", "lock")}
        />
      )}
      {tab === "yeu-cau" && canViewYcch && (
        <AdjustRequestsTab token={token!} canAdjust={canApproveYcch} />
      )}
    </main>
  );
}
