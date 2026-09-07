// Tab KIỂM KÊ — ba bước, hết.
//
//   1. Tạo đợt → máy bung sẵn một dòng cho MỖI tài sản đang dùng thuộc phạm vi.
//   2. Cầm danh sách đi đối chiếu, mỗi dòng tick Có / Không thấy, gõ tình trạng nếu cần.
//   3. Kết thúc đợt → ra hai danh sách: THIẾU (có sổ không thấy) · THỪA (thấy không sổ).
//
// Cố ý KHÔNG có: dán QR lên máy, quét bằng điện thoại, ký duyệt nhiều cấp. Xưởng in này kiểm kê
// một hai lần một năm — mấy thứ đó thêm màn để sai chứ không thêm việc làm được.
//
// Đợt ĐÃ KẾT là đóng hẳn: kết quả kiểm kê là chứng từ, sửa sau khi đã ký biên bản thì biên bản
// thành vô nghĩa. Cần kiểm lại thì lập đợt mới.
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Department } from "../../api/client";
import { taiSanApi, type KiemKeChiTiet, type KiemKeRow } from "../../api/taiSan";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { Badge, HOM_NAY, NGAY_MAX, NGAY_MIN, ngay } from "./chung";

const NHAN_TT_DOT: Record<string, string> = { dang_kiem: "Đang kiểm", da_ket: "Đã kết thúc" };

