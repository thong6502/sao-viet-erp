import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LsxPhuThuocOption } from "../api/client";
import type { RefRow } from "../pages/LsxRoutingTable";
import { type EditRow, tenBuoc } from "../pages/lsxBuoc";
import { DagNodeCard } from "./DagNodeCard";
import { Icon } from "./Icons";
import "../pages/dag-routing.css";

export interface DagRoutingCanvasProps {
  rows: EditRow[];
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: LsxPhuThuocOption[];
  /** Lệnh đang ghép chung tờ → node bước in hiện dạng CHUNG (viền đứt + mã bài). */
  baiGhep: import("../api/client").LsxBaiGhep | null;
  canUpdate: boolean;
  onUpdateRows: (rows: EditRow[]) => void;
  /** `tab` chỉ dùng cho deep-link từ badge trên node (vd sổ giao–nhận). */
  onOpenDrawer: (index: number, tab?: "giao_nhan") => void;
  /** `afterKey` = chèn ngay sau node ĐANG CHỌN (nếu có) để `thu_tu` đúng liền — số lượng + số hiệu
   *  bám `thu_tu` nên đây là chỗ quyết định vị trí, không phải cạnh phụ thuộc. Không chọn node nào
   *  thì thêm ở cuối. */
  onAddStep: (afterKey?: string) => void;
}

export interface Point {
  x: number;
  y: number;
}

const NODE_WIDTH = 240;
const NODE_HEIGHT = 144;
const GAP_X = 56;
const GAP_Y = 160;
const START_X = 50;
const START_Y = 50;
const GRAPH_PADDING = 32;
/** Chừa mép khi thu vừa khung để node ngoài cùng không dính sát viền viewport. */
const VIEW_PADDING = 24;
const MIN_VIEWPORT_HEIGHT = 320;
const MAX_VIEWPORT_HEIGHT = 580;

/** Tự động tính toán vị trí phân tầng ( Sugiyama / Layered Layout ).
 *
 * `ghostKeys` = bước của LSX KHÁC trong cùng đơn hàng đang được phụ thuộc. Chúng luôn là nguồn
 * (level 0) vì canvas không sửa được routing của lệnh khác — nhờ vậy cột trái đọc ra ngay
 * "cái gì từ lệnh khác chảy vào lệnh này".
 */
function computeAutoLayout(rows: EditRow[], ghostKeys: string[] = []): Record<string, Point> {
  const rowMap = new Map<string, EditRow>();
  rows.forEach((r) => rowMap.set(r.key, r));
  const ghosts = new Set(ghostKeys);

  // Tính level (độ sâu) của từng bước
  const levels = new Map<string, number>();
  ghosts.forEach((key) => levels.set(key, 0));

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
      if (rowMap.has(predKey) || ghosts.has(predKey)) {
        maxPredLevel = Math.max(maxPredLevel, getLevel(predKey, new Set(visited)));
      }
    }

    const lvl = maxPredLevel + 1;
    levels.set(key, lvl);
    return lvl;
  }

  rows.forEach((r) => getLevel(r.key));

  // Nhóm node theo level — ghost xếp trước để nằm trên cùng cột 0
  const levelGroups = new Map<number, string[]>();
  [...ghostKeys, ...rows.map((r) => r.key)].forEach((key) => {
    const lvl = levels.get(key) ?? 0;
    if (!levelGroups.has(lvl)) levelGroups.set(lvl, []);
    levelGroups.get(lvl)!.push(key);
  });

  const positions: Record<string, Point> = {};

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

/** Một tầng thì canvas gọn; nhiều nhánh mới tăng chiều cao, tối đa bằng chiều cao cũ. */
export function computeViewportHeight(rows: EditRow[], ghostKeys: string[] = []): number {
  if (!rows.length) return MIN_VIEWPORT_HEIGHT;
  const auto = computeAutoLayout(rows, ghostKeys);
  const keys = [...rows.map((row) => row.key), ...ghostKeys];
  const maxY = Math.max(...keys.map((key) => auto[key]?.y ?? START_Y));
  return Math.max(
    MIN_VIEWPORT_HEIGHT,
    Math.min(MAX_VIEWPORT_HEIGHT, maxY + NODE_HEIGHT + GRAPH_PADDING),
  );
}

