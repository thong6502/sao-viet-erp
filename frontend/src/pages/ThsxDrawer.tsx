// DRAWER một công việc của bàn THỰC HIỆN SẢN XUẤT (`/work-items/{id}` detail).
//
// Các khối (§3):
//  1) THANH KẾ HOẠCH — dự kiến bắt đầu→kết thúc · máy · dải phút chạy · khối lượng + đơn vị bản
//     địa · kíp chuẩn/đang có (chỉ ĐỌC, số kế hoạch), kèm DẶN DÒ của kế hoạch và thẻ QUY CÁCH
//     gấp/mở — thẻ việc phải TỰ ĐỦ để làm: tổ trưởng không có quyền `lsx` để tra ngược hồ sơ lệnh.
//  2) TỔ THỰC HIỆN (roster) — người `active`; ô "Giao người" (combobox từ `nhanVienChon`, loại người
//     đã trong roster; bước nội bộ `loai_buoc="to"` chỉ nhận thợ LƯƠNG KHOÁN) + nút Rút.
//  3) PHIÊN CHẠY — Bắt đầu / Tạm dừng / Kết thúc (điều kiện bật ở §8) + danh sách phiên + khoảng
//     tham gia (bảng phụ gấp/mở).
//  4) PHA SAU (Giai đoạn 3+4) — sản lượng · bàn giao · vật tư · hỗ trợ chéo · chia sản lượng, dựng ở
//     `ThsxExecPanels`; mọi mặt GHI đi qua `exec.*` (controller lo khoá lạc quan + refetch + toast).
//
// Component KHÔNG tự gọi API ghi: phát ý định qua callback; controller lo dialog lý do + version lạc quan.
import { useEffect, useMemo, useRef, useState } from "react";
import { assetUrl } from "../api/client";
import type {
  SxNhanVienChon, SxWorkItemChiTiet, SxHoTroUngVien, SxQuyCachThe,
} from "../api/client";
import type { MayChon } from "../api/kyThuatMay";
import { Button } from "../components/Button";
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { Icon } from "../components/Icons";
import { num, ngayGio } from "./keHoachSxShared";
import { nhanChang } from "./lsxBuoc";
import { phutChayText, slText, sxSerial, ThsxTrangThaiPill } from "./thsxShared";
import { ThsxBaoSuCoDialog } from "./ThsxBaoSuCoDialog";
import { ThsxDoiMay } from "./ThsxDoiMay";
import { ThsxExecPanels, ThsxNhanVe, type ThsxExec } from "./ThsxExecPanels";
import type { SxChoCuaViec } from "./thsxChoXacNhan";
import { ThsxTepLenh } from "./ThsxTepLenh";
import { ThsxKetQuaKcs } from "./ThsxKetQuaKcs";

interface Props {
  chiTiet: SxWorkItemChiTiet | null;
  loading: boolean;
  /** Người chọn được cho ô "Giao người" (endpoint riêng của module, gác `san_xuat:read`). */
  candidates: SxNhanVienChon[];
  /** Ứng viên HỖ TRỢ CHÉO (§9) — thợ tổ SX khác đang làm (endpoint riêng module). */
  hoTroUngVien: SxHoTroUngVien[];
  /** Danh mục máy (`may-chon` — không đòi quyền `dm_thiet_bi`), chỉ để dựng nhãn máy hiện tại cho
   *  Báo sự cố. Ô "Đổi máy" KHÔNG dùng: nó tự nạp danh sách theo công đoạn + tình trạng (`ThsxDoiMay`). */
  mayOptions: MayChon[];
  /** Hợp đồng các mặt GHI của Giai đoạn 3+4+5. */
  exec: ThsxExec;
  /** Có một lệnh ghi đang bay (khoá nút để tránh double-submit). */
  busy: boolean;
  onGiao: (employeeId: number) => void;
  onRut: (phanCongId: number) => void;
  onBatDau: () => void;
  /** Tổ tích "đã nhận khuôn/khung" — cổng DUY NHẤT mở nút Bắt đầu cho bước cần dụng cụ. */
  onNhanKhuon: () => void;
  /** Tích trả khuôn về kệ sau khi làm xong (không bắt buộc, chỉ để kho biết dao đang ở đâu). */
  onTraKhuon: () => void;
  onTamDung: () => void;
  onKetThuc: () => void;
  onClose: () => void;
  /** Tab mở sẵn — công đoạn đang có việc chờ tổ bấm thì mở thẳng chỗ bấm (Nhận / KCS / Bàn giao).
   *  Chỉ đọc lúc mount. */
  tabDau?: ThsxDrawerTab;
  /** Bộ đếm SSE tệp đính kèm theo lệnh (AppShell) — thẻ "Tệp của lệnh" tự nạp lại khi lệnh của nó đổi. */
  dinhKemDem?: Record<number, number>;
  /** Nhịp nạp lại mục "Kết quả KCS" (SSE + sau mỗi lần ghi của bàn). */
  kcsTick?: number;
  /** Lỗi KCS đang chờ người xem bấm "Đã xem" — chỉ những lỗi này mới bày nút. */
  kcsLoiChoXem?: ReadonlySet<number>;
  /** Việc chờ tổ bấm của CHÍNH công việc đang mở (§11.5) — chấm đỏ trên tab nơi bấm: Nhận (bàn
   *  giao đến), Bàn giao & Vật tư (hỗ trợ chéo), KCS (lỗi chưa xem). */
  cho?: SxChoCuaViec;
  onDaXemKcs?: (loiId: number) => void;
}

