// Khay hồ sơ nhân viên: điều phối tab + chuỗi reload (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  assetUrl,
  type EmployeeDetail,
  type EmployeeMeta,
} from "../../../api/client";
import { EmptyState } from "../../../components/EmptyState";
import { useCan } from "../../../auth/permissions";
import { fmtDate } from "../../../utils/format";
import type { NavigateFn } from "../../../components/AppShell";
import {
  AlertTriangle,
  Briefcase,
  Calendar,
  ChevronDown,
  Clock,
  CreditCard,
  Edit2,
  TrendingUp,
  UserCheck,
  UserMinus,
  UserPlus,
  X,
} from "lucide-react";
import type { Tab } from "./shared/types";
import { errMsg } from "./shared/helpers";
import { StatusBadge } from "./components/badges";
import { InfoTab } from "./tabs/InfoTab";
import { SalaryTab } from "./tabs/SalaryTab";
import { AccountTab } from "./tabs/AccountTab";
import { EventsTab } from "./tabs/EventsTab";
import { FilesTab } from "./tabs/FilesTab";
import { ActivityTab } from "./tabs/ActivityTab";
import { ActionDialog } from "./modals/ActionDialog";

export function EmployeeDetailPanel({
  token,
  employeeId,
  meta,
  navigate,
  onClose,
  onChanged,
}: {
  token: string;
  employeeId: number;
  meta: EmployeeMeta | null;
  navigate?: NavigateFn;
  onClose: () => void;
  onChanged: () => void;
}) {
  const can = useCan();
  const canUpdate = can("nhan_su", "update");
  const canEditSalaryFields = can("nhan_su", "edit_salary");
  const canViewSalary =
    can("nhan_su", "view_salary") || canEditSalaryFields;
  const canManageStatus = can("nhan_su", "manage_status");
  const canTransfer = can("nhan_su", "transfer");
  const canViewAccount = can("nguoi_dung", "read");
  const [emp, setEmp] = useState<EmployeeDetail | null>(null);
  const [tab, setTab] = useState<Tab>("info");
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null); // dialog kind
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [editInfo, setEditInfo] = useState(false);
  const [editSalary, setEditSalary] = useState(false);

  const reload = useCallback(() => {
    api.employees
      .get(token, employeeId)
      .then(setEmp)
      .catch((e) => setError(errMsg(e)));
  }, [token, employeeId]);

  useEffect(() => {
    setTab("info");
    setEditInfo(false);
    setEditSalary(false);
    reload();
  }, [reload]);

  if (!emp) {
    // Tách "đang tải" khỏi "gọi hỏng": trước đây cả hai in cùng một dòng chữ xám nên mất
    // mạng cũng trông y như đang chờ — người dùng ngồi đợi mãi một khay không bao giờ mở.
    return (
      <div className="ns2-detail__loading">
        {error ? (
          <EmptyState trangThai="loi" loi={error} onThuLai={reload} />
        ) : (
          <EmptyState trangThai="dang-tai" />
        )}
      </div>
    );
  }

  const resigned = emp.status === "resigned";
  const tabs: [Tab, string][] = [
    ["info", "Thông tin"],
    ...(canViewSalary ? [["salary", "Lương & BHXH"] as [Tab, string]] : []),
    // Gộp từ màn Người dùng (đã bỏ): mọi tài khoản thuộc một hồ sơ nên quản ngay tại đây.
    ...(canViewAccount
      ? [["account", "Tài khoản & Quyền"] as [Tab, string]]
      : []),
    ["events", "Quá trình công tác"],
    ["files", "Đính kèm"],
    ["activity", "Nhật ký"],
  ];

  return (
    <div className="ns2-detail">
      <header className="ns2-detail__head">
        <button
          type="button"
          className="ns-modal__close-btn"
          onClick={onClose}
          aria-label="Đóng"
        >
          <X size={18} />
        </button>
        <div className="ns-avatar ns-avatar--lg">
          {assetUrl(emp.photo_url) ? (
            <img src={assetUrl(emp.photo_url)!} alt={emp.full_name} />
          ) : (
            emp.full_name.trim().slice(0, 1).toUpperCase()
          )}
        </div>
        <div className="ns2-detail__id">
          <h2>
            {emp.full_name}
            <StatusBadge status={emp.status} />
          </h2>
          <p className="ns-detail__meta">
            <Briefcase size={13} />
            {/* job_grade_name là nhãn danh mục (Thợ lành nghề…Lính mới) — hiện nguyên văn, không ghép tiền tố. */}
            {emp.code} · {emp.department_name ?? "—"} · {emp.position ?? "—"}
            {(emp.job_grade_name ?? emp.job_grade)
              ? ` · ${emp.job_grade_name ?? emp.job_grade}`
              : ""}
          </p>
          <p className="ns-detail__meta">
            <Calendar size={13} />
            Vào làm {fmtDate(emp.hire_date)} ·{" "}
            {emp.account_username
              ? `🔑 ${emp.account_username}`
              : "chưa nối tài khoản"}
          </p>
        </div>
      </header>

      {(navigate || canUpdate || canManageStatus || canTransfer) && (
        <div className="ns-detail__actions">
          <div className="ns-detail__shortcuts">
            {navigate && (
              <>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() =>
                    navigate("cham-cong", { focusEmployeeId: emp.id })
                  }
                >
                  <Clock size={12} />
                  Chấm công
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() =>
                    navigate("nghi-phep", { focusEmployeeId: emp.id })
                  }
                >
                  <Calendar size={12} />
                  Nghỉ phép
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => navigate("luong", { focusEmployeeId: emp.id })}
                >
                  <CreditCard size={12} />
                  Lương
                </button>
              </>
            )}
          </div>
          <div className="ns-detail__ops">
            {canUpdate && tab === "info" && !resigned && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setEditInfo(!editInfo)}
              >
                <Edit2 size={12} />
                {editInfo ? "Hủy sửa" : "Sửa thông tin"}
              </button>
            )}
            {canUpdate &&
              canEditSalaryFields &&
              tab === "salary" &&
              canViewSalary &&
              !resigned && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setEditSalary(!editSalary)}
              >
                <Edit2 size={12} />
                {editSalary ? "Hủy sửa" : "Sửa lương & BHXH"}
              </button>
            )}
            {(canManageStatus || canTransfer) && (
              <div className="ns-dropdown">
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                >
                  Thao tác hồ sơ
                  <ChevronDown size={12} />
                </button>
                {dropdownOpen && (
                  <div className="ns-dropdown-menu">
                    {/* Hiện ở CẢ "Thử việc" (xác nhận sớm) lẫn "Hết thử việc · chờ xác nhận".
                        Thiếu vế thứ hai là người đã hết hạn không còn đường nào lên chính thức. */}
                    {canManageStatus
                      && (emp.status === "probation" || emp.status === "probation_ended") && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("confirm");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserCheck size={14} /> Chuyển chính thức
                      </button>
                    )}
                    {canManageStatus && emp.status === "active" && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("leave_start");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserMinus size={14} /> Cho nghỉ dài hạn
                      </button>
                    )}
                    {canManageStatus && emp.status === "on_leave" && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("leave_end");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserCheck size={14} /> Đi làm lại
                      </button>
                    )}
                    {canTransfer && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("transfer");
                          setDropdownOpen(false);
                        }}
                      >
                        <TrendingUp size={14} /> Điều chuyển tổ
                      </button>
                    )}
                    {canTransfer && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("promote");
                          setDropdownOpen(false);
                        }}
                      >
                        <TrendingUp size={14} /> Nâng bậc / Chức danh
                      </button>
                    )}
                    {canManageStatus && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("suspend");
                          setDropdownOpen(false);
                        }}
                      >
                        <AlertTriangle size={14} /> Đình chỉ công tác
                      </button>
                    )}
                    {canManageStatus && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item ns-danger"
                        onClick={() => {
                          setAction("resign");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserMinus size={14} /> Thôi việc / Nghỉ việc
                      </button>
                    )}
                    {canManageStatus && resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("reinstate");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserPlus size={14} /> Tuyển dụng lại
                      </button>
                    )}
                    {/* Tài khoản đăng nhập quản ở tab "Tài khoản & Quyền" — mọi tài khoản
                        thuộc một hồ sơ nên không còn "gỡ liên kết". */}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <nav className="ns-tabs ns2-detail__tabs">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "is-active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="ns2-detail__body">
        {tab === "info" && (
          <InfoTab
            token={token}
            emp={emp}
            meta={meta}
            canUpdate={canUpdate}
            edit={editInfo}
            setEdit={setEditInfo}
            onSaved={() => {
              reload();
              onChanged();
            }}
          />
        )}
        {tab === "salary" && canViewSalary && (
          <SalaryTab
            token={token}
            emp={emp}
            edit={editSalary}
            setEdit={setEditSalary}
            onSaved={() => {
              reload();
              onChanged();
            }}
          />
        )}
        {tab === "account" && canViewAccount && (
          <AccountTab
            token={token}
            emp={emp}
            meta={meta}
            onChanged={() => {
              reload();
              onChanged();
            }}
          />
        )}
        {tab === "events" && (
          <EventsTab token={token} employeeId={employeeId} meta={meta} />
        )}
        {tab === "files" && (
          <FilesTab
            token={token}
            employeeId={employeeId}
            canUpdate={canUpdate}
          />
        )}
        {tab === "activity" && (
          <ActivityTab token={token} employeeId={employeeId} />
        )}
      </div>

      {action && (
        <ActionDialog
          token={token}
          emp={emp}
          meta={meta}
          kind={action}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null);
            reload();
            onChanged();
          }}
        />
      )}
    </div>
  );
}
