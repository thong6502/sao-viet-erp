// Thanh trên cùng của màn Yêu cầu mua hàng: tiêu đề + ô tìm + lọc trạng thái + nút tạo
// (tách từ pages/DepartmentPurchaseRequestsPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import { SOURCE_STATUS_META } from "../shared/constants";
import type { StatusFilter } from "../shared/types";

export function RequestsToolbar({
  loading,
  total,
  q,
  setQ,
  status,
  setStatus,
  setPage,
  load,
  canCreate,
  openCreate,
}: {
  loading: boolean;
  total: number;
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  status: StatusFilter;
  setStatus: Dispatch<SetStateAction<StatusFilter>>;
  setPage: Dispatch<SetStateAction<number>>;
  load: () => void;
  canCreate: boolean;
  openCreate: () => void;
}) {
  return (
      <div className="purchase__topbar-unified">
        <div className="purchase__topbar-left">
          <h1 className="purchase__topbar-title">Yêu cầu mua hàng</h1>
          <span className="purchase__count-badge">{loading ? "..." : total}</span>
        </div>
        <div className="purchase__topbar-controls">
          <form
            className="purchase__search-wrap"
            onSubmit={(e) => {
              e.preventDefault();
              load();
            }}
          >
            <span className="purchase__search-icon">
              <Icon name="search" size={16} />
            </span>
            <input
              className="input purchase__search-input"
              placeholder="Tìm mã yêu cầu, mục đích, vật tư..."
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
            {Object.entries(SOURCE_STATUS_META).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </div>
        <div className="purchase__topbar-actions">
          {canCreate && (
            <Button variant="accent" onClick={openCreate}>
              + Tạo yêu cầu mua
            </Button>
          )}
        </div>
      </div>
  );
}
