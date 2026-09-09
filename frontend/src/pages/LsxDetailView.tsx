// Chi tiết 1 LỆNH SẢN XUẤT — nơi kế hoạch hoàn thiện lệnh trước khi lập kế hoạch.
// 5 tab: Thông tin chung · Quy cách · Công đoạn (routing) · Vật tư · Nhật ký.
// Cột phải: checklist "còn thiếu gì" + nút "Sẵn sàng lập kế hoạch" (CTA duy nhất của màn).
//
// Trạng thái `nhap ↔ cho_bo_sung` do SERVER lật sau mỗi lần lưu — client luôn lấy lại từ response,
// không tự đoán. `san_sang` là hành động của NGƯỜI (server trả 409 nếu còn thiếu).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  LSX_THIEU_LABELS,
  nhanMa,
  api,
  type DanhMucDoiBuoc,
  type DanhMucDoiVatTu,
  type LsxActivity,
  type LsxBoDauViec,
  type LsxCongDoanBody,
  type LsxDetail,
  type LsxQuyCachBody,
  type LsxTongQuanOut,
  type LsxUpdateBody,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { MucInHang } from "../components/MucIn";
import { Timeline } from "../components/Timeline";
import { ImpositionDiagram } from "./ImpositionDiagram";
import { LsxRoutingTable, type RefRow } from "./LsxRoutingTable";
import { LsxVatTuPanel } from "./LsxVatTuPanel";
import { donViChuoi } from "./lsxBuoc";
import { bangKeVatTu } from "./lsxVatTu";
import { useNapTenDonVi } from "./tenDonVi";
import {
  BangLoi,
  ChipGap,
  DenTienDo,
  TrangThaiPill,
  classHan,
  ngay,
  ngayGio,
  nhanCachIn,
  num,
} from "./keHoachSxShared";

// Tab "Số lượng & bù hao" ĐÃ BỎ: mọi số ở đó nay là dẫn xuất của chuỗi ngược (số tờ in, tờ
// nguyên, bù hao) và đã hiện ở thanh bên. Ô duy nhất còn gõ được là SL ra của bước CUỐI, nằm
// trong drawer bước; con/tờ chuyển sang tab Quy cách.
type TabKey = "chung" | "quycach" | "routing" | "vattu" | "nhatky";

// "Vật tư" đứng ngay SAU Công đoạn: bốn tab cũ đi theo mạch lệnh-gì → làm-ra-sao → qua-những-bước
// -nào → ai-đã-đụng-vào. Câu "ăn những gì" thuộc về chỗ sau chuỗi bước, trước sổ nhật ký.
const TABS: { key: TabKey; label: string }[] = [
  { key: "chung", label: "Thông tin chung" },
  { key: "quycach", label: "Quy cách" },
  { key: "routing", label: "Công đoạn" },
  { key: "vattu", label: "Vật tư" },
  { key: "nhatky", label: "Nhật ký" },
];

const ACTION_LABEL: Record<string, string> = {
  create_lsx: "Tạo lệnh",
  update_lsx: "Sửa thông tin",
  update_lsx_routing: "Sửa công đoạn",
  update_lsx_danh_muc: "Cập nhật theo danh mục",
  lsx_trang_thai: "Đổi trạng thái",
  delete_lsx: "Xoá lệnh",
};

/** Một dòng gọn cho băng vàng: bước này lệch những gì. Bảng cũ → mới đầy đủ nằm trong dialog —
 *  băng chỉ cần đủ để người lập kế hoạch quyết CÓ MỞ RA XEM hay không. */
function tomTatBuoc(b: DanhMucDoiBuoc): string {
  const y: string[] = [];
  if (b.khoan_mo_coi) y.push(`đầu việc “${b.khoan_mo_coi}” không còn thuộc công đoạn/tổ`);
  if (b.khoan_chua_chon) y.push(`chưa chọn đầu việc, danh mục nay có “${b.khoan_chua_chon}”`);
  if (b.khoan.length) y.push(b.khoan.map((k) => k.nhan.toLowerCase()).join(", "));
  if (b.vat_tu_them.length) y.push(`thêm ${b.vat_tu_them.length} vật tư`);
  if (b.vat_tu_lech.length) y.push(`${b.vat_tu_lech.length} vật tư lệch số`);
  if (b.vat_tu_bo.length) y.push(`${b.vat_tu_bo.length} vật tư danh mục không còn bung`);
  if (b.may_canh_bao) y.push(b.may_canh_bao);
  return y.join(" · ");
}

interface FormState {
  ten: string;
  han_hoan_thanh_sx: string;
  is_rush: boolean;
  may_id: string;
  ghi_chu: string;
  so_luong_dat: string;
  so_to_ke_hoach: string;
  so_to_nguyen: string;
  so_con: string;
  /** THÔNG SỐ của ảnh chụp — kế hoạch sửa được tại chỗ. Số dẫn xuất (kẽm · lượt · mảnh xả · tờ)
   *  KHÔNG nằm ở đây: server tính lại từ bộ này, màn chỉ hiện. */
  qc: LsxQuyCachBody;
}

/** Đọc cụm THÔNG SỐ ra khỏi ảnh chụp. Chỉ lấy đúng những khoá server cho sửa — bê cả
 *  `quy_cach_json` vào form là gửi ngược cả số dẫn xuất lên rồi tưởng mình sửa được chúng. */
function toQc(d: LsxDetail): LsxQuyCachBody {
  const q = (d.quy_cach_json ?? {}) as Record<string, unknown>;
  const n = (k: string): number => Number(q[k] ?? 0) || 0;
  const ml = (k: string): string[] => (Array.isArray(q[k]) ? (q[k] as string[]).map(String) : []);
  return {
    giay_id: q.giay_id == null ? null : Number(q.giay_id),
    nguon_giay: String(q.nguon_giay ?? "cong_ty"),
    kho_nguyen_dai: n("kho_nguyen_dai"), kho_nguyen_rong: n("kho_nguyen_rong"),
    kho_in_dai: n("kho_in_dai"), kho_in_rong: n("kho_in_rong"),
    dai_thanh_pham: n("dai_thanh_pham"), rong_thanh_pham: n("rong_thanh_pham"),
    quy_cach_in: String(q.quy_cach_in ?? "mot_mat"),
    muc_a: ml("muc_a"), muc_b: ml("muc_b"),
    so_trang: Math.max(n("so_trang"), 1), trang_moi_tay: Math.max(n("trang_moi_tay"), 1),
    bleed_mm: n("bleed_mm"), khe_cat_mm: n("khe_cat_mm"),
    con_auto: q.con_auto !== false,
  };
}

// `soBaiIn` đã bỏ cùng tab "Số lượng & bù hao": số bài in nay chỉ còn được dùng trong chuỗi
// ngược ở server (`_ap_chuoi_nguoc`), frontend không tự tính số tờ nữa.

function toForm(d: LsxDetail): FormState {
  return {
    ten: d.ten,
    han_hoan_thanh_sx: d.han_hoan_thanh_sx ?? "",
    is_rush: d.is_rush,
    may_id: d.may_id != null ? String(d.may_id) : "",
    ghi_chu: d.ghi_chu ?? "",
    so_luong_dat: String(d.so_luong_dat),
    so_to_ke_hoach: String(d.so_to_ke_hoach),
    so_to_nguyen: String(d.so_to_nguyen),
    so_con: String(d.so_con),
    qc: toQc(d),
  };
}

