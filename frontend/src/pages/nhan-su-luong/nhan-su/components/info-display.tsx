// Thẻ/ô hiển thị chỉ-đọc của màn Hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import type { ReactNode } from "react";

export function InfoCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: any;
  children: ReactNode;
}) {
  return (
    <div className="ns-info-card">
      <h4 className="ns-info-card__title">
        {Icon && <Icon size={14} />} {title}
      </h4>
      <div className="ns-info-grid">{children}</div>
    </div>
  );
}

export function InfoField({
  label,
  value,
  icon: Icon,
  hint,
}: {
  label: string;
  value: string | null | undefined;
  icon?: any;
  hint?: string;
}) {
  return (
    <div className="ns-info-field">
      {Icon && <Icon className="ns-info-field__icon" size={14} />}
      <div className="ns-info-field__content">
        <span className="ns-info-field__label">{label}</span>
        {value ? (
          <span className="ns-info-field__value">{value}</span>
        ) : (
          <span className="ns-info-field__value ns-info-field__value--empty">
            —
          </span>
        )}
        {hint && <span className="ns-info-field__hint">{hint}</span>}
      </div>
    </div>
  );
}
