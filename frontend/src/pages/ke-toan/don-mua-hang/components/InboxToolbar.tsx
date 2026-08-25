// Thanh LỌC của màn Đơn mua hàng (Kế toán) — tách từ pages/AccountingPurchaseInboxPage.tsx.
import type { Dispatch, SetStateAction } from "react";
import type { SupplierRow } from "../../../../api/client";
import { STATUS_META } from "../shared/constants";
import type { DepositFilter } from "../shared/types";

export function InboxToolbar({
  q,
  setQ,
  setPage,
  load,
  statusFilter,
  setStatusFilter,
  supplierFilter,
  setSupplierFilter,
  suppliers,
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
}: {
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  setPage: Dispatch<SetStateAction<number>>;
  load: () => void;
  statusFilter: string;
  setStatusFilter: Dispatch<SetStateAction<string>>;
  supplierFilter: number | "all";
  setSupplierFilter: Dispatch<SetStateAction<number | "all">>;
  suppliers: SupplierRow[];
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
}) {
  return (
    <section className="acct-toolbar">
      <form
        className="md-page__search"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          load();
        }}
      >
        <input
          className="input"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Tìm mã đơn, YCMH, nhà cung cấp..."
        />
        {/* <Button type="submit" variant="ghost">
          Tìm
        </Button> */}
      </form>
      <select
        className="input acct-toolbar__select"
        value={statusFilter}
        onChange={(event) => {
          setStatusFilter(event.target.value);
          setPage(1);
        }}
      >
        <option value="all">Tất cả trạng thái</option>
        {/* Bỏ "Nháp": đơn nháp là thu mua còn đang sửa, CHƯA gửi duyệt — kế toán không có việc
            gì với nó. Backend cũng đã loại hẳn khỏi hộp thư này, để đây chỉ là cho khớp. */}
        {Object.entries(STATUS_META)
          .filter(([value]) => value !== "draft")
          .map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.label}
            </option>
          ))}
      </select>
      <select
        className="input acct-toolbar__select"
        value={supplierFilter}
        onChange={(event) => {
          setSupplierFilter(event.target.value === "all" ? "all" : Number(event.target.value));
          setPage(1);
        }}
      >
        <option value="all">Tất cả nhà cung cấp</option>
        {suppliers.map((supplier) => (
          <option key={supplier.id} value={supplier.id}>
            {supplier.name}
          </option>
        ))}
      </select>
      <select
        className="input acct-toolbar__select"
        value={depositFilter}
        onChange={(event) => {
          setDepositFilter(event.target.value as DepositFilter);
          setPage(1);
        }}
      >
        <option value="all">Tất cả tiền cọc</option>
        <option value="none">Không yêu cầu cọc</option>
        <option value="unpaid">Chưa cọc</option>
        <option value="partial">Cọc thiếu</option>
        <option value="enough">Cọc đủ</option>
      </select>
      <div className="acct-toolbar__date-group">
        <span>Ngày tạo</span>
        <input
          className="input acct-toolbar__date"
          type="date"
          title="Ngày tạo từ"
          value={createdFrom}
          onChange={(event) => {
            setCreatedFrom(event.target.value);
            setPage(1);
          }}
        />
        <input
          className="input acct-toolbar__date"
          type="date"
          title="Ngày tạo đến"
          value={createdTo}
          onChange={(event) => {
            setCreatedTo(event.target.value);
            setPage(1);
          }}
        />
      </div>
      <div className="acct-toolbar__date-group">
        <span>Ngày cần hàng</span>
        <input
          className="input acct-toolbar__date"
          type="date"
          title="Ngày cần từ"
          value={neededFrom}
          onChange={(event) => {
            setNeededFrom(event.target.value);
            setPage(1);
          }}
        />
        <input
          className="input acct-toolbar__date"
          type="date"
          title="Ngày cần đến"
          value={neededTo}
          onChange={(event) => {
            setNeededTo(event.target.value);
            setPage(1);
          }}
        />
      </div>
    </section>
  );
}
