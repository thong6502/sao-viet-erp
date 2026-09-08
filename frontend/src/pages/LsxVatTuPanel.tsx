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
import { nhanDonVi } from "./lsxBuoc";
import { useNapTenDonVi } from "./tenDonVi";
import type { BangKeVatTu, DongKe, TongKe } from "./lsxVatTu";

/** Nhãn tình trạng khuôn — cùng bộ mã với danh mục Khuôn. Mã lạ thì hiện mã trần, không nuốt. */
const TINH_TRANG: Record<string, string> = {
  dang_dung: "đang dùng",
  dang_dat_lam: "đang đặt làm",
  hong: "hỏng",
  thanh_ly: "đã thanh lý",
};

/** Một hàng vật tư. Trước đây mỗi món là một CARD xếp dọc: cùng một thông tin mà mã, tên, số
 *  lượng, đơn vị của các món không thẳng cột nào với nhau, đọc 8 món phải quét mắt zig-zag. Bảng
 *  cho số lượng thẳng cột và nhóm/bước thành cột lọc được bằng mắt. */
function HangMon({ d, buocs, coBuoc }: { d: DongKe; buocs?: number[]; coBuoc: boolean }) {
  const chu =
    d.nhom === "dung_cu" && d.chu_thich
      ? (TINH_TRANG[d.chu_thich] ?? d.chu_thich)
      : d.chu_thich;

  const nhomLabel =
    d.nhom === "nvl" ? "NVL chính" : d.nhom === "dung_cu" ? "Dụng cụ / Khuôn" : "Phụ liệu";

  return (
    <tr className={`khsx-vtbang__r khsx-vtbang__r--${d.nhom}`}>
      <td className="khsx-vtbang__ma">{d.ma || ""}</td>
      <td className="khsx-vtbang__ten">
        <span className="khsx-vtbang__ten-txt">{d.ten}</span>
        {chu && <span className="khsx-vtbang__sub">{chu}</span>}
      </td>
      <td className="khsx-vtbang__sl">{d.so_luong != null ? num(d.so_luong) : "—"}</td>
      <td className="khsx-vtbang__dv">{d.don_vi ? nhanDonVi(d.don_vi) : ""}</td>
      <td className="khsx-vtbang__nhom">
        <span className={`khsx-vtcard__tag khsx-vtcard__tag--${d.nhom}`}>{nhomLabel}</span>
      </td>
      {coBuoc && (
        <td className="khsx-vtbang__buoc">
          {buocs && buocs.length > 0 && (
            <span className={`khsx-vtcard__buoc${buocs.length > 1 ? " is-nhieu" : ""}`}>
              {buocs.map((b) => `#${b}`).join(" · ")}
            </span>
          )}
        </td>
      )}
    </tr>
  );
}

/** Bảng vật tư dùng chung cho hai chỗ: trong từng bước (không có cột Bước — đã biết bước nào rồi)
 *  và ở khối BOM tổng gom (có cột Bước, vì một món đi vào nhiều bước). */
