// LỊCH CHẠY — GANTT THANH: mỗi hàng MÁY là 1 track 7 ngày, mỗi lệnh là 1 THANH bắc từ ngày chạy
// tới hạn giao (nội bộ ưu tiên). 3 hành vi tách bạch: kéo-THÂN đổi máy/ngày (HTML5 drag) · kéo-ĐUÔI
// đổi hạn nội bộ (pointer, chỉ lệnh NHÁP) · bấm-THÂN mở lệnh. Máy CHỈ GHI NHẬN: trùng máy chỉ tô cảnh
// báo (không chặn). Menu "…" = popover neo (bản-sao-bàn-phím cho kéo/resize). Khay "Chưa xếp" = vùng gỡ.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  Flag,
  Gauge,
  Lock,
  MoreHorizontal,
  Scissors,
} from "lucide-react";
import { api, ApiError, type LichChayRow } from "../api/client";
import { mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { ToastStack, useToasts } from "./LsxToast";
import { hanGiao } from "../utils/format";
import "./lenh-san-xuat.css";

const WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function mondayIdx(jsDay: number): number {
  return (jsDay + 6) % 7; // JS 0=CN → 6, 1=T2 → 0
}
function startOfWeek(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - mondayIdx(x.getDay()));
  return x;
}
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
// Chênh lệch NGÀY (chuẩn hoá về nửa đêm địa phương, bỏ giờ) giữa iso và cột đầu cửa sổ.
function diffDays(iso: string, base: Date): number {
  const s = iso.slice(0, 10);
  const [y, m, dd] = s.split("-").map(Number);
  const a = new Date(y, (m ?? 1) - 1, dd ?? 1).getTime();
  const b = new Date(base.getFullYear(), base.getMonth(), base.getDate()).getTime();
  return Math.round((a - b) / 86400000);
}
function dm(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, dd] = iso.slice(0, 10).split("-").map(Number);
  const d = new Date(y, (m ?? 1) - 1, dd ?? 1);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}
// Lọc "máy in" — KHÔNG dùng loai_may.startsWith("press_") (ra rỗng). Copy cục bộ (rebuildCatalogConfigs).
const isMayIn = (val: unknown) => {
  const s = String(val || "").trim().toLowerCase();
  return s === "máy in" || s === "in ngoài" || s.startsWith("in ") || s.includes("máy in") || s.includes("in offset");
};
// ===== MOCK công suất máy (CHƯA nối BE) =====
// Công suất THẬT sau này suy từ `may_thiet_bi.toc_do` (đơn vị `to_gio`) × giờ chạy/ngày (`so_ca`).
// Ở đây MOCK, deterministic theo id để số không nhảy mỗi lần render, và MỖI MÁY MỘT MỨC khác nhau.
const MOCK_CONG_SUAT = [5200, 6800, 4500, 7600, 3800, 6100, 5500, 4200, 7100, 3400];
const mockCongSuat = (may: { id: number; ten?: string }) => {
  // Máy IN: suy theo SỐ MÀU trong tên (2 màu→7.000 · 4→9.000 · 5→10.000 · 6→11.000 · 7→12.000)
  // — máy nhiều màu/khổ lớn thì công suất cao hơn, nên mỗi máy ra một mức khác nhau, trông như thật.
  const mau = /(\d+)\s*màu/i.exec(may.ten ?? "")?.[1];
  if (mau) return 5000 + Number(mau) * 1000;
  // Máy sau in (bế/cán/bồi…): bảng mock rải đều, deterministic theo id.
  return MOCK_CONG_SUAT[Math.abs(may.id) % MOCK_CONG_SUAT.length];
};

