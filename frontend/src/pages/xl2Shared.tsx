// Bộ dùng chung của màn XẾP LỊCH CÔNG ĐOẠN 2 (`xep_lich_2`) — tách khỏi controller để cả
// `XepLich2Page` lẫn `Xl2Gantt` cùng dùng mà không vòng import. KHÔNG đụng gì của màn cũ.
//
// Ba thứ ở đây:
//  1) BA MỨC kiểm soát (`XL2_MUC_META` + `Xl2MucPill`) — màn cũ chỉ 2 mức, v2 cần 3 (đặt-lịch /
//     phát-hành / cảnh-báo), mỗi mức MỘT họ màu + icon + chữ (a11y: không chỉ dựa màu).
//  2) TRỤC THỜI GIAN TUYẾN TÍNH — v2 việc CHẠY LIÊN TỤC (finish = start + chiếm-máy theo đồng hồ
//     tường), KHÔNG cắt theo ca ⇒ dùng scale tuyến tính đơn giản, KHÔNG tái dùng `buildScale`
//     (cái đó nén giờ-ngoài-ca, sẽ bẻ gãy thanh v2).
//  3) Nhãn dẫn xuất cho dòng lịch (Dong không mang tên máy/công đoạn).
import type { ReactNode } from "react";
import { Icon, type IconName } from "../components/Icons";
import { wallMinutes, wallOf, fromWall } from "./gantt-time";
import type { Xl2Dong, Xl2Issue, Xl2Muc, Xl2Nguon } from "../api/client";

// ============================ BA MỨC KIỂM SOÁT ==============================
export interface Xl2MucMeta {
  label: string;
  icon: IconName;
  /** class nền/viền của pill + neo màu vùng (định nghĩa trong xep-lich-2.css). */
  cls: string;
  /** thứ tự nặng — số lớn = nặng hơn (để chọn mức "nặng nhất còn tồn"). */
  rank: number;
}

export const XL2_MUC_META: Record<Xl2Muc, Xl2MucMeta> = {
  chan_dat_lich: { label: "Chặn đặt lịch", icon: "ban", cls: "xl2-muc--dat", rank: 3 },
  chan_phat_hanh: { label: "Chặn phát hành", icon: "lock", cls: "xl2-muc--ph", rank: 2 },
  canh_bao: { label: "Cảnh báo", icon: "alert", cls: "xl2-muc--warn", rank: 1 },
};

export const XL2_MUC_ORDER: Xl2Muc[] = ["chan_dat_lich", "chan_phat_hanh", "canh_bao"];

/** Mức NẶNG NHẤT trong danh sách vấn đề (null nếu rỗng) — để tô viền hàng/thanh theo mức nặng nhất. */
export function mucNangNhat(issues: Xl2Issue[] | undefined | null): Xl2Muc | null {
  if (!issues || issues.length === 0) return null;
  let best: Xl2Muc | null = null;
  for (const it of issues) {
    if (best === null || XL2_MUC_META[it.muc].rank > XL2_MUC_META[best].rank) best = it.muc;
  }
  return best;
}

/** Đếm vấn đề theo từng mức. */
export function demTheoMuc(issues: Xl2Issue[]): Record<Xl2Muc, number> {
  const out: Record<Xl2Muc, number> = { chan_dat_lich: 0, chan_phat_hanh: 0, canh_bao: 0 };
  for (const it of issues) out[it.muc] += 1;
  return out;
}

/** Pill mức — r99, LUÔN kèm icon + chữ (người mù màu vẫn phân biệt). `count` tuỳ chọn. */
export function Xl2MucPill({
  muc,
  count,
  size = "sm",
}: {
  muc: Xl2Muc;
  count?: number;
  size?: "sm" | "xs";
}): ReactNode {
  const m = XL2_MUC_META[muc];
  return (
    <span className={`xl2-mucpill ${m.cls} xl2-mucpill--${size}`}>
      <Icon name={m.icon} size={size === "xs" ? 11 : 13} />
      <span>{m.label}</span>
      {count !== undefined && count > 1 ? <b className="xl2-mucpill__n">{count}</b> : null}
    </span>
  );
}

// ============================ TRỤC THỜI GIAN ================================
// Bề rộng cột nhãn lane + chiều cao thanh (LABEL_W=270 hiển thị trọn vẹn thông số máy, BAR_H=34 hiển thị 2 tầng thông tin).
export const LABEL_W = 270;
export const BAR_H = 34;
/** Dải overlay (nhiệt tải máy / đỉnh quân số) neo đáy lane, KHÔNG đè thanh việc (F1). */
export const LANE_OVERLAY_H = 12;
/** thanh (34) + đệm trên (8) + band overlay đáy (12) = 54. Đồng bộ với `--xl2-lane-h` trong CSS. */
export const LANE_H = BAR_H + 8 + LANE_OVERLAY_H;
export const CLUSTER_HEAD_H = 32;

