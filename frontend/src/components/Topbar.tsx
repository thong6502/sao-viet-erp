// Global top header bar (ERP shell). Light `--paper` surface that sits above the
// scrolling content on every page. Hosts the user widget on the right — avatar +
// name + a dropdown (Hồ sơ của tôi + Đăng xuất).
import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "./Icons";
import "./topbar.css";

interface TopbarProps {
  /** Mở trang "Hồ sơ của tôi" (nhà chung self-service tài khoản). */
  onOpenProfile?: () => void;
  /** Mở/đóng ngăn kéo điều hướng (chỉ hiện ở màn hẹp — xem `.topbar__nav-toggle`). */
  onToggleNav?: () => void;
  /** Ngăn kéo điều hướng đang mở? — nuôi `aria-expanded` của nút hamburger. */
  navOpen?: boolean;
}

export function Topbar({ onOpenProfile, onToggleNav, navOpen = false }: TopbarProps) {
  return (
    <header className="topbar">
      {/* Hamburger: CSS ẩn ở màn rộng (sidebar cố định), hiện khi sidebar hoá ngăn kéo. */}
      <button
        type="button"
        className="topbar__nav-toggle"
        onClick={onToggleNav}
        aria-label={navOpen ? "Đóng menu điều hướng" : "Mở menu điều hướng"}
        aria-expanded={navOpen}
      >
        <Icon name={navOpen ? "x" : "menu"} size={20} />
      </button>
      <div className="topbar__spacer" />
      <UserWidget onOpenProfile={onOpenProfile} />
    </header>
  );
}

interface UserWidgetProps {
  onOpenProfile?: () => void;
}

function UserWidget({ onOpenProfile }: UserWidgetProps) {
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

  function openProfile() {
    setOpen(false);
    onOpenProfile?.();
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
            id="profile-action-open"
            type="button"
            className="tb-user__item"
            role="menuitem"
            onClick={openProfile}
          >
            <Icon name="users" size={15} />
            Hồ sơ của tôi
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
