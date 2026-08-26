// Hộp thoại TẠO / SỬA yêu cầu mua hàng — đầu phiếu + bảng dòng vật tư
// (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
// `token` lấy bằng `useAuth()` tại chỗ như bản gốc, KHÔNG luồn thêm prop: hai ô chọn vật tư bên
// dưới vẫn viết `token={token ?? ""}` y nguyên.
// 26/08/2026 — vỏ chuyển từ modal giữa màn (`md-page__overlay` + `md-page__dialog`) sang KHUÔN
// DRAWER của Thu mua (`rc-drawer` + `purchase__hero-banner` + `purchase__drawer-form` +
// `purchase__drawer-footer`), chủ chốt: "sao mỗi nơi một màu". Bản cũ đã có sẵn hero-banner nên
// chỉ là chuyển đổi DỞ DANG. Đây là FORM NHẬP LIỆU (bảng dòng vật tư đang gõ) nên đóng AN TOÀN:
// scrim KHÔNG bắt click, KHÔNG Esc-to-close — chỉ ✕ và nút Hủy. Toàn bộ `save` / validate / bảng
// dòng giữ NGUYÊN — chỉ đổi vỏ.
import type { Dispatch, FormEvent, SetStateAction } from "react";
import type {
  DepartmentPurchaseRequestInput,
  DepartmentPurchaseRequestRow,
  DepartmentPurchaseRequestLineInput,
} from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import {
  DonViChonTheoHang,
  MaterialCombobox,
} from "../../../../components/MaterialCombobox";
import { emptyLine } from "../shared/helpers";

