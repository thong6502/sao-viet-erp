// TẦNG LỆNH của bàn tổ — bản ghi của bàn là LỆNH SX (hoặc BÀI GHÉP), không phải công đoạn rời.
//
// Chủ xưởng chốt 11/09/2026: *"lệnh hoặc bài ghép thôi, chứ không làm sao tôi biết được công đoạn
// đó cho lệnh nào"*. Component này chỉ lo tầng ngoài (dòng lệnh + gấp/mở); công đoạn bên trong do
// nơi gọi vẽ qua `render` (hiện chỉ còn view "danh sách" — view "thẻ" đã gỡ 14/09/2026).
//
// Cắt trang do MÁY CHỦ làm, đếm theo LỆNH (xem `api.sanXuat.workItems`), nên ở đây không có chỗ
// nào cắt mảng — `lenh` nhận vào là đúng một trang.
import { useState, type ReactNode } from "react";
import { Icon } from "../components/Icons";
import type { SxLenhNhom, SxWorkItem } from "../api/client";
import { ngayGio } from "./keHoachSxShared";
import { ChamCho, type SxChoCuaViec } from "./thsxChoXacNhan";
import { ThsxDaiRouting } from "./ThsxDaiRouting";
import { sxNguonIcon } from "./thsxShared";

/** Khoá ổn định của một lệnh trên bàn (bài ghép và lệnh có thể trùng id). */
function khoaLenh(l: SxLenhNhom): string {
  return `${l.nguon_loai}:${l.lsx_id ?? l.bai_ghep_id ?? 0}`;
}

/** Gộp việc chờ của mọi công đoạn trong lệnh — chấm đỏ ở dòng lệnh khi lệnh đang gấp. */
function choCuaLenh(l: SxLenhNhom, cho?: ReadonlyMap<number, SxChoCuaViec>): SxChoCuaViec | undefined {
  if (!cho) return undefined;
  const t = { nhan: 0, kcs: 0, hoTro: 0 };
  for (const w of l.cong_viec) {
    const c = cho.get(w.id);
    if (c) { t.nhan += c.nhan; t.kcs += c.kcs; t.hoTro += c.hoTro; }
  }
  return t;
}

export function ThsxLenhGroups({
  lenh, selectedId, render, cho,
}: {
  lenh: SxLenhNhom[];
  selectedId: number | null;
  render: (viec: SxWorkItem[]) => ReactNode;
  /** Việc chờ tổ bấm theo công đoạn (§11.5) — chấm đỏ ở dòng lệnh, lệnh có việc chờ mở sẵn. */
  cho?: ReadonlyMap<number, SxChoCuaViec>;
}) {
  // State DƯƠNG (tập lệnh ĐANG MỞ), không phải tập đang gấp: luật cần là "lệnh đầu mở sẵn" —
  // mở bàn ra mà mọi thứ gấp hết thì tổ phải bấm thêm một nhịp mới thấy việc. `null` = chưa ai
  // đụng vào, dùng mặc định; đụng rồi thì tôn trọng đúng những gì người ta đã mở.
  const [moTay, setMoTay] = useState<Set<string> | null>(null);
  // Lệnh có việc chờ tổ bấm cũng mở sẵn — chấm đỏ nằm trên dòng công đoạn, gấp lại là giấu mất.
  const macDinh = new Set([
    ...(lenh.length ? [khoaLenh(lenh[0])] : []),
    ...lenh.filter((l) => l.cong_viec.some((w) => cho?.has(w.id))).map(khoaLenh),
  ]);
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
        const choLenh = choCuaLenh(l, cho);
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
              {l.khach_hang && (
                <span className="thsx-lenh__khach" title={`Khách hàng: ${l.khach_hang}`}>
                  <Icon name="building" size={12} />
                  <span>{l.khach_hang}</span>
                </span>
              )}
              <ChamCho c={choLenh} />
              <span className="thsx-lenh__spacer" />
              {l.nhan_luc && (
                <span className="thsx-lenh__gio thsx-num" title="Lúc tổ nhận việc (phát hành xuống tổ)">
                  Nhận {ngayGio(l.nhan_luc)}
                </span>
              )}
              <span className="thsx-lenh__n thsx-num">{l.so_viec} việc</span>
              <LenhDigest d={l.digest} />
            </button>
            {mo && (
              <div className="thsx-lenh__body">
                <ThsxDaiRouting dai={l.routing ?? []} />
                {render(l.cong_viec)}
              </div>
            )}
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
