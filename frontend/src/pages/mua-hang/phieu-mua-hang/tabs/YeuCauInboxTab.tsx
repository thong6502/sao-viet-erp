// Tab "Yêu cầu chờ xử lý" — hộp yêu cầu của bộ phận (tách từ pages/PurchaseRequestsPage.tsx).
import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { DepartmentPurchaseRequestRow } from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { EmptyRow } from "../../../../components/EmptyState";
import { Icon } from "../../../../components/Icons";
import { fmtDate } from "../../../../utils/format";
import { SOURCE_STATUS_META } from "../shared/constants";
import { purchaseChildSummary } from "../shared/helpers";
import type { SourceStatusFilter } from "../shared/types";
import { SourceStatusBadge } from "../components/purchaseCells";

export function YeuCauInboxTab({
  bannerLoi,
  sourceQ,
  setSourceQ,
  sourceStatus,
  setSourceStatus,
  sourcePage,
  setSourcePage,
  sourceLoading,
  sourceError,
  sourceRows,
  sourceTotal,
  sourceTotalPages,
  loadSources,
  canCreate,
  openCreatePurchaseRequest,
}: {
  bannerLoi: ReactNode;
  sourceQ: string;
  setSourceQ: Dispatch<SetStateAction<string>>;
  sourceStatus: SourceStatusFilter;
  setSourceStatus: Dispatch<SetStateAction<SourceStatusFilter>>;
  sourcePage: number;
  setSourcePage: Dispatch<SetStateAction<number>>;
  sourceLoading: boolean;
  sourceError: string | null;
  sourceRows: DepartmentPurchaseRequestRow[];
  sourceTotal: number;
  sourceTotalPages: number;
  loadSources: () => void;
  canCreate: boolean;
  openCreatePurchaseRequest: (pickedSource: DepartmentPurchaseRequestRow) => void;
}) {
  return (
    <section className="md-page__tablewrap acct-mh__frame purchase__source-inbox">
      {bannerLoi}

      <div className="purchase__source-toolbar">
        <form
          className="md-page__search purchase__search-wrap"
          onSubmit={(e) => {
            e.preventDefault();
            setSourcePage(1);
          }}
        >
          <span className="purchase__search-icon">
            <Icon name="search" size={16} />
          </span>
          <input
            className="input purchase__search-input"
            placeholder="Tìm mã yêu cầu, mục đích..."
            value={sourceQ}
            onChange={(e) => {
              setSourceQ(e.target.value);
              setSourcePage(1);
            }}
          />
        </form>
        <select
          className="input purchase__select-modern"
          value={sourceStatus}
          onChange={(e) => {
            setSourceStatus(e.target.value as SourceStatusFilter);
            setSourcePage(1);
          }}
        >
          <option value="all">Tất cả yêu cầu</option>
          {Object.entries(SOURCE_STATUS_META).map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.label}
            </option>
          ))}
        </select>
      </div>

      <table className="md-page__table purchase__table-modern">
        <thead>
          {/* KHÔNG còn cột "Thao tác": bấm vào DÒNG là lập đơn luôn (openCreatePurchaseRequest).
              Thao tác gộp vào bản ghi cho khớp Yêu cầu mua hàng của phòng ban (24/08/2026). */}
          <tr>
            <th>Mã yêu cầu</th>
            <th>Nguồn</th>
            <th>Ngày tạo</th>
            <th>Cần hàng</th>
            <th>Vật tư</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {sourceLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk-${i}`} className="purchase__skeleton-row">
                <td><div className="purchase__skeleton-bar" style={{ width: "130px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "150px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
              </tr>
            ))
          ) : sourceError ? (
            <EmptyRow
              colSpan={6}
              trangThai="loi"
              loi={sourceError}
              onThuLai={loadSources}
            />
          ) : sourceRows.length === 0 ? (
            <EmptyRow
              colSpan={6}
              icon="clipboard"
              title="Chưa có yêu cầu mua từ phòng ban"
              sub="Đơn mua hàng luôn bắt đầu từ một yêu cầu của bộ phận — chờ họ gửi sang."
            />
          ) : (
            sourceRows.map((row) => {
              const disabled = row.status !== "open";
              // Đếm/hiện món CÒN SỐNG (bỏ dòng đã huỷ) — khớp cách bảng Yêu cầu mua hàng đếm,
              // không thì phiếu "Hủy một phần" phồng số món lên vô nghĩa.
              const dong = row.lines.filter((line) => !line.cancelled_at);
              return (
                <tr
                  key={row.id}
                  className="md-page__row"
                  onClick={() =>
                    !disabled && canCreate
                      ? openCreatePurchaseRequest(row)
                      : undefined
                  }
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
                    <div className="purchase__dept-title">
                      {row.requesting_department_name ||
                        row.requested_by_name ||
                        "Nội bộ"}
                    </div>
                    {row.requesting_department_name && row.requested_by_name && (
                      <div className="md-page__muted">{row.requested_by_name}</div>
                    )}
                  </td>
                  <td>{fmtDate(row.created_at)}</td>
                  <td>{fmtDate(row.needed_date)}</td>
                  <td title={dong.map((line) => line.item_name).join(", ")}>
                    <span className="purchase__item-chip">{dong.length} món</span>
                  </td>
                  <td>
                    <div className="purchase__status-col">
                      <SourceStatusBadge status={row.workflow_status} />
                      {purchaseChildSummary(row) && (
                        <div className="md-page__muted purchase__source-progress">
                          {purchaseChildSummary(row)}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
      {!sourceLoading && (
      <div className="purchase__source-foot">
        <span className="md-page__muted">
          Tổng {sourceTotal} yêu cầu
          {sourceTotalPages > 1 ? ` · Trang ${sourcePage}/${sourceTotalPages}` : ""}
        </span>
        {sourceTotalPages > 1 && (
          <div className="md-page__pager-btns">
            <Button
              variant="ghost"
              disabled={sourcePage <= 1 || sourceLoading}
              onClick={() => setSourcePage((value) => value - 1)}
            >
              Trước
            </Button>
            <Button
              variant="ghost"
              disabled={sourcePage >= sourceTotalPages || sourceLoading}
              onClick={() => setSourcePage((value) => value + 1)}
            >
              Sau
            </Button>
          </div>
        )}
      </div>
      )}
    </section>
  );
}
