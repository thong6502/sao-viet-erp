// TAB VẬT TƯ của bàn Kế hoạch sản xuất — BẢNG CÂN ĐỐI MASTER + DRAWER CHI TIẾT
//
// Đọc `GET /api/ke-hoach-vat-tu/can-doi`. Gom theo MẶT HÀNG dạng Bảng Master phẳng (chuẩn
// RebuildCatalog / PhieuTinhGia), hiển thị 15-20 mặt hàng/màn hình mà không cần cuộn nhiều.
//
// Click vào dòng → Mở Drawer trượt bên phải (.rc-drawer) xem phân bổ trừ tồn qua từng lệnh sản xuất.
// Tick chọn dòng thiếu → Floating Action Dock ở đáy cho phép tạo Đề nghị mua hàng gộp.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type CanDoiDong,
  type CanDoiKhoaDong,
  type CanDoiMau,
  type CanDoiNhom,
  type CanDoiOut,
  type DeNghiMuaXemTruoc,
  type HangLoai,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BangLoi, ChipGap, EmptyState, Skeleton, classHan, ngay, num } from "./keHoachSxShared";
import { nhanDonVi } from "./lsxBuoc";
import { moTaPhieuMua, tomTatPhieuMua, vetDangKep } from "./phieuMuaNhan";
import { useNapTenDonVi } from "./tenDonVi";

/** Bốn màu — LUÔN kèm chữ, không chỉ dựa màu (a11y). Nhãn nói HỆ QUẢ, không nói màu. */
const MAU_META: Record<CanDoiMau, { label: string; cls: string; hint: string }> = {
  xam: { label: "Đã cấp đủ", cls: "khvt-pill--xam", hint: "Kho đã xuất đủ cho lệnh này." },
  xanh: { label: "Đủ trong kho", cls: "khvt-pill--xanh", hint: "Đủ bằng chính tồn đang có." },
  vang: {
    label: "Đủ nhờ hàng về",
    cls: "khvt-pill--vang",
    hint: "Chỉ đủ nếu lô hàng đang mua về đúng hẹn.",
  },
  do: { label: "Thiếu", cls: "khvt-pill--do", hint: "Không đủ — cần đặt mua thêm." },
  khong_ro: {
    label: "Chưa đánh giá được",
    cls: "khvt-pill--khongro",
    hint: "Chưa quy đổi được về đơn vị kho — hệ thống KHÔNG đoán. Kiểm lại đơn vị của mặt hàng.",
  },
};

function metaCua(mau: CanDoiMau): { label: string; cls: string; hint: string } {
  return MAU_META[mau] ?? {
    label: String(mau),
    cls: "khvt-pill--khongro",
    hint: "Trạng thái mới từ máy chủ mà màn này chưa biết.",
  };
}

const KHUON_META: Record<string, string> = {
  dang_dung: "Đang dùng",
  dang_dat_lam: "Đang đặt làm",
  hong: "Hỏng",
  thanh_ly: "Đã thanh lý",
};

/** Nhãn phân loại mặt hàng ngắn gọn */
function nhanLoaiHang(nhom: CanDoiNhom): { label: string; cls: string } {
  if (nhom.loai_nhom === "cong_cu") return { label: "Khuôn", cls: "khvt-tag--khuon" };
  switch (nhom.hang_loai) {
    case "giay":
      return { label: "Giấy", cls: "khvt-tag--giay" };
    case "muc":
      return { label: "Mực", cls: "khvt-tag--muc" };
    case "khuon":
      return { label: "Khuôn", cls: "khvt-tag--khuon" };
    default:
      return { label: "Vật tư", cls: "khvt-tag--vattu" };
  }
}

/** Khoá duy nhất của một dòng trong cả bảng — dùng cho tick chọn, cho React key, và cho payload đề nghị mua. */
function khoa(nhom: CanDoiNhom, d: CanDoiDong): string {
  return `${nhom.hang_loai}:${nhom.hang_id}:${d.lsx_id ?? ""}:${d.bai_ghep_id ?? ""}:${d.buoc_id ?? ""}`;
}

