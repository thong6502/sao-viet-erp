// VIỆC CHỜ TỔ BẤM trên bàn tổ (spec §11.5) — bàn giao đến chờ nhận · hỗ trợ chéo chờ bên tổ mình ·
// lỗi KCS tổ chưa xem (mở tab KCS là xem). Không còn hộp riêng đầu trang: mỗi việc gắn vào CÔNG ĐOẠN của nó — chấm đỏ
// trên dòng công đoạn, trên đầu lệnh và trên tab ngăn chi tiết nơi bấm. Chấm nghĩa là "còn việc chờ
// bấm", không phải "chưa đọc": xác nhận / đã xem xong là tự tắt, không cần lưu trạng thái đã đọc.
//
// Nguồn duy nhất là `GET /teams/{id}/cho-xac-nhan` (máy chủ lọc theo quyền Xác nhận sản lượng trọn
// tổ) — dòng bảng, đầu lệnh, tab ngăn và ô "chờ xác nhận" cùng đọc một chỗ nên không lệch nhau.
import type { SxChoXacNhan } from "../api/client";
import type { ThsxDrawerTab } from "./ThsxDrawer";

/** Số việc chờ của MỘT công đoạn, theo nơi bấm. */
export interface SxChoCuaViec {
  /** Bàn giao đến chờ nhận — tab "Nhận". */
  nhan: number;
  /** Lỗi KCS chưa xem — tab "KCS". */
  kcs: number;
  /** Hỗ trợ chéo chờ bên tổ mình — mục Hỗ trợ chéo ở tab "Bàn giao & Vật tư". */
  hoTro: number;
}

export function choTheoViec(d: SxChoXacNhan | null): Map<number, SxChoCuaViec> {
  const m = new Map<number, SxChoCuaViec>();
  const lay = (id: number) => {
    let c = m.get(id);
    if (!c) { c = { nhan: 0, kcs: 0, hoTro: 0 }; m.set(id, c); }
    return c;
  };
  for (const b of d?.ban_giao ?? []) lay(b.dich_cong_viec_id).nhan += 1;
  for (const l of d?.kcs_loi ?? []) if (l.cong_viec_id != null) lay(l.cong_viec_id).kcs += 1;
  for (const h of d?.ho_tro ?? []) lay(h.cong_viec_id).hoTro += 1;
  return m;
}

export function tongCho(d: SxChoXacNhan | null): number {
  return (d?.ban_giao.length ?? 0) + (d?.ho_tro.length ?? 0) + (d?.kcs_loi.length ?? 0);
}

/** Việc chờ mà bàn KHÔNG vẽ công đoạn của nó (thường là tổ cho mượn người) — không có dòng nào để
 *  gắn chấm, nên liệt kê riêng khi bật ô "chờ xác nhận". */
export function choNgoaiBan(d: SxChoXacNhan | null): SxChoXacNhan | null {
  if (!d) return null;
  return {
    team_id: d.team_id,
    ban_giao: d.ban_giao.filter((b) => !b.tren_ban),
    ho_tro: d.ho_tro.filter((h) => !h.tren_ban),
    kcs_loi: d.kcs_loi.filter((l) => !l.tren_ban),
  };
}

/** Tab mở sẵn khi bấm một công đoạn: đang có việc chờ thì vào thẳng chỗ bấm. */
export function tabCho(c: SxChoCuaViec | undefined): ThsxDrawerTab {
  if (!c) return "van_hanh";
  if (c.nhan > 0) return "nhan";
  if (c.kcs > 0) return "kcs";
  if (c.hoTro > 0) return "ban_giao";
  return "van_hanh";
}

export function coCho(c: SxChoCuaViec | undefined): boolean {
  return !!c && c.nhan + c.kcs + c.hoTro > 0;
}

/** Câu nói rõ đang chờ gì — tooltip/aria của chấm. */
export function nhanCho(c: SxChoCuaViec | undefined): string {
  if (!c) return "";
  return [
    c.nhan > 0 && `${c.nhan} bàn giao chờ nhận`,
    c.kcs > 0 && `${c.kcs} lỗi KCS chờ xem`,
    c.hoTro > 0 && `${c.hoTro} hỗ trợ chéo chờ xác nhận`,
  ].filter(Boolean).join(" · ");
}

/** Chấm đỏ "còn việc chờ tổ bấm". Không có việc chờ thì không vẽ gì. */
export function ChamCho({ c, nhan }: { c: SxChoCuaViec | undefined; nhan?: string }) {
  if (!coCho(c)) return null;
  const chu = nhan ?? nhanCho(c);
  return <span className="thsx-cho-dot" role="img" aria-label={chu} title={chu} />;
}
