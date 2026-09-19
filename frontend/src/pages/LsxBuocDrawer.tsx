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
import { Select, type SelectOption } from "../components/Select";
import { dvNhan as dvNhanChung, type RefRow } from "./LsxRoutingTable";
import { num } from "./keHoachSxShared";
import { donViOptions, useNapTenDonVi } from "./tenDonVi";
import {
  type EditRow,
  type HangLoai,
  capMon,
  heSoChu,
  mayChonDuoc,
  nhanChang,
  nhanDonVi,
  phut,
  tenBuoc,
  thoiLuong,
  thoiLuongLive,
} from "./lsxBuoc";

// Bước THUÊ NGOÀI nhập liệu Y HỆT bước máy: nhà thầu được khai sẵn trong danh mục Máy (tên kèm
// hậu tố "thuê ngoài – <tên nhà in>", đủ thông số như máy nhà), kế hoạch vẫn chọn máy như
// thường. Chỉ khác hai chỗ nằm phía sau màn này: KHÔNG sinh tiền khoán và KHÔNG ghi sản lượng
// vào tổ. Vì vậy KHÔNG có ô/tab nào riêng cho thuê ngoài.
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
  | "nhan_dien"
  | "so_luong"
  | "ai_lam"
  | "vat_tu"
  | "phu_thuoc"
  | "thoi_gian"
  | "cau_hinh"
  | "phan_cong"
  | "tien_do";

type MainTab = "cau_hinh" | "phan_cong" | "vat_tu" | "tien_do" | "phu_thuoc";

