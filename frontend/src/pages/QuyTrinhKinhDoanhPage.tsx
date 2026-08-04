import { useState, useMemo, useRef } from "react";
import "./quy-trinh-kinh-doanh.css";

/** Quy trình kinh doanh — Bản đồ quy trình tương tác WOW cho khối bán hàng.
  * Hỗ trợ: Path tracing (hover tô sáng luồng), Flow Neon Pulse (hạt năng lượng chạy),
  * Multi-view mode (Swimlane vs Timeline), Drawer thông tin chi tiết. */

export type LaneKey = "kh" | "kd" | "sx" | "kho" | "gh";
export type NodeKind = "process" | "start" | "end" | "decision";

export interface FlowNode {
  id: string;
  label: string;
  sub?: string;
  lane: LaneKey;
  kind: NodeKind;
  cx: number;
  cy: number;
  /** Nav ID nếu bấm được; bỏ trống = phân hệ chưa có màn. */
  to?: string;
  role: string;
  desc: string;
}

export interface FlowEdge {
  from: string;
  to: string;
  d: string;
  label?: string;
  lx?: number;
  ly?: number;
}

const VIEW_W = 1280;
const VIEW_H = 650;
const HEAD_H = 40;

export const LANES: { key: LaneKey; label: string; cx: number; colorVar: string }[] = [
  { key: "kh", label: "Khách hàng", cx: 135, colorVar: "var(--steel)" },
  { key: "kd", label: "Kinh doanh", cx: 385, colorVar: "var(--rust)" },
  { key: "sx", label: "Sản xuất", cx: 635, colorVar: "var(--moss)" },
  { key: "kho", label: "Kho", cx: 885, colorVar: "var(--amber)" },
  { key: "gh", label: "Giao hàng", cx: 1135, colorVar: "var(--plum)" },
];

const DIVIDERS = [255, 505, 755, 1005];

