export type BaiGhep2TabKey = "chung" | "quycach" | "routing" | "vattu" | "nhatky";

export const BAI_GHEP_2_TABS: { key: BaiGhep2TabKey; label: string }[] = [
  { key: "chung", label: "Thông tin chung" },
  { key: "quycach", label: "Quy cách" },
  { key: "routing", label: "Công đoạn" },
  { key: "vattu", label: "Vật tư" },
  { key: "nhatky", label: "Nhật ký" },
];

export function coTheTaoBai(picked: ReadonlySet<number>): boolean {
  return picked.size >= 2;
}

export function giuLuaChonSauTai(
  picked: ReadonlySet<number>,
  visibleIds: readonly number[],
  query: string,
): Set<number> {
  if (query.trim()) return new Set(picked);
  const available = new Set(visibleIds);
  return new Set([...picked].filter((id) => available.has(id)));
}

export function quyetDinhRealtime(dirty: boolean, tab: BaiGhep2TabKey): {
  stale: boolean;
  refresh: ("detail" | "vattu" | "nhatky")[];
} {
  if (dirty) return { stale: true, refresh: [] };
  const refresh: ("detail" | "vattu" | "nhatky")[] = ["detail"];
  if (tab === "vattu") refresh.push("vattu");
  if (tab === "nhatky") refresh.push("nhatky");
  return { stale: false, refresh };
}

type NodeRef = { lsxId: number; congDoanId: number | null; stepKey: string };
type Verdict = { gop_duoc: boolean; ly_do: string | null } | undefined;

/** Lớp hiển thị chỉ làm sáng điều kiện chắc chắn; server vẫn là cửa kiểm cuối cho DAG/chu trình. */
export function trangThaiUngVien(
  selected: NodeRef,
  candidate: NodeRef,
  verdict: Verdict,
): "selected" | "eligible" | "blocked" {
  if (selected.stepKey === candidate.stepKey) return "selected";
  if (selected.lsxId === candidate.lsxId) return "blocked";
  if (selected.congDoanId == null || selected.congDoanId !== candidate.congDoanId) return "blocked";
  return verdict?.gop_duoc ? "eligible" : "blocked";
}
