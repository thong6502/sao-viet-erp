// Drawer CHI TIẾT một LƯỢT CHẠY CHUNG của bài ghép — cùng khuôn với drawer bước lệnh
// (`LsxBuocDrawer`): head + capsule tabs + section card.
//
// Vì sao viết lại (18/08/2026): bản cũ là form phẳng thừa kế từ màn `BaiGhepSoDo` đã xoá, đeo khuôn
// `.bgsd-*` trong khi bước lệnh đã sang khuôn `.khsx-*` nhiều tab. Cùng MỘT việc (khai kế hoạch cho
// một bước) mà hai màn hai kiểu thì người dùng phải học hai lần — và bản cũ chôn mất một loạt số
// server đã gửi sẵn: hao %, hệ số quy đổi, cảnh báo đứt chuỗi đơn vị, bóc tách thời lượng, tiền
// khoán, gợi ý định mức vật tư.
//
// KHÔNG dựng thẳng `LsxBuocDrawer`: hợp đồng dữ liệu khác hẳn — bước chung là MỘT lần lên máy cho N
// lệnh, nên số lượng · hao · thời lượng là DẪN XUẤT (engine tính lúc đọc, không có ô sửa), có
// `thanh_vien[]` + nút "Tách lượt chung", không có khuôn dao, không có DAG riêng (DAG ở tầng bài).
// Thứ kế thừa được là NGÔN NGỮ THIẾT KẾ, không phải component.
//
// Form tự nạp `ke-hoach-sx.css` (khuôn `.khsx-*`) và `bai-ghep.css` (danh sách ghi chú của lệnh) để
// style đi theo component chứ không đi theo trang nào.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { LSX_LOAI_BUOC_META, type BaiGhepBuocChungBody, type BaiGhepSoDo } from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { TagPicker } from "../components/TagPicker";
import { num } from "./keHoachSxShared";
import { heSoChu, nhanDonVi, phut, thoiLuongLive, type MayTinhGio } from "./lsxBuoc";
import "./ke-hoach-sx.css";
import "./bai-ghep.css";

type TabKey = "cau_hinh" | "phan_cong" | "vat_tu" | "tien_do" | "gia_cong" | "cac_lenh";

/** Máy đọc từ danh mục: nhóm để lọc + ba tốc độ và chuẩn bị để tính lại giờ NGAY khi đổi máy,
 *  không đợi lưu (`thoiLuongLive` dùng đúng bộ số này ở bước lệnh). */
interface MayRef extends MayTinhGio {
  id: number;
  ten: string;
  loaiMay: string | null;
}

/** Lập kế hoạch cho MỘT lượt chạy chung.
 *
 * Chỉ mở những ô NGƯỜI nhập: tổ · máy · số người · số lượt · thời gian khác · năng suất (bước tổ) ·
 * khoán · vật tư · ghi chú · gia công ngoài. Số lượng / hao / thời lượng KHÔNG có ô sửa — chúng là
 * dẫn xuất, engine tính lúc đọc; cho sửa là đẻ nguồn sự thật thứ hai.
 */
