// Drawer TẠO / SỬA đơn mua hàng (tách từ pages/PurchaseRequestsPage.tsx).
// ⚠️ KHỐI CẤM XÉ — TÂM THUẾ: ô VAT / chiết khấu, `lineDiscountAmount`, `lineTotal` và bảng xem
// trước `phieuSeTao` phải nằm cùng nhau. Hàm `save` (validate + gọi API) CỐ Ý Ở LẠI SHELL và
// truyền xuống đây làm handler của <form>: nó chạm `rows`/`tab`/`loadSuppliers` bên đó.
import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { PurchaseRequestRow, SupplierRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { money } from "../../../../utils/format";
// Đơn vị lưu bằng MÃ (`cai`), tên hiển thị ("cái") nằm ở danh mục Đơn vị — xem pages/tenDonVi.ts.
import { tenDonVi } from "../../../tenDonVi";
import {
  applySupplierPrices,
  bestSupplierIdForLines,
  lineDiscountAmount,
  lineTotal,
} from "../shared/helpers";
import type { FormLine, FormState, PhieuSeTao } from "../shared/types";
import { LineSupplierPicker } from "./LineSupplierPicker";
import { LocalField, StatusBadge } from "./purchaseCells";

// Nhãn ĐI KÈM TỪNG Ô của lưới dòng hàng. Trên màn rộng luôn `display: none`
// (khai ở §66 của `styles/responsive.css`) nên KHÔNG chiếm ô nào của grid —
// bố cục màn rộng giữ nguyên hàng nhãn `.purchase__line-labels` như cũ. Chỉ ở
// `@media (max-width: 768px)` nhãn mới bật lên, vì ở đó `purchase.css:1967` ẩn
// hàng nhãn còn lưới xếp một cột: không có nhãn thì người dùng nhìn dãy ô số
// "18000 · 5 · 8" mà không biết đâu là Đơn giá đâu là VAT — biểu mẫu này SINH
// ĐƠN MUA và ghi tiền nên nhầm ô là ra đơn sai tiền.
// `aria-hidden` vì mỗi ô đã có `aria-label` riêng, không đọc lặp hai lần.
function NhanO({ chu, sao }: { chu: string; sao?: boolean }) {
  return (
    <span className="purchase__line-lb" aria-hidden="true">
      {chu}
      {sao ? <span className="purchase__required-star"> *</span> : null}
    </span>
  );
}

export function PurchaseFormDrawer({
  mode,
  setMode,
  editing,
  form,
  setForm,
  setLine,
  save,
  saving,
  formError,
  suppliers,
  minPurchaseDate,
  expectedReceiptMinDate,
  phieuSeTao,
}: {
  mode: "create" | "edit";
  setMode: Dispatch<SetStateAction<null | "create" | "edit">>;
  editing: PurchaseRequestRow | null;
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  setLine: (index: number, patch: Partial<FormLine>) => void;
  /** Chính là `save` của shell — đừng bê nó vào đây. */
  save: (e: FormEvent) => Promise<void>;
  saving: boolean;
  formError: string | null;
  suppliers: SupplierRow[];
  minPurchaseDate: string;
  expectedReceiptMinDate: string;
  phieuSeTao: PhieuSeTao[];
}) {
  return (
    <div className="rc-drawer__scrim" role="presentation">
      <aside
        className="rc-drawer purchase__drawer-780"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={
          mode === "edit"
            ? editing?.code ?? "Sửa đơn mua hàng"
            : "Đơn mua hàng mới"
        }
      >
        <div className="purchase__hero-banner">
          <div className="purchase__hero-top">
            <div>
              <span className="purchase__hero-kicker">
                {mode === "edit" ? "Sửa đơn mua hàng" : "Tạo đơn mua hàng"}
              </span>
              <div className="purchase__hero-title-row">
                <h2 className="purchase__hero-code">
                  {mode === "edit" ? editing?.code : "Đơn mua hàng mới"}
                </h2>
                {mode === "edit" && editing && (
                  <StatusBadge status={editing.status} />
                )}
              </div>
            </div>
            <button
              type="button"
              className="purchase__hero-x"
              onClick={() => setMode(null)}
              aria-label="Đóng"
            >
              ✕
            </button>
          </div>
          <div className="purchase__hero-meta">
            {mode === "edit" ? (
              <>
                <span>{editing?.supplier_name || "Chưa chọn"}</span>
                <span className="purchase__hero-dot">•</span>
                <span>{form.lines.length} mặt hàng</span>
              </>
            ) : (
              <>
                <span>{form.lines.length} mặt hàng</span>
                {form.source_request_ids.length > 0 && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>
                      {form.source_request_ids.length} yêu cầu nguồn
                    </span>
                  </>
                )}
              </>
            )}
          </div>
        </div>
        <form onSubmit={save} className="purchase__drawer-form">
          <div className="rc-drawer__body">
          {formError && (
            <div className="banner banner--error" role="alert">
              {formError}
            </div>
          )}
          <div className="md-page__form-grid">
            {/* Ô NCC ở ĐẦU PHIẾU chỉ còn cho chế độ SỬA: phiếu đã tồn tại thì nó vốn thuộc về
                một nhà cung cấp. Lúc TẠO thì NCC gán ở từng DÒNG, vì một yêu cầu thường chứa
                hàng của nhiều nơi và mỗi NCC phải ra một phiếu riêng. */}
            {mode === "edit" && (
            <LocalField label="Nhà cung cấp" required>
              <select
                className="input"
                required
                value={form.supplier_id ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    supplier_id: e.target.value ? Number(e.target.value) : null,
                    lines: applySupplierPrices(
                      form.lines,
                      suppliers,
                      e.target.value ? Number(e.target.value) : null,
                    ),
                  })
                }
              >
                <option value="">Chọn nhà cung cấp</option>
                {suppliers.map((supplier) => {
                  const bestId = bestSupplierIdForLines(form.lines, suppliers);
                  const bestHint =
                    supplier.id === bestId ? " - giá thấp nhất" : "";
                  return (
                    <option key={supplier.id} value={supplier.id}>
                      {`${supplier.name}${bestHint}`}
                    </option>
                  );
                })}
              </select>
            </LocalField>
            )}
            <LocalField label="Ngày cần hàng" required>
              <input
                className="input"
                type="date"
                required
                min={minPurchaseDate}
                value={form.needed_date ?? ""}
                onChange={(e) =>
                  setForm({ ...form, needed_date: e.target.value })
                }
              />
            </LocalField>
            {/* NGÀY NHẬN HÀNG CHỈ KHAI ĐƯỢC Ở CHẾ ĐỘ SỬA (chủ chốt 28/08/2026).
                Lúc TẠO, phiếu này tách thành N đơn theo NCC — mà ô ở đây chỉ có MỘT, nên nó
                đóng cùng một ngày lên cả N đơn dù mỗi NCC hẹn một ngày khác nhau. Không phải
                lỗi trưng bày: ngày này là "ngày hàng về" của kế hoạch vật tư
                (`ke_hoach_vat_tu_service.tinh_cung`), chép nhầm là bơm số sai vào đường cung.
                Chế độ SỬA thì đúng — ở đó một phiếu = một NCC = một ngày. */}
            {mode === "edit" && (
            <LocalField label="Ngày dự kiến nhận hàng">
              <input
                className="input"
                type="date"
                min={expectedReceiptMinDate}
                value={form.expected_receipt_date ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    expected_receipt_date: e.target.value,
                  })
                }
              />
            </LocalField>
            )}
            {/* MỘT ô thay cho cặp "Mục đích" + "Ghi chú" (chủ chốt 07/08/2026) — xem
                DepartmentPurchaseRequestsPage cho lý do. */}
            <LocalField label="Nội dung / mục đích" wide required>
              <textarea
                className="input purchase__textarea"
                required
                value={form.content ?? ""}
                onChange={(e) =>
                  setForm({ ...form, content: e.target.value })
                }
                placeholder="Ví dụ: mua giấy cho đơn hàng ĐH-2026-031, giao trước 20/8"
              />
            </LocalField>
          </div>

          <div className="purchase__form-section">
            <div className="purchase__form-section-head">
              <h3>Dòng hàng</h3>
              {/* KHÔNG có nút thêm dòng: danh sách hàng lấy nguyên từ yêu cầu của bộ phận.
                  Thu mua thêm được một dòng thì thành mua thứ không ai xin. Cần mua thêm thì
                  bộ phận gửi yêu cầu mới, để còn có người duyệt. */}
              <span className="md-page__muted">
                Lấy từ yêu cầu — Thu mua chọn nhà cung cấp và giá
              </span>
            </div>
            <div
              className={`purchase__line-editor${
                mode !== "edit" ? " purchase__line-editor--tach-ncc" : ""
              }`}
            >
              <div className="purchase__line-labels" aria-hidden="true">
                <span>
                  Vật tư <span className="purchase__required-star">*</span>
                </span>
                {mode !== "edit" && (
                  <span>
                    Nhà cung cấp{" "}
                    <span className="purchase__required-star">*</span>
                  </span>
                )}
                <span>
                  ĐVT <span className="purchase__required-star">*</span>
                </span>
                <span>
                  Số lượng{" "}
                  <span className="purchase__required-star">*</span>
                </span>
                <span>
                  Đơn giá <span className="purchase__required-star">*</span>
                </span>
                <span>Giảm (%)</span>
                <span>Tiền giảm</span>
                <span>VAT (%)</span>
                <span>Ghi chú dòng</span>
                <span>Thành tiền</span>
                <span></span>
              </div>
              {form.lines.map((line, index) => (
                <div className="purchase__line-edit" key={index}>
                  {/* Vật tư và ĐVT do BỘ PHẬN ĐỀ NGHỊ quyết, thu mua không được đổi — đổi ở
                      đây là mua thứ khác với thứ người ta xin mà không ai hay. Thu mua chỉ
                      chọn MUA CỦA AI và giá. Cùng lý do: không thêm/xoá dòng. */}
                  <NhanO chu="Vật tư" sao />
                  <input
                    className="input purchase__line-name purchase__readonly-field"
                    required
                    readOnly
                    aria-label="Tên vật tư"
                    title="Vật tư do bộ phận đề nghị khai — Thu mua không sửa được"
                    value={line.item_name}
                  />
                  {mode !== "edit" && <NhanO chu="Nhà cung cấp" sao />}
                  {mode !== "edit" && (
                    <LineSupplierPicker
                      line={line}
                      suppliers={suppliers}
                      onPick={(chao) =>
                        setLine(index, {
                          supplier_id: chao?.supplier_id ?? null,
                          // Chọn NCC là lấy luôn GIÁ CỦA CHÍNH HỌ — để người dùng gõ lại là
                          // mở đường cho việc đặt một đằng, giá một nẻo.
                          ...(chao
                            ? {
                                // ĐVT giữ nguyên của DÒNG (đơn vị gốc — cả YCMH lẫn đơn mua đều
                                // khoá về gốc). KHÔNG lấy `chao.unit`: NCC báo theo ram mà dòng
                                // tính theo tờ thì đơn vị phải là tờ.
                                unit: line.unit || chao.unit,
                                // ⚠️ GIÁ ĐÃ QUY ĐỔI, không phải giá thô (29/08/2026). NCC báo
                                // 1.020.000đ/ram, dòng tính theo tờ (1 ram = 500 tờ) ⇒ phải điền
                                // 2.040đ/tờ. Lấy giá thô là dòng đơn thành 1.000 tờ × 1.020.000đ,
                                // sai 500 lần mà không có gì chặn — đúng cái lỗ mở ra khi bảng
                                // giá NCC được phép khai đơn vị khác gốc.
                                // Chưa quy đổi được (`null`) thì lùi về giá thô: mặt hàng ngoài
                                // danh mục vốn không có đơn vị gốc nào để mà lệch.
                                expected_unit_price: chao.gia_quy_doi ?? chao.unit_price,
                                vat_percent: chao.vat_percent,
                              }
                            : {}),
                        })
                      }
                    />
                  )}
                  {/* ĐVT + SỐ LƯỢNG là số liệu bộ phận đề nghị khai, Thu mua KHÔNG sửa được. Nên
                      để là THẺ CHỮ chứ không phải `<input readOnly>`:
                       - `<input>` trong bảng này bị ép `width: 100%` của ô, mà bề rộng ô lại do
                         TIÊU ĐỀ quyết định — nội dung dài hơn thì tràn ra ngoài một cách vô hình
                         ("500.000.000" cụt còn "500.000."). Thẻ chữ thì cột tự nở vừa nội dung.
                       - Hộp nhập rỗng mời người ta bấm vào gõ, rồi phát hiện không gõ được.
                      Đơn vị hiện TÊN ("cái") chứ không phải mã (`cai`); `line.unit` trong state vẫn
                      giữ mã và đó mới là thứ gửi lên. */}
                  <NhanO chu="ĐVT" sao />
                  <span
                    className="input purchase__line-unit purchase__readonly-field"
                    aria-label="Đơn vị tính"
                    title={`${tenDonVi(line.unit) ?? line.unit} — đơn vị tính do bộ phận đề nghị khai, Thu mua không sửa được`}
                  >
                    {tenDonVi(line.unit) ?? line.unit}
                  </span>
                  <NhanO chu="Số lượng" sao />
                  <span
                    className="input purchase__number-input purchase__readonly-field"
                    aria-label="Số lượng"
                    title={
                      // Số ĐẦY ĐỦ đứng TRƯỚC: ô hẹp thì chữ bị cắt "…", và thứ người ta rê chuột
                      // vào để xem là CON SỐ, không phải câu giải thích.
                      line.quantity > 0
                        ? `${line.quantity.toLocaleString("vi-VN")} ${tenDonVi(line.unit) ?? line.unit} — số lượng do bộ phận đề nghị khai, Thu mua không sửa được`
                        : "Số lượng do bộ phận đề nghị khai — Thu mua không sửa được"
                    }
                  >
                    {line.quantity > 0
                      ? line.quantity.toLocaleString("vi-VN")
                      : ""}
                  </span>
                  <NhanO chu="Đơn giá" sao />
                  <input
                    className="input purchase__number-input"
                    type="number"
                    min="1"
                    step="1"
                    required
                    aria-label="Đơn giá dự kiến"
                    placeholder="VD: 2200"
                    value={
                      line.expected_unit_price > 0
                        ? line.expected_unit_price
                        : ""
                    }
                    onChange={(e) =>
                      setLine(index, {
                        expected_unit_price: Number(e.target.value || 0),
                      })
                    }
                  />
                  <NhanO chu="Giảm (%)" />
                  <input
                    className="input purchase__number-input"
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    aria-label="Giảm giá phần trăm"
                    placeholder="VD: 5"
                    value={
                      line.discount_percent > 0 ? line.discount_percent : ""
                    }
                    onChange={(e) =>
                      setLine(index, {
                        discount_percent: Number(e.target.value || 0),
                      })
                    }
                  />
                  <NhanO chu="Tiền giảm" />
                  <strong className="purchase__line-sum">
                    {lineDiscountAmount(line) > 0 ? (
                      money(lineDiscountAmount(line))
                    ) : (
                      <span className="md-page__muted">0 đ</span>
                    )}
                  </strong>
                  <NhanO chu="VAT (%)" />
                  <input
                    className="input purchase__number-input"
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    aria-label="Thuế GTGT phần trăm"
                    placeholder="VD: 8"
                    value={line.vat_percent > 0 ? line.vat_percent : ""}
                    onChange={(e) =>
                      setLine(index, {
                        vat_percent: Number(e.target.value || 0),
                      })
                    }
                  />
                  <NhanO chu="Ghi chú dòng" />
                  <input
                    className="input purchase__line-note"
                    aria-label="Ghi chú dòng"
                    placeholder="Nếu có"
                    value={line.note ?? ""}
                    onChange={(e) =>
                      setLine(index, { note: e.target.value })
                    }
                  />
                  {/* `title` = số ĐẦY ĐỦ. Ô có cắt gọn "…" cho ca tiền quá lớn (xem
                      `.purchase__line-sum`), nên phải luôn có đường đọc lại trọn con số — cắt mất
                      chữ số của một ô TIỀN mà không cách nào xem lại là kiểu giấu số tệ nhất. */}
                  <NhanO chu="Thành tiền" />
                  <strong
                    className="purchase__line-sum"
                    title={
                      line.quantity > 0 && line.expected_unit_price > 0
                        ? money(lineTotal(line))
                        : undefined
                    }
                  >
                    {line.quantity > 0 && line.expected_unit_price > 0 ? (
                      money(lineTotal(line))
                    ) : (
                      <span className="md-page__muted">Chưa tính</span>
                    )}
                  </strong>
                  {/* Ô trống giữ chỗ cột cuối — bỏ hẳn thì lưới lệch một cột. Không cho xoá
                      dòng vì bỏ bớt là mua thiếu so với thứ bộ phận đã xin, mà phiếu vẫn
                      trông như đã xử lý xong yêu cầu đó. */}
                  <span aria-hidden="true" />
                </div>
              ))}
            </div>
            <div className="purchase__form-total">
              <span>Tổng dự kiến</span>
              <strong>
                {money(
                  form.lines.reduce(
                    (sum, line) => sum + lineTotal(line),
                    0,
                  ),
                )}
              </strong>
            </div>
            {/* Nói TRƯỚC sẽ đẻ ra mấy phiếu. Bấm Lưu rồi mới thấy danh sách nhảy thêm mấy
                dòng là bất ngờ không đáng có — và người dùng cần biết để còn đổi NCC. */}
            {mode !== "edit" && phieuSeTao.length > 0 && (
              <p className="md-page__muted" style={{ marginTop: 4 }}>
                Sẽ tạo <strong>{phieuSeTao.length} đơn</strong> —{" "}
                {phieuSeTao
                  .map(
                    (p) =>
                      `${p.ten}: ${p.soDong} dòng / ${money(p.tien)}`,
                  )
                  .join(" · ")}
              </p>
            )}
          </div>
          </div>
          <div className="purchase__drawer-footer">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setMode(null)}
              disabled={saving}
            >
              Hủy
            </button>
            <Button type="submit" variant="accent" loading={saving}>
              Lưu đơn
            </Button>
          </div>
        </form>
      </aside>
    </div>
  );
}
