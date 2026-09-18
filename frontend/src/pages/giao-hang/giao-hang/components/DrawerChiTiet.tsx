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
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <div>
              <Pill
                text={NHAN_TRANG_THAI_YC[r.trang_thai] ?? r.trang_thai}
                tone={r.trang_thai === "da_giao_du" ? "on" : r.trang_thai === "da_huy" ? "off" : "warn"}
              />
            </div>
            <h2 className="rc-drawer__title" style={{ margin: 0 }}>{r.code}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        <div className="rc-drawer__body">
          <section className="gh-card">
            <h3 className="gh-card__title">Đơn hàng &amp; khách hàng</h3>
            <div className="gh-grid-2">
              <div className="gh-meta-item">
                <span className="gh-meta-label">Khách hàng</span>
                <span className="gh-meta-value">{r.customer_name}</span>
              </div>
              <div className="gh-meta-item">
                <span className="gh-meta-label">Mã đơn hàng</span>
                <span className="gh-meta-value">{r.order_code}</span>
              </div>
              <div className="gh-meta-item">
                <span className="gh-meta-label">Ngày cần giao</span>
                <span className="gh-meta-value">{fmtDate(r.ngay_can_giao)}</span>
              </div>
              <div className="gh-meta-item">
                <span className="gh-meta-label">Người nhận &amp; SĐT</span>
                <span className="gh-meta-value">
                  {r.nguoi_nhan ?? "—"}{r.sdt_nguoi_nhan ? ` · ${r.sdt_nguoi_nhan}` : ""}
                </span>
              </div>
              <div className="gh-meta-item" style={{ gridColumn: "1 / -1" }}>
                <span className="gh-meta-label">Địa chỉ giao</span>
                <span className="gh-meta-value">{r.dia_chi || "—"}</span>
              </div>
              {r.ghi_chu && (
                <div className="gh-meta-item" style={{ gridColumn: "1 / -1" }}>
                  <span className="gh-meta-label">Ghi chú</span>
                  <span className="gh-meta-value">{r.ghi_chu}</span>
                </div>
              )}
            </div>
          </section>

          <section className="gh-card">
            <h3 className="gh-card__title">Hàng cần giao</h3>
            <table className="rc__table">
              <thead>
                <tr>
                  <th>Mặt hàng</th>
                  <th style={{ width: 110, textAlign: "right" }}>Yêu cầu</th>
                  <th style={{ width: 110, textAlign: "right" }}>Đã giao</th>
                </tr>
              </thead>
              <tbody>
                {r.lines.map((l) => (
                  <tr key={l.id}>
                    <td style={{ fontWeight: 500 }}>{l.mo_ta}</td>
                    <td style={{ textAlign: "right" }} className="gh-num">
                      {l.qty} {l.don_vi_tinh}
                    </td>
                    <td style={{ textAlign: "right" }} className="gh-num">
                      {l.da_giao} {l.don_vi_tinh}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="gh-card">
            <h3 className="gh-card__title">Chuyến giao</h3>
            {detail.trips.length === 0 && <p className="rc__sub" style={{ margin: "4px 0" }}>Chưa lên kế hoạch.</p>}
            {detail.trips.map((t) => (
              <div key={t.id} className="gh-line">
                <Pill
                  text={nhanChuyen(t)}
                  tone={toneChuyen(t.trang_thai)}
                />
                <span style={{ fontWeight: 500 }}>
                  {t.employee_name} · {fmtDateTime(t.gio_lay_hang)}
                  {t.km != null ? ` · ${t.km} km` : ""}
                  {t.yeu_cau_kho_ma ? ` · ${t.yeu_cau_kho_ma}` : ""}
                  {t.luot ? ` · lượt ${t.luot.code}` : ""}
                  {t.luot?.so_dong_ho != null
                    ? ` · đồng hồ ${t.luot.so_dong_ho.toLocaleString("vi-VN")}` : ""}
                  {t.luot?.la_diem_cuoi && t.luot.km_ve_kho != null
                    ? ` · về kho ${t.luot.km_ve_kho} km` : ""}
                </span>
                {t.ly_do_that_bai && <em>({t.ly_do_that_bai})</em>}
              </div>
            ))}
            {detail.trips[0] && <DinhKemChuyenBox tripId={detail.trips[0].id} token={token} />}
          </section>

          <section className="gh-card">
            <h3 className="gh-card__title">Lịch sử trạng thái</h3>
            {detail.lich_su.length === 0 && <p className="rc__sub" style={{ margin: "4px 0" }}>Chưa có lịch sử trạng thái.</p>}
            {detail.lich_su.map((h) => (
              <div key={h.id} className="gh-line">
                <span>
                  <strong>{fmtDateTime(h.luc)}</strong> · {NHAN_TRANG_THAI_CHUYEN[h.den_trang_thai] ?? h.den_trang_thai}
                  {h.nguoi_thao_tac_name ? ` · ${h.nguoi_thao_tac_name}` : ""}
                  {h.ly_do ? ` — ${h.ly_do}` : ""}
                </span>
              </div>
            ))}
          </section>

          {huyDuoc && onHuy && (
            <section className="gh-card" style={{ borderColor: "#fecaca", background: "#fef2f2" }}>
              <h3 className="gh-card__title" style={{ color: "#991b1b" }}>Huỷ yêu cầu</h3>
              <div style={{ display: "flex", gap: "10px", marginTop: "8px" }}>
                <input
                  className="input"
                  placeholder="Lý do huỷ..."
                  value={lyDo}
                  onChange={(e) => setLyDo(e.target.value)}
                />
                <Button variant="ghost" disabled={!lyDo.trim()} onClick={() => onHuy(lyDo.trim())}>
                  Huỷ yêu cầu
                </Button>
              </div>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}
