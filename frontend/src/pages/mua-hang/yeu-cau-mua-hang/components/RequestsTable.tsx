// Bảng danh sách yêu cầu mua hàng + phân trang (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import type { DepartmentPurchaseRequestRow } from "../../../../api/client";
import { EmptyRow } from "../../../../components/EmptyState";
import { fmtDate } from "../../../../utils/format";
import { SOURCE_STATUS_META, SOURCE_TYPE_LABELS } from "../shared/constants";
import { dongSong } from "../shared/helpers";
import type { StatusFilter } from "../shared/types";
import { SourceStatusBadge } from "./requestCells";

export function RequestsTable({
  loading,
  listError,
  load,
  rows,
  q,
  setQ,
  status,
  setStatus,
  page,
  setPage,
  total,
  totalPages,
  focusRequestCode,
  selectedId,
  setSelectedId,
}: {
  loading: boolean;
  listError: string | null;
  load: () => void;
  rows: DepartmentPurchaseRequestRow[];
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  status: StatusFilter;
  setStatus: Dispatch<SetStateAction<StatusFilter>>;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  total: number;
  totalPages: number;
  focusRequestCode: string | null;
  selectedId: number | null;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
}) {
  return (
      <section className="card md-page__tablewrap">
        <table className="md-page__table purchase__table-modern">
          <thead>
            <tr>
              <th style={{ width: "160px" }}>Mã yêu cầu</th>
              <th style={{ width: "210px" }}>Bộ phận / Người tạo</th>
              <th style={{ width: "110px" }}>Vật tư</th>
              <th style={{ width: "130px" }}>Ngày cần hàng</th>
              <th style={{ width: "180px" }}>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "140px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "70px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "100px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "130px" }} /></td>
                </tr>
              ))
            ) : listError ? (
              <EmptyRow
                colSpan={5}
                trangThai="loi"
                loi={listError}
                onThuLai={load}
              />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={5}
                icon="clipboard"
                title="Chưa có yêu cầu mua hàng nào khớp"
                sub={
                  q.trim() || status !== "all"
                    ? "Thử bỏ bớt bộ lọc hoặc xoá từ khoá tìm kiếm."
                    : "Bộ phận gửi yêu cầu vật tư sang Thu mua tại đây."
                }
                action={
                  q.trim() || status !== "all" ? (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => {
                        setQ("");
                        setStatus("all");
                        setPage(1);
                      }}
                    >
                      Xoá bộ lọc
                    </button>
                  ) : undefined
                }
              />
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className={`md-page__row${
                    row.code === focusRequestCode || selectedId === row.id
                      ? " purchase__row--selected"
                      : ""
                  }`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td>
                    <div className="purchase__code-row">
                      <strong className="purchase__code-badge">{row.code}</strong>
                      {row.related_document_code && (
                        <span
                          className="purchase__source-tag"
                          title={`Chứng từ liên quan: ${row.related_document_type || "Nguồn"} ${row.related_document_code}`}
                        >
                          {row.related_document_code}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="purchase__dept-title">{row.requesting_department_name || "Nội bộ"}</div>
                    <div className="md-page__muted">
                      {row.requested_by_name || SOURCE_TYPE_LABELS[row.source_type]}
                    </div>
                  </td>
                  <td title={row.lines.map((line) => line.item_name).join(", ")}>
                    <span className="purchase__item-chip">{dongSong(row).length} món</span>
                  </td>
                  <td>{fmtDate(row.needed_date)}</td>
                  <td>
                    <div className="purchase__status-col">
                      <SourceStatusBadge status={row.workflow_status} />
                      {row.workflow_status === "partially_cancelled" && (
                        <div className="md-page__muted">
                          {SOURCE_STATUS_META[row.progress_status]?.label ?? row.progress_status} · bỏ {row.cancelled_line_count}/{row.cancelled_line_count + row.active_line_count} món
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {!loading && totalPages > 1 && (
          <div className="purchase__source-foot">
            <span className="md-page__muted">
              Tổng {total} yêu cầu · Trang {page}/{totalPages}
            </span>
            <div className="md-page__pager-btns">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Sau
              </button>
            </div>
          </div>
        )}
      </section>
  );
}
