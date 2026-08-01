// Drawer CHI TIẾT 1 BƯỚC routing — chỗ khai đủ thứ mà bảng không chứa nổi.
//
// Vì sao tách khỏi bảng: routing lát này cần nhiều dữ liệu mỗi bước (đơn vị, thời gian, nhân công,
// vật tư, phụ thuộc và gia công ngoài). Nhồi hết vào bảng thì mỗi ô còn
// ~60px và phải cuộn ngang liên tục. Bảng giữ phần QUYẾT ĐỊNH (bước nào, ai làm, bao lâu), drawer
// giữ phần KHAI BÁO.
//
// Sửa ở đây ghi THẲNG vào state của bảng (không có nút "Áp dụng" riêng) — vẫn chỉ một nút "Lưu
// công đoạn" duy nhất ở bảng, nên người dùng không phải nhớ mình đang ở tầng lưu nào.
//
// Năng suất là snapshot chỉ đọc từ máy hoặc định mức đầu việc; người dùng chỉ nhập đè thời gian.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { LSX_LOAI_BUOC_META, type LsxLoaiBuoc } from "../api/client";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { dvNhan as dvNhanChung, type RefRow } from "./LsxRoutingTable";
import { num } from "./keHoachSxShared";
import {
  DON_VI_NANG_SUAT,
  type EditRow,
  n,
  phut,
  thoiLuong,
  thoiLuongLive,
} from "./lsxBuoc";

const LOAI_BUOC_ORDER: LsxLoaiBuoc[] = ["may", "to", "thue_ngoai"];

/** Gom máy theo `loai_may`.
 *  Xưởng có ~24 máy đủ loại (bế, bồi, UV, cán, in) — đổ phẳng thì gán máy bế cho bước ghi kẽm
 *  cũng trôi. Nhóm KHÔNG chặn: vẫn chọn được máy bất kỳ, chỉ là mắt phải đi qua nhãn loại. */
function nhomMayTheoLoai(mayRefs: RefRow[]): { ten: string; items: RefRow[] }[] {
  const groups = new Map<string, RefRow[]>();
  for (const m of mayRefs) {
    const k = (m.nhom || "").trim() || "Chưa phân loại";
    const arr = groups.get(k);
    if (arr) arr.push(m);
    else groups.set(k, [m]);
  }
  return [...groups.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], "vi"))
    .map(([ten, items]) => ({ ten, items }));
}

type TabKey = "nhan_dien" | "so_luong" | "ai_lam" | "vat_tu" | "phu_thuoc" | "thoi_gian";

const TABS: { key: TabKey; id: string; label: string }[] = [
  { key: "nhan_dien", id: "sec-nhan-dien", label: "Nhận diện" },
  { key: "so_luong", id: "sec-so-luong", label: "Số lượng" },
  { key: "ai_lam", id: "sec-ai-lam", label: "Phân công" },
  { key: "vat_tu", id: "sec-vat-tu", label: "Vật tư" },
  { key: "phu_thuoc", id: "sec-phu-thuoc", label: "Phụ thuộc" },
  { key: "thoi_gian", id: "sec-thoi-gian", label: "Thời gian" },
];

