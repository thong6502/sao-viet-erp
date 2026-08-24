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
import { CatalogDrawer } from "./CatalogDrawer";
import { OTim } from "./OTim";
import { XoaDanhMucDialog } from "./XoaDanhMucDialog";
import { CircleXIcon, PlusIcon, TrashIcon } from "./icons";
import type { CatalogConfig } from "./types";
import "../rebuild-catalog.css";

/** Số dòng mỗi trang của MỌI màn danh mục. Trang cắt Ở MÁY CHỦ (`page`+`size`): mỗi lần mở màn
 *  chỉ kéo về 20 dòng, không phải cả danh mục. Tìm kiếm và tab lọc vì thế cũng phải chạy ở máy
 *  chủ — lọc trong JS trên 20 dòng đang xem sẽ biến ô tìm thành "tìm trong trang này".
 *
 *  ⚠️ KHÔNG export: đây là con số của MÀN NÀY. Chỗ khác cần "20" thì tự khai — chia sẻ hằng này
 *  ra ngoài là sớm muộn có người đổi nó cho màn của họ rồi kéo cả 10 màn danh mục đi theo. */
const PAGE_SIZE = 20;

export function CatalogListPage({ config, onMutate }: { config: CatalogConfig; onMutate?: () => void }) {
  const { token } = useAuth();
  const can = useCan();
  // Gác nút GHI theo quyền module. Trước 15/08/2026 màn này không hỏi quyền một câu nào: vai
  // chỉ-đọc vẫn thấy đủ Thêm / Xóa / Bật lại, bấm xong mới ăn 403 — nút bày ra để rồi từ chối.
  // `moduleQuyen` bỏ trống (vd màn dùng trong test) = không gác, hành vi cũ y nguyên.
  const mQuyen = config.moduleQuyen;
  // `khongTaoTay` / `khongXoa` là luật CỦA MÀN, đứng TRƯỚC quyền: có quyền tạo vẫn không tạo
  // tay được, vì dòng ở đó do hệ sinh (xem `types.ts`).
  const duocTao = !config.khongTaoTay && (!mQuyen || can(mQuyen, "create"));
  const duocXoa = !config.khongXoa && (!mQuyen || can(mQuyen, "delete"));
  const duocBatLai = !mQuyen || can(mQuyen, "update");
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Row | "new" | null>(null);
  const [deleting, setDeleting] = useState<Row | null>(null);      // renderDeleteDialog: dialog xóa riêng
  const [q, setQ] = useState("");
  const qTre = useTre(q);              // gõ xong 300ms mới hỏi máy chủ
  const [facet, setFacet] = useState("all");
  // Xem các mục ĐÃ NGỪNG DÙNG. Trước 14/08/2026 hộp thoại xoá hứa "có thể khôi phục lại khi cần"
  // mà màn lọc cứng `active:true` và không có nút nào bật lại — ẩn xong là mất tăm, lời hứa suông.
  const [xemDaNgung, setXemDaNgung] = useState(false);
  const [soDaNgung, setSoDaNgung] = useState(0);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);                                  // tổng SAU bộ lọc
  const [facets, setFacets] = useState<Record<string, number>>({});       // số cho từng tab lọc
  // Đổi bộ lọc thì về trang đầu — đứng ở trang 7 rồi gõ tìm còn 3 kết quả là bảng trống trơn.
  useEffect(() => { setPage(1); }, [qTre, facet, xemDaNgung]);

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
    })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
        if (r.facets) setFacets(r.facets);
        // Xoá nốt dòng cuối của trang cuối ⇒ `total` co lại mà `page` đứng yên ⇒ bảng rỗng trơn,
        // người dùng tưởng mất sạch dữ liệu. Lùi về trang cuối còn thật.
        const ve = trangHopLe(page, r.total, PAGE_SIZE);
        if (ve !== null) setPage(ve);
      })
      // Giữ LÝ DO thôi, không gói sẵn câu "Không tải được danh sách" vào đây: khối rỗng của bảng
      // đã nói câu đó rồi, nhét cả hai vào một chỗ là đọc ra hai lần cùng một ý.
      .catch((e) => setError(e instanceof ApiError ? e.message : "Máy chủ không phản hồi."))
      .finally(() => setLoading(false));
  }, [token, api, config.softDelete, xemDaNgung, page, qTre, facet, facetKey]);
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
  const tongTheoTim = useMemo(() => {
    const ds = Object.values(facets);
    return config.facet && ds.length ? ds.reduce((a, b) => a + b, 0) : total;
  }, [config.facet, facets, total]);
  // `xemDaNgung` cũng là một bộ lọc: bảng rỗng lúc đó KHÔNG có nghĩa "chưa có gì trong hệ thống".
  const dangLoc = qTre.trim() !== "" || facet !== "all" || xemDaNgung;
  const bangTrong = !loading && rows.length === 0;

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

  const facetCount = (v: string) => facets[v] ?? 0;

  return (
    // `rc--dm`: scope RIÊNG của màn danh mục. Không dùng `.rc` sẵn có làm mốc vì `KhoPage` và
    // `KhoHangView` cũng là `<main className="rc">` — đè theo `.rc` là rò ngược sang Kho.
    // Xem khối "GIÀNH LẠI …" ở cuối `rebuild-catalog.css`.
    <main className="rc rc--dm">
      {/* HEADER — MỘT dạng cho cả 10 màn, ba hàng cố định trên một kẻ ngang:
            1. tiêu đề · pill đếm ····· [+ Thêm …]
            2. (chỉ khi có `subtitle`) một dòng giải thích
            3. [ô tìm] ····· dải chip lọc │ công tắc "Hiện mục đã ngừng"
          Trước đây bố cục rẽ theo việc `subtitle` có chữ hay không — một trường NỘI DUNG mà
          quyết định KHUNG, nên hai màn bỏ trống nó (Công đoạn · Đơn vị) trông như màn của app
          khác. Nay `subtitle` chỉ quyết định có render dòng chữ đó hay không. */}
      <header className="rc__head">
        <div className="rc__headrow">
          <h1 className="rc__title">{config.heading ?? config.title}</h1>
          <span className="rc__count">{tongTheoTim} mục</span>
          <div className="rc__spacer" />
          {duocTao && (
            <Button variant="accent" onClick={() => setEditing("new")}>
              <PlusIcon /> Thêm {config.title.toLowerCase()}
            </Button>
          )}
        </div>

        {/* Không có mô tả thì KHÔNG render thẻ rỗng: một `<p>` trống vẫn ăn margin, header của hai
            màn cạnh nhau tụt lệch nhau vài pixel mà không ai hiểu vì sao. */}
        {config.subtitle ? <p className="rc__sub">{config.subtitle}</p> : null}

        <div className="rc__filterbar">
          <OTim value={q} onChange={setQ} />
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
              <th style={{ width: "14%" }}>Mã</th>
              {/* TÊN là cột người ta đọc để nhận ra dòng — cho nó rộng nhất. 16% cũ làm tên sản
                  phẩm xuống 2–3 dòng trong khi cột bên cạnh bỏ trống. */}
              <th style={{ width: "24%" }}>Tên</th>
              {config.columns.map((c) => {
                const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                // ⚠️ `table-layout: fixed` + `width: 100%`: cột KHÔNG khai bề rộng ăn TRỌN phần
                // còn lại. Màn Thành phẩm chỉ có đúng một cột như vậy (ĐVT) nên nó chiếm 46% màn
                // hình cho một chữ "hộp", còn Tên bị ép xuống 3 dòng (chủ báo 22/08/2026).
                // ĐVT ở cả ba danh mục (Giấy · Vật tư khác · Thành phẩm) đều là một chip ngắn.
                const w = c.key === "quy_doi_text" ? "34%"
                  : c.key === "canh_bao" ? "12%"
                  : c.key === "ghi_chu" ? "22%"
                  : c.key === "don_vi_gia" ? "9%"
                  : undefined;
                return <th key={c.key} style={w ? { width: w } : undefined} className={isCenter ? "text-center" : ""}>{c.label}</th>;
              })}
              <th className="rc__actcol" style={{ width: "8%", textAlign: "right" }}>Hành động</th>
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
                  <td className="rc__actcol"><span className="rc-skel" style={{ width: "70px" }} /></td>
                </tr>
              ))
            ) : rows.length === 0 ? (
              // BA ca khác hẳn nhau, đừng gộp: (a) chưa có gì · (b) bộ lọc không ra · (c) TẢI HỎNG.
              // Trước 15/08/2026 backend chết là bảng vẫn in "Chưa có giấy nào trong hệ thống." —
              // bảng NÓI SAI SỰ THẬT, và câu sai đó còn mời người ta đi tạo lại dữ liệu đang có.
              <tr>
                <td colSpan={config.columns.length + 3} className="rc__empty-state-td">
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
              const noWrapKeys = ["ma", "dai", "bac", "active", "version_no", "gsm", "kho", "don_vi_gia", "don_gia", "kho_max", "so_to_bu_hao"];
              return (
                <tr key={r.id} className={`rc__row${r.active === false ? " rc__row--ngung" : ""}`}
                  onClick={() => setEditing(r)}>
                  <td className="rc__mono rc__nowrap"><span className="rc__code-badge" title={String(r.ma)}>{String(r.ma)}</span></td>
                  <td className="rc__name">
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
                    {Boolean(r.tram_dong_giay) && (
                      <span className="badge-sem badge-sem--steel" title={`Trạm dòng giấy: ${String(r.tram_dong_giay)}`}>
                        Trạm giấy
                      </span>
                    )}
                  </td>
                  {config.columns.map((c) => {
                    const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                    const classes = [
                      isCenter ? "text-center" : "",
                      noWrapKeys.includes(c.key) ? "rc__nowrap" : ""
                    ].filter(Boolean).join(" ");
                    return (
                      <td key={c.key} className={classes || undefined}>
                        {c.render ? c.render(r, extra ? (extra[String(r.id)] ?? null) : undefined) : (r[c.key] == null || r[c.key] === "" ? "—" : String(r[c.key]))}
                      </td>
                    );
                  })}
                  {/* Không có quyền thì ô rỗng, KHÔNG phải nút xám: nút xám vẫn là một lời mời,
                      người ta hover đi hover lại tìm cách bật nó lên. Chữ "Xóa" giữ nguyên bên
                      cạnh icon — thùng rác trần bắt người dùng đoán, mà đoán sai ở đây là mất dòng. */}
                  <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                    {r.active === false ? (
                      duocBatLai && (
                        <button type="button" className="rc__link-btn" onClick={() => batLai(r)}
                          title="Cho dùng lại — mục này sẽ hiện lại ở các ô chọn">
                          <span>Bật lại</span>
                        </button>
                      )
                    ) : (
                      duocXoa && (
                        <button type="button" className="rc__link-btn rc__link-btn--danger" onClick={() => remove(r)} title="Xóa">
                          <TrashIcon size={13} />
                          <span>Xóa</span>
                        </button>
                      )
                    )}
                  </td>
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
    </main>
  );
}