/** Số theo đơn vị gốc — 2 chữ số thập phân, bỏ phần thập phân vô nghĩa. */
function soGoc(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

type FilterType = "all" | "thieu" | "khong_ro" | "du";

export function VatTuKeHoachView({
  eventTick,
  canDeNghiMua,
  onOpenLsx,
  onSoDo,
  onSoGiuLau,
  onMoFormMua,
}: {
  eventTick?: number;
  canDeNghiMua: boolean;
  onOpenLsx?: (id: number) => void;
  onSoDo?: (n: number) => void;
  /** Badge "giữ lâu" của nút Theo lệnh — server trả kèm bảng cân đối, khỏi gọi `/theo-lenh`. */
  onSoGiuLau?: (n: number) => void;
  /** Mở form "Tạo yêu cầu mua hàng" ĐÃ ĐIỀN SẴN từ bản nháp server vừa tính.
   *
   *  Bảng này không tự dựng form mua thứ hai: form đã có ở màn Yêu cầu mua hàng, việc ở đây chỉ là
   *  đưa số sang. Không truyền callback (màn cha không có `navigate`) thì rơi về đường cũ — tạo
   *  thẳng yêu cầu rồi báo mã, còn hơn một cái nút bấm không ra gì. */
  onMoFormMua?: (nhap: DeNghiMuaXemTruoc) => void;
}) {
  const { token } = useAuth();
  // ĐVT trên màn là TÊN trong danh mục ("tờ" · "bản kẽm"), không phải MÃ ("to" · "kem").
  useNapTenDonVi();
  const [data, setData] = useState<CanDoiOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [filterType, setFilterType] = useState<FilterType>("all");
  const [chon, setChon] = useState<Set<string>>(new Set());
  const [dangGui, setDangGui] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [selectedNhomId, setSelectedNhomId] = useState<string | null>(null);

  // KHÔNG gửi `chi_thieu` theo chip: năm chip lọc ngay trên bảng đã nạp (`nhomsHienThi`), còn
  // gửi lên thì mỗi lần bấm chip là chạy lại cả bảng cân đối toàn xưởng — và số trên các chip
  // khác tụt theo tập đã lọc. Chỉ ô tìm kiếm đi về máy chủ.
  const load = useCallback(() => {
    if (!token) return;
    setErr(null);
    api.keHoachVatTu
      .canDoi(token, { q: q.trim() || undefined })
      .then(setData)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, q]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, eventTick, q]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 6000);
    return () => clearTimeout(t);
  }, [flash]);

  // Tick chỉ có nghĩa với dòng ĐỎ (dòng khác không có gì để mua)
  const dongDo = useMemo(() => {
    const m = new Map<string, { nhom: CanDoiNhom; dong: CanDoiDong }>();
    for (const nhom of data?.items ?? []) {
      if (nhom.loai_nhom !== "vat_tu") continue;
      for (const d of nhom.dong) {
        if (d.trang_thai === "do") m.set(khoa(nhom, d), { nhom, dong: d });
      }
    }
    return m;
  }, [data]);

  useEffect(() => {
    setChon((cu) => {
      const moi = new Set([...cu].filter((k) => dongDo.has(k)));
      return moi.size === cu.size ? cu : moi;
    });
  }, [dongDo]);

  function toggle(k: string) {
    setChon((cu) => {
      const s = new Set(cu);
      if (s.has(k)) s.delete(k);
      else s.add(k);
      return s;
    });
  }

  function tickCaNhom(nhom: CanDoiNhom, bat: boolean) {
    const keys = nhom.dong.filter((d) => d.trang_thai === "do").map((d) => khoa(nhom, d));
    setChon((cu) => {
      const s = new Set(cu);
      for (const k of keys) {
        if (bat) s.add(k);
        else s.delete(k);
      }
      return s;
    });
  }

  const nhoms = data?.items ?? [];
  const tongDo = nhoms.reduce((s, n) => s + n.so_dong_do, 0);
  const tongKhongRo = nhoms.reduce((s, n) => s + n.so_dong_khong_ro, 0);

  const nhomAnToan = useMemo(() => {
    return nhoms.filter((n) => n.so_dong_do === 0 && n.so_dong_khong_ro === 0);
  }, [nhoms]);

  // Báo ngược số dòng đỏ lên trang cha
  useEffect(() => {
    if (data && !q.trim()) {
      onSoDo?.(tongDo + tongKhongRo);
    }
  }, [data, q, tongDo, tongKhongRo, onSoDo]);

  useEffect(() => {
    if (data) onSoGiuLau?.(data.so_giu_lau ?? 0);
  }, [data, onSoGiuLau]);

  // Lọc danh sách theo filterType
  const nhomsHienThi = useMemo(() => {
    if (filterType === "thieu") return nhoms.filter((n) => n.so_dong_do > 0);
    if (filterType === "khong_ro") return nhoms.filter((n) => n.so_dong_khong_ro > 0);
    if (filterType === "du") return nhomAnToan;
    return nhoms;
  }, [nhoms, filterType, nhomAnToan]);

  // Nhóm đang mở trong Drawer
  const selectedNhom = useMemo(() => {
    if (!selectedNhomId) return null;
    return nhoms.find((n) => `${n.hang_loai}-${n.hang_id}` === selectedNhomId) ?? null;
  }, [nhoms, selectedNhomId]);

  // Tổng lượng thiếu tính theo các dòng đã chọn
  const tongKgChon = useMemo(() => {
    let sum = 0;
    for (const k of chon) {
      const item = dongDo.get(k);
      if (item?.dong.thieu) {
        sum += item.dong.thieu;
      }
    }
    return sum;
  }, [chon, dongDo]);

  // Tất cả các dòng đỏ trong danh sách hiển thị đã được tick hết chưa
  const tatCaDongDoHienThi = useMemo(() => {
    const keys: string[] = [];
    for (const nhom of nhomsHienThi) {
      if (nhom.loai_nhom !== "vat_tu") continue;
      for (const d of nhom.dong) {
        if (d.trang_thai === "do") keys.push(khoa(nhom, d));
      }
    }
    return keys;
  }, [nhomsHienThi]);

  const daTickHetMoiDong =
    tatCaDongDoHienThi.length > 0 && tatCaDongDoHienThi.every((k) => chon.has(k));

  function toggleTickTatCa() {
    if (daTickHetMoiDong) {
      setChon((cu) => {
        const s = new Set(cu);
        for (const k of tatCaDongDoHienThi) s.delete(k);
        return s;
      });
    } else {
      setChon((cu) => {
        const s = new Set(cu);
        for (const k of tatCaDongDoHienThi) s.add(k);
        return s;
      });
    }
  }

  async function deNghiMua() {
    if (!token || chon.size === 0) return;
    const dong: CanDoiKhoaDong[] = [...chon]
      .map((k) => dongDo.get(k))
      .filter((x): x is { nhom: CanDoiNhom; dong: CanDoiDong } => !!x)
      .map(({ nhom, dong: d }) => ({
        hang_loai: nhom.hang_loai as HangLoai,
        hang_id: nhom.hang_id,
        lsx_id: d.lsx_id,
        bai_ghep_id: d.bai_ghep_id,
        buoc_id: d.buoc_id,
      }));
    setDangGui(true);
    try {
      // MỞ FORM, KHÔNG TỰ LẬP PHIẾU (20/08/2026, theo yêu cầu chủ). Cửa `xem-truoc` tính đúng thứ
      // đường tạo thật sẽ dùng — số lượng đã gộp theo mặt hàng, nội dung, lệnh nguồn — nhưng KHÔNG
      // ghi gì. NGÀY CẦN HÀNG để trống cho người lập tự gõ (18/09/2026: hệ không suy nữa); ngày đó
      // lưu xong sẽ quay về làm "Ngày cần" của đúng các lệnh đã tick.
      const nhap = await api.keHoachVatTu.xemTruocDeNghiMua(token, dong);
      if (onMoFormMua) {
        onMoFormMua(nhap);
        return;
      }
      // Đường lùi: không sang được màn Yêu cầu mua hàng thì vẫn lập như cũ, đừng để người dùng
      // bấm xong không thấy gì xảy ra. Không có form để gõ ngày ⇒ server báo "Ngày cần hàng bắt
      // buộc" — đúng, vì hệ không được tự điền ngày thay người.
      const r = await api.keHoachVatTu.deNghiMua(token, dong);
      setChon(new Set());
      setFlash(
        `Đã lập yêu cầu mua ${r.code}. Mở màn Mua hàng để xem lại số lượng rồi gửi — hệ thống KHÔNG tự gửi.`,
      );
      load();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDangGui(false);
    }
  }

  return (
    <div className="khvt-view">
      {/* ── 1. UNIFIED CONTROL BAR: StatusTabs tích hợp KPI + Search ── */}
      <div className="khvt-unified-bar">
        <div className="khvt-unified-tabs" role="tablist" aria-label="Bộ lọc kế hoạch vật tư">
          <button
            type="button"
            role="tab"
            aria-selected={filterType === "all"}
            className={`khvt-utab ${filterType === "all" ? "is-active" : ""}`}
            onClick={() => setFilterType("all")}
          >
            <span>Tất cả</span>
            <span className="khvt-utab__count">{num(nhoms.length)}</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={filterType === "thieu"}
            className={`khvt-utab khvt-utab--do ${filterType === "thieu" ? "is-active" : ""}`}
            onClick={() => setFilterType("thieu")}
          >
            <span className="khvt-utab__dot" />
            <span>Cần mua ngay</span>
            {tongDo > 0 && <span className="khvt-utab__count khvt-utab__count--do">{num(tongDo)}</span>}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={filterType === "khong_ro"}
            className={`khvt-utab khvt-utab--khongro ${filterType === "khong_ro" ? "is-active" : ""}`}
            onClick={() => setFilterType("khong_ro")}
          >
            <span className="khvt-utab__dot" />
            <span>Chưa rõ ĐVT</span>
            {tongKhongRo > 0 && (
              <span className="khvt-utab__count khvt-utab__count--khongro">{num(tongKhongRo)}</span>
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={filterType === "du"}
            className={`khvt-utab khvt-utab--du ${filterType === "du" ? "is-active" : ""}`}
            onClick={() => setFilterType("du")}
          >
            <span className="khvt-utab__dot" />
            <span>Đã đủ 100%</span>
            <span className="khvt-utab__count khvt-utab__count--du">{num(nhomAnToan.length)}</span>
          </button>
        </div>

        <div className="khvt-toolbar__search">
          <Icon name="search" size={14} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm mã lệnh, tên giấy, mực, khuôn..."
            aria-label="Tìm trong bảng cân đối vật tư"
          />
          {q && (
            <button
              type="button"
              className="khvt-toolbar__clear"
              onClick={() => setQ("")}
              title="Xoá tìm kiếm"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {flash && (
        <div className="banner banner--success" role="status" aria-live="polite">
          <Icon name="check" size={16} />
          <span>{flash}</span>
        </div>
      )}

      {err && <BangLoi text={err} onRetry={load} />}

      {/* ── 2. ALERT STRIP: Cảnh báo lệnh bỏ qua gọn gàng ── */}
      {(data?.bo_qua.length ?? 0) > 0 && (
        <div className="khvt-alert-inline" role="status">
          <Icon name="help" size={14} />
          <div className="khvt-alert-inline__content">
            <strong>{data!.bo_qua.length} lệnh/bài chưa thể cân đối vật tư:</strong>
            <span className="khvt-alert-inline__items">
              {data!.bo_qua.map((b) => (
                <span key={b.ma} className="khvt-alert-inline__item" title={b.ly_do}>
                  <code>{b.ma}</code> ({b.ly_do})
                </span>
              ))}
            </span>
          </div>
        </div>
      )}

      {/* ── 3. MASTER TABLE: Bảng tổng hợp các mặt hàng ── */}
      {data === null ? (
        <div className="khsx__tablewrap khvt-master-tablewrap">
          <table className="khsx__table khvt-master-table">
            <Skeleton rows={6} cols={7} />
          </table>
        </div>
      ) : nhomsHienThi.length === 0 ? (
        <EmptyState
          icon={q || filterType !== "all" ? "search" : "packageCheck"}
          title={
            q || filterType !== "all"
              ? "Không có mặt hàng nào khớp bộ lọc."
              : "Chưa có nhu cầu vật tư nào cần cân đối."
          }
          sub={
            q || filterType !== "all"
              ? "Thử xoá ô tìm kiếm hoặc chuyển sang tab lọc khác."
              : "Bảng gom nhu cầu của các lệnh ở trạng thái Sẵn sàng · Đã lập kế hoạch · Đã phát hành."
          }
          action={
            q || filterType !== "all" ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setFilterType("all");
                  setQ("");
                }}
              >
                Xoá bộ lọc &amp; Xem tất cả
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="khsx__tablewrap khvt-master-tablewrap">
          <table className="khsx__table khvt-master-table">
            <caption className="sr-only">Bảng cân đối kế hoạch vật tư toàn xưởng</caption>
            <thead>
              <tr>
                {canDeNghiMua && (
                  <th scope="col" className="khvt-th--tick" style={{ width: 40 }}>
                    {tatCaDongDoHienThi.length > 0 ? (
                      <input
                        type="checkbox"
                        checked={daTickHetMoiDong}
                        onChange={toggleTickTatCa}
                        title="Chọn tất cả dòng thiếu đang hiển thị"
                        aria-label="Chọn tất cả dòng thiếu"
                      />
                    ) : (
                      <span className="sr-only">Chọn</span>
                    )}
                  </th>
                )}
                <th scope="col" style={{ minWidth: 260 }}>
                  Mặt hàng &amp; Quy cách
                </th>
                <th scope="col" style={{ width: 170 }}>
                  Tồn / Nhu cầu
                </th>
                <th scope="col" style={{ width: 110 }}>
                  Độ phủ
                </th>
                <th scope="col" className="khsx-th--num" style={{ width: 130 }}>
                  Lượng thiếu
                </th>
                <th scope="col" style={{ minWidth: 170 }}>
                  Lệnh sử dụng
                </th>
                <th scope="col" style={{ minWidth: 185 }}>
                  Trạng thái
                </th>
                <th scope="col" className="khsx__col--opt" style={{ width: 120 }}>
                  Ngày cần
                </th>
              </tr>
            </thead>
            <tbody>
              {nhomsHienThi.map((nhom) => {
                const nhomId = `${nhom.hang_loai}-${nhom.hang_id}`;
                const tag = nhanLoaiHang(nhom);
                const ton = nhom.ton ?? 0;
                const tongCan = nhom.tong_can ?? 0;
                const pct = tongCan > 0 ? Math.min(100, Math.round((ton / tongCan) * 100)) : 100;
                const isThieu = nhom.so_dong_do > 0;
                const isKhongRo = nhom.so_dong_khong_ro > 0;
                const isDu = !isThieu && !isKhongRo;
                // Chỉ bày ở mặt hàng CÒN PHẢI LO — nhóm đã đủ kho mà vẫn đeo mã phiếu thì
                // cột trạng thái toàn chữ, cái cần đọc chìm mất. Drawer vẫn kê đủ.
                const vetMua = isDu ? null : tomTatPhieuMua(nhom.phieu_mua);

                // Màu chỉ số độ phủ — ba trạng thái, nặng nhất thắng:
                //   đỏ  = tồn + hàng đang về vẫn thiếu ⇒ phải mua
                //   vàng = chưa quy đổi được đơn vị ⇒ con số chưa tin được
                //   xanh = đủ, không phải lo
                const mauPhu = isThieu ? "is-deficit" : isKhongRo ? "is-unknown" : "is-full";

                // Tính tổng lượng thiếu của cả nhóm
                const tongThieuNhom = nhom.dong.reduce((s, d) => s + (d.thieu ?? 0), 0);

                // Dòng đỏ thuộc nhóm này
                const keysDo = nhom.dong.filter((d) => d.trang_thai === "do").map((d) => khoa(nhom, d));
                const daTickNhom = keysDo.length > 0 && keysDo.every((k) => chon.has(k));

                // Ngày cần SỚM NHẤT của mặt hàng — chỉ có ở lệnh đã lập yêu cầu mua (ngày người lập
                // gõ). Không lệnh nào đã mua ⇒ trống, hệ không suy.
                const ngayCanSomNhat = nhom.dong
                  .map((d) => d.ngay_can)
                  .filter((v): v is string => !!v)
                  .sort()[0];

                // Lấy danh sách mã lệnh liên quan (tối đa 2 badge + đếm)
                const dsLenh = Array.from(new Set(nhom.dong.map((d) => d.ma).filter(Boolean)));
                const lenhHien = dsLenh.slice(0, 2);
                const lenhDu = dsLenh.length - lenhHien.length;

                return (
                  <tr
                    key={nhomId}
                    className={`khsx__row khvt-master-row ${
                      isThieu ? "khvt-row--thieu" : isKhongRo ? "khvt-row--khongro" : ""
                    } ${daTickNhom ? "khvt-row--chon" : ""}`}
                    onClick={() => setSelectedNhomId(nhomId)}
                  >
                    {canDeNghiMua && (
                      <td className="khvt-td--tick" onClick={(e) => e.stopPropagation()}>
                        {keysDo.length > 0 ? (
                          <input
                            type="checkbox"
                            checked={daTickNhom}
                            onChange={(e) => tickCaNhom(nhom, e.target.checked)}
                            title={`Chọn ${keysDo.length} dòng thiếu của ${nhom.hang_ten}`}
                            aria-label={`Chọn các dòng thiếu của ${nhom.hang_ten}`}
                          />
                        ) : (
                          <span className="khvt-td--empty-tick" />
                        )}
                      </td>
                    )}

                    {/* Cột 1: Mặt hàng — chỉ TÊN, không bày mã danh mục. Người xem bảng cân đối
                        đọc "Bản kẽm khổ 74", không đọc "KEM-74"; ai quen mã thì gõ vào ô tìm kiếm
                        vẫn ra (server lọc cả `hang_ma`). */}
                    <td>
                      <div className="khvt-cell-item">
                        <div className="khvt-cell-item__top">
                          <span className="khvt-item-name" title={nhom.hang_ten ?? undefined}>
                            {nhom.hang_ten ?? "(mặt hàng đã gỡ khỏi danh mục)"}
                          </span>
                          <span className={`khvt-item-tag ${tag.cls}`}>{tag.label}</span>
                        </div>
                      </div>
                    </td>

                    {/* Cột 2: Tồn / Nhu cầu */}
                    <td>
                      <div className="khvt-cell-ton-can">
                        <div className="khvt-ton-can-text">
                          <span className="khvt-ton-val">
                            Tồn <b>{soGoc(nhom.ton)}</b>
                          </span>
                          <span className="khvt-can-sep">/</span>
                          <span className="khvt-can-val">
                            Cần <b>{soGoc(nhom.tong_can)}</b>
                          </span>
                          <span className="khvt-unit-val">{nhanDonVi(nhom.don_vi_goc)}</span>
                        </div>
                        <div className="khvt-mini-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                          <div
                            className={`khvt-mini-bar__fill ${mauPhu}`}
                            style={{ width: `${Math.max(4, pct)}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Cột 3: Độ phủ */}
                    <td>
                      <span className={`khvt-coverage-badge ${mauPhu}`}>
                        {pct}%
                      </span>
                    </td>

                    {/* Cột 4: Lượng thiếu (Shape Pill 999px đồng bộ với Độ phủ & Trạng thái) */}
                    <td className="khsx-num khvt-cell-thieu">
                      {tongThieuNhom > 0 ? (
                        <span className="khvt-deficit-pill" title={`Thiếu ${soGoc(tongThieuNhom)} ${nhanDonVi(nhom.don_vi_goc)}`}>
                          -{soGoc(tongThieuNhom)} {nhanDonVi(nhom.don_vi_goc)}
                        </span>
                      ) : (
                        <span className="khvt-deficit-zero">0 {nhanDonVi(nhom.don_vi_goc)}</span>
                      )}
                    </td>

                    {/* Cột 5: Lệnh sử dụng */}
                    <td>
                      <div className="khvt-cell-lenhs">
                        {lenhHien.map((ma) => (
                          <span key={ma} className="khvt-lenh-pill">
                            {ma}
                          </span>
                        ))}
                        {lenhDu > 0 && (
                          <span className="khvt-lenh-more" title={`Còn ${lenhDu} lệnh khác`}>
                            +{lenhDu}
                          </span>
                        )}
                        {dsLenh.length === 0 && <span className="khsx-muted">—</span>}
                      </div>
                    </td>

                    {/* Cột 6: Trạng thái (2 tầng mạch lạc) */}
                    <td>
                      <div className="khvt-status-cell">
                        {isThieu && (
                          <span className="khvt-badge khvt-badge--do">
                            <Icon name="ban" size={11} /> {nhom.so_dong_do} dòng thiếu
                          </span>
                        )}
                        {isKhongRo && !isThieu && (
                          <span className="khvt-badge khvt-badge--khongro">
                            <Icon name="help" size={11} /> Chưa quy đổi
                          </span>
                        )}
                        {isDu && (
                          <span className="khvt-badge khvt-badge--du">
                            <Icon name="check" size={11} /> Đủ trong kho
                          </span>
                        )}

                        {/* Thẻ thông tin PO ở tầng 2 */}
                        {vetMua && (
                          <div className="khvt-po-note" title={vetMua.title}>
                            <Icon name="cart" size={11} />
                            <span>{vetMua.chinh}</span>
                            {vetMua.them > 0 && <b>+{vetMua.them}</b>}
                            {/* Món kẹt bị `+N` nuốt mất. Chip chỉ khoe phiếu CHẮC NHẤT (đúng luật
                                "tin xấu không che tin tốt"), nên phần đứng lại phải tự gọi tên —
                                không thì nó nằm im trong tooltip, không ai mở ra đọc. */}
                            {vetMua.kep && (
                              <span className="khvt-po-note__kep">
                                <Icon name="alert" size={10} /> có đơn bị từ chối
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Cột 7: Ngày cần — lấy từ yêu cầu mua đã lập, trống nếu chưa mua */}
                    <td className="khsx__col--opt">
                      {ngayCanSomNhat ? (
                        <span
                          className="khvt-date-badge"
                          title="Ngày cần hàng ghi trên yêu cầu mua đã lập (sớm nhất)"
                        >
                          <Icon name="clock" size={11} /> {ngay(ngayCanSomNhat)}
                        </span>
                      ) : (
                        <span className="khvt-date-empty">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 4. FLOATING ACTION DOCK: Thao tác gom đề nghị mua ── */}
      {canDeNghiMua && chon.size > 0 && (
        <div className="khvt-floating-dock" role="region" aria-label="Thao tác với dòng đã chọn">
          <div className="khvt-floating-dock__inner">
            <div className="khvt-floating-dock__info">
              <span className="khvt-floating-dock__count">
                Đã chọn <b>{chon.size}</b> dòng thiếu
              </span>
              {tongKgChon > 0 && (
                <span className="khvt-floating-dock__total">
                  Tổng nhu cầu: <b>{soGoc(tongKgChon)} kg</b>
                </span>
              )}
              <span className="khvt-floating-dock__hint">
                Mở form yêu cầu mua đã điền sẵn — xem lại số rồi bấm Lưu.
              </span>
            </div>

            <div className="khvt-floating-dock__actions">
              <Button variant="secondary" onClick={() => setChon(new Set())}>
                Bỏ chọn
              </Button>
              <Button onClick={deNghiMua} disabled={dangGui} className="khvt-btn-action">
                <Icon name="packageCheck" size={15} />
                {dangGui ? "Đang mở form…" : `Đề nghị mua ngay (${chon.size})`}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── 5. DRAWER CHI TIẾT MẶT HÀNG (VatTuDetailDrawer) ── */}
      {selectedNhom && (
        <VatTuDetailDrawer
          nhom={selectedNhom}
          chon={chon}
          canDeNghiMua={canDeNghiMua}
          onToggle={toggle}
          onTickNhom={tickCaNhom}
          onClose={() => setSelectedNhomId(null)}
          onOpenLsx={onOpenLsx}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DRAWER CHI TIẾT MẶT HÀNG — Phân rã lịch trình & tiêu thụ từng lệnh
// ─────────────────────────────────────────────────────────────────────────────
function VatTuDetailDrawer({
  nhom,
  chon,
  canDeNghiMua,
  onToggle,
  onTickNhom,
  onClose,
  onOpenLsx,
}: {
  nhom: CanDoiNhom;
  chon: Set<string>;
  canDeNghiMua: boolean;
  onToggle: (k: string) => void;
  onTickNhom: (nhom: CanDoiNhom, bat: boolean) => void;
  onClose: () => void;
  onOpenLsx?: (id: number) => void;
}) {
  const keysDo = nhom.dong.filter((d) => d.trang_thai === "do").map((d) => khoa(nhom, d));
  const daTickHet = keysDo.length > 0 && keysDo.every((k) => chon.has(k));

  const ton = nhom.ton ?? 0;
  const tongCan = nhom.tong_can ?? 0;
  const pct = tongCan > 0 ? Math.min(100, Math.round((ton / tongCan) * 100)) : 100;
  const isThieu = nhom.so_dong_do > 0;
  // Cùng luật màu với bảng: đỏ (phải mua) > vàng (chưa quy đổi) > xanh.
  const mauPhu = isThieu ? "is-deficit" : nhom.so_dong_khong_ro > 0 ? "is-unknown" : "is-full";
  const tag = nhanLoaiHang(nhom);
  const tongThieuNhom = nhom.dong.reduce((s, d) => s + (d.thieu ?? 0), 0);

  // Đóng bằng phím Esc
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="rc-drawer__scrim khvt-drawer-scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer rc-drawer--wide khvt-drawer" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <header className="rc-drawer__head khvt-drawer__head">
          <div>
            <div className="rc-drawer__kicker">
              <span className={`khvt-item-tag ${tag.cls}`}>{tag.label}</span>
              <span>Kế hoạch vật tư · Chi tiết cân đối</span>
            </div>
            <h2 className="rc-drawer__title khvt-drawer__title">
              {nhom.hang_ten}
            </h2>
            <div className="khvt-drawer__subline">
              <span>Mã vật tư:</span>
              <span className="khvt-drawer__code">{nhom.hang_ma ?? "—"}</span>
            </div>
          </div>
          <button type="button" className="khvt-drawer__x" onClick={onClose} aria-label="Đóng">
            <Icon name="x" size={16} />
          </button>
        </header>

        {/* Drawer Body */}
        <div className="rc-drawer__body khvt-drawer__body">
          {/* Dải KPI Compact (§4 UI_DESIGN.md) */}
          <div className="khvt-drawer-kpi-grid">
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">Tồn khả dụng</span>
              <span className="khvt-bento-kpi__val">
                {soGoc(nhom.ton)} {nhanDonVi(nhom.don_vi_goc)}
              </span>
            </div>
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">Tổng nhu cầu</span>
              <span className="khvt-bento-kpi__val">
                {soGoc(nhom.tong_can)} {nhanDonVi(nhom.don_vi_goc)}
              </span>
            </div>
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">Cân đối</span>
              <span className="khvt-bento-kpi__val">
                {tongThieuNhom > 0 ? (
                  <span className="khvt-bento-kpi__val--deficit">
                    -{soGoc(tongThieuNhom)} {nhanDonVi(nhom.don_vi_goc)}
                  </span>
                ) : (
                  <span className="khvt-bento-kpi__val--ok">
                    0 {nhanDonVi(nhom.don_vi_goc)}
                  </span>
                )}
              </span>
            </div>
            <div className="khvt-bento-kpi">
              <span className="khvt-bento-kpi__label">Độ phủ kho</span>
              <div className="khvt-bento-kpi__cov">
                <span className="khvt-bento-kpi__cov-pct">{pct}%</span>
                <div className="khvt-mini-bar">
                  <div
                    className={`khvt-mini-bar__fill ${mauPhu}`}
                    style={{ width: `${Math.max(4, pct)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Phiếu ĐANG CHẠY của món — trả lời "đã có ai lo chưa" trước khi người dùng bấm Mua.
              Bày ĐỦ danh sách (không cắt như trên bảng): drawer là chỗ tra, và hai phiếu cùng số
              lượng nằm cạnh nhau chính là dấu hiệu ai đó đã đề nghị trùng. */}
          {(nhom.phieu_mua ?? []).length > 0 && (
            <div className="khvt-recommend-box">
              <div className="khvt-recommend-box__badge khvt-recommend-box__badge--warn">
                <Icon name="cart" size={16} />
              </div>
              <div className="khvt-recommend-box__content">
                Món này <b>đã có {nhom.phieu_mua.length} phiếu đang chạy</b> — kiểm trước khi đề
                nghị mua thêm, tránh đặt trùng:
                <ul className="khvt-po-list">
                  {nhom.phieu_mua.map((pm) => (
                    <li key={pm.ma} className={vetDangKep(pm) ? "khvt-po--kep" : undefined}>
                      <span className="khvt-po-list__loai">
                        {pm.loai === "pmh" ? "Phiếu mua" : "Đề nghị"}
                      </span>
                      {moTaPhieuMua(pm, { dayDu: true })}
                      {/* Món kẹt: nói luôn VIỆC CẦN LÀM. "Đơn bị từ chối" mà không kèm câu này thì
                          người đọc vẫn ngồi chờ, vì mọi dòng khác trong danh sách đều đang chạy. */}
                      {vetDangKep(pm) && (
                        <em className="khvt-po-list__kep">
                          — đang đứng, cần thu mua lập lại đơn
                        </em>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Công cụ khuôn bế ghi chú */}
          {nhom.loai_nhom === "cong_cu" && (
            <div className="khvt-recommend-box">
              <div className="khvt-recommend-box__badge khvt-recommend-box__badge--warn">
                <Icon name="help" size={16} />
              </div>
              <div className="khvt-recommend-box__content">
                Khuôn không mua tự động. Vui lòng sang <b>Mua hàng → Yêu cầu của bộ phận</b> để tạo
                phiếu đặt làm khuôn mã <b>{nhom.hang_ma ?? "—"}</b>.
                {nhom.khuon_tinh_trang && (
                  <span className="khvt-badge khvt-badge--khongro" style={{ marginLeft: 8 }}>
                    {KHUON_META[nhom.khuon_tinh_trang] ?? nhom.khuon_tinh_trang}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Bảng phân rã các lệnh tiêu thụ */}
          <div className="khvt-drawer-breakdown">
            <div className="khvt-drawer-breakdown__head">
              <h3 className="khvt-drawer-breakdown__title">
                Phân bổ tiêu thụ theo thứ tự hạn sản xuất ({nhom.dong.length} lệnh)
              </h3>
              {canDeNghiMua && keysDo.length > 0 && (
                <label className="khvt-tickall">
                  <input
                    type="checkbox"
                    checked={daTickHet}
                    onChange={(e) => onTickNhom(nhom, e.target.checked)}
                  />
                  <span>Chọn hết ({keysDo.length} dòng thiếu)</span>
                </label>
              )}
            </div>

            <div className="khsx__tablewrap">
              <table className="khsx__table khvt-table">
                <thead>
                  <tr>
                    {canDeNghiMua && (
                      <th scope="col" className="khvt-th--tick">
                        <span className="sr-only">Chọn</span>
                      </th>
                    )}
                    <th scope="col" style={{ width: 110 }}>
                      Ngày cần
                    </th>
                    <th scope="col">Lệnh / Công đoạn</th>
                    <th scope="col" className="khsx-th--num" style={{ width: 130 }}>
                      Nhu cầu
                    </th>
                    <th scope="col" className="khsx-th--num" style={{ width: 140 }}>
                      Còn lại sau
                    </th>
                    <th scope="col" style={{ width: 160 }}>
                      Trạng thái
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {nhom.dong.map((d) => {
                    const k = khoa(nhom, d);
                    const meta = metaCua(d.trang_thai);
                    const chonDuoc = canDeNghiMua && d.trang_thai === "do";
                    const isConLaiAm = (d.con_lai_sau ?? 0) < 0;

                    return (
                      <tr key={k} className={`khsx__row ${chon.has(k) ? "khvt-row--chon" : ""}`}>
                        {canDeNghiMua && (
                          <td className="khvt-td--tick">
                            {chonDuoc ? (
                              <input
                                type="checkbox"
                                checked={chon.has(k)}
                                onChange={() => onToggle(k)}
                                aria-label={`Chọn dòng ${d.ma}`}
                              />
                            ) : (
                              <span className="khvt-td--empty-tick" />
                            )}
                          </td>
                        )}

                        <td
                          className={`khvt-cell-date ${classHan(d.ngay_can)}`}
                          title={d.ngay_can ? "Ngày cần hàng ghi trên yêu cầu mua đã lập" : "Chưa lập yêu cầu mua cho lệnh này"}
                        >
                          <span className="khvt-date-val">{ngay(d.ngay_can)}</span>
                        </td>

                        <td>
                          <div className="khvt-cell-lsx">
                            {d.lsx_id && onOpenLsx ? (
                              <button
                                type="button"
                                className="khvt-lsx-link"
                                onClick={() => onOpenLsx(d.lsx_id!)}
                                title="Mở chi tiết lệnh sản xuất"
                              >
                                {d.ma}
                              </button>
                            ) : (
                              <span className="khvt-lsx-code">{d.ma}</span>
                            )}
                            {d.is_rush && <ChipGap />}
                          </div>
                          {d.ten_viec && <div className="khvt-lsx-sub">{d.ten_viec}</div>}
                        </td>

                        <td className="khsx-num khvt-num-cell">
                          <div className="khvt-num-primary">{d.nhu_cau_hien_thi}</div>
                          <div className="khvt-sub-pills">
                            {(d.da_cap ?? 0) > 0 && (
                              <span className="khvt-cap-pill khvt-cap-pill--ok">
                                cấp {soGoc(d.da_cap)} {nhanDonVi(nhom.don_vi_goc)}
                              </span>
                            )}
                            {(d.dang_linh ?? 0) > 0 && (
                              <span className="khvt-cap-pill khvt-cap-pill--warn">
                                lĩnh {soGoc(d.dang_linh)} {nhanDonVi(nhom.don_vi_goc)}
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="khsx-num khvt-num-cell">
                          {isConLaiAm ? (() => {
                            const valThieu = d.thieu ?? (d.con_lai_sau != null ? Math.abs(d.con_lai_sau) : 0);
                            return (
                              <div className="khvt-deficit-pill" title={`Thiếu ${soGoc(valThieu)} ${nhanDonVi(nhom.don_vi_goc)}`}>
                                <b>Thiếu -{soGoc(valThieu)}</b>
                                <small>{nhanDonVi(nhom.don_vi_goc)}</small>
                              </div>
                            );
                          })() : (
                            <span className="khvt-num-primary">{soGoc(d.con_lai_sau)}</span>
                          )}
                        </td>

                        <td>
                          <span className={`khsx-pill ${meta.cls}`} title={meta.hint}>
                            <span className="khsx-pill__dot" aria-hidden="true" />
                            {meta.label}
                          </span>
                          {d.canh_bao.includes("khong_doi_chieu_duoc") && (
                            <div className="khsx-warn-inline">
                              <Icon name="help" size={11} /> chưa quy đổi ĐVT
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Drawer Foot */}
        <footer className="rc-drawer__foot khvt-drawer__foot">
          <Button variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          {canDeNghiMua && keysDo.length > 0 && (
            <Button
              className="khvt-btn-action"
              onClick={() => onTickNhom(nhom, true)}
              disabled={daTickHet}
            >
              <Icon name="packageCheck" size={15} />
              {daTickHet ? "Đã chọn dòng thiếu" : `Chọn ${keysDo.length} dòng thiếu để mua`}
            </Button>
          )}
        </footer>
      </aside>
    </div>
  );
}

