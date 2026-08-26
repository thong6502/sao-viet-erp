// Tab 2 của drawer Nhà cung cấp — "Bảng giá vật tư": nhập/xuất Excel + bảng giá từng mặt hàng
// (tách từ pages/SuppliersPage.tsx).
// `token` lấy bằng `useAuth()` tại chỗ như bản gốc, KHÔNG luồn thêm prop: các chỗ dưới vẫn viết
// `token!` / `token ?? ""` y nguyên.
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import type { SupplierInput, SupplierRow } from "../../../../api/client";
import { api } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import {
  DonViChonTheoHang,
  MaterialCombobox,
} from "../../../../components/MaterialCombobox";
import { money } from "../../../../utils/format";
import { emptySupplierItem } from "../shared/helpers";
import type {
  FormItemRow,
  NhapKetQua,
  QuyDoiDongInfo,
} from "../shared/types";

export function SupplierItemsTab({
  mode,
  selected,
  setForm,
  itemsInForm,
  filteredFormItems,
  itemSearchQ,
  setItemSearchQ,
  setSupplierItem,
  quyDoiDong,
  ghiQuyDoiDong,
  fileVatTuRef,
  nhapDang,
  nhapKetQua,
  setNhapKetQua,
  nhapExcel,
  taiFile,
}: {
  mode: null | "create" | "edit";
  selected: SupplierRow | null;
  setForm: Dispatch<SetStateAction<SupplierInput>>;
  itemsInForm: SupplierInput["items"] & object;
  filteredFormItems: FormItemRow[];
  itemSearchQ: string;
  setItemSearchQ: Dispatch<SetStateAction<string>>;
  setSupplierItem: (
    index: number,
    patch: Partial<FormItemRow["item"]>,
  ) => void;
  quyDoiDong: Record<number, QuyDoiDongInfo | null>;
  ghiQuyDoiDong: (index: number, info: QuyDoiDongInfo | null) => void;
  fileVatTuRef: MutableRefObject<HTMLInputElement | null>;
  nhapDang: boolean;
  nhapKetQua: NhapKetQua | null;
  setNhapKetQua: Dispatch<SetStateAction<NhapKetQua | null>>;
  nhapExcel: (file: File) => Promise<void>;
  taiFile: (lay: () => Promise<string>, ten: string) => Promise<void>;
}) {
  const { token } = useAuth();
  return (
                  <section className="supplier__items-section">
                    <div className="supplier__items-head">
                      <div>
                        <h3 style={{ fontSize: "16px", fontWeight: "bold" }}>
                          Danh mục &amp; Báo giá Vật tư
                        </h3>
                        <p className="md-page__muted">
                          Khai báo đơn giá &amp; VAT hiện tại để gợi ý tự động
                          khi lập Phiếu Mua Hàng.
                        </p>
                      </div>
                      <div className="supplier__items-actions">
                        {/* Tải mẫu đứng TRƯỚC Nhập: thứ tự nút là thứ tự việc phải làm. */}
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() =>
                            taiFile(
                              () => api.suppliers.itemsTemplateBlobUrl(token!),
                              "mau-vat-tu-nha-cung-cap.xlsx",
                            )
                          }
                        >
                          Tải mẫu
                        </button>
                        {/* Xuất chỉ có nghĩa với NCC ĐÃ LƯU — NCC đang tạo mới chưa có id. */}
                        {mode === "edit" && selected && (
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() =>
                              taiFile(
                                () =>
                                  api.suppliers.itemsExportBlobUrl(
                                    token!,
                                    selected.id,
                                  ),
                                `vat-tu-${selected.id}.xlsx`,
                              )
                            }
                          >
                            Xuất Excel
                          </button>
                        )}
                        <input
                          ref={fileVatTuRef}
                          type="file"
                          accept=".xlsx"
                          style={{ display: "none" }}
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            // Xoá value ngay: chọn LẠI đúng file vừa chọn vẫn phải bắn onChange.
                            e.target.value = "";
                            if (file) void nhapExcel(file);
                          }}
                        />
                        <button
                          type="button"
                          className="btn btn--ghost"
                          disabled={nhapDang}
                          onClick={() => fileVatTuRef.current?.click()}
                        >
                          {nhapDang ? "Đang đọc..." : "Nhập Excel"}
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() =>
                            setForm((current) => ({
                              ...current,
                              items: [
                                ...(current.items ?? []),
                                emptySupplierItem(),
                              ],
                            }))
                          }
                        >
                          + Thêm mặt hàng
                        </button>
                      </div>
                    </div>

                    {nhapKetQua && (
                      <div className="supplier__import-result">
                        <div className="supplier__import-head">
                          <strong>
                            Đã nạp {nhapKetQua.them} mặt hàng mới
                            {nhapKetQua.capNhat > 0
                              ? `, cập nhật ${nhapKetQua.capNhat} mặt hàng`
                              : ""}
                            .
                          </strong>
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() => setNhapKetQua(null)}
                          >
                            Đóng
                          </button>
                        </div>
                        {/* Nói rõ CHƯA vào sổ: người dùng đóng drawer là mất sạch phần vừa nhập. */}
                        <p className="md-page__muted">
                          Chưa lưu — kiểm lại bảng dưới rồi bấm{" "}
                          <strong>Lưu nhà cung cấp</strong>. Tối đa 500 dòng /
                          file, mỗi file cho một nhà cung cấp.
                        </p>
                        {nhapKetQua.errors.length > 0 && (
                          <ul className="supplier__import-errors">
                            {nhapKetQua.errors.map((e) => (
                              <li key={`${e.row}-${e.message}`}>
                                <strong>Dòng {e.row}:</strong> {e.message}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* Toolbar tìm kiếm vật tư trong drawer */}
                    <div
                      style={{
                        display: "flex",
                        gap: "10px",
                        alignItems: "center",
                      }}
                    >
                      <input
                        className="input"
                        placeholder="Tìm vật tư trong bảng giá..."
                        value={itemSearchQ}
                        onChange={(e) => setItemSearchQ(e.target.value)}
                        style={{ maxWidth: "280px" }}
                      />
                      <span
                        className="md-page__muted"
                        style={{ fontSize: "13px" }}
                      >
                        Hiển thị {filteredFormItems.length} /{" "}
                        {itemsInForm.length} vật tư
                      </span>
                    </div>

                    {/* Table Editor */}
                    <div className="supplier__item-editor">
                      <div
                        className="supplier__item-labels"
                        aria-hidden="true"
                        style={{
                          gridTemplateColumns:
                            "minmax(170px, 1.3fr) minmax(70px, 0.5fr) minmax(105px, 0.75fr) minmax(120px, 0.85fr) minmax(60px, 0.45fr) minmax(110px, 0.75fr) minmax(78px, 0.5fr) minmax(110px, 0.85fr) 36px",
                        }}
                      >
                        <span>Tên vật tư *</span>
                        <span>ĐVT *</span>
                        <span>Đơn giá (chưa VAT) *</span>
                        <span title="Quy giá về đơn vị gốc của mặt hàng để so ngang giữa các NCC (ông báo đ/ram, ông báo đ/kg).">
                          Giá quy về gốc
                        </span>
                        <span>VAT %</span>
                        <span>Giá sau VAT</span>
                        {/* BỎ 10/08/2026 cột "Giao (ngày)" (mg 0176): lúc khai danh mục NCC thì
                            chưa ai biết ông ấy giao mấy ngày — số gõ vào là số đoán, mà kế hoạch
                            lại dựa vào đó để báo trễ. Cần lại thì SUY từ lịch sử mua (ngày đặt →
                            ngày nhận thật), đừng bắt khai tay. */}
                        <span>Ghi chú</span>
                        <span></span>
                      </div>

                      {filteredFormItems.map(({ item, originalIndex }) => {
                        const priceAfterVAT =
                          (item.unit_price || 0) *
                          (1 + (item.vat_percent || 0) / 100);
                        // Cùng công thức server dùng ở `/api/supplier-items/so-gia`: 1 đơn vị NCC
                        // bán bằng `heSoVeGoc` đơn vị gốc ⇒ giá/đơn-vị-gốc = giá ÷ hệ số. Hệ số
                        // lấy TỪ SERVER (không tự suy ở FE) nên hai nơi không thể lệch.
                        const quyDoi = quyDoiDong[originalIndex];
                        const giaVeGoc =
                          quyDoi && item.unit_price > 0
                            ? Math.round(item.unit_price / quyDoi.heSoVeGoc)
                            : null;

                        return (
                          <div
                            className="supplier__item-row"
                            key={originalIndex}
                            style={{
                              gridTemplateColumns:
                                "minmax(170px, 1.3fr) minmax(70px, 0.5fr) minmax(105px, 0.75fr) minmax(120px, 0.85fr) minmax(60px, 0.45fr) minmax(110px, 0.75fr) minmax(78px, 0.5fr) minmax(110px, 0.85fr) 36px",
                            }}
                          >
                            {/* CHỌN từ danh mục gốc, không gõ tự do nữa: ghép NCC với kho bằng
                                chuỗi tên là trượt thầm lặng ("Couche 150" ≠ "Couché 150 79×109"),
                                mà trượt thì mãi không so được giá. Đổi mặt hàng → xoá đơn vị cũ,
                                vì đơn vị dùng được phụ thuộc chính mặt hàng. */}
                            <MaterialCombobox
                              token={token ?? ""}
                              hangTen={item.item_name || null}
                              onPick={(m) =>
                                setSupplierItem(originalIndex, {
                                  hang_loai: m.hang_loai,
                                  hang_id: m.hang_id,
                                  item_name: m.ten,
                                  unit: "",
                                })
                              }
                              placeholder="Gõ tên vật tư…"
                            />
                            {item.hang_loai && item.hang_id ? (
                              /* ĐVT = ĐÚNG đơn vị gốc của mặt hàng, KHÔNG cho chọn (chủ chốt
                                 15/08/2026, sau khi nghe rõ đánh đổi bên dưới).
                                 Lý do: hai NCC cùng bán một món, một bên ghi "cái" một bên ghi
                                 "con" — cùng một lượng, khác mỗi cách gọi — thì mọi thứ đối chiếu
                                 sang YCMH/kho đều lệch mà không ai thấy.
                                 ĐÁNH ĐỔI ĐÃ BIẾT: NCC báo giá theo ram/tấn nay phải tự quy về
                                 tờ/kg trước khi nhập; cột "giá về gốc" bên phải vì thế luôn bằng
                                 chính đơn giá. Máy chủ VẪN nhận đơn vị quy đổi (dòng cũ khai theo
                                 ram còn nguyên, không bị viết lại) — hàng rào này chỉ ở màn nhập. */
                              <DonViChonTheoHang
                                chiDoc
                                token={token ?? ""}
                                hangLoai={item.hang_loai}
                                hangId={item.hang_id}
                                value={item.unit}
                                onChange={(ma) =>
                                  setSupplierItem(originalIndex, { unit: ma })
                                }
                                onQuyDoi={(info) => ghiQuyDoiDong(originalIndex, info)}
                              />
                            ) : (
                              // Chưa chọn mặt hàng → chưa biết đơn vị. Trước đây cho gõ tự do; gõ
                              // tự do là mở đường cho đơn vị lạ ("thùg") lọt vào, quy đổi tắt lặng
                              // lẽ và giá không quy về gốc được để so giữa các NCC.
                              // Dùng CHUNG dáng chỉ-đọc với nhánh trên: hai trạng thái của cùng
                              // một ô mà một bên là ô nhập khoá, một bên là chữ, thì nhìn như lỗi.
                              <span
                                className="kho-dv__ro kho-dv__ro--trong"
                                title="Chọn vật tư trước"
                              >
                                {item.unit || "—"}
                              </span>
                            )}
                            <input
                              className="input purchase__number-input"
                              type="number"
                              min="0"
                              step="1"
                              placeholder="2200"
                              value={item.unit_price > 0 ? item.unit_price : ""}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  unit_price: Number(e.target.value || 0),
                                })
                              }
                            />
                            <div
                              className="supplier-item-vat-calculated"
                              title={
                                giaVeGoc
                                  ? `${money(item.unit_price)} / ${item.unit} ÷ ${quyDoi!.heSoVeGoc} = ${money(giaVeGoc)} / ${quyDoi!.donViGocTen}`
                                  : "Gắn mặt hàng gốc + chọn đơn vị đổi được thì mới quy đổi được."
                              }
                            >
                              {giaVeGoc
                                ? `${money(giaVeGoc)}/${quyDoi!.donViGocTen}`
                                : "—"}
                            </div>
                            <input
                              className="input purchase__number-input"
                              type="number"
                              min="0"
                              max="100"
                              step="0.01"
                              placeholder="10"
                              value={
                                (item.vat_percent ?? 0) >= 0
                                  ? item.vat_percent
                                  : ""
                              }
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  vat_percent: Number(e.target.value || 0),
                                })
                              }
                            />
                            <div className="supplier-item-vat-calculated">
                              {item.unit_price > 0 ? money(priceAfterVAT) : "—"}
                            </div>
                            <input
                              className="input"
                              placeholder="Nếu có"
                              value={item.note ?? ""}
                              onChange={(e) =>
                                setSupplierItem(originalIndex, {
                                  note: e.target.value,
                                })
                              }
                            />
                            <button
                              type="button"
                              className="supplier__item-remove"
                              disabled={itemsInForm.length <= 1}
                              title="Xóa dòng"
                              aria-label="Xóa mặt hàng"
                              onClick={() =>
                                setForm((current) => ({
                                  ...current,
                                  items: (current.items ?? []).filter(
                                    (_, i) => i !== originalIndex,
                                  ),
                                }))
                              }
                            >
                              ×
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </section>
  );
}