function normalizeTab(t?: TabKey): MainTab {
  if (!t) return "cau_hinh";
  if (t === "nhan_dien" || t === "so_luong" || t === "cau_hinh") return "cau_hinh";
  if (t === "ai_lam" || t === "phan_cong") return "phan_cong";
  if (t === "vat_tu") return "vat_tu";
  // Phụ thuộc DAG tách khỏi "Tiến độ & Thời gian" 18/08/2026: chọn tiền nhiệm là việc của người
  // xếp lịch, xem giờ chạy là việc của người lập kế hoạch — hai đầu việc khác nhau, cuộn qua nhau.
  if (t === "phu_thuoc") return "phu_thuoc";
  if (t === "thoi_gian" || t === "tien_do") return "tien_do";
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
  tenKhach,
  onTaoKhuon,
  vatTuRefs,
  giayRefs,
  phuThuocRefs,
  baiGhep,
  // (`dvChuoi` vẫn là prop — nơi gọi vẫn truyền — nhưng thân drawer hiện KHÔNG đọc tới, nên bỏ
  //  khỏi destructure cho `tsc` sạch. Cần dùng lại thì thêm tên vào đây, không phải sửa kiểu.)
  canUpdate,
  onPatch,
  onPatchLsx,
  onDoiCongDoan,
  onDoiMay,
  onDoiTo,
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
  /** Tên khách của lệnh — để khối Khuôn nói rõ danh sách đang lọc theo ai. */
  tenKhach: string;
  /** Tạo dao mới cho bước — trả id dao vừa tạo để gán luôn. */
  onTaoKhuon: (input: { ten: string; loai: string | null }) => Promise<number>;
  vatTuRefs: RefRow[] | null;
  giayRefs: RefRow[] | null;
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
  /** Đổi máy: tốc độ + chuẩn bị lấy theo danh mục Máy NGAY, rồi hỏi server thời lượng mới. Không
   *  đi qua `onPatch` vì hai số đó không nằm trong form — chúng tới từ máy vừa chọn. */
  onDoiMay: (mayId: number | null) => void;
  /** Đổi tổ: chọn MỘT trong các tổ phụ trách của công đoạn. */
  onDoiTo: (departmentId: number | null) => void;
  /** Mở sẵn tới khối nào (badge ngoài bảng/sơ đồ bấm vào là nhảy thẳng, khỏi cuộn tìm). */
  tabDau?: TabKey;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [activeTab, setActiveTab] = useState<MainTab>(() => normalizeTab(tabDau));

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

  // Bảng nhãn đơn vị nạp ở bảng cha rồi, gọi lại ở đây chỉ để drawer TỰ vẽ lại khi bảng về muộn
  // (hook có cache + danh sách người chờ dùng chung, không đẻ thêm request).
  const napDv = useNapTenDonVi();
  // Bước NGOÀI dòng giấy (ghi kẽm, đóng thùng): số không suy được từ chuỗi giấy, cũng không công
  // thức chung nào ở danh mục nói hộ — số bản kẽm đổi theo số màu/số mặt/số bài của TỪNG đơn. Nên
  // đây là chỗ DUY NHẤT khai được, và khai xong thì danh mục thôi kéo lại (`tu_khai_don_vi` ở BE).
  const laNgoaiDong = row.tren_dong_giay === false;
  const khaiTay = laNgoaiDong && canUpdate;
  const dvOpts = useMemo<SelectOption<string>[]>(() => {
    const ds = donViOptions();
    return [
      { value: "", label: ds.length ? "— chưa khai —" : "Đang nạp danh mục Đơn vị…" },
      ...ds.map((o) => ({ value: o.value, label: o.label, hint: o.value })),
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [napDv]);
  // Đơn vị để DÁN CẠNH SỐ — cùng hàm bảng routing dùng. Lối lùi về đơn vị sản lượng của danh mục
  // GỠ 18/09/2026 (mg `0324`): bước ngoài dòng chỉ có đơn vị khi người lập lệnh tự khai.
  const dvNhan = (dv: string | null | undefined) => dvNhanChung(dv, row);
  // Dòng "Số vào = ra ÷ hệ số × (1 + hao%) + hao" của bước ngoài dòng GỠ 18/09/2026 (mg `0324`)
  // cùng `LsxService.buoc_ngoai_dong` nó diễn giải — server thôi suy số vào từ số ra cho bước ấy.

  // Danh sách CÔNG ĐOẠN cho ô gõ-lọc. Danh mục công đoạn đã hơn 30 dòng và còn dài ra; thẻ
  // <select> gốc chỉ nhảy theo ký tự ĐẦU nên "cán màng" phải gõ đúng "c-á-n", gõ "can mang"
  // hay "mang mo" đều trượt. `Select searchable` khớp gần đúng (bỏ dấu, tách từ — xem
  // `utils/timGanDung`) và soi cả `hint`, nên mã CD-00xx cũng tìm được.
  const cdOpts = useMemo<SelectOption<string>[]>(() => {
    if (!congDoanRefs) return [];
    const ds: SelectOption<string>[] = [{ value: "", label: "— chọn công đoạn —" }];
    // Bước khai tên tự do (không nối danh mục) và bước trỏ tới công đoạn ĐÃ ẨN/XOÁ khỏi danh mục
    // vẫn phải hiện đúng tên đang có, không thì mở drawer ra là thấy ô rỗng và lưu đè mất tên.
    if (row.cong_doan_id == null && row.ten) {
      ds.push({ value: "__keep__", label: `${row.ten} (tên tự do)` });
    }
    if (row.cong_doan_id != null && !congDoanRefs.some((c) => c.id === row.cong_doan_id)) {
      ds.push({ value: String(row.cong_doan_id), label: row.ten });
    }
    for (const c of congDoanRefs) {
      ds.push({ value: String(c.id), label: c.ten, search: c.ma ?? "" });
    }
    return ds;
  }, [congDoanRefs, row.cong_doan_id, row.ten]);

  // Danh sách MÓN thêm được vào khối vật tư của bước. Nhãn KHÔNG mang mã: danh sách này dài và
  // mã "GL-0001-COPY-COPY" đẩy tên món ra sau, nhìn cả cột chỉ thấy tiền tố giống nhau. Mã chuyển
  // xuống `search` — vẫn gõ mã ra được, chỉ là không chiếm chỗ trên màn.
  const themMonOpts = useMemo<SelectOption<string>[]>(() => {
    const daCo = (hl: HangLoai, id: number) =>
      row.vat_tus.some((v) => capMon(v.hang_loai, v.vat_tu_id) === capMon(hl, id));
    const ds: SelectOption<string>[] = [];
    // GIẤY đứng TRƯỚC: đây là món đắt nhất và là thứ người lập lệnh tìm đầu tiên. Chọn giấy ở đây
    // CHÍNH LÀ khai NVL chính cho bước — bước nào mang dòng giấy thì ngày cần giấy bám bước đó.
    for (const x of giayRefs ?? []) {
      if (daCo("giay", x.id)) continue;
      ds.push({
        value: capMon("giay", x.id),
        label: `${x.ten} (${nhanDonVi(x.donVi)})`,
        search: x.ma ?? "",
        group: "NVL chính — danh mục Giấy",
      });
    }
    for (const x of vatTuRefs ?? []) {
      if (daCo("vat_tu", x.id)) continue;
      ds.push({
        value: capMon("vat_tu", x.id),
        label: `${x.ten} (${nhanDonVi(x.donVi)})`,
        search: x.ma ?? "",
        group: "Vật tư in ấn",
      });
    }
    return ds;
  }, [giayRefs, vatTuRefs, row.vat_tus]);

  const mayForm = mayRefs?.find((m) => m.id === row.may_id) ?? null;
  const t = useMemo(() => thoiLuong(row, mayForm), [row, mayForm]);
  const tg = useMemo(() => thoiLuongLive(row, mayForm), [row, mayForm]);
  // Luật lọc nằm ở `mayChonDuoc` (xem `lsxBuoc.ts`) — cùng một luật với backend, và tách ra khỏi
  // JSX để test được: bảng máy của công đoạn thắng, chưa khai thì lùi về nhóm máy.
  const nhomMay = useMemo(() => {
    if (!mayRefs) return [];
    const cd = congDoanRefs?.find((c) => c.id === row.cong_doan_id) ?? null;
    return nhomMayTheoLoai(mayChonDuoc(mayRefs, cd, row.may_id));
  }, [mayRefs, congDoanRefs, row.cong_doan_id, row.may_id]);
  // Ô TỔ: chỉ các tổ phụ trách khai ở danh mục Công đoạn (nhiều tổ, 18/09/2026), đúng thứ tự khai
  // (tổ đầu = mặc định). Công đoạn chưa khai tổ ⇒ mời mọi tổ, như server không chặn. Tổ đang gán mà
  // không còn phụ trách vẫn hiện (gắn nhãn) — bỏ nó khỏi danh sách là select nhảy về dòng trống.
  const toChon = useMemo(() => {
    if (!toRefs) return { items: [] as { id: number; ten: string }[], gioiHan: false };
    const cd = congDoanRefs?.find((c) => c.id === row.cong_doan_id) ?? null;
    const ids = cd?.toChoPhep ?? [];
    const items = ids.length
      ? ids.map((id) => ({ id, ten: toRefs.find((t) => t.id === id)?.ten ?? `Tổ #${id} (đã xoá)` }))
      : toRefs.map((t) => ({ id: t.id, ten: t.ten }));
    if (row.department_id != null && !items.some((t) => t.id === row.department_id)) {
      const ten = toRefs.find((t) => t.id === row.department_id)?.ten ?? row.department_ten ?? `Tổ #${row.department_id}`;
      items.push({ id: row.department_id, ten: `${ten} (không còn phụ trách công đoạn)` });
    }
    return { items, gioiHan: ids.length > 0 };
  }, [toRefs, congDoanRefs, row.cong_doan_id, row.department_id, row.department_ten]);

  // Đầu việc khoán của bước (`dsKhoan` / `khoanDaChon`) GỠ 18/09/2026 (mg `0320`).
  const mayDaChon = mayRefs?.find((m) => m.id === row.may_id);
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

  // `tuDinhMuc` · `bungVatTu` · `chonDauViec` GỠ 18/09/2026: vật tư bung theo CÔNG ĐOẠN ở server
  // (tab Vật tư của danh mục, mg `0316`), bước thôi chọn đầu việc.

  function doiLoaiBuoc(k: LsxLoaiBuoc) {
    // Kíp chuẩn + năng suất khoán GỠ 18/09/2026 (mg `0321`): đổi loại bước chỉ còn đổi CÁCH TÍNH
    // GIỜ — máy/thuê ngoài theo tốc độ máy, tổ theo số giờ kế hoạch gõ tay (ô nằm ở tab Thời gian).
    if (k === "may" || k === "thue_ngoai") {
      onPatch({ loai_buoc: k });
      return;
    }
    onPatch({
      loai_buoc: k,
      may_id: null,
      // Ô "số lượt qua máy" không hiện ở bước tổ (08/09/2026) — trả về 1 ngay lúc đổi loại, để
      // số 2 lượt của bước máy cũ không nằm lại vô hình trong bản nháp.
      so_luot_chay: "1",
    });
  }

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
    // CUỐI hàng — badge đếm số bước tiền nhiệm đang chọn, đúng con số trước đây treo ở tab Tiến độ.
    list.push({ key: "phu_thuoc", label: "Phụ thuộc", badge: row.phu_thuoc_step_keys.length });
    return list;
  }, [row.vat_tus.length, row.phu_thuoc_step_keys.length]);

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
                      <Select
                        options={cdOpts}
                        value={
                          row.cong_doan_id != null
                            ? String(row.cong_doan_id)
                            : row.ten
                              ? "__keep__"
                              : ""
                        }
                        onChange={(v) => {
                          if (v === "__keep__") return;
                          onDoiCongDoan(v ? Number(v) : null);
                        }}
                        disabled={!canUpdate}
                        ariaLabel="Tên công đoạn"
                        placeholder="— chọn công đoạn —"
                        searchable
                        searchPlaceholder="Gõ tên hoặc mã công đoạn…"
                        // `portal`: drawer cuộn dọc, popover thường bị cắt ở mép khối "Nhận diện".
                        portal
                        className="khsx-select-std"
                      />
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

                  {/* Hàng 2: Ghi chú kỹ thuật — chiếm cả hàng từ 07/09/2026, khi ô "Bước bắt buộc"
                      ở cột 2 bị GỠ: routing đã khai bước nào thì bước đó PHẢI làm, không có bước
                      tuỳ chọn nữa (`lsx_cong_doan.bat_buoc` luôn TRUE, xem migration 0275). */}
                  <label className="khsx-field khsx-field--wide">
                    <span className="khsx-field__label">GHI CHÚ KỸ THUẬT CHO THỢ</span>
                    <input
                      className="khsx-input-std"
                      value={row.ghi_chu}
                      disabled={!canUpdate}
                      placeholder="vd: canh màu theo mẫu đã ký, kiểm tra keo..."
                      onChange={(e) => set("ghi_chu", e.target.value)}
                    />
                  </label>
                </div>
              </section>

              {/* Khối Nhãn (gắn thẻ tự do cho bước) ẨN 07/09/2026. API `cong-doan-tags` + nhãn đã
                  gán vẫn còn nguyên trong DB, chỉ không bày cửa gán/gỡ ở drawer nữa — bật lại là
                  trả `<TagPicker buocLoai="lsx" buocId={row.id} …>` vào đúng chỗ này. */}

              {/* Ô "Tiêu chí KCS bổ sung" GỠ 08/09/2026 (mg 0283): tiêu chí KCS chỉ còn MỘT
                  nguồn là danh mục Tiêu chí KCS gắn theo công đoạn, khai một lần áp cho mọi
                  lệnh chạy công đoạn đó. Xem `docs/design-kcs-theo-cong-doan.md` mục 5. */}

              {/* Khối Dòng chảy Số lượng (Production Flow Pipeline) */}
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Dòng chảy số lượng & hao hụt</h3>
                </div>

                {/* Băng giải thích "bước không nằm trên dòng giấy" ĐÃ BỎ 09/09/2026 theo yêu cầu —
                    nó chỉ mô tả lại cách máy tính số, không đòi người khai làm gì. `tren_dong_giay`
                    vẫn về từ API và vẫn lái cách tính, chỉ không bày một câu chữ ở đây nữa.
                    Băng ĐỎ "Chưa tính được số vào" (`loi_quy_doi`) GỠ 18/09/2026 (mg `0324`). */}

                <div className="khsx-flow-pipeline">
                  {/* Node Vào */}
                  <div className="khsx-flow-node khsx-flow-node--in">
                    <span className="khsx-flow-node__kicker">SỐ LƯỢNG VÀO</span>
                    <div className="khsx-flow-node__val-row">
                      {khaiTay ? (
                        <div className="khsx-flow-input-wrap">
                          <input
                            type="number"
                            min={0}
                            className="khsx-flow-editable-input"
                            aria-label="Số lượng vào của bước"
                            value={row.so_luong_vao}
                            onChange={(e) => onPatch({ so_luong_vao: e.target.value })}
                          />
                          <Select
                            options={dvOpts}
                            value={row.don_vi_vao}
                            // Chọn MỘT vế thì điền luôn vế kia nếu nó còn trống: bước ngoài dòng
                            // thường đếm cùng một thứ ở hai đầu (nhận việc ghi 4 bản, giao 4 bản).
                            // Server chỉ coi là "khai tay" khi ĐỦ CẢ HAI ô, nên để người dùng chọn
                            // một ô rồi tưởng xong là ô kia im lặng không có tác dụng gì.
                            onChange={(v) => onPatch({
                              don_vi_vao: v, ...(row.don_vi_ra ? {} : { don_vi_ra: v }),
                            })}
                            ariaLabel="Đơn vị đầu vào của bước"
                            searchable
                            portal
                            className="khsx-flow-dv-select"
                          />
                        </div>
                      ) : (
                        <>
                          <span className="khsx-flow-node__val">{num(Number(row.so_luong_vao || 0))}</span>
                          <span className="khsx-unit-pill">{dvNhan(row.don_vi_vao)}</span>
                        </>
                      )}
                    </div>
                    <span className="khsx-flow-node__hint">
                      {khaiTay ? "Bước ngoài dòng giấy — kế hoạch tự khai" : "Đầu vào công đoạn"}
                    </span>
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
                      ) : khaiTay ? (
                        <div className="khsx-flow-input-wrap">
                          <input
                            type="number"
                            min={0}
                            className="khsx-flow-editable-input"
                            aria-label="Số lượng ra của bước"
                            value={row.so_luong_ra}
                            onChange={(e) => onPatch({ so_luong_ra: e.target.value })}
                          />
                          <Select
                            options={dvOpts}
                            value={row.don_vi_ra}
                            onChange={(v) => onPatch({
                              don_vi_ra: v, ...(row.don_vi_vao ? {} : { don_vi_vao: v }),
                            })}
                            ariaLabel="Đơn vị đầu ra của bước"
                            searchable
                            portal
                            className="khsx-flow-dv-select"
                          />
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
                        : khaiTay
                          ? "Gõ số rồi bấm Lưu công đoạn — số này xuống thẳng thẻ việc của tổ"
                          : laNgoaiDong
                            ? "Bước ngoài dòng giấy — kế hoạch tự khai"
                            : "Tự động tính ngược từ bước cuối"}
                    </span>
                  </div>
                </div>

                {/* Hai dòng diễn giải "Số ra = …" / "Số vào = …" của bước ngoài dòng giấy GỠ
                    18/09/2026 (mg `0324`) cùng công thức sản lượng ra của công đoạn. */}
              </section>
            </div>
          )}

          {/* =========================================================================
              TAB 2: PHÂN CÔNG & THIẾT BỊ
             ========================================================================= */}
          {activeTab === "phan_cong" && (
            <div className="khsx-tab-pane">
                <div className="khsx-form-stack">
                  {/* Thẻ Tổ phụ trách */}
                  <section className="khsx-section-card">
                    <div className="khsx-section-card__head">
                      <h3 className="khsx-section-card__title">Tổ sản xuất & Máy thiết bị</h3>
                    </div>

                    <div className="khsx-assign-grid">
                      {/* TỔ PHỤ TRÁCH — chọn MỘT trong các tổ khai ở danh mục Công đoạn (nhiều tổ,
                          18/09/2026). Bước chạy chung ở bài ghép thì tổ do lượt chung quyết, như máy. */}
                      <label className="khsx-field">
                        <span className="khsx-field__label">TỔ PHỤ TRÁCH</span>
                        {buocGhep && deLen ? (
                          <div className="khsx-gang-box">
                            <span className="khsx-gang-box__title">
                              {deLen.to_ten ?? "Chưa chọn ở bài"}
                            </span>
                            <span className="khsx-gang-box__hint">
                              Tổ của lượt chung — đổi ở bài <strong>{buocGhep.ma}</strong>.
                            </span>
                          </div>
                        ) : toRefs ? (
                          <>
                            <select
                              className="khsx-select-std"
                              value={row.department_id ?? ""}
                              disabled={!canUpdate}
                              onChange={(e) => onDoiTo(e.target.value ? Number(e.target.value) : null)}
                            >
                              {row.department_id == null && <option value="">— chọn tổ —</option>}
                              {toChon.items.map((t, i) => (
                                <option key={t.id} value={t.id}>
                                  {toChon.gioiHan && i === 0 ? `${t.ten} · mặc định` : t.ten}
                                </option>
                              ))}
                            </select>
                            <span className="khsx-field__hint">
                              {toChon.gioiHan
                                ? "Chỉ các tổ phụ trách khai ở danh mục Công đoạn. Lúc ghi mẻ, bàn tổ chọn trong công việc khoán của tổ này."
                                : "Công đoạn chưa khai tổ phụ trách — đang mời mọi tổ."}
                            </span>
                          </>
                        ) : (
                          <span className="khsx-val-text">{row.department_ten ?? "—"}</span>
                        )}
                      </label>

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
                                      {m.active === false ? `${m.ten} (ngừng dùng)` : m.ten}
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

                  {/* Hai thẻ "KÍP CHUẨN" và "Đầu việc thợ làm" GỠ 18/09/2026 (mg `0320` + `0321`, chủ
                      khoanh đỏ trên màn): bỏ hẳn logic kíp người, bước thôi chọn đầu việc — việc
                      khoán thợ chọn lúc ghi mẻ ở bàn tổ. Giờ của bước tổ gõ ở tab Thời gian. */}

                  {/* Thẻ Khuôn dao của bước */}
                  {row.requires_tooling && (
                    <KhuonCuaBuoc
                      row={row}
                      tenSanPham={tenSanPham}
                      tenKhach={tenKhach}
                      khuonRefs={khuonRefs}
                      canUpdate={canUpdate}
                      onChon={(id) => set("khuon_be_id", id)}
                      onTaoMoi={onTaoKhuon}
                    />
                  )}
                </div>
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
                    <h3 className="khsx-section-card__title">Định mức NVL &amp; vật tư (BOM)</h3>
                    <p className="khsx-section-card__sub">
                      Món công đoạn này ăn — cả GIẤY (NVL chính) lẫn vật tư tiêu hao. Bước nào mang
                      dòng giấy thì ngày cần giấy ở bảng cân đối bám đúng bước đó.
                    </p>
                  </div>
                  <span className="khsx-badge-count">{row.vat_tus.length} món</span>
                </div>

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
                        const g = row.vat_tu_goi_y.find(
                          (x) => capMon(x.hang_loai, x.vat_tu_id) === capMon(v.hang_loai, v.vat_tu_id));
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
                                const g = row.vat_tu_goi_y.find(
                          (x) => capMon(x.hang_loai, x.vat_tu_id) === capMon(v.hang_loai, v.vat_tu_id));
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
                            Chưa khai món nào cho công đoạn này — chọn giấy hoặc vật tư ở ô bên dưới.
                          </td>
                        </tr>
                      ) : (
                        row.vat_tus.map((v, i) => {
                          const goiY = row.vat_tu_goi_y.find(
                            (g) => capMon(g.hang_loai, g.vat_tu_id) === capMon(v.hang_loai, v.vat_tu_id));
                          const soMay = goiY?.so_luong ?? null;
                          const soLuu = v.so_luong.trim() === "" ? null : Number(v.so_luong);
                          const lech =
                            soMay !== null &&
                            soLuu !== null &&
                            Number.isFinite(soLuu) &&
                            Math.abs(soMay - soLuu) > 0.0005;
                          return (
                            <tr className="khsx-vattu-tr" key={capMon(v.hang_loai, v.vat_tu_id)}>
                              <td className="khsx-vattu-td khsx-vattu-td--info">
                                <div className="khsx-vattu-cell-name">
                                  <span className="khsx-vattu-code">{v.vat_tu_ma}</span>
                                  <span className="khsx-vattu-name">{v.vat_tu_ten}</span>
                                  {v.hang_loai === "giay" && (
                                    <span className="khsx-vattu-nvl-badge">NVL chính</span>
                                  )}
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
                    {canUpdate && (vatTuRefs || giayRefs) && (
                      <tfoot className="khsx-vattu-tfoot">
                        <tr>
                          <td colSpan={5} className="khsx-vattu-td-add">
                            <div className="khsx-vattu-add-bar">
                              <span className="khsx-vattu-add-icon">＋</span>
                              <Select
                                options={themMonOpts}
                                value=""
                                placeholder="— Thêm vật tư / NVL chính vào công đoạn —"
                                ariaLabel="Thêm vật tư hoặc NVL chính vào công đoạn"
                                searchable
                                searchPlaceholder="Gõ tên hoặc mã vật tư…"
                                portal
                                className="khsx-vattu-select-clean"
                                onChange={(v) => {
                                  // Giá trị là CẶP `hang_loai:id` — hai danh mục đánh số độc lập,
                                  // gửi id trần thì server không biết tra bảng nào.
                                  const [hl, sid] = String(v).split(":");
                                  if (!hl || !sid) return;
                                  const hangLoai = hl as HangLoai;
                                  const item = (hangLoai === "giay" ? giayRefs : vatTuRefs)
                                    ?.find((v) => v.id === Number(sid));
                                  const cap = capMon(hangLoai, Number(sid));
                                  if (!item) return;
                                  if (row.vat_tus.some(
                                    (v) => capMon(v.hang_loai, v.vat_tu_id) === cap)) return;
                                  const goiY = row.vat_tu_goi_y.find(
                                    (g) => capMon(g.hang_loai, g.vat_tu_id) === cap);
                                  set("vat_tus", [
                                    ...row.vat_tus,
                                    {
                                      hang_loai: hangLoai,
                                      vat_tu_id: item.id,
                                      vat_tu_ma: item.ma ?? "",
                                      vat_tu_ten: item.ten,
                                      don_vi: item.donVi ?? "",
                                      so_luong: goiY?.so_luong != null ? String(goiY.so_luong) : "",
                                      tu_dong: false,
                                    },
                                  ]);
                                }}
                              />
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
                  {/* 08/09/2026: ô CHỈ hiện ở bước máy/thuê ngoài — làm tay thì không có
                      "lượt qua máy" nào để đếm. Bước tổ ép cứng 1 lượt (payload gửi 1, server ghi
                      lại 1 lần nữa), nên chip `so_luot_chay` của công thức giờ vẫn có số
                      thật để dùng, chỉ là luôn bằng 1. */}
                  {row.loai_buoc !== "to" && (
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
                            2 lượt
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
                  )}

                  {/* SỐ GIỜ KẾ HOẠCH (18/09/2026, mg `0319`) — bước TỔ không còn năng suất hay kíp
                      để máy chia, nên giờ của nó là số người lập lệnh ƯỚC gõ tay. Mặc định 0, nhận
                      số lẻ (1,5 giờ), để 0 cũng không cảnh báo gì (chủ chốt). */}
                  {row.loai_buoc === "to" && (
                    <div className="khsx-field">
                      <label className="khsx-field__label" htmlFor={`gio-kh-${row.key}`}>SỐ GIỜ KẾ HOẠCH</label>
                      <div className="khsx-input-unit-combine">
                        <input
                          id={`gio-kh-${row.key}`}
                          type="number"
                          min="0"
                          step="0.25"
                          inputMode="decimal"
                          className="khsx-input-combine__num"
                          value={row.so_gio_ke_hoach}
                          placeholder="0"
                          disabled={!canUpdate}
                          onChange={(e) => {
                            // Chỉ nhận SỐ: ô rỗng về "" (gửi đi thành 0), số âm kẹp về 0. Giữ nguyên
                            // chuỗi đang gõ ("1." / "0,5" giữa chừng) để không nuốt dấu thập phân.
                            const v = e.target.value;
                            set("so_gio_ke_hoach", v === "" || Number(v) >= 0 ? v : "0");
                          }}
                        />
                        <span className="khsx-input-combine__unit">giờ</span>
                      </div>
                      <span className="khsx-field__hint">
                        Tổ ước làm bao lâu — xếp lịch chiếm đúng chừng ấy giờ của tổ. Để 0 nếu chưa ước.
                      </span>
                    </div>
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
                            : (row.loai_buoc === "to" ? (row.department_ten ?? "Tổ làm tay") : "Chưa gán máy")}
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
                              {tg.quy_doi_dien_giai ? String(tg.quy_doi_dien_giai) : `${num(Number(tg.so_luong_vao ?? 0))} ${nhanChang(tg.don_vi_vao as string | null)}`}
                            </span>
                            <span className="khsx-formula-op">÷</span>
                            <span className="khsx-formula-token khsx-formula-token--speed">
                              {num(Number(tg.nang_suat_hieu_dung ?? 0))}/giờ
                            </span>
                            {row.loai_buoc !== "to" && Number(tg.so_luot_chay ?? 1) !== 1 && (
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
                            Nguồn tính: {mayDaChon ? mayDaChon.ten : "Chưa gán máy"}
                          </span>
                        </div>
                      </div>
                    )}
                    {row.loai_buoc === "to" && (
                      <div style={{ padding: "0 16px 14px", background: "#ffffff" }}>
                        <div className="khsx-time-row__formula-card" style={{ marginTop: 0 }}>
                          <div className="khsx-formula-compact">
                            <span className="khsx-formula-token khsx-formula-token--qty">
                              {num(Number(tg.so_gio_ke_hoach ?? row.so_gio_ke_hoach ?? 0))} giờ kế hoạch
                            </span>
                            <span className="khsx-formula-op">=</span>
                            <span className="khsx-formula-token khsx-formula-token--result">
                              {phut(Number(tg.chay_phut ?? 0))}
                            </span>
                          </div>
                          <span className="khsx-time-row__src">Nguồn tính: số giờ người lập lệnh gõ</span>
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
                        ? "Bước tổ chạy theo số giờ kế hoạch gõ tay — không có khoảng nhanh–chậm."
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

/** Nhãn loại dụng cụ — khớp `khuon_be.LOAI_KHUON` (mg 0205; `khung_lua` thêm 04/09/2026 vì khung
 *  lụa cũng nằm kho dùng lại, không phải vật tư tiêu hao). Trước đây chỗ này là phép hỏi
 *  `=== "khuon_ep" ? … : "khuôn bế"`, nên bước IN LỤA mở thẻ ra thấy chữ "khuôn bế" — kho đã nhận
 *  khung lụa mà màn vẫn gọi sai tên. Dòng chưa phân loại (`loai = null`, 6 dòng khai trước mg
 *  0205) rơi về chữ chung. */
const NHAN_TOOLING: Record<string, string> = {
  khuon_be: "khuôn bế",
  khuon_ep: "khuôn ép kim",
  khung_lua: "khung lụa",
};

/** Tình trạng khuôn rút thành CHỮ NGẮN đứng cạnh tên trong ô chọn — chỉ hiện khi KHÔNG bình
 *  thường. Dao sẵn sàng thì để trống cho danh sách đỡ rối; đã chọn rồi mới xem câu đầy đủ ở
 *  `moTaTinhTrang`. */
function nhanTinhTrangNgan(tt: string | null | undefined): string | undefined {
  switch (tt) {
    case "dang_dat_lam": return "ĐANG LÀM";
    case "hong": return "HỎNG";
    case "thanh_ly": return "ĐÃ THANH LÝ";
    default: return undefined;
  }
}

/** Ba MỨC của tình trạng dao */
function nhomTinhTrang(tt: string | null | undefined): "san" | "cho" | "hong" {
  if (tt === "hong" || tt === "thanh_ly") return "hong";
  if (tt === "dang_dat_lam") return "cho";
  return "san";
}

/** Một câu trả lời trọn vẹn cho "dao này dùng được chưa, lấy ở đâu". */
function moTaTinhTrang(dao: { so_ke?: string | null; tinh_trang?: string } | null): string {
  if (!dao) return "Chưa nạp được thông tin khuôn — bấm Làm mới ở đầu màn.";
  switch (dao.tinh_trang) {
    case "dang_dat_lam":
      // Không kèm ngày dự kiến nữa (mg `0293` gỡ cột): mốc đó chưa ai cập nhật bao giờ. Người theo
      // dõi dao đổi tình trạng khi cầm được nó — đó mới là tin nói ra được.
      return "Đang đặt làm — chưa có trong tay. Bước này chưa chạy được.";
    case "hong":
      return "Khuôn HỎNG — không dùng được. Chọn con khác hoặc làm khuôn mới.";
    case "thanh_ly":
      return "Khuôn ĐÃ THANH LÝ — không còn trong kho. Chọn con khác hoặc làm khuôn mới.";
    default:
      return dao.so_ke ? `Có sẵn — lấy tại ${dao.so_ke}` : "Có sẵn — chưa khai số kệ";
  }
}

/** Khối KHUÔN của một bước */
function KhuonCuaBuoc({
  row,
  tenSanPham,
  tenKhach,
  khuonRefs,
  canUpdate,
  onChon,
  onTaoMoi,
}: {
  row: EditRow;
  tenSanPham: string;
  /** Tên khách của lệnh — CHỈ để nói ra thành lời cái bộ lọc server đã áp. Danh sách chỉ có vài
   *  dòng nên dễ tưởng kho rỗng; ghi tên khách ra thì người chốt dao biết ngay vì sao ngắn. */
  tenKhach: string;
  khuonRefs: import("../api/client").KhuonChonDuoc[] | null;
  canUpdate: boolean;
  onChon: (id: number | null) => void;
  onTaoMoi: (input: { ten: string; loai: string | null }) => Promise<number>;
}) {
  const [moTaoMoi, setMoTaoMoi] = useState(false);
  const [tenMoi, setTenMoi] = useState("");
  const [dangTao, setDangTao] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const nhanLoai = NHAN_TOOLING[row.tooling_type ?? ""] ?? "khuôn / khung";

  const chonDuoc = useMemo(() => {
    const ds = khuonRefs ?? [];
    return ds.filter((k) => !row.tooling_type || !k.loai || k.loai === row.tooling_type);
  }, [khuonRefs, row.tooling_type]);

  // Ô chọn là `<Select>` gõ-lọc (bỏ dấu), không phải `<select>` gốc: kho dao của một khách lặp
  // lại vẫn tới vài chục con và tên chúng na ná nhau ("hộp bánh 20×20", "hộp bánh 20×25"), cuộn
  // tay để tìm là chỗ người ta bỏ cuộc rồi bấm "Làm khuôn mới" — đặt lại con dao đang nằm trên kệ.
  // MÃ + SỐ KỆ xuống dòng phụ chứ không bỏ đi như ô vật tư/máy: ở đây mã là thứ dán trên con dao
  // và số kệ là chỗ đi lấy nó, hai thứ đều phải đọc được lúc chọn. `khopGanDung` quét cả dòng phụ
  // nên gõ "kb-0002" hay "b1" vẫn ra.
  const khuonOpts = useMemo<SelectOption<string>[]>(
    () => chonDuoc.map((k) => ({
      value: String(k.id),
      label: k.ten || k.ma,
      sub: [k.ma, k.so_ke].filter(Boolean).join(" · "),
      hint: nhanTinhTrangNgan(k.tinh_trang),
    })),
    [chonDuoc],
  );

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
    };
  }, [row, khuonRefs]);

  const daChon = row.khuon_be_id != null;

  async function taoMoi() {
    const ten = tenMoi.trim();
    if (!ten) {
      setLoi("Cần tên khuôn.");
      return;
    }
    setDangTao(true);
    setLoi(null);
    try {
      onChon(await onTaoMoi({ ten, loai: row.tooling_type }));
      setMoTaoMoi(false);
      setTenMoi("");
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

      {/* Ý ĐỊNH CỦA SALE, chép từ phiếu tính giá — đọc TRƯỚC khi chọn dao (chốt 04/09/2026). Không
          có dòng này thì kế hoạch chốt dao trong bóng tối: tiền khuôn đã báo cho khách rồi mà
          người chốt không biết, tới lúc lệch mới lòi ra ở hoá đơn. */}
      {row.khuon_nguon && (
        <p className="khsx-khuon__y-dinh">
          Sale báo:{" "}
          {row.khuon_nguon === "lam_moi"
            ? `làm khuôn mới${row.khuon_phi ? `, ${row.khuon_phi.toLocaleString("vi-VN")}đ` : ""}`
            : "dùng khuôn có sẵn"}
        </p>
      )}
      {/* NHẮC chứ không chặn: máy không biết xưởng sẽ báo lại khách hay tự nuốt chi phí. */}
      {row.khuon_lech && <p className="khsx-khuon__lech">{row.khuon_lech}</p>}

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
        <>
          <div className="khsx-khuon__chon">
            <Select
              options={khuonOpts}
              value=""
              placeholder={chonDuoc.length > 0
                ? `— chọn ${nhanLoai} có sẵn (${chonDuoc.length}) —`
                : `— khách này chưa có ${nhanLoai} nào —`}
              ariaLabel={`Chọn ${nhanLoai} có sẵn`}
              disabled={chonDuoc.length === 0}
              searchable
              searchPlaceholder="Gõ tên, mã hoặc số kệ…"
              portal
              onChange={(v) => v && onChon(Number(v))}
            />
            <Button variant="secondary" onClick={() => { setMoTaoMoi(true); setTenMoi(tenSanPham); }}>
              + Làm khuôn mới
            </Button>
          </div>
          {/* Nói THÀNH LỜI bộ lọc mà server đã áp (`lsx_service.khuon_chon_duoc`: khách của lệnh +
              loại của bước). Không có câu này thì danh sách 1–2 dòng trông y như kho rỗng, và
              người chốt dao đi làm con dao mới trong khi khách khác đang giữ đúng con đó. */}
          <span className="khsx-field__hint">
            Chỉ hiện {nhanLoai} của khách <b>{tenKhach || "— chưa có khách"}</b> — dụng cụ là của
            khách, không dùng chéo. Chưa thấy con cần tìm thì kiểm ở màn Khuôn xem nó
            đã gắn đúng khách chưa.
          </span>
        </>
      )}
    </section>
  );
}
