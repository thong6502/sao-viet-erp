// BÁO CÁO CÔNG NỢ (131 Phải thu · 331 Phải trả) — Sổ tổng hợp MISA + Sổ chi tiết + Khóa kỳ + In chuẩn Excel
//
// Tab "Chi tiết đơn & đợt" ĐÃ GỠ 05/09/2026 (chủ chốt chọn cách B). Nó KHÔNG phải báo cáo theo
// kỳ dù ngồi trong màn Báo cáo: `tu_ngay` bị bỏ qua hoàn toàn nên đợt đã tất toán từ kỳ trước
// vẫn nằm đó, và "đã trả/còn nợ" tính tại HÔM NAY (`_no_tung_dot` không nhận mốc ngày) nên in
// lại kỳ cũ ra số khác lần in trước. Vai trò của nó nay chia đôi: giải thích số của kỳ →
// `SoChiTietDrawer` (§5.1, lọc đúng kỳ); xem đợt nào quá hạn → màn Công nợ phải trả.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type BaoCaoCongNo,
  type CongNoKhoaSoTrangThai,
  type CongNoKyRow,
} from "../../../api/client";
import { useCan } from "../../../auth/permissions";
import { useAuth } from "../../../auth/useAuth";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import type { NavigateFn } from "../../../components/AppShell";
import { Icon } from "../../../components/Icons";
import { money } from "../../../utils/format";
// import { printBaoCaoCongNo } from "../../../utils/printBaoCaoCongNo";
import { SoChiTietDrawer } from "./SoChiTietDrawer";
import { nhanKy, type Ky } from "./shared/ky";
import "../../accounting.css";
import "./bao-cao-cong-no.css";


function so(v: number): string {
  return v ? Math.round(v).toLocaleString("vi-VN") : "";
}

function O({ v, manh = false }: { v: number; manh?: boolean }) {
  if (!v) return <span className="bccn__khong">—</span>;
  return <span className={manh ? "bccn__tien bccn__tien--manh" : "bccn__tien"}>{so(v)}</span>;
}

function tieuDeMan(s: string | undefined, ben: "receivables" | "payables"): string {
  if (s) {
    const thuong = s.toLocaleLowerCase("vi-VN");
    return thuong.charAt(0).toLocaleUpperCase("vi-VN") + thuong.slice(1);
  }
  return ben === "receivables" ? "Tổng hợp công nợ phải thu" : "Tổng hợp công nợ phải trả";
}

/** Hôm nay dạng `YYYY-MM-DD`, làm TRẦN cho mọi ô chọn ngày.
 *
 *  Tự ghép chứ không dùng `toISOString()`: hàm đó đổi sang UTC nên tối muộn giờ VN trả về ngày
 *  HÔM TRƯỚC, và trần lại hụt mất một ngày.
 *
 *  Vì sao cần trần (sửa 04/09/2026): báo cáo là sổ của việc ĐÃ XẢY RA, còn chốt sổ là tuyên bố
 *  "kỳ này xong rồi". Cả hai đều vô nghĩa với ngày chưa tới — mà hộp khóa kỳ trước đó còn mặc
 *  định đề nghị chốt tới 30/09 khi mới mùng 4. */
