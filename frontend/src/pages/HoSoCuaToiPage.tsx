// "Hồ sơ của tôi" — nhà chung self-service cho MỌI tài khoản (module không gate `nhan_su`).
// - Nhân viên (có hồ sơ /me): xem hồ sơ của mình, tự sửa liên lạc; định danh/lương do HCNS quản lý.
// - Admin / tài khoản chưa gắn hồ sơ: self-service tài khoản (ảnh · tên · mật khẩu) + xem thông tin tài khoản.
// Gộp từ hộp thoại "Tài khoản" cũ (ProfileDialog) — 1 nhà chung thay cho menu 4 mục ở Topbar.
//
// MỘT TRANG CUỘN, KHÔNG TAB: chip "Đề nghị chờ duyệt" phải CUỘN TỚI khối đề nghị (đổi tab rồi mới
// cuộn là mất ngữ cảnh), và băng "hồ sơ còn thiếu" chỉ có nghĩa khi nhìn được toàn cảnh ô trống.
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  ApiError,
  api,
  assetUrl,
  type EmployeeAttachment,
  type EmployeeDetail,
  type EmployeeEvent,
  type LeaveQuota,
  type MyContactInput,
  type PayrollLine,
  type PayrollPeriod,
  type Profile,
  type UpdateRequest,
  type UpdateRequestInput,
  type WorkShift,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { Field } from "../components/Field";
import { Icon, type IconName } from "../components/Icons";
import { Timeline, type TimelineEntry } from "../components/Timeline";
import "./nhan-su.css";
import "./ho-so-cua-toi.css";

const STATUS_LABEL: Record<string, string> = {
  probation: "Thử việc", active: "Chính thức", on_leave: "Nghỉ dài hạn",
  suspended: "Đình chỉ", resigned: "Đã nghỉ",
};
const STATUS_CLASS: Record<string, string> = {
  probation: "ns-badge--warn", active: "ns-badge--ok", on_leave: "ns-badge--info",
  suspended: "ns-badge--muted", resigned: "ns-badge--danger",
};
const GENDER_LABEL: Record<string, string> = { male: "Nam", female: "Nữ", other: "Khác" };
const DOC_KIND_LABEL: Record<string, string> = {
  hop_dong: "Hợp đồng", cccd: "CCCD", bang_cap: "Bằng cấp", khac: "Khác",
};
const EVENT_LABEL: Record<string, string> = {
  hired: "Vào làm", confirmed: "Chuyển chính thức", transferred: "Điều chuyển",
  promoted: "Nâng bậc / đổi chức danh", leave_start: "Bắt đầu nghỉ dài hạn",
  leave_end: "Đi làm lại", suspended: "Đình chỉ", resigned: "Nghỉ việc", reinstated: "Tuyển lại",
};
// Nhãn cách tính thuế TNCN. `null` KHÔNG có ở đây: null = bị che quyền, xử riêng (ẩn cả dòng).
const PIT_MODE_LABEL: Record<string, string> = {
  luy_tien: "Luỹ tiến (HĐ ≥ 3 tháng)", khau_tru_10: "Khấu trừ 10%", cam_ket_08: "Cam kết 08/CK-TNCN",
};
const REQ_STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt", approved: "Đã duyệt", rejected: "Từ chối", cancelled: "Đã rút lại",
};

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString("vi-VN");
}
function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
const fmtSo = (n: number): string => n.toLocaleString("vi-VN");

/** Thâm niên tổng = thâm niên khai TRƯỚC khi vào (tháng) + số tháng từ `hire_date` tới nay.
 *  Bỏ vế đầu là tính hụt với người chuyển từ nơi khác sang. Trả null khi chưa có gì để hiện. */
function thamNien(priorMonths: number | undefined, hireDate: string | null | undefined): string | null {
  let tuNgayVao = 0;
  if (hireDate) {
    const h = new Date(hireDate);
    if (!Number.isNaN(h.getTime())) {
      const now = new Date();
      tuNgayVao = Math.max(0, (now.getFullYear() - h.getFullYear()) * 12 + (now.getMonth() - h.getMonth()));
    }
  }
  const tong = (priorMonths ?? 0) + tuNgayVao;
  if (tong <= 0) return null;
  return `${Math.floor(tong / 12)} năm ${tong % 12} tháng`;
}

// --- Trạng thái tải của MỘT nguồn số liệu ------------------------------------
// Bốn ca phải phân biệt được: đang tải · có số · rỗng thật · LỖI. Gộp "lỗi" vào "rỗng" (kiểu
// `.catch(() => setX([]))`) là để máy nói sai sự thật với người dùng — màn in "chưa có gì"
// trong khi máy chủ đang chết.
type Tai<T> =
  | { tt: "dang-tai" }
  | { tt: "ok"; du: T }
  | { tt: "rong"; vi_sao: string }
  | { tt: "loi" };

const DANG_TAI = { tt: "dang-tai" } as const;

interface SoPhep { con_lai: number; da_dung: number; han_muc: number; ten: string; them: number }
interface SoCong { cong: number; chuan: number | null; ngay: number; thang: number }
interface SoLuong { ky: PayrollPeriod; dong: PayrollLine }

