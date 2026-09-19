// "Tạo yêu cầu giao hàng" — khối trên màn Đơn hàng bán (docs/prd-giao-hang.md §3, §5).
//
// Đặt ở ĐÂY chứ không dựng màn mới: người lập yêu cầu là Bán hàng, và họ đang đứng ở đơn hàng.
// Bắt họ nhớ mã đơn rồi sang màn khác gõ lại là thêm một chỗ gõ sai.
//
// HAI LUẬT của PRD được thể hiện thẳng trên giao diện:
//   · "CHỌN, không gõ lại" — địa chỉ / người nhận / SĐT điền sẵn từ đơn, sửa được, rồi ĐÔNG LẠI
//     thành snapshot của yêu cầu (sửa địa chỉ đơn tháng sau không đổi phiếu giao cũ).
//   · "GHI LÀ GHI" — không có ô Thao tác của màn Giao hàng thì KHÔNG bày nút. Bày ra rồi bấm ăn
//     403 trông như hệ thống hỏng, chứ không như "anh không có quyền".
// (tách từ pages/TaoYeuCauGiaoHang.tsx).
import { Fragment, useCallback, useEffect, useState } from "react";
import type { ConPhaiGiao, DeliveryRequest } from "../../../api/client";
import { api } from "../../../api/client";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
import { Button } from "../../../components/Button";
import { fmtDate } from "../../../utils/format";
import { gomCum, nhanCum } from "../gomCum";
import "../../giao-hang.css";

/** Hôm nay dạng `YYYY-MM-DD` — cùng dạng với `input[type=date]`, so sánh chuỗi là đủ.
 *  `toISOString()` trả giờ UTC nên có thể lệch một ngày; dùng giờ ĐỊA PHƯƠNG vì người dùng và
 *  nhà máy đều ở VN, lệch ngày ở đây là chặn nhầm đúng ngày hôm nay. */
