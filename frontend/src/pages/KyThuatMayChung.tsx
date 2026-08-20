// Kỹ thuật máy — mảnh dùng chung cho 2 màn (Sửa chữa máy · Phiếu bảo trì).
// Đặt chung vì cả hai màn đều có: khối ảnh trước/sau, badge trạng thái, và cùng một luật
// "chưa có ảnh chứng thực thì chưa đóng được phiếu".
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icons";
import { assetUrl } from "../api/client";
import { nhatKyDanhMuc, type NhatKyItem } from "../api/rebuildCatalog";
import { kyThuatMay, type Anh, type LoaiPhieu } from "../api/kyThuatMay";
import { coChu, nenAnh } from "../lib/anhNen";

/** Màn hẹp HOẶC không có hover (cảm ứng) ⇒ đổi sang bố cục danh sách/thẻ.
 *
 * Khai MỘT chỗ cho cả lịch lẫn bảng: hai định nghĩa breakpoint là sớm muộn một màn đổi hình còn
 * màn kia thì không, ngay trên cùng một cái điện thoại. */
export function useManHep(): boolean {
  const truyVan = "(max-width: 820px), (hover: none)";
  const [hep, setHep] = useState(() =>
    typeof window !== "undefined" && window.matchMedia(truyVan).matches);
  useEffect(() => {
    const mq = window.matchMedia(truyVan);
    const doi = () => setHep(mq.matches);
    mq.addEventListener("change", doi);
    return () => mq.removeEventListener("change", doi);
  }, []);
  return hep;
}

/** Khớp `LOAI_MODULE` bên `routers/nhat_ky_danh_muc.py` — sai chuỗi là 404, không phải danh sách rỗng. */
export type LoaiNhatKy = "ky_thuat_sua_chua" | "ky_thuat_bao_tri" | "ky_thuat_yeu_cau";

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

/** Badge trạng thái của PHIẾU BẢO TRÌ — một chỗ duy nhất dựng nó.
 *
 * "Quá hạn" không phải trạng thái lưu trong DB mà là dẫn xuất (chưa xong + hạn đã qua), nên nó
 * phải nằm chung với hai trạng thái thật ở đây; tách ra là mỗi màn tự chọn lúc nào gọi là quá hạn.
 * Trước đây badge này dựng tay ở 6 chỗ (bảng · thẻ điện thoại · drawer · 4 chỗ trong lịch) và đã
 * bắt đầu lệch nhau: chỗ có icon chỗ không, chỗ gọi "Chờ làm" chỗ "Chờ thực hiện".
 */
export function BadgeBaoTri({ trangThai, quaHan, gonNhe = false }: {
  trangThai: string; quaHan?: boolean; gonNhe?: boolean;
}) {
  if (trangThai === "hoan_thanh") {
    return (
      <Badge kieu="tt-hoan_thanh">
        <Icon name="check" size={11} /> Hoàn thành
      </Badge>
    );
  }
  // Đã hủy đứng TRƯỚC nhánh quá hạn: phiếu hủy không bao giờ là "quá hạn" (backend cũng không tính),
  // để mờ + gạch ngang cho mắt lướt qua không nhầm với việc còn phải làm.
  if (trangThai === "da_huy") {
    return (
      <Badge kieu="tt-da_huy">
        <Icon name="ban" size={11} /> Đã hủy
      </Badge>
    );
  }
  if (quaHan) {
    return (
      <Badge kieu="tt-qua_han">
        <Icon name="alert" size={11} /> Quá hạn
      </Badge>
    );
  }
  return (
    <Badge kieu="tt-cho_thuc_hien">
      {!gonNhe && <Icon name="clock" size={11} />} Chờ làm
    </Badge>
  );
}

/** Lịch sử thao tác của MỘT phiếu — ai làm gì, lúc nào.
 *
 * Đọc `audit_logs` qua endpoint nhật ký dùng chung (`/api/nhat-ky-danh-muc/{loai}/{id}`), không
 * đẻ bảng lịch sử riêng. Đây là chỗ đọc được AI làm gì lúc nào: tick việc con, hủy phiếu kèm lý do,
 * và (dữ liệu cũ) lý do từng lần dời lịch trước khi chức năng dời bị gỡ.
 */
