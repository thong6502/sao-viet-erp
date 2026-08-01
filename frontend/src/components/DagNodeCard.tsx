import React, { useMemo } from "react";
import type { RefRow } from "../pages/LsxRoutingTable";
import { type EditRow, n, phut, thoiLuong } from "../pages/lsxBuoc";
import { Icon } from "./Icons";
import { LSX_DON_VI_LABELS, LSX_LOAI_BUOC_META } from "../api/client";

export interface DagNodeCardProps {
  row: EditRow;
  index: number;
  total: number;
  position: { x: number; y: number };
  isSelected: boolean;
  isConnecting: boolean;
  isHoveredPort: "in" | "out" | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  warnings: string[];
  canUpdate: boolean;
  onNodeMouseDown: (e: React.MouseEvent, key: string) => void;
  onPortMouseDown: (e: React.MouseEvent, key: string, portType: "in" | "out") => void;
  onPortMouseUp: (e: React.MouseEvent, key: string, portType: "in" | "out") => void;
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
  toRefs,
  mayRefs,
  warnings,
  canUpdate,
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

  const mayTen = useMemo(() => {
    if (!row.may_id || !mayRefs) return null;
    return mayRefs.find((m) => m.id === row.may_id)?.ten ?? null;
  }, [row.may_id, mayRefs]);

  const thoiGian = useMemo(() => {
    const t = thoiLuong(row);
    return phut(t.tong);
  }, [row]);

  const meta = LSX_LOAI_BUOC_META[row.loai_buoc] ?? { label: row.loai_buoc };

  // Màu viền theo mức độ cảnh báo
  const hasError = warnings.some((w) => w.includes("chưa") || w.includes("đứt"));
  const hasWarning = warnings.length > 0 && !hasError;

  let cardClass = "dag-node";
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
        <span className="dag-node__title" title={row.ten}>
          {row.ten || "Công đoạn"}
        </span>

        <span className={`dag-node__type-tag dag-node__type-tag--${row.loai_buoc}`}>
          {meta.label}
        </span>

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
            <small>{LSX_DON_VI_LABELS[row.don_vi_vao] ?? row.don_vi_vao}</small>
          </span>
          <span className="dag-node__flow-arrow">➔</span>
          <span>
            {n(row.so_luong_ra) > 0 ? n(row.so_luong_ra).toLocaleString("vi-VN") : "—"}{" "}
            <small>{LSX_DON_VI_LABELS[row.don_vi_ra] ?? row.don_vi_ra}</small>
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
