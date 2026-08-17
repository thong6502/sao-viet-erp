const REALTIME_MODULES = new Set([
  "bao_gia", "don_hang_ban", "khach_hang", "luong", "san_xuat", "bai_ghep", "bai_ghep_2",
  "xep_lich", "kho", "tang_ca", "di_muon", "thu_mua", "yeu_cau_mua_hang", "ke_toan",
  "phieu_chi", "phieu_thu",
]);

export function coTheMoKenhSse(readable: ReadonlySet<string>): boolean {
  return [...readable].some((moduleKey) => REALTIME_MODULES.has(moduleKey));
}
