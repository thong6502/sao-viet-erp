// Hộp thoại GHI KẾT QUẢ GIAO (tách từ pages/GiaoHangPage.tsx).
// ⚠️ Ô `km` ở đây NUÔI TIỀN KHOÁN KM của tài xế, và payload `ghiKetQua` là logic nghiệp vụ —
// giữ nguyên văn, đừng đụng.
import { useEffect, useState } from "react";
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
  const [nguoiNhan, setNguoiNhan] = useState("");
  const [lyDo, setLyDo] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [xacNhanKm, setXacNhanKm] = useState(false);
  // Số thực nhận TỪNG DÒNG. Bản đầu chỉ có một ô cho `lines[0]` — đơn hai mặt hàng là ghi thiếu
  // hẳn một dòng mà không ai báo.
  const [nhan, setNhan] = useState<Record<number, string>>({});
  const [conLai, setConLai] = useState<DongConLai[]>([]);

  // Đọc từ CHÍNH YÊU CẦU, không phải từ đơn: chuyến này chỉ giao phần của yêu cầu đó, và phần
  // "còn lại" phải trừ những lần giao trước của cùng yêu cầu — đúng phép máy chủ đang tính.
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
      km: Number(km),
      xac_nhan_km_lon: xacNhanKm,
    };
    if (ketQua === "thanh_cong" || ketQua === "giao_thieu") body.nguoi_nhan_thuc_te = nguoiNhan;
    if (ketQua === "giao_thieu")
      body.so_thuc_nhan = conLai.map((l) => ({
        order_line_id: l.order_line_id,
        qty: Number(nhan[l.order_line_id] ?? 0),
      }));
    if (ketQua === "that_bai") {
      body.ly_do_that_bai = lyDo;
      // Chỉ còn MỘT hướng xử lý (22/08/2026): hàng về kho. "Chờ giao lại" giữ hàng trên xe trong
      // khi sổ kho ghi đã xuất — chính chỗ đó che mất lỗi "trả hàng về không vào sổ".
      body.huong_xu_ly = "tra_ve";
    }
    api.giaoHang
      .ghiKetQua(token, trip.id, body)
      .then(onXong)
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Không ghi được kết quả";
        setLoi(msg);
        // Km lớn bất thường là chặn MỀM — hiện nút xác nhận thay vì bắt gõ lại.
        if (msg.includes("bất thường")) setXacNhanKm(false);
      });
  };

  const kmLon = Number(km) > 500;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <h2 className="rc-drawer__title">Kết quả · {trip.request_code}</h2>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="rc-drawer__body">
          <label>
            Kết quả
            <select className="input" value={ketQua}
              onChange={(e) => setKetQua(e.target.value as KetQuaInput["ket_qua"])}>
              <option value="thanh_cong">Giao thành công</option>
              <option value="giao_thieu">Giao thiếu</option>
              {/* "Khách hẹn lại" GỠ 22/08/2026: nó là trạng thái treo — chuyến chưa xong mà cũng
                  không kết thúc, hàng nằm trên xe không biết tới bao giờ. Khách hẹn lại thì chọn
                  "Giao thất bại", hàng về kho, rồi lập YÊU CẦU MỚI cho ngày hẹn. */}
              <option value="that_bai">Giao thất bại</option>
            </select>
          </label>

          <label>
            Số km thực tế
            {/* `type="number"` chứ KHÔNG phải `inputMode` — inputMode chỉ đổi bàn phím điện
                thoại, bàn phím máy tính vẫn gõ chữ vào được. `min=0` vì 0 km là số THẬT. */}
            <input className="input" type="number" min="0" step="1" value={km}
              onChange={(e) => setKm(e.target.value)} />
          </label>
          {/* 0 km là số THẬT (xe chưa lăn bánh) — không chặn. Chỉ hỏi lại khi lớn bất thường. */}
          {kmLon && (
            <label className="gh-line">
              <input type="checkbox" checked={xacNhanKm}
                onChange={(e) => setXacNhanKm(e.target.checked)} />
              {" "}Xác nhận {km} km là đúng
            </label>
          )}

          {/* SỐ LƯỢNG THỰC NHẬN hiện ở CẢ HAI kết quả. Trước đây chọn "Giao thành công" thì
              máy tự điền, người bấm không thấy mình đang xác nhận bao nhiêu — mà đây là con số
              cộng thẳng vào "đã giao" của đơn hàng. */}
          {(ketQua === "thanh_cong" || ketQua === "giao_thieu") && (
            <fieldset className="gh-pick">
              <legend>
                {ketQua === "thanh_cong" ? "Khách nhận đủ" : "Số khách thực nhận"}
              </legend>
              {conLai.length === 0 && <p className="rc__sub">Không còn hàng nào để giao.</p>}
              {conLai.map((l) => (
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
                    // Thành công = nhận đủ ⇒ khoá ô, chỉ để XEM. Muốn sửa số thì đổi kết quả
                    // sang "Giao thiếu" — để lựa chọn nằm ở dropdown, không nằm ở việc gõ số.
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
              <input className="input" value={nguoiNhan}
                onChange={(e) => setNguoiNhan(e.target.value)} />
            </label>
          )}

          {ketQua === "that_bai" && (
            <>
              <label>
                Lý do thất bại
                <input className="input" value={lyDo} onChange={(e) => setLyDo(e.target.value)} />
              </label>
              {/* Không còn ô chọn: chỉ một hướng. Nói TRƯỚC hệ quả, đừng để người dùng phát
                  hiện sau khi bấm. */}
              <p className="rc__sub">
                Hàng sẽ được <strong>trả về kho</strong>. Muốn giao lại thì lập
                {" "}<strong>yêu cầu giao mới</strong>.
              </p>
            </>
          )}

          {loi && (
            <div className="banner banner--error" role="alert">
              {loi}
            </div>
          )}

          <Button variant="accent" disabled={km === ""} onClick={gui}>
            Lưu kết quả
          </Button>
        </div>
      </aside>
    </div>
  );
}
