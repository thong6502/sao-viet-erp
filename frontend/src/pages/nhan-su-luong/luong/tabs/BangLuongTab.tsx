// Tab Bảng lương tháng (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Calendar,
  DollarSign,
  Download,
  Users,
  TrendingDown,
  TrendingUp,
  Search,
  RefreshCw,
  Lock,
  Unlock,
  CheckCircle2,
  RotateCcw,
  Send,
  X,
} from "lucide-react";
import {
  api,
  type PayrollLine,
  type PayrollParams,
  type PayrollPeriod,
} from "../../../../api/client";
import { MonthPicker } from "../../../../components/MonthPicker";
import { GIO_NHAP_MAX, GIO_NHAP_MIN, gioNhapSai } from "../../../../lib/gioNhap";
import { fmtDateTime } from "../../../../utils/format";
import { EmptyRow, EmptyState } from "../../../../components/EmptyState";
import { RowActionButton } from "../../../../components/RowActionButton";
import {
  bhThueRows,
  bonusTitle,
  bonusTotal,
  chiTiet,
  curYm,
  errText,
  hoaHongTotal,
  money,
  phatRows,
  phuCapRows,
  phuCapTotal,
} from "../shared/helpers";
import { PayslipCard } from "../components/PayslipCard";
import { SoiKhoanKm } from "../components/SoiKhoanKm";
import { LineEditModal } from "../modals/LineEditModal";

// --- Tab: Bảng lương tháng --------------------------------------------------