// MOCK số TỜ IN của 1 lệnh — tải máy đếm THEO TỜ IN (chủ chốt).
// ⚠️ Bản THẬT phải gom theo `print_form.so_to_chay` và KHỬ TRÙNG: xưởng ghép bài ~40% nên NHIỀU
// lệnh có thể in CHUNG 1 tờ in = 1 lượt chạy máy — cộng theo lệnh sẽ đếm trùng, cảnh báo sai.
const MOCK_TO_IN = [3200, 5400, 1800, 8600, 2500, 6100, 4300, 7400, 900, 5900];
const mockToIn = (lenhId: number) => MOCK_TO_IN[Math.abs(lenhId) % MOCK_TO_IN.length];
const fmtTo = (n: number) => n.toLocaleString("vi-VN");

const dueRank = (r: LichChayRow): number => {
  const d = hanGiao(r.han_giao_noi_bo ?? r.han_giao_khach);
  return d ? { over: 0, soon: 1, ok: 2 }[d.level] : 3;
};

type BarLevel = "over" | "soon" | "ok" | "nodue";
interface MayLite {
  id: number;
  ma: string;
  ten: string;
}
interface DragInfo {
  lenhId: number;
  fromMayId: number | null;
  fromNgay: string | null;
}
interface BarLayout {
  row: LichChayRow;
  startIdx: number;
  endIdx: number;
  clippedLeft: boolean;
  clippedRight: boolean;
  lane: number;
  level: BarLevel;
  dueRaw: string | null;
}
interface ResizeInfo {
  lenhId: number;
  startIdx: number;
  origEnd: number;
  rectLeft: number;
  colW: number;
}
interface MenuState {
  lenhId: number;
  left: number;
  top: number;
  above: boolean;
}

