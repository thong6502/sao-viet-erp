// Ô nhập số · hàng tham số · công tắc (tách từ pages/CauHinhLuongTab.tsx).

export function NumInput({
  value,
  onChange,
  suffix,
  step,
  min,
  max,
  disabled,
  placeholder,
  invalid,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  placeholder?: string;
  invalid?: boolean;
}) {
  return (
    <div
      className={`rc-input-wrapper${disabled ? " rc-input-wrapper--ro" : ""}`}
    >
      <input
        className={`rc-input rc-input--num${invalid ? " rc-input--invalid" : ""}`}
        type="number"
        inputMode="decimal"
        step={step ?? 1}
        min={min}
        max={max}
        disabled={disabled}
        placeholder={placeholder}
        value={value == null ? "" : value}
        onChange={(e) =>
          onChange(e.target.value === "" ? null : Number(e.target.value))
        }
      />
      {suffix && <span className="rc-input-suffix">{suffix}</span>}
    </div>
  );
}

/** Ô số bắt buộc có giá trị (tham số công ty) — rỗng quy về 0, không đẩy null xuống payload. */

export function ParamField({
  label,
  hint,
  warn,
  value,
  onChange,
  suffix,
  step,
  min,
  max,
  readOnly,
}: {
  label: string;
  hint?: string;
  warn?: string | null;
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
  readOnly?: boolean;
}) {
  return (
    <div className="rc-field">
      <span className="rc-field__label">{label}</span>
      <NumInput
        value={value}
        onChange={(v) => onChange(v ?? 0)}
        suffix={suffix}
        step={step}
        min={min}
        max={max}
        disabled={readOnly}
      />
      {warn ? (
        <span className="rc-field__hint cl-warn">{warn}</span>
      ) : hint ? (
        <span className="rc-field__hint">{hint}</span>
      ) : null}
    </div>
  );
}

export function Switch({
  on,
  onChange,
  disabled,
  label,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <label className="rc-switch">
      <input
        type="checkbox"
        checked={on}
        disabled={disabled}
        aria-label={label}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="rc-switch__slider" />
    </label>
  );
}

// --- Kiểu state cục bộ ------------------------------------------------------

/** Một bậc thuế trong state cục bộ — `id: null` = bậc mới, chưa POST. */
