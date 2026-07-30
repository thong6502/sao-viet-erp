// Chart primitives dùng chung (Recharts) — theo skill dataviz:
//   - bar MẢNH, bo đầu 4px neo baseline, grid ngang mờ, trục mono nhỏ recessive;
//   - tooltip mặc định trên mọi mark (card nhỏ, số mono);
//   - palette categorical CỐ ĐỊNH thứ tự, đã qua validator (lightness/chroma/CVD/contrast)
//     trên surface --canvas #fbfaf5 — KHÔNG dùng token brand ít chroma (moss/steel đọc thành xám).
import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Thứ tự series cố định — tông ĐẤT theo prototype: rust · charcoal · gold · green ·
 *  plum · sienna. Đã qua validator dataviz (CVD/contrast/lightness PASS); riêng charcoal
 *  cố ý "fail" sàn chroma vì prototype dùng lát ĐEN làm series 2 — chấp nhận được nhờ
 *  tương phản cao + donut/legend luôn có nhãn và % (secondary encoding). */
export const CHART_SERIES = ["#c5400a", "#2a2723", "#a87708", "#2e7d46", "#5f4d9e", "#a04a2a"];

/* Hai trục hai font: trục phân loại là CHỮ (--ff-sans), trục giá trị là SỐ (--ff-num,
   chữ số đều bề rộng nên vạch chia không so le). Trước đây dùng chung một const. */
const AXIS_TICK_CAT = { fontFamily: "var(--ff-sans)", fontSize: 10, fill: "var(--ash-2)" } as const;
const AXIS_TICK_NUM = { fontFamily: "var(--ff-num)", fontSize: 10, fill: "var(--ash-2)" } as const;

function TipCard({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        background: "var(--canvas)",
        border: "1px solid var(--rule)",
        borderRadius: 6,
        padding: "6px 10px",
        boxShadow: "var(--shadow-4)",
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      {children}
    </div>
  );
}

export interface BarDatum {
  label: string;
  value: number;
  /** Dòng phụ trong tooltip (vd "9 đơn"). */
  sub?: string;
}

/** Bar chart theo tháng: một series, bar mảnh bo đầu, tooltip giá trị + dòng phụ. */
export function MonthBars({
  data,
  height = 210,
  color = CHART_SERIES[0],
  formatValue,
  formatAxis,
}: {
  data: BarDatum[];
  height?: number;
  color?: string;
  /** Format giá trị trong tooltip (vd moneyCompact). */
  formatValue: (v: number) => string;
  /** Format vạch trục Y (vd đổi ra triệu). */
  formatAxis: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barCategoryGap="32%">
        <CartesianGrid vertical={false} stroke="var(--rule-hair)" />
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={{ stroke: "var(--rule-soft)" }}
          tick={AXIS_TICK_CAT}
          dy={4}
          interval={0}
        />
        <YAxis
          width={40}
          tickCount={4}
          tickLine={false}
          axisLine={false}
          tick={AXIS_TICK_NUM}
          tickFormatter={formatAxis}
        />
        <Tooltip
          cursor={{ fill: "var(--rule-hair)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as BarDatum;
            return (
              <TipCard>
                <strong style={{ fontFamily: "var(--ff-sans)" }}>{d.label}</strong>
                <div style={{ fontFamily: "var(--ff-num)", color: "var(--ink)" }}>
                  {formatValue(d.value)}
                </div>
                {d.sub && <div style={{ color: "var(--ash)" }}>{d.sub}</div>}
              </TipCard>
            );
          }}
        />
        <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} maxBarSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface SliceDatum {
  label: string;
  value: number;
}

/** Donut cơ cấu: khe 2px giữa lát (paddingAngle + stroke surface), legend HTML bên cạnh
 *  (chấm màu + nhãn + % — chữ luôn màu ink/ash, không nhuộm màu series). */
export function MixDonut({
  slices,
  centerTop,
  centerBottom,
  formatValue,
  height = 150,
  stacked = false,
}: {
  slices: SliceDatum[];
  centerTop: string;
  centerBottom: string;
  formatValue: (v: number) => string;
  height?: number;
  /** Bố cục đứng (mẫu prototype): donut giữa trên, legend full-width bên dưới
   *  (hàng dot + nhãn + % đậm, ngăn hairline). Mặc định là ngang. */
  stacked?: boolean;
}) {
  const total = slices.reduce((s, d) => s + d.value, 0) || 1;
  const shown = slices.slice(0, CHART_SERIES.length);
  return (
    <div
      style={
        stacked
          ? { display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }
          : { display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }
      }
    >
      <div style={{ position: "relative", width: height, height, flex: "0 0 auto" }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={shown}
              dataKey="value"
              nameKey="label"
              innerRadius="62%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="var(--canvas)"
              strokeWidth={2}
              startAngle={90}
              endAngle={-270}
            >
              {shown.map((d, i) => (
                <Cell key={d.label} fill={CHART_SERIES[i % CHART_SERIES.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as SliceDatum;
                return (
                  <TipCard>
                    <strong>{d.label}</strong>
                    <div style={{ fontFamily: "var(--ff-num)" }}>
                      {formatValue(d.value)} · {Math.round((d.value / total) * 100)}%
                    </div>
                  </TipCard>
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          {stacked ? (
            <>
              <span className="stat__label">{centerBottom}</span>
              <span style={{ fontFamily: "var(--ff-num)", fontSize: 22, fontWeight: 600, color: "var(--ink)" }}>
                {centerTop}
              </span>
            </>
          ) : (
            <>
              <span style={{ fontFamily: "var(--ff-num)", fontSize: 17, fontWeight: 600, color: "var(--ink)" }}>
                {centerTop}
              </span>
              <span className="stat__label">{centerBottom}</span>
            </>
          )}
        </div>
      </div>
      <ul
        style={
          stacked
            ? { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", width: "100%" }
            : { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6, minWidth: 130, flex: 1 }
        }
      >
        {shown.map((d, i) => (
          <li
            key={d.label}
            style={
              stacked
                ? { display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "7px 0", borderBottom: i < shown.length - 1 ? "1px solid var(--rule-hair)" : "none" }
                : { display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }
            }
          >
            <span
              aria-hidden="true"
              style={{
                width: 10,
                height: 10,
                borderRadius: 3,
                background: CHART_SERIES[i % CHART_SERIES.length],
                flex: "0 0 auto",
              }}
            />
            <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--ink)" }}>
              {d.label}
            </span>
            <span style={{ fontFamily: "var(--ff-num)", color: stacked ? "var(--ink)" : "var(--ash)", fontWeight: stacked ? 600 : 400 }}>
              {Math.round((d.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
