// Tab "Nhân viên giao hàng" — bảng tài xế theo tháng (tách từ pages/GiaoHangPage.tsx).
import type { DeliveryDriver } from "../../../../api/client";
import { NHAN_TRANG_THAI_NV } from "../shared/constants";
import { KhoangTrong, Pill } from "../components/giaoHangCells";

// =============================================================================
// Tab · Nhân viên giao hàng
// =============================================================================
export function BangNhanVien({ rows, loading, thang, onDoiThang }: {
  rows: DeliveryDriver[]; loading: boolean;
  thang: string; onDoiThang: (t: string) => void;
}) {
  // Ô chọn tháng đứng NGOÀI nhánh rỗng: hết người trong tháng này không có nghĩa là hết người —
  // ẩn ô chọn lúc đó là nhốt người dùng ở đúng cái tháng trống, không quay lại được.
  const dauBang = (
    <div className="gh-nvbar">
      <label className="gh-nvbar__thang">
        <span>Tháng</span>
        <input className="input" type="month" value={thang}
          onChange={(e) => onDoiThang(e.target.value)} />
      </label>
      <span className="rc__sub">
        Hai cột <strong>tháng này</strong> đổi theo ô trên. Cột <strong>hôm nay</strong> và trạng
        thái luôn là hiện tại.
      </span>
    </div>
  );

  if (!loading && rows.length === 0)
    return (
      <>
        {dauBang}
        <KhoangTrong
          title="Chưa có nhân viên giao hàng nào"
          desc="Bảng liệt kê người thuộc Bộ phận Giao hàng (bật ở màn Phòng ban), cộng người đã được phân chuyến."
        />
      </>
    );
  return (
    // Dải chọn tháng đứng NGOÀI `.rc__tablewrap`: thẻ đó có viền + `overflow-x: auto`, để ô chọn
    // vào trong là nó nằm trong khung bảng và trôi ngang theo bảng khi màn hẹp.
    <>
      {dauBang}
      <div className="rc__tablewrap">
        <table className="rc__table rc__table--fixed">
        <thead>
          <tr>
            <th>Nhân viên</th>
            <th style={{ width: "14%" }}>Trạng thái</th>
            <th style={{ width: "16%" }}>Đang thực hiện</th>
            <th style={{ width: "16%" }}>Chuyến kế tiếp</th>
            {/* Bốn cột SỐ đều căn phải — trộn trái/phải thì mắt phải nhảy qua nhảy lại để
                so hàng, và các số nhiều chữ số trông như lệch cột. */}
            {/* "Xong hôm nay" đổi thành "Đã giao hôm nay" (chủ 21/08/2026: "nhìn vào người ta
                không hiểu đâu") — "xong" không nói xong CÁI GÌ. Đếm số CHUYẾN hàng tới tay
                khách, tính cả chuyến giao thiếu. */}
            <th className="gh-num" style={{ width: "10%" }}>Đã giao hôm nay</th>
            <th className="gh-num" style={{ width: "10%" }}>Km hôm nay</th>
            {/* Hai khung thời gian, hai câu hỏi khác nhau: cột NGÀY để điều độ ("giờ ai đang
                rảnh"), cột THÁNG để theo dõi định kỳ. Gộp một cột là mất một trong hai. */}
            <th className="gh-num" style={{ width: "10%" }}>Đã giao tháng này</th>
            <th className="gh-num" style={{ width: "10%" }}>Km tháng này</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={8}>Đang tải…</td>
            </tr>
          )}
          {rows.map((d) => (
            <tr key={d.employee_id}>
              <td>{d.ho_ten}</td>
              <td>
                <Pill
                  text={NHAN_TRANG_THAI_NV[d.trang_thai] ?? d.trang_thai}
                  tone={d.trang_thai === "ranh" ? "on" : d.trang_thai === "nghi" ? "off" : "warn"}
                />
              </td>
              <td>{d.chuyen_dang_thuc_hien ?? "—"}</td>
              <td>{d.chuyen_ke_tiep ?? "—"}</td>
              <td className="gh-num">{d.so_chuyen_xong}</td>
              {/* Số km CHỈ ĐỂ THỐNG KÊ — không vào lương (PRD quyết định #3). */}
              <td className="gh-num">{d.tong_km}</td>
              <td className="gh-num">{d.so_chuyen_thang ?? 0}</td>
              <td className="gh-num">{d.tong_km_thang ?? 0}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </>
  );
}
