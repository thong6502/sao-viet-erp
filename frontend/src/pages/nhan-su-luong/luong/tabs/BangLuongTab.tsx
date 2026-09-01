// Tab Bảng lương tháng (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Calendar,
  DollarSign,
  Download,
  Users,
  Clock,
  TrendingDown,
  Search,
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
  bonusTitle,
  bonusTotal,
  curYm,
  errText,
  hoaHongTotal,
  money,
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
  const totalNet = shown.reduce((s, l) => s + l.net_pay, 0);
  const totalStaff = shown.length;
  const officialCount = shown.filter((l) => !l.is_probation).length;
  const probationCount = shown.filter((l) => l.is_probation).length;
  const totalWorkdays = shown.reduce((s, l) => s + (l.actual_cong ?? 0), 0);
  const totalDeductions = shown.reduce(
    (s, l) =>
      s +
      (l.vi_pham ?? 0) +
      (l.bhxh ?? 0) +
      (l.advance_total ?? 0) +
      (l.luong_dot_1_total ?? 0),
    0,
  );

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
        {/* Nút CAM (`btn--accent`) = việc chính của màn. "Tính lại" và "Khởi tạo bảng lương" là
            CÙNG một việc ở hai trạng thái nên cùng vai; hai nút KHÔNG BAO GIỜ hiện cùng lúc
            ("Tính lại" đòi `period`, "Khởi tạo" nằm trong nhánh `!period`) nên vẫn đúng luật
            MỖI MÀN CHỈ MỘT NÚT CAM. Thêm nút cam thứ hai vào thanh này là phá luật đó.
            ⚠️ `btn--primary` trong bộ CSS này ra màu NAVY, không phải cam — đừng "sửa" ngược lại. */}
        {canManage && isDraft && period && (
          <button
            className="btn btn--accent"
            onClick={() => run(() => api.luong.generate(token, year, month))}
            disabled={busy}
          >
            {busy ? "Đang tính…" : "↻ Tính lại"}
          </button>
        )}
        {canLockPeriod && period && isDraft && (
          // Kỳ công chưa chốt ⇒ KHOÁ nút chứ không để bấm rồi ăn lỗi đỏ (luật đợt 5). `title` là
          // chỗ DUY NHẤT nói được lý do khi nút đã xám, nên phải nói rõ phải làm gì tiếp.
          <button
            className="btn btn--ghost"
            onClick={() => run(() => api.luong.lock(token, year, month))}
            disabled={busy || Boolean(chanChotLyDo)}
            title={chanChotLyDo ?? undefined}
          >
            🔒 Chốt
          </button>
        )}
        {canLockPeriod && locked && (
          <button
            className="btn btn--ghost"
            onClick={() => run(() => api.luong.reopen(token, year, month))}
            disabled={busy}
          >
            Mở lại
          </button>
        )}
        {canMarkPaid && locked && (
          <button
            className="btn btn--primary"
            onClick={() => run(() => api.luong.pay(token, year, month))}
            disabled={busy}
          >
            💵 Đã chi
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
            ↩ Hủy đã chi
          </button>
        )}
        {/* CÔNG BỐ PHIẾU LƯƠNG (12/08/2026) — trả lời câu "KHI NÀO người lao động thấy phiếu".
            Chỉ hiện khi kỳ ĐÃ CHỐT: bản nháp thì số chưa đóng băng, phát ra là mời người ta đọc
            một con số sắp đổi. Gác chung ô quyền với Chốt bảng lương (đường 2 — bớt ô để quên). */}
        {canLockPeriod && (locked || paid) && (
          <button
            className="btn btn--ghost"
            onClick={() =>
              setCongBo((v) => (v ? null : { mo: "", dong: "" }))
            }
            disabled={busy}
            title="Chọn khoảng thời gian người lao động xem được phiếu lương của kỳ này."
          >
            📤 {period?.cong_bo_luc ? "Đổi lịch phiếu" : "Công bố phiếu"}
          </button>
        )}
        {canLockPeriod && period?.cong_bo_luc && (
          <button
            className="btn btn--ghost"
            onClick={() => run(() => api.luong.thuHoi(token, year, month))}
            disabled={busy}
            title="Rút phiếu lại — người lao động thôi thấy ngay lập tức."
          >
            ↩ Thu hồi phiếu
          </button>
        )}
        {/* Ký tự ⬇ gõ thẳng trong chuỗi đã bỏ: mỗi hệ điều hành vẽ một kiểu, không nhận màu/kích
            thước theo nút. Dùng icon thật. Bộ `components/Icons.tsx` KHÔNG có glyph tải xuống
            (đã soát: gần nhất chỉ là `chevron` — mũi tên xuống của menu, đọc thành "mở danh
            sách"), nên lấy `Download` của lucide đúng như màn Nhân sự đang dùng cho CHÍNH nút
            "Xuất Excel" (NhanSuPage.tsx:654). Nhãn giữ nguyên: backend nay sinh .xlsx thật. */}
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
        {locked && <span className="ns-badge ns-badge--muted">Đã chốt</span>}
        {paid && (
          <span className="ns-badge ns-badge--muted">
            💵 Đã chi
            {/* `fmtDateTime` (utils/format) chứ không phải `new Date().toLocaleDateString`:
                backend trả mốc thời gian UTC KHÔNG có hậu tố Z, để `new Date()` tự hiểu là giờ
                địa phương thì ngày chi lệch mất một hôm nếu chi vào đầu/cuối ngày. */}
            {period?.paid_at ? ` ${fmtDateTime(period.paid_at)}` : ""}
          </span>
        )}
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

      {period && (
        <div className="lg-kpi-grid">
          <div className="lg-kpi-card lg-kpi-card--net">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <DollarSign size={15} />
              </span>
              <span className="lg-kpi-card-label">Tổng thực lĩnh</span>
            </div>
            <div className="lg-kpi-card-val">{money(totalNet)}đ</div>
            <div className="lg-kpi-card-sub">
              Chi trả cho {totalStaff} nhân sự
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--staff">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <Users size={15} />
              </span>
              <span className="lg-kpi-card-label">Quy mô nhân sự</span>
            </div>
            <div className="lg-kpi-card-val">{totalStaff} người</div>
            <div className="lg-kpi-card-sub">
              {officialCount} chính thức · {probationCount} thử việc
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--workday">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <Clock size={15} />
              </span>
              <span className="lg-kpi-card-label">Tổng ngày công</span>
            </div>
            <div className="lg-kpi-card-val">
              {totalWorkdays.toLocaleString("vi-VN")} công
            </div>
            <div className="lg-kpi-card-sub">
              Trung bình{" "}
              {(totalStaff ? totalWorkdays / totalStaff : 0).toFixed(1)}{" "}
              công/người
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--deduct">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <TrendingDown size={15} />
              </span>
              <span className="lg-kpi-card-label">Khấu trừ & Tạm ứng</span>
            </div>
            <div className="lg-kpi-card-val">−{money(totalDeductions)}đ</div>
            <div className="lg-kpi-card-sub">Bảo hiểm, phạt và ứng lương</div>
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
                    <span className="lg-source-name">Khấu trừ & Tạm ứng</span>
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
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Họ tên</th>
                <th>Phòng/Tổ</th>
                <th className="lg-num">Công</th>
                <th className="lg-num">Lương công</th>
                <th className="lg-num">Chuyên cần</th>
                <th className="lg-num">Phụ cấp</th>
                <th className="lg-num">Khoán</th>
                {/* Khoán km đứng cạnh Khoán vì cùng loại: tiền máy tự tính từ sản lượng/km, cộng
                    phẳng lên lương chấm công. Cột RIÊNG chứ không gộp — bài học hoa hồng. */}
                <th className="lg-num">Khoán km</th>
                <th className="lg-num">Tăng ca</th>
                <th className="lg-num">Ca đêm</th>
                <th className="lg-num">Vi phạm</th>
                <th className="lg-num">Thưởng</th>
                {/* Hoa hồng đứng CẠNH Thưởng vì trước 24/08/2026 nó nằm lẫn bên trong cột đó —
                    để sát nhau thì người quen bảng cũ nhìn ra ngay số đã tách đi đâu. */}
                <th className="lg-num">Hoa hồng</th>
                <th className="lg-num">BHXH</th>
                <th className="lg-num">Đợt 1 / Tạm ứng</th>
                <th className="lg-num lg-net">Thực lĩnh</th>
                {/* Tên cột thống nhất toàn hệ là "Thao tác" (không phải "Hành động"), và có CHỮ
                    chứ không để trống — ô trống thì người đọc bảng 16 cột không biết cột cuối
                    làm gì. `lg-actcol` canh phải để tiêu đề đứng thẳng cột nút. */}
                <th className="lg-actcol">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((l) => (
                <tr key={l.id}>
                  <td className="ns__code">{l.employee_code}</td>
                  <td>
                    {l.employee_name}{" "}
                    {l.is_probation && (
                      <span className="ns-badge ns-badge--muted">TV</span>
                    )}
                  </td>
                  <td>{l.department_name ?? "—"}</td>
                  <td className="lg-num">{l.actual_cong}</td>
                  <td className="lg-num">{money(l.luong_cong)}</td>
                  <td className="lg-num">{money(l.chuyen_can)}</td>
                  <td className="lg-num">{money(l.allowance)}</td>
                  <td className="lg-num">{l.khoan ? money(l.khoan) : "—"}</td>
                  <td className="lg-num">
                    {l.khoan_km ? (
                      // Bấm được ⇒ phải TRÔNG như bấm được. Số gạch chân kiểu link, không phải
                      // một con số trơ mà người dùng phải đoán là có thể bấm.
                      <button
                        type="button"
                        className="lg-linkbtn"
                        title="Xem từng chuyến giao đã sinh ra số này"
                        onClick={() => setSoiKm(l)}
                      >
                        {money(l.khoan_km)}
                      </button>
                    ) : (
                      <span title="Không có chuyến giao trong kỳ, hoặc tổ chưa bật Bộ phận Giao hàng">
                        —
                      </span>
                    )}
                  </td>
                  <td
                    className="lg-num"
                    title={
                      l.ot_minutes
                        ? `${(l.ot_minutes / 60).toFixed(1)}h tăng ca`
                        : ""
                    }
                  >
                    {l.ot_pay ? money(l.ot_pay) : "—"}
                  </td>
                  <td
                    className="lg-num"
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
                  <td className={`lg-num ${l.vi_pham ? "lg-minus" : ""}`}>
                    {l.vi_pham ? "−" + money(l.vi_pham) : "—"}
                  </td>
                  {/* "Thưởng" = khoản PHÁT SINH kỳ này (`source='line'`) + 6 cột thưởng cũ đã
                      ngừng ghi. Khoản từ hồ sơ KHÔNG tính ở đây — nó nằm ở cột "Phụ cấp"
                      (`allowance`); cộng cả hai là đếm đôi trên bảng. */}
                  <td className="lg-num" title={bonusTitle(l)}>
                    {bonusTotal(l) ? money(bonusTotal(l)) : "—"}
                  </td>
                  <td
                    className="lg-num"
                    title={
                      hoaHongTotal(l)
                        ? "Hoa hồng kinh doanh — máy tự tính theo hoá đơn bán trong kỳ"
                        : "Chưa khai % hoa hồng ở hồ sơ lương của nhân viên kinh doanh"
                    }
                  >
                    {hoaHongTotal(l) ? money(hoaHongTotal(l)) : "—"}
                  </td>
                  <td className="lg-num lg-minus">
                    {l.bhxh ? "−" + money(l.bhxh) : "—"}
                  </td>
                  <td
                    className={`lg-num ${l.advance_total || l.luong_dot_1_total ? "lg-minus" : ""}`}
                  >
                    {l.luong_dot_1_total ? (
                      <div title="Thanh toán lương đợt 1">
                        −{money(l.luong_dot_1_total)}
                      </div>
                    ) : null}
                    {l.advance_total ? (
                      <div title="Tạm ứng đã nhận">
                        −{money(l.advance_total)}
                      </div>
                    ) : null}
                    {!l.advance_total && !l.luong_dot_1_total ? "—" : null}
                  </td>
                  <td className="lg-num lg-net">{money(l.net_pay)}</td>
                  <td className="lg-rowact">
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
              ))}
              {/* colSpan=18 = ĐÚNG số cột đang hiện (16 → 17 khi tách cột "Hoa hồng" → 18 khi
                  thêm "Khoán km", cùng ngày 24/08/2026). Bảng này KHÔNG ẩn/hiện cột theo quyền
                  (chỉ nút trong ô Thao tác mới theo quyền) nên số cứng là đúng — thêm/bớt <th>
                  thì phải sửa cả số này lẫn colSpan của <tfoot> bên dưới. */}
              {shown.length === 0 && (
                <EmptyRow
                  colSpan={18}
                  trangThai={
                    listErr ? "loi" : listLoading ? "dang-tai" : "rong"
                  }
                  loi={listErr}
                  onThuLai={load}
                  icon="users"
                  // "Chưa có…" chứ không "Không có…": dữ liệu chưa tới, không phải phán quyết.
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
              <tr className="lg-foot">
                <td colSpan={16}>Tổng thực lĩnh ({shown.length} người)</td>
                <td className="lg-num lg-net">{money(totalNet)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {editing && (
        <LineEditModal
          token={token}
          line={editing}
          readOnly={!isDraft}
          // Khối "Khoản phát sinh" lưu NGAY từng thao tác ⇒ đóng màn cũng phải tải lại bảng,
          // không thì cột phụ cấp / TNCN của dòng đó còn là số trước khi thêm khoản.
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
