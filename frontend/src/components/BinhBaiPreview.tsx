// Live SVG preview sơ đồ tờ in (spec §9.4). Vẽ theo khổ tờ in (từ engine) + kích thước con
// (từ Bảng thử). Con số badge lấy từ engine (preview); vị trí ô tự tính client-side để VẼ.
import { useMemo } from "react";
import type { PreviewOut, TestBench, VersionConfig } from "../api/binhBai";

interface Props {
  config: VersionConfig;
  bench: TestBench;
  preview: PreviewOut | null;
  error?: string | null;
}

const AREA_W = 400;
const AREA_H = 320;
const PAD = 14;

function fit1d(usable: number, cell: number, gutter: number): number {
  const denom = cell + gutter;
  if (usable <= 0 || denom <= 0) return 0;
  return Math.max(0, Math.floor((usable + gutter) / denom));
}

export function BinhBaiPreview({ config, bench, preview, error }: Props) {
  const model = useMemo(() => buildModel(config, bench, preview), [config, bench, preview]);
  const errWarn = preview?.warnings.find((w) => w.severity === "error");
  // Thiếu số liệu (E-MODE-REQ) = hướng dẫn nhẹ; còn lại (không vừa khổ) = lỗi đỏ.
  const isMissing = !error && !!errWarn && errWarn.code === "E-MODE-REQ";
  const hasError = !!error || (!!errWarn && !isMissing);
  const errMsg = error || errWarn?.message || "Không vừa khổ máy";
  const guideMsg = isMissing ? errWarn!.message : (!preview ? "Nhập số liệu ở Bảng thử để xem sơ đồ." : "");

  return (
    <div className="bb-preview">
      <svg viewBox={`0 0 ${AREA_W} ${AREA_H}`} className="bb-preview__svg" role="img"
        aria-label="Sơ đồ bình bản">
        {/* nền */}
        <rect x={0} y={0} width={AREA_W} height={AREA_H} className="bb-preview__bg" />
        {model && (
          <g>
            {/* tờ in */}
            <rect x={model.x} y={model.y} width={model.w} height={model.h}
              className={`bb-sheet${hasError ? " bb-sheet--error" : ""}`} />
            {/* nhíp (gripper) */}
            {model.gripperH > 0 && (
              <g>
                <rect x={model.x} y={model.y + model.h - model.gripperH} width={model.w}
                  height={model.gripperH} className="bb-gripper" />
                <text x={model.x + model.w / 2} y={model.y + model.h - model.gripperH / 2}
                  className="bb-lbl bb-lbl--sm" textAnchor="middle" dominantBaseline="middle">
                  nhíp {bench.gripper_mm}mm
                </text>
              </g>
            )}
            {/* thang màu đuôi (tail) */}
            {model.tailH > 0 && (
              <rect x={model.x} y={model.y} width={model.w} height={model.tailH} className="bb-tail" />
            )}
            {/* lề hông */}
            {model.sideW > 0 && (
              <>
                <rect x={model.x} y={model.y} width={model.sideW} height={model.h} className="bb-side" />
                <rect x={model.x + model.w - model.sideW} y={model.y} width={model.sideW}
                  height={model.h} className="bb-side" />
              </>
            )}
            {/* vùng in được (viền) */}
            <rect x={model.ux} y={model.uy} width={model.uw} height={model.uh} className="bb-usable" />
            {/* các đơn vị */}
            {model.cells.map((c, i) => (
              <g key={i}>
                <rect x={c.x} y={c.y} width={c.w} height={c.h}
                  className={`bb-cell bb-cell--${model.kind}${c.hatch ? " bb-cell--matrix" : ""}`} />
                {c.label && (
                  <text x={c.x + c.w / 2} y={c.y + c.h / 2} className="bb-lbl bb-lbl--cell"
                    textAnchor="middle" dominantBaseline="middle"
                    transform={c.rot ? `rotate(180 ${c.x + c.w / 2} ${c.y + c.h / 2})` : undefined}>
                    {c.label}
                  </text>
                )}
                {c.fold && (
                  <line x1={c.x} y1={c.y + c.h / 2} x2={c.x + c.w} y2={c.y + c.h / 2}
                    className="bb-fold" />
                )}
              </g>
            ))}
          </g>
        )}
        {hasError && (
          <text x={AREA_W / 2} y={AREA_H / 2} className="bb-error" textAnchor="middle">
            {errMsg}
          </text>
        )}
        {isMissing && (
          <text x={AREA_W / 2} y={AREA_H / 2} className="bb-guide" textAnchor="middle">
            <tspan x={AREA_W / 2}>✎ Cần thêm số liệu ở Bảng thử</tspan>
          </text>
        )}
      </svg>

      {/* badge tổng */}
      <div className="bb-preview__badge">
        {preview && !hasError && !isMissing ? (
          <>
            <strong>{preview.don_vi_per_to_in}</strong>{" "}
            {unitLabel(preview.layout_mode)}/tờ in
            {preview.hao_hinh_hoc_pct > 0 && (
              <span className="bb-preview__waste"> · hao {(preview.hao_hinh_hoc_pct * 100).toFixed(0)}%</span>
            )}
          </>
        ) : hasError ? (
          <span className="bb-preview__err">⚠ {errMsg}</span>
        ) : (
          <span className="bb-preview__waste">{guideMsg}</span>
        )}
      </div>
    </div>
  );
}

