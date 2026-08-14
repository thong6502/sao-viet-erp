// Global top header bar (ERP shell). Light `--paper` surface that sits above the
// scrolling content on every page. Hosts the notification bell (dropdown center) +
// the user widget on the right — avatar + name + a dropdown (Hồ sơ của tôi + Đăng xuất).
import { useEffect, useRef, useState } from "react";
import { assetUrl, type AppNotification } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Icon } from "./Icons";
import "./topbar.css";

interface TopbarProps {
  /** Mở trang "Hồ sơ của tôi" (nhà chung self-service tài khoản). */
  onOpenProfile?: () => void;
  /** Chuông: số đơn nghỉ của tôi vừa được quyết mà chưa xem (lối tắt sang Nghỉ phép). */
  leaveUnseen?: number;
  /** Bấm lối tắt nghỉ phép → mở Nghỉ phép (Đơn của tôi) + đánh dấu đã xem. */
  onOpenLeave?: () => void;
  /** Danh sách thông báo (mới nhất trước) + số chưa đọc — nuôi chuông. */
  notifs?: AppNotification[];
  notifUnread?: number;
  /** Bấm 1 thông báo → điều hướng tới phiếu/yêu cầu + đánh dấu đã đọc. */
  onOpenNotif?: (n: AppNotification) => void;
  /** Đánh dấu đã đọc hết. */
  onMarkAllRead?: () => void;
}

export function Topbar({
  onOpenProfile,
  leaveUnseen = 0,
  onOpenLeave,
  notifs = [],
  notifUnread = 0,
  onOpenNotif,
  onMarkAllRead,
}: TopbarProps) {
  return (
    <header className="topbar">
      <NotificationBell
        leaveUnseen={leaveUnseen}
        onOpenLeave={onOpenLeave}
        notifs={notifs}
        notifUnread={notifUnread}
        onOpenNotif={onOpenNotif}
        onMarkAllRead={onMarkAllRead}
      />
      <UserWidget onOpenProfile={onOpenProfile} />
    </header>
  );
}

/** Backend lưu UTC nhưng serialize KHÔNG kèm offset (naive) → thêm 'Z' để `new Date` hiểu là UTC,
 *  không thì trình duyệt coi là giờ máy (VN = UTC+7) → lệch 7 giờ ("vừa gửi" hoá "7 giờ trước"). */
function parseUTC(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

/** Thời gian tương đối gọn (vd "5 phút trước", "3 giờ trước", "Hôm qua"). */
function timeAgo(iso: string): string {
  const then = parseUTC(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return "Vừa xong";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} phút trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} giờ trước`;
  const d = Math.floor(h / 24);
  if (d === 1) return "Hôm qua";
  if (d < 7) return `${d} ngày trước`;
  return parseUTC(iso).toLocaleDateString("vi-VN");
}

interface BellProps {
  leaveUnseen: number;
  onOpenLeave?: () => void;
  notifs: AppNotification[];
  notifUnread: number;
  onOpenNotif?: (n: AppNotification) => void;
  onMarkAllRead?: () => void;
}

function NotificationBell({
  leaveUnseen,
  onOpenLeave,
  notifs,
  notifUnread,
  onOpenNotif,
  onMarkAllRead,
}: BellProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const total = notifUnread + leaveUnseen;
  const empty = notifs.length === 0 && leaveUnseen === 0;

  return (
    <div className="tb-bell-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`tb-bell${open ? " is-open" : ""}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={total > 0 ? `${total} thông báo mới` : "Thông báo"}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" size={18} />
        {total > 0 && <span className="tb-bell__badge">{total > 9 ? "9+" : total}</span>}
      </button>

      {open && (
        <div className="tb-notif" role="menu" aria-label="Thông báo">
          <div className="tb-notif__head">
            <span className="tb-notif__title">Thông báo</span>
            {notifUnread > 0 && (
              <button
                type="button"
                className="tb-notif__markall"
                onClick={() => onMarkAllRead?.()}
              >
                Đánh dấu đã đọc
              </button>
            )}
          </div>

          <div className="tb-notif__list">
            {/* Lối tắt Nghỉ phép — giữ cơ chế cũ, gộp vào chuông cho một cửa. */}
            {leaveUnseen > 0 && onOpenLeave && (
              <button
                type="button"
                className="tb-notif__item tb-notif__item--unread"
                onClick={() => {
                  setOpen(false);
                  onOpenLeave();
                }}
              >
                <span className="tb-notif__dot" aria-hidden="true" />
                <span className="tb-notif__body">
                  <span className="tb-notif__t">Đơn nghỉ phép của bạn vừa được quyết</span>
                  <span className="tb-notif__s">
                    {leaveUnseen} đơn mới · bấm để xem
                  </span>
                </span>
              </button>
            )}

            {notifs.map((n) => (
              <button
                key={n.id}
                type="button"
                className={`tb-notif__item${n.da_doc ? "" : " tb-notif__item--unread"}`}
                onClick={() => {
                  setOpen(false);
                  onOpenNotif?.(n);
                }}
              >
                {!n.da_doc && <span className="tb-notif__dot" aria-hidden="true" />}
                <span className="tb-notif__body">
                  <span className="tb-notif__t">{n.tieu_de}</span>
                  {n.noi_dung && <span className="tb-notif__s">{n.noi_dung}</span>}
                  <span className="tb-notif__time">{timeAgo(n.created_at)}</span>
                </span>
              </button>
            ))}

            {empty && <div className="tb-notif__empty">Chưa có thông báo nào.</div>}
          </div>
        </div>
      )}
    </div>
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
