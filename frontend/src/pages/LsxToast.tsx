// Toast cục bộ cho phân hệ Sản xuất (app CHƯA có toast provider chung — các màn khác dùng banner
// inline). Real-time gửi nội bộ do backend bắn SSE; ở Chunk 7 FE chỉ cần báo THÀNH CÔNG/LỖI tại chỗ
// sau thao tác (ghép · gán máy · duyệt mẫu · phát). Bám look app: canvas + hairline + rust/moss/signal.
import { useCallback, useRef, useState } from "react";

export type ToastKind = "ok" | "err";
export interface Toast {
  id: number;
  kind: ToastKind;
  msg: string;
}

export interface ToastApi {
  toasts: Toast[];
  ok: (msg: string) => void;
  err: (msg: string) => void;
  dismiss: (id: number) => void;
}

/** Hàng đợi toast tự huỷ (mặc định 4s). Trả API + danh sách để render qua <ToastStack>. */
export function useToasts(autoMs = 4000): ToastApi {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, msg: string) => {
      const id = ++seq.current;
      setToasts((list) => [...list, { id, kind, msg }]);
      if (autoMs > 0) window.setTimeout(() => dismiss(id), autoMs);
    },
    [autoMs, dismiss],
  );

  const ok = useCallback((msg: string) => push("ok", msg), [push]);
  const err = useCallback((msg: string) => push("err", msg), [push]);

  return { toasts, ok, err, dismiss };
}

export function ToastStack({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="lsx-toastwrap" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`lsx-toast lsx-toast--${t.kind}`}>
          <span className="lsx-toast__ic" aria-hidden="true">
            {t.kind === "ok" ? <CheckIcon /> : <AlertIcon />}
          </span>
          <span className="lsx-toast__msg">{t.msg}</span>
          <button
            type="button"
            className="lsx-toast__x"
            aria-label="Đóng thông báo"
            onClick={() => onDismiss(t.id)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
}

const CheckIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const AlertIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 8v5M12 16.5h.01" />
    <path d="M10.3 3.9 2.4 18a1.9 1.9 0 0 0 1.7 2.9h15.8a1.9 1.9 0 0 0 1.7-2.9L13.7 3.9a1.9 1.9 0 0 0-3.4 0Z" />
  </svg>
);
