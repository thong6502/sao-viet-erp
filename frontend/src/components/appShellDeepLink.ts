// Deep link QR "phiếu công nghệ" (Task 14): `#lsx=<id>&pv=<phien_ban_in>` — chuỗi này do
// `phieu_cong_nghe.noi_dung_qr` (backend) sinh ra và in lên góc tờ phiếu A4. Tổ trưởng quét mã dán
// ở máy → mở đúng hồ sơ lệnh đó trên hệ thống, ĐI QUA cổng đăng nhập (khác `#s=` của
// `PublicScanPage.readScanToken`, tra kho CÔNG KHAI và bắt TRƯỚC cổng — xem docstring `App.tsx`).
// Vì phải qua cổng đăng nhập nên chỗ đọc hash này là `AppShell` (chỉ mount khi ĐÃ có phiên),
// KHÔNG phải `App.tsx`.
//
// Tách khỏi `AppShell.tsx` theo đúng khuôn `appShellRealtime.ts` (`coTheMoKenhSse`): logic phân
// tích chuỗi có một bài canh RIÊNG, không phải dựng cả AppShell (hàng chục lượt gọi API lúc mount)
// chỉ để thử một regex.

export interface LsxDeepLink {
  lsxId: number;
  /** Phiên bản phát hành đang IN TRÊN TỜ GIẤY đã quét. `null` = QR không mang `pv` (phiếu in từ
   *  lúc lệnh chưa có `phien_ban` nào — xem `noi_dung_qr` phía backend); hồ sơ khi đó không có gì
   *  để so, không bày băng cảnh báo. */
  pv: number | null;
}

/** Đọc `window.location.hash` (truyền tay để hàm thuần, dễ viết bài canh — không đụng `window`).
 *  Không phải deep link phiếu công nghệ (không có khoá `lsx`, hoặc id không phải số nguyên dương)
 *  ⇒ `null`, KHÔNG ném lỗi: hash có thể trống, hoặc mang `#s=` của QR tem kho. */
export function docDeepLinkLsx(hash: string): LsxDeepLink | null {
  if (!hash.startsWith("#")) return null;
  const params = new URLSearchParams(hash.slice(1));
  const raw = params.get("lsx");
  if (raw == null) return null;
  // `Number("12abc")` ⇒ NaN nên đã bị `Number.isInteger` chặn; `Number("")` ⇒ 0 nên còn phải tự
  // loại — cả hai đều là id không hợp lệ, không phải "lệnh #0".
  const lsxId = Number(raw);
  if (!Number.isInteger(lsxId) || lsxId <= 0) return null;
  // `pv` chỉ nhận CHUỖI SỐ NGUYÊN THUẦN (`noi_dung_qr` chỉ sinh `str(int)` hoặc rỗng) — gõ tay một
  // giá trị lạ vào URL thì coi như không có, đừng đẩy `NaN`/số âm xuống băng cảnh báo.
  const pvRaw = params.get("pv");
  const pv = pvRaw != null && /^\d+$/.test(pvRaw) ? Number(pvRaw) : null;
  return { lsxId, pv };
}
