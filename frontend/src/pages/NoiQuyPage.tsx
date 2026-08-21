import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ExternalLink,
  FileImage,
  FileText,
  Plus,
  Search,
  Upload,
  X,
} from "lucide-react";
import { ApiError, api, assetUrl, type NoiQuyRecord } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyRow } from "../components/EmptyState";
import { Pager, trangHopLe } from "../components/Pager";
import { RowActionButton } from "../components/RowActionButton";
import { useDebounced } from "../utils/useDebounced";
import "./nhan-su.css";
import "./noi-quy.css";

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const FILE_ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp";
/** Cỡ trang chuẩn toàn hệ (prd-dong-bo-ui-thu-mua-nhan-su §2). */
const PAGE_SIZE = 20;

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isNetwork) return "Mất kết nối. Vui lòng thử lại.";
    if (error.status >= 500) return "Có lỗi xảy ra, vui lòng thử lại sau.";
    return error.message;
  }
  return error instanceof Error ? error.message : "Đã có lỗi xảy ra.";
}

function dateTime(value: string): string {
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
  const date = new Date(!hasZone && value.includes("T") ? `${value}Z` : value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fileSize(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function isImage(row: NoiQuyRecord): boolean {
  return row.file_type.startsWith("image/");
}

export function NoiQuyPage() {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("noi_quy", "create");
  const canDelete = can("noi_quy", "delete");

  const [rows, setRows] = useState<NoiQuyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  /** Lỗi THAO TÁC (chọn file sai, tải lên hỏng, xoá hỏng) → băng đỏ trên đầu màn. */
  const [error, setError] = useState<string | null>(null);
  /** Lỗi TẢI DANH SÁCH → ô nhớ RIÊNG, chỉ nó mới được thay chỗ của bảng.
   *  ⚠ Gộp hai ô này lại thì chọn nhầm file 30 MB cũng làm cả bảng tài liệu biến mất. */
  const [listError, setListError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  /** Ô nhập bám `query` (gõ tới đâu hiện tới đó); chỉ lời gọi máy chủ đọc bản đã chậm 300ms. */
  const queryDebounced = useDebounced(query);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [preview, setPreview] = useState<NoiQuyRecord | null>(null);
  const [deleting, setDeleting] = useState<NoiQuyRecord | null>(null);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setListError(null);
    try {
      const res = await api.noiQuy.list(token, {
        q: queryDebounced.trim() || undefined,
        page,
        size: PAGE_SIZE,
      });
      setRows(res.items);
      setTotal(res.total);
      // Đang đứng trang 3 mà xoá nốt dòng cuối ⇒ chỉ còn 2 trang: nhảy về trang cuối còn thật,
      // không để bảng rỗng trơn làm người dùng tưởng mất sạch tài liệu.
      const trangCanVe = trangHopLe(page, res.total, PAGE_SIZE);
      if (trangCanVe !== null) setPage(trangCanVe);
    } catch (err) {
      setListError(messageFor(err));
    } finally {
      setLoading(false);
    }
  }, [token, queryDebounced, page]);

  useEffect(() => {
    void load();
  }, [load]);

  function resetForm() {
    setName("");
    setNote("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  function closeCreate() {
    if (busy) return;
    setShowCreate(false);
    resetForm();
  }

  function chooseFile(selected: File | null) {
    if (!selected) return;
    if (selected.size > MAX_FILE_BYTES) {
      setError("Tệp vượt quá 20 MB.");
      return;
    }
    if (!/\.(pdf|png|jpe?g|webp)$/i.test(selected.name)) {
      setError("Chỉ nhận PDF, PNG, JPG/JPEG hoặc WebP để có thể xem trước.");
      return;
    }
    setError(null);
    setFile(selected);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token || busy) return;
    if (!name.trim()) {
      setError("Tên tài liệu là bắt buộc.");
      return;
    }
    if (!file) {
      setError("Bạn chưa chọn file tài liệu.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.noiQuy.create(token, {
        name: name.trim(),
        note: note.trim(),
        file,
      });
      setShowCreate(false);
      resetForm();
      // TẢI LẠI thay vì chèn tay vào đầu mảng: bảng đã phân trang, chèn tay là trang hiện tại
      // thừa ra 1 dòng còn `total` thì đứng im ⇒ số trang lệch. Bản ghi mới xếp đầu (mới nhất
      // trước) nên về trang 1 để người vừa tải lên nhìn thấy ngay việc mình vừa làm.
      if (page !== 1) setPage(1);   // đổi trang ⇒ effect tự gọi lại `load`
      else void load();
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!token || !deleting || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.noiQuy.delete(token, deleting.id);
      if (preview?.id === deleting.id) setPreview(null);
      setDeleting(null);
      // TẢI LẠI thay vì lọc khỏi mảng: lọc tay để lại trang 19 dòng và `total` sai một đơn vị.
      void load();
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="nqr">
      <header className="ns__head nqr__head">
        <div>
          {/* Eyebrow = tên SECTION trên sidebar, chép NGUYÊN VĂN, một cấp.
              ⚠ Lớp cũ `ns__eyebrow` KHÔNG có CSS ở bất kỳ file nào (nên phải gõ HOA bằng tay
              mới ra dáng eyebrow) — dùng `eyebrow` của global.css. Mục này vừa được dời sang
              section "Nhân sự & Lương" nên chữ ở đây phải khớp tên section đó. */}
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="ns__title">Nội quy công ty</h1>
          <p className="ns__sub">Danh mục tài liệu nội quy và quy định đang lưu hành.</p>
        </div>
        {/* ⚠ `variant="primary"` trong code này ra màu NAVY. Hành động chính = `accent`. */}
        {canCreate && (
          <Button variant="accent" onClick={() => setShowCreate(true)}>
            <Plus size={16} /> Thêm tài liệu
          </Button>
        )}
      </header>

      {error && <div className="banner banner--error" role="alert">{error}</div>}

      <section className="nqr__tools" aria-label="Tìm tài liệu">
        <Search size={17} aria-hidden="true" />
        <input
          value={query}
          // ĐỔI TỪ KHOÁ ⇒ VỀ TRANG 1, đặt NGAY TRONG handler (không qua `useEffect` theo dõi
          // từ khoá): làm ở effect thì lượt tải cũ đã bắn đi với số trang cũ rồi mới có lượt
          // tải mới — hai lượt chồng nhau, lượt cũ về sau đè kết quả mới.
          // Thiếu hẳn bước reset thì đang ở trang 3, gõ từ khoá chỉ còn 1 trang kết quả ⇒ bảng
          // rỗng trơn mà người dùng tưởng "không có gì khớp". Lỗi này đã gặp thật.
          onChange={(event) => { setQuery(event.target.value); setPage(1); }}
          placeholder="Tìm theo mã, tên, file, người upload..."
          aria-label="Tìm tài liệu nội quy"
        />
        {/* Số này lấy từ `total` của MÁY CHỦ, không phải `rows.length` — bảng đã phân trang nên
            `rows.length` chỉ là số dòng của trang đang xem (tối đa 20). */}
        <span>{total} bản ghi</span>
      </section>

      <section className="nqr__table-wrap">
        <table className="nqr__table">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Tên</th>
              <th>File</th>
              <th>Ghi chú</th>
              <th>Người upload</th>
              <th>Ngày upload</th>
              {canDelete && <th className="nqr__action-head">Thao tác</th>}
            </tr>
          </thead>
          <tbody>
            {/* ⚠ colSpan phải khớp số cột ĐANG hiện — cột "Thao tác" chỉ có khi `canDelete`,
                gõ số cứng là ô rỗng thụt hẳn một cột với người không có quyền xoá. */}
            {loading && (
              <EmptyRow colSpan={canDelete ? 7 : 6} trangThai="dang-tai" />
            )}
            {!loading && listError && (
              <EmptyRow
                colSpan={canDelete ? 7 : 6}
                trangThai="loi"
                loi={listError}
                onThuLai={() => void load()}
              />
            )}
            {!loading && !listError && rows.length === 0 && (
              <EmptyRow
                colSpan={canDelete ? 7 : 6}
                icon="book"
                title={query ? "Chưa có tài liệu nào khớp" : "Chưa có tài liệu nội quy"}
                sub={query ? "Thử rút gọn từ khoá tìm." : "Bấm “Thêm tài liệu” để tải nội quy đầu tiên lên."}
              />
            )}
            {!loading && !listError && rows.map((row) => (
              <tr key={row.id}>
                <td><span className="nqr__code">{row.code}</span></td>
                <td><strong className="nqr__name">{row.name}</strong></td>
                <td>
                  <button type="button" className="nqr__file" onClick={() => setPreview(row)}>
                    {isImage(row) ? <FileImage size={17} /> : <FileText size={17} />}
                    <span><b>{row.file_name}</b><small>{fileSize(row.file_size)}</small></span>
                  </button>
                </td>
                <td className="nqr__note">{row.note || "—"}</td>
                <td>{row.uploaded_by_name}</td>
                <td className="nqr__date">{dateTime(row.uploaded_at)}</td>
                {canDelete && (
                  <td className="nqr__action">
                    {/* Nút xoá trên dòng → RowActionButton dense, GIỮ `danger`: xoá kéo theo
                        cả file đính kèm, mất tín hiệu đỏ là bấm nhầm cột bên cạnh. */}
                    <RowActionButton
                      dense
                      danger
                      label={`Xóa ${row.name}`}
                      icon="trash"
                      onClick={() => setDeleting(row)}
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Chân bảng CHỈ hiện khi bảng thật sự có dòng (chuẩn §2.7, mẫu `SuppliersPage`): lúc
          đang tải / lỗi / rỗng thì khối `EmptyRow` trong bảng đã nói hết, in thêm "Tổng 0 tài
          liệu" bên dưới chỉ là một câu thừa mâu thuẫn với câu ngay trên nó. */}
      {!loading && !listError && rows.length > 0 && (
        <Pager
          total={total}
          page={page}
          size={PAGE_SIZE}
          loading={loading}
          unit="tài liệu"
          onPage={setPage}
        />
      )}

      {showCreate && (
        <div className="nqr-modal" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeCreate();
        }}>
          <form className="nqr-modal__box nqr-create" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="nqr-create-title">
            <header className="nqr-modal__head">
              <div><span>THÊM BẢN GHI</span><h2 id="nqr-create-title">Tải tài liệu nội quy</h2></div>
              <button type="button" onClick={closeCreate} aria-label="Đóng" disabled={busy}><X size={19} /></button>
            </header>
            <div className="nqr-modal__body">
              <label className="field">
                <span className="field__label">Tên tài liệu <b className="required">*</b></span>
                <input className="input" value={name} maxLength={200} onChange={(event) => setName(event.target.value)} placeholder="VD: Nội quy lao động năm 2026" autoFocus />
              </label>
              <label className="field">
                <span className="field__label">Ghi chú</span>
                <textarea className="input nqr-create__note" value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="Thông tin bổ sung nếu có" />
              </label>
              <div className="field">
                <span className="field__label">File tài liệu <b className="required">*</b></span>
                <input ref={fileRef} type="file" accept={FILE_ACCEPT} hidden onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} />
                <button type="button" className={`nqr-picker${file ? " has-file" : ""}`} onClick={() => fileRef.current?.click()}>
                  <Upload size={21} />
                  <span>{file ? file.name : "Chọn file PDF hoặc ảnh"}<small>{file ? fileSize(file.size) : "PDF, PNG, JPG, WebP · tối đa 20 MB"}</small></span>
                </button>
              </div>
            </div>
            <footer className="nqr-modal__foot">
              <Button type="button" variant="ghost" onClick={closeCreate} disabled={busy}>Hủy</Button>
              <Button type="submit" variant="accent" loading={busy}>Tải lên</Button>
            </footer>
          </form>
        </div>
      )}

      {preview && (
        <div className="nqr-modal nqr-modal--preview" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setPreview(null);
        }}>
          <section className="nqr-modal__box nqr-preview" role="dialog" aria-modal="true" aria-labelledby="nqr-preview-title">
            <header className="nqr-modal__head">
              <div><span>{preview.code}</span><h2 id="nqr-preview-title">{preview.name}</h2></div>
              <div className="nqr-preview__actions">
                <a href={assetUrl(preview.file_url) ?? "#"} target="_blank" rel="noreferrer" title="Mở trong tab mới"><ExternalLink size={18} /></a>
                <button type="button" onClick={() => setPreview(null)} aria-label="Đóng"><X size={19} /></button>
              </div>
            </header>
            <div className="nqr-preview__body">
              {isImage(preview) ? (
                <img src={assetUrl(preview.file_url) ?? ""} alt={preview.name} />
              ) : (
                <iframe src={assetUrl(preview.file_url) ?? ""} title={preview.name} />
              )}
            </div>
          </section>
        </div>
      )}

      <ConfirmDialog
        open={deleting !== null}
        title="Xóa tài liệu nội quy?"
        message={deleting ? `“${deleting.name}” và file đính kèm sẽ bị xóa khỏi hệ thống.` : undefined}
        confirmLabel="Xóa tài liệu"
        cancelLabel="Giữ lại"
        danger
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => { if (!busy) setDeleting(null); }}
      />
    </main>
  );
}
