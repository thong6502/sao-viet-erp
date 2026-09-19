// Việc chờ tổ bấm mà công đoạn KHÔNG nằm trên bàn đang xem (spec §11.5, cờ `tren_ban` của máy chủ).
//
// Việc chờ bình thường gắn vào công đoạn của nó: chấm đỏ trên dòng, trên đầu lệnh, trên tab ngăn chi
// tiết nơi bấm (xem `thsxChoXacNhan.tsx`). Còn lại đúng những việc không có dòng nào để gắn chấm —
// điển hình là tổ CHO MƯỢN người: công đoạn thuộc tổ kia, bàn tổ mình không vẽ nó. Danh sách này chỉ
// hiện khi bật ô "chờ xác nhận" trên thanh lọc, và chỉ khi thật sự có việc như vậy.
//
//  · Hỗ trợ chéo chờ bên mình: xác nhận / từ chối NGAY tại đây — lối vào duy nhất của tổ cho mượn.
//  · Bàn giao đến / KCS báo lỗi ngoài bàn (hiếm — phạm vi xác nhận rộng hơn phạm vi bàn): "Mở" ngăn
//    chi tiết công đoạn, vào thẳng tab Nhận / KCS. Lỗi KCS không có nút "Đã xem" riêng: mở tab KCS
//    là tổ đã xem (18/09/2026, xem `ThsxKetQuaKcs`).
//
// Component không tự gọi API — mọi mặt ghi đi qua callback của controller (toast + nạp lại).
import { useState } from "react";
import type { SxChoXacNhan, SxChoXacNhanBanGiao, SxChoXacNhanHoTro, SxChoXacNhanKcsLoi } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ngay, ngayGio, num } from "./keHoachSxShared";
import { Field } from "./ThsxExecPanels";
import { nhanDonVi } from "./lsxBuoc";

