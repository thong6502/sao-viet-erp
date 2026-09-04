// BÁO CÁO CÔNG NỢ (131 Phải thu · 331 Phải trả) — Theo dõi chi tiết đơn/đợt + Sổ tổng hợp MISA + Khóa kỳ + In chuẩn Excel
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type BaoCaoCongNo,
  type CongNoChiTietPhaiThuRow,
  type CongNoChiTietPhaiTraRow,
  type CongNoKhoaSoTrangThai,
  type CongNoKyRow,
} from "../../../api/client";
import { useCan } from "../../../auth/permissions";
import { useAuth } from "../../../auth/useAuth";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/ConfirmDialog";
import { Icon } from "../../../components/Icons";
import { money } from "../../../utils/format";
import { AgingStrip } from "../components/AgingStrip";
import { printBaoCaoCongNo } from "../../../utils/printBaoCaoCongNo";
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
}: {
  ben: "receivables" | "payables";
  /** Kỳ do VỎ giữ (`BaoCaoKeToanPage`) — để đổi tab không mất kỳ đang chọn. */
  ky: Ky;
  onKy: (ky: Ky) => void;
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
  const [chiTietThu, setChiTietThu] = useState<CongNoChiTietPhaiThuRow[]>([]);
  const [chiTietTra, setChiTietTra] = useState<CongNoChiTietPhaiTraRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  const [q, setQ] = useState("");
  // RỔ TUỔI đang lọc. Lọc chạy ở SERVER (nó giữ mốc rổ) chứ không lọc trên mảng đã tải — giao
  // diện tuyệt đối không gõ lại số ngày 7/15/30/60 ở đâu cả.
  const [roTuoi, setRoTuoi] = useState<string | null>(null);

  // Chế độ xem: "so" = Sổ tổng hợp (mẫu Excel) | "chitiet" = Chi tiết theo đơn / đợt
  const [viewMode, setViewMode] = useState<"so" | "chitiet">("so");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

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

    const pBaoCao = api.accounting.baoCaoCongNo(token, ben, {
      tuNgay: ky.tu,
      denNgay: ky.den,
      roTuoi,
    });
    const pChiTiet =
      ben === "receivables"
        ? api.accounting.congNoChiTietPhaiThu(token, { tuNgay: ky.tu, denNgay: ky.den })
        : api.accounting.congNoChiTietPhaiTra(token, { tuNgay: ky.tu, denNgay: ky.den });

    Promise.all([pBaoCao, pChiTiet])
      .then(([bc, ct]) => {
        setData(bc);
        if (ben === "receivables") {
          setChiTietThu(ct as CongNoChiTietPhaiThuRow[]);
        } else {
          setChiTietTra(ct as CongNoChiTietPhaiTraRow[]);
        }
      })
      .catch((cause) => {
        setError(cause instanceof ApiError ? cause.message : "Không tải được báo cáo công nợ.");
      })
      .finally(() => setLoading(false));
  }, [token, ben, ky.tu, ky.den, roTuoi]);

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

  // Lọc dữ liệu Chi tiết
  const dongChiTiet = useMemo(() => {
    const tim = q.trim().toLowerCase();
    if (ben === "receivables") {
      return chiTietThu.filter((d) => {
        if (!tim) return true;
        return (
          d.customer_name.toLowerCase().includes(tim) ||
          (d.customer_code ?? "").toLowerCase().includes(tim)
        );
      });
    } else {
      return chiTietTra.filter((d) => {
        if (!tim) return true;
        return (
          d.supplier_name.toLowerCase().includes(tim) ||
          (d.supplier_code ?? "").toLowerCase().includes(tim)
        );
      });
    }
  }, [ben, chiTietThu, chiTietTra, q]);

  // Tổng hợp chỉ số KPI
  const kpi = useMemo(() => {
    if (ben === "receivables") {
      const tongNo = chiTietThu.reduce((s, x) => s + x.total_due, 0);
      const tongQuaHan = chiTietThu.reduce((s, x) => s + x.overdue_amount, 0);
      const soDoiTuong = chiTietThu.filter((x) => x.total_due > 0).length;
      return { tongNo, tongQuaHan, soDoiTuong };
    } else {
      const tongNo = chiTietTra.reduce((s, x) => s + x.total_due, 0);
      const tongQuaHan = chiTietTra.reduce((s, x) => s + x.overdue_amount, 0);
      const soDoiTuong = chiTietTra.filter((x) => x.total_due > 0).length;
      return { tongNo, tongQuaHan, soDoiTuong };
    }
  }, [ben, chiTietThu, chiTietTra]);

  // Bung/gập dòng chi tiết
  function toggleExpand(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleExpandAll() {
    if (expandedIds.size > 0) {
      setExpandedIds(new Set());
    } else {
      const allIds =
        ben === "receivables"
          ? chiTietThu.map((x) => x.customer_id)
          : chiTietTra.map((x) => x.supplier_id);
      setExpandedIds(new Set(allIds));
    }
  }

  // In báo cáo (đúng mẫu file Excel)
  function inBaoCao() {
    if (!data) return;
    printBaoCaoCongNo(data);
  }

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
          <Button variant="ghost" onClick={inBaoCao} disabled={!data || loading} title="In báo cáo mẫu chuẩn A4 ngang như file Excel">
            <Icon name="printer" size={14} /> In báo cáo
          </Button>
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

      {/* Dải KPI */}
      <section className="bccn__kpi" aria-label="Tổng quan kỳ">
        <div className="bccn__kpi-o">
          <span className="bccn__kpi-nhan">Tổng nợ kỳ này</span>
          {/* `key` = chính giá trị số — React remount đúng LÚC SỐ ĐỔI (data mới về), không phải
              lúc bấm chọn kỳ (khi bảng còn đang tải số cũ). Loé sai lúc là loé cho vui, không
              phải tín hiệu "số vừa cập nhật". */}
          <div className="bccn__kpi-so" key={kpi.tongNo}>
            <b className="bccn__kpi-val bccn__kpi-val--highlight">{money(kpi.tongNo)}</b>
          </div>
        </div>
        <i className="bccn__kpi-sep" aria-hidden="true" />
        <div className="bccn__kpi-o bccn__kpi-o--manh">
          <span className="bccn__kpi-nhan">Nợ quá hạn</span>
          <div className="bccn__kpi-so" key={kpi.tongQuaHan}>
            {kpi.tongQuaHan > 0 ? (
              <b className="bccn__kpi-val bccn__kpi-val--rust">
                {money(kpi.tongQuaHan)}
                <span className="bccn__kpi-pct">
                  ({Math.round((kpi.tongQuaHan / (kpi.tongNo || 1)) * 100)}%)
                </span>
              </b>
            ) : (
              <b className="bccn__kpi-val bccn__kpi-val--trong">0 đ</b>
            )}
          </div>
        </div>
        <i className="bccn__kpi-sep" aria-hidden="true" />
        <div className="bccn__kpi-o">
          <span className="bccn__kpi-nhan">Đối tượng còn nợ</span>
          <div className="bccn__kpi-so" key={kpi.soDoiTuong}>
            <b className="bccn__kpi-val">{kpi.soDoiTuong} đối tượng</b>
          </div>
        </div>
      </section>

      {/* Toolbar & Quản lý kỳ */}
      <section className="bccn__bar" aria-label="Kỳ báo cáo và bộ lọc">
        <div className="bccn__bar-hang">
          {/* CHỌN KỲ — ô DUY NHẤT quyết định khoảng thời gian (làm lại 04/09/2026).
              Chủ chốt: *"Từ ngày Đến ngày mình không cho chọn ngày nữa, nó hiển thị ngày theo kì
              mình chốt"*. Trước đó có BA thứ cùng đòi quyết định khoảng — ô kỳ, hai ô ngày, và
              bốn nút Tháng này/Quý này — nên kỳ đang xem hay lệch kỳ đã chốt, và badge "Chốt một
              phần" hiện lên liên tục mà không ai hiểu vì sao.
              Danh sách kỳ = NHỮNG LẦN BẤM CHỐT có thật + kỳ hiện tại chưa chốt (server dựng). */}
          <label className="bccn__o bccn__o--ky">
            <span>Kỳ kế toán</span>
            <select
              className="input bccn__select-ky"
              value={`${ky.tu}_${ky.den}`}
              onChange={(e) => {
                const [tu, den] = e.target.value.split("_");
                if (tu && den) {
                  setRoTuoi(null);      // rổ của kỳ cũ vô nghĩa ở kỳ mới
                  onKy({ tu, den });
                }
              }}
            >
              {/* Kỳ đang xem mà KHÔNG có trong danh sách (vd link cũ, hoặc kỳ vừa mở khóa) vẫn
                  phải hiện ra, nếu không ô select nhảy về mục đầu và bảng đổi số dưới chân người
                  đang đọc. */}
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
          </label>

          {/* NGÀY CHỈ ĐỂ ĐỌC — suy từ kỳ đã chọn, không bấm được. Đây chính là chỗ sửa: cho gõ
              ngày lẻ thì kỳ báo cáo không bao giờ khớp kỳ đã chốt. */}
          <div className="bccn__khoang" aria-label="Khoảng ngày của kỳ">
            <span className="bccn__khoang-nhan">Từ ngày</span>
            <b className="bccn__khoang-ngay">{fmtDate(ky.tu)}</b>
            <i className="bccn__mui" aria-hidden="true">→</i>
            <span className="bccn__khoang-nhan">Đến ngày</span>
            <b className="bccn__khoang-ngay">{fmtDate(ky.den)}</b>
          </div>

          {/* BADGE TRẠNG THÁI KỲ — BA trạng thái, không phải hai. "Chốt một phần" nghĩa là kỳ này
              có ngày đã chốt, có ngày chưa. Gộp nó vào "Đang mở" là giấu mất chuyện nửa kỳ đã
              chốt; gộp vào "Đã chốt" thì tệ hơn — sổ nói dối rằng cả kỳ đã đóng. */}
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

        {/* DẢI PHÂN TUỔI NỢ — dùng lại `AgingStrip` của hai màn Công nợ, KHÔNG vẽ cái thứ hai.
            Khác một điểm sống còn: rổ ở đây tính TẠI "Đến ngày" của kỳ, còn bên kia luôn neo vào
            hôm nay. Nhờ thế in lại kỳ tháng 7 vào tháng 9 vẫn ra đúng con số hồi tháng 8.
            Đặt DƯỚI thanh kỳ và TRÊN ô tìm: chọn kỳ trước, rồi mới soi nặng nhẹ, rồi mới lọc. */}
        {/* CHỈ ở chế độ Sổ tổng hợp: rổ lọc trên `data.items` (sổ), còn bảng Chi tiết đơn/đợt
            lấy từ nguồn khác — để dải ở đó thì bấm vào như không có tác dụng. */}
        {viewMode === "so" && (
          <div className="bccn__ro">
            <AgingStrip buckets={data?.aging ?? []} dangChon={roTuoi} onChon={setRoTuoi} />
          </div>
        )}

        <div className="bccn__bar-hang bccn__bar-hang--phu">
          <div className="bccn__tim">
            <Icon name="search" size={14} />
            <input
              className="bccn__tim-o"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm theo mã hoặc tên đối tượng..."
            />
          </div>

          {/* Nút chuyển chế độ xem */}
          <div className="bccn__view-switch">
            <button
              type="button"
              className={`bccn__view-btn${viewMode === "so" ? " is-active" : ""}`}
              onClick={() => setViewMode("so")}
            >
              <Icon name="table" size={13} /> Sổ tổng hợp (mẫu Excel)
            </button>
            <button
              type="button"
              className={`bccn__view-btn${viewMode === "chitiet" ? " is-active" : ""}`}
              onClick={() => {
                // Bỏ lọc rổ khi rời Sổ tổng hợp: dải rổ bị ẩn ở chế độ Chi tiết, để lọc còn treo
                // thì quay lại sổ sẽ thấy danh sách bị cắt mà không hiểu vì sao.
                setRoTuoi(null);
                setViewMode("chitiet");
              }}
            >
              <Icon name="layers" size={13} /> Chi tiết đơn & đợt
            </button>
          </div>

          {/* Ô tick "Ẩn dòng không phát sinh" ĐÃ GỠ (chủ chốt 04/09/2026: *"tôi thấy nó có tác
              dụng gì đâu"* — đúng). Nó lọc "cả 6 cột đều 0", mà máy chủ đã bỏ sạch dòng đó trước
              khi trả về (`_Gom.ket_qua(an_dong_trong=True)`, không chỗ gọi nào truyền False, cũng
              không có query param để tắt) — nên bật/tắt đều ra cùng một danh sách.
              Cần lại thì phải nối THẬT từ máy chủ (trả về cả đối tượng dư 0 / không phát sinh),
              chứ đừng dựng lại mỗi cái công tắc ở giao diện. */}
          {viewMode === "chitiet" && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={toggleExpandAll}>
              {expandedIds.size > 0 ? "Thu gọn tất cả" : "Mở rộng tất cả"}
            </button>
          )}

          <span className="bccn__dem">
            {loading
              ? "Đang tải…"
              : viewMode === "so"
                ? `${dongSo.length} đối tượng${roTuoi ? " · đang lọc theo rổ tuổi" : ""}`
                : `${dongChiTiet.length} đối tượng`}
          </span>
        </div>
      </section>

      {error && <div className="alert alert--error">{error}</div>}

      {/* CHẾ ĐỘ 1: BẢNG SỔ TỔNG HỢP MẪU EXCEL MISA */}
      {viewMode === "so" && (
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
                  <tr
                    key={`${d.doi_tuong_id ?? "khac"}-${d.ten}`}
                    className={d.doi_tuong_id === null ? "bccn__row--khac" : undefined}
                  >
                    <td className="bccn__ma">{d.ma || <span className="bccn__khong">—</span>}</td>
                    <td className="bccn__ten">
                      <span>{d.ten}</span>
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
            Đơn vị: VNĐ. Bảng đối chiếu khớp 100% với file Excel mẫu MISA. Bấm nút "In báo cáo" để in bản A4 ngang.
          </p>
        </section>
      )}

      {/* CHẾ ĐỘ 2: BẢNG MASTER-DETAIL CHI TIẾT THEO ĐƠN & ĐỢT GIAO */}
      {viewMode === "chitiet" && (
        <section className="bccn__wrap">
          <table className="bccn__table bccn__table--detail">
            <thead>
              <tr>
                <th style={{ width: 44 }}></th>
                <th style={{ width: 120 }}>Mã đối tượng</th>
                <th>Tên đối tượng</th>
                <th style={{ width: 140, textAlign: "right" }}>Hạn mức tín dụng</th>
                <th style={{ width: 140, textAlign: "right" }}>Tổng nợ</th>
                <th style={{ width: 140, textAlign: "right" }}>Nợ quá hạn</th>
                <th style={{ width: 100, textAlign: "center" }}>Số đơn / đợt</th>
              </tr>
            </thead>
            <tbody>
              {loading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={`sk-ct-${i}`} className="purchase__skeleton-row">
                    <td colSpan={7}>
                      <div className="purchase__skeleton-bar" style={{ width: "100%", height: 24 }} />
                    </td>
                  </tr>
                ))}
              {!loading && dongChiTiet.length === 0 && (
                <tr>
                  <td colSpan={7} className="bccn__trong">
                    Không có phát sinh công nợ chi tiết nào trong kỳ.
                  </td>
                </tr>
              )}
              {!loading &&
                dongChiTiet.map((item) => {
                  const id = ben === "receivables" ? (item as CongNoChiTietPhaiThuRow).customer_id : (item as CongNoChiTietPhaiTraRow).supplier_id;
                  const code = ben === "receivables" ? (item as CongNoChiTietPhaiThuRow).customer_code : (item as CongNoChiTietPhaiTraRow).supplier_code;
                  const name = ben === "receivables" ? (item as CongNoChiTietPhaiThuRow).customer_name : (item as CongNoChiTietPhaiTraRow).supplier_name;
                  const isExp = expandedIds.has(id);
                  const vuot = item.credit_limit > 0 && item.total_due > item.credit_limit;

                  return (
                    <Fragment key={`item-${id}`}>
                      <tr
                        className={`bccn__master-row${isExp ? " is-expanded" : ""}`}
                        onClick={() => toggleExpand(id)}
                      >
                        <td className="bccn__exp-btn">
                          <button
                            type="button"
                            className={`bccn__chevron${isExp ? " is-down" : ""}`}
                            aria-label="Bung/gập chi tiết"
                          >
                            <Icon name="chevron" size={14} />
                          </button>
                        </td>
                        <td className="bccn__ma">{code || "—"}</td>
                        <td className="bccn__ten">
                          <b>{name}</b>
                          {/* KHÔNG lặp lại số tiền vượt — "Hạn mức tín dụng" và "Tổng nợ" đã là
                              hai cột ngay trên chính hàng này, chênh lệch tự suy ra được. Nhắc lại
                              số lần thứ ba cạnh cái tên là thứ làm pill này to hơn cả tên công ty. */}
                          {vuot && (
                            <span className="badge-sem badge-sem--rust bccn__badge-vuot">
                              Vượt hạn mức
                            </span>
                          )}
                        </td>
                        <td className="bccn__col-money">
                          {item.credit_limit > 0 ? money(item.credit_limit) : <span className="bccn__khong">—</span>}
                        </td>
                        <td className="bccn__col-money bccn__tien--manh">
                          {money(item.total_due)}
                        </td>
                        <td className="bccn__col-money">
                          {item.overdue_amount > 0 ? (
                            <span className="bccn__val-rust">{money(item.overdue_amount)}</span>
                          ) : (
                            <span className="bccn__khong">—</span>
                          )}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <span className="bccn__pill-count">{item.items.length} đơn</span>
                        </td>
                      </tr>

                      {/* Dòng chi tiết lồng con */}
                      {isExp && (
                        <tr className="bccn__subtable-row">
                          <td colSpan={7} className="bccn__subtable-cell">
                            <div className="bccn__subtable-box">
                              {ben === "receivables" ? (
                                <table className="bccn__nested-table">
                                  <thead>
                                    <tr>
                                      <th>Mã đơn</th>
                                      <th>Số hóa đơn</th>
                                      <th>Ngày HĐ</th>
                                      <th>Hạn thanh toán</th>
                                      <th style={{ textAlign: "right" }}>Giá trị HĐ</th>
                                      <th style={{ textAlign: "right" }}>Đã thu</th>
                                      <th style={{ textAlign: "right" }}>Còn nợ</th>
                                      <th style={{ textAlign: "center" }}>Trạng thái nợ</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {item.items.length === 0 && (
                                      <tr><td colSpan={8} className="bccn__trong">Không có đơn hàng nào</td></tr>
                                    )}
                                    {item.items.map((sub: any, idx: number) => {
                                      const conNo = sub.remaining_amount ?? 0;
                                      const overdue = sub.overdue_days ?? 0;
                                      return (
                                        <tr key={`rcv-sub-${idx}`}>
                                          <td className="bccn__ma">{sub.order_code || "—"}</td>
                                          <td>{sub.invoice_number || "—"}</td>
                                          <td>{fmtDate(sub.invoice_date)}</td>
                                          <td>{fmtDate(sub.due_date)}</td>
                                          <td style={{ textAlign: "right" }}>{money(sub.amount)}</td>
                                          <td style={{ textAlign: "right" }}>{money(sub.received_amount)}</td>
                                          <td style={{ textAlign: "right", fontWeight: "bold" }}>{money(conNo)}</td>
                                          <td style={{ textAlign: "center" }}>
                                            {conNo <= 0 ? (
                                              <span className="bccn__trang-thai bccn__trang-thai--ok">Đã thanh toán</span>
                                            ) : overdue > 7 ? (
                                              <span className="badge-sem badge-sem--rust">Quá hạn {overdue} ngày</span>
                                            ) : overdue > 0 ? (
                                              <span className="badge-sem badge-sem--amber">Trễ {overdue} ngày</span>
                                            ) : (
                                              <span className="bccn__trang-thai bccn__trang-thai--ok">Trong hạn</span>
                                            )}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              ) : (
                                <table className="bccn__nested-table">
                                  <thead>
                                    <tr>
                                      <th>Mã đơn mua (PMH)</th>
                                      <th>Mã đợt giao</th>
                                      <th>Ngày nhận hàng</th>
                                      <th>Hạn thanh toán</th>
                                      <th style={{ textAlign: "right" }}>Giá trị đợt</th>
                                      <th style={{ textAlign: "right" }}>Đã trả</th>
                                      <th style={{ textAlign: "right" }}>Còn nợ</th>
                                      <th style={{ textAlign: "center" }}>Trạng thái nợ</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {item.items.length === 0 && (
                                      <tr><td colSpan={8} className="bccn__trong">Không có đợt giao nào</td></tr>
                                    )}
                                    {item.items.map((sub: any, idx: number) => {
                                      const conNo = sub.con_no ?? 0;
                                      const overdue = sub.overdue_days ?? 0;
                                      return (
                                        <tr key={`pay-sub-${idx}`}>
                                          <td className="bccn__ma">{sub.purchase_request_code || "—"}</td>
                                          {/* Số đợt TRONG ĐƠN. Lùi về `delivery_id` là hiện
                                              "Đợt #20" cho đợt đầu tiên của một NCC. */}
                                          <td>{sub.delivery_code || `Đợt ${sub.seq_no ?? "?"}`}</td>
                                          <td>{fmtDate(sub.delivery_date)}</td>
                                          <td>{fmtDate(sub.due_date)}</td>
                                          <td style={{ textAlign: "right" }}>{money(sub.delivery_value)}</td>
                                          <td
                                            style={{ textAlign: "right" }}
                                            title={
                                              sub.coc_bu
                                                ? `Gồm ${money(sub.coc_bu)} từ tiền cọc của cả đơn bù xuống đợt này`
                                                : undefined
                                            }
                                          >
                                            {money(sub.paid_amount)}
                                          </td>
                                          <td style={{ textAlign: "right", fontWeight: "bold" }}>{money(conNo)}</td>
                                          <td style={{ textAlign: "center" }}>
                                            {conNo <= 0 ? (
                                              <span className="bccn__trang-thai bccn__trang-thai--ok">Đã thanh toán</span>
                                            ) : overdue > 7 ? (
                                              <span className="badge-sem badge-sem--rust">Quá hạn {overdue} ngày</span>
                                            ) : overdue > 0 ? (
                                              <span className="badge-sem badge-sem--amber">Trễ {overdue} ngày</span>
                                            ) : (
                                              <span className="bccn__trang-thai bccn__trang-thai--ok">Trong hạn</span>
                                            )}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
            </tbody>
            <tfoot className="bccn__foot">
              <tr>
                <td colSpan={3}>
                  Tổng cộng: <b>{dongChiTiet.length} đối tượng</b>
                </td>
                <td></td>
                <td style={{ textAlign: "right", fontWeight: "bold" }}>{money(kpi.tongNo)}</td>
                <td style={{ textAlign: "right", fontWeight: "bold", color: "var(--rust)" }}>
                  {money(kpi.tongQuaHan)}
                </td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </section>
      )}

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
    </main>
  );
}
