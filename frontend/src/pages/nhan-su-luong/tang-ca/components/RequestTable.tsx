// Bảng phiếu tăng ca dùng chung cho cả 2 tab (tách từ pages/TangCaPage.tsx).
import { type OvertimeRequest } from "../../../../api/client";
import { EmptyRow } from "../../../../components/EmptyState";
// `fmtDateISO` = bản dùng chung của `fmtYmd` cũ (ISO yyyy-mm-dd → dd/mm/yyyy, giữ số 0 đệm,
// KHÔNG qua `new Date()` nên không lệch múi giờ). Đừng chép lại bản cục bộ.
import { fmtDateISO, fmtDateTime } from "../../../../utils/format";
import { minToHhmm } from "../shared/helpers";
import { StatusBadge } from "./badges";

// --- Bảng phiếu dùng chung ---------------------------------------------------

export function RequestTable({
  rows,
  showEmployee,
  selectable,
  selected,
  onToggle,
  actions,
  loading,
  listError,
  onRetry,
  emptyTitle,
  emptySub,
}: {
  rows: OvertimeRequest[];
  showEmployee: boolean;
  selectable: boolean;
  selected: Set<number>;
  onToggle: (id: number) => void;
  actions: (r: OvertimeRequest) => React.ReactNode;
  /** Ba ca rỗng do NƠI GỌI cấp — bảng này không tự gọi máy chủ. `listError` CHỈ nhận lỗi
   *  TẢI DANH SÁCH, đừng truyền lỗi duyệt/hủy vào. */
  loading?: boolean;
  listError?: string | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptySub?: string;
}) {
  // ⚠ Số cột ĐANG hiện: 8 cột cố định + 2 cột bật/tắt theo ngữ cảnh. Trước đây gõ cứng 10 nên
  // ở tab "Phiếu của tôi" (8 cột) ô rỗng thừa 2 cột, kéo bảng rộng ra.
  const cols = 8 + (selectable ? 1 : 0) + (showEmployee ? 1 : 0);
  return (
    <div className="ns__tablewrap">
      <table className="ns__table tc-table">
        <thead>
          <tr>
            {selectable && <th style={{ width: 36 }} aria-label="Chọn phiếu" />}
            {showEmployee && <th>Nhân viên</th>}
            <th>Ngày công</th>
            <th>Khoảng tăng ca</th>
            <th>Số giờ</th>
            <th>Lý do</th>
            <th>Trạng thái</th>
            <th>Người duyệt</th>
            <th>Ghi chú duyệt</th>
            {/* `<th>` rỗng phải có aria-label, không thì trình đọc màn hình đọc ra một ô câm. */}
            <th className="tc-col-act" aria-label="Thao tác" />
          </tr>
        </thead>
        <tbody>
          {loading && <EmptyRow colSpan={cols} trangThai="dang-tai" />}
          {!loading && listError && (
            <EmptyRow
              colSpan={cols}
              trangThai="loi"
              loi={listError}
              onThuLai={onRetry}
            />
          )}
          {!loading && !listError && rows.map((r) => (
            <tr key={r.id}>
              {selectable && (
                <td>
                  {r.status === "pending" && (
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => onToggle(r.id)}
                    />
                  )}
                </td>
              )}
              {showEmployee && <td>{r.employee_name ?? "—"}</td>}
              <td>{fmtDateISO(r.work_date)}</td>
              <td>
                {minToHhmm(r.from_minute)} → {minToHhmm(r.to_minute)}
              </td>
              <td>
                {Math.floor(r.minutes / 60)}h
                {r.minutes % 60 ? ` ${r.minutes % 60}'` : ""}
              </td>
              <td>{r.reason ?? "—"}</td>
              <td>
                <StatusBadge status={r.status} />
              </td>
              <td>
                {r.decided_by_name ? (
                  <>
                    {r.decided_by_name}
                    {r.decided_at && (
                      <div className="tc-muted">{fmtDateTime(r.decided_at)}</div>
                    )}
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>{r.decision_note || "—"}</td>
              <td className="tc-col-act">
                <div className="cc-rowact">{actions(r)}</div>
              </td>
            </tr>
          ))}
          {!loading && !listError && rows.length === 0 && (
            <EmptyRow
              colSpan={cols}
              icon="clock"
              title={emptyTitle ?? "Chưa có phiếu tăng ca nào"}
              sub={emptySub}
            />
          )}
        </tbody>
      </table>
    </div>
  );
}