/** Chiều rộng nội dung thật để viewport sinh thanh cuộn tới node ngoài cùng. */
export function computeCanvasWidth(
  positions: Record<string, Point>,
  keys: string[],
): number {
  if (!keys.length) return 0;
  const maxX = Math.max(...keys.map((key) => positions[key]?.x ?? START_X));
  return maxX + NODE_WIDTH + GRAPH_PADDING;
}

export function computeCanvasHeight(
  positions: Record<string, Point>,
  keys: string[],
): number {
  if (!keys.length) return MIN_VIEWPORT_HEIGHT;
  const maxY = Math.max(...keys.map((key) => positions[key]?.y ?? START_Y));
  return maxY + NODE_HEIGHT + GRAPH_PADDING;
}

/** Tỉ lệ thu để TRỌN sơ đồ (w×h) lọt vào khung nhìn.
 *
 * Chuỗi tuyến tính 5 bước đã rộng ~1.500px trong khi khung chỉ ~1.150px, nên mặc định phải thu
 * lại — không thì bước cuối nằm ngoài tầm mắt và người dùng phải mò thanh cuộn mới biết còn gì.
 * Không phóng quá 100% (chữ vỡ) và không thu dưới 35% (hết đọc nổi).
 *
 * Ở màn hẹp (≤768px) sàn nâng lên 55%: `transform: scale()` co luôn VÙNG CHẠM, nên ở 35% hai nút
 * `.dag-node__btn` (khai 44px) chỉ còn 15,4px trên màn — dưới cả mức AA 24px của WCAG 2.5.8.
 * 44 × 0,55 = 24,2px, cộng phần nới của §77 (`styles/responsive.css`) là qua ngưỡng. Đây CHỈ là
 * sàn của phép TỰ căn; nút "−" vẫn cho người dùng chủ động xuống tới 0,2 để nhìn toàn cảnh.
 */
const SAN_TU_CAN_HEP = 0.55;
const MAN_HEP_PX = 768;

function tinhZoomVua(vp: HTMLDivElement, w: number, h: number): number {
  if (w <= 0 || h <= 0) return 1;
  const san = typeof window !== "undefined" && window.innerWidth <= MAN_HEP_PX ? SAN_TU_CAN_HEP : 0.35;
  const vua = Math.min(1, (vp.clientWidth - VIEW_PADDING) / w, (vp.clientHeight - VIEW_PADDING) / h);
  return Math.max(san, Math.floor(vua * 100) / 100);
}

/** Đặt chỗ cho một node ngoài LSX ở cột trái, đẩy cả sơ đồ sang phải nếu cột đó đang bị chiếm. */
export function themViTriGhost(
  prev: Record<string, Point>,
  key: string,
  ghostIndex: number,
  rowKeys: string[],
): Record<string, Point> {
  const next = { ...prev };
  const canTrai = START_X + NODE_WIDTH + GAP_X;
  const daCo = rowKeys.filter((k) => next[k]);
  if (daCo.length) {
    const minX = Math.min(...daCo.map((k) => next[k].x));
    if (minX < canTrai) {
      const delta = canTrai - minX;
      daCo.forEach((k) => {
        next[k] = { x: next[k].x + delta, y: next[k].y };
      });
    }
  }
  next[key] = { x: START_X, y: START_Y + ghostIndex * GAP_Y };
  return next;
}