function homNay(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const HOM_NAY = homNay();

export function TaoYeuCauGiaoHang({
  orderId,
  diaChiMacDinh,
  nguoiNhanMacDinh,
  sdtMacDinh,
}: {
  orderId: number;
  diaChiMacDinh?: string | null;
  nguoiNhanMacDinh?: string | null;
  sdtMacDinh?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canRead = can("giao_hang", "read");
  const canWrite = can("giao_hang", "create");

  const [con, setCon] = useState<ConPhaiGiao | null>(null);
  const [ds, setDs] = useState<DeliveryRequest[]>([]);
  const [mo, setMo] = useState(false);
  const [ngay, setNgay] = useState("");
  const [soLuong, setSoLuong] = useState<Record<number, string>>({});
  // TÍCH TỪNG DÒNG. Đơn hai sản phẩm mà mới xong cái thứ nhất là chuyện thường — phải giao được
  // riêng cái đó.
  const [chon, setChon] = useState<Record<number, boolean>>({});
  const [diaChi, setDiaChi] = useState(diaChiMacDinh ?? "");
  const [nguoiNhan, setNguoiNhan] = useState(nguoiNhanMacDinh ?? "");
  const [sdt, setSdt] = useState(sdtMacDinh ?? "");
  const [loi, setLoi] = useState<string | null>(null);
  const [dangGui, setDangGui] = useState(false);

  const load = useCallback(() => {
    if (!token || !canRead) return;
    api.giaoHang.conPhaiGiao(token, orderId).then(setCon).catch(() => setCon(null));
    api.giaoHang.requests(token, { orderId }).then((r) => setDs(r.items)).catch(() => setDs([]));
  }, [token, orderId, canRead]);

  useEffect(() => {
    load();
  }, [load]);

  if (!canRead || !con) return null;

  const conGi = con.lines.some((l) => l.con_phai_giao > 0);
  const ngayQuaKhu = ngay !== "" && ngay < HOM_NAY;

  const gui = () => {
    if (!token) return;
    setLoi(null);
    setDangGui(true);
    // Một cụm gửi MỘT dòng (dòng đầu) — máy chủ bung ra mọi dòng của cụm cùng số.
    const lines = gomCum(con.lines)
      .filter((c) => chon[c.dau.order_line_id])
      // Mặt hàng kho KHÔNG gửi từ đây: máy chủ tự khai vào danh mục Thành phẩm từ chính dòng đơn.
      // Sản phẩm in là hàng đặt riêng — không có sẵn trong danh mục để mà chọn.
      .map((c) => ({
        order_line_id: c.dau.order_line_id,
        qty: Number(soLuong[c.dau.order_line_id] ?? 0),
      }))
      .filter((l) => l.qty > 0);
    api.giaoHang
      .createRequest(token, {
        order_id: orderId,
        ngay_can_giao: ngay,
        lines,
        dia_chi: diaChi || null,
        nguoi_nhan: nguoiNhan || null,
        sdt_nguoi_nhan: sdt || null,
      })
      .then(() => {
        setMo(false);
        setSoLuong({});
        setChon({});
        load();
      })
      .catch((e: unknown) => setLoi(e instanceof Error ? e.message : "Không tạo được yêu cầu"))
      .finally(() => setDangGui(false));
  };

  return (
    <section className="gh-section">
      <div className="rc__headrow" style={{ marginBottom: "12px" }}>
        <h3 className="rc__title" style={{ fontSize: "15px", margin: 0 }}>Giao hàng</h3>
        {con.da_giao_du && <span className="rc-pill rc-pill--on gh-pill gh-pill--on">Đã giao đủ</span>}
      </div>

      <div style={{ border: "1px solid #e2e8f0", borderRadius: "8px", overflow: "hidden", marginBottom: "14px" }}>
        <table className="rc__table">
          <thead>
            <tr>
              <th>Mặt hàng</th>
              <th style={{ width: 110, textAlign: "right" }}>Đặt</th>
              <th style={{ width: 100, textAlign: "right" }}>Đã giao</th>
              <th style={{ width: 120, textAlign: "right" }}>Còn phải giao</th>
            </tr>
          </thead>
          <tbody>
            {con.lines.map((l) => (
              <tr key={l.order_line_id}>
                <td style={{ fontWeight: 500 }}>{l.mo_ta}</td>
                <td className="gh-num">
                  {l.qty_dat} {l.don_vi_tinh}
                </td>
                <td className="gh-num">{l.da_giao}</td>
                <td className="gh-num" style={{ fontWeight: 600, color: l.con_phai_giao > 0 ? "#0f172a" : "#64748b" }}>
                  {l.con_phai_giao}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {ds.length > 0 && (
        <p className="rc__sub" style={{ margin: "0 0 12px" }}>
          Đã lập {ds.length} yêu cầu: {ds.map((r) => r.code).join(", ")}
        </p>
      )}

      {canWrite && conGi && !mo && (
        <Button variant="accent" onClick={() => setMo(true)}>
          Tạo yêu cầu giao hàng
        </Button>
      )}
      {!canWrite && conGi && (
        <p className="rc__sub">
          Chỉ xem — vai của bạn chưa được bật ô Thao tác ở màn Giao hàng nên không lập được yêu cầu.
        </p>
      )}

      {mo && (
        <div className="gh-form" style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid #e2e8f0" }}>
          <label>
            Ngày cần giao
            <input className="input" type="date" value={ngay} min={HOM_NAY}
              onChange={(e) => setNgay(e.target.value)} />
          </label>
          <fieldset className="gh-pick">
            <legend>Chọn hàng giao đợt này</legend>
            <p className="rc__sub" style={{ margin: "0 0 8px 6px" }}>
              Hàng của đơn đã được tự khai vào danh mục <strong>Thành phẩm</strong> khi chốt đơn —
              không phải chọn mặt hàng kho.
            </p>
            {gomCum(con.lines.filter((l) => l.con_phai_giao > 0))
              .map((c) => {
                // Ô của cả cụm: khoá = dòng đầu; trần = phần còn ít nhất trong các dòng của cụm.
                const l = c.dau;
                const conCum = Math.min(...c.dong.map((d) => d.con_phai_giao));
                const tich = Boolean(chon[l.order_line_id]);
                return (
                  <Fragment key={l.order_line_id}>
                  {(
                  <div className={`gh-pick__row${tich ? " is-on" : ""}`}>
                    <label className="gh-pick__tick">
                      <input
                        type="checkbox"
                        checked={tich}
                        onChange={(e) => {
                          const bat = e.target.checked;
                          setChon((p) => ({ ...p, [l.order_line_id]: bat }));
                          // Tích là điền sẵn TOÀN BỘ phần còn lại — ca hay gặp nhất. Ai muốn
                          // giao ít hơn thì sửa số, đỡ hơn bắt mọi người gõ số mỗi lần.
                          setSoLuong((p) => ({
                            ...p,
                            [l.order_line_id]: bat ? String(conCum) : "",
                          }));
                        }}
                      />
                      <span>
                        {nhanCum(c)}
                        <em> · còn {conCum} {c.donVi}</em>
                      </span>
                    </label>
                    {/* `type="number"` chứ KHÔNG phải `inputMode="numeric"`: inputMode chỉ đổi
                        bàn phím điện thoại, gõ chữ trên máy tính vẫn lọt. `max` chặn ngay tại ô
                        thay vì để máy chủ trả lỗi sau khi đã bấm Gửi. */}
                    <input
                      className="input gh-pick__qty"
                      type="number" min="1" step="1" max={conCum}
                      disabled={!tich}
                      aria-label={`Số lượng giao — ${c.ten}`}
                      value={soLuong[l.order_line_id] ?? ""}
                      onChange={(e) =>
                        setSoLuong((p) => ({ ...p, [l.order_line_id]: e.target.value }))
                      }
                    />
                  </div>
                  )}
                  </Fragment>
                );
              })}
          </fieldset>
          <label>
            Địa chỉ giao
            <input className="input" value={diaChi} placeholder="Địa chỉ nơi giao hàng..." onChange={(e) => setDiaChi(e.target.value)} />
          </label>
          <label>
            Người nhận
            <input className="input" value={nguoiNhan} placeholder="Tên người nhận hàng..."
              onChange={(e) => setNguoiNhan(e.target.value)} />
          </label>
          <label>
            SĐT người nhận
            <input className="input" value={sdt} placeholder="Số điện thoại liên hệ..." onChange={(e) => setSdt(e.target.value)} />
          </label>

          {ngayQuaKhu && (
            <div className="banner banner--error" role="alert" style={{ margin: 0 }}>
              Ngày cần giao không được ở quá khứ — hôm nay là {fmtDate(HOM_NAY)}.
            </div>
          )}
          {loi && (
            <div className="banner banner--error" role="alert" style={{ margin: 0 }}>
              {loi}
            </div>
          )}

          <div className="gh-actions">
            <Button
              variant="accent"
              disabled={
                !ngay || dangGui || ngayQuaKhu ||
                !con.lines.some((l) => chon[l.order_line_id])
              }
              onClick={gui}
            >
              Gửi yêu cầu
            </Button>
            <Button variant="ghost" onClick={() => setMo(false)}>
              Bỏ
            </Button>
          </div>
        </div>
      )}

      {ds.length > 0 && (
        <p className="rc__sub" style={{ margin: "10px 0 0" }}>
          Yêu cầu gần nhất cần giao ngày {fmtDate(ds[0].ngay_can_giao)}.
        </p>
      )}
    </section>
  );
}
