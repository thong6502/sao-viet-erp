// Bảng đơn nghỉ dùng chung cho tab "Đơn của tôi" và "Duyệt đơn"
// (tách từ pages/NghiPhepPage.tsx).
import type { LeaveRequest } from "../../../../api/client";
import { EmptyRow } from "../../../../components/EmptyState";
import { RowActionButton } from "../../../../components/RowActionButton";
// `fmtDate` DÙNG CHUNG (utils/format) — bản cục bộ cũ y hệt, chép lại chỉ tạo thêm một chỗ
// phải nhớ sửa. Đừng viết lại.
import { fmtDate } from "../../../../utils/format";
import { getInitials } from "../shared/helpers";
import { StatusBadge } from "./badges";

// --- Shared table -----------------------------------------------------------

export function LeaveTable({ items, showEmployee, onCancel, onApprove, onReject,
  selectable, selected, onToggle, onToggleAll, allPendingCount, onRowClick,
  loading, listError, onRetry, emptyTitle, emptySub }: {
  items: LeaveRequest[]; showEmployee: boolean;
  onCancel?: (id: number) => void; onApprove?: (id: number) => void; onReject?: (r: LeaveRequest) => void;
  selectable?: boolean; selected?: Set<number>; onToggle?: (id: number) => void;
  onToggleAll?: () => void; allPendingCount?: number;
  onRowClick?: (r: LeaveRequest) => void;
  /** Ba ca rỗng phải do NƠI GỌI cấp: bảng này không tự gọi máy chủ nên không tự biết
   *  đang tải hay gọi hỏng. `listError` CHỈ nhận lỗi TẢI DANH SÁCH — đừng truyền lỗi
   *  duyệt/từ chối vào đây, không thì một lần bấm hỏng là mất cả bảng. */
  loading?: boolean; listError?: string | null; onRetry?: () => void;
  emptyTitle?: string; emptySub?: string;
}) {
  const allChecked = !!allPendingCount && selected?.size === allPendingCount;
  // ⚠ Đếm theo số cột ĐANG hiện (2 cột bật/tắt theo ngữ cảnh), đừng gõ số cứng.
  const cols = (showEmployee ? 8 : 7) + (selectable ? 1 : 0);
  return (
    <div className="cc-table-card">
      <div className="cc-timesheet-scroll-container">
        <table className="cc-timesheet-table cc-leave-table">
          <thead>
            <tr>
              {selectable && <th className="ns-col-pick"><input type="checkbox" checked={allChecked} onChange={onToggleAll} title="Chọn tất cả đơn chờ" aria-label="Chọn tất cả đơn chờ duyệt" /></th>}
              {showEmployee && <th>Nhân viên</th>}
              <th>Loại nghỉ</th>
              <th>Từ ngày</th>
              <th>Đến ngày</th>
              <th className="ns-col-mid">Số ngày</th>
              <th>Lý do</th>
              <th className="ns-col-mid">Trạng thái</th>
              {/* Tên cột thống nhất toàn hệ là "Thao tác" (không dùng "Hành động"). */}
              <th className="ns-col-act">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading && <EmptyRow colSpan={cols} trangThai="dang-tai" />}
            {!loading && listError && (
              <EmptyRow colSpan={cols} trangThai="loi" loi={listError} onThuLai={onRetry} />
            )}
            {!loading && !listError && items.map((r) => (
              <tr key={r.id} onClick={() => onRowClick?.(r)} className="cc-leave-table-row">
                {selectable && (
                  <td className="ns-col-pick" onClick={(e) => e.stopPropagation()}>
                    {r.status === "pending" && <input type="checkbox" checked={selected?.has(r.id) ?? false} onChange={() => onToggle?.(r.id)} aria-label={`Chọn đơn của ${r.employee_name ?? `NV#${r.employee_id}`}`} />}
                  </td>
                )}
                {showEmployee && (
                  <td>
                    <div className="cc-name-cell-wrapper">
                      <span className="cc-name-avatar">{getInitials(r.employee_name)}</span>
                      <span className="cc-name-text-plain" title={r.employee_name ?? `NV#${r.employee_id}`}>
                        {r.employee_name ?? `NV#${r.employee_id}`}
                      </span>
                    </div>
                  </td>
                )}
                <td>
                  <div className="cc-leave-type-cell">
                    <span className="cc-leave-type-name">{r.leave_type_name ?? "—"}</span>
                    {r.is_paid === false ? (
                      <span className="cc-type-badge cc-type-badge--unpaid">Không lương</span>
                    ) : (
                      <span className="cc-type-badge cc-type-badge--paid">Có lương</span>
                    )}
                  </div>
                </td>
                <td className="cc-date-cell">{fmtDate(r.start_date)}</td>
                <td className="cc-date-cell">{fmtDate(r.end_date)}</td>
                <td className="ns-col-mid">
                  <span className="cc-days-pill">{r.days} ngày</span>
                </td>
                <td>
                  <div className="cc-reason-wrapper">
                    <span className="cc-reason-text">{r.reason || "—"}</span>
                    {r.decision_note && (
                      <div className="cc-decision-note-sub">
                        💬 {r.decision_note}
                      </div>
                    )}
                  </div>
                </td>
                <td className="ns-col-mid"><StatusBadge s={r.status} /></td>
                <td className="ns-col-act" onClick={(e) => e.stopPropagation()}>
                  {/* Nút chữ trên dòng → RowActionButton dạng dense (icon + tooltip).
                      GIỮ `danger` cho Từ chối / Hủy: cả hai đều là quyết định người khác
                      nhận được ngay, mất tín hiệu đỏ là bấm nhầm ô bên cạnh. */}
                  <div className="cc-approve-actions-cell ns-rowact">
                    {onApprove && r.status === "pending" && (
                      <RowActionButton dense label="Duyệt" icon="check" onClick={() => onApprove(r.id)} />
                    )}
                    {onReject && r.status === "pending" && (
                      <RowActionButton dense danger label="Từ chối" icon="ban" onClick={() => onReject(r)} />
                    )}
                    {onCancel && (r.status === "pending" || r.status === "approved") && (
                      <RowActionButton dense danger label="Hủy đơn" icon="x" onClick={() => onCancel(r.id)} />
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && !listError && items.length === 0 && (
              <EmptyRow
                colSpan={cols}
                icon="calendar"
                title={emptyTitle ?? "Chưa có đơn xin nghỉ phép nào"}
                sub={emptySub ?? "Bấm “Xin nghỉ phép” để gửi đơn đầu tiên."}
              />
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
