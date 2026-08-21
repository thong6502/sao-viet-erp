import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BaiGhepSoDo as SoDo } from "../api/client";
import { LSX_LOAI_BUOC_META } from "../api/client";
import "../pages/dag-routing.css";
import { Icon, type IconName } from "./Icons";
import { ConfirmDialog } from "./ConfirmDialog";
import { ChipGap, classHan, ngay, num } from "../pages/keHoachSxShared";
import { heSoChu, nhanDonVi, phut } from "../pages/lsxBuoc";

type Node = SoDo["nhanh"][number]["buoc"][number];
type BuocChung = SoDo["gop"][number];
export type UngVien = Record<string, { gop_duoc: boolean; ly_do: string | null }>;

const MAU_NHANH = ["#c25e38", "#2563eb", "#059669", "#7c5cbf", "#b7791f", "#be185d"];
/** Màu của một nhánh theo chỉ số `mau` server gán. EXPORT vì tab Quy cách cũng tô theo lệnh —
 *  hai nơi tự chọn bảng màu riêng là cùng một lệnh hai màu, nhìn tưởng hai lệnh. */
export function mauNhanh(i: number): string {
  return MAU_NHANH[i % MAU_NHANH.length];
}
const mau = mauNhanh;

interface Point {
  x: number;
  y: number;
}

export interface BaiGhepDagCanvasProps {
  sd: SoDo;
  /** Đang xem: `step_key` của bước chung, hoặc `lsx_id` của một nhánh. */
  chon: string | number | null;
  onChon: (val: string | number) => void;
  onMoLenh?: (lsxId: number) => void;
  /** Gộp các bước đang chọn thành một lượt chạy chung. */
  onGop?: (stepKeys: string[]) => Promise<unknown>;
  /** Tách lượt chung — số riêng của từng lệnh quay lại nguyên vẹn. */
  onTach?: (gangStepKey: string) => Promise<unknown>;
  /** Mở drawer lập kế hoạch cho lượt chung (tổ · máy · vật tư · ghi chú). */
  onMoBuocChung?: (gangStepKey: string) => void;
  /** Hỏi server bước nào gộp thêm được — kiểm vòng TRƯỚC, nút Gộp không bao giờ bấm rồi bị từ chối. */
  onHoiUngVien?: (stepKeys: string[]) => Promise<UngVien>;
  /** Sửa `con/tờ` ngay trên thẻ lệnh. Đẩy lên cha — sơ đồ KHÔNG tự gọi API ghi. */
  onSuaCon?: (thanhVienId: number, soCon: number) => void;
  canUpdate?: boolean;
}

/** `.dag-node` ở `dag-routing.css` rộng 240px — thẻ ở đây dùng lại đúng bộ class đó để hai màn
 *  nhìn y hệt nhau, nên mọi phép đo phải bám theo con số của nó. */
const CARD_W = 240;
const CARD_H = 148;
const GANG_W = 264;
const HDR_W = 200;
const HDR_H = 128;
const GAP_X = 56;
const ROW_H = 190;
const PAD = 32;
/** Đệm quanh nội dung khi căn vừa, để node ngoài cùng không dính mép khung. */
const PAD_BIEN = 48;
const ZOOM_MIN = 0.35;
const ZOOM_MAX = 2.5;

const kepZoom = (z: number) => Math.min(Math.max(z, ZOOM_MIN), ZOOM_MAX);

/** Biên nội dung theo toạ độ CHƯA nhân zoom. Dùng cho cả phép căn vừa lẫn kích thước vùng cuộn —
 *  mặt vẽ cố định thì thanh cuộn sẽ kéo vào hàng nghìn pixel trắng. */
export function tinhBienNoiDung(pos: Record<string, Point>): { w: number; h: number } {
  let maxX = 0;
  let maxY = 0;
  for (const [id, p] of Object.entries(pos)) {
    const w = id.startsWith("hdr_") ? HDR_W : id.startsWith("gop_") ? GANG_W : CARD_W;
    const h = id.startsWith("hdr_") ? HDR_H : CARD_H;
    maxX = Math.max(maxX, p.x + w);
    maxY = Math.max(maxY, p.y + h);
  }
  return { w: maxX + PAD_BIEN, h: maxY + PAD_BIEN };
}

/** Cột của từng bước, sao cho các bước ĐÃ GỘP nằm thẳng một cột (chúng là MỘT thẻ).
 *
 * Không ép các lệnh cùng số công đoạn: mỗi lệnh dài ngắn tuỳ nó, chỉ điểm gộp mới phải trùng cột.
 * Chạy tăng dần cho tới khi ổn định — giá trị chỉ đi lên và bị chặn trên nên chắc chắn dừng.
 *
 * Trả kèm `hoiTu`: ngân sách vòng lặp là CHẶN CỨNG chứ không phải chứng minh hội tụ. Hết ngân
 * sách mà còn đổi thì các bước cùng nhóm chưa chắc cùng cột — thẻ chung sẽ vẽ đè. Im lặng trả
 * layout sai là kiểu lỗi không ai truy được, nên phải có cờ để màn hình nói ra.
 */
export function tinhCot(sd: SoDo): { cot: Record<string, number>; hoiTu: boolean } {
  const cot: Record<string, number> = {};
  const nhomGop: string[][] = sd.gop.map((g) => g.thanh_vien.map((tv) => tv.lsx_step_key));
  sd.nhanh.forEach((n) => n.buoc.forEach((b, i) => (cot[b.step_key] = i)));

  // Cạnh CHÉO LỆNH cũng phải đẩy cột. Trước đây hàm chỉ nhìn thứ tự MẢNG trong một nhánh, nên
  // "bìa chờ ruột" vẽ ra dây chạy ngược từ phải sang trái — sơ đồ nói sai chiều phụ thuộc.
  // Chỉ nhận cạnh trỏ vào bước CÓ trong sơ đồ; tiền nhiệm ngoài bài đã vẽ riêng thành node mờ.
  const canh: Array<[string, string]> = [];
  sd.nhanh.forEach((n) =>
    n.buoc.forEach((b) =>
      b.phu_thuoc_step_keys.forEach((pk) => {
        if (cot[pk] !== undefined) canh.push([pk, b.step_key]);
      }),
    ),
  );

  const tongBuoc = sd.nhanh.reduce((s, n) => s + n.buoc.length, 0);
  let hoiTu = false;
  for (let vong = 0; vong <= tongBuoc + canh.length; vong++) {
    let doi = false;
    for (const nhom of nhomGop) {
      const c = Math.max(...nhom.map((k) => cot[k] ?? 0));
      for (const k of nhom) {
        if (cot[k] !== c) {
          cot[k] = c;
          doi = true;
        }
      }
    }
    for (const n of sd.nhanh) {
      for (let i = 1; i < n.buoc.length; i++) {
        const truoc = cot[n.buoc[i - 1].step_key] ?? 0;
        if ((cot[n.buoc[i].step_key] ?? 0) <= truoc) {
          cot[n.buoc[i].step_key] = truoc + 1;
          doi = true;
        }
      }
    }
    for (const [truoc, sau] of canh) {
      if ((cot[sau] ?? 0) <= (cot[truoc] ?? 0)) {
        cot[sau] = (cot[truoc] ?? 0) + 1;
        doi = true;
      }
    }
    if (!doi) {
      hoiTu = true;
      break;
    }
  }
  return { cot, hoiTu };
}

