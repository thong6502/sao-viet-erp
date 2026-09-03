// Màn "Hồ sơ lệnh sản xuất" — bàn của người ĐI TRA (điều độ · QC · trưởng phòng KD · sale).
// Trả lời đúng một câu: "lệnh này đang ở đâu, có kịp không".
//
// ⚠️ MÀN NÀY KHÔNG GHI GÌ CẢ. Không Tạo LSX · không Xuất/Nhập Excel · không Nhân bản · không Xóa ·
// không nút điều hành (Bắt đầu/Tạm dừng/Kết thúc/Giao người/Rút người) · không sửa routing. Toàn
// bộ control bấm được chỉ có 5 loại: đổi tab · đổi bộ lọc · gõ ô tìm · lật trang · mở hồ sơ.
// Tạo/sửa lệnh vẫn ở màn Kế hoạch sản xuất (module `san_xuat`); đây là module RIÊNG
// (`lenh_san_xuat`) vì khác người, khác quyền. Thiết kế chốt: `docs/design-ho-so-lenh-san-xuat-ui.md`.
//
// ⚠️ KHÔNG MỘT SỐ TIỀN NÀO, kể cả trong `title`. Máy chủ đã không trả (`test_khong_lo_tien` giữ);
// đừng tính bù ở đây.
//
// ⚠️ LỌC + ĐẾM + CẮT TRANG ĐỀU Ở MÁY CHỦ. Không `rows.filter`, không `rows.slice`, không đếm số
// trên tab từ `items`: trang chỉ cầm 50 dòng trên một tập có thể cả trăm — đếm ở đây là in ra một
// con số sai mà không ai thấy sai.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type {
  LenhSxItem,
  LenhSxMayLoc,
  LenhSxSummaryOut,
  LsxTheoDoiCanhBao,
  LsxTheoDoiTab,
  LsxTheoDoiTrangThai,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { NavigateFn } from "../components/AppShell";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { Pager, trangHopLe } from "../components/Pager";
import { useTre } from "../lib/useTre";
import { LenhSxHoSoView } from "./LenhSxHoSoView";
import {
  BangLoi,
  ChipGap,
  EmptyState,
  NHOM_CONG_DOAN,
  Skeleton,
  classHan,
  ngay,
  ngayGio,
  num,
} from "./keHoachSxShared";
// `ke-hoach-sx.css` NẠP TRƯỚC vì màn này mượn `ChipGap` / `EmptyState` / `Skeleton` / `classHan`
// của `keHoachSxShared` — bốn thứ đó ăn class `.khsx-*` mà file kia định nghĩa, còn
// `keHoachSxShared.tsx` thì không tự nạp CSS. Hôm nay AppShell import tĩnh `KeHoachSXPage` nên nó
// vốn đã có trong bundle; khai ở đây để ngày nào màn kia chuyển sang lazy-load thì màn này không
// mất hình. Nạp TRƯỚC để mọi rule `.hslsx` bên dưới thắng khi trùng độ ưu tiên.
import "./ke-hoach-sx.css";
import "./lenh-san-xuat.css";

/** Số dòng mỗi trang. Bằng `danh_sach.PAGE_SIZE_MAC_DINH` ở máy chủ nên không đẻ ra con số thứ hai
 *  phải nhớ.
 *
 *  Vì sao 50 chứ không phải 20 như màn danh mục: chi phí MỘT request ở đây KHÔNG phụ thuộc
 *  `page_size` — tầng 1 quét trọn tập lệnh trong phạm vi rồi tầng 2 mới cắt trang (docstring
 *  `services/lenh_sx/danh_sach.py`). Trang nhỏ = nhiều request = nhiều lượt quét. Bảng có
 *  `max-height` + cuộn dọc nên 50 dòng vẫn gọn.
 *
 *  ⚠️ KHÔNG export: con số của MÀN NÀY. */
const PAGE_SIZE = 50;

/** Gộp sự kiện SSE rồi mới tải lại. Chuyền chạy thì sự kiện tới liên tục — refetch mỗi cái là
 *  bảng nhấp nháy dưới tay người đang đọc. */
const SSE_GOP_MS = 2000;

/** Bảy tab. Chuỗi khoá là HỢP ĐỒNG (đi thẳng ra `?tab=` và khớp `danh_sach.TAB_CHO_PHEP`) —
 *  đừng đổi. Thứ tự trái→phải = dòng chảy của lệnh, với Cảnh báo chen ngay sau Đang SX vì đó là
 *  hai tab điều độ bấm nhiều nhất trong ngày. */
const TABS: { key: LsxTheoDoiTab; label: string }[] = [
  { key: "tat_ca", label: "Tất cả" },
  { key: "dang_sx", label: "Đang SX" },
  { key: "canh_bao", label: "Cảnh báo" },
  { key: "kcs", label: "KCS" },
  { key: "cho_nhap_kho", label: "Chờ nhập kho" },
  { key: "san_sang_giao", label: "Sẵn sàng giao" },
  { key: "hoan_thanh", label: "Hoàn thành" },
];

/** Pill trạng thái — bộ RIÊNG của màn này (6 giá trị của `trang_thai.TAB_CHINH`), KHÔNG phải bộ
 *  nhãn vòng đời lệnh của màn Kế hoạch SX. Hai bộ khác nhau nên không nhét chung vào
 *  `keHoachSxShared`. Luôn có CHỮ, không bao giờ chỉ dựa màu. */
const PILL: Record<LsxTheoDoiTrangThai, { label: string; cls: string }> = {
  dang_sx: { label: "Đang SX", cls: "hslsx-pill--steel" },
  canh_bao: { label: "Cảnh báo", cls: "hslsx-pill--signal" },
  kcs: { label: "KCS", cls: "hslsx-pill--plum" },
  cho_nhap_kho: { label: "Chờ nhập kho", cls: "hslsx-pill--amber" },
  san_sang_giao: { label: "Sẵn sàng giao", cls: "hslsx-pill--moss" },
  hoan_thanh: { label: "Hoàn thành", cls: "hslsx-pill--xong" },
};

