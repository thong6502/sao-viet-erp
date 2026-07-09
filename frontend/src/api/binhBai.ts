// API module — Quy tắc bình bài. Types + endpoints riêng file, DÙNG CHUNG `authed` của client.ts
// (silent-refresh nhất quán với toàn app). Wiring P5.
import { authed } from "./client";

// --- Types (mirror backend schemas/quy_tac_binh_bai.py) --------------------
export type LayoutMode = "step_repeat" | "signature" | "nesting";
export type TrangThai = "active" | "inactive";
export type GrainConstraint = "none" | "canh_dai" | "canh_ngan" | "song_song_gay";
export type WorkStyle = "sheetwise" | "work_turn";

export interface VersionConfig {
  layout_mode: LayoutMode;
  side_margin_mm: number;
  tail_colorbar_mm: number;
  gutter_mm: number;
  allow_rotate: boolean;
  grain_constraint: GrainConstraint;
  bleed_default_mm: number;
  allow_gang: boolean;
  min_gutter_mm: number;
  pages_per_sig: number | null;
  work_style: WorkStyle;
  matrix_allowance_mm: number;
  min_pages: number | null;
  max_pages: number | null;
  min_spine_mm: number | null;
  warn_on_grain_violation: boolean;
}

export interface VersionRow extends VersionConfig {
  id: number;
  rule_id: number;
  version_no: number;
  is_current: boolean;
  ghi_chu_version: string | null;
  created_at: string;
}

export interface RuleRow {
  id: number;
  ma: string;
  ten: string;
  mo_ta: string | null;
  trang_thai: TrangThai;
  created_at: string;
  updated_at: string | null;
  current_version: VersionRow | null;
  version_count: number;
}

export interface RuleDetail extends RuleRow {
  versions: VersionRow[];
}

export interface RuleListOut {
  items: RuleRow[];
  total: number;
  page: number;
  size: number;
}

export interface TestBench {
  rong_tp: number;
  dai_tp: number;
  bleed_mm: number | null;
  so_trang: number | null;
  binding: string | null;
  cover_separate: boolean;
  blank_w: number | null;
  blank_h: number | null;
  caliper_mm: number | null;
  rong_ng: number;
  dai_ng: number;
  gsm: number;
  gia_kg: number;
  tho: string;
  gripper_mm: number;
  max_w: number;
  max_h: number;
  min_w: number;
  min_h: number;
  so_luong: number;
  so_mau_truoc: number;
  so_mau_sau: number;
}

export interface PrintSheetOut {
  rong: number;
  dai: number;
  kieu_cat: string;
  per_nguyen: number;
}

export interface WarningOut {
  code: string;
  message: string;
  severity: "error" | "warning";
}

export interface PreviewOut {
  layout_mode: LayoutMode;
  kho_to_in: PrintSheetOut | null;
  don_vi_per_to_in: number;
  to_in_per_nguyen: number;
  tong_don_vi_per_nguyen: number;
  so_kem: number;
  hao_hinh_hoc_pct: number;
  so_to_in: number | null;
  so_to_nguyen: number | null;
  so_tay: number | null;
  danh_sach_tay: Array<Record<string, number>> | null;
  spine_mm: number | null;
  creep_mm: number | null;
  warnings: WarningOut[];
}

export const DEFAULT_CONFIG: VersionConfig = {
  layout_mode: "step_repeat",
  side_margin_mm: 5,
  tail_colorbar_mm: 8,
  gutter_mm: 4,
  allow_rotate: true,
  grain_constraint: "none",
  bleed_default_mm: 3,
  allow_gang: false,
  min_gutter_mm: 4,
  pages_per_sig: null,
  work_style: "sheetwise",
  matrix_allowance_mm: 5,
  min_pages: null,
  max_pages: null,
  min_spine_mm: null,
  warn_on_grain_violation: true,
};

export const DEFAULT_BENCH: TestBench = {
  rong_tp: 90, dai_tp: 53, bleed_mm: 2, so_trang: null, binding: null, cover_separate: false,
  blank_w: null, blank_h: null, caliper_mm: null,
  rong_ng: 430, dai_ng: 650, gsm: 150, gia_kg: 30000, tho: "none",
  gripper_mm: 12, max_w: 0, max_h: 0, min_w: 0, min_h: 0,
  so_luong: 10000, so_mau_truoc: 4, so_mau_sau: 4,
};

// --- API funcs -------------------------------------------------------------
export const binhBaiApi = {
  list(token: string, params: { q?: string; trang_thai?: string; page?: number; size?: number } = {}) {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.trang_thai) qs.set("trang_thai", params.trang_thai);
    if (params.page) qs.set("page", String(params.page));
    if (params.size) qs.set("size", String(params.size));
    const suffix = qs.toString() ? `?${qs}` : "";
    return authed<RuleListOut>(`/api/quy-tac-binh-bai${suffix}`, token);
  },
  get(token: string, id: number) {
    return authed<RuleDetail>(`/api/quy-tac-binh-bai/${id}`, token);
  },
  create(token: string, body: { ma: string; ten: string; mo_ta?: string | null; config: VersionConfig }) {
    return authed<RuleRow>("/api/quy-tac-binh-bai", token, { method: "POST", body: JSON.stringify(body) });
  },
  updateHeader(token: string, id: number, body: { ten: string; mo_ta?: string | null; trang_thai?: string }) {
    return authed<RuleRow>(`/api/quy-tac-binh-bai/${id}`, token, { method: "PUT", body: JSON.stringify(body) });
  },
  createVersion(token: string, id: number, body: { config: VersionConfig; ghi_chu_version?: string | null }) {
    return authed<VersionRow>(`/api/quy-tac-binh-bai/${id}/versions`, token, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  remove(token: string, id: number) {
    return authed<void>(`/api/quy-tac-binh-bai/${id}`, token, { method: "DELETE" });
  },
  preview(token: string, body: { config: VersionConfig; bench: TestBench }) {
    return authed<PreviewOut>("/api/quy-tac-binh-bai/preview", token, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
