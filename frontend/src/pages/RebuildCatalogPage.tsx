// Trang danh mục GENERIC (rebuild) — list + drawer form theo SECTION + search + filter tab.
// 1 component cho 6 module (Máy · Vật liệu · Công đoạn · Loại SP) qua `config`. On-brand với
// design system app (tokens rust/ink/paper). Form lean nhưng có nhóm; đủ theo spec là follow-up.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Pager, trangHopLe } from "../components/Pager";
import { ApiError, authed } from "../api/client";
import {
  crud, giayVersions, addGiayVersion, nhatKyDanhMuc,
  type GiayGiaVersion, type NhatKyItem, type Row,
} from "../api/rebuildCatalog";
import { kyThuatMay } from "../api/kyThuatMay";
import "./rebuild-catalog.css";

export interface FieldDef {
  key: string;
  label: string;
  // `ref-search-ma` = như `ref-search` nhưng lưu MÃ (chuỗi) thay vì id — cho cột trỏ danh mục bằng
  // mã như `don_vi_gia` (quy đổi làm việc trên mã `kg`/`to`, không trên id).
  type?: "text" | "number" | "date" | "select" | "checkbox" | "json" | "ref" | "ref-multi" | "ref-search" | "ref-search-ma" | "bands" | "size_tiers" | "nhom_may" | "nhom_may-multi" | "formula" | "dau-viec-dinh-muc" | "chuan_bi_khoan" | "lich_bao_tri" | "don_vi_toc_do";
  options?: { value: string; label: string }[];
  /** Ô `formula`: ÉP bộ chip theo loại này thay vì suy từ màn. Cần khi MỘT màn có hai ô công thức
   *  hỏi hai câu khác nhau — "Công thức tính giá" (ra tiền) vs "Công thức tính lượng" (ra lượng,
   *  cần chip `sl_vao`/`sl_ra`, không cần chip đơn giá). */
  loaiO?: string;
  refPrefix?: string;           // ref / ref-multi / ref-search: endpoint danh mục nguồn (đổ theo TÊN/MÃ)
  /** Query thêm khi nạp danh mục nguồn, vd `{ active: true }` — không lọc thì picker mời cả dòng
   *  đã ngừng dùng, người ta chọn xong bấm Lưu mới ăn lỗi từ server. */
  refParams?: Record<string, unknown>;
  required?: boolean;
  /** Chuỗi tĩnh, HOẶC hàm dựng câu từ chính form đang gõ — vd quy cách đóng gói hiện
   *  "1 thùng = 3 kg" ghép từ ô đơn vị đóng gói + ô hệ số + ĐVT. Câu đọc được kiểm bằng mắt
   *  ngay lúc khai, đỡ hơn hẳn hai ô số rời không nói lên nghĩa gì. */
  hint?: string | ((form: Record<string, unknown>) => string);
  group?: string;               // nhóm section trong drawer
  showIf?: (form: Record<string, unknown>) => boolean;  // ẩn/hiện field theo giá trị khác
  default?: unknown;            // prefill khi TẠO MỚI (giá trị thật, không phải placeholder "0")
  jsonKey?: string;             // field lưu LỒNG trong cột JSON này (vd "fields_theo_loai")
}
export interface ColumnDef {
  key: string;
  label: string;
  /** `extra` = dữ liệu PHỤ của chính dòng này, do `config.loadExtra` nạp song song (vd trạng thái
   *  máy lúc này). `undefined` khi chưa nạp xong hoặc dòng không có gì để nói. */
  render?: (r: Row, extra?: unknown) => ReactNode;
}
export interface FacetDef {
  key: string;                  // field lọc (vd "nhom")
  values: { value: string; label: string }[];
  /** Nhóm máy do xưởng tự đặt: sinh thêm tab cho giá trị có thật trong dữ liệu mà
   *  `values` chưa liệt kê — khai cứng sẽ bỏ sót nhóm người dùng tự đặt. */
  dynamic?: boolean;
}
/** "Nhóm máy" là CHỮ TỰ DO nên phải đoán bằng tên. Định nghĩa ở đây (không phải trong
 *  `rebuildCatalogConfigs`) vì cả trang lẫn config cùng dùng, mà config đã import từ file này —
 *  để bên kia rồi import ngược lại là thành vòng tròn. */
export const isMayIn = (val: unknown) => {
  const s = String(val || "").trim().toLowerCase();
  return s === "máy in" || s === "in ngoài" || s.startsWith("in ") || s.includes("máy in") || s.includes("in offset");
};

export interface CatalogConfig {
  title: string;
  subtitle?: string;
  showCount?: boolean;
  prefix: string;
  /** Khoá loại của bản ghi trong nhật ký (`"{loai}:{id}"` — khớp `LOAI_MODULE` ở backend).
   *  Có khoá này thì drawer mọc thêm tab "Nhật ký" khi đang SỬA một bản ghi đã lưu. */
  nhatKyLoai?: string;
  columns: ColumnDef[];
  fields: FieldDef[];
  facet?: FacetDef;             // tab lọc phía trên (tùy chọn)
  /** Dữ liệu PHỤ nạp SONG SONG danh sách, khoá theo id bản ghi — cột nào cần thì đọc ở tham số
   *  thứ hai của `render`. Dùng cho số DẪN XUẤT không thuộc bản ghi (vd trạng thái máy suy từ sự
   *  cố + vùng khoá + lệnh đang chạy). Cố ý KHÔNG nhét vào schema CRUD dùng chung: schema đó
   *  đang đổ dropdown cho cả chục màn khác, bắt họ trả giá cho số chỉ một màn cần là sai chỗ.
   *  Hỏng thì NUỐT (trả `{}`) — mất cột phụ không được phép làm trắng cả bảng danh mục. */
  loadExtra?: (token: string) => Promise<Record<string, unknown>>;
  /** Chia phần khai báo thành nhiều TAB theo `group`. Chỉ màn khai dài mới cần (Máy có 7 nhóm,
   *  cuộn một mạch rất mệt). Không khai thì render một mạch như cũ. Nhóm không liệt kê ở đây rơi
   *  vào tab ĐẦU TIÊN — quên khai một nhóm thì nó vẫn hiện, không biến mất im lặng. */
  tabsKhai?: { id: string; label: string; groups: string[] }[];
  // Block phụ cuối drawer (preview BHR của Máy · bảng quy đổi của Đơn vị). `existing` = null khi
  // đang TẠO — block nào cần id thì tự nhắc "lưu trước đã".
  renderExtra?: (form: Record<string, unknown>, existing: Row | null) => ReactNode;
  hasVersions?: boolean;        // bật lịch sử giá (Giấy): thêm cột "Phiên bản" bấm mở lịch sử
  softDelete?: boolean;         // "Xóa" = ẩn mềm (active=false), giữ dữ liệu; list chỉ hiện active
  autoCode?: boolean;           // mã sinh NGẦM ở backend → ẩn ô "Mã" lúc tạo, không gửi ma
  /** Tạo xong thì GIỮ drawer mở ở bản ghi vừa tạo. Dùng cho màn có khối con phải gắn vào id (vd
   *  Đơn vị: tạo "tấn" xong khai ngay quy đổi) — đóng phắt là bắt người ta đi tìm lại dòng. */
  moLaiSauKhiTao?: boolean;
  deriveInitial?: (existing: Row | null) => Record<string, unknown>;  // giá trị UI suy ra khi mở form (vd _method)
  // map field UI → body API trước khi gửi. `existing` = bản ghi đang sửa (null khi TẠO) — cần khi
  // phải GỘP vào một cột JSON: field bị `showIf` ẩn thì không có trong `body`, dựng lại cột JSON
  // từ số 0 là xoá mất các khoá khác của cột đó.
  transformSubmit?: (
    body: Record<string, unknown>,
    form: Record<string, unknown>,
    existing: Row | null,
  ) => Record<string, unknown>;
  /** Ghi đè luồng XÓA mặc định (window.confirm + ẩn mềm) bằng dialog riêng — vd Kho: kiểm kho
   *  còn tồn / phiếu chờ ghi sổ / đề nghị dở rồi bắt gõ mã mới cho xóa. Dialog tự gọi API; xong
   *  gọi ctx.onDone (đóng + reload), hủy thì ctx.onClose. */
  renderDeleteDialog?: (row: Row, ctx: { token: string; onClose: () => void; onDone: () => void }) => ReactNode;
}

/** Số dòng mỗi trang của MỌI màn danh mục. Trang cắt Ở MÁY CHỦ (`page`+`size`): mỗi lần mở màn
 *  chỉ kéo về 20 dòng, không phải cả danh mục. Tìm kiếm và tab lọc vì thế cũng phải chạy ở máy
 *  chủ — lọc trong JS trên 20 dòng đang xem sẽ biến ô tìm thành "tìm trong trang này". */
const PAGE_SIZE = 20;

/** Chờ người ta gõ xong mới hỏi máy chủ. Không có nó thì mỗi phím là một request. */
function useTre<T>(giaTri: T, ms = 300): T {
  const [tre, setTre] = useState(giaTri);
  useEffect(() => {
    const t = setTimeout(() => setTre(giaTri), ms);
    return () => clearTimeout(t);
  }, [giaTri, ms]);
  return tre;
}

