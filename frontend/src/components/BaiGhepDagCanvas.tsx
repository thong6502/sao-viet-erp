import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BaiGhepSoDo as SoDo } from "../api/client";
import { LSX_LOAI_BUOC_META } from "../api/client";
import { Icon } from "./Icons";
import { ChipGap, classHan, ngay, num } from "../pages/keHoachSxShared";
import { phut } from "../pages/lsxBuoc";

const MAU_NHANH = ["#c25e38", "#2563eb", "#059669", "#7c5cbf", "#b7791f", "#be185d"];
function mau(i: number): string {
  return MAU_NHANH[i % MAU_NHANH.length];
}

interface Point {
  x: number;
  y: number;
}

export interface BaiGhepDagCanvasProps {
  sd: SoDo;
  chon: "in" | number | null;
  onChon: (val: "in" | number) => void;
  onMoLenh?: (lsxId: number) => void;
}

const CARD_NODE_W = 175;
const CARD_NODE_H = 68;
const CARD_IN_W = 235;
const CARD_IN_H = 105;
const BRANCH_HDR_W = 155;
const GAP_X = 52;

function getStepIcon(loaiBuoc: string): string {
  switch (loaiBuoc) {
    case "thue_ngoai":
      return "truck";
    case "may":
    case "print":
      return "printer";
    case "phu":
    case "ctp":
      return "layers";
    case "dong_goi":
      return "package";
    case "kcs":
      return "check-circle";
    default:
      return "sliders";
  }
}

