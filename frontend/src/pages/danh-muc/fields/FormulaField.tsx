// Ô CÔNG THỨC — gõ ra chip tiếng Việt, có gợi ý biến, kiểm cú pháp và bảng biến khả dụng.
import { useEffect, useMemo, useRef, useState } from "react";

import { catToken } from "../formulaTokens";
import { traBien, useBienCongThuc, type BienCongThuc } from "../bienCongThuc";
import { CircleXIcon, XIcon } from "../icons";

const MATH_FUNCS = ["ceil", "floor", "round", "max", "min"];

function renderFormulaChips({
  value,
  tra,
  validVars,
  whitelist,
  onRemoveToken,
}: {
  value: string;
  tra: (ma: string) => BienCongThuc | undefined;
  validVars: string[] | null;
  whitelist: string[];
  onRemoveToken?: (index: number) => void;
}) {
  const matches = catToken(value);

  return matches.map((m, idx) => {
    if (/^\s+$/.test(m)) {
      return <span key={idx} className="rc-formula__chip-space">{m}</span>;
    }

    const trimmed = m.trim();
    const info = tra(trimmed);
    const isValidVar = validVars ? validVars.includes(trimmed) : (whitelist.includes(trimmed) || !!info);

    if (isValidVar || info) {
      return (
        <span
          key={idx}
          className="rc-formula__chip-token rc-formula__chip-token--var"
          title={info ? `${info.nhan} (Mã: ${trimmed})\nĐơn vị: ${info.don_vi}\nNguồn: ${info.nguon}` : `Mã: ${trimmed}`}
        >
          <span className="rc-formula__chip-token-label">{info?.nhan ?? trimmed}</span>
          {onRemoveToken && (
            <button
              type="button"
              className="rc-formula__chip-token-del"
              onClick={(e) => {
                e.stopPropagation();
                onRemoveToken(idx);
              }}
              title={`Xoá biến ${info?.nhan ?? trimmed}`}
            >
              ×
            </button>
          )}
        </span>
      );
    }

    if (MATH_FUNCS.includes(trimmed)) {
      return (
        <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--func">
          {trimmed}
        </span>
      );
    }

    if (/^\d+(?:\.\d+)?$/.test(trimmed)) {
      return (
        <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--num">
          {trimmed}
        </span>
      );
    }

    if (/^[\+\-\*\/\(\)\,]$/.test(trimmed)) {
      const displayOp = trimmed === "*" ? "×" : trimmed === "/" ? "÷" : trimmed === "-" ? "−" : trimmed;
      return (
        <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--op">
          {displayOp}
        </span>
      );
    }

    return (
      <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--error" title={`Biến "${trimmed}" chưa hỗ trợ hoặc gõ sai`}>
        {trimmed}
      </span>
    );
  });
}