export function RebuildCatalogPage({ config, onMutate }: { config: CatalogConfig; onMutate?: () => void }) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Row | "new" | null>(null);
  const [pricingRow, setPricingRow] = useState<Row | null>(null);  // hasVersions: mở drawer Lịch sử giá
  const [deleting, setDeleting] = useState<Row | null>(null);      // renderDeleteDialog: dialog xóa riêng
  const [q, setQ] = useState("");
  const qTre = useTre(q);              // gõ xong 300ms mới hỏi máy chủ
  const [facet, setFacet] = useState("all");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);                                  // tổng SAU bộ lọc
  const [facets, setFacets] = useState<Record<string, number>>({});       // số cho từng tab lọc
  // Đổi bộ lọc thì về trang đầu — đứng ở trang 7 rồi gõ tìm còn 3 kết quả là bảng trống trơn.
  useEffect(() => { setPage(1); }, [qTre, facet]);

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
      ...(config.softDelete ? { active: true } : {}),   // xóa mềm: chỉ hiện dòng còn active
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
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách."))
      .finally(() => setLoading(false));
  }, [token, api, config.softDelete, page, qTre, facet, facetKey]);
  useEffect(() => { load(); }, [load]);

  // Dữ liệu phụ nạp RIÊNG, không đi kèm mỗi lần lật trang: nó là map cho CẢ danh mục (vd trạng
  // thái mọi máy), lật trang không làm nó khác đi. Chỉ nạp lại sau khi có người ghi (`tick`).
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!token || !config.loadExtra) return;
    // Hỏng thì để nguyên `null` — cột phụ sẽ nói "chưa biết" chứ không bịa ra trạng thái đẹp.
    config.loadExtra(token).then(setExtra).catch(() => setExtra(null));
  }, [token, config.loadExtra, tick]);

  /** Sau khi TẠO / SỬA / XÓA: tải lại cả bảng lẫn dữ liệu phụ. */
  const lamMoi = useCallback(() => { load(); setTick((t) => t + 1); }, [load]);

  // Tab lọc: giữ THỨ TỰ khai sẵn, nối thêm giá trị TỰ DO người dùng đã khai (facet.dynamic) —
  // nay đọc từ `facets` của máy chủ, vì màn chỉ cầm 20 dòng nên không tự quét ra được nữa.
  const facetValues = useMemo(() => {
    const f = config.facet;
    if (!f) return [];
    if (!f.dynamic) return f.values;
    const known = new Set(f.values.map((v) => v.value));
    const them = Object.keys(facets)
      .filter((v) => v && !known.has(v))
      .sort((a, b) => a.localeCompare(b, "vi"));
    return [...f.values, ...them.map((v) => ({ value: v, label: v }))];
  }, [config.facet, facets]);

  // Số cạnh tiêu đề và số trên tab "Tất cả": tổng theo Ô TÌM, KHÔNG theo tab đang chọn — đứng ở
  // tab "Bế" mà tiêu đề tụt xuống còn 3 thì người ta tưởng danh mục có 3 dòng.
  // `total` là tổng SAU cả tab, nên màn có tab thì cộng từ `facets`. Khoá rỗng trong `facets` là
  // dòng chưa khai giá trị đó — vẫn phải cộng, bỏ đi là "Tất cả" hụt số.
  const tongTheoTim = useMemo(() => {
    const ds = Object.values(facets);
    return config.facet && ds.length ? ds.reduce((a, b) => a + b, 0) : total;
  }, [config.facet, facets, total]);
  const dangLoc = qTre.trim() !== "" || facet !== "all";

  const [confirmDeleteRow, setConfirmDeleteRow] = useState<Row | null>(null);

  async function remove(r: Row) {
    if (!token) return;
    if (config.renderDeleteDialog) { setDeleting(r); return; }   // luồng xóa riêng (vd Kho)
    setConfirmDeleteRow(r);
  }

  const facetCount = (v: string) => facets[v] ?? 0;

  return (
    <main className="rc">
      {config.subtitle ? (
        <>
          <header className="rc__head">
            <div className="rc__headrow">
              <h1 className="rc__title">{config.title}</h1>
              {config.showCount !== false && <span className="rc__count">{tongTheoTim} mục</span>}
            </div>
            <p className="rc__sub">{config.subtitle}</p>
          </header>

          <div className="rc__toolbar">
            <div className="rc__search-wrapper">
              <SearchIcon />
              <input className="rc__search" placeholder="Tìm mã / tên…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <div className="rc__spacer" />
            <Button variant="accent" onClick={() => setEditing("new")}>
              <PlusIcon /> Thêm {config.title.toLowerCase()}
            </Button>
          </div>
        </>
      ) : (
        <div className="rc__unified-bar">
          <div className="rc__headrow">
            <h1 className="rc__title">{config.title}</h1>
            {config.showCount !== false && <span className="rc__count">{tongTheoTim} mục</span>}
          </div>
          <div className="rc__unified-right">
            <div className="rc__search-wrapper">
              <SearchIcon />
              <input className="rc__search" placeholder="Tìm mã / tên…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <Button variant="accent" onClick={() => setEditing("new")}>
              <PlusIcon /> Thêm {config.title.toLowerCase()}
            </Button>
          </div>
        </div>
      )}

      {config.facet && (
        <div className="rc__tabs">
          <button className={`rc__tab${facet === "all" ? " is-active" : ""}`} onClick={() => setFacet("all")}>
            Tất cả <span className="rc__tabn">{tongTheoTim}</span>
          </button>
          {facetValues.map((v) => (
            <button key={v.value} className={`rc__tab${facet === v.value ? " is-active" : ""}`}
              onClick={() => setFacet(v.value)}>
              {v.label} <span className="rc__tabn">{facetCount(v.value)}</span>
            </button>
          ))}
        </div>
      )}

      {error && (
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
              <th style={{ width: "16%" }}>Tên</th>
              {config.columns.map((c) => {
                const isCenter = c.key === "bac" || c.key === "dai" || c.key === "active";
                const w = c.key === "quy_doi_text" ? "34%" : c.key === "canh_bao" ? "12%" : c.key === "ghi_chu" ? "16%" : undefined;
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
              <tr>
                <td colSpan={config.columns.length + 3} className="rc__empty-state-td">
                  <div className="rc__empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="rc__empty-icon">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="m15 9-6 6M9 9l6 6"/>
                    </svg>
                    <p className="rc__empty-text">
                      {dangLoc ? "Không tìm thấy kết quả phù hợp với bộ lọc." : `Chưa có ${config.title.toLowerCase()} nào trong hệ thống.`}
                    </p>
                    {dangLoc ? (
                      <Button variant="ghost" onClick={() => { setQ(""); setFacet("all"); }}>Xóa bộ lọc</Button>
                    ) : (
                      <Button variant="ghost" onClick={() => setEditing("new")}><PlusIcon /> Tạo {config.title.toLowerCase()}</Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : rows.map((r) => {
              const noWrapKeys = ["ma", "dai", "bac", "active", "version_no", "gsm", "kho", "don_vi_gia", "don_gia", "kho_max", "so_to_bu_hao"];
              return (
                <tr key={r.id} className="rc__row" onClick={() => setEditing(r)}>
                  <td className="rc__mono rc__nowrap"><span className="rc__code-badge" title={String(r.ma)}>{String(r.ma)}</span></td>
                  <td className="rc__name">
                    {String(r.ten)}
                    {Boolean(r.tram_dong_giay) && (
                      <span className="rc__tram-badge" title={`Trạm dòng giấy: ${String(r.tram_dong_giay)}`}>
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
                  <td className="rc__actcol" onClick={(e) => e.stopPropagation()}>
                    {config.hasVersions && (
                      <button type="button" className="rc__link-btn" onClick={() => setPricingRow(r)} title="Lịch sử giá / nhập đơn giá">
                        <TagIcon />
                        <span>Giá</span>
                      </button>
                    )}
                    <button type="button" className="rc__link-btn rc__link-btn--danger" onClick={() => remove(r)} title="Xóa">
                      <TrashIcon2 />
                      <span>Xóa</span>
                    </button>
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

      {pricingRow && (
        <PriceHistoryDrawer row={pricingRow}
          onClose={() => setPricingRow(null)}
          onSaved={() => { setPricingRow(null); lamMoi(); }} />
      )}

      {deleting && token && config.renderDeleteDialog?.(deleting, {
        token,
        onClose: () => setDeleting(null),
        onDone: () => { setDeleting(null); lamMoi(); onMutate?.(); },
      })}

      {confirmDeleteRow && (
        <ConfirmDialog
          open={!!confirmDeleteRow}
          title="Xóa danh mục"
          message={
            config.softDelete
              ? `Xóa "${confirmDeleteRow.ten}" (${confirmDeleteRow.ma})? Bản ghi sẽ được ẩn khỏi danh sách và có thể khôi phục lại khi cần.`
              : `Xóa "${confirmDeleteRow.ten}" (${confirmDeleteRow.ma})? Hành động này sẽ xóa hoàn toàn bản ghi khỏi hệ thống.`
          }
          confirmLabel="Xóa danh mục"
          danger
          onConfirm={async () => {
            if (!token) return;
            const r = confirmDeleteRow;
            setConfirmDeleteRow(null);
            if (config.softDelete) {
              try {
                await api.update(token, r.id, { ...r, active: false });
                lamMoi();
                onMutate?.();
              } catch (e) {
                setError(e instanceof ApiError ? e.message : "Không xóa được danh mục.");
              }
            } else {
              try {
                await api.remove(token, r.id);
                lamMoi();
                onMutate?.();
              } catch (e) {
                setError(e instanceof ApiError ? e.message : "Không xóa được.");
              }
            }
          }}
          onCancel={() => setConfirmDeleteRow(null)}
        />
      )}
    </main>
  );
}

// ── PRICE HISTORY DRAWER (Lịch sử giá Giấy — xem phiên bản + thêm đơn giá mới) ────
function PriceHistoryDrawer({ row, onClose, onSaved }: {
  row: Row; onClose: () => void; onSaved: () => void;
}) {
  const { token } = useAuth();
  const [versions, setVersions] = useState<GiayGiaVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const numOf = (v: unknown) => Number(v) || 0;
  const [form, setForm] = useState({
    don_gia: "",
    don_vi_gia: String(row.don_vi_gia ?? "kg"),
    ngay_hieu_luc: "",
    ghi_chu: "",
  });
  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }));

  const reload = useCallback(() => {
    if (!token) return;
    setLoading(true);
    giayVersions(token, row.id)
      .then((v) => setVersions(v))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được lịch sử giá."))
      .finally(() => setLoading(false));
  }, [token, row.id]);
  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (!token) return;
    const dg = Number(form.don_gia);
    if (!(dg >= 0) || form.don_gia === "") { setErr("Nhập đơn giá hợp lệ."); return; }
    setSaving(true); setErr(null);
    try {
      // Ảnh chụp: giữ nguyên gsm/khổ hiện hành của giấy, chỉ đổi đơn giá + ĐVT + ngày + lý do.
      await addGiayVersion(token, row.id, {
        gsm: numOf(row.gsm),
        kho_dai: numOf(row.kho_dai),
        kho_rong: numOf(row.kho_rong),
        don_vi_gia: form.don_vi_gia,
        don_gia: dg,
        gia_thi_truong: row.gia_thi_truong != null ? numOf(row.gia_thi_truong) : null,
        ngay_hieu_luc: form.ngay_hieu_luc || null,
        ghi_chu: form.ghi_chu.trim() || null,
      });
      setForm((p) => ({ ...p, don_gia: "", ghi_chu: "" }));
      reload();
      onSaved();  // reload danh sách chính để cột Giá (don_gia mirror) cập nhật
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Lưu đơn giá thất bại.");
    } finally { setSaving(false); }
  }

  const DVT: Record<string, string> = { kg: "KG", cai: "CÁI", ram: "Ram", to: "Tờ", tan: "Tấn" };
  const vnd = (v: unknown) => (v == null ? "—" : Number(v).toLocaleString("vi-VN"));

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">Lịch sử giá</div>
            <h2 className="rc-drawer__title">{String(row.ma)} · {String(row.ten)}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="rc-drawer__body">
          {err && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{err}</div>}

          <section className="rc-sec">
            <div className="rc-sec__title">Thêm đơn giá mới</div>
            <div className="rc-grid">
              <label className="rc-field">
                <span className="rc-field__label">Đơn giá *</span>
                <div className="rc-input-wrapper">
                  <input className="rc-input rc-input--num" type="number" step="any" inputMode="decimal"
                    value={form.don_gia} placeholder="0" onChange={(e) => set("don_gia", e.target.value)} />
                </div>
              </label>
              <label className="rc-field">
                <span className="rc-field__label">ĐVT</span>
                <div className="rc-input-wrapper">
                  <select className="rc-input" value={form.don_vi_gia} onChange={(e) => set("don_vi_gia", e.target.value)}>
                    {Object.entries(DVT).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              </label>
              <label className="rc-field">
                <span className="rc-field__label">Ngày hiệu lực</span>
                <div className="rc-input-wrapper">
                  <input className="rc-input" type="date" value={form.ngay_hieu_luc} onChange={(e) => set("ngay_hieu_luc", e.target.value)} />
                </div>
              </label>
              <label className="rc-field rc-field--full">
                <span className="rc-field__label">Lý do đổi giá</span>
                <div className="rc-input-wrapper">
                  <input className="rc-input" type="text" value={form.ghi_chu} placeholder="vd: NCC tăng giá"
                    onChange={(e) => set("ghi_chu", e.target.value)} />
                </div>
              </label>
            </div>
            <div style={{ marginTop: "var(--sp-3)" }}>
              <Button type="button" variant="primary" loading={saving} onClick={submit}>Lưu đơn giá</Button>
            </div>
            <span className="rc-field__hint">Giữ nguyên định lượng {vnd(row.gsm)}g · khổ {vnd(row.kho_rong)}×{vnd(row.kho_dai)} hiện hành; tạo phiên bản mới và cập nhật giá đang dùng.</span>
          </section>

          <section className="rc-sec">
            <div className="rc-sec__title">Các phiên bản giá</div>
            {loading ? (
              <div className="rc__msg">Đang tải…</div>
            ) : versions.length === 0 ? (
              <div className="rc-bands__empty">Chưa có phiên bản giá.</div>
            ) : (
              <div className="rc__tablewrap">
                <table className="rc__table">
                  <thead>
                    <tr>
                      <th>#</th><th className="text-center">Hiện dùng</th>
                      <th className="rc__nowrap">Đơn giá</th><th>ĐVT</th>
                      <th className="rc__nowrap">Hiệu lực</th><th>Lý do</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr key={v.id} className="rc__row">
                        <td className="rc__mono">{v.version_no}</td>
                        <td className="text-center">{v.is_current ? "✓" : ""}</td>
                        <td className="rc__nowrap">{vnd(v.don_gia)}</td>
                        <td>{DVT[v.don_vi_gia] ?? v.don_vi_gia}</td>
                        <td className="rc__nowrap">{v.ngay_hieu_luc ?? "—"}</td>
                        <td>{v.ghi_chu ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onClose}>Đóng</Button>
        </footer>
      </aside>
    </div>
  );
}

const TagIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82Z" />
    <circle cx="7" cy="7" r="1.2" />
  </svg>
);

// ── UTILITY: PARSE UNIT SUFFIX FROM LABEL ─────────────────────────────────────────
function parseLabelAndSuffix(label: string): { cleanLabel: string; suffix: string | null } {
  const parenMatch = label.match(/\s*\(([^)]+)\)\s*$/);
  if (parenMatch) {
    return { cleanLabel: label.replace(parenMatch[0], "").trim(), suffix: parenMatch[1] };
  }
  const percentMatch = label.match(/\s*%\s*$/);
  if (percentMatch) {
    return { cleanLabel: label.replace(percentMatch[0], "").trim(), suffix: "%" };
  }
  return { cleanLabel: label, suffix: null };
}

// ── UTILITY: SUGGEST NEXT SEQUENTIAL CODE ─────────────────────────────────────────
function tienToMa(prefix: string): string {
  if (prefix.includes("loai-san-pham")) return "LSP-";
  if (prefix.includes("may-thiet-bi")) return "TB-";
  if (prefix.includes("cong-doan")) return "CD-";
  if (prefix.endsWith("/kho")) return "KHO-";
  if (prefix.includes("giay")) return "GL-";
  if (prefix.includes("muc")) return "MUC-";
  if (prefix.includes("ban-kem")) return "KEM-";
  if (prefix.includes("quy-tac-binh-bai")) return "BB-";
  return "MA-";
}

function soLonNhat(rows: Row[], codePrefix: string): number {
  const numRegex = new RegExp(`^${codePrefix}(\\d+)$`);
  let maxNum = 0;
  for (const r of rows) {
    const m = String(r.ma).trim().toUpperCase().match(numRegex);
    if (m) {
      const val = parseInt(m[1], 10);
      if (val > maxNum) maxNum = val;
    }
  }
  return maxNum;
}

/** Mã gợi ý cho bản ghi mới — HỎI MÁY CHỦ, không đoán từ mấy dòng đang hiện trên bảng.
 *
 *  Từ khi màn phân trang ở máy chủ, bảng chỉ cầm 20 dòng: đoán mã lớn nhất trong đó là đứng ở
 *  trang 1 (sắp theo mã tăng dần) sẽ gợi ý ra mã ĐÃ CÓ, người khai bấm Lưu mới ăn lỗi trùng.
 *  Danh sách sắp tăng dần nên mã lớn nhất nằm ở TRANG CUỐI — hai request nhẹ (một để biết tổng,
 *  một để lấy trang cuối) thay cho việc kéo cả danh mục về. */
async function goiYMaTiepTheo(prefix: string, token: string): Promise<string> {
  const codePrefix = tienToMa(prefix);
  const api = crud(prefix);
  const dau = await api.list(token, { q: codePrefix, size: 1 });
  const soTrang = Math.max(1, Math.ceil(dau.total / 200));
  const cuoi = dau.total > 1
    ? await api.list(token, { q: codePrefix, size: 200, page: soTrang })
    : dau;
  return `${codePrefix}${String(soLonNhat(cuoi.items, codePrefix) + 1).padStart(4, "0")}`;
}

// ── INLINE SVG ICONS ─────────────────────────────────────────────────────────────
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="rc__search-icon">
    <circle cx="11" cy="11" r="8"/>
    <path d="m21 21-4.3-4.3"/>
  </svg>
);



const TrashIcon2 = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
  </svg>
);

/** Đồng hồ — dùng ở cột "Tốc độ & Chuẩn bị" bên `rebuildCatalogConfigs`, nên phải export. */
export const ClockIcon = ({ width = 12, height = 12 }: { width?: number; height?: number }) => (
  <svg width={width} height={height} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3.5 2" />
  </svg>
);

const ArrowUpIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="m18 15-6-6-6 6"/>
  </svg>
);

const ArrowDownIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="m6 9 6 6 6-6"/>
  </svg>
);

const TrashIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/>
  </svg>
);

const PlusIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "4px" }}>
    <path d="M5 12h14M12 5v14"/>
  </svg>
);

