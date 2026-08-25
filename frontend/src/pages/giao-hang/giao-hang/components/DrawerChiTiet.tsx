// Drawer CHI TIẾT một yêu cầu giao — thông tin, danh sách chuyến, đính kèm, lịch sử, huỷ
// (tách từ pages/GiaoHangPage.tsx).
import { useState } from "react";
import type { DeliveryRequestDetail } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { fmtDate, fmtDateTime } from "../../../../utils/format";
import {
  NHAN_TRANG_THAI_CHUYEN,
  NHAN_TRANG_THAI_YC,
} from "../shared/constants";
import { nhanChuyen, toneChuyen } from "../shared/helpers";
import { Pill } from "./giaoHangCells";
import { DinhKemChuyenBox } from "./DinhKemChuyenBox";

export function DrawerChiTiet({
  detail,
  canCancel,
  onClose,
  onHuy,
}: {
  detail: DeliveryRequestDetail;
  canCancel: boolean;
  onClose: () => void;
  onHuy?: (lyDo: string) => void;
}) {
  const { token } = useAuth();
  const [lyDo, setLyDo] = useState("");
  const r = detail.request;
  const huyDuoc = canCancel && r.trang_thai === "cho_len_ke_hoach" && detail.trips.length === 0;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <Pill
              text={NHAN_TRANG_THAI_YC[r.trang_thai] ?? r.trang_thai}
              tone={r.trang_thai === "da_giao_du" ? "on" : r.trang_thai === "da_huy" ? "off" : "warn"}
            />
            <h2 className="rc-drawer__title">{r.code}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        <div className="rc-drawer__body">
          <section>
            <h3>Đơn hàng &amp; khách</h3>
            <p>
              {r.order_code} · {r.customer_name}
            </p>
            <p>Ngày cần giao: {fmtDate(r.ngay_can_giao)}</p>
            {/* Địa chỉ là SNAPSHOT lúc lập yêu cầu — sửa địa chỉ đơn sau này KHÔNG đổi dòng này. */}
            <p>
              {r.dia_chi}
              {r.nguoi_nhan ? ` — ${r.nguoi_nhan}` : ""}
              {r.sdt_nguoi_nhan ? ` · ${r.sdt_nguoi_nhan}` : ""}
            </p>
            {r.ghi_chu && <p>{r.ghi_chu}</p>}
          </section>

          <section>
            <h3>Hàng cần giao</h3>
            <table className="rc__table">
              <thead>
                <tr>
                  <th>Mặt hàng</th>
                  <th>Yêu cầu</th>
                  <th>Đã giao</th>
                </tr>
              </thead>
              <tbody>
                {r.lines.map((l) => (
                  <tr key={l.id}>
                    <td>{l.mo_ta}</td>
                    <td>
                      {l.qty} {l.don_vi_tinh}
                    </td>
                    <td>{l.da_giao}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            {/* MỘT yêu cầu = MỘT chuyến (22/08/2026). Bỏ tiêu đề đếm "Các lần giao (N)" — đếm một
                thứ luôn bằng 1 là bắt người đọc hỏi "sao lại có số đếm ở đây". Muốn giao lại thì
                lập yêu cầu mới, nên phần này chỉ còn là dòng thông tin của chính chuyến đó. */}
            <h3>Chuyến giao</h3>
            {detail.trips.length === 0 && <p>Chưa lên kế hoạch.</p>}
            {detail.trips.map((t) => (
              <div key={t.id} className="gh-line">
                <Pill
                  text={nhanChuyen(t)}
                  tone={toneChuyen(t.trang_thai)}
                />
                <span>
                  {t.employee_name} · {fmtDateTime(t.gio_lay_hang)}
                  {t.km != null ? ` · ${t.km} km` : ""}
                  {t.yeu_cau_kho_ma ? ` · ${t.yeu_cau_kho_ma}` : ""}
                </span>
                {t.ly_do_that_bai && <em>{t.ly_do_that_bai}</em>}
              </div>
            ))}
            {detail.trips[0] && <DinhKemChuyenBox tripId={detail.trips[0].id} token={token} />}
          </section>

          <section>
            <h3>Lịch sử trạng thái</h3>
            {detail.lich_su.map((h) => (
              <div key={h.id} className="gh-line">
                <span>
                  {fmtDateTime(h.luc)} · {NHAN_TRANG_THAI_CHUYEN[h.den_trang_thai] ?? h.den_trang_thai}
                  {h.nguoi_thao_tac_name ? ` · ${h.nguoi_thao_tac_name}` : ""}
                  {h.ly_do ? ` — ${h.ly_do}` : ""}
                </span>
              </div>
            ))}
          </section>

          {huyDuoc && onHuy && (
            <section>
              <h3>Huỷ yêu cầu</h3>
              <input
                className="input"
                placeholder="Lý do huỷ"
                value={lyDo}
                onChange={(e) => setLyDo(e.target.value)}
              />
              <Button variant="ghost" disabled={!lyDo.trim()} onClick={() => onHuy(lyDo.trim())}>
                Huỷ yêu cầu
              </Button>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}
