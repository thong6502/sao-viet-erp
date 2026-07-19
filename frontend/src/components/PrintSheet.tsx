// Khuôn phiếu in dùng chung — header (logo · tiêu đề · số/ngày) + overlay preview + nút In.
// Nội dung phiếu (bảng, tổng, chữ ký…) truyền vào qua children. Bám phong cách bản in Báo giá đã duyệt.
import type { ReactNode } from "react";
import svnLogoUrl from "../assets/sao-viet-nhat-logo-mark.png";
import { COMPANY } from "../constants/company";
import "./print-sheet.css";

export function PrintSheet({
  title,
  docNo,
  docDate,
  canPrint,
  onClose,
  children,
  footer,
}: {
  title: string;
  docNo?: string;
  docDate?: string;
  canPrint?: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="ps-ov" onClick={onClose}>
      <div className="ps-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="ps-dialog-head">
          <h2>Xem trước bản in</h2>
          <button onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>
        <div className="psheet">
          <header className="ps-mh">
            <div className="ps-logo">
              <img src={svnLogoUrl} alt="SVN" />
            </div>
            <div className="ps-th">
              <h1>{title}</h1>
              <div className="ps-cty">{COMPANY.name}</div>
              <div className="ps-cty">{COMPANY.address}</div>
            </div>
            <div className="ps-meta">
              {docNo && (
                <div>
                  Số: <b>{docNo}</b>
                </div>
              )}
              {docDate && (
                <div>
                  Ngày: <b>{docDate}</b>
                </div>
              )}
            </div>
          </header>
          {children}
          {footer ?? (
            <div className="ps-foot">
              <span>{COMPANY.name}</span>
              <span>In lúc {new Date().toLocaleString("vi-VN")}</span>
            </div>
          )}
        </div>
        <div className="ps-dialog-actions">
          <button className="btn btn--secondary" onClick={onClose}>
            Đóng
          </button>
          {(canPrint ?? true) && (
            <button className="btn btn--primary" onClick={() => window.print()}>
              In / Lưu PDF
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
