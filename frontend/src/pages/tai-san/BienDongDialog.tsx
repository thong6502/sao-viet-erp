// BA chứng từ biến động của MỘT tài sản, trong MỘT hộp thoại — đổi bằng dãy nút ở đầu.
//
// Gộp làm một vì đứng từ chỗ người dùng thì cả ba đều là "món này vừa có chuyện": đổi chỗ, sửa
// chữa lớn, hay thôi không dùng nữa. Tách thành ba nút riêng trên bảng là dòng nào cũng ba nút.
//
//   • Điều chuyển — đổi bộ phận giữ. KHÔNG đụng một đồng nào trên sổ.
//   • Nâng cấp    — cộng chi phí vào nguyên giá, chia lại phần còn phải trích cho số tháng còn
//                   dùng. Hao mòn đã trích giữ nguyên: nâng cấp không xoá quá khứ.
//   • Ghi giảm    — thanh lý / nhượng bán / mất / hỏng. Lô CCDC bỏ bớt vài cái thì lô vẫn sống.
import { useState } from "react";
import { ApiError } from "../../api/client";
import type { Department } from "../../api/client";
import {
  LY_DO_GHI_GIAM,
  NHAN_BIEN_DONG,
  taiSanApi,
  type TaiSanChiTiet,
} from "../../api/taiSan";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { HOM_NAY, NGAY_MAX, NGAY_MIN, OTien, ngay, tien, tienDon } from "./chung";

