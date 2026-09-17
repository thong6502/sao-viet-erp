// Ngăn kéo BÁO SỰ CỐ của bàn tổ (§7.2 mở rộng 31/08/2026).
//
// Cùng KHUÔN với ngăn kéo "Báo máy hỏng · Yêu cầu mới" của màn Sửa chữa máy (`SuaChuaMayPage`):
// lời báo nào cũng rơi vào chung một hộp thư của tổ sửa chữa, nên người báo ở bàn tổ hay ở màn Sửa
// chữa máy phải gặp đúng một kiểu ô. Khác duy nhất: ô Máy KHOÁ — server tự lấy máy của công việc
// đang chạy (`SuCoIn` không nhận `may_id`), và ô tick "máy đang dừng" ở đây còn tạm dừng công việc.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { SxSuCoIn } from "../api/client";
import { NHAN_MUC_DO } from "../api/kyThuatMay";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import "./rebuild-catalog.css";
import "./ky-thuat-may.css";

// Mức độ: đọc thẳng `NHAN_MUC_DO` của module Sửa chữa máy, không khai lại chuỗi ở màn này.
const MUC_DO_OPTS = Object.entries(NHAN_MUC_DO);
const MUC_DO_MAC_DINH =
  "trung_binh" in NHAN_MUC_DO ? "trung_binh" : (MUC_DO_OPTS[0]?.[0] ?? "trung_binh");

