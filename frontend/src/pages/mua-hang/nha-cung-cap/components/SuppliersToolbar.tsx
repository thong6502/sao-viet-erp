// Đầu màn Nhà cung cấp: thanh tiêu đề + tìm + lọc trạng thái + nút thêm, và dải KPI một hàng
// (tách từ pages/SuppliersPage.tsx).
import type { Dispatch, SetStateAction } from "react";
import { Button } from "../../../../components/Button";
import { Icon } from "../../../../components/Icons";
import type { LocSaoNcc } from "../shared/types";

export function SuppliersToolbar({
  q,
  setQ,
  status,
  setStatus,
  locSao,
  setLocSao,
  setPage,
  load,
  canCreate,
  openCreate,
  stats,
}: {
  q: string;
  setQ: Dispatch<SetStateAction<string>>;
  status: "all" | "active" | "inactive";
  setStatus: Dispatch<SetStateAction<"all" | "active" | "inactive">>;
  locSao: LocSaoNcc;
  setLocSao: Dispatch<SetStateAction<LocSaoNcc>>;
  setPage: Dispatch<SetStateAction<number>>;
  load: () => void;
  canCreate: boolean;
  openCreate: () => void;
  stats: { totalCount: number; activeCount: number; inactiveCount: number };
}) {
  return (
    <>
      {/* Đầu màn gọn 1 HÀNG như màn "Yêu cầu mua hàng": tiêu đề + badge đếm trái, ô tìm + lọc
          giữa, nút "+ Thêm NCC" phải. Bỏ eyebrow + mô tả để không chiếm chiều cao; dải KPI 3 chỉ
          số vẫn giữ ngay dưới (một hàng mỏng). */}
      <div className="purchase__topbar-unified">
        <div className="purchase__topbar-left">
          <h1 className="purchase__topbar-title">Nhà cung cấp</h1>
        </div>
        <div className="purchase__topbar-controls">
          <form
            className="purchase__search-wrap"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              load();
            }}
          >
            <span className="purchase__search-icon">
              <Icon name="search" size={16} />
            </span>
            <input
              className="input purchase__search-input"
              placeholder="Tìm Tên NCC, MST, SĐT, liên hệ, tên mặt hàng..."
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
              setStatus(e.target.value as "all" | "active" | "inactive");
              setPage(1);
            }}
          >
            <option value="active">Đang hợp tác</option>
            <option value="inactive">Tạm ngừng hợp tác</option>
            <option value="all">Tất cả trạng thái</option>
          </select>
          {/* Lọc theo SAO — sao do máy tự tính từ phiếu mua hàng (xem SaoNcc.tsx).
              CỐ Ý KHÔNG có mục "Chưa đánh giá": lọc ở đây trả lời câu "ai đáng tin", mà NCC chưa
              có đơn nào thì chưa trả lời được — họ nằm sẵn ở "Tất cả sao" rồi. */}
          <select
            className="input purchase__select-modern"
            value={locSao === null ? "all" : String(locSao)}
            onChange={(e) => {
              setLocSao(e.target.value === "all" ? null : Number(e.target.value));
              setPage(1);
            }}
            title="Lọc theo sao đánh giá"
          >
            <option value="all">Tất cả sao</option>
            <option value="4">Từ 4 sao trở lên</option>
            <option value="3">Từ 3 sao trở lên</option>
          </select>
        </div>
        {canCreate && (
          // ⚠️ TÊN LỚP ĐẶT NGƯỢC VỚI TÀI LIỆU: `variant="accent"` mới ra màu CAM thương hiệu,
          // `variant="primary"` ra màu NAVY. Đây là hành động chính DUY NHẤT của màn nền; nút cam
          // thứ hai của màn nằm trong DRAWER ("Lưu nhà cung cấp") — khác hộp nên không phạm luật
          // "tối đa MỘT nút cam mỗi màn / mỗi hộp thoại". Đừng nâng thêm nút nào lên accent.
          <div className="purchase__topbar-actions">
            <Button variant="accent" onClick={openCreate}>
              + Thêm NCC
            </Button>
          </div>
        )}
      </div>

      {/* DẢI CHỈ SỐ một hàng — bản mẫu `.rdx-compact-kpi` ở DepartmentsPage (và `.pay-kpibar` ở
          màn Công nợ). Trước 09/08/2026 đây là 3 THẺ cao ~78px với emoji tự chế 🏢 ✓ – :
            · emoji đổi hình theo font từng máy và không mang nghĩa cố định — "–" chẳng ai đọc ra
              "tạm ngừng"; icon nay lấy từ bộ `<Icon>` dùng chung nên cùng nét với mọi màn khác.
            · ba thẻ ăn gần một phần tư màn laptop cho thứ đọc mất một giây, đẩy BẢNG NCC (nội dung
              thật của màn) xuống dưới nếp gấp.
          Số ở đây đếm TOÀN BỘ nhà cung cấp (`allSuppliers`, tải riêng), không phải trang đang xem. */}
      <div className="supplier__kpi" aria-label="Tóm tắt nhà cung cấp">
        <div className="supplier__kpi-item">
          <span className="supplier__kpi-icon supplier__kpi-icon--steel">
            <Icon name="truck" size={15} />
          </span>
          <span className="supplier__kpi-body">
            <b className="supplier__kpi-val">{stats.totalCount}</b>
            <span className="supplier__kpi-lbl">Nhà cung cấp</span>
          </span>
        </div>

        <span className="supplier__kpi-sep" aria-hidden="true" />

        <div className="supplier__kpi-item">
          <span className="supplier__kpi-icon supplier__kpi-icon--ok">
            <Icon name="check" size={15} />
          </span>
          <span className="supplier__kpi-body">
            <b className="supplier__kpi-val">{stats.activeCount}</b>
            <span className="supplier__kpi-lbl">Đang hợp tác</span>
          </span>
        </div>

        <span className="supplier__kpi-sep" aria-hidden="true" />

        <div className="supplier__kpi-item">
          <span className="supplier__kpi-icon supplier__kpi-icon--warn">
            <Icon name="ban" size={15} />
          </span>
          <span className="supplier__kpi-body">
            <b className="supplier__kpi-val">{stats.inactiveCount}</b>
            <span className="supplier__kpi-lbl">Tạm ngừng</span>
          </span>
        </div>
      </div>
    </>
  );
}
