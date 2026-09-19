// Danh mục "Tiêu chí KCS" — KHAI THEO CÂY, không phải bảng phẳng (08/09/2026, chủ chốt chốt:
// "chọn giai đoạn → chọn công đoạn → thêm hạng mục kiểm cho công đoạn, HẾT").
//
// Vì sao KHÔNG dùng nền `RebuildCatalogPage` như 12 màn danh mục kia: nền đó bày MỘT bảng phẳng,
// mỗi dòng một bản ghi. Ở đây đơn vị người dùng nghĩ tới là CÔNG ĐOẠN (một dòng của tờ ISO
// 9001-2015 treo ở xưởng), còn hạng mục kiểm là các gạch đầu dòng bên dưới nó — bày phẳng thì
// người khai phải tự nhớ mình đang khai cho công đoạn nào ở từng dòng.
//
// Ba tầng: Giai đoạn (`cong_doan.nhom`, 4 mã cố định) → Công đoạn → hạng mục kiểm.
// GIAI ĐOẠN KHÔNG phải bản ghi: nó là thuộc tính sẵn có của công đoạn, ở đây chỉ dùng để GOM
// nhóm khi đọc và để LỌC ô chọn khi thêm. Thêm "công đoạn cần kiểm" = khai hạng mục đầu tiên
// cho nó; xoá hạng mục cuối cùng thì công đoạn tự rời khỏi danh sách.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, api,
  type KcsCongDoanChon, type KcsHangMuc, type KcsKhaiBaoGiaiDoan,
} from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { NHOM_CONG_DOAN } from "../keHoachSxShared";
import "../rebuild-catalog.css";
import "./kcs-khai-bao.css";

const MODULE = "dm_kcs_tieu_chi";

function formatTenCongDoan(s: string): string {
  if (!s) return "";
  const trimmed = s.trim();
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

// --- Inline SVG Icons --------------------------------------------------------
function IconSearch() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function IconPlus() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function IconEdit() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function IconTrash() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function IconInfo() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function StageIcon({ nhom }: { nhom: string }) {
  if (nhom === "prepress") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <circle cx="12" cy="8" r="2" />
        <circle cx="8" cy="14" r="2" />
        <circle cx="16" cy="14" r="2" />
      </svg>
    );
  }
  if (nhom === "print") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="6 9 6 2 18 2 18 9" />
        <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
        <rect x="6" y="14" width="12" height="8" />
      </svg>
    );
  }
  if (nhom === "finishing") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="3" />
        <circle cx="6" cy="18" r="3" />
        <line x1="20" y1="4" x2="8.12" y2="15.88" />
        <line x1="14.47" y1="14.47" x2="20" y2="20" />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    </svg>
  );
}

// --- Xếp gạch -----------------------------------------------------------------
// Thẻ cao thấp khác nhau theo số hạng mục; lưới hàng-cột để lại khoảng hổng dưới thẻ ngắn ở từng
// hàng. Ở đây thẻ kế tiếp luôn vào cột ĐANG THẤP HƠN ⇒ đỉnh thẻ sau không bao giờ cao hơn thẻ trước,
// đọc từ trên xuống vẫn đúng thứ tự. Chiều cao ƯỚC từ dữ liệu, không đo DOM: mở form trong thẻ làm
// thẻ cao lên nhưng không nhảy cột giữa lúc gõ. Ước lệch (tên dài xuống dòng) chỉ làm chia cột kém
// tối ưu chút — đáy hai cột vẫn bằng nhau nhờ CSS cho thẻ cuối mỗi cột giãn (`.kkb-cot`).
type TheCongDoan = { gdNhom: string; cd: KcsKhaiBaoGiaiDoan["cong_doan"][number] };

const THE_RONG_TOI_THIEU = 540;
const KHE_LUOI = 16;
// Đo trên màn 17/09/2026: đầu thẻ 55px (gồm vạch màu 4px), dòng hạng mục 60px, thêm 25px nếu có hướng dẫn.
const CAO_DAU_THE = 55;
const CAO_DONG = 60;
const CAO_HUONG_DAN = 25;

function uocCaoThe({ cd }: TheCongDoan): number {
  return cd.hang_muc.reduce(
    (tong, h) => tong + CAO_DONG + (h.huong_dan ? CAO_HUONG_DAN : 0),
    CAO_DAU_THE,
  );
}