export function ThsxChoNgoaiBan({
  data, busy, onMoBanGiao, onXacNhanHoTro, onHuyHoTro, onMoKcs,
}: {
  data: SxChoXacNhan | null;
  busy: boolean;
  onMoBanGiao: (dichCongViecId: number) => void;
  onXacNhanHoTro: (id: number, version: number) => void;
  onHuyHoTro: (id: number, lyDo: string, version: number) => Promise<boolean>;
  /** Mở ngăn chi tiết của công đoạn bị báo lỗi, tab KCS (có ảnh) — mở là tổ đã xem. */
  onMoKcs: (congViecId: number) => void;
}) {
  const bg = data?.ban_giao ?? [];
  const ht = data?.ho_tro ?? [];
  const kl = data?.kcs_loi ?? [];
  const n = bg.length + ht.length + kl.length;
  if (n === 0) return null;

  return (
    <div className="thsx-hopthu">
      <div className="thsx-hopthu__col">
        <div className="thsx-hopthu__h">
          <Icon name="users" size={14} />
          <span>Chờ tổ bạn xác nhận · công đoạn không nằm trên bàn này</span>
          <span className="thsx-hopthu__n thsx-num">{n}</span>
        </div>
        <ul className="thsx-hopthu__list">
          {kl.map((l) => <KcsLoiRow key={`kcs${l.loi_id}`} l={l} busy={busy} onMo={onMoKcs} />)}
          {bg.map((b) => <BanGiaoRow key={`bg${b.id}`} b={b} busy={busy} onMo={onMoBanGiao} />)}
          {ht.map((h) => (
            <HoTroRow key={`ht${h.id}`} h={h} busy={busy} onXacNhan={onXacNhanHoTro} onHuy={onHuyHoTro} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function KcsLoiRow({
  l, busy, onMo,
}: {
  l: SxChoXacNhanKcsLoi; busy: boolean;
  onMo: (congViecId: number) => void;
}) {
  return (
    <li className="thsx-hopthu__it">
      <div className="thsx-hopthu__main">
        <Icon name="shield" size={14} />
        <span className="thsx-hopthu__ten">KCS báo lỗi</span>
        {l.so_luong > 0 && <span className="thsx-num">{num(l.so_luong)} {nhanDonVi(l.don_vi)}</span>}
      </div>
      <p className="thsx-hopthu__mo">{l.mo_ta || "Lỗi"}</p>
      <p className="thsx-hopthu__mo">
        {[l.lsx_ma, l.ten_cong_doan].filter(Boolean).join(" · ")}
        {l.phat_hien_o ? ` · bắt ở ${l.phat_hien_o}` : ""}
        {l.nguoi_kiem ? ` · ${l.nguoi_kiem}` : ""}{l.luc ? ` · ${ngayGio(l.luc)}` : ""}
        {l.so_anh > 0 ? ` · ${l.so_anh} ảnh` : ""}
      </p>
      <div className="thsx-x-act thsx-x-act--row">
        {l.cong_viec_id != null && (
          <Button variant="accent" onClick={() => onMo(l.cong_viec_id!)} disabled={busy}>
            <Icon name="eye" size={13} /> Mở để xem
          </Button>
        )}
      </div>
    </li>
  );
}

function BanGiaoRow({
  b, busy, onMo,
}: {
  b: SxChoXacNhanBanGiao; busy: boolean; onMo: (dichCongViecId: number) => void;
}) {
  return (
    <li className="thsx-hopthu__it">
      <div className="thsx-hopthu__main">
        <Icon name="truck" size={14} />
        <span className="thsx-hopthu__ten">Bàn giao đến</span>
        <span className="thsx-num">{num(b.so_luong)} {nhanDonVi(b.don_vi)}</span>
      </div>
      <p className="thsx-hopthu__mo">
        {b.nguon_ten}{b.nguon_to_ten ? ` (${b.nguon_to_ten})` : ""} → {b.dich_ten}
        {b.lsx_ma ? ` · ${b.lsx_ma}` : ""}
      </p>
      <div className="thsx-x-act thsx-x-act--row">
        <Button variant="accent" onClick={() => onMo(b.dich_cong_viec_id)} disabled={busy}>
          <Icon name="arrowRight" size={13} /> Mở để xác nhận
        </Button>
      </div>
    </li>
  );
}

function HoTroRow({
  h, busy, onXacNhan, onHuy,
}: {
  h: SxChoXacNhanHoTro; busy: boolean;
  onXacNhan: (id: number, version: number) => void;
  onHuy: (id: number, lyDo: string, version: number) => Promise<boolean>;
}) {
  const [tuChoiMo, setTuChoiMo] = useState(false);
  const [lyDo, setLyDo] = useState("");
  // Nói rõ tổ mình đứng ở bên nào: cho mượn người hay đang cần người.
  const vai = h.cho_ben_goc && !h.cho_ben_thuc_hien
    ? `${h.to_goc_ten ?? "Tổ bạn"} cho mượn người`
    : h.cho_ben_thuc_hien && !h.cho_ben_goc
      ? `${h.to_thuc_hien_ten ?? "Tổ bạn"} nhận người hỗ trợ`
      : "Tổ bạn đứng cả hai bên";
  return (
    <li className="thsx-hopthu__it">
      <div className="thsx-hopthu__main">
        <Icon name="users" size={14} />
        <span className="thsx-hopthu__ten">Hỗ trợ chéo · {h.ho_ten}</span>
        <span className="thsx-num">{ngay(h.ngay_lam_viec)}</span>
      </div>
      <p className="thsx-hopthu__mo">
        {h.to_goc_ten ?? "?"} → {h.ten_cong_doan} ({h.to_thuc_hien_ten ?? "?"}){h.lsx_ma ? ` · ${h.lsx_ma}` : ""}
      </p>
      <p className="thsx-hopthu__mo">{vai}{h.mo_ta ? ` · ${h.mo_ta}` : ""}</p>
      {!tuChoiMo ? (
        <div className="thsx-x-act thsx-x-act--row">
          <Button variant="ghost" onClick={() => setTuChoiMo(true)} disabled={busy}>
            <Icon name="x" size={12} /> Từ chối
          </Button>
          <Button variant="accent" onClick={() => onXacNhan(h.id, h.version)} disabled={busy}>
            <Icon name="check" size={13} /> Xác nhận
          </Button>
        </div>
      ) : (
        <div className="thsx-x-form thsx-x-form--sub">
          <Field label="Lý do từ chối">
            <input type="text" className="thsx-x-in" value={lyDo} onChange={(e) => setLyDo(e.target.value)}
              placeholder="Tuỳ chọn" autoFocus />
          </Field>
          <div className="thsx-x-act">
            <Button variant="ghost" onClick={() => { setTuChoiMo(false); setLyDo(""); }} disabled={busy}>Đóng</Button>
            <Button variant="secondary" disabled={busy}
              onClick={async () => { if (await onHuy(h.id, lyDo.trim(), h.version)) setTuChoiMo(false); }}>
              <Icon name="ban" size={13} /> Từ chối lời mời
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
