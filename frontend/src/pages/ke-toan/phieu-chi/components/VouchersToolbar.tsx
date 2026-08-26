// Thanh LỌC của màn Phiếu chi (tách từ pages/PaymentVouchersPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import { Button } from "../../../../components/Button";
import { STATUS_META } from "../shared/list-constants";

export function VouchersToolbar({
  q,
  setQ,
  setPage,
  load,
  typeFilter,
  setTypeFilter,
  statusFilter,
  setStatusFilter,
  canApprove,
  setStandaloneOpen,
}: {
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  setPage: Dispatch<SetStateAction<number>>;
  load: () => void;
  typeFilter: string;
  setTypeFilter: Dispatch<SetStateAction<string>>;
  statusFilter: string;
  setStatusFilter: Dispatch<SetStateAction<string>>;
  canApprove: boolean;
  setStandaloneOpen: Dispatch<SetStateAction<boolean>>;
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
          placeholder="Tìm PC, UNC, PMH, YCMH..."
        />
        {/* <Button type="submit" variant="ghost">
          Tìm
        </Button> */}
      </form>
      <div className="acct-toolbar__filters">
        <select
          className="input"
          value={typeFilter}
          onChange={(event) => {
            setTypeFilter(event.target.value);
            setPage(1);
          }}
        >
          <option value="all">Tất cả hình thức</option>
          <option value="cash">Tiền mặt</option>
          <option value="bank_transfer">Chuyển khoản</option>
        </select>
        <select
          className="input"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
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
        {canApprove && (
          <Button variant="accent" onClick={() => setStandaloneOpen(true)}>
            + Tạo phiếu chi
          </Button>
        )}
      </div>
    </section>
  );
}
