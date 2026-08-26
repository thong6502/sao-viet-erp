// Tab "Đơn mua hàng" — bảng phiếu mua + bộ lọc (tách từ pages/PurchaseRequestsPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import type { PurchaseRequestRow, SupplierRow } from "../../../../api/client";
import { CodeLink } from "../../../../components/CodeLink";
import { EmptyRow } from "../../../../components/EmptyState";
import { Icon } from "../../../../components/Icons";
import { Select, type SelectOption } from "../../../../components/Select";
import { fmtDate, money } from "../../../../utils/format";
import { STATUS_META } from "../shared/constants";
import { noiDung } from "../shared/helpers";
import type { DepositFilter, PurchaseTab, StatusFilter } from "../shared/types";
import { DepositCell, StatusBadge } from "../components/purchaseCells";

export function PhieuListTab({
  coYcQuaHan,
  choMua,
  setTab,
  q,
  setQ,
  page,
  setPage,
  status,
  setStatus,
  supplierFilter,
  setSupplierFilter,
  depositFilter,
  setDepositFilter,
  createdFrom,
  setCreatedFrom,
  createdTo,
  setCreatedTo,
  neededFrom,
  setNeededFrom,
  neededTo,
  setNeededTo,
  suppliers,
  loading,
  listError,
  load,
  rows,
  selected,
  setSelectedId,
  openYcmh,
  total,
  totalPages,
}: {
  coYcQuaHan: boolean;
  choMua: { soLuong: number; somNhat: string | null };
  setTab: Dispatch<SetStateAction<PurchaseTab>>;
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  status: StatusFilter;
  setStatus: Dispatch<SetStateAction<StatusFilter>>;
  supplierFilter: number | "all";
  setSupplierFilter: Dispatch<SetStateAction<number | "all">>;
  depositFilter: DepositFilter;
  setDepositFilter: Dispatch<SetStateAction<DepositFilter>>;
  createdFrom: string;
  setCreatedFrom: Dispatch<SetStateAction<string>>;
  createdTo: string;
  setCreatedTo: Dispatch<SetStateAction<string>>;
  neededFrom: string;
  setNeededFrom: Dispatch<SetStateAction<string>>;
  neededTo: string;
  setNeededTo: Dispatch<SetStateAction<string>>;
  suppliers: SupplierRow[];
  loading: boolean;
  listError: string | null;
  load: () => void;
  rows: PurchaseRequestRow[];
  selected: PurchaseRequestRow | null;
  setSelectedId: Dispatch<SetStateAction<number | null>>;
  openYcmh: (code: string) => void;
  total: number;
  totalPages: number;
}) {
  // Ô lọc NCC là <Select searchable> chứ không phải <select>: danh sách nhà cung cấp dài, thẻ
  // gốc không gõ tìm được. Giữ NGUYÊN kiểu giá trị `"all" | number` và thứ tự option cũ.
  const supplierOptions: SelectOption<number | "all">[] = [
    { value: "all", label: "Tất cả nhà cung cấp" },
    ...suppliers.map((supplier) => ({ value: supplier.id, label: supplier.name })),
  ];
  return (
    <>
    {/* Dải nhắc CHỈ hiện khi có yêu cầu đã quá ngày cần hàng — nó là lời cảnh báo, không phải
        thanh trạng thái. Ngày bình thường không render gì cả (xem `coYcQuaHan`). */}
    {coYcQuaHan && (
      <div className="purchase__nhac" role="status">
        <Icon name="alert" size={14} />
        <span>
          <b>{choMua.soLuong}</b> yêu cầu đang chờ, sớm nhất cần{" "}
          {fmtDate(choMua.somNhat)}
        </span>
        <button
          type="button"
          className="purchase__nhac-xem"
          onClick={() => setTab("yeu-cau")}
        >
          Xem
        </button>
      </div>
    )}

    <section className="card md-page__tablewrap purchase__list">
      {/* Ô tìm + bộ lọc ngay đầu thẻ, dồn TRÁI; KHÔNG lặp tiêu đề "Đơn mua hàng" — đã có trên tab. */}
      <div className="purchase__list-tools purchase__source-toolbar">
          <form
            className="md-page__search purchase__search-wrap"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
            }}
          >
            <span className="purchase__search-icon">
              <Icon name="search" size={16} />
            </span>
            <input
              className="input purchase__search-input"
              placeholder="Tìm mã phiếu, mục đích, ghi chú..."
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </form>
          <select
            className="input purchase__select-modern"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as StatusFilter);
              setPage(1);
            }}
          >
            <option value="all">Tất cả trạng thái</option>
            {Object.entries(STATUS_META).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
          <div className="purchase__filter-select">
            <Select
              options={supplierOptions}
              value={supplierFilter}
              onChange={(v) => {
                setSupplierFilter(v === "all" ? "all" : Number(v));
                setPage(1);
              }}
              ariaLabel="Lọc nhà cung cấp"
              searchable
              searchPlaceholder="Tìm nhà cung cấp…"
              portal
              className="purchase__select-modern"
            />
          </div>
          <select
            className="input purchase__select-modern"
            value={depositFilter}
            onChange={(e) => {
              setDepositFilter(e.target.value as DepositFilter);
              setPage(1);
            }}
          >
            <option value="all">Tất cả tiền cọc</option>
            <option value="none">Không yêu cầu cọc</option>
            <option value="unpaid">Chưa cọc</option>
            <option value="partial">Cọc thiếu</option>
            <option value="enough">Cọc đủ</option>
          </select>
          <div className="purchase__date-group">
            <span>Ngày tạo</span>
            <input
              className="input purchase__date-filter"
              type="date"
              title="Ngày tạo từ"
              value={createdFrom}
              onChange={(e) => {
                setCreatedFrom(e.target.value);
                setPage(1);
              }}
            />
            <input
              className="input purchase__date-filter"
              type="date"
              title="Ngày tạo đến"
              value={createdTo}
              onChange={(e) => {
                setCreatedTo(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div className="purchase__date-group">
            <span>Ngày cần hàng</span>
            <input
              className="input purchase__date-filter"
              type="date"
              title="Ngày cần từ"
              value={neededFrom}
              onChange={(e) => {
                setNeededFrom(e.target.value);
                setPage(1);
              }}
            />
            <input
              className="input purchase__date-filter"
              type="date"
              title="Ngày cần đến"
              value={neededTo}
              onChange={(e) => {
                setNeededTo(e.target.value);
                setPage(1);
              }}
            />
          </div>
      </div>

      <table className="md-page__table">
        <thead>
          <tr>
            {/* KHÔNG còn cột "Thao tác": bấm vào DÒNG mở drawer chi tiết, mọi thao tác (In · Sửa ·
                Gửi duyệt · Ghi đợt giao · Huỷ…) nằm ở chân drawer. Gộp thao tác vào bản ghi cho
                khớp Yêu cầu mua hàng của phòng ban (24/08/2026). */}
            <th>Mã đơn</th>
            <th>Nhà cung cấp</th>
            <th>Ngày tạo</th>
            <th>Cần / Dự kiến nhận</th>
            <th>Tổng dự kiến</th>
            <th>Tiền cọc</th>
            <th>Người tạo / duyệt</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk-${i}`} className="purchase__skeleton-row">
                <td><div className="purchase__skeleton-bar" style={{ width: "120px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "150px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "80px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "90px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
                <td><div className="purchase__skeleton-bar" style={{ width: "110px" }} /></td>
              </tr>
            ))
          ) : listError ? (
            <EmptyRow colSpan={8} trangThai="loi" loi={listError} onThuLai={load} />
          ) : rows.length === 0 ? (
            <EmptyRow
              colSpan={8}
              icon="cart"
              title="Chưa có đơn mua hàng nào khớp"
              sub={
                q.trim() ||
                status !== "all" ||
                supplierFilter !== "all" ||
                depositFilter !== "all" ||
                createdFrom ||
                createdTo ||
                neededFrom ||
                neededTo
                  ? "Thử bỏ bớt bộ lọc hoặc xoá từ khoá tìm kiếm."
                  : "Sang tab Yêu cầu chờ xử lý để chọn một yêu cầu rồi lập đơn mua."
              }
              action={
                q.trim() ||
                status !== "all" ||
                supplierFilter !== "all" ||
                depositFilter !== "all" ||
                createdFrom ||
                createdTo ||
                neededFrom ||
                neededTo ? (
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => {
                      setQ("");
                      setStatus("all");
                      setSupplierFilter("all");
                      setDepositFilter("all");
                      setCreatedFrom("");
                      setCreatedTo("");
                      setNeededFrom("");
                      setNeededTo("");
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
                className={`md-page__row${selected?.id === row.id ? " purchase__row--selected" : ""}`}
                onClick={() => setSelectedId(row.id)}
              >
                <td className="purchase__code-cell">
                  <strong className="md-page__mono">{row.code}</strong>
                  <div className="purchase__source-codes">
                    {row.sources.length
                      ? row.sources.map((source, index) => (
                          <span key={source.id}>
                            {index > 0 && ", "}
                            <CodeLink
                              code={source.code}
                              onOpen={openYcmh}
                            />
                          </span>
                        ))
                      : "Chưa gắn yêu cầu"}
                  </div>
                  <div className="md-page__muted purchase__row-purpose">
                    {noiDung(row) || "—"}
                  </div>
                </td>
                <td
                  className="purchase__supplier-cell"
                  title={row.supplier_name ?? undefined}
                >
                  {row.supplier_name || (
                    <span className="md-page__muted">Chưa chọn</span>
                  )}
                </td>
                <td className="purchase__date-cell">
                  {fmtDate(row.created_at)}
                </td>
                <td className="purchase__date-cell">
                  {fmtDate(row.needed_date)}
                  {row.expected_receipt_date && (
                    <div className="md-page__muted">
                      Nhận: {fmtDate(row.expected_receipt_date)}
                    </div>
                  )}
                </td>
                <td className="md-page__price purchase__money-cell">
                  {money(row.total_estimate)}
                </td>
                <td className="md-page__price purchase__money-cell">
                  <DepositCell row={row} />
                </td>
                <td>
                  <div>
                    {row.created_by_name || (
                      <span className="md-page__muted">—</span>
                    )}
                  </div>
                  <div className="md-page__muted">
                    {row.approved_by_name || "Chưa duyệt"}
                  </div>
                </td>
                <td>
                  <StatusBadge status={row.status} />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      {/* Chân bảng CÙNG KHUÔN với bảng yêu cầu phía trên: tổng bên trái, nút chuyển trang bên
          phải, và CHỈ hiện nút khi thật sự có nhiều hơn một trang. Trước 08/08/2026 khối này
          nằm ngoài thẻ và luôn in "Trang 1/1" kèm hai nút mờ — nhiễu mà không nói thêm gì. */}
      {!loading && (
      <div className="purchase__source-foot">
        <span className="md-page__muted">
          Tổng {total} đơn
          {totalPages > 1 ? ` · Trang ${page}/${totalPages}` : ""}
        </span>
        {totalPages > 1 && (
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
        )}
      </div>
      )}
    </section>
    </>
  );
}