/** Phân nhóm công đoạn để tô màu Chroma Task Capsules: In (Blue) · Sau in (Amber) · Đóng gói (Emerald) · Thuê ngoài (Purple) */
export type Xl2NhomCd = "in" | "sau_in" | "dong_goi" | "thue_ngoai";
export function nhomCongDoan(congDoanTen: string | null | undefined, isNcc?: boolean): Xl2NhomCd {
  if (isNcc) return "thue_ngoai";
  if (!congDoanTen) return "in";
  const s = congDoanTen.toLowerCase();
  if (s.includes("in ") || s.startsWith("in") || s.includes("offset") || s.includes("kỹ thuật số") || s.includes("in màu")) return "in";
  if (s.includes("đóng gói") || s.includes("giao hàng") || s.includes("kiểm phẩm") || s.includes("hoàn thiện") || s.includes("thùng")) return "dong_goi";
  return "sau_in"; // Bế, cán, gấp, xén, dán, ép kim, uv, khâu chỉ...
}

export type Xl2Zoom = "gio" | "ca" | "ngay" | "tuan";
/** px mỗi PHÚT — thanh chạy liên tục nên trục thuần tuyến tính, zoom chỉ đổi mật độ. */
export const XL2_PX_PER_MIN: Record<Xl2Zoom, number> = {
  gio: 1.4,
  ca: 0.55,
  ngay: 0.26,
  tuan: 0.09,
};

export interface Xl2Scale {
  winStart: number; // phút wall
  winEnd: number;
  ppm: number;
  width: number;
  xOf(t: number): number;
  tOf(x: number): number;
}

/** Trục TUYẾN TÍNH: mọi phút đều rộng như nhau (không nén ngoài-ca) — đúng luật chạy-liên-tục v2. */
export function buildLinearScale(winStart: number, winEnd: number, zoom: Xl2Zoom): Xl2Scale {
  const ppm = XL2_PX_PER_MIN[zoom];
  const width = Math.max(0, (winEnd - winStart) * ppm);
  return {
    winStart,
    winEnd,
    ppm,
    width,
    xOf: (t: number) => (Math.max(winStart, Math.min(t, winEnd)) - winStart) * ppm,
    tOf: (x: number) => winStart + Math.max(0, Math.min(x, width)) / ppm,
  };
}

/** Phút wall lúc 00:00 của một ngày "YYYY-MM-DD". */
export function ngayToWall(ymd: string): number {
  const m = ymd.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return NaN;
  return wallOf(+m[1], +m[2], +m[3], 0, 0);
}

/** Ghép phút wall → chuỗi NAIVE "YYYY-MM-DDTHH:MM:00" để gửi server (giữ nguyên giờ nhà máy). */
export function wallToNaive(t: number): string {
  const w = fromWall(t);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${w.y}-${p(w.mo)}-${p(w.d)}T${p(w.hh)}:${p(w.mi)}:00`;
}

export { wallMinutes };

// ============================ NHÃN DẪN XUẤT =================================
/** Khoá thực thể của một dòng — LSX hoặc bài ghép (dùng để gom/nổi cả chuỗi). */
export function dongEntityKey(d: Pick<Xl2Dong, "nguon" | "lsx_id" | "bai_ghep_id">): string {
  return d.nguon === "lsx" ? `lsx:${d.lsx_id ?? 0}` : `in_ghep:${d.bai_ghep_id ?? 0}`;
}

export function entityKey(nguon: Xl2Nguon, id: number): string {
  return `${nguon}:${id}`;
}

/** Nhãn ngắn cho thực thể khi CHƯA có mã (Dong không mang mã) — "LSX#12" / "GB#3".
 *  GIỮ cho tra cứu thô; nhãn HIỂN THỊ nên dùng `dongMa` (có mã thật) hoặc `dongNhanParts`. */
export function dongNhan(d: Pick<Xl2Dong, "nguon" | "lsx_id" | "bai_ghep_id">): string {
  return d.nguon === "lsx" ? `LSX#${d.lsx_id ?? "?"}` : `GB#${d.bai_ghep_id ?? "?"}`;
}

