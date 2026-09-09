// Ngăn kéo XEM một tài sản — bấm vào dòng trong danh sách là mở (chủ 08/09/2026: "bấm vào 1 sản
// phẩm thì xem được bảng khấu hao dự kiến, không phải chỉ lúc lưu / tạo mới").
//
// Chỉ ĐỌC: tóm tắt số, bảng khấu hao dự kiến trọn đời (tháng đã gộp vào lũy kế in đậm), lịch sử
// chứng từ. Sửa / biến động vẫn đi qua hai nút ở cột Thao tác — không nhét nút vào đây để ngăn
// kéo khỏi thành bản sao của cả trang.
import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  NHAN_BIEN_DONG,
  NHAN_LOAI,
  NHAN_NGUON_VAO,
  NHAN_TRANG_THAI,
  taiSanApi,
  type DongDuKien,
  type TaiSanChiTiet,
} from "../../api/taiSan";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { Badge, ngay, tien, tienDon } from "./chung";

export function ChiTietDialog({
  token,
  taiSan,
  onClose,
}: {
  token: string;
  taiSan: TaiSanChiTiet;
  onClose: () => void;
}) {
  const [lich, setLich] = useState<DongDuKien[] | null>(null);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    let conDung = true;
    taiSanApi
      .duKien(token, taiSan.id)
      .then((ds) => { if (conDung) setLich(ds); })
      .catch((e) => {
        if (conDung) setLoi(e instanceof ApiError ? e.message : "Không tải được lịch khấu hao.");
      });
    return () => { conDung = false; };
  }, [token, taiSan.id]);

  // "YYYY-MM" của tháng cuối đã gộp vào hao mòn lũy kế — dòng ≤ mốc này là ĐÃ TRÍCH.
  const den = taiSan.luy_ke_den;
  const daTrich = (d: DongDuKien) =>
    den !== "" && `${d.nam}-${String(d.thang).padStart(2, "0")}` <= den;
  const denNhan = den ? `${den.slice(5, 7)}/${den.slice(0, 4)}` : "";
  const mucThang = taiSan.so_thang_con > 0
    ? Math.floor(taiSan.co_so_trich / taiSan.so_thang_con)
    : 0;

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              {NHAN_LOAI[taiSan.loai] ?? taiSan.loai} · {taiSan.ma}
            </div>
            <h2 className="rc-drawer__title">{taiSan.ten}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={17} />
          </button>
        </header>

        <div className="rc-drawer__body">
          {loi && (
            <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-3)" }}>
              {loi}
            </div>
          )}

          <section className="rc-sec">
            <div className="rc-sec__title">Tóm tắt</div>
            <div className="ts-dukien" style={{ maxHeight: "none" }}>
              <table>
                <tbody>
                  <tr>
                    <td>Trạng thái</td>
                    <td>
                      <Badge he={taiSan.trang_thai}>
                        {NHAN_TRANG_THAI[taiSan.trang_thai] ?? taiSan.trang_thai}
                      </Badge>
                    </td>
                  </tr>
                  <tr>
                    <td>Nguyên giá</td>
                    <td>{tien(taiSan.nguyen_gia)}{taiSan.so_luong > 1 ? ` · ${taiSan.so_luong} cái` : ""}</td>
                  </tr>
                  <tr>
                    <td>Đã hao mòn{denNhan ? ` (hết ${denNhan})` : ""}</td>
                    <td>{tien(taiSan.hao_mon_luy_ke)}</td>
                  </tr>
                  <tr><td>Còn lại</td><td>{tien(taiSan.con_lai)}</td></tr>
                  <tr>
                    <td>Dùng từ</td>
                    <td>
                      {ngay(taiSan.ngay_su_dung)} · {taiSan.so_thang} tháng ·{" "}
                      {NHAN_NGUON_VAO[taiSan.nguon_vao] ?? taiSan.nguon_vao}
                    </td>
                  </tr>
                  <tr><td>Mức trích một tháng</td><td>{tien(mucThang)}</td></tr>
                  <tr>
                    <td>Bộ phận · người quản lý</td>
                    <td>{taiSan.bo_phan_ten ?? "chưa gán"} · {taiSan.nguoi_quan_ly ?? "chưa gán"}</td>
                  </tr>
                  {taiSan.ghi_chu && <tr><td>Ghi chú</td><td>{taiSan.ghi_chu}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rc-sec">
            <div className="rc-sec__title">Bảng khấu hao dự kiến</div>
            <p className="rc-field__hint" style={{ marginBottom: "var(--sp-2)" }}>
              Mỗi tháng một dòng, từ tháng đầu tới khi hết giá trị. Dòng in đậm là tháng đã gộp vào
              hao mòn lũy kế (tới hết {denNhan || "tháng trước"}); phần còn lại là dự kiến.
            </p>
            <div className="ts-dukien">
              <table>
                <thead>
                  <tr>
                    <th>Tháng</th>
                    <th>Trích trong tháng</th>
                    <th>Lũy kế</th>
                    <th>Còn lại</th>
                  </tr>
                </thead>
                <tbody>
                  {lich === null ? (
                    <tr><td colSpan={4}>Đang tải…</td></tr>
                  ) : lich.length === 0 ? (
                    <tr><td colSpan={4}>Không có tháng nào trích — chưa tới mốc hoặc đã hết giá trị.</td></tr>
                  ) : (
                    lich.map((d) => (
                      <tr key={`${d.nam}-${d.thang}`} title={d.dien_giai ?? undefined}
                        className={[
                          daTrich(d) ? "ts-dukien__da" : "",
                          d.su_kien.length > 0 ? "ts-dukien__moc" : "",
                        ].filter(Boolean).join(" ") || undefined}>
                        <td>{String(d.thang).padStart(2, "0")}/{d.nam}</td>
                        <td>{tien(d.muc_trich)}</td>
                        <td>{tien(d.luy_ke)}</td>
                        <td>{tien(d.con_lai)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {/* Tháng có chuyện (vạch đỏ bên trái) được giải nghĩa ngay dưới bảng: số trước → sau,
                để "26.400.000" ở bảng tháng nối được về "28.800.000 bớt 1 cái" ở đây. */}
            {lich && lich.some((d) => d.su_kien.length > 0) && (
              <ul className="ts-moc">
                {lich.flatMap((d) => d.su_kien.map((s, i) => (
                  <li key={`moc-${d.nam}-${d.thang}-${i}`}>
                    <strong>{String(d.thang).padStart(2, "0")}/{d.nam}</strong> — {s.chi_tiet}
                  </li>
                )))}
              </ul>
            )}
          </section>

          <section className="rc-sec">
            <div className="rc-sec__title">Lịch sử biến động</div>
            {taiSan.bien_dong.length === 0 ? (
              <p className="rc-field__hint">Chưa có chứng từ nào.</p>
            ) : (
              <div className="ts-dukien" style={{ maxHeight: "none" }}>
                <table>
                  <tbody>
                    {taiSan.bien_dong.map((b) => (
                      <tr key={b.id}>
                        <td>{ngay(b.ngay)}</td>
                        <td>
                          {NHAN_BIEN_DONG[b.loai] ?? b.loai}
                          {b.so_tien != null ? ` · ${tienDon(b.so_tien)}` : ""}
                          {b.so_luong_giam != null ? ` · ${b.so_luong_giam} cái` : ""}
                        </td>
                        <td>{b.ly_do ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <footer className="rc-drawer__foot">
          <Button variant="primary" type="button" onClick={onClose}>Đóng</Button>
        </footer>
      </aside>
    </div>
  );
}