/** Tiền nhiệm KHÔNG thuộc LSX đang mở = bước của lệnh khác trong cùng đơn hàng. */
export function ghostKeysCua(rows: EditRow[]): string[] {
  const noiBo = new Set(rows.map((r) => r.key));
  const out: string[] = [];
  rows.forEach((r) =>
    (r.phu_thuoc_step_keys || []).forEach((key) => {
      if (!noiBo.has(key) && !out.includes(key)) out.push(key);
    }),
  );
  return out;
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

/** Node chỉ-đọc cho bước thuộc LSX KHÁC trong cùng đơn hàng: chỉ có cổng Ra, không sửa/xoá. */
function DagGhostNodeCard({
  stepKey,
  option,
  position,
  onNodeMouseDown,
  onPortMouseDown,
  onMouseEnter,
  onMouseLeave,
}: {
  stepKey: string;
  option: LsxPhuThuocOption | undefined;
  position: Point;
  onNodeMouseDown: (e: React.MouseEvent, key: string) => void;
  onPortMouseDown: (e: React.MouseEvent, key: string, portType: "in" | "out") => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}) {
  return (
    <div
      className="dag-node dag-node--ngoai"
      style={{ left: `${position.x}px`, top: `${position.y}px` }}
      onMouseDown={(e) => onNodeMouseDown(e, stepKey)}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      title="Bước của lệnh sản xuất khác — sửa tại lệnh đó"
    >
      <div className="dag-node__head dag-node__head--ngoai">
        <span className="dag-node__lsx">{option?.lsx_ma ?? "LSX khác"}</span>
        <span className="dag-node__title" title={option?.ten_buoc ?? stepKey}>
          {option?.ten_buoc ?? "Bước ngoài lệnh"}
        </span>
      </div>
      <div className="dag-node__body">
        <div className="dag-node__row">
          <span className="dag-node__badge">
            <Icon name="workflow" size={11} />
            {option ? `Bước #${option.thu_tu * 10}` : stepKey}
          </span>
          {option?.nhom && <span className="dag-node__badge">{option.nhom}</span>}
        </div>
        <p className="dag-node__ngoai-hint">
          Lệnh này chỉ chạy sau khi bước trên của lệnh kia xong.
        </p>
      </div>
      <div
        className="dag-port dag-port--out"
        title="Kéo dây từ đây sang cổng Vào của bước trong lệnh này"
        onMouseDown={(e) => {
          e.stopPropagation();
          onPortMouseDown(e, stepKey, "out");
        }}
      />
    </div>
  );
}

export function DagRoutingCanvas({
  rows,
  congDoanRefs,
  toRefs,
  mayRefs,
  vatTuRefs: _vatTuRefs,
  phuThuocRefs,
  baiGhep,
  canUpdate,
  onUpdateRows,
  onOpenDrawer,
  onAddStep,
}: DagRoutingCanvasProps) {
  // State vị trí các node trên canvas
  const [positions, setPositions] = useState<Record<string, Point>>(() => computeAutoLayout(rows));
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  // State Zoom & Pan canvas. Pan = CUỘN THẬT của viewport, không phải transform: kéo nền bằng
  // transform thì không có biên, đẩy quá tay là node ra ngoài khung và không còn thanh cuộn nào
  // kéo về (hàng node bị cụt mất header).
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });

  // State kéo node
  const [draggingKey, setDraggingKey] = useState<string | null>(null);
  const dragStartRef = useRef<Point>({ x: 0, y: 0 });
  const nodeStartPosRef = useRef<Point>({ x: 0, y: 0 });

  // State kéo nối dây (Creating Wire)
  const [connectingSourceKey, setConnectingSourceKey] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState<Point>({ x: 0, y: 0 });

  // State hover highlight dây nối
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [hoveredWireId, setHoveredWireId] = useState<string | null>(null);

  // State thu gọn từng nhóm LSX trong Sidebar ngăn trái
  const [collapsedGroups, setCollapsedGroups] = useState<Record<number, boolean>>({});

  // Bước LSX khác đang được kéo dây nhưng chưa nối xong — giữ tạm để có điểm neo vẽ dây nháp.
  const [ghostDangKeo, setGhostDangKeo] = useState<string | null>(null);
  const [railMo, setRailMo] = useState(false);

  const viewportRef = useRef<HTMLDivElement>(null);
  // Người dùng đã tự chỉnh tầm nhìn (zoom / kéo nền / kéo node) thì thôi tự thu vừa khung —
  // giật tầm nhìn dưới tay người đang thao tác còn khó chịu hơn là thấy thiếu một bước.
  const daTuChinhRef = useRef(false);
  const ghostKeys = useMemo(() => {
    const ds = ghostKeysCua(rows);
    if (ghostDangKeo && !ds.includes(ghostDangKeo) && !rows.some((r) => r.key === ghostDangKeo)) {
      ds.push(ghostDangKeo);
    }
    return ds;
  }, [rows, ghostDangKeo]);
  const allKeys = useMemo(() => [...rows.map((r) => r.key), ...ghostKeys], [rows, ghostKeys]);
  const optionByKey = useMemo(
    () => new Map(phuThuocRefs.map((o) => [o.step_key, o] as const)),
    [phuThuocRefs],
  );
  /** Ngăn trái: mọi bước của LSX KHÁC trong đơn, gom theo lệnh — nguồn để kéo dây thẳng vào canvas. */
  const railGroups = useMemo(() => {
    const noiBo = new Set(rows.map((r) => r.key));
    const groups = new Map<number, { ma: string; nhom: string | null; items: LsxPhuThuocOption[] }>();
    phuThuocRefs
      .filter((o) => !noiBo.has(o.step_key))
      .forEach((o) => {
        const g = groups.get(o.lsx_id) ?? { ma: o.lsx_ma, nhom: o.nhom, items: [] };
        g.items.push(o);
        groups.set(o.lsx_id, g);
      });
    return [...groups.entries()].map(([lsxId, g]) => ({ lsxId, ...g }));
  }, [phuThuocRefs, rows]);
  const daNoiKeys = useMemo(
    () => new Set(rows.flatMap((r) => r.phu_thuoc_step_keys || [])),
    [rows],
  );

  const layoutSignature = rows
    .map((row) => `${row.key}:${(row.phu_thuoc_step_keys || []).join(",")}`)
    .join("|");
  const viewportHeight = useMemo(
    () => computeViewportHeight(rows, ghostKeys),
    [layoutSignature, ghostKeys],
  );
  const canvasWidth = useMemo(() => computeCanvasWidth(positions, allKeys), [positions, allKeys]);
  const canvasHeight = useMemo(() => computeCanvasHeight(positions, allKeys), [positions, allKeys]);

  // Cập nhật vị trí tự động cho các bước mới thêm chưa có vị trí
  useEffect(() => {
    setPositions((prev) => {
      const auto = computeAutoLayout(rows, ghostKeys);
      let updated = { ...prev };
      let changed = false;
      rows.forEach((r) => {
        if (!updated[r.key]) {
          updated[r.key] = auto[r.key] || { x: START_X, y: START_Y };
          changed = true;
        }
      });
      ghostKeys.forEach((key, idx) => {
        if (!updated[key]) {
          updated = themViTriGhost(updated, key, idx, rows.map((r) => r.key));
          changed = true;
        }
      });
      return changed ? updated : prev;
    });
  }, [rows, ghostKeys]);

  /** Thu cả sơ đồ vào vừa khung nhìn — nhìn một phát ra trọn chuỗi, khỏi cuộn ngang đoán mò. */
  const thuVuaKhung = useCallback(
    (viTri: Record<string, Point> = positions) => {
      const vp = viewportRef.current;
      if (!vp) return;
      setZoom(
        tinhZoomVua(vp, computeCanvasWidth(viTri, allKeys), computeCanvasHeight(viTri, allKeys)),
      );
      vp.scrollLeft = 0;
      vp.scrollTop = 0;
    },
    [positions, allKeys],
  );

  // Mở sơ đồ / thêm–bớt bước: tự thu vừa khung, trừ khi người dùng đã tự chỉnh tầm nhìn.
  useEffect(() => {
    if (daTuChinhRef.current) return;
    thuVuaKhung();
  }, [thuVuaKhung]);

  // Nút Sắp xếp tự động (Auto Layout)
  const handleAutoLayout = useCallback(() => {
    const auto = computeAutoLayout(rows, ghostKeys);
    setPositions(auto);
    // Xếp lại là trả tầm nhìn về mặc định luôn: xếp gọn mà vẫn phải cuộn tìm thì xếp làm gì.
    daTuChinhRef.current = false;
    thuVuaKhung(auto);
  }, [rows, ghostKeys, thuVuaKhung]);

  // Tính toán đường cong Bezier giữa 2 cổng kết nối
  // Độ cong bám khoảng cách thật: ép tối thiểu 50px trong khi hai cột chỉ cách 56px thì dây
  // phình ra rồi thắt lại thành chữ S — nhìn như dây điện. Chặn trên để dây đi xa khỏi vòng quá.
  const calculateBezier = useCallback(
    (p1: Point, p2: Point) => {
      const dx = Math.min(90, Math.max(24, Math.abs(p2.x - p1.x) / 2));
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
    const vp = viewportRef.current;
    setIsPanning(true);
    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      scrollLeft: vp?.scrollLeft ?? 0,
      scrollTop: vp?.scrollTop ?? 0,
    };
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
        const vp = viewportRef.current;
        if (vp) {
          daTuChinhRef.current = true;
          vp.scrollLeft = panStartRef.current.scrollLeft - (e.clientX - panStartRef.current.x);
          vp.scrollTop = panStartRef.current.scrollTop - (e.clientY - panStartRef.current.y);
        }
        return;
      }

      // Khi đang Drag 1 Node
      if (draggingKey) {
        daTuChinhRef.current = true;
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

      // Khi đang Kéo dây nối. PHẢI cộng scrollLeft/scrollTop: canvas cuộn được nên góc trái
      // viewport không còn là gốc toạ độ — thiếu nó là dây nháp bay lệch khỏi con trỏ đúng bằng
      // quãng đã cuộn.
      if (connectingSourceKey && viewportRef.current) {
        const vp = viewportRef.current;
        const rect = vp.getBoundingClientRect();
        const canvasX = (e.clientX - rect.left + vp.scrollLeft) / zoom;
        const canvasY = (e.clientY - rect.top + vp.scrollTop) / zoom;
        setMousePos({ x: canvasX, y: canvasY });
      }
    },
    [isPanning, draggingKey, connectingSourceKey, zoom]
  );

  // Thả chuột
  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
    setDraggingKey(null);
    if (connectingSourceKey) {
      setConnectingSourceKey(null);
    }
    setGhostDangKeo(null);
  }, [connectingSourceKey]);

  // Kéo dây bắt đầu từ NGĂN TRÁI (ngoài viewport) nên phải nghe mouseup ở cấp window, không thì
  // thả tay ngoài canvas là dây nháp treo lại.
  useEffect(() => {
    if (!connectingSourceKey && !isPanning && !draggingKey) return;
    const huy = () => {
      setIsPanning(false);
      setDraggingKey(null);
      setConnectingSourceKey(null);
      setGhostDangKeo(null);
    };
    window.addEventListener("mouseup", huy);
    return () => window.removeEventListener("mouseup", huy);
  }, [connectingSourceKey, isPanning, draggingKey]);

  // Bắt đầu kéo dây từ Cổng Out
  const handlePortMouseDown = (_e: React.MouseEvent, key: string, portType: "in" | "out") => {
    if (!canUpdate || portType !== "out") return;
    setConnectingSourceKey(key);
    const startPos = getPortOutPos(key);
    setMousePos(startPos);
  };

  /** Bấm giữ một bước ở ngăn trái = dựng node bóng mờ ở cột trái rồi kéo dây từ cổng Ra của nó. */
  const handleRailMouseDown = (e: React.MouseEvent, option: LsxPhuThuocOption) => {
    e.preventDefault();
    if (!canUpdate) return;
    const key = option.step_key;
    let viTri: Point = positions[key] ?? { x: START_X, y: START_Y };
    if (!positions[key]) {
      const rowKeys = rows.map((r) => r.key);
      const tiep = themViTriGhost(positions, key, ghostKeys.length, rowKeys);
      viTri = tiep[key];
      setPositions(tiep);
    }
    setGhostDangKeo(key);
    setConnectingSourceKey(key);
    setMousePos({ x: viTri.x + NODE_WIDTH, y: viTri.y + 60 });
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

          {canUpdate && (() => {
            // Thêm bước = CHÈN SAU 1 bước đang chọn (thu_tu liền ngay). Không còn nút "thêm ở
            // cuối" chung chung: bấm chọn 1 node rồi mới hiện "Chèn sau: <bước>". Danh sách RỖNG
            // là ngoại lệ duy nhất còn nút thêm-bước-đầu — chưa có bước nào để chèn sau. Nhãn dùng
            // tenBuoc() để bám tên công đoạn đang gắn, không trơ literal "Công đoạn".
            const nodeChon = selectedKey ? rows.find((r) => r.key === selectedKey) : null;
            if (nodeChon) {
              const tenChon = tenBuoc(nodeChon, congDoanRefs).trim() || "bước đã chọn";
              const tenNgan = tenChon.length > 18 ? `${tenChon.slice(0, 17)}…` : tenChon;
              return (
                <button
                  type="button"
                  className="dag-btn-icon"
                  style={{ background: "#c25e38", color: "#fff", borderColor: "#c25e38" }}
                  onClick={() => onAddStep(selectedKey ?? undefined)}
                  title={`Chèn 1 công đoạn ngay sau "${tenChon}"`}
                >
                  <Icon name="plus" size={14} /> Chèn sau: {tenNgan}
                </button>
              );
            }
            if (rows.length === 0) {
              return (
                <button
                  type="button"
                  className="dag-btn-icon"
                  style={{ background: "#c25e38", color: "#fff", borderColor: "#c25e38" }}
                  onClick={() => onAddStep(undefined)}
                  title="Thêm công đoạn đầu tiên cho lệnh"
                >
                  <Icon name="plus" size={14} /> Thêm công đoạn
                </button>
              );
            }
            return (
              <span className="dag-toolbar__hint">
                Bấm chọn 1 bước để chèn công đoạn ngay sau nó
              </span>
            );
          })()}
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
            {ghostKeys.length > 0 && (
              <span className="dag-legend__item">
                <span className="dag-legend__dot dag-legend__dot--ngoai" /> Bước LSX khác
              </span>
            )}
          </div>

          <button
            type="button"
            className="dag-btn-icon"
            onClick={() => {
              daTuChinhRef.current = false;
              thuVuaKhung();
            }}
            title="Thu cả sơ đồ vừa khung nhìn"
          >
            <Icon name="maximize" size={13} /> Vừa khung
          </button>
          <div className="dag-zoom">
            <button
              type="button"
              className="dag-zoom__btn"
              onClick={() => {
                daTuChinhRef.current = true;
                setZoom((z) => Math.max(0.2, Math.round((z - 0.1) * 100) / 100));
              }}
              title="Thu nhỏ"
            >
              <Icon name="minus" size={13} />
            </button>
            <span className="dag-zoom__val">{Math.round(zoom * 100)}%</span>
            <button
              type="button"
              className="dag-zoom__btn"
              onClick={() => {
                daTuChinhRef.current = true;
                setZoom((z) => Math.min(1.8, Math.round((z + 0.1) * 100) / 100));
              }}
              title="Phóng to"
            >
              <Icon name="plus" size={13} />
            </button>
          </div>
        </div>
      </div>

      <div className="dag-main" style={{ height: viewportHeight }}>
        {/* Ngăn trái: bước của LSX khác trong cùng đơn hàng — kéo thẳng vào canvas, khỏi mở drawer */}
        {railGroups.length > 0 && (
          <aside className={`dag-rail ${railMo ? "" : "dag-rail--dong"}`}>
            <button
              type="button"
              className="dag-rail__head"
              onClick={() => setRailMo((v) => !v)}
              aria-expanded={railMo}
              title={railMo ? "Thu gọn ngăn" : "Mở ngăn bước LSX khác"}
            >
              <Icon name="workflow" size={13} />
              {railMo && <span className="dag-rail__title">Bước LSX khác</span>}
              <span className="dag-rail__count">
                {railGroups.reduce((s, g) => s + g.items.length, 0)}
              </span>
              {railMo && <Icon name="chevron" size={13} />}
            </button>

            {railMo && (
              <div className="dag-rail__body">
                <p className="dag-rail__hint">
                  {canUpdate
                    ? "Bấm giữ một bước rồi kéo sang cổng Vào (chấm xanh) của bước trong lệnh này."
                    : "Chỉ xem — không có quyền sửa công đoạn."}
                </p>
                {railGroups.map((g) => {
                  const isCollapsed = Boolean(collapsedGroups[g.lsxId]);
                  return (
                    <div className="dag-rail__group" key={g.lsxId}>
                      <div
                        className="dag-rail__group-head"
                        onClick={() =>
                          setCollapsedGroups((prev) => ({ ...prev, [g.lsxId]: !prev[g.lsxId] }))
                        }
                        title={isCollapsed ? "Bấm để mở danh sách bước" : "Bấm để thu gọn"}
                      >
                        <span className="dag-rail__lsx" title={g.ma}>{g.ma}</span>
                        {g.nhom && <span className="dag-rail__nhom" title={g.nhom}>{g.nhom}</span>}
                        <span className="dag-rail__group-count">({g.items.length})</span>
                        <span
                          className={`dag-rail__group-chevron ${isCollapsed ? "is-collapsed" : ""}`}
                        >
                          <Icon name="chevron" size={11} />
                        </span>
                      </div>
                      {!isCollapsed &&
                        g.items.map((o) => (
                          <div
                            key={o.step_key}
                            className={`dag-rail__item ${daNoiKeys.has(o.step_key) ? "is-noi" : ""} ${
                              canUpdate ? "" : "is-readonly"
                            }`}
                            onMouseDown={(e) => handleRailMouseDown(e, o)}
                            title={
                              canUpdate
                                ? `Kéo "${o.ten_buoc}" sang cổng Vào của bước cần chờ nó`
                                : o.ten_buoc
                            }
                          >
                            <span className="dag-rail__port" />
                            <span className="dag-rail__ten">{o.ten_buoc}</span>
                            {daNoiKeys.has(o.step_key) && (
                              <span className="dag-rail__da-noi" title="Đã nối vào lệnh này">
                                <Icon name="check" size={12} />
                              </span>
                            )}
                          </div>
                        ))}
                    </div>
                  );
                })}
              </div>
            )}
          </aside>
        )}

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
            // Nhân zoom vào chính hộp canvas: scale() không làm vùng cuộn to ra, phóng to mà
            // không nhân là node ngoài cùng nằm ngoài tầm cuộn.
            width: canvasWidth * zoom,
            minWidth: "100%",
            // Trước đây ép cao bằng cả viewport nên luôn tràn đúng bề dày thanh cuộn ngang →
            // đẻ ra một thanh cuộn dọc vô nghĩa. minHeight lo phần nền, height lo vùng cuộn.
            height: canvasHeight * zoom,
            minHeight: "100%",
            transform: `scale(${zoom})`,
            // `--dag-zoom` bơm tỉ lệ thu phóng ra CSS: `scale()` co MỌI thứ bên trong, kể cả vùng
            // chạm của `.dag-node__btn`, nên tầng CSS cần biết đang co bao nhiêu để nới bù
            // (xem §77 trong `styles/responsive.css`).
            ["--dag-zoom" as string]: String(zoom),
          } as React.CSSProperties}
        >
          {/* Lớp SVG vẽ Dây nối */}
          <svg className="dag-svg-layer">
            {/* Dây nối chính thức */}
            {wires.map((w) => {
              const isHighlighted =
                (hoveredKey && (w.sourceKey === hoveredKey || w.targetKey === hoveredKey)) ||
                hoveredWireId === w.id;
              const isAnyHovered = Boolean(hoveredKey || hoveredWireId);

              let wireClass = "dag-wire";
              if (isHighlighted) wireClass += " dag-wire--highlighted";
              else if (isAnyHovered) wireClass += " dag-wire--dimmed";

              return (
                <g
                  key={w.id}
                  onMouseEnter={() => setHoveredWireId(w.id)}
                  onMouseLeave={() => setHoveredWireId(null)}
                >
                  <path className={wireClass} d={w.path} />
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
              );
            })}

            {/* Dây nối nháp đang kéo (Draft wire) */}
            {connectingSourceKey && (
              <path
                className="dag-wire--draft"
                d={calculateBezier(getPortOutPos(connectingSourceKey), mousePos)}
              />
            )}
          </svg>

          {/* Node bóng mờ: bước của LSX khác đang được phụ thuộc — chỉ đọc, chỉ có cổng Ra */}
          {ghostKeys.map((key, idx) => (
            <DagGhostNodeCard
              key={key}
              stepKey={key}
              option={optionByKey.get(key)}
              position={positions[key] || { x: START_X, y: START_Y + idx * GAP_Y }}
              onNodeMouseDown={handleNodeMouseDown}
              onPortMouseDown={handlePortMouseDown}
              onMouseEnter={() => setHoveredKey(key)}
              onMouseLeave={() => setHoveredKey(null)}
            />
          ))}

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
                congDoanRefs={congDoanRefs}
                toRefs={toRefs}
                mayRefs={mayRefs}
                warnings={[]}
                maBaiGhep={baiGhep?.buoc_bi_de?.[r.key] ? baiGhep.ma : null}
                canUpdate={canUpdate}
                onMouseEnter={() => setHoveredKey(r.key)}
                onMouseLeave={() => setHoveredKey(null)}
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
    </div>
  );
}
