// Hộp thoại GHI KẾT QUẢ GIAO (tách từ pages/GiaoHangPage.tsx).
// ⚠️ Ô `km` (chuyến ngoài lượt) và ô SỐ ĐỒNG HỒ (chuyến trong lượt xe, từ 18/09/2026) ở đây NUÔI
// TIỀN KHOÁN KM của tài xế, và payload `ghiKetQua` là logic nghiệp vụ — sửa thì sửa có chủ đích.
import { useEffect, useState } from "react";
import { crud, type Row } from "../../../../api/rebuildCatalog";
import type { DeliveryTrip, KetQuaInput } from "../../../../api/client";
import { api } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import type { DongConLai } from "../shared/types";

// =============================================================================
// Dialog · Nhập kết quả
// =============================================================================
export function DialogKetQua({
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
  const [ketQua, setKetQua] = useState<KetQuaInput["ket_qua"]>("thanh_cong");
  const [km, setKm] = useState("");
  const luot = trip.luot ?? null;
  const [soDongHo, setSoDongHo] = useState("");
  const [nguoiNhan, setNguoiNhan] = useState("");
  const [lyDo, setLyDo] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [xacNhanKm, setXacNhanKm] = useState(false);
  const [hoiXacNhan, setHoiXacNhan] = useState(false);
  const [xeId, setXeId] = useState(trip.vehicle_id ? String(trip.vehicle_id) : "");
  const [xeDs, setXeDs] = useState<Row[]>([]);
  const [nhan, setNhan] = useState<Record<number, string>>({});
  const [conLai, setConLai] = useState<DongConLai[] | null>(null);

  useEffect(() => {
    if (trip.luot) return;
    crud("/api/xe").list(token, { active: true })
      .then(async (r) => {
        const ds = r.items;
        if (trip.vehicle_id && !ds.some((x) => x.id === trip.vehicle_id)) {
          const cu = await crud("/api/xe").get(token, trip.vehicle_id).catch(() => null);
          if (cu) ds.push(cu);
        }
        setXeDs(ds);
      })
      .catch(() => setXeDs([]));
  }, [token, trip.vehicle_id, trip.luot]);

  useEffect(() => {
    api.giaoHang
      .request(token, trip.request_id)
      .then((d) => {
        const ds = d.request.lines
          .map((l) => ({
            order_line_id: l.order_line_id,
            mo_ta: l.mo_ta,
            don_vi_tinh: l.don_vi_tinh,
            con: l.qty - l.da_giao,
          }))
          .filter((l) => l.con > 0);
        setConLai(ds);
        setNhan(Object.fromEntries(ds.map((l) => [l.order_line_id, String(l.con)])));
      })
      .catch(() => setConLai([]));
  }, [token, trip.request_id]);

  const gui = () => {
    setLoi(null);
    const body: KetQuaInput = {
      ket_qua: ketQua,
      ...(luot ? { so_dong_ho: Number(soDongHo) } : { km: Number(km) }),
      xac_nhan_km_lon: xacNhanKm,
    };
    if (xeId && !luot) body.vehicle_id = Number(xeId);
    if (ketQua === "thanh_cong" || ketQua === "giao_thieu") body.nguoi_nhan_thuc_te = nguoiNhan;
    if (ketQua === "giao_thieu")
      body.so_thuc_nhan = (conLai ?? []).map((l) => ({
        order_line_id: l.order_line_id,
        qty: Number(nhan[l.order_line_id] ?? 0),
      }));
    if (ketQua === "that_bai") {
      body.ly_do_that_bai = lyDo;
      body.huong_xu_ly = "tra_ve";
    }
    api.giaoHang
      .ghiKetQua(token, trip.id, body)
      .then(onXong)
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Không ghi được kết quả";
        setLoi(msg);
        if (msg.includes("bất thường")) {
          setXacNhanKm(false);
          setHoiXacNhan(true);
        }
      });
  };

  const soGo = soDongHo === "" ? null : Number(soDongHo);
  const ganNhat = luot?.so_dong_ho_gan_nhat ?? null;
  const chang = soGo != null && ganNhat != null && soGo >= ganNhat ? soGo - ganNhat : null;
  const kmXem = luot ? chang : km === "" ? null : Number(km);
  const kmLon = (kmXem ?? 0) > 500 || hoiXacNhan;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Kết quả · {trip.request_code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body gh-form">
          <label>
            Kết quả
            <select className="input" value={ketQua}
              onChange={(e) => setKetQua(e.target.value as KetQuaInput["ket_qua"])}>
              <option value="thanh_cong">Giao thành công</option>
              <option value="giao_thieu">Giao thiếu</option>
              <option value="that_bai">Giao thất bại</option>
            </select>
          </label>

          {luot ? (
            <div className="gh-card" style={{ background: "#f8fafc", margin: "4px 0" }}>
              <label>
                Số đồng hồ lúc tới khách
                <input className="input" type="number" min="0" step="1" value={soDongHo}
                  onChange={(e) => setSoDongHo(e.target.value)} />
              </label>
              <p className="rc__sub" style={{ margin: "6px 0 0" }}>
                Lượt <b>{luot.code}</b>
                {trip.xe_bien_so ? ` · xe ${trip.xe_bien_so}` : ""}
                {ganNhat != null ? ` · số gần nhất đã ghi ${ganNhat.toLocaleString("vi-VN")}` : ""}
                {chang != null ? ` ⇒ chặng này ${chang.toLocaleString("vi-VN")} km` : ""}
              </p>
              {soGo != null && luot.so_dong_ho_xuat_phat != null && soGo < luot.so_dong_ho_xuat_phat
                && soDongHo.length >= String(luot.so_dong_ho_xuat_phat).length && (
                <div className="banner banner--warn" role="status" style={{ marginTop: "8px" }}>
                  Nhỏ hơn số lúc xuất phát ({luot.so_dong_ho_xuat_phat.toLocaleString("vi-VN")}) —
                  đồng hồ không chạy lùi, kiểm lại số.
                </div>
              )}
            </div>
          ) : (
            <label>
              Số km thực tế
              <input className="input" type="number" min="0" step="1" value={km}
                onChange={(e) => setKm(e.target.value)} />
            </label>
          )}

          {!luot && xeDs.length > 0 && (
            <label>
              Xe đã chạy chuyến
              <select className="input" value={xeId} onChange={(e) => setXeId(e.target.value)}>
                <option value="">— Chọn xe —</option>
                {xeDs.map((x) => (
                  <option key={x.id} value={x.id}>
                    {String(x.ma ?? "")}
                    {x.ten ? ` · ${String(x.ten)}` : ""}
                    {x.tai_trong != null ? ` · ${Number(x.tai_trong).toLocaleString("vi-VN")} tấn` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          {kmLon && (
            <label className="gh-line" style={{ background: "#fffbeb", padding: "8px 12px", borderRadius: "6px" }}>
              <input type="checkbox" checked={xacNhanKm}
                onChange={(e) => setXacNhanKm(e.target.checked)} />
              {" "}
              {luot
                ? `Xác nhận ${chang != null ? `chặng ${chang} km` : `số đồng hồ ${soDongHo}`} là đúng`
                : `Xác nhận ${km} km là đúng`}
            </label>
          )}

          {(ketQua === "thanh_cong" || ketQua === "giao_thieu") && (
            <fieldset className="gh-pick">
              <legend>
                {ketQua === "thanh_cong" ? "Khách nhận đủ" : "Số khách thực nhận"}
              </legend>
              {conLai === null && <p className="rc__sub">Đang tải hàng của yêu cầu…</p>}
              {conLai?.length === 0 && <p className="rc__sub">Không còn hàng nào để giao.</p>}
              {(conLai ?? []).map((l) => (
                <div key={l.order_line_id} className="gh-pick__row">
                  <span className="gh-pick__tick">
                    <span>
                      {l.mo_ta}
                      <em> · còn {l.con} {l.don_vi_tinh}</em>
                    </span>
                  </span>
                  <input
                    className="input gh-pick__qty"
                    type="number" min="0" step="1" max={l.con}
                    disabled={ketQua === "thanh_cong"}
                    aria-label={`Số thực nhận — ${l.mo_ta ?? ""}`}
                    value={ketQua === "thanh_cong" ? String(l.con) : (nhan[l.order_line_id] ?? "")}
                    onChange={(e) =>
                      setNhan((p) => ({ ...p, [l.order_line_id]: e.target.value }))
                    }
                  />
                </div>
              ))}
            </fieldset>
          )}

          {(ketQua === "thanh_cong" || ketQua === "giao_thieu") && (
            <label>
              Người nhận hàng
              <input className="input" value={nguoiNhan} placeholder="Tên người nhận..."
                onChange={(e) => setNguoiNhan(e.target.value)} />
            </label>
          )}

          {ketQua === "that_bai" && (
            <>
              <label>
                Lý do thất bại
                <input className="input" value={lyDo} placeholder="Nhập lý do giao thất bại..."
                  onChange={(e) => setLyDo(e.target.value)} />
              </label>
              <p className="rc__sub" style={{ margin: 0 }}>
                Hàng sẽ được <strong>trả về kho</strong>. Muốn giao lại thì lập
                {" "}<strong>yêu cầu giao mới</strong>.
              </p>
            </>
          )}

          {loi && (
            <div className="banner banner--error" role="alert" style={{ margin: 0 }}>
              {loi}
            </div>
          )}

          <Button variant="accent" disabled={luot ? soDongHo === "" : km === ""} onClick={gui}>
            Lưu kết quả
          </Button>
        </div>
      </aside>
    </div>
  );
}
