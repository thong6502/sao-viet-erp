// "Nội quy công ty" — Giám đốc ban hành, MỌI nhân viên đọc (chủ 30/07/2026).
//
// BỘ NỘI QUY LÀ **NHIỀU TÀI LIỆU**: Nội quy lao động, Quy chế lương thưởng, An toàn lao động,
// Các lỗi thường gặp… Cột phải liệt kê TIÊU ĐỀ, bấm vào là mở nội dung bên trái.
//   ⇒ Ban hành, lịch sử, file đã ký, bản nháp đều RIÊNG TỪNG TÀI LIỆU. Sửa "Các lỗi thường gặp"
//     thì "Nội quy lao động" giữ nguyên ngày ban hành cũ. Đừng gộp lại thành một mốc chung.
//
// Ba trạng thái trên CÙNG một màn, đừng tách màn:
//   1. Nhân viên thường  → `GET /documents` + `GET /documents/{id}/current`. Không nút, không
//      banner, KHÔNG chữ "nháp".
//   2. Giám đốc, chế độ XEM (mặc định) → thấy bản đang hiệu lực trước, không rơi thẳng vào sửa.
//   3. Giám đốc, chế độ SỬA → badge rust + banner giải thích + thanh sticky đáy.
//
// **CHỈ TẢI FILE LÊN — KHÔNG có trình soạn thảo** (chủ chốt 30/07/2026). Đừng dựng lại TipTap.
//   • PDF  → server dựng ẢNH TỪNG TRANG ⇒ giữ nguyên 100%, kể cả bản scan có ký, đóng dấu đỏ.
//   • Word → HTML giàu định dạng qua `docx-preview` (nạp muộn, xem `noiQuyWordImport.ts`).
// Bản `source_kind='html'` vẫn HIỂN THỊ được (dữ liệu cũ soạn trong app trước 30/07) — gỡ đường
// SOẠN html không có nghĩa là gỡ đường HIỆN html.
//
// CỐ Ý KHÔNG có: nút "Đã đọc"/đếm lượt đọc (chủ đã bác), tìm trong trang, nút In, xuất ngược ra
// Word, thư viện đọc PDF phía trình duyệt, màn riêng cho lịch sử, và **nút XOÁ tài liệu** —
// backend cố ý không mở endpoint xoá (xoá kéo theo cả lịch sử + ảnh trang + file qua CASCADE).
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
} from "react";
import DOMPurify from "dompurify";
import { Upload } from "lucide-react";
import {
  ApiError,
  api,
  assetUrl,
  type NoiQuy,
  type NoiQuyAttachment,
  type NoiQuyDocument,
  type NoiQuyPage as NoiQuyPageImage,
  type NoiQuyVersionRow,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { Icon } from "../components/Icons";
import "./nhan-su.css";
import "./noi-quy.css";

/** Server cũng chặn (routers/noi_quy.py) — chốt ở FE chỉ để khỏi tải phí 20 MB rồi mới báo lỗi. */
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const FILE_ACCEPT = ".pdf,.doc,.docx,.jpg,.jpeg,.png";
/** Nội dung chính chỉ nhận .pdf và .docx — hai đường server/trình duyệt dựng lại được. */
const NOI_DUNG_ACCEPT = ".pdf,.docx";

// Dữ liệu cũ có thể là văn bản thuần (DB thật của chủ còn 4 bản `source_kind='html'`, bản dài tới
// ~46 000 ký tự). Chuyển sang HTML để màn đọc chỉ có MỘT đường render, nhưng không tự sửa chữ
// người soạn. ⚠️ Gỡ hai hàm dưới là đổi cách hiển thị đúng những bản đó.
const RE_HEADING = /^(CHƯƠNG|Chương|PHẦN|Phần|MỤC|Mục)\s+[IVXLCDM\d]+/;
const RE_ARTICLE = /^Điều\s+\d+\s*[.:]/;

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function plainTextToHtml(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((raw) => raw.replace(/^\n+|\s+$/g, ""))
    .filter(Boolean)
    .map((b) => {
      const lines = b.split("\n");
      if (RE_HEADING.test(lines[0]) && lines.length <= 2) {
        return `<h2>${escapeHtml(lines.join(" - "))}</h2>`;
      }
      const m = RE_ARTICLE.exec(b);
      if (m) {
        return `<p><strong>${escapeHtml(m[0])}</strong>${escapeHtml(b.slice(m[0].length)).replace(/\n/g, "<br>")}</p>`;
      }
      return `<p>${escapeHtml(b).replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function normalizeContent(value: string): string {
  if (!value.trim()) return "";
  return /<\/?[a-z][\s\S]*>/i.test(value) ? value : plainTextToHtml(value);
}

// Cấp tiêu đề sâu nhất mà CẢ BA tầng đều biết: bộ lọc nh3 ở server, `capHeadings` dưới đây, và
// CSS. Ba tầng này từng lệch nhau (Word tới cấp 6, server chỉ tới 4, CSS chỉ tới 3) và hậu quả là
// tiêu đề cấp 5 bị server xoá ÂM THẦM sau khi lưu.
const MAX_HEADING = 4;

// `h5`/`h6` được cho qua bộ lọc CHỈ để `capHeadings` còn thấy mà hạ cấp — sau đó không còn nữa.
const SANITIZE_OPTIONS = {
  ALLOWED_TAGS: [
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "hr", "a", "img",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    // `span`/`div` để cụm chữ đổi cỡ/đổi màu giữa câu và các khối canh lề còn chỗ đứng.
    "span", "div",
  ],
  // `style` là BẮT BUỘC: canh lề / cỡ chữ / màu chữ / font của tài liệu Word đều được
  // `docxToRichHtml` ép thành `style` nội tuyến. Thiếu nó ở đây thì bản Word vừa chuyển xong bị
  // chính FE xoá sạch định dạng trước khi kịp gửi lên server.
  // Lọc từng thuộc tính CSS ở `filterStyles`, không cho qua nguyên chuỗi.
  ALLOWED_ATTR: ["href", "title", "src", "alt", "width", "height", "colspan", "rowspan", "style"],
  // Server không giữ `data-*`; giữ ở FE chỉ tạo cảnh "xem trước khác bản đã lưu".
  ALLOW_DATA_ATTR: false,
};

// --- Mirror bộ lọc `style` của server ---------------------------------------
// Ba hằng dưới đây phải khớp ĐÚNG `_STYLE_TAGS`, `_CSS_CHO_PHEP`, `_CSS_CHAN` trong
// `backend/app/services/noi_quy_service.py`. Vì sao phải lặp lại thay vì để server lọc là xong:
// server là chốt CUỐI, nhưng nếu FE hiển thị rộng hơn server thì chủ xem trước thấy đẹp, lưu lại
// thì mất một phần định dạng mà chẳng có thông báo nào. Cho hai bên khắt khe BẰNG NHAU thì thứ
// nhìn thấy lúc xem trước đúng bằng thứ nhân viên sẽ đọc.
const STYLE_TAGS = new Set([
  "P", "DIV", "SPAN", "TD", "TH", "TABLE", "TR",
  "H1", "H2", "H3", "H4", "LI", "UL", "OL", "BLOCKQUOTE",
]);
const CSS_ALLOWED = new Set([
  "text-align", "text-indent", "text-decoration", "text-transform",
  "font-weight", "font-style", "font-size", "font-family",
  "color", "background-color", "width", "margin-left", "padding-left",
  "vertical-align", "line-height",
]);
const CSS_BLOCKED = ["url(", "expression", "@import", "javascript:", "\\", "/*", "*/"];

/** Giữ lại CHỈ các khai báo CSS trong allowlist, bỏ theo TỪNG khai báo.
 *
 *  Bỏ từng khai báo chứ không bỏ cả chuỗi: một khai báo lạ không được kéo theo những khai báo
 *  lành — mất `text-align: center` là bản nội quy lệch hết tiêu đề. */
function filterStyles(root: HTMLElement): void {
  root.querySelectorAll<HTMLElement>("[style]").forEach((el) => {
    if (!STYLE_TAGS.has(el.tagName)) {
      el.removeAttribute("style");
      return;
    }
    const keep: string[] = [];
    for (const decl of (el.getAttribute("style") ?? "").split(";")) {
      const at = decl.indexOf(":");
      if (at < 0) continue;
      const name = decl.slice(0, at).trim().toLowerCase();
      const value = decl.slice(at + 1).split(/\s+/).filter(Boolean).join(" ");
      if (!CSS_ALLOWED.has(name) || !value) continue;
      if (CSS_BLOCKED.some((bad) => value.toLowerCase().includes(bad))) continue;
      keep.push(`${name}: ${value}`);
    }
    if (keep.length) el.setAttribute("style", keep.join("; "));
    else el.removeAttribute("style");
  });
}

/** Hạ `<h5>/<h6>` xuống `<h4>` — KHÔNG để chúng tụt thành đoạn văn thường.
 *
 * Word soạn được tới Heading 6 nhưng server chỉ giữ tới `h4`. Để nguyên thì thẻ bị xoá lúc lưu và
 * tiêu đề thành chữ trơn, không báo gì. Hạ xuống `h4` thì mất ĐỘ SÂU nhưng còn giữ VAI TRÒ tiêu
 * đề — và chủ nhìn thấy ngay ở phần xem trước để tự sắp lại nếu muốn. */
function capHeadings(root: HTMLElement): void {
  root.querySelectorAll("h5, h6").forEach((cu) => {
    const moi = document.createElement(`h${MAX_HEADING}`);
    moi.innerHTML = cu.innerHTML;
    // Mang theo `style`: tiêu đề từ Word thường mang cả canh lề và cỡ chữ ở chính thẻ đó, bỏ đi
    // là vừa mất độ sâu vừa mất dáng.
    const style = cu.getAttribute("style");
    if (style) moi.setAttribute("style", style);
    cu.replaceWith(moi);
  });
}

function safeHtml(value: string): string {
  const box = document.createElement("div");
  box.innerHTML = DOMPurify.sanitize(normalizeContent(value), SANITIZE_OPTIONS);
  // Thứ tự có ý: `capHeadings` sinh ra `h4` MỚI (mang theo `style` cũ) nên phải chạy TRƯỚC
  // `filterStyles`, để những `style` vừa sao chép qua cũng bị soi bằng cùng một allowlist.
  capHeadings(box);
  filterStyles(box);
  return box.innerHTML;
}

/** HTML cho MÀN ĐỌC: làm sạch, rồi bọc mỗi `<table>` vào một khay cuộn ngang.
 *
 * Vì sao cần khay: bảng nội quy hay 4–5 cột. Ép vừa bề ngang điện thoại 375px thì chữ dồn thành
 * cột 1–2 ký tự, đọc không nổi; để tràn tự do thì CẢ TRANG cuộn ngang, mọi đoạn văn khác cũng lệch.
 * Cho bảng cuộn trong khay riêng của nó là giữ được cả hai. */
function docHtml(value: string): string {
  const box = document.createElement("div");
  box.innerHTML = safeHtml(value);
  box.querySelectorAll("table").forEach((bang) => {
    const khay = document.createElement("div");
    khay.className = "nq-scrollx";
    bang.replaceWith(khay);
    khay.appendChild(bang);
  });
  return box.innerHTML;
}

function htmlText(value: string): string {
  const box = document.createElement("div");
  box.innerHTML = safeHtml(value);
  return box.textContent ?? "";
}

// --- Ngày giờ ------------------------------------------------------------------------------
// Backend lưu UTC nhưng SQLite trả ISO KHÔNG có hậu tố Z → phải tự coi là UTC, nếu không lệch
// −7h (cùng luật với utils/format.ts:fmtDateTime). Không dùng thẳng helper chung vì màn này cần
// dd/mm/yyyy có số 0 đệm và giờ KHÔNG có giây.
function parseTs(value?: string | null): Date | null {
  if (!value) return null;
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
  const d = new Date(!hasTz && value.includes("T") ? `${value}Z` : value);
  return Number.isNaN(d.getTime()) ? null : d;
}
/** "30/07/2026" */
function fmtNgay(value?: string | null): string {
  const d = parseTs(value);
  return d
    ? d.toLocaleDateString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      })
    : "—";
}
/** "30/07/2026 14:05" */
function fmtNgayGio(value?: string | null): string {
  const d = parseTs(value);
  return d
    ? d.toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}
/** "14:05" — mốc "Đã lưu" trong phiên đang mở, luôn là giờ máy người dùng. */
function fmtGio(d: Date): string {
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

// Chép từ HoSoCuaToiPage.tsx:559 — giữ nguyên chữ tiếng Việt backend trả về ở 400/422.
function messageFor(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return "Mất kết nối. Vui lòng thử lại.";
    if (err.status >= 500) return "Có lỗi xảy ra, vui lòng thử lại sau.";
    return err.message;
  }
  if (err instanceof Error && err.message) return err.message;
  return "Đã có lỗi xảy ra. Vui lòng thử lại.";
}

/** Bản này hiện bằng ẢNH TRANG (đường PDF giữ nguyên dáng) hay bằng HTML?
 *
 *  `source_kind === 'file'` MÀ `pages` rỗng là trường hợp thật, không phải dữ liệu lỗi: đó là
 *  đường Word — nội dung là HTML giàu định dạng nằm trong `noi_dung`. Nên phải kiểm cả hai. */
function laBanAnhTrang(v: NoiQuy | null): boolean {
  return v?.source_kind === "file" && (v.pages?.length ?? 0) > 0;
}

/** File GỐC của lần tải nội dung lên — đích của nút "Tải bản PDF gốc".
 *
 *  Lọc theo cờ `is_import_source` do server phơi ra, KHÔNG suy từ tên/đường dẫn file. Server chỉ
 *  giữ ĐÚNG MỘT hàng mang cờ này (tải lại thì thay, không cộng dồn), nên không cần chọn lựa gì
 *  thêm; còn file chứng từ chủ tự bấm "Đính kèm" luôn là `false` và không bao giờ lọt vào đây. */
function timBanGoc(v: NoiQuy | null): NoiQuyAttachment | null {
  return (v?.attachments ?? []).find((a) => a.is_import_source) ?? null;
}

/** Ảnh từng trang của bản PDF — dùng CHUNG cho màn đọc và chế độ sửa. */
function PagesView({
  pages,
  banGoc,
}: {
  pages: NoiQuyPageImage[];
  banGoc: NoiQuyAttachment | null;
}) {
  return (
    <article className="nq-pages">
      <div className="nq-pages__bar">
        <span className="nq-pages__meta">
          Bản gốc {pages.length} trang · bấm vào trang để xem cỡ thật
        </span>
        {banGoc && (
          // Đường thoát chắc chắn khi ảnh không vừa mắt (chữ nhỏ, muốn in ra). `/api/files` xác
          // thực bằng COOKIE nên thẻ <a> thường là đủ, không cần Bearer.
          <a
            className="nq-pages__dl"
            href={assetUrl(banGoc.file_url) ?? "#"}
            target="_blank"
            rel="noreferrer"
            title={banGoc.file_name}
          >
            Tải bản PDF gốc
          </a>
        )}
      </div>
      {pages.map((p) => (
        <figure className="nq-page" key={p.page_no}>
          {/* Mở ảnh ở tab mới = có sẵn phóng to/kéo của trình duyệt và của điện thoại. CỐ Ý không
              tự dựng khung xem ảnh: một trang A4 co vào 375px là không đọc nổi, mà thêm thư viện
              xem ảnh vào màn CẢ CÔNG TY tải thì đắt hơn lợi. */}
          <a href={assetUrl(p.file_url) ?? "#"} target="_blank" rel="noreferrer">
            <img
              src={assetUrl(p.file_url) ?? ""}
              alt={`Nội quy công ty — trang ${p.page_no}`}
              // `lazy`: nội quy 20 trang là ~5 MB. Không tải lười thì công nhân dùng điện thoại
              // mạng yếu ngoài xưởng phải chờ hết 5 MB mới đọc được trang 1.
              loading="lazy"
              // Khai sẵn khung ảnh, nếu không trang NHẢY mỗi lần một ảnh tải xong.
              // `|| undefined` chứ không `|| 0`: `width="0"` làm ảnh co về 0 và mất hẳn.
              width={p.width || undefined}
              height={p.height || undefined}
            />
          </a>
          <figcaption className="nq-page__no">
            Trang {p.page_no}/{pages.length}
          </figcaption>
        </figure>
      ))}
    </article>
  );
}

type Mode = "view" | "edit";
type Busy =
  | null
  | "doc"      // đổi tài liệu đang mở
  | "draft"    // mở nháp
  | "save"     // lưu ghi chú
  | "publish"
  | "upload"   // đính kèm chứng từ
  | "noiDung"  // tải file nội dung lên (PDF dựng ảnh / Word chuyển đổi)
  | "del"
  | "doiTen"   // thêm / đổi tên tài liệu
  | "an";      // ẩn / hiện tài liệu
/** Hộp thoại tiêu đề tài liệu dùng CHUNG cho "Thêm" và "Đổi tên" — cùng một ô nhập, cùng một
 *  luật (không rỗng, không trùng tên). */
type TenDlg = null | { kieu: "them" } | { kieu: "doi-ten"; doc: NoiQuyDocument };

export function NoiQuyPage() {
  const { token } = useAuth();
  const can = useCan();
  const canEdit = can("noi_quy", "update");

  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  /** Cảnh báo về CHẤT LƯỢNG bản vừa nhập — hiện tới khi thoát sửa hoặc nhập lại, KHÔNG tự tắt.
   *
   *  Tách khỏi `okMsg` chứ không nhồi vào cùng một câu: nội quy gần như toàn bộ là điều khoản có
   *  số, mất số thứ tự là văn bản HỎNG mà nhìn vẫn tưởng đủ. Loại cảnh báo đó phải sống qua vài
   *  thao tác và phải nhắc lại lúc bấm Ban hành, chứ không được trôi cùng một thông báo thành
   *  công màu xanh. Vì vậy `luuGhiChu` CỐ Ý không xoá nó. */
  const [warnMsg, setWarnMsg] = useState<string | null>(null);
  const [dlgErr, setDlgErr] = useState<string | null>(null);

  /** DANH SÁCH TÀI LIỆU. Người soạn lấy từ `/documents/tat-ca` (kèm doc chưa ban hành, doc đã ẩn
   *  và cờ `co_nhap`); nhân viên lấy từ `/documents` (đã lọc sẵn). */
  const [docs, setDocs] = useState<NoiQuyDocument[]>([]);
  const [docId, setDocId] = useState<number | null>(null);
  const [current, setCurrent] = useState<NoiQuy | null>(null);
  const [draft, setDraft] = useState<NoiQuy | null>(null);
  const [versions, setVersions] = useState<NoiQuyVersionRow[]>([]);

  const [mode, setMode] = useState<Mode>("view");
  const [ghiChu, setGhiChu] = useState("");
  /** Ghi chú ĐÃ LƯU của bản nháp — mốc so dirty. */
  const [baseGhiChu, setBaseGhiChu] = useState("");
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  const [busy, setBusy] = useState<Busy>(null);
  const [askPublish, setAskPublish] = useState(false);
  /** Tài liệu người dùng muốn chuyển sang khi đang có ghi chú chưa lưu; `null` = thoát sửa hẳn. */
  const [askDiscard, setAskDiscard] = useState<false | { toi: number | null }>(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [delFile, setDelFile] = useState<NoiQuyAttachment | null>(null);
  const [tenDlg, setTenDlg] = useState<TenDlg>(null);
  const [tenMoi, setTenMoi] = useState("");
  const [askAn, setAskAn] = useState<NoiQuyDocument | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const noiDungRef = useRef<HTMLInputElement>(null);

  const isBusy = busy !== null;
  const docHienTai = useMemo(() => docs.find((d) => d.id === docId) ?? null, [docs, docId]);
  const daBanHanh = !!current?.has_content;
  const dirty = mode === "edit" && ghiChu !== baseGhiChu;

  /** Tải nội dung + lịch sử của MỘT tài liệu.
   *
   *  ⚠️ CỐ Ý KHÔNG gọi `GET /draft` ở đây. Endpoint đó TẠO hàng nháp; gọi cho từng tài liệu lúc
   *  mở màn là mọi tài liệu đều sinh nháp và cờ `co_nhap` bật hết — danh sách mất sạch ý nghĩa.
   *  Nháp chỉ mở khi người dùng thật sự bấm "Sửa". */
  const napTaiLieu = useCallback(
    async (id: number) => {
      const [cur, vs] = await Promise.all([
        api.noiQuy.docCurrent(token!, id),
        canEdit
          ? api.noiQuy.versions(token!, id)
          : Promise.resolve({ items: [] as NoiQuyVersionRow[] }),
      ]);
      setCurrent(cur);
      setVersions(vs.items);
    },
    [token, canEdit],
  );

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setLoadErr(null);
    try {
      const res = canEdit
        ? await api.noiQuy.documentsAll(token)
        : await api.noiQuy.documents(token);
      setDocs(res.items);
      // Mặc định mở tài liệu ĐẦU DANH SÁCH (server đã xếp theo `seq`).
      const dau = res.items[0]?.id ?? null;
      setDocId(dau);
      if (dau === null) {
        setCurrent(null);
        setVersions([]);
        return;
      }
      await napTaiLieu(dau);
    } catch (err) {
      // KHÔNG nuốt lỗi thành "chưa có nội quy" — nhân viên sẽ tin công ty không có nội quy.
      setLoadErr(messageFor(err));
    } finally {
      setLoading(false);
    }
  }, [token, canEdit, napTaiLieu]);

  useEffect(() => {
    void load();
  }, [load]);

  // Rời hẳn trang / F5 khi đang có ghi chú chưa lưu → trình duyệt hỏi lại.
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  // --- Hành vi -------------------------------------------------------------------------

  /** Mở nháp của tài liệu `id` và vào chế độ sửa. */
  const moNhap = useCallback(
    async (id: number) => {
      const d = await api.noiQuy.draft(token!, id);
      setDraft(d);
      setGhiChu(d.ghi_chu ?? "");
      setBaseGhiChu(d.ghi_chu ?? "");
      setSavedAt(null);
      setMode("edit");
      // `GET /draft` vừa TẠO nháp ⇒ danh sách của người soạn phải thấy cờ ngay, đừng đợi lần tải
      // lại sau mới đúng.
      setDocs((ds) => ds.map((x) => (x.id === id ? { ...x, co_nhap: true } : x)));
    },
    [token],
  );

  async function enterEdit() {
    if (!token || isBusy || docId === null) return;
    setActionErr(null);
    setOkMsg(null);
    setWarnMsg(null);
    setBusy("draft");
    try {
      await moNhap(docId);
    } catch (err) {
      setActionErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  /** Đổi tài liệu đang mở. Ở chế độ sửa thì mở luôn nháp của tài liệu mới — người dùng vừa bấm
   *  "Sửa" xong, rơi ngược về chế độ xem là mất một nhịp không hiểu vì sao. */
  async function chuyenTaiLieu(id: number) {
    if (!token) return;
    setBusy("doc");
    setActionErr(null);
    setOkMsg(null);
    setWarnMsg(null);
    setDocId(id);
    setCurrent(null);
    setDraft(null);
    setVersions([]);
    setGhiChu("");
    setBaseGhiChu("");
    setSavedAt(null);
    try {
      await napTaiLieu(id);
      if (mode === "edit") await moNhap(id);
    } catch (err) {
      setActionErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  function moTaiLieu(id: number) {
    if (!token || isBusy || id === docId) return;
    if (dirty) {
      setAskDiscard({ toi: id });
      return;
    }
    void chuyenTaiLieu(id);
  }

  /** Lưu GHI CHÚ vào nháp.
   *
   *  ⚠️ `noi_dung` gửi lại NGUYÊN VĂN của nháp và `source_kind` BỎ TRỐNG (= giữ nguyên nguồn).
   *  Gửi chuỗi rỗng là xoá trắng nội dung Word vừa nhập; gửi `'html'` là server XOÁ ảnh trang của
   *  bản PDF — mất trắng tập ảnh vừa dựng 30 giây. */
  async function luuGhiChu(): Promise<NoiQuy> {
    const res = await api.noiQuy.saveDraft(token!, docId!, {
      noi_dung: draft?.noi_dung ?? "",
      ghi_chu: ghiChu.trim() || null,
    });
    setDraft(res);
    setBaseGhiChu(ghiChu);
    setSavedAt(new Date());
    return res;
  }

  async function onSave() {
    if (!token || isBusy || docId === null) return;
    setBusy("save");
    setActionErr(null);
    setOkMsg(null);
    try {
      await luuGhiChu();
    } catch (err) {
      setActionErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  async function onPublish() {
    if (!token || isBusy || docId === null) return;
    const id = docId;
    setBusy("publish");
    setDlgErr(null);
    try {
      // ⚠️ Ghi chú chưa lưu phải lưu TRƯỚC. `POST /publish` không nhận body: không lưu thì nó ban
      // hành bản nháp CŨ và nuốt mất ghi chú vừa gõ mà không báo gì.
      if (dirty) await luuGhiChu();
      const pub = await api.noiQuy.publish(token, id);
      setCurrent(pub); // publish trả về đúng bản vừa ban hành
      // Nháp đã hoá thành bản hiệu lực. Đặt null thay vì gọi lại /draft — gọi là TẠO nháp mới.
      setDraft(null);
      setMode("view");
      setAskPublish(false);
      setGhiChu("");
      setBaseGhiChu("");
      setSavedAt(null);
      setActionErr(null);
      setWarnMsg(null); // đã ban hành = đã soát; giữ lại chỉ làm người ta tưởng bản mới cũng lỗi
      setOkMsg(
        `Đã ban hành “${pub.title ?? docHienTai?.title ?? "tài liệu"}”. ` +
        `Toàn công ty đọc được bản này từ bây giờ. Các tài liệu khác giữ nguyên ngày ban hành cũ.`,
      );
      // Dòng trong danh sách: hết nháp treo, có ngày ban hành mới.
      setDocs((ds) =>
        ds.map((x) => (x.id === id ? { ...x, co_nhap: false, published_at: pub.published_at } : x)),
      );
      try {
        setVersions((await api.noiQuy.versions(token, id)).items);
      } catch {
        /* lịch sử tải hụt không được che mất thông báo ban hành thành công */
      }
    } catch (err) {
      setDlgErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  /** "Thoát sửa" chứ KHÔNG phải "Hủy": không có API xoá nháp, "Hủy" là hứa hẹn sai. */
  function onExit() {
    if (dirty) {
      setAskDiscard({ toi: null });
      return;
    }
    leaveEdit(null);
  }
  /** `toi = null` ⇒ về chế độ xem. `toi = id` ⇒ bỏ ghi chú rồi chuyển sang tài liệu đó. */
  function leaveEdit(toi: number | null) {
    setAskDiscard(false);
    setGhiChu(baseGhiChu);
    setActionErr(null);
    setWarnMsg(null);
    if (toi === null) {
      setMode("view");
      return;
    }
    // `ghiChu` vừa đặt lại bằng `baseGhiChu` ở trên nên `dirty` đã tắt — nhưng state React chưa
    // kịp áp dụng trong lượt này, vì vậy KHÔNG gọi `moTaiLieu` (nó sẽ thấy `dirty` cũ và mở lại
    // đúng hộp thoại này). Gọi thẳng hàm làm việc.
    void chuyenTaiLieu(toi);
  }

  /** Ảnh trong THÂN tài liệu Word (logo, con dấu, chữ ký) — `docxToRichHtml` đẩy từng ảnh qua đây.
   *
   *  ⚠️ Không phải "ảnh của trình soạn thảo": màn này không còn trình soạn thảo. Bỏ bước này thì
   *  bộ lọc của server vứt mọi `<img src="blob:...">` và tài liệu mất sạch con dấu/chữ ký mà vẫn
   *  đủ chữ — hỏng ÂM THẦM. */
  async function uploadAnhTrongBai(file: File): Promise<string> {
    if (!token) throw new Error("Phiên đăng nhập không còn hiệu lực.");
    if (file.size > MAX_FILE_BYTES) {
      const err = new Error("Ảnh vượt quá 20 MB.");
      setActionErr(err.message);
      throw err;
    }
    setActionErr(null);
    try {
      return (await api.noiQuy.uploadImage(token, file)).url;
    } catch (err) {
      setActionErr(messageFor(err));
      throw err;
    }
  }

  /** Tải NỘI DUNG lên. PDF → server dựng ảnh từng trang; Word → HTML giàu định dạng ở trình duyệt. */
  async function runTaiLen(file: File) {
    if (!token || isBusy || docId === null) return;
    const id = docId;
    setPendingFile(null);
    setBusy("noiDung");
    setActionErr(null);
    setOkMsg(null);
    setWarnMsg(null); // tải lại = cảnh báo của lần trước hết hiệu lực
    try {
      if (file.name.toLowerCase().endsWith(".pdf")) {
        // Endpoint này GHI THẲNG vào nháp (xoá `noi_dung`, đặt `source_kind='file'`, tự đính file
        // gốc) ⇒ phải đồng bộ lại state theo kết quả trả về.
        const res = await api.noiQuy.banGocPdf(token, id, file);
        setDraft(res);
        // ⚠️ CHỈ dời mốc so dirty, KHÔNG đụng ô `ghiChu`. Endpoint này không ghi `ghi_chu`, nên
        // nhồi `res.ghi_chu` ngược vào ô nhập là XOÁ câu ghi chú người dùng vừa gõ mà chưa lưu.
        setBaseGhiChu(res.ghi_chu ?? "");
        setSavedAt(new Date());
        setOkMsg(
          `Đã dựng ${res.pages.length} trang từ bản gốc. Nhân viên sẽ thấy đúng bản này sau khi ` +
          `bấm “Ban hành”. Muốn sửa chữ thì sửa ở file rồi tải lên lại.`,
        );
        return;
      }

      // Word: chuyển ở TRÌNH DUYỆT (server không đọc .docx) rồi lưu như HTML giàu định dạng.
      const { docxToRichHtml } = await import("./noiQuyWordImport");
      const converted = await docxToRichHtml(file, uploadAnhTrongBai);
      const html = safeHtml(converted.html);
      if (!htmlText(html).trim() && !/<img\b/i.test(html)) {
        throw new Error("Không tìm thấy nội dung có thể nhập trong tài liệu.");
      }
      const res = await api.noiQuy.saveDraft(token, id, {
        noi_dung: html,
        ghi_chu: ghiChu.trim() || null,
        source_kind: "file",
      });
      setDraft(res);
      setBaseGhiChu(ghiChu);
      setSavedAt(new Date());
      // ⚠️ Đường này dồn HẾT thông báo vào `warnMsg`, KHÔNG dùng `okMsg`: banner cảnh báo đứng
      // trên banner thành công, nên tách ra hai chỗ là mấy câu trong `okMsg` (ảnh bị bỏ, chưa đính
      // được file gốc) không bao giờ hiện ra.
      // Cảnh báo SỐ THỨ TỰ luôn nói, mỗi lần đi đường Word — nói mạnh hơn khi dò được là tài liệu
      // THẬT SỰ dùng số tự động. Đây là chỗ nguy hiểm nhất của cả tính năng: bản nội quy mất số
      // điều khoản trông vẫn "đủ chữ", chỉ tới lúc tranh chấp mới phát hiện dẫn sai điều.
      const loiNhac = [
        "Đã lấy nội dung Word và giữ lại định dạng.",
        converted.matSoTuDong
          ? "Tài liệu này CÓ dùng số thứ tự tự động của Word (1., 2., a., b.) — phần số đó KHÔNG giữ được."
          : "Số thứ tự tự động của Word (1., 2., a., b.) KHÔNG giữ được.",
        "Hãy soát lại toàn bộ số điều khoản trước khi ban hành.",
        "Word chỉ giữ được khoảng 90% (khung text box, tab stop, ngắt trang cũng không có trong HTML).",
        ...converted.warnings,
      ];
      // Giữ file gốc để sau này đối chiếu. Đính kèm hỏng chỉ là mất bản đối chiếu — KHÔNG được
      // kéo theo nội dung đã chuyển đổi thành công, nên hạ xuống cảnh báo mềm.
      try {
        const att = await api.noiQuy.uploadAttachment(token, id, file);
        setDraft((d) => (d ? { ...d, attachments: [...d.attachments, att] } : d));
      } catch {
        loiNhac.push("Chưa đính được file Word gốc kèm theo — bấm “Đính kèm file…” nếu cần.");
      }
      setWarnMsg(loiNhac.join(" "));
    } catch (err) {
      setActionErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  function onNoiDungPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    e.target.value = ""; // cho phép chọn lại đúng file đó sau khi lỗi
    if (!file) return;
    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith(".pdf") && !lowerName.endsWith(".docx")) {
      setActionErr("Chỉ nhận file Word (.docx) hoặc PDF.");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setActionErr("Tệp vượt quá 20 MB.");
      return;
    }
    // Nháp đã có nội dung (chữ HOẶC ảnh trang) thì phải hỏi — tải lên là THAY, không cộng thêm.
    if (coNoiDung) {
      setPendingFile(file);
      return;
    }
    void runTaiLen(file);
  }

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    e.target.value = ""; // cho phép chọn lại đúng file đó sau khi lỗi
    if (!f || !token || docId === null) return;
    if (f.size > MAX_FILE_BYTES) {
      setActionErr("Tệp vượt quá 20 MB.");
      return;
    }
    setBusy("upload");
    setActionErr(null);
    setOkMsg(null);
    try {
      const att = await api.noiQuy.uploadAttachment(token, docId, f);
      setDraft((d) => (d ? { ...d, attachments: [...d.attachments, att] } : d));
    } catch (err) {
      setActionErr(messageFor(err)); // 400 → hiện đúng `detail` server trả về
    } finally {
      setBusy(null);
    }
  }

  async function onDelFile() {
    if (!token || !delFile || isBusy) return;
    setBusy("del");
    setDlgErr(null);
    try {
      // id PHẢI là hàng file của NHÁP (không phải của bản đã ban hành) — nếu không ăn 400.
      await api.noiQuy.deleteAttachment(token, delFile.id);
      setDraft((d) => (d ? { ...d, attachments: d.attachments.filter((x) => x.id !== delFile.id) } : d));
      setDelFile(null);
    } catch (err) {
      setDlgErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  /** Thêm tài liệu MỚI, hoặc đổi tên tài liệu đang chọn — cùng một hộp thoại.
   *
   *  ⚠️ Nút "Thêm tài liệu" là BẮT BUỘC: sau migration hệ thống chỉ có đúng một tài liệu, không
   *  có nút này thì không bao giờ thêm được cái thứ hai. */
  async function onLuuTen() {
    if (!token || !tenDlg || isBusy) return;
    const ten = tenMoi.trim();
    if (!ten) {
      setDlgErr("Tên tài liệu không được để trống.");
      return;
    }
    setBusy("doiTen");
    setDlgErr(null);
    try {
      if (tenDlg.kieu === "them") {
        const moi = await api.noiQuy.createDocument(token, ten);
        setDocs((ds) => [...ds, moi]);
        setTenDlg(null);
        // Đang có ghi chú chưa lưu ở tài liệu hiện tại thì ĐỨNG YÊN — nhảy sang tài liệu mới là
        // nuốt mất câu họ vừa gõ. Thêm xong vẫn nằm sẵn trong danh sách, bấm vào là mở.
        if (dirty) {
          setOkMsg(
            `Đã thêm “${moi.title}” vào danh sách. Bạn đang có ghi chú chưa lưu ở tài liệu này ` +
            `nên chưa chuyển sang — lưu hoặc bỏ ghi chú rồi bấm tiêu đề mới ở cột phải.`,
          );
          return;
        }
        setOkMsg(`Đã thêm “${moi.title}”. Tải file nội dung lên rồi bấm “Ban hành” thì nhân viên mới thấy.`);
        // Đưa thẳng vào chế độ sửa của tài liệu mới: tạo xong mà đứng yên thì bước tiếp theo
        // (tải file lên) không có chỗ nào gợi ra.
        setDocId(moi.id);
        setCurrent(null);
        setVersions([]);
        await moNhap(moi.id);
      } else {
        const sua = await api.noiQuy.patchDocument(token, tenDlg.doc.id, { title: ten });
        setDocs((ds) => ds.map((x) => (x.id === sua.id ? { ...x, title: sua.title } : x)));
        setTenDlg(null);
        setOkMsg(`Đã đổi tên thành “${sua.title}”. Các bản ĐÃ ban hành vẫn giữ tiêu đề cũ của chúng.`);
      }
    } catch (err) {
      setDlgErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  /** Ẩn / hiện lại tài liệu. KHÔNG có nút xoá — backend cố ý không mở endpoint xoá. */
  async function onDoiHienThi() {
    if (!token || !askAn || isBusy) return;
    const bat = !askAn.is_active;
    setBusy("an");
    setDlgErr(null);
    try {
      const sua = await api.noiQuy.patchDocument(token, askAn.id, { is_active: bat });
      setDocs((ds) => ds.map((x) => (x.id === sua.id ? { ...x, is_active: sua.is_active } : x)));
      setAskAn(null);
      setOkMsg(
        bat
          ? `Đã hiện lại “${sua.title}” cho nhân viên.`
          : `Đã ẩn “${sua.title}”. Nhân viên không còn thấy tài liệu này; nội dung và lịch sử vẫn còn nguyên.`,
      );
    } catch (err) {
      setDlgErr(messageFor(err));
    } finally {
      setBusy(null);
    }
  }

  // --- Dựng hình -----------------------------------------------------------------------

  const files = mode === "edit" ? (draft?.attachments ?? []) : (current?.attachments ?? []);
  // Chế độ xem mà không có file ⇒ bỏ hẳn khối, đừng hiện hộp rỗng. Khi sửa thì luôn hiện
  // (cần chỗ bấm "Đính kèm file…").
  const showFiles = mode === "edit" || files.length > 0;
  const showHistory = canEdit && versions.length > 0;
  // Danh sách tài liệu LUÔN hiện với người soạn — kể cả khi chưa có tài liệu nào, vì nút "Thêm
  // tài liệu" nằm trong khối này.
  const showDocList = canEdit || docs.length > 0;
  const asideEmpty = !showDocList && !showFiles && !showHistory;

  const anhTrangNhap = draft?.pages ?? [];

  // ⚠️ PHẢI memo. `htmlText` gọi DOMPurify rồi parse lại TOÀN BỘ tài liệu — nội quy 40 trang là
  // việc nặng thấy rõ, mà nó chạy lại mỗi lần render (gõ ghi chú là mỗi ký tự một lần).
  const { soTu, docTrong } = useMemo(() => {
    const html = draft?.noi_dung ?? "";
    const plain = htmlText(html).trim();
    const trong = !plain && !/<img\b/i.test(html);
    return { soTu: plain ? plain.split(/\s+/).length : 0, docTrong: trong };
  }, [draft?.noi_dung]);
  const coNoiDung = !docTrong || anhTrangNhap.length > 0;
  // Bản dạng ảnh trang có `noi_dung` trống là BÌNH THƯỜNG — nội dung của nó là ảnh. Server cũng
  // cho ban hành. Không tính vào đây thì nút "Ban hành" bị khoá vĩnh viễn với nội quy PDF.
  const khongCoGiDeBanHanh = !coNoiDung;

  // ② TỐI ĐA MỘT banner: lỗi > cảnh báo nháp > thành công.
  function renderBanner(): ReactNode {
    if (loadErr)
      return (
        <div className="banner banner--error" role="alert">
          <span>{loadErr}</span>
          <Button variant="ghost" onClick={() => void load()}>
            Thử lại
          </Button>
        </div>
      );
    if (actionErr)
      return (
        <div className="banner banner--error" role="alert">
          <span>{actionErr}</span>
        </div>
      );
    // Cảnh báo chất lượng bản vừa nhập đứng TRÊN banner ngữ cảnh "đang sửa bản nháp": thanh dính
    // dưới đáy đã nhắc "Bản nháp — nhân viên chưa thấy" suốt phiên rồi, còn câu "soát lại số điều
    // khoản" thì chỉ có ở đây.
    if (warnMsg)
      return (
        <div className="banner banner--warn" role="alert">
          <span>
            {warnMsg}
            <span className="nq-banner__sub">
              Muốn giữ nguyên tuyệt đối cả số thứ tự: mở file trong Word → Lưu thành PDF → tải bản
              PDF lên.
            </span>
          </span>
        </div>
      );
    // ⚠️ `okMsg` phải đứng TRÊN banner "đang sửa bản nháp", nếu không nó không bao giờ hiện: ở chế
    // độ sửa thì điều kiện dưới luôn đúng, nên mọi thông báo kết quả bị che sạch.
    if (okMsg)
      return (
        <div className="banner banner--success" role="status">
          <span>{okMsg}</span>
        </div>
      );
    if (mode === "edit")
      return (
        <div className="banner banner--warn" role="status">
          <span>
            Bạn đang sửa BẢN NHÁP của “{docHienTai?.title ?? "tài liệu"}” — nhân viên CHƯA nhìn
            thấy nội dung này.
            <span className="nq-banner__sub">
              {daBanHanh
                ? `Họ vẫn đọc bản ban hành ngày ${fmtNgay(current?.published_at)}. Bấm “Ban hành” mới thay bản họ đọc — và chỉ thay ĐÚNG tài liệu này.`
                : "Tài liệu này chưa từng được ban hành nên chưa nằm trong danh sách của nhân viên."}
            </span>
          </span>
        </div>
      );
    // Chưa ban hành lần nào thì trạng thái rỗng đã nói về nháp treo rồi — không nhắc hai lần.
    if (docHienTai?.co_nhap && daBanHanh)
      return (
        <div className="banner banner--warn" role="status">
          <span>
            “{docHienTai.title}” có bản nháp chưa ban hành.
            <span className="nq-banner__sub">
              Nhân viên vẫn đang đọc bản ban hành {fmtNgay(current?.published_at)}.
            </span>
          </span>
          <Button variant="ghost" onClick={() => void enterEdit()} disabled={isBusy}>
            Mở bản nháp
          </Button>
        </div>
      );
    return null;
  }

  function renderEmpty(): ReactNode {
    // Chưa có TÀI LIỆU nào trong hệ thống.
    if (docId === null)
      return (
        <div className="card card--dense nq-state">
          <span className="nq-state__title">
            {canEdit ? "Chưa có tài liệu nội quy nào" : "Công ty chưa ban hành nội quy"}
          </span>
          <span className="nq-state__desc">
            {canEdit
              ? "Bấm “Thêm tài liệu” ở cột phải để tạo tài liệu đầu tiên (VD: Nội quy lao động), rồi tải file Word/PDF lên."
              : "Khi Giám đốc ban hành, nội dung sẽ hiện ở đây."}
          </span>
        </div>
      );
    // Có tài liệu nhưng CHÍNH NÓ chưa ban hành lần nào.
    if (!canEdit)
      return (
        <div className="card card--dense nq-state">
          <span className="nq-state__title">Tài liệu này chưa được ban hành</span>
          <span className="nq-state__desc">Khi Giám đốc ban hành, nội dung sẽ hiện ở đây.</span>
        </div>
      );
    return (
      <div className="card card--dense nq-state">
        <span className="nq-state__title">“{docHienTai?.title}” chưa được ban hành</span>
        <span className="nq-state__desc">
          {docHienTai?.co_nhap
            ? "Tài liệu này đang có bản nháp chưa ban hành."
            : "Tải file Word (.docx) hoặc PDF lên là xong — nhân viên đọc đúng bản gốc."}
        </span>
        <Button variant="accent" onClick={() => void enterEdit()} loading={busy === "draft"} disabled={isBusy}>
          {docHienTai?.co_nhap ? "Mở bản nháp" : "Tải nội dung lên"}
        </Button>
      </div>
    );
  }

  /** Khối tải nội dung lên — MỘT đường duy nhất, nhưng cái được và cái mất khác nhau rõ giữa
   *  PDF và Word nên phải nói thẳng ở đây, không giấu trong tooltip. */
  function renderSourcePicker(): ReactNode {
    return (
      <div className="nq-src">
        <span className="nq-src__title">Tải nội dung lên</span>
        <div className="nq-src__row">
          <input
            ref={noiDungRef}
            type="file"
            accept={NOI_DUNG_ACCEPT}
            hidden
            onChange={onNoiDungPick}
          />
          <Button
            variant="secondary"
            onClick={() => noiDungRef.current?.click()}
            loading={busy === "noiDung"}
            disabled={isBusy}
          >
            <Upload size={16} />
            {coNoiDung ? "Thay bằng file khác…" : "Chọn file Word/PDF…"}
          </Button>
          <span className="nq-src__desc">
            <strong>PDF</strong> — giữ nguyên 100% bố cục, kiểu chữ, chữ ký và dấu đỏ, kể cả bản
            scan. PDF dày mất 10–30 giây để dựng ảnh từng trang.
            <br />
            <strong>Word (.docx)</strong> — giữ được khoảng 90%, nhưng{" "}
            <strong>số thứ tự tự động (1., 2., a., b.) KHÔNG giữ được</strong>. Chắc ăn thì mở
            trong Word → Lưu thành PDF → tải bản PDF lên.
            <br />
            Sửa nội dung = sửa ở file rồi tải lên lại; không gõ trong app.
          </span>
        </div>
        {busy === "noiDung" && (
          // Dựng ảnh một tập PDF dày mất 10–30 giây. Không có dòng này thì màn hình đứng im và
          // người dùng bấm lại / tải lại trang giữa chừng.
          <p className="nq-src__busy" role="status">
            Đang xử lý tài liệu… PDF dày mất 10–30 giây để dựng ảnh từng trang. Đừng đóng trang.
          </p>
        )}
      </div>
    );
  }

  /** Nội dung của một bản (nháp hoặc đã ban hành): ảnh trang, hoặc HTML. */
  function renderNoiDung(v: NoiQuy | null): ReactNode {
    // Bản `file` CÓ ảnh trang ⇒ nội dung LÀ ảnh trang. `file` mà không có ảnh trang là đường Word:
    // nội dung là HTML giàu định dạng, hiện y như bản `html` (dữ liệu cũ soạn trong app).
    if (laBanAnhTrang(v)) return <PagesView pages={v!.pages} banGoc={timBanGoc(v)} />;
    return (
      <article className="nq-doc">
        <div
          // `--goc` = nội dung đã được trình bày xong ở Word. Class này TẮT mấy luật "ý kiến
          // riêng" của app (canh giữa h1, h2 màu rust): tài liệu nào không khai canh lề thì đúng
          // ra là canh trái, app tự canh giữa hộ là sửa dáng của người ta.
          className={`nq-doc__text${v?.source_kind === "file" ? " nq-doc__text--goc" : ""}`}
          aria-label="Nội dung nội quy"
          dangerouslySetInnerHTML={{ __html: docHtml(v?.noi_dung ?? "") }}
        />
      </article>
    );
  }

  function renderMain(): ReactNode {
    if (mode === "edit")
      return (
        <div>
          <label className="field">
            <span className="field__label">Ghi chú bản này (tuỳ chọn)</span>
            <input
              className="input"
              maxLength={255}
              value={ghiChu}
              placeholder="VD: Bổ sung quy định giờ tăng ca"
              onChange={(e) => setGhiChu(e.target.value)}
            />
          </label>
          <div className="nq-edit__wrap">
            {renderSourcePicker()}
            {anhTrangNhap.length > 0 ? (
              <>
                <div className="nq-src__note">
                  <span>
                    Bản nháp này đang hiện <strong>đúng bản gốc</strong> — nhân viên sẽ thấy chính
                    những trang dưới đây sau khi bạn bấm “Ban hành”.
                  </span>
                </div>
                <PagesView pages={anhTrangNhap} banGoc={timBanGoc(draft)} />
              </>
            ) : docTrong ? (
              <div className="card card--dense nq-state">
                <span className="nq-state__title">Bản nháp đang trống</span>
                <span className="nq-state__desc">
                  Chọn file Word/PDF ở trên để đưa nội dung vào. Chưa có nội dung thì chưa ban hành
                  được.
                </span>
              </div>
            ) : (
              <>
                <div className="nq-src__note">
                  <span>
                    Đây là <strong>bản xem trước</strong> của nháp — đúng thứ nhân viên sẽ đọc sau
                    khi bạn bấm “Ban hành”.
                  </span>
                </div>
                {renderNoiDung(draft)}
              </>
            )}
          </div>
        </div>
      );
    if (!daBanHanh) return renderEmpty();
    return renderNoiDung(current);
  }

  /** Tiêu đề TÀI LIỆU ĐANG MỞ + mốc ban hành CỦA CHÍNH NÓ.
   *
   *  Mốc này CỐ Ý không nằm ở header trang nữa: từ khi mỗi tài liệu ban hành riêng thì "Ban hành
   *  30/07" đặt cạnh tên màn là nói dối — ngày đó chỉ đúng cho một tài liệu trong bộ. */
  function renderDocHead(): ReactNode {
    if (docId === null) return null;
    const ten = docHienTai?.title ?? current?.title ?? "Tài liệu";
    return (
      <div className="nq-dochead">
        <div className="nq-dochead__row">
          <h2 className="nq-dochead__title">{ten}</h2>
          {mode === "edit" ? (
            <span className="badge-sem badge-sem--rust-solid">Bản nháp</span>
          ) : daBanHanh ? (
            <span className="badge-sem badge-sem--moss">Đang hiệu lực</span>
          ) : (
            <span className="badge-sem badge-sem--muted">Chưa ban hành</span>
          )}
          {docHienTai && !docHienTai.is_active && (
            <span className="badge-sem badge-sem--muted">Đã ẩn với nhân viên</span>
          )}
        </div>
        {mode === "view" && daBanHanh && (
          <p className="nq-dochead__meta">
            Ban hành {fmtNgay(current?.published_at)}
            {current?.published_by_name ? ` · ${current.published_by_name}` : ""}
            {current?.ghi_chu ? ` · ${current.ghi_chu}` : ""}
          </p>
        )}
      </div>
    );
  }

  /** DANH SÁCH TÀI LIỆU — khối đầu tiên của cột phải, TRÊN "Bản đã ký" và "Lịch sử".
   *
   *  Đây là đường duy nhất đi tới từng tài liệu trong bộ; đặt nó dưới hai khối kia là chôn mất
   *  chức năng chính của màn. */
  function renderDocList(): ReactNode {
    return (
      <section className="card card--dense">
        <h2 className="nq-aside__title">Tài liệu ({docs.length})</h2>
        {docs.length === 0 ? (
          <p className="cc-note">Chưa có tài liệu nào.</p>
        ) : (
          <ul className="nq-toclist">
            {docs.map((d) => {
              const dangChon = d.id === docId;
              return (
                <li key={d.id}>
                  <button
                    type="button"
                    className={`nq-tocitem${dangChon ? " is-active" : ""}`}
                    aria-current={dangChon ? "true" : undefined}
                    disabled={isBusy && !dangChon}
                    onClick={() => moTaiLieu(d.id)}
                  >
                    {d.title}
                    <span className="nq-tocitem__meta">
                      {d.published_at ? (
                        `Ban hành ${fmtNgay(d.published_at)}`
                      ) : (
                        <span className="nq-tocitem__tag">Chưa ban hành</span>
                      )}
                      {/* Hai nhãn dưới chỉ có nghĩa với người soạn: `/documents` của nhân viên đã
                          lọc bỏ doc chưa ban hành và doc đã ẩn, còn `co_nhap` luôn `false`. */}
                      {canEdit && d.co_nhap && <span className="nq-tocitem__tag"> · có nháp</span>}
                      {canEdit && !d.is_active && <span className="nq-tocitem__tag"> · đã ẩn</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {canEdit && (
          <div className="nq-toc__acts">
            <button
              type="button"
              className="nq-toc__btn"
              disabled={isBusy}
              onClick={() => {
                setDlgErr(null);
                setTenMoi("");
                setTenDlg({ kieu: "them" });
              }}
            >
              + Thêm tài liệu
            </button>
            {docHienTai && (
              <>
                <button
                  type="button"
                  className="nq-toc__btn"
                  disabled={isBusy}
                  onClick={() => {
                    setDlgErr(null);
                    setTenMoi(docHienTai.title);
                    setTenDlg({ kieu: "doi-ten", doc: docHienTai });
                  }}
                >
                  Đổi tên
                </button>
                <button
                  type="button"
                  className="nq-toc__btn"
                  disabled={isBusy}
                  onClick={() => {
                    setDlgErr(null);
                    setAskAn(docHienTai);
                  }}
                >
                  {docHienTai.is_active ? "Ẩn tài liệu" : "Hiện lại"}
                </button>
              </>
            )}
          </div>
        )}
      </section>
    );
  }

  return (
    <main className="nq">
      {/* Header LUÔN render — kể cả lúc đang tải / lỗi. */}
      <header className="ns__head">
        <div>
          <div className="nq__titlerow">
            <h1 className="ns__title">Nội quy công ty</h1>
          </div>
          {docs.length > 1 && (
            <p className="ns__sub">Bấm tiêu đề ở cột phải để mở từng tài liệu.</p>
          )}
        </div>
        {canEdit && mode === "view" && docId !== null && (
          // primary chứ không accent — màu rust để dành cho nút "Ban hành".
          <Button variant="primary" onClick={() => void enterEdit()} loading={busy === "draft"} disabled={isBusy}>
            Sửa tài liệu này
          </Button>
        )}
      </header>

      {renderBanner()}

      {loading ? (
        <div className="card card--dense nq-state">
          <span className="nq-state__desc">Đang tải nội quy…</span>
        </div>
      ) : loadErr ? null : (
        <div className={`nq__body${asideEmpty ? " nq__body--solo" : ""}`}>
          <div>
            {renderDocHead()}
            {busy === "doc" ? (
              <div className="card card--dense nq-state">
                <span className="nq-state__desc">Đang mở tài liệu…</span>
              </div>
            ) : (
              renderMain()
            )}
          </div>

          {!asideEmpty && (
            <aside className="nq-aside">
              {showDocList && renderDocList()}

              {showFiles && (
                <section className="card card--dense">
                  <h2 className="nq-aside__title">Bản đã ký</h2>
                  {files.length > 0 && (
                    <ul className="ns-filelist">
                      {files.map((a) => (
                        <li key={a.id}>
                          {/* /api/files xác thực bằng COOKIE — thẻ <a> thường là đủ, không cần Bearer. */}
                          <a href={assetUrl(a.file_url) ?? "#"} target="_blank" rel="noreferrer">
                            {a.file_name}
                          </a>
                          <span className="ns-file__date">{fmtNgay(a.uploaded_at)}</span>
                          {mode === "edit" && (
                            <button
                              type="button"
                              className="nq-filedel"
                              aria-label={`Gỡ file ${a.file_name}`}
                              disabled={isBusy}
                              onClick={() => {
                                setDlgErr(null);
                                setDelFile(a);
                              }}
                            >
                              <Icon name="trash" size={15} />
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {mode === "edit" && (
                    <>
                      {files.length === 0 && (
                        <p className="cc-note">Chưa có file. Đính kèm bản PDF đã ký/đóng dấu nếu có.</p>
                      )}
                      <input
                        ref={fileRef}
                        type="file"
                        accept={FILE_ACCEPT}
                        style={{ display: "none" }}
                        onChange={onPick}
                      />
                      <Button
                        variant="ghost"
                        onClick={() => fileRef.current?.click()}
                        loading={busy === "upload"}
                        disabled={isBusy}
                        style={{ marginTop: "var(--sp-3)" }}
                      >
                        Đính kèm file…
                      </Button>
                    </>
                  )}
                </section>
              )}

              {showHistory && (
                <section className="card card--dense">
                  <details>
                    <summary className="nq-aside__title">
                      Lịch sử ban hành ({versions.length})
                    </summary>
                    {/* Các dòng CỐ Ý không bấm được: API không trả `noi_dung` bản cũ. */}
                    <ul className="nq-hist">
                      {versions.map((v) => (
                        <li key={v.id}>
                          <span className="nq-hist__when">{fmtNgay(v.published_at)}</span>
                          {v.published_by_name ? ` · ${v.published_by_name}` : ""}
                          {v.ghi_chu ? ` — ${v.ghi_chu}` : ""}
                        </li>
                      ))}
                    </ul>
                    <p className="cc-note" style={{ marginTop: "var(--sp-3)" }}>
                      Lịch sử của riêng “{docHienTai?.title}”. Chỉ lưu mốc ban hành; không mở lại
                      được nội dung bản cũ trên màn này.
                    </p>
                  </details>
                </section>
              )}
            </aside>
          )}
        </div>
      )}

      {mode === "edit" && (
        <div className="nq-bar">
          <span className={`nq-bar__txt${khongCoGiDeBanHanh ? " is-blocked" : ""}`}>
            {khongCoGiDeBanHanh ? (
              "Nội quy đang trống — tải file Word/PDF lên rồi mới ban hành được."
            ) : (
              <>
                <span className="nq-bar__dot">●</span> Bản nháp — nhân viên chưa thấy
                {dirty ? " · Ghi chú chưa lưu" : savedAt ? ` · Đã lưu ${fmtGio(savedAt)}` : ""}
              </>
            )}
          </span>
          <span className="nq-bar__acts">
            <Button variant="ghost" onClick={onExit} disabled={isBusy}>
              Thoát sửa
            </Button>
            <Button
              variant="secondary"
              onClick={() => void onSave()}
              loading={busy === "save"}
              disabled={isBusy || !dirty}
            >
              Lưu ghi chú
            </Button>
            <Button
              variant="accent"
              onClick={() => {
                setDlgErr(null);
                setAskPublish(true);
              }}
              disabled={isBusy || khongCoGiDeBanHanh}
            >
              Ban hành…
            </Button>
          </span>
        </div>
      )}

      {/* danger={false} + KHÔNG countdown: ban hành không phá huỷ gì, bản cũ vẫn nằm trong lịch sử. */}
      <ConfirmDialog
        open={askPublish}
        title={`Ban hành “${docHienTai?.title ?? "tài liệu"}” cho toàn công ty?`}
        message="Sau khi ban hành, mọi nhân viên sẽ đọc bản này ngay lập tức."
        confirmLabel="Ban hành"
        cancelLabel="Xem lại"
        danger={false}
        busy={busy === "publish"}
        error={dlgErr}
        onConfirm={() => void onPublish()}
        onCancel={() => {
          setAskPublish(false);
          setDlgErr(null);
        }}
      >
        <p className="cc-note">
          Bản này:{" "}
          {anhTrangNhap.length > 0
            ? `${anhTrangNhap.length} trang ảnh từ bản gốc`
            : `${soTu} từ`}{" "}
          · {draft?.attachments.length ?? 0} file đính kèm
          {/* Mốc sửa cuối để phân biệt "nháp vừa làm xong" với "nháp bỏ quên từ 3 tuần trước" —
              cả hai trông giống hệt nhau ở mọi chỗ khác trên màn. */}
          {draft?.updated_at ? ` · nháp sửa lần cuối ${fmtNgayGio(draft.updated_at)}` : ""}
        </p>
        {/* Nhắc LẠI ngay trước khi bấm — đây là lần cuối còn cản được. Bản nội quy mất số điều
            khoản trông vẫn "đủ chữ", ban hành rồi thì cả công ty dẫn sai số điều. */}
        {warnMsg && (
          <p className="cc-note nq-dlg__warn" style={{ marginTop: "var(--sp-2)" }}>
            Đã soát lại số điều khoản chưa? Số thứ tự tự động của Word không giữ được ở bản này.
          </p>
        )}
        <p className="cc-note" style={{ marginTop: "var(--sp-2)" }}>
          {daBanHanh
            ? `Bản đang hiệu lực của tài liệu này (ban hành ${fmtNgay(current?.published_at)}) sẽ lùi thành lịch sử, không bị xoá.`
            : "Tài liệu này ban hành lần đầu — sau khi ban hành nó mới hiện trong danh sách của nhân viên."}
          {" "}Các tài liệu khác trong bộ nội quy KHÔNG bị đụng tới.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={pendingFile !== null}
        title="Thay nội dung bản nháp?"
        message={
          pendingFile
            ? `Nội dung hiện có trong bản nháp sẽ bị thay bằng “${pendingFile.name}”.`
            : undefined
        }
        confirmLabel="Thay bằng file này"
        cancelLabel="Giữ nội dung hiện tại"
        danger={false}
        busy={busy === "noiDung"}
        onConfirm={() => {
          if (pendingFile) void runTaiLen(pendingFile);
        }}
        onCancel={() => setPendingFile(null)}
      >
        <p className="cc-note">
          Tải lên là THAY, không cộng thêm.
          {anhTrangNhap.length > 0 && " Ảnh từng trang của bản gốc đang có cũng sẽ bị thay."}
        </p>
      </ConfirmDialog>

      {/* Thêm tài liệu / đổi tên — cùng một ô nhập, cùng một luật (không rỗng, không trùng tên). */}
      <ConfirmDialog
        open={tenDlg !== null}
        title={tenDlg?.kieu === "them" ? "Thêm tài liệu vào bộ nội quy" : "Đổi tên tài liệu"}
        confirmLabel={tenDlg?.kieu === "them" ? "Thêm tài liệu" : "Lưu tên"}
        cancelLabel="Hủy"
        danger={false}
        busy={busy === "doiTen"}
        error={dlgErr}
        confirmDisabled={!tenMoi.trim()}
        onConfirm={() => void onLuuTen()}
        onCancel={() => {
          setTenDlg(null);
          setDlgErr(null);
        }}
      >
        <label className="field">
          <span className="field__label">Tên tài liệu</span>
          <input
            className="input"
            maxLength={200}
            autoFocus
            value={tenMoi}
            placeholder="VD: Nội quy lao động"
            onChange={(e) => setTenMoi(e.target.value)}
          />
        </label>
        <p className="cc-note" style={{ marginTop: "var(--sp-2)" }}>
          {tenDlg?.kieu === "them"
            ? "Tạo xong sẽ mở luôn chế độ sửa để bạn tải file Word/PDF lên. Tài liệu chỉ hiện với nhân viên sau khi ban hành."
            : "Chỉ đổi tên hiện hành. Các bản ĐÃ ban hành vẫn giữ tiêu đề lúc chúng được ban hành — đổi tên hôm nay không viết lại lịch sử hôm qua."}
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={askAn !== null}
        title={askAn?.is_active ? `Ẩn “${askAn?.title}” với nhân viên?` : `Hiện lại “${askAn?.title}”?`}
        message={
          askAn?.is_active
            ? "Tài liệu sẽ biến khỏi danh sách của nhân viên."
            : "Tài liệu sẽ hiện lại trong danh sách của nhân viên."
        }
        confirmLabel={askAn?.is_active ? "Ẩn tài liệu" : "Hiện lại"}
        cancelLabel="Giữ nguyên"
        danger={!!askAn?.is_active}
        busy={busy === "an"}
        error={dlgErr}
        onConfirm={() => void onDoiHienThi()}
        onCancel={() => {
          setAskAn(null);
          setDlgErr(null);
        }}
      >
        {askAn?.is_active && (
          <p className="cc-note">
            Nội dung, file đã ký và lịch sử ban hành vẫn còn nguyên — ẩn là cất đi, không phải xoá.
            Bật lại bất cứ lúc nào bằng nút “Hiện lại”. (Hệ thống CỐ Ý không có nút xoá tài liệu.)
          </p>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={delFile !== null}
        title="Gỡ file đính kèm?"
        message={delFile ? `“${delFile.file_name}” sẽ bị gỡ khỏi bản nháp.` : undefined}
        confirmLabel="Gỡ file"
        cancelLabel="Giữ lại"
        danger
        busy={busy === "del"}
        error={dlgErr}
        onConfirm={() => void onDelFile()}
        onCancel={() => {
          setDelFile(null);
          setDlgErr(null);
        }}
      />

      <DiscardChangesDialog
        open={askDiscard !== false}
        message="Ghi chú của bản nháp có thay đổi chưa lưu. Bỏ thay đổi đó?"
        onDiscard={() => leaveEdit(askDiscard === false ? null : askDiscard.toi)}
        onKeepEditing={() => setAskDiscard(false)}
      />
    </main>
  );
}
