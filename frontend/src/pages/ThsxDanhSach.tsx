// VIEW "DANH SÁCH BẢN GHI" của bàn tổ — thay Gantt bằng bảng khi tổ trưởng muốn đọc/lọc nhanh
// nhiều việc cùng lúc (khác Gantt: không cần đọc vị trí trên trục thời gian). Cùng 3 nhóm với cột
// trái ("Trong cửa sổ" / "Ngoài cửa sổ" / "Chưa định giờ") để không lệch số đếm với `groups.tong`.
// CHỈ ĐỌC — bấm dòng gọi `onPick` giống hệt `ListRow` (mở drawer, dời cửa sổ nếu ngoài cửa sổ).
import { Icon, type IconName } from "../components/Icons";
import type { SxVatTuDinhMuc, SxWorkItem } from "../api/client";
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { num, ngayGio } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
import { sxNguonIcon, sxSerial, ThsxTrangThaiPill } from "./thsxShared";

interface Props {
  timed: SxWorkItem[];
  outWin: SxWorkItem[];
  untimed: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
}

/** Rút gọn định mức vật tư cho một ô bảng: tối đa 2 dòng, còn lại gộp "+N khác". */
function dinhMucText(vt: SxVatTuDinhMuc[]): string {
  if (!vt || vt.length === 0) return "—";
  const head = vt.slice(0, 2).map((v) => {
    const ten = (v.ten || "").trim() || "—";
    const sl = v.so_luong == null ? "" : ` ${num(v.so_luong)}${v.don_vi ? ` ${nhanDonVi(v.don_vi)}` : ""}`;
    return `${ten}${sl}`;
  });
  const rest = vt.length - head.length;
  return rest > 0 ? `${head.join(", ")} +${rest} khác` : head.join(", ");
}

export function ThsxDanhSach({ timed, outWin, untimed, selectedId, onPick }: Props) {
  return (
    <div className="thsx-ds__scroll">
      <DsSection label="Trong cửa sổ" icon="calendar" viec={timed} selectedId={selectedId} onPick={onPick} />
      <DsSection label="Ngoài cửa sổ" icon="history" viec={outWin} selectedId={selectedId} onPick={onPick} />
      <DsSection label="Chưa định giờ" icon="clock" viec={untimed} selectedId={selectedId} onPick={onPick} />
    </div>
  );
}

function DsSection({
  label, icon, viec, selectedId, onPick,
}: {
  label: string;
  icon: IconName;
  viec: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
}) {
  if (viec.length === 0) return null;
  return (
    <div className="thsx-ds__sec">
      <div className="thsx-ds__sech">
        <Icon name={icon} size={12} /> {label}
        <span className="thsx-ds__secn thsx-num">{viec.length}</span>
      </div>
      <table className="thsx-ds__tbl">
        <thead>
          <tr>
            <th>Nguồn</th>
            <th>Công đoạn</th>
            <th>Máy</th>
            <th>Giờ hẹn</th>
            <th className="r">SL vào → ra</th>
            <th>Định mức vật tư</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          {viec.map((w) => (
            <DsRow key={w.id} w={w} selected={w.id === selectedId} onPick={() => onPick(w)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DsRow({ w, selected, onPick }: { w: SxWorkItem; selected: boolean; onPick: () => void }) {
  return (
    <tr
      className={`thsx-ds__row${selected ? " thsx-ds__row--sel" : ""}${w.la_kcs ? " thsx-ds__row--kcs" : ""}`}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      onClick={onPick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}
    >
      <td>
        <span className="thsx-ds__src">
          <Icon name={sxNguonIcon(w.nguon_loai)} size={13} />
          <span className="thsx-num">{sxSerial(w.nguon_ma)}</span>
        </span>
        {w.nguon_ten && <div className="thsx-ds__srcten" title={w.nguon_ten}>{w.nguon_ten}</div>}
      </td>
      <td>
        {w.ten_cong_doan || "—"}
        {w.la_kcs && <span className="thsx-lrow__kcs thsx-ds__kcs">KCS</span>}
        <ChipLoaiBuoc loai_buoc={w.loai_buoc} nha_cung_cap={w.nha_cung_cap} />
        <ChipKhuon can_khuon={!!w.khuon} khuon={{ ...(w.khuon ?? {}), da_nhan: w.khuon_da_nhan }} />
      </td>
      <td>{w.may || "—"}</td>
      <td className="thsx-num">{w.du_kien_bat_dau ? ngayGio(w.du_kien_bat_dau) : "—"}</td>
      <td className="r thsx-num">
        {num(w.so_luong_vao)}{w.don_vi_vao ? ` ${nhanDonVi(w.don_vi_vao)}` : ""}
        {" → "}
        {num(w.so_luong_ra)}{w.don_vi_ra ? ` ${nhanDonVi(w.don_vi_ra)}` : ""}
      </td>
      <td className="thsx-ds__vt" title={dinhMucText(w.dinh_muc_vat_tu)}>{dinhMucText(w.dinh_muc_vat_tu)}</td>
      <td><ThsxTrangThaiPill tt={w.trang_thai} size="xs" /></td>
    </tr>
  );
}
