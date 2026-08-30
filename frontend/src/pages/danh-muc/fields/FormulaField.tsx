// Ô CÔNG THỨC — gõ ra chip tiếng Việt, có gợi ý biến, kiểm cú pháp và bảng biến khả dụng.
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../../auth/useAuth";
import { ApiError } from "../../../api/client";
import { crud, type CongThucLichSuItem } from "../../../api/rebuildCatalog";
import { catToken, laToanTu } from "../formulaTokens";
import { traBien, useBienCongThuc, type BienCongThuc } from "../bienCongThuc";
import { CircleXIcon, XIcon } from "../icons";
import { nhanThoiGian } from "../nhat-ky/nhatKyNhan";

const MATH_FUNCS = ["ceil", "floor", "round", "max", "min", "if"];

/** Vẽ MỘT chip. Trước đây hàm này tự cắt token từ `value` rồi vẽ cả dãy một lượt — nay ô gõ có
 *  thể nằm CHÈN GIỮA dãy, nên chỗ gọi phải tự cắt đôi mảng token và vẽ từng chip với chỉ số thật.
 *
 *  `onDatCaret(i)` = bấm vào chip thì đưa ô gõ về đúng chỗ đó (nửa trái → đứng trước chip, nửa
 *  phải → đứng sau). Không có nó thì chip chỉ xoá được bằng nút "×", mà nút "×" chỉ mọc trên chip
 *  BIẾN — gõ nhầm dấu "×" ở giữa công thức là phải xoá lùi từ cuối về, đúng chỗ khó chịu 25/08. */
function veChip({
  tok,
  idx,
  tra,
  validVars,
  whitelist,
  onXoa,
  onDatCaret,
}: {
  tok: string;
  idx: number;
  tra: (ma: string) => BienCongThuc | undefined;
  validVars: string[] | null;
  whitelist: string[];
  onXoa?: (index: number) => void;
  onDatCaret?: (index: number) => void;
}) {
  const info = tra(tok);
  const isValidVar = validVars ? validVars.includes(tok) : (whitelist.includes(tok) || !!info);

  // Bấm chip = đặt con trỏ, KHÔNG được để ô gõ mất focus trước đã: blur chốt nốt chữ đang gõ dở
  // thành chip mới, chỉ số chip lúc ấy đã xê dịch ⇒ con trỏ nhảy sai chỗ. `preventDefault` ở
  // mousedown giữ focus lại, phần chốt chữ do chính `onDatCaret` lo (nó biết chèn ở đâu).
  const datCaret = onDatCaret
    ? (e: React.MouseEvent<HTMLSpanElement>) => {
        e.preventDefault();
        e.stopPropagation();
        const r = e.currentTarget.getBoundingClientRect();
        onDatCaret(e.clientX < r.left + r.width / 2 ? idx : idx + 1);
      }
    : undefined;

  // Phải chặn CẢ `click`, không chỉ `mousedown`: nền ô (`rc-formula__single-stage`) có onClick kéo
  // con trỏ về cuối để "bấm chỗ trống là gõ tiếp". Cú bấm chip nổi bọt lên tới đó là vừa đặt con
  // trỏ xong đã bị lôi ngược về cuối — nhìn như bấm chip chẳng ăn thua gì.
  const chanNoi = (e: React.MouseEvent) => e.stopPropagation();
  const chung = { onMouseDown: datCaret, onClick: chanNoi };

  if (isValidVar || info) {
    return (
      <span
        key={idx}
        {...chung}
        className="rc-formula__chip-token rc-formula__chip-token--var"
        title={info ? `${info.nhan} (Mã: ${tok})
Đơn vị: ${info.don_vi}
Nguồn: ${info.nguon}` : `Mã: ${tok}`}
      >
        <span className="rc-formula__chip-token-label">{info?.nhan ?? tok}</span>
        {onXoa && (
          <button
            type="button"
            className="rc-formula__chip-token-del"
            // Cũng phải chặn ở mousedown: để blur chạy trước là chữ đang gõ dở chốt thêm một
            // chip, `idx` xê ra và nút "×" xoá nhầm chip bên cạnh.
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onXoa(idx);
            }}
            onClick={chanNoi}
            title={`Xoá biến ${info?.nhan ?? tok}`}
          >
            ×
          </button>
        )}
      </span>
    );
  }

  if (MATH_FUNCS.includes(tok)) {
    return (
      <span key={idx} {...chung} className="rc-formula__chip-token rc-formula__chip-token--func">
        {tok}
      </span>
    );
  }

  if (/^\d+(?:\.\d+)?$/.test(tok)) {
    return (
      <span key={idx} {...chung} className="rc-formula__chip-token rc-formula__chip-token--num">
        {tok}
      </span>
    );
  }

  if (laToanTu(tok)) {
    const displayOp = tok === "*" ? "×" : tok === "/" ? "÷" : tok === "-" ? "−" : tok;
    return (
      <span key={idx} {...chung} className="rc-formula__chip-token rc-formula__chip-token--op">
        {displayOp}
      </span>
    );
  }

  return (
    <span
      key={idx}
      {...chung}
      className="rc-formula__chip-token rc-formula__chip-token--error"
      title={`Biến "${tok}" chưa hỗ trợ hoặc gõ sai`}
    >
      {tok}
    </span>
  );
}

