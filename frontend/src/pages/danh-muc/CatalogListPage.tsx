// Trang danh mục GENERIC — list + drawer form theo SECTION + search + filter tab.
// 1 component cho 10 danh mục qua `config` (danh sách ở `REBUILD_CONFIGS`). On-brand với
// design system app (tokens rust/ink/paper).
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../../auth/useAuth";
import { useCan } from "../../auth/permissions";
import { Button } from "../../components/Button";
import { Pager, trangHopLe } from "../../components/Pager";
import { useTre } from "../../lib/useTre";
import { ApiError } from "../../api/client";
import { crud, type Row } from "../../api/rebuildCatalog";
import { useNapTenDonVi } from "../tenDonVi";
import { CatalogDrawer } from "./CatalogDrawer";
import { ImportExcelDialog } from "../../components/ImportExcelDialog";
import { OTim } from "./OTim";
import { LocNangCao, type GiaTriLoc } from "./LocNangCao";
import { XoaDanhMucDialog } from "./XoaDanhMucDialog";
import { CircleXIcon, CopyIcon, DownloadIcon, FilterIcon, PlusIcon, TrashIcon, UndoIcon, UploadIcon } from "./icons";
import type { CatalogConfig } from "./types";
import { DieuHuongDanhMuc } from "./dieuHuong";
import type { NavigateFn } from "../../components/AppShell";
import "../rebuild-catalog.css";

/** Số dòng mỗi trang của MỌI màn danh mục. Trang cắt Ở MÁY CHỦ (`page`+`size`): mỗi lần mở màn
 *  chỉ kéo về 20 dòng, không phải cả danh mục. Tìm kiếm và tab lọc vì thế cũng phải chạy ở máy
 *  chủ — lọc trong JS trên 20 dòng đang xem sẽ biến ô tìm thành "tìm trong trang này".
 *
 *  ⚠️ KHÔNG export: đây là con số của MÀN NÀY. Chỗ khác cần "20" thì tự khai — chia sẻ hằng này
 *  ra ngoài là sớm muộn có người đổi nó cho màn của họ rồi kéo cả 10 màn danh mục đi theo. */
const PAGE_SIZE = 20;

/** Bề rộng (px) cột Hành động = đúng cụm nút có thể hiện. Trước 18/09/2026 cột đóng cứng 8%: ở
 *  bảng rộng 1150px chỉ được 92px, mà "Nhân bản" + "Xóa" cần 160px ⇒ "Xóa" tràn ra ngoài bảng,
 *  khung sinh thanh cuộn ngang, mở màn lên không thấy nút Xóa đâu (5 màn có Nhân bản đều dính).
 *  Số đo từ `.rc__link-btn` (viền 2 + đệm 16 + icon 13 + khe 4 + chữ 600 12.5px Be Vietnam Pro,
 *  font đóng gói sẵn nên máy nào cũng rộng như nhau) cộng dư 1-2px. Đổi chữ/icon/đệm nút là đo lại. */
const NUT_RONG = { nhanBan: 96, xoa: 62, batLai: 78 } as const;
/** Khe giữa hai nút (`.rc__acts` gap) + đệm trái 8 / phải 12 của ô. */
const NUT_KHE = 4;
const COT_NUT_DEM = 20;

