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
            <section className="rc-sec">
              <div className="rc-sec__title">Máy hỏng thế nào</div>
              <div className="rc-grid">
                <label className="rc-field">
                  <span className="rc-field__label">Máy *</span>
                  <select className="rc-input" value="may" disabled>
                    <option value="may">{mayNhan}</option>
                  </select>
                  <span className="ktm-hint">Máy của công việc đang chạy — muốn báo máy khác thì vào màn Sửa chữa máy.</span>
                </label>

                <label className="rc-field">
                  <span className="rc-field__label">Bộ phận hỏng *</span>
                  <input className="rc-input" value={boPhan} maxLength={150} autoFocus
                    placeholder="vd: Trục cán & bạc đạn"
                    onChange={(e) => setBoPhan(e.target.value)} />
                  {thuGui && thieuBoPhan && <span className="ktm-hint ktm-hint--loi">Chưa ghi bộ phận hỏng.</span>}
                </label>

                <label className="rc-field">
                  <span className="rc-field__label">Mức độ (theo bạn thấy)</span>
                  <select className="rc-input" value={mucDo} onChange={(e) => setMucDo(e.target.value)}>
                    {MUC_DO_OPTS.map(([ma, nhan]) => <option key={ma} value={ma}>{nhan}</option>)}
                  </select>
                  <span className="ktm-hint">Cứ chọn theo cảm nhận — tổ sửa chữa sẽ đánh giá lại.</span>
                </label>

                <label className="rc-field ktm-tick">
                  <input type="checkbox" checked={mayDung} onChange={(e) => setMayDung(e.target.checked)} />
                  <span>
                    <strong>Máy đang dừng, không chạy được</strong>
                    {/* Tick ở đây khác màn Sửa chữa máy ở HỆ QUẢ: ngoài lên đầu hàng chờ còn là mốc
                        mất giờ máy của lệnh ⇒ nói thẳng ra trước khi bấm gửi. */}
                    <span className="ktm-hint">
                      Đánh dấu là yêu cầu này lên đầu hàng chờ.{" "}
                      {dangChay
                        ? "Công việc sẽ TẠM DỪNG và phiên máy đóng lại — giờ máy ngừng tính từ lúc gửi."
                        : "Công việc đang tạm dừng nên không đóng thêm phiên nào."}
                    </span>
                  </span>
                </label>

                <label className="rc-field rc-field--full">
                  <span className="rc-field__label">Triệu chứng{mayDung ? " *" : ""}</span>
                  <textarea className="rc-input" rows={3} value={moTa}
                    placeholder="Kể đúng cái mình thấy: máy kêu to ở tốc độ cao, tờ in ra bị nhăn mép…"
                    onChange={(e) => setMoTa(e.target.value)} />
                  {mayDung && (
                    <span className={`ktm-hint${thuGui && thieuMoTa ? " ktm-hint--loi" : ""}`}>
                      Bắt buộc khi máy dừng — đây là mốc mất giờ máy của lệnh.
                    </span>
                  )}
                </label>
              </div>
            </section>
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
