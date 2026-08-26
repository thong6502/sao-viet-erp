// Tab 1 của drawer Nhà cung cấp — "Thông tin chung & Pháp lý" (tách từ pages/SuppliersPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import type { SupplierInput, SupplierRow } from "../../../../api/client";
import { LocalField } from "../components/LocalField";
import { SaoNcc } from "../components/SaoNcc";
import { soNgayVi } from "../shared/helpers";

/** Khối SAO — chỉ ĐỌC, nằm trên đầu hồ sơ. KHÔNG có ô chấm tay ở đâu cả: điểm gõ tay là ý kiến,
 *  còn con số ở đây truy ngược được về từng phiếu mua hàng.
 *
 *  Chỉ hiện khi đang MỞ hồ sơ có sẵn (`selected`); lúc thêm mới thì NCC còn chưa tồn tại, treo
 *  "Chưa đánh giá" ở đó chỉ là một dòng thừa. */
function KhoiSao({ ncc }: { ncc: SupplierRow }) {
  const chuaCham = ncc.rating === null;
  return (
    <div className="supplier__sao-box" aria-label="Đánh giá nhà cung cấp">
      <div className="supplier__sao-box-head">
        <SaoNcc rating={ncc.rating} cao={17} />
        <span className="supplier__sao-box-lbl">Đánh giá giao hàng</span>
      </div>
      <p className="supplier__sao-box-sub">
        {chuaCham ? (
          <>
            Chưa có đơn hàng nào đủ dữ liệu để chấm. Sao sẽ tự hiện sau đơn đầu tiên —{" "}
            <strong>không phải 0 sao</strong>, chỉ là chưa có gì để nói.
          </>
        ) : (
          <>
            Tính từ <strong>{ncc.rating_count}</strong> đơn · đúng hẹn{" "}
            <strong>
              {ncc.on_time_count}/{ncc.rating_count}
            </strong>
            {ncc.late_count > 0 && (
              <>
                {" "}· trễ <strong>{ncc.late_count}</strong> đơn, trung bình{" "}
                <strong>{soNgayVi(ncc.avg_late_days)} ngày</strong>
              </>
            )}
          </>
        )}
      </p>
      <p className="supplier__sao-box-note">
        Máy tự tính, không ai chấm tay: so ngày giao đủ với <em>Ngày cần hàng</em> trên phiếu mua.
        Đúng hẹn hoặc sớm = 5 sao; trễ 1–3 ngày = 4; 4–7 = 3; 8–14 = 2; trên 14 ngày = 1.
      </p>
    </div>
  );
}

