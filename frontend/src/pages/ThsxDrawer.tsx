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
import { useMemo, useState } from "react";
import type {
  SxNhanVienChon, SxWorkItemChiTiet, SxHoTroUngVien,
  SxKcsChiTiet, SxKhoChiTiet, SxDongNhomDieuKien, SxQuyCachThe,
} from "../api/client";
import type { MayChon } from "../api/kyThuatMay";
import { Button } from "../components/Button";
import { ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { Icon } from "../components/Icons";
import { num, ngayGio } from "./keHoachSxShared";
import { nhanChang } from "./lsxBuoc";
import { phutChayText, slText, sxSerial, ThsxTrangThaiPill } from "./thsxShared";
import { ThsxBaoSuCoDialog } from "./ThsxBaoSuCoDialog";
import { ThsxExecPanels, type ThsxExec } from "./ThsxExecPanels";
import { ThsxKcsPanel, ThsxKhoPanel, ThsxDongNhomPanel, type Opt } from "./ThsxG5";

interface Props {
  chiTiet: SxWorkItemChiTiet | null;
  loading: boolean;
  canAssign: boolean;
  /** Người chọn được cho ô "Giao người" (endpoint riêng của module, gác `san_xuat:read`). */
  candidates: SxNhanVienChon[];
  /** Ứng viên HỖ TRỢ CHÉO (§9) — thợ tổ SX khác đang làm (endpoint riêng module). */
  hoTroUngVien: SxHoTroUngVien[];
  /** Máy chọn được cho ô "Đổi máy" (`may-chon` — không đòi quyền `dm_thiet_bi` như thợ đứng máy). */
  mayOptions: MayChon[];
  /** Hợp đồng các mặt GHI của Giai đoạn 3+4+5. */
  exec: ThsxExec;
  /** Giai đoạn 5 — KCS §13: mẻ kiểm tra + lỗi + ảnh (chỉ nạp khi bước `la_kcs`). */
  kcsCt: SxKcsChiTiet | null;
  /** Giai đoạn 5 — Kho §14: yêu cầu nhập + BTP dư (chỉ nạp khi `la_kcs` + có `nhom_id`). */
  khoCt: SxKhoChiTiet | null;
  /** Giai đoạn 5 — §16/§13.3: checklist cổng đóng nhóm (chỉ nạp khi `la_kcs_cuoi` + có `nhom_id`). */
  dieuKien: SxDongNhomDieuKien | null;
  /** §8 — thưởng/phạt tổ trưởng của nhóm. Nạp cho MỌI bước có `nhom_id`, không riêng KCS cuối:
   *  tổ trưởng tổ In cũng phải xem được điểm chất lượng của tổ mình ngay tại bước của họ. */
  /** Danh sách tổ có thể chỉ định "chịu trách nhiệm lỗi" (dẫn xuất từ ứng viên hỗ trợ). */
  toChiuOpts: Opt[];
  /** Công đoạn thượng nguồn có thể gán "liên đới lỗi" (dẫn xuất từ bàn giao đến). */
  congDoanRefOpts: Opt[];
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
}

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

export function ThsxDrawer({
  chiTiet, loading, canAssign, candidates, hoTroUngVien, mayOptions, exec, busy,
  kcsCt, khoCt, dieuKien, toChiuOpts, congDoanRefOpts,
  onGiao, onRut, onBatDau, onNhanKhuon, onTraKhuon, onTamDung, onKetThuc, onClose,
}: Props) {
  const [activeTab, setActiveTab] = useState<"van_hanh" | "ban_giao" | "kcs_kho">("van_hanh");
  const [giaoOpen, setGiaoOpen] = useState(false);
  const [q, setQ] = useState("");
  const [moKhoang, setMoKhoang] = useState(false);
  const [doiMayOpen, setDoiMayOpen] = useState(false);
  const [mayChonId, setMayChonId] = useState<number | "">("");
  const [lyDoMay, setLyDoMay] = useState("");
  // Báo sự cố (§7.2 mở rộng 31/08/2026) — ô nhập nằm trong ngăn kéo `ThsxBaoSuCoDialog`.
  const [suCoOpen, setSuCoOpen] = useState(false);

  const cv = chiTiet?.cong_viec ?? null;
  const tt = chiTiet?.trang_thai ?? cv?.trang_thai ?? "released";
  const isTo = cv?.loai_buoc === "to";
  const isMay = cv?.loai_buoc === "may" || cv?.loai_buoc === "thue_ngoai";
  const canDoiMay = canAssign && !busy && (tt === "running" || tt === "paused") && isMay;
  const canBaoSuCo = canDoiMay;

  const rosterActive = useMemo(
    () => (chiTiet?.phan_cong ?? []).filter((p) => p.trang_thai === "active"),
    [chiTiet],
  );
  const mayOptionsKhaDung = useMemo(
    () => mayOptions.filter((m) => m.id !== cv?.may_id),
    [mayOptions, cv?.may_id],
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

  const hasKcsKho = !!(cv?.la_kcs || cv?.la_kcs_cuoi || cv?.nhom_id != null);

  // Tiến độ sản xuất %
  const targetVal = cv?.thuc_nhan || cv?.so_luong_vao || 0;
  const currentVal = cv?.da_lam || 0;
  const progressPct = targetVal > 0 ? Math.min(100, Math.round((currentVal / targetVal) * 100)) : 0;

  function chon(c: SxNhanVienChon) {
    if (isTo && !c.la_luong_khoan) return;
    onGiao(c.id);
    setGiaoOpen(false);
    setQ("");
  }

  async function xacNhanDoiMay() {
    if (mayChonId === "") return;
    const ok = await exec.doiMay(mayChonId, lyDoMay.trim() || null);
    if (ok) {
      setDoiMayOpen(false);
      setMayChonId("");
      setLyDoMay("");
    }
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
        <div className="thsx-drawer-tabs" role="tablist">
          <button
            type="button"
            className={`thsx-drawer-tab${activeTab === "van_hanh" ? " is-active" : ""}`}
            onClick={() => setActiveTab("van_hanh")}
            role="tab"
            aria-selected={activeTab === "van_hanh"}
          >
            <Icon name="cpu" size={13} /> Vận hành &amp; Quy cách
          </button>
          <button
            type="button"
            className={`thsx-drawer-tab${activeTab === "ban_giao" ? " is-active" : ""}`}
            onClick={() => setActiveTab("ban_giao")}
            role="tab"
            aria-selected={activeTab === "ban_giao"}
          >
            <Icon name="check" size={13} /> Bàn giao &amp; Vật tư
          </button>
          {hasKcsKho && (
            <button
              type="button"
              className={`thsx-drawer-tab${activeTab === "kcs_kho" ? " is-active" : ""}`}
              onClick={() => setActiveTab("kcs_kho")}
              role="tab"
              aria-selected={activeTab === "kcs_kho"}
            >
              <Icon name="alert" size={13} /> KCS &amp; Kho
              {(cv.la_kcs || cv.la_kcs_cuoi) && <span className="thsx-drawer-tab__dot" />}
            </button>
          )}
        </div>
      )}

      <div className="thsx-panel__body">
        {loading && !chiTiet ? (
          <div className="thsx-panel__loading">Đang tải…</div>
        ) : !cv || !chiTiet ? (
          <div className="thsx-panel__empty">Không tải được chi tiết công việc.</div>
        ) : (
          <>
            {/* ================= TAB 1: VẬN HÀNH & QUY CÁCH ================= */}
            {activeTab === "van_hanh" && (
              <>
                {/* 1A · THỰC TẾ SẢN XUẤT & PRODUCTION HUB (ĐẶT LÊN ĐẦU THEO PLAN) */}
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

                {/* 1B · THẺ QUY CÁCH CHẠY MÁY (BẢNG PHẲNG 2 CỘT SIÊU MẢNH - PHẲNG TĂM TẮP) */}
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

                {/* 1C · GHI CHÚ KỸ THUẬT — ô "Ghi chú kỹ thuật cho thợ" của bước. LUÔN hiện (kể cả trống)
                    vì bảng danh sách không còn dòng mở rộng để xem nhanh: thợ phải biết là không có dặn dò. */}
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
                                Bước nội bộ chỉ nhận thợ <b>lương khoán</b>.
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
                                    <span className={`thsx-tag ${c.la_luong_khoan ? "thsx-tag--khoan" : "thsx-tag--nhat"}`}>
                                      {c.la_luong_khoan ? "khoán" : "công nhật"}
                                    </span>
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
                    <p className="thsx-note">Chưa giao ai. Cần ≥1 thợ lương khoán để bắt đầu.</p>
                  ) : (
                    <ul className="thsx-roster-grid-2col">
                      {rosterActive.map((p) => (
                        <li key={p.id} className="thsx-roster-chip-card">
                          <div className="thsx-roster-chip-left">
                            <span className="thsx-roster-avatar-glow">
                              {p.ho_ten ? p.ho_ten.trim().charAt(0).toUpperCase() : "T"}
                            </span>
                            <span className="thsx-roster__nm">{p.ho_ten}</span>
                            <span className={`thsx-tag ${p.la_luong_khoan ? "thsx-tag--khoan" : "thsx-tag--nhat"}`}>
                              {p.la_luong_khoan ? "khoán" : "công nhật"}
                            </span>
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
                                <span className="thsx-roster-avatar-glow" style={{ width: 20, height: 20, fontSize: 10 }}>
                                  {k.ho_ten ? k.ho_ten.trim().charAt(0).toUpperCase() : "T"}
                                </span>
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

            {/* ================= TAB 2: BÀN GIAO & VẬT TƯ ================= */}
            {activeTab === "ban_giao" && (
              <ThsxExecPanels
                chiTiet={chiTiet}
                canAssign={canAssign}
                busy={busy}
                hoTroUngVien={hoTroUngVien}
                exec={exec}
              />
            )}

            {/* ================= TAB 3: KCS & KHO ================= */}
            {activeTab === "kcs_kho" && hasKcsKho && (
              <>
                {cv.la_kcs && (
                  <ThsxKcsPanel
                    chiTiet={chiTiet}
                    ct={kcsCt}
                    canAssign={canAssign}
                    busy={busy}
                    toChiuOpts={toChiuOpts}
                    congDoanRefOpts={congDoanRefOpts}
                    exec={exec}
                  />
                )}
                {cv.la_kcs && cv.nhom_id != null && (
                  <ThsxKhoPanel
                    chiTiet={chiTiet}
                    kho={khoCt}
                    kcsBatches={kcsCt?.batch ?? []}
                    canAssign={canAssign}
                    busy={busy}
                    exec={exec}
                  />
                )}
                {cv.la_kcs_cuoi && cv.nhom_id != null && (
                  <ThsxDongNhomPanel
                    dieuKien={dieuKien}
                    canAssign={canAssign}
                    busy={busy}
                    onDongThieu={exec.dongThieu}
                  />
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* PINNED BOTTOM ACTION FOOTER BAR */}
      {cv && (
        <div className="thsx-glass-footer">
          {lechKip && !done && (
            <div className="thsx-alert-capsule">
              <Icon name="alert" size={14} style={{ color: "#d97706" }} />
              <span>Kíp lệch so với kế hoạch — Bắt đầu sẽ chọn lý do.</span>
            </div>
          )}
          {!hasKhoan && !done && tt !== "running" && (
            <div className="thsx-alert-capsule">
              <Icon name="alert" size={14} style={{ color: "#d97706" }} />
              <span>Cần ≥1 thợ lương khoán mới bắt đầu được.</span>
            </div>
          )}
          {khuonChoNhan && !done && tt !== "running" && (
            <div className="thsx-alert-capsule">
              <Icon name="alert" size={14} style={{ color: "#d97706" }} />
              <span>Chưa nhận khuôn/khung — tích “Đã nhận” ở khối trên trước.</span>
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
          {doiMayOpen && (
            <div className="thsx-x-form thsx-x-form--sub" style={{ marginTop: "12px" }}>
              <div className="thsx-x-grid2">
                <label className="thsx-x-fld">
                  <span className="thsx-x-fld__l">Máy mới</span>
                  <select className="thsx-x-sel" value={mayChonId} disabled={mayOptionsKhaDung.length === 0}
                    onChange={(e) => setMayChonId(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">— Chọn máy —</option>
                    {mayOptionsKhaDung.map((m) => (
                      <option key={m.id} value={m.id}>{m.ma}{m.ten ? ` — ${m.ten}` : ""}</option>
                    ))}
                  </select>
                </label>
                <label className="thsx-x-fld">
                  <span className="thsx-x-fld__l">Lý do (không bắt buộc)</span>
                  <input className="thsx-x-in" value={lyDoMay} onChange={(e) => setLyDoMay(e.target.value)} placeholder="Máy hỏng, đổi ca…" />
                </label>
              </div>
              <div className="thsx-run" style={{ marginTop: "8px" }}>
                <Button variant="ghost" onClick={() => { setDoiMayOpen(false); setMayChonId(""); setLyDoMay(""); }}>Huỷ</Button>
                <Button variant="accent" onClick={xacNhanDoiMay} disabled={busy || mayChonId === ""}>Xác nhận đổi máy</Button>
              </div>
            </div>
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

