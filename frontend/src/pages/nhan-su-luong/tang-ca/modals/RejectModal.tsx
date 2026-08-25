// Modal từ chối phiếu tăng ca — bắt buộc ghi lý do (tách từ pages/TangCaPage.tsx).
import { useState } from "react";

// --- Modal từ chối (bắt buộc ghi lý do) --------------------------------------

export function RejectModal({
  count,
  onClose,
  onConfirm,
}: {
  count: number;
  onClose: () => void;
  onConfirm: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Từ chối {count > 1 ? `${count} phiếu` : "phiếu tăng ca"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          <label className="ns-field">
            <span className="ns-field__label">Lý do từ chối *</span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="vd: hôm nay không cần tăng ca"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            disabled={!note.trim()}
            onClick={() => onConfirm(note.trim())}
          >
            Từ chối
          </button>
        </footer>
      </div>
    </div>
  );
}
