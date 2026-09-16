// Hộp "Chờ tổ bạn xác nhận" mức trang của Bàn tổ — việc GIỮA HAI TỔ mà bên tổ mình phải bấm.
//
//  · Bàn giao đến chờ nhận: bấm "Mở" → drawer công đoạn đích, tab Bàn giao. Xác nhận ở đó chứ không
//    ở hộp vì người nhận cần thấy mẻ nào đi theo trước khi đứng tên con số.
//  · Hỗ trợ chéo chờ bên mình: xác nhận / từ chối NGAY tại hộp — tổ cho mượn người thường không xem
//    được công đoạn của tổ kia, nên đây là lối vào duy nhất của họ.
//
// Chỉ hiện khi CÓ việc; dữ liệu do máy chủ lọc theo quyền Xác nhận sản lượng trọn tổ trong vùng bàn.
// Component không tự gọi API — mọi mặt ghi đi qua callback của controller (toast + nạp lại).
import { useState } from "react";
import type { SxChoXacNhan, SxChoXacNhanBanGiao, SxChoXacNhanHoTro } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { ngay, num } from "./keHoachSxShared";
import { Field } from "./ThsxExecPanels";
import { nhanDonVi } from "./lsxBuoc";

export function ThsxChoXacNhanBar({
  data, busy, onMoBanGiao, onXacNhanHoTro, onHuyHoTro,
}: {
  data: SxChoXacNhan | null;
  busy: boolean;
  onMoBanGiao: (dichCongViecId: number) => void;
  onXacNhanHoTro: (id: number, version: number) => void;
  onHuyHoTro: (id: number, lyDo: string, version: number) => Promise<boolean>;
}) {
  const bg = data?.ban_giao ?? [];
  const ht = data?.ho_tro ?? [];
  const n = bg.length + ht.length;
  if (n === 0) return null;

  return (
    <div className="thsx-hopthu">
      <div className="thsx-hopthu__col">
        <div className="thsx-hopthu__h">
          <Icon name="users" size={14} />
          <span>Chờ tổ bạn xác nhận</span>
          <span className="thsx-hopthu__n thsx-num">{n}</span>
        </div>
        <ul className="thsx-hopthu__list">
          {bg.map((b) => <BanGiaoRow key={`bg${b.id}`} b={b} busy={busy} onMo={onMoBanGiao} />)}
          {ht.map((h) => (
            <HoTroRow key={`ht${h.id}`} h={h} busy={busy} onXacNhan={onXacNhanHoTro} onHuy={onHuyHoTro} />
          ))}
        </ul>
      </div>
    </div>
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
        <span className="thsx-num">{num(h.ty_le_phan_tram)}% · {ngay(h.ngay_lam_viec)}</span>
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
