// TẦNG LỆNH của bàn tổ — bản ghi của bàn là LỆNH SX (hoặc BÀI GHÉP), không phải công đoạn rời.
//
// Chủ xưởng chốt 11/09/2026: *"lệnh hoặc bài ghép thôi, chứ không làm sao tôi biết được công đoạn
// đó cho lệnh nào"*. Component này chỉ lo tầng ngoài (dòng lệnh + gấp/mở); công đoạn bên trong do
// nơi gọi vẽ qua `render` — nhờ vậy view "thẻ" và view "danh sách" dùng CHUNG một tầng lệnh mà
// vẫn giữ mật độ hiển thị riêng của mình.
//
// Cắt trang do MÁY CHỦ làm, đếm theo LỆNH (xem `api.sanXuat.workItems`), nên ở đây không có chỗ
// nào cắt mảng — `lenh` nhận vào là đúng một trang.
import { useState, type ReactNode } from "react";
import { Icon } from "../components/Icons";
import type { SxLenhNhom, SxWorkItem } from "../api/client";
import { ngayGio } from "./keHoachSxShared";
import { sxNguonIcon } from "./thsxShared";

/** Khoá ổn định của một lệnh trên bàn (bài ghép và lệnh có thể trùng id). */
function khoaLenh(l: SxLenhNhom): string {
  return `${l.nguon_loai}:${l.lsx_id ?? l.bai_ghep_id ?? 0}`;
}

export function ThsxLenhGroups({
  lenh, selectedId, render,
}: {
  lenh: SxLenhNhom[];
  selectedId: number | null;
  render: (viec: SxWorkItem[]) => ReactNode;
}) {
  // State DƯƠNG (tập lệnh ĐANG MỞ), không phải tập đang gấp: luật cần là "lệnh đầu mở sẵn" —
  // mở bàn ra mà mọi thứ gấp hết thì tổ phải bấm thêm một nhịp mới thấy việc. `null` = chưa ai
  // đụng vào, dùng mặc định; đụng rồi thì tôn trọng đúng những gì người ta đã mở.
  const [moTay, setMoTay] = useState<Set<string> | null>(null);
  const macDinh = new Set(lenh.length ? [khoaLenh(lenh[0])] : []);
  const dangMo = moTay ?? macDinh;

  function bat(k: string) {
    const next = new Set(dangMo);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setMoTay(next);
  }

  if (lenh.length === 0) {
    return <p className="thsx-note">Tổ chưa có lệnh nào được phát hành.</p>;
  }

  return (
    <div className="thsx-lenh__scroll">
      {lenh.map((l) => {
        const k = khoaLenh(l);
        // Lệnh chứa việc đang chọn LUÔN mở: bấm một thẻ ở drawer rồi mà lệnh của nó gấp lại thì
        // người dùng mất dấu chỗ mình đang đứng.
        const mo = dangMo.has(k) || l.cong_viec.some((w) => w.id === selectedId);
        return (
          <section key={k} className={`thsx-lenh${mo ? " thsx-lenh--mo" : ""}`}>
            <button
              type="button" className="thsx-lenh__h" aria-expanded={mo}
              onClick={() => bat(k)}
            >
              <Icon name="chevron" size={13} className={mo ? "" : "thsx-rot-90"} />
              <Icon name={sxNguonIcon(l.nguon_loai)} size={15} className="thsx-lenh__ic" />
              <span className="thsx-lenh__ma thsx-num">{l.nguon_ma || "— không rõ lệnh —"}</span>
              <span className="thsx-lenh__ten">{l.nguon_ten}</span>
              <span className="thsx-lenh__spacer" />
              <span className="thsx-lenh__gio thsx-num">
                {l.som_nhat ? ngayGio(l.som_nhat) : "chưa xếp giờ"}
              </span>
              <span className="thsx-lenh__n thsx-num">{l.so_viec} việc</span>
              <LenhDigest d={l.digest} />
            </button>
            {mo && <div className="thsx-lenh__body">{render(l.cong_viec)}</div>}
          </section>
        );
      })}
    </div>
  );
}

/** Bốn con số trạng thái của lệnh — chỉ hiện con số khác 0, kèm chữ ở `title` cho người đọc màn. */
function LenhDigest({ d }: { d: SxLenhNhom["digest"] }) {
  const o: [keyof SxLenhNhom["digest"], string, string][] = [
    ["running", "Đang chạy", "thsx-lenh__dg--run"],
    ["paused", "Tạm dừng", "thsx-lenh__dg--pause"],
    ["released", "Chờ làm", "thsx-lenh__dg--wait"],
    ["completed", "Hoàn thành", "thsx-lenh__dg--done"],
  ];
  return (
    <span className="thsx-lenh__dg">
      {o.filter(([k]) => d[k] > 0).map(([k, nhan, cls]) => (
        <span key={k} className={cls} title={nhan}>{d[k]}</span>
      ))}
    </span>
  );
}
