// Bảng danh sách nhà cung cấp + chân phân trang (tách từ pages/SuppliersPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import type { SupplierRow } from "../../../../api/client";
import { EmptyRow } from "../../../../components/EmptyState";

export function SuppliersTable({
  loading,
  listError,
  load,
  rows,
  canUpdate,
  openEdit,
  total,
  page,
  setPage,
  totalPages,
}: {
  loading: boolean;
  listError: string | null;
  load: () => void;
  rows: SupplierRow[];
  canUpdate: boolean;
  openEdit: (row: SupplierRow) => void;
  total: number;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  totalPages: number;
}) {
  return (
    <>
      {/* Modern Table List */}
      <div className="card md-page__tablewrap supplier__tablewrap">
        <table className="md-page__table supplier__table">
          <colgroup>
            <col className="supplier__col-name" />
            <col className="supplier__col-contact" />
            <col className="supplier__col-items" />
            <col className="supplier__col-status" />
          </colgroup>
          <thead>
            <tr>
              <th>Nhà cung cấp</th>
              <th>Người liên hệ</th>
              <th>Mặt hàng</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="purchase__skeleton-row">
                  <td><div className="purchase__skeleton-bar" style={{ width: "160px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "140px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                  <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                </tr>
              ))
            ) : listError ? (
              <EmptyRow
                colSpan={4}
                trangThai="loi"
                loi={listError}
                onThuLai={load}
              />
            ) : rows.length === 0 ? (
              <EmptyRow
                colSpan={4}
                icon="truck"
                title="Chưa có nhà cung cấp nào khớp"
                sub="Khai nhà cung cấp trước, rồi mới khai bảng giá vật tư của họ."
              />
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="md-page__row"
                  onClick={canUpdate ? () => openEdit(row) : undefined}
                >
                  {/* Column 1: Supplier Name + Group Badge + Tax Code */}
                  <td className="supplier__name-cell">
                    <strong className="supplier__primary">{row.name}</strong>
                    <div
                      style={{
                        display: "flex",
                        gap: "6px",
                        alignItems: "center",
                        flexWrap: "wrap",
                        marginTop: "4px",
                      }}
                    >
                      {/* {row.supplier_group && (
                        <span className="supplier-group-badge">{row.supplier_group}</span>
                      )} */}
                      {row.tax_code && (
                        <span
                          className="md-page__mono md-page__muted"
                          style={{ fontSize: "12px" }}
                        >
                          MST: {row.tax_code}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Column 2: Contact Person + Phone link / Email */}
                  <td className="supplier__contact-cell">
                    <div>
                      <strong>
                        {row.contact_name || (
                          <span className="md-page__muted">—</span>
                        )}
                      </strong>
                    </div>
                    <div
                      className="supplier__secondary"
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "2px",
                        fontSize: "12px",
                      }}
                    >
                      {row.phone && (
                        <a
                          // href={`tel:${row.phone}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            color: "var(--moss-deep)",
                            textDecoration: "none",
                            fontWeight: 500,
                          }}
                        >
                          {row.phone}
                        </a>
                      )}
                      {row.email && (
                        <a
                          // href={`mailto:${row.email}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            color: "var(--ash)",
                            textDecoration: "none",
                          }}
                        >
                          {row.email}
                        </a>
                      )}
                      {!row.phone && !row.email && (
                        <span className="md-page__muted">—</span>
                      )}
                    </div>
                  </td>

                  {/* Column 3: Mặt hàng — chỉ hiện số đếm */}
                  <td className="supplier__items-cell">
                    {row.items.length > 0 ? (
                      <span
                        className="ir-tab__count"
                        style={{ fontSize: "12px" }}
                      >
                        {row.items.length} mặt hàng
                      </span>
                    ) : (
                      <span className="md-page__muted">Chưa có báo giá</span>
                    )}
                  </td>

                  {/* Column 5: Status Pill */}
                  <td>
                    <span
                      className={`md-purchase__status-badge ${
                        row.status === "active" ? "is-active" : "is-inactive"
                      }`}
                    >
                      {row.status === "active" ? "Hoạt động" : "Tạm ngừng"}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Chân bảng chuẩn: tổng bên TRÁI, nút chuyển trang bên PHẢI, và CHỈ hiện nút khi thật sự
          có nhiều hơn một trang (mẫu: `.purchase__source-foot` ở PurchaseRequestsPage). Danh mục
          NCC thường gọn trong một trang — treo "Trang 1/1" kèm hai nút mờ là nhiễu mà không nói
          thêm điều gì. */}
      {!loading && rows.length > 0 && (
        <div className="md-page__pager">
          <span className="md-page__muted">
            Tổng {total} NCC
            {totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ""}
          </span>
          {totalPages > 1 && (
            <div className="md-page__pager-btns">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Sau
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