export type ThsxDrawerTab = "van_hanh" | "nhan" | "ban_giao" | "kcs";

const DONG_LABEL: Record<string, string> = {
  tam_dung: "tạm dừng",
  ket_thuc: "kết thúc",
  // Đổi máy giữa chừng KHÔNG phải tạm dừng thật (§7.2 mở rộng 31/08/2026, review vòng 1) — nhãn
  // riêng để người xem lịch sử phiên không hiểu lầm công việc đã dừng.
  doi_may: "đổi máy",
};

// THẺ QUY CÁCH (§6) — thứ tự đọc của người đứng máy: giấy → khổ → mặt/màu/kẽm → con/tờ → SL đặt.
// Server BỎ HẲN khoá không có số, nên bảng này chỉ là NHÃN + đuôi đơn vị; hàng nào thiếu thì
// không vẽ. Khoá `ghi_chu_ky_thuat` là chữ nên tách ra khỏi bảng (vẽ thành đoạn riêng bên dưới).
const QUY_CACH_DONG: [keyof SxQuyCachThe, string, string][] = [
  ["giay", "Giấy", ""],
  ["dinh_luong", "Định lượng", " gsm"],
  ["kho_in", "Khổ tờ in", " mm"],
  ["kho_tp", "Khổ thành phẩm", " mm"],
  ["so_mat", "Số mặt", ""],
  ["so_mau", "Số màu", ""],
  ["so_kem", "Số kẽm", " bản"],
  ["so_con", "Con / tờ", ""],
  ["so_luong", "SL đặt của đơn", ""],
];

function khoangTimeText(batDau: string | null | undefined, ketThuc: string | null | undefined): string {
  if (!batDau) return "—";
  const d1 = new Date(batDau);
  if (Number.isNaN(d1.getTime())) return "—";
  const m1 = String(d1.getMonth() + 1).padStart(2, "0");
  const dt1 = String(d1.getDate()).padStart(2, "0");
  const hh1 = String(d1.getHours()).padStart(2, "0");
  const mm1 = String(d1.getMinutes()).padStart(2, "0");
  const str1 = `${dt1}/${m1} ${hh1}:${mm1}`;

  if (!ketThuc) return `${str1} → Đang chạy`;
  const d2 = new Date(ketThuc);
  if (Number.isNaN(d2.getTime())) return `${str1} → —`;

  const hh2 = String(d2.getHours()).padStart(2, "0");
  const mm2 = String(d2.getMinutes()).padStart(2, "0");

  if (d1.toDateString() === d2.toDateString()) {
    const diffMin = Math.round((d2.getTime() - d1.getTime()) / 60000);
    const minText = diffMin > 0 ? ` (${diffMin}p)` : "";
    return `${str1} → ${hh2}:${mm2}${minText}`;
  }

  const m2 = String(d2.getMonth() + 1).padStart(2, "0");
  const dt2 = String(d2.getDate()).padStart(2, "0");
  return `${str1} → ${dt2}/${m2} ${hh2}:${mm2}`;
}

/** Ảnh đại diện của thợ; chưa có ảnh (hoặc ảnh tải hỏng) thì vẽ chữ cái đầu như cũ. */
function AnhNguoi({ ten, url, size }: { ten: string; url?: string | null; size?: number }) {
  const [srcHong, setSrcHong] = useState<string | null>(null);
  const src = assetUrl(url);
  const style = size ? { width: size, height: size, fontSize: size / 2 } : undefined;
  return (
    <span className="thsx-roster-avatar-glow" style={style}>
      {src && src !== srcHong
        ? <img src={src} alt="" onError={() => setSrcHong(src)} />
        : (ten ? ten.trim().charAt(0).toUpperCase() : "T")}
    </span>
  );
}

