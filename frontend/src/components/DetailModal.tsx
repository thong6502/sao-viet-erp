// Popup xem CHI TIẾT một bản ghi (phiếu chi/thu, PMH…) — thay cho kiểu panel chi tiết
// nằm bên cạnh danh sách. Bấm 1 dòng trong bảng → mở popup này; bảng được full chiều
// ngang (hợp laptop). Esc / bấm ra ngoài / nút × đều đóng.
//
// Đây là popup CHỈ-XEM: các nút thao tác đặt ở `footer`, và nơi gọi phải ĐÓNG popup
// trước khi mở form lập/sửa để không chồng hai lớp cửa sổ.
import { useEffect, type ReactNode } from "react";
import "./detail-modal.css";

interface DetailModalProps {
  /** Nhãn nhỏ phía trên tiêu đề, vd "Phiếu chi". */
  kicker?: string;
  /** Tiêu đề chính — thường là mã chứng từ. */
  title: string;
  /** Dòng phụ dưới tiêu đề, vd "Số phiếu: PC00015". */
  subtitle?: ReactNode;
  /** Góc phải đầu popup — badge trạng thái (và badge cảnh báo nếu có). */
  badge?: ReactNode;
  /** Hàng nút thao tác dưới đáy. */
  footer?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

export function DetailModal({
  kicker,
  title,
  subtitle,
  badge,
  footer,
  onClose,
  children,
}: DetailModalProps) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="dmodal-overlay" onMouseDown={onClose}>
      <div
        className="dmodal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="dmodal__head">
          <div className="dmodal__heading">
            {kicker && <p className="eyebrow">{kicker}</p>}
            <h2 className="dmodal__title">{title}</h2>
            {subtitle && <div className="dmodal__subtitle">{subtitle}</div>}
          </div>
          <div className="dmodal__head-right">
            <button
              type="button"
              className="dmodal__x"
              onClick={onClose}
              aria-label="Đóng"
            >
              ×
            </button>
            {badge}
          </div>
        </header>
        <div className="dmodal__body">{children}</div>
        {footer && <footer className="dmodal__foot">{footer}</footer>}
      </div>
    </div>
  );
}
