// User detail popup (spec-07 PBI-5003 + spec-08 PBI-2003/2006/2008): profile edit (name +
// department), role assignment, lock/unlock, reset password (temp shown once), revoke all
// sessions, plus read-only live sessions and recent activity. Reuses the modal shell (cdlg-*),
// Select, and DiscardChangesDialog. Warns before closing while profile/role are unsaved.
import { useEffect, useState } from "react";
import {
  ApiError,
  api,
  type AuditRow,
  type Department,
  type Role,
  type Session,
  type UserRow,
} from "../api/client";
import { useCan } from "../auth/permissions";
import { Button } from "./Button";
import { ConfirmDialog } from "./ConfirmDialog";
import { DiscardChangesDialog } from "./DiscardChangesDialog";
import { Select } from "./Select";
import "./confirm-dialog.css";
import "./user-detail-dialog.css";

interface UserDetailDialogProps {
  open: boolean;
  user: UserRow | null;
  departments: Department[];
  token: string | null;
  currentUserId: number | null;
  onClose: () => void;
  onChanged: () => void;
}

function deviceLabel(ua: string | null): string {
  if (!ua) return "Thiết bị không rõ";
  const browser = /Edg/.test(ua)
    ? "Edge"
    : /Chrome/.test(ua)
      ? "Chrome"
      : /Firefox/.test(ua)
        ? "Firefox"
        : /Safari/.test(ua)
          ? "Safari"
          : null;
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Android/.test(ua)
      ? "Android"
      : /iPhone|iPad|iOS/.test(ua)
        ? "iOS"
        : /Mac OS X|Macintosh/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : null;
  const parts = [browser, os].filter(Boolean);
  return parts.length ? parts.join(" · ") : ua.length > 48 ? `${ua.slice(0, 48)}…` : ua;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN");
}