function BangMon({ dong, coBuoc = false }: { dong: (DongKe | TongKe)[]; coBuoc?: boolean }) {
  return (
    <div className="khsx-vtbang__wrap">
      <table className="khsx-vtbang">
        <thead>
          <tr>
            <th className="khsx-vtbang__ma">Mã</th>
            <th className="khsx-vtbang__ten">Vật tư</th>
            <th className="khsx-vtbang__sl">Số lượng</th>
            <th className="khsx-vtbang__dv">ĐVT</th>
            <th className="khsx-vtbang__nhom">Nhóm</th>
            {coBuoc && <th className="khsx-vtbang__buoc">Bước</th>}
          </tr>
        </thead>
        <tbody>
          {dong.map((d) => (
            <HangMon
              d={d}
              buocs={"buocs" in d ? d.buocs : undefined}
              coBuoc={coBuoc}
              key={`${d.khoa}|${d.don_vi ?? ""}`}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** `ke` tính SẴN ở màn cha (một lần cho cả ô tóm tắt trên đầu màn lẫn bảng này) — panel chỉ vẽ. */
export function LsxVatTuPanel({ ke }: { ke: BangKeVatTu }) {
  // Panel này mount từ HAI màn (Lệnh SX · Bài ghép 2) — tự nạp nhãn đơn vị thay vì trông chờ màn
  // cha, vì bên Bài ghép 2 không có ai nạp. Hook có cache chung nên gọi thêm không tốn lượt gọi.
  useNapTenDonVi();
  // Không có bước NÀO để bày pipeline VÀ cũng chẳng có món nào để gom ⇒ trống thật, mới báo trống.
  // Ở lệnh đơn hai điều kiện luôn đi cùng (tổng suy từ bước, không bước thì không món) nên câu này
  // giữ nguyên. Ở bài ghép, bước = bước CHUNG (`sd.gop`) có thể còn rỗng khi chưa gộp, nhưng BOM vẫn
  // gồm vật tư bước riêng của thành viên — lúc đó phải hiện BOM, đừng nuốt cả buy-list.
  if (ke.buocs.length === 0 && ke.tong.length === 0) {
    return <p className="khsx-muted">Lệnh chưa có công đoạn nào — khai công đoạn trước đã.</p>;
  }

  return (
    <div className="khsx-vtke">
      {/* Dải Compact Strip KPI Tóm Tắt */}
      <div className="khsx-vtke__strip">
        <div className="khsx-vtke__strip-item">
          <span className="khsx-vtke__strip-lbl">Tổng nhu cầu</span>
          <span className="khsx-vtke__strip-val">
            <b>{ke.so_mon}</b> <small>món</small>
          </span>
        </div>

        <div className="khsx-vtke__strip-sep" aria-hidden="true" />

        <div className="khsx-vtke__strip-item">
          <span className="khsx-vtke__strip-lbl">Độ phủ công đoạn</span>
          <span className="khsx-vtke__strip-val">
            <b>{ke.buocs.length - ke.so_buoc_trong}/{ke.buocs.length}</b> <small>bước dùng vật tư</small>
          </span>
        </div>

        {(ke.so_buoc_chua_dau_viec > 0 || ke.buocs.some((b) => b.thieu_khuon)) && (
          <>
            <div className="khsx-vtke__strip-sep" aria-hidden="true" />
            <div className="khsx-vtke__strip-item">
              <span className="khsx-vtke__strip-lbl">Cảnh báo</span>
              <div className="khsx-vtke__strip-alerts">
                {ke.so_buoc_chua_dau_viec > 0 && (
                  <span className="khsx-vtke__strip-badge khsx-vtke__strip-badge--warn">
                    <Icon name="alert" size={12} /> {ke.so_buoc_chua_dau_viec} bước chưa chọn đầu việc
                  </span>
                )}
                {ke.buocs.some((b) => b.thieu_khuon) && (
                  <span className="khsx-vtke__strip-badge khsx-vtke__strip-badge--danger">
                    <Icon name="alert" size={12} /> Thiếu khuôn bế
                  </span>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Dòng chảy vật tư theo Trục Tiến trình (Vertical Process Pipeline) */}
      <ol className="khsx-vtke__pipeline">
        {ke.buocs.map((b) => {
          const hasVatTu = b.dong.length > 0;
          return (
            <li className={`khsx-vtke__step ${hasVatTu ? "has-vattu" : ""}`} key={b.id}>
              <div className="khsx-vtke__node-col">
                <span className="khsx-vtke__node">#{b.thu_tu}</span>
                <div className="khsx-vtke__line" aria-hidden="true" />
              </div>

              <div className="khsx-vtke__step-body">
                <div className="khsx-vtke__step-head">
                  <div className="khsx-vtke__step-title-wrap">
                    <span className="khsx-vtke__step-title">{b.ten}</span>
                    {b.to && <span className="khsx-vtke__org-tag">{b.to}</span>}
                    {b.may && <span className="khsx-vtke__mach-tag">{b.may}</span>}
                  </div>
                  {b.dau_viec ? (
                    <span className="khsx-vtke__job-tag">{b.dau_viec}</span>
                  ) : (
                    <span className="khsx-vtke__job-tag is-empty">chưa chọn đầu việc</span>
                  )}
                </div>

                <div className="khsx-vtke__flow-bar">
                  <span className="khsx-vtke__flow-num">
                    <b>{num(b.sl_vao)}</b> {b.dv_vao}
                  </span>
                  <span className="khsx-vtke__flow-arrow" aria-hidden="true">→</span>
                  <span className="khsx-vtke__flow-num">
                    <b>{num(b.sl_ra)}</b> {b.dv_ra}
                  </span>
                  {!b.tren_dong_giay && (
                    <span
                      className="khsx-vtke__ngoai"
                      title="Bước này đo bằng đơn vị riêng, không nằm trên dòng giấy — số vào/ra không nối với bước liền kề."
                    >
                      ngoài dòng giấy
                    </span>
                  )}
                </div>

                {hasVatTu ? (
                  <BangMon dong={b.dong} />
                ) : (
                  <div className="khsx-vtke__empty-step">
                    <span>— Không tiêu hao vật tư ở bước này</span>
                  </div>
                )}

                {b.thieu_khuon && (
                  <div className="khsx-vtke__alert-box">
                    <Icon name="alert" size={13} />
                    <span>Công đoạn này cần khuôn nhưng lệnh chưa gán con nào.</span>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {/* Khối BOM Tổng gom cuối bảng */}
      <div className="khsx-vtke__bom">
        <div className="khsx-vtke__bom-head">
          <div className="khsx-vtke__bom-title-row">
            <Icon name="layers" size={15} />
            <h5 className="khsx-vtke__bom-title">Tổng gom vật tư cần dùng (BOM)</h5>
          </div>
          <span className="khsx-vtke__bom-count">{ke.tong.length} mặt hàng</span>
        </div>

        {ke.tong.length === 0 ? (
          <p className="khsx-muted">Chưa có món nào để gom.</p>
        ) : (
          <BangMon dong={ke.tong} coBuoc />
        )}

        <div className="khsx-vtke__bom-foot">
          <Icon name="alert" size={14} />
          <span>
            Đây là <b>tổng số cần</b> theo định mức kỹ thuật — Kiểm tra tồn kho, giữ chỗ và cấp phát tại <b>Kế hoạch vật tư</b>.
          </span>
        </div>
      </div>
    </div>
  );
}
