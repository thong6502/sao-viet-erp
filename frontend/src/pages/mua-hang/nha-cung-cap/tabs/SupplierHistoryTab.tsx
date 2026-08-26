// Tab 3 của drawer Nhà cung cấp — "Lịch sử mua hàng (PMH)" (tách từ pages/SuppliersPage.tsx).
import type { PurchaseRequestRow, SupplierRow } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { fmtDate, money } from "../../../../utils/format";
import { getPOStatusLabel } from "../shared/helpers";

export function SupplierHistoryTab({
  mode,
  selected,
  poList,
  poLoading,
  poError,
}: {
  mode: null | "create" | "edit";
  selected: SupplierRow | null;
  poList: PurchaseRequestRow[];
  poLoading: boolean;
  poError: string | null;
}) {
  return (
                  <div>
                    <h3
                      style={{
                        fontSize: "16px",
                        fontWeight: "bold",
                        marginBottom: "4px",
                      }}
                    >
                      Lịch sử Phiếu Mua Hàng (PMH)
                    </h3>
                    <p
                      className="md-page__muted"
                      style={{ marginBottom: "16px" }}
                    >
                      Danh sách các đơn mua hàng đã được giao cho NCC này xử lý.
                    </p>

                    {/* Ba ca đang tải / rỗng / lỗi dùng CHUNG khối `EmptyState` như mọi danh sách
                        khác (chuẩn đợt 2 §f) — trước đây chỗ này tự dựng ba kiểu riêng.
                        Ca "chưa lưu NCC" KHÔNG phải một trong ba ca đó: nó là điều kiện chưa đủ để
                        hỏi máy chủ, nên vẫn là banner hướng dẫn.
                        `poError` là ô nhớ RIÊNG của bảng này (chỉ ghi trong catch của lượt tải
                        lịch sử), không dùng chung với `error` thao tác — giữ nguyên như vậy. */}
                    {mode === "create" || !selected ? (
                      <div className="banner banner--info">
                        Vui lòng lưu thông tin nhà cung cấp trước khi xem lịch
                        sử mua hàng.
                      </div>
                    ) : poLoading ? (
                      <EmptyState trangThai="dang-tai" />
                    ) : poError ? (
                      <EmptyState trangThai="loi" loi={poError} />
                    ) : poList.length === 0 ? (
                      <EmptyState
                        icon="cart"
                        title="Chưa có phiếu mua hàng nào với nhà cung cấp này"
                        sub="Phiếu mua lập từ màn Mua hàng sẽ tự hiện ở đây."
                      />
                    ) : (
                      <div className="card md-page__tablewrap">
                        <table className="md-page__table">
                          <thead>
                            <tr>
                              <th>Mã PMH</th>
                              <th>Ngày tạo</th>
                              <th>Mục đích / Người tạo</th>
                              <th style={{ textAlign: "right" }}>
                                Tổng giá trị
                              </th>
                              <th>Trạng thái PMH</th>
                            </tr>
                          </thead>
                          <tbody>
                            {poList.map((po) => {
                              const statusMeta = getPOStatusLabel(po.status);
                              return (
                                <tr key={po.id}>
                                  <td
                                    className="md-page__mono"
                                    style={{ fontWeight: "bold" }}
                                  >
                                    {po.code}
                                  </td>
                                  <td className="md-page__mono">
                                    {fmtDate(po.created_at)}
                                  </td>
                                  <td>
                                    <div>{po.purpose || "Mua vật tư in"}</div>
                                    <div
                                      className="md-page__muted"
                                      style={{ fontSize: "12px" }}
                                    >
                                      Bởi: {po.created_by_name || "Hệ thống"}
                                    </div>
                                  </td>
                                  <td style={{ textAlign: "right" }}>
                                    <strong className="md-page__price">
                                      {money(po.total_estimate ?? 0)}
                                    </strong>
                                  </td>
                                  <td>
                                    <span
                                      className={`purchase__status ${statusMeta.className}`}
                                    >
                                      {statusMeta.label}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
  );
}
