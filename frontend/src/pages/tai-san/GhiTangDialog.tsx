// Phiếu GHI TĂNG tài sản / công cụ dụng cụ — cũng là chỗ SỬA một món đã có trong sổ.
//
// Ba điều đã chốt khi thiết kế, đừng vô tình gỡ:
//
//  1. KHÔNG có ô "Tài khoản 211 / 153 / 242", cũng không có ô định khoản riêng. Định khoản là
//     việc của phần mềm kế toán bên ngoài; cần nhớ thì gõ vào ô GHI CHÚ. Thêm ô tài khoản vào là
//     biến màn này thành nửa phần mềm kế toán — đúng thứ đã quyết là không làm.
//  2. Nguyên giá KHÔNG gõ tay: nó là TỔNG các dòng cấu thành (giá mua + vận chuyển + lắp đặt
//     chạy thử). Ba tháng sau còn lần được vì sao ra con số đó.
//  3. Số tháng khấu hao do người dùng gõ, phần mềm chỉ GỢI Ý khung tham khảo. Không có bảng
//     "nhóm tài sản" khai sẵn số năm — đã bỏ vì thừa: mỗi món gõ một lần rồi thôi.
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import type { Department } from "../../api/client";
import {
  NGUONG_TSCD,
  taiSanApi,
  type DongDuKien,
  type TaiSanChiTiet,
} from "../../api/taiSan";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icons";
import { HOM_NAY, NGAY_MAX, NGAY_MIN, OTien, tien, tienDon } from "./chung";

interface DongChiPhi {
  dien_giai: string;
  so_tien: number;
}

interface Form {
  ten: string;
  loai: string;
  so_luong: number;
  don_gia: number;
  so_thang: number;
  ngay_su_dung: string;
  chi_phi: DongChiPhi[];
  bo_phan_id: string;
  nguoi_quan_ly: string;
  vi_tri: string;
  so_hoa_don: string;
  nha_cung_cap: string;
  ghi_chu: string;
  // --- nhánh số dư đầu kỳ ---
  dau_ky: boolean;
  moc_tu_ngay: string;
  thang_da_trich_dau_ky: number;
  hao_mon_dau_ky: number;
}

const FORM_RONG: Form = {
  ten: "", loai: "tscd", so_luong: 1, don_gia: 0, so_thang: 0, ngay_su_dung: HOM_NAY,
  chi_phi: [{ dien_giai: "Giá mua", so_tien: 0 }],
  bo_phan_id: "", nguoi_quan_ly: "", vi_tri: "", so_hoa_don: "", nha_cung_cap: "",
  ghi_chu: "",
  dau_ky: false, moc_tu_ngay: "", thang_da_trich_dau_ky: 0, hao_mon_dau_ky: 0,
};