export function LsxBuocDrawer({
  row,
  index,
  tong,
  soLuongDat,
  buHaoThem,
  congDoanRefs,
  toRefs,
  mayRefs,
  vatTuRefs,
  phuThuocRefs,
  canUpdate,
  onPatch,
  onPatchLsx,
  onDoiCongDoan,
  onDoiTo,
  onClose,
  onPrev,
  onNext,
}: {
  row: EditRow;
  index: number;
  tong: number;
  soLuongDat: number;
  /** `lsx.bu_hao_to` — hao thêm của kế hoạch, cộng vào bước CUỐI (đơn vị theo bước đó). */
  buHaoThem: number;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  canUpdate: boolean;
  onPatch: (p: Partial<EditRow>) => void;
  /** Sửa thẳng CẤP LỆNH — chỉ bước CUỐI dùng: SL thành phẩm cần giao (`so_luong_dat`) và hao
   *  thêm của kế hoạch (`bu_hao_to`). Cả chuỗi phía trên tính ngược lại từ hai số này. */
  onPatchLsx?: (p: { so_luong_dat?: number; bu_hao_to?: number }) => void;
  /** Đổi công đoạn: kéo lại toàn bộ mặc định của công đoạn mới (giữ SL vào/ra). */
  onDoiCongDoan: (congDoanId: number | null) => void;
  onDoiTo: (departmentId: number | null) => void;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("nhan_dien");

  const ngoai = row.loai_buoc === "thue_ngoai";
  const doiDonVi = !!row.don_vi_vao && !!row.don_vi_ra && row.don_vi_vao !== row.don_vi_ra;
  // Bước CUỐI là chỗ DUY NHẤT còn gõ số: SL thành phẩm cần giao + hao thêm. Bước không chạm giấy
  // (chế bản, đơn vị trống) không tính là bước cuối của dòng giấy.
  const laBuocCuoi = index === tong - 1 && !!row.don_vi_ra;
  const [slRaCuoi, setSlRaCuoi] = useState(String(soLuongDat ?? 0));
  const [haoThem, setHaoThem] = useState(String(buHaoThem ?? 0));
  useEffect(() => setSlRaCuoi(String(soLuongDat ?? 0)), [soLuongDat]);
  useEffect(() => setHaoThem(String(buHaoThem ?? 0)), [buHaoThem]);
  // Nhãn đơn vị dùng CHUNG với bảng routing — hai nơi tự viết là sớm muộn lệch chữ.
  const dvNhan = (dv: string | null | undefined) => dvNhanChung(dv, row.nhom);
  const t = useMemo(() => thoiLuong(row), [row]);
  const tg = useMemo(() => thoiLuongLive(row), [row]);
  const nhomMay = useMemo(
    () => (mayRefs ? nhomMayTheoLoai(mayRefs) : []),
    [mayRefs],
  );

  // Đầu việc khoán chọn được: danh sách server gửi + giữ cả đầu việc ĐANG ghim dù nó không còn khớp
  const dsKhoan = useMemo(() => {
    const ds = [...row.khoan_chon_duoc];
    if (row.khoan_rate_id && !ds.some((k) => k.id === row.khoan_rate_id)) {
      ds.unshift({
        id: row.khoan_rate_id,
        ten: `(đang ghim) đầu việc #${row.khoan_rate_id}`,
        don_vi: "",
        don_gia: 0,
      });
    }
    return ds;
  }, [row.khoan_chon_duoc, row.khoan_rate_id]);
  const mayDaChon = mayRefs?.find((m) => m.id === row.may_id);
  const khoanDaChon = dsKhoan.find((k) => k.id === row.khoan_rate_id);
  const nhomPhuThuoc = useMemo(() => {
    const currentLsxId = phuThuocRefs.find((o) => o.step_key === row.key)?.lsx_id;
    const groups = new Map<number, typeof phuThuocRefs>();
    for (const option of phuThuocRefs.filter((o) => o.step_key !== row.key)) {
      groups.set(option.lsx_id, [...(groups.get(option.lsx_id) ?? []), option]);
    }
    return [...groups.entries()]
      .sort(([a], [b]) => (a === currentLsxId ? -1 : b === currentLsxId ? 1 : a - b))
      .map(([lsxId, options]) => ({
        lsxId,
        label: `${options[0]?.lsx_ma ?? `LSX #${lsxId}`}${lsxId === currentLsxId ? " · hiện tại" : ""}`,
        options,
      }));
  }, [phuThuocRefs, row.key]);

  const khoanConKhop = row.khoan_rate_id === row.khoan_rate_id_luc_tai;

  useEffect(() => titleRef.current?.focus(), [row.key]);

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (!focusables || focusables.length === 0) return;
    const dau = focusables[0];
    const cuoi = focusables[focusables.length - 1];
    if (!e.shiftKey && document.activeElement === cuoi) {
      e.preventDefault();
      dau.focus();
    } else if (e.shiftKey && document.activeElement === dau) {
      e.preventDefault();
      cuoi.focus();
    }
  }

  function set<K extends keyof EditRow>(k: K, v: EditRow[K]) {
    onPatch({ [k]: v } as Partial<EditRow>);
  }

  function chonDauViec(rawId: string) {
    const id = rawId ? Number(rawId) : null;
    const chon = dsKhoan.find((x) => x.id === id);
    onPatch({
      khoan_rate_id: id,
      nang_suat: chon?.nang_suat_nguoi_gio ? String(chon.nang_suat_nguoi_gio) : "",
      don_vi_nang_suat: chon?.don_vi_nang_suat ?? "",
      so_nhan_cong: String(chon?.so_nguoi_tieu_chuan ?? 1),
      so_nhan_cong_tieu_chuan: chon?.so_nguoi_tieu_chuan ?? 1,
      so_nhan_cong_toi_da: chon?.so_nguoi_toi_da ?? null,
      chay_phut: "",
    });
  }

  const ngayNhanGoiY = useMemo(() => {
    if (!row.ngay_gui_dk) return "";
    const ngay = n(row.van_chuyen_ngay) * 2 + n(row.gia_cong_ngay);
    if (ngay <= 0) return "";
    const d = new Date(`${row.ngay_gui_dk}T00:00:00`);
    d.setDate(d.getDate() + Math.ceil(ngay));
    const hai = (v: number) => String(v).padStart(2, "0");
    return `${d.getFullYear()}-${hai(d.getMonth() + 1)}-${hai(d.getDate())}`;
  }, [row.ngay_gui_dk, row.van_chuyen_ngay, row.gia_cong_ngay]);

  const meta = LSX_LOAI_BUOC_META[row.loai_buoc];

  const scrollToSection = (id: string, key: TabKey) => {
    setActiveTab(key);
    const target = panelRef.current?.querySelector(`#${id}`);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // Tính tỷ lệ % thời gian cho thanh phân bổ
  const timeBreakdown = useMemo(() => {
    const setup = Number(tg.setup_phut ?? 0);
    const chay = Number(tg.chay_phut ?? 0);
    const veSinh = Number(tg.ve_sinh_phut ?? 0);
    const cho = Number(tg.cho_phut ?? 0);
    const diChuyen = Number(tg.di_chuyen_phut ?? 0);
    const total = setup + chay + veSinh + cho + diChuyen || 1;
    return {
      setup,
      chay,
      veSinh,
      cho,
      diChuyen,
      total,
      pctSetup: (setup / total) * 100,
      pctChay: (chay / total) * 100,
      pctVeSinh: (veSinh / total) * 100,
      pctCho: ((cho + diChuyen) / total) * 100,
    };
  }, [tg]);

  return (
    <div className="khsx-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panelRef}
        className={`khsx-drawer khsx-drawer--buoc khsx-drawer--${row.loai_buoc}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="khsx-buoc-title"
        onKeyDown={onKeyDown}
      >
        <header className="khsx-drawer__head">
          {/* Accent bar thể hiện loại bước ở cạnh trên */}
          <div className={`khsx-drawer__accent khsx-drawer__accent--${meta.tone}`} />

          {/* Top Bar: Title + Badges + Actions gộp 1 hàng siêu gọn */}
          <div className="khsx-drawer__head-row">
            <div className="khsx-drawer__head-left">
              <span className="khsx-stepper-pill">
                BƯỚC {String(index + 1).padStart(2, "0")}/{String(tong).padStart(2, "0")}
              </span>
              <span className={`khsx-lb khsx-lb--${meta.tone}`}>{meta.label}</span>
              <h2
                className="khsx-drawer__title-compact"
                id="khsx-buoc-title"
                tabIndex={-1}
                ref={titleRef}
              >
                {row.ten || "Công đoạn chưa đặt tên"}
              </h2>
            </div>

            <div className="khsx-drawer__actions">
              <div className="khsx-buoc__nav" role="group" aria-label="Điều hướng bước">
                <button
                  type="button"
                  className="khsx-nav-btn"
                  onClick={onPrev}
                  disabled={index === 0}
                  aria-label="Bước trước"
                  title="Bước trước"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                </button>
                <button
                  type="button"
                  className="khsx-nav-btn"
                  onClick={onNext}
                  disabled={index >= tong - 1}
                  aria-label="Bước sau"
                  title="Bước sau"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
              </div>

              <button
                type="button"
                className="khsx-drawer__x"
                onClick={onClose}
                aria-label="Đóng panel"
                title="Đóng (Esc)"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Sub-navigation chỉ mục gọn gàng ở hàng 2 */}
          <nav className="khsx-drawer-subnav" aria-label="Phân đoạn nội dung">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`khsx-subnav-item ${activeTab === tab.key ? "is-active" : ""}`}
                onClick={() => scrollToSection(tab.id, tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </header>

        <div className="khsx-drawer__body">
          {/* --- 1. Nhận diện --- */}
          <Nhom id="sec-nhan-dien" title="Nhận diện">
            <div className="khsx-form">
              <label className="khsx-field">
                <span className="khsx-field__label">Công đoạn</span>
                {congDoanRefs ? (
                  <select
                    value={row.cong_doan_id ?? (row.ten ? "__keep__" : "")}
                    disabled={!canUpdate}
                    onChange={(e) => {
                      if (e.target.value === "__keep__") return;
                      onDoiCongDoan(e.target.value ? Number(e.target.value) : null);
                    }}
                  >
                    <option value="">— chọn công đoạn —</option>
                    {row.cong_doan_id == null && row.ten && (
                      <option value="__keep__">{row.ten} (tên tự do)</option>
                    )}
                    {row.cong_doan_id != null &&
                      !congDoanRefs.some((c) => c.id === row.cong_doan_id) && (
                        <option value={row.cong_doan_id}>{row.ten}</option>
                      )}
                    {congDoanRefs.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.ten}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={row.ten}
                    disabled={!canUpdate}
                    onChange={(e) => set("ten", e.target.value)}
                  />
                )}
              </label>

              <div className="khsx-field khsx-field--wide">
                <span className="khsx-field__label">
                  Loại bước — quyết định tài nguyên chiếm dụng khi xếp lịch
                </span>
                <div className="khsx-seg khsx-seg--wide" role="group" aria-label="Loại bước">
                  {LOAI_BUOC_ORDER.map((k) => {
                    const m = LSX_LOAI_BUOC_META[k];
                    return (
                      <button
                        key={k}
                        type="button"
                        className={row.loai_buoc === k ? "is-active" : ""}
                        disabled={!canUpdate}
                        aria-pressed={row.loai_buoc === k}
                        title={m.hint}
                        onClick={() => set("loai_buoc", k)}
                      >
                        {m.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <label className="khsx-field--check-card">
                <input
                  type="checkbox"
                  checked={row.bat_buoc}
                  disabled={!canUpdate}
                  onChange={(e) => set("bat_buoc", e.target.checked)}
                />
                <div className="khsx-check-card__info">
                  <span className="khsx-check-card__title">Bước bắt buộc</span>
                  <span className="khsx-check-card__sub">
                    Bỏ tick = công đoạn tùy chọn, có thể bỏ qua khi cần tiến độ gấp
                  </span>
                </div>
              </label>

              <label className="khsx-field khsx-field--wide">
                <span className="khsx-field__label">Ghi chú kỹ thuật cho thợ</span>
                <input
                  value={row.ghi_chu}
                  disabled={!canUpdate}
                  placeholder="vd: canh màu theo mẫu đã ký, kiểm tra kỹ độ bám keo"
                  onChange={(e) => set("ghi_chu", e.target.value)}
                />
              </label>
            </div>
          </Nhom>

          {/* --- 2. Số lượng --- */}
          <Nhom id="sec-so-luong" title="Số lượng & hao hụt">
            <div className="khsx-metric-cards-container">
              {/* Card Vào */}
              <div className="khsx-mcard">
                <div className="khsx-mcard__head">
                  <span className="khsx-mcard__label">SỐ LƯỢNG VÀO</span>
                </div>
                <div className="khsx-mcard__body">
                  <span className="khsx-mcard__val">{num(Number(row.so_luong_vao || 0))}</span>
                  <span className="khsx-unit-badge">{dvNhan(row.don_vi_vao)}</span>
                </div>
                <span className="khsx-mcard__hint">Đầu vào công đoạn</span>
              </div>

              {/* Center Flow Icon */}
              <div className="khsx-mcard__flow-badge" title="Luồng tính ngược số lượng">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              </div>

              {/* Card Ra */}
              <div className={`khsx-mcard ${laBuocCuoi ? "khsx-mcard--highlight" : ""}`}>
                <div className="khsx-mcard__head">
                  <span className="khsx-mcard__label">SỐ LƯỢNG RA</span>
                  {laBuocCuoi && <span className="khsx-tag-editable">Số giao</span>}
                </div>
                <div className="khsx-mcard__body">
                  {laBuocCuoi ? (
                    <div className="khsx-mcard__input-group">
                      <input
                        type="number"
                        min={1}
                        className="khsx-metric-input"
                        value={slRaCuoi}
                        disabled={!canUpdate}
                        onChange={(e) => setSlRaCuoi(e.target.value)}
                        onBlur={() =>
                          onPatchLsx?.({ so_luong_dat: Math.max(0, Number(slRaCuoi) || 0) })
                        }
                      />
                      <span className="khsx-unit-badge">{dvNhan(row.don_vi_ra)}</span>
                    </div>
                  ) : (
                    <>
                      <span className="khsx-mcard__val">{num(Number(row.so_luong_ra || 0))}</span>
                      <span className="khsx-unit-badge">{dvNhan(row.don_vi_ra)}</span>
                    </>
                  )}
                </div>
                <span className="khsx-mcard__hint">
                  {laBuocCuoi ? "Số thành phẩm giao" : "Tự động tính ngược từ bước thành phẩm cuối"}
                </span>
              </div>
            </div>

            {/* Hao Hụt & Quy Đổi Bar */}
            <div className="khsx-wastage-bar">
              <div className="khsx-wchip">
                <span className="khsx-wchip__label">Hao hụt định mức:</span>
                <span className="khsx-wchip__val">
                  {Number(row.hao_hut || 0) > 0 || Number(row.hao_hut_pct || 0) > 0 ? (
                    <>
                      <strong>{num(Number(row.hao_hut))}</strong>{" "}
                      <span className="khsx-unit-badge khsx-unit-badge--sm">{dvNhan(row.don_vi_vao)}</span>
                      {Number(row.hao_hut_pct || 0) > 0 && ` (+${row.hao_hut_pct}%)`}
                    </>
                  ) : (
                    <span className="khsx-val-muted">—</span>
                  )}
                </span>
              </div>

              {laBuocCuoi && (
                <div className="khsx-wchip khsx-wchip--input">
                  <span className="khsx-wchip__label">Hao hụt thêm:</span>
                  <div className="khsx-wchip__input-group">
                    <input
                      type="number"
                      min={0}
                      className="khsx-wchip-input"
                      value={haoThem}
                      disabled={!canUpdate}
                      onChange={(e) => setHaoThem(e.target.value)}
                      onBlur={() =>
                        onPatchLsx?.({ bu_hao_to: Math.max(0, Number(haoThem) || 0) })
                      }
                    />
                    <span className="khsx-unit-badge khsx-unit-badge--sm">{dvNhan(row.don_vi_ra)}</span>
                  </div>
                </div>
              )}

              {doiDonVi && (
                <div className="khsx-wchip khsx-wchip--info">
                  <span className="khsx-wchip__label">Quy đổi:</span>
                  <span className="khsx-wchip__val">
                    1 {dvNhan(row.don_vi_vao)} = <strong>{num(Number(row.he_so_quy_doi || 1))}</strong>{" "}
                    {dvNhan(row.don_vi_ra)}
                  </span>
                </div>
              )}
            </div>
          </Nhom>

          {/* --- 3. Thực hiện --- */}
          <Nhom id="sec-ai-lam" title="Phân công thực hiện">
            <div className="khsx-form">
              {!ngoai && (
                <>
                  <label className="khsx-field">
                    <span className="khsx-field__label">Tổ phụ trách</span>
                    {toRefs ? (
                      <select
                        value={row.department_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) =>
                          onDoiTo(e.target.value ? Number(e.target.value) : null)
                        }
                      >
                        <option value="">— tổ mặc định của công đoạn —</option>
                        {toRefs.map((t2) => (
                          <option key={t2.id} value={t2.id}>
                            {t2.ten}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="khsx-kv__val">tổ mặc định</span>
                    )}
                  </label>

                  <label className="khsx-field">
                    <span className="khsx-field__label">Máy sản xuất</span>
                    {mayRefs ? (
                      <select
                        value={row.may_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) =>
                          set("may_id", e.target.value ? Number(e.target.value) : null)
                        }
                      >
                        <option value="">— chưa gán máy —</option>
                        {nhomMay.map((g) => (
                          <optgroup key={g.ten} label={g.ten}>
                            {g.items.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.ten}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    ) : (
                      <span className="khsx-kv__val">—</span>
                    )}
                  </label>

                  {row.loai_buoc === "may" && (
                    <label className="khsx-field">
                      <span className="khsx-field__label">Số người vận hành kế hoạch</span>
                      <input
                        type="number"
                        min="1"
                        value={row.so_nhan_cong}
                        placeholder="1"
                        disabled={!canUpdate}
                        onChange={(e) => set("so_nhan_cong", e.target.value)}
                      />
                      <span className="khsx-field__hint">
                        Kíp vận hành tiêu chuẩn: {row.so_nhan_cong_tieu_chuan} người. Nhân lực
                        không làm thay đổi tốc độ máy.
                      </span>
                    </label>
                  )}

                  {row.loai_buoc === "to" && (
                    <label className="khsx-field">
                      <span className="khsx-field__label">Số người kế hoạch</span>
                      <input
                        type="number"
                        min="1"
                        value={row.so_nhan_cong}
                        placeholder="1"
                        disabled={!canUpdate}
                        onChange={(e) => set("so_nhan_cong", e.target.value)}
                      />
                      <span className="khsx-field__hint">
                        Định mức tiêu chuẩn: {row.so_nhan_cong_tieu_chuan} người. Tối đa tăng
                        năng suất: {row.so_nhan_cong_toi_da ?? "chưa khai"} người.
                      </span>
                    </label>
                  )}

                  {(row.khoan_chon_duoc.length > 0 || row.khoan_rate_id != null) && (
                    <div className="khsx-field khsx-field--wide khsx-khoan-card">
                      <div className="khsx-khoan-card__head">
                        <span className="khsx-field__label">Công việc khoán</span>
                        <span className="khsx-tag-subtle">bảng khoán của tổ</span>
                      </div>
                      <select
                        value={row.khoan_rate_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) => chonDauViec(e.target.value)}
                      >
                        <option value="">— chọn đầu việc khoán —</option>
                        {dsKhoan.map((k) => (
                          <option key={k.id} value={k.id}>
                            {k.don_vi
                              ? `${k.ten} — ${num(k.don_gia)} đ/${k.don_vi}`
                              : k.ten}
                          </option>
                        ))}
                      </select>

                      <div className="khsx-khoan-card__status">
                        {!khoanConKhop ? (
                          <span className="khsx-pill-status khsx-pill-status--warn">
                            Lưu công đoạn để tính lại tiền công
                          </span>
                        ) : row.khoan_dien_giai ? (
                          <span className="khsx-pill-status khsx-pill-status--ok">
                            {row.khoan_dien_giai}
                          </span>
                        ) : row.khoan_ly_do ? (
                          <span className="khsx-pill-status khsx-pill-status--error">
                            {row.khoan_ly_do}
                          </span>
                        ) : row.khoan_chon_duoc.length > 1 ? (
                          <span className="khsx-field__hint">
                            Tổ có {row.khoan_chon_duoc.length} đầu việc khoán — chọn đúng việc thợ làm để tự động ra tiền công.
                          </span>
                        ) : null}
                      </div>
                    </div>
                  )}
                </>
              )}

              {ngoai && (
                <div className="khsx-subcontract-box">
                  <div className="khsx-subcontract-grid">
                    <label className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">Nhà gia công đối tác</span>
                      <input
                        className={!row.nha_cung_cap ? "khsx-input--bad" : ""}
                        value={row.nha_cung_cap}
                        disabled={!canUpdate}
                        placeholder="Tên cơ sở nhận gia công"
                        onChange={(e) => set("nha_cung_cap", e.target.value)}
                      />
                    </label>

                    <label className="khsx-field">
                      <span className="khsx-field__label">Số lượng gửi</span>
                      <input
                        type="number"
                        value={row.sl_gui}
                        placeholder={row.so_luong_vao || "—"}
                        disabled={!canUpdate}
                        onChange={(e) => set("sl_gui", e.target.value)}
                      />
                    </label>

                    <label className="khsx-field">
                      <span className="khsx-field__label">Hao hụt cho phép</span>
                      <input
                        type="number"
                        value={row.hao_hut_cho_phep}
                        placeholder="0"
                        disabled={!canUpdate}
                        onChange={(e) => set("hao_hut_cho_phep", e.target.value)}
                      />
                    </label>
                  </div>

                  {/* Thanh Tiến Độ Mini 4 Mốc Gia Công */}
                  <div className="khsx-subcontract-timeline">
                    <span className="khsx-timeline-title">LỊCH TRÌNH THUÊ NGOÀI DỰ KIẾN</span>
                    <div className="khsx-timeline-steps">
                      <div className="khsx-timeline-step">
                        <span className="khsx-timeline-step__label">Gửi đi</span>
                        <input
                          type="date"
                          className={`khsx-timeline-input ${!row.ngay_gui_dk ? "khsx-input--bad" : ""}`}
                          value={row.ngay_gui_dk}
                          disabled={!canUpdate}
                          onChange={(e) => set("ngay_gui_dk", e.target.value)}
                        />
                      </div>
                      <div className="khsx-timeline-arrow">➔</div>
                      <div className="khsx-timeline-step">
                        <span className="khsx-timeline-step__label">Vận chuyển (ngày)</span>
                        <input
                          type="number"
                          step="0.5"
                          className="khsx-timeline-input"
                          value={row.van_chuyen_ngay}
                          placeholder="0"
                          disabled={!canUpdate}
                          onChange={(e) => set("van_chuyen_ngay", e.target.value)}
                        />
                      </div>
                      <div className="khsx-timeline-arrow">➔</div>
                      <div className="khsx-timeline-step">
                        <span className="khsx-timeline-step__label">Gia công (ngày)</span>
                        <input
                          type="number"
                          step="0.5"
                          className="khsx-timeline-input"
                          value={row.gia_cong_ngay}
                          placeholder="0"
                          disabled={!canUpdate}
                          onChange={(e) => set("gia_cong_ngay", e.target.value)}
                        />
                      </div>
                      <div className="khsx-timeline-arrow">➔</div>
                      <div className="khsx-timeline-step">
                        <span className="khsx-timeline-step__label">Nhận lại</span>
                        <input
                          type="date"
                          className={`khsx-timeline-input ${!row.ngay_nhan_dk ? "khsx-input--bad" : ""}`}
                          value={row.ngay_nhan_dk}
                          disabled={!canUpdate}
                          onChange={(e) => set("ngay_nhan_dk", e.target.value)}
                        />
                      </div>
                    </div>

                    {canUpdate && ngayNhanGoiY && ngayNhanGoiY !== row.ngay_nhan_dk && (
                      <div className="khsx-timeline-suggest">
                        <button
                          type="button"
                          className="khsx-btn-suggest"
                          onClick={() => set("ngay_nhan_dk", ngayNhanGoiY)}
                        >
                          Áp dụng ngày gợi ý: {ngayNhanGoiY} (Gửi + Vận chuyển × 2 + Gia công)
                        </button>
                      </div>
                    )}
                  </div>

                  <div className="khsx-form khsx-form--top-gap">
                    <label className="khsx-field">
                      <span className="khsx-field__label">Đơn giá gia công</span>
                      <input
                        type="number"
                        value={row.don_gia_gia_cong}
                        placeholder="0"
                        disabled={!canUpdate}
                        onChange={(e) => set("don_gia_gia_cong", e.target.value)}
                      />
                    </label>

                    <label className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">Yêu cầu kỹ thuật gửi đối tác</span>
                      <textarea
                        rows={2}
                        value={row.yeu_cau_ky_thuat}
                        disabled={!canUpdate}
                        placeholder="vd: màng mờ mịn, không bong tróc mép, đóng gói 500 cái/tập"
                        onChange={(e) => set("yeu_cau_ky_thuat", e.target.value)}
                      />
                    </label>
                  </div>
                </div>
              )}
            </div>
          </Nhom>

          {/* --- 4. Vật tư --- */}
          <Nhom id="sec-vat-tu" title="Vật tư cần dùng">
            <p className="khsx-nhom__sub">Nhu cầu vật tư riêng biệt của công đoạn này.</p>
            <div className="khsx-vattu-list">
              {row.vat_tus.map((v, i) => (
                <div className="khsx-vattu-row" key={v.vat_tu_id}>
                  <div className="khsx-vattu-row__info">
                    <span className="khsx-vattu-row__code">{v.vat_tu_ma}</span>
                    <span className="khsx-vattu-row__name">{v.vat_tu_ten}</span>
                  </div>
                  <div className="khsx-vattu-row__actions">
                    <input
                      type="number"
                      min="0.001"
                      step="any"
                      className="khsx-vattu-input"
                      value={v.so_luong}
                      disabled={!canUpdate}
                      onChange={(e) =>
                        set(
                          "vat_tus",
                          row.vat_tus.map((x, j) =>
                            j === i ? { ...x, so_luong: e.target.value } : x,
                          ),
                        )
                      }
                    />
                    <span className="khsx-unit-badge">{v.don_vi}</span>
                    {canUpdate && (
                      <button
                        type="button"
                        className="khsx-btn-icon-danger"
                        title="Xóa vật tư"
                        onClick={() =>
                          set(
                            "vat_tus",
                            row.vat_tus.filter((_, j) => j !== i),
                          )
                        }
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              ))}

              {canUpdate && vatTuRefs && (
                <div className="khsx-vattu-add">
                  <span className="khsx-field__label">Thêm vật tư vào công đoạn</span>
                  <select
                    value=""
                    onChange={(e) => {
                      const item = vatTuRefs.find((v) => v.id === Number(e.target.value));
                      if (item && !row.vat_tus.some((v) => v.vat_tu_id === item.id)) {
                        set("vat_tus", [
                          ...row.vat_tus,
                          {
                            vat_tu_id: item.id,
                            vat_tu_ma: item.ma ?? "",
                            vat_tu_ten: item.ten,
                            don_vi: item.donVi ?? "",
                            so_luong: "",
                          },
                        ]);
                      }
                    }}
                  >
                    <option value="">— chọn từ danh mục vật tư in ấn —</option>
                    {vatTuRefs
                      .filter((x) => !row.vat_tus.some((v) => v.vat_tu_id === x.id))
                      .map((x) => (
                        <option key={x.id} value={x.id}>
                          {x.ma} · {x.ten} ({x.donVi})
                        </option>
                      ))}
                  </select>
                </div>
              )}
            </div>
          </Nhom>

          {/* --- 5. Phụ thuộc DAG --- */}
          <Nhom id="sec-phu-thuoc" title="Phụ thuộc để xếp lịch (DAG)">
            <p className="khsx-nhom__sub">
              Bước này chỉ bắt đầu sản xuất sau khi các bước tiền nhiệm dưới đây hoàn thành.
            </p>
            <div className="khsx-dag-groups">
              {nhomPhuThuoc.map((group) => (
                <div className="khsx-dag-group-card" key={group.lsxId}>
                  <div className="khsx-dag-group-card__head">{group.label}</div>
                  <div className="khsx-dag-chips">
                    {group.options.map((o) => {
                      const active = row.phu_thuoc_step_keys.includes(o.step_key);
                      return (
                        <label
                          key={o.step_key}
                          className={`khsx-dag-chip ${active ? "is-active" : ""}`}
                        >
                          <input
                            type="checkbox"
                            disabled={!canUpdate}
                            checked={active}
                            onChange={(e) =>
                              set(
                                "phu_thuoc_step_keys",
                                e.target.checked
                                  ? [...row.phu_thuoc_step_keys, o.step_key]
                                  : row.phu_thuoc_step_keys.filter((k) => k !== o.step_key),
                              )
                            }
                          />
                          <span>{o.ten_buoc}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
              {nhomPhuThuoc.length === 0 && (
                <span className="khsx-field__hint">Chưa có bước khác trong đơn hàng.</span>
              )}
            </div>
          </Nhom>

          {/* --- 6. Năng suất & thời gian --- */}
          <Nhom id="sec-thoi-gian" title="Thời gian & Năng suất">
            <div className="khsx-form">
              <label className="khsx-field">
                <span className="khsx-field__label">Chuẩn bị / Setup (phút)</span>
                <input
                  type="number"
                  value={row.setup_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("setup_phut", e.target.value)}
                />
              </label>

              {row.loai_buoc === "may" && (
                <label className="khsx-field">
                  <span className="khsx-field__label">Số lượt chạy qua máy</span>
                  <input
                    type="number"
                    min="1"
                    value={row.so_luot_chay}
                    placeholder="1"
                    disabled={!canUpdate}
                    onChange={(e) => set("so_luot_chay", e.target.value)}
                  />
                </label>
              )}

              <label className="khsx-field">
                <span className="khsx-field__label">Năng suất kế hoạch</span>
                <div className="khsx-inline">
                  <input type="number" value={row.nang_suat} placeholder="—" disabled />
                  <select
                    className="khsx-inline__unit"
                    value={row.don_vi_nang_suat}
                    disabled
                    aria-label="Đơn vị năng suất"
                  >
                    <option value="">— đơn vị —</option>
                    {DON_VI_NANG_SUAT.map((u) => (
                      <option key={u.key} value={u.key}>
                        {u.label}
                      </option>
                    ))}
                  </select>
                </div>
                <span className="khsx-field__hint">
                  {row.loai_buoc === "may"
                    ? "Kế thừa từ tốc độ chuẩn của máy."
                    : row.loai_buoc === "to"
                    ? "Kế thừa từ định mức đầu việc khoán."
                    : "Không áp dụng cho bước thuê ngoài."}
                </span>
              </label>

              <label className="khsx-field">
                <span className="khsx-field__label">Thời gian chạy (phút)</span>
                <input
                  type="number"
                  value={row.chay_phut}
                  placeholder={t.chay > 0 ? String(Math.round(t.chay)) : "—"}
                  disabled={!canUpdate}
                  onChange={(e) => set("chay_phut", e.target.value)}
                />
                <span className="khsx-field__hint">
                  Để trống = tự động tính từ năng suất. Gõ số vào = ghi đè thời gian chạy.
                </span>
              </label>

              <label className="khsx-field">
                <span className="khsx-field__label">Vệ sinh / chuyển đổi (phút)</span>
                <input
                  type="number"
                  value={row.ve_sinh_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("ve_sinh_phut", e.target.value)}
                />
              </label>

              <label className="khsx-field">
                <span className="khsx-field__label">Chờ kỹ thuật (phút)</span>
                <input
                  type="number"
                  value={row.cho_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("cho_phut", e.target.value)}
                />
                <span className="khsx-field__hint">Khô mực / khô keo — không chiếm dụng máy.</span>
              </label>

              <label className="khsx-field">
                <span className="khsx-field__label">Di chuyển sang bước sau (phút)</span>
                <input
                  type="number"
                  value={row.di_chuyen_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("di_chuyen_phut", e.target.value)}
                />
              </label>
            </div>

            {/* Thanh Phân Bổ Thời Gian Đồ Họa Nằm Ngang (Time Distribution Bar) */}
            <div className="khsx-time-analytics">
              <span className="khsx-time-analytics__title">PHÂN BỔ THỜI GIAN KẾ HOẠCH</span>
              <div className="khsx-time-bar">
                <div
                  className="khsx-time-bar__seg khsx-time-bar__seg--setup"
                  style={{ width: `${timeBreakdown.pctSetup}%` }}
                  title={`Setup: ${timeBreakdown.setup} phút`}
                />
                <div
                  className="khsx-time-bar__seg khsx-time-bar__seg--chay"
                  style={{ width: `${timeBreakdown.pctChay}%` }}
                  title={`Chạy: ${timeBreakdown.chay} phút`}
                />
                <div
                  className="khsx-time-bar__seg khsx-time-bar__seg--vesinh"
                  style={{ width: `${timeBreakdown.pctVeSinh}%` }}
                  title={`Vệ sinh: ${timeBreakdown.veSinh} phút`}
                />
                <div
                  className="khsx-time-bar__seg khsx-time-bar__seg--cho"
                  style={{ width: `${timeBreakdown.pctCho}%` }}
                  title={`Chờ / Di chuyển: ${timeBreakdown.cho + timeBreakdown.diChuyen} phút`}
                />
              </div>

              <div className="khsx-time-legend">
                <span className="khsx-legend-item khsx-legend-item--setup">
                  Setup {num(timeBreakdown.setup)}m
                </span>
                <span className="khsx-legend-item khsx-legend-item--chay">
                  Chạy {num(timeBreakdown.chay)}m
                </span>
                <span className="khsx-legend-item khsx-legend-item--vesinh">
                  Vệ sinh {num(timeBreakdown.veSinh)}m
                </span>
                <span className="khsx-legend-item khsx-legend-item--cho">
                  Chờ/Di chuyển {num(timeBreakdown.cho + timeBreakdown.diChuyen)}m
                </span>
              </div>
            </div>

            {/* Bảng Giải Trình Công Thức Tính & Thời Gian Tổng */}
            <div className="khsx-tinh">
              {Array.isArray(tg.canh_bao) &&
                tg.canh_bao.map((warning) => (
                  <div className="khsx-alert" key={String(warning)}>
                    {String(warning)}
                  </div>
                ))}

              <div className="khsx-tinh__row">
                <span className="khsx-tinh__label">Nguồn tính:</span>
                <span className="khsx-tinh__note">
                  {row.loai_buoc === "may"
                    ? mayDaChon
                      ? `Năng suất máy ${mayDaChon.ten}`
                      : "Chưa gán máy"
                    : row.loai_buoc === "to"
                    ? khoanDaChon
                      ? `Định mức đầu việc ${khoanDaChon.ten}`
                      : "Chưa chọn đầu việc khoán"
                    : "Tiến độ do kế hoạch thuê ngoài khai"}
                </span>
              </div>

              {Number(tg.nang_suat_hieu_dung ?? 0) > 0 && (
                <div className="khsx-formula-box">
                  <span className="khsx-formula-box__title">Công thức thời gian chạy:</span>
                  <code className="khsx-formula-code">
                    {num(Number(tg.so_luong_vao ?? 0))} {String(tg.don_vi_vao ?? "")}
                    {row.loai_buoc === "may" ? ` × ${Number(tg.so_luot_chay ?? 1)} lượt` : ""} ÷{" "}
                    {num(Number(tg.nang_suat_hieu_dung ?? 0))}/giờ × 60 ={" "}
                    <strong>{num(Number(tg.chay_phut ?? 0))} phút</strong>
                  </code>
                </div>
              )}

              <div className="khsx-tinh-metrics-row">
                <div className="khsx-kpi-box khsx-kpi-box--primary">
                  <span className="khsx-kpi-box__label">Thời gian chiếm máy (Gantt)</span>
                  <span className="khsx-kpi-box__val">{phut(t.chiemMay)}</span>
                  <span className="khsx-kpi-box__hint">Chiếm dụng lịch máy / tổ</span>
                </div>

                <div className="khsx-kpi-box">
                  <span className="khsx-kpi-box__label">Tổng thời gian hoàn thành</span>
                  <span className="khsx-kpi-box__val">{phut(t.tong)}</span>
                  <span className="khsx-kpi-box__hint">
                    {t.tong !== t.chiemMay
                      ? `Gồm ${phut(t.tong - t.chiemMay)} chờ/di chuyển`
                      : "Bắt đầu bước sau ngay"}
                  </span>
                </div>
              </div>

              {canUpdate && (
                <p className="khsx-field__hint khsx-hint-center">
                  Sửa số rồi bấm <strong>Lưu công đoạn</strong> ở bảng chính để tính lại diễn giải.
                </p>
              )}
            </div>
          </Nhom>
        </div>

        <footer className="khsx-drawer__foot">
          <p className="khsx-drawer__tally">
            Sửa ở đây chưa ghi vào DB — bấm <strong>Lưu công đoạn</strong> ở bảng chính.
          </p>
          <div className="khsx-drawer__footbtns">
            <Button variant="secondary" onClick={onClose}>
              Xong
            </Button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function Nhom({
  id,
  title,
  children,
}: {
  id?: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="khsx-nhom">
      <h3 className="khsx-nhom__title">{title}</h3>
      {children}
    </section>
  );
}
