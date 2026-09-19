// Đổi / huỷ MỘT chuyến khi tài xế CHƯA cầm hàng (đã lên kế hoạch / kho đang chuẩn bị) — 19/09/2026.
// Đổi xe KHÔNG có ở đây: chuyến trong lượt ăn số đồng hồ của xe lượt, máy chủ chặn đổi xe riêng một
// chuyến — muốn đổi xe thì huỷ chuyến rồi Bán hàng lập yêu cầu mới. Huỷ chuyến là kết cục của yêu
// cầu (một yêu cầu = một chuyến): yêu cầu thành "Chuyến đã huỷ", phần hàng nhả về "giao được".
import { useEffect, useState } from "react";
import type { DeliveryDriverPick, DeliveryTrip } from "../../../../api/client";
import { api } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { GIO_NHAP_MAX, GIO_NHAP_MIN, gioNhapHopLe, gioNhapSai } from "../../../../lib/gioNhap";

/** ISO từ máy chủ → giá trị ô `datetime-local` theo giờ máy người dùng. */
function oGio(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  if (isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function DialogDoiChuyen({
  trip,
  token,
  onClose,
  onXong,
}: {
  trip: DeliveryTrip;
  token: string;
  onClose: () => void;
  onXong: () => void;
}) {
  const [taiXe, setTaiXe] = useState<DeliveryDriverPick[]>([]);
  const [employeeId, setEmployeeId] = useState(String(trip.employee_id));
  const [lay, setLay] = useState(oGio(trip.gio_lay_hang));
  const [giao, setGiao] = useState(oGio(trip.gio_du_kien_giao));
  const [ghiChu, setGhiChu] = useState(trip.ghi_chu_phan_cong ?? "");
  const [lyDo, setLyDo] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [canhBao, setCanhBao] = useState<string[]>([]);
  const [dangGui, setDangGui] = useState(false);

  useEffect(() => {
    api.giaoHang.taiXeChon(token).then((r) => setTaiXe(r.items)).catch(() => setTaiXe([]));
  }, [token]);

  const gioGoc = { lay: oGio(trip.gio_lay_hang), giao: oGio(trip.gio_du_kien_giao) };
  const doi =
    employeeId !== String(trip.employee_id) || lay !== gioGoc.lay || giao !== gioGoc.giao ||
    ghiChu !== (trip.ghi_chu_phan_cong ?? "");

  const luu = () => {
    setLoi(null);
    setDangGui(true);
    api.giaoHang
      .updatePlan(token, trip.id, {
        ...(employeeId !== String(trip.employee_id) ? { employee_id: Number(employeeId) } : {}),
        // Chỉ gửi giờ NGƯỜI DÙNG VỪA ĐỔI: máy chủ chặn giờ quá khứ, gửi lại giờ cũ đã qua là chặn oan.
        ...(lay !== gioGoc.lay ? { gio_lay_hang: new Date(lay).toISOString() } : {}),
        ...(giao !== gioGoc.giao ? { gio_du_kien_giao: new Date(giao).toISOString() } : {}),
        ghi_chu_phan_cong: ghiChu || null,
      })
      .then((r) => {
        if (r.canh_bao.length) {
          setCanhBao(r.canh_bao);
          window.setTimeout(onXong, 1500);
        } else onXong();
      })
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không đổi được kế hoạch"))
      .finally(() => setDangGui(false));
  };

  const huy = () => {
    setLoi(null);
    setDangGui(true);
    api.giaoHang
      .cancelPlan(token, trip.id, lyDo.trim())
      .then(onXong)
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không huỷ được chuyến"))
      .finally(() => setDangGui(false));
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Đổi / huỷ chuyến · {trip.request_code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body gh-form">
          <p className="rc__sub" style={{ margin: 0 }}>
            {trip.customer_name} · {trip.order_code}
            {trip.xe_bien_so ? ` · xe ${trip.xe_bien_so}` : ""}
            {trip.yeu_cau_kho_ma ? ` · đã gửi kho ${trip.yeu_cau_kho_ma}` : ""}
          </p>

          <div className="gh-card" style={{ marginBottom: 0 }}>
            <h3 className="gh-card__title">Đổi kế hoạch</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <label>
                Nhân viên giao
                <select className="input" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
                  {!taiXe.some((t) => String(t.id) === String(trip.employee_id)) && (
                    <option value={trip.employee_id}>{trip.employee_name ?? "Tài xế hiện tại"}</option>
                  )}
                  {taiXe.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.full_name}{t.code ? ` · ${t.code}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Giờ lấy hàng
                <input className="input" type="datetime-local" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
                  value={lay} onChange={(e) => setLay(e.target.value)} />
              </label>
              <label>
                Giờ dự kiến giao
                <input className="input" type="datetime-local" min={GIO_NHAP_MIN} max={GIO_NHAP_MAX}
                  value={giao} onChange={(e) => setGiao(e.target.value)} />
              </label>
              {(gioNhapSai(lay) || gioNhapSai(giao)) && (
                <div className="banner banner--warn" role="status" style={{ margin: 0 }}>
                  Giờ không đọc được — năm phải 4 chữ số, trong khoảng 2000–2099.
                </div>
              )}
              <label>
                Ghi chú phân công
                <input className="input" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} />
              </label>
              <Button variant="accent"
                disabled={!doi || dangGui || !gioNhapHopLe(lay) || !gioNhapHopLe(giao)}
                onClick={luu}>
                Lưu thay đổi
              </Button>
            </div>
          </div>

          <div className="gh-card" style={{ marginBottom: 0 }}>
            <h3 className="gh-card__title">Huỷ chuyến</h3>
            {trip.kho_da_lap_phieu ? (
              <div className="banner banner--warn" role="status" style={{ margin: 0 }}>
                Kho đã lập phiếu cho đề nghị xuất {trip.yeu_cau_kho_ma ?? ""} — hàng đã soạn. Báo kho huỷ
                phiếu trước rồi mới huỷ chuyến được.
              </div>
            ) : (
              <>
                <p className="rc__sub" style={{ margin: "0 0 8px" }}>
                  Yêu cầu giao kết thúc ở “Chuyến đã huỷ”, hàng nhả về phần giao được — Bán hàng thấy
                  ngay trên đơn, muốn giao tiếp thì lập yêu cầu mới.
                  {trip.yeu_cau_kho_ma ? ` Đề nghị xuất kho ${trip.yeu_cau_kho_ma} huỷ theo.` : ""}
                </p>
                <label>
                  Lý do huỷ chuyến
                  <input className="input" value={lyDo} onChange={(e) => setLyDo(e.target.value)} />
                </label>
                <Button variant="ghost" disabled={!lyDo.trim() || dangGui} onClick={huy}>
                  Huỷ chuyến
                </Button>
              </>
            )}
          </div>

          {canhBao.map((c) => (
            <div key={c} className="banner banner--warn" role="status" style={{ margin: 0 }}>{c}</div>
          ))}
          {loi && <div className="banner banner--error" role="alert" style={{ margin: 0 }}>{loi}</div>}
        </div>
      </aside>
    </div>
  );
}
