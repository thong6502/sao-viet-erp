// Sơ đồ TRỰC QUAN kiểu bình bài cho màn cấu hình (live preview).
// Vẽ SVG suy THẲNG từ các trường của quy tắc — đổi số mặt / hệ số / toggle là hình đổi ngay.
//   1 mặt            → 1 tờ, toàn con mặt trước (T)
//   Tự trở (chung kẽm hoặc tỉ lệ con/tờ < 1) → 1 tờ chia nửa T | nửa S, có mũi tên "trở"
//   A-B (2 kẽm riêng) → 2 tờ: kẽm mặt trước (T) + kẽm mặt sau (S)
// KHÔNG gọi engine — thuần minh hoạ nghiệp vụ để nhân viên nhìn là hiểu.
import "./imposition-schematic.css";

export interface ImpositionSchematicProps {
  sides: number;
  finishedFactor: number;
  plateSetFactor: number;
  passCount: number;
  sharedPlateSet: boolean;
  allowRotate: boolean;
}

const GEO = 8; // số con hình học mẫu (4 cột × 2 hàng)
const COLS = 4;
const ROWS = 2;

// Kích thước theo đơn vị viewBox
const M = 6;
const SHEET_W = 104;
const SHEET_H = 58;
const GAP = 26;
const PAD = 6;
const CGAP = 3;
const CELL_W = (SHEET_W - PAD * 2 - (COLS - 1) * CGAP) / COLS;
const CELL_H = (SHEET_H - PAD * 2 - (ROWS - 1) * CGAP) / ROWS;

const FRONT = { fill: "var(--rust-soft)", stroke: "var(--rust)", ink: "var(--rust-deep)", letter: "T" };
const BACK = { fill: "var(--steel-soft)", stroke: "var(--steel)", ink: "var(--steel)", letter: "S" };

export function ImpositionSchematic({
  sides,
  finishedFactor,
  plateSetFactor,
  passCount,
  sharedPlateSet,
  allowRotate,
}: ImpositionSchematicProps) {
  const ff = Number.isFinite(finishedFactor) && finishedFactor > 0 ? finishedFactor : 1;
  const twoSide = sides === 2;
  const shared = sharedPlateSet || !(Number.isFinite(plateSetFactor) && plateSetFactor > 1);
  const split = twoSide && (shared || ff < 1); // 1 tờ chia T|S (kiểu tự trở)
  const mode: "one" | "turn" | "ab" = !twoSide ? "one" : split ? "turn" : "ab";
  const plates = mode === "ab" ? 2 : 1;
  const piecesPerSheet = Math.max(1, Math.round(GEO * ff));
  const passes = Number.isFinite(passCount) && passCount > 0 ? passCount : 1;

  const nSheets = mode === "ab" ? 2 : 1;
  const topGap = twoSide ? 15 : 7;
  const labelH = 12;
  const vbW = M * 2 + SHEET_W * nSheets + GAP * (nSheets - 1);
  const vbH = M + topGap + SHEET_H + labelH + M;
  const sheetY = M + topGap;

  function sideAt(sheetIdx: number, col: number) {
    if (mode === "one") return FRONT;
    if (mode === "ab") return sheetIdx === 0 ? FRONT : BACK;
    return col < COLS / 2 ? FRONT : BACK; // turn: nửa trái trước, nửa phải sau
  }

  function renderSheet(sheetIdx: number, originX: number, label: string) {
    const cells = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const s = sideAt(sheetIdx, c);
        const x = originX + PAD + c * (CELL_W + CGAP);
        const y = sheetY + PAD + r * (CELL_H + CGAP);
        cells.push(
          <g key={`${sheetIdx}-${r}-${c}`}>
            <rect x={x} y={y} width={CELL_W} height={CELL_H} rx={1.5} fill={s.fill} stroke={s.stroke} strokeWidth={0.4} />
            <text x={x + CELL_W / 2} y={y + CELL_H / 2 + 3.2} fontSize={8.5} fill={s.ink} textAnchor="middle" fontFamily="var(--ff-mono)">{s.letter}</text>
          </g>,
        );
      }
    }
    return (
      <g key={`sheet-${sheetIdx}`}>
        <rect x={originX} y={sheetY} width={SHEET_W} height={SHEET_H} rx={2} fill="var(--canvas)" stroke="var(--ink)" strokeWidth={0.5} />
        {cells}
        <text x={originX + SHEET_W / 2} y={sheetY + SHEET_H + 9} fontSize={6} fill="var(--ash)" textAnchor="middle">{label}</text>
        {allowRotate && (
          <text x={originX + SHEET_W - 3.5} y={sheetY + 8} fontSize={7} fill="var(--ash)" textAnchor="end">⟳</text>
        )}
      </g>
    );
  }

  const sheets = mode === "ab"
    ? [renderSheet(0, M, "Kẽm mặt trước"), renderSheet(1, M + SHEET_W + GAP, "Kẽm mặt sau")]
    : [renderSheet(0, M, mode === "one" ? "1 bộ kẽm" : "Tự trở · 1 bộ kẽm")];

  return (
    <div className="imp-schem">
      <svg viewBox={`0 0 ${vbW} ${vbH}`} width="100%" role="img" aria-label={`Sơ đồ kiểu bình: ${piecesPerSheet} con/tờ, ${plates} bộ kẽm`}>
        <defs>
          <marker id="imp-arrow" markerUnits="userSpaceOnUse" markerWidth="6" markerHeight="6" refX="4" refY="2" orient="auto">
            <path d="M0,0 L4,2 L0,4 Z" fill="var(--ash)" />
          </marker>
        </defs>

        {/* Mũi tên trở bài */}
        {mode === "turn" && (
          <>
            <path
              d={`M ${M + SHEET_W * 0.34} ${M + 11} Q ${M + SHEET_W / 2} ${M + 1} ${M + SHEET_W * 0.66} ${M + 11}`}
              fill="none"
              stroke="var(--ash)"
              strokeWidth={0.7}
              markerEnd="url(#imp-arrow)"
            />
            <text x={M + SHEET_W / 2} y={M + 5.5} fontSize={6} fill="var(--ash)" textAnchor="middle">trở bài</text>
          </>
        )}
        {mode === "ab" && (
          <>
            <path
              d={`M ${M + SHEET_W + 3} ${sheetY + SHEET_H / 2} L ${M + SHEET_W + GAP - 4} ${sheetY + SHEET_H / 2}`}
              stroke="var(--ash)"
              strokeWidth={0.7}
              markerEnd="url(#imp-arrow)"
            />
            <text x={M + SHEET_W + GAP / 2} y={sheetY + SHEET_H / 2 - 3} fontSize={5.5} fill="var(--ash)" textAnchor="middle">lật</text>
          </>
        )}

        {sheets}
      </svg>

      <div className="imp-schem__caption">
        <span><strong>{piecesPerSheet}</strong> con thành phẩm/tờ</span>
        <span className="imp-schem__dot">·</span>
        <span><strong>{plates}</strong> bộ kẽm</span>
        <span className="imp-schem__dot">·</span>
        <span>qua máy <strong>×{passes}</strong></span>
        {allowRotate && (
          <>
            <span className="imp-schem__dot">·</span>
            <span>⟳ cho xoay bài</span>
          </>
        )}
      </div>
      <div className="imp-schem__note">Minh hoạ mẫu 8 con hình học/tờ · T = mặt trước, S = mặt sau</div>
    </div>
  );
}
