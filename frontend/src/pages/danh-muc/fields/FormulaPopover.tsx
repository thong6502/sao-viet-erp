// POPUP công thức — panel NỔI neo vào đúng ô vừa bấm (07/09/2026).
//
// Trước đó ba bảng trong drawer Công đoạn (máy · đầu việc · vật tư của đầu việc) bung công thức
// bằng một HÀNG PHỤ chèn ngay dưới dòng. Cách đó đẩy mọi dòng phía dưới tụt xuống: bấm ô ở cuối
// bảng thì panel mọc ra ngoài tầm nhìn, người khai bấm xong không thấy gì đổi và tưởng ô chết.
//
// Nay panel bay lên trên bảng, bảng đứng yên. Kỹ thuật đi theo đúng lối `components/Select.tsx`
// bản `portal`: treo ở `document.body` + `position: fixed` để KHÔNG bị cắt bởi khung cuộn của
// bảng/drawer, rồi dán lại vào ô mỗi khi cuộn hoặc đổi cỡ cửa sổ.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/** Bề ngang panel. Công thức có `if(...)` được vẽ thụt dòng theo cấp lồng nên hẹp là vỡ thành
 *  nhiều dòng vụn; rộng hơn màn hình thì lại chẳng còn là popup. */
const RONG = 760;
/** Chiều cao ƯỚC LƯỢNG để quyết định lật lên hay xuống — đo bằng chiều cao thật thì phải render
 *  trước rồi mới biết, mà lúc đó panel đã nhảy một nhịp trước mắt người dùng. */
const CAO_UOC = 380;
const KHE = 4;    // khe giữa ô và panel
const LE = 8;     // lề tối thiểu với mép màn hình
/** Dưới ngưỡng này thì panel neo vào ô không còn khai được: ô công thức + hàng toán tử + bảng chip
 *  đã chiếm gần hết, còn lại là một khe cuộn vài dòng. Gặp vậy thì thôi neo, trải hết chiều cao. */
const CAO_DU = 280;

type ViTri = { left: number; width: number; maxHeight: number; top?: number; bottom?: number };

function tinhViTri(el: HTMLElement): ViTri {
  const r = el.getBoundingClientRect();
  const width = Math.min(RONG, window.innerWidth - LE * 2);
  // Neo mép TRÁI vào ô, nhưng không cho tràn mép phải màn hình.
  const left = Math.min(Math.max(LE, r.left), window.innerWidth - LE - width);
  const choDuoi = window.innerHeight - r.bottom - KHE - LE;
  const choTren = r.top - KHE - LE;
  // Cửa sổ thấp (hoặc ô nằm đúng giữa màn): cả hai phía đều chật. Neo vào ô lúc này chỉ ra một khe
  // 200px cuộn được vài dòng — thà bỏ neo, trải panel hết chiều cao và chấp nhận nó che mất ô.
  if (Math.max(choTren, choDuoi) < CAO_DU) {
    return { left, width, top: LE, maxHeight: window.innerHeight - LE * 2 };
  }
  // Lật LÊN khi dưới ô không đủ chỗ mà trên thì rộng hơn — ô ở cuối bảng là trường hợp thường gặp
  // nhất, và cũng chính là chỗ lối bung-hàng-phụ cũ giấu mất panel.
  const len = choDuoi < CAO_UOC && choTren > choDuoi;
  // KẸP chiều cao theo chỗ trống thật của bên đã chọn. Không kẹp thì panel cao hơn khoảng trống sẽ
  // thò đầu ra ngoài mép trên màn hình — mất luôn dòng tiêu đề và ô công thức, đúng phần cần nhìn.
  const maxHeight = len ? choTren : choDuoi;
  return len
    ? { left, width, maxHeight, bottom: window.innerHeight - r.top + KHE }
    : { left, width, maxHeight, top: r.bottom + KHE };
}