export function BangLuongTab({
  token,
  canManage,
  canLockPeriod,
  canMarkPaid,
  canExportPayroll,
}: {
  token: string;
  canManage: boolean;
  canLockPeriod: boolean;
  canMarkPaid: boolean;
  canExportPayroll: boolean;
}) {
  const [ym, setYm] = useState(curYm);
  const [period, setPeriod] = useState<PayrollPeriod | null>(null);
  const [lines, setLines] = useState<PayrollLine[]>([]);
  // Lý do CHƯA chốt được bảng lương, do máy chủ soạn. null = chốt được. Màn chỉ hiện lại,
  // không tự suy luật — xem chú thích ở `PayrollTable.chan_chot_ly_do`.
  const [chanChotLyDo, setChanChotLyDo] = useState<string | null>(null);
  const [canhBaoChot, setCanhBaoChot] = useState<string | null>(null);
  // Bảng "Công bố phiếu lương" — null = đang đóng. Mở ra thì giữ CẢ HAI mốc của cửa sổ xem:
  // `mo` (trống = ngay bây giờ) và `dong` (trống = không thời hạn). Chuỗi `datetime-local`.
  const [congBo, setCongBo] = useState<{ mo: string; dong: string } | null>(null);
  /** `datetime-local` trả GIỜ MÁY NGƯỜI DÙNG, không kèm múi giờ. `fmtDateTime` lại dán `Z` vào
   *  chuỗi thiếu múi giờ (đúng cho dữ liệu API, vì máy chủ trả UTC) ⇒ đưa thẳng vào là câu tóm
   *  tắt LỆCH 7 TIẾNG so với cái người dùng vừa gõ. Quy về ISO có múi giờ trước rồi mới format.
   *
   *  Gõ dở ô ngày-giờ ⇒ `new Date(...)` ra Invalid Date và `.toISOString()` NÉM — mà hàm này chạy
   *  TRONG LÚC RENDER (câu tóm tắt dưới hai ô), nên ném là trắng cả tab. Chặn tại đây. */
  const gioDiaPhuong = (v: string) => {
    if (!v) return "—";
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? "—" : fmtDateTime(d.toISOString());
  };
  // Hai ô ĐỀU được bỏ trống (mỗi kiểu trống một nghĩa) nên "trống" không phải lỗi — chỉ chặn khi
  // có gõ mà không dùng được. Công bố nhầm năm 0920 là phiếu lương mở ở một thế kỷ khác.
  const congBoGioSai = gioNhapSai(congBo?.mo) || gioNhapSai(congBo?.dong);
  const [filter, setFilter] = useState<"all" | "ct" | "tv">("all");
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("all");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // ⚠️ HAI ô nhớ lỗi KHÁC NHAU, đừng gộp lại:
  //   `err`     = lỗi THAO TÁC (tính lại · chốt · đã chi · xuất file) → hiện ở banner đỏ.
  //   `listErr` = lỗi TẢI BẢNG → hiện ở khối rỗng ca `lỗi`.
  // Gộp một ô thì một lần xuất Excel hỏng cũng làm cả bảng lương biến mất khỏi màn.
  const [listErr, setListErr] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [editing, setEditing] = useState<PayrollLine | null>(null);
  const [printing, setPrinting] = useState<PayrollLine | null>(null);
  // Bảng đối chiếu khoán km — HCNS bấm vào cột "Khoán km" để soi từng chuyến. Bắt buộc phải có:
  // km là TÀI XẾ TỰ GÕ, khác hẳn hoa hồng (nguồn là hoá đơn kế toán đã xuất).
  const [soiKm, setSoiKm] = useState<PayrollLine | null>(null);
  const [params, setParams] = useState<PayrollParams | null>(null);
  const [year, month] = ym.split("-").map(Number);

  // Chế độ xem: "detailed" (19 cột chi tiết) vs "compact" (8 cột rút gọn)
  const [viewMode, setViewMode] = useState<"detailed" | "compact">("detailed");
  // Dòng đang chọn (highlight row khi cuộn ngang)
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    api.luong
      .getParams(token)
      .then(setParams)
      .catch(() => setParams(null));
  }, [token]);

  const load = useCallback(() => {
    setListLoading(true);
    api.luong
      .table(token, year, month)
      .then((t) => {
        setPeriod(t.period);
        setLines(t.lines);
        setChanChotLyDo(t.chan_chot_ly_do ?? null);
        setCanhBaoChot(t.canh_bao_chot ?? null);
        setListErr(null);
      })
      .catch((e) => {
        // `GET /table` trả 200 kèm `period: null` khi kỳ CHƯA được tạo (xem
        // `routers/payroll.py:get_table`) ⇒ rơi vào nhánh này nghĩa là gọi HỎNG thật (mất mạng,
        // 403, 500), KHÔNG phải "chưa có kỳ". Trước đây nuốt lỗi rồi vẽ màn "Kỳ lương chưa được
        // tạo" — hệ nói sai sự thật, kế toán tưởng phải khởi tạo lại kỳ đã có.
        setPeriod(null);
        setLines([]);
        setListErr(errText(e));
      })
      .finally(() => setListLoading(false));
  }, [token, year, month]);
  useEffect(() => {
    load();
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      load();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // Danh sách Phòng/Tổ lấy từ CHÍNH các dòng lương đang có, không gọi thêm API: kỳ lương nào
  // cũng chỉ gồm người có mặt trong kỳ đó, nên đổ cả cây phòng ban ra là bày cả những tổ không
  // có ai để lọc.
  const dsPhong = useMemo(
    () =>
      Array.from(
        new Set(lines.map((l) => (l.department_name ?? "").trim()).filter(Boolean)),
      ).sort((a, b) => a.localeCompare(b, "vi")),
    [lines],
  );

  const kw = q.trim().toLowerCase();
  const shown = lines.filter((l) => {
    if (filter !== "all" && (filter === "tv") !== l.is_probation) return false;
    if (dept !== "all" && (l.department_name ?? "").trim() !== dept) return false;
    if (!kw) return true;
    // Tìm theo CẢ mã lẫn họ tên — người trả lương gõ mã, người soát gõ tên.
    return (
      (l.employee_name ?? "").toLowerCase().includes(kw) ||
      (l.employee_code ?? "").toLowerCase().includes(kw)
    );
  });

  // Helper tính giá trị từng cột số liệu (dùng chung cho hiển thị dòng, tóm tắt, và tfoot)
  const getLuongCongVal = (l: PayrollLine) => {
    if (l.lay_bu_lo) {
      return (l.khoan ?? 0) + (l.khoan_km ?? 0) + (l.luong_cong ?? 0);
    }
    return l.bu_lo_theo_cong != null && !l.luong_cong ? 0 : (l.luong_cong ?? 0);
  };
  const getKhoanSpVal = (l: PayrollLine) => (l.lay_bu_lo ? 0 : (l.khoan ?? 0));
  const getKhoanKmVal = (l: PayrollLine) => (l.lay_bu_lo ? 0 : (l.khoan_km ?? 0));
  const getTangCaVal = (l: PayrollLine) => (l.ot_pay ?? 0) + (l.luong_ngay_le ?? 0);
  const getCaDemVal = (l: PayrollLine) => (l.night_pay ?? 0) + (l.night_premium_pay ?? 0);
  const getTamUngVal = (l: PayrollLine) =>
    (l.luong_dot_1_total ?? 0) +
    (l.advance_total ?? 0) +
    (l.no_ung_ky_truoc ?? 0) -
    // Phần CHƯA trừ hết kỳ này (tạm ứng trừ SAU CÙNG) đã chuyển sang kỳ sau ⇒ không phải tiền
    // trừ của kỳ này. Phiếu lương in nó thành dòng ÂM, bảng phải khớp.
    (l.no_ung_chuyen_ky_sau ?? 0);

  const getPhatVal = (l: PayrollLine) =>
    phatRows(l).reduce((s, [, v]) => s + v, 0);
  const getBhThueVal = (l: PayrollLine) =>
    bhThueRows(l).reduce((s, [, v]) => s + v, 0);

  const getLineIncome = (l: PayrollLine) =>
    getLuongCongVal(l) +
    (l.chuyen_can ?? 0) +
    phuCapTotal(l) +
    getKhoanSpVal(l) +
    getKhoanKmVal(l) +
    (l.thuong_to_truong ?? 0) +
    getTangCaVal(l) +
    getCaDemVal(l) +
    bonusTotal(l) +
    hoaHongTotal(l);

  const getLineDeductions = (l: PayrollLine) =>
    getPhatVal(l) + getBhThueVal(l) + getTamUngVal(l);

  const totals = useMemo(() => {
    let actualCong = 0;
    let luongCong = 0;
    let chuyenCan = 0;
    let allowance = 0;
    let khoanSp = 0;
    let khoanKm = 0;
    let thuongTt = 0;
    let tangCa = 0;
    let caDem = 0;
    let thuong = 0;
    let hoaHong = 0;
    let phat = 0;
    let bhThue = 0;
    let tamUng = 0;
    let net = 0;
    let gross = 0;
    let deductions = 0;

    for (const l of shown) {
      const cLuongCong = getLuongCongVal(l);
      const cChuyenCan = l.chuyen_can ?? 0;
      const cAllowance = phuCapTotal(l);
      const cKhoanSp = getKhoanSpVal(l);
      const cKhoanKm = getKhoanKmVal(l);
      const cThuongTt = l.thuong_to_truong ?? 0;
      const cTangCa = getTangCaVal(l);
      const cCaDem = getCaDemVal(l);
      const cThuong = bonusTotal(l);
      const cHoaHong = hoaHongTotal(l);

      const cViPham = getPhatVal(l);
      const cBhxh = getBhThueVal(l);
      const cTamUng = getTamUngVal(l);

      const cIncome =
        cLuongCong +
        cChuyenCan +
        cAllowance +
        cKhoanSp +
        cKhoanKm +
        cThuongTt +
        cTangCa +
        cCaDem +
        cThuong +
        cHoaHong;
      const cDeduct = cViPham + cBhxh + cTamUng;

      actualCong += l.actual_cong ?? 0;
      luongCong += cLuongCong;
      chuyenCan += cChuyenCan;
      allowance += cAllowance;
      khoanSp += cKhoanSp;
      khoanKm += cKhoanKm;
      thuongTt += cThuongTt;
      tangCa += cTangCa;
      caDem += cCaDem;
      thuong += cThuong;
      hoaHong += cHoaHong;
      phat += cViPham;
      bhThue += cBhxh;
      tamUng += cTamUng;
      net += l.net_pay ?? 0;
      gross += cIncome;
      deductions += cDeduct;
    }

    return {
      actualCong,
      luongCong,
      chuyenCan,
      allowance,
      khoanSp,
      khoanKm,
      thuongTt,
      tangCa,
      caDem,
      thuong,
      hoaHong,
      phat,
      bhThue,
      tamUng,
      net,
      gross,
      deductions,
    };
  }, [shown]);

  const totalNet = totals.net;
  const totalGross = totals.gross;
  const totalDeductions = totals.deductions;
  const totalStaff = shown.length;
  const officialCount = shown.filter((l) => !l.is_probation).length;
  const probationCount = shown.filter((l) => l.is_probation).length;
  const totalWorkdays = totals.actualCong;

  const status = period?.status;
  const isDraft = !period || status === "draft";
  const locked = status === "locked";
  const paid = status === "paid";

  async function downloadXlsx(kind: "table" | "bank") {
    setBusy(true);
    setErr(null);
    try {
      const url = await api.luong.xlsxBlobUrl(token, kind, year, month);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${kind === "bank" ? "chuyen-khoan" : "bang-luong"}-${ym}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar lg-toolbar">
        {/* Nhóm bộ lọc (bên trái) */}
        <div className="lg-toolbar-filters">
          <div className="lg-date-wrapper">
            <span className="lg-date-icon">
              <Calendar size={14} />
            </span>
            <MonthPicker value={ym} onChange={setYm} ariaLabel="Kỳ lương" />
          </div>
          <div className="lg-search-wrapper">
            <span className="lg-search-icon">
              <Search size={14} />
            </span>
            <input
              className="lg-search-input"
              placeholder="Tìm theo tên / mã…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            {q && (
              <button
                type="button"
                className="lg-search-clear"
                onClick={() => setQ("")}
                title="Xóa tìm kiếm"
              >
                <X size={13} />
              </button>
            )}
          </div>
          {dsPhong.length > 1 && (
            <select
              className="lg-dept-filter"
              value={dept}
              onChange={(e) => setDept(e.target.value)}
              title="Lọc theo Phòng / Tổ"
            >
              <option value="all">Tất cả phòng / tổ</option>
              {dsPhong.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          )}
          <div className="lg-seg">
            {(["all", "ct", "tv"] as const).map((f) => (
              <button
                key={f}
                className={filter === f ? "is-active" : ""}
                onClick={() => setFilter(f)}
              >
                {f === "all" ? "Tất cả" : f === "ct" ? "Chính thức" : "Thử việc"}
              </button>
            ))}
          </div>

          {/* Toggle chế độ xem: Chi tiết vs Tóm tắt */}
          <div className="lg-seg lg-view-seg" role="group" aria-label="Chế độ xem bảng lương">
            <button
              type="button"
              className={viewMode === "detailed" ? "is-active" : ""}
              onClick={() => setViewMode("detailed")}
              title="Xem đầy đủ 19 cột chi tiết"
            >
              Xem chi tiết
            </button>
            <button
              type="button"
              className={viewMode === "compact" ? "is-active" : ""}
              onClick={() => setViewMode("compact")}
              title="Xem rút gọn 8 cột tổng quan"
            >
              Xem tóm tắt
            </button>
          </div>
        </div>

        {/* Nhóm thao tác & xuất file (bên phải) */}
        <div className="lg-toolbar-actions">
          {canManage && isDraft && period && (
            <button
              className="btn btn--accent"
              onClick={() => run(() => api.luong.generate(token, year, month))}
              disabled={busy}
            >
              <RefreshCw size={14} className={busy ? "spin" : ""} />
              {busy ? "Đang tính…" : "Tính lại"}
            </button>
          )}
          {canLockPeriod && period && isDraft && (
            <button
              className="btn btn--ghost"
              onClick={() => run(() => api.luong.lock(token, year, month))}
              disabled={busy || Boolean(chanChotLyDo)}
              title={chanChotLyDo ?? undefined}
            >
              <Lock size={14} /> Chốt
            </button>
          )}
          {canLockPeriod && locked && (
            <button
              className="btn btn--ghost"
              onClick={() => run(() => api.luong.reopen(token, year, month))}
              disabled={busy}
            >
              <Unlock size={14} /> Mở lại
            </button>
          )}
          {canMarkPaid && locked && (
            <button
              className="btn btn--primary"
              onClick={() => run(() => api.luong.pay(token, year, month))}
              disabled={busy}
            >
              <CheckCircle2 size={14} /> Đã chi
            </button>
          )}
          {canMarkPaid && paid && (
            <button
              className="btn btn--ghost"
              onClick={() =>
                run(() => api.luong.unpay(token, year, month, "hủy đã chi"))
              }
              disabled={busy}
            >
              <RotateCcw size={14} /> Hủy đã chi
            </button>
          )}
          {canLockPeriod && (locked || paid) && (
            <button
              className="btn btn--ghost"
              onClick={() =>
                setCongBo((v) => (v ? null : { mo: "", dong: "" }))
              }
              disabled={busy}
              title="Chọn khoảng thời gian người lao động xem được phiếu lương của kỳ này."
            >
              <Send size={14} /> {period?.cong_bo_luc ? "Đổi lịch phiếu" : "Công bố phiếu"}
            </button>
          )}
          {canLockPeriod && period?.cong_bo_luc && (
            <button
              className="btn btn--ghost"
              onClick={() => run(() => api.luong.thuHoi(token, year, month))}
              disabled={busy}
              title="Rút phiếu lại — người lao động thôi thấy ngay lập tức."
            >
              <RotateCcw size={14} /> Thu hồi phiếu
            </button>
          )}
          {canExportPayroll && period && (
            <button
              className="btn btn--ghost"
              onClick={() => downloadXlsx("table")}
              disabled={busy}
            >
              <Download size={14} /> Xuất Excel
            </button>
          )}
          {canExportPayroll && (locked || paid) && (
            <button
              className="btn btn--ghost"
              onClick={() => downloadXlsx("bank")}
              disabled={busy}
            >
              <Download size={14} /> File chuyển khoản
            </button>
          )}
          {locked && (
            <span className="ns-badge ns-badge--muted">
              <Lock size={12} /> Đã chốt
            </span>
          )}
          {paid && (
            <span className="ns-badge ns-badge--ok">
              <CheckCircle2 size={12} /> Đã chi
              {period?.paid_at ? ` ${fmtDateTime(period.paid_at)}` : ""}
            </span>
          )}
        </div>
      </div>

      {err && (
        <div className="banner banner--error" style={{ marginBottom: 12 }}>
          {err}
        </div>
      )}

      {/* Kỳ công chưa chốt: hiện NGAY CẢ KHI chưa khởi tạo bảng lương, để người tính lương biết
          trước chứ không phải bấm Chốt rồi mới bị chặn. Nút "Chốt" cũng đã xám (xem thanh trên).
          Chỉ nhắc, KHÔNG chặn Tính lại — xem thử quỹ lương giữa tháng vẫn là việc bình thường. */}
      {/* BẢNG CÔNG BỐ PHIẾU LƯƠNG — một cửa sổ mở–đóng, không phải hai nút rời.
          Chủ chốt 12/08/2026: "công bố nhưng cũng phải cài giờ phiếu hiển thị trong bao lâu".
          Hai ô ĐỀU CÓ THỂ BỎ TRỐNG và mỗi cách bỏ trống có nghĩa riêng — nên phải nói ra bằng
          chữ ngay dưới ô, đừng bắt người dùng đoán. Nút gợi ý nhanh (7/30 ngày) tính từ MỐC MỞ
          chứ không phải từ hôm nay, nếu không hẹn mở tháng sau mà đóng tuần này. */}
      {congBo && (
        <div className="lg-congbo">
          <div className="lg-congbo__title">
            Người lao động xem phiếu lương {String(month).padStart(2, "0")}/{year} trong khoảng
          </div>
          <div className="lg-congbo__grid">
            <label className="lg-congbo__field">
              <span>Mở lúc</span>
              <input
                type="datetime-local"
                min={GIO_NHAP_MIN}
                max={GIO_NHAP_MAX}
                value={congBo.mo}
                onChange={(e) => setCongBo({ ...congBo, mo: e.target.value })}
              />
              <em>{congBo.mo ? "" : "bỏ trống = mở ngay khi bấm"}</em>
            </label>
            <label className="lg-congbo__field">
              <span>Đóng lúc</span>
              <input
                type="datetime-local"
                value={congBo.dong}
                min={congBo.mo || GIO_NHAP_MIN}
                max={GIO_NHAP_MAX}
                onChange={(e) => setCongBo({ ...congBo, dong: e.target.value })}
              />
              <em>{congBo.dong ? "" : "bỏ trống = mở không thời hạn"}</em>
            </label>
            <div className="lg-congbo__quick">
              {([["7 ngày", 7], ["14 ngày", 14], ["30 ngày", 30]] as const).map(([nhan, ngay]) => (
                <button
                  key={ngay}
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    // Mốc mở gõ hỏng thì tính từ nó ra toàn NaN — quay về "từ bây giờ" cho lành.
                    const goc = gioNhapSai(congBo.mo) || !congBo.mo
                      ? new Date() : new Date(congBo.mo);
                    const het = new Date(goc.getTime() + ngay * 86400000);
                    const p2 = (n: number) => String(n).padStart(2, "0");
                    setCongBo({
                      ...congBo,
                      dong: `${het.getFullYear()}-${p2(het.getMonth() + 1)}-${p2(het.getDate())}T${p2(het.getHours())}:${p2(het.getMinutes())}`,
                    });
                  }}
                >
                  {nhan}
                </button>
              ))}
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setCongBo({ ...congBo, dong: "" })}
              >
                Không giới hạn
              </button>
            </div>
          </div>
          <div className="lg-congbo__foot">
            <span className="lg-congbo__hint">
              {congBoGioSai
                ? "⚠ Giờ không đọc được — năm phải 4 chữ số, trong khoảng 2000–2099."
                : congBo.dong && congBo.mo && new Date(congBo.dong) <= new Date(congBo.mo)
                  ? "⚠ Giờ đóng phải sau giờ mở."
                  : `Phiếu mở ${congBo.mo ? `từ ${gioDiaPhuong(congBo.mo)}` : "ngay bây giờ"}` +
                    (congBo.dong ? ` đến ${gioDiaPhuong(congBo.dong)}.` : ", không thời hạn.")}
            </span>
            <div className="lg-congbo__act">
              <button className="btn btn--ghost" onClick={() => setCongBo(null)}>
                Bỏ
              </button>
              <button
                className="btn btn--accent"
                disabled={
                  busy ||
                  congBoGioSai ||
                  Boolean(congBo.dong && congBo.mo && new Date(congBo.dong) <= new Date(congBo.mo))
                }
                onClick={() => {
                  const mo = congBo.mo ? new Date(congBo.mo).toISOString() : null;
                  const dong = congBo.dong ? new Date(congBo.dong).toISOString() : null;
                  setCongBo(null);
                  run(() => api.luong.congBo(token, year, month, mo, dong));
                }}
              >
                {period?.cong_bo_luc ? "Cập nhật" : "Công bố"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Trạng thái hiện tại — nói rõ CẢ HAI đầu cửa sổ, đừng để HCNS phải đoán phiếu còn mở không. */}
      {period?.cong_bo_luc && (
        <div className="banner banner--success" style={{ marginBottom: 12 }}>
          {new Date(period.cong_bo_luc) > new Date()
            ? `Đã hẹn — phiếu mở lúc ${fmtDateTime(period.cong_bo_luc)}`
            : `Đang mở từ ${fmtDateTime(period.cong_bo_luc)}`}
          {period.dong_phieu_luc
            ? new Date(period.dong_phieu_luc) <= new Date()
              ? ` · ĐÃ ĐÓNG lúc ${fmtDateTime(period.dong_phieu_luc)} — người lao động thôi xem được.`
              : ` · đóng lúc ${fmtDateTime(period.dong_phieu_luc)}.`
            : " · không thời hạn."}
        </div>
      )}

      {chanChotLyDo && isDraft && (
        <div className="banner banner--warn" style={{ marginBottom: 12 }}>
          {chanChotLyDo}
        </div>
      )}
      {canhBaoChot && isDraft && (
        <div className="banner banner--info" style={{ marginBottom: 12 }}>
          {canhBaoChot}
        </div>
      )}

      {period && (
        <div className="lg-kpi-grid">
          <div className="lg-kpi-card lg-kpi-card--net">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <DollarSign size={15} />
              </span>
              <span className="lg-kpi-card-label">Tổng thực lĩnh (Net)</span>
            </div>
            <div className="lg-kpi-card-val">{money(totalNet)}đ</div>
            <div className="lg-kpi-card-sub">
              Chi trả cho {totalStaff} nhân sự
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--gross">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <TrendingUp size={15} />
              </span>
              <span className="lg-kpi-card-label">Tổng thu nhập gộp (+)</span>
            </div>
            <div className="lg-kpi-card-val">{money(totalGross)}đ</div>
            <div className="lg-kpi-card-sub">
              Tổng thu nhập trước giảm trừ
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--deduct">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <TrendingDown size={15} />
              </span>
              <span className="lg-kpi-card-label">Khấu trừ &amp; Tạm ứng (−)</span>
            </div>
            <div className="lg-kpi-card-val">−{money(totalDeductions)}đ</div>
            <div className="lg-kpi-card-sub">BHXH · đoàn phí · thuế, phạt và tạm ứng</div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--staff">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <Users size={15} />
              </span>
              <span className="lg-kpi-card-label">Quy mô &amp; Ngày công</span>
            </div>
            <div className="lg-kpi-card-val">{totalStaff} người</div>
            <div className="lg-kpi-card-sub">
              {officialCount} CT · {probationCount} TV · {totalWorkdays.toLocaleString("vi-VN")} ngày công
            </div>
          </div>
        </div>
      )}

      {/* Thanh công thức trực quan */}
      {period && (
        <div className="lg-formula-bar" role="region" aria-label="Quy tắc tính lương">
          <div className="lg-formula-title">
            <span className="lg-formula-badge">Quy tắc tính</span>
          </div>
          <div className="lg-formula-equation">
            <span
              className="lg-formula-item lg-formula-item--net"
              title="Thực lĩnh = Lương công + Thu nhập & Phụ cấp − Giảm trừ & Tạm ứng"
            >
              Thực lĩnh (=)
            </span>
            <span className="lg-formula-op">=</span>
            <span
              className="lg-formula-item lg-formula-item--base"
              title="Lương theo ngày công thực tế (hoặc mức bù lỗ tối thiểu của tổ khoán)"
            >
              Lương công
            </span>
            <span className="lg-formula-op">+</span>
            <span
              className="lg-formula-item lg-formula-item--income"
              title="Bao gồm: Chuyên cần + Phụ cấp + Khoán SP + Khoán km + Thưởng TT + Tăng ca + Ca đêm + Thưởng + Hoa hồng"
            >
              Các khoản thu nhập (+)
            </span>
            <span className="lg-formula-op">−</span>
            <span
              className="lg-formula-item lg-formula-item--deduct"
              title="Bao gồm: Phạt &amp; giảm trừ (đi trễ, biên bản, 5S, ĐT vượt trội, khoản trừ danh mục) + BHXH · đoàn phí · thuế TNCN + Lương đợt 1 và Tạm ứng"
            >
              Các khoản giảm trừ (−)
            </span>
          </div>
          <div className="lg-formula-tip">
            💡 Nhấp vào dòng bất kỳ để highlight dòng khi cuộn ngang
          </div>
        </div>
      )}

      {/* BA CA phải tách, không gộp (xem components/EmptyState.tsx):
            đang tải · gọi HỎNG · thật sự chưa có kỳ.
          Trước đây cả ba đều rơi vào màn "Kỳ lương chưa được tạo": vào màn là nháy một nhịp
          "chưa tạo" rồi mới ra bảng, còn khi backend chết thì mời người ta khởi tạo lại một kỳ
          lương đã có sẵn. */}
      {listLoading && !period ? (
        <EmptyState trangThai="dang-tai" />
      ) : listErr && !period ? (
        <EmptyState trangThai="loi" loi={listErr} onThuLai={load} />
      ) : !period ? (
        <div className="lg-init-dashboard">
          <div className="lg-init-grid">
            <div className="lg-init-section lg-init-section--sources">
              <h3 className="lg-init-section-title">Dữ liệu nguồn đồng bộ</h3>
              <p className="lg-init-section-desc">
                Hệ thống tự động liên kết các phân hệ dữ liệu để tính toán lương
                chính xác:
              </p>

              <div className="lg-source-list">
                <div className="lg-source-item">
                  <div className="lg-source-item-head">
                    <span className="lg-source-bullet lg-source-bullet--active"></span>
                    <span className="lg-source-name">Dữ liệu Chấm công</span>
                  </div>
                  <span className="lg-source-text">
                    Lấy số ngày công thực tế, giờ tăng ca, số ngày làm ca đêm đã
                    chốt từ phân hệ Chấm công.
                  </span>
                </div>

                <div className="lg-source-item">
                  <div className="lg-source-item-head">
                    <span className="lg-source-bullet lg-source-bullet--active"></span>
                    <span className="lg-source-name">
                      Thang bậc lương của tổ
                    </span>
                  </div>
                  <span className="lg-source-text">
                    Áp dụng mức lương chuẩn theo vị trí, tổ nhóm công tác, thâm
                    niên và giới tính đã cấu hình.
                  </span>
                </div>

                <div className="lg-source-item">
                  <div className="lg-source-item-head">
                    <span className="lg-source-bullet lg-source-bullet--active"></span>
                    <span className="lg-source-name">Khấu trừ &amp; Tạm ứng</span>
                  </div>
                  <span className="lg-source-text">
                    Tự động trừ các khoản tạm ứng đã phê duyệt trong tháng, tính
                    BHXH bắt buộc và thuế TNCN lũy tiến.
                  </span>
                </div>
              </div>
            </div>

            <div className="lg-init-section lg-init-section--params">
              <h3 className="lg-init-section-title">
                Tham số cấu hình hiện tại
              </h3>
              <p className="lg-init-section-desc">
                Các tham số chung đang áp dụng trong hệ thống (sửa tại tab Quy
                tắc lương):
              </p>

              {params ? (
                <div className="lg-param-table">
                  <div className="lg-param-row">
                    <span className="lg-param-name">Công chuẩn / tháng</span>
                    <span className="lg-param-val">
                      Tự tính theo Lịch &amp; Ngày lễ
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">Giờ công tiêu chuẩn</span>
                    <span className="lg-param-val">
                      {params.standard_hours_per_day}h/ngày
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">Tỷ lệ lương thử việc</span>
                    <span className="lg-param-val">
                      {params.probation_ratio * 100}%
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">Giảm trừ bản thân</span>
                    <span className="lg-param-val">
                      {money(params.deduction_self)}đ
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">
                      Giảm trừ người phụ thuộc
                    </span>
                    <span className="lg-param-val">
                      {money(params.deduction_dependent)}đ
                    </span>
                  </div>
                </div>
              ) : (
                <p className="lg-param-loading">Đang tải tham số...</p>
              )}
            </div>
          </div>

          <div className="lg-init-action-card">
            <div className="lg-init-action-info">
              <h4 className="lg-init-action-title">
                Kỳ lương tháng {month}/{year} chưa được tạo
              </h4>
              <p className="lg-init-action-desc">
                Xác nhận các thông tin dữ liệu nguồn và tham số ở trên trước khi
                tiến hành khởi tạo.
              </p>
            </div>
            {canManage && isDraft && (
              <button
                className="btn btn--accent btn--large"
                onClick={() =>
                  run(() => api.luong.generate(token, year, month))
                }
                disabled={busy}
              >
                {busy ? "Đang tính toán..." : "Khởi tạo bảng lương"}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="ns__tablewrap lg-table">
          <table className={`ns__table ${viewMode === "compact" ? "ns__table--compact" : ""}`}>
            {viewMode === "detailed" ? (
              <thead>
                {/* Tầng 1: Super Headers phân nhóm cột theo logic kế toán */}
                <tr className="lg-th-super">
                  <th colSpan={3} className="lg-th-group lg-th-group--info">
                    Thông tin nhân sự
                  </th>
                  <th colSpan={2} className="lg-th-group lg-th-group--base">
                    Công &amp; Lương cơ sở
                  </th>
                  <th colSpan={9} className="lg-th-group lg-th-group--income">
                    Thu nhập &amp; Phụ cấp (+)
                  </th>
                  <th colSpan={3} className="lg-th-group lg-th-group--deduct">
                    Giảm trừ &amp; Tạm ứng (−)
                  </th>
                  <th rowSpan={2} className="lg-num lg-net lg-th-group--net">
                    Thực lĩnh (=)
                  </th>
                  <th rowSpan={2} className="lg-actcol lg-sticky-act">
                    Thao tác
                  </th>
                </tr>
                {/* Tầng 2: Tiêu đề từng cột cụ thể */}
                <tr className="lg-th-sub">
                  <th className="lg-sticky-code">Mã</th>
                  <th className="lg-sticky-name">Họ tên</th>
                  <th>Phòng/Tổ</th>
                  <th className="lg-num">Công</th>
                  <th className="lg-num">Lương công</th>
                  <th className="lg-num lg-th-sub--income">Chuyên cần</th>
                  <th className="lg-num lg-th-sub--income">Phụ cấp</th>
                  <th className="lg-num lg-th-sub--income">Khoán SP</th>
                  <th className="lg-num lg-th-sub--income">Khoán km</th>
                  <th className="lg-num lg-th-sub--income">Thưởng TT</th>
                  <th className="lg-num lg-th-sub--income">Tăng ca</th>
                  <th className="lg-num lg-th-sub--income">Ca đêm</th>
                  <th className="lg-num lg-th-sub--income">Thưởng</th>
                  <th className="lg-num lg-th-sub--income lg-border-group-end">Hoa hồng</th>
                  <th className="lg-num lg-th-sub--deduct">Phạt / giảm trừ</th>
                  <th className="lg-num lg-th-sub--deduct">BH · Đoàn phí · Thuế</th>
                  <th className="lg-num lg-th-sub--deduct lg-border-group-end">Đợt 1 / Tạm ứng</th>
                </tr>
              </thead>
            ) : (
              <thead>
                <tr>
                  <th className="lg-sticky-code">Mã NV</th>
                  <th className="lg-sticky-name">Họ tên</th>
                  <th>Phòng/Tổ</th>
                  <th className="lg-num">Ngày công</th>
                  <th className="lg-num lg-th-income-header">Tổng thu nhập (+)</th>
                  <th className="lg-num lg-th-deduct-header">Tổng giảm trừ (−)</th>
                  <th className="lg-num lg-net lg-th-group--net">Thực lĩnh (=)</th>
                  <th className="lg-actcol lg-sticky-act">Thao tác</th>
                </tr>
              </thead>
            )}
            <tbody>
              {viewMode === "detailed"
                ? shown.map((l) => {
                    const isSelected = selectedId === l.id;
                    return (
                      <tr
                        key={l.id}
                        className={isSelected ? "is-selected" : ""}
                        onClick={() => setSelectedId(isSelected ? null : l.id)}
                      >
                        <td className="ns__code lg-sticky-code">{l.employee_code}</td>
                        <td className="lg-sticky-name">
                          {l.employee_name}{" "}
                          {l.chua_khai_luong && (
                            <span
                              className="rc-pill rc-pill--off"
                              title="Có công nhưng chưa khai mức lương ở Lương → Lương nhân viên — đang tính 0đ, kỳ này chưa chốt được"
                            >
                              chưa khai lương
                            </span>
                          )}{" "}
                          {/* Ô "Mức đóng BHXH" khai riêng từng người (16/09/2026): mốc lương CŨ còn
                              trống thì engine tạm đóng theo mức nền — gắn nhãn để HCNS khai lại. */}
                          {l.chua_khai_muc_bh && (
                            <span
                              className="rc-pill rc-pill--off"
                              title="Chưa khai Mức đóng BHXH ở hồ sơ lương — đang tạm đóng theo lương cơ bản + trách nhiệm. Khai lại ở Lương → Lương nhân viên → Sửa lương."
                            >
                              chưa khai mức BHXH
                            </span>
                          )}{" "}
                          {l.is_probation && (
                            <span className="ns-badge ns-badge--muted">TV</span>
                          )}
                        </td>
                        <td>{l.department_name ?? "—"}</td>
                        {/* Công ngày LỄ / CHỦ NHẬT là gốc của hệ số Đ98.1.b/c */}
                        <td
                          className="lg-num"
                          title={
                            [
                              (l.special_cong ?? 0) > 0
                                ? `trong đó ${l.special_cong} công ngày lễ / nghỉ tuần (ăn hệ số)`
                                : "",
                              l.luong_ngay_le && (l.le_nghi_cong ?? 0) > 0
                                ? `${l.le_nghi_cong} công ngày lễ nghỉ (trả riêng ngoài khoán)`
                                : "",
                            ]
                              .filter(Boolean)
                              .map((s, i) => (i === 0 ? `Tổng ${l.actual_cong} công, ${s}` : s))
                              .join(" · ") || undefined
                          }
                        >
                          {l.actual_cong}
                          {(l.special_cong ?? 0) > 0 || l.luong_ngay_le ? (
                            <span className="lg-cong-le"> •</span>
                          ) : null}
                        </td>
                        {/* Lương công */}
                        <td
                          className="lg-num"
                          title={
                            [
                              // THỬ VIỆC ở tổ khoán KHÔNG đem so với sản lượng (chủ chốt 16/09/2026,
                              // PRD §00.9) ⇒ câu "lấy số lớn hơn" bên dưới sai với họ: hai cột khoán
                              // của dòng này luôn 0, nói "khoán 0 → lấy bù lỗ" là kế toán tưởng tổ
                              // chưa nhập sản lượng.
                              l.bu_lo_theo_cong != null && l.is_probation
                                ? `Thử việc — trả theo BÙ LỖ, KHÔNG trả theo sản lượng: bù lỗ theo công ${money(l.bu_lo_theo_cong)} (mức nền đã nhân % thử việc, phụ cấp đủ 100%). Sản lượng / km kỳ này vẫn được ghi nhận bên Sản xuất, chỉ không trả tiền theo.`
                                : "",
                              l.bu_lo_theo_cong != null && !l.is_probation
                                ? `${l.la_giao_hang ? "Tài xế / phụ xe" : "Tổ khoán"} — lấy số lớn hơn giữa ${l.la_giao_hang ? "tiền km" : "tiền khoán"} và ${l.la_giao_hang ? "vế thời gian (bù lỗ theo công gồm phụ cấp + tiền tăng ca)" : "bù lỗ theo công (gồm phụ cấp)"}. Bù lỗ ${money(l.bu_lo_theo_cong)}${l.la_giao_hang ? ` + tăng ca ${money(l.ot_pay)}` : ""} · ${l.la_giao_hang ? "km" : "khoán"} ${money(l.la_giao_hang ? (l.khoan_km ?? 0) : l.khoan)} → ${l.lay_bu_lo ? "lấy bù lỗ, ô này là phần bù thêm" : l.bu_lo_theo_cong || l.khoan || l.khoan_km ? "lấy khoán, không bù" : "chưa có ngày đi làm để so"}`
                                : "",
                              l.luong_ngay_le
                                ? `Công ngày lễ trả riêng ngoài khoán ${money(l.luong_ngay_le)} (cột Tăng ca · CN / lễ)`
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" · ") || undefined
                          }
                        >
                          {l.lay_bu_lo
                            ? money(l.khoan + (l.khoan_km ?? 0) + l.luong_cong)
                            : l.bu_lo_theo_cong != null && !l.luong_cong
                              ? "—"
                              : l.luong_cong ? money(l.luong_cong) : "—"}
                          {l.bu_lo_theo_cong != null && (l.lay_bu_lo || l.bu_lo_theo_cong || l.khoan) ? (
                            <span className="lg-ot-khoan">{l.lay_bu_lo ? "bù lỗ" : "lấy khoán"}</span>
                          ) : null}
                        </td>
                        <td className={`lg-num ${l.chuyen_can ? "" : "lg-zero"}`}>
                          {l.chuyen_can ? money(l.chuyen_can) : "—"}
                        </td>
                        <td
                          className={`lg-num ${phuCapTotal(l) ? "" : "lg-zero"}`}
                          title={
                            [
                              chiTiet(phuCapRows(l), ""),
                              l.phu_cap_thang != null && l.phu_cap_thang > 0
                                ? `Phụ cấp tháng ${money(l.phu_cap_thang)} ÷ ${l.standard_cong} × ${l.cong_phu_cap ?? 0} công (kể cả khoản hồ sơ)`
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" · ") || undefined
                          }
                        >
                          {phuCapTotal(l) ? money(phuCapTotal(l)) : "—"}
                        </td>
                        <td
                          className={`lg-num ${l.khoan && !l.lay_bu_lo ? "" : "lg-zero"}`}
                          title={
                            l.lay_bu_lo && l.khoan
                              ? `Tiền khoán kỳ này ${money(l.khoan)} — thấp hơn bù lỗ theo công nên KHÔNG lấy (đã trả theo bù lỗ ở cột Lương công)`
                              : undefined
                          }
                        >
                          {l.khoan && !l.lay_bu_lo ? money(l.khoan) : "—"}
                        </td>
                        <td className="lg-num">
                          {l.khoan_km && !l.lay_bu_lo ? (
                            <button
                              type="button"
                              className="lg-linkbtn"
                              title="Xem từng chuyến giao đã sinh ra số này"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSoiKm(l);
                              }}
                            >
                              {money(l.khoan_km)}
                            </button>
                          ) : (
                            <span
                              className="lg-zero"
                              title={
                                l.lay_bu_lo && l.khoan_km
                                  ? `Tiền km kỳ này ${money(l.khoan_km)} — thấp hơn vế thời gian (bù lỗ theo công + tiền tăng ca) nên KHÔNG lấy; phần chênh đã trả ở cột Lương công / Tăng ca`
                                  : "Không có chuyến giao trong kỳ, hoặc tổ chưa bật Bộ phận Giao hàng"
                              }
                            >
                              —
                            </span>
                          )}
                        </td>
                        <td
                          className={`lg-num ${l.thuong_to_truong ? ((l.thuong_to_truong ?? 0) < 0 ? "lg-minus" : "") : "lg-zero"}`}
                          title={
                            l.thuong_to_truong
                              ? "Thưởng/phạt tổ trưởng theo tỷ lệ lỗi KCS, tính lúc đóng nhóm thành phẩm"
                              : "Kỳ này tổ trưởng không có nhóm nào đóng, hoặc tổ chưa khai bậc thưởng"
                          }
                        >
                          {l.thuong_to_truong ? money(l.thuong_to_truong) : "—"}
                        </td>
                        <td
                          className={`lg-num ${(l.ot_pay || l.luong_ngay_le) ? "" : "lg-zero"}`}
                          title={[
                            l.ot_minutes ? `${(l.ot_minutes / 60).toFixed(1)}h tăng ca` : "",
                            // TỔ GIAO HÀNG tách khỏi câu của tổ khoán sản lượng (16/09/2026, PRD
                            // §00.10): tài xế / phụ xe CÓ tiền giờ tăng ca, và tiền đó là một vế
                            // của phép so với khoán km — nói "khoán không có tiền tăng ca" ở đây
                            // là sai với đúng cái ô đang hiện tiền.
                            l.che_do_khoan && !l.la_giao_hang
                              ? "Chế độ khoán — KHÔNG có tiền tăng ca (làm thêm giờ đã trả qua tiền khoán); vẫn có cơm tăng ca"
                              : "",
                            l.che_do_khoan && l.la_giao_hang
                              ? "Tài xế / phụ xe: CÓ tiền giờ tăng ca (hệ số bình thường) — nằm trong vế thời gian đem so với khoán km, tháng lấy km thì không trả"
                              : "",
                            l.che_do_khoan && !l.la_giao_hang && (l.ot_pay || l.luong_ngay_le)
                              ? "Số ở ô này là tiền ngày Chủ nhật / lễ, không phải tiền tăng ca"
                              : "",
                            l.che_do_khoan && l.ot_pay
                              ? `${l.la_giao_hang ? "giờ tăng ca + phần thêm ngày CN / lễ" : "làm nguyên ngày CN / lễ"}${(l.special_cong ?? 0) > 0 ? ` ${l.special_cong} công` : ""}: ${money(l.ot_pay)}`
                              : "",
                            l.luong_ngay_le
                              ? `công ngày lễ nghỉ (ngoài khoán)${(l.le_nghi_cong ?? 0) > 0 ? ` ${l.le_nghi_cong} ngày` : ""}: ${money(l.luong_ngay_le)}`
                              : "",
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        >
                          {l.ot_pay || l.luong_ngay_le
                            ? money((l.ot_pay ?? 0) + (l.luong_ngay_le ?? 0))
                            : "—"}
                          {l.che_do_khoan && (l.ot_pay || l.luong_ngay_le) ? (
                            <span className="lg-ot-khoan">CN / lễ</span>
                          ) : null}
                        </td>
                        <td
                          className={`lg-num ${(l.night_pay || l.night_premium_pay) ? "" : "lg-zero"}`}
                          title={[
                            l.night_days ? `${l.night_days} ngày ca đêm` : "",
                            l.night_pay
                              ? `phụ cấp ca (tay) ${money(l.night_pay)}`
                              : "",
                            l.night_premium_pay
                              ? `premium giờ×hệ số ${money(l.night_premium_pay)}`
                              : "",
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        >
                          {l.night_pay || l.night_premium_pay
                            ? money((l.night_pay ?? 0) + (l.night_premium_pay ?? 0))
                            : "—"}
                        </td>
                        <td className={`lg-num ${bonusTotal(l) ? "" : "lg-zero"}`} title={bonusTitle(l)}>
                          {bonusTotal(l) ? money(bonusTotal(l)) : "—"}
                        </td>
                        <td
                          className={`lg-num ${hoaHongTotal(l) ? "" : "lg-zero"}`}
                          title={
                            hoaHongTotal(l)
                              ? "Hoa hồng kinh doanh — máy tự tính theo hoá đơn bán trong kỳ"
                              : "Chưa khai % hoa hồng ở hồ sơ lương của nhân viên kinh doanh"
                          }
                        >
                          {hoaHongTotal(l) ? money(hoaHongTotal(l)) : "—"}
                        </td>
                        {/* Nhóm Giảm trừ & Tạm ứng */}
                        <td
                          className={`lg-num ${getPhatVal(l) ? "lg-minus" : "lg-zero"}`}
                          title={chiTiet(phatRows(l))}
                        >
                          {getPhatVal(l) ? "−" + money(getPhatVal(l)) : "—"}
                        </td>
                        <td
                          className={`lg-num ${getBhThueVal(l) ? "lg-minus" : "lg-zero"}`}
                          title={chiTiet(bhThueRows(l))}
                        >
                          {getBhThueVal(l) ? "−" + money(getBhThueVal(l)) : "—"}
                        </td>
                        <td
                          className={`lg-num ${l.advance_total || l.luong_dot_1_total || (l.no_ung_ky_truoc ?? 0) ? "lg-minus" : "lg-zero"}`}
                        >
                          {l.luong_dot_1_total ? (
                            <div className="lg-subcell" title="Thanh toán lương đợt 1">
                              Đợt 1: −{money(l.luong_dot_1_total)}
                            </div>
                          ) : null}
                          {l.advance_total ? (
                            <div className="lg-subcell" title="Tạm ứng đã nhận">
                              Ứng: −{money(l.advance_total)}
                            </div>
                          ) : null}
                          {(l.no_ung_ky_truoc ?? 0) > 0 ? (
                            <div
                              className="lg-subcell lg-muted"
                              title="Nợ tạm ứng kỳ trước chuyển sang (trừ sau cùng, sau BHXH · đoàn phí · thuế)"
                            >
                              Nợ cũ: −{money(l.no_ung_ky_truoc ?? 0)}
                            </div>
                          ) : null}
                          {(l.no_ung_chuyen_ky_sau ?? 0) > 0 ? (
                            <div
                              className="lg-subcell lg-muted"
                              title="Chưa trừ hết — chuyển sang kỳ sau (tạm ứng trừ sau cùng)"
                            >
                              còn nợ {money(l.no_ung_chuyen_ky_sau ?? 0)}
                            </div>
                          ) : null}
                          {!l.advance_total && !l.luong_dot_1_total && !(l.no_ung_ky_truoc ?? 0) ? "—" : null}
                        </td>
                        <td className="lg-num lg-net">{money(l.net_pay)}</td>
                        <td
                          className="lg-rowact lg-sticky-act"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {canManage && !locked && (
                            <RowActionButton
                              dense
                              label="Sửa dòng lương"
                              icon="pencil"
                              onClick={() => setEditing(l)}
                            />
                          )}
                          <RowActionButton
                            dense
                            label="In phiếu lương"
                            icon="printer"
                            onClick={() => setPrinting(l)}
                          />
                        </td>
                      </tr>
                    );
                  })
                : shown.map((l) => {
                    const isSelected = selectedId === l.id;
                    const rowIncome = getLineIncome(l);
                    const rowDeduct = getLineDeductions(l);

                    const incomeTooltip = [
                      getLuongCongVal(l) > 0 ? `Lương công: ${money(getLuongCongVal(l))}` : "",
                      (l.chuyen_can ?? 0) > 0 ? `Chuyên cần: ${money(l.chuyen_can)}` : "",
                      phuCapTotal(l) > 0 ? chiTiet(phuCapRows(l), "") : "",
                      getKhoanSpVal(l) > 0 ? `Khoán SP: ${money(getKhoanSpVal(l))}` : "",
                      getKhoanKmVal(l) > 0 ? `Khoán km: ${money(getKhoanKmVal(l))}` : "",
                      (l.thuong_to_truong ?? 0) !== 0 ? `Thưởng TT: ${money(l.thuong_to_truong)}` : "",
                      getTangCaVal(l) > 0 ? `Tăng ca/Lễ: ${money(getTangCaVal(l))}` : "",
                      getCaDemVal(l) > 0 ? `Ca đêm: ${money(getCaDemVal(l))}` : "",
                      bonusTotal(l) > 0 ? `Thưởng: ${money(bonusTotal(l))}` : "",
                      hoaHongTotal(l) > 0 ? `Hoa hồng: ${money(hoaHongTotal(l))}` : "",
                    ].filter(Boolean).join(" · ") || "0đ";

                    const deductTooltip = [
                      chiTiet(phatRows(l)),
                      chiTiet(bhThueRows(l)),
                      (l.luong_dot_1_total ?? 0) > 0 ? `Đợt 1: −${money(l.luong_dot_1_total)}` : "",
                      (l.advance_total ?? 0) > 0 ? `Tạm ứng: −${money(l.advance_total)}` : "",
                      (l.no_ung_ky_truoc ?? 0) > 0 ? `Nợ cũ: −${money(l.no_ung_ky_truoc)}` : "",
                      (l.no_ung_chuyen_ky_sau ?? 0) > 0
                        ? `Chưa trừ hết, chuyển kỳ sau: +${money(l.no_ung_chuyen_ky_sau)}`
                        : "",
                    ].filter(Boolean).join(" · ") || "0đ";

                    return (
                      <tr
                        key={l.id}
                        className={isSelected ? "is-selected" : ""}
                        onClick={() => setSelectedId(isSelected ? null : l.id)}
                      >
                        <td className="ns__code lg-sticky-code">{l.employee_code}</td>
                        <td className="lg-sticky-name">
                          {l.employee_name}{" "}
                          {l.chua_khai_luong && (
                            <span
                              className="rc-pill rc-pill--off"
                              title="Có công nhưng chưa khai mức lương ở Lương → Lương nhân viên — đang tính 0đ, kỳ này chưa chốt được"
                            >
                              chưa khai lương
                            </span>
                          )}{" "}
                          {/* Ô "Mức đóng BHXH" khai riêng từng người (16/09/2026): mốc lương CŨ còn
                              trống thì engine tạm đóng theo mức nền — gắn nhãn để HCNS khai lại. */}
                          {l.chua_khai_muc_bh && (
                            <span
                              className="rc-pill rc-pill--off"
                              title="Chưa khai Mức đóng BHXH ở hồ sơ lương — đang tạm đóng theo lương cơ bản + trách nhiệm. Khai lại ở Lương → Lương nhân viên → Sửa lương."
                            >
                              chưa khai mức BHXH
                            </span>
                          )}{" "}
                          {l.is_probation && (
                            <span className="ns-badge ns-badge--muted">TV</span>
                          )}
                        </td>
                        <td>{l.department_name ?? "—"}</td>
                        <td className="lg-num">
                          {l.actual_cong}
                          {(l.special_cong ?? 0) > 0 || l.luong_ngay_le ? (
                            <span className="lg-cong-le"> •</span>
                          ) : null}
                        </td>
                        <td className="lg-num lg-plus-val" title={incomeTooltip}>
                          +{money(rowIncome)}
                        </td>
                        <td
                          className={`lg-num ${rowDeduct > 0 ? "lg-minus" : "lg-zero"}`}
                          title={deductTooltip}
                        >
                          {rowDeduct > 0 ? "−" + money(rowDeduct) : "—"}
                        </td>
                        <td className="lg-num lg-net">{money(l.net_pay)}</td>
                        <td
                          className="lg-rowact lg-sticky-act"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {canManage && !locked && (
                            <RowActionButton
                              dense
                              label="Sửa dòng lương"
                              icon="pencil"
                              onClick={() => setEditing(l)}
                            />
                          )}
                          <RowActionButton
                            dense
                            label="In phiếu lương"
                            icon="printer"
                            onClick={() => setPrinting(l)}
                          />
                        </td>
                      </tr>
                    );
                  })}
              {/* colSpan đúng theo chế độ xem đang chọn */}
              {shown.length === 0 && (
                <EmptyRow
                  colSpan={viewMode === "detailed" ? 19 : 8}
                  trangThai={
                    listErr ? "loi" : listLoading ? "dang-tai" : "rong"
                  }
                  loi={listErr}
                  onThuLai={load}
                  icon="users"
                  title={
                    lines.length
                      ? "Chưa có ai khớp bộ lọc"
                      : "Chưa có dòng lương nào trong kỳ"
                  }
                  sub={
                    lines.length
                      ? "Bỏ bớt từ khoá, phòng/tổ hoặc nhóm Chính thức / Thử việc rồi xem lại."
                      : "Bấm “Tính lại” để dựng lại bảng lương của kỳ này từ chấm công."
                  }
                  action={
                    lines.length ? (
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => {
                          setQ("");
                          setDept("all");
                          setFilter("all");
                        }}
                      >
                        Xoá bộ lọc
                      </button>
                    ) : undefined
                  }
                />
              )}
            </tbody>
            <tfoot>
              {viewMode === "detailed" ? (
                <tr className="lg-foot">
                  <td className="lg-sticky-code lg-foot-cell">Tổng ({shown.length})</td>
                  <td className="lg-sticky-name lg-foot-cell"></td>
                  <td className="lg-foot-cell"></td>
                  <td className="lg-num lg-foot-val">{totals.actualCong.toLocaleString("vi-VN")}</td>
                  <td className="lg-num lg-foot-val">{totals.luongCong ? money(totals.luongCong) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.chuyenCan ? money(totals.chuyenCan) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.allowance ? money(totals.allowance) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.khoanSp ? money(totals.khoanSp) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.khoanKm ? money(totals.khoanKm) : "—"}</td>
                  <td className={`lg-num lg-foot-val ${totals.thuongTt < 0 ? "lg-minus" : ""}`}>
                    {totals.thuongTt ? money(totals.thuongTt) : "—"}
                  </td>
                  <td className="lg-num lg-foot-val">{totals.tangCa ? money(totals.tangCa) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.caDem ? money(totals.caDem) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.thuong ? money(totals.thuong) : "—"}</td>
                  <td className="lg-num lg-foot-val">{totals.hoaHong ? money(totals.hoaHong) : "—"}</td>
                  <td className="lg-num lg-foot-val lg-minus">{totals.phat ? "−" + money(totals.phat) : "—"}</td>
                  <td className="lg-num lg-foot-val lg-minus">{totals.bhThue ? "−" + money(totals.bhThue) : "—"}</td>
                  <td className="lg-num lg-foot-val lg-minus">{totals.tamUng ? "−" + money(totals.tamUng) : "—"}</td>
                  <td className="lg-num lg-net lg-foot-val">{money(totals.net)}</td>
                  <td className="lg-sticky-act lg-foot-cell"></td>
                </tr>
              ) : (
                <tr className="lg-foot">
                  <td className="lg-sticky-code lg-foot-cell">Tổng ({shown.length})</td>
                  <td className="lg-sticky-name lg-foot-cell"></td>
                  <td className="lg-foot-cell"></td>
                  <td className="lg-num lg-foot-val">{totals.actualCong.toLocaleString("vi-VN")}</td>
                  <td className="lg-num lg-plus-val lg-foot-val">+{money(totals.gross)}</td>
                  <td className="lg-num lg-minus lg-foot-val">{totals.deductions ? "−" + money(totals.deductions) : "—"}</td>
                  <td className="lg-num lg-net lg-foot-val">{money(totals.net)}</td>
                  <td className="lg-sticky-act lg-foot-cell"></td>
                </tr>
              )}
            </tfoot>
          </table>
        </div>
      )}

      {editing && (
        <LineEditModal
          token={token}
          line={editing}
          readOnly={!isDraft}
          onClose={() => {
            setEditing(null);
            load();
          }}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {soiKm && period && (
        <SoiKhoanKm
          token={token}
          line={soiKm}
          period={period}
          onClose={() => setSoiKm(null)}
        />
      )}

      {printing && period && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box ns-modal__box--wide">
            <header className="ns-modal__head lg-payslip-noprint">
              <h2>Phiếu lương — {printing.employee_name}</h2>
              <button className="ns-modal__x" onClick={() => setPrinting(null)}>
                ×
              </button>
            </header>
            <div className="ns-modal__body">
              <PayslipCard line={printing} period={period} />
            </div>
            <footer className="ns-modal__foot lg-payslip-noprint">
              <button
                className="btn btn--ghost"
                onClick={() => setPrinting(null)}
              >
                Đóng
              </button>
              <button
                className="btn btn--primary"
                onClick={() => window.print()}
              >
                🖨 In phiếu
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