/** Badge cảnh báo. Pill và badge KHÔNG nói trùng nhau: pill trả lời "lệnh đang ở khâu nào",
 *  badge trả lời "vì cái gì mà nó bị giữ lại". Thứ tự máy chủ trả đã ổn định — đừng sort lại. */
const CANH_BAO: Record<LsxTheoDoiCanhBao, { label: string; cls: string }> = {
  su_co: { label: "Sự cố", cls: "hslsx-badge--signal" },
  tam_dung: { label: "Tạm dừng", cls: "hslsx-badge--amber" },
  tre_han: { label: "Trễ hạn", cls: "hslsx-badge--signal" },
  kcs_khong_dat: { label: "KCS không đạt", cls: "hslsx-badge--signal" },
  thieu_vat_tu: { label: "Thiếu vật tư", cls: "hslsx-badge--amber" },
};

/** Ô `<input type="date">` cho gõ năm 6 chữ số và đẻ ra giá trị rác → máy chủ trả 422 CÂM (bẫy đã
 *  dính ở màn khác). Phân biệt BA ca: trống (không gửi, không báo) · gõ sai (không gửi + viền
 *  cảnh báo) · hợp lệ (gửi). */
function ngayHopLe(v: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const nam = Number(v.slice(0, 4));
  if (nam < 2000 || nam > 2999) return false;
  return !Number.isNaN(new Date(v).getTime());
}