/** Thứ tự HÀNG (chỉ số nhánh gốc) sao cho thành viên của cùng một lượt chung nằm liền nhau.
 *
 * Thẻ chung đặt ở hàng nhỏ nhất và cao tới hàng lớn nhất nó đè lên. Bài 3 lệnh mà chỉ hàng 0 và
 * hàng 2 gộp thì thẻ chung phủ luôn thẻ bước của hàng 1 — thẻ dưới mất hẳn, không ai biết nó
 * tồn tại. Xếp liền nhau vừa hết đè vừa nói đúng hơn: nhánh nào chung tờ thì đứng cạnh nhau.
 *
 * Không phải lúc nào cũng xếp liền được (ba lượt chung đan chéo nhau thì bất khả), nên
 * `initialPositions` còn một cửa chặn nữa: thẻ nào vẫn vướng thì đẩy sang phải.
 */
export function sapHang(sd: SoDo): number[] {
  const viTri = new Map<number, number>();
  sd.nhanh.forEach((n, i) => viTri.set(n.lsx_id, i));
  const nhom = sd.gop
    .map((g) =>
      g.thanh_vien
        .map((tv) => viTri.get(tv.lsx_id))
        .filter((i): i is number => i !== undefined),
    )
    .sort((a, b) => b.length - a.length);   // nhóm lớn xếp trước: bị xé thì thiệt hại lớn hơn

  const thuTu: number[] = [];
  const daXep = new Set<number>();
  for (const g of nhom) {
    for (const i of g) {
      if (daXep.has(i)) continue;
      daXep.add(i);
      thuTu.push(i);
    }
  }
  sd.nhanh.forEach((_, i) => {
    if (!daXep.has(i)) thuTu.push(i);
  });
  return thuTu;
}

/** Chiều cao thật của một thẻ chung — nó trải qua các HÀNG nó đè lên. */
function caoGopCua(g: BuocChung, hangCua: (lsxId: number) => number | undefined): number {
  const hang = g.thanh_vien
    .map((tv) => hangCua(tv.lsx_id))
    .filter((i): i is number => i !== undefined);
  if (!hang.length) return CARD_H;
  return (Math.max(...hang) - Math.min(...hang)) * ROW_H + CARD_H;
}

function getStepIcon(node: { loai_buoc: string; nhom: string | null }): IconName {
  if (node.loai_buoc === "thue_ngoai") return "truck";
  switch (node.nhom) {
    case "print":
      return "printer";
    case "prepress":
      return "layers";
    case "finishing":
      return "scissors";
    default:
      return "settings";
  }
}

// `nhanDonVi` + `heSoChu` dùng chung từ `pages/lsxBuoc` — bản riêng ở đây đã gỡ, chép đôi là hai
// chỗ lệch nhau ngay lần đầu ai đó thêm một đơn vị mới.

/** Khối "vào ➔ ra" — dùng lại `.dag-node__flow` chứ không đẻ CSS mới. */
function LuongSoLuong({
  vao,
  ra,
  dvVao,
  dvRa,
}: {
  vao: number | null;
  ra: number | null;
  dvVao: string | null;
  dvRa: string | null;
}) {
  return (
    <div className="dag-node__flow">
      <span>
        {vao == null ? "—" : num(vao)} <small>{nhanDonVi(dvVao)}</small>
      </span>
      <span className="dag-node__flow-arrow">➔</span>
      <span>
        {ra == null ? "—" : num(ra)} <small>{nhanDonVi(dvRa)}</small>
      </span>
    </div>
  );
}