export function ThsxBaoSuCoDialog({ mayNhan, dangChay, busy, onGui, onClose }: {
  /** Nhãn máy của công việc (chỉ để đọc). */
  mayNhan: string;
  /** Công việc đang CHẠY (không phải tạm dừng) — tick "máy dừng" mới đóng phiên máy. */
  dangChay: boolean;
  busy: boolean;
  /** Trả `true` khi gửi thành công ⇒ đóng ngăn kéo; lỗi thì controller đã toast, giữ nguyên ô đã gõ. */
  onGui: (body: SxSuCoIn) => Promise<boolean>;
  onClose: () => void;
}) {
  const [boPhan, setBoPhan] = useState("");
  const [moTa, setMoTa] = useState("");
  const [mucDo, setMucDo] = useState(MUC_DO_MAC_DINH);
  const [mayDung, setMayDung] = useState(false);
  const [thuGui, setThuGui] = useState(false);
  const nganKeoRef = useRef<HTMLElement>(null);
  const nhanTrenNen = useRef(false);
  useEffect(() => { nganKeoRef.current?.focus({ preventScroll: true }); }, []);

  const thieuBoPhan = !boPhan.trim();
  // Service là trọng tài (`mo_ta` bắt buộc khi dừng sản xuất) — chặn sẵn ở đây để khỏi đi một vòng 422.
  const thieuMoTa = mayDung && !moTa.trim();

  const gui = async () => {
    setThuGui(true);
    if (busy || thieuBoPhan || thieuMoTa) return;
    const ok = await onGui({
      bo_phan_hong: boPhan.trim(),
      mo_ta: moTa.trim() || null,
      muc_do: mucDo,
      dung_san_xuat: mayDung,
    });
    if (ok) onClose();
  };

  // PORTAL ra `body` vì `.thsx-panel--open` có `transform` — render tại chỗ thì ngăn kéo bị nhốt
  // trong khung drawer bàn tổ. `zIndex` inline: `.rc-drawer__scrim` khai 60, thấp hơn drawer bàn tổ.
  return createPortal(
    <div className="rc-drawer__scrim" style={{ zIndex: 70 }}
      // Chỉ đóng khi nhấn VÀ thả đều trên nền: bôi chữ trong ô rồi thả lệch ra ngoài không được vứt
      // mất lời báo. `stopPropagation` vì sự kiện React đi xuyên portal, nổi về cây bàn tổ.
      onMouseDown={(e) => { nhanTrenNen.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        e.stopPropagation();
        if (nhanTrenNen.current && e.target === e.currentTarget && !busy) onClose();
      }}>
      <aside ref={nganKeoRef} className="rc-drawer ktm-drawer" role="dialog" aria-modal="true"
        aria-label="Báo máy hỏng — Yêu cầu mới" tabIndex={-1}
        // Esc nuốt tại đây: trang nghe Esc ở `document` để đóng cả drawer bàn tổ.
        onKeyDown={(e) => {
          if (e.key !== "Escape" || e.defaultPrevented) return;
          e.preventDefault();
          if (!busy) onClose();
        }}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">Báo máy hỏng</div>
            <h2 className="rc-drawer__title">Yêu cầu mới</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} disabled={busy} aria-label="Đóng">
            <Icon name="x" size={14} />
          </button>
        </header>

        <form className="ktm-drawer__form" onSubmit={(e) => { e.preventDefault(); void gui(); }}>
          <div className="rc-drawer__body">
            <div className="ktm-form-card">
              <div className="ktm-form-card__head">
                <div className="ktm-form-card__icon">
                  <Icon name="alert" size={15} />
                </div>
                <h3 className="ktm-form-card__title">Thông tin báo sự cố máy</h3>
              </div>

              {/* Thẻ cảnh báo Máy Đang Dừng (Emergency Stop Alert Card) */}
              <label className={`ktm-emergency-card${mayDung ? " is-active" : ""}`}>
                <input type="checkbox" className="ktm-emergency-card__checkbox" checked={mayDung} disabled={busy}
                  onChange={(e) => setMayDung(e.target.checked)} />
                <div className="ktm-emergency-card__body">
                  <div className="ktm-emergency-card__title">
                    <span>Máy đang dừng, không chạy được</span>
                    {mayDung && <span className="ktm-emergency-card__badge">🛑 Ưu tiên cao & Tạm dừng LXS</span>}
                  </div>
                  <span className="ktm-emergency-card__desc">
                    Đánh dấu yêu cầu lên đầu hàng chờ.{" "}
                    {dangChay
                      ? "Công việc sẽ TẠM DỪNG và phiên máy đóng lại — giờ máy ngừng tính từ lúc gửi."
                      : "Công việc đang tạm dừng nên không đóng thêm phiên nào."}
                  </span>
                </div>
              </label>

              <div className="rc-grid" style={{ gap: "14px" }}>
                <label className="rc-field">
                  <span className="rc-field__label">Máy *</span>
                  <input className="rc-input ktm-input-modern" value={mayNhan} disabled />
                  <span className="rc-field__hint">Máy của công việc đang chạy trên bàn tổ.</span>
                </label>

                <label className="rc-field">
                  <span className="rc-field__label">Bộ phận hỏng *</span>
                  <input className="rc-input ktm-input-modern" value={boPhan} maxLength={150} autoFocus disabled={busy}
                    placeholder="vd: Trục cán & bạc đạn"
                    onChange={(e) => setBoPhan(e.target.value)} />
                  {thuGui && thieuBoPhan && <span className="rc-field__hint ktm-hint--loi">Chưa ghi bộ phận hỏng.</span>}
                </label>

                <div className="rc-field rc-field--full">
                  <span className="rc-field__label">Mức độ (theo bạn cảm nhận)</span>
                  <div className="ktm-priority-seg" style={{ marginBottom: "6px" }}>
                    {MUC_DO_OPTS.map(([ma, nhan]) => {
                      const isSel = mucDo === ma;
                      return (
                        <button key={ma} type="button"
                          disabled={busy} aria-pressed={isSel}
                          className={`ktm-priority-btn ktm-priority-btn--${ma}${isSel ? " is-selected" : ""}`}
                          onClick={() => setMucDo(ma)}>
                          <span className={`ktm-priority-dot ktm-priority-dot--${ma}`} />
                          {nhan}
                        </button>
                      );
                    })}
                  </div>
                  <span className="rc-field__hint">Cứ chọn theo cảm nhận — tổ sửa chữa sẽ đánh giá lại khi tiếp nhận.</span>
                </div>

                <label className="rc-field rc-field--full">
                  <span className="rc-field__label">Triệu chứng{mayDung ? " *" : ""}</span>
                  <textarea className="rc-input ktm-input-modern" rows={2} value={moTa} disabled={busy}
                    placeholder="Kể đúng cái mình thấy: máy kêu to ở tốc độ cao, tờ in ra bị nhăn mép…"
                    onChange={(e) => setMoTa(e.target.value)} />
                  {mayDung && (
                    <span className={`rc-field__hint${thuGui && thieuMoTa ? " ktm-hint--loi" : ""}`}>
                      Bắt buộc khi máy dừng — đây là mốc mất giờ máy của lệnh.
                    </span>
                  )}
                </label>
              </div>
            </div>
          </div>

          <footer className="rc-drawer__foot">
            <Button variant="ghost" type="button" onClick={onClose} disabled={busy}>Hủy</Button>
            <Button variant="accent" type="submit" disabled={busy}>
              {busy ? "Đang gửi…" : "Gửi yêu cầu"}
            </Button>
          </footer>
        </form>
      </aside>
    </div>,
    document.body,
  );
}
