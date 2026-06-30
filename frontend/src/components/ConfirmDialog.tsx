// Reusable confirmation popup (centered modal over a scrim). Used for actions that need
// an explicit yes/no — e.g. saving or deleting a department. Esc and scrim-click cancel
// (unless busy). Pass body content as children (e.g. a list of what will be deleted).
import { useEffect, type ReactNode } from "react";
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
  onConfirm,
  onCancel,
  children,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

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
          {danger ? (
            <button
              type="button"
              className="btn btn--danger"
              onClick={onConfirm}
              disabled={busy || confirmDisabled}
            >
              {busy ? "Đang xử lý…" : confirmLabel}
            </button>
          ) : (
            <Button
              type="button"
              variant="accent"
              onClick={onConfirm}
              loading={busy}
              disabled={confirmDisabled}
            >
              {confirmLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
