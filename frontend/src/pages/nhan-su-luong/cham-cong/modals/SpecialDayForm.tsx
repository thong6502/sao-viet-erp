// Form ngày đặc biệt (tách từ pages/ChamCongPage.tsx).
import { useState } from "react";
import {
  api,
  type SpecialDay,
  type SpecialDayInput,
} from "../../../../api/client";

export function SpecialDayForm({
  token,
  special,
  year,
  onClose,
  onSaved,
}: {
  token: string;
  special: SpecialDay | null;
  year: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<SpecialDayInput>({
    day: special?.day ?? `${year}-01-01`,
    kind: special?.kind ?? "off",
    name: special?.name ?? "",
    is_paid: special?.is_paid ?? true,
    note: special?.note ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof SpecialDayInput>(k: K, v: SpecialDayInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (special) await api.calendar.updateSpecialDay(token, special.id, form);
      else await api.calendar.createSpecialDay(token, form);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu.");
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{special ? "Sửa ngày đặc biệt" : "Thêm ngày đặc biệt"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field">
            <span className="ns-field__label">Ngày *</span>
            <input
              type="date"
              value={form.day}
              onChange={(e) => set("day", e.target.value)}
            />
          </label>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Tên *</span>
            <input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="vd Quốc khánh"
            />
          </label>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Loại</span>
            <select
              value={form.kind}
              onChange={(e) =>
                set("kind", e.target.value as "off" | "work" | "off1x")
              }
            >
              <option value="off">Nghỉ lễ (ngày lẽ ra làm nhưng nghỉ)</option>
              <option value="work">Làm bù (đi làm ngày lẽ ra nghỉ)</option>
              <option value="off1x">
                Nghỉ — đi làm chỉ lương chính (1×, không hệ số)
              </option>
            </select>
          </label>
          {form.kind === "off" && (
            <label className="ns-check" style={{ marginTop: 12 }}>
              <input
                type="checkbox"
                checked={!!form.is_paid}
                onChange={(e) => set("is_paid", e.target.checked)}
              />
              Hưởng nguyên lương (cộng 1 công vào bảng công)
            </label>
          )}
          {form.kind === "off1x" && (
            <p className="cc-note" style={{ marginTop: 10 }}>
              Ngày nghỉ <b>không lương</b>. Ai đi làm được{" "}
              <b>cộng thêm 1 công lương chính (1×)</b> — KHÔNG nhân hệ số
              lễ/nghỉ, không bị trần công tháng.
            </p>
          )}
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Ghi chú</span>
            <input
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
              placeholder="vd mùng 1 Tết Âm lịch"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || !form.name.trim() || !form.day}
          >
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
