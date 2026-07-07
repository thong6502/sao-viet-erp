// Sơ đồ TRỰC QUAN kiểu bình bài cho màn cấu hình (live preview).
// Mỗi hệ số = một hàng biểu tượng riêng → đổi ô nhập nào thì hàng đó thêm/bớt hình ngay:
//   Số bộ kẽm       → hàng "Kẽm"      (tấm kẽm ▮)
//   Số mặt + Tỉ lệ  → hình tờ in       (con T/S, chia nửa khi tự trở)
//   Số lần chạy máy → hàng "Lượt máy" (mũi tên ▶)
//   Số lần lăn mực  → hàng "Lượt mực" (giọt mực ●)
// KHÔNG gọi engine — thuần minh hoạ nghiệp vụ. Giá trị lớn bất thường (vd 45) rút gọn "×N".
import "./imposition-schematic.css";

export interface ImpositionSchematicProps {
  sides: number;
  finishedFactor: number;
  plateSetFactor: number;
  passCount: number;
  inkPassFactor: number;
  sharedPlateSet: boolean;
  allowRotate: boolean;
}

const GEO = 8; // số con hình học mẫu (4 cột × 2 hàng)
const COLS = 4;
const ROWS = 2;
const CAP = 6; // tối đa số biểu tượng vẽ, quá thì hiện "×N"

// Kích thước tờ in theo đơn vị viewBox
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

function fmtNum(n: number): string {
  return Number.isFinite(n) ? String(Math.round(n * 1000) / 1000) : "?";
}

function Meter({ label, count, unit, kind }: { label: string; count: number; unit: string; kind: "plate" | "pass" | "ink" }) {
  const n = Math.max(0, Math.round(Number.isFinite(count) ? count : 0));
  const shown = Math.min(n, CAP);
  return (
    <div className="imp-meter">
      <span className="imp-meter__label">{label}</span>
      <span className="imp-meter__icons">
        {n === 0 ? (
          <span className="imp-meter__val">— không</span>
        ) : (
          <>
            {Array.from({ length: shown }).map((_, i) => (
              <span key={i} className={`imp-glyph imp-glyph--${kind}`} />
            ))}
            <span className="imp-meter__val">{n > CAP ? `×${n}` : `${n} ${unit}`}</span>
          </>
        )}
      </span>
    </div>
  );
}

