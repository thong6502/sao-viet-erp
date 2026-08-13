// Chi tiết 1 LỆNH SẢN XUẤT — nơi kế hoạch hoàn thiện lệnh trước khi lập kế hoạch.
// 4 tab: Thông tin chung · Quy cách · Công đoạn (routing) · Nhật ký.
// Cột phải: checklist "còn thiếu gì" + nút "Sẵn sàng lập kế hoạch" (CTA duy nhất của màn).
//
// Trạng thái `nhap ↔ cho_bo_sung` do SERVER lật sau mỗi lần lưu — client luôn lấy lại từ response,
// không tự đoán. `san_sang` là hành động của NGƯỜI (server trả 409 nếu còn thiếu).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  LSX_CANH_BAO_LABELS,
  LSX_THIEU_LABELS,
  nhanMa,
  api,
  type LsxActivity,
  type LsxCongDoanBody,
  type LsxDetail,
  type LsxQuyCachBody,
  type LsxQuyCachXemTruoc,
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
import { donViChuoi } from "./lsxBuoc";
import { useNapTenDonVi } from "./tenDonVi";
import {
  BangLoi,
  ChipGap,
  TrangThaiPill,
  classHan,
  ngay,
  ngayGio,
  num,
} from "./keHoachSxShared";

// Tab "Số lượng & bù hao" ĐÃ BỎ: mọi số ở đó nay là dẫn xuất của chuỗi ngược (số tờ in, tờ
// nguyên, bù hao) và đã hiện ở thanh bên. Ô duy nhất còn gõ được là SL ra của bước CUỐI, nằm
// trong drawer bước; con/tờ chuyển sang tab Quy cách.
type TabKey = "chung" | "quycach" | "routing" | "nhatky";

const TABS: { key: TabKey; label: string }[] = [
  { key: "chung", label: "Thông tin chung" },
  { key: "quycach", label: "Quy cách" },
  { key: "routing", label: "Công đoạn" },
  { key: "nhatky", label: "Nhật ký" },
];

const ACTION_LABEL: Record<string, string> = {
  create_lsx: "Tạo lệnh",
  update_lsx: "Sửa thông tin",
  update_lsx_routing: "Sửa công đoạn",
  lsx_trang_thai: "Đổi trạng thái",
  delete_lsx: "Xoá lệnh",
};

interface FormState {
  ten: string;
  han_hoan_thanh_sx: string;
  is_rush: boolean;
  khuon_be_id: string;
  may_id: string;
  ghi_chu: string;
  so_luong_dat: string;
  bu_hao_to: string;
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
    khuon_be_id: d.khuon_be_id != null ? String(d.khuon_be_id) : "",
    may_id: d.may_id != null ? String(d.may_id) : "",
    ghi_chu: d.ghi_chu ?? "",
    so_luong_dat: String(d.so_luong_dat),
    bu_hao_to: String(d.bu_hao_to),
    so_to_ke_hoach: String(d.so_to_ke_hoach),
    so_to_nguyen: String(d.so_to_nguyen),
    so_con: String(d.so_con),
    qc: toQc(d),
  };
}

