// Khung "Tệp đính kèm" dùng chung: kéo-thả hoặc chọn nhiều tệp, mỗi tệp một request (tối đa 3 chạy
// song song), tệp lỗi đứng riêng với nút Thử lại, tệp xong hiện ngay trong danh sách. Danh sách có ảnh
// thu nhỏ, xem trước ảnh/PDF, tải về, xoá có hỏi lại.
//
// Component KHÔNG gọi API: màn cha giữ danh sách và truyền hàm tải/xoá, nên gắn được vào bất kỳ
// chứng từ nào có bảng đính kèm cùng hình `TepDinhKem`.
import { useEffect, useRef, useState, type DragEvent } from "react";
import { ApiError, assetUrl } from "../api/client";
import { ngayGio } from "../pages/keHoachSxShared";
import { Button } from "./Button";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icons";
import {
  chonViecKeTiep,
  duoiTep,
  dungLuong,
  kiemTruocKhiTai,
  kieuXemTruoc,
  nenThuLai,
  type TepDinhKem,
  type TepXem,
  type ViecTai,
} from "./tepDinhKem";
import "./dinh-kem-tep.css";

/** Ba tệp cùng lúc: đủ nhanh cho một mẻ ảnh mẫu, không chiếm hết băng thông của máy xưởng. */
const SONG_SONG = 3;

function loiTaiLen(e: unknown, maxBytes: number): { loi: string; thuLai: boolean } {
  if (!(e instanceof ApiError)) return { loi: "Tải lên không thành công", thuLai: true };
  if (e.isNetwork) return { loi: "Mất kết nối tới máy chủ", thuLai: true };
  // 413 do nginx chặn trả trang HTML, không có câu tiếng Việt của máy chủ để hiện.
  if (e.status === 413) {
    return { loi: `Tệp vượt quá ${Math.round(maxBytes / (1024 * 1024))}MB`, thuLai: false };
  }
  if (e.isForbidden) return { loi: "Bạn không có quyền thêm tệp", thuLai: false };
  return { loi: e.message, thuLai: nenThuLai(e.status) };
}