export function BuocChungForm({
  g,
  canUpdate,
  onLuu,
  onTach,
  index,
  tong,
  onPrev,
  onNext,
  onClose,
  banner,
}: {
  g: BaiGhepSoDo["gop"][number];
  canUpdate: boolean;
  onLuu: (body: BaiGhepBuocChungBody) => Promise<unknown>;
  onTach: () => Promise<unknown>;
  /** Vị trí trong danh sách bước chung của bài — có thì head hiện "BƯỚC CHUNG 02/03" + nút ← →. */
  index?: number;
  tong?: number;
  onPrev?: () => void;
  onNext?: () => void;
  onClose?: () => void;
  /** Băng thông báo của trang (lỗi lưu, "bước vừa gộp chưa có cấu hình") — nằm ngay dưới thanh tab. */
  banner?: ReactNode;
}) {
  const { token } = useAuth();
  const [toRefs, setToRefs] = useState<{ id: number; ten: string }[] | null>(null);
  const [mayRefs, setMayRefs] = useState<MayRef[] | null>(null);
  const [vtRefs, setVtRefs] = useState<{ id: number; ma: string; ten: string; donVi: string }[] | null>(null);
  const [f, setF] = useState<BaiGhepBuocChungBody>({});
  // Chuỗi đang gõ của ô định mức vật tư. Body gửi lên là SỐ, nhưng gõ "0.35" phải đi qua "0." —
  // ép về số ngay từng phím thì "0." thành 0 và con trỏ nhảy về đầu.
  const [vtGo, setVtGo] = useState<Record<number, string>>({});
  const [tab, setTab] = useState<TabKey>("cau_hinh");
  const [dangLuu, setDangLuu] = useState(false);
  const [confirmTach, setConfirmTach] = useState(false);

  useEffect(() => {
    if (!token) return;
    crud("/api/cong-doan/phong-ban").list(token)
      .then((r) => setToRefs(r.items.map((t) => ({ id: t.id, ten: String(t.ten) }))))
      .catch(() => setToRefs(null));
    crud("/api/may-thiet-bi").list(token)
      .then((r) => setMayRefs(r.items.map((m) => {
        const khoan = (m.fields_theo_loai as { chuan_bi_khoan?: { ten?: string; phut?: number }[] } | null)
          ?.chuan_bi_khoan;
        return {
          id: m.id,
          ten: String(m.ten),
          loaiMay: (m as { loai_may?: string | null }).loai_may ?? null,
          tocDo: m.toc_do == null ? null : Number(m.toc_do),
          tocDoMin: m.toc_do_min == null ? null : Number(m.toc_do_min),
          tocDoMax: m.toc_do_max == null ? null : Number(m.toc_do_max),
          donViTocDo: m.don_vi_toc_do ? String(m.don_vi_toc_do) : null,
          chuanBiPhut: m.makeready_time_default == null ? null : Number(m.makeready_time_default),
          chuanBiKhoan: Array.isArray(khoan) ? khoan : [],
        };
      })))
      .catch(() => setMayRefs(null));
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true })
      .then((r) => setVtRefs(r.items.map((v) => ({
        id: v.id, ma: String(v.ma), ten: String(v.ten), donVi: String(v.don_vi_gia ?? ""),
      }))))
      .catch(() => setVtRefs(null));
  }, [token]);

  // Đổi form về `{}` khi chuyển sang bước chung khác — không thì số vừa gõ cho bước này rơi sang
  // bước kia lúc bấm Lưu. Tab cũng về đầu: bước mới là câu chuyện mới.
  useEffect(() => {
    setF({});
    setVtGo({});
    setTab("cau_hinh");
  }, [g.step_key]);

  /** Giá trị đang hiển thị: ưu tiên thứ người vừa gõ, chưa gõ thì lấy thứ server đang giữ. */
  const val = <K extends keyof BaiGhepBuocChungBody>(k: K, hienCo: BaiGhepBuocChungBody[K]) =>
    (f[k] !== undefined ? f[k] : hienCo);

  const meta = LSX_LOAI_BUOC_META[g.loai_buoc];
  const ngoai = g.loai_buoc === "thue_ngoai";
  const dvVao = nhanDonVi(g.don_vi_vao);
  const dvRa = nhanDonVi(g.don_vi_ra);

  /** Đầu việc đang GHIM có thể không còn trong bảng khoán của tổ (đổi tổ, hoặc dòng bị ngừng) —
   *  vẫn phải bày ra, không thì `<select>` rơi về "— chọn —" và người dùng tưởng chưa ai chọn. */
  const dsKhoan = (() => {
    const ds = [...g.khoan_chon_duoc];
    if (g.khoan_rate_id != null && !ds.some((k) => k.id === g.khoan_rate_id)) {
      ds.unshift({
        id: g.khoan_rate_id,
        ten: g.khoan_ten ?? `(đang ghim) đầu việc #${g.khoan_rate_id}`,
        don_vi: g.khoan_don_vi ?? "",
        don_gia: g.khoan_don_gia ?? 0,
      });
    }
    return ds;
  })();

  // "Nhảy tiền" khi đổi đầu việc: server đã tính sẵn tiền công của TỪNG lựa chọn cho đúng bước này
  // (`tien_du_kien`), nên chọn ở dropdown là ra số ngay — khỏi Lưu trước. Chỉ áp khi CHƯA đổi tổ:
  // đổi tổ thì cả danh sách đầu việc + tiền kèm theo thuộc tổ CŨ, phải Lưu để backend chấm lại.
  const doiTo = f.department_id !== undefined;
  const selId = val("piece_rate_id", g.khoan_rate_id);
  const optLive =
    !doiTo && selId != null
      ? dsKhoan.find((k) => k.id === selId && "tien_du_kien" in k)
      : undefined;
  const tienLive = optLive?.tien_du_kien ?? null;
  const slLive = optLive?.sl_du_kien ?? null;
  const dvSlLive = optLive?.don_vi_sl_du_kien ?? null;
  const dienGiaiLive = optLive?.dien_giai_du_kien ?? null;
  // Số bày ở dải KPI: ưu tiên bản live; nếu KHÔNG đổi gì thì giữ số server đã lưu; đổi (đổi tổ, hoặc
  // xoá lựa chọn / ghim dòng đã ngừng) mà chưa có bản live thì ẩn đi — đừng để số cũ đánh lừa.
  const chuaDoiKhoan = !doiTo && f.piece_rate_id === undefined;
  const tienHien = optLive ? tienLive : chuaDoiKhoan ? g.khoan_tien : null;
  const slHien = optLive ? slLive : chuaDoiKhoan ? g.khoan_sl : null;
  const dvSlHien = optLive ? dvSlLive : g.khoan_don_vi_sl;

  // Vật tư sửa theo LÔ: giữ nguyên danh sách hiện có rồi thay cả cụm khi lưu (API là replace-all).
  const vtHienTai = (f.vat_tus ?? g.vat_tus.map((v) => ({ vat_tu_id: v.vat_tu_id, so_luong: v.so_luong })));
  const datVatTu = (rows: { vat_tu_id: number; so_luong: number }[]) => setF({ ...f, vat_tus: rows });

  // Bung vật tư của đầu việc khoán vào danh sách — như bước lệnh. Model bước chung không mang cờ
  // `tu_dong` nên gộp theo `vat_tu_id`: CHỈ thêm mã chưa có, không đè số người đã khai tay.
  const bungVatTu = (
    chon: { vat_tus?: { vat_tu_id: number; so_luong: number }[] } | undefined,
    goc: { vat_tu_id: number; so_luong: number }[],
  ) => {
    const moi = (chon?.vat_tus ?? [])
      .filter((v) => !goc.some((b) => b.vat_tu_id === v.vat_tu_id))
      .map((v) => ({ vat_tu_id: v.vat_tu_id, so_luong: v.so_luong }));
    return [...goc, ...moi];
  };

  // Đầu việc khoán ĐÃ GHIM sẵn (công đoạn chỉ có một đầu việc → server tự chọn) mà chưa có vật tư:
  // bung vật tư của nó ngay khi mở, y như bước lệnh. Người dùng chưa đụng vật tư (f.vat_tus rỗng) và
  // bước chưa lưu vật tư nào (g.vat_tus rỗng) mới bung — không đè lên thứ họ đang sửa / đã chốt.
  useEffect(() => {
    if (!canUpdate || g.khoan_rate_id == null || f.vat_tus !== undefined || g.vat_tus.length > 0) return;
    const chon = dsKhoan.find((x) => x.id === g.khoan_rate_id);
    if (!chon?.vat_tus?.length) return;
    datVatTu(bungVatTu(chon, vtHienTai));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g.step_key, g.khoan_rate_id, dsKhoan]);

  const mayId = val("may_id", g.may_id) ?? null;
  const mayDaChon = (mayRefs ?? []).find((m) => m.id === mayId) ?? null;
  // Nhân lực: số BỐ TRÍ so với biên của bước. Cảnh báo ngay tại chỗ khai, đừng đợi tới bàn xếp
  // lịch — tới đó mới biết thì bài đã lập kế hoạch, sửa lại tốn một vòng.
  const boTri = Math.max(1, Math.trunc(Number(val("so_nhan_cong", g.so_nhan_cong) ?? 1)) || 1);
  const bienMin = val("so_nhan_cong_toi_thieu", g.so_nhan_cong_toi_thieu) ?? null;
  const bienMax = val("so_nhan_cong_toi_da", g.so_nhan_cong_toi_da) ?? null;
  const bienTc = val("so_nhan_cong_tieu_chuan", g.so_nhan_cong_tieu_chuan) ?? 1;
  const ngoaiBien =
    (bienMin != null && boTri < bienMin) || (bienMax != null && boTri > bienMax);
  const bienText = `${bienMin ?? "–"}–${bienMax ?? "–"}`;

  // Thời lượng tính LẠI TẠI CHỖ bằng đúng công thức của bước lệnh: đổi máy / số lượt / thời gian
  // khác là bảng bóc tách nhảy ngay, không phải lưu rồi mở lại mới thấy. Chưa nạp xong danh mục máy
  // ⇒ `mayDaChon` null ⇒ rơi về diễn giải server đã trả.
  const tg = useMemo(
    () => thoiLuongLive(
      {
        loai_buoc: g.loai_buoc,
        so_luot_chay: String(val("so_luot_chay", g.so_luot_chay) ?? 1),
        so_nhan_cong: String(val("so_nhan_cong", g.so_nhan_cong) ?? 1),
        // Thời lượng chia theo số người TIÊU CHUẨN (xem `thoi_luong_buoc` ở backend), không theo
        // số bố trí. Trước đây chỗ này mượn tạm `so_nhan_cong` làm tiêu chuẩn vì form chưa có biên
        // — hai bên lệch nhau ngay khi bố trí ≠ tiêu chuẩn, xem-trước ra một số, lưu xong ra số khác.
        so_nhan_cong_toi_da: val("so_nhan_cong_toi_da", g.so_nhan_cong_toi_da) ?? null,
        so_nhan_cong_tieu_chuan: Number(
          val("so_nhan_cong_tieu_chuan", g.so_nhan_cong_tieu_chuan) || 1,
        ),
        nang_suat: String(val("nang_suat", g.nang_suat) ?? ""),
        phat_sinh_phut: String(val("phat_sinh_phut", g.phat_sinh_phut) ?? 0),
        thoi_luong_dien_giai: g.thoi_luong_dien_giai,
        don_vi_vao: g.don_vi_vao ?? "",
        so_luong_vao: String(g.so_luong_vao),
      },
      mayDaChon,
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [g, f.so_luot_chay, f.so_nhan_cong, f.so_nhan_cong_tieu_chuan, f.so_nhan_cong_toi_da,
     f.nang_suat, f.phat_sinh_phut, mayDaChon],
  );

  const setup = Number(tg.setup_phut ?? 0);
  const phatSinh = Number(tg.phat_sinh_phut ?? 0);
  const chayTB = Number(tg.chay_phut ?? 0);
  const chiemTB = Number(tg.chiem_tai_nguyen_phut ?? 0);
  const chiemMin = phatSinh + setup + Number(tg.chay_phut_min ?? chayTB);
  const chiemMax = phatSinh + setup + Number(tg.chay_phut_max ?? chayTB);
  const coDai = Boolean(tg.co_dai_toc_do);
  const khoanChuanBi: { ten?: string; phut?: number }[] = Array.isArray(tg.chuan_bi_khoan)
    ? (tg.chuan_bi_khoan as { ten?: string; phut?: number }[])
    : [];
  const canhBaoGio = Array.isArray(tg.canh_bao) ? (tg.canh_bao as unknown[]) : [];

  const tabsList: { key: TabKey; label: string; badge?: number }[] = [
    { key: "cau_hinh", label: "Cấu hình & Số lượng" },
    { key: "phan_cong", label: "Phân công & Thiết bị" },
    { key: "vat_tu", label: "Vật tư", badge: vtHienTai.length },
    { key: "tien_do", label: "Tiến độ & Thời gian" },
    ...(ngoai ? [{ key: "gia_cong" as TabKey, label: "Gia công ngoài" }] : []),
    { key: "cac_lenh", label: "Các lệnh trên tờ", badge: g.thanh_vien.length },
  ];

  const dirty = Object.keys(f).length > 0;
  const luu = async () => {
    setDangLuu(true);
    try {
      const saved = await onLuu(f);
      // Trang trả `false` khi API từ chối nhưng đã đưa lỗi lên banner — giữ nguyên draft để người
      // lập kế hoạch sửa tiếp, đừng xoá thứ họ vừa gõ.
      if (saved !== false) {
        setF({});
        setVtGo({});
      }
    } finally {
      setDangLuu(false);
    }
  };

  return (
    <>
      <header className="khsx-drawer__head">
        <div className={`khsx-drawer__accent khsx-drawer__accent--${g.loai_buoc}`} />

        <div className="khsx-drawer__head-main">
          <div className="khsx-drawer__head-info">
            <div className="khsx-drawer__head-meta">
              <span className="khsx-step-kicker">
                BƯỚC CHUNG
                {index != null && tong != null
                  ? ` ${String(index + 1).padStart(2, "0")}/${String(tong).padStart(2, "0")}`
                  : ""}
              </span>
              <span className="khsx-dot-sep">·</span>
              <span className={`khsx-type-tag khsx-type-tag--${g.loai_buoc}`}>{meta.label}</span>
              <span className="khsx-dot-sep">·</span>
              <span className="khsx-tag-subtle">
                {g.thanh_vien.length} lệnh chạy chung{g.ma_bai_ghep ? ` · ${g.ma_bai_ghep}` : ""}
              </span>
            </div>
            <h2 className="khsx-drawer__title-main">{g.ten || "Bước chung chưa đặt tên"}</h2>
          </div>

          <div className="khsx-drawer__head-actions">
            {(onPrev || onNext) && (
              <div className="khsx-nav-group" role="group" aria-label="Điều hướng bước chung">
                <button
                  type="button" className="khsx-nav-btn" onClick={onPrev}
                  disabled={!onPrev || index === 0} aria-label="Bước chung trước" title="Bước chung trước"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                </button>
                <button
                  type="button" className="khsx-nav-btn" onClick={onNext}
                  disabled={!onNext || (index != null && tong != null && index >= tong - 1)}
                  aria-label="Bước chung sau" title="Bước chung sau"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
              </div>
            )}
            {onClose && (
              <button type="button" className="khsx-close-btn" onClick={onClose} aria-label="Đóng panel" title="Đóng (Esc)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>

        <nav className="khsx-tabs-bar" aria-label="Phân đoạn nội dung">
          {tabsList.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`khsx-tab-btn ${tab === t.key ? "is-active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              <span className="khsx-tab-label">{t.label}</span>
              {t.badge != null && t.badge > 0 && <span className="khsx-tab-badge">{t.badge}</span>}
            </button>
          ))}
        </nav>
      </header>

      {banner}

      <div className="khsx-drawer__body">
        {/* ================= TAB 1: CẤU HÌNH & SỐ LƯỢNG (toàn số DẪN XUẤT) ================= */}
        {tab === "cau_hinh" && (
          <div className="khsx-tab-pane">
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <div>
                  <h3 className="khsx-section-card__title">Dòng chảy số lượng & hao hụt</h3>
                  <p className="khsx-section-card__sub">
                    Số của CẢ LƯỢT — engine tính lúc đọc, không có ô sửa tay.
                  </p>
                </div>
              </div>

              {g.loi_quy_doi ? (
                <div className="khsx-note-banner khsx-note-banner--error">
                  <span className="khsx-note-icon">⚠</span>
                  <span>
                    <strong>Chưa tính được số vào.</strong> {g.loi_quy_doi}{" "}
                    Khai cầu quy đổi ở module <strong>Đơn vị &amp; quy đổi</strong> rồi mở lại bước —
                    không có cầu thì bài không phát hành được.
                  </span>
                </div>
              ) : !g.tren_giay ? (
                <div className="khsx-note-banner">
                  <span>
                    Bước này <strong>không nằm trên dòng giấy</strong> (chung bản/kẽm cho cả bài) nên
                    số ra là số bản/kẽm tính từ quy cách tờ ghép, không đếm theo số tờ chạy máy.
                  </span>
                </div>
              ) : null}

              {g.canh_bao_don_vi.map((c) => (
                <div className="khsx-note-banner khsx-note-banner--warn" key={c}>
                  <span>{c}</span>
                </div>
              ))}

              {/* SỐ RA đến từ đâu — công thức sản lượng của công đoạn (chỉ bước ngoài dòng giấy). Với
                  bước ngoài dòng, RA là gốc (số kẽm/bản) còn VÀO suy ngược từ nó. */}
              {g.san_luong_dien_giai && (
                <div className="khsx-flow-formula">
                  <span className="khsx-flow-formula__label">Số ra =</span>
                  <span className="khsx-flow-formula__expr">{g.san_luong_dien_giai}</span>
                </div>
              )}

              <div className="khsx-flow-pipeline">
                <div className="khsx-flow-node khsx-flow-node--in">
                  <span className="khsx-flow-node__kicker">SỐ LƯỢNG VÀO</span>
                  <div className="khsx-flow-node__val-row">
                    <span className="khsx-flow-node__val">{num(g.so_luong_vao)}</span>
                    <span className="khsx-unit-pill">{dvVao}</span>
                  </div>
                  <span className="khsx-flow-node__hint">Cộng của {g.thanh_vien.length} lệnh trên tờ</span>
                </div>

                <div className="khsx-flow-connector">
                  <div className="khsx-flow-arrow-line">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M5 12h14M13 6l6 6-6 6" />
                    </svg>
                  </div>
                  <div className="khsx-flow-badges-stack">
                    {/* Hao đếm ĐÚNG MỘT LẦN cho cả lượt — chỗ hay bị hiểu nhầm nhất: một lần lên máy
                        thì bù hao một bộ, không phải mỗi lệnh một bộ. */}
                    <div className="khsx-flow-chip khsx-flow-chip--waste">
                      <span className="khsx-flow-chip__label">Hao (một lần):</span>
                      <span className="khsx-flow-chip__val">
                        {g.hao_hut > 0 || g.hao_hut_pct > 0 ? (
                          <>
                            <strong>{num(g.hao_hut)}</strong> {dvVao}
                            {g.hao_hut_pct > 0 && ` (+${num(g.hao_hut_pct)}%)`}
                          </>
                        ) : "—"}
                      </span>
                    </div>
                    {heSoChu(g.he_so_quy_doi, g.don_vi_vao, g.don_vi_ra) && (
                      <div className="khsx-flow-chip khsx-flow-chip--ratio">
                        <span className="khsx-flow-chip__label">Quy đổi:</span>
                        <span className="khsx-flow-chip__val">
                          <strong>{heSoChu(g.he_so_quy_doi, g.don_vi_vao, g.don_vi_ra)}</strong>
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="khsx-flow-node khsx-flow-node--out">
                  <div className="khsx-flow-node__head">
                    <span className="khsx-flow-node__kicker">SỐ LƯỢNG RA</span>
                  </div>
                  <div className="khsx-flow-node__val-row">
                    <span className="khsx-flow-node__val">{num(g.so_luong_ra)}</span>
                    <span className="khsx-unit-pill">{dvRa}</span>
                  </div>
                  <span className="khsx-flow-node__hint">
                    {g.so_luong_ra_quy != null && g.don_vi_ra !== g.don_vi_vao
                      ? `≈ ${num(g.so_luong_ra_quy)} ${dvVao} theo đơn vị vào`
                      : "Chia lại cho từng lệnh sau bước này"}
                  </span>
                </div>
              </div>
            </section>

            {g.thieu.length > 0 && (
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Còn thiếu để chạy được</h3>
                  <span className="khsx-badge-count">{g.thieu.length}</span>
                </div>
                {g.thieu.map((t) => (
                  <div className="khsx-alert" key={t}>{t}</div>
                ))}
              </section>
            )}

            {/* Nhãn của lượt chung — logic gán thẻ y hệt module Khách hàng (kho dùng chung, thêm/gỡ
                tức thì, xoá khỏi kho hỏi số bước). Lượt chung luôn đã lưu nên có id để neo. */}
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <h3 className="khsx-section-card__title">Nhãn</h3>
              </div>
              <TagPicker buocLoai="bai_ghep" buocId={g.id} canUpdate={canUpdate} />
            </section>
          </div>
        )}

        {/* ================= TAB 2: PHÂN CÔNG & THIẾT BỊ ================= */}
        {tab === "phan_cong" && (
          <div className="khsx-tab-pane">
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <h3 className="khsx-section-card__title">Tổ sản xuất & Máy thiết bị</h3>
              </div>

              {g.may_khong_hop.map((c) => (
                <div className="khsx-note-banner khsx-note-banner--warn" key={c}>
                  <span>{c}</span>
                </div>
              ))}

              <div className="khsx-assign-grid">
                <label className="khsx-field">
                  <span className="khsx-field__label">TỔ PHỤ TRÁCH</span>
                  <select
                    className="khsx-select-std"
                    value={val("department_id", g.department_id) ?? ""}
                    disabled={!canUpdate || !toRefs}
                    onChange={(e) => setF({ ...f, department_id: e.target.value ? Number(e.target.value) : null })}
                  >
                    <option value="">— chọn tổ —</option>
                    {(toRefs ?? []).map((t) => (
                      <option key={t.id} value={t.id}>{t.ten}</option>
                    ))}
                  </select>
                  <span className="khsx-field__hint">Đổi tổ thì bảng khoán đổi theo — lưu rồi mở lại mới thấy danh sách mới.</span>
                </label>

                {!ngoai && (
                  <label className="khsx-field">
                    <span className="khsx-field__label">MÁY CHẠY LƯỢT CHUNG</span>
                    <select
                      className="khsx-select-std"
                      value={mayId ?? ""}
                      disabled={!canUpdate || !mayRefs}
                      onChange={(e) => setF({ ...f, may_id: e.target.value ? Number(e.target.value) : null })}
                    >
                      <option value="">— chọn máy —</option>
                      {(mayRefs ?? [])
                        .filter((m) => {
                          // Lọc máy theo NHÓM công đoạn (bước Bế chỉ thấy máy Bế). Chưa khai ràng
                          // buộc → hiện tất cả. Giữ máy ĐANG CHỌN dù sai loại, để select không rơi
                          // về trống.
                          const allow = g.nhom_may_cho_phep ?? [];
                          if (allow.length === 0) return true;
                          if (m.id === mayId) return true;
                          return m.loaiMay != null && allow.includes(m.loaiMay);
                        })
                        .map((m) => (
                          <option key={m.id} value={m.id}>{m.ten}</option>
                        ))}
                    </select>
                    {(g.nhom_may_cho_phep?.length ?? 0) > 0 && (
                      <span className="khsx-field__hint">Chỉ máy nhóm: {g.nhom_may_cho_phep.join(", ")}</span>
                    )}
                    {mayDaChon && (
                      <span className="khsx-field__hint">
                        {mayDaChon.tocDo
                          ? `Tốc độ ${num(Number(mayDaChon.tocDo))} ${mayDaChon.donViTocDo || "đv"}/giờ`
                          : "Máy chưa khai tốc độ"}
                        {mayDaChon.chuanBiPhut ? ` · chuẩn bị ${num(Number(mayDaChon.chuanBiPhut))}′` : ""}
                      </span>
                    )}
                  </label>
                )}
              </div>
            </section>

            {!ngoai && (
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">
                    {g.loai_buoc === "may" ? "Nhân sự vận hành máy" : "Nhân sự làm tay"}
                  </h3>
                </div>
                {/* Cùng một hình với khối Nhân lực của bước lệnh (21/08/2026): số BỐ TRÍ ở trên,
                    ba mốc định biên ở dưới. Trước đây bước chung của bài chỉ có mỗi ô "số người kế
                    hoạch" trơ trọi — người khai không biết bước cần tối thiểu/tối đa mấy người, mà
                    đúng bộ số đó mới là thứ bàn xếp lịch dùng để kêu quá tải quân số tổ. */}
                <div className="khsx-labor-section">
                  <label className="khsx-field">
                    <span className="khsx-field__label">SỐ NGƯỜI BỐ TRÍ (KẾ HOẠCH)</span>
                    <div className="khsx-input-unit-combine">
                      <input
                        type="number" min="1" className="khsx-input-combine__num"
                        value={val("so_nhan_cong", g.so_nhan_cong) ?? ""}
                        placeholder="1"
                        disabled={!canUpdate}
                        onChange={(e) => setF({ ...f, so_nhan_cong: Number(e.target.value) || 1 })}
                      />
                      <span className="khsx-input-combine__unit">người</span>
                    </div>
                    <span className="khsx-field__hint">
                      Bàn xếp lịch cân quân số tổ theo đúng số này.{" "}
                      {g.loai_buoc === "may"
                        ? "Thêm người không làm máy chạy nhanh hơn."
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
                          <input
                            type="number"
                            min="1"
                            className="khsx-labor-num-field"
                            value={val(khoa, g[khoa]) ?? ""}
                            placeholder="—"
                            disabled={!canUpdate}
                            onChange={(e) => {
                              const so = e.target.value === "" ? null : Math.max(1, Number(e.target.value) || 1);
                              if (khoa === "so_nhan_cong_tieu_chuan") {
                                const std = so ?? 1;
                                const cu = Math.max(1, Number(g.so_nhan_cong_tieu_chuan) || 1);
                                // Kế hoạch đang bám kíp chuẩn ⇒ kéo theo cho khỏi lệch. Người khai
                                // đã chỉnh tay số khác ⇒ giữ nguyên, không giẫm lên họ.
                                setF(
                                  boTri === cu
                                    ? { ...f, so_nhan_cong_tieu_chuan: std, so_nhan_cong: std }
                                    : { ...f, so_nhan_cong_tieu_chuan: std },
                                );
                                return;
                              }
                              setF({ ...f, [khoa]: so });
                            }}
                          />
                          <span className="khsx-labor-unit">người</span>
                        </label>
                      ))}
                    </div>
                    <span className="khsx-field__hint">
                      {g.loai_buoc === "may" ? (
                        <>Kíp đứng máy chỉ để bàn xếp lịch cân người — không đổi thời lượng, vì thời
                        lượng bước máy chạy theo tốc độ máy.</>
                      ) : (
                        <>
                          Kíp tiêu chuẩn <strong>rút ngắn thời gian</strong>: năng suất khoán khai theo
                          đầu người nên kíp {Math.max(1, Number(bienTc) || 1)} người làm nhanh gấp{" "}
                          {Math.max(1, Number(bienTc) || 1)}. Tối thiểu/tối đa chỉ để bàn xếp lịch cảnh
                          báo, không đổi thời lượng bước.
                        </>
                      )}
                    </span>
                  </div>
                </div>
              </section>
            )}

            {(g.khoan_chon_duoc.length > 0 || g.khoan_rate_id != null) && (
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Đầu việc khoán lương thợ</h3>
                  <span className="khsx-tag-subtle">bảng khoán của tổ</span>
                </div>

                <div className="khsx-khoan-body">
                  {/* Ghim theo ID; đơn giá là ảnh chụp do server giữ. */}
                  <select
                    className="khsx-select-std"
                    value={val("piece_rate_id", g.khoan_rate_id) ?? ""}
                    disabled={!canUpdate}
                    onChange={(e) => {
                      const id = e.target.value ? Number(e.target.value) : null;
                      const chon = id != null ? dsKhoan.find((k) => k.id === id) : undefined;
                      const bung = bungVatTu(chon, vtHienTai);
                      setF({
                        ...f,
                        piece_rate_id: id,
                        ...(bung.length > vtHienTai.length ? { vat_tus: bung } : {}),
                      });
                    }}
                  >
                    <option value="">— chọn đầu việc khoán —</option>
                    {dsKhoan.map((k) => (
                      <option key={k.id} value={k.id}>
                        {k.don_vi ? `${k.ten} — ${num(k.don_gia)} đ/${k.don_vi}` : k.ten}
                      </option>
                    ))}
                  </select>

                  <div className="khsx-khoan-status-row">
                    {doiTo ? (
                      <span className="khsx-pill-status khsx-pill-status--warn">
                        Lưu lượt chung để tính lại tiền công
                      </span>
                    ) : optLive ? (
                      tienLive != null ? (
                        <span className="khsx-pill-status khsx-pill-status--ok">
                          {dienGiaiLive ?? g.khoan_dien_giai}
                        </span>
                      ) : (
                        <span className="khsx-pill-status khsx-pill-status--error">
                          {dienGiaiLive ?? "Chưa quy đổi được sản lượng sang đơn vị đơn giá."}
                        </span>
                      )
                    ) : f.piece_rate_id !== undefined ? (
                      <span className="khsx-pill-status khsx-pill-status--warn">
                        Lưu lượt chung để tính lại tiền công
                      </span>
                    ) : g.khoan_dien_giai ? (
                      <span className="khsx-pill-status khsx-pill-status--ok">{g.khoan_dien_giai}</span>
                    ) : g.khoan_ly_do ? (
                      <span className="khsx-pill-status khsx-pill-status--error">{g.khoan_ly_do}</span>
                    ) : g.khoan_chon_duoc.length > 1 ? (
                      <span className="khsx-field__hint">
                        Tổ có {g.khoan_chon_duoc.length} đầu việc khoán — chọn đúng việc thợ làm để tự
                        ra tiền công.
                      </span>
                    ) : null}
                  </div>
                </div>

                {g.khoan_thieu.map((c) => (
                  <div className="khsx-note-banner khsx-note-banner--warn" key={c}>
                    <span>{c}</span>
                  </div>
                ))}

                {(tienHien != null || slHien != null) && (
                  <div className="khsx-compact-kpi-strip">
                    <div className="khsx-compact-kpi-cell">
                      <span className="khsx-compact-kpi-label">Sản lượng tính công</span>
                      <div className="khsx-compact-kpi-val-group">
                        <span className="khsx-compact-kpi-val">
                          {slHien != null ? num(slHien) : "—"}
                        </span>
                        <span className="khsx-compact-kpi-sub">{nhanDonVi(dvSlHien) || "chưa quy đổi"}</span>
                      </div>
                    </div>
                    <div className="khsx-compact-kpi-cell khsx-compact-kpi-cell--rust">
                      <span className="khsx-compact-kpi-label">Tiền công cả lượt chung</span>
                      <div className="khsx-compact-kpi-val-group">
                        <span className="khsx-compact-kpi-val">
                          {tienHien != null ? `${num(tienHien)} đ` : "—"}
                        </span>
                        <span className="khsx-compact-kpi-sub">chia lại cho {g.thanh_vien.length} lệnh</span>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
        )}

        {/* ================= TAB 3: VẬT TƯ CỦA CẢ LƯỢT ================= */}
        {tab === "vat_tu" && (
          <div className="khsx-tab-pane">
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <div>
                  <h3 className="khsx-section-card__title">Vật tư cho cả lượt chung</h3>
                  <p className="khsx-section-card__sub">
                    Mực · kẽm · màng dùng chung cho tờ ghép, không của riêng lệnh nào.
                  </p>
                </div>
                <span className="khsx-badge-count">{vtHienTai.length} vật tư</span>
              </div>

              {vtHienTai.length > 0 && (
                <div className="khsx-vattu-table-head">
                  <span>VẬT TƯ & QUY CÁCH</span>
                  <span>ĐỊNH MỨC TIÊU HAO</span>
                </div>
              )}

              {/* Thanh Chỉ Số Mini & Nút Đồng Bộ Nhanh */}
              {vtHienTai.length > 0 && (
                <div className="khsx-vattu-metric-bar">
                  <div className="khsx-vattu-metric-chips">
                    <span className="khsx-vattu-metric-chip">
                      Tổng: <strong>{vtHienTai.length}</strong>
                    </span>
                    <span className="khsx-vattu-metric-dot" />
                    <span className="khsx-vattu-metric-chip">
                      Khớp công thức:{" "}
                      <strong>
                        {
                          vtHienTai.filter((row) => {
                            const goiY = g.vat_tu_goi_y.find((x) => x.vat_tu_id === row.vat_tu_id);
                            return (
                              goiY?.so_luong != null &&
                              Math.abs(goiY.so_luong - Number(row.so_luong)) <= 0.0005
                            );
                          }).length
                        }
                      </strong>
                    </span>
                  </div>

                  {canUpdate &&
                    vtHienTai.some((row) => {
                      const goiY = g.vat_tu_goi_y.find((x) => x.vat_tu_id === row.vat_tu_id);
                      return (
                        goiY?.so_luong != null &&
                        Math.abs(goiY.so_luong - Number(row.so_luong)) > 0.0005
                      );
                    }) && (
                      <button
                        type="button"
                        className="khsx-vattu-sync-all-btn"
                        title="Cập nhật toàn bộ số lượng theo công thức định mức"
                        onClick={() => {
                          const next = vtHienTai.map((row) => {
                            const goiY = g.vat_tu_goi_y.find((x) => x.vat_tu_id === row.vat_tu_id);
                            return goiY?.so_luong != null
                              ? { ...row, so_luong: goiY.so_luong }
                              : row;
                          });
                          datVatTu(next);
                          const nextVtGo = { ...vtGo };
                          for (const row of next) {
                            nextVtGo[row.vat_tu_id] = String(row.so_luong);
                          }
                          setVtGo(nextVtGo);
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
                    {vtHienTai.length === 0 ? (
                      <tr className="khsx-vattu-tr">
                        <td colSpan={5} className="khsx-vattu-td" style={{ textAlign: "center", color: "#94a3b8", padding: "20px" }}>
                          Chưa khai vật tư nào cho lượt này.
                        </td>
                      </tr>
                    ) : (
                      vtHienTai.map((row, i) => {
                        const dm = (vtRefs ?? []).find((v) => v.id === row.vat_tu_id);
                        const snap = g.vat_tus.find((v) => v.vat_tu_id === row.vat_tu_id);
                        const donVi = dm?.donVi || snap?.don_vi || "";
                        const goiY = g.vat_tu_goi_y.find((x) => x.vat_tu_id === row.vat_tu_id);
                        const soMay = goiY?.so_luong ?? null;
                        const soLuu = Number(row.so_luong);
                        const khop = soMay !== null && Number.isFinite(soLuu) && Math.abs(soMay - soLuu) <= 0.0005;
                        const lech = soMay !== null && Number.isFinite(soLuu) && !khop;
                        return (
                          <tr className="khsx-vattu-tr" key={`${row.vat_tu_id}_${i}`}>
                            <td className="khsx-vattu-td khsx-vattu-td--info">
                              <div className="khsx-vattu-cell-name">
                                <span className="khsx-vattu-code">{dm?.ma ?? snap?.ma ?? "—"}</span>
                                <span className="khsx-vattu-name">{dm?.ten ?? snap?.ten ?? `Vật tư #${row.vat_tu_id}`}</span>
                              </div>
                            </td>
                            <td className="khsx-vattu-td khsx-vattu-td--why">
                              {goiY?.dien_giai ? (
                                <div className="khsx-formula-wrap">
                                  <code className="khsx-formula-code">{goiY.dien_giai}</code>
                                  {lech && (
                                    <div className="khsx-diff-badge">
                                      <span>Lệch: {num(soMay as number)} {nhanDonVi(donVi)}</span>
                                      {canUpdate && (
                                        <button
                                          type="button"
                                          className="khsx-vattu-fix-btn"
                                          onClick={() => {
                                            setVtGo({ ...vtGo, [row.vat_tu_id]: String(soMay) });
                                            const next = [...vtHienTai];
                                            next[i] = { ...row, so_luong: Number(soMay) };
                                            datVatTu(next);
                                          }}
                                        >
                                          Dùng số này
                                        </button>
                                      )}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="khsx-vattu-no-formula">
                                  Chưa tự tính được — {goiY?.ly_do ?? "vật tư không còn dùng ở danh mục."}
                                </span>
                              )}
                            </td>
                            <td className="khsx-vattu-td khsx-vattu-td--status">
                              <span className={`khsx-vattu-src-badge ${khop ? "is-auto" : "is-manual"}`}>
                                {khop ? "Tự tính" : "Đã sửa"}
                              </span>
                            </td>
                            <td className="khsx-vattu-td khsx-vattu-td--input">
                              <div className="khsx-vattu-input-group">
                                <input
                                  type="number"
                                  min="0"
                                  step="any"
                                  className="khsx-vattu-num-input"
                                  value={vtGo[row.vat_tu_id] ?? String(row.so_luong ?? "")}
                                  placeholder="0"
                                  disabled={!canUpdate}
                                  onChange={(e) => {
                                    setVtGo({ ...vtGo, [row.vat_tu_id]: e.target.value });
                                    const next = [...vtHienTai];
                                    next[i] = { ...row, so_luong: Number(e.target.value) || 0 };
                                    datVatTu(next);
                                  }}
                                />
                                <span className="khsx-vattu-unit-tag">{nhanDonVi(donVi)}</span>
                              </div>
                            </td>
                            <td className="khsx-vattu-td khsx-vattu-td--action" style={{ textAlign: "center" }}>
                              {canUpdate && (
                                <button
                                  type="button"
                                  className="khsx-vattu-del-btn"
                                  title="Bỏ vật tư khỏi lượt chung"
                                  aria-label={`Bỏ ${dm?.ten ?? snap?.ten ?? "vật tư"}`}
                                  onClick={() => datVatTu(vtHienTai.filter((_, j) => j !== i))}
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
                  {canUpdate && vtRefs && (
                    <tfoot className="khsx-vattu-tfoot">
                      <tr>
                        <td colSpan={5} className="khsx-vattu-td-add">
                          <div className="khsx-vattu-add-bar">
                            <span className="khsx-vattu-add-icon">＋</span>
                            <select
                              className="khsx-vattu-select-clean"
                              value=""
                              aria-label="Thêm vật tư vào lượt chung"
                              onChange={(e) => {
                                const item = vtRefs.find((v) => v.id === Number(e.target.value));
                                if (!item || vtHienTai.some((v) => v.vat_tu_id === item.id)) return;
                                const goiYMoi = g.vat_tu_goi_y.find((x) => x.vat_tu_id === item.id);
                                datVatTu([...vtHienTai, { vat_tu_id: item.id, so_luong: goiYMoi?.so_luong ?? 0 }]);
                              }}
                            >
                              <option value="">— Thêm vật tư vào lượt chung —</option>
                              {vtRefs
                                .filter((x) => !vtHienTai.some((v) => v.vat_tu_id === x.id))
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

        {/* ================= TAB 4: TIẾN ĐỘ & THỜI GIAN ================= */}
        {tab === "tien_do" && (
          <div className="khsx-tab-pane">
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <h3 className="khsx-section-card__title">Tham số vận hành & phát sinh</h3>
              </div>

              <div className="khsx-thoi-gian-grid">
                {g.loai_buoc === "may" ? (
                  <div className="khsx-field">
                    <span className="khsx-field__label">SỐ LƯỢT CHẠY QUA MÁY</span>
                    <div className="khsx-turns-control">
                      <div className="khsx-turns-presets" role="group" aria-label="Số lượt chạy">
                        {[1, 2].map((v) => (
                          <button
                            key={v}
                            type="button"
                            className={`khsx-turn-btn ${Number(val("so_luot_chay", g.so_luot_chay) ?? 1) === v ? "is-active" : ""}`}
                            disabled={!canUpdate}
                            onClick={() => setF({ ...f, so_luot_chay: v })}
                          >
                            {v === 1 ? "1 lượt" : "2 lượt (In trở)"}
                          </button>
                        ))}
                      </div>
                      <div className="khsx-input-unit-combine khsx-turns-custom">
                        <input
                          type="number" min="1" className="khsx-input-combine__num"
                          value={val("so_luot_chay", g.so_luot_chay) ?? ""}
                          placeholder="1"
                          disabled={!canUpdate}
                          onChange={(e) => setF({ ...f, so_luot_chay: Number(e.target.value) || 1 })}
                        />
                        <span className="khsx-input-combine__unit">lượt</span>
                      </div>
                    </div>
                    <span className="khsx-field__hint">In trở 2 mặt = 2 lượt qua máy</span>
                  </div>
                ) : g.loai_buoc === "to" ? (
                  <label className="khsx-field">
                    <span className="khsx-field__label">NĂNG SUẤT MỘT NGƯỜI</span>
                    <div className="khsx-input-unit-combine">
                      <input
                        type="number" min="0" className="khsx-input-combine__num"
                        placeholder="theo đầu việc"
                        value={val("nang_suat", g.nang_suat) ?? ""}
                        disabled={!canUpdate}
                        onChange={(e) => setF({ ...f, nang_suat: e.target.value ? Number(e.target.value) : null })}
                      />
                      <span className="khsx-input-combine__unit">{dvVao || "đv"}/giờ</span>
                    </div>
                    <span className="khsx-field__hint">Nhân với số người kế hoạch để ra năng suất cả tổ.</span>
                  </label>
                ) : (
                  <div className="khsx-field" />
                )}

                <div className="khsx-field">
                  <span className="khsx-field__label">THỜI GIAN PHÁT SINH / KHÁC</span>
                  <div className="khsx-extra-time-control">
                    <div className="khsx-input-unit-combine">
                      <input
                        type="number" min="0" className="khsx-input-combine__num"
                        value={val("phat_sinh_phut", g.phat_sinh_phut) ?? ""}
                        placeholder="0"
                        disabled={!canUpdate}
                        onChange={(e) => setF({ ...f, phat_sinh_phut: Math.max(0, Number(e.target.value) || 0) })}
                      />
                      <span className="khsx-input-combine__unit">phút</span>
                    </div>
                    {canUpdate && (
                      <div className="khsx-quick-presets">
                        {[15, 30].map((v) => (
                          <button
                            key={v} type="button" className="khsx-preset-btn" title={`Thêm ${v} phút`}
                            onClick={() => setF({
                              ...f,
                              phat_sinh_phut: Number(val("phat_sinh_phut", g.phat_sinh_phut) ?? 0) + v,
                            })}
                          >
                            +{v}′
                          </button>
                        ))}
                        {Number(val("phat_sinh_phut", g.phat_sinh_phut) ?? 0) > 0 && (
                          <button
                            type="button" className="khsx-preset-btn khsx-preset-btn--reset"
                            title="Đặt lại 0 phút"
                            onClick={() => setF({ ...f, phat_sinh_phut: 0 })}
                          >
                            Xóa
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <span className="khsx-field__hint">Cộng thẳng vào giờ chiếm máy</span>
                </div>
              </div>
            </section>

            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <div>
                  <h3 className="khsx-section-card__title">Bóc tách thời gian lượt chung</h3>
                  <p className="khsx-section-card__sub">
                    Một lần lên máy cho {g.thanh_vien.length} lệnh — không cộng dồn thời gian từng lệnh.
                  </p>
                </div>
              </div>

              {canhBaoGio.map((c) => (
                <div className="khsx-alert" key={String(c)}>{String(c)}</div>
              ))}

              {chiemTB > 0 && (
                <div className="khsx-proportion-wrap">
                  <div className="khsx-proportion-bar">
                    {setup > 0 && (
                      <div
                        className="khsx-proportion-seg khsx-proportion-seg--amber"
                        style={{ width: `${Math.max(2, (setup / chiemTB) * 100)}%` }}
                        title={`Chuẩn bị: ${num(setup)}′`}
                      />
                    )}
                    {chayTB > 0 && (
                      <div
                        className="khsx-proportion-seg khsx-proportion-seg--moss"
                        style={{ width: `${Math.max(2, (chayTB / chiemTB) * 100)}%` }}
                        title={`Chạy máy: ${num(chayTB)}′`}
                      />
                    )}
                    {phatSinh > 0 && (
                      <div
                        className="khsx-proportion-seg khsx-proportion-seg--plum"
                        style={{ width: `${Math.max(2, (phatSinh / chiemTB) * 100)}%` }}
                        title={`Phát sinh: ${num(phatSinh)}′`}
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

              <div className="khsx-time-list">
                {/* GIAI ĐOẠN 1: Chuẩn bị */}
                <div className="khsx-time-stage-card khsx-time-stage-card--amber">
                  <div className="khsx-time-stage-card__head">
                    <div className="khsx-time-stage-card__title-group">
                      <div className="khsx-time-stage-card__title-row">
                        <span className="khsx-time-tag khsx-time-tag--amber">Chuẩn bị</span>
                        <span className="khsx-time-stage-card__title">Chuẩn bị tờ ghép</span>
                      </div>
                      <span className="khsx-time-stage-card__device-chip">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="2" y="6" width="20" height="12" rx="2" />
                          <circle cx="12" cy="12" r="2" />
                          <path d="M6 12h.01M18 12h.01" />
                        </svg>
                        {mayDaChon?.ten
                          ? (mayDaChon.ten.toLowerCase().startsWith("máy") ? mayDaChon.ten : `Máy ${mayDaChon.ten}`)
                          : g.may_ten
                            ? (g.may_ten.toLowerCase().startsWith("máy") ? g.may_ten : `Máy ${g.may_ten}`)
                            : "Chưa gán máy"}
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

                {/* GIAI ĐOẠN 2: Chạy máy cả tờ ghép */}
                <div className="khsx-time-stage-card khsx-time-stage-card--moss">
                  <div className="khsx-time-stage-card__head">
                    <div className="khsx-time-stage-card__title-group">
                      <div className="khsx-time-stage-card__title-row">
                        <span className="khsx-time-tag khsx-time-tag--moss">Chạy máy</span>
                        <span className="khsx-time-stage-card__title">Thời gian chạy cả tờ ghép</span>
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
                          <span className="khsx-formula-text">
                            {tg.quy_doi_dien_giai
                              ? String(tg.quy_doi_dien_giai)
                              : `${num(Number(tg.so_luong_vao ?? 0))} ${nhanDonVi(String(tg.don_vi_vao ?? ""))}`}
                            {" ÷ "}
                            {num(Number(tg.nang_suat_hieu_dung ?? 0))}/giờ
                            {g.loai_buoc === "may" && Number(tg.so_luot_chay ?? 1) !== 1
                              ? ` × ${Number(tg.so_luot_chay ?? 1)} lượt`
                              : ""}
                            {" = "}
                            <strong>{phut(chayTB)}</strong>
                          </span>
                        </div>
                        <span className="khsx-time-row__src">
                          Nguồn: {g.loai_buoc === "may"
                            ? (mayDaChon?.ten ?? g.may_ten ?? "Chưa gán máy")
                            : (g.khoan_ten ?? "Đầu việc khoán")}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

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

                {coDai ? (
                  <div className="khsx-tolerance-line">
                    <div className="khsx-tolerance-line__head">
                      <span>Biên độ tốc độ máy (Min — Max)</span>
                      <span>Kế hoạch Gantt: <b>{phut(chiemTB)}</b></span>
                    </div>
                    <div className="khsx-tolerance-line__bar">
                      <span className="khsx-tolerance-line__node">Nhanh nhất: <b>{phut(chiemMin)}</b></span>
                      <div className="khsx-tolerance-line__track">
                        <div className="khsx-tolerance-line__point" />
                      </div>
                      <span className="khsx-tolerance-line__node">Chậm nhất: <b>{phut(chiemMax)}</b></span>
                    </div>
                  </div>
                ) : (
                  <div className="khsx-tolerance-empty">
                    {g.loai_buoc === "to"
                      ? "Đầu việc chưa khai năng suất tối thiểu / tối đa nên chưa có khoảng nhanh–chậm."
                      : "Máy chưa khai tốc độ tối thiểu / tối đa nên chưa có khoảng nhanh–chậm."}
                  </div>
                )}
              </div>

              <div className="khsx-compact-kpi-strip">
                <div className="khsx-compact-kpi-cell khsx-compact-kpi-cell--rust">
                  <span className="khsx-compact-kpi-label">Thời gian chiếm máy (Gantt)</span>
                  <div className="khsx-compact-kpi-val-group">
                    <span className="khsx-compact-kpi-val">{phut(chiemTB)}</span>
                    {dirty && <span className="khsx-compact-kpi-sub">tính thử — lưu để chốt vào lịch</span>}
                  </div>
                </div>
                <div className="khsx-compact-kpi-cell">
                  <span className="khsx-compact-kpi-label">Nếu tách ra chạy riêng</span>
                  <div className="khsx-compact-kpi-val-group">
                    <span className="khsx-compact-kpi-val">{g.thanh_vien.length} lần chuẩn bị</span>
                    <span className="khsx-compact-kpi-sub">chạy chung chỉ tốn 1</span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}

        {/* ================= TAB 5: GIA CÔNG NGOÀI (chỉ bước thuê ngoài) ================= */}
        {tab === "gia_cong" && ngoai && (
          <div className="khsx-tab-pane">
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <div>
                  <h3 className="khsx-section-card__title">Đối tác & Khối lượng gia công</h3>
                  {/* Bước chung nằm TRƯỚC điểm toả nên cả gửi lẫn nhận đều ở tầng bài — một phiếu. */}
                  <p className="khsx-section-card__sub">Cả tờ ghép đi một phiếu, một nhà cung cấp.</p>
                </div>
              </div>

              <div className="khsx-subcontract-grid-full">
                <label className="khsx-field">
                  <span className="khsx-field__label">NHÀ CUNG CẤP</span>
                  <input
                    type="text" className="khsx-select-std" disabled={!canUpdate}
                    value={val("nha_cung_cap", g.nha_cung_cap) ?? ""}
                    placeholder="tên nhà gia công"
                    onChange={(e) => setF({ ...f, nha_cung_cap: e.target.value })}
                  />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">SỐ LƯỢNG GỬI</span>
                  <div className="khsx-vattu-input-group">
                    <input
                      type="number" min="0" className="khsx-vattu-num-input" disabled={!canUpdate}
                      value={val("sl_gui", g.sl_gui) ?? ""}
                      onChange={(e) => setF({ ...f, sl_gui: e.target.value ? Number(e.target.value) : null })}
                    />
                    <span className="khsx-vattu-unit-tag">{dvVao}</span>
                  </div>
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">HAO HỤT CHO PHÉP</span>
                  <div className="khsx-vattu-input-group">
                    <input
                      type="number" min="0" className="khsx-vattu-num-input" disabled={!canUpdate}
                      title="Thoả thuận với nhà gia công"
                      value={val("hao_hut_cho_phep", g.hao_hut_cho_phep) ?? ""}
                      onChange={(e) => setF({ ...f, hao_hut_cho_phep: e.target.value ? Number(e.target.value) : null })}
                    />
                    <span className="khsx-vattu-unit-tag">{dvVao}</span>
                  </div>
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">ĐƠN GIÁ GIA CÔNG</span>
                  <div className="khsx-vattu-input-group">
                    <input
                      type="number" min="0" className="khsx-vattu-num-input" disabled={!canUpdate}
                      value={val("don_gia_gia_cong", g.don_gia_gia_cong) ?? ""}
                      onChange={(e) => setF({ ...f, don_gia_gia_cong: e.target.value ? Number(e.target.value) : null })}
                    />
                    <span className="khsx-vattu-unit-tag">đ/{dvVao || "đơn vị"}</span>
                  </div>
                </label>
              </div>
            </section>

            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <h3 className="khsx-section-card__title">Lịch trình tiến độ dự kiến</h3>
              </div>
              <div className="khsx-subcontract-grid-full">
                <label className="khsx-field">
                  <span className="khsx-field__label">NGÀY GỬI (DK)</span>
                  <input
                    type="date" className="khsx-select-std" disabled={!canUpdate}
                    value={val("ngay_gui_dk", g.ngay_gui_dk) ?? ""}
                    onChange={(e) => setF({ ...f, ngay_gui_dk: e.target.value || null })}
                  />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">NGÀY NHẬN (DK)</span>
                  <input
                    type="date" className="khsx-select-std" disabled={!canUpdate}
                    value={val("ngay_nhan_dk", g.ngay_nhan_dk) ?? ""}
                    onChange={(e) => setF({ ...f, ngay_nhan_dk: e.target.value || null })}
                  />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">VẬN CHUYỂN</span>
                  <div className="khsx-vattu-input-group">
                    <input
                      type="number" min="0" step="0.5" className="khsx-vattu-num-input" disabled={!canUpdate}
                      title="Tính cả hai chiều"
                      value={val("van_chuyen_ngay", g.van_chuyen_ngay) ?? ""}
                      onChange={(e) => setF({ ...f, van_chuyen_ngay: e.target.value ? Number(e.target.value) : null })}
                    />
                    <span className="khsx-vattu-unit-tag">ngày</span>
                  </div>
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">GIA CÔNG</span>
                  <div className="khsx-vattu-input-group">
                    <input
                      type="number" min="0" step="0.5" className="khsx-vattu-num-input" disabled={!canUpdate}
                      value={val("gia_cong_ngay", g.gia_cong_ngay) ?? ""}
                      onChange={(e) => setF({ ...f, gia_cong_ngay: e.target.value ? Number(e.target.value) : null })}
                    />
                    <span className="khsx-vattu-unit-tag">ngày</span>
                  </div>
                </label>
              </div>

              <label className="khsx-field">
                <span className="khsx-field__label">YÊU CẦU KỸ THUẬT GỬI NHÀ GIA CÔNG</span>
                <textarea
                  rows={2} className="khsx-textarea" disabled={!canUpdate}
                  value={val("yeu_cau_ky_thuat", g.yeu_cau_ky_thuat) ?? ""}
                  onChange={(e) => setF({ ...f, yeu_cau_ky_thuat: e.target.value })}
                />
              </label>
            </section>
          </div>
        )}

        {/* ================= TAB 6: CÁC LỆNH TRÊN TỜ ================= */}
        {tab === "cac_lenh" && (
          <div className="khsx-tab-pane">
            <section className="khsx-section-card">
              <div className="khsx-section-card__head">
                <div>
                  <h3 className="khsx-section-card__title">Yêu cầu kỹ thuật của từng lệnh</h3>
                  {/* GOM chứ không đè: thợ chạy chung một lượt phải đọc được yêu cầu của mọi khách
                      trên tờ đó. */}
                  <p className="khsx-section-card__sub">Gom hết, không đè lên nhau.</p>
                </div>
                <span className="khsx-badge-count">{g.thanh_vien.length} lệnh</span>
              </div>

              <ul className="bgsd-gang-notes">
                {g.thanh_vien.map((tv) => (
                  <li key={tv.lsx_step_key}>
                    <span className="khsx__code">{tv.lsx_ma}</span>
                    <span className={tv.ghi_chu_ky_thuat ? "" : "khsx-muted"}>
                      {tv.ghi_chu_ky_thuat || "không có ghi chú riêng"}
                    </span>
                  </li>
                ))}
              </ul>

              <label className="khsx-field">
                <span className="khsx-field__label">Ghi chú của bài cho lượt chạy này</span>
                <textarea
                  rows={2} className="khsx-textarea" disabled={!canUpdate}
                  value={f.ghi_chu ?? g.ghi_chu ?? ""}
                  onChange={(e) => setF({ ...f, ghi_chu: e.target.value })}
                />
              </label>
            </section>

            {canUpdate && (
              <section className="khsx-section-card">
                <div className="khsx-section-card__head">
                  <h3 className="khsx-section-card__title">Bỏ chạy chung</h3>
                </div>
                <p className="khsx-field__hint">
                  Tách ra thì kế hoạch của lượt chung mất, {g.thanh_vien.length} lệnh quay lại số riêng
                  và mỗi lệnh tự chuẩn bị máy một lần.
                </p>
                <div>
                  <button
                    type="button" className="khsx-xlink" style={{ color: "var(--signal)" }}
                    onClick={() => setConfirmTach(true)}
                  >
                    Tách lượt chung
                  </button>
                </div>
              </section>
            )}
          </div>
        )}
      </div>

      <footer className="khsx-drawer__foot">
        <p className="khsx-drawer__tally">
          {dirty
            ? "Có thay đổi chưa lưu — số giờ ở tab Tiến độ đang là tính thử."
            : "Số lượng · hao · thời lượng do hệ thống tính, không sửa tay."}
        </p>
        <div className="khsx-drawer__footbtns">
          {onClose && <Button variant="secondary" onClick={onClose}>Đóng</Button>}
          {canUpdate && (
            <Button variant="primary" disabled={!dirty} loading={dangLuu} onClick={() => void luu()}>
              Lưu kế hoạch lượt chung
            </Button>
          )}
        </div>
      </footer>

      <ConfirmDialog
        open={confirmTach}
        title={`Tách "${g.ten}"?`}
        message="Kế hoạch của lượt chung sẽ mất, số riêng của từng lệnh quay lại."
        confirmLabel="Tách lượt chung"
        cancelLabel="Hủy"
        danger
        onConfirm={() => {
          setConfirmTach(false);
          void onTach();
        }}
        onCancel={() => setConfirmTach(false)}
      />
    </>
  );
}
