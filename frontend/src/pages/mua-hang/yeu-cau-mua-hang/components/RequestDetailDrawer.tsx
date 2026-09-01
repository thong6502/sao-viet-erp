// Drawer CHI TIẾT yêu cầu mua hàng — hero + 2 tab (vật tư · lịch sử) + chân nút Sửa/Huỷ
// (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
// `user` lấy thẳng bằng `useAuth()` như bản gốc, KHÔNG luồn thêm prop: hai câu điều kiện dưới
// chân drawer vẫn viết `user?.id` y nguyên.
import type { Dispatch, SetStateAction } from "react";
import type { DepartmentPurchaseRequestRow } from "../../../../api/client";
import { useAuth } from "../../../../auth/useAuth";
import { Icon } from "../../../../components/Icons";
import { RowActionButton } from "../../../../components/RowActionButton";
import { StatusHistoryTimeline } from "../../../../components/StatusHistoryTimeline";
import { fmtDate } from "../../../../utils/format";
// Đơn vị lưu bằng MÃ (`cai`), tên hiển thị ("cái") nằm ở danh mục Đơn vị — xem pages/tenDonVi.ts.
import { tenDonVi } from "../../../tenDonVi";
import { dongSong, noiDung } from "../shared/helpers";
import type { BoMonState } from "../shared/types";
import { LineFulfilmentCell, SourceStatusBadge } from "./requestCells";

