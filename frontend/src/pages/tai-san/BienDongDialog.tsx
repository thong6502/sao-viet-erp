// HAI chứng từ biến động của MỘT tài sản, trong MỘT hộp thoại — đổi bằng dãy nút ở đầu.
//
// Gộp làm một vì đứng từ chỗ người dùng thì cả hai đều là "món này vừa có chuyện": đổi chỗ hay
// sửa chữa lớn. Tách thành nút riêng trên bảng là dòng nào cũng thêm nút.
//
//   • Điều chuyển   — đổi bộ phận giữ (kèm người quản lý mới). KHÔNG đụng một đồng nào trên sổ.
//   • Sửa chữa lớn  — (mã `nang_cap`) cộng chi phí vào nguyên giá, chia lại phần còn phải trích
//                     cho số tháng còn dùng. Hao mòn đã trích giữ nguyên. Chỉ cho sửa chữa làm
//                     máy tốt hơn / dùng lâu hơn; bảo dưỡng thường xuyên là chi phí tháng đó,
//                     không nhập ở đây (TT45/2013 Điều 7).
//
// KHÔNG có "Ghi giảm" nữa (chủ 08/09/2026: "cái ghi giảm bỏ đi"): món bán / hỏng / không dùng nữa
// thì bấm Xoá ở danh sách. Dòng cũ đã ghi giảm trước đó vẫn hiện trong lịch sử.
import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { Department } from "../../api/client";
import {
  NHAN_BIEN_DONG,
  taiSanApi,
  type NhanVienChon,
  type TaiSanChiTiet,
} from "../../api/taiSan";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { HOM_NAY, NGAY_MAX, NGAY_MIN, OTien, ngay, tien, tienDon } from "./chung";

type Mode = "dieu_chuyen" | "nang_cap";

