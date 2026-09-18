// XẾP LỊCH 3 — CỘT HÀNG CHỜ (REDESIGN STUDIO DOCK)
import { CheckCircle2, ChevronLeft, Clock, Layers, Search, X } from "lucide-react";
import type { XlThe } from "../api/client";
import { gioChu, ngayNgan } from "./xlShared";

export interface XlHangChoProps {
  the: XlThe[];
  tong: number;
  tim: string;
  trang: number;
  moiTrang: number;
  dangTai: boolean;
  chonId: number | null;
  keoDuoc: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?(): void;
  onTim(v: string): void;
  onTrang(v: number): void;
  onChon(lsxId: number): void;
  onKeo(lsxId: number | null): void;
}

export function XlHangCho({
  the, tong, tim, trang, moiTrang, dangTai, chonId, keoDuoc,
  isCollapsed, onToggleCollapse, onTim, onTrang, onChon, onKeo,
}: XlHangChoProps) {
  const soTrang = Math.max(1, Math.ceil(tong / moiTrang));

  if (isCollapsed) {
    return (
      <aside className="xl-cho xl-cho--collapsed">
        <button
          type="button"
          className="xl-cho__btn-expand"
          onClick={onToggleCollapse}
          title="Mở rộng Hàng chờ"
        >
          <Layers size={15} />
          <span className="xl-cho__badge-num">{tong}</span>
        </button>
      </aside>
    );
  }

  return (
    <aside className="xl-cho">
      <header className="xl-cho__dau">
        <div className="xl-cho__tieu-cum">
          <h2>
            Hàng chờ <span className="xl-cho__dem">{tong}</span>
          </h2>
          {onToggleCollapse && (
            <button
              type="button"
              className="xl-cho__btn-collapse"
              onClick={onToggleCollapse}
              title="Thu gọn cột Hàng chờ"
            >
              <ChevronLeft size={14} />
            </button>
          )}
        </div>
        <div className="xl-cho__tim-wrap">
          <Search size={14} className="xl-cho__tim-icon" />
          <input
            className="xl-cho__tim"
            value={tim}
            placeholder="Tìm mã / tên lệnh…"
            onChange={(e) => onTim(e.target.value)}
          />
          {tim && (
            <button
              type="button"
              className="xl-cho__xoa"
              onClick={() => onTim("")}
              aria-label="Xóa tìm kiếm"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </header>

      <div className="xl-cho__list">
        {dangTai && the.length === 0 && (
          <div className="xl-cho__trong-box">
            <p>Đang tải dữ liệu hàng chờ…</p>
          </div>
        )}
        {!dangTai && the.length === 0 && (
          <div className="xl-cho__trong-box">
            <CheckCircle2 size={24} className="xl-cho__trong-icon" />
            <p>
              {tim ? "Không có lệnh nào khớp từ khóa." : "Tuyệt vời! Tất cả lệnh sẵn sàng đều đã được xếp lịch."}
            </p>
          </div>
        )}
        {the.map((t) => (
          <article
            key={t.lsx_id}
            className={`xl-the${chonId === t.lsx_id ? " xl-the--chon" : ""}`}
            draggable={keoDuoc}
            onDragStart={() => onKeo(t.lsx_id)}
            onDragEnd={() => onKeo(null)}
            onClick={() => onChon(t.lsx_id)}
          >
            <div className="xl-the__dau">
              {t.is_rush && <span className="xl-gap">GẤP</span>}
              <span className="xl-the__ma">{t.ma}</span>
              <span className="xl-the__han" title="Mục tiêu hoàn thành SX">
                <Clock size={11} />
                {ngayNgan(t.han_hoan_thanh_sx)}
              </span>
            </div>
            <div className="xl-the__ten">{t.ten || "—"}</div>
            <div className="xl-the__khach">{t.customer_name ?? "—"}</div>
            <div className="xl-the__chips">
              <span className="xl-the__chip">
                {t.so_luong_dat.toLocaleString("vi-VN")} {t.don_vi_tinh ?? "sp"}
              </span>
              <span className="xl-the__chip">{t.chay_phut > 0 ? gioChu(t.chay_phut) : "—"}</span>
              <span className="xl-the__chip">{t.so_buoc} bước</span>
            </div>
          </article>
        ))}
      </div>

      {soTrang > 1 && (
        <footer className="xl-cho__trang">
          <button type="button" disabled={trang <= 1} onClick={() => onTrang(trang - 1)} aria-label="Trang trước">
            ‹
          </button>
          <span>
            {trang}/{soTrang}
          </span>
          <button type="button" disabled={trang >= soTrang} onClick={() => onTrang(trang + 1)} aria-label="Trang sau">
            ›
          </button>
        </footer>
      )}
    </aside>
  );
}