export function FormulaField({
  value,
  onChange,
  configPrefix,
  bienGoiY,
  an,
  loaiO: loaiOEp,
  nhanO = "Công thức tính giá",
  goY = "Nhập công thức tính giá (vd: dai_tp * rong_tp * don_gia)...",
  id = "formula-textarea",
  recordId = null,
  truocGiaTri = null,
  truocSuaLuc = null,
}: {
  value: string;
  onChange: (v: string) => void;
  configPrefix: string;
  bienGoiY?: string[];
  /** Danh sách mã biến CẦN ẨN khỏi bảng chip gợi ý, dù `loaiO` cho phép — dùng khi biến chỉ có
   *  nghĩa với MỘT số bản ghi trong cùng loại ô. Không ảnh hưởng `bienGoiY`. */
  an?: string[];
  loaiO?: string;
  nhanO?: React.ReactNode;
  goY?: string;
  id?: string;
  /** Id của dòng đang sửa — chỉ có khi đang EDIT (đã lưu). Cần để gọi
   *  `GET /{prefix}/{id}/lich-su-cong-thuc` khi bấm "Xem thêm lịch sử". */
  recordId?: number | null;
  /** Giá trị NGAY TRƯỚC lần sửa gần nhất của CHÍNH ô này (mục 3+7). `null` = chưa từng sửa —
   *  không hiện dòng nhắc. Đọc từ `<field.key>_truoc` trên dòng, xem `routers/catalog_base.py`. */
  truocGiaTri?: string | null;
  /** Thời điểm của lần sửa đó (ISO), đi kèm `truocGiaTri`. */
  truocSuaLuc?: string | null;
}) {
  const isCd = configPrefix.includes("cong-doan");
  const isGiay = configPrefix.endsWith("/giay");
  const isDonVi = configPrefix.includes("don-vi");
  const loaiO = loaiOEp ?? (isDonVi ? "quy_doi" : isCd ? "cong_doan" : isGiay ? "giay" : "vat_tu");
  const tuDien = useBienCongThuc();
  const tra = useMemo(() => traBien(tuDien), [tuDien]);
  const whitelist = useMemo(() => {
    const goc = bienGoiY ?? tuDien.filter((b) => b.loai.includes(loaiO)).map((b) => b.ma);
    return an && an.length ? goc.filter((ma) => !an.includes(ma)) : goc;
  }, [bienGoiY, tuDien, loaiO, an]);
  const validVars = useMemo(
    () => (whitelist.length ? [...whitelist] : null),
    [whitelist],
  );

  // ---- CON TRỎ TRONG DÃY CHIP ----
  // Trước 25/08/2026 ô gõ đóng đinh ở CUỐI: muốn bỏ một dấu hay một biến nằm giữa công thức thì
  // hoặc bấm trúng nút "×" bé xíu (chỉ chip BIẾN mới có), hoặc xoá lùi sạch từ cuối về. Nay ô gõ
  // là một con trỏ chạy được: `caret` = số chip đứng TRƯỚC nó.
  //
  // Token được CHUẨN HOÁ (bỏ khoảng trắng thừa, nối lại bằng đúng một dấu cách) — chỗ xoá chip cũ
  // đã làm vậy từ trước, nay cả ô làm một kiểu để chỉ số chip khớp với chuỗi công thức.
  const toks = useMemo(() => catToken(value).map((t) => t.trim()).filter(Boolean), [value]);
  const [caret, setCaret] = useState(toks.length);
  // Chuỗi do CHÍNH ô này vừa ghi ra. Value đổi mà không phải do mình (mở drawer, cha nạp dữ liệu,
  // bấm nút mẫu) thì con trỏ về cuối; do mình thì giữ nguyên chỗ vừa đặt.
  const tuMinh = useRef<string | null>(null);
  useEffect(() => {
    if (tuMinh.current === value) return;
    setCaret(catToken(value).map((t) => t.trim()).filter(Boolean).length);
  }, [value]);

  /** Ghi công thức mới + đặt con trỏ, và nhớ là do mình ghi. */
  const ghi = (t: string[], caretMoi: number) => {
    const chuoi = t.join(" ");
    tuMinh.current = chuoi;
    onChange(chuoi);
    setCaret(Math.max(0, Math.min(caretMoi, t.length)));
  };

  /** Cắt chuỗi thô thành token sạch (một cú bấm có thể sinh nhiều token: "max(" → max + "("). */
  const catSach = (tho: string) => catToken(tho).map((x) => x.trim()).filter(Boolean);

  /** Chèn vào ĐÚNG chỗ con trỏ — không phải cuối công thức. */
  const chenTaiCaret = (tho: string) => {
    const moi = catSach(tho);
    if (!moi.length) return;
    const t = [...toks];
    t.splice(caret, 0, ...moi);
    ghi(t, caret + moi.length);
  };

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
      chenTaiCaret(word);
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
    const moi = [...catSach(typedWord), ...catSach(them)];
    if (!moi.length) return;
    const t = [...toks];
    t.splice(caret, 0, ...moi);
    ghi(t, caret + moi.length);
    setTypedWord("");
    setShowAuto(false);
    setTimeout(() => oInline()?.focus(), 10);
  };

  /** Bỏ đúng token thứ `idx` (nút "×" trên chip, hoặc Backspace/Delete quanh con trỏ). */
  const handleRemoveToken = (idx: number) => {
    if (idx < 0 || idx >= toks.length) return;
    const t = [...toks];
    t.splice(idx, 1);
    ghi(t, idx < caret ? caret - 1 : caret);
  };

  /** Bấm vào một chip → đưa con trỏ về chỗ đó. Chữ đang gõ dở phải CHỐT trước (không thì nó bay
   *  mất), và chốt xong thì chỉ số chip xê ra — nên vị trí đích phải bù lại. */
  const datCaret = (i: number) => {
    const moi = catSach(typedWord);
    if (moi.length) {
      const t = [...toks];
      t.splice(caret, 0, ...moi);
      ghi(t, caret <= i ? i + moi.length : i);
      setTypedWord("");
      setShowAuto(false);
    } else {
      setCaret(Math.max(0, Math.min(i, toks.length)));
    }
    setTimeout(() => oInline()?.focus(), 0);
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
      chenTaiCaret(appended);
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
      chenTaiCaret(trimmed);
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
    chenTaiCaret(varName);
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

    // ---- ĐIỀU HƯỚNG TRONG DÃY CHIP ----
    // Ô gõ trống ⇒ mũi tên/Backspace/Delete nói về CHIP chứ không về chữ. Còn đang gõ dở thì để
    // yên cho con trỏ chạy trong chữ như mọi ô nhập bình thường.
    const el = e.currentTarget;
    const oDauChu = el.selectionStart === 0 && el.selectionEnd === 0;

    if (!typedWord) {
      if (e.key === "ArrowLeft" && caret > 0) {
        e.preventDefault();
        setCaret(caret - 1);
        return;
      }
      if (e.key === "ArrowRight" && caret < toks.length) {
        e.preventDefault();
        setCaret(caret + 1);
        return;
      }
      if (e.key === "Home" && caret > 0) {
        e.preventDefault();
        setCaret(0);
        return;
      }
      if (e.key === "End" && caret < toks.length) {
        e.preventDefault();
        setCaret(toks.length);
        return;
      }
      if (e.key === "Backspace" && caret > 0) {
        e.preventDefault();
        handleRemoveToken(caret - 1);   // xoá chip BÊN TRÁI con trỏ
        return;
      }
      if (e.key === "Delete" && caret < toks.length) {
        e.preventDefault();
        handleRemoveToken(caret);       // xoá chip BÊN PHẢI con trỏ
        return;
      }
      return;
    }

    // Đang gõ dở mà bấm ← ở đầu chữ: chốt chữ thành chip rồi đứng BÊN TRÁI nó, đúng như ô nhập
    // thường nhảy qua một từ. Không chốt thì chữ vừa gõ bay mất không dấu vết.
    if (e.key === "ArrowLeft" && oDauChu) {
      const moi = catSach(typedWord);
      if (!moi.length) return;
      e.preventDefault();
      const t = [...toks];
      t.splice(caret, 0, ...moi);
      ghi(t, caret);
      setTypedWord("");
      setShowAuto(false);
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
        !laToanTu(trimmed)
      ) {
        return {
          valid: false,
          error: `Biến hoặc hàm "${trimmed}" không được hỗ trợ trong hệ thống`
        };
      }
    }

    return { valid: true, error: null };
  }, [value, validVars]);

  // ---- "LẦN TRƯỚC" (mục 3+7) ----
  // Dòng nhắc đọc thẳng từ props (đã có sẵn trên response, không tốn request). "Xem thêm lịch sử"
  // mới gọi API, và chỉ gọi MỘT LẦN — bấm lại lần hai chỉ đóng/mở, không tải lại.
  const { token } = useAuth();
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<CongThucLichSuItem[] | null>(null);
  const [historyErr, setHistoryErr] = useState<string | null>(null);
  const toggleHistory = () => {
    setShowHistory((s) => !s);
    if (history !== null || historyErr || !token || recordId == null) return;
    crud(configPrefix).lichSuCongThuc(token, recordId)
      .then(setHistory)
      .catch((e) => setHistoryErr(e instanceof ApiError ? e.message : "Không tải được lịch sử."));
  };

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
                <div className="rc-syntax__sec-title">So sánh — chỉ dùng trong if(...)</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>&gt; &lt; &gt;= &lt;=</code></td><td>lớn hơn · nhỏ hơn · ≥ · ≤</td></tr>
                  <tr><td><code>== !=</code></td><td>bằng · khác</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Hàm</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>if(dk, dung, sai)</code></td><td>đúng điều kiện thì lấy vế 1, sai thì vế 2 — lồng được nhiều lớp</td></tr>
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
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" > ")} title="Lớn hơn">&gt;</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" < ")} title="Nhỏ hơn">&lt;</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" >= ")} title="Lớn hơn hoặc bằng">&gt;=</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" <= ")} title="Nhỏ hơn hoặc bằng">&lt;=</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" == ")} title="Bằng">==</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" != ")} title="Khác">!=</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("max(")} title="Hàm max">max</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("min(")} title="Hàm min">min</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("round(")} title="Hàm round">round</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("if(")} title="Hàm if — điều kiện">if</button>
        </div>

        {/* Ô công thức Chip Tiếng Việt duy nhất (Inline Chip Editor Container) */}
        <div
          className="rc-formula__single-stage"
          onClick={() => {
            // Bấm vào KHOẢNG TRỐNG của ô (chip tự chặn cú bấm của mình) = gõ tiếp ở cuối.
            setCaret(toks.length);
            oInline()?.focus();
          }}
        >
          <div className="rc-formula__chips-wrap">
            {/* Dãy chip bị CẮT ĐÔI ngay chỗ con trỏ: chip bên trái · ô gõ · chip bên phải. */}
            {toks.slice(0, caret).map((tok, i) =>
              veChip({ tok, idx: i, tra, validVars, whitelist, onXoa: handleRemoveToken, onDatCaret: datCaret }),
            )}

            <div
              className={`rc-formula__inline-input-box${caret < toks.length ? " rc-formula__inline-input-box--giua" : ""}`}
              // Đứng giữa dãy thì ô gõ chỉ được rộng bằng chữ đang gõ — để nguyên `flex:1` là nó
              // đẩy toàn bộ chip bên phải văng sang lề kia.
              style={caret < toks.length ? { width: `${Math.max(1, typedWord.length)}ch` } : undefined}
              // Bấm vào CHÍNH ô gõ thì không được coi là "bấm chỗ trống": nền ô sẽ kéo con trỏ về
              // cuối, mà con trỏ đang đứng giữa dãy — vừa đặt xong đã bị lôi đi.
              onClick={(e) => e.stopPropagation()}
            >
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

            {toks.slice(caret).map((tok, i) =>
              veChip({ tok, idx: caret + i, tra, validVars, whitelist, onXoa: handleRemoveToken, onDatCaret: datCaret }),
            )}
          </div>
        </div>
      </div>

      {/* 2. "Lần trước" (mục 3+7) — máy chỉ ghi nhận, người tự so sánh và quyết định. */}
      {truocGiaTri != null && (
        <div className="rc-formula__lan-truoc">
          <span className="rc-formula__lan-truoc-nhan">Lần trước:</span>
          <code className="rc-formula__lan-truoc-gt">{truocGiaTri}</code>
          {truocSuaLuc && (
            <span className="rc-formula__lan-truoc-luc">(sửa lúc {nhanThoiGian(truocSuaLuc)})</span>
          )}
          {recordId != null && (
            <button
              type="button"
              className="rc-formula__lich-su-toggle"
              onClick={toggleHistory}
              aria-expanded={showHistory}
            >
              {showHistory ? "Ẩn lịch sử" : "Xem thêm lịch sử"}
            </button>
          )}
        </div>
      )}

      {showHistory && (
        <div className="rc-formula__lich-su">
          {historyErr ? (
            <div className="rc-formula__lich-su-loi">{historyErr}</div>
          ) : history === null ? (
            <div className="rc-formula__lich-su-dang-tai">Đang tải…</div>
          ) : history.length === 0 ? (
            <div className="rc-formula__lich-su-rong">Chưa có lịch sử.</div>
          ) : (
            <ul className="rc-formula__lich-su-list">
              {history.map((h) => (
                <li key={h.id} className="rc-formula__lich-su-item">
                  <span className="rc-formula__lich-su-item-luc">{nhanThoiGian(h.sua_luc)}</span>
                  <code className="rc-formula__lich-su-item-cu">{h.gia_tri_cu ?? "(trống)"}</code>
                  <span className="rc-formula__lich-su-item-mui-ten">→</span>
                  <code className="rc-formula__lich-su-item-moi">{h.gia_tri_moi ?? "(trống)"}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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
