// Vỏ DRAWER dùng chung — scrim + panel + đầu + chân.
//
// Giữ NGUYÊN bộ tên class `rc-drawer*` nên không đổi một pixel nào so với bản viết tay trước đó.
// Cái được thêm là bốn thứ mà bản cũ thiếu, và thiếu ở đây thì mọi màn dùng drawer đều thiếu:
//
//  1. **Esc đóng.** Bản cũ chỉ đóng được bằng chuột (bấm ✕ hoặc bấm ra nền). `PriceHistoryDrawer`
//     — mã đã xoá 15/08/2026 — thì lại CÓ Esc; tức là cùng một app, hai drawer cư xử khác nhau.
//  2. **Focus vào panel khi mở.** Không đưa focus vào thì bàn phím vẫn đứng ở nút vừa bấm phía
//     sau lớp mờ: Tab một cái là chạy lung tung trong trang nền, người dùng bàn phím lạc hẳn.
//  3. **`role="dialog" aria-modal` đặt trên PANEL, không phải trên SCRIM.** Chỗ cũ khai sai: scrim
//     là lớp phủ trang trí, gán vai hộp thoại cho nó thì trình đọc màn hình coi CẢ lớp phủ là nội
//     dung hộp thoại.
//  4. **Chặn cuộn nền.** Mở drawer rồi lăn chuột là trang phía sau trôi, đóng ra mất chỗ đang đọc.
//
// Di trú 8 call-site drawer còn lại (Kho · Kỹ thuật máy · …) sang đây là việc của đợt sau — mấy
// màn đó đang sửa dở, đụng vào là giẫm chân nhau.
import { useEffect, useId, useRef, type ReactNode } from "react";

import { XIcon } from "../icons";

export function Drawer({
  kicker, title, rong, onClose, foot, children,
}: {
  /** Dòng nhỏ phía trên tiêu đề ("Chỉnh sửa" / "Thêm mới"). */
  kicker?: ReactNode;
  title: ReactNode;
  /** Bản RỘNG (`rc-drawer--formula`) — cho màn có ô công thức / khối quy đổi. */
  rong?: boolean;
  onClose: () => void;
  /** Hàng nút dưới cùng. Để trống thì không render chân. */
  foot?: ReactNode;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();

  // `onClose` là hàm mới mỗi lần render (chỗ gọi khai inline), nên phải đi qua ref: để nó trong
  // deps thì mỗi phím gõ là một lượt gỡ/gắn listener + set lại `overflow` của body.
  const dongRef = useRef(onClose);
  dongRef.current = onClose;

  // Esc đóng + chặn cuộn nền. Gộp một effect: cả hai đều là "trong lúc drawer đang mở".
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Esc là của lớp TRÊN CÙNG, mà drawer gần như luôn là lớp DƯỚI. Ba lớp có thể nằm trên nó,
      // và cả ba đều nghe `keydown` trên `document` — `stopPropagation` KHÔNG chặn được listener
      // cùng một node, nên phải tự nhường:
      //   1. hộp thoại xác nhận (`ConfirmDialog`/`DiscardChangesDialog`, chung lớp `.cdlg-overlay`)
      //      — Esc để bỏ một câu hỏi mà đóng luôn drawer là mất trắng thứ vừa gõ;
      //   2. popover "Cú pháp" và danh sách gợi ý biến của ô công thức — chúng đánh dấu
      //      `preventDefault()` khi nuốt phím (xem `fields/FormulaField.tsx`);
      //   3. `<select>`/`<datalist>` đang bung — trình duyệt tự nuốt, không tới đây.
      if (e.defaultPrevented) return;
      if (document.querySelector(".cdlg-overlay")) return;
      dongRef.current();
    };
    document.addEventListener("keydown", onKey);
    const cuoCu = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = cuoCu;
    };
  }, []);

  // Focus vào panel (không vào ô đầu tiên): nhảy thẳng vào ô nhập thì trình đọc màn hình đọc mỗi
  // cái nhãn ô đó, người dùng không biết vừa mở ra cái gì.
  useEffect(() => { panelRef.current?.focus(); }, []);

  return (
    <div className="rc-drawer__scrim" onClick={onClose}>
      <aside
        ref={panelRef}
        className={`rc-drawer${rong ? " rc-drawer--formula" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="rc-drawer__head">
          <div>
            {kicker != null && <div className="rc-drawer__kicker">{kicker}</div>}
            <h2 className="rc-drawer__title" id={titleId}>{title}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <XIcon />
          </button>
        </header>

        {children}

        {foot != null && <footer className="rc-drawer__foot">{foot}</footer>}
      </aside>
    </div>
  );
}