export function FormulaField({
  value,
  onChange,
  configPrefix,
  bienGoiY,
  loaiO: loaiOEp,
  nhanO = "Công thức tính giá",
  goY = "Nhập công thức tính giá (vd: dai_tp * rong_tp * don_gia)...",
  id = "formula-textarea",
}: {
  value: string;
  onChange: (v: string) => void;
  configPrefix: string;
  bienGoiY?: string[];
  loaiO?: string;
  nhanO?: React.ReactNode;
  goY?: string;
  id?: string;
}) {
  const isCd = configPrefix.includes("cong-doan");
  const isGiay = configPrefix.endsWith("/giay");
  const isDonVi = configPrefix.includes("don-vi");
  const loaiO = loaiOEp ?? (isDonVi ? "quy_doi" : isCd ? "cong_doan" : isGiay ? "giay" : "vat_tu");
  const tuDien = useBienCongThuc();
  const tra = useMemo(() => traBien(tuDien), [tuDien]);
  const whitelist = useMemo(
    () => bienGoiY ?? tuDien.filter((b) => b.loai.includes(loaiO)).map((b) => b.ma),
    [bienGoiY, tuDien, loaiO],
  );
  const validVars = useMemo(
    () => (whitelist.length ? [...whitelist] : null),
    [whitelist],
  );

  const [showSyntax, setShowSyntax] = useState(false);
  const syntaxBtnRef = useRef<HTMLButtonElement>(null);
  const syntaxPopRef = useRef<HTMLDivElement>(null);

  const [typedWord, setTypedWord] = useState("");
  const [showAuto, setShowAuto] = useState(false);
  const [autoIdx, setAutoIdx] = useState(0);

  const autoSuggestions = useMemo(() => {
    if (!typedWord || typedWord.length < 1) return [];
    const q = typedWord.toLowerCase();
    return whitelist.filter((v) => {
      const info = tra(v);
      return v.toLowerCase().includes(q) || (info && info.nhan.toLowerCase().includes(q));
    }).slice(0, 8);
  }, [typedWord, whitelist, tra]);

  useEffect(() => {
    if (!showSyntax) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (syntaxPopRef.current?.contains(t) || syntaxBtnRef.current?.contains(t)) return;
      setShowSyntax(false);
    };
    // Esc đóng popover — và CHỈ popover. Ô công thức luôn nằm trong một drawer, mà drawer cũng
    // nghe Esc trên `document`; listener của drawer gắn TRƯỚC nên ở pha nổi bọt nó chạy trước và
    // đóng phắt cả drawer. Bắt ở pha BẮT (`capture`) để mình chạy trước, rồi `preventDefault()`
    // làm dấu cho drawer biết phím này đã có chủ (xem `components/Drawer.tsx`).
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setShowSyntax(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [showSyntax]);

  const commitTypedWord = (textToCommit?: string) => {
    const word = (textToCommit !== undefined ? textToCommit : typedWord).trim();
    if (word) {
      onChange((value ? value.trimEnd() + " " : "") + word + " ");
      setTypedWord("");
      setShowAuto(false);
    }
  };

  const oInline = () => document.getElementById(id) as HTMLInputElement | null;

  /** Chèn toán tử / hàm / chip biến vào công thức đã chốt.
   *  Chữ đang gõ dở phải CHỐT TRƯỚC: bấm "×" giữa chừng mà mất chữ vừa gõ thì người khai không
   *  hiểu vì sao. Hàm và mở ngoặc dính liền tham số ("max(" → "max(dai_in"), còn lại tách bằng
   *  khoảng trắng cho tokenizer cắt đúng. */
  const insertVar = (text: string) => {
    const them = text.trim();
    if (!them) return;
    const dangGo = typedWord.trim();
    let goc = value.trimEnd();
    if (dangGo) goc = (goc ? goc + " " : "") + dangGo;
    onChange((goc ? goc + " " : "") + them + (them.endsWith("(") ? "" : " "));
    setTypedWord("");
    setShowAuto(false);
    setTimeout(() => oInline()?.focus(), 10);
  };

  /** Bấm "×" trên một chip → bỏ đúng token đó. `idx` là chỉ số trong CÙNG mảng token mà
   *  `renderFormulaChips` cắt ra từ `value`, nên phải cắt lại y hệt rồi splice. */
  const handleRemoveToken = (idx: number) => {
    const matches = catToken(value);
    if (idx < 0 || idx >= matches.length) return;
    matches.splice(idx, 1);
    onChange(matches.join("").replace(/\s+/g, " ").trim());
  };

  /** Rời ô → chốt nốt chữ đang gõ dở thành chip. Ô inline KHÔNG nằm trong `value`, không chốt thì
   *  gõ "1000" rồi bấm thẳng nút Lưu là số đó bay mất, im lặng. */
  const handleInlineBlur = () => {
    commitTypedWord();
    setShowAuto(false);
  };

  const handleInlineChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const text = e.target.value;

    // Nếu gõ toán tử (+ - * / ()), commit từ trước đó (nếu có) + toán tử
    const lastChar = text.slice(-1);
    if (/^[\+\-\*\/\(\)]$/.test(lastChar)) {
      const wordBefore = text.slice(0, -1).trim();
      let appended = "";
      if (wordBefore) {
        appended += wordBefore + " ";
      }
      appended += (lastChar === "*" ? " * " : lastChar === "/" ? " / " : lastChar === "-" ? " - " : lastChar === "+" ? " + " : lastChar);
      onChange((value ? value + " " : "") + appended);
      setTypedWord("");
      setShowAuto(false);
      return;
    }

    setTypedWord(text);

    // Nếu từ vừa gõ khớp chính xác 1 mã biến trong whitelist -> tự hóa Chip ngay!
    // TRỪ khi còn mã DÀI HƠN bắt đầu bằng chữ này (`so_mau` còn `so_mau_pha`): chốt sớm là người
    // ta không gõ nốt được nữa. Trường hợp đó để Enter/Tab trên gợi ý quyết định.
    const trimmed = text.trim();
    const conMaDaiHon = whitelist.some((v) => v !== trimmed && v.startsWith(trimmed));
    if (whitelist.includes(trimmed) && !conMaDaiHon) {
      onChange((value ? value + " " : "") + trimmed + " ");
      setTypedWord("");
      setShowAuto(false);
      return;
    }

    if (trimmed.length >= 1) {
      setShowAuto(true);
      setAutoIdx(0);
    } else {
      setShowAuto(false);
    }
  };

  const insertSuggestion = (varName: string) => {
    const prefix = value ? value.trimEnd() + " " : "";
    onChange(prefix + varName + " ");
    setTypedWord("");
    setShowAuto(false);
    setTimeout(() => {
      const el = document.getElementById(id) as HTMLInputElement | null;
      el?.focus();
    }, 10);
  };

  const handleInlineKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showAuto && autoSuggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setAutoIdx((i) => Math.min(i + 1, autoSuggestions.length - 1));
        return;
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setAutoIdx((i) => Math.max(i - 1, 0));
        return;
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertSuggestion(autoSuggestions[autoIdx]);
        return;
      } else if (e.key === "Escape") {
        // Đánh dấu phím đã có chủ: Esc ở đây là "đóng danh sách gợi ý", không phải "đóng drawer".
        // Handler của React chạy trước listener trên `document` của drawer, nên dấu này tới kịp.
        e.preventDefault();
        setShowAuto(false);
        return;
      }
    }

    // Enter khi không có gợi ý nào: vẫn phải chốt chữ đang gõ (số "1000" chẳng khớp biến nào),
    // và chặn Enter lọt ra ngoài làm submit drawer.
    if (e.key === "Enter" && typedWord.trim()) {
      e.preventDefault();
      commitTypedWord();
      return;
    }

    if (e.key === "Backspace" && !typedWord) {
        const matches = catToken(value);
      if (matches.length > 0) {
        e.preventDefault();
        matches.pop();
        onChange(matches.join(""));
      }
    }
  };

  const groups = useMemo(() => {
    const sizeVars = ["dai_tp", "rong_tp", "dai_nguyen", "rong_nguyen", "dai_in", "rong_in",
      "dai", "rong"];
    const qtyVars = ["so_luong", "so_tp", "so_mau", "so_mat", "so_kem", "to_dau_vao", "to_sau_in",
      "to_nguyen", "so_con"];
    const priceVars = ["dinh_luong", "don_gia_giay", "don_gia_vat_tu"];
    const daXep = new Set([...sizeVars, ...qtyVars, ...priceVars]);

    return [
      {
        name: "Kích thước",
        key: "size",
        colorClass: "rc-formula__var-tag--size",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect width="20" height="8" x="2" y="8" rx="1.5"/>
            <path d="M6 16v-4M10 16v-2M14 16v-4M18 16v-2"/>
          </svg>
        ),
        vars: whitelist.filter(v => sizeVars.includes(v))
      },
      {
        name: "Số lượng & Sản lượng",
        key: "qty",
        colorClass: "rc-formula__var-tag--qty",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 22V4c0-.5.2-1 .6-1.4C5 2.2 5.5 2 6 2h12c.5 0 1 .2 1.4.6.4.4.6.9.6 1.4v18l-4-2-4 2-4-2-4 2z"/>
            <path d="M8 6h8M8 10h8M8 14h6"/>
          </svg>
        ),
        vars: whitelist.filter(v => qtyVars.includes(v))
      },
      {
        name: "Giá vốn & Đơn giá",
        key: "price",
        colorClass: "rc-formula__var-tag--price",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" x2="12" y1="2" y2="22"/>
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
        ),
        vars: whitelist.filter(v => priceVars.includes(v))
      },
      {
        name: "Khác",
        key: "khac",
        colorClass: "rc-formula__var-tag--qty",
        icon: null,
        vars: whitelist.filter(v => !daXep.has(v)),
      },
    ].filter(g => g.vars.length > 0);
  }, [whitelist]);

  const { valid, error } = useMemo(() => {
    if (!value.trim()) return { valid: true, error: null };

    let openParen = 0;
    for (const char of value) {
      if (char === '(') openParen++;
      if (char === ')') openParen--;
      if (openParen < 0) {
        return { valid: false, error: "Đóng mở ngoặc đơn không hợp lệ" };
      }
    }
    if (openParen !== 0) {
      return { valid: false, error: "Thiếu dấu đóng hoặc mở ngoặc đơn" };
    }

    if (!validVars) return { valid: true, error: null };

    const tokens = catToken(value);

    for (const token of tokens) {
      const trimmed = token.trim();
      if (!trimmed) continue;

      if (
        !validVars.includes(trimmed) &&
        !MATH_FUNCS.includes(trimmed) &&
        !/^\d+(?:\.\d+)?$/.test(trimmed) &&
        !/^[+\-*/(),]$/.test(trimmed)
      ) {
        return {
          valid: false,
          error: `Biến hoặc hàm "${trimmed}" không được hỗ trợ trong hệ thống`
        };
      }
    }

    return { valid: true, error: null };
  }, [value, validVars]);

  return (
    <div className="rc-formula">
      {/* 1. Trình soạn thảo công thức ở trên cùng */}
      <div className="rc-formula__editor-container">
        <div className="rc-formula__editor-header">
          <span className="rc-formula__editor-label">{nhanO}</span>
          <button
            ref={syntaxBtnRef}
            type="button"
            className={`rc-formula__syntax-btn${showSyntax ? " is-open" : ""}`}
            onClick={() => setShowSyntax((s) => !s)}
            aria-expanded={showSyntax}
            title="Phép tính · hàm · biến được hỗ trợ"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M6 8h.01M10 8h.01M14 8h.01M6 12h.01M10 12h.01M14 12h.01M8 16h8" />
            </svg>
            Cú pháp
          </button>
          {showSyntax && (
            <div ref={syntaxPopRef} className="rc-syntax" role="dialog" aria-label="Cú pháp công thức">
              <div className="rc-syntax__head">
                <span>Cú pháp công thức</span>
                <button type="button" className="rc-syntax__x" onClick={() => setShowSyntax(false)} aria-label="Đóng">
                  <XIcon size={12} />
                </button>
              </div>
              <div className="rc-syntax__body">
                <div className="rc-syntax__sec-title">Phép tính</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>+ - * /</code></td><td>cộng · trừ · nhân · chia</td></tr>
                  <tr><td><code>**</code></td><td>lũy thừa</td></tr>
                  <tr><td><code>( )</code></td><td>ngoặc nhóm</td></tr>
                  <tr><td><code>-x</code></td><td>dấu âm đơn</td></tr>
                  <tr><td><code>,</code></td><td>ngăn tham số hàm</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Hàm — đúng 5</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>max(a,b)</code></td><td>lớn nhất — giá sàn</td></tr>
                  <tr><td><code>min(a,b)</code></td><td>nhỏ nhất — giá trần</td></tr>
                  <tr><td><code>round(x)</code></td><td>làm tròn</td></tr>
                  <tr><td><code>ceil(x)</code></td><td>làm tròn lên</td></tr>
                  <tr><td><code>floor(x)</code></td><td>làm tròn xuống</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Biến</div>
                <p className="rc-syntax__note">Bấm chip biến ở dưới để chèn. Kích thước tính bằng <b>mét</b>.</p>
              </div>
            </div>
          )}
        </div>

        {/* Thanh chèn toán tử nhanh */}
        {/* `preventDefault` trên mousedown: giữ con trỏ trong ô inline. Không có nó thì bấm nút là
            ô blur TRƯỚC → chốt chữ đang gõ một lần, rồi `insertVar` chốt thêm lần nữa → chip đôi. */}
        <div className="rc-formula__op-toolbar" onMouseDown={(e) => e.preventDefault()}>
          <span className="rc-formula__op-label">Chèn toán tử:</span>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" + ")} title="Cộng">+</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" - ")} title="Trừ">−</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" * ")} title="Nhân">×</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" / ")} title="Chia">÷</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("(")} title="Mở ngoặc">(</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(")")} title="Đóng ngoặc">)</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("max(")} title="Hàm max">max</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("min(")} title="Hàm min">min</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("round(")} title="Hàm round">round</button>
        </div>

        {/* Ô công thức Chip Tiếng Việt duy nhất (Inline Chip Editor Container) */}
        <div
          className="rc-formula__single-stage"
          onClick={() => {
            const el = document.getElementById(id) as HTMLInputElement | null;
            el?.focus();
          }}
        >
          <div className="rc-formula__chips-wrap">
            {value.trim() ? (
              renderFormulaChips({ value, tra, validVars, whitelist, onRemoveToken: handleRemoveToken })
            ) : null}

            <div className="rc-formula__inline-input-box">
              <input
                id={id}
                className="rc-formula__inline-input"
                value={typedWord}
                onChange={handleInlineChange}
                onKeyDown={handleInlineKeyDown}
                onBlur={handleInlineBlur}
                autoComplete="off"
                spellCheck={false}
                placeholder={value.trim() ? "" : goY}
              />
              {showAuto && autoSuggestions.length > 0 && (
                <div
                  className="rc-formula__autocomplete"
                  role="listbox"
                  onMouseDown={(e) => e.preventDefault()}
                >
                  <div className="rc-formula__autocomplete-head">Gợi ý biến phù hợp:</div>
                  {autoSuggestions.map((v, idx) => (
                    <div
                      key={v}
                      className={`rc-formula__autocomplete-item${idx === autoIdx ? " is-selected" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        insertSuggestion(v);
                      }}
                      onMouseEnter={() => setAutoIdx(idx)}
                    >
                      <div className="rc-formula__autocomplete-main">
                        <span className="rc-formula__autocomplete-name">{tra(v)?.nhan ?? v}</span>
                        <code className="rc-formula__autocomplete-code">{v}</code>
                      </div>
                      {tra(v)?.don_vi && (
                        <span className="rc-formula__autocomplete-unit">{tra(v)!.don_vi}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {!valid && (
        <div className="rc-formula__validation">
          <div className="rc-formula__status rc-formula__status--error">
            <CircleXIcon size={12} sw={3} style={{ marginRight: "6px" }} />
            {error}
          </div>
        </div>
      )}

      {/* 3. Danh sách biến khả dụng (Gom chung 1 nhóm) */}
      <div className="rc-formula__header-bar">
        <span className="rc-formula__header-title">Danh sách biến khả dụng</span>
      </div>

      <div className="rc-formula__all-vars" onMouseDown={(e) => e.preventDefault()}>
        {groups.flatMap((g) => g.vars.map((v) => ({ v, colorClass: g.colorClass }))).map(({ v, colorClass }) => (
          <button
            key={v}
            type="button"
            className={`rc-formula__var-tag ${colorClass}`}
            onClick={() => insertVar(v)}
            // Hover nói đủ BA thứ: ý nghĩa · đơn vị · số ở đâu ra. Thiếu đơn vị thì người khai
            // không biết `dai_in` là mét hay milimét (chỗ đẻ ra công thức lệch thang); thiếu nguồn
            // thì không biết `to_dau_vao` đã gồm bù hao chưa rồi nhân hao thêm lần nữa.
            title={tra(v)
              ? `${tra(v)!.mo_ta}\nĐơn vị: ${tra(v)!.don_vi}\nNguồn: ${tra(v)!.nguon}`
              : v}
          >
            <span className="rc-formula__var-name">{tra(v)?.nhan ?? v}</span>
            <code className="rc-formula__var-code">{v}</code>
          </button>
        ))}
      </div>
    </div>
  );
}