export function BienDongDialog({
  token,
  taiSan,
  boPhan,
  onClose,
  onSaved,
}: {
  token: string;
  taiSan: TaiSanChiTiet;
  boPhan: Department[];
  onClose: () => void;
  /** Gọi sau khi lưu — để bảng ngoài nạp lại số. */
  onSaved: () => void;
}) {
  const [mode, setMode] = useState<Mode>("dieu_chuyen");
  const [ngayCt, setNgayCt] = useState(HOM_NAY);
  const [lyDo, setLyDo] = useState("");
  const [boPhanMoi, setBoPhanMoi] = useState("");
  // Người quản lý mới = NHÂN VIÊN của bộ phận NHẬN; đổi bộ phận nhận là nạp lại danh sách và bỏ
  // chọn — người cũ thuộc bộ phận cũ, để lại là sai.
  const [nguoiMoi, setNguoiMoi] = useState("");
  const [nhanVien, setNhanVien] = useState<NhanVienChon[]>([]);
  useEffect(() => {
    setNguoiMoi("");
    if (!boPhanMoi) {
      setNhanVien([]);
      return;
    }
    let conDung = true;
    taiSanApi
      .nhanVienBoPhan(token, Number(boPhanMoi))
      .then((ds) => { if (conDung) setNhanVien(ds); })
      .catch(() => { if (conDung) setNhanVien([]); });
    return () => { conDung = false; };
  }, [token, boPhanMoi]);
  const [soTien, setSoTien] = useState(0);
  const [soThangConLai, setSoThangConLai] = useState(taiSan.so_thang_con);

  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  // Sau khi lưu: nạp lại chi tiết để thấy dòng biến động mới VÀ mức trích đã đổi. Không tự suy
  // trên máy khách — con số phải là con số máy chủ đang giữ.
  const [sau, setSau] = useState<TaiSanChiTiet | null>(null);

  const hopLe =
    ngayCt !== ""
    && (mode !== "dieu_chuyen" || boPhanMoi !== "")
    && (mode !== "nang_cap" || (soTien > 0 && soThangConLai > 0));

  async function guiDi() {
    setBan(true);
    setLoi(null);
    const body: Record<string, unknown> = {
      loai: mode,
      ngay: ngayCt,
      ly_do: lyDo.trim() || null,
    };
    if (mode === "dieu_chuyen") {
      body.bo_phan_moi_id = Number(boPhanMoi);
      body.nguoi_quan_ly_id = nguoiMoi ? Number(nguoiMoi) : null;
    }
    if (mode === "nang_cap") {
      body.so_tien = soTien;
      body.so_thang_con_lai = soThangConLai;
    }
    try {
      await taiSanApi.bienDong(token, taiSan.id, body);
      setSau(await taiSanApi.chiTiet(token, taiSan.id));
      onSaved();
    } catch (e) {
      // Câu 422 của máy chủ ("ngày trước ngày đưa vào sử dụng"…) là chỉ dẫn, không phải sự cố —
      // hiện nguyên văn.
      setLoi(e instanceof ApiError ? e.message : "Không lưu được chứng từ.");
    } finally {
      setBan(false);
    }
  }

  const hienTai = sau ?? taiSan;
  const mucTrich = hienTai.so_thang_con > 0
    ? Math.floor(hienTai.co_so_trich / hienTai.so_thang_con)
    : 0;

  // Xem trước sửa chữa lớn: nguyên giá trước → sau (chính xác) và mức tháng mới (ƯỚC — máy chủ
  // tính lũy kế tới trước tháng áp dụng, ở đây lấy lũy kế tới hết tháng trước cộng thêm các tháng
  // chen giữa theo mức hiện tại). Số chính xác hiện ở bảng "Đã ghi chứng từ" sau khi lưu.
  const thangApDung = (() => {
    if (!ngayCt) return null;
    const d = new Date(`${ngayCt}T00:00:00`);
    if (Number.isNaN(d.getTime())) return null;
    if (d.getDate() !== 1) d.setMonth(d.getMonth() + 1, 1);
    return { nam: d.getFullYear(), thang: d.getMonth() + 1 };
  })();
  const xemTruoc = (() => {
    if (mode !== "nang_cap" || soTien <= 0 || soThangConLai <= 0 || !thangApDung) return null;
    const ngMoi = taiSan.nguyen_gia + soTien;
    let luyKe = taiSan.hao_mon_luy_ke;
    const den = taiSan.luy_ke_den;                       // "YYYY-MM" — tháng cuối đã gộp
    if (den) {
      const chen = (thangApDung.nam - Number(den.slice(0, 4))) * 12
        + (thangApDung.thang - Number(den.slice(5, 7))) - 1;
      luyKe = Math.min(taiSan.nguyen_gia, luyKe + Math.max(0, chen) * mucTrich);
    }
    return {
      ngMoi,
      mucMoi: Math.floor((ngMoi - luyKe) / soThangConLai),
      tu: `${String(thangApDung.thang).padStart(2, "0")}/${thangApDung.nam}`,
    };
  })();

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">Biến động · {taiSan.ma}</div>
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

          {sau ? (
            <section className="rc-sec">
              <div className="rc-sec__title">Đã ghi chứng từ</div>
              <div className="ts-dukien" style={{ maxHeight: "none" }}>
                <table>
                  <tbody>
                    <tr><td>Nguyên giá</td><td>{tien(sau.nguyen_gia)}</td></tr>
                    <tr><td>Hao mòn lũy kế</td><td>{tien(sau.hao_mon_luy_ke)}</td></tr>
                    <tr><td>Còn phải trích</td><td>{tien(sau.co_so_trich)}</td></tr>
                    <tr><td>Số tháng còn</td><td>{sau.so_thang_con}</td></tr>
                    <tr><td>Mức trích một tháng</td><td>{tien(mucTrich)}</td></tr>
                    <tr><td>Áp dụng từ</td><td>{ngay(sau.moc_tu_ngay)}</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <>
              <div className="ts-mode">
                {(["dieu_chuyen", "nang_cap"] as Mode[]).map((m) => (
                  <button key={m} type="button"
                    className={`ts-mode__nut${mode === m ? " is-active" : ""}`}
                    onClick={() => { setMode(m); setLoi(null); }}>
                    {NHAN_BIEN_DONG[m]}
                  </button>
                ))}
              </div>

              <section className="rc-sec">
                <div className="rc-sec__title">{NHAN_BIEN_DONG[mode]}</div>
                <div className="rc-grid">
                  <label className="rc-field">
                    <span className="rc-field__label">Ngày chứng từ <em>*</em></span>
                    <input className="rc-input" type="date" min={NGAY_MIN} max={NGAY_MAX}
                      value={ngayCt} onChange={(e) => setNgayCt(e.target.value)} />
                    <span className="rc-field__hint">
                      Không sớm hơn ngày đưa vào sử dụng.
                    </span>
                  </label>

                  {mode === "dieu_chuyen" && (
                    <>
                      <label className="rc-field">
                        <span className="rc-field__label">Bộ phận nhận <em>*</em></span>
                        <select className="rc-input" value={boPhanMoi}
                          onChange={(e) => setBoPhanMoi(e.target.value)}>
                          <option value="">— Chọn bộ phận —</option>
                          {boPhan.filter((b) => b.id !== taiSan.bo_phan_id).map((b) => (
                            <option key={b.id} value={b.id}>{b.name}</option>
                          ))}
                        </select>
                        <span className="rc-field__hint">
                          Đang ở: {taiSan.bo_phan_ten ?? "chưa gán"}. Đổi chỗ KHÔNG đụng tới số
                          — chỉ đổi bộ phận đứng tên trên bảng khấu hao tháng.
                        </span>
                      </label>
                      <label className="rc-field">
                        <span className="rc-field__label">Người quản lý mới</span>
                        <select className="rc-input" value={nguoiMoi} disabled={!boPhanMoi}
                          onChange={(e) => setNguoiMoi(e.target.value)}>
                          <option value="">— Bỏ trống —</option>
                          {nhanVien.map((nv) => (
                            <option key={nv.id} value={nv.id}>{nv.full_name} ({nv.code})</option>
                          ))}
                        </select>
                        <span className="rc-field__hint">
                          Nhân viên của bộ phận nhận. Không chọn thì bỏ trống — người cũ
                          ({taiSan.nguoi_quan_ly ?? "chưa gán"}) thuộc bộ phận cũ.
                        </span>
                      </label>
                    </>
                  )}

                  {mode === "nang_cap" && (
                    <>
                      <div className="rc-field rc-field--full">
                        <span className="rc-field__hint">
                          Chỉ ghi ở đây khi sửa chữa làm máy <strong>tốt hơn hoặc dùng lâu hơn</strong>
                          {" "}(thay đầu máy, đại tu, lắp thêm bộ phận): tiền sửa cộng vào nguyên giá
                          rồi chia lại cho số tháng còn dùng. Bảo dưỡng, thay vặt hằng tháng thì
                          <strong> không</strong> cộng vào máy — kế toán ghi chi phí tháng đó, không nhập ở đây.
                        </span>
                      </div>
                      <label className="rc-field">
                        <span className="rc-field__label">Chi phí sửa chữa <em>*</em></span>
                        <OTien value={soTien} onChange={setSoTien} />
                        <span className="rc-field__hint">
                          Cộng thẳng vào nguyên giá (đang là {tienDon(taiSan.nguyen_gia)}). Mức
                          mới áp từ đầu tháng sau — đúng ngày 1 thì ngay tháng đó.
                        </span>
                      </label>
                      <label className="rc-field">
                        <span className="rc-field__label">Số tháng còn dùng <em>*</em></span>
                        <input className="rc-input ts-num" type="number" min={1} max={600} step={1}
                          value={soThangConLai || ""}
                          onChange={(e) => setSoThangConLai(Math.max(0, Number(e.target.value) || 0))} />
                        <span className="rc-field__hint">
                          Tính từ tháng áp dụng. Đang còn {taiSan.so_thang_con} tháng — sửa chữa lớn
                          thường kéo dài thêm tuổi máy.
                        </span>
                      </label>
                      {xemTruoc && (
                        <div className="rc-field rc-field--full ts-xemtruoc">
                          Sau khi lưu: nguyên giá <strong>{tien(taiSan.nguyen_gia)} → {tien(xemTruoc.ngMoi)}</strong>
                          {" · "}mức tháng <strong>{tien(mucTrich)} → ≈ {tien(xemTruoc.mucMoi)}</strong>
                          {" "}từ tháng {xemTruoc.tu}. Hao mòn đã trích giữ nguyên.
                        </div>
                      )}
                    </>
                  )}

                  <label className="rc-field rc-field--full">
                    <span className="rc-field__label">Lý do / diễn giải</span>
                    <input className="rc-input" value={lyDo} maxLength={255}
                      onChange={(e) => setLyDo(e.target.value)} />
                  </label>
                </div>
              </section>
            </>
          )}

          <section className="rc-sec">
            <div className="rc-sec__title">Lịch sử biến động</div>
            {hienTai.bien_dong.length === 0 ? (
              <p className="rc-field__hint">Chưa có chứng từ nào.</p>
            ) : (
              <div className="ts-bd">
                {hienTai.bien_dong.map((b) => (
                  <div className="ts-bd__dong" key={b.id}>
                    <span className="ts-bd__ngay">{ngay(b.ngay)}</span>
                    <span className="ts-bd__loai">{NHAN_BIEN_DONG[b.loai] ?? b.loai}</span>
                    <span className="ts-bd__ly-do">
                      {b.ly_do ?? "—"}
                      {b.so_tien != null && ` · ${tienDon(b.so_tien)}`}
                      {b.so_luong_giam != null && ` · ${b.so_luong_giam} cái`}
                      {b.so_thang_con_lai != null && ` · còn ${b.so_thang_con_lai} tháng`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <footer className="rc-drawer__foot">
          {sau ? (
            <Button variant="primary" type="button" onClick={onClose}>Xong</Button>
          ) : (
            <>
              <Button variant="ghost" type="button" onClick={onClose}>Hủy</Button>
              <Button variant="accent" type="button" loading={ban} disabled={!hopLe}
                onClick={guiDi}>
                Lưu chứng từ
              </Button>
            </>
          )}
        </footer>
      </aside>
    </div>
  );
}
