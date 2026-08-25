// Bảng đối chiếu khoán km của một dòng lương (tách từ pages/LuongPage.tsx).
import { useEffect, useState } from "react";
import {
  api,
  type KhoanKmChiTiet,
  type PayrollLine,
  type PayrollPeriod,
} from "../../../../api/client";
import { money } from "../shared/helpers";

/** Bảng đối chiếu KHOÁN KM của một dòng lương — HCNS bấm số ở cột "Khoán km" để mở.
 *
 * ⭐ Vì sao bắt buộc có: km là **tài xế tự gõ**. Hoa hồng thì nguồn là hoá đơn kế toán đã xuất,
 * đã qua tay người khác; km thì không ai kiểm giữa chừng. Không cho soi lại từng chuyến thì khoán
 * km thành tiền tự khai, và cuối tháng không đối chiếu được với sổ tài xế.
 *
 * CHỈ XEM, không sửa: cái gì máy tự tính thì đừng phơi thành ô gõ tay. Sai km ⇒ sửa ở chuyến giao
 * rồi tính lại — chữa đúng gốc, không nắn ngọn.
 */
export function SoiKhoanKm({
  token,
  line,
  period,
  onClose,
}: {
  token: string;
  line: PayrollLine;
  period: PayrollPeriod;
  onClose: () => void;
}) {
  const [data, setData] = useState<KhoanKmChiTiet | null>(null);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    let huy = false;
    api.luong
      .chiTietKhoanKm(token, line.id)
      .then((r) => !huy && setData(r))
      .catch((e: unknown) =>
        !huy && setLoi(e instanceof Error ? e.message : "Không tải được chi tiết"),
      );
    return () => {
      huy = true;
    };
  }, [token, line.id]);

  // Tổng bảng chi tiết PHẢI khớp cột trên bảng lương. Lệch nghĩa là một trong hai bên tính sai —
  // nói thẳng ra chứ đừng để HCNS tự phát hiện khi đối chiếu với kế toán.
  const lech = data != null && Math.abs(data.tong - (line.khoan_km ?? 0)) > 1;

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>
            Khoán km — {line.employee_name}
            <span className="lg-soikm__ky">
              {" "}
              kỳ {String(period.month).padStart(2, "0")}/{period.year}
            </span>
          </h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {loi && <div className="banner banner--error">{loi}</div>}
          {lech && (
            <div className="banner banner--warn" role="status">
              Tổng chi tiết ({money(data!.tong)}) khác cột Khoán km trên bảng lương (
              {money(line.khoan_km ?? 0)}) — bấm <b>Tính lại</b> để đồng bộ.
            </div>
          )}
          {data == null && !loi && <p className="cc-note">Đang tải chi tiết…</p>}
          {data != null && data.items.length === 0 && (
            <p className="cc-note">Kỳ này không có chuyến giao nào sinh ra tiền km.</p>
          )}
          {data != null && data.items.length > 0 && (
            <div className="ns__tablewrap">
              <table className="ns__table lg-soikm">
                <thead>
                  <tr>
                    <th>Ngày</th>
                    <th>Chuyến</th>
                    <th>Vai trò</th>
                    <th className="lg-num">Km</th>
                    <th className="lg-num">Đơn giá</th>
                    <th className="lg-num">Phần hưởng</th>
                    <th className="lg-num">Thành tiền</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c) => (
                    <tr key={c.trip_id}>
                      <td>{c.ngay ? new Date(c.ngay).toLocaleDateString("vi-VN") : "—"}</td>
                      <td>#{c.trip_id}</td>
                      <td>
                        <span
                          className={`ns-badge ${
                            c.vai_tro === "tai_xe" ? "ns-badge--info" : "ns-badge--muted"
                          }`}
                        >
                          {c.vai_tro === "tai_xe" ? "Tài xế" : "Phụ xe"}
                        </span>
                      </td>
                      <td className="lg-num">{c.km}</td>
                      <td className="lg-num">{money(c.don_gia_km)}</td>
                      {/* 100% = đi một mình. Không hiện cột này thì hai chuyến cùng km mà tiền
                          khác nhau, HCNS không hiểu vì sao. */}
                      <td className="lg-num">{c.pct}%</td>
                      <td className="lg-num">{money(c.thanh_tien)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="lg-foot">
                    <td colSpan={3}>Cộng {data.items.length} chuyến</td>
                    <td className="lg-num">
                      {data.items.reduce((s, c) => s + c.km, 0)}
                    </td>
                    <td colSpan={2} />
                    <td className="lg-num">{money(data.tong)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
          <p className="cc-note">
            Số này <b>máy tự tính</b> theo km từng chuyến — không sửa ở đây được. Sai km thì sửa ở{" "}
            <b>Giao hàng → chuyến đó</b> rồi bấm <b>Tính lại</b>.
          </p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}
