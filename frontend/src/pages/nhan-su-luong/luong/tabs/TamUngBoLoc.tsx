// Thanh tab trạng thái + bộ lọc loại / tổ / tìm của tab Tạm ứng (25/09/2026) — xem `tamUngLoc.ts`.
import { Search, X } from "lucide-react";
import {
  TAB_TRANG_THAI,
  type BoLocTamUng,
  type LocLoai,
  type TabTrangThai,
} from "./tamUngLoc";

const LOAI: { key: LocLoai; nhan: string }[] = [
  { key: "tat_ca", nhan: "Mọi loại" },
  { key: "tam_ung", nhan: "Tạm ứng" },
  { key: "luong_dot_1", nhan: "Lương đợt 1" },
];

export function TamUngBoLoc({
  tab,
  onTab,
  dem,
  loc,
  onLoc,
  to,
}: {
  tab: TabTrangThai;
  onTab: (t: TabTrangThai) => void;
  dem: Record<TabTrangThai, number>;
  loc: BoLocTamUng;
  onLoc: (l: BoLocTamUng) => void;
  to: { id: string; ten: string }[];
}) {
  return (
    <div className="lg-tu-loc">
      <div className="lg-seg lg-tu-loc__tab" role="tablist" aria-label="Trạng thái phiếu">
        {TAB_TRANG_THAI.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? "is-active" : ""}
            onClick={() => onTab(t.key)}
          >
            {t.nhan} <span className="lg-tu-loc__dem">{dem[t.key]}</span>
          </button>
        ))}
      </div>
      <div className="lg-tu-loc__hang">
        <div className="lg-seg" role="group" aria-label="Loại phiếu">
          {LOAI.map((l) => (
            <button
              key={l.key}
              type="button"
              className={loc.loai === l.key ? "is-active" : ""}
              onClick={() => onLoc({ ...loc, loai: l.key })}
            >
              {l.nhan}
            </button>
          ))}
        </div>
        {to.length > 1 && (
          <select
            className="lg-dept-filter"
            value={loc.to}
            onChange={(e) => onLoc({ ...loc, to: e.target.value })}
            aria-label="Lọc theo tổ"
          >
            <option value="">Tất cả phòng / tổ</option>
            {to.map((d) => (
              <option key={d.id} value={d.id}>
                {d.ten}
              </option>
            ))}
          </select>
        )}
        <div className="lg-search-wrapper">
          <span className="lg-search-icon">
            <Search size={14} />
          </span>
          <input
            className="lg-search-input"
            placeholder="Tìm tên / mã NV / mã phiếu…"
            value={loc.tim}
            onChange={(e) => onLoc({ ...loc, tim: e.target.value })}
          />
          {loc.tim && (
            <button
              type="button"
              className="lg-search-clear"
              onClick={() => onLoc({ ...loc, tim: "" })}
              title="Xóa tìm kiếm"
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
