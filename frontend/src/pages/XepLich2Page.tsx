// XẾP LỊCH CÔNG ĐOẠN 2 — MỘT BÀN LÀM VIỆC (module `xep_lich_2`, cửa vào thứ hai, chạy song song màn cũ).
//
// Ba cột: HÀNG CHỜ (trái, hai rổ đủ/thiếu vật tư) · GANTT (giữa, cụm Máy/Tổ/Thuê-ngoài + "chưa đặt giờ")
// · PANEL dính (phải, chi tiết dòng đang chọn + gợi ý máy + vấn đề). Dải chân CHARCOAL đếm "N chặn · M
// lưu ý" theo THỰC THỂ đang chọn + cửa Phát hành / Thu hồi. Real-time qua `eventTick` (SSE ở AppShell).
//
// HỢP ĐỒNG BACKEND là nguồn sự thật (`/api/xep-lich-2`): mọi endpoint ĐỌC trả dict v2 (type Xl2*), PUT
// lưu ném 409 hai kiểu — chuỗi (khoá lạc quan → tải lại) hoặc `{loai:"chan_dat_lich"}` (bóc bằng
// `xl2ChanDatLich`, không ghi). MÁY CHỈ GHI NHẬN — người kế hoạch quyết máy/giờ; ta không lọc theo khổ/màu.
import {
  useCallback, useEffect, useMemo, useState, type ReactNode,
} from "react";
import {
  ApiError, api, xl2ChanDatLich,
  type Xl2BanLamViec, type Xl2BoiCanh, type Xl2BoiCanhBuoc, type Xl2Dong, type Xl2GoiPhatHanh,
  type Xl2DinhBien,
  type Xl2GoiYKhe,
  type Xl2HangCho, type Xl2Issue, type Xl2Khe, type Xl2Muc, type Xl2Nguon, type Xl2QRow,
  type Xl2NhanNgay, type Xl2TuXep,
  type Xl2VatTuTomTat, type Xl2XemTruoc, type XepLichGoiY,
} from "../api/client";
import { crud, type Row } from "../api/rebuildCatalog";
import { tagTone } from "../lib/tagTone";
import { useDebounced } from "../utils/useDebounced";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon, type IconName } from "../components/Icons";
import { BangLoi, EmptyState, ngay, ngayGio, num, thoiLuong } from "./keHoachSxShared";
import {
  Xl2Gantt, type Xl2Cluster, type Xl2ClusterKey, type Xl2Lane, type Xl2Nhom, type Xl2Patch,
} from "./Xl2Gantt";
import {
  XL2_MUC_META, XL2_MUC_ORDER, Xl2MucPill, demTheoMuc, dongEntityKey, dongMa, dongNhanParts, entityKey,
  mucNangNhat, nguonIcon, zoomVuaKhit, type Xl2Zoom,
} from "./xl2Shared";
import "./xep-lich-2.css";