export function KiemKeView() {
  const { token } = useAuth();
  const can = useCan();
  const taoDuoc = can("tai_san", "create");
  const ghiDuoc = can("tai_san", "update");

  const [dsDot, setDsDot] = useState<KiemKeRow[]>([]);
  const [dot, setDot] = useState<KiemKeChiTiet | null>(null);
  const [boPhan, setBoPhan] = useState<Department[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  // Form tạo đợt
  const [moTao, setMoTao] = useState(false);
  const [ngayDot, setNgayDot] = useState(HOM_NAY);
  const [boPhanDot, setBoPhanDot] = useState("");
  const [ghiChuDot, setGhiChuDot] = useState("");

  const [tenPhatHien, setTenPhatHien] = useState("");

  const napDs = useCallback(() => {
    if (!token) return;
    setDangTai(true);
    taiSanApi
      .dsKiemKe(token, { limit: 50 })
      .then((kq) => setDsDot(kq.items))
      .catch((e) => setLoi(e instanceof ApiError ? e.message : "Không tải được danh sách đợt."))
      .finally(() => setDangTai(false));
  }, [token]);

  useEffect(() => { napDs(); }, [napDs]);
  useEffect(() => {
    if (!token) return;
    api.rbac.departments(token).then(setBoPhan).catch(() => setBoPhan([]));
  }, [token]);

  async function chay(viec: (t: string) => Promise<KiemKeChiTiet | void>) {
    if (!token) return;
    setBan(true);
    setLoi(null);
    try {
      const kq = await viec(token);
      if (kq) setDot(kq);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không thực hiện được.");
    } finally {
      setBan(false);
    }
  }

  async function moDot(id: number) {
    if (!token) return;
    setLoi(null);
    try {
      setDot(await taiSanApi.chiTietKiemKe(token, id));
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không mở được đợt kiểm kê.");
    }
  }

  async function taoDot() {
    if (!token) return;
    setBan(true);
    setLoi(null);
    try {
      const moi = await taiSanApi.taoDotKiemKe(token, {
        ngay: ngayDot,
        bo_phan_id: boPhanDot ? Number(boPhanDot) : null,
        ghi_chu: ghiChuDot.trim() || null,
      });
      setDot(moi);
      setMoTao(false);
      setGhiChuDot("");
      napDs();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không tạo được đợt.");
    } finally {
      setBan(false);
    }
  }

  async function ketThuc() {
    if (!token || !dot) return;
    setBan(true);
    setLoi(null);
    try {
      await taiSanApi.ketThucKiemKe(token, dot.id);
      // Nạp lại chi tiết chứ không dựng kết quả từ response: hai danh sách bên dưới đọc thẳng
      // `dong`, một đường duy nhất cho cả đợt vừa kết lẫn đợt mở lại xem sau.
      setDot(await taiSanApi.chiTietKiemKe(token, dot.id));
      napDs();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không kết thúc được đợt.");
    } finally {
      setBan(false);
    }
  }

  const daKet = dot?.trang_thai === "da_ket";
  const dong = dot?.dong ?? [];
  const thieu = dong.filter((d) => d.tai_san_id && d.ket_qua === "khong_thay");
  const thua = dong.filter((d) => !d.tai_san_id);
  const chuaTick = dong.filter((d) => d.tai_san_id && !d.ket_qua).length;

  return (
    <>
      <div className="ts-kybar">
        <select className="rc-input" aria-label="Chọn đợt kiểm kê" disabled={dangTai || ban}
          value={dot?.id ?? ""} onChange={(e) => {
            if (e.target.value) moDot(Number(e.target.value));
            else setDot(null);
          }}>
          <option value="">{dangTai ? "Đang tải…" : "— Chọn đợt kiểm kê —"}</option>
          {dsDot.map((d) => (
            <option key={d.id} value={d.id}>
              {d.ma} · {ngay(d.ngay)} · {NHAN_TT_DOT[d.trang_thai] ?? d.trang_thai}
            </option>
          ))}
        </select>
        {dot && (
          <Badge he={dot.trang_thai}>{NHAN_TT_DOT[dot.trang_thai] ?? dot.trang_thai}</Badge>
        )}
        <div className="ts-kybar__phai">
          {taoDuoc && (
            <Button variant="accent" disabled={ban} onClick={() => setMoTao((v) => !v)}>
              <Icon name="plus" size={15} /> Đợt kiểm kê mới
            </Button>
          )}
        </div>
      </div>

      {loi && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          {loi}
        </div>
      )}

      {moTao && (
        <section className="rc-sec">
          <div className="rc-sec__title">Đợt kiểm kê mới</div>
          <div className="rc-grid">
            <label className="rc-field">
              <span className="rc-field__label">Ngày kiểm kê <em>*</em></span>
              <input className="rc-input" type="date" min={NGAY_MIN} max={NGAY_MAX}
                value={ngayDot} onChange={(e) => setNgayDot(e.target.value)} />
            </label>
            <label className="rc-field">
              <span className="rc-field__label">Phạm vi</span>
              <select className="rc-input" value={boPhanDot}
                onChange={(e) => setBoPhanDot(e.target.value)}>
                <option value="">Cả xưởng</option>
                {boPhan.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <span className="rc-field__hint">
                Máy bung sẵn một dòng cho mỗi tài sản ĐANG DÙNG trong phạm vi. Món đã ghi giảm
                không bung — nó không còn ở xưởng, hỏi "có thấy không" là vô nghĩa.
              </span>
            </label>
            <label className="rc-field rc-field--full">
              <span className="rc-field__label">Ghi chú</span>
              <input className="rc-input" value={ghiChuDot} maxLength={500}
                onChange={(e) => setGhiChuDot(e.target.value)} />
            </label>
          </div>
          <div style={{ display: "flex", gap: "var(--sp-2)", marginTop: "var(--sp-2)" }}>
            <Button variant="ghost" onClick={() => setMoTao(false)}>Hủy</Button>
            <Button variant="accent" loading={ban} onClick={taoDot}>Tạo đợt</Button>
          </div>
        </section>
      )}

      {!dot ? (
        <div className="rc__empty-state">
          <p className="rc__empty-text">
            Chọn một đợt để xem, hoặc lập đợt mới. Kiểm kê là lúc đối chiếu sổ với thứ thật sự
            còn ở xưởng.
          </p>
        </div>
      ) : (
        <>
          {daKet && (
            <div className="ts-khoa">
              <Icon name="lock" size={15} />
              <span>
                Đợt {dot.ma} đã kết thúc — không sửa được nữa. Cần kiểm lại thì lập đợt mới.
              </span>
            </div>
          )}

          {daKet && (
            <div className="ts-ketqua">
              <div className="ts-ketqua__o">
                <div className="ts-ketqua__title ts-ketqua__title--thieu">
                  Thiếu — có trong sổ, đi kiểm không thấy ({thieu.length})
                </div>
                {thieu.length === 0 ? (
                  <p className="ts-ketqua__rong">Không thiếu món nào.</p>
                ) : (
                  <ul className="ts-ketqua__ds">
                    {thieu.map((d) => (
                      <li key={d.id}>{d.ma} · {d.ten}{d.ghi_chu ? ` — ${d.ghi_chu}` : ""}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="ts-ketqua__o">
                <div className="ts-ketqua__title ts-ketqua__title--thua">
                  Thừa — thấy ở xưởng, không có trong sổ ({thua.length})
                </div>
                {thua.length === 0 ? (
                  <p className="ts-ketqua__rong">Không có món nào ngoài sổ.</p>
                ) : (
                  <ul className="ts-ketqua__ds">
                    {thua.map((d) => (
                      <li key={d.id}>
                        {d.ten_phat_hien}{d.tinh_trang ? ` — ${d.tinh_trang}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="rc-field__hint" style={{ marginTop: 6 }}>
                  Món thừa muốn vào sổ thì ghi tăng ở tab Danh sách — đợt kiểm kê chỉ ghi nhận.
                </p>
              </div>
            </div>
          )}

          <div className="rc__tablewrap">
            <table className="rc__table">
              <thead>
                <tr>
                  <th style={{ width: "10%" }}>Mã</th>
                  <th>Tên</th>
                  <th style={{ width: "20%" }}>Tình trạng</th>
                  <th style={{ width: "18%" }} className="text-center">Kết quả</th>
                </tr>
              </thead>
              <tbody>
                {dong.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="rc__empty-state-td">
                      <div className="rc__empty-state">
                        <p className="rc__empty-text">
                          Đợt này không có dòng nào — phạm vi đã chọn chưa có tài sản đang dùng.
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  dong.map((d) => (
                    <tr key={d.id}>
                      <td>
                        {d.ma
                          ? <span className="rc__code-badge">{d.ma}</span>
                          : <span className="ts-phu">ngoài sổ</span>}
                      </td>
                      <td>{d.ten ?? d.ten_phat_hien}</td>
                      <td>
                        <input className="rc-input" defaultValue={d.tinh_trang ?? ""}
                          maxLength={255} disabled={daKet || !ghiDuoc}
                          placeholder="Còn tốt / mòn / hỏng…"
                          aria-label={`Tình trạng ${d.ten ?? d.ten_phat_hien ?? ""}`}
                          // Ghi lúc RỜI ô, không ghi từng phím: gõ "Còn tốt" mà bắn bảy lượt gọi
                          // thì lượt cũ về sau có thể đè lượt mới.
                          onBlur={(e) => {
                            if (e.target.value === (d.tinh_trang ?? "")) return;
                            chay((t) => taiSanApi.ghiKetQua(t, dot.id, d.id, {
                              tinh_trang: e.target.value,
                            }));
                          }} />
                      </td>
                      <td className="text-center">
                        {d.tai_san_id ? (
                          <span className="ts-tick">
                            <button type="button" disabled={daKet || ban || !ghiDuoc}
                              className={`ts-tick__nut${d.ket_qua === "co" ? " is-co" : ""}`}
                              onClick={() => chay((t) => taiSanApi.ghiKetQua(t, dot.id, d.id, {
                                ket_qua: "co",
                              }))}>
                              Có
                            </button>
                            <button type="button" disabled={daKet || ban || !ghiDuoc}
                              className={`ts-tick__nut${d.ket_qua === "khong_thay" ? " is-khong" : ""}`}
                              onClick={() => chay((t) => taiSanApi.ghiKetQua(t, dot.id, d.id, {
                                ket_qua: "khong_thay",
                              }))}>
                              Không thấy
                            </button>
                          </span>
                        ) : (
                          <span className="ts-phu">phát hiện ngoài sổ</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {!daKet && ghiDuoc && (
            <section className="rc-sec">
              <div className="rc-sec__title">Phát hiện ngoài sổ</div>
              <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "flex-start" }}>
                <input className="rc-input" value={tenPhatHien} maxLength={255}
                  aria-label="Tên món phát hiện ngoài sổ"
                  placeholder="Máy dán keo chưa vào sổ"
                  onChange={(e) => setTenPhatHien(e.target.value)} />
                <Button variant="ghost" disabled={ban || !tenPhatHien.trim()}
                  onClick={() => chay(async (t) => {
                    const kq = await taiSanApi.themPhatHien(t, dot.id, {
                      ten_phat_hien: tenPhatHien.trim(),
                    });
                    setTenPhatHien("");
                    return kq;
                  })}>
                  <Icon name="plus" size={15} /> Thêm
                </Button>
              </div>
              <p className="rc-field__hint" style={{ marginTop: 6 }}>
                Món có ở xưởng mà không có trong sổ. Chỉ ghi nhận — đưa vào sổ hay không là việc
                của phiếu ghi tăng.
              </p>
            </section>
          )}

          {!daKet && ghiDuoc && (
            <div className="ts-kybar" style={{ marginTop: "var(--sp-3)" }}>
              {chuaTick > 0 && (
                <span className="rc-field__hint">
                  Còn {chuaTick} dòng chưa tick. Kết thúc luôn thì mấy dòng đó không vào danh sách
                  thiếu — nên tick hết trước.
                </span>
              )}
              <div className="ts-kybar__phai">
                <Button variant="primary" loading={ban} onClick={ketThuc}>
                  <Icon name="check" size={15} /> Kết thúc đợt
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
