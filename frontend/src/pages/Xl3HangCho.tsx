// XẾP LỊCH 3 — CỘT HÀNG CHỜ (REDESIGN STUDIO DOCK)
import { CheckCircle2, ChevronLeft, Clock, Layers, Search, X } from "lucide-react";
import type { Xl3The } from "../api/client";
import { ngayNgan, thoiLuong } from "./xl3Shared";

export interface Xl3HangChoProps {
  the: Xl3The[];
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

export function Xl3HangCho({
  the, tong, tim, trang, moiTrang, dangTai, chonId, keoDuoc,
  isCollapsed, onToggleCollapse, onTim, onTrang, onChon, onKeo,
}: Xl3HangChoProps) {
  const soTrang = Math.max(1, Math.ceil(tong / moiTrang));

  if (isCollapsed) {
    return (
      <aside className="xl3-cho xl3-cho--collapsed">
        <button
          type="button"
          className="xl3-cho__btn-expand"
          onClick={onToggleCollapse}
          title="Mở rộng Hàng chờ"
        >
          <Layers size={15} />
          <span className="xl3-cho__badge-num">{tong}</span>
        </button>
      </aside>
    );
  }

  return (
    <aside className="xl3-cho">
      <header className="xl3-cho__dau">
        <div className="xl3-cho__tieu-cum">
          <h2>
            Hàng chờ <span className="xl3-cho__dem">{tong}</span>
          </h2>
          {onToggleCollapse && (
            <button
              type="button"
              className="xl3-cho__btn-collapse"
              onClick={onToggleCollapse}
              title="Thu gọn cột Hàng chờ"
            >
              <ChevronLeft size={14} />
            </button>
          )}
        </div>
        <div className="xl3-cho__tim-wrap">
          <Search size={14} className="xl3-cho__tim-icon" />
          <input
            className="xl3-cho__tim"
            value={tim}
            placeholder="Tìm mã / tên lệnh…"
            onChange={(e) => onTim(e.target.value)}
          />
          {tim && (
            <button
              type="button"
              className="xl3-cho__xoa"
              onClick={() => onTim("")}
              aria-label="Xóa tìm kiếm"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </header>

      <div className="xl3-cho__list">
        {dangTai && the.length === 0 && (
          <div className="xl3-cho__trong-box">
            <p>Đang tải dữ liệu hàng chờ…</p>
          </div>
        )}
        {!dangTai && the.length === 0 && (
          <div className="xl3-cho__trong-box">
            <CheckCircle2 size={24} className="xl3-cho__trong-icon" />
            <p>
              {tim ? "Không có lệnh nào khớp từ khóa." : "Tuyệt vời! Tất cả lệnh sẵn sàng đều đã được xếp lịch."}
            </p>
          </div>
        )}
        {the.map((t) => (
          <article
            key={t.lsx_id}
            className={`xl3-the${chonId === t.lsx_id ? " xl3-the--chon" : ""}`}
            draggable={keoDuoc}
            onDragStart={() => onKeo(t.lsx_id)}
            onDragEnd={() => onKeo(null)}
            onClick={() => onChon(t.lsx_id)}
          >
            <div className="xl3-the__dau">
              {t.is_rush && <span className="xl3-gap">GẤP</span>}
              <span className="xl3-the__ma">{t.ma}</span>
              <span className="xl3-the__han" title="Mục tiêu hoàn thành SX">
                <Clock size={11} />
                {ngayNgan(t.han_hoan_thanh_sx)}
              </span>
            </div>
            <div className="xl3-the__ten">{t.ten || "—"}</div>
            <div className="xl3-the__khach">{t.customer_name ?? "—"}</div>
            <div className="xl3-the__chips">
              <span className="xl3-the__chip">
                {t.so_luong_dat.toLocaleString("vi-VN")} {t.don_vi_tinh ?? "sp"}
              </span>
              <span className="xl3-the__chip">{thoiLuong(t.chay_phut)}</span>
              <span className="xl3-the__chip">{t.so_buoc} bước</span>
            </div>
          </article>
        ))}
      </div>

      {soTrang > 1 && (
        <footer className="xl3-cho__trang">
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

