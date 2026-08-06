// Mực in dùng chung cho PHIẾU TÍNH GIÁ và LỆNH SẢN XUẤT.
//
// Tách ra đây vì hai màn cùng khai mực và cùng cần số kẽm. Để mỗi màn một bản là đúng chỗ hai
// bên lệch nhau: phiếu báo giá 8 kẽm còn lệnh xuống xưởng 6, không ai biết bên nào đúng.
//
// Công thức kẽm là bản SAO của `so_kem_moi_tay` bên server — có ở client để bấm chip là số nhảy
// ngay, không đợi vòng gọi API. Lệch giữa hai bên sẽ lộ ngay ở dòng tổng server trả về.
import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icons";
// CSS đi theo COMPONENT, không nằm ở css của một màn — nhờ vậy màn nào dùng khối này là tự có
// style, không phải nhớ import thêm. Trước đó `.tg-muc*` nằm trong `pages/tinh-gia.css` mà màn
// lệnh sản xuất không import file đó.
import "./MucIn.css";

/** Bốn mã mực process. Mọi mã khác trong tập là màu PHA (Pantone), chuỗi tự do. */
export const MUC_PROCESS = ["C", "M", "Y", "K"] as const;

/** Màu tô chip — TRANG TRÍ. Chữ C/M/Y/K luôn hiện để không phân biệt bằng mỗi màu. */
const MUC_MAU: Record<string, string> = {
  C: "#00A0DF", M: "#EC008C", Y: "#FFD700", K: "#231F20",
};

export interface PantoneStyle {
  code: string;
  label: string;
  bg: string;
  softBg: string;
  borderColor: string;
  textColor: string;
}

export const PANTONE_PRESETS: PantoneStyle[] = [
  { code: "185C", label: "185 C", bg: "#E4002B", softBg: "#fef2f2", borderColor: "#fecdd3", textColor: "#991b1b" },
  { code: "021C", label: "021 C", bg: "#FE5000", softBg: "#fff7ed", borderColor: "#fed7aa", textColor: "#9a3412" },
  { code: "Reflex Blue", label: "Reflex Blue", bg: "#0A1172", softBg: "#eff6ff", borderColor: "#bfdbfe", textColor: "#1e40af" },
  { code: "300C", label: "300 C", bg: "#005EB8", softBg: "#f0f9ff", borderColor: "#bae6fd", textColor: "#0369a1" },
  { code: "012C", label: "012 C", bg: "#FCD116", softBg: "#fefce8", borderColor: "#fef08a", textColor: "#854d0e" },
  { code: "Cool Gray 7C", label: "Cool Gray 7C", bg: "#97999B", softBg: "#f8fafc", borderColor: "#e2e8f0", textColor: "#334155" },
  { code: "871C", label: "871 C", bg: "linear-gradient(135deg, #d4af37, #aa7c11)", softBg: "#fefce8", borderColor: "#fef08a", textColor: "#713f12" },
  { code: "877C", label: "877 C", bg: "linear-gradient(135deg, #e0e0e0, #9e9e9e)", softBg: "#f8fafc", borderColor: "#cbd5e1", textColor: "#334155" },
  { code: "Warm Red", label: "Warm Red", bg: "#F9423A", softBg: "#fff1f2", borderColor: "#fecdd3", textColor: "#9f1239" },
  { code: "355C", label: "355 C", bg: "#009A44", softBg: "#f0fdf4", borderColor: "#bbf7d0", textColor: "#166534" },
];

export const getPantoneColor = (m: string): { bg: string; softBg?: string; borderColor?: string; textColor?: string } => {
  const norm = m.replace(/\s+/g, "").toUpperCase();
  const found = PANTONE_PRESETS.find(
    (p) => p.code.replace(/\s+/g, "").toUpperCase() === norm
  );
  if (found) return { bg: found.bg, softBg: found.softBg, borderColor: found.borderColor, textColor: found.textColor };
  let hash = 0;
  for (let i = 0; i < m.length; i++) {
    hash = m.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return {
    bg: `hsl(${hue}, 75%, 45%)`,
    softBg: `hsl(${hue}, 80%, 96%)`,
    borderColor: `hsl(${hue}, 70%, 88%)`,
    textColor: `hsl(${hue}, 85%, 28%)`,
  };
};

export const laMucPha = (m: string): boolean =>
  !MUC_PROCESS.includes(m as (typeof MUC_PROCESS)[number]);

/** Chuẩn hoá y hệt `tap_muc` của server: viết hoa, gộp khoảng trắng, bỏ trùng, giữ thứ tự. */
export const chuanHoaMuc = (v: unknown): string[] => {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const x of v) {
    const ma = String(x ?? "").trim().replace(/\s+/g, " ").toUpperCase();
    if (ma && !out.includes(ma)) out.push(ma);
  }
  return out;
};

/** Kẽm cho MỘT tay. `max(|A|,|B|)` là rút gọn SAI cho tự trở. */
export const soKemMoiTay = (mucA: string[], mucB: string[], quyCach: string): number => {
  if (quyCach === "mot_mat") return mucA.length;
  if (quyCach === "tu_tro" || quyCach === "tro_nhip") return new Set([...mucA, ...mucB]).size;
  return mucA.length + mucB.length;
};