function unitLabel(mode: string): string {
  if (mode === "signature") return "tay";
  if (mode === "nesting") return "blank";
  return "con";
}

interface Cell {
  x: number; y: number; w: number; h: number;
  label?: string; hatch?: boolean; rot?: boolean; fold?: boolean;
}
interface Model {
  x: number; y: number; w: number; h: number;      // tờ in (px)
  ux: number; uy: number; uw: number; uh: number;   // vùng in được (px)
  gripperH: number; tailH: number; sideW: number;
  cells: Cell[];
  kind: string;
}

function buildModel(config: VersionConfig, bench: TestBench, preview: PreviewOut | null): Model | null {
  // Khổ tờ in: ưu tiên engine trả về, else tờ nguyên.
  const sw = preview?.kho_to_in?.rong || bench.rong_ng || 0;
  const sh = preview?.kho_to_in?.dai || bench.dai_ng || 0;
  if (sw <= 0 || sh <= 0) return null;

  const scale = Math.min((AREA_W - 2 * PAD) / sw, (AREA_H - 2 * PAD) / sh);
  const w = sw * scale;
  const h = sh * scale;
  const x = (AREA_W - w) / 2;
  const y = (AREA_H - h) / 2;

  const gripperH = (bench.gripper_mm || 0) * scale;
  const tailH = (config.tail_colorbar_mm || 0) * scale;
  const sideW = (config.side_margin_mm || 0) * scale;

  // vùng in được (px): trừ nhíp (đáy) + thang (đỉnh) + lề (2 bên)
  const ux = x + sideW;
  const uy = y + tailH;
  const uw = w - 2 * sideW;
  const uh = h - tailH - gripperH;

  const cells: Cell[] = [];
  let kind = config.layout_mode;

  const bleed = bench.bleed_mm ?? config.bleed_default_mm ?? 0;

  if (config.layout_mode === "nesting") {
    const bw = (bench.blank_w ?? 0), bh = (bench.blank_h ?? 0);
    if (bw > 0 && bh > 0) {
      placeGrid(cells, ux, uy, uw, uh, bw, bh, config.matrix_allowance_mm, scale, true, "");
    }
  } else if (config.layout_mode === "signature") {
    // 1 mặt tờ in: pps/2 trang, đánh số + đường gấp.
    const pps = preview?.danh_sach_tay?.[0]?.pages_per_sig ?? config.pages_per_sig ?? 8;
    const perSide = Math.max(1, Math.floor(pps / 2));
    const pw = bench.rong_tp + 2 * bleed, ph = bench.dai_tp + 2 * bleed;
    placeGrid(cells, ux, uy, uw, uh, pw, ph, config.gutter_mm, scale, false, "p", perSide, true);
  } else {
    // step_repeat
    const cw = bench.rong_tp + 2 * bleed, ch = bench.dai_tp + 2 * bleed;
    placeGrid(cells, ux, uy, uw, uh, cw, ch, config.gutter_mm, scale, config.allow_rotate, "");
  }

  return { x, y, w, h, ux, uy, uw, uh, gripperH, tailH, sideW, cells, kind };
}

// Xếp lưới ô để VẼ (mirror fit engine). rotate=true thử cả 2 hướng lấy nhiều hơn.
function placeGrid(out: Cell[], ux: number, uy: number, uw: number, uh: number,
                   cellW: number, cellH: number, gap: number, scale: number,
                   rotate: boolean, labelPrefix: string, limit = 0, fold = false) {
  const uwm = uw / scale, uhm = uh / scale;  // usable in mm
  const c0 = fit1d(uwm, cellW, gap) * fit1d(uhm, cellH, gap);
  const c90 = rotate ? fit1d(uwm, cellH, gap) * fit1d(uhm, cellW, gap) : 0;
  const useRot = c90 > c0;
  const cw = (useRot ? cellH : cellW);
  const ch = (useRot ? cellW : cellH);
  const cols = fit1d(uwm, cw, gap);
  const rows = fit1d(uhm, ch, gap);
  const cwPx = cw * scale, chPx = ch * scale, gapPx = gap * scale;
  let n = 0;
  for (let r = 0; r < rows; r++) {
    for (let col = 0; col < cols; col++) {
      if (limit && n >= limit) return;
      n++;
      out.push({
        x: ux + col * (cwPx + gapPx),
        y: uy + r * (chPx + gapPx),
        w: cwPx,
        h: chPx,
        label: labelPrefix ? `${labelPrefix}${n}` : String(n),
        rot: useRot,
        fold,
        hatch: false,
      });
    }
  }
}