export function UserDetailDialog({
  open,
  user,
  departments,
  token,
  currentUserId,
  onClose,
  onChanged,
}: UserDetailDialogProps) {
  const [editName, setEditName] = useState("");
  const [editDept, setEditDept] = useState<number | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [deptRoles, setDeptRoles] = useState<Role[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);
  const [editRole, setEditRole] = useState<number | null>(null);
  const [roleSaving, setRoleSaving] = useState(false);
  const [roleSaved, setRoleSaved] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);

  const [activeBusy, setActiveBusy] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [sessions, setSessions] = useState<Session[]>([]);
  const [activity, setActivity] = useState<AuditRow[]>([]);
  const [sideLoading, setSideLoading] = useState(false);

  const [confirmDiscard, setConfirmDiscard] = useState(false);
  // Popup cảnh báo có đếm ngược 5s cho các thao tác nhạy cảm (đặt lại MK / thu hồi phiên /
  // khóa / đổi hồ sơ / đổi vai trò). Bấm nút chỉ mở popup; xác nhận mới chạy thật.
  const [pending, setPending] = useState<null | {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
    run: () => void;
  }>(null);

  const can = useCan();
  const canManage = can("nguoi_dung", "update");
  const canReset = can("nguoi_dung", "reset_password");
  // Quyền chi tiết nhóm 1 — mỗi thao tác tách riêng.
  const canLock = can("nguoi_dung", "lock");
  const canRevoke = can("nguoi_dung", "revoke_sessions");
  const canDelete = can("nguoi_dung", "delete");
  const canAssignRole = can("nguoi_dung", "assign_role");
  const canTransfer = can("nguoi_dung", "transfer");

  const userId = user?.id ?? null;
  const deptId = user?.department_id ?? null;

  // (Re)load form + side panels when the dialog opens or the user's saved dept changes
  // (dept change drops the role, so the role picker must reload for the new department).
  useEffect(() => {
    if (!open || userId == null || !user) return;
    setEditName(user.name);
    setEditDept(user.department_id);
    setEditRole(user.role_id);
    setProfileError(null);
    setRoleSaved(false);
    setRoleError(null);
    setActionError(null);
    setTempPassword(null);

    let cancelled = false;
    setRolesLoading(true);
    setSideLoading(true);
    const roleP =
      token && deptId != null
        ? api.rbac.roles(token, deptId).catch(() => [] as Role[])
        : Promise.resolve([] as Role[]);
    roleP.then((rs) => !cancelled && setDeptRoles(rs)).finally(() => !cancelled && setRolesLoading(false));
    reloadSide(cancelled);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, userId, deptId, token]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") attemptClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  });

  if (!open || !user) return null;

  const isSelf = currentUserId != null && user.id === currentUserId;
  const profileDirty = editName.trim() !== user.name || editDept !== user.department_id;
  const roleDirty = editRole !== (user.role_id ?? null);
  const deptChanging = editDept !== user.department_id;
  const busy = profileSaving || roleSaving || activeBusy || resetBusy || revokeBusy || deleteBusy;

  function reloadSide(cancelled = false) {
    if (!token || userId == null) return;
    setSideLoading(true);
    Promise.all([
      api.rbac.userSessions(token, userId).catch(() => [] as Session[]),
      api.rbac.userActivity(token, userId).catch(() => [] as AuditRow[]),
    ])
      .then(([ss, act]) => {
        if (cancelled) return;
        setSessions(ss);
        setActivity(act);
      })
      .finally(() => !cancelled && setSideLoading(false));
  }

  function attemptClose() {
    if (busy) return;
    if (profileDirty || roleDirty) setConfirmDiscard(true);
    else onClose();
  }

  async function onSaveProfile() {
    if (!token || !user || editDept == null || !editName.trim() || profileSaving) return;
    setProfileSaving(true);
    setProfileError(null);
    try {
      await api.rbac.updateUser(token, user.id, editName.trim(), editDept);
      onChanged(); // parent refresh → updated user prop re-seeds the form via effect
    } catch (e) {
      if (e instanceof ApiError && e.isForbidden)
        setProfileError("Bạn không có quyền sửa thông tin.");
      else if (e instanceof ApiError && e.status === 404) setProfileError(e.message);
      else setProfileError("Không lưu được thông tin. Vui lòng thử lại.");
    } finally {
      setProfileSaving(false);
    }
  }

  async function onSaveRole() {
    if (!token || !user || roleSaving) return;
    setRoleSaving(true);
    setRoleError(null);
    try {
      await api.rbac.assignUserRole(token, user.id, editRole);
      onChanged();
      setRoleSaved(true);
      reloadSide();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setRoleError(e.message);
      else if (e instanceof ApiError && e.isForbidden) setRoleError("Bạn không có quyền gán vai trò.");
      else setRoleError("Không gán được vai trò. Vui lòng thử lại.");
    } finally {
      setRoleSaving(false);
    }
  }

  async function onToggleActive() {
    if (!token || !user || activeBusy) return;
    setActiveBusy(true);
    setActionError(null);
    try {
      await api.rbac.setUserActive(token, user.id, !user.is_active);
      onChanged();
      reloadSide();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setActionError(e.message);
      else setActionError("Không đổi được trạng thái. Vui lòng thử lại.");
    } finally {
      setActiveBusy(false);
    }
  }

  async function onResetPassword() {
    if (!token || !user || resetBusy) return;
    setResetBusy(true);
    setActionError(null);
    setTempPassword(null);
    try {
      const res = await api.rbac.resetUserPassword(token, user.id);
      setTempPassword(res.temporary_password);
      reloadSide(); // sessions were revoked
    } catch (e) {
      if (e instanceof ApiError && e.isForbidden)
        setActionError("Bạn không có quyền đặt lại mật khẩu.");
      else setActionError("Không đặt lại được mật khẩu. Vui lòng thử lại.");
    } finally {
      setResetBusy(false);
    }
  }

  async function onRevokeSessions() {
    if (!token || !user || revokeBusy) return;
    setRevokeBusy(true);
    setActionError(null);
    try {
      await api.rbac.revokeUserSessions(token, user.id);
      reloadSide();
    } catch (e) {
      if (e instanceof ApiError && e.isForbidden)
        setActionError("Bạn không có quyền thu hồi phiên.");
      else setActionError("Không thu hồi được phiên. Vui lòng thử lại.");
    } finally {
      setRevokeBusy(false);
    }
  }

  async function onDeleteUser() {
    if (!token || !user || deleteBusy) return;
    setDeleteBusy(true);
    setActionError(null);
    try {
      await api.rbac.deleteUser(token, user.id);
      onChanged(); // ẩn khỏi danh sách
      onClose();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setActionError(e.message);
      else if (e instanceof ApiError && e.isForbidden) setActionError("Bạn không có quyền xóa người dùng.");
      else setActionError("Không xóa được người dùng. Vui lòng thử lại.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <>
      <div className="cdlg-overlay" onMouseDown={attemptClose}>
        <div
          className="cdlg cdlg--wide"
          role="dialog"
          aria-modal="true"
          aria-label={`Tài khoản ${user.name}`}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="cdlg__head">
            <h2 className="cdlg__title">Tài khoản · {user.name}</h2>
          </div>
          <div className="cdlg__body udlg">
            {/* Hồ sơ (PBI-2003). */}
            <section className="udlg__section">
              <p className="eyebrow">Hồ sơ</p>
              <div className="udlg__grid">
                <div className="field">
                  <label className="field__label" htmlFor="ud-name">
                    Họ tên
                  </label>
                  <input
                    id="ud-name"
                    className="input"
                    value={editName}
                    disabled={!canManage}
                    onChange={(e) => {
                      setEditName(e.target.value);
                      if (profileError) setProfileError(null);
                    }}
                  />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor="ud-username">
                    Tên đăng nhập
                  </label>
                  <input id="ud-username" className="input" value={user.username} disabled />
                </div>
                <div className="field">
                  <span className="field__label">Phòng ban</span>
                  <Select
                    portal
                    ariaLabel="Phòng ban"
                    value={editDept}
                    placeholder="— Chọn phòng —"
                    disabled={!canManage || !canTransfer}
                    onChange={(v) => {
                      setEditDept(v);
                      if (profileError) setProfileError(null);
                    }}
                    options={departments.map((d) => ({
                      value: d.id,
                      label: d.name,
                      hint: d.code || undefined,
                    }))}
                  />
                  {canManage && !canTransfer && (
                    <span className="udlg__hint">Cần quyền "Chuyển phòng ban" để đổi phòng.</span>
                  )}
                </div>
                <div className="field udlg__status-field">
                  <span className="field__label">Trạng thái</span>
                  <span className={`udlg__badge${user.is_active ? "" : " udlg__badge--locked"}`}>
                    {user.is_active ? "Đang hoạt động" : "Đã khóa"}
                  </span>
                </div>
              </div>
              {deptChanging && (
                <p className="udlg__warn">Đổi phòng ban sẽ gỡ vai trò hiện tại của người này.</p>
              )}
              {canManage && (
                <div className="udlg__row">
                  <Button
                    variant="accent"
                    onClick={() =>
                      setPending({
                        title: "Xác nhận đổi thông tin",
                        message:
                          "Bạn sắp cập nhật hồ sơ người dùng này" +
                          (deptChanging ? " (đổi phòng ban sẽ gỡ vai trò hiện tại)" : "") +
                          ". Kiểm tra kỹ trước khi xác nhận.",
                        confirmLabel: "Lưu thông tin",
                        run: onSaveProfile,
                      })
                    }
                    disabled={!profileDirty || !editName.trim() || editDept == null}
                    loading={profileSaving}
                  >
                    Lưu thông tin
                  </Button>
                  {profileError && (
                    <span className="udlg__error" role="alert">
                      {profileError}
                    </span>
                  )}
                </div>
              )}
            </section>

            <div className="udlg__divider" />

            {/* Vai trò (PBI-2004). */}
            <section className="udlg__section">
              <p className="eyebrow">Vai trò (trong phòng)</p>
              <Select
                portal
                ariaLabel="Vai trò trong phòng"
                value={editRole}
                placeholder="— Chưa gán —"
                disabled={rolesLoading || deptId == null || !canAssignRole}
                onChange={(v) => {
                  setEditRole(v);
                  setRoleSaved(false);
                  if (roleError) setRoleError(null);
                }}
                options={[
                  { value: null, label: "— Chưa gán —" },
                  ...deptRoles.map((r) => ({ value: r.id, label: r.name })),
                ]}
              />
              {deptId != null && deptRoles.length === 0 && !rolesLoading && (
                <span className="udlg__hint">Phòng chưa có vai trò — tạo ở màn Phòng ban.</span>
              )}
              {canAssignRole && (
                <div className="udlg__row">
                  <Button
                    variant="accent"
                    onClick={() =>
                      setPending({
                        title: "Xác nhận đổi vai trò",
                        message:
                          "Bạn sắp thay đổi vai trò (quyền hạn) của người dùng này. " +
                          "Kiểm tra kỹ trước khi xác nhận.",
                        confirmLabel: "Lưu vai trò",
                        run: onSaveRole,
                      })
                    }
                    disabled={!roleDirty}
                    loading={roleSaving}
                  >
                    Lưu vai trò
                  </Button>
                  {roleSaved && !roleDirty && <span className="udlg__saved">Đã lưu</span>}
                  {roleError && (
                    <span className="udlg__error" role="alert">
                      {roleError}
                    </span>
                  )}
                </div>
              )}
            </section>

            <div className="udlg__divider" />

            {/* Thao tác bảo mật (PBI-2006 / PBI-2008). */}
            <section className="udlg__section">
              <p className="eyebrow">Bảo mật</p>
              {canReset || canRevoke || canLock || canDelete ? (
                <div className="udlg__row">
                  {canReset && (
                    <Button
                      variant="primary"
                      loading={resetBusy}
                      onClick={() =>
                        setPending({
                          title: "Đặt lại mật khẩu?",
                          message:
                            "Mật khẩu hiện tại của người dùng sẽ bị hủy và thay bằng mật khẩu " +
                            "tạm (hiển thị một lần). Mọi phiên đăng nhập của họ cũng bị thu hồi. " +
                            "Thao tác không thể hoàn tác.",
                          confirmLabel: "Đặt lại mật khẩu",
                          danger: true,
                          run: onResetPassword,
                        })
                      }
                    >
                      Đặt lại mật khẩu
                    </Button>
                  )}
                  {canRevoke && (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      disabled={revokeBusy || isSelf}
                      onClick={() =>
                        setPending({
                          title: "Thu hồi mọi phiên?",
                          message:
                            "Tất cả phiên đăng nhập của người dùng này sẽ bị đăng xuất ngay lập " +
                            "tức. Họ sẽ phải đăng nhập lại.",
                          confirmLabel: "Thu hồi mọi phiên",
                          danger: true,
                          run: onRevokeSessions,
                        })
                      }
                    >
                      Thu hồi mọi phiên
                    </button>
                  )}
                  {canLock && (
                    <button
                      type="button"
                      className={`btn ${user.is_active ? "btn--danger" : "btn--primary"}`}
                      disabled={activeBusy || isSelf}
                      onClick={() =>
                        setPending({
                          title: user.is_active ? "Khóa tài khoản?" : "Mở khóa tài khoản?",
                          message: user.is_active
                            ? "Người dùng sẽ bị đăng xuất và không thể đăng nhập cho tới khi được " +
                              "mở khóa lại."
                            : "Người dùng sẽ đăng nhập lại được sau khi mở khóa.",
                          confirmLabel: user.is_active ? "Khóa tài khoản" : "Mở khóa tài khoản",
                          danger: user.is_active,
                          run: onToggleActive,
                        })
                      }
                    >
                      {user.is_active ? "Khóa tài khoản" : "Mở khóa tài khoản"}
                    </button>
                  )}
                  {canDelete && (
                    <button
                      type="button"
                      className="btn btn--danger"
                      disabled={deleteBusy || isSelf}
                      onClick={() =>
                        setPending({
                          title: "Xóa người dùng?",
                          message:
                            "Tài khoản sẽ bị xóa (xóa mềm): ẩn khỏi danh sách, bị đăng xuất và " +
                            "không đăng nhập lại được. Dữ liệu/lịch sử vẫn được giữ lại. " +
                            "Liên hệ quản trị nếu cần khôi phục.",
                          confirmLabel: "Xóa người dùng",
                          danger: true,
                          run: onDeleteUser,
                        })
                      }
                    >
                      Xóa người dùng
                    </button>
                  )}
                </div>
              ) : (
                <span className="udlg__hint">Bạn chỉ có quyền xem tài khoản này.</span>
              )}
              {(canRevoke || canLock || canDelete) && isSelf && (
                <span className="udlg__hint">
                  Không thể tự khóa, thu hồi phiên hoặc xóa tài khoản chính mình.
                </span>
              )}
              {actionError && (
                <span className="udlg__error" role="alert">
                  {actionError}
                </span>
              )}
              {tempPassword && (
                <div className="udlg__temp" role="status">
                  <span className="udlg__temp-label">Mật khẩu tạm (hiển thị một lần):</span>
                  <code className="udlg__temp-value">{tempPassword}</code>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => navigator.clipboard?.writeText(tempPassword)}
                  >
                    Sao chép
                  </button>
                </div>
              )}
            </section>

            <div className="udlg__divider" />

            {/* Phiên đang hoạt động (PBI-2008). */}
            <section className="udlg__section">
              <p className="eyebrow">Phiên đang hoạt động</p>
              {sideLoading ? (
                <p className="udlg__muted">Đang tải…</p>
              ) : sessions.length === 0 ? (
                <p className="udlg__muted">Không có phiên nào đang hoạt động.</p>
              ) : (
                <ul className="udlg__list">
                  {sessions.map((s) => (
                    <li key={s.id} className="udlg__list-row">
                      <span className="udlg__list-main">{deviceLabel(s.user_agent)}</span>
                      <span className="udlg__list-meta">
                        Tạo {fmtDate(s.created_at)} · Hết hạn {fmtDate(s.expires_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="udlg__divider" />

            {/* Hoạt động gần đây (PBI-2008). */}
            <section className="udlg__section">
              <p className="eyebrow">Hoạt động gần đây</p>
              {sideLoading ? (
                <p className="udlg__muted">Đang tải…</p>
              ) : activity.length === 0 ? (
                <p className="udlg__muted">Chưa có hoạt động.</p>
              ) : (
                <ul className="udlg__list udlg__list--activity">
                  {activity.map((a) => (
                    <li key={a.id} className="udlg__list-row">
                      <span className="udlg__list-main">{a.action}</span>
                      <span className="udlg__list-meta">
                        {fmtDate(a.created_at)}
                        {a.detail ? ` · ${a.detail}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <div className="cdlg__foot">
            <button type="button" className="btn btn--ghost" onClick={attemptClose} disabled={busy}>
              Đóng
            </button>
          </div>
        </div>
      </div>

      <DiscardChangesDialog
        open={confirmDiscard}
        message="Bạn có thay đổi chưa lưu. Thoát mà không lưu?"
        onDiscard={() => {
          setConfirmDiscard(false);
          onClose();
        }}
        onKeepEditing={() => setConfirmDiscard(false)}
      />

      {/* Popup cảnh báo có đếm ngược 5s cho thao tác nhạy cảm. */}
      <ConfirmDialog
        open={pending != null}
        title={pending?.title ?? ""}
        message={pending?.message}
        confirmLabel={pending?.confirmLabel ?? "Xác nhận"}
        danger={pending?.danger}
        countdownSeconds={5}
        onConfirm={() => {
          const p = pending;
          setPending(null);
          p?.run();
        }}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
