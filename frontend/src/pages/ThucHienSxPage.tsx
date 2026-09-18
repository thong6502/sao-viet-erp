// THỰC HIỆN SẢN XUẤT tại TỔ — "một bàn làm việc" (module `san_xuat`, pha đứng SAU "Xếp lịch").
//
// Controller bàn tổ: nhận `teamId`, giữ cửa sổ ngày (7/14/30 ngày) + việc + việc-đang-chọn + version
// lạc quan; gọi `api.sanXuat.*`; dựng top → subbar → grid (hàng chờ trái · lịch ngày giữa · drawer
// phải) → foot. Điều phối drawer + dialog lý do + toast. **KHÔNG kéo–thả** (tổ trưởng chỉ đọc lịch, ghi
// phân công / phiên chạy). Real-time qua `eventTick` (SSE mắc ở AppShell) → refetch tức thì.
//
// LÝ DO bắt buộc (bám luật BE): chỉ còn Tạm dừng cần `ly_do`. Lý do "số người khác kíp chuẩn" GỠ
// 18/09/2026 (mg `0321`) cùng kíp chuẩn của bước; sớm hay trễ so với giờ dự kiến KHÔNG hỏi lý do
// (gỡ 16/09/2026). Ghi hỏng: 403 → "ngoài phạm vi"; 400/khác → toast + refetch chi tiết.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, api,
  type SxWorkItem, type SxWorkItemChiTiet, type SxNhanVienChon, type SxLenhNhom,
  type SxHoTroUngVien, type SxSanLuongCuaToi,
  type SxSuCoIn, type SxChoXacNhan,
} from "../api/client";
import { kyThuatMay, type MayChon } from "../api/kyThuatMay";
import { useAuth } from "../auth/useAuth";
import { useDebounced } from "../utils/useDebounced";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { Icon } from "../components/Icons";
import "../components/empty-state.css";
import { BangLoi, EmptyState, ngay, ngayGio } from "./keHoachSxShared";
import { useNapTenDonVi } from "./tenDonVi";
import { ngayToWall, wallMinutes } from "./gantt-time";
import { ThsxLichNgay } from "./ThsxLichNgay";
import { ThsxDanhSach } from "./ThsxDanhSach";
import { ChipKcs, ChipKhuon, ChipLoaiBuoc } from "../components/ChipBuoc";
import { ThsxDrawer, type ThsxDrawerTab } from "./ThsxDrawer";
import { type ThsxExec } from "./ThsxExecPanels";
import { ThsxChoNgoaiBan } from "./ThsxChoNgoaiBan";
import { ChamCho, choNgoaiBan, choTheoViec, tabCho, tongCho, type SxChoCuaViec } from "./thsxChoXacNhan";
import { ThsxSanLuongCuaToi } from "./ThsxSanLuongCuaToi";
import { ThsxSanLuongTab } from "./ThsxSanLuongTab";
import {
  chonHinhBan, sxCoGio, sxDigest, sxNguonIcon, sxSerial,
  ThsxTrangThaiPill,
} from "./thsxShared";
import "./thuc-hien-sx.css";

// ============================ helper thuần ==================================
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function addDays(s: string, n: number): string {
  const [y, mo, d] = s.split("-").map(Number);
  return ymd(new Date(y, mo - 1, d + n));
}
/** Thứ Hai của tuần chứa `d` (đầu cửa sổ mặc định). */
function mondayOf(d: Date): string {
  const wd = d.getDay(); // 0=CN … 6=T7
  const shift = wd === 0 ? -6 : 1 - wd;
  return ymd(new Date(d.getFullYear(), d.getMonth(), d.getDate() + shift));
}
function mondayOfIso(iso: string): string {
  const [y, mo, d] = iso.slice(0, 10).split("-").map(Number);
  return mondayOf(new Date(y, mo - 1, d));
}
/** "14/09 – 20/09" trong năm nay; khác năm nay thì kèm năm ("29/12/2026 – 04/01/2027"). Năm đầy đủ
 *  luôn có ở tooltip. */
function nhanKhoang(tu: string, den: string): string {
  const namNay = String(new Date().getFullYear());
  const dm = (s: string) => `${s.slice(8)}/${s.slice(5, 7)}`;
  if (tu.slice(0, 4) === namNay && den.slice(0, 4) === namNay) return `${dm(tu)} – ${dm(den)}`;
  const namTu = tu.slice(0, 4) !== den.slice(0, 4) ? `/${tu.slice(0, 4)}` : "";
  return `${dm(tu)}${namTu} – ${dm(den)}/${den.slice(0, 4)}`;
}

const CO_TRANG = 20; // lệnh / trang — đơn vị trang của bàn tổ là LỆNH, không phải bước

// View Lịch là lưới CỘT NGÀY như bàn Xếp lịch (15/09/2026) — bỏ zoom Giờ/Ca/Ngày/Tuần. Ba nấc số ngày
// một màn; ◀▶ dời đúng số ngày đang xem.
const SO_NGAY_NAC = [7, 14, 30] as const;
const SO_NGAY_KEY = "thsx.soNgay";
const CHO_THU_KEY = "thsx.hangChoThu";

function readSoNgay(): number {
  const s = typeof localStorage !== "undefined" ? Number(localStorage.getItem(SO_NGAY_KEY)) : NaN;
  return (SO_NGAY_NAC as readonly number[]).includes(s) ? s : 7;
}

// Kiểu view bàn tổ: "danh_sach" (bảng tràn màn), "lich" (Gantt) hay "san_luong" (tab Sản lượng, spec
// 2026-09-14 §6). View "Thẻ" đã gỡ 14/09/2026 — máy nào còn lưu "the" thì rơi về mặc định Bảng.
type ThsxView = "danh_sach" | "lich" | "san_luong";
const VIEW_KEY = "thsx.view";

function readView(): ThsxView {
  const s = typeof localStorage !== "undefined" ? localStorage.getItem(VIEW_KEY) : null;
  return s === "lich" || s === "san_luong" ? s : "danh_sach";
}

// Dialog lý do: chỉ còn Tạm dừng (luôn hỏi).
type Reason = { kind: "tam_dung" };

