// Tab "Loại nghỉ" (HR) (tách từ pages/NghiPhepPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type LeaveType } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { EmptyState } from "../../../../components/EmptyState";
import { Pager } from "../../../../components/Pager";
import { RowActionButton } from "../../../../components/RowActionButton";
import {
  CheckCircle2,
  Edit3,
  Layers,
  LayoutGrid,
  List,
  Plus,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { LeaveTypeForm } from "../modals/LeaveTypeForm";
import { PAGE_SIZE } from "../shared/constants";
import { errMsg } from "../shared/helpers";

// --- Tab: Loại nghỉ (HR) ----------------------------------------------------

export function LeaveTypesTab({ token }: { token: string }) {
  const [items, setItems] = useState<LeaveType[] | null>(null);
  const [editing, setEditing] = useState<LeaveType | "new" | null>(null);
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
  /** Trang của danh mục — cắt ở CLIENT (endpoint `/types` còn nuôi 2 dropdown, xem `PAGE_SIZE`). */
  const [page, setPage] = useState(1);

  const [loading, setLoading] = useState(true);
  /** Lỗi TẢI danh mục. `toggleActive`/`handleDelete` báo lỗi bằng alert nên không đụng ô này —
   *  đúng ý: một lần xoá hỏng không được phép làm cả danh mục biến mất. */
  const [listError, setListError] = useState<string | null>(null);
  const load = useCallback(() => {
    setLoading(true);
    setListError(null);
    api.leaves.types(token)
      .then((r) => setItems(r.items))
      .catch((e) => { setItems([]); setListError(errMsg(e)); })
      .finally(() => setLoading(false));
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function toggleActive(t: LeaveType) {
    try {
      await api.leaves.updateType(token, t.id, {
        name: t.name,
        is_paid: t.is_paid,
        annual_quota: t.annual_quota,
        note: t.note,
        is_active: !t.is_active,
      });
      load();
    } catch (e) {
      alert(errMsg(e));
    }
  }

  async function handleDelete(t: LeaveType) {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa loại nghỉ "${t.name}" không?`)) return;
    try {
      await api.leaves.deleteType(token, t.id);
      load();
    } catch (e) {
      alert(errMsg(e));
    }
  }

  // Ba thẻ thống kê tính trên TOÀN BỘ danh mục, không phải trang đang xem.
  const totalTypes = items?.length ?? 0;
  const paidTypes = items?.filter((t) => t.is_paid).length ?? 0;
  const unpaidTypes = items?.filter((t) => !t.is_paid).length ?? 0;

  // Cắt trang cho CẢ hai chế độ xem (thẻ và bảng) — hai chế độ chỉ khác cách vẽ, cùng một
  // danh sách, nên chuyển qua lại không được nhảy sang tập dữ liệu khác.
  const totalPages = Math.max(1, Math.ceil(totalTypes / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const pagedTypes = (items ?? []).slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  return (
    <div className="cc-leave-types-wrapper">
      {/* 1. Header Toolbar & Quick Stats */}
      <div className="cc-calendar-dashboard" style={{ marginBottom: 20 }}>
        <div className="cc-calendar-stats-strip">
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--users"><Layers size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalTypes}</span>
              <span className="cc-calendar-stat-label">Loại nghỉ</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--check"><CheckCircle2 size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{paidTypes}</span>
              <span className="cc-calendar-stat-label">Có lương P</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--clock"><ShieldCheck size={16} /></span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{unpaidTypes}</span>
              <span className="cc-calendar-stat-label">Không lương</span>
            </div>
          </div>
        </div>

        <div className="cc-leave-types-toolbar-right">
          <div className="cc-view-toggle">
            <button
              className={`cc-view-toggle-btn ${viewMode === "grid" ? "is-active" : ""}`}
              onClick={() => setViewMode("grid")}
              title="Xem dạng thẻ"
            >
              <LayoutGrid size={15} />
            </button>
            <button
              className={`cc-view-toggle-btn ${viewMode === "table" ? "is-active" : ""}`}
              onClick={() => setViewMode("table")}
              title="Xem dạng bảng"
            >
              <List size={15} />
            </button>
          </div>

          {/* Hành động chính DUY NHẤT của tab → cam. (Cặp nút xem thẻ/bảng bên trái là
              công tắc hiển thị, không phải hành động — giữ nguyên dáng cũ.) */}
          <Button variant="accent" className="ns-btn-cta" onClick={() => setEditing("new")}>
            <Plus size={16} />
            <span>Thêm loại nghỉ mới</span>
          </Button>
        </div>
      </div>

      {/* 2. Main Content Display */}
      {loading ? (
        <EmptyState trangThai="dang-tai" />
      ) : listError ? (
        <EmptyState trangThai="loi" loi={listError} onThuLai={load} />
      ) : !items || items.length === 0 ? (
        <EmptyState
          icon="clipboard"
          title="Chưa khai loại nghỉ nào"
          sub="Bấm “Thêm loại nghỉ mới” để khai phép năm, nghỉ ốm, việc riêng…"
        />
      ) : viewMode === "grid" ? (
        /* GRID VIEW (FEATURE CARDS) */
        <div className="cc-leave-types-grid">
          {pagedTypes.map((t) => {
            return (
              <div key={t.id} className={`cc-leave-type-card ${!t.is_active ? "is-inactive" : ""}`}>
                <div className="cc-leave-type-card-head">
                  <div className="cc-leave-type-title-group">
                    <h3 className="cc-leave-type-card-name" title={t.name}>{t.name}</h3>
                    <div className="cc-leave-type-badges-row">
                      {t.is_paid ? (
                        <span className="cc-type-badge cc-type-badge--paid">
                          Có lương
                        </span>
                      ) : (
                        <span className="cc-type-badge cc-type-badge--unpaid">
                          Không lương
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="cc-leave-type-active-switch">
                    <label className="cc-switch" title={t.is_active ? "Đang sử dụng (Click để tắt)" : "Đã tắt (Click để bật)"}>
                      <input type="checkbox" checked={t.is_active} onChange={() => toggleActive(t)} />
                      <span className="cc-slider" />
                    </label>
                  </div>
                </div>

                <div className="cc-leave-type-card-body">
                  <div className="cc-leave-type-info-row">
                    <span className="cc-leave-type-info-label">Hạn mức/năm:</span>
                    <span className="cc-leave-type-info-val">
                      {t.annual_quota > 0 ? (
                        <span className="cc-quota-badge-val">{t.annual_quota} ngày</span>
                      ) : (
                        <span className="cc-quota-badge-val cc-quota-badge-val--unlimited">Theo đơn xin</span>
                      )}
                    </span>
                  </div>
                  {t.note && (
                    <p className="cc-leave-type-note-text" title={t.note}>
                      {t.note}
                    </p>
                  )}
                </div>

                <div className="cc-leave-type-card-foot">
                  <button className="cc-leave-type-action-btn" onClick={() => setEditing(t)}>
                    <Edit3 size={13} />
                    <span>Sửa</span>
                  </button>
                  <button className="cc-leave-type-action-btn cc-leave-type-action-btn--danger" onClick={() => handleDelete(t)}>
                    <Trash2 size={13} />
                    <span>Xóa</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* TABLE VIEW */
        <div className="cc-timesheet-scroll-container cc-calendar-scroll-wrapper">
          <table className="cc-timesheet-table">
            <thead>
              <tr>
                <th>Tên loại nghỉ</th>
                <th className="ns-col-mid">Chế độ lương</th>
                <th className="ns-col-mid">Hạn mức hàng năm</th>
                <th className="ns-col-mid">Trạng thái</th>
                <th className="ns-col-act">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {pagedTypes.map((t) => {
                return (
                  <tr key={t.id} className={!t.is_active ? "is-inactive-row" : ""}>
                    <td style={{ fontWeight: "bold", color: "var(--ink)" }}>
                      <span>{t.name}</span>
                    </td>
                    <td className="ns-col-mid">
                      {t.is_paid ? (
                        <span className="cc-type-badge cc-type-badge--paid">
                          Có lương
                        </span>
                      ) : (
                        <span className="cc-type-badge cc-type-badge--unpaid">
                          Không lương
                        </span>
                      )}
                    </td>
                    <td className="ns-col-mid" style={{ fontWeight: "bold" }}>
                      {t.annual_quota > 0 ? `${t.annual_quota} ngày/năm` : "Theo đơn xin"}
                    </td>
                    <td className="ns-col-mid">
                      <label className="cc-switch" title={t.is_active ? "Đang sử dụng" : "Đã tắt"}>
                        <input type="checkbox" checked={t.is_active} onChange={() => toggleActive(t)} aria-label={`Bật/tắt loại nghỉ ${t.name}`} />
                        <span className="cc-slider" />
                      </label>
                    </td>
                    <td className="ns-col-act">
                      {/* Xoá loại nghỉ đụng tới đơn cũ ⇒ GIỮ `danger`. */}
                      <div className="cc-approve-actions-cell ns-rowact">
                        <RowActionButton dense label="Sửa" icon="pencil" onClick={() => setEditing(t)} />
                        <RowActionButton dense danger label="Xóa" icon="trash" onClick={() => handleDelete(t)} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Chân bảng chung cho CẢ hai chế độ xem (thẻ / bảng). Danh mục thường 5-15 dòng nên nút
          chuyển trang gần như không bao giờ hiện — đúng ý: `Pager` tự ẩn khi chỉ có 1 trang. */}
      {!loading && !listError && totalTypes > 0 && (
        <Pager
          total={totalTypes}
          page={pageSafe}
          size={PAGE_SIZE}
          unit="loại nghỉ"
          onPage={setPage}
        />
      )}

      {editing && (
        <LeaveTypeForm
          token={token}
          type={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}