export function GhiTangDialog({
  token,
  taiSan,
  boPhan,
  onClose,
  onSaved,
}: {
  token: string;
  /** `null` = ghi tăng mới; có giá trị = sửa món đã có. */
  taiSan: TaiSanChiTiet | null;
  boPhan: Department[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const sua = taiSan !== null;
  const [form, setForm] = useState<Form>(FORM_RONG);
  const [luu, setLuu] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  // Sau khi lưu xong thì thay thân phiếu bằng BẢNG DỰ KIẾN — kế toán thấy ngay tháng đầu bị chia
  // theo ngày và tháng cuối gánh phần lẻ thì mới tin con số máy tính ra.
  const [duKien, setDuKien] = useState<DongDuKien[] | null>(null);
  const [tenDaLuu, setTenDaLuu] = useState("");

  useEffect(() => {
    if (!taiSan) {
      setForm(FORM_RONG);
      return;
    }
    setForm({
      ten: taiSan.ten,
      loai: taiSan.loai,
      so_luong: taiSan.so_luong,
      don_gia: taiSan.don_gia ?? 0,
      so_thang: taiSan.so_thang,
      ngay_su_dung: taiSan.ngay_su_dung.slice(0, 10),
      chi_phi: taiSan.chi_phi.length
        ? taiSan.chi_phi.map((c) => ({ dien_giai: c.dien_giai, so_tien: c.so_tien }))
        : [{ dien_giai: "Giá mua", so_tien: taiSan.nguyen_gia }],
      bo_phan_id: taiSan.bo_phan_id ? String(taiSan.bo_phan_id) : "",
      nguoi_quan_ly: taiSan.nguoi_quan_ly ?? "",
      vi_tri: taiSan.vi_tri ?? "",
      so_hoa_don: taiSan.so_hoa_don ?? "",
      nha_cung_cap: taiSan.nha_cung_cap ?? "",
      ghi_chu: taiSan.ghi_chu ?? "",
      dau_ky: taiSan.nguon_vao === "dau_ky",
      moc_tu_ngay: taiSan.moc_tu_ngay.slice(0, 10),
      thang_da_trich_dau_ky: Math.max(0, taiSan.so_thang - taiSan.so_thang_con),
      hao_mon_dau_ky: taiSan.hao_mon_luy_ke,
    });
  }, [taiSan]);

  const laCcdc = form.loai === "ccdc";
  // CCDC mua theo LÔ (12 tấm cao su) nên nguyên giá là số lượng × đơn giá; TSCĐ là tổng các dòng
  // cấu thành. Máy chủ tính lại y hệt — ở đây chỉ để người gõ thấy tổng ngay lúc gõ.
  const nguyenGia = useMemo(
    () => (laCcdc
      ? Math.max(0, form.so_luong) * Math.max(0, form.don_gia)
      : form.chi_phi.reduce((s, d) => s + (d.so_tien || 0), 0)),
    [laCcdc, form.so_luong, form.don_gia, form.chi_phi],
  );

  const duoiNguong = form.loai === "tscd" && nguyenGia > 0 && nguyenGia < NGUONG_TSCD;
  const hopLe = form.ten.trim() !== "" && form.so_thang > 0 && nguyenGia > 0
    && form.ngay_su_dung !== ""
    && (!form.dau_ky || (form.moc_tu_ngay !== "" && form.thang_da_trich_dau_ky > 0));

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function suaDong(i: number, phan: Partial<DongChiPhi>) {
    setForm((f) => ({
      ...f,
      chi_phi: f.chi_phi.map((d, j) => (j === i ? { ...d, ...phan } : d)),
    }));
  }

  /** Thân request. Khi SỬA thì chỉ gửi ô THẬT SỰ ĐỔI.
   *
   *  Không phải để tiết kiệm byte: máy chủ chặn mọi ô ảnh hưởng số khi tài sản đã có số ở kỳ đã
   *  chốt. Gửi cả form thì đổi mỗi chữ trong tên cũng ăn 409 "đang sửa: chi_phi, loai, so_luong…",
   *  và người dùng không hiểu vì sao sửa tên lại đụng tới nguyên giá. */
  function than(): Record<string, unknown> {
    const chiPhi = laCcdc ? [] : form.chi_phi.filter((d) => d.so_tien > 0);
    const day: Record<string, unknown> = {
      ten: form.ten.trim(),
      loai: form.loai,
      so_luong: laCcdc ? form.so_luong : 1,
      don_gia: laCcdc ? form.don_gia : null,
      so_thang: form.so_thang,
      ngay_su_dung: form.ngay_su_dung,
      // CCDC theo lô KHÔNG khai dòng chi phí — máy chủ tự lấy số lượng × đơn giá.
      chi_phi: chiPhi,
      bo_phan_id: form.bo_phan_id ? Number(form.bo_phan_id) : null,
      nguoi_quan_ly: form.nguoi_quan_ly.trim() || null,
      vi_tri: form.vi_tri.trim() || null,
      so_hoa_don: form.so_hoa_don.trim() || null,
      nha_cung_cap: form.nha_cung_cap.trim() || null,
      ghi_chu: form.ghi_chu.trim() || null,
    };
    if (form.dau_ky) {
      day.moc_tu_ngay = form.moc_tu_ngay;
      day.thang_da_trich_dau_ky = form.thang_da_trich_dau_ky;
      day.hao_mon_dau_ky = form.hao_mon_dau_ky;
    }
    if (!taiSan) {
      day.nguon_vao = form.dau_ky ? "dau_ky" : "ghi_tang";
      return day;
    }
    const cu: Record<string, unknown> = {
      ten: taiSan.ten,
      loai: taiSan.loai,
      so_luong: taiSan.so_luong,
      don_gia: taiSan.don_gia,
      so_thang: taiSan.so_thang,
      ngay_su_dung: taiSan.ngay_su_dung.slice(0, 10),
      chi_phi: taiSan.chi_phi.map((c) => ({ dien_giai: c.dien_giai, so_tien: c.so_tien })),
      bo_phan_id: taiSan.bo_phan_id,
      nguoi_quan_ly: taiSan.nguoi_quan_ly,
      vi_tri: taiSan.vi_tri,
      so_hoa_don: taiSan.so_hoa_don,
      nha_cung_cap: taiSan.nha_cung_cap,
      ghi_chu: taiSan.ghi_chu,
      moc_tu_ngay: taiSan.moc_tu_ngay.slice(0, 10),
      thang_da_trich_dau_ky: Math.max(0, taiSan.so_thang - taiSan.so_thang_con),
      hao_mon_dau_ky: taiSan.hao_mon_luy_ke,
    };
    const doi: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(day)) {
      if (JSON.stringify(v ?? null) !== JSON.stringify(cu[k] ?? null)) doi[k] = v;
    }
    return doi;
  }

  async function guiDi() {
    setLuu(true);
    setLoi(null);
    try {
      const body = than();
      const t = sua && taiSan
        ? await taiSanApi.sua(token, taiSan.id, body)
        : await taiSanApi.ghiTang(token, body);
      setTenDaLuu(`${t.ma} · ${t.ten}`);
      setDuKien(await taiSanApi.duKien(token, t.id));
      onSaved();
    } catch (e) {
      // 409 của máy chủ (mã trùng · đã có số ở kỳ đã chốt) là câu người dùng cần đọc NGUYÊN VĂN,
      // đừng gói lại thành "có lỗi xảy ra".
      setLoi(e instanceof ApiError ? e.message : "Không lưu được. Thử lại.");
    } finally {
      setLuu(false);
    }
  }

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              {duKien ? "Đã lưu" : sua ? "Sửa" : "Ghi tăng"}
            </div>
            <h2 className="rc-drawer__title">
              {duKien ? tenDaLuu : sua ? taiSan?.ma : "Tài sản / công cụ dụng cụ mới"}
            </h2>
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

          {duKien ? (
            <section className="rc-sec">
              <div className="rc-sec__title">Bảng khấu hao dự kiến</div>
              <p className="rc-field__hint" style={{ marginBottom: "var(--sp-2)" }}>
                Đây mới là DỰ KIẾN — chưa ghi sổ kỳ nào. Số thật vào sổ khi bấm Tính rồi Chốt ở
                tab “Khấu hao theo kỳ”.
              </p>
              <div className="ts-dukien">
                <table>
                  <thead>
                    <tr>
                      <th>Kỳ</th>
                      <th>Trích trong kỳ</th>
                      <th>Lũy kế</th>
                      <th>Còn lại</th>
                    </tr>
                  </thead>
                  <tbody>
                    {duKien.map((d) => (
                      <tr key={`${d.nam}-${d.thang}`}>
                        <td>{String(d.thang).padStart(2, "0")}/{d.nam}</td>
                        <td>{tien(d.muc_trich)}</td>
                        <td>{tien(d.luy_ke)}</td>
                        <td>{tien(d.con_lai)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <>
              <section className="rc-sec">
                <div className="rc-sec__title">Món này là gì</div>
                <div className="rc-grid">
                  <label className="rc-field">
                    <span className="rc-field__label">Loại <em>*</em></span>
                    <select className="rc-input" value={form.loai}
                      onChange={(e) => set("loai", e.target.value)}>
                      <option value="tscd">Tài sản cố định</option>
                      <option value="ccdc">Công cụ dụng cụ</option>
                    </select>
                    <span className="rc-field__hint">
                      Khác nhau ở chỗ nào: TSCĐ trích khấu hao, CCDC phân bổ. Cách tính giống hệt
                      nhau — chỉ khác cái tên gọi trên chứng từ.
                    </span>
                  </label>
                  <label className="rc-field rc-field--full">
                    <span className="rc-field__label">Tên tài sản <em>*</em></span>
                    <input className="rc-input" value={form.ten} maxLength={255}
                      placeholder="Máy in Komori 4 màu"
                      onChange={(e) => set("ten", e.target.value)} />
                  </label>
                </div>
              </section>

              <section className="rc-sec">
                <div className="rc-sec__title">Nguyên giá</div>
                {laCcdc ? (
                  <div className="rc-grid">
                    <label className="rc-field">
                      <span className="rc-field__label">Số lượng <em>*</em></span>
                      <input className="rc-input ts-num" type="number" min={1} step={1}
                        value={form.so_luong}
                        onChange={(e) => set("so_luong", Math.max(1, Number(e.target.value) || 1))} />
                      <span className="rc-field__hint">
                        Mua theo lô thì khai cả lô một dòng — ghi giảm sau này bớt được từng cái.
                      </span>
                    </label>
                    <label className="rc-field">
                      <span className="rc-field__label">Đơn giá <em>*</em></span>
                      <OTien value={form.don_gia} onChange={(v) => set("don_gia", v)} />
                    </label>
                  </div>
                ) : (
                  <>
                    {/* Bảng dòng: nguyên giá của TSCĐ gồm cả chi phí đưa vào trạng thái sẵn sàng
                        dùng, không riêng giá trên hoá đơn. */}
                    <table className="ts-chiphi">
                      <thead>
                        <tr>
                          <th>Khoản mục</th>
                          <th>Số tiền</th>
                          <th aria-label="Xoá dòng" />
                        </tr>
                      </thead>
                      <tbody>
                        {form.chi_phi.map((d, i) => (
                          <tr key={i}>
                            <td>
                              <input className="rc-input" value={d.dien_giai} maxLength={255}
                                placeholder="Vận chuyển, lắp đặt chạy thử…"
                                aria-label={`Khoản mục dòng ${i + 1}`}
                                onChange={(e) => suaDong(i, { dien_giai: e.target.value })} />
                            </td>
                            <td className="ts-chiphi__tien">
                              <OTien value={d.so_tien} ariaLabel={`Số tiền dòng ${i + 1}`}
                                onChange={(v) => suaDong(i, { so_tien: v })} />
                            </td>
                            <td>
                              <button type="button" className="ts-chiphi__x"
                                aria-label={`Xoá dòng ${i + 1}`}
                                disabled={form.chi_phi.length <= 1}
                                onClick={() => setForm((f) => ({
                                  ...f, chi_phi: f.chi_phi.filter((_, j) => j !== i),
                                }))}>
                                <Icon name="trash" size={15} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <button type="button" className="btn btn--ghost" style={{ marginTop: 6 }}
                      onClick={() => setForm((f) => ({
                        ...f, chi_phi: [...f.chi_phi, { dien_giai: "", so_tien: 0 }],
                      }))}>
                      <Icon name="plus" size={14} /> Thêm khoản mục
                    </button>
                  </>
                )}
                <div className="ts-tong">
                  <span className="ts-tong__nhan">Nguyên giá</span>
                  <span className="ts-tong__so">{tienDon(nguyenGia)}</span>
                </div>
                {duoiNguong && (
                  <div className="ts-luuy">
                    <Icon name="alert" size={14} />
                    <span>
                      Dưới {tien(NGUONG_TSCD)} đ — theo Thông tư 45/2013 mức này thường ghi là
                      <strong> công cụ dụng cụ</strong>, không phải tài sản cố định. Vẫn lưu được
                      nếu bạn có lý do riêng.
                    </span>
                  </div>
                )}
              </section>

              <section className="rc-sec">
                <div className="rc-sec__title">Trích trong bao lâu</div>
                <div className="rc-grid">
                  <label className="rc-field">
                    <span className="rc-field__label">Số tháng <em>*</em></span>
                    <input className="rc-input ts-num" type="number" min={1} max={600} step={1}
                      value={form.so_thang || ""}
                      onChange={(e) => set("so_thang", Math.max(0, Number(e.target.value) || 0))} />
                    <span className="rc-field__hint">
                      Tham khảo: máy in 7–15 năm · công cụ dụng cụ tối đa 3 năm.
                      {form.so_thang > 0 && ` Đang khai ${form.so_thang} tháng ≈ ${(form.so_thang / 12).toFixed(1)} năm.`}
                    </span>
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Ngày đưa vào sử dụng <em>*</em></span>
                    <input className="rc-input" type="date" min={NGAY_MIN} max={NGAY_MAX}
                      value={form.ngay_su_dung}
                      onChange={(e) => set("ngay_su_dung", e.target.value)} />
                    <span className="rc-field__hint">
                      Tháng đầu chỉ trích theo số ngày thực dùng, không trích tròn tháng.
                    </span>
                  </label>
                </div>
              </section>

              <section className="rc-sec">
                <div className="rc-sec__title">Ai giữ, để ở đâu</div>
                <div className="rc-grid">
                  <label className="rc-field">
                    <span className="rc-field__label">Bộ phận sử dụng</span>
                    <select className="rc-input" value={form.bo_phan_id}
                      onChange={(e) => set("bo_phan_id", e.target.value)}>
                      <option value="">— Chưa gán —</option>
                      {boPhan.map((b) => (
                        <option key={b.id} value={b.id}>{b.name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Người quản lý</span>
                    <input className="rc-input" value={form.nguoi_quan_ly} maxLength={255}
                      onChange={(e) => set("nguoi_quan_ly", e.target.value)} />
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Vị trí</span>
                    <input className="rc-input" value={form.vi_tri} maxLength={255}
                      placeholder="Xưởng in — dãy A"
                      onChange={(e) => set("vi_tri", e.target.value)} />
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Số hóa đơn</span>
                    <input className="rc-input" value={form.so_hoa_don} maxLength={64}
                      onChange={(e) => set("so_hoa_don", e.target.value)} />
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Nhà cung cấp</span>
                    <input className="rc-input" value={form.nha_cung_cap} maxLength={255}
                      onChange={(e) => set("nha_cung_cap", e.target.value)} />
                  </label>
                </div>
              </section>

              <section className="rc-sec">
                <div className="rc-sec__title">Ghi chú</div>
                <div className="rc-grid">
                  <label className="rc-field rc-field--full">
                    <span className="rc-field__label">Ghi chú</span>
                    <textarea className="rc-input" rows={2} maxLength={1000} value={form.ghi_chu}
                      onChange={(e) => set("ghi_chu", e.target.value)} />
                    <span className="rc-field__hint">
                      Chữ tự do, phần mềm không đọc nội dung — muốn ghi định khoản vào đây cũng được.
                    </span>
                  </label>
                </div>
              </section>

              <section className="rc-sec">
                <div className="rc-sec__title">Số dư đầu kỳ</div>
                <label className="rc-field rc-field--check">
                  <input type="checkbox" checked={form.dau_ky} disabled={sua}
                    onChange={(e) => set("dau_ky", e.target.checked)} />
                  <span className="rc-field__label">
                    Món này đã dùng TRƯỚC khi lên phần mềm — mang số dư sang
                  </span>
                </label>
                <p className="rc-field__hint">
                  Bật khi nhập sổ cũ: máy đã chạy mấy năm, phần mềm chỉ tính tiếp phần còn lại.
                  {sua && " Không đổi được sau khi đã lưu — nguồn vào là gốc của mọi con số."}
                </p>
                {form.dau_ky && (
                  <div className="rc-grid" style={{ marginTop: "var(--sp-2)" }}>
                    <label className="rc-field">
                      <span className="rc-field__label">Bắt đầu tính trên phần mềm từ <em>*</em></span>
                      <input className="rc-input" type="date" min={NGAY_MIN} max={NGAY_MAX}
                        value={form.moc_tu_ngay}
                        onChange={(e) => set("moc_tu_ngay", e.target.value)} />
                      <span className="rc-field__hint">
                        Thường là ngày 1 của tháng đầu tiên chạy phần mềm.
                      </span>
                    </label>
                    <label className="rc-field">
                      <span className="rc-field__label">Số tháng đã trích <em>*</em></span>
                      <input className="rc-input ts-num" type="number" min={1} step={1}
                        value={form.thang_da_trich_dau_ky || ""}
                        onChange={(e) => set("thang_da_trich_dau_ky", Math.max(0, Number(e.target.value) || 0))} />
                      <span className="rc-field__hint">
                        {form.so_thang > 0 && form.thang_da_trich_dau_ky > 0
                          ? `Còn lại ${Math.max(0, form.so_thang - form.thang_da_trich_dau_ky)} tháng.`
                          : "Đếm từ ngày đưa vào sử dụng tới trước mốc trên."}
                      </span>
                    </label>
                    <label className="rc-field">
                      <span className="rc-field__label">Hao mòn lũy kế <em>*</em></span>
                      <OTien value={form.hao_mon_dau_ky}
                        onChange={(v) => set("hao_mon_dau_ky", v)} />
                      <span className="rc-field__hint">
                        Còn lại chưa trích: {tienDon(Math.max(0, nguyenGia - form.hao_mon_dau_ky))}
                      </span>
                    </label>
                  </div>
                )}
              </section>
            </>
          )}
        </div>

        <footer className="rc-drawer__foot">
          {duKien ? (
            <Button variant="primary" type="button" onClick={onClose}>Xong</Button>
          ) : (
            <>
              <Button variant="ghost" type="button" onClick={onClose}>Hủy</Button>
              <Button variant="accent" type="button" loading={luu} disabled={!hopLe}
                onClick={guiDi}>
                {sua ? "Lưu thay đổi" : "Ghi tăng"}
              </Button>
            </>
          )}
        </footer>
      </aside>
    </div>
  );
}
