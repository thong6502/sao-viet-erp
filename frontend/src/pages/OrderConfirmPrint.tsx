// Phiếu XÁC NHẬN ĐƠN HÀNG (gửi khách) — CÓ giá, CÓ cọc, KHÔNG MST, KHÔNG lộ cost/margin.
// Data lấy trực tiếp từ OrderDetail đã fetch ở màn Đơn hàng bán.
import { PrintSheet } from "../components/PrintSheet";
import type { OrderDetail } from "../api/client";

const money = (n: number | null | undefined): string => Math.round(n || 0).toLocaleString("vi-VN");

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function OrderConfirmPrint({
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
  const remaining = Math.max(0, (d.total_with_vat ?? 0) - (d.deposit_received ?? 0));

  return (
    <PrintSheet
      title="XÁC NHẬN ĐƠN HÀNG"
      docNo={d.order_no}
      docDate={fmtDate(d.created_at)}
      onClose={onClose}
      canPrint={canPrint}
    >
      {/* Thông tin đơn */}
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
          {d.customer_po_no ? (
            <div>
              <span className="ps-lbl">PO khách: </span>
              {d.customer_po_no}
            </div>
          ) : null}
          {d.delivery_address ? (
            <div>
              <span className="ps-lbl">Địa chỉ giao: </span>
              {d.delivery_address}
            </div>
          ) : null}
          {d.quotation_code ? (
            <div>
              <span className="ps-lbl">Báo giá nguồn: </span>
              {d.quotation_code}
            </div>
          ) : null}
          {d.delivery_contact_name || d.delivery_contact_phone ? (
            <div>
              <span className="ps-lbl">Người nhận: </span>
              {[d.delivery_contact_name, d.delivery_contact_phone].filter(Boolean).join(" · ")}
            </div>
          ) : null}
        </div>
      </div>

      {/* Chi tiết đơn hàng */}
      <div className="ps-sec">Chi tiết đơn hàng</div>
      <table className="ps-tbl">
        <colgroup>
          <col style={{ width: "6%" }} />
          <col style={{ width: "34%" }} />
          <col style={{ width: "9%" }} />
          <col style={{ width: "11%" }} />
          <col style={{ width: "15%" }} />
          <col style={{ width: "8%" }} />
          <col style={{ width: "17%" }} />
        </colgroup>
        <thead>
          <tr>
            <th>STT</th>
            <th>Mô tả sản phẩm</th>
            <th>ĐVT</th>
            <th>Số lượng</th>
            <th>Đơn giá (chưa VAT)</th>
            <th>VAT</th>
            <th>Thành tiền (chưa VAT)</th>
          </tr>
        </thead>
        <tbody>
          {d.lines.map((l, i) => (
            <tr key={l.id}>
              <td className="c">{i + 1}</td>
              <td>{l.description}</td>
              <td className="c">{l.don_vi_tinh}</td>
              <td className="c">{l.qty.toLocaleString("vi-VN")}</td>
              <td className="r">{money(l.unit_price_snapshot)}</td>
              <td className="c">{l.vat_pct_estimate}%</td>
              <td className="r">{money(l.line_total)}</td>
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

      {/* Tổng thanh toán */}
      <div className="ps-grand">
        <div className="ps-gt">
          Tổng thanh toán
          <div className="ps-gs">đã gồm VAT</div>
        </div>
        <div className="ps-ga">
          {money(d.total_with_vat)}
          <span className="ps-u">đ</span>
        </div>
      </div>

      {/* Cọc */}
      <div className="ps-deposit">
        <div>
          <span className="ps-lbl">Cọc yêu cầu</span>
          <b>{money(d.deposit_required)} đ</b>
        </div>
        <div>
          <span className="ps-lbl">Đã cọc</span>
          <b>{money(d.deposit_received)} đ</b>
        </div>
        <div>
          <span className="ps-lbl">Còn phải trả</span>
          <b>{money(remaining)} đ</b>
        </div>
      </div>

      {/* Chữ ký */}
      <div className="ps-signs">
        <div>
          <div className="ps-role">Khách hàng</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
        <div>
          <div className="ps-role">Đại diện bên bán</div>
          <div className="ps-hint">(Ký, ghi rõ họ tên)</div>
          <div className="ps-sp" />
        </div>
      </div>
    </PrintSheet>
  );
}
