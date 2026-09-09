// Màn TÀI SẢN CỐ ĐỊNH & CÔNG CỤ DỤNG CỤ (kế toán).
//
// Phạm vi CỐ Ý HẸP (chủ 08/09/2026: "nó chỉ theo dõi khấu hao thôi"): ghi tăng · bảng khấu hao
// từng tháng · hai chứng từ biến động (điều chuyển · sửa chữa lớn) · xoá món không dùng nữa.
// Không định khoản, không sổ cái, không nhóm tài sản khai sẵn, không kỳ chốt, không ghi giảm,
// không kiểm kê. Cầu nối sang phần mềm kế toán là file Excel bảng khấu hao — người ta đọc rồi
// tự gõ; muốn nhớ định khoản thì ghi vào ô ghi chú.
//
// MỘT màn hai tab chứ không hai mục menu: cả hai đọc cùng một sổ, và người làm việc này đi qua
// lại giữa chúng trong cùng một buổi (ghi tăng xong là xem bảng tháng).
import { useState } from "react";
import { DanhSachView } from "./DanhSachView";
import { KhauHaoThangView } from "./KhauHaoThangView";
import "../rebuild-catalog.css";
import "./tai-san.css";

type Tab = "so" | "thang";

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
        <button className={`rc__tab${tab === "thang" ? " is-active" : ""}`}
          onClick={() => setTab("thang")}>
          Bảng khấu hao tháng
        </button>
      </div>

      {tab === "so" && <DanhSachView />}
      {tab === "thang" && <KhauHaoThangView />}
    </div>
  );
}
