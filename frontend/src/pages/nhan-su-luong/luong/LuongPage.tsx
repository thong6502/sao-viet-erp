// Lương (module `luong`, Phase 1 — lương thời gian). 5 tab:
//   • Bảng lương tháng — Tạo → soát ô vàng → Chốt → xuất Excel + file chuyển khoản.
//   • Lương nhân viên — khai báo (nhóm/bậc + mức) & điều chỉnh (lịch sử).
//   • Tạm ứng — ghi nhiều lần → duyệt → tự trừ.
//   • Cấu hình lương — 3 tab con: bậc lương & KPI · cơ chế theo bộ phận · phụ cấp & bảo hiểm.
//   • Phiếu lương của tôi — self-service.
import { useEffect, useState } from "react";
import {
  Calendar,
  Users,
  Sliders,
  Wallet,
  Receipt,
  HandCoins,
} from "lucide-react";
import type { NavigateFn } from "../../../components/AppShell";
import { useAuth } from "../../../auth/useAuth";
import { useCan, useSelfService } from "../../../auth/permissions";
import { CauHinhLuongTab } from "../../CauHinhLuongTab";
import { DiscardChangesDialog } from "../../../components/DiscardChangesDialog";
import type { Tab } from "./shared/types";
import { BangLuongTab } from "./tabs/BangLuongTab";
import { NhanVienTab } from "./tabs/NhanVienTab";
import { TamUngTab } from "./tabs/TamUngTab";
import { TamUngCuaToiTab } from "./tabs/TamUngCuaToiTab";
import { PhieuLuongTab } from "./tabs/PhieuLuongTab";
import "../../nhan-su.css";
import "../../luong.css";

