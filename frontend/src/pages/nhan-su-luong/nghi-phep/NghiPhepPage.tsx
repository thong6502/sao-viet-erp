// Nghỉ phép (module `nhan_su`). 3 tab:
//   • Đơn của tôi — NV tạo đơn xin nghỉ + xem/hủy đơn của mình (self-service).
//   • Duyệt đơn (HR) — chờ duyệt → duyệt / từ chối; xem toàn bộ.
//   • Loại nghỉ (HR) — khai loại nghỉ (có lương / hạn mức).
// (tách từ pages/NghiPhepPage.tsx).
import { useEffect, useState } from "react";
import { useAuth } from "../../../auth/useAuth";
import { useCan, useSelfService } from "../../../auth/permissions";
import { Calendar, ClipboardCheck, FileText, Sliders } from "lucide-react";
import { ApproveTab } from "./tabs/ApproveTab";
import { CalendarTab } from "./tabs/CalendarTab";
import { LeaveTypesTab } from "./tabs/LeaveTypesTab";
import { MyLeaveTab } from "./tabs/MyLeaveTab";
import type { Tab } from "./shared/types";
import "../../nhan-su.css";
import "../../cham-cong.css";
import "../../nghi-phep.css";

export function NghiPhepPage({ onChanged, focusEmployeeId }: { onChanged?: () => void; focusEmployeeId?: number }) {
  const { token } = useAuth();
  const can = useCan();
  // Quyền DUYỆT đơn — HCNS/Admin, VÀ tổ trưởng (chủ chốt 29/07/2026: tổ trưởng duyệt đơn trong
  // tổ mình). Dùng cho tab "Duyệt đơn" + "Lịch nghỉ".
  const canManage = can("nghi_phep", "approve");
  // Ô TỰ PHỤC VỤ (đợt 3) — quản trị TẮT ĐƯỢC. Không hỏi thì tắt xong nút vẫn bày ra, bấm
  // mới ăn 403: trông như hệ thống hỏng chứ không như "anh không có quyền".
  const tuPhucVu = useSelfService();
  // Ô THAO TÁC của Tự phục vụ — TÁCH khỏi ô Xem ngày 11/08/2026. Tab/danh sách đi theo ô
  // Xem; còn nút GỬI · SỬA · HUỶ thì đi theo ô này.
  // GHI LÀ GHI — gửi / sửa / huỷ đơn của CHÍNH MÌNH vẫn đòi ô Thao tác của màn Nghỉ phép
  // (chủ chốt 15/08/2026: *"tôi chưa bật thao tác vẫn bấm gửi đơn được nè"*). Chỉ phần ĐỌC dữ
  // liệu của mình mới là quyền đương nhiên.
  const tuPhucVuGhi = can("nghi_phep", "create");
  // Danh mục LOẠI NGHỈ là chính sách TOÀN CÔNG TY, chỉ HCNS/Admin. Phải gác bằng `update` cho
  // KHỚP backend (`routers/leaves.py` gác 3 endpoint /types bằng `update`) — gác bằng `approve`
  // là tổ trưởng (approve=true, update=false) nhìn thấy tab, mở ra, bấm lưu rồi ăn 403: màn
  // mời-rồi-đuổi, người dùng tưởng mình có quyền.
  // Danh mục LOẠI NGHỈ có ô riêng từ 15/08/2026 (mg 0197) — trước đó nó dùng chung cột với nút
  // "Thao tác", nên bật Thao tác (để thợ gửi/huỷ đơn của mình) là mở luôn quyền sửa chính sách
  // nghỉ của cả nhà máy.
  const canTypes = can("nghi_phep", "manage_leave_types");
  // Ai bị gỡ ô Tự phục vụ thì mở thẳng tab Duyệt — không thì vào màn là thấy tab trống.
  const [tab, setTab] = useState<Tab>("me");

  // Liên thông từ Hồ sơ NV → mở "Duyệt đơn" lọc đúng NV đó.
  useEffect(() => {
    if (focusEmployeeId && canManage) setTab("approve");
  }, [focusEmployeeId, canManage]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          {/* Eyebrow = tên SECTION trên sidebar, chép nguyên văn, MỘT cấp (không ghi tên
              item "Nghỉ phép" — tiêu đề ngay dưới đã nói rồi). Lớp phải là `eyebrow`. */}
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="ns__title">Nghỉ phép</h1>
          <p className="ns__sub">Đơn xin nghỉ · duyệt · loại nghỉ. Ngày nghỉ đã duyệt hiện trên Bảng công tháng.</p>
        </div>
      </header>
      <nav className="ns-tabs cc-tabs lg-tabs" aria-label="Phân hệ Nghỉ phép">
        <div className="lg-tabs__group">
          {tuPhucVu && (
            <button className={`lg-tab-btn ${tab === "me" ? "is-active" : ""}`} onClick={() => setTab("me")} title="Đơn xin nghỉ cá nhân">
              <FileText className="lg-tab-btn__icon" />
              <span>Đơn của tôi</span>
            </button>
          )}
          {canManage && (
            <button className={`lg-tab-btn ${tab === "approve" ? "is-active" : ""}`} onClick={() => setTab("approve")} title="Duyệt đơn xin nghỉ nhân viên">
              <ClipboardCheck className="lg-tab-btn__icon" />
              <span>Duyệt đơn</span>
            </button>
          )}
          {canManage && (
            <button className={`lg-tab-btn ${tab === "calendar" ? "is-active" : ""}`} onClick={() => setTab("calendar")} title="Lịch nghỉ toàn công ty">
              <Calendar className="lg-tab-btn__icon" />
              <span>Lịch nghỉ</span>
            </button>
          )}
          {/* Loại nghỉ theo quyền UPDATE (khác 3 tab trên dùng APPROVE) — giữ đúng phân quyền
              của dev, đừng gộp về canManage. */}
          {canTypes && (
            <button className={`lg-tab-btn ${tab === "types" ? "is-active" : ""}`} onClick={() => setTab("types")} title="Cấu hình loại nghỉ">
              <Sliders className="lg-tab-btn__icon" />
              <span>Loại nghỉ</span>
            </button>
          )}
        </div>
      </nav>
      {tab === "me" && tuPhucVu && (
        <MyLeaveTab token={token!} onChanged={onChanged} coQuyenGhi={tuPhucVuGhi} />
      )}
      {tab === "approve" && canManage && <ApproveTab token={token!} onChanged={onChanged} focusEmployeeId={focusEmployeeId} />}
      {tab === "calendar" && canManage && <CalendarTab token={token!} />}
      {tab === "types" && canTypes && <LeaveTypesTab token={token!} />}
    </main>
  );
}