/** Mã HIỂN THỊ của một dòng — ưu tiên mã THẬT backend kèm sẵn (`lsx_ma`/`bai_ghep_ma`, vd
 *  "LSX26-0001" / "GB26-0003"); chỉ lùi về "LSX#id"/"GB#id" khi thiếu (dòng cũ / lỗi tra cứu). */
export function dongMa(
  d: Pick<Xl2Dong, "nguon" | "lsx_id" | "bai_ghep_id" | "lsx_ma" | "bai_ghep_ma">,
): string {
  if (d.nguon === "lsx") return d.lsx_ma ?? `LSX#${d.lsx_id ?? "?"}`;
  return d.bai_ghep_ma ?? `GB#${d.bai_ghep_id ?? "?"}`;
}

/** SỐ SERIAL ngắn cho nhãn thanh Gantt (§10.3): bỏ tiền tố năm dùng-chung "LSX26-"/"GB26-" khiến
 *  mọi thanh nhìn giống hệt ⇒ chỉ lấy phần sau dấu "-" ("LSX26-0012" → "0012"). Thiếu mã thật thì
 *  rơi về "#id". Mã đầy đủ vẫn nằm ở tooltip/aria (nên nhãn ngắn không mất thông tin tra cứu). */
export function dongSerial(
  d: Pick<Xl2Dong, "nguon" | "lsx_id" | "bai_ghep_id" | "lsx_ma" | "bai_ghep_ma">,
): string {
  const raw = d.nguon === "lsx" ? d.lsx_ma : d.bai_ghep_ma;
  if (raw) {
    const i = raw.lastIndexOf("-");
    return i >= 0 && i < raw.length - 1 ? raw.slice(i + 1) : raw;
  }
  const id = d.nguon === "lsx" ? d.lsx_id : d.bai_ghep_id;
  return `#${id ?? "?"}`;
}

/** Đếm SỐ VIỆC trong một tập lane — cluster-head và digest DÙNG CHUNG để "số việc" không lệch nhau
 *  (§10.5). Nhận cấu trúc tối thiểu để khỏi vòng import type `Xl2Lane` (định nghĩa ở Xl2Gantt). */
export function demViecLanes(lanes: { dong: unknown[] }[]): number {
  return lanes.reduce((n, l) => n + l.dong.length, 0);
}

/** Chọn zoom "VỪA KHÍT" (§10.3): tự chọn mật độ trục theo thời lượng việc điển hình trong cửa sổ.
 *  Lấy TRUNG VỊ thời lượng (phút) rồi ngắm một thanh ~130px (đủ chỗ "serial · công đoạn"); chọn nấc
 *  zoom có px/phút gần nhất. Rỗng ⇒ giữ "ngày". Thuần tính từ `ban.dong`, không gọi thêm API. */
export function zoomVuaKhit(durMins: number[]): Xl2Zoom {
  const ds = durMins.filter((m) => Number.isFinite(m) && m > 0).sort((a, b) => a - b);
  if (ds.length === 0) return "ngay";
  const median = ds[Math.floor(ds.length / 2)];
  const wantPpm = 130 / median; // px mục tiêu cho một thanh điển hình
  let best: Xl2Zoom = "ngay";
  let bestDiff = Infinity;
  (Object.keys(XL2_PX_PER_MIN) as Xl2Zoom[]).forEach((z) => {
    const diff = Math.abs(XL2_PX_PER_MIN[z] - wantPpm);
    if (diff < bestDiff) { bestDiff = diff; best = z; }
  });
  return best;
}

/** Ba mảnh nhãn một dòng cho thanh Gantt / panel: MÃ (chính) · CÔNG ĐOẠN (bước đang xếp) ·
 *  SẢN PHẨM (phụ). Lấy từ field dẫn xuất backend đã đính; thiếu thì mã rơi về "#id". */
export interface Xl2NhanParts {
  ma: string;
  congDoan: string | null;
  sanPham: string | null;
}
export function dongNhanParts(
  d: Pick<
    Xl2Dong,
    "nguon" | "lsx_id" | "bai_ghep_id" | "lsx_ma" | "bai_ghep_ma" | "cong_doan_ten" | "ten_san_pham"
  >,
): Xl2NhanParts {
  return { ma: dongMa(d), congDoan: d.cong_doan_ten || null, sanPham: d.ten_san_pham || null };
}

/** Icon phân biệt nguồn: lệnh (workflow) vs bài ghép (layers). */
export function nguonIcon(nguon: Xl2Nguon): IconName {
  return nguon === "lsx" ? "workflow" : "layers";
}