export function FormulaPopover({ neo, nhan, onClose, onHuy, children }: {
  /** Ô vừa bấm — panel dán vào nó. `null` = không mở. */
  neo: HTMLElement | null;
  /** Tên ô, dùng làm nhãn cho trình đọc màn hình (và để test gọi tên panel). */
  nhan: string;
  /** CHỐT: đóng panel, giữ nguyên công thức vừa sửa (drawer lưu sau, bằng nút "Lưu thay đổi"). */
  onClose: () => void;
  /** BỎ SỬA: trả ô về công thức lúc mở panel rồi đóng. Không truyền ⇒ nút ✕ chỉ đóng. */
  onHuy?: () => void;
  children: React.ReactNode;
}) {
  const [vt, setViTri] = useState<ViTri | null>(null);
  const popRef = useRef<HTMLDivElement>(null);
  // Chỗ gọi hay truyền `onClose` là hàm mũi tên viết thẳng trong JSX — hàm mới mỗi lần render.
  // Để nó trong mảng phụ thuộc là cứ mỗi nhịp gõ chip lại gỡ/gắn lại cả bộ listener.
  const dongRef = useRef(onClose);
  dongRef.current = onClose;
  const huyRef = useRef(onHuy ?? onClose);
  huyRef.current = onHuy ?? onClose;

  useLayoutEffect(() => {
    if (neo) setViTri(tinhViTri(neo));
  }, [neo]);

  useEffect(() => {
    if (!neo) return;
    const dan = () => {
      // Dòng bị xoá khỏi bảng ⇒ ô neo rời DOM, panel còn lại thì trôi lơ lửng không thuộc về ai.
      if (!neo.isConnected) { dongRef.current(); return; }
      setViTri(tinhViTri(neo));
    };
    // Bấm ra ngoài = CHỐT chứ không bỏ sửa. Gõ nửa chừng rồi lỡ tay bấm trúng nền mà mất sạch công
    // thức thì tệ hơn nhiều so với việc phải bấm thêm ✕ khi thật sự muốn bỏ.
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      // Bấm trong panel: đang khai, không phải ý đóng. Bấm lại CHÍNH ô neo: để nút đó tự bật/tắt,
      // đóng ở đây là nó đóng rồi `onClick` mở lại ngay — nhìn như bấm không ăn.
      if (popRef.current?.contains(t) || neo.contains(t)) return;
      dongRef.current();
    };
    // Esc bắt ở pha BẮT rồi `preventDefault()` — đúng giao kèo nhường phím của
    // `components/Drawer.tsx`: lớp nào nuốt Esc thì đánh dấu, drawer thấy dấu là không tự đóng.
    // Nhường tiếp cho popover "Cú pháp" của chính ô công thức (nó nằm TRONG panel này, đóng panel
    // là nuốt luôn cả nó) — một nhịp Esc chỉ được gỡ MỘT lớp.
    //
    // Esc đi cùng đường với ✕ (BỎ SỬA), không đi với "Xong": ở mọi hộp thoại khác trong màn này Esc
    // đều là "thôi, không làm nữa".
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector(".rc-syntax")) return;
      e.preventDefault();
      huyRef.current();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", dan);
    // `true`: cuộn xảy ra ở khung TRONG drawer, không nổi bọt lên `window`.
    window.addEventListener("scroll", dan, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
      window.removeEventListener("resize", dan);
      window.removeEventListener("scroll", dan, true);
    };
  }, [neo]);

  if (!neo || !vt) return null;
  return createPortal(
    <div
      ref={popRef}
      className="rc-ct-pop"
      role="dialog"
      aria-label={nhan}
      style={{
        position: "fixed",
        left: vt.left, width: vt.width, top: vt.top, bottom: vt.bottom, maxHeight: vt.maxHeight,
      }}
    >
      {/* Nút ✕ KHÔNG nằm ở đây mà ở hàng tên ô bên trong `FormulaField` (prop `onDong`) — dựng thêm
          một thanh tiêu đề cho popup là hai băng xám chồng nhau, tên ô in hai lần. */}
      <div className="rc-ct-pop__body">{children}</div>
      <div className="rc-ct-pop__foot">
        <button type="button" className="rc-ct-pop__ok" onClick={onClose}>Xong</button>
      </div>
    </div>,
    document.body,
  );
}