// ============================ controller =====================================
export function ThucHienSxPage({
  teamId,
  tenTo,
  laTho = false,
  eventTick,
  vatTuDeNghiDem,
  dinhKemDem,
  onXemCongViec,
  onBadgeStale,
}: {
  teamId: number;
  tenTo?: string;
  /** Người đang xem vào tổ này với tư cách THỢ (cờ `la_tho` của `GET /teams`, do máy chủ tính).
   *  Bật băng "Sản lượng của tôi" theo cờ này chứ không suy từ scope ở FE. */
  laTho?: boolean;
  eventTick?: number;
  /** Số lần đề nghị cấp vật tư đổi, ĐẾM THEO công việc (SSE, mắc ở AppShell). CỐ TÌNH không đi qua
   *  `eventTick`: sự kiện này broadcast TOÀN HỆ, nếu bump tick chung thì mỗi lần bất kỳ tổ nào
   *  trong nhà máy gửi đề nghị là drawer của mọi người gọi lại API. Chỉ nạp lại khi số đếm CỦA
   *  RIÊNG việc đang mở tăng — một sự kiện, nhiều nhất MỘT lượt gọi lại. */
  vatTuDeNghiDem?: Record<number, number>;
  /** Bộ đếm SSE tệp đính kèm theo LỆNH — chuyển xuống thẻ "Tệp của lệnh" của drawer. */
  dinhKemDem?: Record<number, number>;
  /** Báo lên AppShell việc đang mở drawer, để nó khỏi bắn toast cho chính việc đó. */
  onXemCongViec?: (id: number | null) => void;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  // Bàn tổ hiện TÊN đơn vị lấy từ danh mục ("tờ", "bản kẽm") chứ không hiện MÃ ("to", "kem") —
  // nạp một lần ở đây cho cả cây con (drawer · ghi sản lượng · KCS · kho) dùng `nhanDonVi`.
  useNapTenDonVi();

  // Bàn tổ có HAI hình dữ liệu (11/09/2026): `lenh` = một TRANG lệnh/bài ghép (view Danh
  // sách, máy chủ đã gom và cắt trang theo LỆNH); `items` = mảng bước phẳng (view Lịch/Gantt —
  // trục thời gian không có tầng lệnh). Đúng một hình được nạp mỗi lần, tuỳ `view`.
  const [items, setItems] = useState<SxWorkItem[] | null>(null);
  const [lenh, setLenh] = useState<SxLenhNhom[] | null>(null);
  const [trang, setTrang] = useState(1);
  const [tongLenh, setTongLenh] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<SxNhanVienChon[]>([]);
  const [hoTroUngVien, setHoTroUngVien] = useState<SxHoTroUngVien[]>([]);
  // Ngày XƯỞNG máy chủ trả kèm danh sách người — ô chọn so đơn nghỉ phép với ngày này.
  const [ungVienHomNay, setUngVienHomNay] = useState<string | null>(null);
  // Nhịp nạp lại hai danh sách người. Tình trạng (đang chạy việc nào, chờ mấy việc) đổi theo việc
  // của TỔ KHÁC mà bàn này không nhận sự kiện, nên mỗi lần mở ô chọn là nạp lại cho tươi.
  const [ungVienTick, setUngVienTick] = useState(0);
  const lamMoiUngVien = useCallback(() => setUngVienTick((n) => n + 1), []);
  const [mayOptions, setMayOptions] = useState<MayChon[]>([]);

  // Việc chờ tổ bấm (§11.5) — bàn giao đến · hỗ trợ chéo chờ bên tổ mình · lỗi KCS chưa xem (máy chủ
  // lọc theo quyền). Không còn hộp đầu trang: thành chấm đỏ trên dòng công đoạn / đầu lệnh / tab ngăn.
  const [choXn, setChoXn] = useState<SxChoXacNhan | null>(null);
  // Ô "chờ xác nhận" trên thanh lọc: bật thì máy chủ chỉ trả lệnh có việc chờ (lọc TRƯỚC khi cắt trang).
  const [chiCho, setChiCho] = useState(false);
  const [g5Tick, setG5Tick] = useState(0); // nhịp refetch riêng cho G5 sau mỗi lệnh ghi

  const [winTu, setWinTu] = useState<string>(() => mondayOf(new Date()));
  const [soNgay, setSoNgay] = useState<number>(readSoNgay);
  useEffect(() => { localStorage.setItem(SO_NGAY_KEY, String(soNgay)); }, [soNgay]);
  const winDen = useMemo(() => addDays(winTu, soNgay - 1), [winTu, soNgay]);
  const [choThu, setChoThu] = useState<boolean>(() =>
    typeof localStorage !== "undefined" && localStorage.getItem(CHO_THU_KEY) === "1");
  useEffect(() => { localStorage.setItem(CHO_THU_KEY, choThu ? "1" : "0"); }, [choThu]);
  const [view, setView] = useState<ThsxView>(readView);
  useEffect(() => { localStorage.setItem(VIEW_KEY, view); }, [view]);

  const [q, setQ] = useState("");
  const qd = useDebounced(q, 200);
  const choMap = useMemo(() => choTheoViec(choXn), [choXn]);
  const soChoXn = tongCho(choXn);
  const ngoaiBan = useMemo(() => choNgoaiBan(choXn), [choXn]);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Tab mở sẵn của drawer + nhịp remount: công đoạn đang có việc chờ thì vào thẳng tab nơi bấm (Nhận /
  // KCS / Bàn giao), kể cả khi đúng việc đó đang mở sẵn ở tab khác.
  const [tabDau, setTabDau] = useState<ThsxDrawerTab>("van_hanh");
  const [moLan, setMoLan] = useState(0);
  const [chiTiet, setChiTiet] = useState<SxWorkItemChiTiet | null>(null);
  const [ctLoading, setCtLoading] = useState(false);

  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [reason, setReason] = useState<Reason | null>(null);
  const [reasonText, setReasonText] = useState("");

  // ---- nạp dữ liệu ----
  // Từ khoá chỉ gửi máy chủ ở view Bảng. View Lịch lọc trên máy nên gõ tìm KHÔNG được nạp lại:
  // trước đây mỗi nhịp debounce bắn thêm một GET y hệt cửa sổ đang có (đo 15/09/2026).
  const timMayChu = view === "danh_sach" ? qd.trim() : "";
  const loadItems = useCallback(() => {
    // Tab Sản lượng tự nạp dữ liệu riêng — khỏi kéo trang lệnh về cho một bảng không hiện.
    if (!token || view === "san_luong") return;
    setErr(null);
    const phang = view === "lich";
    api.sanXuat.workItems(token, {
      teamId,
      nhom: phang ? "phang" : "lenh",
      // Tìm kiếm lọc Ở MÁY CHỦ, trước khi cắt trang — lọc bằng JS sau khi trang về thì ô tìm
      // kiếm chỉ soi được đúng 20 lệnh đang hiện. Chế độ phẳng kéo trọn bàn nên màn tự lọc.
      ...(phang ? { tuNgay: winTu, denNgay: winDen } : { tim: timMayChu || undefined, trang, coTrang: CO_TRANG }),
      choXacNhan: chiCho || undefined,
    })
      .then((r) => {
        // Hình nào là do CỜ `nhom` của máy chủ quyết, không do "có mảng lệnh hay không" —
        // xem `chonHinhBan`.
        const h = chonHinhBan(r);
        setItems(h.cong_viec);
        setLenh(h.lenh);
        setTongLenh(h.tongLenh);
        setErr(null);
      })
      .catch((e: unknown) => setErr(e instanceof ApiError
        ? (e.isForbidden ? "Tổ này ngoài phạm vi của bạn." : e.message)
        : String(e)));
  }, [token, teamId, view, timMayChu, trang, winTu, winDen, chiCho]);

  // SSE bump (`eventTick`) nạp lại nhưng GIỮ NGUYÊN `trang` — nhảy về trang 1 giữa lúc tổ đang
  // thao tác ở trang 3 là cướp chỗ đứng của người ta.
  useEffect(() => { loadItems(); }, [loadItems, eventTick]);
  // Đổi tổ / đổi từ khoá / đổi chế độ lọc ⇒ trang cũ không còn nghĩa, về trang 1.
  useEffect(() => { setTrang(1); }, [teamId, qd, chiCho]);
  // Đổi tổ thì tắt ô "chờ xác nhận" — ô đó là của bàn trước.
  useEffect(() => { setChiCho(false); }, [teamId]);
  const soTrang = Math.max(1, Math.ceil(tongLenh / CO_TRANG));

  // Luỹ kế sản lượng tháng của CHÍNH mình — CHỈ nạp khi vào tổ với tư cách THỢ (§6). Tổ trưởng
  // không có băng này: bảng ai-được-bao-nhiêu của cả tổ đã nằm trong drawer từng mẻ.
  // Nạp lại theo `eventTick` để vừa chốt một bản chia xong là con số nhích ngay, không phải F5.
  const [slToi, setSlToi] = useState<SxSanLuongCuaToi | null>(null);
  useEffect(() => {
    if (!token || !laTho) { setSlToi(null); return; }
    const nay = new Date();
    api.sanXuat.sanLuongCuaToi(token, nay.getFullYear(), nay.getMonth() + 1)
      .then(setSlToi)
      .catch(() => setSlToi(null));
  }, [token, laTho, eventTick]);

  // Tổ THẬT của việc đang mở: bàn nút cha gộp việc của nhiều tổ con, nên danh chọn người và xác nhận
  // nhận vật tư đi theo tổ của việc; chưa mở việc nào thì dùng nút đang xem.
  const toCuaViec = chiTiet?.cong_viec.department_id ?? teamId;

  // Ứng viên "Giao người" — endpoint riêng module (KHÔNG dùng api.employees vì gác quyền nhan_su).
  useEffect(() => {
    if (!token) return;
    api.sanXuat.nhanVienChon(token, toCuaViec)
      .then((r) => { setCandidates(r.nhan_vien); setUngVienHomNay(r.hom_nay); })
      .catch(() => setCandidates([]));
  }, [token, toCuaViec, ungVienTick]);

  // Ứng viên HỖ TRỢ CHÉO (§9) — thợ tổ SX khác đang làm; đổi tổ → dọn cache lý do (danh mục chung, giữ được).
  useEffect(() => {
    if (!token) return;
    api.sanXuat.hoTroUngVien(token, toCuaViec)
      .then((r) => setHoTroUngVien(r.nhan_vien))
      .catch(() => setHoTroUngVien([]));
  }, [token, toCuaViec, ungVienTick]);

  // Máy chọn được cho "Đổi máy" §7.2 — endpoint hẹp `may-chon` (KHÔNG dùng `mayThietBi.list`: đòi
  // quyền `dm_thiet_bi` mà thợ đứng máy không có). Danh mục máy CHUNG toàn hệ thống, không theo tổ.
  useEffect(() => {
    if (!token) return;
    kyThuatMay.mayChon(token)
      .then(setMayOptions)
      .catch(() => setMayOptions([]));
  }, [token]);

  // Đổi tổ → dọn lựa chọn.
  useEffect(() => { setSelectedId(null); setChiTiet(null); }, [teamId]);

  // ---- chi tiết việc đang chọn (drawer) ----
  const loadChiTiet = useCallback((id: number | null) => {
    if (!token || id == null) { setChiTiet(null); return Promise.resolve(); }
    setCtLoading(true);
    return api.sanXuat.chiTiet(token, id)
      .then((r) => { setChiTiet(r); })
      .catch(() => { setChiTiet(null); })
      .finally(() => setCtLoading(false));
  }, [token]);

  // `mutate` đang chờ máy chủ lưu (từ lúc gửi tới lúc bắt đầu nạp lại chi tiết).
  const dangGhi = useRef(false);
  useEffect(() => { void loadChiTiet(selectedId); }, [loadChiTiet, selectedId]);
  // Sự kiện SX (SSE) → nạp lại việc đang mở. Đang có lượt ghi của chính mình thì BỎ: `mutate` nạp
  // lại ngay sau khi lưu xong, lượt đó bắt đầu sau mọi sự kiện về trước nó nên đã phủ luôn. Không
  // bỏ thì SSE của chính cú bấm (về TRƯỚC phản hồi POST) đẻ một GET song song — đo 16/09/2026 hai
  // GET chồng nhau kéo mỗi cái từ ~330 ms lên ~570 ms.
  const tickDaNap = useRef(eventTick);
  useEffect(() => {
    if (tickDaNap.current === eventTick) return;
    tickDaNap.current = eventTick;
    if (dangGhi.current) return;
    void loadChiTiet(selectedId);
  }, [eventTick, loadChiTiet, selectedId]);

  // Đề nghị vật tư đổi (SSE): CHỈ nạp lại khi số đếm CỦA RIÊNG việc đang mở tăng. So theo cặp
  // (việc, số đếm) nên đổi việc KHÔNG kéo theo một lượt gọi thừa — effect ngay trên vừa nạp rồi.
  const vtDaXem = useRef<{ cv: number | null; dem: number }>({ cv: null, dem: 0 });
  // Mốc thao tác ghi GẦN NHẤT của chính người này (`mutate` đặt HAI lần: trước khi gọi API và sau
  // khi nạp lại xong) — để tín hiệu SSE vọng về từ chính cú bấm đó không bắt nạp lần hai.
  const vuaTuNap = useRef(0);
  const vtDem = selectedId != null ? (vatTuDeNghiDem?.[selectedId] ?? 0) : 0;
  useEffect(() => {
    const truoc = vtDaXem.current;
    if (selectedId == null || truoc.cv !== selectedId || vtDem === truoc.dem) {
      vtDaXem.current = { cv: selectedId, dem: vtDem };
      return;
    }
    const nap = () => {
      vtDaXem.current = { cv: selectedId, dem: vtDem };
      void loadChiTiet(selectedId);
    };
    // Người VỪA bấm đã được `mutate` nạp lại xong, rồi sự kiện SSE của chính họ vọng về ngay sau
    // đó: nạp ngay là một lượt gọi API thừa cho đúng dữ liệu vừa lấy.
    const con = 2000 - (Date.now() - vuaTuNap.current);
    if (con <= 0) { nap(); return; }
    // …nhưng KHÔNG được vứt sự kiện rơi vào cửa đó. Cửa mở vì thao tác của CHÍNH mình, mà sự kiện
    // rơi vào có thể là của tổ trưởng khác — bỏ qua rồi đánh dấu "đã xem" là drawer đứng số cũ vô
    // thời hạn, không toast (AppShell im vì đúng việc đang mở) và không tự sửa theo thời gian.
    // Nên: hẹn ĐÚNG phần còn lại của cửa rồi nạp một lượt. `vtDaXem` chỉ ghi khi thật sự nạp, nên
    // nếu effect chạy lại giữa chừng thì sự kiện vẫn còn nguyên là "chưa xem". Một hẹn duy nhất —
    // không vòng lặp thăm dò, và vẫn đúng "một sự kiện nhiều nhất một lượt gọi API".
    const h = setTimeout(nap, con);
    return () => clearTimeout(h);
  }, [vtDem, selectedId, loadChiTiet]);

  // Cho AppShell biết drawer đang mở việc nào — nó dùng để KHÔNG bắn toast cho chính việc đó.
  useEffect(() => {
    onXemCongViec?.(selectedId);
    return () => onXemCongViec?.(null);
  }, [onXemCongViec, selectedId]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  /* Khối "thưởng/phạt tổ trưởng" GỠ 11/09/2026 (mg `0297`) — sản xuất thôi giữ tiền. */

  // Hộp thư LỖI KCS đã GỠ khỏi màn production (Task 9 §6.4, mg 0250 kiêm nhiệm) — luồng phản hồi
  // trách nhiệm cũ (pending/accepted/rejected) không còn hiện ở UI mới; hồ sơ cũ vẫn đọc được qua
  // drawer lịch sử nếu cần, chỉ KHÔNG polling/hiện thanh cảnh báo ở bàn tổ thường nữa.

  // Hộp thư KHO nhập thành phẩm ĐÃ GỠ 17/09/2026: KCS gửi thành phẩm thành yêu cầu NHẬP thật, kho
  // nhận ở Hộp yêu cầu của module Kho (design nhập kho thành phẩm qua Yêu cầu nhập xuất).

  // Việc chờ tổ bấm — nạp lại theo SSE (bàn giao/hỗ trợ đổi ở tổ kia) và sau mỗi lệnh ghi (kể cả ghi
  // trong ngăn chi tiết: xác nhận nhận hàng xong thì chấm đỏ phải tắt ngay, không chờ SSE).
  const [choTick, setChoTick] = useState(0);
  useEffect(() => {
    if (!token) { setChoXn(null); return; }
    let alive = true;
    api.sanXuat.choXacNhan(token, teamId)
      .then((r) => { if (alive) setChoXn(r); })
      .catch(() => { if (alive) setChoXn(null); });
    return () => { alive = false; };
  }, [token, teamId, eventTick, g5Tick, choTick]);
  // Hết việc chờ thì ô lọc tự tắt — để bật mà bảng trống trơn thì tổ tưởng mất lệnh.
  useEffect(() => { if (chiCho && choXn && soChoXn === 0) setChiCho(false); }, [chiCho, choXn, soChoXn]);

  // ---- lọc + gom nhóm cột trái / cluster timeline ----
  const winStartW = useMemo(() => ngayToWall(winTu), [winTu]);
  const winEndW = useMemo(() => ngayToWall(winDen) + 1440, [winDen]);

  const overlaps = useCallback((w: SxWorkItem): boolean => {
    if (!sxCoGio(w)) return false;
    const s = wallMinutes(w.du_kien_bat_dau as string);
    const e = wallMinutes(w.du_kien_ket_thuc as string);
    if (!Number.isFinite(s) || !Number.isFinite(e)) return false;
    return s < winEndW && e > winStartW;
  }, [winStartW, winEndW]);

  const match = useCallback((w: SxWorkItem): boolean => {
    const kw = qd.trim().toLowerCase();
    if (!kw) return true;
    return [w.nguon_ma, w.ten_cong_doan, w.may, w.nguon_ten, w.khach_hang]
      .some((s) => (s || "").toLowerCase().includes(kw));
  }, [qd]);

  const startW = (w: SxWorkItem) => wallMinutes(w.du_kien_bat_dau as string);
  const groups = useMemo(() => {
    const filtered = (items ?? []).filter(match);
    const timed = filtered.filter(overlaps).sort((a, b) => startW(a) - startW(b));
    const outWin = filtered.filter((w) => sxCoGio(w) && !overlaps(w)).sort((a, b) => startW(a) - startW(b));
    const untimed = filtered.filter((w) => !sxCoGio(w));
    return { tong: filtered.length, timed, outWin, untimed };
  }, [items, match, overlaps]);

  // Hàng chờ của view Lịch = việc KHÔNG vẽ được lên lưới đang xem (chưa định giờ / ngoài cửa sổ);
  // việc trong cửa sổ đã là một dòng trên lưới, lặp lại ở cột trái chỉ là nhiễu.
  const soCho = groups.untimed.length + groups.outWin.length;
  // Băng KPI đọc từ hình đang nạp: chế độ lệnh cộng `digest` của TRANG hiện tại (mỗi lệnh đã có
  // sẵn bốn con số từ máy chủ), chế độ phẳng đếm thẳng trên mảng bước.
  const digest = useMemo(() => {
    if (lenh == null) return sxDigest(items ?? []);
    const d = { tong: 0, released: 0, running: 0, paused: 0, completed: 0 };
    for (const l of lenh) {
      d.tong += l.so_viec;
      d.released += l.digest.released;
      d.running += l.digest.running;
      d.paused += l.digest.paused;
      d.completed += l.digest.completed;
    }
    return d;
  }, [lenh, items]);

  // ---- chọn việc: mở drawer + (nếu ngoài cửa sổ) dời cửa sổ tới tuần của việc ----
  const pickViec = useCallback((w: SxWorkItem) => {
    if (sxCoGio(w) && !overlaps(w)) setWinTu(mondayOfIso(w.du_kien_bat_dau as string));
    setTabDau(tabCho(choMap.get(w.id)));
    setSelectedId(w.id);
  }, [overlaps, choMap]);
  const closePanel = useCallback(() => setSelectedId(null), []);

  // ---- ghi (khoá lạc quan) ----
  const handleErr = useCallback((e: unknown) => {
    if (e instanceof ApiError) {
      if (e.isForbidden) { setToast("Ngoài phạm vi — bạn không thao tác được việc này."); return; }
      setToast(e.message || "Không lưu được — đã tải lại bản mới.");
      void loadChiTiet(selectedId);
      return;
    }
    setToast("Lỗi mạng — thử lại.");
  }, [loadChiTiet, selectedId]);

  const mutate = useCallback(async <T,>(run: () => Promise<T>, ok: string): Promise<T | null> => {
    if (!token || selectedId == null) return null;
    setBusy(true);
    // Mốc đặt TRƯỚC cả `run()`: BE gọi `hub.broadcast(...)` TRƯỚC khi `return`, nên gói SSE của
    // chính cú bấm này có thể tới trình duyệt SỚM HƠN lúc `run()` resolve. Mốc đặt sau `run()` là
    // đã muộn — tín hiệu cần chặn đã đi qua cửa rồi.
    vuaTuNap.current = Date.now();
    dangGhi.current = true;
    let r: T;
    try {
      r = await run();
    } catch (e) {
      dangGhi.current = false;
      handleErr(e);
      setBusy(false);
      return null;
    }
    setReason(null);
    setReasonText("");
    setToast(ok);
    // Trả kết quả NGAY khi máy chủ đã lưu để hộp nhập (Ghi mẻ, Đề xuất bàn giao…) đóng liền. Trước
    // đây hộp đứng chờ nạp lại cả chi tiết việc: đo 16/09/2026 lưu mất 87 ms mà hộp 688 ms mới
    // đóng. `busy` giữ tới khi nạp xong nên nút trong drawer không bấm được trên số cũ.
    const nap = loadChiTiet(selectedId);
    dangGhi.current = false;
    void nap.finally(() => {
      // Đặt LẠI sau khi nạp xong: mốc đầu phủ khoảng sự kiện về SỚM, mốc này phủ khoảng nó về
      // MUỘN hơn lượt nạp. Cùng cửa 2 giây, không đẻ cơ chế mới.
      vuaTuNap.current = Date.now();
      loadItems();
      setChoTick((t) => t + 1);
      onBadgeStale?.();
      setBusy(false);
    });
    return r;
  }, [token, selectedId, loadChiTiet, loadItems, onBadgeStale, handleErr]);

  // Ghi G5 trong DRAWER (cần việc đang chọn): refetch chi tiết + việc + nhịp G5; badge tổ nháy.
  // Ghi từ HỘP THƯ mức trang (không cần drawer): hỗ trợ chéo · kho xác nhận nhập/nhận.
  const mutateInbox = useCallback(async (run: () => Promise<unknown>, ok: string): Promise<boolean> => {
    if (!token) return false;
    setBusy(true);
    try {
      await run();
      if (selectedId != null) await loadChiTiet(selectedId);
      loadItems();
      onBadgeStale?.();
      setToast(ok);
      return true;
    } catch (e) {
      handleErr(e);
      return false;
    } finally {
      setBusy(false);
      setG5Tick((t) => t + 1);
    }
  }, [token, selectedId, loadChiTiet, loadItems, onBadgeStale, handleErr]);

  // KCS báo lỗi về tổ — một chiều, không Nhận/Từ chối trách nhiệm. Không có nút "Đã xem" ở đâu cả:
  // mở tab KCS của ngăn chi tiết = tổ đã xem (18/09/2026), kể cả mở từ danh sách ngoài bàn. Lặng lẽ:
  // không toast, không khoá nút của ngăn — nhãn "Tổ đã xem (…) · giờ" hiện ngay trong tab là đủ báo.
  const kcsLoiChoXem = useMemo(() => new Set((choXn?.kcs_loi ?? []).map((l) => l.loi_id)), [choXn]);
  const onXemKcs = useCallback((loiIds: number[]) => {
    if (!token) return;
    void Promise.all(loiIds.map((id) => api.sanXuat.daXemLoiKcs(token, id)))
      .then(() => {
        loadItems();
        onBadgeStale?.();
      })
      .catch(handleErr)
      .finally(() => setG5Tick((t) => t + 1));
  }, [token, loadItems, onBadgeStale, handleErr]);

  const onMoBanGiaoCho = useCallback((dichCongViecId: number) => {
    setTabDau("nhan");
    setMoLan((n) => n + 1);
    setSelectedId(dichCongViecId);
  }, []);
  // "Mở" lỗi KCS: ngăn chi tiết công đoạn bị báo lỗi, mở thẳng tab KCS.
  const onMoKcsCho = useCallback((congViecId: number) => {
    setTabDau("kcs");
    setMoLan((n) => n + 1);
    setSelectedId(congViecId);
  }, []);
  const onXacNhanHoTroCho = useCallback((id: number, version: number) => {
    void mutateInbox(() => api.sanXuat.xacNhanHoTro(token!, id, { expected_version: version }),
      "Đã xác nhận hỗ trợ chéo.");
  }, [mutateInbox, token]);
  const onHuyHoTroCho = useCallback((id: number, lyDo: string, version: number) =>
    mutateInbox(() => api.sanXuat.huyHoTro(token!, id, { ly_do: lyDo || null, expected_version: version }),
      "Đã từ chối lời mời hỗ trợ."), [mutateInbox, token]);

  const ver = () => chiTiet?.version;

  const onGiao = useCallback((employeeId: number) => {
    if (selectedId == null) return;
    void mutate(() => api.sanXuat.phanCong(token!, selectedId, { employee_id: employeeId, expected_version: ver() }),
      "Đã giao người vào việc.");
  }, [mutate, token, selectedId, chiTiet]);

  const onRut = useCallback((phanCongId: number) => {
    if (selectedId == null) return;
    void mutate(() => api.sanXuat.rut(token!, phanCongId, { expected_version: ver() }),
      "Đã rút người khỏi việc.");
  }, [mutate, token, selectedId, chiTiet]);

  // Đổi máy §7.2 mở rộng — `ver()` cần `chiTiet` tươi trong deps (khác các mặt exec khác vốn nhận
  // version qua tham số của người gọi), nên tách riêng thay vì viết trực tiếp trong `exec` useMemo.
  const onDoiMay = useCallback((mayId: number, lyDo?: string | null) => mutate(() => api.sanXuat.doiMay(token!, selectedId!, {
    may_id: mayId, ly_do: lyDo ?? null, expected_version: ver(),
  }), "Đã đổi máy.").then((r) => r != null), [mutate, token, selectedId, chiTiet]);

  // Báo sự cố §7.2 mở rộng — cùng lý do tách riêng như `onDoiMay`: cần `chiTiet` tươi cho `ver()`.
  // Toast gọi tên MÃ YÊU CẦU vừa sinh để tổ trưởng bám theo được ở màn Sửa chữa máy; `mutate` chỉ
  // nhận chuỗi cố định nên tự đặt toast sau khi có kết quả.
  const onBaoSuCo = useCallback((body: SxSuCoIn) => mutate(
    () => api.sanXuat.baoSuCo(token!, selectedId!, { ...body, expected_version: ver() }),
    "Đã gửi báo sự cố tới tổ sửa chữa.",
  ).then((r) => {
    if (r) setToast(`Đã gửi ${r.yeu_cau_ma} tới tổ sửa chữa${body.dung_san_xuat ? " · công việc đã tạm dừng" : ""}.`);
    return r != null;
  }), [mutate, token, selectedId, chiTiet]);

  // Bắt đầu / Tiếp tục: thẳng, không hỏi gì — kíp chuẩn đã gỡ (mg `0321`) nên không còn "số người
  // khác dự kiến"; sớm hay trễ so với giờ dự kiến cũng không hỏi.
  const onBatDau = useCallback(() => {
    if (selectedId != null) void mutate(() => api.sanXuat.batDau(token!, selectedId, { expected_version: ver() }), "Đã bắt đầu.");
  }, [chiTiet, mutate, token, selectedId]);

  // Nhận / trả khuôn (04/09/2026). Nhận là thứ DUY NHẤT mở cổng Bắt đầu cho bước cần dụng cụ —
  // không hỏi lý do gì cả: người bấm là người đang cầm con dao trong tay.
  const onNhanKhuon = useCallback(() => {
    if (selectedId != null) {
      void mutate(() => api.sanXuat.nhanKhuon(token!, selectedId), "Đã nhận khuôn.");
    }
  }, [mutate, token, selectedId]);

  const onTraKhuon = useCallback(() => {
    if (selectedId != null) {
      void mutate(() => api.sanXuat.traKhuon(token!, selectedId), "Đã trả khuôn về kệ.");
    }
  }, [mutate, token, selectedId]);

  // Tạm dừng: lý do BẮT BUỘC luôn.
  const onTamDung = useCallback(() => {
    setReasonText("");
    setReason({ kind: "tam_dung" });
  }, []);

  // Kết thúc: không hỏi lý do, sớm hay trễ đều bấm là xong.
  const onKetThuc = useCallback(() => {
    if (selectedId != null) void mutate(() => api.sanXuat.ketThuc(token!, selectedId, { expected_version: ver() }), "Đã kết thúc.");
  }, [chiTiet, mutate, token, selectedId]);

  // Nút chạy nhanh trên DÒNG bảng: mở drawer rồi ĐỢI chi tiết của đúng việc đó về mới bấm. Ba hàm
  // trên đọc `chiTiet`/`selectedId` hiện hành — gọi ngay trong cú bấm là nhắm vào việc đang mở
  // trước đó (hoặc không làm gì khi chưa mở việc nào).
  const [choLam, setChoLam] = useState<{ id: number; viec: "bat_dau" | "tam_dung" | "ket_thuc" } | null>(null);
  const lamNhanh = useCallback((w: SxWorkItem, viec: "bat_dau" | "tam_dung" | "ket_thuc") => {
    pickViec(w);
    setChoLam({ id: w.id, viec });
  }, [pickViec]);
  useEffect(() => {
    if (!choLam || ctLoading || !chiTiet || chiTiet.cong_viec.id !== choLam.id) return;
    setChoLam(null);
    if (!chiTiet.quyen?.run_order) return;
    if (choLam.viec === "bat_dau") {
      // Cùng cổng với nút Bắt đầu ở chân drawer. Chưa đủ thì chỉ mở drawer — chân drawer đã nói lý do.
      const coKhoan = (chiTiet.phan_cong ?? []).some((p) => p.trang_thai === "active" && p.la_luong_khoan);
      const choKhuon = !!chiTiet.cong_viec.khuon && !chiTiet.cong_viec.khuon_da_nhan;
      if (coKhoan && !choKhuon) onBatDau();
    } else if (choLam.viec === "tam_dung") onTamDung();
    else onKetThuc();
  }, [choLam, ctLoading, chiTiet, onBatDau, onTamDung, onKetThuc]);

  const confirmReason = useCallback(() => {
    if (!reason || selectedId == null) return;
    const txt = reasonText.trim();
    void mutate(() => api.sanXuat.tamDung(token!, selectedId, { ly_do: txt, expected_version: ver() }), "Đã tạm dừng.");
  }, [reason, reasonText, mutate, token, selectedId, chiTiet]);

  // ---- Giai đoạn 3+4: hợp đồng các mặt GHI cho drawer (mọi mặt qua `mutate` → refetch + toast) ----
  const exec = useMemo<ThsxExec>(() => {
    const ok = (p: Promise<unknown | null>) => p.then((r) => r != null);
    return {
      doiMay: onDoiMay,
      baoSuCo: onBaoSuCo,
      taoBatch: (b) => mutate(() => api.sanXuat.taoBatch(token!, selectedId!, b), "Đã ghi mẻ sản lượng.")
        .then((r) => (r ? r.ket_qua_lsx ?? [] : null)),
      deXuatBanGiao: (b) => ok(mutate(() => api.sanXuat.deXuatBanGiao(token!, selectedId!, b), "Đã đề xuất bàn giao.")),
      suaBanGiao: (id, b) => ok(mutate(() => api.sanXuat.suaBanGiao(token!, id, b), "Đã sửa mẻ bàn giao.")),
      xacNhanBanGiao: (id, v) => ok(mutate(() => api.sanXuat.xacNhanBanGiao(token!, id, { expected_version: v }), "Đã xác nhận bàn giao.")),
      dieuChinhBanGiao: (id, b) => ok(mutate(() => api.sanXuat.dieuChinhBanGiao(token!, id, b), "Đã điều chỉnh bàn giao.")),
      xacNhanVatTu: (voucherId) => ok(mutate(() => api.sanXuat.xacNhanVatTu(token!, { voucher_id: voucherId, department_id: toCuaViec }), "Đã xác nhận nhận vật tư.")),
      // Đề nghị cấp vật tư: 400 = vi phạm nghiệp vụ, `handleErr` hiện NGUYÊN VĂN câu tiếng Việt
      // của BE (kho đã lập phiếu, đề nghị đã huỷ…) — không nuốt thành "Có lỗi xảy ra".
      deNghiVatTu: (cvId, b) => ok(mutate(() => api.sanXuat.deNghiVatTu(token!, cvId, b), "Đã gửi đề nghị cấp vật tư.")),
      suaDeNghiVatTu: (cvId, dnId, b) => ok(mutate(() => api.sanXuat.suaDeNghiVatTu(token!, cvId, dnId, b), "Đã lưu đề nghị cấp vật tư.")),
      deXuatHoTro: (b) => ok(mutate(() => api.sanXuat.deXuatHoTro(token!, selectedId!, b), "Đã đề xuất hỗ trợ.")),
      xacNhanHoTro: (id, v) => ok(mutate(() => api.sanXuat.xacNhanHoTro(token!, id, { expected_version: v }), "Đã xác nhận hỗ trợ.")),
      huyHoTro: (id, lyDo, v) => ok(mutate(() => api.sanXuat.huyHoTro(token!, id, { ly_do: lyDo || null, expected_version: v }), "Đã huỷ hỗ trợ.")),
      capNhatDanhMucMe: (batchId) => ok(mutate(() => api.sanXuat.capNhatDanhMucMe(token!, batchId), "Đã cập nhật mẻ theo danh mục.")),
    };
  }, [mutate, token, selectedId, toCuaViec, onDoiMay, onBaoSuCo]);

  const panelOpen = selectedId != null;

  // Ngăn chi tiết là lớp NỔI (trượt từ phải, nền mờ) như drawer danh mục — Esc đóng như ở đó.
  // Nhường Esc cho lớp trên nó: hộp thoại xác nhận (`.cdlg-overlay`) và ô nào đã tự nuốt phím.
  useEffect(() => {
    if (!panelOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (document.querySelector(".cdlg-overlay")) return;
      closePanel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [panelOpen, closePanel]);

  // ============================ render =======================================
  return (
    <div className="thsx">
      {/* Thanh trên */}
      <div className="thsx-top">
        <div className="thsx-top__hang">
          <div className="thsx-top__title">
            <Icon name="users" size={20} />
            <span>Bàn tổ · {tenTo ?? `#${teamId}`}</span>
          </div>
          <div className="thsx-top__spacer" />
          <div className="thsx-seg" role="group" aria-label="Kiểu xem">
            <button type="button" className="thsx-seg__btn" title="Xem danh sách bản ghi (Bảng)"
              aria-pressed={view === "danh_sach"} onClick={() => setView("danh_sach")}>
              <Icon name="table" size={13} /> Bảng
            </button>
            <button type="button" className="thsx-seg__btn" title="Xem theo lịch (Gantt)"
              aria-pressed={view === "lich"} onClick={() => setView("lich")}>
              <Icon name="layout" size={13} /> Lịch
            </button>
            <button type="button" className="thsx-seg__btn" title="Sản lượng theo lệnh, công đoạn, người"
              aria-pressed={view === "san_luong"} onClick={() => { setSelectedId(null); setView("san_luong"); }}>
              <Icon name="activity" size={13} /> Sản lượng
            </button>
          </div>
        </div>
        {/* Hàng 2 — CHỈ view Lịch: điều hướng ngày bên trái (đọc trước), số liệu bên phải. */}
        {view === "lich" && (
          <div className="thsx-top__hang">
            <div className="thsx-top__grp">
              <button type="button" className="thsx-nutnay" onClick={() => setWinTu(mondayOf(new Date()))}>
                Hôm nay
              </button>
              <div className="thsx-kyngay">
                <button type="button" title="Kỳ trước" aria-label="Kỳ trước"
                  onClick={() => setWinTu((s) => addDays(s, -soNgay))}>
                  <Icon name="chevron" size={16} className="thsx-rot90" />
                </button>
                <span className="thsx-kyngay__nhan thsx-num" title={`${ngay(winTu)} – ${ngay(winDen)} · ${soNgay} ngày`}>
                  <Icon name="calendar" size={13} />
                  {nhanKhoang(winTu, winDen)}
                </span>
                <button type="button" title="Kỳ sau" aria-label="Kỳ sau"
                  onClick={() => setWinTu((s) => addDays(s, soNgay))}>
                  <Icon name="chevron" size={16} className="thsx-rot270" />
                </button>
              </div>
              <div className="thsx-songay" role="group" aria-label="Số ngày một màn">
                {SO_NGAY_NAC.map((n) => (
                  <button key={n} type="button" className="thsx-songay__btn"
                    aria-pressed={soNgay === n} onClick={() => setSoNgay(n)}>
                    {n} Ngày
                  </button>
                ))}
              </div>
            </div>
            <ONutCho so={soChoXn} bat={chiCho} onDoi={setChiCho} />
            <div className="thsx-top__spacer" />
            <div className="thsx-kpi" aria-label="Tổng quan việc của tổ">
              {([
                ["", digest.tong, "việc"],
                ["run", digest.running, "đang chạy"],
                ["pause", digest.paused, "tạm dừng"],
                ["cho", digest.released, "chờ làm"],
                ["done", digest.completed, "xong"],
              ] as const).map(([k, so, chu]) => (
                <span key={chu} className={`thsx-kpi__pill${k ? ` thsx-kpi__pill--${k}` : ""}${so === 0 ? " thsx-kpi__pill--0" : ""}`}>
                  {k && <i aria-hidden="true" />}
                  <strong className="thsx-num">{so}</strong> {chu}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <ThsxSanLuongCuaToi data={slToi} />

      {view === "san_luong" ? (
        <ThsxSanLuongTab teamId={teamId} eventTick={eventTick} />
      ) : (<>
      {/* Thanh phụ: tìm + digest — CHỈ view Bảng. View Lịch để số liệu trên thanh trên và ô tìm ở
          đầu cột Hàng chờ, như bàn Xếp lịch. */}
      {view === "danh_sach" && <div className="thsx-subbar">
        <div className="thsx-search">
          <Icon name="search" size={15} className="thsx-search__ic" />
          <input type="search" className="thsx-search__in" value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã / khách / công đoạn / máy…" aria-label="Tìm trong việc của tổ" />
          {q && (
            <button type="button" className="thsx-search__clear" aria-label="Xoá tìm" onClick={() => setQ("")}>
              <Icon name="x" size={13} />
            </button>
          )}
        </div>
        <ONutCho so={soChoXn} bat={chiCho} onDoi={setChiCho} />
        <div className="thsx-subbar__spacer" />
        <div className="thsx-digest" aria-label="Tổng quan việc của tổ">
          <span className="thsx-digest__chip thsx-digest__chip--tong"><Icon name="clipboard" size={12} /> <b className="thsx-num">{digest.tong}</b> việc</span>
          <span className="thsx-digest__chip thsx-digest__chip--run"><Icon name="play" size={12} /> <b className="thsx-num">{digest.running}</b> đang chạy</span>
          <span className="thsx-digest__chip thsx-digest__chip--pause"><Icon name="pause" size={12} /> <b className="thsx-num">{digest.paused}</b> tạm dừng</span>
          <span className="thsx-digest__chip thsx-digest__chip--released"><Icon name="clock" size={12} /> <b className="thsx-num">{digest.released}</b> chờ làm</span>
          <span className="thsx-digest__chip thsx-digest__chip--done"><Icon name="check" size={12} /> <b className="thsx-num">{digest.completed}</b> xong</span>
        </div>
      </div>}

      {/* Việc chờ TỔ bấm (bàn giao đến, hỗ trợ chéo, lỗi KCS) gắn vào công đoạn của nó (§11.5); chỉ
          việc không có dòng trên bàn mới liệt kê riêng, khi bật ô "chờ xác nhận". */}
      {chiCho && <ThsxChoNgoaiBan
        data={ngoaiBan}
        busy={busy}
        onMoBanGiao={onMoBanGiaoCho}
        onXacNhanHoTro={onXacNhanHoTroCho}
        onHuyHoTro={onHuyHoTroCho}
        onMoKcs={onMoKcsCho}
      />}

      {/* Lưới 3 cột — Tự ẩn sidebar trái khi ở chế độ Bảng để tràn 100% không gian */}
      <div className={`thsx-grid${panelOpen ? " is-panel" : ""}${view !== "lich" ? " thsx-grid--full" : " thsx-grid--lich"}${view === "lich" && choThu ? " thsx-grid--cho-thu" : ""}`}>
        {/* CỘT TRÁI — HÀNG CHỜ, chỉ ở view Lịch: việc chưa định giờ / ngoài khoảng ngày đang xem.
            Việc trong khoảng đã là một dòng trên lưới nên không lặp lại ở đây. Thu gọn được. */}
        {view === "lich" && (choThu ? (
          <aside className="thsx-list thsx-list--thu">
            <button type="button" className="thsx-cho__mo" title="Mở Hàng chờ" aria-label="Mở Hàng chờ"
              onClick={() => setChoThu(false)}>
              <Icon name="layers" size={15} />
              <span className="thsx-cho__mo-dem thsx-num">{soCho}</span>
            </button>
          </aside>
        ) : (
          <aside className="thsx-list">
            <div className="thsx-cho__dau">
              <div className="thsx-cho__tieu">
                <h2>Hàng chờ</h2>
                <span className="thsx-cho__dem thsx-num">{soCho}</span>
                <button type="button" className="thsx-cho__thu" title="Thu gọn Hàng chờ"
                  aria-label="Thu gọn Hàng chờ" onClick={() => setChoThu(true)}>
                  <Icon name="chevron" size={14} className="thsx-rot90" />
                </button>
              </div>
              <div className="thsx-search thsx-search--cho">
                <Icon name="search" size={14} className="thsx-search__ic" />
                <input type="search" className="thsx-search__in" value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Tìm mã / khách / công đoạn / máy…" aria-label="Tìm trong việc của tổ" />
                {q && (
                  <button type="button" className="thsx-search__clear" aria-label="Xoá tìm" onClick={() => setQ("")}>
                    <Icon name="x" size={13} />
                  </button>
                )}
              </div>
            </div>
            <div className="thsx-list__body">
              {err ? (
                <div className="thsx-list__pad"><BangLoi text={err} onRetry={loadItems} /></div>
              ) : items == null ? (
                <ListSkeleton />
              ) : soCho === 0 ? (
                <div className="thsx-cho__trong">
                  <Icon name={q ? "search" : "check"} size={24} />
                  {/* Không tách nhánh "chưa có việc phát hành": `items` chỉ là việc của KHOẢNG NGÀY đang
                      xem, dời sang tuần trống thì tổng về 0 dù tổ vẫn còn việc ở tuần khác. */}
                  <p>{q
                    ? "Không có việc chờ nào khớp từ khoá."
                    : chiCho
                      ? "Không có công đoạn chờ xác nhận nào nằm ngoài lịch."
                      : "Tất cả việc của tổ đều đã nằm trên lịch."}</p>
                </div>
              ) : (
                <>
                  <ListSection label="Chưa định giờ" icon="clock" viec={groups.untimed}
                    selectedId={selectedId} onPick={pickViec} cho={choMap} />
                  <ListSection label="Ngoài khoảng ngày" icon="history" viec={groups.outWin}
                    selectedId={selectedId} onPick={pickViec} cho={choMap} />
                </>
              )}
            </div>
          </aside>
        ))}

        {/* CỘT GIỮA — bảng (Danh sách) hoặc lịch ngày */}
        <section className="thsx-center thsx-col--center">
          {err ? (
            <div className="thsx-centerempty"><BangLoi text={err} onRetry={loadItems} /></div>
          ) : (view === "lich" ? items : lenh) == null ? (
            view === "lich" ? <TimelineSkeleton /> : <ListSkeleton />
          ) : view === "danh_sach" ? (
            (lenh ?? []).length === 0 ? (
              <div className="thsx-centerempty">
                <EmptyState icon={q ? "search" : "check"}
                  title={q ? "Không khớp tìm kiếm" : chiCho ? "Không có lệnh nào trên bàn đang chờ xác nhận" : "Chưa có việc phát hành"}
                  sub={q ? "Thử đổi từ khoá."
                    : chiCho ? "Việc chờ còn lại thuộc công đoạn ngoài bàn này — xem danh sách phía trên."
                      : "Khi một gói được phát hành, việc của tổ sẽ hiện ở đây."} />
              </div>
            ) : (
              <>
                <ThsxDanhSach
                  lenh={lenh ?? []}
                  selectedId={selectedId}
                  onPick={pickViec}
                  onBatDau={(w) => lamNhanh(w, "bat_dau")}
                  onTamDung={(w) => lamNhanh(w, "tam_dung")}
                  onKetThuc={(w) => lamNhanh(w, "ket_thuc")}
                  cho={choMap}
                />
                <ThanhTrang trang={trang} soTrang={soTrang} tong={tongLenh} onDoi={setTrang} />
              </>
            )
          ) : (
            <ThsxLichNgay
              tu={winTu}
              soNgay={soNgay}
              dangTim={qd.trim() !== ""}
              viec={groups.timed}
              selectedId={selectedId}
              onChon={pickViec}
              cho={choMap}
            />
          )}
        </section>

        {/* NGĂN CHI TIẾT — lớp nổi trượt từ phải (không chiếm cột lưới) */}
        <aside className={`thsx-panel${panelOpen ? " thsx-panel--open" : ""}`}
          aria-label="Chi tiết công việc đang chọn">
          {panelOpen && (
            // Ngăn chi tiết vẽ hỏng thì chỉ ngăn này báo lỗi — bảng việc, hộp thư, đăng nhập đứng
            // nguyên. Không bọc thì một lỗi vẽ gỡ cả ứng dụng (xem `ErrorBoundary`).
            <ErrorBoundary
              // `key`: đổi công việc chọn phải REMOUNT cả drawer, không chỉ đổi prop — review vòng
              // 1, Minor 5. State nội bộ (`doiMayOpen`/`mayChonId`/`lyDoMay`, `giaoOpen`/`moKhoang`)
              // trước đây sống qua lần đổi `selectedId` vì component không unmount, để lại form
              // "Đổi máy" còn mở hoặc còn chọn dở máy của công việc TRƯỚC khi bấm sang việc khác.
              // Đặt ở ranh giới nên chọn việc khác cũng xoá luôn trạng thái lỗi.
              key={`${selectedId}:${moLan}`}
              fallback={(thuLai) => <NganChiTietLoi onThuLai={thuLai} onClose={closePanel} />}
            >
            <ThsxDrawer
              tabDau={tabDau}
              dinhKemDem={dinhKemDem}
              kcsTick={(eventTick ?? 0) + g5Tick}
              kcsLoiChoXem={kcsLoiChoXem}
              cho={selectedId != null ? choMap.get(selectedId) : undefined}
              onXemKcs={onXemKcs}
              chiTiet={chiTiet}
              loading={ctLoading}
              candidates={candidates}
              hoTroUngVien={hoTroUngVien}
              ungVienHomNay={ungVienHomNay}
              onMoChonNguoi={lamMoiUngVien}
              mayOptions={mayOptions}
              exec={exec}
              busy={busy}
              onGiao={onGiao}
              onRut={onRut}
              onBatDau={onBatDau}
              onNhanKhuon={onNhanKhuon}
              onTraKhuon={onTraKhuon}
              onTamDung={onTamDung}
              onKetThuc={onKetThuc}
              onClose={closePanel}
            />
            </ErrorBoundary>
          )}
        </aside>
      </div>

      {/* Nền mờ phía sau ngăn chi tiết — bấm ra ngoài là đóng */}
      {panelOpen && <div className="thsx-scrim" onClick={closePanel} aria-hidden="true" />}

      {/* Dải chân — chú giải trạng thái + cửa sổ */}
      <div className="thsx-foot">
        <div className="thsx-foot__legend" aria-hidden="true">
          <span className="thsx-lg thsx-lg--released"><i /> Chờ làm</span>
          <span className="thsx-lg thsx-lg--running"><i /> Đang chạy</span>
          <span className="thsx-lg thsx-lg--paused"><i /> Tạm dừng</span>
          <span className="thsx-lg thsx-lg--completed"><i /> Hoàn thành</span>
          <span className="thsx-lg thsx-lg--actual"><i /> Thực tế</span>
        </div>
        <div className="thsx-foot__spacer" />
      </div>
      </>)}

      {/* Dialog lý do Tạm dừng */}
      <ConfirmDialog
        open={!!reason}
        title={reason ? <span><Icon name="alert" size={16} /> Tạm dừng — nêu lý do</span> : ""}
        confirmLabel="Tạm dừng"
        confirmDisabled={!!reason && reasonText.trim() === ""}
        busy={busy}
        onConfirm={confirmReason}
        onCancel={() => { setReason(null); setReasonText(""); }}
      >
        {reason && (
          <div className="thsx-dlg-fields">
            <label className="thsx-dlg-field">
              <textarea className="thsx-dlg-reason" autoFocus
                placeholder="Lý do tạm dừng (hết giấy, hỏng máy…)"
                value={reasonText} onChange={(e) => setReasonText(e.target.value)} />
            </label>
          </div>
        )}
      </ConfirmDialog>

      {toast && <div className="thsx-toast" role="status">{toast}</div>}
    </div>
  );
}

// ============================ danh sách trái — 1 nhóm ======================
function ListSection({
  label, icon, viec, selectedId, onPick, cho,
}: {
  label: string;
  icon: Parameters<typeof Icon>[0]["name"];
  viec: SxWorkItem[];
  selectedId: number | null;
  onPick: (w: SxWorkItem) => void;
  cho?: ReadonlyMap<number, SxChoCuaViec>;
}) {
  if (viec.length === 0) return null;
  return (
    <div className="thsx-lsec">
      <div className="thsx-lsec__label">
        <Icon name={icon} size={12} /> {label}
        <span className="thsx-lsec__n thsx-num">{viec.length}</span>
      </div>
      {viec.map((w) => (
        <ListRow key={w.id} w={w} selected={w.id === selectedId} onPick={() => onPick(w)} cho={cho?.get(w.id)} />
      ))}
    </div>
  );
}

function ListRow({ w, selected, onPick, cho }: {
  w: SxWorkItem; selected: boolean; onPick: () => void; cho?: SxChoCuaViec;
}) {
  return (
    <button type="button" className={`thsx-lrow${selected ? " thsx-lrow--sel" : ""}`}
      aria-pressed={selected} onClick={onPick}>
      <div className="thsx-lrow__top">
        <Icon name={sxNguonIcon(w.nguon_loai)} size={13} className="thsx-lrow__nic" />
        <span className="thsx-lrow__serial thsx-num">{sxSerial(w.nguon_ma)}</span>
        <ChamCho c={cho} />
        <span className="thsx-lrow__spacer" />
        <ThsxTrangThaiPill tt={w.trang_thai} size="xs" />
      </div>
      <div className="thsx-lrow__cd">{w.ten_cong_doan || "—"}</div>
      <div className="thsx-lrow__meta">
        {w.may && <span className="thsx-lrow__may"><Icon name="printer" size={11} /> {w.may}</span>}
        {w.du_kien_bat_dau && (
          <span className="thsx-lrow__gio thsx-num"><Icon name="clock" size={11} /> {ngayGio(w.du_kien_bat_dau)}</span>
        )}
        <ChipKcs so_lan={w.kcs_so_lan} loi={w.kcs_loi} />
        <ChipLoaiBuoc loai_buoc={w.loai_buoc} nha_cung_cap={w.nha_cung_cap} />
        <ChipKhuon can_khuon={!!w.khuon} khuon={{ ...(w.khuon ?? {}), da_nhan: w.khuon_da_nhan }} />
      </div>
    </button>
  );
}

// ===================== ô "chờ xác nhận" trên thanh lọc ======================
/** Đếm việc chờ tổ bấm + công tắc lọc bảng về các lệnh có việc chờ (máy chủ lọc, §11.5). Không có
 *  việc chờ và đang tắt thì không chiếm chỗ. */
export function ONutCho({ so, bat, onDoi }: { so: number; bat: boolean; onDoi: (b: boolean) => void }) {
  if (so === 0 && !bat) return null;
  return (
    <button type="button" className={`thsx-cho-chip${bat ? " is-on" : ""}`} aria-pressed={bat}
      title={bat ? "Đang chỉ hiện lệnh có việc chờ tổ xác nhận — bấm để xem lại tất cả"
        : "Chỉ hiện lệnh có việc chờ tổ xác nhận"}
      onClick={() => onDoi(!bat)}>
      <span className="thsx-cho-chip__dot" aria-hidden="true" />
      <b className="thsx-num">{so}</b> chờ xác nhận
      {bat && <Icon name="x" size={12} />}
    </button>
  );
}

// ======================= ngăn chi tiết vẽ hỏng ==============================
/** Thay ngăn chi tiết khi nó ném lỗi lúc vẽ. Giữ đầu ngăn + nút Đóng như bản thường để người
 *  dùng thoát ra bằng đúng chỗ quen tay; câu chữ nói việc cần làm, không bày thông báo kỹ thuật. */
export function NganChiTietLoi({ onThuLai, onClose }: { onThuLai: () => void; onClose: () => void }) {
  return (
    <div className="thsx-panel__inner">
      <div className="thsx-panel__head">
        <div className="thsx-panel__title">
          <span className="thsx-panel__cd">Chi tiết công việc</span>
        </div>
        <button type="button" className="thsx-panel__close" onClick={onClose} aria-label="Đóng">
          <Icon name="x" size={16} />
        </button>
      </div>
      <div className="empty-state empty-state--inline empty-state--loi" role="alert">
        <Icon name="alert" size={40} />
        <p className="empty-state__title">Không hiển thị được chi tiết công việc này</p>
        <p className="empty-state__sub">
          Bảng việc và các thao tác khác vẫn dùng bình thường. Bấm Thử lại, hoặc đóng ngăn rồi chọn
          lại công việc. Lặp lại nhiều lần thì báo quản trị hệ thống.
        </p>
        <button type="button" className="btn btn--ghost" onClick={onThuLai}>
          Thử lại
        </button>
      </div>
    </div>
  );
}

// ============================ skeleton lúc tải ==============================
function TimelineSkeleton() {
  const rows: [number, number][] = [
    [8, 42], [26, 30], [4, 54], [36, 28], [12, 46], [30, 34], [6, 50], [20, 38],
  ];
  return (
    <div className="thsx-skel" role="status" aria-label="Đang tải bàn làm việc">
      {rows.map(([off, w], i) => (
        <div className="thsx-skel__row" key={i}>
          <div className="thsx-skel__lbl" />
          <div className="thsx-skel__bar" style={{ marginLeft: `${off}%`, width: `${w}%` }} />
        </div>
      ))}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="thsx-skel-q" role="status" aria-label="Đang tải danh sách việc">
      {[0, 1, 2, 3].map((i) => <div className="thsx-skel__q" key={i} />)}
    </div>
  );
}

// ===================== thanh phân trang (đếm theo LỆNH) =====================
/** Máy chủ cắt trang, màn chỉ đi tới/lui. Đơn vị đếm là LỆNH nên con số ở đây là "12 lệnh", không
 *  phải số bước — một lệnh không bao giờ bị xé qua hai trang. */
function ThanhTrang({
  trang, soTrang, tong, onDoi,
}: {
  trang: number;
  soTrang: number;
  tong: number;
  onDoi: (t: number) => void;
}) {
  if (soTrang <= 1) return null;
  return (
    <div className="thsx-trang">
      <button type="button" className="thsx-trang__nut" disabled={trang <= 1}
        onClick={() => onDoi(Math.max(1, trang - 1))}>
        <Icon name="chevron" size={14} className="thsx-rot90" /> Trước
      </button>
      <span className="thsx-trang__vt">
        Trang <b className="thsx-num">{trang}</b>/<b className="thsx-num">{soTrang}</b>
        <span className="thsx-trang__tong"> · <b className="thsx-num">{tong}</b> lệnh</span>
      </span>
      <button type="button" className="thsx-trang__nut" disabled={trang >= soTrang}
        onClick={() => onDoi(Math.min(soTrang, trang + 1))}>
        Sau <Icon name="chevron" size={14} className="thsx-rot-90" />
      </button>
    </div>
  );
}
