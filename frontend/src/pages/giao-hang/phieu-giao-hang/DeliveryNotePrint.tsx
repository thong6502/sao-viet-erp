// Phiếu GIAO HÀNG (đi kèm hàng lúc giao, người nhận ký nhận) — GIỮ giá/VAT/tổng như tờ xác nhận
// (kiêm chứng từ đối chiếu tiền), KHÔNG lộ MST/cost/margin. Ngày giao chừa TRỐNG để ghi tay; số
// phiếu mượn số đơn (chưa có sổ cấp số phiếu giao riêng — đó là module giao hàng làm sau).
// Data lấy trực tiếp từ OrderDetail đã fetch ở màn Đơn hàng bán.
// (tách từ pages/DeliveryNotePrint.tsx).
import { PrintSheet } from "../../../components/PrintSheet";
import { gopTheoNhom } from "../../../utils/gop-nhom";
import type { OrderDetail } from "../../../api/client";

const money = (n: number | null | undefined): string => Math.round(n || 0).toLocaleString("vi-VN");
// Đơn giá KHÔNG làm tròn: dòng gộp (ruột + bìa) hay ra số lẻ .5 — làm tròn xong khách nhân
// Số lượng × Đơn giá ra khác Thành tiền. Giữ tối đa 2 số lẻ để phép nhân trên giấy luôn khớp.
function donGia(n: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

/** dd/mm/yyyy — `toLocaleDateString("vi-VN")` trả "9/8/2026", thiếu số 0 nên hai ngày trên cùng
 *  tờ nhìn so le. Chứng từ gửi khách phải một khuôn ngày duy nhất. */
function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (isNaN(d.getTime())) return "—";
  const p2 = (n: number) => (n < 10 ? "0" : "") + n;
  return `${p2(d.getDate())}/${p2(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function DeliveryNotePrint({
  d,
  onClose,
  canPrint,
}: {
  d: OrderDetail;
  onClose: () => void;
  canPrint?: boolean;
}) {
  const total = d.total ?? 0;
  const vat = Math.max(0, (d.total_with_vat ?? 0) - total);
  // Gộp dòng cùng nhãn `nhom` y như bản báo giá → tờ giao khớp "quyển sách" (ruột + bìa gộp), đúng
  // thứ giao tận tay chứ không phải linh kiện rời. Đơn bên trong vẫn giữ từng dòng để sinh LSX riêng.
  const dongGop = gopTheoNhom(d.lines, (l) => ({
    nhom: l.nhom,
    ten: l.description,
    soLuong: l.qty,
    donViTinh: l.don_vi_tinh,
    thanhTien: l.line_total ?? 0,
    tienVat: Math.round(((l.line_total ?? 0) * (l.vat_pct_estimate || 0)) / 100),
    vatPct: l.vat_pct_estimate,
  }));
  const remaining = Math.max(0, (d.total_with_vat ?? 0) - (d.deposit_received ?? 0));

  return (
    <PrintSheet
      title="PHIẾU GIAO HÀNG"
      docNo={d.order_no}
      onClose={onClose}
      canPrint={canPrint}
    >
      {/* Thông tin giao — người nhận / địa chỉ lên đầu vì đây là thứ người cầm hàng cần nhất */}
      <div className="ps-info">
        <div className="ps-info-grid">
          <div>
            <span className="ps-lbl">Khách hàng: </span>
            <b>{d.customer_name ?? "—"}</b>
          </div>
          <div>
            <span className="ps-lbl">Hạn giao: </span>
            <b>{fmtDate(d.delivery_committed_date)}</b>
          </div>
          {d.delivery_contact_name || d.delivery_contact_phone ? (
            <div>
              <span className="ps-lbl">Người nhận: </span>
              {[d.delivery_contact_name, d.delivery_contact_phone].filter(Boolean).join(" · ")}
            </div>
          ) : null}
          {d.delivery_address ? (
            <div>
              <span className="ps-lbl">Địa chỉ giao: </span>
              {d.delivery_address}
            </div>
          ) : null}
          {d.customer_po_no ? (
            <div>
              <span className="ps-lbl">PO khách: </span>
              {d.customer_po_no}
            </div>
          ) : null}
          {/* Ngày giao THỰC chừa trống để người giao/nhận điền tay (ngày giao hay lệch hạn cam kết). */}
          <div>
            <span className="ps-lbl">Ngày giao: </span>
            <span className="ps-blank">&nbsp;</span>
          </div>
        </div>
      </div>

      {/* Chi tiết hàng giao */}
      <div className="ps-sec">Chi tiết hàng giao</div>
      <table className="ps-tbl">
        <colgroup>
          <col style={{ width: "6%" }} />
          <col style={{ width: "35%" }} />
          <col style={{ width: "7%" }} />
          <col style={{ width: "12%" }} />
          {/* Đơn giá phải chứa được số có phần thập phân ("120.257,4") mà không ngắt dòng. */}
          <col style={{ width: "17%" }} />
          <col style={{ width: "6%" }} />
          <col style={{ width: "17%" }} />
        </colgroup>
        <thead>
          <tr>
            <th>STT</th>
            <th>Mô tả sản phẩm</th>
            <th>ĐVT</th>
            {/* Cột số căn PHẢI cả nhãn lẫn giá trị — chữ số thẳng cột với nhãn của chính nó. */}
            <th className="r">SL giao</th>
            <th className="r">Đơn giá<span className="ps-sub">chưa VAT</span></th>
            <th>VAT</th>
            <th className="r">Thành tiền<span className="ps-sub">chưa VAT</span></th>
          </tr>
        </thead>
        <tbody>
          {dongGop.length === 0 && (
            <tr>
              <td className="c ps-empty" colSpan={7}>Đơn hàng chưa có dòng sản phẩm nào.</td>
            </tr>
          )}
          {dongGop.map((g, i) => (
            <tr key={g.key}>
              <td className="c">{i + 1}</td>
              <td className="ps-desc">{g.ten}</td>
              <td className="c">{g.donViTinh}</td>
              <td className="r">{g.soLuong.toLocaleString("vi-VN")}</td>
              <td className="r">{donGia(g.soLuong > 0 ? g.thanhTien / g.soLuong : g.thanhTien)}</td>
              <td className="c">{g.vatPct === null ? "—" : `${g.vatPct}%`}</td>
              <td className="r">{money(g.thanhTien)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="ps-sub-lbl" colSpan={6}>
              Cộng tiền hàng (chưa VAT)
            </td>
            <td className="r">{money(total)}</td>
          </tr>
          <tr>
            <td className="ps-sub-lbl" colSpan={6}>
              Thuế GTGT
            </td>
            <td className="r">{money(vat)}</td>
          </tr>
        </tfoot>
      </table>

      {/* Tổng giá trị lô giao */}
      <div className="ps-grand">
        <div className="ps-gt">
          Tổng giá trị
          <div className="ps-gs">đã gồm VAT</div>
        </div>
        <div className="ps-ga">
          {money(d.total_with_vat)}
          <span className="ps-u">đ</span>
        </div>
      </div>

      {/* Thanh toán — lúc nhận hàng người ta cần biết còn nợ bao nhiêu */}
      <div className="ps-pay">
        <div>
          <span className="ps-lbl">Đã thanh toán</span>
          <b>{money(d.deposit_received)} đ</b>
        </div>
        <div>
          <span className="ps-lbl">Còn phải trả</span>
          <b>{money(remaining)} đ</b>
        </div>
      </div>

      {/* Biên nhận: ai giao · ai nhận · ai lập — đây là dấu vết giao hàng (POD) */}
      <div className="ps-signs ps-signs--3">
        <div>
          <div className="ps-role">Người giao hàng</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
        <div>
          <div className="ps-role">Người nhận hàng</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
        <div>
          <div className="ps-role">Người lập phiếu</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
      </div>
    </PrintSheet>
  );
}