export function BaiGhepDagCanvas({ sd, chon, onChon, onMoLenh }: BaiGhepDagCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Viewport State
  const [zoom, setZoom] = useState(0.92);
  const [pan, setPan] = useState<Point>({ x: 30, y: 30 });
  const [isPanning, setIsPanning] = useState(false);
  const [showGrid, setShowGrid] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const panStartRef = useRef<Point>({ x: 0, y: 0 });
  const panInitialRef = useRef<Point>({ x: 0, y: 0 });

  // Node Drag Positions
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [draggingNode, setDraggingNode] = useState<{ id: string; startMouse: Point; startPos: Point } | null>(null);

  const ngoaiMap = useMemo(() => new Map(sd.ngoai.map((o) => [o.step_key, o])), [sd.ngoai]);

  const initialPositions = useMemo(() => {
    const pos: Record<string, Point> = {};
    const nhanhList = sd.nhanh;
    if (nhanhList.length === 0) return pos;

    const rowHeight = 135;
    const startY = 50;

    let maxTruocInCount = 1;
    nhanhList.forEach((n) => {
      if (n.truoc_in.length > maxTruocInCount) maxTruocInCount = n.truoc_in.length;
    });

    const centerInX = 30 + BRANCH_HDR_W + 60 + maxTruocInCount * (CARD_NODE_W + GAP_X);

    pos["in"] = { x: centerInX, y: startY + (nhanhList.length * rowHeight) / 2 - CARD_IN_H / 2 + 10 };

    nhanhList.forEach((n, idx) => {
      const y = startY + idx * rowHeight + 15;

      pos[`hdr_left_${n.lsx_id}`] = { x: 30, y: y + 10 };

      let curXLeft = 30 + BRANCH_HDR_W + 50;
      n.truoc_in.forEach((node) => {
        pos[`node_${node.step_key}`] = { x: curXLeft, y };
        curXLeft += CARD_NODE_W + GAP_X;
      });

      let curXRight = centerInX + CARD_IN_W + 60;
      n.sau_in.forEach((node) => {
        node.phu_thuoc_step_keys.forEach((pk) => {
          if (ngoaiMap.has(pk) && !pos[`ngoai_${pk}`]) {
            pos[`ngoai_${pk}`] = { x: curXRight, y: y - 48 };
          }
        });

        pos[`node_${node.step_key}`] = { x: curXRight, y };
        curXRight += CARD_NODE_W + GAP_X;
      });

      pos[`hdr_right_${n.lsx_id}`] = { x: curXRight, y: y + 14 };
    });

    return pos;
  }, [sd, ngoaiMap]);

  useEffect(() => {
    setPositions(initialPositions);
  }, [initialPositions]);

  const handleResetLayout = () => {
    setPositions(initialPositions);
    setZoom(0.92);
    setPan({ x: 30, y: 30 });
  };

  const handleFitView = () => {
    setZoom(0.88);
    setPan({ x: 20, y: 20 });
  };

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!isFullscreen) {
      if (containerRef.current.requestFullscreen) containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  // SỬA LỖI SCROLL: Chỉ thu phóng khi bấm phím Ctrl/Cmd, cuộn chuột bình thường cho phép cuộn trang tự nhiên!
  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
      setZoom((prev) => Math.min(Math.max(prev * zoomFactor, 0.35), 2.5));
    }
  };

  const handleMouseDownCanvas = (e: React.MouseEvent) => {
    if (e.target !== containerRef.current && !(e.target as HTMLElement).classList.contains("bgsd-canvas__bg")) {
      return;
    }
    setIsPanning(true);
    panStartRef.current = { x: e.clientX, y: e.clientY };
    panInitialRef.current = { ...pan };
  };

  const handleStartDragNode = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const currentPos = positions[id] || { x: 0, y: 0 };
    setDraggingNode({
      id,
      startMouse: { x: e.clientX, y: e.clientY },
      startPos: { ...currentPos },
    });
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isPanning) {
        const dx = (e.clientX - panStartRef.current.x) / zoom;
        const dy = (e.clientY - panStartRef.current.y) / zoom;
        setPan({
          x: panInitialRef.current.x + dx,
          y: panInitialRef.current.y + dy,
        });
      } else if (draggingNode) {
        const dx = (e.clientX - draggingNode.startMouse.x) / zoom;
        const dy = (e.clientY - draggingNode.startMouse.y) / zoom;
        setPositions((prev) => ({
          ...prev,
          [draggingNode.id]: {
            x: Math.max(10, draggingNode.startPos.x + dx),
            y: Math.max(10, draggingNode.startPos.y + dy),
          },
        }));
      }
    };

    const handleMouseUp = () => {
      setIsPanning(false);
      setDraggingNode(null);
    };

    if (isPanning || draggingNode) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isPanning, draggingNode, zoom]);

  const drawBezier = (p1: Point, p2: Point) => {
    const gapX = p2.x - p1.x;
    const dx = gapX > 0 ? Math.min(gapX * 0.42, 40) : Math.max(Math.abs(gapX) * 0.42, 25);
    return `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y}, ${p2.x - dx} ${p2.y}, ${p2.x} ${p2.y}`;
  };

  const nodeInPos = positions["in"] || { x: 460, y: 100 };

  return (
    <div className={`bgsd-canvas-wrap ${showGrid ? "has-dot-grid" : ""}`}>
      {/* Controls Toolbar */}
      <div className="bgsd-canvas__toolbar">
        <button type="button" className="bgsd-tb-btn" onClick={() => setZoom((z) => Math.max(z - 0.12, 0.35))} title="Thu nhỏ">
          <Icon name="minus" size={14} />
        </button>
        <span className="bgsd-tb-zoom">{Math.round(zoom * 100)}%</span>
        <button type="button" className="bgsd-tb-btn" onClick={() => setZoom((z) => Math.min(z + 0.12, 2.5))} title="Phóng to">
          <Icon name="plus" size={14} />
        </button>
        <div className="bgsd-tb-divider" />
        <button type="button" className="bgsd-tb-btn bgsd-tb-btn--text" onClick={handleFitView} title="Thu vừa tầm mắt">
          <Icon name="maximize" size={13} /> Căn vừa
        </button>
        <button type="button" className="bgsd-tb-btn bgsd-tb-btn--text" onClick={handleResetLayout} title="Xếp lại sơ đồ">
          <Icon name="rotate-ccw" size={13} /> Sắp xếp lại
        </button>
        <div className="bgsd-tb-divider" />
        <button
          type="button"
          className={`bgsd-tb-btn ${showGrid ? "is-active" : ""}`}
          onClick={() => setShowGrid((g) => !g)}
          title="Bật/Tắt lưới chấm"
        >
          <Icon name="grid" size={14} />
        </button>
        <button
          type="button"
          className="bgsd-tb-btn"
          onClick={handleToggleFullscreen}
          title="Toàn màn hình"
        >
          <Icon name="external-link" size={14} />
        </button>
      </div>

      {/* Main Canvas */}
      <div
        ref={containerRef}
        className={`bgsd-canvas ${isPanning ? "is-panning" : ""}`}
        onWheel={handleWheel}
        onMouseDown={handleMouseDownCanvas}
      >
        <div
          className="bgsd-canvas__viewport bgsd-canvas__bg"
          style={{
            transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
            transformOrigin: "0 0",
          }}
        >
          {/* SVG Connectors */}
          <svg className="bgsd-canvas__svg">
            {sd.nhanh.map((n) => {
              const c = mau(n.mau);
              const isSelected = chon === n.lsx_id;
              const strokeWidth = isSelected ? 3.2 : 2;
              const opacity = chon !== null && !isSelected && chon !== "in" ? 0.25 : 0.85;

              const lines: React.ReactNode[] = [];

              let prevPt: Point = positions[`hdr_left_${n.lsx_id}`]
                ? { x: positions[`hdr_left_${n.lsx_id}`].x + BRANCH_HDR_W, y: positions[`hdr_left_${n.lsx_id}`].y + 24 }
                : { x: 50, y: 50 };

              n.truoc_in.forEach((node) => {
                const nodeP = positions[`node_${node.step_key}`];
                if (nodeP) {
                  const currPt: Point = { x: nodeP.x, y: nodeP.y + CARD_NODE_H / 2 };
                  const pathD = drawBezier(prevPt, currPt);
                  lines.push(
                    <g key={`group_t_${node.step_key}`}>
                      <path d={pathD} stroke={c} strokeWidth={strokeWidth} strokeOpacity={opacity} fill="none" />
                      <path
                        d={pathD}
                        className="bgsd-flow-line"
                        stroke="#ffffff"
                        strokeWidth={strokeWidth - 0.5}
                        strokeDasharray="6,8"
                        fill="none"
                      />
                    </g>
                  );
                  prevPt = { x: nodeP.x + CARD_NODE_W, y: nodeP.y + CARD_NODE_H / 2 };
                }
              });

              const inPtLeft: Point = { x: nodeInPos.x, y: nodeInPos.y + 24 + n.mau * 14 };
              const pathToIn = drawBezier(prevPt, inPtLeft);
              lines.push(
                <g key={`group_to_in_${n.lsx_id}`}>
                  <path d={pathToIn} stroke={c} strokeWidth={strokeWidth + 0.5} strokeOpacity={opacity} fill="none" />
                  <path
                    d={pathToIn}
                    className="bgsd-flow-line"
                    stroke="#ffffff"
                    strokeWidth={strokeWidth - 0.5}
                    strokeDasharray="6,8"
                    fill="none"
                  />
                  <circle cx={inPtLeft.x} cy={inPtLeft.y} r={4} fill={c} />
                </g>
              );

              let prevPtSau: Point = { x: nodeInPos.x + CARD_IN_W, y: nodeInPos.y + 24 + n.mau * 14 };

              n.sau_in.forEach((node) => {
                const nodeP = positions[`node_${node.step_key}`];
                if (nodeP) {
                  const currPt: Point = { x: nodeP.x, y: nodeP.y + CARD_NODE_H / 2 };
                  const pathD = drawBezier(prevPtSau, currPt);

                  lines.push(
                    <g key={`group_s_${node.step_key}`}>
                      <path d={pathD} stroke={c} strokeWidth={strokeWidth} strokeOpacity={opacity} fill="none" />
                      <path
                        d={pathD}
                        className="bgsd-flow-line"
                        stroke="#ffffff"
                        strokeWidth={strokeWidth - 0.5}
                        strokeDasharray="6,8"
                        fill="none"
                      />
                    </g>
                  );
                  prevPtSau = { x: nodeP.x + CARD_NODE_W, y: nodeP.y + CARD_NODE_H / 2 };

                  node.phu_thuoc_step_keys.forEach((pk) => {
                    const ngoaiP = positions[`ngoai_${pk}`];
                    if (ngoaiP) {
                      lines.push(
                        <path
                          key={`line_ngoai_${pk}_${node.step_key}`}
                          d={drawBezier({ x: ngoaiP.x + CARD_NODE_W, y: ngoaiP.y + CARD_NODE_H / 2 }, currPt)}
                          stroke="#64748b"
                          strokeWidth={1.8}
                          strokeDasharray="4,4"
                          fill="none"
                        />
                      );
                    }
                  });
                }
              });

              const hdrRightP = positions[`hdr_right_${n.lsx_id}`];
              if (hdrRightP) {
                const pathD = drawBezier(prevPtSau, { x: hdrRightP.x, y: hdrRightP.y + 18 });
                lines.push(
                  <path
                    key={`line_hdr_r_${n.lsx_id}`}
                    d={pathD}
                    stroke={c}
                    strokeWidth={strokeWidth}
                    strokeOpacity={opacity * 0.75}
                    strokeDasharray="4,4"
                    fill="none"
                  />
                );
              }

              return <g key={`group_${n.lsx_id}`}>{lines}</g>;
            })}
          </svg>

          {/* Node IN CHUNG TỜ */}
          <div
            className={`bgsd-card-in ${chon === "in" ? "is-chon" : ""}`}
            style={{
              left: nodeInPos.x,
              top: nodeInPos.y,
              width: CARD_IN_W,
              height: CARD_IN_H,
            }}
            onClick={() => onChon("in")}
            onMouseDown={(e) => handleStartDragNode("in", e)}
          >
            <span className="bgsd-port bgsd-port--left" />
            <span className="bgsd-port bgsd-port--right" />

            <div className="bgsd-card-in__head">
              <span className="bgsd-card-in__ma">{sd.bai_ghep.ma}</span>
              <span className="bgsd-card-in__pill">🖨️ MÁY IN</span>
            </div>
            <div className="bgsd-card-in__title">IN CHUNG TỜ</div>
            <div className="bgsd-card-in__foot">
              <span className="bgsd-card-in__may">
                <Icon name="cpu" size={12} /> {sd.bai_ghep.may_ten ?? "chưa chọn máy"}
              </span>
              <span className="bgsd-card-in__badge">
                {num(sd.bai_ghep.tong_to)} tờ cấp
              </span>
            </div>
          </div>

          {/* Render Branches */}
          {sd.nhanh.map((n) => {
            const c = mau(n.mau);
            const isSelected = chon === n.lsx_id;

            const hdrLeftP = positions[`hdr_left_${n.lsx_id}`] || { x: 30, y: 60 };
            const hdrRightP = positions[`hdr_right_${n.lsx_id}`];

            return (
              <React.Fragment key={n.thanh_vien_id}>
                {/* Header LSX bên trái - CHỈ CHỌN NHÁNH, KHÔNG CHUYỂN TRANG */}
                <div
                  className={`bgsd-card-branch ${isSelected ? "is-chon" : ""}`}
                  style={{
                    left: hdrLeftP.x,
                    top: hdrLeftP.y,
                    borderColor: c,
                    width: BRANCH_HDR_W,
                  }}
                  onClick={() => onChon(n.lsx_id)}
                  onMouseDown={(e) => handleStartDragNode(`hdr_left_${n.lsx_id}`, e)}
                >
                  <div className="bgsd-card-branch__head">
                    <span className="bgsd__cham" style={{ background: c }} />
                    <span className="khsx__code">{n.lsx_ma}</span>
                  </div>
                  <div className="bgsd-card-branch__cust">{n.customer_name ?? "Khách lẻ"}</div>
                  <div className="bgsd-card-branch__tags">
                    {n.is_rush && <ChipGap />}
                    {n.han_hoan_thanh_sx && (
                      <small className={`bgsd-card-branch__han ${classHan(n.han_hoan_thanh_sx)}`}>
                        hạn {ngay(n.han_hoan_thanh_sx)}
                      </small>
                    )}
                  </div>
                </div>

                {/* Các bước Trước In - CHỈ CHỌN NHÁNH ĐỂ XEM PANEL DƯỚI, KHÔNG NHẢY TRANG */}
                {n.truoc_in.map((node) => {
                  const p = positions[`node_${node.step_key}`] || { x: 0, y: 0 };
                  const meta = LSX_LOAI_BUOC_META[node.loai_buoc] ?? { label: node.loai_buoc };

                  return (
                    <button
                      type="button"
                      key={node.step_key}
                      className={`bgsd-node bgsd-card-node ${isSelected ? "is-nhanh-chon" : ""}`}
                      style={{
                        left: p.x,
                        top: p.y,
                        width: CARD_NODE_W,
                        height: CARD_NODE_H,
                        ["--mau-nhanh" as string]: c,
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        onChon(n.lsx_id);
                      }}
                      onMouseDown={(e) => handleStartDragNode(`node_${node.step_key}`, e)}
                    >
                      <div className="bgsd-card-node__icon">
                        <Icon name={getStepIcon(node.loai_buoc)} size={14} />
                      </div>
                      <div className="bgsd-card-node__body">
                        <span className="bgsd-node__ten">{node.ten}</span>
                        <span className="bgsd-node__phu">
                          {node.loai_buoc === "thue_ngoai"
                            ? node.nha_cung_cap || "chưa có nhà gia công"
                            : node.may_ten || node.to_ten || meta.label}
                          {node.tong_phut > 0 ? ` · ${phut(node.tong_phut)}` : ""}
                        </span>
                      </div>
                    </button>
                  );
                })}

                {/* Các bước Sau In - CHỈ CHỌN NHÁNH ĐỂ XEM PANEL DƯỚI, KHÔNG NHẢY TRANG */}
                {n.sau_in.map((node) => {
                  const p = positions[`node_${node.step_key}`] || { x: 0, y: 0 };
                  const meta = LSX_LOAI_BUOC_META[node.loai_buoc] ?? { label: node.loai_buoc };

                  return (
                    <React.Fragment key={node.step_key}>
                      {/* Node ngoại lệ */}
                      {node.phu_thuoc_step_keys.map((pk) => {
                        const o = ngoaiMap.get(pk);
                        const np = positions[`ngoai_${pk}`];
                        if (!o || !np) return null;
                        return (
                          <div
                            key={pk}
                            className="bgsd-node bgsd-node--ngoai bgsd-card-node"
                            style={{
                              left: np.x,
                              top: np.y,
                              width: CARD_NODE_W,
                              height: CARD_NODE_H,
                            }}
                            onMouseDown={(e) => handleStartDragNode(`ngoai_${pk}`, e)}
                          >
                            <div className="bgsd-card-node__icon">
                              <Icon name="link" size={14} />
                            </div>
                            <div className="bgsd-card-node__body">
                              <span className="bgsd-node__ten">{o.ten}</span>
                              <span className="bgsd-node__phu">{o.lsx_ma ?? "LSX khác"}</span>
                            </div>
                          </div>
                        );
                      })}

                      <button
                        type="button"
                        className={`bgsd-node bgsd-card-node ${isSelected ? "is-nhanh-chon" : ""}`}
                        style={{
                          left: p.x,
                          top: p.y,
                          width: CARD_NODE_W,
                          height: CARD_NODE_H,
                          ["--mau-nhanh" as string]: c,
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onChon(n.lsx_id);
                        }}
                        onMouseDown={(e) => handleStartDragNode(`node_${node.step_key}`, e)}
                      >
                        <div className="bgsd-card-node__icon">
                          <Icon name={getStepIcon(node.loai_buoc)} size={14} />
                        </div>
                        <div className="bgsd-card-node__body">
                          <span className="bgsd-node__ten">{node.ten}</span>
                          <span className="bgsd-node__phu">
                            {node.loai_buoc === "thue_ngoai"
                              ? node.nha_cung_cap || "chưa có nhà gia công"
                              : node.may_ten || node.to_ten || meta.label}
                            {node.tong_phut > 0 ? ` · ${phut(node.tong_phut)}` : ""}
                          </span>
                        </div>
                      </button>
                    </React.Fragment>
                  );
                })}

                {/* Header Kết quả Dư/Thiếu */}
                {hdrRightP && (
                  <div
                    className="bgsd-card-branch bgsd-card-branch--right"
                    style={{
                      left: hdrRightP.x,
                      top: hdrRightP.y,
                    }}
                    onMouseDown={(e) => handleStartDragNode(`hdr_right_${n.lsx_id}`, e)}
                  >
                    {n.du > 0 ? (
                      <span className="bgsd-pill-status is-surplus">
                        <Icon name="check-circle" size={12} /> dư +{num(n.du)}
                      </span>
                    ) : (
                      <span className="bgsd-pill-status is-exact">
                        vừa đủ
                      </span>
                    )}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}