export const NODES: FlowNode[] = [
  {
    id: "start",
    label: "Bắt đầu",
    lane: "kh",
    kind: "start",
    cx: 135,
    cy: 60,
    role: "Khách hàng",
    desc: "Khởi động nhu cầu mua sắm sản phẩm/dịch vụ in ấn từ phía Khách hàng.",
  },
  {
    id: "req",
    label: "Yêu cầu báo giá",
    lane: "kh",
    kind: "process",
    cx: 135,
    cy: 110,
    to: "khach-hang",
    role: "Khách hàng / Sales",
    desc: "Tiếp nhận thông tin yêu cầu chi tiết (quy cách, số lượng, thời gian) từ Khách hàng.",
  },
  {
    id: "price",
    label: "Tính giá",
    lane: "kd",
    kind: "process",
    cx: 385,
    cy: 110,
    to: "tinh-gia",
    role: "Kỹ thuật / Tính giá",
    desc: "Tính toán chi phí nguyên vật liệu, khuôn in, gia công và lên phương án giá tối ưu.",
  },
  {
    id: "confirm",
    label: "Xác nhận đơn hàng",
    lane: "kh",
    kind: "process",
    cx: 135,
    cy: 160,
    to: "khach-hang",
    role: "Khách hàng",
    desc: "Khách hàng duyệt báo giá, chốt điều khoản thanh toán và tiến hành ký hợp đồng / chốt đơn.",
  },
  {
    id: "quote",
    label: "Báo giá",
    lane: "kd",
    kind: "process",
    cx: 385,
    cy: 160,
    to: "bao-gia",
    role: "Phòng Kinh doanh",
    desc: "Lập bảng báo giá chính thức và gửi cho Khách hàng qua Email / Zalo.",
  },
  {
    id: "order",
    label: "Đơn đặt hàng bán",
    lane: "kd",
    kind: "process",
    cx: 385,
    cy: 210,
    to: "don-hang-ban",
    role: "Phòng Kinh doanh",
    desc: "Tạo Đơn bán chính thức trên hệ thống ERP, theo dõi tiến độ sản xuất và thanh toán.",
  },
  {
    id: "plan",
    label: "Kế hoạch giao hàng",
    lane: "kd",
    kind: "process",
    cx: 385,
    cy: 260,
    sub: "Sales lập",
    role: "Phòng Kinh doanh",
    desc: "Lên lịch trình dự kiến bàn giao sản phẩm cho khách hàng.",
  },
  {
    id: "prod",
    label: "Sản xuất",
    lane: "sx",
    kind: "process",
    cx: 635,
    cy: 260,
    to: "ke-hoach-sx",
    role: "Quản lý Sản xuất",
    desc: "Tiến hành sản xuất, phát lệnh tới các tổ in, cắt, gia công cán màng, bế hộp.",
  },
  {
    id: "stockin",
    label: "Nhập kho",
    lane: "kho",
    kind: "process",
    cx: 885,
    cy: 310,
    role: "Thủ kho",
    desc: "Kiểm đếm thành phẩm hoàn thiện từ xưởng và lập phiếu nhập kho lưu trữ.",
  },
  {
    id: "stockout",
    label: "Phiếu xuất kho",
    lane: "kho",
    kind: "process",
    cx: 885,
    cy: 360,
    sub: "Kho lập",
    role: "Thủ kho",
    desc: "Xuất hàng khỏi kho sẵn sàng bàn giao cho đội vận chuyển.",
  },
  {
    id: "delivery",
    label: "Phiếu giao hàng",
    lane: "gh",
    kind: "process",
    cx: 1135,
    cy: 410,
    sub: "Giao hàng lập",
    role: "Đội Giao hàng",
    desc: "Tiến hành vận chuyển hàng hóa tới địa chỉ khách hàng và ký biên bản giao nhận.",
  },
  {
    id: "receive",
    label: "Nhận hàng",
    lane: "kh",
    kind: "process",
    cx: 135,
    cy: 410,
    to: "khach-hang",
    role: "Khách hàng",
    desc: "Khách hàng nhận hàng, nghiệm thu chất lượng và phản hồi kết quả.",
  },
  {
    id: "return",
    label: "Xác nhận trả hàng",
    lane: "kd",
    kind: "decision",
    cx: 385,
    cy: 460,
    role: "Kinh doanh / QA",
    desc: "Đánh giá yêu cầu trả hàng nếu hàng bị lỗi quy cách hoặc nhầm lẫn sản phẩm.",
  },
  {
    id: "returned",
    label: "Hàng bán trả lại",
    lane: "kh",
    kind: "process",
    cx: 135,
    cy: 510,
    to: "khach-hang",
    role: "Kho / Kinh doanh",
    desc: "Xử lý thủ tục nhập trả lại kho và lên phương án đền bù / làm lại.",
  },
  {
    id: "receipt",
    label: "Phiếu thu / Báo có",
    lane: "kd",
    kind: "process",
    cx: 385,
    cy: 510,
    sub: "Kế toán",
    role: "Kế toán",
    desc: "Ghi nhận dòng tiền thanh toán từ khách hàng vào hệ thống kế toán.",
  },
  {
    id: "report",
    label: "Báo cáo bán hàng",
    lane: "kd",
    kind: "process",
    cx: 385,
    cy: 560,
    role: "Quản lý / Kinh doanh",
    desc: "Tổng hợp doanh thu, chi phí, hiệu suất chốt đơn và công nợ khách hàng.",
  },
  {
    id: "end",
    label: "Kết thúc",
    lane: "kd",
    kind: "end",
    cx: 385,
    cy: 610,
    role: "Hệ thống",
    desc: "Đơn hàng hoàn tất vòng đời bán hàng và thu tiền thành công.",
  },
];