export function ThsxDrawer({
  chiTiet, loading, candidates, hoTroUngVien, mayOptions, exec, busy,
  onGiao, onRut, onBatDau, onNhanKhuon, onTraKhuon, onTamDung, onKetThuc, onClose, tabDau = "van_hanh", dinhKemDem,
  kcsTick, kcsLoiChoXem, cho, onDaXemKcs,
}: Props) {
  const [activeTab, setActiveTab] = useState<ThsxDrawerTab>(tabDau);
  // Ba tab dùng chung MỘT khung cuộn — đổi tab mà không kéo về đầu thì tab mới mở ra ở vị trí cuộn
  // của tab cũ (cuộn Vận hành tới đáy rồi bấm Bàn giao là thấy ngay đáy Bàn giao, mất phần đầu).
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [activeTab]);
  const [giaoOpen, setGiaoOpen] = useState(false);
  const [q, setQ] = useState("");
  const [moKhoang, setMoKhoang] = useState(false);
  const [doiMayOpen, setDoiMayOpen] = useState(false);
  // Báo sự cố (§7.2 mở rộng 31/08/2026) — ô nhập nằm trong ngăn kéo `ThsxBaoSuCoDialog`.
  const [suCoOpen, setSuCoOpen] = useState(false);

  const cv = chiTiet?.cong_viec ?? null;
  // Quyền TRÊN CHÍNH công việc này (máy chủ tính theo dòng quyền của tổ; mức "Của tôi" chỉ bật khi
  // việc đang giao cho mình). Vận hành = Thực hiện lệnh; KCS = KCS; nhập kho = Kho.
  const canAssign = !!chiTiet?.quyen?.run_order;
  // Nút tắt vì hai lý do khác nhau: không được cấp Thực hiện lệnh, hoặc có nhưng mức "Của tôi" mà
  // việc chưa giao cho mình. Câu báo phải nói đúng lý do — người đã bật quyền đọc "cần quyền" là
  // tưởng hệ thống lỗi (16/09/2026).
  const chuaGiaoChoToi = !canAssign && chiTiet?.quyen_muc?.run_order === "own";
  const tt = chiTiet?.trang_thai ?? cv?.trang_thai ?? "released";
  const isTo = cv?.loai_buoc === "to";
  const isMay = cv?.loai_buoc === "may" || cv?.loai_buoc === "thue_ngoai";
  const canDoiMay = canAssign && !busy && (tt === "running" || tt === "paused") && isMay;
  const canBaoSuCo = canDoiMay;

  const rosterActive = useMemo(
    () => (chiTiet?.phan_cong ?? []).filter((p) => p.trang_thai === "active"),
    [chiTiet],
  );
  const mayHienTai = mayOptions.find((m) => m.id === cv?.may_id);
  const mayNhanSuCo = mayHienTai ? `${mayHienTai.ma} · ${mayHienTai.ten}` : (cv?.may ?? "—");
  const lechKip = cv?.du_kien_so_nguoi != null && rosterActive.length !== cv.du_kien_so_nguoi;
  const phutChay = cv ? phutChayText(cv) : null;
  
  // Dòng quy cách hiển thị bảng (Option A: Inline Spec Table)
  const quyCachItems = useMemo(
    () => (cv?.quy_cach ? QUY_CACH_DONG.filter(([k]) => cv.quy_cach![k] != null) : []),
    [cv?.quy_cach],
  );

  const hasKhoan = rosterActive.some((p) => p.la_luong_khoan);
  const done = tt === "completed";
  const khuonChoNhan = !!cv?.khuon && !cv?.khuon_da_nhan;
  const canBatDau =
    canAssign && !busy && (tt === "released" || tt === "paused") && hasKhoan && !khuonChoNhan;
  const canTamDung = canAssign && !busy && tt === "running";
  const canKetThuc = canAssign && !busy && (tt === "running" || tt === "paused");
  const canGiao = canAssign && !done;

  const activeIds = useMemo(() => new Set(rosterActive.map((p) => p.employee_id)), [rosterActive]);
  const dsChon = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return candidates
      .filter((c) => !activeIds.has(c.id))
      .filter((c) => !kw || c.full_name.toLowerCase().includes(kw) || (c.code ?? "").toLowerCase().includes(kw));
  }, [candidates, activeIds, q]);


  // Tiến độ sản xuất % — cùng mốc với dòng bảng (`ThsxDanhSach`) và ô "Còn thiếu": mục tiêu ĐẦU RA
  // (đã rút theo thực nhận), không phải lượng vào. Lấy `thuc_nhan`/`so_luong_vao` như trước là chia
  // sản lượng tờ ra cho số tờ vào có bù hao: In 0004 làm đủ 5.340 cũng chỉ 94% "của 5.690".
  const targetVal = cv?.muc_tieu ?? cv?.so_luong_ra ?? 0;
  const currentVal = cv?.da_lam || 0;
  const progressPct = targetVal > 0 ? Math.min(100, Math.round((currentVal / targetVal) * 100)) : 0;

  function chon(c: SxNhanVienChon) {
    if (isTo && !c.la_luong_khoan) return;
    onGiao(c.id);
    setGiaoOpen(false);
    setQ("");
  }

  const serial = cv ? sxSerial(cv.nguon_ma) : "";

  return (
    <div className="thsx-panel__inner">
      {/* 1 · HERO HEADER */}
      <div className="thsx-panel__head">
        <div className="thsx-panel__title">
          {cv ? (
            <>
              <span className="thsx-panel__serial">{serial}</span>
              <span className="thsx-panel__cd">{cv.ten_cong_doan}</span>
              <ChipLoaiBuoc loai_buoc={cv.loai_buoc} nha_cung_cap={cv.nha_cung_cap} />
            </>
          ) : (
            <span className="thsx-panel__cd">Chi tiết công việc</span>
          )}
        </div>
        {chiTiet && <ThsxTrangThaiPill tt={tt} />}
        <button type="button" className="thsx-panel__close" onClick={onClose} aria-label="Đóng">
          <Icon name="x" size={16} />
        </button>
      </div>

      {/* 1B · MINI KPI STRIP (TOP QUICK SUMMARY) */}
      {cv && (
        <div className="thsx-mini-kpis">
          <span className="thsx-mini-kpi-item">
            {tt === "running" && <span className="thsx-pulse-dot" style={{ marginRight: 4 }} />}
            <Icon name="clock" size={13} style={{ color: "#64748b" }} /> Dự kiến: <b>{phutChay || "—"}</b>
          </span>
          <span className="thsx-mini-kpi-item">
            <Icon name="box" size={13} style={{ color: "#64748b" }} /> Mục tiêu: <b>{num(targetVal)}{cv.don_vi_ra ? ` ${nhanChang(cv.don_vi_ra)}` : ""}</b>
          </span>
          <span className="thsx-mini-kpi-item">
            <Icon name="users" size={13} style={{ color: "#64748b" }} /> Kíp: <b>{rosterActive.length}/{cv.du_kien_so_nguoi ?? 1} thợ</b>
          </span>
        </div>
      )}

      {/* 2 · TAB NAVIGATION BAR (OPTION 2: TABBED SIDEBAR) */}
      {cv && (
        <div className="thsx-drawer-tabs">
          <div className="thsx-drawer-tabs__track" role="tablist">
            <button
              type="button"
              className={`thsx-drawer-tab${activeTab === "van_hanh" ? " is-active" : ""}`}
              onClick={() => setActiveTab("van_hanh")}
              role="tab"
              aria-selected={activeTab === "van_hanh"}
            >
              <Icon name="cpu" size={13} /> Vận hành &amp; Quy cách
            </button>
            {/* Nhận đứng TRƯỚC Bàn giao: thứ tự việc đến tay tổ — nhận hàng, làm, giao đi. */}
            <button
              type="button"
              className={`thsx-drawer-tab${activeTab === "nhan" ? " is-active" : ""}`}
              onClick={() => setActiveTab("nhan")}
              role="tab"
              aria-selected={activeTab === "nhan"}
            >
              <Icon name="packageCheck" size={13} /> Nhận
              {!!cho?.nhan && <span className="thsx-drawer-tab__dot" title="Có bàn giao chờ tổ nhận" />}
            </button>
            <button
              type="button"
              className={`thsx-drawer-tab${activeTab === "ban_giao" ? " is-active" : ""}`}
              onClick={() => setActiveTab("ban_giao")}
              role="tab"
              aria-selected={activeTab === "ban_giao"}
            >
              <Icon name="truck" size={13} /> Bàn giao &amp; Vật tư
              {!!cho?.hoTro && <span className="thsx-drawer-tab__dot" title="Có hỗ trợ chéo chờ tổ xác nhận" />}
            </button>
            <button
              type="button"
              className={`thsx-drawer-tab${activeTab === "kcs" ? " is-active" : ""}`}
              onClick={() => setActiveTab("kcs")}
              role="tab"
              aria-selected={activeTab === "kcs"}
            >
              <Icon name="shield" size={13} /> KCS
              {!!cho?.kcs && <span className="thsx-drawer-tab__dot" title="Có lỗi KCS chờ tổ xem" />}
            </button>
          </div>
        </div>
      )}

      <div className="thsx-panel__body" ref={bodyRef}>
        {loading && !chiTiet ? (
          <div className="thsx-panel__loading">Đang tải…</div>
        ) : !cv || !chiTiet ? (
          <div className="thsx-panel__empty">Không tải được chi tiết công việc.</div>
        ) : (
          <>
            {/* ================= TAB 1: VẬN HÀNH & QUY CÁCH ================= */}
            {activeTab === "van_hanh" && (
              <>
                {/* 1A · GHI CHÚ KỸ THUẬT — ô "Ghi chú kỹ thuật cho thợ" của bước, ĐẦU TAB để thợ đọc dặn dò
                    trước mọi thứ (16/09/2026). LUÔN hiện (kể cả trống) vì bảng danh sách không còn dòng
                    mở rộng để xem nhanh: thợ phải biết là không có dặn dò. */}
                {cv.ghi_chu?.trim() ? (
                  <div className="thsx-card" style={{ background: "#fffbebe6", borderColor: "#fde68a" }}>
                    <div className="thsx-psec__h">
                      <Icon name="alert" size={14} style={{ color: "#d97706" }} />
                      <span className="thsx-psec__title" style={{ color: "#b45309" }}>Ghi chú kỹ thuật</span>
                    </div>
                    <p className="thsx-dando">{cv.ghi_chu}</p>
                  </div>
                ) : (
                  <div className="thsx-card">
                    <div className="thsx-psec__h">
                      <Icon name="fileText" size={14} />
                      <span className="thsx-psec__title">Ghi chú kỹ thuật</span>
                    </div>
                    <p className="thsx-dando thsx-dando--trong">Không có dặn dò riêng</p>
                  </div>
                )}

                {/* 1B · THỰC TẾ SẢN XUẤT & PRODUCTION HUB */}
                <div className="thsx-card thsx-prod-hub">
                  <div className="thsx-psec__h">
                    <Icon name="activity" size={14} />
                    <span className="thsx-psec__title">Tiến độ sản xuất thực tế</span>
                    <span className="thsx-prod-hub__pct">{progressPct}%</span>
                  </div>

                  {targetVal > 0 && (
                    <div className="thsx-progress-box" style={{ margin: "4px 0 4px 0" }}>
                      <div className="thsx-progress-bar" style={{ height: "6px" }}>
                        <div className="thsx-progress-fill" style={{ width: `${progressPct}%` }} />
                      </div>
                    </div>
                  )}

                  <div className="thsx-flat-metric-strip">
                    <div className="thsx-flat-metric-col">
                      <span className="thsx-metric-lbl">Đã làm</span>
                      <span className="thsx-metric-val thsx-metric-val--done">
                        {num(cv.da_lam || 0)}
                        {cv.don_vi_ra ? <span className="thsx-metric-unit">{nhanChang(cv.don_vi_ra)}</span> : null}
                      </span>
                    </div>
                    <div className="thsx-flat-metric-col">
                      <span className="thsx-metric-lbl">Thực nhận</span>
                      <span className="thsx-metric-val">
                        {cv.thuc_nhan != null ? (
                          <>
                            {num(cv.thuc_nhan)}
                            {cv.don_vi_vao ? <span className="thsx-metric-unit">{nhanChang(cv.don_vi_vao)}</span> : null}
                          </>
                        ) : (
                          <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: "normal" }}>Chưa giao</span>
                        )}
                      </span>
                    </div>
                    <div className="thsx-flat-metric-col">
                      <span className="thsx-metric-lbl">Còn thiếu</span>
                      <span className={`thsx-metric-val${(cv.con_thieu ?? 0) > 0 ? " thsx-metric-val--thieu" : ""}`}>
                        {cv.con_thieu == null ? (
                          "—"
                        ) : cv.con_thieu > 0 ? (
                          <>
                            {num(cv.con_thieu)}
                            {cv.don_vi_ra ? <span className="thsx-metric-unit">{nhanChang(cv.don_vi_ra)}</span> : null}
                          </>
                        ) : (
                          "Đủ"
                        )}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 1C · THẺ QUY CÁCH CHẠY MÁY (BẢNG PHẲNG 2 CỘT SIÊU MẢNH - PHẲNG TĂM TẮP) */}
                {cv.quy_cach && (
                  <div className="thsx-card">
                    <div className="thsx-psec__h">
                      <Icon name="layers" size={14} />
                      <span className="thsx-psec__title" style={{ color: "var(--rust-deep)" }}>
                        Quy cách chạy máy
                      </span>
                    </div>
                    <div className="thsx-flat-spec-grid">
                      {quyCachItems.map(([k, nhan, duoi]) => (
                        <div className="thsx-flat-spec-item" key={k}>
                          <span className="thsx-flat-spec-lbl">{nhan}:</span>
                          <span className="thsx-flat-spec-val">{`${cv.quy_cach![k]}${duoi}`}</span>
                        </div>
                      ))}
                    </div>
                    {cv.quy_cach.ghi_chu_ky_thuat && (
                      <div style={{ marginTop: "8px", paddingTop: "6px", borderTop: "1px solid #f1f5f9" }}>
                        <p className="thsx-dando" style={{ fontSize: "12px", color: "#475569" }}>
                          {cv.quy_cach.ghi_chu_ky_thuat}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* 1D · KẾ HOẠCH & MÁY GÁN (GRID 2 CỘT MINI MATRIX) */}
                <section className="thsx-psec">
                  <div className="thsx-psec__h">
                    <Icon name="clock" size={14} />
                    <span className="thsx-psec__title">Thông tin kế hoạch</span>
                  </div>
                  <div className="thsx-plan-grid-2col">
                    <div className="thsx-plan-grid-item">
                      <span className="thsx-plan-lbl">Dự kiến:</span>
                      <span className="thsx-plan-val">
                        {cv.du_kien_bat_dau ? ngayGio(cv.du_kien_bat_dau) : "—"}
                        {" đến "}
                        {cv.du_kien_ket_thuc ? ngayGio(cv.du_kien_ket_thuc) : "—"}
                      </span>
                    </div>
                    {phutChay && (
                      <div className="thsx-plan-grid-item">
                        <span className="thsx-plan-lbl">Chạy máy:</span>
                        <span className="thsx-plan-val">{phutChay}</span>
                      </div>
                    )}
                    {cv.may && (
                      <div className="thsx-plan-grid-item">
                        <span className="thsx-plan-lbl">Máy:</span>
                        <span className="thsx-plan-val" style={{ fontWeight: "700", color: "#0284c7" }}>
                          {cv.may}
                        </span>
                      </div>
                    )}
                    <div className="thsx-plan-grid-item">
                      <span className="thsx-plan-lbl">Khối lượng:</span>
                      <span className="thsx-plan-val">{slText(cv)}</span>
                    </div>
                    {cv.du_kien_so_nguoi != null && (
                      <div className="thsx-plan-grid-item">
                        <span className="thsx-plan-lbl">Kíp SX:</span>
                        <span className={`thsx-plan-val${lechKip ? " thsx-plan-val--thieu" : ""}`}>
                          Chuẩn {num(cv.du_kien_so_nguoi)} / Đang có {num(rosterActive.length)} thợ
                        </span>
                      </div>
                    )}
                    <div className="thsx-plan-grid-item">
                      <span className="thsx-plan-lbl">Nguồn LSX:</span>
                      <span className="thsx-plan-val">
                        {cv.nguon_ma}
                        {cv.nguon_ten ? ` (${cv.nguon_ten})` : ""}
                      </span>
                    </div>
                  </div>
                </section>

                {/* 1E · KHUÔN / KHUNG */}
                {cv.khuon && (
                  <section className="thsx-psec">
                    <div className="thsx-psec__h"><span className="thsx-psec__title">Khuôn &amp; khung</span></div>
                    <div className="thsx-khuon">
                      <ChipKhuon can_khuon khuon={{ ...cv.khuon, da_nhan: cv.khuon_da_nhan }} />
                      {cv.khuon.ten && <span className="thsx-khuon__ten">{cv.khuon.ten}</span>}
                      {cv.khuon.so_ke && !cv.khuon_da_nhan && (
                        <span className="thsx-khuon__ke">Lấy ở {cv.khuon.so_ke}</span>
                      )}
                    </div>
                    <div className="thsx-khuon__act">
                      {!cv.khuon_da_nhan && canAssign && (
                        <Button variant="secondary" onClick={onNhanKhuon} disabled={busy}>
                          Đã nhận khuôn
                        </Button>
                      )}
                      {/* Thiếu quyền thì nói ra, đừng để khối trống trơn: người xem tưởng hệ thống
                          không có chỗ tích nhận (16/09/2026). */}
                      {!cv.khuon_da_nhan && !canAssign && (
                        <span className="thsx-khuon__xong">
                          {chuaGiaoChoToi
                            ? "Việc này chưa giao cho bạn — quyền Thực hiện lệnh của bạn ở tổ này là “Của tôi”, chỉ áp cho việc được giao."
                            : "Cần quyền Thực hiện lệnh ở tổ này mới xác nhận nhận khuôn được."}
                        </span>
                      )}
                      {cv.khuon_da_nhan && !cv.khuon_da_tra && done && canAssign && (
                        <Button variant="ghost" onClick={onTraKhuon} disabled={busy}>
                          Đã trả khuôn về kệ
                        </Button>
                      )}
                      {cv.khuon_da_tra && <span className="thsx-khuon__xong">Đã trả về kệ.</span>}
                    </div>
                  </section>
                )}

                {/* 1F · TỔ THỰC HIỆN (ROSTER COMPACT GRID 2 CỘT) */}
                <section className="thsx-psec">
                  <div className="thsx-psec__h">
                    <span className="thsx-psec__title">Tổ thực hiện ({rosterActive.length})</span>
                    {canGiao && (
                      <div className="thsx-giao">
                        <Button variant="ghost" onClick={() => setGiaoOpen((o) => !o)} disabled={busy} aria-expanded={giaoOpen}>
                          <Icon name="plus" size={14} /> Giao người
                        </Button>
                        {giaoOpen && (
                          <div className="thsx-giao__pop" role="dialog" aria-label="Chọn người để giao">
                            <div className="thsx-giao__search">
                              <Icon name="search" size={14} />
                              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm tên / mã…" />
                            </div>
                            {isTo && (
                              <p className="thsx-giao__note">
                                Bước nội bộ không nhận người <b>công nhật</b>.
                              </p>
                            )}
                            <div className="thsx-giao__list">
                              {dsChon.length === 0 ? (
                                <div className="thsx-giao__empty">Không còn ai để giao.</div>
                              ) : dsChon.map((c) => {
                                const chan = isTo && !c.la_luong_khoan;
                                return (
                                  <button key={c.id} type="button" className="thsx-giao__opt"
                                    disabled={chan} onClick={() => chon(c)}
                                    title={chan ? "Công nhật — không giao vào bước nội bộ" : undefined}>
                                    <span className="thsx-giao__nm">{c.full_name}</span>
                                    {c.code && <span className="thsx-giao__code">{c.code}</span>}
                                    {/* Thợ tổ sản xuất mặc định hưởng khoán — chỉ đánh dấu ngoại lệ công nhật. */}
                                    {!c.la_luong_khoan && <span className="thsx-tag thsx-tag--nhat">công nhật</span>}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  {rosterActive.length === 0 ? (
                    <p className="thsx-note">Chưa giao ai — giao ít nhất 1 thợ để bắt đầu.</p>
                  ) : (
                    <ul className="thsx-roster-grid-2col">
                      {rosterActive.map((p) => (
                        <li key={p.id} className="thsx-roster-chip-card">
                          <div className="thsx-roster-chip-left">
                            <AnhNguoi ten={p.ho_ten} url={p.avatar_url} />
                            <span className="thsx-roster__nm">{p.ho_ten}</span>
                            {!p.la_luong_khoan && <span className="thsx-tag thsx-tag--nhat">công nhật</span>}
                          </div>
                          {canAssign && !done && (
                            <button type="button" className="thsx-roster__rut-chip" onClick={() => onRut(p.id)}
                              disabled={busy} title="Rút khỏi công việc">
                              <Icon name="x" size={12} />
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                {/* 1F' · TỆP CỦA LỆNH — maket/bản vẽ Kế hoạch SX đính kèm; tổ xem/tải, không sửa. */}
                <ThsxTepLenh congViecId={cv.id} dinhKemDem={dinhKemDem} />

                {/* 1G · PHIÊN CHẠY & KHOẢNG THAM GIA LOG */}
                <section className="thsx-psec">
                  <div className="thsx-psec__h">
                    <Icon name="history" size={14} />
                    <span className="thsx-psec__title">Lịch sử phiên chạy ({chiTiet.phien_chay.length})</span>
                  </div>
                  {chiTiet.phien_chay.length === 0 ? (
                    <p className="thsx-note">Chưa có phiên chạy nào.</p>
                  ) : (
                    <ul className="thsx-phien-timeline">
                      {chiTiet.phien_chay.map((ph) => {
                        const dang = ph.ket_thuc == null;
                        return (
                          <li key={ph.id} className={`thsx-phien-timeline__row${dang ? " is-run" : ""}`}>
                            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <span className="thsx-phien__no">#{ph.so_thu_tu}</span>
                              {dang && <span className="thsx-pulse-dot" />}
                              <span className="thsx-phien__time thsx-kv__v--num">
                                {khoangTimeText(ph.bat_dau, ph.ket_thuc)}
                              </span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                              {ph.may_ten && <span className="thsx-tag">{ph.may_ten}</span>}
                              {ph.loai_dong && (
                                <span className="thsx-phien__dong">{DONG_LABEL[ph.loai_dong] ?? ph.loai_dong}</span>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}

                  {chiTiet.khoang_tham_gia.length > 0 && (
                    <div style={{ marginTop: "6px" }}>
                      <button type="button" className="thsx-fold" onClick={() => setMoKhoang((o) => !o)} aria-expanded={moKhoang}>
                        <Icon name="chevron" size={13} /> Khoảng tham gia ({chiTiet.khoang_tham_gia.length})
                      </button>
                      {moKhoang && (
                        <ul className="thsx-kthamgia-list">
                          {chiTiet.khoang_tham_gia.map((k) => (
                            <li key={k.id} className="thsx-kthamgia-chip-row">
                              <div className="thsx-kthamgia-left">
                                <AnhNguoi ten={k.ho_ten} url={k.avatar_url} size={20} />
                                <span className="thsx-kthamgia-name">{k.ho_ten}</span>
                                <span className="thsx-phien__no" style={{ fontSize: 10, padding: "0 4px" }}>
                                  #{chiTiet.phien_chay.find((p) => p.id === k.phien_chay_id)?.so_thu_tu ?? "?"}
                                </span>
                              </div>
                              <span className="thsx-kthamgia-time-badge">
                                {khoangTimeText(k.bat_dau, k.ket_thuc)}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </section>
              </>
            )}

            {/* ================= TAB NHẬN: BÀN GIAO ĐẾN ================= */}
            {activeTab === "nhan" && <ThsxNhanVe chiTiet={chiTiet} busy={busy} exec={exec} />}

            {/* ================= TAB 2: BÀN GIAO & VẬT TƯ ================= */}
            {activeTab === "ban_giao" && (
              <ThsxExecPanels
                chiTiet={chiTiet}
                busy={busy}
                hoTroUngVien={hoTroUngVien}
                exec={exec}
              />
            )}

            {/* ================= TAB 3: KCS ================= */}
            {/* KCS kiểm công đoạn này (theo lệnh, mg 0306): các lần kiểm, lỗi + ảnh, nút "Đã xem". */}
            {activeTab === "kcs" && (
              <ThsxKetQuaKcs congViecId={cv.id} kcsTick={kcsTick} loiChoXem={kcsLoiChoXem}
                busy={busy} onDaXem={onDaXemKcs} />
            )}

          </>
        )}
      </div>

      {/* PINNED BOTTOM ACTION FOOTER BAR — việc Hoàn thành thì bỏ hẳn: mọi nút dưới đây (Bắt đầu,
          Đổi máy, Báo sự cố) chỉ chạy khi việc đang chạy/tạm dừng, để lại chỉ là hàng nút mờ vô dụng;
          trạng thái đã có ở đầu ngăn. */}
      {cv && !done && (
        <div className="thsx-glass-footer">
          {/* Lý do lệch kíp chỉ được hỏi lúc Bắt đầu / Tiếp tục (`thuc_thi.bat_dau`) — đang chạy thì câu
              này hứa một bước không còn nút nào dẫn tới. Chưa giao ai thì câu dưới ("Cần giao ít nhất
              1 thợ") mới là chỗ chặn thật; hiện thêm câu này chỉ gây nhầm là đang lệch GIỜ kế hoạch. */}
          {lechKip && rosterActive.length > 0 && (tt === "released" || tt === "paused") && (
            <div className="thsx-alert-capsule">
              <Icon name="alert" size={14} style={{ color: "#d97706" }} />
              <span>
                Số thợ khác kíp chuẩn ({rosterActive.length}/{cv.du_kien_so_nguoi}) — {tt === "paused" ? "Tiếp tục" : "Bắt đầu"} sẽ chọn lý do.
              </span>
            </div>
          )}
          {!hasKhoan && !done && tt !== "running" && (
            <div className="thsx-alert-capsule">
              <Icon name="alert" size={14} style={{ color: "#d97706" }} />
              {/* Máy chủ đòi ≥1 người hưởng khoán (`thuc_thi.bat_dau`); tổ không cần nghe chữ "khoán" —
                  chỉ khi người đang giao toàn công nhật mới phải nói vì sao vẫn chưa bắt đầu được. */}
              <span>
                {rosterActive.length === 0
                  ? "Cần giao ít nhất 1 thợ mới bắt đầu được."
                  : "Người đang giao đều là công nhật — cần thêm ít nhất 1 thợ không phải công nhật mới bắt đầu được."}
              </span>
            </div>
          )}
          {khuonChoNhan && !done && tt !== "running" && (
            <div className="thsx-alert-capsule">
              <Icon name="alert" size={14} style={{ color: "#d97706" }} />
              {/* Gọi đúng tên nút + tên mục, không chỉ hướng "khối trên": mục nằm dưới tầm mắt khi
                  mới mở drawer. Thiếu quyền thì nút không có — nói lý do thay vì bảo đi tìm nó. */}
              <span>
                Chưa nhận khuôn/khung{cv.khuon?.ma ? ` ${cv.khuon.ma}` : ""} —{" "}
                {canAssign
                  ? "bấm “Đã nhận khuôn” ở mục Khuôn & khung rồi mới Bắt đầu."
                  : chuaGiaoChoToi
                    ? "việc chưa giao cho bạn, mà quyền của bạn ở tổ này là “Của tôi”."
                    : "cần quyền Thực hiện lệnh ở tổ này mới xác nhận được."}
              </span>
            </div>
          )}

          <div className="thsx-run">
            {tt === "running" ? (
              <>
                <Button variant="secondary" onClick={onTamDung} disabled={!canTamDung}>
                  <Icon name="pause" size={14} /> Tạm dừng
                </Button>
                <Button variant="accent" onClick={onKetThuc} disabled={!canKetThuc}>
                  <Icon name="square" size={13} /> Kết thúc
                </Button>
              </>
            ) : (
              <>
                <Button variant="accent" onClick={onBatDau} disabled={!canBatDau}>
                  <Icon name="play" size={14} /> {tt === "paused" ? "Tiếp tục" : "Bắt đầu"}
                </Button>
                {tt === "paused" && (
                  <Button variant="secondary" onClick={onKetThuc} disabled={!canKetThuc}>
                    <Icon name="square" size={13} /> Kết thúc
                  </Button>
                )}
              </>
            )}
            {isMay && (
              <Button variant="ghost" onClick={() => setDoiMayOpen((o) => !o)} disabled={!canDoiMay} aria-expanded={doiMayOpen}>
                <Icon name="cpu" size={14} /> Đổi máy
              </Button>
            )}
            {isMay && (
              <Button variant="ghost" onClick={() => setSuCoOpen(true)} disabled={!canBaoSuCo} aria-haspopup="dialog">
                <Icon name="alert" size={14} /> Báo sự cố
              </Button>
            )}
          </div>

          {/* FORM ĐỔI MÁY & BÁO SỰ CỐ */}
          {doiMayOpen && cv && (
            <ThsxDoiMay congViecId={cv.id} mayHienTaiId={cv.may_id} tenCongDoan={cv.ten_cong_doan} busy={busy}
              onDoi={exec.doiMay} onClose={() => setDoiMayOpen(false)} />
          )}

          {suCoOpen && cv && (
            <ThsxBaoSuCoDialog
              mayNhan={mayNhanSuCo}
              dangChay={tt === "running"}
              busy={busy}
              onGui={exec.baoSuCo}
              onClose={() => setSuCoOpen(false)}
            />
          )}
        </div>
      )}
    </div>
  );
}