export function CatalogListPage({ config, onMutate, navigate }: {
  config: CatalogConfig; onMutate?: () => void;
  /** Cho ô bấm-để-mở-màn-khác (vd mã đơn ở Thành phẩm) — xem `dieuHuong.ts`. */
  navigate?: NavigateFn;
}) {
  const { token } = useAuth();
  const can = useCan();
  // Nạp bảng nhãn ĐƠN VỊ + CHẶNG dòng giấy cho cả trang lẫn drawer con: cột "Đơn vị" của màn Công
  // đoạn và ô chọn Đơn vị đầu vào/ra đọc `/api/don-vi/tram` (xem `tenDonVi.ts`). Gọi ở ĐÂY chứ
  // không ở từng config vì config là dữ liệu, không phải component — và một lần gọi ở gốc thì
  // drawer vẽ lại theo. Bảng nạp một lần cho cả phiên nên các màn khác không tốn thêm chuyến nào.
  useNapTenDonVi();
  // Gác nút GHI theo quyền module. Trước 15/08/2026 màn này không hỏi quyền một câu nào: vai
  // chỉ-đọc vẫn thấy đủ Thêm / Xóa / Bật lại, bấm xong mới ăn 403 — nút bày ra để rồi từ chối.
  // `moduleQuyen` bỏ trống (vd màn dùng trong test) = không gác, hành vi cũ y nguyên.
  const mQuyen = config.moduleQuyen;
  // `khongTaoTay` / `khongXoa` là luật CỦA MÀN, đứng TRƯỚC quyền: có quyền tạo vẫn không tạo
  // tay được, vì dòng ở đó do hệ sinh (xem `types.ts`).
  const duocTao = !config.khongTaoTay && (!mQuyen || can(mQuyen, "create"));
  const duocXoa = !config.khongXoa && (!mQuyen || can(mQuyen, "delete"));
  const duocBatLai = !mQuyen || can(mQuyen, "update");
  // `enableClone` là luật CỦA MÀN (chỉ 5 danh mục khai tay có route `/clone`); quyền `clone` TÁCH
  // khỏi `create` — vai được tạo mới (gõ tay) chưa chắc nên nhân bản hàng cũ (nhân đôi giá/công
  // thức đang chạy mà không soát lại từng ô).
  const duocClone = Boolean(config.enableClone) && (!mQuyen || can(mQuyen, "clone"));
  // Excel — HAI nút, HAI mức quyền khác nhau, đừng gộp làm một:
  //   · "Xuất Excel" chỉ cần quyền ĐỌC (đang đứng ở màn là đã đủ) — backend cũng gác `/mau-excel`
  //     bằng đúng dependency đọc của màn. Gộp chung với nhập là giấu mất đường lấy file khỏi
  //     người chỉ có quyền xem, trong khi họ chẳng ghi được gì.
  //   · "Nhập Excel" đòi CẢ `create` LẪN `update`: một dòng có thể là tạo mới hay cập nhật, mà
  //     lúc gác thì chưa ai biết — biết được thì đã đọc xong file rồi. Thiếu một trong hai mà vẫn
  //     hiện nút là mời bấm để ăn 403 giữa luồng.
  //   · Màn `khongTaoTay` (Thành phẩm) thì quyền `create` không còn nghĩa gì — máy chủ chặn mọi dòng
  //     mã mới, file chỉ còn SỬA được dòng đã có ⇒ đủ quyền `update` là được nhập.
  const duocXuatExcel = Boolean(config.enableImport);
  const duocImport = duocXuatExcel && duocBatLai && (Boolean(config.khongTaoTay) || duocTao);
  const [showImport, setShowImport] = useState(false);
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Row | "new" | null>(null);
  const [deleting, setDeleting] = useState<Row | null>(null);      // renderDeleteDialog: dialog xóa riêng
  const [q, setQ] = useState("");
  const qTre = useTre(q);              // gõ xong 300ms mới hỏi máy chủ
  const [facet, setFacet] = useState("all");
  // Lọc nâng cao (`config.locNangCao`): `{param: giá trị}`, khoá vắng = không lọc tiêu chí đó.
  // Bảng mở/gập tách khỏi giá trị: gập lại thì bộ lọc VẪN áp, chỉ thu về hàng nhãn.
  const [locNC, setLocNC] = useState<GiaTriLoc>({});
  const [moLocNC, setMoLocNC] = useState(false);
  const soLocNC = Object.keys(locNC).length;
  // Xem các mục ĐÃ NGỪNG DÙNG. Trước 14/08/2026 hộp thoại xoá hứa "có thể khôi phục lại khi cần"
  // mà màn lọc cứng `active:true` và không có nút nào bật lại — ẩn xong là mất tăm, lời hứa suông.
  const [xemDaNgung, setXemDaNgung] = useState(false);
  const [soDaNgung, setSoDaNgung] = useState(0);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);                                  // tổng SAU bộ lọc
  const [facets, setFacets] = useState<Record<string, number>>({});       // số cho từng tab lọc
  const [tongServer, setTongServer] = useState<number | null>(null);      // `tong_theo_tim` nếu có
  // Đổi bộ lọc thì về trang đầu — đứng ở trang 7 rồi gõ tìm còn 3 kết quả là bảng trống trơn.
  useEffect(() => { setPage(1); }, [qTre, facet, xemDaNgung, locNC]);

  // Dữ liệu phụ theo dòng (vd trạng thái máy). Nạp SONG SONG, không nối tiếp: cột phụ chậm không
  // được phép giữ cả bảng ở trạng thái skeleton.
  // `null` = CHƯA BIẾT (đang nạp, hoặc nạp hỏng) — khác hẳn "đã nạp xong, dòng này không có gì".
  // Gộp hai cái làm một là trong lúc chờ API, máy đang hỏng hiện "Rảnh" — sai đúng thứ người ta
  // mở bảng ra để tìm.
  const [extra, setExtra] = useState<Record<string, unknown> | null>(null);

  const facetKey = config.facet?.key;

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    // MỘT request cho MỘT trang: lọc + đếm + cắt trang đều nằm ở máy chủ. Trước 14/08/2026 màn
    // kéo cả danh mục về rồi lọc trong JS — danh mục lớn là vừa nặng đường truyền vừa cụt dữ
    // liệu (trần `size` của backend là 200).
    api.list(token, {
      page,
      size: PAGE_SIZE,
      // Xoá mềm: mặc định chỉ hiện dòng còn dùng; bật công tắc thì xem ĐÚNG các dòng đã ngừng.
      ...(config.softDelete ? { active: !xemDaNgung } : {}),
      ...(qTre.trim() ? { q: qTre.trim() } : {}),
      ...(facetKey && facet !== "all" ? { [facetKey]: facet } : {}),
      ...locNC,
    })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
        if (r.facets) setFacets(r.facets);
        setTongServer(typeof r.tong_theo_tim === "number" ? r.tong_theo_tim : null);
        // Xoá nốt dòng cuối của trang cuối ⇒ `total` co lại mà `page` đứng yên ⇒ bảng rỗng trơn,
        // người dùng tưởng mất sạch dữ liệu. Lùi về trang cuối còn thật.
        const ve = trangHopLe(page, r.total, PAGE_SIZE);
        if (ve !== null) setPage(ve);
      })
      // Giữ LÝ DO thôi, không gói sẵn câu "Không tải được danh sách" vào đây: khối rỗng của bảng
      // đã nói câu đó rồi, nhét cả hai vào một chỗ là đọc ra hai lần cùng một ý.
      .catch((e) => setError(e instanceof ApiError ? e.message : "Máy chủ không phản hồi."))
      .finally(() => setLoading(false));
  }, [token, api, config.softDelete, xemDaNgung, page, qTre, facet, facetKey, locNC]);
  useEffect(() => { load(); }, [load]);

  // Dữ liệu phụ nạp RIÊNG, không đi kèm mỗi lần lật trang: nó là map cho CẢ danh mục (vd trạng
  // thái mọi máy), lật trang không làm nó khác đi. Chỉ nạp lại sau khi có người ghi (`tick`).
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!token || !config.loadExtra) return;
    // Hỏng thì để nguyên `null` — cột phụ sẽ nói "chưa biết" chứ không bịa ra trạng thái đẹp.
    config.loadExtra(token).then(setExtra).catch(() => setExtra(null));
  }, [token, config.loadExtra, tick]);

  // Đếm số mục ĐÃ NGỪNG — một request rẻ (`size:1`, chỉ lấy `total`). Không có mục nào bị ngừng
  // thì công tắc không mọc ra: đừng bày một cái nút mở ra danh sách rỗng.
  useEffect(() => {
    if (!token || !config.softDelete) { setSoDaNgung(0); return; }
    api.list(token, { page: 1, size: 1, active: false })
      .then((r) => {
        setSoDaNgung(r.total);
        // Bật lại cái cuối cùng ⇒ công tắc biến mất, mà màn vẫn đứng ở chế độ "đã ngừng" nhìn
        // vào bảng rỗng. Tự quay về danh sách chính.
        if (r.total === 0) setXemDaNgung(false);
      })
      .catch(() => setSoDaNgung(0));   // hỏng thì coi như không có — không chặn màn chính
  }, [token, api, config.softDelete, tick]);

  /** Sau khi TẠO / SỬA / XÓA: tải lại cả bảng lẫn dữ liệu phụ. */
  const lamMoi = useCallback(() => { load(); setTick((t) => t + 1); }, [load]);

  // Danh mục THẬT làm nền cho hàng tab (`facet.source`, vd Nhóm máy). Nạp riêng và nạp lại sau
  // mỗi lần ghi (`tick`): khai thêm một nhóm trong drawer là hàng tab phải có ngay chỗ của nó.
  // Trước 22/08/2026 tab chỉ mọc từ SỐ ĐẾM của máy chủ (`GROUP BY` trên chính bảng đang xem), nên
  // nhóm vừa tạo — chưa dòng nào thuộc về — im lặng như thể không lưu được.
  const facetSource = config.facet?.source;
  const [facetDm, setFacetDm] = useState<{ value: string; label: string }[] | null>(null);
  useEffect(() => {
    if (!token || !facetSource) { setFacetDm(null); return; }
    let alive = true;
    crud(facetSource).list(token, { page: 1, size: 200 })
      .then((r) => {
        if (!alive) return;
        setFacetDm(r.items
          .map((it) => String(it.ten ?? "").trim())
          .filter(Boolean)
          .map((v) => ({ value: v, label: v })));
      })
      // Hỏng thì để `null`: hàng tab lùi về đúng những giá trị máy chủ đang đếm được, KHÔNG bịa
      // ra một danh sách tên nằm sẵn trong code (danh mục là động, tên trong code sớm muộn lệch).
      .catch(() => { if (alive) setFacetDm(null); });
    return () => { alive = false; };
  }, [token, facetSource, tick]);

  // Tab lọc: nền là danh mục thật (`source`) — hoặc danh sách khai cứng (`values`) với màn không
  // có danh mục — rồi nối thêm giá trị TỰ DO đã có trong dữ liệu mà nền chưa liệt kê
  // (`facet.dynamic`), đọc từ `facets` của máy chủ vì màn chỉ cầm 20 dòng.
  const facetValues = useMemo(() => {
    const f = config.facet;
    if (!f) return [];
    const nen = facetDm ?? f.values ?? [];
    if (!f.dynamic) return nen;
    const known = new Set(nen.map((v) => v.value));
    const them = Object.keys(facets)
      .filter((v) => v && !known.has(v))
      .sort((a, b) => a.localeCompare(b, "vi"));
    return [...nen, ...them.map((v) => ({ value: v, label: v }))];
  }, [config.facet, facets, facetDm]);

  // Số cạnh tiêu đề và số trên tab "Tất cả": tổng theo Ô TÌM, KHÔNG theo tab đang chọn — đứng ở
  // tab "Bế" mà tiêu đề tụt xuống còn 3 thì người ta tưởng danh mục có 3 dòng.
  // `total` là tổng SAU cả tab, nên màn có tab thì cộng từ `facets`. Khoá rỗng trong `facets` là
  // dòng chưa khai giá trị đó — vẫn phải cộng, bỏ đi là "Tất cả" hụt số.
  // Màn mà một dòng nằm ở NHIỀU tab (Công việc khoán nhiều tổ) thì cộng là đếm trùng — server trả
  // sẵn `tong_theo_tim`, có thì đọc nó.
  const tongTheoTim = useMemo(() => {
    if (tongServer != null) return tongServer;
    const ds = Object.values(facets);
    return config.facet && ds.length ? ds.reduce((a, b) => a + b, 0) : total;
  }, [config.facet, facets, total, tongServer]);
  // `xemDaNgung` cũng là một bộ lọc: bảng rỗng lúc đó KHÔNG có nghĩa "chưa có gì trong hệ thống".
  const dangLoc = qTre.trim() !== "" || facet !== "all" || xemDaNgung || soLocNC > 0;
  const bangTrong = !loading && rows.length === 0;
  // Cột Hành động rộng theo cụm nút DÀI NHẤT có thể nằm trên một dòng: dòng còn dùng mang Nhân bản
  // + Xóa, dòng đã ngừng chỉ mang Bật lại. Sàn 96px để tiêu đề "Hành động" đứng một dòng. Không
  // dòng nào có nút (vd Thành phẩm: không xoá, không nhân bản) thì KHÔNG mọc cột — trước đây vẫn
  // chừa 8% trống trơn dưới tiêu đề "Hành động".
  const rongNutSong = (duocClone ? NUT_RONG.nhanBan : 0) + (duocXoa ? NUT_RONG.xoa : 0)
    + (duocClone && duocXoa ? NUT_KHE : 0);
  const rongNutNgung = duocBatLai && (xemDaNgung || rows.some((r) => r.active === false)) ? NUT_RONG.batLai : 0;
  const rongNut = Math.max(rongNutSong, rongNutNgung);
  const coCotNut = rongNut > 0;
  const rongCotNut = Math.max(96, rongNut + COT_NUT_DEM);

  // Bề rộng cột nội dung. ⚠️ `table-layout: fixed` + `width: 100%`: cột KHÔNG khai bề rộng ăn TRỌN
  // phần còn lại. Màn Thành phẩm từng chỉ có đúng một cột như vậy (ĐVT) nên nó chiếm 46% màn hình
  // cho một chữ "hộp", còn Tên bị ép xuống 3 dòng (chủ báo 22/08/2026). ĐVT ở cả ba danh mục
  // (Giấy · Vật tư khác · Thành phẩm) đều là một chip ngắn.
  // Màn đã tự khai `width` thì bảng mặc định theo key đứng ngoài: cột nó cố ý để trống là cột ĂN
  // PHẦN CÒN LẠI (vd Ghi chú của Công đoạn), chen 22% vào là tổng vượt 100% và cả bảng tràn ngang.
  const khaiRongRieng = config.columns.some((c) => c.width);
  const widthMa = config.widthMa ?? "14%";
  const widthTen = config.widthTen ?? "24%";
  const rongCot: (string | undefined)[] = config.columns.map((c) => c.width ?? (khaiRongRieng ? undefined
    : c.key === "quy_doi_text" ? "34%"
    : c.key === "ghi_chu" ? "22%"
    : c.key === "don_vi_gia" ? "9%"
    : undefined));
  // Cột nào cũng có % mà cộng chưa tới 100% (Vật tư khác: 14+24+9+22) ⇒ trình duyệt dồn TOÀN BỘ
  // phần dư vào cột px duy nhất là cột Hành động: đo được 357px trống trơn bên trái hai nút, trong
  // khi Ghi chú bị cắt "…". Nhả bề rộng cột nội dung CUỐI để nó ăn phần dư thay. Tổng ≥ 100% thì
  // trình duyệt tự co đều, không có phần dư, để nguyên.
  const tongPhanTram = [widthMa, widthTen, ...rongCot]
    .reduce((s, w) => s + (w?.endsWith("%") ? parseFloat(w) : NaN), 0);
  if (rongCot.length > 0 && tongPhanTram < 100) rongCot[rongCot.length - 1] = undefined;

  const [confirmDeleteRow, setConfirmDeleteRow] = useState<Row | null>(null);

  function remove(r: Row) {
    if (!token) return;
    if (config.renderDeleteDialog) { setDeleting(r); return; }   // luồng xóa riêng (vd Kho)
    setConfirmDeleteRow(r);
  }

  /** Bật lại một mục đã ngừng — route riêng `PATCH /{id}/active`, xem `crud.datActive`. */
  async function batLai(r: Row) {
    if (!token) return;
    try {
      await api.datActive(token, r.id, true);
      lamMoi();
      onMutate?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không bật lại được.");
    }
  }

  /** Nhân bản — server copy toàn bộ cột, tự đặt mã/tên "(bản sao)" không trùng. Mở luôn dòng mới
   *  trong drawer để đổi tên/giá ngay, không bắt tìm lại nó giữa cả bảng. */
  async function clone(r: Row) {
    if (!token) return;
    try {
      const moi = await api.clone(token, r.id);
      lamMoi();
      onMutate?.();
      setEditing(moi);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không nhân bản được.");
    }
  }

  /** Xuất Excel — CHỈ dòng đang dùng, nhưng ĐỦ ô cấu hình hiện hành: mọi công thức, bậc tính và bảng
   *  con đi ra sheet riêng đọc được. Danh mục rỗng thì chỉ còn dòng tiêu đề, tự đóng vai file mẫu —
   *  nên không còn nút "Tải mẫu" riêng. */
  async function xuatExcel() {
    if (!token) return;
    try {
      const url = await api.templateBlobUrl(token);
      const a = document.createElement("a");
      a.href = url;
      a.download = `xuat-${config.prefix.split("/").pop()}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xuất được file.");
    }
  }

  const facetCount = (v: string) => facets[v] ?? 0;

  return (
    // `rc--dm`: scope RIÊNG của màn danh mục. Không dùng `.rc` sẵn có làm mốc vì `KhoPage` và
    // `KhoHangView` cũng là `<main className="rc">` — đè theo `.rc` là rò ngược sang Kho.
    // Xem khối "GIÀNH LẠI …" ở cuối `rebuild-catalog.css`.
    // Provider để ngoài cùng, không thụt lề cả khối cho gọn diff — xem `dieuHuong.ts`.
    <DieuHuongDanhMuc.Provider value={navigate}>
    <main className="rc rc--dm">
      {/* HEADER — MỘT dạng cho cả 13 màn, hai hàng cố định trên một kẻ ngang:
            1. tiêu đề · pill đếm ····· [+ Thêm …]
            2. [ô tìm] [Lọc nâng cao] ····· dải chip lọc │ công tắc "Hiện mục đã ngừng"
            (3.) bảng Lọc nâng cao khi mở, hoặc hàng nhãn bộ lọc đang áp khi gập — chỉ màn có
                 `config.locNangCao`. */}
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">{config.heading ?? config.title}</h1>
          <span className="rc__count">{tongTheoTim} mục</span>
          <div className="rc__spacer" />
          {duocXuatExcel && (
            <Button variant="ghost" onClick={xuatExcel} title="Xuất toàn bộ cấu hình đang dùng ra Excel — sửa rồi nhập lại để cập nhật hàng loạt">
              <DownloadIcon /> Xuất Excel
            </Button>
          )}
          {duocImport && (
            <Button variant="ghost" onClick={() => setShowImport(true)}>
              <UploadIcon /> Nhập Excel
            </Button>
          )}
          {duocTao && (
            <Button variant="accent" onClick={() => setEditing("new")}>
              <PlusIcon /> Thêm {config.title.toLowerCase()}
            </Button>
          )}
        </div>

        <div className="rc__filterbar">
          <OTim value={q} onChange={setQ} placeholder={config.timGoiY} />
          {config.locNangCao && (
            <button type="button"
              className={`rc__locnc-btn${moLocNC ? " is-open" : ""}${soLocNC > 0 ? " is-active" : ""}`}
              aria-expanded={moLocNC}
              onClick={() => setMoLocNC((v) => !v)}>
              <FilterIcon /> Lọc nâng cao
              {soLocNC > 0 && <span className="chip-count">{soLocNC}</span>}
            </button>
          )}
          <div className="rc__spacer" />
          {config.facet && (
            // `.seg` = charcoal khi chọn. Đúng ngôn ngữ của app: rust dành cho HÀNH ĐỘNG và
            // TOGGLE CHẾ ĐỘ, charcoal dành cho LỰA CHỌN LỌC. Bộ lọc gạch chân rust trước đây nói
            // bằng giọng của cái nút bấm.
            <div className="rc__segs" role="group" aria-label={`Lọc ${config.title.toLowerCase()}`}>
              <button type="button"
                className={`seg${facet === "all" && !xemDaNgung ? " is-active" : ""}`}
                aria-pressed={facet === "all" && !xemDaNgung}
                onClick={() => { setFacet("all"); setXemDaNgung(false); }}>
                Tất cả <span className="chip-count">{tongTheoTim}</span>
              </button>
              {facetValues.map((v) => (
                <button key={v.value} type="button"
                  className={`seg${facet === v.value && !xemDaNgung ? " is-active" : ""}`}
                  aria-pressed={facet === v.value && !xemDaNgung}
                  onClick={() => { setFacet(v.value); setXemDaNgung(false); }}>
                  {v.label} <span className="chip-count">{facetCount(v.value)}</span>
                </button>
              ))}
            </div>
          )}
          {/* KHÔNG phải một chip lọc: nó mở ra một TẬP KHÁC chứ không cắt tập đang xem. Nên tách
              khỏi dải `.seg` bằng một vạch, và để màu trung tính — đây là chỗ cất đồ đã tắt, không
              phải lối đi chính. Chỉ mọc khi THẬT SỰ có mục bị ngừng: đừng bày nút mở ra danh sách
              rỗng. Đây là đường "khôi phục" mà hộp thoại xoá vẫn hứa suốt từ trước tới nay. */}
          {config.softDelete && soDaNgung > 0 && (
            <button type="button"
              className={`rc__ngung${xemDaNgung ? " is-active" : ""}`}
              aria-pressed={xemDaNgung}
              onClick={() => setXemDaNgung((v) => !v)}>
              Hiện mục đã ngừng <span className="chip-count">{soDaNgung}</span>
            </button>
          )}
        </div>
        {config.locNangCao && (
          <LocNangCao defs={config.locNangCao} value={locNC} onChange={setLocNC}
            mo={moLocNC} token={token} />
        )}
      </header>

      {/* Bảng RỖNG vì tải hỏng thì để khối rỗng nói (nó có nút Tải lại rồi) — hai chỗ cùng kêu một
          lỗi kèm hai nút "Tải lại" là bắt người ta đoán xem nên bấm cái nào. Banner ở đây chỉ còn
          lo lỗi XẢY RA KHI BẢNG ĐANG CÓ DỮ LIỆU (xoá hụt, bật lại hụt). */}
      {error && !bangTrong && (
        <div className="banner banner--error" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: "12px" }} onClick={() => { setError(null); load(); }}>Tải lại</button>
        </div>
      )}

      <div className="rc__tablewrap">
        <table className="rc__table">
          <thead>
            <tr>
              <th style={{ width: widthMa }}>Mã</th>
              {/* TÊN là cột người ta đọc để nhận ra dòng — cho nó rộng nhất. 16% cũ làm tên sản
                  phẩm xuống 2–3 dòng trong khi cột bên cạnh bỏ trống. */}
              <th style={{ width: widthTen }}>Tên</th>
              {config.columns.map((c, i) => {
                const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                const w = rongCot[i];
                return <th key={c.key} style={w ? { width: w } : undefined} className={isCenter ? "text-center" : ""}>{c.label}</th>;
              })}
              {coCotNut && <th className="rc__actcol" style={{ width: `${rongCotNut}px` }}>Hành động</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Skeleton: 5 hàng ô shimmer thay cho dòng chữ "Đang tải…"
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="rc-skel__row">
                  <td><span className="rc-skel" style={{ width: "60%" }} /></td>
                  <td><span className="rc-skel" style={{ width: "80%" }} /></td>
                  {config.columns.map((c) => (
                    <td key={c.key}><span className="rc-skel" style={{ width: "50%" }} /></td>
                  ))}
                  {coCotNut && <td className="rc__actcol"><span className="rc-skel" style={{ width: "70px" }} /></td>}
                </tr>
              ))
            ) : rows.length === 0 ? (
              // BA ca khác hẳn nhau, đừng gộp: (a) chưa có gì · (b) bộ lọc không ra · (c) TẢI HỎNG.
              // Trước 15/08/2026 backend chết là bảng vẫn in "Chưa có giấy nào trong hệ thống." —
              // bảng NÓI SAI SỰ THẬT, và câu sai đó còn mời người ta đi tạo lại dữ liệu đang có.
              <tr>
                <td colSpan={config.columns.length + (coCotNut ? 3 : 2)} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <CircleXIcon size={48} sw={1.5}
                      className={`rc__empty-icon${error ? " rc__empty-icon--loi" : ""}`} />
                    <p className="rc__empty-text">
                      {error
                        ? "Không tải được danh sách."
                        : dangLoc
                          ? "Không tìm thấy kết quả phù hợp với bộ lọc."
                          : `Chưa có ${config.title.toLowerCase()} nào trong hệ thống.`}
                    </p>
                    {error && <p className="rc__empty-sub">{error}</p>}
                    {error ? (
                      <Button variant="ghost" onClick={() => { setError(null); load(); }}>Tải lại</Button>
                    ) : dangLoc ? (
                      <Button variant="ghost" onClick={() => { setQ(""); setFacet("all"); setXemDaNgung(false); }}>Xóa bộ lọc</Button>
                    ) : duocTao ? (
                      <Button variant="ghost" onClick={() => setEditing("new")}><PlusIcon /> Tạo {config.title.toLowerCase()}</Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ) : rows.map((r) => {
              const noWrapKeys = ["ma", "dai", "bac", "active", "version_no", "gsm", "kho", "don_vi_gia", "don_gia", "kho_max", "so_to_bu_hao", "order_no", "created_at"];
              // Cột chữ PHỤ (không phải định danh) — cắt 1 dòng + "…", đủ chữ xem lúc rê chuột
              // (title). Thiếu luật này thì dòng nào rơi vào chữ dài (vd Ghi chú) là cao vọt hẳn
              // lên so với dòng bên cạnh — bảng nhìn lởm chởm dù dữ liệu không có gì bất thường.
              const clipKeys = [
                "ghi_chu", "nhom", "don_vi_vao", "kieu_bu_hao",
                // Cùng dạng "chữ phụ dài": tên khác của Ghi chú/Mô tả/Vị trí/Nhóm ở các danh mục
                // khác (Công việc khoán, Chủng loại giấy, Lý do & lỗi SX, Kho hàng, Máy, Khuôn).
                "note", "mo_ta", "vi_tri", "loai_may", "khach_hang_ten", "so_ke",
                // Thành phẩm: tên khách đặt lần đầu ("Công ty TNHH …") — đủ chữ xem trong drawer.
                "customer_ten",
                // Khuôn: "Loại" ("Khuôn ép kim") và "Tình trạng" ("Đang đặt làm") là
                // nhãn ánh xạ nhưng có giá trị dài hơn hẳn số còn lại trong cùng cột — cột hẹp
                // nên vỡ 2-3 dòng ngay cả khi các giá trị khác vẫn gọn 1 dòng.
                "loai", "tinh_trang",
              ];
              // Cắt 1 dòng CHỈ TRÊN ĐIỆN THOẠI (dt). Khác `clipKeys` ở chỗ class `rc__clip-dt`
              // KHÔNG có luật nào ở cấp cao nhất — luật duy nhất của nó nằm trong
              // `@media screen and (max-width: 768px)` của `styles/responsive.css` (§71.3), nên
              // màn ≥769px giữ nguyên hành vi xuống dòng đầy đủ.
              // Tiêu chí KCS: cột "Hướng dẫn" (`rebuildCatalogConfigs.tsx:924`) là câu văn xuôi
              // dài nhất trong cả 14 màn danh mục — cột `huong_dan` của model cho tới 500 ký tự.
              // Không có luật này thì ở 375px (cột rộng 96px) một hàng cao tới 404px. Nhưng dùng
              // `rc__clip` dùng-chung thì `rebuild-catalog.css:983` (ngoài mọi `@media`) cắt luôn
              // cả trên máy bàn — nhân viên KCS mất câu hướng dẫn ở tầm nhìn. Đây là cột
              // `huong_dan` DUY NHẤT trong `REBUILD_CONFIGS`, không màn nào khác dính theo.
              const clipDtKeys = ["huong_dan"];
              return (
                <tr key={r.id} className={`rc__row${r.active === false ? " rc__row--ngung" : ""}`}
                  onClick={() => setEditing(r)}>
                  <td className="rc__mono rc__nowrap"><span className="rc__code-badge" title={String(r.ma)}>{String(r.ma)}</span></td>
                  <td className="rc__name">
                    {/* Flex nằm trên DIV con, không phải trên `<td>`: `display:flex` thẳng trên ô
                        bảng phá vỡ mô hình table-cell (trình duyệt tự bọc nó vào 1 cell ẩn cao
                        bằng đúng nội dung), nên khi hàng bị kéo cao bởi cột bên cạnh (vd Bậc số
                        lượng nhiều dòng), Tên bị dính lên đỉnh thay vì căn giữa như các cột khác. */}
                    <div className="rc__name-inner">
                      {/* ĐƯỜNG BÀN PHÍM để mở dòng. Cả hàng vẫn bấm được bằng chuột (tiện, quen tay),
                          nhưng cái mở được bằng Tab + Enter/Space phải là một `<button>` THẬT nằm
                          trong ô Tên — KHÔNG phải `role="button"` dán lên `<tr>`: gán vai nút cho
                          hàng là xoá luôn vai "row" của nó, trình đọc màn hình mất cả cấu trúc bảng
                          (không còn đọc được "cột Ghi chú: …"). Đặt trên TÊN cũng nói rõ chỗ nào
                          bấm được — trước đây cả hàng bấm được mà không có dấu hiệu nào. */}
                      <button type="button" className="rc__open"
                        aria-label={`Mở ${String(r.ten)} (${String(r.ma)})`}
                        onClick={() => setEditing(r)}>
                        {String(r.ten)}
                      </button>
                      {r.active === false && (
                        <span className="badge-sem badge-sem--muted" title="Đã ngừng dùng — không hiện ở ô chọn khi tạo mới, nhưng chứng từ cũ vẫn giữ nguyên">
                          Đã ngừng
                        </span>
                      )}
                      {/* GỠ 06/09/2026: badge "Trạm giấy". Đơn vị không còn mang cờ trạm — 5 chặng
                          của dòng giấy nay khai thẳng ở ô Đơn vị vào/ra của màn Công đoạn. */}
                    </div>
                  </td>
                  {config.columns.map((c) => {
                    const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                    const isClip = clipKeys.includes(c.key);
                    const classes = [
                      isCenter ? "text-center" : "",
                      noWrapKeys.includes(c.key) ? "rc__nowrap" : "",
                      isClip ? "rc__clip" : "",
                      clipDtKeys.includes(c.key) ? "rc__clip-dt" : "",
                    ].filter(Boolean).join(" ");
                    const noi = c.render ? c.render(r, extra ? (extra[String(r.id)] ?? null) : undefined) : (r[c.key] == null || r[c.key] === "" ? "" : String(r[c.key]));
                    const meoChu = isClip && typeof noi === "string" && noi !== "" ? noi : undefined;
                    return (
                      <td key={c.key} className={classes || undefined} title={meoChu}>
                        {noi}
                      </td>
                    );
                  })}
                  {/* Không có quyền thì ô rỗng, KHÔNG phải nút xám: nút xám vẫn là một lời mời,
                      người ta hover đi hover lại tìm cách bật nó lên. Chữ "Xóa" giữ nguyên bên
                      cạnh icon — thùng rác trần bắt người dùng đoán, mà đoán sai ở đây là mất dòng. */}
                  {/* Nút nằm trong MỘT hàng flex (`.rc__acts`) chứ không thả inline trong ô: hai
                      `inline-flex` đứng cạnh nhau canh theo đường chân chữ, mà nút có icon lấy đáy
                      SVG làm chân chữ ⇒ "Xóa" bị đội cao hơn "Nhân bản" 2px. Nhãn đọc màn hình kèm
                      TÊN dòng: cả cột đều là "Xóa", nghe một chuỗi "Xóa, Xóa, Xóa" là không biết
                      đang đứng ở dòng nào. */}
                  {coCotNut && (
                  <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                    <div className="rc__acts">
                    {r.active === false ? (
                      duocBatLai && (
                        <button type="button" className="rc__link-btn" onClick={() => batLai(r)}
                          aria-label={`Bật lại ${String(r.ten)}`}
                          title="Cho dùng lại — mục này sẽ hiện lại ở các ô chọn">
                          <UndoIcon />
                          <span>Bật lại</span>
                        </button>
                      )
                    ) : (
                      <>
                        {duocClone && (
                          <button type="button" className="rc__link-btn" onClick={() => clone(r)}
                            aria-label={`Nhân bản ${String(r.ten)}`}
                            title="Nhân bản — tạo một dòng mới sao y dòng này, đổi tên rồi lưu">
                            <CopyIcon />
                            <span>Nhân bản</span>
                          </button>
                        )}
                        {duocXoa && (
                          <button type="button" className="rc__link-btn rc__link-btn--danger" onClick={() => remove(r)}
                            aria-label={`Xóa ${String(r.ten)}`} title="Xóa">
                            <TrashIcon size={13} />
                            <span>Xóa</span>
                          </button>
                        )}
                      </>
                    )}
                    </div>
                  </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Chân bảng: `total` là tổng SAU bộ lọc (đúng cái đang được cắt trang), khác con số "N mục"
          trên tiêu đề = tổng theo ô tìm, không theo tab. Bảng rỗng thì ẩn — khối "chưa có / không
          tìm thấy" đã nói giúp, thêm dòng "Tổng 0 bản ghi" là thừa. Khóa nút khi đang tải để
          bấm dồn không đẻ ra hai lượt gọi chồng nhau. */}
      {total > 0 && (
        <Pager total={total} page={page} size={PAGE_SIZE} onPage={setPage} loading={loading} unit="bản ghi" />
      )}

      {editing && (
        <CatalogDrawer config={config} existing={editing === "new" ? null : editing}
          onClose={() => { setEditing(null); lamMoi(); }}
          onSaved={(moi) => {
            setEditing(config.moLaiSauKhiTao && editing === "new" && moi ? moi : null);
            lamMoi();
            onMutate?.();
          }} />
      )}

      {deleting && token && config.renderDeleteDialog?.(deleting, {
        token,
        onClose: () => setDeleting(null),
        onDone: () => { setDeleting(null); lamMoi(); onMutate?.(); },
      })}

      {confirmDeleteRow && token && (
        <XoaDanhMucDialog
          row={confirmDeleteRow}
          config={config}
          token={token}
          onClose={() => setConfirmDeleteRow(null)}
          onXong={() => { lamMoi(); onMutate?.(); }}
          onLoi={setError}
        />
      )}

      {showImport && token && (
        <ImportExcelDialog
          ten={config.title.toLowerCase()}
          chay={(f, mode) => crud(config.prefix).importExcel(token, f, mode)}
          onClose={() => setShowImport(false)}
          onImported={() => { setShowImport(false); lamMoi(); onMutate?.(); }}
        />
      )}
    </main>
    </DieuHuongDanhMuc.Provider>
  );
}
