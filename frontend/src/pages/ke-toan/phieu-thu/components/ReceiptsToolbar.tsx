// Thanh LỌC của màn Phiếu thu (tách từ pages/PaymentReceiptsPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import { Button } from "../../../../components/Button";
import { STATUS_META } from "../shared/constants";

export function ReceiptsToolbar({
  q,
  setQ,
  setPage,
  load,
  statusFilter,
  setStatusFilter,
  canApprove,
  setCreatingOther,
}: {
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  setPage: Dispatch<SetStateAction<number>>;
  load: () => void;
  statusFilter: string;
  setStatusFilter: Dispatch<SetStateAction<string>>;
  canApprove: boolean;
  setCreatingOther: Dispatch<SetStateAction<boolean>>;
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
          placeholder="Tìm PT, hóa đơn, đơn bán, PC, người nộp..."
        />
        {/* <Button type="submit" variant="ghost">
          Tìm
        </Button> */}
      </form>
      <div className="acct-toolbar__filters">
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
          <Button variant="accent" onClick={() => setCreatingOther(true)}>
            + Tạo phiếu thu
          </Button>
        )}
      </div>
    </section>
  );
}
