// Kỹ thuật máy — mảnh dùng chung cho 2 màn (Sửa chữa máy · Phiếu bảo trì).
// Đặt chung vì cả hai màn đều có: khối ảnh trước/sau, badge trạng thái, và cùng một luật
// "chưa có ảnh chứng thực thì chưa đóng được phiếu".
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { assetUrl } from "../api/client";
import { nhatKyDanhMuc, type NhatKyItem } from "../api/rebuildCatalog";
import { kyThuatMay, type Anh, type LoaiPhieu } from "../api/kyThuatMay";

/** Khớp `LOAI_MODULE` bên `routers/nhat_ky_danh_muc.py` — sai chuỗi là 404, không phải danh sách rỗng. */
export type LoaiNhatKy = "ky_thuat_sua_chua" | "ky_thuat_bao_tri";

export function fmtNgay(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function fmtNgayGio(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleDateString("vi-VN")} ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
}

/** `yyyy-mm-dd` của HÔM NAY theo giờ máy người dùng — dùng cho <input type="date">. */
export function homNay(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function Badge({ kieu, children }: { kieu: string; children: React.ReactNode }) {
  return <span className={`ktm-badge ktm-badge--${kieu}`}>{children}</span>;
}

/** Lịch sử thao tác của MỘT phiếu — ai làm gì, lúc nào.
 *
 * Đọc `audit_logs` qua endpoint nhật ký dùng chung (`/api/nhat-ky-danh-muc/{loai}/{id}`), không
 * đẻ bảng lịch sử riêng. Đây là chỗ duy nhất đọc được **lý do dời lịch của từng lần dời**: cột
 * `ly_do_doi` trên phiếu chỉ giữ lần gần nhất, dời lần thứ hai là lý do lần đầu mất hút.
 */
export function NhatKyPhieu({ loai, phieuId }: { loai: LoaiNhatKy; phieuId: number }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<NhatKyItem[]>([]);
  const [dangTai, setDangTai] = useState(true);

  useEffect(() => {
    if (!token) return;
    setDangTai(true);
    nhatKyDanhMuc(token, loai, phieuId)
      .then((r) => setRows(r.items ?? []))
      .catch(() => setRows([]))
      .finally(() => setDangTai(false));
  }, [token, loai, phieuId]);

  if (dangTai) return <p className="ktm-hint">Đang tải lịch sử…</p>;
  if (rows.length === 0) {
    return <p className="ktm-hint">Chưa có thao tác nào được ghi lại trên phiếu này.</p>;
  }
  return (
    <ol className="ktm-nk">
      {rows.map((r, i) => (
        <li key={i}>
          <div className="ktm-nk__dau">
            <span className="ktm-nk__gio">{fmtNgayGio(r.at)}</span>
            {/* Không có tên = việc do hệ thống/seed sinh, nói thẳng chứ đừng để trống cho người
                đọc tự đoán là lỗi hiển thị. */}
            <span className="ktm-nk__ai">{r.actor_name ?? "Hệ thống"}</span>
          </div>
          <div className="ktm-nk__viec">{r.detail}</div>
        </li>
      ))}
    </ol>
  );
}

/** Thanh chuyển trang. Phiếu tích lại theo tháng (≈400 phiếu/năm) nên KHÔNG tải hết rồi cuộn:
 *  lọc + phân trang đều ở server, đây chỉ là hai cái nút và một dòng "đang xem tới đâu". */
export function PhanTrang({ page, size, total, onDoi }: {
  page: number; size: number; total: number; onDoi: (p: number) => void;
}) {
  const soTrang = Math.max(1, Math.ceil(total / size));
  if (total <= size) return null;          // một trang thì thanh này chỉ tổ chiếm chỗ
  const dau = (page - 1) * size + 1;
  const cuoi = Math.min(page * size, total);
  return (
    <div className="ktm-trang">
      <span className="ktm-trang__so">
        {dau}–{cuoi} / {total} phiếu
      </span>
      <div className="ktm-trang__nut">
        <button type="button" disabled={page <= 1} onClick={() => onDoi(page - 1)}>
          <Icon name="chevron" size={14} style={{ transform: "rotate(90deg)" }} /> Trước
        </button>
        <span className="ktm-trang__vi-tri">Trang {page}/{soTrang}</span>
        <button type="button" disabled={page >= soTrang} onClick={() => onDoi(page + 1)}>
          Sau <Icon name="chevron" size={14} style={{ transform: "rotate(-90deg)" }} />
        </button>
      </div>
    </div>
  );
}

/** Khối ảnh của MỘT giai đoạn (hiện trạng / chứng thực).
 *
 * `batBuoc` chỉ đổi cách trình bày (viền + dòng nhắc) — cửa chặn thật nằm ở backend, không phải ở
 * đây: khoá nút bên FE mà backend không chặn thì gọi thẳng API là qua.
 */
export function AnhBox({
  loai, phieuId, giaiDoan, tieuDe, moTa, batBuoc = false, khoa = false, onChanged,
}: {
  loai: LoaiPhieu;
  phieuId: number;
  giaiDoan: "truoc" | "sau";
  tieuDe: string;
  moTa?: string;
  batBuoc?: boolean;
  khoa?: boolean;
  onChanged?: () => void;
}) {
  const { token } = useAuth();
  const [anh, setAnh] = useState<Anh[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [xemAnh, setXemAnh] = useState<Anh | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const nap = () => {
    if (!token) return;
    kyThuatMay.listAnh(token, loai, phieuId)
      .then((r) => setAnh(r.filter((a) => a.giai_doan === giaiDoan)))
      .catch(() => setAnh([]));
  };
  useEffect(nap, [token, loai, phieuId, giaiDoan]);

  const them = async (files: FileList | null) => {
    if (!token || !files?.length) return;
    setDangTai(true);
    setLoi(null);
    try {
      for (const f of Array.from(files)) {
        await kyThuatMay.uploadAnh(token, loai, phieuId, f, giaiDoan);
      }
      nap();
      onChanged?.();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Tải ảnh không thành công.");
    } finally {
      setDangTai(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const xoa = async (a: Anh) => {
    if (!token) return;
    setLoi(null);
    try {
      await kyThuatMay.removeAnh(token, a.id);
      nap();
      onChanged?.();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không xoá được ảnh.");
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!khoa && !isDragging) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (!khoa) {
      them(e.dataTransfer.files);
    }
  };

  return (
    <section
      className={`ktm-anh${batBuoc ? " ktm-anh--batbuoc" : ""}${isDragging ? " is-dragging" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="ktm-anh__head">
        <span className="ktm-anh__title">{tieuDe}</span>
        <span className={anh.length > 0 ? "ktm-anhchip is-du" : batBuoc ? "ktm-anhchip is-thieu" : "ktm-anhchip"}>
          <Icon name={anh.length > 0 ? "camera" : batBuoc ? "alert" : "camera"} size={12} />
          {anh.length > 0 ? `${anh.length} ảnh` : batBuoc ? "Chưa có ảnh (Bắt buộc)" : "0 ảnh"}
        </span>
      </div>
      {moTa && <p className="ktm-anh__mota">{moTa}</p>}

      {anh.length === 0 && !khoa ? (
        <div
          className={`ktm-dropzone${isDragging ? " is-dragging" : ""}${batBuoc ? " is-batbuoc" : ""}`}
          onClick={() => inputRef.current?.click()}
        >
          <div className="ktm-dropzone__icon">
            <Icon name="camera" size={30} />
          </div>
          <div className="ktm-dropzone__main">
            {dangTai ? "Đang nộp ảnh lên hệ thống…" : "Kéo & thả ảnh vào đây hoặc bấm để tải lên"}
          </div>
          <div className="ktm-dropzone__sub">
            Định dạng hỗ trợ: JPG, PNG, HEIC — Hỗ trợ tải nhiều ảnh cùng lúc
          </div>
          {batBuoc && (
            <span className="ktm-dropzone__tag">
              <Icon name="alert" size={12} /> Cần ít nhất 1 ảnh chứng thực mới xác nhận hoàn thành
            </span>
          )}
        </div>
      ) : (
        <div className="ktm-anh__grid">
          {anh.map((a) => (
            <figure className="ktm-anh__o" key={a.id}>
              <img src={assetUrl(a.file_url) ?? ""} alt={a.file_name} loading="lazy" onClick={() => setXemAnh(a)} />
              <div className="ktm-anh__overlay">
                <button type="button" className="ktm-anh__btn-view" title="Xem phóng to" onClick={() => setXemAnh(a)}>
                  <Icon name="eye" size={14} />
                </button>
                {!khoa && (
                  <button type="button" className="ktm-anh__btn-del" title="Xoá ảnh" onClick={() => xoa(a)}>
                    <Icon name="trash" size={14} />
                  </button>
                )}
              </div>
              <figcaption>{fmtNgayGio(a.uploaded_at)}</figcaption>
            </figure>
          ))}
          {!khoa && (
            <button
              type="button"
              className={`ktm-anh__them${isDragging ? " is-dragging" : ""}`}
              onClick={() => inputRef.current?.click()}
              disabled={dangTai}
            >
              <Icon name="plus" size={18} />
              <span>{dangTai ? "Đang tải…" : "Thêm ảnh"}</span>
            </button>
          )}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => them(e.target.files)}
      />
      {loi && <p className="ktm-anh__loi">{loi}</p>}

      {/* Lightbox Modal phóng to ảnh */}
      {xemAnh && (
        <div className="ktm-lightbox-overlay" onClick={() => setXemAnh(null)}>
          <div className="ktm-lightbox" onClick={(e) => e.stopPropagation()}>
            <div className="ktm-lightbox__head">
              <span className="ktm-lightbox__name">{xemAnh.file_name}</span>
              <button type="button" className="ktm-lightbox__close" onClick={() => setXemAnh(null)}>
                <Icon name="x" size={18} />
              </button>
            </div>
            <div className="ktm-lightbox__body">
              <img src={assetUrl(xemAnh.file_url) ?? ""} alt={xemAnh.file_name} />
            </div>
            <div className="ktm-lightbox__foot">
              Tải lên ngày {fmtNgayGio(xemAnh.uploaded_at)}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