export function BaiGhepDagCanvas({
  sd,
  chon,
  onChon,
  onMoLenh,
  onGop,
  onTach,
  onMoBuocChung,
  onHoiUngVien,
  onSuaCon,
  canUpdate = true,
}: BaiGhepDagCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Viewport State — vị trí do scrollLeft/scrollTop của vùng cuộn quyết, KHÔNG còn state `pan`.
  const [zoom, setZoom] = useState(0.92);
  const [isPanning, setIsPanning] = useState(false);
  const [showGrid, setShowGrid] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  /** Người dùng đã tự chỉnh zoom chưa — nếu rồi thì resize khung không được tự căn đè lên. */
  const tuChinhZoomRef = useRef(false);
  const keoRef = useRef({ mx: 0, my: 0, sl: 0, st: 0 });

  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [draggingNode, setDraggingNode] = useState<{ id: string; startMouse: Point; startPos: Point } | null>(null);

  // --- Chọn để GỘP ----------------------------------------------------------
  const [dangChon, setDangChon] = useState<string[]>([]);
  const [ungVien, setUngVien] = useState<UngVien>({});
  const [dangGop, setDangGop] = useState(false);
  /** Vì sao thẻ vừa bấm không gộp được — thẻ mờ mà bấm vào không nói gì là màn hình câm. */
  const [lyDoChan, setLyDoChan] = useState<string | null>(null);
  /** Thẻ gộp đang mở popup xác nhận tách. */
  const [tachTarget, setTachTarget] = useState<BuocChung | null>(null);
  /** Số thứ tự lượt hỏi ứng viên: chỉ lượt MỚI NHẤT được ghi kết quả. */
  const seqUngVienRef = useRef(0);

  const ngoaiMap = useMemo(() => new Map(sd.ngoai.map((o) => [o.step_key, o])), [sd.ngoai]);
  /** `lsx_step_key → bước chung đang đè lên nó`. */
  const deLen = useMemo(() => {
    const m = new Map<string, BuocChung>();
    sd.gop.forEach((g) => g.thanh_vien.forEach((tv) => m.set(tv.lsx_step_key, g)));
    return m;
  }, [sd.gop]);
  const nodeMap = useMemo(() => {
    const m = new Map<string, Node>();
    sd.nhanh.forEach((n) => n.buoc.forEach((b) => m.set(b.step_key, b)));
    return m;
  }, [sd.nhanh]);
  /** `lsx_id → HÀNG hiển thị`. Khác thứ tự mảng `sd.nhanh`: thành viên của cùng một lượt chung
   *  được xếp liền nhau để thẻ chung không trải qua nhánh lạ (xem `sapHang`). */
  const hangCuaLsx = useMemo(() => {
    const m = new Map<number, number>();
    sapHang(sd).forEach((idxGoc, hang) => {
      const n = sd.nhanh[idxGoc];
      if (n) m.set(n.lsx_id, hang);
    });
    return m;
  }, [sd]);
  const hangCua = useCallback((lsxId: number) => hangCuaLsx.get(lsxId) ?? 0, [hangCuaLsx]);

  /** `step_key → hàng chứa nó`. Cần để vẽ cạnh CHÉO LỆNH giữa hai lệnh trong cùng
   *  bài — vd sách: ruột cắt xong mới vào bìa. Trước đây chỉ vẽ tiền nhiệm NGOÀI bài, nên cạnh
   *  chéo giữa hai thành viên biến mất khỏi sơ đồ dù engine vẫn tính nó. */
  const hangCuaBuoc = useMemo(() => {
    const m = new Map<string, number>();
    sd.nhanh.forEach((n) => n.buoc.forEach((b) => m.set(b.step_key, hangCuaLsx.get(n.lsx_id) ?? 0)));
    return m;
  }, [sd.nhanh, hangCuaLsx]);

  const layout = useMemo(() => tinhCot(sd), [sd]);
  const cot = layout.cot;
  const xCuaCot = useCallback((c: number) => PAD + HDR_W + GAP_X + c * (CARD_W + GAP_X), []);

  const initialPositions = useMemo(() => {
    const pos: Record<string, Point> = {};
    sd.nhanh.forEach((n) => {
      const y = PAD + hangCua(n.lsx_id) * ROW_H;
      pos[`hdr_${n.lsx_id}`] = { x: PAD, y: y + (CARD_H - HDR_H) / 2 };
      n.buoc.forEach((b) => {
        if (deLen.has(b.step_key)) return;   // bước bị đè không có thẻ riêng — thẻ chung thay nó
        pos[`node_${b.step_key}`] = { x: xCuaCot(cot[b.step_key] ?? 0), y };
      });
    });

    // Thẻ chung: cùng cột, trải dọc từ hàng đầu tới hàng cuối mà nó đè lên → nhánh tụ vào trái,
    // toả ra phải, không cần vẽ thêm khung gì.
    const oGop: Array<{ x: number; y: number; cao: number }> = [];
    sd.gop.forEach((g) => {
      const hang = g.thanh_vien
        .map((tv) => hangCuaLsx.get(tv.lsx_id))
        .filter((i): i is number => i !== undefined);
      if (!hang.length) return;
      const c = cot[g.thanh_vien[0].lsx_step_key] ?? 0;
      const p = { x: xCuaCot(c), y: PAD + Math.min(...hang) * ROW_H };
      pos[`gop_${g.step_key}`] = p;
      oGop.push({ ...p, cao: caoGopCua(g, (id) => hangCuaLsx.get(id)) });
    });

    // Cửa chặn cuối: `sapHang` xếp thành viên liền nhau nhưng ba lượt chung đan chéo thì bất khả.
    // Thẻ nào còn nằm trong vùng của một thẻ chung mà không phải thành viên → đẩy sang phải.
    // Để chồng lên nhau là thẻ dưới biến mất, không ai biết bước đó tồn tại.
    for (const [id, p] of Object.entries(pos)) {
      if (id.startsWith("gop_")) continue;
      const w = id.startsWith("hdr_") ? HDR_W : CARD_W;
      const h = id.startsWith("hdr_") ? HDR_H : CARD_H;
      for (const o of oGop) {
        if (p.x < o.x + GANG_W && p.x + w > o.x && p.y < o.y + o.cao && p.y + h > o.y) {
          p.x = o.x + GANG_W + GAP_X;
        }
      }
    }

    // Tiền nhiệm NGOÀI bài (ruột sách của cùng đơn…) → node bóng mờ, đặt lệch lên trên bước cần nó.
    sd.nhanh.forEach((n) => {
      const y = PAD + hangCua(n.lsx_id) * ROW_H;
      n.buoc.forEach((b) => {
        b.phu_thuoc_step_keys.forEach((pk) => {
          if (!ngoaiMap.has(pk) || pos[`ngoai_${pk}`]) return;
          pos[`ngoai_${pk}`] = { x: xCuaCot(Math.max(0, (cot[b.step_key] ?? 0) - 1)), y: y - 72 };
        });
      });
    });
    return pos;
  }, [sd, cot, deLen, ngoaiMap, xCuaCot, hangCua, hangCuaLsx]);

  useEffect(() => {
    setPositions(initialPositions);
  }, [initialPositions]);

  const caoGop = useCallback(
    (g: BuocChung) => caoGopCua(g, (id) => hangCuaLsx.get(id)),
    [hangCuaLsx],
  );

  const bien = useMemo(() => {
    const b = tinhBienNoiDung(positions);
    // `tinhBienNoiDung` giả định mọi thẻ cao `CARD_H`; thẻ chung trải dọc nên phải cộng bù.
    let maxY = b.h;
    sd.gop.forEach((g) => {
      const p = positions[`gop_${g.step_key}`];
      if (p) maxY = Math.max(maxY, p.y + caoGop(g) + PAD_BIEN);
    });
    return { w: b.w, h: maxY };
  }, [positions, sd.gop, caoGop]);

  /** Căn vừa THẬT: đo khung, đo nội dung, chọn tỉ lệ nhỏ hơn giữa hai chiều rồi cuộn về góc.
   *  Không phóng quá 100% — bài nhỏ mà kéo giãn ra thì thẻ vỡ nét.
   *  `clientWidth/Height` ĐÃ GỒM đệm của vùng cuộn, phải trừ ra mới đúng chỗ vẽ được. */
  const canVua = useCallback(() => {
    const el = containerRef.current;
    if (!el || bien.w <= PAD_BIEN || bien.h <= PAD_BIEN) return;
    const cs = getComputedStyle(el);
    const rong = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const cao = el.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    if (rong <= 0 || cao <= 0) return;
    setZoom(kepZoom(Math.min(rong / bien.w, cao / bien.h, 1)));
    el.scrollTo({ left: 0, top: 0 });
  }, [bien]);

  const handleResetLayout = () => {
    setPositions(initialPositions);
    tuChinhZoomRef.current = false;
    canVua();
  };

  const handleFitView = () => {
    tuChinhZoomRef.current = false;
    canVua();
  };

  const doiZoom = (tinh: (z: number) => number) => {
    tuChinhZoomRef.current = true;
    setZoom((z) => kepZoom(tinh(z)));
  };

  // Căn vừa lúc mở màn và mỗi khi dữ liệu sơ đồ đổi (bien đổi theo positions).
  useEffect(() => {
    if (tuChinhZoomRef.current) return;
    canVua();
  }, [canVua]);

  // Khung đổi kích thước (mở/đóng sidebar, xoay màn) → căn lại, trừ khi người dùng đã tự chỉnh zoom.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      if (!tuChinhZoomRef.current) canVua();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [canVua]);

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!isFullscreen) {
      if (containerRef.current.requestFullscreen) containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  // Lăn thường / Shift+lăn để cho chính vùng cuộn lo (cuộn hết mới nhả sang trang). Ctrl/Cmd+lăn thì
  // thu phóng — phải gắn tay với passive:false, vì onWheel của React là listener thụ động nên
  // preventDefault bị bỏ qua và trình duyệt zoom cả trang thay vì zoom sơ đồ.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      tuChinhZoomRef.current = true;
      setZoom((prev) => kepZoom(prev * (e.deltaY < 0 ? 1.08 : 0.92)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // --- Chọn / gộp -----------------------------------------------------------
  const huyChon = useCallback(() => {
    seqUngVienRef.current += 1;    // câu trả lời đang bay về sẽ bị bỏ, không sáng lại thẻ nào
    setDangChon([]);
    setUngVien({});
    setLyDoChan(null);
  }, []);

  useEffect(() => {
    if (!dangChon.length) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") huyChon();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dangChon.length, huyChon]);

  // Sơ đồ nạp lại (gộp/tách xong) → tập đang chọn không còn nghĩa gì.
  useEffect(() => {
    huyChon();
  }, [sd, huyChon]);

  /** Hỏi server sau mỗi lần đổi tập chọn. Kiểm vòng ở server vì nó mới thấy cạnh chéo lệnh.
   *
   *  Đánh số lượt hỏi: bấm nhanh thì câu trả lời có thể về KHÔNG theo thứ tự gửi, và câu của tập
   *  chọn cũ mà về sau sẽ sáng nhầm thẻ cho tập mới — bấm Gộp là ăn 409, đúng cái mà "kiểm TRƯỚC"
   *  sinh ra để tránh. Chỉ lượt mới nhất được ghi kết quả.
   */
  const capNhatUngVien = useCallback(
    async (keys: string[]) => {
      const seq = ++seqUngVienRef.current;
      if (!onHoiUngVien || !keys.length) {
        setUngVien({});
        return;
      }
      try {
        const kq = await onHoiUngVien(keys);
        if (seq === seqUngVienRef.current) setUngVien(kq);
      } catch {
        if (seq === seqUngVienRef.current) setUngVien({});   // hỏi hụt thì thà đừng sáng thẻ nào
      }
    },
    [onHoiUngVien],
  );

  /** Bấm một thẻ bước = CHỌN ĐỂ GỘP, không mở popup.
   *
   * Trước đây bấm thẻ là mở popup chi tiết lệnh; giờ một-bấm đã mang nghĩa khác nên popup sẽ đè
   * ngay lên thao tác đang làm. Muốn xem lệnh thì bấm thẻ lệnh đầu hàng, hoặc nháy đúp.
   *
   * Tính tập mới NGOÀI updater của `setDangChon`. Gọi `capNhatUngVien` bên trong updater là gửi
   * ĐÔI request dưới StrictMode (React chạy updater hai lần để soi hàm thuần) — mỗi cú bấm hai
   * lượt hỏi server, và hai lượt ấy còn đua nhau ghi `ungVien`.
   */
  const hopDieuKienGop = useCallback((node: Node) => {
    if (!dangChon.length) return true;
    const dau = nodeMap.get(dangChon[0]);
    if (!dau || dau.cong_doan_id == null || dau.cong_doan_id !== node.cong_doan_id) return false;
    const lsxDau = sd.nhanh.find((n) => n.buoc.some((b) => b.step_key === dau.step_key))?.lsx_id;
    const lsxNode = sd.nhanh.find((n) => n.buoc.some((b) => b.step_key === node.step_key))?.lsx_id;
    return lsxDau != null && lsxNode != null && lsxDau !== lsxNode;
  }, [dangChon, nodeMap, sd.nhanh]);

  const bamThe = useCallback(
    (node: Node) => {
      if (!canUpdate || !onGop || deLen.has(node.step_key)) return;
      const truoc = dangChon;
      let sau: string[];
      if (truoc.includes(node.step_key)) sau = truoc.filter((k) => k !== node.step_key);
      else if (!truoc.length) sau = [node.step_key];
      else if (ungVien[node.step_key]?.gop_duoc && hopDieuKienGop(node)) sau = [...truoc, node.step_key];
      else if (ungVien[node.step_key]) {
        // Mờ vì sẽ sinh vòng: KHÔNG cho chọn, nhưng phải nói ra. Trước đây chỗ này `return` câm —
        // người dùng bấm mãi không hiểu vì sao thẻ không nhận.
        setLyDoChan(
          ungVien[node.step_key].ly_do
            ?? (!hopDieuKienGop(node) ? "Chỉ gộp bước cùng công đoạn ở một lệnh khác." : null)
            ?? `Không gộp "${node.ten}" vào lượt đang chọn được — sẽ sinh vòng phụ thuộc.`,
        );
        return;
      } else sau = [node.step_key];                          // khác công đoạn → chọn lại từ đầu
      setLyDoChan(null);
      setDangChon(sau);
      void capNhatUngVien(sau);
    },
    [canUpdate, onGop, deLen, ungVien, dangChon, capNhatUngVien, hopDieuKienGop],
  );

  /** Nhánh nào đang được tô đậm: nhánh người bấm, hoặc nhánh của bước đầu tiên đang chọn để gộp. */
  const lsxDangChon = useMemo(() => {
    if (typeof chon === "number") return chon;
    if (!dangChon.length) return null;
    return sd.nhanh.find((n) => n.buoc.some((b) => b.step_key === dangChon[0]))?.lsx_id ?? null;
  }, [chon, dangChon, sd.nhanh]);

  const gopNgay = async () => {
    if (!onGop || dangChon.length < 2) return;
    setDangGop(true);
    try {
      await onGop(dangChon);
      huyChon();
    } finally {
      setDangGop(false);
    }
  };

  const tachNgay = (g: BuocChung) => {
    if (!onTach) return;
    if (g.da_lap_ke_hoach) {
      setTachTarget(g);
    } else {
      void onTach(g.step_key);
    }
  };

  const tenDangChon = dangChon.length ? nodeMap.get(dangChon[0])?.ten ?? "" : "";

  // --- Kéo thả --------------------------------------------------------------
  const handleMouseDownCanvas = (e: React.MouseEvent) => {
    const el = containerRef.current;
    if (!el) return;
    const t = e.target as HTMLElement;
    if (t !== el && !t.classList.contains("bgsd-canvas__bg")) return;
    huyChon();                                    // bấm nền trống = huỷ chọn
    setIsPanning(true);
    keoRef.current = { mx: e.clientX, my: e.clientY, sl: el.scrollLeft, st: el.scrollTop };
  };

  const handleStartDragNode = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const currentPos = positions[id] || { x: 0, y: 0 };
    setDraggingNode({ id, startMouse: { x: e.clientX, y: e.clientY }, startPos: { ...currentPos } });
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isPanning) {
        // Kéo nền = cuộn ngược chiều tay, không đụng tới zoom nên không chia cho zoom.
        const el = containerRef.current;
        if (el) {
          el.scrollLeft = keoRef.current.sl - (e.clientX - keoRef.current.mx);
          el.scrollTop = keoRef.current.st - (e.clientY - keoRef.current.my);
        }
      } else if (draggingNode) {
        const dx = (e.clientX - draggingNode.startMouse.x) / zoom;
        const dy = (e.clientY - draggingNode.startMouse.y) / zoom;
        setPositions((prev) => ({
          ...prev,
          [draggingNode.id]: {
            x: Math.max(10, draggingNode.startPos.x + dx),
            y: Math.max(10, draggingNode.startPos.y + dy),
          },
        }));
      }
    };
    const handleMouseUp = () => {
      setIsPanning(false);
      setDraggingNode(null);
    };
    if (isPanning || draggingNode) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isPanning, draggingNode, zoom]);

  const drawBezier = (p1: Point, p2: Point) => {
    const gapX = p2.x - p1.x;
    const dx = gapX > 0 ? Math.min(gapX * 0.45, 56) : Math.max(Math.abs(gapX) * 0.45, 32);
    return `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y}, ${p2.x - dx} ${p2.y}, ${p2.x} ${p2.y}`;
  };

  /** Mép phải / mép trái của một bước ở ĐÚNG toạ độ hiển thị thực tế của thẻ.
   *  Bước đã gộp thì mép nằm ở thẻ chung theo đúng hàng của nhánh đó trên thẻ chung. */
  const mep = useCallback(
    (stepKey: string, ben: "trai" | "phai", _yNhanh: number): Point | null => {
      const g = deLen.get(stepKey);
      if (g) {
        const p = positions[`gop_${g.step_key}`];
        if (!p) return null;
        const minHang = Math.min(...g.thanh_vien.map((tv) => hangCuaLsx.get(tv.lsx_id) ?? 0));
        const currentHang = hangCuaBuoc.get(stepKey) ?? minHang;
        const yOffset = (currentHang - minHang) * ROW_H + CARD_H / 2;
        return { x: ben === "trai" ? p.x : p.x + GANG_W, y: p.y + yOffset };
      }
      const p = positions[`node_${stepKey}`];
      if (!p) return null;
      return { x: ben === "trai" ? p.x : p.x + CARD_W, y: p.y + CARD_H / 2 };
    },
    [deLen, positions, hangCuaLsx, hangCuaBuoc],
  );

  return (
    <div className={`bgsd-canvas-wrap ${showGrid ? "has-dot-grid" : ""}`}>
      <div className="bgsd-canvas__toolbar">
        <button type="button" className="bgsd-tb-btn" onClick={() => doiZoom((z) => z - 0.12)} title="Thu nhỏ" aria-label="Thu nhỏ sơ đồ">
          <Icon name="minus" size={14} />
        </button>
        <span className="bgsd-tb-zoom" role="status" aria-label={`Tỉ lệ ${Math.round(zoom * 100)} phần trăm`}>
          {Math.round(zoom * 100)}%
        </span>
        <button type="button" className="bgsd-tb-btn" onClick={() => doiZoom((z) => z + 0.12)} title="Phóng to" aria-label="Phóng to sơ đồ">
          <Icon name="plus" size={14} />
        </button>
        <div className="bgsd-tb-divider" />
        <button type="button" className="bgsd-tb-btn bgsd-tb-btn--text" onClick={handleFitView} title="Thu vừa tầm mắt">
          <Icon name="maximize" size={13} /> Căn vừa
        </button>
        <button type="button" className="bgsd-tb-btn bgsd-tb-btn--text" onClick={handleResetLayout} title="Xếp lại sơ đồ">
          <Icon name="rotateCcw" size={13} /> Sắp xếp lại
        </button>
        <div className="bgsd-tb-divider" />
        <button
          type="button"
          className={`bgsd-tb-btn ${showGrid ? "is-active" : ""}`}
          onClick={() => setShowGrid((g) => !g)}
          title="Bật/Tắt lưới chấm"
          aria-label="Bật hoặc tắt lưới chấm nền"
          aria-pressed={showGrid}
        >
          <Icon name="grid" size={14} />
        </button>
        <button
          type="button"
          className="bgsd-tb-btn"
          onClick={handleToggleFullscreen}
          title="Toàn màn hình"
          aria-label={isFullscreen ? "Thoát toàn màn hình" : "Xem sơ đồ toàn màn hình"}
        >
          <Icon name="fullscreen" size={14} />
        </button>
        {/* Phép xếp cột hết ngân sách vòng lặp mà chưa ổn định → các bước cùng lượt chung chưa
            chắc cùng cột, thẻ có thể vẽ lệch. Nói ra thay vì lặng lẽ bày một sơ đồ sai. */}
        {!layout.hoiTu && (
          <span className="bgsd-tb-canhbao" role="alert" title="Sơ đồ có ràng buộc vòng hoặc quá phức tạp để xếp cột — vị trí thẻ có thể chưa đúng. Số liệu không ảnh hưởng.">
            <Icon name="alert" size={13} /> Sơ đồ xếp chưa chuẩn
          </span>
        )}
      </div>

      {/* Vùng cuộn thật: có thanh cuộn 2 chiều, lăn/Shift+lăn/phím mũi tên chạy sẵn. */}
      <div
        ref={containerRef}
        className={`bgsd-canvas ${isPanning ? "is-panning" : ""}`}
        onMouseDown={handleMouseDownCanvas}
        tabIndex={0}
        role="group"
        aria-label="Sơ đồ bài ghép — dùng phím mũi tên để di chuyển, Ctrl và lăn chuột để thu phóng"
      >
        {/* Lớp định cỡ: mang đúng kích thước ĐÃ nhân zoom để sinh ra tầm cuộn chuẩn. */}
        <div className="bgsd-canvas__sizer" style={{ width: bien.w * zoom, height: bien.h * zoom }}>
          <div
            className="bgsd-canvas__viewport bgsd-canvas__bg"
            style={{ width: bien.w, height: bien.h, transform: `scale(${zoom})`, transformOrigin: "0 0" }}
          >
            <svg className="bgsd-canvas__svg">
              <defs>
                <filter id="bgsdGlowFilter" x="-30%" y="-30%" width="160%" height="160%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              {sd.nhanh.map((n) => {
                const c = mau(n.mau);
                const isSelected = lsxDangChon === n.lsx_id;
                const strokeWidth = isSelected ? 4 : 2.8;
                const opacity = lsxDangChon !== null && !isSelected ? 0.25 : 0.95;
                const filterAttr = isSelected ? "url(#bgsdGlowFilter)" : undefined;
                const hang = hangCua(n.lsx_id);
                const yNhanh = PAD + hang * ROW_H;
                const lines: React.ReactNode[] = [];

                const hdrP = positions[`hdr_${n.lsx_id}`];
                let prev: Point | null = hdrP
                  ? { x: hdrP.x + HDR_W, y: hdrP.y + HDR_H / 2 }
                  : null;

                n.buoc.forEach((b, i) => {
                  const truocCungGop =
                    i > 0 && deLen.get(n.buoc[i - 1].step_key) === deLen.get(b.step_key) && deLen.has(b.step_key);
                  const vao = mep(b.step_key, "trai", yNhanh);
                  if (prev && vao && !truocCungGop) {
                    const d = drawBezier(prev, vao);
                    lines.push(
                      <g key={`e_${b.step_key}`}>
                        <path d={d} stroke={c} strokeWidth={strokeWidth} strokeOpacity={opacity} fill="none" filter={filterAttr} strokeLinecap="round" />
                        <path d={d} className="bgsd-flow-line" stroke="rgba(255, 255, 255, 0.85)" strokeWidth={Math.max(1.2, strokeWidth - 1.2)} strokeDasharray="6,8" fill="none" />
                        {deLen.has(b.step_key) && (
                          <circle cx={vao.x} cy={vao.y} r={5} fill={c} stroke="#ffffff" strokeWidth={1.5} />
                        )}
                      </g>,
                    );
                  }
                  prev = mep(b.step_key, "phai", yNhanh) ?? prev;

                  b.phu_thuoc_step_keys.forEach((pk) => {
                    if (!vao) return;
                    // Tiền nhiệm NGOÀI bài → dây xám đứt nét, để thấy nhánh còn chờ lệnh khác.
                    const np = positions[`ngoai_${pk}`];
                    if (np) {
                      lines.push(
                        <path
                          key={`ng_${pk}_${b.step_key}`}
                          d={drawBezier({ x: np.x + CARD_W, y: np.y + CARD_H / 2 }, vao)}
                          stroke="#64748b" strokeWidth={1.8} strokeDasharray="4,4" fill="none"
                        />,
                      );
                      return;
                    }
                    // Tiền nhiệm là bước của LỆNH KHÁC TRONG BÀI (sách: ruột xong mới vào bìa).
                    // Bỏ qua cạnh trong cùng một hàng — dây tuần tự ở trên đã vẽ rồi.
                    const hangTruoc = hangCuaBuoc.get(pk);
                    if (hangTruoc === undefined || hangTruoc === hang) return;
                    const ra = mep(pk, "phai", PAD + hangTruoc * ROW_H);
                    if (!ra) return;
                    lines.push(
                      <path
                        key={`cheo_${pk}_${b.step_key}`}
                        className="bgsd-edge-cheo"
                        d={drawBezier(ra, vao)}
                        stroke="#7c3aed" strokeWidth={1.8} strokeDasharray="6,5" fill="none"
                      >
                        <title>Chờ bước của lệnh khác trong bài</title>
                      </path>,
                    );
                  });
                });

                // Dây nối tới thẻ kết quả tổng kết cuối nhánh (Right Result Node: "vừa đủ" / "dư +100 con")
                if (n.toa_step_key && prev) {
                  const maxCot = Math.max(0, ...n.buoc.map((b) => cot[b.step_key] ?? 0)) + 1;
                  const rightPos = { x: xCuaCot(maxCot), y: yNhanh + CARD_H / 2 };
                  const dRight = drawBezier(prev, rightPos);
                  lines.push(
                    <g key={`right_${n.lsx_id}`}>
                      <path d={dRight} stroke={c} strokeWidth={strokeWidth} strokeOpacity={opacity} fill="none" filter={filterAttr} strokeLinecap="round" />
                      <path d={dRight} className="bgsd-flow-line" stroke="rgba(255, 255, 255, 0.85)" strokeWidth={Math.max(1.2, strokeWidth - 1.2)} strokeDasharray="6,8" fill="none" />
                    </g>,
                  );
                }

                return <g key={`g_${n.lsx_id}`}>{lines}</g>;
              })}
            </svg>

            {/* --- Thẻ chung: một lượt chạy, nhánh tụ vào trái và toả ra phải --- */}
            {sd.gop.map((g) => {
              const p = positions[`gop_${g.step_key}`];
              if (!p) return null;
              const meta = LSX_LOAI_BUOC_META[g.loai_buoc] ?? { label: g.loai_buoc };
              const mauCham = g.thanh_vien
                .map((tv) => sd.nhanh.find((n) => n.lsx_id === tv.lsx_id)?.mau ?? 0);
              return (
                <div
                  key={g.step_key}
                  className={`dag-node bgsd-gang bgsd-gang--hover-act ${
                    chon === g.step_key ? "dag-node--selected" : ""
                  } ${g.thieu.length ? "dag-node--has-error" : ""}`}
                  style={{ left: p.x, top: p.y, width: GANG_W, minHeight: caoGop(g) }}
                  aria-label={`Bước chung ${g.ten}`}
                  onClick={() => onChon(g.step_key)}
                  onDoubleClick={() => onMoBuocChung?.(g.step_key)}
                  onMouseDown={(e) => handleStartDragNode(`gop_${g.step_key}`, e)}
                >
                  <div className="dag-port dag-port--in" />
                  <div className="dag-node__head">
                    <span className="bgsd-gang__chams">
                      {mauCham.map((m, i) => (
                        <span key={i} className="bgsd__cham" style={{ background: mau(m) }} />
                      ))}
                    </span>
                    <button type="button" className="dag-node__title bgsd-node-title-btn" title={g.ten}
                      style={{ appearance: "none", border: 0, padding: 0, background: "transparent", font: "inherit", textAlign: "left", cursor: "pointer" }}
                      aria-pressed={chon === g.step_key}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => { e.stopPropagation(); onChon(g.step_key); }}
                      onDoubleClick={(e) => { e.stopPropagation(); onMoBuocChung?.(g.step_key); }}>
                      {g.ten}
                    </button>
                    <span className="dag-node__type-tag dag-node__type-tag--ghep" title="Chạy chung một lượt">
                      {g.ma_bai_ghep}
                    </span>
                    {canUpdate && onTach && (
                      <div className="dag-node__actions">
                        <button
                          type="button" className="dag-node__btn" title="Lập kế hoạch cho lượt chung"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => { e.stopPropagation(); onMoBuocChung?.(g.step_key); }}
                        >
                          <Icon name="edit" size={12} />
                        </button>
                        <button
                          type="button" className="dag-node__btn dag-node__btn--delete" title="Tách lượt chung"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => { e.stopPropagation(); void tachNgay(g); }}
                        >
                          <Icon name="unlink" size={12} />
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="dag-node__body">
                    <div className="dag-node__row">
                      <span className="dag-node__badge">
                        <Icon name="users" size={11} />
                        {g.to_ten ? `Tổ ${g.to_ten}` : "Chưa chọn tổ"}
                      </span>
                      {g.loai_buoc === "thue_ngoai" ? (
                        <span className="dag-node__badge" title="Cả bài đi một phiếu, một nhà cung cấp">
                          <Icon name="truck" size={11} />
                          {g.nha_cung_cap || "chưa có nhà gia công"}
                        </span>
                      ) : (
                        g.may_ten && (
                          <span className="dag-node__badge" title={`Máy: ${g.may_ten}`}>
                            <Icon name="cpu" size={11} />
                            {g.may_ten}
                          </span>
                        )
                      )}
                      <span className="dag-node__badge" title={meta.label}>{meta.label}</span>
                    </div>

                    {/* Bước chế bản (prepress) chạy chung = CHUNG BẢN (1 bộ kẽm) — không nằm trên
                        dòng giấy nên KHÔNG có số tờ vào/ra (trước đây hiện "250→250" vô nghĩa). */}
                    {!g.tren_giay ? (
                      <div className="bgsd-gang__chungban">
                        <Icon name="layers" size={11} /> Chung bản — 1 bộ kẽm cho cả lượt
                      </div>
                    ) : (
                      <>
                        {/* Số của CẢ LƯỢT, tính bằng tờ ghép — hao đếm ĐÚNG MỘT LẦN, không phải mỗi
                            lệnh một bộ cho cùng một lần lên máy. */}
                        <LuongSoLuong vao={g.so_luong_vao} ra={g.so_luong_ra} dvVao={g.don_vi_vao} dvRa={g.don_vi_ra} />
                        {/* Bước ĐỔI đơn vị (bế, đóng cuốn) thì phải nói rõ cầu, không thì "20.500 tờ →
                            2.050 cuốn" đọc lên vô lý — đúng cách panel bù hao bên tính giá trình bày. */}
                        {heSoChu(g.he_so_quy_doi, g.don_vi_vao, g.don_vi_ra) && (
                          <div className="dag-node__row">
                            <span className="dag-node__label"><Icon name="rotateCcw" size={11} /></span>
                            <span className="dag-node__value">
                              {heSoChu(g.he_so_quy_doi, g.don_vi_vao, g.don_vi_ra)}
                            </span>
                          </div>
                        )}
                        {g.hao_hut > 0 && (
                          <div className="dag-node__row">
                            {/* T4: "bước này" — phân biệt với TỔNG hao ở header (Σ mọi bước chung). */}
                            <span className="dag-node__label">Hao bước này:</span>
                            <span
                              className="dag-node__value"
                              title={
                                g.so_luong_ra_quy != null
                                  ? `cần ${num(g.so_luong_ra_quy)} ${nhanDonVi(g.don_vi_vao)} tốt `
                                    + `+ ${num(g.hao_hut)} hao = ${num(g.so_luong_vao)} ${nhanDonVi(g.don_vi_vao)}`
                                  : "Một lần lên máy thì canh máy một lần"
                              }
                            >
                              {num(g.hao_hut)} {nhanDonVi(g.don_vi_vao)}
                              {g.hao_hut_pct > 0 ? ` (${g.hao_hut_pct}%)` : ""}
                            </span>
                          </div>
                        )}
                        {/* T2b: hiện ĐÍCH DANH bước + đơn vị lệch (server đã gắn per-thẻ), không còn
                            câu chung "Chuỗi đơn vị có vấn đề" dán lên mọi thẻ. */}
                        {g.canh_bao_don_vi.length > 0 && (
                          <div className="dag-node__warn" title={g.canh_bao_don_vi.join("\n")}>
                            <Icon name="alert" size={11} /> {g.canh_bao_don_vi.join("; ")}
                          </div>
                        )}
                      </>
                    )}
                    <div className="dag-node__row">
                      <span className="dag-node__label">Thời lượng:</span>
                      <span className="dag-node__value">{phut(g.tong_phut)}</span>
                    </div>

                    <div className="bgsd-gang__lenh">
                      {g.thanh_vien.map((tv) => (
                        <span key={tv.lsx_step_key} className="bgsd-gang__lenh-chip" title={tv.ghi_chu_ky_thuat ?? undefined}>
                          {tv.lsx_ma}
                          {tv.ghi_chu_ky_thuat ? " *" : ""}
                        </span>
                      ))}
                    </div>

                    {g.thieu.length > 0 && (
                      <div className="dag-node__warnings">
                        {g.thieu.map((w) => (
                          <span key={w} className="dag-node__warning-chip dag-node__warning-chip--err">⚠️ {w}</span>
                        ))}
                      </div>
                    )}
                    {/* T3: máy gán không hợp công đoạn (sai loại / vượt khổ-màu-gsm) — cảnh báo mềm. */}
                    {g.may_khong_hop.length > 0 && (
                      <div className="dag-node__warnings">
                        {g.may_khong_hop.map((w) => (
                          <span key={w} className="dag-node__warning-chip dag-node__warning-chip--err">⚠️ {w}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="dag-port dag-port--out" />
                </div>
              );
            })}

            {/* --- Từng nhánh: thẻ lệnh + routing đầy đủ --- */}
            {sd.nhanh.map((n) => {
              const c = mau(n.mau);
              const isSelected = lsxDangChon === n.lsx_id;
              const hdrP = positions[`hdr_${n.lsx_id}`] || { x: PAD, y: PAD };
              const yNhanh = PAD + hangCua(n.lsx_id) * ROW_H;
              // Chip "dư tờ" bám vào thẻ RIÊNG đầu tiên sau điểm toả. Không có thẻ nào (bước gộp
              // là bước cuối routing — rất hay gặp khi mới gộp bước in) thì `-1`, và chip chuyển
              // sang khối tổng kết cuối nhánh chứ KHÔNG biến mất như trước.
              const toaIdx = n.toa_step_key
                ? n.buoc.findIndex((x) => x.step_key === n.toa_step_key)
                : -1;
              const neoDuTo =
                toaIdx >= 0
                  ? n.buoc.findIndex((b, j) => j > toaIdx && !deLen.has(b.step_key))
                  : -1;

              return (
                <React.Fragment key={n.thanh_vien_id}>
                  <div
                    className={`bgsd-card-branch ${isSelected ? "is-chon" : ""}`}
                    style={{
                      left: hdrP.x, top: hdrP.y, borderColor: c,
                      width: HDR_W, height: HDR_H, ["--mau-nhanh" as string]: c,
                    }}
                    onClick={() => onChon(n.lsx_id)}
                    onDoubleClick={() => onMoLenh?.(n.lsx_id)}
                    onMouseDown={(e) => handleStartDragNode(`hdr_${n.lsx_id}`, e)}
                    title={n.lsx_ten ? `${n.lsx_ma}: ${n.lsx_ten} (Nháy đúp để mở lệnh)` : "Nháy đúp để mở lệnh sản xuất"}
                  >
                    <div className="bgsd-card-branch__head">
                      <span className="bgsd__cham" style={{ background: c }} />
                      <button type="button" className="khsx__code bgsd-node-title-btn"
                        style={{ appearance: "none", border: 0, padding: 0, background: "transparent", font: "inherit", textAlign: "left", cursor: "pointer" }}
                        aria-pressed={isSelected}
                        aria-label={`Chọn lệnh ${n.lsx_ma}`}
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => { e.stopPropagation(); onChon(n.lsx_id); }}
                        onDoubleClick={(e) => { e.stopPropagation(); onMoLenh?.(n.lsx_id); }}>
                        {n.lsx_ma}
                      </button>
                      {/* `con/tờ` CHỈ GHI NHẬN (bình bài bằng phần mềm khác), nhưng là khoá chia
                          mọi thứ sau điểm toả — sản lượng và giấy đều chia theo con. Sửa TẠI CHỖ
                          vì đây là số người cân bài chỉnh nhiều nhất; bắt mở modal cho mỗi lần
                          đổi một con số là thừa hẳn một vòng thao tác. */}
                      {canUpdate && onSuaCon ? (
                        <input
                          type="number" min={0} className="bgsd-branch__ups bgsd-branch__ups--edit"
                          defaultValue={n.so_con_tren_to}
                          title="Số con xếp trên tờ ghép — khoá chia sản lượng và giấy"
                          aria-label={`Số con trên tờ của lệnh ${n.lsx_ma}`}
                          onClick={(e) => e.stopPropagation()}
                          onDoubleClick={(e) => e.stopPropagation()}
                          onMouseDown={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                            if (e.key === "Escape") {
                              (e.target as HTMLInputElement).value = String(n.so_con_tren_to);
                              (e.target as HTMLInputElement).blur();
                            }
                          }}
                          onBlur={(e) => {
                            const v = Math.max(0, Math.trunc(Number(e.target.value)));
                            if (!Number.isFinite(v) || v === n.so_con_tren_to) {
                              e.target.value = String(n.so_con_tren_to);
                              return;
                            }
                            onSuaCon(n.thanh_vien_id, v);
                          }}
                        />
                      ) : (
                        <span className="bgsd-branch__ups" title="Số con xếp trên tờ ghép — khoá chia sản lượng và giấy">
                          {n.so_con_tren_to} con/tờ
                        </span>
                      )}
                    </div>
                    <div className="bgsd-card-branch__cust">
                      {n.lsx_ten && <span className="bgsd-branch__sp" title={n.lsx_ten}>{n.lsx_ten}</span>}
                      <span className="bgsd-branch__kh" title={`Khách: ${n.customer_name ?? "khách lẻ"}`}>
                        {n.customer_name ?? "Khách lẻ"}
                      </span>
                    </div>
                    <div className="bgsd-card-branch__to">
                      {n.so_con_tren_to > 0 ? (
                        <span className="bgsd-branch__can" title="Số tờ in lệnh này thật sự cần — đã gồm hao của các bước riêng">
                          cần {num(n.nhu_cau_to)} tờ
                        </span>
                      ) : (
                        <span className="bgsd-branch__can is-warn" title="Chưa xếp con nào lên tờ">chưa xếp con</span>
                      )}
                      {!n.toa_step_key && (
                        <span className="bgsd-branch__du" title="Lệnh chưa gộp bước nào — chưa chung tờ với bài">
                          chạy riêng
                        </span>
                      )}
                      {/* Tờ thì dùng CHUNG nên không có "tờ của lệnh nào"; chia được là CHI PHÍ
                          giấy, chia theo con — cùng khoá với phép chia sản lượng ở điểm toả. */}
                      {n.phan_giay_to > 0 && (
                        <span
                          className="bgsd-branch__giay"
                          title={`Phần giấy lệnh này gánh: ${num(n.phan_giay_to)} tờ nguyên `
                            + `(${n.ty_le_giay}% diện tích tờ, chia theo con)`}
                        >
                          giấy {num(n.phan_giay_to)} tờ · {n.ty_le_giay}%
                        </span>
                      )}
                    </div>
                    <div className="bgsd-card-branch__tags">
                      {n.is_rush && <span className="bgsd-rush-tag"><ChipGap /></span>}
                      {n.han_hoan_thanh_sx && (
                        <small className={`bgsd-card-branch__han ${classHan(n.han_hoan_thanh_sx)}`}>
                          hạn {ngay(n.han_hoan_thanh_sx)}
                        </small>
                      )}
                    </div>
                  </div>

                  {n.buoc.map((b, i) => {
                    if (deLen.has(b.step_key)) return null;     // thẻ chung đã thay nó
                    const p = positions[`node_${b.step_key}`] || { x: 0, y: 0 };
                    const meta = LSX_LOAI_BUOC_META[b.loai_buoc] ?? { label: b.loai_buoc };
                    const daChon = dangChon.includes(b.step_key);
                    const uv = ungVien[b.step_key];
                    const sang = !!uv?.gop_duoc && hopDieuKienGop(b);
                    const mo = dangChon.length > 0 && !daChon && !sang;

                    return (
                      <React.Fragment key={b.step_key}>
                        {/* Tiền nhiệm ngoài bài — node bóng mờ, chỉ để biết nhánh còn chờ ai. */}
                        {b.phu_thuoc_step_keys.map((pk) => {
                          const o = ngoaiMap.get(pk);
                          const np = positions[`ngoai_${pk}`];
                          if (!o || !np) return null;
                          return (
                            <div
                              key={pk} className="dag-node bgsd-node--ngoai"
                              style={{ left: np.x, top: np.y, width: CARD_W }}
                              onMouseDown={(e) => handleStartDragNode(`ngoai_${pk}`, e)}
                            >
                              <div className="dag-node__head">
                                <Icon name="link" size={12} />
                                <span className="dag-node__title" title={o.ten}>{o.ten}</span>
                                <span className="dag-node__type-tag">{o.lsx_ma ?? "LSX khác"}</span>
                              </div>
                            </div>
                          );
                        })}

                        <div
                          className={`dag-node bgsd-step ${isSelected ? "is-nhanh-chon" : ""} ${
                            daChon ? "dag-node--selected is-chon-gop" : ""
                          } ${sang ? "is-ung-vien" : ""} ${mo ? "is-mo" : ""}`}
                          style={{ left: p.x, top: p.y, width: CARD_W, ["--mau-nhanh" as string]: c }}
                          title={uv && !uv.gop_duoc ? uv.ly_do ?? undefined : undefined}
                          role="button"
                          tabIndex={0}
                          aria-label={`Công đoạn ${b.ten}`}
                          aria-pressed={daChon}
                          onClick={(e) => { e.stopPropagation(); bamThe(b); }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              bamThe(b);
                            }
                          }}
                          onDoubleClick={(e) => { e.stopPropagation(); onMoLenh?.(n.lsx_id); }}
                          onMouseDown={(e) => handleStartDragNode(`node_${b.step_key}`, e)}
                        >
                          <div className="dag-port dag-port--in" />
                          <div className="dag-node__head">
                            <span className="dag-node__seq">#{(i + 1) * 10}</span>
                            <span className="dag-node__title" title={b.ten}>{b.ten}</span>
                            <span className={`dag-node__type-tag dag-node__type-tag--${b.loai_buoc}`}>
                              {meta.label}
                            </span>
                          </div>
                          <div className="dag-node__body">
                            <div className="dag-node__row">
                              <span className="dag-node__badge">
                                <Icon name={getStepIcon(b)} size={11} />
                                {b.to_ten ? `Tổ ${b.to_ten}` : "Chưa chọn tổ"}
                              </span>
                              {b.loai_buoc === "thue_ngoai"
                                ? <span className="dag-node__badge"><Icon name="truck" size={11} />{b.nha_cung_cap || "chưa có nhà gia công"}</span>
                                : b.may_ten && <span className="dag-node__badge" title={`Máy: ${b.may_ten}`}><Icon name="cpu" size={11} />{b.may_ten}</span>}
                            </div>
                            <LuongSoLuong vao={b.so_luong_vao} ra={b.so_luong_ra} dvVao={b.don_vi_vao} dvRa={b.don_vi_ra} />
                            <div className="dag-node__row">
                              <span className="dag-node__label">Thời lượng:</span>
                              <span className="dag-node__value">{phut(b.tong_phut)}</span>
                            </div>
                          </div>
                          <div className="dag-port dag-port--out" />
                        </div>

                        {/* Dư TỜ — phát sinh NGAY tại điểm toả: bài chạy `so_to_tot` tờ chung, lệnh
                            nào cần ít hơn thì thừa ngay tại đó. Khác hẳn dư CON ở cuối chuỗi. */}
                        {i === neoDuTo && (
                          <div
                            className={`bgsd-du-to ${n.du_to > 0 ? "is-thua" : "is-vua"}`}
                            style={{ left: p.x - 6, top: p.y - 24 }}
                            title={
                              n.du_to > 0
                                ? `Bài chạy ${num(n.nhu_cau_to + n.du_to)} tờ, lệnh này chỉ cần ${num(n.nhu_cau_to)} tờ`
                                : "Lệnh này là lệnh quyết định số tờ của bài"
                            }
                          >
                            {n.du_to > 0 ? `+${num(n.du_to)} tờ` : "đủ tờ"}
                          </div>
                        )}
                      </React.Fragment>
                    );
                  })}

                  {/* Dư THÀNH PHẨM ở cuối nhánh — đã trừ hao mọi bước riêng, khác dư tờ ở điểm toả. */}
                  {n.toa_step_key && (
                    <div
                      className="bgsd-card-branch bgsd-card-branch--right"
                      style={{
                        left: xCuaCot(Math.max(0, ...n.buoc.map((b) => cot[b.step_key] ?? 0)) + 1),
                        top: yNhanh + CARD_H / 2 - 18,
                      }}
                    >
                      {/* Bước gộp là bước CUỐI routing thì không còn thẻ riêng nào để treo chip
                          "dư tờ" lên. Trước đây chip biến mất hẳn, dù `du_to` vẫn khác 0 — số có
                          mà màn hình câm. Dồn về đây, xếp trên dư thành phẩm: hai số cùng là
                          tổng kết cuối nhánh, đọc liền nhau đúng thứ tự tờ → con. */}
                      {neoDuTo < 0 && (
                        <span
                          className={`bgsd-du-to bgsd-du-to--tong ${n.du_to > 0 ? "is-thua" : "is-vua"}`}
                          title={
                            n.du_to > 0
                              ? `Bài chạy ${num(n.nhu_cau_to + n.du_to)} tờ, lệnh này chỉ cần ${num(n.nhu_cau_to)} tờ`
                              : "Lệnh này là lệnh quyết định số tờ của bài"
                          }
                        >
                          {n.du_to > 0 ? `+${num(n.du_to)} tờ` : "đủ tờ"}
                        </span>
                      )}
                      {n.du > 0 ? (
                        <span className="bgsd-pill-status is-surplus">
                          <Icon name="check" size={12} /> dư +{num(n.du)} con
                        </span>
                      ) : (
                        <span className="bgsd-pill-status is-exact">vừa đủ</span>
                      )}
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>

      {/* Thanh nổi khi đang chọn bước để gộp. Kiểm vòng đã chạy TRƯỚC nên nút Gộp bấm là ăn. */}
      {dangChon.length > 0 && (
        <div className="bgsd-selbar" role="status">
          <span className="bgsd-selbar__info">
            Đã chọn <b>{dangChon.length}</b> bước{tenDangChon ? ` · ${tenDangChon}` : ""}
          </span>
          {/* Bấm thẻ mờ vì sinh vòng: nói ngay lý do server trả về. Trước đây chỗ này im, người
              dùng bấm mãi không hiểu vì sao thẻ không nhận. */}
          {lyDoChan && (
            <span className="bgsd-selbar__chan" role="alert">
              <Icon name="alert" size={13} /> {lyDoChan}
            </span>
          )}
          <button
            type="button" className="bgsd-selbar__gop"
            disabled={dangChon.length < 2 || dangGop}
            onClick={() => void gopNgay()}
          >
            <Icon name="link" size={13} /> {dangGop ? "Đang gộp…" : `Gộp ${dangChon.length} bước`}
          </button>
          <button type="button" className="bgsd-selbar__huy" onClick={huyChon}>Huỷ (Esc)</button>
        </div>
      )}

      {/* Modal xác nhận tách lượt chung */}
      <ConfirmDialog
        open={tachTarget !== null}
        title={`Tách lượt chung "${tachTarget?.ten}"?`}
        message="Kế hoạch của lượt chung sẽ mất, số riêng của từng lệnh quay lại."
        confirmLabel="Tách lượt chung"
        cancelLabel="Hủy"
        danger
        onConfirm={() => {
          if (tachTarget && onTach) {
            const g = tachTarget;
            setTachTarget(null);
            void onTach(g.step_key);
          }
        }}
        onCancel={() => setTachTarget(null)}
      />
    </div>
  );
}
