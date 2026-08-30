// Tab "Đơn giao hàng" — bảng chuyến gộp theo yêu cầu + cụm nút thao tác từng chuyến
// (tách từ pages/GiaoHangPage.tsx).
import type { DeliveryTrip } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDateTime } from "../../../../utils/format";
import { nhanChuyen, toneChuyen } from "../shared/helpers";
import { KhoangTrong, Pill } from "../components/giaoHangCells";

// =============================================================================
// Tab · Đơn giao hàng
// =============================================================================
export function BangKeHoach({
  trips,
  loading,
  onMo,
  onGuiDeNghi,
  onDaLay,
  onBatDau,
  onKetQua,
  onDaTra,
}: {
  trips: DeliveryTrip[];
  loading: boolean;
  onMo: (requestId: number) => void;
  onGuiDeNghi?: (t: DeliveryTrip) => void;
  onDaLay?: (t: DeliveryTrip) => void;
  onBatDau?: (t: DeliveryTrip) => void;
  onKetQua?: (t: DeliveryTrip) => void;
  onDaTra?: (t: DeliveryTrip) => void;
}) {
  if (!loading && trips.length === 0)
    return (
      <KhoangTrong
        title="Chưa có đơn giao hàng nào"
        desc="Đơn giao hàng sinh ra khi quản lý phân công tài xế cho một yêu cầu giao. Yêu cầu thì Bán hàng lập từ màn Đơn hàng bán, ở khối “Giao hàng” cuối trang đơn đã chốt."
      />
    );
  return (
    <div className="rc__tablewrap">
      <table className="rc__table rc__table--fixed">
        <thead>
          <tr>
            <th style={{ width: "11%" }}>Yêu cầu</th>
            <th style={{ width: "9%" }}>Đơn hàng</th>
            {/* Khách hàng KHÔNG khai bề ngang — nó ăn phần còn lại. Trước đây 8 cột kia cộng
                lại 92% nên tên khách bị ép xuống 8%, gãy làm hai dòng. */}
            <th>Khách hàng</th>
            <th style={{ width: "12%" }}>Nhân viên giao</th>
            <th style={{ width: "12%" }}>Giờ lấy hàng</th>
            <th style={{ width: "12%" }}>Dự kiến giao</th>
            <th style={{ width: "13%" }}>Trạng thái</th>
            {/* TỔNG km cả các lần giao của yêu cầu — không phải km của riêng lần cuối. */}
            <th style={{ width: "6%" }}>Tổng km</th>
            <th style={{ width: "11%" }} />
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={9}>Đang tải…</td>
            </tr>
          )}
          {trips.map((t) => (
            <tr key={t.request_id}>
              <td>
                <button type="button" className="gh-link" onClick={() => onMo(t.request_id)}>
                  {t.request_code}
                </button>
              </td>
              <td>{t.order_code}</td>
              <td>{t.customer_name}</td>
              <td>{t.employee_name}</td>
              <td className="gh-nowrap">{fmtDateTime(t.gio_lay_hang)}</td>
              <td className="gh-nowrap">{fmtDateTime(t.gio_du_kien_giao)}</td>
              {/* `gh-nowrap`: "Kho đã chuẩn bị xong" dài hơn nhãn cũ nên cột hẹp bẻ nó xuống
                  hai dòng giữa chữ, viên pill vỡ làm đôi. */}
              <td className="gh-nowrap">
                <Pill
                  text={nhanChuyen(t)}
                  tone={toneChuyen(t.trang_thai)}
                />
              </td>
              <td className="gh-num">{t.tong_km || "—"}</td>
              <td>
                {/* Hàng ra khỏi kho phải có phiếu kho — giao khách không ngoại lệ. Nút này
                    lập một YÊU CẦU XUẤT KHO thật, kho lập phiếu bằng luồng sẵn có. */}
                {t.trang_thai === "da_len_ke_hoach" && !t.yeu_cau_kho_ma && onGuiDeNghi && (
                  <Button variant="accent" onClick={() => onGuiDeNghi(t)}>
                    Gửi yêu cầu xuất kho
                  </Button>
                )}
                {/* Mã yêu cầu kho (DNX…) KHÔNG hiện ở cột Thao tác — nó không phải thao tác,
                    không có nhãn, và đứng cạnh nút thì trông như một nút hỏng (bỏ 20/08/2026).
                    Mã vẫn còn ở chi tiết yêu cầu, chỗ có ngữ cảnh để đọc. */}
                {/* Tài xế TỰ bấm — người cầm hàng mới biết hàng đã ra khỏi kho. */}
                {t.trang_thai === "dang_chuan_bi" && onDaLay && (
                  <Button variant="accent" onClick={() => onDaLay(t)}>
                    Đã lấy hàng
                  </Button>
                )}
                {t.trang_thai === "da_lay_hang" && onBatDau && (
                  <Button variant="ghost" onClick={() => onBatDau(t)}>
                    Bắt đầu giao
                  </Button>
                )}
                {t.trang_thai === "dang_giao" && onKetQua && (
                  <Button variant="accent" onClick={() => onKetQua(t)}>
                    Nhập kết quả
                  </Button>
                )}
                {/* Thiếu nút này thì chuyến giao hỏng nằm mãi ở "Đang trả hàng": API có, giao
                    diện quên — chuyến tắc mà không ai biết vì sao. */}
                {t.trang_thai === "dang_tra_hang" && onDaTra && (
                  <Button variant="ghost" onClick={() => onDaTra(t)}>
                    Kho đã nhận lại
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
