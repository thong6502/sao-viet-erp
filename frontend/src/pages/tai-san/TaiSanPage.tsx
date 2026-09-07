// Màn TÀI SẢN CỐ ĐỊNH & CÔNG CỤ DỤNG CỤ (kế toán).
//
// Phạm vi CỐ Ý HẸP: ghi tăng · trích khấu hao theo kỳ · ba chứng từ biến động · kiểm kê. Không
// định khoản, không sổ cái, không nhóm tài sản khai sẵn. Cầu nối duy nhất sang phần mềm kế toán
// là ô "Ghi chú hạch toán" tự gõ + file Excel bảng khấu hao.
import { DanhSachView } from "./DanhSachView";
import "../rebuild-catalog.css";
import "./tai-san.css";

export function TaiSanPage() {
  return (
    <div className="rc ts">
      <div className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">Tài sản & Công cụ dụng cụ</h1>
        </div>
        <p className="rc__sub">
          Sổ những thứ xưởng mua về dùng nhiều năm: máy in, máy dao, tấm cao su, khuôn bế. Ghi
          tăng một lần rồi mỗi tháng trích một phần vào chi phí.
        </p>
      </div>

      <DanhSachView />
    </div>
  );
}
