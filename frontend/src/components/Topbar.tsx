// Global top header bar (ERP shell). Light `--paper` surface that sits above the
// scrolling content on every page. Hosts the user widget on the right — avatar +
// name + a dropdown (Thông tin tài khoản · Đổi tên · Đổi avatar · Đổi mật khẩu +
// Đăng xuất). Replaces the per-page Log out button (moved here from the sidebar
// bottom — feat-018). Click outside closes the dropdown.
import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "./Icons";
import "./topbar.css";

interface TopbarProps {
  /** Open a profile panel by key (feat-019..022 wire these). */
  onProfileAction?: (action: "info" | "name" | "avatar" | "password") => void;
  /** Chuông: số đơn nghỉ của tôi vừa được quyết mà chưa xem. */
  leaveUnseen?: number;
  /** Bấm chuông → mở Nghỉ phép (Đơn của tôi) + đánh dấu đã xem. */
  onOpenLeave?: () => void;
}

export function Topbar({ onProfileAction, leaveUnseen = 0, onOpenLeave }: TopbarProps) {
  return (
    <header className="topbar">
      {onOpenLeave && (
        <button
          type="button"
          className="tb-bell"
          aria-label={leaveUnseen > 0 ? `${leaveUnseen} thông báo nghỉ phép mới` : "Thông báo"}
          title={leaveUnseen > 0 ? `${leaveUnseen} đơn nghỉ vừa được duyệt/từ chối` : "Thông báo"}
          onClick={onOpenLeave}
        >
          <Icon name="bell" size={18} />
          {leaveUnseen > 0 && <span className="tb-bell__badge">{leaveUnseen > 9 ? "9+" : leaveUnseen}</span>}
        </button>
      )}
      <UserWidget onProfileAction={onProfileAction} />
    </header>
  );
}

interface UserWidgetProps {
  onProfileAction?: (action: "info" | "name" | "avatar" | "password") => void;
}

function UserWidget({ onProfileAction }: UserWidgetProps) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click.
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (!user) return null;

  const display = user.name?.trim() || user.username;
  const avatarSrc = assetUrl(user.avatar_url);
  const initials = display
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  function handleAction(action: "info" | "name" | "avatar" | "password") {
    setOpen(false);
    onProfileAction?.(action);
  }

  return (
    <div className="tb-user" ref={wrapRef}>
      <button
        id="topbar-user-widget"
        type="button"
        className={`tb-user__trigger${open ? " is-open" : ""}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="Tùy chọn tài khoản"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="tb-user__avatar">
          {avatarSrc ? <img src={avatarSrc} alt="" /> : <span>{initials}</span>}
        </div>
        <div className="tb-user__trigger-text">
          <span className="tb-user__name">{display}</span>
          <span className="tb-user__sub">{user.username}</span>
        </div>
        <Icon name="chevron" size={14} className={`tb-user__caret${open ? " is-up" : ""}`} />
      </button>

      {open && (
        <div className="tb-user__dropdown" role="menu" aria-label="Tùy chọn tài khoản">
          <div className="tb-user__dropdown-header">
            <div className="tb-user__avatar tb-user__avatar--lg">
              {avatarSrc ? <img src={avatarSrc} alt="" /> : <span>{initials}</span>}
            </div>
            <div className="tb-user__info">
              <span className="tb-user__name">{display}</span>
              <span className="tb-user__sub">{user.username}</span>
            </div>
          </div>
          <div className="tb-user__divider" />
          <button
            id="profile-action-info"
            type="button"
            className="tb-user__item"
            role="menuitem"
            onClick={() => handleAction("info")}
          >
            <Icon name="users" size={15} />
            Thông tin tài khoản
          </button>
          <button
            id="profile-action-name"
            type="button"
            className="tb-user__item"
            role="menuitem"
            onClick={() => handleAction("name")}
          >
            <Icon name="fileText" size={15} />
            Đổi tên hiển thị
          </button>
          <button
            id="profile-action-avatar"
            type="button"
            className="tb-user__item"
            role="menuitem"
            onClick={() => handleAction("avatar")}
          >
            <Icon name="grid" size={15} />
            Đổi avatar
          </button>
          <button
            id="profile-action-password"
            type="button"
            className="tb-user__item"
            role="menuitem"
            onClick={() => handleAction("password")}
          >
            <Icon name="shield" size={15} />
            Đổi mật khẩu
          </button>
          <div className="tb-user__divider" />
          <button
            id="profile-action-logout"
            type="button"
            className="tb-user__item tb-user__item--danger"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            <Icon name="activity" size={15} />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
