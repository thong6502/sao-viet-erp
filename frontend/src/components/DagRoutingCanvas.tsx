import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RefRow } from "../pages/LsxRoutingTable";
import { type EditRow } from "../pages/lsxBuoc";
import { DagNodeCard } from "./DagNodeCard";
import { Icon } from "./Icons";
import "../pages/dag-routing.css";

export interface DagRoutingCanvasProps {
  rows: EditRow[];
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  canUpdate: boolean;
  onUpdateRows: (rows: EditRow[]) => void;
  onOpenDrawer: (index: number) => void;
  onAddStep: () => void;
}

interface Point {
  x: number;
  y: number;
}

/** Tự động tính toán vị trí phân tầng ( Sugiyama / Layered Layout ) */
function computeAutoLayout(rows: EditRow[]): Record<string, Point> {
  const rowMap = new Map<string, EditRow>();
  rows.forEach((r) => rowMap.set(r.key, r));

  // Tính level (độ sâu) của từng bước
  const levels = new Map<string, number>();

  function getLevel(key: string, visited = new Set<string>()): number {
    if (levels.has(key)) return levels.get(key)!;
    if (visited.has(key)) return 0; // Tránh treo nếu có cycle
    visited.add(key);

    const r = rowMap.get(key);
    if (!r || !r.phu_thuoc_step_keys || r.phu_thuoc_step_keys.length === 0) {
      levels.set(key, 0);
      return 0;
    }

    let maxPredLevel = -1;
    for (const predKey of r.phu_thuoc_step_keys) {
      if (rowMap.has(predKey)) {
        maxPredLevel = Math.max(maxPredLevel, getLevel(predKey, new Set(visited)));
      }
    }

    const lvl = maxPredLevel + 1;
    levels.set(key, lvl);
    return lvl;
  }

  rows.forEach((r) => getLevel(r.key));

  // Nhóm node theo level
  const levelGroups = new Map<number, string[]>();
  rows.forEach((r) => {
    const lvl = levels.get(r.key) ?? 0;
    if (!levelGroups.has(lvl)) levelGroups.set(lvl, []);
    levelGroups.get(lvl)!.push(r.key);
  });

  const positions: Record<string, Point> = {};
  const NODE_WIDTH = 240;
  const GAP_X = 80;
  const GAP_Y = 160;
  const START_X = 50;
  const START_Y = 50;

  levelGroups.forEach((keys, lvl) => {
    keys.forEach((key, idx) => {
      positions[key] = {
        x: START_X + lvl * (NODE_WIDTH + GAP_X),
        y: START_Y + idx * GAP_Y,
      };
    });
  });

  return positions;
}

/** Kiểm tra nếu thêm mối quan hệ targetKey -> dependsOnSourceKey có tạo chu trình lặp (Cycle) không */
function checkCreatesCycle(rows: EditRow[], targetKey: string, sourceKey: string): boolean {
  if (targetKey === sourceKey) return true;

  // Xây đồ thị phụ thuộc hiện tại: pred -> successors
  const graph = new Map<string, string[]>();
  rows.forEach((r) => {
    (r.phu_thuoc_step_keys || []).forEach((pred) => {
      if (!graph.has(pred)) graph.set(pred, []);
      graph.get(pred)!.push(r.key);
    });
  });

  // Tìm kiếm xem từ targetKey có đường đi nào tới sourceKey không
  const queue = [targetKey];
  const visited = new Set<string>();

  while (queue.length > 0) {
    const curr = queue.shift()!;
    if (curr === sourceKey) return true;
    if (!visited.has(curr)) {
      visited.add(curr);
      const nexts = graph.get(curr) || [];
      queue.push(...nexts);
    }
  }

  return false;
}