// ── CUSTOM SUGGEST COMPONENT (Dropdown + Text input toggle) ──────────────────────────
// ── BANDS EDITOR (bậc số lượng động: Từ SL · Đến SL · Giá trị · Đơn vị) ──────────
interface BacRow { sl_tu?: number | null; sl_den?: number | null; gia_tri?: number; don_vi?: string }
function BandsField({ value, onChange }: { value: BacRow[]; onChange: (v: BacRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<BacRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => {
    const lastRow = rows[rows.length - 1];
    const nextTu = lastRow && lastRow.sl_den != null ? lastRow.sl_den : 0;
    onChange([...rows, { sl_tu: nextTu, sl_den: null, gia_tri: 0, don_vi: lastRow?.don_vi ?? "to" }]);
  };
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const num = (v: unknown) => (v === "" || v == null ? "" : String(v));
  return (
    <div className="rc-bands">
      <table className="rc-bands__table">
        <thead>
          <tr><th>Từ SL</th><th>Đến SL</th><th>Giá trị</th><th>Đơn vị</th><th></th></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={5} className="rc-bands__empty">Chưa có bậc — bấm “＋ Thêm bậc”.</td></tr>
          )}
          {rows.map((r, i) => {
            const isRangeInvalid = r.sl_den !== null && r.sl_den !== undefined && (r.sl_tu ?? 0) >= r.sl_den;
            return (
              <tr key={i} className={isRangeInvalid ? "rc-bands__row--invalid" : ""}>
                <td>
                  <input
                    className={`rc-input rc-input--num${isRangeInvalid ? " rc-input--invalid" : ""}`}
                    type="number"
                    value={num(r.sl_tu)}
                    title={isRangeInvalid ? "Từ SL phải bé hơn Đến SL" : undefined}
                    onChange={(e) => setRow(i, { sl_tu: e.target.value === "" ? 0 : Number(e.target.value) })}
                  />
                </td>
                <td>
                  <input
                    className={`rc-input rc-input--num${isRangeInvalid ? " rc-input--invalid" : ""}`}
                    type="number"
                    placeholder="∞"
                    value={num(r.sl_den)}
                    title={isRangeInvalid ? "Từ SL phải bé hơn Đến SL" : undefined}
                    onChange={(e) => setRow(i, { sl_den: e.target.value === "" ? null : Number(e.target.value) })}
                  />
                </td>
                <td>
                  <input
                    className="rc-input rc-input--num"
                    type="number"
                    step="any"
                    value={num(r.gia_tri)}
                    onChange={(e) => setRow(i, { gia_tri: e.target.value === "" ? 0 : Number(e.target.value) })}
                  />
                </td>
                <td style={{ textAlign: "center" }}>
                  <div className="rc-bands__unit-toggle">
                    <button
                      type="button"
                      className={`rc-bands__unit-btn${(r.don_vi ?? "to") === "to" ? " is-active" : ""}`}
                      onClick={() => setRow(i, { don_vi: "to" })}
                    >
                      Tờ
                    </button>
                    <button
                      type="button"
                      className={`rc-bands__unit-btn${(r.don_vi ?? "to") === "pct" ? " is-active" : ""}`}
                      onClick={() => setRow(i, { don_vi: "pct" })}
                    >
                      %
                    </button>
                  </div>
                </td>
                <td style={{ textAlign: "center" }}>
                  <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xóa bậc">
                    <TrashIcon />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <button type="button" className="rc-bands__add" onClick={add}>＋ Thêm bậc</button>
    </div>
  );
}

// ── ĐƠN VỊ TỐC ĐỘ: bảng NHÃN hiển thị cho cột danh sách (ô CHỌN lấy động — xem `DonViTocDoField`) ─
//
// Lịch sử: 04/08/2026 từng KHOÁ CỨNG danh sách này (bỏ nguồn động) vì đổ hết cờ `dung_lam_toc_do`
// làm ô mọc nhiều lựa chọn Lệnh SX không dùng được. 11/08/2026 (theo yêu cầu chủ) ô chọn QUAY LẠI
// lấy động từ `/api/don-vi` (lọc `dung_lam_toc_do`) để hết cảnh hai danh sách lệch nhau. Danh sách
// dưới GIỜ chỉ còn là NHÃN hiển thị (fallback) cho cột danh sách máy, không phải nguồn của ô chọn.
//
// 🔴 Mã giữ khuôn `<đơn vị đếm>_gio`. Lệnh SX CHỈ khớp thời lượng với `to_gio · cai_gio · kem_gio`
// (`_DV_VAO_SANG_NS` trong `lsx_service.py`). Đơn vị khác vẫn LƯU được (ghi nhận năng lực máy) nhưng
// bước KHÔNG lấy tốc độ từ máy — thời gian chạy để trống, KHÔNG cảnh báo. Muốn bớt lựa chọn thừa thì
// BỎ TICK `dung_lam_toc_do` ở màn Đơn vị cho các đơn vị chưa chạy được (chỉ giữ tờ · cái · kẽm).
export const DON_VI_TOC_DO: { ma: string; nhan: string }[] = [
  { ma: "ban_proof_gio", nhan: "bản proof/h" },
  { ma: "mau_gio", nhan: "mẫu/h" },
  { ma: "kem_gio", nhan: "kẽm/h" },
  { ma: "to_gio", nhan: "tờ/h" },
  { ma: "tan_gio", nhan: "tấn/h" },
  { ma: "me_gio", nhan: "mẻ/h" },
  { ma: "m2_gio", nhan: "m²/h" },
  { ma: "nhip_gio", nhan: "nhịp/h" },
  { ma: "hop_gio", nhan: "hộp/h" },
];

function DonViTocDoField({
  value, onChange, donViList,
}: {
  value: string;
  onChange: (v: string) => void;
  donViList: Row[];
}) {
  // Đơn vị tốc độ lấy ĐỘNG từ danh mục Đơn vị (đơn vị có tick "dùng làm tốc độ"), KHÔNG còn danh
  // sách viết cứng — thêm/bớt/đổi quản MỘT chỗ ở màn Đơn vị & quy đổi. Giá trị lưu vẫn là
  // `<mã>_gio` để khớp máy đã khai + engine Lệnh SX (chỉ khớp thời lượng với to_gio/cai_gio/kem_gio).
  const opts = donViList
    .filter((d) => d.dung_lam_toc_do === true)
    .map((d) => ({ ma: `${d.ma}_gio`, nhan: `${d.ten}/h` }));
  // Máy khai từ trước bằng mã nay không còn bày (đơn vị bỏ tick / đơn vị cũ) vẫn phải hiện ra —
  // bỏ qua là mở form thấy trống, bấm Lưu một cái là xoá mất khai báo đang đúng.
  const laKhaiCu = value !== "" && !opts.some((d) => d.ma === value);
  const nhanCu = value.endsWith("_gio") ? `${value.slice(0, -4)}/h` : value;
  return (
    <select className="rc-input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">— chọn —</option>
      {opts.map((d) => (
        <option key={d.ma} value={d.ma}>{d.nhan}</option>
      ))}
      {laKhaiCu && <option value={value}>{nhanCu} — khai cũ</option>}
    </select>
  );
}

// ── NHÓM MÁY: chọn + thêm/xoá NGAY TẠI CHỖ ─────────────────────────────────────
//
// Danh mục THẬT (`/api/nhom-may`) chứ không còn là chữ tự do khai cứng trong code. Giá trị lưu
// trên máy vẫn là CHỮ (`may_thiet_bi.loai_may`) — bảng chỉ quản danh sách tên được bày ra.
// Quyền `dm_thiet_bi` = đúng module của màn này, nên không có cảnh thấy nút rồi ăn 403.
// 🔴 Xoá nhóm còn máy dùng bị backend CHẶN kèm số máy — hiện nguyên câu đó cho người ta biết
// phải đi sửa mấy máy, đừng nuốt thành "không xoá được".
const nhomMayApi = crud("/api/nhom-may");

function NhomMayField({
  value, onChange, options, onCatalogChanged,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Row[];
  onCatalogChanged: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const coQuyen = can("dm_thiet_bi", "create") && can("dm_thiet_bi", "delete");
  const [moQuanLy, setMoQuanLy] = useState(false);
  const [tenMoi, setTenMoi] = useState("");
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  async function xoa(row: Row) {
    if (!token) return;
    setBan(true); setLoi(null);
    try {
      await nhomMayApi.remove(token, row.id);
      if (value === row.ten) onChange("");
      onCatalogChanged();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xoá được nhóm máy.");
    } finally { setBan(false); }
  }

  async function them() {
    const ten = tenMoi.trim();
    if (!token || !ten) return;
    setBan(true); setLoi(null);
    try {
      await nhomMayApi.create(token, { ten });
      setTenMoi("");
      onChange(ten);            // vừa tạo là chọn luôn — không bắt bấm thêm một nhát
      onCatalogChanged();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không tạo được nhóm máy.");
    } finally { setBan(false); }
  }

  return (
    <div className="rc-dvtd">
      <div className="rc-dvtd__row">
        <select className="rc-input" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">— chọn nhóm máy —</option>
          {options.map((o) => (
            <option key={o.id} value={String(o.ten)}>{String(o.ten)}</option>
          ))}
        </select>
        {coQuyen && (
          <button type="button" className="rc-dvtd__manage" onClick={() => setMoQuanLy((v) => !v)}>
            {moQuanLy ? "Xong" : "＋ Thêm / xoá"}
          </button>
        )}
      </div>
      {moQuanLy && coQuyen && (
        <div className="rc-dvtd__panel">
          {loi && <div className="rc-dvtd__err">{loi}</div>}
          <div className="rc-dvtd__chips">
            {options.length === 0 && <span className="rc__chip-muted">Chưa có nhóm máy nào.</span>}
            {options.map((o) => (
              <span key={o.id} className="rc-dvtd__chip">
                {String(o.ten)}
                <button type="button" disabled={ban} title="Xoá nhóm (chỉ được khi không còn máy nào dùng)"
                  onClick={() => xoa(o)}>×</button>
              </span>
            ))}
          </div>
          <div className="rc-dvtd__row">
            <input className="rc-input" value={tenMoi} disabled={ban}
              placeholder="Tên nhóm mới, vd: Ép kim"
              onChange={(e) => setTenMoi(e.target.value)} />
            <button type="button" className="rc-dvtd__manage" disabled={ban || !tenMoi.trim()}
              onClick={them}>Thêm</button>
          </div>
          <p className="rc-field__hint">
            Nhóm đang có máy dùng thì không xoá được — đổi nhóm cho những máy đó trước đã.
          </p>
        </div>
      )}
    </div>
  );
}

// ── CHUẨN BỊ THEO KHOẢN (thay giấy 15p · thay mực 18p → tổng 33p) ────────────────
// Tổng là Ô CHỈ ĐỌC, tự cộng. Cho sửa tay ô tổng là đẻ nguồn chân lý thứ hai: sửa một khoản rồi
// tổng không khớp thì không ai biết bên nào đúng. Tổng này chính là số ghi vào
// `makeready_time_default` — cột Xếp lịch đang đọc (xem transformSubmit của CFG_MAY).
export interface ChuanBiKhoanRow { ten?: string; phut?: number }

export function tongChuanBi(rows: ChuanBiKhoanRow[] | undefined): number {
  return (rows ?? []).reduce((s, r) => s + (Number(r.phut) || 0), 0);
}

function ChuanBiKhoanField({
  value,
  onChange,
}: { value: ChuanBiKhoanRow[]; onChange: (v: ChuanBiKhoanRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<ChuanBiKhoanRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => onChange([...rows, { ten: "", phut: 0 }]);
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const tong = tongChuanBi(rows);
  return (
    <div className="rc-bands">
      <table className="rc-bands__table">
        <thead>
          <tr><th>Việc chuẩn bị</th><th>Số phút</th><th></th></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={3} className="rc-bands__empty">Chưa có khoản — bấm “＋ Thêm khoản”.</td></tr>
          )}
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <input
                  className="rc-input"
                  value={r.ten ?? ""}
                  placeholder="vd: Thay giấy"
                  onChange={(e) => setRow(i, { ten: e.target.value })}
                />
              </td>
              <td>
                <input
                  className="rc-input rc-input--num"
                  type="number"
                  step="any"
                  inputMode="decimal"
                  value={r.phut === undefined || r.phut === null ? "" : String(r.phut)}
                  onChange={(e) => setRow(i, { phut: e.target.value === "" ? undefined : Number(e.target.value) })}
                />
              </td>
              <td style={{ textAlign: "center" }}>
                <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xóa khoản">
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td style={{ textAlign: "right", fontWeight: 600 }}>Tổng (tự cộng)</td>
            <td style={{ fontWeight: 700 }}>{tong.toLocaleString("vi-VN")} phút</td>
            <td />
          </tr>
        </tfoot>
      </table>
      <button type="button" className="rc-bands__add" onClick={add}>＋ Thêm khoản</button>
    </div>
  );
}

// ── LỊCH BẢO TRÌ ĐỊNH KỲ — GÓI (có chu kỳ + hạn) → VIỆC CON (nội dung phải làm) ──
// Lưu LỒNG trong fields_theo_loai.lich_bao_tri (jsonKey) — không cột mới, không migration.
// Chỉ GÓI mới có chu kỳ: một lần dừng máy 4 tiếng mà mỗi việc con một hạn riêng thì bảng việc của
// thợ cả đỏ rực 5 dòng cùng nội dung, nhìn vài hôm là hết tin.
export interface HangMucConRow { id?: string; ten?: string }
export interface LichBaoTriRow {
  id?: string; viec?: string; so?: number; don_vi?: string;
  // Mốc cho kỳ ĐẦU TIÊN: kỳ 1 rơi đúng vào ngày này. Từ kỳ 2 trở đi hạn = ngày HOÀN THÀNH phiếu
  // gần nhất + chu kỳ, nên ô này khai MỘT LẦN rồi thôi.
  // ⚠️ KHÁC hẳn ô "Lần cuối làm" đã bỏ 12/08/2026: ô đó bắt sửa lại sau MỖI lần bảo trì nên không
  // ai sửa, còn ô này chỉ để mồi lần đầu. Đừng gộp/gỡ nhầm hai thứ.
  ngay_bat_dau?: string;  // ISO date (yyyy-mm-dd)
  lan_cuoi?: string;      // (đã bỏ khỏi form) giá trị cũ vẫn giữ nguyên trong JSON khi lưu
  dung_phut?: number;     // 0/trống = không phải dừng máy
  hang_muc?: HangMucConRow[];   // việc con trong gói — không có cũng chạy (gói khai từ trước)
}
const DON_VI_CHU_KY = [
  { v: "ngay", n: "ngày" }, { v: "tuan", n: "tuần" },
  { v: "thang", n: "tháng" }, { v: "nam", n: "năm" },
];

/** `id` ỔN ĐỊNH cho mỗi hạng mục — phiếu bảo trì neo vào đây. Neo theo TÊN thì đổi tên là mất
 *  sạch mốc; neo theo THỨ TỰ thì xoá một dòng là mọi phiếu trỏ nhầm hạng mục, im lặng. */
function _hangMucId(): string {
  return `hm-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function LichBaoTriField({
  value,
  onChange,
  mayId = null,
}: { value: LichBaoTriRow[]; onChange: (v: LichBaoTriRow[]) => void; mayId?: number | null }) {
  const { token } = useAuth();
  const rows = value ?? [];
  // Hạn kế tiếp từng gói — CHỈ ĐỌC, tính ở backend từ phiếu bảo trì gần nhất (hoặc "Bắt đầu từ"
  // khi chưa có phiếu nào). Máy chưa lưu (`mayId` null) thì chưa có gì để hỏi.
  const [han, setHan] = useState<Record<string, { han: string | null; nguon: string }>>({});
  useEffect(() => {
    if (!token || !mayId) return;
    let huy = false;
    kyThuatMay.hanCuaMay(token, mayId)
      .then((items) => {
        if (huy) return;
        const m: Record<string, { han: string | null; nguon: string }> = {};
        for (const it of items) if (it.goi_id) m[it.goi_id] = { han: it.han, nguon: it.nguon };
        setHan(m);
      })
      // Nuốt lỗi có chủ đích: dòng "Kỳ tới" là thông tin PHỤ, thiếu quyền đọc module Kỹ thuật máy
      // thì vẫn phải khai được lịch bảo trì như thường.
      .catch(() => setHan({}));
    return () => { huy = true; };
  }, [token, mayId]);
  const setRow = (i: number, patch: Partial<LichBaoTriRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => onChange([...rows, { id: _hangMucId(), viec: "", so: undefined, don_vi: "thang", hang_muc: [] }]);
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));

  const setViecCon = (i: number, list: HangMucConRow[]) => setRow(i, { hang_muc: list });

  return (
    <div className="rc-goi-list">
      {rows.length === 0 && (
        <p className="rc-goi__empty">
          Chưa có gói bảo trì nào. Một gói = một lần dừng máy theo chu kỳ (vd “Bảo trì 3 tháng”),
          bên trong liệt kê những việc phải làm trong lần đó.
        </p>
      )}
      {rows.map((r, i) => {
        const viecCon = r.hang_muc ?? [];
        return (
          <section className="rc-goi" key={r.id ?? i}>
            <div className="rc-goi__head">
              <input
                className="rc-input rc-goi__ten"
                value={r.viec ?? ""}
                placeholder="Tên gói — vd: Bảo trì 3 tháng"
                onChange={(e) => setRow(i, { viec: e.target.value })}
              />
              <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xoá gói bảo trì">
                <TrashIcon />
              </button>
            </div>

            <div className="rc-goi__so">
              <label className="rc-goi__o">
                <span>Mỗi</span>
                <input
                  className="rc-input rc-input--num"
                  type="number" step="any" min={1} inputMode="numeric"
                  value={r.so === undefined || r.so === null ? "" : String(r.so)}
                  onChange={(e) => setRow(i, { so: e.target.value === "" ? undefined : Number(e.target.value) })}
                />
                <select
                  className="rc-input"
                  value={r.don_vi ?? "thang"}
                  onChange={(e) => setRow(i, { don_vi: e.target.value })}
                >
                  {DON_VI_CHU_KY.map((d) => <option key={d.v} value={d.v}>{d.n}</option>)}
                </select>
              </label>
              {/* Mốc kỳ ĐẦU. Không có nó thì màn Phiếu bảo trì không biết gói này tới hạn chưa —
                  đành coi là tới hạn ngay hôm nay, nên bấm "Sinh phiếu từ lịch" là ra một loạt
                  phiếu cùng ngày. Khai một lần ở đây là hết cảnh đó. */}
              <label className="rc-goi__o rc-goi__o--ngay">
                <span>Bắt đầu từ</span>
                <input
                  className="rc-input"
                  type="date"
                  value={r.ngay_bat_dau ?? ""}
                  onChange={(e) => setRow(i, { ngay_bat_dau: e.target.value || undefined })}
                />
              </label>
              {/* "Lần cuối làm" + "Dừng máy (phút)" đã BỎ khỏi form 12/08/2026 (chủ xưởng chốt).
                  Giá trị cũ trong JSON vẫn được giữ nguyên khi lưu (xem transformSubmit) — chỉ là
                  không khai ở đây nữa. Mốc các kỳ SAU đi ra từ PHIẾU bảo trì, đúng một nguồn;
                  "Bắt đầu từ" ở trên chỉ mồi cho kỳ 1, không phải ô đó sống lại. */}
            </div>
            {(r.so ?? 0) > 0 && !r.ngay_bat_dau && !han[r.id ?? ""]?.han && (
              <p className="rc-goi__nhac">
                Chưa có ngày bắt đầu — gói này sẽ bị coi là tới hạn ngay khi sinh phiếu.
              </p>
            )}
            {/* Kỳ tới: CHỈ ĐỌC. Nó đi ra từ phiếu bảo trì gần nhất nên khai tay ở đây là đẻ ra hai
                nguồn sự thật — mốc thật nằm ở phiếu, không nằm trong ô. */}
            {han[r.id ?? ""]?.han && (
              <p className="rc-goi__ky">
                Kỳ tới: <strong>{new Date(`${han[r.id!]!.han}T00:00:00`).toLocaleDateString("vi-VN")}</strong>
                <span className="rc-goi__ky-nguon">
                  {han[r.id!]!.nguon === "phieu"
                    ? "tính từ phiếu bảo trì gần nhất"
                    : han[r.id!]!.nguon === "ngay_bat_dau"
                      ? "kỳ đầu, theo ngày bắt đầu"
                      : "chưa có mốc — coi như tới hạn"}
                </span>
              </p>
            )}

            <div className="rc-goi__viec">
              <div className="rc-goi__viec-head">
                Việc phải làm trong gói
                {/* Đếm việc ĐÃ CÓ TÊN, không đếm dòng trống vừa bấm thêm — "4 việc" trong khi cả
                    4 ô còn trắng là con số nói dối ngay trước mắt người đang gõ. */}
                <span className="rc-goi__dem">
                  {viecCon.filter((h) => (h.ten ?? "").trim()).length || "chưa khai"}
                  {viecCon.some((h) => (h.ten ?? "").trim()) ? " việc" : ""}
                </span>
              </div>
              <ol className="rc-goi__ol">
                {viecCon.map((h, j) => (
                  <li key={h.id ?? j}>
                    <input
                      className="rc-input"
                      value={h.ten ?? ""}
                      placeholder="vd: Thay set dao bế (4 dao)"
                      onChange={(e) => setViecCon(i, viecCon.map((x, k) => (k === j ? { ...x, ten: e.target.value } : x)))}
                    />
                    <button
                      type="button" className="rc-bands__del" title="Xoá việc"
                      onClick={() => setViecCon(i, viecCon.filter((_, k) => k !== j))}
                    >
                      <TrashIcon />
                    </button>
                  </li>
                ))}
              </ol>
              <button
                type="button" className="rc-bands__add"
                onClick={() => setViecCon(i, [...viecCon, { id: _hangMucId(), ten: "" }])}
              >
                ＋ Thêm việc
              </button>
            </div>
          </section>
        );
      })}
      <button type="button" className="rc-bands__add rc-goi__add" onClick={add}>＋ Thêm gói bảo trì</button>
    </div>
  );
}

// ── SIZE-TIER EDITOR (bậc đơn giá theo kích thước: Đến cỡ cm · Đơn giá đ) ─────────
interface SizeTierRow { den_cm?: number | null; don_gia?: number }
function SizeTiersField({ value, onChange }: { value: SizeTierRow[]; onChange: (v: SizeTierRow[]) => void }) {
  const rows = value ?? [];
  const setRow = (i: number, patch: Partial<SizeTierRow>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const add = () => {
    const last = rows[rows.length - 1];
    const nextCap = last && last.den_cm != null ? last.den_cm : 0;
    onChange([...rows, { den_cm: nextCap ? nextCap * 2 : 20, don_gia: 0 }]);
  };
  const del = (i: number) => onChange(rows.filter((_, j) => j !== i));
  const num = (v: unknown) => (v === "" || v == null ? "" : String(v));
  return (
    <div className="rc-bands">
      <table className="rc-bands__table">
        <thead>
          <tr><th>Đến cỡ (cm)</th><th>Đơn giá (đ)</th><th></th></tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={3} className="rc-bands__empty">Chưa có bậc — bấm “＋ Thêm bậc”. Cỡ = cạnh dài thành phẩm.</td></tr>
          )}
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <input className="rc-input rc-input--num" type="number" step="any" placeholder="∞ (trên các mức)"
                  value={num(r.den_cm)}
                  onChange={(e) => setRow(i, { den_cm: e.target.value === "" ? null : Number(e.target.value) })} />
              </td>
              <td>
                <input className="rc-input rc-input--num" type="number" step="any"
                  value={num(r.don_gia)}
                  onChange={(e) => setRow(i, { don_gia: e.target.value === "" ? 0 : Number(e.target.value) })} />
              </td>
              <td style={{ textAlign: "center" }}>
                <button type="button" className="rc-bands__del" onClick={() => del(i)} title="Xóa bậc">
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="rc-bands__add" onClick={add}>＋ Thêm bậc</button>
    </div>
  );
}

// `nang_suat_nguoi_gio` = mức TRUNG BÌNH (số chảy vào công thức thời lượng bước Tổ); min/max chỉ
// để ra khoảng nhanh–chậm, để trống thì ba mức bằng nhau. `don_vi_nang_suat` là NHÃN khai báo —
// không quy đổi, dùng chung bảng mã với ô "Đơn vị tốc độ" của máy.
interface DinhMucRow {
  piece_rate_id: number; nang_suat_nguoi_gio: number;
  nang_suat_nguoi_gio_min?: number | null; nang_suat_nguoi_gio_max?: number | null;
  don_vi_nang_suat?: string | null;
  // Ba mốc nhân lực: tối thiểu ≤ chuẩn ≤ tối đa. Tối thiểu mới là KHAI BÁO, chưa vào công thức.
  so_nguoi_toi_thieu?: number;
  so_nguoi_tieu_chuan: number; so_nguoi_toi_da: number;
  /** VẬT TƯ đầu việc này tiêu thụ (nền BOM, mg 0191) — chỉ DANH SÁCH, không có số lượng: định mức
   *  tuỳ quy cách từng lệnh nên số khai ở đây là số chết. Số suy lúc bung ở bước lệnh. */
  vat_tu_ids?: number[];
}
// `donViVao` vẫn nằm trong props (chỗ gọi truyền vào) nhưng KHÔNG dùng nữa: đơn vị năng suất
// giờ do người khai chọn ở từng dòng, không còn suy theo đơn vị vào của công đoạn.
function DinhMucDauViecField({ value, options, departmentId, onChange }: {
  value: DinhMucRow[]; options: Row[]; departmentId: number | null; donViVao: string;
  onChange: (v: DinhMucRow[]) => void;
}) {
  const { token } = useAuth();
  const allowed = options.filter((o) => Number(o.department_id) === departmentId);
  const selected = new Set(value.map((r) => r.piece_rate_id));
  const patch = (i: number, p: Partial<DinhMucRow>) => onChange(value.map((r, j) => j === i ? { ...r, ...p } : r));

  // Danh mục Vật tư khác cho dropdown gắn vật tư. Nạp TẠI ĐÂY chứ không qua `refData` chung: cột
  // này là danh mục thứ HAI của cùng một field, mà bộ nạp chung khoá theo một `refPrefix` mỗi field.
  const [vatTu, setVatTu] = useState<Row[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    crud("/api/vat-lieu-kho/vat-tu-in-an").list(token, { active: true })
      .then((r) => { if (alive) setVatTu(r.items); })
      .catch(() => { if (alive) setVatTu([]); });
    return () => { alive = false; };
  }, [token]);
  const vatTuTheoId = useMemo(() => new Map(vatTu.map((v) => [Number(v.id), v])), [vatTu]);
  // Hàng phụ đang mở — mỗi lúc một dòng, mở cái khác thì cái cũ đóng (bảng đã 10 cột, bung hai
  // hàng cùng lúc là mất dấu dòng nào của ai).
  const [moVatTu, setMoVatTu] = useState<number | null>(null);
  return <div className="rc-bands rc-bands--dinh-muc">
    {!departmentId ? <div className="rc-bands__empty">Chọn Tổ phụ trách trước.</div> : <>
      <div className="rc-dinh-muc-wrapper">
        <table className="rc-dinh-muc-table">
          <thead>
            <tr className="rc-dinh-muc-table__group-row">
              <th rowSpan={2} className="rc-col--left">Đầu việc chi tiết</th>
              <th colSpan={4} className="rc-col--group rc-group--ns">Năng suất khoán</th>
              <th colSpan={3} className="rc-col--group rc-group--nl">Định mức nhân lực (người)</th>
              {/* Cột "Mặc định" (radio chọn đầu việc điền sẵn) GỠ 12/08/2026 — xem mg 0190. Bế tay
                  hay bế máy là quyết định theo HÀNG, không khai một lần ở danh mục được. */}
              {/* VẬT TƯ đầu việc tiêu thụ (mg 0191) — nền BOM. Chỉ danh sách, KHÔNG có số lượng. */}
              <th rowSpan={2} className="rc-col--center"
                title="Vật tư đầu việc này tiêu thụ. Số lượng tính ở lệnh theo quy cách.">Vật tư</th>
              <th rowSpan={2} className="rc-col--center" style={{ width: 36 }} />
            </tr>
            <tr className="rc-dinh-muc-table__sub-row">
              <th className="rc-col--num">Trung bình</th>
              <th className="rc-col--num">Tối thiểu</th>
              <th className="rc-col--num">Tối đa</th>
              <th className="rc-col--unit">Đơn vị</th>
              <th className="rc-col--num">Tối thiểu</th>
              <th className="rc-col--num">Chuẩn</th>
              <th className="rc-col--num">Tối đa</th>
            </tr>
          </thead>
          <tbody>{value.length === 0 && <tr><td colSpan={10} className="rc-bands__empty">
            {allowed.length === 0 ? "Tổ này chưa có đầu việc khoán để liên kết." : "Chưa chọn đầu việc định mức."}
          </td></tr>}{value.map((r, i) => { const opt = options.find((o) => o.id === r.piece_rate_id); const vtIds = r.vat_tu_ids ?? []; const mo = moVatTu === r.piece_rate_id; return <Fragment key={r.piece_rate_id}><tr>
            <td className="rc-col--left rc-dinh-muc-name">{opt ? `${opt.ma} · ${opt.ten}` : `#${r.piece_rate_id}`}</td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" value={r.nang_suat_nguoi_gio} onChange={(e) => patch(i, { nang_suat_nguoi_gio: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" placeholder="—"
              value={r.nang_suat_nguoi_gio_min ?? ""}
              onChange={(e) => patch(i, { nang_suat_nguoi_gio_min: e.target.value === "" ? null : Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="0.01" step="any" placeholder="—"
              value={r.nang_suat_nguoi_gio_max ?? ""}
              onChange={(e) => patch(i, { nang_suat_nguoi_gio_max: e.target.value === "" ? null : Number(e.target.value) })} /></td>
            {/* KHOÁ theo đơn vị của ĐƠN GIÁ KHOÁN (chủ chốt 10/08/2026) — chữ, không phải ô chọn.
                Cùng một đầu việc thì tính tiền và đếm năng suất bằng cùng một thứ; khai ở Lương
                khoán rồi thì đừng bắt chọn lại. Đổi đơn vị ⇒ sửa ở màn Lương khoán. */}
            <td className="rc-col--unit rc-dinh-muc-unit">{opt?.don_vi ? `${opt.don_vi}/h` : "—"}</td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_toi_thieu ?? 1} onChange={(e) => patch(i, { so_nguoi_toi_thieu: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_tieu_chuan} onChange={(e) => patch(i, { so_nguoi_tieu_chuan: Number(e.target.value) })} /></td>
            <td className="rc-col--num"><input className="rc-input rc-input--num" type="number" min="1" value={r.so_nguoi_toi_da} onChange={(e) => patch(i, { so_nguoi_toi_da: Number(e.target.value) })} /></td>
            {/* Bấm để bung HÀNG PHỤ ngay dưới — không mở drawer lồng drawer, người khai vẫn thấy
                cả bảng để so các dòng với nhau. */}
            <td className="rc-col--center">
              <button type="button" className={`rc-dm-vt__pill ${mo ? "is-open" : ""} ${vtIds.length ? "" : "is-empty"}`}
                title="Vật tư đầu việc này tiêu thụ"
                onClick={() => setMoVatTu(mo ? null : r.piece_rate_id)}>
                {vtIds.length ? `${vtIds.length} vật tư` : "＋ gắn"}
              </button>
            </td>
            <td className="rc-col--center"><button type="button" className="rc-bands__del" onClick={() => onChange(value.filter((_, j) => j !== i))}><TrashIcon /></button></td>
          </tr>{mo && <tr className="rc-dm-vt__row"><td colSpan={10}>
            <div className="rc-dm-vt">
              {vtIds.length === 0 && <div className="rc-dm-vt__empty">Chưa gắn vật tư nào.</div>}
              {vtIds.map((vid) => { const vt = vatTuTheoId.get(vid); return (
                <div className="rc-dm-vt__item" key={vid}>
                  <span className="rc-dm-vt__ma">{String(vt?.ma ?? `#${vid}`)}</span>
                  <span className="rc-dm-vt__ten">{String(vt?.ten ?? "(đã gỡ khỏi danh mục)")}</span>
                  <span className="rc-dm-vt__dv">{String(vt?.don_vi_gia ?? "—")}</span>
                  <button type="button" className="rc-bands__del" title="Bỏ vật tư khỏi đầu việc"
                    onClick={() => patch(i, { vat_tu_ids: vtIds.filter((x) => x !== vid) })}>
                    <TrashIcon />
                  </button>
                </div>
              ); })}
              <select className="rc-dinh-muc-add__select" value=""
                onChange={(e) => { const id = Number(e.target.value); if (id) patch(i, { vat_tu_ids: [...vtIds, id] }); }}>
                <option value="">＋ chọn từ danh mục vật tư khác</option>
                {vatTu.filter((v) => !vtIds.includes(Number(v.id))).map((v) => (
                  <option key={v.id} value={v.id}>{String(v.ma)} · {String(v.ten)} ({String(v.don_vi_gia ?? "—")})</option>
                ))}
              </select>
              <p className="rc-dm-vt__note">
                Số lượng tính ở lệnh theo quy cách — chỗ này chỉ khai <b>dùng những gì</b>.
              </p>
            </div>
          </td></tr>}</Fragment>; })}</tbody>
        </table>
      </div>
      <div className="rc-dinh-muc-add">
        <select className="rc-dinh-muc-add__select" value="" onChange={(e) => { const id = Number(e.target.value); if (id) onChange([...value, { piece_rate_id: id, nang_suat_nguoi_gio: 1, nang_suat_nguoi_gio_min: null, nang_suat_nguoi_gio_max: null, don_vi_nang_suat: null, so_nguoi_toi_thieu: 1, so_nguoi_tieu_chuan: 1, so_nguoi_toi_da: 1, vat_tu_ids: [] }]); }}>
          <option value="">＋ Chọn đầu việc của tổ</option>{allowed.filter((o) => !selected.has(o.id)).map((o) => <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>)}
        </select>
      </div>
    </>}
  </div>;
}



// ── DRAWER COMPONENT ─────────────────────────────────────────────────────────────
function CatalogDrawer({ config, existing, onClose, onSaved }: {
  config: CatalogConfig; existing: Row | null;
  onClose: () => void; onSaved: (moi?: Row) => void;
}) {
  const { token } = useAuth();
  const api = useMemo(() => crud(config.prefix), [config.prefix]);
  const isEdit = existing != null;
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {
      // Mã gợi ý điền SAU (hỏi máy chủ, xem effect bên dưới) — mở drawer ra ô mã trống một nhịp
      // còn hơn điền sẵn một mã đã có người dùng.
      ma: existing?.ma ?? "",
      ten: existing?.ten ?? ""
    };
    for (const f of config.fields) {
      if (f.type === "ref-multi" || f.type === "nhom_may-multi" || f.type === "bands" || f.type === "size_tiers" || f.type === "dau-viec-dinh-muc") {
        const ev = existing?.[f.key];
        init[f.key] = Array.isArray(ev) ? ev : [];
      } else if (f.jsonKey) {
        // field lồng trong cột JSON (vd fields_theo_loai.click_mau)
        const box = existing?.[f.jsonKey] as Record<string, unknown> | undefined;
        const raw = existing ? box?.[f.key] : undefined;
        // Field kiểu DANH SÁCH phải rơi về [] chứ không phải "" — đưa "" cho editor mảng là vỡ.
        init[f.key] = f.type === "chuan_bi_khoan" || f.type === "lich_bao_tri"
          ? (Array.isArray(raw) ? raw : [])
          : (existing ? raw ?? "" : f.default ?? "");
      } else {
        init[f.key] = existing ? existing[f.key] ?? "" : f.default ?? "";
      }
    }
    if (config.deriveInitial) Object.assign(init, config.deriveInitial(existing));  // vd suy _method từ pricing_basis
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));

  // Mã gợi ý cho bản ghi MỚI (màn nào để người dùng tự đặt mã). Hỏi xong mới điền, và chỉ điền
  // khi ô mã vẫn còn trống — người khai gõ tay trước thì tôn trọng cái họ gõ.
  useEffect(() => {
    if (isEdit || config.autoCode || !token) return;
    let huy = false;
    goiYMaTiepTheo(config.prefix, token)
      .then((ma) => { if (!huy) setForm((p) => (String(p.ma ?? "") ? p : { ...p, ma })); })
      .catch(() => {});   // hỏng thì để trống, người khai tự gõ — không chặn việc tạo mới
    return () => { huy = true; };
  }, [isEdit, config.autoCode, config.prefix, token]);
  const setRef = (key: string, value: string) => {
    if (key !== "department_id" || String(form.department_id ?? "") === value) {
      set(key, value);
      return;
    }
    const dinhMuc = Array.isArray(form.dau_viec_dinh_muc) ? form.dau_viec_dinh_muc : [];
    if (dinhMuc.length > 0 && !window.confirm("Đổi tổ phụ trách sẽ bỏ các đầu việc định mức đã chọn. Tiếp tục?")) return;
    setForm((prev) => ({ ...prev, department_id: value, dau_viec_dinh_muc: [] }));
  };

  // Đổ dropdown "chọn theo tên" cho field ref/ref-multi từ danh mục nguồn.
  const [refData, setRefData] = useState<Record<string, Row[]>>({});
  // Nạp lại danh mục nguồn sau khi người dùng sửa nó NGAY TRONG drawer (vd bật/gỡ đơn vị tốc độ) —
  // `config.fields` là hằng nên effect dưới không tự chạy lại.
  const [refTick, setRefTick] = useState(0);
  const onRefChanged = useCallback(() => setRefTick((t) => t + 1), []);
  useEffect(() => {
    if (!token) return;
    // Gộp `refParams` theo prefix: nhiều field có thể cùng trỏ một danh mục (vd ĐVT và Đơn vị đóng
    // gói đều lấy `/api/don-vi`) — nạp một lần, query là hợp của các field đó.
    const theoPrefix = new Map<string, Record<string, unknown>>();
    for (const f of config.fields) {
      if (!f.refPrefix) continue;
      if (!(f.type === "ref" || f.type === "ref-multi" || f.type === "ref-search" || f.type === "ref-search-ma" || f.type === "dau-viec-dinh-muc" || f.type === "don_vi_toc_do" || f.type === "nhom_may" || f.type === "nhom_may-multi")) continue;
      theoPrefix.set(f.refPrefix, { ...(theoPrefix.get(f.refPrefix) ?? {}), ...(f.refParams ?? {}) });
    }
    if (theoPrefix.size === 0) return;
    let alive = true;
    Promise.all([...theoPrefix].map(([p, params]) =>
      crud(p).list(token, params).then((r) => [p, r.items] as const).catch(() => [p, [] as Row[]] as const)))
      .then((entries) => { if (alive) setRefData(Object.fromEntries(entries)); });
    return () => { alive = false; };
  }, [token, config.fields, refTick]);

  const visibleFields = useMemo(
    () => config.fields.filter((f) => !f.showIf || f.showIf(form)),
    [config.fields, form],
  );

  // Tab đang mở. Màn không chia tab khai báo thì vẫn là "info" như trước; màn có chia (Máy) thì
  // giá trị là id của tab khai. Dùng chung một state với tab "formula"/"nhatky" — hai bộ state
  // song song là sớm muộn có lúc cả hai cùng "đang mở".
  const [formulaTab, setFormulaTab] = useState<string>(config.tabsKhai?.[0]?.id ?? "info");

  const renderField = (f: FieldDef) => {
    const { cleanLabel, suffix } = parseLabelAndSuffix(f.label);
    const hint = typeof f.hint === "function" ? f.hint(form) : f.hint;
    const isFullWidth = f.type === "bands" || f.type === "size_tiers" || f.type === "chuan_bi_khoan" || f.type === "lich_bao_tri" || f.type === "ref-multi" || f.type === "nhom_may-multi" || f.type === "dau-viec-dinh-muc" || f.type === "json" || f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta";
    // "div" chứ không "label": khối này chứa NHIỀU input, bọc trong <label> là bấm đâu cũng nhảy
    // focus vào ô đầu tiên.
    const Tag = f.type === "formula" || f.type === "bands" || f.type === "size_tiers" || f.type === "chuan_bi_khoan" || f.type === "lich_bao_tri" ? "div" : "label";
    return (
      <Tag className={`rc-field${f.type === "checkbox" ? " rc-field--check" : ""}${isFullWidth ? " rc-field--full" : ""}`} key={f.key}>
        <span className="rc-field__label">{cleanLabel}{f.required ? " *" : ""}</span>
        {f.type === "lich_bao_tri" ? (
          <LichBaoTriField value={Array.isArray(form[f.key]) ? (form[f.key] as LichBaoTriRow[]) : []}
            mayId={isEdit && existing ? Number(existing.id) : null}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "chuan_bi_khoan" ? (
          <ChuanBiKhoanField value={Array.isArray(form[f.key]) ? (form[f.key] as ChuanBiKhoanRow[]) : []}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "bands" ? (
          <BandsField value={Array.isArray(form[f.key]) ? (form[f.key] as BacRow[]) : []}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "size_tiers" ? (
          <SizeTiersField value={Array.isArray(form[f.key]) ? (form[f.key] as SizeTierRow[]) : []}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "dau-viec-dinh-muc" ? (
          <DinhMucDauViecField value={Array.isArray(form[f.key]) ? form[f.key] as DinhMucRow[] : []}
            options={refData[f.refPrefix ?? ""] ?? []}
            departmentId={form.department_id ? Number(form.department_id) : null}
            donViVao={String(form.don_vi_vao ?? "")}
            onChange={(v) => set(f.key, v)} />
        ) : f.type === "select" ? (
          <div className="rc-input-wrapper">
            <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)}>
              <option value="">—</option>
              {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        ) : f.type === "nhom_may" ? (
          <NhomMayField
            value={String(form[f.key] ?? "")}
            onChange={(v) => set(f.key, v)}
            options={refData[f.refPrefix ?? ""] ?? []}
            onCatalogChanged={onRefChanged}
          />
        ) : f.type === "nhom_may-multi" ? (
          <NhomMayMultiField
            value={Array.isArray(form[f.key]) ? (form[f.key] as string[]) : []}
            options={refData[f.refPrefix ?? ""] ?? []}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "don_vi_toc_do" ? (
          <DonViTocDoField
            value={String(form[f.key] ?? "")}
            onChange={(v) => set(f.key, v)}
            donViList={refData[f.refPrefix ?? ""] ?? []}
          />
        ) : f.type === "ref" ? (
          <div className="rc-input-wrapper">
            <select className="rc-input" value={String(form[f.key] ?? "")} onChange={(e) => setRef(f.key, e.target.value)}>
              <option value="">— chọn —</option>
              {(refData[f.refPrefix ?? ""] ?? []).map((o) => (
                <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>
              ))}
            </select>
          </div>
        ) : f.type === "ref-search" ? (
          <RefSearchField
            value={form[f.key] == null || form[f.key] === "" ? null : Number(form[f.key])}
            options={refData[f.refPrefix ?? ""] ?? []}
            placeholder={hint ?? "Gõ mã / tên để tìm…"}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "ref-search-ma" ? (
          <RefSearchField
            value={form[f.key] == null || form[f.key] === "" ? null : String(form[f.key])}
            options={refData[f.refPrefix ?? ""] ?? []}
            placeholder={hint ?? "Gõ mã / tên để tìm…"}
            byMa
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "ref-multi" ? (
          <RefMultiField
            value={Array.isArray(form[f.key]) ? (form[f.key] as number[]) : []}
            options={refData[f.refPrefix ?? ""] ?? []}
            onChange={(v) => set(f.key, v)}
          />
        ) : f.type === "formula" ? (
          <FormulaField value={String(form[f.key] ?? "")} onChange={(v) => set(f.key, v)}
            configPrefix={config.prefix}
            // Ô tự khai loại (vd "Công thức tính lượng" ở Vật tư/Giấy) thì ÉP bộ chip theo nó —
            // một màn có thể có hai ô công thức hỏi hai câu khác nhau.
            loaiO={f.loaiO}
            id={`formula-${f.key}`}
            // Màn Đơn vị: ô này ra LƯỢNG, không ra tiền — nhãn phải nói đúng, không thì người khai
            // tưởng đang gõ công thức giá rồi nhét đơn giá vào.
            {...(config.prefix.includes("don-vi")
              ? { nhanO: "Cách đo của đơn vị này",
                  goY: "vd: dai_in * rong_in * to_sau_in  (một m² tờ in đo thế nào)" }
              : {})} />
        ) : f.type === "checkbox" ? (
          <label className="rc-switch">
            <input type="checkbox" checked={!!form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />
            <span className="rc-switch__slider" />
            <span className="rc-switch__label">{form[f.key] ? "Có" : "Không"}</span>
          </label>
        ) : f.type === "date" ? (
          <div className="rc-input-wrapper">
            <input className="rc-input" type="date"
              value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
          </div>
        ) : f.key === "ghi_chu" || f.key === "ghi_chu_2" || f.key === "mo_ta" ? (
          <div className="rc-input-wrapper">
            <textarea className="rc-textarea" rows={2} value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} placeholder="Nhập ghi chú hoặc thông tin bổ sung..." />
          </div>
        ) : (
          <div className="rc-input-wrapper">
            <input className={`rc-input${f.type === "number" ? " rc-input--num" : ""}`}
              type={f.type === "number" ? "number" : "text"} step="any" inputMode={f.type === "number" ? "decimal" : undefined}
              value={String(form[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} />
            {suffix && <span className="rc-input-suffix">{suffix}</span>}
          </div>
        )}
        {hint && !(f.type === "ref-search" || f.type === "ref-search-ma") && <span className="rc-field__hint">{hint}</span>}
      </Tag>
    );
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!token || isMaDuplicate) return;
    setSaving(true); setErr(null);
    const body: Record<string, unknown> = { ten: form.ten };
    if (!config.autoCode || isEdit) body.ma = form.ma;
    for (const f of visibleFields) {
      let v = form[f.key];
      if (f.type === "ref-multi" || f.type === "nhom_may-multi" || f.type === "bands" || f.type === "size_tiers" || f.type === "dau-viec-dinh-muc") { body[f.key] = Array.isArray(v) ? v : []; continue; }
      if (v === "" || v === undefined) {
        const kieuChu = !f.type || f.type === "text" || f.type === "date" || f.type === "nhom_may";
        const voonCoGiaTri = isEdit && existing != null && existing[f.key] != null
          && existing[f.key] !== "";
        if (!f.required && !(kieuChu && voonCoGiaTri)) continue;
      }
      if ((f.type === "number" || f.type === "ref" || f.type === "ref-search") && v !== "" && v != null) v = Number(v);
      if (f.type === "json" && typeof v === "string" && v.trim()) {
        try { v = JSON.parse(v); } catch { setErr(`${f.label}: JSON không hợp lệ.`); setSaving(false); return; }
      }
      if (f.jsonKey) {
        const box = (body[f.jsonKey] as Record<string, unknown>) ??
          { ...((existing?.[f.jsonKey] as Record<string, unknown>) ?? {}) };
        box[f.key] = v;
        body[f.jsonKey] = box;
        continue;
      }
      body[f.key] = v;
    }
    try {
      // transformSubmit nằm TRONG try: nó ném thì trước đây thoát khỏi hàm async mà cờ `saving`
      // vẫn bật ⇒ nút quay mãi, không một chữ báo lỗi.
      const finalBody = config.transformSubmit ? config.transformSubmit(body, form, existing) : body;
      const moi = isEdit && existing
        ? await api.update(token, existing.id, finalBody)
        : await api.create(token, finalBody);
      onSaved(moi);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Lưu thất bại.");
    } finally {
      // Lưu xong drawer KHÔNG chắc đóng: `config.moLaiSauKhiTao` (màn Đơn vị) giữ nó lại để khai
      // quy đổi ngay. Tắt cờ ở nhánh lỗi thôi là tạo xong nút kẹt vĩnh viễn ở trạng thái quay.
      setSaving(false);
    }
  }

  const typedMa = String(form.ma ?? "").trim().toUpperCase();
  const maTre = useTre(typedMa, 400);
  // Cảnh báo trùng mã: HỎI MÁY CHỦ (bảng chỉ còn 20 dòng nên không tự biết được). Một request
  // nhẹ sau khi gõ xong, lọc sẵn theo chính chuỗi vừa gõ. Đây chỉ là cảnh báo SỚM — chốt chặn
  // thật vẫn là ràng buộc trùng mã ở backend, nên sót một ca hiếm cũng không lọt vào DB.
  const [isMaDuplicate, setMaTrung] = useState(false);
  useEffect(() => {
    if (isEdit || !maTre || !token) { setMaTrung(false); return; }
    let huy = false;
    api.list(token, { q: maTre, size: 50 })
      .then((r) => {
        if (!huy) setMaTrung(r.items.some((x) => String(x.ma).trim().toUpperCase() === maTre));
      })
      .catch(() => { if (!huy) setMaTrung(false); });
    return () => { huy = true; };
  }, [isEdit, maTre, token, api]);

  const hasFormulaField = useMemo(
    () => visibleFields.some((f) => f.type === "formula") || config.renderExtra != null,
    [visibleFields, config.renderExtra]
  );
  // Nhật ký chỉ có nghĩa với bản ghi ĐÃ LƯU — đang thêm mới thì chưa có gì để xem.
  const coNhatKy = isEdit && !!config.nhatKyLoai && !!existing?.id;

  /** Tab khai báo có field THẬT ĐỂ HIỆN. Nhóm nào không được tab nào nhận thì dồn vào tab đầu —
   *  quên khai một nhóm trong config thì nó vẫn hiện chứ không biến mất im lặng. Tab rỗng (vd
   *  máy Bế không có nhóm "Khổ kẽm & Vùng in") bị bỏ hẳn, không bày ra rồi mở ra trắng trơn. */
  const tabsKhai = useMemo(() => {
    if (!config.tabsKhai?.length) return null;
    const daKhai = new Set(config.tabsKhai.flatMap((t) => t.groups));
    const conLai = [...new Set(visibleFields.map((f) => f.group || "Thông tin khác"))]
      .filter((g) => !daKhai.has(g));
    const coField = (groups: string[]) =>
      visibleFields.some((f) => f.type !== "formula" && groups.includes(f.group || "Thông tin khác"));
    return config.tabsKhai
      .map((t, i) => ({ ...t, groups: i === 0 ? [...t.groups, ...conLai] : t.groups, laDau: i === 0 }))
      .filter((t) => t.laDau || coField(t.groups));
  }, [config.tabsKhai, visibleFields]);

  // Tab đang chọn có thể vừa bị ẩn (đổi nhóm máy làm cả nhóm field biến mất) → rơi về tab đầu.
  const tabKhaiHienTai = tabsKhai
    ? (tabsKhai.find((t) => t.id === formulaTab) ?? tabsKhai[0])
    : null;
  const dangOTabKhai = !tabsKhai
    ? formulaTab === "info"
    : formulaTab !== "formula" && formulaTab !== "nhatky";
  const coTabs = hasFormulaField || coNhatKy || (tabsKhai?.length ?? 0) > 1;

  const renderFieldsContent = (chiNhom?: string[], keoTheoMaTen = true) => {
    const fieldsToRender = visibleFields.filter((f) => f.type !== "formula")
      .filter((f) => !chiNhom || chiNhom.includes(f.group || "Thông tin khác"));
    const hasGroups = fieldsToRender.some((f) => f.group);

    const baseFields = !(config.autoCode && !isEdit) ? (
      <>
        <label className="rc-field">
          <span className="rc-field__label">Mã <em>*</em></span>
          <div className={`rc-input-wrapper${isEdit ? " rc-input-wrapper--ro" : ""}`}>
            <input className="rc-input rc-mono" value={String(form.ma ?? "")}
              disabled={isEdit} onChange={(e) => set("ma", e.target.value.toUpperCase())} required placeholder="Mã..." />
          </div>
          {!isEdit && typedMa && (
            <span style={{ fontSize: "11px", fontWeight: "600", marginTop: "1px", color: isMaDuplicate ? "var(--signal, #8a1f1f)" : "var(--moss, #2f5d3a)" }}>
              {isMaDuplicate ? "Mã đã tồn tại!" : "Mã hợp lệ!"}
            </span>
          )}
        </label>
        <label className="rc-field">
          <span className="rc-field__label">Tên <em>*</em></span>
          <div className="rc-input-wrapper">
            <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
          </div>
        </label>
      </>
    ) : (
      <label className="rc-field rc-field--full">
        <span className="rc-field__label">Tên <em>*</em></span>
        <div className="rc-input-wrapper">
          <input className="rc-input" value={String(form.ten ?? "")} onChange={(e) => set("ten", e.target.value)} required />
        </div>
      </label>
    );

    if (!hasGroups) {
      return (
        <section className="rc-card-section" style={{ padding: "16px 20px" }}>
          <div className="rc-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: "12px 16px" }}>
            {keoTheoMaTen && baseFields}
            {fieldsToRender.map(renderField)}
          </div>
        </section>
      );
    }

    const sectionsMap = new Map<string, FieldDef[]>();
    fieldsToRender.forEach((f) => {
      const gName = f.group || "Thông tin khác";
      if (!sectionsMap.has(gName)) sectionsMap.set(gName, []);
      sectionsMap.get(gName)!.push(f);
    });

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {Array.from(sectionsMap.entries()).map(([gName, fields], idx) => {
          const isFirst = idx === 0;
          const colCount = gName === "Thông số chừa lề tờ in" && fields.length === 3 ? 3 : 2;
          return (
            <section className="rc-card-section" style={{ padding: "16px 20px" }} key={gName}>
              <div className="rc-card-section__title">{gName}</div>
              <div className="rc-grid" style={{ gridTemplateColumns: `repeat(${colCount}, 1fr)`, gap: "12px 16px" }}>
                {keoTheoMaTen && isFirst && baseFields}
                {fields.map(renderField)}
              </div>
            </section>
          );
        })}
      </div>
    );
  };

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className={`rc-drawer${hasFormulaField ? " rc-drawer--formula" : ""}`} onClick={(e) => e.stopPropagation()}>
        <header className="rc-drawer__head">
          <div>
            <div className="rc-drawer__kicker">{isEdit ? "Chỉnh sửa" : "Thêm mới"}</div>
            <h2 className="rc-drawer__title">{isEdit ? String(existing?.ten) : config.title}</h2>
          </div>
          <button type="button" className="rc-drawer__x" onClick={onClose} aria-label="Đóng">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <form className="rc-drawer__body" onSubmit={submit}>
          {err && <div className="banner banner--error" style={{ marginBottom: "var(--sp-4)" }}>{err}</div>}
          
          {coTabs ? (
            <div>
              <div className="rc-drawer__tabs" style={{ marginBottom: "var(--sp-4)" }}>
                {tabsKhai ? tabsKhai.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`rc-drawer__tab${tabKhaiHienTai?.id === t.id && dangOTabKhai ? " is-active" : ""}`}
                    onClick={() => setFormulaTab(t.id)}
                  >
                    {t.label}
                  </button>
                )) : (
                  <button
                    type="button"
                    className={`rc-drawer__tab${formulaTab === "info" ? " is-active" : ""}`}
                    onClick={() => setFormulaTab("info")}
                  >
                    Khai báo thông tin
                  </button>
                )}
                {hasFormulaField && (
                  <button
                    type="button"
                    className={`rc-drawer__tab${formulaTab === "formula" ? " is-active" : ""}`}
                    onClick={() => setFormulaTab("formula")}
                  >
                    {config.renderExtra ? "Công thức quy đổi" : "Công thức tính giá"}
                  </button>
                )}
                {coNhatKy && (
                  <button
                    type="button"
                    className={`rc-drawer__tab${formulaTab === "nhatky" ? " is-active" : ""}`}
                    onClick={() => setFormulaTab("nhatky")}
                  >
                    Nhật ký
                  </button>
                )}
              </div>

              {dangOTabKhai && (tabKhaiHienTai
                ? renderFieldsContent(tabKhaiHienTai.groups, tabKhaiHienTai.laDau)
                : renderFieldsContent())}
              {formulaTab === "formula" && (
                <div>
                  {visibleFields
                    .filter((f) => f.type === "formula")
                    .map(renderField)}
                  {config.renderExtra?.(form, existing)}
                </div>
              )}
              {formulaTab === "nhatky" && coNhatKy && (
                <NhatKyTab loai={config.nhatKyLoai!} id={Number(existing!.id)} />
              )}
            </div>
          ) : (
            renderFieldsContent()
          )}
        </form>

        <footer className="rc-drawer__foot">
          <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
          <Button type="button" variant="primary" loading={saving} disabled={isMaDuplicate || (!isEdit && !config.autoCode && !typedMa)} onClick={() => submit(new Event("submit") as unknown as FormEvent)}>
            {isEdit ? "Lưu thay đổi" : "Tạo mới"}
          </Button>
        </footer>
      </aside>
    </div>
  );
}

// ── TAB NHẬT KÝ ──────────────────────────────────────────────────────────────────
/** Ai đổi gì, lúc nào — cho MỘT bản ghi danh mục. Mỗi lần bấm Lưu là MỘT mục, các trường đổi
 *  nằm bên trong mục đó (backend nối bằng " · ") chứ không tách thành nhiều mục rời. */
const NK_NHAN: Record<string, string> = {
  dm_tao: "Tạo mới",
  dm_sua: "Cập nhật",
  dm_xoa: "Xoá",
};

/** "13:44 05/08/2026", riêng trong 48h gần nhất thì thay ngày bằng hôm nay/hôm qua — ba tháng
 *  sau mở lại "3 ngày trước" thì vô nghĩa, nên tuyệt đối vẫn là mặc định. */
function nhanThoiGian(iso: string): string {
  const d = new Date(iso);
  const gio = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
  const ngay0 = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const homNay = new Date();
  const moc = new Date(homNay.getFullYear(), homNay.getMonth(), homNay.getDate()).getTime();
  const lech = Math.round((moc - ngay0) / 86400000);
  if (lech === 0) return `${gio} hôm nay`;
  if (lech === 1) return `${gio} hôm qua`;
  return `${gio} ${d.toLocaleDateString("vi-VN")}`;
}

const NK_FIELD_LABELS: Record<string, string> = {
  fields_theo_loai: "Thông số theo loại máy",
  machine_group: "Nhóm máy",
  machine_type: "Loại máy",
  process_type: "Công đoạn máy",
  status: "Trạng thái",
  note: "Ghi chú",
  code: "Mã",
  name: "Tên",
  max_width_cm: "Khổ rộng tối đa",
  max_height_cm: "Khổ dài tối đa",
  min_width_cm: "Khổ rộng tối thiểu",
  min_height_cm: "Khổ dài tối thiểu",
  speed: "Tốc độ",
  setup_time_mins: "Thời gian chuẩn bị (phút)",
  changeover_time_mins: "Thời gian chuyển đổi (phút)",
  setup_waste_sheets: "Tờ bù hao chuẩn bị",
  supported_materials: "Vật liệu hỗ trợ",
  num_ink_units: "Số đơn vị in",
  supports_perfecting: "In 2 mặt cùng lúc",
};

const NK_SUB_LABELS: Record<string, string> = {
  chuan_bi_khoan: "Chuẩn bị khoan",
  so_luong_dao: "Số lượng dao",
  duong_kinh: "Đường kính",
  khoan_lo: "Khoan lỗ",
  can_mang: "Cán màng",
  be_noi: "Bế nổi",
  ep_kim: "Ép kim",
};

function formatNkVal(valStr: string): string {
  let s = valStr.trim();
  if (s === "{}" || s === "dict()") return "Trống";

  if (s.includes("{") && s.includes("}")) {
    try {
      const jsonStr = s
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null');
      const parsed = JSON.parse(jsonStr);
      if (typeof parsed === "object" && parsed !== null) {
        const keys = Object.keys(parsed);
        if (keys.length === 0) return "Trống";
        const items: string[] = [];
        for (const [k, v] of Object.entries(parsed)) {
          const kLbl = NK_SUB_LABELS[k] || k.replace(/_/g, " ");
          let vLbl = "";
          if (Array.isArray(v)) {
            vLbl = v.length > 0 ? v.join(", ") : "Chưa thiết lập";
          } else if (v === null || v === "") {
            vLbl = "Trống";
          } else if (typeof v === "boolean") {
            vLbl = v ? "Có" : "Không";
          } else {
            vLbl = String(v);
          }
          items.push(`${kLbl}: ${vLbl}`);
        }
        return items.join("; ");
      }
    } catch {
      s = s.replace(/'([^']+)':\s*\[\]/g, (_, k) => `${NK_SUB_LABELS[k] || k}: Chưa thiết lập`);
      s = s.replace(/'([^']+)':\s*'([^']*)'/g, (_, k, v) => `${NK_SUB_LABELS[k] || k}: ${v || "Trống"}`);
      s = s.replace(/'([^']+)':\s*(\d+)/g, (_, k, v) => `${NK_SUB_LABELS[k] || k}: ${v}`);
      s = s.replace(/'([^']+)':\s*(True|False)/g, (_, k, v) => `${NK_SUB_LABELS[k] || k}: ${v === "True" ? "Có" : "Không"}`);
      s = s.replace(/[{}]/g, "");
    }
  }
  return s;
}

function formatNkLine(item: string): { left: string; right?: string } {
  const parts = item.split(" → ");
  if (parts.length === 2) {
    let [left, right] = parts;
    for (const [key, label] of Object.entries(NK_FIELD_LABELS)) {
      if (left.startsWith(key + " ")) {
        left = label + ": " + left.slice(key.length + 1);
      } else if (left === key) {
        left = label;
      }
    }
    left = formatNkVal(left);
    right = formatNkVal(right);
    return { left, right };
  }

  let s = item;
  for (const [key, label] of Object.entries(NK_FIELD_LABELS)) {
    if (s.startsWith(key + " ")) {
      s = label + ": " + s.slice(key.length + 1);
    } else if (s === key) {
      s = label;
    }
  }
  s = formatNkVal(s);
  return { left: s };
}

function NhatKyChangeItem({ item }: { item: string }) {
  const isTien = /đ\/|Đơn giá/.test(item);
  const { left, right } = formatNkLine(item);
  if (right !== undefined) {
    return (
      <li className={`rc-nk__change-row${isTien ? " is-tien" : ""}`}>
        <span className="rc-nk__change-left">{left}</span>
        <span className="rc-nk__arrow" aria-hidden="true">→</span>
        <span className="rc-nk__change-right">{right}</span>
      </li>
    );
  }
  return <li className={`rc-nk__change-row${isTien ? " is-tien" : ""}`}>{left}</li>;
}

function NhatKyTab({ loai, id }: { loai: string; id: number }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<NhatKyItem[] | null>(null);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    let huy = false;
    setRows(null);
    setLoi(null);
    nhatKyDanhMuc(token!, loai, id)
      .then((r) => { if (!huy) setRows(r.items); })
      .catch((e) => { if (!huy) setLoi(e instanceof ApiError ? e.message : "Không tải được nhật ký."); });
    return () => { huy = true; };
  }, [token, loai, id]);

  if (loi) return <div className="banner banner--error">{loi}</div>;
  if (rows === null) return <div className="rc-nk__empty">Đang tải nhật ký…</div>;
  if (rows.length === 0) {
    return (
      <div className="rc-nk__empty">
        Chưa có thay đổi nào được ghi. Nhật ký bắt đầu từ lần sửa tiếp theo.
      </div>
    );
  }

  return (
    <ol className="rc-nk">
      {rows.map((r, i) => {
        const dong = r.detail ? r.detail.split(" · ").filter(Boolean) : [];
        const laTao = r.action === "dm_tao";
        const laXoa = r.action === "dm_xoa";
        return (
          <li key={i} className={`rc-nk__item${laTao ? " is-tao" : laXoa ? " is-xoa" : " is-sua"}`}>
            <span className="rc-nk__dot" aria-hidden="true">
              {laTao ? "+" : laXoa ? "×" : "✎"}
            </span>
            <div className="rc-nk__body">
              <div className="rc-nk__head">
                <span className={`rc-nk__badge rc-nk__badge--${r.action}`}>{NK_NHAN[r.action] ?? r.action}</span>
                <span className="rc-nk__who">{r.actor_name ?? "—"}</span>
                <time className="rc-nk__at" dateTime={r.at}>{nhanThoiGian(r.at)}</time>
              </div>
              {/* Tạo mới / Xoá: detail chỉ là tên bản ghi → đã có ở tiêu đề drawer, không lặp lại. */}
              {r.action === "dm_sua" && dong.length > 0 && (
                <ul className="rc-nk__changes">
                  {dong.map((d, k) => (
                    <NhatKyChangeItem key={k} item={d} />
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ── TIMELINE MULTI-PICKER ────────────────────────────────────────────────────────
/** Multi-select nhóm máy → lưu mảng TÊN (khớp `may_thiet_bi.loai_may`). Khác `RefMultiField` (lưu
 *  id) và `NhomMayField` (single). Dùng cho `cong_doan.nhom_may_cho_phep` — chặn gán máy sai loại. */
function NhomMayMultiField({ value, options, onChange }: {
  value: string[]; options: Row[]; onChange: (v: string[]) => void;
}) {
  const chon = Array.isArray(value) ? value : [];
  const toggle = (ten: string) =>
    onChange(chon.includes(ten) ? chon.filter((t) => t !== ten) : [...chon, ten]);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {options.length === 0 ? (
        <div className="rc-timeline__empty">Chưa có nhóm máy nào trong danh mục.</div>
      ) : (
        options.map((o) => {
          const ten = String(o.ten);
          const on = chon.includes(ten);
          return (
            <label
              key={o.id}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 10px", borderRadius: 999, cursor: "pointer",
                border: `1px solid ${on ? "#2563eb" : "var(--rule-hair, #e2e8f0)"}`,
                background: on ? "#eff6ff" : "var(--paper, #fff)",
                color: on ? "#1d4ed8" : "var(--ink-soft, #475569)",
                fontSize: 12, fontWeight: 600,
              }}
            >
              <input type="checkbox" checked={on} onChange={() => toggle(ten)} />
              {ten}
            </label>
          );
        })
      )}
      <div style={{ flexBasis: "100%", fontSize: 11, color: "var(--ink-soft, #64748b)" }}>
        Bỏ trống = mọi máy (không ràng buộc). Chọn nhóm nào thì chỉ máy nhóm đó được gán cho công đoạn này ở bài ghép.
      </div>
    </div>
  );
}

// `CaLamField` (ô "Ca làm việc của máy này") ĐÃ XOÁ 2026-08-10 — máy chạy liên tục, ca chỉ khai ở
// Nhân sự → Ca kíp. Nếu cần lại một ô chọn nhiều mục dạng chip thì viết mới, đừng dựng lại ô ca.


function RefMultiField({ value, options, onChange }: {
  value: number[]; options: Row[]; onChange: (v: number[]) => void;
}) {
  const byId = (id: number) => options.find((o) => o.id === id);
  const move = (i: number, d: number) => {
    const a = [...value]; const j = i + d;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]]; onChange(a);
  };
  const remaining = options.filter((o) => !value.includes(o.id));
  
  return (
    <div className="rc-rt">
      {value.length === 0 ? (
        <div className="rc-timeline__empty">Chưa chọn công đoạn nào. Hãy thêm ở dưới.</div>
      ) : (
        <div className="rc-timeline">
          {value.map((id, i) => {
            const r = byId(id);
            return (
              <div className="rc-timeline__node" key={id}>
                <div className="rc-timeline__line" />
                <div className="rc-timeline__marker">{i + 1}</div>
                <div className="rc-timeline__content">
                  <span className="rc-timeline__name">{r ? `${r.ma} · ${r.ten}` : `#${id} (đã xóa)`}</span>
                  <div className="rc-timeline__actions">
                    <button type="button" className="rc-timeline__btn" onClick={() => move(i, -1)} disabled={i === 0} title="Di chuyển lên">
                      <ArrowUpIcon />
                    </button>
                    <button type="button" className="rc-timeline__btn" onClick={() => move(i, 1)} disabled={i === value.length - 1} title="Di chuyển xuống">
                      <ArrowDownIcon />
                    </button>
                    <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" onClick={() => onChange(value.filter((_, k) => k !== i))} title="Bỏ chọn">
                      <TrashIcon />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div className="rc-input-wrapper rc-rt__add">
        <select className="rc-input" value=""
          onChange={(e) => { if (e.target.value) onChange([...value, Number(e.target.value)]); }}>
          <option value="">+ Thêm công đoạn tiếp theo…</option>
          {remaining.map((o) => <option key={o.id} value={o.id}>{o.ma} · {o.ten}</option>)}
        </select>
      </div>
    </div>
  );
}

// Ô tìm-chọn 1 danh mục theo MÃ (typeahead, bỏ dấu vẫn khớp) — vd chọn bù hao cho công đoạn.
function RefSearchField({ value, options, placeholder, byMa, onChange }: {
  value: number | string | null; options: Row[]; placeholder?: string;
  /** Lưu MÃ (chuỗi) thay vì id — cho cột trỏ danh mục bằng mã, vd `don_vi_gia`. */
  byMa?: boolean;
  onChange: (v: number | string | null) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const norm = (s: string) =>
    s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
  const rong = value == null || value === "";
  const selected = rong ? null : options.find(
    (o) => (byMa ? String(o.ma ?? "").toLowerCase() === String(value).toLowerCase() : o.id === value)
  ) ?? null;
  const nq = norm(q.trim());
  const matches = (nq
    ? options.filter((o) => norm(`${o.ma} ${o.ten}`).includes(nq))
    : options
  ).slice(0, 20);

  // Có giá trị nhưng KHÔNG khớp danh mục (đơn vị đã ngừng dùng / mã cũ). Hiện nguyên mã + báo đỏ:
  // để ô trắng như chưa chọn thì người dùng tưởng trống, bấm Lưu và giá trị hỏng vẫn nằm nguyên đó.
  if (!rong && !selected) {
    return (
      <div className="rc-input-wrapper" style={{ display: "flex", gap: "6px", alignItems: "stretch" }}>
        <span className="rc-input" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--danger, #b3261e)" }}>
          <span><b style={{ fontFamily: "var(--ff-num)" }}>{String(value)}</b> · không có trong danh mục</span>
          <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" title="Bỏ chọn — tìm lại"
            onClick={() => { onChange(null); setQ(""); setOpen(true); }}>✕</button>
        </span>
      </div>
    );
  }
  if (selected) {
    const displayName = selected.ten ? String(selected.ten) : String(selected.ma ?? value);
    return (
      <div className="rc-input-wrapper" style={{ display: "flex", gap: "6px", alignItems: "stretch" }}>
        <span className="rc-input" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", fontWeight: 500 }}>
          <span>{displayName}</span>
          <button type="button" className="rc-timeline__btn rc-timeline__btn--danger" title="Bỏ chọn — tìm lại"
            onClick={() => { onChange(null); setQ(""); setOpen(true); }}>✕</button>
        </span>
      </div>
    );
  }
  return (
    <div className="rc-input-wrapper" style={{ position: "relative" }}>
      <input className="rc-input" value={q} placeholder={placeholder ?? "Gõ mã / tên để tìm…"}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && matches.length > 0 && (
        <div className="rc-ref-search-panel">
          {matches.map((o) => {
            const showCode = o.ma && o.ma.toLowerCase() !== String(o.ten).toLowerCase();
            return (
              <button
                type="button"
                key={o.id}
                className="rc-ref-search-item"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { onChange(byMa ? String(o.ma) : o.id); setQ(""); setOpen(false); }}
              >
                <span className="rc-ref-search-item__name">{o.ten || o.ma}</span>
                {showCode && <span className="rc-ref-search-item__code">{o.ma}</span>}
              </button>
            );
          })}
        </div>
      )}
      {open && nq && matches.length === 0 && (
        <div className="rc-ref-search-panel" style={{ padding: "10px 12px", color: "var(--ash, #64748b)", fontSize: "12.5px" }}>
          Không thấy mã/tên khớp “{q}”.
        </div>
      )}
    </div>
  );
}

export type BienCongThuc = {
  ma: string;
  nhan: string;
  mo_ta: string;
  don_vi: string;
  nguon: string;
  loai: string[];
};

let _bienCache: BienCongThuc[] | null = null;
let _bienChoDoi: Promise<BienCongThuc[]> | null = null;

export function useBienCongThuc(): BienCongThuc[] {
  const { token } = useAuth();
  const [bien, setBien] = useState<BienCongThuc[]>(_bienCache ?? []);
  useEffect(() => {
    if (!token || _bienCache) return;
    const cho = (_bienChoDoi ??= authed<{ items: BienCongThuc[] }>("/api/bien-cong-thuc", token)
      .then((r) => (_bienCache = r.items))
      .catch((): BienCongThuc[] => []));
    let song = true;
    cho.then((ds) => { if (song) setBien(ds); });
    return () => { song = false; };
  }, [token]);
  return bien;
}

export type TraBien = (ma: string) => BienCongThuc | undefined;

export function traBien(ds: BienCongThuc[]): TraBien {
  const theoMa = new Map(ds.map((b) => [b.ma, b]));
  return (ma) => theoMa.get(ma);
}

const MATH_FUNCS = ["ceil", "floor", "round", "max", "min"];


function renderFormulaChips({
  value,
  tra,
  validVars,
  whitelist,
  onRemoveToken,
}: {
  value: string;
  tra: (ma: string) => BienCongThuc | undefined;
  validVars: string[] | null;
  whitelist: string[];
  onRemoveToken?: (index: number) => void;
}) {
  const tokenRegex = /[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[\+\-\*\/\(\)\,]|[\s]+/g;
  const matches = value.match(tokenRegex) || [];

  return matches.map((m, idx) => {
    if (/^\s+$/.test(m)) {
      return <span key={idx} className="rc-formula__chip-space">{m}</span>;
    }

    const trimmed = m.trim();
    const info = tra(trimmed);
    const isValidVar = validVars ? validVars.includes(trimmed) : (whitelist.includes(trimmed) || !!info);

    if (isValidVar || info) {
      return (
        <span
          key={idx}
          className="rc-formula__chip-token rc-formula__chip-token--var"
          title={info ? `${info.nhan} (Mã: ${trimmed})\nĐơn vị: ${info.don_vi}\nNguồn: ${info.nguon}` : `Mã: ${trimmed}`}
        >
          <span className="rc-formula__chip-token-label">{info?.nhan ?? trimmed}</span>
          {onRemoveToken && (
            <button
              type="button"
              className="rc-formula__chip-token-del"
              onClick={(e) => {
                e.stopPropagation();
                onRemoveToken(idx);
              }}
              title={`Xoá biến ${info?.nhan ?? trimmed}`}
            >
              ×
            </button>
          )}
        </span>
      );
    }

    if (MATH_FUNCS.includes(trimmed)) {
      return (
        <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--func">
          {trimmed}
        </span>
      );
    }

    if (/^\d+(?:\.\d+)?$/.test(trimmed)) {
      return (
        <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--num">
          {trimmed}
        </span>
      );
    }

    if (/^[\+\-\*\/\(\)\,]$/.test(trimmed)) {
      const displayOp = trimmed === "*" ? "×" : trimmed === "/" ? "÷" : trimmed === "-" ? "−" : trimmed;
      return (
        <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--op">
          {displayOp}
        </span>
      );
    }

    return (
      <span key={idx} className="rc-formula__chip-token rc-formula__chip-token--error" title={`Biến "${trimmed}" chưa hỗ trợ hoặc gõ sai`}>
        {trimmed}
      </span>
    );
  });
}

export function FormulaField({
  value,
  onChange,
  configPrefix,
  bienGoiY,
  loaiO: loaiOEp,
  nhanO = "Công thức tính giá",
  goY = "Nhập công thức tính giá (vd: dai_tp * rong_tp * don_gia)...",
  id = "formula-textarea",
}: {
  value: string;
  onChange: (v: string) => void;
  configPrefix: string;
  bienGoiY?: string[];
  loaiO?: string;
  nhanO?: React.ReactNode;
  goY?: string;
  id?: string;
}) {
  const isCd = configPrefix.includes("cong-doan");
  const isGiay = configPrefix.endsWith("/giay");
  const isDonVi = configPrefix.includes("don-vi");
  const loaiO = loaiOEp ?? (isDonVi ? "quy_doi" : isCd ? "cong_doan" : isGiay ? "giay" : "vat_tu");
  const tuDien = useBienCongThuc();
  const tra = useMemo(() => traBien(tuDien), [tuDien]);
  const whitelist = useMemo(
    () => bienGoiY ?? tuDien.filter((b) => b.loai.includes(loaiO)).map((b) => b.ma),
    [bienGoiY, tuDien, loaiO],
  );
  const validVars = useMemo(
    () => (whitelist.length ? [...whitelist] : null),
    [whitelist],
  );

  const [showSyntax, setShowSyntax] = useState(false);
  const syntaxBtnRef = useRef<HTMLButtonElement>(null);
  const syntaxPopRef = useRef<HTMLDivElement>(null);

  const [typedWord, setTypedWord] = useState("");
  const [showAuto, setShowAuto] = useState(false);
  const [autoIdx, setAutoIdx] = useState(0);

  const autoSuggestions = useMemo(() => {
    if (!typedWord || typedWord.length < 1) return [];
    const q = typedWord.toLowerCase();
    return whitelist.filter((v) => {
      const info = tra(v);
      return v.toLowerCase().includes(q) || (info && info.nhan.toLowerCase().includes(q));
    }).slice(0, 8);
  }, [typedWord, whitelist, tra]);

  useEffect(() => {
    if (!showSyntax) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (syntaxPopRef.current?.contains(t) || syntaxBtnRef.current?.contains(t)) return;
      setShowSyntax(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setShowSyntax(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [showSyntax]);

  const commitTypedWord = (textToCommit?: string) => {
    const word = (textToCommit !== undefined ? textToCommit : typedWord).trim();
    if (word) {
      onChange((value ? value.trimEnd() + " " : "") + word + " ");
      setTypedWord("");
      setShowAuto(false);
    }
  };

  const oInline = () => document.getElementById(id) as HTMLInputElement | null;

  /** Chèn toán tử / hàm / chip biến vào công thức đã chốt.
   *  Chữ đang gõ dở phải CHỐT TRƯỚC: bấm "×" giữa chừng mà mất chữ vừa gõ thì người khai không
   *  hiểu vì sao. Hàm và mở ngoặc dính liền tham số ("max(" → "max(dai_in"), còn lại tách bằng
   *  khoảng trắng cho tokenizer cắt đúng. */
  const insertVar = (text: string) => {
    const them = text.trim();
    if (!them) return;
    const dangGo = typedWord.trim();
    let goc = value.trimEnd();
    if (dangGo) goc = (goc ? goc + " " : "") + dangGo;
    onChange((goc ? goc + " " : "") + them + (them.endsWith("(") ? "" : " "));
    setTypedWord("");
    setShowAuto(false);
    setTimeout(() => oInline()?.focus(), 10);
  };

  /** Bấm "×" trên một chip → bỏ đúng token đó. `idx` là chỉ số trong CÙNG mảng token mà
   *  `renderFormulaChips` cắt ra từ `value`, nên phải cắt lại y hệt rồi splice. */
  const handleRemoveToken = (idx: number) => {
    const tokenRegex = /[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[\+\-\*\/\(\)\,]|[\s]+/g;
    const matches = value.match(tokenRegex) || [];
    if (idx < 0 || idx >= matches.length) return;
    matches.splice(idx, 1);
    onChange(matches.join("").replace(/\s+/g, " ").trim());
  };

  /** Rời ô → chốt nốt chữ đang gõ dở thành chip. Ô inline KHÔNG nằm trong `value`, không chốt thì
   *  gõ "1000" rồi bấm thẳng nút Lưu là số đó bay mất, im lặng. */
  const handleInlineBlur = () => {
    commitTypedWord();
    setShowAuto(false);
  };

  const handleInlineChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const text = e.target.value;

    // Nếu gõ toán tử (+ - * / ()), commit từ trước đó (nếu có) + toán tử
    const lastChar = text.slice(-1);
    if (/^[\+\-\*\/\(\)]$/.test(lastChar)) {
      const wordBefore = text.slice(0, -1).trim();
      let appended = "";
      if (wordBefore) {
        appended += wordBefore + " ";
      }
      appended += (lastChar === "*" ? " * " : lastChar === "/" ? " / " : lastChar === "-" ? " - " : lastChar === "+" ? " + " : lastChar);
      onChange((value ? value + " " : "") + appended);
      setTypedWord("");
      setShowAuto(false);
      return;
    }

    setTypedWord(text);

    // Nếu từ vừa gõ khớp chính xác 1 mã biến trong whitelist -> tự hóa Chip ngay!
    // TRỪ khi còn mã DÀI HƠN bắt đầu bằng chữ này (`so_mau` còn `so_mau_pha`): chốt sớm là người
    // ta không gõ nốt được nữa. Trường hợp đó để Enter/Tab trên gợi ý quyết định.
    const trimmed = text.trim();
    const conMaDaiHon = whitelist.some((v) => v !== trimmed && v.startsWith(trimmed));
    if (whitelist.includes(trimmed) && !conMaDaiHon) {
      onChange((value ? value + " " : "") + trimmed + " ");
      setTypedWord("");
      setShowAuto(false);
      return;
    }

    if (trimmed.length >= 1) {
      setShowAuto(true);
      setAutoIdx(0);
    } else {
      setShowAuto(false);
    }
  };

  const insertSuggestion = (varName: string) => {
    const prefix = value ? value.trimEnd() + " " : "";
    onChange(prefix + varName + " ");
    setTypedWord("");
    setShowAuto(false);
    setTimeout(() => {
      const el = document.getElementById(id) as HTMLInputElement | null;
      el?.focus();
    }, 10);
  };

  const handleInlineKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showAuto && autoSuggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setAutoIdx((i) => Math.min(i + 1, autoSuggestions.length - 1));
        return;
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setAutoIdx((i) => Math.max(i - 1, 0));
        return;
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertSuggestion(autoSuggestions[autoIdx]);
        return;
      } else if (e.key === "Escape") {
        setShowAuto(false);
        return;
      }
    }

    // Enter khi không có gợi ý nào: vẫn phải chốt chữ đang gõ (số "1000" chẳng khớp biến nào),
    // và chặn Enter lọt ra ngoài làm submit drawer.
    if (e.key === "Enter" && typedWord.trim()) {
      e.preventDefault();
      commitTypedWord();
      return;
    }

    if (e.key === "Backspace" && !typedWord) {
      const tokenRegex = /[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[\+\-\*\/\(\)\,]|[\s]+/g;
      const matches = value.match(tokenRegex) || [];
      if (matches.length > 0) {
        e.preventDefault();
        matches.pop();
        onChange(matches.join(""));
      }
    }
  };

  const groups = useMemo(() => {
    const sizeVars = ["dai_tp", "rong_tp", "dai_nguyen", "rong_nguyen", "dai_in", "rong_in",
      "dai", "rong"];
    const qtyVars = ["so_luong", "so_tp", "so_mau", "so_mat", "so_kem", "to_dau_vao", "to_sau_in",
      "to_nguyen", "so_con"];
    const priceVars = ["dinh_luong", "don_gia_giay", "don_gia_vat_tu"];
    const daXep = new Set([...sizeVars, ...qtyVars, ...priceVars]);

    return [
      {
        name: "Kích thước",
        key: "size",
        colorClass: "rc-formula__var-tag--size",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect width="20" height="8" x="2" y="8" rx="1.5"/>
            <path d="M6 16v-4M10 16v-2M14 16v-4M18 16v-2"/>
          </svg>
        ),
        vars: whitelist.filter(v => sizeVars.includes(v))
      },
      {
        name: "Số lượng & Sản lượng",
        key: "qty",
        colorClass: "rc-formula__var-tag--qty",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 22V4c0-.5.2-1 .6-1.4C5 2.2 5.5 2 6 2h12c.5 0 1 .2 1.4.6.4.4.6.9.6 1.4v18l-4-2-4 2-4-2-4 2z"/>
            <path d="M8 6h8M8 10h8M8 14h6"/>
          </svg>
        ),
        vars: whitelist.filter(v => qtyVars.includes(v))
      },
      {
        name: "Giá vốn & Đơn giá",
        key: "price",
        colorClass: "rc-formula__var-tag--price",
        icon: (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" x2="12" y1="2" y2="22"/>
            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
        ),
        vars: whitelist.filter(v => priceVars.includes(v))
      },
      {
        name: "Khác",
        key: "khac",
        colorClass: "rc-formula__var-tag--qty",
        icon: null,
        vars: whitelist.filter(v => !daXep.has(v)),
      },
    ].filter(g => g.vars.length > 0);
  }, [whitelist]);

  const { valid, error } = useMemo(() => {
    if (!value.trim()) return { valid: true, error: null };
    
    let openParen = 0;
    for (const char of value) {
      if (char === '(') openParen++;
      if (char === ')') openParen--;
      if (openParen < 0) {
        return { valid: false, error: "Đóng mở ngoặc đơn không hợp lệ" };
      }
    }
    if (openParen !== 0) {
      return { valid: false, error: "Thiếu dấu đóng hoặc mở ngoặc đơn" };
    }

    if (!validVars) return { valid: true, error: null };

    const tokenRegex = /[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[\+\-\*\/\(\)]|\s+/g;
    const tokens = value.match(tokenRegex) || [];

    for (const token of tokens) {
      const trimmed = token.trim();
      if (!trimmed) continue;

      if (
        !validVars.includes(trimmed) &&
        !MATH_FUNCS.includes(trimmed) &&
        !/^\d+(?:\.\d+)?$/.test(trimmed) &&
        !/^[\+\-\*\/\(\)]$/.test(trimmed)
      ) {
        return {
          valid: false,
          error: `Biến hoặc hàm "${trimmed}" không được hỗ trợ trong hệ thống`
        };
      }
    }

    return { valid: true, error: null };
  }, [value, validVars]);

  return (
    <div className="rc-formula">
      {/* 1. Trình soạn thảo công thức ở trên cùng */}
      <div className="rc-formula__editor-container">
        <div className="rc-formula__editor-header">
          <span className="rc-formula__editor-label">{nhanO}</span>
          <button
            ref={syntaxBtnRef}
            type="button"
            className={`rc-formula__syntax-btn${showSyntax ? " is-open" : ""}`}
            onClick={() => setShowSyntax((s) => !s)}
            aria-expanded={showSyntax}
            title="Phép tính · hàm · biến được hỗ trợ"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M6 8h.01M10 8h.01M14 8h.01M6 12h.01M10 12h.01M14 12h.01M8 16h8" />
            </svg>
            Cú pháp
          </button>
          {showSyntax && (
            <div ref={syntaxPopRef} className="rc-syntax" role="dialog" aria-label="Cú pháp công thức">
              <div className="rc-syntax__head">
                <span>Cú pháp công thức</span>
                <button type="button" className="rc-syntax__x" onClick={() => setShowSyntax(false)} aria-label="Đóng">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
                </button>
              </div>
              <div className="rc-syntax__body">
                <div className="rc-syntax__sec-title">Phép tính</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>+ - * /</code></td><td>cộng · trừ · nhân · chia</td></tr>
                  <tr><td><code>**</code></td><td>lũy thừa</td></tr>
                  <tr><td><code>( )</code></td><td>ngoặc nhóm</td></tr>
                  <tr><td><code>-x</code></td><td>dấu âm đơn</td></tr>
                  <tr><td><code>,</code></td><td>ngăn tham số hàm</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Hàm — đúng 5</div>
                <table className="rc-syntax__tbl"><tbody>
                  <tr><td><code>max(a,b)</code></td><td>lớn nhất — giá sàn</td></tr>
                  <tr><td><code>min(a,b)</code></td><td>nhỏ nhất — giá trần</td></tr>
                  <tr><td><code>round(x)</code></td><td>làm tròn</td></tr>
                  <tr><td><code>ceil(x)</code></td><td>làm tròn lên</td></tr>
                  <tr><td><code>floor(x)</code></td><td>làm tròn xuống</td></tr>
                </tbody></table>
                <div className="rc-syntax__sec-title">Biến</div>
                <p className="rc-syntax__note">Bấm chip biến ở dưới để chèn. Kích thước tính bằng <b>mét</b>.</p>
              </div>
            </div>
          )}
        </div>

        {/* Thanh chèn toán tử nhanh */}
        {/* `preventDefault` trên mousedown: giữ con trỏ trong ô inline. Không có nó thì bấm nút là
            ô blur TRƯỚC → chốt chữ đang gõ một lần, rồi `insertVar` chốt thêm lần nữa → chip đôi. */}
        <div className="rc-formula__op-toolbar" onMouseDown={(e) => e.preventDefault()}>
          <span className="rc-formula__op-label">Chèn toán tử:</span>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" + ")} title="Cộng">+</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" - ")} title="Trừ">−</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" * ")} title="Nhân">×</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(" / ")} title="Chia">÷</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("(")} title="Mở ngoặc">(</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar(")")} title="Đóng ngoặc">)</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("max(")} title="Hàm max">max</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("min(")} title="Hàm min">min</button>
          <button type="button" className="rc-formula__op-btn" onClick={() => insertVar("round(")} title="Hàm round">round</button>
        </div>

        {/* Ô công thức Chip Tiếng Việt duy nhất (Inline Chip Editor Container) */}
        <div
          className="rc-formula__single-stage"
          onClick={() => {
            const el = document.getElementById(id) as HTMLInputElement | null;
            el?.focus();
          }}
        >
          <div className="rc-formula__chips-wrap">
            {value.trim() ? (
              renderFormulaChips({ value, tra, validVars, whitelist, onRemoveToken: handleRemoveToken })
            ) : null}

            <div className="rc-formula__inline-input-box">
              <input
                id={id}
                className="rc-formula__inline-input"
                value={typedWord}
                onChange={handleInlineChange}
                onKeyDown={handleInlineKeyDown}
                onBlur={handleInlineBlur}
                autoComplete="off"
                spellCheck={false}
                placeholder={value.trim() ? "" : goY}
              />
              {showAuto && autoSuggestions.length > 0 && (
                <div
                  className="rc-formula__autocomplete"
                  role="listbox"
                  onMouseDown={(e) => e.preventDefault()}
                >
                  <div className="rc-formula__autocomplete-head">Gợi ý biến phù hợp:</div>
                  {autoSuggestions.map((v, idx) => (
                    <div
                      key={v}
                      className={`rc-formula__autocomplete-item${idx === autoIdx ? " is-selected" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        insertSuggestion(v);
                      }}
                      onMouseEnter={() => setAutoIdx(idx)}
                    >
                      <div className="rc-formula__autocomplete-main">
                        <span className="rc-formula__autocomplete-name">{tra(v)?.nhan ?? v}</span>
                        <code className="rc-formula__autocomplete-code">{v}</code>
                      </div>
                      {tra(v)?.don_vi && (
                        <span className="rc-formula__autocomplete-unit">{tra(v)!.don_vi}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {!valid && (
        <div className="rc-formula__validation">
          <div className="rc-formula__status rc-formula__status--error">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "6px" }}>
              <circle cx="12" cy="12" r="10"/>
              <path d="m15 9-6 6M9 9l6 6"/>
            </svg>
            {error}
          </div>
        </div>
      )}

      {/* 3. Danh sách biến khả dụng (Gom chung 1 nhóm) */}
      <div className="rc-formula__header-bar">
        <span className="rc-formula__header-title">Danh sách biến khả dụng</span>
      </div>

      <div className="rc-formula__all-vars" onMouseDown={(e) => e.preventDefault()}>
        {groups.flatMap((g) => g.vars.map((v) => ({ v, colorClass: g.colorClass }))).map(({ v, colorClass }) => (
          <button
            key={v}
            type="button"
            className={`rc-formula__var-tag ${colorClass}`}
            onClick={() => insertVar(v)}
            // Hover nói đủ BA thứ: ý nghĩa · đơn vị · số ở đâu ra. Thiếu đơn vị thì người khai
            // không biết `dai_in` là mét hay milimét (chỗ đẻ ra công thức lệch thang); thiếu nguồn
            // thì không biết `to_dau_vao` đã gồm bù hao chưa rồi nhân hao thêm lần nữa.
            title={tra(v)
              ? `${tra(v)!.mo_ta}\nĐơn vị: ${tra(v)!.don_vi}\nNguồn: ${tra(v)!.nguon}`
              : v}
          >
            <span className="rc-formula__var-name">{tra(v)?.nhan ?? v}</span>
            <code className="rc-formula__var-code">{v}</code>
          </button>
        ))}
      </div>
    </div>
  );
}