export function RequestDetailDrawer({
  selected,
  setSelectedId,
  drawerTab,
  setDrawerTab,
  boMonDuoc,
  setBoMon,
  canAdminCancel,
  canUpdate,
  openEdit,
  setCanceling,
}: {
  selected: DepartmentPurchaseRequestRow;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  drawerTab: "items" | "history";
  setDrawerTab: Dispatch<SetStateAction<"items" | "history">>;
  boMonDuoc: boolean;
  setBoMon: Dispatch<SetStateAction<BoMonState | null>>;
  canAdminCancel: boolean;
  canUpdate: boolean;
  openEdit: (row: DepartmentPurchaseRequestRow) => void;
  setCanceling: Dispatch<SetStateAction<DepartmentPurchaseRequestRow | null>>;
}) {
  const { user } = useAuth();
  return (
        <div className="rc-drawer__scrim" onClick={() => setSelectedId(null)}>
          <aside className="rc-drawer purchase__drawer-780" onClick={(e) => e.stopPropagation()}>
            <div className="purchase__hero-banner">
              <div className="purchase__hero-top">
                <div>
                  <span className="purchase__hero-kicker">Chi tiết yêu cầu mua hàng</span>
                  <div className="purchase__hero-title-row">
                    <h2 className="purchase__hero-code">{selected.code}</h2>
                    <SourceStatusBadge status={selected.workflow_status} />
                  </div>
                </div>
                <button
                  type="button"
                  className="purchase__hero-x"
                  onClick={() => setSelectedId(null)}
                  aria-label="Đóng"
                >
                  ✕
                </button>
              </div>

              <div className="purchase__hero-meta">
                <span>{selected.requesting_department_name || "Nội bộ"}</span>
                {selected.requested_by_name && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span>{selected.requested_by_name}</span>
                  </>
                )}
                <span className="purchase__hero-dot">•</span>
                <span className="purchase__hero-date">Cần {fmtDate(selected.needed_date)}</span>
                <span className="purchase__hero-dot">•</span>
                <span>
                  {dongSong(selected).length} mặt hàng
                  {selected.cancelled_line_count > 0 ? ` (đã bỏ ${selected.cancelled_line_count})` : ""}
                </span>
                {selected.related_document_code && (
                  <>
                    <span className="purchase__hero-dot">•</span>
                    <span className="purchase__hero-chip" style={{ margin: 0 }}>
                      {selected.related_document_code}
                    </span>
                  </>
                )}
              </div>
            </div>

            <div className="rc-drawer__tabs" style={{ margin: "16px 24px 0 24px" }}>
              <button
                type="button"
                className={`rc-drawer__tab ${drawerTab === "items" ? "is-active" : ""}`}
                onClick={() => setDrawerTab("items")}
              >
                Nội dung & Vật tư ({dongSong(selected).length})
              </button>
              <button
                type="button"
                className={`rc-drawer__tab ${drawerTab === "history" ? "is-active" : ""}`}
                onClick={() => setDrawerTab("history")}
              >
                Lịch sử trạng thái ({selected.status_history?.length || 0})
              </button>
            </div>

            <div className="rc-drawer__body purchase__drawer-body-wow">
              {drawerTab === "items" ? (
                <>
                  {noiDung(selected) && (
                    <div className="purchase__note" style={{ fontSize: "13px" }}>
                      {noiDung(selected)}
                    </div>
                  )}

                  {selected.reject_reason && (
                    <div className="purchase__note purchase__note--reject">
                      <strong>Lý do từ chối / huỷ:</strong> {selected.reject_reason}
                    </div>
                  )}

                  <div className="purchase__items-section">
                    <table className="pay-table purchase__drawer-table">
                      <thead>
                        <tr>
                          <th>Vật tư</th>
                          <th className="pay-num">Yêu cầu</th>
                          <th>Nhà cung cấp & PMH</th>
                          <th>Trạng thái</th>
                          {boMonDuoc && selected.lines.some((l) => !l.cancelled_at && l.can_cancel) && (
                            <th className="md-page__actions-col">Thao tác</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {selected.lines.map((line) => (
                          <tr
                            key={line.id}
                            className={line.cancelled_at ? "purchase__dong-da-bo" : undefined}
                          >
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                <span style={{ color: "var(--ash)" }}>
                                  <Icon name="box" size={14} />
                                </span>
                                <strong style={{ fontFamily: "var(--ff-sans)" }}>{line.item_name}</strong>
                              </div>
                              {line.note && (
                                <div style={{ fontSize: "12px", color: "var(--ash)", marginTop: "2px" }}>
                                  {line.note}
                                </div>
                              )}
                              {line.cancelled_at && (
                                <div className="md-page__muted" style={{ fontSize: "12px" }}>
                                  Đã bỏ{line.cancelled_by_name ? ` bởi ${line.cancelled_by_name}` : ""} · {fmtDate(line.cancelled_at)}
                                  {line.cancel_reason ? ` — ${line.cancel_reason}` : ""}
                                </div>
                              )}
                            </td>
                            <td className="pay-num">
                              <span className="purchase__qty-badge">
                                {line.quantity.toLocaleString("vi-VN")}{" "}
                                {tenDonVi(line.unit) ?? line.unit}
                              </span>
                            </td>
                            <td>
                              {line.fulfilment?.supplier_name ? (
                                <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                                  <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--ink)" }}>
                                    {line.fulfilment.supplier_name}
                                  </span>
                                  {line.fulfilment?.purchase_code && (
                                    <span className="purchase__spec-tag purchase__spec-tag--pmh" style={{ fontSize: "12px", width: "fit-content" }}>
                                      {line.fulfilment.purchase_code}
                                      {line.fulfilment.received_quantity ? ` · nhận ${line.fulfilment.received_quantity.toLocaleString("vi-VN")} ${tenDonVi(line.unit) ?? line.unit}` : ""}
                                    </span>
                                  )}
                                </div>
                              ) : line.fulfilment?.purchase_code ? (
                                <span className="purchase__spec-tag purchase__spec-tag--pmh" style={{ fontSize: "12px" }}>
                                  {line.fulfilment.purchase_code}
                                </span>
                              ) : (
                                <span className="md-page__muted" style={{ fontSize: "12px" }}>—</span>
                              )}
                            </td>
                            <td>
                              {line.cancelled_at ? (
                                <span className="purchase__status purchase__status--cancelled">
                                  Đã bỏ
                                </span>
                              ) : (
                                <LineFulfilmentCell
                                  line={line}
                                  coPhieu={selected.purchase_requests.length > 0}
                                />
                              )}
                            </td>
                            {boMonDuoc && selected.lines.some((l) => !l.cancelled_at && l.can_cancel) && (
                              <td className="md-page__actions-col">
                                {!line.cancelled_at && line.can_cancel && (
                                  <div className="purchase__actions purchase__actions--dense">
                                    <RowActionButton
                                      dense
                                      danger
                                      icon="ban"
                                      label={line.cancel_block_reason ?? "Bỏ món"}
                                      onClick={() => setBoMon({ line, reason: "", error: null })}
                                    />
                                  </div>
                                )}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="purchase__timeline-section">
                  <StatusHistoryTimeline items={selected.status_history} />
                </div>
              )}
            </div>

            {selected.status === "open" &&
              (canAdminCancel || (canUpdate && selected.requested_by_user_id === user?.id)) && (
                <div className="rc-drawer__footer purchase__drawer-footer">
                  {canUpdate && selected.requested_by_user_id === user?.id && (
                    <button
                      type="button"
                      className="btn btn--primary"
                      onClick={() => openEdit(selected)}
                    >
                      <Icon name="edit" size={14} /> Sửa yêu cầu
                    </button>
                  )}
                  {(canAdminCancel ||
                    (canUpdate && selected.requested_by_user_id === user?.id)) && (
                    <button
                      type="button"
                      className="btn btn--danger"
                      onClick={() => setCanceling(selected)}
                    >
                      <Icon name="ban" size={14} /> Hủy yêu cầu
                    </button>
                  )}
                </div>
              )}
          </aside>
        </div>
  );
}