export function LuongPage({
  navigate,
  focusEmployeeId,
  eventTick,
  openTab,
}: {
  /** Nhảy chéo màn — tab Tạm ứng mở phiếu chi đã lập bên Kế toán. */
  navigate?: NavigateFn;
  focusEmployeeId?: number;
  /** Tăng mỗi sự kiện real-time (SSE) → tab Tạm ứng đang mở tự refetch, không cần đổi màn. */
  eventTick?: number;
  /** Liên thông từ màn Phòng ban ("Sửa ở Cấu hình lương") → mở thẳng tab cấu hình. */
  openTab?: "cauhinh";
}) {
  const { token } = useAuth();
  const can = useCan();
  const canManage = can("luong", "update");
  // `luong:read` (cột Xem) nay chỉ MỞ MÀN — không còn mở tab quản lý nào. Hai tab cá nhân
  // (Phiếu lương / Tạm ứng của tôi) là dữ liệu của chính người đăng nhập, không cần ô.
  const canCreateAdvance = can("luong", "create");
  const canApproveAdvance = can("luong", "approve");
  const canLockPeriod = can("luong", "lock");
  // Ô TỰ PHỤC VỤ (đợt 3) — quản trị TẮT ĐƯỢC. Không hỏi thì tắt xong nút vẫn bày ra, bấm
  // mới ăn 403: trông như hệ thống hỏng chứ không như "anh không có quyền".
  const tuPhucVu = useSelfService();
  // Ô RIÊNG (10/08/2026): "Đã chi" tuyên bố TIỀN ĐÃ RA TỚI TAY người lao động và khoá kỳ —
  // khác hẳn "Chốt" (số đã tính xong). Ngoài đời hai người: người tính lương chốt số, kế toán
  // mới xác nhận đã trả.
  const canMarkPaid = can("luong", "manage_status");
  const canExportPayroll = can("luong", "export");
  // BẢNG LƯƠNG THÁNG là công cụ QUẢN LÝ (danh sách cả công ty + Tính lại + Chốt kỳ) ⇒ Ô RIÊNG
  // từ 15/08/2026, cùng khuôn "Bảng công tháng" bên Chấm công. Trước đó nó đi theo cột Xem, nên
  // cấp ô Lương ở phạm vi "Của tôi" là thợ vẫn mở được bảng lương của cả công ty.
  // Vẫn cho những ai có việc PHẢI làm trên bảng đó (chốt kỳ · đánh dấu đã chi · xuất file) vào —
  // không thì cấp đúng ô của họ mà vẫn không thấy chỗ để bấm.
  // Cột Thao tác KHÔNG mở tab nào (chủ chốt 15/08/2026) — nó chỉ cho GHI vào tab đã mở được.
  // Trước đó `|| canManage` làm tab hiện ra rồi bấm vào ăn 403, vì máy chủ đòi ô riêng.
  const canOpenBangLuong = can("luong", "view_payroll_table");
  const canLuongNhanVien = can("luong", "manage_salary_profiles");
  // Tab TẠM ỨNG là danh sách phiếu của NGƯỜI KHÁC ⇒ đi theo ô "Duyệt tạm ứng" (đã có sẵn), không
  // theo cột Xem. Tạm ứng CỦA MÌNH nằm ở tab riêng bên phải, không cần ô nào.
  const canOpenTamUng = canApproveAdvance;
  // Cấu hình lương là dữ liệu nhạy cảm: quyền đọc module không đủ.
  // Người có quyền sửa luôn được xem để tránh ma trận quyền cũ khóa nhầm quản trị viên.
  // Tab "Cấu hình lương" đi theo ĐÚNG ô của nó (`Xem cấu hình lương`). Trước 11/08/2026 còn
  // `|| canManage`: ai bật ô Thao tác là tab cấu hình tự bung ra — mà sửa một dòng lương và sửa
  // thang bậc / hệ số / thuế của cả công ty là hai mức khác hẳn nhau.
  const canReadConfig = can("luong", "view_salary");
  const [tab, setTab] = useState<Tab>(
    canOpenBangLuong ? "bang" : canReadConfig ? "cauhinh" : "phieu",
  );
  // Cấu hình lương đang có thay đổi chưa lưu → chặn rời tab (S5).
  const [cfgDirty, setCfgDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);
  function go(next: Tab) {
    if (next === tab) return;
    if (tab === "cauhinh" && cfgDirty) setPendingTab(next);
    else setTab(next);
  }

  // Liên thông từ Hồ sơ nhân sự → mở tab "Lương nhân viên" tại đúng NV.
  useEffect(() => {
    if (focusEmployeeId && canManage) setTab("nhanvien");
  }, [focusEmployeeId, canManage]);
  useEffect(() => {
    if (openTab === "cauhinh" && canReadConfig) setTab("cauhinh");
  }, [openTab, canReadConfig]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          {/* Eyebrow = TÊN SECTION trên thanh bên, chép NGUYÊN VĂN và chỉ MỘT cấp — không ghi
              tên item ("Lương") vì <h1> ngay dưới đã nói rồi. Lớp phải là `eyebrow` (global.css);
              `ns__eyebrow` KHÔNG có CSS ở đâu cả, dùng nhầm là ra chữ thường 15px. */}
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="ns__title">Lương</h1>
          <p className="ns__sub">
            Bảng lương thời gian hàng tháng · tự kéo công từ Chấm công
          </p>
        </div>
      </header>

      <nav className="ns-tabs cc-tabs lg-tabs" aria-label="Phân hệ Lương">
        <div className="lg-tabs__group">
          {canOpenBangLuong && (
            <button
              className={`lg-tab-btn ${tab === "bang" ? "is-active" : ""}`}
              onClick={() => go("bang")}
              title="Quản lý bảng lương tháng"
            >
              <Calendar className="lg-tab-btn__icon" />
              <span>Bảng lương tháng</span>
            </button>
          )}
          {canLuongNhanVien && (
            <button
              className={`lg-tab-btn ${tab === "nhanvien" ? "is-active" : ""}`}
              onClick={() => go("nhanvien")}
              title="Khai báo & điều chỉnh lương nhân viên"
            >
              <Users className="lg-tab-btn__icon" />
              <span>Lương nhân viên</span>
            </button>
          )}
          {canOpenTamUng && (
            <button
              className={`lg-tab-btn ${tab === "tamung" ? "is-active" : ""}`}
              onClick={() => go("tamung")}
              title="Duyệt & quản lý tạm ứng"
            >
              <Wallet className="lg-tab-btn__icon" />
              <span>Tạm ứng</span>
            </button>
          )}
          {canReadConfig && (
            <button
              className={`lg-tab-btn ${tab === "cauhinh" ? "is-active" : ""}`}
              onClick={() => go("cauhinh")}
              title="Cấu hình thang bậc lương & cơ chế"
            >
              <Sliders className="lg-tab-btn__icon" />
              <span>Cấu hình lương</span>
              {cfgDirty && (
                <span className="lg-tab-badge lg-tab-badge--dirty" title="Có thay đổi chưa lưu">•</span>
              )}
            </button>
          )}
        </div>

        {(canOpenBangLuong || canManage || canOpenTamUng) && (
          <div className="lg-tabs__divider" aria-hidden="true" />
        )}

        {tuPhucVu && (
          <div className="lg-tabs__group lg-tabs__group--personal">
            <button
              className={`lg-tab-btn ${tab === "phieu" ? "is-active" : ""}`}
              onClick={() => go("phieu")}
              title="Xem phiếu lương cá nhân"
            >
              <Receipt className="lg-tab-btn__icon" />
              <span>Phiếu lương của tôi</span>
            </button>
            <button
              className={`lg-tab-btn ${tab === "tamung-me" ? "is-active" : ""}`}
              onClick={() => go("tamung-me")}
              title="Đề nghị & theo dõi tạm ứng cá nhân"
            >
              <HandCoins className="lg-tab-btn__icon" />
              <span>Tạm ứng của tôi</span>
            </button>
          </div>
        )}
      </nav>

      {tab === "bang" && canOpenBangLuong && (
        <BangLuongTab
          token={token!}
          canManage={canManage}
          canLockPeriod={canLockPeriod}
          canMarkPaid={canMarkPaid}
          canExportPayroll={canExportPayroll}
        />
      )}
      {tab === "nhanvien" && canLuongNhanVien && (
        <NhanVienTab token={token!} focusEmployeeId={focusEmployeeId} />
      )}
      {tab === "tamung" && canOpenTamUng && (
        <TamUngTab
          token={token!}
          navigate={navigate}
          eventTick={eventTick}
          canCreateAdvance={canCreateAdvance}
          canApproveAdvance={canApproveAdvance}
        />
      )}
      {tab === "cauhinh" && canReadConfig && (
        <CauHinhLuongTab
          token={token!}
          readOnly={!canManage}
          onDirtyChange={setCfgDirty}
          navigate={navigate}
        />
      )}
      {tab === "phieu" && tuPhucVu && <PhieuLuongTab token={token!} />}
      {tab === "tamung-me" && tuPhucVu && (
        <TamUngCuaToiTab token={token!} eventTick={eventTick} canCreate={canCreateAdvance} />
      )}

      <DiscardChangesDialog
        open={pendingTab !== null}
        message="Bạn có thay đổi chưa lưu ở Cấu hình lương. Rời đi mà không lưu?"
        onDiscard={() => {
          setCfgDirty(false);
          if (pendingTab) setTab(pendingTab);
          setPendingTab(null);
        }}
        onKeepEditing={() => setPendingTab(null)}
      />
    </main>
  );
}
