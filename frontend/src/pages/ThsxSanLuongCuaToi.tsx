// Băng "CÁC MẺ TÔI THAM GIA" — chỉ hiện cho THỢ (spec 2026-09-18 §7.5, thay băng "Sản lượng của
// tôi" của 2026-09-11 §6).
//
// Thợ xem lại tháng này mình đã có mặt ở những mẻ nào để đối chiếu với kế toán: ngày · lệnh · công
// đoạn · việc khoán · sản lượng của CẢ MẺ · danh sách người. Không có "phần của tôi", không số phút
// của ai, không ô tiền — tầng chia sản lượng đã gỡ (mg 0322), hệ không bịa ra con số không ai quyết.
import { Fragment, useState } from "react";
import type { SxSanLuongCuaToi } from "../api/client";
import { Icon } from "../components/Icons";
import { gioNgan, num } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";

function ngayNgan(v: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "—"
    : `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function ThsxSanLuongCuaToi({ data }: { data: SxSanLuongCuaToi | null }) {
  const [mo, setMo] = useState(false);
  // Chưa nạp xong thì KHÔNG vẽ băng rỗng: một khung xám nhấp nháy rồi mới có số đọc thành lỗi.
  if (!data) return null;
  const co = data.me.length > 0;
  return (
    <section className="thsx-slt" aria-label="Các mẻ tôi tham gia">
      <div className="thsx-slt__dau">
        <span className="thsx-slt__nhan">Các mẻ tôi tham gia · tháng {data.thang}/{data.nam}</span>
        {co ? (
          <button type="button" className="thsx-slt__mo" aria-expanded={mo} onClick={() => setMo((x) => !x)}>
            <span className="thsx-num">{data.so_me} mẻ</span>
            <Icon name="chevron" size={12} className={mo ? "" : "thsx-rot-90"} />
          </button>
        ) : (
          <span className="thsx-slt__trong">Tháng này bạn chưa có mặt ở mẻ nào.</span>
        )}
      </div>
      {co && mo && (
        <ul className="thsx-slt__ds">
          {data.me.map((m) => (
            <li key={m.batch_id} className="thsx-slt__me">
              <div className="thsx-slt__d1">
                <span className="thsx-num">{ngayNgan(m.bat_dau)} {gioNgan(m.bat_dau)}</span>
                {m.lsx_ma && <b>{m.lsx_ma}</b>}
                <span>{m.ten_cong_doan}</span>
              </div>
              <div className="thsx-slt__d2">
                <span>{m.viec_khoan_ten ?? "— chưa khai việc khoán"}</span>
                <span>
                  · mẻ <b className="thsx-num">{num(m.tot)}</b>{m.don_vi ? ` ${nhanDonVi(m.don_vi)}` : ""}
                  {m.hong > 0 && <> · hỏng <span className="thsx-num">{num(m.hong)}</span></>}
                </span>
              </div>
              <div className="thsx-slt__d3">
                Người:{" "}
                {m.nguoi_tham_gia.map((n, i) => (
                  <Fragment key={n.employee_id}>
                    {i > 0 && " · "}
                    {n.employee_id === data.employee_id ? <b>tôi</b> : n.ho_ten}
                    {n.to_ten && <span className="thsx-slt__to"> ({n.to_ten})</span>}
                  </Fragment>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
