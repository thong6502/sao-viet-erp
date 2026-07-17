// Toast dùng chung toàn app: gọi `toast("...")` từ bất kỳ đâu; <Toaster/> mount 1 lần ở AppShell.
// Hiện trên cùng màn hình, tự tắt sau ~4s. Không phụ thuộc prop drilling.
import { useEffect, useState } from "react";
import "./toast.css";

export type ToastKind = "success" | "info" | "error";
interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

type Listener = (t: ToastItem) => void;
const listeners = new Set<Listener>();
let seq = 1; // KHÔNG dùng Date.now/Math.random — counter đủ để phân biệt.

export function toast(message: string, kind: ToastKind = "success"): void {
  const item: ToastItem = { id: seq++, message, kind };
  listeners.forEach((l) => l(item));
}

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const l: Listener = (t) => {
      setItems((xs) => [...xs, t]);
      window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== t.id)), 4000);
    };
    listeners.add(l);
    return () => { listeners.delete(l); };
  }, []);

  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((t) => (
        <div
          key={t.id}
          className={`toast toast--${t.kind}`}
          onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}
          title="Bấm để ẩn"
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