export function SupplierInfoTab({
  form,
  setForm,
  selected,
}: {
  form: SupplierInput;
  setForm: Dispatch<SetStateAction<SupplierInput>>;
  /** Hồ sơ đang mở — `null` khi đang THÊM MỚI. Chỉ dùng để đọc sao, không dính vào form. */
  selected: SupplierRow | null;
}) {
  return (
                  <div className="md-page__form-grid">
                    {selected && (
                      <div className="md-page__form-wide">
                        <KhoiSao ncc={selected} />
                      </div>
                    )}

                    <LocalField label="Tên nhà cung cấp" required>
                      <input
                        className="input"
                        required
                        value={form.name}
                        onChange={(e) =>
                          setForm({ ...form, name: e.target.value })
                        }
                        placeholder="VD: Công ty TNHH Giấy Việt Triều"
                      />
                    </LocalField>

                    <LocalField label="Nhóm" required>
                      <input
                        className="input"
                        required
                        value={form.supplier_group ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, supplier_group: e.target.value })
                        }
                        placeholder="Giấy in, Mực & Hóa chất, Gia công ngoài..."
                      />
                    </LocalField>

                    <LocalField label="Mã số thuế" required>
                      <input
                        className="input md-page__mono"
                        required
                        value={form.tax_code ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, tax_code: e.target.value })
                        }
                        placeholder="0101234567"
                      />
                    </LocalField>

                    <LocalField label="Người liên hệ" required>
                      <input
                        className="input"
                        required
                        value={form.contact_name ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, contact_name: e.target.value })
                        }
                        placeholder="VD: Anh Nam (Kinh doanh)"
                      />
                    </LocalField>

                    <LocalField label="Số điện thoại" required>
                      <input
                        className="input"
                        required
                        value={form.phone ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, phone: e.target.value })
                        }
                        placeholder="0988123456"
                      />
                    </LocalField>

                    <LocalField label="Email" required>
                      <input
                        className="input"
                        required
                        type="email"
                        value={form.email ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, email: e.target.value })
                        }
                        placeholder="kinhdoanh@viettrieu.vn"
                      />
                    </LocalField>

                    <LocalField label="Điều khoản thanh toán">
                      <input
                        className="input"
                        value={form.payment_terms ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, payment_terms: e.target.value })
                        }
                        placeholder="Công nợ 30 ngày, Thanh toán ngay..."
                      />
                    </LocalField>

                    {/* HẠN MỨC + SỐ NGÀY CHO NỢ — nền của cảnh báo "Vượt hạn mức" và cột "Quá
                        hạn" ở màn Công nợ. Cả hai là CẢNH BÁO MỀM: hệ nói cho người biết, người
                        quyết — không chặn lập/duyệt phiếu ở đâu cả. */}
                    <LocalField label="Hạn mức công nợ (VNĐ)">
                      <input
                        className="input"
                        type="number"
                        min={0}
                        step={1000}
                        value={form.credit_limit ? form.credit_limit : ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            credit_limit: Math.max(
                              0,
                              Math.round(Number(e.target.value) || 0),
                            ),
                          })
                        }
                        placeholder="Để trống = không đặt hạn mức"
                      />
                      <small className="supplier__hint">
                        Để trống hoặc 0 = không đặt hạn mức, sẽ không bao giờ
                        báo vượt.
                      </small>
                    </LocalField>

                    <LocalField label="Số ngày cho nợ">
                      {/* Hai ca KHÁC HẲN NHAU, đừng ép null thành 0: để trống = chưa đặt hạn (đợt
                          giao không vào cột Quá hạn) · 0 = trả ngay (quá hạn ngay hôm sau). */}
                      <input
                        className="input"
                        type="number"
                        min={0}
                        step={1}
                        value={form.credit_days ?? ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            credit_days:
                              e.target.value === ""
                                ? null
                                : Math.max(
                                    0,
                                    Math.round(Number(e.target.value) || 0),
                                  ),
                          })
                        }
                        placeholder="Để trống = chưa đặt hạn"
                      />
                      <small className="supplier__hint">
                        Để trống = <strong>chưa đặt hạn</strong>, đợt giao không
                        vào cột Quá hạn. Nhập <strong>0</strong> = trả ngay.
                      </small>
                    </LocalField>

                    <LocalField label="Trạng thái">
                      <select
                        className="input"
                        value={form.status ?? "active"}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            status: e.target.value as "active" | "inactive",
                          })
                        }
                      >
                        <option value="active">Hoạt động (Active)</option>
                        <option value="inactive">Tạm ngừng (Inactive)</option>
                      </select>
                    </LocalField>

                    <LocalField label="Địa chỉ" wide required>
                      <input
                        className="input"
                        required
                        value={form.address ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, address: e.target.value })
                        }
                        placeholder="Số 15, Đường Cầu Diễn, Bắc Từ Liêm, Hà Nội"
                      />
                    </LocalField>

                    <LocalField label="Ghi chú" wide>
                      <textarea
                        className="input purchase__textarea"
                        value={form.note ?? ""}
                        onChange={(e) =>
                          setForm({ ...form, note: e.target.value })
                        }
                        placeholder="Ghi chú thêm về năng lực, ưu đãi chiết khấu..."
                      />
                    </LocalField>
                  </div>
  );
}
