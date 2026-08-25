// Tab "Yêu cầu giao" — danh sách yêu cầu chờ lên kế hoạch (tách từ pages/GiaoHangPage.tsx).
import type { DeliveryRequest } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDate } from "../../../../utils/format";
import { KhoangTrong } from "../components/giaoHangCells";

// =============================================================================
// Tab · Yêu cầu giao
// =============================================================================
export function BangChoLenKeHoach({
  rows,
  loading,
  onMo,
  onLenKeHoach,
}: {
  rows: DeliveryRequest[];
  loading: boolean;
  onMo: (id: number) => void;
  onLenKeHoach: (r: DeliveryRequest) => void;
}) {
  if (!loading && rows.length === 0)
    return (
      <KhoangTrong
        title="Không có yêu cầu giao nào đang chờ"
        desc="Mọi yêu cầu Bán hàng gửi sang đều đã lên đơn giao hàng. Yêu cầu mới sẽ hiện ở đây ngay, không cần tải lại trang."
      />
    );
  return (
    <div className="rc__tablewrap">
      <table className="rc__table rc__table--fixed">
        <thead>
          <tr>
            <th style={{ width: "12%" }}>Mã yêu cầu</th>
            <th style={{ width: "11%" }}>Đơn hàng</th>
            <th>Khách hàng</th>
            <th style={{ width: "12%" }}>Ngày cần giao</th>
            <th style={{ width: "20%" }}>Hàng hoá</th>
            <th style={{ width: "13%" }}>Người yêu cầu</th>
            {/* Cột "Lệnh SX" GỠ 20/08/2026: bộ phận giao hàng chỉ nhận yêu cầu, sản xuất tới
                đâu là việc của xưởng. Cột chỉ-để-nhìn mà không ai quyết theo nó là cột thừa. */}
            <th style={{ width: "12%" }} />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={7}>Đang tải…</td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <button type="button" className="gh-link" onClick={() => onMo(r.id)}>
                  {r.code}
                </button>
              </td>
              <td>{r.order_code}</td>
              <td>{r.customer_name}</td>
              <td>{fmtDate(r.ngay_can_giao)}</td>
              {/* CHỈ ĐẾM, không liệt kê. Đổ cả danh sách ra đây làm dòng cao gấp ba và đẩy
                  cột Thao tác ra rìa — mà tên sản phẩm in thì dài sẵn ("Hộp thuốc 10 vỉ — in 2
                  màu, cán bóng"). Muốn xem gì thì bấm mã yêu cầu để mở chi tiết.
                  `title` để rê chuột xem nhanh — không tốn chỗ nào trên bảng. */}
              <td className="gh-nowrap" title={r.lines
                .map((l) => `${l.mo_ta ?? ""} × ${l.qty}${l.don_vi_tinh ? ` ${l.don_vi_tinh}` : ""}`)
                .join(" · ")}>
                {r.lines.length} mặt hàng
              </td>
              <td>{r.created_by_name}</td>
              <td>
                <Button variant="accent" onClick={() => onLenKeHoach(r)}>
                  Lên đơn giao hàng
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