export function DagRoutingCanvas({
  rows,
  congDoanRefs: _congDoanRefs,
  toRefs,
  mayRefs,
  vatTuRefs: _vatTuRefs,
  phuThuocRefs: _phuThuocRefs,
  canUpdate,
  onUpdateRows,
  onOpenDrawer,
  onAddStep,
}: DagRoutingCanvasProps) {
  // State vị trí các node trên canvas
  const [positions, setPositions] = useState<Record<string, Point>>(() => computeAutoLayout(rows));
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  // State Zoom & Pan canvas
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<Point>({ x: 0, y: 0 });

  // State kéo node
  const [draggingKey, setDraggingKey] = useState<string | null>(null);
  const dragStartRef = useRef<Point>({ x: 0, y: 0 });
  const nodeStartPosRef = useRef<Point>({ x: 0, y: 0 });

  // State kéo nối dây (Creating Wire)
  const [connectingSourceKey, setConnectingSourceKey] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState<Point>({ x: 0, y: 0 });

  const viewportRef = useRef<HTMLDivElement>(null);

  // Cập nhật vị trí tự động cho các bước mới thêm chưa có vị trí
  useEffect(() => {
    setPositions((prev) => {
      const auto = computeAutoLayout(rows);
      const updated = { ...prev };
      let changed = false;
      rows.forEach((r) => {
        if (!updated[r.key]) {
          updated[r.key] = auto[r.key] || { x: 50, y: 50 };
          changed = true;
        }
      });
      return changed ? updated : prev;
    });
  }, [rows]);

  // Nút Sắp xếp tự động (Auto Layout)
  const handleAutoLayout = useCallback(() => {
    setPositions(computeAutoLayout(rows));
    setPan({ x: 0, y: 0 });
    setZoom(1);
  }, [rows]);

  // Tính toán đường cong Bezier giữa 2 cổng kết nối
  const calculateBezier = useCallback(
    (p1: Point, p2: Point) => {
      const dx = Math.max(50, Math.abs(p2.x - p1.x) / 2);
      return `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y}, ${p2.x - dx} ${p2.y}, ${p2.x} ${p2.y}`;
    },
    []
  );

  // Lấy vị trí Cổng Out (Bên phải Node)
  const getPortOutPos = useCallback(
    (key: string): Point => {
      const pos = positions[key] || { x: 0, y: 0 };
      return { x: pos.x + 240, y: pos.y + 60 };
    },
    [positions]
  );

  // Lấy vị trí Cổng In (Bên trái Node)
  const getPortInPos = useCallback(
    (key: string): Point => {
      const pos = positions[key] || { x: 0, y: 0 };
      return { x: pos.x, y: pos.y + 60 };
    },
    [positions]
  );

  // Sự kiện Bắt đầu Pan canvas khi click vào nền
  const handleViewportMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // Chỉ bắt chuột trái
    setIsPanning(true);
    panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    setSelectedKey(null);
  };

  // Sự kiện Bắt đầu Kéo thả Node
  const handleNodeMouseDown = (e: React.MouseEvent, key: string) => {
    e.stopPropagation();
    if (!canUpdate) return;
    setSelectedKey(key);
    setDraggingKey(key);
    dragStartRef.current = { x: e.clientX, y: e.clientY };
    nodeStartPosRef.current = positions[key] || { x: 0, y: 0 };
  };

  // Sự kiện MouseMove toàn màn hình để Pan / Drag Node / Drag Dây nối
  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      // Khi đang Pan canvas
      if (isPanning) {
        setPan({
          x: e.clientX - panStartRef.current.x,
          y: e.clientY - panStartRef.current.y,
        });
        return;
      }

      // Khi đang Drag 1 Node
      if (draggingKey) {
        const dx = (e.clientX - dragStartRef.current.x) / zoom;
        const dy = (e.clientY - dragStartRef.current.y) / zoom;
        const newX = Math.max(10, Math.round((nodeStartPosRef.current.x + dx) / 10) * 10);
        const newY = Math.max(10, Math.round((nodeStartPosRef.current.y + dy) / 10) * 10);
        setPositions((prev) => ({
          ...prev,
          [draggingKey]: { x: newX, y: newY },
        }));
        return;
      }

      // Khi đang Kéo dây nối
      if (connectingSourceKey && viewportRef.current) {
        const rect = viewportRef.current.getBoundingClientRect();
        const canvasX = (e.clientX - rect.left - pan.x) / zoom;
        const canvasY = (e.clientY - rect.top - pan.y) / zoom;
        setMousePos({ x: canvasX, y: canvasY });
      }
    },
    [isPanning, draggingKey, connectingSourceKey, pan, zoom]
  );

  // Thả chuột
  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
    setDraggingKey(null);
    if (connectingSourceKey) {
      setConnectingSourceKey(null);
    }
  }, [connectingSourceKey]);

  // Bắt đầu kéo dây từ Cổng Out
  const handlePortMouseDown = (_e: React.MouseEvent, key: string, portType: "in" | "out") => {
    if (!canUpdate || portType !== "out") return;
    setConnectingSourceKey(key);
    const startPos = getPortOutPos(key);
    setMousePos(startPos);
  };

  // Thả dây vào Cổng In của Node đích
  const handlePortMouseUp = (_e: React.MouseEvent, targetKey: string, portType: "in" | "out") => {
    if (!connectingSourceKey || portType !== "in" || connectingSourceKey === targetKey) {
      setConnectingSourceKey(null);
      return;
    }

    const sourceKey = connectingSourceKey;
    setConnectingSourceKey(null);

    // Kiểm tra chu trình lặp (Cycle prevention)
    if (checkCreatesCycle(rows, targetKey, sourceKey)) {
      alert("⚠️ Không thể nối dây: Mối quan hệ này sẽ tạo thành chu trình lặp (Cycle)!");
      return;
    }

    // Cập nhật danh sách phụ thuộc cho targetKey
    const nextRows = rows.map((r) => {
      if (r.key === targetKey) {
        const currentKeys = r.phu_thuoc_step_keys || [];
        if (!currentKeys.includes(sourceKey)) {
          return { ...r, phu_thuoc_step_keys: [...currentKeys, sourceKey] };
        }
      }
      return r;
    });

    onUpdateRows(nextRows);
  };

  // Xóa 1 dây nối phụ thuộc
  const handleDeleteWire = (targetKey: string, sourceKey: string) => {
    const nextRows = rows.map((r) => {
      if (r.key === targetKey) {
        return {
          ...r,
          phu_thuoc_step_keys: (r.phu_thuoc_step_keys || []).filter((k) => k !== sourceKey),
        };
      }
      return r;
    });
    onUpdateRows(nextRows);
  };

  // Xóa 1 Node công đoạn
  const handleDeleteNode = (index: number) => {
    const removedKey = rows[index]?.key;
    const nextRows = rows
      .filter((_, i) => i !== index)
      .map((r) => ({
        ...r,
        phu_thuoc_step_keys: (r.phu_thuoc_step_keys || []).filter((k) => k !== removedKey),
      }));
    onUpdateRows(nextRows);
  };

  // Danh sách dây nối SVG
  const wires = useMemo(() => {
    const list: {
      id: string;
      targetKey: string;
      sourceKey: string;
      path: string;
      midPoint: Point;
    }[] = [];

    rows.forEach((r) => {
      (r.phu_thuoc_step_keys || []).forEach((sourceKey) => {
        if (positions[sourceKey] && positions[r.key]) {
          const p1 = getPortOutPos(sourceKey);
          const p2 = getPortInPos(r.key);
          const path = calculateBezier(p1, p2);
          const midPoint = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
          list.push({
            id: `${sourceKey}->${r.key}`,
            sourceKey,
            targetKey: r.key,
            path,
            midPoint,
          });
        }
      });
    });

    return list;
  }, [rows, positions, getPortOutPos, getPortInPos, calculateBezier]);

  return (
    <div className="dag-wrapper">
      {/* Toolbar phía trên */}
      <div className="dag-toolbar">
        <div className="dag-toolbar__left">
          <button
            type="button"
            className="dag-btn-icon"
            onClick={handleAutoLayout}
            title="Tự động sắp xếp các bước công đoạn theo phân tầng"
          >
            <Icon name="layout" size={14} /> Sắp xếp tự động
          </button>

          {canUpdate && (
            <button
              type="button"
              className="dag-btn-icon"
              style={{ background: "#c25e38", color: "#fff", borderColor: "#c25e38" }}
              onClick={onAddStep}
            >
              <Icon name="plus" size={14} /> Thêm công đoạn
            </button>
          )}
        </div>

        <div className="dag-toolbar__right">
          {/* Zoom controls */}
          <div className="dag-legend">
            <span className="dag-legend__item">
              <span className="dag-legend__dot" style={{ background: "#2563eb" }} /> Cổng Vào
              (Input)
            </span>
            <span className="dag-legend__item">
              <span className="dag-legend__dot" style={{ background: "#c25e38" }} /> Cổng Ra
              (Output)
            </span>
          </div>

          <button
            type="button"
            className="dag-btn-icon"
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.1))}
            title="Thu nhỏ"
          >
            <Icon name="minus" size={13} />
          </button>
          <span style={{ fontSize: 12, fontWeight: 600, minWidth: 40, textAlign: "center" }}>
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            className="dag-btn-icon"
            onClick={() => setZoom((z) => Math.min(1.8, z + 0.1))}
            title="Phóng to"
          >
            <Icon name="plus" size={13} />
          </button>
        </div>
      </div>

      {/* Viewport Canvas */}
      <div
        ref={viewportRef}
        className="dag-viewport"
        onMouseDown={handleViewportMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        <div
          className="dag-canvas"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          }}
        >
          {/* Lớp SVG vẽ Dây nối */}
          <svg className="dag-svg-layer">
            {/* Dây nối chính thức */}
            {wires.map((w) => (
              <g key={w.id}>
                <path className="dag-wire" d={w.path} />
                {canUpdate && (
                  <g
                    className="dag-wire-delete"
                    transform={`translate(${w.midPoint.x}, ${w.midPoint.y})`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteWire(w.targetKey, w.sourceKey);
                    }}
                  >
                    <circle r="9" fill="#8c959f" />
                    <text
                      x="0"
                      y="3.5"
                      textAnchor="middle"
                      fill="#fff"
                      fontSize="11"
                      fontWeight="bold"
                    >
                      ×
                    </text>
                  </g>
                )}
              </g>
            ))}

            {/* Dây nối nháp đang kéo (Draft wire) */}
            {connectingSourceKey && (
              <path
                className="dag-wire--draft"
                d={calculateBezier(getPortOutPos(connectingSourceKey), mousePos)}
              />
            )}
          </svg>

          {/* Lớp các Node công đoạn */}
          {rows.map((r, i) => {
            const pos = positions[r.key] || { x: 50 + i * 260, y: 50 };
            return (
              <DagNodeCard
                key={r.key}
                row={r}
                index={i}
                total={rows.length}
                position={pos}
                isSelected={selectedKey === r.key}
                isConnecting={connectingSourceKey !== null}
                isHoveredPort={null}
                toRefs={toRefs}
                mayRefs={mayRefs}
                warnings={[]}
                canUpdate={canUpdate}
                onNodeMouseDown={handleNodeMouseDown}
                onPortMouseDown={handlePortMouseDown}
                onPortMouseUp={handlePortMouseUp}
                onOpenDrawer={onOpenDrawer}
                onDeleteNode={handleDeleteNode}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
