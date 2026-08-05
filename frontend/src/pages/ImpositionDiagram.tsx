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
  chuaMm: number; // chừa GỘP (mm) trừ đều mỗi chiều — đường cũ, dùng khi không tách chiều
  chuaDai?: number; // chừa chiều DÀI (nhíp giấy + đuôi) — ưu tiên hơn chuaMm
  chuaRong?: number; // chừa chiều RỘNG (lề hông ×2)
  /** Hoặc đưa nguyên CÁC KHOẢN CHỪA của phiếu/quy cách → server tự tách chiều. Ưu tiên dùng cách
   *  này: nơi gọi khỏi lặp lại phép cộng của engine (đúng chỗ màn lệnh từng cộng sai). */
  chuaTho?: {
    chua_nhip?: number;   // ô đè của phiếu
    nhip_giay_mm?: number; le_hong_mm?: number; duoi_thang_mau_mm?: number;  // danh mục MÁY
  };
  bleedMm?: number; // tràn lề mỗi cạnh con
  kheCatMm?: number; // khe giữa 2 con kề nhau
  soCon: number; // Số con hiện tại (có thể được đè tay)
  /** > 1 = SÁCH (gấp tay) → vẽ lưới TAY thay cho lưới con. Xem `luoiTay` bên dưới. */
  trangMoiTay?: number;
}

/** Lưới của một TAY SÁCH — hỏi câu khác hẳn bình bài, nên không dùng chung đáp án được:
 *  bình bài hỏi "tờ này nhét được mấy con", tay sách thì số ô ĐÃ CHỐT (= trang mỗi tay ÷ 2),
 *  việc còn lại chỉ là xếp đúng chừng ấy ô cho vừa tờ. Lấy `con` của engine vẽ tay 16 trang
 *  là ra 16 ô trong khi đúng phải 8.
 *
 *  Thử mọi cách chia `cols × rows = oMoiMat`, cả hai hướng trang. Diện tích giấy ăn vào NHƯ NHAU
 *  ở mọi cách chia (tích cols×rows không đổi) nên KHÔNG phân xử được bằng phế liệu. Thứ tự chấm:
 *
 *   ① TRANG ĐỨNG trước — chỉ xoay 90° khi để đứng không cách nào vừa. Chấm bằng độ phủ trước
 *     rồi mới tính hướng thì tay 16 khổ 65×86 ra "2×4 xoay 90°": vẫn vừa tờ, vẫn đúng 8 ô, ăn
 *     giấy y hệt, nhưng không ai bình bài kiểu đó — thợ xếp 4×2 trang đứng.
 *   ② cùng hướng thì lấy cái phủ đều hai chiều nhất (`min(phủ ngang, phủ dọc)` lớn nhất).
 *
 *  ĐÂY LÀ HÌNH MINH HOẠ, KHÔNG PHẢI BẢN BÌNH BÀI ĐEM IN: không đánh số trang, không hướng gấp,
 *  không thớ giấy. Muốn mấy thứ đó thì phải dựng `folding_scheme` ở docs/spec-quy-tac-binh-bai.md. */
function luoiTay(
  oMoiMat: number, dungW: number, dungH: number, pieceR: number, pieceD: number, khe: number,
): { cols: number; rows: number; xoay: boolean } | null {
  if (oMoiMat < 1 || dungW <= 0 || dungH <= 0 || pieceR <= 0 || pieceD <= 0) return null;
  let best: { cols: number; rows: number; xoay: boolean; phu: number } | null = null;
  for (const xoay of [false, true]) {
    for (let cols = 1; cols <= oMoiMat; cols++) {
      if (oMoiMat % cols !== 0) continue;
      const rows = oMoiMat / cols;
      const cw = xoay ? pieceD : pieceR;
      const ch = xoay ? pieceR : pieceD;
      const canW = cols * cw + khe * (cols - 1);
      const canH = rows * ch + khe * (rows - 1);
      if (canW > dungW || canH > dungH) continue;
      const phu = Math.min(canW / dungW, canH / dungH);
      if (!best || phu > best.phu) best = { cols, rows, xoay, phu };
    }
    // ① Đã có cách xếp trang ĐỨNG thì dừng — vòng `xoay = true` chỉ là phương án cứu.
    if (best) break;
  }
  return best ? { cols: best.cols, rows: best.rows, xoay: best.xoay } : null;
}