// ============================ helper thuần ==================================
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function addDays(s: string, n: number): string {
  const [y, mo, d] = s.split("-").map(Number);
  const dt = new Date(y, mo - 1, d + n);
  return ymd(dt);
}
// datetime-local ↔ ISO NAIVE giờ nhà máy (không đổi múi).
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}` : "";
}
function fromLocalInput(local: string): string | null {
  if (!local) return null;
  return local.length === 16 ? `${local}:00` : local;
}

// Hai cách GOM HÀNG trên cùng một bàn, cùng một bộ dữ liệu (không gọi thêm API):
//  · theo TÀI NGUYÊN — mỗi máy/tổ một hàng, để nhìn máy nào kín máy nào rảnh (mặt phẳng lịch xưởng);
//  · theo LỆNH — mỗi LSX/bài ghép một hàng, cả chuỗi công đoạn nằm trên MỘT hàng, để nhìn đường đi
//    của cả lệnh từ bước đầu tới bước cuối.
const NHOMS: { key: Xl2Nhom; label: string; icon: IconName; hint: string }[] = [
  { key: "tai_nguyen", label: "Theo máy · tổ", icon: "printer",
    hint: "Mỗi máy / tổ một hàng — nhìn ra máy nào kín, máy nào còn rảnh." },
  { key: "lenh", label: "Theo lệnh", icon: "workflow",
    hint: "Mỗi lệnh / bài ghép một hàng — cả chuỗi công đoạn của một lệnh nằm trên một hàng." },
];

const ZOOMS: { key: Xl2Zoom; label: string }[] = [
  { key: "gio", label: "Giờ" },
  { key: "ca", label: "Ca" },
  { key: "ngay", label: "Ngày" },
  { key: "tuan", label: "Tuần" },
];
const WIN_SPAN = 14; // 2 tuần / bàn

type Xl2QLoc = "all" | "tre" | "gap";
const QFILTERS: { key: Xl2QLoc; label: string }[] = [
  { key: "all", label: "Tất cả" },
  { key: "tre", label: "Trễ" },
  { key: "gap", label: "Gấp" },
];
const MOI_TRANG = 50; // dòng / trang hàng chờ (cắt trang Ở MÁY CHỦ)
// Khối "Gợi ý khe rảnh thông minh" trong ngăn kéo bước — user yêu cầu ẨN 25/08/2026.
// Giữ nguyên mã (state + `onGoiYKhe` + API) để bật lại chỉ bằng một chữ `true`.
const HIEN_GOI_Y_KHE = false;
// Khối "Gợi ý máy" (thẻ máy + "N máy không vào được danh sách") — cũng ẩn theo yêu cầu 25/08/2026.
const HIEN_GOI_Y_MAY = false;

const mucBarCls = (m: Xl2Muc): "dat" | "ph" | "warn" =>
  m === "chan_dat_lich" ? "dat" : m === "chan_phat_hanh" ? "ph" : "warn";

// Câu toast khi cửa PHÁT HÀNH chặn. Backend trả `{loai:"chan_dat_lich", van_de:[...]}` (object) nên
// `ApiError.message` chỉ còn "Request failed (409)." — đọc xong không biết gỡ cái gì. Từ 25/08/2026
// phát hành đi CHUNG MỘT CỬA với dải chân (`kiem_phat_hanh`) nên danh sách này đúng bằng danh sách
// đang bày trên bàn: kể tên vấn đề đầu + đếm phần còn lại là người xếp biết ngay chỗ phải sửa.
function loiPhatHanh(e: unknown, macDinh: string): string {
  const chan = xl2ChanDatLich(e);
  if (chan && chan.length > 0) {
    const dau = chan[0];
    const ten = dau.doi_tuong ? `${dau.doi_tuong}: ` : "";
    const them = chan.length > 1 ? ` (+${chan.length - 1} vấn đề nữa)` : "";
    return `${macDinh} — ${ten}${dau.mo_ta}${them}`;
  }
  return e instanceof ApiError ? e.message : macDinh;
}

// NHÂN LỰC CỦA BƯỚC — một chỗ tính, ba chỗ hiện (thẻ bước · hộp xác nhận · panel dòng đã xếp).
// `so` là số BỐ TRÍ (kế hoạch) — đúng con số bàn xếp lịch cân quân số tổ; `db` là ba mốc định biên.
// Bước máy chỉ khai kíp chuẩn (danh mục Máy không có tối thiểu/tối đa) nên viết gọn "chuẩn N" thay vì
// "– · N · –": dấu gạch đọc như dữ liệu hỏng, trong khi thật ra máy không có khái niệm biên.
function nhanLucTom(so: number | null | undefined, db: Xl2DinhBien | null | undefined): {
  coBien: boolean; text: string | null; ngoai: boolean;
} {
  const coBien = !!db && (db.toi_thieu != null || db.toi_da != null);
  const text = !db
    ? null
    : coBien
      ? `${db.toi_thieu ?? "–"} · ${db.tieu_chuan ?? "–"} · ${db.toi_da ?? "–"}`
      : db.tieu_chuan != null
        ? `chuẩn ${db.tieu_chuan}`
        : null;
  // Từ 21/08/2026 quân số KHÔNG còn chặn đặt lịch, nên chỗ duy nhất người xếp nhìn thấy sai lệch là
  // con số này — ra ngoài biên thì tô tín hiệu ngay tại chỗ.
  const ngoai =
    so != null && !!db &&
    ((db.toi_thieu != null && so < db.toi_thieu) || (db.toi_da != null && so > db.toi_da));
  return { coBien, text, ngoai };
}

// Item 13 — MỞ MODULE NGUỒN để sửa GỐC vấn đề. Chỉ nối những `nguon` có màn sửa RIÊNG: vật tư → Kho,
// còn bước/tiền-nhiệm (routing · thiếu dữ liệu · thuê ngoài thiếu NCC đều phát ở bước) → Lệnh SX. Máy /
// tổ / ca / hạn xử lý NGAY trên bàn này (đổi máy·tổ·giờ, dời khe) nên KHÔNG đẩy đi màn khác — nút chỉ
// hiện khi thật sự có chỗ đi sửa, tránh đưa người dùng lòng vòng.
const XL2_NGUON_MODULE: Record<string, { id: string; nhan: string }> = {
  vat_tu: { id: "kho-main", nhan: "Mở Kho" },
  buoc: { id: "ke-hoach-sx", nhan: "Mở Lệnh SX" },
  tien_nhiem: { id: "ke-hoach-sx", nhan: "Mở Lệnh SX" },
};

// ============================ controller =====================================
export function XepLich2Page({
  navigate,
  eventTick,
  onBadgeStale,
  focusLsxMa,
}: {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  eventTick?: number;
  onBadgeStale?: () => void;
  /** Mã lệnh đi kèm khi tới đây bằng ĐÈN của màn Lệnh SX ("N bước chưa có giờ") — đổ thẳng vào ô
   *  tìm của hàng chờ để người dùng thấy ngay lệnh vừa bấm, không phải dò giữa cả bàn. */
  focusLsxMa?: string | null;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("xep_lich_2", "create");
  const canUpdate = can("xep_lich_2", "update");
  const canApprove = can("xep_lich_2", "approve");

  const [hangCho, setHangCho] = useState<Xl2HangCho | null>(null);
  const [ban, setBan] = useState<Xl2BanLamViec | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [errQueue, setErrQueue] = useState<string | null>(null);
  const [mays, setMays] = useState<Row[]>([]);
  const [phongBans, setPhongBans] = useState<Row[]>([]);

  const [winTu, setWinTu] = useState<string>(() => ymd(new Date()));
  const winDen = useMemo(() => addDays(winTu, WIN_SPAN - 1), [winTu]);
  const [zoom, setZoom] = useState<Xl2Zoom>("ngay");
  // Gom lane theo tài nguyên (mặc định) hay theo lệnh — xem `NHOMS`.
  const [nhom, setNhom] = useState<Xl2Nhom>("tai_nguyen");
  // Lọc cụm HIỂN THỊ trên Gantt (§11) — tập các cụm ĐANG ẨN. Không phá dữ liệu: cụm ẩn chỉ thôi vẽ,
  // số việc vẫn hiện trên chip để bật lại. Bàn bận (nhiều máy/tổ) → soi riêng từng nhóm tài nguyên.
  const [ganttAn, setGanttAn] = useState<Set<Xl2ClusterKey>>(() => new Set());
  // §15 — bấm một MỨC ở dải tổng quan để NỔI mọi thanh đúng mức đó trên Gantt (soi nhanh "đâu là các
  // thanh chặn đặt lịch"). null = không nổi theo mức. Bấm lại mức đang bật để tắt.
  const [hlMuc, setHlMuc] = useState<Xl2Muc | null>(null);
  // B5 — "Chỉ việc có vấn đề": lọc bàn xuống các thanh CÓ mức. Khai ở đây vì `clustersHienThi` (bên
  // dưới) đọc tới; auto-tắt khi bàn sạch nằm cạnh `soVanDeBan`.
  const [chiVanDe, setChiVanDe] = useState(false);

  // Lọc + cắt trang + đếm HÀNG CHỜ đều Ở MÁY CHỦ (§12.7, cấm cắt-trang ở JS): `q` (mã) + `loc`
  // (chip) đi thẳng vào API; `facets` (all/tre/gap) từ máy chủ. Chip "Xung đột" cũ đã BỎ — trùng
  // nghĩa với rổ "thiếu vật tư" đã hiện trực quan; "Chưa giờ" (§10.5) vô nghĩa với hàng chờ vì mọi
  // dòng ở đây đều chưa vào lịch ⇒ thay bằng "Gấp".
  const [q, setQ] = useState(focusLsxMa ?? "");
  const qd = useDebounced(q, 200);
  const [qFilter, setQFilter] = useState<Xl2QLoc>("all");
  const [trang, setTrang] = useState(1);
  const [queueTab, setQueueTab] = useState<"all" | "xep" | "chan">("all");
  // Bấm đèn ở màn Lệnh SX lần thứ hai (đang đứng sẵn ở đây) vẫn phải nhảy đúng lệnh mới.
  useEffect(() => {
    if (focusLsxMa) setQ(focusLsxMa);
  }, [focusLsxMa]);

  // Chọn: THỰC THỂ (highlight cả chuỗi + đếm phát hành) và DÒNG (panel chi tiết).
  const [selEntity, setSelEntity] = useState<{ nguon: Xl2Nguon; id: number } | null>(null);
  const [selDongId, setSelDongId] = useState<number | null>(null);
  const [xemTruoc, setXemTruoc] = useState<Xl2XemTruoc | null>(null);
  // Xem-trước HỎNG khác với xem-trước SẠCH: không có cờ này thì panel vấn đề in "cách đặt hiện tại
  // sạch" ngay cả khi cú gọi ngã — tức là báo an toàn cho một thứ chưa hề soi được.
  const [xtErr, setXtErr] = useState(false);
  // Gõ lại ô Bắt đầu → panel soi lại. Giữ kết quả CŨ trên màn (đỡ nhấp nháy) nhưng phải gắn nhãn
  // "đang soi lại", không thì người dùng đọc kết quả của giờ CŨ mà tưởng là của giờ vừa gõ.
  const [xtBusy, setXtBusy] = useState(false);
  const [goiY, setGoiY] = useState<XepLichGoiY | null>(null);
  const [boiCanh, setBoiCanh] = useState<Xl2BoiCanh | null>(null);
  const [phIssues, setPhIssues] = useState<Xl2Issue[] | null>(null);
  const [phErr, setPhErr] = useState(false);
  const [goiPh, setGoiPh] = useState<Xl2GoiPhatHanh | null>(null);   // §4.3 trạng thái gói phát hành
  const [showVerHist, setShowVerHist] = useState(false);   // xổ lịch sử phiên bản trong dải chân

  const [toast, setToast] = useState<{ text: string; undo?: () => void } | null>(null);
  const [busy, setBusy] = useState(false);

  // Hộp thoại
  const [preview, setPreview] = useState<{ dong: Xl2Dong; patch: Xl2Patch; xt: Xl2XemTruoc } | null>(null);
  const [conflict, setConflict] = useState<Xl2Dong | null>(null);
  const [askRelease, setAskRelease] = useState<{ nguon: Xl2Nguon; id: number; ma: string } | null>(null);
  const [askRecall, setAskRecall] = useState<{ nguon: Xl2Nguon; id: number; ma: string } | null>(null);
  const [recallReason, setRecallReason] = useState("");
  const [askCapNhat, setAskCapNhat] = useState<{ nguon: Xl2Nguon; id: number; ma: string } | null>(null);  // §4.3
  const [capNhatReason, setCapNhatReason] = useState("");
  const [askXoaNhap, setAskXoaNhap] = useState<Xl2Dong | null>(null);

  // Gợi ý khe trống (F4) — theo dòng đang chọn
  const [goiYKhe, setGoiYKhe] = useState<Xl2GoiYKhe | null>(null);
  const [goiYKheLoading, setGoiYKheLoading] = useState(false);

  // Tự xếp lịch cả lệnh (thuật toán `auto` bên BE) — theo THỰC THỂ đang chọn.
  const [tuXep, setTuXep] = useState<Xl2TuXep | null>(null);
  const [tuXepBusy, setTuXepBusy] = useState(false);
  const [tuXepErr, setTuXepErr] = useState<string | null>(null);

  // Nháp panel (máy / tổ / giờ)
  const [draftMay, setDraftMay] = useState<number | null>(null);
  const [draftDept, setDraftDept] = useState<number | null>(null);
  const [draftStart, setDraftStart] = useState<string>("");

  // Bố cục & View Mode: Thu gọn Hàng chờ & Chế độ Toàn màn hình Gantt (Focus Canvas)
  const [queueCollapsed, setQueueCollapsed] = useState(false);
  const [focusMode, setFocusMode] = useState(false);

  // Phím tắt Esc để đóng panel chi tiết
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && (selDongId != null || selEntity != null)) {
        setSelDongId(null);
        setSelEntity(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selDongId, selEntity]);

  // ---- nạp dữ liệu ----
  const loadQueue = useCallback(() => {
    if (!token) return;
    setErrQueue(null);
    api.xepLich2.hangCho(token, { trang, moi_trang: MOI_TRANG, q: qd, loc: qFilter })
      .then((r) => {
        setHangCho(r);
        setErrQueue(null);
        if (r.trang > r.so_trang) setTrang(r.so_trang); // trang rơi ngoài vùng (đưa việc đi) → kéo về
      })
      .catch((e: unknown) => setErrQueue(e instanceof ApiError ? e.message : String(e)));
  }, [token, trang, qd, qFilter]);
  const loadBan = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.xepLich2.banLamViec(token, { tu: winTu, den: winDen }).then(setBan).catch((e: unknown) =>
      setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, winTu, winDen]);

  useEffect(() => { loadQueue(); }, [loadQueue, eventTick]);
  useEffect(() => { loadBan(); }, [loadBan, eventTick]);
  // Đổi từ khoá / chip lọc ⇒ về trang 1 (kết quả lọc mới, không giữ số trang cũ).
  useEffect(() => { setTrang(1); }, [qd, qFilter]);

  useEffect(() => {
    if (!token) return;
    crud("/api/may-thiet-bi").list(token).then((r) => setMays(r.items)).catch(() => {});
    crud("/api/cong-doan/phong-ban").list(token).then((r) => setPhongBans(r.items)).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.undo ? 7000 : 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // Tên tra cứu
  const mayTen = useMemo(() => new Map(mays.map((m) => [m.id, m.ten])), [mays]);
  const deptTen = useMemo(() => new Map(phongBans.map((p) => [p.id, p.ten])), [phongBans]);

  // Dòng đang chọn
  const selDong = useMemo(
    () => ban?.dong.find((d) => d.id === selDongId) ?? null,
    [ban, selDongId],
  );

  // ---- bối cảnh thực thể đang chọn (Panel phải + kiểm phát hành, MỘT cú gọi) ----
  // `boi_canh` đã gộp cả `van_de` = kiểm-phát-hành nên KHÔNG gọi `kiemPhatHanh` riêng nữa; footer/
  // bar vẫn dùng `phIssues` (rút từ đây) để đếm mức + gate nút Phát hành.
  useEffect(() => {
    if (!token || !selEntity) { setBoiCanh(null); setPhIssues(null); setPhErr(false); setGoiPh(null); return; }
    let alive = true;
    setPhErr(false);
    api.xepLich2.boiCanh(token, selEntity)
      .then((r) => { if (alive) { setBoiCanh(r); setPhIssues(r.van_de); setPhErr(false); } })
      .catch(() => { if (alive) { setBoiCanh(null); setPhIssues(null); setPhErr(true); } });
    // §4.3: trạng thái gói phát hành → footer đổi cửa Phát hành ⇄ Phát hành cập nhật / Thu hồi.
    api.xepLich2.goiPhatHanh(token, selEntity)
      .then((g) => { if (alive) setGoiPh(g); })
      .catch(() => { if (alive) setGoiPh(null); });
    return () => { alive = false; };
  }, [token, selEntity, eventTick]);

  // ---- gợi ý máy theo dòng đang chọn ----
  // KHÔNG phụ thuộc ô nháp: gợi ý máy trả lời "máy nào nên chạy bước này", gõ giờ không đổi câu đó.
  useEffect(() => {
    if (!token || selDongId == null) { setGoiY(null); return; }
    let alive = true;
    api.xepLich2.goiY(token, selDongId)
      .then((r) => { if (alive) setGoiY(r); })
      .catch(() => { if (alive) setGoiY(null); });
    return () => { alive = false; };
  }, [token, selDongId, eventTick]);

  // Nháp panel gom thành patch tối thiểu — dùng CHUNG cho xem-trước tự động và nút Áp dụng, để
  // panel vấn đề soi ĐÚNG cái sắp ghi chứ không phải cái đang nằm trong DB.
  const draftPatch = useMemo<Xl2Patch>(() => {
    if (!selDong) return {};
    const patch: Xl2Patch = {};
    if (draftMay !== selDong.may_id) { patch.may_id = draftMay; patch.department_id = draftMay != null ? null : draftDept; }
    else if (draftDept !== selDong.department_id) { patch.department_id = draftDept; patch.may_id = draftDept != null ? null : draftMay; }
    const startIso = fromLocalInput(draftStart);
    if (startIso !== selDong.start_at) patch.start_at = startIso;
    return patch;
  }, [selDong, draftMay, draftDept, draftStart]);
  const draftKey = JSON.stringify(draftPatch);

  // ---- xem-trước theo NHÁP đang gõ ----
  // Hoãn 300ms: gõ datetime-local bắn onChange từng ký tự, không hoãn thì mỗi lần sửa phút là một
  // cú gọi engine. `alive` chặn kết quả về trễ đè lên kết quả của lần gõ mới hơn.
  useEffect(() => {
    if (!token || selDongId == null) { setXemTruoc(null); setXtErr(false); setXtBusy(false); return; }
    let alive = true;
    setXtBusy(true);
    const t = window.setTimeout(() => {
      api.xepLich2.xemTruoc(token, selDongId, draftPatch)
        .then((r) => { if (alive) { setXemTruoc(r); setXtErr(false); setXtBusy(false); } })
        .catch(() => { if (alive) { setXemTruoc(null); setXtErr(true); setXtBusy(false); } });
    }, 300);
    return () => { alive = false; window.clearTimeout(t); };
    // `draftKey` (chuỗi hoá của `draftPatch`) làm khoá phụ thuộc: patch là object, so sánh tham
    // chiếu thì mọi lần render lại đều tưởng là đổi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selDongId, draftKey, eventTick]);

  // Đồng bộ nháp panel theo dòng chọn
  useEffect(() => {
    if (!selDong) { setDraftMay(null); setDraftDept(null); setDraftStart(""); return; }
    setDraftMay(selDong.may_id);
    setDraftDept(selDong.department_id);
    setDraftStart(toLocalInput(selDong.start_at));
  }, [selDong]);

  // Đổi dòng chọn → xoá gợi ý khe cũ (F4) và xoá luôn kết quả soi của dòng TRƯỚC: trong 300ms chờ
  // soi lại, để nguyên panel cũ là đang gán vấn đề của dòng khác cho dòng vừa chọn.
  useEffect(() => { setGoiYKhe(null); setXemTruoc(null); setXtErr(false); }, [selDongId]);
  // Đổi lệnh đang chọn → xoá kết quả tự-xếp cũ (kết quả bám đúng MỘT lệnh, không được trôi sang lệnh khác).
  useEffect(() => { setTuXep(null); setTuXepErr(null); }, [selEntity]);

  // ---- dựng cụm/lane cho Gantt ----
  const clusters = useMemo<Xl2Cluster[]>(() => {
    const dong = ban?.dong ?? [];
    // Khay "CHƯA ĐẶT GIỜ" dùng CHUNG cho cả hai cách gom — thanh không có mốc thì không nằm lên trục
    // thời gian được, gom kiểu nào cũng vậy.
    const khayCho = (ds: Xl2Dong[]): Xl2Cluster => ({
      key: "cho", label: "Chưa đặt giờ", icon: "clock",
      lanes: [{ key: "cho:_", cluster: "cho", resId: null, label: "Nháp — chọn để xếp máy · giờ", packed: true, dong: ds }],
    });

    // ---- gom THEO LỆNH: mỗi LSX / bài ghép MỘT hàng, cả chuỗi công đoạn trên một hàng ----
    if (nhom === "lenh") {
      const lenh = new Map<string, Xl2Dong[]>();
      const chua: Xl2Dong[] = [];
      for (const d of dong) {
        if (!d.start_at) { chua.push(d); continue; }
        const k = dongEntityKey(d);
        (lenh.get(k) ?? lenh.set(k, []).get(k)!).push(d);
      }
      const out: Xl2Cluster[] = [];
      if (lenh.size) {
        const lanes: Xl2Lane[] = [...lenh.entries()]
          .map(([k, ds]) => {
            const d0 = ds[0];
            const som = ds.reduce((m, d) => (d.start_at && (!m || d.start_at < m) ? d.start_at : m), "" as string);
            return { key: `lenh:${k}`, cluster: "lenh" as const, resId: null,
              label: dongMa(d0), sub: d0.ten_san_pham, dong: ds, som };
          })
          // Lệnh chạy sớm lên trên — đọc từ trên xuống là đọc theo dòng thời gian.
          .sort((a, b) => (a.som || "").localeCompare(b.som || "") || a.label.localeCompare(b.label))
          .map(({ som: _som, ...l }) => l);
        out.push({ key: "lenh", label: "Theo lệnh", icon: "workflow", lanes });
      }
      if (chua.length) out.push(khayCho(chua));
      return out;
    }

    const may = new Map<number, Xl2Dong[]>();
    const to = new Map<number, Xl2Dong[]>();
    // Thuê ngoài gom theo TÊN nhà cung cấp (khoá "" = chưa rõ NCC, gộp về một khay đáy cụm).
    const ncc = new Map<string, Xl2Dong[]>();
    const cho: Xl2Dong[] = [];
    for (const d of dong) {
      if (d.may_id != null) (may.get(d.may_id) ?? may.set(d.may_id, []).get(d.may_id)!).push(d);
      else if (d.department_id != null) (to.get(d.department_id) ?? to.set(d.department_id, []).get(d.department_id)!).push(d);
      else if (d.start_at) { const s = (d.nha_cung_cap ?? "").trim(); (ncc.get(s) ?? ncc.set(s, []).get(s)!).push(d); }
      else cho.push(d);
    }
    const out: Xl2Cluster[] = [];
    // Cụm tài nguyên (Máy · Tổ · Thuê-ngoài) lên TRƯỚC — đây là mặt phẳng lịch chính.
    if (may.size) {
      const lanes: Xl2Lane[] = [...may.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([id, ds]) => ({ key: `may:${id}`, cluster: "may", resId: id, label: mayTen.get(id) ?? `Máy #${id}`, dong: ds }));
      out.push({ key: "may", label: "Máy", icon: "printer", lanes });
    }
    if (to.size) {
      const lanes: Xl2Lane[] = [...to.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([id, ds]) => ({ key: `to:${id}`, cluster: "to", resId: id, label: deptTen.get(id) ?? `Tổ #${id}`, dong: ds }));
      out.push({ key: "to", label: "Tổ", icon: "users", lanes });
    }
    if (ncc.size) {
      const lanes: Xl2Lane[] = [...ncc.entries()]
        // NCC có tên xếp A→Z; khay "chưa rõ" (khoá "") đẩy xuống cuối bằng ký tự cao nhất.
        .sort((a, b) => (a[0] || "￿").localeCompare(b[0] || "￿"))
        .map(([sup, ds]) => ({ key: `ncc:${sup || "_"}`, cluster: "ncc", resId: null,
          label: sup || "Thuê ngoài — chưa rõ NCC", dong: ds }));
      out.push({ key: "ncc", label: "Thuê ngoài", icon: "truck", lanes });
    }
    // Khay "CHƯA ĐẶT GIỜ" xuống ĐÁY (§10.2): rổ việc nháp chờ kéo lên lịch — như khay to-do dưới bàn,
    // không chen giữa các lane tài nguyên. Đồng bộ hai chiều với hàng chờ (chọn ở đây ↔ chọn ở kia).
    if (cho.length) out.push(khayCho(cho));
    return out;
  }, [ban, mayTen, deptTen, nhom]);

  // Cụm còn lại sau bộ lọc §11 (bỏ cụm đang ẩn) + lọc B5 (chỉ thanh có vấn đề, bỏ lane/cụm rỗng theo).
  // Gantt vẽ cái này; `clusters` gốc giữ để đếm chip.
  const clustersHienThi = useMemo(() => {
    let cs = clusters.filter((c) => !ganttAn.has(c.key));
    if (chiVanDe) {
      cs = cs
        .map((c) => ({ ...c, lanes: c.lanes.map((l) => ({ ...l, dong: l.dong.filter((d) => d.muc != null) })).filter((l) => l.dong.length > 0) }))
        .filter((c) => c.lanes.length > 0);
    }
    return cs;
  }, [clusters, ganttAn, chiVanDe]);

  // Mức tô thanh, ba lớp CHỒNG (lớp sau đè lớp trước — cụ thể hơn thắng):
  //  (a) NỔI TOÀN BÀN theo mức đang bấm ở dải tổng quan (§15) — dùng `dong.muc` máy chủ tính sẵn;
  //  (b) cả chuỗi THỰC THỂ đang chọn (từ kiểm phát hành);
  //  (c) DÒNG đang chọn (từ xem-trước) — nặng nhất về độ ưu tiên nên đặt cuối.
  const selEntityKey = selEntity ? entityKey(selEntity.nguon, selEntity.id) : null;
  // Đổi thực thể đang chọn → gấp lịch sử phiên bản đang xổ (tránh treo dữ liệu của thực thể cũ).
  useEffect(() => { setShowVerHist(false); }, [selEntityKey]);
  const barMuc = useMemo(() => {
    const m = new Map<number, Xl2Muc>();
    if (hlMuc && ban) {
      for (const d of ban.dong) if (d.muc === hlMuc) m.set(d.id, d.muc);
    }
    const entMuc = mucNangNhat(phIssues);
    if (entMuc && selEntityKey && ban) {
      for (const d of ban.dong) if (dongEntityKey(d) === selEntityKey) m.set(d.id, entMuc);
    }
    if (selDongId != null) {
      const dm = mucNangNhat(xemTruoc?.van_de);
      if (dm) m.set(selDongId, dm);
      else m.delete(selDongId);
    }
    return m;
  }, [hlMuc, phIssues, selEntityKey, ban, selDongId, xemTruoc]);

  // §15 — TỔNG 3 MỨC theo TOÀN bàn: đếm dòng theo `dong.muc` (máy chủ tính bằng CHÍNH detector đặt-lịch,
  // nên khớp panel/xem-trước). Chỉ có chan_dat_lich / canh_bao ở cấp THANH (chan_phat_hanh là cấp lệnh,
  // đếm ở dải chân khi chọn thực thể) — nên số này luôn 0, chip tự ẩn.
  const boardMuc = useMemo(() => {
    const out: Record<Xl2Muc, number> = { chan_dat_lich: 0, chan_phat_hanh: 0, canh_bao: 0 };
    for (const d of ban?.dong ?? []) if (d.muc) out[d.muc] += 1;
    return out;
  }, [ban]);
  // Mức đang nổi mà đổi cửa sổ/tải lại làm số về 0 → tự tắt để dải không kẹt trạng thái "bật nhưng trống".
  useEffect(() => { if (hlMuc && boardMuc[hlMuc] === 0) setHlMuc(null); }, [hlMuc, boardMuc]);
  const onToggleMuc = useCallback((m: Xl2Muc) => setHlMuc((cur) => (cur === m ? null : m)), []);
  // Mức nào có mặt trên bàn (để dựng nút nổi ở DẢI CHÂN — C1) + tổng thanh đang vướng (cho lọc B5).
  const mucCoSoBan = useMemo(() => XL2_MUC_ORDER.filter((m) => boardMuc[m] > 0), [boardMuc]);
  const soVanDeBan = boardMuc.chan_dat_lich + boardMuc.canh_bao;
  // Lọc B5 tự tắt khi bàn sạch vấn đề (đổi cửa sổ / tải lại) để không kẹt trạng thái "bật mà trống".
  useEffect(() => { if (chiVanDe && soVanDeBan === 0) setChiVanDe(false); }, [chiVanDe, soVanDeBan]);

  // Mã HIỂN THỊ của thực thể đang chọn — lấy từ hàng chờ (Xl2QRow.ma) hoặc mã dòng trên bàn;
  // lùi về "LSX#id"/"GB#id" nếu chưa nạp được (điểm 2: bỏ "#id" trần khi đã có mã thật).
  const selEntityMa = useMemo(() => {
    if (!selEntity) return null;
    const rows = [...(hangCho?.xep_duoc ?? []), ...(hangCho?.bi_chan ?? [])];
    const qr = rows.find((r) => r.nguon === selEntity.nguon && r.id === selEntity.id);
    if (qr) return qr.ma;
    const d = ban?.dong.find((x) => selEntityKey != null && dongEntityKey(x) === selEntityKey);
    if (d) return selEntity.nguon === "lsx" ? d.lsx_ma : d.bai_ghep_ma;
    return null;
  }, [selEntity, selEntityKey, hangCho, ban]);
  const selEntityLabel = selEntityMa
    ?? (selEntity ? `${selEntity.nguon === "lsx" ? "LSX" : "GB"}#${selEntity.id}` : "");

  // Tổng quan bàn (điểm 3): thành phần lịch trong cửa sổ — thuần dẫn xuất từ ban.dong, không gọi thêm.
  const digest = useMemo(() => {
    const dong = ban?.dong ?? [];
    let daXep = 0;
    let chuaGio = 0;
    let ncc = 0;
    const may = new Set<number>();
    const to = new Set<number>();
    for (const d of dong) {
      if (d.start_at) daXep += 1; else chuaGio += 1;
      if (d.may_id != null) may.add(d.may_id);
      else if (d.department_id != null) to.add(d.department_id);
      else if (d.start_at) ncc += 1;
    }
    return { tong: dong.length, daXep, chuaGio, may: may.size, to: to.size, ncc };
  }, [ban]);

  // Hôm nay (YYYY-MM-DD) — chỉ để tô "trễ" trên hàng chờ; lọc/đếm đã ở máy chủ.
  const today = useMemo(() => ymd(new Date()), []);
  // Rổ + facet lấy THẲNG từ máy chủ (đã lọc theo q/loc). `facets` đếm CẢ hàng chờ.
  const fXep = hangCho?.xep_duoc ?? [];
  const fChan = hangCho?.bi_chan ?? [];
  const facets = hangCho?.facets ?? { all: 0, tre: 0, gap: 0 };

  // "Vừa khít" (§10.3): tự chọn zoom theo mật độ việc đang xếp trong cửa sổ (thuần dẫn xuất).
  const onVuaKhit = useCallback(() => {
    setZoom(zoomVuaKhit((ban?.dong ?? []).map((d) => d.boc_tach?.chiem_may_phut ?? 0)));
  }, [ban]);

  // ---- hành động ----
  const reloadAll = useCallback(() => { loadQueue(); loadBan(); onBadgeStale?.(); }, [loadQueue, loadBan, onBadgeStale]);

  const pickQueue = useCallback((r: Xl2QRow) => {
    setSelDongId(null);
    setSelEntity({ nguon: r.nguon, id: r.id });
  }, []);

  const pickDong = useCallback((dongId: number) => {
    const d = ban?.dong.find((x) => x.id === dongId);
    setSelDongId(dongId);
    if (d) {
      if (d.nguon === "lsx" && d.lsx_id != null) setSelEntity({ nguon: "lsx", id: d.lsx_id });
      else if (d.nguon === "in_ghep" && d.bai_ghep_id != null) setSelEntity({ nguon: "in_ghep", id: d.bai_ghep_id });
    }
  }, [ban]);

  // Đóng bảng chi tiết (điểm 8: drawer trên màn hẹp) — bỏ chọn dòng + thực thể.
  const closePanel = useCallback(() => { setSelDongId(null); setSelEntity(null); }, []);

  // Item 13 — nhảy sang MODULE NGUỒN của một vấn đề để sửa gốc. Lệnh SX nhận thẳng LSX đang chọn
  // (`openLsxId`) để mở đúng lệnh; bài ghép / Kho không có mốc lệnh đơn lẻ ⇒ lùi về mở MÀN (vẫn đúng chỗ).
  const moNguon = useCallback((issue: Xl2Issue) => {
    const target = XL2_NGUON_MODULE[issue.nguon];
    if (!target || !navigate) return;
    const params: Record<string, unknown> = {};
    if (target.id === "ke-hoach-sx" && selEntity?.nguon === "lsx") params.openLsxId = selEntity.id;
    navigate(target.id, params);
  }, [navigate, selEntity]);
  const canMoNguon = !!navigate;

  // Mở đúng chỗ SỬA nhân lực của một dòng đã xếp: dòng của lệnh → Lệnh SX mở thẳng lệnh đó (drawer
  // bước có ô số người + ba mốc biên); dòng của bài ghép → màn Bài ghép (bước chung của bài, không có
  // mốc lệnh đơn lẻ để mở sâu hơn — cùng cách lùi như `moNguon`).
  const moBuocCuaDong = useCallback((d: Xl2Dong) => {
    if (!navigate) return;
    if (d.nguon === "lsx" && d.lsx_id != null) navigate("ke-hoach-sx", { openLsxId: d.lsx_id });
    else navigate("bai-ghep-2", {});
  }, [navigate]);

  const duaVao = useCallback(async (r: Xl2QRow) => {
    if (!token) return;
    setBusy(true);
    try {
      if (r.nguon === "lsx") await api.xepLich2.duaVaoLsx(token, r.id);
      else await api.xepLich2.duaVaoBaiGhep(token, r.id);
      setToast({ text: `Đã đưa ${r.ma} vào kế hoạch` });
      reloadAll();
    } catch (e) {
      setToast({ text: e instanceof ApiError ? e.message : "Không đưa vào được" });
    } finally { setBusy(false); }
  }, [token, reloadAll]);

  // TỰ XẾP LỊCH cả lệnh — engine `auto` bên BE chọn máy + giờ cho từng bước theo đúng thứ tự routing,
  // tính bằng thời lượng TRUNG BÌNH, né trùng máy/khoá máy, và nếu lượt đầu trễ hạn SX thì tự chạy
  // thêm một lượt "cứu hạn" (ưu tiên máy nhanh nhất) rồi giữ lượt nào tốt hơn.
  //  · `ghiDe=false` → chỉ đụng bước CÒN TRỐNG giờ; bước đã xếp/đang khoá giữ nguyên.
  //  · `ghiDe=true`  → xếp lại toàn bộ chuỗi (trừ bước đang khoá).
  const chayTuXep = useCallback(async (ghiDe: boolean) => {
    if (!token || !selEntity) return;
    setTuXepBusy(true);
    setTuXepErr(null);
    try {
      const r = await api.xepLich2.tuXep(token, { nguon: selEntity.nguon, id: selEntity.id, ghiDe });
      setTuXep(r);
      setToast({ text: r.tom_tat });
      reloadAll();
    } catch (e) {
      setTuXepErr(e instanceof ApiError ? e.message : "Không chạy được tự xếp");
    } finally { setTuXepBusy(false); }
  }, [token, selEntity, reloadAll]);

  // Đề xuất một patch (kéo-thả / phím / panel / gợi ý) → xem-trước → mở hộp xác nhận.
  const propose = useCallback(async (dongId: number, patch: Xl2Patch) => {
    if (!token) return;
    const d = ban?.dong.find((x) => x.id === dongId);
    if (!d) return;
    try {
      const xt = await api.xepLich2.xemTruoc(token, dongId, patch);
      setPreview({ dong: d, patch, xt });
    } catch (e) {
      setToast({ text: e instanceof ApiError ? e.message : "Không xem trước được" });
    }
  }, [token, ban]);

  // Áp nháp panel: gom các ô đã đổi so với dòng hiện tại thành patch tối thiểu.
  const apDungPanel = useCallback(() => {
    if (!selDong) return;
    if (Object.keys(draftPatch).length === 0) { setToast({ text: "Chưa có thay đổi nào" }); return; }
    void propose(selDong.id, draftPatch);
  }, [selDong, draftPatch, propose]);

  // Ghi (từ hộp xem-trước).
  const confirmLuu = useCallback(async () => {
    if (!token || !preview) return;
    const { dong, patch } = preview;
    setBusy(true);
    try {
      await api.xepLich2.luu(token, dong.id, { expected_updated_at: dong.updated_at, ...patch });
      setPreview(null);
      setToast({ text: `Đã xếp ${dongMa(dong)}` });
      reloadAll();
      setSelDongId(dong.id); // giữ chọn → panel refetch
    } catch (e) {
      const blocked = xl2ChanDatLich(e);
      if (blocked) {
        // Chặn đặt lịch: giữ hộp, hiện vấn đề đỏ, không ghi.
        setPreview((p) => p ? { ...p, xt: { ...p.xt, van_de: blocked } } : p);
        setToast({ text: "Bị chặn đặt lịch — xem vấn đề bên dưới" });
      } else if (e instanceof ApiError && e.isConflict) {
        setPreview(null);
        setConflict(dong);
      } else {
        setToast({ text: e instanceof ApiError ? e.message : "Không lưu được" });
      }
    } finally { setBusy(false); }
  }, [token, preview, reloadAll]);

  const doRelease = useCallback(async () => {
    if (!token || !askRelease) return;
    setBusy(true);
    try {
      if (askRelease.nguon === "lsx") await api.xepLich2.phatHanhLsx(token, askRelease.id);
      else await api.xepLich2.phatHanhBaiGhep(token, askRelease.id);
      setToast({ text: `Đã phát hành ${askRelease.ma}` });
      setAskRelease(null);
      reloadAll();
    } catch (e) {
      setToast({ text: loiPhatHanh(e, "Không phát hành được") });
    } finally { setBusy(false); }
  }, [token, askRelease, reloadAll]);

  const doRecall = useCallback(async () => {
    if (!token || !askRecall) return;
    setBusy(true);
    try {
      if (askRecall.nguon === "lsx") await api.xepLich2.goPhatHanhLsx(token, askRecall.id, recallReason);
      else await api.xepLich2.goPhatHanhBaiGhep(token, askRecall.id, recallReason);
      setToast({ text: `Đã thu hồi ${askRecall.ma}` });
      setAskRecall(null);
      setRecallReason("");
      reloadAll();
    } catch (e) {
      setToast({ text: e instanceof ApiError ? e.message : "Không thu hồi được" });
    } finally { setBusy(false); }
  }, [token, askRecall, recallReason, reloadAll]);

  // Phát hành CẬP NHẬT (§4.3): tái chụp việc chưa bắt đầu theo lịch mới, lên phiên bản kèm lý do.
  const doCapNhat = useCallback(async () => {
    if (!token || !askCapNhat) return;
    if (capNhatReason.trim().length < 3) { setToast({ text: "Ghi lý do cập nhật (tối thiểu 3 ký tự)" }); return; }
    setBusy(true);
    try {
      const kq = askCapNhat.nguon === "lsx"
        ? await api.xepLich2.phatHanhCapNhatLsx(token, askCapNhat.id, capNhatReason)
        : await api.xepLich2.phatHanhCapNhatBaiGhep(token, askCapNhat.id, capNhatReason);
      setToast({ text: `Đã cập nhật ${askCapNhat.ma} → phiên bản ${kq.version_hien_tai} · tái chụp ${kq.so_cong_viec_cap_nhat} việc` });
      setAskCapNhat(null);
      setCapNhatReason("");
      reloadAll();
    } catch (e) {
      setToast({ text: loiPhatHanh(e, "Không phát hành cập nhật được") });
    } finally { setBusy(false); }
  }, [token, askCapNhat, capNhatReason, reloadAll]);

  // Gợi ý ≤3 khe trống (F4) — theo cửa sổ Gantt hiện tại.
  const onGoiYKhe = useCallback(async () => {
    if (!token || selDongId == null) return;
    setGoiYKheLoading(true);
    try {
      const r = await api.xepLich2.goiYKhe(token, selDongId, { tu: winTu, den: winDen });
      setGoiYKhe(r);
    } catch (e) {
      setToast({ text: e instanceof ApiError ? e.message : "Không lấy được gợi ý, thử lại." });
    } finally { setGoiYKheLoading(false); }
  }, [token, selDongId, winTu, winDen]);

  // Chọn một khe → ĐỔ giờ vào ô "Bắt đầu" (KHÔNG tự lưu — người bấm "Xem trước & xếp" mới chốt).
  const onChonKhe = useCallback((k: Xl2Khe) => {
    setDraftStart(toLocalInput(k.start_at));
  }, []);

  // Xoá nháp lệnh (F3) — gỡ cả chuỗi thực thể khỏi kế hoạch; 409 nếu đã phát hành / đang khoá.
  const doXoaNhap = useCallback(async () => {
    if (!token || !askXoaNhap) return;
    const d = askXoaNhap;
    setBusy(true);
    try {
      if (d.nguon === "lsx" && d.lsx_id != null) await api.xepLich2.xoaNhapLsx(token, d.lsx_id);
      else if (d.nguon === "in_ghep" && d.bai_ghep_id != null) await api.xepLich2.xoaNhapBaiGhep(token, d.bai_ghep_id);
      else throw new Error("Thiếu nguồn dòng");
      setAskXoaNhap(null);
      setSelDongId(null);
      setToast({ text: `Đã xoá nháp ${dongMa(d)}` });
      reloadAll();
    } catch (e) {
      setAskXoaNhap(null);
      if (e instanceof ApiError && e.isConflict) {
        setToast({ text: e.message || "Lệnh đã phát hành hoặc đang khoá — thu hồi trước đã." });
      } else {
        setToast({ text: e instanceof ApiError ? e.message : "Không xoá được, thử lại." });
      }
    } finally { setBusy(false); }
  }, [token, askXoaNhap, reloadAll]);

  // ---- render ----
  const queueCount = facets.all;                    // TỔNG hàng chờ (cả bàn), không phải trang hiện tại
  const tongLoc = hangCho?.tong ?? 0;               // số dòng KHỚP bộ lọc (dựng phân trang)
  const soTrang = hangCho?.so_trang ?? 1;
  const khongKhop = hangCho != null && tongLoc === 0 && queueCount > 0; // còn việc nhưng lọc không ra
  const phCount = phIssues ? demTheoMuc(phIssues) : null;
  const previewBlocked = !!preview && preview.xt.van_de.some((v) => v.muc === "chan_dat_lich");
  const canReleaseNow = !!selEntity && phIssues != null
    && !phIssues.some((v) => v.muc === "chan_phat_hanh" || v.muc === "chan_dat_lich");
  const panelOpen = !!(selDong || selEntity);

  return (
    <div className="xl2">
      {/* Tầng 1: Command & Timeline Bar */}
      <div className="xl2-top">
        <div className="xl2-top__left">
          <span className="xl2-top__title">Xếp lịch công đoạn 2</span>
          <div className="xl2-top__win">
            <button type="button" className="xl2-iconbtn xl2-iconbtn--subtle" title="14 ngày trước" aria-label="14 ngày trước"
              onClick={() => setWinTu((s) => addDays(s, -WIN_SPAN))}>
              <Icon name="chevron" size={14} className="xl2-rot180" />
            </button>
            <span className="xl2-win-label">{ngay(winTu)} — {ngay(winDen)}</span>
            <button type="button" className="xl2-iconbtn xl2-iconbtn--subtle" title="14 ngày sau" aria-label="14 ngày sau"
              onClick={() => setWinTu((s) => addDays(s, WIN_SPAN))}>
              <Icon name="chevron" size={14} />
            </button>
            <button type="button" className="xl2-iconbtn xl2-iconbtn--subtle" title="Về hôm nay" aria-label="Về hôm nay"
              onClick={() => setWinTu(ymd(new Date()))}>
              <Icon name="refresh" size={13} />
            </button>
          </div>
        </div>

        <div className="xl2-top__center">
          <div className="xl2-seg" role="group" aria-label="Cách gom hàng trên bàn">
            {NHOMS.map((h) => (
              <button key={h.key} type="button" className="xl2-seg__btn"
                aria-pressed={nhom === h.key} title={h.hint} onClick={() => setNhom(h.key)}>
                {h.label}
              </button>
            ))}
          </div>

          <div className="xl2-seg" role="group" aria-label="Mật độ trục thời gian">
            {ZOOMS.map((z) => (
              <button key={z.key} type="button" className="xl2-seg__btn"
                aria-pressed={zoom === z.key} onClick={() => setZoom(z.key)}>
                {z.label}
              </button>
            ))}
          </div>

          <button type="button" className="xl2-iconbtn xl2-iconbtn--wide"
            title="Vừa khít — tự chọn mật độ theo lượng việc" aria-label="Vừa khít"
            disabled={!ban || ban.dong.length === 0} onClick={onVuaKhit}>
            <span>Vừa khít</span>
          </button>

          <button
            type="button"
            className={`xl2-iconbtn${focusMode ? " is-active" : ""}`}
            title={focusMode ? "Thoát toàn màn hình" : "Toàn màn hình Gantt"}
            aria-label="Toàn màn hình Gantt"
            onClick={() => setFocusMode((v) => !v)}
          >
            <Icon name="maximize" size={14} />
          </button>
        </div>

        <div className="xl2-top__right">
          {ban && (
            <div className="xl2-kpisummary">
              <span className="xl2-kpisummary__item" title="Tiến độ xếp việc">
                Đã xếp: <b className="xl2-num">{digest.daXep}/{digest.tong}</b>
              </span>
              <span className="xl2-kpisummary__sep">·</span>
              <span className="xl2-kpisummary__item">
                <b className="xl2-num">{digest.may}</b> máy · <b className="xl2-num">{digest.to}</b> tổ
              </span>
              {facets.gap > 0 && (
                <>
                  <span className="xl2-kpisummary__sep">·</span>
                  <span className="xl2-kpisummary__item xl2-kpisummary__item--rush">
                    <b className="xl2-num">{facets.gap}</b> gấp
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Tầng 2: Search, Quick Filters & Cluster Toggles */}
      <div className="xl2-subbar">
        <div className="xl2-search" style={{ maxWidth: 220 }}>
          <Icon name="search" size={13} className="xl2-search__ic" />
          <input
            type="search" className="xl2-search__in" value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm LSX, bài ghép…" aria-label="Tìm trong hàng chờ"
          />
          {q && (
            <button type="button" className="xl2-search__clear" aria-label="Xoá tìm" onClick={() => setQ("")}>
              <Icon name="x" size={12} />
            </button>
          )}
        </div>

        <div className="xl2-chips" role="group" aria-label="Lọc hàng chờ">
          {QFILTERS.map((f) => (
            <button key={f.key} type="button"
              className={`xl2-chip${qFilter === f.key ? " is-active" : ""}`}
              aria-pressed={qFilter === f.key} onClick={() => setQFilter(f.key)}>
              {f.label}
              <span className={`chip-count${f.key !== "all" && facets[f.key] > 0 && qFilter !== f.key ? " chip-count--alert" : ""}`}>
                {facets[f.key]}
              </span>
            </button>
          ))}
        </div>

        <div className="xl2-subbar__spacer" />

        {soVanDeBan > 0 && (
          <button type="button"
            className={`xl2-filterbtn xl2-filterbtn--vd${chiVanDe ? " is-on" : ""}`}
            aria-pressed={chiVanDe}
            title={chiVanDe ? "Hiện lại mọi việc" : "Chỉ hiện việc đang có vấn đề"}
            onClick={() => setChiVanDe((v) => !v)}>
            <span>Có vấn đề</span>
            <b className="xl2-filterbtn__n xl2-num">{soVanDeBan}</b>
          </button>
        )}

        {clusters.length > 1 && (
          <div className="xl2-cluster-toggles" role="group" aria-label="Bật tắt cụm tài nguyên">
            <span className="xl2-cluster-toggles__label">Hiện:</span>
            {clusters.map((c) => {
              const an = ganttAn.has(c.key);
              const n = c.lanes.reduce((s, l) => s + l.dong.length, 0);
              return (
                <button key={c.key} type="button"
                  className={`xl2-cluster-toggle${an ? " is-off" : " is-on"}`}
                  aria-pressed={!an}
                  title={an ? `Hiện cụm ${c.label}` : `Ẩn cụm ${c.label}`}
                  onClick={() => setGanttAn((prev) => {
                    const next = new Set(prev);
                    if (next.has(c.key)) next.delete(c.key); else next.add(c.key);
                    return next;
                  })}>
                  <span>{c.label}</span>
                  <b className="xl2-cluster-toggle__n xl2-num">{n}</b>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Lưới 3 cột siêu linh hoạt — co giãn mượt mà giữa các chế độ */}
      <div className={`xl2-grid${panelOpen && !focusMode ? " is-panel" : ""}${queueCollapsed || focusMode ? " is-queue-collapsed" : ""}${focusMode ? " is-focus" : ""}`}>
        {/* CỘT TRÁI — Hàng chờ (Dockable / Collapsible) */}
        <aside className={`xl2-queue${queueCollapsed || focusMode ? " xl2-queue--collapsed" : ""}`}>
          {queueCollapsed || focusMode ? (
            <div className="xl2-queue__minirail" onClick={() => { setQueueCollapsed(false); setFocusMode(false); }} title="Mở rộng Hàng chờ">
              <button type="button" className="xl2-queue__railbtn" aria-label="Mở rộng hàng chờ">
                <Icon name="clipboard" size={16} />
              </button>
              <div className="xl2-queue__railcount" title={`${queueCount} việc trong hàng chờ`}>
                <span className="xl2-num">{queueCount}</span>
              </div>
              <div className="xl2-queue__railtext">HÀNG CHỜ</div>
            </div>
          ) : (
            <>
              <div className="xl2-queue__head">
                <div className="xl2-queue__iconbox">
                  <Icon name="clipboard" size={15} />
                </div>
                <h2>Hàng chờ</h2>
                <span className="xl2-queue__count xl2-num">{queueCount}</span>
                <div className="xl2-queue__head-spacer" />
                <button
                  type="button"
                  className="xl2-queue__togglebtn"
                  title="Thu gọn hàng chờ để mở rộng Gantt"
                  aria-label="Thu gọn hàng chờ"
                  onClick={() => setQueueCollapsed(true)}
                >
                  <Icon name="chevron" size={14} className="xl2-rot180" />
                </button>
              </div>
              <div className="xl2-qtabs" role="tablist">
                <button type="button" className={`xl2-qtab${queueTab === "all" ? " is-active" : ""}`} onClick={() => setQueueTab("all")}>
                  <span>Tất cả</span>
                  <span className="xl2-qtab__count">{queueCount}</span>
                </button>
                <button type="button" className={`xl2-qtab${queueTab === "xep" ? " is-active" : ""}`} onClick={() => setQueueTab("xep")}>
                  <span>Sẵn sàng</span>
                  <span className="xl2-qtab__count">{fXep.length}</span>
                </button>
                <button type="button" className={`xl2-qtab${queueTab === "chan" ? " is-active" : ""}`} onClick={() => setQueueTab("chan")}>
                  <span>Bị chặn</span>
                  <span className="xl2-qtab__count">{fChan.length}</span>
                </button>
              </div>
              <div className="xl2-queue__body">
                {errQueue ? (
                  <div style={{ padding: "var(--sp-4)" }}><BangLoi text={errQueue} onRetry={loadQueue} /></div>
                ) : hangCho == null ? (
                  <QueueSkeleton />
                ) : queueCount === 0 ? (
                  <EmptyState icon="check" title="Hết việc chờ xếp" sub="Mọi lệnh / bài ghép sẵn sàng đã vào kế hoạch." />
                ) : khongKhop ? (
                  <div className="xl2-qempty">
                    <EmptyState icon="search" title="Không khớp bộ lọc"
                      sub="Thử đổi từ khoá hoặc chọn lại 'Tất cả'." />
                    <Button variant="ghost" onClick={() => { setQ(""); setQFilter("all"); }}>Xoá lọc</Button>
                  </div>
                ) : (
                  <>
                    {(queueTab === "all" || queueTab === "xep") && fXep.length > 0 && (
                      <div className="xl2-qsec">
                        {queueTab === "all" && <div className="xl2-qsec__label"><Icon name="check" size={12} /> Đủ vật tư · xếp được</div>}
                        {fXep.map((r) => (
                          <QueueRow key={`${r.nguon}:${r.id}`} r={r} today={today} selected={sameEntity(selEntity, r)}
                            canCreate={canCreate} busy={busy} onPick={() => pickQueue(r)} onDua={() => duaVao(r)} />
                        ))}
                      </div>
                    )}
                    {(queueTab === "all" || queueTab === "chan") && fChan.length > 0 && (
                      <div className="xl2-qsec">
                        {queueTab === "all" && <div className="xl2-qsec__label xl2-qsec__label--blocked"><Icon name="lock" size={12} /> Thiếu vật tư · vẫn đưa vào nháp được</div>}
                        {fChan.map((r) => (
                          <QueueRow key={`${r.nguon}:${r.id}`} r={r} today={today} selected={sameEntity(selEntity, r)}
                            canCreate={canCreate} busy={busy} onPick={() => pickQueue(r)} onDua={() => duaVao(r)} />
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
              {/* Phân trang máy chủ — chỉ hiện khi kết quả lọc tràn 1 trang. */}
              {hangCho != null && soTrang > 1 && (
                <div className="xl2-pager">
                  <button type="button" className="xl2-pager__btn" aria-label="Trang trước"
                    disabled={trang <= 1} onClick={() => setTrang((t) => Math.max(1, t - 1))}>
                    <Icon name="chevron" size={15} className="xl2-rot180" />
                  </button>
                  <span className="xl2-pager__lb">
                    Trang <b className="xl2-num">{trang}</b>/<span className="xl2-num">{soTrang}</span>
                    <span className="xl2-pager__tong"> · {tongLoc} dòng</span>
                  </span>
                  <button type="button" className="xl2-pager__btn" aria-label="Trang sau"
                    disabled={trang >= soTrang} onClick={() => setTrang((t) => Math.min(soTrang, t + 1))}>
                    <Icon name="chevron" size={15} />
                  </button>
                </div>
              )}
            </>
          )}
        </aside>

        {/* CỘT GIỮA — Gantt Canvas */}
        <section className="xl2-center xl2-col--center">
          {err ? (
            <div style={{ padding: "var(--sp-4)" }}><BangLoi text={err} onRetry={loadBan} /></div>
          ) : ban == null ? (
            <GanttSkeleton />
          ) : clusters.length === 0 ? (
            <div className="xl2-centerempty">
              <EmptyState icon="calendar" title="Bàn trống trong khoảng này"
                sub="Chọn một lệnh / bài ghép ở hàng chờ rồi 'Đưa vào kế hoạch' để bắt đầu xếp." />
            </div>
          ) : (
            <>
              {clustersHienThi.length === 0 ? (
            <div className="xl2-centerempty">
              <EmptyState icon={chiVanDe ? "check" : "workflow"}
                title={chiVanDe ? "Không có việc vấn đề đang hiện" : "Đã ẩn hết cụm"}
                sub={chiVanDe
                  ? "Tắt lọc 'Chỉ việc có vấn đề' hoặc bật lại cụm để xem toàn bàn."
                  : "Bật lại một cụm ở thanh lọc phía trên để xem lịch."} />
            </div>
          ) : (
            <Xl2Gantt
                  clusters={clustersHienThi}
                  ca={ban.ca}
                  caNhan={ban.ca_nhan ?? []}
                  nhom={nhom}
                  ngayLe={ban.ngay_le}
                  khoaMay={ban.khoa_may}
                  taiMay={ban.tai_may}
                  taiTo={ban.tai_to}
                  winTu={winTu}
                  winDen={winDen}
                  zoom={zoom}
                  selectedDongId={selDongId}
                  selectedEntityKey={selEntityKey}
                  barMuc={barMuc}
                  canUpdate={canUpdate}
                  onSelectDong={pickDong}
                  onPropose={(dongId, patch) => void propose(dongId, patch)}
                  onDropQueue={(r) => void duaVao(r)}
                />
              )}
            </>
          )}
        </section>

        {/* CỘT PHẢI — Smart Slide-over Inspector Panel */}
        <aside className={`xl2-panel${panelOpen && !focusMode ? " xl2-panel--open" : ""}`} aria-label="Chi tiết dòng đang chọn">
          {panelOpen && (
            <div className="xl2-panel__head">
              <div className="xl2-panel__head-title" title={selDong ? dongNhanParts(selDong).ma : selEntityLabel}>
                <Icon name={selDong ? (selDong.is_locked ? "lock" : nguonIcon(selDong.nguon)) : (selEntity ? nguonIcon(selEntity.nguon) : "workflow")} size={16} />
                <span className="xl2-panel__head-ma">{selDong ? dongNhanParts(selDong).ma : selEntityLabel}</span>
                {selDong && dongNhanParts(selDong).congDoan && (
                  <span className="xl2-panel__head-sub">· {dongNhanParts(selDong).congDoan}</span>
                )}
              </div>
              <button
                type="button"
                className="xl2-panel__closebtn"
                onClick={closePanel}
                aria-label="Đóng bảng chi tiết"
                title="Đóng (Esc)"
              >
                <Icon name="x" size={15} />
                <span>Đóng</span>
                <kbd className="xl2-kbd">Esc</kbd>
              </button>
            </div>
          )}
          <div className="xl2-panel__body">
            {/* TỰ XẾP LỊCH đứng TRÊN mọi khối chi tiết: nó làm việc theo CẢ LỆNH, nên phải thấy được cả
                khi đang chọn một bước lẻ (bấm một thanh là `selEntity` cũng được đặt theo lệnh của thanh đó). */}
            {selEntity && canUpdate && (
              <TuXepPanel ma={selEntityLabel} bc={boiCanh} kq={tuXep} busy={tuXepBusy} loi={tuXepErr}
                onChay={(ghiDe) => void chayTuXep(ghiDe)} />
            )}
            {selDong ? (
              <DongPanel
                dong={selDong} xt={xemTruoc} xtErr={xtErr} xtBusy={xtBusy} goiY={goiY}
                mays={mays} phongBans={phongBans} mayTen={mayTen} deptTen={deptTen}
                draftMay={draftMay} draftDept={draftDept} draftStart={draftStart}
                canUpdate={canUpdate}
                setDraftMay={setDraftMay} setDraftDept={setDraftDept} setDraftStart={setDraftStart}
                onApDung={apDungPanel}
                onGoiY={(mayId) => void propose(selDong.id, { may_id: mayId, department_id: null })}
                goiYKhe={goiYKhe} goiYKheLoading={goiYKheLoading}
                onGoiYKhe={() => void onGoiYKhe()} onChonKhe={onChonKhe}
                onXoaNhap={() => setAskXoaNhap(selDong)}
                onMoNguon={canMoNguon ? moNguon : undefined}
                onMoBuoc={navigate ? () => moBuocCuaDong(selDong) : undefined}
              />
            ) : selEntity ? (
              <EntityPanel nguon={selEntity.nguon} ma={selEntityLabel} bc={boiCanh}
                issues={phIssues} phErr={phErr} mayTen={mayTen} deptTen={deptTen}
                onMoNguon={canMoNguon ? moNguon : undefined} />
            ) : (
              <div className="xl2-panel__empty">
                <EmptyState icon="workflow" title="Chưa chọn gì"
                  sub="Chọn ở hàng chờ để xem vấn đề, hoặc chọn một thanh trên Gantt để xếp máy · giờ." />
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Nền mờ đóng drawer (chỉ hiện trên màn hẹp qua CSS) */}
      {panelOpen && <div className="xl2-scrim" onClick={closePanel} aria-hidden="true" />}

      {/* Dải chân — tổng MỨC toàn bàn bấm-được (C1, §3) LUÔN ở đây · rồi đếm theo thực thể đang chọn + cửa phát hành */}
      <div className="xl2-foot">
        {mucCoSoBan.length > 0 && (
          <div className="xl2-foot__muc" role="group" aria-label="Nổi thanh theo mức trên toàn bàn">
            {mucCoSoBan.map((m) => {
              const on = hlMuc === m;
              const meta = XL2_MUC_META[m];
              return (
                <button key={m} type="button"
                  className={`xl2-digest__muc xl2-digest__muc--${mucBarCls(m)}${on ? " is-on" : ""}`}
                  aria-pressed={on}
                  title={on ? "Bỏ nổi các thanh này" : `Nổi ${boardMuc[m]} thanh · ${meta.label}`}
                  onClick={() => onToggleMuc(m)}>
                  <Icon name={meta.icon} size={12} />
                  <b className="xl2-num">{boardMuc[m]}</b>
                  <span className="xl2-digest__muc-lb">{meta.label}</span>
                </button>
              );
            })}
            <span className="xl2-foot__sep" aria-hidden="true" />
          </div>
        )}
        {selEntity ? (
          <>
            <div className="xl2-foot__ctx">
              <Icon name={nguonIcon(selEntity.nguon)} size={15} />
              <span>{selEntity.nguon === "lsx" ? "Lệnh" : "Bài ghép"}</span>
              <b>{selEntityLabel}</b>
            </div>
            <div className="xl2-foot__counts">
              {phErr ? (
                <span className="xl2-foot__none xl2-foot__none--err"><Icon name="alert" size={13} /> Không kiểm được — thử chọn lại</span>
              ) : phCount == null ? (
                <span className="xl2-foot__none">đang kiểm…</span>
              ) : phIssues && phIssues.length === 0 ? (
                <span className="xl2-foot__count xl2-foot__count--ok"><Icon name="check" size={13} /> Đủ điều kiện phát hành</span>
              ) : (
                <>
                  {phCount.chan_dat_lich > 0 && (
                    <span className="xl2-foot__count xl2-foot__count--dat"><Icon name="ban" size={13} /> <b>{phCount.chan_dat_lich}</b> chặn đặt lịch</span>
                  )}
                  {phCount.chan_phat_hanh > 0 && (
                    <span className="xl2-foot__count xl2-foot__count--ph"><Icon name="lock" size={13} /> <b>{phCount.chan_phat_hanh}</b> chặn phát hành</span>
                  )}
                  {phCount.canh_bao > 0 && (
                    <span className="xl2-foot__count xl2-foot__count--warn"><Icon name="alert" size={13} /> <b>{phCount.canh_bao}</b> lưu ý</span>
                  )}
                </>
              )}
            </div>
            <div className="xl2-foot__spacer" />
            {canApprove && (
              <div className="xl2-foot__act">
                {goiPh?.co_goi ? (
                  // ĐÃ phát hành: cửa đổi sang Phát hành cập nhật (§4.3) + Thu hồi (chặn nếu có việc đã bắt đầu).
                  <>
                    {goiPh.version_hien_tai != null && goiPh.version_hien_tai > 1 && (
                      <div className="xl2-verhist">
                        <button type="button" className="xl2-foot__count xl2-foot__count--btn"
                          title="Xem lịch sử các lần phát hành cập nhật"
                          aria-expanded={showVerHist}
                          onClick={() => setShowVerHist((v) => !v)}>
                          <Icon name="history" size={13} /> phiên bản <b>{goiPh.version_hien_tai}</b>
                        </button>
                        {showVerHist && (
                          <div className="xl2-verhist__pop" role="dialog" aria-label="Lịch sử phiên bản">
                            <div className="xl2-verhist__head">
                              <span>Lịch sử phiên bản</span>
                              <button type="button" className="xl2-verhist__x" aria-label="Đóng"
                                onClick={() => setShowVerHist(false)}>
                                <Icon name="x" size={13} />
                              </button>
                            </div>
                            {goiPh.phien_bans && goiPh.phien_bans.length > 0 ? (
                              <ul className="xl2-verhist__list">
                                {[...goiPh.phien_bans].reverse().map((p) => (
                                  <li key={p.so} className="xl2-verhist__item">
                                    <div className="xl2-verhist__row">
                                      <b>{p.loai === "cap_nhat" ? `Cập nhật · bản ${p.so}` : "Phát hành gốc"}</b>
                                      <span className="xl2-verhist__khi">{ngayGio(p.luc)}</span>
                                    </div>
                                    {p.ly_do && <div className="xl2-verhist__lydo">{p.ly_do}</div>}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <div className="xl2-verhist__empty">Chưa có dữ liệu lịch sử.</div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    <Button variant="ghost" disabled={!goiPh.cho_phep_thu_hoi}
                      title={goiPh.cho_phep_thu_hoi ? undefined : "Đã có việc bắt đầu — chỉ cập nhật được phần chưa bắt đầu"}
                      onClick={() => setAskRecall({ nguon: selEntity.nguon, id: selEntity.id, ma: selEntityLabel })}>
                      Thu hồi
                    </Button>
                    <Button variant="accent" disabled={!goiPh.cho_phep_cap_nhat}
                      title={goiPh.cho_phep_cap_nhat ? "Tái chụp việc chưa bắt đầu theo lịch mới" : "Mọi việc đã bắt đầu — không còn gì để cập nhật"}
                      onClick={() => setAskCapNhat({ nguon: selEntity.nguon, id: selEntity.id, ma: selEntityLabel })}>
                      Phát hành cập nhật
                    </Button>
                  </>
                ) : (
                  // CHƯA phát hành (hoặc trạng thái gói chưa biết) — cửa Phát hành như cũ.
                  <Button variant="accent" disabled={!canReleaseNow}
                    title={canReleaseNow ? undefined : "Còn vấn đề chặn phát hành"}
                    onClick={() => setAskRelease({ nguon: selEntity.nguon, id: selEntity.id, ma: selEntityLabel })}>
                    Phát hành
                  </Button>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="xl2-foot__idle">
            <Icon name="workflow" size={14} />
            <span>Chọn một lệnh / bài ghép hoặc kéo thả vào máy để xem điều kiện phát hành.</span>
          </div>
        )}
      </div>

      {/* Hộp xem-trước → xếp */}
      <ConfirmDialog
        open={!!preview}
        wide
        title={<span><Icon name="calendar" size={16} /> Xác nhận xếp vào lịch</span>}
        confirmLabel="Xếp vào lịch"
        confirmDisabled={previewBlocked}
        busy={busy}
        onConfirm={confirmLuu}
        onCancel={() => setPreview(null)}
      >
        {preview && (
          <Xl2PreviewDialogBody
            preview={preview}
            mayTen={mayTen}
            deptTen={deptTen}
            onMoNguon={canMoNguon ? moNguon : undefined}
          />
        )}
      </ConfirmDialog>

      {/* Hộp xung đột phiên bản */}
      <ConfirmDialog
        open={!!conflict}
        title={<span><Icon name="refresh" size={16} /> Lịch vừa thay đổi</span>}
        message="Dòng này vừa được người khác chỉnh. Tải lại để lấy bản mới nhất rồi thao tác lại."
        confirmLabel="Tải lại"
        onConfirm={() => { const d = conflict; setConflict(null); reloadAll(); if (d) setSelDongId(d.id); }}
        onCancel={() => setConflict(null)}
      />

      {/* Hộp phát hành */}
      <ConfirmDialog
        open={!!askRelease}
        title={<span><Icon name="check" size={16} /> Phát hành {askRelease?.ma}?</span>}
        message="Phát hành khoá kế hoạch và mở cửa vật tư dùng chung. Kiểm phát hành đã sạch."
        confirmLabel="Phát hành"
        busy={busy}
        onConfirm={doRelease}
        onCancel={() => setAskRelease(null)}
      />

      {/* Hộp thu hồi (lý do) */}
      <ConfirmDialog
        open={!!askRecall}
        danger
        title={<span><Icon name="history" size={16} /> Thu hồi {askRecall?.ma}?</span>}
        message="Gỡ phát hành, đưa về nháp. Lý do ghi vào nhật ký."
        confirmLabel="Thu hồi"
        busy={busy}
        onConfirm={doRecall}
        onCancel={() => { setAskRecall(null); setRecallReason(""); }}
      >
        <textarea className="xl2-dlg-reason" placeholder="Lý do thu hồi (ghi vào nhật ký)…"
          value={recallReason} onChange={(e) => setRecallReason(e.target.value)} />
      </ConfirmDialog>

      {/* Hộp phát hành cập nhật (§4.3) — lý do bắt buộc, giữ lịch sử phiên bản */}
      <ConfirmDialog
        open={!!askCapNhat}
        title={<span><Icon name="refresh" size={16} /> Phát hành cập nhật {askCapNhat?.ma}?</span>}
        message={
          `Tái chụp máy + giờ của ${goiPh?.so_chua_bat_dau ?? 0} việc CHƯA bắt đầu theo lịch hiện tại, lên phiên bản mới`
          + `${goiPh?.so_da_bat_dau ? ` (giữ nguyên ${goiPh.so_da_bat_dau} việc đã bắt đầu)` : ""}`
          + ". Phân công + hỗ trợ của việc cập nhật bị huỷ để tổ xác nhận lại."
        }
        confirmLabel="Phát hành cập nhật"
        confirmDisabled={capNhatReason.trim().length < 3}
        busy={busy}
        onConfirm={doCapNhat}
        onCancel={() => { setAskCapNhat(null); setCapNhatReason(""); }}
      >
        <textarea className="xl2-dlg-reason" placeholder="Lý do cập nhật lịch (ghi vào lịch sử phiên bản)…"
          value={capNhatReason} onChange={(e) => setCapNhatReason(e.target.value)} />
      </ConfirmDialog>

      {/* Hộp xoá nháp lệnh (F3) */}
      <ConfirmDialog
        open={!!askXoaNhap}
        danger
        title={<span><Icon name="trash" size={16} /> Xoá nháp lệnh này?</span>}
        message={askXoaNhap
          ? `${dongMa(askXoaNhap)} sẽ rời khỏi kế hoạch xếp lịch. Lệnh sản xuất gốc KHÔNG bị xoá — bạn có thể xếp lại từ hàng chờ.`
          : ""}
        confirmLabel="Xoá nháp"
        busy={busy}
        onConfirm={doXoaNhap}
        onCancel={() => setAskXoaNhap(null)}
      />

      {toast && (
        <div className="xl2-toast" role="status">
          <span>{toast.text}</span>
          {toast.undo && <button type="button" className="xl2-toast__undo" onClick={() => { toast.undo?.(); setToast(null); }}>Hoàn tác</button>}
        </div>
      )}
    </div>
  );
}

// ============================ hàng chờ — 1 dòng =============================
function sameEntity(sel: { nguon: Xl2Nguon; id: number } | null, r: Xl2QRow): boolean {
  return !!sel && sel.nguon === r.nguon && sel.id === r.id;
}

function QueueRow({
  r, today, selected, canCreate, busy, onPick, onDua,
}: {
  r: Xl2QRow;
  today: string;
  selected: boolean;
  canCreate: boolean;
  busy: boolean;
  onPick: () => void;
  onDua: () => void;
}) {
  const worst = mucNangNhat(r.van_de);
  const isOverdue = (r.han != null && r.han < today) || (r.han_giao != null && r.han_giao < today);
  const stripeCls = r.is_rush
    ? " xl2-qrow--stripe-rush"
    : isOverdue
      ? " xl2-qrow--stripe-tre"
      : r.van_de.length === 0
        ? " xl2-qrow--stripe-ready"
        : "";
  const soCd = r.so_cong_doan_chua_xep;

  return (
    <div
      className={`xl2-qrow${selected ? " xl2-qrow--sel" : ""}${r.van_de.length ? " xl2-qrow--blocked" : ""}${stripeCls}`}
      role="button"
      tabIndex={0}
      draggable={canCreate && !busy}
      onDragStart={(e) => {
        e.dataTransfer.setData("application/json", JSON.stringify({ r }));
        e.dataTransfer.effectAllowed = "copy";
      }}
      onClick={onPick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}
      title={`${r.ma}${r.ten_san_pham ? ` · ${r.ten_san_pham}` : ""}${r.is_rush ? " · LỆNH GẤP" : ""}${r.han ? ` · Hạn SX: ${ngay(r.han)}` : ""}${soCd != null ? ` · ${soCd} bước chưa xếp` : ""}`}
    >
      {/* Hàng 1: Grip + Icon + Mã + Gấp + Nút đưa vào */}
      <div className="xl2-qrow__top">
        <span className="xl2-qrow__grip" title="Kéo thả vào máy trên lịch" aria-hidden="true">
          <Icon name="grip" size={12} />
        </span>
        <span className="xl2-qrow__ma">
          <Icon name={nguonIcon(r.nguon)} size={13} /> {r.ma}
        </span>
        {r.is_rush && <span className="xl2-qrow__rush" title="Lệnh gấp"><Icon name="alert" size={9} /> Gấp</span>}
        <div className="xl2-qrow__spacer" />
        {canCreate && (
          <button
            type="button"
            className="xl2-qrow__quickbtn"
            onClick={(e) => { e.stopPropagation(); onDua(); }}
            disabled={busy}
            title="Đưa vào kế hoạch"
          >
            <Icon name="plus" size={11} /> Đưa vào
          </button>
        )}
      </div>

      {/* Hàng 2: Tên sản phẩm / diễn giải */}
      {r.ten_san_pham && (
        <div className="xl2-qrow__product" title={r.ten_san_pham}>
          {r.ten_san_pham}
        </div>
      )}

      {/* Hàng 2.5: Tên khách hàng + nhãn (customer_tags thật — Khó tính/Nhạy giá/Ưu tiên...) */}
      {(r.ten_khach_hang || r.nhan_khach_hang.length > 0) && (
        <div className="xl2-qrow__tags">
          {r.ten_khach_hang && (
            <span className="xl2-qrow__customer" title={r.ten_khach_hang}>{r.ten_khach_hang}</span>
          )}
          {r.nhan_khach_hang.map((t) => (
            <span key={t} className={`xl2-tag xl2-tag--${tagTone(t)}`}>{t}</span>
          ))}
        </div>
      )}

      {/* Hàng 3: Số lượng + Số bước + Pill mức nặng nhất */}
      <div className="xl2-qrow__meta">
        {r.so_luong_dat != null && (
          <span className="xl2-qrow__qty" title="Số lượng đặt">
            <b className="xl2-num">{num(r.so_luong_dat)}</b> {r.don_vi_tinh ?? "cái"}
          </span>
        )}
        {soCd != null && soCd > 0 && (
          <span className="xl2-qrow__steps" title={`${soCd} công đoạn chưa xếp`}>
            <Icon name="workflow" size={11} /> {soCd} bước
          </span>
        )}
        {worst && <Xl2MucPill muc={worst} count={r.van_de.length} size="xs" />}
      </div>

      {/* Hàng 4: Hạn SX & Hạn giao */}
      {(r.han || r.han_giao) && (
        <div className="xl2-qrow__dates">
          {r.han && (
            <span className={`xl2-qrow__date${r.han < today ? " is-overdue" : ""}`} title="Hạn hoàn thành sản xuất">
              <Icon name="calendar" size={11} />
              <span>SX: <b>{ngay(r.han)}</b></span>
            </span>
          )}
          {r.han_giao && (
            <span className={`xl2-qrow__date${r.han_giao < today ? " is-overdue" : ""}`} title="Hạn giao hàng cho khách">
              <Icon name="truck" size={11} />
              <span>Giao: <b>{ngay(r.han_giao)}</b></span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ============================ panel: thực thể (chưa có dòng) ================
// Panel phải ĐẦY ĐỦ cho một lệnh/bài chưa chọn dòng: đầu thực thể + hai hạn + đệm ngày · vật tư tóm
// tắt · chuỗi công đoạn (thời lượng · máy/tổ/NCC · người + định biên min·chuẩn·max · quân số) · vấn
// đề chặn phát hành. Dữ liệu từ `boi_canh` (§8); `bc==null` ⇒ đang tải / lỗi.
function EntityPanel({
  nguon, ma, bc, issues, phErr, mayTen, deptTen, onMoNguon,
}: {
  nguon: Xl2Nguon;
  ma: string;
  bc: Xl2BoiCanh | null;
  issues: Xl2Issue[] | null;
  phErr: boolean;
  mayTen: Map<number, string>;
  deptTen: Map<number, string>;
  onMoNguon?: (i: Xl2Issue) => void;
}) {
  return (
    <>
      <div className="xl2-psec">
        <div className="xl2-psec__title">
          <Icon name={nguonIcon(nguon)} size={18} />
          <span style={{ flex: "1 1 auto", minWidth: 0 }}>{bc?.ma ?? ma}</span>
          {bc?.is_rush && <span className="xl2-qrow__rush"><Icon name="alert" size={10} /> Gấp</span>}
        </div>
        <div className="xl2-psub">
          <span className="xl2-psub__cd">{nguon === "lsx" ? "Lệnh sản xuất" : "Bài ghép"}</span>
          {bc?.ten_san_pham && <><span className="xl2-psub__dot">·</span><span>{bc.ten_san_pham}</span></>}
        </div>
        {bc ? (
          <div style={{ marginTop: "var(--sp-2)" }}>
            <div className="xl2-kv"><span className="xl2-kv__k">Hạn hoàn thành SX</span><span className="xl2-kv__v xl2-kv__v--num">{bc.han_sx ? ngay(bc.han_sx) : "—"}</span></div>
            <div className="xl2-kv"><span className="xl2-kv__k">Hạn giao khách</span><span className="xl2-kv__v xl2-kv__v--num">{bc.han_giao ? ngay(bc.han_giao) : "—"}</span></div>
            {bc.dem_ngay != null && (
              <div className="xl2-kv">
                <span className="xl2-kv__k">Đệm SX → giao</span>
                <span className={`xl2-kv__v xl2-kv__v--num${bc.dem_ngay < 0 ? " xl2-kv__v--tre" : ""}`}>
                  {bc.dem_ngay < 0 ? `trễ ${-bc.dem_ngay} ngày` : `${bc.dem_ngay} ngày`}
                </span>
              </div>
            )}
            <div className="xl2-kv"><span className="xl2-kv__k">Kế hoạch</span><span className="xl2-kv__v">{bc.da_vao_ke_hoach ? "Đã đưa vào" : "Chưa đưa vào"}</span></div>
          </div>
        ) : (
          <p className="xl2-note" style={{ marginTop: "var(--sp-2)" }}>
            {phErr ? "Không tải được bối cảnh — thử chọn lại." : "Đang tải bối cảnh…"}
          </p>
        )}
      </div>

      {bc && (
        <div className="xl2-psec">
          <div className="xl2-psec__h"><Icon name="box" size={13} /> Vật tư</div>
          <VatTuTomTat vt={bc.vat_tu} />
        </div>
      )}

      {bc && (
        <div className="xl2-psec">
          <div className="xl2-psec__h">
            <Icon name="workflow" size={13} /> Chuỗi công đoạn
            {bc.buoc.length > 0 && <span className="xl2-num" style={{ marginLeft: 4 }}>({bc.buoc.length})</span>}
          </div>
          {bc.buoc.length === 0 ? (
            <p className="xl2-note">
              {bc.da_vao_ke_hoach
                ? "Chưa có bước routing nào."
                : "Chưa đưa vào kế hoạch — bấm “Đưa vào kế hoạch” ở hàng chờ để sinh chuỗi bước rồi xếp máy · giờ."}
            </p>
          ) : (
            <div className="xl2-steps">
              {bc.buoc.map((b) => <StepCard key={b.id} b={b} mayTen={mayTen} deptTen={deptTen} />)}
            </div>
          )}
        </div>
      )}

      <div className="xl2-psec">
        <div className="xl2-psec__h"><Icon name="alert" size={13} /> Vấn đề chặn phát hành</div>
        {phErr ? <p className="xl2-note">Không kiểm được — thử chọn lại.</p>
          : issues == null ? <p className="xl2-note">Đang kiểm…</p>
          : <IssueList issues={issues} empty="Không có vấn đề chặn phát hành." onMoNguon={onMoNguon} />}
      </div>
    </>
  );
}

// Tóm tắt vật tư mức lệnh: MỘT dòng trạng thái (đủ / thiếu N món / chưa rõ / lỗi) + vài số phụ.
function VatTuTomTat({ vt }: { vt: Xl2VatTuTomTat }) {
  if (!vt.bat) return <p className="xl2-note">Chưa bật giữ chỗ vật tư cho lệnh này.</p>;
  if (vt.loi) {
    return (
      <div className="xl2-vt xl2-vt--warn">
        <Icon name="alert" size={14} /><span>Bảng cân đối vật tư đang lỗi — chưa kết luận đủ/thiếu.</span>
      </div>
    );
  }
  const st: { cls: string; icon: IconName; text: string } = vt.du
    ? { cls: "ok", icon: "check", text: "Đủ vật tư" }
    : vt.khong_ro
      ? { cls: "warn", icon: "alert", text: "Chưa rõ vật tư" }
      : { cls: "bad", icon: "lock", text: `Thiếu ${vt.so_mon_thieu ?? "?"} món` };
  return (
    <>
      <div className={`xl2-vt xl2-vt--${st.cls}`}><Icon name={st.icon} size={14} /><span>{st.text}</span></div>
      {vt.so_mon_dang_giu != null && (
        <div style={{ marginTop: "var(--sp-2)" }}>
          <div className="xl2-kv"><span className="xl2-kv__k">Đang giữ chỗ</span><span className="xl2-kv__v xl2-kv__v--num">{vt.so_mon_dang_giu} món</span></div>
        </div>
      )}
      {/* `xep_som_nhat` chỉ có khi CÒN vật tư ĐANG VỀ (giữ chỗ nguồn đang-về, chưa nhập kho): không
          được bắt đầu trước ngày hứa về. Nói thẳng "đang về" thay vì nhãn nhạt "xếp sớm nhất" (B4). */}
      {vt.xep_som_nhat && (
        <div className="xl2-vt xl2-vt--warn" style={{ marginTop: "var(--sp-2)" }}>
          <Icon name="truck" size={14} />
          <span>Vật tư đang về — xếp được sớm nhất {ngay(vt.xep_som_nhat)}</span>
        </div>
      )}
    </>
  );
}

// Một BƯỚC trong chuỗi DAG: tên + tài nguyên (máy/tổ/NCC) + thời lượng (dải min–max) + nguồn tính +
// người & định biên (min·chuẩn·max, item 17) + quân số (đỏ khi quá tải).
function StepCard({
  b, mayTen, deptTen,
}: {
  b: Xl2BoiCanhBuoc;
  mayTen: Map<number, string>;
  deptTen: Map<number, string>;
}) {
  const res: { icon: IconName; label: string } = b.may_id != null
    ? { icon: "printer", label: b.may_ten ?? mayTen.get(b.may_id) ?? `Máy #${b.may_id}` }
    : b.department_id != null
      ? { icon: "users", label: b.to_ten ?? deptTen.get(b.department_id) ?? `Tổ #${b.department_id}` }
      : b.nha_cung_cap
        ? { icon: "truck", label: b.nha_cung_cap }
        : { icon: "clock", label: "Chưa gán máy · tổ" };
  const hasRange = b.chiem_may_phut_min !== b.chiem_may_phut_max;
  const nguonLb = b.nguon_thoi_luong === "thue_ngoai" ? "thuê ngoài"
    : b.nguon_thoi_luong === "may" ? "theo máy" : "làm tay";
  const db = b.dinh_bien;
  const { coBien: dbCoBien, text: dbText, ngoai: dbNgoai } = nhanLucTom(b.so_nhan_cong, db);
  const worst = mucNangNhat(b.van_de);
  return (
    <div className={`xl2-step${b.is_locked ? " xl2-step--locked" : ""}`}>
      <div className="xl2-step__head">
        <span className="xl2-step__no xl2-num">{b.thu_tu}</span>
        <span className="xl2-step__name">{b.cong_doan_ten ?? "—"}</span>
        {b.is_locked && <Icon name="lock" size={12} className="xl2-step__lock" />}
        {worst && <span className="xl2-step__muc"><Xl2MucPill muc={worst} count={b.van_de.length} size="xs" /></span>}
      </div>
      <div className="xl2-step__res"><Icon name={res.icon} size={12} /> {res.label}</div>
      {b.start_at && (
        <div className="xl2-step__time xl2-num">{ngayGio(b.start_at)} → {b.finish_at ? ngayGio(b.finish_at) : "—"}</div>
      )}
      <div className="xl2-step__facts">
        <span className="xl2-step__fact">
          <Icon name="clock" size={11} /> {thoiLuong(b.chiem_may_phut)}
          {hasRange && <span className="xl2-step__range"> ({thoiLuong(b.chiem_may_phut_min)}–{thoiLuong(b.chiem_may_phut_max)})</span>}
        </span>
        <span className="xl2-step__tag">{nguonLb}</span>
        {b.so_nhan_cong != null && (
          <span
            className={`xl2-step__fact${dbNgoai ? " xl2-step__fact--warn" : ""}`}
            title={dbNgoai ? `Bố trí ${b.so_nhan_cong} người, ngoài biên ${db.toi_thieu ?? "–"}–${db.toi_da ?? "–"} của bước — sửa ở màn Lệnh sản xuất, khối Nhân lực.` : "Số người bố trí (kế hoạch) — bàn xếp lịch cân quân số tổ theo số này."}
          >
            <Icon name={dbNgoai ? "alert" : "users"} size={11} /> {b.so_nhan_cong} người
          </span>
        )}
        {dbText && (
          <span
            className="xl2-step__fact"
            title={dbCoBien ? "Định biên của bước: tối thiểu · tiêu chuẩn · tối đa" : "Kíp vận hành tiêu chuẩn theo danh mục Máy"}
          >
            ĐB {dbText}
          </span>
        )}
      </div>
      {b.quan_so && (
        <div className={`xl2-step__qs${b.quan_so.con_ranh < 0 ? " xl2-step__qs--over" : ""}`}>
          <Icon name={b.quan_so.con_ranh < 0 ? "alert" : "users"} size={11} />
          <span>
            Quân số tổ {b.quan_so.so_nguoi} · đỉnh {b.quan_so.dinh} ·{" "}
            {b.quan_so.con_ranh < 0 ? `quá tải ${-b.quan_so.con_ranh}` : `còn rảnh ${b.quan_so.con_ranh}`}
          </span>
        </div>
      )}
    </div>
  );
}

// ============================ panel: dòng đã chọn ==========================
// Item 14 — HỆ QUẢ của cách đặt hiện tại (xem-trước, KHÔNG ghi): "hạn mới" (giờ lệnh xong muộn nhất) so
// hạn SX + các bước SAU đã có giờ bị lấn thứ tự. Thuần thông tin — v2 xếp TAY, không tự dời hộ; chỉ phơi
// ra để người xếp tự cân. Rỗng cả hai (dòng chưa giờ / không lấn ai) ⇒ không vẽ khối.
function Xl2AnhHuong({ xt }: { xt: Xl2XemTruoc }) {
  const co = xt.han_moi != null || xt.cong_doan_anh_huong.length > 0;
  if (!co) return null;
  return (
    <div className="xl2-psec">
      <div className="xl2-psec__h"><Icon name="workflow" size={13} /> Ảnh hưởng khi xếp</div>
      {xt.han_moi != null && (
        <div className="xl2-kv">
          <span className="xl2-kv__k">Hạn mới · lệnh xong</span>
          <span className={`xl2-kv__v xl2-kv__v--num${xt.tre_han_sx ? " xl2-kv__v--tre" : ""}`}>
            {ngay(xt.han_moi)}
            {xt.tre_han_sx && xt.tre_ngay != null && (
              <span className="xl2-tre-pill"><Icon name="alert" size={11} /> trễ {xt.tre_ngay} ngày</span>
            )}
          </span>
        </div>
      )}
      {xt.han_sx && (
        <div className="xl2-kv"><span className="xl2-kv__k">Hạn SX</span><span className="xl2-kv__v xl2-kv__v--num">{ngay(xt.han_sx)}</span></div>
      )}
      {xt.cong_doan_anh_huong.length > 0 && (
        <div className="xl2-ah">
          <div className="xl2-ah__lb">
            <Icon name="alert" size={11} /> {xt.cong_doan_anh_huong.length} bước sau bị lấn thứ tự — người xếp tự cân
          </div>
          {xt.cong_doan_anh_huong.map((a) => (
            <div key={a.dong_id} className="xl2-ah__row">
              <span className="xl2-ah__tt xl2-num">B{a.thu_tu + 1}</span>
              <span className="xl2-ah__cd">{a.cong_doan_ten ?? `Bước #${a.dong_id}`}</span>
              <span className="xl2-ah__t xl2-num">{a.start_at ? ngayGio(a.start_at) : "—"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function computeSlackDays(hanMoiStr: string | null | undefined, hanSxStr: string | null | undefined): number | null {
  if (!hanMoiStr || !hanSxStr) return null;
  const dMoi = new Date(hanMoiStr.slice(0, 10));
  const dSx = new Date(hanSxStr.slice(0, 10));
  if (Number.isNaN(dMoi.getTime()) || Number.isNaN(dSx.getTime())) return null;
  return Math.round((dSx.getTime() - dMoi.getTime()) / 86_400_000);
}

function Xl2PreviewDialogBody({
  preview,
  mayTen,
  deptTen,
  onMoNguon,
}: {
  preview: { dong: Xl2Dong; patch: Xl2Patch; xt: Xl2XemTruoc };
  mayTen: Map<number, string>;
  deptTen: Map<number, string>;
  onMoNguon?: (i: Xl2Issue) => void;
}) {
  const { dong, patch, xt } = preview;
  const nhan = dongNhanParts(dong);
  const mayId = patch.may_id !== undefined ? patch.may_id : dong.may_id;
  const deptId = patch.department_id !== undefined ? patch.department_id : dong.department_id;
  const mayName = mayId != null ? (mayTen.get(mayId) ?? `Máy #${mayId}`) : null;
  const deptName = deptId != null ? (deptTen.get(deptId) ?? `Tổ #${deptId}`) : null;
  const resourceName = mayName ?? deptName ?? "Chưa gán máy / tổ";
  const resourceIcon: IconName = mayName ? "printer" : deptName ? "users" : "truck";

  const startIso = xt.start_at ?? patch.start_at ?? dong.start_at;
  const finishIso = xt.finish_at ?? dong.finish_at;
  const slackDays = computeSlackDays(xt.han_moi ?? finishIso, xt.han_sx);
  const hasIssues = xt.van_de && xt.van_de.length > 0;
  // Nhân lực bước. Câu cảnh báo quân số chỉ in con số đỉnh ("Đỉnh 5 người…") — đứng một mình nó
  // không cho biết 5 ở đâu ra, cũng không cho biết bước định biên bao nhiêu. Dán thẳng vào hàng
  // thẻ dữ kiện: bố trí bao nhiêu, biên bao nhiêu, ngoài biên thì tô đỏ.
  const nl = nhanLucTom(xt.so_nhan_cong, xt.dinh_bien);
  const nhanLucText = nl.text == null ? null : nl.coBien ? `định biên ${nl.text}` : `kíp ${nl.text}`;
  const nhanLucNgoai = nl.ngoai;

  return (
    <div className="xl2-dlg-preview">
      {/* 1. Context header: Lệnh / Sản phẩm / Công đoạn / Tài nguyên */}
      <div className="xl2-dlg-context">
        <div className="xl2-dlg-context__main">
          <div className="xl2-dlg-context__title">
            <Icon name={dong.is_locked ? "lock" : nguonIcon(dong.nguon)} size={15} />
            <span className="xl2-dlg-context__ma">{nhan.ma}</span>
            {nhan.sanPham && <span className="xl2-dlg-context__sp">· {nhan.sanPham}</span>}
          </div>
          <div className="xl2-dlg-context__sub">
            <span className="xl2-dlg-context__cd">
              {dong.buoc_thu_tu != null ? `Bước ${dong.buoc_thu_tu + 1}: ` : ""}{nhan.congDoan || "Công đoạn"}
            </span>
          </div>
        </div>
        <div className="xl2-dlg-context__res">
          <span className="xl2-dlg-context__res-lb">Tài nguyên thực hiện</span>
          <span className="xl2-dlg-context__res-val">
            <Icon name={resourceIcon} size={12} /> {resourceName}
          </span>
        </div>
      </div>

      {/* 2. Time Breakdown Card: Bắt đầu vs Kết thúc + Chiếm máy */}
      <div className="xl2-dlg-card">
        <div className="xl2-dlg-timegrid">
          <div className="xl2-dlg-timecol">
            <span className="xl2-dlg-timelb">Bắt đầu dự kiến</span>
            <span className="xl2-dlg-timeval">{startIso ? ngayGio(startIso) : "—"}</span>
          </div>
          <div className="xl2-dlg-timearrow">
            <Icon name="arrowRight" size={14} />
          </div>
          <div className="xl2-dlg-timecol">
            <span className="xl2-dlg-timelb">Kết thúc dự kiến</span>
            <span className="xl2-dlg-timeval xl2-dlg-timeval--finish">{finishIso ? ngayGio(finishIso) : "—"}</span>
          </div>
        </div>
        <div className="xl2-dlg-timemeta">
          <span className="xl2-dlg-tag">
            <Icon name="clock" size={11} /> Chiếm máy: <b>{thoiLuong(xt.chiem_may_phut)}</b>
          </span>
          {dong.boc_tach && (
            <span className="xl2-dlg-tag">
              Canh máy {dong.boc_tach.canh_may_phut}p · Chạy {dong.boc_tach.chay_phut}p
            </span>
          )}
          <span className="xl2-dlg-tag">
            {xt.theo_may ? "Theo tốc độ máy" : "Theo định mức"}
          </span>
          {xt.so_nhan_cong != null && (
            <span
              className={`xl2-dlg-tag${nhanLucNgoai ? " xl2-dlg-tag--warn" : ""}`}
              title={
                nhanLucNgoai
                  ? "Số người bố trí ở bước nằm ngoài định biên — sửa tại màn Lệnh sản xuất, khối Nhân lực."
                  : "Số người bố trí ở bước (khai tại màn Lệnh sản xuất, khối Nhân lực)."
              }
            >
              <Icon name={nhanLucNgoai ? "alert" : "users"} size={11} /> Bố trí{" "}
              <b>{xt.so_nhan_cong} người</b>
              {nhanLucText ? ` · ${nhanLucText}` : ""}
            </span>
          )}
        </div>
      </div>

      {/* 3. Deadline & Slack Analysis (nếu có hạn) */}
      {(xt.han_moi != null || xt.han_sx != null || xt.han_giao != null) && (
        <div className="xl2-dlg-card xl2-dlg-card--slack">
          <div className="xl2-dlg-slackgrid">
            <div className="xl2-dlg-slackitem">
              <span className="xl2-dlg-timelb">Mốc xong lệnh mới</span>
              <span className="xl2-dlg-timeval">{xt.han_moi ? ngay(xt.han_moi) : "—"}</span>
            </div>
            <div className="xl2-dlg-slackitem">
              <span className="xl2-dlg-timelb">Hạn hoàn thành SX</span>
              <div className="xl2-dlg-slackval">
                <span className="xl2-dlg-timeval">{xt.han_sx ? ngay(xt.han_sx) : "—"}</span>
                {slackDays != null && (
                  <span className={`xl2-slack-pill ${slackDays < 0 ? "xl2-slack-pill--late" : "xl2-slack-pill--ok"}`}>
                    {slackDays < 0 ? `Trễ ${Math.abs(slackDays)} ngày` : `Dư ${slackDays} ngày`}
                  </span>
                )}
              </div>
            </div>
            {xt.han_giao && (
              <div className="xl2-dlg-slackitem">
                <span className="xl2-dlg-timelb">Hạn giao khách</span>
                <span className="xl2-dlg-timeval">{ngay(xt.han_giao)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4. Downstream Step Impact (nếu có bước sau bị lấn) */}
      {xt.cong_doan_anh_huong.length > 0 && (
        <div className="xl2-dlg-impact">
          <div className="xl2-dlg-impact__h">
            <Icon name="alert" size={13} /> {xt.cong_doan_anh_huong.length} bước sau bị lấn thứ tự thời gian:
          </div>
          <div className="xl2-dlg-impact__list">
            {xt.cong_doan_anh_huong.map((a) => (
              <div key={a.dong_id} className="xl2-dlg-impact__row">
                <span className="xl2-dlg-impact__tt">B{a.thu_tu + 1}</span>
                <span className="xl2-dlg-impact__cd">{a.cong_doan_ten ?? `Bước #${a.dong_id}`}</span>
                <span className="xl2-dlg-impact__t">{a.start_at ? ngayGio(a.start_at) : "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Validation Status Callout */}
      {!hasIssues ? (
        <div className="xl2-dlg-clean">
          <Icon name="check" size={15} />
          <span>Đủ điều kiện xếp lịch — Không phát hiện xung đột máy / tổ.</span>
        </div>
      ) : (
        <div className="xl2-dlg-issues">
          <div className="xl2-dlg-issues__h"><Icon name="alert" size={13} /> Lưu ý & Vấn đề cần cân nhắc:</div>
          <IssueList issues={xt.van_de} empty="" onMoNguon={onMoNguon} />
        </div>
      )}
    </div>
  );
}

function fmtSlotDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const thuNames = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
  const thu = thuNames[d.getDay()];
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${thu}, ${dd}/${mm}`;
}

function fmtSlotTimeRange(startIso: string, finishIso: string) {
  const s = new Date(startIso);
  const f = new Date(finishIso);
  if (Number.isNaN(s.getTime()) || Number.isNaN(f.getTime())) return `${ngayGio(startIso)} → ${ngayGio(finishIso)}`;
  const sTime = s.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  const fTime = f.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  return `${sTime} – ${fTime}`;
}

// ============================ nhãn THẬT cho gợi ý ==========================
// `nhan_ngay` do backend chấm (thứ · cuối tuần · ngày lễ · ca đêm). v2 KHÔNG chặn chủ nhật / ngày lễ
// (chỉ tô nền) nên một khe "sạch luật" vẫn có thể rơi vào mùng 2/9 — phải nói ra để người xếp tự
// quyết, thay cho cái nhãn "Lý tưởng" cũ vốn chỉ có nghĩa là "không có cảnh báo".
function NhanNgayTags({ nn, soCanhBao }: { nn?: Xl2NhanNgay | null; soCanhBao: number }) {
  const tags: { text: string; icon: IconName; warn: boolean }[] = [];
  if (nn?.thu) tags.push({ text: nn.thu, icon: "calendar", warn: false });
  if (nn?.ngay_le) tags.push({ text: nn.ngay_le, icon: "calendar", warn: true });
  else if (nn?.cuoi_tuan) tags.push({ text: "Cuối tuần", icon: "calendar", warn: true });
  if (nn?.ca_dem) tags.push({ text: "Ca đêm", icon: "clock", warn: true });
  if (soCanhBao > 0) tags.push({ text: `${soCanhBao} lưu ý`, icon: "alert", warn: true });
  return (
    <>
      {tags.map((t, i) => (
        <span key={i} className={`xl2-smartcard__tag${t.warn ? " xl2-smartcard__tag--warn" : ""}`}>
          <Icon name={t.icon} size={11} /> {t.text}
        </span>
      ))}
      {nn != null && soCanhBao === 0 && !nn.ngay_le && !nn.cuoi_tuan && !nn.ca_dem && (
        <span className="xl2-smartcard__tag xl2-smartcard__tag--ok">
          <Icon name="check" size={11} /> Không vướng luật nào
        </span>
      )}
    </>
  );
}

// Ba số thời lượng: LỊCH tính theo mức TRUNG BÌNH; nhanh-nhất … chậm-nhất chỉ là dải (chính là "hai
// cái râu" trên thanh Gantt). Bằng nhau ⇒ máy chưa khai tốc độ nhanh/chậm — nói thẳng chứ đừng để
// người xem tưởng máy chạy chính xác tuyệt đối.
function DaiThoiLuong({ tb, min, max }: { tb: number; min?: number | null; max?: number | null }) {
  const co = min != null && max != null && max > min;
  return (
    <span className="xl2-smartcard__tag" title={co
      ? `Lịch tính theo mức trung bình ${thoiLuong(tb)} · nhanh nhất ${thoiLuong(min)} · chậm nhất ${thoiLuong(max)}`
      : "Máy chưa khai tốc độ nhanh nhất / chậm nhất nên chỉ có một con số — không vẽ râu"}>
      <Icon name="clock" size={11} /> {thoiLuong(tb)}
      {co && <i className="xl2-dai">{thoiLuong(min)} – {thoiLuong(max)}</i>}
    </span>
  );
}

// Ba BẬC điểm máy — chỉ để đổi màu chip, KHÔNG phải một luật nghiệp vụ. Cố ý không có bậc "đỏ":
// mọi máy còn trong danh sách đều xếp được, chỉ hơn kém nhau chỗ phí; cái thật sự phải cảnh báo là
// cờ `tre_han` chứ không phải điểm thấp.
function bacDiem(d: number): "tot" | "kha" | "thuong" {
  return d >= 75 ? "tot" : d >= 50 ? "kha" : "thuong";
}

// ============================ tự xếp lịch cả lệnh ==========================
// Người kế hoạch bấm một nút, hệ tự chọn MÁY + GIỜ cho từng bước theo đúng thứ tự routing. Máy chỉ
// GHI NHẬN đề xuất: mọi bước xếp xong vẫn hiện ra kèm câu vì-sao và các lưu ý, sửa tay lại được.
function TuXepPanel({ bc, kq, busy, loi, onChay }: {
  ma: string;
  bc: Xl2BoiCanh | null;
  kq: Xl2TuXep | null;
  busy: boolean;
  loi: string | null;
  onChay: (ghiDe: boolean) => void;
}) {
  // KHOÁ tại chỗ + nói lý do, không giấu nút (giấu đi thì người dùng tưởng chức năng hỏng).
  const ly = !bc ? "Đang tải bối cảnh lệnh…"
    : !bc.da_vao_ke_hoach ? "Lệnh chưa vào kế hoạch — bấm “Đưa vào kế hoạch” ở hàng chờ trước đã."
      : bc.buoc.length === 0 ? "Lệnh chưa có bước công đoạn nào để xếp."
        : null;
  const khoa = busy || ly != null;
  return (
    <div className="xl2-psec xl2-tuxep">
      <div className="xl2-psec__h"><Icon name="zap" size={13} /> Tự xếp lịch cả lệnh</div>
      <div className="xl2-tuxep__btns">
        <Button variant="accent" block disabled={khoa} onClick={() => onChay(false)}>
           {busy ? "Đang xếp…" : "Xếp các bước còn trống"}
        </Button>
        <Button variant="secondary" block disabled={khoa} onClick={() => onChay(true)}>
           Xếp lại toàn bộ chuỗi
        </Button>
      </div>
      {ly && <p className="xl2-note">{ly}</p>}
      {loi && <p className="xl2-note">{loi}</p>}
      {kq && (
        <div className="xl2-tuxep__kq">
          <div className={`xl2-tuxep__tom${kq.tre_han_sx ? " is-tre" : ""}`}>
            <Icon name={kq.tre_han_sx ? "alert" : "check"} size={13} /> {kq.tom_tat}
          </div>
          {(kq.da_xep ?? []).map((b) => (
            <div key={b.dong_id} className="xl2-tuxep__b">
              <div className="xl2-tuxep__b-top">
                <span className="xl2-tuxep__tt">B{b.thu_tu + 1}</span>
                <span className="xl2-tuxep__cd">{b.cong_doan_ten ?? `Bước #${b.dong_id}`}</span>
                <span className="xl2-tuxep__may">
                  {b.may_ten ?? (b.may_id != null ? `Máy #${b.may_id}` : "không dùng máy")}
                </span>
              </div>
              <div className="xl2-tuxep__b-time">{ngayGio(b.start_at)} → {ngayGio(b.finish_at)}</div>
              <div className="xl2-tuxep__b-meta">
                <DaiThoiLuong tb={b.chiem_may_phut} min={b.chiem_may_phut_min} max={b.chiem_may_phut_max} />
                {b.so_may_xet > 0 && (
                  <span className="xl2-smartcard__tag">{b.so_may_xet} máy đã cân nhắc</span>
                )}
                {(b.canh_bao ?? []).length > 0 && (
                  <span className="xl2-smartcard__tag xl2-smartcard__tag--warn">
                    <Icon name="alert" size={11} /> {(b.canh_bao ?? []).length} lưu ý
                  </span>
                )}
              </div>
              <div className="xl2-tuxep__why">{b.ly_do}</div>
            </div>
          ))}
          {(kq.bo_qua ?? []).length > 0 && (
            <div className="xl2-tuxep__bq">
              <div className="xl2-tuxep__bq-h">
                <Icon name="alert" size={12} /> {kq.bo_qua.length} bước chưa xếp được — thiếu gì nói thẳng:
              </div>
              {kq.bo_qua.map((b) => (
                <div key={b.dong_id} className="xl2-tuxep__bq-row">
                  <b>B{b.thu_tu + 1}</b> {b.cong_doan_ten ?? `#${b.dong_id}`} — {b.ly_do}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DongPanel({
  dong, xt, xtErr, xtBusy, goiY, mays, phongBans, mayTen, deptTen,
  draftMay, draftDept, draftStart, canUpdate,
  setDraftMay, setDraftDept, setDraftStart, onApDung, onGoiY,
  goiYKhe, goiYKheLoading, onGoiYKhe, onChonKhe, onXoaNhap, onMoNguon, onMoBuoc,
}: {
  dong: Xl2Dong;
  xt: Xl2XemTruoc | null;
  xtErr: boolean;
  xtBusy: boolean;
  goiY: XepLichGoiY | null;
  mays: Row[];
  phongBans: Row[];
  mayTen: Map<number, string>;
  deptTen: Map<number, string>;
  draftMay: number | null;
  draftDept: number | null;
  draftStart: string;
  canUpdate: boolean;
  setDraftMay: (v: number | null) => void;
  setDraftDept: (v: number | null) => void;
  setDraftStart: (v: string) => void;
  onApDung: () => void;
  onGoiY: (mayId: number) => void;
  goiYKhe: Xl2GoiYKhe | null;
  goiYKheLoading: boolean;
  onGoiYKhe: () => void;
  onChonKhe: (k: Xl2Khe) => void;
  onXoaNhap: () => void;
  onMoNguon?: (i: Xl2Issue) => void;
  /** Mở đúng chỗ SỬA số người của bước (Lệnh SX / Bài ghép). Không có `navigate` thì bỏ. */
  onMoBuoc?: () => void;
}) {
  const resLabel: ReactNode = dong.may_id != null
    ? <><Icon name="printer" size={13} /> {mayTen.get(dong.may_id) ?? `Máy #${dong.may_id}`}</>
    : dong.department_id != null
      ? <><Icon name="users" size={13} /> {deptTen.get(dong.department_id) ?? `Tổ #${dong.department_id}`}</>
      : <><Icon name="truck" size={13} /> Chưa gán máy / tổ</>;
  const nhan = dongNhanParts(dong);
  const nl = nhanLucTom(xt?.so_nhan_cong, xt?.dinh_bien);

  return (
    <>
      <div className="xl2-psec">
        <div className="xl2-psec__title">
          <Icon name={dong.is_locked ? "lock" : nguonIcon(dong.nguon)} size={18} />
          {nhan.ma}
        </div>
        {(nhan.congDoan || nhan.sanPham) && (
          <div className="xl2-psub">
            {nhan.congDoan && <span className="xl2-psub__cd">{nhan.congDoan}</span>}
            {nhan.congDoan && nhan.sanPham && <span className="xl2-psub__dot">·</span>}
            {nhan.sanPham && <span>{nhan.sanPham}</span>}
          </div>
        )}
        <div style={{ marginTop: "var(--sp-2)" }}>
          <div className="xl2-kv"><span className="xl2-kv__k">Tài nguyên</span><span className="xl2-kv__v" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>{resLabel}</span></div>
          <div className="xl2-kv"><span className="xl2-kv__k">Bắt đầu</span><span className="xl2-kv__v xl2-kv__v--num">{dong.start_at ? ngayGio(dong.start_at) : "—"}</span></div>
          <div className="xl2-kv"><span className="xl2-kv__k">Kết thúc</span><span className="xl2-kv__v xl2-kv__v--num">{(xt?.finish_at ?? dong.finish_at) ? ngayGio(xt?.finish_at ?? dong.finish_at) : "—"}</span></div>
          {xt && <div className="xl2-kv"><span className="xl2-kv__k">Chiếm máy</span><span className="xl2-kv__v xl2-kv__v--num">{thoiLuong(xt.chiem_may_phut)}{xt.theo_may ? " (theo máy)" : ""}</span></div>}
          {/* NHÂN LỰC — khối này trước chỉ có tài nguyên + giờ + chiếm máy, nên khi lịch kêu "đỉnh N
              người vượt quân số tổ" người xếp không thấy bước khai bao nhiêu người, cũng không biết
              đi đâu sửa. Nay số bố trí đứng cạnh ba mốc định biên, ra ngoài biên thì tô tín hiệu, và
              có lối mở thẳng sang chỗ sửa. */}
          {xt && xt.so_nhan_cong != null && (
            <div className="xl2-kv">
              <span className="xl2-kv__k">Nhân lực</span>
              <span className={`xl2-kv__v xl2-kv__v--nhanluc${nl.ngoai ? " xl2-kv__v--canh" : ""}`}>
                <span className="xl2-kv__v--num">
                  {nl.ngoai && <Icon name="alert" size={11} />} {xt.so_nhan_cong} người
                </span>
                {nl.text && (
                  <span
                    className="xl2-kv__bien"
                    title={nl.coBien
                      ? "Định biên của bước: tối thiểu · tiêu chuẩn · tối đa"
                      : "Kíp vận hành tiêu chuẩn theo danh mục Máy"}
                  >
                    {nl.coBien ? "biên" : "kíp"} {nl.text}
                  </span>
                )}
                {onMoBuoc && (
                  <button type="button" className="xl2-kv__go" onClick={onMoBuoc}
                    title={dong.nguon === "lsx"
                      ? "Mở lệnh sản xuất — sửa số người ở khối Nhân lực của bước."
                      : "Mở màn Bài ghép — sửa số người ở bước chung của bài."}>
                    <Icon name="link" size={11} /> Sửa
                  </button>
                )}
              </span>
            </div>
          )}
          {dong.is_locked && <div className="xl2-kv"><span className="xl2-kv__k">Trạng thái</span><span className="xl2-kv__v">Đã khóa</span></div>}
        </div>
      </div>

      {xt && <Xl2AnhHuong xt={xt} />}

      {canUpdate && !dong.is_locked && (
        <div className="xl2-psec">
          <div className="xl2-psec__h"><Icon name="settings" size={13} /> Đặt máy · tổ · giờ</div>
          <label className="xl2-field">
            <span className="xl2-field__lb">Máy</span>
            <select value={draftMay ?? ""} onChange={(e) => { const v = e.target.value ? Number(e.target.value) : null; setDraftMay(v); if (v != null) setDraftDept(null); }}>
              <option value="">— không gán máy —</option>
              {mays.map((m) => <option key={m.id} value={m.id}>{m.ma} · {m.ten}</option>)}
            </select>
          </label>
          <label className="xl2-field">
            <span className="xl2-field__lb">Tổ (nếu bước làm tay)</span>
            <select value={draftDept ?? ""} onChange={(e) => { const v = e.target.value ? Number(e.target.value) : null; setDraftDept(v); if (v != null) setDraftMay(null); }}>
              <option value="">— không gán tổ —</option>
              {phongBans.map((p) => <option key={p.id} value={p.id}>{p.ma} · {p.ten}</option>)}
            </select>
          </label>
          <label className="xl2-field">
            <span className="xl2-field__lb">Bắt đầu</span>
            <input type="datetime-local" value={draftStart} onChange={(e) => setDraftStart(e.target.value)} />
          </label>
          <div style={{ marginTop: "var(--sp-3)" }}>
            <Button variant="accent" block onClick={onApDung}><Icon name="calendar" size={14} /> Xem trước & xếp</Button>
          </div>
        </div>
      )}

      {HIEN_GOI_Y_KHE && canUpdate && !dong.is_locked && (
        <div className="xl2-psec">
          <div className="xl2-psec__h xl2-psec__h--flex">
            <span className="xl2-psec__h-left"><Icon name="cpu" size={13} /> Gợi ý khe rảnh thông minh</span>
            {goiYKhe && goiYKhe.khe.length > 0 && (
              <button
                type="button"
                className="xl2-smartslot__reload"
                onClick={onGoiYKhe}
                disabled={goiYKheLoading}
                title="Tính lại gợi ý khe"
              >
                <Icon name="refresh" size={11} /> Tính lại
              </button>
            )}
          </div>
          {(!goiYKhe || goiYKhe.khe.length === 0) && !goiYKheLoading && (
            <Button variant="secondary" block onClick={onGoiYKhe}>
              <Icon name="search" size={14} /> Tìm ≤3 khe rảnh sớm nhất
            </Button>
          )}
          {goiYKheLoading ? (
            <div className="xl2-smartslot-skel">
              <div className="xl2-smartslot-skel__card" />
              <div className="xl2-smartslot-skel__card" />
              <div className="xl2-smartslot-skel__card" />
            </div>
          ) : goiYKhe && goiYKhe.khe.length > 0 ? (
            <div className="xl2-smartslot">
              {/* Backend trả các khe theo THỨ TỰ SỚM DẦN trên máy đang chọn — nên nhãn cũng chỉ được nói
                  đúng chừng đó. Ba tên chiến-lược cũ ("Tiết kiệm canh máy" / "Đệm an toàn") là chữ FE
                  tự gán theo vị trí mảng, không có gì bên dưới đỡ; ba lớp màu thì GIỮ vì chúng chỉ để
                  phân biệt thẻ 1-2-3. Nhãn thẻ 2-3 mang SỐ THẬT: muộn hơn khe sớm nhất bao lâu —
                  đó là cái giá phải trả khi bỏ khe đầu, thứ duy nhất phân biệt được ba thẻ này. */}
              {goiYKhe.khe.map((k, i) => {
                const strat = i === 0 ? "speed" : i === 1 ? "batch" : "safe";
                const treP = Math.max(0, Math.round(
                  (new Date(k.start_at).getTime() - new Date(goiYKhe.khe[0].start_at).getTime()) / 60000));
                const stratName = i === 0 ? "Sớm nhất" : `Muộn hơn ${thoiLuong(treP)}`;
                return (
                  <div
                    key={i}
                    className={`xl2-smartcard xl2-smartcard--${strat}`}
                    onClick={() => onChonKhe(k)}
                    title={`Gán vào khe: ${ngayGio(k.start_at)}`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onChonKhe(k); } }}
                  >
                    <div className="xl2-smartcard__head">
                      <span className="xl2-smartcard__pill">{stratName}</span>
                      <span className="xl2-smartcard__date">{fmtSlotDate(k.start_at)}</span>
                    </div>
                    <div className="xl2-smartcard__main">
                      <div className="xl2-smartcard__time">{fmtSlotTimeRange(k.start_at, k.finish_at)}</div>
                      <button
                        type="button"
                        className="xl2-smartcard__apply"
                        onClick={(e) => { e.stopPropagation(); onChonKhe(k); }}
                      >
                        Gán
                      </button>
                    </div>
                    <div className="xl2-smartcard__meta">
                      <DaiThoiLuong tb={k.chiem_may_phut} min={k.chiem_may_phut_min} max={k.chiem_may_phut_max} />
                      <NhanNgayTags nn={k.nhan_ngay} soCanhBao={(k.canh_bao ?? []).length} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : goiYKhe ? (
            <div style={{ marginTop: "var(--sp-2)" }}>
              <EmptyState icon="search" title="Chưa có khe phù hợp"
                sub={goiYKhe.ghi_chu ?? "Thử chọn máy hoặc nới cửa sổ thời gian."} />
            </div>
          ) : null}
        </div>
      )}

      {HIEN_GOI_Y_MAY && goiY && canUpdate && !dong.is_locked && (goiY.goi_y_may.length > 0 || goiY.vi_sao_trong) && (
        <div className="xl2-psec">
          <div className="xl2-goiy">
            {goiY.goi_y_may.map((g) => (
              <button key={g.may_id} type="button"
                className={`xl2-goiy__row${g.tre_han ? " xl2-goiy__row--tre" : ""}`}
                onClick={() => onGoiY(g.may_id)}>
                <span className="xl2-goiy__top">
                  <Icon name="printer" size={13} />
                  <span className="xl2-goiy__name">{g.may_ten ?? `Máy #${g.may_id}`}</span>
                  {g.tre_han && <span className="xl2-goiy__flag xl2-goiy__flag--tre">trễ hạn</span>}
                  {g.cung_gom && <span className="xl2-goiy__flag">cùng bộ</span>}
                  <span className="xl2-goiy__sub">{g.finish ? `xong ${ngayGio(g.finish)}` : thoiLuong(g.chiem_may_phut)}</span>
                  {/* Điểm để LIẾC, không để tính: con số đứng một mình thì vô nghĩa, nên ngay dưới
                      nó là bảng trục nói điểm ấy tới từ đâu. */}
                  <span className={`xl2-goiy__diem xl2-goiy__diem--${bacDiem(g.diem)}`}>{g.diem}</span>
                </span>
                {/* Câu vì-sao do CHÍNH thuật toán tự-xếp sinh ra — bấm máy này thì lát nữa tự-xếp cũng
                    chọn đúng nó, không có chuyện gợi một đằng xếp một nẻo. */}
                <span className="xl2-goiy__why">{g.ly_do}</span>
                {(g.truc ?? []).length > 0 && (
                  <span className="xl2-truc">
                    {g.truc.map((t) => (
                      <span key={t.ma} className="xl2-truc__i" title={t.cau}>
                        <span className="xl2-truc__ten">{t.ten}</span>
                        <span className="xl2-truc__bar">
                          <i style={{ width: `${Math.round(Math.max(0, Math.min(1, t.ty_le)) * 100)}%` }} />
                        </span>
                      </span>
                    ))}
                  </span>
                )}
                <span className="xl2-goiy__meta">
                  <DaiThoiLuong tb={g.chiem_may_phut} min={g.chiem_may_phut_min} max={g.chiem_may_phut_max} />
                  <NhanNgayTags nn={g.nhan_ngay} soCanhBao={(g.canh_bao ?? []).length} />
                </span>
              </button>
            ))}
          </div>
          {goiY.vi_sao_trong && (
            <div style={{ marginTop: "var(--sp-2)" }}>
              <EmptyState icon="search" title="Không máy nào nhận được bước này" sub={goiY.vi_sao_trong} />
            </div>
          )}
          {/* Máy VẮNG MẶT phải giải thích được. Gập lại vì đây là việc đi sửa Danh mục chứ không phải
              việc đang làm — nhưng bày sẵn số máy để người ta biết có cái đáng mở ra xem. */}
          {(goiY.bi_loai ?? []).length > 0 && (
            <details className="xl2-loai">
              <summary>{goiY.bi_loai.length} máy không vào được danh sách — vì sao?</summary>
              <ul>{goiY.bi_loai.map((c, i) => <li key={i}>{c}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      <div className="xl2-psec">
        <div className="xl2-psec__h">
          <Icon name="alert" size={13} /> Vấn đề của cách đặt đang gõ
          {xtBusy && xt != null && <span className="xl2-psec__hint">đang soi lại…</span>}
        </div>
        {/* Ba trạng thái KHÁC NHAU: chưa soi xong · soi hỏng · soi xong và sạch. Gộp cả ba thành
            "sạch" là báo an toàn cho thứ chưa hề kiểm được. Trạng thái thứ tư (có kết quả CŨ,
            đang soi lại theo ô vừa gõ) giữ kết quả trên màn kèm nhãn — xoá trắng mỗi ký tự thì
            panel nhấp nháy, mà im lặng thì người đọc tưởng số cũ là số mới. */}
        {xtErr ? <p className="xl2-note">Không soi được — chọn lại dòng để thử lại.</p>
          : xt == null ? <p className="xl2-note">Đang soi…</p>
            : <div className={xtBusy ? "xl2-soi-lai" : undefined}>
                <IssueList issues={xt.van_de} empty="Không có vấn đề — cách đặt hiện tại sạch." onMoNguon={onMoNguon} />
              </div>}
      </div>

      {canUpdate && !dong.is_locked && (
        <div className="xl2-psec xl2-psec--danger">
          <div className="xl2-psec__h"><Icon name="trash" size={13} /> Xoá nháp lệnh</div>
          <p className="xl2-note">Gỡ {nhan.ma} khỏi kế hoạch. Lệnh gốc vẫn còn ở hàng chờ.</p>
          <Button variant="ghost" block className="xl2-btn-danger" onClick={onXoaNhap}>
            <Icon name="trash" size={14} /> Xoá nháp khỏi kế hoạch
          </Button>
        </div>
      )}
    </>
  );
}

// ============================ skeleton lúc tải =============================
function GanttSkeleton() {
  const rows: [number, number][] = [
    [8, 42], [26, 30], [4, 54], [36, 28], [12, 46], [30, 34], [6, 50], [20, 38], [14, 44],
  ];
  return (
    <div className="xl2-skel" role="status" aria-label="Đang tải bàn làm việc">
      {rows.map(([off, w], i) => (
        <div className="xl2-skel__row" key={i}>
          <div className="xl2-skel__lbl" />
          <div className="xl2-skel__bar" style={{ marginLeft: `${off}%`, width: `${w}%` }} />
        </div>
      ))}
    </div>
  );
}

function QueueSkeleton() {
  return (
    <div className="xl2-skel-q" role="status" aria-label="Đang tải hàng chờ">
      {[0, 1, 2, 3].map((i) => <div className="xl2-skel__q" key={i} />)}
    </div>
  );
}

// ============================ danh sách vấn đề (3 mức) =====================
// `onMoNguon` (item 13) tuỳ chọn: có thì mỗi vấn đề CÓ MÀN SỬA RIÊNG (vật tư/bước/tiền-nhiệm) hiện thêm
// nút nhảy thẳng sang module nguồn để sửa gốc; vấn đề xử lý-tại-chỗ (máy/tổ/ca/hạn) không có nút.
function IssueList({ issues, empty, onMoNguon }: {
  issues: Xl2Issue[]; empty: string; onMoNguon?: (i: Xl2Issue) => void;
}) {
  if (issues.length === 0) return <p className="xl2-note">{empty}</p>;
  const iconOf = (m: Xl2Muc): IconName => XL2_MUC_META[m].icon;
  return (
    <div className="xl2-issues">
      {issues.map((v, i) => {
        const nguonMod = onMoNguon ? XL2_NGUON_MODULE[v.nguon] : undefined;
        return (
          <div key={`${v.ma}-${i}`} className={`xl2-issue xl2-issue--${mucBarCls(v.muc)}`}>
            <Icon name={iconOf(v.muc)} size={14} className="xl2-issue__ic" />
            <div className="xl2-issue__body">
              <div className="xl2-issue__mota">
                {v.doi_tuong && <span className="xl2-issue__doituong">{v.doi_tuong}</span>}
                {v.mo_ta}
              </div>
              {v.goi_y && <div className="xl2-issue__goiy">→ {v.goi_y}</div>}
              <div className="xl2-issue__foot">
                {v.ma && <span className="xl2-issue__ma">{v.ma}</span>}
                {nguonMod && (
                  <button type="button" className="xl2-issue__open" onClick={() => onMoNguon?.(v)}>
                    <Icon name="link" size={11} /> {nguonMod.nhan}
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
