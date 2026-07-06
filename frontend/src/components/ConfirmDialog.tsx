// Reusable confirmation popup (centered modal over a scrim). Used for actions that need
// an explicit yes/no — e.g. saving or deleting a department. Esc and scrim-click cancel
// (unless busy). Pass body content as children (e.g. a list of what will be deleted).
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "./Button";
import "./confirm-dialog.css";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  wide?: boolean;
  busy?: boolean;
  error?: string | null;
  confirmDisabled?: boolean;
  /** Bắt chờ N giây trước khi cho bấm Xác nhận (thao tác nhạy cảm). Đếm ngược trên nút. */
  countdownSeconds?: number;
  /** Ẩn hẳn nút xác nhận — dùng khi dialog mở ở chế độ chỉ xem. */
  hideConfirm?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Xác nhận",
  cancelLabel = "Hủy",
  danger = false,
  wide = false,
  busy = false,
  error = null,
  confirmDisabled = false,
  countdownSeconds = 0,
  hideConfirm = false,
  onConfirm,
  onCancel,
  children,
}: ConfirmDialogProps) {
  // Đếm ngược: khi mở, khóa nút Xác nhận trong `countdownSeconds` giây (đọc kỹ cảnh báo).
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    if (!open || !countdownSeconds) {
      setRemaining(0);
      return;
    }
    setRemaining(countdownSeconds);
    const t = setInterval(() => {
      setRemaining((s) => {
        if (s <= 1) {
          clearInterval(t);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [open, countdownSeconds]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const counting = remaining > 0;
  const isConfirmDisabled = confirmDisabled || counting;
  const shownLabel = counting ? `${confirmLabel} (${remaining}s)` : confirmLabel;

  return (
    <div className="cdlg-overlay" onMouseDown={() => !busy && onCancel()}>
      <div
        className={`cdlg${wide ? " cdlg--wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="cdlg__head">
          <h2 className="cdlg__title">{title}</h2>
        </div>
        <div className="cdlg__body">
          {message && <p className="cdlg__msg">{message}</p>}
          {children}
          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}
        </div>
        <div className="cdlg__foot">
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          {hideConfirm ? null : danger ? (
            <button
              type="button"
              className="btn btn--danger"
              onClick={onConfirm}
              disabled={busy || isConfirmDisabled}
            >
              {busy ? "Đang xử lý…" : shownLabel}
            </button>
          ) : (
            <Button
              type="button"
              variant="accent"
              onClick={onConfirm}
              loading={busy}
              disabled={isConfirmDisabled}
            >
              {shownLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
