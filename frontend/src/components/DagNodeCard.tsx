import React, { useMemo } from "react";
import { dvNhan, type RefRow } from "../pages/LsxRoutingTable";
import { type EditRow, n, phut, tenBuoc, thoiLuong } from "../pages/lsxBuoc";
import { Icon } from "./Icons";
import { ChipKhuon, ChipLoaiBuoc } from "./ChipBuoc";

export interface DagNodeCardProps {
  row: EditRow;
  index: number;
  total: number;
  position: { x: number; y: number };
  isSelected: boolean;
  isConnecting: boolean;
  isHoveredPort: "in" | "out" | null;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  warnings: string[];
  /** Khác null = bước in này CHẠY CHUNG tờ với bài ghép đó — thông số tờ sửa ở bài. */
  maBaiGhep?: string | null;
  canUpdate: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onNodeMouseDown: (e: React.MouseEvent, key: string) => void;
  onPortMouseDown: (e: React.MouseEvent, key: string, portType: "in" | "out") => void;
  onPortMouseUp: (e: React.MouseEvent, key: string, portType: "in" | "out") => void;
  /** `tab` chỉ dùng cho deep-link từ badge — mở drawer là nhảy thẳng tới khối đó. */
  onOpenDrawer: (index: number) => void;
  onDeleteNode: (index: number) => void;
}

