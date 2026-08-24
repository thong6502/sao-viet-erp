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
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { LSX_LOAI_BUOC_META, type LsxLoaiBuoc } from "../api/client";
import { Button } from "../components/Button";
import { TagPicker } from "../components/TagPicker";
import { dvNhan as dvNhanChung, type RefRow } from "./LsxRoutingTable";
import { ngayGio, num } from "./keHoachSxShared";
import {
  type EditRow,
  heSoChu,
  n,
  nhanDonVi,
  phut,
  tenBuoc,
  thoiLuong,
  thoiLuongLive,
} from "./lsxBuoc";

// "Thuê ngoài" GỠ khỏi nút chọn theo yêu cầu — xưởng không đưa việc ra ngoài qua màn này.
// Vẫn CHỪA nút khi bước ĐÃ lỡ đặt thuê-ngoài (dữ liệu cũ) để toggle không rơi vào trạng thái
// trống không đổi được — người dùng thấy nó đang bật và chuyển về Máy/Tổ được.
const LOAI_BUOC_ORDER: LsxLoaiBuoc[] = ["may", "to"];

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
  | "nhan_dien"
  | "so_luong"
  | "ai_lam"
  | "giao_nhan"
  | "vat_tu"
  | "phu_thuoc"
  | "thoi_gian"
  | "cau_hinh"
  | "phan_cong"
  | "tien_do";

type MainTab = "cau_hinh" | "phan_cong" | "vat_tu" | "tien_do" | "phu_thuoc" | "giao_nhan";

function normalizeTab(t?: TabKey): MainTab {
  if (!t) return "cau_hinh";
  if (t === "nhan_dien" || t === "so_luong" || t === "cau_hinh") return "cau_hinh";
  if (t === "ai_lam" || t === "phan_cong") return "phan_cong";
  if (t === "vat_tu") return "vat_tu";
  // Phụ thuộc DAG tách khỏi "Tiến độ & Thời gian" 18/08/2026: chọn tiền nhiệm là việc của người
  // xếp lịch, xem giờ chạy là việc của người lập kế hoạch — hai đầu việc khác nhau, cuộn qua nhau.
  if (t === "phu_thuoc") return "phu_thuoc";
  if (t === "thoi_gian" || t === "tien_do") return "tien_do";
  if (t === "giao_nhan") return "giao_nhan";
  return "cau_hinh";
}

