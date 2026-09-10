// XẾP LỊCH 3 — cột HÀNG CHỜ: lệnh đủ điều kiện xếp mà chưa có giờ bắt đầu.
//
// Mỗi thẻ mang đúng những số cần để QUYẾT xếp lệnh nào trước: khách, hạn SX, sản lượng, và thời
// gian chạy ước tính (tổng giờ máy của cả routing). KHÔNG bày trạng thái vật tư ở đây — màn này
// không chặn theo vật tư, bày lên chỉ mời người ta tự chặn mình.
//
// Thẻ KÉO ĐƯỢC sang lưới. Đó là đường đặt lịch lần đầu; bấm thẻ chỉ mở panel để xem trước.
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
  onTim(v: string): void;
  onTrang(v: number): void;
  onChon(lsxId: number): void;
  onKeo(lsxId: number | null): void;
}

export function Xl3HangCho({
  the, tong, tim, trang, moiTrang, dangTai, chonId, keoDuoc,
  onTim, onTrang, onChon, onKeo,
}: Xl3HangChoProps) {
  const soTrang = Math.max(1, Math.ceil(tong / moiTrang));
  return (
    <aside className="xl3-cho">
      <header className="xl3-cho__dau">
        <h2>
          Hàng chờ <span className="xl3-cho__dem">{tong}</span>
        </h2>
        <input
          className="xl3-cho__tim"
          value={tim}
          placeholder="Tìm mã / tên lệnh…"
          onChange={(e) => onTim(e.target.value)}
        />
      </header>

      <div className="xl3-cho__list">
        {dangTai && the.length === 0 && <p className="xl3-cho__trong">Đang tải…</p>}
        {!dangTai && the.length === 0 && (
          <p className="xl3-cho__trong">
            {tim ? "Không có lệnh nào khớp." : "Hết việc chờ xếp — mọi lệnh sẵn sàng đều đã có giờ."}
          </p>
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
              <strong>{t.ma}</strong>
              <span className="xl3-the__han">{ngayNgan(t.han_hoan_thanh_sx)}</span>
            </div>
            <div className="xl3-the__ten">{t.ten || "—"}</div>
            <div className="xl3-the__khach">{t.customer_name ?? "—"}</div>
            <dl className="xl3-the__so">
              <div>
                <dt>Sản lượng</dt>
                <dd>
                  {t.so_luong_dat.toLocaleString("vi-VN")} {t.don_vi_tinh ?? ""}
                </dd>
              </div>
              <div>
                <dt>Tờ kế hoạch</dt>
                <dd>{t.so_to_ke_hoach.toLocaleString("vi-VN")}</dd>
              </div>
              <div>
                <dt>Chạy ước tính</dt>
                <dd>{thoiLuong(t.chay_phut)}</dd>
              </div>
              <div>
                <dt>Số bước</dt>
                <dd>{t.so_buoc}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>

      {soTrang > 1 && (
        <footer className="xl3-cho__trang">
          <button type="button" disabled={trang <= 1} onClick={() => onTrang(trang - 1)}>
            ‹
          </button>
          <span>
            {trang}/{soTrang}
          </span>
          <button type="button" disabled={trang >= soTrang} onClick={() => onTrang(trang + 1)}>
            ›
          </button>
        </footer>
      )}
    </aside>
  );
}
