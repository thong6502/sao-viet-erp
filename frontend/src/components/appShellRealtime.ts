/** Tiền tố khoá DÒNG QUYỀN THEO TỔ (`to_sx_<id phòng ban>`, spec 2026-09-14) — cổng Bàn tổ. */
export const TIEN_TO_BAN_TO = "to_sx_";

/** Các khoá dòng tổ người dùng có Xem. Bàn tổ KHÔNG còn gác bằng `san_xuat` (đó là Kế hoạch SX):
 *  có Xem ở ít nhất một dòng là vào được, còn thấy những bàn nào do máy chủ tính (`GET /teams`). */
export function khoaBanTo(readable: ReadonlySet<string>): string[] {
  return [...readable].filter((moduleKey) => moduleKey.startsWith(TIEN_TO_BAN_TO));
}

export function coQuyenBanTo(readable: ReadonlySet<string>): boolean {
  return khoaBanTo(readable).length > 0;
}