export function DagNodeCard({
  row,
  index,
  total: _total,
  position,
  isSelected,
  isConnecting: _isConnecting,
  isHoveredPort,
  congDoanRefs,
  toRefs,
  mayRefs,
  warnings,
  maBaiGhep,
  canUpdate,
  onMouseEnter,
  onMouseLeave,
  onNodeMouseDown,
  onPortMouseDown,
  onPortMouseUp,
  onOpenDrawer,
  onDeleteNode,
}: DagNodeCardProps) {
  // Tìm nhãn tổ & máy
  const toTen = useMemo(() => {
    if (!row.department_id || !toRefs) return null;
    return toRefs.find((t) => t.id === row.department_id)?.ten ?? null;
  }, [row.department_id, toRefs]);

  // Máy đang gán — nguồn tốc độ + thời gian chuẩn bị của công thức thời lượng. Trước đây chỉ lấy
  // mỗi TÊN để in badge, còn `thoiLuong(row)` gọi không kèm máy nên node luôn hiện "—" dù drawer
  // ngay cạnh đã tính ra số: hai chỗ cùng công thức mà một chỗ thiếu đầu vào.
  const may = useMemo(
    () => (row.may_id && mayRefs ? mayRefs.find((m) => m.id === row.may_id) ?? null : null),
    [row.may_id, mayRefs],
  );
  const mayTen = may?.ten ?? null;

  const thoiGian = useMemo(() => {
    const t = thoiLuong(row, may);
    return phut(t.tong);
  }, [row, may]);

  // Màu viền theo mức độ cảnh báo
  const hasError = warnings.some((w) => w.includes("chưa") || w.includes("đứt"));
  const hasWarning = warnings.length > 0 && !hasError;

  let cardClass = "dag-node";
  if (maBaiGhep) cardClass += " dag-node--ghep";
  if (isSelected) cardClass += " dag-node--selected";
  else if (hasError) cardClass += " dag-node--has-error";
  else if (hasWarning) cardClass += " dag-node--has-warning";

  const seqNumber = (index + 1) * 10;

  return (
    <div
      className={cardClass}
      style={{
        left: `${position.x}px`,
        top: `${position.y}px`,
      }}
      onMouseDown={(e) => onNodeMouseDown(e, row.key)}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Cổng vào (Input Port - bên trái) */}
      <div
        className={`dag-port dag-port--in ${isHoveredPort === "in" ? "dag-port--in-target" : ""}`}
        title="Tiền nhiệm (Input) - Bấm kéo dây từ bước trước nối vào đây"
        onMouseDown={(e) => {
          e.stopPropagation();
          onPortMouseDown(e, row.key, "in");
        }}
        onMouseUp={(e) => {
          e.stopPropagation();
          onPortMouseUp(e, row.key, "in");
        }}
      />

      {/* Header của Card */}
      <div className="dag-node__head">
        <span className="dag-node__seq">#{seqNumber}</span>
        <span className="dag-node__title" title={tenBuoc(row, congDoanRefs)}>
          {tenBuoc(row, congDoanRefs) || "Công đoạn"}
        </span>

        {maBaiGhep ? (
          <span className="dag-node__type-tag dag-node__type-tag--ghep" title="Chạy chung tờ">
            {maBaiGhep}
          </span>
        ) : (
          /* Chip DÙNG CHUNG với bảng công đoạn và các màn xưởng (`ChipBuoc`) — thẻ DAG trước đây
             tự vẽ lại nhãn từ `LSX_LOAI_BUOC_META` nên bước thuê ngoài chưa điền nơi làm chỉ hiện
             chữ "Thuê ngoài" trống trơn, không ai biết còn thiếu gì. */
          <ChipLoaiBuoc loai_buoc={row.loai_buoc} nha_cung_cap={row.nha_cung_cap} />
        )}
        {/* Con dao của bước — thẻ DAG là chỗ người kế hoạch nhìn cả chuỗi một lượt, thiếu dao phải
            thấy ngay ở đây chứ không phải mở từng drawer. */}
        <ChipKhuon
          can_khuon={row.requires_tooling}
          khuon={{
            ma: row.khuon_be_ma,
            so_ke: row.khuon_be_so_ke,
            tinh_trang: row.khuon_be_tinh_trang,
            ngay_ve_du_kien: row.khuon_be_ngay_ve,
          }}
        />

        {canUpdate && (
          <div className="dag-node__actions">
            <button
              type="button"
              className="dag-node__btn"
              title="Sửa chi tiết bước (Mở Drawer)"
              onClick={(e) => {
                e.stopPropagation();
                onOpenDrawer(index);
              }}
            >
              <Icon name="edit" size={12} />
            </button>
            <button
              type="button"
              className="dag-node__btn dag-node__btn--delete"
              title="Xóa công đoạn này"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteNode(index);
              }}
            >
              <Icon name="x" size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Body của Card */}
      <div className="dag-node__body">
        {/* Tổ / Máy */}
        <div className="dag-node__row">
          <span className="dag-node__badge">
            <Icon name="users" size={11} />
            {toTen ? `Tổ ${toTen}` : "Chưa chọn tổ"}
          </span>
          {mayTen && (
            <span className="dag-node__badge" title={`Máy: ${mayTen}`}>
              <Icon name="cpu" size={11} />
              {mayTen}
            </span>
          )}
        </div>

        {/* Luồng số lượng Vào -> Ra */}
        <div className="dag-node__flow">
          <span>
            {n(row.so_luong_vao) > 0 ? n(row.so_luong_vao).toLocaleString("vi-VN") : "—"}{" "}
            <small>{dvNhan(row.don_vi_vao, row)}</small>
          </span>
          <span className="dag-node__flow-arrow">➔</span>
          <span>
            {n(row.so_luong_ra) > 0 ? n(row.so_luong_ra).toLocaleString("vi-VN") : "—"}{" "}
            <small>{dvNhan(row.don_vi_ra, row)}</small>
          </span>
        </div>

        {/* Thời lượng */}
        <div className="dag-node__row">
          <span className="dag-node__label">Thời lượng:</span>
          <span className="dag-node__value">{thoiGian}</span>
        </div>

        {/* Cảnh báo nếu có */}
        {warnings.length > 0 && (
          <div className="dag-node__warnings">
            {warnings.map((w, idx) => (
              <span
                key={idx}
                className={`dag-node__warning-chip ${
                  w.includes("chưa") || w.includes("đứt")
                    ? "dag-node__warning-chip--err"
                    : "dag-node__warning-chip--warn"
                }`}
              >
                ⚠️ {w}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Cổng ra (Output Port - bên phải) */}
      <div
        className="dag-port dag-port--out"
        title="Kế nhiệm (Output) - Bấm giữ kéo dây nối sang bước tiếp theo"
        onMouseDown={(e) => {
          e.stopPropagation();
          onPortMouseDown(e, row.key, "out");
        }}
        onMouseUp={(e) => {
          e.stopPropagation();
          onPortMouseUp(e, row.key, "out");
        }}
      />
    </div>
  );
}