export const EDGES: FlowEdge[] = [
  { from: "start", to: "req", d: "M135 72 L135 96" },
  { from: "req", to: "price", d: "M205 110 L315 110" },
  { from: "price", to: "quote", d: "M385 124 L385 146" },
  { from: "quote", to: "confirm", d: "M315 160 L205 160" },
  { from: "confirm", to: "order", d: "M135 174 L135 210 L315 210" },
  { from: "order", to: "prod", d: "M455 210 L635 210 L635 246" },
  { from: "order", to: "plan", d: "M385 224 L385 246" },
  { from: "prod", to: "stockin", d: "M705 260 L885 260 L885 296" },
  { from: "stockin", to: "stockout", d: "M885 324 L885 346" },
  { from: "stockout", to: "delivery", d: "M955 360 L1135 360 L1135 396" },
  { from: "delivery", to: "receive", d: "M1065 410 L205 410" },
  { from: "receive", to: "return", d: "M135 424 L135 442 L385 442" },
  { from: "return", to: "receipt", d: "M385 478 L385 496", label: "Không", lx: 405, ly: 486 },
  { from: "return", to: "returned", d: "M325 460 L135 460 L135 496", label: "Có", lx: 155, ly: 452 },
  { from: "receipt", to: "report", d: "M385 524 L385 546" },
  { from: "returned", to: "report", d: "M135 524 L135 560 L315 560" },
  { from: "report", to: "end", d: "M385 574 L385 598" },
];

const PROC_W = 140;
const PROC_H = 28;
const TERM_W = 100;
const TERM_H = 24;
const DIA_HW = 60;
const DIA_HH = 18;
const ICON_S = 10 / 24;

/** Hàm lấy toàn bộ kết nối trước/sau của node đang hover */
function getConnectedElements(targetId: string | null) {
  if (!targetId) return { nodes: new Set<string>(), edges: new Set<number>() };

  const connectedNodes = new Set<string>([targetId]);
  const connectedEdges = new Set<number>();

  // Tìm downstream (đi tiếp)
  const queueDown = [targetId];
  while (queueDown.length > 0) {
    const curr = queueDown.shift()!;
    EDGES.forEach((e, idx) => {
      if (e.from === curr && !connectedNodes.has(e.to)) {
        connectedNodes.add(e.to);
        connectedEdges.add(idx);
        queueDown.push(e.to);
      }
    });
  }

  // Tìm upstream (nguồn gốc)
  const queueUp = [targetId];
  while (queueUp.length > 0) {
    const curr = queueUp.shift()!;
    EDGES.forEach((e, idx) => {
      if (e.to === curr && !connectedNodes.has(e.from)) {
        connectedNodes.add(e.from);
        connectedEdges.add(idx);
        queueUp.push(e.from);
      }
    });
  }

  return { nodes: connectedNodes, edges: connectedEdges };
}