export function HoSoCuaToiPage({ navigate }: { navigate?: NavigateFn }) {
  const { token, user } = useAuth();
  const [emp, setEmp] = useState<EmployeeDetail | null>(null);
  const [hasEmp, setHasEmp] = useState<boolean | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [events, setEvents] = useState<EmployeeEvent[]>([]);
  const [files, setFiles] = useState<Tai<EmployeeAttachment[]>>(DANG_TAI);
  const [shift, setShift] = useState<WorkShift | null>(null);
  const [editing, setEditing] = useState(false);
  const [reqs, setReqs] = useState<Tai<UpdateRequest[]>>(DANG_TAI);
  const [requesting, setRequesting] = useState(false);
  const [huyReq, setHuyReq] = useState<UpdateRequest | null>(null);
  const [huyBusy, setHuyBusy] = useState(false);
  const [huyErr, setHuyErr] = useState<string | null>(null);
  const [xemHetReq, setXemHetReq] = useState(false);
  // Số liệu "của tôi" — mỗi nguồn tải/thử lại ĐỘC LẬP, hỏng một chip không kéo sập cả màn.
  const [phep, setPhep] = useState<Tai<SoPhep>>(DANG_TAI);
  const [cong, setCong] = useState<Tai<SoCong>>(DANG_TAI);
  const [luong, setLuong] = useState<Tai<SoLuong>>(DANG_TAI);
  // Self-service tài khoản (gộp từ ProfileDialog): ảnh · mật khẩu · tên (tên chỉ cho tài khoản không hồ sơ).
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [nameOpen, setNameOpen] = useState(false);
  const reqRef = useRef<HTMLDivElement>(null);
  const [nhayReq, setNhayReq] = useState(false);

  const loadReqs = useCallback(() => {
    if (!token) return;
    api.employees.myRequests(token)
      .then((r) => setReqs({ tt: "ok", du: r.items }))
      .catch(() => setReqs({ tt: "loi" }));
  }, [token]);

  const load = useCallback(() => {
    if (!token) return;
    api.employees.me(token).then((r) => { setHasEmp(r.has_employee); setEmp(r.employee); }).catch(() => setHasEmp(false));
    api.profile(token).then(setProfile).catch(() => setProfile(null));
    api.employees.myEvents(token).then((r) => setEvents(r.items)).catch(() => setEvents([]));
    api.employees.myAttachments(token)
      .then((r) => setFiles({ tt: "ok", du: r.items }))
      .catch(() => setFiles({ tt: "loi" }));
    loadReqs();
  }, [token, loadReqs]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (emp?.default_shift_id && token) {
      api.attendance.shifts(token).then((r) => setShift(r.items.find((s) => s.id === emp.default_shift_id) ?? null)).catch(() => setShift(null));
    }
  }, [token, emp?.default_shift_id]);

  // --- 3 nguồn số liệu "của tôi" (chỉ nhánh nhân viên) ---------------------
  const napPhep = useCallback(() => {
    if (!token) return;
    setPhep(DANG_TAI);
    api.leaves.me(token, { size: 1 })
      .then((r) => {
        const qs: LeaveQuota[] = (r.quotas ?? []).filter((q) => q.annual_quota > 0);
        if (!r.has_employee || qs.length === 0) { setPhep({ tt: "rong", vi_sao: "Chưa khai quỹ phép năm" }); return; }
        // Loại phép chính = hạn mức lớn nhất (phép năm); các loại còn lại gộp thành "+N loại khác".
        const chinh = qs.reduce((a, b) => (b.annual_quota > a.annual_quota ? b : a));
        setPhep({ tt: "ok", du: { con_lai: chinh.remaining, da_dung: chinh.used, han_muc: chinh.annual_quota, ten: chinh.name, them: qs.length - 1 } });
      })
      // 403 (vai không có quyền đọc nghỉ phép) cũng rơi vào đây — coi như chưa có số, không dọa lỗi.
      .catch((e) => setPhep(e instanceof ApiError && e.status === 403
        ? { tt: "rong", vi_sao: "Bạn không xem được mục nghỉ phép" } : { tt: "loi" }));
  }, [token]);

  const napCong = useCallback((employeeId: number) => {
    if (!token) return;
    setCong(DANG_TAI);
    const now = new Date();
    const y = now.getFullYear(), m = now.getMonth() + 1;
    api.attendance.myTimesheet(token, y, m)
      .then((r) => {
        // `rows` có thể chứa nhiều người (tổ trưởng có scope) — phải tìm ĐÚNG dòng của mình,
        // không lấy rows[0]. `standard_cong` nằm ở cấp bảng, không ở dòng.
        const row = r.rows.find((x) => x.employee_id === employeeId);
        if (!row) { setCong({ tt: "rong", vi_sao: "Chưa có dữ liệu công tháng này" }); return; }
        setCong({ tt: "ok", du: { cong: row.total_cong ?? 0, chuan: r.standard_cong ?? null, ngay: row.total_days, thang: m } });
      })
      .catch(() => setCong({ tt: "loi" }));
  }, [token]);

  const napLuong = useCallback(() => {
    if (!token) return;
    setLuong(DANG_TAI);
    api.luong.myPayslip(token)
      .then((r) => {
        if (!r.has_employee || !r.line || !r.period) { setLuong({ tt: "rong", vi_sao: "Chưa có kỳ lương nào" }); return; }
        setLuong({ tt: "ok", du: { ky: r.period, dong: r.line } });
      })
      .catch((e) => setLuong(e instanceof ApiError && e.status === 403
        ? { tt: "rong", vi_sao: "Bạn không xem được phiếu lương" } : { tt: "loi" }));
  }, [token]);

  useEffect(() => {
    if (!emp) return;
    napPhep();
    napCong(emp.id);
    napLuong();
  }, [emp, napPhep, napCong, napLuong]);

  const tl: TimelineEntry[] = events.map((ev) => {
    const tone: TimelineEntry["tone"] | undefined =
      ev.event_type === "hired" ? "rust"
      : ["confirmed", "promoted", "leave_end", "reinstated"].includes(ev.event_type) ? "moss"
      : ev.event_type === "transferred" ? "steel"
      : ["resigned", "suspended", "leave_start"].includes(ev.event_type) ? "signal" : undefined;
    return {
      title: EVENT_LABEL[ev.event_type] ?? ev.event_type,
      meta: [fmtDate(ev.effective_date), ev.note || null].filter(Boolean).join(" · "),
      accent: tone === "moss" || tone === "rust", tone,
    };
  });

  const dsReq = reqs.tt === "ok" ? reqs.du : [];
  const choDuyet = dsReq.filter((r) => r.status === "pending");
  // Ô còn trống — tách hai nhóm vì hai nhóm dẫn tới HAI việc khác nhau: tự điền vs gửi đề nghị.
  const thieu = useMemo(() => oThieu(emp), [emp]);

  const cuonToiReq = useCallback(() => {
    reqRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setNhayReq(true);
    setTimeout(() => setNhayReq(false), 1800);
  }, []);

  async function xacNhanHuy() {
    if (!huyReq || !token) return;
    setHuyBusy(true); setHuyErr(null);
    try {
      await api.employees.cancelMyRequest(token, huyReq.id);
      setHuyReq(null); setHuyBusy(false);
      loadReqs();
    } catch (e) { setHuyErr(messageFor(e)); setHuyBusy(false); }
  }

  if (hasEmp === null) return <main className="ns"><p className="ns__empty">Đang tải…</p></main>;

  // Nút ✎ overlay trên avatar → mở AvatarModal (dùng chung 2 nhánh).
  const avatarEditBtn = (
    <button type="button" className="mine__avatar-edit" aria-label="Đổi ảnh đại diện" onClick={() => setAvatarOpen(true)}>
      <Icon name="pencil" size={15} />
    </button>
  );
  // Các modal self-service (mount cuối mỗi nhánh). AvatarModal cập nhật KÉP (topbar + hero) qua updateUser+load.
  const accountModals = (
    <>
      {avatarOpen && <AvatarModal onClose={() => setAvatarOpen(false)} onSaved={() => { setAvatarOpen(false); load(); }} />}
      {pwOpen && <PasswordModal onClose={() => setPwOpen(false)} />}
      {nameOpen && <NameModal onClose={() => setNameOpen(false)} onSaved={() => { setNameOpen(false); load(); }} />}
    </>
  );
  // Khối "Tài khoản & bảo mật" — DÙNG CHUNG hai nhánh (trước đây nhánh NV chỉ có dòng
  // "Mật khẩu ••••••••" không mang thông tin gì, còn thông tin tài khoản thật thì chỉ nhánh admin có).
  const accountCard = (
    <div className="mine__card mine__wide">
      <div className="mine__reqhead">
        <h4 className="ns-info-card__title" style={{ border: 0, margin: 0, padding: 0 }}>
          <Icon name="shield" size={14} /> Tài khoản &amp; bảo mật
        </h4>
        <Button variant="ghost" onClick={() => setPwOpen(true)}>Đổi mật khẩu</Button>
      </div>
      <div className="mine__acct-grid">
        <Row k="Tên đăng nhập" v={profile?.username} />
        <Row k="Vai trò" v={profile?.role_name} rong="Chưa gán" />
        <Row k="Phòng ban" v={profile?.department_name} rong="Chưa gán" />
        <Row k="Ngày tạo tài khoản" v={profile ? fmtDateTime(profile.created_at) : null} />
      </div>
      <p className="cc-note mine__acct-note">
        Mật khẩu không hiển thị được. Đổi ngay nếu bạn nghi có người khác biết.
      </p>
    </div>
  );

  // === NHÁNH ADMIN / TÀI KHOẢN CHƯA GẮN HỒ SƠ: self-service tài khoản ===
  if (!hasEmp || !emp) {
    const display = user?.name?.trim() || user?.username || "—";
    const avatarSrc = assetUrl(user?.avatar_url);
    const initials = display.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
    return (
      <main className="ns mine">
        <div className="mine__hero">
          <div className="mine__avatar-wrap">
            <div className="ns-avatar ns-avatar--xl">{avatarSrc ? <img src={avatarSrc} alt="" /> : initials}</div>
            {avatarEditBtn}
          </div>
          <div className="mine__heroid">
            <h1>
              {display}
              <button type="button" className="mine__name-edit" aria-label="Đổi tên hiển thị" onClick={() => setNameOpen(true)}>
                <Icon name="pencil" size={14} />
              </button>
            </h1>
            <p className="mine__herosub">{user?.username ?? ""}</p>
          </div>
        </div>

        {accountCard}
        {accountModals}
      </main>
    );
  }

  // === NHÁNH NHÂN VIÊN: hồ sơ của tôi ===
  const tn = thamNien(emp.prior_seniority_months, emp.hire_date);
  const bac = emp.job_grade_name ?? emp.job_grade;   // job_grade_name = nguồn sự thật; cột chữ chỉ để đọc dữ liệu cũ
  const badgeTrangThai = emp.status === "probation" && emp.probation_end_date
    ? `${STATUS_LABEL.probation} · đến ${fmtDate(emp.probation_end_date)}`
    : STATUS_LABEL[emp.status] ?? emp.status;

  const statusBadgeClass = STATUS_CLASS[emp.status]
    ? `mine__hero-badge--${emp.status === "active" ? "ok" : emp.status === "probation" ? "warn" : "muted"}`
    : "mine__hero-badge--muted";
  const statusDotClass = emp.status === "active" ? "mine__status-dot--active"
    : emp.status === "probation" ? "mine__status-dot--probation" : "";

  return (
    <main className="ns mine">
      <div className="mine__hero">
        <div className="mine__avatar-wrap">
          <div className="ns-avatar ns-avatar--xl">
            {assetUrl(emp.photo_url) ? <img src={assetUrl(emp.photo_url)!} alt="" /> : emp.full_name.slice(0, 1)}
          </div>
          {statusDotClass && <span className={`mine__status-dot ${statusDotClass}`} title={STATUS_LABEL[emp.status]} />}
          {avatarEditBtn}
        </div>
        <div className="mine__heroid">
          <h1>
            {emp.full_name}
            <span className={`mine__hero-badge ${statusBadgeClass}`}>
              {badgeTrangThai}
            </span>
          </h1>
          <p>
            {emp.department_name ?? "—"}
            {emp.position && emp.position !== emp.department_name ? ` · ${emp.position}` : ""}
            {bac && bac !== emp.position ? ` · ${bac}` : ""}
          </p>
          <p className="mine__herosub">
            Mã NV: {emp.code} · Vào làm {fmtDate(emp.hire_date)}{tn ? ` · Thâm niên ${tn}` : ""}
          </p>
          {emp.department_head_name && (
            <p className="mine__herosub">Trưởng bộ phận: {emp.department_head_name}</p>
          )}
        </div>
      </div>

      {/* Số liệu "của tôi" — kéo từ 3 màn nguồn về đây, bấm là sang đúng màn đó. */}
      <section className="mine__stats" aria-label="Số liệu của tôi">
        <StatChip
          nhan="Phép năm còn lại" icon="calendar" tt={phep}
          giaTri={(d) => ({ so: fmtSo(d.con_lai), donVi: "ngày" })}
          phu={(d) => `Đã dùng ${fmtSo(d.da_dung)}/${fmtSo(d.han_muc)} ngày${d.them > 0 ? ` · +${d.them} loại khác` : ""}`}
          tone={(d) => (d.con_lai >= 3 ? "ok" : d.con_lai >= 0.5 ? "warn" : "low")}
          doc={(d) => `Phép năm còn lại ${d.con_lai} ngày, đã dùng ${d.da_dung} trên ${d.han_muc}. Mở màn Nghỉ phép.`}
          onGo={() => navigate?.("nghi-phep")} onThuLai={napPhep} moTaGo="Mở màn Nghỉ phép"
        />
        <StatChip
          nhan={`Công tháng ${new Date().getMonth() + 1}`} icon="clock" tt={cong}
          giaTri={(d) => ({ so: fmtSo(d.cong), donVi: "công" })}
          phu={(d) => `${d.chuan != null ? `Chuẩn ${fmtSo(d.chuan)} công · ` : ""}${fmtSo(d.ngay)} ngày có mặt`}
          tone={() => "info"}
          doc={(d) => `Công tháng ${d.thang}: ${d.cong} công, ${d.ngay} ngày có mặt. Mở màn Chấm công.`}
          onGo={() => navigate?.("cham-cong")} onThuLai={() => napCong(emp.id)} moTaGo="Mở màn Chấm công"
        />
        <StatChip
          nhan="Phiếu lương gần nhất" icon="calculator" tt={luong}
          giaTri={(d) => ({ so: `${fmtSo(Math.round(d.dong.net_pay))} đ`, donVi: null, tien: true })}
          phu={(d) => `Kỳ ${d.ky.month}/${d.ky.year}${d.ky.paid_at ? "" : " · chưa chốt"}`}
          tone={() => "money"}
          doc={(d) => `Phiếu lương kỳ ${d.ky.month} năm ${d.ky.year}, thực nhận ${Math.round(d.dong.net_pay)} đồng. Mở màn Lương.`}
          onGo={() => navigate?.("luong")} onThuLai={napLuong} moTaGo="Mở màn Lương"
        />
        <StatChip
          nhan="Đề nghị chờ duyệt" icon="send"
          tt={reqs.tt === "ok" ? { tt: "ok", du: dsReq } : reqs.tt === "loi" ? { tt: "loi" } : DANG_TAI}
          giaTri={() => ({ so: fmtSo(choDuyet.length), donVi: "đề nghị" })}
          phu={() => (choDuyet.length > 0
            ? `Gửi gần nhất ${fmtDate(choDuyet[0].created_at)}`
            : "Không có đề nghị nào đang chờ")}
          tone={() => (choDuyet.length > 0 ? "warn" : "none")}
          doc={() => `${choDuyet.length} đề nghị đang chờ duyệt. Xem khối Đề nghị cập nhật.`}
          onGo={cuonToiReq} onThuLai={loadReqs} moTaGo="Xem khối Đề nghị cập nhật"
        />
      </section>

      {(thieu.tu.length > 0 || thieu.hcns.length > 0) && (() => {
        const totalFields = 15;
        const missingCount = thieu.tu.length + thieu.hcns.length;
        const pct = Math.max(0, Math.round(((totalFields - missingCount) / totalFields) * 100));
        return (
          <div className="mine__nudge">
            <div className="mine__nudge-left">
              <div className="mine__nudge-icon"><Icon name="shield" size={18} /></div>
              <div className="mine__nudge-text">
                <div className="mine__nudge-head">
                  <span className="mine__nudge-title">Hoàn thiện hồ sơ</span>
                  <span className="mine__nudge-badge">{pct}% đã hoàn thành</span>
                </div>
                <div className="mine__nudge-bar-wrap">
                  <div className="mine__nudge-bar-fill" style={{ width: `${pct}%` }} />
                </div>
                <span className="mine__nudge-sub">
                  Còn {missingCount} mục chưa khai
                  {thieu.tu.length > 0 ? ` (${thieu.tu.length} mục bạn tự sửa` : ""}
                  {thieu.hcns.length > 0 ? `${thieu.tu.length > 0 ? " · " : " ("}${thieu.hcns.length} mục do HCNS)` : ")"}
                </span>
              </div>
            </div>
            <div className="mine__nudge__acts">
              {thieu.tu.length > 0 && (
                <button type="button" className="mine__nudge-btn-main" onClick={() => setEditing(true)}>
                  Điền {thieu.tu.length} mục bạn tự sửa
                </button>
              )}
              {thieu.hcns.length > 0 && (
                <button type="button" className="mine__nudge-btn-sub" onClick={() => setRequesting(true)}>
                  Đề nghị HCNS bổ sung {thieu.hcns.length} mục
                </button>
              )}
            </div>
          </div>
        );
      })()}

      <div className="mine__cards">
        <div className="mine__card">
          <div className="mine__reqhead">
            <h4 className="ns-info-card__title mine__cardtitle">
              <span className="mine__card-icon"><Icon name="users" size={14} /></span>
              Thông tin liên hệ
              <span className="mine__ownchip">Bạn tự sửa</span>
            </h4>
            <button className="btn btn--ghost" onClick={() => setEditing(true)}>Sửa</button>
          </div>
          <Row k="SĐT" v={emp.phone} />
          <Row k="Email" v={emp.email} />
          <Row k="Chỗ ở hiện tại" v={emp.current_address} />
          <Row k="Liên hệ khẩn (tên)" v={emp.emergency_contact_name} />
          <Row k="Liên hệ khẩn (SĐT)" v={emp.emergency_contact_phone} />
        </div>

        <div className="mine__card">
          <h4 className="ns-info-card__title mine__cardtitle">
            <span className="mine__card-icon"><Icon name="fileCheck" size={14} /></span>
            Cá nhân
            <LockChip onClick={() => setRequesting(true)} />
          </h4>
          <Row k="Ngày sinh" v={emp.date_of_birth ? fmtDate(emp.date_of_birth) : null} />
          <Row k="Giới tính" v={emp.gender ? GENDER_LABEL[emp.gender] : null} />
          <Row k="CCCD" v={emp.national_id} />
          {/* Ngày/nơi cấp chỉ có nghĩa khi đã có số CCCD — chưa có số thì hai dòng này là nhiễu. */}
          {emp.national_id && <Row k="Ngày cấp CCCD" v={emp.national_id_date ? fmtDate(emp.national_id_date) : null} />}
          {emp.national_id && <Row k="Nơi cấp CCCD" v={emp.national_id_place} />}
          <Row k="Hộ khẩu" v={emp.permanent_address} />
        </div>

        <div className="mine__card">
          <h4 className="ns-info-card__title mine__cardtitle">
            <span className="mine__card-icon"><Icon name="calculator" size={14} /></span>
            Ngân hàng · Thuế · BHXH
            <LockChip onClick={() => setRequesting(true)} />
          </h4>
          <Row k="Số tài khoản" v={emp.bank_account} />
          <Row k="Ngân hàng" v={emp.bank_name} />
          <Row k="Số sổ BHXH" v={emp.social_insurance_no} />
          <Row k="MST cá nhân" v={emp.pit_tax_code} />
          {/* pit_mode = null nghĩa là BỊ CHE theo quyền, KHÔNG phải "chưa khai" → ẩn hẳn dòng,
              in "Chưa khai" ở đây là nói sai sự thật. */}
          {emp.pit_mode && <Row k="Cách tính thuế TNCN" v={PIT_MODE_LABEL[emp.pit_mode] ?? emp.pit_mode} />}
          <Row k="Người phụ thuộc" v={String(emp.dependents_count)} />
        </div>

        <div className="mine__card">
          <h4 className="ns-info-card__title mine__cardtitle">
            <span className="mine__card-icon"><Icon name="clipboard" size={14} /></span>
            Công việc
          </h4>
          <Row
            k="Ca mặc định"
            v={shift ? `${shift.name} (${shift.start_time}–${shift.end_time})` : null}
            hint="Ca do HCNS gán ở màn Chấm công"
          />
          <Row k="Bậc tay nghề" v={bac} />
          {emp.department_head_name && <Row k="Trưởng bộ phận" v={emp.department_head_name} />}
          {emp.status === "probation" && (
            <Row k="Hết thử việc" v={emp.probation_end_date ? fmtDate(emp.probation_end_date) : null} />
          )}
        </div>
      </div>

      {accountCard}

      <div
        className={`mine__card mine__wide${nhayReq ? " mine__flash" : ""}`}
        id="mine-requests"
        ref={reqRef}
      >
        <div className="mine__reqhead">
          <h4 className="ns-info-card__title mine__cardtitle">
            <span className="mine__card-icon"><Icon name="send" size={14} /></span>
            Đề nghị cập nhật hồ sơ
            {choDuyet.length > 0 && <span className="ns-badge ns-badge--warn">{choDuyet.length} chờ duyệt</span>}
          </h4>
          <button className="btn btn--ghost" onClick={() => setRequesting(true)}>+ Gửi đề nghị</button>
        </div>
        <p className="cc-note">Các mục như tên, CCCD, hộ khẩu, số tài khoản… bạn không sửa thẳng — gửi đề nghị để HCNS duyệt.</p>
        {reqs.tt !== "ok" ? (
          <EmptyState trangThai={reqs.tt === "loi" ? "loi" : "dang-tai"} inline onThuLai={loadReqs} />
        ) : dsReq.length === 0 ? (
          <EmptyState
            inline icon="send" title="Chưa gửi đề nghị nào."
            sub="Các mục do HCNS quản lý (tên, CCCD, hộ khẩu, số tài khoản…) sửa qua đề nghị."
          />
        ) : (
          <>
            <ul className="mine__reqlist">
              {sapXepReq(dsReq).slice(0, xemHetReq ? undefined : 5).map((r) => (
                <ReqItem key={r.id} req={r} emp={emp} onHuy={() => { setHuyErr(null); setHuyReq(r); }} />
              ))}
            </ul>
            {!xemHetReq && dsReq.length > 5 && (
              <button className="btn btn--ghost mine__reqmore" onClick={() => setXemHetReq(true)}>
                Xem thêm ({dsReq.length - 5})
              </button>
            )}
          </>
        )}
      </div>

      <div className="mine__card mine__wide">
        <h4 className="ns-info-card__title mine__cardtitle">
          <Icon name="fileText" size={14} /> Giấy tờ của tôi
        </h4>
        {files.tt !== "ok" ? (
          <EmptyState trangThai={files.tt === "loi" ? "loi" : "dang-tai"} inline onThuLai={load} />
        ) : files.du.length === 0 ? (
          <EmptyState
            inline icon="fileText" title="Chưa có giấy tờ nào."
            sub="Hợp đồng, CCCD, bằng cấp do HCNS tải lên hồ sơ của bạn."
          />
        ) : (
          <ul className="ns-filelist-v2">
            {files.du.map((a) => (
              <li key={a.id} className="ns-fileitem">
                <span className={`ns-fileitem__icon ns-fileitem__icon--${kieuFile(a.file_name)}`}>
                  <Icon name="fileText" size={16} />
                </span>
                <span className="ns-fileitem__main">
                  <span className="ns-fileitem__name-group">
                    <a className="ns-fileitem__name" href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">
                      {a.file_name}
                    </a>
                    <span className="ns-fileitem__badge">{DOC_KIND_LABEL[a.doc_kind] ?? a.doc_kind}</span>
                  </span>
                  <span className="ns-fileitem__sub">Tải lên {fmtDate(a.uploaded_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mine__card mine__wide">
        <h4 className="ns-info-card__title mine__cardtitle">
          <Icon name="activity" size={14} /> Quá trình công tác
        </h4>
        <Timeline items={tl} emptyText="Chưa có mốc quá trình công tác." />
      </div>

      {editing && <ContactModal token={token!} emp={emp} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />}
      {requesting && <RequestModal token={token!} emp={emp} onClose={() => setRequesting(false)} onSaved={() => { setRequesting(false); load(); }} />}
      <ConfirmDialog
        open={huyReq !== null}
        title="Hủy đề nghị này?"
        message="Đề nghị sẽ được rút lại, HCNS không xử lý nữa. Bạn có thể gửi lại bất cứ lúc nào."
        confirmLabel="Hủy đề nghị" cancelLabel="Giữ lại" danger
        busy={huyBusy} error={huyErr}
        onConfirm={xacNhanHuy} onCancel={() => { setHuyReq(null); setHuyErr(null); }}
      />
      {accountModals}
    </main>
  );
}

// --- helpers hiển thị --------------------------------------------------------

const REQ_FIELD_LABEL: Record<string, string> = {
  full_name: "Họ tên", date_of_birth: "Ngày sinh", national_id: "CCCD",
  national_id_date: "Ngày cấp CCCD", national_id_place: "Nơi cấp CCCD",
  permanent_address: "Hộ khẩu", bank_account: "Số tài khoản", bank_name: "Ngân hàng",
  dependents_count: "Người phụ thuộc",
};

/** Ô còn trống, TÁCH hai nhóm vì dẫn tới hai việc khác nhau: tự điền (modal liên hệ) vs
 *  gửi đề nghị cho HCNS. Cố ý KHÔNG đếm: `dependents_count` (0 là giá trị thật),
 *  `pit_mode` (null = bị che quyền), `probation_end_date` (chỉ có nghĩa khi thử việc). */
function oThieu(emp: EmployeeDetail | null): { tu: string[]; hcns: string[] } {
  if (!emp) return { tu: [], hcns: [] };
  const trong = (v: unknown) => v === null || v === undefined || v === "";
  const tu = ([
    ["phone", emp.phone], ["email", emp.email], ["current_address", emp.current_address],
    ["emergency_contact_name", emp.emergency_contact_name], ["emergency_contact_phone", emp.emergency_contact_phone],
  ] as const).filter(([, v]) => trong(v)).map(([k]) => k as string);
  const hcns = ([
    ["date_of_birth", emp.date_of_birth], ["gender", emp.gender], ["national_id", emp.national_id],
    ["national_id_date", emp.national_id_date], ["national_id_place", emp.national_id_place],
    ["permanent_address", emp.permanent_address], ["bank_account", emp.bank_account],
    ["bank_name", emp.bank_name], ["social_insurance_no", emp.social_insurance_no],
    ["pit_tax_code", emp.pit_tax_code],
  ] as const).filter(([, v]) => trong(v)).map(([k]) => k as string);
  return { tu, hcns };
}

/** Chờ duyệt lên đầu (việc còn treo), rồi mới tới đơn đã xong theo thời gian gửi giảm dần. */
function sapXepReq(items: UpdateRequest[]): UpdateRequest[] {
  return [...items].sort((a, b) => {
    const pa = a.status === "pending" ? 0 : 1, pb = b.status === "pending" ? 0 : 1;
    if (pa !== pb) return pa - pb;
    return (b.created_at ?? "").localeCompare(a.created_at ?? "");
  });
}

function kieuFile(name: string): "pdf" | "img" | "doc" {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  if (ext === "pdf") return "pdf";
  if (["jpg", "jpeg", "png", "gif", "webp", "heic"].includes(ext)) return "img";
  return "doc";
}

function Row({ k, v, rong = "Chưa khai", hint }: {
  k: string; v: string | null | undefined; rong?: string; hint?: string;
}) {
  const co = v !== null && v !== undefined && v !== "";
  return (
    <div className="ns-kv">
      <span className="ns-kv__k">{k}</span>
      <span className="ns-kv__v">
        <span className={co ? undefined : "mine__kv--empty"}>
          {!co && <Icon name="alert" size={11} />}
          {co ? v : rong}
        </span>
        {hint && <span className="mine__kv-hint">{hint}</span>}
      </span>
    </div>
  );
}

/** Chip khoá cạnh tiêu đề khối do HCNS quản — bấm là mở thẳng form đề nghị. Đặt ngay cạnh
 *  field bị khoá nên không cần thêm link "Cần đổi tên?" ở hero nữa. */
function LockChip({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button" className="mine__lockchip" onClick={onClick}
      title="Mục này do HCNS quản lý. Bấm để gửi đề nghị sửa."
      aria-label="Mục này do HCNS quản lý. Bấm để gửi đề nghị sửa."
    >
      <Icon name="lock" size={11} /> HCNS quản lý
    </button>
  );
}

type ChipTone = "ok" | "warn" | "low" | "info" | "money" | "none";

/** Một ô số liệu "của tôi". Cả thẻ là MỘT nút — ca lỗi đổi vai thành "thử lại" chứ không nhét
 *  nút con vào trong nút (HTML không hợp lệ). */
function StatChip<T>({ nhan, icon, tt, giaTri, phu, tone, doc, onGo, onThuLai, moTaGo }: {
  nhan: string;
  icon: IconName;
  tt: Tai<T>;
  giaTri: (d: T) => { so: string; donVi: string | null; tien?: boolean };
  phu: (d: T) => string;
  tone: (d: T) => ChipTone;
  doc: (d: T) => string;
  onGo: () => void;
  onThuLai: () => void;
  moTaGo: string;
}) {
  const nhanEl = (
    <span className="mine__stat-label">
      <span className="mine__stat-icon-wrap"><Icon name={icon} size={13} /></span>
      {nhan}
    </span>
  );

  if (tt.tt === "dang-tai") {
    return (
      <div className="mine__stat mine__stat--none" aria-busy="true">
        {nhanEl}
        <span className="mine__skel mine__skel--val" />
        <span className="mine__skel mine__skel--sub" />
      </div>
    );
  }
  if (tt.tt === "loi") {
    return (
      <button type="button" className="mine__stat mine__stat--low" onClick={onThuLai}
              aria-label={`${nhan}: không tải được. Bấm để thử lại.`}>
        {nhanEl}
        <span className="mine__stat-val mine__stat-val--none">–</span>
        <span className="mine__stat-sub mine__stat-sub--err">Không tải được. Bấm để thử lại.</span>
      </button>
    );
  }
  if (tt.tt === "rong") {
    return (
      <button type="button" className="mine__stat mine__stat--none" onClick={onGo}
              aria-label={`${nhan}: chưa có số liệu. ${moTaGo}.`}>
        {nhanEl}
        <span className="mine__stat-val mine__stat-val--none">–</span>
        <span className="mine__stat-sub">{tt.vi_sao}</span>
        <Icon name="arrowRight" size={14} className="mine__stat-go" />
      </button>
    );
  }
  const { so, donVi, tien } = giaTri(tt.du);
  return (
    <button type="button" className={`mine__stat mine__stat--${tone(tt.du)}`} onClick={onGo}
            aria-label={doc(tt.du)}>
      {nhanEl}
      <span className={`mine__stat-val${tien ? " mine__stat-val--money" : ""}`}>
        {so}{donVi && <span className="mine__stat-unit">{donVi}</span>}
      </span>
      <span className="mine__stat-sub">{phu(tt.du)}</span>
      <Icon name="arrowRight" size={14} className="mine__stat-go" />
    </button>
  );
}

/** Một đề nghị + VẾT xử lý. Mũi tên "cũ → mới" chỉ vẽ khi còn `pending`: khi đã duyệt, hồ sơ
 *  đã mang giá trị mới nên hai vế trùng nhau — vẽ mũi tên lúc đó là bịa dữ liệu. */
function ReqItem({ req, emp, onHuy }: { req: UpdateRequest; emp: EmployeeDetail; onHuy: () => void }) {
  const cho = req.status === "pending";
  const cls = req.status === "approved" ? "is-approved"
    : req.status === "rejected" ? "is-rejected"
    : req.status === "cancelled" ? "is-cancelled" : "is-pending";
  const badgeCls = req.status === "approved" ? "ns-badge--ok"
    : req.status === "rejected" ? "ns-badge--danger"
    : req.status === "cancelled" ? "ns-badge--muted" : "ns-badge--warn";
  return (
    <li className={`mine__reqitem ${cls}`}>
      <div className="mine__reqitem__head">
        <span className={`ns-badge ${badgeCls}`}>{REQ_STATUS_LABEL[req.status] ?? req.status}</span>
        <span className="mine__reqdate">Gửi {fmtDateTime(req.created_at)}</span>
      </div>
      <div className="mine__reqchange">
        {Object.entries(req.changes).map(([k, v]) => (
          <div className="mine__reqchange__row" key={k}>
            <span className="mine__reqchange__k">{REQ_FIELD_LABEL[k] ?? k}</span>
            <span className="mine__reqchange__v">
              {cho && <><span className="mine__reqchange__old">{giaTriCu(emp, k) || "(chưa có)"}</span> → </>}
              <strong>{v === null || v === "" ? "(bỏ trống)" : String(v)}</strong>
            </span>
          </div>
        ))}
        {req.reason && (
          <div className="mine__reqchange__row">
            <span className="mine__reqchange__k">Lý do</span>
            <span className="mine__reqchange__v">{req.reason}</span>
          </div>
        )}
      </div>
      {req.status === "rejected" && (
        <p className="mine__reqreject">
          <Icon name="alert" size={14} />
          {req.decision_note || "HCNS không ghi lý do. Liên hệ HCNS để biết thêm."}
        </p>
      )}
      {(req.decided_at || cho) && (
        <div className="mine__reqtrace">
          {cho ? (
            <button className="btn btn--ghost mine__reqcancel" onClick={onHuy}>
              <Icon name="x" size={13} /> Hủy đề nghị
            </button>
          ) : (
            <span>
              {req.status === "cancelled" ? "Bạn rút lại" : `Quyết bởi ${req.decided_by_name ?? "HCNS"}`}
              {req.decided_at ? ` · ${fmtDateTime(req.decided_at)}` : ""}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

/** Giá trị ĐANG có trên hồ sơ của một field trong `changes` — để so "cũ → mới". */
function giaTriCu(emp: EmployeeDetail, field: string): string {
  const v = (emp as unknown as Record<string, unknown>)[field];
  if (v === null || v === undefined || v === "") return "";
  if (field === "date_of_birth" || field === "national_id_date") return fmtDate(String(v));
  return String(v);
}

function ContactModal({ token, emp, onClose, onSaved }: {
  token: string; emp: EmployeeDetail; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<MyContactInput>({
    phone: emp.phone ?? "", email: emp.email ?? "", current_address: emp.current_address ?? "",
    emergency_contact_name: emp.emergency_contact_name ?? "", emergency_contact_phone: emp.emergency_contact_phone ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  function set<K extends keyof MyContactInput>(k: K, v: MyContactInput[K]) { setForm((f) => ({ ...f, [k]: v })); }
  async function save() {
    setBusy(true); setErr(null);
    try { await api.employees.updateMe(token, form); onSaved(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi lưu."); setBusy(false); }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-contact-title">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2 id="mine-contact-title">
            <span className="mine__modal-title-icon"><Icon name="users" size={15} /></span>
            Cập nhật thông tin liên hệ
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="mine__modal-notice">
            <span className="mine__modal-notice-icon"><Icon name="alert" size={14} /></span>
            <span>Bạn chỉ sửa được thông tin liên lạc. Các thông tin định danh, chức danh, lương &amp; BHXH do phòng HCNS quản lý.</span>
          </div>
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">SĐT cá nhân</span>
              <div className="mine__input-wrap">
                <Icon name="phone" size={15} className="mine__input-icon" />
                <input className="mine__input-num" value={form.phone ?? ""} placeholder="090x xxx xxx" onChange={(e) => set("phone", e.target.value)} />
              </div>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Email</span>
              <div className="mine__input-wrap">
                <Icon name="mail" size={15} className="mine__input-icon" />
                <input type="email" value={form.email ?? ""} placeholder="email@example.com" onChange={(e) => set("email", e.target.value)} />
              </div>
            </label>
            <label className="ns-field" style={{ gridColumn: "1 / -1" }}>
              <span className="ns-field__label">Chỗ ở hiện tại</span>
              <div className="mine__input-wrap">
                <Icon name="mapPin" size={15} className="mine__input-icon" />
                <input value={form.current_address ?? ""} placeholder="Nhập địa chỉ chỗ ở hiện tại..." onChange={(e) => set("current_address", e.target.value)} />
              </div>
            </label>

            <div className="mine__modal-emergency-box">
              <div className="mine__modal-section-title">
                <Icon name="users" size={14} /> Liên hệ khẩn cấp
              </div>
              <div className="ns-grid" style={{ gap: "12px", width: "100%" }}>
                <label className="ns-field">
                  <span className="ns-field__label">Họ tên người liên hệ</span>
                  <div className="mine__input-wrap">
                    <Icon name="users" size={15} className="mine__input-icon" />
                    <input value={form.emergency_contact_name ?? ""} placeholder="Họ và tên người thân" onChange={(e) => set("emergency_contact_name", e.target.value)} />
                  </div>
                </label>
                <label className="ns-field">
                  <span className="ns-field__label">SĐT người liên hệ</span>
                  <div className="mine__input-wrap">
                    <Icon name="phone" size={15} className="mine__input-icon" />
                    <input className="mine__input-num" value={form.emergency_contact_phone ?? ""} placeholder="090x xxx xxx" onChange={(e) => set("emergency_contact_phone", e.target.value)} />
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto", display: "flex", gap: "10px", alignItems: "center" }}>
            <button type="button" className="mine__btn-cancel" onClick={onClose} disabled={busy}>Đóng</button>
            <button type="button" className="mine__btn-primary" onClick={save} disabled={busy}>
              {busy ? "Đang lưu…" : "Lưu thay đổi"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

// Đề nghị sửa field bảo vệ → HCNS duyệt. Chỉ gửi field ĐÃ ĐỔI so với hiện tại.
function RequestModal({ token, emp, onClose, onSaved }: {
  token: string; emp: EmployeeDetail; onClose: () => void; onSaved: () => void;
}) {
  const orig: Record<string, string> = {
    full_name: emp.full_name ?? "", date_of_birth: emp.date_of_birth ?? "", national_id: emp.national_id ?? "",
    national_id_date: emp.national_id_date ?? "", national_id_place: emp.national_id_place ?? "",
    permanent_address: emp.permanent_address ?? "", bank_account: emp.bank_account ?? "",
    bank_name: emp.bank_name ?? "", dependents_count: String(emp.dependents_count ?? 0),
  };
  const [form, setForm] = useState<Record<string, string>>({ ...orig });
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    const changes: UpdateRequestInput["changes"] = {};
    for (const k of Object.keys(orig)) {
      if (form[k] !== orig[k]) changes[k] = k === "dependents_count" ? Number(form[k]) : form[k];
    }
    if (Object.keys(changes).length === 0) { setErr("Bạn chưa thay đổi mục nào."); return; }
    setBusy(true); setErr(null);
    try { await api.employees.createMyRequest(token, { changes, reason: reason || null }); onSaved(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Lỗi khi gửi."); setBusy(false); }
  }
  const F = (label: string, k: string, type = "text", placeholder = "", className = "") => (
    <label className="ns-field"><span className="ns-field__label">{label}</span>
      <input type={type} className={className} placeholder={placeholder} value={form[k]} onChange={(e) => set(k, e.target.value)} /></label>
  );
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-req-title">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2 id="mine-req-title">
            <span className="mine__modal-title-icon"><Icon name="fileText" size={15} /></span>
            Đề nghị cập nhật hồ sơ
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="mine__modal-notice">
            <span className="mine__modal-notice-icon"><Icon name="alert" size={14} /></span>
            <span>Sửa các mục cần đổi rồi gửi. Phòng HCNS duyệt xong mới áp dụng vào hồ sơ. Chỉ gửi các mục bạn thay đổi.</span>
          </div>
          <div className="ns-grid">
            {F("Họ tên", "full_name", "text", "Nhập họ và tên đầy đủ")}
            {F("Ngày sinh", "date_of_birth", "date")}
            {F("CCCD", "national_id", "text", "Nhập số CCCD/CMND", "mine__input-num")}
            {F("Ngày cấp CCCD", "national_id_date", "date")}
            {F("Nơi cấp CCCD", "national_id_place", "text", "Công an Tỉnh/Thành phố...")}
            {F("Hộ khẩu", "permanent_address", "text", "Địa chỉ hộ khẩu thường trú")}
            {F("Số tài khoản", "bank_account", "text", "Nhập số tài khoản ngân hàng", "mine__input-num")}
            {F("Ngân hàng", "bank_name", "text", "Tên ngân hàng (VD: Vietcombank)")}
            {F("Người phụ thuộc", "dependents_count", "number", "0", "mine__input-num")}
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do đề nghị cập nhật</span>
            <input value={reason} placeholder="Ghi rõ lý do thay đổi thông tin (không bắt buộc)..." onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto", display: "flex", gap: "10px", alignItems: "center" }}>
            <button type="button" className="mine__btn-cancel" onClick={onClose} disabled={busy}>Đóng</button>
            <button type="button" className="mine__btn-primary" onClick={save} disabled={busy}>{busy ? "Đang gửi…" : "Gửi đề nghị"}</button>
          </div>
        </footer>
      </div>
    </div>
  );
}

// === Self-service tài khoản (gộp từ ProfileDialog) — vỏ ns-modal, không dùng vỏ pd-* ===

const AVATAR_MAX_BYTES = 2 * 1024 * 1024;
const AVATAR_TYPES = ["image/jpeg", "image/png"];

// Đổi ảnh đại diện. Nhân viên & admin đều dùng; BE tự ghi vào ảnh hồ sơ nếu có hồ sơ.
// Sau lưu/xóa: updateUser (topbar đọc user.avatar_url) + onSaved→load (hero đọc emp.photo_url) — CẬP NHẬT KÉP.
function AvatarModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { token, user, updateUser } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Revoke object URL khi preview đổi / unmount.
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const currentSrc = assetUrl(user?.avatar_url);
  const shownSrc = previewUrl ?? currentSrc;
  const initials = (user?.name?.trim() || user?.username || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");

  function pick(e: ChangeEvent<HTMLInputElement>) {
    setFormError(null);
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    if (!AVATAR_TYPES.includes(f.type)) { setFieldError("Ảnh phải là JPG hoặc PNG."); setFile(null); return; }
    if (f.size > AVATAR_MAX_BYTES) { setFieldError("Ảnh vượt quá 2 MB."); setFile(null); return; }
    setFieldError(null);
    setFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(f));
  }

  async function save() {
    if (!file || busy) return;
    setBusy(true); setFormError(null);
    try {
      const { avatar_url } = await api.uploadAvatar(token!, file);
      updateUser({ avatar_url });
      onSaved();
    } catch (err) { setFormError(messageFor(err)); setBusy(false); }
  }

  async function remove() {
    if (busy) return;
    setBusy(true); setFormError(null);
    try {
      await api.removeAvatar(token!);
      updateUser({ avatar_url: null });
      onSaved();
    } catch (err) { setFormError(messageFor(err)); setBusy(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-avatar-title">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2 id="mine-avatar-title">
            <span className="mine__modal-title-icon"><Icon name="pencil" size={15} /></span>
            Đổi ảnh đại diện
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="mine__avatar-modal">
            <div className="ns-avatar ns-avatar--xl">{shownSrc ? <img src={shownSrc} alt="" /> : initials}</div>
            <div className="mine__avatar-modal__controls">
              <input ref={inputRef} type="file" accept="image/jpeg,image/png" className="mine__vh" onChange={pick} disabled={busy} />
              <Button type="button" variant="ghost" onClick={() => inputRef.current?.click()} disabled={busy}>Chọn ảnh…</Button>
              <p className="mine__hint">JPG hoặc PNG, tối đa 2 MB.</p>
              {fieldError && <span className="field__error" role="alert">{fieldError}</span>}
            </div>
          </div>
        </div>
        <footer className="ns-modal__foot">
          {currentSrc
            ? <Button type="button" variant="ghost" onClick={remove} disabled={busy}>Xóa ảnh</Button>
            : <span />}
          <div className="ns-modal__footright" style={{ marginLeft: "auto" }}>
            <Button type="button" variant="primary" onClick={save} loading={busy} disabled={!file}>Lưu</Button>
          </div>
        </footer>
      </div>
    </div>
  );
}

interface PwErrors { current?: string; next?: string; confirm?: string; }

// Đổi mật khẩu. Thành công (204) → báo + logout về Login. 400 (sai mật khẩu cũ) → lỗi inline, giữ form.
function PasswordModal({ onClose }: { onClose: () => void }) {
  const { token, logout, setNotice } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<PwErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function validate(): PwErrors {
    const e: PwErrors = {};
    if (!current) e.current = "Vui lòng nhập mật khẩu hiện tại.";
    if (next.length < 8) e.next = "Mật khẩu mới tối thiểu 8 ký tự.";
    else if (!/[a-zA-Z]/.test(next) || !/\d/.test(next)) e.next = "Mật khẩu mới phải gồm cả chữ và số.";
    if (confirm !== next) e.confirm = "Xác nhận mật khẩu không khớp.";
    return e;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setFormError(null);
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setSaving(true);
    try {
      await api.changePassword(token!, current, next);
      setNotice("Đổi mật khẩu thành công. Vui lòng đăng nhập lại.");
      await logout();
    } catch (err) { setFormError(messageFor(err)); setSaving(false); }
  }

  const inputType = show ? "text" : "password";
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-pw-title">
      <form className="ns-modal__box" onSubmit={onSubmit} noValidate>
        <header className="ns-modal__head">
          <h2 id="mine-pw-title">
            <span className="mine__modal-title-icon"><Icon name="shield" size={15} /></span>
            Đổi mật khẩu
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="mine__form">
            <Field label="Mật khẩu hiện tại" type={inputType} autoComplete="current-password" value={current} error={errors.current} onChange={(e) => setCurrent(e.target.value)} disabled={saving} />
            <Field label="Mật khẩu mới" type={inputType} autoComplete="new-password" value={next} error={errors.next} onChange={(e) => setNext(e.target.value)} disabled={saving} />
            <Field label="Xác nhận mật khẩu mới" type={inputType} autoComplete="new-password" value={confirm} error={errors.confirm} onChange={(e) => setConfirm(e.target.value)} disabled={saving} />
            <label className="mine__pw-show"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Hiện mật khẩu</label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto" }}>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu mật khẩu</Button>
          </div>
        </footer>
      </form>
    </div>
  );
}

// Đổi tên hiển thị — chỉ cho tài khoản CHƯA gắn hồ sơ (BE trả 400 nếu tài khoản có hồ sơ: tên do HCNS/hồ sơ quyết).
function NameModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { token, user, updateUser } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    setFormError(null);
    const trimmed = name.trim();
    if (!trimmed) { setFieldError("Tên hiển thị không được để trống."); return; }
    if (trimmed.length > 100) { setFieldError("Tên hiển thị tối đa 100 ký tự."); return; }
    setFieldError(null);
    setSaving(true);
    try {
      const updated = await api.updateName(token!, trimmed);
      updateUser({ name: updated.name });
      onSaved();
    } catch (err) { setFormError(messageFor(err)); setSaving(false); }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="mine-name-title">
      <form className="ns-modal__box" onSubmit={onSubmit} noValidate>
        <header className="ns-modal__head">
          <h2 id="mine-name-title">
            <span className="mine__modal-title-icon"><Icon name="users" size={15} /></span>
            Đổi tên hiển thị
          </h2>
          <button type="button" className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="ns-modal__body">
          {formError && <div className="banner banner--error" role="alert">{formError}</div>}
          <div className="mine__form">
            <Field label="Tên hiển thị" value={name} error={fieldError ?? undefined} maxLength={120} autoFocus onChange={(e) => setName(e.target.value)} disabled={saving} />
          </div>
        </div>
        <footer className="ns-modal__foot">
          <div className="ns-modal__footright" style={{ marginLeft: "auto" }}>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Hủy</Button>
            <Button type="submit" variant="primary" loading={saving}>Lưu</Button>
          </div>
        </footer>
      </form>
    </div>
  );
}

function messageFor(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return "Mất kết nối. Vui lòng thử lại.";
    if (err.status >= 500) return "Có lỗi xảy ra, vui lòng thử lại sau.";
    return err.message; // surfaces the backend's Vietnamese detail (400/422)
  }
  return "Đã có lỗi xảy ra. Vui lòng thử lại.";
}
