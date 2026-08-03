import { useId, type InputHTMLAttributes, type ReactNode } from "react";
import { Icon, type IconName } from "./Icons";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  icon?: IconName;
  endAction?: ReactNode;
}

export function Field({ label, error, icon, endAction, id, ...rest }: FieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const errorId = `${inputId}-error`;

  return (
    <div className="field">
      <label className="field__label" htmlFor={inputId}>
        {label}
      </label>
      <div className={`field__input-wrap${icon ? " has-icon" : ""}${endAction ? " has-end-action" : ""}`}>
        {icon && (
          <span className="field__icon">
            <Icon name={icon} size={15} />
          </span>
        )}
        <input
          id={inputId}
          className={`input${error ? " input--error" : ""}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          {...rest}
        />
        {endAction && <div className="field__end-action">{endAction}</div>}
      </div>
      {error && (
        <span className="field__error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