export function ImpositionSchematic({
  sides,
  finishedFactor,
  plateSetFactor,
  passCount,
  inkPassFactor,
  sharedPlateSet,
  allowRotate,
}: ImpositionSchematicProps) {
  const ff = Number.isFinite(finishedFactor) && finishedFactor > 0 ? finishedFactor : 1;
  const twoSide = sides === 2;
  const twoPiece = ff < 1; // bồi 2 mảnh: 2 ô ghép 1 SP
  const shared = sharedPlateSet || !(Number.isFinite(plateSetFactor) && plateSetFactor > 1);
  // one   = 1 mặt · glue = bồi 2 mảnh (2 ô = 1 SP) · turn = tự trở (mỗi ô tự đủ 2 mặt nhờ lật)
  // ab    = trở nhíp 2 kẽm riêng (2 tờ).
  const mode: "one" | "glue" | "turn" | "ab" =
    !twoSide ? "one" : twoPiece ? "glue" : shared ? "turn" : "ab";
  const piecesPerSheet = Math.max(1, Math.round(GEO * ff));

  const nSheets = mode === "ab" ? 2 : 1;
  const topGap = mode === "turn" ? 15 : 7;
  const labelH = 12;
  const vbW = M * 2 + SHEET_W * nSheets + GAP * (nSheets - 1);
  const vbH = M + topGap + SHEET_H + labelH + M;
  const sheetY = M + topGap;

  function sideAt(sheetIdx: number, col: number) {
    if (mode === "ab") return sheetIdx === 0 ? FRONT : BACK;
    if (mode === "glue") return col < COLS / 2 ? FRONT : BACK; // nửa trái T, nửa phải S
    return FRONT; // one
  }

  function renderSheet(sheetIdx: number, originX: number, label: string) {
    const cells = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = originX + PAD + c * (CELL_W + CGAP);
        const y = sheetY + PAD + r * (CELL_H + CGAP);
        if (mode === "turn") {
          // Tự trở: MỖI ô là 1 sản phẩm 2 mặt — nửa trên T (mặt trước), nửa dưới S (mặt sau).
          const hy = CELL_H / 2;
          cells.push(
            <g key={`${sheetIdx}-${r}-${c}`}>
              <rect x={x} y={y} width={CELL_W} height={hy} fill={FRONT.fill} stroke={FRONT.stroke} strokeWidth={0.3} />
              <rect x={x} y={y + hy} width={CELL_W} height={hy} fill={BACK.fill} stroke={BACK.stroke} strokeWidth={0.3} />
              <rect x={x} y={y} width={CELL_W} height={CELL_H} rx={1.5} fill="none" stroke="var(--ink)" strokeWidth={0.5} />
              <text x={x + CELL_W / 2} y={y + hy * 0.72} fontSize={5.5} fill={FRONT.ink} textAnchor="middle" fontFamily="var(--ff-mono)">T</text>
              <text x={x + CELL_W / 2} y={y + hy + hy * 0.78} fontSize={5.5} fill={BACK.ink} textAnchor="middle" fontFamily="var(--ff-mono)">S</text>
            </g>,
          );
        } else {
          const s = sideAt(sheetIdx, c);
          cells.push(
            <g key={`${sheetIdx}-${r}-${c}`}>
              <rect x={x} y={y} width={CELL_W} height={CELL_H} rx={1.5} fill={s.fill} stroke={s.stroke} strokeWidth={0.4} />
              <text x={x + CELL_W / 2} y={y + CELL_H / 2 + 3.2} fontSize={8.5} fill={s.ink} textAnchor="middle" fontFamily="var(--ff-mono)">{s.letter}</text>
            </g>,
          );
        }
      }
    }
    return (
      <g key={`sheet-${sheetIdx}`}>
        <rect x={originX} y={sheetY} width={SHEET_W} height={SHEET_H} rx={2} fill="var(--canvas)" stroke="var(--ink)" strokeWidth={0.5} />
        {cells}
        <text x={originX + SHEET_W / 2} y={sheetY + SHEET_H + 9} fontSize={6} fill="var(--ash)" textAnchor="middle">{label}</text>
      </g>
    );
  }

  const SHEET_LABEL: Record<string, string> = {
    one: "In 1 mặt",
    turn: "Tự trở — mỗi ô đủ 2 mặt",
    glue: "Bồi 2 mảnh — 2 ô ghép 1 SP",
  };
  const sheets = mode === "ab"
    ? [renderSheet(0, M, "Kẽm mặt trước"), renderSheet(1, M + SHEET_W + GAP, "Kẽm mặt sau")]
    : [renderSheet(0, M, SHEET_LABEL[mode])];

  return (
    <div className="imp-schem">
      <Meter label="Kẽm" count={plateSetFactor} unit="bộ" kind="plate" />

      <svg viewBox={`0 0 ${vbW} ${vbH}`} width="100%" role="img" aria-label={`Sơ đồ kiểu bình ${mode}: ${piecesPerSheet} con/tờ`}>
        <defs>
          <marker id="imp-arrow" markerUnits="userSpaceOnUse" markerWidth="6" markerHeight="6" refX="4" refY="2" orient="auto">
            <path d="M0,0 L4,2 L0,4 Z" fill="var(--ash)" />
          </marker>
        </defs>
        {mode === "turn" && (
          <>
            <path d={`M ${M + SHEET_W * 0.34} ${M + 11} Q ${M + SHEET_W / 2} ${M + 1} ${M + SHEET_W * 0.66} ${M + 11}`} fill="none" stroke="var(--ash)" strokeWidth={0.7} markerEnd="url(#imp-arrow)" />
            <text x={M + SHEET_W / 2} y={M + 5.5} fontSize={6} fill="var(--ash)" textAnchor="middle">trở bài</text>
          </>
        )}
        {mode === "ab" && (
          <>
            <path d={`M ${M + SHEET_W + 3} ${sheetY + SHEET_H / 2} L ${M + SHEET_W + GAP - 4} ${sheetY + SHEET_H / 2}`} stroke="var(--ash)" strokeWidth={0.7} markerEnd="url(#imp-arrow)" />
            <text x={M + SHEET_W + GAP / 2} y={sheetY + SHEET_H / 2 - 3} fontSize={5.5} fill="var(--ash)" textAnchor="middle">lật</text>
          </>
        )}
        {sheets}
      </svg>

      <Meter label="Lượt máy" count={passCount} unit="lượt" kind="pass" />
      <Meter label="Lượt mực" count={inkPassFactor} unit="lần" kind="ink" />

      <div className="imp-schem__flow">
        <strong>{GEO}</strong> con hình học <span className="imp-schem__op">× {fmtNum(ff)}</span> = <strong>{piecesPerSheet}</strong> con thành phẩm/tờ
      </div>
      <div className="imp-schem__note">
        T = mặt trước · S = mặt sau{allowRotate ? " · ⟳ cho xoay bài" : ""}
      </div>
      <div className="imp-schem__note">
        (8 ô chỉ là hình minh họa — số con thật do khổ giấy ÷ khổ sản phẩm quyết định ở màn Tính giá)
      </div>
    </div>
  );
}
