import "./ui-blocks.css";

/**
 * Sơ đồ bình bản trực quan — mirror ĐÚNG công thức auto-imposition của pricing_engine:
 *   usable_w = sheet_w − gripper − 2×edge_trim
 *   usable_h = sheet_h − 2×edge_trim
 *   piece    = finished + 2×bleed + gutter (mỗi chiều)
 *   straight = ⌊uw/pw⌋×⌊uh/ph⌋ ; rotated (nếu không khóa thớ) = ⌊uw/ph⌋×⌊uh/pw⌋ → lấy max
 * Đổi công thức engine thì PHẢI đổi ở đây — hình sai là lừa người dùng.
 */
export interface ImpositionInput {
  sheetW: number;
  sheetH: number;
  finishedW: number;
  finishedH: number;
  gripperCm: number;
  edgeTrimCm: number;
  bleedCm: number;
  gutterCm: number;
  grainLocked: boolean;
}

export interface ImpositionLayout {
  fits: boolean;
  rotated: boolean;
  cols: number;
  rows: number;
  pieces: number;
  efficiencyPct: number; // (con × diện tích thành phẩm) / diện tích tờ
  usableW: number;
  usableH: number;
  pieceW: number;
  pieceH: number;
}

export function computeImposition(inp: ImpositionInput): ImpositionLayout | null {
  const { sheetW: sw, sheetH: sh, finishedW: fw, finishedH: fh } = inp;
  if (!sw || !sh || !fw || !fh || sw <= 0 || sh <= 0 || fw <= 0 || fh <= 0) return null;

  const usableW = sw - inp.gripperCm - 2 * inp.edgeTrimCm;
  const usableH = sh - 2 * inp.edgeTrimCm;
  const pieceW = fw + 2 * inp.bleedCm + inp.gutterCm;
  const pieceH = fh + 2 * inp.bleedCm + inp.gutterCm;

  if (usableW <= 0 || usableH <= 0 || pieceW <= 0 || pieceH <= 0) {
    return { fits: false, rotated: false, cols: 0, rows: 0, pieces: 0, efficiencyPct: 0, usableW, usableH, pieceW, pieceH };
  }

  const straightCols = Math.floor(usableW / pieceW);
  const straightRows = Math.floor(usableH / pieceH);
  const straight = Math.max(0, straightCols * straightRows);

  let rotated = 0;
  let rotCols = 0;
  let rotRows = 0;
  if (!inp.grainLocked) {
    rotCols = Math.floor(usableW / pieceH);
    rotRows = Math.floor(usableH / pieceW);
    rotated = Math.max(0, rotCols * rotRows);
  }

  const useRotated = rotated > straight;
  const pieces = Math.max(straight, rotated);
  const cols = useRotated ? rotCols : straightCols;
  const rows = useRotated ? rotRows : straightRows;
  const efficiencyPct = pieces > 0 ? (pieces * fw * fh) / (sw * sh) * 100 : 0;

  return {
    fits: pieces >= 1,
    rotated: useRotated,
    cols,
    rows,
    pieces,
    efficiencyPct,
    usableW,
    usableH,
    pieceW,
    pieceH,
  };
}

export function ImpositionDiagram({ input }: { input: ImpositionInput }) {
  const layout = computeImposition(input);
  if (!layout) return null;

  const { sheetW: sw, sheetH: sh } = input;
  const { fits, rotated, cols, rows, pieces } = layout;

  // Piece thực vẽ (đã gồm bleed, trừ gutter làm khe trắng giữa các con)
  const drawW = (rotated ? layout.pieceH : layout.pieceW) - input.gutterCm;
  const drawH = (rotated ? layout.pieceW : layout.pieceH) - input.gutterCm;
  const stepW = rotated ? layout.pieceH : layout.pieceW;
  const stepH = rotated ? layout.pieceW : layout.pieceH;
  const originX = input.gripperCm + input.edgeTrimCm;
  const originY = input.edgeTrimCm;
  const showNumbers = pieces > 0 && pieces <= 40;

  const cells: Array<{ x: number; y: number; n: number }> = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      cells.push({ x: originX + c * stepW, y: originY + r * stepH, n: r * cols + c + 1 });
    }
  }

  const fontSize = Math.min(drawW, drawH) * 0.36;

  return (
    <svg
      viewBox={`-1 -1 ${sw + 2} ${sh + 2}`}
      style={{ width: "100%", maxWidth: "420px", height: "auto", display: "block" }}
      role="img"
      aria-label={`Sơ đồ bình bản: ${pieces} con/tờ`}
    >
      {/* Tờ giấy */}
      <rect x={0} y={0} width={sw} height={sh} fill="var(--canvas)" stroke="var(--ink)" strokeWidth={0.25} />

      {/* Vùng nhíp (cạnh nạp giấy, bên trái) */}
      {input.gripperCm > 0 && (
        <>
          <rect x={0} y={0} width={input.gripperCm} height={sh} fill="var(--rule-soft)" stroke="var(--rule)" strokeWidth={0.1} />
          {sh > 8 && (
            <text
              x={input.gripperCm / 2}
              y={sh / 2}
              fontSize={Math.min(2.6, input.gripperCm * 0.7)}
              fill="var(--ash)"
              textAnchor="middle"
              transform={`rotate(-90 ${input.gripperCm / 2} ${sh / 2})`}
            >
              nhíp
            </text>
          )}
        </>
      )}

      {/* Khung xén mép */}
      {input.edgeTrimCm > 0 && (
        <rect
          x={input.gripperCm + input.edgeTrimCm}
          y={input.edgeTrimCm}
          width={Math.max(0, layout.usableW)}
          height={Math.max(0, layout.usableH)}
          fill="none"
          stroke="var(--ash-2)"
          strokeWidth={0.12}
          strokeDasharray="0.8 0.6"
        />
      )}

      {/* Các con */}
      {fits ? (
        cells.map((cell) => (
          <g key={cell.n}>
            <rect
              x={cell.x}
              y={cell.y}
              width={drawW}
              height={drawH}
              fill="var(--rust-soft)"
              stroke="var(--rust)"
              strokeWidth={0.18}
            />
            {showNumbers && (
              <text
                x={cell.x + drawW / 2}
                y={cell.y + drawH / 2 + fontSize * 0.35}
                fontSize={fontSize}
                fill="var(--rust-deep)"
                textAnchor="middle"
                fontFamily="var(--ff-mono)"
              >
                {cell.n}
              </text>
            )}
          </g>
        ))
      ) : (
        // Vượt khổ: vẽ con tràn ra ngoài tờ cho thấy vì sao không đặt vừa
        <>
          <rect
            x={originX}
            y={originY}
            width={layout.pieceW - input.gutterCm}
            height={layout.pieceH - input.gutterCm}
            fill="var(--signal-soft)"
            stroke="var(--signal)"
            strokeWidth={0.25}
            strokeDasharray="1.2 0.8"
          />
          <text x={sw / 2} y={sh / 2} fontSize={Math.min(3.2, sw / 14)} fill="var(--signal)" textAnchor="middle" fontWeight="bold">
            VƯỢT KHỔ
          </text>
        </>
      )}
    </svg>
  );
}
