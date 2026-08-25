// Form khai ca (tách từ pages/ChamCongPage.tsx).
import { useState } from "react";
import {
  api,
  type WorkShift,
  type WorkShiftInput,
} from "../../../../api/client";
import { ChevronDown } from "lucide-react";
import { TIME_HOURS, TIME_MINUTES } from "../shared/constants";
import { normalizeTime24 } from "../shared/helpers";

export function ShiftForm({
  token,
  shift,
  onClose,
  onSaved,
}: {
  token: string;
  shift: WorkShift | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkShiftInput>({
    name: shift?.name ?? "",
    start_time: shift?.start_time ?? "08:00",
    end_time: shift?.end_time ?? "17:00",
    is_overnight: shift?.is_overnight ?? false,
    night_multiplier: shift?.night_multiplier ?? 1.3,
    grace_minutes: shift?.grace_minutes ?? 5,
    meal_allowance: shift?.meal_allowance ?? 25000,
    shift_allowance: shift?.shift_allowance ?? 50000,
    note: shift?.note ?? "",
    is_active: shift?.is_active ?? true,
    ca_san_xuat: shift?.ca_san_xuat ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof WorkShiftInput>(k: K, v: WorkShiftInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  function timeParts(field: "start_time" | "end_time") {
    return (normalizeTime24(form[field]) ?? "00:00").split(":");
  }
  function setTimePart(
    field: "start_time" | "end_time",
    part: "hour" | "minute",
    value: string,
  ) {
    const [hour, minute] = timeParts(field);
    set(field, part === "hour" ? `${value}:${minute}` : `${hour}:${value}`);
  }
  async function save() {
    setBusy(true);
    setError(null);
    const startTime = normalizeTime24(form.start_time);
    const endTime = normalizeTime24(form.end_time);
    if (!startTime || !endTime) {
      setError("Giờ ca không hợp lệ. Vui lòng chọn lại giờ và phút.");
      setBusy(false);
      return;
    }
    const payload = { ...form, start_time: startTime, end_time: endTime };
    setForm(payload);
    try {
      if (shift) await api.attendance.updateShift(token, shift.id, payload);
      else await api.attendance.createShift(token, payload);
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
          <h2>{shift ? "Sửa ca làm việc" : "Thêm ca làm việc"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          <label className="ns-field">
            <span className="ns-field__label">Tên ca *</span>
            <input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="Hành chính / Ca 1…"
            />
          </label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Giờ vào ca (24 giờ)</span>
              <span className="cc-time-selects">
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Giờ</span>
                  <select
                    aria-label="Giờ vào ca"
                    value={timeParts("start_time")[0]}
                    onChange={(e) =>
                      setTimePart("start_time", "hour", e.target.value)
                    }
                  >
                    {TIME_HOURS.map((hour) => (
                      <option key={hour} value={hour}>
                        {hour}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
                <strong className="cc-time-selects__separator">:</strong>
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Phút</span>
                  <select
                    aria-label="Phút vào ca"
                    value={timeParts("start_time")[1]}
                    onChange={(e) =>
                      setTimePart("start_time", "minute", e.target.value)
                    }
                  >
                    {TIME_MINUTES.map((minute) => (
                      <option key={minute} value={minute}>
                        {minute}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Giờ ra ca (24 giờ)</span>
              <span className="cc-time-selects">
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Giờ</span>
                  <select
                    aria-label="Giờ ra ca"
                    value={timeParts("end_time")[0]}
                    onChange={(e) =>
                      setTimePart("end_time", "hour", e.target.value)
                    }
                  >
                    {TIME_HOURS.map((hour) => (
                      <option key={hour} value={hour}>
                        {hour}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
                <strong className="cc-time-selects__separator">:</strong>
                <span className="cc-time-select">
                  <span className="cc-time-select__caption">Phút</span>
                  <select
                    aria-label="Phút ra ca"
                    value={timeParts("end_time")[1]}
                    onChange={(e) =>
                      setTimePart("end_time", "minute", e.target.value)
                    }
                  >
                    {TIME_MINUTES.map((minute) => (
                      <option key={minute} value={minute}>
                        {minute}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="cc-time-select__chevron" size={15} />
                </span>
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Dung sai đi muộn (phút)</span>
              <input
                type="number"
                min={0}
                value={form.grace_minutes}
                onChange={(e) => set("grace_minutes", Number(e.target.value))}
              />
            </label>
          </div>
          <p className="cc-note" style={{ marginTop: 8 }}>
            Chọn theo giờ 24 giờ: <strong>00:00 là nửa đêm</strong>, còn{" "}
            <strong>12:00 là buổi trưa</strong>.
          </p>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Phụ cấp cơm (đ)</span>
              <input
                type="number"
                min={0}
                step={5000}
                value={form.meal_allowance ?? 0}
                onChange={(e) => set("meal_allowance", Number(e.target.value))}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Phụ cấp ca (đ)</span>
              <input
                type="number"
                min={0}
                step={5000}
                value={form.shift_allowance ?? 0}
                onChange={(e) => set("shift_allowance", Number(e.target.value))}
              />
            </label>
          </div>
          <p className="cc-note" style={{ marginTop: 8 }}>
            Phụ cấp gắn theo ca: nhân viên được gán ca này sẽ tự cộng khi tính
            lương.
          </p>
          <label className="ns-check" style={{ marginTop: 12 }}>
            <input
              type="checkbox"
              checked={!!form.is_overnight}
              onChange={(e) => set("is_overnight", e.target.checked)}
            />
            Ca qua đêm (ra hôm sau, vd 22:00→06:00)
          </label>
          {form.is_overnight && (
            <label className="ns-field" style={{ marginTop: 10 }}>
              <span className="ns-field__label">
                Hệ số ca đêm (vd 1.3 = +30%)
              </span>
              <input
                type="number"
                min={1}
                step={0.05}
                value={form.night_multiplier ?? 1.3}
                onChange={(e) =>
                  set("night_multiplier", Number(e.target.value))
                }
              />
              <span className="cc-note" style={{ marginTop: 4 }}>
                Cộng thêm cho GIỜ rơi 22h–06h trong ca (theo luật ≥ 1.3 = +30%).
                Tăng ca đêm tính riêng theo Cấu hình lương.
              </span>
            </label>
          )}
          <label className="ns-check" style={{ marginTop: 10 }}>
            <input
              type="checkbox"
              checked={!!form.ca_san_xuat}
              onChange={(e) => set("ca_san_xuat", e.target.checked)}
            />{" "}
            Ca chạy dưới xưởng sản xuất
          </label>
          <p className="cc-note" style={{ marginTop: 4 }}>
            Bật cho ca có người đứng máy. Bàn Xếp lịch lấy đúng các ca này làm
            giờ làm của xưởng: khung giờ được phép đặt việc, và mẫu số tính %
            tải máy. Ca văn phòng (vd Hành chính 08:00–17:00) thì tắt — vẫn chấm
            công bình thường, chỉ thôi tính vào lịch xưởng.
          </p>
          <label className="ns-check">
            <input
              type="checkbox"
              checked={!!form.is_active}
              onChange={(e) => set("is_active", e.target.checked)}
            />{" "}
            Đang dùng
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
