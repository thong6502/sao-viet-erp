// Mảnh dùng chung của màn THỰC HIỆN SẢN XUẤT tại tổ (`san_xuat`, "một bàn làm việc").
//
// Ở đây CHỈ những thứ độc lập trình bày, để cả `ThucHienSxPage`, `ThsxTimeline`, `ThsxDrawer`
// cùng dùng mà không vòng import:
//  1) `THSX_TT_META` + `ThsxTrangThaiPill` — pill trạng thái công việc (LUÔN icon + CHỮ, a11y).
//  2) Gom cluster theo `loai_buoc` (máy / năng-lực-tổ / thuê-ngoài) → lane → việc.
//  3) Nhãn dẫn xuất (serial nguồn, icon nguồn) + digest đếm theo trạng thái.
//
// TRỤC THỜI GIAN **tái dùng** `xl2Shared.tsx` (buildLinearScale / XL2_PX_PER_MIN / LABEL_W / BAR_H) —
// KHÔNG chép lại. Việc thực hiện chạy theo đồng hồ tường như v2 nên trục tuyến tính là đúng.
import { Icon, type IconName } from "../components/Icons";
import type { SxWorkItem } from "../api/client";

// ============================ TRẠNG THÁI CÔNG VIỆC ==========================
/** 4 trạng thái enum backend (`models/san_xuat.py`): released / running / paused / completed. */
export type SxTrangThai = "released" | "running" | "paused" | "completed";

export interface ThsxTtMeta {
  label: string;
  icon: IconName;
  /** class họ màu của pill + neo vân/độ-mờ của thanh (định nghĩa trong thuc-hien-sx.css). */
  cls: string;
}

export const THSX_TT_META: Record<SxTrangThai, ThsxTtMeta> = {
  released: { label: "Chờ làm", icon: "clock", cls: "thsx-tt--released" },
  running: { label: "Đang chạy", icon: "play", cls: "thsx-tt--running" },
  paused: { label: "Tạm dừng", icon: "pause", cls: "thsx-tt--paused" },
  completed: { label: "Hoàn thành", icon: "check", cls: "thsx-tt--completed" },
};

/** Meta an toàn cho một chuỗi trạng thái bất kỳ (lùi về "released" nếu lạ). */
export function ttMeta(tt: string): ThsxTtMeta {
  return THSX_TT_META[(tt as SxTrangThai)] ?? THSX_TT_META.released;
}

/** Pill trạng thái — r99, LUÔN kèm icon + chữ (người mù màu vẫn phân biệt). */
export function ThsxTrangThaiPill({ tt, size = "sm" }: { tt: string; size?: "sm" | "xs" }) {
  const m = ttMeta(tt);
  return (
    <span className={`thsx-tt ${m.cls} thsx-tt--${size}`}>
      <Icon name={m.icon} size={size === "xs" ? 11 : 13} />
      <span>{m.label}</span>
    </span>
  );
}

// ============================ NHÃN DẪN XUẤT =================================
/** SERIAL ngắn cho nhãn thanh: bỏ tiền tố năm dùng-chung ("LSX26-0012" → "0012"). Mã đầy đủ vẫn ở
 *  tooltip/aria nên nhãn ngắn không mất thông tin tra cứu. Thiếu mã ⇒ "—". */
export function sxSerial(nguonMa: string | null | undefined): string {
  const raw = (nguonMa ?? "").trim();
  if (!raw) return "—";
  const i = raw.lastIndexOf("-");
  return i >= 0 && i < raw.length - 1 ? raw.slice(i + 1) : raw;
}

/** Icon phân biệt nguồn: lệnh sản xuất (workflow) vs bài ghép (layers); rỗng ⇒ hộp. */
export function sxNguonIcon(nguonLoai: string): IconName {
  if (nguonLoai === "bai_ghep") return "layers";
  if (nguonLoai === "lsx") return "workflow";
  return "box";
}

/** Việc có đủ mốc kế hoạch để đặt lên trục thời gian? Thiếu ⇒ vào lane "chưa định giờ" ở cột trái. */
export function sxCoGio(w: SxWorkItem): boolean {
  return !!w.du_kien_bat_dau && !!w.du_kien_ket_thuc;
}

