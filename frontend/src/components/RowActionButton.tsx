// Nút thao tác trên MỘT dòng bảng. `dense` = chỉ icon + tooltip (CSS thuần, không
// JS); `!dense` = nút chữ thường. Tách từ PurchaseActionButton (cũ nằm trong
// PurchaseRequestsPage) vì cả Thu mua lẫn Kế toán đều cần — đặt ở components/ để
// không màn nào phải import ngược từ màn khác.
import { useId } from "react";
import { Button } from "./Button";
import { Icon, type IconName } from "./Icons";
import "./row-action-button.css";

interface RowActionButtonProps {
  /** true: chỉ hiện icon + tooltip; false: hiện nhãn chữ. */
  dense: boolean;
  /** Vừa là chữ (khi !dense) vừa là aria-label + nội dung tooltip (khi dense). */
  label: string;
  icon: IconName;
  variant?: "accent" | "ghost";
  loading?: boolean;
  danger?: boolean;
  /** Nút thấy được nhưng bấm không được. Tooltip vẫn hiện vì nó nằm ở `<span>` bọc ngoài —
   *  `:hover` trên chính nút disabled thì trình duyệt nuốt mất sự kiện. */
  disabled?: boolean;
  onClick: () => void;
}

export function RowActionButton({
  dense,
  label,
  icon,
  variant = "ghost",
  loading = false,
  danger = false,
  disabled = false,
  onClick,
}: RowActionButtonProps) {
  const tooltipId = useId();
  const className = [
    "md-page__rowbtn",
    dense ? "rowact__icon-btn" : "",
    danger ? "md-page__rowbtn--danger" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const button = (
    <Button
      type="button"
      variant={variant}
      className={className}
      loading={loading}
      disabled={disabled}
      aria-label={dense ? label : undefined}
      aria-describedby={dense ? tooltipId : undefined}
      onClick={onClick}
    >
      {dense ? <Icon name={icon} size={17} /> : label}
    </Button>
  );

  if (!dense) return button;

  return (
    <span className="rowact__tip">
      {button}
      <span id={tooltipId} className="rowact__tip-bubble" role="tooltip">
        {label}
      </span>
    </span>
  );
}
