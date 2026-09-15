// Hàm thuần của khung "Tệp đính kèm" — tách khỏi component để kiểm bằng vitest không cần DOM.

/** Hình dạng tối thiểu một tệp đã lưu mà khung cần — bảng đính kèm nào khớp là gắn được. */
export interface TepDinhKem {
  id: number;
  ten_tep: string;
  file_url: string;
  content_type: string | null;
  kich_thuoc: number;
  nguoi_tai_ten: string | null;
  tai_luc: string;
}

export type TrangThaiViec = "cho" | "dang" | "loi";

/** Một tệp trong hàng đợi tải lên. Tải xong thì RỜI hàng (tệp đã hiện trong danh sách thật). */
export interface ViecTai {
  id: number;
  file: File;
  trangThai: TrangThaiViec;
  loi: string | null;
  /** Lỗi này gửi lại có thể qua không — không thì chỉ còn nút Bỏ. */
  thuLai?: boolean;
}

/** Id các việc nên bắt đầu NGAY để số việc đang chạy không vượt `gioiHan`. Việc lỗi đứng yên chờ
 *  người bấm "Thử lại" — tự chạy lại một tệp bị máy chủ từ chối (quá cỡ, đuôi .exe) chỉ lặp lỗi. */
export function chonViecKeTiep(hang: ViecTai[], gioiHan: number): number[] {
  const conCho = gioiHan - hang.filter((v) => v.trangThai === "dang").length;
  if (conCho <= 0) return [];
  return hang.filter((v) => v.trangThai === "cho").slice(0, conCho).map((v) => v.id);
}

/** Lỗi phát hiện được ở trình duyệt. Máy chủ vẫn kiểm lại — đây chỉ để báo ngay. */
export function kiemTruocKhiTai(f: { name: string; size: number }, maxBytes: number): string | null {
  if (f.size === 0) return "Tệp rỗng";
  if (f.size > maxBytes) return `Tệp vượt quá ${Math.round(maxBytes / (1024 * 1024))}MB`;
  return null;
}

export type KieuXemTruoc = "anh" | "pdf" | "khac";

/** Ảnh → thu nhỏ + phóng to; PDF → xem trong khung; còn lại (.ai .cdr .psd .zip…) → tải về. */
export function kieuXemTruoc(t: { ten_tep: string; content_type: string | null }): KieuXemTruoc {
  const ct = (t.content_type ?? "").toLowerCase();
  if (ct.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(t.ten_tep)) return "anh";
  if (ct === "application/pdf" || /\.pdf$/i.test(t.ten_tep)) return "pdf";
  return "khac";
}

/** "820 B" · "1,5 KB" · "12,3 MB". */
export function dungLuong(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} KB`;
  return `${(kb / 1024).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} MB`;
}

/** "AI" · "CDR" · "TỆP" — nhãn thay ảnh thu nhỏ. Đuôi dài quá 4 ký tự thì không phải đuôi đáng tin. */
export function duoiTep(ten: string): string {
  const m = /\.([a-z0-9]{1,4})$/i.exec(ten);
  return m && m.index > 0 ? m[1].toUpperCase() : "TỆP";
}

/** Mất mạng (0), hết giờ (408), bị giới hạn nhịp (429), máy chủ lỗi (5xx) thì lần sau có thể khác.
 *  Còn lại là máy chủ đã từ chối chính tệp hoặc quyền — gửi lại y nguyên vẫn bị từ chối. */
export function nenThuLai(status: number): boolean {
  return status === 0 || status === 408 || status === 429 || status >= 500;
}
