// Kiểu dùng chung của tab Cấu hình lương (tách từ pages/CauHinhLuongTab.tsx).
import type { ComponentKind } from "../../../../../api/client";

export type SubTab = "cochE" | "danhmuc" | "phucap";

export type BracketDraft = {
  key: string;
  id: number | null;
  up_to: number | null;
  rate: number;
};
/** Một bậc PHẠT trễ/sớm trong state cục bộ — `id: null` = bậc mới, chưa POST. */

export type PenaltyDraft = {
  key: string;
  id: number | null;
  up_to_minute: number | null;
  amount: number;
};

export type PendingNav =
  | { kind: "dept"; id: number }
  | { kind: "sub"; sub: SubTab }
  | null;

export type BracketRow = { up_to: number | null; rate: number; note: string };

export type CompDraft = { name: string; kind: ComponentKind; is_taxable: boolean };
