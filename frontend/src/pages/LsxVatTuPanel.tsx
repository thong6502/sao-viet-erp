// Tab "Vật tư" của màn chi tiết lệnh — bảng kê NVL · vật tư · dụng cụ, GOM THEO TỪNG CÔNG ĐOẠN.
//
// Vì sao gom theo công đoạn chứ không theo loại vật tư: câu người lập lệnh hỏi ở đây là "bước này
// ăn gì", đi dọc chuỗi đúng thứ tự chạy. Câu "mua bao nhiêu" thì gom theo món — nằm ở khối TỔNG
// GOM cuối bảng, và đó cũng là chỗ nối sang màn Kế hoạch vật tư.
//
// Màn này CHỈ NÓI CẦN. Không tồn, không thiếu, không "phải mua" — ba thứ đó phải trừ tồn + hàng
// đang về + phần kho đã cấp, mà màn lệnh không biết và không nên biết. Hai chỗ cùng tính tồn thì
// sớm muộn lệch nhau, lúc lệch không biết tin bên nào.
import { Icon } from "../components/Icons";
import { num } from "./keHoachSxShared";
import type { BangKeVatTu, DongKe, NhomVatTu } from "./lsxVatTu";

const ICON: Record<NhomVatTu, "layers" | "box" | "scissors"> = {
  nvl: "layers",
  vat_tu: "box",
  dung_cu: "scissors",
};

/** Nhãn tình trạng khuôn — cùng bộ mã với danh mục Khuôn. Mã lạ thì hiện mã trần, không nuốt. */
const TINH_TRANG: Record<string, string> = {
  dang_dung: "đang dùng",
  dang_dat_lam: "đang đặt làm",
  hong: "hỏng",
  thanh_ly: "đã thanh lý",
};

function soLuongChu(d: Pick<DongKe, "so_luong" | "don_vi">): string {
  if (d.so_luong == null) return "";
  return `${num(d.so_luong)}${d.don_vi ? ` ${d.don_vi}` : ""}`;
}

function DongMon({ d, buocs }: { d: DongKe; buocs?: number[] }) {
  const chu =
    d.nhom === "dung_cu" && d.chu_thich
      ? (TINH_TRANG[d.chu_thich] ?? d.chu_thich)
      : d.chu_thich;
  return (
    <div className={`khsx-vtke-mon khsx-vtke-mon--${d.nhom}`}>
      <span className="khsx-vtke-mon__ico" aria-hidden="true">
        <Icon name={ICON[d.nhom]} size={13} />
      </span>
      <span className="khsx-vtke-mon__ten">
        {d.ma && <span className="khsx-vtke-mon__ma">{d.ma}</span>}
        {d.ten}
      </span>
      <span className="khsx-vtke-mon__so">{soLuongChu(d)}</span>
      <span className="khsx-vtke-mon__phu">
        {chu}
        {buocs && buocs.length > 0 && (
          <span className={`khsx-vtke-mon__buoc${buocs.length > 1 ? " is-nhieu" : ""}`}>
            {buocs.map((b) => `#${b}`).join(" · ")}
          </span>
        )}
      </span>
    </div>
  );
}

/** `ke` tính SẴN ở màn cha (một lần cho cả ô tóm tắt trên đầu màn lẫn bảng này) — panel chỉ vẽ. */
export function LsxVatTuPanel({ ke }: { ke: BangKeVatTu }) {
  if (ke.buocs.length === 0) {
    return <p className="khsx-muted">Lệnh chưa có công đoạn nào — khai công đoạn trước đã.</p>;
  }

  return (
    <div className="khsx-vtke">
      <div className="khsx-vtke__tomtat">
        <span className="khsx-vtke__tomtat-chinh">
          {ke.so_mon > 0 ? `${num(ke.so_mon)} món` : "Chưa khai món nào"}
        </span>
        {ke.so_buoc_trong > 0 && (
          <span className="khsx-vtke__tomtat-phu">
            {ke.so_buoc_trong}/{ke.buocs.length} bước không khai vật tư
          </span>
        )}
        {ke.so_buoc_chua_dau_viec > 0 && (
          <span className="khsx-vtke__tomtat-phu">
            {ke.so_buoc_chua_dau_viec} bước chưa chọn đầu việc
          </span>
        )}
      </div>

      <ol className="khsx-vtke__ds">
        {ke.buocs.map((b) => (
          <li className="khsx-vtke__buoc" key={b.id}>
            <span className="khsx-vtke__stt">#{b.thu_tu}</span>
            <div className="khsx-vtke__than">
              <div className="khsx-vtke__dau">
                <span className="khsx-vtke__ten">{b.ten}</span>
                {b.to && <span className="khsx-vtke__no">{b.to}</span>}
                {b.may && <span className="khsx-vtke__no">{b.may}</span>}
                {b.dau_viec ? (
                  <span className="khsx-vtke__dv">{b.dau_viec}</span>
                ) : (
                  <span className="khsx-vtke__dv khsx-vtke__dv--trong">chưa chọn đầu việc</span>
                )}
              </div>

              <div className="khsx-vtke__luong">
                {num(b.sl_vao)} {b.dv_vao} <span aria-hidden="true">→</span> {num(b.sl_ra)} {b.dv_ra}
                {!b.tren_dong_giay && (
                  // Bước đo bằng thước RIÊNG của nó (ghi kẽm đếm bản in). Số vào/ra ở đây không nối
                  // với bước liền trước — không nói ra thì người đọc tưởng chuyền bị đứt.
                  <span
                    className="khsx-vtke__ngoai"
                    title="Bước này đo bằng đơn vị riêng, không nằm trên dòng giấy — số vào/ra không nối với bước liền kề."
                  >
                    ngoài dòng giấy
                  </span>
                )}
              </div>

              {b.dong.length > 0 ? (
                <div className="khsx-vtke__mons">
                  {b.dong.map((m) => (
                    <DongMon d={m} key={`${b.id}-${m.khoa}`} />
                  ))}
                </div>
              ) : (
                <p className="khsx-vtke__trong">Không khai vật tư</p>
              )}

              {b.thieu_khuon && (
                <p className="khsx-vtke__thieu">
                  <Icon name="alert" size={12} /> Công đoạn này cần khuôn nhưng lệnh chưa gán con nào.
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>

      <div className="khsx-vtke__tong">
        <h5 className="khsx-vtke__tong-tieu">Tổng gom — lệnh này cần</h5>
        {ke.tong.length === 0 ? (
          <p className="khsx-muted">Chưa có món nào để gom.</p>
        ) : (
          <div className="khsx-vtke__mons">
            {ke.tong.map((t) => (
              <DongMon d={t} buocs={t.buocs} key={`${t.khoa}|${t.don_vi ?? ""}`} />
            ))}
          </div>
        )}
        <p className="khsx-vtke__ghi">
          Đây là số <strong>cần</strong> — chưa trừ tồn kho, chưa trừ hàng đang về. Đủ hay thiếu thì
          xem ở màn <em>Kế hoạch vật tư</em>.
        </p>
      </div>
    </div>
  );
}