export function LsxBuocDrawer({
  row,
  index,
  tong,
  laBuocGiao,
  soLuongDat,
  congDoanRefs,
  toRefs,
  mayRefs,
  khuonRefs,
  tenSanPham,
  onTaoKhuon,
  vatTuRefs,
  phuThuocRefs,
  baiGhep,
  // (`dvChuoi` vẫn là prop — nơi gọi vẫn truyền — nhưng thân drawer hiện KHÔNG đọc tới, nên bỏ
  //  khỏi destructure cho `tsc` sạch. Cần dùng lại thì thêm tên vào đây, không phải sửa kiểu.)
  canUpdate,
  onPatch,
  onPatchLsx,
  onDoiCongDoan,
  onDoiMay,
  onGiaoNhan,
  tabDau,
  onClose,
  onPrev,
  onNext,
}: {
  row: EditRow;
  index: number;
  tong: number;
  /** Bước này có phải BƯỚC GIAO KHÁCH không — bước cuối TRÊN DÒNG GIẤY, do bảng cha suy từ cả
   *  chuỗi (khớp backend `buoc[-1]`). KHÔNG suy từ `index === tong-1`: bước bản-kèm/CTP chèn giữa
   *  vẫn có thể đứng cuối bảng mà không giao khách. */
  laBuocGiao: boolean;
  soLuongDat: number;
  congDoanRefs: RefRow[] | null;
  toRefs: RefRow[] | null;
  mayRefs: RefRow[] | null;
  /** Dao chọn được của LỆNH này — server đã lọc theo khách. Lọc tiếp theo loại của bước làm ở
   *  `KhuonCuaBuoc`; danh sách tới đây chỉ còn vài dòng nên lọc ở màn là hợp lý, không phải
   *  "kéo cả bảng về rồi cắt". */
  khuonRefs: import("../api/client").KhuonChonDuoc[] | null;
  /** Tên sản phẩm của lệnh — mặc định cho tên dao mới (KHÔNG lấy tên bước). */
  tenSanPham: string;
  /** Tạo dao mới cho bước — trả id dao vừa tạo để gán luôn. */
  onTaoKhuon: (input: { ten: string; loai: string | null; ngay_ve: string }) => Promise<number>;
  vatTuRefs: RefRow[] | null;
  phuThuocRefs: import("../api/client").LsxPhuThuocOption[];
  /** Lệnh đang ghép chung tờ — bước in của nó do BÀI điều phối, khoá máy ở đây. */
  baiGhep: import("../api/client").LsxBaiGhep | null;
  /** Đơn vị bốn chặng của cả chuỗi (bảng routing suy ra bằng `donViChuoi`). Drawer chỉ thấy MỘT
   *  bước nên không tự suy được chặng thành phẩm — mà câu "số con sửa tại bài" cần đúng chặng đó. */
  dvChuoi: import("./lsxBuoc").DonViChuoi;
  canUpdate: boolean;
  onPatch: (p: Partial<EditRow>) => void;
  /** Sửa thẳng CẤP LỆNH — chỉ bước CUỐI dùng: SL thành phẩm cần giao (`so_luong_dat`). Cả chuỗi
   *  phía trên tính ngược lại từ số này. */
  onPatchLsx?: (p: { so_luong_dat?: number }) => void;
  /** Đổi công đoạn: kéo lại toàn bộ mặc định của công đoạn mới (giữ SL vào/ra). */
  onDoiCongDoan: (congDoanId: number | null) => void;
  /** Đổi máy: kíp đứng máy lấy theo danh mục Máy NGAY, rồi hỏi server thời lượng mới. Không đi
   *  qua `onPatch` vì hai số đó không nằm trong form — chúng tới từ máy vừa chọn. */
  onDoiMay: (mayId: number | null) => void;
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
  const [activeTab, setActiveTab] = useState<MainTab>(() => normalizeTab(tabDau));

  const ngoai = row.loai_buoc === "thue_ngoai";
  // Bước đang bị bài ghép ĐÈ: máy thật nằm ở bài. Cho sửa ở đây là cho sửa một ô vô tác dụng —
  // xếp lịch không đọc nó, thời lượng cũng tính theo máy của bài.
  const deLen = baiGhep?.buoc_bi_de?.[row.key] ?? null;
  const buocGhep = baiGhep && deLen ? baiGhep : null;
  const doiDonVi = !!row.don_vi_vao && !!row.don_vi_ra && row.don_vi_vao !== row.don_vi_ra;
  // Bước GIAO KHÁCH là chỗ DUY NHẤT còn gõ số: SL thành phẩm cần giao (`so_luong_dat`). Bảng cha
  // đã xác định bước nào giao khách (cuối dòng giấy, không phải cuối bảng) và truyền `laBuocGiao`.
  const laBuocCuoi = laBuocGiao && !!row.don_vi_ra;
  const [slRaCuoi, setSlRaCuoi] = useState(String(soLuongDat ?? 0));
  useEffect(() => setSlRaCuoi(String(soLuongDat ?? 0)), [soLuongDat]);

  // --- Sổ giao – nhận thực tế (bước thuê ngoài) --------------------------------------
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

  const dvNhan = (dv: string | null | undefined) => dvNhanChung(dv, row);
  // CÔNG THỨC số VÀO — nói rõ số từ đâu ra thay vì để người dùng đoán (bug cũ: "vào 9 · hao 2 → ra
  // 25" không khớp). CHỈ cho bước NGOÀI dòng giấy: số vào = ceil( (ra ÷ hệ số + hao cố định) ÷
  // (1 − hao%) ). Trên dòng giấy số suy ngược theo chuỗi giấy nên caption ở node RA nói thay.
  const flowFormula = useMemo(() => {
    if (row.loi_quy_doi || row.tren_dong_giay !== false) return null;
    const ra = Number(row.so_luong_ra || 0);
    const vao = Number(row.so_luong_vao || 0);
    const hs = Number(row.he_so_quy_doi || 1) || 1;
    const haoCd = Number(row.hao_hut || 0);
    const haoPct = Number(row.hao_hut_pct || 0);
    const dvV = dvNhan(row.don_vi_vao);
    const dvR = dvNhan(row.don_vi_ra);
    let expr = `${num(ra)} ${dvR}`;
    if (hs !== 1) expr += ` ÷ ${num(hs)}`;
    if (haoCd > 0) expr += ` + ${num(haoCd)} ${dvV} hao`;
    if (haoPct > 0) expr += ` ÷ (1 − ${haoPct}%)`;
    return { ket_qua: `${num(vao)} ${dvV}`, expr };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row]);
  const mayForm = mayRefs?.find((m) => m.id === row.may_id) ?? null;
  const t = useMemo(() => thoiLuong(row, mayForm), [row, mayForm]);
  const tg = useMemo(() => thoiLuongLive(row, mayForm), [row, mayForm]);
  // Máy chọn được LỌC theo "Máy làm được công đoạn này" khai ở danh mục Công đoạn (loai_may). Cùng
  // luật engine xếp lịch `_may_lam_duoc`: rỗng/không khai ⇒ nhận mọi máy; có khai ⇒ chỉ máy đúng
  // nhóm, NHƯNG vẫn GIỮ máy đang gán dù sai loại (dữ liệu cũ) để không âm thầm bỏ lựa chọn hiện có.
  const nhomMay = useMemo(() => {
    if (!mayRefs) return [];
    const allow =
      congDoanRefs?.find((c) => c.id === row.cong_doan_id)?.nhomMayChoPhep ?? null;
    if (!allow || allow.length === 0) return nhomMayTheoLoai(mayRefs);
    const loc = mayRefs.filter(
      (m) => (m.nhom != null && allow.includes(m.nhom)) || m.id === row.may_id,
    );
    return nhomMayTheoLoai(loc);
  }, [mayRefs, congDoanRefs, row.cong_doan_id, row.may_id]);

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
  // Số người bố trí có nằm trong biên định biên của bước không. Cảnh báo NGAY tại khối Nhân lực
  // chứ không đợi bàn xếp lịch: tới đó mới biết thì lệnh đã phát, sửa lại tốn một vòng.
  const nguoiBoTri = Math.max(1, Math.trunc(Number(row.so_nhan_cong)) || 1);
  const bienMin = row.so_nhan_cong_toi_thieu;
  const bienMax = row.so_nhan_cong_toi_da;
  const ngoaiBien =
    (bienMin != null && nguoiBoTri < bienMin) || (bienMax != null && nguoiBoTri > bienMax);
  const bienText = `${bienMin ?? "–"}–${bienMax ?? "–"}`;
  const khoanDaChon = dsKhoan.find((k) => k.id === row.khoan_rate_id);
  // "Nhảy tiền" khi đổi đầu việc: server tính sẵn tiền công của TỪNG lựa chọn cho đúng bước này
  // (`tien_du_kien`), nên chọn ở dropdown là ra số ngay — khỏi Lưu trước. Có key ⇒ option đến từ
  // server cho bước hiện tại; đổi tổ nạp lại danh sách KHÔNG kèm số ⇒ rơi về "Lưu công đoạn…".
  const khoanLive =
    khoanDaChon && "tien_du_kien" in khoanDaChon ? khoanDaChon : undefined;
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

  // ĐẦU VIỆC ĐÃ CHỌN SẴN thì cũng phải bung vật tư
  useEffect(() => {
    if (!canUpdate || row.khoan_rate_id == null || row.vat_tus.length > 0) return;
    const chon = dsKhoan.find((x) => x.id === row.khoan_rate_id);
    if (!chon?.vat_tus?.length) return;
    onPatch(bungVatTu(chon));
  }, [row.key, row.khoan_rate_id, dsKhoan]); // eslint-disable-line react-hooks/exhaustive-deps

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

  function bungVatTu(chon: (typeof dsKhoan)[number] | undefined): Partial<EditRow> {
    const giu = row.vat_tus.filter((v) => !v.tu_dong);
    const moi = (chon?.vat_tus ?? [])
      .filter((v) => !giu.some((g) => g.vat_tu_id === v.vat_tu_id))
      .map((v) => ({
        vat_tu_id: v.vat_tu_id,
        vat_tu_ma: v.ma,
        vat_tu_ten: v.ten,
        don_vi: v.don_vi,
        so_luong: String(v.so_luong),
        tu_dong: true,
      }));
    return { vat_tus: [...giu, ...moi] };
  }

  function chonDauViec(rawId: string) {
    const id = rawId ? Number(rawId) : null;
    const chon = dsKhoan.find((x) => x.id === id);
    onPatch({ khoan_rate_id: id, ...tuDinhMuc(chon), ...bungVatTu(chon) });
  }

  function doiLoaiBuoc(k: LsxLoaiBuoc) {
    if (k === "may") {
      // Bỏ định mức nhân lực của bảng khoán TỔ lại phía sau: bước máy nghe số người vận hành của
      // MÁY. Chưa gán máy thì tạm 1 người, chọn máy xong `onDoiMay` điền lại.
      const kip = Math.max(Math.trunc(Number(mayForm?.soNguoiVanHanh ?? 1)) || 1, 1);
      onPatch({
        loai_buoc: k,
        so_nhan_cong_tieu_chuan: kip,
        so_nhan_cong_toi_thieu: null,
        so_nhan_cong_toi_da: null,
        so_nhan_cong: String(kip),
      });
      return;
    }
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

  // Mở drawer từ badge trạng thái ngoài bảng/sơ đồ → nhảy thẳng tới tab đó
  useEffect(() => {
    if (tabDau) {
      setActiveTab(normalizeTab(tabDau));
    }
  }, [row.key, tabDau]);

  const setup = Number(tg.setup_phut ?? 0);
  const phatSinh = Number(tg.phat_sinh_phut ?? 0);
  const chayTB = Number(tg.chay_phut ?? 0);
  const coDai = Boolean(tg.co_dai_toc_do);
  const khoanChuanBi: { ten?: string; phut?: number }[] = Array.isArray(tg.chuan_bi_khoan)
    ? (tg.chuan_bi_khoan as { ten?: string; phut?: number }[])
    : [];
  const mayTen = mayDaChon?.ten ?? "";
  const chiemTB = Number(tg.chiem_tai_nguyen_phut ?? 0);
  const chiemMin = phatSinh + setup + Number(tg.chay_phut_min ?? chayTB);
  const chiemMax = phatSinh + setup + Number(tg.chay_phut_max ?? chayTB);

  // Danh sách Tab chính cho Drawer
  const tabsList = useMemo(() => {
    const list: { key: MainTab; label: string; badge?: number }[] = [
      { key: "cau_hinh", label: "Cấu hình & Số lượng" },
      { key: "phan_cong", label: "Phân công & Thiết bị" },
      { key: "vat_tu", label: "Vật tư", badge: row.vat_tus.length },
      { key: "tien_do", label: "Tiến độ & Thời gian" },
    ];
    if (ngoai) {
      list.push({ key: "giao_nhan", label: "Giao – nhận" });
    }
    // CUỐI hàng — badge đếm số bước tiền nhiệm đang chọn, đúng con số trước đây treo ở tab Tiến độ.
    list.push({ key: "phu_thuoc", label: "Phụ thuộc", badge: row.phu_thuoc_step_keys.length });
    return list;
  }, [ngoai, row.vat_tus.length, row.phu_thuoc_step_keys.length]);

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

          {/* Top Bar: Kicker + Type + Title + Nav actions */}
          <div className="khsx-drawer__head-main">
            <div className="khsx-drawer__head-info">
              <div className="khsx-drawer__head-meta">
                <span className="khsx-step-kicker">
                  BƯỚC {String(index + 1).padStart(2, "0")}/{String(tong).padStart(2, "0")}
                </span>
                <span className="khsx-dot-sep">·</span>
                <span className={`khsx-type-tag khsx-type-tag--${meta.tone}`}>
                  {meta.label}
                </span>
              </div>
              <h2
                className="khsx-drawer__title-main"
                id="khsx-buoc-title"
                tabIndex={-1}
                ref={titleRef}
              >
                {tenBuoc(row, congDoanRefs) || "Công đoạn chưa đặt tên"}
              </h2>
            </div>

            <div className="khsx-drawer__head-actions">
              <div className="khsx-nav-group" role="group" aria-label="Điều hướng bước">
                <button
                  type="button"
                  className="khsx-nav-btn"
                  onClick={onPrev}
                  disabled={index === 0}
                  aria-label="Bước trước"
                  title="Bước trước (←)"
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
                  title="Bước sau (→)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
              </div>

              <button
                type="button"
                className="khsx-close-btn"
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

          {/* Segmented Capsule Tabs Navigation */}
          <nav className="khsx-tabs-bar" aria-label="Phân đoạn nội dung">
            {tabsList.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`khsx-tab-btn ${activeTab === tab.key ? "is-active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
              >
                <span className="khsx-tab-label">{tab.label}</span>
                {tab.badge != null && tab.badge > 0 && (
                  <span className="khsx-tab-badge">{tab.badge}</span>
                )}
              </button>
            ))}
          </nav>
        </header>

        <div className="khsx-drawer__body">
          {/* =========================================================================
              TAB 1: CẤU HÌNH & SỐ LƯỢNG
             ========================================================================= */}
          {activeTab === "cau_hinh" && (
            <div className="khsx-tab-pane">
              {/* Khối Nhận diện */}
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Nhận diện công đoạn</h3>
                </div>

                <div className="khsx-nhan-dien-grid">
                  {/* Hàng 1 - Cột 1: Công đoạn */}
                  <label className="khsx-field">
                    <span className="khsx-field__label">TÊN CÔNG ĐOẠN</span>
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
                    <span className="khsx-field__label">LOẠI BƯỚC THỰC HIỆN</span>
                    <div className="khsx-seg-std" role="group" aria-label="Loại bước">
                      {(row.loai_buoc === "thue_ngoai"
                        ? [...LOAI_BUOC_ORDER, "thue_ngoai" as LsxLoaiBuoc]
                        : LOAI_BUOC_ORDER
                      ).map((k) => {
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
                    <span className="khsx-field__label">GHI CHÚ KỸ THUẬT CHO THỢ</span>
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
                    <span className="khsx-field__label">QUY ĐỊNH BẮT BUỘC</span>
                    <label className={`khsx-check-pill ${row.bat_buoc ? "is-checked" : ""}`}>
                      <input
                        type="checkbox"
                        checked={row.bat_buoc}
                        disabled={!canUpdate}
                        onChange={(e) => set("bat_buoc", e.target.checked)}
                      />
                      <span className="khsx-check-pill__text">
                        <strong>Bước bắt buộc</strong> (không được bỏ qua trong lệnh)
                      </span>
                    </label>
                  </div>
                </div>
              </section>

              {/* Khối Nhãn — gắn thẻ tự do cho bước (vd "Thuê ngoài", "Bế ngoài"). Logic y hệt gán
                  thẻ ở module Khách hàng: kho nhãn dùng chung, thêm/gỡ tức thì, xoá khỏi kho hỏi số
                  bước. Chỉ hiện khi bước ĐÃ LƯU (có id) — bước mới phải lưu công đoạn trước mới có
                  chỗ neo nhãn. */}
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Nhãn</h3>
                </div>
                {row.id != null ? (
                  <TagPicker buocLoai="lsx" buocId={row.id} canUpdate={canUpdate} />
                ) : (
                  <p className="khsx-hint-muted">
                    Lưu công đoạn trước rồi mở lại để gắn nhãn cho bước này.
                  </p>
                )}
              </section>

              {/* Khối Dòng chảy Số lượng (Production Flow Pipeline) */}
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Dòng chảy số lượng & hao hụt</h3>
                </div>

                {row.loi_quy_doi ? (
                  <div className="khsx-note-banner khsx-note-banner--error">
                    <span className="khsx-note-icon">⚠</span>
                    <span>
                      <strong>Chưa tính được số vào.</strong> {row.loi_quy_doi}{" "}
                      Khai cầu quy đổi ở module <strong>Đơn vị &amp; quy đổi</strong> rồi mở lại
                      bước — không có cầu thì lệnh không phát hành được.
                    </span>
                  </div>
                ) : row.tren_dong_giay === false ? (
                  <div className="khsx-note-banner">
                    <span>
                      Bước này <strong>không nằm trên dòng giấy</strong> (đếm bằng{" "}
                      {dvNhan(row.don_vi_vao)}) nên số vào suy từ số ra qua hệ số quy đổi + bù hao,
                      không tính ngược từ bước cuối.
                    </span>
                  </div>
                ) : null}

                <div className="khsx-flow-pipeline">
                  {/* Node Vào */}
                  <div className="khsx-flow-node khsx-flow-node--in">
                    <span className="khsx-flow-node__kicker">SỐ LƯỢNG VÀO</span>
                    <div className="khsx-flow-node__val-row">
                      <span className="khsx-flow-node__val">{num(Number(row.so_luong_vao || 0))}</span>
                      <span className="khsx-unit-pill">{dvNhan(row.don_vi_vao)}</span>
                    </div>
                    <span className="khsx-flow-node__hint">Đầu vào công đoạn</span>
                  </div>

                  {/* Connector Trung gian (Hao hụt & Quy đổi) */}
                  <div className="khsx-flow-connector">
                    <div className="khsx-flow-arrow-line">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M5 12h14M13 6l6 6-6 6" />
                      </svg>
                    </div>

                    <div className="khsx-flow-badges-stack">
                      <div className="khsx-flow-chip khsx-flow-chip--waste">
                        <span className="khsx-flow-chip__label">Hao hụt:</span>
                        <span className="khsx-flow-chip__val">
                          {Number(row.hao_hut || 0) > 0 || Number(row.hao_hut_pct || 0) > 0 ? (
                            <>
                              <strong>{num(Number(row.hao_hut))}</strong> {dvNhan(row.don_vi_vao)}
                              {Number(row.hao_hut_pct || 0) > 0 && ` (+${row.hao_hut_pct}%)`}
                            </>
                          ) : (
                            "—"
                          )}
                        </span>
                      </div>

                      {doiDonVi && heSoChu(Number(row.he_so_quy_doi || 1), row.don_vi_vao, row.don_vi_ra) && (
                        <div className="khsx-flow-chip khsx-flow-chip--ratio">
                          <span className="khsx-flow-chip__label">Quy đổi:</span>
                          <span className="khsx-flow-chip__val">
                            <strong>{heSoChu(Number(row.he_so_quy_doi || 1), row.don_vi_vao, row.don_vi_ra)}</strong>
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Node Ra */}
                  <div className={`khsx-flow-node khsx-flow-node--out ${laBuocCuoi ? "is-final" : ""}`}>
                    <div className="khsx-flow-node__head">
                      <span className="khsx-flow-node__kicker">SỐ LƯỢNG RA</span>
                      {laBuocCuoi && <span className="khsx-tag-final">Số giao</span>}
                    </div>

                    <div className="khsx-flow-node__val-row">
                      {laBuocCuoi ? (
                        <div className="khsx-flow-input-wrap">
                          <input
                            type="number"
                            min={1}
                            className="khsx-flow-editable-input"
                            value={slRaCuoi}
                            disabled={!canUpdate}
                            onChange={(e) => setSlRaCuoi(e.target.value)}
                            onBlur={() =>
                              onPatchLsx?.({ so_luong_dat: Math.max(0, Number(slRaCuoi) || 0) })
                            }
                          />
                          <span className="khsx-unit-pill">{dvNhan(row.don_vi_ra)}</span>
                        </div>
                      ) : (
                        <>
                          <span className="khsx-flow-node__val">{num(Number(row.so_luong_ra || 0))}</span>
                          <span className="khsx-unit-pill">{dvNhan(row.don_vi_ra)}</span>
                        </>
                      )}
                    </div>
                    <span className="khsx-flow-node__hint">
                      {laBuocCuoi
                        ? "Số thành phẩm giao khách"
                        : row.tren_dong_giay === false
                          ? "Theo công thức sản lượng của bước"
                          : "Tự động tính ngược từ bước cuối"}
                    </span>
                  </div>
                </div>

                {/* SỐ RA đến từ đâu — công thức sản lượng của công đoạn (chỉ bước ngoài dòng giấy).
                    Đặt TRÊN dòng "Số vào" vì với bước ngoài dòng, RA là gốc còn VÀO suy ngược từ nó. */}
                {row.san_luong_dien_giai && (
                  <div className="khsx-flow-formula">
                    <span className="khsx-flow-formula__label">Số ra =</span>
                    <span className="khsx-flow-formula__expr">{row.san_luong_dien_giai}</span>
                  </div>
                )}

                {flowFormula && (
                  <div className="khsx-flow-formula">
                    <span className="khsx-flow-formula__label">Số vào =</span>
                    <span className="khsx-flow-formula__expr">
                      {flowFormula.ket_qua}
                      <span className="khsx-flow-formula__eq"> = </span>
                      {flowFormula.expr}
                    </span>
                  </div>
                )}
              </section>
            </div>
          )}

          {/* =========================================================================
              TAB 2: PHÂN CÔNG & THIẾT BỊ
             ========================================================================= */}
          {activeTab === "phan_cong" && (
            <div className="khsx-tab-pane">
              {!ngoai ? (
                <div className="khsx-form-stack">
                  {/* Thẻ Tổ phụ trách */}
                  <section className="khsx-section-card">
                    <div className="khsx-section-card__head">
                      <h3 className="khsx-section-card__title">Tổ sản xuất & Máy thiết bị</h3>
                    </div>

                    <div className="khsx-assign-grid">
                      {/* TỔ PHỤ TRÁCH — CHỈ ĐỌC. Tổ khai một chỗ ở danh mục Công đoạn; drawer chỉ
                          bày lại, không cho đổi (chủ 22/08/2026). Đổi công đoạn ⇒ tổ tự theo. */}
                      <div className="khsx-field">
                        <span className="khsx-field__label">TỔ PHỤ TRÁCH</span>
                        <span className="khsx-val-text">
                          {(row.department_id != null
                            ? toRefs?.find((t2) => t2.id === row.department_id)?.ten
                            : null) ??
                            row.department_ten ??
                            "Theo mặc định của công đoạn"}
                        </span>
                        <span className="khsx-field__hint">
                          Khai ở danh mục Công đoạn — đổi tổ tại đó.
                        </span>
                      </div>

                      {/* Máy sản xuất (chỉ với bước MÁY) */}
                      {row.loai_buoc !== "to" && (
                        <label className="khsx-field">
                          <span className="khsx-field__label">MÁY SẢN XUẤT</span>
                          {buocGhep && deLen ? (
                            <div className="khsx-gang-box">
                              <span className="khsx-gang-box__title">
                                {deLen.may_ten ?? buocGhep.may_ten ?? "Chưa chọn ở bài"}
                              </span>
                              <span className="khsx-gang-box__hint">
                                Bước "{deLen.ten}" chạy chung ở bài <strong>{buocGhep.ma}</strong> (cấp {deLen.so_luong_vao.toLocaleString("vi-VN")} {dvNhanChung(row.don_vi_vao)}).
                              </span>
                            </div>
                          ) : mayRefs ? (
                            <select
                              className="khsx-select-std"
                              value={row.may_id ?? ""}
                              disabled={!canUpdate}
                              onChange={(e) =>
                                onDoiMay(e.target.value ? Number(e.target.value) : null)
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
                            <span className="khsx-val-text">—</span>
                          )}
                        </label>
                      )}
                    </div>
                  </section>

                  {/* Nhân lực của bước — MỘT khối chung cho cả bước Máy lẫn bước Tổ (21/08/2026).
                      Trước đây hai loại bước hở mỗi bên một nửa: bước máy chỉ có ô "kế hoạch" còn ba
                      mốc định biên để trống, bước tổ thì ngược lại — ba mốc hiện đủ mà con số kế
                      hoạch (đúng con số bàn xếp lịch dùng để cân quân số tổ) lại không có ô nào.
                      Hậu quả thật: một bước tổ đọng số 5 người từ đường ghi cũ, lịch báo quá tải mà
                      người khai không thấy 5 ở đâu để sửa. Nay cả hai loại cùng một hình — số bố trí
                      ở trên, ba mốc ở dưới — và bố trí ra ngoài biên thì nói ngay tại chỗ. */}
                  {(row.loai_buoc === "may" || row.loai_buoc === "to") && (
                    <section className="khsx-section-card">
                      <div className="khsx-section-card__head">
                        <h3 className="khsx-section-card__title">
                          {row.loai_buoc === "may" ? "Nhân sự vận hành máy" : "Nhân sự tổ làm tay"}
                        </h3>
                      </div>

                      <div className="khsx-labor-section">
                        <label className="khsx-field">
                          <span className="khsx-field__label">SỐ NGƯỜI BỐ TRÍ (KẾ HOẠCH)</span>
                          <div className="khsx-input-unit-combine">
                            <input
                              type="number"
                              min="1"
                              className="khsx-input-combine__num"
                              value={row.so_nhan_cong}
                              placeholder="1"
                              disabled={!canUpdate}
                              onChange={(e) => set("so_nhan_cong", e.target.value)}
                            />
                            <span className="khsx-input-combine__unit">người</span>
                          </div>
                          <span className="khsx-field__hint">
                            Bàn xếp lịch cân quân số tổ theo đúng số này.{" "}
                            {row.loai_buoc === "may"
                              ? "Nhân lực không thay đổi tốc độ máy."
                              : "Không đổi thời lượng bước — thời lượng chia theo số người tiêu chuẩn."}
                            {ngoaiBien && (
                              <strong className="khsx-labor-warn">
                                {" "}
                                Ngoài biên {bienText} người của bước.
                              </strong>
                            )}
                          </span>
                        </label>

                        {/* Biên nhân lực — nuôi cảnh báo thiếu/quá người khi xếp lịch, không vào thời gian. */}
                        <div className="khsx-labor-triplet-card">
                          <span className="khsx-field__label">BIÊN NHÂN LỰC (ĐỂ XẾP LỊCH)</span>
                          <div className="khsx-labor-triplet-grid">
                            {([
                              ["Tối thiểu", "so_nhan_cong_toi_thieu"],
                              ["Tiêu chuẩn", "so_nhan_cong_tieu_chuan"],
                              ["Tối đa", "so_nhan_cong_toi_da"],
                            ] as const).map(([nhan, khoa]) => (
                              <label className="khsx-labor-pill-input" key={khoa}>
                                <span className="khsx-labor-pill-label">{nhan}</span>
                                {row.loai_buoc === "may" ? (
                                  // Bước máy: kíp chuẩn là thông số của MÁY, sửa ở danh mục Máy để mọi
                                  // lệnh cùng ăn — hiện ở đây nhưng khoá, kèm lý do ở dòng gợi ý dưới.
                                  <span className="khsx-labor-num-field khsx-labor-num-field--ro">
                                    {row[khoa] ?? "—"}
                                  </span>
                                ) : (
                                  <input
                                    type="number"
                                    min="1"
                                    className="khsx-labor-num-field"
                                    value={row[khoa] ?? ""}
                                    placeholder="—"
                                    disabled={!canUpdate}
                                    onChange={(e) => {
                                      if (khoa === "so_nhan_cong_tieu_chuan") {
                                        const std =
                                          e.target.value === ""
                                            ? 1
                                            : Math.max(1, Number(e.target.value) || 1);
                                        const cu = Math.max(1, Number(row.so_nhan_cong_tieu_chuan) || 1);
                                        const kh = Math.max(1, Number(row.so_nhan_cong) || 1);
                                        // Kế hoạch đang bám kíp chuẩn ⇒ kéo theo cho khỏi lệch. Người
                                        // khai đã chỉnh tay số khác ⇒ giữ nguyên, không giẫm lên họ.
                                        onPatch(
                                          kh === cu
                                            ? { so_nhan_cong_tieu_chuan: std, so_nhan_cong: String(std) }
                                            : { so_nhan_cong_tieu_chuan: std },
                                        );
                                        return;
                                      }
                                      set(khoa, e.target.value === "" ? null : Number(e.target.value));
                                    }}
                                  />
                                )}
                                <span className="khsx-labor-unit">người</span>
                              </label>
                            ))}
                          </div>
                          <span className="khsx-field__hint">
                            {row.loai_buoc === "may" ? (
                              <>
                                Kíp tiêu chuẩn lấy từ danh mục Máy
                                {mayDaChon ? ` (${mayDaChon.ten})` : " — chọn máy ở khối trên"}; đổi ở đó
                                thì mọi lệnh cùng ăn. Máy chưa khai tối thiểu/tối đa nên để trống.
                              </>
                            ) : (
                              <>
                                Kíp tiêu chuẩn <strong>rút ngắn thời gian</strong>: năng suất khoán khai
                                theo đầu người nên kíp{" "}
                                {Math.max(1, Number(row.so_nhan_cong_tieu_chuan) || 1)} người làm nhanh gấp{" "}
                                {Math.max(1, Number(row.so_nhan_cong_tieu_chuan) || 1)}. Tối thiểu/tối đa
                                chỉ để bàn xếp lịch cảnh báo, không đổi thời lượng bước.
                              </>
                            )}
                          </span>
                        </div>
                      </div>
                    </section>
                  )}

                  {/* Thẻ Công việc khoán */}
                  {(row.khoan_chon_duoc.length > 0 || row.khoan_rate_id != null) && (
                    <section className="khsx-section-card">
                      <div className="khsx-section-card__head">
                        <h3 className="khsx-section-card__title">Đầu việc khoán lương thợ</h3>
                        <span className="khsx-tag-subtle">bảng khoán của tổ</span>
                      </div>

                      <div className="khsx-khoan-body">
                        <select
                          className="khsx-select-std"
                          value={row.khoan_rate_id ?? ""}
                          disabled={!canUpdate}
                          onChange={(e) => chonDauViec(e.target.value)}
                        >
                          <option value="">— chọn đầu việc khoán —</option>
                          {dsKhoan.map((k) => (
                            <option key={k.id} value={k.id}>
                              {k.don_vi
                                ? `${k.ten} — ${num(k.don_gia)} đ/${dvNhanChung(k.don_vi)}`
                                : k.ten}
                            </option>
                          ))}
                        </select>

                        <div className="khsx-khoan-status-row">
                          {khoanLive ? (
                            khoanLive.tien_du_kien != null ? (
                              <span className="khsx-pill-status khsx-pill-status--ok">
                                {khoanLive.dien_giai_du_kien ?? row.khoan_dien_giai}
                              </span>
                            ) : (
                              <span className="khsx-pill-status khsx-pill-status--error">
                                {khoanLive.dien_giai_du_kien ?? "Chưa quy đổi được sản lượng sang đơn vị đơn giá."}
                              </span>
                            )
                          ) : !khoanConKhop ? (
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
                    </section>
                  )}

                  {/* Thẻ Khuôn dao của bước */}
                  {row.requires_tooling && (
                    <KhuonCuaBuoc
                      row={row}
                      tenSanPham={tenSanPham}
                      khuonRefs={khuonRefs}
                      canUpdate={canUpdate}
                      onChon={(id) => set("khuon_be_id", id)}
                      onTaoMoi={onTaoKhuon}
                    />
                  )}
                </div>
              ) : (
                /* Tab phân công cho bước THUÊ NGOÀI */
                <div className="khsx-subcontract-stack">
                  <section className="khsx-section-card">
                    <div className="khsx-section-card__head">
                      <h3 className="khsx-section-card__title">Đối tác & Khối lượng gia công</h3>
                    </div>

                    <div className="khsx-subcontract-grid-full">
                      <label className="khsx-field">
                        <span className="khsx-field__label">NHÀ GIA CÔNG ĐỐI TÁC</span>
                        <input
                          className={`khsx-input-std ${!row.nha_cung_cap ? "khsx-input--bad" : ""}`}
                          value={row.nha_cung_cap}
                          disabled={!canUpdate}
                          placeholder="Nhập tên cơ sở / nhà máy gia công đối tác..."
                          onChange={(e) => set("nha_cung_cap", e.target.value)}
                        />
                      </label>

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
                    </div>
                  </section>

                  {/* Thẻ Lịch trình tiến độ gia công */}
                  <section className="khsx-section-card">
                    <div className="khsx-section-card__head">
                      <h3 className="khsx-section-card__title">Lịch trình tiến độ dự kiến</h3>
                      {canUpdate && ngayNhanGoiY && ngayNhanGoiY !== row.ngay_nhan_dk && (
                        <button
                          type="button"
                          className="khsx-btn-suggest-pill"
                          onClick={() => set("ngay_nhan_dk", ngayNhanGoiY)}
                        >
                          Áp dụng gợi ý: <strong>{ngayNhanGoiY}</strong>
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
                  </section>

                  {/* Đơn giá & Yêu cầu kỹ thuật */}
                  <section className="khsx-section-card">
                    <div className="khsx-section-card__head">
                      <h3 className="khsx-section-card__title">Đơn giá & Yêu cầu kỹ thuật</h3>
                    </div>

                    <div className="khsx-subcontract-grid-full">
                      <label className="khsx-field">
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

                      <label className="khsx-field">
                        <span className="khsx-field__label">YÊU CẦU KỸ THUẬT GỬI ĐỐI TÁC</span>
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
                  </section>

                  {/* Thẻ Khuôn dao của bước (nếu có) */}
                  {row.requires_tooling && (
                    <KhuonCuaBuoc
                      row={row}
                      tenSanPham={tenSanPham}
                      khuonRefs={khuonRefs}
                      canUpdate={canUpdate}
                      onChon={(id) => set("khuon_be_id", id)}
                      onTaoMoi={onTaoKhuon}
                    />
                  )}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 3: VẬT TƯ (BOM)
             ========================================================================= */}
          {activeTab === "vat_tu" && (
            <div className="khsx-tab-pane">
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <div>
                    <h3 className="khsx-section-card__title">Định mức vật tư tiêu hao (BOM)</h3>
                    <p className="khsx-section-card__sub">Nhu cầu vật tư riêng biệt của công đoạn này.</p>
                  </div>
                  <span className="khsx-badge-count">{row.vat_tus.length} vật tư</span>
                </div>

                {/* Cảnh báo quy đổi vật tư */}
                {(dsKhoan.find((x) => x.id === row.khoan_rate_id)?.canh_bao_vat_tu ?? []).map((c) => (
                  <div className="khsx-note-banner khsx-note-banner--warn" key={c}>
                    <span>{c}</span>
                  </div>
                ))}

                {/* Thanh Chỉ Số Mini & Nút Đồng Bộ Nhanh */}
                {row.vat_tus.length > 0 && (
                  <div className="khsx-vattu-metric-bar">
                    <div className="khsx-vattu-metric-chips">
                      <span className="khsx-vattu-metric-chip">
                        Tổng: <strong>{row.vat_tus.length}</strong>
                      </span>
                      <span className="khsx-vattu-metric-dot" />
                      <span className="khsx-vattu-metric-chip">
                        Tự tính: <strong>{row.vat_tus.filter((v) => v.tu_dong).length}</strong>
                      </span>
                      <span className="khsx-vattu-metric-dot" />
                      <span className="khsx-vattu-metric-chip">
                        Đã sửa: <strong>{row.vat_tus.filter((v) => !v.tu_dong).length}</strong>
                      </span>
                    </div>

                    {canUpdate &&
                      row.vat_tus.some((v) => {
                        const g = row.vat_tu_goi_y.find((x) => x.vat_tu_id === v.vat_tu_id);
                        return (
                          g?.so_luong != null &&
                          (!v.tu_dong || Math.abs(g.so_luong - Number(v.so_luong)) > 0.0005)
                        );
                      }) && (
                        <button
                          type="button"
                          className="khsx-vattu-sync-all-btn"
                          title="Cập nhật toàn bộ số lượng theo công thức định mức"
                          onClick={() => {
                            set(
                              "vat_tus",
                              row.vat_tus.map((v) => {
                                const g = row.vat_tu_goi_y.find((x) => x.vat_tu_id === v.vat_tu_id);
                                return g?.so_luong != null
                                  ? { ...v, so_luong: String(g.so_luong), tu_dong: true }
                                  : v;
                              }),
                            );
                          }}
                        >
                          Đồng bộ tất cả theo công thức
                        </button>
                      )}
                  </div>
                )}

                {/* Bảng Kỹ Thuật Data Table */}
                <div className="khsx-vattu-table-wrap">
                  <table className="khsx-vattu-table">
                    <thead className="khsx-vattu-thead">
                      <tr>
                        <th className="khsx-vattu-th" style={{ width: "28%" }}>VẬT TƯ & QUY CÁCH</th>
                        <th className="khsx-vattu-th" style={{ width: "36%" }}>DIỄN GIẢI CÔNG THỨC</th>
                        <th className="khsx-vattu-th" style={{ width: "12%" }}>NGUỒN SỐ</th>
                        <th className="khsx-vattu-th" style={{ width: "18%", textAlign: "right" }}>ĐỊNH MỨC TIÊU HAO</th>
                        <th className="khsx-vattu-th" style={{ width: "6%", textAlign: "center" }}></th>
                      </tr>
                    </thead>
                    <tbody className="khsx-vattu-tbody">
                      {row.vat_tus.length === 0 ? (
                        <tr className="khsx-vattu-tr">
                          <td colSpan={5} className="khsx-vattu-td" style={{ textAlign: "center", color: "#94a3b8", padding: "20px" }}>
                            Chưa có vật tư tiêu hao cho công đoạn này.
                          </td>
                        </tr>
                      ) : (
                        row.vat_tus.map((v, i) => {
                          const goiY = row.vat_tu_goi_y.find((g) => g.vat_tu_id === v.vat_tu_id);
                          const soMay = goiY?.so_luong ?? null;
                          const soLuu = v.so_luong.trim() === "" ? null : Number(v.so_luong);
                          const lech =
                            soMay !== null &&
                            soLuu !== null &&
                            Number.isFinite(soLuu) &&
                            Math.abs(soMay - soLuu) > 0.0005;
                          return (
                            <tr className="khsx-vattu-tr" key={v.vat_tu_id}>
                              <td className="khsx-vattu-td khsx-vattu-td--info">
                                <div className="khsx-vattu-cell-name">
                                  <span className="khsx-vattu-code">{v.vat_tu_ma}</span>
                                  <span className="khsx-vattu-name">{v.vat_tu_ten}</span>
                                </div>
                              </td>
                              <td className="khsx-vattu-td khsx-vattu-td--why">
                                {goiY?.dien_giai ? (
                                  <div className="khsx-formula-wrap">
                                    <code className="khsx-formula-code">{goiY.dien_giai}</code>
                                    {lech && (
                                      <div className="khsx-diff-badge">
                                        <span>Lệch: {num(soMay as number)} {nhanDonVi(v.don_vi)}</span>
                                        {canUpdate && (
                                          <button
                                            type="button"
                                            className="khsx-vattu-fix-btn"
                                            onClick={() =>
                                              set(
                                                "vat_tus",
                                                row.vat_tus.map((x, j) =>
                                                  j === i
                                                    ? { ...x, so_luong: String(soMay), tu_dong: true }
                                                    : x,
                                                ),
                                              )
                                            }
                                          >
                                            Dùng số này
                                          </button>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span className="khsx-vattu-no-formula">
                                    Chưa tự tính được — {goiY?.ly_do ?? "chưa có công thức lượng."}
                                  </span>
                                )}
                              </td>
                              <td className="khsx-vattu-td khsx-vattu-td--status">
                                <span className={`khsx-vattu-src-badge ${v.tu_dong ? "is-auto" : "is-manual"}`}>
                                  {v.tu_dong ? "Tự tính" : "Đã sửa"}
                                </span>
                              </td>
                              <td className="khsx-vattu-td khsx-vattu-td--input">
                                <div className="khsx-vattu-input-group">
                                  <input
                                    type="number"
                                    min="0.001"
                                    step="any"
                                    className="khsx-vattu-num-input"
                                    value={v.so_luong}
                                    placeholder="0"
                                    disabled={!canUpdate}
                                    onChange={(e) =>
                                      set(
                                        "vat_tus",
                                        row.vat_tus.map((x, j) =>
                                          j === i ? { ...x, so_luong: e.target.value, tu_dong: false } : x,
                                        ),
                                      )
                                    }
                                  />
                                  <span className="khsx-vattu-unit-tag">{nhanDonVi(v.don_vi)}</span>
                                </div>
                              </td>
                              <td className="khsx-vattu-td khsx-vattu-td--action" style={{ textAlign: "center" }}>
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
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                    {canUpdate && vatTuRefs && (
                      <tfoot className="khsx-vattu-tfoot">
                        <tr>
                          <td colSpan={5} className="khsx-vattu-td-add">
                            <div className="khsx-vattu-add-bar">
                              <span className="khsx-vattu-add-icon">＋</span>
                              <select
                                className="khsx-vattu-select-clean"
                                value=""
                                onChange={(e) => {
                                  const item = vatTuRefs.find((v) => v.id === Number(e.target.value));
                                  if (item && !row.vat_tus.some((v) => v.vat_tu_id === item.id)) {
                                    const goiY = row.vat_tu_goi_y.find((g) => g.vat_tu_id === item.id);
                                    set("vat_tus", [
                                      ...row.vat_tus,
                                      {
                                        vat_tu_id: item.id,
                                        vat_tu_ma: item.ma ?? "",
                                        vat_tu_ten: item.ten,
                                        don_vi: item.donVi ?? "",
                                        so_luong: goiY?.so_luong != null ? String(goiY.so_luong) : "",
                                        tu_dong: false,
                                      },
                                    ]);
                                  }
                                }}
                              >
                                <option value="">— Thêm vật tư vào công đoạn —</option>
                                {vatTuRefs
                                  .filter((x) => !row.vat_tus.some((v) => v.vat_tu_id === x.id))
                                  .map((x) => (
                                    <option key={x.id} value={x.id}>
                                      {x.ma} · {x.ten} ({nhanDonVi(x.donVi)})
                                    </option>
                                  ))}
                              </select>
                            </div>
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </section>
            </div>
          )}

          {/* =========================================================================
              TAB 4: TIẾN ĐỘ & THỜI GIAN
             ========================================================================= */}
          {/* =========================================================================
              TAB CUỐI: PHỤ THUỘC XẾP LỊCH (DAG)
             ========================================================================= */}
          {activeTab === "phu_thuoc" && (
            <div className="khsx-tab-pane">
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <div>
                    <h3 className="khsx-section-card__title">Phụ thuộc xếp lịch (DAG)</h3>
                    <p className="khsx-section-card__sub">
                      Bước này chỉ bắt đầu sau khi các bước tiền nhiệm hoàn thành.
                    </p>
                  </div>
                </div>

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
                              <span className="khsx-dag-chip__text">{o.ten_buoc}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                  {nhomPhuThuoc.length === 0 && (
                    <span className="khsx-field__hint">Chưa có bước khác trong đơn hàng để tạo phụ thuộc.</span>
                  )}
                </div>
              </section>
            </div>
          )}

          {activeTab === "tien_do" && (
            <div className="khsx-tab-pane">
              {/* Card 1: Tham số vận hành & Phát sinh */}
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Tham số vận hành & phát sinh</h3>
                </div>

                <div className="khsx-thoi-gian-grid">
                  {row.loai_buoc === "may" ? (
                    <div className="khsx-field">
                      <span className="khsx-field__label">SỐ LƯỢT CHẠY QUA MÁY</span>
                      <div className="khsx-turns-control">
                        <div className="khsx-turns-presets" role="group" aria-label="Số lượt chạy">
                          <button
                            type="button"
                            className={`khsx-turn-btn ${row.so_luot_chay === "1" || !row.so_luot_chay ? "is-active" : ""}`}
                            disabled={!canUpdate}
                            onClick={() => set("so_luot_chay", "1")}
                          >
                            1 lượt
                          </button>
                          <button
                            type="button"
                            className={`khsx-turn-btn ${row.so_luot_chay === "2" ? "is-active" : ""}`}
                            disabled={!canUpdate}
                            onClick={() => set("so_luot_chay", "2")}
                          >
                            2 lượt (In trở)
                          </button>
                        </div>
                        <div className="khsx-input-unit-combine khsx-turns-custom">
                          <input
                            type="number"
                            min="1"
                            className="khsx-input-combine__num"
                            value={row.so_luot_chay}
                            placeholder="1"
                            disabled={!canUpdate}
                            onChange={(e) => set("so_luot_chay", e.target.value)}
                          />
                          <span className="khsx-input-combine__unit">lượt</span>
                        </div>
                      </div>
                      <span className="khsx-field__hint">In trở 2 mặt = 2 lượt qua máy</span>
                    </div>
                  ) : (
                    <div className="khsx-field" />
                  )}

                  <div className="khsx-field">
                    <span className="khsx-field__label">THỜI GIAN PHÁT SINH / KHÁC</span>
                    <div className="khsx-extra-time-control">
                      <div className="khsx-input-unit-combine">
                        <input
                          type="number"
                          min="0"
                          className="khsx-input-combine__num"
                          value={row.phat_sinh_phut}
                          placeholder="0"
                          disabled={!canUpdate}
                          onChange={(e) => set("phat_sinh_phut", Math.max(0, Number(e.target.value) || 0).toString())}
                        />
                        <span className="khsx-input-combine__unit">phút</span>
                      </div>
                      {canUpdate && (
                        <div className="khsx-quick-presets">
                          <button
                            type="button"
                            className="khsx-preset-btn"
                            title="Thêm 15 phút"
                            onClick={() => set("phat_sinh_phut", (Number(row.phat_sinh_phut || 0) + 15).toString())}
                          >
                            +15′
                          </button>
                          <button
                            type="button"
                            className="khsx-preset-btn"
                            title="Thêm 30 phút"
                            onClick={() => set("phat_sinh_phut", (Number(row.phat_sinh_phut || 0) + 30).toString())}
                          >
                            +30′
                          </button>
                          {Number(row.phat_sinh_phut || 0) > 0 && (
                            <button
                              type="button"
                              className="khsx-preset-btn khsx-preset-btn--reset"
                              title="Đặt lại 0 phút"
                              onClick={() => set("phat_sinh_phut", "0")}
                            >
                              Xóa
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    <span className="khsx-field__hint">Cộng thẳng vào giờ máy</span>
                  </div>
                </div>
              </section>

              {/* Card 2: Bóc tách thời gian & Tiến độ */}
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Bóc tách thời gian & tiến độ</h3>
                </div>

                {Array.isArray(tg.canh_bao) &&
                  tg.canh_bao.map((warning) => (
                    <div className="khsx-alert" key={String(warning)}>
                      {String(warning)}
                    </div>
                  ))}

                {/* Mini Timeline Tỷ trọng (Proportion Bar) */}
                {chiemTB > 0 && (
                  <div className="khsx-proportion-wrap">
                    <div className="khsx-proportion-bar">
                      {setup > 0 && (
                        <div
                          className="khsx-proportion-seg khsx-proportion-seg--amber"
                          style={{ width: `${Math.max(2, (setup / chiemTB) * 100)}%` }}
                          title={`Chuẩn bị: ${num(setup)}' (${((setup / chiemTB) * 100).toFixed(1)}%)`}
                        />
                      )}
                      {chayTB > 0 && (
                        <div
                          className="khsx-proportion-seg khsx-proportion-seg--moss"
                          style={{ width: `${Math.max(2, (chayTB / chiemTB) * 100)}%` }}
                          title={`Chạy máy: ${num(chayTB)}' (${((chayTB / chiemTB) * 100).toFixed(1)}%)`}
                        />
                      )}
                      {phatSinh > 0 && (
                        <div
                          className="khsx-proportion-seg khsx-proportion-seg--plum"
                          style={{ width: `${Math.max(2, (phatSinh / chiemTB) * 100)}%` }}
                          title={`Phát sinh: ${num(phatSinh)}' (${((phatSinh / chiemTB) * 100).toFixed(1)}%)`}
                        />
                      )}
                    </div>
                    <div className="khsx-proportion-legend">
                      <span className="khsx-legend-tag khsx-legend-tag--amber">
                        <span className="khsx-legend-bullet" />
                        Chuẩn bị: <b>{num(setup)}′</b> ({((setup / chiemTB) * 100).toFixed(1)}%)
                      </span>
                      <span className="khsx-legend-tag khsx-legend-tag--moss">
                        <span className="khsx-legend-bullet" />
                        Chạy máy: <b>{num(chayTB)}′</b> ({((chayTB / chiemTB) * 100).toFixed(1)}%)
                      </span>
                      {phatSinh > 0 && (
                        <span className="khsx-legend-tag khsx-legend-tag--plum">
                          <span className="khsx-legend-bullet" />
                          Phát sinh: <b>{num(phatSinh)}′</b> ({((phatSinh / chiemTB) * 100).toFixed(1)}%)
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Danh sách bóc tách giai đoạn */}
                <div className="khsx-time-list">
                  {/* GIAI ĐOẠN 1: Chuẩn bị máy */}
                  <div className="khsx-time-stage-card khsx-time-stage-card--amber">
                    <div className="khsx-time-stage-card__head">
                      <div className="khsx-time-stage-card__title-group">
                        <div className="khsx-time-stage-card__title-row">
                          <span className="khsx-time-tag khsx-time-tag--amber">Chuẩn bị</span>
                          <span className="khsx-time-stage-card__title">Chuẩn bị &amp; căn chỉnh</span>
                        </div>
                        <span className="khsx-time-stage-card__device-chip">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="2" y="6" width="20" height="12" rx="2" />
                            <circle cx="12" cy="12" r="2" />
                            <path d="M6 12h.01M18 12h.01" />
                          </svg>
                          {mayTen
                            ? (mayTen.toLowerCase().startsWith("máy") ? mayTen : `Máy ${mayTen}`)
                            : (row.loai_buoc === "to" && khoanDaChon ? khoanDaChon.ten : "Chưa gán máy")}
                        </span>
                      </div>

                      <div className="khsx-time-stage-card__stat">
                        <div className="khsx-time-stage-card__stat-main">
                          <span className="khsx-time-stage-card__stat-num khsx-time-stage-card__stat-num--amber">
                            {num(setup)}′
                          </span>
                          <span className="khsx-time-stage-card__stat-hours">({phut(setup)})</span>
                        </div>
                        {chiemTB > 0 && (
                          <span className="khsx-time-stage-card__stat-ratio">
                            Tỷ trọng: <b>{((setup / chiemTB) * 100).toFixed(1)}%</b>
                          </span>
                        )}
                      </div>
                    </div>

                    {khoanChuanBi.length > 0 && (
                      <div className="khsx-subtask-container">
                        <div className="khsx-subtask-chips">
                          {khoanChuanBi.map((k, i) => (
                            <span key={`${k.ten}-${i}`} className="khsx-subtask-chip">
                              <span className="khsx-subtask-chip__name">{k.ten || "—"}</span>
                              <b className="khsx-subtask-chip__val">{num(k.phut)}′</b>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* GIAI ĐOẠN 2: Chạy máy sản xuất */}
                  <div className="khsx-time-stage-card khsx-time-stage-card--moss">
                    <div className="khsx-time-stage-card__head">
                      <div className="khsx-time-stage-card__title-group">
                        <div className="khsx-time-stage-card__title-row">
                          <span className="khsx-time-tag khsx-time-tag--moss">Chạy máy</span>
                          <span className="khsx-time-stage-card__title">Thời gian chạy sản xuất</span>
                        </div>
                      </div>

                      <div className="khsx-time-stage-card__stat">
                        <div className="khsx-time-stage-card__stat-main">
                          <span className="khsx-time-stage-card__stat-num khsx-time-stage-card__stat-num--moss">
                            {num(chayTB)}′
                          </span>
                          <span className="khsx-time-stage-card__stat-hours">({phut(chayTB)})</span>
                        </div>
                        {chiemTB > 0 && (
                          <span className="khsx-time-stage-card__stat-ratio">
                            Tỷ trọng: <b>{((chayTB / chiemTB) * 100).toFixed(1)}%</b>
                          </span>
                        )}
                      </div>
                    </div>

                    {Number(tg.nang_suat_hieu_dung ?? 0) > 0 && tg.phuong_phap !== "chua_quy_doi" && (
                      <div style={{ padding: "0 16px 14px", background: "#ffffff" }}>
                        <div className="khsx-time-row__formula-card" style={{ marginTop: 0 }}>
                          <div className="khsx-formula-compact">
                            <span className="khsx-formula-token khsx-formula-token--qty">
                              {tg.quy_doi_dien_giai ? String(tg.quy_doi_dien_giai) : `${num(Number(tg.so_luong_vao ?? 0))} ${String(tg.don_vi_vao ?? "")}`}
                            </span>
                            <span className="khsx-formula-op">÷</span>
                            {row.loai_buoc === "to" && Number(tg.so_nhan_cong_tinh ?? 1) > 1 ? (
                              // Bày rõ phép nhân kíp chuẩn: gộp cả cụm vào MỘT mẫu số trong ngoặc để
                              // đọc đúng thứ tự (SL ÷ (năng suất × người)), không đọc thành ÷ rồi ×.
                              <span className="khsx-formula-token khsx-formula-token--speed">
                                ({num(Number(tg.nang_suat_co_so ?? 0))}/giờ × {Number(tg.so_nhan_cong_tinh ?? 1)} người)
                              </span>
                            ) : (
                              <span className="khsx-formula-token khsx-formula-token--speed">
                                {num(Number(tg.nang_suat_hieu_dung ?? 0))}/giờ
                              </span>
                            )}
                            {row.loai_buoc === "may" && Number(tg.so_luot_chay ?? 1) !== 1 && (
                              <>
                                <span className="khsx-formula-op">×</span>
                                <span className="khsx-formula-token khsx-formula-token--turns">
                                  {Number(tg.so_luot_chay ?? 1)} lượt
                                </span>
                              </>
                            )}
                            <span className="khsx-formula-op">=</span>
                            <span className="khsx-formula-token khsx-formula-token--result">
                              {phut(Number(tg.chay_phut ?? 0))}
                            </span>
                          </div>
                          <span className="khsx-time-row__src">
                            Nguồn tính: {row.loai_buoc === "may" ? (mayDaChon ? mayDaChon.ten : "Chưa gán máy") : (khoanDaChon ? khoanDaChon.ten : "Đầu việc khoán")}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Khoản Phát sinh - Plum (nếu có) */}
                  {phatSinh > 0 && (
                    <div className="khsx-time-row khsx-time-row--plum">
                      <div className="khsx-time-row__main">
                        <div className="khsx-time-row__title-group">
                          <span className="khsx-time-tag khsx-time-tag--plum">Phát sinh</span>
                          <span className="khsx-time-row__label">Thời gian phát sinh ngoài định mức</span>
                        </div>
                        <span className="khsx-time-row__val khsx-time-row__val--plum">
                          {num(phatSinh)}′ <span className="khsx-time-row__val-sub">({phut(phatSinh)})</span>
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Dải dung sai tốc độ máy (Speed Spectrum Bar) */}
                  {coDai ? (
                    <div className="khsx-tolerance-line">
                      <div className="khsx-tolerance-line__head">
                        <span className="khsx-tolerance-title">Biên độ tốc độ máy (Min — Max)</span>
                        <span className="khsx-tolerance-target">
                          Kế hoạch Gantt: <b>{phut(chiemTB)}</b>
                        </span>
                      </div>
                      <div className="khsx-tolerance-line__bar">
                        <div className="khsx-tolerance-node khsx-tolerance-node--fast">
                          <span className="khsx-tolerance-node__kicker">Nhanh nhất</span>
                          <b className="khsx-tolerance-node__val">{phut(chiemMin)}</b>
                        </div>
                        <div className="khsx-tolerance-line__track">
                          <div className="khsx-tolerance-line__point" title={`Kế hoạch: ${phut(chiemTB)}`}>
                            <span className="khsx-tolerance-line__pin" />
                          </div>
                        </div>
                        <div className="khsx-tolerance-node khsx-tolerance-node--slow">
                          <span className="khsx-tolerance-node__kicker">Chậm nhất</span>
                          <b className="khsx-tolerance-node__val">{phut(chiemMax)}</b>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="khsx-tolerance-empty">
                      {row.loai_buoc === "to"
                        ? "Đầu việc chưa khai năng suất tối thiểu / tối đa nên chưa có khoảng nhanh–chậm."
                        : "Máy chưa khai tốc độ tối thiểu / tối đa nên chưa có khoảng nhanh–chậm."}
                    </div>
                  )}
                </div>

                {/* Dải chỉ số tổng hợp (Hero KPI Strip theo §4 UI_DESIGN.md) */}
                <div className="khsx-compact-kpi-strip">
                  <div className="khsx-compact-kpi-cell khsx-compact-kpi-cell--rust">
                    <div className="khsx-compact-kpi-header">
                      <span className="khsx-compact-kpi-icon">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="12" cy="12" r="10" />
                          <polyline points="12 6 12 12 16 14" />
                        </svg>
                      </span>
                      <span className="khsx-compact-kpi-label">Thời gian chiếm máy (Gantt)</span>
                    </div>
                    <div className="khsx-compact-kpi-val-group">
                      <span className="khsx-compact-kpi-val">{phut(t.chiemMay)}</span>
                      {t.chiemMay >= 60 && (
                        <span className="khsx-compact-kpi-pill">
                          ≈ {(t.chiemMay / 60 / 24).toFixed(1)} ngày lịch
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="khsx-compact-kpi-cell">
                    <div className="khsx-compact-kpi-header">
                      <span className="khsx-compact-kpi-icon">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                      </span>
                      <span className="khsx-compact-kpi-label">Tổng thời gian hoàn thành</span>
                    </div>
                    <div className="khsx-compact-kpi-val-group">
                      <span className="khsx-compact-kpi-val">{phut(t.tong)}</span>
                      <span className={`khsx-compact-kpi-sub ${t.tong !== t.chiemMay ? "is-waiting" : "is-immediate"}`}>
                        {t.tong !== t.chiemMay ? `Gồm ${phut(t.tong - t.chiemMay)} chờ` : "Bắt đầu bước sau ngay"}
                      </span>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          )}

          {/* =========================================================================
              TAB 5: THỰC TẾ GIAO – NHẬN (chỉ bước thuê ngoài)
             ========================================================================= */}
          {activeTab === "giao_nhan" && ngoai && (
            <div className="khsx-tab-pane">
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Sổ theo dõi giao – nhận thực tế</h3>
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
                </div>

                <div className="khsx-gn">
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
              </section>
            </div>
          )}
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

/** Ba MỨC của tình trạng dao */
function nhomTinhTrang(tt: string | null | undefined): "san" | "cho" | "hong" {
  if (tt === "hong" || tt === "thanh_ly") return "hong";
  if (tt === "dang_dat_lam") return "cho";
  return "san";
}

/** Một câu trả lời trọn vẹn cho "dao này dùng được chưa, lấy ở đâu". */
function moTaTinhTrang(dao: { so_ke?: string | null; tinh_trang?: string;
                              ngay_ve_du_kien?: string | null } | null): string {
  if (!dao) return "Chưa nạp được thông tin khuôn — bấm Làm mới ở đầu màn.";
  switch (dao.tinh_trang) {
    case "dang_dat_lam":
      return dao.ngay_ve_du_kien
        ? `Đang làm — dự kiến có ngày ${ngayVN(dao.ngay_ve_du_kien)}. Bước này chưa chạy được.`
        : "Đang làm — chưa có ngày dự kiến. Bước này chưa chạy được.";
    case "hong":
      return "Khuôn HỎNG — không dùng được. Chọn con khác hoặc làm khuôn mới.";
    case "thanh_ly":
      return "Khuôn ĐÃ THANH LÝ — không còn trong kho. Chọn con khác hoặc làm khuôn mới.";
    default:
      return dao.so_ke ? `Có sẵn — lấy tại ${dao.so_ke}` : "Có sẵn — chưa khai số kệ";
  }
}

function ngayVN(s: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
}

/** Khối KHUÔN của một bước */
function KhuonCuaBuoc({
  row,
  tenSanPham,
  khuonRefs,
  canUpdate,
  onChon,
  onTaoMoi,
}: {
  row: EditRow;
  tenSanPham: string;
  khuonRefs: import("../api/client").KhuonChonDuoc[] | null;
  canUpdate: boolean;
  onChon: (id: number | null) => void;
  onTaoMoi: (input: { ten: string; loai: string | null; ngay_ve: string }) => Promise<number>;
}) {
  const [moTaoMoi, setMoTaoMoi] = useState(false);
  const [tenMoi, setTenMoi] = useState("");
  const [ngayVe, setNgayVe] = useState("");
  const [dangTao, setDangTao] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const nhanLoai = row.tooling_type === "khuon_ep" ? "khuôn ép nhũ / dập nổi" : "khuôn bế";

  const chonDuoc = useMemo(() => {
    const ds = khuonRefs ?? [];
    return ds.filter((k) => !row.tooling_type || !k.loai || k.loai === row.tooling_type);
  }, [khuonRefs, row.tooling_type]);

  const dao = useMemo(() => {
    if (row.khuon_be_id == null) return null;
    const trong = (khuonRefs ?? []).find((k) => k.id === row.khuon_be_id);
    if (trong) return trong;
    if (!row.khuon_be_ma && !row.khuon_be_ten) return null;
    return {
      id: row.khuon_be_id,
      ma: row.khuon_be_ma ?? `#${row.khuon_be_id}`,
      ten: row.khuon_be_ten ?? "",
      loai: row.tooling_type,
      so_ke: row.khuon_be_so_ke,
      tinh_trang: row.khuon_be_tinh_trang ?? "",
      ngay_ve_du_kien: row.khuon_be_ngay_ve,
    };
  }, [row, khuonRefs]);

  const daChon = row.khuon_be_id != null;

  async function taoMoi() {
    const ten = tenMoi.trim();
    if (!ten || !ngayVe) {
      setLoi("Cần tên khuôn và ngày cần có.");
      return;
    }
    setDangTao(true);
    setLoi(null);
    try {
      onChon(await onTaoMoi({ ten, loai: row.tooling_type, ngay_ve: ngayVe }));
      setMoTaoMoi(false);
      setTenMoi("");
      setNgayVe("");
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không tạo được khuôn.");
    } finally {
      setDangTao(false);
    }
  }

  return (
    <section className="khsx-section-card">
      <div className="khsx-section-card__head">
        <h3 className="khsx-section-card__title">Khuôn của bước ({nhanLoai})</h3>
      </div>

      {daChon ? (
        <div className="khsx-khuon__da-chon">
          <div className="khsx-khuon__hang1">
            <span className="khsx-khuon__ma">{dao?.ma ?? `#${row.khuon_be_id}`}</span>
            <span className="khsx-khuon__ten">{dao?.ten || "—"}</span>
            {canUpdate && (
              <button type="button" className="khsx-khuon__bo" onClick={() => onChon(null)}>
                Bỏ chọn
              </button>
            )}
          </div>
          <span className={`khsx-khuon__tt khsx-khuon__tt--${nhomTinhTrang(dao?.tinh_trang)}`}>
            {moTaTinhTrang(dao)}
          </span>
        </div>
      ) : !canUpdate ? (
        <span className="khsx-val-text">Chưa gán khuôn</span>
      ) : moTaoMoi ? (
        <div className="khsx-khuon__form">
          <label className="khsx-field">
            <span className="khsx-field__label">Tên khuôn</span>
            <input
              className="khsx-input-std"
              value={tenMoi}
              onChange={(e) => setTenMoi(e.target.value)}
              placeholder="vd: Hộp bánh trung thu 20×20"
              autoFocus
            />
          </label>
          <label className="khsx-field">
            <span className="khsx-field__label">Ngày có khuôn (dự kiến)</span>
            <input
              type="date"
              className="khsx-input-std"
              value={ngayVe}
              onChange={(e) => setNgayVe(e.target.value)}
            />
            <span className="khsx-field__hint">
              Thuê ngoài thì là ngày về; xưởng tự làm thì là ngày làm xong.
            </span>
          </label>
          <div className="khsx-khuon__form-nut">
            <Button variant="primary" onClick={taoMoi} loading={dangTao}>Tạo khuôn</Button>
            <Button variant="ghost" onClick={() => { setMoTaoMoi(false); setLoi(null); }}>Huỷ</Button>
          </div>
          {loi && <div className="khsx-alert" role="alert">{loi}</div>}
          <span className="khsx-field__hint">
            Khuôn mới vào kho ở tình trạng <b>đang đặt làm</b>. Có dao trong tay thì vào màn Khuôn
            đổi tình trạng — mọi lệnh đang chờ nó tự cập nhật.
          </span>
        </div>
      ) : (
        <div className="khsx-khuon__chon">
          <select
            className="khsx-select-std"
            value=""
            onChange={(e) => e.target.value && onChon(Number(e.target.value))}
            aria-label={`Chọn ${nhanLoai} có sẵn`}
          >
            <option value="">
              {chonDuoc.length > 0
                ? `— chọn ${nhanLoai} có sẵn (${chonDuoc.length}) —`
                : `— khách này chưa có ${nhanLoai} nào —`}
            </option>
            {chonDuoc.map((k) => (
              <option key={k.id} value={k.id}>
                {k.ma} · {k.ten}
                {k.tinh_trang === "dang_dat_lam" ? " · ĐANG LÀM"
                  : k.tinh_trang === "hong" ? " · HỎNG"
                  : k.tinh_trang === "thanh_ly" ? " · ĐÃ THANH LÝ"
                  : k.so_ke ? ` · ${k.so_ke}` : ""}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => { setMoTaoMoi(true); setTenMoi(tenSanPham); }}>
            + Làm khuôn mới
          </Button>
        </div>
      )}
    </section>
  );
}