export function LenhSanXuatLichChayView({
  onBack,
  onOpen,
}: {
  onBack: () => void;
  onOpen: (id: number) => void;
}) {
  const { token } = useAuth();
  const { toasts, ok: toastOk, err: toastErr, dismiss: toastDismiss } = useToasts();

  const [anchor, setAnchor] = useState<Date>(() => startOfWeek(new Date()));
  const [rows, setRows] = useState<LichChayRow[] | null>(null);
  const [mays, setMays] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [dropKey, setDropKey] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [resizePreview, setResizePreview] = useState<{ lenhId: number; endIdx: number } | null>(null);
  const dragRef = useRef<DragInfo | null>(null);
  const resizeRef = useRef<ResizeInfo | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const days = useMemo(() => {
    const out: Date[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(anchor);
      d.setDate(anchor.getDate() + i);
      out.push(d);
    }
    return out;
  }, [anchor]);
  const windowStart = days[0];
  const from = ymd(days[0]);
  const to = ymd(days[6]);
  const todayStr = ymd(new Date());

  const load = useCallback(() => {
    if (!token) return;
    Promise.all([
      api.lenhSanXuat.lichChay(token, { from, to }),
      mayThietBi.list(token).catch(() => ({ items: [] as Row[] })),
    ])
      .then(([lich, may]) => {
        setRows(lich);
        setMays(may.items);
        setError(null);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được lịch chạy."),
      );
  }, [token, from, to]);
  useEffect(() => {
    setRows(null);
    load();
  }, [load]);

  // Esc / click-ngoài / cuộn / đổi kích thước → đóng popover "…" (neo cứng theo viewport).
  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    const close = () => setMenu(null);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  const mayById = useMemo(() => new Map(mays.map((m) => [m.id, m])), [mays]);

  // Hàng máy = (máy in trong danh mục) ∪ (mọi may_id đang có trong data) → lệnh gán máy lạ vẫn hiện.
  const machineRows = useMemo<MayLite[]>(() => {
    const seen = new Set<number>();
    const out: MayLite[] = [];
    mays
      .filter((m) => isMayIn(m.loai_may))
      .forEach((m) => {
        if (!seen.has(m.id)) {
          seen.add(m.id);
          out.push({
            id: m.id,
            ma: String(m.ma ?? `#${m.id}`),
            ten: String(m.ten ?? m.ma ?? `#${m.id}`),
          });
        }
      });
    (rows ?? []).forEach((r) => {
      if (r.may_id != null && !seen.has(r.may_id)) {
        seen.add(r.may_id);
        const m = mayById.get(r.may_id);
        out.push({
          id: r.may_id,
          ma: m ? String(m.ma ?? `#${r.may_id}`) : `#${r.may_id}`,
          ten: m ? String(m.ten ?? m.ma ?? `#${r.may_id}`) : `Máy #${r.may_id}`,
        });
      }
    });
    return out.sort((a, b) => a.ma.localeCompare(b.ma, "vi", { numeric: true }));
  }, [mays, rows, mayById]);

  // Thanh Gantt theo máy + lane-packing (không chồng thanh) + cover[col] để cảnh báo kẹt máy.
  const { barsByMachine, coverByMachine } = useMemo(() => {
    const barsByMachine = new Map<number, BarLayout[]>();
    const coverByMachine = new Map<number, number[]>();
    const byMachine = new Map<number, LichChayRow[]>();
    (rows ?? []).forEach((r) => {
      if (r.may_id == null || r.ngay_chay == null) return;
      const arr = byMachine.get(r.may_id);
      if (arr) arr.push(r);
      else byMachine.set(r.may_id, [r]);
    });
    byMachine.forEach((list, mid) => {
      const bars: BarLayout[] = list.map((r) => {
        const rawStart = diffDays(r.ngay_chay as string, windowStart);
        const startIdx = clamp(rawStart, 0, 6);
        const dueRaw = r.han_giao_noi_bo ?? r.han_giao_khach;
        const rawDue = dueRaw ? diffDays(dueRaw, windowStart) : null;
        const endIdx = rawDue != null ? clamp(rawDue, startIdx, 6) : startIdx;
        const due = hanGiao(dueRaw);
        const level: BarLevel = due ? due.level : dueRaw ? "ok" : "nodue";
        return {
          row: r,
          startIdx,
          endIdx,
          clippedLeft: rawStart < 0,
          clippedRight: rawDue != null && rawDue > 6,
          lane: 0,
          level,
          dueRaw,
        };
      });
      bars.sort(
        (a, b) => a.startIdx - b.startIdx || a.endIdx - b.endIdx || a.row.lenh_id - b.row.lenh_id,
      );
      const lanes: number[] = [];
      bars.forEach((b) => {
        let lane = lanes.findIndex((end) => end < b.startIdx);
        if (lane === -1) {
          lane = lanes.length;
          lanes.push(b.endIdx);
        } else {
          lanes[lane] = b.endIdx;
        }
        b.lane = lane;
      });
      const cover = [0, 0, 0, 0, 0, 0, 0];
      bars.forEach((b) => {
        for (let c = b.startIdx; c <= b.endIdx; c++) cover[c]++;
      });
      barsByMachine.set(mid, bars);
      coverByMachine.set(mid, cover);
    });
    return { barsByMachine, coverByMachine };
  }, [rows, windowStart]);

  const unscheduled = useMemo(
    () =>
      (rows ?? [])
        .filter((r) => r.may_id == null || r.ngay_chay == null)
        .sort((a, b) => dueRank(a) - dueRank(b) || a.lenh_id - b.lenh_id),
    [rows],
  );

  const clearDrag = () => {
    dragRef.current = null;
    setDraggingId(null);
    setDropKey(null);
  };

  const performMove = useCallback(
    async (lenhId: number, mayId: number | null, ngay: string | null) => {
      if (!token) return;
      setRows((prev) =>
        prev
          ? prev.map((r) =>
              r.lenh_id === lenhId ? { ...r, may_id: mayId, ngay_chay: ngay } : r,
            )
          : prev,
      );
      try {
        await api.lenhSanXuat.xepLich(token, lenhId, { may_id: mayId, ngay_chay: ngay });
        toastOk(mayId == null ? "Đã gỡ lệnh khỏi lịch" : "Đã xếp lệnh vào lịch");
        load();
      } catch (e) {
        toastErr(e instanceof ApiError ? e.message : "Không xếp được lịch.");
        load();
      }
    },
    [token, load, toastOk, toastErr],
  );

  // Đổi HẠN NỘI BỘ (kéo-đuôi / menu) — chỉ lệnh nháp; sau phát backend 409 → revert (reload) + toast khóa.
  const performResize = useCallback(
    async (lenhId: number, dueISO: string) => {
      if (!token) return;
      setRows((prev) =>
        prev
          ? prev.map((r) =>
              r.lenh_id === lenhId ? { ...r, han_giao_noi_bo: dueISO } : r,
            )
          : prev,
      );
      try {
        await api.lenhSanXuat.suaHanGiao(token, lenhId, { han_giao_noi_bo: dueISO });
        toastOk("Đã đổi hạn nội bộ");
        load();
      } catch (e) {
        if (e instanceof ApiError && e.isConflict) toastErr("Hạn đã khóa sau khi phát lệnh");
        else toastErr(e instanceof ApiError ? e.message : "Không đổi được hạn.");
        load();
      }
    },
    [token, load, toastOk, toastErr],
  );

  const onDropCell = (mayId: number, ngay: string) => {
    const d = dragRef.current;
    clearDrag();
    if (!d) return;
    if (d.fromMayId === mayId && d.fromNgay === ngay) return; // về đúng ô cũ → bỏ
    performMove(d.lenhId, mayId, ngay);
  };
  const onDropTray = () => {
    const d = dragRef.current;
    clearDrag();
    if (!d) return;
    if (d.fromMayId == null && d.fromNgay == null) return; // vốn đã ở khay
    performMove(d.lenhId, null, null);
  };

  // Neo popover "…" theo viewport (fixed) — mở xuống dưới, lật lên nếu ở nửa dưới màn hình.
  const anchorMenu = (el: HTMLElement, lenhId: number) => {
    const r = el.getBoundingClientRect();
    const POP = 264;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - POP - 8));
    const above = r.bottom > window.innerHeight * 0.62;
    const top = above ? r.top - 6 : r.bottom + 6;
    setMenu((prev) => (prev?.lenhId === lenhId ? null : { lenhId, left, top, above }));
  };

  const shiftWeek = (delta: number) => {
    setMenu(null);
    setAnchor((a) => {
      const d = new Date(a);
      d.setDate(a.getDate() + delta * 7);
      return d;
    });
  };
  const goToday = () => {
    setMenu(null);
    setAnchor(startOfWeek(new Date()));
  };

  // ---- 1 THANH Gantt ----
  function renderBar(bl: BarLayout, m: MayLite) {
    const r = bl.row;
    const isNhap = r.trang_thai === "nhap";
    const previewEnd =
      resizePreview?.lenhId === r.lenh_id ? resizePreview.endIdx : bl.endIdx;
    const effEnd = Math.max(bl.startIdx, previewEnd);
    const resizing = resizePreview?.lenhId === r.lenh_id;
    const needMold = r.can_khuon && !r.khuon_be_id;
    const specText =
      r.giay_label ||
      (r.spec_tom_tat || "").split(" · ").map((s) => s.trim()).filter(Boolean)[0] ||
      "";
    const menuOpen = menu?.lenhId === r.lenh_id;
    const showGrip = isNhap && !bl.clippedRight;
    const aria =
      `Lệnh ${r.ma} · máy ${m.ten} · bắt đầu ${dm(r.ngay_chay)} · ` +
      `hạn nội bộ ${r.han_giao_noi_bo ? dm(r.han_giao_noi_bo) : "chưa đặt"} · ` +
      `${isNhap ? "nháp" : "đang chạy"}`;

    const onGripDown = (e: React.PointerEvent) => {
      e.stopPropagation();
      e.preventDefault();
      const track = (e.currentTarget as HTMLElement).closest(".lsx-gtrack") as HTMLElement | null;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      try {
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      } catch {
        /* pointer capture optional */
      }
      resizeRef.current = {
        lenhId: r.lenh_id,
        startIdx: bl.startIdx,
        origEnd: bl.endIdx,
        rectLeft: rect.left,
        colW: rect.width / 7,
      };
      setResizePreview({ lenhId: r.lenh_id, endIdx: bl.endIdx });
    };
    const colAt = (clientX: number, st: ResizeInfo) =>
      clamp(Math.floor((clientX - st.rectLeft) / st.colW), st.startIdx, 6);
    const onGripMove = (e: React.PointerEvent) => {
      const st = resizeRef.current;
      if (!st) return;
      const col = colAt(e.clientX, st);
      setResizePreview((p) => (p && p.endIdx === col ? p : { lenhId: st.lenhId, endIdx: col }));
    };
    const onGripUp = (e: React.PointerEvent) => {
      const st = resizeRef.current;
      resizeRef.current = null;
      setResizePreview(null);
      if (!st) return;
      const col = colAt(e.clientX, st);
      if (col === st.origEnd) return;
      const d = new Date(windowStart);
      d.setDate(windowStart.getDate() + col);
      performResize(st.lenhId, ymd(d));
    };
    const onGripCancel = () => {
      resizeRef.current = null;
      setResizePreview(null);
    };

    return (
      <div
        key={r.lenh_id}
        role="button"
        tabIndex={0}
        draggable
        aria-label={aria}
        className={
          `lsx-gbar lsx-gbar--${bl.level}` +
          (draggingId === r.lenh_id ? " is-dragging" : "") +
          (resizing ? " is-resizing" : "")
        }
        style={{ gridColumn: `${bl.startIdx + 1} / ${effEnd + 2}`, gridRow: bl.lane + 1 }}
        onClick={() => onOpen(r.lenh_id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpen(r.lenh_id);
          }
        }}
        onDragStart={(e) => {
          if (resizeRef.current) {
            e.preventDefault();
            return;
          }
          dragRef.current = {
            lenhId: r.lenh_id,
            fromMayId: r.may_id,
            fromNgay: r.ngay_chay?.slice(0, 10) ?? null,
          };
          e.dataTransfer.setData("text/plain", String(r.lenh_id)); // Firefox cần mới cho kéo
          e.dataTransfer.effectAllowed = "move";
          setDraggingId(r.lenh_id);
        }}
        onDragEnd={clearDrag}
      >
        {bl.clippedLeft ? (
          <span className="lsx-gbar__ovl lsx-gbar__ovl--l" aria-hidden>
            ‹
          </span>
        ) : null}
        <span className="lsx-gbar__code mono">{r.ma}</span>
        {specText ? <span className="lsx-gbar__spec">{specText}</span> : <span className="lsx-gbar__spec" />}
        {needMold ? (
          <span className="lsx-badge lsx-badge--danger lsx-gbar__mold">
            <Scissors size={10} /> Chưa khuôn
          </span>
        ) : null}
        {bl.dueRaw ? (
          <span className={`lsx-gbar__due lsx-gbar__due--${bl.level}`}>
            <Flag size={10} /> {dm(bl.dueRaw)}
          </span>
        ) : (
          <span className="lsx-gbar__due lsx-gbar__due--nodue">+ hạn</span>
        )}
        <button
          type="button"
          className="lsx-gbar__menu"
          aria-label="Xếp máy / ngày / hạn"
          aria-haspopup="dialog"
          aria-expanded={menuOpen}
          draggable={false}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            anchorMenu(e.currentTarget, r.lenh_id);
          }}
        >
          <MoreHorizontal size={15} />
        </button>
        {showGrip ? (
          <span
            className="lsx-gbar__grip"
            aria-hidden
            tabIndex={-1}
            onPointerDown={onGripDown}
            onPointerMove={onGripMove}
            onPointerUp={onGripUp}
            onPointerCancel={onGripCancel}
          />
        ) : null}
        {bl.clippedRight ? (
          <span className="lsx-gbar__ovl lsx-gbar__ovl--r" aria-hidden>
            ›
          </span>
        ) : null}
      </div>
    );
  }

  // ---- Thẻ trong KHAY "Chưa xếp" (kéo được + bấm mở + "…" gán) ----
  function renderTrayChip(r: LichChayRow) {
    const due = hanGiao(r.han_giao_noi_bo ?? r.han_giao_khach);
    const level = due?.level ?? "ok";
    const specChips = [
      ...(r.spec_tom_tat || "").split(" · ").map((s) => s.trim()).filter(Boolean),
      ...(r.giay_label ? [r.giay_label] : []),
    ];
    const needMold = r.can_khuon && !r.khuon_be_id;
    const menuOpen = menu?.lenhId === r.lenh_id;
    return (
      <div
        key={r.lenh_id}
        role="button"
        tabIndex={0}
        className={`lsx-lchip lsx-lchip--${level}${draggingId === r.lenh_id ? " is-dragging" : ""}`}
        draggable
        aria-label={`Lệnh ${r.ma} · chưa xếp${due ? ` · ${due.label}` : ""}`}
        onClick={() => onOpen(r.lenh_id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpen(r.lenh_id);
          }
        }}
        onDragStart={(e) => {
          dragRef.current = {
            lenhId: r.lenh_id,
            fromMayId: r.may_id,
            fromNgay: r.ngay_chay?.slice(0, 10) ?? null,
          };
          e.dataTransfer.setData("text/plain", String(r.lenh_id));
          e.dataTransfer.effectAllowed = "move";
          setDraggingId(r.lenh_id);
        }}
        onDragEnd={clearDrag}
      >
        <div className="lsx-lchip__top">
          <span className="lsx-lchip__code mono">{r.ma}</span>
          {needMold ? (
            <span className="lsx-badge lsx-badge--danger lsx-lchip__flag">
              <Scissors size={11} /> Chưa khuôn
            </span>
          ) : null}
          <button
            type="button"
            className="lsx-lchip__more"
            aria-label="Xếp vào máy / ngày"
            aria-haspopup="dialog"
            aria-expanded={menuOpen}
            draggable={false}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              anchorMenu(e.currentTarget, r.lenh_id);
            }}
          >
            <MoreHorizontal size={16} />
          </button>
        </div>
        <div className="lsx-lchip__name">
          {[r.order_no, r.khach].filter(Boolean).join(" · ") || "—"}
        </div>
        {specChips.length > 0 ? (
          <div className="lsx-specchips">
            {specChips.map((c, i) => (
              <span className="lsx-specchip" key={i}>
                <span className="lsx-specchip__v">{c}</span>
              </span>
            ))}
          </div>
        ) : null}
        {due ? (
          <span className={`lsx-due lsx-due--${due.level}`}>
            <Clock size={12} /> {due.label}
          </span>
        ) : null}
      </div>
    );
  }

  const menuRow = menu ? (rows ?? []).find((r) => r.lenh_id === menu.lenhId) ?? null : null;

  return (
    <main className="lsx">
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <div className="lsx-eyebrow">
            <span className="sq" /> Sản xuất · Lịch chạy
          </div>
          <h1 className="lsx-head__title">Lịch chạy máy in</h1>
          <p className="lsx-head__sub">
            Kéo thân thanh đổi máy/ngày · kéo đuôi đổi hạn nội bộ · bấm để mở lệnh. Máy chỉ ghi nhận.
          </p>
        </div>
        <div className="lsx-head__actions">
          <button type="button" className="lsx-back" onClick={onBack}>
            <ChevronLeft size={16} /> Danh sách lệnh
          </button>
          <div className="lsx-lich__nav">
            <button type="button" className="lsx-lich__navbtn" onClick={() => shiftWeek(-1)}>
              <ChevronLeft size={15} /> Tuần trước
            </button>
            <button type="button" className="lsx-lich__navbtn" onClick={goToday}>
              <Calendar size={14} /> Hôm nay
            </button>
            <button type="button" className="lsx-lich__navbtn" onClick={() => shiftWeek(1)}>
              Tuần sau <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </header>

      {error ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-2)" }}>
          <span>{error}</span>
          <button
            type="button"
            className="btn btn--ghost"
            style={{ padding: "4px 12px", fontSize: "12px" }}
            onClick={load}
          >
            Tải lại
          </button>
        </div>
      ) : null}

      {rows === null ? (
        <div className="lsx-msg">Đang tải lịch chạy…</div>
      ) : machineRows.length === 0 ? (
        <div className="lsx-empty">
          <Calendar size={44} strokeWidth={1.4} className="lsx-empty__icon" />
          <p className="lsx-empty__title">Chưa có máy in trong danh mục</p>
          <p className="lsx-empty__sub">
            Thêm máy in ở danh mục Thiết bị &amp; Máy in để lên lịch chạy.
          </p>
        </div>
      ) : (
        <div className="lsx-lich">
          <aside className="lsx-lich__tray">
            <div className="lsx-panel">
              <div className="lsx-panel__hd">
                <h3>
                  <Clock size={16} /> Chưa xếp lịch · {unscheduled.length}
                </h3>
              </div>
              <div
                className={`lsx-lich__traylist${dropKey === "tray" ? " is-drop" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDropKey("tray");
                }}
                onDragLeave={() => setDropKey((p) => (p === "tray" ? null : p))}
                onDrop={(e) => {
                  e.preventDefault();
                  onDropTray();
                }}
              >
                {unscheduled.length === 0 ? (
                  <div className="lsx-empty lsx-empty--sm">
                    <p className="lsx-empty__title">Mọi lệnh đã lên lịch</p>
                  </div>
                ) : (
                  unscheduled.map((r) => renderTrayChip(r))
                )}
              </div>
            </div>
          </aside>

          <div className="lsx-lich__gridwrap">
            <div
              className="lsx-lich__grid"
              style={{ gridTemplateColumns: `132px repeat(${days.length}, minmax(150px, 1fr))` }}
            >
              <div className="lsx-lich__corner" />
              {days.map((d) => {
                const k = ymd(d);
                const we = d.getDay() === 0 || d.getDay() === 6;
                return (
                  <div
                    key={k}
                    className={`lsx-lich__day${k === todayStr ? " lsx-lich__day--today" : ""}${we ? " lsx-lich__day--we" : ""}`}
                  >
                    <span className="lsx-lich__dayw">{WD[mondayIdx(d.getDay())]}</span>
                    <span className="lsx-lich__dayd">
                      {d.getDate()}/{d.getMonth() + 1}
                    </span>
                  </div>
                );
              })}

              {machineRows.map((m) => {
                const bars = barsByMachine.get(m.id) ?? [];
                const cover = coverByMachine.get(m.id) ?? [0, 0, 0, 0, 0, 0, 0];
                const clashDays = cover.filter((c) => c >= 2).length;
                // MOCK công suất + tải: tải NGÀY = tổng tờ in của các lệnh BẮT ĐẦU chạy đúng ngày đó.
                const congSuat = mockCongSuat(m);
                const tai = [0, 0, 0, 0, 0, 0, 0];
                bars.forEach((b) => {
                  if (!b.clippedLeft && b.startIdx >= 0 && b.startIdx < 7) {
                    tai[b.startIdx] += mockToIn(b.row.lenh_id);
                  }
                });
                const overDays = tai.filter((t) => t > congSuat).length;
                return (
                  <div key={m.id} className="lsx-lich__mrow" style={{ display: "contents" }}>
                    <div className="lsx-lich__mach">
                      <span className="lsx-lich__machname">{m.ten}</span>
                      <span className="lsx-lich__machma mono">{m.ma}</span>
                      <span className="lsx-lich__machcap">
                        <Gauge size={10} /> {fmtTo(congSuat)} tờ/ngày <em>mock</em>
                      </span>
                      {clashDays > 0 ? (
                        <span className="lsx-grow__clash">
                          <AlertTriangle size={11} /> Kẹt máy · {clashDays} ngày chồng
                        </span>
                      ) : null}
                      {overDays > 0 ? (
                        <span className="lsx-grow__over">
                          <AlertTriangle size={11} /> Quá tải · {overDays} ngày
                        </span>
                      ) : null}
                    </div>
                    <div className="lsx-gtrack">
                      <div className="lsx-gcells">
                        {days.map((d, ci) => {
                          const k = ymd(d);
                          const we = d.getDay() === 0 || d.getDay() === 6;
                          const cellKey = `${m.id}|${k}`;
                          const isClash = cover[ci] >= 2;
                          const isOver = tai[ci] > congSuat;
                          return (
                            <div
                              key={k}
                              aria-hidden
                              className={
                                "lsx-gcell" +
                                (we ? " lsx-gcell--we" : "") +
                                (k === todayStr ? " lsx-gcell--today" : "") +
                                (dropKey === cellKey ? " lsx-gcell--drop" : "") +
                                (isOver ? " lsx-gcell--over" : "") +
                                (isClash ? " lsx-gcell--clash" : "")
                              }
                              onDragOver={(e) => {
                                e.preventDefault();
                                setDropKey(cellKey);
                              }}
                              onDragLeave={() => setDropKey((p) => (p === cellKey ? null : p))}
                              onDrop={(e) => {
                                e.preventDefault();
                                onDropCell(m.id, k);
                              }}
                            >
                              {tai[ci] > 0 ? (
                                <span className={"lsx-gcell__load" + (isOver ? " is-over" : "")}>
                                  {isOver ? `${fmtTo(tai[ci])} / ${fmtTo(congSuat)}` : fmtTo(tai[ci])}
                                </span>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                      <div className="lsx-gbars">
                        {bars.map((bl) => renderBar(bl, m))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {menu && menuRow ? (
        <div
          ref={menuRef}
          className="lsx-gpop"
          role="dialog"
          aria-label={`Xếp lịch lệnh ${menuRow.ma}`}
          style={{
            left: menu.left,
            top: menu.top,
            transform: menu.above ? "translateY(-100%)" : undefined,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="lsx-gpop__hd">
            <span className="lsx-gpop__code mono">{menuRow.ma}</span>
            <span className="lsx-gpop__tt">Xếp lịch chạy</span>
          </div>
          <label className="lsx-gpop__f">
            <span className="lsx-gpop__lb">Máy in</span>
            <select
              className="lsx-gpop__in"
              value={menuRow.may_id ?? ""}
              onChange={(e) =>
                performMove(
                  menuRow.lenh_id,
                  e.target.value ? Number(e.target.value) : null,
                  menuRow.ngay_chay?.slice(0, 10) ?? null,
                )
              }
            >
              <option value="">— chọn máy</option>
              {machineRows.map((mm) => (
                <option key={mm.id} value={mm.id}>
                  {mm.ten}
                </option>
              ))}
            </select>
          </label>
          <label className="lsx-gpop__f">
            <span className="lsx-gpop__lb">Ngày bắt đầu</span>
            <input
              type="date"
              className="lsx-gpop__in"
              value={menuRow.ngay_chay?.slice(0, 10) ?? ""}
              onChange={(e) =>
                performMove(menuRow.lenh_id, menuRow.may_id, e.target.value || null)
              }
            />
          </label>
          <label className="lsx-gpop__f">
            <span className="lsx-gpop__lb">Hạn nội bộ</span>
            {menuRow.trang_thai === "nhap" ? (
              <input
                type="date"
                className="lsx-gpop__in"
                value={menuRow.han_giao_noi_bo?.slice(0, 10) ?? ""}
                min={menuRow.ngay_chay?.slice(0, 10) ?? undefined}
                onChange={(e) => {
                  if (e.target.value) performResize(menuRow.lenh_id, e.target.value);
                }}
              />
            ) : (
              <span className="lsx-gpop__locked">
                <Lock size={12} /> Hạn đã khóa (đã phát)
              </span>
            )}
          </label>
          {menuRow.may_id != null || menuRow.ngay_chay != null ? (
            <button
              type="button"
              className="lsx-gpop__rm"
              onClick={() => {
                performMove(menuRow.lenh_id, null, null);
                setMenu(null);
              }}
            >
              Gỡ khỏi lịch
            </button>
          ) : null}
        </div>
      ) : null}

      <ToastStack toasts={toasts} onDismiss={toastDismiss} />
    </main>
  );
}