type Mode = "dieu_chuyen" | "nang_cap" | "ghi_giam";

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
  const daGiam = taiSan.trang_thai === "da_giam";
  const [mode, setMode] = useState<Mode>("dieu_chuyen");
  const [ngayCt, setNgayCt] = useState(HOM_NAY);
  const [lyDo, setLyDo] = useState("");
  const [ghiChuHt, setGhiChuHt] = useState("");
  const [boPhanMoi, setBoPhanMoi] = useState("");
  const [soTien, setSoTien] = useState(0);
  const [soThangConLai, setSoThangConLai] = useState(taiSan.so_thang_con);
  const [giaBan, setGiaBan] = useState(0);
  const [coGiaBan, setCoGiaBan] = useState(false);
  const [soLuongGiam, setSoLuongGiam] = useState(taiSan.so_luong);

  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  // Sau khi lưu: nạp lại chi tiết để thấy dòng biến động mới VÀ mức trích đã đổi. Không tự suy
  // trên máy khách — con số phải là con số máy chủ đang giữ.
  const [sau, setSau] = useState<TaiSanChiTiet | null>(null);

  const hopLe =
    ngayCt !== ""
    && (mode !== "dieu_chuyen" || boPhanMoi !== "")
    && (mode !== "nang_cap" || (soTien > 0 && soThangConLai > 0))
    && (mode !== "ghi_giam" || lyDo.trim() !== "");

  async function guiDi() {
    setBan(true);
    setLoi(null);
    const body: Record<string, unknown> = {
      loai: mode,
      ngay: ngayCt,
      ly_do: lyDo.trim() || null,
      ghi_chu_hach_toan: ghiChuHt.trim() || null,
    };
    if (mode === "dieu_chuyen") body.bo_phan_moi_id = Number(boPhanMoi);
    if (mode === "nang_cap") {
      body.so_tien = soTien;
      body.so_thang_con_lai = soThangConLai;
    }
    if (mode === "ghi_giam") {
      body.gia_ban = coGiaBan ? giaBan : null;
      // Chỉ gửi số lượng cho lô CCDC nhiều cái — TSCĐ một cái thì ô này vô nghĩa.
      body.so_luong_giam = taiSan.so_luong > 1 ? soLuongGiam : null;
    }
    try {
      await taiSanApi.bienDong(token, taiSan.id, body);
      setSau(await taiSanApi.chiTiet(token, taiSan.id));
      onSaved();
    } catch (e) {
      // Câu 409 "Kỳ MM/YYYY đã chốt…" là chỉ dẫn, không phải sự cố — hiện nguyên văn.
      setLoi(e instanceof ApiError ? e.message : "Không lưu được chứng từ.");
    } finally {
      setBan(false);
    }
  }

  const hienTai = sau ?? taiSan;
  const mucTrich = hienTai.so_thang_con > 0
    ? Math.floor(hienTai.co_so_trich / hienTai.so_thang_con)
    : 0;

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
                    <tr><td>Áp dụng từ kỳ</td><td>{ngay(sau.moc_tu_ngay)}</td></tr>
                  </tbody>
                </table>
              </div>
              {sau.chenh_lech_thanh_ly !== null && (
                <div className="ts-luuy" style={{ marginTop: "var(--sp-3)" }}>
                  <Icon name="alert" size={14} />
                  <span>
                    Chênh lệch thanh lý: <strong>{tienDon(sau.chenh_lech_thanh_ly)}</strong>{" "}
                    ({sau.chenh_lech_thanh_ly >= 0 ? "lãi" : "lỗ"}) — giá bán trừ giá trị còn lại.
                    Hạch toán vào đâu là việc của bạn; ghi vào ô ghi chú hạch toán nếu cần nhớ.
                  </span>
                </div>
              )}
            </section>
          ) : (
            <>
              <div className="ts-mode">
                {(["dieu_chuyen", "nang_cap", "ghi_giam"] as Mode[]).map((m) => (
                  <button key={m} type="button"
                    className={`ts-mode__nut${mode === m ? " is-active" : ""}`}
                    disabled={daGiam}
                    onClick={() => { setMode(m); setLoi(null); }}>
                    {NHAN_BIEN_DONG[m]}
                  </button>
                ))}
              </div>

              {daGiam && (
                <div className="ts-luuy">
                  <Icon name="alert" size={14} />
                  <span>
                    Món này đã ghi giảm ngày {ngay(taiSan.ngay_giam)} — không lập thêm chứng từ
                    được nữa. Xem lịch sử bên dưới.
                  </span>
                </div>
              )}

              {!daGiam && (
                <section className="rc-sec">
                  <div className="rc-sec__title">{NHAN_BIEN_DONG[mode]}</div>
                  <div className="rc-grid">
                    <label className="rc-field">
                      <span className="rc-field__label">Ngày chứng từ <em>*</em></span>
                      <input className="rc-input" type="date" min={NGAY_MIN} max={NGAY_MAX}
                        value={ngayCt} onChange={(e) => setNgayCt(e.target.value)} />
                      <span className="rc-field__hint">
                        Ngày rơi vào kỳ đã chốt thì máy chủ chặn — mở lại kỳ đó trước.
                      </span>
                    </label>

                    {mode === "dieu_chuyen" && (
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
                          Đang ở: {taiSan.bo_phan_ten ?? "chưa gán"}. Đổi chỗ KHÔNG đụng tới số —
                          chỉ đổi nơi chịu chi phí từ kỳ sau.
                        </span>
                      </label>
                    )}

                    {mode === "nang_cap" && (
                      <>
                        <label className="rc-field">
                          <span className="rc-field__label">Chi phí nâng cấp <em>*</em></span>
                          <OTien value={soTien} onChange={setSoTien} />
                          <span className="rc-field__hint">
                            Cộng thẳng vào nguyên giá (đang là {tienDon(taiSan.nguyen_gia)}).
                          </span>
                        </label>
                        <label className="rc-field">
                          <span className="rc-field__label">Số tháng còn dùng <em>*</em></span>
                          <input className="rc-input ts-num" type="number" min={1} max={600} step={1}
                            value={soThangConLai || ""}
                            onChange={(e) => setSoThangConLai(Math.max(0, Number(e.target.value) || 0))} />
                          <span className="rc-field__hint">
                            Tính từ kỳ áp dụng. Đang còn {taiSan.so_thang_con} tháng — sửa chữa lớn
                            thường kéo dài thêm tuổi máy.
                          </span>
                        </label>
                      </>
                    )}

                    {mode === "ghi_giam" && (
                      <>
                        <label className="rc-field">
                          <span className="rc-field__label">Lý do <em>*</em></span>
                          <input className="rc-input" list="ts-ly-do-giam" value={lyDo}
                            maxLength={255} placeholder="Thanh lý"
                            onChange={(e) => setLyDo(e.target.value)} />
                          <datalist id="ts-ly-do-giam">
                            {LY_DO_GHI_GIAM.map((x) => <option key={x} value={x} />)}
                          </datalist>
                        </label>
                        {taiSan.so_luong > 1 && (
                          <label className="rc-field">
                            <span className="rc-field__label">Số lượng giảm</span>
                            <input className="rc-input ts-num" type="number" min={1}
                              max={taiSan.so_luong} step={1} value={soLuongGiam}
                              onChange={(e) => setSoLuongGiam(
                                Math.min(taiSan.so_luong, Math.max(1, Number(e.target.value) || 1)),
                              )} />
                            <span className="rc-field__hint">
                              Lô đang có {taiSan.so_luong} cái. Bỏ bớt vài cái thì lô vẫn sống,
                              nguyên giá và hao mòn cùng rút theo tỷ lệ.
                            </span>
                          </label>
                        )}
                        <label className="rc-field rc-field--check">
                          <input type="checkbox" checked={coGiaBan}
                            onChange={(e) => setCoGiaBan(e.target.checked)} />
                          <span className="rc-field__label">Có bán được tiền</span>
                        </label>
                        {coGiaBan && (
                          <label className="rc-field">
                            <span className="rc-field__label">Giá bán</span>
                            <OTien value={giaBan} onChange={setGiaBan} />
                            <span className="rc-field__hint">
                              Còn lại trên sổ: {tienDon(taiSan.con_lai)} — chênh lệch sẽ hiện sau
                              khi lưu.
                            </span>
                          </label>
                        )}
                      </>
                    )}

                    {mode !== "ghi_giam" && (
                      <label className="rc-field rc-field--full">
                        <span className="rc-field__label">Lý do / diễn giải</span>
                        <input className="rc-input" value={lyDo} maxLength={255}
                          onChange={(e) => setLyDo(e.target.value)} />
                      </label>
                    )}

                    <label className="rc-field rc-field--full">
                      <span className="rc-field__label">Ghi chú hạch toán</span>
                      <input className="rc-input" value={ghiChuHt} maxLength={500}
                        placeholder="811 / 211 - thanh lý"
                        onChange={(e) => setGhiChuHt(e.target.value)} />
                    </label>
                  </div>
                </section>
              )}
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
          {sau || daGiam ? (
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
