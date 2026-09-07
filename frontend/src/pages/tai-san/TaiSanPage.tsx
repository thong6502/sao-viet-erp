// Màn TÀI SẢN CỐ ĐỊNH & CÔNG CỤ DỤNG CỤ (kế toán).
//
// Phạm vi CỐ Ý HẸP: ghi tăng · trích khấu hao theo kỳ · ba chứng từ biến động · kiểm kê. Không
// định khoản, không sổ cái, không nhóm tài sản khai sẵn. Cầu nối duy nhất sang phần mềm kế toán
// là ô "Ghi chú hạch toán" tự gõ + file Excel bảng khấu hao.
//
// MỘT màn ba tab chứ không ba mục menu: cả ba đọc cùng một sổ, và người làm việc này đi qua lại
// giữa chúng trong cùng một buổi (ghi tăng xong là tính lại kỳ; kiểm kê xong là ghi giảm).
import { useState } from "react";
import { DanhSachView } from "./DanhSachView";
import { KhauHaoKyView } from "./KhauHaoKyView";
import "../rebuild-catalog.css";
import "./tai-san.css";

type Tab = "so" | "ky";

export function TaiSanPage() {
  const [tab, setTab] = useState<Tab>("so");

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

      <div className="rc__tabs">
        <button className={`rc__tab${tab === "so" ? " is-active" : ""}`}
          onClick={() => setTab("so")}>
          Danh sách
        </button>
        <button className={`rc__tab${tab === "ky" ? " is-active" : ""}`}
          onClick={() => setTab("ky")}>
          Khấu hao theo kỳ
        </button>
      </div>

      {tab === "so" ? <DanhSachView /> : <KhauHaoKyView />}
    </div>
  );
}