export function NhatKyPhieu({ loai, phieuId }: { loai: LoaiNhatKy; phieuId: number }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<NhatKyItem[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);
  const [lan, setLan] = useState(0);

  useEffect(() => {
    if (!token) return;
    setDangTai(true);
    setLoi(null);
    nhatKyDanhMuc(token, loai, phieuId)
      .then((r) => setRows(r.items ?? []))
      // Nuốt lỗi ở đây là mạng hỏng hiện y hệt "chưa có thao tác nào" — người đọc kết luận phiếu
      // sạch sẽ trong khi thật ra họ chưa nhìn thấy gì cả.
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được lịch sử thao tác."))
      .finally(() => setDangTai(false));
  }, [token, loai, phieuId, lan]);

  if (dangTai) return <p className="ktm-hint">Đang tải lịch sử…</p>;
  if (loi) {
    return (
      <p className="ktm-hint ktm-hint--loi">
        {loi}{" "}
        <button type="button" className="ktm-hint__thu-lai" onClick={() => setLan((n) => n + 1)}>
          Thử lại
        </button>
      </p>
    );
  }
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

// `PhanTrang` tự viết ĐÃ GỠ 14/08/2026 — hai màn dùng `components/Pager.tsx` như mọi màn khác
// (`Pager` + `trangHopLe`). Bản riêng ở đây thiếu `loading` nên bấm dồn "Sau" ra hai lượt gọi
// chồng nhau, và tự ẩn khi chỉ có một trang nên người dùng mất luôn dòng "Tổng N phiếu".

/** Khối ảnh của MỘT giai đoạn (hiện trạng / chứng thực).
 *
 * `batBuoc` chỉ đổi cách trình bày (viền + dòng nhắc) — cửa chặn thật nằm ở backend, không phải ở
 * đây: khoá nút bên FE mà backend không chặn thì gọi thẳng API là qua.
 *
 * Danh sách ảnh do DRAWER nạp và truyền xuống (`tatCaAnh` = ảnh của cả phiếu, khối này tự lọc theo
 * giai đoạn): hai khối trước/sau nếu mỗi cái tự gọi API thì mở một phiếu là hai request giống hệt
 * nhau, thêm/xoá một tấm lại hai lần nữa.
 */
export function AnhBox({
  loai, phieuId, giaiDoan, tieuDe, moTa, batBuoc = false, khoa = false,
  tatCaAnh, onChanged,
}: {
  loai: LoaiPhieu;
  phieuId: number;
  giaiDoan: "truoc" | "sau";
  tieuDe: string;
  moTa?: string;
  batBuoc?: boolean;
  khoa?: boolean;
  tatCaAnh: Anh[];
  onChanged?: () => void;
}) {
  const { token } = useAuth();
  const [dangTai, setDangTai] = useState(false);
  const [dangNen, setDangNen] = useState(false);
  const [tietKiem, setTietKiem] = useState<{ goc: number; sau: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [xemAnh, setXemAnh] = useState<Anh | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const anh = tatCaAnh.filter((a) => a.giai_doan === giaiDoan);

  const them = async (files: FileList | null) => {
    if (!token || !files?.length) return;
    setLoi(null);
    setTietKiem(null);
    let goc = 0;
    let sau = 0;
    try {
      for (const f of Array.from(files)) {
        // Nén TRƯỚC khi gửi: ảnh điện thoại 4–8MB/tấm, mạng xưởng yếu thì tải nguyên bản là thợ
        // đứng chờ. Nén hỏng (HEIC…) thì `nenAnh` trả lại file gốc chứ không chặn.
        setDangNen(true);
        const kq = await nenAnh(f);
        setDangNen(false);
        goc += kq.goc;
        sau += kq.sau;
        setDangTai(true);
        await kyThuatMay.uploadAnh(token, loai, phieuId, kq.file, giaiDoan);
      }
      if (sau < goc) setTietKiem({ goc, sau });
      onChanged?.();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Tải ảnh không thành công.");
    } finally {
      setDangNen(false);
      setDangTai(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const xoa = async (a: Anh) => {
    if (!token) return;
    setLoi(null);
    try {
      await kyThuatMay.removeAnh(token, a.id);
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
            {dangNen ? "Đang nén ảnh cho nhẹ…"
              : dangTai ? "Đang nộp ảnh lên hệ thống…"
              : "Kéo & thả ảnh vào đây hoặc bấm để tải lên"}
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
              disabled={dangTai || dangNen}
            >
              <Icon name="plus" size={18} />
              <span>{dangNen ? "Đang nén…" : dangTai ? "Đang tải…" : "Thêm ảnh"}</span>
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
      {/* Nói ra đã nén được bao nhiêu: thợ thấy "6,2 MB → 380 KB" thì hiểu vì sao lần này tải nhanh,
          và biết ảnh vẫn lên đủ chứ không phải bị bỏ bớt. */}
      {tietKiem && (
        <p className="ktm-anh__nen">
          <Icon name="zap" size={11} /> Đã nén cho nhẹ: {coChu(tietKiem.goc)} → {coChu(tietKiem.sau)}
        </p>
      )}
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