export function LsxDetailView({
  lsxId,
  onBack,
  onChanged,
  navigate,
}: {
  lsxId: number;
  onBack: () => void;
  onChanged: () => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const canUpdate = useCan()("san_xuat", "update");
  // Nhãn đơn vị đọc từ DANH MỤC (không bảng nhãn cứng) — cùng nguồn với bảng routing và Tính giá.
  useNapTenDonVi();
  const [d, setD] = useState<LsxDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("chung");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingRouting, setSavingRouting] = useState(false);
  const [routingDirty, setRoutingDirty] = useState(false);
  const [readyErr, setReadyErr] = useState<string | null>(null);
  const [askDelete, setAskDelete] = useState(false);
  const [acts, setActs] = useState<LsxActivity[] | null>(null);
  /** Số MÁY TỰ TÍNH ứng với thông số đang gõ — server trả, chưa lưu. null = chưa sửa gì. */
  const [xemTruoc, setXemTruoc] = useState<LsxQuyCachXemTruoc | null>(null);

  // Danh mục cho dropdown — nạp MỘT LẦN ở đây rồi truyền xuống bảng routing.
  const [congDoanRefs, setCongDoanRefs] = useState<RefRow[] | null>(null);
  const [toRefs, setToRefs] = useState<RefRow[] | null>(null);
  const [mayRefs, setMayRefs] = useState<RefRow[] | null>(null);
  // Danh mục khuôn — cho ô chọn khuôn trong drawer BƯỚC (bước nào có cờ `requires_tooling`).
  const [khuonRefs, setKhuonRefs] = useState<RefRow[] | null>(null);
  /** Danh mục giấy cho ô chọn ở khối "Giấy & tờ in". `gsm` đi kèm để hiện định lượng mới ngay. */
  const [giayRefs, setGiayRefs] = useState<
    { id: number; ten: string; ma: string; gsm: number | null }[] | null
  >(null);
  const [vatTuRefs, setVatTuRefs] = useState<RefRow[] | null>(null);
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

  useEffect(() => {
    if (!token) return;
    // Không có quyền đọc danh mục → để null, ô hiện read-only thay vì select rỗng (select rỗng
    // + lưu = xoá trắng dữ liệu).
    api.congDoan.list(token).then((r) => setCongDoanRefs(r.items.map((c) => ({ id: c.id, ten: c.ten })))).catch(() => setCongDoanRefs(null));
    api.khuonBe.list(token, { active: true })
      .then((r) => setKhuonRefs(r.items.map((k) => ({ id: k.id, ten: k.ten }))))
      .catch(() => setKhuonRefs(null));
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
      };
    }))).catch(() => setMayRefs(null));
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true }).then((r) =>
      setVatTuRefs(r.items.map((v) => ({ id: v.id, ten: v.ten, ma: String(v.ma), donVi: String(v.don_vi_gia ?? "") })))
    ).catch(() => setVatTuRefs(null));
    // Danh mục GIẤY — để kế hoạch đổi giấy ngay tại lệnh. Giấy hết hàng thì xưởng thay loại khác
    // cùng tính chất (có khi xịn hơn) mà không phải quay về phiếu tính giá tạo lại lệnh. Giữ luôn
    // `gsm` để đổi xong hiện định lượng mới ngay, khỏi chờ lưu — server cũng kéo `gsm` theo giấy
    // (`ap_quy_cach`), đây chỉ là để hai bên nói cùng một số trong lúc đang sửa.
    crud("/api/vat-lieu-kho/giay").list(token, { active: true }).then((r) =>
      setGiayRefs(r.items.map((g) => ({
        id: g.id, ten: String(g.ten), ma: String(g.ma ?? ""),
        gsm: Number(g.gsm ?? 0) || null,
      })))
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
  function setQc(p: Partial<LsxQuyCachBody>) {
    setForm((prev) => (prev ? { ...prev, qc: { ...prev.qc, ...p } } : prev));
  }

  // --- Xem trước LIVE các số máy tự tính ---------------------------------------------------
  // Đổi thông số là hỏi SERVER số mới, không tự tính ở client: engine chỉ có MỘT bản, không thì
  // màn hiện một số còn nút Lưu ghi số khác. Debounce 350ms cho ô gõ số.
  const qcDoi = useMemo(
    () => (d && form ? JSON.stringify(form.qc) !== JSON.stringify(toQc(d)) : false),
    [d, form],
  );
  const qcSig = form ? JSON.stringify(form.qc) : "";
  useEffect(() => {
    if (!token || !d || !qcDoi || !form) {
      setXemTruoc(null);
      return;
    }
    const h = window.setTimeout(() => {
      api.lsx.xemTruocQuyCach(token, d.id, form.qc).then(setXemTruoc).catch(() => setXemTruoc(null));
    }, 350);
    return () => window.clearTimeout(h);
    // `form.qc` so bằng CHUỖI — object mới mỗi render thì effect bắn liên tục, debounce không cứu.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, d?.id, qcDoi, qcSig]);

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
      bu_hao_to: Number(form.bu_hao_to || 0),
      // `so_to_ke_hoach` / `so_to_nguyen` KHÔNG gửi nữa — server đọc ra từ chuỗi ngược tại hai
      // ranh giới đơn vị (tờ nguyên → tờ in). Gửi lên chỉ tổ có nguồn sự thật thứ hai.
      so_con: Number(form.so_con || 1),
    };
    // Chỉ gửi cụm THÔNG SỐ khi nó thật sự đổi — gửi kèm mỗi lần lưu là mỗi lần lưu đều kích
    // bình bài lại + chạy lại chuỗi ngược, đè cả những số người khác vừa chỉnh.
    if (qcDoi) body.quy_cach = form.qc;
    // KHÔNG gửi `khuon_be_id` / `may_id` nữa: hai ô đó đã bỏ khỏi màn (11/08/2026). Không gửi =
    // server giữ nguyên giá trị nó đang có (máy dự kiến suy từ phiếu tính giá lúc tạo lệnh).
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
    async (p: { so_luong_dat?: number; bu_hao_to?: number }) => {
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

  /** Ghi nhận hàng gia công ngoài đi/về — GHI THẲNG, không chờ "Lưu công đoạn".
   *
   * Đây là THỰC THI chứ không phải cấu hình: nó xảy ra lúc lệnh đang chạy, và cửa ghi riêng ở
   * server không bị guard "đã lập kế hoạch" chặn. Ghi xong nhận về `LsxDetail` mới nên bảng và
   * sơ đồ tự có số mới.
   */
  const ghiGiaoNhan = useCallback(
    async (buocId: number, body: { su_kien: "giao" | "nhan"; luc?: string; so_luong?: number }) => {
      if (!token || !d) throw new Error("chưa sẵn sàng");
      const r = await api.lsx.giaoNhan(token, d.id, buocId, body);
      setD(r);
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
  // Ảnh chụp quy cách của lệnh CŨ không có các khoá thêm sau (bleed, khe cắt, cách bình…).
  // Thiếu khoá thì phải hiện "—", KHÔNG được để `n()` trả 0 rồi bày ra như số thật của phiếu.
  const co = (k: string): boolean => qc[k] !== undefined && qc[k] !== null;
  // Số tờ in / tờ nguyên KHÔNG còn tính ở đây: chúng là hai mốc ĐỌC RA từ chuỗi ngược bên server
  // (`_ap_chuoi_nguoc`). Giữ bản tính thứ hai ở frontend là mở đường cho hai số lệch nhau.
  const hanTre =
    !!form.han_hoan_thanh_sx && !!d.han_giao_khach && form.han_hoan_thanh_sx >= d.han_giao_khach;

  // XEM TRƯỚC thông số: thanh KPI phải nói CÙNG con số với khối "Máy tự tính" ngay dưới nó. Trước
  // đây KPI đọc số ĐÃ LƯU còn khối kia hiện số mới kèm chip "tính lại" — sửa khổ tờ in xong là một
  // màn hiện hai con số cho cùng một thứ, người dùng không biết tin cái nào.
  // `tam = true` ⇒ số CHƯA LƯU, thẻ tự gắn dấu hiệu (viền đứt) để không ai tưởng đã ghi vào DB.
  const kpiSo = (cu: number, moi: number | undefined) => ({
    so: moi ?? cu,
    tam: moi != null && moi !== cu,
  });
  // Định lượng của giấy ĐANG CHỌN trong form (khác giấy đã lưu khi người dùng vừa đổi). Đọc từ
  // danh mục chứ không đợi server: server có kéo `gsm` theo giấy, nhưng chỉ lúc LƯU.
  const giayGsm = giayRefs?.find((g) => g.id === form.qc.giay_id)?.gsm ?? null;
  const kpiToIn = kpiSo(d.so_to_ke_hoach, xemTruoc?.so_to_ke_hoach);
  const kpiToNguyen = kpiSo(d.so_to_nguyen, xemTruoc?.so_to_nguyen);
  const kpiCon = kpiSo(d.so_con, xemTruoc?.so_con);

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

          {canUpdate && d.trang_thai !== "san_sang" && (
            <Button variant="ghost" className="khsx-btn--danger" onClick={() => setAskDelete(true)}>
              <Icon name="trash" size={14} /> Xoá lệnh
            </Button>
          )}
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

      {/* Top Summary Bar - Top Bar ngang (Option 1) */}
      {/* Top Summary Bar - Hero Readiness Card 2 Tầng */}
      <div className="khsx-topbar">
        {/* Tầng 1: Trạng thái kiểm tra & Nút Hành động CTA chính */}
        <div className="khsx-topbar__header">
          <div className="khsx-topbar__status">
            {d.trang_thai === "san_sang" ? (
              <span className="khsx-topbar__tag khsx-topbar__tag--ok">
                <Icon name="check" size={14} /> Sẵn sàng lập kế hoạch
              </span>
            ) : d.thieu.length > 0 ? (
              <div className="khsx-topbar__pop-trigger">
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

            {d.canh_bao.length > 0 && (
              <span
                className="khsx-topbar__tag khsx-topbar__tag--info"
                title={d.canh_bao.map((c) => nhanMa(LSX_CANH_BAO_LABELS, c, dvChuoi)).join("; ")}
              >
                <Icon name="help" size={13} /> {d.canh_bao.length} lưu ý
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
          <div className="khsx-kpi-tile">
            <span className="khsx-kpi-tile__label">Bù hao</span>
            <span className="khsx-kpi-tile__val">
              {num(d.bu_hao_to)} <small>{dvTo}</small>
            </span>
          </div>

          <div
            className={`khsx-kpi-tile khsx-kpi-tile--hero${kpiToIn.tam ? " khsx-kpi-tile--tam" : ""}`}
            title={kpiToIn.tam ? "Số theo thông số đang sửa — chưa lưu" : undefined}
          >
            <span className="khsx-kpi-tile__label">Vào máy</span>
            <span className="khsx-kpi-tile__val">
              {num(kpiToIn.so)} <small>{dvTo}</small>
            </span>
          </div>

          <div
            className={`khsx-kpi-tile${kpiToNguyen.tam ? " khsx-kpi-tile--tam" : ""}`}
            title={kpiToNguyen.tam ? "Số theo thông số đang sửa — chưa lưu" : undefined}
          >
            <span className="khsx-kpi-tile__label">Giấy nguyên</span>
            <span className="khsx-kpi-tile__val">
              {num(kpiToNguyen.so)} <small>{dvToNguyen}</small>
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
              className={`khsx-kpi-tile${kpiCon.tam ? " khsx-kpi-tile--tam" : ""}`}
              title={
                kpiCon.tam
                  ? "Số theo thông số đang sửa — chưa lưu"
                  : dvTp && dvTo
                    ? `${num(kpiCon.so)} ${dvTp} trên 1 ${dvTo}`
                    : undefined
              }
            >
              <span className="khsx-kpi-tile__label">Bình bài</span>
              <span className="khsx-kpi-tile__val">
                {num(kpiCon.so)} <small>{dvTp}</small>
              </span>
            </div>
          )}

          <div className="khsx-kpi-tile">
            <span className="khsx-kpi-tile__label">Công đoạn</span>
            <span className="khsx-kpi-tile__val">{num(d.cong_doans.length)}</span>
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

      <div className="khsx-detail__grid">
        <div className="khsx-detail__main">
          <div className="khsx-tabs" role="tablist" aria-label="Nội dung lệnh sản xuất">
            {TABS.map((t) => (
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
              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="pencil" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Thông tin kế hoạch</h4>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-form">
                    <label className="khsx-field">
                      <span className="khsx-field__label">Tên lệnh</span>
                      <input value={form.ten} onChange={(e) => set("ten", e.target.value)} />
                    </label>
                    <label className="khsx-field">
                      <span className="khsx-field__label">Hạn hoàn thành sản xuất</span>
                      <input
                        type="date"
                        value={form.han_hoan_thanh_sx}
                        onChange={(e) => set("han_hoan_thanh_sx", e.target.value)}
                      />
                      {hanTre && (
                        <span className="khsx-field__warn">
                          Hạn sản xuất nên sớm hơn hạn giao khách ít nhất 1 ngày
                        </span>
                      )}
                    </label>
                    <label className={`khsx-field khsx-field--check ${form.is_rush ? "is-checked" : ""}`}>
                      <input
                        type="checkbox"
                        checked={form.is_rush}
                        onChange={(e) => set("is_rush", e.target.checked)}
                      />
                      <span>Hàng GẤP — ưu tiên ở xưởng</span>
                    </label>
                    {/* BỎ hai ô "Khuôn bế" và "Máy in dự kiến" (chủ 11/08/2026). Máy thật gán theo
                        TỪNG BƯỚC ở màn Xếp lịch công đoạn, khuôn cũng gắn với bước bế — khai ở cấp
                        lệnh chỉ là con số dự kiến nằm song song, sửa một nơi không kéo nơi kia. */}
                    <label className="khsx-field khsx-field--wide">
                      <span className="khsx-field__label">Ghi chú kế hoạch</span>
                      <textarea rows={3} value={form.ghi_chu} onChange={(e) => set("ghi_chu", e.target.value)} />
                    </label>
                  </div>
                </div>
              </div>

              <div className="khsx-spec__card">
                <div className="khsx-spec__card-head">
                  <div className="khsx-spec__card-icon">
                    <Icon name="fileCheck" size={16} />
                  </div>
                  <h4 className="khsx-spec__title">Đơn hàng &amp; Nhân sự phụ trách</h4>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-kvgrid">
                    <KV k="Đơn hàng" v={d.order_no ?? "—"} />
                    <KV k="Khách hàng" v={d.customer_name ?? "—"} />
                    <KV k="Sale phụ trách" v={d.sale_name ?? "—"} />
                    <KV k="Người phụ trách KH" v={d.nguoi_phu_trach_ten ?? "—"} />
                    <KV k="Hạn giao khách" v={ngay(d.han_giao_khach)} mono />
                    <KV k="Bàn giao lúc" v={ngayGio(d.ban_giao_at)} mono />
                    <KV k="Tạo lúc" v={ngayGio(d.created_at)} mono />
                    <KV k="Sửa lúc" v={ngayGio(d.updated_at)} mono />
                  </div>
                </div>
              </div>
            </section>
          )}

          {tab === "quycach" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-quycach" aria-labelledby="khsx-tab-quycach" tabIndex={0}>
              {qc.ghi_chu_ky_thuat ? (
                <div className="khsx-spec__note">
                  <Icon name="bell" size={16} />
                  <div>
                    <strong className="khsx-spec__note-title">LƯU Ý SẢN XUẤT / GHI CHÚ KỸ THUẬT</strong>
                    <span className="khsx-spec__note-content">{String(qc.ghi_chu_ky_thuat)}</span>
                  </div>
                </div>
              ) : null}
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
                  {/* Ảnh chụp từ phiếu, nhưng SỬA ĐƯỢC tại chỗ — kế hoạch khỏi phải quay về phiếu
                      rồi tạo lại lệnh (tạo lại là mất sạch routing đã chỉnh). Lệnh vẫn KHÔNG tự
                      bám theo phiếu. Nói rõ ở nhãn vì ngay khối dưới là số máy tự tính, không sửa
                      được — bày lẫn lộn rồi số tự nhảy thì người dùng tưởng máy hỏng. */}
                  <span className="khsx-spec__hint">thông số — sửa được</span>
                </div>
                <div className="khsx-spec__card-body">
                  <div className="khsx-kvgrid">
                    {/* GIẤY SỬA ĐƯỢC tại lệnh (13/08/2026). Trước đây là chữ chết, trong khi mọi ô
                        khác trong khối này đều sửa được và nhãn khối ghi "thông số — sửa được".
                        Nghiệp vụ: giấy hết hàng thì xưởng thay loại khác cùng tính chất (có khi
                        xịn hơn) — bắt quay về phiếu tính giá tạo lại lệnh là mất sạch routing đã
                        chỉnh. Backend vốn đã nhận `giay_id` và tự kéo `gsm` + tên theo giấy mới
                        (`lsx_service.ap_quy_cach`); chỗ này chỉ thiếu ô chọn.
                        Danh mục chưa nạp xong ⇒ vẫn hiện tên đã lưu, không để ô trống. */}
                    {giayRefs ? (
                      <label className={`khsx-kv ${canUpdate ? "khsx-kv--edit" : ""}`}>
                        <span className="khsx-kv__key">Giấy</span>
                        <select
                          className="khsx-kv__input"
                          disabled={!canUpdate}
                          value={form.qc.giay_id ?? ""}
                          onChange={(e) =>
                            setQc({ giay_id: e.target.value ? Number(e.target.value) : null })
                          }
                        >
                          <option value="">— chưa chọn giấy —</option>
                          {giayRefs.map((g) => (
                            <option key={g.id} value={g.id}>
                              {g.ten}{g.gsm ? ` · ${g.gsm} gsm` : ""}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <KV k="Giấy" v={s("giay_ten")} />
                    )}
                    {/* Định lượng đi THEO giấy: đổi giấy là số này đổi ngay, khỏi chờ bấm Lưu —
                        không thì màn hiện giấy mới cạnh gsm của cuộn giấy cũ. Chưa chọn được
                        trong danh mục thì rơi về số đã lưu. */}
                    <KV
                      k="Định lượng (gsm)"
                      v={
                        giayGsm != null
                          ? num(giayGsm)
                          : qc.gsm
                            ? num(n("gsm"))
                            : "—"
                      }
                      mono
                    />
                    {/* GỠ 2026-08-09 (Đợt 4 · K): dòng "Nguồn giấy". Công ty luôn cấp giấy nên
                        dòng này chỉ còn là một ô luôn ghi "Công ty" — chiếm chỗ, không nói gì. */}
                    <KVNum k="Khổ giấy nguyên dài" suffix="mm" disabled={!canUpdate}
                      v={form.qc.kho_nguyen_dai} onChange={(x) => setQc({ kho_nguyen_dai: x })} />
                    <KVNum k="Khổ giấy nguyên rộng" suffix="mm" disabled={!canUpdate}
                      v={form.qc.kho_nguyen_rong} onChange={(x) => setQc({ kho_nguyen_rong: x })} />
                    <KVNum k={`Khổ ${dvTo} dài`} suffix="mm" disabled={!canUpdate}
                      v={form.qc.kho_in_dai} onChange={(x) => setQc({ kho_in_dai: x })} />
                    <KVNum k={`Khổ ${dvTo} rộng`} suffix="mm" disabled={!canUpdate}
                      v={form.qc.kho_in_rong} onChange={(x) => setQc({ kho_in_rong: x })} />
                    {/* 0 × 0 = CHƯA khai khổ tờ in — engine chạy thẳng trên khổ giấy nguyên. Nói
                        ra chứ để hai số 0 trần thì trông như thiếu dữ liệu. */}
                    {!((form.qc.kho_in_dai ?? 0) > 0 && (form.qc.kho_in_rong ?? 0) > 0) && (
                      <p className="khsx-nhom__sub khsx-kv--span">
                        Để 0 × 0 = in thẳng khổ giấy nguyên, không xả.
                      </p>
                    )}
                    <KVNum k="Khổ thành phẩm dài" suffix="mm" disabled={!canUpdate}
                      v={form.qc.dai_thanh_pham} onChange={(x) => setQc({ dai_thanh_pham: x })} />
                    <KVNum k="Khổ thành phẩm rộng" suffix="mm" disabled={!canUpdate}
                      v={form.qc.rong_thanh_pham} onChange={(x) => setQc({ rong_thanh_pham: x })} />
                    <label className={`khsx-kv ${canUpdate ? "khsx-kv--edit" : ""}`}>
                      <span className="khsx-kv__key">Cách in</span>
                      <select
                        className="khsx-kv__input"
                        disabled={!canUpdate}
                        value={form.qc.quy_cach_in ?? "mot_mat"}
                        onChange={(e) => setQc({ quy_cach_in: e.target.value })}
                      >
                        <option value="mot_mat">1 mặt</option>
                        <option value="hai_mat">2 mặt (AB)</option>
                        <option value="tu_tro">Tự trở</option>
                        <option value="tro_nhip">Trở nhíp</option>
                      </select>
                    </label>
                    {/* Hai ô này CHỈ có nghĩa với hàng NHIỀU TRANG. Thẻ, tờ rơi, hộp thì cả hai
                        luôn là 1/1 — bày ra chỉ tổ chiếm chỗ và mời người ta gõ một số vô nghĩa.
                        Cấu trúc sản phẩm (mấy trang) là việc của bài TÍNH GIÁ, không phải của kế
                        hoạch: muốn biến một tờ rời thành sách thì sửa ở phiếu rồi tạo lại lệnh. */}
                    {(form.qc.so_trang ?? 1) > 1 && (
                      <>
                        <KVNum k="Số trang" disabled={!canUpdate}
                          v={form.qc.so_trang} onChange={(x) => setQc({ so_trang: Math.max(1, x) })} />
                        <KVNum k="Trang mỗi tay" disabled={!canUpdate}
                          v={form.qc.trang_moi_tay} onChange={(x) => setQc({ trang_moi_tay: Math.max(1, x) })} />
                      </>
                    )}
                    <KVNum k="Bleed" suffix="mm" disabled={!canUpdate}
                      v={form.qc.bleed_mm} onChange={(x) => setQc({ bleed_mm: x })} />
                    <KVNum k="Khe cắt" suffix="mm" disabled={!canUpdate}
                      v={form.qc.khe_cat_mm} onChange={(x) => setQc({ khe_cat_mm: x })} />
                    {/* Mực KHÔNG nhét vào lưới key-value: nó là tập mã, cần chip bấm. Dùng lại
                        đúng khối đã dựng ở phiếu tính giá, không đẻ khối thứ hai rồi hai bên lệch. */}
                    <div className="khsx-kv khsx-kv--span">
                      <span className="khsx-kv__key">Mực in</span>
                      <MucInHang
                        mucA={form.qc.muc_a ?? []}
                        mucB={form.qc.muc_b ?? []}
                        quyCachIn={form.qc.quy_cach_in ?? "mot_mat"}
                        disabled={!canUpdate}
                        onChange={(a, b) => setQc({ muc_a: a, muc_b: b })}
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
                    {/* Con/tờ là NGUYÊN NHÂN với hàng cắt rời: xưởng ép số con khác bài tính giá là
                        chuyện thường, đổi xong server chạy lại cả chuỗi ngược.
                        Với SÁCH GẤP TAY thì KHOÁ: tờ in gấp nguyên vẹn thành một tay, giấy tính
                        theo `1/so_tay`, `con` bị `cau_to_sang_cai` loại hoàn toàn. Để ô mở là mời
                        người dùng gõ một số rồi bấm lưu mà không có gì đổi — lừa người dùng. */}
                    <label
                      className={`khsx-kv ${laSach ? "" : "khsx-kv--edit"}`}
                      title={giaiThichSach}
                    >
                      {/* Nhãn NGẮN, tỉ số để trong tooltip: nhét "· SẢN PHẨM XONG mỗi TỜ CHẠY MÁY"
                          vào nhãn thì ô đầu tiên cao gấp đôi mấy ô cạnh nó, cả lưới lệch. */}
                      <span
                        className="khsx-kv__key"
                        title={dvTp && dvTo ? `Số ${dvTp} trên 1 ${dvTo}` : undefined}
                      >
                        Bình bài
                      </span>
                      <input
                        className="khsx-kv__input"
                        type="number"
                        min={1}
                        disabled={!canUpdate || laSach}
                        value={xemTruoc && !laSach ? String(xemTruoc.so_con) : form.so_con}
                        onChange={(e) => set("so_con", e.target.value)}
                      />
                    </label>
                    {laSach && (
                      <p className="khsx-nhom__sub khsx-kv--span">{giaiThichSach}</p>
                    )}
                    <KVDeriv k="Số mảnh xả" cu={n("so_manh_xa")} moi={xemTruoc?.so_manh_xa} />
                    <KVDeriv k="Số kẽm" cu={n("so_kem")} moi={xemTruoc?.so_kem} />
                    <KVDeriv k="Số lượt in" cu={n("so_luot")} moi={xemTruoc?.so_luot} />
                    {/* NHÃN nói CHẶNG, ĐƠN VỊ đi với con số — cùng luật với thanh KPI. Trước đây
                        nhãn lấy thẳng tên đơn vị nên lệnh KHÔNG có bước xả (tờ nguyên = tờ in) đẻ
                        ra hai dòng "SỐ TỜ CHẠY MÁY KẾ HOẠCH" và "SỐ TỜ CHẠY MÁY" cùng một con số —
                        nhìn như một chỗ bị lặp, trong khi chúng là hai chặng khác nhau. */}
                    <KVDeriv k="Vào máy" dv={dvTo} cu={d.so_to_ke_hoach} moi={xemTruoc?.so_to_ke_hoach} />
                    <KVDeriv k="Giấy nguyên" dv={dvToNguyen} cu={d.so_to_nguyen} moi={xemTruoc?.so_to_nguyen} />
                    <KVDeriv
                      k="Số bài in"
                      dv={dvTay}
                      cu={n("so_to_per_sp") || 1}
                      moi={xemTruoc?.so_to_per_sp}
                    />
                    <KV
                      k="Cách bình"
                      v={co("con_auto") ? (qc.con_auto === false ? "Ép số con" : "Máy tự bình") : "—"}
                      badge
                    />
                  </div>
                  {/* Ngả 1 vẫn ĐÈ số gõ tay — nhưng đè có báo trước, không lén. */}
                  {xemTruoc && xemTruoc.doi.length > 0 && (
                    <p className="khsx-spec__canhbao">
                      Đổi {xemTruoc.doi.length} thông số — các số trên sẽ ghi đè khi bấm Lưu.
                    </p>
                  )}
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
                      soCon={xemTruoc?.so_con ?? n("so_con")}
                      trangMoiTay={form.qc.trang_moi_tay ?? 1}
                      dvCon={dvTp}
                      dvTo={dvTo}
                    />
                  </div>
                </div>
              )}

            </section>
          )}

          {tab === "routing" && (
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
                    buHaoThem={d.bu_hao_to}
                    leadTime={d.lead_time}
                    baiGhep={d.bai_ghep}
                    congDoanRefs={congDoanRefs}
                    toRefs={toRefs}
                    mayRefs={mayRefs}
                    khuonRefs={khuonRefs}
                    vatTuRefs={vatTuRefs}
                    phuThuocRefs={phuThuocRefs}
                    canUpdate={canUpdate}
                    saving={savingRouting}
                    onSave={luuRouting}
                    onPatchLsx={patchLsx}
                    onMacDinhBuoc={macDinhBuoc}
                    onDauViecOptions={dauViecOptions}
                    onGiaoNhan={ghiGiaoNhan}
                    onDirtyChange={setRoutingDirty}
                    dvChuoi={dvChuoi}
                  />
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
    </div>
  );
}

/** Ô THÔNG SỐ gõ số — cùng khuôn `khsx-kv--edit` mà ô "Con / tờ" đang dùng. */
function KVNum({
  k, v, onChange, disabled, suffix,
}: {
  k: string;
  v: number | undefined;
  onChange: (n: number) => void;
  disabled?: boolean;
  suffix?: string;
}) {
  return (
    <label className={`khsx-kv ${disabled ? "" : "khsx-kv--edit"}`}>
      <span className="khsx-kv__key">{k}{suffix ? ` (${suffix})` : ""}</span>
      <input
        className="khsx-kv__input"
        type="number"
        min={0}
        disabled={disabled}
        value={v ?? 0}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
      />
    </label>
  );
}

/** Số MÁY TỰ TÍNH. Đổi thì hiện số cũ gạch ngang bên cạnh — thấy hệ quả TRƯỚC khi bấm Lưu,
 *  đúng nguyên tắc "thay đổi gì là thay trên UI luôn, nhấn lưu mới vào DB". */
function KVDeriv(
  { k, cu, moi, dv }: { k: string; cu: number; moi: number | undefined; dv?: string },
) {
  const doi = moi != null && moi !== cu;
  return (
    <div className="khsx-kv khsx-kv--deriv">
      <span className="khsx-kv__key">{k}</span>
      <span className="khsx-kv__val khsx-num">
        {doi && <s className="khsx-kv__cu">{cu.toLocaleString("vi-VN")}</s>}
        {(doi ? (moi as number) : cu).toLocaleString("vi-VN")}
        {/* ĐƠN VỊ đi với con số, không nằm trong nhãn — nhãn để dành nói CHẶNG. Rỗng thì không
            hiện gì: routing chưa nói tới chặng đó, bịa một chữ vào đây là quay lại lối cũ. */}
        {dv ? <small className="khsx-unit">{dv}</small> : null}
        {doi && <span className="khsx-kv__moi">tính lại</span>}
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