function homNayISO(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(
    n.getDate(),
  ).padStart(2, "0")}`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

export function BaoCaoCongNoPage({
  ben,
  ky,
  onKy,
  navigate,
}: {
  ben: "receivables" | "payables";
  /** Kỳ do VỎ giữ (`BaoCaoKeToanPage`) — để đổi tab không mất kỳ đang chọn. */
  ky: Ky;
  onKy: (ky: Ky) => void;
  navigate?: NavigateFn;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Khoá/mở kỳ là quyền THAO TÁC riêng của `bao_cao_cong_no` (chủ chốt 04/09/2026), tách khỏi
  // Xem — ai chỉ xem sổ đối chiếu MISA không tự nhiên có luôn quyền niêm kỳ. Ẩn hẳn nút thay vì
  // hiện-rồi-khoá: bấm vào ăn 403 vô nghĩa với người chưa từng được cấp, đúng nếp "Lập phiếu chi"
  // ở Công nợ phải trả (`canCreateVoucher &&`).
  const canKhoaSo = can("bao_cao_cong_no", "update");
  // PHÂN HỆ khoá sổ suy thẳng từ tab đang xem. Hai sổ ĐỘC LẬP — chốt công nợ phải trả không được
  // kéo theo phải thu (chủ báo 04/09/2026: *"2 cái này nó khác nhau mà"*).
  const phanHe: "phai_thu" | "phai_tra" = ben === "receivables" ? "phai_thu" : "phai_tra";
  const [data, setData] = useState<BaoCaoCongNo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  const [q, setQ] = useState("");
  // Đối tượng đang mở SỔ CHI TIẾT. Giữ cả TÊN vừa bấm để hiện ngay lúc còn đang tải —
  // `id` có thể là `null` (dòng "ngoài danh mục") nên không dùng chính nó làm cờ đóng/mở được.
  const [xemSo, setXemSo] = useState<{ id: number | null; ten: string } | null>(null);

  // Khóa kỳ
  const [kyList, setKyList] = useState<CongNoKyRow[]>([]);
  const [khoaOpen, setKhoaOpen] = useState(false);
  const [khoaHanhDong, setKhoaHanhDong] = useState<"khoa" | "mo">("khoa");
  const [khoaTu, setKhoaTu] = useState("");
  const [khoaDen, setKhoaDen] = useState("");
  const [khoaTen, setKhoaTen] = useState("");
  const [khoaBusy, setKhoaBusy] = useState(false);
  const [khoaError, setKhoaError] = useState<string | null>(null);

  // Tải danh sách kỳ
  const loadKyList = useCallback(() => {
    if (!token) return;
    api.accounting.congNoKyList(token, phanHe).then(setKyList).catch(() => {});
  }, [token, phanHe]);

  useEffect(() => {
    loadKyList();
  }, [loadKyList]);

  // NHẢY VỀ KỲ HIỆN TẠI ngay khi biết danh sách kỳ thật (04/09/2026).
  //
  // Giá trị đầu ở vỏ là "đầu tháng → hôm nay" — một khoảng lịch, không phải kỳ kế toán. Từ khi
  // kỳ do LẦN CHỐT quyết định, khoảng đó gần như chắc chắn không khớp kỳ nào, và người dùng mở
  // màn ra là thấy ngay badge "Chốt một phần" khó hiểu. Chỉ nhảy MỘT LẦN: sau đó họ tự chọn kỳ
  // nào là quyền của họ, đừng giật lại.
  const daNhayKy = useRef(false);
  useEffect(() => {
    if (daNhayKy.current || kyList.length === 0) return;
    daNhayKy.current = true;
    const dungKy = kyList.some((k) => k.tu_ngay === ky.tu && k.den_ngay === ky.den);
    if (!dungKy) onKy({ tu: kyList[0].tu_ngay, den: kyList[0].den_ngay });
  }, [kyList, ky.tu, ky.den, onKy]);

  // TRẠNG THÁI KHÓA của đúng kỳ đang xem — HỎI SERVER, không tự suy (sửa 04/09/2026).
  //
  // Bản cũ dò trong `kyList` rồi so BẰNG ĐÚNG hai đầu ngày. `kyList` chỉ có kỳ THÁNG TRỌN
  // (01/09–30/09) nên kỳ báo cáo lẻ (01/09–04/09) không bao giờ khớp ⇒ luôn ra "chưa khóa": bấm
  // khóa xong nút vẫn ghi "Khóa kỳ", không dấu hiệu gì. Trên DB dev còn nguyên bốn lần bấm lại.
  const [trangThaiKhoa, setTrangThaiKhoa] = useState<CongNoKhoaSoTrangThai | null>(null);
  const kyHienTaiDaKhoa = trangThaiKhoa?.da_khoa ?? false;
  const kyKhoaMotPhan = trangThaiKhoa?.khoa_mot_phan ?? false;

  const loadTrangThaiKhoa = useCallback(() => {
    if (!token) return;
    api.accounting
      .congNoKhoaSoTrangThai(token, { tuNgay: ky.tu, denNgay: ky.den, phanHe })
      .then(setTrangThaiKhoa)
      .catch(() => setTrangThaiKhoa(null));
  }, [token, ky.tu, ky.den, phanHe]);

  useEffect(loadTrangThaiKhoa, [loadTrangThaiKhoa]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);

    api.accounting
      .baoCaoCongNo(token, ben, { tuNgay: ky.tu, denNgay: ky.den })
      .then(setData)
      .catch((cause) => {
        setError(cause instanceof ApiError ? cause.message : "Không tải được báo cáo công nợ.");
      })
      .finally(() => setLoading(false));
  }, [token, ben, ky.tu, ky.den]);

  useEffect(load, [load]);

  // Lọc dữ liệu Sổ tổng hợp
  const dongSo = useMemo(() => {
    const tim = q.trim().toLowerCase();
    return (data?.items ?? []).filter((d) => {
      if (!tim) return true;
      return d.ten.toLowerCase().includes(tim) || (d.ma ?? "").toLowerCase().includes(tim);
    });
  }, [data, q]);

  // Tổng cộng của phần sổ đang hiện
  const tongSo = useMemo(() => {
    const cot = ["dau_no", "dau_co", "ps_no", "ps_co", "cuoi_no", "cuoi_co"] as const;
    const ra = { so_dong: dongSo.length } as Record<string, number>;
    for (const k of cot) ra[k] = dongSo.reduce((s, d) => s + d[k], 0);
    return ra;
  }, [dongSo]);

  // KPI lấy THẲNG từ sổ tổng hợp (05/09/2026, cùng lúc gỡ tab "Chi tiết đơn & đợt").
  //
  // Trước đây ba con số này tính từ bảng chi tiết — mà bảng đó bỏ qua `tu_ngay` và tính "đã trả"
  // tại HÔM NAY, nên KPI không phải số CỦA KỲ: in lại kỳ cũ ra số khác lần in trước, và còn đá
  // nhau với chính bảng sổ ngay bên dưới. Lấy từ `data` thì KPI, sổ và dải rổ tuổi cùng một mốc.
  //
  //   • Nợ = dư CUỐI KỲ đúng bên của tài khoản: 331 dư bên Có, 131 dư bên Nợ.
  //   • Quá hạn = mọi rổ TRỪ rổ "chưa tới hạn" — dải rổ đã tính sẵn tại `den_ngay`.
  // KPI chuẩn 4 chỉ số tài chính của kỳ kế toán: Đầu + Tăng - Giảm = Cuối
  const kpi = useMemo(() => {
    const ben_no = ben === "receivables" ? "cuoi_no" : "cuoi_co";
    const items = data?.items ?? [];
    return {
      dauKy: ben === "receivables" ? (tongSo.dau_no || 0) : (tongSo.dau_co || 0),
      tangKy: ben === "receivables" ? (tongSo.ps_no || 0) : (tongSo.ps_co || 0),
      giamKy: ben === "receivables" ? (tongSo.ps_co || 0) : (tongSo.ps_no || 0),
      cuoiKy: ben === "receivables" ? (tongSo.cuoi_no || 0) : (tongSo.cuoi_co || 0),
      soDoiTuong: items.filter((d) => d[ben_no] > 0).length,
    };
  }, [ben, data, tongSo]);

  // In báo cáo (tạm thời ẩn theo yêu cầu)
  // function inBaoCao() {
  //   if (!data) return;
  //   printBaoCaoCongNo(data);
  // }

  // Xuất file Excel (.xlsx)
  async function xuatExcel() {
    if (!token) return;
    setDangXuat(true);
    try {
      const { url, ten } = await api.accounting.baoCaoCongNoXlsx(token, ben, {
        tuNgay: ky.tu,
        denNgay: ky.den,
      });
      const a = document.createElement("a");
      a.href = url;
      a.download = ten;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xuất được file.");
    } finally {
      setDangXuat(false);
    }
  }

  // Khóa / Mở kỳ
  function openKhoaModal() {
    loadKyList();
    const daKhoa = kyHienTaiDaKhoa;
    setKhoaHanhDong(daKhoa ? "mo" : "khoa");
    // CHỐT: luôn nối tiếp sau kỳ trước — không cho tự chọn ngày bắt đầu, vì chọn lệch là hoặc
    // chồng lấn kỳ cũ (server chặn 422) hoặc để hở một quãng không kỳ nào nhận.
    // MỞ: lấy đúng hai đầu của kỳ đang chọn, mở nguyên kỳ chứ không mở nửa vời.
    setKhoaTu(daKhoa ? ky.tu : mocChotTiepTheo ?? ky.tu);
    setKhoaDen(ky.den);
    // ĐỂ TRỐNG, không điền sẵn: tên gợi ý suy từ CHÍNH khoảng sắp chốt (xem `tenGoiY`) và phải
    // đổi theo khi người dùng sửa ngày. Điền sẵn theo kỳ đang XEM là sinh ra bản ghi mang tên một
    // khoảng mà phủ một khoảng khác — dữ liệu dev 04/09/2026 còn nguyên một dòng như thế
    // ("03/07 – 03/09/2026" nhưng thật ra phủ từ 01/01).
    setKhoaTen("");
    setKhoaError(null);
    setKhoaOpen(true);
  }

  async function saveKhoa() {
    if (!token) return;
    if (!khoaTu || !khoaDen) {
      setKhoaError("Vui lòng chọn cả ngày bắt đầu và kết thúc.");
      return;
    }
    if (khoaDen < khoaTu) {
      setKhoaError("Ngày đến phải lớn hơn hoặc bằng ngày từ.");
      return;
    }
    setKhoaBusy(true);
    setKhoaError(null);
    try {
      await api.accounting.setCongNoKhoaSo(token, {
        phan_he: phanHe,
        tu_ngay: khoaTu,
        den_ngay: khoaDen,
        hanh_dong: khoaHanhDong,
        ten: khoaHanhDong === "khoa" ? khoaTen.trim() || tenGoiY || null : null,
      });
      loadKyList();
      loadTrangThaiKhoa();
      load();
      setKhoaOpen(false);
    } catch (e) {
      setKhoaError(e instanceof ApiError ? e.message : "Không thực hiện được thao tác.");
    } finally {
      setKhoaBusy(false);
    }
  }

  // NGÀY BẮT ĐẦU của kỳ chốt tiếp theo = ngày ngay sau kỳ đã chốt cuối cùng. Server đã tính sẵn
  // và trả về ở mục "kỳ hiện tại" đầu danh sách, nên giao diện KHÔNG tự cộng ngày — cộng ở hai
  // nơi là hai nơi lệch nhau.
  const mocChotTiepTheo = kyList.find((k) => k.dang_dien_ra)?.tu_ngay ?? null;

  /** Tên kỳ gợi ý — LUÔN bám theo khoảng thật sắp chốt, tự đổi khi sửa ngày. */
  const tenGoiY = useMemo(
    () => (khoaTu && khoaDen ? `Kỳ ${fmtDate(khoaTu)}–${fmtDate(khoaDen)}` : ""),
    [khoaTu, khoaDen],
  );

  // KỲ ĐÃ CÓ KỲ CHỐT SAU ⇒ NIÊM VĨNH VIỄN (chủ chốt 04/09/2026: *"không cho luôn, đã tạo ra kì
  // mới rồi thì không cho mở nữa"*). Không phải tháo ngược từng nấc — mở kỳ sau ra rồi thì kỳ
  // trước vẫn niêm. Server tính sẵn `co_the_mo`; giao diện chỉ việc MỜ nút, đừng để người dùng
  // học luật bằng cách đâm vào lỗi 422.
  const kyDangChon = kyList.find((k) => k.tu_ngay === ky.tu && k.den_ngay === ky.den);
  const chanMoKy = kyHienTaiDaKhoa && kyDangChon != null && !kyDangChon.co_the_mo;
  // Kỳ chặn = kỳ chốt SỚM NHẤT nằm sau kỳ đang xem. Không lọc theo `da_khoa`: kỳ sau dù đã
  // được mở ra thì nó vẫn là thứ niêm kỳ này lại.
  const kyChan = chanMoKy
    ? kyList
        .filter((k) => !k.dang_dien_ra && k.den_ngay > ky.den)
        .sort((a, b) => a.den_ngay.localeCompare(b.den_ngay))[0]
    : undefined;

  const kyHienTai = nhanKy(ky);

  return (
    <main className="bccn">
      {/* Header */}
      <header className="bccn__head">
        <div className="bccn__head-chu">
          <h1 className="bccn__title">{tieuDeMan(data?.tieu_de, ben)}</h1>
          <p className="bccn__sub">
            Tài khoản <b>{data?.tk ?? (ben === "receivables" ? "131" : "331")}</b> · Sổ theo kỳ đối chiếu với MISA
            {kyHienTai ? ` · ${kyHienTai}` : ""}
          </p>
        </div>
        <div className="bccn__head-actions">
          {/* Tạm thời ẩn nút In báo cáo theo yêu cầu */}
          <Button variant="ghost" onClick={xuatExcel} disabled={dangXuat || !data} title="Xuất file .xlsx chuẩn MISA">
            <Icon name="table" size={14} /> {dangXuat ? "Đang xuất…" : "Xuất Excel"}
          </Button>
          {canKhoaSo && (
            <Button
              variant="secondary"
              onClick={openKhoaModal}
              disabled={chanMoKy}
              className={kyHienTaiDaKhoa ? "bccn__btn-locked" : ""}
              title={
                chanMoKy
                  ? `Kỳ này đã niêm — đã có kỳ chốt sau nó${kyChan ? ` (${kyChan.ten})` : ""}. Sổ đóng rồi thì không mở lại được nữa.`
                  : "Khóa hoặc mở sổ kỳ kế toán"
              }
            >
              <Icon name={kyHienTaiDaKhoa ? "lock" : "lockOpen"} size={14} />
              {kyHienTaiDaKhoa ? "Mở khóa kỳ" : kyKhoaMotPhan ? "Chốt nốt kỳ" : "Khóa kỳ"}
            </Button>
          )}
        </div>
      </header>

      {/* 4 Thẻ KPI Kế toán chuẩn kỳ */}
      <section className="bccn__kpi-grid" aria-label="Tổng quan kỳ">
        <div className="bccn__kpi-card">
          <div className="bccn__kpi-top">
            <span className="bccn__kpi-label">Dư nợ đầu kỳ</span>
            <Icon name="history" size={14} className="bccn__kpi-icon" />
          </div>
          <div className="bccn__kpi-number">{money(kpi.dauKy)}</div>
          <span className="bccn__kpi-sub">
            {ben === "receivables" ? "Dư nợ chuyển sang" : "Dư có chuyển sang"}
          </span>
        </div>

        <div className="bccn__kpi-card">
          <div className="bccn__kpi-top">
            <span className="bccn__kpi-label">
              {ben === "receivables" ? "Phát sinh tăng (Nợ)" : "Phát sinh tăng (Có)"}
            </span>
            <Icon name="arrowRight" size={14} className="bccn__kpi-icon" />
          </div>
          <div className="bccn__kpi-number">{money(kpi.tangKy)}</div>
          <span className="bccn__kpi-sub">
            {ben === "receivables" ? "Hóa đơn / Ghi nợ" : "Nhận hàng / Ghi có"}
          </span>
        </div>

        <div className="bccn__kpi-card">
          <div className="bccn__kpi-top">
            <span className="bccn__kpi-label">
              {ben === "receivables" ? "Đã thu trong kỳ" : "Đã trả trong kỳ"}
            </span>
            <Icon name="check" size={14} className="bccn__kpi-icon" />
          </div>
          <div className="bccn__kpi-number">{money(kpi.giamKy)}</div>
          <span className="bccn__kpi-sub">
            {ben === "receivables" ? "Phiếu thu / Giảm nợ" : "Phiếu chi / Giảm nợ"}
          </span>
        </div>

        <div className="bccn__kpi-card bccn__kpi-card--highlight">
          <div className="bccn__kpi-top">
            <span className="bccn__kpi-label">Dư nợ cuối kỳ</span>
            <Icon name="calculator" size={14} className="bccn__kpi-icon" />
          </div>
          <div className="bccn__kpi-number">{money(kpi.cuoiKy)}</div>
          <span className="bccn__kpi-sub">{kpi.soDoiTuong} đối tượng còn nợ</span>
        </div>
      </section>

      {/* Toolbar hợp nhất chuẩn RebuildCatalogPage */}
      <section className="bccn__toolbar" aria-label="Kỳ báo cáo và bộ lọc">
        <div className="bccn__toolbar-trai">
          <div className="bccn__ky-group">
            <label className="bccn__ky-label" htmlFor="bccn-select-ky">
              <Icon name="calendar" size={14} />
              <span>Kỳ</span>
            </label>
            <select
              id="bccn-select-ky"
              className="input bccn__select-ky"
              value={`${ky.tu}_${ky.den}`}
              onChange={(e) => {
                const [tu, den] = e.target.value.split("_");
                if (tu && den) onKy({ tu, den });
              }}
            >
              {!kyList.some((k) => k.tu_ngay === ky.tu && k.den_ngay === ky.den) && (
                <option value={`${ky.tu}_${ky.den}`}>
                  {nhanKy(ky) || `Kỳ ${fmtDate(ky.tu)}–${fmtDate(ky.den)}`}
                </option>
              )}
              {kyList.map((k) => (
                <option key={`${k.tu_ngay}_${k.den_ngay}`} value={`${k.tu_ngay}_${k.den_ngay}`}>
                  {k.ten} {k.da_khoa ? "🔒" : k.khoa_mot_phan ? "◑" : ""}
                </option>
              ))}
            </select>
          </div>


          <div className="bccn__status-pill">
            {kyHienTaiDaKhoa ? (
              <span
                className="badge-sem badge-sem--rust"
                title={
                  chanMoKy
                    ? `Đã chốt sổ và ĐÃ NIÊM: có kỳ chốt sau nó${kyChan ? ` (${kyChan.ten})` : ""}, nên không mở lại được nữa.`
                    : "Mọi ngày trong kỳ này đều đã chốt sổ"
                }
              >
                <Icon name="lock" size={13} /> Đã chốt sổ
                {chanMoKy && <span className="bccn__khoa-cung"> · đã niêm</span>}
              </span>
            ) : kyKhoaMotPhan ? (
              <span
                className="badge-sem badge-sem--amber"
                title="Kỳ này có ngày đã chốt, có ngày chưa — thường là do một kỳ chốt cũ chỉ phủ được một phần."
              >
                <Icon name="lock" size={13} /> Chốt một phần
              </span>
            ) : (
              <span className="badge-sem badge-sem--moss" title="Kỳ kế toán đang mở, chưa chốt sổ">
                <Icon name="lockOpen" size={13} /> Chưa chốt
              </span>
            )}
          </div>
        </div>

        <div className="bccn__toolbar-phai">
          <div className="bccn__tim">
            <Icon name="search" size={14} className="bccn__tim-icon" />
            <input
              className="bccn__tim-o"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm mã hoặc tên đối tượng..."
            />
            {q && (
              <button
                type="button"
                className="bccn__tim-xoa"
                onClick={() => setQ("")}
                aria-label="Xóa tìm kiếm"
              >
                ✕
              </button>
            )}
          </div>

          <span className="chip-count bccn__dem-chip">
            {loading ? "…" : `${dongSo.length} đối tượng`}
          </span>
        </div>
      </section>

      {error && <div className="alert alert--error">{error}</div>}

    {/* BẢNG SỔ TỔNG HỢP MẪU EXCEL MISA */}
      <section className="bccn__wrap">
        <table className="bccn__table">
          <colgroup>
            <col className="bccn__c-ma" />
            <col className="bccn__c-ten" />
            <col className="bccn__c-tk" />
            <col span={6} className="bccn__c-tien" />
          </colgroup>
          <thead>
            <tr className="bccn__hang-cum">
              <th rowSpan={2} className="bccn__th-ma">{data?.nhan_ma ?? "Mã đối tượng"}</th>
              <th rowSpan={2}>{data?.nhan_ten ?? "Tên đối tượng"}</th>
              <th rowSpan={2}>TK công nợ</th>
              <th colSpan={2} className="bccn__cum">Số dư đầu kỳ</th>
              <th colSpan={2} className="bccn__cum">Số phát sinh</th>
              <th colSpan={2} className="bccn__cum bccn__cum--cuoi">Số dư cuối kỳ</th>
            </tr>
            <tr className="bccn__hang-noco">
              <th>Nợ</th>
              <th className="bccn__het-cum">Có</th>
              <th>Nợ</th>
              <th className="bccn__het-cum">Có</th>
              <th>Nợ</th>
              <th>Có</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={`sk-${i}`} className="purchase__skeleton-row">
                  {Array.from({ length: 9 }).map((__, j) => (
                    <td key={j}>
                      <div
                        className="purchase__skeleton-bar"
                        style={{ width: j === 1 ? "180px" : j === 0 ? "80px" : "70px" }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading && dongSo.length === 0 && (
              <tr>
                <td colSpan={9} className="bccn__trong">
                  {q.trim() ? "Không có đối tượng nào khớp từ khoá." : "Kỳ này không có phát sinh nào."}
                </td>
              </tr>
            )}
            {!loading &&
              dongSo.map((d) => (
                // Bấm một dòng → mở SỔ CHI TIẾT của đối tượng đó (PRD §5.1). Cả dòng bấm được
                // cho dễ trúng, nhưng phím vẫn phải đi được — thiếu `role`/`tabIndex`/Enter là
                // người dùng bàn phím mất hẳn đường vào sổ chi tiết.
                <tr
                  key={`${d.doi_tuong_id ?? "khac"}-${d.ten}`}
                  className={[
                    d.doi_tuong_id === null ? "bccn__row--khac" : "",
                    "bccn__row--mo",
                  ].filter(Boolean).join(" ")}
                  role="button"
                  tabIndex={0}
                  aria-label={`Xem sổ chi tiết công nợ của ${d.ten}`}
                  onClick={() => setXemSo({ id: d.doi_tuong_id, ten: d.ten })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setXemSo({ id: d.doi_tuong_id, ten: d.ten });
                    }
                  }}
                >
                  <td className="bccn__ma">{d.ma || <span className="bccn__khong">—</span>}</td>
                  <td className="bccn__ten">
                    <span className="bccn__row-mo-nhan">
                      {d.ten}
                      <span className="bccn__row-action-hint">
                        <Icon name="arrowRight" size={13} />
                      </span>
                    </span>
                    {d.doi_tuong_id === null && (
                      <span className="bccn__nhan-khac" title="Ngoài danh mục">ngoài danh mục</span>
                    )}
                  </td>
                  <td className="bccn__tk-cell">{d.tk || data?.tk || "—"}</td>
                  <td><O v={d.dau_no} /></td>
                  <td className="bccn__het-cum"><O v={d.dau_co} /></td>
                  <td><O v={d.ps_no} /></td>
                  <td className="bccn__het-cum"><O v={d.ps_co} /></td>
                  <td><O v={d.cuoi_no} manh /></td>
                  <td><O v={d.cuoi_co} manh /></td>
                </tr>
              ))}
          </tbody>
          {!loading && dongSo.length > 0 && (
            <tfoot className="bccn__foot">
              <tr>
                <td colSpan={3}>
                  Số dòng = <b>{tongSo.so_dong}</b>
                </td>
                <td><O v={tongSo.dau_no} manh /></td>
                <td className="bccn__het-cum"><O v={tongSo.dau_co} manh /></td>
                <td><O v={tongSo.ps_no} manh /></td>
                <td className="bccn__het-cum"><O v={tongSo.ps_co} manh /></td>
                <td><O v={tongSo.cuoi_no} manh /></td>
                <td><O v={tongSo.cuoi_co} manh /></td>
              </tr>
            </tfoot>
          )}
        </table>
        <p className="bccn__chan">
          Đơn vị: VNĐ. Bảng đối chiếu khớp 100% với file Excel mẫu MISA.
        </p>
      </section>

      {/* Dialog Khóa / Mở kỳ kế toán */}
      <ConfirmDialog
        open={khoaOpen}
        title={khoaHanhDong === "khoa" ? "Khóa kỳ kế toán công nợ" : "Mở lại kỳ kế toán công nợ"}
        confirmLabel={khoaHanhDong === "khoa" ? "Khóa sổ" : "Mở sổ"}
        cancelLabel="Hủy"
        busy={khoaBusy}
        error={khoaError}
        confirmDisabled={!khoaTu || !khoaDen}
        onConfirm={saveKhoa}
        onCancel={() => setKhoaOpen(false)}
      >
        <div className="kho-khoa">
          <div className="kho-khoa__field">
            <span className="kho-khoa__label">Hành động</span>
            <div className="kho-khoa__seg">
              {(
                [
                  ["khoa", "Khóa kỳ"],
                  ["mo", "Mở kỳ"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`kho-khoa__seg-btn${
                    khoaHanhDong === id ? (id === "khoa" ? " is-khoa" : " is-mo") : ""
                  }`}
                  onClick={() => setKhoaHanhDong(id)}
                >
                  <Icon name={id === "mo" ? "lockOpen" : "lock"} size={14} /> {label}
                </button>
              ))}
            </div>
          </div>

          <div className="kho-khoa__row">
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="bccn-khoa-tu">
                Từ ngày{" "}
                <em className="kho-khoa__auto">
                  {khoaHanhDong === "khoa" ? "nối tiếp kỳ trước" : "đúng kỳ đang chọn"}
                </em>
              </label>
              {/* Ô ngày KHOÁ ở CẢ HAI hành động (chủ chốt 04/09/2026: *"mở lại kỳ thì chọn kỳ đã
                  khoá mới nhất để mở chứ, sao lại chọn ngày"*). Khoá kỳ: ngày đầu do máy chủ nối
                  tiếp, không cho chọn lệch. Mở kỳ: chỉ có MỘT đích là mở NGUYÊN kỳ đang xem — bày ô
                  ngày cho gõ là mời người ta mở nửa kỳ hoặc một khoảng chẳng trùng kỳ nào. */}
              <input
                id="bccn-khoa-tu"
                type="date"
                className="input"
                value={khoaTu}
                readOnly
                title={
                  khoaHanhDong === "khoa"
                    ? "Kỳ mới luôn bắt đầu ngay sau ngày chốt cuối cùng — không đè lên kỳ đã chốt, cũng không để hở ngày nào."
                    : "Mở nguyên kỳ đang chọn ở mục Kỳ kế toán — muốn mở kỳ khác thì chọn kỳ đó trước."
                }
              />
            </div>
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="bccn-khoa-den">Đến ngày</label>
              <input
                id="bccn-khoa-den"
                type="date"
                className="input"
                value={khoaDen}
                readOnly={khoaHanhDong === "mo"}
                min={khoaTu || undefined}
                max={homNayISO()}
                onChange={(e) => setKhoaDen(e.target.value)}
                title={
                  khoaHanhDong === "mo"
                    ? "Mở nguyên kỳ đang chọn — không mở nửa kỳ."
                    : undefined
                }
              />
            </div>
          </div>

          {khoaHanhDong === "khoa" && (
            <div className="kho-khoa__field">
              <label className="kho-khoa__label" htmlFor="bccn-khoa-ten">Tên kỳ (tùy chọn)</label>
              <input
                id="bccn-khoa-ten"
                className="input"
                value={khoaTen}
                maxLength={120}
                onChange={(e) => setKhoaTen(e.target.value)}
                placeholder={tenGoiY || "vd: Chốt kì 1 2026"}
              />
            </div>
          )}

          <p className={`kho-khoa__note kho-khoa__note--${khoaHanhDong}`}>
            <Icon name={khoaHanhDong === "mo" ? "lockOpen" : "lock"} size={14} />
            <span>
              {khoaHanhDong === "khoa"
                ? "Các hóa đơn và chứng từ thanh toán phát sinh trong khoảng này sẽ thuộc kỳ đã chốt — hệ thống sẽ lưu snapshot số dư để đối chiếu MISA và chặn chỉnh sửa dữ liệu đã chốt."
                : "Mở lại NGUYÊN kỳ đang chọn để tiếp tục ghi sổ hoặc điều chỉnh chứng từ — chỉ kỳ chốt MỚI NHẤT mới mở được (kỳ đã có kỳ chốt sau nó thì niêm vĩnh viễn). Thao tác mở sổ được ghi lại trong lịch sử hệ thống."}
            </span>
          </p>
        </div>
      </ConfirmDialog>

      {xemSo && (
        <SoChiTietDrawer
          ben={ben}
          doiTuongId={xemSo.id}
          tenLui={xemSo.ten}
          tuNgay={ky.tu}
          denNgay={ky.den}
          onClose={() => setXemSo(null)}
          navigate={navigate}
        />
      )}
    </main>
  );
}