/** Giờ HH:MM cho dòng "Vừa cập nhật" ở chân bảng. */
function gioPhut(d: Date): string {
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function LenhSanXuatPage({
  eventTick,
  navigate,
  openHoSoId,
  openHoSoPv,
  openHoSoSeq,
}: {
  /** Nhích theo MỌI sự kiện SSE của AppShell. Màn gộp lại rồi mới tải lại (xem `SSE_GOP_MS`). */
  eventTick?: number;
  /** Chỉ để hồ sơ có đường đi tiếp sang màn Đơn hàng bán (liên kết tạo yêu cầu giao hàng). Bảng
   *  này tự nó KHÔNG điều hướng đi đâu cả. Chưa truyền ⇒ liên kết đó không được vẽ ra. */
  navigate?: NavigateFn;
  /** Deep link QR phiếu công nghệ (Task 14): AppShell đọc hash `#lsx=&pv=` rồi bơm xuống đây qua
   *  `navParams.openHoSoLsxId`. Có giá trị ⇒ mở NGAY hồ sơ đó, không đợi người dùng tự tìm dòng
   *  trong bảng phía sau (bảng vẫn tải như thường — hồ sơ chỉ VẼ ĐÈ lên nó). */
  openHoSoId?: number | null;
  /** Đi kèm `openHoSoId`: phiên bản in trên tờ giấy đã quét, truyền tiếp cho băng cảnh báo của hồ
   *  sơ (xem `LenhSxHoSoView`). Mở hồ sơ bằng cách bấm DÒNG trong bảng thì không có giá trị này —
   *  đó không phải một tờ giấy đang cầm, không có gì để so. */
  openHoSoPv?: number | null;
  /** `navParams.navSeq` của AppShell — tăng mỗi lượt `navigate(...)`, kể cả khi `openHoSoId`/
   *  `openHoSoPv` ra CÙNG giá trị như lượt trước (Task 14, lỗi N1 vòng rà lại: quét LẠI đúng tờ
   *  giấy vừa đóng ngăn kéo thì hai giá trị nguyên thuỷ kia không đổi, effect bên dưới không có gì
   *  để phân biệt hai lượt và im lặng không mở lại). Chỉ dùng để KÍCH effect chạy lại — thân effect
   *  không đọc giá trị của nó. */
  openHoSoSeq?: number | null;
}) {
  const { token } = useAuth();

  // --- bộ lọc (tất cả chạy Ở MÁY CHỦ) ---------------------------------------
  const [q, setQ] = useState("");
  const qTre = useTre(q); // gõ xong 300ms mới hỏi máy chủ
  const [nhomCd, setNhomCd] = useState("");
  const [mayId, setMayId] = useState("");
  const [uuTien, setUuTien] = useState("");
  const [tuNgay, setTuNgay] = useState("");
  const [denNgay, setDenNgay] = useState("");
  const [chiTre, setChiTre] = useState(false);
  const [tab, setTab] = useState<LsxTheoDoiTab>("tat_ca");
  const [page, setPage] = useState(1);

  // --- hồ sơ một lệnh --------------------------------------------------------
  // Hồ sơ vẽ ĐÈ lên bảng chứ không thay màn. Chín thứ ngay trên kia (`q`…`page`) đều là state cục
  // bộ của component này: hoán màn ⇒ React tháo component ⇒ về lại là tab "Tất cả", bộ lọc trắng,
  // trang 1, cuộn về đầu. Người điều độ lọc "Cảnh báo + máy X + chỉ trễ", cuộn xuống dòng thứ 30,
  // mở một lệnh ra xem rồi quay lại phải thấy y nguyên chỗ cũ — giữ bảng mounted là cách duy nhất
  // có được điều đó mà không phải nâng cả chín thứ lên URL.
  const [hoSoId, setHoSoId] = useState<number | null>(null);
  // Phiên bản in trên tờ giấy đã quét (Task 14, deep link QR) — CHỈ có giá trị khi hồ sơ được mở
  // qua `openHoSoId`/`openHoSoPv`. Mở tay bằng cách bấm dòng trong bảng thì không có tờ giấy nào
  // để so, phải là `null` (xem `moHoSoTay` bên dưới).
  const [hoSoPv, setHoSoPv] = useState<number | null>(null);

  // Deep link QR: props đổi (AppShell vừa đọc hash `#lsx=&pv=` xong) ⇒ mở hồ sơ đó ngay, kể cả khi
  // đang mở sẵn một hồ sơ khác (quét mã mới trong lúc đang xem lệnh khác là tình huống thật — tổ
  // trưởng cầm điện thoại đi qua nhiều máy). Không có `openHoSoId` (giá trị `null`/`undefined`,
  // trang mở bình thường không qua QR) thì không làm gì — KHÔNG tự đóng hồ sơ đang mở tay.
  //
  // `openHoSoSeq` trong deps (sửa vòng 2, lỗi N1): quét LẠI đúng lệnh vừa đóng cho ra CÙNG cặp
  // `openHoSoId`/`openHoSoPv` như lần trước — chỉ hai giá trị đó thì React thấy deps "không đổi"
  // và bỏ qua effect. `openHoSoSeq` tăng ở MỌI lượt `navigate` nên luôn phân biệt được hai lượt.
  useEffect(() => {
    if (openHoSoId == null) return;
    setHoSoId(openHoSoId);
    setHoSoPv(openHoSoPv ?? null);
  }, [openHoSoId, openHoSoPv, openHoSoSeq]);

  // Mở tay từ bảng (bấm dòng) — không phải quét QR nên không có `pv` để so, phải xoá pv của lần mở
  // QR trước đó (nếu có) chứ không được giữ lại và so nhầm với lệnh mới.
  const moHoSoTay = useCallback((id: number) => {
    setHoSoId(id);
    setHoSoPv(null);
  }, []);

  const dongHoSo = useCallback(() => {
    const id = hoSoId;
    setHoSoId(null);
    setHoSoPv(null);
    // Trả tiêu điểm về ĐÚNG nút vừa bấm, không phải về đầu trang: người dùng bàn phím đang ở dòng
    // 30 thì đóng hồ sơ xong vẫn phải ở dòng 30. Dòng có thể đã biến mất (SSE đổi trạng thái lệnh
    // trong lúc xem) nên phải chịu được ca không tìm thấy.
    requestAnimationFrame(() => {
      const nut = document.querySelector<HTMLButtonElement>(`.hslsx__open[data-lsx="${id}"]`);
      if (nut) nut.focus();
      else khungRef.current?.focus();
    });
  }, [hoSoId]);

  // Chỉ gửi khoảng ngày khi PARSE RA ngày thật — ô trống và ô gõ sai đều không gửi, nhưng chỉ ô
  // gõ sai mới đeo viền cảnh báo.
  const tuGui = ngayHopLe(tuNgay) ? tuNgay : undefined;
  const denGui = ngayHopLe(denNgay) ? denNgay : undefined;
  const tuSai = tuNgay !== "" && tuGui === undefined;
  const denSai = denNgay !== "" && denGui === undefined;

  // --- dữ liệu ---------------------------------------------------------------
  const [rows, setRows] = useState<LenhSxItem[]>([]);
  const [total, setTotal] = useState(0);
  const [dem, setDem] = useState<Partial<Record<LsxTheoDoiTab, number>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [daTai, setDaTai] = useState(false); // đã có ÍT NHẤT một lượt tải xong
  const [loi, setLoi] = useState<{ text: string; cam: boolean } | null>(null);
  const [capNhatLuc, setCapNhatLuc] = useState<Date | null>(null);

  const [kpi, setKpi] = useState<LenhSxSummaryOut | null>(null);
  const [kpiLoi, setKpiLoi] = useState(false);
  const [dsMay, setDsMay] = useState<LenhSxMayLoc[] | null>(null);

  // Đổi BẤT KỲ bộ lọc nào (kể cả tab) ⇒ về trang 1. Đứng ở trang 7 rồi gõ tìm còn 3 kết quả là
  // bảng trống trơn và người dùng tưởng mất dữ liệu.
  useEffect(() => {
    setPage(1);
  }, [qTre, nhomCd, mayId, uuTien, tuGui, denGui, chiTre, tab]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.lenhSanXuat
      .danhSach(token, {
        tab,
        q: qTre.trim() || undefined,
        page,
        page_size: PAGE_SIZE,
        nhom_cong_doan: nhomCd || undefined,
        may_id: mayId ? Number(mayId) : undefined,
        uu_tien: uuTien ? (uuTien as "gap" | "binh_thuong") : undefined,
        // `true` khi bật, KHÔNG GỬI khi tắt — gửi `false` là hỏi "chỉ lệnh không trễ", một câu
        // không ai hỏi.
        tre: chiTre ? true : undefined,
        tu_ngay: tuGui,
        den_ngay: denGui,
      })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
        setDem(r.dem_theo_tab);
        setLoi(null);
        setDaTai(true);
        setCapNhatLuc(new Date());
        // Màn này không xoá dòng, nhưng `total` vẫn co lại khi người khác đổi trạng thái lệnh
        // (SSE) — đang đứng trang 6 mà tập tụt còn 4 trang thì bảng rỗng trơn.
        const ve = trangHopLe(page, r.total, PAGE_SIZE);
        if (ve !== null) setPage(ve);
      })
      .catch((e) => {
        const cam = e instanceof ApiError && e.isForbidden;
        setLoi({
          text: cam
            ? "Bạn không có quyền xem hồ sơ lệnh sản xuất."
            : e instanceof ApiError
              ? e.message
              : "Máy chủ không phản hồi.",
          cam,
        });
      })
      .finally(() => setLoading(false));
  }, [token, tab, qTre, page, nhomCd, mayId, uuTien, chiTre, tuGui, denGui]);
  useEffect(() => {
    load();
  }, [load]);

  // KPI đi request RIÊNG và KHÔNG nhận tham số lọc nào — nó luôn là toàn phạm vi của token. Hỏng
  // thì dải thẻ tự nói, KHÔNG chặn bảng (và ngược lại).
  const [kpiTick, setKpiTick] = useState(0);
  useEffect(() => {
    if (!token) return;
    let song = true;
    api.lenhSanXuat
      .summary(token)
      .then((r) => {
        if (!song) return;
        setKpi(r);
        setKpiLoi(false);
      })
      .catch(() => {
        if (!song) return;
        setKpi(null);
        setKpiLoi(true);
      });
    return () => {
      song = false;
    };
  }, [token, kpiTick]);

  // Nhịp SSE đã gộp 2 giây. Khai TRƯỚC hai effect dưới vì cả hai đều bám vào nó — bảng, KPI và ô
  // lọc Máy phải tươi theo CÙNG một nhịp.
  const tickTre = useTre(eventTick ?? 0, SSE_GOP_MS);

  // Nguồn ô lọc Máy — map cho cả phạm vi, lật trang không làm nó khác đi nên KHÔNG bám bộ lọc.
  // Nhưng PHẢI bám `tickTre`: các con số `(N)` trong option nằm ngay trên cái bảng tự tươi theo
  // SSE; để option đứng im là hai con số cạnh nhau nói hai chuyện mà người đọc không có cách nào
  // biết cái nào đúng.
  // Hỏng ⇒ `null` ⇒ ô lọc Máy ẨN HẲN, ba bộ lọc còn lại vẫn chạy. Bày một select rỗng (hoặc một
  // select bấm vào là 403) là đúng thứ dự án đã bỏ công gỡ ở màn danh mục.
  useEffect(() => {
    if (!token) return;
    let song = true;
    api.lenhSanXuat
      .boLoc(token)
      .then((r) => {
        if (song) setDsMay(r.may);
      })
      .catch(() => {
        if (song) setDsMay(null);
      });
    // Thiếu dòng này thì `song` không bao giờ hạ: rời màn giữa lúc request bay là setState trên
    // component đã tháo, và một phản hồi cũ về sau còn ghi đè được danh sách mới.
    return () => {
      song = false;
    };
  }, [token, tickTre]);

  // --- realtime: gộp sự kiện 2 giây rồi tải lại CẢ HAI, giữ nguyên trang/tab/lọc/vị trí cuộn ----
  // KHÔNG toast: bảng tra cứu không phải chỗ báo tin, và toast mỗi lần một tổ bấm Kết thúc là làm
  // phiền người đang đọc. Thay vào đó chân bảng hiện "Vừa cập nhật HH:MM".
  const tickDau = useRef(tickTre);
  useEffect(() => {
    if (tickTre === tickDau.current) return;
    tickDau.current = tickTre;
    load();
    setKpiTick((t) => t + 1);
  }, [tickTre, load]);

  // --- dẫn xuất --------------------------------------------------------------
  // Số cạnh tiêu đề = tổng theo BỘ LỌC (`dem_theo_tab.tat_ca`), KHÔNG theo tab. `total` của
  // response là tổng SAU cả tab và chỉ dùng cho Pager — hoán chỗ hai số này thì đứng ở tab "Chờ
  // nhập kho" mà tiêu đề tụt xuống 7, người ta tưởng cả hệ có 7 lệnh.
  const tongTheoLoc = dem?.tat_ca ?? null;
  const dangLoc =
    qTre.trim() !== "" ||
    nhomCd !== "" ||
    mayId !== "" ||
    uuTien !== "" ||
    tuNgay !== "" ||
    denNgay !== "" ||
    chiTre ||
    tab !== "tat_ca";
  const bangTrong = daTai && !loading && rows.length === 0;

  const xoaLoc = useCallback(() => {
    setQ("");
    setNhomCd("");
    setMayId("");
    setUuTien("");
    setTuNgay("");
    setDenNgay("");
    setChiTre(false);
    setTab("tat_ca");
    setPage(1);
  }, []);

  // --- dải tab: roving tabindex + kích hoạt THỦ CÔNG -------------------------
  // `←` `→` chỉ DỜI FOCUS, `Enter`/`Space` mới đổi tab (nút thường tự làm việc đó qua `onClick`).
  // Bắt buộc phải thủ công: mỗi lần đổi tab là một request, kích hoạt tự động khi lướt phím sẽ
  // bắn 6 request liên tiếp.
  const tabIdx = Math.max(0, TABS.findIndex((t) => t.key === tab));
  const [tabFocus, setTabFocus] = useState(tabIdx);
  useEffect(() => {
    setTabFocus(tabIdx);
  }, [tabIdx]);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  function phimTab(e: React.KeyboardEvent, i: number) {
    let toi = i;
    if (e.key === "ArrowRight") toi = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") toi = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") toi = 0;
    else if (e.key === "End") toi = TABS.length - 1;
    else return;
    e.preventDefault();
    setTabFocus(toi);
    tabRefs.current[toi]?.focus();
  }

  // --- gợi ý "vuốt ngang" ở màn hẹp -----------------------------------------
  // Chỉ hiện khi bảng THẬT SỰ rộng hơn khung (CSS ẩn nó ở ≥769px). Không ẩn cột nào ở màn hẹp:
  // ẩn cột là giấu mất dữ liệu người ta mở màn ra để tìm.
  const khungRef = useRef<HTMLDivElement | null>(null);
  const [tranNgang, setTranNgang] = useState(false);
  useEffect(() => {
    const el = khungRef.current;
    if (!el) return;
    const do_ = () => setTranNgang(el.scrollWidth > el.clientWidth + 1);
    do_();
    const ro = new ResizeObserver(do_);
    ro.observe(el);
    return () => ro.disconnect();
  }, [rows.length]);

  const kpiTre = kpi?.du_kien_tre ?? 0;
  const tyLeKcs = useMemo(() => {
    if (!kpi || kpi.ty_le_kcs_dat_hom_nay == null) return null;
    return kpi.ty_le_kcs_dat_hom_nay.toLocaleString("vi-VN", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
  }, [kpi]);

  const nhanTabDangChon = TABS[tabIdx]?.label ?? "Tất cả";

  return (
    <main className="hslsx">
      {/* ① HEADER — nói ngay đây là bàn TRA, và đường tạo/sửa nằm ở màn nào. */}
      <header className="hslsx__head">
        <div className="hslsx__headrow">
          <h1 className="hslsx__title">Hồ sơ lệnh sản xuất</h1>
          {tongTheoLoc !== null && <span className="hslsx__count">{num(tongTheoLoc)} lệnh</span>}
          <span className="hslsx__ro" title="Màn tra cứu — không có thao tác ghi nào">
            Chỉ xem
          </span>
          <div className="hslsx__spacer" />
        </div>
        <p className="hslsx__sub">
          Lệnh đã phát hành — theo dõi tới đâu. Tạo và sửa lệnh ở màn Kế hoạch sản xuất.
        </p>
      </header>

      {/* ② KPI — trả lời câu hỏi KHÔNG cần tìm gì cả: "hôm nay nhà máy thế nào". */}
      <section className="hslsx__kpis" aria-label="Số tổng hợp toàn phạm vi">
        <KpiThe
          nhan="Đang sản xuất"
          so={kpi?.dang_sx}
          dv="lệnh"
          dangTai={!kpi && !kpiLoi}
          loi={kpiLoi}
          chuThich="Lệnh chưa ra khỏi nhà máy. KHÔNG bằng số ở tab Đang SX — lệnh đang chạy mà dính cảnh báo nằm ở tab Cảnh báo, nhưng nó vẫn đang sản xuất."
        />
        <KpiThe
          nhan="Công đoạn xong hôm nay"
          so={kpi?.cong_doan_xong_hom_nay}
          dv="công đoạn"
          dangTai={!kpi && !kpiLoi}
          loi={kpiLoi}
          chuThich="Đếm theo công đoạn, không theo lệnh. Một ca in ghép phục vụ nhiều lệnh vẫn tính một."
        />
        <KpiThe
          nhan="Dự kiến trễ"
          so={kpi?.du_kien_tre}
          dv="lệnh"
          dangTai={!kpi && !kpiLoi}
          loi={kpiLoi}
          // Chỉ thẻ này được tô, và chỉ khi > 0: tô cả bốn thì màu hết mang tin.
          canhBao={!!kpi && kpiTre > 0}
          chuThich="Lệnh CHƯA XONG mà dự kiến vượt hạn SX nội bộ. Là tập con của thẻ Đang sản xuất. Bộ lọc «Chỉ lệnh trễ» rộng hơn thẻ này: nó đếm cả lệnh đã giao xong nhưng xong trễ."
        />
        <KpiThe
          nhan="KCS đạt hôm nay"
          // `null` ⇒ "—" + dòng phụ, KHÔNG đổ 0: "0 % đạt" là báo động sai, và nó sẽ nổ mỗi sáng
          // sớm trước lô KCS đầu tiên.
          chu={tyLeKcs === null ? "—" : `${tyLeKcs} %`}
          phu={kpi && kpi.ty_le_kcs_dat_hom_nay == null ? "Chưa kiểm lô nào hôm nay" : undefined}
          dangTai={!kpi && !kpiLoi}
          loi={kpiLoi}
          chuThich="Tính theo SỐ LƯỢNG (tổng đạt / tổng nhận), không phải trung bình cộng các lô."
        />
      </section>
      <p className="hslsx__kpinote">
        {kpiLoi ? (
          <>
            <span className="hslsx__kpinote--loi">Không tải được số tổng hợp.</span>{" "}
            <button type="button" className="hslsx__linkbtn" onClick={() => setKpiTick((t) => t + 1)}>
              Thử lại
            </button>
          </>
        ) : (
          // Bẫy đọc số phải xử ngay: `/summary` KHÔNG nhận tham số lọc nào, bảng thì đã lọc — hai
          // con số không bao giờ khớp, và đó là đúng. Thiếu câu này là mỗi tuần có một người đi hỏi.
          "Toàn phạm vi của bạn · không đổi theo bộ lọc"
        )}
      </p>

      {/* ③ LỌC — đặt TRÊN tab, không phải gu: số trên mỗi tab là facet của tập ĐÃ LỌC, nên dòng
          chảy phải đúng chiều nhân quả (thu hẹp tập → chia tập đã hẹp → đọc dòng). */}
      <section className="hslsx__filters">
        <div className="hslsx__search">
          <Icon name="search" size={15} />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={200}
            // Liệt kê ĐÚNG bốn thứ máy chủ thật sự tìm (`Lsx.ma`, `Lsx.ten`, `Order.order_no`,
            // `Customer.name`). Hứa nhiều hơn bốn thứ này là hứa suông.
            placeholder="Tìm mã lệnh, tên sản phẩm, số đơn, khách hàng"
            aria-label="Tìm mã lệnh, tên sản phẩm, số đơn, khách hàng"
          />
          {q !== "" && (
            <button type="button" className="hslsx__clearq" onClick={() => setQ("")} aria-label="Xóa ô tìm">
              <Icon name="x" size={14} />
            </button>
          )}
        </div>

        <label className="hslsx__field">
          <span className="hslsx__field-lb">Nhóm CĐ</span>
          <select value={nhomCd} onChange={(e) => setNhomCd(e.target.value)}>
            <option value="">Tất cả</option>
            {Object.entries(NHOM_CONG_DOAN).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>

        {/* Ô Máy chỉ mọc khi máy chủ trả được danh sách và danh sách có mục. Nguồn là
            `/api/lenh-san-xuat/bo-loc` — gác bằng chính `lenh_san_xuat:read` nên vai QC vào được
            (danh mục máy `/api/may-thiet-bi` đòi `dm_thiet_bi` hoặc `tinh_gia_thanh`, QC không có). */}
        {dsMay && dsMay.length > 0 && (
          <label className="hslsx__field">
            <span className="hslsx__field-lb">Máy</span>
            <select value={mayId} onChange={(e) => setMayId(e.target.value)}>
              <option value="">Tất cả</option>
              {dsMay.map((m) => (
                <option key={m.id} value={String(m.id)}>
                  {m.ten ?? m.ma ?? `#${m.id}`} ({m.so_lenh})
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="hslsx__field">
          <span className="hslsx__field-lb">Ưu tiên</span>
          <select value={uuTien} onChange={(e) => setUuTien(e.target.value)}>
            <option value="">Tất cả</option>
            <option value="gap">Gấp</option>
            <option value="binh_thuong">Bình thường</option>
          </select>
        </label>

        <div className="hslsx__daterange">
          <span className="hslsx__field-lb" id="hslsx-hansx">
            Hạn SX
          </span>
          <div className="hslsx__daterow">
            <input
              type="date"
              value={tuNgay}
              min="2000-01-01"
              max="2999-12-31"
              onChange={(e) => setTuNgay(e.target.value)}
              className={tuSai ? "is-sai" : undefined}
              aria-labelledby="hslsx-hansx"
              aria-label="Hạn SX từ ngày"
              aria-invalid={tuSai || undefined}
            />
            <span aria-hidden="true">→</span>
            <input
              type="date"
              value={denNgay}
              min="2000-01-01"
              max="2999-12-31"
              onChange={(e) => setDenNgay(e.target.value)}
              className={denSai ? "is-sai" : undefined}
              aria-labelledby="hslsx-hansx"
              aria-label="Hạn SX đến ngày"
              aria-invalid={denSai || undefined}
            />
          </div>
          {/* `NULL` không khớp phép so nào ⇒ đặt khoảng ngày là lệnh chưa khai hạn SX biến mất khỏi
              bảng. Không nói ra thì người dùng tưởng mất lệnh. */}
          <span className="hslsx__hint">Lệnh chưa khai hạn SX không nằm trong khoảng nào.</span>
        </div>

        <button
          type="button"
          className={`hslsx__toggle${chiTre ? " is-on" : ""}`}
          aria-pressed={chiTre}
          onClick={() => setChiTre((v) => !v)}
        >
          Chỉ lệnh trễ
        </button>

        {dangLoc && (
          <button type="button" className="hslsx__linkbtn" onClick={xoaLoc}>
            Xóa bộ lọc
          </button>
        )}
      </section>

      {/* ④ BẢY TAB — `tablist` thật: đúng MỘT tab được chọn và nó đổi nội dung của một panel. */}
      <div className="hslsx__tabs" role="tablist" aria-label="Lọc lệnh theo trạng thái">
        {TABS.map((t, i) => (
          <button
            key={t.key}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`hslsx-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls="hslsx-panel"
            tabIndex={i === tabFocus ? 0 : -1}
            className={`hslsx__tab${tab === t.key ? " is-active" : ""}`}
            onKeyDown={(e) => phimTab(e, i)}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {/* Số LẤY NGUYÊN từ `dem_theo_tab` của máy chủ. Đang tải ⇒ để TRỐNG chỗ số, không hiện
                `0` (số 0 lúc đang tải là một khẳng định sai về nhà máy). */}
            {dem ? <span className="hslsx__tabnum">{num(dem[t.key] ?? 0)}</span> : null}
          </button>
        ))}
      </div>

      <div id="hslsx-panel" role="tabpanel" aria-labelledby={`hslsx-tab-${tab}`} tabIndex={0}>
        {/* Lỗi khi bảng ĐANG CÓ dữ liệu ⇒ banner, giữ nguyên bảng cũ (đọc được còn hơn màn trắng).
            Lỗi khi bảng đang RỖNG ⇒ khối rỗng đổi mặt. CẤM cả hai cùng kêu kèm hai nút "Tải lại". */}
        {loi && !bangTrong && rows.length > 0 && (
          <BangLoi text="Không làm mới được danh sách." onRetry={load} />
        )}

        <div
          className="hslsx__tablewrap"
          ref={khungRef}
          tabIndex={0}
          role="group"
          aria-label="Bảng lệnh sản xuất — cuộn được bằng phím mũi tên"
        >
          <table className="hslsx__table">
            <caption className="sr-only">Danh sách lệnh sản xuất đã phát hành</caption>
            <thead>
              <tr>
                <th scope="col" className="hslsx__c1">
                  Mã
                </th>
                <th scope="col" className="hslsx__c2">
                  Sản phẩm / SL
                </th>
                <th scope="col" className="hslsx__c3">
                  Khách
                </th>
                <th scope="col" className="hslsx__c4">
                  Máy / người
                </th>
                <th scope="col" className="hslsx__c5">
                  Công đoạn + tiến độ
                </th>
                <th scope="col" className="hslsx__c6">
                  Hạn / Dự kiến
                </th>
                <th scope="col" className="hslsx__c7">
                  Trạng thái
                </th>
                {/* `<th>` rỗng làm trình đọc màn hình đọc "cột trống". */}
                <th scope="col" className="hslsx__c8">
                  <span className="sr-only">Mở hồ sơ</span>
                </th>
              </tr>
            </thead>
            {loading && rows.length === 0 ? (
              // Lần tải ĐẦU: skeleton giữ nguyên `thead` để bề ngang cột không nhảy khi dữ liệu về.
              // Lần tải LẠI (đổi tab/lọc/lật trang) mà bảng đang có dòng: giữ dòng cũ, chỉ làm mờ —
              // thay bảng bằng skeleton mỗi lần bấm tab là màn nhấp nháy liên tục.
              <Skeleton rows={8} cols={8} />
            ) : (
              <tbody className={loading ? "is-mo" : undefined}>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="hslsx__empty-td">
                      {loi ? (
                        <EmptyState
                          icon="alert"
                          title={
                            loi.cam ? loi.text : "Không tải được danh sách lệnh."
                          }
                          sub={loi.cam ? undefined : loi.text}
                          action={
                            // 403 thì KHÔNG có nút Tải lại: thử lại cũng thế.
                            loi.cam ? undefined : (
                              <Button variant="ghost" onClick={load}>
                                Tải lại
                              </Button>
                            )
                          }
                        />
                      ) : dangLoc && (dem?.tat_ca ?? 0) > 0 && (dem?.[tab] ?? 0) === 0 && tab !== "tat_ca" ? (
                        // (c) rỗng CHỈ vì tab — bộ lọc vẫn ra dòng, chỉ tab này không có.
                        <EmptyState
                          icon="clipboard"
                          title={`Tab «${nhanTabDangChon}» hiện không có lệnh nào.`}
                          action={
                            <Button variant="ghost" onClick={() => setTab("tat_ca")}>
                              Về tab Tất cả
                            </Button>
                          }
                        />
                      ) : dangLoc ? (
                        // (b) bộ lọc không ra
                        <EmptyState
                          icon="search"
                          title="Không có lệnh nào khớp bộ lọc."
                          sub="Thử bỏ bớt điều kiện, hoặc mở rộng khoảng hạn SX."
                          action={
                            <Button variant="ghost" onClick={xoaLoc}>
                              Xóa bộ lọc
                            </Button>
                          }
                        />
                      ) : (
                        // (a) chưa có gì — KHÔNG nút: màn chỉ đọc, không mời tạo lệnh.
                        <EmptyState
                          icon="clipboard"
                          title="Chưa có lệnh sản xuất nào đã phát hành trong phạm vi của bạn."
                          sub="Lệnh còn đang lập vẫn nằm ở màn Kế hoạch sản xuất."
                        />
                      )}
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => <Dong key={r.id} r={r} onMoHoSo={moHoSoTay} />)
                )}
              </tbody>
            )}
          </table>
        </div>

        {tranNgang && <p className="hslsx__vuot">Vuốt ngang để xem thêm cột →</p>}

        {/* Bảng rỗng ⇒ ẩn Pager: khối rỗng đã nói giúp rồi. */}
        {total > 0 && (
          <div className="hslsx__foot" aria-live="polite">
            <Pager
              total={total}
              page={page}
              size={PAGE_SIZE}
              onPage={setPage}
              loading={loading}
              unit="lệnh"
            />
            {capNhatLuc && <span className="hslsx__moi">Vừa cập nhật {gioPhut(capNhatLuc)}</span>}
          </div>
        )}
      </div>

      {/* ⑥ HỒ SƠ — nằm TRONG `<main className="hslsx">` để mọi rule nền của scope (`.sr-only`,
          vòng tiêu điểm, `.hslsx-pill--*`, `.hslsx__bar`) áp được vào lớp phủ mà không phải chép
          lại lần hai. Bản thân nó `position: fixed` nên vẫn phủ trọn màn hình. */}
      {hoSoId !== null && (
        <LenhSxHoSoView
          lsxId={hoSoId}
          pv={hoSoPv}
          onClose={dongHoSo}
          eventTick={eventTick}
          onMoDon={
            // `openOrderId` là đường ĐÃ CHẠY của màn Báo giá: AppShell mở màn Đơn hàng bán rồi
            // bung drawer đúng đơn, ở đó có sẵn nút "Tạo yêu cầu giao hàng". Hồ sơ không cần
            // (và không được) biết gì thêm về form giao hàng.
            navigate ? (orderId) => navigate("don-hang-ban", { openOrderId: orderId }) : undefined
          }
        />
      )}
    </main>
  );
}

/** MỘT thẻ KPI. Đang tải ⇒ shimmer, KHÔNG hiện `0`: số 0 lúc đang tải là một khẳng định sai về
 *  nhà máy. Thẻ KHÔNG bấm được — thẻ "Dự kiến trễ" đếm lệnh CHƯA XONG mà trễ, còn bộ lọc
 *  «Chỉ lệnh trễ» đếm cả lệnh đã giao xong nhưng xong trễ; bấm một cái ra số lớn hơn cái vừa đọc
 *  là kiểu lệch làm mất lòng tin vào cả màn. */
function KpiThe({
  nhan,
  so,
  chu,
  dv,
  phu,
  dangTai,
  loi,
  canhBao,
  chuThich,
}: {
  nhan: string;
  so?: number;
  chu?: string;
  dv?: string;
  phu?: string;
  dangTai?: boolean;
  loi?: boolean;
  canhBao?: boolean;
  chuThich: string;
}) {
  return (
    <div className={`hslsx-kpi${canhBao ? " hslsx-kpi--canhbao" : ""}`} title={chuThich}>
      <span className="hslsx-kpi__lb">{nhan}</span>
      {dangTai ? (
        <span className="hslsx-kpi__shim" aria-hidden="true" />
      ) : (
        <span className="hslsx-kpi__val">
          {loi ? "—" : (chu ?? (so == null ? "—" : num(so)))}
          {!loi && dv && so != null ? <small>{dv}</small> : null}
        </span>
      )}
      {phu && !loi && <span className="hslsx-kpi__phu">{phu}</span>}
      <span className="sr-only">{chuThich}</span>
    </div>
  );
}

/** MỘT hàng bảng. Cả hàng bấm được bằng CHUỘT, nhưng KHÔNG gán `role="button"` lên `<tr>`: gán vai
 *  nút cho hàng là xoá luôn vai `row` của nó, trình đọc màn hình mất cấu trúc bảng (không còn đọc
 *  được "cột Trạng thái: …"). Đường bàn phím đi qua nút mũi tên ở cột 8. */
function Dong({ r, onMoHoSo }: { r: LenhSxItem; onMoHoSo: (id: number) => void }) {
  const pill = PILL[r.trang_thai] ?? PILL.dang_sx;
  const pct = Math.max(0, Math.min(100, Math.round(r.tien_do_pct)));
  const uoc = r.tien_do_uoc_tinh;
  const nguoiDau = r.nguoi.slice(0, 2);
  const nguoiThua = r.nguoi.length - nguoiDau.length;
  const cbHien = r.canh_bao.slice(0, 2);
  const cbThua = r.canh_bao.length - cbHien.length;
  const nhomLb = r.nhom_cong_doan ? (NHOM_CONG_DOAN[r.nhom_cong_doan] ?? r.nhom_cong_doan) : null;

  return (
    // `is-mo-duoc` mang `cursor: pointer` + đổi nền khi rê. Hồ sơ đã nối nên MỌI dòng đều bấm
    // được — nhánh "chưa nối ⇒ hàng câm" đã bỏ cùng lúc prop thành bắt buộc.
    <tr className="hslsx__row is-mo-duoc" onClick={() => onMoHoSo(r.id)}>
      {/* Cột 1 — Mã là ĐỊNH DANH: không bao giờ cắt, không ellipsis. Cắt mã là hỏng cả dòng. */}
      <td className="hslsx__c1">
        <span className="hslsx__ma">{r.ma}</span>
        {r.is_rush && <ChipGap />}
      </td>

      <td className="hslsx__c2">
        <span className="hslsx__ten" title={r.ten ?? undefined}>
          {r.ten ?? "—"}
        </span>
        <span className="hslsx__nho">
          {num(r.so_luong_dat)} {r.don_vi_tinh ?? ""}
          {r.da_giao > 0 ? ` · đã giao ${num(r.da_giao)}` : ""}
        </span>
      </td>

      <td className="hslsx__c3">
        <span className="hslsx__ten" title={r.khach_hang ?? undefined}>
          {r.khach_hang ?? "—"}
        </span>
        {r.sale && <span className="hslsx__nho">{r.sale}</span>}
      </td>

      <td className="hslsx__c4">
        <span className="hslsx__ten">{r.may ?? "—"}</span>
        {r.nguoi.length > 0 && (
          // Cắt từ CUỐI: thứ tự mảng là thứ tự giao. `title` giữ đủ tên, và `aria-label` bù cho
          // người đi bàn phím / cảm ứng (title không tới được họ).
          <span className="hslsx__nho" title={r.nguoi.join(", ")} aria-label={`Người: ${r.nguoi.join(", ")}`}>
            {nguoiDau.join(", ")}
            {nguoiThua > 0 ? ` +${nguoiThua}` : ""}
          </span>
        )}
      </td>

      {/* Cột 5 — `gio_may` vào `title`, KHÔNG có cột riêng. ⚠️ ĐỪNG CỘNG `gio_may` qua nhiều lệnh:
          một lượt in ghép 3 lệnh được đếm đủ cho cả 3, cộng lại vượt giờ máy thật của xưởng. */}
      <td className="hslsx__c5" title={`Đã chạy ${num(Math.round(r.gio_may * 10) / 10)} giờ máy`}>
        <span className="hslsx__buoc">
          <span className="hslsx__ten" title={r.buoc_hien_tai ?? undefined}>
            {r.buoc_hien_tai ?? "—"}
          </span>
          {nhomLb && <span className="hslsx__chipnhom">{nhomLb}</span>}
        </span>
        <span className="hslsx__tiendo">
          <span
            className="hslsx__bar"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuetext={uoc ? `khoảng ${pct} phần trăm, ước tính` : `${pct} phần trăm`}
            // Cờ ước tính phải ra tới mặt màn: 40% "đo được" và 40% "ước tính" là hai mức tin cậy
            // khác hẳn nhau, gộp làm một là mời điều độ quyết trên con số họ tưởng chắc hơn thực tế.
            title={uoc ? "Ước tính theo thời lượng kế hoạch — bước chưa khai sản lượng" : undefined}
          >
            <span className={`hslsx__barfill${uoc ? " is-uoc" : ""}`} style={{ width: `${pct}%` }} />
          </span>
          <span className="hslsx__pct">
            {uoc ? "~" : ""}
            {pct}%
          </span>
        </span>
      </td>

      {/* Cột 6 — hai mốc, đừng lẫn: trên là hạn SX NỘI BỘ (cùng cột mà `tre_han` và bộ lọc ngày
          lấy làm mốc), dưới là dự kiến xong. `han_giao_khach` chỉ nằm trong `title`: cột đã chật,
          và trễ SX ≠ trễ giao — bày cạnh nhau là mời so nhầm. */}
      <td
        className="hslsx__c6"
        title={r.han_giao_khach ? `Hạn giao khách: ${ngay(r.han_giao_khach)}` : undefined}
      >
        {/* `han_hoan_thanh_sx` là DATE ⇒ `ngay()`, không `ngayGio()`. */}
        <span className={`hslsx__han ${classHan(r.han_hoan_thanh_sx)}`}>
          {ngay(r.han_hoan_thanh_sx)}
        </span>
        {/* `du_kien_xong` là DATETIME ⇒ `ngayGio()`. `null` ⇒ "Chưa đủ dữ liệu", KHÔNG "—": máy chủ
            cố ý im khi có bước thiếu thời lượng, thà im còn hơn bịa một mốc đem đi hứa với khách. */}
        <span className="hslsx__nho">
          {r.du_kien_xong ? ngayGio(r.du_kien_xong) : "Chưa đủ dữ liệu"}
        </span>
      </td>

      <td className="hslsx__c7">
        <span className={`hslsx-pill ${pill.cls}`}>{pill.label}</span>
        {cbHien.length > 0 && (
          <span className="hslsx__cbs">
            {cbHien.map((c) => {
              const meta = CANH_BAO[c];
              return (
                <span key={c} className={`hslsx-badge ${meta?.cls ?? ""}`}>
                  {meta?.label ?? c}
                </span>
              );
            })}
            {cbThua > 0 && (
              <span
                className="hslsx-badge hslsx-badge--them"
                title={r.canh_bao.map((c) => CANH_BAO[c]?.label ?? c).join(", ")}
              >
                +{cbThua}
              </span>
            )}
          </span>
        )}
      </td>

      {/* Cột 8 — đường BÀN PHÍM vào hồ sơ (cả hàng bấm được nhưng `<tr>` không nhận tiêu điểm).
          Mũi tên luôn `opacity: 1` (cảm ứng không có trạng thái rê). */}
      <td className="hslsx__c8" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="hslsx__open"
          /* Mốc để đóng hồ sơ xong trả tiêu điểm về ĐÚNG dòng vừa mở (xem `dongHoSo`). */
          data-lsx={r.id}
          aria-label={`Mở hồ sơ lệnh ${r.ma} — ${r.ten ?? "chưa đặt tên"}`}
          onClick={(e) => {
            e.stopPropagation();
            onMoHoSo(r.id);
          }}
        >
          <Icon name="chevron" size={16} />
        </button>
      </td>
    </tr>
  );
}
