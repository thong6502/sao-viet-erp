// Sơ đồ bình bài LIVE — vẽ tờ in ② + lưới con ③ xếp ĐÚNG engine (/api/tinh-gia/binh-bai).
// KHÔNG tự tính layout kiểu khác: gọi endpoint (debounce ~300ms) → dùng cols/rows/rotated/usable
// để hình luôn khớp số con thật. con=0 (khổ TP > khổ in) → cảnh báo đỏ "không vừa". SVG thuần,
// viewBox theo khổ (mm), token repo (rust accent), KHÔNG emoji.
import { useEffect, useRef, useState } from "react";
import { api, type BinhBaiOut } from "../api/client";
import { useAuth } from "../auth/useAuth";

interface Props {
  khoInDai: number; // ② mm
  khoInRong: number; // ② mm
  daiTP: number; // ③ mm
  rongTP: number; // ③ mm
  chuaMm: number; // tổng 5 chừa (mm) trừ mỗi chiều
}

export function ImpositionDiagram({ khoInDai, khoInRong, daiTP, rongTP, chuaMm }: Props) {
  const { token } = useAuth();
  const [lay, setLay] = useState<BinhBaiOut | null>(null);
  const [pending, setPending] = useState(false);
  const seq = useRef(0);

  const ready = khoInDai > 0 && khoInRong > 0 && daiTP > 0 && rongTP > 0;

  useEffect(() => {
    if (!token || !ready) {
      setLay(null);
      return;
    }
    setPending(true);
    const my = ++seq.current;
    const h = window.setTimeout(() => {
      api.tinhGia
        .binhBai(token, {
          kho_in_dai: khoInDai,
          kho_in_rong: khoInRong,
          dai_thanh_pham: daiTP,
          rong_thanh_pham: rongTP,
          chua_mm: chuaMm,
        })
        .then((res) => {
          if (my === seq.current) {
            setLay(res);
            setPending(false);
          }
        })
        .catch(() => {
          if (my === seq.current) {
            setLay(null);
            setPending(false);
          }
        });
    }, 300);
    return () => window.clearTimeout(h);
  }, [token, ready, khoInDai, khoInRong, daiTP, rongTP, chuaMm]);

  // Chưa đủ khổ → khối hướng dẫn.
  if (!ready) {
    return (
      <div className="tg-imp tg-imp--empty">
        <ImpIcon />
        <p className="tg-imp__hint">Nhập khổ tờ in và khổ thành phẩm để xem sơ đồ bình bài.</p>
      </div>
    );
  }

  // ── Kích thước vẽ theo mm (viewBox = khổ tờ in) ──
  // Trục X = chiều RỘNG (②), trục Y = chiều DÀI (②) — khớp cols=RỘNG / rows=DÀI của engine.
  const W = khoInRong;
  const H = khoInDai;
  const pad = Math.max(W, H) * 0.04;
  const inset = (lay ? Math.max(0, chuaMm) : 0) / 2; // chừa vẽ = tổng chừa/2 mỗi biên

  const cols = lay?.cols ?? 0;
  const rows = lay?.rows ?? 0;
  const rotated = !!lay?.rotated;
  const con = lay?.con ?? 0;
  // Kích thước 1 con trên trục vẽ (X=rộng, Y=dài).
  const cellW = rotated ? daiTP : rongTP; // theo trục X (rộng ②)
  const cellH = rotated ? rongTP : daiTP; // theo trục Y (dài ②)

  const pieces: { x: number; y: number }[] = [];
  if (con > 0) {
    for (let r = 0; r < rows; r++) {
      for (let cix = 0; cix < cols; cix++) {
        pieces.push({ x: inset + cix * cellW, y: inset + r * cellH });
      }
    }
  }
  const showIndex = con > 0 && con <= 24;

  return (
    <div className={`tg-imp${con === 0 && lay ? " tg-imp--bad" : ""}`}>
      <div className="tg-imp__stage">
        <svg
          className="tg-imp__svg"
          viewBox={`${-pad} ${-pad} ${W + pad * 2} ${H + pad * 2}`}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={
            con > 0
              ? `Sơ đồ bình bài: ${con} con mỗi tờ in`
              : "Khổ thành phẩm lớn hơn khổ tờ in — không vừa"
          }
        >
          {/* Tờ in */}
          <rect
            className="tg-imp__sheet"
            x={0}
            y={0}
            width={W}
            height={H}
            rx={Math.max(W, H) * 0.008}
            vectorEffect="non-scaling-stroke"
          />
          {/* Vùng khả dụng (trừ chừa) */}
          {inset > 0 && (
            <rect
              className="tg-imp__usable"
              x={inset}
              y={inset}
              width={Math.max(W - inset * 2, 0)}
              height={Math.max(H - inset * 2, 0)}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {/* Lưới con */}
          {pieces.map((p, i) => (
            <g key={i}>
              <rect
                className="tg-imp__piece"
                x={p.x}
                y={p.y}
                width={cellW}
                height={cellH}
                vectorEffect="non-scaling-stroke"
              />
              {showIndex && (
                <text
                  className="tg-imp__pnum"
                  x={p.x + cellW / 2}
                  y={p.y + cellH / 2}
                  dominantBaseline="central"
                  textAnchor="middle"
                  fontSize={Math.min(cellW, cellH) * 0.42}
                >
                  {i + 1}
                </text>
              )}
            </g>
          ))}
          {/* Cảnh báo không vừa */}
          {con === 0 && lay && (
            <line
              className="tg-imp__cross"
              x1={inset || W * 0.12}
              y1={inset || H * 0.12}
              x2={W - (inset || W * 0.12)}
              y2={H - (inset || H * 0.12)}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>

      <div className="tg-imp__caption">
        {con > 0 ? (
          <>
            <span className="tg-imp__con">{con}</span>
            <span className="tg-imp__con-unit">con/tờ</span>
            <span className="tg-imp__sep">·</span>
            <span className="tg-imp__eff">hiệu suất {lay?.hieu_suat ?? 0}%</span>
            <span className="tg-imp__grid">
              {cols}×{rows}
              {rotated ? " · xoay 90°" : ""}
            </span>
          </>
        ) : lay ? (
          <span className="tg-imp__warn">Khổ thành phẩm lớn hơn khổ tờ in — không vừa.</span>
        ) : (
          <span className="tg-imp__loading">{pending ? "Đang tính bình bài…" : "—"}</span>
        )}
      </div>
    </div>
  );
}

const ImpIcon = () => (
  <svg
    width="26"
    height="26"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
  </svg>
);