// ============================ GOM CLUSTER ===================================
export type ThsxClusterKey = "may" | "to" | "thue_ngoai";

export interface ThsxLane {
  key: string;                 // "may:<tên>" | "to:<công đoạn>" | "thue_ngoai:_"
  cluster: ThsxClusterKey;
  label: string;
  viec: SxWorkItem[];
}
export interface ThsxCluster {
  key: ThsxClusterKey;
  label: string;
  icon: IconName;
  /** đơn vị đếm lane ("máy" / "công đoạn" / "đối tác") cho nhãn cluster-head. */
  unit: string;
  lanes: ThsxLane[];
}

function pushLane(map: Map<string, SxWorkItem[]>, key: string, w: SxWorkItem): void {
  const arr = map.get(key) ?? map.set(key, []).get(key)!;
  arr.push(w);
}

/** Gom việc → cluster theo `loai_buoc` (§3):
 *  · "may"        → cụm "Máy", mỗi TÊN MÁY một lane.
 *  · "thue_ngoai" → cụm "Thuê ngoài", một lane.
 *  · còn lại ("to"/rỗng) → cụm "Năng lực tổ", lane theo `ten_cong_doan` (thủ công, không neo máy).
 *  Chỉ nhận việc CÓ GIỜ (đã lọc trước ở controller) — việc thiếu giờ nằm ở cột trái. */
export function buildThsxClusters(items: SxWorkItem[]): ThsxCluster[] {
  const may = new Map<string, SxWorkItem[]>();
  const to = new Map<string, SxWorkItem[]>();
  const ngoai: SxWorkItem[] = [];

  for (const w of items) {
    if (w.loai_buoc === "thue_ngoai") {
      ngoai.push(w);
    } else if (w.loai_buoc === "may") {
      pushLane(may, (w.may || "").trim() || "— chưa rõ máy —", w);
    } else {
      pushLane(to, (w.ten_cong_doan || "").trim() || "— công đoạn —", w);
    }
  }

  const viLabel = (a: [string, SxWorkItem[]], b: [string, SxWorkItem[]]) =>
    a[0].localeCompare(b[0], "vi");

  const out: ThsxCluster[] = [];
  if (may.size) {
    out.push({
      key: "may", label: "Máy", icon: "printer", unit: "máy",
      lanes: [...may.entries()].sort(viLabel).map(([label, viec]): ThsxLane => ({
        key: `may:${label}`, cluster: "may", label, viec,
      })),
    });
  }
  if (to.size) {
    out.push({
      key: "to", label: "Năng lực tổ", icon: "users", unit: "công đoạn",
      lanes: [...to.entries()].sort(viLabel).map(([label, viec]): ThsxLane => ({
        key: `to:${label}`, cluster: "to", label, viec,
      })),
    });
  }
  if (ngoai.length) {
    out.push({
      key: "thue_ngoai", label: "Thuê ngoài", icon: "truck", unit: "đối tác",
      lanes: [{ key: "thue_ngoai:_", cluster: "thue_ngoai", label: "Thuê ngoài", viec: ngoai }],
    });
  }
  return out;
}

/** Đếm SỐ VIỆC trong một tập lane (cluster-head + digest DÙNG CHUNG để không lệch nhau). */
export function demViecLanes(lanes: ThsxLane[]): number {
  return lanes.reduce((n, l) => n + l.viec.length, 0);
}

// ============================ DIGEST ========================================
export interface ThsxDigest {
  tong: number;
  released: number;
  running: number;
  paused: number;
  completed: number;
}

/** Đếm việc theo trạng thái cho dải digest ở subbar (§3 subbar). */
export function sxDigest(items: SxWorkItem[]): ThsxDigest {
  const d: ThsxDigest = { tong: items.length, released: 0, running: 0, paused: 0, completed: 0 };
  for (const w of items) {
    if (w.trang_thai === "running") d.running += 1;
    else if (w.trang_thai === "paused") d.paused += 1;
    else if (w.trang_thai === "completed") d.completed += 1;
    else d.released += 1;
  }
  return d;
}