function getInitials(name?: string | null): string {
  if (!name) return "—";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function demNgayConLai(hanGiaoStr?: string | null): string {
  if (!hanGiaoStr) return "";
  const dg = new Date(hanGiaoStr);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  dg.setHours(0, 0, 0, 0);
  const diff = Math.round((dg.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (diff < 0) return `Quá hạn ${Math.abs(diff)} ngày`;
  if (diff === 0) return `Hôm nay giao`;
  return `Còn ${diff} ngày`;
}

function tinhNgayDem(hanSxStr: string | null | undefined, hanGiaoStr: string | null | undefined): {
  status: "safe" | "warning" | "danger" | "none";
  text: string;
} {
  if (!hanSxStr || !hanGiaoStr) return { status: "none", text: "" };
  const dSx = new Date(hanSxStr);
  const dGiao = new Date(hanGiaoStr);
  if (isNaN(dSx.getTime()) || isNaN(dGiao.getTime())) return { status: "none", text: "" };
  dSx.setHours(0, 0, 0, 0);
  dGiao.setHours(0, 0, 0, 0);
  const diffDays = Math.round((dGiao.getTime() - dSx.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays >= 2) {
    return { status: "safe", text: `Đệm ${diffDays} ngày an toàn trước hạn giao` };
  } else if (diffDays === 1) {
    return { status: "warning", text: `Đệm 1 ngày — Cận kề hạn giao khách` };
  } else if (diffDays === 0) {
    return { status: "warning", text: `Trùng hạn giao — Không có ngày đệm` };
  } else {
    return { status: "danger", text: `Trễ hơn hạn giao khách ${Math.abs(diffDays)} ngày!` };
  }
}

export function LsxDetailView({
  lsxId,
  onBack,
  onChanged,
  navigate,
  eventTick,
}: {
  lsxId: number;
  onBack: () => void;
  onChanged: () => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  /** Tick SSE của `AppShell` — nhảy mỗi sự kiện real-time. Màn DANH SÁCH tự refetch theo nó; màn
   *  này thì KHÔNG được tự refetch (xem nút "Làm mới"), chỉ dùng để biết có gì mới. */
  eventTick?: number;
}) {
  const { token } = useAuth();
  const canUpdate = useCan()("san_xuat", "update");
  // Nhãn đơn vị đọc từ DANH MỤC (không bảng nhãn cứng) — cùng nguồn với bảng routing và Tính giá.
  // Gọi (không giữ version): hook tự `setState` khi danh mục về ⇒ màn vẽ lại ⇒ bảng kê vật tư
  // tính lại nhãn đơn vị. Nó là hàm thuần gọi thẳng trong render, không cache.
  useNapTenDonVi();
  const [d, setD] = useState<LsxDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("chung");
  const [form, setForm] = useState<FormState | null>(null);
  const [copiedOrder, setCopiedOrder] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingRouting, setSavingRouting] = useState(false);
  const [routingDirty, setRoutingDirty] = useState(false);
  /** Bước bị GỠ đầu việc mồ côi ở lần lưu routing vừa rồi — lưu VẪN thành công, đây chỉ là lưu ý
   *  để mở đúng bước chọn lại đầu việc. Xoá khi lưu lại hoặc khi người dùng đóng. */
  const [boDauViec, setBoDauViec] = useState<LsxBoDauViec[]>([]);
  const [readyErr, setReadyErr] = useState<string | null>(null);
  const [askDelete, setAskDelete] = useState(false);
  /** Bảng cũ → mới của nút "Cập nhật theo danh mục". KHÔNG ghi thẳng khi bấm: số khoán và định
   *  mức là tiền công của thợ, đổi lén một phát cả lệnh thì người lập kế hoạch không có cách nào
   *  biết cái gì vừa đổi. Mở bảng ra, đọc, rồi mới đồng ý. */
  const [xemDmDoi, setXemDmDoi] = useState(false);
  const [dongBo, setDongBo] = useState(false);
  const [dongBoErr, setDongBoErr] = useState<string | null>(null);
  const [acts, setActs] = useState<LsxActivity[] | null>(null);
  /* GỠ 07/09/2026 cùng ô Giấy: hai ô `xemTruoc` / `xemTruocLoi`. Chúng chỉ có việc khi quy cách ở
     lệnh còn sửa được — nay cụm thông số là ảnh chụp CHỈ XEM của phiếu tính giá nên không còn gì
     để tính lại trước lúc bấm Lưu, và `api.lsx.xemTruocQuyCach` không còn ai gọi. */
  /** Ba đèn "vướng gì" — CÙNG nguồn với bảng lệnh, ở đây hiện đủ chữ. Chưa về = `null` ⇒ chưa
   *  vẽ gì, đừng hiện "không vướng gì" khi thật ra chưa hỏi xong. */
  const [den, setDen] = useState<LsxTongQuanOut["items"][number] | null>(null);

  // Danh mục cho dropdown — nạp MỘT LẦN ở đây rồi truyền xuống bảng routing.
  const [congDoanRefs, setCongDoanRefs] = useState<RefRow[] | null>(null);
  const [toRefs, setToRefs] = useState<RefRow[] | null>(null);
  const [mayRefs, setMayRefs] = useState<RefRow[] | null>(null);
  // Dao chọn được của LỆNH này — server đã lọc theo khách của lệnh. Nạp MỘT lần cho cả routing;
  // lọc tiếp theo loại của từng bước làm trong drawer (danh sách tới đó chỉ còn vài dòng).
  const [khuonRefs, setKhuonRefs] = useState<
    import("../api/client").KhuonChonDuoc[] | null
  >(null);
  const [vatTuRefs, setVatTuRefs] = useState<RefRow[] | null>(null);
  // DANH MỤC GIẤY — nguồn NVL chính của bước (08/09/2026). Nạp riêng chứ không gộp vào `vatTuRefs`:
  // hai danh mục đánh số ĐỘC LẬP, gộp phẳng là Giấy #7 đè Vật tư #7 ngay ở dropdown.
  const [giayRefs, setGiayRefs] = useState<RefRow[] | null>(null);
  const [phuThuocRefs, setPhuThuocRefs] = useState<import("../api/client").LsxPhuThuocOption[]>([]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    api.lsx
      .get(token, lsxId)
      .then((r) => {
        setD(r);
        setForm(toForm(r));
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [token, lsxId]);

  useEffect(() => load(), [load]);

  const napKhuon = useCallback(() => {
    if (!token) return;
    api.lsx.khuonChonDuoc(token, lsxId).then(setKhuonRefs).catch(() => setKhuonRefs(null));
  }, [token, lsxId]);
  useEffect(() => napKhuon(), [napKhuon]);

  // Ba đèn "vướng gì" — GỌI RỜI khỏi `GET /api/lsx/{id}` vì endpoint tổng quan chạy engine cân đối
  // vật tư + bộ dò xếp lịch; màn chi tiết phải mở ngay, đèn về sau. Nạp lại theo `d` để sau mỗi
  // lần lưu/làm mới đèn nói chuyện mới.
  useEffect(() => {
    if (!token || !d) return;
    let huy = false;
    api.lsx
      .tongQuan(token, [lsxId])
      .then((r) => {
        if (!huy) setDen(r.items[0] ?? null);
      })
      .catch(() => {
        if (!huy) setDen(null);   // đèn hỏng thì màn vẫn dùng được
      });
    return () => {
      huy = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, lsxId, d]);

  // --- "Có thay đổi mới" ---------------------------------------------------------------------
  // Mốc tick tại lần nạp gần nhất. Tick nhảy quá mốc ⇒ có ai đó vừa sửa lệnh này (hoặc bài ghép /
  // xếp lịch liên quan) SAU khi ta cầm dữ liệu.
  //
  // Nhận cả sự kiện do CHÍNH TA gây ra (lưu xong là server broadcast). Ta đồng bộ mốc ở mỗi lần
  // `load()` xong nên phần lớn tự tắt; sự kiện về trễ hơn `load()` vài chục ms thì nút sáng OAN
  // một lúc. Chấp nhận: bấm vào chỉ tốn một lần nạp lại, còn BỎ SÓT thay đổi thật thì người kế
  // hoạch sửa trên dữ liệu cũ rồi ghi đè việc của người khác.
  const tickDaXem = useRef(eventTick ?? 0);
  const coDuLieuMoi = (eventTick ?? 0) > tickDaXem.current;
  const lamMoi = useCallback(() => {
    tickDaXem.current = eventTick ?? 0;
    load();
    napKhuon();
  }, [eventTick, load, napKhuon]);
  useEffect(() => {
    // Mỗi lần dữ liệu về (kể cả lần đầu và sau khi tự lưu) thì coi như đã xem tới tick hiện tại.
    if (d) tickDaXem.current = eventTick ?? 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d]);

  /** Lấy số mới nhất của danh mục cho CẢ lệnh. Server không xoá dòng vật tư nào và không đụng số
   *  nhân công đã sắp — bảng cũ → mới người dùng vừa đọc là ĐÚNG những gì sẽ ghi. */
  const capNhatTheoDanhMuc = useCallback(async () => {
    if (!token) return;
    setDongBo(true);
    setDongBoErr(null);
    try {
      const r = await api.lsx.dongBoDanhMuc(token, lsxId);
      setD(r);
      setForm(toForm(r));
      setXemDmDoi(false);
      // Bảng lệnh có đèn "Danh mục" cùng nguồn ⇒ báo cho màn cha nạp lại, không thì chấm vàng
      // còn nằm đó tới lần lọc sau.
      onChanged();
    } catch (e: unknown) {
      setDongBoErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDongBo(false);
    }
  }, [token, lsxId, onChanged]);

  /** Tạo dao mới cho một bước → dòng mới trong danh mục Khuôn ở tình trạng "đang đặt làm".
   *
   *  Khách + loại lấy từ chính lệnh và bước, không hỏi lại: người cấu hình lệnh không nên phải gõ
   *  lại thứ hệ thống đã biết. Nạp lại danh sách ngay để dao vừa tạo có mặt cho các bước khác. */
  const taoKhuon = useCallback(
    async (input: { ten: string; loai: string | null; ngay_ve: string }) => {
      if (!token) throw new Error("Chưa đăng nhập.");
      const row = await api.lsx.taoKhuonChoLenh(token, lsxId, {
        ten: input.ten, loai: input.loai, ngay_ve_du_kien: input.ngay_ve,
      });
      // Nhét NGAY dòng vừa tạo vào danh sách, ĐỪNG chỉ đợi `napKhuon()`: nó không await được (chỗ
      // gọi cần `id` trả về ngay để gán vào bước), nên có một khe mà bước đã trỏ vào dao mới trong
      // khi danh sách chưa có nó — chip in ra "#7" trống trơn đúng như lỗi vừa gặp.
      setKhuonRefs((prev) => [...(prev ?? []), row]);
      napKhuon();
      return row.id;
    },
    [token, lsxId, napKhuon],
  );

  useEffect(() => {
    if (!token) return;
    // Không có quyền đọc danh mục → để null, ô hiện read-only thay vì select rỗng (select rỗng
    // + lưu = xoá trắng dữ liệu).
    // `may_lam_duoc` = bảng "Máy chạy được công đoạn này" ở danh mục Công đoạn. Giữ lại id để
    // drawer bước lọc dropdown MÁY đúng như bài ghép và engine xếp lịch đang chặn (`RefRow`).
    api.congDoan.list(token).then((r) => setCongDoanRefs(r.items.map((c) => ({
      // `ma` chỉ để GÕ TÌM trong drawer bước (không hiện ra) — người khai quen gõ "CD-0003".
      id: c.id, ten: c.ten, ma: c.ma, nhomMayChoPhep: c.nhom_may_cho_phep,
      mayChoPhep: (c.may_lam_duoc ?? []).map((m) => m.may_id),
    })))).catch(() => setCongDoanRefs(null));
    crud("/api/cong-doan/phong-ban").list(token).then((r) => setToRefs(r.items.map((t) => ({ id: t.id, ten: t.ten })))).catch(() => setToRefs(null));
    // Giữ luôn TỐC ĐỘ + CHUẨN BỊ của máy: form phải tính lại thời lượng ngay khi đổi máy, chứ
    // không đợi lưu rồi server mới trả số về (xem `RefRow`).
    crud("/api/may-thiet-bi").list(token).then((r) => setMayRefs(r.items.map((m) => {
      const khoan = (m.fields_theo_loai as { chuan_bi_khoan?: { ten?: string; phut?: number }[] } | null)
        ?.chuan_bi_khoan;
      return {
        id: m.id, ten: m.ten, nhom: m.loai_may ? String(m.loai_may) : null,
        tocDo: m.toc_do == null ? null : Number(m.toc_do),
        tocDoMin: m.toc_do_min == null ? null : Number(m.toc_do_min),
        tocDoMax: m.toc_do_max == null ? null : Number(m.toc_do_max),
        donViTocDo: m.don_vi_toc_do ? String(m.don_vi_toc_do) : null,
        chuanBiPhut: m.makeready_time_default == null ? null : Number(m.makeready_time_default),
        chuanBiKhoan: Array.isArray(khoan) ? khoan : [],
        // Ô "Số người vận hành tiêu chuẩn" của máy ĐÃ GỠ (06/09/2026, mg `0270`): kíp của mọi loại
        // bước nay đến từ định mức đầu việc của công đoạn, nên chọn máy không đụng số người nữa.
      };
    }))).catch(() => setMayRefs(null));
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true }).then((r) =>
      setVatTuRefs(r.items.map((v) => ({ id: v.id, ten: v.ten, ma: String(v.ma), donVi: String(v.don_vi_gia ?? "") })))
    ).catch(() => setVatTuRefs(null));
    crud("/api/vat-lieu-kho/giay").list(token, { active: true }).then((r) =>
      setGiayRefs(r.items.map((v) => ({ id: v.id, ten: v.ten, ma: String(v.ma), donVi: String(v.don_vi_gia ?? "") })))
    ).catch(() => setGiayRefs(null));
    api.lsx.phuThuocOptions(token, lsxId).then(setPhuThuocRefs).catch(() => setPhuThuocRefs([]));
  }, [token, lsxId]);

  // Nhật ký nạp LƯỜI — chỉ khi mở tab.
  useEffect(() => {
    if (tab !== "nhatky" || !token || acts !== null) return;
    api.lsx.activity(token, lsxId).then((r) => setActs(r.items)).catch(() => setActs([]));
  }, [tab, token, lsxId, acts]);

  const dirty = useMemo(() => {
    if (!d || !form) return false;
    return JSON.stringify(form) !== JSON.stringify(toForm(d));
  }, [d, form]);

  function set<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev));
  }
  // Lệnh đang GIỮ CHỖ vật tư. Server (`_chan_dang_giu_cho`) chặn ba đường: đổi `so_luong_dat`,
  // gửi `quy_cach`, và xoá lệnh — cùng luật với routing. Tách ra thành cờ riêng để màn NÓI TRƯỚC
  // thay vì để người ta gõ xong cả bảng thông số rồi mới ăn 409 lúc bấm Lưu.
  const giuCho = !!d?.giu_cho_bat;
  // Danh mục đã đổi sau lúc lệnh chụp ảnh. `null` = còn khớp hết ⇒ KHÔNG băng, không chỗ trống.
  const dmDoi = d?.danh_muc_doi ?? null;
  // QUY CÁCH Ở LỆNH = CHỈ XEM, không chừa ô nào (07/09/2026). Cụm này là thứ đã chốt với khách ở
  // phiếu tính giá — giấy, khổ, cách in, số trang, bleed, khe cắt, bình bài đều là số đã tính ra
  // giá và đã báo. Phiếu tính ra sao thì lệnh chạy y như vậy; gõ lại ở lệnh là lệnh chạy một đằng,
  // khách mua một nẻo, mà không ai đối chiếu. Muốn đổi thật thì sửa ở phiếu rồi TẠO LẠI lệnh.
  //
  // Ô Giấy từng là ngoại lệ "chữa cháy khi giấy hết hàng" (05/09/2026) — GỠ 07/09/2026. Nó là ô
  // cuối cùng sửa được `form.qc`, nên gỡ xong kéo theo cả đường xem-trước-trước-khi-lưu: `luu()`
  // không bao giờ gửi `quy_cach` nữa, khối "Máy tự tính" chỉ còn hiện số đã lưu.

  async function luu() {
    if (!token || !form || !d) return;
    setSaving(true);
    setErr(null);
    const body: LsxUpdateBody = {
      ten: form.ten,
      han_hoan_thanh_sx: form.han_hoan_thanh_sx || null,
      is_rush: form.is_rush,
      ghi_chu: form.ghi_chu || null,
      so_luong_dat: Number(form.so_luong_dat || 0),
      // `so_to_ke_hoach` / `so_to_nguyen` KHÔNG gửi nữa — server đọc ra từ chuỗi ngược tại hai
      // ranh giới đơn vị (tờ nguyên → tờ in). Gửi lên chỉ tổ có nguồn sự thật thứ hai.
      so_con: Number(form.so_con || 1),
    };
    // KHÔNG gửi `quy_cach` (07/09/2026): màn này không còn ô nào sửa thông số. Gửi kèm chỉ mở
    // đường cho một cú Lưu vô tình kích bình bài lại + chạy lại chuỗi ngược, đè số người khác chỉnh.
    // KHÔNG gửi `may_id`: ô đó đã bỏ khỏi màn (11/08/2026). Không gửi = server giữ nguyên giá trị
    // nó đang có (máy dự kiến suy từ phiếu tính giá lúc tạo lệnh). Khuôn thì không còn cột nào để
    // gửi — đã xoá hẳn 16/08/2026 (mg `0203`).
    try {
      const r = await api.lsx.update(token, d.id, body);
      setD(r);
      setForm(toForm(r));
      setActs(null);
      onChanged();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  /** Sửa cấp LỆNH từ drawer bước cuối: SL thành phẩm cần giao + hao thêm.
   *
   *  Hai số này là ĐẦU VÀO DUY NHẤT của chuỗi ngược — server nhận xong tính lại vào/ra + hao của
   *  mọi bước rồi trả lệnh mới, nên phải nạp lại `d` chứ không patch cục bộ. */
  const patchLsx = useCallback(
    async (p: { so_luong_dat?: number }) => {
      if (!token || !d) return;
      try {
        const r = await api.lsx.update(token, d.id, p as LsxUpdateBody);
        setD(r);
        setForm(toForm(r));
        onChanged();
      } catch (e: unknown) {
        setErr(e instanceof ApiError ? e.message : String(e));
      }
    },
    [token, d, onChanged],
  );

  /** Bộ mặc định của công đoạn mới khi kế hoạch đổi 1 bước — luật ở backend, client chỉ áp. */
  const macDinhBuoc = useCallback(
    async (congDoanId: number) => {
      if (!token || !d) throw new Error("chưa sẵn sàng");
      return api.lsx.macDinhBuoc(token, d.id, congDoanId);
    },
    [token, d],
  );

  const dauViecOptions = useCallback(
    async (congDoanId: number, departmentId: number) => {
      if (!token || !d) throw new Error("chưa sẵn sàng");
      return api.lsx.dauViecOptions(token, d.id, congDoanId, departmentId);
    },
    [token, d],
  );

  /** Sửa gì trên drawer → hỏi server luôn: SL vào quy đổi sang đơn vị ĐÍCH của bộ số MỚI ra bao
   *  nhiêu, và tiền công bằng bao nhiêu. Tốc độ/kíp/chuẩn bị thì form tự tính từ `mayRefs`; riêng
   *  phép quy đổi và tiền công chỉ backend làm được. */
  const xemTruocBuoc = useCallback(
    async (
      stepKey: string,
      dang: { mayId?: number | null; loaiBuoc?: string | null;
              pieceRateId?: number | null; soLuotChay?: number | null },
    ) => {
      if (!token || !d) throw new Error("chưa sẵn sàng");
      return api.lsx.xemTruocBuoc(token, d.id, stepKey, dang);
    },
    [token, d],
  );

  /** Đổi/chèn công đoạn → hỏi server số VÀO–RA + đơn vị của CẢ CHUỖI (chỉ backend chạy được
   *  chuỗi ngược + bảng cầu quy đổi). Cùng lẽ với `xemTruocBuoc`: số nhảy ngay, khỏi bấm Lưu. */
  const xemTruocRouting = useCallback(
    async (rows: import("../api/client").LsxXemTruocRoutingRow[]) => {
      if (!token || !d) throw new Error("chưa sẵn sàng");
      const r = await api.lsx.xemTruocRouting(token, d.id, rows);
      return r.cong_doans;
    },
    [token, d],
  );

  async function luuRouting(body: LsxCongDoanBody[], lyDo?: string) {
    if (!token || !d) return;
    setSavingRouting(true);
    setErr(null);
    try {
      const r = await api.lsx.saveRouting(token, d.id, body, lyDo);
      setD(r);
      setForm(toForm(r));
      setActs(null);
      setRoutingDirty(false);
      // Lưu THÀNH CÔNG nhưng server có thể đã gỡ đầu việc mồ côi (danh mục đổi dưới chân lệnh) —
      // bày lưu ý đích danh bước để mở lại chọn đầu việc, thay cho việc chặn cứng nút Lưu như trước.
      setBoDauViec(r.bo_dau_viec ?? []);
      api.lsx.phuThuocOptions(token, d.id).then(setPhuThuocRefs).catch(() => {});
      onChanged();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSavingRouting(false);
    }
  }

  async function doiTrangThai(tt: "nhap" | "san_sang") {
    if (!token || !d) return;
    setReadyErr(null);
    try {
      const r = await api.lsx.setTrangThai(token, d.id, tt);
      setD(r);
      setForm(toForm(r));
      setActs(null);
      onChanged();
    } catch (e: unknown) {
      setReadyErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function xoa() {
    if (!token || !d) return;
    try {
      await api.lsx.remove(token, d.id);
      onChanged();
      onBack();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setAskDelete(false);
    }
  }

  // HOOK PHẢI NẰM TRƯỚC MỌI `return` SỚM. Khối này từng đứng dưới hai nhánh return bên dưới:
  // render đầu (đang tải) React đếm 45 hook, dữ liệu về thành 46 → "Rendered more hooks than
  // during the previous render" và cả màn trắng ngay khi bấm vào một lệnh. `d`/`form` lúc này
  // còn có thể là null nên đọc bằng `?.` — `tinhNgayDem` đã nhận null/undefined và trả "none".
  const demHan = useMemo(
    () => tinhNgayDem(form?.han_hoan_thanh_sx, d?.han_giao_khach),
    [form?.han_hoan_thanh_sx, d?.han_giao_khach],
  );

  if (loading) {
    // Skeleton GIỮ ĐÚNG layout (head + 2 cột) để nội dung thật không làm nhảy trang.
    return (
      <div className="khsx-detail" role="status" aria-live="polite">
        <span className="sr-only">Đang tải lệnh sản xuất…</span>
        <header className="khsx-detail__head">
          <span className="khsx-skel__bar khsx-skel__bar--title" />
          <span className="khsx-skel__bar khsx-skel__bar--sub" />
        </header>
        <div className="khsx-detail__grid">
          <div className="khsx-detail__main">
            <span className="khsx-skel__bar" />
            <span className="khsx-skel__bar" />
            <span className="khsx-skel__bar" />
          </div>
          <aside className="khsx-aside">
            <span className="khsx-skel__bar khsx-skel__bar--card" />
          </aside>
        </div>
      </div>
    );
  }
  if (!d || !form) {
    return (
      <div className="khsx-detail__gone">
        <BangLoi text={err ?? "Lệnh không còn tồn tại (có thể đã bị xoá)."} />
        <Button variant="secondary" onClick={onBack}>
          ‹ Về danh sách lệnh
        </Button>
      </div>
    );
  }

  // Đơn đã hủy → khóa hẳn routing: ẩn tab (không chỉ khóa sửa), khớp server đã chặn PUT
  // /routing khi order.status = cancelled (lsx_service.replace_routing).
  const orderCancelled = d.order_status === "cancelled";
  const visibleTabs = orderCancelled ? TABS.filter((t) => t.key !== "routing") : TABS;

  const qc = (d.quy_cach_json ?? {}) as Record<string, unknown>;
  const n = (k: string): number => Number(qc[k] ?? 0);
  const s = (k: string): string => (qc[k] == null || qc[k] === "" ? "—" : String(qc[k]));
  const coBinhBai = n("kho_in_dai") > 0 && n("kho_in_rong") > 0 && n("dai_thanh_pham") > 0 && n("rong_thanh_pham") > 0;
  // Nhãn cách in nay nằm trong chính ô <select> của khối thông số — không dựng thêm biến nhãn
  // thứ hai. Khổ tờ in 0 × 0 (in thẳng khổ giấy nguyên) được nói bằng dòng hint dưới hai ô nhập.
  const vatTus = (Array.isArray(qc.vat_tus) ? qc.vat_tus : []) as { ten?: string; so_luong?: number }[];
  // ĐƠN VỊ CỦA CHÍNH LỆNH NÀY (12/08/2026) — trước đó thanh KPI và khối "Máy tự tính" gọi cứng
  // "Tờ in" · "Tờ nguyên" · "con/tờ", trong khi xưởng khai đơn vị riêng trong danh mục: lệnh chạy
  // `to_chay` ("TỜ CHẠY MÁY") mà màn vẫn ghi "TỜ IN". Luật đọc-từ-routing nằm ở `donViChuoi`
  // (lsxBuoc.ts) — dùng chung với bảng routing, đừng chép lại ở đây.
  const dvChuoi = donViChuoi(d, d.don_vi_tinh);
  const { to: dvTo, tp: dvTp, tay: dvTay, toNguyen: dvToNguyen } = dvChuoi;
  // Bảng kê vật tư — tính MỘT lần cho cả ô tóm tắt trên đầu màn lẫn tab "Vật tư". Hàm thuần chạy
  // trên ≤ vài chục bước nên gọi thẳng trong render, không cần memo.
  const keVatTu = bangKeVatTu({ congDoans: d.cong_doans });

  // SÁCH GẤP TAY vs CẮT RỜI — cùng tiêu chí backend dùng để chọn nhánh hệ số (`la_gap_tay`).
  // Sách: tờ in gấp NGUYÊN VẸN thành một tay, một cuốn cần `soTay` TỜ → giấy nhân lên theo số tay,
  // và `con/tờ` KHÔNG vào công thức giấy (nó chỉ để bình bài + kiểm khổ có vừa tờ).
  const trangMoiTay = Math.max(n("trang_moi_tay") || 1, 1);
  const laSach = trangMoiTay > 1;
  const soTay = laSach ? Math.max(Math.ceil(Math.max(n("so_trang"), 1) / trangMoiTay), 1) : 1;
  const giaiThichSach = laSach
    ? `Sách gấp tay — ${dvTp}/${dvTo} chỉ để bình bài và kiểm khổ, KHÔNG chi phối số giấy. `
      + `Giấy tính theo ${num(soTay)} ${dvTo} = 1 ${d.don_vi_tinh || "cuốn"}.`
    : undefined;
  // Số tờ in / tờ nguyên KHÔNG còn tính ở đây: chúng là hai mốc ĐỌC RA từ chuỗi ngược bên server
  // (`_ap_chuoi_nguoc`). Giữ bản tính thứ hai ở frontend là mở đường cho hai số lệch nhau.
  // Thanh KPI và khối "Máy tự tính" đọc THẲNG số đã lưu (`d.*`) từ 07/09/2026: không còn ô nào
  // sửa thông số ở màn này nên không còn cảnh "số đang gõ" khác "số trong DB" để phải phân biệt.

  return (
    <div className="khsx-detail">
      <header className="khsx-detail__head">
        <button type="button" className="khsx-back" onClick={onBack}>
          <Icon name="chevron" size={13} style={{ transform: "rotate(90deg)" }} /> Quay lại danh sách lệnh
        </button>

        <div className="khsx-detail__titlebox">
          <div className="khsx-detail__titlerow">
            <span className="eyebrow">SẢN XUẤT · LỆNH SẢN XUẤT</span>
            <div className="khsx-detail__mabox">
              <h1 className="khsx-detail__ma">{d.ma}</h1>
              <TrangThaiPill tt={d.trang_thai} lg />
              {d.is_rush && <ChipGap />}
            </div>
            {d.ten && <p className="khsx-detail__name">{d.ten}</p>}
          </div>

          <div className="khsx-detail__headnut">
            {/* Nút LÀM MỚI — sáng lên khi lệnh này bị người/màn khác sửa (tín hiệu SSE `lsx_changed`).
                CỐ Ý không tự nạp lại: bảng công đoạn giữ sửa CHƯA LƯU ("Sửa ở đây chưa ghi vào DB
                — bấm Lưu công đoạn"), tự nạp là im lặng xoá việc người ta đang làm dở. Máy báo có
                cái mới, người quyết lúc nào lấy. */}
            <button
              type="button"
              className={`khsx-lammoi${coDuLieuMoi ? " is-moi" : ""}`}
              onClick={lamMoi}
              title={coDuLieuMoi
                ? "Lệnh này vừa bị sửa ở nơi khác — bấm để nạp lại"
                : "Nạp lại lệnh và danh sách khuôn"}
            >
              <Icon name="refresh" size={13} />
              {coDuLieuMoi ? "Có thay đổi mới — làm mới" : "Làm mới"}
            </button>
            {/* Đang giữ chỗ thì server xoá không nổi (`_chan_dang_giu_cho`). Thay nút bằng CHIP nói
                thẳng lý do chứ không để nút mờ đi im lặng: nút disabled chỉ có tooltip, người dùng
                bấm không ăn rồi tự đoán là hết quyền. Chip hiện ở MỌI tab nên đây cũng là chỗ báo
                cái khoá cho ai đang đứng ở tab khác tab Thông số. */}
            {canUpdate && d.trang_thai !== "san_sang" && (
              giuCho ? (
                <span
                  className="khsx-khoa-chip"
                  title="Nhả chỗ ở Kế hoạch vật tư › Theo lệnh sản xuất rồi mới xoá được lệnh."
                >
                  <Icon name="lock" size={13} /> Giữ chỗ vật tư — chưa xoá được
                </span>
              ) : (
                <Button variant="ghost" className="khsx-btn--danger" onClick={() => setAskDelete(true)}>
                  <Icon name="trash" size={14} /> Xoá lệnh
                </Button>
              )
            )}
          </div>
        </div>

        <div className="khsx-detail__chips">
          {d.order_no && (
            <button
              type="button"
              className="khsx-chip-btn"
              onClick={() => navigate?.("don-hang-ban", { openOrderId: d.order_id })}
            >
              <Icon name="cart" size={13} /> Đơn {d.order_no}
            </button>
          )}
          {d.customer_name && (
            <span className="khsx-chip-tag">
              <Icon name="users" size={13} /> {d.customer_name}
            </span>
          )}
          {d.customer_po_no && (
            <span className="khsx-chip-tag">
              <Icon name="fileText" size={13} /> PO: {d.customer_po_no}
            </span>
          )}
          {d.quote_number && (
            <span className="khsx-chip-tag">
              <Icon name="calculator" size={13} /> Báo giá {d.quote_number}
              {d.quote_version_number ? ` v${d.quote_version_number}` : ""}
            </span>
          )}
          {d.ptg_ma && (
            <button
              type="button"
              className="khsx-chip-btn khsx-chip-btn--accent"
              onClick={() => navigate?.("tinh-gia", { focusPhieuId: d.ptg_id })}
            >
              <Icon name="clipboard" size={13} /> {d.ptg_ma}
            </button>
          )}
        </div>
      </header>

      {/* BĂNG "danh mục đã đổi" — đứng ngay dưới đầu trang, TRÊN cả hàng đèn: nó nói rằng những
          con số người ta sắp đọc ở dưới là số CŨ. Hiện cả khi lệnh đã lập kế hoạch (chỉ khoá nút),
          vì lúc đó biết mà không sửa được vẫn hơn không biết. */}
      {dmDoi && (
        <div className="khsx-luuy khsx-dmdoi" role="status">
          <p className="khsx-luuy__title">
            <Icon name="refresh" size={15} />
            Danh mục đã đổi sau lần lệnh này lấy số — {dmDoi.so_buoc} công đoạn đang giữ số cũ
            <span className="khsx-dmdoi__nut">
              {dmDoi.co_the_cap_nhat ? (
                <button type="button" className="khsx-dmdoi__btn" onClick={() => setXemDmDoi(true)}>
                  Cập nhật theo danh mục
                </button>
              ) : (
                /* Nút mờ chỉ có tooltip — người dùng bấm không ăn rồi tự đoán là hết quyền. Nói
                   thẳng lý do bằng chữ, cùng luật với chip "Giữ chỗ vật tư" ở đầu trang. */
                <span className="khsx-dmdoi__khoa">
                  <Icon name="lock" size={12} /> {dmDoi.ly_do_khoa || "Chưa cập nhật được"}
                </span>
              )}
            </span>
          </p>
          <ul className="khsx-luuy__list">
            {dmDoi.buocs.map((b) => (
              <li key={b.buoc_id}>
                <strong>Bước {b.thu_tu} · {b.ten}:</strong> {tomTatBuoc(b)}
              </li>
            ))}
          </ul>
          <p className="khsx-luuy__foot">
            Giữ số cũ KHÔNG chặn gì cả — lệnh vẫn xếp lịch và chạy được. Chỉ là tiền công và định
            mức đang tính theo bản danh mục lúc bung lệnh.
          </p>
        </div>
      )}

      {/* Bốn thứ có thể chặn lệnh chạy: vật tư đã có chủ chưa · lịch đứng được chưa · có ai
          làm không · số còn khớp danh mục không. Khối "Còn thiếu N mục" ngay dưới chỉ nói về sự
          đầy đủ của CHÍNH lệnh — hai câu khác nhau, cố ý không trộn. Đủ chữ ở đây (bảng lệnh chỉ
          đủ chỗ cho nhãn ngắn). */}
      {den?.den && (
        <div className="khsx-denrow">
          <DenTienDo
            den={den.den}
            lg
            onNhay={navigate ? (nhay) => navigate(nhay.man, { focusLsxMa: d.ma }) : undefined}
          />
        </div>
      )}

      {/* Top Summary Bar - Top Bar ngang (Option 1) */}
      {/* Top Summary Bar - Hero Readiness Card 2 Tầng */}
      <div className="khsx-topbar">
        {/* Tầng 1: Trạng thái kiểm tra & Nút Hành động CTA chính */}
        <div className="khsx-topbar__header">
          <div className="khsx-topbar__status">
            {/* Bảng "còn thiếu" trước đây chỉ mở bằng rê chuột — điện thoại không có chuột,
                bàn phím cũng không tới được. Thẻ kích hoạt bên dưới có tabIndex để chạm/Tab
                là mở (quy tắc :focus-within nằm ở §28 styles/responsive.css). */}
            {d.trang_thai === "san_sang" ? (
              <span className="khsx-topbar__tag khsx-topbar__tag--ok">
                <Icon name="check" size={14} /> Sẵn sàng lập kế hoạch
              </span>
            ) : d.thieu.length > 0 ? (
              <div className="khsx-topbar__pop-trigger" tabIndex={0}>
                <span className="khsx-topbar__tag khsx-topbar__tag--warn">
                  <Icon name="alert" size={14} /> Còn thiếu {d.thieu.length} mục
                </span>
                <div className="khsx-topbar__popover">
                  <p className="khsx-topbar__pop-title">Danh sách mục chưa hoàn thiện:</p>
                  <ul>
                    {d.thieu.map((code) => (
                      <li key={code}>
                        <span>• {nhanMa(LSX_THIEU_LABELS, code, dvChuoi)}</span>
                        {code === "thieu_routing" && (
                          <button type="button" className="khsx-xlink" onClick={() => setTab("routing")}>Sửa →</button>
                        )}
                        {(code === "thieu_giay" || code === "thieu_kho") && (
                          <button type="button" className="khsx-xlink" onClick={() => setTab("quycach")}>Xem →</button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <span className="khsx-topbar__tag khsx-topbar__tag--ok">
                <Icon name="check" size={14} /> Đủ dữ liệu
              </span>
            )}
          </div>

          {/* Nút hành động CTA & Nút Lưu khi Form thay đổi */}
          <div className="khsx-topbar__action">
            {dirty && (
              <div style={{ display: "flex", gap: 6, marginRight: 8 }}>
                <Button variant="ghost" onClick={() => setForm(toForm(d))}>
                  Hoàn tác
                </Button>
                <Button variant="primary" loading={saving} onClick={luu}>
                  Lưu thay đổi
                </Button>
              </div>
            )}

            {d.trang_thai === "san_sang" ? (
              <Button variant="ghost" onClick={() => doiTrangThai("nhap")}>
                Mở lại để sửa
              </Button>
            ) : (
              <Button variant="accent" disabled={d.thieu.length > 0} onClick={() => doiTrangThai("san_sang")}>
                Sẵn sàng lập kế hoạch
              </Button>
            )}
          </div>
        </div>

        {/* Tầng 2: Dải thẻ KPI chỉ số (KPI Grid Tiles) */}
        <div className="khsx-topbar__metrics-grid">
          <div className="khsx-kpi-tile">
            <span className="khsx-kpi-tile__label">SL Đặt</span>
            <span className="khsx-kpi-tile__val">
              {num(d.so_luong_dat)} <small>{d.don_vi_tinh}</small>
            </span>
          </div>

          {/* NHÃN nói CHẶNG, ĐƠN VỊ đi với con số (12/08/2026) — cùng luật với bảng danh sách lệnh
              và bảng lệnh dự kiến. Bản trước lấy tên đơn vị làm nhãn thẻ, nên chặng nào routing
              không nói tới là phải bịa một chữ ("TỜ NGUYÊN") rồi bày cạnh chữ đọc thật.
              Ngoại lệ có chủ ý: các ô KÍCH THƯỚC ("Khổ … dài") vẫn mang tên đơn vị trong nhãn —
              giá trị ở đó là mm, không có cặp số+đơn vị nào để tách. */}
          {/* GỠ 15/08/2026: ô KPI "Bù hao" — nó đọc `lsx.bu_hao_to`, cột chỉ đổi được bằng ô
              "Hao hụt thêm" (nay đã bỏ) nên luôn hiện 0 trên mọi lệnh. Hao thật của từng bước xem
              ở chip "Hao hụt định mức" trong drawer bước — đo đúng đơn vị của bước đó. */}

          <div className="khsx-kpi-tile khsx-kpi-tile--hero">
            <span className="khsx-kpi-tile__label">Vào máy</span>
            <span className="khsx-kpi-tile__val">
              {num(d.so_to_ke_hoach)} <small>{dvTo}</small>
            </span>
          </div>

          <div className="khsx-kpi-tile">
            <span className="khsx-kpi-tile__label">Giấy nguyên</span>
            <span className="khsx-kpi-tile__val">
              {num(d.so_to_nguyen)} <small>{dvToNguyen}</small>
            </span>
          </div>

          {laSach ? (
            <div className="khsx-kpi-tile" title={giaiThichSach}>
              <span className="khsx-kpi-tile__label">Gấp tay</span>
              <span className="khsx-kpi-tile__val">
                {num(soTay)} <small>{dvTay || dvTo}{d.don_vi_tinh ? ` / ${d.don_vi_tinh}` : ""}</small>
              </span>
            </div>
          ) : (
            <div
              className="khsx-kpi-tile"
              title={dvTp && dvTo ? `${num(d.so_con)} ${dvTp} trên 1 ${dvTo}` : undefined}
            >
              <span className="khsx-kpi-tile__label">Bình bài</span>
              <span className="khsx-kpi-tile__val">
                {num(d.so_con)} <small>{dvTp}</small>
              </span>
            </div>
          )}

          <div className="khsx-kpi-tile">
            <span className="khsx-kpi-tile__label">Công đoạn</span>
            <span className="khsx-kpi-tile__val">{num(d.cong_doans.length)}</span>
          </div>

          {/* Ô này hiện ở MỌI tab — đó là lý do nó tồn tại. Đứng ở tab Công đoạn vẫn liếc thấy
              lệnh đã khai vật tư chưa, khỏi phải nhớ bấm sang tab khác để kiểm trước khi phát hành.
              Chưa khai gì thì để "—" nhạt, KHÔNG hiện số 0: 0 trông như một số đã tính. */}
          <div
            className="khsx-kpi-tile"
            title={
              keVatTu.so_mon > 0
                ? `${keVatTu.so_mon} món · ${keVatTu.so_buoc_trong}/${d.cong_doans.length} bước chưa khai`
                : "Lệnh chưa khai vật tư nào"
            }
          >
            <span className="khsx-kpi-tile__label">Vật tư</span>
            <span className="khsx-kpi-tile__val">
              {keVatTu.so_mon > 0 ? (
                <>
                  {num(keVatTu.so_mon)} <small>món</small>
                </>
              ) : (
                <span className="khsx-muted">—</span>
              )}
            </span>
          </div>

          <div className="khsx-kpi-tile">
            <span className="khsx-kpi-tile__label">Hạn giao</span>
            <span className={`khsx-kpi-tile__val ${classHan(d.han_giao_khach)}`}>
              {ngay(d.han_giao_khach)}
            </span>
          </div>

          {d.khoan_tien_tong > 0 && (
            <div className="khsx-kpi-tile khsx-kpi-tile--rust" title="Tổng tiền công thợ dự kiến">
              <span className="khsx-kpi-tile__label">Công thợ</span>
              <span className="khsx-kpi-tile__val khsx-kpi-tile__val--rust">
                {num(d.khoan_tien_tong)} <small>đ</small>
              </span>
            </div>
          )}
        </div>
      </div>

      {readyErr && <BangLoi text={readyErr} onRetry={load} />}
      {err && <BangLoi text={err} onRetry={load} />}

      {boDauViec.length > 0 && (
        <div className="khsx-luuy" role="status">
          <p className="khsx-luuy__title">
            <Icon name="alert" size={15} />
            Đã lưu — nhưng gỡ đầu việc mồ côi ở {boDauViec.length} bước
            <button
              type="button"
              className="khsx-luuy__x"
              aria-label="Đóng lưu ý"
              onClick={() => setBoDauViec([])}
            >
              <Icon name="x" size={14} />
            </button>
          </p>
          <ul className="khsx-luuy__list">
            {boDauViec.map((b) => (
              <li key={b.vi_tri}>
                <strong>Bước {b.vi_tri} · {b.ten}:</strong>{" "}
                đầu việc “{b.dau_viec}” không còn thuộc công đoạn/tổ hiện tại nên đã gỡ.
              </li>
            ))}
          </ul>
          <p className="khsx-luuy__foot">
            Mở tab Công đoạn, vào từng bước trên để chọn lại đầu việc phù hợp (nếu cần).
          </p>
        </div>
      )}

      <div className="khsx-detail__grid">
        <div className="khsx-detail__main">
          <div className="khsx-tabs" role="tablist" aria-label="Nội dung lệnh sản xuất">
            {visibleTabs.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`khsx-tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls={`khsx-panel-${t.key}`}
                className={`khsx-tabs__btn ${tab === t.key ? "is-active" : ""}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                {((t.key === "routing" && routingDirty) ||
                  ((t.key === "chung" || t.key === "quycach") && dirty)) && (
                  <span className="khsx-tabs__dot" aria-label="có thay đổi chưa lưu" />
                )}
              </button>
            ))}
          </div>

          {tab === "chung" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-chung" aria-labelledby="khsx-tab-chung" tabIndex={0}>
              <div className={`khsx-spec__card ${form.is_rush ? "khsx-spec__card--rush" : ""}`}>
                <div className="khsx-spec__card-head khsx-spec__card-head--flex">
                  <h4 className="khsx-spec__title">Thông tin kế hoạch</h4>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={form.is_rush}
                    className={`khsx-rush-toggle ${form.is_rush ? "is-rush" : ""}`}
                    onClick={() => set("is_rush", !form.is_rush)}
                    title={form.is_rush ? "Đang bật ưu tiên hàng gấp ở xưởng" : "Bấm để đánh dấu hàng gấp"}
                  >
                    <span className="khsx-rush-toggle__indicator">
                      {form.is_rush && <span className="khsx-rush-toggle__pulse" />}
                    </span>
                    <span className="khsx-rush-toggle__label">
                      {form.is_rush ? "Ưu tiên: Hàng GẤP" : "Hàng thường"}
                    </span>
                  </button>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-plan-form">
                    <div className="khsx-plan-form__row">
                      <label className="khsx-field khsx-field--flex2">
                        <span className="khsx-field__label">Tên lệnh sản xuất</span>
                        <input
                          value={form.ten}
                          placeholder="Nhập tên lệnh..."
                          onChange={(e) => set("ten", e.target.value)}
                        />
                      </label>
                      <label className="khsx-field khsx-field--flex1">
                        <span className="khsx-field__label">Hạn hoàn thành sản xuất</span>
                        <input
                          type="date"
                          value={form.han_hoan_thanh_sx}
                          onChange={(e) => set("han_hoan_thanh_sx", e.target.value)}
                        />
                      </label>
                    </div>

                    {demHan.status !== "none" && (
                      <div className={`khsx-buffer-gauge khsx-buffer-gauge--${demHan.status}`}>
                        <div className="khsx-buffer-gauge__track">
                          <div className="khsx-buffer-gauge__milestone">
                            <span className="khsx-buffer-gauge__tag">Bàn giao</span>
                            <span className="khsx-buffer-gauge__val">{ngay(d.ban_giao_at || d.created_at)}</span>
                          </div>
                          <div className="khsx-buffer-gauge__bar-wrap">
                            <div className="khsx-buffer-gauge__bar" />
                            <span className="khsx-buffer-gauge__badge">
                              {demHan.text}
                            </span>
                          </div>
                          <div className="khsx-buffer-gauge__milestone">
                            <span className="khsx-buffer-gauge__tag">Hạn giao</span>
                            <span className="khsx-buffer-gauge__val">{ngay(d.han_giao_khach)}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    <label className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">Ghi chú kế hoạch</span>
                      <textarea
                        rows={3}
                        placeholder="Ghi chú điều phối sản xuất, dặn dò xưởng..."
                        value={form.ghi_chu}
                        onChange={(e) => set("ghi_chu", e.target.value)}
                      />
                    </label>
                  </div>
                </div>
              </div>

              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head khsx-spec__card-head--flex">
                  <h4 className="khsx-spec__title">Đơn hàng &amp; Nhân sự phụ trách</h4>
                  {d.order_no && (
                    <div className="khsx-order-badge" title="Mã đơn hàng">
                      <span className="khsx-order-badge__code">{d.order_no}</span>
                      <button
                        type="button"
                        className="khsx-order-badge__copy"
                        onClick={() => {
                          if (navigator.clipboard) {
                            navigator.clipboard.writeText(d.order_no || "");
                          }
                          setCopiedOrder(true);
                          setTimeout(() => setCopiedOrder(false), 2000);
                        }}
                        title="Copy mã đơn hàng"
                      >
                        {copiedOrder ? "Đã chép" : "Chép mã"}
                      </button>
                    </div>
                  )}
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-split-grid">
                    {/* Cột trái: Thông tin đơn hàng & Khách hàng */}
                    <div className="khsx-split-col">
                      <div className="khsx-entity-row">
                        <span className="khsx-entity-row__label">Khách hàng</span>
                        <div className="khsx-entity-row__val-main">{d.customer_name || "—"}</div>
                      </div>
                      <div className="khsx-entity-row">
                        <span className="khsx-entity-row__label">Hạn giao khách</span>
                        <div className="khsx-entity-row__val-date">
                          <span className="khsx-val-date__main">{ngay(d.han_giao_khach)}</span>
                          {d.han_giao_khach && (
                            <span className={`khsx-val-date__badge ${classHan(d.han_giao_khach)}`}>
                              {demNgayConLai(d.han_giao_khach)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Cột phải: Đội ngũ phụ trách */}
                    <div className="khsx-split-col">
                      <div className="khsx-team-item">
                        <div className="khsx-team-item__avatar">
                          {getInitials(d.sale_name)}
                        </div>
                        <div className="khsx-team-item__info">
                          <span className="khsx-team-item__role">Kinh doanh phụ trách</span>
                          <span className="khsx-team-item__name">{d.sale_name || "—"}</span>
                        </div>
                      </div>

                      <div className="khsx-team-item">
                        <div className="khsx-team-item__avatar khsx-team-item__avatar--blue">
                          {getInitials(d.nguoi_phu_trach_ten || "Kế hoạch")}
                        </div>
                        <div className="khsx-team-item__info">
                          <span className="khsx-team-item__role">Điều phối kế hoạch</span>
                          <span className="khsx-team-item__name">{d.nguoi_phu_trach_ten || "Kế hoạch sản xuất"}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="khsx-spec__card-foot">
                  <div className="khsx-audit-trail">
                    <span>Bàn giao: <strong>{ngayGio(d.ban_giao_at) || "—"}</strong></span>
                    <span className="khsx-audit-trail__dot">•</span>
                    <span>Tạo lúc: <strong>{ngayGio(d.created_at) || "—"}</strong></span>
                    <span className="khsx-audit-trail__dot">•</span>
                    <span>Sửa lúc: <strong>{ngayGio(d.updated_at) || "—"}</strong></span>
                  </div>
                </div>
              </div>
            </section>
          )}

          {tab === "quycach" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-quycach" aria-labelledby="khsx-tab-quycach" tabIndex={0}>
              {d.luu_y_gui_xuong ? (
                <div className="khsx-spec__note">
                  <Icon name="bell" size={16} />
                  <div>
                    <strong className="khsx-spec__note-title">LƯU Ý SẢN XUẤT (GỬI XƯỞNG)</strong>
                    <span className="khsx-spec__note-content">{d.luu_y_gui_xuong}</span>
                  </div>
                </div>
              ) : null}
              {/* GỠ 07/09/2026: băng "đang giữ chỗ vật tư nên ô Giấy khoá luôn". Ô Giấy đã bỏ
                  hẳn nên băng đi báo khoá một ô không còn trên màn. Giữ chỗ vẫn khoá bảng công
                  đoạn và nút Xoá — hai chỗ đó có băng/chip riêng. */}
              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="box" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Thành phẩm</h4>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-kvgrid">
                    {/* Khối này giữ đúng phần NHẬN DIỆN sản phẩm. Hai ô đã gỡ (12/08/2026):
                        · "Dài × rộng (mm)" — trùng cặp ô nhập "Khổ thành phẩm dài/rộng" ở khối
                          Giấy, mà tệ hơn là LỆCH ĐƯỢC: ô này đọc ảnh chụp đã lưu còn ô kia đọc
                          form đang gõ, nên sửa khổ xong hai chỗ hiện hai số cho tới lúc bấm Lưu.
                        · "Số bài in" — trùng ô cùng tên ở khối "Máy tự tính". Với hàng cắt rời nó
                          chỉ hiện "1" (không nói gì), còn với sách thì câu diễn giải đầy đủ
                          ("5 TỜ CHẠY MÁY = 1 cuốn") đã nằm sẵn dưới ô Bình bài — xem `giaiThichSach`. */}
                    <KV k="Tên sản phẩm" v={s("ten")} />
                    <KV k="Loại sản phẩm" v={s("loai_san_pham_ten")} />
                    <KV k="Đơn vị tính" v={s("don_vi_tinh")} />
                    {/* Hai số PHÂN BIỆT sách với hàng cắt rời. Có sẵn trong ảnh chụp quy cách nhưng
                        trước đây không màn nào render → nhìn lệnh không biết đây là loại gì. */}
                    {laSach && (
                      <KV k="Số trang / trang mỗi tay" v={`${num(n("so_trang"))} / ${num(trangMoiTay)}`} mono />
                    )}
                    {/* Ưu tiên nhãn ĐỌC SỐNG từ dòng đơn; ảnh chụp quy cách chỉ là dự phòng cho
                        lệnh tạo trước khi có tính năng nhóm. */}
                    <KV k="Thuộc sản phẩm" v={d.nhom || s("nhom_bao_gia")} />
                  </div>
                </div>
              </div>

              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="printer" size={16} />
                  </div>
                  {/* "Khổ giấy nguyên" là kích thước TỜ GIẤY MUA VỀ — thuộc tính của giấy trong
                      danh mục, không phải đơn vị đếm của routing, nên giữ nguyên chữ. Còn "tờ in"
                      chính là đơn vị bước in đang đếm ⇒ lấy tên từ danh mục. */}
                  <h4 className="khsx-spec__title">Giấy &amp; {dvTo}</h4>
                  {/* Ảnh chụp từ phiếu tính giá và GIỮ NGUYÊN như ảnh chụp: cụm này là thứ đã tính
                      ra giá và đã báo cho khách. Nhãn nói thẳng "chỉ xem" — vì ngay khối dưới là số
                      máy tự tính cũng không sửa được; hai khối cùng "chỉ xem" mà không nói lý do
                      thì trông như màn hỏng. */}
                  <span className="khsx-spec__hint">thông số — chỉ xem</span>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-kvgrid">
                    {/* ĐƯỜNG ĐI TIẾP phải nằm ngay trong khối, không chỉ ở nhãn góc: nhãn nói
                        "chỉ xem" là mới nói được nửa việc, người kế hoạch còn phải biết đi đâu để
                        đổi thật. Nói luôn cả vế "lệnh không tự bám theo phiếu" vì sửa phiếu xong
                        mà lệnh đứng yên là chỗ dễ tưởng hỏng nhất. */}
                    <p className="khsx-nhom__sub khsx-kv--span">
                      Thông số chụp từ phiếu tính giá lúc tạo lệnh và không sửa ở đây, kể cả giấy —
                      muốn đổi thì sửa ở phiếu tính giá rồi tạo lại lệnh (lệnh không tự bám theo
                      phiếu).
                    </p>
                    {/* GIẤY — CHỈ XEM từ 07/09/2026. Trước đó đây là ô sửa được duy nhất của cả
                        cụm (13/08/2026, bó vào danh sách thay thế 05/09/2026) để xưởng đổi giấy
                        tại chỗ khi hết hàng. Nay bỏ hẳn: phiếu tính giá tính trên giấy nào thì
                        lệnh chạy đúng giấy đó, đổi giấy là đổi bài toán giá nên phải quay về phiếu
                        rồi tạo lại lệnh. Backend `ap_quy_cach` vẫn nhận `giay_id`, chỉ là màn này
                        không còn gửi `quy_cach` nữa. */}
                    <KV k="Giấy" v={s("giay_ten")} />
                    {/* Định lượng đọc thẳng từ ảnh chụp, không tra lại danh mục: giấy ở lệnh không
                        đổi được nữa nên `gsm` đã lưu luôn là gsm của đúng loại giấy đang hiện. */}
                    <KV k="Định lượng (gsm)" v={qc.gsm ? num(n("gsm")) : "—"} mono />
                    {/* GỠ 2026-08-09 (Đợt 4 · K): dòng "Nguồn giấy". Công ty luôn cấp giấy nên
                        dòng này chỉ còn là một ô luôn ghi "Công ty" — chiếm chỗ, không nói gì. */}
                    <KVSo k="Khổ giấy nguyên dài" suffix="mm" v={form.qc.kho_nguyen_dai} />
                    <KVSo k="Khổ giấy nguyên rộng" suffix="mm" v={form.qc.kho_nguyen_rong} />
                    <KVSo k={`Khổ ${dvTo} dài`} suffix="mm" v={form.qc.kho_in_dai} />
                    <KVSo k={`Khổ ${dvTo} rộng`} suffix="mm" v={form.qc.kho_in_rong} />
                    {/* 0 × 0 = CHƯA khai khổ tờ in — engine chạy thẳng trên khổ giấy nguyên. Nói
                        ra chứ để hai số 0 trần thì trông như thiếu dữ liệu. */}
                    {!((form.qc.kho_in_dai ?? 0) > 0 && (form.qc.kho_in_rong ?? 0) > 0) && (
                      <p className="khsx-nhom__sub khsx-kv--span">
                        Để 0 × 0 = in thẳng khổ giấy nguyên, không xả.
                      </p>
                    )}
                    <KVSo k="Khổ thành phẩm dài" suffix="mm" v={form.qc.dai_thanh_pham} />
                    <KVSo k="Khổ thành phẩm rộng" suffix="mm" v={form.qc.rong_thanh_pham} />
                    <KV k="Cách in" v={nhanCachIn(form.qc.quy_cach_in ?? "mot_mat")} />
                    {/* Hai ô này CHỈ có nghĩa với hàng NHIỀU TRANG. Thẻ, tờ rơi, hộp thì cả hai
                        luôn là 1/1 — bày ra chỉ tổ chiếm chỗ và mời người ta gõ một số vô nghĩa.
                        Cấu trúc sản phẩm (mấy trang) là việc của bài TÍNH GIÁ, không phải của kế
                        hoạch: muốn biến một tờ rời thành sách thì sửa ở phiếu rồi tạo lại lệnh. */}
                    {(form.qc.so_trang ?? 1) > 1 && (
                      <>
                        <KVSo k="Số trang" v={form.qc.so_trang} />
                        <KVSo k="Trang mỗi tay" v={form.qc.trang_moi_tay} />
                      </>
                    )}
                    <KVSo k="Bleed" suffix="mm" v={form.qc.bleed_mm} />
                    <KVSo k="Khe cắt" suffix="mm" v={form.qc.khe_cat_mm} />
                    {/* Mực KHÔNG nhét vào lưới key-value: nó là tập mã, cần chip bấm. Dùng lại
                        đúng khối đã dựng ở phiếu tính giá, không đẻ khối thứ hai rồi hai bên lệch.
                        `disabled` cứng + `onChange` rỗng: khối này là bảng chip có sẵn đường sửa,
                        bỏ hẳn `onChange` thì phải sửa chữ ký component dùng chung ở hai màn. */}
                    <div className="khsx-kv khsx-kv--span">
                      <span className="khsx-kv__key">Mực in</span>
                      <MucInHang
                        mucA={form.qc.muc_a ?? []}
                        mucB={form.qc.muc_b ?? []}
                        quyCachIn={form.qc.quy_cach_in ?? "mot_mat"}
                        disabled
                        onChange={() => {}}
                      />
                    </div>
                    {/* Chừa TÁCH CHIỀU do SERVER tính (`chua_theo_chieu`) — màn này chỉ hiện. Cộng
                        lại ở đây là đẻ bản thứ hai của công thức, mà bản thứ hai chính là chỗ vừa
                        sai: gộp "20" rồi trừ đều hai chiều, trong khi engine trừ 15/10. */}
                    <KV k="Chừa dài / rộng (mm)" v={`${num(d.chua_dai)} / ${num(d.chua_rong)}`} mono />
                  </div>
                </div>
              </div>

              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="grid" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Máy tự tính</h4>
                  {/* Khối HỆ QUẢ. Không ô nào sửa được ở đây — muốn số khác thì sửa THÔNG SỐ ở
                      khối trên. Sửa xong là mọi số dưới này tính lại, kể cả số ai đó từng gõ tay. */}
                  <span className="khsx-spec__hint">theo thông số ở trên</span>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-kvgrid">
                    {/* Bình bài (`so_con`) CŨNG chỉ xem từ 05/09/2026. Nó không phải "thông số
                        trình bày": đổi con/tờ là `_ap_chuoi_nguoc` viết lại số tờ kế hoạch ⇒ đổi
                        lượng giấy cần (đo trên LSX26-0008: 16 → 8 con làm giấy nguyên 368 → 505
                        tờ). Bài ghép mới là chỗ ép lại con/tờ, ở đó có bàn giấy và máy thật. */}
                    <div className="khsx-kv" title={giaiThichSach}>
                      {/* Nhãn NGẮN, tỉ số để trong tooltip: nhét "· SẢN PHẨM XONG mỗi TỜ CHẠY MÁY"
                          vào nhãn thì ô đầu tiên cao gấp đôi mấy ô cạnh nó, cả lưới lệch. */}
                      <span
                        className="khsx-kv__key"
                        title={dvTp && dvTo ? `Số ${dvTp} trên 1 ${dvTo}` : undefined}
                      >
                        Bình bài
                      </span>
                      <span className="khsx-kv__val khsx-num">
                        {num(Number(form.so_con) || 0)}
                      </span>
                    </div>
                    {laSach && (
                      <p className="khsx-nhom__sub khsx-kv--span">{giaiThichSach}</p>
                    )}
                    <KVSoDv k="Số mảnh xả" v={n("so_manh_xa")} />
                    <KVSoDv k="Số kẽm" v={n("so_kem")} />
                    <KVSoDv k="Số lượt in" v={n("so_luot")} />
                    {/* NHÃN nói CHẶNG, ĐƠN VỊ đi với con số — cùng luật với thanh KPI. Trước đây
                        nhãn lấy thẳng tên đơn vị nên lệnh KHÔNG có bước xả (tờ nguyên = tờ in) đẻ
                        ra hai dòng "SỐ TỜ CHẠY MÁY KẾ HOẠCH" và "SỐ TỜ CHẠY MÁY" cùng một con số —
                        nhìn như một chỗ bị lặp, trong khi chúng là hai chặng khác nhau. */}
                    <KVSoDv k="Vào máy" dv={dvTo} v={d.so_to_ke_hoach} />
                    <KVSoDv k="Giấy nguyên" dv={dvToNguyen} v={d.so_to_nguyen} />
                    <KVSoDv k="Số bài in" dv={dvTay} v={n("so_to_per_sp") || 1} />
                    {/* GỠ 07/09/2026: ô "Cách bình" (`con_auto`). Nó chỉ nói ENGINE đã bình bài kiểu
                        nào — máy tự xếp hay ép đúng số con khai ở phiếu tính giá — mà kết quả của cả
                        hai kiểu đã nằm ngay ô "Bình bài" phía trên. Ở lệnh thì không ai chọn được
                        kiểu nữa (quy cách chỉ xem), nên dòng này chỉ là một chữ không dẫn đi đâu. */}
                  </div>
                </div>
              </div>

              {vatTus.length > 0 && (
                <div className="khsx-spec__card">
                  <div className="khsx-spec__card-head">
                    <div className="khsx-spec__card-icon">
                      <Icon name="layers" size={16} />
                    </div>
                    <h4 className="khsx-spec__title">Vật tư khác</h4>
                  </div>
                  <div className="khsx-spec__card-body">
                    <div className="khsx-kvgrid">
                      {vatTus.map((vt, i) => (
                        <KV
                          key={i}
                          k={vt.ten || `Vật tư ${i + 1}`}
                          v={vt.so_luong ? num(Number(vt.so_luong)) : "theo định mức"}
                          mono
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {coBinhBai && (
                <div className="khsx-spec__card khsx-spec__card--diagram">
                  <div className="khsx-spec__card-head">
                    <div className="khsx-spec__card-icon">
                      <Icon name="clipboard" size={16} />
                    </div>
                    <h4 className="khsx-spec__title">
                      {laSach ? "Sơ đồ tay sách" : "Sơ đồ bình khổ"}
                    </h4>
                  </div>
                  <div className="khsx-spec__card-body">
                    {/* KẾ THỪA TRỌN từ phiếu tính giá: đưa NGUYÊN các khoản chừa + bleed + khe cắt
                        của quy cách, để server tách chiều bằng đúng engine. Bản trước tự cộng năm
                        khoản thành một số rồi trừ đều hai chiều và bỏ quên bleed → sơ đồ vẽ 105
                        con trong khi phiếu ra 99, hiệu suất cũng thành số ảo.

                        Khổ/bleed/khe LẤY TỪ `form.qc` chứ không từ ảnh chụp đã lưu: từ khi mở khoá
                        sửa thông số, đọc ảnh chụp nghĩa là gõ lại khổ tờ in mà hình đứng im.
                        `trangMoiTay` BẮT BUỘC truyền — thiếu nó thì sách vẽ lưới CẮT RỜI (16 con,
                        4×4) trong khi tờ in gấp nguyên thành một tay, không cắt con nào. */}
                    <ImpositionDiagram
                      khoInDai={form.qc.kho_in_dai ?? 0}
                      khoInRong={form.qc.kho_in_rong ?? 0}
                      daiTP={form.qc.dai_thanh_pham ?? 0}
                      rongTP={form.qc.rong_thanh_pham ?? 0}
                      chuaMm={0}
                      chuaTho={{
                        chua_nhip: n("chua_nhip"),
                        nhip_giay_mm: n("nhip_giay_mm"),
                        le_hong_mm: n("le_hong_mm"),
                        duoi_thang_mau_mm: n("duoi_thang_mau_mm"),
                      }}
                      bleedMm={form.qc.bleed_mm ?? 0}
                      kheCatMm={form.qc.khe_cat_mm ?? 0}
                      soCon={n("so_con")}
                      trangMoiTay={form.qc.trang_moi_tay ?? 1}
                      dvCon={dvTp}
                      dvTo={dvTo}
                    />
                  </div>
                </div>
              )}

            </section>
          )}

          {tab === "routing" && !orderCancelled && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-routing" aria-labelledby="khsx-tab-routing" tabIndex={0}>
              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="workflow" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Công đoạn sản xuất (Routing)</h4>
                </div>
                <div className="khsx-spec__card-body">
                  <LsxRoutingTable
                    congDoans={d.cong_doans}
                    soLuongDat={d.so_luong_dat}
                    leadTime={d.lead_time}
                    baiGhep={d.bai_ghep}
                    congDoanRefs={congDoanRefs}
                    toRefs={toRefs}
                    mayRefs={mayRefs}
                    khuonRefs={khuonRefs}
                    tenSanPham={d.ten}
                    tenKhach={d.customer_name ?? ""}
                    onTaoKhuon={taoKhuon}
                    vatTuRefs={vatTuRefs}
                    giayRefs={giayRefs}
                    phuThuocRefs={phuThuocRefs}
                    canUpdate={canUpdate}
                    giuCho={d.giu_cho_bat}
                    saving={savingRouting}
                    onSave={luuRouting}
                    onPatchLsx={patchLsx}
                    onMacDinhBuoc={macDinhBuoc}
                    onDauViecOptions={dauViecOptions}
                    onXemTruocBuoc={xemTruocBuoc}
                    onXemTruocRouting={xemTruocRouting}
                    onDirtyChange={setRoutingDirty}
                    dvChuoi={dvChuoi}
                  />
                </div>
              </div>
            </section>
          )}

          {tab === "vattu" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-vattu" aria-labelledby="khsx-tab-vattu" tabIndex={0}>
              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="box" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Vật tư của lệnh</h4>
                </div>
                <div className="khsx-spec__card-body">
                  <LsxVatTuPanel ke={keVatTu} />
                </div>
              </div>
            </section>
          )}

          {tab === "nhatky" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-nhatky" aria-labelledby="khsx-tab-nhatky" tabIndex={0}>
              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="clock" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Nhật ký hoạt động &amp; Lịch sử thay đổi</h4>
                </div>
                <div className="khsx-spec__card-body">
                  {acts === null ? (
                    <p className="khsx-muted">Đang tải nhật ký…</p>
                  ) : (
                    <Timeline
                      emptyText="Chưa có hoạt động."
                      items={acts.map((a) => ({
                        title: a.detail || ACTION_LABEL[a.action] || a.action,
                        meta: `${a.actor_name ?? "—"} · ${ngayGio(a.at)}`,
                        accent: a.action === "create_lsx" || a.action === "lsx_trang_thai",
                      }))}
                    />
                  )}
                </div>
              </div>
            </section>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={askDelete}
        title={`Xoá lệnh ${d.ma}?`}
        message="Lệnh chưa phát hành nên xoá được. Dòng đơn sẽ quay lại hàng chờ để lên lệnh lại."
        confirmLabel="Xoá lệnh"
        danger
        onConfirm={xoa}
        onCancel={() => setAskDelete(false)}
      />

      {/* Bảng CŨ → MỚI. Bấm "Cập nhật theo danh mục" ở băng chỉ MỞ cái này; ghi thật là nút trong
          đây. Người lập kế hoạch phải nhìn thấy tiền công đổi từ đâu sang đâu trước khi đồng ý. */}
      <ConfirmDialog
        open={xemDmDoi && !!dmDoi}
        wide
        title={`Lấy số mới của danh mục cho ${d.ma}?`}
        confirmLabel="Đồng ý cập nhật"
        cancelLabel="Để nguyên số cũ"
        busy={dongBo}
        error={dongBoErr}
        onConfirm={capNhatTheoDanhMuc}
        onCancel={() => {
          setXemDmDoi(false);
          setDongBoErr(null);
        }}
      >
        <div className="khsx-dmdoi__bang">
          {(dmDoi?.buocs ?? []).map((b) => (
            <section key={b.buoc_id} className="khsx-dmdoi__buoc">
              <h4>Bước {b.thu_tu} · {b.ten}</h4>
              {b.khoan_mo_coi && (
                <p className="khsx-dmdoi__note">
                  Đầu việc “{b.khoan_mo_coi}” không còn thuộc công đoạn/tổ của bước. Cập nhật KHÔNG
                  chọn hộ — mở tab Công đoạn chọn lại đầu việc rồi bấm Lưu.
                </p>
              )}
              {b.khoan_chua_chon && (
                <p className="khsx-dmdoi__note">
                  Bước chưa chọn đầu việc; danh mục nay chỉ có đúng một cái là “{b.khoan_chua_chon}”
                  nên cập nhật sẽ điền vào.
                </p>
              )}
              {b.may_canh_bao && <p className="khsx-dmdoi__note">{b.may_canh_bao}</p>}
              {(b.khoan.length > 0 || b.vat_tu_them.length > 0 || b.vat_tu_lech.length > 0) && (
                <table className="khsx-dmdoi__tbl">
                  <thead>
                    <tr><th>Ô</th><th>Đang giữ</th><th>Danh mục nay</th></tr>
                  </thead>
                  <tbody>
                    {b.khoan.map((k) => (
                      <tr key={k.truong}>
                        <td>{k.nhan}</td>
                        <td className="khsx-dmdoi__cu">{k.cu ?? "—"}</td>
                        <td className="khsx-dmdoi__moi">{k.moi ?? "—"}</td>
                      </tr>
                    ))}
                    {b.vat_tu_them.map((v) => (
                      <tr key={`t${v.vat_tu_id}`}>
                        <td>{tenVatTu(v)}</td>
                        <td className="khsx-dmdoi__cu">chưa có</td>
                        <td className="khsx-dmdoi__moi">{num(v.so_luong_moi ?? 0)} {v.don_vi ?? ""}</td>
                      </tr>
                    ))}
                    {b.vat_tu_lech.map((v) => (
                      <tr key={`l${v.vat_tu_id}`}>
                        <td>{tenVatTu(v)}</td>
                        <td className="khsx-dmdoi__cu">{num(v.so_luong_cu ?? 0)} {v.don_vi ?? ""}</td>
                        <td className="khsx-dmdoi__moi">{num(v.so_luong_moi ?? 0)} {v.don_vi ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {b.vat_tu_bo.length > 0 && (
                <p className="khsx-dmdoi__note">
                  GIỮ NGUYÊN, không xoá: {b.vat_tu_bo.map(tenVatTu).join(" · ")} — danh mục nay
                  không bung ra món này nữa (thường vì ô “Công thức định mức” bị bỏ trống). Muốn bỏ
                  thì xoá tay ở tab Công đoạn.
                </p>
              )}
            </section>
          ))}
          <p className="khsx-dmdoi__foot">
            Cập nhật KHÔNG đụng số nhân công đã sắp cho từng bước và KHÔNG xoá dòng vật tư nào.
          </p>
        </div>
      </ConfirmDialog>
    </div>
  );
}

/** Nhãn một món vật tư trên bảng cũ → mới. Mã có thì mã đứng trước — người xưởng đọc mã nhanh hơn
 *  đọc tên, mà tên món in ấn hay dài quá một dòng. */
function tenVatTu(v: DanhMucDoiVatTu): string {
  return [v.ma, v.ten].filter(Boolean).join(" · ") || `#${v.vat_tu_id}`;
}

/** Ô THÔNG SỐ dạng số — CHỈ HIỆN. Trước 05/09/2026 đây là ô `<input type="number">` (`KVNum`);
 *  nay quy cách ở lệnh không sửa được nữa nên bỏ hẳn ô nhập thay vì để `<input disabled>`: ô mờ
 *  đọc như "tạm thời không bấm được", còn thật ra ở màn này KHÔNG có đường sửa nào cả. Đơn vị vẫn
 *  nằm trong nhãn như cũ để lưới không đổi bố cục. */
function KVSo({ k, v, suffix }: { k: string; v: number | undefined; suffix?: string }) {
  return <KV k={`${k}${suffix ? ` (${suffix})` : ""}`} v={num(v ?? 0)} mono />;
}

/** Số MÁY TỰ TÍNH — chỉ hiện. Trước 07/09/2026 ô này còn gánh phần "xem trước": sửa thông số thì
 *  hiện số cũ gạch ngang cạnh số mới kèm chip "tính lại". Quy cách ở lệnh nay không sửa được nữa
 *  nên chỉ còn MỘT con số, giữ nguyên class để lưới không đổi bố cục. */
function KVSoDv({ k, v, dv }: { k: string; v: number; dv?: string }) {
  return (
    <div className="khsx-kv khsx-kv--deriv">
      <span className="khsx-kv__key">{k}</span>
      <span className="khsx-kv__val khsx-num">
        {v.toLocaleString("vi-VN")}
        {/* ĐƠN VỊ đi với con số, không nằm trong nhãn — nhãn để dành nói CHẶNG. Rỗng thì không
            hiện gì: routing chưa nói tới chặng đó, bịa một chữ vào đây là quay lại lối cũ. */}
        {dv ? <small className="khsx-unit">{dv}</small> : null}
      </span>
    </div>
  );
}

function KV({
  k,
  v,
  mono = false,
  badge = false,
}: {
  k: string;
  v: React.ReactNode;
  mono?: boolean;
  badge?: boolean;
}) {
  const isNil = typeof v === "string" && (v === "—" || v === "-" || v.startsWith("— "));
  return (
    <div className="khsx-kv">
      <span className="khsx-kv__key">{k}</span>
      <span
        className={`khsx-kv__val ${mono ? "khsx-num" : ""} ${isNil ? "is-nil" : ""} ${badge && !isNil ? "is-badge" : ""}`}
      >
        {v}
      </span>
    </div>
  );
}