function chiaCot(dsThe: TheCongDoan[], soCot: number): TheCongDoan[][] {
  const cot: TheCongDoan[][] = Array.from({ length: soCot }, () => []);
  const cao = new Array<number>(soCot).fill(0);
  for (const the of dsThe) {
    let thapNhat = 0;
    for (let i = 1; i < soCot; i++) if (cao[i] < cao[thapNhat]) thapNhat = i;
    cot[thapNhat].push(the);
    cao[thapNhat] += uocCaoThe(the) + KHE_LUOI;
  }
  return cot;
}

interface FormState {
  id: number | null;
  cong_doan_id: number;
  ten: string;
  huong_dan: string;
  thu_tu: number;
  // Màn không có ô cho hai cờ này nhưng PUT ghi đè cả bản ghi — sửa câu chữ phải GIỮ nguyên cờ
  // đang có, đừng gán cứng `true` (sửa dòng "ngừng dùng" sẽ lặng lẽ bật nó lại).
  bat_buoc: boolean;
  active: boolean;
}

function formRong(cong_doan_id: number, thu_tu: number): FormState {
  return { id: null, cong_doan_id, ten: "", huong_dan: "", thu_tu, bat_buoc: true, active: true };
}

export function KcsKhaiBaoPage() {
  const { token } = useAuth();
  const can = useCan();
  const suaDuoc = can(MODULE, "update");
  const xoaDuoc = can(MODULE, "delete");

  const [giaiDoan, setGiaiDoan] = useState<KcsKhaiBaoGiaiDoan[] | null>(null);
  const [congDoanOpts, setCongDoanOpts] = useState<KcsCongDoanChon[]>([]);
  const [loi, setLoi] = useState<string | null>(null);
  const [tuKhoa, setTuKhoa] = useState("");
  const [tabGiaiDoan, setTabGiaiDoan] = useState<string>("all");
  const [moThemCongDoan, setMoThemCongDoan] = useState(false);

  const [form, setForm] = useState<FormState | null>(null);
  const [dangLuu, setDangLuu] = useState(false);

  const [themNhom, setThemNhom] = useState<string>("");
  const [themCongDoanId, setThemCongDoanId] = useState<number | "">("");

  // MỘT cửa cho cả cây lẫn ô chọn công đoạn — đừng gọi thêm `api.congDoan.list`: dòng đầy đủ
  // nặng gấp ~6 lần cả cây, lại đòi quyền Công đoạn/Tính giá nên người chỉ có quyền KCS bị 403.
  const tai = useCallback(() => {
    if (!token) return;
    setLoi(null);
    api.kcsHangMuc.khaiBao(token)
      .then((kb) => {
        setGiaiDoan(kb.giai_doan);
        setCongDoanOpts(kb.cong_doan_chon);
      })
      .catch((e) => {
        setGiaiDoan([]);
        setLoi(e instanceof ApiError ? e.message : "Không tải được danh mục.");
      });
  }, [token]);

  useEffect(() => { tai(); }, [tai]);

  const daKhai = useMemo(
    () => new Set((giaiDoan ?? []).flatMap((g) => g.cong_doan.map((c) => c.cong_doan_id))),
    [giaiDoan],
  );

  // Server đã bỏ công đoạn ngừng dùng / đã khai và xếp theo mã — ở đây chỉ lọc giai đoạn.
  const congDoanChonDuoc = useMemo(
    () => congDoanOpts.filter((c) => c.nhom === themNhom),
    [congDoanOpts, themNhom],
  );

  // Thống kê tổng số công đoạn & số hạng mục + Đếm theo nhóm
  const { soCongDoan, soHangMuc, demCongDoanTheoNhom } = useMemo(() => {
    if (!giaiDoan) return { soCongDoan: 0, soHangMuc: 0, demCongDoanTheoNhom: {} as Record<string, number> };
    let cdCount = 0;
    let hmCount = 0;
    const demNhom: Record<string, number> = {};
    for (const g of giaiDoan) {
      const n = g.cong_doan.length;
      cdCount += n;
      demNhom[g.nhom || "other"] = n;
      for (const c of g.cong_doan) {
        hmCount += c.hang_muc.length;
      }
    }
    return { soCongDoan: cdCount, soHangMuc: hmCount, demCongDoanTheoNhom: demNhom };
  }, [giaiDoan]);

  // Lọc theo từ khóa tìm kiếm & Tab giai đoạn
  const danhSachCongDoanHienThi = useMemo(() => {
    if (!giaiDoan) return [];
    const q = tuKhoa.trim().toLowerCase();

    const result: TheCongDoan[] = [];

    for (const gd of giaiDoan) {
      const nhomMa = gd.nhom || "other";
      if (tabGiaiDoan !== "all" && tabGiaiDoan !== nhomMa) continue;

      for (const cd of gd.cong_doan) {
        if (q) {
          const cdKhop = cd.ten.toLowerCase().includes(q) || cd.ma.toLowerCase().includes(q);
          const hmKhop = cd.hang_muc.some(
            (h) => h.ten.toLowerCase().includes(q) || (h.huong_dan && h.huong_dan.toLowerCase().includes(q)),
          );
          if (!cdKhop && !hmKhop) continue;
        }
        result.push({ gdNhom: nhomMa, cd });
      }
    }

    return result;
  }, [giaiDoan, tuKhoa, tabGiaiDoan]);

  // Số cột theo bề ngang KHUNG LƯỚI (không theo cửa sổ: sidebar ăn bớt chỗ). Ref dạng callback vì
  // lưới chỉ mount khi đã có dữ liệu; đo ngay lúc gắn để lần vẽ đầu đã đúng số cột.
  const [soCot, setSoCot] = useState(1);
  const roLuoi = useRef<ResizeObserver | null>(null);
  const ganLuoi = useCallback((el: HTMLDivElement | null) => {
    roLuoi.current?.disconnect();
    roLuoi.current = null;
    if (!el) return;
    const doLai = () => setSoCot(
      Math.max(1, Math.floor((el.clientWidth + KHE_LUOI) / (THE_RONG_TOI_THIEU + KHE_LUOI))),
    );
    doLai();
    if (typeof ResizeObserver === "undefined") return;
    roLuoi.current = new ResizeObserver(doLai);
    roLuoi.current.observe(el);
  }, []);

  const cotThe = useMemo(() => chiaCot(danhSachCongDoanHienThi, soCot), [danhSachCongDoanHienThi, soCot]);

  async function luu() {
    if (!token || !form) return;
    const ten = form.ten.trim();
    if (!ten) { setLoi("Nhập câu chữ hạng mục kiểm."); return; }
    setDangLuu(true);
    setLoi(null);
    try {
      const body = {
        cong_doan_id: form.cong_doan_id,
        ten,
        huong_dan: form.huong_dan.trim() || null,
        bat_buoc: form.bat_buoc,
        thu_tu: form.thu_tu,
        active: form.active,
      };
      if (form.id == null) await api.kcsHangMuc.tao(token, body);
      else await api.kcsHangMuc.sua(token, form.id, body);
      setForm(null);
      setThemCongDoanId("");
      tai();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không lưu được hạng mục kiểm.");
    } finally {
      setDangLuu(false);
    }
  }

  async function xoa(h: KcsHangMuc) {
    if (!token) return;
    if (!window.confirm(`Xoá hạng mục “${h.ten}”?`)) return;
    setLoi(null);
    try {
      await api.kcsHangMuc.xoa(token, h.id);
      tai();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xoá được hạng mục kiểm.");
    }
  }

  function formHangMuc() {
    if (!form) return null;
    return (
      <div className="kkb-form">
        <div className="kkb-form__title">
          {form.id == null ? "Thêm hạng mục mới" : "Chỉnh sửa hạng mục"}
        </div>
        <div className="kkb-form__fields">
          <label className="kkb-form__ten">
            <span>Hạng mục kiểm *</span>
            <input
              type="text" className="rc-input" autoFocus value={form.ten}
              placeholder="vd: Chồng màu đúng mẫu đã ký"
              onChange={(e) => setForm({ ...form, ten: e.target.value })}
            />
          </label>
          <label className="kkb-form__hd">
            <span>Hướng dẫn kiểm</span>
            <input
              type="text" className="rc-input" value={form.huong_dan}
              placeholder="vd: Soi dưới đèn D50..."
              onChange={(e) => setForm({ ...form, huong_dan: e.target.value })}
            />
          </label>
          <div className="kkb-form__nut">
            <button type="button" className="kkb-btn" onClick={() => setForm(null)}>Huỷ</button>
            <button type="button" className="kkb-btn kkb-btn--chinh" onClick={luu} disabled={dangLuu}>
              {dangLuu ? "Đang lưu…" : form.id == null ? "Thêm hạng mục" : "Lưu"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <main className="rc kkb kkb--compact">
      {/* --- TOPBAR 2 TẦNG CHUYÊN NGHIỆP UI/UX --- */}
      <header className="kkb-topbar">
        {/* Tầng 1: Page Header & Primary Action CTA */}
        <div className="kkb-topbar__header">
          <div className="kkb-topbar__left">
            <h1 className="kkb-topbar__title">Thiết lập Tiêu chí</h1>
            <span className="kkb-topbar__count">{soCongDoan} CĐ · {soHangMuc} Tiêu chí</span>
          </div>

          {suaDuoc && (
            <button
              type="button"
              className={`btn ${moThemCongDoan ? "btn--ghost" : "btn--accent"} kkb-topbar__add-btn`}
              onClick={() => setMoThemCongDoan(!moThemCongDoan)}
            >
              <IconPlus /> {moThemCongDoan ? "Đóng" : "Thêm Tiêu chí"}
            </button>
          )}
        </div>

        {/* Tầng 2: Toolbar Bộ lọc Giai đoạn & Tìm kiếm */}
        <div className="kkb-topbar__toolbar">
          <nav className="kkb-tabs">
            <button
              type="button"
              className={`kkb-tab ${tabGiaiDoan === "all" ? "kkb-tab--active" : ""}`}
              onClick={() => setTabGiaiDoan("all")}
            >
              <span>Tất cả ({soCongDoan})</span>
            </button>
            {Object.entries(NHOM_CONG_DOAN).map(([ma, nhan]) => {
              const cnt = demCongDoanTheoNhom[ma] || 0;
              return (
                <button
                  key={ma}
                  type="button"
                  className={`kkb-tab kkb-tab--${ma} ${tabGiaiDoan === ma ? "kkb-tab--active" : ""}`}
                  onClick={() => setTabGiaiDoan(ma)}
                >
                  <StageIcon nhom={ma} />
                  <span>{nhan} ({cnt})</span>
                </button>
              );
            })}
          </nav>

          <div className="kkb-searchbox">
            <IconSearch />
            <input
              type="text"
              className="kkb-searchbox__input"
              placeholder="Tìm tiêu chí KCS, mã CĐ..."
              value={tuKhoa}
              onChange={(e) => setTuKhoa(e.target.value)}
            />
            {tuKhoa && (
              <button
                type="button"
                className="kkb-searchbox__clear"
                onClick={() => setTuKhoa("")}
                title="Xoá tìm kiếm"
              >
                ×
              </button>
            )}
          </div>
        </div>
      </header>

      {loi && (
        <div className="banner banner--error" role="alert">
          <span>{loi}</span>
        </div>
      )}

      {/* --- KHỐI THÊM CÔNG ĐOẠN (COLLAPSIBLE TOOLBAR) --- */}
      {suaDuoc && moThemCongDoan && (
        <section className="kkb-them-pop">
          <div className="kkb-them-pop__head">
            <span>Khai báo Công đoạn kiểm tra mới</span>
          </div>
          <div className="kkb-them-pop__row">
            <label>
              <span>Giai đoạn *</span>
              <select
                className="rc-input"
                value={themNhom}
                onChange={(e) => { setThemNhom(e.target.value); setThemCongDoanId(""); }}
              >
                <option value="">— Chọn giai đoạn —</option>
                {Object.entries(NHOM_CONG_DOAN).map(([ma, nhan]) => (
                  <option key={ma} value={ma}>{nhan}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Công đoạn *</span>
              <select
                className="rc-input"
                value={themCongDoanId}
                disabled={!themNhom}
                onChange={(e) => setThemCongDoanId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">
                  {!themNhom ? "— Chọn giai đoạn trước —"
                    : congDoanChonDuoc.length === 0 ? "— Giai đoạn này đã khai hết —"
                      : "— Chọn công đoạn —"}
                </option>
                {congDoanChonDuoc.map((c) => (
                  <option key={c.id} value={c.id}>{c.ma} · {c.ten}</option>
                ))}
              </select>
            </label>
            <button
              type="button" className="kkb-btn kkb-btn--chinh"
              disabled={themCongDoanId === ""}
              onClick={() => setForm(formRong(Number(themCongDoanId), 1))}
            >
              <IconPlus /> Thêm hạng mục
            </button>
          </div>
          {form && form.id == null && !daKhai.has(form.cong_doan_id) && formHangMuc()}
        </section>
      )}

      {/* --- THỦY THỂ CARDS DẠNG MOCKUP IMAGE 2 --- */}
      {giaiDoan == null ? (
        <div className="rc__tablewrap">
          <table className="rc__table">
            <tbody>
              {Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="rc-skel__row"><td><span className="rc-skel" style={{ width: "60%" }} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : danhSachCongDoanHienThi.length === 0 ? (
        <div className="rc__empty-state kkb-empty">
          <p className="rc__empty-text">
            {tuKhoa ? `Không tìm thấy tiêu chí KCS phù hợp với từ khóa "${tuKhoa}".` : "Không có công đoạn nào."}
          </p>
          <p className="rc__empty-sub">
            {tuKhoa ? "Thử tìm từ khóa khác hoặc bấm nút Xoá tìm kiếm." : "Chọn giai đoạn và thêm công đoạn cần kiểm."}
          </p>
        </div>
      ) : (
        <div
          className="kkb-grid" ref={ganLuoi}
          style={{ gridTemplateColumns: `repeat(${cotThe.length}, minmax(0, 1fr))` }}
        >
          {cotThe.map((cot, iCot) => (
            <div key={iCot} className="kkb-cot">
              {cot.map(({ gdNhom, cd }) => (
                <article key={cd.cong_doan_id} className={`kkb-cd kkb-cd--${gdNhom}`}>
                  {/* BOOKMARK RIBBON FLAG NHƯ MOCKUP 2 */}
                  <div className={`kkb-cd__bookmark kkb-cd__bookmark--${gdNhom}`}>
                    <svg width="20" height="28" viewBox="0 0 24 32" fill="currentColor">
                      <path d="M0 0h24v32l-12-6-12 6V0z"/>
                    </svg>
                  </div>

                  <header className="kkb-cd__head">
                    <div className="kkb-cd__info">
                      <h3>{formatTenCongDoan(cd.ten)}</h3>
                      <span className="kkb-cd__ma">{cd.ma}</span>
                    </div>
                    <div className="kkb-cd__actions">
                      <span className="kkb-cd__count-tag">{cd.hang_muc.length} Tiêu chí</span>
                      {suaDuoc && (
                        <button
                          type="button" className="kkb-cd__btn-them"
                          onClick={() => setForm(formRong(cd.cong_doan_id, cd.hang_muc.length + 1))}
                        >
                          <IconPlus /> Thêm mới
                        </button>
                      )}
                    </div>
                  </header>

                  <div className="kkb-cd__body">
                    {cd.hang_muc.map((h, i) => (
                      <div key={h.id} className={`kkb-hm ${h.active ? "" : "kkb-hm--tat"}`}>
                        <div className={`kkb-hm__num-chip kkb-hm__num-chip--${gdNhom}`}>
                          {i + 1}
                        </div>
                        <div className="kkb-hm__content">
                          <div className="kkb-hm__ten">
                            {h.ten}
                            {!h.active && <span className="kkb-tat"> · ngừng dùng</span>}
                          </div>
                          {h.huong_dan && (
                            <div className="kkb-hm__hd">
                              <IconInfo />
                              <span>{h.huong_dan}</span>
                            </div>
                          )}
                        </div>
                        <div className="kkb-hm__actions">
                          {suaDuoc && (
                            <button
                              type="button" className="kkb-icon-btn" title="Chỉnh sửa hạng mục"
                              onClick={() => setForm({
                                id: h.id, cong_doan_id: h.cong_doan_id, ten: h.ten,
                                huong_dan: h.huong_dan ?? "", thu_tu: h.thu_tu,
                                bat_buoc: h.bat_buoc, active: h.active,
                              })}
                            >
                              <IconEdit />
                            </button>
                          )}
                          {xoaDuoc && (
                            <button
                              type="button" className="kkb-icon-btn kkb-icon-btn--danger" title="Xoá hạng mục"
                              onClick={() => xoa(h)}
                            >
                              <IconTrash />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {form && form.cong_doan_id === cd.cong_doan_id && formHangMuc()}
                </article>
              ))}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}