export function QuyTrinhKinhDoanhPage({ navigate }: { navigate: (id: string) => void }) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null);
  const [activeLaneFilter, setActiveLaneFilter] = useState<LaneKey | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [zoomLevel, setZoomLevel] = useState(1);

  const boardRef = useRef<HTMLDivElement>(null);

  // Kết nối path tracing
  const { nodes: connectedNodes, edges: connectedEdges } = useMemo(
    () => getConnectedElements(hoveredNodeId),
    [hoveredNodeId]
  );

  // Lọc theo lane & search query
  const filteredNodes = useMemo(() => {
    return NODES.filter((n) => {
      const matchLane = activeLaneFilter === "all" || n.lane === activeLaneFilter;
      const matchQuery =
        !searchQuery ||
        n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (n.sub && n.sub.toLowerCase().includes(searchQuery.toLowerCase())) ||
        n.role.toLowerCase().includes(searchQuery.toLowerCase());
      return matchLane && matchQuery;
    });
  }, [activeLaneFilter, searchQuery]);

  const filteredNodeIds = useMemo(
    () => new Set(filteredNodes.map((n) => n.id)),
    [filteredNodes]
  );

  // Handler Zoom
  const handleZoom = (delta: number) => {
    setZoomLevel((prev) => Math.min(Math.max(0.6, prev + delta), 1.5));
  };
  const handleResetZoom = () => setZoomLevel(1);

  return (
    <main className="qtkd">
      {/* Header Bar */}
      <header className="qtkd__head">
        <div className="qtkd__headrow">
          <div className="qtkd__title-box">
            <h1 className="qtkd__title">Quy trình kinh doanh</h1>
            <span className="qtkd__count">Phân hệ Bán hàng & Sản xuất</span>
          </div>

          {/* Quick Metrics Bar */}
          <div className="qtkd__metrics">
            <div className="qtkd__metric-pill">
              <span className="qtkd__metric-dot is-active"></span>
              <span className="qtkd__metric-num">17</span> Bước quy trình
            </div>
            <div className="qtkd__metric-pill">
              <span className="qtkd__metric-dot is-link"></span>
              <span className="qtkd__metric-num">7</span> Màn hình hoạt động
            </div>
          </div>
        </div>

        {/* Dynamic Controls Bar */}
        <div className="qtkd__toolbar">
          {/* Lane Filters */}
          <div className="qtkd__lane-filters">
            <button
              className={`qtkd__filter-pill ${activeLaneFilter === "all" ? "is-active" : ""}`}
              onClick={() => setActiveLaneFilter("all")}
            >
              Tất cả làn
            </button>
            {LANES.map((l) => (
              <button
                key={l.key}
                className={`qtkd__filter-pill is-${l.key} ${activeLaneFilter === l.key ? "is-active" : ""}`}
                onClick={() => setActiveLaneFilter(l.key)}
              >
                {l.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="qtkd__search-box">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              placeholder="Tìm kiếm bước..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="qtkd__search-clear" onClick={() => setSearchQuery("")}>
                ×
              </button>
            )}
          </div>

          {/* Zoom controls */}
          <div className="qtkd__zoom-box">
            <button onClick={() => handleZoom(-0.1)} title="Thu nhỏ (-)">
              -
            </button>
            <span>{Math.round(zoomLevel * 100)}%</span>
            <button onClick={() => handleZoom(0.1)} title="Phóng to (+)">
              +
            </button>
            {zoomLevel !== 1 && (
              <button onClick={handleResetZoom} title="Khôi phục 100%">
                ↺
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area — Sơ đồ Swimlane */}
      <div className="qtkd__board" ref={boardRef}>
        <div
          className="qtkd__zoom-wrapper"
          style={{
            transform: `scale(${zoomLevel})`,
            transformOrigin: "top left",
            transition: "transform 0.2s cubic-bezier(0.2, 0, 0, 1)",
          }}
        >
          <svg
            className="qtkd-svg"
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            role="img"
            aria-label="Sơ đồ swimlane quy trình kinh doanh 5 làn."
          >
            <defs>
              <marker
                id="qtkd-arrow"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path
                  d="M2 1 L8 5 L2 9"
                  className="qtkd-arrowhead"
                  fill="none"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </marker>
              <marker
                id="qtkd-arrow-active"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="8"
                markerHeight="8"
                orient="auto-start-reverse"
              >
                <path
                  d="M2 1 L8 5 L2 9"
                  className="qtkd-arrowhead-active"
                  fill="none"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </marker>

              {/* Neon Glow Filter */}
              <filter id="qtkd-glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Lane Background Bands */}
            <rect className="qtkd-lane-band" x="0" y="0" width={VIEW_W} height={HEAD_H} />
            {DIVIDERS.map((x) => (
              <line key={x} className="qtkd-divider" x1={x} y1="0" x2={x} y2={VIEW_H} />
            ))}
            <line className="qtkd-lane-rule" x1="0" y1={HEAD_H} x2={VIEW_W} y2={HEAD_H} />

            {/* Lane Headers */}
            {LANES.map((l) => (
              <g key={l.key} className={`qtkd-lane-header ${activeLaneFilter === l.key ? "is-highlighted" : ""}`}>
                <text className="qtkd-lane-label" x={l.cx} y={HEAD_H / 2 + 1} textAnchor="middle" dominantBaseline="central">
                  {l.label}
                </text>
              </g>
            ))}

            {/* Edges */}
            {EDGES.map((edge, idx) => {
              const isHoverActive = connectedEdges.has(idx);
              const isDimmed = hoveredNodeId && !isHoverActive;
              return (
                <g
                  key={idx}
                  className={`qtkd-edge-group ${isHoverActive ? "is-active" : ""} ${isDimmed ? "is-dimmed" : ""}`}
                >
                  <path
                    className="qtkd-edge"
                    d={edge.d}
                    fill="none"
                    markerEnd={isHoverActive ? "url(#qtkd-arrow-active)" : "url(#qtkd-arrow)"}
                  />
                  {isHoverActive && (
                    <path
                      className="qtkd-edge-pulse"
                      d={edge.d}
                      fill="none"
                      filter="url(#qtkd-glow)"
                    />
                  )}
                  {edge.label && (
                    <text className="qtkd-edge-label" x={edge.lx} y={edge.ly} textAnchor="middle" dominantBaseline="central">
                      {edge.label}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Nodes */}
            {NODES.map((node) => {
              const isConnected = connectedNodes.has(node.id);
              const isDimmed =
                (hoveredNodeId && !isConnected) ||
                (!filteredNodeIds.has(node.id) && !hoveredNodeId);
              const isSelected = selectedNode?.id === node.id;
              const isHovered = hoveredNodeId === node.id;

              return (
                <FlowNodeRender
                  key={node.id}
                  node={node}
                  isHovered={isHovered}
                  isConnected={isConnected}
                  isDimmed={isDimmed}
                  isSelected={isSelected}
                  onHover={() => setHoveredNodeId(node.id)}
                  onLeave={() => setHoveredNodeId(null)}
                  onClick={() => setSelectedNode(node)}
                  navigate={navigate}
                />
              );
            })}
          </svg>
        </div>
      </div>

      {/* Flyout Detail Drawer */}
      {selectedNode && (
        <aside className="qtkd-drawer" role="dialog" aria-labelledby="drawer-title">
          <div className="qtkd-drawer__backdrop" onClick={() => setSelectedNode(null)} />
          <div className="qtkd-drawer__content">
            <header className="qtkd-drawer__head">
              <div className="qtkd-drawer__tag-group">
                <span className={`qtkd-drawer__lane-tag is-${selectedNode.lane}`}>
                  {LANES.find((l) => l.key === selectedNode.lane)?.label}
                </span>
                <span className="qtkd-drawer__kind-tag">{selectedNode.kind.toUpperCase()}</span>
              </div>

              <button className="qtkd-drawer__close" onClick={() => setSelectedNode(null)} aria-label="Đóng">
                ×
              </button>
            </header>

            <div className="qtkd-drawer__body">
              <h2 id="drawer-title" className="qtkd-drawer__title">
                {selectedNode.label}
              </h2>
              {selectedNode.sub && <p className="qtkd-drawer__sub">{selectedNode.sub}</p>}

              <div className="qtkd-drawer__section">
                <h4>Nhiệm vụ & Quyết định</h4>
                <p>{selectedNode.desc}</p>
              </div>

              <div className="qtkd-drawer__section">
                <h4>Bộ phận phụ trách</h4>
                <div className="qtkd-drawer__role-pill">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                  {selectedNode.role}
                </div>
              </div>

              <div className="qtkd-drawer__section">
                <h4>Liên kết phân hệ ERP</h4>
                {selectedNode.to ? (
                  <div className="qtkd-drawer__link-box">
                    <p className="qtkd-drawer__link-info">
                      Màn hình làm việc trực tiếp đã sẵn sàng trên hệ thống.
                    </p>
                    <button
                      className="qtkd-drawer__action-btn"
                      onClick={() => navigate(selectedNode.to!)}
                    >
                      Truy cập màn {selectedNode.label} ngay
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="5" y1="12" x2="19" y2="12" />
                        <polyline points="12 5 19 12 12 19" />
                      </svg>
                    </button>
                  </div>
                ) : (
                  <div className="qtkd-drawer__soon-box">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    <span>Phân hệ này đang trong lộ trình phát triển.</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </aside>
      )}
    </main>
  );
}

/** Component vẽ từng Node SVG với hiệu ứng tương tác cao cấp */
function FlowNodeRender({
  node,
  isHovered,
  isConnected,
  isDimmed,
  isSelected,
  onHover,
  onLeave,
  onClick,
}: {
  node: FlowNode;
  isHovered: boolean;
  isConnected: boolean;
  isDimmed: boolean;
  isSelected: boolean;
  onHover: () => void;
  onLeave: () => void;
  onClick: () => void;
  navigate: (id: string) => void;
}) {
  const { cx, cy, kind, label, sub, lane, to } = node;
  const link = !!to;

  const cls = [
    "qtkd-node",
    `is-${lane}`,
    `is-${kind}`,
    link ? "qtkd-node--link" : "qtkd-node--soon",
    isHovered ? "is-hovered" : "",
    isConnected ? "is-connected" : "",
    isDimmed ? "is-dimmed" : "",
    isSelected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const shape =
    kind === "decision" ? (
      <polygon
        className="qtkd-shape"
        points={`${cx},${cy - DIA_HH} ${cx + DIA_HW},${cy} ${cx},${cy + DIA_HH} ${cx - DIA_HW},${cy}`}
      />
    ) : kind === "start" || kind === "end" ? (
      <rect
        className="qtkd-shape"
        x={cx - TERM_W / 2}
        y={cy - TERM_H / 2}
        width={TERM_W}
        height={TERM_H}
        rx={TERM_H / 2}
      />
    ) : (
      <rect
        className="qtkd-shape"
        x={cx - PROC_W / 2}
        y={cy - PROC_H / 2}
        width={PROC_W}
        height={PROC_H}
      />
    );

  let text;
  if (kind === "decision") {
    const [l1, l2] = ["Xác nhận", "trả hàng"];
    text = (
      <>
        <text className="qtkd-label" x={cx} y={cy - 5} textAnchor="middle" dominantBaseline="central">
          {l1}
        </text>
        <text className="qtkd-label" x={cx} y={cy + 5} textAnchor="middle" dominantBaseline="central">
          {l2}
        </text>
      </>
    );
  } else if (sub) {
    text = (
      <>
        <text className="qtkd-label" x={cx} y={cy - 5} textAnchor="middle" dominantBaseline="central">
          {label}
        </text>
        <text className="qtkd-sub" x={cx} y={cy + 6} textAnchor="middle" dominantBaseline="central">
          {sub}
        </text>
      </>
    );
  } else {
    text = (
      <text
        className={kind === "start" || kind === "end" ? "qtkd-label qtkd-label--term" : "qtkd-label"}
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {label}
      </text>
    );
  }

  // Icon mũi tên nhỏ báo hiệu bấm mở được màn
  const goIcon =
    link && kind === "process" ? (
      <g
        className="qtkd-go"
        transform={`translate(${cx + PROC_W / 2 - 16} ${cy - PROC_H / 2 + 10}) scale(${ICON_S})`}
        aria-hidden="true"
      >
        <path d="M7 7h10v10" />
        <path d="M7 17 17 7" />
      </g>
    ) : null;

  return (
    <g
      className={cls}
      role="button"
      tabIndex={0}
      aria-label={`Chi tiết bước ${label}`}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {shape}
      {text}
      {goIcon}
    </g>
  );
}