/** Lớp tô màu theo loại tệp (dùng chung với thẻ tệp chỉ đọc ở Bàn tổ). */
export function layLopDuoi(tenTep: string): string {
  const ext = duoiTep(tenTep).toLowerCase();
  if (ext === "pdf") return "dkt-thumb--pdf";
  if (["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(ext)) return "dkt-thumb--img";
  if (["doc", "docx"].includes(ext)) return "dkt-thumb--doc";
  if (["xls", "xlsx", "csv"].includes(ext)) return "dkt-thumb--xls";
  if (["ai", "cdr", "psd", "dwg", "dxf"].includes(ext)) return "dkt-thumb--cad";
  if (["zip", "rar", "7z", "tar"].includes(ext)) return "dkt-thumb--zip";
  return "dkt-thumb--other";
}

export function DinhKemTep({
  items,
  loiNap,
  onNapLai,
  canEdit,
  lyDoKhoa,
  maxBytes,
  taiLen,
  xoa,
}: {
  /** `null` = đang nạp lần đầu. */
  items: TepDinhKem[] | null;
  loiNap?: string | null;
  onNapLai?: () => void;
  canEdit: boolean;
  /** Vì sao không thêm/xoá được (vd đơn đã hủy). Bỏ trống khi chỉ đơn giản là không có quyền. */
  lyDoKhoa?: string | null;
  maxBytes: number;
  /** Gửi MỘT tệp; resolve khi máy chủ đã nhận và màn cha đã đưa tệp vào `items`. */
  taiLen: (file: File) => Promise<void>;
  xoa: (tep: TepDinhKem) => Promise<void>;
}) {
  const [hang, setHang] = useState<ViecTai[]>([]);
  const [keo, setKeo] = useState(false);
  const [xem, setXem] = useState<TepDinhKem | null>(null);
  const [canXoa, setCanXoa] = useState<TepDinhKem | null>(null);
  const [dangXoa, setDangXoa] = useState(false);
  const [loiXoa, setLoiXoa] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const seq = useRef(0);
  // Việc đã phát request — chặn phát hai lần khi effect chạy lại trước lúc state kịp đổi sang "dang"
  // (StrictMode chạy effect hai lần; thêm tệp mới giữa chừng cũng làm effect chạy lại).
  const daPhat = useRef(new Set<number>());
  const taiLenRef = useRef(taiLen);
  useEffect(() => {
    taiLenRef.current = taiLen;
  }, [taiLen]);

  useEffect(() => {
    for (const id of chonViecKeTiep(hang, SONG_SONG)) {
      const viec = hang.find((v) => v.id === id);
      if (!viec || daPhat.current.has(id)) continue;
      daPhat.current.add(id);
      setHang((h) => h.map((v) => (v.id === id ? { ...v, trangThai: "dang", loi: null } : v)));
      taiLenRef.current(viec.file).then(
        () => {
          daPhat.current.delete(id);
          setHang((h) => h.filter((v) => v.id !== id));
        },
        (e: unknown) => {
          daPhat.current.delete(id);
          const { loi, thuLai } = loiTaiLen(e, maxBytes);
          setHang((h) => h.map((v) => (v.id === id ? { ...v, trangThai: "loi", loi, thuLai } : v)));
        },
      );
    }
  }, [hang, maxBytes]);

  // Đóng tab/tải lại trang giữa lúc còn tệp chưa gửi xong thì trình duyệt hỏi lại.
  const conDangGui = hang.some((v) => v.trangThai !== "loi");
  useEffect(() => {
    if (!conDangGui) return;
    const giu = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", giu);
    return () => window.removeEventListener("beforeunload", giu);
  }, [conDangGui]);

  function themTep(files: FileList | null) {
    if (!files || files.length === 0) return;
    const moi: ViecTai[] = Array.from(files).map((file) => {
      const loi = kiemTruocKhiTai(file, maxBytes);
      return { id: ++seq.current, file, trangThai: loi ? "loi" : "cho", loi, thuLai: false };
    });
    setHang((h) => [...h, ...moi]);
  }

  function coTep(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  async function xacNhanXoa() {
    if (!canXoa) return;
    setDangXoa(true);
    setLoiXoa(null);
    try {
      await xoa(canXoa);
      setCanXoa(null);
    } catch (e) {
      setLoiXoa(e instanceof ApiError ? e.message : "Xoá không thành công");
    } finally {
      setDangXoa(false);
    }
  }

  const soDangGui = hang.filter((v) => v.trangThai !== "loi").length;
  const coTepLuu = (items ?? []).length > 0 || hang.length > 0;

  return (
    <div className="dkt">
      {lyDoKhoa && (
        <p className="dkt-khoa">
          <Icon name="alert" size={16} /> <span>{lyDoKhoa}</span>
        </p>
      )}

      {/* 1. Khi CHƯA có tệp nào: Thùng Upload Hợp Nhất (Hero Dropzone) */}
      {canEdit && !coTepLuu && items !== null && (
        <div
          className={`dkt-hero-drop${keo ? " is-keo" : ""}`}
          onDragEnter={(e) => {
            if (coTep(e)) {
              e.preventDefault();
              setKeo(true);
            }
          }}
          onDragOver={(e) => {
            if (coTep(e)) e.preventDefault();
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setKeo(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setKeo(false);
            themTep(e.dataTransfer.files);
          }}
        >
          <div className="dkt-hero__badge" aria-hidden="true">
            <Icon name="upload" size={32} />
          </div>
          <p className="dkt-hero__title">
            {keo ? "Thả tệp vào đây để tải lên ngay!" : "Kéo & thả tệp vào đây để đính kèm"}
          </p>
          <p className="dkt-hero__desc">
            Bạn có thể đính kèm các file maket, bản vẽ kỹ thuật, hợp đồng PDF, ảnh mẫu hoặc tài liệu liên quan.
          </p>
          <Button
            type="button"
            variant="primary"
            className="dkt-hero__btn"
            onClick={() => inputRef.current?.click()}
          >
            <Icon name="plus" size={18} />
            <span>Chọn tệp từ máy tính…</span>
          </Button>
          <div className="dkt-hero__formats">
            <span className="dkt-fmt-tag">PDF</span>
            <span className="dkt-fmt-tag">PNG, JPG</span>
            <span className="dkt-fmt-tag">AI, CDR</span>
            <span className="dkt-fmt-tag">DOCX, XLSX</span>
            <span className="dkt-fmt-tag">ZIP</span>
            <span className="dkt-fmt-hint">· Tối đa {Math.round(maxBytes / (1024 * 1024))}MB mỗi tệp</span>
          </div>
          <input
            ref={inputRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              themTep(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      )}

      {/* 2. Khi ĐÃ có tệp: Vùng Upload thu gọn ở trên (Compact Dropbar) */}
      {canEdit && coTepLuu && (
        <div
          className={`dkt-compact-drop${keo ? " is-keo" : ""}`}
          onDragEnter={(e) => {
            if (coTep(e)) {
              e.preventDefault();
              setKeo(true);
            }
          }}
          onDragOver={(e) => {
            if (coTep(e)) e.preventDefault();
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setKeo(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setKeo(false);
            themTep(e.dataTransfer.files);
          }}
        >
          <div className="dkt-compact__left">
            <span className="dkt-compact__icon" aria-hidden="true">
              <Icon name="upload" size={18} />
            </span>
            <div className="dkt-compact__text">
              <p className="dkt-compact__lead">
                {keo ? "Thả tệp vào đây để tải thêm!" : "Kéo thả hoặc bấm để thêm tệp đính kèm"}
              </p>
              <p className="dkt-compact__hint">Tối đa {Math.round(maxBytes / (1024 * 1024))}MB mỗi tệp</p>
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            className="dkt-compact__btn"
            onClick={() => inputRef.current?.click()}
          >
            <Icon name="plus" size={15} />
            <span>Thêm tệp…</span>
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              themTep(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      )}

      {/* Hàng chờ tải lên */}
      {hang.length > 0 && (
        <div className="dkt-hang">
          <div className="dkt-hang__head">
            <span className="dkt-hang__spinner" />
            <p className="dkt-hang__tong" aria-live="polite">
              {soDangGui > 0 ? `Đang tải lên ${soDangGui} tệp…` : "Có tệp chưa tải lên được"}
            </p>
          </div>
          <ul className="dkt-hang__list">
            {hang.map((v) => (
              <li key={v.id} className={`dkt-viec dkt-viec--${v.trangThai}`}>
                <div className="dkt-viec__info">
                  <p className="dkt-viec__ten">{v.file.name}</p>
                  <p className="dkt-viec__trang-thai">
                    {v.trangThai === "dang" && (
                      <>
                        <span className="spinner" aria-hidden="true" /> Đang tải lên…
                      </>
                    )}
                    {v.trangThai === "cho" && "Đang chờ hàng đợi"}
                    {v.trangThai === "loi" && (
                      <>
                        <Icon name="alert" size={14} /> {v.loi}
                      </>
                    )}
                    <span className="dkt-viec__co"> · {dungLuong(v.file.size)}</span>
                  </p>
                </div>
                {v.trangThai === "loi" && (
                  <div className="dkt-viec__nut">
                    {v.thuLai && (
                      <button
                        type="button"
                        className="dkt-nut"
                        onClick={() =>
                          setHang((h) => h.map((x) => (x.id === v.id ? { ...x, trangThai: "cho", loi: null } : x)))
                        }
                      >
                        <Icon name="refresh" size={14} />
                        <span>Thử lại</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="dkt-nut dkt-nut--xoa"
                      aria-label={`Bỏ ${v.file.name} khỏi hàng chờ`}
                      onClick={() => setHang((h) => h.filter((x) => x.id !== v.id))}
                    >
                      <Icon name="x" size={14} />
                      <span>Bỏ</span>
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Lỗi nạp hoặc Loading */}
      {loiNap ? (
        <div className="dkt-loi-nap">
          <span>
            <Icon name="alert" size={16} /> {loiNap}
          </span>
          {onNapLai && (
            <button type="button" className="dkt-nut" onClick={onNapLai}>
              <Icon name="refresh" size={14} />
              <span>Tải lại danh sách</span>
            </button>
          )}
        </div>
      ) : items === null ? (
        <div className="dkt-loading">
          <span className="spinner" />
          <span>Đang nạp danh sách tệp đính kèm…</span>
        </div>
      ) : items.length > 0 && (
        <div className="dkt-sec">
          <div className="dkt-sec__head">
            <span className="dkt-sec__title">Tệp đã đính kèm ({items.length})</span>
          </div>
          <ul className="dkt-list">
            {items.map((t) => {
              const kieu = kieuXemTruoc(t);
              const url = assetUrl(t.file_url) ?? undefined;
              const extClass = layLopDuoi(t.ten_tep);
              const duoi = duoiTep(t.ten_tep);
              return (
                <li key={t.id} className="dkt-tep">
                  {kieu === "khac" ? (
                    <span className={`dkt-tep__thumb ${extClass}`} aria-hidden="true">
                      {duoi}
                    </span>
                  ) : (
                    <button
                      type="button"
                      className={`dkt-tep__thumb ${extClass}`}
                      aria-label={`Xem trước ${t.ten_tep}`}
                      onClick={() => setXem(t)}
                    >
                      {kieu === "anh" ? (
                        <img src={url} alt="" loading="lazy" />
                      ) : (
                        <span className="dkt-tep__thumb-label">PDF</span>
                      )}
                    </button>
                  )}
                  <div className="dkt-tep__info">
                    <div className="dkt-tep__top">
                      <p className="dkt-tep__ten" title={t.ten_tep}>
                        {t.ten_tep}
                      </p>
                      <span className={`dkt-tag ${extClass}`}>{duoi}</span>
                    </div>
                    <p className="dkt-tep__meta">
                      <span>{dungLuong(t.kich_thuoc)}</span>
                      <span className="dkt-meta-sep">•</span>
                      <span>{t.nguoi_tai_ten ?? "Hệ thống"}</span>
                      <span className="dkt-meta-sep">•</span>
                      <span>{ngayGio(t.tai_luc)}</span>
                    </p>
                  </div>
                  <div className="dkt-tep__nut">
                    {kieu !== "khac" && (
                      <button
                        type="button"
                        className="dkt-nut dkt-nut--xem"
                        title="Xem trước tệp"
                        onClick={() => setXem(t)}
                      >
                        <Icon name="eye" size={14} />
                        <span>Xem</span>
                      </button>
                    )}
                    <a
                      className="dkt-nut dkt-nut--tai"
                      href={url}
                      download={t.ten_tep}
                      target="_blank"
                      rel="noopener"
                      title="Tải tệp về máy"
                    >
                      <Icon name="download" size={14} />
                      <span>Tải về</span>
                    </a>
                    {canEdit && (
                      <button
                        type="button"
                        className="dkt-nut dkt-nut--xoa"
                        aria-label={`Xoá ${t.ten_tep}`}
                        title="Xoá tệp"
                        onClick={() => {
                          setLoiXoa(null);
                          setCanXoa(t);
                        }}
                      >
                        <Icon name="trash" size={14} />
                        <span>Xoá</span>
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {xem && <XemTruoc tep={xem} onDong={() => setXem(null)} />}

      <ConfirmDialog
        open={canXoa !== null}
        title="Xoá tệp đính kèm?"
        message={canXoa ? `“${canXoa.ten_tep}” sẽ bị xoá hẳn khỏi kho lưu trữ, không khôi phục được.` : undefined}
        confirmLabel="Xoá tệp"
        cancelLabel="Giữ lại"
        danger
        busy={dangXoa}
        error={loiXoa}
        onConfirm={xacNhanXoa}
        onCancel={() => setCanXoa(null)}
      />
    </div>
  );
}

/** Hộp xem trước ảnh/PDF toàn màn — dùng lại ở thẻ tệp chỉ đọc (Bàn tổ). */
export function XemTruoc({ tep, onDong }: { tep: TepXem; onDong: () => void }) {
  const nutDong = useRef<HTMLButtonElement | null>(null);
  const onDongRef = useRef(onDong);
  useEffect(() => {
    onDongRef.current = onDong;
  }, [onDong]);

  useEffect(() => {
    const truoc = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    nutDong.current?.focus();
    // Bắt ở pha capture + preventDefault: trang chứa (vd bàn tổ) cũng nghe Esc ở `document` để đóng
    // ngăn chi tiết, đăng ký trước nên chạy trước — không vậy thì một Esc đóng luôn cả ngăn.
    const phim = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();
      onDongRef.current();
    };
    document.addEventListener("keydown", phim, true);
    return () => {
      document.removeEventListener("keydown", phim, true);
      truoc?.focus();
    };
  }, []);

  const url = assetUrl(tep.file_url) ?? undefined;
  const kieu = kieuXemTruoc(tep);
  return (
    <div
      className="dkt-xem"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onDong();
      }}
    >
      <div className="dkt-xem__hop" role="dialog" aria-modal="true" aria-label={tep.ten_tep}>
        <header className="dkt-xem__dau">
          <p className="dkt-xem__ten">{tep.ten_tep}</p>
          <a className="dkt-nut dkt-nut--toi" href={url} download={tep.ten_tep} target="_blank" rel="noopener">
            <Icon name="download" size={15} />
            <span>Tải về</span>
          </a>
          <button ref={nutDong} type="button" className="dkt-nut dkt-nut--toi" onClick={onDong} aria-label="Đóng xem trước">
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="dkt-xem__than">
          {kieu === "anh" ? (
            <img src={url} alt={tep.ten_tep} />
          ) : (
            <iframe src={url} title={tep.ten_tep} />
          )}
        </div>
      </div>
    </div>
  );
}