/** Hai hàng chip mực + dòng phép tính. Màn nào cần khung/tiêu đề thì tự bọc bên ngoài. */
export function MucInHang({
  mucA, mucB, quyCachIn, disabled, onChange,
}: {
  mucA: string[];
  mucB: string[];
  quyCachIn: string;
  disabled?: boolean;
  onChange: (a: string[], b: string[]) => void;
}) {
  const [openMat, setOpenMat] = useState<"a" | "b" | null>(null);
  const [inputVal, setInputVal] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);

  const motMat = quyCachIn === "mot_mat";
  const chung = quyCachIn === "tu_tro" || quyCachIn === "tro_nhip";
  const kem = soKemMoiTay(mucA, mucB, quyCachIn);
  const dienGiai = motMat || chung ? `${kem} mực dùng chung` : `${mucA.length} + ${mucB.length}`;

  const dat = (la: "a" | "b", tap: string[]) => (la === "a" ? onChange(tap, mucB) : onChange(mucA, tap));
  const doi = (la: "a" | "b", ma: string) => {
    const cur = la === "a" ? mucA : mucB;
    dat(la, cur.includes(ma) ? cur.filter((x) => x !== ma) : [...cur, ma]);
  };

  const handleAdd = (la: "a" | "b", maRaw: string) => {
    const ma = chuanHoaMuc([maRaw])[0];
    const cur = la === "a" ? mucA : mucB;
    if (ma && !cur.includes(ma)) {
      dat(la, [...cur, ma]);
    }
    setOpenMat(null);
    setInputVal("");
  };

  useEffect(() => {
    if (!openMat) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpenMat(null);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenMat(null);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openMat]);

  const hang = (la: "a" | "b", nhan: string) => {
    const tap = la === "a" ? mucA : mucB;
    const kia = la === "a" ? mucB : mucA;
    const dungLai = kia.filter((m) => laMucPha(m) && !tap.includes(m));
    const isOpen = openMat === la;

    return (
      <div className="tg-muc__row">
        <span className="tg-muc__side">{nhan}</span>
        <div className="tg-muc__chips">
          {MUC_PROCESS.map((m) => {
            const on = tap.includes(m);
            return (
              <button
                key={m}
                type="button"
                className={`tg-muc__proc${on ? " is-on" : ""}`}
                aria-pressed={on}
                aria-label={`Mực ${m} ${nhan}`}
                disabled={disabled}
                style={on ? { background: MUC_MAU[m], color: m === "Y" ? "#412402" : "#fff" } : undefined}
                onClick={() => doi(la, m)}
              >
                {m}
              </button>
            );
          })}
          {tap.filter(laMucPha).map((m) => {
            const col = getPantoneColor(m);
            return (
              <span key={m} className="tg-muc__pha">
                <span className="tg-muc__pha-dot" style={{ background: col.bg }} />
                {m}
                <button
                  type="button"
                  aria-label={`Bỏ mực ${m} ${nhan}`}
                  disabled={disabled}
                  onClick={() => doi(la, m)}
                >
                  <Icon name="x" size={11} />
                </button>
              </span>
            );
          })}

          <div className="tg-pantone-wrapper">
            <button
              type="button"
              className={`tg-muc__add${isOpen ? " is-active" : ""}`}
              disabled={disabled}
              onClick={() => {
                if (isOpen) {
                  setOpenMat(null);
                } else {
                  setOpenMat(la);
                  setInputVal("");
                }
              }}
            >
              + Pantone
            </button>

            {isOpen && !disabled && (
              <div className={`tg-pantone-popover${la === "b" ? " tg-pantone-popover--up" : ""}`} ref={popoverRef}>
                <form
                  className="tg-pantone-popover__form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleAdd(la, inputVal);
                  }}
                >
                  <div className="tg-pantone-popover__input-wrap">
                    <Icon name="search" size={13} />
                    <input
                      type="text"
                      className="tg-pantone-popover__input"
                      placeholder="Nhập mã Pantone (vd: 185C)..."
                      value={inputVal}
                      onChange={(e) => setInputVal(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <button
                    type="submit"
                    className="tg-pantone-popover__submit"
                    disabled={!inputVal.trim()}
                  >
                    <span>Thêm</span>
                    <span className="tg-pantone-popover__enter-key">↵</span>
                  </button>
                </form>

                <div className="tg-pantone-popover__sec">
                  <span className="tg-pantone-popover__title">MÃ MÀU PHỔ BIẾN</span>
                  <div className="tg-pantone-popover__grid">
                    {PANTONE_PRESETS.map((p) => {
                      const isAdded = tap.includes(p.code);
                      return (
                        <button
                          key={p.code}
                          type="button"
                          disabled={isAdded}
                          className={`tg-pantone-popover__chip${isAdded ? " is-disabled" : ""}`}
                          onClick={() => handleAdd(la, p.code)}
                          title={isAdded ? "Đã chọn màu này" : `Thêm Pantone ${p.label}`}
                        >
                          <span
                            className="tg-pantone-popover__dot"
                            style={{ background: p.bg }}
                          />
                          <span className="tg-pantone-popover__code">
                            {p.label}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {dungLai.length > 0 && (
                  <div className="tg-pantone-popover__sec tg-pantone-popover__sec--reuse">
                    <span className="tg-pantone-popover__title">DÙNG LẠI TỪ MẶT KIA</span>
                    <div className="tg-pantone-popover__reuse-list">
                      {dungLai.map((m) => {
                        const col = getPantoneColor(m);
                        return (
                          <button
                            key={m}
                            type="button"
                            className="tg-pantone-popover__reuse-chip"
                            onClick={() => handleAdd(la, m)}
                          >
                            <span
                              className="tg-pantone-popover__dot"
                              style={{ background: col.bg }}
                            />
                            <span>+ {m}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <span className="tg-muc__count">{tap.length} mực</span>
      </div>
    );
  };

  return (
    <>
      {hang("a", "Mặt A")}
      {!motMat && hang("b", "Mặt B")}
      <div className="tg-muc__derive">{dienGiai} = {kem} kẽm mỗi tay</div>
    </>
  );
}
