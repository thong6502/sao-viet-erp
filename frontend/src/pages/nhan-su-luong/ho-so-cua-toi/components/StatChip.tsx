// Ô số liệu "của tôi" ở đầu màn (tách từ pages/HoSoCuaToiPage.tsx).
import { Icon, type IconName } from "../../../../components/Icons";
import type { ChipTone, Tai } from "../shared/types";

/** Một ô số liệu "của tôi". Cả thẻ là MỘT nút — ca lỗi đổi vai thành "thử lại" chứ không nhét
 *  nút con vào trong nút (HTML không hợp lệ). */
export function StatChip<T>({ nhan, icon, tt, giaTri, phu, tone, doc, onGo, onThuLai, moTaGo }: {
  nhan: string;
  icon: IconName;
  tt: Tai<T>;
  giaTri: (d: T) => { so: string; donVi: string | null; tien?: boolean };
  phu: (d: T) => string;
  tone: (d: T) => ChipTone;
  doc: (d: T) => string;
  onGo: () => void;
  onThuLai: () => void;
  moTaGo: string;
}) {
  const nhanEl = (
    <span className="mine__stat-label">
      <span className="mine__stat-icon-wrap"><Icon name={icon} size={13} /></span>
      {nhan}
    </span>
  );

  if (tt.tt === "dang-tai") {
    return (
      <div className="mine__stat mine__stat--none" aria-busy="true">
        {nhanEl}
        <span className="mine__skel mine__skel--val" />
        <span className="mine__skel mine__skel--sub" />
      </div>
    );
  }
  if (tt.tt === "loi") {
    return (
      <button type="button" className="mine__stat mine__stat--low" onClick={onThuLai}
              aria-label={`${nhan}: không tải được. Bấm để thử lại.`}>
        {nhanEl}
        <span className="mine__stat-val mine__stat-val--none">–</span>
        <span className="mine__stat-sub mine__stat-sub--err">Không tải được. Bấm để thử lại.</span>
      </button>
    );
  }
  if (tt.tt === "rong") {
    return (
      <button type="button" className="mine__stat mine__stat--none" onClick={onGo}
              aria-label={`${nhan}: chưa có số liệu. ${moTaGo}.`}>
        {nhanEl}
        <span className="mine__stat-val mine__stat-val--none">–</span>
        <span className="mine__stat-sub">{tt.vi_sao}</span>
        <Icon name="arrowRight" size={14} className="mine__stat-go" />
      </button>
    );
  }
  const { so, donVi, tien } = giaTri(tt.du);
  return (
    <button type="button" className={`mine__stat mine__stat--${tone(tt.du)}`} onClick={onGo}
            aria-label={doc(tt.du)}>
      {nhanEl}
      <span className={`mine__stat-val${tien ? " mine__stat-val--money" : ""}`}>
        {so}{donVi && <span className="mine__stat-unit">{donVi}</span>}
      </span>
      <span className="mine__stat-sub">{phu(tt.du)}</span>
      <Icon name="arrowRight" size={14} className="mine__stat-go" />
    </button>
  );
}