export function RequestFormDrawer({
  editing,
  departmentName,
  form,
  setForm,
  setLine,
  formError,
  minNeededDate,
  saving,
  save,
  closeForm,
}: {
  editing: DepartmentPurchaseRequestRow | null;
  departmentName: string | null;
  form: DepartmentPurchaseRequestInput;
  setForm: Dispatch<SetStateAction<DepartmentPurchaseRequestInput>>;
  setLine: (
    index: number,
    patch: Partial<DepartmentPurchaseRequestLineInput>,
  ) => void;
  formError: string | null;
  minNeededDate: string;
  saving: boolean;
  save: (e: FormEvent) => Promise<void>;
  closeForm: () => void;
}) {
  const { token } = useAuth();
  return (
        <div className="rc-drawer__scrim" role="presentation">
          <aside
            className="rc-drawer purchase__drawer-780"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={editing ? "Sửa yêu cầu mua hàng" : "Tạo yêu cầu mua hàng"}
          >
            <div className="purchase__hero-banner">
              <div className="purchase__hero-top">
                <div>
                  <span className="purchase__hero-kicker">Form nhập liệu vật tư</span>
                  <div className="purchase__hero-title-row">
                    <h2 className="purchase__hero-code">
                      {editing ? "Sửa yêu cầu mua hàng" : "Tạo yêu cầu mua hàng"}
                    </h2>
                  </div>
                </div>
                <button
                  type="button"
                  className="purchase__hero-x"
                  onClick={closeForm}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>

              <div className="purchase__hero-meta">
                <span>{departmentName || "Nội bộ"}</span>
                {editing && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>{editing.code}</span>
                  </>
                )}
              </div>
            </div>

            <form className="purchase__drawer-form" onSubmit={save}>
            <div className="rc-drawer__body">
              {formError && (
                <div className="banner banner--error" role="alert" style={{ marginBottom: "16px" }}>
                  {formError}
                </div>
              )}

              <div className="purchase__modal-top-fields">
                <div className="md-page__field" style={{ width: "220px" }}>
                  <label htmlFor="needed_date_input">
                    Ngày cần hàng <span className="md-page__req">*</span>
                  </label>
                  <input
                    id="needed_date_input"
                    className="input purchase__input-flat"
                    type="date"
                    required
                    min={minNeededDate}
                    value={form.needed_date}
                    onChange={(e) =>
                      setForm({ ...form, needed_date: e.target.value })
                    }
                  />
                </div>

                <div className="md-page__field" style={{ width: "100%" }}>
                  <label htmlFor="content_input">
                    Nội dung / mục đích <span className="md-page__req">*</span>
                  </label>
                  <textarea
                    id="content_input"
                    className="input purchase__textarea-flat"
                    required
                    rows={2}
                    value={form.content}
                    onChange={(e) =>
                      setForm({ ...form, content: e.target.value })
                    }
                    placeholder="VD: thiếu giấy cho lệnh sản xuất SX-2026-014, cần trước ngày đóng gói"
                  />
                </div>
              </div>

              <div className="purchase__modal-items-head">
                <h4 className="purchase__section-heading" style={{ margin: 0 }}>
                  Danh sách vật tư cần mua ({form.lines.length})
                </h4>
              </div>

              <div className="purchase__modal-table-wrap">
                <table className="pay-table purchase__modal-table">
                  <thead>
                    <tr>
                      <th style={{ width: "36%" }}>Vật tư *</th>
                      <th style={{ width: "16%" }}>ĐVT</th>
                      <th style={{ width: "18%" }} className="pay-num">Số lượng *</th>
                      <th>Ghi chú dòng</th>
                      <th style={{ width: "40px", textAlign: "center" }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.lines.map((line, index) => (
                      <tr key={index}>
                        <td>
                          <MaterialCombobox
                            token={token ?? ""}
                            hangTen={line.item_name || null}
                            chiCoNhaCungCap
                            onPick={(m) =>
                              setLine(index, {
                                hang_loai: m.hang_loai,
                                hang_id: m.hang_id,
                                item_name: m.ten,
                                unit: "",
                              })
                            }
                          />
                        </td>
                        <td>
                          <DonViChonTheoHang
                            chiDoc
                            token={token ?? ""}
                            hangLoai={line.hang_loai ?? null}
                            hangId={line.hang_id ?? null}
                            value={line.unit}
                            onChange={(ma) => setLine(index, { unit: ma })}
                            disabled={!line.hang_loai || !line.hang_id}
                          />
                        </td>
                        <td className="pay-num">
                          <input
                            className="input purchase__input-flat pay-num"
                            type="number"
                            min="0.01"
                            step="0.01"
                            required
                            placeholder="1000"
                            value={line.quantity > 0 ? line.quantity : ""}
                            onChange={(e) =>
                              setLine(index, {
                                quantity: Number(e.target.value || 0),
                              })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="input purchase__input-flat"
                            placeholder="Nếu có"
                            value={line.note ?? ""}
                            onChange={(e) => setLine(index, { note: e.target.value })}
                          />
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <button
                            type="button"
                            className="purchase__icon-trash-btn"
                            aria-label="Xóa dòng vật tư"
                            title="Xóa dòng"
                            disabled={form.lines.length <= 1}
                            onClick={() =>
                              setForm((current) => ({
                                ...current,
                                lines: current.lines.filter((_, i) => i !== index),
                              }))
                            }
                          >
                            <Icon name="trash" size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                    <tr className="purchase__add-line-tr">
                      <td colSpan={5} style={{ padding: 0 }}>
                        <button
                          type="button"
                          className="purchase__add-line-btn"
                          onClick={() =>
                            setForm((current) => ({
                              ...current,
                              lines: [...current.lines, emptyLine()],
                            }))
                          }
                        >
                          <Icon name="plus" size={14} /> Thêm dòng vật tư mới...
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

              <div className="purchase__drawer-footer">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={closeForm}
                  disabled={saving}
                >
                  Hủy
                </button>
                <Button type="submit" variant="accent" loading={saving} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  {editing ? (
                    <>
                      <Icon name="edit" size={14} /> Cập nhật yêu cầu
                    </>
                  ) : (
                    <>
                      <Icon name="plus" size={14} /> Lưu yêu cầu
                    </>
                  )}
                </Button>
              </div>
            </form>
          </aside>
        </div>
  );
}
