const REALTIME_MODULES = new Set([
  "bao_gia", "don_hang_ban", "khach_hang", "luong", "san_xuat", "bai_ghep_2",
  // `cham_cong` THAY `di_muon` (26/08/2026): khoá cũ đã gộp về `cham_cong.approve_late_early` và
  // đang bị gỡ khỏi ma trận quyền — để `di_muon` ở đây thì vai MỚI không mở được kênh SSE. Đã đếm:
  // mọi vai đang có `di_muon` đều đã có `cham_cong`, nên đổi không ai mất.
  "xep_lich_2", "kho", "tang_ca", "cham_cong", "thu_mua", "yeu_cau_mua_hang", "ke_toan",
  "phieu_chi", "phieu_thu", "ke_hoach_vat_tu",
]);

export function coTheMoKenhSse(readable: ReadonlySet<string>): boolean {
  return [...readable].some((moduleKey) => REALTIME_MODULES.has(moduleKey));
}