export function ImpositionDiagram({
  khoInDai, khoInRong, daiTP, rongTP, chuaMm,
  chuaDai, chuaRong, chuaTho, bleedMm = 0, kheCatMm = 0, soCon, trangMoiTay = 1,
}: Props) {
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
          chua_dai_mm: chuaDai,
          chua_rong_mm: chuaRong,
          ...(chuaTho ?? {}),
          bleed_mm: bleedMm,
          khe_cat_mm: kheCatMm,
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
    // `chuaTho` là object → so bằng CHUỖI, không thì mỗi lần render lại là một tham chiếu mới và
    // effect bắn liên tục (debounce 300ms không cứu nổi).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, ready, khoInDai, khoInRong, daiTP, rongTP, chuaMm, chuaDai, chuaRong,
      JSON.stringify(chuaTho ?? null), bleedMm, kheCatMm]);

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
  // Chừa vẽ lấy THEO CHIỀU từ chính engine (`chua_dai`/`chua_rong`) — chia đôi về hai biên.
  const insetY = (lay ? Math.max(0, lay.chua_dai) : 0) / 2; // trục Y = chiều DÀI
  const insetX = (lay ? Math.max(0, lay.chua_rong) : 0) / 2; // trục X = chiều RỘNG

  const khe = Math.max(0, kheCatMm); // n con → n−1 khe
  // bleed > 0 → mỗi ô vẽ HAI hình: ngoài = vùng tràn lề, trong = thành phẩm thật.
  const bleed = Math.max(0, bleedMm);
  // Kích thước 1 ô trên trục vẽ (X=rộng, Y=dài) — dùng piece ĐÃ cộng bleed của engine. Nhánh dự
  // phòng phải cộng bleed tay: lưới tay vẽ được TRƯỚC khi /binh-bai trả lời, không thì nhấp nháy.
  const pieceD = lay?.piece_dai ?? daiTP + bleed * 2;
  const pieceR = lay?.piece_rong ?? rongTP + bleed * 2;

  // ── SÁCH: lưới TAY, không phải lưới con ──
  const laTay = trangMoiTay > 1;
  const oMoiMat = laTay ? Math.max(1, Math.ceil(trangMoiTay / 2)) : 0; // tay in 2 mặt → chia đôi
  const tay = laTay
    ? luoiTay(oMoiMat, Math.max(W - (lay?.chua_rong ?? 0), 0), Math.max(H - (lay?.chua_dai ?? 0), 0),
              pieceR, pieceD, khe)
    : null;

  const cols = laTay ? tay?.cols ?? 0 : lay?.cols ?? 0;
  const rows = laTay ? tay?.rows ?? 0 : lay?.rows ?? 0;
  const rotated = laTay ? !!tay?.xoay : !!lay?.rotated;
  // Số ô VẼ: tay sách luôn đủ `oMoiMat` (không có chuyện xếp thiếu trang), tờ rời theo engine.
  const con = laTay ? (tay ? oMoiMat : 0) : lay?.con ?? 0;
  const cellW = rotated ? pieceD : pieceR; // theo trục X (rộng ②)
  const cellH = rotated ? pieceR : pieceD; // theo trục Y (dài ②)

  // Bình bài xếp KÍN nên vẽ từ mép chừa là đúng. Tay sách thì số ô chốt cứng, thường chỉ ăn
  // nửa tờ — vẽ từ góc sẽ ra một khối lệch trông như hình vẽ hỏng, nên căn giữa vùng khả dụng.
  const canhX =
    laTay && con > 0
      ? Math.max((W - insetX * 2 - (cols * cellW + khe * (cols - 1))) / 2, 0)
      : 0;
  const canhY =
    laTay && con > 0
      ? Math.max((H - insetY * 2 - (rows * cellH + khe * (rows - 1))) / 2, 0)
      : 0;

  const pieces: { x: number; y: number; used: boolean }[] = [];
  if (con > 0) {
    let index = 0;
    for (let r = 0; r < rows; r++) {
      for (let cix = 0; cix < cols; cix++) {
        pieces.push({
          x: insetX + canhX + cix * (cellW + khe),
          y: insetY + canhY + r * (cellH + khe),
          used: laTay || index < soCon,
        });
        index++;
      }
    }
  }
  // Đánh số ô = số con thứ mấy. Tay sách KHÔNG đánh: 1..8 ở đây dễ bị đọc nhầm thành số TRANG,
  // mà thứ tự trang thật thì phụ thuộc kiểu gấp — thứ hình này không biết và không hứa.
  const showIndex = !laTay && con > 0 && con <= 24;
  const trimW = Math.max(cellW - bleed * 2, 0);
  const trimH = Math.max(cellH - bleed * 2, 0);
  // Phần tờ thật sự dùng — tay 16 trên tờ chứa nổi 32 thì con số này rơi xuống ~50%, nhìn là biết.
  const phuTay =
    laTay && tay && W > 0 && H > 0
      ? Math.round(((oMoiMat * cellW * cellH) / ((W - (lay?.chua_rong ?? 0)) * (H - (lay?.chua_dai ?? 0)))) * 100)
      : 0;
  const chuaD = lay?.chua_dai ?? 0;
  const chuaR = lay?.chua_rong ?? 0;
  const coThongSo = bleed > 0 || khe > 0 || chuaD > 0 || chuaR > 0;

  return (
    <div className={`tg-imp${con === 0 && (lay || laTay) ? " tg-imp--bad" : ""}`}>
      <div className="tg-imp__stage">
        <svg
          className="tg-imp__svg"
          viewBox={`${-pad} ${-pad} ${W + pad * 2} ${H + pad * 2}`}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={
            laTay
              ? con > 0
                ? `Sơ đồ tay sách: ${oMoiMat} trang mỗi mặt tờ in, lưới ${cols}×${rows}`
                : `Khổ tờ in không xếp nổi ${oMoiMat} trang mỗi mặt`
              : con > 0
                ? `Sơ đồ bình bài: ${soCon} con mỗi tờ in (tổng ${con})`
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
          {/* Vùng khả dụng (trừ chừa) — chừa lệch nhau giữa 2 chiều nên vẽ theo từng trục */}
          {(insetX > 0 || insetY > 0) && (
            <rect
              className="tg-imp__usable"
              x={insetX}
              y={insetY}
              width={Math.max(W - insetX * 2, 0)}
              height={Math.max(H - insetY * 2, 0)}
              vectorEffect="non-scaling-stroke"
            />
          )}
          {/* Lưới con. bleed > 0 → hình ngoài = vùng tràn lề, hình trong = thành phẩm thật. */}
          {pieces.map((p, i) => (
            <g key={i}>
              {bleed > 0 && (
                <rect
                  className="tg-imp__bleed"
                  x={p.x}
                  y={p.y}
                  width={cellW}
                  height={cellH}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              <rect
                className={`tg-imp__piece${p.used ? "" : " tg-imp__piece--unused"}`}
                x={p.x + bleed}
                y={p.y + bleed}
                width={trimW}
                height={trimH}
                vectorEffect="non-scaling-stroke"
              />
              {p.used && showIndex && (
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
          {con === 0 && (lay || laTay) && (
            <line
              className="tg-imp__cross"
              x1={insetX || W * 0.12}
              y1={insetY || H * 0.12}
              x2={W - (insetX || W * 0.12)}
              y2={H - (insetY || H * 0.12)}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>

      <div className="tg-imp__caption">
        {laTay ? (
          con > 0 ? (
            <>
              <span className="tg-imp__con">{oMoiMat}</span>
              <span className="tg-imp__con-unit">trang/mặt</span>
              <span className="tg-imp__sep">·</span>
              <span className="tg-imp__eff">hiệu suất {phuTay}%</span>
              <span className="tg-imp__grid">
                {cols}×{rows}
                {rotated ? " · xoay 90°" : ""}
              </span>
            </>
          ) : (
            <span className="tg-imp__warn">
              Khổ tờ in không xếp nổi {oMoiMat} trang mỗi mặt.
            </span>
          )
        ) : con > 0 ? (
          <>
            <span className="tg-imp__con">{soCon}</span>
            <span className="tg-imp__con-unit">con/tờ</span>
            {/* Đè số con LỚN HƠN sức chứa lưới → giá vốn thiếu tờ. Chỉ NHẮC, không tự sửa. */}
            {soCon > con ? (
              <span className="tg-imp__over">đè vượt bình bài · engine xếp được {con}</span>
            ) : soCon < con ? (
              <span className="tg-imp__overridden-hint" style={{ fontSize: "10.5px", color: "var(--ash-2)", marginLeft: "2px" }}>
                (engine {con})
              </span>
            ) : null}
            <span className="tg-imp__sep">·</span>
            {/* Hiệu suất của LƯỚI engine — không nhân tỉ lệ đè, tránh vọt quá 100%. */}
            <span className="tg-imp__eff">hiệu suất {Math.round(lay?.hieu_suat ?? 0)}%</span>
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

      {/* Thông số ĐANG áp dụng — để nhìn ra ngay vì sao số con đổi, khỏi phải đoán. */}
      {lay && coThongSo && (
        <div className="tg-imp__params">
          {bleed > 0 && (
            <span className="tg-imp__param">
              bleed <b>{bleed}</b> · con {cellW}×{cellH}
            </span>
          )}
          {khe > 0 && (
            <span className="tg-imp__param">
              khe cắt <b>{khe}</b>
            </span>
          )}
          {(chuaD > 0 || chuaR > 0) && (
            <span className="tg-imp__param">
              chừa dài <b>{chuaD}</b> · rộng <b>{chuaR}</b>
            </span>
          )}
        </div>
      )}
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
