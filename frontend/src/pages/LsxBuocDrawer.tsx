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
import { dvNhan as dvNhanChung, type RefRow } from "./LsxRoutingTable";
import { ngayGio, num } from "./keHoachSxShared";
import {
  type EditRow,
  heSoChu,
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

export type TabKey =
  | "nhan_dien" | "so_luong" | "ai_lam" | "giao_nhan" | "vat_tu" | "phu_thuoc" | "thoi_gian";

const TABS: { key: TabKey; id: string; label: string; chiThueNgoai?: boolean }[] = [
  { key: "nhan_dien", id: "sec-nhan-dien", label: "Nhận diện" },
  { key: "so_luong", id: "sec-so-luong", label: "Số lượng" },
  { key: "ai_lam", id: "sec-ai-lam", label: "Phân công" },
  // Sổ giao – nhận chỉ có nghĩa với hàng gửi ra ngoài; bước máy/tổ không hiện tab này.
  { key: "giao_nhan", id: "sec-giao-nhan", label: "Giao – nhận", chiThueNgoai: true },
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
  khuonRefs,
  vatTuRefs,
  phuThuocRefs,
  baiGhep,
  dvChuoi,
  canUpdate,
  onPatch,
  onPatchLsx,
  onDoiCongDoan,
  onDoiTo,
  onGiaoNhan,
  tabDau,
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
  khuonRefs: RefRow[] | null;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  /** Lệnh đang ghép chung tờ — bước in của nó do BÀI điều phối, khoá máy ở đây. */
  baiGhep: import("../api/client").LsxBaiGhep | null;
  /** Đơn vị bốn chặng của cả chuỗi (bảng routing suy ra bằng `donViChuoi`). Drawer chỉ thấy MỘT
   *  bước nên không tự suy được chặng thành phẩm — mà câu "số con sửa tại bài" cần đúng chặng đó. */
  dvChuoi: import("./lsxBuoc").DonViChuoi;
  canUpdate: boolean;
  onPatch: (p: Partial<EditRow>) => void;
  /** Sửa thẳng CẤP LỆNH — chỉ bước CUỐI dùng: SL thành phẩm cần giao (`so_luong_dat`) và hao
   *  thêm của kế hoạch (`bu_hao_to`). Cả chuỗi phía trên tính ngược lại từ hai số này. */
  onPatchLsx?: (p: { so_luong_dat?: number; bu_hao_to?: number }) => void;
  /** Đổi công đoạn: kéo lại toàn bộ mặc định của công đoạn mới (giữ SL vào/ra). */
  onDoiCongDoan: (congDoanId: number | null) => void;
  onDoiTo: (departmentId: number | null) => void;
  /** Ghi nhận hàng gia công ngoài đi/về — ghi THẲNG lên server, không chờ "Lưu công đoạn". */
  onGiaoNhan: (
    buocId: number, body: { su_kien: "giao" | "nhan"; luc?: string; so_luong?: number },
  ) => Promise<void>;
  /** Mở sẵn tới khối nào (badge ngoài bảng/sơ đồ bấm vào là nhảy thẳng, khỏi cuộn tìm). */
  tabDau?: TabKey;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("nhan_dien");

  const ngoai = row.loai_buoc === "thue_ngoai";
  // Bước đang bị bài ghép ĐÈ: máy thật nằm ở bài. Cho sửa ở đây là cho sửa một ô vô tác dụng —
  // xếp lịch không đọc nó, thời lượng cũng tính theo máy của bài. Không riêng bước in nữa: bài
  // gộp cả CTP/cán/bế, nên tra theo lớp đè (`buoc_bi_de`) chứ không so với một step_key duy nhất.
  const deLen = baiGhep?.buoc_bi_de?.[row.key] ?? null;
  const buocGhep = baiGhep && deLen ? baiGhep : null;
  const doiDonVi = !!row.don_vi_vao && !!row.don_vi_ra && row.don_vi_vao !== row.don_vi_ra;
  // Bước CUỐI là chỗ DUY NHẤT còn gõ số: SL thành phẩm cần giao + hao thêm. Bước không chạm giấy
  // (chế bản, đơn vị trống) không tính là bước cuối của dòng giấy.
  const laBuocCuoi = index === tong - 1 && !!row.don_vi_ra;
  const [slRaCuoi, setSlRaCuoi] = useState(String(soLuongDat ?? 0));
  const [haoThem, setHaoThem] = useState(String(buHaoThem ?? 0));
  useEffect(() => setSlRaCuoi(String(soLuongDat ?? 0)), [soLuongDat]);
  useEffect(() => setHaoThem(String(buHaoThem ?? 0)), [buHaoThem]);

  // --- Sổ giao – nhận thực tế (bước thuê ngoài) --------------------------------------
  // Ghi THẲNG lên server, khác mọi ô khác trong drawer (chờ "Lưu công đoạn"). Vì đây là ghi
  // nhận THỰC THI: nó xảy ra lúc lệnh đang chạy, mà lưu routing thì bị chặn đúng lúc đó.
  const gn = row.giao_nhan;
  const [gnMo, setGnMo] = useState<"giao" | "nhan" | null>(null);
  const [gnLuc, setGnLuc] = useState("");
  const [gnSl, setGnSl] = useState("");
  const [gnDangGhi, setGnDangGhi] = useState(false);
  const [gnLoi, setGnLoi] = useState<string | null>(null);
  useEffect(() => {
    setGnMo(null);
    setGnLoi(null);
  }, [row.key]);

  function moGiaoNhan(suKien: "giao" | "nhan") {
    // Điền sẵn để hai click là xong: giờ = bây giờ, SL = số dự kiến (giao) / số đã giao (nhận).
    const mac = suKien === "giao"
      ? (gn?.sl_giao_thuc ?? (row.sl_gui ? n(row.sl_gui) : null))
      : (gn?.sl_nhan_thuc ?? gn?.sl_giao_thuc ?? null);
    setGnSl(mac != null ? String(mac) : "");
    const t = new Date();
    setGnLuc(new Date(t.getTime() - t.getTimezoneOffset() * 60_000).toISOString().slice(0, 16));
    setGnLoi(null);
    setGnMo(suKien);
  }

  async function luuGiaoNhan() {
    if (!gnMo || row.id == null) return;
    setGnDangGhi(true);
    setGnLoi(null);
    try {
      await onGiaoNhan(row.id, {
        su_kien: gnMo,
        luc: gnLuc ? new Date(gnLuc).toISOString() : undefined,
        so_luong: gnSl === "" ? undefined : Number(gnSl),
      });
      setGnMo(null);
    } catch (e) {
      setGnLoi(e instanceof Error ? e.message : "Không ghi được — thử lại.");
    } finally {
      setGnDangGhi(false);
    }
  }
  // Nhãn đơn vị dùng CHUNG với bảng routing — hai nơi tự viết là sớm muộn lệch chữ.
  const dvNhan = (dv: string | null | undefined) => dvNhanChung(dv, row.nhom);
  // Máy đang chọn TRÊN FORM (chưa lưu) — nguồn tốc độ + chuẩn bị để số nhảy NGAY khi đổi máy,
  // không phải bấm Lưu rồi mới biết. Khai trước `mayDaChon` bên dưới vì hai memo cần nó.
  const mayForm = mayRefs?.find((m) => m.id === row.may_id) ?? null;
  const t = useMemo(() => thoiLuong(row, mayForm), [row, mayForm]);
  const tg = useMemo(() => thoiLuongLive(row, mayForm), [row, mayForm]);
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

  /** Định mức của một đầu việc → các ô của bước. Dùng chung cho "chọn đầu việc" và "đổi loại
   *  bước sang Tổ": cả hai đều phải kéo năng suất + ba mốc người vào ngay, không thì bước Tổ
   *  hiện 0 phút cho tới khi lưu rồi mở lại. */
  function tuDinhMuc(chon: (typeof dsKhoan)[number] | undefined): Partial<EditRow> {
    return {
      nang_suat: chon?.nang_suat_nguoi_gio ? String(chon.nang_suat_nguoi_gio) : "",
      don_vi_nang_suat: chon?.don_vi_nang_suat ?? "",
      so_nhan_cong: String(chon?.so_nguoi_tieu_chuan ?? 1),
      so_nhan_cong_toi_thieu: chon?.so_nguoi_toi_thieu ?? null,
      so_nhan_cong_tieu_chuan: chon?.so_nguoi_tieu_chuan ?? 1,
      so_nhan_cong_toi_da: chon?.so_nguoi_toi_da ?? null,
    };
  }

  /** Vật tư của đầu việc → khối "Vật tư cần dùng" (nền BOM, mg 0191).
   *
   *  GIỮ NGUYÊN dòng người: `tu_dong === false` là người tự thêm hoặc đã sửa số — máy chừa ra.
   *  Chỉ dòng máy bung lần trước mới bị thay bộ mới. Không thế thì đổi công việc khoán một cái là
   *  mất sạch số người kế hoạch vừa gõ.
   *
   *  Lọc trùng theo `vat_tu_id` vì DB có UNIQUE (bước, vật tư) — người đã tự thêm mực rồi thì máy
   *  không chèn thêm một dòng mực nữa, tôn trọng số họ khai.
   */
  function bungVatTu(chon: (typeof dsKhoan)[number] | undefined): Partial<EditRow> {
    const giu = row.vat_tus.filter((v) => !v.tu_dong);
    const moi = (chon?.vat_tus ?? [])
      .filter((v) => !giu.some((g) => g.vat_tu_id === v.vat_tu_id))
      .map((v) => ({
        vat_tu_id: v.vat_tu_id, vat_tu_ma: v.ma, vat_tu_ten: v.ten,
        don_vi: v.don_vi, so_luong: String(v.so_luong), tu_dong: true,
      }));
    return { vat_tus: [...giu, ...moi] };
  }

  function chonDauViec(rawId: string) {
    const id = rawId ? Number(rawId) : null;
    const chon = dsKhoan.find((x) => x.id === id);
    onPatch({ khoan_rate_id: id, ...tuDinhMuc(chon), ...bungVatTu(chon) });
  }

  /** Đổi loại bước. Sang TỔ: gỡ máy (bước tay không chiếm máy) và kéo định mức của đầu việc
   *  đang chọn — nguồn năng suất đổi từ MÁY sang ĐẦU VIỆC, không kéo thì thời lượng đứng ở 0. */
  function doiLoaiBuoc(k: LsxLoaiBuoc) {
    if (k !== "to") {
      set("loai_buoc", k);
      return;
    }
    const chon = dsKhoan.find((x) => x.id === row.khoan_rate_id) ?? dsKhoan[0];
    onPatch({
      loai_buoc: k,
      may_id: null,
      ...(chon ? { khoan_rate_id: chon.id, ...tuDinhMuc(chon), ...bungVatTu(chon) } : {}),
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

  // Mở drawer từ badge trạng thái ngoài bảng/sơ đồ → nhảy thẳng tới khối đó, khỏi cuộn tìm.
  useEffect(() => {
    if (!tabDau) return;
    const tab = TABS.find((t) => t.key === tabDau);
    if (tab) scrollToSection(tab.id, tab.key);
    // Chỉ chạy khi đổi bước đang mở: cuộn lại mỗi lần render là cướp thao tác của người dùng.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row.key, tabDau]);

  // Nguyên liệu cho khối "phép tính xổ ra" ở tab Thời gian. TẤT CẢ là số SERVER đã tính
  // (`thoi_luong_dien_giai`) — client KHÔNG nhân chia lại, kẻo hai nơi ra hai kết quả khác nhau.
  const setup = Number(tg.setup_phut ?? 0);
  const phatSinh = Number(tg.phat_sinh_phut ?? 0);
  const chayTB = Number(tg.chay_phut ?? 0);
  // Năng suất HIỆU DỤNG = số thật sự nằm dưới mẫu số: bước Máy là tốc độ máy, bước Tổ là
  // năng suất một người × số người tính.
  const hieuDung = Number(tg.nang_suat_hieu_dung ?? tg.nang_suat_co_so ?? 0);
  const slVao = Number(tg.so_luong_vao ?? 0);
  const soLuot = Number(tg.so_luot_chay ?? 1) || 1;
  const coDai = Boolean(tg.co_dai_toc_do);
  const khoanChuanBi: { ten?: string; phut?: number }[] = Array.isArray(tg.chuan_bi_khoan)
    ? (tg.chuan_bi_khoan as { ten?: string; phut?: number }[])
    : [];
  const mayTen = mayDaChon?.ten ?? "";
  // Ba con số chỉ khác nhau ở phần CHẠY; "thời gian khác" và chuẩn bị là hằng nên không
  // góp vào độ rộng khoảng nhanh–chậm.
  const chiemTB = Number(tg.chiem_tai_nguyen_phut ?? 0);
  const chiemMin = phatSinh + setup + Number(tg.chay_phut_min ?? chayTB);
  const chiemMax = phatSinh + setup + Number(tg.chay_phut_max ?? chayTB);
  // Chờ kỹ thuật nằm NGOÀI ba số trên (chúng đều là "chiếm máy"). Chỉ hiện khi > 0 — bước không
  // chờ mà vẫn bày một dòng "0′" là thêm chữ để đọc mà không thêm thông tin.
  const choKT = Number(tg.cho_phut ?? 0);

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
            {TABS.filter((tab) => !tab.chiThueNgoai || ngoai).map((tab) => (
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
            <div className="khsx-nhan-dien-grid">
              {/* Hàng 1 - Cột 1: Công đoạn */}
              <label className="khsx-field">
                <span className="khsx-field__label">CÔNG ĐOẠN</span>
                {congDoanRefs ? (
                  <select
                    className="khsx-select-std"
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
                    className="khsx-input-std"
                    value={row.ten}
                    disabled={!canUpdate}
                    onChange={(e) => set("ten", e.target.value)}
                  />
                )}
              </label>

              {/* Hàng 1 - Cột 2: Loại bước */}
              <div className="khsx-field">
                <span className="khsx-field__label">LOẠI BƯỚC</span>
                <div className="khsx-seg-std" role="group" aria-label="Loại bước">
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
                        onClick={() => doiLoaiBuoc(k)}
                      >
                        {m.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Hàng 2 - Cột 1: Ghi chú kỹ thuật */}
              <label className="khsx-field">
                <span className="khsx-field__label">GHI CHÚ KÝ THUẬT CHO THỢ</span>
                <input
                  className="khsx-input-std"
                  value={row.ghi_chu}
                  disabled={!canUpdate}
                  placeholder="vd: canh màu theo mẫu đã ký, kiểm tra keo..."
                  onChange={(e) => set("ghi_chu", e.target.value)}
                />
              </label>

              {/* Hàng 2 - Cột 2: Tùy chọn bước bắt buộc */}
              <div className="khsx-field">
                <span className="khsx-field__label">TÙY CHỌN BƯỚC</span>
                <label className="khsx-check-box-std">
                  <input
                    type="checkbox"
                    checked={row.bat_buoc}
                    disabled={!canUpdate}
                    onChange={(e) => set("bat_buoc", e.target.checked)}
                  />
                  <span className="khsx-check-label-text">
                    <strong>Bước bắt buộc</strong> (không được bỏ qua)
                  </span>
                </label>
              </div>
            </div>
          </Nhom>

          {/* --- 2. Số lượng --- */}
          <Nhom id="sec-so-luong" title="Số lượng & hao hụt">
            {/* Bước NGOÀI dòng giấy (ghi kẽm `bài → bản kẽm`, trộn keo `cái → mẻ`…) đứng ngoài
                chuỗi bù hao: số lượng không tự tính ngược và hao của nó không cộng vào số giấy
                phải mua. Nói NGAY TẠI ĐÂY, cạnh đúng hai con số đang đứng im — trước 11/08/2026
                lời giải thích chỉ nằm trong tooltip chip "N lưu ý" tít trên thanh tiêu đề. */}
            {row.tren_dong_giay === false && (
              <p className="khsx-note khsx-note--info">
                Bước này <strong>không nằm trên dòng giấy</strong> (đếm bằng{" "}
                {dvNhan(row.don_vi_vao)}) nên số lượng không tự tính ngược từ bước cuối, và bù hao
                của nó không cộng vào số giấy phải mua. Nhập tay số lượng nếu cần theo dõi.
              </p>
            )}
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

              {/* `heSoChu` LẬT lại khi hệ số < 1 (sách gấp tay): "10 Tờ in = 1 Thành phẩm" thay vì
                  "1 Tờ in = 0,1 Thành phẩm" — cùng cách trình bày với panel bù hao bên Tính giá. */}
              {doiDonVi && heSoChu(Number(row.he_so_quy_doi || 1), row.don_vi_vao, row.don_vi_ra) && (
                <div className="khsx-wchip khsx-wchip--info">
                  <span className="khsx-wchip__label">Quy đổi:</span>
                  <span className="khsx-wchip__val">
                    <strong>{heSoChu(Number(row.he_so_quy_doi || 1), row.don_vi_vao, row.don_vi_ra)}</strong>
                  </span>
                </div>
              )}
            </div>
          </Nhom>

          {/* --- 3. Thực hiện --- */}
          <Nhom id="sec-ai-lam" title="Phân công thực hiện">
            {!ngoai ? (
              <div className="khsx-form">
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

                {/* Bước TỔ làm bằng tay theo tổ, KHÔNG chiếm máy — ô máy ở đây chỉ gây hiểu nhầm
                    (và máy đã gán còn ăn một lane Gantt). Đổi sang Tổ là gỡ luôn máy. */}
                {row.loai_buoc !== "to" && (
                <label className="khsx-field">
                  <span className="khsx-field__label">Máy sản xuất</span>
                  {buocGhep && deLen ? (
                    <>
                      <span className="khsx-kv__val">
                        {deLen.may_ten ?? buocGhep.may_ten ?? "chưa chọn ở bài"}
                      </span>
                      {/* CẢ HAI số: lượt chung chạy bao nhiêu, và phần của riêng lệnh này là bao
                          nhiêu. Chỉ hiện một số là người đọc không biết mình đang nhìn cái nào. */}
                      {/* Đơn vị lấy từ CHÍNH bước này: lượt chung của bài và phần của lệnh chạy
                          cùng một thứ tờ, nên `row.don_vi_vao` đúng cho cả hai số (`buoc_bi_de`
                          không gửi đơn vị riêng). Ghi cứng "tờ" ở đây là dán nhãn sai lên số thật
                          khi xưởng khai đơn vị tên khác. */}
                      <span className="khsx-field__hint">
                        Bước "{deLen.ten}" chạy chung ở bài <strong>{buocGhep.ma}</strong> —
                        bài cấp {deLen.so_luong_vao.toLocaleString("vi-VN")}{" "}
                        {dvNhanChung(row.don_vi_vao)}
                        {n(row.so_luong_vao) > 0 && (
                          <>
                            {" "}· phần lệnh này {n(row.so_luong_vao).toLocaleString("vi-VN")}{" "}
                            {dvNhanChung(row.don_vi_vao)}
                          </>
                        )}
                        . Đổi máy, giấy, khổ {dvChuoi.to} và số {dvChuoi.tp} tại bài.
                      </span>
                    </>
                  ) : mayRefs ? (
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
                )}

                {/* KHUÔN của bước — chỉ hỏi khi công đoạn nguồn bật cờ "cần khuôn / kẽm riêng"
                    trong danh mục. Cờ đọc từ danh mục, KHÔNG dò chữ "bế" trong tên bước: tên là
                    chữ người dùng gõ, đặt "Die-cut" hay "Ép kim" đều được.
                    `kem` (bản kẽm) không hỏi — kẽm là vật tư tiêu hao, mỗi bài phơi mới, không có
                    dòng nào trong kho khuôn để trỏ tới. */}
                {row.requires_tooling && row.tooling_type !== "kem" && (
                  <label className="khsx-field">
                    <span className="khsx-field__label">
                      {row.tooling_type === "khuon_ep" ? "Khuôn ép nhũ / dập nổi" : "Khuôn bế"}
                    </span>
                    {khuonRefs ? (
                      <select
                        value={row.khuon_be_id ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) =>
                          set("khuon_be_id", e.target.value ? Number(e.target.value) : null)
                        }
                      >
                        <option value="">— chưa gán khuôn —</option>
                        {khuonRefs.map((k) => (
                          <option key={k.id} value={k.id}>
                            {k.ten}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="khsx-kv__val">{row.khuon_be_ten ?? "—"}</span>
                    )}
                    <span className="khsx-field__hint">
                      Bảng cân đối vật tư canh khuôn theo NGÀY CHẠY BƯỚC NÀY — khuôn về sau ngày đó
                      là báo đỏ.
                    </span>
                  </label>
                )}

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
                  <>
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
                        Số người thật sự bố trí cho bước này. Thời gian chạy tính theo mức
                        min(kế hoạch, tối đa).
                      </span>
                    </label>

                    {/* Ba mốc định mức KẾ THỪA từ đầu việc khoán của công đoạn — mặc định, KHÔNG
                        read-only: mỗi lệnh một hoàn cảnh (tổ mượn người, hàng gấp). */}
                    <div className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">Định mức nhân lực của đầu việc</span>
                      <div className="khsx-form khsx-form--3">
                        {([
                          ["Tối thiểu", "so_nhan_cong_toi_thieu"],
                          ["Tiêu chuẩn", "so_nhan_cong_tieu_chuan"],
                          ["Tối đa", "so_nhan_cong_toi_da"],
                        ] as const).map(([nhan, khoa]) => (
                          <label className="khsx-field" key={khoa}>
                            <span className="khsx-field__label">{nhan}</span>
                            <input
                              type="number"
                              min="1"
                              value={row[khoa] ?? ""}
                              placeholder="chưa khai"
                              disabled={!canUpdate}
                              onChange={(e) => {
                                const v = e.target.value === "" ? null : Number(e.target.value);
                                // `tieu_chuan` không nhận null (cột NOT NULL) — trống thì về 1.
                                set(khoa, khoa === "so_nhan_cong_tieu_chuan" ? (v ?? 1) : v);
                              }}
                            />
                          </label>
                        ))}
                      </div>
                      <span className="khsx-field__hint">
                        Kế thừa từ đầu việc khoán đang chọn, sửa tại đây chỉ đổi cho lệnh này —
                        không ngược lên danh mục. Chỉ mức <strong>tối đa</strong> vào công thức
                        (trần thời gian); tối thiểu hiện là khai báo.
                      </span>
                    </div>
                  </>
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
              </div>
            ) : (
              <div className="khsx-subcontract-sync">
                {/* Hàng 1: Nhà gia công đối tác */}
                <label className="khsx-field khsx-field--full">
                  <span className="khsx-field__label">NHÀ GIA CÔNG ĐỐI TÁC</span>
                  <input
                    className={`khsx-input-std ${!row.nha_cung_cap ? "khsx-input--bad" : ""}`}
                    value={row.nha_cung_cap}
                    disabled={!canUpdate}
                    placeholder="Nhập tên cơ sở / nhà máy gia công đối tác..."
                    onChange={(e) => set("nha_cung_cap", e.target.value)}
                  />
                </label>

                {/* Hàng 2: Số lượng gửi & Hao hụt cho phép */}
                <div className="khsx-subcontract-grid">
                  <label className="khsx-field">
                    <span className="khsx-field__label">SỐ LƯỢNG GỬI GIA CÔNG</span>
                    <div className="khsx-vattu-input-group">
                      <input
                        type="number"
                        className="khsx-vattu-num-input"
                        value={row.sl_gui}
                        placeholder={row.so_luong_vao || "0"}
                        disabled={!canUpdate}
                        onChange={(e) => set("sl_gui", e.target.value)}
                      />
                      <span className="khsx-vattu-unit-tag">{dvNhan(row.don_vi_vao)}</span>
                    </div>
                  </label>

                  <label className="khsx-field">
                    <span className="khsx-field__label">HAO HỤT CHO PHÉP</span>
                    <div className="khsx-vattu-input-group">
                      <input
                        type="number"
                        min="0"
                        className="khsx-vattu-num-input"
                        value={row.hao_hut_cho_phep}
                        placeholder="0"
                        disabled={!canUpdate}
                        onChange={(e) => set("hao_hut_cho_phep", e.target.value)}
                      />
                      <span className="khsx-vattu-unit-tag">{dvNhan(row.don_vi_vao)}</span>
                    </div>
                  </label>
                </div>

                {/* Hàng 3: Thẻ Lịch trình tiến độ gia công dạng 2 Cột rộng rãi */}
                <div className="khsx-subcontract-schedule-card">
                  <div className="khsx-schedule-card__head">
                    <span className="khsx-field__label">LỊCH TRÌNH TIẾN ĐỘ GIA CÔNG DỰ KIẾN</span>
                    {canUpdate && ngayNhanGoiY && ngayNhanGoiY !== row.ngay_nhan_dk && (
                      <button
                        type="button"
                        className="khsx-btn-suggest-pill"
                        onClick={() => set("ngay_nhan_dk", ngayNhanGoiY)}
                      >
                        ⚡ Áp dụng gợi ý: <strong>{ngayNhanGoiY}</strong>
                      </button>
                    )}
                  </div>

                  <div className="khsx-schedule-grid">
                    <label className="khsx-field">
                      <span className="khsx-field__label">NGÀY GỬI ĐI</span>
                      <input
                        type="date"
                        className={`khsx-input-std ${!row.ngay_gui_dk ? "khsx-input--bad" : ""}`}
                        value={row.ngay_gui_dk}
                        disabled={!canUpdate}
                        onChange={(e) => set("ngay_gui_dk", e.target.value)}
                      />
                    </label>

                    <label className="khsx-field">
                      <span className="khsx-field__label">NGÀY NHẬN LẠI</span>
                      <input
                        type="date"
                        className={`khsx-input-std ${!row.ngay_nhan_dk ? "khsx-input--bad" : ""}`}
                        value={row.ngay_nhan_dk}
                        disabled={!canUpdate}
                        onChange={(e) => set("ngay_nhan_dk", e.target.value)}
                      />
                    </label>

                    <label className="khsx-field">
                      <span className="khsx-field__label">THỜI GIAN VẬN CHUYỂN</span>
                      <div className="khsx-vattu-input-group">
                        <input
                          type="number"
                          step="0.5"
                          min="0"
                          className="khsx-vattu-num-input"
                          value={row.van_chuyen_ngay}
                          placeholder="0"
                          disabled={!canUpdate}
                          onChange={(e) => set("van_chuyen_ngay", e.target.value)}
                        />
                        <span className="khsx-vattu-unit-tag">ngày</span>
                      </div>
                    </label>

                    <label className="khsx-field">
                      <span className="khsx-field__label">THỜI GIAN GIA CÔNG</span>
                      <div className="khsx-vattu-input-group">
                        <input
                          type="number"
                          step="0.5"
                          min="0"
                          className="khsx-vattu-num-input"
                          value={row.gia_cong_ngay}
                          placeholder="0"
                          disabled={!canUpdate}
                          onChange={(e) => set("gia_cong_ngay", e.target.value)}
                        />
                        <span className="khsx-vattu-unit-tag">ngày</span>
                      </div>
                    </label>
                  </div>
                </div>

                {/* Hàng 4: Đơn giá & Yêu cầu kỹ thuật */}
                <div className="khsx-subcontract-grid">
                  <label className="khsx-field khsx-field--full">
                    <span className="khsx-field__label">ĐƠN GIÁ GIA CÔNG (VNĐ)</span>
                    <div className="khsx-vattu-input-group">
                      <input
                        type="number"
                        min="0"
                        className="khsx-vattu-num-input"
                        value={row.don_gia_gia_cong}
                        placeholder="0"
                        disabled={!canUpdate}
                        onChange={(e) => set("don_gia_gia_cong", e.target.value)}
                      />
                      <span className="khsx-vattu-unit-tag">đ/{dvNhan(row.don_vi_vao) || "đơn vị"}</span>
                    </div>
                  </label>

                  <label className="khsx-field khsx-field--full">
                    <span className="khsx-field__label">YÊU CẦU KÝ THUẬT GỬI ĐỐI TÁC</span>
                    <textarea
                      className="khsx-textarea-std"
                      rows={2}
                      value={row.yeu_cau_ky_thuat}
                      disabled={!canUpdate}
                      placeholder="vd: màng mờ mịn, không bong tróc mép, đóng gói 500 cái/tập..."
                      onChange={(e) => set("yeu_cau_ky_thuat", e.target.value)}
                    />
                  </label>
                </div>
              </div>
            )}
          </Nhom>

          {/* --- 3b. Thực tế giao – nhận (chỉ bước thuê ngoài) ---
              Khối trên là DỰ KIẾN, khối này là ĐÃ XẢY RA. Ghi thẳng, không chờ "Lưu công đoạn". */}
          {ngoai && (
            <Nhom id="sec-giao-nhan" title="Thực tế giao – nhận">
              <div className="khsx-gn">
                <div className="khsx-gn__head">
                  <span className={`khsx-gn__pill khsx-gn__pill--${gn?.giao_nhan_trang_thai ?? "chua_gui"}`}>
                    {gn?.giao_nhan_trang_thai === "da_ve"
                      ? "Đã về"
                      : gn?.giao_nhan_trang_thai === "dang_ngoai"
                      ? "Đang ở ngoài"
                      : "Chưa gửi"}
                  </span>
                  {gn?.qua_han_ngay != null && gn.qua_han_ngay > 0 && (
                    <span className="khsx-gn__canhbao">Quá hạn nhận {gn.qua_han_ngay} ngày</span>
                  )}
                </div>

                {row.id == null ? (
                  <p className="khsx-field__hint">
                    Bước chưa lưu — bấm <strong>Lưu công đoạn</strong> rồi mới ghi được giao – nhận.
                  </p>
                ) : (
                  <div className="khsx-gn__cot">
                    {(["giao", "nhan"] as const).map((su) => {
                      const daCo = su === "giao" ? gn?.giao_luc : gn?.nhan_luc;
                      const nguoi = su === "giao" ? gn?.nguoi_giao_ten : gn?.nguoi_nhan_ten;
                      const sl = su === "giao" ? gn?.sl_giao_thuc : gn?.sl_nhan_thuc;
                      // Chưa giao thì chưa nhận được — không mở nút nhận trước.
                      const khoa = su === "nhan" && !gn?.giao_luc;
                      return (
                        <div className="khsx-gn__muc" key={su}>
                          {daCo ? (
                            <div className="khsx-gn__dong">
                              <span className="khsx-gn__nhan">{su === "giao" ? "Giao" : "Nhận"}</span>
                              <span className="khsx-gn__noi">
                                <strong>{nguoi ?? "—"}</strong> {su === "giao" ? "giao" : "nhận"}{" "}
                                <strong>{sl != null ? num(sl) : "—"}</strong>{" "}
                                {dvNhan(row.don_vi_vao)} lúc {ngayGio(daCo)}
                              </span>
                              {canUpdate && (
                                <button
                                  type="button"
                                  className="khsx-gn__sua"
                                  onClick={() => moGiaoNhan(su)}
                                >
                                  Sửa
                                </button>
                              )}
                            </div>
                          ) : (
                            <Button
                              variant="secondary"
                              disabled={!canUpdate || khoa}
                              onClick={() => moGiaoNhan(su)}
                            >
                              {su === "giao" ? "Xác nhận đã giao" : "Xác nhận đã nhận"}
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {gnMo && (
                  <div className="khsx-gn__form">
                    <label className="khsx-field">
                      <span className="khsx-field__label">
                        {gnMo === "giao" ? "LÚC GIAO" : "LÚC NHẬN"}
                      </span>
                      <input
                        type="datetime-local"
                        className="khsx-input-std"
                        value={gnLuc}
                        onChange={(e) => setGnLuc(e.target.value)}
                      />
                    </label>
                    <label className="khsx-field">
                      <span className="khsx-field__label">
                        {gnMo === "giao" ? "SỐ THỰC GỬI" : "SỐ THỰC NHẬN"}
                      </span>
                      <div className="khsx-vattu-input-group">
                        <input
                          type="number"
                          min="0"
                          className="khsx-vattu-num-input"
                          value={gnSl}
                          onChange={(e) => setGnSl(e.target.value)}
                        />
                        <span className="khsx-vattu-unit-tag">{dvNhan(row.don_vi_vao)}</span>
                      </div>
                    </label>
                    <div className="khsx-gn__formbtns">
                      <Button variant="accent" loading={gnDangGhi} onClick={luuGiaoNhan}>
                        Ghi nhận
                      </Button>
                      <Button variant="secondary" onClick={() => setGnMo(null)}>
                        Huỷ
                      </Button>
                    </div>
                    <p className="khsx-field__hint khsx-gn__hint">
                      Người ghi nhận là bạn. Ghi xong lưu ngay, không cần bấm Lưu công đoạn.
                    </p>
                  </div>
                )}

                {gnLoi && <div className="khsx-alert">{gnLoi}</div>}
                {gn?.so_hut != null && gn.so_hut !== 0 && (
                  <div className={gn.hut_vuot_dinh_muc ? "khsx-alert" : "khsx-field__hint"}>
                    Hụt {num(gn.so_hut)} {dvNhan(row.don_vi_vao)}
                    {row.hao_hut_cho_phep
                      ? ` · định mức cho phép ${num(n(row.hao_hut_cho_phep))}`
                      : " · chưa khai định mức cho phép"}
                  </div>
                )}
                {gn?.tien_gia_cong_thuc != null && (
                  <p className="khsx-field__hint">
                    Tiền gia công thực (theo số nhận): <strong>{num(gn.tien_gia_cong_thuc)} đ</strong>
                  </p>
                )}
              </div>
            </Nhom>
          )}

          {/* --- 4. Vật tư --- */}
          <Nhom id="sec-vat-tu" title="Vật tư cần dùng">
            <div className="khsx-vattu-section">
              <p className="khsx-nhom__sub">Nhu cầu vật tư riêng biệt của công đoạn này.</p>

              {/* Vật tư khai ở đầu việc nhưng KHÔNG quy đổi được sang đơn vị của nó — máy không
                  đoán, chỉ nói thiếu gì. Không có dòng này thì vật tư "biến mất" mà không ai hiểu. */}
              {(dsKhoan.find((x) => x.id === row.khoan_rate_id)?.canh_bao_vat_tu ?? []).map((c) => (
                <p className="khsx-vattu-warn" key={c}>⚠ {c}</p>
              ))}

              {row.vat_tus.length > 0 && (
                <div className="khsx-vattu-table-head">
                  <span>VẬT TƯ & QUY CÁCH</span>
                  <span>ĐỊNH MỨC TIÊU HAO</span>
                </div>
              )}

              <div className="khsx-vattu-list">
                {row.vat_tus.map((v, i) => (
                  <div className="khsx-vattu-card" key={v.vat_tu_id}>
                    <div className="khsx-vattu-card__info">
                      <span className="khsx-vattu-card__code">{v.vat_tu_ma}</span>
                      <span className="khsx-vattu-card__name">{v.vat_tu_ten}</span>
                      {/* Cho biết số này ở đâu ra: máy tính từ quy cách, hay người đã gõ đè. Không
                          có dấu này thì đổi công việc khoán xong người ta không biết dòng nào vừa
                          bị thay, dòng nào còn giữ. */}
                      <span className={`khsx-vattu-card__src ${v.tu_dong ? "is-auto" : ""}`}>
                        {v.tu_dong ? "tự tính" : "đã sửa"}
                      </span>
                    </div>

                    <div className="khsx-vattu-card__actions">
                      <div className="khsx-vattu-input-group">
                        <input
                          type="number"
                          min="0.001"
                          step="any"
                          className="khsx-vattu-num-input"
                          value={v.so_luong}
                          placeholder="0"
                          disabled={!canUpdate}
                          // Gõ đè ⇒ dòng thành CỦA NGƯỜI: lần bung sau máy chừa ra, không ghi đè.
                          onChange={(e) =>
                            set(
                              "vat_tus",
                              row.vat_tus.map((x, j) =>
                                j === i ? { ...x, so_luong: e.target.value, tu_dong: false } : x,
                              ),
                            )
                          }
                        />
                        <span className="khsx-vattu-unit-tag">{dvNhan(v.don_vi)}</span>
                      </div>

                      {canUpdate && (
                        <button
                          type="button"
                          className="khsx-vattu-del-btn"
                          title="Xóa vật tư khỏi công đoạn"
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
                  <div className="khsx-vattu-add-box">
                    <span className="khsx-vattu-add-label">+ THÊM VẬT TƯ VÀO CÔNG ĐOẠN</span>
                    <select
                      className="khsx-vattu-select-add"
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
                              tu_dong: false,   // người tự thêm ⇒ máy không đụng tới
                            },
                          ]);
                        }
                      }}
                    >
                      <option value="">— chọn từ danh mục vật tư khác —</option>
                      {vatTuRefs
                        .filter((x) => !row.vat_tus.some((v) => v.vat_tu_id === x.id))
                        .map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.ma} · {x.ten} ({dvNhan(x.donVi)})
                          </option>
                        ))}
                    </select>
                  </div>
                )}
              </div>
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
          <Nhom id="sec-thoi-gian" title="Thời gian">
            {/* Công thức chốt 2026-08-04 (chỉ áp cho bước MÁY):
                  thời lượng = thời gian khác + chuẩn bị (từ MÁY) + SL vào × 60 ÷ tốc độ × số lượt
                Chuẩn bị + tốc độ KẾ THỪA từ module Máy, không sửa tại bước. Ô duy nhất còn gõ
                được là "Thời gian khác". Ba dòng thời lượng = thay tốc độ bằng max/TB/min. */}
            <div className="khsx-thoi-gian-grid">
              {row.loai_buoc === "may" ? (
                <label className="khsx-field">
                  <span className="khsx-field__label">SỐ LƯỢT CHẠY QUA MÁY</span>
                  <input
                    type="number"
                    min="1"
                    className="khsx-input-std"
                    value={row.so_luot_chay}
                    placeholder="1"
                    disabled={!canUpdate}
                    onChange={(e) => set("so_luot_chay", e.target.value)}
                  />
                  <span className="khsx-field__hint">In trở 2 mặt = 2 lượt qua máy</span>
                </label>
              ) : (
                <div className="khsx-field" />
              )}

              <label className="khsx-field khsx-field--highlight-input">
                <span className="khsx-field__label">THỜI GIAN KHÁC (PHÚT)</span>
                <input
                  type="number"
                  min="0"
                  className="khsx-input-std khsx-input-std--bold"
                  value={row.phat_sinh_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("phat_sinh_phut", Math.max(0, Number(e.target.value) || 0).toString())}
                />
                <span className="khsx-field__hint">Phát sinh ngoài định mức — cộng thẳng vào giờ máy</span>
              </label>

              {/* CHỜ KỸ THUẬT (mục B) — đứng NGAY CẠNH "Thời gian khác" để thấy ngay hai ô này
                  ngược nhau: một cái chiếm máy, một cái không. Kế thừa từ danh mục Công đoạn theo
                  cặp (công đoạn × loại SP) là MẶC ĐỊNH, không phải read-only: lô giấy dày hôm nay
                  khô lâu hơn thì người kế hoạch phải gõ đè được. */}
              <label className="khsx-field">
                <span className="khsx-field__label">CHỜ KỸ THUẬT (PHÚT)</span>
                <input
                  type="number"
                  min="0"
                  className="khsx-input-std"
                  value={row.cho_phut}
                  placeholder="0"
                  disabled={!canUpdate}
                  onChange={(e) => set("cho_phut", Math.max(0, Number(e.target.value) || 0).toString())}
                />
                <span className="khsx-field__hint">
                  Mực khô · keo đông · màng nguội. Máy KHÔNG bận — chỉ bước sau phải lùi.
                </span>
              </label>
            </div>

            {/* Phép tính xổ ra từng dòng, chuẩn bị chi tiết theo từng khoản của máy. */}
            <div className="khsx-tinh-gio">
              <div className="khsx-tinh-gio__row">
                <span>Thời gian khác</span>
                <b>{num(phatSinh)}′</b>
              </div>
              <div className="khsx-tinh-gio__row">
                <span>Chuẩn bị {mayTen ? `(máy ${mayTen})` : "(từ máy)"}</span>
                <b>{num(setup)}′</b>
              </div>
              {khoanChuanBi.length > 0 && (
                <ul className="khsx-tinh-gio__khoan">
                  {khoanChuanBi.map((k, i) => (
                    <li key={`${k.ten}-${i}`}>
                      <span>{k.ten || "—"}</span>
                      <span>{num(k.phut)}′</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="khsx-tinh-gio__row">
                <span>
                  Chạy{" "}
                  {/* Bước TỔ chia cho năng suất HIỆU DỤNG (năng suất người × số người tính), không
                      phải năng suất một người — hai số lệch nhau đúng bằng số người. */}
                  {hieuDung > 0
                    ? `${num(slVao)} × 60 ÷ ${num(hieuDung)}${soLuot > 1 ? ` × ${soLuot}` : ""}`
                    : "— chưa tính được"}
                </span>
                <b>{num(chayTB)}′</b>
              </div>
              <div className="khsx-tinh-gio__row khsx-tinh-gio__row--tong">
                <span>Trung bình — Gantt đặt lịch theo số này</span>
                <b>{phut(chiemTB)}</b>
              </div>
              {coDai ? (
                <div className="khsx-tinh-gio__dai">
                  <span>Nhanh nhất <b>{phut(chiemMin)}</b></span>
                  <span>Chậm nhất <b>{phut(chiemMax)}</b></span>
                </div>
              ) : (
                <div className="khsx-tinh-gio__dai khsx-tinh-gio__dai--trong">
                  {row.loai_buoc === "to"
                    ? "Đầu việc chưa khai năng suất tối thiểu / tối đa nên chưa có khoảng nhanh–chậm."
                    : "Máy chưa khai tốc độ tối thiểu / tối đa nên chưa có khoảng nhanh–chậm."}
                </div>
              )}
              {choKT > 0 && (
                <>
                  <div className="khsx-tinh-gio__row">
                    <span>Chờ kỹ thuật — máy rảnh, chỉ bước sau lùi</span>
                    <b>{num(choKT)}′</b>
                  </div>
                  <div className="khsx-tinh-gio__row khsx-tinh-gio__row--tong">
                    <span>Tổng thời gian dẫn của bước</span>
                    <b>{phut(chiemTB + choKT)}</b>
                  </div>
                </>
              )}
            </div>

            {/* Giải Trình KPI Dual Cards */}
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
